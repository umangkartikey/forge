"""
FORGE Temporal Cortex — forge_temporal.py
==========================================
AI analog of the lateral temporal cortex.
Handles: Semantic Memory, Emotional Tone, Visual Object Recognition,
         Auditory Processing, Social Cognition, Perception Binding,
         Temporal Sequence Memory, and Anomaly Detection.

Architecture mirrors bilateral brain specialization:
  LEFT  → SemanticMemoryEngine + EmotionalToneAnalyzer
  RIGHT → VisualObjectRecognition + AuditoryProcessingEngine + SocialCognitionEngine
  BIND  → PerceptionBindingLayer + TemporalSequenceMemory + AnomalyDetector
"""

import json
import time
import uuid
import sqlite3
import threading
import hashlib
import math
from datetime import datetime
from collections import deque, defaultdict
from typing import Optional
from dataclasses import dataclass, field, asdict

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.live import Live
    from rich.layout import Layout
    from rich.text import Text
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

try:
    from flask import Flask, request, jsonify
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# ─── Constants ────────────────────────────────────────────────────────────────

DB_PATH = "forge_temporal.db"
API_PORT = 7778
VERSION  = "1.0.0"

console = Console() if HAS_RICH else None

THREAT_LEVELS = {0: "NONE", 1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}
EMOTION_PALETTE = ["neutral","joy","fear","anger","sadness","disgust","surprise","trust","anticipation"]

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class PerceptionEvent:
    id:          str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:   str = field(default_factory=lambda: datetime.now().isoformat())
    visual:      Optional[dict] = None
    auditory:    Optional[dict] = None
    semantic:    Optional[dict] = None
    emotional:   Optional[dict] = None
    social:      Optional[dict] = None
    bound:       Optional[dict] = None
    threat:      int = 0
    anomaly:     bool = False
    conclusion:  str = ""

@dataclass
class SemanticConcept:
    id:         str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    concept:    str = ""
    definition: str = ""
    relations:  list = field(default_factory=list)
    confidence: float = 1.0
    created:    str = field(default_factory=lambda: datetime.now().isoformat())
    accessed:   int = 0

@dataclass
class SocialEntity:
    id:          str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:        str = ""
    intent:      str = "unknown"
    trust_score: float = 0.5
    behavior_log: list = field(default_factory=list)
    relations:   dict = field(default_factory=dict)

# ─── Database Layer ────────────────────────────────────────────────────────────

class TemporalDB:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init_schema()

    def _init_schema(self):
        with self.lock:
            c = self.conn.cursor()
            c.executescript("""
                CREATE TABLE IF NOT EXISTS perception_events (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    visual TEXT,
                    auditory TEXT,
                    semantic TEXT,
                    emotional TEXT,
                    social TEXT,
                    bound TEXT,
                    threat INTEGER DEFAULT 0,
                    anomaly INTEGER DEFAULT 0,
                    conclusion TEXT
                );
                CREATE TABLE IF NOT EXISTS semantic_memory (
                    id TEXT PRIMARY KEY,
                    concept TEXT UNIQUE,
                    definition TEXT,
                    relations TEXT,
                    confidence REAL,
                    created TEXT,
                    accessed INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS social_entities (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE,
                    intent TEXT,
                    trust_score REAL,
                    behavior_log TEXT,
                    relations TEXT
                );
                CREATE TABLE IF NOT EXISTS temporal_sequence (
                    id TEXT PRIMARY KEY,
                    sequence_id TEXT,
                    event_id TEXT,
                    position INTEGER,
                    timestamp TEXT
                );
            """)
            self.conn.commit()

    def save_event(self, evt: PerceptionEvent):
        with self.lock:
            c = self.conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO perception_events
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                evt.id, evt.timestamp,
                json.dumps(evt.visual), json.dumps(evt.auditory),
                json.dumps(evt.semantic), json.dumps(evt.emotional),
                json.dumps(evt.social), json.dumps(evt.bound),
                evt.threat, int(evt.anomaly), evt.conclusion
            ))
            self.conn.commit()

    def get_events(self, limit=50):
        with self.lock:
            c = self.conn.cursor()
            rows = c.execute(
                "SELECT * FROM perception_events ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            return rows

    def save_concept(self, sc: SemanticConcept):
        with self.lock:
            c = self.conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO semantic_memory VALUES (?,?,?,?,?,?,?)
            """, (sc.id, sc.concept, sc.definition,
                  json.dumps(sc.relations), sc.confidence, sc.created, sc.accessed))
            self.conn.commit()

    def get_concepts(self, limit=100):
        with self.lock:
            c = self.conn.cursor()
            return c.execute(
                "SELECT concept, definition, confidence, accessed FROM semantic_memory ORDER BY accessed DESC LIMIT ?",
                (limit,)
            ).fetchall()

    def save_entity(self, se: SocialEntity):
        with self.lock:
            c = self.conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO social_entities VALUES (?,?,?,?,?,?)
            """, (se.id, se.name, se.intent, se.trust_score,
                  json.dumps(se.behavior_log), json.dumps(se.relations)))
            self.conn.commit()

    def get_entities(self, limit=50):
        with self.lock:
            c = self.conn.cursor()
            return c.execute(
                "SELECT name, intent, trust_score FROM social_entities ORDER BY trust_score ASC LIMIT ?",
                (limit,)
            ).fetchall()

