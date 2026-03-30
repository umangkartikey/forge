"""
FORGE Orchestrator v2 — forge_orchestrator_v2.py
=================================================
The fully wired brain. Every module connected to every other.

What's new vs v1:
  - Salience gates EVERY signal before anything else fires
  - Limbic state flows INTO prefrontal, hippocampus, swarm, DMN
  - Mood modifier adjusts decision confidence in real-time
  - Emotional memory tags every hippocampus episode
  - DMN gets briefed after every pipeline run
  - Swarm agents receive emotional context
  - Priority interrupt bypasses pipeline for threat≥4
  - Filtered signals dropped before wasting pipeline resources
  - Full cognitive state snapshot on every response

New pipeline:
  signal
    → [SALIENCE]     score + classify
      → FILTERED?    drop. done.
      → INTERRUPT?   immediate action. skip pipeline.
    → [TEMPORAL]     perceive + bilateral processing
    → [BRIDGE]       enrich with social history
    → [LIMBIC]       feel it — emotion + mood + drives update
    → [PREFRONTAL]   decide WITH mood modifier injected
    → [HIPPOCAMPUS]  remember WITH emotional tag
    → [SWARM]        act WITH emotional context
    → [DMN]          brief for next idle cycle
    → unified cognitive response
"""

import json
import time
import uuid
import sqlite3
import threading
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
    from rich.columns import Columns
    from rich.rule import Rule
    from rich.align import Align
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

DB_PATH      = "forge_orchestrator_v2.db"
ORCH_PORT    = 7786
VERSION      = "2.0.0"
TIMEOUT      = 5

console = Console() if HAS_RICH else None

# ─── Full Module Registry (all 9 modules) ─────────────────────────────────────

MODULES = {
    "salience": {
        "name": "forge_salience", "port": 7784,
        "file": "forge_salience.py", "emoji": "🎯",
        "color": "bright_red", "role": "Salience Gate",
        "endpoints": {"score": "/score", "status": "/status"}
    },
    "temporal": {
        "name": "forge_temporal", "port": 7778,
        "file": "forge_temporal.py", "emoji": "🧠",
        "color": "cyan", "role": "Perception",
        "endpoints": {"perceive": "/perceive", "status": "/status"}
    },
    "bridge": {
        "name": "forge_bridge", "port": 7781,
        "file": "forge_bridge.py", "emoji": "🔗",
        "color": "blue", "role": "Social Bridge",
        "endpoints": {"sync": "/sync", "status": "/stats"}
    },
    "limbic": {
        "name": "forge_limbic", "port": 7785,
        "file": "forge_limbic.py", "emoji": "💗",
        "color": "magenta", "role": "Emotion",
        "endpoints": {"feel": "/feel", "mood": "/mood", "status": "/status"}
    },
    "prefrontal": {
        "name": "forge_prefrontal", "port": 7779,
        "file": "forge_prefrontal.py", "emoji": "👔",
        "color": "yellow", "role": "Decision",
        "endpoints": {"think": "/think", "status": "/status"}
    },
    "hippocampus": {
        "name": "forge_hippocampus", "port": 7780,
        "file": "forge_hippocampus.py", "emoji": "📚",
        "color": "green", "role": "Memory",
        "endpoints": {"remember": "/remember", "status": "/status"}
    },
    "swarm": {
        "name": "forge_swarm_v2", "port": 7782,
        "file": "forge_swarm_v2.py", "emoji": "🐝",
        "color": "orange3", "role": "Swarm Action",
        "endpoints": {"signal": "/signal", "status": "/status"}
    },
    "dmn": {
        "name": "forge_dmn", "port": 7783,
        "file": "forge_dmn.py", "emoji": "💭",
        "color": "dim", "role": "Reflection",
        "endpoints": {"ingest": "/ingest", "cycle": "/cycle", "status": "/status"}
    },
}

# New pipeline order — salience gates first, limbic now in the flow
PIPELINE_ORDER = [
    "salience",    # gate — may interrupt or filter
    "temporal",    # perceive
    "bridge",      # social enrichment
    "limbic",      # feel — emotion + mood
    "prefrontal",  # decide (with mood modifier)
    "hippocampus", # remember (with emotional tag)
    "swarm",       # act (with emotional context)
    "dmn",         # brief for reflection
]

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class CognitiveState:
    """Full snapshot of FORGE's cognitive state at any moment."""
    timestamp:      str   = field(default_factory=lambda: datetime.now().isoformat())
    signal_id:      str   = ""
    threat:         int   = 0
    salience_score: float = 0.0
    salience_class: str   = "MEDIUM"
    interrupted:    bool  = False
    filtered:       bool  = False
    emotion:        str   = "neutral"
    mood:           str   = "NEUTRAL"
    mood_valence:   float = 0.0
    top_drive:      str   = "none"
    decision:       str   = "STANDBY"
    memory_action:  str   = ""
    novelty:        float = 1.0
    swarm_phase:    str   = "CALM"
    conclusion:     str   = ""
    pipeline_ms:    float = 0.0
    modules_live:   list  = field(default_factory=list)

