import asyncio
import time
from ..hal.dht_sensor import DHT22Sensor
from ..hal.relay_output import RelayOutput

class HumidityLoop:
    """
    Manages the humidity control loop using hysteresis (bang-bang with deadband).
    Reads humidity from a DHT22 sensor and controls a humidifier relay.
    """
    def __init__(self,
                 humidity_sensor: DHT22Sensor,
                 humidifier_relay: RelayOutput,
                 setpoint: float = 60.0, # Target humidity %
                 hysteresis: float = 2.0, # Control deadband (+/- from setpoint)
                 sample_time: float = 5.0 # Control loop interval in seconds
                ):
        """
        Initializes the humidity control loop.

        Args:
            humidity_sensor: Instance of DHT22Sensor.
            humidifier_relay: Instance of RelayOutput for the humidifier.
            setpoint: Initial target humidity percentage.
            hysteresis: The range around the setpoint for switching (e.g., 2.0 means
                        turn ON below setpoint - 1.0, turn OFF above setpoint + 1.0).
            sample_time: How often the control loop runs (seconds).
        """
        if hysteresis <= 0:
            raise ValueError("Hysteresis must be a positive value.")

        self.humidity_sensor = humidity_sensor
        self.humidifier_relay = humidifier_relay
        self._setpoint = setpoint
        self._hysteresis = hysteresis
        self._sample_time = sample_time

        # Calculate thresholds based on setpoint and hysteresis
        self._turn_on_threshold = self._setpoint - (self._hysteresis / 2.0)
        self._turn_off_threshold = self._setpoint + (self._hysteresis / 2.0)

        self._current_humidity: float | None = None
        self._humidifier_on: bool = False
        self._last_update_time: float = 0
        self._active = True # Flag to control the run loop

        # Attempt initial sensor read
        self._read_sensor()
        print(f"HumidityLoop initialized. Initial Hum: {self._current_humidity}%, Setpoint: {self._setpoint}%, Hyst: {self._hysteresis}%")
        print(f" -> ON Threshold: {self._turn_on_threshold}%, OFF Threshold: {self._turn_off_threshold}%")


    def _read_sensor(self):
        """Reads the sensor and updates the internal humidity state."""
        _, hum = self.humidity_sensor.read() # We only need humidity here
        if hum is not None:
            self._current_humidity = hum
        else:
            # Keep the last known humidity if read fails? Or set to None?
            print("Warning: Failed to read humidity sensor.")
            # self._current_humidity = None # Option 1: Indicate failure
            pass # Option 2: Keep last known value (use with caution)


    def _update_control(self):
        """Applies hysteresis logic and updates the humidifier relay state."""
        if self._current_humidity is None:
            # Safety measure: If we don't know the humidity, turn the humidifier off.
            print("Safety: Turning humidifier OFF due to unknown humidity.")
            if self._humidifier_on: # Only act if it was on
                 self.humidifier_relay.off()
                 self._humidifier_on = False
            return

        # Hysteresis Logic
        new_humidifier_state = self._humidifier_on # Assume no change initially

        if self._humidifier_on:
            # If currently ON, check if humidity has risen above the OFF threshold
            if self._current_humidity >= self._turn_off_threshold:
                new_humidifier_state = False
        else:
            # If currently OFF, check if humidity has fallen below the ON threshold
            if self._current_humidity <= self._turn_on_threshold:
                new_humidifier_state = True

        # Update relay only if state changes
        if new_humidifier_state != self._humidifier_on:
            if new_humidifier_state:
                self.humidifier_relay.on()
                print(f"Humidifier ON (Hum: {self._current_humidity:.2f}%, Setpoint: {self._setpoint:.1f}%, Threshold: <= {self._turn_on_threshold:.1f}%)")
            else:
                self.humidifier_relay.off()
                print(f"Humidifier OFF (Hum: {self._current_humidity:.2f}%, Setpoint: {self._setpoint:.1f}%, Threshold: >= {self._turn_off_threshold:.1f}%)")
            self._humidifier_on = new_humidifier_state

    async def run(self):
        """Runs the humidity control loop asynchronously."""
        print("Humidity control loop started.")
        while self._active:
            start_time = time.monotonic()

            self._read_sensor()
            self._update_control()

            self._last_update_time = time.monotonic()
            elapsed_time = self._last_update_time - start_time

            # Wait until the next sample time
            wait_time = max(0, self._sample_time - elapsed_time)
            await asyncio.sleep(wait_time)

        print("Humidity control loop stopped.")
        self.humidifier_relay.off() # Ensure humidifier is off when loop stops

    def stop(self):
        """Stops the control loop."""
        self._active = False

    def update_setpoint(self, new_setpoint: float):
        """Updates the target humidity and recalculates thresholds."""
        try:
            new_setpoint = float(new_setpoint)
            if 0 <= new_setpoint <= 100:
                self._setpoint = new_setpoint
                # Recalculate thresholds
                self._turn_on_threshold = self._setpoint - (self._hysteresis / 2.0)
                self._turn_off_threshold = self._setpoint + (self._hysteresis / 2.0)
                print(f"Humidity setpoint updated to: {self._setpoint}%. New thresholds: ON <= {self._turn_on_threshold:.1f}, OFF >= {self._turn_off_threshold:.1f}")
            else:
                print(f"Error: Invalid humidity setpoint value: {new_setpoint}. Must be between 0 and 100.")
        except ValueError:
            print(f"Error: Invalid humidity setpoint value: {new_setpoint}")

    @property
    def current_humidity(self) -> float | None:
        """Returns the last read humidity."""
        return self._current_humidity

    @property
    def setpoint(self) -> float:
        """Returns the current target humidity."""
        return self._setpoint

    @property
    def humidifier_is_on(self) -> bool:
        """Returns True if the humidifier relay is currently commanded ON."""
        return self._humidifier_on

    def close(self):
        """Stops the loop and releases resources."""
        print("Closing HumidityLoop resources...")
        self.stop()
        # Relay resources are closed by its own __del__ or explicit close if needed elsewhere

    def __del__(self):
        """Ensures the loop is stopped upon object deletion."""
        self.stop()

# Example Usage (Conceptual - requires running within an asyncio loop)
# async def main():
#     from ..hal.relay_output import RelayOutput
#     from ..hal.dht_sensor import DHT22Sensor
#     DHT_PIN = 4
#     HUMIDIFIER_PIN = 27
#
#     sensor = DHT22Sensor(DHT_PIN)
#     relay = RelayOutput(HUMIDIFIER_PIN)
#
#     loop = HumidityLoop(humidity_sensor=sensor, humidifier_relay=relay, setpoint=55.0, hysteresis=5.0, sample_time=3)
#
#     run_task = asyncio.create_task(loop.run())
#
#     # Simulate running for a while
#     await asyncio.sleep(15)
#     loop.update_setpoint(60.0)
#     await asyncio.sleep(15)
#
#     loop.stop()
#     await run_task # Wait for loop to finish cleanly
#     relay.close() # Explicitly close relay if needed
#
# if __name__ == '__main__':
#      asyncio.run(main())