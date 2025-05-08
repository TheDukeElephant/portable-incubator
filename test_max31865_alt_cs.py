#!/usr/bin/env python3
"""
Debug script for MAX31865 with alternative CS pin.
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

def test_with_cs_pin(cs_pin):
    print(f"\nTesting with CS pin: {cs_pin}")
    
    # Initialize SPI with very conservative settings
    spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
    
    # Configure SPI with even slower speed and explicit mode
    try:
        while not spi.try_lock():
            pass
        # Try a much lower baudrate
        spi.configure(baudrate=100000, polarity=0, phase=1)
        print(f"SPI configured with: 100kHz, CPOL=0, CPHA=1 (Mode 1)")
    finally:
        spi.unlock()
    
    # Initialize CS pin
    cs = digitalio.DigitalInOut(cs_pin)
    cs.direction = digitalio.Direction.OUTPUT
    cs.value = True  # Deselect initially
    time.sleep(0.1)  # Give it time to stabilize
    
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
        print(f"CS pin {cs_pin} failed.")
        return False
    else:
        print("\n*** COMMUNICATION SUCCESSFUL ***")
        print(f"CS pin {cs_pin} works!")
        return True

def main():
    print("MAX31865 Debug Test - Alternative CS Pins")
    print("---------------------------------------")
    
    # Try different CS pins
    cs_pins = [
        board.D8,   # Default (GPIO8)
        board.D7,   # GPIO7
        board.D25,  # GPIO25
        board.D24,  # GPIO24
        board.D18,  # GPIO18 (PWM0)
        board.D17,  # GPIO17
    ]
    
    for pin in cs_pins:
        success = test_with_cs_pin(pin)
        if success:
            print(f"\nFound working CS pin: {pin}")
            print("Please update your code to use this pin.")
            break
    else:
        print("\nNone of the tested CS pins worked.")
        print("Please check your wiring and MAX31865 board.")

if __name__ == "__main__":
    main()