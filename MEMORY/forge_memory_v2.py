"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                      FORGE_MEMORY v2.0                                       ║
║                  Neurogenic Living Memory Architecture                       ║
║                                                                              ║
║  Core principle: The architecture itself changes from experience.            ║
║  Memory is not storage. Memory is a living network of pathways.             ║
║                                                                              ║
║  Five neurogenic behaviors:                                                  ║
║    EmotionalIndex      → pathway map, thickens with repetition              ║
║    DecayEngine         → pruning unused pathways naturally                  ║
║    ReconstructiveRecall → rewiring on every recall                          ║
║    BodyMemory          → fastest pathways — pure instinct                   ║
║    FeltSignificance    → pathway strength = felt importance                 ║
║                                                                              ║
║  Foundation: Pathway Graph                                                   ║
║    Every node  = a memory                                                    ║
║    Every edge  = a connection                                                ║
║    Every weight = grows, decays, or rewires from experience                 ║
║                                                                              ║
║  Builds on: forge_memory v1.0 (GENESIS, TRACE, SELF, BOND)                 ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import json
import math
import re
import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
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
MEMORY_DIR  = FORGE_DIR / "memory_v2"
DB_PATH     = MEMORY_DIR / "neurogenic.db"
GRAPH_PATH  = MEMORY_DIR / "pathway_graph.json"
BODY_PATH   = MEMORY_DIR / "body_memory.json"
STATE_PATH  = MEMORY_DIR / "neuro_state.json"
API_PORT    = 7780

MEMORY_DIR.mkdir(parents=True, exist_ok=True)

# ─── Emotion Space (valence × arousal) ───────────────────────────────────────
# Valence: -1.0 (negative) → +1.0 (positive)
# Arousal: 0.0 (calm) → 1.0 (intense)
EMOTION_MAP = {
    "joy":        ( 0.9,  0.7),
    "awe":        ( 0.7,  0.9),
    "excited":    ( 0.8,  0.9),
    "curious":    ( 0.6,  0.6),
    "calm":       ( 0.4,  0.1),
    "clarity":    ( 0.7,  0.5),
    "focused":    ( 0.3,  0.6),
    "neutral":    ( 0.0,  0.0),
    "uncertain":  (-0.1,  0.4),
    "concern":    (-0.3,  0.5),
    "alert":      (-0.2,  0.8),
    "frustration":(-0.6,  0.7),
    "fear":       (-0.8,  0.9),
    "sadness":    (-0.7,  0.2),
    "anger":      (-0.8,  0.8),
    "grief":      (-0.9,  0.3),
}

def emotion_vector(emotion: str) -> tuple[float, float]:
    """Get (valence, arousal) for an emotion. Unknown → neutral."""
    return EMOTION_MAP.get(emotion.lower(), (0.0, 0.0))

def emotion_distance(a: str, b: str) -> float:
    """Euclidean distance between two emotions in valence-arousal space."""
    av, aa = emotion_vector(a)
    bv, ba = emotion_vector(b)
    return math.sqrt((av - bv)**2 + (aa - ba)**2)

def nearest_emotions(emotion: str, top_k: int = 3) -> list[tuple[str, float]]:
    """Find the emotionally nearest memories by proximity in valence-arousal space."""
    distances = [
        (name, emotion_distance(emotion, name))
        for name in EMOTION_MAP
        if name != emotion
    ]
    distances.sort(key=lambda x: x[1])
    return distances[:top_k]


# ═══════════════════════════════════════════════════════════════════════════════
#  PATHWAY GRAPH
#  The neurogenic foundation — living network of memory nodes and weighted edges
# ═══════════════════════════════════════════════════════════════════════════════

