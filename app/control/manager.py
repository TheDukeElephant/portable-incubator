import asyncio
import time
from typing import Dict, Any, Optional, List

# Hardware Abstraction Layer Imports
from ..hal.dht_sensor import DHT22Sensor
from ..hal.o2_sensor import DFRobotO2Sensor
from ..hal.relay_output import RelayOutput
from ..hal.co2_sensor import CO2Sensor # Import the new dummy sensor

# Control Loop Imports
from .temperature import TemperatureLoop
from .humidity import HumidityLoop
from .o2 import O2Loop
from .co2 import CO2Loop # Import the new control loop

# Data Logger Import
from ..datalogger import DataLogger

# --- Configuration ---
# GPIO Pins (BCM Mode)
DHT_PIN = 4
HEATER_PIN = 17
HUMIDIFIER_PIN = 27
# CO2_VALVE_PIN = 22 # This seemed to be for adding CO2, replaced by vent control
ARGON_VALVE_PIN = 23
CO2_VENT_PIN = 24      # Pin for the CO2 vent relay, controlled by CO2Loop

# I2C Configuration
O2_SENSOR_ADDR = 0x73 # Default for DFRobot Gravity O2, confirm if different

# Control Loop Settings
CONTROL_SAMPLE_TIME = 5.0 # seconds
LOGGING_INTERVAL = 60.0 # seconds

# Default Setpoints
DEFAULT_TEMP_SETPOINT = 37.0
DEFAULT_HUMIDITY_SETPOINT = 60.0
DEFAULT_O2_SETPOINT = 5.0 # Target O2 level (Argon triggers if O2 > this)
DEFAULT_CO2_SETPOINT = 1000.0 # Default max CO2 level in ppm

# PID / Hysteresis Parameters
TEMP_PID_P = 5.0
TEMP_PID_I = 0.1
TEMP_PID_D = 1.0
HUMIDITY_HYSTERESIS = 4.0 # +/- 2.0% around setpoint

