/**
 * VA Signals Dashboard
 * Frontend application for monitoring VA document processing
 */

// Configuration
const CONFIG = {
    refreshInterval: 60000, // 60 seconds
    apiBase: '/api',
    wsBase: `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`,
    dateFormat: {
        full: { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' },
        time: { hour: '2-digit', minute: '2-digit' }
    },
    toastDuration: 5000
};

// State management
const state = {
    runs: [],
    stats: null,
    frDocuments: [],
    frDocumentsFiltered: [],
    ecfrDocuments: [],
    health: null,
    errors: [],
    summaries: [],
    summarizedDocIds: new Set(),
    driftEvents: [],
    driftStats: null,
    bills: [],
    billStats: null,
    hearings: [],
    hearingStats: null,
    // Oversight monitor
    oversightStats: null,
    oversightEvents: [],
    // State monitor
    stateStats: null,
    stateSignals: [],
    stateRuns: [],
    stateFilter: 'all',
    // Battlefield dashboard
    battlefieldStats: null,
    battlefieldVehicles: [],
    battlefieldCriticalGates: [],
    battlefieldAlerts: [],
    activeMainTab: 'federal',
    charts: {
        runsChart: null,
        statusChart: null
    },
    refreshTimer: null,
    ws: null,
    wsReconnectTimer: null,
    filters: {
        fr: {
            search: '',
            type: '',
            dateFrom: '',
            dateTo: ''
        }
    },
    loading: {
        runs: true,
        stats: true,
        frDocs: true,
        ecfrDocs: true,
        summaries: true,
        drift: true,
        bills: true,
        hearings: true,
        oversightStats: true,
        oversightEvents: true,
        stateStats: true,
        stateSignals: true,
        stateRuns: true,
        battlefieldStats: true,
        battlefieldVehicles: true,
        battlefieldCriticalGates: true,
        battlefieldAlerts: true
    }
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
    modalClose: document.getElementById('modal-close'),
    summariesFeed: document.getElementById('summaries-feed'),
    summariesCount: document.getElementById('summaries-count'),
    summaryModal: document.getElementById('summary-modal'),
    summaryDetails: document.getElementById('summary-details'),
    summaryModalClose: document.getElementById('summary-modal-close'),
    reportsBtn: document.getElementById('reports-btn'),
    reportsDropdown: document.querySelector('.reports-dropdown'),
    toastContainer: document.getElementById('toast-container'),
    // Filter elements
    frSearch: document.getElementById('fr-search'),
    frTypeFilter: document.getElementById('fr-type-filter'),
    frDateFrom: document.getElementById('fr-date-from'),
    frDateTo: document.getElementById('fr-date-to'),
    clearFrFilters: document.getElementById('clear-fr-filters'),
    exportFrCsv: document.getElementById('export-fr-csv'),
    exportSummariesCsv: document.getElementById('export-summaries-csv'),
    frResultsCount: document.getElementById('fr-results-count'),
    // Agenda drift elements
    driftCount: document.getElementById('drift-count'),
    driftMembers: document.getElementById('drift-members'),
    driftUtterances: document.getElementById('drift-utterances'),
    driftBaselines: document.getElementById('drift-baselines'),
    driftEvents: document.getElementById('drift-events'),
    // Bills elements
    billsCount: document.getElementById('bills-count'),
    billsTotal: document.getElementById('bills-total'),
    billsNewWeek: document.getElementById('bills-new-week'),
    billsTbody: document.getElementById('bills-tbody'),
    // Hearings elements
    hearingsCount: document.getElementById('hearings-count'),
    hearingsHvac: document.getElementById('hearings-hvac'),
    hearingsSvac: document.getElementById('hearings-svac'),
    hearingsTotal: document.getElementById('hearings-total'),
    hearingsList: document.getElementById('hearings-list'),
    // Oversight elements
    oversightTotalEvents: document.getElementById('oversight-total-events'),
    oversightEscalations: document.getElementById('oversight-escalations'),
    oversightDeviations: document.getElementById('oversight-deviations'),
    oversightSurfaced: document.getElementById('oversight-surfaced'),
    oversightLastEvent: document.getElementById('oversight-last-event'),
    oversightEventsTbody: document.getElementById('oversight-events-tbody'),
    oversightEventsCount: document.getElementById('oversight-events-count'),
    oversightSourceList: document.getElementById('oversight-source-list'),
    // State monitor elements
    stateTotalSignals: document.getElementById('state-total-signals'),
    stateHighSeverity: document.getElementById('state-high-severity'),
    stateLastRun: document.getElementById('state-last-run'),
    stateNewSignals: document.getElementById('state-new-signals'),
    txBar: document.getElementById('tx-bar'),
    txCount: document.getElementById('tx-count'),
    flBar: document.getElementById('fl-bar'),
    flCount: document.getElementById('fl-count'),
    caBar: document.getElementById('ca-bar'),
    caCount: document.getElementById('ca-count'),
    sevHigh: document.getElementById('sev-high'),
    sevMedium: document.getElementById('sev-medium'),
    sevLow: document.getElementById('sev-low'),
    sevNoise: document.getElementById('sev-noise'),
    stateSignalsTbody: document.getElementById('state-signals-tbody'),
    stateRunsTbody: document.getElementById('state-runs-tbody'),
    stateRunsCount: document.getElementById('state-runs-count')
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

function renderFlagBadge(value) {
    return `<span class="flag-badge ${value ? 'yes' : 'no'}">${value ? 'Yes' : 'No'}</span>`;
}

// Toast Notification System
function showToast(type, title, message) {
    if (!elements.toastContainer) return;

    const icons = {
        success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <div class="toast-content">
            <div class="toast-title">${escapeHtml(title)}</div>
            ${message ? `<div class="toast-message">${escapeHtml(message)}</div>` : ''}
        </div>
        <button class="toast-close">&times;</button>
    `;

    const closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', () => removeToast(toast));

    elements.toastContainer.appendChild(toast);

    // Auto-remove after duration
    setTimeout(() => removeToast(toast), CONFIG.toastDuration);
}

function removeToast(toast) {
    if (!toast || !toast.parentNode) return;
    toast.classList.add('toast-exit');
    setTimeout(() => {
        if (toast.parentNode) {
            toast.parentNode.removeChild(toast);
        }
    }, 300);
}

// Skeleton Loading Functions
function renderSkeletonRows(count, columns) {
    const sizes = ['medium', 'large', 'small', 'medium', 'small'];
    return Array(count).fill(0).map(() => `
        <tr class="skeleton-row">
            ${Array(columns).fill(0).map((_, i) => `
                <td><div class="skeleton skeleton-cell ${sizes[i % sizes.length]}"></div></td>
            `).join('')}
        </tr>
    `).join('');
}

function renderSkeletonCards(count) {
    return Array(count).fill(0).map(() => `
        <div class="skeleton-card">
            <div class="skeleton skeleton-line short"></div>
            <div class="skeleton skeleton-line full"></div>
            <div class="skeleton skeleton-line medium"></div>
        </div>
    `).join('');
}

// CSV Export Functions
function downloadCsv(data, filename) {
    const blob = new Blob([data], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

function escapeCsvValue(value) {
    if (value === null || value === undefined) return '';
    const str = String(value);
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
        return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
}

function exportFrDocumentsToCsv() {
    const docs = state.frDocumentsFiltered.length > 0 ? state.frDocumentsFiltered : state.frDocuments;
    if (docs.length === 0) {
        showToast('warning', 'No Data', 'No documents to export');
        return;
    }

    const headers = ['doc_id', 'published_date', 'first_seen_at', 'has_summary', 'source_url'];
    const rows = docs.map(doc => {
        const docId = doc.doc_id || doc.document_id || doc.id;
        return [
            escapeCsvValue(docId),
            escapeCsvValue(doc.published_date),
            escapeCsvValue(doc.first_seen_at || doc.created_at),
            state.summarizedDocIds.has(docId) ? 'Yes' : 'No',
            escapeCsvValue(doc.source_url || doc.url)
        ].join(',');
    });

    const csv = [headers.join(','), ...rows].join('\n');
    const date = new Date().toISOString().split('T')[0];
    downloadCsv(csv, `fr-documents-${date}.csv`);
    showToast('success', 'Export Complete', `Exported ${docs.length} documents`);
}

function exportSummariesToCsv() {
    if (state.summaries.length === 0) {
        showToast('warning', 'No Data', 'No summaries to export');
        return;
    }

    const headers = ['doc_id', 'summary', 'bullet_points', 'veteran_impact', 'tags', 'summarized_at', 'source_url'];
    const rows = state.summaries.map(s => [
        escapeCsvValue(s.doc_id),
        escapeCsvValue(s.summary),
        escapeCsvValue((s.bullet_points || []).join('; ')),
        escapeCsvValue(s.veteran_impact),
        escapeCsvValue((s.tags || []).join(', ')),
        escapeCsvValue(s.summarized_at),
        escapeCsvValue(s.source_url)
    ].join(','));

    const csv = [headers.join(','), ...rows].join('\n');
    const date = new Date().toISOString().split('T')[0];
    downloadCsv(csv, `summaries-${date}.csv`);
    showToast('success', 'Export Complete', `Exported ${state.summaries.length} summaries`);
}

// Filter Functions
function applyFrFilters() {
    const { search, type, dateFrom, dateTo } = state.filters.fr;
    let filtered = [...state.frDocuments];

    // Search filter
    if (search) {
        const searchLower = search.toLowerCase();
        filtered = filtered.filter(doc => {
            const docId = (doc.doc_id || doc.document_id || doc.id || '').toLowerCase();
            const url = (doc.source_url || '').toLowerCase();
            return docId.includes(searchLower) || url.includes(searchLower);
        });
    }

    // Type filter (would need doc type in data, placeholder for now)
    // if (type) {
    //     filtered = filtered.filter(doc => doc.type === type);
    // }

    // Date filters
    if (dateFrom) {
        const fromDate = new Date(dateFrom);
        filtered = filtered.filter(doc => {
            const docDate = new Date(doc.published_date || doc.first_seen_at);
            return docDate >= fromDate;
        });
    }

    if (dateTo) {
        const toDate = new Date(dateTo);
        toDate.setHours(23, 59, 59, 999);
        filtered = filtered.filter(doc => {
            const docDate = new Date(doc.published_date || doc.first_seen_at);
            return docDate <= toDate;
        });
    }

    state.frDocumentsFiltered = filtered;
    renderFrTable();

    // Update results count
    if (elements.frResultsCount) {
        const total = state.frDocuments.length;
        const shown = filtered.length;
        elements.frResultsCount.textContent = search || dateFrom || dateTo ?
            `${shown} of ${total}` : '';
    }
}

function clearFrFilters() {
    state.filters.fr = { search: '', type: '', dateFrom: '', dateTo: '' };
    if (elements.frSearch) elements.frSearch.value = '';
    if (elements.frTypeFilter) elements.frTypeFilter.value = '';
    if (elements.frDateFrom) elements.frDateFrom.value = '';
    if (elements.frDateTo) elements.frDateTo.value = '';
    state.frDocumentsFiltered = [];
    renderFrTable();
    if (elements.frResultsCount) elements.frResultsCount.textContent = '';
}

// WebSocket Functions
function connectWebSocket() {
    // Check if WebSocket endpoint exists before connecting
    if (state.ws && state.ws.readyState === WebSocket.OPEN) return;

    try {
        state.ws = new WebSocket(CONFIG.wsBase);

        state.ws.onopen = () => {
            console.log('WebSocket connected');
            showToast('success', 'Connected', 'Real-time updates enabled');
            // Clear any reconnect timer
            if (state.wsReconnectTimer) {
                clearTimeout(state.wsReconnectTimer);
                state.wsReconnectTimer = null;
            }
        };

        state.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
            } catch (e) {
                console.error('WebSocket message parse error:', e);
            }
        };

        state.ws.onclose = () => {
            console.log('WebSocket disconnected');
            // Schedule reconnection
            if (!state.wsReconnectTimer) {
                state.wsReconnectTimer = setTimeout(() => {
                    state.wsReconnectTimer = null;
                    connectWebSocket();
                }, 5000);
            }
        };

        state.ws.onerror = (error) => {
            console.log('WebSocket error (will fallback to polling):', error);
            // Don't show error toast - silently fallback to polling
        };
    } catch (e) {
        console.log('WebSocket not available, using polling');
    }
}

function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'new_run':
            // Add new run to the beginning
            state.runs.unshift(data.run);
            state.runs = state.runs.slice(0, 50); // Keep max 50
            renderRunsTable();
            showToast('info', 'New Run', `${data.run.source_id}: ${data.run.status}`);
            break;

        case 'new_document':
            state.frDocuments.unshift(data.document);
            renderFrTable();
            showToast('info', 'New Document', data.document.doc_id);
            break;

        case 'new_summary':
            state.summaries.unshift(data.summary);
            state.summarizedDocIds.add(data.summary.doc_id);
            renderSummariesFeed();
            renderFrTable(); // Update summary badges
            showToast('success', 'New Summary', data.summary.doc_id);
            break;

        case 'stats_update':
            state.stats = data.stats;
            updateHealthCards();
            updateCharts();
            break;

        case 'error':
            showToast('error', 'Error', data.message);
            break;

        default:
            console.log('Unknown WebSocket message type:', data.type);
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
    state.loading.runs = true;
    renderRunsTable(); // Show skeleton
    const data = await fetchApi('/runs');
    state.loading.runs = false;
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
    state.loading.frDocs = true;
    renderFrTable(); // Show skeleton
    const data = await fetchApi('/documents/fr');
    state.loading.frDocs = false;
    if (data) {
        state.frDocuments = Array.isArray(data) ? data : (data.documents || []);
        state.frDocumentsFiltered = [];
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
        state.errors = Array.isArray(data) ? data : (data.error_runs || data.errors || []);
        updateLastError();
    }
}

async function loadSummaries() {
    state.loading.summaries = true;
    renderSummariesFeed(); // Show skeleton
    const data = await fetchApi('/summaries');
    state.loading.summaries = false;
    if (data) {
        state.summaries = Array.isArray(data) ? data : (data.summaries || []);
        renderSummariesFeed();
    }
}

async function loadSummarizedDocIds() {
    const data = await fetchApi('/summaries/doc-ids');
    if (data && data.doc_ids) {
        state.summarizedDocIds = new Set(data.doc_ids);
    }
}

async function loadDriftEvents() {
    state.loading.drift = true;
    renderDriftEvents();
    const data = await fetchApi('/agenda-drift/events?limit=20');
    state.loading.drift = false;
    if (data) {
        state.driftEvents = data.events || [];
        renderDriftEvents();
    }
}

async function loadDriftStats() {
    const data = await fetchApi('/agenda-drift/stats');
    if (data) {
        state.driftStats = data;
        updateDriftStats();
    }
}

async function loadBills() {
    state.loading.bills = true;
    renderBillsTable();
    const data = await fetchApi('/bills?limit=50');
    state.loading.bills = false;
    if (data) {
        state.bills = data.bills || [];
        renderBillsTable();
    }
}

async function loadBillStats() {
    const data = await fetchApi('/bills/stats');
    if (data) {
        state.billStats = data;
        updateBillStats();
    }
}

async function loadHearings() {
    state.loading.hearings = true;
    renderHearings();
    const data = await fetchApi('/hearings?upcoming=true&limit=20');
    state.loading.hearings = false;
    if (data) {
        state.hearings = data.hearings || [];
        renderHearings();
    }
}

async function loadHearingStats() {
    const data = await fetchApi('/hearings/stats');
    if (data) {
        state.hearingStats = data;
        updateHearingStats();
    }
}

// Render Functions
function updateHealthCards() {
    const stats = state.stats;

    // Total runs today
    const runsToday = stats?.runs_today ?? stats?.total_runs_today ?? '--';
    elements.totalRuns.textContent = runsToday;

    // Healthy rate (SUCCESS + NO_DATA = runs without errors)
    let healthyRate = stats?.healthy_rate ?? stats?.success_rate;
    if (healthyRate !== null && healthyRate !== undefined) {
        const rateValue = typeof healthyRate === 'number' ? healthyRate : parseFloat(healthyRate);
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
        const errorTime = lastError.ended_at || lastError.created_at || lastError.timestamp;
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

    elements.runsTbody.innerHTML = runs.map((run, index) => {
        const sourceClass = getSourceClass(run.source_id);
        const statusClass = getStatusClass(run.status);
        // Handle errors array properly - check length, not just truthiness
        const errorsArray = Array.isArray(run.errors) ? run.errors : [];
        const errorText = run.error_message || (errorsArray.length > 0 ? errorsArray.join('\n') : '');
        const hasErrors = errorText.length > 0;

        // Store error text in a data attribute to avoid escaping issues
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
                        ? `<button class="error-btn" data-error="${escapeHtml(errorText)}" onclick="showErrorFromButton(this)">View</button>`
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
                <td colspan="4" class="empty-state">
                    <p>No FR documents found</p>
                </td>
            </tr>
        `;
        return;
    }

    elements.frTbody.innerHTML = docs.map(doc => {
        const docId = doc.doc_id || doc.document_id || doc.id;
        const sourceUrl = doc.source_url || doc.url;
        const hasSummary = state.summarizedDocIds.has(docId);

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
                    ${hasSummary
                        ? `<button class="summary-badge" onclick="showSummaryModal('${escapeHtml(docId)}')">
                               <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                   <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                   <polyline points="14 2 14 8 20 8"/>
                               </svg>
                               Summary
                           </button>`
                        : '<span class="no-errors">--</span>'
                    }
                </td>
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

function renderSummariesFeed() {
    const summaries = state.summaries;

    if (!elements.summariesFeed) return;

    elements.summariesCount.textContent = `${summaries.length} summaries`;

    if (summaries.length === 0) {
        elements.summariesFeed.innerHTML = `
            <div class="empty-summaries">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                    <line x1="16" y1="13" x2="8" y2="13"/>
                    <line x1="16" y1="17" x2="8" y2="17"/>
                </svg>
                <p>No summaries available yet</p>
            </div>
        `;
        return;
    }

    elements.summariesFeed.innerHTML = summaries.map((summary, index) => {
        const docId = summary.doc_id;
        const tags = summary.tags || [];
        const bulletPoints = summary.bullet_points || [];
        const sourceUrl = summary.source_url;

        return `
            <div class="summary-card" data-doc-id="${escapeHtml(docId)}">
                <div class="summary-header">
                    <div class="summary-doc-id">
                        ${sourceUrl
                            ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(docId)}</a>`
                            : `<span>${escapeHtml(docId)}</span>`
                        }
                    </div>
                    <span class="summary-date">${formatRelativeTime(summary.summarized_at)}</span>
                </div>
                <p class="summary-text">${escapeHtml(summary.summary)}</p>
                ${tags.length > 0 ? `
                    <div class="summary-tags">
                        ${tags.map(tag => `<span class="tag ${escapeHtml(tag)}">${escapeHtml(tag)}</span>`).join('')}
                    </div>
                ` : ''}
                <button class="summary-expand" onclick="toggleSummaryDetails(${index})">
                    <span>Show details</span>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="6 9 12 15 18 9"/>
                    </svg>
                </button>
                <div class="summary-details" id="summary-details-${index}">
                    ${bulletPoints.length > 0 ? `
                        <ul class="summary-bullet-points">
                            ${bulletPoints.map(point => `<li>${escapeHtml(point)}</li>`).join('')}
                        </ul>
                    ` : ''}
                    ${summary.veteran_impact ? `
                        <div class="summary-impact">
                            <span class="summary-impact-label">Veteran Impact</span>
                            <p class="summary-impact-text">${escapeHtml(summary.veteran_impact)}</p>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }).join('');
}

function toggleSummaryDetails(index) {
    const detailsEl = document.getElementById(`summary-details-${index}`);
    const buttonEl = detailsEl?.previousElementSibling;

    if (detailsEl) {
        detailsEl.classList.toggle('visible');
        if (buttonEl) {
            buttonEl.classList.toggle('expanded');
            const spanEl = buttonEl.querySelector('span');
            if (spanEl) {
                spanEl.textContent = detailsEl.classList.contains('visible') ? 'Hide details' : 'Show details';
            }
        }
    }
}

function updateDriftStats() {
    const stats = state.driftStats;
    if (!stats) return;

    if (elements.driftMembers) {
        elements.driftMembers.textContent = stats.total_members ?? '--';
    }
    if (elements.driftUtterances) {
        elements.driftUtterances.textContent = stats.total_utterances ?? '--';
    }
    if (elements.driftBaselines) {
        elements.driftBaselines.textContent = stats.members_with_baselines ?? '--';
    }
    if (elements.driftCount) {
        const count = state.driftEvents.length;
        elements.driftCount.textContent = `${count} deviation${count !== 1 ? 's' : ''}`;
    }
}

function renderDriftEvents() {
    if (!elements.driftEvents) return;

    const events = state.driftEvents;

    if (state.loading.drift) {
        elements.driftEvents.innerHTML = '<div class="loading-state">Loading...</div>';
        return;
    }

    if (events.length === 0) {
        elements.driftEvents.innerHTML = `
            <div class="empty-drift">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                </svg>
                <p>No unusual statements detected yet</p>
                <span class="empty-drift-hint">Statements are flagged when members talk differently than usual</span>
            </div>
        `;
        return;
    }

    elements.driftEvents.innerHTML = events.map(event => {
        const zscoreClass = event.zscore >= 3 ? 'high' : event.zscore >= 2.5 ? 'medium' : 'low';
        const unusualLabel = event.zscore >= 3 ? 'Very unusual' : event.zscore >= 2.5 ? 'Unusual' : 'Slightly unusual';

        // Parse hearing ID for friendlier display (e.g., "118-senate-54761" -> "Senate Hearing #54761")
        const hearingParts = event.hearing_id.split('-');
        const chamber = hearingParts[1] === 'senate' ? 'Senate' : 'House';
        const hearingNum = hearingParts[2] || event.hearing_id;
        const hearingDisplay = `${chamber} Hearing #${hearingNum}`;

        // Build the explanation/note section if present
        const noteHtml = event.note ? `
                <div class="drift-explanation">
                    <span class="drift-explanation-label">Why flagged:</span>
                    <p class="drift-explanation-text">${escapeHtml(event.note)}</p>
                </div>
            ` : '';

        return `
            <div class="drift-event">
                <div class="drift-event-header">
                    <span class="drift-member">${escapeHtml(event.member_name)}</span>
                    <span class="drift-zscore ${zscoreClass}" title="Unusualness score: ${event.zscore.toFixed(2)} standard deviations from their normal">${unusualLabel}</span>
                </div>
                <div class="drift-event-details">
                    <span class="drift-hearing">${escapeHtml(hearingDisplay)}</span>
                    <span class="drift-time">${formatRelativeTime(event.detected_at)}</span>
                </div>${noteHtml}
            </div>
        `;
    }).join('');

    // Update count badge
    if (elements.driftCount) {
        elements.driftCount.textContent = `${events.length} flagged`;
    }
}

function updateBillStats() {
    const stats = state.billStats;
    if (!stats) return;

    if (elements.billsTotal) {
        elements.billsTotal.textContent = stats.total_bills ?? '--';
    }
    if (elements.billsNewWeek) {
        elements.billsNewWeek.textContent = stats.new_this_week ?? '--';
    }
    if (elements.billsCount) {
        const count = state.bills.length;
        elements.billsCount.textContent = `${stats.total_bills ?? count} bills`;
    }
}

function renderBillsTable() {
    if (!elements.billsTbody) return;

    const bills = state.bills;

    if (state.loading.bills) {
        elements.billsTbody.innerHTML = `
            <tr class="loading-row">
                <td colspan="5">Loading...</td>
            </tr>
        `;
        return;
    }

    if (bills.length === 0) {
        elements.billsTbody.innerHTML = `
            <tr class="empty-state-row">
                <td colspan="5" class="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                        <line x1="16" y1="13" x2="8" y2="13"/>
                        <line x1="16" y1="17" x2="8" y2="17"/>
                    </svg>
                    <p>No bills tracked yet</p>
                </td>
            </tr>
        `;
        return;
    }

    elements.billsTbody.innerHTML = bills.map(bill => {
        const billType = (bill.bill_type || '').toUpperCase();
        const billNum = bill.bill_number;
        const displayId = `${billType} ${billNum}`;

        // Map bill_type to Congress.gov URL format
        const billTypeMap = {
            'hr': 'house-bill',
            's': 'senate-bill',
            'hjres': 'house-joint-resolution',
            'sjres': 'senate-joint-resolution',
            'hres': 'house-resolution',
            'sres': 'senate-resolution',
            'hconres': 'house-concurrent-resolution',
            'sconres': 'senate-concurrent-resolution'
        };
        const urlBillType = billTypeMap[bill.bill_type.toLowerCase()] || 'bill';
        const congressUrl = `https://www.congress.gov/bill/${bill.congress}th-congress/${urlBillType}/${billNum}`;

        // Sponsor display
        let sponsorDisplay = '--';
        if (bill.sponsor_name) {
            const party = bill.sponsor_party ? ` (${bill.sponsor_party})` : '';
            const state = bill.sponsor_state ? `-${bill.sponsor_state}` : '';
            sponsorDisplay = `${escapeHtml(bill.sponsor_name)}${party}${state}`;
        }

        // Title truncation
        const titleDisplay = bill.title && bill.title.length > 80
            ? escapeHtml(bill.title.substring(0, 80)) + '...'
            : escapeHtml(bill.title || '--');

        // Latest action
        const actionDisplay = bill.latest_action_text && bill.latest_action_text.length > 60
            ? escapeHtml(bill.latest_action_text.substring(0, 60)) + '...'
            : escapeHtml(bill.latest_action_text || '--');

        return `
            <tr>
                <td>
                    <a href="${escapeHtml(congressUrl)}" target="_blank" rel="noopener noreferrer" class="bill-link">
                        ${escapeHtml(displayId)}
                    </a>
                </td>
                <td class="bill-title" title="${escapeHtml(bill.title || '')}">${titleDisplay}</td>
                <td class="bill-sponsor">${sponsorDisplay}</td>
                <td class="bill-action" title="${escapeHtml(bill.latest_action_text || '')}">${actionDisplay}</td>
                <td>${formatRelativeTime(bill.latest_action_date || bill.first_seen_at)}</td>
            </tr>
        `;
    }).join('');

    // Update count badge
    if (elements.billsCount) {
        const total = state.billStats?.total_bills ?? bills.length;
        elements.billsCount.textContent = `${total} bills`;
    }
}

function formatHearingDate(dateString) {
    if (!dateString) return '--';
    const date = new Date(dateString + 'T00:00:00');
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatHearingTime(timeString) {
    if (!timeString) return '';
    // Time might come as "HH:MM:SS" or "HH:MM"
    const parts = timeString.split(':');
    if (parts.length < 2) return timeString;
    let hours = parseInt(parts[0], 10);
    const mins = parts[1];
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12 || 12;
    return `${hours}:${mins} ${ampm}`;
}

function getHearingStatusClass(status) {
    if (!status) return 'scheduled';
    const s = status.toLowerCase();
    if (s.includes('cancel')) return 'cancelled';
    if (s.includes('reschedule') || s.includes('postpone')) return 'rescheduled';
    return 'scheduled';
}

function updateHearingStats() {
    const stats = state.hearingStats;
    if (!stats) return;

    if (elements.hearingsHvac) {
        elements.hearingsHvac.textContent = stats.by_committee?.HVAC ?? 0;
    }
    if (elements.hearingsSvac) {
        elements.hearingsSvac.textContent = stats.by_committee?.SVAC ?? 0;
    }
    if (elements.hearingsTotal) {
        elements.hearingsTotal.textContent = stats.upcoming_count ?? '--';
    }
    if (elements.hearingsCount) {
        const count = stats.upcoming_count ?? 0;
        elements.hearingsCount.textContent = `${count} upcoming`;
    }
}

function renderHearings() {
    if (!elements.hearingsList) return;

    const hearings = state.hearings;

    if (state.loading.hearings) {
        elements.hearingsList.innerHTML = '<div class="loading-state">Loading hearings...</div>';
        return;
    }

    if (hearings.length === 0) {
        elements.hearingsList.innerHTML = `
            <div class="empty-hearings">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                    <line x1="16" y1="2" x2="16" y2="6"/>
                    <line x1="8" y1="2" x2="8" y2="6"/>
                    <line x1="3" y1="10" x2="21" y2="10"/>
                </svg>
                <p>No upcoming hearings scheduled</p>
            </div>
        `;
        return;
    }

    elements.hearingsList.innerHTML = hearings.map(hearing => {
        const statusClass = getHearingStatusClass(hearing.status);
        const chamberLower = (hearing.chamber || '').toLowerCase();
        const isHouse = chamberLower === 'house';
        const chamberClass = isHouse ? 'hvac' : 'svac';

        // Determine committee label - show subcommittee name if available
        let chamberLabel = isHouse ? 'HVAC' : 'SVAC';
        const committeeName = hearing.committee_name || '';
        if (committeeName.includes('Subcommittee')) {
            // Extract subcommittee name: "House VA Subcommittee on X" -> "X"
            const match = committeeName.match(/Subcommittee on (.+)$/);
            if (match) {
                chamberLabel = match[1].length > 20 ? match[1].substring(0, 18) + '...' : match[1];
            }
        }

        // Build title display
        const titleDisplay = hearing.title
            ? (hearing.title.length > 100 ? escapeHtml(hearing.title.substring(0, 100)) + '...' : escapeHtml(hearing.title))
            : 'Committee Hearing';

        // Format date nicely
        const dateDisplay = formatHearingDate(hearing.hearing_date);
        const timeDisplay = formatHearingTime(hearing.hearing_time);

        return `
            <div class="hearing-card">
                <div class="hearing-card-header">
                    <div class="hearing-date-badge">
                        <span class="hearing-date">${escapeHtml(dateDisplay)}</span>
                        ${timeDisplay ? `<span class="hearing-time">${escapeHtml(timeDisplay)}</span>` : ''}
                    </div>
                    <div class="hearing-badges">
                        <span class="hearing-committee ${chamberClass}">${escapeHtml(chamberLabel)}</span>
                        <span class="hearing-status ${statusClass}">${escapeHtml(hearing.status || 'Scheduled')}</span>
                    </div>
                </div>
                <div class="hearing-title">
                    ${hearing.url
                        ? `<a href="${escapeHtml(hearing.url)}" target="_blank" rel="noopener noreferrer">${titleDisplay}</a>`
                        : `<span>${titleDisplay}</span>`
                    }
                </div>
                ${hearing.meeting_type ? `<div class="hearing-type">${escapeHtml(hearing.meeting_type)}</div>` : ''}
            </div>
        `;
    }).join('');

    // Update count badge
    if (elements.hearingsCount) {
        elements.hearingsCount.textContent = `${hearings.length} upcoming`;
    }
}

async function showSummaryModal(docId) {
    const data = await fetchApi(`/summaries/${docId}`);
    if (!data) {
        alert('Could not load summary');
        return;
    }

    const tags = data.tags || [];
    const bulletPoints = data.bullet_points || [];

    elements.summaryDetails.innerHTML = `
        <div class="summary-tags" style="margin-bottom: 1rem;">
            ${tags.map(tag => `<span class="tag ${escapeHtml(tag)}">${escapeHtml(tag)}</span>`).join('')}
        </div>
        <p class="modal-summary-text">${escapeHtml(data.summary)}</p>
        ${bulletPoints.length > 0 ? `
            <div class="modal-summary-section">
                <h4>Key Points</h4>
                <ul>
                    ${bulletPoints.map(point => `<li>${escapeHtml(point)}</li>`).join('')}
                </ul>
            </div>
        ` : ''}
        ${data.veteran_impact ? `
            <div class="modal-summary-section">
                <h4>Veteran Impact</h4>
                <div class="summary-impact">
                    <p class="summary-impact-text">${escapeHtml(data.veteran_impact)}</p>
                </div>
            </div>
        ` : ''}
        ${data.source_url ? `
            <div class="modal-summary-section">
                <a href="${escapeHtml(data.source_url)}" target="_blank" rel="noopener noreferrer" class="doc-link">
                    View Original Document
                </a>
            </div>
        ` : ''}
    `;

    elements.summaryModal.classList.add('active');
}

function hideSummaryModal() {
    elements.summaryModal.classList.remove('active');
}

// Reports Functions
async function downloadReport(reportType) {
    // Close dropdown
    if (elements.reportsDropdown) {
        elements.reportsDropdown.classList.remove('active');
    }

    try {
        const response = await fetch(`${CONFIG.apiBase}/reports/generate?type=${reportType}&format=json`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const report = await response.json();
        const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = `va-signals-${reportType}-report-${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (error) {
        console.error('Error downloading report:', error);
        alert('Failed to download report. Please try again.');
    }
}

function toggleReportsDropdown() {
    if (elements.reportsDropdown) {
        elements.reportsDropdown.classList.toggle('active');
    }
}

// Chart Functions
function updateCharts() {
    updateRunsChart();
    updateStatusChart();
}

function updateRunsChart() {
    const ctx = document.getElementById('runs-chart');
    if (!ctx) return;

    // Get runs by day data from stats
    let labels = [];
    let data = [];

    if (state.stats?.runs_by_day && Array.isArray(state.stats.runs_by_day)) {
        // API returns array of {date, count} objects
        const runsByDay = state.stats.runs_by_day.slice(-7);
        labels = runsByDay.map(d => {
            const date = new Date(d.date + 'T00:00:00');
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        });
        data = runsByDay.map(d => d.count);
    } else {
        // Fallback: generate last 7 days with zero data
        for (let i = 6; i >= 0; i--) {
            const date = new Date();
            date.setDate(date.getDate() - i);
            labels.push(date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
            data.push(0);
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

function showErrorFromButton(button) {
    const errorText = button.dataset.error || 'No error details available';
    showErrorDetails(errorText);
}

function showColumnExplanation(column) {
    const explanations = {
        source: `
            <div class="explanation-content">
                <h3>What is a Source?</h3>
                <p>A <strong>source</strong> is a government data feed that the system monitors for changes.</p>

                <div class="explanation-breakdown">
                    <div class="explanation-item">
                        <span class="label">govinfo_fr_bulk</span>
                        <span class="value" style="color: var(--accent-primary)">Federal Register</span>
                    </div>
                    <div class="explanation-item">
                        <span class="label">govinfo_ecfr_title_38</span>
                        <span class="value" style="color: var(--accent-primary)">eCFR Title 38 (VA regulations)</span>
                    </div>
                </div>

                <p class="explanation-note">
                    The Federal Register publishes new rules, notices, and proposed regulations daily.
                    eCFR Title 38 contains the official VA regulations.
                </p>
            </div>
        `,
        status: `
            <div class="explanation-content">
                <h3>What does Status mean?</h3>
                <p>Status tells you what happened when the system checked a source.</p>

                <div class="explanation-breakdown">
                    <div class="explanation-item success">
                        <span class="label">SUCCESS</span>
                        <span class="value">Found new documents</span>
                    </div>
                    <div class="explanation-item no-data">
                        <span class="label">NO_DATA</span>
                        <span class="value">Checked successfully, nothing new</span>
                    </div>
                    <div class="explanation-item error">
                        <span class="label">ERROR</span>
                        <span class="value">Something went wrong</span>
                    </div>
                </div>

                <p class="explanation-note">
                    NO_DATA is normal! The Federal Register doesn't publish on weekends or holidays.
                    It just means the system checked and found no new content.
                </p>
            </div>
        `,
        started: `
            <div class="explanation-content">
                <h3>What is a Run?</h3>
                <p>A <strong>run</strong> is one check of a data source. The system automatically runs on a schedule.</p>

                <div class="explanation-breakdown">
                    <div class="explanation-item">
                        <span class="label">Schedule</span>
                        <span class="value">Daily at 6:15 AM ET</span>
                    </div>
                    <div class="explanation-item">
                        <span class="label">Trigger</span>
                        <span class="value">GitHub Actions (automated)</span>
                    </div>
                    <div class="explanation-item">
                        <span class="label">Can also run</span>
                        <span class="value">Manually via command line</span>
                    </div>
                </div>

                <p class="explanation-note">
                    Each run: connects to the source → downloads latest data →
                    compares against what we've seen before → saves any new documents →
                    sends alerts if something changed.
                </p>
            </div>
        `,
        records: `
            <div class="explanation-content">
                <h3>What does Records mean?</h3>
                <p><strong>Records</strong> is the number of items the system examined during that run.</p>

                <div class="explanation-breakdown">
                    <div class="explanation-item">
                        <span class="label">For FR (Federal Register)</span>
                        <span class="value">Days of XML files checked</span>
                    </div>
                    <div class="explanation-item">
                        <span class="label">For eCFR</span>
                        <span class="value">Usually 1 (the whole title)</span>
                    </div>
                </div>

                <p class="explanation-note">
                    A high number means more data was scanned. It doesn't mean that many
                    <em>new</em> documents were found — most are usually already in the database.
                </p>
            </div>
        `
    };

    const content = explanations[column] || '<p>No explanation available.</p>';
    elements.errorDetails.innerHTML = content;
    elements.errorModal.classList.add('active');
}

function showDriftExplanation(topic) {
    const explanations = {
        main: `
            <div class="explanation-content">
                <h3>What is Message Shift Detection?</h3>
                <p>This feature monitors how <strong>Congress members talk about VA issues</strong> in committee hearings.</p>

                <p>We analyze each member's speaking patterns over time. When someone suddenly talks very differently than usual, it gets flagged.</p>

                <div class="explanation-breakdown">
                    <div class="explanation-item">
                        <span class="label">Why it matters</span>
                        <span class="value">Sudden shifts might signal new priorities, external influence, or emerging issues</span>
                    </div>
                </div>

                <p class="explanation-note">
                    <strong>Example:</strong> If a member usually focuses on healthcare but suddenly starts emphasizing budget cuts, that's a "shift" worth investigating.
                </p>
            </div>
        `,
        members: `
            <div class="explanation-content">
                <h3>Congress Members</h3>
                <p>The number of <strong>Senators and Representatives</strong> we're tracking from VA-related committee hearings.</p>

                <p class="explanation-note">
                    We extract who said what from official hearing transcripts published by Congress.gov.
                </p>
            </div>
        `,
        statements: `
            <div class="explanation-content">
                <h3>Statements Analyzed</h3>
                <p>The total number of <strong>individual things members said</strong> during hearings that we've processed.</p>

                <p>Each statement is converted into a mathematical representation (embedding) that captures its meaning, so we can compare statements to each other.</p>

                <p class="explanation-note">
                    More statements = better understanding of how each member typically talks.
                </p>
            </div>
        `,
        baselines: `
            <div class="explanation-content">
                <h3>Ready to Monitor</h3>
                <p>Members who have <strong>enough historical data</strong> for us to detect unusual statements.</p>

                <p>We need at least 5 past statements from a member to understand their "normal" speaking pattern. Once we have that, we can spot when they deviate.</p>

                <div class="explanation-breakdown">
                    <div class="explanation-item">
                        <span class="label">Not ready yet?</span>
                        <span class="value">Some members are new or rarely speak — we need more data</span>
                    </div>
                </div>
            </div>
        `,
        unusual: `
            <div class="explanation-content">
                <h3>What makes a statement "unusual"?</h3>
                <p>A statement is flagged when it's <strong>significantly different</strong> from how that member typically talks.</p>

                <div class="explanation-breakdown">
                    <div class="explanation-item">
                        <span class="label">Unusualness Score (z)</span>
                        <span class="value">How many standard deviations from their average</span>
                    </div>
                    <div class="explanation-item">
                        <span class="label">z ≥ 2.0</span>
                        <span class="value">Flagged — only ~5% of statements are this different</span>
                    </div>
                    <div class="explanation-item">
                        <span class="label">z ≥ 3.0</span>
                        <span class="value">Very unusual — less than 1% are this different</span>
                    </div>
                </div>

                <p class="explanation-note">
                    Higher scores = more unusual. But unusual isn't always bad — it might just be a new topic.
                </p>
            </div>
        `
    };

    const content = explanations[topic] || '<p>No explanation available.</p>';
    elements.errorDetails.innerHTML = content;
    elements.errorModal.classList.add('active');
}

function showHealthyExplanation() {
    const stats = state.stats;
    const total = stats?.total_runs ?? 0;
    const success = stats?.success_count ?? 0;
    const noData = stats?.no_data_count ?? 0;
    const errors = stats?.error_count ?? 0;
    const healthyRate = stats?.healthy_rate ?? 0;

    const explanation = `
        <div class="explanation-content">
            <h3>What does "${healthyRate}% Healthy" mean?</h3>
            <p>This shows how often the system runs <strong>without errors</strong>.</p>

            <div class="explanation-breakdown">
                <div class="explanation-item success">
                    <span class="label">Found new documents</span>
                    <span class="value">${success} runs</span>
                </div>
                <div class="explanation-item no-data">
                    <span class="label">Checked, nothing new</span>
                    <span class="value">${noData} runs</span>
                </div>
                <div class="explanation-item error">
                    <span class="label">Had errors</span>
                    <span class="value">${errors} runs</span>
                </div>
                <div class="explanation-item total">
                    <span class="label">Total runs</span>
                    <span class="value">${total}</span>
                </div>
            </div>

            <p class="explanation-summary">
                <strong>${healthyRate}%</strong> = (${success} + ${noData}) ÷ ${total} × 100
            </p>
            <p class="explanation-note">
                "Checked, nothing new" is normal — the Federal Register doesn't publish every day.
                What matters is the system ran without crashing.
            </p>
        </div>
    `;

    elements.errorDetails.innerHTML = explanation;
    elements.errorModal.classList.add('active');
}

function hideErrorModal() {
    elements.errorModal.classList.remove('active');
}

// Tab Functions
// ============================================
// Oversight Monitor Functions
// ============================================

async function fetchOversightStats() {
    try {
        const response = await fetch(`${CONFIG.apiBase}/oversight/stats`);
        if (!response.ok) throw new Error('Failed to fetch oversight stats');
        state.oversightStats = await response.json();
        renderOversightStats();
    } catch (error) {
        console.error('Error fetching oversight stats:', error);
    } finally {
        state.loading.oversightStats = false;
    }
}

async function fetchOversightEvents() {
    try {
        const response = await fetch(`${CONFIG.apiBase}/oversight/events`);
        if (!response.ok) throw new Error('Failed to fetch oversight events');
        const data = await response.json();
        state.oversightEvents = data.events || [];
        renderOversightEvents();
    } catch (error) {
        console.error('Error fetching oversight events:', error);
    } finally {
        state.loading.oversightEvents = false;
    }
}

function renderOversightStats() {
    if (!state.oversightStats) return;
    const stats = state.oversightStats;

    if (elements.oversightTotalEvents) {
        elements.oversightTotalEvents.textContent = stats.total_events ?? 0;
    }
    if (elements.oversightEscalations) {
        elements.oversightEscalations.textContent = stats.escalations ?? 0;
    }
    if (elements.oversightDeviations) {
        elements.oversightDeviations.textContent = stats.deviations ?? 0;
    }
    if (elements.oversightSurfaced) {
        elements.oversightSurfaced.textContent = stats.surfaced ?? 0;
    }
    if (elements.oversightLastEvent) {
        const last = stats.last_event_at ? formatRelativeTime(stats.last_event_at) : '--';
        elements.oversightLastEvent.textContent = `Last event: ${last}`;
    }

    if (elements.oversightSourceList) {
        const entries = Object.entries(stats.by_source || {})
            .sort((a, b) => b[1] - a[1]);

        if (entries.length === 0) {
            elements.oversightSourceList.innerHTML = '<div class="empty-state">No events yet</div>';
            return;
        }

        elements.oversightSourceList.innerHTML = entries.map(([source, count]) => `
            <div class="oversight-source-row">
                <span class="oversight-source-name">
                    <span class="source-badge ${getSourceClass(source)}">${escapeHtml(source)}</span>
                </span>
                <span class="oversight-source-count">${count}</span>
            </div>
        `).join('');
    }
}

function renderOversightEvents() {
    if (!elements.oversightEventsTbody) return;

    if (elements.oversightEventsCount) {
        elements.oversightEventsCount.textContent = `${state.oversightEvents.length} events`;
    }

    if (state.loading.oversightEvents) {
        elements.oversightEventsTbody.innerHTML = `
            <tr class="loading-row">
                <td colspan="6">Loading...</td>
            </tr>
        `;
        return;
    }

    if (state.oversightEvents.length === 0) {
        elements.oversightEventsTbody.innerHTML = `
            <tr class="empty-state-row">
                <td colspan="6" class="empty-state">No events yet</td>
            </tr>
        `;
        return;
    }

    elements.oversightEventsTbody.innerHTML = state.oversightEvents.slice(0, 50).map(event => {
        const published = event.pub_timestamp || event.fetched_at;
        return `
            <tr>
                <td><span class="source-badge ${getSourceClass(event.primary_source_type)}">${escapeHtml(event.primary_source_type)}</span></td>
                <td><a href="${escapeHtml(event.primary_url)}" target="_blank" rel="noopener">${escapeHtml(event.title)}</a></td>
                <td>${formatDateTime(published)}</td>
                <td>${renderFlagBadge(event.is_escalation)}</td>
                <td>${renderFlagBadge(event.is_deviation)}</td>
                <td>${renderFlagBadge(event.surfaced)}</td>
            </tr>
        `;
    }).join('');
}

async function refreshOversightData() {
    await Promise.all([
        fetchOversightStats(),
        fetchOversightEvents()
    ]);
}

// ============================================
// State Monitor Functions
// ============================================

async function fetchStateStats() {
    try {
        const response = await fetch(`${CONFIG.apiBase}/state/stats`);
        if (!response.ok) throw new Error('Failed to fetch state stats');
        state.stateStats = await response.json();
        renderStateStats();
    } catch (error) {
        console.error('Error fetching state stats:', error);
    } finally {
        state.loading.stateStats = false;
    }
}

async function fetchStateSignals() {
    try {
        const stateParam = state.stateFilter !== 'all' ? `?state=${state.stateFilter}` : '';
        const response = await fetch(`${CONFIG.apiBase}/state/signals${stateParam}`);
        if (!response.ok) throw new Error('Failed to fetch state signals');
        const data = await response.json();
        state.stateSignals = data.signals || [];
        renderStateSignals();
    } catch (error) {
        console.error('Error fetching state signals:', error);
    } finally {
        state.loading.stateSignals = false;
    }
}

async function fetchStateRuns() {
    try {
        const response = await fetch(`${CONFIG.apiBase}/state/runs`);
        if (!response.ok) throw new Error('Failed to fetch state runs');
        const data = await response.json();
        state.stateRuns = data.runs || [];
        renderStateRuns();
    } catch (error) {
        console.error('Error fetching state runs:', error);
    } finally {
        state.loading.stateRuns = false;
    }
}

function renderStateStats() {
    if (!state.stateStats) return;

    const stats = state.stateStats;

    // Update health cards
    if (elements.stateTotalSignals) {
        elements.stateTotalSignals.textContent = stats.total_signals || 0;
    }
    if (elements.stateHighSeverity) {
        elements.stateHighSeverity.textContent = stats.by_severity?.high || 0;
    }
    if (elements.stateLastRun && stats.last_run) {
        elements.stateLastRun.textContent = formatRelativeTime(stats.last_run.finished_at);
    }
    if (elements.stateNewSignals && stats.last_run) {
        elements.stateNewSignals.textContent = stats.last_run.signals_found || 0;
    }

    // Update state bars
    const byState = stats.by_state || {};
    const maxCount = Math.max(byState.TX || 0, byState.CA || 0, byState.FL || 0, 1);

    if (elements.txBar) {
        elements.txBar.style.width = `${((byState.TX || 0) / maxCount) * 100}%`;
    }
    if (elements.txCount) {
        elements.txCount.textContent = byState.TX || 0;
    }
    if (elements.flBar) {
        elements.flBar.style.width = `${((byState.FL || 0) / maxCount) * 100}%`;
    }
    if (elements.flCount) {
        elements.flCount.textContent = byState.FL || 0;
    }
    if (elements.caBar) {
        elements.caBar.style.width = `${((byState.CA || 0) / maxCount) * 100}%`;
    }
    if (elements.caCount) {
        elements.caCount.textContent = byState.CA || 0;
    }

    // Update severity cards
    const bySeverity = stats.by_severity || {};
    if (elements.sevHigh) elements.sevHigh.textContent = bySeverity.high || 0;
    if (elements.sevMedium) elements.sevMedium.textContent = bySeverity.medium || 0;
    if (elements.sevLow) elements.sevLow.textContent = bySeverity.low || 0;
    if (elements.sevNoise) elements.sevNoise.textContent = bySeverity.noise || 0;
}

function renderStateSignals() {
    if (!elements.stateSignalsTbody) return;

    if (state.stateSignals.length === 0) {
        elements.stateSignalsTbody.innerHTML = `
            <tr>
                <td colspan="5" class="empty-state">No signals found</td>
            </tr>
        `;
        return;
    }

    elements.stateSignalsTbody.innerHTML = state.stateSignals.slice(0, 50).map(signal => `
        <tr>
            <td><span class="state-badge ${signal.state}">${signal.state}</span></td>
            <td><span class="severity-badge ${signal.severity || 'low'}">${signal.severity || 'unclassified'}</span></td>
            <td class="signal-title" title="${escapeHtml(signal.title)}">
                ${signal.url ? `<a href="${escapeHtml(signal.url)}" target="_blank">${escapeHtml(signal.title?.substring(0, 60) || 'Untitled')}${signal.title?.length > 60 ? '...' : ''}</a>` : escapeHtml(signal.title?.substring(0, 60) || 'Untitled')}
            </td>
            <td class="source-cell">${escapeHtml(signal.source_id?.replace(/_/g, ' ') || '--')}</td>
            <td>${signal.pub_date || '--'}</td>
        </tr>
    `).join('');
}

function renderStateRuns() {
    if (!elements.stateRunsTbody) return;

    if (state.stateRuns.length === 0) {
        elements.stateRunsTbody.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">No runs found</td>
            </tr>
        `;
        return;
    }

    if (elements.stateRunsCount) {
        elements.stateRunsCount.textContent = `${state.stateRuns.length} runs`;
    }

    elements.stateRunsTbody.innerHTML = state.stateRuns.slice(0, 20).map(run => `
        <tr>
            <td>${escapeHtml(run.run_type || '--')}</td>
            <td>${run.state || 'all'}</td>
            <td><span class="status-badge ${getStatusClass(run.status)}">${run.status}</span></td>
            <td>${run.signals_found || 0}</td>
            <td>${run.high_severity_count || 0}</td>
            <td>${formatRelativeTime(run.started_at)}</td>
        </tr>
    `).join('');
}

async function refreshStateData() {
    await Promise.all([
        fetchStateStats(),
        fetchStateSignals(),
        fetchStateRuns()
    ]);
}

function initMainTabs() {
    const mainTabs = document.querySelectorAll('.main-tab');
    mainTabs.forEach(tab => {
        tab.addEventListener('click', async () => {
            // Update active tab
            mainTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // Update active panel
            const tabId = tab.dataset.tab;
            document.querySelectorAll('.tab-panel').forEach(panel => {
                panel.classList.remove('active');
            });
            document.getElementById(`${tabId}-panel`)?.classList.add('active');

            state.activeMainTab = tabId;

            // Load state data when switching to state tab
            if (tabId === 'state' && state.loading.stateStats) {
                await refreshStateData();
            }
            // Load oversight data when switching to oversight tab
            if (tabId === 'oversight' && (state.loading.oversightStats || state.loading.oversightEvents)) {
                await refreshOversightData();
            }
            // Load battlefield data when switching to battlefield tab
            if (tabId === 'battlefield' && state.loading.battlefieldStats) {
                await refreshBattlefield();
            }
        });
    });

    // Init state filter buttons
    const stateFilters = document.querySelectorAll('.state-filter');
    stateFilters.forEach(btn => {
        btn.addEventListener('click', async () => {
            stateFilters.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.stateFilter = btn.dataset.state;
            await fetchStateSignals();
        });
    });
}

function initTabs() {
    // Init main tabs (Federal/State)
    initMainTabs();

    // Init document tabs (FR/eCFR)
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

    // Load federal data in parallel
    const federalPromises = [
        loadRuns(),
        loadStats(),
        loadFrDocuments(),
        loadEcfrDocuments(),
        loadHealth(),
        loadErrors(),
        loadSummaries(),
        loadSummarizedDocIds(),
        loadDriftEvents(),
        loadDriftStats(),
        loadBills(),
        loadBillStats(),
        loadHearings(),
        loadHearingStats()
    ];

    // Load state data if on state tab
    if (state.activeMainTab === 'state') {
        federalPromises.push(refreshStateData());
    }
    // Load oversight data if on oversight tab
    if (state.activeMainTab === 'oversight') {
        federalPromises.push(refreshOversightData());
    }
    // Load battlefield data if on battlefield tab
    if (state.activeMainTab === 'battlefield') {
        federalPromises.push(refreshBattlefield());
    }

    await Promise.all(federalPromises);

    // Re-render FR table to show summary badges (after summarizedDocIds is loaded)
    renderFrTable();
}

function startAutoRefresh() {
    if (state.refreshTimer) {
        clearInterval(state.refreshTimer);
    }
    state.refreshTimer = setInterval(refreshAll, CONFIG.refreshInterval);
}

// Event Listeners
function initEventListeners() {
    // Error modal close
    elements.modalClose.addEventListener('click', hideErrorModal);
    elements.errorModal.addEventListener('click', (e) => {
        if (e.target === elements.errorModal) {
            hideErrorModal();
        }
    });

    // Summary modal close
    if (elements.summaryModalClose) {
        elements.summaryModalClose.addEventListener('click', hideSummaryModal);
    }
    if (elements.summaryModal) {
        elements.summaryModal.addEventListener('click', (e) => {
            if (e.target === elements.summaryModal) {
                hideSummaryModal();
            }
        });
    }

    // Reports dropdown toggle
    if (elements.reportsBtn) {
        elements.reportsBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleReportsDropdown();
        });
    }

    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (elements.reportsDropdown && !elements.reportsDropdown.contains(e.target)) {
            elements.reportsDropdown.classList.remove('active');
        }
    });

    // Keyboard events
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            hideErrorModal();
            hideSummaryModal();
            if (elements.reportsDropdown) {
                elements.reportsDropdown.classList.remove('active');
            }
        }
    });
}

