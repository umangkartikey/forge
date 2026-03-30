"""
FORGE Salience Network — forge_salience.py
==========================================
AI analog of the brain's salience network.

The salience network decides what's worth paying attention to.
It is the brain's priority interrupt system — some signals jump the queue,
others flow normally, routine input is filtered away.

Without salience, all signals are equal. With it, FORGE knows what matters.

Architecture:
  SalienceDetector    → scores every signal on urgency + novelty + relevance
  PriorityInterrupt   → threat≥4 bypasses full pipeline — immediate response
  AttentionFilter     → routine signals flow at normal pace
  BottomUpSalience    → signal-driven (sudden, loud, dangerous, unexpected)
  TopDownSalience     → goal-driven (relevant to what FORGE cares about now)
  SalienceMap         → real-time map of what's hot right now
  OrientingResponse   → "wait — what was that?" — catches subtle anomalies
  SalienceHistory     → tracks what has grabbed attention over time
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

DB_PATH  = "forge_salience.db"
API_PORT = 7784
VERSION  = "1.0.0"

# Salience thresholds
INTERRUPT_THRESHOLD  = 0.85   # above this → priority interrupt
HIGH_SALIENCE        = 0.65
MEDIUM_SALIENCE      = 0.40
FILTER_THRESHOLD     = 0.15   # below this → filtered out (too routine)

console = Console() if HAS_RICH else None

# ─── Enums ────────────────────────────────────────────────────────────────────

class SalienceClass(Enum):
    INTERRUPT  = "INTERRUPT"   # bypass pipeline — act NOW
    HIGH       = "HIGH"        # front of queue
    MEDIUM     = "MEDIUM"      # normal processing
    LOW        = "LOW"         # background
    FILTERED   = "FILTERED"    # too routine — ignore

class AttentionMode(Enum):
    VIGILANT   = "VIGILANT"    # heightened — after recent threat
    NORMAL     = "NORMAL"      # baseline
    RELAXED    = "RELAXED"     # calm period — slightly lower sensitivity
    FOCUSED    = "FOCUSED"     # locked onto specific target
    ORIENTING  = "ORIENTING"   # something caught attention — investigating

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class SalienceScore:
    id:              str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:       str   = field(default_factory=lambda: datetime.now().isoformat())
    signal_id:       str   = ""
    # Component scores (0-1 each)
    urgency:         float = 0.0   # how time-critical
    novelty:         float = 0.0   # how unexpected
    relevance:       float = 0.0   # how goal-relevant
    intensity:       float = 0.0   # how strong the signal is
    social_weight:   float = 0.0   # involves known threat entity?
    # Composite
    bottom_up:       float = 0.0   # signal-driven score
    top_down:        float = 0.0   # goal-driven score
    final_score:     float = 0.0   # weighted combination
    salience_class:  str   = SalienceClass.MEDIUM.value
    interrupt:       bool  = False
    routing:         str   = "NORMAL_PIPELINE"
    explanation:     str   = ""

@dataclass
class SalienceMapEntry:
    concept:     str   = ""
    heat:        float = 0.0   # 0-1 current salience heat
    peak_heat:   float = 0.0
    last_active: str   = field(default_factory=lambda: datetime.now().isoformat())
    activations: int   = 0

@dataclass
class OrientingEvent:
    id:          str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:   str   = field(default_factory=lambda: datetime.now().isoformat())
    trigger:     str   = ""
    strength:    float = 0.0
    resolved:    bool  = False
    resolution:  str   = ""

# ─── Database ─────────────────────────────────────────────────────────────────

class SalienceDB:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init()

    def _init(self):
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS salience_scores (
                    id TEXT PRIMARY KEY, timestamp TEXT, signal_id TEXT,
                    urgency REAL, novelty REAL, relevance REAL,
                    intensity REAL, social_weight REAL,
                    bottom_up REAL, top_down REAL, final_score REAL,
                    salience_class TEXT, interrupt INTEGER,
                    routing TEXT, explanation TEXT
                );
                CREATE TABLE IF NOT EXISTS salience_map (
                    concept TEXT PRIMARY KEY, heat REAL, peak_heat REAL,
                    last_active TEXT, activations INTEGER
                );
                CREATE TABLE IF NOT EXISTS orienting_events (
                    id TEXT PRIMARY KEY, timestamp TEXT, trigger TEXT,
                    strength REAL, resolved INTEGER, resolution TEXT
                );
                CREATE TABLE IF NOT EXISTS attention_log (
                    id TEXT PRIMARY KEY, timestamp TEXT,
                    mode TEXT, trigger TEXT, duration_ms REAL
                );
            """)
            self.conn.commit()

    def save_score(self, s: SalienceScore):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO salience_scores VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (s.id, s.timestamp, s.signal_id, s.urgency, s.novelty,
                  s.relevance, s.intensity, s.social_weight,
                  s.bottom_up, s.top_down, s.final_score,
                  s.salience_class, int(s.interrupt), s.routing, s.explanation))
            self.conn.commit()

    def update_map(self, concept: str, heat: float):
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM salience_map WHERE concept=?", (concept,)
            ).fetchone()
            if row:
                new_heat = min(1.0, heat)
                peak     = max(row[2], new_heat)
                self.conn.execute("""
                    UPDATE salience_map SET heat=?, peak_heat=?,
                    last_active=?, activations=? WHERE concept=?
                """, (new_heat, peak, datetime.now().isoformat(), row[4]+1, concept))
            else:
                self.conn.execute(
                    "INSERT INTO salience_map VALUES (?,?,?,?,?)",
                    (concept, heat, heat, datetime.now().isoformat(), 1)
                )
            self.conn.commit()

    def get_map(self, top_n=10):
        with self.lock:
            return self.conn.execute(
                "SELECT concept, heat, peak_heat, activations FROM salience_map ORDER BY heat DESC LIMIT ?",
                (top_n,)
            ).fetchall()

    def get_scores(self, limit=20):
        with self.lock:
            return self.conn.execute(
                "SELECT id, timestamp, final_score, salience_class, interrupt, routing, explanation FROM salience_scores ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()

    def save_orient(self, o: OrientingEvent):
        with self.lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO orienting_events VALUES (?,?,?,?,?,?)",
                (o.id, o.timestamp, o.trigger, o.strength, int(o.resolved), o.resolution)
            )
            self.conn.commit()


