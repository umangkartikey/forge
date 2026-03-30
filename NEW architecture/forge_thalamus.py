"""
FORGE Thalamus — forge_thalamus.py
====================================
AI analog of the brain's thalamic relay system.

The thalamus is the brain's central switchboard — almost every
signal entering the brain passes through it. But it is NOT a
passive relay. It is an active, intelligent gatekeeper that:

  1. Routes signals to the correct cortical modules
  2. Amplifies weak-but-important signals
  3. Suppresses irrelevant noise
  4. Manages consciousness state (awake/drowsy/crisis/focused)
  5. Synchronizes all modules with a cognitive rhythm
  6. Prevents cognitive overload via load balancing
  7. Gates external input during DMN reflection periods

Without the thalamus, FORGE processes every signal the same way.
With it, FORGE has selective attention, cognitive rhythm, and
something approaching a unified conscious state.

Architecture:
  SensoryRelay       → intelligent routing to correct modules
  AttentionGate      → per-module open/close/amplify/dampen
  ConsciousnessEngine→ AWAKE/DROWSY/FOCUSED/CRISIS/DREAMING state
  LoadBalancer       → prevents cognitive overload
  SignalAmplifier    → boosts weak-but-important signals
  NoiseFilter        → suppresses irrelevant background
  ThalamicClock      → synchronizes all modules (cognitive rhythm)
  SleepWakeCycle     → FORGE's circadian-like cycle
  ThalamicMemory     → short-term signal queue during suppression
"""

import json
import time
import uuid
import sqlite3
import threading
import math
from datetime import datetime, timedelta
from collections import deque, defaultdict
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.columns import Columns
    from rich.rule import Rule
    from rich.text import Text
    from rich.layout import Layout
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

DB_PATH  = "forge_thalamus.db"
API_PORT = 7790
VERSION  = "1.0.0"

# Load thresholds
LOAD_CRITICAL  = 0.85
LOAD_HIGH      = 0.65
LOAD_MODERATE  = 0.40
LOAD_LOW       = 0.20

# Clock frequency (cognitive ticks per second)
CLOCK_FREQ_HZ  = 2.0

# Sleep/wake cycle
SLEEP_THRESHOLD_IDLE_SECS = 60.0   # no signals for this long → drowsy
WAKE_ON_THREAT            = 2      # threat >= this instantly wakes

console = Console() if HAS_RICH else None

# ─── Enums ────────────────────────────────────────────────────────────────────

class ConsciousnessState(Enum):
    AWAKE     = "AWAKE"      # normal full awareness
    FOCUSED   = "FOCUSED"    # locked onto specific task/entity
    DROWSY    = "DROWSY"     # reduced sensitivity, slower processing
    CRISIS    = "CRISIS"     # maximum threat — narrowed to survival channels
    DREAMING  = "DREAMING"   # DMN dominant — external input dampened
    RECOVERING= "RECOVERING" # post-crisis — rebuilding normal state

class GateState(Enum):
    OPEN      = "OPEN"       # full signal flow
    AMPLIFIED = "AMPLIFIED"  # signal boosted
    DAMPENED  = "DAMPENED"   # signal reduced
    CLOSED    = "CLOSED"     # no signal passes
    QUEUED    = "QUEUED"     # signal held for later

class SignalPriority(Enum):
    CRITICAL  = 5
    HIGH      = 4
    NORMAL    = 3
    LOW       = 2
    BACKGROUND= 1

class ClockPhase(Enum):
    INTEGRATE = "INTEGRATE"  # gather inputs
    PROCESS   = "PROCESS"    # cognitive processing
    OUTPUT    = "OUTPUT"     # dispatch responses
    REST      = "REST"       # brief recovery

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class ThalamicGate:
    """Per-module attention gate."""
    module:      str   = ""
    state:       str   = GateState.OPEN.value
    gain:        float = 1.0     # signal multiplier (0.0 - 2.0)
    threshold:   float = 0.0     # minimum salience to pass
    queue:       deque = field(default_factory=lambda: deque(maxlen=20))
    pass_count:  int   = 0
    block_count: int   = 0
    last_signal: str   = ""

@dataclass
class ThalamicSignal:
    """A signal processed by the thalamus."""
    id:              str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:       str   = field(default_factory=lambda: datetime.now().isoformat())
    raw_threat:      int   = 0
    raw_salience:    float = 0.5
    adjusted_salience:float= 0.5
    priority:        str   = SignalPriority.NORMAL.value
    routing:         dict  = field(default_factory=dict)
    consciousness_state: str = ConsciousnessState.AWAKE.value
    load_at_entry:   float = 0.0
    amplified:       bool  = False
    filtered:        bool  = False
    queued:          bool  = False
    processing_ms:   float = 0.0

@dataclass
class ClockTick:
    """One tick of the thalamic clock."""
    tick:        int   = 0
    timestamp:   str   = field(default_factory=lambda: datetime.now().isoformat())
    phase:       str   = ClockPhase.INTEGRATE.value
    consciousness:str  = ConsciousnessState.AWAKE.value
    load:        float = 0.0
    gates_open:  int   = 0
    gates_closed:int   = 0
    signals_this_tick: int = 0

@dataclass
class CognitiveCycle:
    """One full INTEGRATE→PROCESS→OUTPUT→REST cycle."""
    id:          str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    start:       str   = field(default_factory=lambda: datetime.now().isoformat())
    ticks:       int   = 0
    signals_processed: int = 0
    avg_load:    float = 0.0
    dominant_state: str = ConsciousnessState.AWAKE.value
    insights_enabled: bool = True

# ─── Database ─────────────────────────────────────────────────────────────────