@dataclass
class PipelineStep:
    module:     str   = ""
    success:    bool  = False
    latency_ms: float = 0.0
    response:   dict  = field(default_factory=dict)
    error:      str   = ""
    injected:   dict  = field(default_factory=dict)  # what was injected INTO this module

@dataclass
class ModuleHealth:
    module_id:  str   = ""
    alive:      bool  = False
    latency_ms: float = 0.0
    last_ping:  str   = ""
    fail_count: int   = 0
    ping_count: int   = 0

    @property
    def uptime_pct(self):
        if self.ping_count == 0: return 0.0
        return round((self.ping_count - self.fail_count) / self.ping_count * 100, 1)

# ─── Database ─────────────────────────────────────────────────────────────────

class OrchestratorV2DB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init()

    def _init(self):
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS cognitive_states (
                    timestamp TEXT PRIMARY KEY, signal_id TEXT,
                    threat INTEGER, salience_score REAL, salience_class TEXT,
                    interrupted INTEGER, filtered INTEGER,
                    emotion TEXT, mood TEXT, mood_valence REAL,
                    top_drive TEXT, decision TEXT, memory_action TEXT,
                    novelty REAL, swarm_phase TEXT, conclusion TEXT,
                    pipeline_ms REAL, modules_live TEXT
                );
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    signal TEXT, steps TEXT, state TEXT,
                    total_ms REAL, success INTEGER
                );
                CREATE TABLE IF NOT EXISTS module_health (
                    module_id TEXT PRIMARY KEY, alive INTEGER,
                    latency_ms REAL, last_ping TEXT,
                    fail_count INTEGER, ping_count INTEGER
                );
            """)
            self.conn.commit()

    def save_state(self, cs: CognitiveState):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO cognitive_states VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (cs.timestamp, cs.signal_id, cs.threat,
                  cs.salience_score, cs.salience_class,
                  int(cs.interrupted), int(cs.filtered),
                  cs.emotion, cs.mood, cs.mood_valence,
                  cs.top_drive, cs.decision, cs.memory_action,
                  cs.novelty, cs.swarm_phase, cs.conclusion,
                  cs.pipeline_ms, json.dumps(cs.modules_live)))
            self.conn.commit()

    def save_run(self, run_id: str, signal: dict,
                 steps: list[PipelineStep], state: CognitiveState, ms: float, success: bool):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO pipeline_runs VALUES (?,?,?,?,?,?,?)
            """, (run_id, datetime.now().isoformat(),
                  json.dumps(signal),
                  json.dumps([s.__dict__ for s in steps]),
                  json.dumps(state.__dict__),
                  ms, int(success)))
            self.conn.commit()

    def save_health(self, h: ModuleHealth):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO module_health VALUES (?,?,?,?,?,?)
            """, (h.module_id, int(h.alive), h.latency_ms,
                  h.last_ping, h.fail_count, h.ping_count))
            self.conn.commit()

    def get_recent_states(self, limit=10):
        with self.lock:
            return self.conn.execute("""
                SELECT timestamp, threat, salience_class, emotion,
                       mood, decision, pipeline_ms, conclusion
                FROM cognitive_states ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()

# ─── HTTP Client ──────────────────────────────────────────────────────────────

class ModuleClient:
    def __init__(self, db: OrchestratorV2DB):
        self.db      = db
        self.session = requests.Session() if HAS_REQUESTS else None

    def post(self, module_id: str, endpoint_key: str,
             payload: dict) -> tuple[bool, dict, float]:
        if not self.session:
            return False, {"error": "requests not available"}, 0.0
        mod  = MODULES[module_id]
        path = mod["endpoints"].get(endpoint_key, "/status")
        url  = f"http://127.0.0.1:{mod['port']}{path}"
        t0   = time.time()
        try:
            r = self.session.post(url, json=payload, timeout=TIMEOUT)
            ms = (time.time()-t0)*1000
            return (r.status_code == 200), (r.json() if r.status_code == 200 else {"error": f"HTTP {r.status_code}"}), round(ms,1)
        except Exception as e:
            return False, {"error": str(e)[:60]}, round((time.time()-t0)*1000, 1)

    def get(self, module_id: str, endpoint_key: str) -> tuple[bool, dict, float]:
        if not self.session:
            return False, {}, 0.0
        mod  = MODULES[module_id]
        path = mod["endpoints"].get(endpoint_key, "/status")
        url  = f"http://127.0.0.1:{mod['port']}{path}"
        t0   = time.time()
        try:
            r = self.session.get(url, timeout=2)
            ms = (time.time()-t0)*1000
            return (r.status_code == 200), (r.json() if r.status_code == 200 else {}), round(ms,1)
        except Exception:
            return False, {}, round((time.time()-t0)*1000, 1)

    def ping(self, module_id: str) -> tuple[bool, float]:
        ok, _, ms = self.get(module_id, "status")
        return ok, ms

