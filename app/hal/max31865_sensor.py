import board
import busio
import digitalio
import adafruit_max31865
import logging
import time # <-- Add missing import

logger = logging.getLogger(__name__)

class MAX31865:
    """
    Hardware Abstraction Layer for the MAX31865 PT100/PT1000 RTD Sensor Amplifier.
    """
    # Default values match the working example script
    def __init__(self, cs_pin=board.D5, rtd_nominal_resistance=100.0, ref_resistance=430.0, wires=2):
        """
        Initializes the MAX31865 sensor based on the working example script.

        Args:
            cs_pin: The board pin for the chip select (CS) line. Defaults to board.D5 (GPIO5).
            rtd_nominal_resistance: The nominal resistance of the RTD sensor (e.g., 100.0 for PT100).
            ref_resistance: The reference resistor value on the MAX31865 board.
            wires: The number of wires for the RTD sensor (2, 3, or 4).
        """
        self.sensor = None
        self._rtd_nominal_resistance = rtd_nominal_resistance # Store for reference
        self._ref_resistance = ref_resistance # Store for reference
        self._wires = wires # Store for reference

        try:
            # SPI setup (Standard Blinka way)
            sck_pin = board.SCK
            mosi_pin = board.MOSI
            miso_pin = board.MISO
            logger.debug(f"Attempting SPI with SCK: {sck_pin}, MOSI: {mosi_pin}, MISO: {miso_pin}")
            spi = busio.SPI(sck_pin, MOSI=mosi_pin, MISO=miso_pin)
            logger.info(f"busio.SPI object created: {spi}")

            # CS Pin setup
            cs = digitalio.DigitalInOut(cs_pin)
            cs.direction = digitalio.Direction.OUTPUT
            cs.value = True # Deselect

            # Initialize using keyword arguments from the working example
            # Note: Using 'rtd_nominal' and 'ref_resistor' as per example
            self.sensor = adafruit_max31865.MAX31865(
                spi,
                cs,
                wires=self._wires, # Use stored value
                rtd_nominal=self._rtd_nominal_resistance, # Use stored value
                ref_resistor=self._ref_resistance      # Use stored value
            )
            logger.info(f"MAX31865 sensor initialized on CS pin {cs_pin} with wires={self._wires}, rtd_nominal={self._rtd_nominal_resistance}, ref_resistor={self._ref_resistance}")

            # Optional: Test read after init
            _ = self.sensor.temperature
            logger.info("Initial temperature read successful after initialization.")

        except Exception as e: # Catch any potential errors during init
            logger.error(f"An unexpected error occurred during MAX31865 initialization ({e.__class__.__name__}): {e}")
            self.sensor = None
            # Do not re-raise here, allow manager to handle None sensor object

    def read_temperature(self):
        """
        Reads the temperature from the MAX31865 sensor.

        Returns:
            float: The temperature in Celsius, or None if a read error occurs or sensor not initialized.
        """
        if self.sensor is None:
            logger.warning("MAX31865 sensor not initialized. Cannot read temperature.")
            return None

        temperature = None # Initialize temperature
        try:
            temperature = self.sensor.temperature
            logger.debug(f"Raw temperature reading: {temperature}°C")
        except RuntimeError as e:
            logger.error(f"Failed to read temperature from MAX31865 (RuntimeError): {e}")
            self._handle_fault() # Check for specific faults on RuntimeError
            return None # Return None on exception
        except Exception as e:
            logger.error(f"An unexpected error occurred while reading temperature: {e}")
            return None # Return None on exception
        finally:
            # Optionally check fault status even if no exception occurred
            # self._handle_fault() # Can be noisy if called every time
            pass

        # Check if the reading itself indicates a fault (like -242)
        if temperature is not None and temperature < -240:
             logger.warning(f"Temperature reading ({temperature}°C) indicates a potential fault.")
             self._handle_fault() # Check for specific faults if reading is bad

        return temperature

    def _handle_fault(self):
        """
        Checks and logs any fault conditions reported by the sensor.
        Uses properties/methods compatible with recent library versions.
        """
        logger.debug("Entering _handle_fault()...")
        if self.sensor is None:
            logger.warning("_handle_fault: Attempted to handle fault, but self.sensor is None.")
            return

        try:
            # Use the fault property (returns tuple in recent versions)
            fault_tuple = self.sensor.fault
            logger.debug(f"Read fault tuple: {fault_tuple}")

            if isinstance(fault_tuple, tuple) and any(fault_tuple):
                logger.warning(f"MAX31865 Fault detected (Tuple: {fault_tuple})!")
                fault_map = [
                    "RTD High Threshold", "RTD Low Threshold",
                    "REFIN- > 0.85 x VBIAS", "REFIN- < 0.85 x VBIAS (FORCE- open)",
                    "RTDIN- < 0.85 x VBIAS (FORCE- open)", "Overvoltage/undervoltage"
                ]
                for i, fault_active in enumerate(fault_tuple):
                    if fault_active and i < len(fault_map):
                        logger.warning(f"MAX31865 Fault: {fault_map[i]}")

                # Try to clear faults
                try:
                    self.sensor.clear_faults()
                    logger.debug("Attempted to clear MAX31865 faults.")
                except AttributeError:
                    logger.warning("'sensor.clear_faults()' method not found for this library version.")
                except Exception as e:
                    logger.error(f"Error calling clear_faults(): {e}")
            elif isinstance(fault_tuple, tuple):
                logger.debug("No specific fault flags set in fault tuple.")
            else:
                logger.warning(f"Unexpected fault status type received: {type(fault_tuple)}, value: {fault_tuple}")

        except AttributeError:
             logger.error("Could not read fault status: 'sensor.fault' attribute does not exist.")
        except Exception as e:
             logger.error(f"Error reading fault status: {e}")

# Basic test usage (if run directly)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print("Running basic MAX31865 HAL test...")
    # Use GPIO5 (board.D5) as per the working example
    test_sensor = MAX31865(cs_pin=board.D5, wires=2, rtd_nominal_resistance=100.0, ref_resistance=430.0)

    if test_sensor.sensor:
        print("Sensor initialized. Reading temperature...")
        try:
            while True:
                temp = test_sensor.read_temperature()
                if temp is not None:
                    print(f"Temperature: {temp:.2f}°C")
                else:
                    print("Failed to read temperature or sensor fault.")
                time.sleep(2.0)
        except KeyboardInterrupt:
            print("Exiting test.")
    else:
        print("MAX31865 sensor could not be initialized. Please check logs and setup.")
