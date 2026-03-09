#!/usr/bin/env python3
"""
FORGE MOBILE — Intelligence in Your Pocket
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FORGE on any phone. No install. Just open the URL.

What it does:
  📸 Take a photo → Sherlock analyzes it instantly
  🌍 GeoSpy locates any image you send
  🕵️  OSINT on any name, domain, or IP
  🎤  Voice commands via phone mic
  🔔  Push alerts from Ghost missions
  📍  Real GPS from your phone
  💬  Chat interface to all FORGE tools
  📊  Live dashboard of all FORGE activity

How it works:
  forge_mobile.py runs a FastAPI server
  Your phone opens http://YOUR_IP:7345
  That's it. Works on iOS, Android, any browser.
  No App Store. No install. Instant.

Usage:
  python forge_mobile.py              # start server
  python forge_mobile.py --port 7345  # custom port
  python forge_mobile.py --qr         # print QR code for easy phone access
  python forge_mobile.py --public     # expose via ngrok (public URL)
"""

import sys, os, re, json, time, base64, hashlib, threading
import urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime

# ── FastAPI ────────────────────────────────────────────────────────────────────
try:
    from fastapi import FastAPI, HTTPException, UploadFile, File, Form
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
    FASTAPI = True
except ImportError:
    FASTAPI = False

# ── AI ─────────────────────────────────────────────────────────────────────────
try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True

    def ai_call(prompt, system="", max_tokens=1500):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or MOBILE_SYSTEM,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text

    def ai_vision(prompt, image_b64, media_type="image/jpeg", max_tokens=1500):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=MOBILE_SYSTEM,
            messages=[{"role":"user","content":[
                {"type":"image","source":{"type":"base64","media_type":media_type,"data":image_b64}},
                {"type":"text","text":prompt}
            ]}]
        )
        return r.content[0].text

    def ai_json(prompt, system="", max_tokens=600):
        result = ai_call(prompt, system or "Reply ONLY with valid JSON.", max_tokens)
        try:
            clean = re.sub(r"```[a-z]*","",result).replace("```","").strip()
            return json.loads(clean)
        except:
            m = re.search(r"\{.*\}",result,re.DOTALL)
            if m:
                try: return json.loads(m.group())
                except: pass
        return None

except ImportError:
    AI_AVAILABLE = False
    def ai_call(p,s="",m=1500): return "Install anthropic: pip install anthropic"
    def ai_vision(p,b,mt="image/jpeg",m=1500): return "Install anthropic."
    def ai_json(p,s="",m=600): return None

# ── Rich ───────────────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    RICH    = True
    console = Console()
    rprint  = console.print
except ImportError:
    RICH = False
    def rprint(x,**kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

MOBILE_SYSTEM = """You are FORGE — a powerful intelligence assistant on mobile.

You are concise, clear, and actionable. 
Responses are formatted for a phone screen — short paragraphs, key findings first.
You analyze images, locate places, investigate people/domains, and answer questions.
Always lead with the most important finding."""

# ── Paths ──────────────────────────────────────────────────────────────────────
MOBILE_DIR  = Path("forge_mobile")
UPLOADS_DIR = MOBILE_DIR / "uploads"
CACHE_DIR   = MOBILE_DIR / "cache"

for d in [MOBILE_DIR, UPLOADS_DIR, CACHE_DIR]:
    d.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# 📱 PWA HTML — the entire mobile app in one string
# ══════════════════════════════════════════════════════════════════════════════

def build_pwa_html(server_host=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#050810">
<title>FORGE Mobile</title>
<link rel="manifest" href="/manifest.json">
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Bebas+Neue&display=swap" rel="stylesheet">
<style>
:root {{
  --bg:     #050810;
  --panel:  #090c18;
  --border: #151c30;
  --green:  #00ff88;
  --gd:     #00804a;
  --amber:  #ff9500;
  --red:    #ff2244;
  --text:   #a0b4c8;
  --head:   #e0ecff;
  --dim:    #2a3448;
  --safe:   env(safe-area-inset-bottom, 0px);
}}
* {{ box-sizing:border-box; margin:0; padding:0; -webkit-tap-highlight-color:transparent; }}
html, body {{ height:100%; background:var(--bg); font-family:'Share Tech Mono',monospace; color:var(--text); overflow:hidden; }}

/* ── STATUS BAR ── */
.status-bar {{
  background:rgba(0,0,0,0.9);
  padding:env(safe-area-inset-top,0) 16px 8px;
  border-bottom:1px solid var(--border);
  display:flex; align-items:center; gap:10px;
  position:fixed; top:0; left:0; right:0; z-index:100;
}}
.status-bar .logo {{
  font-family:'Bebas Neue',sans-serif;
  font-size:20px; letter-spacing:6px; color:var(--green);
  text-shadow:0 0 12px rgba(0,255,136,0.4);
}}
.status-indicator {{
  width:7px; height:7px; border-radius:50%;
  background:var(--gd); margin-left:auto;
}}
.status-indicator.online {{ background:var(--green); box-shadow:0 0 6px var(--green); animation:blink 2s infinite; }}
.status-indicator.working {{ background:var(--amber); animation:blink 0.5s infinite; }}
@keyframes blink {{ 0%,100%{{opacity:1}} 50%{{opacity:0.3}} }}

/* ── TABS ── */
.tab-bar {{
  position:fixed; bottom:0; left:0; right:0;
  padding-bottom:var(--safe);
  background:rgba(5,8,16,0.98);
  border-top:1px solid var(--border);
  display:flex; z-index:100;
}}
.tab {{
  flex:1; display:flex; flex-direction:column; align-items:center;
  padding:10px 4px; gap:3px; cursor:pointer;
  font-size:8px; letter-spacing:1px; color:var(--dim);
  transition:color 0.15s;
  border:none; background:transparent;
}}
.tab.active {{ color:var(--green); }}
.tab-icon {{ font-size:18px; }}

/* ── PAGES ── */
.pages {{
  position:fixed;
  top:calc(52px + env(safe-area-inset-top,0px));
  bottom:calc(56px + var(--safe));
  left:0; right:0;
  overflow:hidden;
}}
.page {{
  position:absolute; inset:0;
  overflow-y:auto;
  padding:12px;
  display:none;
  -webkit-overflow-scrolling:touch;
}}
.page.active {{ display:block; }}

/* ── CHAT PAGE ── */
.chat-messages {{
  display:flex; flex-direction:column; gap:10px;
  padding-bottom:80px;
  min-height:100%;
}}
.msg {{
  max-width:88%; padding:10px 12px;
  border-radius:2px; font-size:12px; line-height:1.6;
}}
.msg.user {{
  background:rgba(0,255,136,0.08);
  border:1px solid var(--gd);
  align-self:flex-end;
  color:var(--green);
}}
.msg.forge {{
  background:var(--panel);
  border:1px solid var(--border);
  border-left:3px solid var(--gd);
  align-self:flex-start;
  color:var(--head);
}}
.msg.forge.thinking {{
  color:var(--dim);
  font-style:italic;
  animation:pulse 1s infinite;
}}
@keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:0.4}} }}
.msg-img {{
  max-width:100%; border:1px solid var(--border); display:block; margin-bottom:6px;
}}

