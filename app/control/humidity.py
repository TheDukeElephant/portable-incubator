import asyncio
import time
from ..hal.dht_sensor import DHT22Sensor
from ..hal.relay_output import RelayOutput
from .base_loop import BaseLoop # Import BaseLoop
# Forward declaration for type hinting
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .manager import ControlManager

class HumidityLoop(BaseLoop): # Inherit from BaseLoop
    """
    Manages the humidity control loop using hysteresis (bang-bang with deadband).
    Reads humidity from a DHT22 sensor and controls a humidifier relay.
    """
    def __init__(self,
                 manager: 'ControlManager', # Add manager argument
                 humidity_sensor: DHT22Sensor,
                 humidifier_relay: RelayOutput,
                 enabled_attr: str, # Accept the enabled attribute name
                 setpoint: float = 60.0, # Target humidity %
                 hysteresis: float = 2.0, # Control deadband (+/- from setpoint)
                 sample_time: float = 5.0 # Control loop interval in seconds
                ):
        """
        Initializes the humidity control loop.

        Args:
            manager: The ControlManager instance.
            humidity_sensor: Instance of DHT22Sensor.
            humidifier_relay: Instance of RelayOutput for the humidifier.
            enabled_attr: The attribute name in the manager for the enabled state.
            setpoint: Initial target humidity percentage.
            hysteresis: The range around the setpoint for switching (e.g., 2.0 means
                        turn ON below setpoint - 1.0, turn OFF above setpoint + 1.0).
            sample_time: How often the control loop runs (seconds).
        """
        if hysteresis <= 0:
            raise ValueError("Hysteresis must be a positive value.")

        # Call BaseLoop constructor, passing the manager, interval, and enabled_attr
        super().__init__(manager=manager, control_interval=sample_time, enabled_attr=enabled_attr) # Pass the manager instance

        self.humidity_sensor = humidity_sensor
        self.humidifier_relay = humidifier_relay
        self._setpoint = setpoint
        self._hysteresis = hysteresis
        # self._sample_time = sample_time # Handled by BaseLoop

        # Calculate thresholds based on setpoint and hysteresis
        self._turn_on_threshold = self._setpoint - (self._hysteresis / 2.0)
        self._turn_off_threshold = self._setpoint + (self._hysteresis / 2.0)

        self._current_humidity: float | None = None
        self._humidifier_on: bool = False
        # self._last_update_time: float = 0 # Handled by BaseLoop timing
        # self._active = True # Replaced by BaseLoop._is_running and _stop_event

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
            # Indicate failure with "NC" (Not Connected)
            print("Warning: Failed to read humidity sensor. Setting humidity to 'NC'.")
            self._current_humidity = "NC"


    async def control_step(self):
        """Reads sensor, applies hysteresis logic, and updates the humidifier relay state."""
        print(f"DEBUG: Humidity control_step. is_active={self._active()}") # <-- Use print and call _active()
        self._read_sensor() # Read sensor first

        # 1. Check Sensor Status
        if self._current_humidity == "NC":
            print("Safety: Turning humidifier OFF due to sensor failure.")
            self._ensure_actuator_off() # Ensure humidifier is off
            return

        # --- Control logic proceeds only if BaseLoop determined the loop is active ---
        # This check is implicitly handled by the BaseLoop.run() method calling this function only when _active() is true.
        # However, we double-check sensor status above.

        # 2. Determine desired humidifier state based on Hysteresis
        should_be_on = self._humidifier_on # Assume no change initially
        if self._humidifier_on:
            # If currently ON, check if humidity has risen above the OFF threshold
            if self._current_humidity >= self._turn_off_threshold:
                should_be_on = False
        else:
            # If currently OFF, check if humidity has fallen below the ON threshold
            if self._current_humidity <= self._turn_on_threshold:
                should_be_on = True

        # 3. Update Relay only if state needs to change
        if should_be_on and not self._humidifier_on:
            self.humidifier_relay.on()
            self._humidifier_on = True
            print(f"Humidifier ON (Hum: {self._current_humidity:.2f}%, Setpoint: {self._setpoint:.1f}%, Threshold: <= {self._turn_on_threshold:.1f}%)")
        elif not should_be_on and self._humidifier_on:
            self.humidifier_relay.off()
            self._humidifier_on = False
            print(f"Humidifier OFF (Hum: {self._current_humidity:.2f}%, Setpoint: {self._setpoint:.1f}%, Threshold: >= {self._turn_off_threshold:.1f}%)")
        # else: No change needed

    def _ensure_actuator_off(self):
        """Turns the humidifier relay off."""
        print(f"DEBUG: Humidity _ensure_actuator_off called. Current humidifier state: {self._humidifier_on}") # <-- Use print
        if self.humidifier_relay and self._humidifier_on:
            print("Humidity loop inactive: Turning humidifier OFF.") # <-- Use print
            try:
                self.humidifier_relay.off()
                print("DEBUG: Hum humidifier_relay.off() called.") # <-- ADDED LOG
                self._humidifier_on = False
            except Exception as e:
                print(f"ERROR in Hum _ensure_actuator_off: {e}") # <-- ADDED ERROR LOG
        elif self.humidifier_relay:
             # Ensure it's off even if _humidifier_on was already False
             try:
                 self.humidifier_relay.off()
                 print("DEBUG: Hum _ensure_actuator_off ensuring relay is off.") # <-- ADDED LOG
             except Exception as e:
                 print(f"ERROR in Hum _ensure_actuator_off (ensuring off): {e}") # <-- ADDED ERROR LOG

    # Remove the custom run() method, BaseLoop provides it.
    # async def run(self): ...

    async def stop(self):
        """Stops the loop and ensures the humidifier is turned off."""
        # Call BaseLoop's stop first
        await super().stop()
        # Ensure humidifier is off as a final step
        if self.humidifier_relay and self._humidifier_on:
             print("HumidityLoop stopping: Turning humidifier OFF.")
             self.humidifier_relay.off()
             self._humidifier_on = False
        # No need to print "stopped" here, BaseLoop does it.

    # Change update_setpoint to a setter property
    @property
    def setpoint(self) -> float:
        """Returns the current target humidity."""
        return self._setpoint

    @setpoint.setter
    def setpoint(self, new_setpoint: float):
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

    # Keep humidifier_is_on property
    @property
    def humidifier_is_on(self) -> bool:
        """Returns True if the humidifier relay is currently commanded ON."""
        # The BaseLoop ensures this is only True when the loop is active and commanded ON.
        return self._humidifier_on

    def get_status(self) -> dict:
        """Returns the current status of the humidity loop."""
        return {
            "humidity": self.current_humidity,
            "setpoint": self.setpoint,
            "humidifier_on": self.humidifier_is_on, # Use property which checks incubator_running
            "hysteresis": self._hysteresis,
            "on_threshold": self._turn_on_threshold,
            "off_threshold": self._turn_off_threshold,
            "control_interval_s": self.control_interval
        }

    # Remove close() and __del__(), rely on manager calling stop() and closing relays
    # def close(self): ...
    # def __del__(self): ...