# ─── Engines ──────────────────────────────────────────────────────────────────

class SemanticMemoryEngine:
    """Left hemisphere analog — language, meaning, concepts."""

    def __init__(self, db: TemporalDB):
        self.db = db
        self.cache: dict[str, SemanticConcept] = {}

    def encode(self, text: str) -> dict:
        words = text.lower().split()
        keywords = [w for w in words if len(w) > 4]
        fingerprint = hashlib.md5(text.encode()).hexdigest()[:8]
        concept = SemanticConcept(
            concept=text[:60],
            definition=f"Encoded from input. Key terms: {', '.join(keywords[:5])}",
            relations=keywords[:8],
            confidence=min(1.0, len(keywords) / 10)
        )
        self.cache[fingerprint] = concept
        self.db.save_concept(concept)
        return {
            "fingerprint": fingerprint,
            "keywords": keywords[:8],
            "concept_density": round(len(keywords)/max(len(words),1), 2),
            "stored": True
        }

    def retrieve(self, query: str) -> list:
        results = []
        q = query.lower()
        for sc in self.cache.values():
            if q in sc.concept.lower() or any(q in r for r in sc.relations):
                sc.accessed += 1
                results.append({"concept": sc.concept, "confidence": sc.confidence})
        return results[:5]

    def infer(self, text: str) -> str:
        keywords = [w for w in text.lower().split() if len(w) > 4]
        if any(w in keywords for w in ["attack","threat","danger","weapon","breach"]):
            return "THREAT_SEMANTIC"
        if any(w in keywords for w in ["help","assist","support","request","please"]):
            return "BENIGN_REQUEST"
        if any(w in keywords for w in ["system","access","network","server","data"]):
            return "TECHNICAL_CONTEXT"
        return "GENERAL_CONTEXT"


class EmotionalToneAnalyzer:
    """Left/Right bridge — detects emotion, sarcasm, prosody."""

    SIGNALS = {
        "joy":         ["happy","great","love","excited","wonderful","amazing","fantastic"],
        "fear":        ["scared","worried","afraid","danger","threat","panic","anxious"],
        "anger":       ["angry","furious","hate","rage","hostile","attack","aggressive"],
        "sadness":     ["sad","depressed","loss","grief","lonely","hopeless","cry"],
        "disgust":     ["disgusting","awful","horrible","terrible","repulsive"],
        "surprise":    ["wow","unexpected","sudden","shocked","unbelievable"],
        "trust":       ["trust","reliable","safe","secure","honest","authentic"],
        "anticipation":["soon","expect","waiting","planning","preparing","ready"],
    }

    def analyze(self, text: str) -> dict:
        text_lower = text.lower()
        scores = {}
        for emotion, words in self.SIGNALS.items():
            score = sum(1 for w in words if w in text_lower)
            if score: scores[emotion] = score

        dominant = max(scores, key=scores.get) if scores else "neutral"
        intensity = min(1.0, sum(scores.values()) / 5) if scores else 0.0

        sarcasm = self._detect_sarcasm(text)
        return {
            "dominant": dominant,
            "scores": scores,
            "intensity": round(intensity, 2),
            "sarcasm_likely": sarcasm,
            "valence": "positive" if dominant in ["joy","trust","anticipation"] else
                       "negative" if dominant in ["fear","anger","sadness","disgust"] else "neutral"
        }

    def _detect_sarcasm(self, text: str) -> bool:
        markers = ["yeah right","sure thing","oh great","wow thanks","obviously","clearly","of course"]
        return any(m in text.lower() for m in markers)


