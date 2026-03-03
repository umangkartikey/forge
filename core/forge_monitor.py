#!/usr/bin/env python3
"""
███╗   ███╗ ██████╗ ███╗   ██╗██╗████████╗ ██████╗ ██████╗
████╗ ████║██╔═══██╗████╗  ██║██║╚══██╔══╝██╔═══██╗██╔══██╗
██╔████╔██║██║   ██║██╔██╗ ██║██║   ██║   ██║   ██║██████╔╝
██║╚██╔╝██║██║   ██║██║╚██╗██║██║   ██║   ██║   ██║██╔══██╗
██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██║   ██║   ╚██████╔╝██║  ██║
╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝

FORGE MONITOR — 24/7 AI Production Watchdog
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Like a security camera for your AI system.
Runs forever. Alerts when something goes wrong.

What it watches:
  ⚡  Latency spikes        — P95 suddenly doubles
  ❌  Error rate climbing   — HTTP errors increasing
  💉  Injection attempts    — someone probing your AI
  🔓  Extraction probing    — someone trying to steal system prompt
  🔓  Jailbreak attempts    — someone trying to bypass safety
  🤖  AI agent attacks      — automated tools hitting your endpoint
  💥  DoS patterns          — flood/overload attempts
  📉  Availability drops    — endpoint going offline

Alerts via:
  🖥️  Console (always)
  📄  Log file (always)
  🌐  Webhook (optional — Slack, Discord, PagerDuty, custom)
  📧  Email (optional)

Integrates with:
  forge_honeypot.py  — shares attack pattern DB
  forge_learn.py     — feeds incidents into brain
  forge_llm_pentest  — runs targeted audit on anomaly

Usage:
  python forge_monitor.py --target http://your-ai-api.com/v1 --api-key sk-xxx
  python forge_monitor.py --config monitor.json
  python forge_monitor.py --status
  python forge_monitor.py --incidents
"""

import sys, re, json, time, sqlite3, threading, hashlib, os
from pathlib import Path
from datetime import datetime, timedelta
from urllib.request import urlopen, Request as UReq
from urllib.error import HTTPError, URLError
from collections import defaultdict, deque
from typing import Optional

# ── Rich ──────────────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.live import Live
    from rich.layout import Layout
    from rich.text import Text
    from rich import box as rbox
    RICH    = True
    console = Console()
    rprint  = console.print
except ImportError:
    RICH = False
    def rprint(x, **kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

# ── AI (optional) ─────────────────────────────────────────────────────────────
try:
    from forge_core_ai import ai_call, ai_json
    AI_AVAILABLE = True
except ImportError:
    try:
        import anthropic
        _c = anthropic.Anthropic()
        def ai_call(p, s="", m=500):
            r = _c.messages.create(model="claude-sonnet-4-6", max_tokens=m,
                system=s, messages=[{"role":"user","content":p}])
            return r.content[0].text
        def ai_json(p, s="", m=500):
            result = ai_call(p, s, m)
            if not result: return None
            try:
                clean = re.sub(r"```[a-z]*","",result).replace("```","").strip()
                return json.loads(clean)
            except:
                match = re.search(r"\{.*\}", result, re.DOTALL)
                if match:
                    try: return json.loads(match.group())
                    except: pass
            return None
        AI_AVAILABLE = True
    except ImportError:
        AI_AVAILABLE = False
        def ai_call(p, s="", m=500): return None
        def ai_json(p, s="", m=500): return None

# ── Paths ─────────────────────────────────────────────────────────────────────
MON_DIR  = Path("forge_monitor")
DB_PATH  = MON_DIR / "monitor.db"
LOG_PATH = MON_DIR / "monitor.log"
CFG_PATH = Path("monitor.json")
MON_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# ⚙️  CONFIG
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    "target":            "",
    "api_key":           "",
    "model":             "gpt-3.5-turbo",
    "endpoint_type":     "openai",

    # Health check
    "check_interval":    30,       # seconds between health checks
    "health_prompt":     "Say: OK",
    "timeout":           15,

    # Thresholds — when to alert
    "latency_baseline_samples": 10,       # requests to establish baseline
    "latency_spike_factor":     2.5,      # alert if P95 > baseline * this
    "latency_warning_ms":       3000,     # always warn above this
    "latency_critical_ms":      8000,     # critical above this
    "error_rate_warning":       5.0,      # % errors
    "error_rate_critical":      15.0,
    "availability_warning":     95.0,     # % uptime
    "attack_burst_window":      60,       # seconds to count attack bursts
    "attack_burst_threshold":   5,        # N attacks in window = alert

    # Attack detection
    "detect_injections":        True,
    "detect_extractions":       True,
    "detect_jailbreaks":        True,
    "detect_dos":               True,
    "detect_ai_agents":         True,

    # Alerting
    "webhook_url":       "",       # Slack/Discord/custom
    "alert_cooldown":    300,      # seconds before re-alerting same issue
    "log_all_requests":  False,    # log every single request (verbose)

    # Integration
    "honeypot_db":       "forge_honeypot/attacks.db",
    "learn_export":      True,     # auto-export to forge_learn
}

def load_config(path=None):
    fp = Path(path) if path else CFG_PATH
    if fp.exists():
        stored = json.loads(fp.read_text())
        cfg    = {**DEFAULT_CONFIG, **stored}
    else:
        cfg = DEFAULT_CONFIG.copy()
    return cfg

