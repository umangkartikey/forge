"""
FORGE Hippocampus — forge_hippocampus.py
=========================================
AI analog of the hippocampus — the memory consolidator.
Bridges forge_temporal (perception) and forge_prefrontal (decisions)
into lasting, retrievable, evolving long-term knowledge.

Architecture:
  ConsolidationEngine     → converts working memory into long-term storage
  EpisodicMemoryStore     → timestamped event sequences with full context
  SemanticLongTermStore   → distilled facts extracted from episodes
  SpatialMemoryMap        → cognitive map of entities, locations, environments
  PatternCompletion       → recalls full memory from partial cue
  NoveltyDetector         → flags things never seen before
  ReconsolidationEngine   → updates old memories when contradicted
  MemoryDecayModel        → Ebbinghaus forgetting curve
"""

import json
import time
import uuid
import sqlite3
import threading
import math
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Optional
from dataclasses import dataclass, field, asdict

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.layout import Layout
    from rich.text import Text
    from rich.columns import Columns
    from rich.rule import Rule
    from rich.tree import Tree
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

DB_PATH  = "forge_hippocampus.db"
API_PORT = 7780
VERSION  = "1.0.0"

console = Console() if HAS_RICH else None

# Ebbinghaus forgetting curve: retention = e^(-t/stability)
# stability increases with each successful recall
BASE_STABILITY   = 1.0    # days
MAX_STABILITY    = 365.0  # days — memories can last up to a year
NOVELTY_THRESHOLD = 0.35  # similarity below this = novel
RECONSOLIDATE_THRESHOLD = 0.6  # similarity above this = update existing

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class Episode:
    id:            str  = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:     str  = field(default_factory=lambda: datetime.now().isoformat())
    title:         str  = ""
    context:       dict = field(default_factory=dict)   # full perception event
    decision:      dict = field(default_factory=dict)   # prefrontal decision
    entities:      list = field(default_factory=list)   # who was involved
    location:      str  = ""                            # where
    emotion_tag:   str  = "neutral"
    threat_level:  int  = 0
    keywords:      list = field(default_factory=list)
    importance:    float = 0.5                          # 0-1
    recall_count:  int  = 0
    stability:     float = BASE_STABILITY               # Ebbinghaus stability
    last_recalled: str  = field(default_factory=lambda: datetime.now().isoformat())
    consolidated:  bool = False
    novelty_score: float = 1.0                          # 1=totally new, 0=seen before

@dataclass
class SemanticFact:
    id:         str  = field(default_factory=lambda: str(uuid.uuid4())[:8])
    fact:       str  = ""
    confidence: float = 0.5
    source_episodes: list = field(default_factory=list)
    category:   str  = "general"
    created:    str  = field(default_factory=lambda: datetime.now().isoformat())
    updated:    str  = field(default_factory=lambda: datetime.now().isoformat())
    reinforced: int  = 0
    contradictions: list = field(default_factory=list)

@dataclass
class SpatialNode:
    id:         str  = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:       str  = ""
    node_type:  str  = "entity"   # entity | location | concept
    position:   dict = field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    connections: list = field(default_factory=list)
    visit_count: int  = 0
    last_seen:  str  = field(default_factory=lambda: datetime.now().isoformat())
    attributes: dict = field(default_factory=dict)
    threat_history: list = field(default_factory=list)

@dataclass
class MemoryTrace:
    """Lightweight index entry for pattern completion."""
    episode_id:  str  = ""
    fingerprint: str  = ""
    keywords:    list = field(default_factory=list)
    emotion_tag: str  = "neutral"
    threat_level: int = 0
    timestamp:   str  = field(default_factory=lambda: datetime.now().isoformat())

# ─── Database ─────────────────────────────────────────────────────────────────

