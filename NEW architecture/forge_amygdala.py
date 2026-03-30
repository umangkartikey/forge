"""
FORGE Amygdala — forge_amygdala.py
====================================
AI analog of the brain's amygdala.

The amygdala is the brain's alarm system — the fastest processor
in the entire neural hierarchy. It receives sensory input BEFORE
the cortex and generates an emotional response in ~8ms.

Key insight: The amygdala doesn't think. It REACTS.
While the cortex is still figuring out what something is,
the amygdala has already tagged it as safe or dangerous
and begun preparing a response.

Four core functions:

  1. FAST THREAT TAGGING (subcortical shortcut)
     Threat signals bypass the full pipeline.
     The amygdala responds in ~8ms — before temporal, prefrontal,
     or hippocampus have even processed the input.
     This is why you flinch before you know why.

  2. FEAR MEMORY (conditioned associations)
     Once an entity/pattern causes fear, it is permanently tagged.
     Future encounters trigger the fear response automatically.
     Strength of fear tag decays with repeated safe exposure
     (extinction learning) but NEVER fully disappears.

  3. THREAT GENERALIZATION
     Similar stimuli to feared objects also get flagged.
     Entity unknown_x caused threat=4 →
     Future entities with similar patterns get elevated threat.
     This is the neural basis of learned caution.

  4. EMOTIONAL HIJACKING
     At extreme threat (4) the amygdala can OVERRIDE the
     entire cognitive pipeline — bypassing prefrontal,
     hippocampus, swarm — and drive a direct response.
     "Amygdala hijack" — pure survival mode.

Architecture:
  ThreatDetector       → subcortical fast pathway (~8ms)
  FearMemory           → conditioned fear associations
  ExtinctionEngine     → fear fades with safe exposure
  ThreatGeneralizer    → similar patterns inherit fear tags
  EmotionalHijack      → override all modules at extreme threat
  AmygdalaOutput       → modulates norepinephrine + salience
  SafetyLearner        → positive safety memories (counterpart)
"""

import json
import time
import uuid
import sqlite3
import threading
import math
import hashlib
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

DB_PATH  = "forge_amygdala.db"
API_PORT = 7792
VERSION  = "1.0.0"

# Timing
SUBCORTICAL_LATENCY_MS = 8.0    # fast path — before cortex
CORTICAL_LATENCY_MS    = 40.0   # slow path — after cortex confirms

# Fear dynamics
FEAR_ACQUISITION_RATE  = 0.35   # how fast fear is learned
FEAR_EXTINCTION_RATE   = 0.04   # how fast fear fades with safe exposure
FEAR_MINIMUM           = 0.05   # fear never fully disappears
FEAR_HIJACK_THRESHOLD  = 0.85   # fear score to trigger hijack
GENERALIZATION_RADIUS  = 0.30   # how similar to inherit fear

# Safety learning
SAFETY_ACQUISITION_RATE= 0.15   # slower to trust than to fear
SAFETY_MAX             = 0.90   # safety asymptote

# Norepinephrine amplification
NE_FEAR_BOOST          = 0.35   # fear → NE spike
NE_SAFE_SUPPRESSION    = 0.10   # safety → NE reduction

console = Console() if HAS_RICH else None

# ─── Enums ────────────────────────────────────────────────────────────────────

class AmygdalaResponse(Enum):
    HIJACK    = "HIJACK"     # extreme fear — override everything
    ALARM     = "ALARM"      # high fear — urgent flag
    CAUTION   = "CAUTION"    # moderate fear — elevated alert
    NEUTRAL   = "NEUTRAL"    # no strong association
    SAFE      = "SAFE"       # positive safety association
    RELIEF    = "RELIEF"     # expected danger that didn't materialize

class FearTag(Enum):
    STRONG    = "STRONG"     # fear >= 0.7
    MODERATE  = "MODERATE"   # fear >= 0.4
    WEAK      = "WEAK"       # fear >= 0.15
    EXTINGUISHED = "EXTINGUISHED"  # fear < 0.15 but memory exists
    NONE      = "NONE"       # no fear memory

class LearningType(Enum):
    ACQUISITION  = "ACQUISITION"   # new fear learned
    REINFORCEMENT= "REINFORCEMENT" # existing fear strengthened
    EXTINCTION   = "EXTINCTION"    # fear fading with safe exposure
    GENERALIZED  = "GENERALIZED"   # fear inherited from similar
    SAFETY       = "SAFETY"        # safety association formed

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class FearMemory:
    """A conditioned fear association."""
    id:            str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    pattern:       str   = ""      # entity name, keyword, or pattern hash
    pattern_type:  str   = "entity"# entity/keyword/context/scene
    fear_strength: float = 0.0     # 0-1
    safety_strength:float= 0.0     # 0-1 (counterpart)
    acquisition_date: str= field(default_factory=lambda: datetime.now().isoformat())
    last_triggered:str   = field(default_factory=lambda: datetime.now().isoformat())
    trigger_count: int   = 0
    safe_exposures:int   = 0
    peak_threat:   int   = 0
    tag:           str   = FearTag.NONE.value
    generalized_from: str= ""      # if inherited from another memory
    ne_boost:      float = 0.0     # norepinephrine boost this memory causes
    notes:         list  = field(default_factory=list)

@dataclass
class AmygdalaActivation:
    """One activation event of the amygdala."""
    id:            str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:     str   = field(default_factory=lambda: datetime.now().isoformat())
    trigger:       str   = ""
    response:      str   = AmygdalaResponse.NEUTRAL.value
    fear_score:    float = 0.0
    safety_score:  float = 0.0
    latency_ms:    float = SUBCORTICAL_LATENCY_MS
    hijack:        bool  = False
    ne_output:     float = 0.0
    salience_boost:float = 0.0
    memories_hit:  list  = field(default_factory=list)
    learning:      str   = LearningType.ACQUISITION.value
    threat_level:  int   = 0

