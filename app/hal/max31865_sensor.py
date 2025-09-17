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

        # Check if the reading itself indicates a fault (like -242). Treat as invalid.
        if temperature is not None and temperature < -240:
            logger.warning("Temperature reading (%s°C) indicates a potential fault.", temperature)
            self._handle_fault()  # Check for specific faults if reading is bad
            return None

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
            logger.error("Error reading fault status: %s", e)

class MAX31865_Hub:
    """
    Manages two MAX31865 sensors, each on a different CS pin.
    """
    def __init__(self, cs_pin_1, cs_pin_2, rtd_nominal_resistance=100.0, ref_resistance=430.0, wires=2):
        """
        Initializes the MAX31865 Hub with two sensors.

        Args:
            cs_pin_1: The board pin for Chip Select of the first sensor.
            cs_pin_2: The board pin for Chip Select of the second sensor.
            rtd_nominal_resistance: Nominal resistance of the RTD (e.g., 100.0 for PT100).
            ref_resistance: Reference resistor value on the MAX31865 board.
            wires: Number of wires for the RTD sensor (2, 3, or 4).
        """
        logger.info(f"Initializing MAX31865 Hub with CS1: {cs_pin_1}, CS2: {cs_pin_2}")
        self.sensor1 = MAX31865(
            cs_pin=cs_pin_1,
            rtd_nominal_resistance=rtd_nominal_resistance,
            ref_resistance=ref_resistance,
            wires=wires
        )
        self.sensor2 = MAX31865(
            cs_pin=cs_pin_2,
            rtd_nominal_resistance=rtd_nominal_resistance,
            ref_resistance=ref_resistance,
            wires=wires
        )

        if not self.sensor1.sensor:
            logger.error(f"Failed to initialize MAX31865 Sensor 1 on CS pin {cs_pin_1}.")
        else:
            logger.info(f"MAX31865 Sensor 1 initialized on CS pin {cs_pin_1}.")
            try:
                t1 = self.sensor1.read_temperature()
                logger.info(f"MAX31865 Sensor 1 first read: {t1}")
            except Exception as e:
                logger.error(f"MAX31865 Sensor 1 first read error: {e}")

        if not self.sensor2.sensor:
            logger.error(f"Failed to initialize MAX31865 Sensor 2 on CS pin {cs_pin_2}.")
        else:
            logger.info(f"MAX31865 Sensor 2 initialized on CS pin {cs_pin_2}.")
            try:
                t2 = self.sensor2.read_temperature()
                logger.info(f"MAX31865 Sensor 2 first read: {t2}")
            except Exception as e:
                logger.error(f"MAX31865 Sensor 2 first read error: {e}")

    def read_temperature_sensor1(self):
        """Reads temperature from sensor 1."""
        if self.sensor1 and self.sensor1.sensor:
            return self.sensor1.read_temperature()
        logger.warning("Sensor 1 not available or not initialized for temperature reading.")
        return None

    def read_temperature_sensor2(self):
        """Reads temperature from sensor 2."""
        if self.sensor2 and self.sensor2.sensor:
            return self.sensor2.read_temperature()
        logger.warning("Sensor 2 not available or not initialized for temperature reading.")
        return None

    def read_all_temperatures(self):
        """Reads temperatures from both sensors and returns them as a dictionary."""
        return {
            "sensor1": self.read_temperature_sensor1(),
            "sensor2": self.read_temperature_sensor2()
        }

# Basic test usage for MAX31865_Hub
if __name__ == '__main__':
    # Configure basic logging
    # For more detailed output, set level to logging.DEBUG
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    logger.info("Running MAX31865_Hub HAL test...")

    # Define CS pins for the two sensors.
    # These are common SPI Chip Select pins on Raspberry Pi.
    # SPI0_CE0_N is GPIO8 (physical pin 24), accessible as board.CE0 or board.D8.
    # SPI0_CE1_N is GPIO7 (physical pin 26), accessible as board.CE1 or board.D7.
    # Ensure these pins are not in use by other SPI devices if SPI0 is shared.
    # If these specific pins are unavailable, any other free GPIO pins can be used.
    # Example: cs_pin_sensor1 = board.D25, cs_pin_sensor2 = board.D24
    try:
        cs_pin_sensor1 = board.CE0
        cs_pin_sensor2 = board.CE1
        logger.info(f"Using CS Pin 1: {cs_pin_sensor1}, CS Pin 2: {cs_pin_sensor2}")
    except AttributeError:
        logger.error("board.CE0 or board.CE1 not defined. Please check your Blinka board definition or choose other GPIOs.")
        logger.info("Example: cs_pin_sensor1 = board.D5 (GPIO5), cs_pin_sensor2 = board.D6 (GPIO6)")
        # Fallback for testing if CE0/CE1 are not available (e.g. on non-Pi or different Blinka setup)
        # Ensure these are valid and free GPIOs on your specific board.
        cs_pin_sensor1 = board.D5 # A default, ensure it's different for sensor 2
        cs_pin_sensor2 = board.D6 # A different default, ensure it's free

    # Initialize the hub for two sensors
    # Common parameters for PT100 sensors:
    # wires: 2, 3, or 4 (ensure this matches your RTD sensor's wiring)
    # rtd_nominal_resistance: 100.0 for PT100, 1000.0 for PT1000
    # ref_resistance: Typically 430.0 for PT100 on Adafruit boards, 4300.0 for PT1000
    sensor_hub = MAX31865_Hub(
        cs_pin_1=cs_pin_sensor1,
        cs_pin_2=cs_pin_sensor2,
        wires=2,
        rtd_nominal_resistance=100.0,
        ref_resistance=430.0
    )

    # Check if sensors were initialized by inspecting the underlying sensor objects
    sensor1_initialized = sensor_hub.sensor1 and sensor_hub.sensor1.sensor
    sensor2_initialized = sensor_hub.sensor2 and sensor_hub.sensor2.sensor

    if sensor1_initialized or sensor2_initialized:
        logger.info("MAX31865 Hub initialized (at least one sensor). Reading temperatures...")
        try:
            for _ in range(5): # Read a few times for testing
                temps = sensor_hub.read_all_temperatures()
                temp1 = temps["sensor1"]
                temp2 = temps["sensor2"]

                if temp1 is not None:
                    logger.info(f"Sensor 1 Temperature: {temp1:.2f}°C")
                else:
                    logger.warning("Failed to read from Sensor 1 (or sensor fault/not initialized).")

                if temp2 is not None:
                    logger.info(f"Sensor 2 Temperature: {temp2:.2f}°C")
                else:
                    logger.warning("Failed to read from Sensor 2 (or sensor fault/not initialized).")
                
                if not sensor1_initialized: logger.info("Sensor 1 was not initialized.")
                if not sensor2_initialized: logger.info("Sensor 2 was not initialized.")

                time.sleep(2.0)
        except KeyboardInterrupt:
            logger.info("Exiting hub test due to KeyboardInterrupt.")
        except Exception as e:
            logger.error(f"An unexpected error occurred during hub test: {e}", exc_info=True)
    else:
        logger.error("Neither MAX31865 sensor in the hub could be initialized. Please check wiring, CS pin assignments, and logs.")
