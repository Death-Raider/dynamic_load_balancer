// Dashboard state
let charts = {};
let statsData = null;
const ENDPOINT = '/stats'
// Chart.js default colors
const chartColors = {
    primary: 'hsl(210, 100%, 50%)',
    primaryGlow: 'hsl(210, 100%, 65%)',
    accent: 'hsl(142, 76%, 36%)',
    warning: 'hsl(38, 92%, 50%)',
    destructive: 'hsl(0, 84%, 60%)',
    muted: 'hsl(215, 20%, 65%)',
    border: 'hsl(215, 28%, 17%)',
};

// Initialize the dashboard
async function initDashboard() {
    initCharts();
    await fetchStats();
    updateDashboard();
    // initCharts();
    // Refresh every 3 seconds
    setInterval(async () => {
        await fetchStats();
        updateDashboard();
    }, 3000);
}

// Fetch stats from API
async function fetchStats() {
    try {
        const response = await fetch(ENDPOINT);
        if (!response.ok) throw new Error('Failed to fetch stats');
        statsData = await response.json();
    } catch (error) {
        console.error('Error fetching stats:', error);
        // Use mock data for testing
        statsData = generateMockData();
    }
}

// Update dashboard with new data
function updateDashboard() {
    if (!statsData) return;
    
    // Hide loading, show dashboard
    document.getElementById('loading').classList.add('hidden');
    document.getElementById('dashboard').classList.remove('hidden');
    
    // Update last update time
    document.getElementById('last-update').textContent = 
        `Updated: ${new Date().toLocaleTimeString()}`;
    
    // Update metric cards
    updateMetricCards();
    
    // Update charts
    updateCharts();
    
    // Update service instances
    updateServiceInstances();
}

// Update metric cards
function updateMetricCards() {
    const currentRPS = statsData.rps[statsData.rps.length - 1] || 0;
    const currentLatency = statsData.latency[statsData.latency.length - 1] || 0;
    const totalRequests = statsData.total_requests[statsData.total_requests.length - 1] || 0;
    
    // Calculate trends (compare last two values)
    const rpsTrend = calculateTrend(statsData.rps);
    const latencyTrend = calculateTrend(statsData.latency);
    
    document.getElementById('services-card').innerHTML = createMetricCard({
        title: 'Active Services',
        value: statsData.num_services,
        icon: 'server',
        trend: 'neutral'
    });
    
    document.getElementById('rps-card').innerHTML = createMetricCard({
        title: 'Requests/Sec',
        value: currentRPS.toFixed(1),
        change: rpsTrend.change,
        trend: rpsTrend.direction,
        icon: 'activity'
    });
    
    document.getElementById('latency-card').innerHTML = createMetricCard({
        title: 'Avg Latency',
        value: (currentLatency * 1000).toFixed(2),
        unit: 'ms',
        change: latencyTrend.change,
        trend: latencyTrend.direction === 'up' ? 'down' : latencyTrend.direction === 'down' ? 'up' : 'neutral',
        icon: 'zap'
    });
    
    document.getElementById('requests-card').innerHTML = createMetricCard({
        title: 'Total Requests',
        value: totalRequests.toLocaleString(),
        icon: 'trending-up'
    });
}

// Create metric card HTML
function createMetricCard({ title, value, unit, change, trend = 'neutral', icon }) {
    const icons = {
        server: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01"></path>',
        activity: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"></path>',
        zap: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path>',
        'trending-up': '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"></path>'
    };
    
    const trendIcons = {
        up: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18"></path>',
        down: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7m0 0l-7-7m7 7V3"></path>',
        neutral: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 12H4"></path>'
    };
    
    return `
        <div class="flex items-center justify-between mb-4">
            <p class="text-sm font-medium text-muted-foreground">${title}</p>
            <div class="metric-icon">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    ${icons[icon]}
                </svg>
            </div>
        </div>
        <div class="space-y-2">
            <div class="flex items-baseline gap-2">
                <h3 class="metric-value">${value}</h3>
                ${unit ? `<span class="text-sm text-muted-foreground">${unit}</span>` : ''}
            </div>
            ${change !== undefined ? `
                <div class="metric-change trend-${trend}">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        ${trendIcons[trend]}
                    </svg>
                    <span>${Math.abs(change).toFixed(1)}%</span>
                </div>
            ` : ''}
        </div>
    `;
}

