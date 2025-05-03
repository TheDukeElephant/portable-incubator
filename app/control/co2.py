import asyncio
import time
from .base_loop import BaseLoop # Corrected import
from ..hal.co2_sensor import CO2Sensor
from ..hal.relay_output import RelayOutput
# Forward declaration for type hinting
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .manager import ControlManager

# --- Configuration ---
DEFAULT_CO2_SETPOINT_PPM = 1000.0 # Target maximum CO2 level in ppm
CONTROL_INTERVAL_SECONDS = 15     # How often to check CO2 level
# VENT_RELAY_PIN = 24            # GPIO pin will now be passed in __init__
MIN_VENT_DURATION_SECONDS = 5     # Minimum time to keep vent open
MAX_VENT_DURATION_SECONDS = 60    # Maximum time to keep vent open in one go
class CO2Loop(BaseLoop):
    """
    Control loop for managing Carbon Dioxide (CO2) levels.
    Currently operates based on a simple threshold: vent if CO2 exceeds setpoint.
    Uses a dummy sensor and placeholder relay pin.
    TODO: Implement real sensor reading and relay control.
    """
    def __init__(self,
                 manager: 'ControlManager', # Add manager argument
                 co2_sensor_port: str, # Accept sensor port path
                 vent_relay_pin: int,
                 enabled_attr: str, # Accept the enabled attribute name
                 setpoint: float = DEFAULT_CO2_SETPOINT_PPM):
        """
        Initializes the CO2 control loop.

        Args:
            manager: The ControlManager instance.
            co2_sensor_port: The serial port device path for the CO2 sensor (e.g., '/dev/ttyS0').
            vent_relay_pin: The GPIO pin number for the vent relay.
            enabled_attr: The attribute name in the manager for the enabled state.
            setpoint: Initial target maximum CO2 level in ppm.
        """
        super().__init__(manager=manager, control_interval=CONTROL_INTERVAL_SECONDS, enabled_attr=enabled_attr) # Pass manager and enabled_attr
        # Instantiate the sensor here using the provided port
        self.sensor = CO2Sensor(url=co2_sensor_port)
        self._setpoint = setpoint
        self.vent_relay_pin = vent_relay_pin
        self.current_co2 = None # Initialize as None
        self.vent_active = False
        self._vent_start_time = None

        # Initialize the vent relay using the provided pin
        try:
            self.vent_relay = RelayOutput(self.vent_relay_pin, initial_value=False) # Start with vent OFF
            print(f"CO2Loop initialized. Vent Relay on GPIO {self.vent_relay_pin}. Setpoint: < {self._setpoint} ppm")
        except Exception as e:
            # Handle cases where GPIO might not be available (e.g., testing off-Pi)
            print(f"Warning: Could not initialize vent relay on GPIO {self.vent_relay_pin}: {e}. CO2 control will be simulated.")
            self.vent_relay = None # Indicate relay is not available

    @property
    def setpoint(self) -> float:
        return self._setpoint

    @setpoint.setter
    def setpoint(self, value: float):
        if value > 0: # Basic validation
            self._setpoint = value
            print(f"[DEBUG] CO2Loop Setpoint updated to: {self._setpoint} ppm")
        else:
            print(f"Warning: Invalid CO2 setpoint ignored: {value}")

    async def control_step(self):
        """Performs a single control step for CO2 management."""
        # 1. Read Sensor (using new async method)
        reading_successful = False
        last_activation_time = getattr(self, "_last_activation_time", None)
        current_time = time.monotonic()
        try:
            self.current_co2 = await self.sensor.read_ppm()
            # Check if the sensor itself returned an invalid reading indicator (e.g., None or specific error value)
            if self.current_co2 is None:
                 print("Warning: CO2 sensor returned None (disconnected or invalid reading).")
                 # Keep self.current_co2 as None
            elif not isinstance(self.current_co2, (int, float)):
                 print(f"Warning: CO2 sensor returned unexpected type: {type(self.current_co2)}. Treating as invalid.")
                 self.current_co2 = None # Treat unexpected types as invalid
            else:
                 reading_successful = True # Mark as successful only if we got a valid number
            # Optional: Add a debug log here if needed
            # print(f"CO2 Read: {self.current_co2} ppm")
        except (RuntimeError, asyncio.TimeoutError, ValueError) as e:
            print(f"Warning: Failed to read CO2 sensor (exception): {e}") # Log the specific error
            self.current_co2 = None # Ensure current_co2 is None on failure
        except Exception as e: # Catch any other unexpected errors
            print(f"Error: Unexpected error reading CO2 sensor: {e}")
            self.current_co2 = None

        # --- Safety Check & Early Exit on Read Failure ---
        if not reading_successful:
            # If reading failed (exception or sensor returned None/invalid), turn off vent
            if self.vent_relay and self.vent_active:
                print("Safety: Turning vent OFF due to failed/invalid CO2 reading.")
                self.vent_relay.off()
                self.vent_active = False
                self._vent_start_time = None
            return # Skip control logic if sensor read failed or was invalid

        # --- Control logic proceeds only if BaseLoop determined the loop is active ---

        # 2. Control Logic (Simple Threshold)
        # This part is only reached if reading_successful is True and the loop is active
        # TODO: Add hysteresis or more advanced control if needed
        if self.vent_relay:
            # We know self.current_co2 is a valid number here
            if self.current_co2 > self._setpoint:
                if not self.vent_active and (last_activation_time is None or current_time - last_activation_time >= 60):
                    print(f"CO2 High ({self.current_co2} ppm > {self._setpoint} ppm). Activating vent for 0.1 seconds.")
                    self.vent_relay.on()
                    await asyncio.sleep(0.1)
                    self.vent_relay.off()
                    self._last_activation_time = current_time
                else:
                    # Check if vent has been open too long (prevent continuous venting)
                    if self._vent_start_time and (time.monotonic() - self._vent_start_time > MAX_VENT_DURATION_SECONDS):
                         print(f"CO2 Vent MAX DURATION ({MAX_VENT_DURATION_SECONDS}s) reached. Temporarily closing vent.")
                         self.vent_relay.off()
                         # We might want a cooldown period here before allowing vent again
                         # For simplicity now, just closing it allows the next check to potentially reopen if still high
                         self.vent_active = False # Mark as inactive so next check re-evaluates
                         self._vent_start_time = None

            elif self.vent_active: # CO2 is below setpoint, and vent is currently active
                 # Check minimum vent duration
                 if self._vent_start_time and (time.monotonic() - self._vent_start_time >= MIN_VENT_DURATION_SECONDS):
                     print(f"CO2 OK ({self.current_co2} ppm <= {self._setpoint} ppm). Deactivating vent.")
                     self.vent_relay.off()
                     self.vent_active = False
                     self._vent_start_time = None
                 # else: Vent is on, but hasn't met minimum duration yet, keep it on.

        else: # Simulation if relay not initialized
             # We know self.current_co2 is a valid number here
             if self.current_co2 > self._setpoint:
                 if not self.vent_active:
                     print(f"CO2 High ({self.current_co2} ppm > {self._setpoint} ppm). (Simulating vent ON)")
                     self.vent_active = True
             elif self.vent_active:
                 print(f"CO2 OK ({self.current_co2} ppm <= {self._setpoint} ppm). (Simulating vent OFF)")
                 self.vent_active = False

        # print(f"CO2 Loop: Current={self.current_co2} ppm, Setpoint=<{self._setpoint} ppm, Vent Active={self.is_vent_active}") # Debug print

    def _ensure_actuator_off(self):
        """Turns the vent relay off and resets vent state."""
        if self.vent_relay and self.vent_active:
            print("CO2 loop inactive: Turning vent OFF.")
            self.vent_relay.off()
        self.vent_active = False
        self._vent_start_time = None

    def get_status(self) -> dict:
        """Returns the current status of the CO2 loop."""
        return {
            "co2_ppm": self.current_co2, # Will be None if reading failed/invalid
            "setpoint_ppm": self._setpoint,
            # Use property which checks incubator_running
            "vent_active": self.is_vent_active,
            "control_interval_s": self.control_interval
        }

    async def stop(self):
        """Stops the loop and ensures the vent is turned off."""
        await super().stop()
        if self.vent_relay and self.vent_active:
            print("CO2Loop stopping: Turning vent OFF.")
            self.vent_relay.off()
            self.vent_active = False
        # No need to print stopped message, BaseLoop handles it.

    def reset_control(self):
        """Resets the vent state, ensuring it's off."""
        print("CO2Loop: Resetting control state (forcing vent OFF).")
        if self.vent_relay and self.vent_active:
            self.vent_relay.off()
        self.vent_active = False
        self._vent_start_time = None

    # Add property for vent status that considers incubator state
    @property
    def is_vent_active(self) -> bool:
        """Returns True if the vent relay is currently commanded ON, incubator is running, and CO2 control is enabled."""
        # The BaseLoop ensures this is only True when the loop is active and commanded ON.
        return self.vent_active