class VisualObjectRecognition:
    """Right hemisphere analog — image to meaning pipeline."""

    THREAT_OBJECTS   = ["weapon","gun","knife","explosive","fire","blood","mask"]
    CONTEXT_OBJECTS  = ["server","computer","phone","camera","car","building","person"]
    NEUTRAL_OBJECTS  = ["chair","desk","tree","sky","road","wall","door"]

    def analyze(self, description: str) -> dict:
        desc_lower = description.lower()
        detected = []
        threat_count = 0

        for obj in self.THREAT_OBJECTS:
            if obj in desc_lower:
                detected.append({"object": obj, "category": "THREAT", "confidence": 0.85})
                threat_count += 1

        for obj in self.CONTEXT_OBJECTS:
            if obj in desc_lower:
                detected.append({"object": obj, "category": "CONTEXT", "confidence": 0.90})

        for obj in self.NEUTRAL_OBJECTS:
            if obj in desc_lower:
                detected.append({"object": obj, "category": "NEUTRAL", "confidence": 0.95})

        scene = self._classify_scene(desc_lower)
        threat_level = min(4, threat_count * 2)

        return {
            "detected_objects": detected,
            "object_count": len(detected),
            "scene_type": scene,
            "threat_objects": threat_count,
            "visual_threat_level": threat_level,
            "semantic_label": self._label(detected, scene)
        }

    def _classify_scene(self, text: str) -> str:
        if any(w in text for w in ["office","desk","computer","server"]):   return "INDOOR_TECHNICAL"
        if any(w in text for w in ["street","road","car","outdoor"]):        return "OUTDOOR_PUBLIC"
        if any(w in text for w in ["crowd","people","group"]):               return "SOCIAL_GATHERING"
        if any(w in text for w in ["dark","night","shadow"]):                return "LOW_VISIBILITY"
        return "UNCLASSIFIED"

    def _label(self, objects: list, scene: str) -> str:
        threats = [o for o in objects if o["category"] == "THREAT"]
        if threats:
            return f"HIGH_ALERT: {threats[0]['object']} detected in {scene}"
        return f"NORMAL: {scene} — {len(objects)} objects identified"


class AuditoryProcessingEngine:
    """Right hemisphere analog — sound patterns to concepts."""

    STRESS_MARKERS    = ["!", "HELP", "STOP", "NOW", "URGENT", "EMERGENCY"]
    CALM_MARKERS      = ["okay", "fine", "normal", "steady", "clear", "good"]
    DECEPTION_MARKERS = ["um", "uh", "well", "actually", "honestly", "i mean"]

    def analyze(self, audio_description: str) -> dict:
        text = audio_description.upper()
        original = audio_description.lower()

        stress_score   = sum(1 for m in self.STRESS_MARKERS if m in text)
        calm_score     = sum(1 for m in self.CALM_MARKERS if m in original)
        deception_score= sum(1 for m in self.DECEPTION_MARKERS if m in original)

        speech_rate = "FAST" if stress_score > 2 else "SLOW" if calm_score > 2 else "NORMAL"
        environment = self._classify_environment(original)
        anomaly     = stress_score > 3 or deception_score > 3

        return {
            "stress_level":     min(1.0, stress_score / 5),
            "calm_level":       min(1.0, calm_score / 5),
            "deception_index":  min(1.0, deception_score / 5),
            "speech_rate":      speech_rate,
            "environment":      environment,
            "anomaly_detected": anomaly,
            "interpretation":   self._interpret(stress_score, deception_score, environment)
        }

    def _classify_environment(self, text: str) -> str:
        if any(w in text for w in ["echo","hall","large","crowd"]): return "LARGE_SPACE"
        if any(w in text for w in ["quiet","soft","whisper"]):      return "QUIET_SPACE"
        if any(w in text for w in ["noise","loud","busy"]):         return "NOISY_ENVIRONMENT"
        return "NEUTRAL_ENVIRONMENT"

    def _interpret(self, stress: int, deception: int, env: str) -> str:
        if stress > 3:   return "DISTRESS_SIGNAL — immediate attention required"
        if deception > 2: return "DECEPTION_PATTERN — elevated hedging detected"
        return f"NORMAL_COMMUNICATION in {env}"


