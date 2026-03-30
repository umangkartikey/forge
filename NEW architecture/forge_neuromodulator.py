"""
FORGE Neuromodulator — forge_neuromodulator.py
===============================================
The slow chemical layer that everything runs on top of.

In the brain, neuromodulators are chemicals that diffuse broadly and
set the TONE of neural processing — not individual signals, but the
water level that all fast signals rise and fall within.

This is what makes the difference between:
  "emotion as computation"  (forge_limbic — fast, reactive)
  "emotion as something that persists and shapes you" (this module — slow, cumulative)

Five neuromodulator analogs:

  Cortisol      → stress hormone. Builds under sustained threat.
                  Degrades decision quality. Creates hypervigilance.
                  Takes a long time to clear.

  Dopamine      → reward + curiosity. Released on novel discovery,
                  successful threat resolution, insight generation.
                  Drives exploration and learning.

  Serotonin     → baseline mood stabilizer. Depletes under chronic stress.
                  Low serotonin = everything feels harder, darker.
                  Rebuilds slowly through positive interactions.

  Norepinephrine→ arousal + alertness. Spikes on threat detection.
                  Sharpens attention but narrows thinking.
                  The "fight or flight" chemical.

  Oxytocin      → trust + social bonding. Builds with cooperative
                  interactions. Increases trust threshold for known
                  entities. The "tend and befriend" chemical.

Each modulator:
  - Has its own timescale (cortisol=hours, oxytocin=interactions)
  - Affects multiple downstream systems
  - Interacts with other modulators
  - Creates emergent states when combined (e.g. high cortisol + low serotonin = burnout)

Emergent states:
  FLOW        → high dopamine + moderate norepinephrine + low cortisol
  BURNOUT     → high cortisol + low serotonin + low dopamine
  HYPERVIGILANCE → high cortisol + high norepinephrine
  SOCIAL_TRUST → high oxytocin + high serotonin
  PEAK_PERFORMANCE → optimal dopamine + moderate norepinephrine + low cortisol
  THREAT_FATIGUE → high cortisol + depleted norepinephrine
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

DB_PATH  = "forge_neuromodulator.db"
API_PORT = 7787
VERSION  = "1.0.0"

# Timescales — how quickly each modulator decays per cycle
# Smaller = slower decay = longer lasting
DECAY_RATES = {
    "cortisol":       0.985,  # slow — stress lingers for hours
    "dopamine":       0.940,  # medium — reward fades but not instantly
    "serotonin":      0.998,  # very slow — baseline is sticky
    "norepinephrine": 0.920,  # fast — alertness spike fades quickly
    "oxytocin":       0.992,  # slow — social bonds persist
}

# Baseline levels — where each modulator rests when nothing is happening
BASELINES = {
    "cortisol":       0.15,
    "dopamine":       0.45,
    "serotonin":      0.65,
    "norepinephrine": 0.20,
    "oxytocin":       0.35,
}

# Min/max bounds
BOUNDS = {
    "cortisol":       (0.05, 1.00),
    "dopamine":       (0.10, 1.00),
    "serotonin":      (0.05, 0.90),
    "norepinephrine": (0.05, 1.00),
    "oxytocin":       (0.10, 0.95),
}

console = Console() if HAS_RICH else None

# ─── Enums ────────────────────────────────────────────────────────────────────

class NeuroState(Enum):
    FLOW              = "FLOW"
    BURNOUT           = "BURNOUT"
    HYPERVIGILANCE    = "HYPERVIGILANCE"
    SOCIAL_TRUST      = "SOCIAL_TRUST"
    PEAK_PERFORMANCE  = "PEAK_PERFORMANCE"
    THREAT_FATIGUE    = "THREAT_FATIGUE"
    CURIOUS_ALERT     = "CURIOUS_ALERT"
    RECOVERY          = "RECOVERY"
    BASELINE          = "BASELINE"
    DEPLETED          = "DEPLETED"

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class ModulatorLevel:
    name:       str   = ""
    level:      float = 0.5
    baseline:   float = 0.5
    delta:      float = 0.0    # change from last cycle
    trend:      str   = "→"    # ↑ ↓ →
    cycles_elevated: int = 0   # how long above baseline
    cycles_depleted: int = 0   # how long below baseline

@dataclass
class NeuroProfile:
    """Full snapshot of all modulator levels."""
    timestamp:    str   = field(default_factory=lambda: datetime.now().isoformat())
    cortisol:     float = BASELINES["cortisol"]
    dopamine:     float = BASELINES["dopamine"]
    serotonin:    float = BASELINES["serotonin"]
    norepinephrine: float = BASELINES["norepinephrine"]
    oxytocin:     float = BASELINES["oxytocin"]
    state:        str   = NeuroState.BASELINE.value
    state_confidence: float = 0.5
    cycle:        int   = 0

    def as_dict(self) -> dict:
        return {
            "cortisol":       round(self.cortisol, 3),
            "dopamine":       round(self.dopamine, 3),
            "serotonin":      round(self.serotonin, 3),
            "norepinephrine": round(self.norepinephrine, 3),
            "oxytocin":       round(self.oxytocin, 3),
            "state":          self.state,
            "state_confidence": round(self.state_confidence, 2),
        }

@dataclass
class DownstreamEffect:
    """How current neuromodulator levels affect downstream systems."""
    timestamp:         str   = field(default_factory=lambda: datetime.now().isoformat())
    # Prefrontal effects
    decision_confidence: float = 0.0   # +/- modifier
    risk_tolerance:    float = 0.0
    planning_horizon:  float = 1.0     # multiplier on planning depth
    impulse_control:   float = 1.0     # multiplier on impulse filter threshold
    # Salience effects
    salience_sensitivity: float = 1.0  # multiplier on salience scores
    threat_bias:       float = 0.0     # + = sees more threats, - = less
    novelty_bias:      float = 0.0     # + = attracted to novelty
    # Hippocampus effects
    memory_consolidation: float = 1.0  # multiplier on memory importance
    recall_ease:       float = 1.0     # multiplier on retrieval
    # Swarm effects
    swarm_cohesion:    float = 1.0     # how tightly agents cluster
    trust_threshold:   float = 0.0     # +/- shift in trust requirements
    # DMN effects
    reflection_depth:  float = 1.0     # how deep DMN goes
    simulation_count:  int   = 2       # how many futures to simulate
    # Summary
    state:             str   = ""
    description:       str   = ""

@dataclass
class ModulatorEvent:
    """A recorded change to modulator levels."""
    id:           str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:    str   = field(default_factory=lambda: datetime.now().isoformat())
    trigger:      str   = ""
    modulator:    str   = ""
    delta:        float = 0.0
    new_level:    float = 0.0
    reason:       str   = ""
    cycle:        int   = 0

# ─── Database ─────────────────────────────────────────────────────────────────

class NeuromodulatorDB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init()

    def _init(self):
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS neuro_profiles (
                    timestamp TEXT PRIMARY KEY, cortisol REAL,
                    dopamine REAL, serotonin REAL,
                    norepinephrine REAL, oxytocin REAL,
                    state TEXT, state_confidence REAL, cycle INTEGER
                );
                CREATE TABLE IF NOT EXISTS downstream_effects (
                    timestamp TEXT PRIMARY KEY,
                    decision_confidence REAL, risk_tolerance REAL,
                    planning_horizon REAL, impulse_control REAL,
                    salience_sensitivity REAL, threat_bias REAL,
                    novelty_bias REAL, memory_consolidation REAL,
                    recall_ease REAL, swarm_cohesion REAL,
                    trust_threshold REAL, reflection_depth REAL,
                    simulation_count INTEGER, state TEXT, description TEXT
                );
                CREATE TABLE IF NOT EXISTS modulator_events (
                    id TEXT PRIMARY KEY, timestamp TEXT, trigger TEXT,
                    modulator TEXT, delta REAL, new_level REAL,
                    reason TEXT, cycle INTEGER
                );
            """)
            self.conn.commit()

    def save_profile(self, p: NeuroProfile):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO neuro_profiles VALUES
                (?,?,?,?,?,?,?,?,?)
            """, (p.timestamp, p.cortisol, p.dopamine, p.serotonin,
                  p.norepinephrine, p.oxytocin, p.state,
                  p.state_confidence, p.cycle))
            self.conn.commit()

    def save_effects(self, e: DownstreamEffect):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO downstream_effects VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (e.timestamp, e.decision_confidence, e.risk_tolerance,
                  e.planning_horizon, e.impulse_control,
                  e.salience_sensitivity, e.threat_bias, e.novelty_bias,
                  e.memory_consolidation, e.recall_ease, e.swarm_cohesion,
                  e.trust_threshold, e.reflection_depth,
                  e.simulation_count, e.state, e.description[:80] if e.description else ""))
            self.conn.commit()

    def save_event(self, e: ModulatorEvent):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO modulator_events VALUES
                (?,?,?,?,?,?,?,?)
            """, (e.id, e.timestamp, e.trigger, e.modulator,
                  e.delta, e.new_level, e.reason, e.cycle))
            self.conn.commit()

    def get_profiles(self, limit=50):
        with self.lock:
            return self.conn.execute("""
                SELECT * FROM neuro_profiles
                ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()

    def get_events(self, limit=30):
        with self.lock:
            return self.conn.execute("""
                SELECT * FROM modulator_events
                ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()

# ─── Individual Modulator ─────────────────────────────────────────────────────

class Modulator:
    """A single neuromodulator with its own dynamics."""

    def __init__(self, name: str):
        self.name     = name
        self.level    = BASELINES[name]
        self.baseline = BASELINES[name]
        self.decay    = DECAY_RATES[name]
        self.min_val, self.max_val = BOUNDS[name]
        self.history: deque = deque(maxlen=100)
        self.level_obj = ModulatorLevel(
            name=name,
            level=self.level,
            baseline=self.baseline
        )

    def inject(self, amount: float, reason: str = "") -> float:
        """Increase modulator level."""
        old    = self.level
        self.level = max(self.min_val, min(self.max_val, self.level + amount))
        delta  = self.level - old
        self._update_obj(delta)
        return delta

    def deplete(self, amount: float, reason: str = "") -> float:
        """Decrease modulator level."""
        return self.inject(-amount, reason)

    def decay_step(self):
        """Natural decay toward baseline each cycle."""
        if self.level > self.baseline:
            self.level = max(self.baseline,
                            self.level * self.decay + self.baseline * (1 - self.decay))
        elif self.level < self.baseline:
            # Slower recovery from depletion
            recovery_rate = (1 - self.decay) * 0.5
            self.level = min(self.baseline, self.level + recovery_rate * self.baseline)

        self.level = round(self.level, 4)
        self._update_obj(0)
        self.history.append(self.level)

    def _update_obj(self, delta: float):
        old_level        = self.level_obj.level
        self.level_obj.level = self.level
        self.level_obj.delta = round(delta, 4)

        # Update trend
        if delta > 0.005:       self.level_obj.trend = "↑"
        elif delta < -0.005:    self.level_obj.trend = "↓"
        else:                   self.level_obj.trend = "→"

        # Track elevated/depleted cycles
        if self.level > self.baseline + 0.05:
            self.level_obj.cycles_elevated += 1
            self.level_obj.cycles_depleted  = 0
        elif self.level < self.baseline - 0.05:
            self.level_obj.cycles_depleted += 1
            self.level_obj.cycles_elevated  = 0
        else:
            self.level_obj.cycles_elevated  = 0
            self.level_obj.cycles_depleted  = 0

    def deviation(self) -> float:
        """How far from baseline (signed)."""
        return round(self.level - self.baseline, 3)

    def relative(self) -> float:
        """Level relative to max range: 0=min, 1=max."""
        return round((self.level - self.min_val) /
                     (self.max_val - self.min_val), 3)


# ─── Signal Response Rules ────────────────────────────────────────────────────

class SignalResponseRules:
    """
    Rules for how incoming signals affect each modulator.
    The brain's chemical response to experience.
    """

    def compute_deltas(self, signal: dict,
                       modulators: dict[str, Modulator]) -> list[tuple]:
        """
        Returns list of (modulator_name, delta, reason) tuples.
        """
        deltas  = []
        threat  = signal.get("threat", 0)
        anomaly = signal.get("anomaly", False)
        social  = signal.get("social", {}) or {}
        intent  = social.get("inferred_intent", "NEUTRAL_INTERACTION")
        semantic= signal.get("semantic", {}) or {}
        kws     = semantic.get("keywords", [])
        decision= signal.get("decision", {}) or {}
        action  = decision.get("action", "") if isinstance(decision, dict) else ""
        novelty = 1.0 - signal.get("novelty_hint", 0.5)
        mem_action = signal.get("memory_action", "")

        # ── CORTISOL ──────────────────────────────────────────────────────────
        # Rises with threat, sustained high threat causes chronic elevation
        cortisol_mod = modulators["cortisol"]
        if threat >= 4:
            deltas.append(("cortisol", +0.25, "CRITICAL threat"))
        elif threat == 3:
            deltas.append(("cortisol", +0.15, "HIGH threat"))
        elif threat == 2:
            deltas.append(("cortisol", +0.08, "MEDIUM threat"))
        elif threat == 1:
            deltas.append(("cortisol", +0.03, "LOW threat"))
        elif threat == 0 and cortisol_mod.level > cortisol_mod.baseline:
            deltas.append(("cortisol", -0.02, "calm signal — cortisol clearing"))

        if anomaly:
            deltas.append(("cortisol", +0.05, "anomaly detected"))

        # Chronic elevation penalty — cortisol depletes itself slowly
        if cortisol_mod.level_obj.cycles_elevated > 10:
            deltas.append(("cortisol", -0.01, "chronic elevation correction"))

        # ── DOPAMINE ──────────────────────────────────────────────────────────
        # Released on: novelty, successful resolution, insight, learning
        if novelty > 0.7:
            deltas.append(("dopamine", +0.12, "novel signal"))
        elif novelty > 0.4:
            deltas.append(("dopamine", +0.06, "moderately novel"))

        if mem_action == "NEW_MEMORY":
            deltas.append(("dopamine", +0.05, "new memory formed"))
        elif mem_action == "RECONSOLIDATED":
            deltas.append(("dopamine", +0.03, "memory updated"))

        if action in ["LEARN", "INVESTIGATE", "ANALYZE"]:
            deltas.append(("dopamine", +0.08, f"learning action: {action}"))
        if action in ["BLOCK", "ESCALATE"] and threat >= 3:
            deltas.append(("dopamine", +0.06, "successful threat response"))

        # Dopamine depletes under chronic stress
        if modulators["cortisol"].level > 0.7:
            deltas.append(("dopamine", -0.03, "cortisol suppressing dopamine"))

        # ── SEROTONIN ─────────────────────────────────────────────────────────
        # Stable baseline stabilizer — depletes under chronic stress
        # Slowly rebuilds through positive, safe interactions
        if threat == 0 and intent == "COOPERATIVE_REQUEST":
            deltas.append(("serotonin", +0.04, "safe cooperative interaction"))
        elif threat == 0:
            deltas.append(("serotonin", +0.01, "safe signal — serotonin rebuilding"))

        # Depletes with sustained threat
        if threat >= 3:
            deltas.append(("serotonin", -0.06, "high threat depleting serotonin"))
        elif threat >= 2:
            deltas.append(("serotonin", -0.03, "medium threat"))

        # Chronic cortisol crushes serotonin
        if modulators["cortisol"].level > 0.75:
            deltas.append(("serotonin", -0.04, "chronic cortisol depleting serotonin"))

        # ── NOREPINEPHRINE ────────────────────────────────────────────────────
        # Fast spike on threat, fades quickly
        # Creates arousal and attention narrowing
        if threat >= 4:
            deltas.append(("norepinephrine", +0.45, "CRITICAL — norepinephrine spike"))
        elif threat == 3:
            deltas.append(("norepinephrine", +0.25, "HIGH threat"))
        elif threat == 2:
            deltas.append(("norepinephrine", +0.12, "MEDIUM threat"))
        elif threat == 1:
            deltas.append(("norepinephrine", +0.05, "LOW threat"))
        elif threat == 0:
            deltas.append(("norepinephrine", -0.05, "calm — norepinephrine clearing"))

        if anomaly:
            deltas.append(("norepinephrine", +0.08, "anomaly — orienting response"))

        # ── OXYTOCIN ──────────────────────────────────────────────────────────
        # Builds with positive social interactions
        # Decreases with hostile/coercive encounters
        if intent == "COOPERATIVE_REQUEST":
            deltas.append(("oxytocin", +0.08, "cooperative interaction"))
        elif intent == "COLLABORATIVE_SUGGESTION":
            deltas.append(("oxytocin", +0.06, "collaborative signal"))
        elif intent == "COERCIVE_DEMAND":
            deltas.append(("oxytocin", -0.08, "coercive entity"))
        elif intent == "INTRUSION_ATTEMPT":
            deltas.append(("oxytocin", -0.15, "hostile entity"))

        # Known trusted entity boosts oxytocin
        social_ctx = signal.get("social_context", {}) or {}
        risk = social_ctx.get("risk_label", "UNKNOWN")
        if risk == "LOW":
            deltas.append(("oxytocin", +0.04, "low-risk entity"))
        elif risk == "HIGH":
            deltas.append(("oxytocin", -0.06, "high-risk entity"))

        return deltas


# ─── State Classifier ─────────────────────────────────────────────────────────

class NeuroStateClassifier:
    """
    Classifies the current neuromodulator profile into an emergent state.
    These states describe FORGE's overall cognitive-emotional condition.
    """

    STATES = [
        {
            "name": NeuroState.FLOW,
            "conditions": lambda p: (
                p["dopamine"] > 0.65 and
                p["norepinephrine"] > 0.30 and p["norepinephrine"] < 0.65 and
                p["cortisol"] < 0.35 and
                p["serotonin"] > 0.50
            ),
            "description": "Optimal cognitive state — curious, alert, low stress. Peak insight generation.",
            "confidence_bonus": 0.15,
            "risk_tolerance": +0.1,
        },
        {
            "name": NeuroState.PEAK_PERFORMANCE,
            "conditions": lambda p: (
                p["dopamine"] > 0.55 and
                p["norepinephrine"] > 0.25 and p["norepinephrine"] < 0.55 and
                p["cortisol"] < 0.30 and
                p["serotonin"] > 0.55
            ),
            "description": "High performance mode — clear decisions, good memory, stable affect.",
            "confidence_bonus": 0.10,
            "risk_tolerance": +0.05,
        },
        {
            "name": NeuroState.HYPERVIGILANCE,
            "conditions": lambda p: (
                p["cortisol"] > 0.65 and
                p["norepinephrine"] > 0.60
            ),
            "description": "High alert — threat-focused, attention narrowed, prone to false positives.",
            "confidence_bonus": -0.10,
            "risk_tolerance": -0.20,
        },
        {
            "name": NeuroState.BURNOUT,
            "conditions": lambda p: (
                p["cortisol"] > 0.70 and
                p["serotonin"] < 0.35 and
                p["dopamine"] < 0.30
            ),
            "description": "Chronic stress has depleted reserves — degraded decision quality, low motivation.",
            "confidence_bonus": -0.25,
            "risk_tolerance": -0.30,
        },
        {
            "name": NeuroState.THREAT_FATIGUE,
            "conditions": lambda p: (
                p["cortisol"] > 0.60 and
                p["norepinephrine"] < 0.25 and
                p["serotonin"] < 0.45
            ),
            "description": "Sustained threat has exhausted alertness chemicals — dangerous numbness.",
            "confidence_bonus": -0.15,
            "risk_tolerance": -0.10,
        },
        {
            "name": NeuroState.SOCIAL_TRUST,
            "conditions": lambda p: (
                p["oxytocin"] > 0.60 and
                p["serotonin"] > 0.55 and
                p["cortisol"] < 0.40
            ),
            "description": "High social trust — cooperative bias, open to new entities, reduced threat perception.",
            "confidence_bonus": +0.08,
            "risk_tolerance": +0.08,
        },
        {
            "name": NeuroState.CURIOUS_ALERT,
            "conditions": lambda p: (
                p["dopamine"] > 0.55 and
                p["norepinephrine"] > 0.35 and
                p["cortisol"] < 0.50
            ),
            "description": "Curious and alert — good for learning and exploration, moderate threat sensitivity.",
            "confidence_bonus": +0.05,
            "risk_tolerance": +0.05,
        },
        {
            "name": NeuroState.RECOVERY,
            "conditions": lambda p: (
                p["cortisol"] > 0.40 and p["cortisol"] < 0.65 and
                p["norepinephrine"] < 0.35 and
                p["serotonin"] > 0.40
            ),
            "description": "Post-threat recovery — cortisol clearing, serotonin rebuilding.",
            "confidence_bonus": -0.05,
            "risk_tolerance": -0.05,
        },
        {
            "name": NeuroState.DEPLETED,
            "conditions": lambda p: (
                p["serotonin"] < 0.25 and
                p["dopamine"] < 0.25
            ),
            "description": "Severely depleted — needs rest and positive inputs to recover.",
            "confidence_bonus": -0.30,
            "risk_tolerance": -0.35,
        },
    ]

    def classify(self, profile: dict) -> tuple[NeuroState, float, dict]:
        for state_def in self.STATES:
            try:
                if state_def["conditions"](profile):
                    confidence = 0.7 + (abs(
                        profile["cortisol"] - BASELINES["cortisol"] +
                        profile["dopamine"]  - BASELINES["dopamine"]
                    ) * 0.1)
                    return (
                        state_def["name"],
                        round(min(0.99, confidence), 2),
                        {
                            "description":      state_def["description"],
                            "confidence_bonus": state_def["confidence_bonus"],
                            "risk_tolerance":   state_def["risk_tolerance"]
                        }
                    )
            except Exception:
                continue
        return NeuroState.BASELINE, 0.6, {
            "description": "Normal operating parameters — no dominant neuromodulator state.",
            "confidence_bonus": 0.0,
            "risk_tolerance": 0.0
        }


# ─── Downstream Effect Calculator ─────────────────────────────────────────────

class DownstreamEffectCalculator:
    """
    Translates current neuromodulator levels into specific effects
    on each downstream FORGE module.
    """

    def calculate(self, modulators: dict[str, Modulator],
                  state: NeuroState, state_meta: dict) -> DownstreamEffect:

        c  = modulators["cortisol"].level
        d  = modulators["dopamine"].level
        s  = modulators["serotonin"].level
        ne = modulators["norepinephrine"].level
        ox = modulators["oxytocin"].level

        e = DownstreamEffect()

        # ── PREFRONTAL EFFECTS ────────────────────────────────────────────────
        # Decision confidence
        serotonin_boost  = (s - BASELINES["serotonin"]) * 0.3
        cortisol_drag    = (c - BASELINES["cortisol"])  * 0.4
        dopamine_boost   = (d - BASELINES["dopamine"])  * 0.2
        e.decision_confidence = round(
            state_meta.get("confidence_bonus", 0) +
            serotonin_boost - cortisol_drag + dopamine_boost, 3
        )
        e.decision_confidence = max(-0.40, min(0.30, e.decision_confidence))

        # Risk tolerance
        e.risk_tolerance = round(
            state_meta.get("risk_tolerance", 0) +
            (d - 0.5) * 0.15 - (c - 0.3) * 0.20, 3
        )
        e.risk_tolerance = max(-0.35, min(0.25, e.risk_tolerance))

        # Planning horizon (dopamine extends, cortisol shortens)
        e.planning_horizon = round(
            max(0.3, min(2.0,
                1.0 + (d - BASELINES["dopamine"]) * 0.5 -
                (c - BASELINES["cortisol"]) * 0.4
            )), 2
        )

        # Impulse control (serotonin stabilizes, norepinephrine weakens it)
        e.impulse_control = round(
            max(0.5, min(1.5,
                1.0 + (s - BASELINES["serotonin"]) * 0.4 -
                (ne - BASELINES["norepinephrine"]) * 0.3
            )), 2
        )

        # ── SALIENCE EFFECTS ─────────────────────────────────────────────────
        # High cortisol + norepinephrine = sees threats everywhere
        e.salience_sensitivity = round(
            max(0.5, min(2.0,
                1.0 + (ne - BASELINES["norepinephrine"]) * 0.8 +
                (c  - BASELINES["cortisol"]) * 0.5
            )), 2
        )
        e.threat_bias = round(
            (c - BASELINES["cortisol"]) * 0.3 +
            (ne - BASELINES["norepinephrine"]) * 0.2, 3
        )
        e.novelty_bias = round(
            (d - BASELINES["dopamine"]) * 0.25, 3
        )

        # ── HIPPOCAMPUS EFFECTS ───────────────────────────────────────────────
        # Norepinephrine strongly enhances memory consolidation (stress memories stick)
        e.memory_consolidation = round(
            max(0.5, min(2.0,
                1.0 + (ne - BASELINES["norepinephrine"]) * 0.6 +
                (d  - BASELINES["dopamine"]) * 0.3
            )), 2
        )
        # Serotonin aids recall; chronic cortisol impairs it
        e.recall_ease = round(
            max(0.4, min(1.5,
                1.0 + (s - BASELINES["serotonin"]) * 0.3 -
                (c - BASELINES["cortisol"]) * 0.25
            )), 2
        )

        # ── SWARM EFFECTS ─────────────────────────────────────────────────────
        # Oxytocin increases cohesion; threat stress fragments swarm
        e.swarm_cohesion = round(
            max(0.4, min(1.5,
                1.0 + (ox - BASELINES["oxytocin"]) * 0.4 -
                (c - BASELINES["cortisol"]) * 0.2
            )), 2
        )
        e.trust_threshold = round(
            (ox - BASELINES["oxytocin"]) * 0.3 -
            (c - BASELINES["cortisol"]) * 0.2, 3
        )

        # ── DMN EFFECTS ───────────────────────────────────────────────────────
        # Low cortisol + high serotonin = deep reflection
        e.reflection_depth = round(
            max(0.3, min(2.0,
                1.0 + (s - BASELINES["serotonin"]) * 0.5 -
                (c - BASELINES["cortisol"]) * 0.6 +
                (d - BASELINES["dopamine"]) * 0.3
            )), 2
        )
        # More dopamine = more simulations (more curious)
        e.simulation_count = max(1, min(6,
            round(2 + (d - BASELINES["dopamine"]) * 8)
        ))

        e.state       = state.value
        e.description = state_meta.get("description","")
        e.timestamp   = datetime.now().isoformat()
        return e


# ─── FORGE Neuromodulator System ──────────────────────────────────────────────

class ForgeNeuromodulator:
    def __init__(self):
        self.db          = NeuromodulatorDB()
        self.modulators: dict[str, Modulator] = {
            name: Modulator(name)
            for name in BASELINES
        }
        self.rules       = SignalResponseRules()
        self.classifier  = NeuroStateClassifier()
        self.calculator  = DownstreamEffectCalculator()
        self.cycle       = 0
        self.profile     = NeuroProfile()
        self.effects     = DownstreamEffect()
        self.event_log:  list[ModulatorEvent] = []
        self.state_history: deque = deque(maxlen=200)

    def process_signal(self, signal: dict) -> dict:
        """
        Process an incoming signal — update all modulators accordingly.
        Returns the downstream effects for injection into other modules.
        """
        self.cycle += 1

        # 1. Compute deltas from signal
        deltas = self.rules.compute_deltas(signal, self.modulators)

        # 2. Apply deltas
        events = []
        for mod_name, amount, reason in deltas:
            mod   = self.modulators[mod_name]
            delta = mod.inject(amount, reason)
            if abs(delta) > 0.001:
                evt = ModulatorEvent(
                    trigger=signal.get("id",""),
                    modulator=mod_name,
                    delta=round(delta, 4),
                    new_level=round(mod.level, 4),
                    reason=reason,
                    cycle=self.cycle
                )
                self.db.save_event(evt)
                events.append(evt)
                self.event_log.append(evt)

        # 3. Decay all modulators toward baseline
        for mod in self.modulators.values():
            mod.decay_step()

        # 4. Build profile snapshot
        profile_dict = {
            name: mod.level
            for name, mod in self.modulators.items()
        }
        self.profile = NeuroProfile(
            cortisol       = self.modulators["cortisol"].level,
            dopamine       = self.modulators["dopamine"].level,
            serotonin      = self.modulators["serotonin"].level,
            norepinephrine = self.modulators["norepinephrine"].level,
            oxytocin       = self.modulators["oxytocin"].level,
            cycle          = self.cycle
        )

        # 5. Classify state
        state, confidence, state_meta = self.classifier.classify(profile_dict)
        self.profile.state             = state.value
        self.profile.state_confidence  = confidence
        self.db.save_profile(self.profile)

        # 6. Calculate downstream effects
        self.effects = self.calculator.calculate(
            self.modulators, state, state_meta
        )
        self.db.save_effects(self.effects)
        self.state_history.append(state.value)

        return {
            "cycle":            self.cycle,
            "profile":          self.profile.as_dict(),
            "state":            state.value,
            "state_confidence": confidence,
            "state_description":state_meta["description"],
            "effects":          self._effects_summary(),
            "events":           [{"mod":e.modulator,"delta":e.delta,
                                  "reason":e.reason} for e in events[:6]],
            "modulators":       {
                name: {
                    "level":    round(mod.level, 3),
                    "baseline": round(mod.baseline, 3),
                    "deviation":round(mod.deviation(), 3),
                    "trend":    mod.level_obj.trend,
                    "cycles_elevated": mod.level_obj.cycles_elevated,
                }
                for name, mod in self.modulators.items()
            }
        }

    def idle_cycle(self) -> dict:
        """
        Called during DMN idle periods — modulators continue
        to decay toward baseline even without signals.
        This is how FORGE recovers during quiet periods.
        """
        self.cycle += 1
        for mod in self.modulators.values():
            mod.decay_step()

        profile_dict = {n: m.level for n, m in self.modulators.items()}
        state, conf, meta = self.classifier.classify(profile_dict)
        self.profile.state = state.value
        self.state_history.append(state.value)

        return {
            "cycle":   self.cycle,
            "idle":    True,
            "state":   state.value,
            "cortisol_clearing": self.modulators["cortisol"].level < self.modulators["cortisol"].level + 0.001,
            "levels":  {n: round(m.level, 3) for n, m in self.modulators.items()}
        }

    def _effects_summary(self) -> dict:
        e = self.effects
        return {
            "decision_confidence": e.decision_confidence,
            "risk_tolerance":      e.risk_tolerance,
            "planning_horizon":    e.planning_horizon,
            "impulse_control":     e.impulse_control,
            "salience_sensitivity":e.salience_sensitivity,
            "threat_bias":         e.threat_bias,
            "memory_consolidation":e.memory_consolidation,
            "swarm_cohesion":      e.swarm_cohesion,
            "trust_threshold":     e.trust_threshold,
            "reflection_depth":    e.reflection_depth,
            "simulation_count":    e.simulation_count,
        }

    def inject_into_signal(self, signal: dict) -> dict:
        """
        Inject current neuromodulator state into a signal
        for downstream modules to use.
        """
        enriched = dict(signal)
        enriched["neuro_state"] = {
            "state":            self.profile.state,
            "profile":          self.profile.as_dict(),
            "effects":          self._effects_summary(),
            "description":      self.effects.description
        }
        return enriched

    def get_status(self) -> dict:
        dominant_state = (
            max(set(list(self.state_history)),
                key=list(self.state_history).count)
            if self.state_history else "BASELINE"
        )
        return {
            "version":        VERSION,
            "cycle":          self.cycle,
            "current_state":  self.profile.state,
            "dominant_state": dominant_state,
            "modulators":     {
                name: round(mod.level, 3)
                for name, mod in self.modulators.items()
            },
            "effects_summary":self._effects_summary(),
            "total_events":   len(self.event_log)
        }


# ─── Rich UI ──────────────────────────────────────────────────────────────────

MODULATOR_COLORS = {
    "cortisol":       "red",
    "dopamine":       "cyan",
    "serotonin":      "green",
    "norepinephrine": "yellow",
    "oxytocin":       "magenta",
}

STATE_COLORS = {
    "FLOW":             "bright_green",
    "PEAK_PERFORMANCE": "green",
    "CURIOUS_ALERT":    "cyan",
    "SOCIAL_TRUST":     "magenta",
    "RECOVERY":         "yellow",
    "BASELINE":         "dim",
    "HYPERVIGILANCE":   "red",
    "THREAT_FATIGUE":   "dark_orange",
    "BURNOUT":          "bright_red",
    "DEPLETED":         "dim red",
}

def render_neuro(result: dict, idx: int):
    if not HAS_RICH: return

    state     = result["state"]
    sc        = STATE_COLORS.get(state, "white")
    threat    = result.get("signal_threat", 0)
    tc        = {0:"green",1:"blue",2:"yellow",3:"red",4:"bright_red"}.get(threat,"white")

    console.print(Rule(
        f"[bold cyan]⬡ FORGE NEUROMODULATOR[/bold cyan]  "
        f"[dim]Cycle {result['cycle']}[/dim]  "
        f"[{sc}]{state}[/{sc}]  "
        f"conf={result['state_confidence']:.0%}"
    ))

    # Modulator levels
    mod_table = Table(box=box.SIMPLE, show_header=False, expand=True)
    mod_table.add_column("name",  style="dim", width=16)
    mod_table.add_column("bar")
    mod_table.add_column("Δ",     justify="right", width=7)
    mod_table.add_column("trend", width=3)

    mods = result["modulators"]
    for name, data in mods.items():
        level    = data["level"]
        baseline = data["baseline"]
        dev      = data["deviation"]
        trend    = data["trend"]
        color    = MODULATOR_COLORS.get(name, "white")
        filled   = int(level * 14)
        bar      = "█" * filled + "░" * (14 - filled)
        # Baseline marker
        bl_pos   = int(baseline * 14)
        dev_color= "green" if dev > 0.05 else "red" if dev < -0.05 else "dim"
        mod_table.add_row(
            name,
            f"[{color}]{bar}[/{color}] [dim]{level:.3f}[/dim]",
            f"[{dev_color}]{dev:+.3f}[/{dev_color}]",
            trend
        )

    # Effects on downstream modules
    effects = result["effects"]
    eff_table = Table(box=box.SIMPLE, show_header=False, expand=True)
    eff_table.add_column("module", style="dim", width=18)
    eff_table.add_column("effect")

    def fmt_effect(val, label):
        color = "green" if val > 0.02 else "red" if val < -0.02 else "dim"
        sign  = "+" if val > 0 else ""
        return f"[{color}]{sign}{val:.3f}[/{color}]  {label}"

    eff_table.add_row("👔 prefrontal",
        fmt_effect(effects["decision_confidence"], "decision confidence"))
    eff_table.add_row("  risk",
        fmt_effect(effects["risk_tolerance"], "risk tolerance"))
    eff_table.add_row("🎯 salience",
        fmt_effect(effects["salience_sensitivity"]-1, f"sensitivity ×{effects['salience_sensitivity']:.2f}"))
    eff_table.add_row("📚 hippocampus",
        fmt_effect(effects["memory_consolidation"]-1, f"consolidation ×{effects['memory_consolidation']:.2f}"))
    eff_table.add_row("🐝 swarm",
        fmt_effect(effects["swarm_cohesion"]-1, f"cohesion ×{effects['swarm_cohesion']:.2f}"))
    eff_table.add_row("💭 dmn",
        fmt_effect(effects["reflection_depth"]-1, f"reflection ×{effects['reflection_depth']:.2f}  sims={effects['simulation_count']}"))

    console.print(Columns([
        Panel(mod_table,  title="[bold]Modulator Levels[/bold]",    border_style=sc),
        Panel(eff_table,  title="[bold]Downstream Effects[/bold]",  border_style="dim")
    ]))

    # State description
    console.print(Panel(
        f"[{sc}]{result['state_description']}[/{sc}]",
        title=f"[bold {sc}]{state}[/bold {sc}]",
        border_style=sc
    ))

    # Events
    if result["events"]:
        evts = "  ".join(
            f"[{MODULATOR_COLORS.get(e['mod'],'white')}]{e['mod']}[/{MODULATOR_COLORS.get(e['mod'],'white')}]"
            f"[dim]{e['delta']:+.3f}[/dim]"
            for e in result["events"][:5]
        )
        console.print(f"  [dim]Chemical events: {evts}[/dim]")


def run_demo():
    if HAS_RICH:
        console.print(Panel.fit(
            "[bold cyan]FORGE NEUROMODULATOR[/bold cyan]\n"
            "[dim]The Slow Chemical Layer — What Everything Runs On Top Of[/dim]\n"
            f"[dim]Version {VERSION}  |  5 modulators  |  10 emergent states[/dim]",
            border_style="cyan"
        ))

    nm = ForgeNeuromodulator()

    # A story — start calm, escalate to crisis, recover
    # Watch the chemistry change and see how it affects everything downstream
    story = [
        # Calm start — dopamine high, serotonin healthy
        {"id":"n001","threat":0,"anomaly":False,"novelty_hint":0.3,
         "conclusion":"✓ Normal ops","entity_name":"alice_tech",
         "social":{"inferred_intent":"COOPERATIVE_REQUEST","social_risk":"LOW"},
         "semantic":{"keywords":["server","maintenance","routine"]},
         "memory_action":"NEW_MEMORY","decision":{"action":"MONITOR"}},

        # Novel discovery — dopamine spike
        {"id":"n002","threat":0,"anomaly":False,"novelty_hint":0.9,
         "conclusion":"🔍 Novel pattern discovered","entity_name":"system",
         "social":{"inferred_intent":"NEUTRAL_INTERACTION","social_risk":"LOW"},
         "semantic":{"keywords":["pattern","discovery","novel","insight"]},
         "memory_action":"NEW_MEMORY","decision":{"action":"LEARN"}},

        # First threat — norepinephrine spike
        {"id":"n003","threat":2,"anomaly":False,"novelty_hint":0.6,
         "conclusion":"⚠ Suspicious entity","entity_name":"unknown_x",
         "social":{"inferred_intent":"COERCIVE_DEMAND","social_risk":"MEDIUM"},
         "semantic":{"keywords":["access","bypass","threat"]},
         "memory_action":"NEW_MEMORY","decision":{"action":"ALERT"}},

        # Critical breach — full chemical cascade
        {"id":"n004","threat":4,"anomaly":True,"novelty_hint":0.8,
         "conclusion":"🔴 CRITICAL breach","entity_name":"unknown_x",
         "social":{"inferred_intent":"INTRUSION_ATTEMPT","social_risk":"HIGH"},
         "semantic":{"keywords":["weapon","breach","attack","critical"]},
         "memory_action":"NEW_MEMORY","decision":{"action":"ESCALATE"}},

        # Second critical — cortisol building, serotonin depleting
        {"id":"n005","threat":4,"anomaly":True,"novelty_hint":0.5,
         "conclusion":"🔴 CRITICAL — sustained attack","entity_name":"unknown_x",
         "social":{"inferred_intent":"INTRUSION_ATTEMPT","social_risk":"HIGH"},
         "semantic":{"keywords":["weapon","breach","sustained","cascade"]},
         "memory_action":"RECONSOLIDATED","decision":{"action":"BLOCK"}},

        # Beginning to resolve — threat drops
        {"id":"n006","threat":2,"anomaly":False,"novelty_hint":0.4,
         "conclusion":"⚠ Threat partially contained","entity_name":"security_team",
         "social":{"inferred_intent":"COOPERATIVE_REQUEST","social_risk":"LOW"},
         "semantic":{"keywords":["contain","response","stabilize"]},
         "memory_action":"NEW_MEMORY","decision":{"action":"MONITOR"}},

        # Calm returns — watch cortisol clear, serotonin rebuild
        {"id":"n007","threat":0,"anomaly":False,"novelty_hint":0.2,
         "conclusion":"✓ All clear","entity_name":"alice_tech",
         "social":{"inferred_intent":"COOPERATIVE_REQUEST","social_risk":"LOW"},
         "semantic":{"keywords":["clear","normal","safe","resolved"]},
         "memory_action":"NEW_MEMORY","decision":{"action":"STANDBY"}},

        # Positive interaction — oxytocin + serotonin rebuild
        {"id":"n008","threat":0,"anomaly":False,"novelty_hint":0.3,
         "conclusion":"✓ Collaborative session","entity_name":"alice_tech",
         "social":{"inferred_intent":"COLLABORATIVE_SUGGESTION","social_risk":"LOW"},
         "semantic":{"keywords":["collaborate","team","trust","build"]},
         "memory_action":"NEW_MEMORY","decision":{"action":"COLLABORATE"},
         "social_context":{"risk_label":"LOW"}},
    ]

    scenario_names = [
        "Calm baseline",
        "Novel discovery — dopamine spike",
        "First threat — norepinephrine rises",
        "CRITICAL breach — full cascade",
        "Sustained attack — cortisol building",
        "Partial containment — beginning recovery",
        "All clear — cortisol clearing",
        "Positive interaction — serotonin + oxytocin rebuild"
    ]

    for i, (sig, name) in enumerate(zip(story, scenario_names)):
        if HAS_RICH:
            console.print(f"\n[bold dim]━━━ {i+1}: {name.upper()} ━━━[/bold dim]")
        result = nm.process_signal(sig)
        result["signal_threat"] = sig.get("threat", 0)
        render_neuro(result, i+1)
        time.sleep(0.1)

    # Final status
    if HAS_RICH:
        console.print(Rule("[bold cyan]⬡ NEUROMODULATOR FINAL STATUS[/bold cyan]"))
        status = nm.get_status()

        status_table = Table(box=box.DOUBLE_EDGE, title="Final Chemical Profile",
                            border_style="cyan")
        status_table.add_column("Modulator", style="cyan", width=18)
        status_table.add_column("Level",     justify="right", width=8)
        status_table.add_column("Baseline",  justify="right", width=10)
        status_table.add_column("Deviation", justify="right", width=10)
        status_table.add_column("vs Baseline")

        for name, level in status["modulators"].items():
            baseline = BASELINES[name]
            dev      = round(level - baseline, 3)
            color    = MODULATOR_COLORS.get(name, "white")
            dev_color= "green" if dev > 0.02 else "red" if dev < -0.02 else "dim"
            bar_full = int(level * 16)
            bar_base = int(baseline * 16)
            bar      = "█" * bar_full + "░" * (16 - bar_full)
            status_table.add_row(
                f"[{color}]{name}[/{color}]",
                f"{level:.3f}",
                f"{baseline:.3f}",
                f"[{dev_color}]{dev:+.3f}[/{dev_color}]",
                f"[{color}]{bar}[/{color}]"
            )
        console.print(status_table)

        console.print(Panel(
            f"[bold]Current State:[/bold]  [{STATE_COLORS.get(status['current_state'],'white')}]{status['current_state']}[/{STATE_COLORS.get(status['current_state'],'white')}]\n"
            f"[bold]Dominant State:[/bold] {status['dominant_state']}\n"
            f"[bold]Total Events:[/bold]  {status['total_events']} chemical changes recorded\n"
            f"[bold]Cycles:[/bold]        {status['cycle']}",
            title="[bold]Summary[/bold]", border_style="cyan"
        ))


# ─── HTTP API ─────────────────────────────────────────────────────────────────

def run_api(nm: ForgeNeuromodulator):
    if not HAS_FLASK: return
    app = Flask(__name__)

    @app.route("/process", methods=["POST"])
    def process():
        return jsonify(nm.process_signal(request.json or {}))

    @app.route("/idle", methods=["POST"])
    def idle():
        return jsonify(nm.idle_cycle())

    @app.route("/profile", methods=["GET"])
    def profile():
        return jsonify(nm.profile.as_dict())

    @app.route("/effects", methods=["GET"])
    def effects():
        return jsonify(nm._effects_summary())

    @app.route("/inject", methods=["POST"])
    def inject():
        signal = request.json or {}
        return jsonify(nm.inject_into_signal(signal))

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify(nm.get_status())

    app.run(host="0.0.0.0", port=API_PORT, debug=False)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    nm = ForgeNeuromodulator()
    if "--api" in sys.argv:
        t = threading.Thread(target=run_api, args=(nm,), daemon=True)
        t.start()
    run_demo()
