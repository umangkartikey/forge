"""
FORGE Swarm v2 — forge_swarm_v2.py
====================================
Cognitive Swarm Intelligence — agents that think, not just execute.

Every agent now has a mini-brain:
  - Perception    (forge_temporal inspired)
  - Decision      (forge_prefrontal inspired)
  - Memory        (forge_hippocampus inspired)
  - Social awareness (forge_bridge inspired)

Swarm capabilities:
  CognitiveAgent        → agent with full perception-decision-memory loop
  SwarmConsensus        → emergent voting — majority + trust-weighted
  ThreatPropagation     → one agent sees danger → whole swarm knows instantly
  SwarmSpatialMap       → agents track each other, know who to call
  RoleFluidityEngine    → agents shift roles dynamically by situation
  AgentLifecycle        → birth, death, rebirth — swarm self-heals
  TrustMesh             → agents distrust each other if behavior degrades
  SwarmMemory           → collective memory shared across all agents
  EmergentBehavior      → complex patterns from simple agent rules
"""

import json
import time
import uuid
import sqlite3
import threading
import math
import random
import hashlib
from datetime import datetime
from collections import defaultdict, deque
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
    from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn
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

DB_PATH  = "forge_swarm_v2.db"
API_PORT = 7782
VERSION  = "2.0.0"

MAX_AGENTS        = 32
MIN_AGENTS        = 3
CONSENSUS_QUORUM  = 0.51   # 51% majority
TRUST_THRESHOLD   = 0.25   # below this → agent isolated
THREAT_BROADCAST_THRESHOLD = 2  # threat >= this → propagate to swarm
AGENT_DEATH_THRESHOLD = 3  # 3 consecutive failures → agent dies
MEMORY_CAPACITY   = 100    # per-agent episodic memory
TICK_INTERVAL     = 0.05   # seconds between simulation ticks

console = Console() if HAS_RICH else None

# ─── Enums ────────────────────────────────────────────────────────────────────

class AgentRole(Enum):
    SCOUT      = "SCOUT"       # first contact, perception-heavy
    DEFENDER   = "DEFENDER"    # threat response, blocking
    ANALYST    = "ANALYST"     # pattern recognition, reasoning
    COORDINATOR= "COORDINATOR" # orchestrates other agents
    HEALER     = "HEALER"      # repairs failed agents, redistributes work
    SENTINEL   = "SENTINEL"    # passive watchdog, anomaly detection
    WORKER     = "WORKER"      # general task execution

class AgentState(Enum):
    IDLE       = "IDLE"
    ACTIVE     = "ACTIVE"
    THINKING   = "THINKING"
    VOTING     = "VOTING"
    EXECUTING  = "EXECUTING"
    STRESSED   = "STRESSED"    # under high load / threat
    ISOLATED   = "ISOLATED"    # low trust — quarantined
    DEAD       = "DEAD"
    RESPAWNING = "RESPAWNING"

class SwarmPhase(Enum):
    CALM       = "CALM"
    ALERT      = "ALERT"
    CRISIS     = "CRISIS"
    RECOVERY   = "RECOVERY"

class ConsensusType(Enum):
    SIMPLE_MAJORITY   = "SIMPLE_MAJORITY"
    TRUST_WEIGHTED    = "TRUST_WEIGHTED"
    UNANIMOUS         = "UNANIMOUS"
    COORDINATOR_VETO  = "COORDINATOR_VETO"

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class AgentMemoryFrame:
    timestamp:  str  = field(default_factory=lambda: datetime.now().isoformat())
    event_type: str  = ""
    threat:     int  = 0
    outcome:    str  = ""
    emotion:    str  = "neutral"
    importance: float= 0.5

@dataclass
class AgentBrain:
    """Mini cognitive core — each agent's private mind."""
    # Perception layer
    last_perception:  dict  = field(default_factory=dict)
    perception_count: int   = 0
    threat_baseline:  float = 0.0

    # Decision layer
    last_decision:    str   = "STANDBY"
    decision_count:   int   = 0
    confidence:       float = 0.5

    # Memory layer
    episodic:         deque = field(default_factory=lambda: deque(maxlen=MEMORY_CAPACITY))
    semantic_facts:   list  = field(default_factory=list)
    novelty_cache:    set   = field(default_factory=set)

    # Emotional state (affects decision making)
    emotional_state:  str   = "neutral"
    stress_level:     float = 0.0

    def perceive(self, signal: dict) -> dict:
        self.last_perception  = signal
        self.perception_count += 1
        threat  = signal.get("threat", 0)
        emotion = signal.get("emotion", "neutral")

        # Update stress
        self.stress_level = min(1.0, self.stress_level * 0.9 + threat * 0.1)
        self.emotional_state = emotion

        # Novelty check
        fp = hashlib.md5(json.dumps(sorted(signal.items()), default=str).encode()).hexdigest()[:8]
        is_novel = fp not in self.novelty_cache
        self.novelty_cache.add(fp)

        return {"threat": threat, "stress": round(self.stress_level, 2),
                "novel": is_novel, "emotion": emotion}

    def decide(self, threat: int, role: AgentRole, phase: SwarmPhase) -> str:
        # Role-biased decision making
        role_actions = {
            AgentRole.SCOUT:       ["INVESTIGATE","MONITOR","REPORT"],
            AgentRole.DEFENDER:    ["BLOCK","ALERT","ESCALATE"],
            AgentRole.ANALYST:     ["ANALYZE","PATTERN_MATCH","REPORT"],
            AgentRole.COORDINATOR: ["COORDINATE","DELEGATE","ESCALATE"],
            AgentRole.HEALER:      ["REPAIR","REDISTRIBUTE","SPAWN"],
            AgentRole.SENTINEL:    ["MONITOR","ALERT","STANDBY"],
            AgentRole.WORKER:      ["EXECUTE","REPORT","STANDBY"],
        }
        actions = role_actions.get(role, ["STANDBY"])

        # Threat overrides role bias
        if threat >= 4:    action = "ESCALATE"
        elif threat >= 3:  action = actions[0] if role == AgentRole.DEFENDER else "ALERT"
        elif threat >= 2:  action = "ALERT" if role != AgentRole.ANALYST else "ANALYZE"
        elif threat >= 1:  action = "MONITOR"
        else:              action = actions[-1]  # idle action

        # Stress amplifies aggression
        if self.stress_level > 0.7 and action == "MONITOR":
            action = "ALERT"

        self.last_decision = action
        self.decision_count += 1
        return action

    def remember(self, event_type: str, threat: int, outcome: str):
        frame = AgentMemoryFrame(
            event_type=event_type, threat=threat,
            outcome=outcome, emotion=self.emotional_state,
            importance=min(1.0, threat/4.0 + 0.2)
        )
        self.episodic.append(frame)

        # Distill semantic facts
        if threat >= 3 and event_type not in self.semantic_facts:
            self.semantic_facts.append(f"threat≥3 via {event_type}")

    def memory_summary(self) -> dict:
        if not self.episodic:
            return {"episodes": 0, "avg_threat": 0, "top_facts": []}
        threats = [e.threat for e in self.episodic]
        return {
            "episodes":   len(self.episodic),
            "avg_threat": round(sum(threats)/len(threats), 2),
            "peak_threat":max(threats),
            "top_facts":  self.semantic_facts[-3:]
        }

