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
                 sensor: CO2Sensor,
                 vent_relay_pin: int,
                 setpoint: float = DEFAULT_CO2_SETPOINT_PPM):
        super().__init__(manager=manager, control_interval=CONTROL_INTERVAL_SECONDS) # Pass manager
        self.sensor = sensor
        self._setpoint = setpoint
        self.vent_relay_pin = vent_relay_pin
        self.current_co2 = None
        self.vent_active = False
        self._vent_start_time = None

        # Initialize the vent relay using the provided pin
        try:
            self.vent_relay = RelayOutput(self.vent_relay_pin, initial_state=False) # Start with vent OFF
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
            print(f"CO2Loop Setpoint updated: < {self._setpoint} ppm")
        else:
            print(f"Warning: Invalid CO2 setpoint ignored: {value}")

    async def control_step(self):
        """Performs a single control step for CO2 management."""
        # 1. Read Sensor
        self.current_co2 = self.sensor.read() # Uses dummy value for now

        if self.current_co2 is None:
            print("Warning: Failed to read CO2 sensor.")
            # Safety: Turn off vent if sensor fails? Or maintain last state?
            # For now, let's turn it off if the reading fails.
            if self.vent_relay and self.vent_active:
                print("Safety: Turning vent OFF due to failed CO2 reading.")
                self.vent_relay.off()
                self.vent_active = False
                self._vent_start_time = None
            return # Skip control logic if sensor read failed

        # --- Check if incubator is running ---
        if not self.manager.incubator_running:
            # If stopped, ensure vent is off and skip logic
            if self.vent_relay and self.vent_active:
                self.vent_relay.off()
                self.vent_active = False
                self._vent_start_time = None
                print("Incubator stopped: Turning vent OFF.")
            return
        # --- Incubator is running, proceed with control ---

        # 2. Control Logic (Simple Threshold)
        # TODO: Add hysteresis or more advanced control if needed
        if self.vent_relay:
            if self.current_co2 > self._setpoint:
                if not self.vent_active:
                    print(f"CO2 High ({self.current_co2} ppm > {self._setpoint} ppm). Activating vent.")
                    self.vent_relay.on()
                    self.vent_active = True
                    self._vent_start_time = time.monotonic()
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
             if self.current_co2 > self._setpoint:
                 if not self.vent_active:
                     print(f"CO2 High ({self.current_co2} ppm > {self._setpoint} ppm). (Simulating vent ON)")
                     self.vent_active = True
             elif self.vent_active:
                 print(f"CO2 OK ({self.current_co2} ppm <= {self._setpoint} ppm). (Simulating vent OFF)")
                 self.vent_active = False

        # print(f"CO2 Loop: Current={self.current_co2} ppm, Setpoint=<{self._setpoint} ppm, Vent Active={self.vent_active}") # Debug print

    def get_status(self) -> dict:
        """Returns the current status of the CO2 loop."""
        return {
            "co2_ppm": self.current_co2,
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

    # Add property for vent status that considers incubator state
    @property
    def is_vent_active(self) -> bool:
        """Returns True if the vent relay is currently commanded ON and incubator is running."""
        return self.vent_active and self.manager.incubator_running