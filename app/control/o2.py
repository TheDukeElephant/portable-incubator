import asyncio
import time
from ..hal.o2_sensor import DFRobotO2Sensor
from ..hal.relay_output import RelayOutput
from .base_loop import BaseLoop # Import BaseLoop
# Forward declaration for type hinting
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .manager import ControlManager

class O2Loop(BaseLoop): # Inherit from BaseLoop
    """
    Manages the O2 control loop using simple threshold control.
    Reads O2 concentration from a DFRobot sensor and controls an Argon valve relay
    to displace O2 when the level is too high.
    """
    def __init__(self,
                 manager: 'ControlManager', # Add manager argument
                 o2_sensor: DFRobotO2Sensor,
                 argon_valve_relay: RelayOutput,
                 setpoint: float = 5.0, # Target O2 percentage (Argon ON if O2 > setpoint)
                 sample_time: float = 5.0 # Control loop interval in seconds
                ):
        """
        Initializes the O2 control loop.

        Args:
            manager: The ControlManager instance.
            o2_sensor: Instance of DFRobotO2Sensor.
            argon_valve_relay: Instance of RelayOutput for the Argon valve.
            setpoint: The target O2 percentage. Argon valve opens if O2 > setpoint.
            sample_time: How often the control loop runs (seconds).
        """
        # Call BaseLoop constructor, passing the manager and interval
        super().__init__(manager=manager, control_interval=sample_time)

        self.o2_sensor = o2_sensor
        self.argon_valve_relay = argon_valve_relay
        self._setpoint = setpoint
        # self._sample_time = sample_time # Handled by BaseLoop

        self._current_o2: float | None = None
        self._argon_valve_on: bool = False
        # self._last_update_time: float = 0 # Handled by BaseLoop timing
        # self._active = True # Replaced by BaseLoop._is_running and _stop_event

        # Attempt initial sensor read
        self._read_sensor()
        print(f"O2Loop initialized. Initial O2: {self._current_o2}%, Setpoint: > {self._setpoint}% triggers Argon")

    def _read_sensor(self):
        """Reads the sensor and updates the internal O2 state."""
        o2_level = self.o2_sensor.read_oxygen_concentration()
        if o2_level is not None:
            self._current_o2 = o2_level
        else:
            # Keep the last known O2 level if read fails? Or set to None?
            print("Warning: Failed to read O2 sensor.")
            # self._current_o2 = None # Option 1: Indicate failure
            pass # Option 2: Keep last known value (use with caution)

    async def control_step(self):
        """Reads sensor, applies threshold logic, and updates the Argon valve relay state."""
        self._read_sensor() # Read sensor first

        if self._current_o2 is None:
            # Safety measure: If we don't know the O2 level, keep the Argon valve closed.
            print("Safety: Turning Argon valve OFF due to unknown O2 level.")
            if self._argon_valve_on: # Only act if it was on
                 self.argon_valve_relay.off()
                 self._argon_valve_on = False
            return

        # --- Check if incubator is running ---
        if not self.manager.incubator_running:
            # If stopped, ensure Argon valve is off and skip logic
            if self._argon_valve_on:
                self.argon_valve_relay.off()
                self._argon_valve_on = False
                print("Incubator stopped: Turning Argon valve OFF.")
            return
        # --- Incubator is running, proceed with control ---

        # Threshold Logic: Turn Argon ON if O2 is strictly greater than setpoint
        new_argon_valve_state = self._current_o2 > self._setpoint

        # Update relay only if state changes
        if new_argon_valve_state != self._argon_valve_on:
            if new_argon_valve_state:
                self.argon_valve_relay.on()
                print(f"Argon Valve ON (O2: {self._current_o2:.2f}% > Setpoint: {self._setpoint:.1f}%)")
            else:
                self.argon_valve_relay.off()
                print(f"Argon Valve OFF (O2: {self._current_o2:.2f}% <= Setpoint: {self._setpoint:.1f}%)")
            self._argon_valve_on = new_argon_valve_state

    # Remove the custom run() method, BaseLoop provides it.
    # async def run(self): ...

    async def stop(self):
        """Stops the loop and ensures the Argon valve is turned off."""
        # Call BaseLoop's stop first
        await super().stop()
        # Ensure Argon valve is off as a final step
        if self.argon_valve_relay and self._argon_valve_on:
             print("O2Loop stopping: Turning Argon valve OFF.")
             self.argon_valve_relay.off()
             self._argon_valve_on = False
        # No need to print "stopped" here, BaseLoop does it.

    # Change update_setpoint to a setter property
    @property
    def setpoint(self) -> float:
        """Returns the current O2 threshold setpoint."""
        return self._setpoint

    @setpoint.setter
    def setpoint(self, new_setpoint: float):
        """Updates the target O2 threshold."""
        try:
            new_setpoint = float(new_setpoint)
            # Add reasonable bounds check if necessary (e.g., 0-100)
            if 0 <= new_setpoint <= 100:
                self._setpoint = new_setpoint
                print(f"O2 setpoint (threshold) updated to: {self._setpoint}%. Argon ON if O2 > {self._setpoint}%.")
            else:
                 print(f"Error: Invalid O2 setpoint value: {new_setpoint}. Must be between 0 and 100.")
        except ValueError:
            print(f"Error: Invalid O2 setpoint value: {new_setpoint}")

    @property
    def current_o2(self) -> float | None:
        """Returns the last read O2 concentration."""
        return self._current_o2

    # Keep argon_valve_is_on property
    @property
    def argon_valve_is_on(self) -> bool:
        """Returns True if the Argon valve relay is currently commanded ON."""
         # Reflect the actual state based on incubator running status as well
        return self._argon_valve_on and self.manager.incubator_running

    def get_status(self) -> dict:
        """Returns the current status of the O2 loop."""
        return {
            "o2": self.current_o2,
            "setpoint": self.setpoint,
            "argon_valve_on": self.argon_valve_is_on, # Use property which checks incubator_running
            "control_interval_s": self.control_interval
        }

    # Remove close() and __del__(), rely on manager calling stop() and closing relays
    # def close(self): ...
    # def __del__(self): ...