# Example Usage (Conceptual - requires running within an asyncio loop)
# async def main():
#     from ..hal.relay_output import RelayOutput
#     from ..hal.dht_sensor import DHT22Sensor
#     # Need a dummy manager for example
#     class DummyManager: incubator_running = True
#     manager = DummyManager()
#     DHT_PIN = 4
#     HUMIDIFIER_PIN = 27
#
#     sensor = DHT22Sensor(DHT_PIN)
#     relay = RelayOutput(HUMIDIFIER_PIN)
#
#     loop = HumidityLoop(manager=manager, humidity_sensor=sensor, humidifier_relay=relay, setpoint=55.0, hysteresis=5.0, sample_time=3)
#
#     run_task = asyncio.create_task(loop.run())
#
#     # Simulate running for a while
#     await asyncio.sleep(10)
#     loop.setpoint = 60.0
#     await asyncio.sleep(5)
#     print("Simulating incubator stop...")
#     manager.incubator_running = False # Stop the incubator
#     await asyncio.sleep(5) # See if humidifier turns off
#     print("Simulating incubator start...")
#     manager.incubator_running = True # Start again
#     await asyncio.sleep(5)
#
#     await loop.stop() # Stop the loop task itself
#     await run_task # Wait for loop to finish cleanly
#     relay.close() # Explicitly close relay if needed
#
# if __name__ == '__main__':
#      asyncio.run(main())