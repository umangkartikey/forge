"""
FORGE Bridge — forge_bridge.py
================================
Bidirectional pipeline connecting forge_temporal.py ↔ forge_social.py

The bridge makes perception and social intelligence symbiotic:
  forge_temporal perceives → bridge pushes entity signal to forge_social
  forge_social knows history → bridge pulls context back into perception

Pipeline:
  TemporalSocialPipeline
    ├── push()   → temporal perception event → social graph update
    ├── pull()   → entity name → full social history context
    ├── sync()   → bidirectional real-time feedback loop
    └── enrich() → augments raw perception with social memory

This module can run standalone (demo) or be imported by either module.
"""

import json
import time
import uuid
import sqlite3
import threading
import hashlib
from datetime import datetime
from collections import defaultdict, deque
from typing import Optional
from dataclasses import dataclass, field

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.layout import Layout
    from rich.text import Text
    from rich.columns import Columns
    from rich.rule import Rule
    from rich.arrow import Arrow
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

DB_PATH  = "forge_bridge.db"
API_PORT = 7781
VERSION  = "1.0.0"

# Trust dynamics
TRUST_GAIN_COOPERATIVE  =  0.08
TRUST_LOSS_COERCIVE     = -0.12
TRUST_LOSS_INTRUSION    = -0.25
TRUST_LOSS_THREAT       = -0.18
TRUST_GAIN_COLLABORATIVE=  0.05

INTENT_TRUST_DELTA = {
    "COOPERATIVE_REQUEST":    TRUST_GAIN_COOPERATIVE,
    "COLLABORATIVE_SUGGESTION": TRUST_GAIN_COLLABORATIVE,
    "NEUTRAL_INTERACTION":    0.0,
    "COERCIVE_DEMAND":        TRUST_LOSS_COERCIVE,
    "INTRUSION_ATTEMPT":      TRUST_LOSS_INTRUSION,
}

console = Console() if HAS_RICH else None

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class SocialSignal:
    """Extracted from forge_temporal, pushed to forge_social."""
    id:            str  = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:     str  = field(default_factory=lambda: datetime.now().isoformat())
    entity:        str  = "unknown"
    intent:        str  = "NEUTRAL_INTERACTION"
    threat_level:  int  = 0
    emotion:       str  = "neutral"
    trust_delta:   float = 0.0
    location:      str  = ""
    anomaly:       bool = False
    raw_conclusion: str = ""
    keywords:      list = field(default_factory=list)
    source_event:  str  = ""   # forge_temporal event ID

@dataclass
class SocialContext:
    """Pulled from forge_social, fed back into forge_temporal."""
    entity:            str   = "unknown"
    known:             bool  = False
    trust_score:       float = 0.5
    trust_trend:       str   = "→"
    total_interactions: int  = 0
    threat_history:    list  = field(default_factory=list)
    avg_threat:        float = 0.0
    max_threat:        int   = 0
    known_associates:  list  = field(default_factory=list)
    community:         str   = "unknown"
    risk_label:        str   = "UNKNOWN"
    last_seen:         str   = ""
    behavior_pattern:  str   = "INSUFFICIENT_DATA"
    enrichment_notes:  list  = field(default_factory=list)

@dataclass
class BridgeEvent:
    """Audit record of every bridge transaction."""
    id:          str  = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:   str  = field(default_factory=lambda: datetime.now().isoformat())
    direction:   str  = ""    # PUSH | PULL | SYNC | ENRICH
    entity:      str  = ""
    signal:      dict = field(default_factory=dict)
    context:     dict = field(default_factory=dict)
    latency_ms:  float = 0.0
    enriched:    bool = False

# ─── Bridge Database ──────────────────────────────────────────────────────────