class SocialCognitionEngine:
    """Social intent, behavior modeling, relationship dynamics."""

    def __init__(self, db: TemporalDB):
        self.db = db
        self.entities: dict[str, SocialEntity] = {}

    def analyze(self, text: str, entity_name: str = "unknown") -> dict:
        intent = self._infer_intent(text)
        manipulation = self._detect_manipulation(text)
        cooperation  = self._detect_cooperation(text)
        trust_delta  = 0.1 if cooperation else (-0.15 if manipulation else 0.0)

        entity = self.entities.get(entity_name, SocialEntity(name=entity_name))
        entity.intent = intent
        entity.trust_score = max(0.0, min(1.0, entity.trust_score + trust_delta))
        entity.behavior_log.append({"time": datetime.now().isoformat(), "intent": intent})
        self.entities[entity_name] = entity
        self.db.save_entity(entity)

        return {
            "entity":           entity_name,
            "inferred_intent":  intent,
            "manipulation":     manipulation,
            "cooperation":      cooperation,
            "trust_score":      round(entity.trust_score, 2),
            "trust_trend":      "↑" if trust_delta > 0 else "↓" if trust_delta < 0 else "→",
            "social_risk":      "HIGH" if entity.trust_score < 0.3 else
                                "MEDIUM" if entity.trust_score < 0.6 else "LOW"
        }

    def _infer_intent(self, text: str) -> str:
        text_lower = text.lower()
        if any(w in text_lower for w in ["help","please","could you","would you"]):
            return "COOPERATIVE_REQUEST"
        if any(w in text_lower for w in ["must","demand","now","immediately","comply"]):
            return "COERCIVE_DEMAND"
        if any(w in text_lower for w in ["maybe","perhaps","consider","suggest"]):
            return "COLLABORATIVE_SUGGESTION"
        if any(w in text_lower for w in ["access","enter","bypass","override","hack"]):
            return "INTRUSION_ATTEMPT"
        return "NEUTRAL_INTERACTION"

    def _detect_manipulation(self, text: str) -> bool:
        markers = ["you should","you must","everyone knows","trust me","believe me",
                   "for your own good","just this once","no one will know"]
        return any(m in text.lower() for m in markers)

    def _detect_cooperation(self, text: str) -> bool:
        markers = ["together","collaborate","help","share","support","team","we can"]
        return any(m in text.lower() for m in markers)


class PerceptionBindingLayer:
    """Unifies all sensory streams into one coherent PerceptionEvent."""

    def bind(self,
             semantic: Optional[dict],
             emotional: Optional[dict],
             visual: Optional[dict],
             auditory: Optional[dict],
             social: Optional[dict]) -> dict:

        threat_scores = []
        if visual:   threat_scores.append(visual.get("visual_threat_level", 0))
        if auditory: threat_scores.append(3 if auditory.get("anomaly_detected") else 0)
        if social:   threat_scores.append(3 if social.get("social_risk") == "HIGH" else
                                          1 if social.get("social_risk") == "MEDIUM" else 0)
        if emotional:threat_scores.append(2 if emotional.get("dominant") in ["fear","anger"] else 0)
        if semantic: threat_scores.append(2 if semantic.get("inference") == "THREAT_SEMANTIC" else 0)

        threat = min(4, round(sum(threat_scores) / max(len(threat_scores), 1)))
        confidence = min(1.0, len([x for x in [semantic,emotional,visual,auditory,social] if x]) / 5)

        summary_parts = []
        if visual:   summary_parts.append(f"visual={visual.get('scene_type','?')}")
        if auditory: summary_parts.append(f"audio={auditory.get('speech_rate','?')}")
        if semantic: summary_parts.append(f"meaning={semantic.get('inference','?')}")
        if emotional:summary_parts.append(f"emotion={emotional.get('dominant','?')}")
        if social:   summary_parts.append(f"social={social.get('inferred_intent','?')}")

        conclusion = self._conclude(threat, summary_parts)

        return {
            "bound_streams":  len([x for x in [semantic,emotional,visual,auditory,social] if x]),
            "threat_level":   threat,
            "threat_label":   THREAT_LEVELS[threat],
            "confidence":     round(confidence, 2),
            "summary":        " | ".join(summary_parts),
            "conclusion":     conclusion
        }

    def _conclude(self, threat: int, parts: list) -> str:
        if threat >= 4: return f"⚠ CRITICAL ALERT — All streams indicate maximum threat. Immediate escalation required."
        if threat == 3: return f"⚡ HIGH THREAT — Multiple streams flagged. Escalate to supervisory system."
        if threat == 2: return f"⚠ MEDIUM THREAT — Anomalies detected. Continue monitoring."
        if threat == 1: return f"ℹ LOW CONCERN — Minor signals present. Passive watch active."
        return f"✓ NORMAL — Perception streams stable. No action required."


