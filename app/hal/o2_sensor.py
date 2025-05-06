# -*- coding: utf-8 -*
'''!
  @file DFRobot_Oxygen.py
  @brief Define the basic struct of DFRobot_Oxygen class, the implementation of basic method
  @copyright Copyright (c) 2010 DFRobot Co.Ltd (http://www.dfrobot.com)
  @license The MIT License (MIT)
  @author [ZhixinLiu](zhixin.liu@dfrobot.com)
  @version V1.0
  @date 2021-10-22
  @url https://github.com/DFRobot/DFRobot_Oxygen
'''
import time
import smbus2 as smbus # Changed to smbus2 for consistency
import os
import logging

## I2C address select
ADDRESS_0                 = 0x70
ADDRESS_1                 = 0x71
ADDRESS_2                 = 0x72
ADDRESS_3                 = 0x73
## Register for oxygen data
OXYGEN_DATA_REGISTER      = 0x03
## Register for users to configure key value manually
USER_SET_REGISTER         = 0x08
## Register for automatically configuring key value
AUTUAL_SET_REGISTER       = 0x09
## Register for obtaining key value
GET_KEY_REGISTER          = 0x0A

class DFRobot_Oxygen(object):
  ## oxygen key value
  __key      = 0.0
  ## Data value to be smoothed
  __count    = 0
  __txbuf      = [0]
  __oxygendata = [0]*101
  # Changed 'bus' parameter to 'i2cbus_obj' to reflect it's an SMBus object
  def __init__(self, i2cbus_obj: smbus.SMBus, logger_parent=None):
    # Setup logger
    if logger_parent:
        self.logger = logger_parent.getChild("DFRobot_Oxygen_HAL")
    else:
        self.logger = logging.getLogger("DFRobot_Oxygen_HAL")
        if not self.logger.handlers: # Add a default handler if none exist
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO) # Default level

    # Assign the pre-initialized SMBus object
    self.i2cbus = i2cbus_obj
    if self.i2cbus:
        self.logger.debug(f"SMBus object received and assigned.")
    else:
        # This case should ideally be prevented by the caller, but good to log.
        self.logger.error(f"No SMBus object provided to DFRobot_Oxygen constructor.")
        raise ValueError("SMBus object cannot be None")

  def get_flash(self):
    # NOTE: Added error handling
    try:
        self.logger.debug(f"Reading key register (GET_KEY_REGISTER: {hex(GET_KEY_REGISTER)})")
        rslt = self.read_reg(GET_KEY_REGISTER, 1) # pylint: disable=no-member
        if not rslt or rslt[0] == 0: # Check if rslt is None or empty, or value is 0
          self.logger.warning("Key register read 0 or empty. Using default key.")
          self.__key = (20.9 / 120.0) # Default value based on original code comment context
        else:
          self.__key = (float(rslt[0]) / 1000.0)
          self.logger.info(f"Key register read successfully. Key set to: {self.__key} (raw: {rslt[0]})")
        time.sleep(0.1)
        return True # Indicate success
    except IOError as e:
        self.logger.error(f"IOError reading key register. Sensor connected? Error: {e}", exc_info=True)
        self.__key = (20.9 / 120.0) # Use default on error
        self.logger.warning("Using default key due to read error.")
        return False # Indicate failure
    except Exception as e: # Catch other potential errors
        self.logger.error(f"Unexpected error reading key register: {e}", exc_info=True)
        self.__key = (20.9 / 120.0) # Use default on error
        self.logger.warning("Using default key due to unexpected error.")
        return False # Indicate failure

  def calibrate(self, vol, mv):
    '''!
      @brief Calibrate sensor
      @param vol Oxygen concentration unit vol
      @param mv Calibrated voltage unit mv
      @return None
    '''
    # NOTE: Added error handling
    try:
        self.logger.info(f"Calibrating sensor with vol: {vol}, mv: {mv}")
        self.__txbuf[0] = int(vol * 10)
        if (mv < 0.000001) and (mv > (-0.000001)):
          self.logger.debug(f"Writing to USER_SET_REGISTER ({hex(USER_SET_REGISTER)}) with value: {self.__txbuf}")
          self.write_reg(USER_SET_REGISTER, self.__txbuf) # pylint: disable=no-member
        else:
          self.__txbuf[0] = int((vol / mv) * 1000)
          self.logger.debug(f"Writing to AUTUAL_SET_REGISTER ({hex(AUTUAL_SET_REGISTER)}) with value: {self.__txbuf}")
          self.write_reg(AUTUAL_SET_REGISTER, self.__txbuf) # pylint: disable=no-member
        self.logger.info("Calibration write successful.")
        return True # Indicate success
    except IOError as e:
        self.logger.error(f"IOError writing calibration register. Sensor connected? Error: {e}", exc_info=True)
        return False # Indicate failure
    except Exception as e: # Catch other potential errors
        self.logger.error(f"Unexpected error during calibration: {e}", exc_info=True)
        return False


  def get_oxygen_data(self, collect_num):
    '''!
      @brief Get oxygen concentration
      @param collectNum The number of data to be smoothed
      @n     For example, upload 20 and take the average value of the 20 data, then return the concentration data
      @return Oxygen concentration (float, unit vol) or "NC" (string) if sensor not connected/error.
      Includes retries and reinitialization for robustness.
    '''
    # NOTE: Modified to handle errors and return "NC"
    retries = 3
    retry_delay = 0.5

    for attempt in range(retries):
        self.logger.debug(f"get_oxygen_data attempt {attempt + 1}/{retries}")
        if not self.get_flash():  # Try to read key, handles initial communication check
            self.logger.warning(f"get_flash failed during get_oxygen_data attempt {attempt + 1}.")
            if attempt == retries - 1:
                self.logger.error("Max retries reached for get_flash. Sensor communication unstable.")
                # Removed problematic re-initialization block
                return "NC"
            else:
                time.sleep(retry_delay)
                continue
        # If get_flash was successful, break the retry loop for get_flash
        break
    else: # This else belongs to the for loop, executed if loop finished without break
        self.logger.error("All attempts to get_flash failed in get_oxygen_data.")
        return "NC"

    # Proceed with reading oxygen data only if get_flash was successful
    if 0 < collect_num <= 100:
        try:
            self.logger.debug(f"Collecting {collect_num} samples for oxygen data.")
            for num in range(collect_num, 1, -1):
                self.__oxygendata[num-1] = self.__oxygendata[num-2]
            # Read sensor data
            self.logger.debug(f"Reading OXYGEN_DATA_REGISTER ({hex(OXYGEN_DATA_REGISTER)})")
            rslt = self.read_reg(OXYGEN_DATA_REGISTER, 3) # pylint: disable=no-member
            if not rslt or len(rslt) < 3:
                self.logger.error(f"Failed to read sufficient data from OXYGEN_DATA_REGISTER. Got: {rslt}")
                return "NC"

            # Calculate oxygen level
            raw_value = (float(rslt[0]) + float(rslt[1]) / 10.0 + float(rslt[2]) / 100.0)
            current_reading = self.__key * raw_value
            self.logger.debug(f"Raw sensor values: {rslt}, calculated raw_value: {raw_value}, key: {self.__key}, current_reading: {current_reading}")
            self.__oxygendata[0] = current_reading

            if self.__count < collect_num:
                self.__count += 1
            # Return the smoothed average
            avg_o2 = self.get_average_num(self.__oxygendata, self.__count)
            self.logger.debug(f"Smoothed O2: {avg_o2} from {self.__count} samples.")
            return avg_o2
        except IOError as e:
            self.logger.error(f"IOError reading oxygen data register. Sensor connected? Error: {e}", exc_info=True)
            return "NC" # Return "NC" on communication error
        except Exception as e: # Catch other potential errors
            self.logger.error(f"Unexpected error reading oxygen data: {e}", exc_info=True)
            return "NC"
    else: # Invalid collect_num
        self.logger.error(f"Invalid collect_num: {collect_num}. Must be between 1 and 100.")
        return "NC" # Or raise an error, returning "NC" for simplicity here

  def get_average_num(self, barry, Len):
    # NOTE: Ensure Len is not zero to avoid division by zero error
    if Len == 0:
        return 0.0 # Or handle as appropriate, maybe return "NC"?
    temp = 0.0
    for num in range (0, Len):
      # Ensure items in barry are numbers before adding
      if isinstance(barry[num], (int, float)):
          temp += barry[num]
      # else: handle potential non-numeric data if necessary
    return (temp / float(Len))

