import time
import logging
from app.control.base_loop import BaseLoop
from app.hal.motor_driver import RelayMotorControl

logger = logging.getLogger(__name__)

# Define GPIO pin for the air pump relay
# Using the pin previously defined as ENA, assuming this is the relay pin now.
# If the pump relay is on GPIO 26, change this value.
AIR_PUMP_RELAY_PIN = 26

# Control parameters for the 1s on, 59s off cycle
PUMP_ON_DURATION_S = 1
PUMP_OFF_DURATION_S = 29
PUMP_CYCLE_DURATION_S = PUMP_ON_DURATION_S + PUMP_OFF_DURATION_S

class AirPumpControlLoop(BaseLoop):
    """
    Control loop for managing the air pump connected via a simple relay.
    Runs the pump for 1 second every 60 seconds.
    Implements the control_step required by BaseLoop.
    """
    def __init__(self, manager: 'ControlManager', control_interval: float, enabled_attr: str):
        """
        Initializes the air pump control loop.

        Args:
            manager: The ControlManager instance (required by BaseLoop).
            control_interval (float): How often the control_step method should be called (in seconds).
                                      This loop's internal timing is based on time.monotonic(),
                                      so the call interval mainly affects responsiveness.
            enabled_attr: The attribute name in the manager for the enabled state.
        """
        # Import ControlManager locally to avoid circular import issues if needed
        from app.control.manager import ControlManager
        # Pass the specific enabled attribute name for this loop
        super().__init__(manager, control_interval, enabled_attr=enabled_attr)
        # self.name = "AirPumpControl" # Name is usually handled by class name or manager
        try:
            self.motor = RelayMotorControl(relay_pin=AIR_PUMP_RELAY_PIN)
            logger.info(f"AirPumpControlLoop initialized with relay on GPIO {AIR_PUMP_RELAY_PIN}")
        except Exception as e:
            logger.error(f"Failed to initialize RelayMotorControl for Air Pump on pin {AIR_PUMP_RELAY_PIN}: {e}", exc_info=True)
            self.motor = None # Ensure motor is None if init fails

        self.last_cycle_start_time = time.monotonic() # Time the current cycle (on or off phase) started
        self.pump_is_on = False # Track if the pump relay is currently active

    async def control_step(self):
        """
        Executes one asynchronous step of the control loop.
        Manages the on/off cycle of the air pump based on elapsed time.
        """
        if not self.motor:
            # logger.warning("Air pump motor not initialized, skipping step.")
            return # Do nothing if motor failed to initialize

        current_time = time.monotonic()
        time_since_cycle_start = current_time - self.last_cycle_start_time

        # Simple timed cycle logic: 1s ON, 59s OFF
        if self.pump_is_on:
            # Pump is currently ON, check if it's time to turn OFF
            if time_since_cycle_start >= PUMP_ON_DURATION_S:
                try:
                    self.motor.off()
                    self.pump_is_on = False
                    self.last_cycle_start_time = current_time # Start the OFF phase timer
                    logger.info(f"Air pump turned OFF. Off phase started.")
                except Exception as e:
                    logger.error(f"Failed to turn off air pump: {e}", exc_info=True)
                    # Consider an error state if needed
        else:
            # Pump is currently OFF, check if it's time to turn ON
            if time_since_cycle_start >= PUMP_OFF_DURATION_S:
                try:
                    self.motor.on()
                    self.pump_is_on = True
                    self.last_cycle_start_time = current_time # Start the ON phase timer
                    logger.info(f"Air pump turned ON for {PUMP_ON_DURATION_S}s.")
                except Exception as e:
                    logger.error(f"Failed to turn on air pump: {e}", exc_info=True)
                    # Consider an error state if needed

    def _ensure_actuator_off(self):
        """Ensures the air pump relay is turned off."""
        if self.motor and self.pump_is_on:
            try:
                logger.info("Air pump loop inactive: Turning relay OFF.")
                self.motor.off()
                self.pump_is_on = False
                self.last_cycle_start_time = time.monotonic() # Reset cycle timer
            except Exception as e:
                logger.error(f"Failed to turn off air pump relay during ensure_off: {e}", exc_info=True)
                # Consider error state

    def reset_control(self):
        """Resets the pump state, ensuring the relay is off."""
        logger.info("AirPumpControlLoop: Resetting control state (forcing relay OFF).")
        if self.motor:
            try:
                self.motor.off()
            except Exception as e:
                 logger.error(f"Failed to turn off air pump relay during reset_control: {e}", exc_info=True)
                 # Consider error state

        self.pump_is_on = False
        self.last_cycle_start_time = time.monotonic() # Reset cycle timer

    # Removed old property definition

    def get_status(self):
        """Returns the current status of the air pump."""
        if not self.motor:
            return {
                "pump_on": False,
                "state": "error - motor not initialized",
                "cycle_elapsed_time": 0.0
            }

        current_time = time.monotonic()
        elapsed_in_phase = current_time - self.last_cycle_start_time
        remaining_in_phase = 0.0
        if self.pump_is_on:
            remaining_in_phase = max(0, PUMP_ON_DURATION_S - elapsed_in_phase)
        else:
            remaining_in_phase = max(0, PUMP_OFF_DURATION_S - elapsed_in_phase)


        return {
            "pump_on": self.pump_is_on,
            "state": "on" if self.pump_is_on else "off",
            "cycle_elapsed_time": elapsed_in_phase,
            "cycle_remaining_time": remaining_in_phase
        }

    def cleanup(self):
        """Cleans up resources used by the control loop."""
        if self.motor:
            try:
                self.motor.off() # Ensure motor is off
                # self.motor.cleanup() # cleanup is called by RelayOutput.__del__ or explicitly elsewhere if needed
                logger.info("AirPumpControlLoop cleanup: Motor turned off.")
            except Exception as e:
                logger.error(f"Error during AirPumpControlLoop cleanup: {e}", exc_info=True)
        else:
            logger.info("AirPumpControlLoop cleanup skipped (motor not initialized).")

# Example usage (for testing purposes - needs adaptation for async and manager)
# if __name__ == '__main__':
#     import asyncio
#     # This example needs a mock manager or adaptation to run standalone
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#     print("Starting Air Pump Control Loop test (requires async setup)...")
#
#     async def run_test():
#         # Mock manager needed here
#         # pump_loop = AirPumpControlLoop(manager=None, control_interval=0.5)
#         print("Mock manager and async runner required for standalone test.")
#         # try:
#         #     start_time = time.monotonic()
#         #     while time.monotonic() - start_time < PUMP_CYCLE_DURATION_S * 2.5: # Run for 2.5 cycles
#         #         await pump_loop.control_step()
#         #         await asyncio.sleep(pump_loop.control_interval) # Use asyncio.sleep
#         # except KeyboardInterrupt:
#         #     print("\nTest interrupted by user.")
#         # finally:
#         #     print("Cleaning up...")
#         #     pump_loop.cleanup() # Cleanup might need async adaptation if it blocks
#         #     print("Test finished.")
#
#     # asyncio.run(run_test())