class HippocampusDB:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init()

    def _init(self):
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY, timestamp TEXT, title TEXT,
                    context TEXT, decision TEXT, entities TEXT,
                    location TEXT, emotion_tag TEXT, threat_level INTEGER,
                    keywords TEXT, importance REAL, recall_count INTEGER,
                    stability REAL, last_recalled TEXT,
                    consolidated INTEGER, novelty_score REAL
                );
                CREATE TABLE IF NOT EXISTS semantic_facts (
                    id TEXT PRIMARY KEY, fact TEXT UNIQUE, confidence REAL,
                    source_episodes TEXT, category TEXT, created TEXT,
                    updated TEXT, reinforced INTEGER, contradictions TEXT
                );
                CREATE TABLE IF NOT EXISTS spatial_nodes (
                    id TEXT PRIMARY KEY, name TEXT UNIQUE, node_type TEXT,
                    position TEXT, connections TEXT, visit_count INTEGER,
                    last_seen TEXT, attributes TEXT, threat_history TEXT
                );
                CREATE TABLE IF NOT EXISTS memory_traces (
                    episode_id TEXT PRIMARY KEY, fingerprint TEXT,
                    keywords TEXT, emotion_tag TEXT,
                    threat_level INTEGER, timestamp TEXT
                );
                CREATE TABLE IF NOT EXISTS consolidation_log (
                    id TEXT PRIMARY KEY, timestamp TEXT, episode_id TEXT,
                    action TEXT, notes TEXT
                );
            """)
            self.conn.commit()

    def save_episode(self, e: Episode):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO episodes VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (e.id, e.timestamp, e.title,
                  json.dumps(e.context), json.dumps(e.decision),
                  json.dumps(e.entities), e.location, e.emotion_tag,
                  e.threat_level, json.dumps(e.keywords), e.importance,
                  e.recall_count, e.stability, e.last_recalled,
                  int(e.consolidated), e.novelty_score))
            self.conn.commit()

    def get_episodes(self, limit=50, min_importance=0.0):
        with self.lock:
            return self.conn.execute("""
                SELECT id, timestamp, title, emotion_tag, threat_level,
                       importance, recall_count, stability, novelty_score
                FROM episodes WHERE importance >= ?
                ORDER BY timestamp DESC LIMIT ?
            """, (min_importance, limit)).fetchall()

    def get_episode_full(self, episode_id: str) -> Optional[dict]:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM episodes WHERE id=?", (episode_id,)
            ).fetchone()
            if not row: return None
            cols = ["id","timestamp","title","context","decision","entities",
                    "location","emotion_tag","threat_level","keywords","importance",
                    "recall_count","stability","last_recalled","consolidated","novelty_score"]
            d = dict(zip(cols, row))
            for f in ["context","decision","entities","keywords"]:
                d[f] = json.loads(d[f]) if d[f] else {}
            return d

    def save_fact(self, f: SemanticFact):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO semantic_facts VALUES
                (?,?,?,?,?,?,?,?,?)
            """, (f.id, f.fact, f.confidence,
                  json.dumps(f.source_episodes), f.category,
                  f.created, f.updated, f.reinforced,
                  json.dumps(f.contradictions)))
            self.conn.commit()

    def get_facts(self, category=None, limit=50):
        with self.lock:
            if category:
                return self.conn.execute(
                    "SELECT fact, confidence, reinforced, category FROM semantic_facts WHERE category=? ORDER BY confidence DESC LIMIT ?",
                    (category, limit)).fetchall()
            return self.conn.execute(
                "SELECT fact, confidence, reinforced, category FROM semantic_facts ORDER BY confidence DESC LIMIT ?",
                (limit,)).fetchall()

    def save_node(self, n: SpatialNode):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO spatial_nodes VALUES
                (?,?,?,?,?,?,?,?,?)
            """, (n.id, n.name, n.node_type,
                  json.dumps(n.position), json.dumps(n.connections),
                  n.visit_count, n.last_seen,
                  json.dumps(n.attributes), json.dumps(n.threat_history)))
            self.conn.commit()

    def get_nodes(self, node_type=None):
        with self.lock:
            if node_type:
                return self.conn.execute(
                    "SELECT id, name, node_type, visit_count, last_seen FROM spatial_nodes WHERE node_type=?",
                    (node_type,)).fetchall()
            return self.conn.execute(
                "SELECT id, name, node_type, visit_count, last_seen FROM spatial_nodes"
            ).fetchall()

    def save_trace(self, t: MemoryTrace):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO memory_traces VALUES (?,?,?,?,?,?)
            """, (t.episode_id, t.fingerprint, json.dumps(t.keywords),
                  t.emotion_tag, t.threat_level, t.timestamp))
            self.conn.commit()

    def get_traces(self):
        with self.lock:
            return self.conn.execute(
                "SELECT episode_id, fingerprint, keywords, emotion_tag, threat_level FROM memory_traces"
            ).fetchall()

    def log_consolidation(self, episode_id: str, action: str, notes: str):
        with self.lock:
            self.conn.execute(
                "INSERT INTO consolidation_log VALUES (?,?,?,?,?)",
                (str(uuid.uuid4())[:8], datetime.now().isoformat(),
                 episode_id, action, notes)
            )
            self.conn.commit()

# ─── Memory Decay Model ───────────────────────────────────────────────────────

class MemoryDecayModel:
    """
    Ebbinghaus forgetting curve.
    retention(t) = e^(-t / stability)
    Each recall strengthens stability — spaced repetition emerges naturally.
    """

    def retention(self, episode: Episode) -> float:
        last = datetime.fromisoformat(episode.last_recalled)
        t_days = (datetime.now() - last).total_seconds() / 86400.0
        return math.exp(-t_days / max(episode.stability, 0.01))

    def after_recall(self, episode: Episode) -> Episode:
        """Strengthen memory after successful recall."""
        episode.recall_count  += 1
        episode.stability      = min(MAX_STABILITY, episode.stability * 2.0)
        episode.last_recalled  = datetime.now().isoformat()
        return episode

    def importance_score(self, episode: Episode) -> float:
        """Importance = threat × emotion × novelty × retention."""
        threat_w  = episode.threat_level / 4.0
        emotion_w = {"fear":0.9,"anger":0.85,"joy":0.5,"sadness":0.7,
                     "surprise":0.75,"trust":0.4,"neutral":0.2}.get(episode.emotion_tag, 0.3)
        novelty_w = episode.novelty_score
        retention = self.retention(episode)
        return round(min(1.0, (threat_w*0.4 + emotion_w*0.25 + novelty_w*0.2 + retention*0.15)), 3)

    def should_forget(self, episode: Episode) -> bool:
        return self.retention(episode) < 0.05 and episode.importance < 0.3


# ─── Novelty Detector ─────────────────────────────────────────────────────────