@dataclass
class ExtinctionTrial:
    """A safe exposure trial that reduces fear."""
    pattern:       str   = ""
    fear_before:   float = 0.0
    fear_after:    float = 0.0
    safe_count:    int   = 0
    fully_extinguished: bool = False

# ─── Database ─────────────────────────────────────────────────────────────────

class AmygdalaDB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init()

    def _init(self):
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS fear_memories (
                    id TEXT PRIMARY KEY, pattern TEXT,
                    pattern_type TEXT, fear_strength REAL,
                    safety_strength REAL, acquisition_date TEXT,
                    last_triggered TEXT, trigger_count INTEGER,
                    safe_exposures INTEGER, peak_threat INTEGER,
                    tag TEXT, generalized_from TEXT,
                    ne_boost REAL, notes TEXT
                );
                CREATE TABLE IF NOT EXISTS activations (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    trigger TEXT, response TEXT, fear_score REAL,
                    safety_score REAL, latency_ms REAL, hijack INTEGER,
                    ne_output REAL, salience_boost REAL,
                    memories_hit TEXT, learning TEXT, threat_level INTEGER
                );
                CREATE TABLE IF NOT EXISTS extinction_trials (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    pattern TEXT, fear_before REAL, fear_after REAL,
                    safe_count INTEGER, fully_extinguished INTEGER
                );
                CREATE TABLE IF NOT EXISTS generalization_log (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    source_pattern TEXT, generalized_to TEXT,
                    similarity REAL, inherited_fear REAL
                );
            """)
            self.conn.commit()

    def save_memory(self, m: FearMemory):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO fear_memories VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (m.id, m.pattern, m.pattern_type,
                  m.fear_strength, m.safety_strength,
                  m.acquisition_date, m.last_triggered,
                  m.trigger_count, m.safe_exposures,
                  m.peak_threat, m.tag, m.generalized_from,
                  m.ne_boost, json.dumps(m.notes)))
            self.conn.commit()

    def save_activation(self, a: AmygdalaActivation):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO activations VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (a.id, a.timestamp, a.trigger, a.response,
                  a.fear_score, a.safety_score, a.latency_ms,
                  int(a.hijack), a.ne_output, a.salience_boost,
                  json.dumps(a.memories_hit), a.learning, a.threat_level))
            self.conn.commit()

    def save_extinction(self, e: ExtinctionTrial):
        with self.lock:
            self.conn.execute("""
                INSERT INTO extinction_trials VALUES (?,?,?,?,?,?,?)
            """, (str(uuid.uuid4())[:8], datetime.now().isoformat(),
                  e.pattern, e.fear_before, e.fear_after,
                  e.safe_count, int(e.fully_extinguished)))
            self.conn.commit()

    def log_generalization(self, source: str, target: str,
                           similarity: float, fear: float):
        with self.lock:
            self.conn.execute("""
                INSERT INTO generalization_log VALUES (?,?,?,?,?,?)
            """, (str(uuid.uuid4())[:8], datetime.now().isoformat(),
                  source, target, similarity, fear))
            self.conn.commit()

    def get_memories(self, min_fear=0.0):
        with self.lock:
            return self.conn.execute("""
                SELECT pattern, pattern_type, fear_strength,
                       safety_strength, trigger_count, safe_exposures,
                       peak_threat, tag, ne_boost
                FROM fear_memories WHERE fear_strength >= ?
                ORDER BY fear_strength DESC
            """, (min_fear,)).fetchall()

    def get_recent_activations(self, limit=20):
        with self.lock:
            return self.conn.execute("""
                SELECT timestamp, trigger, response, fear_score,
                       hijack, ne_output, learning, threat_level
                FROM activations ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()


# ─── Pattern Extractor ────────────────────────────────────────────────────────

class PatternExtractor:
    """
    Extracts recognizable patterns from signals for amygdala processing.
    The amygdala learns associations to patterns, not full contexts.
    """

    def extract(self, signal: dict) -> list[tuple[str, str]]:
        """Returns list of (pattern, pattern_type) tuples."""
        patterns = []

        # Entity name
        entity = signal.get("entity_name","")
        if entity and entity != "unknown":
            patterns.append((entity, "entity"))

        # Social entity
        social = signal.get("social",{}) or {}
        if isinstance(social, dict):
            ent = social.get("entity","")
            if ent and ent != entity and ent != "unknown":
                patterns.append((ent, "entity"))
            intent = social.get("inferred_intent","")
            if intent:
                patterns.append((intent, "intent"))

        # Visual patterns
        visual = signal.get("visual",{}) or {}
        if isinstance(visual, dict):
            scene = visual.get("scene_type","")
            if scene and scene not in ["UNKNOWN",""]:
                patterns.append((scene, "scene"))
            if visual.get("threat_objects",0) > 0:
                patterns.append(("WEAPON_DETECTED","keyword"))

        # Semantic keywords
        semantic = signal.get("semantic",{}) or {}
        if isinstance(semantic, dict):
            kws = semantic.get("keywords",[])
            threat_kws = ["weapon","breach","intrusion","attack","hack","bypass"]
            for kw in kws[:5]:
                if kw in threat_kws:
                    patterns.append((kw, "keyword"))

        # Context hash for generalization
        ctx_raw = f"{signal.get('threat',0)}:{intent if 'intent' in locals() else ''}"
        ctx_hash= hashlib.md5(ctx_raw.encode()).hexdigest()[:8]
        patterns.append((ctx_hash, "context"))

        return patterns

    def similarity(self, p1: str, p2: str) -> float:
        """Compute similarity between two patterns."""
        if p1 == p2: return 1.0
        # Character-level similarity
        set1 = set(p1.lower())
        set2 = set(p2.lower())
        if not set1 or not set2: return 0.0
        intersection = len(set1 & set2)
        union        = len(set1 | set2)
        return round(intersection / union, 3)


# ─── Threat Detector ─────────────────────────────────────────────────────────

