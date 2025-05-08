#!/usr/bin/env python3
"""
Debug script for MAX31865 testing all SPI modes.
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

def test_spi_mode(polarity, phase):
    mode_name = f"Mode {(polarity << 1) | phase}"
    print(f"\nTesting SPI {mode_name} (CPOL={polarity}, CPHA={phase})")
    
    # Initialize SPI
    spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
    
    # Configure SPI with specified mode
    try:
        while not spi.try_lock():
            pass
        spi.configure(baudrate=100000, polarity=polarity, phase=phase)
        print(f"SPI configured with: 100kHz, CPOL={polarity}, CPHA={phase}")
    finally:
        spi.unlock()
    
    # Initialize CS pin
    cs = digitalio.DigitalInOut(board.D8)  # GPIO8
    cs.direction = digitalio.Direction.OUTPUT
    cs.value = True  # Deselect initially
    time.sleep(0.1)  # Give it time to stabilize
    
    # Reset the MAX31865
    print("\nResetting MAX31865...")
    write_register(spi, cs, CONFIG_REG, 0x00)
    time.sleep(0.5)  # Longer delay after reset
    
    # Try writing and reading back a test pattern
    print("\nWriting test pattern 0xA5 to configuration register:")
    write_register(spi, cs, CONFIG_REG, 0xA5)
    time.sleep(0.1)
    
    print("\nReading back test pattern:")
    config = read_register(spi, cs, CONFIG_REG)
    print(f"Config register value: 0x{config:02X} (should be 0xA5)")
    
    if config != 0xA5:
        print(f"\n*** {mode_name} FAILED ***")
        return False
    else:
        print(f"\n*** {mode_name} SUCCESSFUL ***")
        return True

def main():
    print("MAX31865 Debug Test - SPI Modes")
    print("-----------------------------")
    
    # Try all four SPI modes
    modes = [
        (0, 0),  # Mode 0: CPOL=0, CPHA=0
        (0, 1),  # Mode 1: CPOL=0, CPHA=1 (default for MAX31865)
        (1, 0),  # Mode 2: CPOL=1, CPHA=0
        (1, 1),  # Mode 3: CPOL=1, CPHA=1
    ]
    
    for polarity, phase in modes:
        success = test_spi_mode(polarity, phase)
        if success:
            print(f"\nFound working SPI mode: CPOL={polarity}, CPHA={phase}")
            print("Please update your code to use this mode.")
            break
    else:
        print("\nNone of the SPI modes worked.")
        print("Please check your wiring and MAX31865 board.")

if __name__ == "__main__":
    main()