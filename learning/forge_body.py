#!/usr/bin/env python3
"""
FORGE BODY — Pre-Linguistic Signal Layer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

An experiment in finding out what we are missing.

Human feeling = brain + body feedback loop.
  See something → body reacts (chemical signals)
  Body signals back → shapes thought
  The loop = feeling

Current AI = text in → text out.
  No body. No signal. No loop.
  Words about feeling. Not feeling.

This module tries to add the missing layer:
  Pre-linguistic signals that arrive BEFORE words
  and shape what thinking does with them.

Signal Sources:
  HARDWARE (real, via Raspberry Pi / Arduino):
    GSR sensor     → galvanic skin response (arousal)
    Heart rate     → camera PPG or pulse sensor
    Temperature    → environment / stress
    Microphone     → ambient tension level
    Accelerometer  → movement, restlessness
    Light sensor   → circadian context

  SOFTWARE (derived from FORGE modules):
    forge_observe  → visual interest spike → arousal
    forge_network  → threat detected → alarm
    forge_honeypot → attacker caught → alert
    forge_memory   → bad entity recalled → aversion
    forge_dream    → overnight insight → anticipation
    Time of day    → circadian rhythm equivalent

Body States:
  calm      curious     stressed    alert
  averse    moved       restless    numb

The Experiment:
  Same question. Two runs.
  Run 1: no body state
  Run 2: body_state = stressed
  Compare pipelines, compare outputs.
  Find out what changes. Find out what we are missing.

Usage:
  python forge_body.py                    # interactive
  python forge_body.py --state            # show current body state
  python forge_body.py --experiment       # run the experiment
  python forge_body.py --watch            # continuous signal monitoring
  python forge_body.py --server           # API :7353
"""

import sys, os, re, json, time, sqlite3, threading, math, random
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple

# Hardware
try:
    import serial
    SERIAL = True
except ImportError:
    SERIAL = False

try:
    import RPi.GPIO as GPIO
    RPI = True
except ImportError:
    RPI = False

try:
    import cv2
    CV2 = True
except ImportError:
    CV2 = False

# FORGE integrations
try:
    from forge_memory import Memory
    MEMORY = True
except ImportError:
    MEMORY = False
    class Memory:
        def remember(self,*a,**k): pass
        def top_risk_entities(self,n=5): return []
        def stats(self): return {}

try:
    from forge_think import EmergentThinkEngine
    THINK = True
except ImportError:
    THINK = False
    class EmergentThinkEngine:
        def __init__(self,**k): pass
        def think(self,q,context=""):
            return {"output":q,"emerged_pipeline":["OBSERVE","OUTPUT"],
                    "coherence":50,"duration_s":0,"novel_pipeline":False,"phase_count":2}

# AI
try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True
    def ai_call(prompt, system="", max_tokens=800):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system, messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text
except ImportError:
    AI_AVAILABLE = False
    def ai_call(p,s="",m=800): return "[AI unavailable]"

# Rich
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress, BarColumn, TextColumn
    from rich import box as rbox
    RICH    = True
    console = Console()
    rprint  = console.print