# ─── Bottom-Up Salience ───────────────────────────────────────────────────────

class BottomUpSalience:
    """
    Signal-driven salience — what jumps out regardless of goals.
    Driven by: threat level, anomaly, sudden change, intensity.
    This is the "loud noise" mechanism — automatic, pre-cognitive.
    """

    THREAT_WEIGHTS  = {0: 0.05, 1: 0.25, 2: 0.50, 3: 0.80, 4: 1.00}
    EMOTION_WEIGHTS = {
        "fear": 0.90, "anger": 0.85, "surprise": 0.80,
        "disgust": 0.60, "sadness": 0.40,
        "trust": 0.20, "joy": 0.20, "neutral": 0.10
    }

    def score(self, signal: dict) -> tuple[float, dict]:
        threat  = signal.get("threat", 0)
        anomaly = signal.get("anomaly", False)
        emotion = signal.get("emotional", {})
        if isinstance(emotion, dict):
            emotion_name = emotion.get("dominant", "neutral")
            intensity    = emotion.get("intensity", 0.3)
        else:
            emotion_name, intensity = "neutral", 0.3

        social  = signal.get("social", {})
        visual  = signal.get("visual", {})
        auditory= signal.get("auditory", {})

        # Component scores
        urgency   = self.THREAT_WEIGHTS.get(threat, 0.0)
        if anomaly: urgency = min(1.0, urgency + 0.2)

        novelty   = 1.0 - signal.get("novelty_hint", 0.5)  # low novelty_hint = high novelty
        if anomaly: novelty = min(1.0, novelty + 0.3)

        em_weight = self.EMOTION_WEIGHTS.get(emotion_name, 0.1)
        sig_intensity = em_weight * intensity

        # Visual threat boost
        v_threats = visual.get("threat_objects", 0) if isinstance(visual, dict) else 0
        visual_boost = min(0.4, v_threats * 0.2)

        # Auditory stress boost
        a_stress = auditory.get("stress_level", 0.0) if isinstance(auditory, dict) else 0.0
        audio_boost = a_stress * 0.3

        # Social risk boost
        s_risk = social.get("social_risk", "LOW") if isinstance(social, dict) else "LOW"
        social_boost = {"HIGH": 0.3, "MEDIUM": 0.15, "LOW": 0.0}.get(s_risk, 0.0)

        bottom_up = min(1.0,
            urgency * 0.40 +
            novelty * 0.20 +
            sig_intensity * 0.15 +
            visual_boost +
            audio_boost +
            social_boost
        )

        components = {
            "urgency": round(urgency, 2),
            "novelty": round(novelty, 2),
            "intensity": round(sig_intensity, 2),
            "visual_boost": round(visual_boost, 2),
            "audio_boost": round(audio_boost, 2),
            "social_boost": round(social_boost, 2)
        }
        return round(bottom_up, 3), components


