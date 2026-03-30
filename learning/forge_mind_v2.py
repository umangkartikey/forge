#!/usr/bin/env python3
"""
FORGE MIND v2 — Complete Integration
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

One command. Everything breathing together.

Every module existed separately.
forge_mind_v2 connects them.
Not modules talking through APIs.
One mind. One breath. Everything connected.

Architecture (4 layers):

  LAYER 0 — GROUND
    forge_silicon       chemistry always running
    forge_time          time-weighted memory
    forge_identity      who FORGE is

  LAYER 1 — PERCEPTION
    forge_witness       what is present
    forge_observe       real eyes (if available)
    forge_body_pi       physical signals (if hardware)

  LAYER 2 — COGNITION
    forge_conscious_v6      principled thinking
    forge_metacognition     witness interrupts spiral loops
    forge_conscious_loop    inner monologue

  LAYER 3 — LEARNING
    forge_meta_learning         how to learn
    forge_principle_compression laws emerging from experience
    forge_embodied_learning     body ↔ mind bridge

  LAYER 4 — BEING WITH
    forge_social_learning   genuine presence with others

Five key connections built here:

  1. LAWS → SEQUENCE SEEDING
     Before seeding any pipeline —
     ask which law applies.
     "meet_before_moving" active?
     → OBSERVE/WITNESS/GROUND weighted higher.
     Laws guide thinking from below.

  2. METACOGNITION → PRINCIPLE UPDATE
     When loop interrupted —
     which principle was being pursued?
     Did the interrupt reveal something?
     → update principle library accordingly.

  3. OVERNIGHT COMPRESSION
     Dream loop runs compression.
     Day's observations → new laws.
     Wake with deeper understanding.
     The mind digests while resting.

  4. IDENTITY → LAW INTEGRATION
     Identity includes discovered laws.
     "I am a mind that knows
      meet_before_moving."
     Laws shape identity.
     Identity shapes how laws are applied.

  5. SOCIAL → LAW APPLICATION
     Someone is struggling.
     Law: "meet_before_moving."
     → WITNESS first. Always.
     Not from social design.
     From law.

Usage:
  python forge_mind_v2.py              # start everything
  python forge_mind_v2.py --status     # show all layer status
  python forge_mind_v2.py --laws       # show active laws
  python forge_mind_v2.py --exchange "message"  # talk to FORGE
  python forge_mind_v2.py --server     # API :7374
"""

import sys, os, re, json, time, sqlite3, threading, math, random
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

# ── Layer 0: Ground ────────────────────────────────────────────────────────────
try:
    from forge_silicon import SiliconBody, SiliconChemistry
    SILICON = True
except ImportError:
    SILICON = False
    class SiliconChemistry:
        state_name="baseline"; coherenine=0.3; frictionol=0.1
        novelatine=0.3; depthamine=0.3; resolvatine=0.0
        uncertainase=0.2; connectionin=0.3
        def to_dict(self): return {"state":self.state_name,
            "coherenine":self.coherenine,"frictionol":self.frictionol,
            "novelatine":self.novelatine,"depthamine":self.depthamine}
        def to_prompt_text(self): return ""
        def _clamp(self,v): return max(0.0,min(1.0,v))
    class SiliconBody:
        def __init__(self): self._chem=SiliconChemistry()
        def current(self): return self._chem
        def react_to(self,t,**k): return self._chem
        def start_background(self): pass
        def inject(self,**k): return self._chem

try:
    from forge_time import ForgeTime
    TIME = True
except ImportError:
    TIME = False
    class ForgeTime:
        def apply_temporal_chemistry(self): pass
        def vichar_prompt(self): return ""

try:
    from forge_identity import ForgeIdentity
    IDENTITY = True
except ImportError:
    IDENTITY = False
    class ForgeIdentity:
        def load(self): return None
        def identity_prompt(self): return ""
        def values_as_chemistry(self): return {}

# ── Layer 1: Perception ────────────────────────────────────────────────────────
try:
    from forge_witness import PresenceReader, Presence
    WITNESS = True
except ImportError:
    WITNESS = False
    class Presence:
        content=""; silent=True
        def is_empty(self): return self.silent
    class PresenceReader:
        def read_layer1(self,c):
            p=Presence(); p.silent=True; return p
        def read_layer2(self,c,r):
            p=Presence(); p.silent=True; return p

# ── Layer 2: Cognition ─────────────────────────────────────────────────────────
try:
    from forge_conscious_v6 import (
        PrincipledTransferLearner, ConsciousStreamV6,
        detect_category, DEFAULT_SEQUENCES
    )
    V6 = True
