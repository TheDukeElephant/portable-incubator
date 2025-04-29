import json
import asyncio
import time
import threading
import atexit
import io
from flask import Blueprint, render_template, request, jsonify, Response, make_response
from . import sock # sock is initialized in __init__
from .control.manager import ControlManager

# Create a Blueprint
main_bp = Blueprint('main', __name__)

# --- Global Control Manager Instance ---
manager = ControlManager() # Initialize the manager

# --- Background Asyncio Event Loop Handling ---
_async_loop = None
_loop_thread = None

def _run_async_loop():
    """Target function for the background thread to run the asyncio event loop."""
    global _async_loop
    try:
        _async_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_async_loop)
        # Run the manager's start coroutine within this loop
        _async_loop.run_until_complete(manager.start())
        # Keep the loop running to process tasks (control loops, logger)
        _async_loop.run_forever()
    except Exception as e:
        print(f"Error in asyncio background loop: {e}")
    finally:
        if _async_loop and _async_loop.is_running():
             # Perform cleanup if run_forever exits unexpectedly
             print("Asyncio loop stopping...")
             _async_loop.run_until_complete(manager.stop()) # Ensure manager stops
             _async_loop.close()
             print("Asyncio loop closed.")
        _async_loop = None

def start_background_loop():
    """Starts the background thread for the asyncio event loop."""
    global _loop_thread
    if _loop_thread is None or not _loop_thread.is_alive():
        print("Starting asyncio background thread...")
        _loop_thread = threading.Thread(target=_run_async_loop, daemon=True, name="AsyncioLoopThread")
        _loop_thread.start()
    else:
        print("Asyncio background thread already running.")

def stop_background_loop():
    """Signals the asyncio loop and manager to stop."""
    global _async_loop
    if _async_loop and _async_loop.is_running():
        print("Requesting manager stop...")
        # Schedule manager stop in the loop's thread
        future = asyncio.run_coroutine_threadsafe(manager.stop(), _async_loop)
        try:
            future.result(timeout=10) # Wait for manager stop to complete
            print("Manager stop completed.")
        except Exception as e:
            print(f"Error waiting for manager stop: {e}")

        # Stop the loop itself
        print("Requesting asyncio loop stop...")
        _async_loop.call_soon_threadsafe(_async_loop.stop)
        # Wait for the thread to finish
        if _loop_thread:
             _loop_thread.join(timeout=5)
             if _loop_thread.is_alive():
                  print("Warning: Asyncio loop thread did not exit cleanly.")
    else:
        print("Asyncio loop not running or already stopped.")

# --- Start background loop on app startup ---
start_background_loop()

# --- Register shutdown hook ---
atexit.register(stop_background_loop)


# ------------- HTTP endpoints --------------------
@main_bp.route("/")
def ui():
    """Serves the main dashboard UI."""
    return render_template("dashboard.html")

@main_bp.route("/status") # Renamed from /telemetry for clarity
def status():
    """Returns the current status of the incubator."""
    current_status = manager.get_status()
    return jsonify(current_status)

@main_bp.route("/setpoints", methods=["PUT"])
def setpoints():
    """Updates the setpoints for control loops."""
    data = request.json
    if not data:
        return jsonify({"ok": False, "error": "No JSON data received"}), 400

    valid_setpoints = {}
    allowed_keys = ['temperature', 'humidity', 'o2'] # Add 'co2' later
    try:
        for key in allowed_keys:
            if key in data:
                valid_setpoints[key] = float(data[key])
    except (ValueError, TypeError) as e:
         return jsonify({"ok": False, "error": f"Invalid setpoint value type: {e}"}), 400

    if not valid_setpoints:
         return jsonify({"ok": False, "error": f"No valid setpoint keys found in request ({allowed_keys})"}), 400

    # Update the manager (this method is synchronous)
    manager.update_setpoints(valid_setpoints)
    return jsonify({"ok": True, "updated_setpoints": valid_setpoints})

@main_bp.route("/download_log")
def download_log():
    """Downloads the logged data as a CSV file, optionally filtered by duration."""
    global _async_loop
    if not _async_loop or not _async_loop.is_running():
         return "Error: Background processing loop not running.", 500

    # --- Time Range Handling ---
    duration_str = request.args.get('duration', 'all') # Default to 'all' if not provided
    DURATION_MAP = {
        "1m": 60,          # Added
        "5m": 5 * 60,      # Added
        "15m": 15 * 60,     # Added
        "30m": 30 * 60,     # Added
        "1h": 3600,
        "6h": 6 * 3600,
        "24h": 24 * 3600,
        "2d": 2 * 24 * 3600,    # Added
        "5d": 5 * 24 * 3600,    # Added
        "10d": 10 * 24 * 3600,   # Added
        "20d": 20 * 24 * 3600,   # Added
        "7d": 7 * 24 * 3600,
        "30d": 30 * 24 * 3600,
        "60d": 60 * 24 * 3600,   # Added
        "all": None
    }
    duration_seconds = DURATION_MAP.get(duration_str)

    start_time = None
    end_time = time.time() # End time is always now

    if duration_seconds is not None:
        start_time = end_time - duration_seconds
    elif duration_str != 'all':
        # Handle invalid duration string if needed, maybe default to 'all' or return error
        print(f"Warning: Invalid duration '{duration_str}' received. Defaulting to 'all'.")
        duration_str = 'all' # Reset to all if invalid

    print(f"Requesting log download for duration: {duration_str} (Start: {start_time}, End: {end_time})")
    # --- End Time Range Handling ---

    # Need to run the async get_data_as_csv in the background loop thread
    # Pass start_time and end_time (end_time is currently always now, so passing None might be okay if logger handles it)
    future = asyncio.run_coroutine_threadsafe(manager.logger.get_data_as_csv(start_time=start_time, end_time=None), _async_loop)
    try:
        csv_data = future.result(timeout=10) # Wait for the result
    except Exception as e:
        print(f"Error retrieving CSV data: {e}")
        return f"Error retrieving log data: {e}", 500

    if csv_data is None:
        return "No log data found.", 404

    # Create a Flask response for CSV download
    output = make_response(csv_data)
    output.headers["Content-Disposition"] = "attachment; filename=incubator_log.csv"
    output.headers["Content-type"] = "text/csv"
    return output

# ------------- WebSocket stream ------------------
@sock.route("/stream")
def stream(ws):
    """WebSocket endpoint to stream incubator status updates."""
    print("WebSocket client connected.")
    try:
        while True:
            # Fetch current status from the manager
            current_status = manager.get_status()
            try:
                ws.send(json.dumps(current_status))
            except Exception as e: # Catch errors if client disconnects abruptly
                 print(f"WebSocket send error: {e}. Client likely disconnected.")
                 break # Exit loop if send fails

            # Send updates roughly every second
            time.sleep(1)
    except Exception as e:
         print(f"Error in WebSocket handler: {e}")
    finally:
         print("WebSocket client disconnected.")
