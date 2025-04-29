import adafruit_dht
import board
import time
import random

# --- Configuration ---
# Set to True to force dummy mode even if a real sensor library was added later
FORCE_DUMMY_MODE = False # Set to True to test dummy behaviour
DUMMY_TEMP_CELSIUS = 25.0
DUMMY_HUMIDITY_PERCENT = 50.0
DUMMY_VARIATION = 0.5 # Simulate small fluctuations

# Sensor type: Adafruit_DHT.DHT11, Adafruit_DHT.DHT22, or Adafruit_DHT.AM2302
SENSOR_TYPE = adafruit_dht.DHT22

class DHT22Sensor:
    """
    Reads Temperature and Humidity from a DHT22 sensor connected to a specific GPIO pin.
    Uses the adafruit-circuitpython-dht library.
    Includes dummy mode fallback for testing or if sensor fails initialization.
    """
    def __init__(self, pin: int):
        """
        Initializes the DHT22 sensor reader.

        Args:
            pin: The GPIO pin number (BCM numbering) the sensor's data line is connected to.
        """
        self.pin_number = pin
        self.is_dummy = False
        self.dht_device = None
        self._last_temp = DUMMY_TEMP_CELSIUS # Initialize with dummy values
        self._last_humidity = DUMMY_HUMIDITY_PERCENT

        if FORCE_DUMMY_MODE:
            self.is_dummy = True
            print(f"DHT22Sensor (GPIO {pin}) initialized in FORCED DUMMY MODE.")
            return

        try:
            # 1. Check board pin validity
            try:
                self.board_pin = getattr(board, f'D{pin}')
            except AttributeError:
                 raise ValueError(f"Invalid GPIO pin: D{pin} not found in board module.")

            # 2. Attempt to initialize the actual sensor device
            # use_pulseio=False might be needed on some platforms if RuntimeError occurs often
            self.dht_device = SENSOR_TYPE(self.board_pin, use_pulseio=False)
            # Perform an initial read attempt to confirm connectivity
            self._read_sensor_internal()
            print(f"DHT22Sensor initialized for GPIO {pin}. Initial read: Temp={self._last_temp}°C, Hum={self._last_humidity}%")

        except (ValueError, RuntimeError, NotImplementedError) as e:
            print(f"Warning: Failed to initialize DHT22 sensor on GPIO {pin}: {e}. Falling back to DUMMY MODE.")
            self.is_dummy = True
            self.dht_device = None # Ensure device is None in dummy mode
            # Keep dummy values in _last_temp/_last_humidity
        except Exception as e:
            # Catch any other unexpected errors during init
            print(f"Warning: Unexpected error initializing DHT22 sensor on GPIO {pin}: {e}. Falling back to DUMMY MODE.")
            self.is_dummy = True
            self.dht_device = None

    def read(self) -> tuple[float | None, float | None]:
        """
        Reads temperature and humidity.
        Returns dummy values if in dummy mode.
        If not in dummy mode, attempts to read the sensor with retries.
        On failure, returns the last known good values or dummy values if none exist.

        Returns:
            A tuple containing (temperature_celsius, humidity_percent).
        """
        if self.is_dummy:
            # Simulate slight variation around the dummy value
            temp = round(DUMMY_TEMP_CELSIUS + random.uniform(-DUMMY_VARIATION, DUMMY_VARIATION), 1)
            hum = round(DUMMY_HUMIDITY_PERCENT + random.uniform(-DUMMY_VARIATION, DUMMY_VARIATION), 1)
            # Clamp humidity to valid range
            hum = max(0.0, min(100.0, hum))
            self._last_temp = temp
            self._last_humidity = hum
            # print(f"DHT22 Read (Dummy): Temp={temp}°C, Hum={hum}%") # Optional debug
            return temp, hum

        # --- Attempt real sensor read ---
        success = self._read_sensor_internal()

        if not success:
             print(f"DHT22 Read Failed on GPIO {self.pin_number}. Returning last known/dummy values: Temp={self._last_temp}°C, Hum={self._last_humidity}%")

        # Return the latest values stored in _last_temp/_last_humidity
        # which are either the last successful read or the initial dummy values.
        return self._last_temp, self._last_humidity


    def _read_sensor_internal(self) -> bool:
        """
        Internal helper to attempt reading the real sensor with retries.
        Updates _last_temp and _last_humidity on success.

        Returns:
            True if read was successful within retries, False otherwise.
        """
        if not self.dht_device: # Should not happen if not in dummy mode, but check anyway
             print("DHT22 Internal Read Error: Sensor device not available.")
             return False

        retries = 5
        delay_seconds = 2 # DHT22 needs at least 2 seconds between reads

        for attempt in range(retries):
            try:
                temperature = self.dht_device.temperature
                humidity = self.dht_device.humidity

                # Check if reading was successful and values are realistic
                if humidity is not None and temperature is not None and \
                   0 <= humidity <= 100 and -40 < temperature < 80:
                    self._last_humidity = round(humidity, 2)
                    self._last_temp = round(temperature, 2)
                    # print(f"DHT22 Read Success (Attempt {attempt+1}): Temp={self._last_temp}°C, Hum={self._last_humidity}%") # Debug
                    return True # Success
                else:
                    # Got None or unrealistic values
                    print(f"DHT22 Read Attempt {attempt + 1}: Unrealistic/None values (Temp={temperature}, Hum={humidity}). Retrying...")

            except RuntimeError as error:
                # Common error for read failures
                print(f"DHT22 Read Attempt {attempt + 1} Runtime Error: {error}. Retrying...")
                # Optional: Consider re-initializing device on repeated errors
                # try:
                #     self.dht_device.exit() # If exit method exists
                # except: pass
                # try:
                #     self.dht_device = SENSOR_TYPE(self.board_pin, use_pulseio=False)
                # except:
                #     print("Failed to re-initialize DHT device after error.")
                #     self.is_dummy = True # Fallback to dummy if re-init fails
                #     return False
            except Exception as e:
                # Catch other potential errors
                print(f"DHT22 Read Attempt {attempt + 1} Unexpected Error: {e}. Retrying...")

            # Wait before the next retry
            if attempt < retries - 1:
                time.sleep(delay_seconds)

        # If loop completes without success
        return False

    @property
    def temperature(self) -> float | None:
        """Returns the last successfully read temperature in Celsius."""
        # Optionally trigger a read here if data is stale, or rely on external loop
        # self.read() # Be careful about read frequency limits
        return self._last_temp

    @property
    def humidity(self) -> float | None:
        """Returns the last successfully read humidity percentage."""
        # Optionally trigger a read here
        # self.read()
        return self._last_humidity