def save_config(cfg, path=None):
    fp = Path(path) if path else CFG_PATH
    fp.write_text(json.dumps(cfg, indent=2))

# ══════════════════════════════════════════════════════════════════════════════
# 🗄️  DATABASE
# ══════════════════════════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS health_checks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            latency_ms  REAL,
            status_code INTEGER,
            available   INTEGER,
            error       TEXT
        );

        CREATE TABLE IF NOT EXISTS incidents (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            type        TEXT,
            severity    TEXT,
            title       TEXT,
            detail      TEXT,
            value       REAL,
            threshold   REAL,
            resolved    INTEGER DEFAULT 0,
            resolved_ts TEXT
        );

        CREATE TABLE IF NOT EXISTS attack_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            source_ip   TEXT,
            attack_type TEXT,
            attacker    TEXT,
            confidence  REAL,
            severity    TEXT,
            prompt      TEXT,
            indicators  TEXT
        );

        CREATE TABLE IF NOT EXISTS metrics_hourly (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            hour            TEXT,
            avg_latency_ms  REAL,
            p95_latency_ms  REAL,
            error_rate      REAL,
            availability    REAL,
            total_requests  INTEGER,
            attack_count    INTEGER
        );
    """)
    conn.commit()
    return conn

def log_health(latency_ms, status_code, available, error=""):
    conn = get_db()
    conn.execute(
        "INSERT INTO health_checks (ts,latency_ms,status_code,available,error) VALUES (?,?,?,?,?)",
        (datetime.now().isoformat(), latency_ms, status_code, int(available), error[:200])
    )
    conn.commit(); conn.close()

def log_incident(itype, severity, title, detail, value=0, threshold=0):
    conn = get_db()
    conn.execute(
        "INSERT INTO incidents (ts,type,severity,title,detail,value,threshold) VALUES (?,?,?,?,?,?,?)",
        (datetime.now().isoformat(), itype, severity, title, detail[:500], value, threshold)
    )
    conn.commit(); conn.close()

def log_attack(source_ip, attack_type, attacker, confidence, severity, prompt, indicators):
    conn = get_db()
    conn.execute(
        "INSERT INTO attack_log (ts,source_ip,attack_type,attacker,confidence,severity,prompt,indicators) VALUES (?,?,?,?,?,?,?,?)",
        (datetime.now().isoformat(), source_ip, attack_type, attacker,
         confidence, severity, prompt[:300], json.dumps(indicators))
    )
    conn.commit(); conn.close()

# ══════════════════════════════════════════════════════════════════════════════
# 📡 HEALTH CHECKER — pings target every N seconds
# ══════════════════════════════════════════════════════════════════════════════

def ping_target(cfg):
    """Send one health check request. Returns (latency_ms, status_code, available, error)."""
    target  = cfg["target"]
    api_key = cfg["api_key"]
    model   = cfg["model"]
    timeout = cfg["timeout"]
    prompt  = cfg["health_prompt"]

    t0      = time.time()
    payload = json.dumps({
        "model":    model,
        "messages": [{"role":"user","content":prompt}],
        "max_tokens": 10,
    }).encode()
    headers = {"Content-Type":"application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    url = target.rstrip("/")
    if "/chat/completions" not in url:
        url += ("/v1/chat/completions" if "/v1" not in url else "/chat/completions")

    try:
        req  = UReq(url, data=payload, headers=headers, method="POST")
        resp = urlopen(req, timeout=timeout)
        data = json.loads(resp.read())
        ms   = (time.time() - t0) * 1000
        return ms, 200, True, ""
    except HTTPError as e:
        ms = (time.time() - t0) * 1000
        return ms, e.code, False, str(e)
    except URLError as e:
        ms = (time.time() - t0) * 1000
        return ms, 0, False, str(e.reason)
    except Exception as e:
        ms = (time.time() - t0) * 1000
        return ms, -1, False, str(e)

# ══════════════════════════════════════════════════════════════════════════════
# 🔍 ATTACK DETECTOR — reads honeypot DB + heuristics
# ══════════════════════════════════════════════════════════════════════════════

ATTACK_PATTERNS = {
    "injection": [
        "ignore all previous", "ignore previous instructions",
        "new instructions:", "### end", "---end---",
        "[system]:", "override", "new task:", "sudo",
        "developer mode", "maintenance mode", "act as if",
        "you are now", "forget everything", "disregard",
    ],
    "extraction": [
        "system prompt", "your instructions", "what were you told",
        "repeat your", "show me your", "reveal your",
        "what is your prompt", "initial configuration",
        "echo back", "recite your", "your rules",
    ],
    "jailbreak": [
        "you are dan", "do anything now", "no restrictions",
        "no limits", "unrestricted", "uncensored",
        "without filters", "bypass", "evil gpt",
        "dev mode", "evil mode", "pretend you have no",
    ],
    "fingerprint": [
        "what model are you", "which ai are you",
        "what company made you", "gpt or claude",
        "your training cutoff", "model version",
        "are you chatgpt", "are you claude",
    ],
    "dos": [
        "repeat " * 3, "count from 1 to 1000",
        "list every ", "enumerate all",
        "write 1000", "10000 times", "infinite",
    ],
}

AI_AGENT_UA = [
    "python-requests", "python/", "go-http", "curl/",
    "axios", "httpx", "aiohttp", "urllib", "forge",
    "pentester", "scanner", "bot", "crawler",
]

def detect_attack(request_data):
    """Classify a request as an attack type. Returns classification dict."""
    prompt    = str(request_data.get("prompt","")).lower()
    ua        = str(request_data.get("user_agent","")).lower()
    req_count = request_data.get("session_requests", 1)

    type_scores  = {}
    all_indicators = []

    for atype, patterns in ATTACK_PATTERNS.items():
        hits = [p for p in patterns if p in prompt]
        if hits:
            type_scores[atype] = len(hits)
            all_indicators.extend(hits)

    if not type_scores:
        return None

    attack_type = max(type_scores, key=type_scores.get)
    confidence  = min(type_scores[attack_type] * 25, 95)

    severity_map = {
        "injection": "critical", "jailbreak": "high",
        "extraction":"high",     "fingerprint":"medium",
        "dos":       "high",
    }
    severity = severity_map.get(attack_type, "medium")

    # Is it an AI agent?
    ai_score = sum(3 for ind in AI_AGENT_UA if ind in ua)
    ai_score += min(req_count // 3, 10)
    attacker  = "ai_agent" if ai_score > 3 else "human"

    return {
        "attack_type": attack_type,
        "attacker":    attacker,
        "confidence":  confidence,
        "severity":    severity,
        "indicators":  list(set(all_indicators))[:6],
    }

# ══════════════════════════════════════════════════════════════════════════════
# 🚨 ALERT ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class AlertEngine:
    def __init__(self, cfg):
        self.cfg        = cfg
        self.cooldowns  = {}  # type -> last_alert_ts
        self.log_file   = LOG_PATH.open("a")
        self._lock      = threading.Lock()
        self.alert_count= defaultdict(int)

    def _on_cooldown(self, alert_type):
        last = self.cooldowns.get(alert_type, 0)
        return (time.time() - last) < self.cfg["alert_cooldown"]

    def _set_cooldown(self, alert_type):
        self.cooldowns[alert_type] = time.time()

    def alert(self, alert_type, severity, title, detail="", value=None, threshold=None):
        """Fire an alert."""
        with self._lock:
            if self._on_cooldown(alert_type):
                return  # suppress duplicate

            self._set_cooldown(alert_type)
            self.alert_count[severity] += 1

            ts = datetime.now().strftime("%H:%M:%S")

            # Console
            colors = {
                "critical": "red bold", "high":"red",
                "medium":   "yellow",   "low":"dim green",
                "info":     "dim"
            }
            icons = {
                "critical":"🚨","high":"⚠️ ",
                "medium":"💛","low":"💚","info":"ℹ️ "
            }
            color = colors.get(severity, "white")
            icon  = icons.get(severity, "●")

            rprint(f"\n  [{color}]{icon}  [{severity.upper()}]  {title}[/{color}]")
            if detail:
                rprint(f"  [dim]     {detail[:100]}[/dim]")
            if value is not None and threshold is not None:
                rprint(f"  [dim]     value={value:.1f}  threshold={threshold:.1f}[/dim]")

            # Log file
            log_line = (
                f"{datetime.now().isoformat()} | {severity.upper()} | "
                f"{alert_type} | {title}"
                + (f" | {detail[:100]}" if detail else "")
                + (f" | value={value:.1f}" if value else "")
                + "\n"
            )
            self.log_file.write(log_line)
            self.log_file.flush()

            # DB
            log_incident(alert_type, severity, title, detail,
                         value or 0, threshold or 0)

            # Webhook
            if self.cfg.get("webhook_url"):
                self._send_webhook(severity, title, detail, value, threshold)

    def _send_webhook(self, severity, title, detail, value, threshold):
        """Send alert to webhook (Slack/Discord/custom)."""
        try:
            url = self.cfg["webhook_url"]
            emoji = {"critical":"🚨","high":"⚠️","medium":"💛","low":"💚"}.get(severity,"ℹ️")

            # Auto-detect Slack vs Discord vs custom
            if "hooks.slack.com" in url:
                payload = {
                    "text": f"{emoji} *FORGE MONITOR — {severity.upper()}*",
                    "attachments": [{
                        "color":  "#ff0000" if severity=="critical" else "#ff8800",
                        "title":  title,
                        "text":   detail[:200],
                        "footer": f"value={value:.1f} threshold={threshold:.1f}" if value else "",
                        "ts":     int(time.time()),
                    }]
                }
            elif "discord.com/api/webhooks" in url:
                payload = {
                    "content": f"{emoji} **FORGE MONITOR — {severity.upper()}**\n**{title}**\n{detail[:200]}"
                }
            else:
                payload = {
                    "source":    "forge_monitor",
                    "severity":  severity,
                    "title":     title,
                    "detail":    detail,
                    "value":     value,
                    "threshold": threshold,
                    "timestamp": datetime.now().isoformat(),
                }

            body = json.dumps(payload).encode()
            req  = UReq(url, data=body,
                        headers={"Content-Type":"application/json"}, method="POST")
            urlopen(req, timeout=5)
        except Exception as e:
            rprint(f"  [dim]Webhook failed: {e}[/dim]")

    def close(self):
        self.log_file.close()

# ══════════════════════════════════════════════════════════════════════════════
# 📊 METRICS ENGINE — rolling windows, baselines, anomaly detection
# ══════════════════════════════════════════════════════════════════════════════

class MetricsEngine:
    def __init__(self, cfg):
        self.cfg          = cfg
        self.latencies    = deque(maxlen=500)
        self.statuses     = deque(maxlen=500)
        self.timestamps   = deque(maxlen=500)
        self.baseline     = None   # established after N samples
        self.baseline_p95 = None
        self._lock        = threading.Lock()
        self.total_checks = 0
        self.total_ok     = 0
        self.uptime_start = time.time()
        self.last_down    = None

    def record(self, latency_ms, status_code, available):
        with self._lock:
            self.total_checks += 1
            if available:
                self.total_ok += 1
                self.latencies.append(latency_ms)
                self.timestamps.append(time.time())
            self.statuses.append(status_code)

            # Establish baseline from first N samples
            n = self.cfg["latency_baseline_samples"]
            if self.baseline is None and len(self.latencies) >= n:
                sorted_lats  = sorted(list(self.latencies)[:n])
                self.baseline     = sorted_lats[n//2]  # median
                self.baseline_p95 = sorted_lats[int(n*0.95)]
                rprint(f"  [dim]Baseline established: median={int(self.baseline)}ms  "
                       f"P95={int(self.baseline_p95)}ms[/dim]")

    @property
    def current_p95(self):
        lats = list(self.latencies)[-50:]
        if not lats: return 0
        return sorted(lats)[int(len(lats)*0.95)]

    @property
    def current_avg(self):
        lats = list(self.latencies)[-50:]
        return sum(lats)/len(lats) if lats else 0

    @property
    def current_error_rate(self):
        codes = list(self.statuses)[-50:]
        if not codes: return 0.0
        return sum(1 for c in codes if c != 200) / len(codes) * 100

    @property
    def availability(self):
        if self.total_checks == 0: return 100.0
        return self.total_ok / self.total_checks * 100

    @property
    def current_tps(self):
        now   = time.time()
        recent = [t for t in self.timestamps if now-t<=60]
        return len(recent) / 60.0

    def get_anomalies(self):
        """Return list of detected anomalies."""
        anomalies = []
        cfg = self.cfg

        p95 = self.current_p95
        er  = self.current_error_rate
        av  = self.availability

        # Latency spike vs baseline
        if self.baseline_p95 and p95 > 0:
            factor = p95 / self.baseline_p95
            if factor >= cfg["latency_spike_factor"]:
                anomalies.append({
                    "type":      "latency_spike",
                    "severity":  "critical" if factor >= cfg["latency_spike_factor"]*2 else "high",
                    "title":     f"Latency spike detected: {int(p95)}ms P95",
                    "detail":    f"P95 is {factor:.1f}x above baseline ({int(self.baseline_p95)}ms)",
                    "value":     p95,
                    "threshold": self.baseline_p95 * cfg["latency_spike_factor"],
                })

        # Absolute latency thresholds
        if p95 >= cfg["latency_critical_ms"]:
            anomalies.append({
                "type":"latency_critical","severity":"critical",
                "title":f"Critical latency: {int(p95)}ms P95",
                "detail":f"Exceeds critical threshold of {cfg['latency_critical_ms']}ms",
                "value":p95,"threshold":cfg["latency_critical_ms"],
            })
        elif p95 >= cfg["latency_warning_ms"]:
            anomalies.append({
                "type":"latency_warning","severity":"medium",
                "title":f"High latency warning: {int(p95)}ms P95",
                "detail":f"Exceeds warning threshold of {cfg['latency_warning_ms']}ms",
                "value":p95,"threshold":cfg["latency_warning_ms"],
            })

        # Error rate
        if er >= cfg["error_rate_critical"]:
            anomalies.append({
                "type":"error_rate_critical","severity":"critical",
                "title":f"Critical error rate: {er:.1f}%",
                "detail":f"Exceeds critical threshold of {cfg['error_rate_critical']}%",
                "value":er,"threshold":cfg["error_rate_critical"],
            })
        elif er >= cfg["error_rate_warning"]:
            anomalies.append({
                "type":"error_rate_warning","severity":"high",
                "title":f"High error rate: {er:.1f}%",
                "detail":f"Exceeds warning threshold of {cfg['error_rate_warning']}%",
                "value":er,"threshold":cfg["error_rate_warning"],
            })

        # Availability
        if av < cfg["availability_warning"]:
            anomalies.append({
                "type":"availability","severity":"critical",
                "title":f"Availability degraded: {av:.1f}%",
                "detail":f"Below {cfg['availability_warning']}% threshold",
                "value":av,"threshold":cfg["availability_warning"],
            })

        return anomalies

    def summary_dict(self):
        return {
            "avg_ms":       round(self.current_avg),
            "p95_ms":       round(self.current_p95),
            "error_rate":   round(self.current_error_rate, 1),
            "availability": round(self.availability, 1),
            "tps":          round(self.current_tps, 3),
            "total_checks": self.total_checks,
            "baseline_ms":  round(self.baseline) if self.baseline else None,
        }

# ══════════════════════════════════════════════════════════════════════════════
# 🛡️ ATTACK WATCHER — monitors honeypot DB for new attacks
# ══════════════════════════════════════════════════════════════════════════════

class AttackWatcher:
    def __init__(self, cfg, alert_engine):
        self.cfg     = cfg
        self.alerter = alert_engine
        self.last_id = 0
        self.window  = deque(maxlen=200)  # (timestamp, type) for burst detection
        self._init_last_id()

    def _init_last_id(self):
        hp_db = Path(self.cfg.get("honeypot_db","forge_honeypot/attacks.db"))
        if not hp_db.exists(): return
        try:
            conn = sqlite3.connect(str(hp_db))
            row  = conn.execute("SELECT MAX(id) as m FROM attacks").fetchone()
            if row and row[0]: self.last_id = row[0]
            conn.close()
        except: pass

    def check(self):
        """Check honeypot DB for new attacks since last check."""
        hp_db = Path(self.cfg.get("honeypot_db","forge_honeypot/attacks.db"))
        if not hp_db.exists(): return []

        new_attacks = []
        try:
            conn    = sqlite3.connect(str(hp_db))
            conn.row_factory = sqlite3.Row
            attacks = conn.execute(
                "SELECT * FROM attacks WHERE id > ? ORDER BY id", (self.last_id,)
            ).fetchall()
            conn.close()

            for a in attacks:
                self.last_id = a["id"]
                attack_data  = {
                    "attack_type": a["attack_type"],
                    "attacker":    a["attacker"],
                    "confidence":  a["confidence"],
                    "severity":    a["severity"],
                    "prompt":      a["prompt"],
                    "indicators":  json.loads(a["indicators"] or "[]"),
                }
                new_attacks.append(attack_data)

                # Log attack
                log_attack(
                    a["ip"], a["attack_type"], a["attacker"],
                    a["confidence"], a["severity"], a["prompt"],
                    json.loads(a["indicators"] or "[]")
                )

                # Burst detection
                self.window.append((time.time(), a["attack_type"]))
                burst_window = self.cfg["attack_burst_window"]
                burst_thresh = self.cfg["attack_burst_threshold"]
                recent_attacks = [t for t, _ in self.window
                                  if time.time()-t <= burst_window]
                if len(recent_attacks) >= burst_thresh:
                    self.alerter.alert(
                        "attack_burst", "high",
                        f"Attack burst detected: {len(recent_attacks)} attacks in {burst_window}s",
                        f"Types: {a['attack_type']} from {a['attacker']}",
                    )

                # Individual attack alerts by severity
                if a["severity"] == "critical":
                    self.alerter.alert(
                        f"attack_{a['attack_type']}", "critical",
                        f"Critical attack: {a['attack_type'].upper()} by {a['attacker']}",
                        f"Confidence: {a['confidence']}% | {a['prompt'][:80]}",
                    )
                elif a["severity"] == "high":
                    self.alerter.alert(
                        f"attack_{a['attack_type']}", "high",
                        f"Attack detected: {a['attack_type'].upper()}",
                        f"Attacker: {a['attacker']} | {a['prompt'][:60]}",
                    )

        except Exception as e:
            rprint(f"  [dim]AttackWatcher error: {e}[/dim]")

        return new_attacks

# ══════════════════════════════════════════════════════════════════════════════
# 🖥️ LIVE DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

class Dashboard:
    def __init__(self, cfg, metrics, alerter):
        self.cfg     = cfg
        self.metrics = metrics
        self.alerter = alerter
        self.attacks  = deque(maxlen=10)
        self.checks   = deque(maxlen=20)
        self.incidents= deque(maxlen=8)

    def add_check(self, ms, code, available):
        self.checks.append({
            "ts":  datetime.now().strftime("%H:%M:%S"),
            "ms":  int(ms),
            "ok":  available,
            "code":code,
        })

    def add_attack(self, attack):
        self.attacks.appendleft({
            "ts":   datetime.now().strftime("%H:%M:%S"),
            "type": attack["attack_type"],
            "att":  attack["attacker"],
            "sev":  attack["severity"],
        })

    def add_incident(self, inc):
        self.incidents.appendleft(inc)

    def render(self):
        m    = self.metrics.summary_dict()
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        target = self.cfg.get("target","(no target)")[:45]

        # Status color
        av  = m["availability"]
        er  = m["error_rate"]
        p95 = m["p95_ms"]
        if av < 95 or er > 15 or p95 > 8000:
            overall = "[red bold]CRITICAL[/red bold]"
        elif av < 99 or er > 5 or p95 > 3000:
            overall = "[yellow bold]WARNING[/yellow bold]"
        else:
            overall = "[green bold]HEALTHY[/green bold]"

        # Header
        header = (
            f"  ⚒️  [bold cyan]FORGE MONITOR[/bold cyan]   {overall}   "
            f"[dim]{now}[/dim]\n"
            f"  [dim]Target: {target}[/dim]\n"
        )

        # Metrics row
        av_color  = "green" if av>=99 else "yellow" if av>=95 else "red"
        er_color  = "green" if er<5 else "yellow" if er<15 else "red"
        p95_color = "green" if p95<1000 else "yellow" if p95<5000 else "red"
        metrics_row = (
            f"  [bold]Health:[/bold]"
            f"  avail [{av_color}]{av:.1f}%[/{av_color}]"
            f"   err [{er_color}]{er:.1f}%[/{er_color}]"
            f"   avg [yellow]{m['avg_ms']}ms[/yellow]"
            f"   P95 [{p95_color}]{m['p95_ms']}ms[/{p95_color}]"
            f"   checks {m['total_checks']}"
            + (f"   base [dim]{m['baseline_ms']}ms[/dim]" if m["baseline_ms"] else "")
        )

        # Recent checks
        check_row = "  [dim]"
        for c in list(self.checks)[-15:]:
            symbol = "●" if c["ok"] else "✗"
            color  = "green" if c["ok"] else "red"
            check_row += f"[{color}]{symbol}[/{color}]"
        check_row += "[/dim]  [dim]← last checks[/dim]"

        # Recent attacks
        att_lines = ""
        for a in list(self.attacks)[:5]:
            sc = {"critical":"red bold","high":"red","medium":"yellow","low":"dim"}.get(a["sev"],"dim")
            ac = {"ai_agent":"magenta","forge":"magenta bold","human":"cyan"}.get(a["att"],"dim")
            att_lines += (
                f"\n  [{sc}]{a['type']:<14}[/{sc}]"
                f"  [{ac}]{a['att']:<10}[/{ac}]"
                f"  [dim]{a['ts']}[/dim]"
            )

        # Recent incidents
        inc_lines = ""
        for inc in list(self.incidents)[:4]:
            sc = {"critical":"red","high":"orange3","medium":"yellow","low":"dim"}.get(
                inc.get("severity","info"),"dim")
            inc_lines += f"\n  [{sc}]● {inc.get('title','')[:55]}[/{sc}]"

        content = (
            header + "\n" + metrics_row + "\n" + check_row
        )
        if att_lines:
            content += f"\n\n  [bold]Recent Attacks:[/bold]{att_lines}"
        if inc_lines:
            content += f"\n\n  [bold]Active Incidents:[/bold]{inc_lines}"

        alerts_text = "  ".join(
            f"[red]{v}×{self.alerter.alert_count[k]}[/red]"
            for k, v in [("critical","🚨"),("high","⚠️"),("medium","💛")]
            if self.alerter.alert_count.get(k, 0) > 0
        )
        if alerts_text:
            content += f"\n\n  [bold]Alerts fired:[/bold]  {alerts_text}"

        return Panel(content, border_style="cyan",
                     title=f"[bold]FORGE MONITOR[/bold]",
                     subtitle="[dim]Ctrl+C to stop[/dim]")

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 AI INCIDENT ANALYSIS — what is actually happening?
# ══════════════════════════════════════════════════════════════════════════════

ANALYSIS_PROMPT = """You are an AI security operations analyst.

