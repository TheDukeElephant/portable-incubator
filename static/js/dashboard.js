const wsStatusDiv = document.getElementById('ws-status');
const errorDiv = document.getElementById('error-message');
const incubatorToggleButton = document.getElementById('incubator-toggle-button'); // Added button reference
const tempEnableSwitch = document.getElementById('temp-enable-switch');
const humEnableSwitch = document.getElementById('hum-enable-switch');
const o2EnableSwitch = document.getElementById('o2-enable-switch');
const co2EnableSwitch = document.getElementById('co2-enable-switch');
const MAX_DATA_POINTS = 50; // Approx 50 seconds if data comes every second

// Chart instances and data storage
let tempChart, humChart, o2Chart, co2Chart;
const chartData = {
    temperature: { labels: [], values: [] },
    humidity: { labels: [], values: [] },
    o2: { labels: [], values: [] },
    co2: { labels: [], values: [] }
};

// --- WebSocket Connection ---
let socket;
const wsUrl = `ws://${window.location.host}/stream`; // Adjust if needed

// Helper function to show/hide the error message div
function displayError(message) {
    if (message) {
        errorDiv.textContent = message;
        errorDiv.classList.add('visible'); // Add class to make it visible
    } else {
        errorDiv.textContent = '';
        errorDiv.classList.remove('visible'); // Remove class to hide it
    }
}

function connectWebSocket() {
    wsStatusDiv.textContent = 'Connecting...';
    displayError(''); // Clear previous errors
    socket = new WebSocket(wsUrl);

    socket.onopen = function(event) {
        console.log("WebSocket connection opened");
        wsStatusDiv.textContent = 'Connected';
        displayError(''); // Clear error message on successful connection
    };

    socket.onmessage = function(event) {
        // console.log("Message from server: ", event.data);
        try {
            const data = JSON.parse(event.data);
            updateUI(data);
        } catch (e) {
            console.error("Failed to parse WebSocket message:", e);
            displayError('Error processing server update.');
        }
    };

    socket.onerror = function(event) {
        console.error("WebSocket error observed:", event);
        wsStatusDiv.textContent = 'Connection Error!';
        displayError('WebSocket connection error. Check server status.');
        // Optional: Attempt to reconnect after a delay
        // setTimeout(connectWebSocket, 5000);
    };

    socket.onclose = function(event) {
        console.log("WebSocket connection closed:", event);
        wsStatusDiv.textContent = 'Disconnected. Attempting to reconnect...';
        // Attempt to reconnect after a delay
        setTimeout(connectWebSocket, 5000); // Reconnect every 5 seconds
    };
}

// --- Chart Initialization ---
function initCharts() {
    const commonOptions = {
        scales: {
            x: {
                type: 'time',
                time: {
                    unit: 'second',
                    displayFormats: {
                        second: 'HH:mm:ss'
                    },
                    tooltipFormat: 'HH:mm:ss'
                },
                ticks: {
                    maxTicksLimit: 6 // Limit number of time labels
                },
                title: {
                    display: true,
                    text: 'Time'
                }
            },
            y: {
                beginAtZero: false, // Adjust based on sensor range if needed
                title: {
                    display: true,
                    text: 'Value'
                }
            }
        },
        plugins: {
            legend: { display: false },
            tooltip: {
                mode: 'index',
                intersect: false
            }
        },
        animation: false, // Disable animation for real-time updates
        maintainAspectRatio: false
    };

    tempChart = new Chart(document.getElementById('temp-chart').getContext('2d'), {
        type: 'line',
        data: { labels: chartData.temperature.labels, datasets: [{ data: chartData.temperature.values, borderColor: '#FFA500', tension: 0.1, pointRadius: 0 }] },
        options: { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, title: { display: true, text: '°C' } } } }
    });
    humChart = new Chart(document.getElementById('hum-chart').getContext('2d'), {
        type: 'line',
        data: { labels: chartData.humidity.labels, datasets: [{ data: chartData.humidity.values, borderColor: '#3a86ff', tension: 0.1, pointRadius: 0 }] },
        options: { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, title: { display: true, text: '%' } } } }
    });
    o2Chart = new Chart(document.getElementById('o2-chart').getContext('2d'), {
        type: 'line',
        data: { labels: chartData.o2.labels, datasets: [{ data: chartData.o2.values, borderColor: '#4ecca3', tension: 0.1, pointRadius: 0 }] },
        options: { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, title: { display: true, text: '%' } } } }
    });
    co2Chart = new Chart(document.getElementById('co2-chart').getContext('2d'), {
        type: 'line',
        data: { labels: chartData.co2.labels, datasets: [{ data: chartData.co2.values, borderColor: '#C77DFF', tension: 0.1, pointRadius: 0 }] },
        options: { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, title: { display: true, text: '%' } } } }
    });
}

