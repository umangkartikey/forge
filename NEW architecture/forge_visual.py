"""
FORGE Visual Network — forge_visual.py
=======================================
AI analog of the brain's dual visual processing streams.

The brain has two parallel visual pathways:

  VENTRAL STREAM  "What is it?"
    Runs: V1 → V2 → V4 → Inferior Temporal Cortex
    Function: Object identity, face recognition,
              color, form, semantic labeling
    Connects to: hippocampus (memory), temporal cortex (meaning)

  DORSAL STREAM   "Where is it? How do I act on it?"
    Runs: V1 → V2 → V5/MT → Posterior Parietal Cortex
    Function: Spatial location, motion, depth,
              action guidance, threat geometry
    Connects to: prefrontal (action), sensorimotor (movement)

FORGE implementation:

  VentralStream
    ObjectRecognizer    → what objects are present + semantic labels
    FaceRecognizer      → entity matching vs social graph
    SceneClassifier     → environment type + threat context
    ColorSemantic       → color as threat/safety signal

  DorsalStream
    SpatialMapper       → relative positions + distances
    MotionTracker       → velocity + direction vectors
    ThreatGeometry      → exit analysis, flanking, blocking
    ActionAffordances   → what actions this scene permits

  SceneGraph
    Nodes: objects, entities, locations, zones
    Edges: spatial relations (near, blocking, behind, flanking...)
    Temporal edges: was_at, moved_from, approaching

  VisualMemory        → scene recognition + familiarity
  BindingLayer        → merges both streams into unified percept
  VisualSalience      → bottom-up visual attention map
"""

import json
import time
import uuid
import sqlite3
import threading
import math
import re
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

DB_PATH  = "forge_visual.db"
API_PORT = 7789
VERSION  = "1.0.0"

console = Console() if HAS_RICH else None

# ─── Enums ────────────────────────────────────────────────────────────────────

class ObjectCategory(Enum):
    THREAT     = "THREAT"      # weapons, danger objects
    PERSON     = "PERSON"      # human entities
    BARRIER    = "BARRIER"     # walls, doors, obstacles
    EQUIPMENT  = "EQUIPMENT"   # servers, computers, tech
    VEHICLE    = "VEHICLE"     # cars, transport
    ZONE       = "ZONE"        # areas, regions
    UNKNOWN    = "UNKNOWN"

class SpatialRelation(Enum):
    NEAR       = "NEAR"
    FAR        = "FAR"
    BLOCKING   = "BLOCKING"
    BEHIND     = "BEHIND"
    FLANKING   = "FLANKING"
    ABOVE      = "ABOVE"
    BELOW      = "BELOW"
    APPROACHING= "APPROACHING"
    RETREATING = "RETREATING"
    BETWEEN    = "BETWEEN"
    ADJACENT   = "ADJACENT"

class SceneType(Enum):
    INDOOR_SECURE   = "INDOOR_SECURE"
    INDOOR_TECHNICAL= "INDOOR_TECHNICAL"
    INDOOR_PUBLIC   = "INDOOR_PUBLIC"
    OUTDOOR_PUBLIC  = "OUTDOOR_PUBLIC"
    OUTDOOR_PERIMETER="OUTDOOR_PERIMETER"
    LOW_VISIBILITY  = "LOW_VISIBILITY"
    CHOKEPOINT      = "CHOKEPOINT"
    OPEN_SPACE      = "OPEN_SPACE"
    UNKNOWN         = "UNKNOWN"

class ThreatGeometryStatus(Enum):
    CLEAR          = "CLEAR"
    EXIT_BLOCKED   = "EXIT_BLOCKED"
    FLANKED        = "FLANKED"
    CORNERED       = "CORNERED"
    CHOKE_POINT    = "CHOKE_POINT"
    APPROACH_VECTOR= "APPROACH_VECTOR"
    SURROUNDED     = "SURROUNDED"

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class VisualObject:
    id:          str   = field(default_factory=lambda: str(uuid.uuid4())[:6])
    label:       str   = ""
    category:    str   = ObjectCategory.UNKNOWN.value
    confidence:  float = 0.8
    threat_level: int  = 0
    position:    dict  = field(default_factory=lambda: {"x":0.0,"y":0.0,"z":0.0})
    size:        str   = "medium"  # small/medium/large
    color_hint:  str   = ""
    motion:      dict  = field(default_factory=lambda: {"vx":0.0,"vy":0.0,"speed":0.0})
    attributes:  list  = field(default_factory=list)

@dataclass
class SceneGraphNode:
    id:          str   = ""
    label:       str   = ""
    node_type:   str   = ""   # object/entity/zone
    position:    dict  = field(default_factory=lambda: {"x":0.0,"y":0.0})
    connections: list  = field(default_factory=list)
    threat_level:int   = 0
    attributes:  list  = field(default_factory=list)

@dataclass
class SceneGraphEdge:
    from_id:     str   = ""
    to_id:       str   = ""
    relation:    str   = ""
    weight:      float = 1.0
    direction:   str   = "undirected"

@dataclass
class ThreatGeometry:
    status:          str   = ThreatGeometryStatus.CLEAR.value
    exits_blocked:   int   = 0
    exits_clear:     int   = 0
    flanking_threats:int   = 0
    approach_vectors:list  = field(default_factory=list)
    chokepoints:     list  = field(default_factory=list)
    safe_zones:      list  = field(default_factory=list)
    threat_distance: float = 99.0   # distance to nearest threat
    escape_routes:   list  = field(default_factory=list)
    tactical_summary:str   = ""

@dataclass
class VisualPercept:
    """The unified output of both visual streams."""
    id:              str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:       str   = field(default_factory=lambda: datetime.now().isoformat())
    raw_description: str   = ""
    # Ventral stream outputs
    objects:         list  = field(default_factory=list)
    entities:        list  = field(default_factory=list)
    scene_type:      str   = SceneType.UNKNOWN.value
    scene_confidence:float = 0.7
    dominant_color:  str   = ""
    threat_objects:  int   = 0
    # Dorsal stream outputs
    spatial_map:     dict  = field(default_factory=dict)
    motion_vectors:  list  = field(default_factory=list)
    threat_geometry: dict  = field(default_factory=dict)
    affordances:     list  = field(default_factory=list)
    # Scene graph
    graph_nodes:     int   = 0
    graph_edges:     int   = 0
    # Binding
    visual_threat_score: float = 0.0
    novelty_score:       float = 0.5
    familiarity:         float = 0.5
    semantic_summary:    str   = ""
    action_recommendations: list = field(default_factory=list)