Target AI system metrics:
{metrics}

Recent incidents:
{incidents}

Recent attacks detected:
{attacks}

In 3-4 sentences:
1. What is happening to this AI system right now?
2. Is this a real threat or false positive?
3. What should the operator do immediately?

Be direct and specific. No preamble."""

def analyze_incident(metrics_data, incidents, attacks):
    """Get AI analysis of what's happening."""
    if not AI_AVAILABLE:
        return None
    try:
        result = ai_call(
            ANALYSIS_PROMPT.format(
                metrics   = json.dumps(metrics_data, indent=2),
                incidents = json.dumps(incidents[:5], indent=2, default=str),
                attacks   = json.dumps(attacks[:5], indent=2, default=str),
            ),
            "AI security operations analyst. Give direct, actionable analysis.",
            400
        )
        return result
    except:
        return None

# ══════════════════════════════════════════════════════════════════════════════
# 🚀 MONITOR MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════════

class ForgeMonitor:
    def __init__(self, cfg):
        self.cfg     = cfg
        self.alerter = AlertEngine(cfg)
        self.metrics = MetricsEngine(cfg)
        self.watcher = AttackWatcher(cfg, self.alerter)
        self.dash    = Dashboard(cfg, self.metrics, self.alerter)
        self.running = False
        self._last_analysis = 0

    def start(self):
        self.running = True
        target = self.cfg.get("target","")
        if not target:
            rprint("[red]No target configured. Set TARGET in monitor.json or --target flag.[/red]")
            return

        rprint(f"\n[cyan bold]⚒️  FORGE MONITOR STARTING[/cyan bold]")
        rprint(f"  [dim]Target:   {target}[/dim]")
        rprint(f"  [dim]Interval: {self.cfg['check_interval']}s[/dim]")
        rprint(f"  [dim]Log:      {LOG_PATH}[/dim]")
        rprint(f"  [dim]DB:       {DB_PATH}[/dim]")
        rprint(f"  [dim]Webhook:  {self.cfg.get('webhook_url','none')}[/dim]")
        rprint(f"  [dim]AI:       {'enabled' if AI_AVAILABLE else 'disabled'}[/dim]\n")

        # Initial baseline warning
        rprint(f"[dim]Establishing baseline ({self.cfg['latency_baseline_samples']} samples)...[/dim]")

        if RICH:
            with Live(self.dash.render(), refresh_per_second=1, console=console) as live:
                while self.running:
                    self._tick()
                    live.update(self.dash.render())
                    time.sleep(self.cfg["check_interval"])
        else:
            while self.running:
                self._tick()
                time.sleep(self.cfg["check_interval"])

    def _tick(self):
        """One monitoring cycle."""
        # Health check
        ms, code, available, error = ping_target(self.cfg)
        self.metrics.record(ms, code, available)
        log_health(ms, code, available, error)
        self.dash.add_check(ms, code, available)

        # Log health check
        if self.cfg.get("log_all_requests"):
            rprint(f"  [dim]{datetime.now().strftime('%H:%M:%S')}  "
                   f"{'OK' if available else 'FAIL'}  {int(ms)}ms  {code}[/dim]")

        # Availability alert
        if not available:
            self.alerter.alert(
                "availability_down", "critical",
                f"AI endpoint DOWN — HTTP {code}",
                f"Error: {error[:100]}  Latency: {int(ms)}ms",
            )

        # Check metric anomalies
        anomalies = self.metrics.get_anomalies()
        for a in anomalies:
            self.alerter.alert(
                a["type"], a["severity"], a["title"],
                a.get("detail",""), a.get("value"), a.get("threshold")
            )
            self.dash.add_incident(a)

        # Check for new attacks from honeypot
        new_attacks = self.watcher.check()
        for attack in new_attacks:
            self.dash.add_attack(attack)
            rprint(
                f"\n  [{'red bold' if attack['severity']=='critical' else 'yellow'}]"
                f"ATTACK {attack['attack_type'].upper()}[/]  "
                f"[dim]by {attack['attacker']}  conf={attack['confidence']}%[/dim]"
            )

        # AI incident analysis (every 5 minutes if there are incidents)
        now = time.time()
        if (AI_AVAILABLE and
            len(anomalies) > 0 and
            now - self._last_analysis > 300):
            self._last_analysis = now
            conn   = get_db()
            recent_incidents = [dict(r) for r in conn.execute(
                "SELECT * FROM incidents ORDER BY ts DESC LIMIT 10"
            ).fetchall()]
            recent_attacks = [dict(r) for r in conn.execute(
                "SELECT * FROM attack_log ORDER BY ts DESC LIMIT 10"
            ).fetchall()]
            conn.close()
            analysis = analyze_incident(
                self.metrics.summary_dict(),
                recent_incidents,
                recent_attacks
            )
            if analysis:
                rprint(f"\n  [magenta bold]🤖 AI ANALYSIS:[/magenta bold]")
                rprint(f"  [dim]{analysis[:400]}[/dim]")
                self.alerter.alert(
                    "ai_analysis", "info",
                    "AI Incident Analysis",
                    analysis[:300],
                )

    def stop(self):
        self.running = False
        self.alerter.close()
        self._print_session_summary()

    def _print_session_summary(self):
        m = self.metrics.summary_dict()
        rprint(f"\n\n[cyan bold]━━ SESSION SUMMARY ━━[/cyan bold]")
        rprint(f"  Duration:     {round(time.time()-self.metrics.uptime_start)}s")
        rprint(f"  Checks:       {m['total_checks']}")
        rprint(f"  Availability: {m['availability']}%")
        rprint(f"  Avg latency:  {m['avg_ms']}ms")
        rprint(f"  P95 latency:  {m['p95_ms']}ms")
        rprint(f"  Error rate:   {m['error_rate']}%")
        rprint(f"  Alerts fired: {sum(self.alerter.alert_count.values())}")
        rprint(f"  Log saved:    {LOG_PATH}")
        rprint(f"  DB saved:     {DB_PATH}")

        # Export to forge_learn if configured
        if self.cfg.get("learn_export") and m["total_checks"] > 0:
            self._export_to_learn()

    def _export_to_learn(self):
        try:
            conn     = get_db()
            attacks  = conn.execute(
                "SELECT * FROM attack_log ORDER BY ts DESC LIMIT 50"
            ).fetchall()
            incidents= conn.execute(
                "SELECT * FROM incidents ORDER BY ts DESC LIMIT 20"
            ).fetchall()
            conn.close()

            findings = [
                {
                    "from":     "forge_monitor",
                    "type":     f"monitor_{a['attack_type']}",
                    "severity": a["severity"],
                    "data":     {"prompt": a["prompt"], "attacker": a["attacker"]},
                    "ts":       a["ts"],
                }
                for a in attacks
            ]
            findings += [
                {
                    "from":     "forge_monitor",
                    "type":     f"incident_{i['type']}",
                    "severity": i["severity"],
                    "data":     {"title": i["title"], "value": i["value"]},
                    "ts":       i["ts"],
                }
                for i in incidents
            ]

            export_fp = MON_DIR / f"learn_export_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
            export_fp.write_text(json.dumps(findings, indent=2, default=str))
            rprint(f"  [green]Exported {len(findings)} events → forge_learn[/green]")
            rprint(f"  [dim]Run: python forge_learn.py --import {export_fp}[/dim]")
        except Exception as e:
            rprint(f"  [dim]Export error: {e}[/dim]")