// --- UI and Chart Update Function ---
function updateUI(data) {
    console.log("[LOG] updateUI received data:", JSON.stringify(data)); // Log received data
    const now = new Date(); // Use a single timestamp for all values in this update

    // Helper function to update chart data arrays
    const updateChartData = (key, value) => {
        if (value === null || value === undefined) return; // Don't add nulls to chart

        chartData[key].labels.push(now);
        chartData[key].values.push(value);

        // Keep only the last MAX_DATA_POINTS
        if (chartData[key].labels.length > MAX_DATA_POINTS) {
            chartData[key].labels.shift();
            chartData[key].values.shift();
        }
    };

    // Temperature
    document.getElementById('temp-current').textContent = data.temperature !== null ? data.temperature.toFixed(2) : '--';
    document.getElementById('temp-setpoint-display').textContent = data.temp_setpoint !== null ? data.temp_setpoint.toFixed(2) : '--';
    updateRelayStatus('heater-status', data.heater_on, 'Heater');
    // Only update input if it doesn't have focus to avoid disrupting user input
    const tempInput = document.getElementById('temp-setpoint-input');
    if (document.activeElement !== tempInput && data.temp_setpoint !== null) {
         tempInput.value = data.temp_setpoint.toFixed(2);
    }
    updateChartData('temperature', data.temperature); // Update chart data
    // Update Temperature Enable Switch state (only if element exists and data is present)
    // REMOVED: && document.activeElement !== tempEnableSwitch
    if (tempEnableSwitch && data.temperature_enabled !== undefined) {
        console.log(`[LOG] updateUI: Setting tempEnableSwitch.checked = ${data.temperature_enabled}`);
        tempEnableSwitch.checked = data.temperature_enabled;
    }


    // Humidity
    if (data.humidity === "NC") {
        document.getElementById('hum-current').textContent = "NC";
    } else if (data.humidity !== null) {
        document.getElementById('hum-current').textContent = `${data.humidity.toFixed(2)}% RH`;
    } else {
        document.getElementById('hum-current').textContent = '--';
    }
    document.getElementById('hum-setpoint-display').textContent = data.humidity_setpoint !== null ? data.humidity_setpoint.toFixed(1) : '--';
    updateRelayStatus('humidifier-status', data.humidifier_on, 'Humidifier');
    const humInput = document.getElementById('hum-setpoint-input');
     if (document.activeElement !== humInput && data.humidity_setpoint !== null) {
         humInput.value = data.humidity_setpoint.toFixed(1);
    }
    updateChartData('humidity', data.humidity); // Update chart data
    // Update Humidity Enable Switch state
    if (humEnableSwitch && data.humidity_enabled !== undefined /* && document.activeElement !== humEnableSwitch */) { // Removed activeElement check
        console.log(`[LOG] updateUI: Setting humEnableSwitch.checked = ${data.humidity_enabled}`);
        humEnableSwitch.checked = data.humidity_enabled;
    }

    // Oxygen
    document.getElementById('o2-current').textContent = data.o2 !== null ? data.o2.toFixed(2) : 'NC';
    document.getElementById('o2-setpoint-display').textContent = data.o2_setpoint !== null ? data.o2_setpoint.toFixed(1) : '--';
    updateRelayStatus('argon-status', data.argon_valve_on, 'Argon Valve');
     const o2Input = document.getElementById('o2-setpoint-input');
     if (document.activeElement !== o2Input && data.o2_setpoint !== null) {
         o2Input.value = data.o2_setpoint.toFixed(1);
    }
    updateChartData('o2', data.o2); // Update chart data
    // Update O2 Enable Switch state
    if (o2EnableSwitch && data.o2_enabled !== undefined /* && document.activeElement !== o2EnableSwitch */) { // Removed activeElement check
        console.log(`[LOG] updateUI: Setting o2EnableSwitch.checked = ${data.o2_enabled}`);
        o2EnableSwitch.checked = data.o2_enabled;
    }

    // CO2
    const co2_ppm = data.co2_ppm;
    const co2_percentage = co2_ppm !== null ? (co2_ppm / 10000).toFixed(2) : null;
    document.getElementById('co2-current').textContent = co2_percentage !== null ? `${co2_percentage}` : 'NC';
    const co2_setpoint_ppm = data.co2_setpoint_ppm !== null ? data.co2_setpoint_ppm : 1000.0; // Fallback to default
    const co2_setpoint_percentage = (co2_setpoint_ppm / 10000).toFixed(2);
    document.getElementById('co2-setpoint-display').textContent = `${co2_setpoint_percentage}`;
    updateRelayStatus('vent-status', data.vent_active, 'CO2 valve');
    const co2Input = document.getElementById('co2-setpoint-input');
    if (document.activeElement !== co2Input && co2_setpoint_percentage !== null) {
        // Update input field with percentage value
        co2Input.value = co2_setpoint_percentage;
    }
    // Update chart data with the current CO2 percentage to match the Y-axis
    updateChartData('co2', co2_percentage);
    // Update CO2 Enable Switch state
    if (co2EnableSwitch && data.co2_enabled !== undefined && document.activeElement !== co2EnableSwitch) {
        console.log(`[LOG] updateUI: Setting co2EnableSwitch.checked = ${data.co2_enabled}`);
        co2EnableSwitch.checked = data.co2_enabled;
    }

    // Update Incubator State Button
    if (incubatorToggleButton) {
        if (data.incubator_running === true) {
            incubatorToggleButton.textContent = 'Stop Incubator';
            incubatorToggleButton.className = 'toggle-button button-on';
        } else if (data.incubator_running === false) {
            incubatorToggleButton.textContent = 'Start Incubator';
            incubatorToggleButton.className = 'toggle-button button-off';
        }
        // If incubator_running is null/undefined, don't change the button
    }


    // Update charts
    if (tempChart) tempChart.update();
    if (humChart) humChart.update();
    if (o2Chart) o2Chart.update();
    if (co2Chart) co2Chart.update();
}

