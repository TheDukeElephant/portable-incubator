import asyncio
import logging
import time
import json
import os
import threading # Added for lock
import board # Added for MAX31865
import busio # Added for MAX31865
import digitalio # Added for MAX31865
from typing import Dict, Any, Optional, List

# Hardware Abstraction Layer Imports
from ..hal.dht_sensor import DHT22Sensor
from ..hal.max31865_sensor import MAX31865_Hub # Changed to MAX31865_Hub
from ..hal.o2_sensor import DFRobot_Oxygen_IIC
from ..hal.relay_output import RelayOutput
# from ..hal.co2_sensor import CO2Sensor # Import the new dummy sensor # TEMP DISABLED

# Control Loop Imports
from .temperature import TemperatureLoop
from .humidity import HumidityLoop
from .o2 import O2Loop
from .co2 import CO2Loop # Import the new control loop
from .air_pump import AirPumpControlLoop # Import the air pump loop

# Data Logger Import
from ..datalogger import DataLogger

# --- Configuration ---
# GPIO Pins (BCM Mode)
DHT_PIN = 4
HEATER_PIN = 17
HUMIDIFIER_PIN = 27
ARGON_VALVE_PIN = 23
CO2_VENT_PIN = 24

def _resolve_board_pin(name: str):
    """Resolve a board pin by name from env-friendly strings.

    Accepts examples like: 'CE0', 'CE1', 'D5', 'D6', 'GPIO5', 'GPIO6'.
    Returns the corresponding board pin object or raises ValueError.
    """
    if not name:
        raise ValueError("Empty pin name")
    key = name.strip()
    # Normalize common forms
    if key.upper().startswith("GPIO"):
        # Convert GPIO5 -> D5
        num = key[4:]
        key = f"D{num}"
    # Try exact attribute on board (CE0, CE1, D5, etc.)
    attr = key
    # Ensure CE0/CE1 uppercased
    if key.upper() in ("CE0", "CE1"):
        attr = key.upper()
    try:
        return getattr(board, attr)
    except AttributeError as e:
        raise ValueError(f"Unknown board pin '{name}'. Try CE0/CE1 or D<number> or GPIO<number>.") from e

# MAX31865 Chip Select Pins (Board numbering via Blinka)
# Defaults use SPI0: CE0 (GPIO8, physical 24) and CE1 (GPIO7, physical 26)
# You can change these via environment variables MAX31865_CS1 and MAX31865_CS2,
# or to any free GPIOs (e.g., D5, D6) if CE1 has conflicts.
_cs1_env = os.getenv("MAX31865_CS1", "CE0")
_cs2_env = os.getenv("MAX31865_CS2", "CE1")
try:
    MAX31865_CS_PIN_1 = _resolve_board_pin(_cs1_env)
    MAX31865_CS_PIN_2 = _resolve_board_pin(_cs2_env)
except ValueError as _pin_err:
    # Fallback to CE0/CE1 if env vars invalid
    logging.getLogger(__name__).warning(f"Invalid MAX31865 CS env var: {_pin_err}. Falling back to CE0/CE1.")
    MAX31865_CS_PIN_1 = board.CE0
    MAX31865_CS_PIN_2 = board.CE1

# Serial Port Configuration
# Set to 'auto' to scan common ports and pick the first working one.
# Common options scanned: /dev/ttyUSB*, /dev/serial0, /dev/ttyAMA0, /dev/ttyS0
CO2_SENSOR_PORT = os.getenv('CO2_SENSOR_PORT', 'auto')

# I2C Configuration
O2_SENSOR_ADDR = 0x73

# Control Loop Settings
CONTROL_SAMPLE_TIME = 1.0 # seconds
LOGGING_INTERVAL = 1.0 # seconds

# Default Setpoints
DEFAULT_TEMP_SETPOINT = 37.0
DEFAULT_HUMIDITY_SETPOINT = 60.0
DEFAULT_O2_SETPOINT = 5.0
DEFAULT_CO2_SETPOINT = 1000.0

STATE_FILE_PATH = "app/state.json"

# PID / Hysteresis Parameters
TEMP_PID_P = 5.0
TEMP_PID_I = 0.1
TEMP_PID_D = 1.0
HUMIDITY_HYSTERESIS = 4.0