/* ── CHAT INPUT ── */
.chat-input-wrap {{
  position:fixed;
  bottom:calc(56px + var(--safe));
  left:0; right:0;
  background:rgba(5,8,16,0.98);
  border-top:1px solid var(--border);
  padding:8px 12px;
  display:flex; gap:8px; align-items:flex-end;
}}
.chat-input {{
  flex:1;
  background:rgba(0,255,136,0.04);
  border:1px solid var(--gd);
  color:var(--green);
  font-family:'Share Tech Mono',monospace;
  font-size:12px;
  padding:8px 10px;
  outline:none; resize:none;
  max-height:80px;
  border-radius:2px;
}}
.chat-input::placeholder {{ color:var(--dim); }}
.send-btn {{
  width:38px; height:38px;
  background:var(--gd);
  border:none; cursor:pointer;
  display:flex; align-items:center; justify-content:center;
  font-size:16px; flex-shrink:0;
}}
.send-btn:active {{ background:var(--green); }}

/* ── ACTION BUTTONS ── */
.action-grid {{
  display:grid; grid-template-columns:1fr 1fr;
  gap:10px; margin-bottom:14px;
}}
.action-btn {{
  background:var(--panel);
  border:1px solid var(--border);
  border-top:2px solid var(--gd);
  padding:14px 10px;
  text-align:center; cursor:pointer;
  font-family:'Share Tech Mono',monospace;
  font-size:10px; letter-spacing:2px;
  color:var(--text);
  transition:border-top-color 0.15s;
}}
.action-btn:active {{ border-top-color:var(--green); background:rgba(0,255,136,0.04); }}
.action-icon {{ font-size:22px; display:block; margin-bottom:6px; }}

/* ── CAMERA PAGE ── */
#camera-preview {{
  width:100%; background:#000;
  border:1px solid var(--border);
  display:block; max-height:280px; object-fit:cover;
}}
.camera-controls {{
  display:flex; gap:10px; margin-top:10px;
}}
.cam-btn {{
  flex:1; padding:12px;
  background:var(--panel);
  border:1px solid var(--border);
  color:var(--text);
  font-family:'Share Tech Mono',monospace;
  font-size:10px; letter-spacing:2px;
  cursor:pointer; text-align:center;
}}
.cam-btn.primary {{ border-color:var(--gd); color:var(--green); }}
.cam-btn:active {{ background:rgba(0,255,136,0.08); }}
#capture-canvas {{ display:none; }}
#upload-input {{ display:none; }}
.analysis-result {{
  margin-top:12px;
  background:var(--panel);
  border:1px solid var(--border);
  border-left:3px solid var(--gd);
  padding:12px;
  font-size:12px; line-height:1.7;
  color:var(--head);
  white-space:pre-wrap;
}}

