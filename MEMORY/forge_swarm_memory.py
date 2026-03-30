"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     FORGE_SWARM_MEMORY v1.0                                  ║
║                  Three-Tier Army Memory Architecture                         ║
║                                                                              ║
║  Like an army — three levels of intelligence simultaneously:                 ║
║                                                                              ║
║  TIER 1 — SOLDIER   Individual agent memory                                  ║
║                     Each agent's own experience, failures, discoveries       ║
║                     What IT learned on ITS path                              ║
║                                                                              ║
║  TIER 2 — SQUAD     Small group memory (3-7 agents)                          ║
║                     Shared tactics, trust between specific agents            ║
║                     What THIS GROUP learned working together                 ║
║                                                                              ║
║  TIER 3 — COMMAND   Collective emergence memory                              ║
║                     Patterns visible only from above                         ║
║                     What the WHOLE SWARM discovered together                 ║
║                                                                              ║
║  Flow: Soldier → Squad → Command (bottom-up)                                 ║
║        Command → Squad → Soldier (top-down)                                  ║
║                                                                              ║
║  Connects to FORGE_MEMORY:                                                   ║
║    Soldier  → TRACE + BodyMemory                                             ║
║    Squad    → BOND                                                           ║
║    Command  → SELF beliefs + GENESIS crystallization                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import json
import math
import random
import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# ─── Optional Dependencies ────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.tree import Tree
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

try:
    from flask import Flask, request, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

console = Console() if RICH_AVAILABLE else None

def cprint(msg, style=""):
    if console:
        console.print(msg, style=style)
    else:
        print(msg)

# ─── Constants ────────────────────────────────────────────────────────────────
FORGE_DIR   = Path.home() / ".forge"
SWARM_DIR   = FORGE_DIR / "swarm_memory"
DB_PATH     = SWARM_DIR / "swarm.db"
STATE_PATH  = SWARM_DIR / "swarm_state.json"
API_PORT    = 7781

SWARM_DIR.mkdir(parents=True, exist_ok=True)

# ─── FORGE_MEMORY bridge client ───────────────────────────────────────────────
import urllib.request

def _post(url: str, data: dict, timeout: float = 2.0) -> Optional[dict]:
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None