class NoveltyDetector:
    """
    Compares new input fingerprint against known memory traces.
    Novelty = 1 - max_similarity to any existing trace.
    """

    def fingerprint(self, keywords: list, emotion: str, threat: int) -> str:
        raw = f"{sorted(keywords)}_{emotion}_{threat}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def similarity(self, fp1: str, fp2: str) -> float:
        """Simple character-level overlap as proxy for semantic similarity."""
        if fp1 == fp2: return 1.0
        matches = sum(a == b for a, b in zip(fp1, fp2))
        return matches / max(len(fp1), len(fp2))

    def assess(self, keywords: list, emotion: str, threat: int,
               traces: list) -> tuple[float, Optional[str]]:
        """
        Returns (novelty_score, most_similar_episode_id).
        novelty=1.0 → never seen anything like this
        novelty=0.0 → exact match in memory
        """
        fp = self.fingerprint(keywords, emotion, threat)
        if not traces:
            return 1.0, None

        best_sim   = 0.0
        best_ep_id = None
        for row in traces:
            ep_id, existing_fp = row[0], row[1]
            existing_kw = json.loads(row[2]) if isinstance(row[2], str) else row[2]
            existing_em = row[3]
            existing_th = row[4]

            # Multi-dimensional similarity
            fp_sim      = self.similarity(fp, existing_fp)
            emotion_sim = 1.0 if emotion == existing_em else 0.0
            threat_sim  = 1.0 - abs(threat - existing_th) / 4.0
            kw_overlap  = len(set(keywords) & set(existing_kw)) / max(len(set(keywords) | set(existing_kw)), 1)

            sim = (fp_sim*0.3 + emotion_sim*0.2 + threat_sim*0.2 + kw_overlap*0.3)
            if sim > best_sim:
                best_sim   = sim
                best_ep_id = ep_id

        novelty = round(1.0 - best_sim, 3)
        return novelty, best_ep_id


# ─── Reconsolidation Engine ───────────────────────────────────────────────────

class ReconsolidationEngine:
    """
    When new information contradicts or extends an existing memory,
    reconsolidation updates the old memory rather than creating a duplicate.
    This is how the brain revises the past.
    """

    def reconsolidate(self, existing: Episode, new_context: dict,
                      new_decision: dict, db: HippocampusDB) -> Episode:
        """Merge new information into existing episode."""
        old_threat = existing.threat_level
        new_threat = new_context.get("threat", old_threat)

        # Update threat if escalated
        if new_threat > old_threat:
            existing.threat_level = new_threat
            note = f"Threat escalated {old_threat}→{new_threat}"
        else:
            note = "Context reinforced without escalation"

        # Merge keywords
        new_kw = new_context.get("keywords", [])
        existing.keywords = list(set(existing.keywords + new_kw))[:20]

        # Update emotion if stronger
        new_emotion = new_context.get("emotional", {}).get("dominant", existing.emotion_tag)
        emotion_strength = {"fear":0.9,"anger":0.85,"sadness":0.7,"joy":0.5,
                           "surprise":0.75,"trust":0.4,"neutral":0.2}
        if emotion_strength.get(new_emotion, 0) > emotion_strength.get(existing.emotion_tag, 0):
            existing.emotion_tag = new_emotion

        # Lower novelty score (less novel now — seen again)
        existing.novelty_score = max(0.0, existing.novelty_score - 0.15)

        # Update decision if more decisive
        if new_decision:
            existing.decision = new_decision

        existing.consolidated = True
        db.save_episode(existing)
        db.log_consolidation(existing.id, "RECONSOLIDATE", note)
        return existing


# ─── Pattern Completion ───────────────────────────────────────────────────────

class PatternCompletion:
    """
    Recalls full episodes from partial cues.
    Like the hippocampus: a fragment of a smell recalls an entire memory.
    """

    def recall(self, cue: dict, episodes: dict[str, Episode],
               traces: list, novelty_detector: NoveltyDetector) -> list[dict]:
        """
        Given a partial cue (keywords, emotion, threat),
        find matching episodes ranked by relevance × retention.
        """
        cue_keywords = cue.get("keywords", [])
        cue_emotion  = cue.get("emotion", "neutral")
        cue_threat   = cue.get("threat", 0)

        results = []
        for row in traces:
            ep_id      = row[0]
            stored_kw  = json.loads(row[2]) if isinstance(row[2], str) else row[2]
            stored_em  = row[3]
            stored_th  = row[4]

            # Keyword overlap
            kw_overlap = len(set(cue_keywords) & set(stored_kw)) / max(len(set(cue_keywords) | set(stored_kw)), 1)
            emotion_match = 1.0 if cue_emotion == stored_em else 0.3
            threat_match  = 1.0 - abs(cue_threat - stored_th) / 4.0

            relevance = (kw_overlap*0.5 + emotion_match*0.25 + threat_match*0.25)
            if relevance > 0.2 and ep_id in episodes:
                ep = episodes[ep_id]
                score = relevance * novelty_detector.retention(ep) if hasattr(novelty_detector, 'retention') else relevance
                results.append({
                    "episode_id":  ep_id,
                    "title":       ep.title,
                    "timestamp":   ep.timestamp,
                    "relevance":   round(relevance, 3),
                    "retention":   round(math.exp(-(datetime.now() - datetime.fromisoformat(ep.last_recalled)).total_seconds() / 86400.0 / max(ep.stability, 0.01)), 3),
                    "threat":      ep.threat_level,
                    "emotion":     ep.emotion_tag,
                    "importance":  ep.importance,
                    "keywords":    ep.keywords[:5]
                })

        return sorted(results, key=lambda r: r["relevance"] * r["retention"], reverse=True)[:5]