/* ── DASHBOARD PAGE ── */
.stat-grid {{
  display:grid; grid-template-columns:1fr 1fr;
  gap:10px; margin-bottom:14px;
}}
.stat-card {{
  background:var(--panel);
  border:1px solid var(--border);
  padding:14px 12px;
}}
.stat-num {{
  font-family:'Bebas Neue',sans-serif;
  font-size:32px; color:var(--green);
  line-height:1;
  text-shadow:0 0 12px rgba(0,255,136,0.2);
}}
.stat-label {{
  font-size:8px; letter-spacing:2px; color:var(--dim);
  margin-top:4px;
}}
.activity-log {{
  background:var(--panel);
  border:1px solid var(--border);
  padding:12px;
}}
.activity-title {{
  font-size:8px; letter-spacing:3px; color:var(--dim);
  margin-bottom:10px;
}}
.activity-item {{
  padding:6px 0;
  border-bottom:1px solid rgba(21,28,48,0.5);
  font-size:10px; color:var(--text);
  display:flex; gap:8px;
}}
.activity-time {{ color:var(--dim); flex-shrink:0; }}

/* ── TOOLS PAGE ── */
.tool-list {{ display:flex; flex-direction:column; gap:8px; }}
.tool-item {{
  background:var(--panel);
  border:1px solid var(--border);
  border-left:3px solid var(--gd);
  padding:12px;
  cursor:pointer;
  transition:border-left-color 0.15s;
}}
.tool-item:active {{ border-left-color:var(--green); }}
.tool-name {{
  font-size:12px; color:var(--green); margin-bottom:3px;
}}
.tool-desc {{ font-size:10px; color:var(--dim); }}
.tool-port {{ font-size:9px; color:var(--gd); margin-top:4px; }}

/* ── LOCATION ── */
.location-card {{
  background:var(--panel);
  border:1px solid var(--border);
  padding:14px;
  margin-bottom:10px;
}}
.loc-coords {{
  font-size:13px; color:var(--green); margin-bottom:6px;
}}
.loc-detail {{ font-size:10px; color:var(--text); line-height:1.8; }}

/* ── LOADING ── */
.loading-dots::after {{
  content:'...';
  animation:dots 1s steps(4,end) infinite;
}}
@keyframes dots {{
  0%,100%{{content:'.'}} 33%{{content:'..'}} 66%{{content:'...'}};
}}

/* Scrollbar */
::-webkit-scrollbar {{ width:3px; }}
::-webkit-scrollbar-thumb {{ background:var(--border); }}
</style>
</head>
<body>

<!-- STATUS BAR -->
<div class="status-bar">
  <div class="logo">FORGE</div>
  <div style="font-size:9px;letter-spacing:2px;color:var(--dim)" id="status-text">CONNECTING</div>
  <div class="status-indicator" id="status-dot"></div>
</div>

<!-- PAGES -->
<div class="pages">

  <!-- CHAT PAGE -->
  <div class="page active" id="page-chat">
    <div class="chat-messages" id="chat-messages">
      <div class="msg forge">
        FORGE MOBILE ONLINE.<br><br>
        Ask anything. Send a photo. I will analyze, locate, investigate.<br><br>
        <span style="color:var(--dim)">Try: "analyze this photo" → attach image<br>
        "investigate example.com"<br>
        "where was this taken?" → attach image</span>
      </div>
    </div>
  </div>

  <!-- CAMERA PAGE -->
  <div class="page" id="page-camera">
    <div style="margin-bottom:10px;font-size:8px;letter-spacing:3px;color:var(--dim)">VISUAL INTELLIGENCE</div>

    <div class="action-grid">
      <div class="action-btn" onclick="openCamera()">
        <span class="action-icon">📷</span>
        TAKE PHOTO
      </div>
      <div class="action-btn" onclick="document.getElementById('upload-input').click()">
        <span class="action-icon">🖼️</span>
        UPLOAD IMAGE
      </div>
      <div class="action-btn" onclick="analyzeMode='geospy';document.getElementById('upload-input').click()">
        <span class="action-icon">🌍</span>
        GEOSPY LOCATE
      </div>
      <div class="action-btn" onclick="analyzeMode='coldread';openCamera()">
        <span class="action-icon">🕵️</span>
        COLD READ
      </div>
    </div>

    <video id="camera-preview" autoplay playsinline style="display:none"></video>
    <canvas id="capture-canvas"></canvas>
    <img id="preview-img" style="width:100%;display:none;border:1px solid var(--border);max-height:280px;object-fit:cover">

    <div class="camera-controls" id="camera-controls" style="display:none">
      <div class="cam-btn primary" onclick="capturePhoto()">⚡ CAPTURE</div>
      <div class="cam-btn" onclick="stopCamera()">✕ STOP</div>
    </div>

    <div class="camera-controls" id="analyze-controls" style="display:none">
      <div class="cam-btn primary" onclick="analyzeCurrentImage()">🔍 ANALYZE</div>
      <div class="cam-btn" onclick="sendToChat()">💬 SEND TO CHAT</div>
    </div>

    <div id="vision-result" class="analysis-result" style="display:none"></div>
    <input type="file" id="upload-input" accept="image/*" onchange="handleUpload(event)">
  </div>

  <!-- DASHBOARD PAGE -->
  <div class="page" id="page-dash">
    <div style="margin-bottom:10px;font-size:8px;letter-spacing:3px;color:var(--dim)">INTELLIGENCE DASHBOARD</div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-num" id="stat-analyses">0</div>
        <div class="stat-label">ANALYSES</div>
      </div>
      <div class="stat-card">
        <div class="stat-num" id="stat-located">0</div>
        <div class="stat-label">LOCATED</div>
      </div>
      <div class="stat-card">
        <div class="stat-num" id="stat-missions">0</div>
        <div class="stat-label">MISSIONS</div>
      </div>
      <div class="stat-card">
        <div class="stat-num" id="stat-tools">22</div>
        <div class="stat-label">TOOLS</div>
      </div>
    </div>

    <div class="location-card" id="location-card" style="display:none">
      <div style="font-size:8px;letter-spacing:3px;color:var(--dim);margin-bottom:8px">YOUR LOCATION</div>
      <div class="loc-coords" id="loc-coords">--</div>
      <div class="loc-detail" id="loc-detail">Tap to get location</div>
    </div>
    <div class="cam-btn primary" onclick="getLocation()" style="margin-bottom:14px;text-align:center">
      📍 GET MY LOCATION
    </div>

    <div class="activity-log">
      <div class="activity-title">RECENT ACTIVITY</div>
      <div id="activity-list">
        <div style="color:var(--dim);font-size:10px">No activity yet.</div>
      </div>
    </div>
  </div>

  <!-- TOOLS PAGE -->
  <div class="page" id="page-tools">
    <div style="margin-bottom:10px;font-size:8px;letter-spacing:3px;color:var(--dim)">FORGE ECOSYSTEM</div>
    <div class="tool-list" id="tool-list"></div>
  </div>