// Section collapse toggle
function toggleSection(sectionId) {
    const section = document.getElementById(sectionId);
    if (section) {
        section.classList.toggle('collapsed');
        // Save state to localStorage
        const isCollapsed = section.classList.contains('collapsed');
        localStorage.setItem(`section_${sectionId}_collapsed`, isCollapsed);
    }
}

// Restore collapsed states from localStorage
function restoreCollapsedStates() {
    const sections = document.querySelectorAll('.collapsible-section');
    sections.forEach(section => {
        const isCollapsed = localStorage.getItem(`section_${section.id}_collapsed`) === 'true';
        if (isCollapsed) {
            section.classList.add('collapsed');
        }
    });
}

// ============================================================================
// BATTLEFIELD DASHBOARD FUNCTIONS
// ============================================================================

async function fetchBattlefieldStats() {
    try {
        state.loading.battlefieldStats = true;
        const response = await fetch(`${CONFIG.apiBase}/battlefield/stats`);
        if (!response.ok) throw new Error('Failed to fetch battlefield stats');
        state.battlefieldStats = await response.json();
        renderBattlefieldStats();
    } catch (error) {
        console.error('Error fetching battlefield stats:', error);
    } finally {
        state.loading.battlefieldStats = false;
    }
}

async function fetchBattlefieldVehicles() {
    try {
        state.loading.battlefieldVehicles = true;
        const response = await fetch(`${CONFIG.apiBase}/battlefield/vehicles?limit=20`);
        if (!response.ok) throw new Error('Failed to fetch vehicles');
        const data = await response.json();
        state.battlefieldVehicles = data.vehicles || [];
        renderBattlefieldVehicles();
    } catch (error) {
        console.error('Error fetching battlefield vehicles:', error);
    } finally {
        state.loading.battlefieldVehicles = false;
    }
}

