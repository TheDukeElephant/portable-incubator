#!/usr/bin/env python3
"""
Direct test script for MAX31865 sensor using raw register access.
This bypasses higher-level functions to directly read the MAX31865 registers.
"""
import time
import board
import busio
import digitalio
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MAX31865 Register Addresses
CONFIG_REG = 0x00
RTD_MSB_REG = 0x01
RTD_LSB_REG = 0x02
FAULT_STATUS_REG = 0x07

# CONFIG_REG bit positions
BIAS_BIT = 0x80  # Enable bias voltage
CONVERSION_MODE_BIT = 0x40  # 1-shot (0) or auto (1)
ONE_SHOT_BIT = 0x20  # Trigger one-shot conversion
THREE_WIRE_BIT = 0x10  # 2/4-wire (0) or 3-wire (1)
FAULT_DETECTION_BITS = 0x0C  # Fault detection cycle control
FAULT_STATUS_CLEAR_BIT = 0x02  # Clear fault status
FILTER_50HZ_BIT = 0x01  # 60Hz (0) or 50Hz (1) filter

def read_register(spi, cs, reg_addr):
    """Read a register from the MAX31865."""
    # Create read command (MSB=1 for read)
    read_cmd = bytearray([reg_addr | 0x80, 0x00])
    result = bytearray(2)
    
    # Add a small delay before selecting chip
    time.sleep(0.001)
    cs.value = False  # Select chip
    time.sleep(0.001)  # Small delay after chip select
    
    try:
        spi.write(read_cmd)
        time.sleep(0.001)  # Small delay between write and read
        spi.readinto(result)
    finally:
        time.sleep(0.001)  # Small delay before deselecting
        cs.value = True  # Deselect chip
        time.sleep(0.001)  # Small delay after deselect
    
    return result[1]  # Return the data byte

def write_register(spi, cs, reg_addr, data):
    """Write to a register on the MAX31865."""
    # Create write command (MSB=0 for write)
    write_cmd = bytearray([reg_addr & 0x7F, data])
    
    cs.value = False  # Select chip
    try:
        spi.write(write_cmd)
    finally:
        cs.value = True  # Deselect chip

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

def read_fault_status(spi, cs):
    """Read the fault status register from the MAX31865."""
    fault_status = read_register(spi, cs, FAULT_STATUS_REG)
    
    # Decode fault status
    faults = []
    if fault_status & 0x80:
        faults.append("RTD High Threshold")
    if fault_status & 0x40:
        faults.append("RTD Low Threshold")
    if fault_status & 0x20:
        faults.append("REFIN- > 0.85 x VBIAS")
    if fault_status & 0x10:
        faults.append("REFIN- < 0.85 x VBIAS (FORCE- open)")
    if fault_status & 0x08:
        faults.append("RTDIN- < 0.85 x VBIAS (FORCE- open)")
    if fault_status & 0x04:
        faults.append("Overvoltage/undervoltage")
    
    return fault_status, faults

def configure_sensor(spi, cs, wires=2):
    """Configure the MAX31865 sensor."""
    # Try a simpler configuration: bias on, one-shot conversion, 2/4-wire
    config = BIAS_BIT | ONE_SHOT_BIT  # Remove auto conversion
    
    # Set wire mode (3-wire or 2/4-wire)
    if wires == 3:
        config |= THREE_WIRE_BIT
    
    # Write configuration
    write_register(spi, cs, CONFIG_REG, config)
    logger.info(f"Configured MAX31865 with config byte: 0x{config:02X}")
    
    # Read back configuration to verify
    read_config = read_register(spi, cs, CONFIG_REG)
    logger.info(f"Read back config: 0x{read_config:02X}")
    
    # Clear any existing faults
    fault_status, faults = read_fault_status(spi, cs)
    if fault_status:
        logger.warning(f"Clearing faults: {faults}")
        write_register(spi, cs, CONFIG_REG, config | FAULT_STATUS_CLEAR_BIT)

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

def reset_max31865(spi, cs):
    """Perform a software reset of the MAX31865."""
    print("Performing software reset of MAX31865...")
    
    # Write 0x00 to clear the configuration register
    write_register(spi, cs, CONFIG_REG, 0x00)
    time.sleep(0.1)  # Short delay
    
    # Read back to verify
    read_config = read_register(spi, cs, CONFIG_REG)
    print(f"After reset, config register: 0x{read_config:02X}")
    
    # Wait a bit longer before continuing
    time.sleep(0.5)

def main():
    print("MAX31865 Raw Register Test")
    print("-------------------------")
    print("This script directly accesses MAX31865 registers to diagnose issues.")
    print("Press Ctrl+C to exit.")
    print()
    
    # Initialize SPI with explicit mode and frequency
    # Note: We've confirmed the correct SDI/SDO connections
    spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
    
    # Try to configure SPI with specific parameters
    try:
        # Lock SPI bus
        while not spi.try_lock():
            pass
        
        # Configure for MAX31865 (Mode 1: CPOL=0, CPHA=1)
        spi.configure(baudrate=1000000, polarity=0, phase=1)
        print("SPI configured with: 1MHz, CPOL=0, CPHA=1 (Mode 1)")
    finally:
        # Unlock SPI bus
        spi.unlock()
    
    cs = digitalio.DigitalInOut(board.D8)  # GPIO8
    cs.direction = digitalio.Direction.OUTPUT
    cs.value = True  # Deselect initially
    
    # Add reset before configuration
    reset_max31865(spi, cs)
    
    # Configure the sensor
    configure_sensor(spi, cs, wires=2)  # Change to 3 for 3-wire mode if needed
    
    # Read and display fault status
    fault_status, faults = read_fault_status(spi, cs)
    if faults:
        print(f"WARNING: Faults detected: {', '.join(faults)}")
    else:
        print("No faults detected initially.")
    
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
            fault_status, faults = read_fault_status(spi, cs)
            
            # Display results
            print(f"RTD Value: {rtd_value}, Resistance: {resistance:.2f} ohms")
            if temp is not None:
                print(f"Temperature: {temp:.2f}°C")
            else:
                print("Temperature: Invalid reading")
            
            if faults:
                print(f"FAULTS: {', '.join(faults)}")
            
            print("-" * 40)
            
            # Wait before next reading
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nTest script terminated by user.")

if __name__ == "__main__":
    main()
