# Portable Incubator Control System

## Description

The Portable Incubator project is a sophisticated, Flask-based web application meticulously engineered to monitor and precisely control the environmental conditions within a portable incubator unit. Leveraging real-time data acquisition from a suite of integrated sensors (including Temperature, Humidity, Carbon Dioxide (CO2), and Oxygen (O2)), the system employs advanced control algorithms to manage actuators, such as heating elements, humidifiers, and ventilation systems (via relays), ensuring optimal and stable conditions are maintained according to user-defined setpoints. The application features a dynamic web interface, providing users with intuitive visualization of sensor data streams, system status indicators, and comprehensive tools for managing control parameters and system configuration..

## Features

*   **Real-time Monitoring:** Continuous data acquisition and display for Temperature, Humidity, CO2, and O2 levels.
*   **Closed-Loop Control:** Independent PID (Proportional-Integral-Derivative) control loops for managing Temperature, Humidity, CO2, and O2.
*   **Web-Based UI:** Interactive dashboard built with Flask and HTML/CSS/JavaScript for visualizing data and system status.
*   **Hardware Abstraction:** Modular design (`app/hal/`) allows for easier adaptation to different sensor types and hardware configurations.
*   **Data Logging:** (Planned) Persistent logging of sensor data and system events for analysis and record-keeping.
*   **Configuration Management:** Control parameters (setpoints, PID constants) are configurable within the `app/control/` modules.
*   **Extensible Architecture:** Designed for potential future expansion with additional sensors, actuators, or control strategies.

## Architecture Overview

## Gas Control System

### Control Method

The CO2 and O2 levels are managed using simple threshold logic. When the measured level exceeds the setpoint, the corresponding valve is activated. This approach avoids the complexity of PID controllers while ensuring effective control.

### Valve Timing

To address the high system pressure, the following timing constraints are implemented:
- Valves are activated for only 0.1 seconds per activation cycle.
- A mandatory cooldown period of 60 seconds is enforced between activations for each gas type. This allows for proper dilution and prevents rapid cycling.

### Dual CO2 Solenoid System

To enhance CO2 control precision and provide an additional layer of safety, a secondary CO2 solenoid has been implemented. This solenoid is controlled by a relay connected to GPIO 12.

The operational logic for the dual system is as follows:
1.  The primary CO2 solenoid injects CO2 as per its control logic.
2.  After the primary solenoid closes, there is a 1-second pause.
3.  The secondary CO2 solenoid then opens for a brief period of 0.1 seconds.

This staged approach allows for finer adjustments to the CO2 concentration and adds redundancy to the CO2 delivery mechanism.

The system follows a layered architecture:

1.  **Hardware Abstraction Layer (HAL - `app/hal/`):** Provides a standardized interface to interact with physical sensors and actuators, decoupling the core logic from specific hardware implementations.
2.  **Control Layer (`app/control/`):** Contains the core logic for environmental control. Each parameter (Temperature, Humidity, CO2, O2) has a dedicated control loop (`BaseLoop` subclass) managed by a central `ControlManager`. These loops read sensor values via the HAL and determine appropriate actuator actions.
3.  **Application Layer (`app/`):** Built using the Flask framework.
    *   `views.py`: Defines the web routes and handles requests, retrieving data from the control layer and rendering the HTML templates.
    *   `datalogger.py`: (Future) Manages the logging of time-series data.
    *   `__init__.py`: Initializes the Flask application and background control threads.
4.  **Presentation Layer (`templates/`, `static/`):** Contains the HTML templates (using Jinja2) and static assets (CSS, JavaScript) for the web interface.
5.  **Main Execution (`run.py`):** The entry point script that starts the Flask development server and the background control manager thread.

## Hardware Requirements

## Hardware Setup

### GPIO Connections

**Portable Incubator Raspberry Pi GPIO Pin Assignment Plan (BCM Numbering)**