# ─── Spatial Memory Map ───────────────────────────────────────────────────────

class SpatialMemoryMap:
    """
    Cognitive map of entities, locations, and concepts.
    Nodes = things encountered. Edges = relationships.
    Positions drift based on association strength.
    """

    def __init__(self, db: HippocampusDB):
        self.db    = db
        self.nodes: dict[str, SpatialNode] = {}
        self._layout_counter = 0

    def _next_position(self, node_type: str) -> dict:
        """Assign position based on type cluster."""
        self._layout_counter += 1
        angle  = self._layout_counter * 137.5  # golden angle
        radius = {"entity":3.0, "location":6.0, "concept":1.5}.get(node_type, 4.0)
        rad    = math.radians(angle)
        return {"x": round(radius * math.cos(rad), 2),
                "y": round(radius * math.sin(rad), 2)}

    def register(self, name: str, node_type: str, attributes: dict = {}) -> SpatialNode:
        if name in self.nodes:
            node = self.nodes[name]
            node.visit_count += 1
            node.last_seen    = datetime.now().isoformat()
            node.attributes.update(attributes)
        else:
            node = SpatialNode(
                name=name, node_type=node_type,
                position=self._next_position(node_type),
                visit_count=1, attributes=attributes
            )
            self.nodes[name] = node
        self.db.save_node(node)
        return node

    def connect(self, name_a: str, name_b: str, weight: float = 1.0):
        for name in [name_a, name_b]:
            if name not in self.nodes:
                self.register(name, "entity")
        for src, tgt in [(name_a, name_b), (name_b, name_a)]:
            node = self.nodes[src]
            existing = next((c for c in node.connections if c["to"] == tgt), None)
            if existing:
                existing["weight"] = round(min(10.0, existing["weight"] + weight), 2)
            else:
                node.connections.append({"to": tgt, "weight": round(weight, 2)})
            self.db.save_node(node)

    def record_threat(self, entity_name: str, threat: int):
        if entity_name in self.nodes:
            self.nodes[entity_name].threat_history.append({
                "threat": threat, "time": datetime.now().isoformat()
            })
            self.db.save_node(self.nodes[entity_name])

    def get_threat_profile(self, entity_name: str) -> dict:
        if entity_name not in self.nodes:
            return {"entity": entity_name, "known": False}
        node = self.nodes[entity_name]
        history = node.threat_history
        if not history:
            return {"entity": entity_name, "known": True, "avg_threat": 0, "visits": node.visit_count}
        avg = sum(h["threat"] for h in history) / len(history)
        return {
            "entity":     entity_name,
            "known":      True,
            "avg_threat": round(avg, 2),
            "max_threat": max(h["threat"] for h in history),
            "visits":     node.visit_count,
            "connections":len(node.connections)
        }

    def snapshot(self) -> dict:
        return {
            "total_nodes": len(self.nodes),
            "entities":    sum(1 for n in self.nodes.values() if n.node_type == "entity"),
            "locations":   sum(1 for n in self.nodes.values() if n.node_type == "location"),
            "concepts":    sum(1 for n in self.nodes.values() if n.node_type == "concept"),
            "nodes":       [{"name": n.name, "type": n.node_type,
                             "visits": n.visit_count, "connections": len(n.connections)}
                            for n in sorted(self.nodes.values(),
                                           key=lambda x: x.visit_count, reverse=True)[:10]]
        }


# ─── Semantic Long-Term Store ─────────────────────────────────────────────────

class SemanticLongTermStore:
    """
    Distills repeated patterns from episodes into stable facts.
    If something appears in 3+ episodes with high confidence → it becomes a fact.
    """

    def __init__(self, db: HippocampusDB):
        self.db    = db
        self.facts: dict[str, SemanticFact] = {}

    def distill(self, episode: Episode) -> list[SemanticFact]:
        """Extract semantic facts from an episode."""
        new_facts = []

        # Threat pattern fact
        if episode.threat_level >= 2:
            fact_text = f"Entity pattern at threat≥2 involves: {', '.join(episode.keywords[:3])}"
            new_facts.append(self._upsert(fact_text, "threat_pattern",
                                          episode.id, episode.threat_level / 4.0))

        # Emotion-context fact
        if episode.emotion_tag not in ["neutral"]:
            fact_text = f"{episode.emotion_tag.capitalize()} context correlates with: {', '.join(episode.keywords[:3])}"
            new_facts.append(self._upsert(fact_text, "emotion_pattern",
                                          episode.id, 0.5))

        # Location fact
        if episode.location:
            fact_text = f"Location '{episode.location}' associated with threat={episode.threat_level}"
            new_facts.append(self._upsert(fact_text, "location",
                                          episode.id, 0.7))

        # High-importance fact
        if episode.importance >= 0.7:
            fact_text = f"High-importance event: {episode.title[:60]}"
            new_facts.append(self._upsert(fact_text, "significant_event",
                                          episode.id, episode.importance))

        return [f for f in new_facts if f]

    def _upsert(self, fact_text: str, category: str,
                episode_id: str, confidence: float) -> Optional[SemanticFact]:
        # Check for existing similar fact
        existing = next(
            (f for f in self.facts.values()
             if self._text_sim(f.fact, fact_text) > 0.7), None
        )
        if existing:
            existing.reinforced    += 1
            existing.confidence     = min(1.0, existing.confidence + 0.05)
            existing.updated        = datetime.now().isoformat()
            if episode_id not in existing.source_episodes:
                existing.source_episodes.append(episode_id)
            self.db.save_fact(existing)
            return existing
        else:
            sf = SemanticFact(
                fact=fact_text, confidence=confidence,
                source_episodes=[episode_id], category=category
            )
            self.facts[sf.id] = sf
            self.db.save_fact(sf)
            return sf

    def _text_sim(self, a: str, b: str) -> float:
        wa = set(a.lower().split())
        wb = set(b.lower().split())
        return len(wa & wb) / max(len(wa | wb), 1)

    def query(self, keywords: list, top_k: int = 5) -> list[SemanticFact]:
        scored = []
        for f in self.facts.values():
            score = self._text_sim(f.fact, " ".join(keywords))
            if score > 0.1:
                scored.append((score * f.confidence, f))
        return [f for _, f in sorted(scored, reverse=True)[:top_k]]