class BridgeDB:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init()

    def _init(self):
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS social_signals (
                    id TEXT PRIMARY KEY, timestamp TEXT, entity TEXT,
                    intent TEXT, threat_level INTEGER, emotion TEXT,
                    trust_delta REAL, location TEXT, anomaly INTEGER,
                    raw_conclusion TEXT, keywords TEXT, source_event TEXT
                );
                CREATE TABLE IF NOT EXISTS entity_profiles (
                    entity TEXT PRIMARY KEY, trust_score REAL,
                    total_interactions INTEGER, avg_threat REAL,
                    max_threat INTEGER, community TEXT,
                    last_seen TEXT, behavior_pattern TEXT,
                    threat_history TEXT, known_associates TEXT
                );
                CREATE TABLE IF NOT EXISTS bridge_events (
                    id TEXT PRIMARY KEY, timestamp TEXT, direction TEXT,
                    entity TEXT, signal TEXT, context TEXT,
                    latency_ms REAL, enriched INTEGER
                );
                CREATE TABLE IF NOT EXISTS relationship_edges (
                    id TEXT PRIMARY KEY, entity_a TEXT, entity_b TEXT,
                    weight REAL, interaction_count INTEGER,
                    last_interaction TEXT, edge_type TEXT
                );
            """)
            self.conn.commit()

    def upsert_profile(self, entity: str, trust_score: float, threat: int,
                       intent: str, location: str, associates: list):
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM entity_profiles WHERE entity=?", (entity,)
            ).fetchone()

            if row:
                old_trust   = row[1]
                total       = row[2] + 1
                avg_threat  = round((row[3] * row[2] + threat) / total, 3)
                max_threat  = max(row[4], threat)
                history     = json.loads(row[8]) if row[8] else []
                history.append({"threat": threat, "intent": intent,
                                "time": datetime.now().isoformat()})
                history     = history[-50:]  # keep last 50
                known_assoc = list(set(json.loads(row[9] or "[]") + associates))[:20]
                pattern     = self._behavior_pattern(history)
                community   = row[6]

                self.conn.execute("""
                    UPDATE entity_profiles SET
                        trust_score=?, total_interactions=?, avg_threat=?,
                        max_threat=?, last_seen=?, behavior_pattern=?,
                        threat_history=?, known_associates=?
                    WHERE entity=?
                """, (trust_score, total, avg_threat, max_threat,
                      datetime.now().isoformat(), pattern,
                      json.dumps(history), json.dumps(known_assoc), entity))
            else:
                history = [{"threat": threat, "intent": intent,
                           "time": datetime.now().isoformat()}]
                self.conn.execute("""
                    INSERT INTO entity_profiles VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (entity, trust_score, 1, float(threat), threat,
                      "unknown", datetime.now().isoformat(),
                      self._behavior_pattern(history),
                      json.dumps(history), json.dumps(associates)))
            self.conn.commit()

    def _behavior_pattern(self, history: list) -> str:
        if len(history) < 2: return "INSUFFICIENT_DATA"
        threats = [h["threat"] for h in history]
        intents = [h["intent"] for h in history]
        if all(t == 0 for t in threats):         return "CONSISTENTLY_BENIGN"
        if threats[-1] > threats[0]:              return "ESCALATING"
        if threats[-1] < threats[0]:              return "DE_ESCALATING"
        if intents.count("INTRUSION_ATTEMPT") > 1: return "REPEAT_OFFENDER"
        if intents.count("COOPERATIVE_REQUEST") > len(intents)//2: return "COOPERATIVE"
        return "MIXED_SIGNALS"

    def get_profile(self, entity: str) -> Optional[dict]:
        with self.lock:
            row = self.conn.execute(
                "SELECT * FROM entity_profiles WHERE entity=?", (entity,)
            ).fetchone()
            if not row: return None
            return {
                "entity": row[0], "trust_score": row[1],
                "total_interactions": row[2], "avg_threat": row[3],
                "max_threat": row[4], "community": row[5],
                "last_seen": row[6], "behavior_pattern": row[7],
                "threat_history": json.loads(row[8] or "[]"),
                "known_associates": json.loads(row[9] or "[]")
            }

    def save_signal(self, s: SocialSignal):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO social_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (s.id, s.timestamp, s.entity, s.intent, s.threat_level,
                  s.emotion, s.trust_delta, s.location, int(s.anomaly),
                  s.raw_conclusion, json.dumps(s.keywords), s.source_event))
            self.conn.commit()

    def save_bridge_event(self, be: BridgeEvent):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO bridge_events VALUES (?,?,?,?,?,?,?,?)
            """, (be.id, be.timestamp, be.direction, be.entity,
                  json.dumps(be.signal), json.dumps(be.context),
                  be.latency_ms, int(be.enriched)))
            self.conn.commit()

    def upsert_edge(self, entity_a: str, entity_b: str, edge_type: str = "co-occurrence"):
        with self.lock:
            edge_id = hashlib.md5(f"{min(entity_a,entity_b)}{max(entity_a,entity_b)}".encode()).hexdigest()[:8]
            row = self.conn.execute(
                "SELECT * FROM relationship_edges WHERE id=?", (edge_id,)
            ).fetchone()
            if row:
                self.conn.execute("""
                    UPDATE relationship_edges SET
                        weight=?, interaction_count=?, last_interaction=?
                    WHERE id=?
                """, (min(10.0, row[3] + 0.5), row[4]+1,
                      datetime.now().isoformat(), edge_id))
            else:
                self.conn.execute("""
                    INSERT INTO relationship_edges VALUES (?,?,?,?,?,?,?)
                """, (edge_id, entity_a, entity_b, 1.0, 1,
                      datetime.now().isoformat(), edge_type))
            self.conn.commit()

    def get_associates(self, entity: str, limit=10) -> list:
        with self.lock:
            rows = self.conn.execute("""
                SELECT entity_b, weight, interaction_count FROM relationship_edges
                WHERE entity_a=?
                UNION
                SELECT entity_a, weight, interaction_count FROM relationship_edges
                WHERE entity_b=?
                ORDER BY weight DESC LIMIT ?
            """, (entity, entity, limit)).fetchall()
            return [{"entity": r[0], "weight": r[1], "interactions": r[2]} for r in rows]

    def get_all_profiles(self, limit=50):
        with self.lock:
            return self.conn.execute("""
                SELECT entity, trust_score, total_interactions, avg_threat,
                       max_threat, behavior_pattern, last_seen
                FROM entity_profiles ORDER BY total_interactions DESC LIMIT ?
            """, (limit,)).fetchall()

    def get_bridge_events(self, limit=100):
        with self.lock:
            return self.conn.execute("""
                SELECT id, timestamp, direction, entity, latency_ms, enriched
                FROM bridge_events ORDER BY timestamp DESC LIMIT ?
            """, (limit,)).fetchall()

# ─── Signal Extractor ─────────────────────────────────────────────────────────

class SignalExtractor:
    """
    Extracts a clean SocialSignal from a raw forge_temporal PerceptionEvent.
    Handles missing fields gracefully.
    """

    def extract(self, perception: dict) -> SocialSignal:
        social   = perception.get("social") or {}
        emotional= perception.get("emotional") or {}
        semantic = perception.get("semantic") or {}
        visual   = perception.get("visual") or {}
        auditory = perception.get("auditory") or {}
        bound    = perception.get("bound") or {}

        entity  = (social.get("entity") or
                   perception.get("entity_name") or
                   "unknown")
        intent  = social.get("inferred_intent", "NEUTRAL_INTERACTION")
        threat  = perception.get("threat", bound.get("threat_level", 0))
        emotion = emotional.get("dominant", "neutral")
        location= visual.get("scene_type") or auditory.get("environment") or ""
        anomaly = perception.get("anomaly", False)
        conclusion = perception.get("conclusion", bound.get("conclusion", ""))

        keywords = list(semantic.get("keywords") or [])
        if emotion not in ["neutral"] and emotion not in keywords:
            keywords.append(emotion)

        trust_delta = INTENT_TRUST_DELTA.get(intent, 0.0)
        if threat >= 3: trust_delta = min(trust_delta, TRUST_LOSS_THREAT)

        return SocialSignal(
            entity=entity, intent=intent, threat_level=threat,
            emotion=emotion, trust_delta=trust_delta,
            location=location, anomaly=anomaly,
            raw_conclusion=conclusion[:120],
            keywords=keywords[:10],
            source_event=perception.get("id", "")
        )


# ─── Context Builder ──────────────────────────────────────────────────────────

class ContextBuilder:
    """
    Builds a SocialContext from the entity profile stored in BridgeDB.
    This is what gets fed BACK into forge_temporal to enrich perception.
    """

    def build(self, entity: str, db: BridgeDB,
              current_signal: SocialSignal) -> SocialContext:
        profile = db.get_profile(entity)
        associates = db.get_associates(entity)

        if not profile:
            return SocialContext(
                entity=entity, known=False,
                trust_score=0.5,
                risk_label="UNKNOWN",
                enrichment_notes=["First encounter — no prior history."]
            )

        trust = max(0.0, min(1.0, profile["trust_score"] + current_signal.trust_delta))
        risk  = ("HIGH"   if trust < 0.3 else
                 "MEDIUM" if trust < 0.6 else "LOW")

        # Trust trend
        history = profile["threat_history"]
        if len(history) >= 2:
            recent = history[-3:]
            older  = history[:-3] or history
            trend  = ("↑" if sum(h["threat"] for h in recent) <
                              sum(h["threat"] for h in older)
                      else "↓" if sum(h["threat"] for h in recent) >
                              sum(h["threat"] for h in older)
                      else "→")
        else:
            trend = "→"

        # Build enrichment notes — this is the intelligence fed back to temporal
        notes = []
        if profile["total_interactions"] > 1:
            notes.append(f"Seen {profile['total_interactions']} times. Pattern: {profile['behavior_pattern']}.")
        if profile["max_threat"] >= 3:
            notes.append(f"⚠ Previously reached threat={profile['max_threat']}.")
        if profile["behavior_pattern"] == "REPEAT_OFFENDER":
            notes.append("🔴 REPEAT OFFENDER — multiple intrusion attempts recorded.")
        if profile["behavior_pattern"] == "ESCALATING":
            notes.append("📈 Behavior ESCALATING — threat trend rising.")
        if profile["behavior_pattern"] == "CONSISTENTLY_BENIGN":
            notes.append("✓ Consistently benign across all interactions.")
        if associates:
            assoc_names = [a["entity"] for a in associates[:3]]
            notes.append(f"Known associates: {', '.join(assoc_names)}.")
        if not notes:
            notes.append("Insufficient interaction history for pattern analysis.")

        return SocialContext(
            entity=entity, known=True,
            trust_score=round(trust, 3),
            trust_trend=trend,
            total_interactions=profile["total_interactions"],
            threat_history=history[-5:],
            avg_threat=profile["avg_threat"],
            max_threat=profile["max_threat"],
            known_associates=[a["entity"] for a in associates[:5]],
            community=profile["community"],
            risk_label=risk,
            last_seen=profile["last_seen"],
            behavior_pattern=profile["behavior_pattern"],
            enrichment_notes=notes
        )


# ─── Enrichment Engine ────────────────────────────────────────────────────────

class EnrichmentEngine:
    """
    Takes a raw perception event and augments it with social context.
    This is the feedback loop — social history sharpens temporal perception.

    Before enrichment: "unknown entity, intent=COERCIVE_DEMAND, threat=2"
    After enrichment:  "unknown_x, seen 4x, REPEAT_OFFENDER, max_threat=4,
                        associates with known threat actor — escalate threat to 3"
    """

    def enrich(self, perception: dict, context: SocialContext) -> dict:
        enriched = dict(perception)
        adjustments = []

        # Threat adjustment based on history
        current_threat = perception.get("threat", 0)
        if context.known:
            if context.max_threat >= 3 and current_threat < context.max_threat:
                new_threat = min(4, current_threat + 1)
                enriched["threat"] = new_threat
                adjustments.append(
                    f"Threat elevated {current_threat}→{new_threat} "
                    f"(prior max={context.max_threat})"
                )

            if context.behavior_pattern == "REPEAT_OFFENDER":
                enriched["threat"] = min(4, enriched.get("threat", 0) + 1)
                adjustments.append("Threat +1 for REPEAT_OFFENDER pattern")

            if context.behavior_pattern == "CONSISTENTLY_BENIGN" and current_threat <= 1:
                adjustments.append("Trust confirmed — consistent benign history")

        # Inject social context into perception
        enriched["social_context"] = {
            "known":            context.known,
            "trust_score":      context.trust_score,
            "trust_trend":      context.trust_trend,
            "risk_label":       context.risk_label,
            "behavior_pattern": context.behavior_pattern,
            "total_interactions": context.total_interactions,
            "max_threat":       context.max_threat,
            "known_associates": context.known_associates,
            "enrichment_notes": context.enrichment_notes,
            "adjustments":      adjustments
        }

        # Update conclusion with social intelligence
        if adjustments:
            original = enriched.get("conclusion", "")
            enriched["conclusion"] = (
                f"{original} [BRIDGE: {'; '.join(adjustments)}]"
            )

        enriched["bridge_enriched"] = True
        return enriched


# ─── Temporal-Social Pipeline ─────────────────────────────────────────────────

class TemporalSocialPipeline:
    """
    The core bridge.

    push()   → temporal event → extract signal → update social profile
    pull()   → entity name   → get social context
    enrich() → temporal event → augment with social memory
    sync()   → push + pull + enrich in one atomic operation
    """

    def __init__(self):
        self.db        = BridgeDB()
        self.extractor = SignalExtractor()
        self.builder   = ContextBuilder()
        self.enricher  = EnrichmentEngine()
        self.event_log: deque = deque(maxlen=500)
        self._stats    = defaultdict(int)

    def push(self, perception: dict) -> SocialSignal:
        """forge_temporal → forge_social: update social profile."""
        t0     = time.time()
        signal = self.extractor.extract(perception)
        self.db.save_signal(signal)

        # Update entity profile
        self.db.upsert_profile(
            entity=signal.entity,
            trust_score=max(0.0, min(1.0, 0.5 + signal.trust_delta)),
            threat=signal.threat_level,
            intent=signal.intent,
            location=signal.location,
            associates=[]
        )

        # Record bridge event
        latency = (time.time() - t0) * 1000
        be = BridgeEvent(
            direction="PUSH", entity=signal.entity,
            signal={"intent": signal.intent, "threat": signal.threat_level,
                    "trust_delta": signal.trust_delta},
            latency_ms=round(latency, 2)
        )
        self.db.save_bridge_event(be)
        self.event_log.append(be)
        self._stats["pushes"] += 1
        return signal

    def pull(self, entity: str, current_signal: Optional[SocialSignal] = None) -> SocialContext:
        """forge_social → forge_temporal: retrieve social context."""
        t0 = time.time()

        if current_signal is None:
            current_signal = SocialSignal(entity=entity)

        context = self.builder.build(entity, self.db, current_signal)

        latency = (time.time() - t0) * 1000
        be = BridgeEvent(
            direction="PULL", entity=entity,
            context={"known": context.known, "risk": context.risk_label,
                     "trust": context.trust_score, "pattern": context.behavior_pattern},
            latency_ms=round(latency, 2)
        )
        self.db.save_bridge_event(be)
        self.event_log.append(be)
        self._stats["pulls"] += 1
        return context

    def enrich(self, perception: dict) -> dict:
        """Augment perception with full social history."""
        t0      = time.time()
        signal  = self.extractor.extract(perception)
        context = self.builder.build(signal.entity, self.db, signal)
        enriched= self.enricher.enrich(perception, context)

        latency = (time.time() - t0) * 1000
        be = BridgeEvent(
            direction="ENRICH", entity=signal.entity,
            signal={"threat_before": perception.get("threat", 0),
                    "threat_after":  enriched.get("threat", 0)},
            context={"notes": context.enrichment_notes[:2]},
            latency_ms=round(latency, 2), enriched=True
        )
        self.db.save_bridge_event(be)
        self.event_log.append(be)
        self._stats["enrichments"] += 1
        return enriched

    def sync(self, perception: dict) -> tuple[dict, SocialSignal, SocialContext]:
        """
        Full bidirectional sync — the complete feedback loop.
        1. Push: update social profile with new perception
        2. Pull: get full social context for this entity
        3. Enrich: augment perception with social memory
        Returns enriched_perception, signal, context
        """
        t0 = time.time()

        # Step 1: Push
        signal = self.push(perception)

        # Step 2: Pull (now includes the just-pushed data)
        context = self.pull(signal.entity, signal)

        # Step 3: Enrich
        enriched = self.enricher.enrich(perception, context)

        latency = (time.time() - t0) * 1000
        be = BridgeEvent(
            direction="SYNC", entity=signal.entity,
            signal={"intent": signal.intent, "threat": signal.threat_level},
            context={"risk": context.risk_label, "pattern": context.behavior_pattern,
                     "known": context.known, "notes": len(context.enrichment_notes)},
            latency_ms=round(latency, 2), enriched=True
        )
        self.db.save_bridge_event(be)
        self.event_log.append(be)
        self._stats["syncs"] += 1

        return enriched, signal, context

    def link_entities(self, entity_a: str, entity_b: str, edge_type: str = "co-occurrence"):
        """Register a relationship between two entities."""
        self.db.upsert_edge(entity_a, entity_b, edge_type)

    def get_stats(self) -> dict:
        return {
            "version":         VERSION,
            "pushes":          self._stats["pushes"],
            "pulls":           self._stats["pulls"],
            "enrichments":     self._stats["enrichments"],
            "syncs":           self._stats["syncs"],
            "total_events":    sum(self._stats.values()),
            "entities_tracked":len(self.db.get_all_profiles()),
            "bridge_events":   len(self.db.get_bridge_events())
        }


# ─── Rich UI ──────────────────────────────────────────────────────────────────

def render_sync(enriched: dict, signal: SocialSignal,
                context: SocialContext, cycle: int):
    if not HAS_RICH:
        print(f"\n[SYNC {cycle}] {signal.entity} | {signal.intent} | "
              f"threat={signal.threat_level} | risk={context.risk_label}")
        return

    threat_before = enriched.get("social_context", {}).get("adjustments") and \
                    signal.threat_level
    threat_after  = enriched.get("threat", signal.threat_level)
    threat_color  = {0:"green",1:"blue",2:"yellow",3:"red",4:"bright_red"}.get(threat_after,"white")
    risk_color    = {"LOW":"green","MEDIUM":"yellow","HIGH":"red","UNKNOWN":"dim"}.get(context.risk_label,"white")

    console.print(Rule(
        f"[bold cyan]⬡ FORGE BRIDGE[/bold cyan]  "
        f"[dim]Sync #{cycle}  {signal.id}[/dim]"
    ))

    # Push panel
    push_panel = Panel(
        f"[bold]Entity:[/bold]  [cyan]{signal.entity}[/cyan]\n"
        f"[bold]Intent:[/bold]  {signal.intent}\n"
        f"[bold]Threat:[/bold]  [{threat_color}]{signal.threat_level}[/{threat_color}]\n"
        f"[bold]Emotion:[/bold] {signal.emotion}\n"
        f"[bold]Δ Trust:[/bold] [{'green' if signal.trust_delta >= 0 else 'red'}]"
        f"{'+' if signal.trust_delta >= 0 else ''}{signal.trust_delta:.2f}"
        f"[/{'green' if signal.trust_delta >= 0 else 'red'}]\n"
        f"[bold]Keywords:[/bold] [dim]{', '.join(signal.keywords[:4])}[/dim]",
        title="[bold blue]▶ PUSH  temporal→social[/bold blue]",
        border_style="blue"
    )

    # Pull panel
    known_str = "[green]✓ KNOWN[/green]" if context.known else "[dim]? FIRST ENCOUNTER[/dim]"
    pull_panel = Panel(
        f"[bold]Known:[/bold]    {known_str}\n"
        f"[bold]Trust:[/bold]    {context.trust_score:.3f} {context.trust_trend}\n"
        f"[bold]Risk:[/bold]     [{risk_color}]{context.risk_label}[/{risk_color}]\n"
        f"[bold]Seen:[/bold]     {context.total_interactions}× interactions\n"
        f"[bold]Pattern:[/bold]  {context.behavior_pattern}\n"
        f"[bold]Max threat:[/bold] {context.max_threat}",
        title="[bold magenta]◀ PULL  social→temporal[/bold magenta]",
        border_style="magenta"
    )
    console.print(Columns([push_panel, pull_panel]))

    # Enrichment notes
    if context.enrichment_notes:
        notes_text = "\n".join(f"  • {n}" for n in context.enrichment_notes)
        adjustments = enriched.get("social_context", {}).get("adjustments", [])
        adj_text = ""
        if adjustments:
            adj_text = "\n[bold yellow]Adjustments:[/bold yellow]\n"
            adj_text += "\n".join(f"  ⚡ {a}" for a in adjustments)

        console.print(Panel(
            notes_text + adj_text,
            title="[bold]ENRICHMENT INTELLIGENCE[/bold]",
            border_style=threat_color
        ))

    # Final enriched conclusion
    console.print(Panel(
        Text(enriched.get("conclusion", "")[:140], style=f"bold {threat_color}"),
        title=f"[bold {threat_color}]ENRICHED CONCLUSION  —  THREAT {threat_after}[/bold {threat_color}]",
        border_style=threat_color
    ))


def render_social_graph(pipeline: TemporalSocialPipeline):
    if not HAS_RICH: return

    console.print(Rule("[bold cyan]⬡ SOCIAL GRAPH — ALL ENTITIES[/bold cyan]"))
    profiles = pipeline.db.get_all_profiles()

    t = Table(box=box.ROUNDED, border_style="cyan")
    t.add_column("Entity",    style="cyan", width=18)
    t.add_column("Trust",     justify="right", width=7)
    t.add_column("Seen",      justify="right", width=6)
    t.add_column("Avg Threat",justify="right", width=10)
    t.add_column("Max",       justify="center",width=5)
    t.add_column("Pattern",   width=22)
    t.add_column("Last Seen", width=20)

    for row in profiles:
        entity, trust, total, avg_t, max_t, pattern, last = row
        trust_color   = "green" if trust > 0.6 else "yellow" if trust > 0.3 else "red"
        threat_color  = "red" if max_t >= 3 else "yellow" if max_t >= 2 else "green"
        pattern_color = {"REPEAT_OFFENDER":"bright_red","ESCALATING":"red",
                         "CONSISTENTLY_BENIGN":"green","COOPERATIVE":"green",
                         "DE_ESCALATING":"yellow","MIXED_SIGNALS":"yellow",
                         "INSUFFICIENT_DATA":"dim"}.get(pattern, "white")
        t.add_row(
            entity,
            f"[{trust_color}]{trust:.2f}[/{trust_color}]",
            str(total),
            f"{avg_t:.1f}",
            f"[{threat_color}]{max_t}[/{threat_color}]",
            f"[{pattern_color}]{pattern}[/{pattern_color}]",
            last[:19] if last else "—"
        )
    console.print(t)


def run_demo():
    if HAS_RICH:
        console.print(Panel.fit(
            "[bold cyan]FORGE BRIDGE[/bold cyan]\n"
            "[dim]forge_temporal.py ↔ forge_social.py[/dim]\n"
            "[dim]Bidirectional Perception-Social Pipeline[/dim]\n"
            f"[dim]Version {VERSION}[/dim]",
            border_style="cyan"
        ))

    pipeline = TemporalSocialPipeline()

    # Simulate a story unfolding over time
    # The bridge learns about entities across multiple encounters

    story = [
        # Alice — trusted technician, appears 3 times
        {
            "name": "Alice — first encounter",
            "perception": {
                "id": "t001", "threat": 0, "anomaly": False,
                "conclusion": "✓ NORMAL — cooperative technician",
                "emotional": {"dominant": "trust", "intensity": 0.3},
                "social":    {"entity": "alice_tech", "inferred_intent": "COOPERATIVE_REQUEST", "trust_score": 0.75},
                "semantic":  {"keywords": ["firmware","update","server","maintenance"]},
                "visual":    {"scene_type": "INDOOR_TECHNICAL"},
                "auditory":  {"environment": "QUIET_SPACE", "anomaly_detected": False}
            }
        },
        # Unknown — first suspicious encounter
        {
            "name": "Unknown_X — first sighting",
            "perception": {
                "id": "t002", "threat": 2, "anomaly": False,
                "conclusion": "⚠ MEDIUM — coercive demand detected",
                "emotional": {"dominant": "fear", "intensity": 0.6},
                "social":    {"entity": "unknown_x", "inferred_intent": "COERCIVE_DEMAND"},
                "semantic":  {"keywords": ["access","override","bypass","now"]},
                "visual":    {"scene_type": "LOW_VISIBILITY"},
                "auditory":  {"environment": "NOISY_ENVIRONMENT", "anomaly_detected": False}
            }
        },
        # Alice — second normal visit (bridge should recognize her)
        {
            "name": "Alice — second visit (bridge enriches)",
            "perception": {
                "id": "t003", "threat": 0, "anomaly": False,
                "conclusion": "✓ NORMAL — routine maintenance",
                "emotional": {"dominant": "trust", "intensity": 0.2},
                "social":    {"entity": "alice_tech", "inferred_intent": "COOPERATIVE_REQUEST"},
                "semantic":  {"keywords": ["server","check","update","firmware"]},
                "visual":    {"scene_type": "INDOOR_TECHNICAL"},
                "auditory":  {"environment": "QUIET_SPACE", "anomaly_detected": False}
            }
        },
        # Unknown_X — escalates to intrusion
        {
            "name": "Unknown_X — escalates to intrusion",
            "perception": {
                "id": "t004", "threat": 3, "anomaly": True,
                "conclusion": "⚡ HIGH — intrusion attempt confirmed",
                "emotional": {"dominant": "anger", "intensity": 0.9},
                "social":    {"entity": "unknown_x", "inferred_intent": "INTRUSION_ATTEMPT"},
                "semantic":  {"keywords": ["breach","network","server","hack","override"]},
                "visual":    {"scene_type": "LOW_VISIBILITY", "threat_objects": 1},
                "auditory":  {"environment": "NOISY_ENVIRONMENT", "anomaly_detected": True}
            }
        },
        # Unknown_X — THIRD encounter (bridge should flag REPEAT_OFFENDER)
        {
            "name": "Unknown_X — repeat attempt (bridge memory kicks in)",
            "perception": {
                "id": "t005", "threat": 2, "anomaly": False,
                "conclusion": "⚠ MEDIUM — suspicious access attempt",
                "emotional": {"dominant": "fear", "intensity": 0.5},
                "social":    {"entity": "unknown_x", "inferred_intent": "INTRUSION_ATTEMPT"},
                "semantic":  {"keywords": ["access","server","bypass"]},
                "visual":    {"scene_type": "LOW_VISIBILITY"},
                "auditory":  {"environment": "NEUTRAL_ENVIRONMENT", "anomaly_detected": False}
            }
        },
        # New entity — associate of unknown_x spotted with them
        {
            "name": "New entity — seen with unknown_x",
            "perception": {
                "id": "t006", "threat": 1, "anomaly": False,
                "conclusion": "ℹ LOW — unknown associate near restricted area",
                "emotional": {"dominant": "surprise", "intensity": 0.4},
                "social":    {"entity": "shadow_agent", "inferred_intent": "NEUTRAL_INTERACTION"},
                "semantic":  {"keywords": ["loitering","entrance","restricted"]},
                "visual":    {"scene_type": "OUTDOOR_PUBLIC"},
                "auditory":  {"environment": "NEUTRAL_ENVIRONMENT", "anomaly_detected": False}
            }
        },
    ]

    for i, scene in enumerate(story):
        if HAS_RICH:
            console.print(f"\n[bold dim]━━━ SCENE {i+1}: {scene['name'].upper()} ━━━[/bold dim]")

        enriched, signal, context = pipeline.sync(scene["perception"])
        render_sync(enriched, signal, context, i+1)
        time.sleep(0.2)

    # Link unknown_x and shadow_agent (co-occurrence relationship)
    pipeline.link_entities("unknown_x", "shadow_agent", edge_type="co-occurrence")

    # Social graph overview
    if HAS_RICH:
        console.print(f"\n")
    render_social_graph(pipeline)

    # Bridge stats
    if HAS_RICH:
        stats = pipeline.get_stats()
        stats_table = Table(title="BRIDGE STATS", box=box.DOUBLE_EDGE, border_style="cyan")
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Value",  style="white")
        for k, v in stats.items():
            stats_table.add_row(k, str(v))
        console.print(stats_table)


# ─── HTTP API ─────────────────────────────────────────────────────────────────

def run_api(pipeline: TemporalSocialPipeline):
    if not HAS_FLASK: return
    app = Flask(__name__)

    @app.route("/push", methods=["POST"])
    def push():
        data = request.json or {}
        signal = pipeline.push(data.get("perception", {}))
        return jsonify({"entity": signal.entity, "intent": signal.intent,
                        "threat": signal.threat_level, "trust_delta": signal.trust_delta})

    @app.route("/pull/<entity>", methods=["GET"])
    def pull(entity):
        ctx = pipeline.pull(entity)
        return jsonify({"entity": ctx.entity, "known": ctx.known,
                        "trust_score": ctx.trust_score, "risk": ctx.risk_label,
                        "pattern": ctx.behavior_pattern, "notes": ctx.enrichment_notes})

    @app.route("/sync", methods=["POST"])
    def sync():
        data = request.json or {}
        enriched, signal, context = pipeline.sync(data.get("perception", {}))
        return jsonify({"enriched_threat": enriched.get("threat"),
                        "conclusion": enriched.get("conclusion", ""),
                        "social_context": enriched.get("social_context", {})})

    @app.route("/enrich", methods=["POST"])
    def enrich():
        data = request.json or {}
        enriched = pipeline.enrich(data.get("perception", {}))
        return jsonify(enriched)

    @app.route("/graph", methods=["GET"])
    def graph():
        profiles = pipeline.db.get_all_profiles()
        return jsonify([{"entity":r[0],"trust":r[1],"interactions":r[2],
                        "avg_threat":r[3],"pattern":r[5]} for r in profiles])

    @app.route("/stats", methods=["GET"])
    def stats():
        return jsonify(pipeline.get_stats())

    app.run(host="0.0.0.0", port=API_PORT, debug=False)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    pipeline = TemporalSocialPipeline()
    if "--api" in sys.argv:
        t = threading.Thread(target=run_api, args=(pipeline,), daemon=True)
        t.start()
    run_demo()