@dataclass
class CognitiveAgent:
    id:           str  = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:         str  = ""
    role:         AgentRole  = AgentRole.WORKER
    state:        AgentState = AgentState.IDLE
    brain:        AgentBrain = field(default_factory=AgentBrain)

    # Social
    trust_scores: dict = field(default_factory=dict)   # agent_id → trust
    known_agents: list = field(default_factory=list)

    # Performance
    tasks_completed: int   = 0
    tasks_failed:    int   = 0
    consecutive_fails: int = 0
    uptime_start:    str   = field(default_factory=lambda: datetime.now().isoformat())
    last_active:     str   = field(default_factory=lambda: datetime.now().isoformat())

    # Spatial
    position:     dict = field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    zone:         str  = "general"

    # Specializations
    specializations: list = field(default_factory=list)
    load:         float = 0.0   # 0-1 current workload

    def trust_for(self, agent_id: str) -> float:
        return self.trust_scores.get(agent_id, 0.5)

    def update_trust(self, agent_id: str, delta: float):
        current = self.trust_scores.get(agent_id, 0.5)
        self.trust_scores[agent_id] = max(0.0, min(1.0, current + delta))

    def is_alive(self) -> bool:
        return self.state not in [AgentState.DEAD]

    def health_score(self) -> float:
        if self.tasks_completed + self.tasks_failed == 0:
            return 1.0
        success_rate = self.tasks_completed / (self.tasks_completed + self.tasks_failed)
        load_penalty = self.load * 0.2
        stress_penalty = self.brain.stress_level * 0.3
        return round(max(0.0, success_rate - load_penalty - stress_penalty), 3)

@dataclass
class ConsensusVote:
    id:          str  = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:   str  = field(default_factory=lambda: datetime.now().isoformat())
    proposal:    str  = ""
    proposer:    str  = ""
    votes:       dict = field(default_factory=dict)   # agent_id → bool
    weights:     dict = field(default_factory=dict)   # agent_id → trust weight
    result:      Optional[bool] = None
    consensus_type: str = ConsensusType.TRUST_WEIGHTED.value
    rationale:   str  = ""

@dataclass
class SwarmTask:
    id:          str  = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:   str  = field(default_factory=lambda: datetime.now().isoformat())
    task_type:   str  = ""
    priority:    int  = 1
    assigned_to: Optional[str] = None
    status:      str  = "PENDING"
    result:      dict = field(default_factory=dict)
    retries:     int  = 0
    deadline:    Optional[str] = None

@dataclass
class ThreatBroadcast:
    id:          str  = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:   str  = field(default_factory=lambda: datetime.now().isoformat())
    source_agent: str = ""
    threat_level: int = 0
    signal:      dict = field(default_factory=dict)
    acknowledged_by: list = field(default_factory=list)
    propagation_hops: int = 0

# ─── Database ─────────────────────────────────────────────────────────────────