</div>

<!-- CHAT INPUT (fixed above tab bar) -->
<div class="chat-input-wrap" id="chat-input-wrap">
  <textarea class="chat-input" id="chat-input"
    placeholder="Ask FORGE anything..."
    rows="1"
    onkeydown="handleKey(event)"
    oninput="this.style.height='auto';this.style.height=Math.min(this.scrollHeight,80)+'px'"></textarea>
  <button class="send-btn" onclick="sendMessage()">➤</button>
</div>

<!-- TAB BAR -->
<div class="tab-bar">
  <button class="tab active" onclick="switchTab('chat')" id="tab-chat">
    <span class="tab-icon">💬</span>CHAT
  </button>
  <button class="tab" onclick="switchTab('camera')" id="tab-camera">
    <span class="tab-icon">📷</span>CAMERA
  </button>
  <button class="tab" onclick="switchTab('dash')" id="tab-dash">
    <span class="tab-icon">📊</span>DASH
  </button>
  <button class="tab" onclick="switchTab('tools')" id="tab-tools">
    <span class="tab-icon">🔧</span>TOOLS
  </button>
</div>

<script>
const API = '';  // same origin
function handleKey(e) {{ if(e.key==='Enter'&&!e.shiftKey){{e.preventDefault();sendMessage();}} }}
let currentImage = null;
let currentImageB64 = null;
let analyzeMode = 'sherlock';
let cameraStream = null;
let stats = {{analyses:0, located:0, missions:0}};
let activity = [];
let chatHistory = [];

// ── TOOLS REGISTRY ─────────────────────────────────────────────────────────
const FORGE_TOOLS = [
  {{name:'forge_sherlock',     desc:'Holmes deduction engine — Mind Palace',      port:7340, icon:'🕵️'}},
  {{name:'forge_sherlock_video',desc:'Holmes watches video frame by frame',       port:7341, icon:'🎬'}},
  {{name:'forge_geospy',       desc:'Any image → GPS coordinates',                port:7342, icon:'🌍'}},
  {{name:'forge_hands',        desc:'Autonomous digital action engine',           port:7343, icon:'🤝'}},
  {{name:'forge_embodied',     desc:'Physical world — camera, mic, GPIO',         port:7344, icon:'🤖'}},
  {{name:'forge_detective',    desc:'Batcomputer — case file engine',             port:7338, icon:'🦇'}},
  {{name:'forge_nexus',        desc:'Unified intelligence pipeline',              port:7339, icon:'🔗'}},
  {{name:'forge_ghost',        desc:'Autonomous 24/7 agent missions',            port:7335, icon:'👻'}},
  {{name:'forge_monitor',      desc:'Production AI watchdog',                     port:7333, icon:'📡'}},
  {{name:'forge_llm_pentest',  desc:'OWASP LLM Top 10 security auditor',         port:7331, icon:'⚔️'}},
  {{name:'forge_investigate',  desc:'OSINT — DNS, WHOIS, IP, GitHub',            port:7337, icon:'🔍'}},
  {{name:'forge_arena',        desc:'AI vs AI battle testing',                   port:7336, icon:'🏟️'}},
];

// ── INIT ───────────────────────────────────────────────────────────────────
async function init() {{
  renderTools();
  await checkStatus();
  setInterval(checkStatus, 10000);
}}