async function fetchBattlefieldCriticalGates() {
    try {
        state.loading.battlefieldCriticalGates = true;
        const response = await fetch(`${CONFIG.apiBase}/battlefield/critical-gates?days=14`);
        if (!response.ok) throw new Error('Failed to fetch critical gates');
        const data = await response.json();
        state.battlefieldCriticalGates = data.events || [];
        renderBattlefieldCriticalGates();
    } catch (error) {
        console.error('Error fetching critical gates:', error);
    } finally {
        state.loading.battlefieldCriticalGates = false;
    }
}

async function fetchBattlefieldAlerts() {
    try {
        state.loading.battlefieldAlerts = true;
        const response = await fetch(`${CONFIG.apiBase}/battlefield/alerts?hours=48`);
        if (!response.ok) throw new Error('Failed to fetch alerts');
        const data = await response.json();
        state.battlefieldAlerts = data.alerts || [];
        renderBattlefieldAlerts();
    } catch (error) {
        console.error('Error fetching battlefield alerts:', error);
    } finally {
        state.loading.battlefieldAlerts = false;
    }
}

function renderBattlefieldStats() {
    const stats = state.battlefieldStats;
    if (!stats) return;

    const totalVehiclesEl = document.getElementById('bf-total-vehicles');
    const gates14dEl = document.getElementById('bf-gates-14d');
    const alerts48hEl = document.getElementById('bf-alerts-48h');
    const unackAlertsEl = document.getElementById('bf-unack-alerts');

    if (totalVehiclesEl) totalVehiclesEl.textContent = stats.total_vehicles || 0;
    if (gates14dEl) gates14dEl.textContent = stats.upcoming_gates_14d || 0;
    if (alerts48hEl) alerts48hEl.textContent = stats.alerts_48h || 0;
    if (unackAlertsEl) unackAlertsEl.textContent = stats.unacknowledged_alerts || 0;
}