class SwarmDB:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init()

    def _init(self):
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY, name TEXT, role TEXT, state TEXT,
                    tasks_completed INTEGER, tasks_failed INTEGER,
                    consecutive_fails INTEGER, uptime_start TEXT,
                    last_active TEXT, position TEXT, zone TEXT,
                    specializations TEXT, load REAL, trust_scores TEXT
                );
                CREATE TABLE IF NOT EXISTS consensus_votes (
                    id TEXT PRIMARY KEY, timestamp TEXT, proposal TEXT,
                    proposer TEXT, votes TEXT, weights TEXT,
                    result INTEGER, consensus_type TEXT, rationale TEXT
                );
                CREATE TABLE IF NOT EXISTS swarm_tasks (
                    id TEXT PRIMARY KEY, timestamp TEXT, task_type TEXT,
                    priority INTEGER, assigned_to TEXT, status TEXT,
                    result TEXT, retries INTEGER
                );
                CREATE TABLE IF NOT EXISTS threat_broadcasts (
                    id TEXT PRIMARY KEY, timestamp TEXT, source_agent TEXT,
                    threat_level INTEGER, signal TEXT,
                    acknowledged_by TEXT, propagation_hops INTEGER
                );
                CREATE TABLE IF NOT EXISTS swarm_memory (
                    id TEXT PRIMARY KEY, timestamp TEXT, event_type TEXT,
                    threat INTEGER, contributing_agents TEXT,
                    outcome TEXT, importance REAL
                );
                CREATE TABLE IF NOT EXISTS agent_events (
                    id TEXT PRIMARY KEY, timestamp TEXT, agent_id TEXT,
                    event_type TEXT, details TEXT
                );
            """)
            self.conn.commit()

    def save_agent(self, a: CognitiveAgent):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO agents VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (a.id, a.name, a.role.value, a.state.value,
                  a.tasks_completed, a.tasks_failed, a.consecutive_fails,
                  a.uptime_start, a.last_active,
                  json.dumps(a.position), a.zone,
                  json.dumps(a.specializations), a.load,
                  json.dumps(a.trust_scores)))
            self.conn.commit()

    def save_vote(self, v: ConsensusVote):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO consensus_votes VALUES (?,?,?,?,?,?,?,?,?)
            """, (v.id, v.timestamp, v.proposal, v.proposer,
                  json.dumps(v.votes), json.dumps(v.weights),
                  int(v.result) if v.result is not None else None,
                  v.consensus_type, v.rationale))
            self.conn.commit()

    def save_broadcast(self, b: ThreatBroadcast):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO threat_broadcasts VALUES (?,?,?,?,?,?,?)
            """, (b.id, b.timestamp, b.source_agent, b.threat_level,
                  json.dumps(b.signal), json.dumps(b.acknowledged_by),
                  b.propagation_hops))
            self.conn.commit()

    def save_swarm_memory(self, event_type: str, threat: int,
                          agents: list, outcome: str, importance: float):
        with self.lock:
            self.conn.execute("""
                INSERT INTO swarm_memory VALUES (?,?,?,?,?,?,?)
            """, (str(uuid.uuid4())[:8], datetime.now().isoformat(),
                  event_type, threat, json.dumps(agents), outcome, importance))
            self.conn.commit()

    def log_event(self, agent_id: str, event_type: str, details: dict):
        with self.lock:
            self.conn.execute(
                "INSERT INTO agent_events VALUES (?,?,?,?,?)",
                (str(uuid.uuid4())[:8], datetime.now().isoformat(),
                 agent_id, event_type, json.dumps(details))
            )
            self.conn.commit()

    def get_agents(self):
        with self.lock:
            return self.conn.execute(
                "SELECT id,name,role,state,tasks_completed,tasks_failed,load FROM agents"
            ).fetchall()

    def get_votes(self, limit=20):
        with self.lock:
            return self.conn.execute(
                "SELECT id,timestamp,proposal,result,rationale FROM consensus_votes ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()

    def get_broadcasts(self, limit=20):
        with self.lock:
            return self.conn.execute(
                "SELECT id,timestamp,source_agent,threat_level,propagation_hops FROM threat_broadcasts ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()

# ─── Trust Mesh ───────────────────────────────────────────────────────────────

class TrustMesh:
    """
    Agents maintain trust scores for each other.
    Low-trust agents get isolated automatically.
    Trust propagates — if A trusts B and B trusts C, A gains slight trust in C.
    """

    def __init__(self):
        self.mesh: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(lambda: 0.5))
        self.isolated: set = set()

    def observe(self, observer: str, subject: str, outcome: str, threat: int):
        delta = {
            "SUCCESS": +0.06, "COOPERATIVE": +0.05,
            "FAILURE": -0.08, "SUSPICIOUS": -0.12,
            "THREAT_RAISED": -0.15, "THREAT_RESOLVED": +0.10
        }.get(outcome, 0.0)

        if threat >= 3: delta = min(delta, -0.12)

        current = self.mesh[observer][subject]
        self.mesh[observer][subject] = max(0.0, min(1.0, current + delta))

        # Check isolation threshold
        avg_trust = self._avg_trust_for(subject)
        if avg_trust < TRUST_THRESHOLD:
            self.isolated.add(subject)
        elif subject in self.isolated and avg_trust > TRUST_THRESHOLD + 0.1:
            self.isolated.discard(subject)

    def propagate(self, agent_a: str, agent_b: str, agent_c: str):
        """If A trusts B and B trusts C → A gains slight trust in C."""
        ab = self.mesh[agent_a][agent_b]
        bc = self.mesh[agent_b][agent_c]
        if ab > 0.6 and bc > 0.6:
            current = self.mesh[agent_a][agent_c]
            self.mesh[agent_a][agent_c] = min(1.0, current + 0.02)

    def _avg_trust_for(self, subject: str) -> float:
        scores = [self.mesh[obs][subject] for obs in self.mesh if obs != subject]
        return sum(scores) / len(scores) if scores else 0.5

    def get_trust_matrix(self, agents: list) -> dict:
        matrix = {}
        for a in agents:
            matrix[a] = {b: round(self.mesh[a][b], 2) for b in agents if b != a}
        return matrix

    def is_isolated(self, agent_id: str) -> bool:
        return agent_id in self.isolated


# ─── Swarm Consensus ──────────────────────────────────────────────────────────

class SwarmConsensus:
    """
    Emergent voting — agents vote on decisions.
    Trust-weighted: high-trust agents' votes count more.
    Coordinator veto: coordinator can block dangerous proposals.
    """

    def __init__(self, db: SwarmDB, trust_mesh: TrustMesh):
        self.db   = db
        self.trust = trust_mesh
        self.votes: list[ConsensusVote] = []

    def propose(self, proposal: str, proposer: str,
                agents: list[CognitiveAgent],
                consensus_type: ConsensusType = ConsensusType.TRUST_WEIGHTED) -> ConsensusVote:

        vote = ConsensusVote(
            proposal=proposal, proposer=proposer,
            consensus_type=consensus_type.value
        )

        eligible = [a for a in agents
                    if a.is_alive() and a.state != AgentState.ISOLATED
                    and a.id != proposer]

        for agent in eligible:
            # Each agent votes based on their brain + role
            perception = agent.brain.last_perception
            threat     = perception.get("threat", 0)

            # Role-based vote bias
            yes_bias = {
                AgentRole.DEFENDER:    0.7 if "BLOCK" in proposal or "ALERT" in proposal else 0.4,
                AgentRole.ANALYST:     0.6 if "ANALYZE" in proposal else 0.45,
                AgentRole.COORDINATOR: 0.55,
                AgentRole.SCOUT:       0.65 if "INVESTIGATE" in proposal else 0.5,
                AgentRole.SENTINEL:    0.6 if "MONITOR" in proposal else 0.45,
                AgentRole.HEALER:      0.7 if "REPAIR" in proposal or "SPAWN" in proposal else 0.4,
                AgentRole.WORKER:      0.5,
            }.get(agent.role, 0.5)

            # Threat amplifies yes votes for defensive actions
            if threat >= 3 and any(w in proposal for w in ["BLOCK","ESCALATE","ALERT"]):
                yes_bias = min(0.95, yes_bias + 0.25)

            # Stress makes agents more trigger-happy
            yes_bias = min(0.95, yes_bias + agent.brain.stress_level * 0.1)

            vote.votes[agent.id]   = random.random() < yes_bias
            vote.weights[agent.id] = self.trust._avg_trust_for(agent.id)

        vote.result, vote.rationale = self._tally(vote, agents)
        self.db.save_vote(vote)
        self.votes.append(vote)
        return vote

    def _tally(self, vote: ConsensusVote,
               agents: list[CognitiveAgent]) -> tuple[bool, str]:
        if not vote.votes:
            return False, "No eligible voters."

        # Check coordinator veto
        coordinators = [a for a in agents if a.role == AgentRole.COORDINATOR and a.is_alive()]
        for coord in coordinators:
            if coord.id in vote.votes and not vote.votes[coord.id]:
                if "ESCALATE" in vote.proposal or "BLOCK" in vote.proposal:
                    # Coordinator can veto aggressive actions
                    return False, f"Coordinator {coord.name} vetoed {vote.proposal}."

        if vote.consensus_type == ConsensusType.TRUST_WEIGHTED.value:
            yes_weight = sum(vote.weights.get(aid, 0.5)
                            for aid, v in vote.votes.items() if v)
            total_weight = sum(vote.weights.values()) or 1.0
            ratio = yes_weight / total_weight
            passed = ratio >= CONSENSUS_QUORUM
            return passed, (
                f"Trust-weighted: {ratio:.0%} support "
                f"({'PASSED' if passed else 'FAILED'}, quorum={CONSENSUS_QUORUM:.0%})"
            )
        else:
            yes_count = sum(1 for v in vote.votes.values() if v)
            ratio     = yes_count / len(vote.votes)
            passed    = ratio >= CONSENSUS_QUORUM
            return passed, (
                f"Simple majority: {yes_count}/{len(vote.votes)} "
                f"({'PASSED' if passed else 'FAILED'})"
            )


# ─── Threat Propagation ───────────────────────────────────────────────────────

class ThreatPropagation:
    """
    One agent detects threat → broadcasts to swarm → all agents elevate awareness.
    Propagation is hop-based: closest agents first, then ripples outward.
    """

    def __init__(self, db: SwarmDB):
        self.db = db
        self.active_broadcasts: list[ThreatBroadcast] = []

    def broadcast(self, source: CognitiveAgent,
                  threat: int, signal: dict,
                  all_agents: list[CognitiveAgent]) -> ThreatBroadcast:

        bc = ThreatBroadcast(
            source_agent=source.id,
            threat_level=threat,
            signal={"threat": threat, "source_role": source.role.value,
                    "signal_summary": signal.get("conclusion", "")[:80]}
        )

        # Sort agents by proximity (distance in spatial map)
        def dist(a):
            dx = a.position["x"] - source.position["x"]
            dy = a.position["y"] - source.position["y"]
            return math.sqrt(dx*dx + dy*dy)

        sorted_agents = sorted(
            [a for a in all_agents if a.id != source.id and a.is_alive()],
            key=dist
        )

        # Propagate in hops
        hop = 0
        for agent in sorted_agents:
            if agent.state == AgentState.ISOLATED:
                continue

            # Each agent raises their own threat awareness
            agent.brain.stress_level = min(1.0, agent.brain.stress_level + threat * 0.08)

            # State change based on threat level
            if threat >= 4:
                agent.state = AgentState.STRESSED
            elif threat >= 3 and agent.state == AgentState.IDLE:
                agent.state = AgentState.ACTIVE
            elif threat >= 2 and agent.role in [AgentRole.DEFENDER, AgentRole.SENTINEL]:
                agent.state = AgentState.ACTIVE

            bc.acknowledged_by.append(agent.id)
            hop += 1

        bc.propagation_hops = hop
        self.db.save_broadcast(bc)
        self.active_broadcasts.append(bc)
        return bc

    def resolve(self, broadcast_id: str, all_agents: list[CognitiveAgent]):
        """Threat resolved — agents calm down."""
        for agent in all_agents:
            if agent.state == AgentState.STRESSED:
                agent.state = AgentState.ACTIVE
            agent.brain.stress_level = max(0.0, agent.brain.stress_level - 0.2)


# ─── Role Fluidity Engine ─────────────────────────────────────────────────────

class RoleFluidity:
    """
    Agents shift roles dynamically based on:
    - Swarm phase (calm/alert/crisis)
    - Agent health
    - Swarm needs (too many workers, not enough defenders)
    """

    PHASE_IDEAL_COMPOSITION = {
        SwarmPhase.CALM:     {AgentRole.WORKER:0.4, AgentRole.SENTINEL:0.2,
                              AgentRole.ANALYST:0.2, AgentRole.COORDINATOR:0.1,
                              AgentRole.SCOUT:0.1},
        SwarmPhase.ALERT:    {AgentRole.DEFENDER:0.3, AgentRole.SENTINEL:0.25,
                              AgentRole.ANALYST:0.2, AgentRole.COORDINATOR:0.1,
                              AgentRole.SCOUT:0.15},
        SwarmPhase.CRISIS:   {AgentRole.DEFENDER:0.4, AgentRole.COORDINATOR:0.15,
                              AgentRole.HEALER:0.15, AgentRole.ANALYST:0.2,
                              AgentRole.SENTINEL:0.1},
        SwarmPhase.RECOVERY: {AgentRole.HEALER:0.3, AgentRole.WORKER:0.3,
                              AgentRole.ANALYST:0.2, AgentRole.SENTINEL:0.1,
                              AgentRole.COORDINATOR:0.1},
    }

    def rebalance(self, agents: list[CognitiveAgent],
                  phase: SwarmPhase, db: SwarmDB) -> list[tuple]:
        """Returns list of (agent, old_role, new_role) transitions."""
        transitions = []
        ideal       = self.PHASE_IDEAL_COMPOSITION.get(phase, {})
        alive       = [a for a in agents if a.is_alive() and
                       a.state not in [AgentState.ISOLATED, AgentState.DEAD]]
        if not alive: return transitions

        # Count current composition
        current_counts = defaultdict(int)
        for a in alive:
            current_counts[a.role] += 1

        # Find over/under-represented roles
        n = len(alive)
        for role, target_frac in ideal.items():
            target_count  = round(target_frac * n)
            current_count = current_counts.get(role, 0)

            if current_count < target_count:
                # Need more of this role — convert idle workers
                candidates = [a for a in alive
                              if a.role == AgentRole.WORKER
                              and a.state == AgentState.IDLE
                              and a.role != role][:target_count - current_count]
                for agent in candidates:
                    old_role   = agent.role
                    agent.role = role
                    agent.specializations.append(f"adapted_{phase.value.lower()}")
                    db.save_agent(agent)
                    db.log_event(agent.id, "ROLE_SHIFT",
                                {"old": old_role.value, "new": role.value, "phase": phase.value})
                    transitions.append((agent, old_role, role))

        return transitions


# ─── Agent Lifecycle ──────────────────────────────────────────────────────────

class AgentLifecycle:
    """
    Agents are born, can fail, die, and be reborn.
    Swarm self-heals — healers detect dead agents and spawn replacements.
    """

    def __init__(self, db: SwarmDB):
        self.db        = db
        self.dead_agents: list[str] = []
        self.spawn_queue: deque = deque()

    def check_health(self, agents: list[CognitiveAgent]) -> list[CognitiveAgent]:
        """Kill agents that have failed too many times."""
        killed = []
        for agent in agents:
            if (agent.consecutive_fails >= AGENT_DEATH_THRESHOLD and
                    agent.state != AgentState.DEAD):
                agent.state = AgentState.DEAD
                self.dead_agents.append(agent.id)
                self.db.log_event(agent.id, "DEATH",
                    {"reason": "consecutive_failures",
                     "count": agent.consecutive_fails})
                killed.append(agent)
        return killed

    def spawn(self, role: AgentRole, zone: str,
              parent_id: Optional[str] = None) -> CognitiveAgent:
        """Spawn a new agent, optionally inheriting parent's memory."""
        n    = len(self.dead_agents) + 1
        name = f"{role.value[:3].lower()}_{n:03d}"
        pos  = {"x": round(random.uniform(-8, 8), 2),
                "y": round(random.uniform(-8, 8), 2)}

        agent = CognitiveAgent(
            name=name, role=role,
            state=AgentState.RESPAWNING,
            position=pos, zone=zone,
            specializations=[f"born_from_{parent_id[:4]}" if parent_id else "original"]
        )
        # Brief respawn period
        time.sleep(0.01)
        agent.state = AgentState.IDLE
        self.db.save_agent(agent)
        self.db.log_event(agent.id, "SPAWN",
            {"role": role.value, "parent": parent_id or "none", "zone": zone})
        return agent

    def heal(self, dead_agent: CognitiveAgent,
             healer: CognitiveAgent,
             all_agents: list[CognitiveAgent]) -> CognitiveAgent:
        """Healer redistributes dead agent's tasks and spawns replacement."""
        # Spawn replacement with same role
        replacement = self.spawn(dead_agent.role, dead_agent.zone, dead_agent.id)
        self.db.log_event(healer.id, "HEAL",
            {"dead": dead_agent.id, "replacement": replacement.id})
        return replacement