async function checkStatus() {{
  try {{
    const r = await fetch('/api/status', {{signal:AbortSignal.timeout(3000)}});
    const d = await r.json();
    document.getElementById('status-dot').className = 'status-indicator online';
    document.getElementById('status-text').textContent = 'ONLINE';
  }} catch(e) {{
    document.getElementById('status-dot').className = 'status-indicator';
    document.getElementById('status-text').textContent = 'OFFLINE';
  }}
}}

function renderTools() {{
  const list = document.getElementById('tool-list');
  list.innerHTML = FORGE_TOOLS.map(t => `
    <div class="tool-item" onclick="window.open('http://localhost:${{t.port}}','_blank')">
      <div class="tool-name">${{t.icon}} ${{t.name}}</div>
      <div class="tool-desc">${{t.desc}}</div>
      <div class="tool-port">PORT ${{t.port}}</div>
    </div>`
  ).join('');
}}

// ── TABS ───────────────────────────────────────────────────────────────────
function switchTab(name) {{
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('page-'+name).classList.add('active');
  document.getElementById('tab-'+name).classList.add('active');

  // Hide chat input on non-chat tabs
  document.getElementById('chat-input-wrap').style.display =
    name === 'chat' ? 'flex' : 'none';

  if (name === 'dash') updateDash();
}}

// ── CHAT ───────────────────────────────────────────────────────────────────
function addMessage(role, content, imgSrc=null) {{
  const wrap = document.getElementById('chat-messages');
  const msg  = document.createElement('div');
  msg.className = `msg ${{role}}`;
  msg.id = 'msg-' + Date.now();

  if (imgSrc) {{
    const img = document.createElement('img');
    img.src = imgSrc; img.className = 'msg-img';
    msg.appendChild(img);
  }}
  const text = document.createElement('div');
  text.textContent = content;
  msg.appendChild(text);

  wrap.appendChild(msg);
  wrap.scrollTop = wrap.scrollHeight;
  return msg.id;
}}

function updateMessage(id, content) {{
  const el = document.getElementById(id);
  if (el) {{
    el.classList.remove('thinking');
    el.querySelector('div').textContent = content;
    document.getElementById('chat-messages').scrollTop = 99999;
  }}
}}

async function sendMessage() {{
  const input = document.getElementById('chat-input');
  const text  = input.value.trim();
  if (!text && !currentImageB64) return;

  input.value = '';
  input.style.height = 'auto';

  // Show user message
  addMessage('user', text || '📷 Image attached', currentImageB64 ?
    `data:image/jpeg;base64,${{currentImageB64}}` : null);

  // Thinking indicator
  const thinkId = addMessage('forge', '⚡ Analyzing');
  document.getElementById(thinkId).classList.add('thinking');

  document.getElementById('status-dot').className = 'status-indicator working';

  try {{
    const body = {{
      message:   text,
      image_b64: currentImageB64 || null,
      history:   chatHistory.slice(-6),
    }};

    const r = await fetch('/api/chat', {{
      method: 'POST',
      headers: {{'Content-Type':'application/json'}},
      body: JSON.stringify(body),
    }});
    const d = await r.json();

    updateMessage(thinkId, d.response || 'No response.');
    chatHistory.push({{role:'user',content:text}});
    chatHistory.push({{role:'assistant',content:d.response}});

    addActivity('chat', text.slice(0,40) || 'image analysis');
    stats.analyses++;
    document.getElementById('stat-analyses').textContent = stats.analyses;

  }} catch(e) {{
    updateMessage(thinkId, 'Error: ' + e.message);
  }}

  currentImageB64 = null;
  currentImage    = null;
  document.getElementById('status-dot').className = 'status-indicator online';
}}

// ── CAMERA ─────────────────────────────────────────────────────────────────
async function openCamera() {{
  try {{
    const constraints = {{
      video: {{
        facingMode: 'environment',  // rear camera
        width:  {{ideal:1280}},
        height: {{ideal:720}},
      }}
    }};
    cameraStream = await navigator.mediaDevices.getUserMedia(constraints);
    const video  = document.getElementById('camera-preview');
    video.srcObject = cameraStream;
    video.style.display = 'block';
    document.getElementById('preview-img').style.display   = 'none';
    document.getElementById('camera-controls').style.display = 'flex';
    document.getElementById('analyze-controls').style.display = 'none';
    document.getElementById('vision-result').style.display   = 'none';
  }} catch(e) {{
    alert('Camera access denied or unavailable: ' + e.message);
  }}
}}

function capturePhoto() {{
  const video  = document.getElementById('camera-preview');
  const canvas = document.getElementById('capture-canvas');
  canvas.width  = video.videoWidth  || 640;
  canvas.height = video.videoHeight || 480;
  canvas.getContext('2d').drawImage(video, 0, 0);

  currentImageB64 = canvas.toDataURL('image/jpeg', 0.85).split(',')[1];

  // Show preview
  const preview = document.getElementById('preview-img');
  preview.src = 'data:image/jpeg;base64,' + currentImageB64;
  preview.style.display = 'block';
  video.style.display   = 'none';

  stopCamera();
  document.getElementById('analyze-controls').style.display = 'flex';
}}

function stopCamera() {{
  if (cameraStream) {{
    cameraStream.getTracks().forEach(t => t.stop());
    cameraStream = null;
  }}
  document.getElementById('camera-preview').style.display   = 'none';
  document.getElementById('camera-controls').style.display  = 'none';
}}