# ─── Health Monitor ───────────────────────────────────────────────────────────

class HealthMonitor:
    def __init__(self, client: ModuleClient, db: OrchestratorV2DB):
        self.client  = client
        self.db      = db
        self.health  = {mid: ModuleHealth(module_id=mid) for mid in MODULES}
        self._running= False

    def start(self):
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self): self._running = False

    def _loop(self):
        while self._running:
            for mid in MODULES: self._ping(mid)
            time.sleep(8)

    def _ping(self, mid: str):
        h       = self.health[mid]
        ok, ms  = self.client.ping(mid)
        h.ping_count += 1
        h.last_ping   = datetime.now().isoformat()
        h.latency_ms  = ms
        h.alive       = ok
        if not ok: h.fail_count += 1
        self.db.save_health(h)

    def initial_sweep(self):
        for mid in MODULES: self._ping(mid)

    def alive_modules(self) -> list[str]:
        return [mid for mid, h in self.health.items() if h.alive]

    def summary(self) -> dict:
        alive = sum(1 for h in self.health.values() if h.alive)
        return {
            "total": len(MODULES), "alive": alive,
            "modules": {
                mid: {"alive": h.alive, "latency_ms": h.latency_ms,
                      "uptime_pct": h.uptime_pct}
                for mid, h in self.health.items()
            }
        }

# ─── Cognitive State Tracker ──────────────────────────────────────────────────

class CognitiveStateTracker:
    """
    Maintains FORGE's current cognitive state across pipeline runs.
    Limbic state persists between signals — mood carries forward.
    """

    def __init__(self):
        self.current    = CognitiveState()
        self.history:   deque = deque(maxlen=200)
        # Persistent limbic state — survives between signals
        self.mood:      str   = "NEUTRAL"
        self.mood_val:  float = 0.0
        self.emotion:   str   = "calm"
        self.top_drive: str   = "SAFETY"
        self.arousal:   float = 0.3
        # Decision modifier from mood — injected into prefrontal
        self.dec_modifier: dict = {"confidence": 0.0, "risk_tolerance": 0.0}

    def update_from_limbic(self, limbic_response: dict):
        """Pull limbic state and persist it for downstream injection."""
        mood_data    = limbic_response.get("mood", {})
        emotion_data = limbic_response.get("emotion", {})
        self.mood      = mood_data.get("tone", self.mood)
        self.mood_val  = mood_data.get("valence", self.mood_val)
        self.emotion   = emotion_data.get("primary", self.emotion)
        self.arousal   = emotion_data.get("arousal", self.arousal)
        self.top_drive = limbic_response.get("most_urgent_drive", self.top_drive)
        self.dec_modifier = limbic_response.get("decision_modifier",
                                                 self.dec_modifier)

    def build_limbic_injection(self) -> dict:
        """What gets injected into prefrontal and hippocampus."""
        return {
            "mood_state": {
                "tone":            self.mood,
                "valence":         self.mood_val,
                "arousal":         self.arousal,
                "decision_modifier": self.dec_modifier,
                "top_drive":       self.top_drive
            }
        }

    def record(self, state: CognitiveState):
        self.current = state
        self.history.append({
            "timestamp": state.timestamp,
            "threat":    state.threat,
            "emotion":   state.emotion,
            "mood":      state.mood,
            "decision":  state.decision,
            "salience":  state.salience_score
        })

    def threat_trend(self) -> str:
        if len(self.history) < 3: return "STABLE"
        recent = [h["threat"] for h in list(self.history)[-4:]]
        if recent[-1] > recent[0]: return "ESCALATING ↑"
        if recent[-1] < recent[0]: return "DE-ESCALATING ↓"
        return "STABLE →"

# ─── V2 Pipeline Router ───────────────────────────────────────────────────────