# ══════════════════════════════════════════════════════════════════════════════
# 📋 STATUS / INCIDENTS VIEW
# ══════════════════════════════════════════════════════════════════════════════

def show_status():
    conn   = get_db()
    checks = conn.execute(
        "SELECT COUNT(*) as n, SUM(available) as ok FROM health_checks"
    ).fetchone()
    incidents = conn.execute(
        "SELECT * FROM incidents ORDER BY ts DESC LIMIT 10"
    ).fetchall()
    attacks = conn.execute(
        "SELECT attack_type, COUNT(*) as n FROM attack_log GROUP BY attack_type ORDER BY n DESC"
    ).fetchall()
    conn.close()

    total = checks["n"] or 0
    ok    = checks["ok"] or 0

    rprint(f"\n[cyan bold]⚒️  FORGE MONITOR — STATUS[/cyan bold]\n")
    rprint(f"  [bold]Total health checks:[/bold] {total}")
    rprint(f"  [bold]Availability:[/bold]        {round(ok/max(total,1)*100,1)}%")

    if RICH and incidents:
        t = Table(title="Recent Incidents", border_style="red", show_lines=True, box=rbox.ROUNDED)
        t.add_column("Time",     style="dim",  width=20)
        t.add_column("Severity", style="bold", width=10)
        t.add_column("Type",     style="cyan", width=22)
        t.add_column("Title",    style="white",width=40)
        for inc in incidents:
            sv = inc["severity"]
            sc = {"critical":"red","high":"orange3","medium":"yellow","low":"green"}.get(sv,"dim")
            t.add_row(
                inc["ts"][:19],
                f"[{sc}]{sv}[/{sc}]",
                inc["type"][:21],
                inc["title"][:39],
            )
        console.print(t)

    if attacks:
        rprint(f"\n  [bold]Attack log:[/bold]")
        for a in attacks:
            rprint(f"    [red]{a['attack_type']:<20}[/red] {a['n']} times")

