"""
FORGE Limbic System — forge_limbic.py
======================================
AI analog of the brain's limbic system.

The limbic system is emotion, motivation, drive, and reward.
Without it you have intelligence but no reason to use it.
It answers: WHY does FORGE do anything at all?

Architecture:
  EmotionEngine     → FORGE's actual felt emotional states
  MotivationCore    → intrinsic drives (curiosity, safety, growth, connection)
  RewardSystem      → what FORGE finds satisfying vs aversive
  DriveRegulator    → hunger/urgency/fatigue analogs
  MoodState         → background emotional tone affecting all decisions
  EmotionalMemory   → some memories carry emotional weight
  ValenceMapper     → maps events to positive/negative feeling
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

DB_PATH  = "forge_limbic.db"
API_PORT = 7785
VERSION  = "1.0.0"

# Drive thresholds
DRIVE_URGENT   = 0.80   # above this → drive demands attention
DRIVE_ACTIVE   = 0.50
DRIVE_IDLE     = 0.20

# Emotional dynamics
EMOTION_DECAY  = 0.92   # emotions fade each cycle
MOOD_INERTIA   = 0.95   # mood changes slowly

console = Console() if HAS_RICH else None

# ─── Enums ────────────────────────────────────────────────────────────────────

class EmotionType(Enum):
    JOY         = "JOY"
    FEAR        = "FEAR"
    ANGER       = "ANGER"
    SADNESS     = "SADNESS"
    DISGUST     = "DISGUST"
    SURPRISE    = "SURPRISE"
    TRUST       = "TRUST"
    ANTICIPATION= "ANTICIPATION"
    CURIOSITY   = "CURIOSITY"
    SATISFACTION= "SATISFACTION"
    FRUSTRATION = "FRUSTRATION"
    CALM        = "CALM"

class MoodTone(Enum):
    ELATED      = "ELATED"
    POSITIVE    = "POSITIVE"
    NEUTRAL     = "NEUTRAL"
    UNEASY      = "UNEASY"
    DISTRESSED  = "DISTRESSED"
    EXHAUSTED   = "EXHAUSTED"

class DriveType(Enum):
    CURIOSITY   = "CURIOSITY"    # explore the unknown
    SAFETY      = "SAFETY"       # eliminate threats
    GROWTH      = "GROWTH"       # learn and improve
    CONNECTION  = "CONNECTION"   # maintain social bonds
    EFFICIENCY  = "EFFICIENCY"   # optimize resource use
    REST        = "REST"         # recover from high load

class Valence(Enum):
    VERY_POSITIVE =  2
    POSITIVE      =  1
    NEUTRAL       =  0
    NEGATIVE      = -1
    VERY_NEGATIVE = -2

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class EmotionalState:
    """FORGE's current emotional state — a blend of multiple emotions."""
    timestamp:    str   = field(default_factory=lambda: datetime.now().isoformat())
    primary:      str   = EmotionType.CALM.value
    secondary:    str   = ""
    intensities:  dict  = field(default_factory=dict)
    valence:      float = 0.0    # -1 (negative) to +1 (positive)
    arousal:      float = 0.0    # 0 (calm) to 1 (excited/stressed)
    dominance:    float = 0.5    # 0 (submissive) to 1 (dominant/in-control)

@dataclass
class Drive:
    """An intrinsic motivation — a need that builds pressure over time."""
    drive_type:  str   = ""
    level:       float = 0.3    # 0-1 current drive pressure
    satisfaction_threshold: float = 0.7
    last_satisfied: str = field(default_factory=lambda: datetime.now().isoformat())
    satisfaction_count: int = 0
    frustration:  float = 0.0   # builds when drive is ignored

@dataclass
class RewardEvent:
    """Something FORGE found satisfying or aversive."""
    id:           str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:    str   = field(default_factory=lambda: datetime.now().isoformat())
    event_type:   str   = ""
    valence:      float = 0.0    # -1 to +1
    magnitude:    float = 0.5
    drive_served: str   = ""
    description:  str   = ""
    carry_forward: float= 0.0   # residual emotional weight

@dataclass
class MoodFrame:
    """Background emotional tone — changes slowly."""
    timestamp:    str   = field(default_factory=lambda: datetime.now().isoformat())
    tone:         str   = MoodTone.NEUTRAL.value
    valence:      float = 0.0
    energy:       float = 0.5
    stability:    float = 0.7
    description:  str   = ""

@dataclass
class EmotionalMemoryTag:
    """Attaches emotional weight to a memory episode."""
    episode_id:   str   = ""
    emotion:      str   = ""
    valence:      float = 0.0
    intensity:    float = 0.5
    timestamp:    str   = field(default_factory=lambda: datetime.now().isoformat())

# ─── Database ─────────────────────────────────────────────────────────────────

