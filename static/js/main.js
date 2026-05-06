/* ═══════════════════════════════════════════════════════════════
   CloudBackupPro — Main JavaScript
   SocketIO, Charts, Toasts, Progress, Dark Mode
   ═══════════════════════════════════════════════════════════════ */

// ── SocketIO Connection ──
let socket = null;
try { socket = io(); } catch(e) { console.warn('SocketIO not available, using polling fallback'); }

// ── Toast System ──
function showToast(message, type = 'info') {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const icons = { success: 'fa-check-circle', error: 'fa-exclamation-circle', info: 'fa-info-circle' };
    toast.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i><span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => { toast.classList.add('toast-exit'); setTimeout(() => toast.remove(), 300); }, 4000);
}

// ── Mobile Sidebar Toggle ──
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) sidebar.classList.toggle('open');
}

// ── Backup Progress Polling ──
let progressInterval = null;
function startProgressPolling() {
    const section = document.getElementById('progressSection');
    if (!section) return;
    if (progressInterval) clearInterval(progressInterval);
    progressInterval = setInterval(async () => {
        try {
            const res = await fetch('/api/backup/progress');
            const data = await res.json();
            updateProgressUI(data);
            if (!data.active && data.status === 'complete') {
                clearInterval(progressInterval);
                progressInterval = null;
                showToast('Backup completed successfully!', 'success');
                setTimeout(() => location.reload(), 2000);
            }
        } catch(e) {}
    }, 1000);
}

function updateProgressUI(data) {
    const section = document.getElementById('progressSection');
    if (!section) return;
    if (data.active) {
        section.style.display = 'block';
        const fill = document.getElementById('progressFill');
        const info = document.getElementById('progressInfo');
        const fileInfo = document.getElementById('progressFile');
        if (fill) { fill.style.width = data.percent + '%'; fill.classList.add('active'); }
        if (info) info.textContent = `${data.current} / ${data.total} files (${data.percent}%) — ${data.speed_mbps} MB/s`;
        if (fileInfo) fileInfo.textContent = data.file;
    } else if (data.status === 'complete') {
        section.style.display = 'block';
        const fill = document.getElementById('progressFill');
        if (fill) { fill.style.width = '100%'; fill.classList.remove('active'); }
        const info = document.getElementById('progressInfo');
        if (info) info.textContent = 'Backup complete!';
    } else {
        section.style.display = 'none';
    }
}

// ── SocketIO real-time progress ──
if (socket) {
    socket.on('backup_progress', data => updateProgressUI({ active: true, ...data }));
    socket.on('backup_complete', data => {
        updateProgressUI({ active: false, status: 'complete', percent: 100 });
        showToast(`Backup complete: ${data.files} files (${data.size_mb} MB) in ${data.duration}s`, 'success');
        setTimeout(() => location.reload(), 2000);
    });
}

// ── Run Backup ──
async function runBackup() {
    const btn = event?.target || document.getElementById('backupBtn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting...'; }
    try {
        const res = await fetch('/api/backup/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        const data = await res.json();
        if (data.success) {
            showToast(data.message, 'success');
            startProgressPolling();
        } else {
            showToast(data.error || data.message, 'error');
        }
    } catch(e) {
        showToast('Failed to start backup', 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-play"></i> Run Backup'; }
    }
}

// ── Chart Configuration Helpers ──
const chartDefaults = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: { labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 }, padding: 16 } }
    },
    scales: {
        y: { grid: { color: 'rgba(99,102,241,0.06)' }, ticks: { color: '#64748b', font: { family: 'Inter' } } },
        x: { grid: { display: false }, ticks: { color: '#64748b', font: { family: 'Inter' } } }
    }
};