# ─── Swarm Spatial Map ────────────────────────────────────────────────────────

class SwarmSpatialMap:
    """
    Agents track each other's positions and specializations.
    Enables proximity-based communication and task assignment.
    """

    def __init__(self):
        self.positions: dict[str, dict] = {}
        self.zones:     dict[str, list] = defaultdict(list)

    def update(self, agent: CognitiveAgent):
        self.positions[agent.id] = {
            "x": agent.position["x"], "y": agent.position["y"],
            "role": agent.role.value, "state": agent.state.value,
            "zone": agent.zone
        }
        # Zone membership
        for zone_list in self.zones.values():
            if agent.id in zone_list:
                zone_list.remove(agent.id)
        self.zones[agent.zone].append(agent.id)

    def nearest(self, agent: CognitiveAgent, role: Optional[AgentRole],
                agents: list[CognitiveAgent], n: int = 3) -> list[CognitiveAgent]:
        """Find n nearest agents, optionally filtered by role."""
        candidates = [a for a in agents
                      if a.id != agent.id and a.is_alive()
                      and (role is None or a.role == role)]

        def dist(a):
            dx = a.position["x"] - agent.position["x"]
            dy = a.position["y"] - agent.position["y"]
            return math.sqrt(dx*dx + dy*dy)

        return sorted(candidates, key=dist)[:n]

    def drift(self, agent: CognitiveAgent, target: dict, speed: float = 0.1):
        """Move agent toward target position (flocking behavior)."""
        dx = target["x"] - agent.position["x"]
        dy = target["y"] - agent.position["y"]
        dist = math.sqrt(dx*dx + dy*dy)
        if dist > 0.01:
            agent.position["x"] += (dx/dist) * speed
            agent.position["y"] += (dy/dist) * speed

    def snapshot(self, agents: list[CognitiveAgent]) -> dict:
        role_counts   = defaultdict(int)
        state_counts  = defaultdict(int)
        zone_counts   = defaultdict(int)
        for a in agents:
            if a.is_alive():
                role_counts[a.role.value]  += 1
                state_counts[a.state.value]+= 1
                zone_counts[a.zone]        += 1
        return {
            "total_agents":  len(agents),
            "alive":         sum(1 for a in agents if a.is_alive()),
            "dead":          sum(1 for a in agents if a.state == AgentState.DEAD),
            "isolated":      sum(1 for a in agents if a.state == AgentState.ISOLATED),
            "by_role":       dict(role_counts),
            "by_state":      dict(state_counts),
            "by_zone":       dict(zone_counts)
        }


