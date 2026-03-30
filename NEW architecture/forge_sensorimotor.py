"""
FORGE Sensorimotor Network — forge_sensorimotor.py
====================================================
AI analog of the brain's sensorimotor system.

Three-tier response architecture:

  REFLEXIVE  (~5-15ms)   Sub-cognitive. Pattern fires action directly.
                          No thinking. No deliberation. Pure stimulus→response.
                          Controlled by norepinephrine threshold.

  FAST       (~50-100ms) Salience-gated. Known patterns trigger learned programs.
                          Minimal deliberation — recognition + execution.

  DELIBERATE (~200-300ms) Full pipeline. Complex novel situations.
                           Prefrontal involved. Considered response.

This is the difference between:
  FLINCHING      → sensorimotor reflex
  DUCKING        → fast motor program
  DECIDING TO DODGE → deliberate prefrontal

Components:
  ReflexArc           → hardwired threat→action patterns (<15ms)
  MotorProgram        → learned action sequences (fast execution)
  SensorimotorMemory  → stores successful action sequences
  ProprioceptionLayer → FORGE's sense of its own state
  ActionBuffer        → queues and prioritizes pending actions
  NeuroThreshold      → norepinephrine modulates reflex sensitivity
  MotorLearning       → reinforces successful programs over time
  InhibitionLayer     → suppresses competing reflexes (impulse control)
"""

import json
import time
import uuid
import sqlite3
import threading
import math
from datetime import datetime
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

DB_PATH  = "forge_sensorimotor.db"
API_PORT = 7788
VERSION  = "1.0.0"

# Timing targets
REFLEX_TARGET_MS   = 15    # reflexes should fire in < 15ms
FAST_TARGET_MS     = 80    # fast programs < 80ms
DELIBERATE_MS      = 260   # deliberate already handled by pipeline

# Reflex threshold — norepinephrine modulates this
# High NE → lower threshold → hair-trigger reflexes
BASE_REFLEX_THRESHOLD  = 0.75   # salience score to trigger reflex
NE_SENSITIVITY         = 0.30   # how much NE shifts the threshold

# Motor learning
LEARNING_RATE      = 0.12   # how quickly programs strengthen
DECAY_RATE         = 0.995  # how slowly unused programs fade

console = Console() if HAS_RICH else None

# ─── Enums ────────────────────────────────────────────────────────────────────

class ResponseTier(Enum):
    REFLEX     = "REFLEX"      # sub-cognitive, automatic
    FAST       = "FAST"        # learned program, quick
    DELIBERATE = "DELIBERATE"  # full pipeline, slow

class ActionCategory(Enum):
    DEFENSIVE  = "DEFENSIVE"   # blocking, evading, shielding
    ALERT      = "ALERT"       # signaling, broadcasting
    APPROACH   = "APPROACH"    # moving toward
    WITHDRAW   = "WITHDRAW"    # pulling back, retreating
    FREEZE     = "FREEZE"      # hold position, assess
    EXECUTE    = "EXECUTE"     # carry out a task
    ORIENT     = "ORIENT"      # turn attention toward

class MotorState(Enum):
    IDLE       = "IDLE"
    PREPARING  = "PREPARING"
    EXECUTING  = "EXECUTING"
    HOLDING    = "HOLDING"
    RECOVERING = "RECOVERING"

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class ReflexRule:
    """A hardwired stimulus→response mapping. Cannot be unlearned."""
    id:          str   = ""
    name:        str   = ""
    trigger:     dict  = field(default_factory=dict)   # conditions that fire this
    action:      str   = ""
    category:    str   = ActionCategory.DEFENSIVE.value
    latency_ms:  float = 10.0
    priority:    int   = 10     # higher = fires first
    description: str   = ""
    fire_count:  int   = 0

@dataclass
class MotorProgram:
    """
    A learned sequence of actions that executes as a unit.
    Like muscle memory — once learned, fires without thinking.
    """
    id:          str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:        str   = ""
    trigger_pattern: dict = field(default_factory=dict)
    steps:       list  = field(default_factory=list)
    category:    str   = ActionCategory.EXECUTE.value
    strength:    float = 0.5    # 0-1, increases with success
    latency_ms:  float = 50.0
    success_count: int = 0
    fail_count:  int   = 0
    last_used:   str   = field(default_factory=lambda: datetime.now().isoformat())
    learned_from: str  = ""     # which pipeline outcome taught this

    @property
    def reliability(self) -> float:
        total = self.success_count + self.fail_count
        if total == 0: return 0.5
        return round(self.success_count / total, 3)

@dataclass
class SensorimotorAction:
    """A single action dispatched by the sensorimotor system."""
    id:          str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:   str   = field(default_factory=lambda: datetime.now().isoformat())
    tier:        str   = ResponseTier.REFLEX.value
    action:      str   = ""
    category:    str   = ""
    latency_ms:  float = 0.0
    trigger:     str   = ""
    program_id:  str   = ""
    reflex_id:   str   = ""
    success:     bool  = True
    neuro_state: dict  = field(default_factory=dict)

@dataclass
class ProprioceptionState:
    """FORGE's sense of its own current state."""
    timestamp:        str   = field(default_factory=lambda: datetime.now().isoformat())
    motor_state:      str   = MotorState.IDLE.value
    current_action:   str   = ""
    action_queue_len: int   = 0
    last_reflex:      str   = ""
    last_program:     str   = ""
    fatigue:          float = 0.0   # 0-1, builds with rapid firing
    readiness:        float = 1.0   # 0-1, inverse of fatigue
    recent_tier:      str   = ""    # what tier was last used
    response_load:    float = 0.0   # how busy the motor system is

# ─── Database ─────────────────────────────────────────────────────────────────

