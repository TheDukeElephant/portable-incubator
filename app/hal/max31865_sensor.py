import board
import busio
import digitalio
import adafruit_max31865
import logging

logger = logging.getLogger(__name__)

class MAX31865:
    """
    Hardware Abstraction Layer for the MAX31865 PT100/PT1000 RTD Sensor Amplifier.
    """
    def __init__(self, cs_pin=board.D8, rtd_nominal_resistance=100.0, ref_resistance=430.0, wires=3):
        """
        Initializes the MAX31865 sensor.

        Args:
            cs_pin: The board pin for the chip select (CS) line. Defaults to board.D8 (GPIO8).
            rtd_nominal_resistance: The nominal resistance of the RTD sensor (e.g., 100.0 for PT100).
            ref_resistance: The reference resistor value on the MAX31865 board.
            wires: The number of wires for the RTD sensor (2, 3, or 4).
        """
        self.sensor = None
        try:
            # SPI setup
            # Try with explicit pin objects for SCK, MOSI, MISO
            sck_pin = board.SCK # Or board.D11
            mosi_pin = board.MOSI # Or board.D10
            miso_pin = board.MISO # Or board.D9
            
            logger.debug(f"Attempting SPI with SCK: {sck_pin}, MOSI: {mosi_pin}, MISO: {miso_pin}")
            
            # --- Monkey-patch busio.SPI class itself (for diagnostics) ---
            if not hasattr(busio.SPI, 'id'):
                logger.info("Attempting to monkey-patch busio.SPI CLASS with an 'id' attribute (set to 0).")
                busio.SPI.id = 0
            # --- End class monkey-patch ---

            spi = busio.SPI(sck_pin, MOSI=mosi_pin, MISO=miso_pin)
            logger.info(f"busio.SPI object created: {spi}") # Log the object itself
            logger.info(f"Type of spi object: {type(spi)}")
            logger.info(f"Attributes of spi object: {dir(spi)}") # Log all attributes
            if hasattr(spi, 'id'):
                logger.info(f"SPI object now has id: {spi.id}")
            else:
                logger.warning("SPI object still does not have id after class patch and instantiation.")

            cs = digitalio.DigitalInOut(cs_pin)  # Chip select
            cs.direction = digitalio.Direction.OUTPUT
            cs.value = True # Deselect

            # Verify monkey-patch right before use
            if hasattr(spi, 'id'):
                logger.info(f"CONFIRMED: spi object HAS 'id' attribute ({spi.id=}) before passing to MAX31865 constructor.")
            else:
                logger.error("CRITICAL: spi object DOES NOT HAVE 'id' attribute immediately before passing to MAX31865 constructor.")

            self.sensor = adafruit_max31865.MAX31865(
                spi,
                cs,
                # rtd_nominal_resistance=rtd_nominal_resistance, # Removed for testing
                # ref_resistance=ref_resistance, # Removed for testing
                wires=wires # Keep wires for now, common parameter
            )
            logger.info(f"MAX31865 sensor object created for CS pin {cs_pin} with {wires}-wire configuration using SPI bus: {spi} (nominal/ref resistances defaulted by library)")
            # Test sensor communication immediately
            _ = self.sensor.temperature # Try a benign read
            logger.info("MAX31865 sensor communication successful after initialization.")
        except AttributeError as e: # Specifically catch AttributeError like 'SPI' object has no attribute 'id'
            logger.error(f"Failed to initialize MAX31865 sensor (AttributeError): {e}")
            self.sensor = None
            raise # Re-raise
        except Exception as e: # Catch other potential errors during init
            logger.error(f"An unexpected error occurred during MAX31865 initialization ({e.__class__.__name__}): {e}")
            self.sensor = None
            raise # Re-raise

    def read_temperature(self):
        """
        Reads the temperature from the MAX31865 sensor.

        Returns:
            float: The temperature in Celsius, or None if a read error occurs or sensor not initialized.
        """
        if self.sensor is None:
            logger.warning("MAX31865 sensor not initialized. Cannot read temperature.")
            return None

        try:
            temperature = self.sensor.temperature
            # The library might return NaN for fault conditions, check for it.
            # However, the library usually raises RuntimeError for faults.
            # For robustness, we can add a check if needed, but typically faults are exceptions.
            # if temperature != temperature: # Check for NaN
            #     logger.warning("Sensor reported NaN, possibly a fault condition.")
            #     self._handle_fault()
            #     return None
            logger.debug(f"Raw temperature reading: {temperature}°C")
            return temperature
        except RuntimeError as e:
            logger.error(f"Failed to read temperature from MAX31865: {e}")
            self._handle_fault()
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred while reading temperature: {e}")
            return None

    def _handle_fault(self):
        """
        Checks and logs any fault conditions reported by the sensor.
        """
        if self.sensor is None:
            return

        fault = self.sensor.read_fault()
        if fault:
            if fault & adafruit_max31865.MAX31865_FAULT_HIGHTHRESH:
                logger.warning("MAX31865 Fault: RTD High Threshold")
            if fault & adafruit_max31865.MAX31865_FAULT_LOWTHRESH:
                logger.warning("MAX31865 Fault: RTD Low Threshold")
            if fault & adafruit_max31865.MAX31865_FAULT_REFINLOW:
                logger.warning("MAX31865 Fault: REFIN- > 0.85 x VBIAS")
            if fault & adafruit_max31865.MAX31865_FAULT_REFINHIGH:
                logger.warning("MAX31865 Fault: REFIN- < 0.85 x VBIAS (FORCE- open)")
            if fault & adafruit_max31865.MAX31865_FAULT_RTDINLOW:
                logger.warning("MAX31865 Fault: RTDIN- < 0.85 x VBIAS (FORCE- open)")
            if fault & adafruit_max31865.MAX31865_FAULT_OVUV:
                logger.warning("MAX31865 Fault: Overvoltage/undervoltage")
            self.sensor.clear_faults() # Clear faults after reading
        else:
            logger.debug("No faults detected on MAX31865.")