# ─── Swarm Memory ─────────────────────────────────────────────────────────────

class SwarmMemory:
    """
    Collective memory shared across all agents.
    Individual agents contribute — swarm remembers collectively.
    High-importance events get replayed to new agents on spawn.
    """

    def __init__(self, db: SwarmDB, capacity: int = 1000):
        self.db       = db
        self.capacity = capacity
        self.collective: deque = deque(maxlen=capacity)
        self.highlights: list  = []  # top 10 most important memories

    def record(self, event_type: str, threat: int,
               agents: list[str], outcome: str):
        importance = min(1.0, threat/4.0 + len(agents)*0.05)
        entry = {
            "id":        str(uuid.uuid4())[:8],
            "timestamp": datetime.now().isoformat(),
            "event_type":event_type,
            "threat":    threat,
            "agents":    agents,
            "outcome":   outcome,
            "importance":round(importance, 3)
        }
        self.collective.append(entry)
        self.db.save_swarm_memory(event_type, threat, agents, outcome, importance)

        # Update highlights
        self.highlights.append(entry)
        self.highlights.sort(key=lambda x: x["importance"], reverse=True)
        self.highlights = self.highlights[:10]

    def recall(self, event_type: str = "", threat_min: int = 0) -> list:
        return [e for e in self.collective
                if (not event_type or e["event_type"] == event_type)
                and e["threat"] >= threat_min][-10:]

    def brief_new_agent(self, agent: CognitiveAgent):
        """Inject swarm highlights into new agent's brain."""
        for mem in self.highlights[:5]:
            agent.brain.remember(
                mem["event_type"], mem["threat"], mem["outcome"]
            )


# ─── Emergent Behavior Engine ─────────────────────────────────────────────────

