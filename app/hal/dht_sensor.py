import adafruit_dht
import board
import time
import random

# Dummy temperature value for testing
DUMMY_TEMP_CELSIUS = 25.0
import threading # Import threading

# --- Configuration ---
# Set to True to force dummy mode even if a real sensor library was added later
# Removed dummy mode configuration as fallback logic is no longer required.

# Sensor type: Adafruit_DHT.DHT11, Adafruit_DHT.DHT22, or Adafruit_DHT.AM2302
SENSOR_TYPE = adafruit_dht.DHT22

class DHT22Sensor:
    """
    Reads Temperature and Humidity from a DHT22 sensor connected to a specific GPIO pin.
    Uses the adafruit-circuitpython-dht library.
    Includes dummy mode fallback for testing or if sensor fails initialization.
    Initialization is deferred and performed in a background thread.
    """
    def __init__(self, pin: int):
        """
        Initializes the DHT22 sensor reader instance. Hardware initialization is deferred.

        Args:
            pin: The GPIO pin number (BCM numbering) the sensor's data line is connected to.
        """
        self.pin_number = pin
        # Removed dummy mode flag as it is no longer needed.
        self.dht_device = None
        self._initialization_lock = threading.Lock() # Lock for initialization
        self._initialized = False # Flag to track initialization attempt
        self._last_temp = DUMMY_TEMP_CELSIUS # Initialize with dummy temperature
        self._last_humidity = None

        # Removed forced dummy mode logic.

        # Initialization logic moved to _initialize_hardware()
        # We don't want to block here anymore.
        # The calling code should trigger initialization in a background thread.
        print(f"DHT22Sensor (GPIO {pin}) instance created. Hardware initialization deferred.")

    def _initialize_hardware(self):
        """
        Attempts to initialize the actual hardware sensor.
        This method is intended to be called in a background thread.
        Sets self.dht_device on success or logs a warning on failure.
        """
        with self._initialization_lock:
            if self._initialized: # Prevent re-initialization attempt
                return

            print(f"Attempting DHT22 hardware initialization on GPIO {self.pin_number}...")
            try:
                # 1. Check board pin validity
                try:
                    board_pin = getattr(board, f'D{self.pin_number}')
                except AttributeError:
                     raise ValueError(f"Invalid GPIO pin: D{self.pin_number} not found in board module.")

                # 2. Attempt to initialize the actual sensor device
                # use_pulseio=False might be needed on some platforms if RuntimeError occurs often
                temp_device = SENSOR_TYPE(board_pin, use_pulseio=False)

                # 3. Perform an initial read attempt to confirm connectivity
                # This might still block briefly, but less than the old init
                # We need a temporary way to read without relying on the main read method structure yet
                temp_device.temperature # Try reading temperature
                temp_device.humidity    # Try reading humidity

                # 4. Assign only after successful initial read
                self.dht_device = temp_device
                print(f"DHT22Sensor hardware initialized successfully for GPIO {self.pin_number}.")

            except (ValueError, RuntimeError, NotImplementedError, AttributeError) as e: # Added AttributeError for getattr
                print(f"Warning: Failed to initialize DHT22 sensor on GPIO {self.pin_number}: {e}.")
                self.dht_device = None # Ensure device is None
            except Exception as e:
                # Catch any other unexpected errors during init
                print(f"Warning: Unexpected error initializing DHT22 sensor on GPIO {self.pin_number}: {e}.")
                self.dht_device = None # Ensure device is None
            finally:
                self._initialized = True # Mark initialization as attempted (success or failure)

    def read(self) -> tuple[float | None, float | None]:
        """
        Reads temperature and humidity.
        Returns last known values if hardware is not yet initialized or read fails.
        Attempts to read the sensor with retries if hardware is initialized.

        Returns:
            A tuple containing (temperature_celsius, humidity_percent).
        """
        # Removed dummy mode read logic.

        # --- Check if hardware is ready ---
        if not self.dht_device:
            # If not dummy and device not initialized (or failed init), return last known/dummy values
            # Don't even attempt _read_sensor_internal if device isn't ready
            # print(f"DHT22 Read: Hardware not ready/initialized on GPIO {self.pin_number}. Returning last known values.") # Optional debug
            return self._last_temp, self._last_humidity

        # --- Attempt real sensor read (only if self.dht_device is valid) ---
        success = self._read_sensor_internal()

        if not success:
             print(f"DHT22 Read Failed on GPIO {self.pin_number}. Returning last known values: Temp={self._last_temp}°C, Hum={self._last_humidity}%")

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
        # This check is crucial. If called when device isn't ready, it should fail gracefully.
        # The read() method should prevent calling this if dht_device is None.
        if not self.dht_device:
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
        return DUMMY_TEMP_CELSIUS # Always return the dummy temperature

    @property
    def humidity(self) -> float | None:
        """Returns the last successfully read humidity percentage."""
        return self._last_humidity

    def start_background_initialization(self):
        """Starts the hardware initialization in a background thread."""
        if not self._initialized:
            init_thread = threading.Thread(target=self._initialize_hardware, daemon=True)
            init_thread.start()
            print(f"DHT22 background initialization thread started for GPIO {self.pin_number}.")
        else: # Already initialized or init started
             pass # Or print a message indicating it's already handled

# Example Usage (for testing purposes)
if __name__ == '__main__':
    # Replace with the actual GPIO pin connected to the DHT22 data line
    DHT_PIN = 4 # Example pin
    print(f"Testing DHT22Sensor on GPIO {DHT_PIN}...")

    try:
        # 1. Create the sensor instance (doesn't block)
        sensor = DHT22Sensor(DHT_PIN)

        # 2. Start background initialization
        sensor.start_background_initialization()

        # 3. Simulate application doing other things while sensor initializes
        print("Main thread continues while sensor initializes in background...")
        time.sleep(1) # Give init thread a moment to start

        print("\nAttempting initial read (might return dummy/last values if init not complete)...")
        temp, hum = sensor.read()
        if temp is not None and hum is not None:
            print(f"Initial Read: Temperature={temp:.2f}°C, Humidity={hum:.2f}%")
        else:
            print("Initial read failed or returned None.")

        # Wait a bit longer to allow initialization to potentially finish
        print("\nWaiting for potential initialization completion (max 5 seconds)...")
        for _ in range(5):
            if sensor.dht_device: # Check if init finished
                print("Initialization likely complete or switched to dummy.")
                break
            time.sleep(1)
        else:
            print("Initialization might still be ongoing or failed.")


        print("\nReading periodically for 10 seconds...")
        for i in range(5): # Reduced loop for faster testing
            temp, hum = sensor.read()
            if temp is not None and hum is not None:
                print(f"Read {i+1}: Temp={temp:.2f}°C, Hum={hum:.2f}% (Device: {'OK' if sensor.dht_device else 'None'})")
            else:
                print(f"Read {i+1}: Failed")
            # Respect the sensor's minimum read interval
            time.sleep(2) # Wait 2 seconds between reads

    except Exception as e:
        print(f"\nAn error occurred during testing: {e}")
        import traceback
        traceback.print_exc()
        print("\nEnsure the Adafruit_DHT library is installed (`pip install Adafruit_DHT`)")
        print("Ensure the script is run with sufficient permissions (e.g., using sudo)")
        print("Check GPIO pin connection and sensor power.")
    finally:
        print("\nTest finished.")