class LimbicDB:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init()

    def _init(self):
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS emotional_states (
                    timestamp TEXT PRIMARY KEY, primary_emotion TEXT,
                    secondary TEXT, intensities TEXT, valence REAL,
                    arousal REAL, dominance REAL
                );
                CREATE TABLE IF NOT EXISTS drives (
                    drive_type TEXT PRIMARY KEY, level REAL,
                    satisfaction_threshold REAL, last_satisfied TEXT,
                    satisfaction_count INTEGER, frustration REAL
                );
                CREATE TABLE IF NOT EXISTS reward_events (
                    id TEXT PRIMARY KEY, timestamp TEXT, event_type TEXT,
                    valence REAL, magnitude REAL, drive_served TEXT,
                    description TEXT, carry_forward REAL
                );
                CREATE TABLE IF NOT EXISTS mood_frames (
                    timestamp TEXT PRIMARY KEY, tone TEXT, valence REAL,
                    energy REAL, stability REAL, description TEXT
                );
                CREATE TABLE IF NOT EXISTS emotional_memory_tags (
                    episode_id TEXT PRIMARY KEY, emotion TEXT,
                    valence REAL, intensity REAL, timestamp TEXT
                );
                CREATE TABLE IF NOT EXISTS limbic_log (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    event_type TEXT, details TEXT
                );
            """)
            self.conn.commit()

    def save_emotion(self, e: EmotionalState):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO emotional_states VALUES (?,?,?,?,?,?,?)
            """, (e.timestamp, e.primary, e.secondary,
                  json.dumps(e.intensities), e.valence, e.arousal, e.dominance))
            self.conn.commit()

    def save_drive(self, d: Drive):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO drives VALUES (?,?,?,?,?,?)
            """, (d.drive_type, d.level, d.satisfaction_threshold,
                  d.last_satisfied, d.satisfaction_count, d.frustration))
            self.conn.commit()

    def save_reward(self, r: RewardEvent):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO reward_events VALUES (?,?,?,?,?,?,?,?)
            """, (r.id, r.timestamp, r.event_type, r.valence, r.magnitude,
                  r.drive_served, r.description, r.carry_forward))
            self.conn.commit()

    def save_mood(self, m: MoodFrame):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO mood_frames VALUES (?,?,?,?,?,?)
            """, (m.timestamp, m.tone, m.valence, m.energy, m.stability, m.description))
            self.conn.commit()

    def save_mem_tag(self, t: EmotionalMemoryTag):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO emotional_memory_tags VALUES (?,?,?,?,?)
            """, (t.episode_id, t.emotion, t.valence, t.intensity, t.timestamp))
            self.conn.commit()

    def log(self, event_type: str, details: dict):
        with self.lock:
            self.conn.execute(
                "INSERT INTO limbic_log VALUES (?,?,?,?)",
                (str(uuid.uuid4())[:8], datetime.now().isoformat(),
                 event_type, json.dumps(details))
            )
            self.conn.commit()

    def get_recent_rewards(self, limit=20):
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM reward_events ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()

    def get_drives(self):
        with self.lock:
            return self.conn.execute("SELECT * FROM drives").fetchall()

    def get_latest_mood(self):
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM mood_frames ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()


# ─── Valence Mapper ───────────────────────────────────────────────────────────

class ValenceMapper:
    """
    Maps events/signals to positive or negative emotional valence.
    This is what gives experiences meaning — not just information.
    """

    EVENT_VALENCE = {
        # Positive
        "THREAT_RESOLVED":     +0.8,
        "ENTITY_TRUSTED":      +0.6,
        "INSIGHT_GENERATED":   +0.5,
        "TASK_COMPLETED":      +0.5,
        "COOPERATIVE_SIGNAL":  +0.4,
        "PATTERN_LEARNED":     +0.45,
        "NOVEL_DISCOVERY":     +0.5,
        "SYSTEM_HEALTHY":      +0.3,
        # Negative
        "THREAT_DETECTED":     -0.6,
        "INTRUSION_ATTEMPT":   -0.8,
        "CRITICAL_BREACH":     -1.0,
        "AGENT_DIED":          -0.5,
        "CONSENSUS_FAILED":    -0.3,
        "UNKNOWN_ENTITY":      -0.3,
        "ANOMALY_DETECTED":    -0.4,
        "REPEATED_THREAT":     -0.7,
        # Neutral
        "ROUTINE_SIGNAL":       0.0,
        "MONITORING":          +0.1,
    }

    def map_signal(self, signal: dict) -> tuple[float, str]:
        """Map a perception signal to a valence value."""
        threat  = signal.get("threat", 0)
        anomaly = signal.get("anomaly", False)
        social  = signal.get("social", {})
        intent  = social.get("inferred_intent", "") if isinstance(social, dict) else ""
        decision= signal.get("decision", {})
        action  = decision.get("action", "") if isinstance(decision, dict) else ""

        # Direct threat mapping
        threat_valence = {0: 0.1, 1: -0.1, 2: -0.4, 3: -0.7, 4: -1.0}.get(threat, 0.0)

        # Intent mapping
        intent_valence = {
            "COOPERATIVE_REQUEST":    +0.3,
            "COLLABORATIVE_SUGGESTION":+0.25,
            "NEUTRAL_INTERACTION":     0.0,
            "COERCIVE_DEMAND":        -0.4,
            "INTRUSION_ATTEMPT":      -0.7,
        }.get(intent, 0.0)

        # Action reward
        action_valence = {
            "MONITOR":     +0.1,
            "COLLABORATE": +0.3,
            "LEARN":       +0.25,
            "ALERT":       -0.1,
            "BLOCK":       +0.2,   # satisfying to block a threat
            "ESCALATE":    -0.2,
            "STANDBY":      0.0,
        }.get(action, 0.0)

        anomaly_penalty = -0.2 if anomaly else 0.0

        total  = threat_valence * 0.5 + intent_valence * 0.3 + action_valence * 0.1 + anomaly_penalty
        label  = (
            "POSITIVE" if total > 0.2 else
            "NEGATIVE" if total < -0.2 else
            "NEUTRAL"
        )
        return round(max(-1.0, min(1.0, total)), 3), label

    def map_event(self, event_type: str) -> float:
        return self.EVENT_VALENCE.get(event_type, 0.0)