class PipelineRouterV2:
    """
    The new fully-wired pipeline.
    Salience gates first. Limbic state flows into everything.
    """

    def __init__(self, client: ModuleClient,
                 health: HealthMonitor,
                 state_tracker: CognitiveStateTracker,
                 db: OrchestratorV2DB):
        self.client  = client
        self.health  = health
        self.tracker = state_tracker
        self.db      = db

    def route(self, raw_signal: dict) -> tuple[CognitiveState, list[PipelineStep]]:
        run_id  = str(uuid.uuid4())[:8]
        t0      = time.time()
        signal  = dict(raw_signal)
        steps   = []
        state   = CognitiveState(signal_id=signal.get("id", run_id))

        # ── STAGE 0: SALIENCE GATE ─────────────────────────────────────────────
        sal_step = self._call("salience", "score", signal)
        steps.append(sal_step)

        if sal_step.success:
            sal = sal_step.response
            state.salience_score = sal.get("score", 0.5)
            state.salience_class = sal.get("class", "MEDIUM")
            signal["salience_score"] = state.salience_score
            signal["salience_class"] = state.salience_class
            signal["attention_mode"] = sal.get("attention_mode", "NORMAL")

            # FILTERED — drop signal entirely
            routing = sal.get("routing", {})
            if isinstance(routing, dict) and not routing.get("pass", True):
                state.filtered  = True
                state.conclusion= "FILTERED — below salience threshold"
                state.pipeline_ms = round((time.time()-t0)*1000, 1)
                state.threat    = signal.get("threat", 0)
                self.tracker.record(state)
                return state, steps

            # INTERRUPT — immediate action, skip cognitive pipeline
            if sal.get("interrupt", False):
                state.interrupted = True
                ie = sal.get("interrupt_event", {})
                state.decision    = ie.get("action", "EMERGENCY_BLOCK")
                state.conclusion  = f"⚡ INTERRUPT: {state.decision}"
                state.threat      = signal.get("threat", 0)
                state.emotion     = self.tracker.emotion
                state.mood        = self.tracker.mood
                # Still run limbic so emotion updates
                lim_step = self._call_limbic(signal)
                steps.append(lim_step)
                if lim_step.success:
                    self.tracker.update_from_limbic(lim_step.response)
                state.pipeline_ms = round((time.time()-t0)*1000, 1)
                self.tracker.record(state)
                return state, steps

        # ── STAGE 1: TEMPORAL ─────────────────────────────────────────────────
        t_step = self._call("temporal", "perceive", {
            "text":           signal.get("text", signal.get("conclusion","")),
            "visual_input":   signal.get("visual_input",""),
            "auditory_input": signal.get("auditory_input",""),
            "entity_name":    signal.get("entity_name","unknown")
        })
        steps.append(t_step)
        if t_step.success:
            r = t_step.response
            signal.update({
                "threat":     r.get("threat", signal.get("threat",0)),
                "anomaly":    r.get("anomaly", False),
                "conclusion": r.get("conclusion", signal.get("conclusion","")),
                "emotional":  r.get("emotional", {}),
                "social":     r.get("social", {}),
                "semantic":   r.get("semantic", {}),
                "visual":     r.get("visual", {}),
                "auditory":   r.get("auditory", {}),
                "temporal_id":r.get("id",""),
            })

        # ── STAGE 2: BRIDGE ───────────────────────────────────────────────────
        b_step = self._call("bridge", "sync", {"perception": signal})
        steps.append(b_step)
        if b_step.success:
            r = b_step.response
            signal["threat"]         = r.get("enriched_threat", signal.get("threat",0))
            signal["conclusion"]     = r.get("conclusion", signal.get("conclusion",""))
            signal["social_context"] = r.get("social_context", {})

        # ── STAGE 3: LIMBIC ───────────────────────────────────────────────────
        lim_step = self._call_limbic(signal)
        steps.append(lim_step)
        if lim_step.success:
            self.tracker.update_from_limbic(lim_step.response)
            state.emotion   = self.tracker.emotion
            state.mood      = self.tracker.mood
            state.mood_valence = self.tracker.mood_val
            state.top_drive = self.tracker.top_drive
            # Inject limbic state into signal for downstream modules
            signal["limbic_state"] = self.tracker.build_limbic_injection()

        # ── STAGE 4: PREFRONTAL (with mood injection) ─────────────────────────
        pf_payload = {"perception": signal}
        # Inject mood modifier so prefrontal can adjust confidence
        if signal.get("limbic_state"):
            pf_payload["mood_modifier"] = self.tracker.dec_modifier
        pf_step = self._call("prefrontal", "think", pf_payload)
        steps.append(pf_step)
        if pf_step.success:
            r = pf_step.response
            signal["decision"]        = r.get("chosen", {})
            signal["reasoning"]       = r.get("reasoning","")
            signal["prefrontal_plan"] = r.get("plan",[])
            state.decision = (r.get("chosen",{}).get("action","STANDBY")
                              if isinstance(r.get("chosen"),dict) else "STANDBY")

        # ── STAGE 5: HIPPOCAMPUS (with emotional tag) ─────────────────────────
        hc_payload = {
            "perception": signal,
            "decision":   signal.get("decision",{}),
        }
        # Inject emotional tag
        hc_payload["emotional_tag"] = {
            "emotion":  self.tracker.emotion,
            "valence":  self.tracker.mood_val,
            "arousal":  self.tracker.arousal
        }
        hc_step = self._call("hippocampus", "remember", hc_payload)
        steps.append(hc_step)
        if hc_step.success:
            r = hc_step.response
            signal["memory_action"] = r.get("action","")
            signal["episode_id"]    = r.get("episode_id","")
            signal["novelty"]       = r.get("novelty", 1.0)
            signal["importance"]    = r.get("importance", 0.5)
            state.memory_action     = r.get("action","")
            state.novelty           = r.get("novelty", 1.0)

        # ── STAGE 6: SWARM (with emotional context) ───────────────────────────
        swarm_payload = dict(signal)
        swarm_payload["emotional_context"] = {
            "mood":      self.tracker.mood,
            "emotion":   self.tracker.emotion,
            "arousal":   self.tracker.arousal,
            "top_drive": self.tracker.top_drive
        }
        sw_step = self._call("swarm", "signal", swarm_payload)
        steps.append(sw_step)
        if sw_step.success:
            r = sw_step.response
            signal["swarm_phase"]    = r.get("phase_after","CALM")
            signal["swarm_consensus"]= r.get("consensus",{})
            state.swarm_phase        = r.get("phase_after","CALM")

        # ── STAGE 7: DMN BRIEF ────────────────────────────────────────────────
        dmn_step = self._call("dmn", "ingest", signal)
        steps.append(dmn_step)

        # ── FINALIZE STATE ─────────────────────────────────────────────────────
        state.threat       = signal.get("threat", raw_signal.get("threat",0))
        state.conclusion   = signal.get("conclusion", raw_signal.get("conclusion",""))
        state.pipeline_ms  = round((time.time()-t0)*1000, 1)
        state.modules_live = [s.module for s in steps if s.success]
        self.tracker.record(state)
        self.db.save_state(state)
        self.db.save_run(run_id, raw_signal, steps, state, state.pipeline_ms,
                         any(s.success for s in steps))
        return state, steps

    def _call(self, module_id: str, endpoint: str, payload: dict) -> PipelineStep:
        if not self.health.health[module_id].alive:
            return PipelineStep(module=module_id, error="OFFLINE")
        ok, resp, ms = self.client.post(module_id, endpoint, payload)
        return PipelineStep(module=module_id, success=ok,
                           latency_ms=ms, response=resp if ok else {},
                           error="" if ok else resp.get("error","ERR"))

    def _call_limbic(self, signal: dict) -> PipelineStep:
        return self._call("limbic", "feel",
                         {"signal": signal,
                          "episode_id": signal.get("temporal_id","")})