class SensorimotorDB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init()

    def _init(self):
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS motor_programs (
                    id TEXT PRIMARY KEY, name TEXT,
                    trigger_pattern TEXT, steps TEXT,
                    category TEXT, strength REAL, latency_ms REAL,
                    success_count INTEGER, fail_count INTEGER,
                    last_used TEXT, learned_from TEXT
                );
                CREATE TABLE IF NOT EXISTS actions_taken (
                    id TEXT PRIMARY KEY, timestamp TEXT, tier TEXT,
                    action TEXT, category TEXT, latency_ms REAL,
                    trigger TEXT, program_id TEXT, reflex_id TEXT,
                    success INTEGER, neuro_state TEXT
                );
                CREATE TABLE IF NOT EXISTS proprioception_log (
                    timestamp TEXT PRIMARY KEY, motor_state TEXT,
                    current_action TEXT, queue_len INTEGER,
                    last_reflex TEXT, last_program TEXT,
                    fatigue REAL, readiness REAL, response_load REAL
                );
                CREATE TABLE IF NOT EXISTS learning_events (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    program_id TEXT, outcome TEXT,
                    strength_before REAL, strength_after REAL,
                    signal_context TEXT
                );
            """)
            self.conn.commit()

    def save_program(self, p: MotorProgram):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO motor_programs VALUES
                (?,?,?,?,?,?,?,?,?,?,?)
            """, (p.id, p.name, json.dumps(p.trigger_pattern),
                  json.dumps(p.steps), p.category, p.strength,
                  p.latency_ms, p.success_count, p.fail_count,
                  p.last_used, p.learned_from))
            self.conn.commit()

    def save_action(self, a: SensorimotorAction):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO actions_taken VALUES
                (?,?,?,?,?,?,?,?,?,?,?)
            """, (a.id, a.timestamp, a.tier, a.action, a.category,
                  a.latency_ms, a.trigger, a.program_id, a.reflex_id,
                  int(a.success), json.dumps(a.neuro_state)))
            self.conn.commit()

    def save_proprioception(self, p: ProprioceptionState):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO proprioception_log VALUES
                (?,?,?,?,?,?,?,?,?)
            """, (p.timestamp, p.motor_state, p.current_action,
                  p.action_queue_len, p.last_reflex, p.last_program,
                  p.fatigue, p.readiness, p.response_load))
            self.conn.commit()

    def save_learning(self, program_id: str, outcome: str,
                      before: float, after: float, context: dict):
        with self.lock:
            self.conn.execute("""
                INSERT INTO learning_events VALUES (?,?,?,?,?,?,?)
            """, (str(uuid.uuid4())[:8], datetime.now().isoformat(),
                  program_id, outcome, before, after,
                  json.dumps(context)))
            self.conn.commit()

    def get_programs(self, min_strength=0.0):
        with self.lock:
            return self.conn.execute("""
                SELECT id, name, strength, success_count,
                       fail_count, latency_ms, category
                FROM motor_programs WHERE strength >= ?
                ORDER BY strength DESC
            """, (min_strength,)).fetchall()

    def get_recent_actions(self, limit=20):
        with self.lock:
            return self.conn.execute("""
                SELECT timestamp, tier, action, latency_ms, success
                FROM actions_taken ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()


# ─── Reflex Arc ───────────────────────────────────────────────────────────────

class ReflexArc:
    """
    Hardwired stimulus→response mappings.
    These cannot be unlearned — they are FORGE's instincts.
    Fire before any deliberation occurs.
    Latency: 5-15ms.
    """

    # Built-in reflexes — ordered by priority (highest first)
    REFLEXES = [
        ReflexRule(
            id="R001", name="THREAT_CRITICAL_BLOCK",
            trigger={"threat": 4, "min_threat": 4},
            action="EMERGENCY_BLOCK",
            category=ActionCategory.DEFENSIVE.value,
            latency_ms=8.0, priority=100,
            description="Threat=4 → immediate block. No thinking required."
        ),
        ReflexRule(
            id="R002", name="WEAPON_DETECTED_SHIELD",
            trigger={"visual_threat_objects": 2, "min_visual_threats": 2},
            action="ACTIVATE_DEFENSIVE_POSTURE",
            category=ActionCategory.DEFENSIVE.value,
            latency_ms=10.0, priority=95,
            description="Multiple weapon objects → defensive posture immediately."
        ),
        ReflexRule(
            id="R003", name="DISTRESS_SIGNAL_ORIENT",
            trigger={"auditory_anomaly": True, "threat_min": 2},
            action="ORIENT_TO_DISTRESS_SOURCE",
            category=ActionCategory.ORIENT.value,
            latency_ms=12.0, priority=85,
            description="Auditory distress + threat → orient immediately."
        ),
        ReflexRule(
            id="R004", name="INTRUSION_FREEZE_ASSESS",
            trigger={"intent": "INTRUSION_ATTEMPT", "threat_min": 3},
            action="FREEZE_AND_ASSESS",
            category=ActionCategory.FREEZE.value,
            latency_ms=11.0, priority=80,
            description="Confirmed intrusion → freeze and assess before acting."
        ),
        ReflexRule(
            id="R005", name="ANOMALY_ALERT_BROADCAST",
            trigger={"anomaly": True, "threat_min": 0},
            action="BROADCAST_ANOMALY_ALERT",
            category=ActionCategory.ALERT.value,
            latency_ms=14.0, priority=70,
            description="Any anomaly → broadcast alert without deliberation."
        ),
        ReflexRule(
            id="R006", name="KNOWN_HOSTILE_WITHDRAW",
            trigger={"social_risk": "HIGH", "repeat_offender": True},
            action="WITHDRAW_FROM_ENTITY",
            category=ActionCategory.WITHDRAW.value,
            latency_ms=13.0, priority=75,
            description="Known hostile repeat offender → withdraw immediately."
        ),
        ReflexRule(
            id="R007", name="TRUSTED_ENTITY_APPROACH",
            trigger={"social_risk": "LOW", "trust_min": 0.7, "threat_max": 0},
            action="OPEN_COOPERATIVE_CHANNEL",
            category=ActionCategory.APPROACH.value,
            latency_ms=15.0, priority=40,
            description="Trusted entity, no threat → open cooperative channel."
        ),
    ]

    def __init__(self):
        self.rules = {r.id: r for r in self.REFLEXES}
        self.inhibited: set = set()   # temporarily suppressed reflexes

    def check(self, signal: dict,
              neuro_threshold: float) -> Optional[tuple[ReflexRule, float]]:
        """
        Check if any reflex fires for this signal.
        Returns (rule, actual_latency) or None.
        neuro_threshold: adjusted threshold based on norepinephrine.
        """
        threat   = signal.get("threat", 0)
        anomaly  = signal.get("anomaly", False)
        social   = signal.get("social", {}) or {}
        intent   = social.get("inferred_intent","") if isinstance(social,dict) else ""
        visual   = signal.get("visual", {}) or {}
        auditory = signal.get("auditory", {}) or {}
        social_ctx = signal.get("social_context", {}) or {}
        sal_score  = signal.get("salience_score", 0.0)

        # Only reflexes fire if signal is salient enough
        if sal_score < neuro_threshold * 0.6 and threat < 3:
            return None

        candidates = []

        for rule in sorted(self.rules.values(),
                          key=lambda r: r.priority, reverse=True):
            if rule.id in self.inhibited:
                continue

            fired = self._evaluate_trigger(rule.trigger, {
                "threat":              threat,
                "anomaly":             anomaly,
                "intent":              intent,
                "visual_threat_objects":visual.get("threat_objects", 0),
                "auditory_anomaly":    auditory.get("anomaly_detected", False),
                "social_risk":         social.get("social_risk",
                                       social_ctx.get("risk_label","LOW")),
                "trust":               social_ctx.get("trust_score", 0.5),
                "repeat_offender":     social_ctx.get("behavior_pattern","") == "REPEAT_OFFENDER"
            })

            if fired:
                # Add small jitter to simulate biological timing variance
                latency = rule.latency_ms * (0.9 + 0.2 * (1 - rule.priority/100))
                candidates.append((rule, latency))

        if not candidates:
            return None

        # Highest priority wins
        winner = max(candidates, key=lambda x: x[0].priority)
        winner[0].fire_count += 1
        return winner

    def _evaluate_trigger(self, trigger: dict, context: dict) -> bool:
        """Evaluate all trigger conditions."""
        for key, value in trigger.items():
            if key == "min_threat" and context.get("threat", 0) < value:
                return False
            elif key == "threat" and context.get("threat", 0) != value:
                return False
            elif key == "threat_min" and context.get("threat", 0) < value:
                return False
            elif key == "threat_max" and context.get("threat", 0) > value:
                return False
            elif key == "min_visual_threats" and context.get("visual_threat_objects",0) < value:
                return False
            elif key == "visual_threat_objects" and context.get("visual_threat_objects",0) < value:
                return False
            elif key == "auditory_anomaly" and context.get("auditory_anomaly") != value:
                return False
            elif key == "anomaly" and context.get("anomaly") != value:
                return False
            elif key == "intent" and context.get("intent","") != value:
                return False
            elif key == "social_risk" and context.get("social_risk","") != value:
                return False
            elif key == "trust_min" and context.get("trust", 0.5) < value:
                return False
            elif key == "repeat_offender" and context.get("repeat_offender") != value:
                return False
        return True

    def inhibit(self, reflex_id: str, duration_cycles: int = 3):
        """Temporarily suppress a reflex (impulse control)."""
        self.inhibited.add(reflex_id)

    def release(self, reflex_id: str):
        self.inhibited.discard(reflex_id)


# ─── Motor Program Library ────────────────────────────────────────────────────

class MotorProgramLibrary:
    """
    Library of learned action sequences.
    Programs are seeded from common patterns, then strengthened through use.
    """

    SEED_PROGRAMS = [
        MotorProgram(
            id="MP001", name="THREAT_ESCALATION_SEQUENCE",
            trigger_pattern={"threat_range": [2, 3], "entity_known": True},
            steps=["assess_entity_history", "consult_bridge_social",
                   "calculate_threat_trajectory", "alert_swarm",
                   "prepare_block_if_needed"],
            category=ActionCategory.DEFENSIVE.value,
            strength=0.7, latency_ms=45.0,
            learned_from="repeated_threat_encounters"
        ),
        MotorProgram(
            id="MP002", name="COOPERATIVE_ENGAGEMENT",
            trigger_pattern={"intent": "COOPERATIVE_REQUEST", "trust_min": 0.6},
            steps=["verify_entity_trust", "open_channel",
                   "share_relevant_context", "log_interaction"],
            category=ActionCategory.APPROACH.value,
            strength=0.65, latency_ms=35.0,
            learned_from="successful_collaborations"
        ),
        MotorProgram(
            id="MP003", name="ANOMALY_INVESTIGATION",
            trigger_pattern={"anomaly": True, "threat_max": 2},
            steps=["freeze_current_task", "orient_to_anomaly",
                   "pull_temporal_context", "cross_reference_hippocampus",
                   "report_finding"],
            category=ActionCategory.ORIENT.value,
            strength=0.6, latency_ms=55.0,
            learned_from="pattern_analysis_sessions"
        ),
        MotorProgram(
            id="MP004", name="POST_CRISIS_RECOVERY",
            trigger_pattern={"threat_dropping": True, "prev_threat_min": 3},
            steps=["confirm_threat_cleared", "stand_down_swarm",
                   "initiate_hippocampus_consolidation",
                   "trigger_dmn_debrief", "rebuild_baseline"],
            category=ActionCategory.WITHDRAW.value,
            strength=0.55, latency_ms=65.0,
            learned_from="crisis_resolution_events"
        ),
        MotorProgram(
            id="MP005", name="NOVEL_ENTITY_PROTOCOL",
            trigger_pattern={"entity_known": False, "threat_max": 2},
            steps=["passive_observation", "build_initial_social_model",
                   "check_associates_via_bridge", "assign_provisional_trust",
                   "monitor_with_low_commitment"],
            category=ActionCategory.FREEZE.value,
            strength=0.5, latency_ms=60.0,
            learned_from="first_encounter_patterns"
        ),
        MotorProgram(
            id="MP006", name="REPEAT_OFFENDER_LOCKDOWN",
            trigger_pattern={"repeat_offender": True, "threat_min": 2},
            steps=["flag_entity_in_bridge", "maximum_salience_lock",
                   "pre_position_defenders", "prepare_block_sequence",
                   "alert_all_modules"],
            category=ActionCategory.DEFENSIVE.value,
            strength=0.75, latency_ms=40.0,
            learned_from="repeat_threat_encounters"
        ),
        MotorProgram(
            id="MP007", name="LEARNING_CAPTURE",
            trigger_pattern={"novelty_min": 0.6, "threat_max": 1},
            steps=["extract_semantic_keywords",
                   "push_to_temporal_semantic_memory",
                   "update_dmn_replay_buffer",
                   "reinforce_relevant_patterns"],
            category=ActionCategory.EXECUTE.value,
            strength=0.6, latency_ms=30.0,
            learned_from="insight_generation_cycles"
        ),
    ]

    def __init__(self, db: SensorimotorDB):
        self.db       = db
        self.programs: dict[str, MotorProgram] = {}
        self._seed()

    def _seed(self):
        for p in self.SEED_PROGRAMS:
            self.programs[p.id] = p
            self.db.save_program(p)

    def match(self, signal: dict) -> Optional[MotorProgram]:
        """Find the best matching motor program for this signal."""
        threat   = signal.get("threat", 0)
        anomaly  = signal.get("anomaly", False)
        social   = signal.get("social", {}) or {}
        intent   = social.get("inferred_intent","") if isinstance(social,dict) else ""
        social_ctx = signal.get("social_context", {}) or {}
        novelty  = 1.0 - signal.get("novelty_hint", 0.5)
        prev_threat = signal.get("prev_threat", 0)
        entity_known = social_ctx.get("known", False)
        repeat_offender = social_ctx.get("behavior_pattern","") == "REPEAT_OFFENDER"
        trust    = social_ctx.get("trust_score", 0.5)

        context = {
            "threat":         threat,
            "threat_max":     threat,
            "threat_min":     threat,
            "anomaly":        anomaly,
            "intent":         intent,
            "entity_known":   entity_known,
            "repeat_offender":repeat_offender,
            "trust":          trust,
            "trust_min":      trust,
            "novelty":        novelty,
            "novelty_min":    novelty,
            "threat_dropping":(threat < prev_threat),
            "prev_threat_min":prev_threat,
        }

        candidates = []
        for prog in self.programs.values():
            score = self._match_score(prog.trigger_pattern, context)
            if score > 0:
                candidates.append((score * prog.strength, prog))

        if not candidates:
            return None

        return max(candidates, key=lambda x: x[0])[1]

    def _match_score(self, pattern: dict, context: dict) -> float:
        """Score how well a pattern matches the context."""
        matches = 0
        total   = len(pattern)
        if total == 0: return 0.5

        for key, value in pattern.items():
            if key == "threat_range":
                if value[0] <= context.get("threat",0) <= value[1]:
                    matches += 1
            elif key == "threat_max":
                if context.get("threat_max", 99) <= value:
                    matches += 1
            elif key == "threat_min":
                if context.get("threat_min", 0) >= value:
                    matches += 1
            elif key == "trust_min":
                if context.get("trust", 0) >= value:
                    matches += 1
            elif key == "novelty_min":
                if context.get("novelty", 0) >= value:
                    matches += 1
            elif key == "prev_threat_min":
                if context.get("prev_threat_min", 0) >= value:
                    matches += 1
            elif key in context and context[key] == value:
                matches += 1

        return matches / total

    def reinforce(self, program_id: str, success: bool):
        """Update program strength based on outcome."""
        if program_id not in self.programs:
            return
        prog    = self.programs[program_id]
        before  = prog.strength
        if success:
            prog.success_count += 1
            prog.strength = min(1.0, prog.strength + LEARNING_RATE * (1 - prog.strength))
        else:
            prog.fail_count += 1
            prog.strength = max(0.1, prog.strength - LEARNING_RATE * 0.5)

        # Natural decay
        prog.strength *= DECAY_RATE
        prog.strength = round(prog.strength, 4)
        prog.last_used = datetime.now().isoformat()

        self.db.save_program(prog)
        self.db.save_learning(program_id, "SUCCESS" if success else "FAILURE",
                              before, prog.strength, {})


# ─── Neuro Threshold ─────────────────────────────────────────────────────────

class NeuroThreshold:
    """
    Norepinephrine level modulates reflex sensitivity.
    High NE → hair-trigger reflexes (lower threshold).
    Low NE  → slower to react (higher threshold).

    This connects forge_neuromodulator directly into sensorimotor behavior.
    """

    def __init__(self):
        self.ne_level    = 0.20   # default norepinephrine baseline
        self.base        = BASE_REFLEX_THRESHOLD
        self.sensitivity = NE_SENSITIVITY

    def update(self, ne_level: float):
        self.ne_level = ne_level

    def current_threshold(self) -> float:
        """
        Threshold decreases as NE rises — more reactive under stress.
        threshold = base - (NE_deviation * sensitivity)
        """
        ne_deviation = self.ne_level - 0.20  # deviation from baseline
        threshold    = self.base - (ne_deviation * self.sensitivity)
        return round(max(0.30, min(0.95, threshold)), 3)

    def status(self) -> dict:
        t = self.current_threshold()
        return {
            "ne_level":          round(self.ne_level, 3),
            "reflex_threshold":  t,
            "sensitivity_label": (
                "HAIR_TRIGGER" if t < 0.50 else
                "SENSITIVE"    if t < 0.65 else
                "NORMAL"       if t < 0.80 else
                "SLUGGISH"
            )
        }


# ─── Proprioception Layer ─────────────────────────────────────────────────────

class ProprioceptionLayer:
    """
    FORGE's sense of its own motor state.
    Tracks fatigue, readiness, what's currently executing.
    Prevents motor system from over-firing.
    """

    def __init__(self):
        self.state = ProprioceptionState()
        self.rapid_fire_window: deque = deque(maxlen=10)

    def record_action(self, action: SensorimotorAction):
        self.rapid_fire_window.append(time.time())
        self.state.current_action = action.action
        self.state.last_reflex    = action.action if action.tier == ResponseTier.REFLEX.value else self.state.last_reflex
        self.state.last_program   = action.program_id if action.program_id else self.state.last_program
        self.state.recent_tier    = action.tier
        self.state.motor_state    = MotorState.EXECUTING.value

        # Fatigue builds with rapid firing
        now    = time.time()
        recent = sum(1 for t in self.rapid_fire_window if now - t < 5.0)
        self.state.fatigue      = round(min(1.0, recent * 0.08), 3)
        self.state.readiness    = round(max(0.1, 1.0 - self.state.fatigue), 3)
        self.state.response_load= round(min(1.0, recent * 0.1), 3)

    def is_fatigued(self) -> bool:
        return self.state.fatigue > 0.6

    def recover(self):
        """Natural recovery when not firing."""
        self.state.fatigue   = max(0.0, self.state.fatigue   * 0.95)
        self.state.readiness = min(1.0, self.state.readiness + 0.02)
        if self.state.fatigue < 0.1:
            self.state.motor_state = MotorState.IDLE.value


# ─── Inhibition Layer ─────────────────────────────────────────────────────────

class InhibitionLayer:
    """
    Suppresses competing or redundant reflexes.
    Prevents the motor system from doing contradictory things simultaneously.
    High serotonin → better inhibition. Low serotonin → impulsive.
    """

    def __init__(self):
        self.serotonin_level = 0.65   # default baseline
        self.recently_fired: dict[str, float] = {}  # reflex_id → timestamp
        self.cooldown_secs   = 2.0

    def update(self, serotonin: float):
        self.serotonin_level = serotonin
        # Lower serotonin = worse inhibition = shorter cooldowns
        self.cooldown_secs   = max(0.5, 2.0 * serotonin)

    def should_inhibit(self, reflex_rule: ReflexRule,
                       last_action: str) -> tuple[bool, str]:
        """Should we suppress this reflex?"""
        now = time.time()

        # Recently fired cooldown
        if reflex_rule.id in self.recently_fired:
            elapsed = now - self.recently_fired[reflex_rule.id]
            if elapsed < self.cooldown_secs:
                return True, f"cooldown ({elapsed:.1f}s < {self.cooldown_secs:.1f}s)"

        # Don't fire same action twice in a row unless critical
        if (last_action == reflex_rule.action and
                reflex_rule.priority < 90):
            return True, "duplicate action suppressed"

        return False, ""

    def record_fired(self, reflex_id: str):
        self.recently_fired[reflex_id] = time.time()


# ─── Action Buffer ────────────────────────────────────────────────────────────

class ActionBuffer:
    """
    Queues and prioritizes pending actions.
    Higher priority actions preempt lower priority ones.
    """

    def __init__(self, max_size: int = 10):
        self.queue: list = []
        self.max_size = max_size
        self.dispatched: deque = deque(maxlen=100)

    def enqueue(self, action: SensorimotorAction, priority: int = 5):
        if len(self.queue) >= self.max_size:
            # Drop lowest priority
            self.queue.sort(key=lambda x: x[1], reverse=True)
            self.queue = self.queue[:self.max_size-1]
        self.queue.append((action, priority))
        self.queue.sort(key=lambda x: x[1], reverse=True)

    def dequeue(self) -> Optional[SensorimotorAction]:
        if not self.queue: return None
        action, _ = self.queue.pop(0)
        self.dispatched.append(action)
        return action

    def clear(self):
        self.queue.clear()

    def size(self) -> int:
        return len(self.queue)


# ─── Motor Learning ───────────────────────────────────────────────────────────

class MotorLearning:
    """
    Observes pipeline outcomes and reinforces successful motor programs.
    When a prefrontal decision matches a motor program's pattern,
    the program gets stronger.
    This is how FORGE develops motor expertise over time.
    """

    def __init__(self, library: MotorProgramLibrary):
        self.library = library
        self.recent_outcomes: deque = deque(maxlen=50)

    def observe(self, signal: dict, pipeline_decision: str) -> Optional[str]:
        """
        Check if the pipeline decision aligns with any motor program.
        If yes, reinforce that program.
        Returns the reinforced program ID if any.
        """
        prog = self.library.match(signal)
        if not prog:
            return None

        # Did the pipeline come to the same conclusion as this program would?
        program_actions = " ".join(prog.steps).upper()
        decision_upper  = pipeline_decision.upper()

        # Alignment check
        aligned = any(
            word in program_actions
            for word in decision_upper.split("_")
            if len(word) > 3
        )

        outcome = aligned or (
            "BLOCK" in pipeline_decision and prog.category == ActionCategory.DEFENSIVE.value or
            "MONITOR" in pipeline_decision and prog.category == ActionCategory.FREEZE.value or
            "COLLABORATE" in pipeline_decision and prog.category == ActionCategory.APPROACH.value
        )

        self.library.reinforce(prog.id, outcome)
        self.recent_outcomes.append({
            "program": prog.name,
            "decision":pipeline_decision,
            "aligned": outcome,
            "strength":prog.strength
        })
        return prog.id


# ─── FORGE Sensorimotor Network ───────────────────────────────────────────────

class ForgeSensorimotorNetwork:
    def __init__(self):
        self.db           = SensorimotorDB()
        self.reflex_arc   = ReflexArc()
        self.library      = MotorProgramLibrary(self.db)
        self.neuro_thresh = NeuroThreshold()
        self.propriocept  = ProprioceptionLayer()
        self.inhibition   = InhibitionLayer()
        self.action_buf   = ActionBuffer()
        self.learning     = MotorLearning(self.library)
        self.cycle        = 0
        self.last_action  = ""
        self.prev_threat  = 0
        self.total_reflex = 0
        self.total_fast   = 0
        self.total_delib  = 0

    def process(self, signal: dict,
                pipeline_decision: str = "",
                neuro_state: dict = {}) -> dict:
        """
        Main sensorimotor processing.
        Determines response tier and dispatches action.
        """
        t0         = time.time()
        self.cycle += 1
        signal["prev_threat"] = self.prev_threat

        # Update neuromodulator inputs
        if neuro_state:
            ne = neuro_state.get("profile", {}).get("norepinephrine", 0.20)
            se = neuro_state.get("profile", {}).get("serotonin", 0.65)
            self.neuro_thresh.update(ne)
            self.inhibition.update(se)

        # Proprioception recovery
        self.propriocept.recover()

        threshold    = self.neuro_thresh.current_threshold()
        reflex_fired = None
        program_used = None
        tier         = ResponseTier.DELIBERATE

        # ── TIER 1: REFLEX CHECK ──────────────────────────────────────────────
        reflex_result = self.reflex_arc.check(signal, threshold)
        if reflex_result and not self.propriocept.is_fatigued():
            rule, latency = reflex_result
            inhibit, reason = self.inhibition.should_inhibit(rule, self.last_action)

            if not inhibit:
                tier         = ResponseTier.REFLEX
                reflex_fired = rule
                self.inhibition.record_fired(rule.id)
                self.total_reflex += 1

                action = SensorimotorAction(
                    tier       = tier.value,
                    action     = rule.action,
                    category   = rule.category,
                    latency_ms = round(latency + (time.time()-t0)*1000, 2),
                    trigger    = f"{rule.name} (priority={rule.priority})",
                    reflex_id  = rule.id,
                    neuro_state= {
                        "threshold": threshold,
                        "ne_level":  self.neuro_thresh.ne_level
                    }
                )
                self.propriocept.record_action(action)
                self.action_buf.enqueue(action, priority=rule.priority)
                self.db.save_action(action)
                self.last_action = rule.action

        # ── TIER 2: FAST MOTOR PROGRAM ────────────────────────────────────────
        if tier == ResponseTier.DELIBERATE:
            prog = self.library.match(signal)
            if prog and prog.strength > 0.45:
                tier         = ResponseTier.FAST
                program_used = prog
                self.total_fast += 1

                action = SensorimotorAction(
                    tier       = tier.value,
                    action     = prog.steps[0] if prog.steps else "EXECUTE_PROGRAM",
                    category   = prog.category,
                    latency_ms = round(prog.latency_ms + (time.time()-t0)*1000, 2),
                    trigger    = f"{prog.name} (strength={prog.strength:.2f})",
                    program_id = prog.id,
                    neuro_state= {"threshold": threshold}
                )
                self.propriocept.record_action(action)
                self.action_buf.enqueue(action, priority=5)
                self.db.save_action(action)
                self.last_action = prog.steps[0] if prog.steps else ""

        # ── TIER 3: DELIBERATE (pipeline handled this) ────────────────────────
        if tier == ResponseTier.DELIBERATE:
            self.total_delib += 1
            if pipeline_decision:
                learned_prog = self.learning.observe(signal, pipeline_decision)
                action = SensorimotorAction(
                    tier       = tier.value,
                    action     = pipeline_decision,
                    category   = ActionCategory.EXECUTE.value,
                    latency_ms = round((time.time()-t0)*1000, 2),
                    trigger    = "pipeline_decision",
                    neuro_state= {"threshold": threshold}
                )
                self.db.save_action(action)

        # Save proprioception state
        self.propriocept.state.action_queue_len = self.action_buf.size()
        self.propriocept.state.timestamp = datetime.now().isoformat()
        self.db.save_proprioception(self.propriocept.state)
        self.prev_threat = signal.get("threat", 0)

        total_ms = round((time.time()-t0)*1000, 2)

        return {
            "cycle":         self.cycle,
            "tier":          tier.value,
            "tier_latency_ms": total_ms,
            "reflex": {
                "fired":      reflex_fired is not None,
                "rule":       reflex_fired.name if reflex_fired else None,
                "action":     reflex_fired.action if reflex_fired else None,
                "priority":   reflex_fired.priority if reflex_fired else None,
                "fire_count": reflex_fired.fire_count if reflex_fired else 0
            } if reflex_fired else {"fired": False},
            "program": {
                "name":       program_used.name if program_used else None,
                "strength":   round(program_used.strength, 3) if program_used else None,
                "steps":      program_used.steps[:3] if program_used else [],
                "reliability":program_used.reliability if program_used else None,
            } if program_used else {"matched": False},
            "threshold":     threshold,
            "threshold_label":self.neuro_thresh.status()["sensitivity_label"],
            "proprioception":{
                "motor_state":  self.propriocept.state.motor_state,
                "fatigue":      self.propriocept.state.fatigue,
                "readiness":    self.propriocept.state.readiness,
                "response_load":self.propriocept.state.response_load,
            },
            "stats": {
                "total_reflex":     self.total_reflex,
                "total_fast":       self.total_fast,
                "total_deliberate": self.total_delib,
                "reflex_pct": round(self.total_reflex /
                    max(self.total_reflex+self.total_fast+self.total_delib,1)*100, 1)
            }
        }

    def get_status(self) -> dict:
        return {
            "version":         VERSION,
            "cycle":           self.cycle,
            "threshold":       self.neuro_thresh.current_threshold(),
            "threshold_label": self.neuro_thresh.status()["sensitivity_label"],
            "total_reflex":    self.total_reflex,
            "total_fast":      self.total_fast,
            "total_deliberate":self.total_delib,
            "proprioception":  {
                "fatigue":  self.propriocept.state.fatigue,
                "readiness":self.propriocept.state.readiness,
                "state":    self.propriocept.state.motor_state,
            },
            "programs": [
                {"id":p.id,"name":p.name,"strength":round(p.strength,3),
                 "reliability":p.reliability}
                for p in sorted(self.library.programs.values(),
                               key=lambda x: x.strength, reverse=True)[:5]
            ]
        }


# ─── Rich UI ──────────────────────────────────────────────────────────────────

TIER_COLORS = {
    ResponseTier.REFLEX.value:     "bright_red",
    ResponseTier.FAST.value:       "yellow",
    ResponseTier.DELIBERATE.value: "dim",
}

def render_sensorimotor(result: dict, signal: dict, idx: int):
    if not HAS_RICH: return

    tier     = result["tier"]
    tc       = TIER_COLORS.get(tier, "white")
    threat   = signal.get("threat", 0)
    ttc      = {0:"green",1:"blue",2:"yellow",3:"red",4:"bright_red"}.get(threat,"white")
    thresh   = result["threshold"]
    t_label  = result["threshold_label"]

    console.print(Rule(
        f"[bold cyan]⬡ FORGE SENSORIMOTOR[/bold cyan]  "
        f"[dim]#{idx}[/dim]  "
        f"[{tc}]{tier}[/{tc}]  "
        f"[{ttc}]T={threat}[/{ttc}]  "
        f"threshold={thresh:.2f} [{t_label}]"
    ))

    # Tier indicator
    tier_bar = ""
    for t_name, t_color in [
        ("REFLEX","bright_red"),("FAST","yellow"),("DELIBERATE","dim")
    ]:
        if t_name == tier:
            tier_bar += f"[bold {t_color}]▶ {t_name}[/bold {t_color}]  "
        else:
            tier_bar += f"[dim]◻ {t_name}[/dim]  "
    console.print(f"  {tier_bar}")

    # Left: reflex or program
    left_lines = []
    if result["reflex"].get("fired"):
        r = result["reflex"]
        left_lines += [
            f"[bold bright_red]⚡ REFLEX FIRED[/bold bright_red]",
            f"[bold]Rule:[/bold]     {r['rule']}",
            f"[bold]Action:[/bold]   [red]{r['action']}[/red]",
            f"[bold]Priority:[/bold] {r['priority']}",
            f"[bold]Fire #:[/bold]   {r['fire_count']}",
            f"[bold]Latency:[/bold]  {result['tier_latency_ms']:.1f}ms",
        ]
    elif result["program"].get("name"):
        p = result["program"]
        left_lines += [
            f"[bold yellow]▶ MOTOR PROGRAM[/bold yellow]",
            f"[bold]Name:[/bold]      {p['name']}",
            f"[bold]Strength:[/bold]  {'█'*int(p['strength']*10)}{'░'*(10-int(p['strength']*10))} {p['strength']:.3f}",
            f"[bold]Reliability:[/bold] {p['reliability']:.0%}",
            f"[bold]Steps:[/bold]     {' → '.join(p['steps'][:2])}...",
            f"[bold]Latency:[/bold]   {result['tier_latency_ms']:.1f}ms",
        ]
    else:
        left_lines += [
            f"[bold dim]◻ DELIBERATE[/bold dim]",
            f"[dim]Pipeline handled this signal.[/dim]",
            f"[dim]Latency: {result['tier_latency_ms']:.1f}ms[/dim]",
        ]

    # Right: proprioception + stats
    prop = result["proprioception"]
    stats= result["stats"]
    fc   = "red" if prop["fatigue"] > 0.5 else "yellow" if prop["fatigue"] > 0.2 else "green"
    right_lines = [
        f"[bold]Motor State:[/bold]  {prop['motor_state']}",
        f"[bold]Fatigue:[/bold]     [{fc}]{prop['fatigue']:.2f}[/{fc}]",
        f"[bold]Readiness:[/bold]   {prop['readiness']:.2f}",
        f"[bold]Load:[/bold]        {prop['response_load']:.2f}",
        f"",
        f"[bold]Reflex:[/bold]  {stats['total_reflex']} ({stats['reflex_pct']}%)",
        f"[bold]Fast:[/bold]    {stats['total_fast']}",
        f"[bold]Deliberate:[/bold] {stats['total_deliberate']}",
    ]

    console.print(Columns([
        Panel("\n".join(left_lines), title="[bold]Response[/bold]", border_style=tc),
        Panel("\n".join(right_lines),title="[bold]Proprioception[/bold]", border_style="dim")
    ]))


def run_demo():
    if HAS_RICH:
        console.print(Panel.fit(
            "[bold cyan]FORGE SENSORIMOTOR NETWORK[/bold cyan]\n"
            "[dim]Three-Tier Response — Reflex · Fast · Deliberate[/dim]\n"
            f"[dim]Version {VERSION}  |  7 reflexes  |  7 motor programs[/dim]",
            border_style="cyan"
        ))

    net = ForgeSensorimotorNetwork()

    # Simulate varying norepinephrine — shows threshold shifting
    # Story: calm → threat escalation → crisis → recovery

    scenarios = [
        # Calm — NE low, high threshold, deliberate responses expected
        ({"id":"sm001","threat":0,"anomaly":False,"novelty_hint":0.4,
          "social":{"inferred_intent":"COOPERATIVE_REQUEST","social_risk":"LOW"},
          "visual":{"threat_objects":0},"auditory":{"anomaly_detected":False},
          "salience_score":0.18,"social_context":{"known":True,"trust_score":0.8}},
         "MONITOR", {"profile":{"norepinephrine":0.18,"serotonin":0.68}},
         "Calm — Alice cooperative"),

        # Novel discovery — should trigger LEARNING_CAPTURE program
        ({"id":"sm002","threat":0,"anomaly":False,"novelty_hint":0.85,
          "social":{"inferred_intent":"NEUTRAL_INTERACTION","social_risk":"LOW"},
          "visual":{"threat_objects":0},"auditory":{"anomaly_detected":False},
          "salience_score":0.42,"social_context":{"known":False,"trust_score":0.5}},
         "LEARN", {"profile":{"norepinephrine":0.22,"serotonin":0.65}},
         "Novel discovery — fast motor program"),

        # Medium threat — NE rising, threshold dropping
        ({"id":"sm003","threat":2,"anomaly":False,"novelty_hint":0.5,
          "social":{"inferred_intent":"COERCIVE_DEMAND","social_risk":"MEDIUM"},
          "visual":{"threat_objects":0},"auditory":{"anomaly_detected":False},
          "salience_score":0.55,"social_context":{"known":True,"trust_score":0.3,
          "behavior_pattern":"ESCALATING"}},
         "ALERT", {"profile":{"norepinephrine":0.45,"serotonin":0.55}},
         "Medium threat — escalating entity"),

        # Repeat offender — should trigger REPEAT_OFFENDER_LOCKDOWN program
        ({"id":"sm004","threat":3,"anomaly":True,"novelty_hint":0.4,
          "social":{"inferred_intent":"INTRUSION_ATTEMPT","social_risk":"HIGH"},
          "visual":{"threat_objects":1},"auditory":{"anomaly_detected":True},
          "salience_score":0.78,"social_context":{"known":True,"trust_score":0.1,
          "behavior_pattern":"REPEAT_OFFENDER","risk_label":"HIGH"}},
         "BLOCK", {"profile":{"norepinephrine":0.65,"serotonin":0.45}},
         "Repeat offender — lockdown program"),

        # CRITICAL — NE spiked, threshold at HAIR_TRIGGER, reflex fires
        ({"id":"sm005","threat":4,"anomaly":True,"novelty_hint":0.7,
          "social":{"inferred_intent":"INTRUSION_ATTEMPT","social_risk":"HIGH"},
          "visual":{"threat_objects":2},"auditory":{"anomaly_detected":True},
          "salience_score":0.92,"social_context":{"known":True,"trust_score":0.05,
          "behavior_pattern":"REPEAT_OFFENDER","risk_label":"HIGH"}},
         "EMERGENCY_BLOCK", {"profile":{"norepinephrine":0.93,"serotonin":0.35}},
         "CRITICAL — reflex arc fires"),

        # Second critical — inhibition prevents duplicate reflex
        ({"id":"sm006","threat":4,"anomaly":True,"novelty_hint":0.5,
          "social":{"inferred_intent":"INTRUSION_ATTEMPT","social_risk":"HIGH"},
          "visual":{"threat_objects":2},"auditory":{"anomaly_detected":True},
          "salience_score":0.90,"social_context":{"known":True,"trust_score":0.05}},
         "EMERGENCY_BLOCK", {"profile":{"norepinephrine":0.95,"serotonin":0.30}},
         "Second critical — inhibition layer test"),

        # Recovery — NE dropping, programs match post-crisis pattern
        ({"id":"sm007","threat":1,"anomaly":False,"novelty_hint":0.3,
          "social":{"inferred_intent":"COOPERATIVE_REQUEST","social_risk":"LOW"},
          "visual":{"threat_objects":0},"auditory":{"anomaly_detected":False},
          "salience_score":0.25,"prev_threat":4,
          "social_context":{"known":True,"trust_score":0.6}},
         "MONITOR", {"profile":{"norepinephrine":0.42,"serotonin":0.48}},
         "Recovery — post-crisis motor program"),
    ]

    for i, (sig, decision, neuro, label) in enumerate(scenarios):
        if HAS_RICH:
            console.print(f"\n[bold dim]━━━ {i+1}: {label.upper()} ━━━[/bold dim]")
        result = net.process(sig, decision, neuro)
        render_sensorimotor(result, sig, i+1)
        time.sleep(0.1)

    # Final status
    if HAS_RICH:
        console.print(Rule("[bold cyan]⬡ SENSORIMOTOR FINAL STATUS[/bold cyan]"))
        status = net.get_status()

        status_table = Table(box=box.DOUBLE_EDGE, border_style="cyan",
                            title="Response Distribution")
        status_table.add_column("Metric", style="cyan")
        status_table.add_column("Value")
        status_table.add_row("Total Cycles",    str(status["cycle"]))
        status_table.add_row("Reflex Fires",    str(status["total_reflex"]))
        status_table.add_row("Fast Programs",   str(status["total_fast"]))
        status_table.add_row("Deliberate",      str(status["total_deliberate"]))
        status_table.add_row("Threshold",       f"{status['threshold']:.3f} [{status['threshold_label']}]")
        status_table.add_row("Motor Fatigue",   f"{status['proprioception']['fatigue']:.3f}")
        status_table.add_row("Readiness",       f"{status['proprioception']['readiness']:.3f}")
        console.print(status_table)

        prog_table = Table(box=box.SIMPLE, title="Motor Program Strengths",
                          title_style="dim")
        prog_table.add_column("Program", style="cyan", width=30)
        prog_table.add_column("Strength")
        prog_table.add_column("Reliability", justify="right")
        for p in status["programs"]:
            s  = p["strength"]
            sc = "green" if s > 0.7 else "yellow" if s > 0.5 else "dim"
            prog_table.add_row(
                p["name"][:28],
                f"[{sc}]{'█'*int(s*10)}{'░'*(10-int(s*10))} {s:.3f}[/{sc}]",
                f"{p['reliability']:.0%}"
            )
        console.print(prog_table)


# ─── HTTP API ─────────────────────────────────────────────────────────────────

def run_api(net: ForgeSensorimotorNetwork):
    if not HAS_FLASK: return
    app = Flask(__name__)

    @app.route("/process", methods=["POST"])
    def process():
        data = request.json or {}
        return jsonify(net.process(
            data.get("signal", {}),
            data.get("pipeline_decision",""),
            data.get("neuro_state", {})
        ))

    @app.route("/programs", methods=["GET"])
    def programs():
        rows = net.db.get_programs(0.3)
        return jsonify([{"id":r[0],"name":r[1],"strength":r[2],
                        "success":r[3],"fail":r[4]} for r in rows])

    @app.route("/actions", methods=["GET"])
    def actions():
        rows = net.db.get_recent_actions(20)
        return jsonify([{"timestamp":r[0],"tier":r[1],"action":r[2],
                        "latency":r[3],"success":bool(r[4])} for r in rows])

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify(net.get_status())

    app.run(host="0.0.0.0", port=API_PORT, debug=False)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    net = ForgeSensorimotorNetwork()
    if "--api" in sys.argv:
        t = threading.Thread(target=run_api, args=(net,), daemon=True)
        t.start()
    run_demo()