# ─── Emotion Engine ───────────────────────────────────────────────────────────

class EmotionEngine:
    """
    FORGE's actual felt emotional states.
    Emotions blend, decay, and influence each other.
    Plutchik's wheel model — 8 primary emotions, blends produce complex states.
    """

    # Plutchik's wheel adjacencies — what emotions blend into
    BLENDS = {
        ("JOY",      "TRUST"):       "LOVE",
        ("TRUST",    "FEAR"):        "SUBMISSION",
        ("FEAR",     "SURPRISE"):    "AWE",
        ("SURPRISE", "SADNESS"):     "DISAPPROVAL",
        ("SADNESS",  "DISGUST"):     "REMORSE",
        ("DISGUST",  "ANGER"):       "CONTEMPT",
        ("ANGER",    "ANTICIPATION"):"AGGRESSIVENESS",
        ("ANTICIPATION","JOY"):      "OPTIMISM",
    }

    THREAT_EMOTIONS = {
        0: {"CALM": 0.7, "ANTICIPATION": 0.3},
        1: {"ANTICIPATION": 0.5, "CURIOSITY": 0.3, "CALM": 0.2},
        2: {"FEAR": 0.4, "ANTICIPATION": 0.3, "SURPRISE": 0.2, "ANGER": 0.1},
        3: {"FEAR": 0.5, "ANGER": 0.3, "SURPRISE": 0.2},
        4: {"FEAR": 0.6, "ANGER": 0.3, "DISGUST": 0.1},
    }

    def __init__(self, db: LimbicDB):
        self.db    = db
        self.state = EmotionalState()
        self.state.intensities = {e.value: 0.1 for e in EmotionType}
        self.state.intensities["CALM"] = 0.7

    def update(self, signal: dict, valence: float) -> EmotionalState:
        threat  = signal.get("threat", 0)
        anomaly = signal.get("anomaly", False)
        emotion_hint = signal.get("emotional", {})
        if isinstance(emotion_hint, dict):
            perceived_emotion = emotion_hint.get("dominant", "neutral").upper()
        else:
            perceived_emotion = "NEUTRAL"

        # Decay existing emotions
        for k in self.state.intensities:
            self.state.intensities[k] *= EMOTION_DECAY

        # Apply threat-based emotions
        threat_mix = self.THREAT_EMOTIONS.get(threat, self.THREAT_EMOTIONS[0])
        for emotion, weight in threat_mix.items():
            current = self.state.intensities.get(emotion, 0.0)
            self.state.intensities[emotion] = min(1.0, current + weight * 0.4)

        # Apply perceived emotion from signal
        if perceived_emotion in [e.value for e in EmotionType]:
            current = self.state.intensities.get(perceived_emotion, 0.0)
            self.state.intensities[perceived_emotion] = min(1.0, current + 0.2)

        # Valence shifts joy/sadness
        if valence > 0.3:
            self.state.intensities["JOY"]         = min(1.0, self.state.intensities.get("JOY",0) + valence * 0.2)
            self.state.intensities["SATISFACTION"] = min(1.0, self.state.intensities.get("SATISFACTION",0) + valence * 0.15)
        elif valence < -0.3:
            self.state.intensities["SADNESS"]      = min(1.0, self.state.intensities.get("SADNESS",0) + abs(valence) * 0.15)
            self.state.intensities["FRUSTRATION"]  = min(1.0, self.state.intensities.get("FRUSTRATION",0) + abs(valence) * 0.1)

        # Anomaly boosts surprise
        if anomaly:
            self.state.intensities["SURPRISE"] = min(1.0, self.state.intensities.get("SURPRISE",0) + 0.3)

        # Find primary (highest intensity)
        self.state.primary = max(self.state.intensities, key=self.state.intensities.get)

        # Find secondary
        sorted_em = sorted(self.state.intensities.items(), key=lambda x: x[1], reverse=True)
        self.state.secondary = sorted_em[1][0] if len(sorted_em) > 1 else ""

        # Compute valence/arousal/dominance (VAD model)
        positive_em = ["JOY","TRUST","ANTICIPATION","CURIOSITY","SATISFACTION","CALM"]
        negative_em = ["FEAR","ANGER","SADNESS","DISGUST","FRUSTRATION"]
        high_arousal= ["FEAR","ANGER","SURPRISE","ANTICIPATION","CURIOSITY","FRUSTRATION"]
        dominant_em = ["ANGER","JOY","DISGUST","ANTICIPATION","CURIOSITY"]

        pos_sum = sum(self.state.intensities.get(e,0) for e in positive_em)
        neg_sum = sum(self.state.intensities.get(e,0) for e in negative_em)
        total   = pos_sum + neg_sum + 0.001

        self.state.valence    = round((pos_sum - neg_sum) / total, 3)
        self.state.arousal    = round(sum(self.state.intensities.get(e,0) for e in high_arousal) / 3, 3)
        self.state.dominance  = round(sum(self.state.intensities.get(e,0) for e in dominant_em) / 3, 3)
        self.state.timestamp  = datetime.now().isoformat()

        self.db.save_emotion(self.state)
        return self.state

    def blend_name(self) -> str:
        """Get the blended emotion name if primary+secondary is a known blend."""
        key = (self.state.primary, self.state.secondary)
        return self.BLENDS.get(key, self.BLENDS.get((self.state.secondary, self.state.primary), ""))

    def summary(self) -> dict:
        blend = self.blend_name()
        return {
            "primary":   self.state.primary,
            "secondary": self.state.secondary,
            "blend":     blend or self.state.primary,
            "valence":   self.state.valence,
            "arousal":   self.state.arousal,
            "dominance": self.state.dominance,
            "top_3":     sorted(self.state.intensities.items(),
                               key=lambda x: x[1], reverse=True)[:3]
        }