function renderBattlefieldCriticalGates() {
    const tbody = document.getElementById('bf-critical-tbody');
    const countEl = document.getElementById('bf-critical-count');
    if (!tbody) return;

    const gates = state.battlefieldCriticalGates;
    if (countEl) countEl.textContent = `${gates.length} gates`;

    if (gates.length === 0) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="6">No critical gates in next 14 days</td></tr>';
        return;
    }

    tbody.innerHTML = gates.map(gate => {
        const daysClass = gate.days_until <= 3 ? 'critical' : (gate.days_until <= 7 ? 'warning' : '');
        const importanceClass = gate.importance === 'critical' ? 'badge-critical' :
                                gate.importance === 'important' ? 'badge-important' : 'badge-watch';
        return `
            <tr>
                <td>${formatDate(gate.date)}</td>
                <td title="${escapeHtml(gate.title || '')}">${escapeHtml(truncate(gate.identifier || gate.vehicle_id, 30))}</td>
                <td>${escapeHtml(gate.event_type || '')}</td>
                <td class="${daysClass}">${gate.days_until}d</td>
                <td><span class="badge ${importanceClass}">${gate.importance}</span></td>
                <td>${escapeHtml(truncate(gate.prep_required || 'Review', 30))}</td>
            </tr>
        `;
    }).join('');
}

