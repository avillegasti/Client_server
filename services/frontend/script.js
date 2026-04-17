const API_BASE = CONFIG.API_BASE;
const deviceDirectory = new Map();
const CHART_COLORS = {
    temperature: '#e1542f',
    humidity: '#4f88c6',
    battery: '#5ea37a'
};
const chartTimestampFormatter = new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
});
const overviewChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom' } },
    scales: {
        x: { display: true, grid: { display: false } },
        y: { type: 'linear', position: 'left' },
        y1: { type: 'linear', position: 'right', grid: { drawOnChartArea: false } }
    }
};

// Charts
let mainCombinedChart, tempChart, humChart, battChart;
let overviewCameraCharts = [];
let telemetryCameraCharts = [];

document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

async function initApp() {
    setupNavigation();
    initCharts();
    await loadDevices();
    await loadData();

    document.getElementById('refreshBtn').addEventListener('click', loadData);
    document.getElementById('deviceSelect').addEventListener('change', loadData);
    
    // Modal
    const modal = document.getElementById('imageModal');
    const closeBtn = document.querySelector('.close-modal');
    const overlay = document.querySelector('.modal-overlay');
    
    [closeBtn, overlay].forEach(el => {
        el.onclick = () => modal.style.display = "none";
    });

    window.addEventListener('resize', resizeVisibleCharts);
}

function setupNavigation() {
    const navItems = document.querySelectorAll('.sidebar-nav li');
    const sections = document.querySelectorAll('.content-section');
    const title = document.getElementById('section-title');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const sectionId = item.getAttribute('data-section');
            
            // Update Active State
            navItems.forEach(i => i.classList.remove('active'));
            item.classList.add('active');
            
            // Show Section
            sections.forEach(s => s.classList.add('hidden'));
            document.getElementById(`section-${sectionId}`).classList.remove('hidden');
            
            // Update Title
            title.textContent = item.textContent.trim().split(' ').slice(1).join(' ');

            requestAnimationFrame(() => {
                resizeVisibleCharts();
                setTimeout(resizeVisibleCharts, 80);
            });
        });
    });
}

async function loadDevices() {
    try {
        const response = await fetch(`${API_BASE}/api/telemetry/devices`);
        const devices = await response.json();
        const select = document.getElementById('deviceSelect');
        deviceDirectory.clear();
        // Clear existing options except the first one (All Devices)
        while (select.options.length > 1) {
            select.remove(1);
        }

        devices.forEach(dev => {
            const opt = document.createElement('option');
            if (typeof dev === 'object' && dev !== null) {
                opt.value = dev.serial;
                opt.textContent = dev.description || dev.serial;
                deviceDirectory.set(dev.serial, {
                    serial: dev.serial,
                    label: dev.description || dev.serial
                });
            } else {
                opt.value = dev;
                opt.textContent = dev;
                deviceDirectory.set(dev, {
                    serial: dev,
                    label: dev
                });
            }
            select.appendChild(opt);
        });
    } catch (e) {
        console.error("Error loading devices:", e);
    }
}

async function loadData() {
    const deviceSelect = document.getElementById('deviceSelect');
    const device = deviceSelect.value;
    const camera = device ? getCameraFolder(device) : '';
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;

    const telemetryParams = new URLSearchParams({ limit: '1000' });
    const imageParams = new URLSearchParams();
    const overviewParams = new URLSearchParams({ trend_points: '8' });
    const seriesParams = new URLSearchParams({ points_per_device: '100' });

    if (device) {
        telemetryParams.set('device', device);
        imageParams.set('device', device);
        overviewParams.set('device', device);
        seriesParams.set('device', device);
        if (camera) {
            imageParams.set('camera', camera);
        }
    }
    if (startDate) {
        telemetryParams.set('start_date', startDate);
        imageParams.set('start_date', startDate);
        overviewParams.set('start_date', startDate);
        seriesParams.set('start_date', startDate);
    }
    if (endDate) {
        telemetryParams.set('end_date', endDate);
        imageParams.set('end_date', endDate);
        overviewParams.set('end_date', endDate);
        seriesParams.set('end_date', endDate);
    }

    try {
        const [telemetry, images, overview, telemetrySeries] = await Promise.all([
            fetch(`${API_BASE}/api/telemetry/telemetry?${telemetryParams.toString()}`).then(r => r.json()),
            fetch(`${API_BASE}/api/images/images?${imageParams.toString()}`).then(r => r.json()),
            fetch(`${API_BASE}/api/telemetry/overview?${overviewParams.toString()}`).then(r => r.json()),
            fetch(`${API_BASE}/api/telemetry/series?${seriesParams.toString()}`).then(r => r.json())
        ]);

        updateStats(telemetry, images);
        updateCharts(telemetry, overview, telemetrySeries, device);
        renderOverviewByCamera(overview, device);
        updateTable(telemetry);
        updateGallery(images);
    } catch (e) {
        console.error("Error loading data:", e);
    }
}

