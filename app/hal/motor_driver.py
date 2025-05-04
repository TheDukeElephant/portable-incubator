from app.hal.relay_output import RelayOutput
import time # Keep time for potential use in calling code, though not used here directly
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

    def on(self):
        """Turns the motor ON by activating the relay."""
        logger.info(f"Turning motor ON via relay on GPIO {self.relay_pin}.")
        self.relay.on()

    def off(self):
        """Turns the motor OFF by deactivating the relay."""
        logger.info(f"Turning motor OFF via relay on GPIO {self.relay_pin}.")
        self.relay.off()

    def cleanup(self):
        """Cleans up GPIO resources by closing the relay."""
        self.relay.close()
        logger.info("RelayMotorControl resources released.")

# Example usage removed as it relied on the old method.