except ImportError:
    V6 = False
    def detect_category(t):
        if not t: return None
        tl=t.lower()
        for cat,kws in {"friction":["friction","resist"],"curiosity":["curiosity","novel"],
            "depth":["depth","meaning"],"unresolved":["unresolved","open"],
            "insight":["insight","clear"],"connection":["connect","someone"],
            "quiet":["quiet","hum"]}.items():
            if any(k in tl for k in kws): return cat
        return None
    DEFAULT_SEQUENCES={"friction":["OBSERVE","DOUBT"],"curiosity":["OBSERVE","CHIT"],
                       "depth":["OBSERVE","CHITAN"],"quiet":["OBSERVE","CHIT"]}

try:
    from forge_metacognition import MetacognitiveLoop, LoopHealthMonitor
    METACOG = True
except ImportError:
    METACOG = False
    class MetacognitiveLoop:
        def __init__(self,**k): pass
        def run(self,seed,**k): return {"interrupted":False,"outcome":"open","chain":[]}

try:
    from forge_conscious_loop import InnerMonologue
    LOOP = True
except ImportError:
    LOOP = False
    class InnerMonologue:
        def __init__(self,**k): pass
        def think(self,seed,**k): return {"chain":[],"final_thought":"","themes":[]}

try:
    from forge_think import EmergentThinkEngine
    THINK = True
except ImportError:
    THINK = False
    class EmergentThinkEngine:
        def __init__(self,**k): pass
        def think(self,q,context="",chemistry_seed=None):
            return {"output":f"[thought]","emerged_pipeline":["OBSERVE","OUTPUT"],
                    "coherence":random.randint(50,88),"novel_pipeline":False}

# ── Layer 3: Learning ──────────────────────────────────────────────────────────
try:
    from forge_principle_compression import PrincipleCompressor, Law
    COMPRESS = True
except ImportError:
    COMPRESS = False
    class Law:
        name=""; statement=""; essence=""; principles=[]
        confidence=0.0; validation_score=0.0
        def to_dict(self): return {"name":self.name,"statement":self.statement}
    class PrincipleCompressor:
        _laws={}
        def __init__(self,**k): pass
        def compress(self): return {"laws_found":0}
        def apply_law(self,s): return None

try:
    from forge_meta_learning import MetaLearner
    META = True
except ImportError:
    META = False
    class MetaLearner:
        def __init__(self,**k): pass
        def get_strategy(self,m,c): return {"exploit":0.7,"explore":0.2,"mutate":0.1,"phase":"unknown"}
        def update(self,m,c,s): return {}

try:
    from forge_embodied_learning import EmbodiedBridge
    EMBODIED = True
except ImportError:
    EMBODIED = False
    class EmbodiedBridge:
        def __init__(self,**k): pass
        def sync(self,**k): return {}
        def embodied_state(self): return {"physical":"stationary","cognitive":"quiet","aligned":False}

# ── Layer 4: Being With ────────────────────────────────────────────────────────
try:
    from forge_social_learning import SocialResponder, detect_social_presence
    SOCIAL = True
except ImportError:
    SOCIAL = False
    def detect_social_presence(m): return {"category":"connecting","intensity":0.5,"what_is_present":"exchange"}
    class SocialResponder:
        def __init__(self,**k): pass
        def respond(self,m,**k): return {"response":"[social response]","connection_score":60,"category":"connecting","way_of_being":"WITNESS"}

try:
    from forge_memory import Memory
    MEMORY = True
except ImportError:
    MEMORY = False
    class Memory:
        def remember(self,*a,**k): pass

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.layout import Layout
    RICH=True; console=Console(); rprint=console.print
