# portable-incubator
## Description

The Portable Incubator project is a Flask-based web application designed to monitor and control the environment within a portable incubator. It reads data from various sensors (Temperature, Humidity, CO2, O2) and controls actuators (like relays) to maintain desired conditions. The application provides a web interface to visualize sensor data and manage control parameters.

## Usage

1.  **Installation:**
    *   Clone the repository: `git clone https://github.com/your-username/portable-incubator.git`
    *   Navigate to the project directory: `cd portable-incubator`
    *   Install dependencies: `pip install -r requirements.txt`

2.  **Configuration:**
    *   (Optional) Modify sensor/actuator pin configurations in the `app/hal/` directory if your hardware setup differs.
    *   (Optional) Adjust control loop parameters (setpoints, PID values) in the `app/control/` directory.

3.  **Running the Application:**
    *   Execute the main script: `python run.py`
    *   Open your web browser and navigate to `http://localhost:5000` (or the IP address of the device running the code if accessing remotely).

4.  **Web Interface:**
    *   The dashboard displays real-time sensor readings.
    *   (Future Feature) Controls for adjusting setpoints and manual overrides will be available here.