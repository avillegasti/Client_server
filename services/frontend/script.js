const API_BASE = CONFIG.API_BASE;

// Charts
let mainCombinedChart, tempChart, humChart, battChart;

document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

function initApp() {
    setupNavigation();
    initCharts();
    loadDevices();
    loadData();

    document.getElementById('refreshBtn').addEventListener('click', loadData);
    document.getElementById('deviceSelect').addEventListener('change', loadData);
    
    // Modal
    const modal = document.getElementById('imageModal');
    const closeBtn = document.querySelector('.close-modal');
    const overlay = document.querySelector('.modal-overlay');
    
    [closeBtn, overlay].forEach(el => {
        el.onclick = () => modal.style.display = "none";
    });
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
        });
    });
}

async function loadDevices() {
    try {
        const response = await fetch(`${API_BASE}/api/telemetry/devices`);
        const devices = await response.json();
        const select = document.getElementById('deviceSelect');
        // Clear existing options except the first one (All Devices)
        while (select.options.length > 1) {
            select.remove(1);
        }

        devices.forEach(dev => {
            const opt = document.createElement('option');
            if (typeof dev === 'object' && dev !== null) {
                opt.value = dev.serial;
                opt.textContent = dev.description || dev.serial;
            } else {
                opt.value = dev;
                opt.textContent = dev;
            }
            select.appendChild(opt);
        });
    } catch (e) {
        console.error("Error loading devices:", e);
    }
}

async function loadData() {
    const device = document.getElementById('deviceSelect').value;
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;

    let query = `?limit=1000`;
    if (device) query += `&device=${device}`;
    if (startDate) query += `&start_date=${startDate}`;
    if (endDate) query += `&end_date=${endDate}`;

    try {
        const [telemetry, images] = await Promise.all([
            fetch(`${API_BASE}/api/telemetry/telemetry${query}`).then(r => r.json()),
            fetch(`${API_BASE}/api/images/images${device ? '?device=' + device : ''}`).then(r => r.json())
        ]);

        updateStats(telemetry, images);
        updateCharts(telemetry);
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
            { label: 'Temp', borderColor: '#ef4444', data: [], yAxisID: 'y' },
            { label: 'Humidity', borderColor: '#0ea5e9', data: [], yAxisID: 'y1' }
        ]},
        options: {
            ...commonOptions,
            scales: {
                x: { display: true, grid: { display: false } },
                y: { type: 'linear', position: 'left' },
                y1: { type: 'linear', position: 'right', grid: { drawOnChartArea: false } }
            }
        }
    });

    // Individual Charts
    const createChart = (id, label, color) => new Chart(document.getElementById(id), {
        type: 'line',
        data: { labels: [], datasets: [{ label, borderColor: color, backgroundColor: color + '22', fill: true, data: [] }] },
        options: commonOptions
    });

    tempChart = createChart('tempChart', 'Temperature (°C)', '#ef4444');
    humChart = createChart('humChart', 'Humidity (%)', '#0ea5e9');
    battChart = createChart('battChart', 'Battery (V)', '#10b981');
}

function updateCharts(data) {
    const sensors = {
        temperature: data.filter(d => d.sensor_type === 'temperature').reverse(),
        humidity: data.filter(d => d.sensor_type === 'humidity').reverse(),
        battery: data.filter(d => d.sensor_type === 'battery').reverse()
    };

    const labels = sensors.temperature.map(d => new Date(d.timestamp).toLocaleTimeString());

    // Update Main
    mainCombinedChart.data.labels = labels;
    mainCombinedChart.data.datasets[0].data = sensors.temperature.map(d => d.value);
    mainCombinedChart.data.datasets[1].data = sensors.humidity.map(d => d.value);
    mainCombinedChart.update();

    // Update Individual
    const update = (chart, sData) => {
        chart.data.labels = sData.map(d => new Date(d.timestamp).toLocaleTimeString());
        chart.data.datasets[0].data = sData.map(d => d.value);
        chart.update();
    };

    update(tempChart, sensors.temperature);
    update(humChart, sensors.humidity);
    update(battChart, sensors.battery);
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
        const card = document.createElement('div');
        card.className = 'image-card';
        card.innerHTML = `
            <img src="${img.url}" alt="${img.name}" loading="lazy">
            <div class="image-info">
                <strong>${img.name}</strong>
                <small>${img.last_modified}</small>
            </div>
        `;
        card.onclick = () => showImage(img.url, img.name);
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
