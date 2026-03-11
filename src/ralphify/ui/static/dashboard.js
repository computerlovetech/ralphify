// Ralphify Dashboard — Preact + htm + Signals
// Pre-built single-file bundle (no build step required at install time)

import { h, render } from 'https://esm.sh/preact@10.19.3';
import { useState, useEffect, useRef, useCallback } from 'https://esm.sh/preact@10.19.3/hooks';
import { signal, computed } from 'https://esm.sh/@preact/signals@1.3.0?deps=preact@10.19.3';
import htm from 'https://esm.sh/htm@3.1.1';

const html = htm.bind(h);

// ── State ──────────────────────────────────────────────────────────

const runs = signal([]);
const activeRunId = signal(null);
const activeIteration = signal(null);
const iterations = signal({});  // run_id -> [{iteration, status, ...}]
const checkHealth = signal({});  // run_id -> {check_name -> [pass/fail/timeout...]}
const wsConnected = signal(false);
const showNewRunModal = signal(false);
const preSelectedPrompt = signal(null);
const activeTab = signal('runs');  // runs | configure | history
const toastMessage = signal(null);  // { text, type: 'error' | 'info' }
const sidebarOpen = signal(false);  // mobile sidebar drawer

const activeRun = computed(() => runs.value.find(r => r.run_id === activeRunId.value));

// ── Time helpers ────────────────────────────────────────────────────

function formatElapsed(startIso) {
  if (!startIso) return null;
  const start = new Date(startIso);
  const now = new Date();
  const seconds = Math.floor((now - start) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function formatTimeAgo(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  const now = new Date();
  const seconds = Math.floor((now - date) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function formatDateTime(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  return date.toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function selectRun(run_id) {
  if (run_id === activeRunId.value) return;
  activeRunId.value = run_id;
  // Auto-select the latest iteration for the new run
  const runIters = iterations.value[run_id] || [];
  activeIteration.value = runIters.length > 0 ? runIters[runIters.length - 1].iteration : null;
  // Load persisted iteration data if none in memory
  if (runIters.length === 0) {
    loadIterations(run_id);
  }
}

async function loadIterations(run_id) {
  try {
    const data = await api('GET', `/runs/${run_id}/iterations`);
    if (data && data.length > 0) {
      iterations.value = { ...iterations.value, [run_id]: data };
      // Also rebuild check health sparklines from the loaded data
      const health = {};
      for (const it of data) {
        if (it.checks) {
          for (const c of it.checks) {
            if (!health[c.name]) health[c.name] = [];
            health[c.name].push(c.passed ? 'pass' : c.timed_out ? 'timeout' : 'fail');
          }
        }
      }
      if (Object.keys(health).length > 0) {
        checkHealth.value = { ...checkHealth.value, [run_id]: health };
      }
      // Auto-select the latest iteration
      if (run_id === activeRunId.value) {
        activeIteration.value = data[data.length - 1].iteration;
      }
    }
  } catch { /* endpoint may not exist on older servers */ }
}

function showToast(text, type = 'error') {
  toastMessage.value = { text, type };
  globalThis.setTimeout(() => { toastMessage.value = null; }, 4000);
}

// ── WebSocket ──────────────────────────────────────────────────────

let ws = null;
let reconnectTimer = null;

function connectWs() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${protocol}//${location.host}/api/ws`);

  ws.onopen = () => {
    wsConnected.value = true;
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    // Re-fetch runs on reconnect to restore any state missed while disconnected
    loadRuns();
  };

  ws.onclose = () => {
    wsConnected.value = false;
    reconnectTimer = setTimeout(connectWs, 2000);
  };

  ws.onerror = () => ws.close();

  ws.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data);
      handleEvent(event);
    } catch (err) {
      console.error('WS parse error:', err);
    }
  };
}

function handleEvent(event) {
  const { type, run_id, data, timestamp } = event;

  if (type === 'run_started') {
    const existing = runs.value.find(r => r.run_id === run_id);
    if (existing) {
      // Merge extra data (prompt_name, check counts, etc.) from the event
      updateRun(run_id, { status: 'running', started_at: timestamp || existing.started_at, ...data });
    } else {
      runs.value = [...runs.value, {
        run_id,
        status: 'running',
        iteration: 0,
        completed: 0,
        failed: 0,
        timed_out: 0,
        started_at: timestamp,
        ...data,
      }];
    }
    if (!activeRunId.value) selectRun(run_id);
  }

  else if (type === 'iteration_started') {
    updateRun(run_id, { iteration: data.iteration, status: 'running' });
    const runIters = iterations.value[run_id] || [];
    iterations.value = {
      ...iterations.value,
      [run_id]: [...runIters, { iteration: data.iteration, status: 'running' }],
    };
    // Auto-select the latest iteration for the active run
    if (run_id === activeRunId.value) {
      activeIteration.value = data.iteration;
    }
  }

  else if (type === 'iteration_completed') {
    updateRun(run_id, r => ({ completed: r.completed + 1 }));
    updateIteration(run_id, data.iteration, {
      status: 'success',
      returncode: data.returncode,
      duration: data.duration_formatted,
      detail: data.detail,
    });
  }

  else if (type === 'iteration_failed') {
    updateRun(run_id, r => ({ failed: r.failed + 1 }));
    updateIteration(run_id, data.iteration, {
      status: 'failure',
      returncode: data.returncode,
      duration: data.duration_formatted,
      detail: data.detail,
    });
  }

  else if (type === 'iteration_timed_out') {
    updateRun(run_id, r => ({ failed: r.failed + 1, timed_out: r.timed_out + 1 }));
    updateIteration(run_id, data.iteration, {
      status: 'timeout',
      duration: data.duration_formatted,
      detail: data.detail,
    });
  }

  else if (type === 'checks_completed') {
    updateIteration(run_id, data.iteration, { checks: data.results });
    // Update check health sparklines
    const health = { ...(checkHealth.value[run_id] || {}) };
    for (const r of (data.results || [])) {
      if (!health[r.name]) health[r.name] = [];
      health[r.name] = [...health[r.name], r.passed ? 'pass' : r.timed_out ? 'timeout' : 'fail'];
    }
    checkHealth.value = { ...checkHealth.value, [run_id]: health };
  }

  else if (type === 'run_stopped') {
    const status = data.reason === 'completed' ? 'completed'
                 : data.reason === 'error' ? 'failed'
                 : 'stopped';
    updateRun(run_id, { status, stopped_at: timestamp, ...data });
    // Mark any in-progress iterations as crashed/stopped
    if (status !== 'completed') {
      const run = runs.value.find(r => r.run_id === run_id);
      const runIters = iterations.value[run_id] || [];
      const updated = runIters.map(it =>
        it.status === 'running'
          ? { ...it, status: status === 'failed' ? 'failure' : 'stopped', detail: run?.lastError }
          : it
      );
      if (updated !== runIters) {
        iterations.value = { ...iterations.value, [run_id]: updated };
      }
    }
    if (data.reason === 'error') {
      showToast('Run failed — check the timeline for details.', 'error');
    }
  }

  else if (type === 'log_message') {
    // Store log messages so they can be displayed in the iteration panel
    if (data.level === 'error' && data.message) {
      updateRun(run_id, r => ({ lastError: data.message }));
    }
  }

  else if (type === 'run_paused') {
    updateRun(run_id, { status: 'paused' });
  }

  else if (type === 'run_resumed') {
    updateRun(run_id, { status: 'running' });
  }
}

function updateRun(run_id, updates) {
  runs.value = runs.value.map(r => {
    if (r.run_id !== run_id) return r;
    const u = typeof updates === 'function' ? updates(r) : updates;
    return { ...r, ...u };
  });
}

function updateIteration(run_id, iteration, updates) {
  const runIters = iterations.value[run_id] || [];
  iterations.value = {
    ...iterations.value,
    [run_id]: runIters.map(it =>
      it.iteration === iteration ? { ...it, ...updates } : it
    ),
  };
}

// ── API ────────────────────────────────────────────────────────────

async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`/api${path}`, opts);
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try { const err = await res.json(); if (err.detail) detail = err.detail; } catch {}
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

