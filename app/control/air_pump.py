import time
import logging
from app.control.base_loop import BaseLoop
from app.hal.motor_driver import L298NMotor

logger = logging.getLogger(__name__)

# Define GPIO pins (ensure these are correct for your setup)
# Using the pins specified in the task description
PIN_ENA = 17
PIN_IN1 = 27
PIN_IN2 = 22

# Control parameters
PUMP_ON_DURATION_S = 5
PUMP_OFF_DURATION_S = 55
PUMP_CYCLE_DURATION_S = PUMP_ON_DURATION_S + PUMP_OFF_DURATION_S
PUMP_SPEED_PERCENT = 70

class AirPumpControlLoop(BaseLoop):
    """
    Control loop for managing the air pump connected via L298N driver.
    Runs the pump for a set duration at a specific interval.
    """
    def __init__(self, interval_sec=1):
        """
        Initializes the air pump control loop.

        Args:
            interval_sec (int): How often the step method should be called (in seconds).
                                This loop's internal timing is based on time.monotonic(),
                                so the call interval mainly affects responsiveness.
        """
        super().__init__(interval_sec)
        self.name = "AirPumpControl"
        try:
            self.motor = L298NMotor(pin_ena=PIN_ENA, pin_in1=PIN_IN1, pin_in2=PIN_IN2)
            logger.info(f"AirPumpControlLoop initialized with motor on ENA={PIN_ENA}, IN1={PIN_IN1}, IN2={PIN_IN2}")
        except Exception as e:
            logger.error(f"Failed to initialize L298NMotor for Air Pump: {e}", exc_info=True)
            self.motor = None # Ensure motor is None if init fails
            # Consider how to handle this failure - maybe raise an exception or set a failed state

        self.last_cycle_start_time = time.monotonic()
        self.pump_state = "off" # Initial state

    def step(self):
        """
        Executes one step of the control loop.
        Manages the on/off cycle of the air pump.
        """
        if not self.motor:
            # logger.warning("Air pump motor not initialized, skipping step.")
            return # Do nothing if motor failed to initialize

        current_time = time.monotonic()
        time_since_cycle_start = current_time - self.last_cycle_start_time

        # Check if a new cycle should start
        if time_since_cycle_start >= PUMP_CYCLE_DURATION_S:
            self.last_cycle_start_time = current_time
            time_since_cycle_start = 0 # Reset timer for the new cycle
            self.pump_state = "pending_on" # Mark to turn on at the start of the cycle
            logger.debug(f"Air pump cycle reset. Time: {current_time:.2f}")

        # State machine for pump control within the cycle
        if self.pump_state == "pending_on":
            try:
                self.motor.start(PUMP_SPEED_PERCENT)
                self.pump_state = "on"
                logger.info(f"Air pump turned ON at {PUMP_SPEED_PERCENT}% speed. Cycle time: {time_since_cycle_start:.2f}s")
            except Exception as e:
                 logger.error(f"Failed to start air pump: {e}", exc_info=True)
                 self.pump_state = "error" # Enter error state

        elif self.pump_state == "on" and time_since_cycle_start >= PUMP_ON_DURATION_S:
            try:
                self.motor.stop()
                self.pump_state = "off"
                logger.info(f"Air pump turned OFF. Cycle time: {time_since_cycle_start:.2f}s")
            except Exception as e:
                 logger.error(f"Failed to stop air pump: {e}", exc_info=True)
                 self.pump_state = "error" # Enter error state

        elif self.pump_state == "off":
            # Pump remains off until the next cycle starts
            pass

        elif self.pump_state == "error":
            # Stay in error state, maybe attempt recovery or log periodically
            # logger.error("Air pump control is in an error state.")
            pass # Avoid flooding logs, error logged when entering state

        # Optional: Log current state periodically for debugging
        # logger.debug(f"AirPump Step: State={self.pump_state}, CycleTime={time_since_cycle_start:.2f}")

    def get_status(self):
        """Returns the current status of the air pump."""
        if not self.motor:
            return {
                "pump_on": False,
                "speed_percent": 0,
                "state": "error - motor not initialized"
            }

        is_on = self.pump_state == "on"
        current_speed = self.motor.current_speed if is_on else 0

        return {
            "pump_on": is_on,
            "speed_percent": current_speed,
            "state": self.pump_state,
            "cycle_elapsed_time": time.monotonic() - self.last_cycle_start_time
        }

    def cleanup(self):
        """Cleans up resources used by the control loop."""
        if self.motor:
            try:
                self.motor.stop() # Ensure motor is stopped
                self.motor.cleanup()
                logger.info("AirPumpControlLoop cleanup complete.")
            except Exception as e:
                logger.error(f"Error during AirPumpControlLoop cleanup: {e}", exc_info=True)
        else:
            logger.info("AirPumpControlLoop cleanup skipped (motor not initialized).")

# Example usage (for testing purposes)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    print("Starting Air Pump Control Loop test...")
    pump_loop = AirPumpControlLoop(interval_sec=0.5) # Run step more frequently for testing

    try:
        start_time = time.time()
        while time.time() - start_time < PUMP_CYCLE_DURATION_S * 2.5: # Run for 2.5 cycles
            pump_loop.step()
            time.sleep(pump_loop.interval_sec)
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    finally:
        print("Cleaning up...")
        pump_loop.cleanup()
        print("Test finished.")