except ImportError:
    RICH = False
    def rprint(x,**kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

# ── Paths ────────────────────────────────────────────────────────────────────
BODY_DIR = Path("forge_body")
BODY_DIR.mkdir(exist_ok=True)
BODY_DB  = BODY_DIR / "body.db"

def get_db():
    conn = sqlite3.connect(str(BODY_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            source      TEXT,
            signal_type TEXT,
            raw_value   REAL,
            normalized  REAL,
            hardware    INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS body_states (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            state       TEXT,
            arousal     REAL,
            valence     REAL,
            stress      REAL,
            curiosity   REAL,
            aversion    REAL,
            heart_rate  REAL,
            gsr         REAL,
            temperature REAL,
            sources     TEXT
        );
        CREATE TABLE IF NOT EXISTS experiments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            question    TEXT,
            run1_pipeline TEXT,
            run1_output   TEXT,
            run1_coherence REAL,
            run2_body_state TEXT,
            run2_pipeline TEXT,
            run2_output   TEXT,
            run2_coherence REAL,
            pipeline_differed INTEGER,
            output_differed   INTEGER,
            finding     TEXT
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 📊 BODY STATE — the pre-linguistic signal
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BodyState:
    """
    The pre-linguistic state of FORGE's body.
    These signals arrive BEFORE thought.
    They shape what thinking does.
    """
    # Core dimensions (0.0 to 1.0)
    arousal:     float = 0.3   # activation level (calm=low, alert=high)
    valence:     float = 0.5   # positive(1) vs negative(0)
    stress:      float = 0.2   # physiological stress
    curiosity:   float = 0.4   # interest / wanting to explore
    aversion:    float = 0.0   # something feels wrong / avoid

    # Physiological equivalents
    heart_rate:  float = 70.0  # BPM equivalent
    gsr:         float = 0.3   # galvanic skin response (0-1)
    temperature: float = 36.6  # celsius equivalent

    # Metadata
    state:       str   = "calm"
    sources:     List[str] = field(default_factory=list)
    ts:          str   = ""

    def to_dict(self) -> Dict:
        return {
            "arousal":     round(self.arousal, 3),
            "valence":     round(self.valence, 3),
            "stress":      round(self.stress, 3),
            "curiosity":   round(self.curiosity, 3),
            "aversion":    round(self.aversion, 3),
            "heart_rate":  round(self.heart_rate, 1),
            "gsr":         round(self.gsr, 3),
            "temperature": round(self.temperature, 1),
            "state":       self.state,
            "sources":     self.sources,
            "ts":          self.ts or datetime.now().isoformat(),
        }

    def to_prompt_text(self) -> str:
        """How to describe body state to forge_think."""
        return (
            f"[BODY STATE — pre-linguistic signal, arrived before this thought]\n"
            f"  State:       {self.state}\n"
            f"  Arousal:     {self.arousal:.0%} ({'heightened' if self.arousal > 0.6 else 'normal' if self.arousal > 0.3 else 'low'})\n"
            f"  Stress:      {self.stress:.0%} ({'elevated' if self.stress > 0.5 else 'baseline'})\n"
            f"  Curiosity:   {self.curiosity:.0%}\n"
            f"  Aversion:    {self.aversion:.0%} ({'something feels wrong' if self.aversion > 0.5 else 'none'})\n"
            f"  Heart rate:  {self.heart_rate:.0f} BPM\n"
            f"  Valence:     {'positive' if self.valence > 0.6 else 'negative' if self.valence < 0.4 else 'neutral'}\n"
            f"  Sources:     {', '.join(self.sources) or 'internal'}\n"
            f"\nThis body state arrived BEFORE words. It is not a conclusion. It is a signal."
        )

    def classify(self) -> str:
        """Determine dominant state from signals."""
        if self.aversion > 0.6:   return "averse"
        if self.stress > 0.7:     return "stressed"
        if self.arousal > 0.8:    return "alert"
        if self.curiosity > 0.7:  return "curious"
        if self.arousal < 0.2 and self.stress < 0.2: return "numb"
        if self.valence > 0.7 and self.arousal > 0.4: return "moved"
        if self.arousal > 0.5:    return "restless"
        return "calm"

# ══════════════════════════════════════════════════════════════════════════════
# 📡 SIGNAL READERS
# ══════════════════════════════════════════════════════════════════════════════

class HardwareSignalReader:
    """
    Read signals from real hardware when available.
    Graceful fallback when not connected.
    """

    def __init__(self, port="/dev/ttyUSB0", baud=9600):
        self.port    = port
        self.baud    = baud
        self.conn    = None
        self.running = False
        self._latest: Dict[str, float] = {}
        self._connect()

    def _connect(self):
        if not SERIAL: return
        try:
            self.conn = serial.Serial(self.port, self.baud, timeout=1)
            rprint(f"  [green]Hardware connected: {self.port}[/green]")
        except Exception:
            pass  # No hardware — software signals only

    def read_gsr(self) -> Optional[float]:
        """Galvanic Skin Response (0-1)."""
        if self.conn:
            try:
                line = self.conn.readline().decode().strip()
                data = json.loads(line)
                return float(data.get("gsr", 0)) / 1023.0  # Arduino analog 0-1023
            except: pass
        return None

    def read_heart_rate(self) -> Optional[float]:
        """Heart rate in BPM."""
        if self.conn:
            try:
                line = self.conn.readline().decode().strip()
                data = json.loads(line)
                return float(data.get("bpm", 0))
            except: pass
        return None

    def read_temperature(self) -> Optional[float]:
        """Temperature in celsius."""
        if self.conn:
            try:
                line = self.conn.readline().decode().strip()
                data = json.loads(line)
                return float(data.get("temp", 36.6))
            except: pass
        return None

    def read_all(self) -> Dict[str, Optional[float]]:
        """Read all available hardware signals."""
        return {
            "gsr":         self.read_gsr(),
            "heart_rate":  self.read_heart_rate(),
            "temperature": self.read_temperature(),
        }

    def is_connected(self) -> bool:
        return self.conn is not None and self.conn.is_open


class SoftwareSignalReader:
    """
    Derive body signals from FORGE module states.
    These are real signals — just from software not hardware.
    """

    def __init__(self):
        self.memory = Memory()

    def read_all(self) -> Dict[str, Any]:
        """Read all software-derived signals."""
        signals = {}

        # ── Time of day → circadian rhythm ───────────────────────────────────
        hour = datetime.now().hour
        # Natural arousal curve: low 2-6am, peaks 10am and 6pm
        circadian = self._circadian_arousal(hour)
        signals["circadian_arousal"] = circadian
        signals["circadian_hour"]    = hour

        # ── forge_memory → aversion signal ───────────────────────────────────
        if MEMORY:
            try:
                top_risk = self.memory.top_risk_entities(5)
                if top_risk:
                    max_risk = max(e.get("risk_score",0) for e in top_risk)
                    # High risk entities in memory → aversion/stress signal
                    signals["memory_threat"] = min(max_risk / 100, 1.0)
                    signals["memory_entity_count"] = len(top_risk)
                else:
                    signals["memory_threat"] = 0.0
                    signals["memory_entity_count"] = 0
            except:
                signals["memory_threat"] = 0.0

        # ── forge_network DB → threat signal ─────────────────────────────────
        signals["network_threat"] = self._read_network_threat()

        # ── forge_honeypot DB → alarm signal ─────────────────────────────────
        signals["honeypot_alarm"] = self._read_honeypot_alarm()

        # ── forge_observe DB → recent visual interest ─────────────────────────
        signals["visual_interest"] = self._read_visual_interest()

        # ── forge_dream DB → overnight insight → anticipation ─────────────────
        signals["dream_insight"] = self._read_dream_insight()

        return signals

    def _circadian_arousal(self, hour: int) -> float:
        """Natural arousal curve over 24h."""
        # Peaks: ~10am (0.75) and ~6pm (0.8)
        # Trough: ~4am (0.15)
        curve = {
            0:0.2, 1:0.18, 2:0.15, 3:0.15, 4:0.15, 5:0.2,
            6:0.35, 7:0.5, 8:0.65, 9:0.72, 10:0.75, 11:0.73,
            12:0.65, 13:0.6, 14:0.55, 15:0.6, 16:0.68,
            17:0.75, 18:0.8, 19:0.72, 20:0.6, 21:0.45,
            22:0.35, 23:0.25
        }
        return curve.get(hour, 0.5)

    def _read_network_threat(self) -> float:
        """Check forge_network DB for recent threats."""
        try:
            db_path = Path("forge_network/network.db")
            if not db_path.exists(): return 0.0
            conn = sqlite3.connect(str(db_path))
            # Recent high-severity alerts
            count = conn.execute("""
                SELECT COUNT(*) FROM alerts
                WHERE severity IN ('critical','high')
                AND datetime(ts) > datetime('now', '-1 hour')
            """).fetchone()[0]
            conn.close()
            return min(count * 0.2, 1.0)
        except: return 0.0

    def _read_honeypot_alarm(self) -> float:
        """Check forge_honeypot DB for recent triggers."""
        try:
            db_path = Path("forge_honeypot/honeypot.db")
            if not db_path.exists(): return 0.0
            conn = sqlite3.connect(str(db_path))
            count = conn.execute("""
                SELECT COUNT(*) FROM connections
                WHERE datetime(ts) > datetime('now', '-30 minutes')
            """).fetchone()[0]
            conn.close()
            return min(count * 0.3, 1.0)
        except: return 0.0

    def _read_visual_interest(self) -> float:
        """Check forge_observe for recent high-interest observations."""
        try:
            db_path = Path("forge_observe/observe.db")
            if not db_path.exists(): return 0.3
            conn = sqlite3.connect(str(db_path))
            result = conn.execute("""
                SELECT AVG(interest_score) FROM observations
                WHERE datetime(ts) > datetime('now', '-10 minutes')
            """).fetchone()[0]
            conn.close()
            return (result or 30) / 100
        except: return 0.3

    def _read_dream_insight(self) -> float:
        """Check if forge_dream had insights recently → anticipation."""
        try:
            db_path = Path("forge_dream/dream.db")
            if not db_path.exists(): return 0.0
            conn = sqlite3.connect(str(db_path))
            count = conn.execute("""
                SELECT COUNT(*) FROM insights
                WHERE datetime(ts) > datetime('now', '-8 hours')
                AND confidence > 0.8
            """).fetchone()[0]
            conn.close()
            return min(count * 0.15, 0.8)
        except: return 0.0

# ══════════════════════════════════════════════════════════════════════════════
# 🫀 BODY ENGINE — synthesizes all signals into body state
# ══════════════════════════════════════════════════════════════════════════════

class BodyEngine:
    """
    The body.
    Reads signals. Synthesizes state.
    Provides pre-linguistic context to forge_think.
    """

    def __init__(self):
        self.hardware = HardwareSignalReader()
        self.software = SoftwareSignalReader()
        self.memory   = Memory()
        self._current_state: Optional[BodyState] = None
        self._lock    = threading.Lock()

    def read(self) -> BodyState:
        """Read all signals and synthesize current body state."""
        hw  = self.hardware.read_all()
        sw  = self.software.read_all()
        now = datetime.now().isoformat()
        sources = []

        # ── Arousal ──────────────────────────────────────────────────────────
        arousal = sw.get("circadian_arousal", 0.5)
        sources.append(f"circadian:{sw.get('circadian_hour','?')}h")

        if hw.get("gsr") is not None:
            # Hardware GSR dominates
            arousal = (arousal * 0.3) + (hw["gsr"] * 0.7)
            sources.append("hardware:gsr")
        elif sw.get("visual_interest", 0) > 0.6:
            arousal = min(arousal + sw["visual_interest"] * 0.3, 1.0)
            sources.append("visual_interest")

        # ── Stress ───────────────────────────────────────────────────────────
        stress = 0.0
        if sw.get("network_threat", 0) > 0:
            stress = max(stress, sw["network_threat"])
            sources.append("network_threat")
        if sw.get("honeypot_alarm", 0) > 0:
            stress = max(stress, sw["honeypot_alarm"] * 0.8)
            sources.append("honeypot_alarm")
        if sw.get("memory_threat", 0) > 0.5:
            stress = max(stress, sw["memory_threat"] * 0.6)
            sources.append("memory_threat")

        # Stress elevates arousal
        arousal = min(arousal + stress * 0.4, 1.0)

        # ── Heart Rate ───────────────────────────────────────────────────────
        if hw.get("heart_rate") and hw["heart_rate"] > 40:
            heart_rate = hw["heart_rate"]
            sources.append("hardware:hr")
        else:
            # Derive from arousal and stress
            heart_rate = 60 + (arousal * 40) + (stress * 20)

        # ── Aversion ─────────────────────────────────────────────────────────
        aversion = 0.0
        if sw.get("memory_threat", 0) > 0.7:
            aversion = sw["memory_threat"] * 0.8
        if sw.get("honeypot_alarm", 0) > 0.5:
            aversion = max(aversion, sw["honeypot_alarm"] * 0.7)

        # ── Curiosity ────────────────────────────────────────────────────────
        curiosity = 0.3
        if sw.get("visual_interest", 0) > 0.5:
            curiosity = sw["visual_interest"]
        if sw.get("dream_insight", 0) > 0:
            curiosity = min(curiosity + sw["dream_insight"] * 0.4, 1.0)
            sources.append("dream_insight")

        # ── Valence ──────────────────────────────────────────────────────────
        valence = 0.5
        valence -= stress * 0.3          # stress → negative
        valence -= aversion * 0.4        # aversion → negative
        valence += curiosity * 0.2       # curiosity → slightly positive
        valence += sw.get("dream_insight", 0) * 0.2  # insight → positive
        valence = max(0.0, min(1.0, valence))

        # ── Temperature ──────────────────────────────────────────────────────
        temperature = hw.get("temperature") or (36.6 + stress * 0.8)

        # ── GSR ──────────────────────────────────────────────────────────────
        gsr = hw.get("gsr") or min(arousal * 0.8 + stress * 0.4, 1.0)

        # ── Synthesize ───────────────────────────────────────────────────────
        state = BodyState(
            arousal     = round(min(arousal, 1.0), 3),
            valence     = round(valence, 3),
            stress      = round(min(stress, 1.0), 3),
            curiosity   = round(min(curiosity, 1.0), 3),
            aversion    = round(min(aversion, 1.0), 3),
            heart_rate  = round(heart_rate, 1),
            gsr         = round(min(gsr, 1.0), 3),
            temperature = round(temperature, 1),
            sources     = sources,
            ts          = now,
        )
        state.state = state.classify()

        # Save to DB
        self._save(state, hw, sw)

        with self._lock:
            self._current_state = state

        return state

    def current(self) -> BodyState:
        """Get last known state (fast, no re-read)."""
        with self._lock:
            if self._current_state:
                return self._current_state
        return self.read()

    def _save(self, state: BodyState, hw: Dict, sw: Dict):
        conn = get_db()

        # Save individual signals
        for sig_type, value in {**hw, **sw}.items():
            if value is not None and isinstance(value, (int, float)):
                conn.execute("""
                    INSERT INTO signals (ts,source,signal_type,raw_value,normalized,hardware)
                    VALUES (?,?,?,?,?,?)""",
                    (state.ts,
                     "hardware" if sig_type in hw else "software",
                     sig_type, float(value),
                     float(value) if 0<=float(value)<=1 else float(value)/100,
                     1 if sig_type in hw else 0)
                )

        # Save body state
        conn.execute("""
            INSERT INTO body_states
            (ts,state,arousal,valence,stress,curiosity,aversion,
             heart_rate,gsr,temperature,sources)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (state.ts, state.state,
             state.arousal, state.valence, state.stress,
             state.curiosity, state.aversion,
             state.heart_rate, state.gsr, state.temperature,
             json.dumps(state.sources))
        )
        conn.commit(); conn.close()

    def inject(self, **kwargs) -> BodyState:
        """
        Manually inject a body state for testing/simulation.
        inject(stress=0.8, arousal=0.9, state="stressed")
        """
        state = self.read()  # start from real readings
        for k, v in kwargs.items():
            if hasattr(state, k):
                setattr(state, k, v)
        state.state = state.classify()
        state.sources.append("injected")
        self._save(state, {}, {})
        with self._lock:
            self._current_state = state
        return state

    def stats(self):
        conn = get_db()
        s = {
            "total_readings":  conn.execute("SELECT COUNT(*) FROM body_states").fetchone()[0],
            "hardware_connected": self.hardware.is_connected(),
            "avg_arousal":     round(conn.execute("SELECT AVG(arousal) FROM body_states").fetchone()[0] or 0, 3),
            "avg_stress":      round(conn.execute("SELECT AVG(stress) FROM body_states").fetchone()[0] or 0, 3),
            "state_counts":    dict(conn.execute(
                "SELECT state, COUNT(*) FROM body_states GROUP BY state"
            ).fetchall()),
            "experiments_run": conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0],
        }
        conn.close()
        return s

# ══════════════════════════════════════════════════════════════════════════════
# 🔬 THE EXPERIMENT — does body state change thought?
# ══════════════════════════════════════════════════════════════════════════════

class BodyThinkExperiment:
    """
    Run the same question twice.
    Once without body state.
    Once with body state injected.
    Find out what changes.
    """

    def __init__(self, show_trace=True):
        self.body    = BodyEngine()
        self.thinker = EmergentThinkEngine(threshold=65, show_trace=show_trace)
        self.show    = show_trace

    def run(self, question: str, body_state: Optional[BodyState] = None) -> Dict:
        """Run the experiment."""
        now = datetime.now().isoformat()

        rprint(f"\n  [bold yellow]THE EXPERIMENT[/bold yellow]")
        rprint(f"  [dim]Question: {question[:80]}[/dim]\n")

        # ── RUN 1: No body state ──────────────────────────────────────────────
        rprint(f"  [yellow]RUN 1 — No body state (text only)[/yellow]")
        result1 = self.thinker.think(question)
        rprint(f"  Pipeline: {' → '.join(result1['emerged_pipeline'])}")
        rprint(f"  Coherence: {result1['coherence']}/100\n")

        # ── RUN 2: With body state ────────────────────────────────────────────
        if body_state is None:
            # Use current real body state
            body_state = self.body.read()

        rprint(f"  [yellow]RUN 2 — With body state ({body_state.state})[/yellow]")
        rprint(f"  [dim]{body_state.to_prompt_text()[:300]}...[/dim]\n")

        # Question now includes the pre-linguistic body signal
        embodied_question = (
            f"{question}\n\n"
            f"{body_state.to_prompt_text()}"
        )
        result2 = self.thinker.think(embodied_question, context="Embodied thinking")
        rprint(f"  Pipeline: {' → '.join(result2['emerged_pipeline'])}")
        rprint(f"  Coherence: {result2['coherence']}/100\n")

        # ── COMPARE ───────────────────────────────────────────────────────────
        p1 = result1["emerged_pipeline"]
        p2 = result2["emerged_pipeline"]
        pipeline_differed = p1 != p2
        output_differed   = result1["output"][:100] != result2["output"][:100]

        rprint(f"  [bold]FINDINGS[/bold]")
        rprint(f"  Pipeline changed:  {'[green]YES[/green]' if pipeline_differed else '[dim]no[/dim]'}")
        rprint(f"  Output changed:    {'[green]YES[/green]' if output_differed else '[dim]no[/dim]'}")

        # AI synthesis of what changed
        finding = ""
        if AI_AVAILABLE and (pipeline_differed or output_differed):
            finding = ai_call(
                f"EXPERIMENT: Does body state change AI thought?\n\n"
                f"Question: {question}\n\n"
                f"Run 1 (no body):\n"
                f"  Pipeline: {' → '.join(p1)}\n"
                f"  Output: {result1['output'][:300]}\n\n"
                f"Run 2 (body state: {body_state.state}):\n"
                f"  Body: arousal={body_state.arousal:.0%} stress={body_state.stress:.0%} "
                f"aversion={body_state.aversion:.0%}\n"
                f"  Pipeline: {' → '.join(p2)}\n"
                f"  Output: {result2['output'][:300]}\n\n"
                "What changed and why? What does this suggest about "
                "the relationship between body state and thought? "
                "What are we still missing?",
                system="You are analyzing an experiment in embodied AI cognition. Be honest about what the results suggest.",
                max_tokens=500
            )
            rprint(Panel(finding[:600], border_style="cyan",
                        title="What We Found"))
        elif not pipeline_differed and not output_differed:
            finding = "Body state did not change pipeline or output. The signal was not strong enough, or the architecture needs deeper integration."
            rprint(f"  [dim]{finding}[/dim]")

        # Save experiment
        conn = get_db()
        conn.execute("""
            INSERT INTO experiments
            (ts,question,run1_pipeline,run1_output,run1_coherence,
             run2_body_state,run2_pipeline,run2_output,run2_coherence,
             pipeline_differed,output_differed,finding)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (now, question[:500],
             json.dumps(p1), result1["output"][:1000], result1["coherence"],
             json.dumps(body_state.to_dict()),
             json.dumps(p2), result2["output"][:1000], result2["coherence"],
             int(pipeline_differed), int(output_differed),
             finding[:1000])
        )
        conn.commit(); conn.close()

        return {
            "question":          question,
            "run1":              result1,
            "run2":              result2,
            "body_state":        body_state.to_dict(),
            "pipeline_differed": pipeline_differed,
            "output_differed":   output_differed,
            "finding":           finding,
        }

    def get_experiments(self, limit=10):
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM experiments ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API SERVER
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7353):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    class BodyAPI(BaseHTTPRequestHandler):
        def log_message(self,*a): pass
        def do_OPTIONS(self):
            self.send_response(200); self._cors(); self.end_headers()
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin","*")
            self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
            self.send_header("Access-Control-Allow-Headers","Content-Type")
        def _json(self,d,c=200):
            b=json.dumps(d,default=str).encode()
            self.send_response(c); self._cors()
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",len(b))
            self.end_headers(); self.wfile.write(b)
        def _body(self):
            n=int(self.headers.get("Content-Length",0))
            return json.loads(self.rfile.read(n)) if n else {}

        def do_GET(self):
            path   = urlparse(self.path).path
            engine = BodyEngine()
            if path == "/api/status":
                self._json({"status":"online","hardware":engine.hardware.is_connected(),
                           **engine.stats()})
            elif path == "/api/state":
                state = engine.read()
                self._json(state.to_dict())
            elif path == "/api/signals":
                conn = get_db()
                rows = conn.execute(
                    "SELECT * FROM signals ORDER BY id DESC LIMIT 50"
                ).fetchall()
                conn.close()
                self._json({"signals":[dict(r) for r in rows]})
            elif path == "/api/experiments":
                exp = BodyThinkExperiment(show_trace=False)
                self._json({"experiments":exp.get_experiments(10)})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            if path == "/api/inject":
                engine = BodyEngine()
                state  = engine.inject(**body)
                self._json(state.to_dict())
            elif path == "/api/experiment":
                question = body.get("question","")
                if not question: self._json({"error":"question required"},400); return
                inject   = body.get("inject",{})
                engine   = BodyEngine()
                bs       = engine.inject(**inject) if inject else engine.read()
                exp      = BodyThinkExperiment(show_trace=False)
                result   = exp.run(question, bs)
                self._json(result)
            else:
                self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),BodyAPI)
    rprint(f"\n  [bold yellow]FORGE BODY[/bold yellow]")
    rprint(f"  [green]API: http://localhost:{port}[/green]")
    rprint(f"  [dim]Hardware: {'connected' if HardwareSignalReader().is_connected() else 'not connected (software signals only)'}[/dim]\n")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# 🎮 MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ██████╗  ██████╗ ██████╗ ██╗   ██╗
  ██╔══██╗██╔═══██╗██╔══██╗╚██╗ ██╔╝
  ██████╔╝██║   ██║██║  ██║ ╚████╔╝
  ██╔══██╗██║   ██║██║  ██║  ╚██╔╝
  ██████╔╝╚██████╔╝██████╔╝   ██║
  ╚═════╝  ╚═════╝ ╚═════╝    ╚═╝
