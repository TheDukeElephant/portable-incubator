#!/usr/bin/env python3
"""
Simple MAX31865 test using GPIO8 as CS pin.
"""
import time
import spidev
import RPi.GPIO as GPIO

# Initialize GPIO
GPIO.setmode(GPIO.BCM)
CS_PIN = 8  # Use GPIO8 as CS pin
GPIO.setup(CS_PIN, GPIO.OUT)
GPIO.output(CS_PIN, GPIO.HIGH)  # Deselect initially

# Initialize SPI
spi = spidev.SpiDev()
spi.open(0, 0)  # Bus 0, Device 0
spi.max_speed_hz = 100000  # Lower speed for reliability
spi.mode = 1  # CPOL=0, CPHA=1 (Mode 1)
spi.bits_per_word = 8

print("SPI initialized with:")
print(f"  Mode: {spi.mode}")
print(f"  Speed: {spi.max_speed_hz} Hz")
print(f"  Bits per word: {spi.bits_per_word}")
print(f"  CS Pin: GPIO{CS_PIN}")

def test_transfer(data):
    """Test SPI transfer with the MAX31865."""
    print(f"\nSending: {[hex(b) for b in data]}")
    
    GPIO.output(CS_PIN, GPIO.LOW)  # Select chip
    time.sleep(0.01)  # Longer delay
    
    result = spi.xfer2(data)
    
    GPIO.output(CS_PIN, GPIO.HIGH)  # Deselect chip
    time.sleep(0.01)  # Longer delay
    
    print(f"Received: {[hex(b) for b in result]}")
    return result

try:
    print("\nTesting basic SPI communication with MAX31865...")
    
    # Test 1: Read configuration register (should be 0x00 after power-up)
    print("\nTest 1: Reading configuration register (0x00)")
    result = test_transfer([0x80, 0x00])  # 0x80 = read command for register 0
    
    # Test 2: Try to write and read back a test pattern
    print("\nTest 2: Writing test pattern 0xA5 to configuration register")
    test_transfer([0x00, 0xA5])  # 0x00 = write command for register 0
    
    print("\nTest 3: Reading back test pattern")
    result = test_transfer([0x80, 0x00])
    
except KeyboardInterrupt:
    print("\nTest script terminated by user.")
finally:
    # Clean up
    GPIO.output(CS_PIN, GPIO.HIGH)  # Ensure CS is deselected
    spi.close()
    GPIO.cleanup()