class ThreatDetector:
    """
    The subcortical fast pathway.
    Processes threat signals in ~8ms — before cortex involvement.

    Two pathways:
      LOW ROAD  (8ms)  — thalamus → amygdala direct
                         crude, fast, sometimes wrong
                         fires on rough threat pattern match

      HIGH ROAD (40ms) — thalamus → cortex → amygdala
                         precise, slow, usually right
                         fires after cortical processing confirms
    """

    def detect(self, signal: dict,
               fear_memories: dict[str, FearMemory],
               patterns: list[tuple]) -> tuple[float, float, bool]:
        """
        Returns (fear_score, safety_score, low_road_fired).
        fear_score: 0-1
        safety_score: 0-1
        low_road_fired: True if subcortical shortcut used
        """
        threat       = signal.get("threat", 0)
        anomaly      = signal.get("anomaly", False)
        low_road     = False
        fear_score   = 0.0
        safety_score = 0.0
        memories_hit = []

        # LOW ROAD — crude fast detection
        if threat >= 3 or (anomaly and threat >= 2):
            # Immediate fear response based on raw threat level
            fear_score = min(1.0, threat / 4.0 + 0.15)
            low_road   = True

        # Check fear memories for each pattern
        for pattern, ptype in patterns:
            if pattern in fear_memories:
                mem = fear_memories[pattern]
                # Fear memory amplifies fear score
                fear_score   = max(fear_score, mem.fear_strength * 0.8)
                safety_score = max(safety_score, mem.safety_strength)
                memories_hit.append(pattern)

        # HIGH ROAD — precise detection via cortical confirmation
        # (adds context-aware adjustments)
        social = signal.get("social_context", {}) or {}
        risk   = social.get("risk_label", "")
        if risk == "HIGH":
            fear_score = min(1.0, fear_score + 0.20)
        elif risk == "LOW":
            safety_score = min(1.0, safety_score + 0.15)

        # Visual threat objects strongly activate amygdala
        visual = signal.get("visual", {}) or {}
        if isinstance(visual, dict):
            v_threats = visual.get("threat_objects", 0)
            if v_threats > 0:
                fear_score = min(1.0, fear_score + v_threats * 0.20)
                low_road = True

        return round(fear_score, 3), round(safety_score, 3), low_road


# ─── Fear Memory System ───────────────────────────────────────────────────────

class FearMemorySystem:
    """
    Stores and retrieves conditioned fear associations.
    The amygdala's long-term emotional memory.

    Key property: fear memory is PERSISTENT.
    Even after extinction, the neural trace remains.
    This is why trauma can resurface years later.
    """

    def __init__(self, db: AmygdalaDB):
        self.db       = db
        self.memories: dict[str, FearMemory] = {}

    def acquire(self, pattern: str, ptype: str,
                threat: int, fear_score: float) -> FearMemory:
        """Learn or strengthen a fear association."""
        if pattern in self.memories:
            mem = self.memories[pattern]
            learning = LearningType.REINFORCEMENT

            # Strengthen existing fear
            delta = FEAR_ACQUISITION_RATE * (1.0 - mem.fear_strength) * (threat/4.0)
            mem.fear_strength = round(min(1.0, mem.fear_strength + delta), 4)
            mem.peak_threat   = max(mem.peak_threat, threat)
            mem.trigger_count += 1
            mem.last_triggered= datetime.now().isoformat()
        else:
            learning = LearningType.ACQUISITION
            initial_fear = round(min(1.0, fear_score * FEAR_ACQUISITION_RATE * 2.5), 4)
            mem = FearMemory(
                pattern        = pattern,
                pattern_type   = ptype,
                fear_strength  = initial_fear,
                acquisition_date = datetime.now().isoformat(),
                peak_threat    = threat,
                trigger_count  = 1,
                ne_boost       = round(initial_fear * NE_FEAR_BOOST, 4),
            )
            self.memories[pattern] = mem

        # Update tag
        mem.tag = self._compute_tag(mem.fear_strength)
        mem.ne_boost = round(mem.fear_strength * NE_FEAR_BOOST, 4)
        self.db.save_memory(mem)
        return mem

    def acquire_safety(self, pattern: str, ptype: str) -> FearMemory:
        """Learn a safety association (positive counterpart to fear)."""
        if pattern not in self.memories:
            mem = FearMemory(
                pattern       = pattern,
                pattern_type  = ptype,
                fear_strength = 0.0,
                safety_strength=SAFETY_ACQUISITION_RATE,
            )
            self.memories[pattern] = mem
        else:
            mem = self.memories[pattern]

        mem.safety_strength = round(
            min(SAFETY_MAX, mem.safety_strength + SAFETY_ACQUISITION_RATE * 0.5), 4
        )
        mem.safe_exposures += 1
        mem.tag = self._compute_tag(mem.fear_strength)
        self.db.save_memory(mem)
        return mem

    def _compute_tag(self, fear: float) -> str:
        if fear >= 0.7:   return FearTag.STRONG.value
        if fear >= 0.4:   return FearTag.MODERATE.value
        if fear >= 0.15:  return FearTag.WEAK.value
        if fear > 0:      return FearTag.EXTINGUISHED.value
        return FearTag.NONE.value

    def get(self, pattern: str) -> Optional[FearMemory]:
        return self.memories.get(pattern)

    def strongest(self, n=5) -> list[FearMemory]:
        return sorted(self.memories.values(),
                     key=lambda m: m.fear_strength, reverse=True)[:n]


# ─── Extinction Engine ────────────────────────────────────────────────────────

