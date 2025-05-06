import asyncio
import time
import smbus2 # Added for I2C
import logging # Added for logging
from ..hal.o2_sensor import DFRobot_Oxygen_IIC, ADDRESS_0 # Import new HAL class and address
from ..hal.relay_output import RelayOutput
from .base_loop import BaseLoop # Import BaseLoop
# Forward declaration for type hinting
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .manager import ControlManager

class O2Loop(BaseLoop): # Inherit from BaseLoop
    """
    Manages the O2 control loop using simple threshold control.
    Reads O2 concentration from a DFRobot I2C sensor and controls an Argon valve relay
    to displace O2 when the level is too high. Handles sensor connection errors.
    """
    # Note: This sensor uses I2C (SDA/SCL pins), not direct GPIO pins for data.
    # The smbus2 library handles the I2C communication.

    def __init__(self,
                 manager: 'ControlManager', # Add manager argument
                 # o2_sensor parameter removed, we instantiate it here
                 argon_valve_relay: RelayOutput,
                 enabled_attr: str, # Accept the enabled attribute name
                 setpoint: float = 5.0, # Target O2 percentage (Argon ON if O2 > setpoint)
                 sample_time: float = 5.0, # Control loop interval in seconds
                 i2c_bus: int = 1, # Default I2C bus for RPi
                 i2c_address: int = ADDRESS_0 # Default address (0x70)
                ):
        """
        Initializes the O2 control loop.

        Args:
            manager: The ControlManager instance.
            argon_valve_relay: Instance of RelayOutput for the Argon valve.
            enabled_attr: The attribute name in the manager for the enabled state.
            setpoint: The target O2 percentage. Argon valve opens if O2 > setpoint.
            sample_time: How often the control loop runs (seconds).
            i2c_bus: The I2C bus number (default 1 for Raspberry Pi).
            i2c_address: The I2C address of the sensor (default ADDRESS_0=0x70).
                         Can be ADDRESS_1 (0x71), ADDRESS_2 (0x72), ADDRESS_3 (0x73).
        """
        # Call BaseLoop constructor, passing the manager, interval, and enabled_attr
        super().__init__(manager=manager, control_interval=sample_time, enabled_attr=enabled_attr)

        self.logger = manager.logger.getChild("O2Loop") # Get a child logger
        self.logger.info("Initializing O2Loop...")

        self.argon_valve_relay = argon_valve_relay
        self._setpoint = setpoint
        # self._sample_time = sample_time # Handled by BaseLoop

        self.sensor: DFRobot_Oxygen_IIC | None = None # Sensor instance or None if init fails
        self.current_value: float | str = "NC" # Current O2 value (float or "NC" string)
        self._argon_valve_on: bool = False
        # self._last_update_time: float = 0 # Handled by BaseLoop timing
        # self._active = True # Replaced by BaseLoop._is_running and _stop_event

        # --- Initialize Sensor ---
        try:
            # Use smbus2 for I2C communication
            bus = smbus2.SMBus(i2c_bus)
            self.logger.info(f"Attempting to initialize DFRobot_Oxygen_IIC on bus {i2c_bus}, address {hex(i2c_address)}")
            self.sensor = DFRobot_Oxygen_IIC(bus, i2c_address, logger_parent=self.logger) # Pass logger
            # Optional: Perform an initial calibration or check if needed here
            # self.sensor.calibrate(...)
            self.logger.info(f"DFRobot I2C O2 Sensor initialized successfully.")
            # Perform an initial measurement to populate current_value
            self._measure()
            self.logger.info(f"O2Loop initialized. Initial O2: {self.current_value}%, Setpoint: > {self._setpoint}% triggers Argon")

        except (IOError, FileNotFoundError) as e:
            self.logger.error(f"Error initializing DFRobot I2C O2 Sensor on bus {i2c_bus}, address {hex(i2c_address)}: {e}", exc_info=True)
            self.logger.warning("O2 control loop will run, but O2 readings will be 'NC'.")
            self.sensor = None
            self.current_value = "NC" # Ensure state reflects the error
        except Exception as e: # Catch any other unexpected errors during init
            self.logger.error(f"Unexpected error initializing O2 sensor: {e}", exc_info=True)
            self.sensor = None
            self.current_value = "NC"

        # No initial _read_sensor() call needed here anymore

    def _measure(self):
        """Reads the sensor and updates the internal O2 state (self.current_value)."""
        if self.sensor:
            try:
                # Get smoothed data using the HAL method
                self.logger.debug("Attempting to read O2 sensor data.")
                o2_level = self.sensor.get_oxygen_data(collect_num=10)
                self.current_value = o2_level # Store float or "NC" string
                self.logger.debug(f"O2 sensor read: {self.current_value}")
            except Exception as e:
                # Catch potential errors during read, though HAL should handle IOErrors
                self.logger.error(f"Error reading O2 sensor: {e}", exc_info=True)
                self.current_value = "NC"
        else:
            # Sensor failed to initialize
            self.logger.warning("O2 sensor not initialized. Cannot read value.")
            self.current_value = "NC"

    async def control_step(self):
        """Reads sensor, applies threshold logic, and updates the Argon valve relay state."""
        self._measure() # Read sensor first, updates self.current_value
        last_activation_time = getattr(self, "_last_activation_time", None)
        current_time = time.monotonic()

        # 1. Check Sensor Status
        if self.current_value == "NC":
            self.logger.warning("O2 sensor reading 'NC'. Ensuring Argon valve is OFF for safety.")
            self._ensure_actuator_off() # Ensure valve is off
            return

        # --- Convert to float *after* checking for "NC" ---
        try:
            current_o2_float = float(self.current_value)
        except ValueError:
            # Should not happen if HAL returns float or "NC", but good safeguard
            self.logger.error(f"Could not convert O2 value '{self.current_value}' to float. Turning Argon OFF.", exc_info=True)
            self._ensure_actuator_off() # Ensure valve is off
            return

        # --- Control logic proceeds only if BaseLoop determined the loop is active ---
        # This check is implicitly handled by the BaseLoop.run() method calling this function only when _active() is true.
        # However, we double-check sensor status above.

        # 2. Determine desired valve state based on Threshold Logic
        # Turn Argon ON if O2 is strictly greater than setpoint
        should_be_on = current_o2_float > self._setpoint

        # 3. Update Relay only if state needs to change
        if should_be_on and (last_activation_time is None or current_time - last_activation_time >= 60):
            self.logger.info(f"Turning Argon Valve ON for 0.1s (O2: {current_o2_float:.2f}% > Setpoint: {self._setpoint:.1f}%)")
            self.argon_valve_relay.on()
            self._argon_valve_on = True # Set state immediately
            await asyncio.sleep(0.1)
            self.argon_valve_relay.off()
            # self._argon_valve_on = False # State is OFF after sleep, but it *was* on
            self._last_activation_time = current_time
        elif not should_be_on and self._argon_valve_on:
            self.logger.info(f"Turning Argon Valve OFF (O2: {current_o2_float:.2f}% <= Setpoint: {self._setpoint:.1f}%)")
            self.argon_valve_relay.off()
            self._argon_valve_on = False
        # else: No change needed
        self.logger.debug(f"O2 control step. Current: {current_o2_float:.2f}%, Setpoint: {self._setpoint}%, Argon Valve Should Be: {should_be_on}, Is: {self._argon_valve_on}")

    def _ensure_actuator_off(self):
        """Turns the argon valve relay off."""
        if self.argon_valve_relay and self._argon_valve_on: # Check if it *was* on
            self.logger.info("O2 loop inactive or error: Ensuring Argon valve is OFF.")
            self.argon_valve_relay.off()
            self._argon_valve_on = False

    # Remove the custom run() method, BaseLoop provides it.
    # async def run(self): ...

    async def stop(self):
        """Stops the loop and ensures the Argon valve is turned off."""
        # Call BaseLoop's stop first
        await super().stop()
        # Ensure Argon valve is off as a final step
        if self.argon_valve_relay and self._argon_valve_on: # Check if it *was* on
             self.logger.info("O2Loop stopping: Ensuring Argon valve is OFF.")
             self.argon_valve_relay.off()
             self._argon_valve_on = False
        # No need to print "stopped" here, BaseLoop does it.

    # Change update_setpoint to a setter property
    @property
    def setpoint(self) -> float:
        """Returns the current O2 threshold setpoint."""
        return self._setpoint

    @setpoint.setter
    def setpoint(self, new_setpoint: float):
        """Updates the target O2 threshold."""
        try:
            new_setpoint = float(new_setpoint)
            # Add reasonable bounds check if necessary (e.g., 0-100)
            if 0 <= new_setpoint <= 100:
                self._setpoint = new_setpoint
                self.logger.info(f"O2 setpoint (threshold) updated to: {self._setpoint}%. Argon ON if O2 > {self._setpoint}%.")
            else:
                 self.logger.error(f"Invalid O2 setpoint value: {new_setpoint}. Must be between 0 and 100.")
        except ValueError:
            self.logger.error(f"Invalid O2 setpoint value: {new_setpoint}", exc_info=True)

    @property
    def current_o2(self) -> float | str: # Return type updated
        """Returns the last read O2 concentration (float) or 'NC' (string)."""
        return self.current_value # Return the unified value

    # Keep argon_valve_is_on property
    @property
    def argon_valve_is_on(self) -> bool:
        """Returns True if the Argon valve relay is currently commanded ON."""
        # The BaseLoop ensures this is only True when the loop is active and commanded ON.
        return self._argon_valve_on

    def get_status(self) -> dict:
        """Returns the current status of the O2 loop."""
        return {
            "o2": self.current_value, # Changed key to 'o2' to match manager/logger expectation
            "setpoint": self.setpoint,
            "argon_valve_on": self.argon_valve_is_on, # Use property which checks incubator_running
            "control_interval_s": self.control_interval
        }

    # Remove close() and __del__(), rely on manager calling stop() and closing relays
    # def close(self): ...
    # def __del__(self): ...