class ControlManager:
    _logger = logging.getLogger(__name__)
    """
    Orchestrates the initialization and execution of all hardware components,
    control loops, and data logging for the incubator.
    Control loops run continuously, but actuators are enabled/disabled
    based on the `incubator_running` state AND individual control enabled states.
    """
    def __init__(self, db_path: str = "incubator_log.db"):
        print("Initializing Control Manager...")
        self._db_path = db_path
        self._running_tasks: List[asyncio.Task] = []
        self._manager_active = False # Is the manager itself initialized and running tasks?
        self.incubator_running = False # Are the actuators allowed to run (global switch)?
        self._state_lock = threading.Lock() # Lock for state file access

        # --- NEW: Individual Control Enabled States ---
        self.temperature_enabled = True
        self.humidity_enabled = True
        self.o2_enabled = True
        self.co2_enabled = True
        self.air_pump_enabled = True # NEW: Add air pump enabled state
        # ---------------------------------------------

        # 1. Initialize HAL Components
        print("  Initializing HAL components...")
        self.dht_sensor = DHT22Sensor(DHT_PIN)
        self.dht_sensor.start_background_initialization()

        # Initialize MAX31865 Sensor Hub
        print("  Initializing MAX31865 sensor hub...")
        self.max31865_sensor_hub = None # Default to None
        try:
            # Initialize HAL Hub using parameters from the working example
            # CS Pins for Hub: board.CE0 (GPIO8) and board.CE1 (GPIO7)
            # Wires = 2
            # RTD Nominal = 100.0
            # Ref Resistor = 430.0
            self.max31865_sensor_hub = MAX31865_Hub(
                cs_pin_1=MAX31865_CS_PIN_1, # Configurable CS pin 1 (default CE0)
                cs_pin_2=MAX31865_CS_PIN_2, # Configurable CS pin 2 (default CE1)
                wires=2,
                rtd_nominal_resistance=100.0,
                ref_resistance=430.0
            )
            # The HAL class will log its own success/failure.
            print("  Attempted MAX31865_Hub HAL initialization.")
        except AttributeError as e:
            self._logger.error(f"Failed to initialize MAX31865_Hub: board.CE0 or board.CE1 not available. {e}. Temperature control will be disabled.")
            print(f"  Error: Failed to initialize MAX31865_Hub: board.CE0 or board.CE1 not available. {e}. Temperature control will be disabled.")
            self.max31865_sensor_hub = None # Ensure it's None on failure
        except Exception as e: # Catch other exceptions from HAL's __init__
            self._logger.warning(f"Failed to initialize MAX31865_Hub HAL: {e}. Temperature control will be degraded.")
            print(f"  Warning: Failed to initialize MAX31865_Hub HAL: {e}. Temperature control will be degraded.")
            self.max31865_sensor_hub = None # Ensure it's None on failure

        # self.o2_sensor = DFRobot_Oxygen_IIC(bus=1, addr=O2_SENSOR_ADDR) # O2Loop will instantiate its own sensor
        # Use the CO2_SENSOR_PORT constant defined above
        # self.co2_sensor = CO2Sensor(url=CO2_SENSOR_PORT) # TEMP DISABLED

        self.heater_relay = RelayOutput(HEATER_PIN, initial_value=False)
        self.humidifier_relay = RelayOutput(HUMIDIFIER_PIN, initial_value=False)
        self.argon_valve_relay = RelayOutput(ARGON_VALVE_PIN, initial_value=False)
        # Vent relay is initialized within CO2Loop

        # 2. Initialize Control Loops (Pass self as manager)
        print("  Initializing Control Loops...")
        self.temp_loop = TemperatureLoop(
            manager=self, # Pass manager instance
            temp_sensor=self.max31865_sensor_hub, # Pass the sensor hub
            heater_relay=self.heater_relay,
            setpoint=DEFAULT_TEMP_SETPOINT,
            p=TEMP_PID_P, i=TEMP_PID_I, d=TEMP_PID_D,
            sample_time=CONTROL_SAMPLE_TIME,
            enabled_attr="temperature_enabled" # Pass the enabled attribute name
        )
        self.humidity_loop = HumidityLoop(
            manager=self, # Pass manager instance
            humidity_sensor=self.dht_sensor,
            humidifier_relay=self.humidifier_relay,
            setpoint=DEFAULT_HUMIDITY_SETPOINT,
            hysteresis=HUMIDITY_HYSTERESIS,
            sample_time=CONTROL_SAMPLE_TIME,
            enabled_attr="humidity_enabled" # Pass the enabled attribute name
        )
        self.o2_loop = O2Loop(
            manager=self, # Pass manager instance
            argon_valve_relay=self.argon_valve_relay,
            setpoint=DEFAULT_O2_SETPOINT,
            sample_time=CONTROL_SAMPLE_TIME,
            i2c_bus=1, # Explicitly pass bus number
            i2c_address=O2_SENSOR_ADDR, # Pass the correct address 0x73
            enabled_attr="o2_enabled" # Pass the enabled attribute name
        )
        self.co2_loop = CO2Loop(
            manager=self, # Pass manager instance
            co2_sensor_port=CO2_SENSOR_PORT, # Pass the configured sensor port
            vent_relay_pin=CO2_VENT_PIN,
            enabled_attr="co2_enabled", # Pass the enabled attribute name
            setpoint=DEFAULT_CO2_SETPOINT
        )
        self.air_pump_loop = AirPumpControlLoop(
            manager=self, # Pass manager instance (required by BaseLoop)
            control_interval=1.0, # Use control_interval instead of interval_sec
            enabled_attr="air_pump_enabled" # Pass the enabled attribute name
        )

        # 3. Initialize Data Logger
        print("  Initializing Data Logger...")
        self.logger = DataLogger(db_path=self._db_path)

        print("Control Manager Initialized (Loops not started yet).")

        # Load initial state from file (will load enabled states too)
        self._load_state()


    def _save_state(self, state=None):
        """
        Saves the current state to a JSON file.
        If state is provided, uses that; otherwise builds state from current attributes.
        """
        if state is None:
            # Build state from current attributes if not provided
            state = {
                'temp_setpoint': self.temp_loop.setpoint,
                'humidity_setpoint': self.humidity_loop.setpoint,
                'o2_setpoint': self.o2_loop.setpoint,
                'co2_setpoint': self.co2_loop.setpoint if hasattr(self, 'co2_loop') else DEFAULT_CO2_SETPOINT,
                'incubator_running': self.incubator_running,
                'temperature_enabled': self.temperature_enabled,
                'humidity_enabled': self.humidity_enabled,
                'o2_enabled': self.o2_enabled,
                'co2_enabled': self.co2_enabled,
                'air_pump_enabled': self.air_pump_enabled,
            }
        
        try:
            with open(STATE_FILE_PATH, 'w') as f:
                json.dump(state, f, indent=2)
            self._logger.info(f"State saved to {STATE_FILE_PATH}")
        except Exception as e:
            self._logger.error(f"Error saving state to {STATE_FILE_PATH}: {e}")

    def _load_state(self) -> Dict[str, Any]:
        """
        Loads state from JSON file, applies it to the manager/loops,
        and returns the loaded state dictionary (or defaults).
        """
        default_state = {
            'temp_setpoint': DEFAULT_TEMP_SETPOINT,
            'humidity_setpoint': DEFAULT_HUMIDITY_SETPOINT,
            'o2_setpoint': DEFAULT_O2_SETPOINT,
            'co2_setpoint': DEFAULT_CO2_SETPOINT,
            'incubator_running': False,
            'temperature_enabled': True,
            'humidity_enabled': True,
            'o2_enabled': True,
            'co2_enabled': True,
            'air_pump_enabled': True, # NEW: Add default for air pump
        }
        loaded_state = default_state.copy() # Start with defaults

        with self._state_lock: # Acquire lock before accessing/reading state
            if not os.path.exists(STATE_FILE_PATH):
                print(f"State file {STATE_FILE_PATH} not found. Using default values.")
                # Apply defaults to self attributes
                self._apply_state_to_self(default_state)
                return default_state # Return defaults

            try:
                with open(STATE_FILE_PATH, 'r') as f:
                    state_from_file = json.load(f)

                if isinstance(state_from_file, dict):
                    # Update defaults with values from file, ensuring all keys exist
                    loaded_state.update(state_from_file)
                    print(f"Loading state from {STATE_FILE_PATH}: {loaded_state}")
                    # Apply the merged state to self attributes
                    self._apply_state_to_self(loaded_state)
                    print("Successfully applied loaded state.")
                else:
                    print(f"Invalid state format in {STATE_FILE_PATH}. Using default values.")
                    self._apply_state_to_self(default_state) # Apply defaults to self
                    loaded_state = default_state # Ensure we return defaults

            except (IOError, json.JSONDecodeError) as e:
                print(f"Error loading state from {STATE_FILE_PATH}: {e}. Using default values.")
                self._apply_state_to_self(default_state) # Apply defaults to self
                loaded_state = default_state # Ensure we return defaults
            except Exception as e:
                print(f"Unexpected error loading state: {e}. Using default values.")
                self._apply_state_to_self(default_state) # Apply defaults to self
                loaded_state = default_state # Ensure we return defaults

        return loaded_state # Return the state dictionary that was applied

    def _apply_state_to_self(self, state: Dict[str, Any]):
        """Applies values from a state dictionary to the manager's attributes and loops."""
        # Apply setpoints (handle potential type errors)
        try:
            self.temp_loop.setpoint = float(state.get('temp_setpoint', DEFAULT_TEMP_SETPOINT))
            self.humidity_loop.setpoint = float(state.get('humidity_setpoint', DEFAULT_HUMIDITY_SETPOINT))
            self.o2_loop.setpoint = float(state.get('o2_setpoint', DEFAULT_O2_SETPOINT))
            self.co2_loop.setpoint = float(state.get('co2_setpoint', DEFAULT_CO2_SETPOINT))
        except (ValueError, TypeError) as e:
             self._logger.warning(f"Error applying setpoints from state: {e}. Using defaults.") # Use logger
             self.temp_loop.setpoint = DEFAULT_TEMP_SETPOINT
             self.humidity_loop.setpoint = DEFAULT_HUMIDITY_SETPOINT
             self.o2_loop.setpoint = DEFAULT_O2_SETPOINT
             # self.co2_loop.setpoint = DEFAULT_CO2_SETPOINT # TEMP DISABLED

        # Apply running state
        self.incubator_running = bool(state.get('incubator_running', False))

        # Apply enabled states
        self.temperature_enabled = bool(state.get('temperature_enabled', True))
        self.humidity_enabled = bool(state.get('humidity_enabled', True))
        self.o2_enabled = bool(state.get('o2_enabled', True))
        self.co2_enabled = bool(state.get('co2_enabled', True))
        self.air_pump_enabled = bool(state.get('air_pump_enabled', True)) # NEW: Apply air pump state


    def _apply_default_enabled_states(self):
            """Resets enabled states to their default values (True)."""
            print("Applying default enabled states.")
            self.temperature_enabled = True
            self.humidity_enabled = True
            self.o2_enabled = True
            self.co2_enabled = True
            self.air_pump_enabled = True # NEW: Reset air pump state
            # Note: This doesn't reset setpoints or incubator_running state, only the enabled flags.

    async def _logging_task(self):
        """Background task to periodically log data."""
        print("Data logging task started.")
        while self._manager_active: # Keep task alive while manager is active
                try:
                    # Log data regardless of incubator_running state, but log the state itself
                    status = self.get_status() # Get full status including enabled states

                    # Round temperature before creating the log dictionary
                    raw_temp = status.get('temperature')
                    logged_temp = round(raw_temp, 2) if isinstance(raw_temp, (int, float)) else raw_temp

                    log_data = {
                        'incubator_running': status.get('incubator_running'),
                        # --- NEW: Log Enabled States ---
                        'temperature_enabled': status.get('temperature_enabled'),
                        'humidity_enabled': status.get('humidity_enabled'),
                        'o2_enabled': status.get('o2_enabled'),
                        'co2_enabled': status.get('co2_enabled'),
                        'air_pump_enabled': status.get('air_pump_enabled'), # NEW: Log air pump enabled state
                        # ---------------------------------
                        'temperature': logged_temp, # Use the rounded value
                        'humidity': status.get('humidity'),
                        'o2': status.get('o2'),
                        'co2': status.get('co2_ppm'), # Key will be adjusted below
                        'temp_setpoint': status.get('temp_setpoint'),
                        'humidity_setpoint': status.get('humidity_setpoint'),
                        'o2_setpoint': status.get('o2_setpoint'),
                        'co2_setpoint': status.get('co2_setpoint_ppm'), # Key will be adjusted below
                        # Log actuator states as reported by loops (which consider incubator_running AND enabled flags)
                        'heater_on': status.get('heater_on'),
                        'humidifier_on': status.get('humidifier_on'),
                        'argon_valve_on': status.get('argon_valve_on'),
                        # 'vent_active': status.get('vent_active'), # TEMP DISABLED
                        'air_pump_on': status.get('air_pump_on'),
                        'air_pump_speed': status.get('air_pump_speed'),
                    }
                    # Adjust keys to match DataLogger expectations
                    log_data['co2'] = status.get('co2_ppm') # Use 'co2' key
                    log_data['co2_setpoint'] = status.get('co2_setpoint_ppm') # Use 'co2_setpoint' key
                    await self.logger.log_data(log_data)
                    # print("Logged data point.") # Debugging

                    # Wait for the next logging interval
                    await asyncio.sleep(LOGGING_INTERVAL)

                except asyncio.CancelledError:
                    print("Logging task cancelled.")
                    break
                except Exception as e:
                    print(f"Error in logging task: {e}")
                    # Avoid crashing the logger task, wait and retry if manager still active
                    if self._manager_active:
                        await asyncio.sleep(LOGGING_INTERVAL / 2)

        print("Data logging task stopped.")


    async def start(self):
        """Initializes logger, starts all control loops and the logging task."""
        print("ControlManager: Starting background tasks...")
        if self._manager_active:
            print("ControlManager: Already started.")
            return

        try:
            # 1. Initialize Logger DB Connection
            print("  Initializing logger database connection...")
            await self.logger.initialize()
            print("  Logger database initialized.")

            # 2. Mark manager as active *before* starting tasks
            self._manager_active = True
            print("  Manager marked as active.")

            # 3. Start Control Loops and Logging Task
            print("  Starting control loops and logging task...")
            self._running_tasks = [
                asyncio.create_task(self.temp_loop.run(), name="TempLoop"),
                asyncio.create_task(self.humidity_loop.run(), name="HumidityLoop"),
                asyncio.create_task(self.o2_loop.run(), name="O2Loop"),
                asyncio.create_task(self.co2_loop.run(), name="CO2Loop"),
                asyncio.create_task(self.air_pump_loop.run(), name="AirPumpLoop"),
                asyncio.create_task(self._logging_task(), name="LoggingTask")
            ]
            print(f"  {len(self._running_tasks)} background tasks created.")

            # Short delay to allow tasks to start up and potentially fail early
            await asyncio.sleep(0.1)

            # Check if any tasks failed immediately
            for task in self._running_tasks:
                if task.done() and task.exception():
                    raise task.exception() # Raise the exception from the failed task

            print("ControlManager: All background tasks started successfully.")

        except Exception as e:
            print(f"ControlManager: Error during startup: {e}")
            self._manager_active = False # Ensure manager is marked inactive on startup failure
            # Attempt cleanup
            print("ControlManager: Attempting cleanup after startup failure...")
            await self._cleanup_after_failure()
            # Re-raise the exception so the caller knows startup failed
            raise

    async def _cleanup_after_failure(self):
        """Performs cleanup tasks after a failure during startup or normal stop."""
        print("ControlManager: Running cleanup...")
        # Ensure actuators are off
        await self.stop_incubator(force_off=True)

        # Stop any potentially running tasks (even if startup failed partway)
        tasks_to_cancel = list(self._running_tasks) # Use the stored list
        self._running_tasks = [] # Clear the list

        for task in tasks_to_cancel:
             if task and not task.done():
                 task.cancel()
        if tasks_to_cancel:
             print(f"  Waiting for {len(tasks_to_cancel)} tasks to cancel...")
             await asyncio.gather(*[t for t in tasks_to_cancel if t], return_exceptions=True)
             print("  Tasks cancelled.")

        # Clean up HAL components (ensure this is safe even if not fully initialized)
        print("  Closing HAL components...")
        if hasattr(self, 'heater_relay'): self.heater_relay.close()
        if hasattr(self, 'humidifier_relay'): self.humidifier_relay.close()
        if hasattr(self, 'argon_valve_relay'): self.argon_valve_relay.close()
        # if hasattr(self, 'co2_loop') and self.co2_loop.vent_relay: self.co2_loop.vent_relay.close() # TEMP DISABLED
        # if hasattr(self, 'o2_sensor'): self.o2_sensor.close() # O2Loop handles its sensor lifecycle
        # DHT sensor and dummy CO2 sensor don't have close methods

        # Close logger connection if it was initialized
        if hasattr(self, 'logger') and self.logger.is_initialized():
             print("  Closing logger database connection...")
             await self.logger.close()
             print("  Logger closed.")
        print("ControlManager: Cleanup finished.")

    async def stop(self):
            """Stops all background tasks, cleans up HAL, and closes logger."""
            if not self._manager_active:
                print("Control Manager already stopped or not initialized.")
                return

            print("Stopping Control Manager...")
            self._manager_active = False # Signal logger and loops to stop checking state
            # self.incubator_running = False # Don't force incubator off on manager stop, preserve state
            await self.stop_incubator(force_off=True) # Ensure actuators are off when manager stops

            # Stop control loops (calls their internal stop methods)
            # These tasks should exit gracefully now that _manager_active is False in BaseLoop check
            await self.temp_loop.stop()
            await self.humidity_loop.stop()
            await self.o2_loop.stop()
            # await self.co2_loop.stop() # TEMP DISABLED
            await self.air_pump_loop.stop() # Stop the air pump loop

            # Cancel all running tasks gracefully (includes logger)
            tasks_to_cancel = list(self._running_tasks)
            self._running_tasks = []

            for task in tasks_to_cancel:
                if task and not task.done():
                    task.cancel()

            # Wait for tasks to finish cancellation
            if tasks_to_cancel:
                try:
                    await asyncio.gather(*[t for t in tasks_to_cancel if t], return_exceptions=True)
                    print("All background tasks finished or cancelled.")
                except asyncio.CancelledError:
                     print("Gather cancelled (expected during shutdown).")
                except Exception as e:
                     print(f"Error during task gathering on stop: {e}")

            # Clean up HAL components
            print("Closing HAL components...")
            self.heater_relay.close()
            self.humidifier_relay.close()
            self.argon_valve_relay.close()
            # if hasattr(self, 'co2_loop') and self.co2_loop.vent_relay: # TEMP DISABLED
            #      self.co2_loop.vent_relay.close() # TEMP DISABLED
            # self.o2_sensor.close() # O2Loop handles its sensor lifecycle
            # DHT sensor and dummy CO2 sensor don't have close methods

            # Close logger connection
            await self.logger.close()

            print("Control Manager fully stopped.")


    async def start_incubator(self):
        """Allows actuators to run based on control loop logic and enabled flags."""
        if not self._manager_active:
            print("Cannot start incubator: Manager not active.")
            return
        if self.incubator_running:
            print("Incubator already running.")
            return

        print("Starting Incubator (enabling actuators)...")
        self.incubator_running = True
        # Ensure individual control states are respected
        if not self.temperature_enabled:
            self.heater_relay.off()
        if not self.humidity_enabled:
            self.humidifier_relay.off()
        if not self.o2_enabled:
            self.argon_valve_relay.off()
        # if not self.co2_enabled and hasattr(self, 'co2_loop') and self.co2_loop.vent_relay: # TEMP DISABLED
        #     self.co2_loop.vent_relay.off() # TEMP DISABLED
            # Loops are already running, changing the flag enables control (if individually enabled)
            # self._save_state() # REMOVED: Don't save state on main toggle

    async def stop_incubator(self, force_off=False):
        """
        Disallows actuators from running, turning them off.
        If force_off is True, turns off actuators even if manager is stopping.
        """
        if not self._manager_active and not force_off:
            print("Cannot stop incubator: Manager not active.")
            return
        if not self.incubator_running and not force_off:
            # print("Incubator already stopped.") # Optional print
            return

        print("Stopping Incubator (disabling actuators)...")
        self.incubator_running = False
        # Ensure all actuators are turned off regardless of individual states
        self.heater_relay.off()
        self.humidifier_relay.off()
        self.argon_valve_relay.off()
        # if hasattr(self, 'co2_loop') and self.co2_loop.vent_relay: # TEMP DISABLED
        #     self.co2_loop.vent_relay.off() # TEMP DISABLED
        # if self._manager_active: # Only save state if manager is active # <-- Corrected Indent
        #      self._save_state() # REMOVED: Don't save state on main toggle # <-- Corrected Indent

        # Explicitly turn off all actuators immediately
        print("Ensuring actuators are off...") # <-- Corrected Indent
        self.heater_relay.off() # <-- Corrected Indent
        self.humidifier_relay.off() # <-- Corrected Indent
        self.argon_valve_relay.off() # <-- Corrected Indent
        # if hasattr(self, 'co2_loop') and self.co2_loop.vent_relay: # TEMP DISABLED # <-- Corrected Indent
        #     self.co2_loop.vent_relay.off() # TEMP DISABLED # <-- Corrected Indent
        if self.air_pump_loop and self.air_pump_loop.motor: # <-- Corrected Indent
            self.air_pump_loop.motor.stop() # Explicitly stop the pump motor # <-- Corrected Indent
        # Loops will continue running but won't activate relays while flag is False # <-- Corrected Indent


    def get_status(self) -> Dict[str, Any]:
            """Returns the current status of all sensors and control loops."""
            # Get status from each loop (which includes actuator state based on incubator_running)
            temp_status = self.temp_loop.get_status()
            hum_status = self.humidity_loop.get_status()
            o2_status = self.o2_loop.get_status()
            # co2_status = self.co2_loop.get_status() if hasattr(self, 'co2_loop') else {} # TEMP DISABLED
            air_pump_status = self.air_pump_loop.get_status() if hasattr(self, 'air_pump_loop') else {} # Get air pump status safely

            status = {
                "timestamp": time.time(),
                "incubator_running": self.incubator_running, # Report the overall state flag
                # --- NEW: Report Enabled States ---
                "temperature_enabled": self.temperature_enabled,
                "humidity_enabled": self.humidity_enabled,
                "o2_enabled": self.o2_enabled,
                "co2_enabled": self.co2_enabled,
                "air_pump_enabled": self.air_pump_enabled, # NEW: Report air pump enabled state
                # ---------------------------------
                # Updated temperature reporting for MAX31865_Hub
                "temperature_sensor1": temp_status.get("temperature_sensor1"),
                "temperature_sensor2": temp_status.get("temperature_sensor2"),
                "temperature": temp_status.get("temperature_average_control"), # For logging and general display
                "temp_setpoint": temp_status.get("setpoint"),
                "heater_on": temp_status.get("heater_on"), # This should reflect both flags via loop's property
                "humidity": hum_status.get("humidity"),
                "humidity_setpoint": hum_status.get("setpoint"),
                "humidifier_on": hum_status.get("humidifier_on"), # This should reflect both flags via loop's property
                "o2": o2_status.get("o2"),
                "o2_setpoint": o2_status.get("setpoint"),
                "argon_valve_on": o2_status.get("argon_valve_on"), # This should reflect both flags via loop's property
                "co2_ppm": self.co2_loop.current_co2 if hasattr(self, 'co2_loop') else None,
                "co2_setpoint_ppm": self.co2_loop.setpoint if hasattr(self, 'co2_loop') else None,
                "vent_active": self.co2_loop.is_vent_active if hasattr(self, 'co2_loop') else None,
                "air_pump_on": air_pump_status.get("pump_on", False),
                "air_pump_speed": air_pump_status.get("speed_percent", 0),
            }
            return status

    def update_setpoints(self, setpoints: Dict[str, float]):
            """
            Updates the setpoints for the control loops.
            """
            print(f"Updating setpoints: {setpoints}")
            changed = False
            try:
                if 'temperature' in setpoints and self.temp_loop.setpoint != float(setpoints['temperature']):
                    self.temp_loop.setpoint = float(setpoints['temperature'])
                    changed = True
                if 'humidity' in setpoints and self.humidity_loop.setpoint != float(setpoints['humidity']):
                    self.humidity_loop.setpoint = float(setpoints['humidity'])
                    changed = True
                if 'o2' in setpoints and self.o2_loop.setpoint != float(setpoints['o2']):
                    self.o2_loop.setpoint = float(setpoints['o2'])
                    changed = True
                if 'co2' in setpoints and hasattr(self, 'co2_loop') and self.co2_loop.setpoint != float(setpoints['co2']):
                    self.co2_loop.setpoint = float(setpoints['co2'])
                    changed = True
            except ValueError as e:
                print(f"Error updating setpoints: Invalid value type - {e}")
            except Exception as e:
                print(f"Unexpected error updating setpoints: {e}")
            finally:
                # Save state only if a value actually changed
                if changed:
                    # Construct the current state from self attributes to pass to save
                    current_state = {
                        'temp_setpoint': self.temp_loop.setpoint,
                        'humidity_setpoint': self.humidity_loop.setpoint,
                        'o2_setpoint': self.o2_loop.setpoint,
                        'co2_setpoint': self.co2_loop.setpoint if hasattr(self, 'co2_loop') else None,
                        'incubator_running': self.incubator_running,
                        'temperature_enabled': self.temperature_enabled,
                        'humidity_enabled': self.humidity_enabled,
                        'o2_enabled': self.o2_enabled,
                        'co2_enabled': self.co2_enabled,
                        'air_pump_enabled': self.air_pump_enabled, # NEW: Save air pump state
                    }
                    self._save_state(current_state)

    # --- NEW: Getter/Setter Methods for Enabled States ---
    def get_control_state(self, control_name: str) -> Optional[bool]:
            """Gets the enabled state of a specific control loop."""
            if control_name == "temperature":
                return self.temperature_enabled
            elif control_name == "humidity":
                return self.humidity_enabled
            elif control_name == "o2":
                return self.o2_enabled
            elif control_name == "co2":
                return self.co2_enabled
            elif control_name == "air_pump": # NEW: Get air pump state
                return self.air_pump_enabled
            else:
                print(f"Warning: Unknown control name '{control_name}' in get_control_state")
                return None

    def set_control_state(self, control_name: str, enabled: bool):
        """
        Sets the enabled state of a specific control loop.
        """
        control_key_map = {
            "temperature": "temperature_enabled",
            "humidity": "humidity_enabled",
            "o2": "o2_enabled",
            "co2": "co2_enabled",
            "air_pump": "air_pump_enabled",
        }

        if control_name not in control_key_map:
            print(f"Error: Unknown control name '{control_name}' in set_control_state")
            return

        state_key = control_key_map[control_name]

        # Log the requested change using the logger
        self._logger.info(f"Setting {control_name} to {enabled}")

        # Update the in-memory attribute for this specific control
        setattr(self, state_key, enabled)
        
        # If disabling a control, ensure its actuator is turned off
        if not enabled:
            if control_name == "temperature" and hasattr(self, "temp_loop"):
                self.temp_loop._ensure_actuator_off()
            elif control_name == "humidity" and hasattr(self, "humidity_loop"):
                self.humidity_loop._ensure_actuator_off()
            elif control_name == "o2" and hasattr(self, "o2_loop"):
                self.o2_loop._ensure_actuator_off()
            elif control_name == "air_pump" and hasattr(self, "air_pump_loop"):
                if hasattr(self.air_pump_loop, "reset_control"):
                    self.air_pump_loop.reset_control()
        
        # Save the current state to file
        try:
            current_state = {
                'temp_setpoint': self.temp_loop.setpoint,
                'humidity_setpoint': self.humidity_loop.setpoint,
                'o2_setpoint': self.o2_loop.setpoint,
                'co2_setpoint': self.co2_loop.setpoint if hasattr(self, 'co2_loop') else None, # Add CO2 setpoint
                'incubator_running': self.incubator_running,
                'temperature_enabled': self.temperature_enabled,
                'humidity_enabled': self.humidity_enabled,
                'o2_enabled': self.o2_enabled,
                'co2_enabled': self.co2_enabled, # Add CO2 enabled
                'air_pump_enabled': self.air_pump_enabled,
            }
            self._save_state(current_state)
        except Exception as e:
            self._logger.error(f"Error saving state: {e}")

    # ----------------------------------------------------
    # Corrected indentation for __aenter__ and __aexit__
    async def __aenter__(self):
        """Allows using 'async with ControlManager(...)' syntax."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ensures stop is called when exiting 'async with' block."""
        await self.stop()

    # Example Usage (Conceptual - requires running within an asyncio loop)
