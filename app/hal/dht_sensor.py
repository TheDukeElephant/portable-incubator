import adafruit_dht
import board
import time
# Sensor type: Adafruit_DHT.DHT11, Adafruit_DHT.DHT22, or Adafruit_DHT.AM2302
SENSOR_TYPE = adafruit_dht.DHT22

class DHT22Sensor:
    """
    Reads Temperature and Humidity from a DHT22 sensor connected to a specific GPIO pin.
    Uses the Adafruit_DHT library.
    """
    def __init__(self, pin: int):
        """
        Initializes the DHT22 sensor reader.

        Args:
            pin: The GPIO pin number (BCM numbering) the sensor's data line is connected to.
        """
        self.pin = pin
        self.sensor_type = SENSOR_TYPE
        self._last_temp = None
        self._last_humidity = None
        print(f"DHT22Sensor initialized for GPIO {pin}")
        # Perform an initial read to check connectivity, though reads can be slow
        # self.read()

    def read(self) -> tuple[float | None, float | None]:
        """
        Reads temperature and humidity from the sensor.

        Returns:
            A tuple containing (temperature_celsius, humidity_percent).
            Returns (None, None) if the read fails after retries.
        """
        # DHT sensors can be finicky, retrying is often necessary.
        retries = 5
        delay_seconds = 2 # DHT22 needs at least 2 seconds between reads

        for attempt in range(retries):
            try:
                humidity, temperature = adafruit_dht.read(self.sensor_type, self.pin)

                # Check if reading was successful
                if humidity is not None and temperature is not None:
                    # Optional: Add sanity checks for realistic values
                    if 0 <= humidity <= 100 and -40 < temperature < 80:
                        self._last_humidity = round(humidity, 2)
                        self._last_temp = round(temperature, 2)
                        # print(f"DHT22 Read Success: Temp={self._last_temp}°C, Hum={self._last_humidity}%")
                        return self._last_temp, self._last_humidity
                    else:
                        print(f"DHT22 Read Warning: Unrealistic values Temp={temperature}, Hum={humidity}")
                        # Treat unrealistic values as a failure for this attempt
                else:
                    # Reading failed, wait before retrying
                    # print(f"DHT22 Read Attempt {attempt + 1} failed. Retrying...")
                    pass # Adafruit_DHT.read already waits a bit

            except RuntimeError as error:
                # Errors happen fairly often, DHTs are tricky sensors.
                print(f"DHT22 Read Attempt {attempt + 1} Runtime Error: {error}. Retrying...")
            except Exception as e:
                # Catch other potential errors
                print(f"DHT22 Read Attempt {attempt + 1} Unexpected Error: {e}. Retrying...")

            # Wait before the next retry
            if attempt < retries - 1:
                time.sleep(delay_seconds)

        print(f"DHT22 Read Failed after {retries} attempts on GPIO {self.pin}.")
        # Return last known good values if available, otherwise None
        # Or simply return None, None to indicate current read failure
        return None, None # Indicate failure to get a fresh reading

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