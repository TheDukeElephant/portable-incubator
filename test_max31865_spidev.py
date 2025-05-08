#!/usr/bin/env python3
"""
MAX31865 test using spidev library directly.
"""
import time
import spidev
import RPi.GPIO as GPIO

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

# Initialize GPIO
GPIO.setmode(GPIO.BCM)
CS_PIN = 8  # GPIO8 (pin 24)
GPIO.setup(CS_PIN, GPIO.OUT)
GPIO.output(CS_PIN, GPIO.HIGH)  # Deselect initially

# Initialize SPI
spi = spidev.SpiDev()
spi.open(0, 0)  # Bus 0, Device 0
spi.max_speed_hz = 500000  # Lower speed for reliability
spi.mode = 1  # CPOL=0, CPHA=1 (Mode 1)
spi.bits_per_word = 8

print("SPI initialized with:")
print(f"  Mode: {spi.mode}")
print(f"  Speed: {spi.max_speed_hz} Hz")
print(f"  Bits per word: {spi.bits_per_word}")
print(f"  LSB first: {spi.lsbfirst}")

def read_register(reg_addr):
    """Read a register from the MAX31865."""
    # Create read command (MSB=1 for read)
    read_cmd = [reg_addr | 0x80, 0x00]
    
    GPIO.output(CS_PIN, GPIO.LOW)  # Select chip
    time.sleep(0.001)  # Small delay
    
    result = spi.xfer2(read_cmd)
    
    GPIO.output(CS_PIN, GPIO.HIGH)  # Deselect chip
    time.sleep(0.001)  # Small delay
    
    return result[1]  # Return the data byte

def write_register(reg_addr, data):
    """Write to a register on the MAX31865."""
    # Create write command (MSB=0 for write)
    write_cmd = [reg_addr & 0x7F, data]
    
    GPIO.output(CS_PIN, GPIO.LOW)  # Select chip
    time.sleep(0.001)  # Small delay
    
    spi.xfer2(write_cmd)
    
    GPIO.output(CS_PIN, GPIO.HIGH)  # Deselect chip
    time.sleep(0.001)  # Small delay

def read_rtd_value():
    """Read the RTD value from the MAX31865."""
    # Read the RTD MSB and LSB registers
    msb = read_register(RTD_MSB_REG)
    lsb = read_register(RTD_LSB_REG)
    
    # Combine the bytes into a 16-bit value
    rtd_value = (msb << 8) | lsb
    
    # Check if the RTD value is valid (fault bit is LSB of LSB register)
    if lsb & 0x01:
        print("WARNING: Fault detected in RTD value")
    
    # Remove the fault bit
    rtd_value >>= 1
    
    return rtd_value

def read_fault_status():
    """Read the fault status register from the MAX31865."""
    fault_status = read_register(FAULT_STATUS_REG)
    
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

def configure_sensor(wires=2):
    """Configure the MAX31865 sensor."""
    # Reset first
    write_register(CONFIG_REG, 0x00)
    time.sleep(0.1)
    
    # Configure for 2-wire or 3-wire mode
    # BIAS_BIT: Enable bias voltage
    # CONVERSION_MODE_BIT: Enable auto conversion
    # THREE_WIRE_BIT: Set for 3-wire mode (omit for 2/4-wire)
    # FILTER_SELECT_BIT: 50Hz filter
    config = BIAS_BIT | CONVERSION_MODE_BIT | FILTER_SELECT_BIT
    
    if wires == 3:
        config |= THREE_WIRE_BIT
    
    write_register(CONFIG_REG, config)
    print(f"Configured MAX31865 with config byte: 0x{config:02X}")
    
    # Read back configuration to verify
    read_config = read_register(CONFIG_REG)
    print(f"Read back config: 0x{read_config:02X}")
    
    # Clear any existing faults
    fault_status, faults = read_fault_status()
    if faults:
        print(f"Clearing faults: {', '.join(faults)}")
        write_register(CONFIG_REG, config | FAULT_STATUS_CLEAR_BIT)

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
        print(f"ERROR: Resistance too low: {resistance} ohms - likely a short circuit")
        return None
    
    r_ratio = resistance / rtd_nominal
    
    # For very low temperatures or faults, r_ratio might be too low
    if r_ratio < 0.5:
        print(f"ERROR: R/R0 ratio too low: {r_ratio} - likely a fault or open circuit")
        return None
    
    # Calculate temperature
    try:
        c = 1 - r_ratio
        temp = (-A + (A**2 - 4*B*c)**0.5) / (2*B)
        return temp
    except Exception as e:
        print(f"ERROR: Error calculating temperature: {e}")
        return None

try:
    print("\nConfiguring MAX31865 sensor...")
    configure_sensor(wires=2)  # Change to 3 for 3-wire mode if needed
    
    print("\nStarting continuous reading (press Ctrl+C to exit):")
    while True:
        # Read RTD value
        rtd_value = read_rtd_value()
        
        # Calculate resistance
        resistance = (rtd_value * 430.0) / 32768.0
        
        # Calculate temperature
        temp = calculate_temperature(rtd_value)
        
        # Read fault status
        fault_status, faults = read_fault_status()
        
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
finally:
    # Clean up
    GPIO.output(CS_PIN, GPIO.HIGH)  # Ensure CS is deselected
    spi.close()
    GPIO.cleanup()