# Example Usage (Conceptual - requires running within an asyncio loop)
# async def main():
#     from ..hal.relay_output import RelayOutput
#     from ..hal.o2_sensor import DFRobotO2Sensor # Assuming this works
#     # Need a dummy manager for example
#     class DummyManager: incubator_running = True
#     manager = DummyManager()
#
#     ARGON_VALVE_PIN = 23
#     # Assuming DFRobotO2Sensor can be instantiated without errors
#     try:
#         sensor = DFRobotO2Sensor()
#         relay = RelayOutput(ARGON_VALVE_PIN)
#
#         # Example: Target O2 level below 10%
#         # Pass the dummy manager to the constructor
#         loop = O2Loop(manager=manager, o2_sensor=sensor, argon_valve_relay=relay, setpoint=10.0, sample_time=5)
#
#         run_task = asyncio.create_task(loop.run())
#
#         # Simulate running for a while
#         await asyncio.sleep(15)
#         loop.setpoint = 5.0 # Lower the threshold
#         await asyncio.sleep(5)
#         print("Simulating incubator stop...")
#         manager.incubator_running = False # Stop the incubator
#         await asyncio.sleep(5) # See if valve turns off
#         print("Simulating incubator start...")
#         manager.incubator_running = True # Start again
#         await asyncio.sleep(5)
#
#         await loop.stop() # Stop the loop task itself
#         await run_task # Wait for loop to finish cleanly
#         relay.close() # Explicitly close relay if needed
#         sensor.close()
#
#     except Exception as e:
#         print(f"Error during O2 loop example: {e}")
#         print("Ensure sensor and relay can be initialized.")
#
# if __name__ == '__main__':
#      asyncio.run(main())