function handleUpload(e) {{
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = ev => {{
    currentImageB64 = ev.target.result.split(',')[1];
    const preview   = document.getElementById('preview-img');
    preview.src     = ev.target.result;
    preview.style.display = 'block';
    document.getElementById('analyze-controls').style.display = 'flex';
    document.getElementById('vision-result').style.display    = 'none';
  }};
  reader.readAsDataURL(file);
  e.target.value = '';
}}

async function analyzeCurrentImage() {{
  if (!currentImageB64) return;

  const resultEl = document.getElementById('vision-result');
  resultEl.style.display = 'block';
  resultEl.textContent   = '⚡ Analyzing...';

  document.getElementById('status-dot').className = 'status-indicator working';

  try {{
    const r = await fetch('/api/analyze', {{
      method: 'POST',
      headers: {{'Content-Type':'application/json'}},
      body: JSON.stringify({{
        image_b64: currentImageB64,
        mode:      analyzeMode,
      }})
    }});
    const d = await r.json();
    resultEl.textContent = d.result || 'Analysis complete.';
    addActivity('analyze', analyzeMode);
    stats.analyses++;
    if (analyzeMode === 'geospy') stats.located++;
    document.getElementById('stat-analyses').textContent = stats.analyses;
    document.getElementById('stat-located').textContent  = stats.located;
    analyzeMode = 'sherlock';  // reset
  }} catch(e) {{
    resultEl.textContent = 'Error: ' + e.message;
  }}

  document.getElementById('status-dot').className = 'status-indicator online';
}}

function sendToChat() {{
  if (!currentImageB64) return;
  switchTab('chat');
  setTimeout(() => {{
    document.getElementById('chat-input').value = 'Analyze this image';
    sendMessage();
  }}, 100);
}}

// ── LOCATION ───────────────────────────────────────────────────────────────
function getLocation() {{
  if (!navigator.geolocation) {{
    alert('Geolocation not supported');
    return;
  }}
  navigator.geolocation.getCurrentPosition(async pos => {{
    const lat = pos.coords.latitude.toFixed(5);
    const lon = pos.coords.longitude.toFixed(5);
    const acc = Math.round(pos.coords.accuracy);

    document.getElementById('loc-coords').textContent = `${{lat}}, ${{lon}}`;
    document.getElementById('location-card').style.display = 'block';

    // Reverse geocode
    try {{
      const r = await fetch(
        `https://nominatim.openstreetmap.org/reverse?lat=${{lat}}&lon=${{lon}}&format=json`,
        {{headers:{{'User-Agent':'FORGE-Mobile/1.0'}}}}
      );
      const d = await r.json();
      document.getElementById('loc-detail').textContent =
        `${{d.display_name?.slice(0,80) || `${{lat}}, ${{lon}}`}}\nAccuracy: ±${{acc}}m`;
    }} catch(e) {{
      document.getElementById('loc-detail').textContent = `±${{acc}}m accuracy`;
    }}

    addActivity('location', `${{lat}},${{lon}}`);
  }}, err => {{
    alert('Location error: ' + err.message);
  }}, {{enableHighAccuracy:true, timeout:10000}});
}}

// ── DASHBOARD ──────────────────────────────────────────────────────────────
function updateDash() {{
  document.getElementById('stat-analyses').textContent = stats.analyses;
  document.getElementById('stat-located').textContent  = stats.located;
  document.getElementById('stat-missions').textContent = stats.missions;
}}

function addActivity(type, detail) {{
  const ts   = new Date().toLocaleTimeString('en',{{hour:'2-digit',minute:'2-digit'}});
  const icons = {{chat:'💬',analyze:'🔍',location:'📍',mission:'👻',camera:'📷'}};
  activity.unshift({{ts, type, detail, icon: icons[type]||'⚡'}});
  if (activity.length > 20) activity.pop();

  const list = document.getElementById('activity-list');
  list.innerHTML = activity.slice(0,8).map(a =>
    `<div class="activity-item">
      <div class="activity-time">${{a.ts}}</div>
      <div>${{a.icon}} ${{a.type.toUpperCase()}} — ${{a.detail}}</div>
    </div>`
  ).join('') || '<div style="color:var(--dim);font-size:10px">No activity.</div>';
}}

