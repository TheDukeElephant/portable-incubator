from typing import Optional
import asyncio
import time
from simple_pid import PID
# from ..hal.dht_sensor import DHT22Sensor # Replaced by MAX31865
from ..hal.max31865_sensor import MAX31865_Hub # Import MAX31865_Hub
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
                 temp_sensor: Optional[MAX31865_Hub], # Changed to MAX31865_Hub, can be None
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
            temp_sensor: Instance of MAX31865_Hub, or None if not available.
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

        self._current_temperature: dict[str, float | None] | None = None # Store as dict {"sensor1": temp, "sensor2": temp}
        self._heater_on: bool = False
        # self._last_update_time: float = 0 # Handled by BaseLoop timing
        # self._active = True # Replaced by BaseLoop._is_running and _stop_event

        # Attempt initial sensor read
        if self.temp_sensor is None:
            print("Warning: TemperatureLoop initialized without a temperature sensor. Temperature control will be disabled.")
            self._logger.warning("TemperatureLoop initialized without a temperature sensor hub. Heater will be kept off.") # Use logger
            self._current_temperature = None # Ensure it's None if no sensor
        else:
            self._read_sensor() # Read only if sensor exists
        print(f"TemperatureLoop initialized. Initial Temps: {self._current_temperature}, Setpoint: {self.pid.setpoint}°C")

    def _read_sensor(self):
        """Reads the MAX31865_Hub and updates the internal temperature state."""
        if self.temp_sensor is None:
            self._current_temperature = None
            # Optional: Log this periodically if needed, but initial warning in __init__ might be enough
            # print("Warning: Attempted to read temperature, but no sensor hub is available.")
            return # Exit early if no sensor

        temps = self.temp_sensor.read_all_temperatures() # Returns {"sensor1": float|None, "sensor2": float|None}

        if temps["sensor1"] is None and temps["sensor2"] is None:
            self._logger.warning("Failed to read temperature from both MAX31865 sensors.")
            self._current_temperature = None # Indicate a complete failure
        elif temps["sensor1"] is None:
            self._logger.warning("Failed to read temperature from MAX31865 sensor 1.")
            self._current_temperature = {"sensor1": None, "sensor2": temps["sensor2"]}
        elif temps["sensor2"] is None:
            self._logger.warning("Failed to read temperature from MAX31865 sensor 2.")
            self._current_temperature = {"sensor1": temps["sensor1"], "sensor2": None}
        else:
            self._current_temperature = temps
            # print(f"DEBUG: Temperatures read: {self._current_temperature}") # Optional debug

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

        # 1. Check Sensor Status and determine control temperature
        control_temp = None
        if self._current_temperature is None: # Both sensors failed or hub not present
            print("Safety: Turning heater OFF due to no valid temperature readings from hub.")
            self._ensure_actuator_off() # Ensure heater is off and PID reset
            return
        elif self._current_temperature["sensor1"] is not None and self._current_temperature["sensor2"] is not None:
            control_temp = (self._current_temperature["sensor1"] + self._current_temperature["sensor2"]) / 2
            print(f"DEBUG: Using average temp for control: {control_temp:.2f}°C (S1: {self._current_temperature['sensor1']:.2f}, S2: {self._current_temperature['sensor2']:.2f})")
        elif self._current_temperature["sensor1"] is not None:
            control_temp = self._current_temperature["sensor1"]
            print(f"DEBUG: Using Sensor 1 temp for control: {control_temp:.2f}°C (Sensor 2 failed)")
        elif self._current_temperature["sensor2"] is not None:
            control_temp = self._current_temperature["sensor2"]
            print(f"DEBUG: Using Sensor 2 temp for control: {control_temp:.2f}°C (Sensor 1 failed)")
        else: # Should be caught by the first 'is None' check, but as a safeguard
            print("Safety: Turning heater OFF due to no valid temperature readings (internal logic error).")
            self._ensure_actuator_off()
            return

        # 2. Calculate PID Output (only if sensor is OK)
        pid_output = self.pid(control_temp)

        # 3. Determine desired heater state
        should_be_on = pid_output > self._output_threshold

        # 4. Update Relay only if state needs to change
        if should_be_on and not self._heater_on:
            self.heater_relay.on()
            self._heater_on = True
            print(f"Heater ON (Control Temp: {control_temp:.2f}°C, Setpoint: {self.pid.setpoint:.2f}°C, PID: {pid_output:.2f})")
        elif not should_be_on and self._heater_on:
            self.heater_relay.off()
            self._heater_on = False
            print(f"Heater OFF (Control Temp: {control_temp:.2f}°C, Setpoint: {self.pid.setpoint:.2f}°C, PID: {pid_output:.2f})")
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
    def current_temperature(self) -> dict[str, float | None] | None:
        """Returns the last read temperatures as a dictionary {'sensor1': temp1, 'sensor2': temp2} or None."""
        return self._current_temperature

    # Keep heater_is_on property
    @property
    def heater_is_on(self) -> bool:
        """Returns True if the heater relay is currently commanded ON."""
        # The BaseLoop ensures this is only True when the loop is active and commanded ON.
        return self._heater_on

    def get_status(self) -> dict:
        """Returns the current status of the temperature loop."""
        temp_s1_display = "NC"
        temp_s2_display = "NC"
        avg_temp_display = "NC"

        if self.current_temperature is not None:
            if self.current_temperature.get("sensor1") is not None:
                temp_s1_display = f"{self.current_temperature['sensor1']:.2f}"
            if self.current_temperature.get("sensor2") is not None:
                temp_s2_display = f"{self.current_temperature['sensor2']:.2f}"

            s1_val = self.current_temperature.get("sensor1")
            s2_val = self.current_temperature.get("sensor2")

            if s1_val is not None and s2_val is not None:
                avg_temp_display = f"{(s1_val + s2_val) / 2:.2f}"
            elif s1_val is not None:
                avg_temp_display = f"{s1_val:.2f} (S1 only)"
            elif s2_val is not None:
                avg_temp_display = f"{s2_val:.2f} (S2 only)"

        return {
            "temperature_sensor1": temp_s1_display,
            "temperature_sensor2": temp_s2_display,
            "temperature_average_control": avg_temp_display, # Reflects what PID might use
            "setpoint": self.setpoint,
            "heater_on": self.heater_is_on,
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