# ─── Top-Down Salience ────────────────────────────────────────────────────────

class TopDownSalience:
    """
    Goal-driven salience — what matters because of what FORGE cares about.
    Active goals amplify relevance of matching signals.
    This is the "looking for your keys" mechanism — attention guided by intent.
    """

    def __init__(self):
        self.active_goals: list[dict] = [
            {"name": "MAINTAIN_SECURITY",  "keywords": ["threat","weapon","breach","intrusion","attack"], "weight": 1.0},
            {"name": "TRACK_ENTITIES",     "keywords": ["entity","unknown","identity","person","agent"],  "weight": 0.8},
            {"name": "SYSTEM_INTEGRITY",   "keywords": ["network","server","access","system","pipeline"], "weight": 0.7},
            {"name": "SOCIAL_AWARENESS",   "keywords": ["trust","cooperation","intent","behavior"],       "weight": 0.6},
            {"name": "LEARN_PATTERNS",     "keywords": ["pattern","recurring","novel","anomaly"],         "weight": 0.5},
        ]
        self.focus_entity: Optional[str] = None  # currently focused entity

    def score(self, signal: dict) -> tuple[float, str]:
        semantic = signal.get("semantic", {})
        keywords = []
        if isinstance(semantic, dict):
            keywords = semantic.get("keywords", [])

        conclusion = signal.get("conclusion", "")
        text       = signal.get("text", "")
        all_text   = " ".join(keywords + [conclusion, text]).lower()

        best_score  = 0.0
        best_goal   = "none"

        for goal in self.active_goals:
            matches = sum(1 for kw in goal["keywords"] if kw in all_text)
            if matches > 0:
                score = min(1.0, (matches / len(goal["keywords"])) * goal["weight"] * 1.5)
                if score > best_score:
                    best_score = score
                    best_goal  = goal["name"]

        # Focus boost — if we're tracking a specific entity
        if self.focus_entity:
            entity = signal.get("entity_name", "")
            social = signal.get("social", {})
            sig_entity = social.get("entity", entity) if isinstance(social, dict) else entity
            if self.focus_entity.lower() in str(sig_entity).lower():
                best_score = min(1.0, best_score + 0.3)
                best_goal  = f"FOCUS:{self.focus_entity}"

        return round(best_score, 3), best_goal

    def set_focus(self, entity: str):
        self.focus_entity = entity

    def clear_focus(self):
        self.focus_entity = None


