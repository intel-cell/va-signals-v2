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
        summaries: true
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
    frResultsCount: document.getElementById('fr-results-count')
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
        loadErrors(),
        loadSummaries(),
        loadSummarizedDocIds()
    ]);

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

// Make functions available globally for onclick handlers
window.showErrorDetails = showErrorDetails;
window.showErrorFromButton = showErrorFromButton;
window.showColumnExplanation = showColumnExplanation;
window.showHealthyExplanation = showHealthyExplanation;
window.showSummaryModal = showSummaryModal;
window.toggleSummaryDetails = toggleSummaryDetails;
window.downloadReport = downloadReport;

// Initialize
async function init() {
    initTabs();
    initEventListeners();
    await refreshAll();
    startAutoRefresh();
}

// Start the application
document.addEventListener('DOMContentLoaded', init);