function updateStats(telemetry, images) {
    const getAvg = (type) => {
        const vals = telemetry.filter(d => d.sensor_type === type).map(d => d.value);
        if (vals.length === 0) return "--";
        return (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1);
    };

    document.getElementById('avg-temp').textContent = `${getAvg('temperature')} °C`;
    document.getElementById('avg-hum').textContent = `${getAvg('humidity')} %`;
    document.getElementById('avg-batt').textContent = `${getAvg('battery')} V`;
    document.getElementById('total-images').textContent = images.length;
}

function renderOverviewByCamera(overviewData, selectedDevice) {
    const section = document.getElementById('cameraOverviewSection');
    const grid = document.getElementById('cameraOverviewGrid');
    const emptyState = document.getElementById('cameraOverviewEmpty');

    grid.innerHTML = '';

    if (selectedDevice) {
        section.classList.add('hidden');
        return;
    }

    if (!overviewData.length || overviewData.length <= 1) {
        section.classList.add('hidden');
        return;
    }

    section.classList.remove('hidden');
    emptyState.classList.toggle('hidden', overviewData.length > 0);

    overviewData
        .slice()
        .sort((left, right) => getDeviceLabel(left.serial).localeCompare(getDeviceLabel(right.serial)))
        .forEach((item) => {
            const card = document.createElement('article');
            card.className = 'camera-overview-card';
            card.innerHTML = `
                <div class="camera-overview-card-header">
                    <h3>${escapeHtml(getDeviceLabel(item.serial))}</h3>
                    <span>Serial: ${escapeHtml(item.serial)}</span>
                </div>
                <div class="camera-overview-stats">
                    ${renderCameraStat('Last Temp', formatMetric(item.temperature, '°C'))}
                    ${renderCameraStat('Last Humidity', formatMetric(item.humidity, '%'))}
                    ${renderCameraStat('Last Battery', formatMetric(item.battery, 'V'))}
                    ${renderCameraStat('Images', `${item.image_count || 0}`)}
                </div>
                <div class="camera-overview-footer">
                    <span>Latest update</span>
                    <span>${item.latest_timestamp ? new Date(item.latest_timestamp).toLocaleString() : 'No telemetry'}</span>
                </div>
            `;
            grid.appendChild(card);
        });
}

function renderCameraStat(label, value) {
    return `
        <div class="camera-overview-stat">
            <span class="camera-overview-stat-label">${label}</span>
            <span class="camera-overview-stat-value">${value}</span>
        </div>
    `;
}

function getDeviceLabel(serial) {
    return deviceDirectory.get(serial)?.label || serial;
}

function getCameraFolder(serial) {
    const label = getDeviceLabel(serial);
    const normalized = String(label)
        .trim()
        .toLowerCase()
        .replace(/\s+/g, '');

    return normalized || '';
}

function formatMetric(value, unit) {
    return value == null ? '--' : `${value.toFixed(1)} ${unit}`;
}

function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[char]));
}

function initCharts() {
    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom' } },
        scales: { x: { display: false } }
    };

    // Overview Combined Chart
    mainCombinedChart = new Chart(document.getElementById('mainCombinedChart'), {
        type: 'line',
        data: { labels: [], datasets: [
            { label: 'Temp', borderColor: CHART_COLORS.temperature, data: [], yAxisID: 'y' },
            { label: 'Humidity', borderColor: CHART_COLORS.humidity, data: [], yAxisID: 'y1' }
        ]},
        options: overviewChartOptions
    });

    // Individual Charts
    const createChart = (id, label, color) => new Chart(document.getElementById(id), {
        type: 'line',
        data: { labels: [], datasets: [{ label, borderColor: color, backgroundColor: color + '22', fill: true, data: [] }] },
        options: commonOptions
    });

    tempChart = createChart('tempChart', 'Temperature (°C)', CHART_COLORS.temperature);
    humChart = createChart('humChart', 'Humidity (%)', CHART_COLORS.humidity);
    battChart = createChart('battChart', 'Battery (V)', CHART_COLORS.battery);
}

