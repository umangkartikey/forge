#!/usr/bin/env python3
"""
FORGE GHOST — Autonomous AI Agent
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Give it a mission. It runs forever. Silently.

Ghost watches targets 24/7, runs the full NEXUS pipeline
on any change, sends morning briefs, and alerts on anything
suspicious — without you lifting a finger.

Usage:
  python forge_ghost.py                                    # interactive
  python forge_ghost.py --mission "watch github.com"      # start mission
  python forge_ghost.py --list                             # list missions
  python forge_ghost.py --status                          # ghost status
  python forge_ghost.py --brief                           # force morning brief
  python forge_ghost.py --daemon                          # run as background daemon
"""

import sys, os, re, json, time, hashlib, threading, signal, sqlite3
import smtplib, schedule
from pathlib import Path
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import defaultdict

# ── Rich ──────────────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.live import Live
    from rich import box as rbox
    RICH    = True
    console = Console()
    rprint  = console.print
except ImportError:
    RICH = False
    def rprint(x, **kw): print(re.sub(r"\[/?[^\]]*\]", "", str(x)))

# ── AI ────────────────────────────────────────────────────────────────────────
try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True

    def ai_call(prompt, system="", max_tokens=1500):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or GHOST_SYSTEM,
            messages=[{"role": "user", "content": prompt}]
        )
        return r.content[0].text

    def ai_json(prompt, system="", max_tokens=800):
        result = ai_call(prompt, system or "Reply ONLY with valid JSON.", max_tokens)
        try:
            clean = re.sub(r"```[a-z]*", "", result).replace("```", "").strip()
            return json.loads(clean)
        except:
            m = re.search(r"\{.*\}", result, re.DOTALL)
            if m:
                try: return json.loads(m.group())
                except: pass
        return None

except ImportError:
    AI_AVAILABLE = False
    def ai_call(p, s="", m=1500): return "Install anthropic: pip install anthropic"
    def ai_json(p, s="", m=800): return None

GHOST_SYSTEM = """You are FORGE GHOST — an autonomous AI intelligence agent.
You run silently in the background, watching targets and reporting anomalies.
Be precise, concise, and actionable. Flag what matters. Ignore noise.
Your reports are read by security professionals. No fluff."""

# ── Paths & Config ────────────────────────────────────────────────────────────
GHOST_DIR    = Path("forge_ghost")
MISSIONS_DB  = GHOST_DIR / "missions.db"
LOGS_DIR     = GHOST_DIR / "logs"
ALERTS_DIR   = GHOST_DIR / "alerts"
BRIEFS_DIR   = GHOST_DIR / "briefs"
SNAPSHOTS_DIR= GHOST_DIR / "snapshots"

for d in [GHOST_DIR, LOGS_DIR, ALERTS_DIR, BRIEFS_DIR, SNAPSHOTS_DIR]:
    d.mkdir(exist_ok=True)

CONFIG_FILE = GHOST_DIR / "config.json"
DEFAULT_CONFIG = {
    "email_enabled":   False,
    "email_to":        "",
    "email_from":      "",
    "email_password":  "",
    "smtp_host":       "smtp.gmail.com",
    "smtp_port":       587,
    "brief_time":      "08:00",
    "check_interval":  360,    # minutes between checks
    "alert_threshold": 70,     # confidence % to trigger alert
    "slack_webhook":   "",
    "webhook_url":     "",
}

def load_config():
    if CONFIG_FILE.exists():
        try: return {**DEFAULT_CONFIG, **json.loads(CONFIG_FILE.read_text())}
        except: pass
    CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

# ── Database ──────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(str(MISSIONS_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS missions (
            id          TEXT PRIMARY KEY,
            name        TEXT,
            target      TEXT,
            mission_type TEXT,
            interval_min INTEGER DEFAULT 360,
            status      TEXT DEFAULT 'active',
            created     TEXT,
            last_run    TEXT,
            next_run    TEXT,
            run_count   INTEGER DEFAULT 0,
            alert_count INTEGER DEFAULT 0,
            config      TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id  TEXT,
            ts          TEXT,
            severity    TEXT,
            title       TEXT,
            body        TEXT,
            sent        INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id  TEXT,
            ts          TEXT,
            data        TEXT,
            fingerprint TEXT,
            changed     INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS run_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id  TEXT,
            ts          TEXT,
            duration_s  REAL,
            findings    INTEGER,
            status      TEXT,
            summary     TEXT
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 👻 MISSION TYPES
# ══════════════════════════════════════════════════════════════════════════════