// ── Dashboard Charts ──
async function initDashboardCharts() {
    try {
        const res = await fetch('/api/chart-data');
        const data = await res.json();

        // Storage History
        const storageCtx = document.getElementById('storageChart');
        if (storageCtx) {
            new Chart(storageCtx, {
                type: 'line',
                data: {
                    labels: data.storage_history.labels,
                    datasets: [{
                        label: 'Storage (MB)',
                        data: data.storage_history.data,
                        borderColor: '#6366f1', backgroundColor: 'rgba(99,102,241,0.08)',
                        borderWidth: 2.5, pointBackgroundColor: '#6366f1',
                        pointRadius: 3, tension: 0.4, fill: true
                    }]
                },
                options: { ...chartDefaults, plugins: { ...chartDefaults.plugins, legend: { display: false } } }
            });
        }

        // Backup Speed
        const speedCtx = document.getElementById('speedChart');
        if (speedCtx) {
            new Chart(speedCtx, {
                type: 'line',
                data: {
                    labels: data.speed_history.labels,
                    datasets: [{
                        label: 'Speed (MB/s)',
                        data: data.speed_history.data,
                        borderColor: '#22d3ee', backgroundColor: 'rgba(34,211,238,0.08)',
                        borderWidth: 2.5, tension: 0.4, fill: true,
                        pointBackgroundColor: '#22d3ee', pointRadius: 3
                    }]
                },
                options: { ...chartDefaults, plugins: { ...chartDefaults.plugins, legend: { display: false } } }
            });
        }

        // Tier Usage Doughnut
        const tierCtx = document.getElementById('tierChart');
        if (tierCtx) {
            new Chart(tierCtx, {
                type: 'doughnut',
                data: {
                    labels: data.tier_usage.labels,
                    datasets: [{
                        data: data.tier_usage.data,
                        backgroundColor: ['#ef4444', '#f59e0b', '#3b82f6'],
                        borderWidth: 0, hoverOffset: 8
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8', padding: 16, font: { family: 'Inter' } } } },
                    cutout: '72%'
                }
            });
        }

        // Cost Trend
        const costCtx = document.getElementById('costChart');
        if (costCtx) {
            new Chart(costCtx, {
                type: 'line',
                data: {
                    labels: data.cost_trend.dates,
                    datasets: [{
                        label: 'Daily Cost ($)',
                        data: data.cost_trend.total,
                        borderColor: '#a855f7', backgroundColor: 'rgba(168,85,247,0.08)',
                        borderWidth: 2.5, tension: 0.4, fill: true,
                        pointBackgroundColor: '#a855f7', pointRadius: 3
                    }]
                },
                options: { ...chartDefaults, plugins: { ...chartDefaults.plugins, legend: { display: false } } }
            });
        }

        // SLA Gauge
        const healthRes = await fetch('/api/system/health');
        const health = await healthRes.json();
        const gaugeEl = document.getElementById('rpoGauge');
        if (gaugeEl) {
            const pct = Math.min(100, health.rpo_percent);
            gaugeEl.style.setProperty('--gauge-pct', pct + '%');
            gaugeEl.style.background = `conic-gradient(${pct > 70 ? '#10b981' : pct > 40 ? '#f59e0b' : '#ef4444'} ${pct}%, rgba(99,102,241,0.1) 0)`;
            const val = gaugeEl.querySelector('.gauge-value');
            if (val) val.textContent = Math.round(pct) + '%';
        }
        const rtoGauge = document.getElementById('rtoGauge');
        if (rtoGauge) {
            const sr = health.success_rate;
            rtoGauge.style.background = `conic-gradient(${sr > 80 ? '#10b981' : sr > 50 ? '#f59e0b' : '#ef4444'} ${sr}%, rgba(99,102,241,0.1) 0)`;
            const val = rtoGauge.querySelector('.gauge-value');
            if (val) val.textContent = Math.round(sr) + '%';
        }

    } catch(e) { console.error('Chart init error:', e); }

    // Check for active backup
    try {
        const pr = await fetch('/api/backup/progress');
        const pd = await pr.json();
        if (pd.active) startProgressPolling();
    } catch(e) {}
}

// ── Reports Charts ──
function initReportsCharts() {
    const savingsCtx = document.getElementById('savingsChart');
    if (savingsCtx) {
        new Chart(savingsCtx, {
            type: 'bar',
            data: {
                labels: ['Proposed (Tiered)', 'Traditional'],
                datasets: [{
                    label: 'Est. Cost ($)',
                    data: [parseFloat(savingsCtx.dataset.actual), parseFloat(savingsCtx.dataset.legacy)],
                    backgroundColor: ['rgba(99,102,241,0.7)', 'rgba(100,116,139,0.5)'],
                    borderRadius: 8, borderSkipped: false
                }]
            },
            options: {
                indexAxis: 'y', ...chartDefaults,
                plugins: { ...chartDefaults.plugins, legend: { display: false } }
            }
        });
    }
}

// ── Monitoring: Audit Log & ML ──
async function loadAuditLog() {
    try {
        const res = await fetch('/api/audit');
        const logs = await res.json();
        const container = document.getElementById('auditLog');
        if (!container) return;
        container.innerHTML = logs.map(l => `
            <div class="audit-entry">
                <span class="audit-time">${new Date(l.time).toLocaleTimeString()}</span>
                <span class="audit-action">${l.action}</span>
                <span style="flex:1;color:var(--text-secondary)">${l.details}</span>
                <span class="audit-hash" title="Current: ${l.hash}\nPrev: ${l.prev_hash}">
                    <i class="fas fa-link" style="margin-right:4px"></i>${l.hash}
                </span>
            </div>
        `).join('') || '<p style="color:var(--text-muted);padding:20px;text-align:center">No audit entries yet</p>';
    } catch(e) {}
}

async function loadMLPredictions() {
    try {
        const res = await fetch('/api/ml/prediction');
        const data = await res.json();
        const el = document.getElementById('mlPrediction');
        if (el) el.textContent = data.message;
        const crEl = document.getElementById('changeRate');
        if (crEl && data.change_rate) {
            const cr = data.change_rate;
            crEl.innerHTML = `
                <div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:12px">
                    <div class="kpi-card" style="flex:1;min-width:140px;padding:16px">
                        <div class="kpi-label">Trend</div>
                        <div style="font-size:1.1rem;font-weight:700;text-transform:capitalize">${cr.trend}</div>
                    </div>
                    <div class="kpi-card" style="flex:1;min-width:140px;padding:16px">
                        <div class="kpi-label">Rate</div>
                        <div style="font-size:1.1rem;font-weight:700">${cr.rate}x</div>
                    </div>
                    <div class="kpi-card" style="flex:1;min-width:140px;padding:16px">
                        <div class="kpi-label">Confidence</div>
                        <div style="font-size:1.1rem;font-weight:700;text-transform:capitalize">${cr.confidence}</div>
                    </div>
                </div>`;
        }
    } catch(e) {}
}

// ── Restore: Tree & Multi-select ──
function toggleJobFiles(jobId) {
    const header = document.querySelector(`[data-job="${jobId}"]`);
    const files = document.getElementById(`files-${jobId}`);
    if (header) header.classList.toggle('expanded');
    if (files) files.classList.toggle('show');
}

function toggleSelectAll(jobId) {
    const checks = document.querySelectorAll(`#files-${jobId} input[type="checkbox"]`);
    const allChecked = Array.from(checks).every(c => c.checked);
    checks.forEach(c => c.checked = !allChecked);
    updateRestoreCount();
}

function updateRestoreCount() {
    const checked = document.querySelectorAll('.file-check:checked');
    const btn = document.getElementById('restoreBatchBtn');
    if (btn) {
        btn.textContent = `Restore Selected (${checked.length})`;
        btn.disabled = checked.length === 0;
    }
}

async function restoreBatch() {
    const checked = document.querySelectorAll('.file-check:checked');
    const ids = Array.from(checked).map(c => parseInt(c.value));
    if (!ids.length) return showToast('No files selected', 'error');
    const dest = prompt('Restore destination:', '~/restored');
    if (!dest) return;
    const btn = document.getElementById('restoreBatchBtn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Restoring...'; }
    try {
        const res = await fetch('/api/restore/batch', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_ids: ids, dest: dest })
        });
        const data = await res.json();
        showToast(data.message, data.success ? 'success' : 'error');
    } catch(e) { showToast('Restore failed', 'error'); }
    finally { if (btn) { btn.disabled = false; btn.textContent = 'Restore Selected (0)'; } }
}

