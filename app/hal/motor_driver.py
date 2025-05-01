from gpiozero import Motor, Device
from gpiozero.pins.mock import MockFactory # For testing without RPi hardware
import time
import logging

logger = logging.getLogger(__name__)

# Uncomment the following line to run on a Raspberry Pi
# Device.pin_factory = None # Use default RPi.GPIO pin factory

# Comment out the following line if running on a Raspberry Pi
Device.pin_factory = MockFactory() # Use mock pins for testing

class L298NMotor:
    """
    Controls a motor connected via an L298N motor driver using gpiozero.
    Assumes one direction control for a pump (using forward motion).
    """
    def __init__(self, pin_ena, pin_in1, pin_in2, frequency=1000):
        """
        Initializes the motor driver using gpiozero.Motor.

        Args:
            pin_ena (int): GPIO pin number for ENA (PWM speed control).
            pin_in1 (int): GPIO pin number for IN1 (Forward).
            pin_in2 (int): GPIO pin number for IN2 (Backward - unused for pump).
            frequency (int): PWM frequency in Hz (Note: gpiozero Motor handles PWM internally).
        """
        self.pin_ena = pin_ena
        self.pin_in1 = pin_in1
        self.pin_in2 = pin_in2
        # frequency is handled by gpiozero, but we keep it for potential future use/info
        self.frequency = frequency
        self.current_speed = 0.0 # Speed as a fraction (0.0 to 1.0)

        try:
            # Initialize gpiozero Motor
            # We map IN1 to 'forward' and IN2 to 'backward'.
            # Enable pin is used for PWM speed control.
            # Initialize gpiozero Motor, explicitly disabling PWM as it's not supported/needed for the pump
            self.motor = Motor(forward=pin_in1, backward=pin_in2, enable=pin_ena, pwm=False)
            logger.info(f"L298NMotor (gpiozero) initialized on ENA={pin_ena}, IN1={pin_in1}, IN2={pin_in2}")
        except Exception as e:
            logger.error(f"Failed to initialize gpiozero Motor: {e}", exc_info=True)
            self.motor = None
            raise # Re-raise exception to signal failure

    def set_speed(self, speed_percent):
        """
        Sets the motor speed.

        Args:
            speed_percent (int): Desired speed as a percentage (0-100).
        """
        if not 0 <= speed_percent <= 100:
            raise ValueError("Speed must be between 0 and 100 percent.")

        speed_fraction = speed_percent / 100.0
        self.current_speed = speed_fraction

        if speed_fraction > 0:
            # For a pump, we only run forward.
            self.motor.forward(speed=speed_fraction)
            # logger.debug(f"Motor speed set to {speed_percent}% (Fraction: {speed_fraction})")
        else:
            self.motor.stop()
            # logger.debug("Motor speed set to 0%, stopping.")


    def start(self, speed_percent=None):
        """Starts the motor at the specified speed, or the last set speed."""
        if speed_percent is not None:
            self.set_speed(speed_percent)
        elif self.current_speed == 0:
             # Default to a reasonable speed if not set and trying to start
             logger.warning("Starting motor without prior speed set. Defaulting to 50%.")
             self.set_speed(50)
        else:
            # Use the last set speed (convert fraction back to percent for set_speed)
             self.set_speed(int(self.current_speed * 100))

        # Log the speed in percentage
        logger.info(f"Motor started at {int(self.current_speed * 100)}% speed.")


    def stop(self):
        """Stops the motor."""
        self.current_speed = 0.0
        if self.motor:
            self.motor.stop()
        logger.info("Motor stopped.")

    def cleanup(self):
        """Cleans up GPIO resources by closing the motor device."""
        if self.motor:
            self.motor.close()
            self.motor = None # Ensure it's marked as closed
        logger.info("L298NMotor (gpiozero) resources released.")

# Example usage (for testing purposes)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    # Use the specified pins
    ENA = 17
    IN1 = 27
    IN2 = 22

    motor_instance = None # Define outside try block
    try:
        print("Initializing motor...")
        motor_instance = L298NMotor(pin_ena=ENA, pin_in1=IN1, pin_in2=IN2)

        print("Starting motor at 50% speed for 3 seconds...")
        motor_instance.start(50)
        time.sleep(3)

        print("Changing speed to 100% for 3 seconds...")
        motor_instance.set_speed(100)
        time.sleep(3)

        print("Changing speed to 70% for 3 seconds...")
        motor_instance.set_speed(70)
        time.sleep(3)

        print("Stopping motor...")
        motor_instance.stop()
        time.sleep(2)

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