def _get(url: str, timeout: float = 2.0) -> Optional[dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  TIER 1 — SOLDIER MEMORY
#  Individual agent memory — what IT learned on ITS path
# ═══════════════════════════════════════════════════════════════════════════════

class SoldierMemory:
    """
    Every agent in the swarm has its own memory.

    A soldier remembers:
    🗺️  Path       — routes explored, dead ends encountered
    ⚔️  Battles    — challenges faced, how they were resolved
    🎯  Skills     — capabilities developed through repetition
    🤕  Wounds     — failures, what went wrong, lessons learned
    🏆  Victories  — successes, what worked, when and why
    🔗  Bonds      — trust relationships with specific other agents
    """

    def __init__(self, agent_id: str, db_path: Path):
        self.agent_id = agent_id
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS soldier_memories (
                    id          TEXT PRIMARY KEY,
                    agent_id    TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    outcome     TEXT DEFAULT 'unknown',
                    strength    REAL DEFAULT 0.5,
                    times_used  INTEGER DEFAULT 1,
                    task_id     TEXT,
                    squad_id    TEXT,
                    timestamp   TEXT NOT NULL,
                    metadata    TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_skills (
                    agent_id    TEXT NOT NULL,
                    skill       TEXT NOT NULL,
                    proficiency REAL DEFAULT 0.1,
                    uses        INTEGER DEFAULT 0,
                    first_used  TEXT,
                    last_used   TEXT,
                    PRIMARY KEY (agent_id, skill)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_bonds (
                    agent_a     TEXT NOT NULL,
                    agent_b     TEXT NOT NULL,
                    trust       REAL DEFAULT 0.3,
                    synergy     REAL DEFAULT 0.3,
                    interactions INTEGER DEFAULT 0,
                    formed_at   TEXT,
                    PRIMARY KEY (agent_a, agent_b)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_soldier_agent ON soldier_memories(agent_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_soldier_type  ON soldier_memories(memory_type)")
            conn.commit()

    # ── Core memory operations ────────────────────────────────────────────────
    def remember(
        self,
        memory_type: str,
        content: str,
        outcome: str = "unknown",
        strength: float = 0.5,
        task_id: Optional[str] = None,
        squad_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        mem_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO soldier_memories
                (id, agent_id, memory_type, content, outcome, strength, task_id, squad_id, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                mem_id, self.agent_id, memory_type, content, outcome,
                strength, task_id, squad_id,
                datetime.now().isoformat(),
                json.dumps(metadata or {})
            ))
            conn.commit()
        return mem_id

    def recall(self, memory_type: Optional[str] = None, limit: int = 20) -> list[dict]:
        query = "SELECT * FROM soldier_memories WHERE agent_id = ?"
        params = [self.agent_id]
        if memory_type:
            query += " AND memory_type = ?"
            params.append(memory_type)
        query += " ORDER BY strength DESC, timestamp DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    # ── Path memory ───────────────────────────────────────────────────────────
    def explored(self, path: str, outcome: str = "unknown", cost: float = 0.5):
        """Record a path explored — dead end, successful, or partial."""
        return self.remember("path", f"Explored: {path}", outcome=outcome, strength=cost)

    def dead_end(self, path: str, reason: str = ""):
        """Remember a dead end — strong signal to avoid this path."""
        content = f"Dead end: {path}" + (f" — {reason}" if reason else "")
        return self.remember("path", content, outcome="dead_end", strength=0.8)

    # ── Battle memory ─────────────────────────────────────────────────────────
    def fought(self, challenge: str, resolution: str, success: bool = True):
        outcome = "victory" if success else "defeat"
        strength = 0.8 if success else 0.9  # Failures remembered stronger
        return self.remember("battle", f"{challenge} → {resolution}", outcome=outcome, strength=strength)

    # ── Skill development ─────────────────────────────────────────────────────
    def practiced(self, skill: str) -> float:
        """Practice a skill — returns new proficiency level."""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute(
                "SELECT proficiency, uses FROM agent_skills WHERE agent_id=? AND skill=?",
                (self.agent_id, skill)
            ).fetchone()

            if existing:
                new_prof = min(1.0, existing[0] + 0.05)
                new_uses = existing[1] + 1
                conn.execute("""
                    UPDATE agent_skills SET proficiency=?, uses=?, last_used=?
                    WHERE agent_id=? AND skill=?
                """, (new_prof, new_uses, now, self.agent_id, skill))
            else:
                new_prof = 0.1
                conn.execute("""
                    INSERT INTO agent_skills (agent_id, skill, proficiency, uses, first_used, last_used)
                    VALUES (?, ?, 0.1, 1, ?, ?)
                """, (self.agent_id, skill, now, now))
            conn.commit()

        if new_prof >= 0.8:
            cprint(f"  [bold green]🎯 AGENT {self.agent_id[:8]} mastered: {skill}[/bold green]")
        return new_prof

    def skills(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM agent_skills WHERE agent_id=? ORDER BY proficiency DESC",
                (self.agent_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Wound & Victory ───────────────────────────────────────────────────────
    def wounded(self, what_failed: str, lesson: str):
        """Remember a failure — high strength so it's not forgotten."""
        return self.remember("wound",
            f"Failed: {what_failed} | Lesson: {lesson}",
            outcome="failure", strength=0.85)

    def victory(self, what_worked: str, context: str = ""):
        """Remember a success."""
        return self.remember("victory",
            f"Succeeded: {what_worked}" + (f" | Context: {context}" if context else ""),
            outcome="success", strength=0.75)

    # ── Agent bonds ───────────────────────────────────────────────────────────
    def bonded_with(self, other_agent_id: str, outcome: str = "positive"):
        """Record interaction with another agent — builds or weakens trust."""
        delta = 0.1 if outcome == "positive" else -0.05
        now = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute(
                "SELECT trust, synergy, interactions FROM agent_bonds WHERE agent_a=? AND agent_b=?",
                (self.agent_id, other_agent_id)
            ).fetchone()

            if existing:
                new_trust = max(0.0, min(1.0, existing[0] + delta))
                new_synergy = min(1.0, existing[1] + 0.05)
                conn.execute("""
                    UPDATE agent_bonds SET trust=?, synergy=?, interactions=?
                    WHERE agent_a=? AND agent_b=?
                """, (new_trust, new_synergy, existing[2]+1, self.agent_id, other_agent_id))
            else:
                conn.execute("""
                    INSERT INTO agent_bonds (agent_a, agent_b, trust, synergy, interactions, formed_at)
                    VALUES (?, ?, 0.3, 0.3, 1, ?)
                """, (self.agent_id, other_agent_id, now))
            conn.commit()

    def trusted_agents(self, min_trust: float = 0.5) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM agent_bonds WHERE agent_a=? AND trust>=?
                ORDER BY trust DESC
            """, (self.agent_id, min_trust)).fetchall()
        return [dict(r) for r in rows]

    def snapshot(self) -> dict:
        memories = self.recall(limit=100)
        skills = self.skills()
        return {
            "agent_id":      self.agent_id,
            "memory_count":  len(memories),
            "skill_count":   len(skills),
            "top_skills":    [s["skill"] for s in skills[:3]],
            "victories":     sum(1 for m in memories if m["memory_type"] == "victory"),
            "wounds":        sum(1 for m in memories if m["memory_type"] == "wound"),
            "dead_ends":     sum(1 for m in memories if m.get("outcome") == "dead_end"),
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  TIER 2 — SQUAD MEMORY
#  Small group memory — what THIS GROUP learned working together
# ═══════════════════════════════════════════════════════════════════════════════

class SquadMemory:
    """
    A squad is 3-7 agents that work together repeatedly.
    They develop shared tactics, trust, and collective intelligence
    that no individual agent has alone.

    A squad remembers:
    ⚔️  Tactics      — formations and strategies that worked
    🤝  Trust map    — which agents work best together
    🎯  Specialization — what this squad is uniquely good at
    📖  Doctrine     — rules of engagement developed from experience
    🏆  Campaigns    — major operations and their outcomes
    """

    def __init__(self, squad_id: str, agent_ids: list[str], db_path: Path):
        self.squad_id = squad_id
        self.agent_ids = agent_ids
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS squads (
                    squad_id    TEXT PRIMARY KEY,
                    agent_ids   TEXT NOT NULL,
                    formed_at   TEXT NOT NULL,
                    mission_count INTEGER DEFAULT 0,
                    success_rate  REAL DEFAULT 0.0,
                    specialization TEXT DEFAULT 'general',
                    cohesion    REAL DEFAULT 0.3
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS squad_memories (
                    id          TEXT PRIMARY KEY,
                    squad_id    TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    outcome     TEXT DEFAULT 'unknown',
                    strength    REAL DEFAULT 0.5,
                    agents_involved TEXT DEFAULT '[]',
                    timestamp   TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS squad_doctrine (
                    id          TEXT PRIMARY KEY,
                    squad_id    TEXT NOT NULL,
                    rule        TEXT NOT NULL,
                    origin      TEXT,
                    confidence  REAL DEFAULT 0.6,
                    applied_count INTEGER DEFAULT 0,
                    created_at  TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_squad_mem ON squad_memories(squad_id)")
            conn.commit()

        # Register squad
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute(
                "SELECT squad_id FROM squads WHERE squad_id=?", (self.squad_id,)
            ).fetchone()
            if not existing:
                conn.execute("""
                    INSERT INTO squads (squad_id, agent_ids, formed_at)
                    VALUES (?, ?, ?)
                """, (self.squad_id, json.dumps(self.agent_ids), datetime.now().isoformat()))
                conn.commit()

    # ── Squad memory operations ───────────────────────────────────────────────
    def remember(self, memory_type: str, content: str, outcome: str = "unknown",
                 strength: float = 0.5, agents_involved: Optional[list] = None) -> str:
        mem_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO squad_memories
                (id, squad_id, memory_type, content, outcome, strength, agents_involved, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                mem_id, self.squad_id, memory_type, content, outcome, strength,
                json.dumps(agents_involved or self.agent_ids),
                datetime.now().isoformat()
            ))
            conn.commit()
        return mem_id

    # ── Tactics ───────────────────────────────────────────────────────────────
    def learned_tactic(self, tactic: str, context: str, success_rate: float = 0.7):
        """Record a tactic the squad developed through experience."""
        content = f"Tactic: {tactic} | Context: {context} | Success: {success_rate:.0%}"
        mem_id = self.remember("tactic", content, outcome="learned", strength=success_rate)
        cprint(f"  [cyan]⚔️  SQUAD {self.squad_id[:8]} tactic learned: {tactic[:40]}[/cyan]")
        return mem_id

    def tactic_failed(self, tactic: str, reason: str):
        """Record a failed tactic — strong negative signal."""
        return self.remember("tactic", f"FAILED: {tactic} | Reason: {reason}",
                           outcome="failed", strength=0.9)

    # ── Doctrine ──────────────────────────────────────────────────────────────
    def add_doctrine(self, rule: str, origin: str = "", confidence: float = 0.6) -> str:
        """
        Doctrine — rules of engagement developed from experience.
        Like 'always send two agents to sector C' or 'never split when facing X'.
        """
        doc_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO squad_doctrine (id, squad_id, rule, origin, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (doc_id, self.squad_id, rule, origin, confidence, datetime.now().isoformat()))
            conn.commit()
        cprint(f"  [magenta]📖 SQUAD {self.squad_id[:8]} doctrine: {rule[:50]}[/magenta]")
        return doc_id

    def apply_doctrine(self, doc_id: str, success: bool = True):
        """Apply doctrine — strengthens or weakens it based on outcome."""
        delta = 0.05 if success else -0.08
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE squad_doctrine
                SET applied_count = applied_count + 1,
                    confidence = MAX(0.1, MIN(1.0, confidence + ?))
                WHERE id = ?
            """, (delta, doc_id))
            conn.commit()

    def get_doctrine(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM squad_doctrine WHERE squad_id=?
                ORDER BY confidence DESC
            """, (self.squad_id,)).fetchall()
        return [dict(r) for r in rows]

    # ── Campaign memory ───────────────────────────────────────────────────────
    def campaign_complete(self, campaign_name: str, outcome: str,
                         key_lesson: str = "", duration_steps: int = 0):
        """Record a major operation completion."""
        content = f"Campaign: {campaign_name} | Outcome: {outcome} | Steps: {duration_steps}"
        if key_lesson:
            content += f" | Lesson: {key_lesson}"

        strength = 0.9 if outcome == "success" else 0.95
        mem_id = self.remember("campaign", content, outcome=outcome, strength=strength)

        # Update squad stats
        with sqlite3.connect(self.db_path) as conn:
            squad = conn.execute(
                "SELECT mission_count, success_rate FROM squads WHERE squad_id=?",
                (self.squad_id,)
            ).fetchone()
            if squad:
                new_count = squad[0] + 1
                successes = squad[1] * squad[0] + (1 if outcome == "success" else 0)
                new_rate = successes / new_count
                conn.execute("""
                    UPDATE squads SET mission_count=?, success_rate=?
                    WHERE squad_id=?
                """, (new_count, new_rate, self.squad_id))
                conn.commit()

        cprint(f"  [bold]🏆 SQUAD {self.squad_id[:8]} campaign: {campaign_name[:40]} → {outcome}[/bold]")
        return mem_id

    # ── Cohesion ──────────────────────────────────────────────────────────────
    def update_cohesion(self, delta: float):
        """Update squad cohesion — how well they work together."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE squads SET cohesion = MAX(0.0, MIN(1.0, cohesion + ?))
                WHERE squad_id=?
            """, (delta, self.squad_id))
            conn.commit()

    def snapshot(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            squad = conn.execute(
                "SELECT * FROM squads WHERE squad_id=?", (self.squad_id,)
            ).fetchone()
            mem_count = conn.execute(
                "SELECT COUNT(*) FROM squad_memories WHERE squad_id=?", (self.squad_id,)
            ).fetchone()[0]
            doc_count = conn.execute(
                "SELECT COUNT(*) FROM squad_doctrine WHERE squad_id=?", (self.squad_id,)
            ).fetchone()[0]

        if not squad:
            return {}

        squad = dict(zip(["squad_id","agent_ids","formed_at","mission_count","success_rate","specialization","cohesion"], squad))
        return {
            "squad_id":      self.squad_id,
            "agent_count":   len(self.agent_ids),
            "agents":        self.agent_ids,
            "mission_count": squad.get("mission_count", 0),
            "success_rate":  round(float(squad.get("success_rate", 0)), 2),
            "specialization": squad.get("specialization", "general"),
            "cohesion":      round(float(squad.get("cohesion", 0.3)), 2),
            "memory_count":  mem_count,
            "doctrine_count": doc_count,
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  TIER 3 — COMMAND MEMORY
#  Collective emergence — what the WHOLE SWARM discovered together
# ═══════════════════════════════════════════════════════════════════════════════

class CommandMemory:
    """
    Command sees the whole battlefield.
    It remembers patterns invisible at the soldier or squad level.

    Command remembers:
    ✨  Emergence    — patterns that arose from collective behavior
    🗺️  Strategic map — which approaches work at scale
    📊  Performance  — swarm-wide metrics and trends
    🧬  Evolution    — how the swarm's collective behavior has changed
    🎖️  Hall of fame — the most significant discoveries
    📡  Signals      — patterns in how agents communicate
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS command_memories (
                    id              TEXT PRIMARY KEY,
                    memory_type     TEXT NOT NULL,
                    content         TEXT NOT NULL,
                    significance    REAL DEFAULT 0.5,
                    agents_involved INTEGER DEFAULT 0,
                    squads_involved INTEGER DEFAULT 0,
                    verified        INTEGER DEFAULT 0,
                    timestamp       TEXT NOT NULL,
                    metadata        TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS emergence_log (
                    id              TEXT PRIMARY KEY,
                    pattern         TEXT NOT NULL,
                    description     TEXT NOT NULL,
                    agent_count     INTEGER,
                    iterations      INTEGER,
                    efficiency_gain REAL DEFAULT 0.0,
                    task_id         TEXT,
                    timestamp       TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS swarm_evolution (
                    id              TEXT PRIMARY KEY,
                    generation      INTEGER DEFAULT 0,
                    avg_performance REAL DEFAULT 0.0,
                    top_skill       TEXT,
                    dominant_tactic TEXT,
                    agent_count     INTEGER,
                    recorded_at     TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hall_of_fame (
                    id          TEXT PRIMARY KEY,
                    title       TEXT NOT NULL,
                    description TEXT NOT NULL,
                    agent_id    TEXT,
                    squad_id    TEXT,
                    significance REAL DEFAULT 0.8,
                    inducted_at TEXT NOT NULL
                )
            """)
            conn.commit()

    # ── Emergence ─────────────────────────────────────────────────────────────
    def record_emergence(
        self,
        pattern: str,
        description: str,
        agent_count: int,
        iterations: int,
        efficiency_gain: float = 0.0,
        task_id: Optional[str] = None,
    ) -> str:
        """
        Record an emergent pattern — intelligence that arose from collective behavior.
        This is the highest form of swarm memory.
        """
        em_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO emergence_log
                (id, pattern, description, agent_count, iterations, efficiency_gain, task_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (em_id, pattern, description, agent_count, iterations,
                  efficiency_gain, task_id, datetime.now().isoformat()))
            conn.commit()

        # Also store as command memory
        significance = min(1.0, 0.7 + efficiency_gain * 0.3)
        self.remember(
            "emergence",
            f"[EMERGED] {pattern}: {description}",
            significance=significance,
            agents_involved=agent_count,
        )

        cprint(f"  [bold magenta]✨ EMERGENCE recorded: {pattern[:50]} (+{efficiency_gain:.0%} efficiency)[/bold magenta]")

        # Bubble up to FORGE_MEMORY
        self._bubble_to_forge(pattern, description, significance, efficiency_gain)

        return em_id

    def _bubble_to_forge(self, pattern: str, description: str,
                         significance: float, efficiency_gain: float):
        """Bubble command-level insights up to FORGE_MEMORY v1 and v2."""
        # → v1 SELF belief
        _post("http://localhost:7779/self/belief", {
            "belief": f"Swarm discovered: {pattern} — {description[:80]}",
            "confidence": significance,
            "source": "swarm_command",
        })
        # → v1 GENESIS crystallization
        _post("http://localhost:7779/genesis/capture", {
            "thought_type": "crystallization",
            "content": f"Swarm emergence: {pattern} | gain: {efficiency_gain:.0%} | {description[:80]}",
            "artifact_name": "swarm_intelligence",
            "human_id": "default",
            "significance": significance,
        })
        # → v2 emotional feel (emergence always feels like awe)
        _post("http://localhost:7780/feel", {
            "content": f"Swarm emergence: {pattern} — {description}",
            "emotion": "awe",
            "intensity": significance,
            "category": "emergence",
            "module": "swarm_command",
        })

    # ── Strategic map ─────────────────────────────────────────────────────────
    def record_strategy(self, approach: str, outcome: str,
                        scale: int, lesson: str = "") -> str:
        content = f"Strategy at scale {scale}: {approach} → {outcome}"
        if lesson:
            content += f" | {lesson}"
        return self.remember("strategy", content,
                           significance=0.7, agents_involved=scale)

    # ── Evolution ─────────────────────────────────────────────────────────────
    def record_generation(self, generation: int, avg_performance: float,
                          top_skill: str, dominant_tactic: str, agent_count: int):
        """Record a generation snapshot — how the swarm has evolved."""
        gen_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO swarm_evolution
                (id, generation, avg_performance, top_skill, dominant_tactic, agent_count, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (gen_id, generation, avg_performance, top_skill,
                  dominant_tactic, agent_count, datetime.now().isoformat()))
            conn.commit()

        cprint(f"  [dim]🧬 GENERATION {generation}: perf={avg_performance:.2f} | top={top_skill}[/dim]")
        return gen_id

    def evolution_arc(self) -> list[dict]:
        """How the swarm has changed across generations."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM swarm_evolution ORDER BY generation ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Hall of Fame ──────────────────────────────────────────────────────────
    def induct(self, title: str, description: str,
               agent_id: Optional[str] = None, squad_id: Optional[str] = None,
               significance: float = 0.9):
        """Induct a significant achievement into the hall of fame."""
        hof_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO hall_of_fame
                (id, title, description, agent_id, squad_id, significance, inducted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (hof_id, title, description, agent_id, squad_id,
                  significance, datetime.now().isoformat()))
            conn.commit()
        cprint(f"  [bold yellow]🎖️  HALL OF FAME: {title}[/bold yellow]")
        return hof_id

    def hall_of_fame(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM hall_of_fame ORDER BY significance DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Core memory ───────────────────────────────────────────────────────────
    def remember(self, memory_type: str, content: str, significance: float = 0.5,
                 agents_involved: int = 0, squads_involved: int = 0) -> str:
        mem_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO command_memories
                (id, memory_type, content, significance, agents_involved, squads_involved, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (mem_id, memory_type, content, significance,
                  agents_involved, squads_involved, datetime.now().isoformat()))
            conn.commit()
        return mem_id

    def snapshot(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            emergence_count = conn.execute("SELECT COUNT(*) FROM emergence_log").fetchone()[0]
            hof_count = conn.execute("SELECT COUNT(*) FROM hall_of_fame").fetchone()[0]
            gen_count = conn.execute("SELECT COUNT(*) FROM swarm_evolution").fetchone()[0]
            mem_count = conn.execute("SELECT COUNT(*) FROM command_memories").fetchone()[0]
            latest_gen = conn.execute(
                "SELECT avg_performance, top_skill FROM swarm_evolution ORDER BY generation DESC LIMIT 1"
            ).fetchone()

        return {
            "emergence_count":   emergence_count,
            "hall_of_fame_count": hof_count,
            "generations":       gen_count,
            "memory_count":      mem_count,
            "latest_performance": round(latest_gen[0], 3) if latest_gen else 0.0,
            "current_top_skill": latest_gen[1] if latest_gen else "unknown",
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  FLOW ENGINE
#  Bottom-up and top-down intelligence flow between tiers
# ═══════════════════════════════════════════════════════════════════════════════

class SwarmFlowEngine:
    """
    Intelligence flows both directions in an army:

    Bottom-up: Soldier discoveries → Squad tactics → Command emergence
    Top-down:  Command insights → Squad doctrine → Soldier instincts

    The flow engine manages this continuous two-way intelligence transfer.
    """

    def __init__(self, command: CommandMemory, db_path: Path):
        self.command = command
        self.db_path = db_path
        self._bubbled_memories: set = set()
        self._distributed_insights: set = set()

    def bubble_up(self, soldiers: list[SoldierMemory], squads: list[SquadMemory]):
        """
        Bottom-up flow: Soldier victories/wounds → Squad tactics
                        Squad patterns → Command emergence
        """
        bubbled = 0

        # Soldier → Squad: Share victories and wounds with squad
        for soldier in soldiers:
            victories = soldier.recall("victory", limit=5)
            wounds = soldier.recall("wound", limit=5)

            for mem in victories + wounds:
                mem_id = mem["id"]
                if mem_id in self._bubbled_memories:
                    continue

                # Find soldier's squad
                squad_id = mem.get("squad_id")
                if squad_id:
                    matching_squads = [s for s in squads if s.squad_id == squad_id]
                    for squad in matching_squads:
                        if mem["memory_type"] == "victory":
                            squad.learned_tactic(
                                mem["content"][:60],
                                context=f"from agent {soldier.agent_id[:8]}",
                                success_rate=mem["strength"],
                            )
                        else:
                            squad.add_doctrine(
                                f"Avoid: {mem['content'][:60]}",
                                origin=f"agent {soldier.agent_id[:8]} wound",
                                confidence=mem["strength"] * 0.8,
                            )
                        bubbled += 1

                self._bubbled_memories.add(mem_id)

        # Squad → Command: High-confidence doctrine becomes command strategy
        for squad in squads:
            doctrine = squad.get_doctrine()
            for doc in doctrine:
                doc_id = doc["id"]
                if doc_id in self._bubbled_memories:
                    continue
                if doc["confidence"] >= 0.8 and doc["applied_count"] >= 3:
                    self.command.record_strategy(
                        approach=doc["rule"],
                        outcome="validated_doctrine",
                        scale=len(squad.agent_ids),
                        lesson=f"from squad {squad.squad_id[:8]}",
                    )
                    bubbled += 1
                    self._bubbled_memories.add(doc_id)

        if bubbled:
            cprint(f"  [dim]↑ BUBBLE UP: {bubbled} insights flowed to higher tiers[/dim]")
        return bubbled

    def flow_down(self, command: CommandMemory, squads: list[SquadMemory],
                  soldiers: list[SoldierMemory]):
        """
        Top-down flow: Command emergence → Squad doctrine
                       Squad tactics → Soldier instincts
        """
        distributed = 0

        # Command → Squad: Emergent patterns become squad doctrine
        with sqlite3.connect(self.db_path) as conn:
            emergence_rows = conn.execute("""
                SELECT id, pattern, description, efficiency_gain
                FROM emergence_log
                ORDER BY timestamp DESC LIMIT 10
            """).fetchall()

        for row in emergence_rows:
            em_id, pattern, description, gain = row
            if em_id in self._distributed_insights:
                continue

            for squad in squads:
                squad.add_doctrine(
                    rule=f"Apply emergent pattern: {pattern[:50]}",
                    origin="command_emergence",
                    confidence=min(0.9, 0.6 + gain * 0.3),
                )
                distributed += 1

            self._distributed_insights.add(em_id)

        # Squad → Soldier: High-confidence doctrine becomes soldier skill
        for squad in squads:
            doctrine = squad.get_doctrine()
            for doc in doctrine:
                if doc["confidence"] >= 0.7:
                    for soldier in soldiers:
                        if soldier.agent_id in squad.agent_ids:
                            soldier.practiced(f"squad_doctrine:{doc['rule'][:30]}")
                            distributed += 1

        if distributed:
            cprint(f"  [dim]↓ FLOW DOWN: {distributed} insights distributed to lower tiers[/dim]")
        return distributed


# ═══════════════════════════════════════════════════════════════════════════════
#  FORGE SWARM MEMORY — Main Interface
# ═══════════════════════════════════════════════════════════════════════════════

class ForgeSwarmMemory:
    """
    Three-tier army memory for FORGE swarm intelligence.

    Usage:
        swarm_mem = ForgeSwarmMemory()

        # Create agents with individual memory
        agent = swarm_mem.create_agent()
        agent.explored("path_A", outcome="success")
        agent.wounded("path_B failed", "always check boundary conditions")
        agent.practiced("threat_detection")

        # Create squads
        squad = swarm_mem.create_squad([agent1.agent_id, agent2.agent_id])
        squad.learned_tactic("pincer_move", context="open terrain")
        squad.campaign_complete("operation_delta", "success", key_lesson="speed matters")

        # Record emergence at command level
        swarm_mem.command.record_emergence(
            "spontaneous_load_balancing",
            "Agents self-organized without central direction",
            agent_count=50, iterations=847, efficiency_gain=0.34
        )

        # Flow intelligence between tiers
        swarm_mem.flow()
    """

    def __init__(self):
        self.command = CommandMemory(DB_PATH)
        self._soldiers: dict[str, SoldierMemory] = {}
        self._squads: dict[str, SquadMemory] = {}
        self.flow_engine = SwarmFlowEngine(self.command, DB_PATH)
        self._api_thread = None

    def create_agent(self, agent_id: Optional[str] = None) -> SoldierMemory:
        """Create a new agent with individual memory."""
        agent_id = agent_id or f"agent_{str(uuid.uuid4())[:8]}"
        soldier = SoldierMemory(agent_id, DB_PATH)
        self._soldiers[agent_id] = soldier
        return soldier

    def get_agent(self, agent_id: str) -> Optional[SoldierMemory]:
        if agent_id not in self._soldiers:
            self._soldiers[agent_id] = SoldierMemory(agent_id, DB_PATH)
        return self._soldiers[agent_id]

    def create_squad(self, agent_ids: list[str],
                     squad_id: Optional[str] = None) -> SquadMemory:
        """Form a squad from existing agents."""
        squad_id = squad_id or f"squad_{str(uuid.uuid4())[:8]}"
        squad = SquadMemory(squad_id, agent_ids, DB_PATH)
        self._squads[squad_id] = squad

        # Tag agents with squad membership
        for agent_id in agent_ids:
            agent = self.get_agent(agent_id)
            agent.remember("bond", f"Joined squad {squad_id}", strength=0.6,
                          squad_id=squad_id)

        cprint(f"  [green]🐝 SQUAD {squad_id[:8]} formed with {len(agent_ids)} agents[/green]")
        return squad

    def flow(self):
        """Run one full intelligence flow cycle — bottom-up then top-down."""
        soldiers = list(self._soldiers.values())
        squads = list(self._squads.values())

        cprint("\n  [bold]🔄 SWARM FLOW CYCLE[/bold]")
        up = self.flow_engine.bubble_up(soldiers, squads)
        down = self.flow_engine.flow_down(self.command, squads, soldiers)
        cprint(f"  [dim]Flow complete: ↑{up} bubbled, ↓{down} distributed[/dim]")
        return {"bubbled": up, "distributed": down}

    def status(self) -> dict:
        return {
            "version":         "1.0",
            "agent_count":     len(self._soldiers),
            "squad_count":     len(self._squads),
            "command":         self.command.snapshot(),
            "agents":          [a.snapshot() for a in self._soldiers.values()],
            "squads":          [s.snapshot() for s in self._squads.values()],
            "hall_of_fame":    self.command.hall_of_fame(),
        }

    def start_api(self, port: int = API_PORT):
        if not FLASK_AVAILABLE:
            return

        app = Flask("forge_swarm_memory")

        @app.route("/health")
        def health():
            return jsonify({"status": "alive", "module": "forge_swarm_memory"})

        @app.route("/status")
        def status():
            return jsonify(self.status())

        @app.route("/agent/create", methods=["POST"])
        def create_agent():
            d = request.json or {}
            agent = self.create_agent(d.get("agent_id"))
            return jsonify({"agent_id": agent.agent_id})

        @app.route("/agent/<agent_id>/remember", methods=["POST"])
        def agent_remember(agent_id):
            d = request.json
            agent = self.get_agent(agent_id)
            mem_id = agent.remember(d["memory_type"], d["content"],
                                    d.get("outcome", "unknown"), d.get("strength", 0.5))
            return jsonify({"mem_id": mem_id})

        @app.route("/agent/<agent_id>/practice", methods=["POST"])
        def agent_practice(agent_id):
            d = request.json
            agent = self.get_agent(agent_id)
            prof = agent.practiced(d["skill"])
            return jsonify({"proficiency": prof})

        @app.route("/agent/<agent_id>/snapshot")
        def agent_snapshot(agent_id):
            agent = self.get_agent(agent_id)
            return jsonify(agent.snapshot())

        @app.route("/squad/create", methods=["POST"])
        def create_squad():
            d = request.json
            squad = self.create_squad(d["agent_ids"], d.get("squad_id"))
            return jsonify({"squad_id": squad.squad_id})

        @app.route("/squad/<squad_id>/tactic", methods=["POST"])
        def squad_tactic(squad_id):
            d = request.json
            squad = self._squads.get(squad_id)
            if not squad:
                return jsonify({"error": "squad not found"}), 404
            mem_id = squad.learned_tactic(d["tactic"], d.get("context", ""), d.get("success_rate", 0.7))
            return jsonify({"mem_id": mem_id})

        @app.route("/command/emergence", methods=["POST"])
        def emergence():
            d = request.json
            em_id = self.command.record_emergence(
                d["pattern"], d["description"],
                d.get("agent_count", 0), d.get("iterations", 0),
                d.get("efficiency_gain", 0.0), d.get("task_id"),
            )
            return jsonify({"emergence_id": em_id})

        @app.route("/command/hof", methods=["POST"])
        def induct_hof():
            d = request.json
            hof_id = self.command.induct(
                d["title"], d["description"],
                d.get("agent_id"), d.get("squad_id"),
                d.get("significance", 0.9)
            )
            return jsonify({"hof_id": hof_id})

        @app.route("/flow", methods=["POST"])
        def run_flow():
            return jsonify(self.flow())

        import logging
        logging.getLogger("werkzeug").setLevel(logging.ERROR)

        self._api_thread = threading.Thread(
            target=lambda: app.run(host="0.0.0.0", port=port, debug=False),
            daemon=True,
        )
        self._api_thread.start()
        cprint(f"  [bold green]🌐 FORGE_SWARM_MEMORY API on port {port}[/bold green]")


# ═══════════════════════════════════════════════════════════════════════════════
#  DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

def display_status(swarm: ForgeSwarmMemory):
    if not RICH_AVAILABLE:
        print(json.dumps(swarm.status(), indent=2, default=str))
        return

    status = swarm.status()
    console.print()

    # Command panel
    cmd = status["command"]
    cmd_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    cmd_table.add_column("k", style="dim")
    cmd_table.add_column("v", style="white")
    cmd_table.add_row("✨ Emergences",      str(cmd["emergence_count"]))
    cmd_table.add_row("🎖️  Hall of Fame",   str(cmd["hall_of_fame_count"]))
    cmd_table.add_row("🧬 Generations",     str(cmd["generations"]))
    cmd_table.add_row("📊 Latest perf",     str(cmd["latest_performance"]))
    cmd_table.add_row("🎯 Top skill",       cmd["current_top_skill"])
    console.print(Panel(cmd_table, title="[bold magenta]TIER 3 — COMMAND[/bold magenta]", border_style="magenta"))

    # Squad panels
    for squad in status["squads"]:
        sq_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        sq_table.add_column("k", style="dim")
        sq_table.add_column("v", style="white")
        sq_table.add_row("👥 Agents",        str(squad["agent_count"]))
        sq_table.add_row("🏆 Missions",      str(squad["mission_count"]))
        sq_table.add_row("📈 Success rate",  f"{squad['success_rate']:.0%}")
        sq_table.add_row("🤝 Cohesion",      str(squad["cohesion"]))
        sq_table.add_row("📖 Doctrine",      str(squad["doctrine_count"]))
        console.print(Panel(sq_table,
            title=f"[bold cyan]TIER 2 — SQUAD [{squad['squad_id'][:8]}][/bold cyan]",
            border_style="cyan"))

    # Soldier summary
    agents = status["agents"]
    if agents:
        ag_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        ag_table.add_column("Agent", style="cyan")
        ag_table.add_column("Memories", style="white")
        ag_table.add_column("Skills", style="white")
        ag_table.add_column("Victories", style="green")
        ag_table.add_column("Wounds", style="red")
        ag_table.add_column("Top Skills", style="dim")
        for a in agents:
            ag_table.add_row(
                a["agent_id"][:12],
                str(a["memory_count"]),
                str(a["skill_count"]),
                str(a["victories"]),
                str(a["wounds"]),
                ", ".join(a["top_skills"][:2]),
            )
        console.print(Panel(ag_table, title="[bold green]TIER 1 — SOLDIERS[/bold green]", border_style="green"))

    # Hall of fame
    hof = status["hall_of_fame"]
    if hof:
        console.print("  [bold yellow]🎖️  Hall of Fame:[/bold yellow]")
        for entry in hof:
            console.print(f"    ★ [white]{entry['title']}[/white] — [dim]{entry['description'][:50]}[/dim]")
    console.print()


# ═══════════════════════════════════════════════════════════════════════════════
#  DEMO
# ═══════════════════════════════════════════════════════════════════════════════

def run_demo():
    cprint("\n[bold yellow]━━━ FORGE_SWARM_MEMORY DEMO ━━━[/bold yellow]\n") if RICH_AVAILABLE else print("=== SWARM MEMORY DEMO ===")
    cprint("[dim]Three-tier army memory — soldier, squad, command[/dim]\n")

    swarm = ForgeSwarmMemory()

    # ── Create 6 agents ────────────────────────────────────────────────────────
    cprint("[bold cyan]TIER 1 — SOLDIERS[/bold cyan]")
    agents = [swarm.create_agent(f"agent_{i:02d}") for i in range(1, 7)]

    # Each agent explores, learns, gets wounded, achieves victories
    agents[0].explored("route_alpha", outcome="success", cost=0.3)
    agents[0].explored("route_beta", outcome="dead_end", cost=0.8)
    agents[0].dead_end("route_beta", "blocked by resource contention at node 7")
    agents[0].fought("resource_conflict_node7", "redirected via node 9", success=True)
    agents[0].victory("first_path_completion", "route_alpha fastest with 3 agents")
    agents[0].practiced("pathfinding")
    agents[0].practiced("pathfinding")
    agents[0].practiced("pathfinding")

    agents[1].explored("route_gamma", outcome="success", cost=0.4)
    agents[1].wounded("parallel_execution_failed", "lock contention — never parallelize write ops")
    agents[1].victory("discovered_shortcut_via_node12", "saves 34% traversal time")
    agents[1].practiced("threat_detection")
    agents[1].practiced("threat_detection")

    agents[2].explored("route_delta", outcome="partial", cost=0.6)
    agents[2].fought("anomalous_signal_sector_c", "isolated and logged", success=True)
    agents[2].practiced("signal_analysis")
    agents[2].practiced("signal_analysis")
    agents[2].practiced("signal_analysis")
    agents[2].practiced("signal_analysis")

    agents[3].explored("route_alpha", outcome="success", cost=0.25)
    agents[3].victory("confirmed_route_alpha_optimal", "3 agents confirm: fastest path")
    agents[3].bonded_with("agent_01", outcome="positive")
    agents[3].practiced("pathfinding")

    agents[4].explored("sector_c_perimeter", outcome="success", cost=0.5)
    agents[4].fought("boundary_violation_attempt", "blocked and traced to origin", success=True)
    agents[4].practiced("boundary_defense")
    agents[4].practiced("boundary_defense")

    agents[5].explored("route_beta", outcome="dead_end", cost=0.8)
    agents[5].wounded("route_beta_again", "confirmed dead end — add to avoidance list")
    agents[5].victory("cross_validated_dead_ends", "built shared avoidance map with agent_01")
    agents[5].bonded_with("agent_01", outcome="positive")
    agents[5].practiced("pattern_recognition")

    # ── Form 2 squads ──────────────────────────────────────────────────────────
    cprint("\n[bold cyan]TIER 2 — SQUADS[/bold cyan]")

    squad_alpha = swarm.create_squad(
        ["agent_01", "agent_03", "agent_04"],
        squad_id="squad_alpha"
    )
    squad_alpha.learned_tactic(
        "three_agent_parallel_sweep",
        context="open terrain exploration",
        success_rate=0.85,
    )
    squad_alpha.learned_tactic(
        "node_relay_communication",
        context="long distance coordination",
        success_rate=0.78,
    )
    squad_alpha.add_doctrine(
        "Always confirm route_alpha with minimum 2 agents before committing full squad",
        origin="repeated success pattern",
        confidence=0.9,
    )
    squad_alpha.add_doctrine(
        "Never send single agent to route_beta — confirmed dead end",
        origin="agents 01 and 06 wounds",
        confidence=0.95,
    )
    squad_alpha.campaign_complete(
        "Operation Pathfinder",
        outcome="success",
        key_lesson="route_alpha + node relay = optimal strategy",
        duration_steps=127,
    )
    squad_alpha.update_cohesion(0.3)

    squad_beta = swarm.create_squad(
        ["agent_02", "agent_05", "agent_06"],
        squad_id="squad_beta"
    )
    squad_beta.learned_tactic(
        "boundary_perimeter_sweep",
        context="security and threat containment",
        success_rate=0.90,
    )
    squad_beta.add_doctrine(
        "Signal analysis agent always leads sector_c approach",
        origin="agent_03 successful anomaly detection",
        confidence=0.85,
    )
    squad_beta.campaign_complete(
        "Operation Sentinel",
        outcome="success",
        key_lesson="specialized roles outperform generalists in security tasks",
        duration_steps=89,
    )
    squad_beta.update_cohesion(0.25)

    # ── Command — emergence ────────────────────────────────────────────────────
    cprint("\n[bold cyan]TIER 3 — COMMAND[/bold cyan]")

    swarm.command.record_emergence(
        "spontaneous_route_consensus",
        "All 6 agents independently converged on route_alpha as optimal — without coordination",
        agent_count=6,
        iterations=127,
        efficiency_gain=0.34,
        task_id="pathfinder_op",
    )

    swarm.command.record_emergence(
        "dead_end_collective_memory",
        "Agents shared dead-end knowledge laterally — new agents avoided route_beta instantly",
        agent_count=6,
        iterations=45,
        efficiency_gain=0.28,
    )

    swarm.command.record_generation(
        generation=1,
        avg_performance=0.73,
        top_skill="pathfinding",
        dominant_tactic="three_agent_parallel_sweep",
        agent_count=6,
    )

    swarm.command.induct(
        "First Spontaneous Consensus",
        "6 agents converged on optimal route without central direction — pure emergence",
        significance=0.95,
    )

    swarm.command.induct(
        "Collective Dead-End Memory",
        "Swarm developed shared avoidance map laterally — no explicit coordination",
        agent_id="agent_01",
        significance=0.90,
    )

    # ── Intelligence flow ──────────────────────────────────────────────────────
    cprint("\n[bold cyan]INTELLIGENCE FLOW[/bold cyan]")
    swarm.flow()

    # ── Display ────────────────────────────────────────────────────────────────
    display_status(swarm)

    # ── Start API ──────────────────────────────────────────────────────────────
    swarm.start_api()
    time.sleep(0.5)

    cprint(f"[bold green]✓ FORGE_SWARM_MEMORY initialized[/bold green]")
    cprint(f"[dim]  API: http://localhost:{API_PORT}[/dim]")
    cprint(f"[dim]  DB:  {DB_PATH}[/dim]\n")

    return swarm


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    swarm = run_demo()
    try:
        cprint("[dim]Press Ctrl+C to exit[/dim]")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cprint("\n[yellow]FORGE_SWARM_MEMORY shutting down...[/yellow]")