function renderBattlefieldVehicles() {
    const tbody = document.getElementById('bf-vehicles-tbody');
    const countEl = document.getElementById('bf-vehicles-count');
    if (!tbody) return;

    const vehicles = state.battlefieldVehicles;
    if (countEl) countEl.textContent = `${vehicles.length} vehicles`;

    if (vehicles.length === 0) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="6">No active vehicles. Click "Sync Sources" to load data.</td></tr>';
        return;
    }

    tbody.innerHTML = vehicles.map(v => {
        const postureClass = v.our_posture === 'support' ? 'badge-success' :
                            v.our_posture === 'oppose' ? 'badge-error' :
                            v.our_posture === 'neutral_engaged' ? 'badge-warning' : 'badge-info';
        const typeClass = v.vehicle_type === 'bill' ? 'badge-primary' :
                         v.vehicle_type === 'rule' ? 'badge-secondary' :
                         v.vehicle_type === 'oversight' ? 'badge-warning' : 'badge-info';
        return `
            <tr>
                <td title="${escapeHtml(v.title || '')}">${escapeHtml(truncate(v.identifier || v.vehicle_id, 30))}</td>
                <td><span class="badge ${typeClass}">${v.vehicle_type}</span></td>
                <td>${escapeHtml(v.current_stage || '')}</td>
                <td>${v.status_date ? formatDate(v.status_date) : '--'}</td>
                <td><span class="badge ${postureClass}">${v.our_posture || 'monitor'}</span></td>
                <td>${escapeHtml(v.owner_internal || '--')}</td>
            </tr>
        `;
    }).join('');
}

function renderBattlefieldAlerts() {
    const tbody = document.getElementById('bf-alerts-tbody');
    const countEl = document.getElementById('bf-alerts-count');
    if (!tbody) return;

    const alerts = state.battlefieldAlerts;
    if (countEl) countEl.textContent = `${alerts.length} alerts`;

    if (alerts.length === 0) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="6">No alerts in last 48 hours</td></tr>';
        return;
    }

    tbody.innerHTML = alerts.map(a => {
        const typeClass = a.alert_type === 'gate_moved' ? 'badge-warning' :
                         a.alert_type === 'new_gate' ? 'badge-success' :
                         a.alert_type === 'status_changed' ? 'badge-info' :
                         a.alert_type === 'gate_passed' ? 'badge-secondary' : 'badge-primary';
        const impactText = a.days_impact ? `${a.days_impact > 0 ? '+' : ''}${a.days_impact}d` : '--';
        const ackBtn = a.acknowledged ?
            '<span class="badge badge-secondary">ACK</span>' :
            `<button class="btn btn-sm" onclick="acknowledgeBattlefieldAlert('${a.alert_id}')">ACK</button>`;
        return `
            <tr class="${a.acknowledged ? 'acknowledged' : ''}">
                <td>${formatTimestamp(a.timestamp)}</td>
                <td title="${escapeHtml(a.vehicle_title || '')}">${escapeHtml(truncate(a.identifier || a.vehicle_id, 25))}</td>
                <td><span class="badge ${typeClass}">${a.alert_type.replace('_', ' ')}</span></td>
                <td title="${escapeHtml(a.new_value || '')}">${escapeHtml(truncate(a.new_value || '', 40))}</td>
                <td>${impactText}</td>
                <td>${ackBtn}</td>
            </tr>
        `;
    }).join('');
}

async function syncBattlefield() {
    showToast('Syncing battlefield sources...', 'info');
    try {
        const response = await fetch(`${CONFIG.apiBase}/battlefield/sync`, { method: 'POST' });
        if (!response.ok) throw new Error('Sync failed');
        const result = await response.json();
        showToast(`Sync complete: ${JSON.stringify(result.results)}`, 'success');
        await refreshBattlefield();
    } catch (error) {
        showToast(`Sync failed: ${error.message}`, 'error');
    }
}

async function runDetection() {
    showToast('Running gate detection...', 'info');
    try {
        const response = await fetch(`${CONFIG.apiBase}/battlefield/detect`, { method: 'POST' });
        if (!response.ok) throw new Error('Detection failed');
        const result = await response.json();
        showToast(`Detection complete: ${JSON.stringify(result.results)}`, 'success');
        await refreshBattlefield();
    } catch (error) {
        showToast(`Detection failed: ${error.message}`, 'error');
    }
}

async function acknowledgeBattlefieldAlert(alertId) {
    try {
        const response = await fetch(`${CONFIG.apiBase}/battlefield/alerts/${alertId}/acknowledge`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ acknowledged_by: 'dashboard_user' })
        });
        if (!response.ok) throw new Error('Acknowledge failed');
        showToast('Alert acknowledged', 'success');
        await fetchBattlefieldAlerts();
        await fetchBattlefieldStats();
    } catch (error) {
        showToast(`Failed to acknowledge: ${error.message}`, 'error');
    }
}

async function refreshBattlefield() {
    await Promise.all([
        fetchBattlefieldStats(),
        fetchBattlefieldVehicles(),
        fetchBattlefieldCriticalGates(),
        fetchBattlefieldAlerts()
    ]);
}

function truncate(str, maxLen) {
    if (!str) return '';
    return str.length > maxLen ? str.substring(0, maxLen - 3) + '...' : str;
}

