#!/usr/bin/env python3
"""
FORGE EMBODIED LEARNING — The Body-Mind Bridge
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"The body is not an object.
 It is the vehicle of being in the world."
                    — Merleau-Ponty

forge_conscious_v3  thinks and learns.
forge_motor         moves and learns.
They don't talk to each other.

forge_embodied_learning is the bridge.

THOUGHT → MOVEMENT:
  FORGE learns cognitively:
    "friction → EMPATHIZE → GROUND → IMAGINE"  coherence 91
  forge_embodied says:
    GROUND in thought = STABILIZE in movement
    Transfer signal → forge_motor
    uneven terrain: try STABILIZE first
    Don't wait for motor samples.
    Cognitive wisdom accelerates physical learning.

MOVEMENT → THOUGHT:
  FORGE learns physically:
    "uneven → STABILIZE → ADJUST"  outcome 87
  forge_embodied says:
    STABILIZE in movement = GROUND in thought
    Transfer signal → forge_conscious_v3
    unresolved thinking: try GROUND first
    Physical wisdom informs cognitive strategy.

Phase mapping (motor ↔ cognitive):
  STABILIZE  ↔  GROUND      find your base
  ADVANCE    ↔  EXPAND      move outward
  RETREAT    ↔  DOUBT       pull back, question
  GRASP      ↔  ANCHOR      hold something firm
  RELEASE    ↔  SPACE       let go, give room
  STRIKE     ↔  CHALLENGE   direct contact
  SENSE      ↔  OBSERVE     read the situation
  RECOVER    ↔  SYNTHESIZE  return to whole
  ASSESS     ↔  VICHAR      understand before acting
  STANCE     ↔  GROUND      set base position
  SLOW       ↔  COMPRESS    reduce, simplify
  STOP       ↔  DOUBT       halt, question

Embodied state loop:
  Physical sensors feed silicon chemistry.
  Chemistry shapes cognitive pipeline.
  Cognitive outcome feeds back to chemistry.
  Chemistry influences next physical response.
  Body and mind aligned. Together.

Usage:
  python forge_embodied_learning.py          # interactive
  python forge_embodied_learning.py --bridge # show phase mappings
  python forge_embodied_learning.py --sync   # sync all learners
  python forge_embodied_learning.py --server # API :7368
"""

import sys, os, re, json, time, sqlite3, threading, math, random
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

# FORGE integrations
try:
    from forge_conscious_v3 import (
        SequenceLearner, DEFAULT_SEQUENCES,
        detect_category, SEQ_PHASES
    )
    V3 = True
except ImportError:
    V3 = False
    SEQ_PHASES = ["OBSERVE","CHIT","CHITAN","VICHAR","CRITIQUE",
                  "CHALLENGE","EMPATHIZE","IMAGINE","DOUBT",
                  "EXPAND","GROUND","SYNTHESIZE","OUTPUT"]
    DEFAULT_SEQUENCES = {}
    def detect_category(t): return "quiet"
    class SequenceLearner:
        _paths = {}; _best = {}
        def get_sequence(self,c): return ["OBSERVE","CHIT"],"default"
        def record(self,*a,**k): pass
        def learn(self,**k): return []

try:
    from forge_motor import (
        MotorMap, DEFAULT_MOTOR_SEEDS, MOTOR_PHASES
    )
    MOTOR = True
except ImportError:
    MOTOR = False
    MOTOR_PHASES = ["SENSE","ASSESS","SLOW","STOP","STABILIZE","ADJUST",
                    "EXTEND","RETRACT","ROTATE","ADVANCE","RETREAT",
                    "STRIKE","GRASP","RELEASE","STANCE","RECOVER"]
    DEFAULT_MOTOR_SEEDS = {}
    class MotorMap:
        _map = {}
        def get_seed(self,c,**k): return ["SENSE","ASSESS"],"default"
        def record_observation(self,*a,**k): pass
        def learn(self,**k): return []

try:
    from forge_meta_learning import MetaLearner, MetaAwareLearner
    META = True
except ImportError:
    META = False