class ControlManager:
    """
    Orchestrates the initialization and execution of all hardware components,
    control loops, and data logging for the incubator.
    """
    def __init__(self, db_path: str = "incubator_log.db"):
        print("Initializing Control Manager...")
        self._db_path = db_path
        self._running_tasks: List[asyncio.Task] = []
        self._manager_active = False # Is the manager itself initialized and ready?
        self.incubator_running = False # Are the control loops actively running?

        # 1. Initialize HAL Components
        print("  Initializing HAL components...")
        self.dht_sensor = DHT22Sensor(DHT_PIN)
        self.dht_sensor.start_background_initialization() # Start non-blocking init
        self.o2_sensor = DFRobotO2Sensor(i2c_address=O2_SENSOR_ADDR)
        self.co2_sensor = CO2Sensor() # Initialize dummy CO2 sensor

        self.heater_relay = RelayOutput(HEATER_PIN, initial_value=False)
        self.humidifier_relay = RelayOutput(HUMIDIFIER_PIN, initial_value=False)
        self.argon_valve_relay = RelayOutput(ARGON_VALVE_PIN, initial_value=False)
        # self.co2_valve_relay = RelayOutput(CO2_VALVE_PIN, initial_value=False) # Removed, vent relay handled in CO2Loop
        # Note: CO2Loop itself will initialize the vent relay on CO2_VENT_PIN

        # 2. Initialize Control Loops
        print("  Initializing Control Loops...")
        self.temp_loop = TemperatureLoop(
            temp_sensor=self.dht_sensor,
            heater_relay=self.heater_relay,
            setpoint=DEFAULT_TEMP_SETPOINT,
            p=TEMP_PID_P, i=TEMP_PID_I, d=TEMP_PID_D,
            sample_time=CONTROL_SAMPLE_TIME
        )
        self.humidity_loop = HumidityLoop(
            humidity_sensor=self.dht_sensor,
            humidifier_relay=self.humidifier_relay,
            setpoint=DEFAULT_HUMIDITY_SETPOINT,
            hysteresis=HUMIDITY_HYSTERESIS,
            sample_time=CONTROL_SAMPLE_TIME
        )
        self.o2_loop = O2Loop(
            o2_sensor=self.o2_sensor,
            argon_valve_relay=self.argon_valve_relay,
            setpoint=DEFAULT_O2_SETPOINT,
            sample_time=CONTROL_SAMPLE_TIME
        )
        self.co2_loop = CO2Loop(
            sensor=self.co2_sensor,
            vent_relay_pin=CO2_VENT_PIN,
            setpoint=DEFAULT_CO2_SETPOINT
            # sample_time is handled by its internal default or can be added if needed
        )

        # 3. Initialize Data Logger
        print("  Initializing Data Logger...")
        self.logger = DataLogger(db_path=self._db_path)

        print("Control Manager Initialized.")

    async def _logging_task(self):
        """Background task to periodically log data when the incubator is running."""
        print("Data logging task started (will log when incubator is running).")
        while self._manager_active: # Keep task alive while manager is active
            try:
                # Wait until the incubator is running before trying to log
                while not self.incubator_running and self._manager_active:
                    await asyncio.sleep(1) # Check every second if incubator started
                if not self._manager_active: break # Exit if manager stopped while waiting

                # --- Incubator is running, start logging interval ---
                start_log_time = time.monotonic()
                while self.incubator_running and self._manager_active:
                    status = self.get_status()
                    log_data = {
                        'temperature': status.get('temperature'),
                        'humidity': status.get('humidity'),
                        'o2': status.get('o2'),
                        'co2': status.get('co2_ppm'),
                        'temp_setpoint': status.get('temp_setpoint'),
                        'humidity_setpoint': status.get('humidity_setpoint'),
                        'o2_setpoint': status.get('o2_setpoint'),
                        'co2_setpoint': status.get('co2_setpoint_ppm')
                    }
                    await self.logger.log_data(log_data)
                    # print("Logged data point.") # Debugging

                    # Calculate remaining sleep time for the interval
                    elapsed = time.monotonic() - start_log_time
                    sleep_duration = max(0, LOGGING_INTERVAL - elapsed % LOGGING_INTERVAL)
                    await asyncio.sleep(sleep_duration)
                    # No need to reset start_log_time here, the modulo handles the interval

                # If incubator stopped, loop back to the outer waiting loop
                if not self.incubator_running:
                    print("Incubator stopped, pausing logging.")
                    # The inner while loop condition (self.incubator_running) will become false,
                    # causing it to break and return to the outer while loop's check.

            except asyncio.CancelledError:
                print("Logging task cancelled.")
                break # Exit the outer while self._manager_active loop
            except Exception as e:
                print(f"Error in logging task: {e}")
                # Avoid crashing the logger task, wait and retry if manager still active
                if self._manager_active:
                    await asyncio.sleep(LOGGING_INTERVAL / 2) # Wait before retrying the outer loop

        print("Data logging task stopped.")


    async def start(self):
        """Initializes the logger and prepares the manager, but doesn't start loops."""
        if self._manager_active:
            print("Control Manager already initialized.")
            return

        print("Initializing Control Manager...")
        try:
            # Initialize logger database connection
            await self.logger.initialize()
            self._manager_active = True
            print("Control Manager Initialized and ready.")
            # Start the logging task container, it will wait for incubator_running
            log_task = asyncio.create_task(self._logging_task(), name="LoggerTask")
            # We don't store it in self._running_tasks as it's managed differently now
            # Let it run until the manager itself stops.

        except Exception as e:
            print(f"Error initializing Control Manager: {e}")
            self._manager_active = False
            await self.logger.close() # Ensure logger is closed if init failed
            raise # Re-raise the exception

    async def stop(self):
        """Stops incubator loops (if running), cleans up HAL, and closes logger."""
        if not self._manager_active:
            print("Control Manager already stopped or not initialized.")
            return

        print("Stopping Control Manager...")
        # 1. Stop incubator loops if they are running
        await self.stop_incubator()

        # 2. Signal the manager is stopping (will stop logger task loop)
        self._manager_active = False

        # 3. Clean up HAL components
        print("Closing HAL components...")
        self.heater_relay.close()
        self.humidifier_relay.close()
        self.argon_valve_relay.close()
        if self.co2_loop.vent_relay:
             self.co2_loop.vent_relay.close()
        self.o2_sensor.close()
        # DHT sensor and dummy CO2 sensor don't have close methods

        # 4. Close logger connection
        await self.logger.close()

        print("Control Manager fully stopped.")


    async def start_incubator(self):
        """Starts the actual control loops and logging."""
        if self.incubator_running:
            print("Incubator loops already running.")
            return
        if not self._manager_active:
            print("Cannot start incubator loops: Manager not initialized.")
            return

        print("Starting Incubator Control Loops...")
        try:
            self.incubator_running = True
            self._running_tasks = [
                asyncio.create_task(self.temp_loop.run(), name="TempLoop"),
                asyncio.create_task(self.humidity_loop.run(), name="HumidityLoop"),
                asyncio.create_task(self.o2_loop.run(), name="O2Loop"),
                asyncio.create_task(self.co2_loop.run(), name="CO2Loop"),
                # Logging task is already running, waiting for incubator_running flag
            ]
            print(f"Incubator started with {len(self._running_tasks)} control tasks.")
        except Exception as e:
            print(f"Error starting incubator loops: {e}")
            self.incubator_running = False
            await self.stop_incubator() # Attempt cleanup if start failed partially


    async def stop_incubator(self):
        """Stops the control loops."""
        if not self.incubator_running:
            # print("Incubator loops already stopped.") # Can be noisy, optional
            return

        print("Stopping Incubator Control Loops...")
        self.incubator_running = False # Signal loops and logger to stop/pause

        # Stop control loops first (signals them internally)
        self.temp_loop.stop()
        self.humidity_loop.stop()
        self.o2_loop.stop()
        self.co2_loop.stop()

        # Cancel all running tasks gracefully
        tasks_to_cancel = list(self._running_tasks) # Copy list before clearing
        self._running_tasks = [] # Clear the list

        for task in tasks_to_cancel:
            if task and not task.done():
                task.cancel()

        # Wait for tasks to finish cancellation
        if tasks_to_cancel:
            try:
                await asyncio.gather(*[t for t in tasks_to_cancel if t], return_exceptions=True)
                print("All control tasks finished or cancelled.")
            except asyncio.CancelledError:
                 print("Gather cancelled (expected during shutdown).")
            except Exception as e:
                 print(f"Error during task gathering on stop_incubator: {e}")

        # Ensure relays are off when stopping loops explicitly
        print("Ensuring actuators are off...")
        self.heater_relay.off()
        self.humidifier_relay.off()
        self.argon_valve_relay.off()
        if self.co2_loop.vent_relay:
            self.co2_loop.vent_relay.off()

        print("Incubator Control Loops stopped.")


    def get_status(self) -> Dict[str, Any]:
        """Returns the current status of all sensors and control loops."""
        status = {
            "timestamp": time.time(),
            "incubator_running": self.incubator_running, # Add overall state
            "temperature": self.temp_loop.current_temperature,
            "temp_setpoint": self.temp_loop.setpoint,
            "heater_on": self.temp_loop.heater_is_on if self.incubator_running else False,
            "humidity": self.humidity_loop.current_humidity,
            "humidity_setpoint": self.humidity_loop.setpoint,
            "humidifier_on": self.humidity_loop.humidifier_is_on if self.incubator_running else False,
            "o2": self.o2_loop.current_o2,
            "o2_setpoint": self.o2_loop.setpoint,
            "argon_valve_on": self.o2_loop.argon_valve_is_on if self.incubator_running else False,
            # Get CO2 status from the loop
            "co2_ppm": self.co2_loop.current_co2,
            "co2_setpoint_ppm": self.co2_loop.setpoint,
            "vent_active": self.co2_loop.vent_active if self.incubator_running else False,
        }
        return status

    def update_setpoints(self, setpoints: Dict[str, float]):
        """
        Updates the setpoints for the control loops.

        Args:
            setpoints: A dictionary where keys are 'temperature', 'humidity', 'o2'
                       (and eventually 'co2') and values are the new float setpoints.
        """
        print(f"Updating setpoints: {setpoints}")
        try:
            if 'temperature' in setpoints:
                self.temp_loop.setpoint = float(setpoints['temperature']) # Use setter
            if 'humidity' in setpoints:
                self.humidity_loop.setpoint = float(setpoints['humidity']) # Use setter
            if 'o2' in setpoints:
                self.o2_loop.setpoint = float(setpoints['o2']) # Use setter
            if 'co2' in setpoints:
                 self.co2_loop.setpoint = float(setpoints['co2']) # Use setter (already correct)
        except ValueError as e:
             print(f"Error updating setpoints: Invalid value type - {e}")
        except Exception as e:
             print(f"Unexpected error updating setpoints: {e}")

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
#         await manager.start() # This now just initializes
#         print("Manager initialized. Starting incubator...")
#         await manager.start_incubator() # Explicitly start loops
#         print("Incubator running for 10 seconds...")
#         await asyncio.sleep(10)
#         print("Current Status:", manager.get_status())
#         manager.update_setpoints({'temperature': 36.5, 'humidity': 58.0, 'o2': 6.0, 'co2': 950.0})
#         await asyncio.sleep(10)
#         print("Current Status:", manager.get_status())
#         print("Stopping incubator...")
#         await manager.stop_ incubator() # Explicitly stop loops
#         await asyncio.sleep(2) # Give time to see it stopped
#         print("Current Status (after stop):", manager.get_status())
#
#     except Exception as e:
#         print(f"Error during manager example: {e}")
#     finally:
#         await manager.stop() # This stops manager and cleans up everything
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