function formatTimestamp(ts) {
    if (!ts) return '--';
    try {
        const date = new Date(ts);
        return date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch {
        return ts;
    }
}

// Make functions available globally for onclick handlers
window.showErrorDetails = showErrorDetails;
window.showErrorFromButton = showErrorFromButton;
window.showColumnExplanation = showColumnExplanation;
window.showHealthyExplanation = showHealthyExplanation;
window.showDriftExplanation = showDriftExplanation;
window.showSummaryModal = showSummaryModal;
window.toggleSummaryDetails = toggleSummaryDetails;
window.downloadReport = downloadReport;
window.toggleSection = toggleSection;
window.syncBattlefield = syncBattlefield;
window.runDetection = runDetection;
window.acknowledgeBattlefieldAlert = acknowledgeBattlefieldAlert;

// =============================================================================
// SESSION & AUTH MANAGEMENT
// =============================================================================

const AUTH_CONFIG = {
    sessionCheckInterval: 60000, // Check session every minute
    sessionWarningTime: 300000,  // Warn 5 minutes before expiry
    loginUrl: '/login.html',
};

let sessionState = {
    user: null,
    expiresAt: null,
    warningShown: false,
    checkInterval: null,
};

function initSessionManagement() {
    // Check for existing session
    checkSession();

    // Set up user menu
    initUserMenu();

    // Start session monitoring
    sessionState.checkInterval = setInterval(checkSession, AUTH_CONFIG.sessionCheckInterval);

    // Create session timeout modal
    createSessionModal();
}

async function checkSession() {
    try {
        const response = await fetch(`${CONFIG.apiBase}/auth/me`, {
            credentials: 'include',
        });

        if (!response.ok) {
            // Not authenticated, redirect to login
            redirectToLogin();
            return;
        }

        const data = await response.json();
        sessionState.user = data.user;
        sessionState.expiresAt = data.expiresAt ? new Date(data.expiresAt).getTime() : null;

        updateUserDisplay();

        // Check if session is about to expire
        if (sessionState.expiresAt) {
            const timeRemaining = sessionState.expiresAt - Date.now();
            if (timeRemaining > 0 && timeRemaining <= AUTH_CONFIG.sessionWarningTime && !sessionState.warningShown) {
                showSessionWarning(Math.ceil(timeRemaining / 1000));
            }
        }
    } catch (error) {
        // Network error - don't redirect, might be temporary
        console.warn('Session check failed:', error);
    }
}

function updateUserDisplay() {
    const user = sessionState.user;
    if (!user) return;

    const userNameEl = document.getElementById('user-name');
    const userEmailEl = document.getElementById('user-email');
    const userRoleEl = document.getElementById('user-role');
    const userAvatarEl = document.getElementById('user-avatar');
    const auditLogBtn = document.getElementById('audit-log-btn');

    if (userNameEl) {
        userNameEl.textContent = user.displayName || user.email?.split('@')[0] || 'User';
    }

    if (userEmailEl) {
        userEmailEl.textContent = user.email || '';
    }

    if (userRoleEl) {
        const role = user.role || 'VIEWER';
        userRoleEl.textContent = role;
        userRoleEl.className = 'user-role ' + role.toLowerCase();
    }

    if (userAvatarEl && user.photoUrl) {
        userAvatarEl.innerHTML = `<img src="${escapeHtml(user.photoUrl)}" alt="Avatar">`;
    }

    // Show audit log button for COMMANDER role
    if (auditLogBtn && user.role === 'COMMANDER') {
        auditLogBtn.style.display = 'flex';
    }
}

function initUserMenu() {
    const userMenuBtn = document.getElementById('user-menu-btn');
    const userMenuDropdown = document.getElementById('user-menu-container');
    const logoutBtn = document.getElementById('logout-btn');
    const profileBtn = document.getElementById('profile-btn');

    if (userMenuBtn && userMenuDropdown) {
        userMenuBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            userMenuDropdown.classList.toggle('open');
            const menu = document.getElementById('user-dropdown-menu');
            if (menu) {
                menu.style.display = userMenuDropdown.classList.contains('open') ? 'block' : 'none';
            }
        });

        // Close on outside click
        document.addEventListener('click', () => {
            userMenuDropdown.classList.remove('open');
            const menu = document.getElementById('user-dropdown-menu');
            if (menu) menu.style.display = 'none';
        });
    }

    if (logoutBtn) {
        logoutBtn.addEventListener('click', handleLogout);
    }

    if (profileBtn) {
        profileBtn.addEventListener('click', () => {
            showToast('Profile settings coming soon', 'info');
        });
    }
}

async function handleLogout() {
    try {
        // Call backend logout
        await fetch(`${CONFIG.apiBase}/auth/logout`, {
            method: 'POST',
            credentials: 'include',
        });
    } catch (error) {
        console.warn('Logout request failed:', error);
    }

    // Clear local state
    sessionState.user = null;
    sessionState.expiresAt = null;
    sessionStorage.removeItem('user');

    // Clear any Firebase session if present
    if (typeof firebase !== 'undefined' && firebase.auth) {
        try {
            await firebase.auth().signOut();
        } catch (e) {
            // Ignore Firebase errors
        }
    }

    // Redirect to login
    redirectToLogin();
}

function redirectToLogin(expired = false) {
    // Clear session check interval
    if (sessionState.checkInterval) {
        clearInterval(sessionState.checkInterval);
    }

    // Build redirect URL
    const currentUrl = window.location.pathname + window.location.search;
    let loginUrl = AUTH_CONFIG.loginUrl;

    // Add redirect parameter if not already on login page
    if (currentUrl !== AUTH_CONFIG.loginUrl && currentUrl !== '/') {
        loginUrl += `?redirect=${encodeURIComponent(currentUrl)}`;
    }

    if (expired) {
        loginUrl += (loginUrl.includes('?') ? '&' : '?') + 'expired=true';
    }

    window.location.href = loginUrl;
}

function createSessionModal() {
    // Check if modal already exists
    if (document.getElementById('session-modal-overlay')) return;

    const modalHtml = `
        <div class="session-modal-overlay" id="session-modal-overlay">
            <div class="session-modal">
                <div class="session-modal-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <polyline points="12 6 12 12 16 14"/>
                    </svg>
                </div>
                <h3>Session Expiring</h3>
                <p>Your session will expire soon. Would you like to stay signed in?</p>
                <div class="session-modal-countdown" id="session-countdown">5:00</div>
                <div class="session-modal-actions">
                    <button class="btn btn-secondary" id="session-logout-btn">Sign Out</button>
                    <button class="btn btn-primary" id="session-extend-btn">Stay Signed In</button>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // Bind events
    document.getElementById('session-logout-btn')?.addEventListener('click', () => {
        hideSessionWarning();
        handleLogout();
    });

    document.getElementById('session-extend-btn')?.addEventListener('click', extendSession);
}

let sessionCountdownInterval = null;

function showSessionWarning(secondsRemaining) {
    sessionState.warningShown = true;

    const overlay = document.getElementById('session-modal-overlay');
    const countdown = document.getElementById('session-countdown');

    if (overlay) {
        overlay.classList.add('visible');
    }

    // Start countdown
    let remaining = secondsRemaining;
    updateCountdownDisplay(remaining);

    sessionCountdownInterval = setInterval(() => {
        remaining--;
        updateCountdownDisplay(remaining);

        if (remaining <= 0) {
            clearInterval(sessionCountdownInterval);
            hideSessionWarning();
            redirectToLogin(true);
        }
    }, 1000);
}

function updateCountdownDisplay(seconds) {
    const countdown = document.getElementById('session-countdown');
    if (countdown) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        countdown.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
    }
}

function hideSessionWarning() {
    const overlay = document.getElementById('session-modal-overlay');
    if (overlay) {
        overlay.classList.remove('visible');
    }

    if (sessionCountdownInterval) {
        clearInterval(sessionCountdownInterval);
        sessionCountdownInterval = null;
    }
}

async function extendSession() {
    try {
        const response = await fetch(`${CONFIG.apiBase}/auth/refresh`, {
            method: 'POST',
            credentials: 'include',
        });

        if (response.ok) {
            const data = await response.json();
            sessionState.expiresAt = data.expiresAt ? new Date(data.expiresAt).getTime() : null;
            sessionState.warningShown = false;
            hideSessionWarning();
            showToast('Session extended', 'success');
        } else {
            throw new Error('Failed to extend session');
        }
    } catch (error) {
        showToast('Failed to extend session. Please sign in again.', 'error');
        hideSessionWarning();
        redirectToLogin(true);
    }
}

// Export for global access
window.handleLogout = handleLogout;

// =============================================================================
// COMMAND CENTER
// =============================================================================

const commandState = {
    alerts: [],
    activity: [],
    health: {
        federal: 'checking',
        oversight: 'checking',
        state: 'checking',
        battlefield: 'checking'
    },
    notifications: [],
    unreadCount: 0,
};

function initCommandCenter() {
    initNotificationBell();
    initQuickActions();
    initMobileMenu();
    initBriefViewer();
    loadCommandCenterData();
    loadExecutiveSummary();

    // Initialize audit log after session is loaded (for role check)
    setTimeout(() => {
        initAuditLog();
    }, 500);
}

function initNotificationBell() {
    const bellBtn = document.getElementById('notification-btn');
    const bellContainer = document.getElementById('notification-bell');
    const markAllRead = document.getElementById('mark-all-read');

    if (bellBtn && bellContainer) {
        bellBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            bellContainer.classList.toggle('open');
        });

        document.addEventListener('click', () => {
            bellContainer.classList.remove('open');
        });

        document.getElementById('notification-dropdown')?.addEventListener('click', (e) => {
            e.stopPropagation();
        });
    }

    if (markAllRead) {
        markAllRead.addEventListener('click', markAllNotificationsRead);
    }
}

function initQuickActions() {
    document.getElementById('action-generate-brief')?.addEventListener('click', async () => {
        showToast('Generating CEO brief...', 'info');
        try {
            const response = await fetch(`${CONFIG.apiBase}/briefs/generate`, {
                method: 'POST',
                credentials: 'include',
            });
            if (response.ok) {
                showToast('CEO brief generated successfully', 'success');
                loadCommandCenterData();
            } else {
                throw new Error('Failed to generate brief');
            }
        } catch (error) {
            showToast('Brief generation not available', 'warning');
        }
    });

    document.getElementById('action-sync-battlefield')?.addEventListener('click', async () => {
        showToast('Syncing battlefield data...', 'info');
        try {
            await syncBattlefield();
            showToast('Battlefield synced', 'success');
        } catch (error) {
            showToast('Sync failed: ' + error.message, 'error');
        }
    });

    document.getElementById('action-view-brief')?.addEventListener('click', () => {
        // Switch to briefs tab
        const briefsTab = document.querySelector('[data-tab="briefs"]');
        if (briefsTab) {
            briefsTab.click();
        }
    });

    document.getElementById('action-export-report')?.addEventListener('click', () => {
        downloadReport('daily');
    });

    document.getElementById('refresh-activity-btn')?.addEventListener('click', () => {
        loadActivityFeed();
    });
}

async function loadCommandCenterData() {
    await Promise.all([
        loadMissionStatus(),
        loadCriticalAlerts(),
        loadActivityFeed(),
        loadSystemHealth(),
        loadNotifications(),
    ]);

    // Update timestamp
    const timestampEl = document.getElementById('command-last-update');
    if (timestampEl) {
        timestampEl.textContent = new Date().toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
        });
    }
}

async function loadMissionStatus() {
    try {
        // Fetch health stats from existing endpoints
        const response = await fetch(`${CONFIG.apiBase}/health`);
        if (response.ok) {
            const data = await response.json();

            // Update systems operational
            const systems = document.getElementById('systems-operational');
            const indicator = document.getElementById('systems-indicator');
            if (systems) {
                const operational = Object.values(data.sources || {}).filter(s => s.status === 'operational').length;
                const total = Object.values(data.sources || {}).length || 4;
                systems.textContent = `${operational}/${total}`;

                if (indicator) {
                    indicator.classList.remove('operational', 'warning', 'error');
                    if (operational === total) {
                        indicator.classList.add('operational');
                    } else if (operational > 0) {
                        indicator.classList.add('warning');
                    } else {
                        indicator.classList.add('error');
                    }
                }
            }
        }
    } catch (error) {
        console.warn('Failed to load mission status:', error);
    }

    // Load alert count
    try {
        const alertsEl = document.getElementById('critical-alerts-count');
        const alertsIndicator = document.getElementById('alerts-indicator');
        if (alertsEl) {
            const count = commandState.alerts.length;
            alertsEl.textContent = count;
            if (alertsIndicator) {
                alertsIndicator.classList.remove('operational', 'warning', 'error');
                if (count === 0) {
                    alertsIndicator.classList.add('operational');
                } else if (count < 3) {
                    alertsIndicator.classList.add('warning');
                } else {
                    alertsIndicator.classList.add('error');
                }
            }
        }
    } catch (e) {}

    // Load pending actions (from battlefield or other sources)
    try {
        const pendingEl = document.getElementById('pending-actions-count');
        if (pendingEl) {
            const response = await fetch(`${CONFIG.apiBase}/battlefield/stats`);
            if (response.ok) {
                const data = await response.json();
                pendingEl.textContent = data.unacknowledged_alerts || 0;
            } else {
                pendingEl.textContent = '0';
            }
        }
    } catch (e) {
        const pendingEl = document.getElementById('pending-actions-count');
        if (pendingEl) pendingEl.textContent = '0';
    }

    // Load latest brief date
    try {
        const briefEl = document.getElementById('latest-brief-date');
        if (briefEl) {
            const response = await fetch(`${CONFIG.apiBase}/briefs/latest`);
            if (response.ok) {
                const data = await response.json();
                if (data.generated_at) {
                    briefEl.textContent = formatRelativeTime(data.generated_at);
                } else {
                    briefEl.textContent = 'No briefs';
                }
            } else {
                briefEl.textContent = 'N/A';
            }
        }
    } catch (e) {
        const briefEl = document.getElementById('latest-brief-date');
        if (briefEl) briefEl.textContent = 'N/A';
    }
}

async function loadCriticalAlerts() {
    const listEl = document.getElementById('critical-alerts-list');
    const badgeEl = document.getElementById('alerts-badge');

    if (!listEl) return;

    try {
        // Try to get alerts from battlefield
        const response = await fetch(`${CONFIG.apiBase}/battlefield/alerts?limit=5`);
        if (response.ok) {
            const data = await response.json();
            commandState.alerts = data.alerts || [];
        } else {
            commandState.alerts = [];
        }
    } catch (error) {
        commandState.alerts = [];
    }

    if (badgeEl) {
        badgeEl.textContent = commandState.alerts.length;
        badgeEl.style.display = commandState.alerts.length > 0 ? 'inline-flex' : 'none';
    }

    if (commandState.alerts.length === 0) {
        listEl.innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                    <polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
                <p>No critical alerts</p>
            </div>
        `;
        return;
    }

    listEl.innerHTML = commandState.alerts.map(alert => `
        <div class="alert-item ${alert.severity === 'high' ? '' : 'warning'}">
            <div class="alert-severity">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                    <line x1="12" y1="9" x2="12" y2="13"/>
                    <line x1="12" y1="17" x2="12.01" y2="17"/>
                </svg>
            </div>
            <div class="alert-info">
                <div class="alert-title">${escapeHtml(alert.title || alert.message || 'Alert')}</div>
                <div class="alert-source">${escapeHtml(alert.source || 'System')} · ${formatRelativeTime(alert.created_at)}</div>
            </div>
            <div class="alert-actions">
                <button class="btn-acknowledge" onclick="acknowledgeAlert('${alert.id}')">Acknowledge</button>
            </div>
        </div>
    `).join('');
}

