# Portable Incubator Control System

## Description

The Portable Incubator project is a sophisticated, Flask-based web application meticulously engineered to monitor and precisely control the environmental conditions within a portable incubator unit. Leveraging real-time data acquisition from a suite of integrated sensors (including a PT100 for Temperature, DHT22 for Humidity, a serial-based sensor for Carbon Dioxide (CO2), and an I2C sensor for Oxygen (O2)), the system employs advanced control algorithms to manage actuators. These include heating elements, humidifiers, an air pump, and gas control valves (via relays), ensuring optimal and stable conditions are maintained according to user-defined setpoints. The application features a dynamic web interface for data visualization, system status monitoring, and management of control parameters.

## Features

*   **Real-time Monitoring:** Continuous data acquisition and display for Temperature (PT100 & DHT22), Humidity (DHT22), CO2, and O2 levels.
*   **Precision Temperature Control:** Utilizes a PT100 RTD sensor with a MAX31865 converter, managed by a PID control loop.
*   **Gas Control:**
    *   **CO2 Management:** Dual solenoid system for precise CO2 injection using timed pulses (primary solenoid on GPIO 24, secondary on GPIO 12).
    *   **O2 Management:** Argon gas displacement via a relay (GPIO 23) using timed pulses to reduce O2 levels.
*   **Air Pump Control:** Cyclical operation (e.g., 5 seconds ON, 10 seconds OFF) via a relay (GPIO 26) for air circulation/exchange.
*   **Closed-Loop Control:** Independent control loops for Temperature (PID), Humidity (Hysteresis), CO2 (Threshold-based injection), and O2 (Threshold-based displacement).
*   **Web-Based UI:** Interactive dashboard built with Flask and HTML/CSS/JavaScript for visualizing data and system status.
*   **Hardware Abstraction:** Modular design (`app/hal/`) allows for easier adaptation to different sensor types and hardware configurations (e.g., `max31865_sensor.py`, `motor_driver.py` for generic relay control).
*   **Data Logging:** Persistent logging of sensor data, setpoints, and system states to an SQLite database (`incubator_log.db`) with CSV export functionality.
*   **Configuration Management:** Control parameters (setpoints, PID constants, GPIO pins, serial ports) are configurable within the `app/control/manager.py` and respective control modules.
*   **Extensible Architecture:** Designed for potential future expansion with additional sensors, actuators, or control strategies.

## Architecture Overview

## Environmental Control Systems

### CO2 Control System

CO2 levels are managed by injecting CO2 gas when the measured level falls below the setpoint. The system utilizes a serial-based CO2 sensor (e.g., SprintIR-type, configured with a 10x reading multiplier in software) and a dual solenoid valve system for precise control.

### Valve Timing

The injection sequence is as follows:
1.  If CO2 is below the setpoint and the cooldown period has elapsed:
    *   The primary CO2 solenoid (connected to GPIO 24 via `app/hal/relay_output.py`) activates for 0.1 seconds.
    *   A 1-second pause occurs.
    *   The secondary CO2 solenoid (connected to GPIO 12 via `app/hal/relay_output.py`) activates for 0.1 seconds.
2.  A cooldown period of 15 seconds is enforced before another injection cycle can begin.
This staged approach allows for finer adjustments to the CO2 concentration and adds redundancy.

*(The following subsection is now integrated above)*

### O2 Control System

Oxygen levels are managed by displacing O2 with Argon gas when the measured O2 level exceeds the setpoint. The system uses an I2C-based O2 sensor.

The control logic is as follows:
1.  If O2 is above the setpoint and the cooldown period has elapsed:
    *   The Argon valve relay (connected to GPIO 23 via `app/hal/relay_output.py`) activates for 0.1 seconds, releasing Argon into the incubator.
2.  A cooldown period of 60 seconds is enforced before another Argon release cycle can begin.

### Air Pump Control

An air pump, controlled by a relay (GPIO 26 via `app/hal/motor_driver.py` which uses `app/hal/relay_output.py`), provides air circulation or exchange. It operates on a timed cycle, for example, 5 seconds ON followed by 10 seconds OFF, managed by `app/control/air_pump.py`.

## System Architecture Layers
The system follows a layered architecture:

1.  **Hardware Abstraction Layer (HAL - `app/hal/`):** Provides a standardized interface to interact with physical sensors and actuators, decoupling the core logic from specific hardware implementations.
2.  **Control Layer (`app/control/`):** Contains the core logic for environmental control. Each parameter (Temperature, Humidity, CO2, O2, Air Pump) has a dedicated control loop (`BaseLoop` subclass, e.g., `TemperatureLoop`, `CO2Loop`, `AirPumpControlLoop`) managed by a central `ControlManager` (`app/control/manager.py`). These loops read sensor values via the HAL and determine appropriate actuator actions.
3.  **Application Layer (`app/`):** Built using the Flask framework.
    *   `views.py`: Defines the web routes and handles requests, retrieving data from the control layer and rendering the HTML templates.
    *   `datalogger.py`: Manages the logging of time-series data to an SQLite database and provides CSV export.
    *   `__init__.py`: Initializes the Flask application and background control threads.
4.  **Presentation Layer (`templates/`, `static/`):** Contains the HTML templates (using Jinja2) and static assets (CSS, JavaScript) for the web interface.
5.  **Main Execution (`run.py`):** The entry point script that starts the Flask development server and the background control manager thread.

## Hardware Requirements

## Hardware Setup

### GPIO Pin Assignments (BCM Numbering)

**Portable Incubator Raspberry Pi GPIO Pin Assignment Plan (BCM Numbering, as configured in `app/control/manager.py` and related modules)**

| Component                     | Interface | BCM GPIO Pin(s)     | Notes                                     |
| :---------------------------- | :-------- | :------------------ | :---------------------------------------- |
| **Sensors**                   |           |                     |                                           |
| O2 Sensor                     | I2C       | 2 (SDA), 3 (SCL)    | Standard I2C pins                         |
| CO2 Sensor (e.g., SprintIR)   | UART      | 14 (TXD), 15 (RXD)  | Serial Port (e.g., `/dev/ttyS0`)          |
| DHT22 Sensor (Temp/Humidity)  | Digital   | 4                   |                                           |
| PT100 Temp Sensors (2x MAX31865) | SPI       | SCLK: GPIO11, MOSI: GPIO10, MISO: GPIO9, CS0: GPIO8, CS1: GPIO7 | SPI0, Chip Selects on GPIO8 (CE0) & GPIO7 (CE1) |
| **Actuators (Relays)**        |           |                     |                                           |
| Heater Relay                  | Digital   | 17                  | Controls heating element                  |
| Humidifier Relay              | Digital   | 27                  | Controls humidifier                       |
| Air Pump Relay                | Digital   | **26**              | Controls air pump                         |
| Primary CO2 Solenoid Relay    | Digital   | **24**              | Main CO2 injection valve                  |
| Secondary CO2 Solenoid Relay  | Digital   | 12                  | Fine-tune/redundant CO2 injection         |
| Argon Valve Relay             | Digital   | 23                  | Controls Argon release for O2 displacement|

### PT100 Temperature Sensors (Dual MAX31865 Setup)

The system now utilizes a PT100 RTD temperature sensor connected via a MAX31865 RTD-to-Digital converter for precise temperature measurements.

#### MAX31865 to Raspberry Pi Wiring (Dual Sensor Setup):

For connecting two MAX31865 PT100 temperature sensors:

*   **Shared SPI Pins (Common to both sensors):**
    *   **SCLK (Serial Clock):** Connect to RPi Physical Pin 23 (BCM GPIO11 / SPI0_SCLK).
    *   **MOSI (Master Out Slave In) / SDI:** Connect to RPi Physical Pin 19 (BCM GPIO10 / SPI0_MOSI).
    *   **MISO (Master In Slave Out) / SDO:** Connect to RPi Physical Pin 21 (BCM GPIO9 / SPI0_MISO).
*   **Unique Chip Select (CS) Pins:**
    *   **Sensor 1 CS (CS0):** Connect to RPi Physical Pin 24 (BCM GPIO8 / SPI0_CE0_N).
    *   **Sensor 2 CS (CS1):** Connect to RPi Physical Pin 26 (BCM GPIO7 / SPI0_CE1_N).
*   **Power and Ground (For each sensor):**
    *   **VIN/VCC:** Connect to RPi 3.3V PWR (e.g., Physical Pin 1 or 17).
    *   **GND:** Connect to RPi GND (e.g., Physical Pin 6, 9, 14, 20, 25, 30, 34, or 39).

**Note on PT100 Connection:** The PT100 sensor connects to the MAX31865 board. Depending on your specific MAX31865 board and PT100 sensor, you can use 2-wire, 3-wire, or 4-wire configurations. Always consult the datasheet for your MAX31865 board for correct wiring.

#### Raspberry Pi Configuration:

