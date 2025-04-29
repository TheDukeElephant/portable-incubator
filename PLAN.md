# Portable Incubator Control System - Implementation Plan

This document outlines the plan for developing the control software for the portable cell culture incubator using a Raspberry Pi Zero 2 W and a Flask web application.

## 1. Goals

*   Control Temperature using a PID controller and heater relay.
*   Control Humidity using hysteresis control and a humidifier relay.
*   Control O2 levels by displacing with Argon using threshold control and a valve relay.
*   Control CO2 levels using a valve relay (specific logic TBD based on custom sensor).
*   Provide a web UI (touchscreen compatible) to monitor current values and set target setpoints for all variables.
*   Log sensor readings and setpoints periodically to an SQLite database.
*   Allow downloading the logged data as a CSV file via the web UI.

## 2. System Architecture

```mermaid
graph TD
    subgraph Raspberry Pi Zero 2 W
        subgraph Flask Application (app/)
            V[views.py: Routes, WS]
            M[control/manager.py: Runs Loops]
            DLog[datalogger.py]
            UI[templates/dashboard.html]

            subgraph Control Loops (control/)
                CL_T[temperature.py (PID)]
                CL_H[humidity.py (Hysteresis)]
                CL_O2[o2.py (Threshold)]
                CL_CO2[co2.py (Placeholder)]
            end

            subgraph Hardware Abstraction (hal/)
                HAL_DHT[dht_sensor.py]
                HAL_O2[o2_sensor.py]
                HAL_CO2[co2_sensor.py (Placeholder)]
                HAL_R[relay_output.py]
            end

            V --> UI;
            V -- Gets/Sets --> M;
            V -- Serves/Receives --> Browser[Web Browser UI];
            V -- Serves --> CSV_DL[CSV Download];
            M -- Manages --> CL_T;
            M -- Manages --> CL_H;
            M -- Manages --> CL_O2;
            M -- Manages --> CL_CO2;
            M -- Logs Data --> DLog;
            DLog -- Writes/Reads --> DB[(incubator_log.db)];

            CL_T -- Uses --> HAL_DHT;
            CL_T -- Uses --> HAL_R;
            CL_H -- Uses --> HAL_DHT;
            CL_H -- Uses --> HAL_R;
            CL_O2 -- Uses --> HAL_O2;
            CL_O2 -- Uses --> HAL_R;
            CL_CO2 -- Uses --> HAL_CO2;
            CL_CO2 -- Uses --> HAL_R;

            HAL_R -- Controls --> GPIOs[GPIO Pins];
            HAL_DHT -- Reads --> GPIOs;
            HAL_O2 -- Reads --> I2C[I2C Bus];
            HAL_CO2 -- Reads --> CustomIF[Custom Interface];

        end
    end

    subgraph External Hardware
        GPIOs -- Connects --> DHT22[DHT22 Sensor];
        GPIOs -- Connects --> Relays[Heater, Hum, CO2, Argon Relays];
        I2C -- Connects --> DFRobotO2[DFRobot Gravity O2 Sensor];
        CustomIF -- Connects --> SprintIR[SprintIR CO2 Sensor];
    end

    Browser -- Interacts --> UI;
    Browser -- Requests --> CSV_DL;

    style Browser fill:#f9f,stroke:#333,stroke-width:2px
```

## 3. Implementation Details

### 3.1. Project Structure

```
.
├── PLAN.md
├── README.md
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── views.py
│   ├── datalogger.py
│   ├── control/
│   │   ├── __init__.py
│   │   ├── manager.py
│   │   ├── temperature.py
│   │   ├── humidity.py
│   │   ├── o2.py
│   │   └── co2.py
│   └── hal/
│       ├── __init__.py
│       ├── dht_sensor.py
│       ├── o2_sensor.py
│       ├── co2_sensor.py
│       └── relay_output.py
├── static/
│   └── (CSS, JS files for UI)
├── templates/
│   └── dashboard.html
└── incubator_log.db (will be created)
```

### 3.2. Hardware Abstraction Layer (`app/hal/`)

*   **`dht_sensor.py`:** Class `DHT22Sensor` using `Adafruit_DHT` library for Temp/Humidity (GPIO 4).
*   **`o2_sensor.py`:** Class `DFRobotO2Sensor` using appropriate library for DFRobot Gravity O2 Sensor (I2C).
*   **`co2_sensor.py`:** Placeholder class `SprintIRCO2Sensor` for custom SprintIR-WF-20 sensor.
*   **`relay_output.py`:** Class `RelayOutput` using `gpiozero.OutputDevice` for relays:
    *   Heater: GPIO 17
    *   Humidifier: GPIO 27
    *   CO2 Valve: GPIO 22
    *   Argon Valve: GPIO 23

### 3.3. Control Loops (`app/control/`)

*   **`manager.py`:** Initializes HAL components and all control loops. Runs loops concurrently using `asyncio` (interval: 5 seconds).
*   **`temperature.py`:** `TemperatureLoop` class using `DHT22Sensor`, `simple-pid`, and Heater `RelayOutput`.
*   **`humidity.py`:** `HumidityLoop` class using `DHT22Sensor`, Hysteresis logic, and Humidifier `RelayOutput`.
*   **`o2.py`:** `O2Loop` class using `DFRobotO2Sensor`, Threshold logic (Argon valve ON if O2 > setpoint), and Argon `RelayOutput`.
*   **`co2.py`:** Placeholder `CO2Loop` class using `SprintIRCO2Sensor` and CO2 `RelayOutput`.

### 3.4. Data Logging (`app/datalogger.py`)

*   `DataLogger` class using `aiosqlite`.
*   Logs timestamp, sensor values (Temp, Hum, O2, CO2), and setpoints to `incubator_log.db` every 60 seconds.
*   Provides method to retrieve data for CSV export.

### 3.5. Web UI & Backend (`templates/dashboard.html`, `app/views.py`)

*   **`dashboard.html`:** Display current values and setpoints (Temp, Hum, O2 initially). Use JavaScript for WebSocket updates (`/stream`) and sending setpoint changes (`/setpoints` PUT).
*   **`views.py`:**
    *   Update `/telemetry`, `/setpoints`, `/stream` for Temp, Hum, O2.
    *   Add `/download_log` GET endpoint for CSV export.

### 3.6. Dependencies (`requirements.txt`)

*   **Keep:** `Flask`, `Flask-Sock`, `simple-pid`, `gpiozero`, `aiosqlite`
*   **Add:** `Adafruit_DHT` (or similar), DFRobot O2 sensor library.
*   **Remove:** `fastapi`, `uvicorn`, `pydantic`.

## 4. Next Steps (Implementation)

1.  Set up the basic project structure (directories, empty files).
2.  Clean up `requirements.txt`.
3.  Implement the Hardware Abstraction Layer classes.
4.  Implement the Control Loop classes (starting with Temp, Hum, O2).
5.  Implement the Data Logger.
6.  Implement the Control Manager.
7.  Update the Flask views (`app/views.py`).
8.  Develop the Web UI (`templates/dashboard.html` and associated JS/CSS).
9.  Integrate the CO2 sensor and control loop (when details are available).
10. Testing and Tuning.