# Example Usage (Conceptual - requires running within an asyncio loop)
# async def main():
#     from ..hal.relay_output import RelayOutput
#     from ..hal.o2_sensor import DFRobotO2Sensor # Assuming this works
#     # Need a dummy manager for example
#     class DummyManager: incubator_running = True
#     manager = DummyManager()
#
#     ARGON_VALVE_PIN = 23
#     # Assuming DFRobotO2Sensor can be instantiated without errors
#     try:
#         sensor = DFRobotO2Sensor()
#         relay = RelayOutput(ARGON_VALVE_PIN)
#
#         # Example: Target O2 level below 10%
#         # Pass the dummy manager to the constructor
#         loop = O2Loop(manager=manager, o2_sensor=sensor, argon_valve_relay=relay, setpoint=10.0, sample_time=5)
#
#         run_task = asyncio.create_task(loop.run())
#
#         # Simulate running for a while
#         await asyncio.sleep(15)
#         loop.setpoint = 5.0 # Lower the threshold
#         await asyncio.sleep(5)
#         print("Simulating incubator stop...")
#         manager.incubator_running = False # Stop the incubator
#         await asyncio.sleep(5) # See if valve turns off
#         print("Simulating incubator start...")
#         manager.incubator_running = True # Start again
#         await asyncio.sleep(5)
#
#         await loop.stop() # Stop the loop task itself
#         await run_task # Wait for loop to finish cleanly
#         relay.close() # Explicitly close relay if needed
#         sensor.close()
#
#     except Exception as e:
#         print(f"Error during O2 loop example: {e}")
#         print("Ensure sensor and relay can be initialized.")
#
# if __name__ == '__main__':
#      asyncio.run(main())