# ─── Database ─────────────────────────────────────────────────────────────────

class VisualDB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init()

    def _init(self):
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS visual_percepts (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    raw_description TEXT, scene_type TEXT,
                    threat_objects INTEGER, visual_threat_score REAL,
                    novelty_score REAL, familiarity REAL,
                    semantic_summary TEXT, graph_nodes INTEGER,
                    graph_edges INTEGER
                );
                CREATE TABLE IF NOT EXISTS scene_memory (
                    fingerprint TEXT PRIMARY KEY, scene_type TEXT,
                    last_seen TEXT, times_seen INTEGER,
                    avg_threat REAL, description TEXT
                );
                CREATE TABLE IF NOT EXISTS spatial_events (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    entity TEXT, relation TEXT, target TEXT,
                    percept_id TEXT, threat_level INTEGER
                );
            """)
            self.conn.commit()

    def save_percept(self, p: VisualPercept):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO visual_percepts VALUES
                (?,?,?,?,?,?,?,?,?,?,?)
            """, (p.id, p.timestamp, p.raw_description[:200],
                  p.scene_type, p.threat_objects, p.visual_threat_score,
                  p.novelty_score, p.familiarity, p.semantic_summary[:200],
                  p.graph_nodes, p.graph_edges))
            self.conn.commit()

    def update_scene_memory(self, fingerprint: str, scene_type: str,
                             threat: float, description: str):
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM scene_memory WHERE fingerprint=?",
                (fingerprint,)
            ).fetchone()
            if row:
                self.conn.execute("""
                    UPDATE scene_memory SET last_seen=?, times_seen=?,
                    avg_threat=? WHERE fingerprint=?
                """, (datetime.now().isoformat(), row[3]+1,
                      round((row[4]*row[3] + threat)/(row[3]+1), 3),
                      fingerprint))
            else:
                self.conn.execute("""
                    INSERT INTO scene_memory VALUES (?,?,?,?,?,?)
                """, (fingerprint, scene_type, datetime.now().isoformat(),
                      1, threat, description[:100]))
            self.conn.commit()

    def get_scene_familiarity(self, fingerprint: str) -> float:
        with self.lock:
            row = self.conn.execute(
                "SELECT times_seen, avg_threat FROM scene_memory WHERE fingerprint=?",
                (fingerprint,)
            ).fetchone()
            if not row: return 0.0
            # Familiarity increases with repeated exposure
            return round(min(1.0, row[0] * 0.15), 3)

    def get_recent_percepts(self, limit=20):
        with self.lock:
            return self.conn.execute("""
                SELECT id, timestamp, scene_type, threat_objects,
                       visual_threat_score, semantic_summary
                FROM visual_percepts ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()


# ─── Object Lexicon ───────────────────────────────────────────────────────────

class ObjectLexicon:
    """
    Maps words/phrases to VisualObject instances.
    The visual system's vocabulary.
    """

    THREAT_OBJECTS = {
        "weapon": {"threat":4,"category":ObjectCategory.THREAT,"size":"medium","attrs":["lethal","concealed"]},
        "gun":    {"threat":4,"category":ObjectCategory.THREAT,"size":"small", "attrs":["lethal","ranged"]},
        "knife":  {"threat":3,"category":ObjectCategory.THREAT,"size":"small", "attrs":["lethal","close_range"]},
        "explosive":{"threat":4,"category":ObjectCategory.THREAT,"size":"medium","attrs":["lethal","area_effect"]},
        "fire":   {"threat":3,"category":ObjectCategory.THREAT,"size":"large","attrs":["hazard","spreading"]},
        "blade":  {"threat":3,"category":ObjectCategory.THREAT,"size":"small","attrs":["lethal"]},
        "device": {"threat":2,"category":ObjectCategory.THREAT,"size":"small","attrs":["suspicious","unknown"]},
    }

    PERSON_OBJECTS = {
        "person":     {"threat":0,"category":ObjectCategory.PERSON,"size":"medium","attrs":[]},
        "figure":     {"threat":1,"category":ObjectCategory.PERSON,"size":"medium","attrs":["unidentified"]},
        "technician": {"threat":0,"category":ObjectCategory.PERSON,"size":"medium","attrs":["authorized","uniform"]},
        "guard":      {"threat":0,"category":ObjectCategory.PERSON,"size":"medium","attrs":["authorized","security"]},
        "intruder":   {"threat":3,"category":ObjectCategory.PERSON,"size":"medium","attrs":["unauthorized","hostile"]},
        "crowd":      {"threat":1,"category":ObjectCategory.PERSON,"size":"large","attrs":["multiple","unpredictable"]},
        "shadow":     {"threat":2,"category":ObjectCategory.PERSON,"size":"medium","attrs":["concealed","unidentified"]},
    }

    EQUIPMENT_OBJECTS = {
        "server":   {"threat":0,"category":ObjectCategory.EQUIPMENT,"size":"large","attrs":["critical_asset","target"]},
        "computer": {"threat":0,"category":ObjectCategory.EQUIPMENT,"size":"medium","attrs":["asset"]},
        "rack":     {"threat":0,"category":ObjectCategory.EQUIPMENT,"size":"large","attrs":["critical_asset"]},
        "camera":   {"threat":0,"category":ObjectCategory.EQUIPMENT,"size":"small","attrs":["surveillance"]},
        "terminal": {"threat":0,"category":ObjectCategory.EQUIPMENT,"size":"medium","attrs":["access_point"]},
        "cable":    {"threat":0,"category":ObjectCategory.EQUIPMENT,"size":"small","attrs":["infrastructure"]},
    }

    BARRIER_OBJECTS = {
        "door":   {"threat":0,"category":ObjectCategory.BARRIER,"size":"medium","attrs":["access_point","exit"]},
        "gate":   {"threat":0,"category":ObjectCategory.BARRIER,"size":"large","attrs":["access_point","exit"]},
        "wall":   {"threat":0,"category":ObjectCategory.BARRIER,"size":"large","attrs":["barrier"]},
        "fence":  {"threat":0,"category":ObjectCategory.BARRIER,"size":"large","attrs":["perimeter"]},
        "window": {"threat":0,"category":ObjectCategory.BARRIER,"size":"medium","attrs":["opening","vulnerability"]},
        "corridor":{"threat":0,"category":ObjectCategory.BARRIER,"size":"large","attrs":["chokepoint","path"]},
        "entrance":{"threat":0,"category":ObjectCategory.BARRIER,"size":"medium","attrs":["access_point","exit"]},
    }

    COLOR_THREAT = {
        "dark": 1, "shadow": 1, "black": 0,
        "red": 1, "blood": 3, "fire": 2,
        "bright": 0, "white": 0, "normal": 0,
    }

    def __init__(self):
        self.all_objects = {
            **self.THREAT_OBJECTS,
            **self.PERSON_OBJECTS,
            **self.EQUIPMENT_OBJECTS,
            **self.BARRIER_OBJECTS,
        }

    def parse(self, text: str) -> list[VisualObject]:
        """Parse a text description into VisualObject instances."""
        text_lower = text.lower()
        found      = []
        positions  = self._assign_positions(text_lower)

        for word, spec in self.all_objects.items():
            if word in text_lower:
                pos_idx = len(found)
                obj = VisualObject(
                    label    = word,
                    category = spec["category"].value,
                    confidence = 0.85,
                    threat_level = spec["threat"],
                    position = positions[pos_idx % len(positions)],
                    size     = spec["size"],
                    attributes = list(spec["attrs"]),
                )
                # Color hints
                for color, _ in self.COLOR_THREAT.items():
                    if color in text_lower:
                        obj.color_hint = color
                        break

                # Motion hints
                if any(w in text_lower for w in ["moving","running","approaching","coming"]):
                    obj.motion = {"vx": 1.0, "vy": 0.5, "speed": 1.5}
                elif any(w in text_lower for w in ["retreating","fleeing","leaving"]):
                    obj.motion = {"vx":-1.0, "vy":-0.5, "speed": 1.2}

                found.append(obj)

        return found

    def _assign_positions(self, text: str) -> list[dict]:
        """Estimate positions from spatial language."""
        positions = []
        # Parse spatial clues
        zones = {
            "left":   {"x":-3.0,"y":0.0,"z":0.0},
            "right":  {"x": 3.0,"y":0.0,"z":0.0},
            "front":  {"x": 0.0,"y":-3.0,"z":0.0},
            "behind": {"x": 0.0,"y": 3.0,"z":0.0},
            "near":   {"x": 1.0,"y":1.0,"z":0.0},
            "far":    {"x": 5.0,"y":5.0,"z":0.0},
            "center": {"x": 0.0,"y":0.0,"z":0.0},
            "corner": {"x": 4.0,"y":4.0,"z":0.0},
            "door":   {"x": 2.0,"y":0.0,"z":0.0},
            "entrance":{"x":2.0,"y":0.0,"z":0.0},
        }
        for zone, pos in zones.items():
            if zone in text:
                positions.append(pos)

        # Default grid positions
        defaults = [
            {"x":0.0,"y":0.0,"z":0.0}, {"x":2.0,"y":1.0,"z":0.0},
            {"x":-2.0,"y":1.0,"z":0.0}, {"x":0.0,"y":3.0,"z":0.0},
            {"x":3.0,"y":3.0,"z":0.0}, {"x":-3.0,"y":2.0,"z":0.0},
        ]
        positions.extend(defaults)
        return positions if positions else defaults


# ─── Ventral Stream ───────────────────────────────────────────────────────────

class VentralStream:
    """
    The "What is it?" pathway.
    Object recognition, entity identification, scene classification,
    semantic labeling.
    """

    SCENE_CLASSIFIERS = {
        SceneType.INDOOR_TECHNICAL: [
            "server","rack","computer","terminal","cable","network","equipment"
        ],
        SceneType.INDOOR_SECURE: [
            "vault","safe","lock","badge","security","restricted","clearance"
        ],
        SceneType.INDOOR_PUBLIC: [
            "office","desk","chair","hallway","lobby","reception","corridor"
        ],
        SceneType.OUTDOOR_PUBLIC: [
            "street","road","parking","outdoor","building","entrance","plaza"
        ],
        SceneType.OUTDOOR_PERIMETER: [
            "fence","gate","perimeter","wall","boundary","patrol","guard"
        ],
        SceneType.LOW_VISIBILITY: [
            "dark","shadow","night","dim","low","poor","visibility","obscured"
        ],
        SceneType.CHOKEPOINT: [
            "corridor","narrow","tunnel","bottleneck","single","choke"
        ],
        SceneType.OPEN_SPACE: [
            "open","wide","large","field","expanse","room","area"
        ],
    }

    def __init__(self, lexicon: ObjectLexicon):
        self.lexicon = lexicon

    def process(self, description: str) -> dict:
        """Process text description through ventral stream."""
        text_lower = description.lower()

        # Object recognition
        objects    = self.lexicon.parse(description)
        threats    = [o for o in objects if o.category == ObjectCategory.THREAT.value]
        persons    = [o for o in objects if o.category == ObjectCategory.PERSON.value]
        equipment  = [o for o in objects if o.category == ObjectCategory.EQUIPMENT.value]
        barriers   = [o for o in objects if o.category == ObjectCategory.BARRIER.value]

        # Scene classification
        scene_type, confidence = self._classify_scene(text_lower)

        # Entity recognition (persons with identity hints)
        entities = self._recognize_entities(text_lower, persons)

        # Color semantics
        dominant_color = self._extract_color(text_lower)

        # Semantic summary
        summary = self._summarize(objects, scene_type, threats, persons)

        return {
            "objects":       objects,
            "threats":       threats,
            "persons":       persons,
            "equipment":     equipment,
            "barriers":      barriers,
            "entities":      entities,
            "scene_type":    scene_type.value,
            "scene_confidence": confidence,
            "dominant_color":dominant_color,
            "threat_count":  len(threats),
            "person_count":  len(persons),
            "semantic_summary": summary,
        }

    def _classify_scene(self, text: str) -> tuple[SceneType, float]:
        scores = {}
        for scene, keywords in self.SCENE_CLASSIFIERS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[scene] = score

        if not scores:
            return SceneType.UNKNOWN, 0.5

        best  = max(scores, key=scores.get)
        conf  = min(0.95, 0.5 + scores[best] * 0.12)
        return best, round(conf, 2)

    def _recognize_entities(self, text: str,
                             persons: list[VisualObject]) -> list[dict]:
        entities = []
        identity_hints = {
            "uniform": "authorized_personnel",
            "badge":   "authorized_personnel",
            "technician": "technician",
            "guard":   "security_guard",
            "shadow":  "unknown_concealed",
            "masked":  "unknown_masked",
            "hooded":  "unknown_hooded",
        }
        for hint, identity in identity_hints.items():
            if hint in text:
                entities.append({
                    "identity":    identity,
                    "confidence":  0.7,
                    "threat_hint": "low" if "authorized" in identity else "high"
                })
        return entities[:3]

    def _extract_color(self, text: str) -> str:
        colors = ["red","blue","green","black","white","gray","dark","bright","orange"]
        for c in colors:
            if c in text: return c
        return "unspecified"

    def _summarize(self, objects: list, scene: SceneType,
                   threats: list, persons: list) -> str:
        parts = [f"{scene.value} scene"]
        if threats:
            parts.append(f"{len(threats)} threat object(s): {', '.join(o.label for o in threats[:2])}")
        if persons:
            parts.append(f"{len(persons)} person(s) present")
        if not threats and not persons:
            parts.append("no immediate threats detected")
        return ". ".join(parts)


# ─── Dorsal Stream ────────────────────────────────────────────────────────────

class DorsalStream:
    """
    The "Where is it? How do I act on it?" pathway.
    Spatial mapping, motion tracking, threat geometry,
    action affordances.
    """

    def process(self, objects: list[VisualObject],
                scene_type: str, description: str) -> dict:
        """Process object list through dorsal stream."""

        spatial_map    = self._build_spatial_map(objects)
        motion_vectors = self._extract_motion(objects)
        threat_geo     = self._analyze_threat_geometry(objects, description, scene_type)
        affordances    = self._compute_affordances(objects, scene_type, threat_geo)

        return {
            "spatial_map":     spatial_map,
            "motion_vectors":  motion_vectors,
            "threat_geometry": threat_geo,
            "affordances":     affordances,
        }

    def _build_spatial_map(self, objects: list[VisualObject]) -> dict:
        """Build a 2D spatial map of all detected objects."""
        nodes   = {}
        edges   = []
        for obj in objects:
            nodes[obj.id] = {
                "label":    obj.label,
                "category": obj.category,
                "position": obj.position,
                "threat":   obj.threat_level,
            }

        # Compute pairwise distances and relations
        obj_list = list(objects)
        for i, a in enumerate(obj_list):
            for b in obj_list[i+1:]:
                dist = self._distance(a.position, b.position)
                rel  = self._spatial_relation(a, b, dist)
                if rel:
                    edges.append({
                        "from":     a.id,
                        "to":       b.id,
                        "relation": rel,
                        "distance": round(dist, 2)
                    })

        return {
            "nodes":     nodes,
            "edges":     edges,
            "bounds":    self._compute_bounds(objects),
            "centroid":  self._compute_centroid(objects),
        }

    def _distance(self, p1: dict, p2: dict) -> float:
        return math.sqrt(
            (p1["x"]-p2["x"])**2 +
            (p1["y"]-p2["y"])**2
        )

    def _spatial_relation(self, a: VisualObject,
                          b: VisualObject, dist: float) -> Optional[str]:
        if dist < 1.5:   return SpatialRelation.NEAR.value
        if dist < 3.0:   return SpatialRelation.ADJACENT.value
        if dist > 6.0:   return SpatialRelation.FAR.value

        # Blocking: person + barrier close together
        if (a.category == ObjectCategory.PERSON.value and
                b.category == ObjectCategory.BARRIER.value and dist < 2.5):
            return SpatialRelation.BLOCKING.value

        # Flanking: threats on both sides
        if (a.category == ObjectCategory.THREAT.value and
                abs(a.position["x"] - b.position["x"]) > 3.0):
            return SpatialRelation.FLANKING.value

        return None

    def _compute_bounds(self, objects: list) -> dict:
        if not objects: return {"min_x":0,"max_x":0,"min_y":0,"max_y":0}
        xs = [o.position["x"] for o in objects]
        ys = [o.position["y"] for o in objects]
        return {"min_x":min(xs),"max_x":max(xs),"min_y":min(ys),"max_y":max(ys)}

    def _compute_centroid(self, objects: list) -> dict:
        if not objects: return {"x":0,"y":0}
        return {
            "x": round(sum(o.position["x"] for o in objects)/len(objects), 2),
            "y": round(sum(o.position["y"] for o in objects)/len(objects), 2)
        }

    def _extract_motion(self, objects: list[VisualObject]) -> list[dict]:
        moving = []
        for obj in objects:
            if obj.motion.get("speed", 0) > 0.1:
                moving.append({
                    "object":    obj.label,
                    "speed":     obj.motion["speed"],
                    "direction": self._direction_label(obj.motion),
                    "threat":    obj.threat_level
                })
        return moving

    def _direction_label(self, motion: dict) -> str:
        vx, vy = motion.get("vx",0), motion.get("vy",0)
        if abs(vx) < 0.1 and abs(vy) < 0.1: return "stationary"
        if vy < -0.3: return "approaching"
        if vy >  0.3: return "retreating"
        if vx >  0.3: return "moving_right"
        if vx < -0.3: return "moving_left"
        return "moving"

    def _analyze_threat_geometry(self, objects: list[VisualObject],
                                  description: str,
                                  scene_type: str) -> dict:
        text_lower = description.lower()
        threats    = [o for o in objects if o.category == ObjectCategory.THREAT.value]
        barriers   = [o for o in objects if o.category == ObjectCategory.BARRIER.value]
        persons    = [o for o in objects if o.category == ObjectCategory.PERSON.value]

        # Exit analysis
        exit_keywords  = ["door","gate","exit","entrance","window","opening"]
        exits_present  = sum(1 for kw in exit_keywords if kw in text_lower)
        blocked_kws    = ["blocking","blocked","closing","locked"]
        exits_blocked  = sum(1 for kw in blocked_kws if kw in text_lower)
        exits_clear    = max(0, exits_present - exits_blocked)

        # Flanking detection
        flanking = len(threats) >= 2 or "surrounded" in text_lower or "both sides" in text_lower

        # Approach vectors
        approach_vectors = []
        if any(w in text_lower for w in ["approaching","moving toward","coming"]):
            threat_approach = [o for o in threats if o.motion.get("speed",0) > 0]
            for t in threat_approach:
                approach_vectors.append({
                    "object":   t.label,
                    "speed":    t.motion.get("speed",1.0),
                    "distance": t.position.get("y",3.0)
                })

        # Chokepoints
        chokepoints = []
        if any(w in text_lower for w in ["corridor","narrow","hallway","tunnel"]):
            chokepoints.append("corridor")

        # Determine overall geometry status
        if "surrounded" in text_lower or (flanking and exits_blocked > 0):
            geo_status = ThreatGeometryStatus.SURROUNDED
        elif exits_blocked > 0 and exits_clear == 0:
            geo_status = ThreatGeometryStatus.EXIT_BLOCKED
        elif flanking:
            geo_status = ThreatGeometryStatus.FLANKED
        elif chokepoints:
            geo_status = ThreatGeometryStatus.CHOKE_POINT
        elif approach_vectors:
            geo_status = ThreatGeometryStatus.APPROACH_VECTOR
        else:
            geo_status = ThreatGeometryStatus.CLEAR

        # Nearest threat distance
        min_threat_dist = 99.0
        for t in threats:
            d = math.sqrt(t.position["x"]**2 + t.position["y"]**2)
            min_threat_dist = min(min_threat_dist, d)

        # Safe zones
        safe_zones = []
        if exits_clear > 0: safe_zones.append("exit_available")
        if scene_type == SceneType.INDOOR_SECURE.value: safe_zones.append("secure_perimeter")

        # Escape routes
        escape_routes = []
        if exits_clear > 0:
            escape_routes.append(f"{exits_clear} exit(s) available")
        if "window" in text_lower:
            escape_routes.append("window egress possible")

        # Tactical summary
        tactical = self._tactical_summary(geo_status, threats, exits_blocked,
                                           exits_clear, approach_vectors, flanking)

        return {
            "status":           geo_status.value,
            "exits_blocked":    exits_blocked,
            "exits_clear":      exits_clear,
            "flanking_threats": int(flanking),
            "approach_vectors": approach_vectors,
            "chokepoints":      chokepoints,
            "safe_zones":       safe_zones,
            "threat_distance":  round(min_threat_dist, 2),
            "escape_routes":    escape_routes,
            "tactical_summary": tactical,
        }

    def _tactical_summary(self, status: ThreatGeometryStatus,
                           threats: list, exits_blocked: int,
                           exits_clear: int, approaches: list,
                           flanking: bool) -> str:
        if status == ThreatGeometryStatus.SURROUNDED:
            return "⚠ SURROUNDED — all exits compromised. Emergency escalation required."
        if status == ThreatGeometryStatus.EXIT_BLOCKED:
            return f"⚠ EXIT BLOCKED — {exits_blocked} exit(s) compromised. Seek alternative egress."
        if status == ThreatGeometryStatus.FLANKED:
            return "⚡ FLANKED — multiple threat vectors. Consolidate defensive position."
        if status == ThreatGeometryStatus.CHOKE_POINT:
            return "ℹ CHOKEPOINT — bottleneck geometry. Advantage to defender."
        if status == ThreatGeometryStatus.APPROACH_VECTOR:
            speeds = [a["speed"] for a in approaches]
            return f"⬆ APPROACH — {len(approaches)} inbound vector(s). Intercept or withdraw."
        return f"✓ CLEAR — {exits_clear} exit(s) available. Position secure."

    def _compute_affordances(self, objects: list[VisualObject],
                              scene_type: str,
                              threat_geo: dict) -> list[str]:
        """What actions does this scene permit?"""
        affordances = []
        status = threat_geo.get("status","CLEAR")

        if threat_geo.get("exits_clear", 0) > 0:
            affordances.append("WITHDRAW_VIA_EXIT")
        if threat_geo.get("chokepoints"):
            affordances.append("DEFEND_CHOKEPOINT")
        if any(o.category == ObjectCategory.EQUIPMENT.value for o in objects):
            affordances.append("PROTECT_EQUIPMENT")
        if status in ["FLANKED","SURROUNDED"]:
            affordances.append("EMERGENCY_ESCALATE")
        if status == "CLEAR":
            affordances.append("ADVANCE_SAFELY")
        if any(o.category == ObjectCategory.PERSON.value for o in objects):
            affordances.append("ENGAGE_ENTITY")
        if any(o.label == "camera" for o in objects):
            affordances.append("ACTIVATE_SURVEILLANCE")
        if threat_geo.get("threat_distance", 99) < 2.0:
            affordances.append("IMMEDIATE_DEFENSIVE_ACTION")

        return list(dict.fromkeys(affordances))[:6]


# ─── Scene Graph ──────────────────────────────────────────────────────────────

class SceneGraph:
    """
    Unified spatial representation.
    Nodes = objects, entities, zones.
    Edges = spatial relations.
    Enables graph-based reasoning about the scene.
    """

    def __init__(self):
        self.nodes: dict[str, SceneGraphNode] = {}
        self.edges: list[SceneGraphEdge]      = []

    def build(self, ventral: dict, dorsal: dict) -> tuple[int, int]:
        self.nodes.clear()
        self.edges.clear()

        # Add object nodes from ventral
        for obj in ventral["objects"]:
            node = SceneGraphNode(
                id       = obj.id,
                label    = obj.label,
                node_type= "object",
                position = {"x":obj.position["x"],"y":obj.position["y"]},
                threat_level = obj.threat_level,
                attributes   = obj.attributes,
            )
            self.nodes[obj.id] = node

        # Add scene node
        scene_id = "scene_root"
        self.nodes[scene_id] = SceneGraphNode(
            id        = scene_id,
            label     = ventral["scene_type"],
            node_type = "zone",
            attributes = [ventral["scene_type"]]
        )

        # Add spatial edges from dorsal
        spatial_map = dorsal.get("spatial_map", {})
        for edge_data in spatial_map.get("edges", []):
            self.edges.append(SceneGraphEdge(
                from_id  = edge_data["from"],
                to_id    = edge_data["to"],
                relation = edge_data["relation"],
                weight   = 1.0
            ))

        # Connect all objects to scene root
        for nid in self.nodes:
            if nid != scene_id:
                self.edges.append(SceneGraphEdge(
                    from_id  = nid,
                    to_id    = scene_id,
                    relation = "in_scene",
                    weight   = 0.5
                ))

        return len(self.nodes), len(self.edges)

    def query_threats(self) -> list[dict]:
        """Find all threat nodes and their relations."""
        results = []
        for node in self.nodes.values():
            if node.threat_level > 0:
                connected = [
                    {"to": e.to_id, "relation": e.relation}
                    for e in self.edges if e.from_id == node.id
                ]
                results.append({
                    "threat_object": node.label,
                    "threat_level":  node.threat_level,
                    "position":      node.position,
                    "connected_to":  connected[:3]
                })
        return sorted(results, key=lambda x: x["threat_level"], reverse=True)

    def find_blocking_entities(self) -> list[str]:
        """Find entities blocking exits."""
        return [
            e.from_id for e in self.edges
            if e.relation == SpatialRelation.BLOCKING.value
        ]


# ─── Visual Memory ────────────────────────────────────────────────────────────

class VisualMemory:
    """
    Recognizes previously seen scenes.
    Builds familiarity over repeated exposure.
    Flags genuinely novel visual patterns.
    """

    def __init__(self, db: VisualDB):
        self.db       = db
        self.seen:    dict[str, int] = {}
        self.capacity = 500

    def fingerprint(self, objects: list[VisualObject],
                    scene_type: str) -> str:
        """Create a fingerprint of a scene."""
        sorted_labels = sorted(o.label for o in objects)
        raw = f"{scene_type}:{','.join(sorted_labels[:5])}"
        import hashlib
        return hashlib.md5(raw.encode()).hexdigest()[:10]

    def check(self, objects: list[VisualObject],
              scene_type: str, threat: float) -> tuple[float, float]:
        """Returns (familiarity, novelty)."""
        fp   = self.fingerprint(objects, scene_type)
        fam  = self.db.get_scene_familiarity(fp)
        desc = f"{scene_type}: {', '.join(o.label for o in objects[:3])}"
        self.db.update_scene_memory(fp, scene_type, threat, desc)
        novelty = round(max(0.0, 1.0 - fam), 3)
        return fam, novelty


# ─── Visual Salience ──────────────────────────────────────────────────────────

class VisualSalience:
    """
    Bottom-up visual attention — what pops out automatically.
    Bright colors, motion, faces, threat objects grab attention.
    """

    def compute(self, objects: list[VisualObject],
                motion_vectors: list[dict],
                threat_geo: dict) -> dict:

        attention_map = {}

        for obj in objects:
            salience = 0.3  # base

            # Threat objects are visually salient
            if obj.category == ObjectCategory.THREAT.value:
                salience += obj.threat_level * 0.15

            # Faces/persons grab attention
            if obj.category == ObjectCategory.PERSON.value:
                salience += 0.2

            # Motion is very salient
            if obj.motion.get("speed",0) > 0.5:
                salience += 0.3

            # Unusual colors
            if obj.color_hint in ["red","blood","fire"]:
                salience += 0.2

            attention_map[obj.label] = round(min(1.0, salience), 3)

        # Overall scene salience score
        if not attention_map:
            return {"scene_salience": 0.2, "hotspots": [], "attention_map": {}}

        scene_sal = sum(attention_map.values()) / len(attention_map)
        hotspots  = sorted(attention_map.items(), key=lambda x: x[1], reverse=True)[:3]

        # Threat geometry amplifies
        if threat_geo.get("status") not in ["CLEAR"]:
            scene_sal = min(1.0, scene_sal * 1.3)

        return {
            "scene_salience": round(scene_sal, 3),
            "hotspots":       [{"object":k,"salience":v} for k,v in hotspots],
            "attention_map":  attention_map,
        }


# ─── Binding Layer ────────────────────────────────────────────────────────────

class VisualBindingLayer:
    """
    Merges ventral + dorsal streams into unified VisualPercept.
    This is where "what" meets "where" — the full visual experience.
    """

    def bind(self, ventral: dict, dorsal: dict,
             graph_stats: tuple, memory: tuple,
             salience: dict, description: str) -> VisualPercept:

        objects     = ventral["objects"]
        threat_geo  = dorsal["threat_geometry"]
        fam, novelty= memory

        # Visual threat score
        threat_score = 0.0
        for obj in objects:
            if obj.category == ObjectCategory.THREAT.value:
                threat_score += obj.threat_level * 0.25
        if threat_geo["status"] == ThreatGeometryStatus.SURROUNDED.value:
            threat_score += 0.4
        elif threat_geo["status"] == ThreatGeometryStatus.EXIT_BLOCKED.value:
            threat_score += 0.3
        elif threat_geo["status"] == ThreatGeometryStatus.FLANKED.value:
            threat_score += 0.25
        threat_score = round(min(1.0, threat_score), 3)

        # Action recommendations from threat geometry
        recs = list(dorsal["affordances"])
        if threat_score > 0.6:
            recs.insert(0, "ESCALATE_IMMEDIATELY")
        if novelty > 0.8:
            recs.append("INVESTIGATE_NOVEL_SCENE")

        percept = VisualPercept(
            raw_description      = description,
            objects              = objects,
            entities             = ventral["entities"],
            scene_type           = ventral["scene_type"],
            scene_confidence     = ventral["scene_confidence"],
            dominant_color       = ventral["dominant_color"],
            threat_objects       = ventral["threat_count"],
            spatial_map          = dorsal["spatial_map"],
            motion_vectors       = dorsal["motion_vectors"],
            threat_geometry      = threat_geo,
            affordances          = dorsal["affordances"],
            graph_nodes          = graph_stats[0],
            graph_edges          = graph_stats[1],
            visual_threat_score  = threat_score,
            novelty_score        = novelty,
            familiarity          = fam,
            semantic_summary     = ventral["semantic_summary"],
            action_recommendations = recs[:5],
        )
        return percept


# ─── FORGE Visual Network ─────────────────────────────────────────────────────

class ForgeVisualNetwork:
    def __init__(self):
        self.db        = VisualDB()
        self.lexicon   = ObjectLexicon()
        self.ventral   = VentralStream(self.lexicon)
        self.dorsal    = DorsalStream()
        self.graph     = SceneGraph()
        self.memory    = VisualMemory(self.db)
        self.salience  = VisualSalience()
        self.binding   = VisualBindingLayer()
        self.cycle     = 0
        self.percepts: deque = deque(maxlen=200)

    def perceive(self, description: str,
                 entity_name: str = "unknown") -> dict:
        """
        Full visual processing pipeline.
        Ventral → Dorsal → Scene Graph → Memory → Salience → Bind
        """
        t0         = time.time()
        self.cycle += 1

        # 1. Ventral stream — what is it?
        vent = self.ventral.process(description)

        # 2. Dorsal stream — where is it?
        dors = self.dorsal.process(
            vent["objects"], vent["scene_type"], description
        )

        # 3. Scene graph
        n_nodes, n_edges = self.graph.build(vent, dors)

        # 4. Visual memory — seen before?
        threat_val = vent["threat_count"] * 0.3
        fam, novelty = self.memory.check(vent["objects"], vent["scene_type"], threat_val)

        # 5. Visual salience
        sal = self.salience.compute(
            vent["objects"], dors["motion_vectors"], dors["threat_geometry"]
        )

        # 6. Binding — merge everything
        percept = self.binding.bind(
            vent, dors, (n_nodes, n_edges), (fam, novelty), sal, description
        )

        # Save
        self.db.save_percept(percept)
        self.percepts.append(percept)

        duration = (time.time()-t0)*1000

        return {
            "cycle":         self.cycle,
            "duration_ms":   round(duration, 1),
            # Ventral
            "scene_type":    percept.scene_type,
            "scene_confidence": percept.scene_confidence,
            "objects":       [{"label":o.label,"category":o.category,
                               "threat":o.threat_level,"attrs":o.attributes[:2]}
                              for o in percept.objects],
            "entities":      percept.entities,
            "threat_objects":percept.threat_objects,
            "semantic_summary": percept.semantic_summary,
            # Dorsal
            "threat_geometry":{
                "status":       percept.threat_geometry["status"],
                "exits_clear":  percept.threat_geometry["exits_clear"],
                "exits_blocked":percept.threat_geometry["exits_blocked"],
                "flanking":     percept.threat_geometry["flanking_threats"],
                "threat_dist":  percept.threat_geometry["threat_distance"],
                "tactical":     percept.threat_geometry["tactical_summary"],
                "escape_routes":percept.threat_geometry["escape_routes"],
            },
            "motion_vectors":percept.motion_vectors,
            "affordances":   percept.affordances,
            # Graph
            "graph_nodes":   percept.graph_nodes,
            "graph_edges":   percept.graph_edges,
            "threat_graph":  self.graph.query_threats(),
            # Memory + salience
            "familiarity":   percept.familiarity,
            "novelty":       percept.novelty_score,
            "visual_salience":sal["scene_salience"],
            "hotspots":      sal["hotspots"],
            # Binding
            "visual_threat_score": percept.visual_threat_score,
            "action_recommendations": percept.action_recommendations,
        }

    def get_status(self) -> dict:
        return {
            "version":       VERSION,
            "cycle":         self.cycle,
            "percepts_stored":len(self.percepts),
            "scene_memory":  len(self.memory.seen),
        }


# ─── Rich UI ──────────────────────────────────────────────────────────────────

def render_percept(result: dict, description: str, idx: int):
    if not HAS_RICH: return

    vts    = result["visual_threat_score"]
    tc     = "bright_red" if vts > 0.6 else "red" if vts > 0.3 else "yellow" if vts > 0.1 else "green"
    geo    = result["threat_geometry"]
    g_color= {"CLEAR":"green","EXIT_BLOCKED":"red","FLANKED":"red",
              "SURROUNDED":"bright_red","CHOKE_POINT":"yellow",
              "APPROACH_VECTOR":"orange3"}.get(geo["status"],"white")

    console.print(Rule(
        f"[bold cyan]⬡ FORGE VISUAL[/bold cyan]  "
        f"[dim]#{idx}[/dim]  "
        f"[cyan]{result['scene_type']}[/cyan]  "
        f"[{tc}]VTS={vts:.2f}[/{tc}]  "
        f"[{g_color}]{geo['status']}[/{g_color}]"
    ))

    # Ventral panel
    vent_lines = [
        f"[bold]Scene:[/bold]   [cyan]{result['scene_type']}[/cyan] ({result['scene_confidence']:.0%})",
        f"[bold]Summary:[/bold] [dim]{result['semantic_summary'][:60]}[/dim]",
        f"[bold]Objects:[/bold] {len(result['objects'])} detected",
    ]
    obj_color_map = {
        "THREAT": "bright_red", "PERSON": "cyan",
        "EQUIPMENT": "blue", "BARRIER": "dim", "UNKNOWN": "dim"
    }
    for obj in result["objects"][:5]:
        oc = obj_color_map.get(obj["category"],"white")
        vent_lines.append(
            f"  [{oc}]{obj['label']}[/{oc}]"
            f"[dim] ({obj['category']}) T={obj['threat']}[/dim]"
        )
    if result.get("motion_vectors"):
        for mv in result["motion_vectors"][:2]:
            vent_lines.append(
                f"  [yellow]↗ {mv['object']}[/yellow] {mv['direction']} speed={mv['speed']:.1f}"
            )

    # Dorsal panel
    dors_lines = [
        f"[bold]Geometry:[/bold]  [{g_color}]{geo['status']}[/{g_color}]",
        f"[bold]Exits:[/bold]     [green]{geo['exits_clear']} clear[/green] / [red]{geo['exits_blocked']} blocked[/red]",
        f"[bold]Flanking:[/bold]  {'[red]YES[/red]' if geo['flanking'] else '[green]NO[/green]'}",
        f"[bold]Threat Δ:[/bold]  {geo['threat_dist']:.1f}m",
        f"",
        f"[dim]{geo['tactical'][:65]}[/dim]",
    ]
    if result.get("affordances"):
        dors_lines.append(f"\n[bold]Affordances:[/bold]")
        for a in result["affordances"][:3]:
            dors_lines.append(f"  [cyan]→ {a}[/cyan]")

    console.print(Columns([
        Panel("\n".join(vent_lines), title="[bold]👁 VENTRAL  What is it?[/bold]",  border_style="cyan"),
        Panel("\n".join(dors_lines), title="[bold]🗺 DORSAL   Where is it?[/bold]", border_style=g_color)
    ]))

    # Scene graph
    if result.get("threat_graph"):
        tg_lines = []
        for thr in result["threat_graph"][:3]:
            tg_lines.append(
                f"[red]{thr['threat_object']}[/red] (T={thr['threat_level']}) "
                f"@ ({thr['position']['x']:.1f},{thr['position']['y']:.1f})"
            )
            for conn in thr["connected_to"][:2]:
                tg_lines.append(f"  [dim]→ {conn['relation']} → {conn['to']}[/dim]")
        if tg_lines:
            console.print(Panel(
                "\n".join(tg_lines),
                title="[bold]⬡ SCENE GRAPH — Threat Nodes[/bold]",
                border_style="red"
            ))

    # Memory + actions
    fam_bar = "█" * int(result["familiarity"]*10) + "░" * (10-int(result["familiarity"]*10))
    nov_bar = "█" * int(result["novelty"]*10)      + "░" * (10-int(result["novelty"]*10))
    recs    = "  ".join(f"[cyan]{r}[/cyan]" for r in result["action_recommendations"][:3])
    console.print(
        f"  [dim]Familiarity: [{fam_bar}] {result['familiarity']:.2f}  "
        f"Novelty: [{nov_bar}] {result['novelty']:.2f}  "
        f"Salience: {result['visual_salience']:.2f}[/dim]\n"
        f"  Recommendations: {recs}"
    )


def run_demo():
    if HAS_RICH:
        console.print(Panel.fit(
            "[bold cyan]FORGE VISUAL NETWORK[/bold cyan]\n"
            "[dim]Dual Visual Streams — Ventral · Dorsal · Scene Graph[/dim]\n"
            f"[dim]Version {VERSION}  |  Ventral: what · Dorsal: where[/dim]",
            border_style="cyan"
        ))

    net = ForgeVisualNetwork()

    scenes = [
        # Normal indoor technical scene
        ("Technician in uniform standing near server rack. Computer terminal on desk. Door open to corridor.",
         "Routine server room inspection"),

        # Person concealed — low visibility
        ("Dark figure in shadow near entrance door. Low visibility corridor. Person partially concealed.",
         "Suspicious concealed entity"),

        # Weapon detected — critical
        ("Weapon detected near server rack. Person blocking exit door. Two threat objects visible. Dark conditions.",
         "Critical — weapon + exit blocked"),

        # Flanked geometry
        ("Two unknown figures approaching from left and right. Server equipment between them. Corridor chokepoint ahead.",
         "Flanking approach in chokepoint"),

        # Same server room — repeated exposure
        ("Technician in uniform standing near server rack. Computer terminal on desk. Door open to corridor.",
         "Repeated scene — familiarity builds"),

        # Open clear scene — recovery
        ("Empty open office space. Normal lighting. Desk and chair. Window to exterior visible. No persons present.",
         "Clear open space — all clear"),
    ]

    for i, (desc, label) in enumerate(scenes):
        if HAS_RICH:
            console.print(f"\n[bold dim]━━━ {i+1}: {label.upper()} ━━━[/bold dim]")
        result = net.perceive(desc)
        render_percept(result, desc, i+1)
        time.sleep(0.1)

    # Final status
    if HAS_RICH:
        console.print(Rule("[bold cyan]⬡ VISUAL NETWORK FINAL STATUS[/bold cyan]"))
        rows = net.db.get_recent_percepts(8)
        hist = Table(box=box.SIMPLE, title="Visual Percept History", title_style="dim")
        hist.add_column("ID",       width=10)
        hist.add_column("Scene",    width=20)
        hist.add_column("Threats",  justify="center", width=8)
        hist.add_column("VTS",      justify="right",  width=7)
        hist.add_column("Summary",  width=35)
        for row in rows:
            vts   = row[4]
            vc    = "bright_red" if vts>0.6 else "red" if vts>0.3 else "green"
            hist.add_row(
                row[0], row[2][:18],
                str(row[3]),
                f"[{vc}]{vts:.2f}[/{vc}]",
                row[5][:34]
            )
        console.print(hist)


# ─── HTTP API ─────────────────────────────────────────────────────────────────

def run_api(net: ForgeVisualNetwork):
    if not HAS_FLASK: return
    app = Flask(__name__)

    @app.route("/perceive", methods=["POST"])
    def perceive():
        data = request.json or {}
        return jsonify(net.perceive(
            data.get("description",""),
            data.get("entity_name","unknown")
        ))

    @app.route("/percepts", methods=["GET"])
    def percepts():
        rows = net.db.get_recent_percepts(20)
        return jsonify([{"id":r[0],"timestamp":r[1],"scene":r[2],
                        "threats":r[3],"vts":r[4],"summary":r[5]}
                       for r in rows])

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify(net.get_status())

    app.run(host="0.0.0.0", port=API_PORT, debug=False)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    net = ForgeVisualNetwork()
    if "--api" in sys.argv:
        t = threading.Thread(target=run_api, args=(net,), daemon=True)
        t.start()
    run_demo()
