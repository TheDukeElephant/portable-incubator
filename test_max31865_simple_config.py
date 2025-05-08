#!/usr/bin/env python3
"""
MAX31865 test with very simple configuration.
"""
import time
import spidev
import RPi.GPIO as GPIO

# Initialize GPIO
GPIO.setmode(GPIO.BCM)
CS_PIN = 25  # Use the alternative CS pin that showed some response
GPIO.setup(CS_PIN, GPIO.OUT)
GPIO.output(CS_PIN, GPIO.HIGH)  # Deselect initially

# Initialize SPI
spi = spidev.SpiDev()
spi.open(0, 0)  # Bus 0, Device 0
spi.max_speed_hz = 50000  # Even lower speed
spi.mode = 1  # CPOL=0, CPHA=1 (Mode 1)
spi.bits_per_word = 8

print("SPI initialized with:")
print(f"  Mode: {spi.mode}")
print(f"  Speed: {spi.max_speed_hz} Hz")
print(f"  Bits per word: {spi.bits_per_word}")
print(f"  CS Pin: GPIO{CS_PIN}")

def read_register(reg_addr):
    """Read a register from the MAX31865."""
    # Create read command (MSB=1 for read)
    read_cmd = [reg_addr | 0x80, 0x00]
    
    GPIO.output(CS_PIN, GPIO.LOW)  # Select chip
    time.sleep(0.01)  # Longer delay
    
    result = spi.xfer2(read_cmd)
    
    GPIO.output(CS_PIN, GPIO.HIGH)  # Deselect chip
    time.sleep(0.01)  # Longer delay
    
    return result[1]  # Return the data byte

def write_register(reg_addr, data):
    """Write to a register on the MAX31865."""
    # Create write command (MSB=0 for write)
    write_cmd = [reg_addr & 0x7F, data]
    
    GPIO.output(CS_PIN, GPIO.LOW)  # Select chip
    time.sleep(0.01)  # Longer delay
    
    spi.xfer2(write_cmd)
    
    GPIO.output(CS_PIN, GPIO.HIGH)  # Deselect chip
    time.sleep(0.01)  # Longer delay

try:
    print("\nTesting MAX31865 communication...")
    
    # Reset the chip
    write_register(0x00, 0x00)
    time.sleep(0.5)  # Longer delay after reset
    
    # Read the config register after reset
    config = read_register(0x00)
    print(f"Config register after reset: 0x{config:02X} (should be 0x00)")
    
    # Try writing just the bias bit (0x80)
    print("\nSetting only the bias bit (0x80)...")
    write_register(0x00, 0x80)
    time.sleep(0.5)
    
    # Read back the configuration
    read_back = read_register(0x00)
    print(f"Config after setting bias: 0x{read_back:02X} (should be 0x80)")
    
    # Try reading RTD registers
    print("\nReading RTD registers...")
    msb = read_register(0x01)  # RTD MSB
    lsb = read_register(0x02)  # RTD LSB
    print(f"RTD MSB: 0x{msb:02X}, LSB: 0x{lsb:02X}")
    
    # Try reading fault status
    print("\nReading fault status...")
    fault = read_register(0x07)  # Fault status
    print(f"Fault status: 0x{fault:02X}")
    
except KeyboardInterrupt:
    print("\nTest script terminated by user.")
finally:
    # Clean up
    GPIO.output(CS_PIN, GPIO.HIGH)  # Ensure CS is deselected
    spi.close()
    GPIO.cleanup()