async function createRun(config) {
  try {
    const run = await api('POST', '/runs', config);
    // Add run to state immediately so UI doesn't flash empty state
    // while waiting for the run_started WebSocket event.
    const existing = runs.value.find(r => r.run_id === run.run_id);
    if (!existing) {
      runs.value = [...runs.value, { ...run, status: run.status || 'running' }];
    }
    showNewRunModal.value = false;
    selectRun(run.run_id);
    activeTab.value = 'runs';
  } catch (e) {
    showToast(e.message);
    throw e;
  }
}

async function pauseRun(run_id) {
  try { await api('POST', `/runs/${run_id}/pause`); }
  catch (e) { showToast(e.message); }
}
async function resumeRun(run_id) {
  try { await api('POST', `/runs/${run_id}/resume`); }
  catch (e) { showToast(e.message); }
}
async function stopRun(run_id) {
  try { await api('POST', `/runs/${run_id}/stop`); }
  catch (e) { showToast(e.message); }
}

async function updateRunSettings(run_id, settings) {
  try {
    const data = await api('PATCH', `/runs/${run_id}/settings`, settings);
    updateRun(run_id, data);
    showToast('Settings updated', 'success');
  } catch (e) {
    showToast(e.message);
  }
}

function startRunWithPrompt(name) {
  preSelectedPrompt.value = name;
  showNewRunModal.value = true;
}

async function loadRuns() {
  try {
    const data = await api('GET', '/runs');
    // Merge server state with local state to preserve fields added by WS events
    // (e.g. prompt_name from run_started, lastError from log_message).
    const existing = new Map(runs.value.map(r => [r.run_id, r]));
    const merged = data.map(r => ({ ...(existing.get(r.run_id) || {}), ...r }));
    // Also keep any local-only runs not yet on the server
    for (const [id, local] of existing) {
      if (!data.find(r => r.run_id === id)) merged.push(local);
    }
    runs.value = merged;
    // Auto-select a run on initial load if nothing is selected
    if (!activeRunId.value && merged.length > 0) {
      const active = merged.find(r => ['running', 'paused'].includes(r.status));
      selectRun((active || merged[0]).run_id);
    }
  } catch (e) { /* server may not be ready */ }
}

// ── Components ─────────────────────────────────────────────────────

function App() {
  useEffect(() => {
    connectWs();
    loadRuns();
    return () => { if (ws) ws.close(); };
  }, []);

  return html`
    <${Sidebar} />
    <${Main} />
    ${showNewRunModal.value && html`<${NewRunModal} />`}
    ${toastMessage.value && html`<${Toast} ...${toastMessage.value} />`}
  `;
}

function Toast({ text, type }) {
  return html`
    <div class="toast toast-${type}" onClick=${() => toastMessage.value = null}>
      ${type === 'error' && html`
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>
        </svg>
      `}
      ${type === 'success' && html`
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
      `}
      ${text}
    </div>
  `;
}

// ── Sidebar ────────────────────────────────────────────────────────

function Sidebar() {
  const active = runs.value.filter(r => ['running', 'paused', 'pending'].includes(r.status));
  const recent = runs.value.filter(r => ['completed', 'stopped', 'failed'].includes(r.status));

  return html`
    ${sidebarOpen.value && html`<div class="sidebar-overlay" onClick=${() => sidebarOpen.value = false}></div>`}
    <div class="sidebar ${sidebarOpen.value ? 'open' : ''}">
      <div class="sidebar-header">
        <div class="sidebar-header-inner">
          <div class="logo-mark">R</div>
          <h1>Ralphify</h1>
          <span class="version">UI</span>
          <button class="sidebar-close-btn" onClick=${() => sidebarOpen.value = false} aria-label="Close menu">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <path d="M18 6L6 18"/><path d="M6 6l12 12"/>
            </svg>
          </button>
        </div>
        <button class="sidebar-new-run-btn" onClick=${() => { showNewRunModal.value = true; sidebarOpen.value = false; }}>
          + New Run
        </button>
      </div>
      <div class="sidebar-runs">
        <div class="sidebar-section">
          <div class="sidebar-section-title">Active Runs</div>
          ${active.length === 0 && html`
            <div style="padding: 8px 12px; font-size: 13px; color: var(--text-muted)">No active runs</div>
          `}
          ${active.map(r => html`<${RunCard} key=${r.run_id} run=${r} />`)}
        </div>
        <div class="sidebar-section">
          <div class="sidebar-section-title">Recent</div>
          ${recent.length === 0 && html`
            <div style="padding: 8px 12px; font-size: 13px; color: var(--text-muted)">No recent runs</div>
          `}
          ${recent.map(r => html`<${RunCard} key=${r.run_id} run=${r} />`)}
        </div>
      </div>
    </div>
  `;
}

function RunCard({ run }) {
  const isSelected = activeRunId.value === run.run_id;
  const total = run.completed + run.failed;
  const passRate = total > 0 ? (run.completed / total) * 100 : 0;
  const shortId = run.run_id.length > 8 ? run.run_id.slice(0, 8) : run.run_id;
  const displayTitle = run.prompt_name || shortId;
  const isRunning = ['running', 'paused', 'pending'].includes(run.status);

  // Live elapsed time for active runs
  const [elapsed, setElapsed] = useState(() => formatElapsed(run.started_at));
  useEffect(() => {
    if (!isRunning || !run.started_at) return;
    const timer = setInterval(() => setElapsed(formatElapsed(run.started_at)), 1000);
    return () => clearInterval(timer);
  }, [isRunning, run.started_at]);

  return html`
    <div class="run-card ${isSelected ? 'active' : ''}" onClick=${() => { selectRun(run.run_id); sidebarOpen.value = false; }}>
      <div class="run-badge ${run.status}"></div>
      <div class="run-card-info">
        <div class="run-card-title">${displayTitle}</div>
        <div class="run-card-meta">
          ${run.prompt_name ? shortId + ' · ' : ''}iter ${run.iteration || 0}${total > 0 ? ` · ${Math.round(passRate)}%` : ''}${isRunning && elapsed ? ` · ${elapsed}` : ''}
        </div>
      </div>
      ${total > 0 && html`
        <div class="run-card-bar">
          <div class="run-card-bar-fill ${passRate >= 50 ? 'pass' : 'fail'}" style="width: ${passRate}%"></div>
        </div>
      `}
    </div>
  `;
}

// ── Main area ──────────────────────────────────────────────────────

function TabIcon({ tab, size = 16 }) {
  const s = size;
  if (tab === 'runs') return html`
    <svg width=${s} height=${s} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
    </svg>`;
  if (tab === 'configure') return html`
    <svg width=${s} height=${s} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>`;
  if (tab === 'history') return html`
    <svg width=${s} height=${s} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
    </svg>`;
  return null;
}

function Main() {
  const run = activeRun.value;
  const activeCount = runs.value.filter(r => ['running', 'paused', 'pending'].includes(r.status)).length;
  const historyCount = runs.value.filter(r => ['completed', 'stopped', 'failed'].includes(r.status)).length;

  return html`
    <div class="main">
      <${ControlsBar} run=${run} />
      <div class="tabs">
        <div class="tab ${activeTab.value === 'runs' ? 'active' : ''}"
             onClick=${() => activeTab.value = 'runs'}>
          <${TabIcon} tab="runs" size=${15} />
          Runs
          ${activeCount > 0 && html`<span class="tab-badge active">${activeCount}</span>`}
        </div>
        <div class="tab ${activeTab.value === 'configure' ? 'active' : ''}"
             onClick=${() => activeTab.value = 'configure'}>
          <${TabIcon} tab="configure" size=${15} />
          Configure
        </div>
        <div class="tab ${activeTab.value === 'history' ? 'active' : ''}"
             onClick=${() => activeTab.value = 'history'}>
          <${TabIcon} tab="history" size=${15} />
          History
          ${historyCount > 0 && html`<span class="tab-badge">${historyCount}</span>`}
        </div>
      </div>
      <div class="content">
        ${activeTab.value === 'runs' && (!run ? html`<${EmptyState} />` : html`<${TimelineView} run=${run} />`)}
        ${activeTab.value === 'configure' && html`<${ConfigureView} />`}
        ${activeTab.value === 'history' && html`<${HistoryView} />`}
      </div>
    </div>
  `;
}