function updateCharts(data, overviewData, telemetrySeries, selectedDevice) {
    const sensors = {
        temperature: data.filter(d => d.sensor_type === 'temperature').reverse(),
        humidity: data.filter(d => d.sensor_type === 'humidity').reverse(),
        battery: data.filter(d => d.sensor_type === 'battery').reverse()
    };

    const showPerCameraOverview = !selectedDevice && overviewData.length > 1;
    const showPerCameraTelemetry = !selectedDevice && telemetrySeries.length > 1;

    toggleOverviewTrendMode(showPerCameraOverview);

    if (showPerCameraOverview) {
        renderCameraTrendCharts(overviewData);
    } else {
        clearCameraTrendCharts();
        const labels = sensors.temperature.map((d) => formatChartTimestamp(d.timestamp));
        mainCombinedChart.data.labels = labels;
        mainCombinedChart.data.datasets[0].data = sensors.temperature.map(d => d.value);
        mainCombinedChart.data.datasets[1].data = sensors.humidity.map(d => d.value);
        mainCombinedChart.update();
    }

    if (showPerCameraTelemetry) {
        renderTelemetryByCameraCharts(telemetrySeries);
    } else {
        clearTelemetryByCameraCharts();
        updateSingleTelemetryCharts(telemetrySeries, sensors);
    }
}

function updateSingleTelemetryCharts(telemetrySeries, fallbackSensors) {
    const seriesItem = telemetrySeries[0];
    const series = seriesItem?.series || {};

    updateSingleTelemetryChart(tempChart, series.temperature || fallbackSensors.temperature);
    updateSingleTelemetryChart(humChart, series.humidity || fallbackSensors.humidity);
    updateSingleTelemetryChart(battChart, series.battery || fallbackSensors.battery);
}

function updateSingleTelemetryChart(chart, seriesRows) {
    chart.data.labels = seriesRows.map((row) => formatChartTimestamp(row.timestamp));
    chart.data.datasets[0].data = seriesRows.map((row) => row.value);
    chart.update();
}

function toggleOverviewTrendMode(showPerCameraCharts) {
    document.getElementById('mainOverviewChartContainer').classList.toggle('hidden', showPerCameraCharts);
    document.getElementById('cameraTrendSection').classList.toggle('hidden', !showPerCameraCharts);
}

function clearCameraTrendCharts() {
    overviewCameraCharts.forEach((chart) => chart.destroy());
    overviewCameraCharts = [];
    document.getElementById('cameraTrendGrid').innerHTML = '';
}

function renderCameraTrendCharts(overviewData) {
    clearCameraTrendCharts();

    const grid = document.getElementById('cameraTrendGrid');
    overviewData
        .filter((item) => item.trend?.temperature?.length || item.trend?.humidity?.length)
        .sort((left, right) => getDeviceLabel(left.serial).localeCompare(getDeviceLabel(right.serial)))
        .forEach((item, index) => {
            const chartId = `cameraTrendChart-${index}`;
            const card = document.createElement('div');
            card.className = 'chart-container overview-chart-card';
            card.innerHTML = `
                <div class="chart-header">
                    <h3>${escapeHtml(getDeviceLabel(item.serial))}</h3>
                </div>
                <div class="chart-body">
                    <canvas id="${chartId}"></canvas>
                </div>
            `;
            grid.appendChild(card);

            const temperatureTrend = [...(item.trend?.temperature || [])].reverse();
            const humidityTrend = [...(item.trend?.humidity || [])].reverse();
            const labelSource = temperatureTrend.length ? temperatureTrend : humidityTrend;
            const labels = labelSource.map((row) => formatChartTimestamp(row.timestamp));
            const chart = new Chart(document.getElementById(chartId), {
                type: 'line',
                data: {
                    labels,
                    datasets: [
                        { label: 'Temp', borderColor: CHART_COLORS.temperature, data: temperatureTrend.map((row) => row.value), yAxisID: 'y' },
                        { label: 'Humidity', borderColor: CHART_COLORS.humidity, data: humidityTrend.map((row) => row.value), yAxisID: 'y1' }
                    ]
                },
                options: overviewChartOptions
            });
            overviewCameraCharts.push(chart);
        });
}

function clearTelemetryByCameraCharts() {
    telemetryCameraCharts.forEach((chart) => chart.destroy());
    telemetryCameraCharts = [];
    document.getElementById('telemetryByCameraGrid').innerHTML = '';
    document.getElementById('telemetryByCameraSection').classList.add('hidden');
    document.getElementById('mainTelemetryCharts').classList.remove('hidden');
}

