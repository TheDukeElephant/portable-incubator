import asyncio
import time
from simple_pid import PID
from ..hal.dht_sensor import DHT22Sensor
from ..hal.relay_output import RelayOutput
from .base_loop import BaseLoop # Import BaseLoop
# Forward declaration for type hinting
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .manager import ControlManager

class TemperatureLoop(BaseLoop): # Inherit from BaseLoop
    """
    Manages the temperature control loop using a PID controller.
    Reads temperature from a DHT22 sensor and controls a heater relay.
    """
    def __init__(self,
                 manager: 'ControlManager', # Add manager argument
                 temp_sensor: DHT22Sensor,
                 heater_relay: RelayOutput,
                 p: float = 5.0,
                 i: float = 0.1,
                 d: float = 1.0,
                 setpoint: float = 37.0,
                 sample_time: float = 5.0, # Control loop interval in seconds
                 output_threshold: float = 0 # PID output > threshold turns heater ON
                ):
        """
        Initializes the temperature control loop.

        Args:
            manager: The ControlManager instance.
            temp_sensor: Instance of DHT22Sensor.
            heater_relay: Instance of RelayOutput for the heater.
            p: Proportional gain for PID.
            i: Integral gain for PID.
            d: Derivative gain for PID.
            setpoint: Initial target temperature in Celsius.
            sample_time: How often the control loop runs (seconds).
            output_threshold: The PID output value above which the heater turns on.
        """
        # Call BaseLoop constructor, passing the manager and interval
        super().__init__(manager=manager, control_interval=sample_time, enabled_attr="temperature_enabled")

        self.temp_sensor = temp_sensor
        self.heater_relay = heater_relay
        self._output_threshold = output_threshold

        # Configure PID controller
        # Output limits can represent % duty cycle or just directionality
        # For simple on/off, limits aren't strictly necessary but can be good practice.
        self.pid = PID(p, i, d, setpoint=setpoint, sample_time=sample_time, output_limits=(-100, 100))

        self._current_temperature: float | None = None
        self._heater_on: bool = False
        # self._last_update_time: float = 0 # Handled by BaseLoop timing
        # self._active = True # Replaced by BaseLoop._is_running and _stop_event

        # Attempt initial sensor read
        self._read_sensor()
        print(f"TemperatureLoop initialized. Initial Temp: {self._current_temperature}°C, Setpoint: {self.pid.setpoint}°C")

    def _read_sensor(self):
        """Reads the sensor and updates the internal temperature state."""
        import random
        temp, _ = self.temp_sensor.read() # We only need temperature here
        if temp is not None:
            # Add a small random fluctuation to the temperature
            self._current_temperature = temp + random.uniform(-0.5, 0.5)
        else:
            # Keep the last known temperature if read fails? Or set to None?
            # Setting to None might be safer to prevent PID windup on stale data.
            # self._current_temperature = None # Option 1: Indicate failure clearly
            print("Warning: Failed to read temperature sensor.")
            # Option 2: Keep last known value (use with caution)
            # print(f"Warning: Failed to read temperature sensor. Using last known value: {self._current_temperature}")
            pass # Keep last known value for now

    def _update_control(self):
        """Calculates PID output and updates the heater relay state."""
        if self._current_temperature is None:
            # Safety measure: If we don't know the temperature, turn the heater off.
            print("Safety: Turning heater OFF due to unknown temperature.")
            if self._heater_on:  # Check if it was on
                self.heater_relay.off()
                self._heater_on = False
            # Reset PID to prevent windup when sensor recovers
            self.pid.reset()
            return

        # --- Check if incubator is running AND this specific loop is enabled ---
        if not self.manager.incubator_running or not self.manager.temperature_enabled:
            # If stopped or disabled, ensure heater is off and skip PID calculation
            if self._heater_on:
                self.heater_relay.off()
                self._heater_on = False
                if not self.manager.incubator_running:
                    print("Incubator stopped: Turning heater OFF.")
                else: # Must be disabled
                    print("Temperature control disabled: Turning heater OFF.")
            # Reset PID to prevent windup while stopped/disabled
            self.pid.reset()
            return

        # --- Incubator is running and Temperature control is enabled, proceed ---
        # Calculate PID output
        pid_output = self.pid(self._current_temperature)

        # Determine heater state based on PID output and threshold
        new_heater_state = pid_output > self._output_threshold

        if new_heater_state != self._heater_on:
            if new_heater_state:
                self.heater_relay.on()
                print(f"Heater ON (Temp: {self._current_temperature:.2f}°C, Setpoint: {self.pid.setpoint:.2f}°C, PID: {pid_output:.2f})")
            else:
                self.heater_relay.off()
                print(f"Heater OFF (Temp: {self._current_temperature:.2f}°C, Setpoint: {self.pid.setpoint:.2f}°C, PID: {pid_output:.2f})")
            self._heater_on = new_heater_state
        # else: No change in heater state

    async def control_step(self):
        """Performs a single temperature control step."""
        self._read_sensor()
        self._update_control()

    # Remove the custom run() method, BaseLoop provides it.
    # async def run(self): ...

    async def stop(self):
        """Stops the loop and ensures the heater is turned off."""
        # Call BaseLoop's stop first
        await super().stop()
        # Ensure heater is off as a final step when the loop itself is stopped
        if self.heater_relay and self._heater_on:
             print("TemperatureLoop stopping: Turning heater OFF.")
             self.heater_relay.off()
             self._heater_on = False
        # No need to print "stopped" here, BaseLoop does it.

    # Rename update_setpoint to match setter pattern if desired, or keep as is
    # Using a setter property might be more consistent with other loops
    @property
    def setpoint(self) -> float:
        """Returns the current target temperature."""
        return self.pid.setpoint

    @setpoint.setter
    def setpoint(self, new_setpoint: float):
        """Updates the target temperature."""
        try:
            self.pid.setpoint = float(new_setpoint)
            print(f"Temperature setpoint updated to: {self.pid.setpoint}°C")
        except ValueError:
            print(f"Error: Invalid temperature setpoint value: {new_setpoint}")

    # Keep current_temperature property
    @property
    def current_temperature(self) -> float | None:
        """Returns the last read temperature."""
        return self._current_temperature

    # Keep heater_is_on property
    @property
    def heater_is_on(self) -> bool:
        """Returns True if the heater relay is currently commanded ON."""
        # Reflect the actual state based on incubator running AND enabled status
        return self._heater_on and self.manager.incubator_running and self.manager.temperature_enabled

    def get_status(self) -> dict:
        """Returns the current status of the temperature loop."""
        return {
            "temperature": self.current_temperature,
            "setpoint": self.setpoint,
            "heater_on": self.heater_is_on, # Use property which checks incubator_running
            "pid_p": self.pid.Kp,
            "pid_i": self.pid.Ki,
            "pid_d": self.pid.Kd,
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
#     HEATER_PIN = 17
#
#     sensor = DHT22Sensor(DHT_PIN)
#     relay = RelayOutput(HEATER_PIN)
#
#     loop = TemperatureLoop(manager=manager, temp_sensor=sensor, heater_relay=relay, setpoint=30.0, sample_time=2)
#
#     run_task = asyncio.create_task(loop.run())
#
#     # Simulate running for a while
#     await asyncio.sleep(10)
#     loop.setpoint = 32.0
#     await asyncio.sleep(5)
#     print("Simulating incubator stop...")
#     manager.incubator_running = False # Stop the incubator
#     await asyncio.sleep(5) # See if heater turns off
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