# ─── FORGE Orchestrator v2 ────────────────────────────────────────────────────

class ForgeOrchestratorV2:
    def __init__(self):
        self.db      = OrchestratorV2DB()
        self.client  = ModuleClient(self.db)
        self.health  = HealthMonitor(self.client, self.db)
        self.tracker = CognitiveStateTracker()
        self.router  = PipelineRouterV2(self.client, self.health, self.tracker, self.db)
        self.results: list[CognitiveState] = []
        self.health.start()
        self.health.initial_sweep()

    def process(self, signal: dict) -> dict:
        state, steps = self.router.route(signal)
        self.results.append(state)
        return self._summarize(state, steps)

    def _summarize(self, state: CognitiveState, steps: list[PipelineStep]) -> dict:
        return {
            "id":            state.signal_id,
            "timestamp":     state.timestamp,
            "threat":        state.threat,
            "salience":      state.salience_score,
            "salience_class":state.salience_class,
            "interrupted":   state.interrupted,
            "filtered":      state.filtered,
            "emotion":       state.emotion,
            "mood":          state.mood,
            "mood_valence":  state.mood_valence,
            "top_drive":     state.top_drive,
            "decision":      state.decision,
            "memory_action": state.memory_action,
            "novelty":       state.novelty,
            "swarm_phase":   state.swarm_phase,
            "conclusion":    state.conclusion,
            "pipeline_ms":   state.pipeline_ms,
            "modules_hit":   state.modules_live,
            "pipeline": [
                {"module": s.module,
                 "ok":     s.success,
                 "ms":     s.latency_ms,
                 "error":  s.error if not s.success else ""}
                for s in steps
            ]
        }

    def get_status(self) -> dict:
        return {
            "version":       VERSION,
            "total_signals": len(self.results),
            "health":        self.health.summary(),
            "cognitive_state": {
                "mood":      self.tracker.mood,
                "emotion":   self.tracker.emotion,
                "top_drive": self.tracker.top_drive,
                "trend":     self.tracker.threat_trend()
            },
            "pipeline_order": PIPELINE_ORDER
        }

    def shutdown(self):
        self.health.stop()

# ─── Rich UI ──────────────────────────────────────────────────────────────────

