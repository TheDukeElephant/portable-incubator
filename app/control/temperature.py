import asyncio, time
from gpiozero import LED
from simple_pid import PID
from ..settings import settings
from ..db import log_sample

class TemperatureLoop:
    def __init__(self):
        self.heater = LED(settings.heater_gpio)
        self.pid = PID(5, 0.1, 1, setpoint=settings.target_temp)
        self.current = 20.0  # fake starting value

    async def run(self):
        while True:
            # TODO: replace with real sensor read
            self.current += (self.heater.value * 2 - 1) * 0.1
            power = self.pid(self.current)
            self.heater.value = 1 if power > 0 else 0
            await log_sample(time.time(), self.current, self.pid.setpoint)
            await asyncio.sleep(1)