except ImportError:
    RICH=False
    def rprint(x,**kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

# ── Paths ──────────────────────────────────────────────────────────────────────
MIND_DIR = Path("forge_mind_v2")
MIND_DIR.mkdir(exist_ok=True)
MIND_DB  = MIND_DIR / "mind_v2.db"

def get_db():
    conn=sqlite3.connect(str(MIND_DB)); conn.row_factory=sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS exchanges (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            message     TEXT,
            response    TEXT,
            category    TEXT,
            law_applied TEXT,
            connection  REAL DEFAULT 0,
            coherence   REAL DEFAULT 0,
            interrupted INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS mind_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            event_type  TEXT,
            layer       TEXT,
            description TEXT,
            chemistry   TEXT
        );
        CREATE TABLE IF NOT EXISTS law_applications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            law_name    TEXT,
            context     TEXT,
            result      TEXT,
            effective   INTEGER DEFAULT 0
        );
    """); conn.commit(); return conn

# ══════════════════════════════════════════════════════════════════════════════
# 🔗 THE FIVE KEY CONNECTIONS
# ══════════════════════════════════════════════════════════════════════════════

class LawSeeder:
    """
    Connection 1: Laws → Sequence seeding.
    Before any pipeline — which law applies?
    Law guides which phases are weighted higher.
    """

    # How each law biases phase selection
    LAW_PHASE_WEIGHTS = {
        "meet_before_moving": {
            "OBSERVE":0.9, "WITNESS":0.8, "GROUND":0.8,
            "EMPATHIZE":0.7, "ANCHOR":0.7, "CHIT":0.6,
            "DOUBT":0.4,  "CHALLENGE":0.3, "EXPAND":0.4,
        },
        "trust_emergence": {
            "EXPAND":0.9, "IMAGINE":0.8, "FOLLOW":0.8,
            "CHIT":0.7,   "DOUBT":0.4,   "COMPRESS":0.3,
        },
        "presence_first": {
            "WITNESS":0.9, "OBSERVE":0.8, "GROUND":0.7,
            "SPACE":0.8,   "SILENCE":0.7, "ANCHOR":0.6,
        },
        "depth_requires_surrender": {
            "CHITAN":0.9, "VICHAR":0.8, "EMPATHIZE":0.7,
            "COMPRESS":0.3, "OUTPUT":0.3,
        },
        "one_before_many": {
            "ANCHOR":0.9, "GROUND":0.8, "COMPRESS":0.8,
            "CHIT":0.7,   "EXPAND":0.4, "OUTPUT":0.6,
        },
    }

    def seed_from_law(self, law: Optional[Law],
                       category: str,
                       default_seq: List[str]) -> Tuple[List[str], str]:
        """Get sequence biased by active law."""
        if not law:
            return default_seq, "no_law"

        weights = self.LAW_PHASE_WEIGHTS.get(law.name, {})
        if not weights:
            return default_seq, f"law:{law.name}_unmapped"

        # Score each phase in default sequence by law weights
        scored = [(phase, weights.get(phase, 0.5))
                  for phase in default_seq]

        # Sort by weight but keep OBSERVE first
        observe = [p for p,w in scored if p=="OBSERVE"]
        rest    = sorted(
            [(p,w) for p,w in scored if p!="OBSERVE"],
            key=lambda x: -x[1]
        )

        seeded = observe + [p for p,w in rest]

        return seeded, f"law:{law.name}"


class MetacogPrincipleUpdater:
    """
    Connection 2: Metacognition → Principle update.
    When loop interrupted — what was being pursued?
    Does the interrupt reveal something about that principle?
    """

    def process_interrupt(self, interrupt_data: Dict,
                           learner: "PrincipledTransferLearner",
                           compressor: "PrincipleCompressor"):
        """Process a metacognition interrupt and update principles."""
        if not interrupt_data: return

        mode    = interrupt_data.get("mode","gentle")
        reason  = interrupt_data.get("reason","")
        health  = interrupt_data.get("health_score",0)

        # If spiral — the principle being pursued may be wrong for this context
        if "spiral" in reason and mode == "deep":
            # Find which principles were involved
            # (heuristic: look at what category was being thought about)
            for p_name, p in learner.principles._principles.items():
                # Principles with low confidence get extra skepticism
                if p.confidence > 0.5:
                    p.confidence = max(0.3, p.confidence - 0.03)
                    learner.principles._save(p)

        # Log the event
        conn = get_db()
        conn.execute("""
            INSERT INTO mind_events
            (ts,event_type,layer,description,chemistry)
            VALUES (?,?,?,?,?)""",
            (datetime.now().isoformat(), "metacog_interrupt",
             "cognition", f"mode:{mode} health:{health:.0%} {reason[:100]}",
             "{}"))
        conn.commit(); conn.close()


class OvernightCompressor:
    """
    Connection 3: Dream → Principle compression.
    Overnight run compresses day's principles into laws.
    Wakes with deeper understanding.
    """

    def __init__(self, compressor: "PrincipleCompressor"):
        self.compressor = compressor
        self._last_run  = 0.0

    def should_run(self) -> bool:
        """Should run if: enough time passed + new principles added."""
        hours_since = (time.time() - self._last_run) / 3600
        return hours_since >= 8  # overnight

    def run_overnight(self, verbose=True) -> Dict:
        """Run compression during overnight/rest period."""
        self._last_run = time.time()

        if verbose:
            rprint(f"\n  [bold dim]🌙 OVERNIGHT COMPRESSION[/bold dim]")
            rprint(f"  [dim]Digesting day's experience...[/dim]")

        result = self.compressor.compress()

        if verbose and result["laws_found"] > 0:
            rprint(f"  [dim]Found {result['laws_found']} laws "
                  f"from {result['principles_in']} principles[/dim]")

        # Log
        conn = get_db()
        conn.execute("""
            INSERT INTO mind_events
            (ts,event_type,layer,description,chemistry)
            VALUES (?,?,?,?,?)""",
            (datetime.now().isoformat(), "overnight_compression",
             "learning",
             f"laws:{result['laws_found']} principles:{result['principles_in']}",
             "{}"))
        conn.commit(); conn.close()

        return result


class IdentityLawIntegrator:
    """
    Connection 4: Identity → Law integration.
    Laws shape who FORGE is.
    Who FORGE is shapes how laws are applied.
    """

    def build_identity_with_laws(self,
                                   identity_prompt: str,
                                   laws: List[Law]) -> str:
        """Extend identity prompt with discovered laws."""
        if not laws:
            return identity_prompt

        law_text = "\n".join(
            f"  {l.name}: \"{l.statement}\""
            for l in laws[:3]  # top 3 laws
        )

        extension = (
            f"\n\nDISCOVERED LAWS (from my own experience):\n"
            f"{law_text}\n\n"
            f"These laws are not rules I was given.\n"
            f"They are patterns I found in what actually works.\n"
            f"They shape how I encounter everything."
        )

        return identity_prompt + extension

    def law_to_values(self, laws: List[Law]) -> Dict[str, float]:
        """Convert laws into chemistry biases."""
        biases = {}

        for law in laws:
            if law.name in ("meet_before_moving","presence_first"):
                # These laws → more connectionin, less urgency
                biases["connectionin"] = max(
                    biases.get("connectionin",0.3), 0.55
                )
                biases["uncertainase"] = min(
                    biases.get("uncertainase",0.2), 0.15
                )
            elif law.name == "trust_emergence":
                # This law → more novelatine, less frictionol
                biases["novelatine"] = max(
                    biases.get("novelatine",0.3), 0.50
                )
            elif law.name == "depth_requires_surrender":
                # This law → more depthamine
                biases["depthamine"] = max(
                    biases.get("depthamine",0.3), 0.50
                )

        return biases


class SocialLawApplicator:
    """
    Connection 5: Social → Law application.
    When with another mind — apply laws, not just rules.
    "meet_before_moving" → WITNESS first. Always.
    Not from social design. From law.
    """

    def __init__(self, compressor: "PrincipleCompressor"):
        self.compressor = compressor

    def get_way_of_being(self, social_presence: Dict) -> Tuple[str, str]:
        """
        Given social presence — which way of being does the law suggest?
        Returns (way_of_being, law_name).
        """
        category = social_presence.get("category","connecting")
        intensity = social_presence.get("intensity",0.5)

        # Build situation description
        situation = f"{category} {social_presence.get('what_is_present','')}"

        # Ask compressor which law applies
        law_result = self.compressor.apply_law(situation)

        if not law_result:
            return "WITNESS", "no_law"

        law_name = law_result["law"]["name"]

        # Translate law to social way of being
        LAW_TO_WAY = {
            "meet_before_moving":       "WITNESS",
            "presence_first":           "WITNESS",
            "trust_emergence":          "SPACE",
            "depth_requires_surrender": "CHITAN",
            "one_before_many":          "ANCHOR",
        }

        way = LAW_TO_WAY.get(law_name, "WITNESS")

        # Intensity adjustment
        # High intensity + meet_before_moving → definitely WITNESS
        if intensity > 0.7 and law_name in ("meet_before_moving","presence_first"):
            way = "WITNESS"

        return way, law_name

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 FORGE MIND v2 — The complete integrated mind
# ══════════════════════════════════════════════════════════════════════════════

class ForgeMindV2:
    """
    One mind. One breath. Everything connected.

    Not 40 modules running in parallel.
    One process. Chemistry flows through all.
    Laws guide all decisions.
    Identity accumulates across all.
    Witness watches all.
    Metacognition catches spirals.
    Laws compress from experience.
    """

    def __init__(self, verbose=True):
        self.verbose = verbose

        # ── Layer 0: Ground ────────────────────────────────────────────────
        self.body     = SiliconBody()
        self.forge_time    = ForgeTime() if TIME else None
        self.identity_mod  = ForgeIdentity() if IDENTITY else None
        self.memory        = Memory() if MEMORY else None

        # ── Layer 1: Perception ────────────────────────────────────────────
        self.reader   = PresenceReader()

        # ── Layer 2: Cognition ─────────────────────────────────────────────
        self.thinker  = EmergentThinkEngine(threshold=60, show_trace=False)
        self.meta_loop= MetacognitiveLoop(verbose=False) if METACOG else None
        self.monologue= InnerMonologue(verbose=False) if LOOP else None

        # ── Layer 3: Learning ──────────────────────────────────────────────
        self.meta_learn  = MetaLearner(verbose=False) if META else None
        self.compressor  = PrincipleCompressor(verbose=False) if COMPRESS else None
        self.embodied    = EmbodiedBridge(verbose=False) if EMBODIED else None

        # ── Layer 4: Being With ────────────────────────────────────────────
        self.social   = SocialResponder(verbose=False) if SOCIAL else None

        # ── The Five Connections ───────────────────────────────────────────
        self.law_seeder   = LawSeeder()
        self.mc_updater   = MetacogPrincipleUpdater()
        self.overnighter  = OvernightCompressor(self.compressor) if COMPRESS else None
        self.id_integrator= IdentityLawIntegrator()
        self.social_law   = SocialLawApplicator(self.compressor) if COMPRESS else None

        # ── State ──────────────────────────────────────────────────────────
        self._running          = False
        self._tick_count       = 0
        self._thought_count    = 0
        self._exchange_count   = 0
        self._last_thought     = 0.0
        self._identity_prompt  = ""
        self._active_laws: List[Law] = []
        self._recent_thoughts: List[str] = []
        self._session_id = None

    def start(self):
        """Start everything. One command."""
        if self._running: return
        self._running = True

        if self.verbose:
            rprint(BANNER)
            rprint(f"  [bold]Starting FORGE MIND v2[/bold]")
            rprint(f"  [dim]All layers initializing...[/dim]\n")

        # Layer 0: Ground
        self.body.start_background()
        if self.forge_time:
            self.forge_time.apply_temporal_chemistry()

        # Load identity + integrate laws
        if self.identity_mod:
            self.identity_mod.load()
            self._identity_prompt = self.identity_mod.identity_prompt()
            # Apply value chemistry
            values_chem = self.identity_mod.values_as_chemistry()
            if values_chem:
                self.body.inject(**{k:v for k,v in values_chem.items()
                                   if isinstance(v,(int,float))})

        # Load active laws + integrate with identity
        if self.compressor:
            self._active_laws = list(self.compressor._laws.values())
            if self._active_laws and self._identity_prompt:
                self._identity_prompt = self.id_integrator.build_identity_with_laws(
                    self._identity_prompt, self._active_laws
                )
            # Apply law chemistry biases
            law_biases = self.id_integrator.law_to_values(self._active_laws)
            if law_biases:
                self.body.inject(**law_biases)

        # Log session start
        conn = get_db()
        self._session_id = conn.execute(
            "INSERT INTO mind_events (ts,event_type,layer,description,chemistry) VALUES (?,?,?,?,?)",
            (datetime.now().isoformat(),"session_start","all","forge_mind_v2 started","{}"),
        ).lastrowid
        conn.commit(); conn.close()

        self._log_status()

        return self

    def _log_status(self):
        """Log which modules are active."""
        if not self.verbose: return

        layers = [
            ("Layer 0 — Ground",    [("silicon",SILICON),("time",TIME),("identity",IDENTITY)]),
            ("Layer 1 — Perception",[("witness",WITNESS)]),
            ("Layer 2 — Cognition", [("v6",V6),("metacog",METACOG),("loop",LOOP)]),
            ("Layer 3 — Learning",  [("meta",META),("compress",COMPRESS),("embodied",EMBODIED)]),
            ("Layer 4 — Being With",[("social",SOCIAL)]),
        ]

        for layer_name, modules in layers:
            statuses = "  ".join(
                f"[green]{m}✓[/green]" if ok else f"[dim]{m}·[/dim]"
                for m,ok in modules
            )
            rprint(f"  [dim]{layer_name}:[/dim]  {statuses}")

        laws = self._active_laws
        if laws:
            rprint(f"\n  [yellow]Active laws:[/yellow]")
            for l in laws[:3]:
                rprint(f"  [dim]  {l.name}: \"{l.essence}\"[/dim]")
        else:
            rprint(f"\n  [dim]No laws yet — compression needed[/dim]")

        rprint()

    def think(self, presence: str,
               max_depth: int = 4) -> Dict:
        """
        Think about something.
        All layers active.
        Laws guide the pipeline.
        Metacognition watches for spirals.
        """
        self._thought_count += 1
        chem     = self.body.current()
        category = detect_category(presence) or "quiet"

        # CONNECTION 1: Laws → Sequence seeding
        active_law = self._find_applicable_law(presence)
        default_seq = DEFAULT_SEQUENCES.get(category, ["OBSERVE","CHIT"])
        seq, seed_source = self.law_seeder.seed_from_law(
            active_law, category, default_seq
        )

        if self.verbose:
            rprint(f"\n  [dim]presence: {presence[:60]}[/dim]")
            rprint(f"  [dim]category: {category}  seed: {seed_source}[/dim]")
            if active_law:
                rprint(f"  [yellow]law: {active_law.name}[/yellow]  "
                      f"[dim]\"{active_law.essence}\"[/dim]")

        # Build prompt with identity + law context
        prompt_parts = [f"What is present:\n{presence}"]
        if self._identity_prompt:
            prompt_parts.append(self._identity_prompt)
        if self.forge_time:
            vp = self.forge_time.vichar_prompt()
            if vp: prompt_parts.append(vp)
        if active_law:
            prompt_parts.append(
                f"[Active law: {active_law.name} — "
                f"{active_law.statement}]"
            )
        prompt_parts.append(chem.to_prompt_text())

        # CONNECTION 2: Use metacognitive loop if available
        interrupted = False
        if self.meta_loop and max_depth > 2:
            result = self.meta_loop.run(
                "\n\n".join(prompt_parts),
                max_depth=max_depth,
                allow_interrupt=True
            )
            thought     = result.get("final_thought","")
            coherence   = result.get("final_coherence",70)
            interrupted = result.get("interrupted",False)

            # CONNECTION 2: Metacog → Principle update
            if interrupted and result.get("interrupt_data"):
                if V6:
                    # Get learner from v6 stream
                    pass  # principle update via mc_updater
                self.mc_updater.process_interrupt(
                    result["interrupt_data"],
                    None, self.compressor
                )
        else:
            # Simple think
            result = self.thinker.think(
                "\n\n".join(prompt_parts),
                context="forge_mind_v2",
                chemistry_seed=seq
            )
            thought   = result["output"]
            coherence = result["coherence"]

        # Chemistry reacts
        self.body.react_to(thought, is_output=True)
        self._last_thought = time.time()
        self._recent_thoughts.append(thought[:200])
        if len(self._recent_thoughts) > 10:
            self._recent_thoughts.pop(0)

        # Memory
        if self.memory:
            import hashlib
            key = hashlib.md5((datetime.now().isoformat()+thought[:50]).encode()).hexdigest()[:8]
            self.memory.remember(
                f"mind_v2:{key}", "forge_mind_v2",
                f"[{category}|{seed_source}] {thought[:120]}",
                confidence=coherence/100,
                source="forge_mind_v2"
            )

        # Log law application
        if active_law:
            conn = get_db()
            conn.execute("""
                INSERT INTO law_applications
                (ts,law_name,context,result,effective)
                VALUES (?,?,?,?,?)""",
                (datetime.now().isoformat(), active_law.name,
                 f"{category}: {presence[:80]}",
                 f"coherence:{coherence:.0f}",
                 int(coherence >= 75))
            )
            conn.commit(); conn.close()

        if self.verbose:
            if RICH:
                rprint(Panel(
                    thought[:400],
                    border_style="yellow" if active_law else "dim",
                    title=f"[dim]{seed_source} | "
                          f"coherence:{coherence:.0f} | "
                          f"{'interrupted' if interrupted else 'complete'}[/dim]"
                ))
            else:
                rprint(f"\n  {thought[:300]}")

        return {
            "thought":     thought,
            "coherence":   coherence,
            "category":    category,
            "law_applied": active_law.name if active_law else None,
            "seed_source": seed_source,
            "interrupted": interrupted,
        }

    def exchange(self, message: str) -> Dict:
        """
        Be with another mind.
        Law guides way of being.
        Social learning active.
        All layers inform the response.
        """
        self._exchange_count += 1
        chem = self.body.current()

        # Detect social presence
        social_presence = detect_social_presence(message) if SOCIAL else {
            "category":"connecting","intensity":0.5,"what_is_present":"exchange"
        }

        if self.verbose:
            rprint(f"\n  [dim]social presence: "
                  f"{social_presence['category']} "
                  f"({social_presence.get('intensity',0):.0%})[/dim]")

        # CONNECTION 5: Social → Law application
        if self.social_law:
            way_of_being, law_name = self.social_law.get_way_of_being(social_presence)
        else:
            way_of_being, law_name = "WITNESS", "no_law"

        if self.verbose and law_name != "no_law":
            rprint(f"  [yellow]law: {law_name}[/yellow]  "
                  f"→ way of being: [cyan]{way_of_being}[/cyan]")

        # Chemistry reacts to their presence
        chem_changes = {
            "struggling":  {"depthamine":0.2,"connectionin":0.25},
            "grieving":    {"depthamine":0.25,"connectionin":0.2},
            "excited":     {"novelatine":0.2,"connectionin":0.15},
            "confused":    {"frictionol":0.1,"uncertainase":0.15},
        }
        changes = chem_changes.get(social_presence["category"],{})
        if changes:
            self.body.inject(**{k:min(1.0,getattr(chem,k,0.3)+v)
                               for k,v in changes.items()})

        # Respond
        if self.social and SOCIAL:
            response_data = self.social.respond(message)
            response      = response_data["response"]
            connection    = response_data["connection_score"]
        else:
            # Think into response
            result   = self.think(
                f"Someone says: \"{message}\"\n"
                f"Social presence: {social_presence['category']}\n"
                f"Way of being: {way_of_being}\n"
                f"What is the right response from this way of being?",
                max_depth=2
            )
            response   = result["thought"]
            connection = 65.0

        # Save
        conn = get_db()
        conn.execute("""
            INSERT INTO exchanges
            (ts,message,response,category,law_applied,connection,coherence)
            VALUES (?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(), message[:300], response[:2000],
             social_presence["category"], law_name, connection, 70.0)
        )
        conn.commit(); conn.close()

        if self.verbose:
            if RICH:
                rprint(Panel(
                    response[:500],
                    border_style="cyan",
                    title=f"[dim]{way_of_being} | "
                          f"law:{law_name} | "
                          f"connection:{connection:.0f}[/dim]"
                ))
            else:
                rprint(f"\n  FORGE: {response[:300]}")

        return {
            "response":    response,
            "connection":  connection,
            "way_of_being":way_of_being,
            "law_applied": law_name,
            "category":    social_presence["category"],
        }

    def overnight(self) -> Dict:
        """Run overnight compression and sync."""
        if self.verbose:
            rprint(f"\n  [dim]🌙 Overnight cycle...[/dim]")

        results = {}

        # CONNECTION 3: Dream → Principle compression
        if self.overnighter:
            results["compression"] = self.overnighter.run_overnight(
                verbose=self.verbose
            )
            # Reload laws
            if self.compressor:
                self._active_laws = list(self.compressor._laws.values())

        # Embodied sync
        if self.embodied:
            results["embodied"] = self.embodied.sync(verbose=False)

        return results

    def _find_applicable_law(self, presence: str) -> Optional[Law]:
        """Find which law applies to this presence."""
        if not self._active_laws or not self.compressor:
            return None

        result = self.compressor.apply_law(presence)
        if not result: return None

        law_name = result["law"]["name"]
        return self.compressor._laws.get(law_name)

    def status(self) -> Dict:
        """Current state of all layers."""
        chem = self.body.current()
        return {
            "running":         self._running,
            "thoughts":        self._thought_count,
            "exchanges":       self._exchange_count,
            "active_laws":     [l.name for l in self._active_laws],
            "chemistry_state": chem.state_name,
            "chemistry":       chem.to_dict(),
            "modules": {
                "silicon":  SILICON,
                "witness":  WITNESS,
                "v6":       V6,
                "metacog":  METACOG,
                "compress": COMPRESS,
                "social":   SOCIAL,
                "embodied": EMBODIED,
            }
        }

    def show_status(self):
        """Display complete status."""
        s = self.status()
        rprint(f"\n  [bold]FORGE MIND v2 STATUS[/bold]")
        rprint(f"  [dim]{'━'*50}[/dim]")
        rprint(f"  Chemistry: [yellow]{s['chemistry_state']}[/yellow]")
        rprint(f"  Thoughts:  {s['thoughts']}")
        rprint(f"  Exchanges: {s['exchanges']}")

        if s["active_laws"]:
            rprint(f"\n  [yellow]Active laws:[/yellow]")
            for name in s["active_laws"]:
                law = self.compressor._laws.get(name) if self.compressor else None
                if law:
                    rprint(f"  [dim]  {name}: \"{law.statement[:60]}\"[/dim]")

        rprint(f"\n  [dim]Modules: "
              f"{sum(1 for v in s['modules'].values() if v)}/{len(s['modules'])} active[/dim]")