function EmptyState() {
  return html`
    <div class="empty-state">
      <div class="empty-illustration">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
          <g stroke="url(#eig)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 2v6h-6"/>
            <path d="M21 13a9 9 0 1 1-3-7.7L21 8"/>
          </g>
          <defs>
            <linearGradient id="eig" x1="0" y1="0" x2="24" y2="24">
              <stop stop-color="#8B6CF0"/>
              <stop offset="1" stop-color="#E87B4A"/>
            </linearGradient>
          </defs>
        </svg>
      </div>
      <div class="empty-state-text">Ready when you are</div>
      <div class="empty-state-hint">
        Launch an autonomous coding loop and watch your AI agent iterate, test, and improve.
      </div>
      <button class="btn btn-primary btn-lg" onClick=${() => showNewRunModal.value = true}>
        + New Run
      </button>
      <div class="empty-state-steps">
        <div class="step-card step-card-clickable" onClick=${() => activeTab.value = 'configure'}>
          <div class="step-number">1</div>
          <div class="step-title">Configure</div>
          <div class="step-desc">Set up checks and a prompt in your project</div>
        </div>
        <div class="step-card step-card-clickable" onClick=${() => showNewRunModal.value = true}>
          <div class="step-number">2</div>
          <div class="step-title">Launch</div>
          <div class="step-desc">Start a new run from the dashboard</div>
        </div>
        <div class="step-card">
          <div class="step-number">3</div>
          <div class="step-title">Monitor</div>
          <div class="step-desc">Watch iterations and checks in real time</div>
        </div>
      </div>
    </div>
  `;
}

// ── Controls bar ───────────────────────────────────────────────────

function ControlsBar({ run }) {
  return html`
    <div class="controls-bar">
      <button class="hamburger-btn" onClick=${() => sidebarOpen.value = !sidebarOpen.value} aria-label="Toggle menu">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      </button>
      ${run ? html`<${RunControls} run=${run} />` : html`
        <div class="controls-bar-hint">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
          </svg>
          Select a run to see controls
        </div>
      `}
      <div class="connection-status">
        <div class="connection-dot ${wsConnected.value ? 'connected' : 'disconnected'}"></div>
        ${wsConnected.value ? 'Connected' : 'Disconnected'}
      </div>
    </div>
  `;
}

function RunControls({ run }) {
  const isRunning = run.status === 'running';
  const isPaused = run.status === 'paused';
  const isActive = isRunning || isPaused;
  const isFinished = ['completed', 'stopped', 'failed'].includes(run.status);
  const displayTitle = run.prompt_name || 'Ad-hoc run';

  return html`
    <div class="controls-run-name">${displayTitle}</div>
    <span class="run-status-badge ${run.status}">${run.status}</span>
    <div class="controls-separator"></div>
    ${isRunning && html`
      <button class="btn btn-sm" onClick=${() => pauseRun(run.run_id)}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
          <rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
        </svg>
        Pause
      </button>
    `}
    ${isPaused && html`
      <button class="btn btn-sm btn-primary" onClick=${() => resumeRun(run.run_id)}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="5 3 19 12 5 21 5 3"/>
        </svg>
        Resume
      </button>
    `}
    ${isActive && html`
      <button class="btn btn-sm btn-danger" onClick=${() => stopRun(run.run_id)}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="4" y="4" width="16" height="16" rx="2"/>
        </svg>
        Stop
      </button>
    `}
    ${isFinished && html`
      <button class="btn btn-sm btn-primary" onClick=${() => {
        if (run.prompt_name) {
          startRunWithPrompt(run.prompt_name);
        } else {
          showNewRunModal.value = true;
        }
      }}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
        </svg>
        Run Again
      </button>
    `}
    <div class="controls-separator"></div>
    <div class="controls-stats">
      <div class="controls-stat">
        <span class="controls-stat-value">${run.iteration || 0}</span>
        <span class="controls-stat-label">Iter</span>
      </div>
      <div class="controls-stat">
        <span class="controls-stat-value green">${run.completed}</span>
        <span class="controls-stat-label">Pass</span>
      </div>
      <div class="controls-stat">
        <span class="controls-stat-value red">${run.failed}</span>
        <span class="controls-stat-label">Fail</span>
      </div>
    </div>
  `;
}

// ── Run Overview ────────────────────────────────────────────────────

