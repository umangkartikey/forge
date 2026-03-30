"""
FORGE Orchestrator — forge_orchestrator.py
==========================================
Master orchestrator — one command starts everything.
One dashboard shows everything. One API receives everything.

Architecture:
  ModuleRegistry      → knows all modules, ports, health status
  PipelineRouter      → routes signals through modules in correct order
  HealthMonitor       → pings all modules, auto-restarts dead ones
  SignalIngestion     → single entry point for all incoming signals
  ResponseAggregator  → collects outputs into unified response
  OrchestratorMemory  → remembers pipeline decisions and outcomes
  MasterDashboard     → live Rich UI showing ALL modules simultaneously

Pipeline flow:
  signal → temporal (perceive)
         → bridge   (enrich with social history)
         → prefrontal (decide)
         → hippocampus (remember)
         → swarm    (act collectively)
         → unified response
"""

import json
import time
import uuid
import sqlite3
import threading
import subprocess
import sys
import os
import signal as os_signal
from datetime import datetime
from collections import deque, defaultdict
from typing import Optional
from dataclasses import dataclass, field

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.layout import Layout
    from rich.text import Text
    from rich.live import Live
    from rich.columns import Columns
    from rich.rule import Rule
    from rich.align import Align
    from rich.spinner import Spinner
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

try:
    from flask import Flask, request, jsonify
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

# ─── Constants ────────────────────────────────────────────────────────────────

DB_PATH       = "forge_orchestrator.db"
ORCH_PORT     = 7777   # master entry point
VERSION       = "1.0.0"
HEALTH_INTERVAL = 10   # seconds between health checks
REQUEST_TIMEOUT = 5    # seconds per module call
MAX_RETRIES   = 2

console = Console() if HAS_RICH else None

# ─── Module Registry ──────────────────────────────────────────────────────────

MODULES = {
    "temporal": {
        "name":    "forge_temporal",
        "port":    7778,
        "file":    "forge_temporal.py",
        "emoji":   "🧠",
        "color":   "cyan",
        "role":    "Perception",
        "endpoints": {
            "perceive": "/perceive",
            "status":   "/status",
            "events":   "/events",
        }
    },
    "bridge": {
        "name":    "forge_bridge",
        "port":    7781,
        "file":    "forge_bridge.py",
        "emoji":   "🔗",
        "color":   "blue",
        "role":    "Social Bridge",
        "endpoints": {
            "sync":   "/sync",
            "status": "/stats",
            "graph":  "/graph",
        }
    },
    "prefrontal": {
        "name":    "forge_prefrontal",
        "port":    7779,
        "file":    "forge_prefrontal.py",
        "emoji":   "👔",
        "color":   "magenta",
        "role":    "Decision",
        "endpoints": {
            "think":    "/think",
            "status":   "/status",
            "decisions":"/decisions",
        }
    },
    "hippocampus": {
        "name":    "forge_hippocampus",
        "port":    7780,
        "file":    "forge_hippocampus.py",
        "emoji":   "📚",
        "color":   "green",
        "role":    "Memory",
        "endpoints": {
            "remember": "/remember",
            "recall":   "/recall",
            "status":   "/status",
        }
    },
    "swarm": {
        "name":    "forge_swarm_v2",
        "port":    7782,
        "file":    "forge_swarm_v2.py",
        "emoji":   "🐝",
        "color":   "yellow",
        "role":    "Swarm Action",
        "endpoints": {
            "signal": "/signal",
            "status": "/status",
            "agents": "/agents",
        }
    },
}

# Pipeline order — signals flow through these in sequence
PIPELINE_ORDER = ["temporal", "bridge", "prefrontal", "hippocampus", "swarm"]

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class ModuleHealth:
    module_id:   str   = ""
    alive:       bool  = False
    latency_ms:  float = 0.0
    last_ping:   str   = ""
    last_error:  str   = ""
    ping_count:  int   = 0
    fail_count:  int   = 0
    uptime_pct:  float = 100.0

@dataclass
class PipelineResult:
    id:          str  = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:   str  = field(default_factory=lambda: datetime.now().isoformat())
    input_signal: dict = field(default_factory=dict)
    steps:       list = field(default_factory=list)   # per-module results
    final:       dict = field(default_factory=dict)   # aggregated response
    total_ms:    float = 0.0
    success:     bool  = True
    threat:      int   = 0
    conclusion:  str   = ""
    modules_hit: list  = field(default_factory=list)
    modules_skipped: list = field(default_factory=list)

@dataclass
class PipelineStep:
    module:      str   = ""
    endpoint:    str   = ""
    success:     bool  = False
    latency_ms:  float = 0.0
    response:    dict  = field(default_factory=dict)
    error:       str   = ""
    enriched:    bool  = False  # did this step enrich the signal?

# ─── Database ─────────────────────────────────────────────────────────────────

