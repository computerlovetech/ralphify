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
const activeTab = signal('timeline');  // timeline | primitives | history

const activeRun = computed(() => runs.value.find(r => r.run_id === activeRunId.value));

// ── WebSocket ──────────────────────────────────────────────────────

let ws = null;
let reconnectTimer = null;

function connectWs() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${protocol}//${location.host}/api/ws`);

  ws.onopen = () => {
    wsConnected.value = true;
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
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
  const { type, run_id, data } = event;

  if (type === 'run_started') {
    const existing = runs.value.find(r => r.run_id === run_id);
    if (!existing) {
      runs.value = [...runs.value, {
        run_id,
        status: 'running',
        iteration: 0,
        completed: 0,
        failed: 0,
        timed_out: 0,
        ...data,
      }];
    }
    if (!activeRunId.value) activeRunId.value = run_id;
  }

  else if (type === 'iteration_started') {
    updateRun(run_id, { iteration: data.iteration, status: 'running' });
    const runIters = iterations.value[run_id] || [];
    iterations.value = {
      ...iterations.value,
      [run_id]: [...runIters, { iteration: data.iteration, status: 'running' }],
    };
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
    const status = data.reason === 'completed' ? 'completed' : 'stopped';
    updateRun(run_id, { status, ...data });
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
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function createRun(config) {
  const run = await api('POST', '/runs', config);
  showNewRunModal.value = false;
  activeRunId.value = run.run_id;
}

async function pauseRun(run_id) { await api('POST', `/runs/${run_id}/pause`); }
async function resumeRun(run_id) { await api('POST', `/runs/${run_id}/resume`); }
async function stopRun(run_id) { await api('POST', `/runs/${run_id}/stop`); }

async function loadRuns() {
  try {
    const data = await api('GET', '/runs');
    runs.value = data;
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
  `;
}

// ── Sidebar ────────────────────────────────────────────────────────

function Sidebar() {
  const active = runs.value.filter(r => ['running', 'paused', 'pending'].includes(r.status));
  const recent = runs.value.filter(r => ['completed', 'stopped', 'failed'].includes(r.status));

  return html`
    <div class="sidebar">
      <div class="sidebar-header">
        <div class="sidebar-header-inner">
          <div class="logo-mark">R</div>
          <h1>Ralphify</h1>
          <span class="version">UI</span>
        </div>
        <button class="sidebar-new-run-btn" onClick=${() => showNewRunModal.value = true}>
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
  const isActive = activeRunId.value === run.run_id;
  const total = run.completed + run.failed;
  const passRate = total > 0 ? (run.completed / total) * 100 : 0;
  const shortId = run.run_id.length > 12 ? run.run_id.slice(0, 12) : run.run_id;

  return html`
    <div class="run-card ${isActive ? 'active' : ''}" onClick=${() => activeRunId.value = run.run_id}>
      <div class="run-badge ${run.status}"></div>
      <div class="run-card-info">
        <div class="run-card-title">${shortId}</div>
        <div class="run-card-meta">
          iter ${run.iteration || 0}${total > 0 ? ` · ${Math.round(passRate)}% pass` : ` · ${run.status}`}
        </div>
      </div>
      ${run.prompt_name && html`
        <span class="run-card-tag">${run.prompt_name}</span>
      `}
      ${total > 0 && html`
        <div class="run-card-bar">
          <div class="run-card-bar-fill ${passRate >= 50 ? 'pass' : 'fail'}" style="width: ${passRate}%"></div>
        </div>
      `}
    </div>
  `;
}

// ── Main area ──────────────────────────────────────────────────────

function Main() {
  const run = activeRun.value;

  return html`
    <div class="main">
      <${ControlsBar} run=${run} />
      <div class="tabs">
        <div class="tab ${activeTab.value === 'timeline' ? 'active' : ''}"
             onClick=${() => activeTab.value = 'timeline'}>Timeline</div>
        <div class="tab ${activeTab.value === 'primitives' ? 'active' : ''}"
             onClick=${() => activeTab.value = 'primitives'}>Primitives</div>
        <div class="tab ${activeTab.value === 'history' ? 'active' : ''}"
             onClick=${() => activeTab.value = 'history'}>History</div>
      </div>
      <div class="content">
        ${!run && html`<${EmptyState} />`}
        ${run && activeTab.value === 'timeline' && html`<${TimelineView} run=${run} />`}
        ${run && activeTab.value === 'primitives' && html`<${PrimitivesView} />`}
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
        <div class="step-card">
          <div class="step-number">1</div>
          <div class="step-title">Configure</div>
          <div class="step-desc">Set up checks and a prompt in your project</div>
        </div>
        <div class="step-card">
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
      <button class="btn btn-primary" onClick=${() => showNewRunModal.value = true}>New Run</button>
      ${run && html`<${RunControls} run=${run} />`}
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

  return html`
    <div class="controls-separator"></div>
    ${isRunning && html`
      <button class="btn" onClick=${() => pauseRun(run.run_id)}>Pause</button>
    `}
    ${isPaused && html`
      <button class="btn" onClick=${() => resumeRun(run.run_id)}>Resume</button>
    `}
    ${(isRunning || isPaused) && html`
      <button class="btn btn-danger" onClick=${() => stopRun(run.run_id)}>Stop</button>
    `}
    <div class="controls-separator"></div>
    <span class="controls-label">Iter</span>
    <span class="controls-value">${run.iteration || 0}</span>
    <span class="controls-label">Pass</span>
    <span class="controls-value" style="color: var(--green)">${run.completed}</span>
    <span class="controls-label">Fail</span>
    <span class="controls-value" style="color: var(--red)">${run.failed}</span>
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
    : (run.status === 'completed'
        ? `Run completed with ${passRate}% pass rate across ${total} iterations.`
        : `Run ${run.status}. ${total} iterations completed.`);

  return html`
    <div class="run-overview">
      <div class="run-overview-header">
        <div class="run-overview-title">
          <h2>${run.run_id}</h2>
          <span class="run-status-badge ${run.status}">${run.status}</span>
          ${run.prompt_name && html`
            <span class="run-prompt-tag">${run.prompt_name}</span>
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
    <${Timeline} iterations=${runIters} selectedIteration=${selectedIter} />
    ${selected && html`<${IterationPanel} iteration=${selected} />`}
    ${Object.keys(health).length > 0 && html`<${CheckHealthPanel} health=${health} />`}
  `;
}

function Timeline({ iterations: iters, selectedIteration }) {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
    }
  }, [iters.length]);

  return html`
    <div class="timeline" ref=${scrollRef}>
      ${iters.length === 0 && html`
        <div style="color: var(--text-secondary); font-size: 13px; padding: 4px">
          Waiting for iterations...
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
                      it.status === 'timeout' ? 'timeout' : '';

  return html`
    <div class="iteration-panel">
      <div class="iteration-header">
        <span class="iteration-title">Iteration ${it.iteration}</span>
        <span class="iteration-status ${statusClass}">
          ${it.detail || it.status}
        </span>
      </div>
      <div class="iteration-body">
        ${it.checks && it.checks.length > 0 && html`
          <div class="check-results">
            <div style="font-weight: 600; font-size: 13px; margin-bottom: 8px">Checks</div>
            ${it.checks.map(c => html`
              <div class="check-result" key=${c.name}>
                <span class="check-icon ${c.passed ? 'pass' : c.timed_out ? 'timeout' : 'fail'}">
                  ${c.passed ? '\u2713' : c.timed_out ? '\u23f1' : '\u2717'}
                </span>
                <span class="check-name">${c.name}</span>
                ${!c.passed && html`
                  <span class="check-detail">exit ${c.exit_code}</span>
                `}
              </div>
            `)}
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

// ── Primitives view ────────────────────────────────────────────────

function PrimitivesView() {
  const [primitives, setPrimitives] = useState(null);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadPrimitives();
  }, []);

  async function loadPrimitives() {
    try {
      const projectDir = btoa('.');
      const data = await api('GET', `/projects/${projectDir}/primitives`);
      setPrimitives(data);
    } catch (e) {
      setPrimitives([]);
    }
    setLoading(false);
  }

  if (loading) return html`<div style="color: var(--text-secondary); padding: 20px">Loading primitives...</div>`;
  if (!primitives || primitives.length === 0) {
    return html`<div style="color: var(--text-secondary); padding: 20px">No primitives found. Use "ralph new" to create some.</div>`;
  }

  const grouped = {};
  for (const p of primitives) {
    if (!grouped[p.kind]) grouped[p.kind] = [];
    grouped[p.kind].push(p);
  }

  return html`
    <div class="primitive-browser">
      <div class="primitive-tree">
        ${Object.entries(grouped).map(([kind, items]) => html`
          <div key=${kind}>
            <div class="primitive-group-title">${kind}</div>
            ${items.map(p => html`
              <div key=${p.name}
                   class="primitive-item ${selected?.name === p.name && selected?.kind === p.kind ? 'active' : ''}"
                   onClick=${() => setSelected(p)}>
                <div class="primitive-toggle ${p.enabled ? 'enabled' : ''}"></div>
                <span>${p.name}</span>
              </div>
            `)}
          </div>
        `)}
      </div>
      ${selected && html`
        <div class="primitive-editor">
          <div style="font-weight: 600; margin-bottom: 8px">${selected.kind}/${selected.name}</div>
          <textarea value=${selected.content} readonly></textarea>
        </div>
      `}
    </div>
  `;
}

// ── History view ───────────────────────────────────────────────────

function HistoryView() {
  const completedRuns = runs.value.filter(r => ['completed', 'stopped', 'failed'].includes(r.status));

  return html`
    <div class="history-panel">
      <div class="history-header">Run History</div>
      ${completedRuns.length === 0 && html`
        <div style="padding: 16px; color: var(--text-muted); font-size: 12px">No completed runs yet.</div>
      `}
      ${completedRuns.map(r => html`
        <div key=${r.run_id} class="run-summary-card" onClick=${() => { activeRunId.value = r.run_id; activeTab.value = 'timeline'; }}>
          <div class="run-badge ${r.status}"></div>
          <div>
            <div class="run-summary-id">${r.run_id}</div>
            <div class="run-summary-stats">
              ${r.completed + r.failed} iterations \u00b7 ${r.completed} passed \u00b7 ${r.failed} failed
            </div>
          </div>
          <div class="run-summary-time">${r.status}</div>
        </div>
      `)}
    </div>
  `;
}

// ── New Run Modal ──────────────────────────────────────────────────

function NewRunModal() {
  const [config, setConfig] = useState({
    command: 'claude',
    args: ['-p', '--dangerously-skip-permissions'],
    prompt_file: 'PROMPT.md',
    prompt_text: '',
    prompt_name: null,
    max_iterations: '',
    delay: '0',
    timeout: '',
    stop_on_error: false,
    project_dir: '.',
  });
  const [prompts, setPrompts] = useState([]);
  const [promptsLoaded, setPromptsLoaded] = useState(false);

  useEffect(() => {
    const projectDir = btoa(config.project_dir);
    api('GET', `/projects/${projectDir}/primitives`)
      .then(data => {
        const found = (data || []).filter(p => p.kind === 'prompts' && p.enabled);
        setPrompts(found);
        setPromptsLoaded(true);
      })
      .catch(() => setPromptsLoaded(true));
  }, []);

  const updateField = (field) => (e) => {
    setConfig({ ...config, [field]: e.target.type === 'checkbox' ? e.target.checked : e.target.value });
  };

  const selectPrompt = (name) => {
    if (config.prompt_name === name) {
      // Deselect — go back to default prompt file
      setConfig({ ...config, prompt_name: null, prompt_file: 'PROMPT.md' });
    } else {
      setConfig({ ...config, prompt_name: name, prompt_file: '' });
    }
  };

  const handleSubmit = () => {
    const body = {
      command: config.command,
      args: config.args,
      prompt_file: config.prompt_name ? '' : config.prompt_file,
      prompt_name: config.prompt_name || null,
      prompt_text: config.prompt_text || null,
      max_iterations: config.max_iterations ? parseInt(config.max_iterations) : null,
      delay: parseFloat(config.delay) || 0,
      timeout: config.timeout ? parseFloat(config.timeout) : null,
      stop_on_error: config.stop_on_error,
      project_dir: config.project_dir,
    };
    createRun(body);
  };

  return html`
    <div class="modal-overlay" onClick=${(e) => { if (e.target === e.currentTarget) showNewRunModal.value = false; }}>
      <div class="modal">
        <div class="modal-title">New Run</div>
        <div class="form-group">
          <label class="form-label">Command</label>
          <input class="form-input" value=${config.command} onInput=${updateField('command')} />
        </div>
        <div class="form-group">
          <label class="form-label">Prompt</label>
          ${promptsLoaded && prompts.length > 0 && html`
            <div class="prompt-picker">
              ${prompts.map(p => html`
                <button key=${p.name}
                        class="prompt-chip ${config.prompt_name === p.name ? 'selected' : ''}"
                        onClick=${() => selectPrompt(p.name)}
                        title=${p.description || p.name}>
                  <span class="prompt-chip-name">${p.name}</span>
                  ${p.description && html`<span class="prompt-chip-desc">${p.description}</span>`}
                </button>
              `)}
            </div>
          `}
          ${!config.prompt_name && html`
            <input class="form-input" value=${config.prompt_file}
                   onInput=${updateField('prompt_file')}
                   placeholder="PROMPT.md" />
          `}
          ${config.prompt_name && html`
            <div class="prompt-selected-note">
              Using prompt: <strong>${config.prompt_name}</strong>
            </div>
          `}
        </div>
        <div class="form-group">
          <label class="form-label">Project Directory</label>
          <input class="form-input" value=${config.project_dir} onInput=${updateField('project_dir')} />
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Max Iterations</label>
            <input class="form-input" type="number" value=${config.max_iterations}
                   onInput=${updateField('max_iterations')} placeholder="unlimited" />
          </div>
          <div class="form-group">
            <label class="form-label">Delay (s)</label>
            <input class="form-input" type="number" value=${config.delay}
                   onInput=${updateField('delay')} />
          </div>
          <div class="form-group">
            <label class="form-label">Timeout (s)</label>
            <input class="form-input" type="number" value=${config.timeout}
                   onInput=${updateField('timeout')} placeholder="none" />
          </div>
        </div>
        <div class="form-group" style="display: flex; align-items: center; gap: 8px">
          <input type="checkbox" checked=${config.stop_on_error}
                 onChange=${updateField('stop_on_error')} />
          <label class="form-label" style="margin: 0">Stop on error</label>
        </div>
        <div class="modal-actions">
          <button class="btn" onClick=${() => showNewRunModal.value = false}>Cancel</button>
          <button class="btn btn-primary" onClick=${handleSubmit}>Start Run</button>
        </div>
      </div>
    </div>
  `;
}

// ── Mount ──────────────────────────────────────────────────────────

render(html`<${App} />`, document.getElementById('app'));
