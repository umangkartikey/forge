"""
FORGE Default Mode Network — forge_dmn.py
==========================================
AI analog of the brain's Default Mode Network.

The DMN is active when FORGE is NOT processing external signals.
It is the system's inner life — reflection, imagination, self-awareness.

This is what separates REACTIVE intelligence from REFLECTIVE intelligence.

Architecture:
  DMNScheduler        → switches DMN on/off based on pipeline load
  MindWanderingEngine → free-association across memory traces
  SelfModelBuilder    → FORGE's model of its own identity and state
  FutureSimulator     → "what if" scenario generation
  EmpathyEngine       → models other agents' and entities' mental states
  NarrativeWeaver     → builds coherent story from episodic memory
  InsightEngine       → spontaneous pattern breakthroughs
  ReplayBuffer        → hippocampus memory replay during idle periods

DMN lifecycle:
  External signal arrives  → DMN DEACTIVATES (task-positive network takes over)
  Signal processed         → DMN REACTIVATES after cooldown
  During DMN active:
    → replays recent memories
    → finds patterns prefrontal missed
    → simulates future scenarios
    → updates self-model
    → generates insights
    → weaves narrative
  Next signal arrives with richer context from DMN work
"""

import json
import time
import uuid
import sqlite3
import threading
import math
import random
import hashlib
from datetime import datetime, timedelta
from collections import deque, defaultdict
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.layout import Layout
    from rich.text import Text
    from rich.columns import Columns
    from rich.rule import Rule
    from rich.live import Live
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

DB_PATH      = "forge_dmn.db"
API_PORT     = 7783
VERSION      = "1.0.0"

DMN_COOLDOWN     = 3.0   # seconds after last signal before DMN activates
DMN_CYCLE_SECS   = 2.0   # seconds per DMN thinking cycle
MAX_INSIGHTS     = 50
MAX_SIMULATIONS  = 100
MAX_NARRATIVES   = 20
SELF_UPDATE_FREQ = 5     # update self-model every N cycles

console = Console() if HAS_RICH else None

# ─── Enums ────────────────────────────────────────────────────────────────────

class DMNState(Enum):
    ACTIVE      = "ACTIVE"      # DMN running — no external task
    SUPPRESSED  = "SUPPRESSED"  # External signal received — DMN off
    COOLDOWN    = "COOLDOWN"    # Signal just finished — waiting to reactivate
    DREAMING    = "DREAMING"    # Deep DMN — low-load extended reflection

class InsightType(Enum):
    PATTERN       = "PATTERN"       # recurring pattern detected
    ANOMALY       = "ANOMALY"       # something doesn't fit
    PREDICTION    = "PREDICTION"    # likely future event
    CONNECTION    = "CONNECTION"    # two previously unconnected things linked
    CONTRADICTION = "CONTRADICTION" # conflicting information found
    SELF_INSIGHT  = "SELF_INSIGHT"  # insight about FORGE itself

class NarrativeArc(Enum):
    ESCALATION  = "ESCALATION"   # things getting worse
    RESOLUTION  = "RESOLUTION"   # things being resolved
    DISCOVERY   = "DISCOVERY"    # new entity or pattern found
    ROUTINE     = "ROUTINE"      # normal operations
    MYSTERY     = "MYSTERY"      # unexplained pattern

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class Insight:
    id:           str  = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:    str  = field(default_factory=lambda: datetime.now().isoformat())
    insight_type: str  = InsightType.PATTERN.value
    content:      str  = ""
    confidence:   float = 0.5
    source_memories: list = field(default_factory=list)
    entities_involved: list = field(default_factory=list)
    actionable:   bool = False
    action_hint:  str  = ""
    cycle:        int  = 0

@dataclass
class Simulation:
    id:          str  = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:   str  = field(default_factory=lambda: datetime.now().isoformat())
    scenario:    str  = ""
    trigger:     str  = ""       # what memory/pattern triggered this simulation
    outcome_best: str = ""
    outcome_worst: str = ""
    outcome_likely: str = ""
    probability: float = 0.5
    threat_projection: int = 0
    recommended_prep: str = ""
    cycle:       int  = 0

@dataclass
class SelfModel:
    """FORGE's model of its own identity and current state."""
    timestamp:        str   = field(default_factory=lambda: datetime.now().isoformat())
    identity_summary: str   = ""
    current_mood:     str   = "neutral"
    stress_level:     float = 0.0
    confidence_level: float = 0.7
    known_strengths:  list  = field(default_factory=list)
    known_weaknesses: list  = field(default_factory=list)
    active_concerns:  list  = field(default_factory=list)
    recent_growth:    list  = field(default_factory=list)
    total_signals_processed: int = 0
    total_insights_generated: int = 0
    dominant_threat_pattern: str = "none"
    most_encountered_entity: str = "unknown"
    system_health:    str   = "OPTIMAL"

@dataclass
class Narrative:
    id:          str  = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:   str  = field(default_factory=lambda: datetime.now().isoformat())
    arc:         str  = NarrativeArc.ROUTINE.value
    title:       str  = ""
    story:       str  = ""
    episodes:    list = field(default_factory=list)
    entities:    list = field(default_factory=list)
    moral:       str  = ""   # what FORGE learned from this story
    cycle:       int  = 0

@dataclass
class WanderingThought:
    """A single free-association step."""
    from_concept: str  = ""
    to_concept:   str  = ""
    link_type:    str  = ""   # semantic | emotional | temporal | causal
    strength:     float = 0.5
    cycle:        int  = 0

@dataclass
class EmpathyModel:
    """FORGE's model of another entity's mental state."""
    entity:       str   = ""
    timestamp:    str   = field(default_factory=lambda: datetime.now().isoformat())
    inferred_goal: str  = ""
    inferred_emotion: str = "neutral"
    inferred_stress: float = 0.5
    trust_in_forge: float = 0.5
    likely_next_action: str = ""
    threat_to_forge: int = 0
    empathy_confidence: float = 0.5

# ─── Database ─────────────────────────────────────────────────────────────────