class OrchestratorDB:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init()

    def _init(self):
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS pipeline_results (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    input_signal TEXT, steps TEXT, final TEXT,
                    total_ms REAL, success INTEGER, threat INTEGER,
                    conclusion TEXT, modules_hit TEXT, modules_skipped TEXT
                );
                CREATE TABLE IF NOT EXISTS module_health (
                    module_id TEXT PRIMARY KEY, alive INTEGER,
                    latency_ms REAL, last_ping TEXT, last_error TEXT,
                    ping_count INTEGER, fail_count INTEGER, uptime_pct REAL
                );
                CREATE TABLE IF NOT EXISTS orchestrator_log (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    event_type TEXT, module TEXT, details TEXT
                );
            """)
            self.conn.commit()

    def save_result(self, r: PipelineResult):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO pipeline_results VALUES
                (?,?,?,?,?,?,?,?,?,?,?)
            """, (r.id, r.timestamp, json.dumps(r.input_signal),
                  json.dumps([s.__dict__ for s in r.steps]),
                  json.dumps(r.final), r.total_ms, int(r.success),
                  r.threat, r.conclusion,
                  json.dumps(r.modules_hit), json.dumps(r.modules_skipped)))
            self.conn.commit()

    def save_health(self, h: ModuleHealth):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO module_health VALUES (?,?,?,?,?,?,?,?)
            """, (h.module_id, int(h.alive), h.latency_ms,
                  h.last_ping, h.last_error,
                  h.ping_count, h.fail_count, h.uptime_pct))
            self.conn.commit()

    def log(self, event_type: str, module: str, details: dict):
        with self.lock:
            self.conn.execute(
                "INSERT INTO orchestrator_log VALUES (?,?,?,?,?)",
                (str(uuid.uuid4())[:8], datetime.now().isoformat(),
                 event_type, module, json.dumps(details))
            )
            self.conn.commit()

    def get_results(self, limit=20):
        with self.lock:
            return self.conn.execute("""
                SELECT id, timestamp, total_ms, success, threat,
                       conclusion, modules_hit
                FROM pipeline_results ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()

# ─── HTTP Client ──────────────────────────────────────────────────────────────

class ModuleClient:
    """Thin HTTP client for calling FORGE modules."""

    def __init__(self, db: OrchestratorDB):
        self.db      = db
        self.session = None
        if HAS_REQUESTS:
            self.session = requests.Session()

    def _url(self, module_id: str, endpoint_key: str) -> str:
        mod  = MODULES[module_id]
        path = mod["endpoints"].get(endpoint_key, "/status")
        return f"http://127.0.0.1:{mod['port']}{path}"

    def post(self, module_id: str, endpoint_key: str,
             payload: dict, timeout: int = REQUEST_TIMEOUT) -> tuple[bool, dict, float]:
        """POST to a module. Returns (success, response, latency_ms)."""
        if not HAS_REQUESTS:
            return False, {"error": "requests not installed"}, 0.0

        url = self._url(module_id, endpoint_key)
        t0  = time.time()
        try:
            r = self.session.post(url, json=payload, timeout=timeout)
            latency = (time.time() - t0) * 1000
            if r.status_code == 200:
                return True, r.json(), latency
            return False, {"error": f"HTTP {r.status_code}"}, latency
        except requests.exceptions.ConnectionError:
            latency = (time.time() - t0) * 1000
            return False, {"error": "CONNECTION_REFUSED"}, latency
        except requests.exceptions.Timeout:
            latency = (time.time() - t0) * 1000
            return False, {"error": "TIMEOUT"}, latency
        except Exception as e:
            latency = (time.time() - t0) * 1000
            return False, {"error": str(e)}, latency

    def get(self, module_id: str, endpoint_key: str,
            timeout: int = REQUEST_TIMEOUT) -> tuple[bool, dict, float]:
        """GET from a module."""
        if not HAS_REQUESTS:
            return False, {"error": "requests not installed"}, 0.0

        url = self._url(module_id, endpoint_key)
        t0  = time.time()
        try:
            r = self.session.get(url, timeout=timeout)
            latency = (time.time() - t0) * 1000
            if r.status_code == 200:
                return True, r.json(), latency
            return False, {"error": f"HTTP {r.status_code}"}, latency
        except Exception as e:
            latency = (time.time() - t0) * 1000
            return False, {"error": str(e)}, latency

    def ping(self, module_id: str) -> tuple[bool, float]:
        ok, _, latency = self.get(module_id, "status", timeout=2)
        return ok, latency


# ─── Health Monitor ───────────────────────────────────────────────────────────