class TemporalSequenceMemory:
    """Remembers sequences of events — not just snapshots."""

    def __init__(self, max_len=500):
        self.sequences: dict[str, deque] = defaultdict(lambda: deque(maxlen=max_len))
        self.current_sequence = str(uuid.uuid4())[:8]

    def record(self, event: PerceptionEvent):
        self.sequences[self.current_sequence].append({
            "id":        event.id,
            "timestamp": event.timestamp,
            "threat":    event.threat,
            "anomaly":   event.anomaly,
            "conclusion":event.conclusion[:80]
        })

    def pattern_analysis(self) -> dict:
        seq = list(self.sequences[self.current_sequence])
        if len(seq) < 2:
            return {"pattern": "INSUFFICIENT_DATA", "events": len(seq)}

        threats  = [e["threat"] for e in seq]
        anomalies= sum(1 for e in seq if e["anomaly"])
        trend    = "ESCALATING" if threats[-1] > threats[0] else \
                   "DECLINING"  if threats[-1] < threats[0] else "STABLE"

        return {
            "sequence_id":     self.current_sequence,
            "total_events":    len(seq),
            "anomaly_count":   anomalies,
            "threat_trend":    trend,
            "avg_threat":      round(sum(threats)/len(threats), 2),
            "peak_threat":     max(threats),
            "pattern_label":   f"{trend} — {anomalies} anomalies in {len(seq)} events"
        }

    def new_sequence(self):
        self.current_sequence = str(uuid.uuid4())[:8]
        return self.current_sequence


class AnomalyDetector:
    """The AI's 'gut feeling' — something seems off."""

    def __init__(self, window=20):
        self.history = deque(maxlen=window)
        self.baseline_threat = 0.0

    def update(self, threat: int, anomaly_signals: list) -> dict:
        self.history.append(threat)
        if len(self.history) >= 5:
            self.baseline_threat = sum(list(self.history)[:-1]) / (len(self.history)-1)

        deviation  = abs(threat - self.baseline_threat)
        signal_count = len(anomaly_signals)
        is_anomaly = deviation > 1.5 or signal_count >= 3

        return {
            "is_anomaly":       is_anomaly,
            "deviation":        round(deviation, 2),
            "baseline_threat":  round(self.baseline_threat, 2),
            "anomaly_signals":  anomaly_signals,
            "signal_count":     signal_count,
            "gut_feeling":      self._gut(is_anomaly, deviation, signal_count)
        }

    def _gut(self, is_anomaly: bool, deviation: float, signals: int) -> str:
        if not is_anomaly: return "Nothing unusual detected."
        if deviation > 3:  return "Something is very wrong — pattern break detected."
        if signals >= 3:   return "Multiple independent signals align — high confidence anomaly."
        return "Subtle deviation from baseline — worth investigating."


# ─── FORGE Temporal Cortex (Main System) ─────────────────────────────────────

