#!/usr/bin/env python3
"""
Basic SPI communication test.
"""
import time
import board
import busio
import digitalio

# Initialize SPI
spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)

# Initialize CS pin
cs = digitalio.DigitalInOut(board.D8)  # GPIO8
cs.direction = digitalio.Direction.OUTPUT
cs.value = True  # Deselect initially

# Configure SPI
try:
    while not spi.try_lock():
        pass
    spi.configure(baudrate=1000000, polarity=0, phase=1)
    print("SPI configured successfully")
finally:
    spi.unlock()

# Simple test: write and read back a byte
def test_spi_loopback():
    test_data = bytearray([0xA5])  # Test pattern
    result = bytearray(1)
    
    print(f"Testing SPI with data: 0x{test_data[0]:02X}")
    
    cs.value = False  # Select chip
    time.sleep(0.001)
    
    try:
        spi.write(test_data)
        time.sleep(0.001)
        spi.readinto(result)
    finally:
        cs.value = True  # Deselect chip
    
    print(f"Read back: 0x{result[0]:02X}")
    return result[0]

# Run the test
for i in range(5):
    print(f"\nTest {i+1}:")
    result = test_spi_loopback()
    time.sleep(0.5)