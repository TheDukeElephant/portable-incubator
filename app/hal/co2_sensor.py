import time
import random

# --- Configuration ---
# Set to True to force dummy mode even if a real sensor library was added later
FORCE_DUMMY_MODE = True
DUMMY_CO2_PPM = 450.0 # Standard atmospheric CO2 is around 400-450 ppm
DUMMY_VARIATION = 25.0 # Simulate some small fluctuations

class CO2Sensor:
    """
    Reads CO2 level (in ppm).
    Currently uses DUMMY values as the sensor is not connected.
    TODO: Replace with actual sensor integration (e.g., MH-Z19B, Senseair S8).
    """
    def __init__(self, i2c_bus=None, address=None, serial_port=None):
        """
        Initializes the CO2 sensor reader.
        Parameters are placeholders for future real sensor integration.
        """
        self.is_dummy = True
        self._last_co2 = DUMMY_CO2_PPM

        if FORCE_DUMMY_MODE:
            print("CO2Sensor initialized in FORCED DUMMY MODE.")
            return

        # --- Placeholder for real sensor initialization ---
        # try:
        #     # Example: Initialize a real sensor library here
        #     # self.sensor = RealCO2Library(port=serial_port)
        #     # self.is_dummy = False
        #     # print("Real CO2 Sensor Initialized.")
        #     # self._read_sensor() # Perform initial read
        #     raise NotImplementedError("Real CO2 sensor integration not yet implemented.")
        # except Exception as e:
        #     print(f"Warning: Failed to initialize real CO2 sensor ({e}). Falling back to DUMMY MODE.")
        #     self.is_dummy = True
        # --- End Placeholder ---

        if self.is_dummy:
             print("CO2Sensor initialized in DUMMY MODE.")


    def _read_sensor(self) -> float | None:
        """Internal method to read from the actual sensor."""
        # --- Placeholder for real sensor reading ---
        # if self.is_dummy or not hasattr(self, 'sensor'):
        #      raise RuntimeError("Cannot read from sensor in dummy mode or if not initialized.")
        # try:
        #     # co2_value = self.sensor.read_co2()
        #     # return float(co2_value)
        #     raise NotImplementedError("Real CO2 sensor reading not yet implemented.")
        # except Exception as e:
        #     print(f"Error reading real CO2 sensor: {e}")
        #     return None
        # --- End Placeholder ---
        # This part should ideally not be reached if the placeholder logic is active
        print("Warning: _read_sensor called unexpectedly in dummy setup.")
        return None


    def read(self) -> float | None:
        """
        Reads CO2 level in ppm. Returns dummy value if in dummy mode or read fails.
        """
        if self.is_dummy:
            # Simulate slight variation around the dummy value
            self._last_co2 = round(DUMMY_CO2_PPM + random.uniform(-DUMMY_VARIATION, DUMMY_VARIATION), 1)
            # print(f"CO2 Read (Dummy): {self._last_co2} ppm") # Optional debug print
            return self._last_co2
        else:
            # --- Placeholder for real sensor reading logic ---
            # value = self._read_sensor()
            # if value is not None:
            #     self._last_co2 = round(value, 1)
            #     return self._last_co2
            # else:
            #     # Return last known value on read failure, or None
            #     print("Warning: Failed to read real CO2 sensor, returning last known value.")
            #     return self._last_co2 # Or return None
            # --- End Placeholder ---
            print("Warning: Real CO2 sensor read attempted but not implemented.")
            return self._last_co2 # Return last known dummy value as fallback

    @property
    def co2(self) -> float | None:
        """Returns the last successfully read CO2 level in ppm."""
        # In this dummy implementation, 'read' updates _last_co2, so just return it.
        # For a real sensor, you might trigger a read here if data is stale,
        # similar to the DHT sensor, but CO2 sensors often have slower read rates.
        return self._last_co2

# Example Usage (for testing purposes)
if __name__ == '__main__':
    print("Testing CO2Sensor...")
    sensor = CO2Sensor()

    print(f"Initial Dummy Read: {sensor.read()} ppm")
    print("Reading periodically (dummy values)...")
    for i in range(5):
        time.sleep(1)
        print(f"Read {i+1}: {sensor.read()} ppm")

    print("\nTest finished.")