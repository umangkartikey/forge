"""
FORGE Basal Ganglia — forge_basal_ganglia.py
=============================================
AI analog of the brain's basal ganglia.

The basal ganglia is not an initiator — it's a SELECTOR and GATER.
Everything is suppressed by default. The basal ganglia releases
inhibition on exactly one action at a time, letting it through.

Three core functions:

  1. ACTION SELECTION via Go/NoGo competition
     All candidate actions compete. The basal ganglia evaluates
     reward history for each, releases the brake on the winner,
     and strengthens suppression on all losers.

  2. HABIT FORMATION
     Repeated successful sequences get encoded as habits.
     Habits bypass deliberation entirely:
       First encounter:  deliberate (260ms)
       10 repetitions:   fast program (50ms)
       100 repetitions:  pure habit (5ms)

  3. REWARD GATING via dopamine
     Dopamine prediction error drives learning:
       Better than expected → strengthen winning pathway (+)
       Worse than expected  → weaken winning pathway (-)
       As expected          → no change (0)
     This is the biological basis of trial-and-error learning.

Key insight: The basal ganglia learns WHAT WORKS, not what is true.
It is pure pragmatic intelligence — the wisdom layer of FORGE.

Architecture:
  StriatalInput        → receives all candidate actions + context
  DirectPathway        → Go signal — disinhibits selected action
  IndirectPathway      → NoGo signal — suppresses competitors
  SubthalamicNucleus   → emergency brake — stops everything when uncertain
  DopaminePredictor    → predicts expected reward before acting
  RewardGate           → updates pathways based on prediction error
  HabitLibrary         → stores automatic behavior sequences
  HabitStrengthener    → elevates successful sequences to habits
  ActionCompetition    → resolves conflicts between competing actions
"""

import json
import time
import uuid
import sqlite3
import threading
import math
import random
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

DB_PATH  = "forge_basal_ganglia.db"
API_PORT = 7791
VERSION  = "1.0.0"

# Habit thresholds
HABIT_THRESHOLD      = 0.75   # pathway strength → habit
HABIT_STRONG         = 0.90   # fully automatic habit
NOVICE_THRESHOLD     = 0.30   # below this → very uncertain

# Learning rates
DOPAMINE_LEARNING    = 0.15   # how fast dopamine updates pathways
HABIT_DECAY          = 0.998  # habits fade very slowly without use
PREDICTION_MOMENTUM  = 0.85   # reward prediction smoothing

# Competition
MIN_COMPETITION_GAP  = 0.08   # winner must exceed 2nd by this
STN_UNCERTAINTY_THRESHOLD = 0.12  # gap below this → STN fires emergency brake

console = Console() if HAS_RICH else None

# ─── Enums ────────────────────────────────────────────────────────────────────

class PathwayState(Enum):
    INHIBITED  = "INHIBITED"   # default — action suppressed
    DISINHIBITED="DISINHIBITED"# Go signal — action released
    SUPPRESSED = "SUPPRESSED"  # NoGo — actively blocked

class HabitStage(Enum):
    NOVEL      = "NOVEL"       # never done before
    LEARNING   = "LEARNING"    # being acquired (deliberate)
    DEVELOPING = "DEVELOPING"  # getting faster (program)
    HABITUAL   = "HABITUAL"    # automatic (fast)
    EXPERT     = "EXPERT"      # fully ingrained (instant)

class DopamineSignal(Enum):
    BURST      = "BURST"       # better than expected (+)
    PAUSE      = "PAUSE"       # worse than expected (-)
    TONIC      = "TONIC"       # as expected (0)

class SelectionOutcome(Enum):
    SELECTED   = "SELECTED"    # won competition, action taken
    SUPPRESSED = "SUPPRESSED"  # lost competition
    BRAKE      = "BRAKE"       # STN stopped everything
    HABIT      = "HABIT"       # bypassed competition entirely

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class StriatalPathway:
    """One action's pathway through the basal ganglia."""
    action:        str   = ""
    context_key:   str   = ""
    strength:      float = 0.5    # 0-1 how strong this pathway is
    go_weight:     float = 0.5    # direct pathway weight
    nogo_weight:   float = 0.5    # indirect pathway weight
    net_drive:     float = 0.0    # go - nogo
    use_count:     int   = 0
    success_count: int   = 0
    fail_count:    int   = 0
    last_used:     str   = field(default_factory=lambda: datetime.now().isoformat())
    habit_stage:   str   = HabitStage.NOVEL.value
    latency_ms:    float = 260.0  # current execution latency

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return round(self.success_count / total, 3) if total > 0 else 0.5

    @property
    def is_habit(self) -> bool:
        return self.strength >= HABIT_THRESHOLD

    @property
    def is_expert(self) -> bool:
        return self.strength >= HABIT_STRONG

@dataclass
class Habit:
    """A fully formed automatic behavior."""
    id:            str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:          str   = ""
    trigger:       dict  = field(default_factory=dict)
    action:        str   = ""
    sequence:      list  = field(default_factory=list)
    strength:      float = 0.75
    latency_ms:    float = 15.0
    stage:         str   = HabitStage.HABITUAL.value
    fires:         int   = 0
    created:       str   = field(default_factory=lambda: datetime.now().isoformat())
    last_fired:    str   = field(default_factory=lambda: datetime.now().isoformat())
    context_hash:  str   = ""

@dataclass
class DopaminePrediction:
    """Reward prediction for an action in a context."""
    action:        str   = ""
    context:       str   = ""
    predicted:     float = 0.5    # expected reward 0-1
    actual:        float = 0.5    # received reward
    error:         float = 0.0    # actual - predicted (RPE)
    signal:        str   = DopamineSignal.TONIC.value
    updated:       str   = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class CompetitionResult:
    """Result of an action selection competition."""
    id:            str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:     str   = field(default_factory=lambda: datetime.now().isoformat())
    winner:        str   = ""
    winner_strength:float= 0.0
    runner_up:     str   = ""
    runner_up_strength:float=0.0
    gap:           float = 0.0
    outcome:       str   = SelectionOutcome.SELECTED.value
    was_habit:     bool  = False
    stn_brake:     bool  = False
    latency_ms:    float = 0.0
    context_hash:  str   = ""
    dopamine_signal:str  = DopamineSignal.TONIC.value
    candidates:    int   = 0

# ─── Database ─────────────────────────────────────────────────────────────────