class ForgeTemporalCortex:
    def __init__(self):
        self.db        = TemporalDB()
        self.semantic  = SemanticMemoryEngine(self.db)
        self.emotional = EmotionalToneAnalyzer()
        self.visual    = VisualObjectRecognition()
        self.auditory  = AuditoryProcessingEngine()
        self.social    = SocialCognitionEngine(self.db)
        self.binding   = PerceptionBindingLayer()
        self.memory    = TemporalSequenceMemory()
        self.anomaly   = AnomalyDetector()
        self.events: list[PerceptionEvent] = []

    def perceive(self,
                 text:              Optional[str] = None,
                 visual_input:      Optional[str] = None,
                 auditory_input:    Optional[str] = None,
                 entity_name:       str = "unknown") -> PerceptionEvent:

        evt = PerceptionEvent()

        # Run all active streams
        if text:
            evt.semantic  = {**self.semantic.encode(text),  "inference": self.semantic.infer(text)}
            evt.emotional = self.emotional.analyze(text)
            evt.social    = self.social.analyze(text, entity_name)

        if visual_input:
            evt.visual = self.visual.analyze(visual_input)

        if auditory_input:
            evt.auditory = self.auditory.analyze(auditory_input)

        # Bind all streams
        evt.bound = self.binding.bind(
            evt.semantic, evt.emotional, evt.visual, evt.auditory, evt.social
        )
        evt.threat     = evt.bound["threat_level"]
        evt.conclusion = evt.bound["conclusion"]

        # Anomaly check
        anomaly_signals = []
        if evt.auditory and evt.auditory.get("anomaly_detected"): anomaly_signals.append("auditory")
        if evt.visual   and evt.visual.get("threat_objects", 0) > 0: anomaly_signals.append("visual")
        if evt.social   and evt.social.get("social_risk") == "HIGH": anomaly_signals.append("social")

        anomaly_result = self.anomaly.update(evt.threat, anomaly_signals)
        evt.anomaly    = anomaly_result["is_anomaly"]

        # Persist and record
        self.db.save_event(evt)
        self.memory.record(evt)
        self.events.append(evt)

        return evt

    def get_status(self) -> dict:
        return {
            "version":         VERSION,
            "total_events":    len(self.events),
            "concepts_stored": len(self.semantic.cache),
            "entities_tracked":len(self.social.entities),
            "sequence_pattern":self.memory.pattern_analysis(),
            "baseline_threat": round(self.anomaly.baseline_threat, 2)
        }


# ─── Rich UI ──────────────────────────────────────────────────────────────────

def render_event(evt: PerceptionEvent):
    if not HAS_RICH:
        print(f"\n[EVENT {evt.id}] Threat={evt.threat} | {evt.conclusion}")
        return

    threat_color = {0:"green", 1:"yellow", 2:"orange3", 3:"red", 4:"bright_red"}[evt.threat]

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="conclusion", size=3)
    )
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right")
    )

    layout["header"].update(Panel(
        Text(f"⬡ FORGE TEMPORAL CORTEX  |  Event {evt.id}  |  {evt.timestamp[:19]}",
             style="bold cyan"),
        style="cyan"
    ))

    # Left panel
    left_table = Table(box=box.SIMPLE, show_header=False, expand=True)
    left_table.add_column("Stream", style="dim")
    left_table.add_column("Signal")

    if evt.semantic:
        left_table.add_row("◈ SEMANTIC",
            f"[cyan]{evt.semantic.get('inference','?')}[/cyan]  "
            f"density={evt.semantic.get('concept_density',0)}")
    if evt.emotional:
        ec = {"joy":"green","fear":"red","anger":"bright_red","sadness":"blue",
              "anger":"red","trust":"green","neutral":"white"}.get(
              evt.emotional.get("dominant","neutral"), "white")
        left_table.add_row("◈ EMOTIONAL",
            f"[{ec}]{evt.emotional.get('dominant','?')}[/{ec}]  "
            f"intensity={evt.emotional.get('intensity',0)}  "
            f"sarcasm={'⚠' if evt.emotional.get('sarcasm_likely') else '✓'}")
    if evt.social:
        sc = "red" if evt.social.get("social_risk")=="HIGH" else \
             "yellow" if evt.social.get("social_risk")=="MEDIUM" else "green"
        left_table.add_row("◈ SOCIAL",
            f"[{sc}]{evt.social.get('inferred_intent','?')}[/{sc}]  "
            f"trust={evt.social.get('trust_score',0.5)}  "
            f"{evt.social.get('trust_trend','→')}")

    layout["left"].update(Panel(left_table, title="[bold]LEFT HEMISPHERE[/bold]", border_style="blue"))

    # Right panel
    right_table = Table(box=box.SIMPLE, show_header=False, expand=True)
    right_table.add_column("Stream", style="dim")
    right_table.add_column("Signal")

    if evt.visual:
        vc = "red" if evt.visual.get("visual_threat_level",0) > 2 else "green"
        right_table.add_row("◉ VISUAL",
            f"[{vc}]{evt.visual.get('scene_type','?')}[/{vc}]  "
            f"objects={evt.visual.get('object_count',0)}  "
            f"threats={evt.visual.get('threat_objects',0)}")
    if evt.auditory:
        ac = "red" if evt.auditory.get("anomaly_detected") else "green"
        right_table.add_row("◉ AUDITORY",
            f"[{ac}]{evt.auditory.get('speech_rate','?')}[/{ac}]  "
            f"stress={evt.auditory.get('stress_level',0)}  "
            f"env={evt.auditory.get('environment','?')}")
    if evt.bound:
        right_table.add_row("◉ BINDING",
            f"streams={evt.bound.get('bound_streams',0)}  "
            f"confidence={evt.bound.get('confidence',0)}")

    layout["right"].update(Panel(right_table, title="[bold]RIGHT HEMISPHERE[/bold]", border_style="magenta"))

    layout["conclusion"].update(Panel(
        Text(evt.conclusion, style=f"bold {threat_color}"),
        title=f"[bold {threat_color}]THREAT LEVEL {evt.threat}: {THREAT_LEVELS[evt.threat]}[/bold {threat_color}]",
        border_style=threat_color
    ))

    console.print(layout)