# ─── Orienting Response ───────────────────────────────────────────────────────

class OrientingResponse:
    """
    The "wait — what was that?" mechanism.
    Catches subtle anomalies that don't score high on threat
    but are statistically unusual given recent history.
    Like hearing your name in a noisy room.
    """

    def __init__(self, window: int = 20):
        self.history:  deque = deque(maxlen=window)
        self.baseline: float = 0.3
        self.events:   list[OrientingEvent] = []

    def check(self, score: float, signal: dict, db: SalienceDB) -> Optional[OrientingEvent]:
        self.history.append(score)

        if len(self.history) >= 5:
            self.baseline = sum(list(self.history)[:-1]) / (len(self.history) - 1)

        deviation = abs(score - self.baseline)

        # Orienting fires on sudden change — up OR down
        if deviation > 0.25 and len(self.history) >= 3:
            direction = "↑ SPIKE" if score > self.baseline else "↓ DROP"
            trigger   = (
                f"Salience {direction}: {score:.2f} vs baseline {self.baseline:.2f} "
                f"(deviation={deviation:.2f})"
            )
            event = OrientingEvent(
                trigger=trigger,
                strength=min(1.0, deviation * 2),
            )
            db.save_orient(event)
            self.events.append(event)
            return event

        return None


# ─── Salience Map ─────────────────────────────────────────────────────────────

class SalienceMap:
    """
    Real-time heat map of what's currently salient in FORGE's world.
    Concepts that appear in high-salience signals get hot.
    Heat decays over time — like thermal cooling.
    """

    def __init__(self, db: SalienceDB, decay: float = 0.85):
        self.db    = db
        self.decay = decay
        self.map:  dict[str, SalienceMapEntry] = {}

    def update(self, signal: dict, score: float):
        # Extract concepts from signal
        concepts = []
        semantic = signal.get("semantic", {})
        if isinstance(semantic, dict):
            concepts.extend(semantic.get("keywords", [])[:5])

        social = signal.get("social", {})
        if isinstance(social, dict) and social.get("entity"):
            concepts.append(social["entity"])

        entity = signal.get("entity_name", "")
        if entity and entity not in concepts:
            concepts.append(entity)

        # Update heat for each concept
        for concept in concepts:
            if concept not in self.map:
                self.map[concept] = SalienceMapEntry(concept=concept)
            entry      = self.map[concept]
            entry.heat = min(1.0, entry.heat + score * 0.4)
            entry.peak_heat  = max(entry.peak_heat, entry.heat)
            entry.last_active= datetime.now().isoformat()
            entry.activations+= 1
            self.db.update_map(concept, entry.heat)

        # Decay all entries
        for entry in self.map.values():
            entry.heat = round(entry.heat * self.decay, 3)

    def hottest(self, n: int = 5) -> list[SalienceMapEntry]:
        return sorted(self.map.values(), key=lambda e: e.heat, reverse=True)[:n]

    def snapshot(self) -> dict:
        return {
            "total_concepts": len(self.map),
            "hot":  [{"concept": e.concept, "heat": e.heat, "activations": e.activations}
                     for e in self.hottest(8)]
        }


# ─── Priority Interrupt ───────────────────────────────────────────────────────

