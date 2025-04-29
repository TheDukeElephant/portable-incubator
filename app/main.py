import asyncio, time
from fastapi import FastAPI, WebSocket
from .settings import settings
from .control.temperature import TemperatureLoop
from .db import init_db
from pydantic import BaseModel


app = FastAPI(title="Incubator Controller")
loop = TemperatureLoop()

@app.on_event("startup")
async def startup():
    await init_db()
    asyncio.create_task(loop.run())

@app.get("/status")
def status():
    return {"temperature": loop.current, "setpoint": loop.pid.setpoint}

@app.put("/setpoint/{value}")
def set_setpoint(value: float):
    loop.pid.setpoint = value
    return {"ok": True}

@app.websocket("/stream")
async def stream(ws: WebSocket):
    await ws.accept()
    while True:
        await ws.send_json({"t": time.time(),
                            "temp": loop.current,
                            "sp": loop.pid.setpoint})
        await asyncio.sleep(1)

class SetpointUpdate(BaseModel):
    temperature: float | None = None
    humidity: float | None = None
    co2: float | None = None
    o2: float | None = None

@app.get("/telemetry")
def telemetry():
    return {
        "temperature": loop.current,
        "humidity": 55.0,   # TODO real sensor
        "co2": 3.1,
        "o2": 19.5,
        "setpoints": {
            "temperature": loop.pid.setpoint,
            "humidity": 60.0,
            "co2": 5.0,
            "o2": 5.0,
        }
    }

@app.put("/setpoints")
def update_setpoints(body: SetpointUpdate):
    if body.temperature is not None:
        loop.pid.setpoint = body.temperature
    # ...same for others...
    return {"ok": True}
