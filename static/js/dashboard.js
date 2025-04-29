const wsStatusDiv = document.getElementById('ws-status');
const errorDiv = document.getElementById('error-message');
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

function connectWebSocket() {
    wsStatusDiv.textContent = 'Connecting...';
    errorDiv.textContent = ''; // Clear previous errors
    socket = new WebSocket(wsUrl);

    socket.onopen = function(event) {
        console.log("WebSocket connection opened");
        wsStatusDiv.textContent = 'Connected';
    };

    socket.onmessage = function(event) {
        // console.log("Message from server: ", event.data);
        try {
            const data = JSON.parse(event.data);
            updateUI(data);
        } catch (e) {
            console.error("Failed to parse WebSocket message:", e);
            errorDiv.textContent = 'Error processing server update.';
        }
    };

    socket.onerror = function(event) {
        console.error("WebSocket error observed:", event);
        wsStatusDiv.textContent = 'Connection Error!';
        errorDiv.textContent = 'WebSocket connection error. Check server status.';
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
        options: { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, title: { display: true, text: 'ppm' } } } }
    });
}

// --- UI and Chart Update Function ---
function updateUI(data) {
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


    // Humidity
    document.getElementById('hum-current').textContent = data.humidity !== null ? data.humidity.toFixed(2) : '--';
    document.getElementById('hum-setpoint-display').textContent = data.humidity_setpoint !== null ? data.humidity_setpoint.toFixed(1) : '--';
    updateRelayStatus('humidifier-status', data.humidifier_on, 'Humidifier');
    const humInput = document.getElementById('hum-setpoint-input');
     if (document.activeElement !== humInput && data.humidity_setpoint !== null) {
         humInput.value = data.humidity_setpoint.toFixed(1);
    }
    updateChartData('humidity', data.humidity); // Update chart data

    // Oxygen
    document.getElementById('o2-current').textContent = data.o2 !== null ? data.o2.toFixed(2) : '--';
    document.getElementById('o2-setpoint-display').textContent = data.o2_setpoint !== null ? data.o2_setpoint.toFixed(1) : '--';
    updateRelayStatus('argon-status', data.argon_valve_on, 'Argon Valve');
     const o2Input = document.getElementById('o2-setpoint-input');
     if (document.activeElement !== o2Input && data.o2_setpoint !== null) {
         o2Input.value = data.o2_setpoint.toFixed(1);
    }
    updateChartData('o2', data.o2); // Update chart data

    // CO2
    document.getElementById('co2-current').textContent = data.co2_ppm !== null ? data.co2_ppm.toFixed(0) : '--';
    document.getElementById('co2-setpoint-display').textContent = data.co2_setpoint_ppm !== null ? data.co2_setpoint_ppm.toFixed(0) : '--';
    updateRelayStatus('vent-status', data.vent_active, 'Vent');
    const co2Input = document.getElementById('co2-setpoint-input');
    if (document.activeElement !== co2Input && data.co2_setpoint_ppm !== null) {
        co2Input.value = data.co2_setpoint_ppm.toFixed(0);
    }
    updateChartData('co2', data.co2_ppm); // Update chart data
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
    if (co2Setpoint !== '') setpoints.co2 = parseFloat(co2Setpoint);

    if (Object.keys(setpoints).length === 0) {
        errorDiv.textContent = 'No setpoint values entered.';
        return;
    }

    console.log("Sending setpoints:", setpoints);
    errorDiv.textContent = ''; // Clear previous errors

    fetch('/setpoints', {
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
            errorDiv.textContent = `Error updating setpoints: ${data.error || 'Unknown error'}`;
        } else {
             // Optionally clear inputs or provide success message
             console.log("Setpoints updated successfully.");
        }
    })
    .catch((error) => {
        console.error('Error sending setpoints:', error);
        errorDiv.textContent = 'Failed to send setpoints to server.';
    });
}

// --- Initial Connection ---
// --- Initial Connection & Chart Setup ---
initCharts(); // Initialize charts on page load
connectWebSocket();