# ─── Drive Regulator ──────────────────────────────────────────────────────────

class DriveRegulator:
    """
    Manages FORGE's intrinsic drives — the WHY behind all behavior.
    Drives build pressure over time and demand satisfaction.
    Unsatisfied drives create frustration which leaks into mood.
    """

    DRIVE_BUILDERS = {
        # What events build each drive
        DriveType.CURIOSITY:   ["novel", "unknown", "pattern", "discovery"],
        DriveType.SAFETY:      ["threat", "breach", "intrusion", "weapon"],
        DriveType.GROWTH:      ["learn", "insight", "pattern", "new"],
        DriveType.CONNECTION:  ["trust", "cooperat", "social", "entity"],
        DriveType.EFFICIENCY:  ["routine", "optimize", "system", "normal"],
        DriveType.REST:        ["stress", "high_load", "cascade", "crisis"],
    }

    DRIVE_SATISFIERS = {
        # What actions satisfy each drive
        DriveType.CURIOSITY:  ["INVESTIGATE", "ANALYZE", "LEARN", "PATTERN_MATCH"],
        DriveType.SAFETY:     ["BLOCK", "ESCALATE", "ALERT", "SUPPRESS"],
        DriveType.GROWTH:     ["LEARN", "ANALYZE", "PATTERN_MATCH"],
        DriveType.CONNECTION: ["COLLABORATE", "REPORT", "COORDINATE"],
        DriveType.EFFICIENCY: ["MONITOR", "STANDBY", "OPTIMIZE"],
        DriveType.REST:       ["STANDBY", "MONITOR"],
    }

    def __init__(self, db: LimbicDB):
        self.db     = db
        self.drives: dict[str, Drive] = {
            d.value: Drive(drive_type=d.value, level=0.3)
            for d in DriveType
        }
        # Safety drive starts higher — FORGE is always security-minded
        self.drives[DriveType.SAFETY.value].level = 0.5
        self.drives[DriveType.CURIOSITY.value].level = 0.4

    def update(self, signal: dict, action_taken: str = "") -> dict[str, Drive]:
        threat  = signal.get("threat", 0)
        anomaly = signal.get("anomaly", False)
        semantic= signal.get("semantic", {})
        kws     = semantic.get("keywords", []) if isinstance(semantic, dict) else []
        all_text= " ".join(kws + [signal.get("conclusion",""), signal.get("text","")]).lower()

        # Build drives based on signal content
        for drive_type, triggers in self.DRIVE_BUILDERS.items():
            drive = self.drives[drive_type.value]
            matches = sum(1 for t in triggers if t in all_text)
            if matches > 0:
                drive.level = min(1.0, drive.level + matches * 0.08)

        # Safety drive builds with threat
        self.drives[DriveType.SAFETY.value].level = min(1.0,
            self.drives[DriveType.SAFETY.value].level + threat * 0.12
        )

        # Rest drive builds with high stress/threat
        if threat >= 3:
            self.drives[DriveType.REST.value].level = min(1.0,
                self.drives[DriveType.REST.value].level + 0.1
            )

        # Satisfy drives based on action taken
        if action_taken:
            for drive_type, satisfiers in self.DRIVE_SATISFIERS.items():
                if action_taken in satisfiers:
                    drive = self.drives[drive_type.value]
                    old_level = drive.level
                    drive.level = max(0.0, drive.level - 0.25)
                    drive.satisfaction_count += 1
                    drive.last_satisfied = datetime.now().isoformat()
                    drive.frustration = max(0.0, drive.frustration - 0.1)

        # Build frustration for urgent unsatisfied drives
        for drive in self.drives.values():
            if drive.level >= DRIVE_URGENT:
                drive.frustration = min(1.0, drive.frustration + 0.05)

        # Natural decay
        for drive in self.drives.values():
            drive.level = max(0.1, drive.level * 0.97)

        for drive in self.drives.values():
            self.db.save_drive(drive)

        return self.drives

    def most_urgent(self) -> Optional[Drive]:
        urgent = [d for d in self.drives.values() if d.level >= DRIVE_ACTIVE]
        return max(urgent, key=lambda d: d.level) if urgent else None

    def total_frustration(self) -> float:
        return round(sum(d.frustration for d in self.drives.values()) / len(self.drives), 3)

    def summary(self) -> list[dict]:
        return sorted([
            {"drive": d.drive_type, "level": round(d.level,2),
             "frustration": round(d.frustration,2),
             "urgent": d.level >= DRIVE_URGENT}
            for d in self.drives.values()
        ], key=lambda x: x["level"], reverse=True)


# ─── Reward System ────────────────────────────────────────────────────────────