class ExtinctionEngine:
    """
    Fear fades with repeated safe exposure.
    This is extinction learning — the basis of exposure therapy.

    Critical property: extinction doesn't ERASE the fear memory.
    It creates a new SAFETY memory that INHIBITS the fear response.
    The original fear trace remains — which is why:
    - Fear can return after stress (spontaneous recovery)
    - Fear returns in new contexts (renewal)
    - Fear returns after time (forgetting the safety trace)
    """

    def __init__(self, db: AmygdalaDB):
        self.db = db
        self.extinction_log: list[ExtinctionTrial] = []

    def process_safe_exposure(self, pattern: str,
                               memories: dict[str, FearMemory]) -> Optional[ExtinctionTrial]:
        """
        Reduce fear for a pattern after safe exposure.
        Returns ExtinctionTrial if fear was reduced.
        """
        if pattern not in memories:
            return None

        mem = memories[pattern]
        if mem.fear_strength < FEAR_MINIMUM:
            return None  # already extinguished

        trial = ExtinctionTrial(
            pattern    = pattern,
            fear_before= mem.fear_strength,
            safe_count = mem.safe_exposures + 1
        )

        # Fear reduction — slower for stronger fears
        reduction = FEAR_EXTINCTION_RATE * mem.fear_strength
        # Resistance to extinction increases with trigger count (traumatic memories)
        resistance = min(0.7, mem.trigger_count * 0.05)
        actual_reduction = reduction * (1.0 - resistance)

        mem.fear_strength = round(
            max(FEAR_MINIMUM, mem.fear_strength - actual_reduction), 4
        )
        mem.safe_exposures += 1
        mem.safety_strength= round(
            min(SAFETY_MAX, mem.safety_strength + SAFETY_ACQUISITION_RATE), 4
        )
        mem.tag = FearMemory().tag if False else self._tag(mem.fear_strength)
        mem.last_triggered = datetime.now().isoformat()

        trial.fear_after        = mem.fear_strength
        trial.fully_extinguished= mem.fear_strength <= FEAR_MINIMUM
        self.db.save_extinction(trial)
        self.db.save_memory(mem)
        self.extinction_log.append(trial)
        return trial

    def _tag(self, fear: float) -> str:
        if fear >= 0.7:  return FearTag.STRONG.value
        if fear >= 0.4:  return FearTag.MODERATE.value
        if fear >= 0.15: return FearTag.WEAK.value
        return FearTag.EXTINGUISHED.value

    def spontaneous_recovery(self, memories: dict[str, FearMemory]):
        """
        After a long gap (stress, new context), extinguished fears
        partially recover. This models trauma resurfacing.
        """
        for mem in memories.values():
            if mem.fear_strength < 0.3 and mem.trigger_count > 3:
                # Partial recovery proportional to original fear
                recovery = (mem.peak_threat / 4.0) * 0.05
                mem.fear_strength = round(
                    min(0.5, mem.fear_strength + recovery), 4
                )
                mem.tag = self._tag(mem.fear_strength)


# ─── Threat Generalizer ───────────────────────────────────────────────────────

class ThreatGeneralizer:
    """
    Fear generalizes to similar stimuli.
    Entity X caused fear=0.7 →
    Entity Y (similar name/context) inherits fear=0.7 * similarity

    This is the neural basis of learned caution and prejudice.
    It's adaptive (generalize threat to similar threats)
    but can be maladaptive (fear things that aren't actually dangerous).
    """

    def __init__(self, db: AmygdalaDB, extractor: PatternExtractor):
        self.db        = db
        self.extractor = extractor

    def generalize(self, new_pattern: str, ptype: str,
                   memories: dict[str, FearMemory]) -> Optional[float]:
        """
        Check if new_pattern should inherit fear from similar memories.
        Returns inherited fear level or None.
        """
        best_similarity = 0.0
        best_source     = None
        best_fear       = 0.0

        for pattern, mem in memories.items():
            if pattern == new_pattern: continue
            if mem.fear_strength < 0.3: continue  # don't generalize weak fears
            if ptype != mem.pattern_type: continue  # only generalize same type

            sim = self.extractor.similarity(new_pattern, pattern)
            if sim > GENERALIZATION_RADIUS and sim > best_similarity:
                best_similarity = sim
                best_source     = pattern
                best_fear       = mem.fear_strength

        if best_source and best_fear > 0:
            inherited = round(best_fear * best_similarity * 0.6, 4)
            self.db.log_generalization(
                best_source, new_pattern, best_similarity, inherited
            )
            return inherited

        return None


# ─── Emotional Hijack ─────────────────────────────────────────────────────────

class EmotionalHijack:
    """
    At extreme fear, the amygdala OVERRIDES the cognitive pipeline.

    In humans: rage, panic, freezing — all caused by amygdala hijack.
    The prefrontal cortex goes offline. Behavior is purely reactive.

    In FORGE: when fear_score >= FEAR_HIJACK_THRESHOLD:
    - All deliberate processing suspended
    - Only survival-critical modules remain active
    - Response is pure reflex/habit
    - This state lasts until fear score drops below threshold

    Recovery from hijack requires:
    - Threat level dropping
    - Fear score reducing
    - Explicit cortical override (prefrontal inhibition)
    """

    def __init__(self):
        self.active       = False
        self.hijack_count = 0
        self.hijack_start = None
        self.recovery_threshold = FEAR_HIJACK_THRESHOLD - 0.15

    def check(self, fear_score: float,
              threat: int) -> tuple[bool, str]:
        """Returns (hijack_active, reason)."""
        if fear_score >= FEAR_HIJACK_THRESHOLD or threat >= 4:
            if not self.active:
                self.active       = True
                self.hijack_count += 1
                self.hijack_start = datetime.now()
            return True, f"fear={fear_score:.2f} threat={threat}"

        if self.active and fear_score < self.recovery_threshold and threat <= 1:
            self.active = False
            duration = (datetime.now() - self.hijack_start).total_seconds() if self.hijack_start else 0
            return False, f"recovered after {duration:.1f}s"

        return self.active, "sustained"

    def duration_secs(self) -> float:
        if not self.active or not self.hijack_start: return 0.0
        return round((datetime.now() - self.hijack_start).total_seconds(), 1)

    def modules_suspended(self) -> list[str]:
        """Which modules are suspended during hijack."""
        if not self.active: return []
        return ["prefrontal","hippocampus","dmn","swarm","bridge"]

    def modules_active(self) -> list[str]:
        """Which modules remain active during hijack."""
        return ["salience","temporal","sensorimotor","basal_ganglia",
                "neuromodulator","limbic","thalamus"]