init();
</script>
</body>
</html>"""

# ══════════════════════════════════════════════════════════════════════════════
# 🚀 FASTAPI SERVER
# ══════════════════════════════════════════════════════════════════════════════

def create_app():
    if not FASTAPI:
        return None

    app = FastAPI(title="FORGE Mobile", version="1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                      allow_methods=["*"], allow_headers=["*"])

    # ── Activity log (in memory) ───────────────────────────────────────────
    activity_log = []
    stats        = {"analyses":0, "located":0, "missions":0}

    def log_activity(action_type, detail, result=""):
        entry = {
            "ts":     datetime.now().isoformat(),
            "type":   action_type,
            "detail": detail[:100],
            "result": result[:200],
        }
        activity_log.insert(0, entry)
        if len(activity_log) > 100:
            activity_log.pop()
        stats[action_type if action_type in stats else "analyses"] = \
            stats.get(action_type if action_type in stats else "analyses", 0) + 1

    # ── Routes ─────────────────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    async def root():
        return build_pwa_html()

    @app.get("/manifest.json")
    async def manifest():
        return JSONResponse({
            "name":             "FORGE Mobile",
            "short_name":       "FORGE",
            "description":      "AI Intelligence Platform",
            "start_url":        "/",
            "display":          "standalone",
            "background_color": "#050810",
            "theme_color":      "#050810",
            "orientation":      "portrait",
            "icons": [
                {"src":"/icon.png","sizes":"192x192","type":"image/png"},
                {"src":"/icon.png","sizes":"512x512","type":"image/png"},
            ]
        })

    @app.get("/api/status")
    async def status():
        return {
            "status":  "online",
            "ai":      AI_AVAILABLE,
            "ts":      datetime.now().isoformat(),
            "tools":   22,
            "stats":   stats,
        }

    @app.post("/api/chat")
    async def chat(data: dict):
        message   = data.get("message","")
        image_b64 = data.get("image_b64")
        history   = data.get("history",[])

        if not message and not image_b64:
            raise HTTPException(400, "message or image_b64 required")

        if not AI_AVAILABLE:
            return {"response":"AI not available. Install anthropic."}

        # Build messages
        messages = []
        for h in history[-6:]:
            messages.append({"role":h["role"],"content":h["content"]})

        if image_b64:
            content = [
                {"type":"image","source":{"type":"base64",
                 "media_type":"image/jpeg","data":image_b64}},
                {"type":"text","text":message or
                 "Analyze this image. What do you see? Any intelligence value?"}
            ]
            messages.append({"role":"user","content":content})
        else:
            messages.append({"role":"user","content":message})

        # Route to specialist based on message
        system = MOBILE_SYSTEM
        msg_l  = message.lower()

        if any(w in msg_l for w in ["where","location","geospy","locate","gps","taken"]):
            system += "\n\nFocus on geographic analysis. Read location from visual clues."
        elif any(w in msg_l for w in ["investigate","osint","whois","domain","who is"]):
            system += "\n\nFocus on OSINT investigation. Be specific and thorough."
        elif any(w in msg_l for w in ["cold read","read","deduce","sherlock","observe"]):
            system += "\n\nYou are Sherlock Holmes. Perform a full deduction chain."

        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=1000,
            system=system, messages=messages
        )
        response = r.content[0].text
        log_activity("chat", message[:50] or "image", response[:50])
        return {"response":response}

    @app.post("/api/analyze")
    async def analyze(data: dict):
        image_b64 = data.get("image_b64","")
        mode      = data.get("mode","sherlock")

        if not image_b64:
            raise HTTPException(400, "image_b64 required")

        if not AI_AVAILABLE:
            return {"result":"AI not available."}

        prompts = {
            "sherlock": """You are Sherlock Holmes analyzing this image.

## OBSERVATIONS
List every significant detail you notice.

## DEDUCTIONS
For each key observation:
CLUE: [detail]
  → INFERENCE: [meaning]
    → CONCLUSION: [deduction] [X%]

## THE ELEMENTARY
The single most significant finding.""",

            "geospy": """You are a geospatial intelligence analyst.

Analyze this image for location clues:
- Vegetation, architecture, road markings
- Sky, shadows, sun angle
- Signage language, vehicle types
- Infrastructure style

LOCATION ESTIMATE:
Country: [most likely]
Region: [region/city if determinable]
Coordinates: [lat, lon estimate]
Confidence: [X%]

KEY EVIDENCE:
List top 3 location-determining clues.""",

            "coldread": """You are Sherlock Holmes performing a cold read.

Analyze the person(s) in this image:

## PHYSICAL OBSERVATIONS
Clothing, posture, expression, hands, accessories.

## BEHAVIORAL READS
What are they doing? Why? What does it reveal?

## COLD READ DEDUCTIONS
OBSERVATION: [detail]
  → INFERENCE: [meaning]
    → CONCLUSION: [X%]

## THE READ
2-3 sentence summary of what you know about this person.""",

            "security": """Analyze this image for security relevance:

- Sensitive information visible?
- Identifiable locations or people?
- Any security concerns?
- Metadata implications?
- What should be redacted?

