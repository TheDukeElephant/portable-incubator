import time
import sys
# Attempt to import the DFRobot library
try:
    # The exact library name might vary, adjust if necessary
    # Common patterns: DFRobot_OxygenSensor, dfrobot_oxygen
    # Assuming the library provides a class named OxygenSensor
    from DFRobot_OxygenSensor import OxygenSensor
except ImportError:
    print("Warning: DFRobot_OxygenSensor library not found.")
    print("Please install it, e.g., 'pip install DFRobot_OxygenSensor'")
    # Define a dummy class to allow the rest of the app to load
    class OxygenSensor:
        OXYGEN_ADDRESS_3 = 0x73 # Common default, adjust if needed
        def __init__(self, bus): pass
        def get_oxygen_data(self, retries): return 0.0 # Dummy value

# Default I2C bus for Raspberry Pi
I2C_BUS = 1
# Default I2C Address for the DFRobot Gravity O2 Sensor (check datasheet/ jumpers)
# Common addresses are 0x70, 0x71, 0x72, 0x73. Using 0x73 as a guess.
DEFAULT_O2_ADDRESS = OxygenSensor.OXYGEN_ADDRESS_3 # Use address from library if defined

class DFRobotO2Sensor:
    """
    Reads Oxygen concentration from a DFRobot Gravity I2C Oxygen Sensor.
    Assumes usage of the DFRobot_OxygenSensor Python library.
    """
    def __init__(self, i2c_bus: int = I2C_BUS, i2c_address: int = DEFAULT_O2_ADDRESS):
        """
        Initializes the DFRobot O2 sensor reader.

        Args:
            i2c_bus: The I2C bus number (default is 1 for Raspberry Pi).
            i2c_address: The I2C address of the sensor.
        """
        self.i2c_bus = i2c_bus
        self.i2c_address = i2c_address
        self._sensor = None
        self._last_o2 = None

        try:
            # Initialize the sensor using the DFRobot library
            # The library might handle bus opening/closing internally
            self._sensor = OxygenSensor(self.i2c_bus) # Pass bus number
            # Some libraries might require address setting separately or during method calls
            # Or the library might auto-detect if only one sensor is present.
            # This part heavily depends on the specific library's API.
            # We might need to call a specific init or begin method here.
            print(f"DFRobotO2Sensor attempting connection on I2C bus {i2c_bus}, address {hex(i2c_address)}...")
            # Perform an initial read or check status if the library supports it
            self.read_oxygen_concentration() # Call read to check connection
            if self._last_o2 is not None:
                 print(f"DFRobotO2Sensor successfully initialized. Initial reading: {self._last_o2:.2f}%")
            else:
                 print(f"DFRobotO2Sensor initialized, but initial read failed. Check connection/address/library.")

        except ImportError:
             print("DFRobot_OxygenSensor library not installed. Cannot communicate with sensor.")
        except FileNotFoundError:
            print(f"Error: I2C bus {self.i2c_bus} not found. Ensure I2C is enabled on the Raspberry Pi.")
        except Exception as e:
            print(f"Error initializing DFRobot O2 Sensor: {e}")
            print("Check I2C connection, address, and library installation.")
            self._sensor = None # Ensure sensor object is None if init fails

    def read_oxygen_concentration(self) -> float | None:
        """
        Reads the oxygen concentration from the sensor.

        Returns:
            Oxygen concentration in percent, or None if the read fails.
        """
        if not self._sensor:
            print("DFRobot O2 Sensor not initialized, cannot read.")
            return None

        retries = 3
        for attempt in range(retries):
            try:
                # Call the library function to get data
                # The number of retries internal to the library function might vary
                # The library might return concentration directly, or require calculation
                # Assuming get_oxygen_data returns concentration %
                # The library might need the address passed here too.
                concentration = self._sensor.get_oxygen_data(1) # Example: 1 internal retry

                if concentration is not None: # Check for valid reading
                     # Add sanity checks if needed (e.g., 0 <= concentration <= 100)
                     if 0 <= concentration <= 100:
                         self._last_o2 = round(concentration, 2)
                         # print(f"O2 Read Success: {self._last_o2:.2f}%")
                         return self._last_o2
                     else:
                         print(f"O2 Read Warning: Unrealistic value {concentration}%.")
                         # Treat as failure for this attempt
                else:
                    print(f"O2 Read Attempt {attempt + 1} failed (None returned). Retrying...")

            except OSError as e:
                # Common I2C error
                 print(f"O2 Read Attempt {attempt + 1} I/O Error: {e}. Check connection/address. Retrying...")
            except Exception as e:
                print(f"O2 Read Attempt {attempt + 1} Unexpected Error: {e}. Retrying...")

            # Wait before retrying
            if attempt < retries - 1:
                time.sleep(1) # Wait a bit before retrying I2C communication

        print(f"O2 Read Failed after {retries} attempts.")
        # Return last known good value? Or None? Returning None indicates current failure.
        return None

    @property
    def oxygen_concentration(self) -> float | None:
        """Returns the last successfully read oxygen concentration percentage."""
        return self._last_o2

    def close(self):
        """Releases any resources held by the sensor object (if necessary)."""
        # The DFRobot library might handle this in its __del__ or require an explicit close.
        print("Closing DFRobot O2 Sensor resources (if applicable).")
        self._sensor = None # Clear the sensor object

    def __del__(self):
        """Ensures resources are released when the object is destroyed."""
        self.close()


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