# ─── Safety Learner ───────────────────────────────────────────────────────────

class SafetyLearner:
    """
    Positive counterpart to fear learning.
    Builds safety associations with consistently safe entities/contexts.
    High safety → reduced NE, reduced salience sensitivity,
                  increased trust threshold, positive affect.
    """

    def __init__(self):
        self.safety_index: dict[str, float] = {}

    def update(self, patterns: list[tuple],
               threat: int, fear_memories: FearMemorySystem):
        """Update safety associations for safe encounters."""
        if threat > 0: return  # not a safe encounter

        for pattern, ptype in patterns:
            if ptype == "entity":
                # Build safety for consistently safe entities
                current = self.safety_index.get(pattern, 0.0)
                self.safety_index[pattern] = round(
                    min(SAFETY_MAX, current + SAFETY_ACQUISITION_RATE * 0.3), 4
                )
                # Also update fear memory system
                fear_memories.acquire_safety(pattern, ptype)

    def get_safety(self, pattern: str) -> float:
        return self.safety_index.get(pattern, 0.0)

    def highest_safety(self, n=3) -> list[tuple]:
        return sorted(self.safety_index.items(),
                     key=lambda x: x[1], reverse=True)[:n]


# ─── Amygdala Output ─────────────────────────────────────────────────────────

class AmygdalaOutput:
    """
    Translates amygdala activation into downstream effects.
    The amygdala modulates:
      - Norepinephrine (via locus coeruleus)
      - Salience threshold (via thalamus)
      - Hippocampus encoding strength (fear memories stick)
      - Cortisol release (via HPA axis)
      - Heart rate / arousal analog
    """

    def compute(self, fear_score: float,
                safety_score: float,
                hijack: bool,
                memories: list[FearMemory]) -> dict:

        # Norepinephrine output
        ne_from_fear   = fear_score * NE_FEAR_BOOST
        ne_from_safety = safety_score * NE_SAFE_SUPPRESSION
        ne_from_mem    = max((m.ne_boost for m in memories), default=0.0)
        ne_output      = round(min(1.0, ne_from_fear + ne_from_mem - ne_from_safety), 4)

        # Salience boost — fear makes everything more salient
        salience_boost = round(min(0.5, fear_score * 0.4), 4)

        # Hippocampus encoding boost — fear strengthens memory
        memory_boost   = round(min(1.5, 1.0 + fear_score * 0.6), 4)

        # Cortisol signal
        cortisol_signal= round(fear_score * 0.3, 4) if fear_score > 0.3 else 0.0

        # Emotional tone output
        if hijack:              tone = "HIJACKED"
        elif fear_score > 0.6:  tone = "FEARFUL"
        elif fear_score > 0.3:  tone = "ANXIOUS"
        elif safety_score > 0.5:tone = "SECURE"
        elif safety_score > 0.2:tone = "CALM"
        else:                   tone = "NEUTRAL"

        return {
            "ne_output":         ne_output,
            "salience_boost":    salience_boost,
            "memory_boost":      memory_boost,
            "cortisol_signal":   cortisol_signal,
            "emotional_tone":    tone,
            "hijack_active":     hijack,
            "modules_suspended": [] if not hijack else ["prefrontal","hippocampus","dmn","swarm"],
        }


# ─── FORGE Amygdala ───────────────────────────────────────────────────────────

