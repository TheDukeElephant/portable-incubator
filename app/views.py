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

# --- Constants ---
# Define duration map globally for use in both download and UI rendering
DURATION_MAP = {
    "1m": ("Last 1 Minute", 60),
    "5m": ("Last 5 Minutes", 5 * 60),
    "15m": ("Last 15 Minutes", 15 * 60),
    "30m": ("Last 30 Minutes", 30 * 60),
    "1h": ("Last 1 Hour", 3600),
    "6h": ("Last 6 Hours", 6 * 3600),
    "24h": ("Last 24 Hours", 24 * 3600),
    "2d": ("Last 2 Days", 2 * 24 * 3600),
    "5d": ("Last 5 Days", 5 * 24 * 3600),
    "7d": ("Last 7 Days", 7 * 24 * 3600),
    "10d": ("Last 10 Days", 10 * 24 * 3600),
    "20d": ("Last 20 Days", 20 * 24 * 3600),
    "30d": ("Last 30 Days", 30 * 24 * 3600),
    "60d": ("Last 60 Days", 60 * 24 * 3600),
    "all": ("All Data", None)
}


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
    # Pass the duration map to the template
    return render_template("dashboard.html", duration_options=DURATION_MAP)

# --- Modified /status endpoint ---
@main_bp.route("/api/status") # Changed route prefix to /api for consistency
def status():
    """Returns the current status of the incubator, including enabled states."""
    current_status = manager.get_status()
    # The manager.get_status() now includes all necessary fields, including enabled states.
    return jsonify(current_status)

@main_bp.route("/api/setpoints", methods=["PUT"]) # Changed route prefix to /api
def setpoints():
    """Updates the setpoints for control loops."""
    data = request.json
    if not data:
        return jsonify({"ok": False, "error": "No JSON data received"}), 400

    valid_setpoints = {}
    allowed_keys = ['temperature', 'humidity', 'o2', 'co2'] # Added 'co2'
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

# --- NEW: Endpoints for getting/setting individual control states ---
ALLOWED_CONTROL_NAMES = {"temperature", "humidity", "o2", "co2"}

@main_bp.route("/api/control/<string:control_name>/state", methods=["GET"])
def get_control_state(control_name):
    """Gets the enabled state (True/False) for a specific control loop."""
    if control_name not in ALLOWED_CONTROL_NAMES:
        return jsonify({"ok": False, "error": f"Invalid control name: {control_name}. Allowed: {list(ALLOWED_CONTROL_NAMES)}"}), 404

    state = manager.get_control_state(control_name)
    if state is None:
         # This shouldn't happen if control_name is validated, but good practice
         return jsonify({"ok": False, "error": f"Could not retrieve state for {control_name}"}), 500

    return jsonify({"ok": True, "control": control_name, "enabled": state})

@main_bp.route("/api/control/<string:control_name>/state", methods=["POST"])
def set_control_state(control_name):
    """Sets the enabled state (True/False) for a specific control loop."""
    if control_name not in ALLOWED_CONTROL_NAMES:
        return jsonify({"ok": False, "error": f"Invalid control name: {control_name}. Allowed: {list(ALLOWED_CONTROL_NAMES)}"}), 404

    data = request.json
    if not data or 'enabled' not in data or not isinstance(data['enabled'], bool):
        return jsonify({"ok": False, "error": "Invalid JSON data. Required format: {'enabled': true/false}"}), 400

    enabled_value = data['enabled']

    # Set the state using the manager's method (synchronous)
    manager.set_control_state(control_name, enabled_value)

    # Optionally, trigger a WebSocket update immediately after changing state
    # This requires access to the WebSocket handling logic or a shared event queue
    # For simplicity now, the regular WebSocket stream will pick up the change.

    return jsonify({"ok": True, "control": control_name, "enabled": enabled_value})
# --- End NEW Endpoints ---


@main_bp.route("/download_log")
def download_log():
    # ... (download_log implementation remains the same) ...
    global _async_loop
    if not _async_loop or not _async_loop.is_running():
         return "Error: Background processing loop not running.", 500

    # --- Time Range Handling ---
    duration_str = request.args.get('duration', 'all') # Default to 'all' if not provided

    # Use the globally defined DURATION_MAP
    duration_info = DURATION_MAP.get(duration_str)
    if duration_info:
        _, duration_seconds = duration_info # Unpack label and seconds
    else:
        # Handle invalid duration string if needed, maybe default to 'all' or return error
        print(f"Warning: Invalid duration '{duration_str}' received. Defaulting to 'all'.")
        duration_str = 'all' # Reset to all if invalid
        duration_seconds = None # Ensure duration_seconds is None for 'all'

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
    client_active = True
    last_send_time = 0
    send_interval = 1.0 # Send status every 1 second

    try:
        while client_active:
            # --- Receive Messages (with timeout) ---
            try:
                # Use a timeout to avoid blocking indefinitely, allowing status sends
                message_str = ws.receive(timeout=0.1) # Timeout after 100ms
                if message_str:
                    print(f"Received WebSocket message: {message_str}")
                    try:
                        message = json.loads(message_str)
                        if message.get('command') == 'set_incubator_state':
                            state = message.get('state')
                            if state == 'running':
                                print("Received request to START incubator.")
                                # Call manager method (to be implemented)
                                asyncio.run_coroutine_threadsafe(manager.start_incubator(), _async_loop)
                            elif state == 'stopped':
                                print("Received request to STOP incubator.")
                                # Call manager method (to be implemented)
                                asyncio.run_coroutine_threadsafe(manager.stop_incubator(), _async_loop)
                            else:
                                print(f"Invalid state received: {state}")
                        else:
                            print(f"Unknown command received: {message.get('command')}")
                    except json.JSONDecodeError:
                        print(f"Error decoding JSON message: {message_str}")
                    except Exception as e:
                         print(f"Error processing WebSocket message: {e}")

            except TimeoutError:
                # Timeout is expected, just means no message received
                pass
            except Exception as e:
                 print(f"WebSocket receive error: {e}. Client likely disconnected.")
                 client_active = False # Exit loop on receive error
                 break

            # --- Send Status Updates Periodically ---
            current_time = time.time()
            if current_time - last_send_time >= send_interval:
                # Fetch current status from the manager
                current_status = manager.get_status()
                try:
                    ws.send(json.dumps(current_status))
                    last_send_time = current_time
                except Exception as e: # Catch errors if client disconnects abruptly
                     print(f"WebSocket send error: {e}. Client likely disconnected.")
                     client_active = False # Exit loop on send error
                     break

            # Small sleep to prevent busy-waiting when no messages and not time to send
            time.sleep(0.05)

    except Exception as e:
         print(f"Error in WebSocket handler: {e}")
    finally:
         print("WebSocket client disconnected.")