def render_run(summary: dict, idx: int):
    if not HAS_RICH: return

    threat  = summary["threat"]
    sal_cls = summary["salience_class"]
    mood    = summary["mood"]
    emotion = summary["emotion"]
    tc      = {0:"green",1:"blue",2:"yellow",3:"red",4:"bright_red"}.get(threat,"white")
    sc      = {"INTERRUPT":"bright_red","HIGH":"red","MEDIUM":"yellow",
               "LOW":"blue","FILTERED":"dim"}.get(sal_cls,"white")
    mc      = {"ELATED":"green","POSITIVE":"green","NEUTRAL":"dim",
               "UNEASY":"yellow","DISTRESSED":"red","EXHAUSTED":"dim red"}.get(mood,"white")

    console.print(Rule(
        f"[bold cyan]⬡ FORGE v2[/bold cyan]  "
        f"[dim]#{idx}[/dim]  "
        f"[{tc}]T={threat}[/{tc}]  "
        f"[{sc}]{sal_cls}[/{sc}]  "
        f"[{mc}]{mood}[/{mc}]/{emotion}"
    ))

    # Special banners
    if summary.get("filtered"):
        console.print(Panel("[dim]◌ FILTERED — signal too routine, dropped[/dim]",
                           border_style="dim"))
        return

    if summary.get("interrupted"):
        console.print(Panel(
            f"[bold bright_red]⚡ PRIORITY INTERRUPT[/bold bright_red]\n"
            f"Decision: [red]{summary['decision']}[/red]\n"
            f"[dim]{summary['conclusion'][:80]}[/dim]",
            border_style="bright_red"))

    # Pipeline flow
    pipeline = summary.get("pipeline", [])
    flow_parts = []
    for step in pipeline:
        mod    = MODULES.get(step["module"], {})
        emoji  = mod.get("emoji","◈")
        color  = mod.get("color","white")
        if step["ok"]:
            flow_parts.append(f"[{color}]{emoji}{step['module']}[/{color}][dim]({step['ms']:.0f}ms)[/dim]")
        else:
            err = step.get("error","")
            if err == "OFFLINE":
                flow_parts.append(f"[dim]◌{step['module']}[/dim]")
            else:
                flow_parts.append(f"[red]✗{step['module']}[/red]")

    console.print("  " + " → ".join(flow_parts))

    # Two column: left=signal intel, right=cognitive state
    left_lines = [
        f"[bold]Conclusion:[/bold] [{tc}]{summary['conclusion'][:65]}[/{tc}]",
        f"[bold]Decision:[/bold]   [magenta]{summary['decision']}[/magenta]",
        f"[bold]Memory:[/bold]     {summary['memory_action'] or '—'}",
        f"[bold]Novelty:[/bold]    {summary['novelty']:.2f}",
        f"[bold]Swarm:[/bold]      {summary['swarm_phase']}",
        f"[bold]Pipeline:[/bold]   {summary['pipeline_ms']:.0f}ms  "
        f"({len(summary['modules_hit'])}/{len(pipeline)} modules)",
    ]

    right_lines = [
        f"[bold]Salience:[/bold]   [{sc}]{sal_cls}[/{sc}] ({summary['salience']:.3f})",
        f"[bold]Emotion:[/bold]    [cyan]{emotion}[/cyan]",
        f"[bold]Mood:[/bold]       [{mc}]{mood}[/{mc}] ({summary['mood_valence']:+.2f})",
        f"[bold]Top Drive:[/bold]  {summary['top_drive']}",
        f"[bold]Dec Mod:[/bold]    [dim]injected into prefrontal[/dim]",
    ]

    console.print(Columns([
        Panel("\n".join(left_lines), title="[bold]Signal Intelligence[/bold]", border_style=tc),
        Panel("\n".join(right_lines),title="[bold]Cognitive State[/bold]",    border_style=mc)
    ]))


