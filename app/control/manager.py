import asyncio
import time
import json
import os
from typing import Dict, Any, Optional, List

# Hardware Abstraction Layer Imports
from ..hal.dht_sensor import DHT22Sensor
from ..hal.o2_sensor import DFRobot_Oxygen_IIC
from ..hal.relay_output import RelayOutput
from ..hal.co2_sensor import CO2Sensor # Import the new dummy sensor

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

# I2C Configuration
O2_SENSOR_ADDR = 0x73

# Control Loop Settings
CONTROL_SAMPLE_TIME = 5.0 # seconds
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
    """
    Orchestrates the initialization and execution of all hardware components,
    control loops, and data logging for the incubator.
    Control loops run continuously, but actuators are enabled/disabled
    based on the `incubator_running` state.
    """
    def __init__(self, db_path: str = "incubator_log.db"):
        print("Initializing Control Manager...")
        self._db_path = db_path
        self._running_tasks: List[asyncio.Task] = []
        self._manager_active = False # Is the manager itself initialized and running tasks?
        self.incubator_running = False # Are the actuators allowed to run?

        # 1. Initialize HAL Components
        print("  Initializing HAL components...")
        self.dht_sensor = DHT22Sensor(DHT_PIN)
        self.dht_sensor.start_background_initialization()
        self.o2_sensor = DFRobot_Oxygen_IIC(bus=1, addr=O2_SENSOR_ADDR) # Assuming bus 1, adjust if needed
        self.co2_sensor = CO2Sensor()

        self.heater_relay = RelayOutput(HEATER_PIN, initial_value=False)
        self.humidifier_relay = RelayOutput(HUMIDIFIER_PIN, initial_value=False)
        self.argon_valve_relay = RelayOutput(ARGON_VALVE_PIN, initial_value=False)
        # Vent relay is initialized within CO2Loop

        # 2. Initialize Control Loops (Pass self as manager)
        print("  Initializing Control Loops...")
        self.temp_loop = TemperatureLoop(
            manager=self, # Pass manager instance
            temp_sensor=self.dht_sensor,
            heater_relay=self.heater_relay,
            setpoint=DEFAULT_TEMP_SETPOINT,
            p=TEMP_PID_P, i=TEMP_PID_I, d=TEMP_PID_D,
            sample_time=CONTROL_SAMPLE_TIME
        )
        self.humidity_loop = HumidityLoop(
            manager=self, # Pass manager instance
            humidity_sensor=self.dht_sensor,
            humidifier_relay=self.humidifier_relay,
            setpoint=DEFAULT_HUMIDITY_SETPOINT,
            hysteresis=HUMIDITY_HYSTERESIS,
            sample_time=CONTROL_SAMPLE_TIME
        )
        self.o2_loop = O2Loop(
            manager=self, # Pass manager instance
            o2_sensor=self.o2_sensor,
            argon_valve_relay=self.argon_valve_relay,
            setpoint=DEFAULT_O2_SETPOINT,
            sample_time=CONTROL_SAMPLE_TIME
        )
        self.co2_loop = CO2Loop(
            manager=self, # Pass manager instance
            sensor=self.co2_sensor,
            vent_relay_pin=CO2_VENT_PIN,
            setpoint=DEFAULT_CO2_SETPOINT
        )
        self.air_pump_loop = AirPumpControlLoop(
            manager=self, # Pass manager instance (required by BaseLoop)
            control_interval=1.0 # Use control_interval instead of interval_sec
        )

        # 3. Initialize Data Logger
        print("  Initializing Data Logger...")
        self.logger = DataLogger(db_path=self._db_path)

        print("Control Manager Initialized (Loops not started yet).")

        # Load initial state from file
        self._load_state()


    def _save_state(self):
        """Saves the current setpoints and running state to a JSON file."""
        state = {
            'temp_setpoint': self.temp_loop.setpoint,
            'humidity_setpoint': self.humidity_loop.setpoint,
            'o2_setpoint': self.o2_loop.setpoint,
            'co2_setpoint': self.co2_loop.setpoint,
            'incubator_running': self.incubator_running,
        }
        try:
            with open(STATE_FILE_PATH, 'w') as f:
                json.dump(state, f, indent=4)
            # print(f"Saved state: {state}") # Debugging
        except IOError as e:
            print(f"Error saving state to {STATE_FILE_PATH}: {e}")
        except Exception as e:
            print(f"Unexpected error saving state: {e}")

    def _load_state(self):
        """Loads setpoints and running state from JSON file if it exists."""
        if not os.path.exists(STATE_FILE_PATH):
            print(f"State file {STATE_FILE_PATH} not found. Using default values.")
            # Ensure initial save reflects defaults if file doesn't exist
            self._save_state()
            return

        try:
            with open(STATE_FILE_PATH, 'r') as f:
                state = json.load(f)

            print(f"Loading state from {STATE_FILE_PATH}: {state}")

            # Apply loaded state only if keys exist and values are reasonable (basic check)
            if isinstance(state, dict):
                if 'temp_setpoint' in state and isinstance(state['temp_setpoint'], (int, float)):
                    self.temp_loop.setpoint = float(state['temp_setpoint'])
                if 'humidity_setpoint' in state and isinstance(state['humidity_setpoint'], (int, float)):
                    self.humidity_loop.setpoint = float(state['humidity_setpoint'])
                if 'o2_setpoint' in state and isinstance(state['o2_setpoint'], (int, float)):
                    self.o2_loop.setpoint = float(state['o2_setpoint'])
                if 'co2_setpoint' in state and isinstance(state['co2_setpoint'], (int, float)):
                    self.co2_loop.setpoint = float(state['co2_setpoint'])
                if 'incubator_running' in state and isinstance(state['incubator_running'], bool):
                     # Set the initial running state based on loaded value.
                     # The start() method will respect this initial state.
                     # Note: start() currently forces incubator_running=False initially,
                     # this loaded value might be overridden unless start() logic is adjusted.
                     # For now, we load it, but start() behavior takes precedence on initial startup.
                     # A better approach might be to pass this loaded state to start().
                     # Let's keep it simple for now and load it here. The user can then start it.
                     self.incubator_running = state['incubator_running']
                print("Successfully applied loaded state.")
            else:
                 print(f"Invalid state format in {STATE_FILE_PATH}. Using default values.")
                 # Save defaults if file was invalid
                 self._save_state()

        except (IOError, json.JSONDecodeError) as e:
            print(f"Error loading state from {STATE_FILE_PATH}: {e}. Using default values.")
            # Save defaults if file was corrupted
            self._save_state()
        except Exception as e:
            print(f"Unexpected error loading state: {e}. Using default values.")
            # Save defaults on unexpected error
            self._save_state()


    async def _logging_task(self):
        """Background task to periodically log data when the incubator is running."""
        print("Data logging task started.")
        while self._manager_active: # Keep task alive while manager is active
            try:
                # Log data regardless of incubator_running state, but log the state itself
                status = self.get_status() # Get full status including incubator_running
                log_data = {
                    'incubator_running': status.get('incubator_running'),
                    'temperature': status.get('temperature'),
                    'humidity': status.get('humidity'),
                    'o2': status.get('o2'),
                    'co2': status.get('co2_ppm'),
                    'temp_setpoint': status.get('temp_setpoint'),
                    'humidity_setpoint': status.get('humidity_setpoint'),
                    'o2_setpoint': status.get('o2_setpoint'),
                    'co2_setpoint': status.get('co2_setpoint_ppm'),
                    # Log actuator states as reported by loops (which consider incubator_running)
                    'heater_on': status.get('heater_on'),
                    'humidifier_on': status.get('humidifier_on'),
                    'argon_valve_on': status.get('argon_valve_on'),
                    'vent_active': status.get('vent_active'),
                    'air_pump_on': status.get('air_pump_on'), # Add air pump status
                    'air_pump_speed': status.get('air_pump_speed'), # Add air pump speed
                }
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
        if self._manager_active:
            print("Control Manager already started.")
            return

        print("Starting Control Manager and background tasks...")
        try:
            # Initialize logger database connection
            await self.logger.initialize()

            self._manager_active = True
            # Start control loops immediately. They will run but respect incubator_running flag.
            self._running_tasks = [
                asyncio.create_task(self.temp_loop.run(), name="TempLoop"),
                asyncio.create_task(self.humidity_loop.run(), name="HumidityLoop"),
                asyncio.create_task(self.o2_loop.run(), name="O2Loop"),
                asyncio.create_task(self.co2_loop.run(), name="CO2Loop"),
                asyncio.create_task(self.air_pump_loop.run(), name="AirPumpLoop"), # Add air pump loop task
                asyncio.create_task(self._logging_task(), name="LoggerTask") # Start logger task
            ]
            # Incubator starts in the 'stopped' state (actuators off)
            self.incubator_running = False
            print(f"Control Manager started with {len(self._running_tasks)} tasks. Incubator initially STOPPED.")

        except Exception as e:
            print(f"Error starting Control Manager: {e}")
            self._manager_active = False
            await self.logger.close() # Ensure logger is closed if init failed
            # Attempt cleanup if start failed partially
            await self.stop()
            raise # Re-raise the exception

    async def stop(self):
        """Stops all background tasks, cleans up HAL, and closes logger."""
        if not self._manager_active:
            print("Control Manager already stopped or not initialized.")
            return

        print("Stopping Control Manager...")
        self._manager_active = False # Signal logger and loops to stop checking state
        self.incubator_running = False # Ensure state is off

        # Stop control loops (calls their internal stop methods)
        # These tasks should exit gracefully now that _manager_active is False in BaseLoop check
        await self.temp_loop.stop()
        await self.humidity_loop.stop()
        await self.o2_loop.stop()
        await self.co2_loop.stop()
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
        if self.co2_loop.vent_relay:
             self.co2_loop.vent_relay.close()
        self.o2_sensor.close()
        # DHT sensor and dummy CO2 sensor don't have close methods

        # Close logger connection
        await self.logger.close()

        print("Control Manager fully stopped.")


    async def start_incubator(self):
        """Allows actuators to run based on control loop logic."""
        if not self._manager_active:
            print("Cannot start incubator: Manager not active.")
            return
        if self.incubator_running:
            print("Incubator already running.")
            return

        print("Starting Incubator (enabling actuators)...")
        self.incubator_running = True
        # Loops are already running, just changing the flag enables control
        self._save_state() # Save state after change

    async def stop_incubator(self):
        """Disallows actuators from running, turning them off."""
        if not self._manager_active:
            print("Cannot stop incubator: Manager not active.")
            return
        if not self.incubator_running:
            # print("Incubator already stopped.") # Optional print
            return

        print("Stopping Incubator (disabling actuators)...")
        self.incubator_running = False
        self._save_state() # Save state after change

        # Explicitly turn off all actuators immediately
        print("Ensuring actuators are off...")
        self.heater_relay.off()
        self.humidifier_relay.off()
        self.argon_valve_relay.off()
        if self.co2_loop.vent_relay:
            self.co2_loop.vent_relay.off()
        if self.air_pump_loop and self.air_pump_loop.motor:
            self.air_pump_loop.motor.stop() # Explicitly stop the pump motor
        # Loops will continue running but won't activate relays while flag is False


    def get_status(self) -> Dict[str, Any]:
        """Returns the current status of all sensors and control loops."""
        # Get status from each loop (which includes actuator state based on incubator_running)
        temp_status = self.temp_loop.get_status()
        hum_status = self.humidity_loop.get_status()
        o2_status = self.o2_loop.get_status()
        co2_status = self.co2_loop.get_status()
        air_pump_status = self.air_pump_loop.get_status() if hasattr(self, 'air_pump_loop') else {} # Get air pump status safely

        status = {
            "timestamp": time.time(),
            "incubator_running": self.incubator_running, # Report the overall state flag
            "temperature": temp_status.get("temperature"),
            "temp_setpoint": temp_status.get("setpoint"),
            "heater_on": temp_status.get("heater_on"), # This now reflects incubator_running via loop's property
            "humidity": hum_status.get("humidity"),
            "humidity_setpoint": hum_status.get("setpoint"),
            "humidifier_on": hum_status.get("humidifier_on"), # This now reflects incubator_running via loop's property
            "o2": o2_status.get("o2"),
            "o2_setpoint": o2_status.get("setpoint"),
            "argon_valve_on": o2_status.get("argon_valve_on"), # This now reflects incubator_running via loop's property
            "co2_ppm": co2_status.get("co2_ppm"),
            "co2_setpoint_ppm": co2_status.get("setpoint_ppm"),
            "vent_active": co2_status.get("vent_active"), # This now reflects incubator_running via loop's property
            "air_pump_on": air_pump_status.get("pump_on", False), # Add air pump status
            "air_pump_speed": air_pump_status.get("speed_percent", 0), # Add air pump speed
        }
        return status

    def update_setpoints(self, setpoints: Dict[str, float]):
        """
        Updates the setpoints for the control loops.
        """
        print(f"Updating setpoints: {setpoints}")
        try:
            if 'temperature' in setpoints:
                self.temp_loop.setpoint = float(setpoints['temperature'])
            if 'humidity' in setpoints:
                self.humidity_loop.setpoint = float(setpoints['humidity'])
            if 'o2' in setpoints:
                self.o2_loop.setpoint = float(setpoints['o2'])
            if 'co2' in setpoints:
                self.co2_loop.setpoint = float(setpoints['co2'])
        except ValueError as e:
            print(f"Error updating setpoints: Invalid value type - {e}")
        except Exception as e:
            print(f"Unexpected error updating setpoints: {e}")
        finally:
            # Save state regardless of errors in applying specific values
            self._save_state()

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