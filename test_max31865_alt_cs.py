#!/usr/bin/env python3
"""
MAX31865 test with alternative CS pin.
"""
import time
import spidev
import RPi.GPIO as GPIO

# MAX31865 Register Addresses
CONFIG_REG = 0x00
RTD_MSB_REG = 0x01
RTD_LSB_REG = 0x02
FAULT_STATUS_REG = 0x07

# CONFIG_REG bit positions
BIAS_BIT = 0x80
CONVERSION_MODE_BIT = 0x40
ONE_SHOT_BIT = 0x20
THREE_WIRE_BIT = 0x10
FAULT_STATUS_CLEAR_BIT = 0x02
FILTER_SELECT_BIT = 0x01

# Initialize GPIO
GPIO.setmode(GPIO.BCM)
CS_PIN = 25  # Try a different GPIO pin
GPIO.setup(CS_PIN, GPIO.OUT)
GPIO.output(CS_PIN, GPIO.HIGH)  # Deselect initially

# Initialize SPI
spi = spidev.SpiDev()
spi.open(0, 0)  # Bus 0, Device 0
spi.max_speed_hz = 100000  # Even lower speed for reliability
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
    time.sleep(0.005)  # Longer delay
    
    result = spi.xfer2(read_cmd)
    
    GPIO.output(CS_PIN, GPIO.HIGH)  # Deselect chip
    time.sleep(0.005)  # Longer delay
    
    return result[1]  # Return the data byte

def write_register(reg_addr, data):
    """Write to a register on the MAX31865."""
    # Create write command (MSB=0 for write)
    write_cmd = [reg_addr & 0x7F, data]
    
    GPIO.output(CS_PIN, GPIO.LOW)  # Select chip
    time.sleep(0.005)  # Longer delay
    
    spi.xfer2(write_cmd)
    
    GPIO.output(CS_PIN, GPIO.HIGH)  # Deselect chip
    time.sleep(0.005)  # Longer delay

def configure_sensor(wires=2):
    """Configure the MAX31865 sensor."""
    # Reset first
    write_register(CONFIG_REG, 0x00)
    time.sleep(0.1)
    
    # Try a simpler configuration first
    config = BIAS_BIT | ONE_SHOT_BIT  # Just bias and one-shot
    
    if wires == 3:
        config |= THREE_WIRE_BIT
    
    write_register(CONFIG_REG, config)
    print(f"Configured MAX31865 with config byte: 0x{config:02X}")
    
    # Read back configuration to verify
    time.sleep(0.1)  # Longer delay before reading back
    read_config = read_register(CONFIG_REG)
    print(f"Read back config: 0x{read_config:02X}")
    
    # Clear any existing faults
    write_register(CONFIG_REG, config | FAULT_STATUS_CLEAR_BIT)
    time.sleep(0.1)

try:
    print("\nTesting MAX31865 communication...")
    
    # Reset the chip
    write_register(CONFIG_REG, 0x00)
    time.sleep(0.1)
    
    # Read the config register after reset
    config = read_register(CONFIG_REG)
    print(f"Config register after reset: 0x{config:02X} (should be 0x00)")
    
    # Try writing a test pattern
    test_pattern = 0xA5
    write_register(CONFIG_REG, test_pattern)
    time.sleep(0.1)
    
    # Read back the test pattern
    read_back = read_register(CONFIG_REG)
    print(f"Test pattern write: 0x{test_pattern:02X}, read back: 0x{read_back:02X}")
    
    if read_back != test_pattern:
        print("WARNING: Test pattern mismatch - communication issue!")
    else:
        print("Basic communication test PASSED!")
    
    # Configure the sensor
    print("\nConfiguring MAX31865 sensor...")
    configure_sensor(wires=2)  # Change to 3 for 3-wire mode if needed
    
    # Read fault status
    fault = read_register(FAULT_STATUS_REG)
    print(f"Fault status: 0x{fault:02X}")
    
    # Read RTD registers
    msb = read_register(RTD_MSB_REG)
    lsb = read_register(RTD_LSB_REG)
    print(f"RTD MSB: 0x{msb:02X}, LSB: 0x{lsb:02X}")
    
    rtd_value = ((msb << 8) | lsb) >> 1  # Remove fault bit
    resistance = (rtd_value * 430.0) / 32768.0
    print(f"RTD Value: {rtd_value}, Resistance: {resistance:.2f} ohms")
    
except KeyboardInterrupt:
    print("\nTest script terminated by user.")
finally:
    # Clean up
    GPIO.output(CS_PIN, GPIO.HIGH)  # Ensure CS is deselected
    spi.close()
    GPIO.cleanup()
