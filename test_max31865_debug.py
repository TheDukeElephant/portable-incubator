#!/usr/bin/env python3
"""
Debug script for MAX31865 with detailed diagnostics.
"""
import time
import board
import busio
import digitalio
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# MAX31865 Register Addresses
CONFIG_REG = 0x00
RTD_MSB_REG = 0x01
RTD_LSB_REG = 0x02
FAULT_STATUS_REG = 0x07

def read_register(spi, cs, reg_addr):
    """Read a register from the MAX31865 with detailed logging."""
    read_cmd = bytearray([reg_addr | 0x80, 0x00])
    result = bytearray(2)
    
    print(f"Reading register 0x{reg_addr:02X}: Sending {[hex(b) for b in read_cmd]}")
    
    cs.value = False  # Select chip
    time.sleep(0.01)  # Longer delay
    
    try:
        spi.write(read_cmd)
        time.sleep(0.01)  # Longer delay
        spi.readinto(result)
        print(f"Read result: {[hex(b) for b in result]}")
    finally:
        cs.value = True  # Deselect chip
        time.sleep(0.01)  # Longer delay
    
    return result[1]

def write_register(spi, cs, reg_addr, data):
    """Write to a register on the MAX31865 with detailed logging."""
    write_cmd = bytearray([reg_addr & 0x7F, data])
    
    print(f"Writing to register 0x{reg_addr:02X}: Sending {[hex(b) for b in write_cmd]}")
    
    cs.value = False  # Select chip
    time.sleep(0.01)  # Longer delay
    
    try:
        spi.write(write_cmd)
    finally:
        cs.value = True  # Deselect chip
        time.sleep(0.01)  # Longer delay

def main():
    print("MAX31865 Debug Test")
    print("-----------------")
    
    # Initialize SPI with very conservative settings
    spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
    
    # Configure SPI with even slower speed and explicit mode
    try:
        while not spi.try_lock():
            pass
        # Try a much lower baudrate
        spi.configure(baudrate=100000, polarity=0, phase=1)
        print("SPI configured with: 100kHz, CPOL=0, CPHA=1 (Mode 1)")
    finally:
        spi.unlock()
    
    # Initialize CS pin with explicit pull-up
    cs = digitalio.DigitalInOut(board.D8)  # GPIO8
    cs.direction = digitalio.Direction.OUTPUT
    cs.value = True  # Deselect initially
    time.sleep(0.1)  # Give it time to stabilize
    
    print("\nTesting basic SPI communication...")
    
    # Reset the MAX31865
    print("\nResetting MAX31865...")
    write_register(spi, cs, CONFIG_REG, 0x00)
    time.sleep(0.5)  # Longer delay after reset
    
    # Read configuration register to verify reset
    print("\nReading configuration after reset:")
    config = read_register(spi, cs, CONFIG_REG)
    print(f"Config register value: 0x{config:02X} (should be 0x00)")
    
    # Try writing and reading back a test pattern
    print("\nWriting test pattern 0xA5 to configuration register:")
    write_register(spi, cs, CONFIG_REG, 0xA5)
    time.sleep(0.1)
    
    print("\nReading back test pattern:")
    config = read_register(spi, cs, CONFIG_REG)
    print(f"Config register value: 0x{config:02X} (should be 0xA5)")
    
    if config != 0xA5:
        print("\n*** COMMUNICATION FAILURE ***")
        print("The MAX31865 is not responding correctly to SPI commands.")
        print("Possible issues:")
        print("1. Check all wiring connections")
        print("2. Verify the CS pin is correctly connected to GPIO8")
        print("3. Make sure SPI is enabled in raspi-config")
        print("4. Try a different MAX31865 board if available")
        print("5. Check if the MAX31865 board requires 5V instead of 3.3V")
        return
    
    # If we get here, basic communication is working
    print("\nBasic SPI communication SUCCESSFUL!")
    
    # Reset again before configuring
    print("\nResetting MAX31865 again...")
    write_register(spi, cs, CONFIG_REG, 0x00)
    time.sleep(0.5)
    
    # Configure for 2-wire mode
    print("\nConfiguring for 2-wire mode...")
    config = 0xC1  # BIAS_BIT | CONVERSION_MODE_BIT | FILTER_SELECT_BIT
    write_register(spi, cs, CONFIG_REG, config)
    time.sleep(0.1)
    
    # Read back configuration
    print("\nReading back configuration:")
    read_config = read_register(spi, cs, CONFIG_REG)
    print(f"Config register value: 0x{read_config:02X} (should be 0xC1)")
    
    if read_config != config:
        print("\n*** CONFIGURATION FAILURE ***")
        print(f"Expected 0x{config:02X} but got 0x{read_config:02X}")
        print("The MAX31865 is not accepting the configuration.")
        return
    
    # Read RTD registers
    print("\nReading RTD registers:")
    msb = read_register(spi, cs, RTD_MSB_REG)
    lsb = read_register(spi, cs, RTD_LSB_REG)
    rtd_value = ((msb << 8) | lsb) >> 1
    resistance = (rtd_value * 430.0) / 32768.0
    print(f"RTD MSB: 0x{msb:02X}, LSB: 0x{lsb:02X}")
    print(f"RTD Value: {rtd_value}")
    print(f"Calculated Resistance: {resistance:.2f} ohms")
    
    # Read fault status
    print("\nReading fault status:")
    fault = read_register(spi, cs, FAULT_STATUS_REG)
    print(f"Fault status: 0x{fault:02X}")
    
    if fault:
        print("Faults detected:")
        if fault & 0x80: print("  RTD High Threshold")
        if fault & 0x40: print("  RTD Low Threshold")
        if fault & 0x20: print("  REFIN- > 0.85 x Bias")
        if fault & 0x10: print("  REFIN- < 0.85 x Bias - FORCE- open")
        if fault & 0x08: print("  RTDIN- < 0.85 x Bias - FORCE- open")
        if fault & 0x04: print("  Over/Under voltage fault")
    else:
        print("No faults detected")

if __name__ == "__main__":
    main()