class PriorityInterrupt:
    """
    When salience exceeds INTERRUPT_THRESHOLD, the normal pipeline is bypassed.
    The signal goes directly to the response layer — no waiting, no deliberation.
    This is the brain's emergency reflex circuit.
    """

    def __init__(self):
        self.interrupt_count = 0
        self.last_interrupt: Optional[dict] = None

    def check(self, score: SalienceScore, signal: dict) -> Optional[dict]:
        if score.final_score >= INTERRUPT_THRESHOLD or signal.get("threat", 0) >= 4:
            self.interrupt_count += 1
            self.last_interrupt  = {
                "timestamp":   datetime.now().isoformat(),
                "score":       score.final_score,
                "threat":      signal.get("threat", 0),
                "entity":      signal.get("entity_name", "unknown"),
                "conclusion":  signal.get("conclusion", "")[:80],
                "action":      self._immediate_action(signal),
                "interrupt_n": self.interrupt_count
            }
            score.interrupt = True
            score.routing   = "PRIORITY_INTERRUPT"
            return self.last_interrupt
        return None

    def _immediate_action(self, signal: dict) -> str:
        threat = signal.get("threat", 0)
        social = signal.get("social", {})
        intent = social.get("inferred_intent", "") if isinstance(social, dict) else ""

        if threat >= 4:          return "EMERGENCY_BLOCK — maximum threat"
        if "INTRUSION" in intent: return "ISOLATE_ENTITY — intrusion detected"
        if threat >= 3:          return "ESCALATE_IMMEDIATELY — critical threshold"
        return "PRIORITY_ALERT — high salience event"


# ─── Attention Filter ─────────────────────────────────────────────────────────

class AttentionFilter:
    """
    Routes signals based on salience class.
    High → front of processing queue
    Medium → normal pipeline
    Low → background processing
    Filtered → discard (too routine)
    """

    def __init__(self):
        self.mode            = AttentionMode.NORMAL
        self.mode_since      = datetime.now()
        self.filtered_count  = 0
        self.passed_count    = 0

    def route(self, score: SalienceScore, signal: dict) -> dict:
        cls = score.salience_class

        if cls == SalienceClass.FILTERED.value:
            self.filtered_count += 1
            return {
                "pass":     False,
                "reason":   "FILTERED — below salience threshold",
                "score":    score.final_score,
                "class":    cls
            }

        self.passed_count += 1
        pipeline_priority = {
            SalienceClass.INTERRUPT.value: 0,
            SalienceClass.HIGH.value:      1,
            SalienceClass.MEDIUM.value:    2,
            SalienceClass.LOW.value:       3,
        }.get(cls, 2)

        return {
            "pass":             True,
            "pipeline_priority":pipeline_priority,
            "class":            cls,
            "score":            score.final_score,
            "interrupt":        score.interrupt,
            "routing":          score.routing,
            "explanation":      score.explanation
        }

    def update_mode(self, recent_threats: list):
        if not recent_threats:
            self.mode = AttentionMode.NORMAL
            return
        avg = sum(recent_threats) / len(recent_threats)
        if avg >= 2.5:   self.mode = AttentionMode.VIGILANT
        elif avg >= 1.5: self.mode = AttentionMode.NORMAL
        else:            self.mode = AttentionMode.RELAXED

    def mode_multiplier(self) -> float:
        return {
            AttentionMode.VIGILANT:  1.25,
            AttentionMode.NORMAL:    1.00,
            AttentionMode.RELAXED:   0.85,
            AttentionMode.FOCUSED:   1.15,
            AttentionMode.ORIENTING: 1.10,
        }.get(self.mode, 1.0)


# ─── Salience Detector (Main) ─────────────────────────────────────────────────