The SPI interface on the Raspberry Pi must be enabled for the MAX31865 to function. This can typically be done using the `sudo raspi-config` utility:
1.  Navigate to `Interface Options`.
2.  Select `SPI`.
3.  Choose `&lt;Yes&gt;` to enable the SPI interface.
4.  Reboot if prompted.

#### Software Dependency:

The `adafruit-circuitpython-max31865` library is required. This is listed in `requirements.txt`.
*   **Single-Board Computer (SBC):** Raspberry Pi (tested with Zero 2 W, others should work) or similar Linux-based SBC.
*   **Sensors:**
    *   **Temperature (Primary):** PT100 RTD with MAX31865 Breakout Board (SPI interface).
    *   **Temperature & Humidity (Secondary/Ambient):** DHT22 sensor (Digital GPIO interface).
    *   **CO2:** Serial-based CO2 sensor (e.g., SprintIR type, connected via UART).
    *   **O2:** I2C Oxygen Sensor (e.g., DFRobot Gravity I2C Oxygen Sensor, using `smbus2`).
*   **Actuators:**
    *   Relay modules (5V or 3.3V coil, compatible with RPi GPIO logic levels) for:
        *   Heater
        *   Humidifier
        *   Air Pump
        *   Primary CO2 Solenoid Valve
        *   Secondary CO2 Solenoid Valve
        *   Argon Gas Solenoid Valve
*   **Power Supplies:** Appropriate power supplies for the SBC, sensors, and actuators.
*   **Wiring & Connectors:** Jumper wires, connectors as needed.

*Note: GPIO pin assignments, serial port for CO2, and I2C address for O2 are configured in `app/control/manager.py`.*

## Usage

1.  **Prerequisites:**
    *   Python 3.x installed.
    *   `pip` (Python package installer) available.
    *   Git installed.
    *   Hardware connected according to your configuration.

2.  **Installation:**
    *   Clone the repository: `git clone https://github.com/your-username/portable-incubator.git`
    *   Navigate to the project directory: `cd portable-incubator`
    *   Create and activate a virtual environment (recommended):
        ```bash
        python -m venv venv
        source venv/bin/activate  # On Windows use `venv\Scripts\activate`
        ```
    *   Install dependencies: `pip install -r requirements.txt`

3.  **Configuration:**
    *   Review and modify hardware configurations in `app/control/manager.py`. This includes GPIO pin assignments, the serial port for the CO2 sensor (e.g., `CO2_SENSOR_PORT = '/dev/ttyS0'`), the I2C address for the O2 sensor, and the CS pin for the MAX31865 (GPIO 5).
    *   Adjust control loop parameters (setpoints, PID constants, cycle timings, control intervals) in `app/control/manager.py` or the respective files within the `app/control/` directory as needed.

4.  **Running the Application:**
    *   Ensure your virtual environment is activated.
    *   Execute the main script with appropriate permissions (may require `sudo` for GPIO access):
        ```bash
        python run.py
        ```
    *   Access the web interface by opening a web browser and navigating to `http://<SBC_IP_ADDRESS>:5000`. If running locally for testing, use `http://localhost:5000`.

5.  **Web Interface:**
    *   The dashboard provides a real-time overview of all monitored environmental parameters.
    *   Monitor control loop status and actuator states.
    *   Adjust setpoints for Temperature, Humidity, CO2, and O2.
    *   Enable/disable individual control loops (Temperature, Humidity, CO2, O2, Air Pump).
    *   Start/Stop the overall incubator operation.
    *   Download logged data as a CSV file.

## Contributing

Contributions are welcome! If you'd like to contribute, please follow these steps:

1.  Fork the repository.
2.  Create a new branch for your feature or bug fix (`git checkout -b feature/your-feature-name` or `bugfix/issue-description`).
3.  Make your changes and commit them with clear, descriptive messages.
4.  Ensure your code adheres to project standards (e.g., PEP 8 for Python).
5.  Push your changes to your fork (`git push origin feature/your-feature-name`).
6.  Create a Pull Request (PR) against the main repository's `main` branch.
7.  Clearly describe the changes proposed in the PR.

## Roadmap

*   [x] Data Logging to SQLite and CSV Export (Implemented in `app/datalogger.py`)
*   [ ] User authentication and authorization for web interface.
*   [ ] Implement alarm notifications (e.g., email, visual alerts) for critical deviations.
*   [ ] Containerize the application using Docker for easier deployment.
*   [ ] Enhanced UI for historical data visualization directly from the database.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

Copyright (c) 2025 G. M. Ursone