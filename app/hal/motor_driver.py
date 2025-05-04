from app.hal.relay_output import RelayOutput
import time
import logging

logger = logging.getLogger(__name__)

# Uncomment the following line to run on a Raspberry Pi
# Device.pin_factory = None # Use default RPi.GPIO pin factory

# Comment out the following line if running on a Raspberry Pi
# Device.pin_factory = MockFactory() # Use mock pins for testing

class RelayMotorControl:
    """
    Controls a motor connected via an L298N motor driver using gpiozero.
    Assumes one direction control for a pump (using forward motion).
    """
    def __init__(self, relay_pin):
        """
        Initializes the motor control using a relay.

        Args:
            relay_pin (int): GPIO pin number the relay is connected to.
        """
        self.relay = RelayOutput(relay_pin)
        logger.info(f"RelayMotorControl initialized on GPIO {relay_pin}")

    def run_for_one_second_every_minute(self):
        """
        Turns the motor on for 1 second every minute in a separate thread.
        """
        import threading

        def motor_task():
            try:
                while True:
                    logger.info("Turning motor ON for 1 second.")
                    self.relay.on()
                    time.sleep(1)
                    logger.info("Turning motor OFF.")
                    self.relay.off()
                    logger.info("Waiting for 59 seconds.")
                    time.sleep(59)
            except KeyboardInterrupt:
                logger.info("Motor control interrupted by user.")
            finally:
                self.cleanup()

        motor_thread = threading.Thread(target=motor_task, daemon=True)
        motor_thread.start()
        logger.info("Motor control thread started.")

    def cleanup(self):
        """Cleans up GPIO resources by closing the relay."""
        self.relay.close()
        logger.info("RelayMotorControl resources released.")

# Example usage (for testing purposes)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    # Use the specified pins
    RELAY_PIN = 26

    motor_instance = None # Define outside try block
    try:
        print("Initializing motor...")
        motor_instance = RelayMotorControl(relay_pin=RELAY_PIN)

        print("Running motor for 1 second every minute...")
        motor_instance.run_for_one_second_every_minute()

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
    finally:
        if motor_instance:
            print("Cleaning up GPIO...")
            motor_instance.cleanup()
            print("GPIO cleaned up.")
        else:
            print("Motor not initialized, no cleanup needed.")