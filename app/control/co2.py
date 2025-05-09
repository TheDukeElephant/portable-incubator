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
CONTROL_INTERVAL_SECONDS = 1.0    # How often to check CO2 level (Changed from 30)
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
                 co2_sensor_port: str = "/dev/ttyS0", # Accept sensor port path
                 vent_relay_pin: int = 0,
                 enabled_attr: str = "", # Accept the enabled attribute name
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
        # Use the unfiltered 'z' command to read above 20k ppm
        self.sensor = CO2Sensor(url=co2_sensor_port, use_unfiltered_cmd=True)
        self._setpoint = setpoint
        self.vent_relay_pin = vent_relay_pin
        self.current_co2 = None # Initialize as None
        self.vent_active = False
        self._vent_start_time = None

        # Initialize the vent relay using the provided pin
        try:
            self.vent_relay = RelayOutput(self.vent_relay_pin, initial_value=False) # Start with vent OFF
            print(f"CO2Loop initialized. Vent Relay (Primary CO2) on GPIO {self.vent_relay_pin}. Setpoint: < {self._setpoint} ppm")
        except Exception as e:
            # Handle cases where GPIO might not be available (e.g., testing off-Pi)
            print(f"Warning: Could not initialize vent relay (Primary CO2) on GPIO {self.vent_relay_pin}: {e}. Primary CO2 control will be simulated.")
            self.vent_relay = None # Indicate relay is not available

        # Initialize the second CO2 relay
        self.second_co2_relay = None
        try:
            # For now, using the placeholder. Ensure this is a valid integer if not a placeholder.
            pin_value = 12 # Directly use GPIO 12 for the second CO2 relay
            self.second_co2_relay = RelayOutput(pin_value, initial_value=False) # Start with second solenoid OFF
            print(f"CO2Loop: Second CO2 Relay initialized on GPIO {pin_value}.")
        except Exception as e: # Catch any exception during RelayOutput initialization
            print(f"Warning: Could not initialize second CO2 relay on GPIO {pin_value}: {e}. Second CO2 control will be simulated.")
            self.second_co2_relay = None

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

        # --- Debug Logging ---
        print(f"[CO2 DEBUG] Loop Active: {self._active()}") # Corrected: Use _active() method
        print(f"[CO2 DEBUG] Reading Successful: {reading_successful}")
        if reading_successful:
            print(f"[CO2 DEBUG] Current CO2: {self.current_co2} ppm")
            print(f"[CO2 DEBUG] Setpoint: {self._setpoint} ppm")
            print(f"[CO2 DEBUG] Vent Relay Available: {self.vent_relay is not None}")
            if self.vent_relay:
                print(f"[CO2 DEBUG] Vent Active (State): {self.vent_active}")
                print(f"[CO2 DEBUG] Last Activation: {last_activation_time}")
                print(f"[CO2 DEBUG] Current Time: {current_time}")
                if last_activation_time:
                    print(f"[CO2 DEBUG] Time Since Last: {current_time - last_activation_time:.2f}s")
                print(f"[CO2 DEBUG] Condition Check (current > setpoint): {self.current_co2 > self._setpoint}")
                print(f"[CO2 DEBUG] Condition Check (not active and time >= 60): {not self.vent_active and (last_activation_time is None or current_time - last_activation_time >= 60)}")
        # ---------------------

        # 2. Control Logic (Simple Threshold)
        # This part is only reached if reading_successful is True and the loop is active
        # TODO: Add hysteresis or more advanced control if needed
        if self.vent_relay:
            # We know self.current_co2 is a valid number here
            # --- MODIFIED: Invert logic for injection ---
            if self.current_co2 < self._setpoint: # Check if CO2 is LOW
                if not self.vent_active and (last_activation_time is None or current_time - last_activation_time >= 15):
                    # --- MODIFIED: Update log message ---
                    print(f"CO2 Low ({self.current_co2} ppm < {self._setpoint} ppm). Injecting CO2 (Primary Solenoid) for 0.1 seconds.")
                    self.vent_relay.on()
                    await asyncio.sleep(0.1) # Primary solenoid injection duration
                    self.vent_relay.off()
                    print(f"Primary CO2 injection finished. Waiting 1 second before secondary injection.")
                    await asyncio.sleep(1.0) # Wait 1 second

                    if self.second_co2_relay:
                        print(f"Injecting CO2 (Secondary Solenoid) for 0.1 seconds.")
                        self.second_co2_relay.on()
                        await asyncio.sleep(0.1) # Secondary solenoid injection duration
                        self.second_co2_relay.off()
                        print(f"Secondary CO2 injection finished.")
                    else:
                        print(f"Simulating: Secondary CO2 injection for 0.1 seconds (relay not available).")

                    self._last_activation_time = current_time # Mark activation time after both (or primary if secondary fails)
                else:
                    # Check if vent has been open too long (prevent continuous venting)
                    if self._vent_start_time and (time.monotonic() - self._vent_start_time > MAX_VENT_DURATION_SECONDS):
                         print(f"CO2 Vent MAX DURATION ({MAX_VENT_DURATION_SECONDS}s) reached. Temporarily closing vent.")
                         self.vent_relay.off()
                         # We might want a cooldown period here before allowing vent again
                         # For simplicity now, just closing it allows the next check to potentially reopen if still high
                         self.vent_active = False # Mark as inactive so next check re-evaluates
                         self._vent_start_time = None

            # --- MODIFIED: Logic when injection was active ---
            elif self.vent_active: # CO2 is now >= setpoint, and injection relay is currently active (shouldn't happen with 0.1s pulse, but good practice)
                 # Check minimum vent duration (Now minimum *injection* duration - might not be needed for pulse)
                 # If we were doing continuous injection, this logic would turn it off when CO2 >= setpoint
                 # For 0.1s pulse, this 'elif self.vent_active:' block might be unnecessary as vent_active is never True for long.
                 # Let's keep it simple for now and assume the pulse logic handles it.
                 # If issues arise with continuous activation, revisit this block.
                 # Original logic for turning off vent when CO2 <= setpoint is removed as it's inverted.
                 # We might need logic here if MIN_VENT_DURATION_SECONDS > 0.1s was intended for injection.
                 # Assuming 0.1s pulse is the goal, this block can be simplified or removed.
                 # For now, let's comment out the original deactivation logic based on level.
                 # if self._vent_start_time and (time.monotonic() - self._vent_start_time >= MIN_VENT_DURATION_SECONDS):
                 #     print(f"CO2 Reached Setpoint ({self.current_co2} ppm >= {self._setpoint} ppm). Deactivating injection.")
                 #     self.vent_relay.off()
                 #     self.vent_active = False
                 #     self._vent_start_time = None
                 pass # No action needed here for the 0.1s pulse logic when CO2 >= setpoint
                 # else: Vent is on, but hasn't met minimum duration yet, keep it on. # Removed incorrectly indented lines

        else: # Simulation if relay not initialized
             # We know self.current_co2 is a valid number here
             # --- MODIFIED: Invert simulation logic ---
             if self.current_co2 < self._setpoint: # Check if CO2 is LOW
                 if not self.vent_active:
                     # --- MODIFIED: Update simulation message ---
                     print(f"CO2 Low ({self.current_co2} ppm < {self._setpoint} ppm). (Simulating Primary Solenoid injection ON)")
                     self.vent_active = True # Simulate turning on (briefly for pulse)
                     # In simulation, we don't have the sleep/off, so vent_active might stay True until next check
                     # Simulate secondary solenoid action after a delay
                     print(f"(Simulating: Wait 1s then Secondary Solenoid injection for 0.1s)")
 
             elif self.vent_active: # This 'vent_active' refers to the primary solenoid's conceptual state
                 # --- MODIFIED: Update simulation message ---
                 print(f"CO2 Reached Setpoint ({self.current_co2} ppm >= {self._setpoint} ppm). (Simulating Primary Solenoid injection OFF)")
                 self.vent_active = False
                 # No direct simulation for secondary solenoid turning off as it's a pulse
 
         # print(f"CO2 Loop: Current={self.current_co2} ppm, Setpoint=<{self._setpoint} ppm, Vent Active={self.is_vent_active}") # Debug print
 
    def _ensure_actuator_off(self):
         """Turns all CO2 relays off and resets vent state."""
         if self.vent_relay and self.vent_active: # vent_active refers to primary
             print("CO2 loop inactive: Turning Primary CO2 vent OFF.")
             self.vent_relay.off()
         if self.second_co2_relay and self.second_co2_relay.value: # Check actual state for secondary
             print("CO2 loop inactive: Turning Secondary CO2 vent OFF.")
             self.second_co2_relay.off()
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

    async def start(self):
        """Starts the loop and opens the CO2 sensor connection."""
        try:
            await self.sensor.__aenter__()
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"Error: Failed to open CO2 sensor connection: {e}")
            return  # Prevent the loop from starting if sensor connection fails
        await super().start()

    async def stop(self):
        """Stops the loop, closes the CO2 sensor connection, and ensures the vent is turned off."""
        try:
            await self.sensor.__aexit__()
        except Exception as e:
            print(f"Error: Failed to close CO2 sensor connection: {e}")
        await super().stop()
        if self.vent_relay and self.vent_active: # vent_active refers to primary
            print("CO2Loop stopping: Turning Primary CO2 vent OFF.")
            self.vent_relay.off()
        if self.second_co2_relay and self.second_co2_relay.value: # Check actual state for secondary
            print("CO2Loop stopping: Turning Secondary CO2 vent OFF.")
            self.second_co2_relay.off()
        self.vent_active = False
        # No need to print stopped message, BaseLoop handles it.

    def reset_control(self):
        """Resets the CO2 injection state, ensuring all solenoids are off."""
        print("CO2Loop: Resetting control state (forcing all CO2 solenoids OFF).")
        if self.vent_relay and self.vent_active: # vent_active refers to primary
            self.vent_relay.off()
        if self.second_co2_relay and self.second_co2_relay.value: # Check actual state for secondary
            self.second_co2_relay.off()
        self.vent_active = False
        self._vent_start_time = None

    # Add property for vent status that considers incubator state
    @property
    def is_vent_active(self) -> bool:
        """Returns True if the vent relay is currently commanded ON, incubator is running, and CO2 control is enabled."""
        # The BaseLoop ensures this is only True when the loop is active and commanded ON.
        return self.vent_active