class SalienceDetector:
    """
    Combines bottom-up and top-down salience into a final score.
    Applies attention mode multiplier.
    Classifies signal and determines routing.
    """

    def __init__(self, db: SalienceDB,
                 bottom_up: BottomUpSalience,
                 top_down: TopDownSalience,
                 filter_: AttentionFilter):
        self.db        = db
        self.bottom_up = bottom_up
        self.top_down  = top_down
        self.filter    = filter_

    def detect(self, signal: dict) -> SalienceScore:
        bu_score, bu_components = self.bottom_up.score(signal)
        td_score, td_goal       = self.top_down.score(signal)

        # Weighted combination — bottom-up slightly dominant
        mode_mult  = self.filter.mode_multiplier()
        raw_score  = (bu_score * 0.60 + td_score * 0.40) * mode_mult
        final      = round(min(1.0, raw_score), 3)

        # Classify
        if final >= INTERRUPT_THRESHOLD:     cls = SalienceClass.INTERRUPT
        elif final >= HIGH_SALIENCE:         cls = SalienceClass.HIGH
        elif final >= MEDIUM_SALIENCE:       cls = SalienceClass.MEDIUM
        elif final >= FILTER_THRESHOLD:      cls = SalienceClass.LOW
        else:                                cls = SalienceClass.FILTERED

        # Build explanation
        parts = []
        if bu_components["urgency"] > 0.3:
            parts.append(f"urgent(threat={signal.get('threat',0)})")
        if bu_components["novelty"] > 0.5:
            parts.append("novel")
        if bu_components["social_boost"] > 0.1:
            parts.append("social-risk")
        if bu_components["visual_boost"] > 0.1:
            parts.append("visual-threat")
        if td_goal != "none":
            parts.append(f"goal:{td_goal}")
        explanation = ", ".join(parts) if parts else "routine"

        score = SalienceScore(
            signal_id    = signal.get("id", str(uuid.uuid4())[:8]),
            urgency      = bu_components["urgency"],
            novelty      = bu_components["novelty"],
            relevance    = td_score,
            intensity    = bu_components["intensity"],
            social_weight= bu_components["social_boost"],
            bottom_up    = bu_score,
            top_down     = td_score,
            final_score  = final,
            salience_class = cls.value,
            routing      = "NORMAL_PIPELINE",
            explanation  = explanation
        )
        self.db.save_score(score)
        return score


# ─── FORGE Salience Network ───────────────────────────────────────────────────

class ForgeSalienceNetwork:
    def __init__(self):
        self.db         = SalienceDB()
        self.bottom_up  = BottomUpSalience()
        self.top_down   = TopDownSalience()
        self.filter     = AttentionFilter()
        self.detector   = SalienceDetector(self.db, self.bottom_up, self.top_down, self.filter)
        self.interrupt  = PriorityInterrupt()
        self.orienting  = OrientingResponse()
        self.sal_map    = SalienceMap(self.db)
        self.history:   deque = deque(maxlen=100)
        self.recent_threats: deque = deque(maxlen=10)

    def process(self, signal: dict) -> dict:
        """Score a signal and determine its routing."""
        score    = self.detector.detect(signal)
        threat   = signal.get("threat", 0)
        self.recent_threats.append(threat)
        self.filter.update_mode(list(self.recent_threats))

        # Check priority interrupt
        interrupt_event = self.interrupt.check(score, signal)

        # Check orienting response
        orient_event = self.orienting.check(score.final_score, signal, self.db)

        # Update salience map
        self.sal_map.update(signal, score.final_score)

        # Route signal
        routing = self.filter.route(score, signal)

        self.history.append({
            "id":     score.id,
            "score":  score.final_score,
            "class":  score.salience_class,
            "threat": threat
        })

        return {
            "score":         score.final_score,
            "class":         score.salience_class,
            "interrupt":     score.interrupt,
            "routing":       routing,
            "interrupt_event": interrupt_event,
            "orienting":     {"trigger": orient_event.trigger,
                             "strength": orient_event.strength} if orient_event else None,
            "attention_mode":self.filter.mode.value,
            "bottom_up":     score.bottom_up,
            "top_down":      score.top_down,
            "explanation":   score.explanation,
            "map_snapshot":  self.sal_map.snapshot()
        }

    def get_status(self) -> dict:
        return {
            "version":        VERSION,
            "total_scored":   len(self.history),
            "interrupts":     self.interrupt.interrupt_count,
            "filtered":       self.filter.filtered_count,
            "passed":         self.filter.passed_count,
            "attention_mode": self.filter.mode.value,
            "orienting_events":len(self.orienting.events),
            "map":            self.sal_map.snapshot()
        }


