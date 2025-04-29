import asyncio
import time
from ..hal.o2_sensor import DFRobotO2Sensor
from ..hal.relay_output import RelayOutput

class O2Loop:
    """
    Manages the O2 control loop using simple threshold control.
    Reads O2 concentration from a DFRobot sensor and controls an Argon valve relay
    to displace O2 when the level is too high.
    """
    def __init__(self,
                 o2_sensor: DFRobotO2Sensor,
                 argon_valve_relay: RelayOutput,
                 setpoint: float = 20.9, # Target O2 percentage (e.g., atmospheric)
                                         # Or maybe a lower target like 5%? Adjust as needed.
                 sample_time: float = 5.0 # Control loop interval in seconds
                ):
        """
        Initializes the O2 control loop.

        Args:
            o2_sensor: Instance of DFRobotO2Sensor.
            argon_valve_relay: Instance of RelayOutput for the Argon valve.
            setpoint: The target O2 percentage. Argon valve opens if O2 > setpoint.
            sample_time: How often the control loop runs (seconds).
        """
        self.o2_sensor = o2_sensor
        self.argon_valve_relay = argon_valve_relay
        self._setpoint = setpoint
        self._sample_time = sample_time

        self._current_o2: float | None = None
        self._argon_valve_on: bool = False
        self._last_update_time: float = 0
        self._active = True # Flag to control the run loop

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

    def _update_control(self):
        """Applies threshold logic and updates the Argon valve relay state."""
        if self._current_o2 is None:
            # Safety measure: If we don't know the O2 level, keep the Argon valve closed.
            print("Safety: Turning Argon valve OFF due to unknown O2 level.")
            if self._argon_valve_on: # Only act if it was on
                 self.argon_valve_relay.off()
                 self._argon_valve_on = False
            return

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

    async def run(self):
        """Runs the O2 control loop asynchronously."""
        print("O2 control loop started.")
        while self._active:
            start_time = time.monotonic()

            self._read_sensor()
            self._update_control()

            self._last_update_time = time.monotonic()
            elapsed_time = self._last_update_time - start_time

            # Wait until the next sample time
            wait_time = max(0, self._sample_time - elapsed_time)
            await asyncio.sleep(wait_time)

        print("O2 control loop stopped.")
        self.argon_valve_relay.off() # Ensure Argon valve is off when loop stops

    def stop(self):
        """Stops the control loop."""
        self._active = False

    def update_setpoint(self, new_setpoint: float):
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

    @property
    def setpoint(self) -> float:
        """Returns the current O2 threshold setpoint."""
        return self._setpoint

    @property
    def argon_valve_is_on(self) -> bool:
        """Returns True if the Argon valve relay is currently commanded ON."""
        return self._argon_valve_on

    def close(self):
        """Stops the loop and releases resources."""
        print("Closing O2Loop resources...")
        self.stop()
        # Relay resources are closed by its own __del__ or explicit close if needed elsewhere

    def __del__(self):
        """Ensures the loop is stopped upon object deletion."""
        self.stop()

# Example Usage (Conceptual - requires running within an asyncio loop)
# async def main():
#     from ..hal.relay_output import RelayOutput
#     from ..hal.o2_sensor import DFRobotO2Sensor # Assuming this works
#
#     ARGON_VALVE_PIN = 23
#     # Assuming DFRobotO2Sensor can be instantiated without errors
#     try:
#         sensor = DFRobotO2Sensor()
#         relay = RelayOutput(ARGON_VALVE_PIN)
#
#         # Example: Target O2 level below 10%
#         loop = O2Loop(o2_sensor=sensor, argon_valve_relay=relay, setpoint=10.0, sample_time=5)
#
#         run_task = asyncio.create_task(loop.run())
#
#         # Simulate running for a while
#         await asyncio.sleep(20)
#         loop.update_setpoint(5.0) # Lower the threshold
#         await asyncio.sleep(20)
#
#         loop.stop()
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