class DFRobot_Oxygen_IIC(DFRobot_Oxygen):
  def __init__(self, bus, addr, logger_parent=None): # Added logger_parent
    self.__addr = addr
    # Initialize the base class, passing the i2cbus_obj (formerly bus) and logger_parent
    super(DFRobot_Oxygen_IIC, self).__init__(i2cbus_obj=bus, logger_parent=logger_parent) # 'bus' here is the i2cbus_obj from O2Loop
    # Logger is now self.logger from the base class
    # The bus number for logging can be retrieved from the i2cbus object if needed, e.g., bus.fd or similar,
    # but smbus2 doesn't directly expose the bus number easily after init.
    # We'll log the address primarily.
    self.logger.info(f"DFRobot_Oxygen_IIC attempting initialization with provided SMBus object, address {hex(addr)}")

    # NOTE: smbus initialization is now handled by the caller (O2Loop)
    # The try-except for smbus init is handled by the caller.

    # Optional: Perform an initial read to confirm connection?
    try:
        # self.read_reg(GET_KEY_REGISTER, 1) # Example check, get_flash will do this
        if self.get_flash(): # This also logs
             self.logger.info(f"Oxygen sensor I2C communication confirmed for address {hex(addr)}.")
        else:
             self.logger.warning(f"Oxygen sensor I2C communication problem for address {hex(addr)} during init check (get_flash failed).")
             # Depending on desired behavior, could raise an error here
             # raise IOError(f"Failed to confirm sensor communication via get_flash for address {hex(addr)}")
    except Exception as e:
        self.logger.error(f"Failed during initial sensor check for DFRobot_Oxygen_IIC, addr {hex(addr)}: {e}", exc_info=True)
        # Handle initialization failure, maybe raise an error or set a flag
        raise IOError(f"Failed to initialize/check oxygen sensor for address {hex(addr)}")


  def write_reg(self, reg, data):
    # NOTE: Error handling added
    try:
        self.logger.debug(f"I2C write to addr {hex(self.__addr)}, reg {hex(reg)}, data: {data}")
        self.i2cbus.write_i2c_block_data(self.__addr, reg, data)
    except IOError as e:
        self.logger.error(f"I2C write error to reg {hex(reg)} at addr {hex(self.__addr)}: {e}", exc_info=True)
        time.sleep(0.5) # Short delay before potential retry or returning error
        raise # Re-raise the exception to be caught by calling function
    except Exception as e: # Catch other potential errors
        self.logger.error(f"Unexpected error during I2C write to reg {hex(reg)} at addr {hex(self.__addr)}: {e}", exc_info=True)
        raise

  def read_reg(self, reg, length):
    # NOTE: Error handling added, removed infinite loop and os.system call
    try:
        self.logger.debug(f"I2C read from addr {hex(self.__addr)}, reg {hex(reg)}, length: {length}")
        rslt = self.i2cbus.read_i2c_block_data(self.__addr, reg, length)
        self.logger.debug(f"I2C read result: {rslt}")
        return rslt
    except IOError as e:
        self.logger.error(f"I2C read error from reg {hex(reg)} at addr {hex(self.__addr)}: {e}", exc_info=True)
        time.sleep(0.5) # Short delay
        raise # Re-raise the exception to be caught by calling function
    except Exception as e: # Catch other potential errors
        self.logger.error(f"Unexpected error during I2C read from reg {hex(reg)} at addr {hex(self.__addr)}: {e}", exc_info=True)
        raise