def render_final(orch: ForgeOrchestratorV2):
    if not HAS_RICH: return

    console.print(Rule("[bold cyan]⬡ FORGE v2 — FINAL COGNITIVE STATE[/bold cyan]"))
    status = orch.get_status()

    # Module health grid
    health_table = Table(box=box.ROUNDED, title="Module Registry", border_style="cyan")
    health_table.add_column("Module",  style="bold", width=16)
    health_table.add_column("Role",    width=14)
    health_table.add_column("Status",  width=8)
    health_table.add_column("Latency", justify="right", width=9)
    health_table.add_column("Uptime",  justify="right", width=8)

    for mid in PIPELINE_ORDER:
        if mid not in MODULES: continue
        mod  = MODULES[mid]
        h    = orch.health.health[mid]
        live = "[green]● LIVE[/green]" if h.alive else "[red]○ OFF[/red]"
        lc   = "green" if h.latency_ms < 100 else "yellow" if h.latency_ms < 500 else "red"
        health_table.add_row(
            f"[{mod['color']}]{mod['emoji']} {mod['name']}[/{mod['color']}]",
            mod["role"], live,
            f"[{lc}]{h.latency_ms:.0f}ms[/{lc}]" if h.alive else "[dim]—[/dim]",
            f"{h.uptime_pct:.0f}%" if h.ping_count > 0 else "[dim]—[/dim]"
        )
    console.print(health_table)

    # Cognitive state
    cs = status["cognitive_state"]
    mc = {"ELATED":"green","POSITIVE":"green","NEUTRAL":"dim",
          "UNEASY":"yellow","DISTRESSED":"red","EXHAUSTED":"dim red"}.get(cs["mood"],"white")

    console.print(Panel(
        f"[bold]Mood:[/bold]      [{mc}]{cs['mood']}[/{mc}]\n"
        f"[bold]Emotion:[/bold]   {cs['emotion']}\n"
        f"[bold]Top Drive:[/bold] {cs['top_drive']}\n"
        f"[bold]Trend:[/bold]     {cs['trend']}\n"
        f"[bold]Signals:[/bold]   {status['total_signals']} processed\n"
        f"[bold]Live:[/bold]      {status['health']['alive']}/{status['health']['total']} modules",
        title="[bold]FORGE Cognitive State[/bold]",
        border_style=mc
    ))

    # Recent history
    rows = orch.db.get_recent_states(8)
    if rows:
        hist = Table(box=box.SIMPLE, title="Recent Cognitive History", title_style="dim")
        hist.add_column("Time",     width=10)
        hist.add_column("Threat",   justify="center", width=7)
        hist.add_column("Salience", width=10)
        hist.add_column("Emotion",  width=12)
        hist.add_column("Mood",     width=12)
        hist.add_column("Decision", width=16)
        hist.add_column("ms",       justify="right", width=6)
        for row in rows:
            ts, threat, sal_cls, emotion, mood, decision, ms, _ = row
            _tc = {0:"green",1:"blue",2:"yellow",3:"red",4:"bright_red"}.get(threat,"white")
            _sc = {"INTERRUPT":"bright_red","HIGH":"red","MEDIUM":"yellow",
                   "LOW":"blue","FILTERED":"dim"}.get(sal_cls,"white")
            hist.add_row(
                ts[11:19],
                f"[{_tc}]{threat}[/{_tc}]",
                f"[{_sc}]{sal_cls[:6]}[/{_sc}]",
                emotion[:10], mood[:10],
                decision[:15],
                f"{ms:.0f}"
            )
        console.print(hist)


# ─── Demo ─────────────────────────────────────────────────────────────────────