async function restoreSingleFile(fileId) {
    const dest = prompt('Restore destination:', '~/restored');
    if (!dest) return;
    try {
        const res = await fetch(`/api/restore/file/${fileId}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dest: dest })
        });
        const data = await res.json();
        showToast(data.message, data.success ? 'success' : 'error');
    } catch(e) { showToast('Restore failed', 'error'); }
}

// ── Drill ──
async function runDrill() {
    const btn = document.getElementById('drillBtn');
    const steps = document.querySelectorAll('.drill-step');
    const status = document.getElementById('drillStatus');
    const timer = document.getElementById('drillTimer');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Executing...'; }

    // Animate steps
    let timerVal = 0;
    const timerInt = setInterval(() => { timerVal += 0.1; if (timer) timer.textContent = timerVal.toFixed(1) + 's'; }, 100);
    steps.forEach((s, i) => setTimeout(() => { s.classList.add('active'); }, i * 600));

    try {
        const res = await fetch('/api/drill/run', { method: 'POST' });
        const data = await res.json();
        clearInterval(timerInt);
        steps.forEach(s => { s.classList.remove('active'); s.classList.add('done'); });
        if (status) {
            status.style.display = 'block';
            status.className = `glass p-4 mb-4 ${data.success ? 'border-l-4' : 'border-l-4'}`;
            status.style.borderLeftColor = data.success ? '#10b981' : '#ef4444';
            status.innerHTML = `
                <div style="font-weight:700;margin-bottom:8px">${data.success ? '✓ Drill Passed' : '✗ Drill Failed'}</div>
                <div style="color:var(--text-secondary)">${data.message}</div>
                <div style="margin-top:8px;font-size:0.85rem;color:var(--text-muted)">
                    Duration: ${data.duration_seconds}s | RTO: ${data.rto_compliant ? 'PASS ✓' : 'FAIL ✗'} (target: ${data.rto_target_seconds}s)
                </div>`;
        }
        showToast(data.success ? 'Drill passed!' : 'Drill failed', data.success ? 'success' : 'error');
    } catch(e) {
        clearInterval(timerInt);
        showToast('Drill error', 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-shield-alt"></i> Execute Recovery Drill'; }
    }
}

// ── Settings: Run Backup Now ──
async function runBackupNow() {
    try {
        const res = await fetch('/api/backup/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        const data = await res.json();
        showToast(data.message || data.error, data.success ? 'success' : 'error');
    } catch(e) { showToast('Failed to start backup', 'error'); }
}

// ── Init on DOM ready ──
document.addEventListener('DOMContentLoaded', () => {
    // Dashboard charts (only if canvases exist = backups exist)
    if (document.getElementById('storageChart') || document.getElementById('costChart')) initDashboardCharts();
    // Dashboard gauges (always present on dashboard)
    else if (document.getElementById('rpoGauge')) initDashboardGauges();
    // Dashboard progress check
    if (document.getElementById('progressSection')) {
        fetch('/api/backup/progress').then(r => r.json()).then(d => { if (d.active) startProgressPolling(); }).catch(() => {});
    }
    // Reports
    if (document.getElementById('savingsChart')) initReportsCharts();
    // Monitoring
    if (document.getElementById('auditLog')) {
        loadAuditLog();
        loadMLPredictions();
        setInterval(loadAuditLog, 5000);
        setInterval(loadMLPredictions, 15000);
    }
    // Restore: file checkboxes
    document.querySelectorAll('.file-check').forEach(c => c.addEventListener('change', updateRestoreCount));
});

// Separate gauge init for when charts are hidden
async function initDashboardGauges() {
    try {
        const healthRes = await fetch('/api/system/health');
        const health = await healthRes.json();
        const gaugeEl = document.getElementById('rpoGauge');
        if (gaugeEl) {
            const pct = Math.min(100, health.rpo_percent);
            gaugeEl.style.background = `conic-gradient(${pct > 70 ? '#10b981' : pct > 40 ? '#f59e0b' : '#ef4444'} ${pct}%, rgba(99,102,241,0.1) 0)`;
            const val = gaugeEl.querySelector('.gauge-value');
            if (val) val.textContent = Math.round(pct) + '%';
        }
        const rtoGauge = document.getElementById('rtoGauge');
        if (rtoGauge) {
            const sr = health.success_rate;
            rtoGauge.style.background = `conic-gradient(${sr > 80 ? '#10b981' : sr > 50 ? '#f59e0b' : '#ef4444'} ${sr}%, rgba(99,102,241,0.1) 0)`;
            const val = rtoGauge.querySelector('.gauge-value');
            if (val) val.textContent = Math.round(sr) + '%';
        }
    } catch(e) { console.error('Gauge init error:', e); }
}
