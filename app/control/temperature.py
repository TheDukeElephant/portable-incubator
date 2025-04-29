import asyncio, time
from simple_pid import PID

class TemperatureLoop:
    def __init__(self):
        self.current = 25.0
        self.pid = PID(5, 0.1, 1, setpoint=37.0)

    async def run(self):
        while True:
            # fake physics
            self.current += (self.pid(self.current) > 0) * 0.2 - 0.1
            time.sleep(1)