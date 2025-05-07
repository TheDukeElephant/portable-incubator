from typing import Optional
import asyncio
import time
from simple_pid import PID
# from ..hal.dht_sensor import DHT22Sensor # Replaced by MAX31865
from ..hal.max31865_sensor import MAX31865 # Import new sensor
from ..hal.relay_output import RelayOutput
from .base_loop import BaseLoop # Import BaseLoop
# Forward declaration for type hinting
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .manager import ControlManager

class TemperatureLoop(BaseLoop): # Inherit from BaseLoop
    """
    Manages the temperature control loop using a PID controller.
    Reads temperature from a MAX31865 sensor and controls a heater relay.
    """
    def __init__(self,
                 manager: 'ControlManager', # Add manager argument
                 temp_sensor: Optional[MAX31865], # Changed to MAX31865, can be None
                 heater_relay: RelayOutput,
                 enabled_attr: str, # Accept the enabled attribute name
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
            temp_sensor: Instance of MAX31865 sensor, or None if not available.
            heater_relay: Instance of RelayOutput for the heater.
            enabled_attr: The attribute name in the manager for the enabled state.
            p: Proportional gain for PID.
            i: Integral gain for PID.
            d: Derivative gain for PID.
            setpoint: Initial target temperature in Celsius.
            sample_time: How often the control loop runs (seconds).
            output_threshold: The PID output value above which the heater turns on.
        """
        # Call BaseLoop constructor, passing the manager, interval, and enabled_attr
        super().__init__(manager=manager, control_interval=sample_time, enabled_attr=enabled_attr)

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
        if self.temp_sensor is None:
            print("Warning: TemperatureLoop initialized without a temperature sensor. Temperature control will be disabled.")
            self._logger.warning("TemperatureLoop initialized without a temperature sensor. Heater will be kept off.") # Use logger
            self._current_temperature = None # Ensure it's None if no sensor
        else:
            self._read_sensor() # Read only if sensor exists
        print(f"TemperatureLoop initialized. Initial Temp: {self._current_temperature}°C, Setpoint: {self.pid.setpoint}°C")

    def _read_sensor(self):
        """Reads the MAX31865 sensor and updates the internal temperature state."""
        if self.temp_sensor is None:
            self._current_temperature = None
            # Optional: Log this periodically if needed, but initial warning in __init__ might be enough
            # print("Warning: Attempted to read temperature, but no sensor is available.")
            return # Exit early if no sensor

        # import random # No longer needed
        # temp, _ = self.temp_sensor.read() # Old DHT22 call
        temp = self.temp_sensor.read_temperature() # New MAX31865 call

        if temp is not None:
            self._current_temperature = temp
            # print(f"DEBUG: Temperature read: {self._current_temperature}°C") # Optional debug
        else:
            # Setting to None is important for safety logic in control_step
            self._current_temperature = None
            print("Warning: Failed to read temperature from MAX31865 sensor.") # Sensor exists but read failed
            # No longer keeping last known value, None indicates an issue.

    # def _update_control(self): # <-- REMOVE this method, logic moved to control_step
    #     """Calculates PID output and updates the heater relay state."""
    #     pass # Keep method signature for diff tool if needed, but logic is gone

    def _ensure_actuator_off(self):
        """Turns the heater relay off and resets the PID."""
        print(f"DEBUG: Temperature _ensure_actuator_off called. Current heater state: {self._heater_on}") # <-- Use print
        if self.heater_relay and self._heater_on:
            print("Temperature loop inactive: Turning heater OFF and resetting PID.") # <-- Use print
            try:
                self.heater_relay.off()
                print("DEBUG: Temp heater_relay.off() called.") # <-- ADDED LOG
                self._heater_on = False
                self.pid.reset() # Reset PID when loop becomes inactive
            except Exception as e:
                print(f"ERROR in Temp _ensure_actuator_off: {e}") # <-- ADDED ERROR LOG
        elif self.heater_relay:
             # Ensure it's off even if _heater_on was already False
             try:
                 self.heater_relay.off()
                 print("DEBUG: Temp _ensure_actuator_off ensuring relay is off.") # <-- ADDED LOG
             except Exception as e:
                 print(f"ERROR in Temp _ensure_actuator_off (ensuring off): {e}") # <-- ADDED ERROR LOG

    async def control_step(self):
        """Performs a single temperature control step based on sensor reading and PID."""
        print(f"DEBUG: Temperature control_step. is_active={self._active()}") # <-- Use print and call _active()
        self._read_sensor()

        # 1. Check Sensor Status
        if self._current_temperature is None:
            print("Safety: Turning heater OFF due to unknown temperature.")
            self._ensure_actuator_off() # Ensure heater is off and PID reset
            return

        # 2. Calculate PID Output (only if sensor is OK)
        pid_output = self.pid(self._current_temperature)

        # 3. Determine desired heater state
        should_be_on = pid_output > self._output_threshold

        # 4. Update Relay only if state needs to change
        if should_be_on and not self._heater_on:
            self.heater_relay.on()
            self._heater_on = True
            print(f"Heater ON (Temp: {self._current_temperature:.2f}°C, Setpoint: {self.pid.setpoint:.2f}°C, PID: {pid_output:.2f})")
        elif not should_be_on and self._heater_on:
            self.heater_relay.off()
            self._heater_on = False
            print(f"Heater OFF (Temp: {self._current_temperature:.2f}°C, Setpoint: {self.pid.setpoint:.2f}°C, PID: {pid_output:.2f})")
        # else: No change needed

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
        # The BaseLoop ensures this is only True when the loop is active and commanded ON.
        return self._heater_on

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

# Example Usage (Conceptual - requires running within an asyncio loop and MAX31865 setup)
# async def main():
#     import board # Required for MAX31865
#     from ..hal.relay_output import RelayOutput
#     # from ..hal.dht_sensor import DHT22Sensor # Old sensor
#     from ..hal.max31865_sensor import MAX31865 # New sensor
#
#     # Need a dummy manager for example
#     class DummyManager:
#         def __init__(self):
#             self.temperature_control_enabled = True # Example attribute
#     manager = DummyManager()
#
#     HEATER_PIN = 17 # Example GPIO pin for heater
#
#     # Initialize MAX31865 sensor
#     # Ensure SPI is enabled: sudo raspi-config
#     # Connections: SCLK=GPIO11, MOSI=GPIO10, MISO=GPIO9, CS=GPIO8
#     try:
#         max_sensor = MAX31865(cs_pin=board.D8) # GPIO8 is board.D8
#         if max_sensor.sensor is None:
#             print("Failed to initialize MAX31865, exiting example.")
#             return
#     except Exception as e:
#         print(f"Error initializing MAX31865: {e}")
#         return
#
#     heater_relay = RelayOutput(HEATER_PIN)
#
#     # Note: 'enabled_attr' should match an attribute in DummyManager
#     temp_loop = TemperatureLoop(manager=manager,
#                                 temp_sensor=max_sensor,
#                                 heater_relay=heater_relay,
#                                 enabled_attr='temperature_control_enabled', # Matches DummyManager
#                                 setpoint=30.0,
#                                 sample_time=2)
#
#     print("Starting TemperatureLoop example...")
#     run_task = asyncio.create_task(temp_loop.run())
#
#     # Simulate running for a while
#     try:
#         await asyncio.sleep(10)
#         print("Updating setpoint to 32.0°C")
#         temp_loop.setpoint = 32.0
#         await asyncio.sleep(10)
#
#         print("Simulating disabling temperature control...")
#         manager.temperature_control_enabled = False
#         await asyncio.sleep(5) # Give time for loop to react
#         print(f"Heater on after disable: {temp_loop.heater_is_on}")
#
#         print("Simulating enabling temperature control...")
#         manager.temperature_control_enabled = True
#         await asyncio.sleep(10) # Give time for loop to react
#         print(f"Heater on after re-enable: {temp_loop.heater_is_on}")
#
#     except KeyboardInterrupt:
#         print("Keyboard interrupt received.")
#     finally:
#         print("Stopping TemperatureLoop example...")
#         await temp_loop.stop() # Stop the loop task itself
#         await run_task # Wait for loop to finish cleanly
#         heater_relay.close() # Explicitly close relay
#         print("TemperatureLoop example finished.")
#
# if __name__ == '__main__':
#      # This example requires actual hardware or a well-mocked environment
#      # For testing, you might mock board, busio, digitalio, adafruit_max31865
#      # print("To run this example, ensure SPI is configured and a MAX31865 is connected.")
#      # print("Or, mock the hardware components for software testing.")
#      # asyncio.run(main())
#      pass # Commenting out direct run for now as it requires hardware