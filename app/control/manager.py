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
        self._is_running = False

        # 1. Initialize HAL Components
        print("  Initializing HAL components...")
        self.dht_sensor = DHT22Sensor(DHT_PIN)
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
        """Background task to periodically log data."""
        print("Data logging task started.")
        while self._is_running:
            try:
                await asyncio.sleep(LOGGING_INTERVAL)
                if not self._is_running: break # Exit if stopped during sleep

                status = self.get_status()
                log_data = {
                    'temperature': status.get('temperature'),
                    'humidity': status.get('humidity'),
                    'o2': status.get('o2'),
                    'co2': status.get('co2_ppm'), # Get from CO2 loop status
                    'temp_setpoint': status.get('temp_setpoint'),
                    'humidity_setpoint': status.get('humidity_setpoint'),
                    'o2_setpoint': status.get('o2_setpoint'),
                    'co2_setpoint': status.get('co2_setpoint_ppm') # Get from CO2 loop status
                }
                await self.logger.log_data(log_data)
                # print("Logged data point.") # Debugging
            except asyncio.CancelledError:
                print("Logging task cancelled.")
                break
            except Exception as e:
                print(f"Error in logging task: {e}")
                # Avoid crashing the logger task, wait and retry
                await asyncio.sleep(LOGGING_INTERVAL / 2)
        print("Data logging task stopped.")


    async def start(self):
        """Initializes the logger and starts all control loops and logging task."""
        if self._is_running:
            print("Control Manager already running.")
            return

        print("Starting Control Manager...")
        try:
            # Initialize logger database connection
            await self.logger.initialize()

            self._is_running = True
            self._running_tasks = [
                asyncio.create_task(self.temp_loop.run(), name="TempLoop"),
                asyncio.create_task(self.humidity_loop.run(), name="HumidityLoop"),
                asyncio.create_task(self.o2_loop.run(), name="O2Loop"),
                asyncio.create_task(self.co2_loop.run(), name="CO2Loop"), # Add CO2 loop task
                asyncio.create_task(self._logging_task(), name="LoggerTask")
            ]
            print(f"Control Manager started with {len(self._running_tasks)} tasks.")

        except Exception as e:
            print(f"Error starting Control Manager: {e}")
            self._is_running = False
            # Attempt cleanup if start failed partially
            await self.stop()
            raise # Re-raise the exception

    async def stop(self):
        """Stops all control loops, the logging task, and closes resources."""
        if not self._is_running and not self._running_tasks:
            print("Control Manager already stopped.")
            return

        print("Stopping Control Manager...")
        self._is_running = False # Signal loops and logger to stop

        # Stop control loops first
        self.temp_loop.stop()
        self.humidity_loop.stop()
        self.o2_loop.stop()
        self.co2_loop.stop() # Stop the CO2 loop

        # Cancel all running tasks gracefully
        for task in self._running_tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to finish cancellation
        if self._running_tasks:
            try:
                await asyncio.gather(*self._running_tasks, return_exceptions=True)
                print("All tasks finished or cancelled.")
            except asyncio.CancelledError:
                 print("Gather cancelled (expected during shutdown).")
            except Exception as e:
                 print(f"Error during task gathering on stop: {e}")


        self._running_tasks = []

        # Close HAL components (important for GPIO cleanup)
        print("Closing HAL components...")
        self.heater_relay.close()
        self.humidifier_relay.close()
        self.argon_valve_relay.close()
        # self.co2_valve_relay.close() # Removed
        if self.co2_loop.vent_relay: # Close vent relay if initialized
             self.co2_loop.vent_relay.close()
        self.o2_sensor.close()
        # self.dht_sensor doesn't have an explicit close method in the example
        # self.co2_sensor doesn't have a close method in the dummy implementation

        # Close logger connection
        await self.logger.close()

        print("Control Manager stopped.")

    def get_status(self) -> Dict[str, Any]:
        """Returns the current status of all sensors and control loops."""
        status = {
            "timestamp": time.time(),
            "temperature": self.temp_loop.current_temperature,
            "temp_setpoint": self.temp_loop.setpoint,
            "heater_on": self.temp_loop.heater_is_on,
            "humidity": self.humidity_loop.current_humidity,
            "humidity_setpoint": self.humidity_loop.setpoint,
            "humidifier_on": self.humidity_loop.humidifier_is_on,
            "o2": self.o2_loop.current_o2,
            "o2_setpoint": self.o2_loop.setpoint,
            "argon_valve_on": self.o2_loop.argon_valve_is_on,
            # Get CO2 status from the loop
            "co2_ppm": self.co2_loop.current_co2,
            "co2_setpoint_ppm": self.co2_loop.setpoint,
            "vent_active": self.co2_loop.vent_active,
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
        if 'temperature' in setpoints:
            self.temp_loop.update_setpoint(setpoints['temperature'])
        if 'humidity' in setpoints:
            self.humidity_loop.update_setpoint(setpoints['humidity'])
        if 'o2' in setpoints:
            self.o2_loop.update_setpoint(setpoints['o2'])
        if 'co2' in setpoints:
             self.co2_loop.setpoint = setpoints['co2'] # Use the setter property

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
#         await manager.start()
#         print("Manager started. Running for 20 seconds...")
#         await asyncio.sleep(10)
#         print("Current Status:", manager.get_status())
#         manager.update_setpoints({'temperature': 36.5, 'humidity': 58.0, 'o2': 6.0})
#         await asyncio.sleep(10)
#         print("Current Status:", manager.get_status())
#
#     except Exception as e:
#         print(f"Error during manager example: {e}")
#     finally:
#         await manager.stop()
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