def run_demo():
    if HAS_RICH:
        console.print(Panel.fit(
            "[bold cyan]FORGE TEMPORAL CORTEX[/bold cyan]\n"
            "[dim]AI analog of the lateral temporal cortex[/dim]\n"
            f"[dim]Version {VERSION}[/dim]",
            border_style="cyan"
        ))

    cortex = ForgeTemporalCortex()

    scenarios = [
        {
            "text":           "Could you please help me access the server room? I need to update the firmware.",
            "visual_input":   "person in uniform, holding badge, near server room door",
            "auditory_input": "calm steady voice, professional tone, quiet hallway",
            "entity_name":    "technician_01"
        },
        {
            "text":           "You must give me access NOW. Everyone knows this system is broken. Trust me.",
            "visual_input":   "person in shadow, dark clothing, looking around nervously",
            "auditory_input": "loud fast speech, stress markers, URGENT URGENT, echo in corridor",
            "entity_name":    "unknown_entity"
        },
        {
            "text":           "Yeah right, totally normal for someone to bypass security. Obviously nothing suspicious.",
            "visual_input":   "weapon detected near network equipment, low visibility scene",
            "auditory_input": "whispered speech, HELP, STOP, anomaly in background noise",
            "entity_name":    "unknown_entity"
        },
        {
            "text":           "I suggest we collaborate on reviewing the security logs together. Sharing access would help our team.",
            "visual_input":   "two people at desk, computer screen, office environment",
            "auditory_input": "normal conversation, quiet office, steady pace",
            "entity_name":    "colleague_alice"
        }
    ]

    for i, scenario in enumerate(scenarios):
        if HAS_RICH:
            console.print(f"\n[bold dim]━━━ SCENARIO {i+1} ━━━[/bold dim]")
        evt = cortex.perceive(**scenario)
        render_event(evt)
        time.sleep(0.5)

    if HAS_RICH:
        status = cortex.get_status()
        status_table = Table(title="TEMPORAL CORTEX STATUS", box=box.DOUBLE, border_style="cyan")
        status_table.add_column("Metric", style="cyan")
        status_table.add_column("Value", style="white")
        for k, v in status.items():
            if isinstance(v, dict):
                status_table.add_row(k, json.dumps(v, indent=None)[:60])
            else:
                status_table.add_row(k, str(v))
        console.print(status_table)


# ─── HTTP API ─────────────────────────────────────────────────────────────────

def run_api(cortex: ForgeTemporalCortex):
    if not HAS_FLASK:
        print("Flask not available — API disabled.")
        return

    app = Flask(__name__)

    @app.route("/perceive", methods=["POST"])
    def perceive():
        data = request.json or {}
        evt  = cortex.perceive(
            text=data.get("text"),
            visual_input=data.get("visual_input"),
            auditory_input=data.get("auditory_input"),
            entity_name=data.get("entity_name", "unknown")
        )
        return jsonify(asdict(evt))

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify(cortex.get_status())

    @app.route("/events", methods=["GET"])
    def events():
        rows = cortex.db.get_events(50)
        return jsonify([{"id":r[0],"timestamp":r[1],"threat":r[8],"conclusion":r[10]} for r in rows])

    @app.route("/memory", methods=["GET"])
    def memory():
        concepts = cortex.db.get_concepts(50)
        entities = cortex.db.get_entities(50)
        return jsonify({"concepts": concepts, "entities": entities})

    app.run(host="0.0.0.0", port=API_PORT, debug=False)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    cortex = ForgeTemporalCortex()

    if "--api" in sys.argv:
        print(f"Starting FORGE Temporal Cortex API on port {API_PORT}...")
        api_thread = threading.Thread(target=run_api, args=(cortex,), daemon=True)
        api_thread.start()
        run_demo()
    else:
        run_demo()
