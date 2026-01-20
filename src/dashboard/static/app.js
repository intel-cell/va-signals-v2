/**
 * VA Signals Dashboard
 * Frontend application for monitoring VA document processing
 */

// Configuration
const CONFIG = {
    refreshInterval: 60000, // 60 seconds
    apiBase: '/api',
    dateFormat: {
        full: { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' },
        time: { hour: '2-digit', minute: '2-digit' }
    }
};

// State management
const state = {
    runs: [],
    stats: null,
    frDocuments: [],
    ecfrDocuments: [],
    health: null,
    errors: [],
    charts: {
        runsChart: null,
        statusChart: null
    },
    refreshTimer: null
};

// DOM Elements
const elements = {
    lastRefreshTime: document.getElementById('last-refresh-time'),
    totalRuns: document.getElementById('total-runs'),
    successRate: document.getElementById('success-rate'),
    newDocs: document.getElementById('new-docs'),
    lastError: document.getElementById('last-error'),
    runsCount: document.getElementById('runs-count'),
    runsTbody: document.getElementById('runs-tbody'),
    frTbody: document.getElementById('fr-tbody'),
    ecfrTbody: document.getElementById('ecfr-tbody'),
    errorModal: document.getElementById('error-modal'),
    errorDetails: document.getElementById('error-details'),
    modalClose: document.getElementById('modal-close')
};

// Utility Functions
function formatRelativeTime(dateString) {
    if (!dateString) return '--';

    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffSecs < 60) return 'Just now';
    if (diffMins < 60) return `${diffMins} min${diffMins > 1 ? 's' : ''} ago`;
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;

    return date.toLocaleDateString('en-US', CONFIG.dateFormat.full);
}

function formatDateTime(dateString) {
    if (!dateString) return '--';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', CONFIG.dateFormat.full);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getSourceClass(sourceId) {
    if (!sourceId) return 'default';
    const source = sourceId.toLowerCase();
    if (source.includes('fr') || source.includes('federal_register')) return 'fr';
    if (source.includes('ecfr')) return 'ecfr';
    if (source.includes('va')) return 'va';
    return 'default';
}

function getStatusClass(status) {
    if (!status) return 'no-data';
    switch (status.toUpperCase()) {
        case 'SUCCESS': return 'success';
        case 'ERROR': return 'error';
        case 'NO_DATA': return 'no-data';
        default: return 'no-data';
    }
}

// API Functions
async function fetchApi(endpoint) {
    try {
        const response = await fetch(`${CONFIG.apiBase}${endpoint}`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`Error fetching ${endpoint}:`, error);
        return null;
    }
}

// Data Loading Functions
async function loadRuns() {
    const data = await fetchApi('/runs');
    if (data) {
        state.runs = Array.isArray(data) ? data : (data.runs || []);
        renderRunsTable();
    }
}

async function loadStats() {
    const data = await fetchApi('/runs/stats');
    if (data) {
        state.stats = data;
        updateHealthCards();
        updateCharts();
    }
}

async function loadFrDocuments() {
    const data = await fetchApi('/documents/fr');
    if (data) {
        state.frDocuments = Array.isArray(data) ? data : (data.documents || []);
        renderFrTable();
    }
}

async function loadEcfrDocuments() {
    const data = await fetchApi('/documents/ecfr');
    if (data) {
        state.ecfrDocuments = Array.isArray(data) ? data : (data.documents || []);
        renderEcfrTable();
    }
}

async function loadHealth() {
    const data = await fetchApi('/health');
    if (data) {
        state.health = data;
    }
}

async function loadErrors() {
    const data = await fetchApi('/errors');
    if (data) {
        state.errors = Array.isArray(data) ? data : (data.errors || []);
        updateLastError();
    }
}

// Render Functions
function updateHealthCards() {
    const stats = state.stats;

    // Total runs today
    const runsToday = stats?.runs_today ?? stats?.total_runs_today ?? '--';
    elements.totalRuns.textContent = runsToday;

    // Success rate
    let successRate = stats?.success_rate ?? stats?.success_percentage;
    if (successRate !== null && successRate !== undefined) {
        const rateValue = typeof successRate === 'number' ? successRate : parseFloat(successRate);
        elements.successRate.textContent = `${rateValue.toFixed(1)}%`;

        // Color coding
        elements.successRate.classList.remove('success-high', 'success-medium', 'success-low');
        if (rateValue >= 90) {
            elements.successRate.classList.add('success-high');
        } else if (rateValue >= 70) {
            elements.successRate.classList.add('success-medium');
        } else {
            elements.successRate.classList.add('success-low');
        }
    } else {
        elements.successRate.textContent = '--%';
    }

    // New docs today
    const newDocs = stats?.new_docs_today ?? stats?.documents_today ?? '--';
    elements.newDocs.textContent = newDocs;
}