function updateRelayStatus(elementId, isOn, name) {
    const element = document.getElementById(elementId);
    if (isOn) {
        element.textContent = `${name} ON`;
        element.className = 'relay-status relay-on';
    } else {
        element.textContent = `${name} OFF`;
        element.className = 'relay-status relay-off';
    }
}

// --- Setpoint Update Function ---
function updateSetpoints() {
    const tempSetpoint = document.getElementById('temp-setpoint-input').value;
    const humSetpoint = document.getElementById('hum-setpoint-input').value;
    const o2Setpoint = document.getElementById('o2-setpoint-input').value;
    const co2Setpoint = document.getElementById('co2-setpoint-input').value;

    const setpoints = {};
    if (tempSetpoint !== '') setpoints.temperature = parseFloat(tempSetpoint);
    if (humSetpoint !== '') setpoints.humidity = parseFloat(humSetpoint);
    if (o2Setpoint !== '') setpoints.o2 = parseFloat(o2Setpoint);
    console.log("[DEBUG] CO2 setpoint input value:", co2Setpoint);
    if (co2Setpoint !== '') {
        // Convert percentage input back to ppm before sending
        const co2SetpointPercentage = parseFloat(co2Setpoint);
        if (!isNaN(co2SetpointPercentage)) {
            setpoints.co2 = Math.round(co2SetpointPercentage * 10000); // Send ppm to backend
        } else {
             console.warn("Invalid CO2 setpoint input:", co2Setpoint);
             // Optionally display an error to the user here
        }
    }

    if (Object.keys(setpoints).length === 0) {
        displayError('No setpoint values entered.');
        return;
    }

    console.log("Sending setpoints to /api/setpoints:", setpoints);
    displayError(''); // Clear previous errors

    fetch('/api/setpoints', {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(setpoints),
    })
    .then(response => response.json())
    .then(data => {
        console.log('Setpoint update response:', data);
        if (!data.ok) {
            displayError(`Error updating setpoints: ${data.error || 'Unknown error'}`);
        } else {
             // Optionally clear inputs or provide success message
             console.log("Setpoints updated successfully.");
        }
    })
    .catch((error) => {
        console.error('Error sending setpoints:', error);
        displayError('Failed to send setpoints to server.');
    });
}