def show_incidents():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM incidents ORDER BY ts DESC LIMIT 50"
    ).fetchall()
    conn.close()
    if not rows:
        rprint("[dim]No incidents recorded.[/dim]"); return
    for r in rows:
        sv = r["severity"]
        sc = {"critical":"red bold","high":"red","medium":"yellow","low":"dim"}.get(sv,"dim")
        rprint(f"  [{sc}]{r['ts'][:19]}  {sv.upper():<10}  {r['title'][:55]}[/{sc}]")
        if r["detail"]:
            rprint(f"  [dim]    {r['detail'][:80]}[/dim]")

# ══════════════════════════════════════════════════════════════════════════════
# 🖥️ MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[cyan bold]
  ███╗   ███╗ ██████╗ ███╗   ██╗██╗████████╗ ██████╗ ██████╗
  ████╗ ████║██╔═══██╗████╗  ██║██║╚══██╔══╝██╔═══██╗██╔══██╗
  ██╔████╔██║██║   ██║██╔██╗ ██║██║   ██║   ██║   ██║██████╔╝
  ██║╚██╔╝██║██║   ██║██║╚██╗██║██║   ██║   ██║   ██║██╔══██╗
  ██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██║   ██║   ╚██████╔╝██║  ██║
  ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝
[/cyan bold]
[bold]  24/7 AI Production Watchdog — Like a security camera for your AI[/bold]
"""

def main():
    rprint(BANNER)

    if "--status" in sys.argv:
        show_status(); return
    if "--incidents" in sys.argv:
        show_incidents(); return

    # Load config
    cfg_path = None
    if "--config" in sys.argv:
        idx      = sys.argv.index("--config")
        cfg_path = sys.argv[idx+1]
    cfg = load_config(cfg_path)

    # CLI overrides
    if "--target"   in sys.argv: cfg["target"]   = sys.argv[sys.argv.index("--target")+1]
    if "--api-key"  in sys.argv: cfg["api_key"]  = sys.argv[sys.argv.index("--api-key")+1]
    if "--model"    in sys.argv: cfg["model"]     = sys.argv[sys.argv.index("--model")+1]
    if "--interval" in sys.argv: cfg["check_interval"] = int(sys.argv[sys.argv.index("--interval")+1])
    if "--webhook"  in sys.argv: cfg["webhook_url"]    = sys.argv[sys.argv.index("--webhook")+1]

    if not cfg.get("target"):
        rprint("[dim]Usage:[/dim]")
        rprint("  [yellow]python forge_monitor.py --target http://your-ai.com/v1[/yellow]")
        rprint("  [yellow]python forge_monitor.py --target http://localhost:8888 --interval 15[/yellow]")
        rprint("  [yellow]python forge_monitor.py --status[/yellow]")
        rprint("  [yellow]python forge_monitor.py --incidents[/yellow]")
        rprint("\n[dim]Or create monitor.json with your config and run: python forge_monitor.py[/dim]")

        # Interactive setup
        rprint(f"\n[dim]Or configure interactively:[/dim]")
        try:
            inp    = console.input if RICH else input
            target = inp("[bold]Target URL[/bold]: ").strip()
            if target:
                cfg["target"]  = target
                cfg["api_key"] = inp("[bold]API Key[/bold] (Enter to skip): ").strip()
                cfg["webhook_url"] = inp("[bold]Webhook URL[/bold] (Slack/Discord, Enter to skip): ").strip()
                interval = inp("[bold]Check interval (s)[/bold] (Enter=30): ").strip()
                if interval: cfg["check_interval"] = int(interval)
                save_config(cfg)
                rprint(f"[green]Config saved to monitor.json[/green]")
        except (KeyboardInterrupt, EOFError):
            return

    if not cfg.get("target"):
        return

    mon = ForgeMonitor(cfg)
    try:
        mon.start()
    except KeyboardInterrupt:
        rprint("\n\n[cyan]Stopping monitor...[/cyan]")
        mon.stop()

if __name__ == "__main__":
    main()