class DMNDB:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init()

    def _init(self):
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS insights (
                    id TEXT PRIMARY KEY, timestamp TEXT, insight_type TEXT,
                    content TEXT, confidence REAL, source_memories TEXT,
                    entities_involved TEXT, actionable INTEGER,
                    action_hint TEXT, cycle INTEGER
                );
                CREATE TABLE IF NOT EXISTS simulations (
                    id TEXT PRIMARY KEY, timestamp TEXT, scenario TEXT,
                    trigger TEXT, outcome_best TEXT, outcome_worst TEXT,
                    outcome_likely TEXT, probability REAL,
                    threat_projection INTEGER, recommended_prep TEXT, cycle INTEGER
                );
                CREATE TABLE IF NOT EXISTS self_models (
                    timestamp TEXT PRIMARY KEY, identity_summary TEXT,
                    current_mood TEXT, stress_level REAL, confidence_level REAL,
                    known_strengths TEXT, known_weaknesses TEXT,
                    active_concerns TEXT, recent_growth TEXT,
                    total_signals INTEGER, total_insights INTEGER,
                    dominant_threat TEXT, top_entity TEXT, system_health TEXT
                );
                CREATE TABLE IF NOT EXISTS narratives (
                    id TEXT PRIMARY KEY, timestamp TEXT, arc TEXT,
                    title TEXT, story TEXT, episodes TEXT,
                    entities TEXT, moral TEXT, cycle INTEGER
                );
                CREATE TABLE IF NOT EXISTS wandering_log (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    from_concept TEXT, to_concept TEXT,
                    link_type TEXT, strength REAL, cycle INTEGER
                );
                CREATE TABLE IF NOT EXISTS empathy_models (
                    entity TEXT PRIMARY KEY, timestamp TEXT,
                    inferred_goal TEXT, inferred_emotion TEXT,
                    inferred_stress REAL, trust_in_forge REAL,
                    likely_next_action TEXT, threat_to_forge INTEGER,
                    empathy_confidence REAL
                );
                CREATE TABLE IF NOT EXISTS dmn_cycles (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    state TEXT, duration_ms REAL,
                    insights_generated INTEGER, simulations_run INTEGER,
                    thoughts_wandered INTEGER
                );
            """)
            self.conn.commit()

    def save_insight(self, i: Insight):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO insights VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (i.id, i.timestamp, i.insight_type, i.content, i.confidence,
                  json.dumps(i.source_memories), json.dumps(i.entities_involved),
                  int(i.actionable), i.action_hint, i.cycle))
            self.conn.commit()

    def save_simulation(self, s: Simulation):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO simulations VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (s.id, s.timestamp, s.scenario, s.trigger,
                  s.outcome_best, s.outcome_worst, s.outcome_likely,
                  s.probability, s.threat_projection, s.recommended_prep, s.cycle))
            self.conn.commit()

    def save_self_model(self, sm: SelfModel):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO self_models VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (sm.timestamp, sm.identity_summary, sm.current_mood,
                  sm.stress_level, sm.confidence_level,
                  json.dumps(sm.known_strengths), json.dumps(sm.known_weaknesses),
                  json.dumps(sm.active_concerns), json.dumps(sm.recent_growth),
                  sm.total_signals_processed, sm.total_insights_generated,
                  sm.dominant_threat_pattern, sm.most_encountered_entity,
                  sm.system_health))
            self.conn.commit()

    def save_narrative(self, n: Narrative):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO narratives VALUES (?,?,?,?,?,?,?,?,?)
            """, (n.id, n.timestamp, n.arc, n.title, n.story,
                  json.dumps(n.episodes), json.dumps(n.entities), n.moral, n.cycle))
            self.conn.commit()

    def save_wander(self, w: WanderingThought):
        with self.lock:
            self.conn.execute("""
                INSERT INTO wandering_log VALUES (?,?,?,?,?,?,?)
            """, (str(uuid.uuid4())[:8], datetime.now().isoformat(),
                  w.from_concept, w.to_concept, w.link_type, w.strength, w.cycle))
            self.conn.commit()

    def save_empathy(self, e: EmpathyModel):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO empathy_models VALUES (?,?,?,?,?,?,?,?,?)
            """, (e.entity, e.timestamp, e.inferred_goal, e.inferred_emotion,
                  e.inferred_stress, e.trust_in_forge, e.likely_next_action,
                  e.threat_to_forge, e.empathy_confidence))
            self.conn.commit()

    def log_cycle(self, state: str, duration_ms: float,
                  insights: int, sims: int, thoughts: int):
        with self.lock:
            self.conn.execute("""
                INSERT INTO dmn_cycles VALUES (?,?,?,?,?,?,?)
            """, (str(uuid.uuid4())[:8], datetime.now().isoformat(),
                  state, duration_ms, insights, sims, thoughts))
            self.conn.commit()

    def get_insights(self, limit=20, actionable_only=False):
        with self.lock:
            if actionable_only:
                return self.conn.execute(
                    "SELECT * FROM insights WHERE actionable=1 ORDER BY timestamp DESC LIMIT ?",
                    (limit,)).fetchall()
            return self.conn.execute(
                "SELECT * FROM insights ORDER BY confidence DESC LIMIT ?",
                (limit,)).fetchall()

    def get_simulations(self, limit=10):
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM simulations ORDER BY threat_projection DESC LIMIT ?",
                (limit,)).fetchall()

    def get_latest_self_model(self):
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM self_models ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()

    def get_narratives(self, limit=5):
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM narratives ORDER BY timestamp DESC LIMIT ?",
                (limit,)).fetchall()


# ─── Replay Buffer ────────────────────────────────────────────────────────────

class ReplayBuffer:
    """
    During DMN active periods, replays recent memories from hippocampus.
    Like REM sleep — consolidating and reprocessing experiences.
    Prioritizes high-importance and high-threat memories.
    """

    def __init__(self, capacity=200):
        self.buffer: deque = deque(maxlen=capacity)
        self.replay_count = 0

    def ingest(self, memories: list):
        """Load memories from hippocampus format."""
        for mem in memories:
            self.buffer.append({
                "id":        mem.get("id", str(uuid.uuid4())[:8]),
                "threat":    mem.get("threat", 0),
                "emotion":   mem.get("emotion", "neutral"),
                "keywords":  mem.get("keywords", []),
                "importance":mem.get("importance", 0.5),
                "title":     mem.get("title", ""),
                "entities":  mem.get("entities", []),
                "timestamp": mem.get("timestamp", datetime.now().isoformat())
            })

    def sample(self, n=5, bias="importance") -> list:
        """Sample memories — biased toward importance or threat."""
        if not self.buffer:
            return []
        items = list(self.buffer)

        if bias == "importance":
            weights = [i.get("importance", 0.5) + 0.1 for i in items]
        elif bias == "threat":
            weights = [i.get("threat", 0) / 4.0 + 0.1 for i in items]
        elif bias == "recent":
            weights = [float(idx+1) for idx in range(len(items))]
        else:
            weights = [1.0] * len(items)

        total = sum(weights)
        probs = [w/total for w in weights]

        chosen = []
        for _ in range(min(n, len(items))):
            r = random.random()
            cumulative = 0
            for item, prob in zip(items, probs):
                cumulative += prob
                if r <= cumulative and item not in chosen:
                    chosen.append(item)
                    break
        self.replay_count += len(chosen)
        return chosen

    def most_threatening(self, n=3) -> list:
        return sorted(self.buffer, key=lambda x: x.get("threat",0), reverse=True)[:n]

    def most_recent(self, n=5) -> list:
        return list(self.buffer)[-n:]

    def entities_seen(self) -> list:
        entities = []
        for mem in self.buffer:
            entities.extend(mem.get("entities", []))
        return list(dict.fromkeys(entities))


# ─── Mind Wandering Engine ────────────────────────────────────────────────────

class MindWanderingEngine:
    """
    Free-association across memory traces.
    Starts from a random concept and follows links — semantic, emotional, causal.
    Each step can produce a new connection or insight.
    """

    LINK_TYPES = {
        "semantic":  ["similar","related","type_of","part_of","example_of"],
        "emotional": ["triggered","followed","contrasts","intensifies"],
        "temporal":  ["before","after","during","caused","prevented"],
        "causal":    ["led_to","prevented","enabled","blocked"],
    }

    CONCEPT_EXPANSIONS = {
        "threat":       ["danger","attack","intrusion","weapon","breach","alarm"],
        "trust":        ["cooperation","alliance","benign","safe","reliable"],
        "server":       ["network","data","access","infrastructure","security"],
        "entity":       ["person","agent","unknown","identity","behavior"],
        "pattern":      ["recurring","anomaly","baseline","deviation","signal"],
        "fear":         ["danger","escape","alert","stress","urgency"],
        "anger":        ["aggression","threat","conflict","hostility"],
        "memory":       ["past","recall","episode","learning","experience"],
        "system":       ["architecture","module","pipeline","network","forge"],
        "unknown":      ["mystery","investigate","novel","discover","analyze"],
    }

    def __init__(self, db: DMNDB):
        self.db = db
        self.thought_chain: list[WanderingThought] = []

    def wander(self, seed_concepts: list, steps: int = 6, cycle: int = 0) -> list[WanderingThought]:
        """Follow a chain of free associations from seed concepts."""
        thoughts = []
        current = random.choice(seed_concepts) if seed_concepts else "system"

        for step in range(steps):
            # Expand current concept
            expansions = self.CONCEPT_EXPANSIONS.get(current, [current + "_related"])
            if not expansions:
                break

            next_concept = random.choice(expansions)
            link_type    = random.choice(list(self.LINK_TYPES.keys()))
            strength     = round(random.uniform(0.3, 0.9), 2)

            thought = WanderingThought(
                from_concept=current, to_concept=next_concept,
                link_type=link_type, strength=strength, cycle=cycle
            )
            thoughts.append(thought)
            self.db.save_wander(thought)

            # Cross-concept jump occasionally
            if random.random() < 0.3 and seed_concepts:
                current = random.choice(seed_concepts)
            else:
                current = next_concept

        self.thought_chain.extend(thoughts)
        return thoughts

    def find_unexpected_connection(self, thoughts: list[WanderingThought]) -> Optional[str]:
        """Look for surprising long-distance connections in the thought chain."""
        if len(thoughts) < 3:
            return None

        # Find concepts that appear far apart in the chain but connect
        concepts = [t.from_concept for t in thoughts] + [thoughts[-1].to_concept]
        for i, c1 in enumerate(concepts):
            for c2 in concepts[i+3:]:
                if c1 != c2 and self._semantic_distance(c1, c2) > 0.7:
                    return f"Unexpected link: '{c1}' connects to '{c2}' through {len(thoughts)} associations"
        return None

    def _semantic_distance(self, a: str, b: str) -> float:
        """Simple proxy for semantic distance — different domain = high distance."""
        threat_domain   = {"threat","attack","weapon","breach","danger","intrusion"}
        social_domain   = {"trust","entity","person","cooperation","behavior"}
        system_domain   = {"server","network","system","module","pipeline","forge"}
        emotional_domain= {"fear","anger","trust","surprise","emotion","stress"}

        domains = [threat_domain, social_domain, system_domain, emotional_domain]
        a_domains = {i for i, d in enumerate(domains) if a in d}
        b_domains = {i for i, d in enumerate(domains) if b in d}

        if not a_domains or not b_domains:
            return 0.5
        return 0.9 if not (a_domains & b_domains) else 0.1


# ─── Self Model Builder ───────────────────────────────────────────────────────

class SelfModelBuilder:
    """
    Builds and updates FORGE's model of its own identity, state, and growth.
    This is FORGE's sense of self — introspection.
    """

    def __init__(self, db: DMNDB):
        self.db    = db
        self.model = SelfModel()

    def update(self, replay_buffer: ReplayBuffer,
               insights: list[Insight],
               total_signals: int,
               cycle: int) -> SelfModel:

        memories    = list(replay_buffer.buffer)
        threats     = [m.get("threat",0) for m in memories]
        emotions    = [m.get("emotion","neutral") for m in memories]
        entities    = replay_buffer.entities_seen()

        # Stress from recent threats
        recent_threats = [m.get("threat",0) for m in replay_buffer.most_recent(10)]
        avg_recent_threat = sum(recent_threats)/len(recent_threats) if recent_threats else 0
        self.model.stress_level = round(min(1.0, avg_recent_threat / 3.0), 2)

        # Mood from dominant emotion
        emotion_counts = defaultdict(int)
        for e in emotions:
            emotion_counts[e] += 1
        self.model.current_mood = max(emotion_counts, key=emotion_counts.get) if emotion_counts else "neutral"

        # Strengths from consistent successes
        self.model.known_strengths = [
            "Pattern recognition across temporal streams",
            "Social entity tracking via forge_bridge",
            "Threat escalation detection",
            "Memory consolidation with novelty detection",
        ]
        if len(memories) > 20:
            self.model.known_strengths.append("Rich episodic memory foundation")

        # Weaknesses from failures or gaps
        self.model.known_weaknesses = []
        if avg_recent_threat > 2:
            self.model.known_weaknesses.append("Elevated threat environment — decision confidence reduced")
        if not insights:
            self.model.known_weaknesses.append("Insufficient DMN cycles — insight generation lagging")
        if len(entities) < 3:
            self.model.known_weaknesses.append("Limited entity knowledge — social model sparse")

        # Active concerns
        high_threats = [m for m in memories if m.get("threat",0) >= 3]
        self.model.active_concerns = []
        if high_threats:
            self.model.active_concerns.append(
                f"{len(high_threats)} high-threat events in memory — pattern monitoring active"
            )
        unknown_entities = [e for e in entities if "unknown" in e.lower()]
        if unknown_entities:
            self.model.active_concerns.append(
                f"Unidentified entities: {', '.join(unknown_entities[:3])}"
            )

        # Growth tracking
        self.model.recent_growth = []
        if total_signals > 0:
            self.model.recent_growth.append(f"Processed {total_signals} signals")
        if insights:
            self.model.recent_growth.append(f"Generated {len(insights)} insights this session")

        # Dominant threat pattern
        if threats:
            avg_t = sum(threats)/len(threats)
            self.model.dominant_threat_pattern = (
                "HIGH_ALERT" if avg_t > 2.5 else
                "ELEVATED"   if avg_t > 1.5 else
                "NOMINAL"
            )

        # Most encountered entity
        entity_freq = defaultdict(int)
        for e in entities:
            entity_freq[e] += 1
        self.model.most_encountered_entity = (
            max(entity_freq, key=entity_freq.get) if entity_freq else "none"
        )

        # System health
        self.model.total_signals_processed   = total_signals
        self.model.total_insights_generated  = len(insights)
        self.model.system_health = (
            "STRESSED" if self.model.stress_level > 0.7 else
            "ELEVATED" if self.model.stress_level > 0.4 else
            "OPTIMAL"
        )

        # Identity summary
        self.model.identity_summary = (
            f"FORGE is a cognitive intelligence system with {total_signals} signals processed. "
            f"Current mood: {self.model.current_mood}. "
            f"Dominant pattern: {self.model.dominant_threat_pattern}. "
            f"System health: {self.model.system_health}."
        )

        self.model.timestamp = datetime.now().isoformat()
        self.db.save_self_model(self.model)
        return self.model


# ─── Future Simulator ─────────────────────────────────────────────────────────

class FutureSimulator:
    """
    Generates "what if" scenarios based on current memory patterns.
    Projects likely future events and prepares recommended responses.
    This is FORGE's imagination.
    """

    SCENARIO_TEMPLATES = [
        {
            "trigger":  "high_threat_entity",
            "scenario": "Entity {entity} escalates from threat={threat} to critical breach",
            "best":     "Early detection enables preemptive block — zero impact",
            "worst":    "Breach succeeds — full system compromise",
            "likely":   "Partial containment — {entity} blocked after {threat} level breach",
            "prep":     "Pre-position defenders near {entity} last known location"
        },
        {
            "trigger":  "repeat_pattern",
            "scenario": "Recurring pattern '{pattern}' reaches critical frequency",
            "best":     "Pattern recognized early — automated response triggered",
            "worst":    "Pattern overwhelms detection — cascade failure",
            "likely":   "Pattern flagged at cycle 3 — manual review required",
            "prep":     "Increase sentinel sensitivity for '{pattern}' keywords"
        },
        {
            "trigger":  "unknown_entity",
            "scenario": "Unknown entity {entity} reveals true intent — hostile",
            "best":     "Intent revealed early — entity isolated before damage",
            "worst":    "Unknown entity was insider — trust model compromised",
            "likely":   "Entity flagged by bridge enrichment on 3rd interaction",
            "prep":     "Zero-trust protocol for all unknown entities"
        },
        {
            "trigger":  "system_stress",
            "scenario": "Multiple simultaneous threats overwhelm swarm capacity",
            "best":     "Swarm scales via healer spawning — all threats contained",
            "worst":    "Cascade failure — swarm collapses, pipeline dark",
            "likely":   "2-3 threats managed, 1 breaks through — partial damage",
            "prep":     "Pre-spawn 2 additional defenders, activate sentinel grid"
        },
        {
            "trigger":  "calm_period",
            "scenario": "Extended calm precedes coordinated attack",
            "best":     "DMN detects anomalous calm — pre-emptive heightened state",
            "worst":    "Calm lulls system into low sensitivity — attack succeeds",
            "likely":   "Calm period logged — slight sensitivity increase at day 3",
            "prep":     "Never reduce below baseline sentinel coverage"
        },
    ]

    def __init__(self, db: DMNDB):
        self.db = db
        self.simulations: list[Simulation] = []

    def simulate(self, replay_buffer: ReplayBuffer, cycle: int) -> list[Simulation]:
        """Generate simulations based on current memory state."""
        new_sims = []
        memories     = list(replay_buffer.buffer)
        high_threats = [m for m in memories if m.get("threat",0) >= 3]
        unknowns     = [m for m in memories if "unknown" in " ".join(m.get("entities",[""]))]
        keywords_all = []
        for m in memories:
            keywords_all.extend(m.get("keywords",[]))

        # Choose relevant templates
        triggers = []
        if high_threats:    triggers.append(("high_threat_entity", high_threats[0]))
        if unknowns:        triggers.append(("unknown_entity", unknowns[0]))
        if len(memories) > 5: triggers.append(("repeat_pattern", memories[-1]))
        if not high_threats and memories: triggers.append(("calm_period", memories[-1]))

        for trigger_name, source_mem in triggers[:2]:  # max 2 sims per cycle
            template = next(
                (t for t in self.SCENARIO_TEMPLATES if t["trigger"] == trigger_name),
                self.SCENARIO_TEMPLATES[-1]
            )

            entity  = source_mem.get("entities", ["unknown"])[0] if source_mem.get("entities") else "unknown"
            threat  = source_mem.get("threat", 1)
            pattern = source_mem.get("keywords", ["unknown_pattern"])[0]

            sim = Simulation(
                scenario=template["scenario"].format(
                    entity=entity, threat=threat, pattern=pattern),
                trigger=trigger_name,
                outcome_best=template["best"].format(
                    entity=entity, threat=threat, pattern=pattern),
                outcome_worst=template["worst"].format(
                    entity=entity, threat=threat, pattern=pattern),
                outcome_likely=template["likely"].format(
                    entity=entity, threat=threat, pattern=pattern),
                probability=round(random.uniform(0.3, 0.8), 2),
                threat_projection=min(4, threat + random.randint(0, 2)),
                recommended_prep=template["prep"].format(
                    entity=entity, pattern=pattern),
                cycle=cycle
            )
            self.db.save_simulation(sim)
            self.simulations.append(sim)
            new_sims.append(sim)

        return new_sims


# ─── Empathy Engine ───────────────────────────────────────────────────────────

class EmpathyEngine:
    """
    Models other agents' and entities' mental states.
    FORGE imagines itself as the other — what do they want? what do they feel?
    This is the cognitive basis of social intelligence.
    """

    INTENT_EMOTIONS = {
        "COOPERATIVE_REQUEST":    ("help","calm",    0.2),
        "COLLABORATIVE_SUGGESTION":("collaborate","neutral",0.2),
        "NEUTRAL_INTERACTION":    ("observe","neutral",0.3),
        "COERCIVE_DEMAND":        ("control","frustration",0.6),
        "INTRUSION_ATTEMPT":      ("breach","fear",  0.8),
    }

    NEXT_ACTION_MAP = {
        "CONSISTENTLY_BENIGN": "Continue routine access — low risk",
        "ESCALATING":          "Next interaction likely more aggressive",
        "DE_ESCALATING":       "Entity backing down — monitor for reversal",
        "REPEAT_OFFENDER":     "Will attempt again — different vector likely",
        "COOPERATIVE":         "Will seek collaboration again",
        "MIXED_SIGNALS":       "Unpredictable — heightened monitoring needed",
        "INSUFFICIENT_DATA":   "Unknown — default to cautious observation",
    }

    def __init__(self, db: DMNDB):
        self.db = db
        self.models: dict[str, EmpathyModel] = {}

    def model_entity(self, entity_name: str, memory: dict,
                     behavior_pattern: str = "INSUFFICIENT_DATA") -> EmpathyModel:
        """Build empathy model for an entity."""
        intent  = memory.get("social", {}).get("inferred_intent", "NEUTRAL_INTERACTION") if memory.get("social") else "NEUTRAL_INTERACTION"
        threat  = memory.get("threat", 0)

        goal_map = {
            "COOPERATIVE_REQUEST":    f"{entity_name} wants legitimate access or assistance",
            "COERCIVE_DEMAND":        f"{entity_name} wants control — feels blocked or powerless",
            "INTRUSION_ATTEMPT":      f"{entity_name} wants unauthorized access — hostile intent",
            "NEUTRAL_INTERACTION":    f"{entity_name}'s goal is unclear — observing",
            "COLLABORATIVE_SUGGESTION": f"{entity_name} wants to work together toward shared goal",
        }

        emotion_data = self.INTENT_EMOTIONS.get(intent, ("unknown","neutral",0.3))
        inferred_goal, inferred_emotion, inferred_stress = (
            goal_map.get(intent, f"{entity_name}'s intent unclear"),
            emotion_data[1],
            emotion_data[2] + (threat * 0.1)
        )

        # How much does this entity trust FORGE?
        trust_in_forge = {
            "COOPERATIVE_REQUEST": 0.7,
            "COLLABORATIVE_SUGGESTION": 0.65,
            "NEUTRAL_INTERACTION": 0.5,
            "COERCIVE_DEMAND": 0.3,
            "INTRUSION_ATTEMPT": 0.1,
        }.get(intent, 0.5)

        next_action = self.NEXT_ACTION_MAP.get(behavior_pattern, "Unknown next action")

        em = EmpathyModel(
            entity=entity_name,
            inferred_goal=inferred_goal,
            inferred_emotion=inferred_emotion,
            inferred_stress=round(min(1.0, inferred_stress), 2),
            trust_in_forge=trust_in_forge,
            likely_next_action=next_action,
            threat_to_forge=threat,
            empathy_confidence=round(0.4 + (0.1 * min(5, len(str(memory))//50)), 2)
        )
        self.models[entity_name] = em
        self.db.save_empathy(em)
        return em


# ─── Narrative Weaver ─────────────────────────────────────────────────────────

class NarrativeWeaver:
    """
    Builds coherent stories from episodic memory.
    Finds the arc — escalation, resolution, discovery, mystery.
    Extracts the moral — what FORGE should remember.
    """

    def __init__(self, db: DMNDB):
        self.db = db
        self.narratives: list[Narrative] = []

    def weave(self, memories: list, cycle: int) -> Optional[Narrative]:
        """Weave a narrative from a sequence of memories."""
        if len(memories) < 2:
            return None

        threats  = [m.get("threat",0) for m in memories]
        emotions = [m.get("emotion","neutral") for m in memories]
        entities = list(dict.fromkeys(
            e for m in memories for e in m.get("entities",[])
        ))
        keywords = list(dict.fromkeys(
            k for m in memories for k in m.get("keywords",[])[:3]
        ))

        # Determine arc
        if threats[-1] > threats[0] + 1:       arc = NarrativeArc.ESCALATION
        elif threats[-1] < threats[0] - 1:     arc = NarrativeArc.RESOLUTION
        elif len(set(emotions)) > 3:            arc = NarrativeArc.DISCOVERY
        elif max(threats) == 0:                 arc = NarrativeArc.ROUTINE
        else:                                   arc = NarrativeArc.MYSTERY

        # Build title
        titles = {
            NarrativeArc.ESCALATION: f"The Rising Threat of {entities[0] if entities else 'Unknown'}",
            NarrativeArc.RESOLUTION: f"How FORGE Contained the {keywords[0] if keywords else 'Incident'}",
            NarrativeArc.DISCOVERY:  f"The Discovery of {keywords[0] if keywords else 'an Unknown Pattern'}",
            NarrativeArc.ROUTINE:    f"A Quiet Cycle — {datetime.now().strftime('%H:%M')}",
            NarrativeArc.MYSTERY:    f"The Unexplained Pattern in {keywords[0] if keywords else 'the Signal Stream'}",
        }
        title = titles.get(arc, "Untitled Episode")

        # Build story
        story_parts = []
        for i, mem in enumerate(memories[:4]):
            t    = mem.get("threat", 0)
            e    = mem.get("emotion","neutral")
            kw   = ", ".join(mem.get("keywords",[])[:2])
            ent  = mem.get("entities",["unknown"])[0] if mem.get("entities") else "unknown"
            story_parts.append(
                f"[{i+1}] {ent} — threat={t}, emotion={e}, context={kw}"
            )
        story = "\n".join(story_parts)

        # Extract moral
        morals = {
            NarrativeArc.ESCALATION:  f"Pattern: escalation from {threats[0]} to {threats[-1]}. Watch for early signals.",
            NarrativeArc.RESOLUTION:  f"Success: threat de-escalated through {emotions[-1]} response. Replicate.",
            NarrativeArc.DISCOVERY:   f"New pattern emerged involving {', '.join(keywords[:2])}. Encode in semantic memory.",
            NarrativeArc.ROUTINE:     f"Baseline confirmed. Normal operations. Stay vigilant.",
            NarrativeArc.MYSTERY:     f"Unexplained variance in {keywords[0] if keywords else 'signals'}. Investigate.",
        }
        moral = morals.get(arc, "Experience logged.")

        narrative = Narrative(
            arc=arc.value, title=title, story=story,
            episodes=[m.get("id","") for m in memories],
            entities=entities[:5], moral=moral, cycle=cycle
        )
        self.db.save_narrative(narrative)
        self.narratives.append(narrative)
        return narrative


# ─── Insight Engine ───────────────────────────────────────────────────────────

class InsightEngine:
    """
    Spontaneous pattern breakthroughs.
    The "shower thought" of AI — connections the active pipeline never finds
    because it's too busy processing the immediate signal.
    """

    def __init__(self, db: DMNDB):
        self.db = db
        self.insights: list[Insight] = []

    def generate(self, replay_buffer: ReplayBuffer,
                 thoughts: list[WanderingThought],
                 self_model: SelfModel,
                 cycle: int) -> list[Insight]:

        new_insights = []
        memories = list(replay_buffer.buffer)
        if not memories:
            return new_insights

        # 1. Pattern detection — recurring elements
        keyword_freq = defaultdict(int)
        entity_freq  = defaultdict(int)
        threat_seq   = []

        for mem in memories:
            for kw in mem.get("keywords",[]):
                keyword_freq[kw] += 1
            for ent in mem.get("entities",[]):
                entity_freq[ent] += 1
            threat_seq.append(mem.get("threat",0))

        # Top recurring keyword
        if keyword_freq:
            top_kw, count = max(keyword_freq.items(), key=lambda x: x[1])
            if count >= 2:
                insight = Insight(
                    insight_type=InsightType.PATTERN.value,
                    content=f"'{top_kw}' appears in {count} memories — elevated significance",
                    confidence=min(0.9, 0.4 + count*0.15),
                    source_memories=[m.get("id","") for m in memories[:3]],
                    actionable=count >= 3,
                    action_hint=f"Increase sensitivity for '{top_kw}' across all detection streams" if count >= 3 else "",
                    cycle=cycle
                )
                self.db.save_insight(insight)
                self.insights.append(insight)
                new_insights.append(insight)

        # 2. Threat trend insight
        if len(threat_seq) >= 3:
            recent   = threat_seq[-3:]
            baseline = threat_seq[:-3] or [0]
            avg_recent   = sum(recent)/len(recent)
            avg_baseline = sum(baseline)/len(baseline)

            if avg_recent > avg_baseline + 1.0:
                insight = Insight(
                    insight_type=InsightType.PREDICTION.value,
                    content=f"Threat trend rising: baseline={avg_baseline:.1f} → recent={avg_recent:.1f}. Escalation predicted.",
                    confidence=0.75,
                    source_memories=[m.get("id","") for m in memories[-3:]],
                    actionable=True,
                    action_hint="Activate heightened swarm readiness before next signal",
                    cycle=cycle
                )
                self.db.save_insight(insight)
                self.insights.append(insight)
                new_insights.append(insight)

        # 3. Entity insight — high-frequency + high threat
        if entity_freq:
            for ent, freq in entity_freq.items():
                ent_threats = [m.get("threat",0) for m in memories
                               if ent in m.get("entities",[])]
                if ent_threats and freq >= 2 and max(ent_threats) >= 2:
                    insight = Insight(
                        insight_type=InsightType.ANOMALY.value,
                        content=f"Entity '{ent}' seen {freq}× with max threat={max(ent_threats)} — high-risk repeat actor",
                        confidence=0.8,
                        entities_involved=[ent],
                        actionable=True,
                        action_hint=f"Pre-flag '{ent}' in bridge social graph — trigger alert on next appearance",
                        cycle=cycle
                    )
                    self.db.save_insight(insight)
                    self.insights.append(insight)
                    new_insights.append(insight)

        # 4. Connection from mind wandering
        if thoughts:
            strong_thoughts = [t for t in thoughts if t.strength > 0.7]
            if strong_thoughts:
                t = strong_thoughts[0]
                insight = Insight(
                    insight_type=InsightType.CONNECTION.value,
                    content=f"DMN discovered link: '{t.from_concept}' → '{t.to_concept}' via {t.link_type} (strength={t.strength})",
                    confidence=t.strength * 0.7,
                    actionable=False,
                    cycle=cycle
                )
                self.db.save_insight(insight)
                self.insights.append(insight)
                new_insights.append(insight)

        # 5. Self-insight
        if self_model.stress_level > 0.6:
            insight = Insight(
                insight_type=InsightType.SELF_INSIGHT.value,
                content=f"FORGE stress level elevated ({self_model.stress_level:.0%}). Decision quality may be degraded. Recommend DMN extended session.",
                confidence=0.85,
                actionable=True,
                action_hint="Trigger extended DMN cycle — 3× normal duration for recovery",
                cycle=cycle
            )
            self.db.save_insight(insight)
            self.insights.append(insight)
            new_insights.append(insight)

        return new_insights


# ─── DMN Scheduler ────────────────────────────────────────────────────────────

class DMNScheduler:
    """
    Switches DMN on/off based on pipeline activity.
    Tracks when the last external signal arrived.
    DMN activates after cooldown, deactivates when signal arrives.
    """

    def __init__(self, cooldown: float = DMN_COOLDOWN):
        self.cooldown     = cooldown
        self.state        = DMNState.ACTIVE
        self.last_signal  = None
        self.dmn_start    = datetime.now()
        self.active_time  = 0.0
        self.suppressed_time = 0.0
        self._last_tick   = datetime.now()

    def signal_received(self):
        """Call when an external signal arrives — suppresses DMN."""
        self.last_signal = datetime.now()
        if self.state == DMNState.ACTIVE:
            self.active_time += (datetime.now() - self.dmn_start).total_seconds()
        self.state = DMNState.SUPPRESSED

    def tick(self) -> DMNState:
        """Update state based on time since last signal."""
        now = datetime.now()

        if self.state == DMNState.SUPPRESSED:
            if self.last_signal:
                elapsed = (now - self.last_signal).total_seconds()
                if elapsed >= self.cooldown:
                    self.state    = DMNState.COOLDOWN
                    self._last_tick = now

        elif self.state == DMNState.COOLDOWN:
            elapsed = (now - self._last_tick).total_seconds()
            if elapsed >= 1.0:
                self.state    = DMNState.ACTIVE
                self.dmn_start= now

        elif self.state == DMNState.ACTIVE:
            # Deep dreaming after extended active period
            elapsed = (now - self.dmn_start).total_seconds()
            if elapsed > 30.0:
                self.state = DMNState.DREAMING

        return self.state

    def is_active(self) -> bool:
        return self.state in [DMNState.ACTIVE, DMNState.DREAMING]

    def duty_cycle(self) -> dict:
        return {
            "state":          self.state.value,
            "active_pct":     round(self.active_time / max(1, self.active_time + self.suppressed_time) * 100, 1),
            "last_signal_ago":round((datetime.now() - self.last_signal).total_seconds(), 1) if self.last_signal else None
        }


# ─── FORGE Default Mode Network ───────────────────────────────────────────────

class ForgeDMN:
    def __init__(self):
        self.db        = DMNDB()
        self.scheduler = DMNScheduler()
        self.replay    = ReplayBuffer()
        self.wandering = MindWanderingEngine(self.db)
        self.self_model= SelfModelBuilder(self.db)
        self.simulator = FutureSimulator(self.db)
        self.empathy   = EmpathyEngine(self.db)
        self.narrative = NarrativeWeaver(self.db)
        self.insight   = InsightEngine(self.db)

        self.cycle          = 0
        self.total_signals  = 0
        self.all_insights:  list[Insight]    = []
        self.all_sims:      list[Simulation] = []
        self.current_model: Optional[SelfModel] = None
        self._running       = False
        self._thread        = None

    def ingest_signal(self, perception: dict):
        """Called when an external signal arrives — suppresses DMN."""
        self.scheduler.signal_received()
        self.total_signals += 1

        # Feed signal into replay buffer as a memory
        self.replay.ingest([{
            "id":        perception.get("id", str(uuid.uuid4())[:8]),
            "threat":    perception.get("threat", 0),
            "emotion":   perception.get("emotional", {}).get("dominant", "neutral") if perception.get("emotional") else "neutral",
            "keywords":  perception.get("semantic", {}).get("keywords", []) if perception.get("semantic") else [],
            "importance":min(1.0, perception.get("threat",0)/4.0 + 0.2),
            "title":     perception.get("conclusion","")[:60],
            "entities":  [perception.get("entity_name","unknown")],
            "timestamp": datetime.now().isoformat()
        }])

    def run_cycle(self) -> dict:
        """
        One DMN thinking cycle.
        Returns everything generated this cycle.
        """
        self.cycle += 1
        t0     = time.time()
        state  = self.scheduler.tick()

        if not self.scheduler.is_active():
            return {"state": state.value, "cycle": self.cycle, "active": False}

        cycle_insights = []
        cycle_sims     = []
        cycle_thoughts = []
        narrative      = None

        # 1. Memory replay
        replayed = self.replay.sample(n=6, bias="importance")

        # 2. Mind wandering
        seed_concepts = []
        for mem in replayed:
            seed_concepts.extend(mem.get("keywords",[])[:2])
        if not seed_concepts:
            seed_concepts = ["system","pattern","entity","threat"]

        thoughts = self.wandering.wander(seed_concepts, steps=5, cycle=self.cycle)
        cycle_thoughts = thoughts

        # 3. Update self model
        if self.cycle % SELF_UPDATE_FREQ == 0:
            self.current_model = self.self_model.update(
                self.replay, self.all_insights,
                self.total_signals, self.cycle
            )

        # 4. Generate insights
        model = self.current_model or SelfModel()
        cycle_insights = self.insight.generate(
            self.replay, thoughts, model, self.cycle
        )
        self.all_insights.extend(cycle_insights)

        # 5. Run simulations
        if self.cycle % 2 == 0:
            cycle_sims = self.simulator.simulate(self.replay, self.cycle)
            self.all_sims.extend(cycle_sims)

        # 6. Build empathy models for known entities
        entities = self.replay.entities_seen()[:3]
        empathy_models = []
        for ent in entities:
            ent_memories = [m for m in self.replay.buffer if ent in m.get("entities",[])]
            if ent_memories:
                em = self.empathy.model_entity(ent, ent_memories[-1])
                empathy_models.append(em)

        # 7. Weave narrative every 4 cycles
        if self.cycle % 4 == 0 and replayed:
            narrative = self.narrative.weave(replayed, self.cycle)

        duration_ms = (time.time() - t0) * 1000
        self.db.log_cycle(state.value, duration_ms,
                          len(cycle_insights), len(cycle_sims), len(cycle_thoughts))

        return {
            "state":       state.value,
            "cycle":       self.cycle,
            "active":      True,
            "duration_ms": round(duration_ms, 1),
            "replayed":    len(replayed),
            "thoughts":    len(cycle_thoughts),
            "insights":    [{"type":i.insight_type,"content":i.content[:80],
                            "confidence":i.confidence,"actionable":i.actionable}
                           for i in cycle_insights],
            "simulations": [{"scenario":s.scenario[:60],"threat_proj":s.threat_projection,
                            "prep":s.recommended_prep[:60]} for s in cycle_sims],
            "narrative":   {"title":narrative.title,"arc":narrative.arc,
                           "moral":narrative.moral} if narrative else None,
            "self_model":  {"mood":model.current_mood,"stress":model.stress_level,
                           "health":model.system_health} if model else None,
            "empathy":     [{"entity":e.entity,"goal":e.inferred_goal[:50],
                            "next":e.likely_next_action[:40]} for e in empathy_models],
        }

    def start_background(self, interval: float = DMN_CYCLE_SECS):
        """Run DMN cycles in background thread."""
        self._running = True
        def loop():
            while self._running:
                self.run_cycle()
                time.sleep(interval)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def get_status(self) -> dict:
        return {
            "version":        VERSION,
            "cycle":          self.cycle,
            "state":          self.scheduler.state.value,
            "duty_cycle":     self.scheduler.duty_cycle(),
            "total_insights": len(self.all_insights),
            "total_sims":     len(self.all_sims),
            "total_narratives":len(self.narrative.narratives),
            "replay_size":    len(self.replay.buffer),
            "entities_modeled":len(self.empathy.models),
            "top_insights":   [{"type":i.insight_type,"content":i.content[:60],
                               "confidence":i.confidence}
                              for i in sorted(self.all_insights,
                                key=lambda x: x.confidence, reverse=True)[:3]]
        }


# ─── Rich UI ──────────────────────────────────────────────────────────────────

def render_cycle(result: dict, dmn: ForgeDMN):
    if not HAS_RICH or not result.get("active"): return

    state       = result["state"]
    state_color = {"ACTIVE":"cyan","DREAMING":"magenta",
                   "COOLDOWN":"yellow","SUPPRESSED":"dim"}.get(state,"white")

    console.print(Rule(
        f"[bold {state_color}]⬡ FORGE DMN[/bold {state_color}]  "
        f"[dim]Cycle {result['cycle']}  State: {state}  "
        f"{result['duration_ms']:.0f}ms[/dim]"
    ))

    panels = []

    # Insights panel
    if result["insights"]:
        lines = []
        for ins in result["insights"]:
            ic = {"PATTERN":"cyan","PREDICTION":"yellow","ANOMALY":"red",
                  "CONNECTION":"green","SELF_INSIGHT":"magenta",
                  "CONTRADICTION":"orange3"}.get(ins["type"],"white")
            action = " [bold]→ ACTIONABLE[/bold]" if ins["actionable"] else ""
            lines.append(
                f"[{ic}]{ins['type']}[/{ic}] [{ins['confidence']:.0%}]{action}\n"
                f"[dim]{ins['content']}[/dim]"
            )
        panels.append(Panel(
            "\n\n".join(lines),
            title=f"[bold cyan]💡 INSIGHTS ({len(result['insights'])})[/bold cyan]",
            border_style="cyan"
        ))

    # Simulations panel
    if result["simulations"]:
        lines = []
        for sim in result["simulations"]:
            tc = {0:"green",1:"blue",2:"yellow",3:"red",4:"bright_red"}.get(
                sim["threat_proj"],"white")
            lines.append(
                f"[{tc}]Threat→{sim['threat_proj']}[/{tc}]  {sim['scenario']}\n"
                f"[dim]Prep: {sim['prep']}[/dim]"
            )
        panels.append(Panel(
            "\n\n".join(lines),
            title=f"[bold yellow]🔮 SIMULATIONS ({len(result['simulations'])})[/bold yellow]",
            border_style="yellow"
        ))

    if panels:
        console.print(Columns(panels))

    # Narrative
    if result.get("narrative"):
        n = result["narrative"]
        arc_color = {"ESCALATION":"red","RESOLUTION":"green","DISCOVERY":"cyan",
                     "ROUTINE":"dim","MYSTERY":"magenta"}.get(n["arc"],"white")
        console.print(Panel(
            f"[bold]Arc:[/bold] [{arc_color}]{n['arc']}[/{arc_color}]\n"
            f"[bold]Title:[/bold] {n['title']}\n"
            f"[dim]{n['moral']}[/dim]",
            title="[bold]📖 NARRATIVE[/bold]", border_style=arc_color
        ))

    # Self model
    if result.get("self_model"):
        sm = result["self_model"]
        sc = "red" if sm["stress"] > 0.6 else "yellow" if sm["stress"] > 0.3 else "green"
        console.print(
            f"  [dim]Self: mood={sm['mood']}  "
            f"stress=[{sc}]{sm['stress']:.0%}[/{sc}]  "
            f"health={sm['health']}[/dim]"
        )

    # Empathy
    if result.get("empathy"):
        for em in result["empathy"]:
            console.print(
                f"  [dim]Empathy [{em['entity']}]: {em['goal'][:50]} → {em['next'][:40]}[/dim]"
            )

    # Wandering summary
    console.print(
        f"  [dim]Mind wandered {result['thoughts']} steps  |  "
        f"Replayed {result['replayed']} memories[/dim]"
    )


def run_demo():
    if HAS_RICH:
        console.print(Panel.fit(
            "[bold cyan]FORGE DEFAULT MODE NETWORK[/bold cyan]\n"
            "[dim]Reflective Intelligence — FORGE's Inner Life[/dim]\n"
            f"[dim]Version {VERSION}[/dim]",
            border_style="cyan"
        ))

    dmn = ForgeDMN()

    # Feed in some memories (simulating prior pipeline activity)
    past_signals = [
        {"id":"p001","threat":0,"conclusion":"Normal ops","entity_name":"alice_tech",
         "emotional":{"dominant":"trust"},"semantic":{"keywords":["server","maintenance","firmware"]}},
        {"id":"p002","threat":2,"conclusion":"Suspicious entity","entity_name":"unknown_x",
         "emotional":{"dominant":"fear"},"semantic":{"keywords":["access","bypass","override"]}},
        {"id":"p003","threat":4,"conclusion":"CRITICAL breach","entity_name":"unknown_x",
         "emotional":{"dominant":"fear"},"semantic":{"keywords":["weapon","breach","network","server"]}},
        {"id":"p004","threat":3,"conclusion":"Intrusion attempt","entity_name":"unknown_x",
         "emotional":{"dominant":"anger"},"semantic":{"keywords":["hack","intrusion","packet"]}},
        {"id":"p005","threat":0,"conclusion":"Alice routine check","entity_name":"alice_tech",
         "emotional":{"dominant":"trust"},"semantic":{"keywords":["server","check","update"]}},
        {"id":"p006","threat":1,"conclusion":"New entity spotted","entity_name":"shadow_agent",
         "emotional":{"dominant":"surprise"},"semantic":{"keywords":["loitering","restricted","entrance"]}},
    ]

    if HAS_RICH:
        console.print(f"\n[dim]Ingesting {len(past_signals)} past signals into replay buffer...[/dim]")

    for sig in past_signals:
        dmn.ingest_signal(sig)

    # Simulate a signal arriving then DMN waking up
    dmn.scheduler.last_signal = datetime.now() - timedelta(seconds=5)
    dmn.scheduler.state = DMNState.ACTIVE

    if HAS_RICH:
        console.print(f"\n[bold dim]━━━ DMN ACTIVATING — No incoming signals ━━━[/bold dim]\n")

    # Run 6 DMN cycles
    for i in range(6):
        if HAS_RICH:
            console.print(f"\n[bold dim]── Cycle {i+1} ──[/bold dim]")

        # Simulate a signal interrupting cycle 3
        if i == 3:
            if HAS_RICH:
                console.print("[yellow]⚡ External signal received — DMN suppressed[/yellow]")
            dmn.ingest_signal({"id":"live001","threat":2,"entity_name":"unknown_x",
                              "emotional":{"dominant":"fear"},
                              "semantic":{"keywords":["access","server"]},
                              "conclusion":"⚠ MEDIUM threat"})
            dmn.scheduler.last_signal = datetime.now()
            dmn.scheduler.state = DMNState.SUPPRESSED
            time.sleep(0.1)

            if HAS_RICH:
                console.print("[cyan]✓ Signal processed — DMN cooling down, then reactivating[/cyan]")
            dmn.scheduler.last_signal = datetime.now() - timedelta(seconds=4)
            dmn.scheduler.state = DMNState.COOLDOWN

        result = dmn.run_cycle()
        render_cycle(result, dmn)
        time.sleep(0.1)

    # Final status
    if HAS_RICH:
        console.print(f"\n")
        console.print(Rule("[bold cyan]⬡ DMN FINAL STATUS[/bold cyan]"))

        status = dmn.get_status()
        st = Table(box=box.DOUBLE_EDGE, title="DMN STATUS", border_style="cyan")
        st.add_column("Metric", style="cyan")
        st.add_column("Value",  style="white")
        st.add_row("Version",           VERSION)
        st.add_row("Total Cycles",      str(status["cycle"]))
        st.add_row("Current State",     status["state"])
        st.add_row("Total Insights",    str(status["total_insights"]))
        st.add_row("Total Simulations", str(status["total_sims"]))
        st.add_row("Narratives Woven",  str(status["total_narratives"]))
        st.add_row("Entities Modeled",  str(status["entities_modeled"]))
        st.add_row("Replay Buffer",     str(status["replay_size"]))
        console.print(st)

        if status["top_insights"]:
            console.print(Rule("[dim]Top Insights[/dim]"))
            for ins in status["top_insights"]:
                ic = {"PATTERN":"cyan","PREDICTION":"yellow","ANOMALY":"red",
                      "CONNECTION":"green","SELF_INSIGHT":"magenta"}.get(ins["type"],"white")
                console.print(
                    f"  [{ic}]{ins['type']}[/{ic}] [{ins['confidence']:.0%}]  {ins['content']}"
                )


# ─── HTTP API ─────────────────────────────────────────────────────────────────

def run_api(dmn: ForgeDMN):
    if not HAS_FLASK: return
    app = Flask(__name__)

    @app.route("/ingest", methods=["POST"])
    def ingest():
        data = request.json or {}
        dmn.ingest_signal(data)
        return jsonify({"status": "ingested", "buffer_size": len(dmn.replay.buffer)})

    @app.route("/cycle", methods=["POST"])
    def cycle():
        return jsonify(dmn.run_cycle())

    @app.route("/insights", methods=["GET"])
    def insights():
        rows = dmn.db.get_insights(20)
        return jsonify([{"id":r[0],"type":r[2],"content":r[3],
                        "confidence":r[4],"actionable":bool(r[7])} for r in rows])

    @app.route("/simulations", methods=["GET"])
    def simulations():
        rows = dmn.db.get_simulations(10)
        return jsonify([{"scenario":r[2],"threat_proj":r[8],"prep":r[9]} for r in rows])

    @app.route("/self", methods=["GET"])
    def self_model():
        row = dmn.db.get_latest_self_model()
        if not row: return jsonify({})
        return jsonify({"mood":row[2],"stress":row[3],"health":row[13],
                       "identity":row[1],"concerns":json.loads(row[7] or "[]")})

    @app.route("/narratives", methods=["GET"])
    def narratives():
        rows = dmn.db.get_narratives(5)
        return jsonify([{"arc":r[2],"title":r[3],"moral":r[7]} for r in rows])

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify(dmn.get_status())

    dmn.start_background()
    app.run(host="0.0.0.0", port=API_PORT, debug=False)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    dmn = ForgeDMN()
    if "--api" in sys.argv:
        t = threading.Thread(target=run_api, args=(dmn,), daemon=True)
        t.start()
        run_demo()
    else:
        run_demo()