# ─── Consolidation Engine ─────────────────────────────────────────────────────

class ConsolidationEngine:
    """
    The core hippocampal function.
    Takes raw perception + decision → encodes lasting memory.
    """

    def __init__(self, db: HippocampusDB, novelty: NoveltyDetector,
                 reconsolidation: ReconsolidationEngine,
                 decay: MemoryDecayModel, spatial: SpatialMemoryMap,
                 semantic: SemanticLongTermStore):
        self.db              = db
        self.novelty         = novelty
        self.reconsolidation = reconsolidation
        self.decay           = decay
        self.spatial         = spatial
        self.semantic        = semantic

    def consolidate(self, perception: dict, decision: dict = {}) -> tuple[Episode, str]:
        """
        Main consolidation cycle.
        Returns (Episode, action) where action is one of:
        NEW_MEMORY | RECONSOLIDATED | REINFORCED | FORGOTTEN_PREVENTED
        """
        # Extract core fields
        threat    = perception.get("threat", 0)
        emotional = perception.get("emotional") or {}
        social    = perception.get("social") or {}
        visual    = perception.get("visual") or {}
        auditory  = perception.get("auditory") or {}
        semantic_ctx = perception.get("semantic") or {}
        conclusion   = perception.get("conclusion", "")

        emotion_tag = emotional.get("dominant", "neutral")
        entity_name = social.get("entity", perception.get("entity_name", "unknown"))
        location    = visual.get("scene_type", auditory.get("environment", "UNKNOWN"))

        # Build keyword set
        keywords = []
        if semantic_ctx.get("keywords"): keywords += semantic_ctx["keywords"][:5]
        if visual.get("scene_type"):     keywords.append(visual["scene_type"])
        if emotion_tag != "neutral":     keywords.append(emotion_tag)
        if entity_name != "unknown":     keywords.append(entity_name)
        keywords = list(dict.fromkeys(keywords))[:12]

        # Novelty assessment
        traces  = self.db.get_traces()
        novelty_score, similar_ep_id = self.novelty.assess(keywords, emotion_tag, threat, traces)

        # Determine action
        if novelty_score > NOVELTY_THRESHOLD:
            action = "NEW_MEMORY"
        elif similar_ep_id and novelty_score < (1 - RECONSOLIDATE_THRESHOLD):
            action = "RECONSOLIDATED"
        else:
            action = "REINFORCED"

        if action in ["RECONSOLIDATED", "REINFORCED"] and similar_ep_id:
            full = self.db.get_episode_full(similar_ep_id)
            if full:
                existing = Episode(**{k: full[k] for k in full if k in Episode.__dataclass_fields__})
                existing = self.reconsolidation.reconsolidate(existing, perception, decision, self.db)
                self._update_spatial(entity_name, location, threat, keywords)
                self.semantic.distill(existing)
                return existing, action

        # Create new episode
        title = self._make_title(conclusion, threat, emotion_tag, entity_name)
        ep = Episode(
            title=title, context=perception, decision=decision,
            entities=[entity_name] if entity_name != "unknown" else [],
            location=location, emotion_tag=emotion_tag,
            threat_level=threat, keywords=keywords,
            novelty_score=novelty_score
        )
        ep.importance = self.decay.importance_score(ep)

        # Save everything
        self.db.save_episode(ep)
        self.db.save_trace(MemoryTrace(
            episode_id=ep.id,
            fingerprint=self.novelty.fingerprint(keywords, emotion_tag, threat),
            keywords=keywords, emotion_tag=emotion_tag, threat_level=threat
        ))
        self.db.log_consolidation(ep.id, "NEW_MEMORY",
                                  f"novelty={novelty_score:.2f} importance={ep.importance:.2f}")

        self._update_spatial(entity_name, location, threat, keywords)
        self.semantic.distill(ep)

        return ep, action

    def _make_title(self, conclusion: str, threat: int, emotion: str, entity: str) -> str:
        prefix = {4:"🔴 CRITICAL",3:"🟠 HIGH",2:"🟡 MEDIUM",1:"🔵 LOW",0:"🟢 NORMAL"}.get(threat,"⚪")
        label  = conclusion[:50] if conclusion else f"{emotion} event involving {entity}"
        return f"{prefix} | {label}"

    def _update_spatial(self, entity: str, location: str, threat: int, keywords: list):
        if entity and entity != "unknown":
            self.spatial.register(entity, "entity", {"last_threat": threat})
            self.spatial.record_threat(entity, threat)
        if location and location != "UNKNOWN":
            self.spatial.register(location, "location")
            if entity and entity != "unknown":
                self.spatial.connect(entity, location, weight=1.0)
        for kw in keywords[:3]:
            self.spatial.register(kw, "concept")
            if entity and entity != "unknown":
                self.spatial.connect(entity, kw, weight=0.5)


