import time
import sys
import random

# --- Configuration ---
# Set to True to force dummy mode even if a real sensor library was added later
FORCE_DUMMY_MODE = False # Set to True to test dummy behaviour
DUMMY_O2_PERCENT = 20.9 # Standard atmospheric O2
DUMMY_VARIATION = 0.1 # Simulate small fluctuations

# Attempt to import the DFRobot library
_DFRobotOxygenSensorLib = None
try:
    # The exact library name might vary, adjust if necessary
    from DFRobot_OxygenSensor import OxygenSensor as _DFRobotOxygenSensorLib
    print("DFRobot_OxygenSensor library found.")
except ImportError:
    print("Warning: DFRobot_OxygenSensor library not found.")
    print("Please install it, e.g., 'pip install DFRobot_OxygenSensor'")
    print("O2 sensor will operate in DUMMY MODE.")

# Default I2C bus for Raspberry Pi
I2C_BUS = 1
# Default I2C Address for the DFRobot Gravity O2 Sensor
DEFAULT_O2_ADDRESS = 0x73 # Use the known default address directly

class DFRobotO2Sensor:
    """
    Reads Oxygen concentration from a DFRobot Gravity I2C Oxygen Sensor.
    Assumes usage of the DFRobot_OxygenSensor Python library.
    Includes dummy mode fallback for testing or if sensor fails initialization.
    """
    def __init__(self, i2c_bus: int = I2C_BUS, i2c_address: int = DEFAULT_O2_ADDRESS):
        """
        Initializes the DFRobot O2 sensor reader.

        Args:
            i2c_bus: The I2C bus number (default is 1 for Raspberry Pi).
            i2c_address: The I2C address of the sensor (currently not used by library?).
        """
        self.i2c_bus = i2c_bus
        self.i2c_address = i2c_address # Store address, though library might not use it directly
        self.is_dummy = False
        self._sensor: _DFRobotOxygenSensorLib | None = None
        self._last_o2 = DUMMY_O2_PERCENT # Initialize with dummy value

        if FORCE_DUMMY_MODE or _DFRobotOxygenSensorLib is None:
            self.is_dummy = True
            print(f"DFRobotO2Sensor (Bus {i2c_bus}) initialized in DUMMY MODE.")
            return

        try:
            # Initialize the sensor using the DFRobot library
            # The library seems to only take the bus number in constructor
            self._sensor = _DFRobotOxygenSensorLib(self.i2c_bus)
            print(f"DFRobotO2Sensor attempting connection on I2C bus {i2c_bus}...")
            # Perform an initial read attempt to confirm connectivity
            success = self._read_sensor_internal()
            if success:
                 print(f"DFRobotO2Sensor successfully initialized. Initial reading: {self._last_o2:.2f}%")
            else:
                 print(f"Warning: DFRobotO2Sensor initialized, but initial read failed. Check connection/address. Falling back to DUMMY MODE.")
                 self.is_dummy = True
                 self._sensor = None # Ensure sensor is None if falling back

        except (FileNotFoundError, OSError) as e: # Common I2C/hardware errors
            print(f"Warning: Failed to initialize DFRobot O2 sensor on I2C bus {self.i2c_bus}: {e}. Falling back to DUMMY MODE.")
            self.is_dummy = True
            self._sensor = None
        except Exception as e:
            # Catch any other unexpected errors during init
            print(f"Warning: Unexpected error initializing DFRobot O2 sensor: {e}. Falling back to DUMMY MODE.")
            self.is_dummy = True
    def read_oxygen_concentration(self) -> float:
        """
        Reads the oxygen concentration.
        Returns dummy values if in dummy mode.
        If not in dummy mode, attempts to read the sensor with retries.
        On failure, returns the last known good value or the initial dummy value.

        Returns:
            Oxygen concentration in percent.
        """
        if self.is_dummy:
            # Simulate slight variation around the dummy value
            o2 = round(DUMMY_O2_PERCENT + random.uniform(-DUMMY_VARIATION, DUMMY_VARIATION), 2)
            # Clamp to valid range
            o2 = max(0.0, min(100.0, o2))
            self._last_o2 = o2
            # print(f"O2 Read (Dummy): {o2}%") # Optional debug
            return o2

        # --- Attempt real sensor read ---
        success = self._read_sensor_internal()

        if not success:
             print(f"O2 Read Failed on I2C bus {self.i2c_bus}. Returning last known/dummy value: {self._last_o2:.2f}%")

        # Return the latest value stored in _last_o2
        return self._last_o2


    def _read_sensor_internal(self) -> bool:
        """
        Internal helper to attempt reading the real sensor with retries.
        Updates _last_o2 on success.

        Returns:
            True if read was successful within retries, False otherwise.
        """
        if not self._sensor:
             print("O2 Internal Read Error: Sensor device not available.")
             return False

        retries = 3
        delay_seconds = 1 # Wait between I2C retries

        for attempt in range(retries):
            try:
                # Call the library function to get data
                # Assuming get_oxygen_data takes internal retries (e.g., 1) and returns %
                concentration = self._sensor.get_oxygen_data(1)

                # Check for valid reading and realistic values
                if concentration is not None and 0 <= concentration <= 100:
                    self._last_o2 = round(concentration, 2)
                    # print(f"O2 Read Success (Attempt {attempt+1}): {self._last_o2:.2f}%") # Debug
                    return True # Success
                else:
                    print(f"O2 Read Attempt {attempt + 1}: Unrealistic/None value ({concentration}). Retrying...")

            except OSError as e:
                # Common I2C error
                 print(f"O2 Read Attempt {attempt + 1} I/O Error: {e}. Check connection/address. Retrying...")
            except Exception as e:
                print(f"O2 Read Attempt {attempt + 1} Unexpected Error: {e}. Retrying...")

            # Wait before the next retry
            if attempt < retries - 1:
                time.sleep(delay_seconds)

        # If loop completes without success
        return False

    @property
    def oxygen_concentration(self) -> float:
        """Returns the last known oxygen concentration percentage (could be dummy)."""
        # In this implementation, read() updates _last_o2, so just return it.
        return self._last_o2

    def close(self):
        """Releases any resources held by the sensor object (if applicable)."""
        # Check if the library requires an explicit close method. If not, just clear the reference.
        if self._sensor:
             print("Closing DFRobot O2 Sensor resources (clearing reference).")
             # If self._sensor had a close() method, call it here:
             # try:
             #     self._sensor.close()
             # except AttributeError:
             #     pass # Library object might not have close()
             self._sensor = None

    # Remove __del__ method


# Example Usage (for testing purposes)
if __name__ == '__main__':
    print("Testing DFRobotO2Sensor...")
    # Ensure I2C is enabled: sudo raspi-config -> Interface Options -> I2C
    # Ensure library is installed: pip install DFRobot_OxygenSensor
    # Check sensor address: sudo i2cdetect -y 1

    sensor = None
    try:
        sensor = DFRobotO2Sensor() # Use default bus and address

        if sensor._sensor: # Check if initialization seemed okay
            print("\nReading periodically for 20 seconds...")
            for i in range(10):
                o2_level = sensor.read_oxygen_concentration()
                if o2_level is not None:
                    print(f"Read {i+1}: O2 = {o2_level:.2f}%")
                else:
                    print(f"Read {i+1}: Failed")
                time.sleep(2) # Wait between reads
        else:
            print("Sensor initialization failed, cannot perform reads.")

    except Exception as e:
        print(f"\nAn error occurred during testing: {e}")
    finally:
        if sensor:
            sensor.close()
        print("\nTest finished.")