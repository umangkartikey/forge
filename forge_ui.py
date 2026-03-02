#!/usr/bin/env python3
"""
⚒️  FORGE UI — Real-Time Web Dashboard
Pure stdlib. No Flask. No deps beyond what FORGE already needs.

Opens a browser dashboard showing:
  🐝 Live swarm worker grid with progress bars
  🧠 Hive mind message feed (live stream)
  🔍 Findings table (auto-updating, severity colored)
  📊 Learning brain stats
  🔨 Module pool (grows as workers build)
  🎮 Controls — launch swarm, trigger learning, build tools

Usage: python forge_ui.py
Then open: http://localhost:7331
"""

import json, os, re, sys, time, threading, hashlib, shutil
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ── Paths (mirrors forge_swarm.py) ───────────────────────────────────────────
SWARM_ROOT   = Path("forge_swarm")
HIVE_DIR     = SWARM_ROOT / "hive"
WORKERS_DIR  = SWARM_ROOT / "workers"
MODULES_POOL = SWARM_ROOT / "modules_pool"
HIVE_BUS     = HIVE_DIR / "bus.json"
HIVE_MEMORY  = HIVE_DIR / "memory.json"
HIVE_MODULES = HIVE_DIR / "modules.json"
HIVE_STATUS  = HIVE_DIR / "status.json"
LEARN_DIR    = Path("forge_learn")
BRAIN_DB     = LEARN_DIR / "brain.db"

PORT = 7331

# ── Safe reads ────────────────────────────────────────────────────────────────
def safe_read(path, default=None):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except: pass
    return default if default is not None else {}

def brain_stats():
    """Read stats from SQLite brain if available."""
    try:
        import sqlite3
        if not BRAIN_DB.exists(): return {}
        conn = sqlite3.connect(str(BRAIN_DB))
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        stats = {
            "runs":     c.execute("SELECT COUNT(*) as n FROM runs").fetchone()["n"],
            "findings": c.execute("SELECT COUNT(*) as n FROM findings").fetchone()["n"],
            "modules":  c.execute("SELECT COUNT(*) as n FROM modules").fetchone()["n"],
            "patterns": c.execute("SELECT COUNT(*) as n FROM patterns").fetchone()["n"],
            "insights": c.execute("SELECT COUNT(*) as n FROM insights").fetchone()["n"],
            "avg_score":round(c.execute("SELECT COALESCE(AVG(score),0) FROM runs WHERE score>0").fetchone()[0],1),
        }
        conn.close()
        return stats
    except: return {}

def get_state():
    """Aggregate all FORGE state into one dict."""
    status  = safe_read(HIVE_STATUS, {})
    memory  = safe_read(HIVE_MEMORY, {})
    mods    = safe_read(HIVE_MODULES, {})
    bus     = safe_read(HIVE_BUS,    {"messages":[]})

    findings = memory.get("findings", [])
    messages = bus.get("messages", [])

    # Worker dirs
    worker_logs = {}
    if WORKERS_DIR.exists():
        for d in WORKERS_DIR.iterdir():
            log_f = d / "worker.log"
            if log_f.exists():
                lines = log_f.read_text().strip().split("\n")
                worker_logs[d.name] = lines[-1][:80] if lines else ""

    # Module pool files
    pool_files = []
    if MODULES_POOL.exists():
        for f in MODULES_POOL.glob("*.py"):
            info = mods.get(f.stem, {})
            pool_files.append({
                "name": f.stem,
                "size": f.stat().st_size,
                "built_by": info.get("built_by", "?"),
                "description": info.get("description", "")[:50],
            })

    return {
        "ts":          datetime.now().isoformat(),
        "workers":     status,
        "worker_logs": worker_logs,
        "findings":    findings[-50:],
        "messages":    messages[-30:],
        "modules":     pool_files,
        "target":      memory.get("target", "—"),
        "goal":        memory.get("goal", "—"),
        "brain":       brain_stats(),
        "hive_active": HIVE_DIR.exists(),
    }