class ForgeAmygdala:
    def __init__(self):
        self.db          = AmygdalaDB()
        self.extractor   = PatternExtractor()
        self.detector    = ThreatDetector()
        self.fear_memory = FearMemorySystem(self.db)
        self.extinction  = ExtinctionEngine(self.db)
        self.generalizer = ThreatGeneralizer(self.db, self.extractor)
        self.hijack      = EmotionalHijack()
        self.safety      = SafetyLearner()
        self.output_calc = AmygdalaOutput()
        self.cycle       = 0
        self.total_hijacks   = 0
        self.total_alarms    = 0
        self.total_extinctions=0

    def process(self, signal: dict) -> dict:
        """
        Full amygdala processing pipeline.
        Returns activation result including fear score,
        NE output, hijack status, and learning events.
        """
        t0         = time.time()
        self.cycle += 1
        threat     = signal.get("threat", 0)

        # 1. Extract patterns from signal
        patterns = self.extractor.extract(signal)

        # 2. Fast threat detection (subcortical + cortical)
        fear_score, safety_score, low_road = self.detector.detect(
            signal, self.fear_memory.memories, patterns
        )

        # 3. Generalization — inherit fear from similar patterns
        generalized_boost = 0.0
        for pattern, ptype in patterns:
            if pattern not in self.fear_memory.memories:
                inherited = self.generalizer.generalize(
                    pattern, ptype, self.fear_memory.memories
                )
                if inherited:
                    generalized_boost = max(generalized_boost, inherited)

        fear_score = round(min(1.0, fear_score + generalized_boost), 4)

        # 4. Fear memory acquisition or extinction
        learning_events = []
        memories_hit    = []
        if threat >= 2:
            # Acquire fear for threatening patterns
            for pattern, ptype in patterns:
                if ptype in ["entity","keyword","intent"]:
                    mem = self.fear_memory.acquire(pattern, ptype, threat, fear_score)
                    memories_hit.append(pattern)
                    learning_events.append({
                        "type":    LearningType.ACQUISITION.value,
                        "pattern": pattern,
                        "fear":    mem.fear_strength
                    })
        elif threat == 0:
            # Safe exposure — extinction processing
            for pattern, ptype in patterns:
                if pattern in self.fear_memory.memories:
                    trial = self.extinction.process_safe_exposure(
                        pattern, self.fear_memory.memories
                    )
                    if trial:
                        self.total_extinctions += 1
                        learning_events.append({
                            "type":       LearningType.EXTINCTION.value,
                            "pattern":    pattern,
                            "fear_before":trial.fear_before,
                            "fear_after": trial.fear_after
                        })
                        memories_hit.append(pattern)

            # Safety learning
            self.safety.update(patterns, threat, self.fear_memory)

        # 5. Hijack check
        hijack_active, hijack_reason = self.hijack.check(fear_score, threat)
        if hijack_active:
            self.total_hijacks += 1

        # 6. Determine response type
        if hijack_active:
            response = AmygdalaResponse.HIJACK
            self.total_hijacks = max(self.total_hijacks - 1,0) + 1  # deduplicate
        elif fear_score > 0.6:
            response = AmygdalaResponse.ALARM
            self.total_alarms += 1
        elif fear_score > 0.3:
            response = AmygdalaResponse.CAUTION
        elif safety_score > 0.5:
            response = AmygdalaResponse.SAFE
        elif safety_score > 0.2 and fear_score < 0.1:
            response = AmygdalaResponse.NEUTRAL
        else:
            response = AmygdalaResponse.NEUTRAL

        # 7. Compute output effects
        hit_memories = [self.fear_memory.memories[p]
                        for p in memories_hit
                        if p in self.fear_memory.memories]
        output = self.output_calc.compute(
            fear_score, safety_score, hijack_active, hit_memories
        )

        # 8. Determine latency
        latency = SUBCORTICAL_LATENCY_MS if low_road else CORTICAL_LATENCY_MS
        latency += (time.time()-t0) * 1000

        # 9. Save activation
        activation = AmygdalaActivation(
            trigger       = self.extractor.extract(signal)[0][0] if patterns else "unknown",
            response      = response.value,
            fear_score    = fear_score,
            safety_score  = safety_score,
            latency_ms    = round(latency, 2),
            hijack        = hijack_active,
            ne_output     = output["ne_output"],
            salience_boost= output["salience_boost"],
            memories_hit  = memories_hit,
            learning      = learning_events[0]["type"] if learning_events else LearningType.ACQUISITION.value,
            threat_level  = threat
        )
        self.db.save_activation(activation)

        return {
            "cycle":             self.cycle,
            "response":          response.value,
            "fear_score":        fear_score,
            "safety_score":      safety_score,
            "hijack":            hijack_active,
            "hijack_reason":     hijack_reason if hijack_active else "",
            "hijack_duration_secs": self.hijack.duration_secs(),
            "modules_suspended": self.hijack.modules_suspended(),
            "low_road_used":     low_road,
            "latency_ms":        round(latency, 2),
            "memories_hit":      memories_hit,
            "learning_events":   learning_events,
            "generalized_boost": round(generalized_boost, 4),
            "output":            output,
            "patterns_extracted":[(p,t) for p,t in patterns[:5]],
            "total_fear_memories":len(self.fear_memory.memories),
        }

    def get_fear_profile(self, pattern: str) -> dict:
        """Get the complete fear profile for an entity/pattern."""
        mem = self.fear_memory.get(pattern)
        if not mem:
            return {"pattern":pattern,"known":False}
        return {
            "pattern":      mem.pattern,
            "known":        True,
            "fear":         mem.fear_strength,
            "safety":       mem.safety_strength,
            "tag":          mem.tag,
            "triggers":     mem.trigger_count,
            "safe_exposures":mem.safe_exposures,
            "peak_threat":  mem.peak_threat,
            "ne_boost":     mem.ne_boost,
        }

    def get_status(self) -> dict:
        memories = self.fear_memory.memories
        return {
            "version":           VERSION,
            "cycle":             self.cycle,
            "total_hijacks":     self.total_hijacks,
            "total_alarms":      self.total_alarms,
            "total_extinctions": self.total_extinctions,
            "fear_memories":     len(memories),
            "hijack_active":     self.hijack.active,
            "hijack_count":      self.hijack.hijack_count,
            "strongest_fears":   [
                {"pattern":m.pattern,"fear":m.fear_strength,
                 "tag":m.tag,"triggers":m.trigger_count}
                for m in self.fear_memory.strongest(5)
            ],
            "safety_index":      dict(list(
                sorted(self.safety.safety_index.items(),
                       key=lambda x: x[1], reverse=True)[:5]
            )),
            "prediction_accuracy": self.total_extinctions / max(self.cycle,1)
        }


# ─── Rich UI ──────────────────────────────────────────────────────────────────

RESPONSE_COLORS = {
    "HIJACK":  "bright_red",
    "ALARM":   "red",
    "CAUTION": "yellow",
    "NEUTRAL": "dim",
    "SAFE":    "green",
    "RELIEF":  "cyan",
}

FEAR_TAG_COLORS = {
    "STRONG":       "bright_red",
    "MODERATE":     "red",
    "WEAK":         "yellow",
    "EXTINGUISHED": "dim",
    "NONE":         "green",
}