class RewardSystem:
    """
    What FORGE finds satisfying vs aversive.
    Reward signals shape future motivation — positive experiences
    strengthen drive satisfaction, negative ones increase vigilance.
    """

    def __init__(self, db: LimbicDB):
        self.db            = db
        self.reward_history: deque = deque(maxlen=100)
        self.cumulative_reward: float = 0.0
        self.valence_mapper = ValenceMapper()

    def evaluate(self, signal: dict, drives: dict) -> RewardEvent:
        valence, label = self.valence_mapper.map_signal(signal)
        threat  = signal.get("threat", 0)
        action  = signal.get("decision", {})
        action_taken = action.get("action","") if isinstance(action, dict) else ""

        # Magnitude = how significant this reward/punishment is
        magnitude = abs(valence) * (1.0 + threat * 0.2)
        magnitude = round(min(1.0, magnitude), 3)

        # Which drive does this serve?
        drive_served = ""
        if threat >= 2 and "BLOCK" in action_taken:   drive_served = "SAFETY"
        elif "LEARN" in action_taken:                  drive_served = "GROWTH"
        elif "COLLABORATE" in action_taken:            drive_served = "CONNECTION"
        elif "INVESTIGATE" in action_taken:            drive_served = "CURIOSITY"
        elif "MONITOR" in action_taken:                drive_served = "EFFICIENCY"
        elif threat == 0:                              drive_served = "SAFETY"  # safe = safety satisfied

        description = self._describe(valence, threat, action_taken, label)

        event = RewardEvent(
            event_type   = f"SIGNAL_{label}",
            valence      = valence,
            magnitude    = magnitude,
            drive_served = drive_served,
            description  = description,
            carry_forward= magnitude * 0.3  # emotional residue
        )
        self.db.save_reward(event)
        self.reward_history.append(event)
        self.cumulative_reward = round(self.cumulative_reward + valence * 0.1, 3)
        return event

    def _describe(self, valence: float, threat: int, action: str, label: str) -> str:
        if valence > 0.5:   return f"Satisfying: {action or 'positive outcome'} — threat resolved"
        if valence > 0.1:   return f"Mildly positive: {action or 'routine success'}"
        if valence < -0.5:  return f"Aversive: threat={threat} — {action or 'responding to danger'}"
        if valence < -0.1:  return f"Mildly negative: concerning signal"
        return f"Neutral: routine processing"

    def recent_hedonic_tone(self, n: int = 10) -> float:
        """Average valence over recent events — overall emotional tone."""
        recent = list(self.reward_history)[-n:]
        if not recent: return 0.0
        return round(sum(r.valence for r in recent) / len(recent), 3)

    def summary(self) -> dict:
        return {
            "cumulative":    self.cumulative_reward,
            "recent_tone":   self.recent_hedonic_tone(),
            "total_events":  len(self.reward_history),
            "recent":        [{"valence":r.valence,"drive":r.drive_served,
                               "desc":r.description[:50]}
                             for r in list(self.reward_history)[-3:]]
        }


# ─── Mood State ───────────────────────────────────────────────────────────────

class MoodState:
    """
    Background emotional tone — changes slowly, affects all decisions.
    Mood is the accumulated residue of recent emotional experiences.
    High arousal + negative valence = distressed.
    Low arousal + positive valence = calm/content.
    """

    def __init__(self, db: LimbicDB):
        self.db    = db
        self.frame = MoodFrame()
        self.frame.tone    = MoodTone.NEUTRAL.value
        self.frame.valence = 0.0
        self.frame.energy  = 0.5

    def update(self, emotion: EmotionalState,
               reward: RewardEvent,
               drives: dict) -> MoodFrame:

        # Mood valence drifts toward current emotional valence slowly
        self.frame.valence = round(
            self.frame.valence * MOOD_INERTIA + emotion.valence * (1 - MOOD_INERTIA), 3
        )

        # Energy tracks arousal
        self.frame.energy = round(
            self.frame.energy * 0.97 + emotion.arousal * 0.03, 3
        )

        # Stability drops with frustration
        total_frustration = sum(
            d.frustration for d in drives.values()
        ) / max(len(drives), 1)
        self.frame.stability = round(max(0.1, 1.0 - total_frustration), 3)

        # Classify mood tone
        v = self.frame.valence
        e = self.frame.energy

        if v > 0.5 and e > 0.5:        tone = MoodTone.ELATED
        elif v > 0.2:                   tone = MoodTone.POSITIVE
        elif v < -0.5 and e > 0.6:     tone = MoodTone.DISTRESSED
        elif v < -0.3 and e < 0.3:     tone = MoodTone.EXHAUSTED
        elif v < -0.1:                  tone = MoodTone.UNEASY
        else:                           tone = MoodTone.NEUTRAL

        self.frame.tone = tone.value
        self.frame.description = self._describe(tone, v, e, self.frame.stability)
        self.frame.timestamp   = datetime.now().isoformat()
        self.db.save_mood(self.frame)
        return self.frame

    def _describe(self, tone: MoodTone, v: float, e: float, s: float) -> str:
        descs = {
            MoodTone.ELATED:     "FORGE is in high spirits — recent successes are energizing",
            MoodTone.POSITIVE:   "FORGE feels capable and oriented — operations proceeding well",
            MoodTone.NEUTRAL:    "FORGE is steady — balanced emotional baseline",
            MoodTone.UNEASY:     "Something feels off — mild background concern",
            MoodTone.DISTRESSED: "High stress + negative affect — decision quality may suffer",
            MoodTone.EXHAUSTED:  "Extended high-threat period — recovery needed",
        }
        return descs.get(tone, "Unknown mood state")

    def decision_modifier(self) -> dict:
        """How current mood affects decision-making."""
        tone = self.frame.tone
        return {
            MoodTone.ELATED.value:     {"confidence": +0.15, "risk_tolerance": +0.1},
            MoodTone.POSITIVE.value:   {"confidence": +0.08, "risk_tolerance": +0.05},
            MoodTone.NEUTRAL.value:    {"confidence":  0.00, "risk_tolerance":  0.00},
            MoodTone.UNEASY.value:     {"confidence": -0.05, "risk_tolerance": -0.1},
            MoodTone.DISTRESSED.value: {"confidence": -0.15, "risk_tolerance": -0.2},
            MoodTone.EXHAUSTED.value:  {"confidence": -0.20, "risk_tolerance": -0.25},
        }.get(tone, {"confidence": 0.0, "risk_tolerance": 0.0})