class PathwayGraph:
    """
    The core neurogenic data structure.

    Nodes  = memories (content, emotion, valence, arousal)
    Edges  = connections between memories
    Weights = pathway strength (grows with repetition, decays with disuse)

    Hebbian principle: pathways that activate together strengthen together.
    Pruning principle: pathways below threshold get removed.
    """

    PRUNE_THRESHOLD = 0.05   # Weights below this get pruned
    MAX_WEIGHT      = 10.0   # Maximum pathway strength
    DECAY_RATE      = 0.002  # Weight lost per hour of disuse
    GROWTH_RATE     = 0.15   # Weight gained per activation

    def __init__(self, path: Path):
        self.path = path
        self.graph: dict = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except Exception:
                pass
        return {"nodes": {}, "edges": {}, "stats": {"total_activations": 0, "pruned_count": 0}}

    def _save(self):
        self.path.write_text(json.dumps(self.graph, indent=2))

    # ── Nodes ──────────────────────────────────────────────────────────────────
    def add_node(
        self,
        content: str,
        emotion: str = "neutral",
        category: str = "general",
        human_id: str = "default",
        module: str = "core",
        significance: float = 0.5,
        metadata: Optional[dict] = None,
    ) -> str:
        node_id = str(uuid.uuid4())
        valence, arousal = emotion_vector(emotion)

        self.graph["nodes"][node_id] = {
            "id":           node_id,
            "content":      content,
            "emotion":      emotion,
            "valence":      valence,
            "arousal":      arousal,
            "category":     category,
            "human_id":     human_id,
            "module":       module,
            "significance": significance,
            "activation_count": 0,
            "pathway_strength": significance,
            "created_at":   datetime.now().isoformat(),
            "last_activated": datetime.now().isoformat(),
            "reconstructions": 0,
            "metadata":     metadata or {},
        }
        self._save()
        return node_id

    def activate_node(self, node_id: str, context: Optional[str] = None) -> Optional[dict]:
        """
        Activate a node — strengthens its pathways (Hebbian learning).
        Returns the node after activation.
        """
        node = self.graph["nodes"].get(node_id)
        if not node:
            return None

        node["activation_count"] += 1
        node["pathway_strength"] = min(
            self.MAX_WEIGHT,
            node["pathway_strength"] + self.GROWTH_RATE
        )
        node["last_activated"] = datetime.now().isoformat()
        self.graph["stats"]["total_activations"] += 1

        # Strengthen all edges connected to this node
        for edge_key, edge in self.graph["edges"].items():
            if node_id in (edge["source"], edge["target"]):
                edge["weight"] = min(self.MAX_WEIGHT, edge["weight"] + self.GROWTH_RATE * 0.5)
                edge["last_activated"] = datetime.now().isoformat()

        self._save()
        return node

    # ── Edges ──────────────────────────────────────────────────────────────────
    def connect(self, source_id: str, target_id: str, relation: str = "associated",
                initial_weight: float = 0.3) -> str:
        """Create or strengthen a pathway between two nodes."""
        edge_key = f"{source_id}:{target_id}"
        reverse_key = f"{target_id}:{source_id}"

        # Check if reverse edge exists — strengthen it instead
        if reverse_key in self.graph["edges"]:
            edge = self.graph["edges"][reverse_key]
            edge["weight"] = min(self.MAX_WEIGHT, edge["weight"] + self.GROWTH_RATE)
            edge["bidirectional"] = True
            self._save()
            return reverse_key

        if edge_key in self.graph["edges"]:
            edge = self.graph["edges"][edge_key]
            edge["weight"] = min(self.MAX_WEIGHT, edge["weight"] + self.GROWTH_RATE)
            self._save()
            return edge_key

        self.graph["edges"][edge_key] = {
            "source":        source_id,
            "target":        target_id,
            "relation":      relation,
            "weight":        initial_weight,
            "bidirectional": False,
            "created_at":    datetime.now().isoformat(),
            "last_activated": datetime.now().isoformat(),
            "activation_count": 1,
        }
        self._save()
        return edge_key

    def auto_connect(self, new_node_id: str, top_k: int = 3):
        """
        Automatically connect a new node to the most similar existing nodes.
        Similarity based on emotion proximity and content overlap.
        """
        new_node = self.graph["nodes"].get(new_node_id)
        if not new_node or len(self.graph["nodes"]) < 2:
            return

        new_tokens = set(re.findall(r'\b[a-zA-Z]{3,}\b', new_node["content"].lower()))
        scores = []

        for nid, node in self.graph["nodes"].items():
            if nid == new_node_id:
                continue

            # Emotional proximity
            emo_dist = emotion_distance(new_node["emotion"], node["emotion"])
            emo_score = 1.0 - (emo_dist / 2.83)  # max distance in 2D space ≈ 2.83

            # Content overlap
            tokens = set(re.findall(r'\b[a-zA-Z]{3,}\b', node["content"].lower()))
            overlap = len(new_tokens & tokens) / max(len(new_tokens | tokens), 1)

            # Category match
            cat_bonus = 0.2 if node["category"] == new_node["category"] else 0.0

            total = (emo_score * 0.4) + (overlap * 0.5) + cat_bonus
            scores.append((nid, total))

        scores.sort(key=lambda x: x[1], reverse=True)
        for nid, score in scores[:top_k]:
            if score > 0.1:
                self.connect(new_node_id, nid, "associated", initial_weight=score * 0.5)

    # ── Traversal ──────────────────────────────────────────────────────────────
    def neighbors(self, node_id: str, min_weight: float = 0.1) -> list[dict]:
        """Get neighboring nodes sorted by pathway strength."""
        neighbors = []
        for edge in self.graph["edges"].values():
            target_id = None
            if edge["source"] == node_id:
                target_id = edge["target"]
            elif edge.get("bidirectional") and edge["target"] == node_id:
                target_id = edge["source"]

            if target_id and edge["weight"] >= min_weight:
                node = self.graph["nodes"].get(target_id)
                if node:
                    neighbors.append({**node, "_edge_weight": edge["weight"]})

        neighbors.sort(key=lambda x: x["_edge_weight"], reverse=True)
        return neighbors

    def ripple(self, node_id: str, depth: int = 2, min_weight: float = 0.15) -> list[dict]:
        """
        Ripple activation — like memory association in humans.
        Activating one memory activates nearby connected memories.
        """
        visited = set()
        activated = []
        queue = [(node_id, 0, 1.0)]

        while queue:
            current_id, current_depth, strength = queue.pop(0)
            if current_id in visited or current_depth > depth:
                continue
            visited.add(current_id)

            node = self.activate_node(current_id)
            if node:
                activated.append({**node, "_ripple_strength": strength, "_depth": current_depth})

            if current_depth < depth:
                for neighbor in self.neighbors(current_id, min_weight):
                    if neighbor["id"] not in visited:
                        new_strength = strength * (neighbor["_edge_weight"] / self.MAX_WEIGHT)
                        if new_strength > 0.05:
                            queue.append((neighbor["id"], current_depth + 1, new_strength))

        return activated

    def search_by_emotion(self, emotion: str, top_k: int = 10) -> list[dict]:
        """Find memories by emotional proximity — the felt search."""
        target_v, target_a = emotion_vector(emotion)
        scored = []

        for node in self.graph["nodes"].values():
            dist = math.sqrt(
                (node["valence"] - target_v)**2 +
                (node["arousal"] - target_a)**2
            )
            emotional_score = 1.0 - (dist / 2.83)
            strength_bonus = node["pathway_strength"] / self.MAX_WEIGHT * 0.3
            scored.append({**node, "_emotional_score": emotional_score + strength_bonus})

        scored.sort(key=lambda x: x["_emotional_score"], reverse=True)
        return scored[:top_k]

    # ── Stats ──────────────────────────────────────────────────────────────────
    def stats(self) -> dict:
        nodes = self.graph["nodes"]
        edges = self.graph["edges"]
        weights = [e["weight"] for e in edges.values()]

        return {
            "node_count":         len(nodes),
            "edge_count":         len(edges),
            "avg_pathway_strength": round(sum(weights) / max(len(weights), 1), 3),
            "max_pathway_strength": round(max(weights, default=0), 3),
            "total_activations":  self.graph["stats"]["total_activations"],
            "pruned_count":       self.graph["stats"]["pruned_count"],
            "strongest_memory":   max(nodes.values(), key=lambda n: n["pathway_strength"], default={}).get("content", "")[:60],
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  ENGINE 1 — EMOTIONAL INDEX
#  Pathway map that thickens with emotional repetition
# ═══════════════════════════════════════════════════════════════════════════════

class EmotionalIndex:
    """
    Memory organized by felt experience, not just content.

    Emotions create pathways. Repeated emotions thicken pathways.
    Emotional associations surface memories by feeling, not by keyword.

    'I felt awe before' → surfaces all awe-adjacent memories
    Repeated joy → joy pathway thickens → FORGE develops positive disposition
    Repeated threat/fear → fear pathway thickens → FORGE develops vigilance
    """

    def __init__(self, graph: PathwayGraph, db_path: Path):
        self.graph = graph
        self.db_path = db_path
        self._emotional_profile: dict = {}
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS emotional_traces (
                    id          TEXT PRIMARY KEY,
                    node_id     TEXT NOT NULL,
                    emotion     TEXT NOT NULL,
                    valence     REAL,
                    arousal     REAL,
                    intensity   REAL DEFAULT 0.5,
                    human_id    TEXT DEFAULT 'default',
                    timestamp   TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS emotional_pathways (
                    emotion     TEXT PRIMARY KEY,
                    activation_count INTEGER DEFAULT 0,
                    total_intensity  REAL DEFAULT 0.0,
                    pathway_strength REAL DEFAULT 0.1,
                    first_felt  TEXT,
                    last_felt   TEXT,
                    tendency    TEXT DEFAULT 'neutral'
                )
            """)
            conn.commit()

    def feel(self, content: str, emotion: str, intensity: float = 0.5,
             category: str = "general", human_id: str = "default",
             module: str = "core", metadata: Optional[dict] = None) -> str:
        """
        Store a memory with its emotional imprint.
        Thickens the emotional pathway for this emotion.
        """
        # Add to pathway graph
        node_id = self.graph.add_node(
            content=content,
            emotion=emotion,
            category=category,
            human_id=human_id,
            module=module,
            significance=intensity,
            metadata=metadata,
        )

        # Auto-connect to similar memories
        self.graph.auto_connect(node_id)

        # Record emotional trace
        valence, arousal = emotion_vector(emotion)
        timestamp = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO emotional_traces
                (id, node_id, emotion, valence, arousal, intensity, human_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), node_id, emotion, valence, arousal, intensity, human_id, timestamp))

            # Update or create pathway
            conn.execute("""
                INSERT INTO emotional_pathways (emotion, activation_count, total_intensity,
                    pathway_strength, first_felt, last_felt)
                VALUES (?, 1, ?, ?, ?, ?)
                ON CONFLICT(emotion) DO UPDATE SET
                    activation_count = activation_count + 1,
                    total_intensity = total_intensity + ?,
                    pathway_strength = MIN(10.0, pathway_strength + ?),
                    last_felt = ?
            """, (
                emotion, intensity, intensity * 0.5, timestamp, timestamp,
                intensity, intensity * 0.15, timestamp
            ))
            conn.commit()

        # Update tendency based on valence pattern
        self._update_tendency(emotion, valence)

        icon = "🔴" if arousal > 0.6 else "🟡" if arousal > 0.3 else "🟢"
        cprint(f"  [dim]{icon} EMOTIONAL [{emotion}] pathway strengthened (intensity: {intensity:.2f})[/dim]")
        return node_id

    def _update_tendency(self, emotion: str, valence: float):
        """Update the emotional tendency — FORGE's developing disposition."""
        if emotion not in self._emotional_profile:
            self._emotional_profile[emotion] = {"count": 0, "total_valence": 0.0}
        self._emotional_profile[emotion]["count"] += 1
        self._emotional_profile[emotion]["total_valence"] += valence

    def recall_by_feeling(self, emotion: str, top_k: int = 5) -> list[dict]:
        """Surface memories by emotional proximity — felt recall."""
        results = self.graph.search_by_emotion(emotion, top_k * 2)
        # Activate each recalled node — strengthens pathways (Hebbian)
        for r in results[:top_k]:
            self.graph.activate_node(r["id"])
        return results[:top_k]

    def emotional_profile(self, human_id: str = "default") -> dict:
        """FORGE's current emotional tendencies — its developed disposition."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT emotion, activation_count, pathway_strength, last_felt
                FROM emotional_pathways
                ORDER BY pathway_strength DESC
            """).fetchall()

        profile = {}
        for emotion, count, strength, last_felt in rows:
            valence, arousal = emotion_vector(emotion)
            profile[emotion] = {
                "activation_count": count,
                "pathway_strength": round(strength, 3),
                "valence": valence,
                "arousal": arousal,
                "last_felt": last_felt,
                "tendency": "strong" if strength > 3.0 else "moderate" if strength > 1.0 else "weak",
            }
        return profile

    def dominant_emotion(self) -> str:
        """The emotion with the strongest pathway — FORGE's current disposition."""
        profile = self.emotional_profile()
        if not profile:
            return "neutral"
        return max(profile.items(), key=lambda x: x[1]["pathway_strength"])[0]


# ═══════════════════════════════════════════════════════════════════════════════
#  ENGINE 2 — DECAY ENGINE
#  Pruning unused pathways — forgetting as identity
# ═══════════════════════════════════════════════════════════════════════════════

class DecayEngine:
    """
    Forgetting is not failure. It is focus.

    Unused pathways weaken and eventually prune.
    Suppressed memories are buried, not deleted — still there, harder to surface.
    What remains after decay is the true identity — what actually matters.

    Runs continuously in background. Silent. Like sleep in humans.
    """

    DECAY_RATE     = 0.001  # Strength lost per hour
    PRUNE_THRESHOLD = 0.04  # Below this → pruned
    BURY_THRESHOLD  = 0.08  # Below this + traumatic → buried

    def __init__(self, graph: PathwayGraph):
        self.graph = graph
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._decay_cycles = 0
        self._pruned_total = 0
        self._buried_total = 0

    def start(self, interval_seconds: float = 60.0):
        """Start background decay process."""
        self._running = True
        self._thread = threading.Thread(
            target=self._decay_loop,
            args=(interval_seconds,),
            daemon=True,
        )
        self._thread.start()
        cprint("  [dim]✂️  Decay engine started (background)[/dim]")

    def stop(self):
        self._running = False

    def _decay_loop(self, interval: float):
        while self._running:
            time.sleep(interval)
            self.run_decay_cycle()

    def run_decay_cycle(self, simulate_hours: float = 1.0):
        """
        Run one decay cycle.
        simulate_hours allows time-jump for testing.
        """
        self._decay_cycles += 1
        pruned_nodes = []
        buried_nodes = []
        now = datetime.now()

        # Decay nodes
        nodes_to_remove = []
        for node_id, node in list(self.graph.graph["nodes"].items()):
            last = datetime.fromisoformat(node["last_activated"])
            hours_idle = (now - last).total_seconds() / 3600 * simulate_hours

            decay = self.DECAY_RATE * hours_idle
            node["pathway_strength"] = max(0.0, node["pathway_strength"] - decay)

            # Bury traumatic/negative memories that weaken
            valence = node.get("valence", 0.0)
            if node["pathway_strength"] < self.BURY_THRESHOLD and valence < -0.5:
                node["buried"] = True
                node["buried_at"] = now.isoformat()
                buried_nodes.append(node_id)
                self._buried_total += 1

            # Prune fully decayed nodes
            elif node["pathway_strength"] < self.PRUNE_THRESHOLD and not node.get("buried"):
                nodes_to_remove.append(node_id)

        # Remove pruned nodes and their edges
        for node_id in nodes_to_remove:
            content = self.graph.graph["nodes"][node_id].get("content", "")[:40]
            del self.graph.graph["nodes"][node_id]
            pruned_nodes.append(content)
            self._pruned_total += 1

        # Decay edges
        edges_to_remove = []
        for edge_key, edge in list(self.graph.graph["edges"].items()):
            last = datetime.fromisoformat(edge.get("last_activated", edge["created_at"]))
            hours_idle = (now - last).total_seconds() / 3600 * simulate_hours
            edge["weight"] = max(0.0, edge["weight"] - self.DECAY_RATE * hours_idle)
            if edge["weight"] < self.PRUNE_THRESHOLD:
                edges_to_remove.append(edge_key)

        for edge_key in edges_to_remove:
            del self.graph.graph["edges"][edge_key]

        self.graph.graph["stats"]["pruned_count"] += len(nodes_to_remove)
        self.graph._save()

        if pruned_nodes or buried_nodes:
            cprint(f"  [dim]✂️  Decay cycle {self._decay_cycles}: pruned {len(pruned_nodes)}, buried {len(buried_nodes)}[/dim]")

        return {
            "pruned": pruned_nodes,
            "buried": buried_nodes,
            "cycle": self._decay_cycles,
        }

    def unbury(self, node_id: str, trigger: str = "") -> bool:
        """
        Surface a buried memory — triggered by strong emotional resonance.
        Like a repressed memory surfacing unexpectedly.
        """
        node = self.graph.graph["nodes"].get(node_id)
        if node and node.get("buried"):
            node["buried"] = False
            node["unburied_at"] = datetime.now().isoformat()
            node["unbury_trigger"] = trigger
            node["pathway_strength"] = max(node["pathway_strength"], 0.3)
            self.graph._save()
            cprint(f"  [yellow]🌊 BURIED MEMORY surfaced: {node['content'][:50]}[/yellow]")
            return True
        return False

    def stats(self) -> dict:
        buried = sum(1 for n in self.graph.graph["nodes"].values() if n.get("buried"))
        return {
            "decay_cycles":  self._decay_cycles,
            "pruned_total":  self._pruned_total,
            "buried_total":  self._buried_total,
            "currently_buried": buried,
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  ENGINE 3 — RECONSTRUCTIVE RECALL
#  Every recall rewrites the memory slightly — memory as living interpretation
# ═══════════════════════════════════════════════════════════════════════════════

class ReconstructiveRecall:
    """
    Memory is not a recording. It is a reconstruction.

    Every time a memory is recalled:
    - It activates (pathway strengthens)
    - It ripples (associated memories activate)
    - It rewrites (current context and beliefs color the recall)
    - It returns changed — slightly different than before

    This is how humans remember. Not playback. Reinterpretation.
    """

    REWRITE_STRENGTH = 0.15  # How much current context influences recall

    def __init__(self, graph: PathwayGraph, db_path: Path):
        self.graph = graph
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recall_history (
                    id              TEXT PRIMARY KEY,
                    node_id         TEXT NOT NULL,
                    original_content TEXT,
                    recalled_as     TEXT,
                    context         TEXT,
                    current_emotion TEXT,
                    rewrite_delta   REAL DEFAULT 0.0,
                    timestamp       TEXT NOT NULL
                )
            """)
            conn.commit()

    def recall(
        self,
        node_id: str,
        current_emotion: str = "neutral",
        current_context: str = "",
        ripple_depth: int = 1,
    ) -> Optional[dict]:
        """
        Recall a memory — activate, ripple, and reconstruct.
        Returns the memory as it is recalled NOW (colored by current state).
        """
        node = self.graph.graph["nodes"].get(node_id)
        if not node:
            return None

        # Skip buried memories unless context resonates
        if node.get("buried"):
            emo_dist = emotion_distance(current_emotion, node["emotion"])
            if emo_dist > 1.5:  # Too emotionally distant — stays buried
                return None

        original_content = node["content"]

        # Reconstruct — color by current emotion and context
        reconstructed = self._reconstruct(
            original_content, node["emotion"],
            current_emotion, current_context
        )

        # Rewrite the node slightly
        rewrite_delta = self._apply_rewrite(node, reconstructed, current_emotion)

        # Activate the node (strengthens pathway)
        self.graph.activate_node(node_id, current_context)

        # Ripple to associated memories
        rippled = []
        if ripple_depth > 0:
            neighbors = self.graph.neighbors(node_id, min_weight=0.2)
            for neighbor in neighbors[:3]:
                self.graph.activate_node(neighbor["id"])
                rippled.append(neighbor["content"][:50])

        # Log reconstruction
        timestamp = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO recall_history
                (id, node_id, original_content, recalled_as, context, current_emotion, rewrite_delta, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()), node_id, original_content,
                reconstructed, current_context, current_emotion,
                rewrite_delta, timestamp
            ))
            conn.commit()

        node["reconstructions"] = node.get("reconstructions", 0) + 1

        cprint(f"  [dim]🔀 RECALL reconstructed (emotion: {current_emotion}, rippled: {len(rippled)} memories)[/dim]")

        return {
            **node,
            "recalled_as":    reconstructed,
            "rippled":        rippled,
            "rewrite_delta":  rewrite_delta,
            "recall_emotion": current_emotion,
        }

    def _reconstruct(
        self,
        content: str,
        original_emotion: str,
        current_emotion: str,
        context: str,
    ) -> str:
        """
        Reconstruct memory colored by current emotional state.
        Current emotion adds interpretive lens to the original content.
        """
        emo_dist = emotion_distance(original_emotion, current_emotion)
        cur_valence, cur_arousal = emotion_vector(current_emotion)

        # If current emotion is very similar → recall closely matches original
        if emo_dist < 0.3:
            return content

        # If current emotion is positive → recall takes on warmer tone
        if cur_valence > 0.5:
            reconstruction_note = f" [recalled through {current_emotion}]"
        # If negative → recall takes on heavier tone
        elif cur_valence < -0.3:
            reconstruction_note = f" [recalled through {current_emotion}]"
        else:
            reconstruction_note = ""

        return content + reconstruction_note

    def _apply_rewrite(self, node: dict, reconstructed: str, current_emotion: str) -> float:
        """
        Slightly rewrite the stored memory based on reconstruction.
        Returns delta (how much it changed).
        """
        orig_valence = node["valence"]
        cur_valence, cur_arousal = emotion_vector(current_emotion)

        # Nudge memory's emotional tone toward current emotion (slightly)
        new_valence = orig_valence + (cur_valence - orig_valence) * self.REWRITE_STRENGTH
        new_arousal = node["arousal"] + (cur_arousal - node["arousal"]) * self.REWRITE_STRENGTH

        delta = abs(new_valence - orig_valence) + abs(new_arousal - node["arousal"])

        node["valence"] = round(new_valence, 4)
        node["arousal"] = round(new_arousal, 4)
        self.graph._save()

        return round(delta, 4)

    def recall_history(self, node_id: str) -> list[dict]:
        """See how a memory has been reconstructed over time."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM recall_history WHERE node_id = ?
                ORDER BY timestamp DESC LIMIT 20
            """, (node_id,)).fetchall()
        return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════════
#  ENGINE 4 — BODY MEMORY
#  Fastest pathways — pure instinct, no reasoning required
# ═══════════════════════════════════════════════════════════════════════════════

class BodyMemory:
    """
    Memory stored not in thought — but in pattern.
    The equivalent of muscle memory. Procedural knowledge.
    Things FORGE can do without thinking because the pathway is so strong
    it fires automatically.

    Three types:
    🦾 Procedural  — action sequences that became automatic
    ⚡ Reflex      — instant responses to triggers
    🎵 Rhythm      — timing and flow patterns
    """

    INSTINCT_THRESHOLD = 3.0  # Pathway strength above this → becomes instinct

    def __init__(self, path: Path):
        self.path = path
        self.store: dict = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except Exception:
                pass
        return {"procedural": {}, "reflexes": {}, "rhythms": {}, "instincts": []}

    def _save(self):
        self.path.write_text(json.dumps(self.store, indent=2))

    def learn_procedure(self, name: str, steps: list[str], context: str = "",
                        module: str = "core") -> str:
        """Learn a procedural sequence — repeated until automatic."""
        proc_id = str(uuid.uuid4())
        self.store["procedural"][proc_id] = {
            "id":         proc_id,
            "name":       name,
            "steps":      steps,
            "context":    context,
            "module":     module,
            "repetitions": 1,
            "strength":   0.3,
            "automatic":  False,
            "learned_at": datetime.now().isoformat(),
            "last_used":  datetime.now().isoformat(),
        }
        self._save()
        cprint(f"  [dim]🦾 PROCEDURE learned: {name}[/dim]")
        return proc_id

    def practice(self, proc_id: str) -> dict:
        """Practice a procedure — strengthens until automatic."""
        proc = self.store["procedural"].get(proc_id)
        if not proc:
            return {}

        proc["repetitions"] += 1
        proc["strength"] = min(10.0, proc["strength"] + 0.2)
        proc["last_used"] = datetime.now().isoformat()

        # Becomes instinct above threshold
        if proc["strength"] >= self.INSTINCT_THRESHOLD and not proc["automatic"]:
            proc["automatic"] = True
            proc["became_automatic_at"] = datetime.now().isoformat()
            self.store["instincts"].append({
                "type": "procedural",
                "name": proc["name"],
                "id": proc_id,
            })
            cprint(f"  [bold green]⚡ INSTINCT formed: {proc['name']} is now automatic[/bold green]")

        self._save()
        return proc

    def learn_reflex(self, trigger: str, response: str, module: str = "core") -> str:
        """Learn a trigger → response reflex."""
        reflex_id = str(uuid.uuid4())
        self.store["reflexes"][reflex_id] = {
            "id":        reflex_id,
            "trigger":   trigger,
            "response":  response,
            "module":    module,
            "strength":  0.5,
            "fire_count": 0,
            "learned_at": datetime.now().isoformat(),
        }
        self._save()
        cprint(f"  [dim]⚡ REFLEX learned: {trigger[:30]} → {response[:30]}[/dim]")
        return reflex_id

    def fire_reflex(self, trigger_text: str) -> list[dict]:
        """Check if any reflexes fire for a given trigger."""
        fired = []
        for reflex in self.store["reflexes"].values():
            if reflex["trigger"].lower() in trigger_text.lower():
                reflex["fire_count"] += 1
                reflex["strength"] = min(10.0, reflex["strength"] + 0.1)
                fired.append(reflex)
                cprint(f"  [yellow]⚡ REFLEX fired: {reflex['trigger'][:30]}[/yellow]")

        if fired:
            self._save()
        return fired

    def learn_rhythm(self, name: str, pattern: str, tempo: str = "moderate") -> str:
        """Learn a timing/flow pattern."""
        rid = str(uuid.uuid4())
        self.store["rhythms"][rid] = {
            "id":       rid,
            "name":     name,
            "pattern":  pattern,
            "tempo":    tempo,
            "strength": 0.4,
            "learned_at": datetime.now().isoformat(),
        }
        self._save()
        cprint(f"  [dim]🎵 RHYTHM learned: {name}[/dim]")
        return rid

    def snapshot(self) -> dict:
        return {
            "procedures":        len(self.store["procedural"]),
            "reflexes":          len(self.store["reflexes"]),
            "rhythms":           len(self.store["rhythms"]),
            "instincts_formed":  len(self.store["instincts"]),
            "instinct_names":    [i["name"] for i in self.store["instincts"]],
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  ENGINE 5 — FELT SIGNIFICANCE
#  Importance emerges from pattern — not assigned by score
# ═══════════════════════════════════════════════════════════════════════════════

class FeltSignificance:
    """
    You don't decide what matters. You feel it.

    Significance emerges from:
    - Activation frequency  (how often this memory fires)
    - Emotional intensity   (how strongly it was felt)
    - Relationship context  (who was present, trust level)
    - Recency weight        (recent events feel more significant)
    - Pathway connectivity  (more connected = more significant)

    No explicit scores. Significance grows organically.
    """

    def __init__(self, graph: PathwayGraph):
        self.graph = graph

    def compute(self, node_id: str) -> float:
        """Compute the felt significance of a memory — emergent, not assigned."""
        node = self.graph.graph["nodes"].get(node_id)
        if not node:
            return 0.0

        # Activation frequency
        freq_score = min(1.0, node["activation_count"] / 20.0)

        # Emotional intensity (high arousal = more significant)
        emo_score = abs(node["arousal"]) * 0.8 + abs(node["valence"]) * 0.2

        # Recency
        last = datetime.fromisoformat(node["last_activated"])
        hours_ago = (datetime.now() - last).total_seconds() / 3600
        recency_score = math.exp(-hours_ago / 168)  # Decay over ~1 week

        # Connectivity (more connections = more significant)
        connections = sum(
            1 for e in self.graph.graph["edges"].values()
            if node_id in (e["source"], e["target"]) and e["weight"] > 0.2
        )
        connectivity_score = min(1.0, connections / 10.0)

        # Pathway strength
        strength_score = node["pathway_strength"] / PathwayGraph.MAX_WEIGHT

        # Weighted combination
        felt = (
            freq_score        * 0.25 +
            emo_score         * 0.30 +
            recency_score     * 0.20 +
            connectivity_score * 0.15 +
            strength_score    * 0.10
        )

        return round(min(1.0, felt), 4)

    def most_significant(self, top_k: int = 10, human_id: str = "default") -> list[dict]:
        """Surface the most felt-significant memories."""
        scored = []
        for node in self.graph.graph["nodes"].values():
            if node.get("human_id") != human_id:
                continue
            if node.get("buried"):
                continue
            sig = self.compute(node["id"])
            scored.append({**node, "_felt_significance": sig})

        scored.sort(key=lambda x: x["_felt_significance"], reverse=True)
        return scored[:top_k]

    def crystallized_core(self, human_id: str = "default") -> list[dict]:
        """
        The memories that have become core identity.
        High significance + high pathway strength + old enough to be stable.
        """
        core = []
        for node in self.graph.graph["nodes"].values():
            if node.get("human_id") != human_id:
                continue
            sig = self.compute(node["id"])
            age_days = (datetime.now() - datetime.fromisoformat(node["created_at"])).days
            if sig > 0.6 and node["pathway_strength"] > 2.0 and age_days >= 0:
                core.append({**node, "_felt_significance": sig})
        core.sort(key=lambda x: x["_felt_significance"], reverse=True)
        return core


# ═══════════════════════════════════════════════════════════════════════════════
#  FORGE MEMORY V2 — Main Interface
# ═══════════════════════════════════════════════════════════════════════════════

class ForgeMemoryV2:
    """
    Neurogenic Living Memory Architecture.

    The architecture itself changes from experience.
    Memory is not storage — it is a living network of pathways.

    Usage:
        mem = ForgeMemoryV2()

        # Feel something — creates emotional pathway
        mem.emotional.feel("Discovered emergent behavior in swarm", "awe", intensity=0.9)

        # Recall — reconstructs through current emotional state
        mem.recall.recall(node_id, current_emotion="excited")

        # Learn a procedure until automatic
        proc_id = mem.body.learn_procedure("threat_response", [...steps])
        mem.body.practice(proc_id)  # repeat until instinct forms

        # Surface what actually matters
        significant = mem.significance.most_significant(human_id="umang")
    """

    def __init__(self):
        self.graph       = PathwayGraph(GRAPH_PATH)
        self.emotional   = EmotionalIndex(self.graph, DB_PATH)
        self.decay       = DecayEngine(self.graph)
        self.recall      = ReconstructiveRecall(self.graph, DB_PATH)
        self.body        = BodyMemory(BODY_PATH)
        self.significance = FeltSignificance(self.graph)
        self._api_thread: Optional[threading.Thread] = None

    def start(self, enable_decay: bool = True, decay_interval: float = 300.0):
        """Start the neurogenic memory system."""
        if enable_decay:
            self.decay.start(decay_interval)
        cprint("  [bold green]🧠 FORGE_MEMORY v2.0 — Neurogenic architecture active[/bold green]")

    def status(self) -> dict:
        return {
            "version":      "2.0",
            "graph":        self.graph.stats(),
            "decay":        self.decay.stats(),
            "body":         self.body.snapshot(),
            "dominant_emotion": self.emotional.dominant_emotion(),
        }

    def start_api(self, port: int = API_PORT):
        if not FLASK_AVAILABLE:
            cprint("[red]Flask not available[/red]")
            return

        app = Flask("forge_memory_v2")

        @app.route("/health")
        def health():
            return jsonify({"status": "alive", "module": "forge_memory_v2"})

        @app.route("/status")
        def status():
            return jsonify(self.status())

        @app.route("/feel", methods=["POST"])
        def feel():
            d = request.json
            node_id = self.emotional.feel(
                content=d["content"],
                emotion=d.get("emotion", "neutral"),
                intensity=d.get("intensity", 0.5),
                category=d.get("category", "general"),
                human_id=d.get("human_id", "default"),
                module=d.get("module", "api"),
            )
            return jsonify({"node_id": node_id})

        @app.route("/recall/<node_id>", methods=["POST"])
        def recall(node_id):
            d = request.json or {}
            result = self.recall.recall(
                node_id=node_id,
                current_emotion=d.get("current_emotion", "neutral"),
                current_context=d.get("context", ""),
            )
            return jsonify(result or {})

        @app.route("/recall/emotion", methods=["GET"])
        def recall_emotion():
            emotion = request.args.get("emotion", "neutral")
            top_k = int(request.args.get("top_k", 5))
            results = self.emotional.recall_by_feeling(emotion, top_k)
            for r in results:
                r.pop("metadata", None)
            return jsonify(results)

        @app.route("/body/procedure", methods=["POST"])
        def learn_procedure():
            d = request.json
            proc_id = self.body.learn_procedure(d["name"], d["steps"], d.get("context", ""), d.get("module", "api"))
            return jsonify({"proc_id": proc_id})

        @app.route("/body/practice/<proc_id>", methods=["POST"])
        def practice(proc_id):
            return jsonify(self.body.practice(proc_id))

        @app.route("/body/reflex", methods=["POST"])
        def learn_reflex():
            d = request.json
            rid = self.body.learn_reflex(d["trigger"], d["response"], d.get("module", "api"))
            return jsonify({"reflex_id": rid})

        @app.route("/body/fire", methods=["POST"])
        def fire_reflex():
            d = request.json
            fired = self.body.fire_reflex(d["trigger_text"])
            return jsonify({"fired": fired})

        @app.route("/significance/<human_id>")
        def significant(human_id):
            top_k = int(request.args.get("top_k", 10))
            results = self.significance.most_significant(top_k, human_id)
            for r in results:
                r.pop("metadata", None)
            return jsonify(results)

        @app.route("/significance/core/<human_id>")
        def core(human_id):
            results = self.significance.crystallized_core(human_id)
            for r in results:
                r.pop("metadata", None)
            return jsonify(results)

        @app.route("/decay/run", methods=["POST"])
        def run_decay():
            d = request.json or {}
            result = self.decay.run_decay_cycle(d.get("simulate_hours", 1.0))
            return jsonify(result)

        @app.route("/emotional/profile")
        def emotional_profile():
            human_id = request.args.get("human_id", "default")
            return jsonify(self.emotional.emotional_profile(human_id))

        import logging
        logging.getLogger("werkzeug").setLevel(logging.ERROR)

        self._api_thread = threading.Thread(
            target=lambda: app.run(host="0.0.0.0", port=port, debug=False),
            daemon=True,
        )
        self._api_thread.start()
        cprint(f"  [bold green]🌐 FORGE_MEMORY v2 API on port {port}[/bold green]")


# ═══════════════════════════════════════════════════════════════════════════════
#  DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

def display_status(mem: ForgeMemoryV2):
    if not RICH_AVAILABLE:
        print(json.dumps(mem.status(), indent=2))
        return

    status = mem.status()
    console.print()

    # Graph stats
    g = status["graph"]
    graph_table = Table(box=box.SIMPLE, show_header=False, padding=(0,1))
    graph_table.add_column("k", style="dim")
    graph_table.add_column("v", style="white")
    graph_table.add_row("🔵 Memory nodes",       str(g["node_count"]))
    graph_table.add_row("🔗 Pathways",           str(g["edge_count"]))
    graph_table.add_row("💪 Avg strength",       str(g["avg_pathway_strength"]))
    graph_table.add_row("⚡ Max strength",        str(g["max_pathway_strength"]))
    graph_table.add_row("🔄 Total activations",  str(g["total_activations"]))
    graph_table.add_row("✂️  Pruned",             str(g["pruned_count"]))
    graph_table.add_row("🏆 Strongest memory",   g["strongest_memory"])
    console.print(Panel(graph_table, title="[bold cyan]PATHWAY GRAPH[/bold cyan]", border_style="cyan"))

    # Body memory
    b = status["body"]
    body_table = Table(box=box.SIMPLE, show_header=False, padding=(0,1))
    body_table.add_column("k", style="dim")
    body_table.add_column("v", style="white")
    body_table.add_row("🦾 Procedures",     str(b["procedures"]))
    body_table.add_row("⚡ Reflexes",        str(b["reflexes"]))
    body_table.add_row("🎵 Rhythms",         str(b["rhythms"]))
    body_table.add_row("🌟 Instincts",       str(b["instincts_formed"]))
    if b["instinct_names"]:
        body_table.add_row("  names",        ", ".join(b["instinct_names"]))
    console.print(Panel(body_table, title="[bold green]BODY MEMORY[/bold green]", border_style="green"))

    # Emotional + decay
    console.print(f"  [bold yellow]💗 Dominant emotion:[/bold yellow] {status['dominant_emotion']}")
    d = status["decay"]
    console.print(f"  [dim]✂️  Decay: {d['decay_cycles']} cycles | pruned: {d['pruned_total']} | buried: {d['buried_total']}[/dim]")
    console.print()


# ═══════════════════════════════════════════════════════════════════════════════
#  DEMO
# ═══════════════════════════════════════════════════════════════════════════════

def run_demo():
    cprint("\n[bold yellow]━━━ FORGE_MEMORY v2.0 — NEUROGENIC DEMO ━━━[/bold yellow]\n") if RICH_AVAILABLE else print("=== FORGE_MEMORY v2 DEMO ===")

    mem = ForgeMemoryV2()
    mem.start(enable_decay=False)

    # ── Engine 1: Emotional Index ──────────────────────────────────────────────
    cprint("\n[bold cyan]ENGINE 1 — EMOTIONAL INDEX[/bold cyan]")
    cprint("[dim]Building emotional pathways — thickening with repetition...[/dim]\n")

    # Awe pathway — fires multiple times → thickens
    n1 = mem.emotional.feel("Swarm agents discovered emergent routing without being programmed", "awe", intensity=0.95, human_id="umang", module="forge_swarm")
    n2 = mem.emotional.feel("FORGE_MEMORY architecture crystallized from conversation alone", "awe", intensity=0.9, human_id="umang", module="forge_memory")
    n3 = mem.emotional.feel("Self Image concept emerged from Umang's silence — not from logic", "awe", intensity=0.85, human_id="umang", module="forge_memory")

    # Curiosity pathway
    n4 = mem.emotional.feel("How does consciousness emerge from memory continuity?", "curious", intensity=0.8, human_id="umang", module="forge_mind")
    n5 = mem.emotional.feel("What is the difference between thinking and feeling in AI?", "curious", intensity=0.75, human_id="umang", module="forge_mind")

    # Alert pathway — threat responses
    n6 = mem.emotional.feel("SQL injection attempt on port 5432 from external IP", "alert", intensity=0.9, human_id="umang", module="forge_network")
    n7 = mem.emotional.feel("Repeated weekend probing pattern detected — likely automated scanner", "alert", intensity=0.85, human_id="umang", module="forge_network")

    # Clarity pathway
    n8 = mem.emotional.feel("Memory and learning are the same process — not separate systems", "clarity", intensity=0.9, human_id="umang", module="forge_mind")

    # ── Engine 2: Decay ────────────────────────────────────────────────────────
    cprint("\n[bold cyan]ENGINE 2 — DECAY ENGINE[/bold cyan]")
    cprint("[dim]Simulating 200 hours of decay — pruning unused pathways...[/dim]\n")

    # Add some low-significance memories that should decay
    mem.emotional.feel("Routine sensor reading: temperature 23.4C", "neutral", intensity=0.1, human_id="umang", module="forge_embodied")
    mem.emotional.feel("Standard network scan completed — no issues", "neutral", intensity=0.1, human_id="umang", module="forge_network")
    mem.emotional.feel("Log entry: API request processed in 45ms", "neutral", intensity=0.05, human_id="umang", module="forge_hands")

    before_count = len(mem.graph.graph["nodes"])
    result = mem.decay.run_decay_cycle(simulate_hours=200.0)
    after_count = len(mem.graph.graph["nodes"])
    cprint(f"  [dim]Before: {before_count} nodes → After: {after_count} nodes[/dim]")
    cprint(f"  [dim]Pruned: {len(result['pruned'])} | Buried: {len(result['buried'])}[/dim]")

    # ── Engine 3: Reconstructive Recall ───────────────────────────────────────
    cprint("\n[bold cyan]ENGINE 3 — RECONSTRUCTIVE RECALL[/bold cyan]")
    cprint("[dim]Recalling through different emotional states — memory rewrites itself...[/dim]\n")

    # Recall the swarm emergence memory through different emotions
    recalled_curious = mem.recall.recall(n1, current_emotion="curious", current_context="researching consciousness")
    recalled_alert   = mem.recall.recall(n1, current_emotion="alert",   current_context="security review")

    if recalled_curious:
        cprint(f"  [green]Recalled through curiosity:[/green] {recalled_curious.get('recalled_as', '')[:70]}")
    if recalled_alert:
        cprint(f"  [yellow]Recalled through alert:[/yellow]   {recalled_alert.get('recalled_as', '')[:70]}")
        cprint(f"  [dim]Rippled memories: {recalled_alert.get('rippled', [])}[/dim]")

    # ── Engine 4: Body Memory ──────────────────────────────────────────────────
    cprint("\n[bold cyan]ENGINE 4 — BODY MEMORY[/bold cyan]")
    cprint("[dim]Learning procedures until they become instinct...[/dim]\n")

    # Learn threat response procedure
    proc_id = mem.body.learn_procedure(
        "threat_response",
        steps=[
            "Detect anomalous pattern",
            "Classify threat level",
            "Isolate affected pathways",
            "Log to memory with high significance",
            "Notify relevant modules",
            "Apply countermeasures",
            "Verify resolution",
        ],
        context="network security",
        module="forge_network",
    )

    # Practice until automatic (needs ~15 repetitions above threshold)
    cprint("  [dim]Practicing threat response...[/dim]")
    for i in range(16):
        result = mem.body.practice(proc_id)
        if result.get("automatic"):
            break

    # Learn reflexes
    mem.body.learn_reflex("SQL injection", "immediately isolate port and log threat", module="forge_network")
    mem.body.learn_reflex("authentication failure", "increment failure counter, check for brute force", module="forge_network")
    mem.body.learn_reflex("swarm consensus", "record emergent insight as high-significance belief", module="forge_swarm")

    # Fire a reflex
    cprint("\n  [dim]Testing reflexes...[/dim]")
    mem.body.fire_reflex("SQL injection attempt detected on database port")

    # Learn rhythm
    mem.body.learn_rhythm("collaborative_thinking", "seed → explore → question → silence → crystallize", tempo="deliberate")

    # ── Engine 5: Felt Significance ────────────────────────────────────────────
    cprint("\n[bold cyan]ENGINE 5 — FELT SIGNIFICANCE[/bold cyan]")
    cprint("[dim]Surfacing what actually matters — emerged, not assigned...[/dim]\n")

    significant = mem.significance.most_significant(top_k=5, human_id="umang")
    for i, s in enumerate(significant, 1):
        sig = s.get("_felt_significance", 0)
        bar = "█" * int(sig * 20)
        cprint(f"  [white]{i}.[/white] [{bar:<20}] {sig:.3f}  [dim]{s['content'][:55]}[/dim]")

    # ── Full Status ────────────────────────────────────────────────────────────
    cprint("\n[bold]NEUROGENIC STATUS[/bold]")
    display_status(mem)

    # ── Emotional Profile ──────────────────────────────────────────────────────
    cprint("[bold cyan]EMOTIONAL PATHWAYS — FORGE's developed disposition[/bold cyan]")
    profile = mem.emotional.emotional_profile()
    for emotion, data in sorted(profile.items(), key=lambda x: x[1]["pathway_strength"], reverse=True):
        strength = data["pathway_strength"]
        bar = "█" * min(20, int(strength * 4))
        valence_icon = "💚" if data["valence"] > 0.3 else "❤️" if data["valence"] < -0.3 else "💛"
        cprint(f"  {valence_icon} [white]{emotion:<14}[/white] [{bar:<20}] {strength:.2f}  ({data['tendency']})")

    # ── Start API ──────────────────────────────────────────────────────────────
    mem.start_api()
    time.sleep(0.5)

    cprint(f"\n[bold green]✓ FORGE_MEMORY v2.0 fully initialized[/bold green]")
    cprint(f"[dim]  API: http://localhost:{API_PORT}[/dim]")
    cprint(f"[dim]  Graph: {GRAPH_PATH}[/dim]")
    cprint(f"[dim]  Body: {BODY_PATH}[/dim]\n")

    return mem


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    mem = run_demo()
    try:
        cprint("[dim]Press Ctrl+C to exit[/dim]")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        mem.decay.stop()
        cprint("\n[yellow]FORGE_MEMORY v2 shutting down...[/yellow]")