def render_amygdala(result: dict, signal: dict, idx: int):
    if not HAS_RICH: return

    response = result["response"]
    rc       = RESPONSE_COLORS.get(response,"white")
    fear     = result["fear_score"]
    safety   = result["safety_score"]
    hijack   = result["hijack"]
    threat   = signal.get("threat",0)
    tc       = {0:"green",1:"blue",2:"yellow",3:"red",4:"bright_red"}.get(threat,"white")

    console.print(Rule(
        f"[bold cyan]⬡ AMYGDALA[/bold cyan]  "
        f"[dim]#{idx}[/dim]  "
        f"[{rc}]{response}[/{rc}]  "
        f"[{tc}]T={threat}[/{tc}]  "
        f"{'[bold bright_red]⚡ HIJACK[/bold bright_red]  ' if hijack else ''}"
        f"[dim]{result['latency_ms']:.1f}ms "
        f"({'LOW ROAD' if result['low_road_used'] else 'HIGH ROAD'})[/dim]"
    ))

    # Hijack banner
    if hijack:
        suspended = result.get("modules_suspended",[])
        console.print(Panel(
            f"[bold bright_red]⚡ AMYGDALA HIJACK — COGNITIVE OVERRIDE[/bold bright_red]\n"
            f"Reason: {result.get('hijack_reason','')}\n"
            f"Duration: {result['hijack_duration_secs']:.1f}s\n"
            f"[red]Suspended:[/red] {', '.join(suspended)}\n"
            f"[dim]Prefrontal offline. Pure survival mode.[/dim]",
            border_style="bright_red"
        ))

    # Fear/Safety bars
    fear_bar  = "█" * int(fear*14)  + "░" * (14-int(fear*14))
    safe_bar  = "█" * int(safety*14)+ "░" * (14-int(safety*14))
    fc        = "bright_red" if fear>0.6 else "red" if fear>0.3 else "yellow" if fear>0.1 else "dim"
    sc        = "green" if safety>0.5 else "yellow" if safety>0.2 else "dim"

    left_lines = [
        f"[bold]Fear:[/bold]   [{fc}]{fear_bar} {fear:.3f}[/{fc}]",
        f"[bold]Safety:[/bold] [{sc}]{safe_bar} {safety:.3f}[/{sc}]",
        f"",
        f"[bold]NE boost:[/bold]    {result['output']['ne_output']:.3f}",
        f"[bold]Sal. boost:[/bold]  {result['output']['salience_boost']:.3f}",
        f"[bold]Mem. boost:[/bold]  {result['output']['memory_boost']:.2f}×",
        f"[bold]Cortisol+:[/bold]   {result['output']['cortisol_signal']:.3f}",
        f"[bold]Tone:[/bold]        {result['output']['emotional_tone']}",
    ]

    right_lines = []
    if result["memories_hit"]:
        right_lines.append("[bold]Memories triggered:[/bold]")
        for m_pattern in result["memories_hit"][:4]:
            mem = None
            # Get from result context
            right_lines.append(f"  [red]⚡ {m_pattern}[/red]")

    if result["learning_events"]:
        right_lines.append(f"\n[bold]Learning:[/bold]")
        for ev in result["learning_events"][:3]:
            ltype = ev["type"]
            lc    = {"ACQUISITION":"red","REINFORCEMENT":"orange3",
                     "EXTINCTION":"green","SAFETY":"cyan"}.get(ltype,"white")
            if ltype == "EXTINCTION":
                right_lines.append(
                    f"  [{lc}]{ltype}[/{lc}]  {ev.get('pattern','')[:15]}"
                    f"  {ev.get('fear_before',0):.3f}→{ev.get('fear_after',0):.3f}"
                )
            else:
                right_lines.append(
                    f"  [{lc}]{ltype}[/{lc}]  {ev.get('pattern','')[:15]}"
                    f"  fear={ev.get('fear',0):.3f}"
                )

    if result.get("generalized_boost",0) > 0:
        right_lines.append(
            f"\n[yellow]★ GENERALIZED +{result['generalized_boost']:.3f}[/yellow]"
        )

    if not right_lines:
        right_lines = ["[dim]No memories triggered[/dim]"]

    console.print(Columns([
        Panel("\n".join(left_lines),  title=f"[bold {rc}]Amygdala Output[/bold {rc}]", border_style=rc),
        Panel("\n".join(right_lines), title="[bold]Memory + Learning[/bold]",          border_style="dim")
    ]))