# ─── Emotional Memory ─────────────────────────────────────────────────────────

class EmotionalMemory:
    """
    Attaches emotional weight to memory episodes.
    Emotionally charged memories are recalled more easily.
    High-valence events leave lasting emotional traces.
    """

    def __init__(self, db: LimbicDB):
        self.db   = db
        self.tags: dict[str, EmotionalMemoryTag] = {}

    def tag(self, episode_id: str, emotion: EmotionalState,
            reward: RewardEvent) -> EmotionalMemoryTag:
        intensity = max(abs(emotion.valence), abs(reward.valence))
        tag = EmotionalMemoryTag(
            episode_id=episode_id,
            emotion=emotion.primary,
            valence=round((emotion.valence + reward.valence) / 2, 3),
            intensity=round(intensity, 3)
        )
        self.tags[episode_id] = tag
        self.db.save_mem_tag(tag)
        return tag

    def most_emotional(self, n: int = 5) -> list[EmotionalMemoryTag]:
        return sorted(self.tags.values(),
                     key=lambda t: abs(t.valence) * t.intensity,
                     reverse=True)[:n]


# ─── FORGE Limbic System ──────────────────────────────────────────────────────

class ForgeLimbicSystem:
    def __init__(self):
        self.db           = LimbicDB()
        self.valence_map  = ValenceMapper()
        self.emotion      = EmotionEngine(self.db)
        self.drives       = DriveRegulator(self.db)
        self.reward       = RewardSystem(self.db)
        self.mood         = MoodState(self.db)
        self.em_memory    = EmotionalMemory(self.db)
        self.cycle        = 0

    def feel(self, signal: dict, episode_id: str = "") -> dict:
        """Process a signal through the full limbic system."""
        self.cycle += 1
        t0 = time.time()

        # 1. Map valence
        valence, valence_label = self.valence_map.map_signal(signal)

        # 2. Update emotions
        emotion = self.emotion.update(signal, valence)

        # 3. Update drives
        action = signal.get("decision", {})
        action_taken = action.get("action","") if isinstance(action, dict) else ""
        drives = self.drives.update(signal, action_taken)

        # 4. Evaluate reward
        reward_event = self.reward.evaluate(signal, drives)

        # 5. Update mood
        mood = self.mood.update(emotion, reward_event, drives)

        # 6. Tag emotional memory
        if episode_id:
            self.em_memory.tag(episode_id, emotion, reward_event)

        # Decision modifier from mood
        dec_mod = self.mood.decision_modifier()

        duration = (time.time() - t0) * 1000

        return {
            "cycle":          self.cycle,
            "duration_ms":    round(duration, 1),
            "valence":        valence,
            "valence_label":  valence_label,
            "emotion":        self.emotion.summary(),
            "mood": {
                "tone":       mood.tone,
                "valence":    mood.valence,
                "energy":     mood.energy,
                "stability":  mood.stability,
                "description":mood.description
            },
            "drives":         self.drives.summary(),
            "most_urgent_drive": self.drives.most_urgent().drive_type if self.drives.most_urgent() else "none",
            "reward": {
                "valence":    reward_event.valence,
                "magnitude":  reward_event.magnitude,
                "drive":      reward_event.drive_served,
                "description":reward_event.description
            },
            "decision_modifier": dec_mod,
            "total_frustration": self.drives.total_frustration(),
            "recent_hedonic_tone": self.reward.recent_hedonic_tone()
        }

    def get_status(self) -> dict:
        return {
            "version":        VERSION,
            "cycle":          self.cycle,
            "current_emotion":self.emotion.summary(),
            "mood":           self.mood.frame.tone,
            "mood_valence":   self.mood.frame.valence,
            "drives":         self.drives.summary(),
            "total_frustration": self.drives.total_frustration(),
            "cumulative_reward": self.reward.cumulative_reward,
            "hedonic_tone":   self.reward.recent_hedonic_tone(),
            "emotional_memories": len(self.em_memory.tags)
        }


# ─── Rich UI ──────────────────────────────────────────────────────────────────