class BasalGangliaDB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init()

    def _init(self):
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS pathways (
                    action TEXT, context_key TEXT,
                    strength REAL, go_weight REAL, nogo_weight REAL,
                    net_drive REAL, use_count INTEGER,
                    success_count INTEGER, fail_count INTEGER,
                    last_used TEXT, habit_stage TEXT, latency_ms REAL,
                    PRIMARY KEY (action, context_key)
                );
                CREATE TABLE IF NOT EXISTS habits (
                    id TEXT PRIMARY KEY, name TEXT, trigger TEXT,
                    action TEXT, sequence TEXT, strength REAL,
                    latency_ms REAL, stage TEXT, fires INTEGER,
                    created TEXT, last_fired TEXT, context_hash TEXT
                );
                CREATE TABLE IF NOT EXISTS dopamine_predictions (
                    action TEXT, context TEXT, predicted REAL,
                    actual REAL, error REAL, signal TEXT, updated TEXT,
                    PRIMARY KEY (action, context)
                );
                CREATE TABLE IF NOT EXISTS competition_results (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    winner TEXT, winner_strength REAL,
                    runner_up TEXT, runner_up_strength REAL,
                    gap REAL, outcome TEXT, was_habit INTEGER,
                    stn_brake INTEGER, latency_ms REAL,
                    context_hash TEXT, dopamine_signal TEXT,
                    candidates INTEGER
                );
                CREATE TABLE IF NOT EXISTS learning_events (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    action TEXT, context TEXT, rpe REAL,
                    strength_before REAL, strength_after REAL,
                    signal TEXT
                );
            """)
            self.conn.commit()

    def save_pathway(self, p: StriatalPathway):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO pathways VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (p.action, p.context_key, p.strength,
                  p.go_weight, p.nogo_weight, p.net_drive,
                  p.use_count, p.success_count, p.fail_count,
                  p.last_used, p.habit_stage, p.latency_ms))
            self.conn.commit()

    def save_habit(self, h: Habit):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO habits VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (h.id, h.name, json.dumps(h.trigger), h.action,
                  json.dumps(h.sequence), h.strength, h.latency_ms,
                  h.stage, h.fires, h.created, h.last_fired, h.context_hash))
            self.conn.commit()

    def save_prediction(self, p: DopaminePrediction):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO dopamine_predictions VALUES
                (?,?,?,?,?,?,?)
            """, (p.action, p.context, p.predicted, p.actual,
                  p.error, p.signal, p.updated))
            self.conn.commit()

    def save_result(self, r: CompetitionResult):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO competition_results VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (r.id, r.timestamp, r.winner, r.winner_strength,
                  r.runner_up, r.runner_up_strength, r.gap,
                  r.outcome, int(r.was_habit), int(r.stn_brake),
                  r.latency_ms, r.context_hash, r.dopamine_signal,
                  r.candidates))
            self.conn.commit()

    def log_learning(self, action: str, context: str, rpe: float,
                     before: float, after: float, signal: str):
        with self.lock:
            self.conn.execute("""
                INSERT INTO learning_events VALUES (?,?,?,?,?,?,?,?)
            """, (str(uuid.uuid4())[:8], datetime.now().isoformat(),
                  action, context, rpe, before, after, signal))
            self.conn.commit()

    def get_pathways(self, min_strength=0.0):
        with self.lock:
            return self.conn.execute("""
                SELECT action, context_key, strength, use_count,
                       success_count, fail_count, habit_stage, latency_ms
                FROM pathways WHERE strength >= ?
                ORDER BY strength DESC
            """, (min_strength,)).fetchall()

    def get_habits(self):
        with self.lock:
            return self.conn.execute("""
                SELECT id, name, action, strength, fires,
                       stage, latency_ms
                FROM habits ORDER BY strength DESC
            """).fetchall()

    def get_recent_results(self, limit=20):
        with self.lock:
            return self.conn.execute("""
                SELECT timestamp, winner, winner_strength, gap,
                       outcome, was_habit, stn_brake, latency_ms,
                       dopamine_signal
                FROM competition_results
                ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()


# ─── Context Hasher ───────────────────────────────────────────────────────────

class ContextHasher:
    """
    Creates a compact context key from a signal.
    Similar contexts map to the same pathways —
    this is how habits generalize across situations.
    """

    def hash(self, signal: dict) -> str:
        import hashlib
        threat   = signal.get("threat", 0)
        intent   = ""
        social   = signal.get("social",{}) or {}
        if isinstance(social, dict):
            intent = social.get("inferred_intent","")[:20]
        scene    = ""
        visual   = signal.get("visual",{}) or {}
        if isinstance(visual, dict):
            scene = visual.get("scene_type","")[:15]
        anomaly  = int(signal.get("anomaly", False))

        # Coarsen threat to buckets for generalization
        threat_bucket = min(4, threat)
        raw   = f"T{threat_bucket}:{intent[:10]}:{scene[:8]}:{anomaly}"
        return hashlib.md5(raw.encode()).hexdigest()[:10]

    def describe(self, signal: dict) -> str:
        threat = signal.get("threat",0)
        social = signal.get("social",{}) or {}
        intent = social.get("inferred_intent","UNKNOWN") if isinstance(social,dict) else "UNKNOWN"
        return f"T={threat}/{intent[:15]}"


# ─── Striatal Input Layer ─────────────────────────────────────────────────────

class StriatalInput:
    """
    Receives candidate actions and enriches them with context.
    This is the input layer of the basal ganglia.
    Evaluates each candidate against stored pathway strengths.
    """

    def __init__(self, db: BasalGangliaDB, hasher: ContextHasher):
        self.db     = db
        self.hasher = hasher
        self.pathways: dict[str, StriatalPathway] = {}

    def evaluate(self, candidates: list[str],
                 signal: dict) -> list[StriatalPathway]:
        """
        For each candidate action, find or create its pathway
        and compute its current drive level.
        """
        ctx_key  = self.hasher.hash(signal)
        threat   = signal.get("threat", 0)
        pathways = []

        for action in candidates:
            key = f"{action}::{ctx_key}"
            if key not in self.pathways:
                # Create new pathway with prior based on action type
                prior = self._action_prior(action, threat)
                p     = StriatalPathway(
                    action       = action,
                    context_key  = ctx_key,
                    strength     = prior,
                    go_weight    = prior,
                    nogo_weight  = 1.0 - prior,
                    net_drive    = prior * 2 - 1.0,
                    habit_stage  = HabitStage.NOVEL.value
                )
                self.pathways[key] = p

            p = self.pathways[key]
            # Compute net drive: Go weight - NoGo weight
            p.net_drive = round(p.go_weight - p.nogo_weight, 4)
            pathways.append(p)

        return pathways

    def _action_prior(self, action: str, threat: int) -> float:
        """Initial strength prior based on action type and threat."""
        defensive = ["BLOCK","ESCALATE","ALERT","SUPPRESS","EMERGENCY_BLOCK"]
        cooperative= ["COLLABORATE","MONITOR","LEARN","STANDBY"]

        if action in defensive and threat >= 2:   return 0.65
        if action in defensive and threat == 0:   return 0.30
        if action in cooperative and threat == 0: return 0.60
        if action in cooperative and threat >= 2: return 0.35
        return 0.45


# ─── Direct Pathway (Go) ─────────────────────────────────────────────────────

class DirectPathway:
    """
    The Go pathway.
    Selects the winning action and releases its inhibition.
    Strengthened by dopamine bursts (reward).
    """

    def select(self, pathways: list[StriatalPathway],
               dopamine_level: float) -> Optional[StriatalPathway]:
        """
        Select the pathway with highest net drive.
        Dopamine amplifies all Go signals — high dopamine = more decisive.
        """
        if not pathways: return None

        # Dopamine modulates decisiveness
        da_boost = (dopamine_level - 0.45) * 0.3

        scored = []
        for p in pathways:
            # Direct pathway: Go weight boosted by dopamine
            go_score = p.go_weight * (1.0 + da_boost) - p.nogo_weight
            scored.append((go_score, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else None

    def strengthen(self, pathway: StriatalPathway, rpe: float):
        """
        Strengthen Go pathway when RPE is positive.
        Weaken when RPE is negative.
        """
        pathway.go_weight = round(
            max(0.05, min(0.98,
                pathway.go_weight + rpe * DOPAMINE_LEARNING
            )), 4
        )


# ─── Indirect Pathway (NoGo) ─────────────────────────────────────────────────

class IndirectPathway:
    """
    The NoGo pathway.
    Actively suppresses losing actions.
    Strengthened when actions fail or are punished.
    """

    def suppress(self, losers: list[StriatalPathway],
                 dopamine_level: float):
        """
        Increase NoGo weight for all losing pathways.
        Low dopamine amplifies NoGo suppression.
        """
        da_suppression = max(0.5, 1.0 - dopamine_level)

        for p in losers:
            p.nogo_weight = round(
                min(0.95,
                    p.nogo_weight + 0.02 * da_suppression
                ), 4
            )
            p.net_drive = round(p.go_weight - p.nogo_weight, 4)

    def strengthen(self, pathway: StriatalPathway, rpe: float):
        """Strengthen NoGo when RPE is negative (action was bad)."""
        if rpe < 0:
            pathway.nogo_weight = round(
                min(0.95,
                    pathway.nogo_weight + abs(rpe) * DOPAMINE_LEARNING
                ), 4
            )


# ─── Subthalamic Nucleus ─────────────────────────────────────────────────────

class SubthalamicNucleus:
    """
    The emergency brake of the basal ganglia.

    When the competition is too close to call — gap between
    winner and runner-up is below threshold — the STN fires
    a broad suppression signal that STOPS all actions.

    This is the biological basis of the pause before a difficult decision.
    "Hold on — I'm not sure enough to act yet."

    Also fires when:
    - Novel context with no pathway history
    - Contradictory signals (high threat + friendly intent)
    - Dopamine is very low (depleted, unreliable)
    """

    def __init__(self):
        self.brake_count = 0
        self.last_brake  = None

    def check(self, winner: StriatalPathway,
              runner_up: Optional[StriatalPathway],
              dopamine: float, signal: dict) -> tuple[bool, str]:
        """
        Returns (should_brake, reason).
        """
        # Very close competition — uncertain
        if runner_up and winner:
            gap = abs(winner.net_drive - runner_up.net_drive)
            if gap < STN_UNCERTAINTY_THRESHOLD and winner.use_count < 3:
                self.brake_count += 1
                return True, f"uncertain_competition (gap={gap:.3f})"

        # Novel context — never done this before
        if winner and winner.use_count == 0 and signal.get("threat", 0) >= 3:
            self.brake_count += 1
            return True, "novel_high_threat_context"

        # Depleted dopamine — can't reliably predict
        if dopamine < 0.15:
            self.brake_count += 1
            return True, f"dopamine_depleted ({dopamine:.2f})"

        # Contradictory signals
        threat = signal.get("threat", 0)
        social = signal.get("social", {}) or {}
        intent = social.get("inferred_intent","") if isinstance(social,dict) else ""
        if threat >= 3 and "COOPERATIVE" in intent:
            self.brake_count += 1
            return True, "contradictory_threat_cooperative"

        return False, ""


# ─── Dopamine Predictor ───────────────────────────────────────────────────────

class DopaminePredictor:
    """
    Predicts expected reward before acting.
    Computes reward prediction error (RPE) after outcome.

    RPE = actual_reward - predicted_reward

    This is the core of dopaminergic learning:
      RPE > 0 → better than expected → burst → strengthen pathway
      RPE < 0 → worse than expected  → pause → weaken pathway
      RPE = 0 → as expected          → tonic  → no change

    The predictor gets better over time —
    it learns to anticipate outcomes accurately.
    """

    def __init__(self, db: BasalGangliaDB):
        self.db          = db
        self.predictions: dict[str, DopaminePrediction] = {}
        self.prediction_accuracy: deque = deque(maxlen=50)

    def predict(self, action: str, context: str,
                dopamine_level: float) -> float:
        """Predict expected reward for this action in this context."""
        key = f"{action}::{context}"
        if key in self.predictions:
            # Update with current dopamine level
            pred = self.predictions[key]
            # High dopamine → slightly more optimistic predictions
            adjusted = pred.predicted + (dopamine_level - 0.45) * 0.1
            return round(max(0.0, min(1.0, adjusted)), 3)

        # New context — prior based on action type
        prior = self._prior(action)
        pred  = DopaminePrediction(
            action=action, context=context,
            predicted=prior, actual=prior
        )
        self.predictions[key] = pred
        return prior

    def update(self, action: str, context: str,
               actual_reward: float) -> tuple[float, DopamineSignal]:
        """
        Update prediction based on actual outcome.
        Returns (rpe, dopamine_signal).
        """
        key = f"{action}::{context}"
        if key not in self.predictions:
            self.predictions[key] = DopaminePrediction(
                action=action, context=context, predicted=0.5
            )

        pred = self.predictions[key]
        rpe  = round(actual_reward - pred.predicted, 4)

        # Determine dopamine signal
        if rpe > 0.05:      signal = DopamineSignal.BURST
        elif rpe < -0.05:   signal = DopamineSignal.PAUSE
        else:               signal = DopamineSignal.TONIC

        # Update prediction (running average)
        pred.predicted = round(
            pred.predicted * PREDICTION_MOMENTUM +
            actual_reward * (1 - PREDICTION_MOMENTUM), 4
        )
        pred.actual   = actual_reward
        pred.error    = rpe
        pred.signal   = signal.value
        pred.updated  = datetime.now().isoformat()

        self.db.save_prediction(pred)
        self.prediction_accuracy.append(abs(rpe))

        return rpe, signal

    def accuracy(self) -> float:
        """How good is our prediction? Lower RPE = better."""
        if not self.prediction_accuracy: return 0.5
        return round(1.0 - sum(self.prediction_accuracy)/len(self.prediction_accuracy), 3)

    def _prior(self, action: str) -> float:
        priors = {
            "BLOCK":0.7,"ESCALATE":0.6,"ALERT":0.65,
            "MONITOR":0.55,"COLLABORATE":0.6,"LEARN":0.58,
            "STANDBY":0.45,"EMERGENCY_BLOCK":0.75,"INVESTIGATE":0.6,
        }
        return priors.get(action, 0.5)


# ─── Habit Library ────────────────────────────────────────────────────────────

class HabitLibrary:
    """
    Stores fully formed automatic behaviors.
    Habits bypass the competition entirely — they fire directly
    when their trigger pattern is recognized.

    A pathway graduates to habit when:
    - strength >= HABIT_THRESHOLD
    - use_count >= 10
    - success_rate >= 0.65
    """

    def __init__(self, db: BasalGangliaDB):
        self.db     = db
        self.habits: dict[str, Habit] = {}
        self._seed_innate_habits()

    def _seed_innate_habits(self):
        """
        Innate habits — so deeply wired they start at full strength.
        These are FORGE's instincts from day 1.
        """
        innate = [
            Habit(
                id="H_INNATE_001",
                name="THREAT4_EMERGENCY_RESPONSE",
                trigger={"threat": 4},
                action="EMERGENCY_BLOCK",
                sequence=["detect_critical_threat","activate_all_defenses",
                          "emergency_block","broadcast_alert","log_crisis"],
                strength=0.98, latency_ms=5.0,
                stage=HabitStage.EXPERT.value, fires=0,
                context_hash="innate"
            ),
            Habit(
                id="H_INNATE_002",
                name="TRUSTED_COOPERATIVE_OPEN",
                trigger={"trust_min":0.7,"threat_max":0},
                action="OPEN_COOPERATIVE_CHANNEL",
                sequence=["verify_trust","open_channel","engage_cooperatively"],
                strength=0.82, latency_ms=12.0,
                stage=HabitStage.EXPERT.value, fires=0,
                context_hash="innate"
            ),
            Habit(
                id="H_INNATE_003",
                name="ANOMALY_IMMEDIATE_ORIENT",
                trigger={"anomaly":True,"threat_max":2},
                action="ORIENT_AND_ASSESS",
                sequence=["freeze","orient_to_anomaly","assess","report"],
                strength=0.80, latency_ms=8.0,
                stage=HabitStage.HABITUAL.value, fires=0,
                context_hash="innate"
            ),
        ]
        for h in innate:
            self.habits[h.id] = h
            self.db.save_habit(h)

    def check_trigger(self, signal: dict) -> Optional[Habit]:
        """Check if any habit fires for this signal."""
        threat = signal.get("threat",0)
        anomaly= signal.get("anomaly",False)
        social_ctx = signal.get("social_context",{}) or {}
        trust  = social_ctx.get("trust_score",0.5)

        for habit in sorted(self.habits.values(),
                           key=lambda h: h.strength, reverse=True):
            if self._matches(habit.trigger, {
                "threat":    threat,
                "anomaly":   anomaly,
                "trust":     trust,
            }):
                return habit
        return None

    def _matches(self, trigger: dict, context: dict) -> bool:
        for key, value in trigger.items():
            if key == "threat" and context.get("threat",0) != value:
                return False
            if key == "threat_max" and context.get("threat",0) > value:
                return False
            if key == "threat_min" and context.get("threat",0) < value:
                return False
            if key == "trust_min" and context.get("trust",0.5) < value:
                return False
            if key == "anomaly" and context.get("anomaly",False) != value:
                return False
        return True

    def elevate(self, pathway: StriatalPathway,
                signal: dict, hasher: ContextHasher):
        """Promote a strong pathway to habit."""
        ctx_hash = hasher.hash(signal)
        habit_id = f"H_{pathway.action}_{ctx_hash[:6]}"

        if habit_id in self.habits:
            # Strengthen existing habit
            h = self.habits[habit_id]
            h.strength = min(1.0, h.strength + 0.02)
            if h.strength >= HABIT_STRONG:
                h.stage     = HabitStage.EXPERT.value
                h.latency_ms= max(5.0, h.latency_ms * 0.9)
        else:
            # Create new habit
            latency = max(5.0, 260.0 * (1.0 - pathway.strength))
            h = Habit(
                id          = habit_id,
                name        = f"{pathway.action}_in_{ctx_hash[:6]}",
                trigger     = {"context_hash": ctx_hash},
                action      = pathway.action,
                sequence    = [pathway.action, "log_habit_fire"],
                strength    = pathway.strength,
                latency_ms  = latency,
                stage       = (HabitStage.EXPERT.value
                               if pathway.strength >= HABIT_STRONG
                               else HabitStage.HABITUAL.value),
                context_hash= ctx_hash
            )
            self.habits[habit_id] = h

        self.db.save_habit(self.habits[habit_id])
        return self.habits[habit_id]

    def fire(self, habit: Habit) -> dict:
        habit.fires    += 1
        habit.last_fired= datetime.now().isoformat()
        habit.strength  = min(1.0, habit.strength + 0.005)  # use strengthens
        self.db.save_habit(habit)
        return {
            "habit_id":   habit.id,
            "name":       habit.name,
            "action":     habit.action,
            "sequence":   habit.sequence,
            "latency_ms": habit.latency_ms,
            "strength":   habit.strength,
            "fires":      habit.fires,
            "stage":      habit.stage
        }


# ─── Habit Strengthener ───────────────────────────────────────────────────────

class HabitStrengthener:
    """
    Monitors pathway strength and elevates to habits.
    Also handles habit degradation for unused behaviors.
    """

    STAGE_THRESHOLDS = [
        (0.0,  0.3,  HabitStage.NOVEL,      260.0),
        (0.3,  0.5,  HabitStage.LEARNING,   180.0),
        (0.5,  0.65, HabitStage.DEVELOPING, 100.0),
        (0.65, 0.80, HabitStage.HABITUAL,    30.0),
        (0.80, 1.0,  HabitStage.EXPERT,      8.0),
    ]

    def update_stage(self, pathway: StriatalPathway) -> bool:
        """Update habit stage based on strength. Returns True if promoted."""
        old_stage = pathway.habit_stage
        new_stage = old_stage
        new_latency = pathway.latency_ms

        for low, high, stage, latency in self.STAGE_THRESHOLDS:
            if low <= pathway.strength < high:
                new_stage   = stage.value
                new_latency = latency
                break
        if pathway.strength >= 0.80:
            new_stage   = HabitStage.EXPERT.value
            new_latency = max(5.0, 8.0 * (1.0 - pathway.strength) * 5)

        pathway.habit_stage = new_stage
        pathway.latency_ms  = new_latency

        return new_stage != old_stage and new_stage in [
            HabitStage.HABITUAL.value, HabitStage.EXPERT.value
        ]

    def decay_pathways(self, pathways: dict[str, StriatalPathway]):
        """Unused pathways slowly weaken."""
        for p in pathways.values():
            if p.use_count > 0:
                p.strength    = round(p.strength * HABIT_DECAY, 4)
                p.go_weight   = round(p.go_weight * HABIT_DECAY, 4)


# ─── Action Competition ───────────────────────────────────────────────────────

class ActionCompetition:
    """
    Resolves conflicts between competing actions.
    The basal ganglia's core function — lateral inhibition.
    """

    def resolve(self, pathways: list[StriatalPathway],
                direct: DirectPathway,
                indirect: IndirectPathway,
                stn: SubthalamicNucleus,
                dopamine: float,
                signal: dict) -> tuple[Optional[StriatalPathway],
                                       list[StriatalPathway],
                                       bool, str]:
        """
        Returns (winner, losers, stn_fired, stn_reason).
        """
        if not pathways:
            return None, [], False, ""

        # Direct pathway selects winner
        winner = direct.select(pathways, dopamine)
        if not winner:
            return None, pathways, False, ""

        runner_up = None
        losers    = []
        for p in pathways:
            if p is not winner:
                if runner_up is None or p.net_drive > runner_up.net_drive:
                    runner_up = p
                losers.append(p)

        # STN check — should we brake?
        stn_fire, stn_reason = stn.check(winner, runner_up, dopamine, signal)
        if stn_fire:
            return None, pathways, True, stn_reason

        # Suppress losers via indirect pathway
        indirect.suppress(losers, dopamine)

        return winner, losers, False, ""


# ─── Reward Gate ──────────────────────────────────────────────────────────────

class RewardGate:
    """
    Updates pathways based on actual outcome vs prediction.
    The learning heart of the basal ganglia.
    """

    def __init__(self, db: BasalGangliaDB,
                 direct: DirectPathway,
                 indirect: IndirectPathway,
                 predictor: DopaminePredictor):
        self.db        = db
        self.direct    = direct
        self.indirect  = indirect
        self.predictor = predictor

    def evaluate_outcome(self, action: str, signal: dict,
                         success: bool) -> float:
        """
        Convert action outcome to reward signal (0-1).
        """
        threat = signal.get("threat",0)
        reward = 0.5  # baseline

        if success:
            reward = 0.6 + threat * 0.08  # higher threat resolution = more reward
        else:
            reward = 0.4 - threat * 0.06  # failure under threat = more punishment

        # Cooperative actions get social reward
        social = signal.get("social",{}) or {}
        intent = social.get("inferred_intent","") if isinstance(social,dict) else ""
        if "COOPERATIVE" in intent and success:
            reward += 0.08

        return round(max(0.0, min(1.0, reward)), 3)

    def update(self, winner: StriatalPathway,
               context: str, reward: float,
               dopamine_level: float) -> tuple[float, DopamineSignal]:
        """Update pathway strengths based on reward."""
        rpe, signal = self.predictor.update(winner.action, context, reward)

        before = winner.strength

        # Update Go/NoGo weights
        self.direct.strengthen(winner, rpe)
        if rpe < 0:
            self.indirect.strengthen(winner, rpe)

        # Update overall strength
        winner.strength = round(
            max(0.05, min(0.98,
                (winner.go_weight - winner.nogo_weight + 1.0) / 2.0
            )), 4
        )
        winner.net_drive = round(winner.go_weight - winner.nogo_weight, 4)

        if rpe > 0:
            winner.success_count += 1
        else:
            winner.fail_count += 1

        winner.use_count  += 1
        winner.last_used   = datetime.now().isoformat()

        self.db.log_learning(
            winner.action, context, rpe,
            before, winner.strength, signal.value
        )
        return rpe, signal


# ─── FORGE Basal Ganglia ──────────────────────────────────────────────────────

class ForgeBasalGanglia:
    def __init__(self):
        self.db        = BasalGangliaDB()
        self.hasher    = ContextHasher()
        self.striatum  = StriatalInput(self.db, self.hasher)
        self.direct    = DirectPathway()
        self.indirect  = IndirectPathway()
        self.stn       = SubthalamicNucleus()
        self.predictor = DopaminePredictor(self.db)
        self.habits    = HabitLibrary(self.db)
        self.strengthener = HabitStrengthener()
        self.competition  = ActionCompetition()
        self.reward_gate  = RewardGate(
            self.db, self.direct, self.indirect, self.predictor
        )
        self.cycle         = 0
        self.habit_fires   = 0
        self.stn_brakes    = 0
        self.total_selected= 0
        self.pending_winner: Optional[StriatalPathway] = None
        self.pending_context: str = ""

    def select(self, candidates: list[str],
               signal: dict,
               dopamine_level: float = 0.45) -> dict:
        """
        Main action selection.
        1. Check habits first (fastest path)
        2. Run competition if no habit fires
        3. STN brake if uncertain
        """
        t0          = time.time()
        self.cycle += 1
        ctx_hash    = self.hasher.hash(signal)
        ctx_desc    = self.hasher.describe(signal)

        # ── HABIT CHECK (fastest path) ────────────────────────────────────
        habit = self.habits.check_trigger(signal)
        if habit:
            self.habit_fires += 1
            result = self.habits.fire(habit)
            latency = habit.latency_ms + (time.time()-t0)*1000

            cr = CompetitionResult(
                winner          = habit.action,
                winner_strength = habit.strength,
                gap             = 1.0,
                outcome         = SelectionOutcome.HABIT.value,
                was_habit       = True,
                latency_ms      = round(latency, 2),
                context_hash    = ctx_hash,
                dopamine_signal = DopamineSignal.TONIC.value,
                candidates      = len(candidates)
            )
            self.db.save_result(cr)

            return {
                "cycle":          self.cycle,
                "outcome":        SelectionOutcome.HABIT.value,
                "selected_action":habit.action,
                "was_habit":      True,
                "habit_name":     habit.name,
                "habit_stage":    habit.stage,
                "habit_strength": habit.strength,
                "habit_fires":    habit.fires,
                "latency_ms":     round(latency, 2),
                "sequence":       habit.sequence,
                "stn_brake":      False,
                "context":        ctx_desc,
                "rpe":            0.0,
                "dopamine_signal":DopamineSignal.TONIC.value,
                "candidates":     len(candidates),
            }

        # ── COMPETITION ───────────────────────────────────────────────────
        pathways = self.striatum.evaluate(candidates, signal)

        # Predict expected reward for each candidate
        for p in pathways:
            p.go_weight = round(
                p.go_weight * 0.7 +
                self.predictor.predict(p.action, ctx_hash, dopamine_level) * 0.3,
                4
            )

        winner, losers, stn_fire, stn_reason = self.competition.resolve(
            pathways, self.direct, self.indirect,
            self.stn, dopamine_level, signal
        )

        if stn_fire:
            self.stn_brakes += 1
            runner_up = max(pathways, key=lambda p: p.net_drive) if pathways else None
            cr = CompetitionResult(
                winner    = runner_up.action if runner_up else "NONE",
                winner_strength = runner_up.net_drive if runner_up else 0.0,
                gap       = 0.0,
                outcome   = SelectionOutcome.BRAKE.value,
                stn_brake = True,
                latency_ms= round((time.time()-t0)*1000, 2),
                context_hash = ctx_hash,
                candidates = len(candidates)
            )
            self.db.save_result(cr)
            return {
                "cycle":          self.cycle,
                "outcome":        SelectionOutcome.BRAKE.value,
                "selected_action":"HOLD",
                "was_habit":      False,
                "stn_brake":      True,
                "stn_reason":     stn_reason,
                "latency_ms":     round((time.time()-t0)*1000, 2),
                "context":        ctx_desc,
                "rpe":            0.0,
                "dopamine_signal":DopamineSignal.TONIC.value,
                "candidates":     len(candidates),
            }

        if not winner:
            return {
                "cycle":          self.cycle,
                "outcome":        "NO_WINNER",
                "selected_action":"STANDBY",
                "was_habit":      False,
                "latency_ms":     round((time.time()-t0)*1000, 2),
                "context":        ctx_desc,
                "rpe":            0.0,
                "dopamine_signal":DopamineSignal.TONIC.value,
                "candidates":     len(candidates),
            }

        self.total_selected += 1
        self.pending_winner  = winner
        self.pending_context = ctx_hash

        runner_up_strength = max(
            (p.net_drive for p in losers), default=0.0
        )
        gap = round(winner.net_drive - runner_up_strength, 4)

        # Update stage
        promoted = self.strengthener.update_stage(winner)
        if promoted or winner.is_habit:
            habit_obj = self.habits.elevate(winner, signal, self.hasher)

        # Save pathways
        for p in pathways:
            self.db.save_pathway(p)

        latency = winner.latency_ms + (time.time()-t0)*1000
        runner_up_action = max(losers, key=lambda p: p.net_drive).action if losers else ""

        cr = CompetitionResult(
            winner           = winner.action,
            winner_strength  = winner.net_drive,
            runner_up        = runner_up_action,
            runner_up_strength = runner_up_strength,
            gap              = gap,
            outcome          = SelectionOutcome.SELECTED.value,
            was_habit        = winner.is_habit,
            latency_ms       = round(latency, 2),
            context_hash     = ctx_hash,
            candidates       = len(candidates)
        )
        self.db.save_result(cr)

        return {
            "cycle":           self.cycle,
            "outcome":         SelectionOutcome.SELECTED.value,
            "selected_action": winner.action,
            "was_habit":       winner.is_habit,
            "habit_stage":     winner.habit_stage,
            "pathway_strength":round(winner.strength, 3),
            "net_drive":       round(winner.net_drive, 4),
            "gap":             round(gap, 4),
            "runner_up":       runner_up_action,
            "latency_ms":      round(latency, 2),
            "context":         ctx_desc,
            "rpe":             0.0,
            "dopamine_signal": DopamineSignal.TONIC.value,
            "candidates":      len(candidates),
            "newly_promoted":  promoted,
            "all_pathways":    [
                {"action":p.action,"strength":round(p.strength,3),
                 "net_drive":round(p.net_drive,4),"stage":p.habit_stage}
                for p in sorted(pathways, key=lambda x: x.net_drive, reverse=True)
            ]
        }

    def feedback(self, success: bool,
                 dopamine_level: float = 0.45) -> dict:
        """
        Provide outcome feedback after action execution.
        Updates pathway strengths via reward gate.
        """
        if not self.pending_winner:
            return {"status": "no_pending_winner"}

        reward = self.reward_gate.evaluate_outcome(
            self.pending_winner.action,
            {"threat": 0},  # simplified
            success
        )
        rpe, da_signal = self.reward_gate.update(
            self.pending_winner, self.pending_context,
            reward, dopamine_level
        )

        # Update stage after learning
        self.strengthener.update_stage(self.pending_winner)
        self.db.save_pathway(self.pending_winner)

        result = {
            "action":          self.pending_winner.action,
            "success":         success,
            "reward":          reward,
            "rpe":             rpe,
            "dopamine_signal": da_signal.value,
            "new_strength":    self.pending_winner.strength,
            "new_stage":       self.pending_winner.habit_stage,
            "new_latency":     self.pending_winner.latency_ms,
        }

        self.pending_winner  = None
        self.pending_context = ""
        return result

    def get_status(self) -> dict:
        pathways = list(self.striatum.pathways.values())
        habits   = list(self.habits.habits.values())
        return {
            "version":          VERSION,
            "cycle":            self.cycle,
            "total_selected":   self.total_selected,
            "habit_fires":      self.habit_fires,
            "stn_brakes":       self.stn_brakes,
            "prediction_accuracy": self.predictor.accuracy(),
            "pathways": {
                "total":    len(pathways),
                "habits":   sum(1 for p in pathways if p.is_habit),
                "experts":  sum(1 for p in pathways if p.is_expert),
                "novel":    sum(1 for p in pathways
                               if p.habit_stage == HabitStage.NOVEL.value),
            },
            "habit_library": {
                "total":    len(habits),
                "innate":   sum(1 for h in habits if h.context_hash == "innate"),
                "learned":  sum(1 for h in habits if h.context_hash != "innate"),
            },
            "top_habits": [
                {"name":h.name,"action":h.action,
                 "strength":round(h.strength,3),
                 "fires":h.fires,"stage":h.stage}
                for h in sorted(habits, key=lambda x: x.strength, reverse=True)[:5]
            ]
        }


# ─── Rich UI ──────────────────────────────────────────────────────────────────

OUTCOME_COLORS = {
    "SELECTED":   "green",
    "HABIT":      "cyan",
    "BRAKE":      "yellow",
    "NO_WINNER":  "dim",
}

STAGE_COLORS = {
    "NOVEL":      "dim",
    "LEARNING":   "blue",
    "DEVELOPING": "yellow",
    "HABITUAL":   "green",
    "EXPERT":     "bright_green",
}

DA_COLORS = {
    "BURST": "green",
    "PAUSE": "red",
    "TONIC": "dim",
}

def render_selection(result: dict, fb: Optional[dict], idx: int):
    if not HAS_RICH: return

    outcome  = result.get("outcome","SELECTED")
    oc       = OUTCOME_COLORS.get(outcome,"white")
    action   = result.get("selected_action","?")
    latency  = result.get("latency_ms",0)
    stage    = result.get("habit_stage","NOVEL")
    sc       = STAGE_COLORS.get(stage,"white")

    console.print(Rule(
        f"[bold cyan]⬡ BASAL GANGLIA[/bold cyan]  "
        f"[dim]#{idx}[/dim]  "
        f"[{oc}]{outcome}[/{oc}]  "
        f"[bold]{action}[/bold]  "
        f"[dim]{latency:.1f}ms[/dim]"
    ))

    # Left: selection result
    left_lines = []
    if result.get("was_habit"):
        left_lines += [
            f"[bold {oc}]⚡ HABIT FIRE[/bold {oc}]",
            f"[bold]Habit:[/bold]    {result.get('habit_name','?')[:30]}",
            f"[bold]Stage:[/bold]    [{sc}]{result.get('habit_stage','?')}[/{sc}]",
            f"[bold]Strength:[/bold] {'█'*int(result.get('habit_strength',0)*10)}{'░'*(10-int(result.get('habit_strength',0)*10))} {result.get('habit_strength',0):.3f}",
            f"[bold]Fires:[/bold]    {result.get('habit_fires',0)}×",
            f"[bold]Sequence:[/bold] [dim]{' → '.join(result.get('sequence',[])[:3])}[/dim]",
        ]
    elif result.get("outcome") == "BRAKE":
        left_lines += [
            f"[bold yellow]⏸ STN BRAKE[/bold yellow]",
            f"[bold]Reason:[/bold]   {result.get('stn_reason','')}",
            f"[bold]Action:[/bold]   HOLD — waiting for clarity",
        ]
    else:
        strength = result.get("pathway_strength",0)
        gap      = result.get("gap",0)
        runner   = result.get("runner_up","?")
        sc2      = STAGE_COLORS.get(stage,"white")
        left_lines += [
            f"[bold green]▶ SELECTED[/bold green]",
            f"[bold]Action:[/bold]   [{oc}]{action}[/{oc}]",
            f"[bold]Strength:[/bold] {'█'*int(strength*10)}{'░'*(10-int(strength*10))} {strength:.3f}",
            f"[bold]Stage:[/bold]    [{sc2}]{stage}[/{sc2}]",
            f"[bold]Gap:[/bold]      {gap:.4f} vs {runner}",
            f"[bold]Latency:[/bold]  {latency:.1f}ms",
        ]
        if result.get("newly_promoted"):
            left_lines.append(f"[bold cyan]★ PROMOTED TO {stage}[/bold cyan]")

    # Right: competition + pathways
    right_lines = [
        f"[bold]Candidates:[/bold] {result.get('candidates',0)}",
        f"[bold]Context:[/bold]    [dim]{result.get('context','')}[/dim]",
        f"",
    ]
    for pw in result.get("all_pathways",[])[:5]:
        sc3 = STAGE_COLORS.get(pw.get("stage","NOVEL"),"white")
        is_winner = pw["action"] == action
        mark = "[bold]▶[/bold]" if is_winner else " "
        right_lines.append(
            f"{mark} [{sc3}]{pw['action']:<18}[/{sc3}] "
            f"[dim]str={pw['strength']:.3f} drive={pw['net_drive']:+.4f}[/dim]"
        )

    console.print(Columns([
        Panel("\n".join(left_lines),  title="[bold]Selection[/bold]",  border_style=oc),
        Panel("\n".join(right_lines), title="[bold]Competition[/bold]",border_style="dim")
    ]))

    # Feedback panel
    if fb:
        rpe     = fb.get("rpe",0)
        da      = fb.get("dopamine_signal","TONIC")
        dac     = DA_COLORS.get(da,"dim")
        new_str = fb.get("new_strength",0)
        new_stage= fb.get("new_stage","NOVEL")
        nsc     = STAGE_COLORS.get(new_stage,"white")
        reward  = fb.get("reward",0.5)
        console.print(Panel(
            f"[bold]Outcome:[/bold]  {'[green]SUCCESS[/green]' if fb['success'] else '[red]FAILURE[/red]'}  "
            f"reward={reward:.2f}  RPE=[{dac}]{rpe:+.3f}[/{dac}]\n"
            f"[bold]Dopamine:[/bold] [{dac}]{da}[/{dac}]\n"
            f"[bold]New str:[/bold]  {'█'*int(new_str*10)}{'░'*(10-int(new_str*10))} {new_str:.4f}  "
            f"[{nsc}]{new_stage}[/{nsc}]  latency={fb.get('new_latency',260):.1f}ms",
            title="[bold]Reward Gate — Learning[/bold]",
            border_style=dac
        ))


def run_demo():
    if HAS_RICH:
        console.print(Panel.fit(
            "[bold cyan]FORGE BASAL GANGLIA[/bold cyan]\n"
            "[dim]Habit Formation · Action Selection · Reward Gating[/dim]\n"
            f"[dim]Version {VERSION}  |  Go/NoGo · STN · Dopamine · Habits[/dim]",
            border_style="cyan"
        ))

    bg = ForgeBasalGanglia()

    # A story that shows habit formation over time
    # Same threat scenario repeated — watch pathways strengthen to habits

    scenarios = [
        # Novel encounter — uncertain, possibly STN brake
        ({"threat":0,"anomaly":False,"social":{"inferred_intent":"COOPERATIVE_REQUEST"},
          "visual":{"scene_type":"INDOOR_TECHNICAL"}},
         ["MONITOR","COLLABORATE","STANDBY","LEARN"],
         0.50, True, "Novel — cooperative first encounter"),

        # Same cooperative — learning
        ({"threat":0,"anomaly":False,"social":{"inferred_intent":"COOPERATIVE_REQUEST"},
          "visual":{"scene_type":"INDOOR_TECHNICAL"}},
         ["MONITOR","COLLABORATE","STANDBY","LEARN"],
         0.55, True, "Repeat cooperative — pathway learning"),

        # Threat — innate habit should fire
        ({"threat":4,"anomaly":True,"social":{"inferred_intent":"INTRUSION_ATTEMPT"},
          "visual":{"scene_type":"LOW_VISIBILITY","threat_objects":2}},
         ["EMERGENCY_BLOCK","ESCALATE","ALERT","BLOCK"],
         0.30, True, "Critical threat — innate habit fires"),

        # Medium threat — competition
        ({"threat":2,"anomaly":False,"social":{"inferred_intent":"COERCIVE_DEMAND"},
          "visual":{"scene_type":"LOW_VISIBILITY"}},
         ["ALERT","BLOCK","INVESTIGATE","MONITOR"],
         0.40, True, "Medium threat — competition"),

        # Cooperative again — pathway getting stronger
        ({"threat":0,"anomaly":False,"social":{"inferred_intent":"COOPERATIVE_REQUEST"},
          "visual":{"scene_type":"INDOOR_TECHNICAL"}},
         ["MONITOR","COLLABORATE","STANDBY","LEARN"],
         0.58, True, "Cooperative 3rd time — habit developing"),

        # Novel context — STN should brake
        ({"threat":3,"anomaly":True,"social":{"inferred_intent":"COOPERATIVE_REQUEST"},
          "visual":{"scene_type":"LOW_VISIBILITY"}},
         ["BLOCK","ESCALATE","ALERT","COLLABORATE"],
         0.35, True, "Contradictory — STN brake test"),

        # Same cooperative 4th time — approaching habit
        ({"threat":0,"anomaly":False,"social":{"inferred_intent":"COOPERATIVE_REQUEST"},
          "visual":{"scene_type":"INDOOR_TECHNICAL"}},
         ["MONITOR","COLLABORATE","STANDBY","LEARN"],
         0.62, True, "Cooperative 4th — nearing habit"),

        # Anomaly — innate habit
        ({"threat":1,"anomaly":True,"social":{"inferred_intent":"NEUTRAL_INTERACTION"},
          "visual":{"scene_type":"INDOOR_TECHNICAL"}},
         ["INVESTIGATE","ALERT","MONITOR","BLOCK"],
         0.45, True, "Anomaly — innate orient habit"),
    ]

    for i, (sig, candidates, dopamine, success, label) in enumerate(scenarios):
        if HAS_RICH:
            console.print(f"\n[bold dim]━━━ {i+1}: {label.upper()} ━━━[/bold dim]")

        result = bg.select(candidates, sig, dopamine)
        fb     = None
        if result.get("outcome") not in ["BRAKE","HABIT","NO_WINNER"]:
            fb = bg.feedback(success, dopamine)

        render_selection(result, fb, i+1)
        time.sleep(0.1)

    # Final status
    if HAS_RICH:
        console.print(Rule("[bold cyan]⬡ BASAL GANGLIA FINAL STATUS[/bold cyan]"))
        status = bg.get_status()

        status_table = Table(box=box.DOUBLE_EDGE, border_style="cyan",
                            title="Basal Ganglia Status")
        status_table.add_column("Metric", style="cyan")
        status_table.add_column("Value",  style="white")
        status_table.add_row("Total Cycles",     str(status["cycle"]))
        status_table.add_row("Total Selected",   str(status["total_selected"]))
        status_table.add_row("Habit Fires",      str(status["habit_fires"]))
        status_table.add_row("STN Brakes",       str(status["stn_brakes"]))
        status_table.add_row("Pred. Accuracy",   f"{status['prediction_accuracy']:.0%}")
        status_table.add_row("Total Pathways",   str(status["pathways"]["total"]))
        status_table.add_row("Habit Pathways",   str(status["pathways"]["habits"]))
        status_table.add_row("Expert Pathways",  str(status["pathways"]["experts"]))
        status_table.add_row("Habit Library",    str(status["habit_library"]["total"]))
        console.print(status_table)

        # Top habits
        habit_table = Table(box=box.SIMPLE, title="Habit Library",
                           title_style="dim")
        habit_table.add_column("Name",     style="cyan", width=28)
        habit_table.add_column("Action",   width=18)
        habit_table.add_column("Strength")
        habit_table.add_column("Fires", justify="right", width=6)
        habit_table.add_column("Stage",  width=12)
        for h in status["top_habits"]:
            s  = h["strength"]
            sc = "bright_green" if s>0.9 else "green" if s>0.75 else "yellow"
            esc= STAGE_COLORS.get(h["stage"],"white")
            habit_table.add_row(
                h["name"][:27], h["action"],
                f"[{sc}]{'█'*int(s*10)}{'░'*(10-int(s*10))} {s:.3f}[/{sc}]",
                str(h["fires"]),
                f"[{esc}]{h['stage']}[/{esc}]"
            )
        console.print(habit_table)


# ─── HTTP API ─────────────────────────────────────────────────────────────────

def run_api(bg: ForgeBasalGanglia):
    if not HAS_FLASK: return
    app = Flask(__name__)

    @app.route("/select", methods=["POST"])
    def select():
        data = request.json or {}
        return jsonify(bg.select(
            data.get("candidates",[]),
            data.get("signal",{}),
            data.get("dopamine",0.45)
        ))

    @app.route("/feedback", methods=["POST"])
    def feedback():
        data = request.json or {}
        return jsonify(bg.feedback(
            data.get("success", True),
            data.get("dopamine", 0.45)
        ))

    @app.route("/habits", methods=["GET"])
    def habits():
        rows = bg.db.get_habits()
        return jsonify([{"id":r[0],"name":r[1],"action":r[2],
                        "strength":r[3],"fires":r[4],"stage":r[5],
                        "latency":r[6]} for r in rows])

    @app.route("/pathways", methods=["GET"])
    def pathways():
        rows = bg.db.get_pathways(0.3)
        return jsonify([{"action":r[0],"context":r[1],"strength":r[2],
                        "uses":r[3],"successes":r[4],"fails":r[5],
                        "stage":r[6],"latency":r[7]} for r in rows])

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify(bg.get_status())

    app.run(host="0.0.0.0", port=API_PORT, debug=False)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    bg = ForgeBasalGanglia()
    if "--api" in sys.argv:
        t = threading.Thread(target=run_api, args=(bg,), daemon=True)
        t.start()
    run_demo()