// Update service instances
function updateServiceInstances() {
    const grid = document.getElementById('services-grid');
    grid.innerHTML = '';
    
    for (let i = 0; i < statsData.num_services; i++) {
        const cpu = statsData.cpu[i] || 0;
        const mem = statsData.mem[i] || 0;
        const threads = statsData.threads[i] || 0;
        const port = statsData.ports[i] || 'N/A';
        
        const status = cpu > 80 || mem > 80 ? 'critical' : cpu > 60 || mem > 60 ? 'warning' : 'healthy';
        
        const card = document.createElement('div');
        card.className = 'service-card';
        card.innerHTML = `
            <div class="flex items-center justify-between mb-3">
                <div class="flex items-center gap-2">
                    <div class="w-2 h-2 rounded-full status-${status}"></div>
                    <span class="text-sm font-medium text-foreground">Service ${i + 1}</span>
                </div>
                <span class="text-xs text-muted-foreground">:${port}</span>
            </div>
            <div class="space-y-3">
                <div>
                    <div class="flex justify-between text-xs text-muted-foreground mb-1">
                        <span>CPU</span>
                        <span>${cpu.toFixed(1)}%</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill progress-primary" style="width: ${cpu}%"></div>
                    </div>
                </div>
                <div>
                    <div class="flex justify-between text-xs text-muted-foreground mb-1">
                        <span>Memory</span>
                        <span>${mem.toFixed(1)}%</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill progress-accent" style="width: ${mem}%"></div>
                    </div>
                </div>
                <div class="flex justify-between text-xs text-muted-foreground">
                    <span>Threads</span>
                    <span>${threads}</span>
                </div>
            </div>
        `;
        grid.appendChild(card);
    }
}

// Initialize all charts
function initCharts() {
    // Latency Chart
    const latencyCtx = document.getElementById('latency-chart').getContext('2d');
    charts.latency = new Chart(latencyCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Latency (ms)',
                data: [],
                borderColor: chartColors.primary,
                backgroundColor: createGradient(latencyCtx, chartColors.primary),
                tension: 0.4,
                fill: true,
                pointRadius: 0,
                pointHoverRadius: 6,
            }]
        },
        options: getChartOptions('ms')
    });
    
    // RPS Chart
    const rpsCtx = document.getElementById('rps-chart').getContext('2d');
    charts.rps = new Chart(rpsCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'RPS',
                    data: [],
                    borderColor: chartColors.accent,
                    backgroundColor: createGradient(rpsCtx, chartColors.accent),
                    tension: 0.4,
                    fill: true,
                    pointRadius: 0,
                    yAxisID: 'y',
                },
                {
                    label: 'Active Services',
                    data: [],
                    borderColor: chartColors.warning,
                    backgroundColor: 'transparent',
                    tension: 0.4,
                    fill: false,
                    pointRadius: 0,
                    yAxisID: 'y1',
                    borderDash: [5, 5],
                }
            ]
        },
        options: getDualAxisChartOptions()
    });
    
    // Response Time Chart
    const responseCtx = document.getElementById('response-time-chart').getContext('2d');
    charts.responseTime = new Chart(responseCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Count',
                data: [],
                backgroundColor: createGradient(responseCtx, chartColors.warning),
                borderRadius: 8,
            }]
        },
        options: getChartOptions('')
    });
    
    // Resource Chart
    const resourceCtx = document.getElementById('resource-chart').getContext('2d');
    charts.resource = new Chart(resourceCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'CPU %',
                    data: [],
                    backgroundColor: chartColors.primary,
                    borderRadius: 8,
                },
                {
                    label: 'Memory %',
                    data: [],
                    backgroundColor: chartColors.accent,
                    borderRadius: 8,
                }
            ]
        },
        options: getChartOptions('%')
    });
}

// Update all charts with new data
function updateCharts() {
    // Update Latency Chart
    charts.latency.data.labels = statsData.ts.map(t => formatTime(t));
    charts.latency.data.datasets[0].data = statsData.latency.map(l => (l * 1000).toFixed(2));
    charts.latency.update('none');
    
    // Update RPS Chart
    charts.rps.data.labels = statsData.ts.map(t => formatTime(t));
    charts.rps.data.datasets[0].data = statsData.rps;
    charts.rps.data.datasets[1].data = statsData.services;
    charts.rps.update('none');
    
    // Update Response Time Chart
    const histogram = createHistogram(statsData.response_times, 20);
    charts.responseTime.data.labels = histogram.labels;
    charts.responseTime.data.datasets[0].data = histogram.data;
    charts.responseTime.update('none');
    
    // Update Resource Chart
    charts.resource.data.labels = statsData.ports.map((p, i) => `Service ${i + 1}`);
    charts.resource.data.datasets[0].data = statsData.cpu;
    charts.resource.data.datasets[1].data = statsData.mem;
    charts.resource.update('none');
}