class EmergentBehavior:
    """
    Complex patterns emerge from simple agent rules.
    Flocking, clustering, cascade detection, collective intelligence.
    """

    def __init__(self, spatial: SwarmSpatialMap):
        self.spatial = spatial

    def flock(self, agents: list[CognitiveAgent]):
        """Reynolds flocking — cohesion + alignment + separation."""
        alive = [a for a in agents if a.is_alive()]
        if len(alive) < 2: return

        for agent in alive:
            neighbors = self.spatial.nearest(agent, None, alive, n=5)
            if not neighbors: continue

            # Cohesion: move toward center of neighbors
            cx = sum(n.position["x"] for n in neighbors) / len(neighbors)
            cy = sum(n.position["y"] for n in neighbors) / len(neighbors)

            # Separation: avoid too-close neighbors
            too_close = [n for n in neighbors
                         if math.sqrt((n.position["x"]-agent.position["x"])**2 +
                                      (n.position["y"]-agent.position["y"])**2) < 0.5]

            if too_close:
                # Push away
                agent.position["x"] -= 0.05
                agent.position["y"] -= 0.05
            else:
                # Pull toward centroid
                self.spatial.drift(agent, {"x": cx, "y": cy}, speed=0.03)

    def detect_clustering(self, agents: list[CognitiveAgent]) -> list[dict]:
        """Identify emergent clusters of agents."""
        alive = [a for a in agents if a.is_alive()]
        visited = set()
        clusters = []

        for agent in alive:
            if agent.id in visited: continue
            cluster = [agent]
            visited.add(agent.id)
            neighbors = self.spatial.nearest(agent, None, alive, n=6)
            for n in neighbors:
                if n.id not in visited:
                    dist = math.sqrt((n.position["x"]-agent.position["x"])**2 +
                                     (n.position["y"]-agent.position["y"])**2)
                    if dist < 2.0:
                        cluster.append(n)
                        visited.add(n.id)

            if len(cluster) >= 2:
                clusters.append({
                    "size":  len(cluster),
                    "roles": [a.role.value for a in cluster],
                    "center": {"x": round(sum(a.position["x"] for a in cluster)/len(cluster), 2),
                               "y": round(sum(a.position["y"] for a in cluster)/len(cluster), 2)},
                    "avg_stress": round(sum(a.brain.stress_level for a in cluster)/len(cluster), 2)
                })
        return sorted(clusters, key=lambda c: c["size"], reverse=True)[:5]

    def cascade_check(self, agents: list[CognitiveAgent]) -> Optional[str]:
        """Detect if a failure cascade is beginning."""
        stressed  = sum(1 for a in agents if a.state == AgentState.STRESSED)
        dead      = sum(1 for a in agents if a.state == AgentState.DEAD)
        isolated  = sum(1 for a in agents if a.state == AgentState.ISOLATED)
        alive     = sum(1 for a in agents if a.is_alive())

        if alive == 0: return "TOTAL_COLLAPSE"
        stress_ratio = stressed / max(alive, 1)
        dead_ratio   = dead / max(len(agents), 1)

        if dead_ratio > 0.4:   return "CASCADE_CRITICAL"
        if stress_ratio > 0.6: return "CASCADE_WARNING"
        if stressed > 0 and dead > 0: return "CASCADE_DEVELOPING"
        return None


# ─── FORGE Swarm v2 (Main) ────────────────────────────────────────────────────

class ForgeSwarmV2:
    def __init__(self, n_agents: int = 8):
        self.db         = SwarmDB()
        self.trust_mesh = TrustMesh()
        self.consensus  = SwarmConsensus(self.db, self.trust_mesh)
        self.propagation= ThreatPropagation(self.db)
        self.role_engine= RoleFluidity()
        self.lifecycle  = AgentLifecycle(self.db)
        self.spatial    = SwarmSpatialMap()
        self.swarm_mem  = SwarmMemory(self.db)
        self.emergent   = EmergentBehavior(self.spatial)

        self.agents:    list[CognitiveAgent] = []
        self.phase:     SwarmPhase = SwarmPhase.CALM
        self.tick:      int = 0
        self.task_queue: deque = deque()
        self.lock       = threading.Lock()

        self._spawn_initial(n_agents)

    def _spawn_initial(self, n: int):
        roles = [
            AgentRole.COORDINATOR,
            AgentRole.SCOUT, AgentRole.SCOUT,
            AgentRole.DEFENDER, AgentRole.DEFENDER,
            AgentRole.ANALYST,
            AgentRole.SENTINEL,
            AgentRole.HEALER,
        ]
        roles = (roles * math.ceil(n / len(roles)))[:n]
        zones = ["alpha","beta","gamma","delta"]

        for i, role in enumerate(roles):
            agent = CognitiveAgent(
                name=f"{role.value[:3].lower()}_{i:02d}",
                role=role, state=AgentState.IDLE,
                position={
                    "x": round(math.cos(i * 2*math.pi/n) * 5, 2),
                    "y": round(math.sin(i * 2*math.pi/n) * 5, 2)
                },
                zone=zones[i % len(zones)]
            )
            # Brief each new agent with swarm memory
            self.swarm_mem.brief_new_agent(agent)
            self.agents.append(agent)
            self.spatial.update(agent)
            self.db.save_agent(agent)

    def process_signal(self, signal: dict) -> dict:
        """
        Main swarm processing loop for an incoming signal.
        All cognitive layers fire in sequence.
        """
        self.tick += 1
        threat = signal.get("threat", 0)
        results = {
            "tick": self.tick, "threat": threat,
            "phase_before": self.phase.value,
            "actions": [], "consensus": None,
            "broadcast": None, "role_shifts": [],
            "cascade": None, "clusters": []
        }

        # 1. Update swarm phase
        old_phase  = self.phase
        self.phase = self._assess_phase(threat)
        if self.phase != old_phase:
            results["phase_change"] = f"{old_phase.value} → {self.phase.value}"

        # 2. Each agent perceives and decides
        agent_decisions = []
        for agent in self.agents:
            if not agent.is_alive(): continue
            perceived = agent.brain.perceive(signal)
            decision  = agent.brain.decide(threat, agent.role, self.phase)
            agent.brain.remember("signal", threat, decision)
            agent.last_active = datetime.now().isoformat()
            agent_decisions.append((agent, decision))
            self.spatial.update(agent)

        results["actions"] = [
            {"agent": a.name, "role": a.role.value, "decision": d}
            for a, d in agent_decisions[:6]
        ]

        # 3. Threat propagation if needed
        if threat >= THREAT_BROADCAST_THRESHOLD:
            source = next(
                (a for a in self.agents
                 if a.role == AgentRole.SCOUT and a.is_alive()), self.agents[0]
            )
            bc = self.propagation.broadcast(source, threat, signal, self.agents)
            results["broadcast"] = {
                "source": source.name, "threat": threat,
                "propagated_to": bc.propagation_hops
            }
            self.swarm_mem.record("THREAT_BROADCAST", threat,
                                  [source.id], f"propagated to {bc.propagation_hops} agents")

        # 4. Consensus vote on major decisions
        if threat >= 2:
            proposal = ("BLOCK_AND_ESCALATE" if threat >= 3 else "ALERT_AND_INVESTIGATE")
            vote = self.consensus.propose(
                proposal, self.agents[0].id, self.agents,
                ConsensusType.TRUST_WEIGHTED
            )
            results["consensus"] = {
                "proposal": vote.proposal,
                "result":   "PASSED" if vote.result else "FAILED",
                "rationale":vote.rationale
            }

        # 5. Role fluidity rebalancing
        if self.tick % 3 == 0:
            transitions = self.role_engine.rebalance(self.agents, self.phase, self.db)
            results["role_shifts"] = [
                {"agent": a.name, "from": old.value, "to": new.value}
                for a, old, new in transitions
            ]

        # 6. Lifecycle — health checks
        killed = self.lifecycle.check_health(self.agents)
        for dead in killed:
            healers = [a for a in self.agents
                       if a.role == AgentRole.HEALER and a.is_alive()]
            if healers:
                replacement = self.lifecycle.heal(dead, healers[0], self.agents)
                self.swarm_mem.brief_new_agent(replacement)
                self.agents.append(replacement)
                self.spatial.update(replacement)
                results["actions"].append({
                    "agent": healers[0].name,
                    "role": "HEALER",
                    "decision": f"SPAWNED {replacement.name} to replace {dead.name}"
                })

        # 7. Emergent behavior
        self.emergent.flock(self.agents)
        results["clusters"] = self.emergent.detect_clustering(self.agents)
        cascade = self.emergent.cascade_check(self.agents)
        if cascade:
            results["cascade"] = cascade

        # 8. Trust mesh updates
        for agent, decision in agent_decisions:
            outcome = "SUCCESS" if decision not in ["STANDBY"] else "SUCCESS"
            for other, _ in agent_decisions[:3]:
                if other.id != agent.id:
                    self.trust_mesh.observe(agent.id, other.id, outcome, threat)

        # 9. Record in swarm memory
        self.swarm_mem.record(
            "SIGNAL_PROCESSED", threat,
            [a.id for a, _ in agent_decisions[:5]],
            f"phase={self.phase.value} consensus={'Y' if results.get('consensus') else 'N'}"
        )

        results["phase_after"] = self.phase.value
        results["alive_agents"] = sum(1 for a in self.agents if a.is_alive())
        return results

    def _assess_phase(self, threat: int) -> SwarmPhase:
        dead    = sum(1 for a in self.agents if a.state == AgentState.DEAD)
        stressed= sum(1 for a in self.agents if a.state == AgentState.STRESSED)
        if threat >= 4 or dead >= 2:           return SwarmPhase.CRISIS
        if threat >= 2 or stressed >= 2:       return SwarmPhase.ALERT
        if dead > 0 or stressed > 0:           return SwarmPhase.RECOVERY
        return SwarmPhase.CALM

    def get_status(self) -> dict:
        snap = self.spatial.snapshot(self.agents)
        return {
            "version":        VERSION,
            "tick":           self.tick,
            "phase":          self.phase.value,
            "swarm_snapshot": snap,
            "memory":         len(self.swarm_mem.collective),
            "highlights":     len(self.swarm_mem.highlights),
            "votes_cast":     len(self.consensus.votes),
            "broadcasts":     len(self.propagation.active_broadcasts),
            "isolated_agents":list(self.trust_mesh.isolated)
        }