function RunOverview({ run }) {
  const total = run.completed + run.failed;
  const passRate = total > 0 ? Math.round((run.completed / total) * 100) : 0;
  const timedOut = run.timed_out || 0;
  const failedOnly = run.failed - timedOut;

  // SVG ring calculations
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const passOffset = total > 0 ? circumference * (1 - run.completed / total) : circumference;
  const failOffset = total > 0 ? circumference * (1 - run.failed / total) : circumference;

  // Hint text based on run state
  const isRunning = run.status === 'running';
  const isHealthy = run.failed === 0 || passRate >= 80;
  const hint = isRunning
    ? (isHealthy
        ? 'All looking good — your agent is making progress.'
        : `Pass rate is ${passRate}%. Check the health sparklines below for stuck checks.`)
    : run.status === 'failed'
        ? (run.lastError || (total > 0 ? `Run failed after ${total} iterations.` : 'Run failed.'))
    : run.status === 'completed'
        ? `Run completed with ${passRate}% pass rate across ${total} iterations.`
        : `Run ${run.status}. ${run.iteration || total} iteration${(run.iteration || total) !== 1 ? 's' : ''} ran.`;

  const isActive = ['running', 'paused', 'pending'].includes(run.status);

  // Live elapsed time for active runs
  const [elapsed, setElapsed] = useState(formatElapsed(run.started_at));
  useEffect(() => {
    if (!isActive || !run.started_at) return;
    const timer = setInterval(() => setElapsed(formatElapsed(run.started_at)), 1000);
    return () => clearInterval(timer);
  }, [isActive, run.started_at]);

  // For finished runs, show total duration if we have both timestamps
  const duration = !isActive && run.started_at && run.stopped_at
    ? formatElapsed(run.started_at)  // stopped_at - started_at would be better, but this shows total from start
    : null;

  // Mid-run settings
  const [showRunSettings, setShowRunSettings] = useState(false);
  const [sMaxIter, setSMaxIter] = useState(run.max_iterations != null ? String(run.max_iterations) : '');
  const [sDelay, setSDelay] = useState(run.delay != null ? String(run.delay) : '0');
  const [sTimeout, setSTimeout] = useState(run.timeout != null ? String(run.timeout) : '');
  const [sStopOnError, setSStopOnError] = useState(run.stop_on_error || false);
  const [sSaving, setSSaving] = useState(false);

  // Sync settings when switching runs
  useEffect(() => {
    setSMaxIter(run.max_iterations != null ? String(run.max_iterations) : '');
    setSDelay(run.delay != null ? String(run.delay) : '0');
    setSTimeout(run.timeout != null ? String(run.timeout) : '');
    setSStopOnError(run.stop_on_error || false);
    setShowRunSettings(false);
  }, [run.run_id]);

  const settingsChanged = (sMaxIter !== (run.max_iterations != null ? String(run.max_iterations) : ''))
    || (sDelay !== (run.delay != null ? String(run.delay) : '0'))
    || (sTimeout !== (run.timeout != null ? String(run.timeout) : ''))
    || (sStopOnError !== (run.stop_on_error || false));

  async function handleApplySettings() {
    setSSaving(true);
    const settings = {};
    if (sMaxIter.trim()) settings.max_iterations = parseInt(sMaxIter);
    else settings.max_iterations = null;
    settings.delay = sDelay.trim() ? parseFloat(sDelay) : 0;
    if (sTimeout.trim()) settings.timeout = parseFloat(sTimeout);
    else settings.timeout = null;
    settings.stop_on_error = sStopOnError;
    await updateRunSettings(run.run_id, settings);
    setSSaving(false);
  }

  return html`
    <div class="run-overview">
      <div class="run-overview-header">
        <div class="run-overview-title">
          <h2>${run.prompt_name || 'Ad-hoc run'}</h2>
          <span class="run-status-badge ${run.status}">${run.status}</span>
        </div>
        <div class="run-overview-meta">
          <span style="font-family: var(--font-mono); font-size: 12px; color: var(--text-muted)">${run.run_id.length > 8 ? run.run_id.slice(0, 8) : run.run_id}</span>
          ${run.started_at && html`
            <span class="run-overview-time">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
              </svg>
              ${isActive
                ? html`<span>Running for <strong>${elapsed}</strong></span>`
                : html`<span title=${formatDateTime(run.started_at)}>${formatTimeAgo(run.started_at)}</span>`
              }
            </span>
          `}
        </div>
      </div>
      <div class="run-overview-body">
        <div class="run-progress-ring">
          <svg width="96" height="96" viewBox="0 0 96 96">
            <circle class="ring-bg" cx="48" cy="48" r="${radius}" />
            <circle class="ring-pass" cx="48" cy="48" r="${radius}"
                    stroke-dasharray="${circumference}"
                    stroke-dashoffset="${passOffset}" />
          </svg>
          <div class="run-progress-label">
            <span class="run-progress-pct">${total > 0 ? `${passRate}%` : '—'}</span>
            <span class="run-progress-sub">pass rate</span>
          </div>
        </div>
        <div class="run-stats-grid">
          <div class="run-stat">
            <span class="run-stat-value primary">${run.iteration || 0}</span>
            <span class="run-stat-label">Iterations</span>
          </div>
          <div class="run-stat">
            <span class="run-stat-value green">${run.completed}</span>
            <span class="run-stat-label">Passed</span>
          </div>
          <div class="run-stat">
            <span class="run-stat-value red">${failedOnly > 0 ? failedOnly : 0}</span>
            <span class="run-stat-label">Failed</span>
          </div>
          <div class="run-stat">
            <span class="run-stat-value yellow">${timedOut}</span>
            <span class="run-stat-label">Timed Out</span>
          </div>
        </div>
      </div>
      <div class="run-overview-hint">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <circle cx="12" cy="12" r="10"/>
          <path d="M12 16v-4"/>
          <path d="M12 8h.01"/>
        </svg>
        ${hint}
      </div>
      ${isActive && html`
        <div class="run-settings-toggle" onClick=${() => setShowRunSettings(!showRunSettings)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
               style="transform: rotate(${showRunSettings ? '90deg' : '0deg'}); transition: transform 0.15s ease">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
          Run Settings
          ${settingsChanged && html`<span class="settings-badge">modified</span>`}
        </div>
        ${showRunSettings && html`
          <div class="run-settings-panel">
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">Max iterations</label>
                <input class="form-input" type="number" value=${sMaxIter}
                       onInput=${(e) => setSMaxIter(e.target.value)} placeholder="unlimited" min="1" />
              </div>
              <div class="form-group">
                <label class="form-label">Delay (s)</label>
                <input class="form-input" type="number" value=${sDelay}
                       onInput=${(e) => setSDelay(e.target.value)} placeholder="0" min="0" />
              </div>
              <div class="form-group">
                <label class="form-label">Timeout (s)</label>
                <input class="form-input" type="number" value=${sTimeout}
                       onInput=${(e) => setSTimeout(e.target.value)} placeholder="none" min="1" />
              </div>
            </div>
            <div class="run-settings-footer">
              <label class="checkbox-row">
                <input type="checkbox" checked=${sStopOnError}
                       onChange=${(e) => setSStopOnError(e.target.checked)} />
                <span>Stop on first error</span>
              </label>
              <button class="btn btn-primary btn-sm" onClick=${handleApplySettings} disabled=${!settingsChanged || sSaving}>
                ${sSaving ? 'Applying...' : 'Apply'}
              </button>
            </div>
          </div>
        `}
      `}
      ${['completed', 'stopped', 'failed'].includes(run.status) && html`
        <div class="run-overview-actions">
          <button class="btn btn-primary" onClick=${() => {
            if (run.prompt_name) {
              startRunWithPrompt(run.prompt_name);
            } else {
              showNewRunModal.value = true;
            }
          }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
            </svg>
            Run Again
          </button>
        </div>
      `}
    </div>
  `;
}

// ── Timeline view ──────────────────────────────────────────────────

function TimelineView({ run }) {
  const runIters = iterations.value[run.run_id] || [];
  const selectedIter = activeIteration.value;
  const selected = runIters.find(it => it.iteration === selectedIter);
  const health = checkHealth.value[run.run_id] || {};

  return html`
    <${RunOverview} run=${run} />
    <${Timeline} iterations=${runIters} selectedIteration=${selectedIter} run=${run} />
    ${selected && html`<${IterationPanel} iteration=${selected} />`}
    ${Object.keys(health).length > 0 && html`<${CheckHealthPanel} health=${health} />`}
  `;
}

function Timeline({ iterations: iters, selectedIteration, run }) {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
    }
  }, [iters.length]);

  const isActive = ['running', 'paused', 'pending'].includes(run?.status);
  const emptyMsg = isActive
    ? 'Waiting for iterations...'
    : run?.iteration > 0
      ? 'Iteration details not available (run was started before this session).'
      : 'No iterations recorded.';

  return html`
    <div class="timeline" ref=${scrollRef}>
      ${iters.length === 0 && html`
        <div style="color: var(--text-secondary); font-size: 13px; padding: 4px">
          ${emptyMsg}
        </div>
      `}
      ${iters.map(it => html`
        <div key=${it.iteration}
             class="timeline-block ${it.status} ${it.iteration === selectedIteration ? 'active' : ''}"
             onClick=${() => activeIteration.value = it.iteration}
             title="Iteration ${it.iteration}: ${it.status}">
          ${it.iteration}
        </div>
      `)}
    </div>
  `;
}

function IterationPanel({ iteration: it }) {
  const statusClass = it.status === 'success' ? 'success' :
                      it.status === 'failure' ? 'failure' :
                      it.status === 'timeout' ? 'timeout' :
                      it.status === 'stopped' ? 'failure' : '';

  const statusLabel = it.status === 'success' ? 'Passed' :
                      it.status === 'failure' ? 'Failed' :
                      it.status === 'timeout' ? 'Timed out' :
                      it.status === 'stopped' ? 'Stopped' :
                      it.status === 'running' ? 'Running' : it.status;

  const statusIcon = it.status === 'success' ? '\u2713' :
                     it.status === 'failure' ? '\u2717' :
                     it.status === 'timeout' ? '\u23f1' :
                     it.status === 'stopped' ? '\u25a0' : '\u2022';

  const passedCount = it.checks ? it.checks.filter(c => c.passed).length : 0;
  const totalChecks = it.checks ? it.checks.length : 0;

  return html`
    <div class="iteration-panel">
      <div class="iteration-header">
        <div class="iteration-header-left">
          <span class="iteration-title">Iteration ${it.iteration}</span>
          <div class="iteration-meta">
            ${it.duration && html`
              <span class="iteration-meta-tag">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                  <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
                </svg>
                ${it.duration}
              </span>
            `}
            ${it.returncode !== undefined && it.returncode !== null && html`
              <span class="iteration-meta-tag">exit ${it.returncode}</span>
            `}
            ${totalChecks > 0 && html`
              <span class="iteration-meta-tag">${passedCount}/${totalChecks} checks</span>
            `}
          </div>
        </div>
        <span class="iteration-status ${statusClass}">
          ${statusIcon} ${statusLabel}
        </span>
      </div>
      <div class="iteration-body">
        ${it.detail && it.detail !== it.status && html`
          <div class="iteration-detail">${it.detail}</div>
        `}
        ${it.checks && it.checks.length > 0 && html`
          <div class="check-results">
            <div class="checks-section-title">Check Results</div>
            ${it.checks.map(c => {
              const checkStatus = c.passed ? 'pass' : c.timed_out ? 'timeout' : 'fail';
              return html`
                <div class="check-result ${checkStatus}" key=${c.name}>
                  <span class="check-icon ${checkStatus}">
                    ${c.passed ? '\u2713' : c.timed_out ? '\u23f1' : '\u2717'}
                  </span>
                  <span class="check-name">${c.name}</span>
                  ${!c.passed && html`
                    <span class="check-detail">exit ${c.exit_code}</span>
                  `}
                </div>
              `;
            })}
          </div>
        `}
        ${it.status === 'running' && html`
          <div style="color: var(--text-secondary); font-size: 13px; display: flex; align-items: center; gap: 8px">
            <div style="width: 8px; height: 8px; border-radius: 50%; background: var(--primary); animation: pulse 1.5s infinite"></div>
            Running...
          </div>
        `}
      </div>
    </div>
  `;
}