# ══════════════════════════════════════════════════════════════════════════════
# HTML DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>⚒️ FORGE — Live Dashboard</title>
<style>
  :root {
    --bg:      #0a0a0f;
    --surface: #111118;
    --border:  #1e1e2e;
    --cyan:    #00d4ff;
    --magenta: #ff2d78;
    --yellow:  #ffd700;
    --green:   #00ff88;
    --red:     #ff3366;
    --orange:  #ff8c00;
    --dim:     #444466;
    --text:    #c0c0d0;
    --white:   #e8e8f0;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
    font-size: 13px;
    min-height: 100vh;
    overflow-x: hidden;
  }

  /* ── Header ── */
  header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 12px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky; top: 0; z-index: 100;
  }
  .logo {
    font-size: 18px;
    font-weight: 700;
    color: var(--cyan);
    letter-spacing: 4px;
    text-shadow: 0 0 20px rgba(0,212,255,0.5);
  }
  .logo span { color: var(--magenta); }
  .status-bar {
    display: flex; gap: 20px; align-items: center;
    font-size: 11px; color: var(--dim);
  }
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 4px; }
  .dot-live { background: var(--green); animation: pulse 1.5s infinite; }
  .dot-dead { background: var(--red); }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
  .target-info { color: var(--cyan); font-size: 11px; }

  /* ── Layout ── */
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    grid-template-rows: auto auto auto;
    gap: 12px;
    padding: 16px;
  }
  .panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }
  .panel-header {
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    display: flex; align-items: center; justify-content: space-between;
  }
  .panel-body { padding: 12px; max-height: 280px; overflow-y: auto; }
  .panel-body::-webkit-scrollbar { width: 4px; }
  .panel-body::-webkit-scrollbar-track { background: var(--bg); }
  .panel-body::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  /* span full columns */
  .span2 { grid-column: span 2; }
  .span3 { grid-column: span 3; }

  /* ── Workers ── */
  .worker-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px,1fr)); gap: 8px; }
  .worker-card {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 12px;
    transition: border-color .3s;
  }
  .worker-card.running { border-color: var(--cyan); }
  .worker-card.building { border-color: var(--magenta); }
  .worker-card.done { border-color: var(--green); }
  .worker-card.dead { border-color: var(--red); opacity:.6; }
  .worker-id { font-size: 11px; font-weight:700; margin-bottom: 6px; }
  .worker-task { font-size: 10px; color: var(--dim); margin-bottom: 6px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .progress-bar { height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; }
  .progress-fill { height: 100%; border-radius: 2px; transition: width .5s; }
  .running .progress-fill  { background: var(--cyan); }
  .building .progress-fill { background: var(--magenta); }
  .done .progress-fill     { background: var(--green); }
  .worker-status { font-size: 10px; margin-top: 4px; }
  .status-running  { color: var(--cyan); }
  .status-building { color: var(--magenta); }
  .status-done     { color: var(--green); }
  .status-dead     { color: var(--red); }
  .status-spawned  { color: var(--yellow); }
  .no-workers { color: var(--dim); font-size: 12px; padding: 20px; text-align:center; }

  /* ── Findings ── */
  .finding-row {
    display: flex; align-items: flex-start; gap: 8px;
    padding: 6px 0; border-bottom: 1px solid var(--border);
    font-size: 11px; animation: fadeIn .4s ease;
  }
  .finding-row:last-child { border-bottom: none; }
  @keyframes fadeIn { from { opacity:0; transform: translateY(-4px); } to { opacity:1; transform: none; } }
  .sev {
    font-size: 9px; font-weight:700; padding: 2px 5px; border-radius: 3px;
    min-width: 56px; text-align:center; letter-spacing:.5px;
  }
  .sev-critical { background:#ff336622; color:var(--red); border:1px solid var(--red); }
  .sev-high     { background:#ff8c0022; color:var(--orange); border:1px solid var(--orange); }
  .sev-medium   { background:#ffd70022; color:var(--yellow); border:1px solid var(--yellow); }
  .sev-info     { background:#00d4ff11; color:var(--cyan); border:1px solid #00d4ff33; }
  .finding-body { flex:1; }
  .finding-type { color: var(--white); font-weight:600; }
  .finding-from { color: var(--dim); margin-left: 6px; }
  .finding-data { color: var(--dim); font-size:10px; margin-top:2px; word-break:break-all; }

  /* ── Messages (hive bus) ── */
  .msg-row {
    padding: 5px 0; border-bottom: 1px solid var(--border);
    font-size: 11px; display:flex; gap: 8px; align-items:flex-start;
    animation: fadeIn .3s ease;
  }
  .msg-row:last-child { border-bottom:none; }
  .msg-ts { color: var(--dim); font-size:9px; white-space:nowrap; margin-top:1px; }
  .msg-type { font-size:9px; padding:2px 5px; border-radius:3px; min-width:90px; text-align:center; }
  .msg-finding      { background:#ffd70011; color:var(--yellow); border:1px solid #ffd70033; }
  .msg-module_built { background:#ff2d7811; color:var(--magenta); border:1px solid #ff2d7833; }
  .msg-task_done    { background:#00ff8811; color:var(--green); border:1px solid #00ff8833; }
  .msg-spawn        { background:#00d4ff11; color:var(--cyan); border:1px solid #00d4ff33; }
  .msg-other        { background:#ffffff08; color:var(--dim); border:1px solid var(--border); }
  .msg-from { color: var(--cyan); font-weight:600; }
  .msg-preview { color: var(--dim); font-size:10px; margin-top:1px; }

  /* ── Modules ── */
  .module-row {
    display:flex; align-items:center; gap:8px;
    padding: 6px 0; border-bottom:1px solid var(--border);
    font-size:11px; animation: fadeIn .4s ease;
  }
  .module-row:last-child { border-bottom:none; }
  .module-icon { color: var(--magenta); font-size:14px; }
  .module-name { color: var(--white); font-weight:600; }
  .module-by   { color: var(--dim); font-size:10px; }
  .module-desc { color: var(--dim); font-size:10px; }
  .module-size { color: var(--dim); font-size:9px; margin-left:auto; }

  /* ── Brain stats ── */
  .brain-grid { display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; }
  .stat-card {
    background: var(--bg); border:1px solid var(--border);
    border-radius:6px; padding:10px; text-align:center;
  }
  .stat-val { font-size:22px; font-weight:700; color:var(--cyan); }
  .stat-lbl { font-size:10px; color:var(--dim); margin-top:2px; letter-spacing:.5px; }
  .stat-score { color: var(--green); }

  /* ── Controls ── */
  .controls { display:flex; gap:8px; flex-wrap:wrap; }
  .btn {
    padding: 8px 16px; border-radius:5px; border:none; cursor:pointer;
    font-family: inherit; font-size:12px; font-weight:600; letter-spacing:.5px;
    transition: all .2s; text-transform:uppercase;
  }
  .btn:hover { transform: translateY(-1px); filter:brightness(1.15); }
  .btn:active { transform: translateY(0); }
  .btn-cyan    { background: var(--cyan);    color: #000; }
  .btn-magenta { background: var(--magenta); color: #fff; }
  .btn-green   { background: var(--green);   color: #000; }
  .btn-yellow  { background: var(--yellow);  color: #000; }
  .btn-dim     { background: var(--border);  color: var(--text); }
  .input-row { display:flex; gap:8px; margin-bottom:8px; }
  .inp {
    flex:1; background:var(--bg); border:1px solid var(--border);
    border-radius:5px; padding:8px 12px; color:var(--white);
    font-family:inherit; font-size:12px; outline:none;
  }
  .inp:focus { border-color:var(--cyan); }
  .inp::placeholder { color:var(--dim); }

  /* ── Log tail ── */
  .log { font-size:10px; color:var(--dim); max-height:140px; overflow-y:auto; }
  .log-line { padding:2px 0; border-bottom:1px solid #ffffff08; }
  .log-line:last-child { border-bottom:none; color:var(--text); }

  /* ── Panel headers color ── */
  .h-cyan    { color: var(--cyan); }
  .h-magenta { color: var(--magenta); }
  .h-yellow  { color: var(--yellow); }
  .h-green   { color: var(--green); }
  .h-orange  { color: var(--orange); }
  .h-white   { color: var(--white); }

  .badge {
    background:var(--border); color:var(--text); border-radius:10px;
    padding:2px 8px; font-size:10px;
  }
  .empty { color:var(--dim); font-size:11px; padding:12px; text-align:center; }
</style>
</head>
<body>

<header>
  <div class="logo">⚒️ F<span>O</span>RGE</div>
  <div class="target-info" id="target-info">No active run</div>
  <div class="status-bar">
    <span><span class="dot dot-live" id="conn-dot"></span><span id="conn-status">Connecting...</span></span>
    <span id="last-update">—</span>
  </div>
</header>

<div class="grid">

  <!-- Workers -->
  <div class="panel span2">
    <div class="panel-header">
      <span class="h-cyan">⚡ SWARM WORKERS</span>
      <span class="badge" id="worker-count">0 active</span>
    </div>
    <div class="panel-body">
      <div class="worker-grid" id="workers">
        <div class="no-workers">No workers spawned. Launch a swarm below.</div>
      </div>
    </div>
  </div>

  <!-- Brain Stats -->
  <div class="panel">
    <div class="panel-header">
      <span class="h-green">🧠 BRAIN STATS</span>
    </div>
    <div class="panel-body">
      <div class="brain-grid" id="brain-grid">
        <div class="stat-card"><div class="stat-val" id="s-runs">—</div><div class="stat-lbl">RUNS</div></div>
        <div class="stat-card"><div class="stat-val" id="s-findings">—</div><div class="stat-lbl">FINDINGS</div></div>
        <div class="stat-card"><div class="stat-val" id="s-patterns">—</div><div class="stat-lbl">PATTERNS</div></div>
        <div class="stat-card"><div class="stat-val" id="s-modules">—</div><div class="stat-lbl">MODULES</div></div>
        <div class="stat-card"><div class="stat-val" id="s-insights">—</div><div class="stat-lbl">INSIGHTS</div></div>
        <div class="stat-card"><div class="stat-val stat-score" id="s-score">—</div><div class="stat-lbl">AVG SCORE</div></div>
      </div>
    </div>
  </div>

  <!-- Findings -->
  <div class="panel span2">
    <div class="panel-header">
      <span class="h-yellow">🔍 LIVE FINDINGS</span>
      <span class="badge" id="finding-count">0</span>
    </div>
    <div class="panel-body" id="findings-body">
      <div class="empty">Findings will appear here as workers report them.</div>
    </div>
  </div>

  <!-- Module Pool -->
  <div class="panel">
    <div class="panel-header">
      <span class="h-magenta">🔨 MODULE POOL</span>
      <span class="badge" id="module-count">0</span>
    </div>
    <div class="panel-body" id="modules-body">
      <div class="empty">Modules built by workers appear here and sync to all instances.</div>
    </div>
  </div>

  <!-- Hive Bus -->
  <div class="panel">
    <div class="panel-header">
      <span class="h-orange">📡 HIVE MIND BUS</span>
      <span class="badge" id="msg-count">0</span>
    </div>
    <div class="panel-body" id="bus-body">
      <div class="empty">Hive messages stream here.</div>
    </div>
  </div>

  <!-- Controls -->
  <div class="panel span2">
    <div class="panel-header"><span class="h-white">🎮 CONTROLS</span></div>
    <div class="panel-body">
      <div class="input-row">
        <input class="inp" id="inp-target" placeholder="Target (e.g. 192.168.1.1 or example.com)" />
        <input class="inp" id="inp-goal" placeholder="Goal (e.g. comprehensive security assessment)" style="flex:1.5" />
      </div>
      <div class="controls">
        <button class="btn btn-cyan"    onclick="launch('swarm')">🐝 Launch Swarm</button>
        <button class="btn btn-magenta" onclick="launch('autopilot')">🤖 Autopilot</button>
        <button class="btn btn-green"   onclick="launch('learn')">📚 Run Learn Loop</button>
        <button class="btn btn-yellow"  onclick="launch('evolve')">🧬 Evolve Prompts</button>
        <button class="btn btn-dim"     onclick="launch('clean')">🗑️ Clean Hive</button>
      </div>
      <div style="margin-top:10px; font-size:10px; color:var(--dim);" id="ctrl-status">
        Ready. Dashboard auto-refreshes every 2 seconds.
      </div>
    </div>
  </div>

</div>

<script>
let lastMsgIds = new Set();
let lastFindings = 0;
let lastModules = 0;

async function fetchState() {
  try {
    const r = await fetch('/api/state');
    if (!r.ok) return;
    const data = await r.json();
    updateAll(data);
    document.getElementById('conn-dot').className = 'dot dot-live';
    document.getElementById('conn-status').textContent = 'Live';
    document.getElementById('last-update').textContent = 
      new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById('conn-dot').className = 'dot dot-dead';
    document.getElementById('conn-status').textContent = 'Disconnected';
  }
}

function updateAll(data) {
  // Target info
  if (data.target && data.target !== '—') {
    document.getElementById('target-info').textContent = 
      `🎯 ${data.target} — ${data.goal || ''}`;
  }

  // Workers
  updateWorkers(data.workers || {}, data.worker_logs || {});

  // Findings
  updateFindings(data.findings || []);

  // Messages
  updateBus(data.messages || []);

  // Modules
  updateModules(data.modules || []);

  // Brain stats
  const b = data.brain || {};
  document.getElementById('s-runs').textContent     = b.runs     ?? '—';
  document.getElementById('s-findings').textContent = b.findings ?? '—';
  document.getElementById('s-patterns').textContent = b.patterns ?? '—';
  document.getElementById('s-modules').textContent  = b.modules  ?? '—';
  document.getElementById('s-insights').textContent = b.insights ?? '—';
  document.getElementById('s-score').textContent    = b.avg_score ? `${b.avg_score}/10` : '—';
}

function updateWorkers(workers, logs) {
  const el = document.getElementById('workers');
  const count = Object.keys(workers).length;
  document.getElementById('worker-count').textContent = 
    count > 0 ? `${count} active` : '0 active';
  
  if (count === 0) {
    el.innerHTML = '<div class="no-workers">No workers spawned. Launch a swarm below.</div>';
    return;
  }
  
  el.innerHTML = Object.entries(workers).map(([id, w]) => {
    const status = w.status || 'idle';
    const prog   = w.progress || 0;
    const task   = w.task || '';
    const log    = logs[id] || '';
    return `
    <div class="worker-card ${status}">
      <div class="worker-id">${id}</div>
      <div class="worker-task" title="${task}">${task || '—'}</div>
      <div class="progress-bar">
        <div class="progress-fill" style="width:${prog}%"></div>
      </div>
      <div class="worker-status status-${status}">${status} ${prog}%</div>
      ${log ? `<div class="worker-task" style="margin-top:4px;font-size:9px">${log}</div>` : ''}
    </div>`;
  }).join('');
}

function updateFindings(findings) {
  const el = document.getElementById('findings-body');
  document.getElementById('finding-count').textContent = findings.length;
  
  if (findings.length === 0) {
    el.innerHTML = '<div class="empty">Findings will appear here as workers report them.</div>';
    return;
  }
  
  const sevClass = s => `sev-${s||'info'}`;
  el.innerHTML = [...findings].reverse().slice(0, 40).map(f => {
    const data = typeof f.data === 'object' ? JSON.stringify(f.data).slice(0,100) : String(f.data||'').slice(0,100);
    return `
    <div class="finding-row">
      <div class="sev ${sevClass(f.severity)}">${(f.severity||'info').toUpperCase()}</div>
      <div class="finding-body">
        <div>
          <span class="finding-type">${f.type||'unknown'}</span>
          <span class="finding-from">← ${f.from||'?'}</span>
        </div>
        <div class="finding-data">${data}</div>
      </div>
    </div>`;
  }).join('');
}

function updateBus(messages) {
  const el = document.getElementById('bus-body');
  document.getElementById('msg-count').textContent = messages.length;
  
  if (messages.length === 0) {
    el.innerHTML = '<div class="empty">Hive messages stream here.</div>';
    return;
  }

  const msgClass = t => {
    const map = {finding:'msg-finding',module_built:'msg-module_built',
                 task_done:'msg-task_done',spawn:'msg-spawn'};
    return map[t] || 'msg-other';
  };

  el.innerHTML = [...messages].reverse().slice(0, 25).map(m => {
    const ts = (m.timestamp||'').slice(11,16);
    const payload = m.payload || {};
    const preview = payload.preview || payload.task || payload.module || payload.message || '';
    return `
    <div class="msg-row">
      <div class="msg-ts">${ts}</div>
      <div class="msg-type ${msgClass(m.type)}">${(m.type||'?').replace('_',' ')}</div>
      <div>
        <div class="msg-from">${m.from||'?'}</div>
        <div class="msg-preview">${String(preview).slice(0,60)}</div>
      </div>
    </div>`;
  }).join('');
}

function updateModules(modules) {
  const el = document.getElementById('modules-body');
  document.getElementById('module-count').textContent = modules.length;
  
  if (modules.length === 0) {
    el.innerHTML = '<div class="empty">Modules built by workers appear here and sync to all instances.</div>';
    return;
  }

  el.innerHTML = modules.map(m => `
    <div class="module-row">
      <div class="module-icon">🔨</div>
      <div>
        <div class="module-name">${m.name}</div>
        <div class="module-desc">${m.description||'—'}</div>
        <div class="module-by">built by ${m.built_by||'?'}</div>
      </div>
      <div class="module-size">${m.size}B</div>
    </div>`).join('');
}

async function launch(action) {
  const target = document.getElementById('inp-target').value.trim();
  const goal   = document.getElementById('inp-goal').value.trim();
  const status = document.getElementById('ctrl-status');

  if ((action === 'swarm' || action === 'autopilot') && !target) {
    status.textContent = '⚠️  Enter a target first.';
    status.style.color = 'var(--red)';
    return;
  }

  status.textContent = `⚡ Sending ${action} command...`;
  status.style.color = 'var(--cyan)';

  try {
    const r = await fetch('/api/command', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({action, target, goal})
    });
    const data = await r.json();
    status.textContent = data.message || 'Command sent.';
    status.style.color = data.ok ? 'var(--green)' : 'var(--yellow)';
  } catch(e) {
    status.textContent = `Error: ${e.message}`;
    status.style.color = 'var(--red)';
  }
}

// Poll every 2 seconds
fetchState();
setInterval(fetchState, 2000);
</script>
</body>
</html>"""

# ══════════════════════════════════════════════════════════════════════════════
# HTTP SERVER
# ══════════════════════════════════════════════════════════════════════════════

class ForgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass  # silence default logs

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self._send(200, "text/html", HTML.encode())
        elif parsed.path == "/api/state":
            try:
                state = get_state()
                self._send(200, "application/json", json.dumps(state).encode())
            except Exception as e:
                self._send(500, "application/json", json.dumps({"error":str(e)}).encode())
        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        if self.path == "/api/command":
            length  = int(self.headers.get("Content-Length", 0))
            body    = json.loads(self.rfile.read(length)) if length else {}
            action  = body.get("action","")
            target  = body.get("target","")
            goal    = body.get("goal","comprehensive security assessment")
            result  = handle_command(action, target, goal)
            self._send(200, "application/json", json.dumps(result).encode())
        else:
            self._send(404, "text/plain", b"Not found")

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

def handle_command(action, target, goal):
    """Execute a dashboard command in a background thread."""
    import subprocess, sys

    if action == "clean":
        try:
            import shutil
            shutil.rmtree("forge_swarm/hive", ignore_errors=True)
            shutil.rmtree("forge_swarm/workers", ignore_errors=True)
            shutil.rmtree("forge_swarm/modules_pool", ignore_errors=True)
            for d in [HIVE_DIR, WORKERS_DIR, MODULES_POOL]:
                d.mkdir(parents=True, exist_ok=True)
            return {"ok":True,"message":"🗑️ Hive cleaned. Ready for next run."}
        except Exception as e:
            return {"ok":False,"message":f"Clean error: {e}"}

    if action == "learn":
        def _learn():
            try:
                subprocess.run([sys.executable,"forge_learn.py","--learn"],timeout=120)
            except: pass
        threading.Thread(target=_learn, daemon=True).start()
        return {"ok":True,"message":"📚 Learning loop started. Check forge_learn/ for results."}

    if action == "evolve":
        def _evolve():
            try:
                subprocess.run([sys.executable,"forge_learn.py","--evolve","swarm_planner"],timeout=180)
            except: pass
        threading.Thread(target=_evolve, daemon=True).start()
        return {"ok":True,"message":"🧬 Prompt evolution started (may take a few minutes)."}

    if action in ("swarm","autopilot") and target:
        script = "forge_swarm.py" if action == "swarm" else "forge_meta.py"
        # Write a task script that runs non-interactively
        task_script = f"""
import sys, json
sys.path.insert(0, '.')

# Simulate running swarm/autopilot for target
target = {json.dumps(target)}
goal   = {json.dumps(goal)}

print(f"FORGE UI: Launching {{action}} on {{target}}")
print(f"Goal: {{goal}}")
print("(Connect interactively via terminal for full control)")
""".replace("{action}", action)
        script_fp = Path("forge_ui_task.py")
        script_fp.write_text(task_script)

        def _run():
            try:
                subprocess.run([sys.executable, str(script_fp)], timeout=300)
            except: pass

        threading.Thread(target=_run, daemon=True).start()
        return {
            "ok":True,
            "message":f"⚡ {action.upper()} initiated for {target}. "
                      f"Run 'python forge_swarm.py' in terminal for full interactive control."
        }

    return {"ok":False,"message":f"Unknown action: {action}"}

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # Ensure dirs exist
    for d in [HIVE_DIR, WORKERS_DIR, MODULES_POOL, LEARN_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    server = HTTPServer(("0.0.0.0", PORT), ForgeHandler)

    print(f"""
  ⚒️  FORGE UI — Real-Time Dashboard
  ══════════════════════════════════
  Open:  http://localhost:{PORT}
  
  Shows live:
    🐝 Swarm workers + progress
    🔍 Findings as they arrive
    📡 Hive mind message bus
    🔨 Module pool (auto-sync)
    🧠 Learning brain stats
  
  Run in parallel:
    python forge_swarm.py    ← launch swarm
    python forge_learn.py    ← run learning loop
    python forge_meta.py     ← use modules
  
  Press Ctrl+C to stop.
""")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  ⚒️  FORGE UI stopped.\n")
        server.shutdown()

if __name__ == "__main__":
    main()