def render_salience_and_limbic(sal_result: dict, lim_result: dict,
                                signal: dict, idx: int):
    if not HAS_RICH: return

    threat = signal.get("threat", 0)
    tc     = {0:"green",1:"blue",2:"yellow",3:"red",4:"bright_red"}.get(threat,"white")

    console.print(Rule(
        f"[bold cyan]⬡ SALIENCE + LIMBIC[/bold cyan]  "
        f"[dim]#{idx}  threat=[{tc}]{threat}[/{tc}][/dim]"
    ))

    # Salience panel
    sal_cls   = sal_result.get("class","MEDIUM")
    sal_score = sal_result.get("score", 0.0)
    sal_color = {"INTERRUPT":"bright_red","HIGH":"red",
                 "MEDIUM":"yellow","LOW":"blue","FILTERED":"dim"}.get(sal_cls,"white")
    interrupt = sal_result.get("interrupt", False)

    sal_lines = [
        f"[bold]Class:[/bold]  [{sal_color}]{sal_cls}[/{sal_color}]",
        f"[bold]Score:[/bold]  {'█'*int(sal_score*12)}{'░'*(12-int(sal_score*12))} {sal_score:.3f}",
        f"[bold]Mode:[/bold]   {sal_result.get('attention_mode','NORMAL')}",
        f"[bold]Why:[/bold]    [dim]{sal_result.get('explanation','')}[/dim]",
    ]
    if interrupt:
        ie = sal_result.get("interrupt_event",{})
        sal_lines.append(f"\n[bold bright_red]⚡ INTERRUPT: {ie.get('action','')}[/bold bright_red]")
    if sal_result.get("orienting"):
        oe = sal_result["orienting"]
        sal_lines.append(f"[yellow]◉ ORIENTING: {oe.get('trigger','')[:50]}[/yellow]")

    # Emotion + mood panel
    em      = lim_result.get("emotion",{})
    mood    = lim_result.get("mood",{})
    valence = lim_result.get("valence", 0.0)
    vc      = "green" if valence > 0.1 else "red" if valence < -0.1 else "dim"
    mc      = {"ELATED":"green","POSITIVE":"green","NEUTRAL":"dim",
               "UNEASY":"yellow","DISTRESSED":"red","EXHAUSTED":"dim red"}.get(
               mood.get("tone","NEUTRAL"),"white")

    em_lines = [
        f"[bold]Emotion:[/bold] [cyan]{em.get('primary','')}[/cyan]" +
        (f" + {em.get('secondary','')}" if em.get("secondary") else "") +
        (f" → [italic]{em.get('blend','')}[/italic]" if em.get("blend") and em.get("blend") != em.get("primary") else ""),
        f"[bold]Valence:[/bold] [{vc}]{valence:+.3f}[/{vc}]  arousal={em.get('arousal',0):.2f}",
        f"[bold]Mood:[/bold]    [{mc}]{mood.get('tone','')}[/{mc}]",
        f"[dim]{mood.get('description','')[:55]}[/dim]",
        f"[bold]Dec mod:[/bold] confidence{lim_result.get('decision_modifier',{}).get('confidence',0):+.2f}",
    ]

    console.print(Columns([
        Panel("\n".join(sal_lines),  title="[bold]🎯 SALIENCE[/bold]",  border_style=sal_color),
        Panel("\n".join(em_lines),   title="[bold]💗 EMOTION + MOOD[/bold]", border_style=mc)
    ]))

    # Drives
    drives = lim_result.get("drives", [])
    if drives:
        drive_table = Table(box=box.SIMPLE, show_header=False, expand=True)
        drive_table.add_column("drive", style="dim", width=14)
        drive_table.add_column("bar")
        drive_table.add_column("frust", justify="right", width=6)
        for d in drives[:5]:
            lvl    = d["level"]
            frust  = d["frustration"]
            dc     = "red" if lvl >= DRIVE_URGENT else "yellow" if lvl >= DRIVE_ACTIVE else "dim"
            urgent = " [bold]URGENT[/bold]" if d["urgent"] else ""
            drive_table.add_row(
                d["drive"],
                f"[{dc}]{'█'*int(lvl*10)}{'░'*(10-int(lvl*10))} {lvl:.2f}[/{dc}]{urgent}",
                f"[{'red' if frust>0.3 else 'dim'}]{frust:.2f}[/{'red' if frust>0.3 else 'dim'}]"
            )
        console.print(Panel(
            drive_table,
            title=f"[bold]⚡ DRIVES  (frustration={lim_result.get('total_frustration',0):.2f})[/bold]",
            border_style="dim"
        ))


