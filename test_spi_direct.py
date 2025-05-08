#!/usr/bin/env python3
"""
Direct SPI test using spidev library.
"""
import time
import spidev

# Initialize SPI
spi = spidev.SpiDev()
spi.open(0, 0)  # Bus 0, Device 0
spi.max_speed_hz = 1000000
spi.mode = 1  # CPOL=0, CPHA=1

print("SPI initialized with:")
print(f"  Mode: {spi.mode}")
print(f"  Speed: {spi.max_speed_hz} Hz")
print(f"  Bits per word: {spi.bits_per_word}")
print(f"  LSB first: {spi.lsbfirst}")

# Simple loopback test
def test_loopback():
    test_data = [0xA5]
    print(f"Sending: {[hex(b) for b in test_data]}")
    
    # In loopback, the data sent on MOSI should be received on MISO
    result = spi.xfer(test_data)
    print(f"Received: {[hex(b) for b in result]}")
    
    return result[0]

# Run the test
for i in range(5):
    print(f"\nTest {i+1}:")
    result = test_loopback()
    time.sleep(0.5)

# Close SPI
spi.close()