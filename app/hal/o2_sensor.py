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
import smbus
import os

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
  def __init__(self, bus):
    try:
        self.i2cbus = smbus.SMBus(bus)
    except Exception as e:
        print(f"Failed to initialize SMBus on bus {bus}: {e}")
        raise IOError(f"SMBus initialization failed on bus {bus}")

  def get_flash(self):
    # NOTE: Added error handling
    try:
        rslt = self.read_reg(GET_KEY_REGISTER, 1)
        if rslt == 0: # Assuming 0 means default or error, check sensor datasheet if possible
          self.__key = (20.9 / 120.0) # Default value based on original code comment context
        else:
          self.__key = (float(rslt[0]) / 1000.0)
        time.sleep(0.1)
        return True # Indicate success
    except IOError:
        print("Error reading key register. Sensor connected?")
        self.__key = (20.9 / 120.0) # Use default on error
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
        self.__txbuf[0] = int(vol * 10)
        if (mv < 0.000001) and (mv > (-0.000001)):
          self.write_reg(USER_SET_REGISTER, self.__txbuf)
        else:
          self.__txbuf[0] = int((vol / mv) * 1000)
          self.write_reg(AUTUAL_SET_REGISTER, self.__txbuf)
        return True # Indicate success
    except IOError:
        print("Error writing calibration register. Sensor connected?")
        return False # Indicate failure


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
        if not self.get_flash():  # Try to read key, handles initial communication check
            if attempt == retries - 1:
                print("Max retries reached. Attempting to reinitialize sensor.")
                try:
                    self.__init__(self.i2cbus.fd if hasattr(self.i2cbus, 'fd') else bus, self.__addr)
                    print("Sensor reinitialized successfully.")
                except Exception as e:
                    print(f"Sensor reinitialization failed: {e}")
                    return "NC"
            else:
                time.sleep(retry_delay)
                continue

    if 0 < collect_num <= 100:
      try:
        for num in range(collect_num, 1, -1):
          self.__oxygendata[num-1] = self.__oxygendata[num-2]
        # Read sensor data
        rslt = self.read_reg(OXYGEN_DATA_REGISTER, 3)
        # Calculate oxygen level
        current_reading = self.__key * (float(rslt[0]) + float(rslt[1]) / 10.0 + float(rslt[2]) / 100.0)
        self.__oxygendata[0] = current_reading

        if self.__count < collect_num:
          self.__count += 1
        # Return the smoothed average
        return self.get_average_num(self.__oxygendata, self.__count)
      except IOError:
          print("Error reading oxygen data register. Sensor connected?")
          # Reset smoothing buffer if read fails? Optional.
          # self.__count = 0
          # self.__oxygendata = [0]*101
          return "NC" # Return "NC" on communication error
    else: # Invalid collect_num
        print("Error: collect_num must be between 1 and 100.")
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
  def __init__(self, bus, addr):
    self.__addr = addr
    # NOTE: Initialize smbus within a try-except block
    try:
        super(DFRobot_Oxygen_IIC, self).__init__(bus)
        # Optional: Perform an initial read to confirm connection?
        # self.read_reg(GET_KEY_REGISTER, 1) # Example check
        print(f"Oxygen sensor initialized on bus {bus}, address {hex(addr)}")
    except Exception as e:
        print(f"Failed to initialize I2C bus {bus}: {e}")
        # Handle initialization failure, maybe raise an error or set a flag
        raise IOError(f"Failed to initialize oxygen sensor on bus {bus}, address {hex(addr)}")


  def write_reg(self, reg, data):
    # NOTE: Error handling added
    try:
        self.i2cbus.write_i2c_block_data(self.__addr, reg, data)
    except IOError as e:
        print(f"I2C write error to reg {hex(reg)} at addr {hex(self.__addr)}: {e}")
        # os.system('i2cdetect -y 1') # Avoid calling os.system if possible
        time.sleep(0.5) # Short delay before potential retry or returning error
        raise # Re-raise the exception to be caught by calling function

  def read_reg(self, reg, length):
    # NOTE: Error handling added, removed infinite loop and os.system call
    try:
        rslt = self.i2cbus.read_i2c_block_data(self.__addr, reg, length)
        return rslt
    except IOError as e:
        print(f"I2C read error from reg {hex(reg)} at addr {hex(self.__addr)}: {e}")
        # os.system('i2cdetect -y 1') # Avoid calling os.system if possible
        time.sleep(0.5) # Short delay
        raise # Re-raise the exception to be caught by calling function