// --- Control Loop Enable/Disable Toggle Function ---
function handleControlToggle(event) {
    const switchElement = event.target;
    const controlName = switchElement.dataset.control; // Get 'temperature', 'humidity', etc.
    const newState = switchElement.checked; // true if checked (enabled), false if unchecked (disabled)
    console.log(`[LOG] handleControlToggle: control='${controlName}', newState=${newState}`); // Log toggle event

    if (!controlName) {
        console.error("Could not determine control name for switch:", switchElement);
        displayError("Internal error: Could not identify control switch.");
        // Revert visual state just in case
        switchElement.checked = !newState;
        return;
    }

    console.log(`Toggling control loop '${controlName}' to state: ${newState}`);
    displayError(''); // Clear previous errors
    // switchElement.disabled = true; // Disable switch during API call // <-- REMOVED

    fetch(`/api/control/${controlName}/state`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ enabled: newState }),
    })
    .then(response => {
        if (!response.ok) {
            // If response is not OK, try to parse error message, otherwise throw generic error
            return response.json().then(errData => {
                throw new Error(errData.error || `HTTP error! status: ${response.status}`);
            }).catch(() => { // Catch if parsing error JSON fails
                throw new Error(`HTTP error! status: ${response.status}`);
            });
        }
        return response.json(); // Parse successful response
    })
    .then(data => {
        console.log(`Control loop '${controlName}' state updated successfully:`, data);
        // Success! The switch state is already visually correct.
        // The next WebSocket update should confirm this state anyway.
    })
    .catch((error) => {
        console.error(`Error updating control loop '${controlName}' state:`, error);
        displayError(`Failed to update ${controlName} state: ${error.message}`);
        // Revert the switch's visual state because the API call failed
        switchElement.checked = !newState;
    })
    .finally(() => {
        // Re-enable the switch regardless of success or failure
        // switchElement.disabled = false; // <-- REMOVED
    });
}

// --- Incubator State Toggle Function ---
function toggleIncubatorState() {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
        displayError('WebSocket is not connected. Cannot change incubator state.');
        return;
    }

    // Determine the *intended* state based on the current button class
    const isCurrentlyOff = incubatorToggleButton.classList.contains('button-off');
    const intendedState = isCurrentlyOff ? 'running' : 'stopped';

    console.log(`Requesting incubator state change to: ${intendedState}`);
    displayError(''); // Clear previous errors

    const message = {
        command: 'set_incubator_state',
        state: intendedState
    };
    socket.send(JSON.stringify(message));

    // Note: Button appearance is updated in updateUI based on confirmation from backend
}


// --- Initial Connection & Event Listeners ---
initCharts(); // Initialize charts on page load
connectWebSocket();
// Add event listener for the toggle button
if (incubatorToggleButton) {
    incubatorToggleButton.addEventListener('click', toggleIncubatorState);
} else {
    console.error("Incubator toggle button not found!");
}

// Add event listeners for control enable/disable switches
if (tempEnableSwitch) tempEnableSwitch.addEventListener('change', handleControlToggle);
if (humEnableSwitch) humEnableSwitch.addEventListener('change', handleControlToggle);
if (o2EnableSwitch) o2EnableSwitch.addEventListener('change', handleControlToggle);
if (co2EnableSwitch) co2EnableSwitch.addEventListener('change', handleControlToggle);


// --- Log Download Function ---
function downloadLogWithDuration() {
    const durationSelect = document.getElementById('log-duration-select');
    const selectedDuration = durationSelect.value;
    const downloadUrl = `/download_log?duration=${selectedDuration}`;

    console.log(`Requesting log download with URL: ${downloadUrl}`);
    // Open the URL in a new tab, which will trigger the download
    window.open(downloadUrl, '_blank');
}