function updateLastError() {
    if (state.errors && state.errors.length > 0) {
        const lastError = state.errors[0];
        const errorTime = lastError.created_at || lastError.timestamp;
        elements.lastError.textContent = formatRelativeTime(errorTime);
        elements.lastError.style.color = 'var(--error)';
    } else {
        elements.lastError.textContent = 'None';
        elements.lastError.style.color = 'var(--success)';
    }
}

function renderRunsTable() {
    const runs = state.runs.slice(0, 20);
    elements.runsCount.textContent = `${runs.length} runs`;

    if (runs.length === 0) {
        elements.runsTbody.innerHTML = `
            <tr class="empty-state-row">
                <td colspan="5" class="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M12 6v6l4 2"/>
                    </svg>
                    <p>No runs recorded yet</p>
                </td>
            </tr>
        `;
        return;
    }

    elements.runsTbody.innerHTML = runs.map(run => {
        const sourceClass = getSourceClass(run.source_id);
        const statusClass = getStatusClass(run.status);
        const hasErrors = run.error_message || run.errors;

        return `
            <tr>
                <td>
                    <span class="source-badge ${sourceClass}">
                        <span class="source-icon"></span>
                        ${escapeHtml(run.source_id || 'Unknown')}
                    </span>
                </td>
                <td>
                    <span class="status-badge ${statusClass}">
                        ${escapeHtml(run.status || 'UNKNOWN')}
                    </span>
                </td>
                <td>${formatRelativeTime(run.started_at || run.created_at)}</td>
                <td>${run.records_fetched ?? run.record_count ?? '--'}</td>
                <td>
                    ${hasErrors
                        ? `<button class="error-btn" onclick="showErrorDetails('${escapeHtml(run.error_message || run.errors || '')}')">View</button>`
                        : '<span class="no-errors">--</span>'
                    }
                </td>
            </tr>
        `;
    }).join('');
}

