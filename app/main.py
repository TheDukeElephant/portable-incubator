import asyncio, time
from fastapi import FastAPI, WebSocket
from .settings import settings
from .control.temperature import TemperatureLoop
from .db import init_db

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