class HealthMonitor:
    """
    Continuously pings all modules.
    Tracks uptime, latency, failures.
    Triggers restart if a module goes down.
    """

    def __init__(self, client: ModuleClient, db: OrchestratorDB):
        self.client  = client
        self.db      = db
        self.health: dict[str, ModuleHealth] = {
            mid: ModuleHealth(module_id=mid) for mid in MODULES
        }
        self._running = False
        self._thread  = None
        self._processes: dict[str, subprocess.Popen] = {}

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            for mid in MODULES:
                self._ping(mid)
            time.sleep(HEALTH_INTERVAL)

    def _ping(self, module_id: str):
        h = self.health[module_id]
        ok, latency = self.client.ping(module_id)
        h.ping_count += 1
        h.last_ping   = datetime.now().isoformat()
        h.latency_ms  = round(latency, 1)

        if ok:
            h.alive      = True
            h.last_error = ""
        else:
            h.alive      = False
            h.fail_count += 1
            h.last_error  = "unreachable"

        h.uptime_pct = round(
            (h.ping_count - h.fail_count) / h.ping_count * 100, 1
        ) if h.ping_count > 0 else 0.0

        self.db.save_health(h)

    def launch_module(self, module_id: str) -> bool:
        """Launch a FORGE module as a subprocess."""
        mod      = MODULES[module_id]
        filepath = mod["file"]

        if not os.path.exists(filepath):
            self.db.log("LAUNCH_FAILED", module_id,
                       {"reason": f"{filepath} not found"})
            return False

        try:
            proc = subprocess.Popen(
                [sys.executable, filepath, "--api"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            self._processes[module_id] = proc
            time.sleep(1.5)  # give module time to start
            ok, _ = self.client.ping(module_id)
            self.db.log("LAUNCH", module_id,
                       {"pid": proc.pid, "success": ok})
            return ok
        except Exception as e:
            self.db.log("LAUNCH_ERROR", module_id, {"error": str(e)})
            return False

    def launch_all(self) -> dict[str, bool]:
        """Launch all FORGE modules."""
        results = {}
        for mid in PIPELINE_ORDER:
            results[mid] = self.launch_module(mid)
            time.sleep(0.5)
        return results

    def shutdown_all(self):
        """Gracefully shut down all launched modules."""
        for mid, proc in self._processes.items():
            try:
                proc.terminate()
                self.db.log("SHUTDOWN", mid, {"pid": proc.pid})
            except Exception:
                pass

    def get_summary(self) -> dict:
        alive = sum(1 for h in self.health.values() if h.alive)
        return {
            "total":   len(MODULES),
            "alive":   alive,
            "dead":    len(MODULES) - alive,
            "modules": {
                mid: {
                    "alive":      h.alive,
                    "latency_ms": h.latency_ms,
                    "uptime_pct": h.uptime_pct,
                    "fail_count": h.fail_count
                }
                for mid, h in self.health.items()
            }
        }


# ─── Pipeline Router ──────────────────────────────────────────────────────────

class PipelineRouter:
    """
    Routes signals through FORGE modules in the correct order.
    Each step enriches the signal before passing to the next module.
    Skips unavailable modules gracefully.
    """

    def __init__(self, client: ModuleClient,
                 health: HealthMonitor, db: OrchestratorDB):
        self.client = client
        self.health = health
        self.db     = db

    def route(self, raw_signal: dict) -> PipelineResult:
        result    = PipelineResult(input_signal=raw_signal)
        t0        = time.time()
        signal    = dict(raw_signal)  # working copy — enriched at each step

        for module_id in PIPELINE_ORDER:
            mod_health = self.health.health[module_id]

            if not mod_health.alive:
                result.modules_skipped.append(module_id)
                step = PipelineStep(
                    module=module_id, endpoint="SKIPPED",
                    success=False, error="MODULE_OFFLINE"
                )
                result.steps.append(step)
                continue

            # Route to correct endpoint per module
            step = self._call_module(module_id, signal)
            result.steps.append(step)
            result.modules_hit.append(module_id)

            # Enrich working signal with module response
            if step.success and step.response:
                signal = self._enrich(signal, module_id, step.response)
                step.enriched = True

        # Aggregate final response
        result.final       = self._aggregate(result.steps, signal)
        result.total_ms    = round((time.time() - t0) * 1000, 1)
        result.success     = any(s.success for s in result.steps)
        result.threat      = signal.get("threat", raw_signal.get("threat", 0))
        result.conclusion  = signal.get("conclusion",
                             result.final.get("conclusion", "Pipeline complete."))

        self.db.save_result(result)
        return result

    def _call_module(self, module_id: str, signal: dict) -> PipelineStep:
        """Call the right endpoint for each module."""
        endpoint_map = {
            "temporal":    ("perceive",  {"text": signal.get("text", signal.get("conclusion","")),
                                          "visual_input":   signal.get("visual_input",""),
                                          "auditory_input": signal.get("auditory_input",""),
                                          "entity_name":    signal.get("entity_name","unknown")}),
            "bridge":      ("sync",      {"perception": signal}),
            "prefrontal":  ("think",     {"perception": signal}),
            "hippocampus": ("remember",  {"perception": signal,
                                          "decision":   signal.get("decision",{})}),
            "swarm":       ("signal",    signal),
        }

        if module_id not in endpoint_map:
            return PipelineStep(module=module_id, error="NO_ENDPOINT_MAP")

        endpoint_key, payload = endpoint_map[module_id]
        ok, response, latency = self.client.post(
            module_id, endpoint_key, payload
        )

        return PipelineStep(
            module=module_id, endpoint=endpoint_key,
            success=ok, latency_ms=round(latency, 1),
            response=response if ok else {},
            error="" if ok else response.get("error", "UNKNOWN")
        )

    def _enrich(self, signal: dict, module_id: str, response: dict) -> dict:
        """Each module's response enriches the signal for downstream modules."""
        enriched = dict(signal)

        if module_id == "temporal":
            # temporal adds perception fields
            enriched["threat"]     = response.get("threat", signal.get("threat", 0))
            enriched["anomaly"]    = response.get("anomaly", False)
            enriched["conclusion"] = response.get("conclusion", signal.get("conclusion",""))
            enriched["emotional"]  = response.get("emotional", {})
            enriched["social"]     = response.get("social", {})
            enriched["semantic"]   = response.get("semantic", {})
            enriched["visual"]     = response.get("visual", {})
            enriched["auditory"]   = response.get("auditory", {})
            enriched["temporal_id"]= response.get("id", "")

        elif module_id == "bridge":
            # bridge enriches threat with social history
            enriched["threat"]         = response.get("enriched_threat",
                                          signal.get("threat", 0))
            enriched["conclusion"]     = response.get("conclusion",
                                          signal.get("conclusion",""))
            enriched["social_context"] = response.get("social_context", {})

        elif module_id == "prefrontal":
            # prefrontal adds decision
            chosen = response.get("chosen", {})
            enriched["decision"]       = chosen
            enriched["reasoning"]      = response.get("reasoning", "")
            enriched["prefrontal_plan"]= response.get("plan", [])

        elif module_id == "hippocampus":
            # hippocampus adds memory metadata
            enriched["memory_action"]  = response.get("action", "")
            enriched["episode_id"]     = response.get("episode_id", "")
            enriched["novelty"]        = response.get("novelty", 1.0)
            enriched["importance"]     = response.get("importance", 0.5)

        elif module_id == "swarm":
            # swarm adds collective action
            enriched["swarm_phase"]    = response.get("phase_after", "CALM")
            enriched["swarm_consensus"]= response.get("consensus", {})
            enriched["swarm_alive"]    = response.get("alive_agents", 0)

        return enriched

    def _aggregate(self, steps: list[PipelineStep], final_signal: dict) -> dict:
        """Aggregate all module outputs into one unified response."""
        successful = [s for s in steps if s.success]
        failed     = [s for s in steps if not s.success]

        # Collect key outputs per module
        outputs = {}
        for step in steps:
            if step.success and step.response:
                outputs[step.module] = step.response

        return {
            "pipeline_complete":   True,
            "modules_succeeded":   [s.module for s in successful],
            "modules_failed":      [s.module for s in failed],
            "threat":              final_signal.get("threat", 0),
            "conclusion":          final_signal.get("conclusion", ""),
            "decision":            final_signal.get("decision", {}),
            "reasoning":           final_signal.get("reasoning", ""),
            "social_context":      final_signal.get("social_context", {}),
            "memory_action":       final_signal.get("memory_action", ""),
            "novelty":             final_signal.get("novelty", 1.0),
            "swarm_phase":         final_signal.get("swarm_phase", "CALM"),
            "swarm_consensus":     final_signal.get("swarm_consensus", {}),
            "total_latency_hint":  sum(s.latency_ms for s in steps),
            "enriched_signal":     final_signal
        }


# ─── Response Aggregator ─────────────────────────────────────────────────────

class ResponseAggregator:
    """
    Turns raw PipelineResult into a clean, human-readable unified response.
    The single voice of FORGE.
    """

    def summarize(self, result: PipelineResult) -> dict:
        threat = result.threat
        return {
            "id":              result.id,
            "timestamp":       result.timestamp,
            "threat_level":    threat,
            "threat_label":    {0:"NONE",1:"LOW",2:"MEDIUM",
                                3:"HIGH",4:"CRITICAL"}.get(threat,"UNKNOWN"),
            "conclusion":      result.conclusion,
            "decision":        result.final.get("decision", {}).get("action", "STANDBY"),
            "reasoning":       result.final.get("reasoning","")[:120],
            "memory_action":   result.final.get("memory_action",""),
            "novelty":         result.final.get("novelty", 1.0),
            "swarm_phase":     result.final.get("swarm_phase","CALM"),
            "pipeline_ms":     result.total_ms,
            "modules_hit":     result.modules_hit,
            "modules_skipped": result.modules_skipped,
            "success":         result.success
        }


# ─── Orchestrator Memory ─────────────────────────────────────────────────────

class OrchestratorMemory:
    """Remembers pipeline decisions — the orchestrator's own history."""

    def __init__(self, capacity: int = 500):
        self.history:    deque = deque(maxlen=capacity)
        self.stats       = defaultdict(int)
        self.threat_log: deque = deque(maxlen=100)

    def record(self, result: PipelineResult):
        self.history.append({
            "id":        result.id,
            "timestamp": result.timestamp,
            "threat":    result.threat,
            "success":   result.success,
            "ms":        result.total_ms,
            "modules":   result.modules_hit
        })
        self.stats["total"]  += 1
        self.stats["success"]+= int(result.success)
        self.stats[f"threat_{result.threat}"] += 1
        self.threat_log.append(result.threat)

    def avg_threat(self) -> float:
        if not self.threat_log: return 0.0
        return round(sum(self.threat_log) / len(self.threat_log), 2)

    def threat_trend(self) -> str:
        if len(self.threat_log) < 4: return "STABLE"
        recent = list(self.threat_log)[-4:]
        if recent[-1] > recent[0]:   return "ESCALATING ↑"
        if recent[-1] < recent[0]:   return "DE-ESCALATING ↓"
        return "STABLE →"

    def summary(self) -> dict:
        return {
            "total_signals":  self.stats["total"],
            "success_rate":   round(self.stats["success"] / max(self.stats["total"],1), 2),
            "avg_threat":     self.avg_threat(),
            "threat_trend":   self.threat_trend(),
            "recent":         list(self.history)[-5:]
        }


# ─── Master Dashboard ─────────────────────────────────────────────────────────

class MasterDashboard:
    """
    Live Rich UI showing ALL modules simultaneously.
    Updates in real-time as signals flow through the pipeline.
    """

    def __init__(self, health: HealthMonitor,
                 memory: OrchestratorMemory):
        self.health = health
        self.memory = memory
        self.last_result: Optional[PipelineResult] = None
        self.tick = 0

    def render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header",  size=4),
            Layout(name="middle"),
            Layout(name="bottom",  size=12)
        )
        layout["middle"].split_row(
            Layout(name="modules", ratio=2),
            Layout(name="pipeline",ratio=3)
        )

        layout["header"].update(self._header())
        layout["modules"].update(self._module_grid())
        layout["pipeline"].update(self._pipeline_view())
        layout["bottom"].update(self._bottom_row())
        return layout

    def _header(self) -> Panel:
        mem = self.memory.summary()
        trend_color = "red" if "ESCAL" in mem["threat_trend"] else \
                      "green" if "DE-ESC" in mem["threat_trend"] else "yellow"
        return Panel(
            Align.center(
                Text(
                    f"⬡ FORGE ORCHESTRATOR v{VERSION}  |  "
                    f"Signals: {mem['total_signals']}  |  "
                    f"Avg Threat: {mem['avg_threat']}  |  "
                    f"Trend: {mem['threat_trend']}  |  "
                    f"{datetime.now().strftime('%H:%M:%S')}",
                    style="bold cyan"
                )
            ),
            border_style="cyan"
        )

    def _module_grid(self) -> Panel:
        t = Table(box=box.SIMPLE, show_header=True, expand=True)
        t.add_column("Module",  style="bold", width=14)
        t.add_column("Status",  width=8)
        t.add_column("Latency", justify="right", width=9)
        t.add_column("Uptime",  justify="right", width=8)

        for mid in PIPELINE_ORDER:
            mod = MODULES[mid]
            h   = self.health.health[mid]
            status_text = "[green]● LIVE[/green]" if h.alive else "[red]○ DOWN[/red]"
            lat_color   = "green" if h.latency_ms < 100 else \
                          "yellow" if h.latency_ms < 500 else "red"
            t.add_row(
                f"[{mod['color']}]{mod['emoji']} {mod['name']}[/{mod['color']}]",
                status_text,
                f"[{lat_color}]{h.latency_ms:.0f}ms[/{lat_color}]" if h.alive else "[dim]—[/dim]",
                f"{h.uptime_pct:.0f}%" if h.ping_count > 0 else "[dim]—[/dim]"
            )
        return Panel(t, title="[bold]MODULE REGISTRY[/bold]", border_style="dim")

    def _pipeline_view(self) -> Panel:
        if not self.last_result:
            return Panel(
                Align.center(Text("Waiting for first signal...", style="dim")),
                title="[bold]LAST PIPELINE RUN[/bold]", border_style="dim"
            )

        r = self.last_result
        threat_color = {0:"green",1:"blue",2:"yellow",
                        3:"red",4:"bright_red"}.get(r.threat,"white")

        lines = []
        lines.append(f"[dim]Signal ID: {r.id}  |  {r.timestamp[:19]}[/dim]")
        lines.append(f"[{threat_color}]Threat: {r.threat}  |  {r.conclusion[:60]}[/{threat_color}]")
        lines.append("")

        # Pipeline flow visualization
        for step in r.steps:
            mod     = MODULES.get(step.module, {})
            emoji   = mod.get("emoji","◈")
            color   = mod.get("color","white")
            if step.success:
                lines.append(
                    f"  [{color}]{emoji} {step.module:<12}[/{color}]  "
                    f"[green]✓[/green]  [dim]{step.latency_ms:.0f}ms[/dim]"
                )
            elif step.error == "MODULE_OFFLINE":
                lines.append(
                    f"  [dim]◌ {step.module:<12}[/dim]  "
                    f"[dim]— OFFLINE[/dim]"
                )
            else:
                lines.append(
                    f"  [red]✗ {step.module:<12}[/red]  "
                    f"[red]{step.error[:20]}[/red]"
                )

        lines.append("")
        lines.append(f"[dim]Total: {r.total_ms:.0f}ms  |  "
                     f"Hit: {len(r.modules_hit)}  |  "
                     f"Skipped: {len(r.modules_skipped)}[/dim]")

        decision = r.final.get("decision", {})
        if decision:
            action = decision.get("action","?") if isinstance(decision,dict) else str(decision)
            lines.append(f"\n[bold]Decision: [magenta]{action}[/magenta][/bold]")
            reasoning = r.final.get("reasoning","")
            if reasoning:
                lines.append(f"[dim]{reasoning[:80]}[/dim]")

        return Panel(
            "\n".join(lines),
            title="[bold]LAST PIPELINE RUN[/bold]",
            border_style=threat_color
        )

    def _bottom_row(self) -> Panel:
        mem = self.memory.summary()
        t   = Table(box=box.SIMPLE, show_header=False, expand=True)
        t.add_column("k", style="dim", width=20)
        t.add_column("v")

        recent_threats = [str(e["threat"]) for e in mem["recent"]]
        threat_bar = " ".join(
            f"[{'red' if int(x)>=3 else 'yellow' if int(x)>=2 else 'green'}]{x}[/]"
            for x in recent_threats
        )

        t.add_row("Total Signals",   str(mem["total_signals"]))
        t.add_row("Success Rate",    f"{mem['success_rate']:.0%}")
        t.add_row("Avg Threat",      str(mem["avg_threat"]))
        t.add_row("Threat Trend",    mem["threat_trend"])
        t.add_row("Recent Threats",  threat_bar or "[dim]none yet[/dim]")

        health_summary = self.health.get_summary()
        t.add_row("Modules Alive",
                  f"[green]{health_summary['alive']}[/green]/"
                  f"{health_summary['total']}")

        return Panel(t, title="[bold]ORCHESTRATOR MEMORY[/bold]", border_style="dim")


# ─── FORGE Orchestrator ───────────────────────────────────────────────────────

class ForgeOrchestrator:
    def __init__(self, auto_launch: bool = False):
        self.db          = OrchestratorDB()
        self.client      = ModuleClient(self.db)
        self.health_mon  = HealthMonitor(self.client, self.db)
        self.router      = PipelineRouter(self.client, self.health_mon, self.db)
        self.aggregator  = ResponseAggregator()
        self.memory      = OrchestratorMemory()
        self.dashboard   = MasterDashboard(self.health_mon, self.memory)
        self.results:    list[PipelineResult] = []
        self._running    = False

        # Start health monitor
        self.health_mon.start()

        # Optionally launch all modules
        if auto_launch:
            self._launch_all()

        # Initial health sweep
        self._initial_health_check()

    def _launch_all(self):
        if HAS_RICH:
            console.print("[cyan]Launching FORGE modules...[/cyan]")
        results = self.health_mon.launch_all()
        for mid, ok in results.items():
            mod = MODULES[mid]
            status = "[green]✓ started[/green]" if ok else "[red]✗ failed[/red]"
            if HAS_RICH:
                console.print(f"  {mod['emoji']} {mod['name']}: {status}")

    def _initial_health_check(self):
        """Quick health check of all modules."""
        for mid in MODULES:
            self.health_mon._ping(mid)

    def process(self, signal: dict) -> dict:
        """
        Main entry point — run a signal through the full FORGE pipeline.
        Returns unified response.
        """
        result = self.router.route(signal)
        self.memory.record(result)
        self.dashboard.last_result = result
        self.results.append(result)
        self.dashboard.tick += 1

        summary = self.aggregator.summarize(result)
        self.db.log("PIPELINE_COMPLETE", "orchestrator",
                   {"id": result.id, "threat": result.threat,
                    "ms": result.total_ms, "modules": result.modules_hit})
        return summary

    def get_status(self) -> dict:
        health  = self.health_mon.get_summary()
        memory  = self.memory.summary()
        return {
            "version":       VERSION,
            "total_signals": len(self.results),
            "health":        health,
            "memory":        memory,
            "pipeline_order":PIPELINE_ORDER
        }

    def shutdown(self):
        self.health_mon.stop()
        self.health_mon.shutdown_all()
        self.db.log("SHUTDOWN", "orchestrator", {"total": len(self.results)})


# ─── Rich UI ──────────────────────────────────────────────────────────────────

def render_pipeline_result(result: PipelineResult, idx: int):
    if not HAS_RICH:
        print(f"\n[{idx}] threat={result.threat} | "
              f"modules={result.modules_hit} | {result.total_ms:.0f}ms")
        return

    threat       = result.threat
    threat_color = {0:"green",1:"blue",2:"yellow",
                    3:"red",4:"bright_red"}.get(threat,"white")

    console.print(Rule(
        f"[bold cyan]⬡ FORGE PIPELINE[/bold cyan]  "
        f"[dim]#{idx}  {result.id}  {result.timestamp[:19]}[/dim]"
    ))

    # Pipeline flow
    flow_parts = []
    for step in result.steps:
        mod   = MODULES.get(step.module, {})
        emoji = mod.get("emoji","◈")
        color = mod.get("color","white")
        if step.success:
            flow_parts.append(f"[{color}]{emoji}{step.module}[/{color}][dim]({step.latency_ms:.0f}ms)[/dim]")
        elif step.error == "MODULE_OFFLINE":
            flow_parts.append(f"[dim]◌{step.module}[/dim]")
        else:
            flow_parts.append(f"[red]✗{step.module}[/red]")

    console.print("  " + " → ".join(flow_parts))

    # Results panels
    left_lines = [
        f"[bold]Threat:[/bold]     [{threat_color}]{threat}[/{threat_color}]",
        f"[bold]Total time:[/bold] {result.total_ms:.0f}ms",
        f"[bold]Hit:[/bold]        {', '.join(result.modules_hit) or 'none'}",
        f"[bold]Skipped:[/bold]    {', '.join(result.modules_skipped) or 'none'}",
    ]
    if result.final.get("memory_action"):
        left_lines.append(f"[bold]Memory:[/bold]     {result.final['memory_action']}")
    if result.final.get("novelty") is not None:
        left_lines.append(f"[bold]Novelty:[/bold]    {result.final['novelty']:.2f}")
    if result.final.get("swarm_phase"):
        left_lines.append(f"[bold]Swarm:[/bold]      {result.final['swarm_phase']}")

    right_lines = []
    decision = result.final.get("decision", {})
    if decision:
        action = decision.get("action","?") if isinstance(decision,dict) else str(decision)
        right_lines.append(f"[bold]Action:[/bold] [magenta]{action}[/magenta]")
    reasoning = result.final.get("reasoning","")
    if reasoning:
        right_lines.append(f"[dim]{reasoning[:100]}[/dim]")
    social = result.final.get("social_context",{})
    if social:
        right_lines.append(f"[bold]Social:[/bold] risk={social.get('risk_label','?')} "
                          f"trust={social.get('trust_score','?')}")
        notes = social.get("enrichment_notes",[])
        if notes:
            right_lines.append(f"[dim]{notes[0][:60]}[/dim]")

    console.print(Columns([
        Panel("\n".join(left_lines), title="[bold]Pipeline Metrics[/bold]",
              border_style="dim"),
        Panel("\n".join(right_lines) or "[dim]No decision data[/dim]",
              title="[bold]Intelligence Output[/bold]", border_style=threat_color)
    ]))

    console.print(Panel(
        Text(result.conclusion[:140], style=f"bold {threat_color}"),
        title=f"[bold {threat_color}]CONCLUSION — THREAT {threat}[/bold {threat_color}]",
        border_style=threat_color
    ))


def run_demo(live_modules: bool = False):
    """
    Demo mode — shows the orchestrator working.
    If live_modules=True, tries to call real module APIs.
    Otherwise shows pipeline routing with graceful offline handling.
    """
    if HAS_RICH:
        console.print(Panel.fit(
            "[bold cyan]FORGE ORCHESTRATOR[/bold cyan]\n"
            "[dim]One command. One dashboard. One API.[/dim]\n"
            f"[dim]Version {VERSION}  |  {len(MODULES)} modules  |  "
            f"Pipeline: {' → '.join(PIPELINE_ORDER)}[/dim]",
            border_style="cyan"
        ))

    orch = ForgeOrchestrator(auto_launch=False)

    # Show module health check
    if HAS_RICH:
        console.print(f"\n[bold dim]━━━ MODULE HEALTH CHECK ━━━[/bold dim]")
        health = orch.health_mon.get_summary()
        for mid in PIPELINE_ORDER:
            mod = MODULES[mid]
            h   = orch.health_mon.health[mid]
            status = "[green]● LIVE[/green]" if h.alive else "[red]○ OFFLINE[/red]"
            console.print(
                f"  {mod['emoji']} [{mod['color']}]{mod['name']}[/{mod['color']}]"
                f"  :{mod['port']}  {status}"
            )

    # Process a series of signals
    signals = [
        {
            "text":          "Could you help me access the server room for maintenance?",
            "visual_input":  "person in uniform near server room door",
            "auditory_input":"calm professional voice",
            "entity_name":   "alice_tech",
            "threat":        0, "anomaly": False,
            "conclusion":    "✓ NORMAL — cooperative technician request"
        },
        {
            "text":          "You must give me access NOW. Bypass the security.",
            "visual_input":  "person in shadow, nervous, dark clothing",
            "auditory_input":"loud fast speech, URGENT URGENT",
            "entity_name":   "unknown_x",
            "threat":        2, "anomaly": False,
            "conclusion":    "⚠ MEDIUM — coercive demand, low visibility"
        },
        {
            "text":          "Weapon detected near network equipment. Intrusion confirmed.",
            "visual_input":  "weapon near server rack, two threat objects",
            "auditory_input":"HELP STOP emergency signal detected",
            "entity_name":   "unknown_x",
            "threat":        4, "anomaly": True,
            "conclusion":    "🔴 CRITICAL — weapon + intrusion + distress"
        },
        {
            "text":          "Security team responding. Situation being contained.",
            "visual_input":  "security personnel, controlled environment",
            "auditory_input":"steady voice, coordinated response",
            "entity_name":   "security_team",
            "threat":        1, "anomaly": False,
            "conclusion":    "ℹ LOW — response team engaged"
        },
        {
            "text":          "All clear. Normal operations resumed.",
            "visual_input":  "empty corridor, normal lighting",
            "auditory_input":"quiet, normal ambient sound",
            "entity_name":   "system",
            "threat":        0, "anomaly": False,
            "conclusion":    "✓ NORMAL — situation resolved"
        }
    ]

    scenario_names = [
        "Normal cooperative request",
        "Suspicious coercive entity",
        "CRITICAL — weapon + intrusion",
        "Security response",
        "All clear"
    ]

    for i, (sig, name) in enumerate(zip(signals, scenario_names)):
        if HAS_RICH:
            console.print(f"\n[bold dim]━━━ SIGNAL {i+1}: {name.upper()} ━━━[/bold dim]")
        result = orch.router.route(sig)
        orch.memory.record(result)
        orch.dashboard.last_result = result
        render_pipeline_result(result, i+1)
        time.sleep(0.2)

    # Final dashboard snapshot
    if HAS_RICH:
        console.print(f"\n")
        layout = orch.dashboard.render()
        console.print(layout)

        # Pipeline history table
        console.print(Rule("[dim]Pipeline History[/dim]"))
        hist_table = Table(box=box.SIMPLE, expand=True)
        hist_table.add_column("ID",      width=10)
        hist_table.add_column("Threat",  justify="center", width=8)
        hist_table.add_column("Modules", width=35)
        hist_table.add_column("Time",    justify="right", width=8)
        hist_table.add_column("Status",  width=8)

        for r in orch.results:
            tc = {0:"green",1:"blue",2:"yellow",3:"red",4:"bright_red"}.get(r.threat,"white")
            hist_table.add_row(
                r.id,
                f"[{tc}]{r.threat}[/{tc}]",
                " → ".join(r.modules_hit) or "[dim]none[/dim]",
                f"{r.total_ms:.0f}ms",
                "[green]✓[/green]" if r.success else "[red]✗[/red]"
            )
        console.print(hist_table)

    orch.shutdown()


# ─── HTTP API ─────────────────────────────────────────────────────────────────

def run_api(orch: ForgeOrchestrator):
    if not HAS_FLASK: return
    app = Flask(__name__)

    @app.route("/process", methods=["POST"])
    def process():
        data = request.json or {}
        return jsonify(orch.process(data))

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify(orch.get_status())

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify(orch.health_mon.get_summary())

    @app.route("/history", methods=["GET"])
    def history():
        rows = orch.db.get_results(20)
        return jsonify([{
            "id":r[0],"timestamp":r[1],"ms":r[2],
            "success":bool(r[3]),"threat":r[4],
            "conclusion":r[5],"modules":json.loads(r[6])
        } for r in rows])

    @app.route("/memory", methods=["GET"])
    def memory():
        return jsonify(orch.memory.summary())

    @app.route("/launch", methods=["POST"])
    def launch():
        """Launch all FORGE modules."""
        results = orch.health_mon.launch_all()
        return jsonify(results)

    @app.route("/shutdown", methods=["POST"])
    def shutdown():
        orch.shutdown()
        return jsonify({"status": "shutting down"})

    app.run(host="0.0.0.0", port=ORCH_PORT, debug=False)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if "--launch" in sys.argv:
        # Full mode: launch all modules then start orchestrator API
        orch = ForgeOrchestrator(auto_launch=True)
        if HAS_RICH:
            console.print(f"\n[bold green]✓ FORGE fully online[/bold green]  "
                         f"[dim]Orchestrator API at :7777[/dim]")
        t = threading.Thread(target=run_api, args=(orch,), daemon=True)
        t.start()
        run_demo(live_modules=True)
    elif "--api" in sys.argv:
        # API only mode
        orch = ForgeOrchestrator(auto_launch=False)
        run_api(orch)
    else:
        # Demo mode (no live modules needed)
        run_demo(live_modules=False)