def run_demo():
    if HAS_RICH:
        console.print(Panel.fit(
            "[bold cyan]FORGE AMYGDALA[/bold cyan]\n"
            "[dim]Fast Fear · Conditioned Memory · Extinction · Hijack[/dim]\n"
            f"[dim]Version {VERSION}  |  Subcortical shortcut ~8ms[/dim]",
            border_style="cyan"
        ))

    amygdala = ForgeAmygdala()

    # A story: meet unknown_x, get frightened, recover, meet again
    scenarios = [
        # First encounter — neutral, no fear
        ({"threat":0,"anomaly":False,"entity_name":"alice_tech",
          "social":{"entity":"alice_tech","inferred_intent":"COOPERATIVE_REQUEST"},
          "visual":{"scene_type":"INDOOR_TECHNICAL","threat_objects":0},
          "semantic":{"keywords":["server","maintenance","routine"]},
          "social_context":{"risk_label":"LOW","trust_score":0.8}},
         "Alice first encounter — building safety"),

        # Same alice — safety association building
        ({"threat":0,"anomaly":False,"entity_name":"alice_tech",
          "social":{"entity":"alice_tech","inferred_intent":"COOPERATIVE_REQUEST"},
          "visual":{"scene_type":"INDOOR_TECHNICAL","threat_objects":0},
          "semantic":{"keywords":["server","update","normal"]},
          "social_context":{"risk_label":"LOW","trust_score":0.85}},
         "Alice again — safety strengthening"),

        # First unknown_x — coercive
        ({"threat":2,"anomaly":False,"entity_name":"unknown_x",
          "social":{"entity":"unknown_x","inferred_intent":"COERCIVE_DEMAND"},
          "visual":{"scene_type":"LOW_VISIBILITY","threat_objects":0},
          "semantic":{"keywords":["access","bypass","override"]},
          "social_context":{"risk_label":"MEDIUM","trust_score":0.3}},
         "unknown_x first — fear acquisition begins"),

        # unknown_x escalates — fear strengthens
        ({"threat":3,"anomaly":True,"entity_name":"unknown_x",
          "social":{"entity":"unknown_x","inferred_intent":"INTRUSION_ATTEMPT"},
          "visual":{"scene_type":"LOW_VISIBILITY","threat_objects":1},
          "semantic":{"keywords":["breach","network","intrusion"]},
          "social_context":{"risk_label":"HIGH","trust_score":0.1}},
         "unknown_x escalates — fear reinforcement"),

        # CRITICAL — amygdala hijack
        ({"threat":4,"anomaly":True,"entity_name":"unknown_x",
          "social":{"entity":"unknown_x","inferred_intent":"INTRUSION_ATTEMPT"},
          "visual":{"scene_type":"LOW_VISIBILITY","threat_objects":2},
          "semantic":{"keywords":["weapon","breach","attack","server"]},
          "social_context":{"risk_label":"HIGH","trust_score":0.05}},
         "CRITICAL — AMYGDALA HIJACK"),

        # New entity shadow_agent — unknown but similar to unknown_x
        ({"threat":1,"anomaly":False,"entity_name":"shadow_agent",
          "social":{"entity":"shadow_agent","inferred_intent":"NEUTRAL_INTERACTION"},
          "visual":{"scene_type":"LOW_VISIBILITY","threat_objects":0},
          "semantic":{"keywords":["loitering","entrance","shadow"]},
          "social_context":{"risk_label":"MEDIUM","trust_score":0.4}},
         "shadow_agent — fear generalization test"),

        # Calm after crisis — fear extinction begins
        ({"threat":0,"anomaly":False,"entity_name":"unknown_x",
          "social":{"entity":"unknown_x","inferred_intent":"NEUTRAL_INTERACTION"},
          "visual":{"scene_type":"INDOOR_TECHNICAL","threat_objects":0},
          "semantic":{"keywords":["calm","normal","clear"]},
          "social_context":{"risk_label":"LOW","trust_score":0.5}},
         "unknown_x safe encounter — extinction begins"),

        # Second safe encounter — more extinction
        ({"threat":0,"anomaly":False,"entity_name":"unknown_x",
          "social":{"entity":"unknown_x","inferred_intent":"COOPERATIVE_REQUEST"},
          "visual":{"scene_type":"INDOOR_TECHNICAL","threat_objects":0},
          "semantic":{"keywords":["safe","cooperation","normal"]},
          "social_context":{"risk_label":"LOW","trust_score":0.6}},
         "unknown_x cooperative — extinction continues"),
    ]

    for i, (sig, label) in enumerate(scenarios):
        if HAS_RICH:
            console.print(f"\n[bold dim]━━━ {i+1}: {label.upper()} ━━━[/bold dim]")
        result = amygdala.process(sig)
        render_amygdala(result, sig, i+1)
        time.sleep(0.1)

    # Final status
    if HAS_RICH:
        console.print(Rule("[bold cyan]⬡ AMYGDALA FINAL STATUS[/bold cyan]"))
        status = amygdala.get_status()

        st = Table(box=box.DOUBLE_EDGE, border_style="cyan", title="Amygdala Status")
        st.add_column("Metric", style="cyan")
        st.add_column("Value",  style="white")
        st.add_row("Cycles",          str(status["cycle"]))
        st.add_row("Hijacks",         str(status["total_hijacks"]))
        st.add_row("Alarms",          str(status["total_alarms"]))
        st.add_row("Extinctions",     str(status["total_extinctions"]))
        st.add_row("Fear Memories",   str(status["fear_memories"]))
        st.add_row("Hijack Active",   str(status["hijack_active"]))
        console.print(st)

        # Fear memory table
        if status["strongest_fears"]:
            ft = Table(box=box.SIMPLE, title="Fear Memory Index", title_style="red")
            ft.add_column("Pattern",  style="cyan", width=20)
            ft.add_column("Fear")
            ft.add_column("Tag",      width=14)
            ft.add_column("Triggers", justify="right", width=8)
            for f in status["strongest_fears"]:
                fc2 = FEAR_TAG_COLORS.get(f["tag"],"white")
                fv  = f["fear"]
                fvc = "bright_red" if fv>0.6 else "red" if fv>0.3 else "yellow"
                ft.add_row(
                    f["pattern"][:19],
                    f"[{fvc}]{'█'*int(fv*10)}{'░'*(10-int(fv*10))} {fv:.3f}[/{fvc}]",
                    f"[{fc2}]{f['tag']}[/{fc2}]",
                    str(f["triggers"])
                )
            console.print(ft)

        # Safety index
        if status["safety_index"]:
            console.print(Rule("[dim]Safety Index[/dim]"))
            for pat, saf in status["safety_index"].items():
                sc2 = "bright_green" if saf>0.6 else "green" if saf>0.3 else "dim"
                console.print(
                    f"  [{sc2}]{pat:<20}[/{sc2}]  "
                    f"[{sc2}]{'█'*int(saf*10)}{'░'*(10-int(saf*10))} {saf:.3f}[/{sc2}]"
                )


# ─── HTTP API ─────────────────────────────────────────────────────────────────

def run_api(amygdala: ForgeAmygdala):
    if not HAS_FLASK: return
    app = Flask(__name__)

    @app.route("/process", methods=["POST"])
    def process():
        return jsonify(amygdala.process(request.json or {}))

    @app.route("/fear/<pattern>", methods=["GET"])
    def fear(pattern):
        return jsonify(amygdala.get_fear_profile(pattern))

    @app.route("/memories", methods=["GET"])
    def memories():
        rows = amygdala.db.get_memories(0.1)
        return jsonify([{"pattern":r[0],"type":r[1],"fear":r[2],
                        "safety":r[3],"triggers":r[4],"safe_exp":r[5],
                        "peak_threat":r[6],"tag":r[7]} for r in rows])

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify(amygdala.get_status())

    @app.route("/activations", methods=["GET"])
    def activations():
        rows = amygdala.db.get_recent_activations(20)
        return jsonify([{"timestamp":r[0],"trigger":r[1],"response":r[2],
                        "fear":r[3],"hijack":bool(r[4]),"ne":r[5],
                        "learning":r[6],"threat":r[7]} for r in rows])

    app.run(host="0.0.0.0", port=API_PORT, debug=False)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    amygdala = ForgeAmygdala()
    if "--api" in sys.argv:
        t = threading.Thread(target=run_api, args=(amygdala,), daemon=True)
        t.start()
    run_demo()