function renderFrTable() {
    const docs = state.frDocuments.slice(0, 50);

    if (docs.length === 0) {
        elements.frTbody.innerHTML = `
            <tr class="empty-state-row">
                <td colspan="3" class="empty-state">
                    <p>No FR documents found</p>
                </td>
            </tr>
        `;
        return;
    }

    elements.frTbody.innerHTML = docs.map(doc => {
        const docId = doc.doc_id || doc.document_id || doc.id;
        const sourceUrl = doc.source_url || doc.url;

        return `
            <tr>
                <td>
                    <span class="source-badge fr">
                        <span class="source-icon"></span>
                        ${escapeHtml(docId)}
                    </span>
                </td>
                <td>${formatRelativeTime(doc.first_seen_at || doc.created_at)}</td>
                <td>
                    ${sourceUrl
                        ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer" class="doc-link truncate" title="${escapeHtml(sourceUrl)}">${escapeHtml(sourceUrl)}</a>`
                        : '--'
                    }
                </td>
            </tr>
        `;
    }).join('');
}

function renderEcfrTable() {
    const docs = state.ecfrDocuments;

    if (docs.length === 0) {
        elements.ecfrTbody.innerHTML = `
            <tr class="empty-state-row">
                <td colspan="3" class="empty-state">
                    <p>No eCFR tracking data found</p>
                </td>
            </tr>
        `;
        return;
    }

    elements.ecfrTbody.innerHTML = docs.map(doc => {
        return `
            <tr>
                <td>${escapeHtml(doc.title || doc.name || '--')}</td>
                <td>${formatDateTime(doc.last_modified || doc.modified_at)}</td>
                <td>${formatRelativeTime(doc.checked_at || doc.last_checked)}</td>
            </tr>
        `;
    }).join('');
}

// Chart Functions
function updateCharts() {
    updateRunsChart();
    updateStatusChart();
}

function updateRunsChart() {
    const ctx = document.getElementById('runs-chart');
    if (!ctx) return;

    // Get runs by day data from stats or generate from runs
    let labels = [];
    let data = [];

    if (state.stats?.runs_by_day) {
        const runsByDay = state.stats.runs_by_day;
        labels = Object.keys(runsByDay).slice(-7);
        data = labels.map(day => runsByDay[day] || 0);
    } else {
        // Generate last 7 days
        for (let i = 6; i >= 0; i--) {
            const date = new Date();
            date.setDate(date.getDate() - i);
            labels.push(date.toLocaleDateString('en-US', { weekday: 'short' }));
            data.push(Math.floor(Math.random() * 20) + 5); // Placeholder
        }
    }

    if (state.charts.runsChart) {
        state.charts.runsChart.data.labels = labels;
        state.charts.runsChart.data.datasets[0].data = data;
        state.charts.runsChart.update();
        return;
    }

    state.charts.runsChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Runs',
                data: data,
                backgroundColor: 'rgba(59, 130, 246, 0.7)',
                borderColor: 'rgba(59, 130, 246, 1)',
                borderWidth: 1,
                borderRadius: 4,
                barThickness: 20
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: '#64748b'
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(51, 65, 85, 0.5)'
                    },
                    ticks: {
                        color: '#64748b',
                        stepSize: 5
                    }
                }
            }
        }
    });
}

function updateStatusChart() {
    const ctx = document.getElementById('status-chart');
    if (!ctx) return;

    let statusData = { success: 0, no_data: 0, error: 0 };

    if (state.stats?.status_distribution) {
        statusData = state.stats.status_distribution;
    } else if (state.runs.length > 0) {
        state.runs.forEach(run => {
            const status = (run.status || '').toLowerCase();
            if (status === 'success') statusData.success++;
            else if (status === 'error') statusData.error++;
            else statusData.no_data++;
        });
    }

    const data = [statusData.success || 0, statusData.no_data || 0, statusData.error || 0];

    if (state.charts.statusChart) {
        state.charts.statusChart.data.datasets[0].data = data;
        state.charts.statusChart.update();
        return;
    }

    state.charts.statusChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Success', 'No Data', 'Error'],
            datasets: [{
                data: data,
                backgroundColor: [
                    '#10b981',
                    '#6b7280',
                    '#ef4444'
                ],
                borderColor: '#1e293b',
                borderWidth: 3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#94a3b8',
                        padding: 15,
                        usePointStyle: true,
                        pointStyle: 'circle'
                    }
                }
            }
        }
    });
}

// Modal Functions
function showErrorDetails(errorText) {
    elements.errorDetails.innerHTML = `<pre class="error-text">${escapeHtml(errorText)}</pre>`;
    elements.errorModal.classList.add('active');
}

function hideErrorModal() {
    elements.errorModal.classList.remove('active');
}

// Tab Functions
function initTabs() {
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Remove active from all tabs
            tabs.forEach(t => t.classList.remove('active'));
            // Add active to clicked tab
            tab.classList.add('active');

            // Hide all tab contents
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });

            // Show selected tab content
            const tabId = tab.dataset.tab;
            document.getElementById(`${tabId}-tab`).classList.add('active');
        });
    });
}

// Refresh Functions
function updateRefreshTime() {
    const now = new Date();
    elements.lastRefreshTime.textContent = now.toLocaleTimeString('en-US', CONFIG.dateFormat.time);
}

async function refreshAll() {
    updateRefreshTime();

    // Load all data in parallel
    await Promise.all([
        loadRuns(),
        loadStats(),
        loadFrDocuments(),
        loadEcfrDocuments(),
        loadHealth(),
        loadErrors()
    ]);
}

function startAutoRefresh() {
    if (state.refreshTimer) {
        clearInterval(state.refreshTimer);
    }
    state.refreshTimer = setInterval(refreshAll, CONFIG.refreshInterval);
}

// Event Listeners
function initEventListeners() {
    // Modal close
    elements.modalClose.addEventListener('click', hideErrorModal);
    elements.errorModal.addEventListener('click', (e) => {
        if (e.target === elements.errorModal) {
            hideErrorModal();
        }
    });

    // Keyboard events
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            hideErrorModal();
        }
    });
}

// Make showErrorDetails available globally for onclick handlers
window.showErrorDetails = showErrorDetails;

// Initialize
async function init() {
    initTabs();
    initEventListeners();
    await refreshAll();
    startAutoRefresh();
}

// Start the application
document.addEventListener('DOMContentLoaded', init);