function CheckHealthPanel({ health }) {
  const checkNames = Object.keys(health);
  const maxLen = Math.max(...checkNames.map(n => health[n].length));

  // Detect stuck loops: 5+ consecutive failures
  const alerts = [];
  for (const name of checkNames) {
    const results = health[name];
    let consecutive = 0;
    for (let i = results.length - 1; i >= 0; i--) {
      if (results[i] !== 'pass') consecutive++;
      else break;
    }
    if (consecutive >= 5) {
      alerts.push(`${name}: ${consecutive} consecutive failures`);
    }
  }

  return html`
    <div class="check-health">
      <div class="check-health-title">Check Health</div>
      ${checkNames.map(name => html`
        <div class="check-health-row" key=${name}>
          <div class="check-health-name" title=${name}>${name}</div>
          <div class="sparkline">
            ${health[name].map((status, i) => html`
              <span key=${i} class="sparkline-bar ${status}"
                    style="height: ${status === 'pass' ? '16px' : '12px'}"></span>
            `)}
          </div>
        </div>
      `)}
      ${alerts.map(alert => html`
        <div class="alert-banner" key=${alert}>${alert}</div>
      `)}
    </div>
  `;
}

// ── Configure view (all primitives) ─────────────────────────────

function KindIcon({ kind, size = 20 }) {
  const s = size;
  if (kind === 'checks') return html`
    <svg width=${s} height=${s} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>
    </svg>`;
  if (kind === 'contexts') return html`
    <svg width=${s} height=${s} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>
    </svg>`;
  if (kind === 'instructions') return html`
    <svg width=${s} height=${s} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
    </svg>`;
  return html`
    <svg width=${s} height=${s} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
    </svg>`;
}

const KINDS_META = {
  prompts: { label: 'Prompts', desc: 'Named task descriptions for starting runs' },
  checks: { label: 'Checks', desc: 'Validation scripts that verify each iteration' },
  contexts: { label: 'Contexts', desc: 'Dynamic context injected into prompts' },
  instructions: { label: 'Instructions', desc: 'Static instructions prepended to prompts' },
};