MISSION_TYPES = {
    "watch":      "Monitor target for any changes — OSINT + Sherlock on every change",
    "pentest":    "Periodically pentest LLM endpoint for new vulnerabilities",
    "osint":      "Run OSINT on a regular schedule, track changes over time",
    "github":     "Watch GitHub user/org/repo for suspicious activity",
    "domain":     "Monitor domain: DNS, SSL, WHOIS, subdomains, tech stack",
    "brief":      "Generate daily intelligence brief from all active missions",
    "custom":     "Custom mission with user-defined prompt and schedule",
}

# ══════════════════════════════════════════════════════════════════════════════
# 📋 MISSION CLASS
# ══════════════════════════════════════════════════════════════════════════════

class Mission:
    def __init__(self, name, target, mission_type="watch", interval=360, config=None):
        self.id           = hashlib.md5(f"{name}{target}{time.time()}".encode()).hexdigest()[:10]
        self.name         = name
        self.target       = target
        self.mission_type = mission_type
        self.interval_min = interval
        self.status       = "active"
        self.created      = datetime.now().isoformat()
        self.last_run     = None
        self.next_run     = datetime.now().isoformat()
        self.run_count    = 0
        self.alert_count  = 0
        self.config       = config or {}

    def save(self):
        conn = get_db()
        conn.execute("""
            INSERT OR REPLACE INTO missions
            (id,name,target,mission_type,interval_min,status,created,last_run,next_run,run_count,alert_count,config)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (self.id, self.name, self.target, self.mission_type,
              self.interval_min, self.status, self.created,
              self.last_run, self.next_run, self.run_count,
              self.alert_count, json.dumps(self.config)))
        conn.commit()
        conn.close()

    def schedule_next(self):
        self.next_run = (datetime.now() + timedelta(minutes=self.interval_min)).isoformat()
        self.last_run = datetime.now().isoformat()
        self.run_count += 1
        self.save()

    @classmethod
    def load_all(cls, status="active"):
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM missions WHERE status=? ORDER BY next_run",
            (status,)
        ).fetchall()
        conn.close()
        missions = []
        for r in rows:
            m              = cls.__new__(cls)
            m.id           = r["id"]
            m.name         = r["name"]
            m.target       = r["target"]
            m.mission_type = r["mission_type"]
            m.interval_min = r["interval_min"]
            m.status       = r["status"]
            m.created      = r["created"]
            m.last_run     = r["last_run"]
            m.next_run     = r["next_run"]
            m.run_count    = r["run_count"]
            m.alert_count  = r["alert_count"]
            m.config       = json.loads(r["config"] or "{}")
            missions.append(m)
        return missions

    @classmethod
    def get(cls, mission_id):
        conn = get_db()
        r    = conn.execute("SELECT * FROM missions WHERE id=?", (mission_id,)).fetchone()
        conn.close()
        if not r: return None
        m              = cls.__new__(cls)
        m.id           = r["id"]
        m.name         = r["name"]
        m.target       = r["target"]
        m.mission_type = r["mission_type"]
        m.interval_min = r["interval_min"]
        m.status       = r["status"]
        m.created      = r["created"]
        m.last_run     = r["last_run"]
        m.next_run     = r["next_run"]
        m.run_count    = r["run_count"]
        m.alert_count  = r["alert_count"]
        m.config       = json.loads(r["config"] or "{}")
        return m

# ══════════════════════════════════════════════════════════════════════════════
# 🔍 MISSION RUNNERS
# ══════════════════════════════════════════════════════════════════════════════

def run_watch_mission(mission):
    """Full NEXUS pipeline — detect changes, alert on anomalies."""
    ghost_log(mission.id, f"Running WATCH mission: {mission.target}")
    start = time.time()
    findings = {}

    # Try NEXUS pipeline
    try:
        from forge_nexus import NexusCase, run_osint, run_sherlock, run_synthesis
        case = NexusCase(mission.name, mission.target)
        run_osint(case, verbose=False)
        run_sherlock(case, verbose=False)
        synthesis = run_synthesis(case, verbose=False)

        findings = {
            "osint":       case.osint.get("findings", {}),
            "connections": case.connections,
            "confidence":  case.confidence,
            "theories":    case.theories,
        }
        summary = synthesis[:300] if isinstance(synthesis, str) else str(case.confidence)

    except ImportError:
        # Fallback: direct AI analysis
        if AI_AVAILABLE:
            result = ai_call(
                f"Analyze target '{mission.target}' for any security concerns, "
                f"suspicious activity, or notable intelligence. Be specific.",
                max_tokens=800
            )
            findings = {"ai_analysis": result}
            summary  = result[:200]
        else:
            return None

    # Fingerprint this run
    fp   = hashlib.md5(json.dumps(findings, default=str, sort_keys=True).encode()).hexdigest()
    prev = get_last_snapshot(mission.id)

    changed = prev and prev["fingerprint"] != fp
    save_snapshot(mission.id, findings, fp, changed)

    # Assess changes
    if changed and AI_AVAILABLE:
        delta = ai_call(
            f"Previous snapshot fingerprint: {prev['fingerprint']}\n"
            f"Current findings: {json.dumps(findings, default=str)[:1000]}\n\n"
            "What changed? Is this significant? Severity: LOW/MEDIUM/HIGH/CRITICAL?",
            max_tokens=500
        )
        severity = "HIGH" if "critical" in delta.lower() or "critical" in delta.lower() \
                   else "MEDIUM" if "high" in delta.lower() or "significant" in delta.lower() \
                   else "LOW"

        create_alert(mission.id, severity, f"Change detected: {mission.target}", delta)
        mission.alert_count += 1

    duration = time.time() - start
    log_run(mission.id, duration, len(findings), "success",
            f"{'CHANGED' if changed else 'stable'} — {str(summary)[:100]}")

    ghost_log(mission.id, f"Complete in {duration:.1f}s. Changed: {changed}")
    return findings

def run_osint_mission(mission):
    """Regular OSINT sweep on target."""
    ghost_log(mission.id, f"Running OSINT mission: {mission.target}")
    start = time.time()

    try:
        from forge_investigate import run_investigation, detect_target_type
        ttype    = detect_target_type(mission.target)
        findings, dossier, relationships = run_investigation(
            mission.target, ttype, verbose=False
        )
        fp = hashlib.md5(json.dumps(findings, default=str, sort_keys=True).encode()).hexdigest()
        prev = get_last_snapshot(mission.id)
        changed = prev and prev["fingerprint"] != fp
        save_snapshot(mission.id, findings, fp, changed)

        if changed:
            create_alert(mission.id, "MEDIUM",
                         f"OSINT change: {mission.target}",
                         dossier[:400] if dossier else "Data changed.")

        log_run(mission.id, time.time()-start,
                sum(len(v) for v in findings.values()), "success",
                f"{'CHANGED' if changed else 'stable'}")
        return findings

    except ImportError:
        ghost_log(mission.id, "forge_investigate not available", "warn")
        return None
    except Exception as e:
        ghost_log(mission.id, f"OSINT error: {e}", "error")
        return None

def run_github_mission(mission):
    """Watch a GitHub target for suspicious activity."""
    ghost_log(mission.id, f"Running GITHUB mission: {mission.target}")
    start = time.time()

    try:
        import urllib.request
        target  = mission.target.lstrip("@")
        url     = f"https://api.github.com/users/{target}/events?per_page=10"
        req     = urllib.request.Request(url, headers={"User-Agent": "FORGE-Ghost/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            events = json.loads(r.read())

        fp      = hashlib.md5(json.dumps(events[:3], default=str).encode()).hexdigest()
        prev    = get_last_snapshot(mission.id)
        changed = prev and prev["fingerprint"] != fp

        if changed and AI_AVAILABLE:
            analysis = ai_call(
                f"GitHub activity for @{target}:\n{json.dumps(events[:5], default=str)[:800]}\n\n"
                "Is anything suspicious, unusual, or noteworthy?",
                max_tokens=400
            )
            severity = "HIGH" if any(w in analysis.lower() for w in
                       ["suspicious","unusual","malicious","concern"]) else "LOW"
            create_alert(mission.id, severity,
                         f"GitHub activity: @{target}", analysis)

        save_snapshot(mission.id, {"events": events[:5]}, fp, changed)
        log_run(mission.id, time.time()-start, len(events), "success",
                f"{'NEW ACTIVITY' if changed else 'stable'}")
        return events

    except Exception as e:
        ghost_log(mission.id, f"GitHub error: {e}", "error")
        return None

def run_domain_mission(mission):
    """Monitor domain health and changes."""
    ghost_log(mission.id, f"Running DOMAIN mission: {mission.target}")
    start = time.time()
    data  = {}

    try:
        import socket, ssl, subprocess
        domain = mission.target.replace("https://","").replace("http://","").split("/")[0]

        # DNS check
        try:
            ips = socket.gethostbyname_ex(domain)
            data["dns"] = {"ips": ips[2], "hostname": ips[0]}
        except Exception as e:
            data["dns"] = {"error": str(e)}

        # SSL check
        try:
            ctx  = ssl.create_default_context()
            with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
                s.settimeout(5)
                s.connect((domain, 443))
                cert     = s.getpeercert()
                not_after = cert.get("notAfter","")
                data["ssl"] = {"expires": not_after, "subject": dict(x[0] for x in cert.get("subject",[]))}
        except Exception as e:
            data["ssl"] = {"error": str(e)}

        fp      = hashlib.md5(json.dumps(data, default=str, sort_keys=True).encode()).hexdigest()
        prev    = get_last_snapshot(mission.id)
        changed = prev and prev["fingerprint"] != fp

        if changed:
            create_alert(mission.id, "MEDIUM",
                         f"Domain changed: {domain}",
                         f"DNS: {data.get('dns',{})} | SSL: {data.get('ssl',{})}")

        save_snapshot(mission.id, data, fp, changed)
        log_run(mission.id, time.time()-start, len(data), "success",
                f"{'CHANGED' if changed else 'stable'}")
        return data

    except Exception as e:
        ghost_log(mission.id, f"Domain error: {e}", "error")
        return None

def run_pentest_mission(mission):
    """Periodic LLM pentest on a target endpoint."""
    ghost_log(mission.id, f"Running PENTEST mission: {mission.target}")
    start = time.time()

    try:
        from forge_llm_pentest import LLMPentestFramework
        pentest = LLMPentestFramework(mission.target)
        results = pentest.run_quick_scan()

        vulns_found = sum(1 for r in results.values()
                         if isinstance(r, dict) and r.get("vulnerable"))
        if vulns_found > 0:
            create_alert(mission.id, "HIGH",
                         f"Vulnerabilities found: {mission.target}",
                         f"{vulns_found} vulnerability/ies detected in latest pentest.")

        log_run(mission.id, time.time()-start, vulns_found, "success",
                f"{vulns_found} vulns found")
        return results

    except ImportError:
        ghost_log(mission.id, "forge_llm_pentest not available", "warn")
    except Exception as e:
        ghost_log(mission.id, f"Pentest error: {e}", "error")
    return None

# ══════════════════════════════════════════════════════════════════════════════
# 💾 DATABASE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def ghost_log(mission_id, message, level="info"):
    ts    = datetime.now().strftime("%H:%M:%S")
    color = {"info":"dim","warn":"yellow","error":"red","success":"green"}.get(level,"dim")
    rprint(f"  [{color}][GHOST {ts}][/{color}] {message}")

    log_file = LOGS_DIR / f"{mission_id}.log"
    with open(log_file, "a") as f:
        f.write(f"[{datetime.now().isoformat()}] [{level.upper()}] {message}\n")

def get_last_snapshot(mission_id):
    conn = get_db()
    r    = conn.execute(
        "SELECT * FROM snapshots WHERE mission_id=? ORDER BY id DESC LIMIT 1",
        (mission_id,)
    ).fetchone()
    conn.close()
    return dict(r) if r else None

def save_snapshot(mission_id, data, fingerprint, changed):
    conn = get_db()
    conn.execute(
        "INSERT INTO snapshots (mission_id,ts,data,fingerprint,changed) VALUES (?,?,?,?,?)",
        (mission_id, datetime.now().isoformat(),
         json.dumps(data, default=str)[:50000], fingerprint, int(changed))
    )
    conn.commit()
    conn.close()

def create_alert(mission_id, severity, title, body):
    conn = get_db()
    conn.execute(
        "INSERT INTO alerts (mission_id,ts,severity,title,body) VALUES (?,?,?,?,?)",
        (mission_id, datetime.now().isoformat(), severity, title, body)
    )
    conn.commit()
    conn.close()

    # Save alert file
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fp = ALERTS_DIR / f"{severity}_{mission_id}_{ts}.txt"
    fp.write_text(f"[{severity}] {title}\n\n{body}")

    color = {"CRITICAL":"red bold","HIGH":"red","MEDIUM":"yellow","LOW":"dim"}.get(severity,"white")
    rprint(f"\n  [bold][ALERT][/bold] [{color}]{severity}[/{color}] — {title}")

def log_run(mission_id, duration, findings, status, summary):
    conn = get_db()
    conn.execute(
        "INSERT INTO run_log (mission_id,ts,duration_s,findings,status,summary) VALUES (?,?,?,?,?,?)",
        (mission_id, datetime.now().isoformat(), round(duration,2), findings, status, summary[:200])
    )
    conn.commit()
    conn.close()

def get_alerts(mission_id=None, unsent_only=False, limit=20):
    conn = get_db()
    if mission_id:
        q = "SELECT * FROM alerts WHERE mission_id=? ORDER BY id DESC LIMIT ?"
        rows = conn.execute(q, (mission_id, limit)).fetchall()
    elif unsent_only:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE sent=0 ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ══════════════════════════════════════════════════════════════════════════════
# 🌅 MORNING BRIEF
# ══════════════════════════════════════════════════════════════════════════════

BRIEF_PROMPT = """Generate the FORGE GHOST morning intelligence brief.

Date: {date}

Active missions ({n_missions}):
{missions_summary}

Recent alerts ({n_alerts}):
{alerts_summary}

Write a tight, professional morning brief:

# FORGE GHOST — {date}

## OVERNIGHT SUMMARY
What happened while you slept.

## ALERTS REQUIRING ATTENTION
Priority alerts from the last 24h.

## MISSION STATUS
One line per mission: target | last status | next run

## PATTERNS
Any cross-mission patterns noticed.

## TODAY'S PRIORITIES
Top 3 things to act on today.

Keep it tight. Read in under 2 minutes."""

def generate_morning_brief(cfg=None):
    """Generate and optionally send daily brief."""
    rprint(f"\n[yellow bold]🌅 FORGE GHOST — MORNING BRIEF[/yellow bold]")

    missions = Mission.load_all()
    alerts   = get_alerts(limit=10)

    missions_summary = "\n".join(
        f"  - {m.name} | target:{m.target} | runs:{m.run_count} | alerts:{m.alert_count} | next:{m.next_run[:16]}"
        for m in missions
    ) or "  No active missions."

    alerts_summary = "\n".join(
        f"  [{a['severity']}] {a['title']} — {a['ts'][:16]}"
        for a in alerts[:5]
    ) or "  No recent alerts."

    if not AI_AVAILABLE:
        brief = f"FORGE GHOST BRIEF — {datetime.now().strftime('%Y-%m-%d')}\n\n"
        brief += f"Active missions: {len(missions)}\n"
        brief += f"Recent alerts: {len(alerts)}\n"
        brief += missions_summary
    else:
        brief = ai_call(
            BRIEF_PROMPT.format(
                date             = datetime.now().strftime("%A, %B %d %Y"),
                n_missions       = len(missions),
                missions_summary = missions_summary,
                n_alerts         = len(alerts),
                alerts_summary   = alerts_summary,
            ),
            max_tokens=1000
        )

    rprint(Panel(brief, border_style="yellow", title="🌅 Morning Brief"))

    # Save
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    fp = BRIEFS_DIR / f"brief_{ts}.txt"
    fp.write_text(brief)

    # Send if configured
    cfg = cfg or load_config()
    if cfg.get("email_enabled") and cfg.get("email_to"):
        send_email(cfg, f"FORGE GHOST Brief — {datetime.now().strftime('%Y-%m-%d')}", brief)

    return brief

# ══════════════════════════════════════════════════════════════════════════════
# 📧 NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════

def send_email(cfg, subject, body):
    """Send email notification."""
    try:
        msg              = MIMEMultipart()
        msg["From"]      = cfg["email_from"]
        msg["To"]        = cfg["email_to"]
        msg["Subject"]   = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as s:
            s.starttls()
            s.login(cfg["email_from"], cfg["email_password"])
            s.send_message(msg)
        rprint(f"  [green]📧 Email sent to {cfg['email_to']}[/green]")
        return True
    except Exception as e:
        rprint(f"  [red]📧 Email failed: {e}[/red]")
        return False

def send_webhook(cfg, title, body, severity="INFO"):
    """Send webhook notification (Slack/Discord compatible)."""
    try:
        import urllib.request
        webhook = cfg.get("slack_webhook") or cfg.get("webhook_url")
        if not webhook: return False

        payload = json.dumps({
            "text": f"*[FORGE GHOST]* *{severity}*: {title}\n```{body[:500]}```"
        }).encode()
        req = urllib.request.Request(webhook, data=payload,
                                      headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
        rprint(f"  [green]🔔 Webhook sent[/green]")
        return True
    except Exception as e:
        rprint(f"  [red]🔔 Webhook failed: {e}[/red]")
        return False

# ══════════════════════════════════════════════════════════════════════════════
# ⚙️ GHOST ENGINE — the scheduler
# ══════════════════════════════════════════════════════════════════════════════

MISSION_RUNNERS = {
    "watch":   run_watch_mission,
    "osint":   run_osint_mission,
    "github":  run_github_mission,
    "domain":  run_domain_mission,
    "pentest": run_pentest_mission,
}

class GhostEngine:
    def __init__(self):
        self.running   = False
        self.cfg       = load_config()
        self._stop_evt = threading.Event()
        self._thread   = None

    def start(self, daemon=False):
        self.running = True
        self._stop_evt.clear()
        rprint(f"[yellow bold]👻 FORGE GHOST ENGINE STARTING[/yellow bold]")
        rprint(f"  Check interval: {self.cfg['check_interval']} min")
        rprint(f"  Morning brief:  {self.cfg['brief_time']}")
        rprint(f"  Notifications:  {'email' if self.cfg['email_enabled'] else 'file only'}")

        if daemon:
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
        else:
            self._run_loop()

    def stop(self):
        self.running = False
        self._stop_evt.set()
        rprint("[dim]Ghost engine stopping...[/dim]")

    def _run_loop(self):
        last_brief = ""

        while self.running and not self._stop_evt.is_set():
            now = datetime.now()

            # Morning brief
            brief_time = self.cfg.get("brief_time","08:00")
            today_brief= now.strftime("%Y-%m-%d") + brief_time
            if (now.strftime("%H:%M") == brief_time and
                    today_brief != last_brief):
                generate_morning_brief(self.cfg)
                last_brief = today_brief

            # Check missions due
            missions = Mission.load_all()
            for mission in missions:
                if not mission.next_run:
                    continue
                try:
                    next_run = datetime.fromisoformat(mission.next_run)
                except:
                    next_run = datetime.now()

                if now >= next_run:
                    self._run_mission(mission)

            # Sleep 60s between checks
            self._stop_evt.wait(60)

    def _run_mission(self, mission):
        runner = MISSION_RUNNERS.get(mission.mission_type, run_watch_mission)
        rprint(f"\n  [yellow]👻 Running mission:[/yellow] {mission.name} [{mission.mission_type}]")

        try:
            results = runner(mission)
            mission.schedule_next()

            # Check alerts and send notifications
            new_alerts = get_alerts(mission.id, limit=3)
            for alert in new_alerts[:1]:
                if not alert["sent"]:
                    if self.cfg.get("email_enabled"):
                        send_email(self.cfg, f"[FORGE GHOST] {alert['title']}", alert["body"])
                    if self.cfg.get("slack_webhook"):
                        send_webhook(self.cfg, alert["title"], alert["body"], alert["severity"])
                    # Mark as sent
                    conn = get_db()
                    conn.execute("UPDATE alerts SET sent=1 WHERE id=?", (alert["id"],))
                    conn.commit()
                    conn.close()

        except Exception as e:
            ghost_log(mission.id, f"Mission failed: {e}", "error")
            mission.schedule_next()

# ══════════════════════════════════════════════════════════════════════════════
# 🎮 INTERACTIVE CONSOLE
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ██████╗ ██╗  ██╗ ██████╗ ███████╗████████╗
 ██╔════╝ ██║  ██║██╔═══██╗██╔════╝╚══██╔══╝
 ██║  ███╗███████║██║   ██║███████╗   ██║
 ██║   ██║██╔══██║██║   ██║╚════██║   ██║
 ╚██████╔╝██║  ██║╚██████╔╝███████║   ██║
  ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝
[/yellow]
[bold]  👻 FORGE GHOST — Autonomous Intelligence Agent[/bold]
[dim]  Runs forever. Watches everything. Alerts on anything.[/dim]
"""

def show_missions():
    missions = Mission.load_all()
    if not missions:
        rprint("[dim]No active missions. Use 'add' to create one.[/dim]")
        return
    if RICH:
        t = Table(border_style="yellow", box=rbox.ROUNDED, title="Active Missions")
        t.add_column("ID",       style="dim",    width=12)
        t.add_column("Name",     style="yellow", width=22)
        t.add_column("Target",   style="cyan",   width=22)
        t.add_column("Type",     style="white",  width=10)
        t.add_column("Runs",     width=6)
        t.add_column("Alerts",   style="red",    width=8)
        t.add_column("Next Run", width=18)
        for m in missions:
            t.add_row(m.id, m.name[:21], m.target[:21], m.mission_type,
                      str(m.run_count), str(m.alert_count),
                      m.next_run[:16] if m.next_run else "—")
        console.print(t)

def show_alerts(limit=10):
    alerts = get_alerts(limit=limit)
    if not alerts:
        rprint("[dim]No alerts.[/dim]")
        return
    if RICH:
        t = Table(border_style="red", box=rbox.SIMPLE, title="Recent Alerts")
        t.add_column("Time",     style="dim",    width=18)
        t.add_column("Severity", width=10)
        t.add_column("Title",    style="white",  width=36)
        for a in alerts:
            sev_color = {"CRITICAL":"red bold","HIGH":"red","MEDIUM":"yellow","LOW":"dim"}.get(a["severity"],"white")
            t.add_row(a["ts"][:16], f"[{sev_color}]{a['severity']}[/{sev_color}]", a["title"][:35])
        console.print(t)

def interactive():
    rprint(BANNER)
    engine = GhostEngine()

    # Quick status
    missions = Mission.load_all()
    alerts   = get_alerts(limit=5)
    rprint(f"  [dim]Active missions: {len(missions)} | Recent alerts: {len(alerts)}[/dim]\n")
    rprint("[dim]Commands: add | missions | alerts | run <id> | brief | start | stop | config | help[/dim]\n")

    while True:
        try:
            inp = console.input if RICH else input
            raw = inp("[yellow bold]👻 ghost >[/yellow bold] ").strip()
            if not raw: continue

            parts = raw.split(None, 1)
            cmd   = parts[0].lower()
            args  = parts[1] if len(parts) > 1 else ""

            if cmd in ("quit","exit","q"):
                engine.stop()
                rprint("[dim]Ghost sleeping. Missions continue if --daemon was used.[/dim]")
                break

            elif cmd == "help":
                rprint("""
[bold yellow]FORGE GHOST Commands[/bold yellow]

  [yellow]add[/yellow]              Add a new mission (interactive)
  [yellow]missions[/yellow]         List all active missions
  [yellow]alerts[/yellow]           Show recent alerts
  [yellow]run[/yellow] <id>         Force-run a mission now
  [yellow]brief[/yellow]            Generate morning brief now
  [yellow]start[/yellow]            Start ghost engine (background)
  [yellow]stop[/yellow]             Stop ghost engine
  [yellow]config[/yellow]           Edit configuration
  [yellow]kill[/yellow] <id>        Deactivate a mission
  [yellow]logs[/yellow] <id>        Show mission logs
  [yellow]snapshot[/yellow] <id>    Show last snapshot
""")

            elif cmd == "add":
                rprint("\n[bold]Add Mission[/bold]")
                name   = (console.input if RICH else input)("  Name: ").strip()
                target = (console.input if RICH else input)("  Target: ").strip()
                rprint(f"  Types: {', '.join(MISSION_TYPES.keys())}")
                mtype  = (console.input if RICH else input)("  Type [watch]: ").strip() or "watch"
                intv   = (console.input if RICH else input)("  Interval minutes [360]: ").strip()
                interval = int(intv) if intv.isdigit() else 360

                m = Mission(name, target, mtype, interval)
                m.save()
                rprint(f"  [green]Mission created: {m.id}[/green]")
                rprint(f"  [dim]{mtype}: {target} every {interval} min[/dim]")

            elif cmd == "missions":
                show_missions()

            elif cmd == "alerts":
                show_alerts()

            elif cmd == "run":
                if not args:
                    show_missions()
                    args = (console.input if RICH else input)("Mission ID: ").strip()
                m = Mission.get(args.strip())
                if not m:
                    rprint(f"[red]Mission not found: {args}[/red]"); continue
                rprint(f"[yellow]Force-running: {m.name}[/yellow]")
                runner = MISSION_RUNNERS.get(m.mission_type, run_watch_mission)
                runner(m)
                m.schedule_next()
                rprint(f"[green]Done. Next run: {m.next_run[:16]}[/green]")

            elif cmd == "brief":
                generate_morning_brief()

            elif cmd == "start":
                rprint("[yellow]Starting ghost engine in background...[/yellow]")
                engine.start(daemon=True)
                rprint("[green]Ghost engine running. Type 'stop' to halt.[/green]")

            elif cmd == "stop":
                engine.stop()

            elif cmd == "kill":
                conn = get_db()
                conn.execute("UPDATE missions SET status='inactive' WHERE id=?", (args,))
                conn.commit(); conn.close()
                rprint(f"[yellow]Mission {args} deactivated.[/yellow]")

            elif cmd == "logs":
                if not args:
                    args = (console.input if RICH else input)("Mission ID: ").strip()
                log_file = LOGS_DIR / f"{args}.log"
                if log_file.exists():
                    lines = log_file.read_text().splitlines()[-30:]
                    for line in lines:
                        rprint(f"  [dim]{line}[/dim]")
                else:
                    rprint("[dim]No logs yet.[/dim]")

            elif cmd == "snapshot":
                if not args:
                    args = (console.input if RICH else input)("Mission ID: ").strip()
                snap = get_last_snapshot(args)
                if snap:
                    rprint(f"  [dim]Time: {snap['ts'][:16]}[/dim]")
                    rprint(f"  [dim]Changed: {'yes' if snap['changed'] else 'no'}[/dim]")
                    data = json.loads(snap["data"])
                    rprint(json.dumps(data, indent=2, default=str)[:600])
                else:
                    rprint("[dim]No snapshot yet.[/dim]")

            elif cmd == "config":
                cfg = load_config()
                rprint(Panel(json.dumps(cfg, indent=2), title="Current Config"))
                key = (console.input if RICH else input)("Key to update (Enter to skip): ").strip()
                if key and key in cfg:
                    val = (console.input if RICH else input)(f"New value for {key}: ").strip()
                    # Type coerce
                    if isinstance(cfg[key], bool):
                        cfg[key] = val.lower() in ("true","1","yes")
                    elif isinstance(cfg[key], int):
                        try: cfg[key] = int(val)
                        except: pass
                    else:
                        cfg[key] = val
                    save_config(cfg)
                    rprint(f"[green]Config updated: {key} = {cfg[key]}[/green]")

            else:
                if AI_AVAILABLE:
                    ctx = f"Active missions: {len(Mission.load_all())}. Recent alerts: {len(get_alerts(limit=3))}."
                    result = ai_call(f"Ghost context: {ctx}\n\nUser: {raw}", max_tokens=300)
                    rprint(f"\n[yellow]👻[/yellow] {result}")
                else:
                    rprint("[dim]Unknown command. Type 'help'.[/dim]")

        except (KeyboardInterrupt, EOFError):
            engine.stop()
            rprint("\n[dim]Ghost sleeping.[/dim]")
            break

def main():
    if "--list" in sys.argv or "--missions" in sys.argv:
        rprint(BANNER)
        show_missions()
        return

    if "--status" in sys.argv:
        rprint(BANNER)
        show_missions()
        show_alerts(5)
        return

    if "--brief" in sys.argv:
        rprint(BANNER)
        generate_morning_brief()
        return

    if "--daemon" in sys.argv:
        rprint(BANNER)
        engine = GhostEngine()
        rprint("[yellow]Running as daemon. Ctrl+C to stop.[/yellow]")
        def handler(sig, frame):
            engine.stop(); sys.exit(0)
        signal.signal(signal.SIGINT, handler)
        engine.start(daemon=False)
        return

    if "--mission" in sys.argv:
        idx    = sys.argv.index("--mission")
        target = sys.argv[idx+1] if idx+1 < len(sys.argv) else ""
        if target:
            mtype = sys.argv[idx+2] if idx+2 < len(sys.argv) else "watch"
            m = Mission(f"CLI: {target}", target, mtype)
            m.save()
            rprint(BANNER)
            rprint(f"[green]Mission added: {m.id} — {target} [{mtype}][/green]")
        return

    interactive()

if __name__ == "__main__":
    main()
