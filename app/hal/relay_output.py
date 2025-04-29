from gpiozero import OutputDevice
from gpiozero.exc import BadPinFactory

# Controls a simple relay connected to a GPIO pin.
# Assumes the relay is ACTIVE HIGH (relay turns ON when GPIO is HIGH).
# If your relay is ACTIVE LOW, set active_high=False in OutputDevice.

class RelayOutput:
    """
    A simple wrapper around gpiozero.OutputDevice for controlling a relay.
    """
    def __init__(self, pin: int, initial_value: bool = False):
        """
        Initializes the relay output.

        Args:
            pin: The GPIO pin number (BCM numbering) the relay is connected to.
            initial_value: The initial state of the relay (False=OFF, True=ON).
                           Defaults to OFF.
        """
        self.pin = pin
        self._device = None
        try:
            # Ensure you have configured a pin factory (e.g., pigpio)
            # if running remotely or need software PWM.
            # For basic usage on the Pi itself, the default RPiGPIO factory is often fine.
            self._device = OutputDevice(pin, active_high=True, initial_value=initial_value)
            print(f"RelayOutput initialized on GPIO {pin}")
        except BadPinFactory as e:
            print(f"Error initializing RelayOutput on GPIO {pin}: {e}")
            print("Ensure a compatible pin factory is configured (e.g., RPi.GPIO, pigpio).")
            # In a real scenario, might want to raise this or handle it differently.
            # For simulation/testing without hardware, you might use a mock pin factory.
        except Exception as e:
            print(f"Unexpected error initializing RelayOutput on GPIO {pin}: {e}")
            # Handle other potential exceptions during initialization

    def on(self):
        """Turns the relay ON."""
        if self._device:
            try:
                self._device.on()
                # print(f"Relay GPIO {self.pin} ON")
            except Exception as e:
                print(f"Error turning ON relay GPIO {self.pin}: {e}")
        else:
            print(f"Simulating: Relay GPIO {self.pin} ON (device not initialized)")


    def off(self):
        """Turns the relay OFF."""
        if self._device:
            try:
                self._device.off()
                # print(f"Relay GPIO {self.pin} OFF")
            except Exception as e:
                print(f"Error turning OFF relay GPIO {self.pin}: {e}")
        else:
            print(f"Simulating: Relay GPIO {self.pin} OFF (device not initialized)")

    @property
    def value(self) -> bool:
        """Returns the current state of the relay (True=ON, False=OFF)."""
        if self._device:
            try:
                return self._device.value == 1 # OutputDevice uses 0/1
            except Exception as e:
                print(f"Error getting value for relay GPIO {self.pin}: {e}")
                return False # Or raise an error, depending on desired behavior
        else:
            print(f"Simulating: Getting value for relay GPIO {self.pin} (device not initialized)")
            return False # Default simulated value

    def close(self):
        """Releases the GPIO resources."""
        if self._device:
            try:
                self._device.close()
                print(f"RelayOutput closed for GPIO {self.pin}")
            except Exception as e:
                print(f"Error closing relay GPIO {self.pin}: {e}")
        self._device = None

    def __del__(self):
        """Ensures resources are released when the object is destroyed."""
        self.close()

# Example Usage (for testing purposes)
if __name__ == '__main__':
    import time
    # Replace with actual GPIO pins used for testing
    HEATER_PIN = 17
    HUMIDIFIER_PIN = 27

    print("Testing RelayOutput...")
    try:
        heater_relay = RelayOutput(HEATER_PIN)
        humidifier_relay = RelayOutput(HUMIDIFIER_PIN, initial_value=True)

        print(f"Initial Heater State (GPIO {HEATER_PIN}): {'ON' if heater_relay.value else 'OFF'}")
        print(f"Initial Humidifier State (GPIO {HUMIDIFIER_PIN}): {'ON' if humidifier_relay.value else 'OFF'}")

        print("Turning heater ON...")
        heater_relay.on()
        time.sleep(2)
        print(f"Heater State: {'ON' if heater_relay.value else 'OFF'}")

        print("Turning humidifier OFF...")
        humidifier_relay.off()
        time.sleep(2)
        print(f"Humidifier State: {'ON' if humidifier_relay.value else 'OFF'}")

        print("Turning heater OFF...")
        heater_relay.off()
        time.sleep(1)

    except Exception as e:
        print(f"An error occurred during testing: {e}")
    finally:
        print("Cleaning up GPIO...")
        # The __del__ method handles cleanup, but explicit close is good practice
        if 'heater_relay' in locals() and heater_relay:
            heater_relay.close()
        if 'humidifier_relay' in locals() and humidifier_relay:
            humidifier_relay.close()
        print("Test finished.")