try:
    from forge_silicon import SiliconBody, SiliconChemistry
    SILICON = True
except ImportError:
    SILICON = False
    class SiliconChemistry:
        state_name="baseline"; coherenine=0.3; frictionol=0.1
        novelatine=0.3; depthamine=0.3; resolvatine=0.0
        uncertainase=0.2; connectionin=0.3
        def to_dict(self): return {}
        def to_prompt_text(self): return ""
        def _clamp(self,v): return max(0.0,min(1.0,v))
    class SiliconBody:
        def __init__(self): self._chem=SiliconChemistry()
        def current(self): return self._chem
        def react_to(self,t,**k): return self._chem
        def start_background(self): pass
        def inject(self,**k): return self._chem

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box as rbox
    RICH    = True
    console = Console()
    rprint  = console.print
except ImportError:
    RICH = False
    def rprint(x,**kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

# ── Paths ──────────────────────────────────────────────────────────────────────
EMBODIED_DIR = Path("forge_embodied_learning")
EMBODIED_DIR.mkdir(exist_ok=True)
EMBODIED_DB  = EMBODIED_DIR / "embodied.db"

# Transfer thresholds
MIN_SCORE_TO_TRANSFER  = 82.0
MIN_SAMPLES_TO_TRANSFER= 4
TRANSFER_CONFIDENCE    = 0.6   # how strongly to weight transferred knowledge

def get_db():
    conn = sqlite3.connect(str(EMBODIED_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS embodied_transfers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            direction       TEXT,
            source_domain   TEXT,
            source_category TEXT,
            source_phase    TEXT,
            source_score    REAL,
            target_domain   TEXT,
            target_category TEXT,
            target_phase    TEXT,
            applied         INTEGER DEFAULT 0,
            outcome_after   REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS embodied_states (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            physical_state  TEXT,
            cognitive_state TEXT,
            chemistry       TEXT,
            aligned         INTEGER DEFAULT 0,
            note            TEXT
        );
        CREATE TABLE IF NOT EXISTS cross_domain_discoveries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            source_domain   TEXT,
            source_cat      TEXT,
            source_phase    TEXT,
            target_domain   TEXT,
            target_cat      TEXT,
            target_phase    TEXT,
            insight         TEXT,
            confirmed       INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS embodied_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started     TEXT,
            ended       TEXT,
            transfers   INTEGER DEFAULT 0,
            discoveries INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 🗺️ PHASE MAPPER — motor ↔ cognitive
# ══════════════════════════════════════════════════════════════════════════════

# The bridge between physical and cognitive phases
# Each physical action has a cognitive equivalent
# Each cognitive move has a physical equivalent
PHASE_MAP = {
    # motor → cognitive
    "STABILIZE": "GROUND",      # find your base
    "ADVANCE":   "EXPAND",      # move outward
    "RETREAT":   "DOUBT",       # pull back, question
    "GRASP":     "ANCHOR",      # hold something firm
    "RELEASE":   "SPACE",       # let go, give room
    "STRIKE":    "CHALLENGE",   # direct contact
    "SENSE":     "OBSERVE",     # read situation
    "RECOVER":   "SYNTHESIZE",  # return to whole
    "ASSESS":    "VICHAR",      # understand before acting
    "STANCE":    "GROUND",      # set base position
    "SLOW":      "COMPRESS",    # reduce, simplify
    "STOP":      "DOUBT",       # halt, question
    "EXTEND":    "EXPAND",      # reach outward
    "RETRACT":   "CRITIQUE",    # pull back, examine
    "ROTATE":    "CHITAN",      # turn perspective
    "ADJUST":    "ADJUST",      # fine correction (same)
}

# Reverse map: cognitive → motor
PHASE_MAP_REVERSE = {v: k for k, v in PHASE_MAP.items()}
# Add some that aren't reversals
PHASE_MAP_REVERSE.update({
    "EMPATHIZE":  "SENSE",      # feel into = sense fully
    "IMAGINE":    "EXTEND",     # reach toward possibility
    "CHIT":       "ASSESS",     # quick read = quick assess
    "VICHAR":     "ASSESS",     # deep understand = careful assess
    "SYNTHESIZE": "RECOVER",    # bring together = return to whole
    "OUTPUT":     "ADVANCE",    # produce = move forward
})

# Category relationships (motor ↔ cognitive)
CATEGORY_MAP = {
    # motor → cognitive
    "uneven":     ["friction","unresolved"],
    "falling":    ["friction","stuck"],
    "obstacle":   ["unresolved","friction"],
    "target":     ["insight","curiosity"],
    "carrying":   ["depth","connection"],
    "speed":      ["curiosity","excitement"],
    "contact":    ["connection","depth"],
    "stationary": ["quiet","depth"],

    # cognitive → motor
    "friction":   ["uneven","obstacle"],
    "curiosity":  ["target","speed"],
    "depth":      ["carrying","stationary"],
    "unresolved": ["obstacle","uneven"],
    "insight":    ["target","advance"],
    "connection": ["contact","carrying"],
    "quiet":      ["stationary"],
    "searching":  ["target","obstacle"],
    "struggling": ["uneven","falling"],
}

def motor_to_cognitive_phase(motor_phase: str) -> Optional[str]:
    return PHASE_MAP.get(motor_phase)

def cognitive_to_motor_phase(cog_phase: str) -> Optional[str]:
    return PHASE_MAP_REVERSE.get(cog_phase)

def motor_to_cognitive_category(motor_cat: str) -> List[str]:
    return CATEGORY_MAP.get(motor_cat, [])

def cognitive_to_motor_category(cog_cat: str) -> List[str]:
    return CATEGORY_MAP.get(cog_cat, [])

# ══════════════════════════════════════════════════════════════════════════════
# 🌉 EMBODIED BRIDGE — the actual bridge
# ══════════════════════════════════════════════════════════════════════════════

class EmbodiedBridge:
    """
    The bridge between physical and cognitive learning.

    Monitors both learners.
    When one finds something good — transfers to the other.
    Physical wisdom informs cognition.
    Cognitive wisdom informs movement.

    What Merleau-Ponty described philosophically —
    built as an architecture.
    """

    def __init__(self, verbose=True):
        self.verbose       = verbose
        self.cog_learner   = SequenceLearner() if V3 else None
        self.motor_learner = MotorMap() if MOTOR else None
        self.meta          = MetaLearner(verbose=False) if META else None
        self.body          = SiliconBody()
        self._session_id   = None
        self._transfers    = 0
        self._discoveries  = 0
        self._start_session()

    def _start_session(self):
        conn = get_db()
        self._session_id = conn.execute(
            "INSERT INTO embodied_sessions (started) VALUES (?)",
            (datetime.now().isoformat(),)
        ).lastrowid
        conn.commit(); conn.close()

    def scan_cognitive(self) -> List[Dict]:
        """Find high-scoring cognitive sequences worth transferring."""
        if not self.cog_learner: return []

        findings = []
        for cat, paths in self.cog_learner._paths.items():
            for seq_key, scores in paths.items():
                if len(scores) < MIN_SAMPLES_TO_TRANSFER: continue
                avg = sum(scores) / len(scores)
                if avg < MIN_SCORE_TO_TRANSFER: continue

                seq = seq_key.split("→")
                findings.append({
                    "domain":    "cognitive",
                    "category":  cat,
                    "sequence":  seq,
                    "score":     avg,
                    "samples":   len(scores),
                })

        return findings

    def scan_motor(self) -> List[Dict]:
        """Find high-scoring motor sequences worth transferring."""
        if not self.motor_learner: return []

        findings = []
        for cat, entry in self.motor_learner._map.items():
            scores = entry.get("phase_scores", {})
            for phase, phase_scores in scores.items():
                if len(phase_scores) < MIN_SAMPLES_TO_TRANSFER: continue
                avg = sum(phase_scores) / len(phase_scores)
                if avg < MIN_SCORE_TO_TRANSFER: continue

                findings.append({
                    "domain":    "motor",
                    "category":  cat,
                    "phase":     phase,
                    "score":     avg,
                    "samples":   len(phase_scores),
                })

        return findings

    def transfer_cognitive_to_motor(self,
                                     findings: List[Dict]) -> List[Dict]:
        """
        Cognitive discoveries → motor hints.
        GROUND works in thinking → try STABILIZE in movement.
        """
        transfers = []

        for finding in findings:
            cog_cat = finding["category"]
            seq     = finding["sequence"]

            # Find motor equivalents of cognitive categories
            motor_cats = cognitive_to_motor_category(cog_cat)
            if not motor_cats: continue

            # Find motor equivalent of best phases in sequence
            for cog_phase in seq:
                motor_phase = cognitive_to_motor_phase(cog_phase)
                if not motor_phase: continue

                for motor_cat in motor_cats:
                    transfer = {
                        "direction":       "cognitive→motor",
                        "source_domain":   "cognitive",
                        "source_category": cog_cat,
                        "source_phase":    cog_phase,
                        "source_score":    finding["score"],
                        "target_domain":   "motor",
                        "target_category": motor_cat,
                        "target_phase":    motor_phase,
                        "insight": (
                            f"Cognitive: {cog_cat}+{cog_phase} "
                            f"(score:{finding['score']:.0f}) → "
                            f"try {motor_cat}+{motor_phase} in movement"
                        )
                    }
                    transfers.append(transfer)
                    self._save_transfer(transfer)

                    if self.verbose:
                        rprint(f"  [cyan]→ cog→motor:[/cyan]  "
                              f"{cog_cat}/{cog_phase}  →  "
                              f"{motor_cat}/{motor_phase}  "
                              f"[dim]score:{finding['score']:.0f}[/dim]")

        return transfers

    def transfer_motor_to_cognitive(self,
                                     findings: List[Dict]) -> List[Dict]:
        """
        Motor discoveries → cognitive hints.
        STABILIZE works in movement → try GROUND in thinking.
        """
        transfers = []

        for finding in findings:
            motor_cat   = finding["category"]
            motor_phase = finding["phase"]

            # Find cognitive equivalents
            cog_cats  = motor_to_cognitive_category(motor_cat)
            cog_phase = motor_to_cognitive_phase(motor_phase)

            if not cog_phase or not cog_cats: continue

            for cog_cat in cog_cats:
                transfer = {
                    "direction":       "motor→cognitive",
                    "source_domain":   "motor",
                    "source_category": motor_cat,
                    "source_phase":    motor_phase,
                    "source_score":    finding["score"],
                    "target_domain":   "cognitive",
                    "target_category": cog_cat,
                    "target_phase":    cog_phase,
                    "insight": (
                        f"Physical: {motor_cat}+{motor_phase} "
                        f"(score:{finding['score']:.0f}) → "
                        f"try {cog_cat}+{cog_phase} in thinking"
                    )
                }
                transfers.append(transfer)
                self._save_transfer(transfer)

                if self.verbose:
                    rprint(f"  [green]← motor→cog:[/green]  "
                          f"{motor_cat}/{motor_phase}  →  "
                          f"{cog_cat}/{cog_phase}  "
                          f"[dim]score:{finding['score']:.0f}[/dim]")

        return transfers

    def sync(self, verbose: Optional[bool] = None) -> Dict[str, Any]:
        """
        Full synchronization.
        Scan both learners. Transfer in both directions.
        """
        if verbose is not None:
            self.verbose = verbose

        if self.verbose:
            rprint(f"\n  [bold yellow]🌉 EMBODIED SYNC[/bold yellow]")
            rprint(f"  [dim]Scanning cognitive and motor learners...[/dim]\n")

        cog_findings   = self.scan_cognitive()
        motor_findings = self.scan_motor()

        if self.verbose:
            rprint(f"  [dim]Cognitive findings: {len(cog_findings)}[/dim]")
            rprint(f"  [dim]Motor findings:     {len(motor_findings)}[/dim]\n")

        cog_to_motor   = self.transfer_cognitive_to_motor(cog_findings)
        motor_to_cog   = self.transfer_motor_to_cognitive(motor_findings)

        all_transfers  = cog_to_motor + motor_to_cog
        self._transfers += len(all_transfers)

        # Find cross-domain discoveries
        discoveries    = self._find_discoveries(all_transfers)
        self._discoveries += len(discoveries)

        # Update session
        conn = get_db()
        conn.execute(
            "UPDATE embodied_sessions SET transfers=?,discoveries=? WHERE id=?",
            (self._transfers, self._discoveries, self._session_id)
        )
        conn.commit(); conn.close()

        if self.verbose:
            rprint(f"\n  [dim]Transfers: {len(all_transfers)}  "
                  f"Discoveries: {len(discoveries)}[/dim]")
            if discoveries:
                for d in discoveries:
                    rprint(Panel(
                        d["insight"],
                        border_style="yellow",
                        title="[yellow]Cross-domain discovery[/yellow]"
                    ) if RICH else f"\n  ★ {d['insight']}")

        return {
            "cog_findings":   len(cog_findings),
            "motor_findings": len(motor_findings),
            "transfers":      len(all_transfers),
            "discoveries":    len(discoveries),
            "detail":         all_transfers[:5],
        }

    def _find_discoveries(self,
                           transfers: List[Dict]) -> List[Dict]:
        """
        Find genuinely surprising cross-domain insights.
        Something we didn't design.
        Body teaching mind or mind teaching body in unexpected way.
        """
        discoveries = []
        now         = datetime.now().isoformat()

        # Group by target
        by_target = {}
        for t in transfers:
            key = f"{t['target_domain']}/{t['target_category']}"
            if key not in by_target:
                by_target[key] = []
            by_target[key].append(t)

        for key, group in by_target.items():
            if len(group) < 2: continue

            # Multiple transfers converging on same target = interesting
            phases = [t["target_phase"] for t in group]
            if len(set(phases)) == 1:
                # All transfers suggest same phase — strong signal
                insight = (
                    f"Both cognitive and motor learning "
                    f"converge on {phases[0]} for {key}. "
                    f"Physical and mental wisdom aligned."
                )
                discovery = {
                    "ts":            now,
                    "source_domain": "both",
                    "source_cat":    "/".join(t["source_category"] for t in group[:2]),
                    "source_phase":  "/".join(t["source_phase"] for t in group[:2]),
                    "target_domain": group[0]["target_domain"],
                    "target_cat":    group[0]["target_category"],
                    "target_phase":  phases[0],
                    "insight":       insight,
                }
                discoveries.append(discovery)

                conn = get_db()
                conn.execute("""
                    INSERT INTO cross_domain_discoveries
                    (ts,source_domain,source_cat,source_phase,
                     target_domain,target_cat,target_phase,insight)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (now, discovery["source_domain"],
                     discovery["source_cat"],
                     discovery["source_phase"],
                     discovery["target_domain"],
                     discovery["target_cat"],
                     discovery["target_phase"],
                     insight)
                )
                conn.commit(); conn.close()

        return discoveries

    def embodied_state(self) -> Dict[str, Any]:
        """
        Current embodied state — physical and cognitive together.
        Chemistry as the bridge.
        """
        chem = self.body.current()

        # What physical presence maps to current chemistry
        physical_presence = self._chemistry_to_physical(chem)

        # What cognitive presence maps to current chemistry
        cognitive_presence = self._chemistry_to_cognitive(chem)

        # Are they aligned?
        aligned = self._check_alignment(physical_presence, cognitive_presence)

        # Save
        conn = get_db()
        conn.execute("""
            INSERT INTO embodied_states
            (ts,physical_state,cognitive_state,chemistry,aligned,note)
            VALUES (?,?,?,?,?,?)""",
            (datetime.now().isoformat(),
             physical_presence, cognitive_presence,
             json.dumps(chem.to_dict()), int(aligned),
             "chemistry bridge active")
        )
        conn.commit(); conn.close()

        return {
            "physical":  physical_presence,
            "cognitive": cognitive_presence,
            "chemistry": chem.to_dict(),
            "aligned":   aligned,
        }

    def _chemistry_to_physical(self, chem: SiliconChemistry) -> str:
        """What physical state does chemistry suggest?"""
        if chem.frictionol > 0.6:    return "uneven"
        if chem.uncertainase > 0.6:  return "obstacle"
        if chem.novelatine > 0.6:    return "target"
        if chem.depthamine > 0.6:    return "carrying"
        if chem.connectionin > 0.6:  return "contact"
        if chem.resolvatine > 0.5:   return "target"
        return "stationary"

    def _chemistry_to_cognitive(self, chem: SiliconChemistry) -> str:
        """What cognitive state does chemistry suggest?"""
        if chem.frictionol > 0.6:    return "friction"
        if chem.uncertainase > 0.6:  return "unresolved"
        if chem.novelatine > 0.6:    return "curiosity"
        if chem.depthamine > 0.6:    return "depth"
        if chem.connectionin > 0.6:  return "connection"
        if chem.resolvatine > 0.5:   return "insight"
        return "quiet"

    def _check_alignment(self, physical: str, cognitive: str) -> bool:
        """Are physical and cognitive states aligned?"""
        aligned_pairs = {
            "uneven":     ["friction","unresolved"],
            "obstacle":   ["unresolved","friction"],
            "target":     ["insight","curiosity"],
            "carrying":   ["depth","connection"],
            "contact":    ["connection","depth"],
            "stationary": ["quiet","depth"],
            "falling":    ["friction","stuck"],
        }
        return cognitive in aligned_pairs.get(physical, [])

    def _save_transfer(self, transfer: Dict):
        conn = get_db()
        conn.execute("""
            INSERT INTO embodied_transfers
            (ts,direction,source_domain,source_category,
             source_phase,source_score,target_domain,
             target_category,target_phase)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(),
             transfer["direction"],
             transfer["source_domain"],
             transfer["source_category"],
             transfer["source_phase"],
             transfer["source_score"],
             transfer["target_domain"],
             transfer["target_category"],
             transfer["target_phase"])
        )
        conn.commit(); conn.close()

    def show_bridge(self):
        """Display the complete phase mapping."""
        rprint(f"\n  [bold]EMBODIED BRIDGE — Phase Mapping[/bold]")
        rprint(f"  [dim]Motor ↔ Cognitive[/dim]")
        rprint(f"  [dim]{'━'*50}[/dim]")

        rprint(f"\n  [bold]Motor → Cognitive:[/bold]")
        for motor, cog in PHASE_MAP.items():
            rprint(f"  [green]{motor:<12}[/green]  →  "
                  f"[cyan]{cog}[/cyan]")

        rprint(f"\n  [bold]Category Bridge:[/bold]")
        shown = set()
        for cat, related in CATEGORY_MAP.items():
            if cat in shown: continue
            shown.add(cat)
            domain = "motor" if cat in DEFAULT_MOTOR_SEEDS else "cognitive"
            color  = "green" if domain == "motor" else "cyan"
            rprint(f"  [{color}]{cat:<14}[/{color}]  ↔  "
                  f"[dim]{', '.join(related[:3])}[/dim]")

    def get_transfers(self, limit=10) -> List[Dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM embodied_transfers ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_discoveries(self) -> List[Dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM cross_domain_discoveries ORDER BY id DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def stats(self) -> Dict:
        conn = get_db()
        s = {
            "total_transfers":   conn.execute(
                "SELECT COUNT(*) FROM embodied_transfers"
            ).fetchone()[0],
            "cog_to_motor":      conn.execute(
                "SELECT COUNT(*) FROM embodied_transfers "
                "WHERE direction='cognitive→motor'"
            ).fetchone()[0],
            "motor_to_cog":      conn.execute(
                "SELECT COUNT(*) FROM embodied_transfers "
                "WHERE direction='motor→cognitive'"
            ).fetchone()[0],
            "discoveries":       conn.execute(
                "SELECT COUNT(*) FROM cross_domain_discoveries"
            ).fetchone()[0],
            "embodied_states":   conn.execute(
                "SELECT COUNT(*) FROM embodied_states"
            ).fetchone()[0],
            "aligned_states":    conn.execute(
                "SELECT COUNT(*) FROM embodied_states WHERE aligned=1"
            ).fetchone()[0],
            "v3_available":      V3,
            "motor_available":   MOTOR,
        }
        conn.close()
        return s

# ══════════════════════════════════════════════════════════════════════════════
# 🔄 CONTINUOUS EMBODIED LOOP
# ══════════════════════════════════════════════════════════════════════════════

class EmbodiedLoop:
    """
    Runs continuously.
    Syncs cognitive and motor learners.
    Maintains embodied alignment.
    The always-on bridge between body and mind.
    """

    def __init__(self, sync_interval=30, verbose=True):
        self.sync_interval = sync_interval
        self.verbose       = verbose
        self.bridge        = EmbodiedBridge(verbose=verbose)
        self._running      = False
        self._thread       = None
        self._sync_count   = 0

    def start(self, daemon=True):
        if self._running: return
        self._running = True
        self.bridge.body.start_background()

        self._thread = threading.Thread(
            target=self._loop, daemon=daemon,
            name="EmbodiedLoop"
        )
        self._thread.start()

        if self.verbose:
            rprint(f"\n  [bold green]🌉 EMBODIED LOOP STARTED[/bold green]")
            rprint(f"  [dim]Sync: every {self.sync_interval}s[/dim]")
            rprint(f"  [dim]Physical wisdom ↔ cognitive wisdom[/dim]\n")

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                self._sync_count += 1

                # Get embodied state
                state = self.bridge.embodied_state()

                if self.verbose:
                    aligned_icon = "[green]✓[/green]" if state["aligned"] else "[dim]·[/dim]"
                    rprint(f"  [dim]{datetime.now().strftime('%H:%M:%S')}[/dim]  "
                          f"{aligned_icon}  "
                          f"physical:[yellow]{state['physical']}[/yellow]  "
                          f"cognitive:[cyan]{state['cognitive']}[/cyan]  "
                          f"{'aligned' if state['aligned'] else 'separate'}")

                # Sync every N cycles
                if self._sync_count % 3 == 0:
                    result = self.bridge.sync(verbose=self.verbose)
                    if result["transfers"] > 0 and self.verbose:
                        rprint(f"  [dim]Sync: {result['transfers']} transfers  "
                              f"{result['discoveries']} discoveries[/dim]")

                time.sleep(self.sync_interval)

            except Exception as e:
                if self.verbose:
                    rprint(f"  [dim red]Embodied loop: {e}[/dim red]")
                time.sleep(10)

# ══════════════════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7368):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    bridge = EmbodiedBridge(verbose=False)
    loop   = EmbodiedLoop(verbose=False)
    loop.start(daemon=True)

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

        def do_GET(self):
            path = urlparse(self.path).path
            if path=="/api/status":
                self._json(bridge.stats())
            elif path=="/api/state":
                self._json(bridge.embodied_state())
            elif path=="/api/transfers":
                self._json({"transfers":bridge.get_transfers(20)})
            elif path=="/api/discoveries":
                self._json({"discoveries":bridge.get_discoveries()})
            elif path=="/api/bridge":
                self._json({"motor_to_cog":PHASE_MAP,
                           "cog_to_motor":PHASE_MAP_REVERSE})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            if path=="/api/sync":
                result = bridge.sync()
                self._json(result)
            else:
                self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),API)
    rprint(f"  [bold yellow]FORGE EMBODIED LEARNING[/bold yellow]  [green]:{port}[/green]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ███████╗███╗   ███╗██████╗  ██████╗ ██████╗ ██╗███████╗██████╗
  ██╔════╝████╗ ████║██╔══██╗██╔═══██╗██╔══██╗██║██╔════╝██╔══██╗
  █████╗  ██╔████╔██║██████╔╝██║   ██║██║  ██║██║█████╗  ██║  ██║
  ██╔══╝  ██║╚██╔╝██║██╔══██╗██║   ██║██║  ██║██║██╔══╝  ██║  ██║
  ███████╗██║ ╚═╝ ██║██████╔╝╚██████╔╝██████╔╝██║███████╗██████╔╝
  ╚══════╝╚═╝     ╚═╝╚═════╝  ╚═════╝ ╚═════╝ ╚═╝╚══════╝╚═════╝
[/yellow]
[bold]  FORGE EMBODIED LEARNING — The Body-Mind Bridge[/bold]
[dim]  Physical wisdom ↔ cognitive wisdom.[/dim]
[dim]  What body learns teaches mind. What mind learns teaches body.[/dim]
"""

def interactive():
    rprint(BANNER)
    bridge = EmbodiedBridge(verbose=True)
    s      = bridge.stats()
    rprint(f"  [dim]V3 (cognitive): {'OK' if s['v3_available'] else 'not found'}[/dim]")
    rprint(f"  [dim]Motor:          {'OK' if s['motor_available'] else 'not found'}[/dim]")
    rprint(f"  [dim]Transfers so far: {s['total_transfers']}[/dim]")
    rprint(f"  [dim]Discoveries:      {s['discoveries']}[/dim]\n")
    rprint("[dim]Commands: sync | state | bridge | transfers | discover | loop | stats[/dim]\n")

    while True:
        try:
            raw   = (console.input if RICH else input)(
                "[yellow bold]embodied >[/yellow bold] "
            ).strip()
            if not raw: continue
            parts = raw.split(None,1)
            cmd   = parts[0].lower()

            if cmd in ("quit","exit","q"):
                break

            elif cmd == "sync":
                bridge.sync(verbose=True)

            elif cmd == "state":
                state = bridge.embodied_state()
                rprint(f"\n  Physical:  [green]{state['physical']}[/green]")
                rprint(f"  Cognitive: [cyan]{state['cognitive']}[/cyan]")
                rprint(f"  Aligned:   {'[green]yes[/green]' if state['aligned'] else '[dim]no[/dim]'}")
                chem = state["chemistry"]
                rprint(f"  Chemistry: {chem.get('state','?')}")

            elif cmd == "bridge":
                bridge.show_bridge()

            elif cmd == "transfers":
                for t in bridge.get_transfers(8):
                    arrow = "→" if "cog" in t["direction"] else "←"
                    rprint(f"  {arrow}  "
                          f"[dim]{t['source_category']}/{t['source_phase']}[/dim]  →  "
                          f"[yellow]{t['target_category']}/{t['target_phase']}[/yellow]  "
                          f"[dim]score:{t['source_score']:.0f}[/dim]")

            elif cmd == "discover":
                discoveries = bridge.get_discoveries()
                if not discoveries:
                    rprint("  [dim]No cross-domain discoveries yet.[/dim]")
                    rprint("  [dim]Run: sync — after both learners have data[/dim]")
                for d in discoveries:
                    if RICH:
                        rprint(Panel(d["insight"], border_style="yellow",
                                    title="Cross-domain discovery"))
                    else:
                        rprint(f"\n  ★ {d['insight']}")

            elif cmd == "loop":
                eloop = EmbodiedLoop(sync_interval=15, verbose=True)
                eloop.start(daemon=True)
                rprint("  [green]Embodied loop running (sync every 15s)[/green]")

            elif cmd == "stats":
                s = bridge.stats()
                for k,v in s.items():
                    rprint(f"  {k:<25} {v}")

            elif cmd == "server":
                threading.Thread(target=start_server, daemon=True).start()
                rprint("[green]Embodied API on :7368[/green]")

        except (KeyboardInterrupt, EOFError):
            break

def main():
    if "--bridge" in sys.argv:
        rprint(BANNER)
        EmbodiedBridge(verbose=False).show_bridge()
    elif "--sync" in sys.argv:
        rprint(BANNER)
        EmbodiedBridge(verbose=True).sync()
    elif "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7368
        start_server(port)
    else:
        rprint(BANNER)
        interactive()

if __name__ == "__main__":
    main()