# ─── Hippocampus (Main System) ────────────────────────────────────────────────

class ForgeHippocampus:
    def __init__(self):
        self.db              = HippocampusDB()
        self.decay           = MemoryDecayModel()
        self.novelty         = NoveltyDetector()
        self.reconsolidation = ReconsolidationEngine()
        self.spatial         = SpatialMemoryMap(self.db)
        self.semantic_store  = SemanticLongTermStore(self.db)
        self.pattern         = PatternCompletion()
        self.consolidation   = ConsolidationEngine(
            self.db, self.novelty, self.reconsolidation,
            self.decay, self.spatial, self.semantic_store
        )
        self.episodes: dict[str, Episode] = {}

    def remember(self, perception: dict, decision: dict = {}) -> dict:
        """Full memory consolidation cycle."""
        ep, action = self.consolidation.consolidate(perception, decision)
        self.episodes[ep.id] = ep
        return {
            "episode_id":   ep.id,
            "title":        ep.title,
            "action":       action,
            "novelty":      ep.novelty_score,
            "importance":   ep.importance,
            "threat":       ep.threat_level,
            "emotion":      ep.emotion_tag,
            "keywords":     ep.keywords,
            "location":     ep.location,
            "facts_derived":len(self.semantic_store.facts)
        }

    def recall(self, cue: dict) -> list[dict]:
        """Pattern completion — recall from partial cue."""
        traces = self.db.get_traces()
        results = self.pattern.recall(cue, self.episodes, traces, self.novelty)
        # Strengthen recalled memories
        for r in results:
            if r["episode_id"] in self.episodes:
                ep = self.episodes[r["episode_id"]]
                ep = self.decay.after_recall(ep)
                self.episodes[ep.id] = ep
                self.db.save_episode(ep)
        return results

    def forget_check(self) -> list[str]:
        """Identify memories that have decayed below threshold."""
        forgotten = []
        for ep in list(self.episodes.values()):
            if self.decay.should_forget(ep):
                forgotten.append(ep.id)
        return forgotten

    def get_status(self) -> dict:
        retentions = [self.decay.retention(ep) for ep in self.episodes.values()]
        avg_ret = round(sum(retentions)/len(retentions), 3) if retentions else 0.0
        return {
            "version":         VERSION,
            "total_episodes":  len(self.episodes),
            "semantic_facts":  len(self.semantic_store.facts),
            "spatial_map":     self.spatial.snapshot(),
            "avg_retention":   avg_ret,
            "forgotten_risk":  len(self.forget_check()),
            "total_traces":    len(self.db.get_traces())
        }


# ─── Rich UI ──────────────────────────────────────────────────────────────────

def render_consolidation(result: dict, ep_num: int):
    if not HAS_RICH:
        print(f"\n[EP {result['episode_id']}] {result['action']} | {result['title'][:60]}")
        return

    action_color = {
        "NEW_MEMORY":     "cyan",
        "RECONSOLIDATED": "yellow",
        "REINFORCED":     "green"
    }.get(result["action"], "white")

    threat_color = {0:"green",1:"blue",2:"yellow",3:"red",4:"bright_red"}.get(result["threat"],"white")

    console.print(Rule(
        f"[bold cyan]⬡ FORGE HIPPOCAMPUS[/bold cyan]  "
        f"[dim]Episode {ep_num}  {result['episode_id']}[/dim]"
    ))

    # Title + action
    console.print(Panel(
        f"[bold]{result['title']}[/bold]",
        subtitle=f"[bold {action_color}]{result['action']}[/bold {action_color}]",
        border_style=action_color
    ))

    # Stats row
    stats = Table(box=box.SIMPLE, show_header=False, expand=True)
    stats.add_column("k", style="dim", width=18)
    stats.add_column("v")
    stats.add_row("Novelty",
        f"{'[cyan]' if result['novelty'] > 0.7 else '[yellow]' if result['novelty'] > 0.35 else '[green]'}"
        f"{'★ NEW' if result['novelty'] > 0.7 else '~ SIMILAR' if result['novelty'] > 0.35 else '○ KNOWN'}"
        f"{'[/cyan]' if result['novelty'] > 0.7 else '[/yellow]' if result['novelty'] > 0.35 else '[/green]'}"
        f"  ({result['novelty']:.2f})")
    stats.add_row("Importance",
        f"[{'bright_red' if result['importance'] > 0.7 else 'yellow' if result['importance'] > 0.4 else 'dim'}]"
        f"{'HIGH' if result['importance'] > 0.7 else 'MEDIUM' if result['importance'] > 0.4 else 'LOW'}"
        f"[/{'bright_red' if result['importance'] > 0.7 else 'yellow' if result['importance'] > 0.4 else 'dim'}]"
        f"  ({result['importance']:.3f})")
    stats.add_row(f"Threat",
        f"[{threat_color}]{result['threat']}[/{threat_color}]")
    stats.add_row("Emotion",      result["emotion"])
    stats.add_row("Location",     result["location"])
    stats.add_row("Keywords",     ", ".join(result["keywords"][:6]))
    stats.add_row("Facts in LTM", str(result["facts_derived"]))

    console.print(stats)