# ─── Rich UI ──────────────────────────────────────────────────────────────────

def render_tick(result: dict, swarm: ForgeSwarmV2):
    if not HAS_RICH: return

    threat      = result["threat"]
    phase       = result["phase_after"]
    phase_color = {"CALM":"green","ALERT":"yellow","CRISIS":"bright_red","RECOVERY":"cyan"}.get(phase,"white")
    threat_color= {0:"green",1:"blue",2:"yellow",3:"red",4:"bright_red"}.get(threat,"white")

    console.print(Rule(
        f"[bold cyan]⬡ FORGE SWARM v2[/bold cyan]  "
        f"[dim]Tick {result['tick']}[/dim]  "
        f"[{phase_color}]Phase: {phase}[/{phase_color}]  "
        f"[{threat_color}]Threat: {threat}[/{threat_color}]"
    ))

    # Phase change banner
    if "phase_change" in result:
        console.print(Panel(
            f"[bold {phase_color}]⚡ PHASE TRANSITION: {result['phase_change']}[/bold {phase_color}]",
            border_style=phase_color
        ))

    # Agent decisions + consensus side by side
    actions_table = Table(box=box.SIMPLE, title="Agent Decisions", title_style="dim")
    actions_table.add_column("Agent", style="cyan", width=12)
    actions_table.add_column("Role",  width=12)
    actions_table.add_column("Decision", width=16)
    for act in result["actions"][:6]:
        dec_color = {"BLOCK":"bright_red","ESCALATE":"red","ALERT":"yellow",
                     "ANALYZE":"cyan","MONITOR":"blue","STANDBY":"dim",
                     "COORDINATE":"magenta","INVESTIGATE":"cyan"}.get(act["decision"],"white")
        actions_table.add_row(
            act["agent"], act["role"],
            f"[{dec_color}]{act['decision']}[/{dec_color}]"
        )

    # Right panel: broadcast + consensus
    right_lines = []
    if result.get("broadcast"):
        bc = result["broadcast"]
        right_lines.append(
            f"[bold red]📡 BROADCAST[/bold red]\n"
            f"  Source: [cyan]{bc['source']}[/cyan]\n"
            f"  Threat: [{threat_color}]{bc['threat']}[/{threat_color}]\n"
            f"  Reached: {bc['propagated_to']} agents\n"
        )
    if result.get("consensus"):
        cv = result["consensus"]
        res_color = "green" if cv["result"] == "PASSED" else "red"
        right_lines.append(
            f"[bold]🗳 CONSENSUS[/bold]\n"
            f"  Proposal: [cyan]{cv['proposal']}[/cyan]\n"
            f"  Result: [{res_color}]{cv['result']}[/{res_color}]\n"
            f"  [dim]{cv['rationale'][:50]}[/dim]"
        )
    if not right_lines:
        right_lines.append("[dim]No broadcast or consensus this tick.[/dim]")

    right_panel = Panel("\n".join(right_lines), title="[bold]Swarm Events[/bold]",
                        border_style=threat_color)

    console.print(Columns([
        Panel(actions_table, border_style="dim"),
        right_panel
    ]))

    # Role shifts
    if result["role_shifts"]:
        shifts_text = "  ".join(
            f"[cyan]{s['agent']}[/cyan]: {s['from']}→[yellow]{s['to']}[/yellow]"
            for s in result["role_shifts"]
        )
        console.print(Panel(shifts_text, title="[bold]Role Fluidity[/bold]",
                            border_style="yellow"))

    # Clusters
    if result["clusters"]:
        cl = result["clusters"][0]
        console.print(
            f"  [dim]Largest cluster: {cl['size']} agents | "
            f"roles: {', '.join(set(cl['roles']))} | "
            f"avg stress: {cl['avg_stress']:.2f}[/dim]"
        )

    # Cascade warning
    if result.get("cascade"):
        console.print(Panel(
            f"[bold bright_red]⚠ CASCADE: {result['cascade']}[/bold bright_red]",
            border_style="bright_red"
        ))

    alive = result["alive_agents"]
    console.print(f"  [dim]Alive: {alive} agents[/dim]")