async function loadActivityFeed() {
    const feedEl = document.getElementById('activity-feed');
    if (!feedEl) return;

    try {
        // Try to get recent runs as activity
        const response = await fetch(`${CONFIG.apiBase}/runs?limit=10`);
        if (response.ok) {
            const data = await response.json();
            const runs = data.runs || [];

            if (runs.length === 0) {
                feedEl.innerHTML = `
                    <div class="activity-item">
                        <div class="activity-icon system">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="12" cy="12" r="10"/>
                                <line x1="12" y1="8" x2="12" y2="12"/>
                                <line x1="12" y1="16" x2="12.01" y2="16"/>
                            </svg>
                        </div>
                        <div class="activity-content">
                            <p class="activity-text">No recent activity</p>
                            <span class="activity-time">--</span>
                        </div>
                    </div>
                `;
                return;
            }

            feedEl.innerHTML = runs.map(run => {
                const iconClass = run.status === 'SUCCESS' ? 'success' :
                                  run.status === 'ERROR' ? 'error' :
                                  run.status === 'NO_DATA' ? 'info' : 'system';

                const iconSvg = run.status === 'SUCCESS' ?
                    '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>' :
                    run.status === 'ERROR' ?
                    '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>' :
                    '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>';

                return `
                    <div class="activity-item">
                        <div class="activity-icon ${iconClass}">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                ${iconSvg}
                            </svg>
                        </div>
                        <div class="activity-content">
                            <p class="activity-text">
                                <span class="activity-target">${escapeHtml(run.source)}</span>
                                ${run.status === 'SUCCESS' ? 'completed run' :
                                  run.status === 'ERROR' ? 'encountered error' :
                                  'completed (no new data)'}
                                ${run.new_records ? `with ${run.new_records} new records` : ''}
                            </p>
                            <span class="activity-time">${formatRelativeTime(run.started_at)}</span>
                        </div>
                    </div>
                `;
            }).join('');
        }
    } catch (error) {
        feedEl.innerHTML = `
            <div class="activity-item">
                <div class="activity-icon system">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <polyline points="12 6 12 12 16 14"/>
                    </svg>
                </div>
                <div class="activity-content">
                    <p class="activity-text">Activity feed unavailable</p>
                    <span class="activity-time">--</span>
                </div>
            </div>
        `;
    }
}

async function loadSystemHealth() {
    const healthItems = {
        'health-federal': 'federal',
        'health-oversight': 'oversight',
        'health-state': 'state',
        'health-battlefield': 'battlefield'
    };

    try {
        const response = await fetch(`${CONFIG.apiBase}/health`);
        if (response.ok) {
            const data = await response.json();

            for (const [elId, source] of Object.entries(healthItems)) {
                const el = document.getElementById(elId);
                if (el) {
                    const sourceData = data.sources?.[source];
                    if (sourceData) {
                        const status = sourceData.status || 'unknown';
                        el.textContent = status.charAt(0).toUpperCase() + status.slice(1);
                        el.className = 'health-status ' + (status === 'operational' ? 'operational' :
                                                           status === 'degraded' ? 'degraded' : 'error');
                        commandState.health[source] = status;
                    } else {
                        el.textContent = 'Unknown';
                        el.className = 'health-status';
                    }
                }
            }
        }
    } catch (error) {
        for (const elId of Object.keys(healthItems)) {
            const el = document.getElementById(elId);
            if (el) {
                el.textContent = 'Unavailable';
                el.className = 'health-status';
            }
        }
    }
}

async function loadNotifications() {
    const listEl = document.getElementById('notification-list');
    const badgeEl = document.getElementById('notification-badge');

    if (!listEl) return;

    try {
        const response = await fetch(`${CONFIG.apiBase}/notifications?limit=10`);
        if (response.ok) {
            const data = await response.json();
            commandState.notifications = data.notifications || [];
            commandState.unreadCount = data.unread_count || 0;
        } else {
            commandState.notifications = [];
            commandState.unreadCount = 0;
        }
    } catch (error) {
        commandState.notifications = [];
        commandState.unreadCount = 0;
    }

    // Update badge
    if (badgeEl) {
        badgeEl.textContent = commandState.unreadCount;
        badgeEl.style.display = commandState.unreadCount > 0 ? 'flex' : 'none';
    }

    // Render notifications
    if (commandState.notifications.length === 0) {
        listEl.innerHTML = `
            <div class="notification-empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
                    <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
                </svg>
                <p>No new notifications</p>
            </div>
        `;
        return;
    }

    listEl.innerHTML = commandState.notifications.map(notif => {
        const iconClass = notif.type || 'info';
        const iconSvg = notif.type === 'alert' ?
            '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>' :
            notif.type === 'success' ?
            '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>' :
            '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>';

        return `
            <div class="notification-item ${notif.read ? '' : 'unread'}" data-id="${notif.id}">
                <div class="notification-icon ${iconClass}">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        ${iconSvg}
                    </svg>
                </div>
                <div class="notification-content">
                    <div class="notification-title">${escapeHtml(notif.title)}</div>
                    <div class="notification-text">${escapeHtml(notif.message)}</div>
                    <div class="notification-time">${formatRelativeTime(notif.created_at)}</div>
                </div>
            </div>
        `;
    }).join('');
}

async function markAllNotificationsRead() {
    try {
        await fetch(`${CONFIG.apiBase}/notifications/read-all`, {
            method: 'POST',
            credentials: 'include',
        });
        commandState.unreadCount = 0;
        const badgeEl = document.getElementById('notification-badge');
        if (badgeEl) {
            badgeEl.style.display = 'none';
        }
        document.querySelectorAll('.notification-item.unread').forEach(el => {
            el.classList.remove('unread');
        });
    } catch (error) {
        console.warn('Failed to mark notifications as read:', error);
    }
}

async function acknowledgeAlert(alertId) {
    try {
        await fetch(`${CONFIG.apiBase}/battlefield/alerts/${alertId}/acknowledge`, {
            method: 'POST',
            credentials: 'include',
        });
        showToast('Alert acknowledged', 'success');
        loadCriticalAlerts();
        loadMissionStatus();
    } catch (error) {
        showToast('Failed to acknowledge alert', 'error');
    }
}

// Export for global access
window.acknowledgeAlert = acknowledgeAlert;

// =============================================================================
// EXECUTIVE SUMMARY
// =============================================================================

async function loadExecutiveSummary() {
    await Promise.all([
        loadExecMetrics(),
        loadExecHeatMap(),
        loadExecCalendar(),
        loadExecCriticalItems()
    ]);
}

async function loadExecMetrics() {
    try {
        // Federal Register count
        const frResponse = await fetch(`${CONFIG.apiBase}/fr/documents?limit=1`);
        if (frResponse.ok) {
            const data = await frResponse.json();
            const el = document.getElementById('metric-fr-count');
            const trendEl = document.getElementById('metric-fr-trend');
            if (el) el.textContent = data.total || '0';
            if (trendEl) {
                const trend = data.trend || 0;
                trendEl.textContent = Math.abs(trend);
                trendEl.className = 'metric-trend ' + (trend > 0 ? 'up' : trend < 0 ? 'down' : 'neutral');
            }
        }
    } catch (e) {}

    try {
        // Bills count
        const billsResponse = await fetch(`${CONFIG.apiBase}/bills?status=active`);
        if (billsResponse.ok) {
            const data = await billsResponse.json();
            const el = document.getElementById('metric-bills-count');
            if (el) el.textContent = data.total || data.bills?.length || '0';
        }
    } catch (e) {}

    try {
        // Hearings count
        const hearingsResponse = await fetch(`${CONFIG.apiBase}/hearings?upcoming=true`);
        if (hearingsResponse.ok) {
            const data = await hearingsResponse.json();
            const el = document.getElementById('metric-hearings-count');
            if (el) el.textContent = data.total || data.hearings?.length || '0';
        }
    } catch (e) {}

    try {
        // State signals count
        const stateResponse = await fetch(`${CONFIG.apiBase}/state/signals?days=7`);
        if (stateResponse.ok) {
            const data = await stateResponse.json();
            const el = document.getElementById('metric-state-count');
            if (el) el.textContent = data.total || data.signals?.length || '0';
        }
    } catch (e) {}

    try {
        // Battlefield vehicles
        const vehiclesResponse = await fetch(`${CONFIG.apiBase}/battlefield/vehicles`);
        if (vehiclesResponse.ok) {
            const data = await vehiclesResponse.json();
            const el = document.getElementById('metric-vehicles-count');
            if (el) el.textContent = data.total || data.vehicles?.length || '0';
        }
    } catch (e) {}
}

async function loadExecHeatMap() {
    try {
        const response = await fetch(`${CONFIG.apiBase}/battlefield/heat-scores`);
        if (response.ok) {
            const data = await response.json();

            const levels = { critical: 0, high: 0, medium: 0, low: 0 };
            (data.scores || []).forEach(item => {
                const score = item.heat_score || 0;
                if (score >= 80) levels.critical++;
                else if (score >= 60) levels.high++;
                else if (score >= 40) levels.medium++;
                else levels.low++;
            });

            const total = Math.max(levels.critical + levels.high + levels.medium + levels.low, 1);

            for (const [level, count] of Object.entries(levels)) {
                const barEl = document.getElementById(`heat-${level}`);
                const valEl = document.getElementById(`heat-${level}-val`);
                if (barEl) barEl.style.width = `${(count / total) * 100}%`;
                if (valEl) valEl.textContent = count;
            }
        }
    } catch (e) {
        console.warn('Failed to load heat map:', e);
    }
}

async function loadExecCalendar() {
    const listEl = document.getElementById('exec-calendar-list');
    if (!listEl) return;

    try {
        // Get upcoming hearings and gates
        const [hearingsRes, gatesRes] = await Promise.all([
            fetch(`${CONFIG.apiBase}/hearings?upcoming=true&limit=5`).catch(() => null),
            fetch(`${CONFIG.apiBase}/battlefield/critical-gates?days=7`).catch(() => null)
        ]);

        const events = [];

        if (hearingsRes?.ok) {
            const data = await hearingsRes.json();
            (data.hearings || []).forEach(h => {
                events.push({
                    date: h.date || h.hearing_date,
                    event: h.title || h.committee,
                    type: 'hearing'
                });
            });
        }

        if (gatesRes?.ok) {
            const data = await gatesRes.json();
            (data.gates || []).forEach(g => {
                events.push({
                    date: g.gate_date || g.date,
                    event: g.title || g.description,
                    type: 'gate',
                    urgent: g.priority === 'high'
                });
            });
        }

        // Sort by date
        events.sort((a, b) => new Date(a.date) - new Date(b.date));

        if (events.length === 0) {
            listEl.innerHTML = '<div class="calendar-item"><span class="calendar-date">--</span><span class="calendar-event">No upcoming events</span></div>';
            return;
        }

        listEl.innerHTML = events.slice(0, 5).map(evt => {
            const date = new Date(evt.date);
            const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            const className = evt.urgent ? 'urgent' : evt.type === 'gate' ? 'warning' : '';
            return `
                <div class="calendar-item ${className}">
                    <span class="calendar-date">${dateStr}</span>
                    <span class="calendar-event">${escapeHtml(evt.event)}</span>
                </div>
            `;
        }).join('');
    } catch (e) {
        listEl.innerHTML = '<div class="calendar-item"><span class="calendar-date">--</span><span class="calendar-event">Unable to load</span></div>';
    }
}