# async def main():
#     manager = ControlManager()
#     try:
#         await manager.start() # Initializes and starts loops (incubator initially stopped)
#         print("Manager started. Incubator initially STOPPED.")
#         await asyncio.sleep(5)
#         print("Current Status (Stopped):", manager.get_status())
#
#         print("\nStarting incubator (enabling actuators)...")
#         await manager.start_incubator()
#         await asyncio.sleep(10)
#         print("Current Status (Running):", manager.get_status())
#
#         print("\nUpdating setpoints...")
#         manager.update_setpoints({'temperature': 36.5, 'humidity': 58.0, 'o2': 6.0, 'co2': 950.0})
#         await asyncio.sleep(10)
#         print("Current Status (Running, New Setpoints):", manager.get_status())
#
#         print("\nStopping incubator (disabling actuators)...")
#         await manager.stop_incubator()
#         await asyncio.sleep(5)
#         print("Current Status (Stopped):", manager.get_status())
#
#     except Exception as e:
#         print(f"Error during manager example: {e}")
#     finally:
#         print("\nStopping manager completely...")
#         await manager.stop() # This stops manager tasks and cleans up everything
#         print("Manager example finished.")
#
# if __name__ == '__main__':
#      # Clean up test database if it exists
#      import os
#      if os.path.exists("incubator_log.db"): os.remove("incubator_log.db")
#
#      asyncio.run(main())
#
#      # Clean up again after run
#      if os.path.exists("incubator_log.db"): os.remove("incubator_log.db")