| Component          | Interface | BCM GPIO Pin(s) | Notes                     |
| :----------------- | :-------- | :-------------- | :------------------------ |
| O2 Sensor          | I2C       | 2 (SDA), 3 (SCL) | Standard I2C pins         |
| CO2 Sensor         | UART      | 14 (TXD), 15 (RXD)| Pi TXD->Sensor RXD, Pi RXD->Sensor TXD |
| DHT22 Sensor       | Digital   | 4               | General Purpose I/O       |
| Heater Relay       | Digital   | 17              | General Purpose Output    |
| Humidifier Relay   | Digital   | 27              | General Purpose Output    |
| Air Pump Relay     | Digital   | 22              | General Purpose Output    |
| CO2 Vent Relay     | Digital   | 24              | General Purpose Output    |
| CO2 Solenoid 2 Relay | Digital   | 12              | Secondary CO2 control     |
| Argon Valve Relay  | Digital   | 23              | General Purpose Output    |

### PT100 Temperature Sensor (MAX31865)

The system now utilizes a PT100 RTD temperature sensor connected via a MAX31865 RTD-to-Digital converter for precise temperature measurements.

#### MAX31865 to Raspberry Pi Wiring:

*   **SCLK (Serial Clock):** RPi Physical Pin 23 (BCM GPIO11)
*   **MOSI (Master Out Slave In) / SDI:** RPi Physical Pin 19 (BCM GPIO10)
*   **MISO (Master In Slave Out) / SDO:** RPi Physical Pin 21 (BCM GPIO9)
*   **CS (Chip Select):** RPi Physical Pin 24 (BCM GPIO8 - SPI0 CE0)
*   **VIN:** RPi Pin 1 (3.3V PWR)
*   **GND:** RPi Pin 6 (GND)

**Note on PT100 Connection:** The PT100 sensor connects to the MAX31865 board. Depending on your specific MAX31865 board and PT100 sensor, you can use 2-wire, 3-wire, or 4-wire configurations. Always consult the datasheet for your MAX31865 board for correct wiring.

#### Raspberry Pi Configuration:

The SPI interface on the Raspberry Pi must be enabled for the MAX31865 to function. This can typically be done using the `sudo raspi-config` utility:
1.  Navigate to `Interface Options`.
2.  Select `SPI`.
3.  Choose `&lt;Yes&gt;` to enable the SPI interface.
4.  Reboot if prompted.

#### Software Dependency:

The `adafruit-circuitpython-max31865` library is required for interfacing with the sensor. This has been added to `requirements.txt` and should be installed during the setup process (`pip install -r requirements.txt`).
*   **Single-Board Computer (SBC):** Raspberry Pi (recommended) or similar Linux-based SBC capable of running Python and interfacing with GPIO.
*   **Sensors:**
    *   DHT22 (or similar) for Temperature and Humidity.
    *   MH-Z19 (or similar I2C/UART) for CO2 sensing.
    *   An appropriate O2 sensor compatible with the SBC's interface (e.g., Gravity Analog Oxygen Sensor).
*   **Actuators:**
    *   Relay modules compatible with the SBC's GPIO voltage levels to control mains-powered devices (heater, humidifier, ventilation fan).
*   **Power Supplies:** Appropriate power supplies for the SBC and any high-power actuators.
*   **Wiring & Connectors:** Jumper wires, breadboard (for prototyping), connectors as needed.

*Note: Specific pin connections depend on user configuration within the `app/hal/` modules.*

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
    *   Review and modify sensor/actuator pin configurations and parameters in the respective files within the `app/hal/` directory to match your specific hardware setup.
    *   Adjust control loop parameters (setpoints, PID values, control intervals) in the files within the `app/control/` directory as needed for your application.

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
    *   (Future Feature) Interface elements for adjusting setpoints and manually toggling actuators.

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

*   [ ] Add user authentication and authorization.
*   [ ] Implement alarm notifications (email, SMS) for critical deviations.
*   [ ] Containerize the application using Docker for easier deployment.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

Copyright (c) 2025 G. M. Ursone