async function loadExecCriticalItems() {
    const listEl = document.getElementById('exec-critical-list');
    if (!listEl) return;

    try {
        // Try to get critical items from battlefield
        const response = await fetch(`${CONFIG.apiBase}/battlefield/critical-items?limit=5`);
        if (response.ok) {
            const data = await response.json();
            const items = data.items || [];

            if (items.length === 0) {
                listEl.innerHTML = '<li class="critical-item">No critical items at this time</li>';
                return;
            }

            listEl.innerHTML = items.map(item => `
                <li class="critical-item">${escapeHtml(item.title || item.description)}</li>
            `).join('');
        } else {
            listEl.innerHTML = '<li class="critical-item">Critical items unavailable</li>';
        }
    } catch (e) {
        listEl.innerHTML = '<li class="critical-item">Unable to load critical items</li>';
    }
}

function printExecutiveSummary() {
    window.print();
}

// =============================================================================
// CEO BRIEF VIEWER
// =============================================================================

let briefsCache = [];

async function initBriefViewer() {
    const selector = document.getElementById('brief-selector');
    if (!selector) return;

    // Load available briefs
    try {
        const response = await fetch(`${CONFIG.apiBase}/briefs?limit=20`);
        if (response.ok) {
            const data = await response.json();
            briefsCache = data.briefs || [];

            selector.innerHTML = '<option value="">Select Brief...</option>' +
                briefsCache.map(brief => {
                    const date = new Date(brief.generated_at || brief.created_at);
                    const dateStr = date.toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                    });
                    return `<option value="${brief.id}">${dateStr}</option>`;
                }).join('');
        }
    } catch (e) {
        console.warn('Failed to load briefs list:', e);
    }

    selector.addEventListener('change', (e) => {
        if (e.target.value) {
            loadBrief(e.target.value);
        } else {
            showEmptyBrief();
        }
    });
}

async function loadBrief(briefId) {
    const container = document.getElementById('brief-container');
    if (!container) return;

    container.innerHTML = '<div class="brief-empty"><p>Loading brief...</p></div>';

    try {
        const response = await fetch(`${CONFIG.apiBase}/briefs/${briefId}`);
        if (response.ok) {
            const brief = await response.json();
            renderBrief(brief);
        } else {
            throw new Error('Failed to load brief');
        }
    } catch (e) {
        container.innerHTML = '<div class="brief-empty"><p>Failed to load brief</p></div>';
    }
}

function renderBrief(brief) {
    const container = document.getElementById('brief-container');
    if (!container) return;

    // Parse markdown to HTML (simple implementation)
    let content = brief.content || brief.markdown || '';

    // Convert markdown to HTML (basic)
    content = parseMarkdown(content);

    // Add evidence pack links styling
    content = content.replace(/\[Evidence Pack: ([^\]]+)\]\(([^)]+)\)/g,
        '<a href="$2" class="evidence-link" target="_blank"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>$1</a>');

    container.innerHTML = `<div class="brief-content">${content}</div>`;
}

function parseMarkdown(text) {
    // Basic markdown to HTML conversion
    let html = text;

    // Headers
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

    // Bold and italic
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Code blocks
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Blockquotes
    html = html.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');

    // Lists
    html = html.replace(/^\* (.+)$/gm, '<li>$1</li>');
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    html = html.replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');

    // Links
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

    // Paragraphs
    html = html.replace(/\n\n/g, '</p><p>');
    html = '<p>' + html + '</p>';

    // Clean up
    html = html.replace(/<p><(h[1-6]|ul|ol|pre|blockquote)/g, '<$1');
    html = html.replace(/<\/(h[1-6]|ul|ol|pre|blockquote)><\/p>/g, '</$1>');
    html = html.replace(/<p><\/p>/g, '');

    return html;
}

function showEmptyBrief() {
    const container = document.getElementById('brief-container');
    if (container) {
        container.innerHTML = `
            <div class="brief-empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                </svg>
                <p>Select a brief from the dropdown above</p>
            </div>
        `;
    }
}

function printBrief() {
    window.print();
}

function exportBriefPdf() {
    // For now, just use print to PDF
    showToast('Use your browser\'s "Save as PDF" option in the print dialog', 'info');
    window.print();
}

// =============================================================================
// AUDIT LOG VIEWER
// =============================================================================

const auditState = {
    logs: [],
    page: 1,
    pageSize: 20,
    totalPages: 1,
    filters: {
        dateFrom: null,
        dateTo: null,
        user: '',
        action: ''
    }
};

function initAuditLog() {
    // Show audit log section for COMMANDER
    if (sessionState.user?.role === 'COMMANDER') {
        const section = document.getElementById('audit-log-section');
        if (section) section.style.display = 'block';
    }

    // Bind filter events
    document.getElementById('apply-audit-filters')?.addEventListener('click', applyAuditFilters);
    document.getElementById('audit-prev-page')?.addEventListener('click', () => navigateAuditPage(-1));
    document.getElementById('audit-next-page')?.addEventListener('click', () => navigateAuditPage(1));

    // Set default date range (last 7 days)
    const today = new Date();
    const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

    const dateFromEl = document.getElementById('audit-date-from');
    const dateToEl = document.getElementById('audit-date-to');
    if (dateFromEl) dateFromEl.value = weekAgo.toISOString().split('T')[0];
    if (dateToEl) dateToEl.value = today.toISOString().split('T')[0];

    loadAuditLog();
}

function applyAuditFilters() {
    auditState.filters.dateFrom = document.getElementById('audit-date-from')?.value || null;
    auditState.filters.dateTo = document.getElementById('audit-date-to')?.value || null;
    auditState.filters.user = document.getElementById('audit-user-filter')?.value || '';
    auditState.filters.action = document.getElementById('audit-action-filter')?.value || '';
    auditState.page = 1;
    loadAuditLog();
}

function navigateAuditPage(direction) {
    const newPage = auditState.page + direction;
    if (newPage >= 1 && newPage <= auditState.totalPages) {
        auditState.page = newPage;
        loadAuditLog();
    }
}

async function loadAuditLog() {
    const tbody = document.getElementById('audit-log-tbody');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="6" class="loading-cell">Loading audit log...</td></tr>';

    try {
        const params = new URLSearchParams({
            page: auditState.page,
            page_size: auditState.pageSize
        });

        if (auditState.filters.dateFrom) params.append('date_from', auditState.filters.dateFrom);
        if (auditState.filters.dateTo) params.append('date_to', auditState.filters.dateTo);
        if (auditState.filters.user) params.append('user', auditState.filters.user);
        if (auditState.filters.action) params.append('action', auditState.filters.action);

        const response = await fetch(`${CONFIG.apiBase}/audit/logs?${params}`, {
            credentials: 'include'
        });

        if (response.ok) {
            const data = await response.json();
            auditState.logs = data.logs || [];
            auditState.totalPages = data.total_pages || 1;

            renderAuditLog();
            updateAuditPagination();

            // Populate user filter if not done
            if (data.users) {
                const userSelect = document.getElementById('audit-user-filter');
                if (userSelect && userSelect.options.length <= 1) {
                    data.users.forEach(user => {
                        const opt = document.createElement('option');
                        opt.value = user;
                        opt.textContent = user;
                        userSelect.appendChild(opt);
                    });
                }
            }
        } else {
            throw new Error('Failed to load audit log');
        }
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="6" class="loading-cell">Audit log unavailable</td></tr>';
    }
}

function renderAuditLog() {
    const tbody = document.getElementById('audit-log-tbody');
    if (!tbody) return;

    if (auditState.logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="loading-cell">No audit entries found</td></tr>';
        return;
    }

    tbody.innerHTML = auditState.logs.map(log => {
        const timestamp = new Date(log.timestamp).toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });

        return `
            <tr>
                <td>${timestamp}</td>
                <td>${escapeHtml(log.user || log.user_email || '--')}</td>
                <td><span class="badge badge-${log.action}">${escapeHtml(log.action)}</span></td>
                <td>${escapeHtml(log.resource || log.endpoint || '--')}</td>
                <td>${escapeHtml(truncate(log.details || log.message || '', 50))}</td>
                <td>${escapeHtml(log.ip_address || '--')}</td>
            </tr>
        `;
    }).join('');
}

function updateAuditPagination() {
    const infoEl = document.getElementById('audit-pagination-info');
    const prevBtn = document.getElementById('audit-prev-page');
    const nextBtn = document.getElementById('audit-next-page');

    if (infoEl) {
        infoEl.textContent = `Page ${auditState.page} of ${auditState.totalPages}`;
    }

    if (prevBtn) prevBtn.disabled = auditState.page <= 1;
    if (nextBtn) nextBtn.disabled = auditState.page >= auditState.totalPages;
}

function exportAuditCsv() {
    if (auditState.logs.length === 0) {
        showToast('No audit data to export', 'warning');
        return;
    }

    const headers = ['Timestamp', 'User', 'Action', 'Resource', 'Details', 'IP Address'];
    const rows = auditState.logs.map(log => [
        new Date(log.timestamp).toISOString(),
        log.user || log.user_email || '',
        log.action || '',
        log.resource || log.endpoint || '',
        log.details || log.message || '',
        log.ip_address || ''
    ]);

    const csvContent = [
        headers.join(','),
        ...rows.map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `audit_log_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
    URL.revokeObjectURL(url);

    showToast('Audit log exported', 'success');
}

// =============================================================================
// MOBILE MENU
// =============================================================================

function initMobileMenu() {
    // Create mobile menu button if not exists
    const header = document.querySelector('.header-left');
    if (header && !document.querySelector('.mobile-menu-btn')) {
        const btn = document.createElement('button');
        btn.className = 'mobile-menu-btn';
        btn.innerHTML = '<span></span><span></span><span></span>';
        btn.addEventListener('click', toggleMobileMenu);
        header.insertBefore(btn, header.firstChild);
    }

    // Create overlay if not exists
    if (!document.querySelector('.mobile-overlay')) {
        const overlay = document.createElement('div');
        overlay.className = 'mobile-overlay';
        overlay.addEventListener('click', closeMobileMenu);
        document.body.appendChild(overlay);
    }

    // Add swipe support for tabs
    initSwipeNavigation();
}

function toggleMobileMenu() {
    const btn = document.querySelector('.mobile-menu-btn');
    const tabs = document.querySelector('.main-tabs');
    const overlay = document.querySelector('.mobile-overlay');

    btn?.classList.toggle('open');
    tabs?.classList.toggle('mobile-open');
    overlay?.classList.toggle('visible');
}

function closeMobileMenu() {
    const btn = document.querySelector('.mobile-menu-btn');
    const tabs = document.querySelector('.main-tabs');
    const overlay = document.querySelector('.mobile-overlay');

    btn?.classList.remove('open');
    tabs?.classList.remove('mobile-open');
    overlay?.classList.remove('visible');
}

function initSwipeNavigation() {
    let touchStartX = 0;
    let touchEndX = 0;

    const panels = document.querySelectorAll('.tab-panel');
    const tabButtons = document.querySelectorAll('.main-tab');
    const tabOrder = Array.from(tabButtons).map(btn => btn.dataset.tab);

    document.addEventListener('touchstart', e => {
        touchStartX = e.changedTouches[0].screenX;
    }, { passive: true });

    document.addEventListener('touchend', e => {
        touchEndX = e.changedTouches[0].screenX;
        handleSwipe();
    }, { passive: true });

    function handleSwipe() {
        const diff = touchStartX - touchEndX;
        const threshold = 100;

        if (Math.abs(diff) < threshold) return;

        const currentTab = document.querySelector('.main-tab.active')?.dataset.tab;
        const currentIndex = tabOrder.indexOf(currentTab);

        if (diff > 0 && currentIndex < tabOrder.length - 1) {
            // Swipe left - next tab
            const nextTab = tabOrder[currentIndex + 1];
            document.querySelector(`[data-tab="${nextTab}"]`)?.click();
        } else if (diff < 0 && currentIndex > 0) {
            // Swipe right - previous tab
            const prevTab = tabOrder[currentIndex - 1];
            document.querySelector(`[data-tab="${prevTab}"]`)?.click();
        }
    }
}

// Export Phase 3 functions for global access
window.printExecutiveSummary = printExecutiveSummary;
window.printBrief = printBrief;
window.exportBriefPdf = exportBriefPdf;
window.exportAuditCsv = exportAuditCsv;

// =============================================================================
// INITIALIZATION
// =============================================================================

// Initialize
async function init() {
    initTabs();
    initEventListeners();
    restoreCollapsedStates();

    // Initialize session management (will redirect if not authenticated)
    initSessionManagement();

    // Initialize Command Center
    initCommandCenter();

    await refreshAll();
    startAutoRefresh();
}

// Start the application
document.addEventListener('DOMContentLoaded', init);