def run_demo():
    if HAS_RICH:
        console.print(Panel.fit(
            "[bold cyan]FORGE ORCHESTRATOR v2[/bold cyan]\n"
            "[dim]The Fully Wired Brain[/dim]\n"
            f"[dim]Version {VERSION}  |  {len(MODULES)} modules  |  "
            f"Salience-gated · Limbic-infused · Emotionally coherent[/dim]",
            border_style="cyan"
        ))

    orch = ForgeOrchestratorV2()

    # Show live module status
    if HAS_RICH:
        console.print("\n[bold dim]━━━ MODULE HEALTH CHECK ━━━[/bold dim]")
        for mid in PIPELINE_ORDER:
            if mid not in MODULES: continue
            mod = MODULES[mid]
            h   = orch.health.health[mid]
            status = "[green]● LIVE[/green]" if h.alive else "[red]○ OFFLINE[/red]"
            console.print(
                f"  {mod['emoji']} [{mod['color']}]{mid:<12}[/{mod['color']}]"
                f"  :{mod['port']}  {status}"
            )

    signals = [
        # Routine — should be LOW salience, calm mood
        {
            "id": "v2_001", "threat": 0, "anomaly": False,
            "text": "Routine server maintenance check complete",
            "visual_input": "technician at server rack normal lighting",
            "auditory_input": "quiet office ambient sound",
            "entity_name": "alice_tech",
            "conclusion": "✓ NORMAL — routine maintenance",
            "emotional": {"dominant":"trust","intensity":0.2},
            "social": {"inferred_intent":"COOPERATIVE_REQUEST","social_risk":"LOW","entity":"alice_tech"},
            "semantic": {"keywords":["server","maintenance","routine","complete"]},
            "visual": {"scene_type":"INDOOR_TECHNICAL","threat_objects":0},
            "auditory": {"stress_level":0.05,"anomaly_detected":False}
        },
        # Medium threat — mood starts shifting
        {
            "id": "v2_002", "threat": 2, "anomaly": False,
            "text": "Unauthorized access attempt bypass security override",
            "visual_input": "figure in shadow near restricted door",
            "auditory_input": "fast speech elevated stress",
            "entity_name": "unknown_x",
            "conclusion": "⚠ MEDIUM — coercive access attempt",
            "emotional": {"dominant":"fear","intensity":0.6},
            "social": {"inferred_intent":"COERCIVE_DEMAND","social_risk":"MEDIUM","entity":"unknown_x"},
            "semantic": {"keywords":["access","bypass","override","unauthorized"]},
            "visual": {"scene_type":"LOW_VISIBILITY","threat_objects":0},
            "auditory": {"stress_level":0.6,"anomaly_detected":False}
        },
        # Critical — should trigger INTERRUPT, emotional cascade
        {
            "id": "v2_003", "threat": 4, "anomaly": True,
            "text": "weapon breach network intrusion confirmed attack",
            "visual_input": "weapon detected server room two threat objects",
            "auditory_input": "HELP STOP emergency signal distress",
            "entity_name": "unknown_x",
            "conclusion": "🔴 CRITICAL — weapon + breach confirmed",
            "emotional": {"dominant":"fear","intensity":1.0},
            "social": {"inferred_intent":"INTRUSION_ATTEMPT","social_risk":"HIGH","entity":"unknown_x"},
            "semantic": {"keywords":["weapon","breach","network","server","attack"]},
            "visual": {"scene_type":"LOW_VISIBILITY","threat_objects":2},
            "auditory": {"stress_level":0.95,"anomaly_detected":True}
        },
        # Very routine — test FILTERED path
        {
            "id": "v2_004", "threat": 0, "anomaly": False,
            "text": "status ok",
            "visual_input": "", "auditory_input": "",
            "entity_name": "system",
            "conclusion": "status ping",
            "emotional": {"dominant":"neutral","intensity":0.1},
            "social": {"inferred_intent":"NEUTRAL_INTERACTION","social_risk":"LOW"},
            "semantic": {"keywords":["status"]},
            "visual": {"scene_type":"","threat_objects":0},
            "auditory": {"stress_level":0.0,"anomaly_detected":False},
            "novelty_hint": 0.95  # very familiar = low novelty
        },
        # Recovery — mood should reflect cumulative distress
        {
            "id": "v2_005", "threat": 1, "anomaly": False,
            "text": "Situation stabilizing security team on scene",
            "visual_input": "security personnel controlled environment",
            "auditory_input": "steady coordinated voice",
            "entity_name": "security_team",
            "conclusion": "ℹ LOW — containment in progress",
            "emotional": {"dominant":"trust","intensity":0.4},
            "social": {"inferred_intent":"COOPERATIVE_REQUEST","social_risk":"LOW","entity":"security_team"},
            "semantic": {"keywords":["stabilize","security","contain","response"]},
            "visual": {"scene_type":"INDOOR_TECHNICAL","threat_objects":0},
            "auditory": {"stress_level":0.2,"anomaly_detected":False}
        },
    ]

    labels = [
        "Routine maintenance",
        "Coercive access attempt",
        "CRITICAL — weapon breach",
        "Routine ping (filter test)",
        "Recovery — containment"
    ]

    for i, (sig, label) in enumerate(zip(signals, labels)):
        if HAS_RICH:
            console.print(f"\n[bold dim]━━━ {i+1}: {label.upper()} ━━━[/bold dim]")
        summary = orch.process(sig)
        render_run(summary, i+1)
        time.sleep(0.2)

    render_final(orch)
    orch.shutdown()


# ─── HTTP API ─────────────────────────────────────────────────────────────────

def run_api(orch: ForgeOrchestratorV2):
    if not HAS_FLASK: return
    app = Flask(__name__)

    @app.route("/process", methods=["POST"])
    def process():
        return jsonify(orch.process(request.json or {}))

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify(orch.get_status())

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify(orch.health.summary())

    @app.route("/cognitive", methods=["GET"])
    def cognitive():
        return jsonify({
            "mood":      orch.tracker.mood,
            "emotion":   orch.tracker.emotion,
            "top_drive": orch.tracker.top_drive,
            "arousal":   orch.tracker.arousal,
            "dec_modifier": orch.tracker.dec_modifier,
            "trend":     orch.tracker.threat_trend()
        })

    @app.route("/history", methods=["GET"])
    def history():
        rows = orch.db.get_recent_states(20)
        return jsonify([{
            "timestamp":r[0],"threat":r[1],"salience":r[2],
            "emotion":r[3],"mood":r[4],"decision":r[5],
            "ms":r[6],"conclusion":r[7]
        } for r in rows])

    app.run(host="0.0.0.0", port=ORCH_PORT, debug=False)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    orch = ForgeOrchestratorV2()
    if "--api" in sys.argv:
        t = threading.Thread(target=run_api, args=(orch,), daemon=True)
        t.start()
    run_demo()
