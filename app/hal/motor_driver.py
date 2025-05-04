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
    Controls a motor using a relay connected to a GPIO pin.
    """
    def __init__(self, relay_pin=26):
        """
        Initializes the motor control using a relay.

        Args:
            relay_pin (int): GPIO pin number the relay is connected to.
        """
        self.relay = RelayOutput(relay_pin)
        self.relay_pin = relay_pin
        logger.info(f"RelayMotorControl initialized on GPIO {relay_pin}")

    async def control_step(self):
        """
        Controls the motor relay using the same logic as the CO2 valve relay.
        """
        try:
            logger.info(f"Turning motor ON for 1 second on GPIO {self.relay_pin}.")
            self.relay.on()
            await asyncio.sleep(1)
            logger.info(f"Turning motor OFF on GPIO {self.relay_pin}.")
            self.relay.off()
            logger.info("Waiting for 59 seconds.")
            await asyncio.sleep(59)
        except Exception as e:
            logger.error(f"Error in motor control step: {e}")

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