function renderTelemetryByCameraCharts(telemetrySeries) {
    clearTelemetryByCameraCharts();

    const grid = document.getElementById('telemetryByCameraGrid');
    const section = document.getElementById('telemetryByCameraSection');
    const mainCharts = document.getElementById('mainTelemetryCharts');

    if (telemetrySeries.length <= 1) {
        return;
    }

    section.classList.remove('hidden');
    mainCharts.classList.add('hidden');

    telemetrySeries
        .slice()
        .sort((left, right) => getDeviceLabel(left.serial).localeCompare(getDeviceLabel(right.serial)))
        .forEach((item, index) => {
            const tempChartId = `telemetry-camera-temp-${index}`;
            const humChartId = `telemetry-camera-hum-${index}`;
            const battChartId = `telemetry-camera-batt-${index}`;

            const card = document.createElement('article');
            card.className = 'telemetry-camera-card';
            card.innerHTML = `
                <div class="telemetry-camera-card-header">
                    <h3>${escapeHtml(getDeviceLabel(item.serial))}</h3>
                    <span>Serial: ${escapeHtml(item.serial)}</span>
                </div>
                <div class="telemetry-camera-charts">
                    ${renderTelemetryCameraChartShell('Temperature (°C)', tempChartId)}
                    ${renderTelemetryCameraChartShell('Humidity (%)', humChartId)}
                    ${renderTelemetryCameraChartShell('Battery (V)', battChartId)}
                </div>
            `;
            grid.appendChild(card);

            telemetryCameraCharts.push(
                createTelemetrySensorChart(tempChartId, item.series?.temperature || [], 'Temperature (°C)', CHART_COLORS.temperature),
                createTelemetrySensorChart(humChartId, item.series?.humidity || [], 'Humidity (%)', CHART_COLORS.humidity),
                createTelemetrySensorChart(battChartId, item.series?.battery || [], 'Battery (V)', CHART_COLORS.battery)
            );
        });
}

function renderTelemetryCameraChartShell(title, chartId) {
    return `
        <div class="telemetry-camera-chart">
            <div class="chart-header"><h4>${title}</h4></div>
            <div class="chart-body"><canvas id="${chartId}"></canvas></div>
        </div>
    `;
}

function createTelemetrySensorChart(chartId, sensorRows, label, color) {
    return new Chart(document.getElementById(chartId), {
        type: 'line',
        data: {
            labels: sensorRows.map((row) => formatChartTimestamp(row.timestamp)),
            datasets: [{
                label,
                borderColor: color,
                backgroundColor: `${color}22`,
                fill: true,
                data: sensorRows.map((row) => row.value)
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom' } },
            scales: { x: { display: false } }
        }
    });
}

function formatChartTimestamp(timestamp) {
    if (!timestamp) {
        return '';
    }

    return chartTimestampFormatter.format(new Date(timestamp));
}

function getAllCharts() {
    return [
        mainCombinedChart,
        tempChart,
        humChart,
        battChart,
        ...overviewCameraCharts,
        ...telemetryCameraCharts
    ].filter(Boolean);
}

function resizeVisibleCharts() {
    getAllCharts().forEach((chart) => {
        chart.resize();
        chart.update('none');
    });
}

function updateTable(data) {
    const tbody = document.querySelector('#logsTable tbody');
    tbody.innerHTML = '';
    data.slice(0, 100).forEach(row => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${row.device_name}</strong></td>
            <td>${new Date(row.timestamp).toLocaleString()}</td>
            <td><span class="badge ${row.sensor_type}">${row.sensor_type}</span></td>
            <td>${row.value}</td>
            <td>${row.unit}</td>
        `;
        tbody.appendChild(tr);
    });
}

function updateGallery(images) {
    const grid = document.getElementById('imageGrid');
    grid.innerHTML = '';
    images.forEach(img => {
        // Ensure the URL is prefixed with API_BASE if it's not already
        const imageUrl = img.url.startsWith(API_BASE) ? img.url : `${API_BASE}${img.url}`;
        
        const card = document.createElement('div');
        card.className = 'image-card';
        card.innerHTML = `
            <img src="${imageUrl}" alt="${img.name}" loading="lazy">
            <div class="image-info">
                <strong>${img.name}</strong>
                <small>${img.last_modified}</small>
            </div>
        `;
        card.onclick = () => showImage(imageUrl, img.name);
        grid.appendChild(card);
    });
}

function showImage(url, name) {
    const modal = document.getElementById('imageModal');
    const modalImg = document.getElementById('imgPreview');
    const captionText = document.getElementById('caption');
    modal.style.display = "block";
    modalImg.src = url;
    captionText.innerHTML = name;
}