function ConfigureView() {
  const [primitives, setPrimitives] = useState(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState({ page: 'overview' });

  useEffect(() => { loadPrimitives(); }, []);

  async function loadPrimitives() {
    try {
      const data = await api('GET', `/projects/${btoa('.')}/primitives`);
      setPrimitives(data);
    } catch (e) {
      setPrimitives([]);
    }
    setLoading(false);
  }

  if (loading) return html`<div style="color: var(--text-secondary); padding: 20px">Loading primitives...</div>`;

  const grouped = { checks: [], contexts: [], instructions: [], prompts: [] };
  for (const p of (primitives || [])) {
    if (grouped[p.kind]) grouped[p.kind].push(p);
  }

  if (view.page === 'overview') {
    return html`
      <div class="prim-overview">
        <div class="prim-overview-header">
          <h2>Configure</h2>
          <p>Set up prompts, checks, contexts, and instructions for your coding loops.</p>
        </div>
        <div class="prim-overview-grid">
          ${['prompts', 'checks', 'contexts', 'instructions'].map(kind => {
            const meta = KINDS_META[kind];
            const count = grouped[kind].length;
            const enabledCount = grouped[kind].filter(p => p.enabled).length;
            return html`
              <button key=${kind} class="prim-kind-card" onClick=${() => setView({ page: 'kind', kind })}>
                <div class="prim-kind-card-icon prim-kind-${kind}">
                  <${KindIcon} kind=${kind} size=${22} />
                </div>
                <div class="prim-kind-card-body">
                  <div class="prim-kind-card-name">${meta.label}</div>
                  <div class="prim-kind-card-desc">${meta.desc}</div>
                </div>
                <div class="prim-kind-card-count">
                  <span class="prim-kind-count-num">${count}</span>
                  ${count > 0 && enabledCount < count && html`
                    <span class="prim-kind-count-detail">${enabledCount} enabled</span>
                  `}
                </div>
              </button>
            `;
          })}
        </div>
        <div class="registry-teaser">
          <div class="registry-teaser-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="2" y1="12" x2="22" y2="12"/>
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
            </svg>
          </div>
          <div class="registry-teaser-body">
            <div class="registry-teaser-title">Ralphify Registry</div>
            <div class="registry-teaser-desc">Browse and install community prompts, checks, and more from the official Ralphify Registry.</div>
          </div>
          <span class="registry-teaser-badge">Coming Soon</span>
        </div>
      </div>
    `;
  }

  const meta = KINDS_META[view.kind];
  const items = grouped[view.kind] || [];

  if (view.page === 'edit') {
    const prim = items.find(p => p.name === view.name);
    if (!prim) { setView({ page: 'kind', kind: view.kind }); return null; }
    return html`<${PrimEditForm}
      primitive=${prim} kind=${view.kind} meta=${meta}
      onBack=${() => setView({ page: 'kind', kind: view.kind })}
      onSaved=${() => { loadPrimitives(); setView({ page: 'kind', kind: view.kind }); }}
    />`;
  }

  if (view.page === 'create') {
    return html`<${PrimCreateForm}
      kind=${view.kind} meta=${meta}
      onBack=${() => setView({ page: 'kind', kind: view.kind })}
      onCreated=${() => { loadPrimitives(); setView({ page: 'kind', kind: view.kind }); }}
    />`;
  }

  // Kind list view
  return html`
    <div class="prim-kind-view">
      <div class="prim-kind-header">
        <button class="prim-back-btn" onClick=${() => setView({ page: 'overview' })}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 12H5"/><polyline points="12 19 5 12 12 5"/>
          </svg>
          All primitives
        </button>
        <div class="prim-kind-title-row">
          <div class="prim-kind-title-icon prim-kind-${view.kind}">
            <${KindIcon} kind=${view.kind} size=${20} />
          </div>
          <h2>${meta.label}</h2>
          <span class="prim-kind-count-badge">${items.length}</span>
          <div style="flex: 1"></div>
          <button class="btn btn-primary btn-sm" onClick=${() => setView({ page: 'create', kind: view.kind })}>
            + Create New
          </button>
        </div>
        <div class="prim-kind-desc">${meta.desc}</div>
      </div>
      ${items.length === 0 && html`
        <div class="prim-empty">
          <div class="prim-empty-icon prim-kind-${view.kind}">
            <${KindIcon} kind=${view.kind} size=${32} />
          </div>
          <div class="prim-empty-text">No ${meta.label.toLowerCase()} yet</div>
          <div class="prim-empty-hint">Create your first ${meta.label.toLowerCase().replace(/s$/, '')} to get started.</div>
          <button class="btn btn-primary" onClick=${() => setView({ page: 'create', kind: view.kind })}>
            + Create ${meta.label.replace(/s$/, '')}
          </button>
        </div>
      `}
      ${items.length > 0 && html`
        <div class="prim-list">
          ${items.map(p => {
            const desc = p.frontmatter?.description;
            const cmd = p.frontmatter?.command;
            return html`
              <div key=${p.name} class="prim-item" onClick=${() => setView({ page: 'edit', kind: view.kind, name: p.name })}>
                <div class="prim-item-dot ${p.enabled ? 'enabled' : 'disabled'}"></div>
                <div class="prim-item-info">
                  <div class="prim-item-name">${p.name}</div>
                  ${desc && html`
                    <div class="prim-item-desc">${desc}</div>
                  `}
                  ${!desc && cmd && html`
                    <div class="prim-item-cmd"><code>${cmd}</code></div>
                  `}
                </div>
                ${cmd && html`
                  <div class="prim-item-cmd-badge" title="Command">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>
                    </svg>
                  </div>
                `}
                ${view.kind === 'prompts' && p.enabled && html`
                  <button class="prim-item-run-btn" title="Run with this prompt" onClick=${(e) => {
                    e.stopPropagation();
                    startRunWithPrompt(p.name);
                  }}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                      <polygon points="5 3 19 12 5 21 5 3"/>
                    </svg>
                    Run
                  </button>
                `}
                <div class="prim-item-badge ${p.enabled ? 'enabled' : 'disabled'}">
                  ${p.enabled ? 'Enabled' : 'Disabled'}
                </div>
                <svg class="prim-item-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                  <polyline points="9 18 15 12 9 6"/>
                </svg>
              </div>
            `;
          })}
        </div>
      `}
    </div>
  `;
}

function PrimEditForm({ primitive, kind, meta, onBack, onSaved }) {
  const [content, setContent] = useState(primitive.content);
  const [description, setDescription] = useState(primitive.frontmatter?.description || '');
  const [enabled, setEnabled] = useState(primitive.enabled);
  const [command, setCommand] = useState(primitive.frontmatter?.command || '');
  const [timeoutVal, setTimeoutVal] = useState(
    primitive.frontmatter?.timeout != null ? String(primitive.frontmatter.timeout) : ''
  );
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const hasCommand = kind === 'checks' || kind === 'contexts';
  const isCheck = kind === 'checks';

  const hasChanges = content !== primitive.content ||
    description !== (primitive.frontmatter?.description || '') ||
    enabled !== primitive.enabled ||
    (hasCommand && command !== (primitive.frontmatter?.command || '')) ||
    (hasCommand && timeoutVal !== (primitive.frontmatter?.timeout != null ? String(primitive.frontmatter.timeout) : ''));

  // Cmd+S / Ctrl+S to save
  const saveRef = useRef(null);
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        saveRef.current?.();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  async function handleSave() {
    setSaving(true);
    try {
      const fm = { ...primitive.frontmatter, description, enabled };
      if (hasCommand) {
        if (command.trim()) fm.command = command.trim();
        else delete fm.command;
        if (timeoutVal.trim()) fm.timeout = parseFloat(timeoutVal);
        else delete fm.timeout;
      }
      await api('PUT', `/projects/${btoa('.')}/primitives/${kind}/${primitive.name}`, {
        content, frontmatter: fm,
      });
      showToast('Changes saved', 'success');
      onSaved();
    } catch (e) {
      showToast(e.message || 'Failed to save changes');
    }
    setSaving(false);
  }
  // Keep ref in sync so Cmd+S always calls the latest handleSave (with current form state)
  saveRef.current = hasChanges && !saving ? handleSave : null;

  async function handleDelete() {
    if (!confirm(`Delete "${primitive.name}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await api('DELETE', `/projects/${btoa('.')}/primitives/${kind}/${primitive.name}`);
      showToast(`Deleted "${primitive.name}"`, 'info');
      onSaved();
    } catch (e) {
      showToast(e.message || 'Failed to delete');
    }
    setDeleting(false);
  }

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await api('POST', `/projects/${btoa('.')}/primitives/checks/${primitive.name}/test`);
      setTestResult(result);
    } catch (e) {
      setTestResult({ passed: false, exit_code: -1, output: e.message || 'Test failed', timed_out: false, duration: 0 });
    }
    setTesting(false);
  }

  return html`
    <div class="prim-editor">
      <div class="prim-editor-header">
        <button class="prim-back-btn" onClick=${onBack}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 12H5"/><polyline points="12 19 5 12 12 5"/>
          </svg>
          ${meta.label}
        </button>
        <div class="prim-editor-title-row">
          <div class="prim-kind-title-icon prim-kind-${kind}">
            <${KindIcon} kind=${kind} size=${18} />
          </div>
          <h2>${primitive.name}</h2>
          <div style="flex: 1"></div>
          ${kind === 'prompts' && primitive.enabled && html`
            <button class="btn btn-sm prim-run-prompt-btn" onClick=${() => startRunWithPrompt(primitive.name)}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
              Run this prompt
            </button>
          `}
          ${isCheck && html`
            <button class="btn btn-sm check-test-btn ${testing ? 'testing' : ''}" onClick=${handleTest} disabled=${testing || !command.trim()}>
              ${testing ? html`
                <div class="btn-spinner"></div>
                Running...
              ` : html`
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                  <polygon points="5 3 19 12 5 21 5 3"/>
                </svg>
                Test
              `}
            </button>
          `}
        </div>
      </div>
      <div class="prim-editor-body">
        <div class="prim-editor-fields">
          <div class="prim-field-row">
            <div class="form-group" style="flex: 1; margin-bottom: 0">
              <label class="form-label">Description</label>
              <input class="form-input" type="text" value=${description}
                     onInput=${(e) => setDescription(e.target.value)}
                     placeholder="Brief description of this ${meta.label.toLowerCase().replace(/s$/, '')}" />
            </div>
            <div class="prim-enabled-field">
              <label class="form-label">Enabled</label>
              <button class="prim-toggle-btn ${enabled ? 'enabled' : ''}"
                      onClick=${() => setEnabled(!enabled)}>
                <span class="prim-toggle-knob"></span>
              </button>
            </div>
          </div>
          ${hasCommand && html`
            <div class="prim-field-row" style="margin-top: 12px">
              <div class="form-group" style="flex: 1; margin-bottom: 0">
                <label class="form-label">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: -1px; margin-right: 4px">
                    <polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>
                  </svg>
                  Command
                </label>
                <input class="form-input mono" type="text" value=${command}
                       onInput=${(e) => setCommand(e.target.value)}
                       placeholder="e.g. uv run pytest" />
              </div>
              <div class="form-group" style="width: 120px; margin-bottom: 0">
                <label class="form-label">Timeout (s)</label>
                <input class="form-input" type="number" value=${timeoutVal}
                       onInput=${(e) => setTimeoutVal(e.target.value)}
                       placeholder="none" />
              </div>
            </div>
          `}
        </div>
        <div class="form-group" style="margin-bottom: 0">
          <label class="form-label">Content</label>
          <textarea class="prim-content-textarea"
                    value=${content}
                    onInput=${(e) => setContent(e.target.value)}
                    rows=${hasCommand ? '8' : '14'}
                    placeholder="Write the content here..."></textarea>
        </div>
        ${testResult && html`
          <div class="check-test-result ${testResult.passed ? 'passed' : 'failed'}">
            <div class="check-test-result-header">
              <div class="check-test-result-status">
                ${testResult.passed ? html`
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                  Passed
                ` : testResult.timed_out ? html`
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
                  </svg>
                  Timed out
                ` : html`
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                    <path d="M18 6L6 18"/><path d="M6 6l12 12"/>
                  </svg>
                  Failed (exit ${testResult.exit_code})
                `}
              </div>
              <div class="check-test-result-meta">
                ${testResult.duration > 0 ? `${testResult.duration}s` : ''}
              </div>
              <button class="check-test-dismiss" onClick=${() => setTestResult(null)} title="Dismiss">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                  <path d="M18 6L6 18"/><path d="M6 6l12 12"/>
                </svg>
              </button>
            </div>
            ${testResult.output && testResult.output.trim() && html`
              <pre class="check-test-output">${testResult.output.trim()}</pre>
            `}
          </div>
        `}
      </div>
      <div class="prim-editor-actions">
        <button class="btn btn-danger-outline" onClick=${handleDelete} disabled=${deleting}>
          ${deleting ? 'Deleting...' : 'Delete'}
        </button>
        <div style="flex: 1"></div>
        <button class="btn" onClick=${onBack}>Cancel</button>
        <button class="btn btn-primary" onClick=${handleSave} disabled=${!hasChanges || saving}>
          ${saving ? 'Saving...' : html`Save Changes <kbd class="btn-kbd">${navigator.platform?.includes('Mac') ? '\u2318' : 'Ctrl'}S</kbd>`}
        </button>
      </div>
    </div>
  `;
}

function PrimCreateForm({ kind, meta, onBack, onCreated }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [content, setContent] = useState('');
  const [command, setCommand] = useState('');
  const [timeoutVal, setTimeoutVal] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState(null);

  const hasCommand = kind === 'checks' || kind === 'contexts';
  const canCreate = name.trim().length > 0 && (!hasCommand || command.trim().length > 0);

  // Cmd+S / Ctrl+S to create
  const createRef = useRef(null);
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        createRef.current?.();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  async function handleCreate() {
    setCreating(true);
    setError(null);
    try {
      const fm = { name: name.trim() };
      if (description.trim()) fm.description = description.trim();
      if (hasCommand && command.trim()) fm.command = command.trim();
      if (hasCommand && timeoutVal.trim()) fm.timeout = parseFloat(timeoutVal);
      await api('POST', `/projects/${btoa('.')}/primitives/${kind}`, {
        content, frontmatter: fm,
      });
      showToast(`Created "${name.trim()}"`, 'success');
      onCreated();
    } catch (e) {
      const msg = e.message.includes('409') ? 'A primitive with that name already exists.' : (e.message || 'Failed to create primitive.');
      setError(msg);
    }
    setCreating(false);
  }
  createRef.current = canCreate && !creating ? handleCreate : null;

  return html`
    <div class="prim-editor">
      <div class="prim-editor-header">
        <button class="prim-back-btn" onClick=${onBack}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M19 12H5"/><polyline points="12 19 5 12 12 5"/>
          </svg>
          ${meta.label}
        </button>
        <div class="prim-editor-title-row">
          <div class="prim-kind-title-icon prim-kind-${kind}">
            <${KindIcon} kind=${kind} size=${18} />
          </div>
          <h2>New ${meta.label.replace(/s$/, '')}</h2>
        </div>
      </div>
      <div class="prim-editor-body">
        <div class="prim-editor-fields">
          <div class="form-group">
            <label class="form-label">Name</label>
            <input class="form-input" type="text" value=${name}
                   onInput=${(e) => setName(e.target.value)}
                   placeholder="e.g. my-${kind.replace(/s$/, '')}" />
          </div>
          <div class="form-group">
            <label class="form-label">Description</label>
            <input class="form-input" type="text" value=${description}
                   onInput=${(e) => setDescription(e.target.value)}
                   placeholder="Brief description (optional)" />
          </div>
          ${hasCommand && html`
            <div class="prim-field-row">
              <div class="form-group" style="flex: 1; margin-bottom: 0">
                <label class="form-label">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: -1px; margin-right: 4px">
                    <polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>
                  </svg>
                  Command
                </label>
                <input class="form-input mono" type="text" value=${command}
                       onInput=${(e) => setCommand(e.target.value)}
                       placeholder="e.g. uv run pytest" />
              </div>
              <div class="form-group" style="width: 120px; margin-bottom: 0">
                <label class="form-label">Timeout (s)</label>
                <input class="form-input" type="number" value=${timeoutVal}
                       onInput=${(e) => setTimeoutVal(e.target.value)}
                       placeholder="60" />
              </div>
            </div>
          `}
        </div>
        <div class="form-group" style="margin-bottom: 0">
          <label class="form-label">Content</label>
          <textarea class="prim-content-textarea"
                    value=${content}
                    onInput=${(e) => setContent(e.target.value)}
                    rows=${hasCommand ? '8' : '14'}
                    placeholder="Write the content here..."></textarea>
        </div>
        ${error && html`<div class="prim-error">${error}</div>`}
      </div>
      <div class="prim-editor-actions">
        <div style="flex: 1"></div>
        <button class="btn" onClick=${onBack}>Cancel</button>
        <button class="btn btn-primary" onClick=${handleCreate} disabled=${!canCreate || creating}>
          ${creating ? 'Creating...' : html`Create ${meta.label.replace(/s$/, '')} <kbd class="btn-kbd">${navigator.platform?.includes('Mac') ? '\u2318' : 'Ctrl'}S</kbd>`}
        </button>
      </div>
    </div>
  `;
}

// ── History view ───────────────────────────────────────────────────

function HistoryView() {
  const completedRuns = runs.value.filter(r => ['completed', 'stopped', 'failed'].includes(r.status));

  if (completedRuns.length === 0) {
    return html`
      <div class="history-empty">
        <div class="history-empty-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
            <g stroke="url(#hig)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </g>
            <defs>
              <linearGradient id="hig" x1="0" y1="0" x2="24" y2="24">
                <stop stop-color="#8B6CF0"/>
                <stop offset="1" stop-color="#E87B4A"/>
              </linearGradient>
            </defs>
          </svg>
        </div>
        <div class="history-empty-title">No completed runs yet</div>
        <div class="history-empty-hint">
          Completed, stopped, and failed runs will appear here so you can review past results.
        </div>
        <button class="btn btn-primary" onClick=${() => showNewRunModal.value = true}>
          + Start Your First Run
        </button>
      </div>
    `;
  }

  return html`
    <div>
      <div class="history-view-header">
        <h2>Run History</h2>
        <p>${completedRuns.length} run${completedRuns.length !== 1 ? 's' : ''}</p>
      </div>
      <div class="history-grid">
        ${completedRuns.map(r => {
          const total = r.completed + r.failed;
          const passRate = total > 0 ? Math.round((r.completed / total) * 100) : 0;
          const shortId = r.run_id.length > 8 ? r.run_id.slice(0, 8) : r.run_id;
          const displayTitle = r.prompt_name || 'Ad-hoc run';
          const rateColor = passRate >= 80 ? 'var(--green)' : passRate >= 50 ? 'var(--yellow)' : 'var(--red)';

          const statusIcon = r.status === 'completed'
            ? html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`
            : r.status === 'failed'
            ? html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18"/><path d="M6 6l12 12"/></svg>`
            : html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`;

          return html`
            <div key=${r.run_id} class="history-card" onClick=${() => { selectRun(r.run_id); activeTab.value = 'runs'; }}>
              <div class="history-card-status-icon ${r.status}">
                ${statusIcon}
              </div>
              <div class="history-card-body">
                <div class="history-card-title">${displayTitle}</div>
                <div class="history-card-meta">
                  <span class="history-card-meta-id">${shortId}</span>
                  <span>\u00b7</span>
                  <span>${r.iteration || total} iteration${(r.iteration || total) !== 1 ? 's' : ''}</span>
                  ${r.started_at && html`
                    <span>\u00b7</span>
                    <span class="history-card-time" title=${formatDateTime(r.started_at)}>${formatTimeAgo(r.started_at)}</span>
                  `}
                  <span class="history-status-badge ${r.status}">${r.status}</span>
                </div>
              </div>
              <div class="history-card-stats">
                <div class="history-stat">
                  <span class="history-stat-value green">${r.completed}</span>
                  <span class="history-stat-label">Pass</span>
                </div>
                <div class="history-stat">
                  <span class="history-stat-value red">${r.failed}</span>
                  <span class="history-stat-label">Fail</span>
                </div>
              </div>
              <div class="history-card-rate">
                <span class="history-rate-pct" style="color: ${rateColor}">${total > 0 ? `${passRate}%` : '\u2014'}</span>
                <div class="history-rate-bar">
                  <div class="history-rate-bar-fill" style="width: ${passRate}%; background: ${rateColor}"></div>
                </div>
                <span class="history-rate-label">Pass rate</span>
              </div>
              <button class="btn btn-sm history-run-again-btn" onClick=${(e) => {
                e.stopPropagation();
                if (r.prompt_name) {
                  startRunWithPrompt(r.prompt_name);
                } else {
                  showNewRunModal.value = true;
                }
              }} title="Run again with the same prompt">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
                </svg>
              </button>
              <svg class="history-card-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </div>
          `;
        })}
      </div>
    </div>
  `;
}

// ── New Run Modal ──────────────────────────────────────────────────

function NewRunModal() {
  const [promptMode, setPromptMode] = useState('named'); // 'named' | 'adhoc'
  const [selectedPrompt, setSelectedPrompt] = useState(preSelectedPrompt.value);
  const [adhocText, setAdhocText] = useState('');
  const [maxIterations, setMaxIterations] = useState('');
  const [delay, setDelay] = useState('0');
  const [timeout, setTimeout] = useState('');
  const [stopOnError, setStopOnError] = useState(false);
  const [prompts, setPrompts] = useState([]);
  const [promptsLoaded, setPromptsLoaded] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    preSelectedPrompt.value = null;
    const projectDir = btoa('.');
    api('GET', `/projects/${projectDir}/primitives`)
      .then(data => {
        const found = (data || []).filter(p => p.kind === 'prompts' && p.enabled);
        setPrompts(found);
        setPromptsLoaded(true);
      })
      .catch(() => setPromptsLoaded(true));

    const onKey = (e) => { if (e.key === 'Escape') showNewRunModal.value = false; };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  const selectPrompt = (name) => {
    if (selectedPrompt === name) {
      setSelectedPrompt(null);
      setShowPreview(false);
    } else {
      setSelectedPrompt(name);
      setPromptMode('named');
      setShowPreview(false);
    }
  };

  const switchToAdhoc = () => {
    setPromptMode('adhoc');
    setSelectedPrompt(null);
  };

  const canSubmit = promptMode === 'named' ? !!selectedPrompt : adhocText.trim().length > 0;

  const handleSubmit = async () => {
    if (submitting) return;
    setSubmitting(true);
    const body = {
      prompt_name: selectedPrompt || null,
      prompt_text: promptMode === 'adhoc' ? adhocText : null,
      max_iterations: maxIterations ? parseInt(maxIterations) : null,
      delay: parseFloat(delay) || 0,
      timeout: timeout ? parseFloat(timeout) : null,
      stop_on_error: stopOnError,
    };
    try {
      await createRun(body);
    } catch {
      setSubmitting(false);
    }
  };

  const hasPrompts = promptsLoaded && prompts.length > 0;

  return html`
    <div class="modal-overlay" onClick=${(e) => { if (e.target === e.currentTarget) showNewRunModal.value = false; }}>
      <div class="modal modal-new-run">
        <div class="modal-header-row">
          <div class="modal-title">Start a New Run</div>
          <button class="modal-close" onClick=${() => showNewRunModal.value = false}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <path d="M18 6L6 18"/><path d="M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div class="modal-section">
          <div class="modal-section-label">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
            Choose a prompt
          </div>

          ${!promptsLoaded && html`
            <div class="prompt-loading">Loading prompts...</div>
          `}

          ${hasPrompts && html`
            <div class="prompt-card-grid">
              ${prompts.map(p => html`
                <button key=${p.name}
                        class="prompt-card ${selectedPrompt === p.name ? 'selected' : ''}"
                        onClick=${() => selectPrompt(p.name)}>
                  <div class="prompt-card-icon">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                      <polyline points="14 2 14 8 20 8"/>
                    </svg>
                  </div>
                  <div class="prompt-card-body">
                    <span class="prompt-card-name">${p.name}</span>
                    ${(p.frontmatter?.description || p.description) && html`
                      <span class="prompt-card-desc">${p.frontmatter?.description || p.description}</span>
                    `}
                  </div>
                  ${selectedPrompt === p.name && html`
                    <div class="prompt-card-check">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20 6 9 17 4 12"/>
                      </svg>
                    </div>
                  `}
                </button>
              `)}
            </div>
          `}

          ${promptsLoaded && prompts.length === 0 && promptMode === 'named' && html`
            <div class="prompt-empty-hint">
              No saved prompts yet. Write an ad-hoc prompt below, or create prompts in <code>.ralph/prompts/</code>.
            </div>
          `}

          ${selectedPrompt && (() => {
            const selectedP = prompts.find(p => p.name === selectedPrompt);
            const previewContent = selectedP?.content || '';
            if (!previewContent) return null;
            return html`
              <button class="prompt-preview-toggle" onClick=${() => setShowPreview(!showPreview)}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                     style="transform: rotate(${showPreview ? '90deg' : '0deg'}); transition: transform 0.15s ease">
                  <polyline points="9 18 15 12 9 6"/>
                </svg>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
                Preview prompt
              </button>
              ${showPreview && html`
                <div class="prompt-preview-panel">
                  <pre class="prompt-preview-content">${previewContent}</pre>
                </div>
              `}
            `;
          })()}
        </div>

        <div class="modal-divider">
          <span class="modal-divider-text" onClick=${switchToAdhoc}>or write an ad-hoc prompt</span>
        </div>

        <div class="modal-section">
          ${promptMode === 'adhoc' && html`
            <textarea class="adhoc-textarea"
                      value=${adhocText}
                      onInput=${(e) => setAdhocText(e.target.value)}
                      placeholder="Describe what you want the agent to do..."
                      rows="4"></textarea>
          `}
          ${promptMode === 'named' && selectedPrompt && html`
            <div class="prompt-selected-banner">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              Using prompt: <strong>${selectedPrompt}</strong>
            </div>
          `}
        </div>

        <div class="modal-settings-toggle" onClick=${() => setShowSettings(!showSettings)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
               style="transform: rotate(${showSettings ? '90deg' : '0deg'}); transition: transform 0.15s ease">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
          Settings
          ${(maxIterations || timeout || delay !== '0' || stopOnError) && html`
            <span class="settings-badge">customised</span>
          `}
        </div>

        ${showSettings && html`
          <div class="modal-settings">
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">Iterations</label>
                <input class="form-input" type="number" value=${maxIterations}
                       onInput=${(e) => setMaxIterations(e.target.value)} placeholder="unlimited" />
              </div>
              <div class="form-group">
                <label class="form-label">Delay (s)</label>
                <input class="form-input" type="number" value=${delay}
                       onInput=${(e) => setDelay(e.target.value)} />
              </div>
              <div class="form-group">
                <label class="form-label">Timeout (s)</label>
                <input class="form-input" type="number" value=${timeout}
                       onInput=${(e) => setTimeout(e.target.value)} placeholder="none" />
              </div>
            </div>
            <label class="checkbox-row">
              <input type="checkbox" checked=${stopOnError}
                     onChange=${(e) => setStopOnError(e.target.checked)} />
              <span>Stop on first error</span>
            </label>
          </div>
        `}

        <div class="modal-actions">
          <button class="btn" onClick=${() => showNewRunModal.value = false} disabled=${submitting}>Cancel</button>
          <button class="btn btn-primary" disabled=${!canSubmit || submitting} onClick=${handleSubmit}>
            ${submitting ? html`
              <div class="btn-spinner"></div>
              Starting...
            ` : html`
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
              Start Run
            `}
          </button>
        </div>
      </div>
    </div>
  `;
}

// ── Mount ──────────────────────────────────────────────────────────

render(html`<${App} />`, document.getElementById('app'));