def render_recall(results: list[dict], cue: dict):
    if not HAS_RICH:
        print(f"\nRecall results for cue {cue}: {len(results)} matches")
        return

    console.print(Rule("[bold magenta]⬡ PATTERN COMPLETION — RECALL[/bold magenta]"))
    if not results:
        console.print("[dim]No matching memories found.[/dim]")
        return

    t = Table(box=box.ROUNDED, border_style="magenta")
    t.add_column("ID",        width=10)
    t.add_column("Title",     width=35)
    t.add_column("Relevance", justify="right", width=10)
    t.add_column("Retention", justify="right", width=10)
    t.add_column("Threat",    justify="center", width=8)
    t.add_column("Emotion",   width=12)

    for r in results:
        ret_color = "green" if r["retention"] > 0.7 else "yellow" if r["retention"] > 0.3 else "red"
        t.add_row(
            r["episode_id"],
            r["title"][:34],
            f"{r['relevance']:.3f}",
            f"[{ret_color}]{r['retention']:.3f}[/{ret_color}]",
            str(r["threat"]),
            r["emotion"]
        )
    console.print(t)


def run_demo():
    if HAS_RICH:
        console.print(Panel.fit(
            "[bold cyan]FORGE HIPPOCAMPUS[/bold cyan]\n"
            "[dim]Long-Term Memory Consolidation — The Memory Architect[/dim]\n"
            f"[dim]Version {VERSION}[/dim]",
            border_style="cyan"
        ))

    hc = ForgeHippocampus()

    # Simulate a sequence of perception + decision events
    events = [
        {
            "perception": {
                "threat": 0, "anomaly": False,
                "conclusion": "✓ NORMAL — Technician Alice at server room",
                "emotional": {"dominant": "trust", "intensity": 0.3},
                "social":    {"entity": "alice", "inferred_intent": "COOPERATIVE_REQUEST", "trust_score": 0.8},
                "semantic":  {"inference": "BENIGN_REQUEST", "keywords": ["firmware","update","server"]},
                "visual":    {"scene_type": "INDOOR_TECHNICAL", "threat_objects": 0},
                "auditory":  {"environment": "QUIET_SPACE", "anomaly_detected": False}
            },
            "decision": {"action": "MONITOR", "net_value": 0.72}
        },
        {
            "perception": {
                "threat": 2, "anomaly": False,
                "conclusion": "⚠ MEDIUM — Suspicious entity near restricted area",
                "emotional": {"dominant": "fear", "intensity": 0.6},
                "social":    {"entity": "unknown_x", "inferred_intent": "COERCIVE_DEMAND", "trust_score": 0.2},
                "semantic":  {"inference": "THREAT_SEMANTIC", "keywords": ["access","bypass","override"]},
                "visual":    {"scene_type": "LOW_VISIBILITY", "threat_objects": 0},
                "auditory":  {"environment": "NOISY_ENVIRONMENT", "anomaly_detected": False}
            },
            "decision": {"action": "ALERT", "net_value": 0.81}
        },
        {
            "perception": {
                "threat": 4, "anomaly": True,
                "conclusion": "⚠ CRITICAL — Weapon detected, intrusion confirmed",
                "emotional": {"dominant": "fear", "intensity": 1.0},
                "social":    {"entity": "unknown_x", "inferred_intent": "INTRUSION_ATTEMPT", "trust_score": 0.05},
                "semantic":  {"inference": "THREAT_SEMANTIC", "keywords": ["weapon","breach","network","server"]},
                "visual":    {"scene_type": "LOW_VISIBILITY", "threat_objects": 2},
                "auditory":  {"environment": "NOISY_ENVIRONMENT", "anomaly_detected": True}
            },
            "decision": {"action": "ESCALATE", "net_value": 0.91}
        },
        {
            "perception": {
                # Same entity, repeat visit — should RECONSOLIDATE
                "threat": 1, "anomaly": False,
                "conclusion": "✓ NORMAL — Technician Alice routine check",
                "emotional": {"dominant": "trust", "intensity": 0.2},
                "social":    {"entity": "alice", "inferred_intent": "COOPERATIVE_REQUEST", "trust_score": 0.85},
                "semantic":  {"inference": "BENIGN_REQUEST", "keywords": ["firmware","check","server","update"]},
                "visual":    {"scene_type": "INDOOR_TECHNICAL", "threat_objects": 0},
                "auditory":  {"environment": "QUIET_SPACE", "anomaly_detected": False}
            },
            "decision": {"action": "COLLABORATE", "net_value": 0.68}
        },
        {
            "perception": {
                "threat": 3, "anomaly": True,
                "conclusion": "⚡ HIGH — Network anomaly cascade detected",
                "emotional": {"dominant": "surprise", "intensity": 0.8},
                "social":    {"entity": "system_node_7", "inferred_intent": "INTRUSION_ATTEMPT", "trust_score": 0.1},
                "semantic":  {"inference": "TECHNICAL_CONTEXT", "keywords": ["network","intrusion","packet","anomaly"]},
                "visual":    {"scene_type": "UNCLASSIFIED", "threat_objects": 0},
                "auditory":  {"environment": "NEUTRAL_ENVIRONMENT", "anomaly_detected": True}
            },
            "decision": {"action": "BLOCK", "net_value": 0.87}
        }
    ]

    for i, ev in enumerate(events):
        if HAS_RICH:
            console.print(f"\n[bold dim]━━━ CONSOLIDATING EVENT {i+1} ━━━[/bold dim]")
        result = hc.remember(ev["perception"], ev["decision"])
        render_consolidation(result, i+1)
        time.sleep(0.2)

    # Pattern completion demo
    if HAS_RICH:
        console.print(f"\n[bold dim]━━━ PATTERN COMPLETION — RECALL CUE ━━━[/bold dim]")
    cue = {"keywords": ["weapon","breach","server"], "emotion": "fear", "threat": 3}
    recalls = hc.recall(cue)
    render_recall(recalls, cue)

    # Spatial map
    if HAS_RICH:
        console.print(f"\n[bold dim]━━━ SPATIAL MEMORY MAP ━━━[/bold dim]")
        snap = hc.spatial.snapshot()
        spatial_table = Table(box=box.SIMPLE, title="Cognitive Map Nodes", title_style="cyan")
        spatial_table.add_column("Name",    style="cyan")
        spatial_table.add_column("Type",    style="dim")
        spatial_table.add_column("Visits",  justify="right")
        spatial_table.add_column("Connections", justify="right")
        for n in snap["nodes"]:
            spatial_table.add_row(n["name"], n["type"], str(n["visits"]), str(n["connections"]))
        console.print(spatial_table)

        # Threat profiles
        console.print(f"\n[bold dim]━━━ ENTITY THREAT PROFILES ━━━[/bold dim]")
        for entity in ["alice", "unknown_x", "system_node_7"]:
            profile = hc.spatial.get_threat_profile(entity)
            color = "red" if profile.get("avg_threat", 0) >= 2 else "green"
            console.print(
                f"  [{color}]{entity}[/{color}]  "
                f"avg_threat={profile.get('avg_threat',0)}  "
                f"max={profile.get('max_threat',0)}  "
                f"visits={profile.get('visits',0)}"
            )

        # Semantic facts
        console.print(f"\n[bold dim]━━━ SEMANTIC LONG-TERM MEMORY ━━━[/bold dim]")
        facts_table = Table(box=box.SIMPLE, title="Distilled Facts", title_style="magenta")
        facts_table.add_column("Fact", width=50)
        facts_table.add_column("Category", width=18)
        facts_table.add_column("Confidence", justify="right")
        for f in list(hc.semantic_store.facts.values())[:8]:
            facts_table.add_row(f.fact[:50], f.category, f"{f.confidence:.2f}")
        console.print(facts_table)

        # Final status
        status = hc.get_status()
        status_table = Table(title="HIPPOCAMPUS STATUS", box=box.DOUBLE_EDGE, border_style="cyan")
        status_table.add_column("Metric", style="cyan")
        status_table.add_column("Value",  style="white")
        for k, v in status.items():
            if isinstance(v, dict):
                status_table.add_row(k, f"{v.get('total_nodes','')} nodes / {v.get('entities','')} entities")
            else:
                status_table.add_row(k, str(v))
        console.print(status_table)


