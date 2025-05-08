#!/usr/bin/env python3
"""
Test MAX31865 with settings matching the working Arduino code.
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
HIGH_FAULT_THR_MSB_REG = 0x03
HIGH_FAULT_THR_LSB_REG = 0x04
LOW_FAULT_THR_MSB_REG = 0x05
LOW_FAULT_THR_LSB_REG = 0x06
FAULT_STATUS_REG = 0x07

# CONFIG_REG bit positions
BIAS_BIT = 0x80
CONVERSION_MODE_BIT = 0x40
ONE_SHOT_BIT = 0x20
THREE_WIRE_BIT = 0x10
FAULT_DETECTION_CYCLE_BITS = 0x0C  # Bits 3:2
FAULT_STATUS_CLEAR_BIT = 0x02
FILTER_SELECT_BIT = 0x01

def read_register(spi, cs, reg_addr):
    """Read a register from the MAX31865."""
    read_cmd = bytearray([reg_addr | 0x80, 0x00])
    result = bytearray(2)
    
    cs.value = False  # Select chip
    time.sleep(0.001)  # Small delay
    
    try:
        spi.write(read_cmd)
        time.sleep(0.001)  # Small delay
        spi.readinto(result)
    finally:
        cs.value = True  # Deselect chip
        time.sleep(0.001)  # Small delay
    
    return result[1]

def write_register(spi, cs, reg_addr, data):
    """Write to a register on the MAX31865."""
    write_cmd = bytearray([reg_addr & 0x7F, data])
    
    cs.value = False  # Select chip
    time.sleep(0.001)  # Small delay
    
    try:
        spi.write(write_cmd)
    finally:
        cs.value = True  # Deselect chip
        time.sleep(0.001)  # Small delay

def read_rtd_value(spi, cs):
    """Read the RTD value from the MAX31865."""
    # Read the RTD MSB and LSB registers
    msb = read_register(spi, cs, RTD_MSB_REG)
    lsb = read_register(spi, cs, RTD_LSB_REG)
    
    # Combine the bytes into a 16-bit value
    rtd_value = (msb << 8) | lsb
    
    # Check if the RTD value is valid (fault bit is LSB of LSB register)
    if lsb & 0x01:
        logger.warning("Fault detected in RTD value")
    
    # Remove the fault bit
    rtd_value >>= 1
    
    return rtd_value

def calculate_temperature(rtd_value, rtd_nominal=100.0, ref_resistance=430.0):
    """Calculate temperature from RTD value."""
    # Convert RTD value to resistance
    resistance = (rtd_value * ref_resistance) / 32768.0
    
    # Calculate temperature using simplified Callendar-Van Dusen equation
    # For PT100: R(t) = R0 * (1 + A*t + B*t^2) for t >= 0
    # where A = 3.9083e-3, B = -5.775e-7
    A = 3.9083e-3
    B = -5.775e-7
    
    # Solve quadratic equation: 0 = B*t^2 + A*t + (1 - R/R0)
    # t = (-A + sqrt(A^2 - 4*B*(1 - R/R0))) / (2*B)
    
    # Check if resistance is valid
    if resistance < 10:
        logger.error(f"Resistance too low: {resistance} ohms - likely a short circuit")
        return None
    
    r_ratio = resistance / rtd_nominal
    
    # For very low temperatures or faults, r_ratio might be too low
    if r_ratio < 0.5:
        logger.error(f"R/R0 ratio too low: {r_ratio} - likely a fault or open circuit")
        return None
    
    # Calculate temperature
    try:
        c = 1 - r_ratio
        temp = (-A + (A**2 - 4*B*c)**0.5) / (2*B)
        return temp
    except Exception as e:
        logger.error(f"Error calculating temperature: {e}")
        return None

def main():
    print("MAX31865 Test - Arduino Match")
    print("----------------------------")
    print("Using settings from working Arduino code")
    
    # Initialize SPI
    spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
    
    # Configure SPI - match Arduino SPI settings
    try:
        while not spi.try_lock():
            pass
        # Arduino typically uses Mode 1 (CPOL=0, CPHA=1) for MAX31865
        spi.configure(baudrate=500000, polarity=0, phase=1)  # Lower baudrate for reliability
        print("SPI configured with: 500kHz, CPOL=0, CPHA=1 (Mode 1)")
    finally:
        spi.unlock()
    
    # Initialize CS pin
    cs = digitalio.DigitalInOut(board.D8)  # GPIO8
    cs.direction = digitalio.Direction.OUTPUT
    cs.value = True  # Deselect initially
    
    # Reset the MAX31865
    print("Resetting MAX31865...")
    write_register(spi, cs, CONFIG_REG, 0x00)  # Reset all bits
    time.sleep(0.1)
    
    # Configure for 2-wire mode - match Arduino configuration
    # The Arduino library uses: bias on, auto conversion, 2-wire, fault detection off, 50Hz filter
    config = BIAS_BIT | CONVERSION_MODE_BIT | FILTER_SELECT_BIT  # 0x81 for 2-wire
    write_register(spi, cs, CONFIG_REG, config)
    print(f"Configured MAX31865 with config byte: 0x{config:02X}")
    
    # Read back configuration to verify
    time.sleep(0.1)  # Give it time to apply
    read_config = read_register(spi, cs, CONFIG_REG)
    print(f"Read back config: 0x{read_config:02X}")
    
    # Clear any existing faults
    write_register(spi, cs, CONFIG_REG, config | FAULT_STATUS_CLEAR_BIT)
    time.sleep(0.1)
    
    # Continuous reading
    print("\nStarting continuous reading (press Ctrl+C to exit):")
    try:
        while True:
            # Read RTD value
            rtd_value = read_rtd_value(spi, cs)
            
            # Calculate resistance
            resistance = (rtd_value * 430.0) / 32768.0
            
            # Calculate temperature
            temp = calculate_temperature(rtd_value)
            
            # Read fault status
            fault_status = read_register(spi, cs, FAULT_STATUS_REG)
            
            # Display results
            print(f"RTD Value: {rtd_value}, Resistance: {resistance:.2f} ohms")
            if temp is not None:
                print(f"Temperature: {temp:.2f}°C")
            else:
                print("Temperature: Invalid reading")
            
            if fault_status:
                print(f"Fault status: 0x{fault_status:02X}")
                # Decode faults like Arduino code
                if fault_status & 0x80:
                    print("  RTD High Threshold")
                if fault_status & 0x40:
                    print("  RTD Low Threshold")
                if fault_status & 0x20:
                    print("  REFIN- > 0.85 x Bias")
                if fault_status & 0x10:
                    print("  REFIN- < 0.85 x Bias - FORCE- open")
                if fault_status & 0x08:
                    print("  RTDIN- < 0.85 x Bias - FORCE- open")
                if fault_status & 0x04:
                    print("  Over/Under voltage fault")
                
                # Clear faults
                write_register(spi, cs, CONFIG_REG, config | FAULT_STATUS_CLEAR_BIT)
            
            print("-" * 40)
            
            # Wait before next reading
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nTest script terminated by user.")

if __name__ == "__main__":
    main()