if __name__ == '__main__':
    # Basic test usage
    logging.basicConfig(level=logging.INFO)
    # Ensure SPI is enabled on your Raspberry Pi:
    # sudo raspi-config -> Interface Options -> SPI -> Yes
    #
    # Connections for MAX31865:
    # Vin -> 3V3 or 5V (check board)
    # GND -> GND
    # SCLK -> GPIO11 (Physical Pin 23)
    # MISO -> GPIO9 (Physical Pin 21)
    # MOSI -> GPIO10 (Physical Pin 19)
    # CS   -> GPIO8 (Physical Pin 24) - Default for this class
    #
    # For PT100 RTD (3-wire example):
    # F+ and RTD+ connected together to one wire of RTD
    # F- to second wire of RTD
    # RTD- to third wire of RTD (often the common wire or different color)

    sensor = MAX31865(cs_pin=board.D8, wires=3) # GPIO8 is board.D8

    if sensor.sensor: # Check if sensor was initialized successfully
        try:
            while True:
                temp = sensor.read_temperature()
                if temp is not None:
                    logger.info(f"Temperature: {temp:.2f}°C")
                else:
                    logger.warning("Failed to read temperature or sensor fault.")
                
                # Check for faults explicitly if needed, though read_temperature handles some
                # sensor._handle_fault() 
                
                # Wait a bit before reading again
                import time
                time.sleep(2.0)
        except KeyboardInterrupt:
            logger.info("Exiting test script.")
        finally:
            # Cleanup (if any specific cleanup is needed for SPI or digitalio)
            # spi.deinit() # If spi was created here and not managed by Blinka globally
            # cs.deinit()
            pass
    else:
        logger.error("MAX31865 sensor could not be initialized. Please check logs and setup.")