# ─── HTTP API ─────────────────────────────────────────────────────────────────

def run_api(hc: ForgeHippocampus):
    if not HAS_FLASK: return
    app = Flask(__name__)

    @app.route("/remember", methods=["POST"])
    def remember():
        data = request.json or {}
        result = hc.remember(data.get("perception", {}), data.get("decision", {}))
        return jsonify(result)

    @app.route("/recall", methods=["POST"])
    def recall():
        cue = request.json or {}
        return jsonify(hc.recall(cue))

    @app.route("/episodes", methods=["GET"])
    def episodes():
        rows = hc.db.get_episodes(50)
        return jsonify([{"id":r[0],"timestamp":r[1],"title":r[2],
                        "emotion":r[3],"threat":r[4],"importance":r[5],
                        "recalls":r[6],"stability":r[7],"novelty":r[8]} for r in rows])

    @app.route("/facts", methods=["GET"])
    def facts():
        rows = hc.db.get_facts()
        return jsonify([{"fact":r[0],"confidence":r[1],"reinforced":r[2],"category":r[3]} for r in rows])

    @app.route("/spatial", methods=["GET"])
    def spatial():
        return jsonify(hc.spatial.snapshot())

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify(hc.get_status())

    app.run(host="0.0.0.0", port=API_PORT, debug=False)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    hc = ForgeHippocampus()
    if "--api" in sys.argv:
        t = threading.Thread(target=run_api, args=(hc,), daemon=True)
        t.start()
    run_demo()
