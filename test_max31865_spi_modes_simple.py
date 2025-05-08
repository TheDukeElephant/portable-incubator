#!/usr/bin/env python3
"""
Test MAX31865 with different SPI modes using a simpler approach.
"""
import time
import spidev
import RPi.GPIO as GPIO

# Initialize GPIO
GPIO.setmode(GPIO.BCM)
CS_PIN = 25  # Use the alternative CS pin that showed some response
GPIO.setup(CS_PIN, GPIO.OUT)
GPIO.output(CS_PIN, GPIO.HIGH)  # Deselect initially

def test_spi_mode(mode_num):
    """Test a specific SPI mode."""
    print(f"\nTesting SPI Mode {mode_num}")
    
    # Initialize SPI
    spi = spidev.SpiDev()
    spi.open(0, 0)  # Bus 0, Device 0
    spi.max_speed_hz = 100000  # Lower speed for reliability
    spi.mode = mode_num
    spi.bits_per_word = 8
    
    print(f"SPI configured with Mode {mode_num}")
    
    # Function to read a register
    def read_reg(addr):
        GPIO.output(CS_PIN, GPIO.LOW)
        time.sleep(0.005)
        result = spi.xfer2([addr | 0x80, 0x00])
        GPIO.output(CS_PIN, GPIO.HIGH)
        time.sleep(0.005)
        return result[1]
    
    # Function to write to a register
    def write_reg(addr, data):
        GPIO.output(CS_PIN, GPIO.LOW)
        time.sleep(0.005)
        spi.xfer2([addr & 0x7F, data])
        GPIO.output(CS_PIN, GPIO.HIGH)
        time.sleep(0.005)
    
    try:
        # Reset the chip
        write_reg(0x00, 0x00)
        time.sleep(0.1)
        
        # Read config register after reset
        config = read_reg(0x00)
        print(f"Config after reset: 0x{config:02X} (should be 0x00)")
        
        # Try writing a test pattern
        test_pattern = 0xA5
        write_reg(0x00, test_pattern)
        time.sleep(0.1)
        
        # Read back the test pattern
        read_back = read_reg(0x00)
        print(f"Test pattern write: 0x{test_pattern:02X}, read back: 0x{read_back:02X}")
        
        if read_back == test_pattern:
            print(f"SPI Mode {mode_num} WORKS!")
            return True
        else:
            print(f"SPI Mode {mode_num} FAILED!")
            return False
    finally:
        spi.close()

try:
    print("Testing MAX31865 with different SPI modes")
    print("----------------------------------------")
    
    # Test all four SPI modes
    for mode in range(4):
        success = test_spi_mode(mode)
        if success:
            print(f"\nSPI Mode {mode} is compatible with MAX31865!")
    
except KeyboardInterrupt:
    print("\nTest script terminated by user.")
finally:
    # Clean up
    GPIO.cleanup()