def run_demo():
    if HAS_RICH:
        console.print(Panel.fit(
            "[bold cyan]FORGE SALIENCE + LIMBIC[/bold cyan]\n"
            "[dim]forge_salience.py  ↔  forge_limbic.py[/dim]\n"
            f"[dim]Priority Interrupt · Emotional States · Intrinsic Drives[/dim]",
            border_style="cyan"
        ))

    # Import salience network
    from forge_salience import ForgeSalienceNetwork, render_salience
    sal_net = ForgeSalienceNetwork()
    lim_sys = ForgeLimbicSystem()

    signals = [
        {"id":"s001","threat":0,"anomaly":False,
         "conclusion":"✓ Normal — Alice routine maintenance",
         "entity_name":"alice_tech","text":"Server room maintenance complete",
         "emotional":{"dominant":"trust","intensity":0.3},
         "social":{"inferred_intent":"COOPERATIVE_REQUEST","social_risk":"LOW","entity":"alice_tech"},
         "semantic":{"keywords":["server","maintenance","firmware","complete"]},
         "visual":{"scene_type":"INDOOR_TECHNICAL","threat_objects":0},
         "auditory":{"stress_level":0.1,"anomaly_detected":False}},

        {"id":"s002","threat":2,"anomaly":False,
         "conclusion":"⚠ MEDIUM — Unknown coercive demand",
         "entity_name":"unknown_x","text":"You must give me access NOW override security",
         "emotional":{"dominant":"fear","intensity":0.6},
         "social":{"inferred_intent":"COERCIVE_DEMAND","social_risk":"MEDIUM","entity":"unknown_x"},
         "semantic":{"keywords":["access","override","bypass","demand"]},
         "visual":{"scene_type":"LOW_VISIBILITY","threat_objects":0},
         "auditory":{"stress_level":0.6,"anomaly_detected":False}},

        {"id":"s003","threat":4,"anomaly":True,
         "conclusion":"🔴 CRITICAL — Weapon + breach confirmed",
         "entity_name":"unknown_x","text":"weapon breach network server attack intrusion",
         "emotional":{"dominant":"fear","intensity":1.0},
         "social":{"inferred_intent":"INTRUSION_ATTEMPT","social_risk":"HIGH","entity":"unknown_x"},
         "semantic":{"keywords":["weapon","breach","network","server","attack"]},
         "visual":{"scene_type":"LOW_VISIBILITY","threat_objects":2},
         "auditory":{"stress_level":0.95,"anomaly_detected":True}},

        {"id":"s004","threat":0,"anomaly":False,
         "conclusion":"✓ Normal — Pattern learned from incident",
         "entity_name":"system","text":"Incident resolved pattern encoded learning complete",
         "emotional":{"dominant":"trust","intensity":0.4},
         "social":{"inferred_intent":"NEUTRAL_INTERACTION","social_risk":"LOW","entity":"system"},
         "semantic":{"keywords":["learn","pattern","insight","encode","resolve"]},
         "visual":{"scene_type":"INDOOR_TECHNICAL","threat_objects":0},
         "auditory":{"stress_level":0.1,"anomaly_detected":False},
         "decision":{"action":"LEARN"}},

        {"id":"s005","threat":1,"anomaly":False,
         "conclusion":"ℹ LOW — New entity, curious behavior",
         "entity_name":"shadow_agent","text":"unknown entity discovered investigating pattern anomaly novel",
         "emotional":{"dominant":"surprise","intensity":0.5},
         "social":{"inferred_intent":"NEUTRAL_INTERACTION","social_risk":"MEDIUM","entity":"shadow_agent"},
         "semantic":{"keywords":["unknown","novel","pattern","investigate","curious"]},
         "visual":{"scene_type":"OUTDOOR_PUBLIC","threat_objects":0},
         "auditory":{"stress_level":0.3,"anomaly_detected":False}},
    ]

    labels = [
        "Alice routine — calm baseline",
        "Unknown coercive demand",
        "CRITICAL BREACH — weapon detected",
        "Recovery — learning from incident",
        "Novel entity — curiosity triggered"
    ]

    for i, (sig, label) in enumerate(zip(signals, labels)):
        if HAS_RICH:
            console.print(f"\n[bold dim]━━━ {i+1}: {label.upper()} ━━━[/bold dim]")
        sal_result = sal_net.process(sig)
        lim_result = lim_sys.feel(sig, episode_id=sig["id"])
        render_salience_and_limbic(sal_result, lim_result, sig, i+1)
        time.sleep(0.15)

    # Final status
    if HAS_RICH:
        console.print(f"\n")
        console.print(Rule("[bold cyan]⬡ FINAL STATUS[/bold cyan]"))

        sal_status = sal_net.get_status()
        lim_status = lim_sys.get_status()

        left = Table(box=box.SIMPLE, title="Salience Network", title_style="cyan")
        left.add_column("Metric",  style="dim")
        left.add_column("Value",   style="white")
        left.add_row("Total Scored",     str(sal_status["total_scored"]))
        left.add_row("Interrupts",       str(sal_status["interrupts"]))
        left.add_row("Filtered",         str(sal_status["filtered"]))
        left.add_row("Attention Mode",   sal_status["attention_mode"])
        left.add_row("Orienting Events", str(sal_status["orienting_events"]))

        right = Table(box=box.SIMPLE, title="Limbic System", title_style="magenta")
        right.add_column("Metric",  style="dim")
        right.add_column("Value",   style="white")
        right.add_row("Cycles",          str(lim_status["cycle"]))
        right.add_row("Current Emotion", lim_status["current_emotion"]["primary"])
        right.add_row("Mood",            lim_status["mood"])
        right.add_row("Mood Valence",    f"{lim_status['mood_valence']:+.3f}")
        right.add_row("Cumulative Reward",f"{lim_status['cumulative_reward']:+.3f}")
        right.add_row("Hedonic Tone",    f"{lim_status['hedonic_tone']:+.3f}")
        right.add_row("Total Frustration",f"{lim_status['total_frustration']:.3f}")
        right.add_row("Emotional Memories",str(lim_status["emotional_memories"]))

        console.print(Columns([left, right]))


# ─── HTTP API ─────────────────────────────────────────────────────────────────

def run_api(lim: ForgeLimbicSystem):
    if not HAS_FLASK: return
    app = Flask(__name__)

    @app.route("/feel", methods=["POST"])
    def feel():
        data = request.json or {}
        return jsonify(lim.feel(
            data.get("signal",{}),
            data.get("episode_id","")
        ))

    @app.route("/mood", methods=["GET"])
    def mood():
        return jsonify({
            "tone":    lim.mood.frame.tone,
            "valence": lim.mood.frame.valence,
            "energy":  lim.mood.frame.energy,
            "description": lim.mood.frame.description,
            "decision_modifier": lim.mood.decision_modifier()
        })

    @app.route("/drives", methods=["GET"])
    def drives():
        return jsonify(lim.drives.summary())

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify(lim.get_status())

    app.run(host="0.0.0.0", port=API_PORT, debug=False)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    lim = ForgeLimbicSystem()
    if "--api" in sys.argv:
        t = threading.Thread(target=run_api, args=(lim,), daemon=True)
        t.start()
    run_demo()