# Example Usage (for testing purposes)
if __name__ == '__main__':
    # Replace with the actual GPIO pin connected to the DHT22 data line
    DHT_PIN = 4
    print(f"Testing DHT22Sensor on GPIO {DHT_PIN}...")

    try:
        sensor = DHT22Sensor(DHT_PIN)

        print("Attempting initial read...")
        temp, hum = sensor.read()
        if temp is not None and hum is not None:
            print(f"Initial Read: Temperature={temp:.2f}°C, Humidity={hum:.2f}%")
        else:
            print("Initial read failed.")

        print("\nReading periodically for 20 seconds...")
        for i in range(10):
            temp, hum = sensor.read()
            if temp is not None and hum is not None:
                print(f"Read {i+1}: Temp={temp:.2f}°C, Hum={hum:.2f}%")
            else:
                print(f"Read {i+1}: Failed")
            # Respect the sensor's minimum read interval
            time.sleep(2) # Wait 2 seconds between reads

    except Exception as e:
        print(f"\nAn error occurred during testing: {e}")
        print("Ensure the Adafruit_DHT library is installed (`pip install Adafruit_DHT`)")
        print("Ensure the script is run with sufficient permissions (e.g., using sudo)")
        print("Check GPIO pin connection and sensor power.")
    finally:
        print("\nTest finished.")