// Chart configuration helpers
function getChartOptions(unit) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                labels: {
                    color: chartColors.muted,
                    font: { size: 12 }
                }
            },
            tooltip: {
                backgroundColor: 'hsl(224, 71%, 6%)',
                borderColor: chartColors.border,
                borderWidth: 1,
                titleColor: chartColors.muted,
                bodyColor: 'hsl(213, 31%, 91%)',
                callbacks: {
                    label: (context) => `${context.dataset.label}: ${context.parsed.y}${unit}`
                }
            }
        },
        scales: {
            x: {
                grid: { color: chartColors.border, opacity: 0.3 },
                ticks: { color: chartColors.muted }
            },
            y: {
                grid: { color: chartColors.border, opacity: 0.3 },
                ticks: { color: chartColors.muted }
            }
        }
    };
}

function getDualAxisChartOptions() {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                labels: {
                    color: chartColors.muted,
                    font: { size: 12 }
                }
            },
            tooltip: {
                backgroundColor: 'hsl(224, 71%, 6%)',
                borderColor: chartColors.border,
                borderWidth: 1,
                titleColor: chartColors.muted,
                bodyColor: 'hsl(213, 31%, 91%)',
            }
        },
        scales: {
            x: {
                grid: { color: chartColors.border, opacity: 0.3 },
                ticks: { color: chartColors.muted }
            },
            y: {
                type: 'linear',
                position: 'left',
                grid: { color: chartColors.border, opacity: 0.3 },
                ticks: { color: chartColors.muted }
            },
            y1: {
                type: 'linear',
                position: 'right',
                grid: { drawOnChartArea: false },
                ticks: { color: chartColors.muted }
            }
        }
    };
}

function createGradient(ctx, color) {
    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, color);
    gradient.addColorStop(1, color);
    return gradient;
}

// Utility functions
function formatTime(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function calculateTrend(data) {
    if (data.length < 2) return { change: 0, direction: 'neutral' };
    const current = data[data.length - 1];
    const previous = data[data.length - 2];
    if (previous === 0) return { change: 0, direction: 'neutral' };
    const change = ((current - previous) / previous) * 100;
    const direction = change > 0 ? 'up' : change < 0 ? 'down' : 'neutral';
    return { change: Math.abs(change), direction };
}

function createHistogram(data, bins) {
    if (!data || data.length === 0) return { labels: [], data: [] };
    
    const min = Math.min(...data);
    const max = Math.max(...data);
    const binSize = (max - min) / bins;
    
    const histogram = new Array(bins).fill(0);
    const labels = [];
    
    data.forEach(value => {
        const binIndex = Math.min(Math.floor((value - min) / binSize), bins - 1);
        histogram[binIndex]++;
    });
    
    for (let i = 0; i < bins; i++) {
        const start = (min + i * binSize).toFixed(2);
        const end = (min + (i + 1) * binSize).toFixed(2);
        labels.push(`${start}-${end}`);
    }
    
    return { labels, data: histogram };
}

// Generate mock data for testing
function generateMockData() {
    const now = Date.now();
    const points = 20;
    
    return {
        num_services: 3,
        ports: ['8080', '8081', '8082'],
        cpu: [45.2, 62.8, 38.5],
        mem_rss_mb: [512, 648, 423],
        mem: [42.3, 58.1, 35.7],
        threads: [12, 16, 10],
        ts: Array.from({ length: points }, (_, i) => new Date(now - (points - i) * 10000)),
        latency: Array.from({ length: points }, () => Math.random() * 0.05 + 0.01),
        rps: Array.from({ length: points }, () => Math.random() * 100 + 50),
        services: Array.from({ length: points }, () => Math.floor(Math.random() * 2) + 2),
        total_requests: Array.from({ length: points }, (_, i) => 1000 + i * 100),
        response_times: Array.from({ length: 100 }, () => Math.random() * 0.5)
    };
}

// Start the dashboard when page loads
document.addEventListener('DOMContentLoaded', initDashboard);