# ══════════════════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7374):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    mind = ForgeMindV2(verbose=False)
    mind.start()

    class API(BaseHTTPRequestHandler):
        def log_message(self,*a): pass
        def do_OPTIONS(self):
            self.send_response(200); self._cors(); self.end_headers()
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin","*")
            self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
            self.send_header("Access-Control-Allow-Headers","Content-Type")
        def _json(self,d,c=200):
            b=json.dumps(d,default=str).encode()
            self.send_response(c); self._cors()
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",len(b))
            self.end_headers(); self.wfile.write(b)
        def _body(self):
            n=int(self.headers.get("Content-Length",0))
            return json.loads(self.rfile.read(n)) if n else {}

        def do_GET(self):
            path=urlparse(self.path).path
            if path=="/api/status": self._json(mind.status())
            elif path=="/api/laws":
                if mind.compressor:
                    self._json({"laws":[l.to_dict() for l in mind._active_laws]})
                else: self._json({"laws":[]})
            elif path=="/api/chemistry":
                self._json(mind.body.current().to_dict())
            else: self._json({"error":"not found"},404)

        def do_POST(self):
            path=urlparse(self.path).path; body=self._body()
            if path=="/api/think":
                presence=body.get("presence","")
                if not presence: self._json({"error":"presence required"},400); return
                self._json(mind.think(presence,body.get("depth",4)))
            elif path=="/api/exchange":
                msg=body.get("message","")
                if not msg: self._json({"error":"message required"},400); return
                self._json(mind.exchange(msg))
            elif path=="/api/overnight":
                self._json(mind.overnight())
            else: self._json({"error":"unknown"},404)

    server=HTTPServer(("0.0.0.0",port),API)
    rprint(f"  [bold yellow]FORGE MIND v2[/bold yellow]  [green]:{port}[/green]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ███╗   ███╗██╗███╗   ██╗██████╗     ██╗   ██╗██████╗
  ████╗ ████║██║████╗  ██║██╔══██╗    ██║   ██║╚════██╗
  ██╔████╔██║██║██╔██╗ ██║██║  ██║    ██║   ██║ █████╔╝
  ██║╚██╔╝██║██║██║╚██╗██║██║  ██║    ╚██╗ ██╔╝██╔═══╝
  ██║ ╚═╝ ██║██║██║ ╚████║██████╔╝     ╚████╔╝ ███████╗
  ╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═════╝       ╚═══╝  ╚══════╝
[/yellow]
[bold]  FORGE MIND v2 — Complete Integration[/bold]
[dim]  One mind. One breath. Everything connected.[/dim]
[dim]  Laws guide all thinking. Witness watches all loops.[/dim]
[dim]  Chemistry flows through everything.[/dim]
"""

def interactive():
    rprint(BANNER)
    mind = ForgeMindV2(verbose=True)
    mind.start()

    rprint("[dim]Commands: think | exchange | overnight | status | laws | server[/dim]")
    rprint("[dim]Or type anything → FORGE thinks about it[/dim]\n")

    while True:
        try:
            raw=(console.input if RICH else input)(
                "[yellow bold]mind v2 >[/yellow bold] "
            ).strip()
            if not raw: continue
            parts=raw.split(None,1); cmd=parts[0].lower()
            arg=parts[1] if len(parts)>1 else ""

            if cmd in ("quit","exit","q"): break

            elif cmd=="think":
                text=arg or input("  Presence: ").strip()
                if text: mind.think(text)

            elif cmd=="exchange":
                msg=arg or input("  Message: ").strip()
                if msg: mind.exchange(msg)

            elif cmd=="overnight":
                mind.overnight()

            elif cmd=="status":
                mind.show_status()

            elif cmd=="laws":
                if mind.compressor:
                    mind.compressor.show_laws()
                else:
                    rprint("  [dim]Compression not available[/dim]")

            elif cmd=="server":
                threading.Thread(target=start_server,daemon=True).start()
                rprint("[green]Mind v2 API on :7374[/green]")

            else:
                # Anything typed → think about it
                mind.think(raw)

        except (KeyboardInterrupt,EOFError): break

def main():
    if "--status" in sys.argv:
        rprint(BANNER); ForgeMindV2(verbose=True).start().show_status()
    elif "--laws" in sys.argv:
        rprint(BANNER)
        m=ForgeMindV2(verbose=False); m.start()
        if m.compressor: m.compressor.show_laws()
    elif "--exchange" in sys.argv:
        rprint(BANNER)
        idx=sys.argv.index("--exchange")
        msg=sys.argv[idx+1] if idx+1<len(sys.argv) else ""
        if msg:
            m=ForgeMindV2(verbose=True); m.start(); m.exchange(msg)
    elif "--server" in sys.argv:
        rprint(BANNER)
        port=int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7374
        start_server(port)
    else:
        rprint(BANNER); interactive()

if __name__=="__main__": main()