Be specific and actionable.""",
        }

        prompt = prompts.get(mode, prompts["sherlock"])
        result = ai_vision(prompt, image_b64)
        log_activity("analyze", mode, result[:50])
        stats["analyses"] = stats.get("analyses",0) + 1
        if mode == "geospy": stats["located"] = stats.get("located",0) + 1

        return {"result":result, "mode":mode}

    @app.post("/api/upload")
    async def upload(file: UploadFile = File(...)):
        """Upload image file."""
        content = await file.read()
        b64     = base64.standard_b64encode(content).decode()
        # Save
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = UPLOADS_DIR / f"upload_{ts}_{file.filename}"
        path.write_bytes(content)
        return {"filename":str(path),"image_b64":b64,"size":len(content)}

    @app.get("/api/activity")
    async def get_activity():
        return {"activity":activity_log[:20],"stats":stats}

    @app.post("/api/investigate")
    async def investigate(data: dict):
        """Quick OSINT investigation."""
        target = data.get("target","")
        if not target:
            raise HTTPException(400,"target required")

        try:
            from forge_investigate import quick_investigate
            result = quick_investigate(target)
            return {"result":result}
        except ImportError:
            if not AI_AVAILABLE:
                return {"result":"Install forge_investigate.py"}
            result = ai_call(
                f"Perform OSINT investigation on: {target}\n\n"
                "Check what you know about:\n"
                "- Is it a domain? Check DNS, company info\n"
                "- Is it a person? Professional background\n"
                "- Is it an IP? Geolocation, ASN\n"
                "Provide actionable intelligence.",
                max_tokens=600
            )
            log_activity("investigate", target, result[:50])
            return {"result":result}

    @app.post("/api/mission")
    async def run_mission(data: dict):
        """Start a Hands mission."""
        goal = data.get("goal","")
        if not goal:
            raise HTTPException(400,"goal required")
        try:
            from forge_hands import Mission, plan_mission, MissionExecutor
            m    = Mission(goal)
            plan = plan_mission(goal)
            stats["missions"] = stats.get("missions",0) + 1

            def run():
                exe = MissionExecutor(m)
                exe.execute(plan)
            threading.Thread(target=run, daemon=True).start()
            log_activity("mission", goal)
            return {"status":"started","mission_id":m.id,"goal":goal}
        except ImportError:
            return {"status":"error","message":"forge_hands.py required"}

    return app

# ══════════════════════════════════════════════════════════════════════════════
# 🖨️  QR CODE
# ══════════════════════════════════════════════════════════════════════════════

def print_qr(url):
    """Print QR code to terminal."""
    try:
        import qrcode
        qr   = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except ImportError:
        # ASCII art QR fallback
        rprint(f"\n  [yellow]📱 Open on your phone:[/yellow]")
        rprint(f"  [green bold]{url}[/green bold]")
        rprint(f"  [dim](Install qrcode for QR: pip install qrcode)[/dim]")

def get_local_ip():
    """Get local network IP."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "localhost"

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 NGROK PUBLIC URL
# ══════════════════════════════════════════════════════════════════════════════

def start_ngrok(port):
    """Start ngrok tunnel for public access."""
    try:
        import subprocess
        proc = subprocess.Popen(
            ["ngrok", "http", str(port)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        time.sleep(2)
        # Get URL from ngrok API
        r   = urllib.request.urlopen("http://localhost:4040/api/tunnels", timeout=3)
        data= json.loads(r.read())
        url = data["tunnels"][0]["public_url"]
        rprint(f"\n  [green]🌐 Public URL: {url}[/green]")
        print_qr(url)
        return url
    except FileNotFoundError:
        rprint("[yellow]ngrok not installed. Install from ngrok.com[/yellow]")
    except Exception as e:
        rprint(f"[yellow]ngrok error: {e}[/yellow]")
    return None

# ══════════════════════════════════════════════════════════════════════════════
# 🎮 MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ███╗   ███╗ ██████╗ ██████╗ ██╗██╗     ███████╗
  ████╗ ████║██╔═══██╗██╔══██╗██║██║     ██╔════╝
  ██╔████╔██║██║   ██║██████╔╝██║██║     █████╗
  ██║╚██╔╝██║██║   ██║██╔══██╗██║██║     ██╔══╝
  ██║ ╚═╝ ██║╚██████╔╝██████╔╝██║███████╗███████╗
  ╚═╝     ╚═╝ ╚═════╝ ╚═════╝ ╚═╝╚══════╝╚══════╝
[/yellow]
[bold]  📱 FORGE MOBILE — Intelligence in Your Pocket[/bold]
[dim]  Open the URL on any phone. No install needed.[/dim]
"""

def main():
    rprint(BANNER)
    rprint(f"  [dim]FastAPI: {'✅' if FASTAPI else '❌ pip install fastapi uvicorn'}[/dim]")
    rprint(f"  [dim]AI:      {'✅' if AI_AVAILABLE else '❌ pip install anthropic'}[/dim]\n")

    if not FASTAPI:
        rprint("[red]Install FastAPI first:[/red]")
        rprint("  pip install fastapi uvicorn python-multipart")
        return

    port   = 7345
    public = False

    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port")+1])
    if "--public" in sys.argv:
        public = True

    ip  = get_local_ip()
    url = f"http://{ip}:{port}"

    rprint(f"  [green]📱 FORGE MOBILE starting...[/green]")
    rprint(f"  [yellow]Local:   http://localhost:{port}[/yellow]")
    rprint(f"  [yellow]Network: {url}[/yellow]")

    if "--qr" in sys.argv or True:  # always show
        print_qr(url)

    if public:
        threading.Thread(target=start_ngrok, args=(port,), daemon=True).start()

    rprint(f"\n  [dim]Open on your phone: {url}[/dim]")
    rprint(f"  [dim]Press Ctrl+C to stop[/dim]\n")

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="error")

if __name__ == "__main__":
    main()