class ThalamicDB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init()

    def _init(self):
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS thalamic_signals (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    raw_threat INTEGER, raw_salience REAL,
                    adjusted_salience REAL, priority TEXT,
                    routing TEXT, consciousness_state TEXT,
                    load_at_entry REAL, amplified INTEGER,
                    filtered INTEGER, queued INTEGER,
                    processing_ms REAL
                );
                CREATE TABLE IF NOT EXISTS clock_ticks (
                    tick INTEGER PRIMARY KEY, timestamp TEXT,
                    phase TEXT, consciousness TEXT, load REAL,
                    gates_open INTEGER, gates_closed INTEGER,
                    signals_this_tick INTEGER
                );
                CREATE TABLE IF NOT EXISTS consciousness_log (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    from_state TEXT, to_state TEXT,
                    trigger TEXT, load REAL
                );
                CREATE TABLE IF NOT EXISTS gate_log (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    module TEXT, old_state TEXT, new_state TEXT,
                    reason TEXT
                );
            """)
            self.conn.commit()

    def save_signal(self, s: ThalamicSignal):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO thalamic_signals VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (s.id, s.timestamp, s.raw_threat, s.raw_salience,
                  s.adjusted_salience, s.priority,
                  json.dumps(s.routing), s.consciousness_state,
                  s.load_at_entry, int(s.amplified),
                  int(s.filtered), int(s.queued), s.processing_ms))
            self.conn.commit()

    def save_tick(self, t: ClockTick):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO clock_ticks VALUES
                (?,?,?,?,?,?,?,?)
            """, (t.tick, t.timestamp, t.phase, t.consciousness,
                  t.load, t.gates_open, t.gates_closed,
                  t.signals_this_tick))
            self.conn.commit()

    def log_consciousness_change(self, from_s: str, to_s: str,
                                  trigger: str, load: float):
        with self.lock:
            self.conn.execute("""
                INSERT INTO consciousness_log VALUES (?,?,?,?,?,?)
            """, (str(uuid.uuid4())[:8], datetime.now().isoformat(),
                  from_s, to_s, trigger, load))
            self.conn.commit()

    def log_gate_change(self, module: str, old: str, new: str, reason: str):
        with self.lock:
            self.conn.execute("""
                INSERT INTO gate_log VALUES (?,?,?,?,?,?)
            """, (str(uuid.uuid4())[:8], datetime.now().isoformat(),
                  module, old, new, reason))
            self.conn.commit()

    def get_recent_signals(self, limit=20):
        with self.lock:
            return self.conn.execute("""
                SELECT id, timestamp, raw_threat, adjusted_salience,
                       priority, consciousness_state, amplified,
                       filtered, processing_ms
                FROM thalamic_signals ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()

    def get_consciousness_log(self, limit=20):
        with self.lock:
            return self.conn.execute("""
                SELECT timestamp, from_state, to_state, trigger
                FROM consciousness_log ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()


# ─── Consciousness Engine ─────────────────────────────────────────────────────

class ConsciousnessEngine:
    """
    Manages FORGE's overall consciousness state.
    State determines how the thalamus processes everything else.

    Transitions:
      AWAKE → FOCUSED    when entity/threat locked
      AWAKE → DROWSY     when idle too long
      AWAKE → CRISIS     when threat ≥ 4
      CRISIS → RECOVERING when threat drops
      RECOVERING → AWAKE  when load normalizes
      AWAKE → DREAMING   when DMN active + no signals
      DREAMING → AWAKE   when signal arrives
      DROWSY → AWAKE     when any signal arrives
    """

    def __init__(self, db: ThalamicDB):
        self.db           = db
        self.state        = ConsciousnessState.AWAKE
        self.state_since  = datetime.now()
        self.focus_target = None
        self.last_signal  = datetime.now()
        self.crisis_count = 0
        self.history:     deque = deque(maxlen=100)

    def update(self, signal: dict, load: float,
               dmn_active: bool = False) -> ConsciousnessState:
        threat  = signal.get("threat", 0)
        salience= signal.get("salience_score", 0.3)
        entity  = signal.get("entity_name", "")
        old     = self.state

        self.last_signal = datetime.now()

        # Transition logic — ordered by priority
        if threat >= 4:
            new = ConsciousnessState.CRISIS
            self.crisis_count += 1
        elif threat >= 3 and self.state != ConsciousnessState.CRISIS:
            new = ConsciousnessState.CRISIS
        elif self.state == ConsciousnessState.CRISIS and threat <= 1:
            new = ConsciousnessState.RECOVERING
        elif self.state == ConsciousnessState.RECOVERING and load < LOAD_MODERATE and threat == 0:
            new = ConsciousnessState.AWAKE
        elif dmn_active and threat == 0 and salience < 0.3:
            new = ConsciousnessState.DREAMING
        elif self.state == ConsciousnessState.DREAMING and (threat > 0 or salience > 0.4):
            new = ConsciousnessState.AWAKE
        elif salience > 0.7 and entity and entity != "unknown":
            new = ConsciousnessState.FOCUSED
            self.focus_target = entity
        elif self.state == ConsciousnessState.FOCUSED and salience < 0.3:
            new = ConsciousnessState.AWAKE
            self.focus_target = None
        elif load > LOAD_CRITICAL:
            new = ConsciousnessState.CRISIS
        else:
            new = self.state

        # Drowsy from prolonged inactivity (checked separately)
        if new == ConsciousnessState.AWAKE:
            idle_secs = (datetime.now() - self.last_signal).total_seconds()
            if idle_secs > SLEEP_THRESHOLD_IDLE_SECS:
                new = ConsciousnessState.DROWSY

        if new != old:
            self.state = new
            self.state_since = datetime.now()
            self.db.log_consciousness_change(
                old.value, new.value,
                f"threat={threat} salience={salience:.2f} load={load:.2f}",
                load
            )

        self.history.append(new.value)
        return new

    def wake(self):
        """Force wake from drowsy/dreaming."""
        if self.state in [ConsciousnessState.DROWSY, ConsciousnessState.DREAMING]:
            old = self.state
            self.state = ConsciousnessState.AWAKE
            self.state_since = datetime.now()
            self.db.log_consciousness_change(old.value, "AWAKE", "forced_wake", 0.0)

    def state_duration_secs(self) -> float:
        return (datetime.now() - self.state_since).total_seconds()

    def summary(self) -> dict:
        return {
            "state":          self.state.value,
            "duration_secs":  round(self.state_duration_secs(), 1),
            "focus_target":   self.focus_target,
            "crisis_count":   self.crisis_count,
            "last_signal_ago":round(
                (datetime.now() - self.last_signal).total_seconds(), 1
            )
        }


# ─── Attention Gate Manager ───────────────────────────────────────────────────

class AttentionGateManager:
    """
    Manages per-module attention gates.
    Each module has a gate that can be:
      OPEN      → signal passes at normal gain
      AMPLIFIED → signal boosted (gain > 1.0)
      DAMPENED  → signal reduced (gain < 1.0)
      CLOSED    → signal blocked
      QUEUED    → signal held for later delivery
    """

    # Module priority groups
    SURVIVAL_MODULES  = {"salience","temporal","prefrontal","sensorimotor"}
    COGNITIVE_MODULES = {"bridge","hippocampus","visual","neuromodulator"}
    BACKGROUND_MODULES= {"dmn","swarm","limbic"}

    # Gate configurations per consciousness state
    GATE_CONFIGS = {
        ConsciousnessState.AWAKE: {
            "salience":       (GateState.OPEN,      1.0),
            "temporal":       (GateState.OPEN,      1.0),
            "bridge":         (GateState.OPEN,      1.0),
            "limbic":         (GateState.OPEN,      1.0),
            "prefrontal":     (GateState.OPEN,      1.0),
            "hippocampus":    (GateState.OPEN,      1.0),
            "swarm":          (GateState.OPEN,      1.0),
            "dmn":            (GateState.OPEN,      0.8),
            "visual":         (GateState.OPEN,      1.0),
            "sensorimotor":   (GateState.OPEN,      1.0),
            "neuromodulator": (GateState.OPEN,      1.0),
        },
        ConsciousnessState.FOCUSED: {
            "salience":       (GateState.AMPLIFIED,  1.3),
            "temporal":       (GateState.AMPLIFIED,  1.2),
            "bridge":         (GateState.AMPLIFIED,  1.3),  # focused on entity
            "limbic":         (GateState.OPEN,       1.0),
            "prefrontal":     (GateState.AMPLIFIED,  1.2),
            "hippocampus":    (GateState.AMPLIFIED,  1.2),  # recall entity history
            "swarm":          (GateState.DAMPENED,   0.7),
            "dmn":            (GateState.CLOSED,     0.0),  # no daydreaming
            "visual":         (GateState.AMPLIFIED,  1.3),
            "sensorimotor":   (GateState.AMPLIFIED,  1.2),
            "neuromodulator": (GateState.OPEN,       1.0),
        },
        ConsciousnessState.DROWSY: {
            "salience":       (GateState.DAMPENED,   0.7),
            "temporal":       (GateState.DAMPENED,   0.6),
            "bridge":         (GateState.DAMPENED,   0.5),
            "limbic":         (GateState.DAMPENED,   0.6),
            "prefrontal":     (GateState.DAMPENED,   0.5),
            "hippocampus":    (GateState.OPEN,       1.0),  # memory consolidation ok
            "swarm":          (GateState.DAMPENED,   0.4),
            "dmn":            (GateState.AMPLIFIED,  1.4),  # dreaming/reflecting
            "visual":         (GateState.DAMPENED,   0.5),
            "sensorimotor":   (GateState.DAMPENED,   0.6),
            "neuromodulator": (GateState.OPEN,       0.8),
        },
        ConsciousnessState.CRISIS: {
            "salience":       (GateState.AMPLIFIED,  2.0),  # max threat detection
            "temporal":       (GateState.AMPLIFIED,  1.5),
            "bridge":         (GateState.OPEN,       1.0),
            "limbic":         (GateState.AMPLIFIED,  1.5),  # feel the crisis
            "prefrontal":     (GateState.AMPLIFIED,  1.3),
            "hippocampus":    (GateState.AMPLIFIED,  1.4),  # encode crisis memory
            "swarm":          (GateState.AMPLIFIED,  1.5),  # all agents active
            "dmn":            (GateState.CLOSED,     0.0),  # no reflection in crisis
            "visual":         (GateState.AMPLIFIED,  1.5),
            "sensorimotor":   (GateState.AMPLIFIED,  2.0),  # reflex priority MAX
            "neuromodulator": (GateState.AMPLIFIED,  1.5),
        },
        ConsciousnessState.DREAMING: {
            "salience":       (GateState.DAMPENED,   0.4),  # external world quieted
            "temporal":       (GateState.DAMPENED,   0.3),
            "bridge":         (GateState.DAMPENED,   0.3),
            "limbic":         (GateState.OPEN,       1.0),  # emotional processing
            "prefrontal":     (GateState.DAMPENED,   0.4),
            "hippocampus":    (GateState.AMPLIFIED,  1.5),  # memory replay
            "swarm":          (GateState.DAMPENED,   0.3),
            "dmn":            (GateState.AMPLIFIED,  2.0),  # DMN at full power
            "visual":         (GateState.DAMPENED,   0.2),
            "sensorimotor":   (GateState.DAMPENED,   0.3),
            "neuromodulator": (GateState.OPEN,       0.8),
        },
        ConsciousnessState.RECOVERING: {
            "salience":       (GateState.OPEN,       1.0),
            "temporal":       (GateState.OPEN,       0.9),
            "bridge":         (GateState.OPEN,       0.9),
            "limbic":         (GateState.OPEN,       1.0),
            "prefrontal":     (GateState.OPEN,       0.8),  # slightly slower
            "hippocampus":    (GateState.AMPLIFIED,  1.3),  # consolidate crisis
            "swarm":          (GateState.DAMPENED,   0.7),
            "dmn":            (GateState.OPEN,       1.2),  # begin reflection
            "visual":         (GateState.OPEN,       0.9),
            "sensorimotor":   (GateState.OPEN,       1.0),
            "neuromodulator": (GateState.AMPLIFIED,  1.2),  # cortisol clearing
        },
    }

    def __init__(self, db: ThalamicDB):
        self.db    = db
        self.gates: dict[str, ThalamicGate] = {}
        self._init_gates()

    def _init_gates(self):
        all_modules = set()
        for config in self.GATE_CONFIGS.values():
            all_modules.update(config.keys())
        for module in all_modules:
            self.gates[module] = ThalamicGate(module=module)

    def configure_for_state(self, state: ConsciousnessState):
        """Reconfigure all gates for the given consciousness state."""
        config = self.GATE_CONFIGS.get(state, self.GATE_CONFIGS[ConsciousnessState.AWAKE])
        for module, (gate_state, gain) in config.items():
            gate = self.gates.get(module)
            if gate:
                old_state = gate.state
                gate.state = gate_state.value
                gate.gain  = gain
                if old_state != gate_state.value:
                    self.db.log_gate_change(
                        module, old_state, gate_state.value,
                        f"consciousness_state={state.value}"
                    )

    def apply_load(self, load: float):
        """
        Under high load, progressively close background module gates.
        This prevents cognitive overload.
        """
        if load > LOAD_CRITICAL:
            # Close background modules entirely
            for module in self.BACKGROUND_MODULES:
                if module in self.gates:
                    if self.gates[module].state != GateState.CLOSED.value:
                        self.gates[module].state = GateState.QUEUED.value
                        self.db.log_gate_change(module, "open",
                                               "QUEUED", f"overload={load:.2f}")

        elif load > LOAD_HIGH:
            for module in self.BACKGROUND_MODULES:
                if module in self.gates:
                    self.gates[module].state  = GateState.DAMPENED.value
                    self.gates[module].gain   = max(0.3, self.gates[module].gain * 0.7)

    def pass_signal(self, module: str, signal: dict) -> tuple[bool, float, str]:
        """
        Determine if signal passes through this module's gate.
        Returns (passes, gain_applied, gate_state)
        """
        gate = self.gates.get(module)
        if not gate:
            return True, 1.0, GateState.OPEN.value

        if gate.state == GateState.CLOSED.value:
            gate.block_count += 1
            return False, 0.0, GateState.CLOSED.value

        if gate.state == GateState.QUEUED.value:
            gate.queue.append(signal)
            return False, 0.0, GateState.QUEUED.value

        # Check threshold
        salience = signal.get("salience_score", 0.5)
        if salience < gate.threshold:
            gate.block_count += 1
            return False, 0.0, "BELOW_THRESHOLD"

        gate.pass_count += 1
        gate.last_signal = datetime.now().isoformat()
        return True, gate.gain, gate.state

    def flush_queue(self, module: str) -> list[dict]:
        """Return queued signals when gate reopens."""
        gate = self.gates.get(module)
        if not gate: return []
        queued = list(gate.queue)
        gate.queue.clear()
        return queued

    def snapshot(self) -> dict:
        return {
            module: {
                "state": gate.state,
                "gain":  round(gate.gain, 2),
                "passed":gate.pass_count,
                "blocked":gate.block_count,
                "queued":len(gate.queue)
            }
            for module, gate in self.gates.items()
        }


# ─── Load Balancer ────────────────────────────────────────────────────────────

class LoadBalancer:
    """
    Monitors cognitive load and prevents overload.
    Load = function of signal frequency + threat level + module saturation.
    """

    def __init__(self, window_secs: float = 10.0):
        self.window      = window_secs
        self.signal_log: deque = deque(maxlen=200)
        self.load        = 0.0
        self.peak_load   = 0.0

    def record(self, signal: dict):
        self.signal_log.append({
            "time":    time.time(),
            "threat":  signal.get("threat", 0),
            "salience":signal.get("salience_score", 0.3)
        })

    def compute(self) -> float:
        """Compute current cognitive load (0-1)."""
        now    = time.time()
        recent = [s for s in self.signal_log
                  if now - s["time"] < self.window]

        if not recent:
            self.load = max(0.0, self.load * 0.95)
            return self.load

        # Frequency component
        freq_load = min(1.0, len(recent) / 20.0)

        # Threat component
        threat_load = sum(s["threat"] for s in recent) / (len(recent) * 4.0)

        # Salience component
        sal_load = sum(s["salience"] for s in recent) / len(recent)

        raw_load = freq_load * 0.4 + threat_load * 0.4 + sal_load * 0.2
        self.load = round(min(1.0, raw_load), 3)
        self.peak_load = max(self.peak_load, self.load)
        return self.load

    def label(self) -> str:
        if self.load >= LOAD_CRITICAL:  return "CRITICAL"
        if self.load >= LOAD_HIGH:      return "HIGH"
        if self.load >= LOAD_MODERATE:  return "MODERATE"
        return "LOW"


# ─── Signal Amplifier ─────────────────────────────────────────────────────────

class SignalAmplifier:
    """
    Boosts weak but important signals.
    The thalamus catches signals that salience might miss.

    Cases:
    - Low salience but matches FOCUSED entity
    - Weak signal that breaks a long pattern
    - First occurrence of new entity
    - Signal from previously BLOCKED module now reopening
    """

    def __init__(self):
        self.amplification_log: deque = deque(maxlen=50)

    def amplify(self, signal: dict, gate_gain: float,
                focus_target: Optional[str]) -> tuple[float, str]:
        """
        Returns (final_salience, reason).
        """
        salience    = signal.get("salience_score", 0.3)
        entity      = signal.get("entity_name","")
        threat      = signal.get("threat", 0)
        novelty     = signal.get("novelty", 1.0)

        amplification_reason = ""
        boost = 0.0

        # Focused entity gets boosted
        if focus_target and entity == focus_target:
            boost += 0.2
            amplification_reason = f"focus_target:{entity}"

        # Novel signal in calm period
        if novelty > 0.8 and threat == 0 and salience < 0.4:
            boost += 0.15
            amplification_reason += " novel_in_calm"

        # Any signal with threat > 0 in DROWSY state gets boosted
        if threat > 0 and salience < 0.3:
            boost += threat * 0.1
            amplification_reason += f" threat_wake_boost"

        final = round(min(1.0, salience * gate_gain + boost), 3)
        if final > salience + 0.05:
            self.amplification_log.append({
                "original": salience, "final": final,
                "reason": amplification_reason.strip()
            })

        return final, amplification_reason.strip()


# ─── Noise Filter ─────────────────────────────────────────────────────────────

class NoiseFilter:
    """
    Suppresses repetitive or irrelevant background signals.
    Prevents FORGE from being overwhelmed by routine noise.

    Filters:
    - Exact same signal within X seconds (duplicate suppression)
    - Same entity, same intent, same threat N times in a row
    - Below-baseline salience with no novel content
    """

    def __init__(self, duplicate_window_secs: float = 3.0):
        self.window      = duplicate_window_secs
        self.recent_fps: deque = deque(maxlen=30)  # (fingerprint, timestamp)
        self.repeat_counter: defaultdict = defaultdict(int)

    def should_filter(self, signal: dict) -> tuple[bool, str]:
        """Returns (filter_it, reason)."""
        import hashlib

        threat  = signal.get("threat", 0)
        entity  = signal.get("entity_name","")
        salience= signal.get("salience_score", 0.3)

        # Never filter threats
        if threat >= 2:
            return False, ""

        # Build signal fingerprint
        fp_raw  = f"{entity}:{threat}:{signal.get('conclusion','')[:30]}"
        fp      = hashlib.md5(fp_raw.encode()).hexdigest()[:8]
        now     = time.time()

        # Duplicate check
        for old_fp, old_time in list(self.recent_fps):
            if old_fp == fp and (now - old_time) < self.window:
                return True, f"duplicate_within_{self.window}s"

        # Repeat entity same-intent check
        intent = signal.get("social", {}) or {}
        intent = intent.get("inferred_intent","") if isinstance(intent,dict) else ""
        rep_key = f"{entity}:{intent}"
        self.repeat_counter[rep_key] += 1
        if self.repeat_counter[rep_key] > 4 and salience < 0.35:
            return True, f"repetitive_entity_signal ({self.repeat_counter[rep_key]}x)"

        # Very low salience + no novelty
        novelty = signal.get("novelty", 1.0)
        if salience < 0.12 and novelty < 0.2:
            return True, "below_noise_floor"

        self.recent_fps.append((fp, now))
        return False, ""


# ─── Thalamic Clock ───────────────────────────────────────────────────────────

class ThalamicClock:
    """
    Synchronizes all FORGE modules with a cognitive rhythm.
    Like the brain's ~40Hz gamma oscillation — provides temporal binding.

    Phases:
      INTEGRATE → collect incoming signals
      PROCESS   → route through modules
      OUTPUT    → dispatch responses
      REST      → brief recovery (allows neuromodulator decay)

    The clock doesn't block — it provides rhythm and phase information
    that other modules can use to synchronize their behavior.
    """

    def __init__(self, freq_hz: float = CLOCK_FREQ_HZ):
        self.freq_hz     = freq_hz
        self.tick_count  = 0
        self.phase       = ClockPhase.INTEGRATE
        self.phase_start = time.time()
        self.phase_duration = 1.0 / freq_hz / 4  # 4 phases per cycle
        self._running    = False
        self._thread     = None
        self.listeners   = []   # callbacks on each tick

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        phases = list(ClockPhase)
        phase_idx = 0
        while self._running:
            now = time.time()
            if now - self.phase_start >= self.phase_duration:
                phase_idx     = (phase_idx + 1) % len(phases)
                self.phase    = phases[phase_idx]
                self.phase_start = now
                self.tick_count += 1
                for cb in self.listeners:
                    try: cb(self.tick_count, self.phase)
                    except Exception: pass
            time.sleep(self.phase_duration * 0.1)

    def register(self, callback):
        self.listeners.append(callback)

    def current_phase(self) -> ClockPhase:
        return self.phase

    def is_processing_phase(self) -> bool:
        return self.phase in [ClockPhase.INTEGRATE, ClockPhase.PROCESS]

    def status(self) -> dict:
        return {
            "tick":    self.tick_count,
            "phase":   self.phase.value,
            "freq_hz": self.freq_hz,
            "running": self._running
        }


# ─── Sleep Wake Cycle ─────────────────────────────────────────────────────────

class SleepWakeCycle:
    """
    FORGE's circadian-like cycle.
    Extended inactivity leads to drowsiness, then sleep-like state.
    Threats instantly wake the system.
    Recovery after crisis follows a recovery curve.

    This gives FORGE temporal depth — it behaves differently
    depending on how long it's been active vs inactive.
    """

    def __init__(self):
        self.awake_since      = datetime.now()
        self.last_active      = datetime.now()
        self.sleep_debt       = 0.0    # builds without rest
        self.recovery_credit  = 0.0    # builds during quiet periods
        self.cycles_awake     = 0
        self.cycles_resting   = 0

    def update(self, had_signal: bool, threat: int) -> dict:
        now   = datetime.now()
        idle  = (now - self.last_active).total_seconds()

        if had_signal:
            self.last_active = now
            self.cycles_awake += 1

            if threat >= WAKE_ON_THREAT:
                # Threat wakes system instantly
                self.sleep_debt = max(0.0, self.sleep_debt - 0.1)
        else:
            self.cycles_resting += 1
            # Quiet time builds recovery credit
            self.recovery_credit = min(1.0, self.recovery_credit + 0.02)
            self.sleep_debt      = max(0.0, self.sleep_debt - 0.01)

        # Sleep debt builds with sustained activity
        if self.cycles_awake % 50 == 0 and self.cycles_awake > 0:
            self.sleep_debt = min(1.0, self.sleep_debt + 0.05)

        readiness = round(max(0.1, 1.0 - self.sleep_debt * 0.5 +
                              self.recovery_credit * 0.3), 3)

        return {
            "awake_secs":     round((now - self.awake_since).total_seconds(), 1),
            "idle_secs":      round(idle, 1),
            "sleep_debt":     round(self.sleep_debt, 3),
            "recovery_credit":round(self.recovery_credit, 3),
            "readiness":      readiness,
            "cycles_awake":   self.cycles_awake,
            "cycles_resting": self.cycles_resting
        }


# ─── FORGE Thalamus ───────────────────────────────────────────────────────────

class ForgeThalamus:
    def __init__(self):
        self.db           = ThalamicDB()
        self.consciousness= ConsciousnessEngine(self.db)
        self.gates        = AttentionGateManager(self.db)
        self.load_balancer= LoadBalancer()
        self.amplifier    = SignalAmplifier()
        self.noise_filter = NoiseFilter()
        self.clock        = ThalamicClock()
        self.sleep_wake   = SleepWakeCycle()
        self.cycle        = 0
        self.total_passed = 0
        self.total_blocked= 0
        self.total_amplified = 0

        # Configure initial gate state
        self.gates.configure_for_state(ConsciousnessState.AWAKE)

        # Start clock
        self.clock.start()

    def process(self, signal: dict, dmn_active: bool = False) -> dict:
        """
        Route a signal through the full thalamic processing chain.
        Returns routing decisions and adjusted signal.
        """
        t0 = time.time()
        self.cycle += 1

        # 1. Noise filter — kill obvious noise first
        filtered, filter_reason = self.noise_filter.should_filter(signal)
        if filtered:
            self.total_blocked += 1
            ts = ThalamicSignal(
                raw_threat   = signal.get("threat",0),
                raw_salience = signal.get("salience_score",0.3),
                filtered     = True,
                processing_ms= round((time.time()-t0)*1000, 2)
            )
            self.db.save_signal(ts)
            return {
                "cycle":       self.cycle,
                "passed":      False,
                "reason":      f"NOISE_FILTERED: {filter_reason}",
                "routing":     {},
                "consciousness":self.consciousness.state.value,
                "load":        self.load_balancer.load,
                "clock_phase": self.clock.current_phase().value,
                "clock_tick":  self.clock.tick_count,
                "modules_open":[],
                "modules_closed":[],
                "focus_target":self.consciousness.focus_target,
                "sleep_wake":  {"sleep_debt":0,"readiness":1,
                                  "idle_secs":0,"awake_secs":0,
                                  "recovery_credit":0,"cycles_awake":0,
                                  "cycles_resting":0},
                "processing_ms":round((time.time()-t0)*1000,2),
                "consciousness_duration_secs":0,
                "load_label":"LOW",
            }

        # 2. Load computation
        self.load_balancer.record(signal)
        load = self.load_balancer.compute()

        # 3. Consciousness state update
        cs = self.consciousness.update(signal, load, dmn_active)

        # 4. Configure gates for current consciousness state
        self.gates.configure_for_state(cs)
        self.gates.apply_load(load)

        # 5. Sleep/wake update
        sleep_status = self.sleep_wake.update(True, signal.get("threat",0))

        # 6. Route signal through each module's gate
        routing = {}
        for module in ["salience","temporal","bridge","limbic","prefrontal",
                       "hippocampus","swarm","dmn","visual",
                       "sensorimotor","neuromodulator"]:
            passes, gain, gate_state = self.gates.pass_signal(module, signal)

            if passes:
                # Apply amplification
                adj_salience, amp_reason = self.amplifier.amplify(
                    signal, gain, self.consciousness.focus_target
                )
                if adj_salience > signal.get("salience_score",0.3) + 0.05:
                    self.total_amplified += 1
                routing[module] = {
                    "passes":    True,
                    "gain":      round(gain, 2),
                    "gate":      gate_state,
                    "adjusted_salience": adj_salience,
                    "amplified": bool(amp_reason)
                }
            else:
                routing[module] = {
                    "passes":    False,
                    "gain":      0.0,
                    "gate":      gate_state,
                    "adjusted_salience": 0.0,
                    "amplified": False
                }

        # Count passes/blocks
        passed_modules  = [m for m,r in routing.items() if r["passes"]]
        blocked_modules = [m for m,r in routing.items() if not r["passes"]]
        self.total_passed  += len(passed_modules)
        self.total_blocked += len(blocked_modules)

        # 7. Build thalamic signal record
        ts = ThalamicSignal(
            raw_threat       = signal.get("threat",0),
            raw_salience     = signal.get("salience_score",0.3),
            adjusted_salience= routing.get("temporal",{}).get("adjusted_salience",
                               signal.get("salience_score",0.3)),
            priority         = self._compute_priority(signal).value,
            routing          = {m: r["passes"] for m,r in routing.items()},
            consciousness_state = cs.value,
            load_at_entry    = load,
            amplified        = self.total_amplified > 0,
            processing_ms    = round((time.time()-t0)*1000, 2)
        )
        self.db.save_signal(ts)

        # 8. Clock tick
        self.db.save_tick(ClockTick(
            tick         = self.cycle,
            phase        = self.clock.current_phase().value,
            consciousness= cs.value,
            load         = load,
            gates_open   = len(passed_modules),
            gates_closed = len(blocked_modules),
            signals_this_tick = 1
        ))

        return {
            "cycle":              self.cycle,
            "passed":             True,
            "consciousness":      cs.value,
            "consciousness_duration_secs": round(self.consciousness.state_duration_secs(),1),
            "load":               load,
            "load_label":         self.load_balancer.label(),
            "clock_phase":        self.clock.current_phase().value,
            "clock_tick":         self.clock.tick_count,
            "routing":            routing,
            "modules_open":       passed_modules,
            "modules_closed":     blocked_modules,
            "focus_target":       self.consciousness.focus_target,
            "sleep_wake":         sleep_status,
            "signal_id":          ts.id,
            "processing_ms":      ts.processing_ms,
        }

    def _compute_priority(self, signal: dict) -> SignalPriority:
        threat  = signal.get("threat", 0)
        salience= signal.get("salience_score", 0.3)
        if threat >= 4:   return SignalPriority.CRITICAL
        if threat >= 3:   return SignalPriority.HIGH
        if salience > 0.7:return SignalPriority.HIGH
        if threat >= 2:   return SignalPriority.NORMAL
        if salience > 0.4:return SignalPriority.NORMAL
        return SignalPriority.LOW

    def force_wake(self):
        self.consciousness.wake()
        self.gates.configure_for_state(ConsciousnessState.AWAKE)

    def get_status(self) -> dict:
        return {
            "version":           VERSION,
            "cycle":             self.cycle,
            "consciousness":     self.consciousness.summary(),
            "load":              self.load_balancer.load,
            "load_label":        self.load_balancer.label(),
            "peak_load":         self.load_balancer.peak_load,
            "clock":             self.clock.status(),
            "gates":             self.gates.snapshot(),
            "total_passed":      self.total_passed,
            "total_blocked":     self.total_blocked,
            "total_amplified":   self.total_amplified,
            "sleep_wake":        self.sleep_wake.update(False, 0)
        }

    def shutdown(self):
        self.clock.stop()


# ─── Rich UI ──────────────────────────────────────────────────────────────────

CS_COLORS = {
    "AWAKE":      "green",
    "FOCUSED":    "cyan",
    "DROWSY":     "dim",
    "CRISIS":     "bright_red",
    "DREAMING":   "magenta",
    "RECOVERING": "yellow",
}

def render_thalamic(result: dict, signal: dict, idx: int):
    if not HAS_RICH: return

    cs      = result["consciousness"]
    csc     = CS_COLORS.get(cs, "white")
    load    = result["load"]
    lc      = "bright_red" if load>0.8 else "red" if load>0.6 else "yellow" if load>0.4 else "green"
    threat  = signal.get("threat",0)
    tc      = {0:"green",1:"blue",2:"yellow",3:"red",4:"bright_red"}.get(threat,"white")
    phase   = result["clock_phase"]

    if not result.get("passed"):
        console.print(Rule(
            f"[bold cyan]⬡ THALAMUS[/bold cyan]  [dim]#{idx}[/dim]  "
            f"[dim]NOISE FILTERED[/dim]"
        ))
        console.print(Panel(
            f"[dim]{result.get('reason','')}[/dim]",
            border_style="dim"
        ))
        return

    console.print(Rule(
        f"[bold cyan]⬡ FORGE THALAMUS[/bold cyan]  "
        f"[dim]#{idx}  tick={result['clock_tick']}  {phase}[/dim]  "
        f"[{csc}]{cs}[/{csc}]  "
        f"[{lc}]load={load:.2f}[/{lc}]"
    ))

    # Gate visualization
    routing = result["routing"]
    gate_lines = []
    gate_order = ["salience","temporal","bridge","limbic","prefrontal",
                  "hippocampus","swarm","dmn","visual","sensorimotor","neuromodulator"]

    gate_table = Table(box=box.SIMPLE, show_header=False, expand=True)
    gate_table.add_column("module", style="dim", width=14)
    gate_table.add_column("gate",   width=12)
    gate_table.add_column("gain",   justify="right", width=6)
    gate_table.add_column("sal",    justify="right", width=6)

    mod_emojis = {
        "salience":"🎯","temporal":"🧠","bridge":"🔗","limbic":"💗",
        "prefrontal":"👔","hippocampus":"📚","swarm":"🐝","dmn":"💭",
        "visual":"👁","sensorimotor":"⚡","neuromodulator":"🧪"
    }

    for mod in gate_order:
        r = routing.get(mod, {})
        passes = r.get("passes", True)
        gate   = r.get("gate","OPEN")
        gain   = r.get("gain", 1.0)
        adj_s  = r.get("adjusted_salience", 0.0)
        amp    = r.get("amplified", False)

        gc = {
            "OPEN":       "green",
            "AMPLIFIED":  "cyan",
            "DAMPENED":   "yellow",
            "CLOSED":     "red",
            "QUEUED":     "dim",
            "BELOW_THRESHOLD":"dim"
        }.get(gate, "white")

        emoji  = mod_emojis.get(mod,"◈")
        gain_s = f"×{gain:.1f}" if passes else "×0"
        gain_c = "green" if gain>1.0 else "red" if gain==0 else "yellow" if gain<1.0 else "dim"

        gate_table.add_row(
            f"{emoji} {mod}",
            f"[{gc}]{'▶' if passes else '✗'} {gate[:8]}[/{gc}]",
            f"[{gain_c}]{gain_s}[/{gain_c}]",
            f"[dim]{adj_s:.2f}[/dim]" if passes else "[dim]—[/dim]"
        )

    # Right: consciousness + load
    right_lines = [
        f"[bold]State:[/bold]    [{csc}]{cs}[/{csc}]",
        f"[bold]Duration:[/bold] {result['consciousness_duration_secs']:.0f}s",
        f"[bold]Load:[/bold]     [{lc}]{load:.3f} {result['load_label']}[/{lc}]",
        f"[bold]Phase:[/bold]    {phase}",
        f"[bold]Focus:[/bold]    {result.get('focus_target') or '—'}",
        f"",
        f"[bold]Open:[/bold]     {len(result['modules_open'])}/11 modules",
        f"[bold]Closed:[/bold]   {len(result['modules_closed'])} modules",
        f"[dim]{', '.join(result['modules_closed'][:3])}[/dim]",
        f"",
        f"[bold]Sleep debt:[/bold] {result['sleep_wake']['sleep_debt']:.3f}",
        f"[bold]Readiness:[/bold]  {result['sleep_wake']['readiness']:.3f}",
    ]

    console.print(Columns([
        Panel(gate_table,           title="[bold]Module Gates[/bold]",      border_style=csc),
        Panel("\n".join(right_lines),title="[bold]Thalamic State[/bold]",   border_style=lc)
    ]))

    # Consciousness panel
    console.print(Panel(
        f"[{csc}]{cs}[/{csc}]"
        + (f" — focused on [{tc}]{result['focus_target']}[/{tc}]"
           if result.get("focus_target") else "")
        + f"\n[dim]{_cs_description(cs)}[/dim]",
        border_style=csc
    ))


def _cs_description(state: str) -> str:
    return {
        "AWAKE":      "Full awareness — all gates open — normal processing",
        "FOCUSED":    "Locked onto target — perception + memory amplified — DMN closed",
        "DROWSY":     "Reduced sensitivity — background modules quiet — DMN opens",
        "CRISIS":     "Maximum threat — survival channels only — all reflexes amplified",
        "DREAMING":   "External world quieted — DMN at full power — memory replay active",
        "RECOVERING": "Post-crisis — cortisol clearing — hippocampus consolidating",
    }.get(state, "Unknown state")


def run_demo():
    if HAS_RICH:
        console.print(Panel.fit(
            "[bold cyan]FORGE THALAMUS[/bold cyan]\n"
            "[dim]Central Relay · Consciousness Gating · Cognitive Rhythm[/dim]\n"
            f"[dim]Version {VERSION}  |  11 gates  |  6 consciousness states[/dim]",
            border_style="cyan"
        ))

    thalamus = ForgeThalamus()

    scenarios = [
        # Normal awake — all gates open
        ({"threat":0,"anomaly":False,"salience_score":0.25,
          "entity_name":"alice_tech","novelty":0.4,
          "conclusion":"✓ NORMAL","social":{"inferred_intent":"COOPERATIVE_REQUEST"}},
         False, "Normal awake — all gates open"),

        # Focus on entity — focused state
        ({"threat":0,"anomaly":False,"salience_score":0.75,
          "entity_name":"unknown_x","novelty":0.7,
          "conclusion":"⚠ Suspicious entity","social":{"inferred_intent":"COERCIVE_DEMAND"}},
         False, "High salience — focus state activates"),

        # Noise — should be filtered
        ({"threat":0,"anomaly":False,"salience_score":0.08,
          "entity_name":"system","novelty":0.05,
          "conclusion":"status ping","social":{"inferred_intent":"NEUTRAL_INTERACTION"}},
         False, "Noise — filter test"),

        # Same noise again — repeat filter
        ({"threat":0,"anomaly":False,"salience_score":0.08,
          "entity_name":"system","novelty":0.05,
          "conclusion":"status ping","social":{"inferred_intent":"NEUTRAL_INTERACTION"}},
         False, "Duplicate noise — repeat filter"),

        # Medium threat — load rising
        ({"threat":2,"anomaly":False,"salience_score":0.55,
          "entity_name":"unknown_x","novelty":0.5,
          "conclusion":"⚠ MEDIUM threat","social":{"inferred_intent":"COERCIVE_DEMAND"}},
         False, "Medium threat — load rising"),

        # Critical — CRISIS state
        ({"threat":4,"anomaly":True,"salience_score":0.95,
          "entity_name":"unknown_x","novelty":0.8,
          "conclusion":"🔴 CRITICAL","social":{"inferred_intent":"INTRUSION_ATTEMPT"}},
         False, "CRITICAL — CRISIS consciousness"),

        # Second critical — crisis sustained
        ({"threat":4,"anomaly":True,"salience_score":0.92,
          "entity_name":"unknown_x","novelty":0.6,
          "conclusion":"🔴 CRITICAL cascade","social":{"inferred_intent":"INTRUSION_ATTEMPT"}},
         False, "Crisis sustained"),

        # DMN active — dreaming state
        ({"threat":0,"anomaly":False,"salience_score":0.15,
          "entity_name":"system","novelty":0.2,
          "conclusion":"✓ Idle","social":{"inferred_intent":"NEUTRAL_INTERACTION"}},
         True, "DMN active — dreaming state"),

        # Recovery
        ({"threat":1,"anomaly":False,"salience_score":0.30,
          "entity_name":"security_team","novelty":0.4,
          "conclusion":"ℹ Recovery","social":{"inferred_intent":"COOPERATIVE_REQUEST"}},
         False, "Post-crisis — recovery"),

        # All clear
        ({"threat":0,"anomaly":False,"salience_score":0.20,
          "entity_name":"alice_tech","novelty":0.3,
          "conclusion":"✓ All clear","social":{"inferred_intent":"COOPERATIVE_REQUEST"}},
         False, "All clear — returning to AWAKE"),
    ]

    for i, (sig, dmn_active, label) in enumerate(scenarios):
        if HAS_RICH:
            console.print(f"\n[bold dim]━━━ {i+1}: {label.upper()} ━━━[/bold dim]")
        result = thalamus.process(sig, dmn_active)
        render_thalamic(result, sig, i+1)
        time.sleep(0.15)

    # Final status
    if HAS_RICH:
        console.print(Rule("[bold cyan]⬡ THALAMUS FINAL STATUS[/bold cyan]"))
        status = thalamus.get_status()

        st = Table(box=box.DOUBLE_EDGE, border_style="cyan", title="Thalamus Status")
        st.add_column("Metric", style="cyan")
        st.add_column("Value",  style="white")
        st.add_row("Consciousness",  status["consciousness"]["state"])
        st.add_row("Crisis Count",   str(status["consciousness"]["crisis_count"]))
        st.add_row("Load",           f"{status['load']:.3f} [{status['load_label']}]")
        st.add_row("Peak Load",      f"{status['peak_load']:.3f}")
        st.add_row("Clock Tick",     str(status["clock"]["tick"]))
        st.add_row("Clock Phase",    status["clock"]["phase"])
        st.add_row("Total Passed",   str(status["total_passed"]))
        st.add_row("Total Blocked",  str(status["total_blocked"]))
        st.add_row("Total Amplified",str(status["total_amplified"]))
        console.print(st)

        # Consciousness history
        rows = thalamus.db.get_consciousness_log(10)
        if rows:
            cl = Table(box=box.SIMPLE, title="Consciousness Transitions", title_style="dim")
            cl.add_column("Time",   width=10)
            cl.add_column("From",   width=12)
            cl.add_column("→ To",   width=12)
            cl.add_column("Trigger",width=40)
            for row in rows:
                fc = CS_COLORS.get(row[1],"white")
                tc = CS_COLORS.get(row[2],"white")
                cl.add_row(
                    row[0][11:19],
                    f"[{fc}]{row[1]}[/{fc}]",
                    f"[{tc}]{row[2]}[/{tc}]",
                    row[3][:38]
                )
            console.print(cl)

    thalamus.shutdown()


# ─── HTTP API ─────────────────────────────────────────────────────────────────

def run_api(thalamus: ForgeThalamus):
    if not HAS_FLASK: return
    app = Flask(__name__)

    @app.route("/process", methods=["POST"])
    def process():
        data = request.json or {}
        return jsonify(thalamus.process(
            data.get("signal",{}),
            data.get("dmn_active", False)
        ))

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify(thalamus.get_status())

    @app.route("/wake", methods=["POST"])
    def wake():
        thalamus.force_wake()
        return jsonify({"status":"awake"})

    @app.route("/gates", methods=["GET"])
    def gates():
        return jsonify(thalamus.gates.snapshot())

    @app.route("/consciousness", methods=["GET"])
    def consciousness():
        return jsonify(thalamus.consciousness.summary())

    @app.route("/history", methods=["GET"])
    def history():
        rows = thalamus.db.get_recent_signals(20)
        return jsonify([{
            "id":r[0],"timestamp":r[1],"threat":r[2],
            "salience":r[3],"priority":r[5],
            "consciousness":r[7],"filtered":bool(r[10]),
            "ms":r[12]
        } for r in rows])

    app.run(host="0.0.0.0", port=API_PORT, debug=False)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    thalamus = ForgeThalamus()
    if "--api" in sys.argv:
        t = threading.Thread(target=run_api, args=(thalamus,), daemon=True)
        t.start()
    run_demo()
