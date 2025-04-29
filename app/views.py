import json, asyncio, time, threading
from flask import render_template, request, jsonify
from . import app, sock
from .control.temperature import TemperatureLoop

loop = TemperatureLoop()

# --- background control loop in its own thread ---
def _runner():
    asyncio.run(loop.run())

threading.Thread(target=_runner, daemon=True).start()

# ------------- HTTP endpoints --------------------
@app.route("/")
def ui():
    return render_template("dashboard.html")

@app.route("/telemetry")
def telemetry():
    return jsonify(
        temperature=loop.current,
        setpoints=dict(temperature=loop.pid.setpoint),
    )

@app.route("/setpoints", methods=["PUT"])
def setpoints():
    data = request.json
    if "temperature" in data:
        loop.pid.setpoint = float(data["temperature"])
    return {"ok": True}

# ------------- WebSocket stream ------------------
@sock.route("/stream")
def ws(ws):
    while True:
        ws.send(json.dumps({
            "t": time.time(),
            "temp": loop.current,
            "sp": loop.pid.setpoint,
        }))
        time.sleep(1)