def render_final_status(swarm: ForgeSwarmV2):
    if not HAS_RICH: return

    console.print(Rule("[bold cyan]⬡ SWARM FINAL STATUS[/bold cyan]"))
    status = swarm.get_status()

    # Agent roster
    roster = Table(box=box.ROUNDED, title="Agent Roster", border_style="cyan")
    roster.add_column("Name",   style="cyan", width=12)
    roster.add_column("Role",   width=12)
    roster.add_column("State",  width=12)
    roster.add_column("Health", justify="right", width=8)
    roster.add_column("Stress", justify="right", width=8)
    roster.add_column("Memory", justify="right", width=8)
    roster.add_column("Zone",   width=8)

    for agent in sorted(swarm.agents, key=lambda a: a.role.value):
        state_color = {
            "IDLE":"dim","ACTIVE":"green","THINKING":"cyan",
            "VOTING":"yellow","EXECUTING":"blue","STRESSED":"red",
            "ISOLATED":"bright_red","DEAD":"dim red","RESPAWNING":"magenta"
        }.get(agent.state.value, "white")
        health = agent.health_score()
        h_color= "green" if health > 0.7 else "yellow" if health > 0.4 else "red"
        mem    = agent.brain.memory_summary()

        roster.add_row(
            agent.name,
            agent.role.value[:10],
            f"[{state_color}]{agent.state.value}[/{state_color}]",
            f"[{h_color}]{health:.2f}[/{h_color}]",
            f"{agent.brain.stress_level:.2f}",
            str(mem["episodes"]),
            agent.zone
        )
    console.print(roster)

    # Swarm memory highlights
    if swarm.swarm_mem.highlights:
        console.print(Rule("[dim]Swarm Memory Highlights[/dim]"))
        mem_table = Table(box=box.SIMPLE, show_header=False)
        mem_table.add_column("", style="dim", width=10)
        mem_table.add_column("", width=50)
        mem_table.add_column("", justify="right", width=8)
        for h in swarm.swarm_mem.highlights[:5]:
            tc = {0:"green",1:"blue",2:"yellow",3:"red",4:"bright_red"}.get(h["threat"],"white")
            mem_table.add_row(
                f"[{tc}]T={h['threat']}[/{tc}]",
                h["event_type"] + " — " + h["outcome"][:40],
                f"imp={h['importance']:.2f}"
            )
        console.print(mem_table)

    # Stats
    stats_table = Table(title="SWARM STATS", box=box.DOUBLE_EDGE, border_style="cyan")
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value",  style="white")
    stats_table.add_row("Version",       VERSION)
    stats_table.add_row("Total Ticks",   str(status["tick"]))
    stats_table.add_row("Final Phase",   status["phase"])
    stats_table.add_row("Alive Agents",  str(status["swarm_snapshot"]["alive"]))
    stats_table.add_row("Dead Agents",   str(status["swarm_snapshot"]["dead"]))
    stats_table.add_row("Votes Cast",    str(status["votes_cast"]))
    stats_table.add_row("Broadcasts",    str(status["broadcasts"]))
    stats_table.add_row("Swarm Memories",str(status["memory"]))
    stats_table.add_row("Isolated",      str(len(status["isolated_agents"])))
    console.print(stats_table)


def run_demo():
    if HAS_RICH:
        console.print(Panel.fit(
            "[bold cyan]FORGE SWARM v2[/bold cyan]\n"
            "[dim]Cognitive Swarm Intelligence — Agents That Think[/dim]\n"
            f"[dim]Version {VERSION}  |  8 agents  |  Full cognitive loop[/dim]",
            border_style="cyan"
        ))

    swarm = ForgeSwarmV2(n_agents=8)

    # A story of escalating threat — the swarm responds collectively
    signals = [
        {"threat": 0, "anomaly": False, "conclusion": "✓ All systems nominal",
         "emotion": "neutral"},
        {"threat": 0, "anomaly": False, "conclusion": "✓ Routine patrol complete",
         "emotion": "trust"},
        {"threat": 1, "anomaly": False, "conclusion": "ℹ Unknown entity logged at perimeter",
         "emotion": "surprise"},
        {"threat": 2, "anomaly": False, "conclusion": "⚠ Suspicious access pattern detected",
         "emotion": "fear"},
        {"threat": 2, "anomaly": True,  "conclusion": "⚠ Anomaly confirmed — coercive entity",
         "emotion": "anger"},
        {"threat": 3, "anomaly": True,  "conclusion": "⚡ Intrusion attempt — multiple vectors",
         "emotion": "anger"},
        {"threat": 4, "anomaly": True,  "conclusion": "🔴 CRITICAL — breach confirmed, weapon detected",
         "emotion": "fear"},
        {"threat": 4, "anomaly": True,  "conclusion": "🔴 CRITICAL — cascade spreading",
         "emotion": "fear"},
        {"threat": 2, "anomaly": False, "conclusion": "⚠ Threat partially contained",
         "emotion": "surprise"},
        {"threat": 1, "anomaly": False, "conclusion": "ℹ Situation stabilizing",
         "emotion": "neutral"},
        {"threat": 0, "anomaly": False, "conclusion": "✓ All clear — swarm recovered",
         "emotion": "trust"},
    ]

    scenario_names = [
        "Calm baseline", "Routine patrol",
        "First anomaly", "Suspicious pattern",
        "Anomaly confirmed", "Intrusion detected",
        "CRITICAL breach", "Cascade spreading",
        "Containment", "Stabilizing", "Recovery"
    ]

    for i, (sig, name) in enumerate(zip(signals, scenario_names)):
        if HAS_RICH:
            console.print(f"\n[bold dim]━━━ TICK {i+1}: {name.upper()} ━━━[/bold dim]")
        result = swarm.process_signal(sig)
        render_tick(result, swarm)
        time.sleep(0.15)

    render_final_status(swarm)


# ─── HTTP API ─────────────────────────────────────────────────────────────────

def run_api(swarm: ForgeSwarmV2):
    if not HAS_FLASK: return
    app = Flask(__name__)

    @app.route("/signal", methods=["POST"])
    def signal():
        data = request.json or {}
        return jsonify(swarm.process_signal(data))

    @app.route("/agents", methods=["GET"])
    def agents():
        return jsonify([{
            "id": a.id, "name": a.name, "role": a.role.value,
            "state": a.state.value, "health": a.health_score(),
            "stress": a.brain.stress_level, "zone": a.zone
        } for a in swarm.agents])

    @app.route("/votes", methods=["GET"])
    def votes():
        rows = swarm.db.get_votes()
        return jsonify([{"id":r[0],"proposal":r[2],"result":r[3],"rationale":r[4]} for r in rows])

    @app.route("/memory", methods=["GET"])
    def memory():
        return jsonify(swarm.swarm_mem.highlights)

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify(swarm.get_status())

    app.run(host="0.0.0.0", port=API_PORT, debug=False)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    swarm = ForgeSwarmV2(n_agents=8)
    if "--api" in sys.argv:
        t = threading.Thread(target=run_api, args=(swarm,), daemon=True)
        t.start()
    run_demo()