# ─── Rich UI ──────────────────────────────────────────────────────────────────

def render_salience(result: dict, signal: dict, idx: int):
    if not HAS_RICH: return

    score      = result["score"]
    cls        = result["class"]
    interrupt  = result["interrupt"]
    mode       = result["attention_mode"]

    cls_color  = {
        "INTERRUPT":"bright_red","HIGH":"red",
        "MEDIUM":"yellow","LOW":"blue","FILTERED":"dim"
    }.get(cls, "white")
    mode_color = {
        "VIGILANT":"red","NORMAL":"green",
        "RELAXED":"dim","FOCUSED":"cyan","ORIENTING":"yellow"
    }.get(mode, "white")

    console.print(Rule(
        f"[bold cyan]⬡ FORGE SALIENCE[/bold cyan]  "
        f"[dim]#{idx}[/dim]  "
        f"[{cls_color}]{cls}[/{cls_color}]  "
        f"score={score:.3f}  "
        f"mode=[{mode_color}]{mode}[/{mode_color}]"
    ))

    if interrupt:
        ie = result["interrupt_event"]
        console.print(Panel(
            f"[bold bright_red]⚡ PRIORITY INTERRUPT #{ie['interrupt_n']}[/bold bright_red]\n"
            f"Action: [red]{ie['action']}[/red]\n"
            f"[dim]{ie['conclusion']}[/dim]",
            border_style="bright_red"
        ))

    # Score breakdown
    score_table = Table(box=box.SIMPLE, show_header=False, expand=True)
    score_table.add_column("k", style="dim", width=16)
    score_table.add_column("v")

    def bar(v, width=12):
        filled = int(v * width)
        return "█" * filled + "░" * (width - filled) + f" {v:.2f}"

    score_table.add_row("Bottom-Up",  f"[cyan]{bar(result['bottom_up'])}[/cyan]")
    score_table.add_row("Top-Down",   f"[magenta]{bar(result['top_down'])}[/magenta]")
    score_table.add_row("Final",      f"[{cls_color}]{bar(score)}[/{cls_color}]")
    score_table.add_row("Why",        f"[dim]{result['explanation']}[/dim]")
    score_table.add_row("Routing",    result["routing"]["routing"] if isinstance(result["routing"], dict) else str(result["routing"]))

    # Map heat
    map_table = Table(box=box.SIMPLE, show_header=False, expand=True)
    map_table.add_column("concept", style="dim", width=14)
    map_table.add_column("heat")
    for entry in result["map_snapshot"]["hot"][:5]:
        h      = entry["heat"]
        hcolor = "red" if h > 0.6 else "yellow" if h > 0.3 else "dim"
        map_table.add_row(
            entry["concept"][:13],
            f"[{hcolor}]{'█'*int(h*10)}{'░'*(10-int(h*10))} {h:.2f}[/{hcolor}]"
        )

    console.print(Columns([
        Panel(score_table, title="[bold]Salience Score[/bold]", border_style=cls_color),
        Panel(map_table,   title="[bold]Heat Map[/bold]",       border_style="dim")
    ]))

    if result.get("orienting"):
        oe = result["orienting"]
        console.print(Panel(
            f"[yellow]◉ ORIENTING RESPONSE[/yellow]  strength={oe['strength']:.2f}\n"
            f"[dim]{oe['trigger']}[/dim]",
            border_style="yellow"
        ))


# ─── HTTP API ─────────────────────────────────────────────────────────────────

def run_api(net: ForgeSalienceNetwork):
    if not HAS_FLASK: return
    app = Flask(__name__)

    @app.route("/score", methods=["POST"])
    def score():
        return jsonify(net.process(request.json or {}))

    @app.route("/map", methods=["GET"])
    def map_():
        return jsonify(net.sal_map.snapshot())

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify(net.get_status())

    app.run(host="0.0.0.0", port=API_PORT, debug=False)