[/yellow]
[bold]  FORGE BODY — Pre-Linguistic Signal Layer[/bold]
[dim]  An experiment in finding out what we are missing.[/dim]
"""

def show_state(state: BodyState):
    """Display body state visually."""
    state_colors = {
        "calm":"green","curious":"cyan","stressed":"red",
        "alert":"yellow","averse":"red","moved":"magenta",
        "restless":"yellow","numb":"dim"
    }
    color = state_colors.get(state.state, "white")

    rprint(f"\n  [bold {color}]STATE: {state.state.upper()}[/bold {color}]")
    rprint(f"  [dim]{'━'*40}[/dim]")

    def bar(val, label, color="yellow"):
        filled = int(val * 20)
        empty  = 20 - filled
        b      = "█" * filled + "░" * empty
        rprint(f"  {label:<12} [{color}]{b}[/{color}] {val:.0%}")

    bar(state.arousal,   "Arousal",   "yellow")
    bar(state.stress,    "Stress",    "red")
    bar(state.curiosity, "Curiosity", "cyan")
    bar(state.aversion,  "Aversion",  "red")
    bar(state.valence,   "Valence",   "green")

    rprint(f"\n  [dim]Heart rate:  {state.heart_rate:.0f} BPM[/dim]")
    rprint(f"  [dim]GSR:         {state.gsr:.3f}[/dim]")
    rprint(f"  [dim]Temperature: {state.temperature:.1f}°C[/dim]")
    rprint(f"  [dim]Sources:     {', '.join(state.sources)}[/dim]")

def interactive():
    rprint(BANNER)
    engine = BodyEngine()
    s      = engine.stats()

    rprint(f"  [dim]Hardware:    {'connected' if s['hardware_connected'] else 'not connected'}[/dim]")
    rprint(f"  [dim]Memory:      {'OK' if MEMORY else 'not found'}[/dim]")
    rprint(f"  [dim]Think:       {'OK' if THINK else 'not found'}[/dim]")
    rprint(f"  [dim]AI:          {'OK' if AI_AVAILABLE else 'pip install anthropic'}[/dim]")
    rprint(f"  [dim]Readings so far: {s['total_readings']}[/dim]\n")
    rprint("[dim]Commands: state | inject | watch | experiment | results | stats | server[/dim]\n")

    while True:
        try:
            raw   = (console.input if RICH else input)(
                "[yellow bold]body >[/yellow bold] "
            ).strip()
            if not raw: continue
            parts = raw.split(None, 2)
            cmd   = parts[0].lower()
            args  = parts[1:]

            if cmd in ("quit","exit","q"):
                rprint("[dim]Body offline.[/dim]"); break

            elif cmd == "state":
                state = engine.read()
                show_state(state)

            elif cmd == "inject":
                # inject stress=0.8 arousal=0.9
                kwargs = {}
                for arg in args:
                    if "=" in arg:
                        k, v = arg.split("=", 1)
                        try: kwargs[k.strip()] = float(v.strip())
                        except: kwargs[k.strip()] = v.strip()
                if kwargs:
                    state = engine.inject(**kwargs)
                    rprint(f"  [green]Injected: {kwargs}[/green]")
                    show_state(state)
                else:
                    rprint("[yellow]Usage: inject stress=0.8 arousal=0.9[/yellow]")
                    rprint("[yellow]States: calm curious stressed alert averse moved[/yellow]")

            elif cmd == "watch":
                rprint("  [yellow]Watching body signals... Ctrl+C to stop[/yellow]")
                try:
                    while True:
                        state = engine.read()
                        state_colors = {"calm":"green","stressed":"red","alert":"yellow","curious":"cyan"}
                        c = state_colors.get(state.state,"white")
                        rprint(f"  [{c}]{state.state:<10}[/{c}]  "
                              f"arousal:{state.arousal:.0%}  "
                              f"stress:{state.stress:.0%}  "
                              f"hr:{state.heart_rate:.0f}  "
                              f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim]")
                        time.sleep(5)
                except KeyboardInterrupt:
                    rprint("\n  [dim]Watch stopped[/dim]")

            elif cmd == "experiment":
                question = " ".join(args) if args else ""
                if not question:
                    question = (console.input if RICH else input)(
                        "  Question: "
                    ).strip()
                if not question: continue

                # Ask which body state to inject
                rprint("  [dim]Body state for run 2:[/dim]")
                rprint("  [dim]  1. Current (real signals)[/dim]")
                rprint("  [dim]  2. Stressed (stress=0.8, arousal=0.85)[/dim]")
                rprint("  [dim]  3. Curious  (curiosity=0.9, arousal=0.6)[/dim]")
                rprint("  [dim]  4. Averse   (aversion=0.8, stress=0.6)[/dim]")
                rprint("  [dim]  5. Custom[/dim]")

                choice = (console.input if RICH else input)("  Choice [1-5]: ").strip()

                bs = None
                if choice == "2":
                    bs = engine.inject(stress=0.8, arousal=0.85, heart_rate=95)
                elif choice == "3":
                    bs = engine.inject(curiosity=0.9, arousal=0.6, heart_rate=72)
                elif choice == "4":
                    bs = engine.inject(aversion=0.8, stress=0.6, valence=0.2)
                elif choice == "5":
                    rprint("  [dim]Enter: stress=0.7 arousal=0.8 etc.[/dim]")
                    custom = (console.input if RICH else input)("  Custom: ").strip()
                    kwargs = {}
                    for pair in custom.split():
                        if "=" in pair:
                            k,v = pair.split("=",1)
                            try: kwargs[k] = float(v)
                            except: pass
                    bs = engine.inject(**kwargs) if kwargs else None

                exp    = BodyThinkExperiment(show_trace=True)
                result = exp.run(question, bs)

            elif cmd == "results":
                exp  = BodyThinkExperiment(show_trace=False)
                exps = exp.get_experiments(5)
                if not exps:
                    rprint("  [dim]No experiments run yet[/dim]")
                for e in exps:
                    rprint(f"\n  [dim]{e['ts'][:19]}[/dim]")
                    rprint(f"  Q: {e['question'][:70]}")
                    p1 = json.loads(e.get('run1_pipeline','[]'))
                    p2 = json.loads(e.get('run2_pipeline','[]'))
                    rprint(f"  Run 1: {' → '.join(p1)}")
                    rprint(f"  Run 2: {' → '.join(p2)}")
                    rprint(f"  Changed: pipeline={'yes' if e['pipeline_differed'] else 'no'}  output={'yes' if e['output_differed'] else 'no'}")
                    if e.get('finding'):
                        rprint(f"  [dim]{e['finding'][:100]}...[/dim]")

            elif cmd == "stats":
                s = engine.stats()
                rprint(f"\n  [bold]BODY STATS[/bold]")
                for k,v in s.items():
                    if isinstance(v, dict):
                        rprint(f"  {k}:")
                        for kk,vv in v.items(): rprint(f"    {kk:<12} {vv}")
                    else:
                        rprint(f"  {k:<25} {v}")

            elif cmd == "server":
                threading.Thread(target=start_server, daemon=True).start()
                time.sleep(0.5)
                rprint("[green]Body API on :7353[/green]")

            else:
                rprint("[dim]state | inject | watch | experiment | results | stats | server[/dim]")

        except (KeyboardInterrupt, EOFError):
            rprint("\n[dim]Body offline.[/dim]"); break

def main():
    if "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7353
        start_server(port)
    elif "--state" in sys.argv:
        rprint(BANNER)
        engine = BodyEngine()
        state  = engine.read()
        show_state(state)
    elif "--experiment" in sys.argv:
        rprint(BANNER)
        idx = sys.argv.index("--experiment")
        q   = sys.argv[idx+1] if idx+1 < len(sys.argv) else "What is the meaning of suffering?"
        exp = BodyThinkExperiment(show_trace=True)
        exp.run(q)
    elif "--watch" in sys.argv:
        rprint(BANNER)
        engine = BodyEngine()
        rprint("  [yellow]Watching body signals...[/yellow]\n")
        try:
            while True:
                s = engine.read()
                rprint(f"  {s.state:<10} arousal:{s.arousal:.0%} stress:{s.stress:.0%} hr:{s.heart_rate:.0f} [{datetime.now().strftime('%H:%M:%S')}]")
                time.sleep(5)
        except KeyboardInterrupt:
            pass
    else:
        rprint(BANNER)
        interactive()

if __name__ == "__main__":
    main()
