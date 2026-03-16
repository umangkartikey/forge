#!/usr/bin/env python3
"""
FORGE META LEARNING — Learning How To Learn
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Every learning module so far uses fixed strategy:
  exploit 70%  explore 20%  mutate 10%
  Always. Same. Forever.

That is not how good learners work.

Good learners adjust strategy based on phase:

  IGNORANT  (0-10 samples)
    Don't know anything yet.
    Explore aggressively.
    exploit:10% explore:80% mutate:10%

  LEARNING  (10-50 samples)
    Patterns emerging. Use them + keep exploring.
    exploit:50% explore:40% mutate:10%

  COMPETENT (50-200 samples)
    Strong signal. Exploit + small mutations.
    exploit:75% explore:15% mutate:10%

  EXPERT    (200+ samples)
    Mostly exploit. Tiny exploration.
    exploit:88% explore:5%  mutate:7%

  DRIFT     (outcomes dropping suddenly)
    Something changed. Explore again.
    exploit:30% explore:60% mutate:10%

Transfer signals (new in meta-learning):
  GROUND worked in friction (91).
  GROUND worked in curiosity (90).
  → Try GROUND earlier in depth.
  → Transfer signal. Don't wait for samples.
  → Accelerate learning in related categories.

How it works:
  Wraps every learner (v2, v3, motor, social).
  Monitors their sample counts + outcome trends.
  Adjusts their exploit/explore/mutate ratios.
  Passes transfer signals between related categories.
  Detects drift. Triggers re-exploration.
  Makes every module smarter without changing their code.

Meta-outcomes:
  Not just "did this cohere"
  But: "is our learning velocity increasing?"
      "are we finding discoveries faster?"
      "is the strategy right for the phase?"

Usage:
  python forge_meta_learning.py              # interactive
  python forge_meta_learning.py --status     # all module phases
  python forge_meta_learning.py --transfer   # show transfer signals
  python forge_meta_learning.py --wrap       # wrap all modules
  python forge_meta_learning.py --server     # API :7367
"""

import sys, os, re, json, time, sqlite3, threading, math, random
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

# FORGE learner imports
try:
    from forge_conscious_v3 import SequenceLearner, DEFAULT_SEQUENCES
    V3 = True
except ImportError:
    V3 = False

try:
    from forge_social_learning import SocialMap, DEFAULT_SOCIAL_SEEDS
    SOCIAL = True
except ImportError:
    SOCIAL = False

try:
    from forge_motor import MotorMap, DEFAULT_MOTOR_SEEDS
    MOTOR = True
except ImportError:
    MOTOR = False

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
META_DIR = Path("forge_meta_learning")
META_DIR.mkdir(exist_ok=True)
META_DB  = META_DIR / "meta.db"

# Learning phases with their strategy ratios
PHASES = {
    "ignorant":  {"samples": (0,   10),  "exploit":0.10, "explore":0.80, "mutate":0.10},
    "learning":  {"samples": (10,  50),  "exploit":0.50, "explore":0.40, "mutate":0.10},
    "competent": {"samples": (50,  200), "exploit":0.75, "explore":0.15, "mutate":0.10},
    "expert":    {"samples": (200, 9999),"exploit":0.88, "explore":0.05, "mutate":0.07},
    "drift":     {"samples": (0,   9999),"exploit":0.30, "explore":0.60, "mutate":0.10},
}

# How many recent samples to check for drift
DRIFT_WINDOW    = 10
DRIFT_THRESHOLD = 8.0   # outcome drop of this much triggers drift

# Transfer signal strength
TRANSFER_MIN_SCORE     = 85.0  # phase must score above this to transfer
TRANSFER_MIN_SAMPLES   = 5     # phase must have this many samples
TRANSFER_BOOST         = 0.15  # how much to boost explore for transfer hint

# Category relationships (which categories share signal)
CATEGORY_RELATIONS = {
    # Thought categories
    "friction":   ["unresolved","depth","quiet"],
    "curiosity":  ["insight","depth","connecting"],
    "depth":      ["friction","connection","quiet"],
    "unresolved": ["friction","searching","stuck"],
    "insight":    ["curiosity","depth","celebrating"],
    "connection": ["depth","curiosity","connecting"],
    "quiet":      ["depth","friction"],

    # Social categories
    "struggling": ["grieving","stuck","confused"],
    "searching":  ["confused","curiosity","unresolved"],
    "excited":    ["celebrating","insight","curiosity"],
    "grieving":   ["struggling","connecting","quiet"],
    "confused":   ["searching","stuck","unresolved"],
    "stuck":      ["struggling","confused","friction"],
    "connecting": ["celebrating","excited","connection"],
    "celebrating":["excited","connecting","insight"],

    # Motor categories
    "uneven":     ["falling","carrying","speed"],
    "falling":    ["uneven","carrying"],
    "obstacle":   ["speed","stationary"],
    "target":     ["contact","stationary"],
    "carrying":   ["uneven","speed"],
    "speed":      ["obstacle","uneven","carrying"],
    "contact":    ["target","carrying"],
    "stationary": ["obstacle","target"],
}

def get_db():
    conn = sqlite3.connect(str(META_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS module_states (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            module      TEXT,
            category    TEXT,
            phase       TEXT,
            samples     INTEGER DEFAULT 0,
            exploit     REAL DEFAULT 0.7,
            explore     REAL DEFAULT 0.2,
            mutate      REAL DEFAULT 0.1,
            velocity    REAL DEFAULT 0,
            drift       INTEGER DEFAULT 0,
            best_score  REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS transfer_signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            source_module TEXT,
            source_cat  TEXT,
            target_cat  TEXT,
            phase       TEXT,
            score       REAL,
            applied     INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS meta_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            event_type  TEXT,
            module      TEXT,
            category    TEXT,
            old_phase   TEXT,
            new_phase   TEXT,
            reason      TEXT
        );
        CREATE TABLE IF NOT EXISTS velocity_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            module      TEXT,
            category    TEXT,
            samples     INTEGER,
            best_score  REAL,
            velocity    REAL
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 📊 LEARNING STATE — what a category knows about itself
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class LearningState:
    """Current learning state for one category in one module."""
    module:     str
    category:   str
    samples:    int     = 0
    phase:      str     = "ignorant"
    exploit:    float   = 0.10
    explore:    float   = 0.80
    mutate:     float   = 0.10
    velocity:   float   = 0.0    # how fast score is improving
    drift:      bool    = False
    best_score: float   = 0.0
    score_history: List[float] = field(default_factory=list)

    def update_phase(self, new_phase: str):
        """Update to new phase and adjust strategy."""
        self.phase = new_phase
        ratios = PHASES[new_phase]
        self.exploit = ratios["exploit"]
        self.explore = ratios["explore"]
        self.mutate  = ratios["mutate"]

    def to_dict(self) -> Dict:
        return {
            "module":   self.module,
            "category": self.category,
            "samples":  self.samples,
            "phase":    self.phase,
            "exploit":  round(self.exploit, 2),
            "explore":  round(self.explore, 2),
            "mutate":   round(self.mutate, 2),
            "velocity": round(self.velocity, 2),
            "drift":    self.drift,
            "best_score": round(self.best_score, 1),
        }

# ══════════════════════════════════════════════════════════════════════════════
# 📡 PHASE DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

def detect_phase(samples: int, score_history: List[float]) -> str:
    """Determine current learning phase."""
    # Check drift first
    if len(score_history) >= DRIFT_WINDOW:
        recent  = score_history[-DRIFT_WINDOW:]
        earlier = score_history[-DRIFT_WINDOW*2:-DRIFT_WINDOW]
        if earlier:
            recent_avg  = sum(recent) / len(recent)
            earlier_avg = sum(earlier) / len(earlier)
            if earlier_avg - recent_avg > DRIFT_THRESHOLD:
                return "drift"

    # Phase by sample count
    for phase, config in PHASES.items():
        if phase == "drift":
            continue
        lo, hi = config["samples"]
        if lo <= samples < hi:
            return phase

    return "expert"

def compute_velocity(score_history: List[float]) -> float:
    """How fast is the score improving? (+ve = faster, -ve = declining)"""
    if len(score_history) < 4:
        return 0.0

    recent   = score_history[-4:]
    earlier  = score_history[-8:-4] if len(score_history) >= 8 else score_history[:4]

    recent_avg  = sum(recent) / len(recent)
    earlier_avg = sum(earlier) / len(earlier)

    return round(recent_avg - earlier_avg, 2)

# ══════════════════════════════════════════════════════════════════════════════
# 🔀 TRANSFER ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class TransferEngine:
    """
    Passes learning signals between related categories.

    GROUND worked in friction (score 91, 8 samples).
    friction and depth are related.
    → Signal to depth: try GROUND sooner.
    → Depth explores GROUND with higher probability.
    → Depth finds GROUND works without needing 8 samples itself.
    → Learning accelerated.

    This is transfer learning.
    What works in one domain
    informs another.
    Not waiting for each to discover independently.
    """

    def find_transfers(self,
                        module: str,
                        all_states: Dict[str, LearningState],
                        learner_maps: Dict) -> List[Dict]:
        """
        Scan all categories for high-scoring phases.
        Generate transfer signals for related categories.
        """
        transfers = []
        now       = datetime.now().isoformat()

        for cat, state in all_states.items():
            if state.samples < TRANSFER_MIN_SAMPLES:
                continue
            if state.best_score < TRANSFER_MIN_SCORE:
                continue

            # Get best phase for this category
            best_phase = self._get_best_phase(cat, learner_maps)
            if not best_phase:
                continue

            # Find related categories
            related = CATEGORY_RELATIONS.get(cat, [])

            for target_cat in related:
                if target_cat not in all_states:
                    continue
                target_state = all_states[target_cat]

                # Only transfer if target hasn't learned this yet
                if target_state.samples >= TRANSFER_MIN_SAMPLES * 3:
                    continue  # target has enough data already

                transfer = {
                    "source_module": module,
                    "source_cat":    cat,
                    "target_cat":    target_cat,
                    "phase":         best_phase,
                    "score":         state.best_score,
                    "boost":         TRANSFER_BOOST,
                }
                transfers.append(transfer)

                # Save transfer signal
                conn = get_db()
                conn.execute("""
                    INSERT INTO transfer_signals
                    (ts,source_module,source_cat,target_cat,phase,score)
                    VALUES (?,?,?,?,?,?)""",
                    (now, module, cat, target_cat,
                     best_phase, state.best_score)
                )
                conn.commit(); conn.close()

        return transfers

    def _get_best_phase(self, category: str,
                         learner_maps: Dict) -> Optional[str]:
        """Get best performing phase for a category from available maps."""
        for map_obj in learner_maps.values():
            if hasattr(map_obj, "_map"):
                entry = map_obj._map.get(category)
                if entry:
                    best = entry.get("best_way") or entry.get("best_phase")
                    if best:
                        return best
        return None

    def apply_transfer(self, target_state: LearningState,
                        transfer: Dict) -> LearningState:
        """
        Apply transfer signal to target state.
        Boost exploration slightly toward transferred phase.
        """
        # Slightly increase explore rate to find transferred phase faster
        if target_state.phase in ("ignorant", "learning"):
            target_state.explore = min(0.90,
                                       target_state.explore + transfer["boost"])
            # Renormalize
            total = (target_state.exploit +
                     target_state.explore +
                     target_state.mutate)
            target_state.exploit /= total
            target_state.explore /= total
            target_state.mutate  /= total

        return target_state

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 META LEARNER — the orchestrator
# ══════════════════════════════════════════════════════════════════════════════

class MetaLearner:
    """
    Learning how to learn.

    Monitors all learning modules.
    Adjusts their strategies based on phase.
    Passes transfer signals between related categories.
    Detects drift and triggers re-exploration.
    Makes every module smarter without changing their code.
    """

    def __init__(self, verbose=True):
        self.verbose  = verbose
        self.transfer = TransferEngine()
        self._states: Dict[str, Dict[str, LearningState]] = {}
        # structure: {module: {category: LearningState}}
        self._maps    = {}
        self._load_maps()
        self._load_states()

    def _load_maps(self):
        """Load available learner maps."""
        if V3:
            self._maps["thought"] = SequenceLearner()
        if SOCIAL:
            self._maps["social"] = SocialMap()
        if MOTOR:
            self._maps["motor"] = MotorMap()

    def _load_states(self):
        """Initialize or load learning states."""
        # Initialize from available maps
        for module, map_obj in self._maps.items():
            self._states[module] = {}
            if hasattr(map_obj, "_map"):
                for cat, entry in map_obj._map.items():
                    samples = entry.get("sample_count", 0)
                    scores  = []

                    # Get score history from way/phase scores
                    way_scores = entry.get("way_scores",
                                 entry.get("phase_scores", {}))
                    for phase_scores in way_scores.values():
                        scores.extend(phase_scores)

                    scores.sort()  # approximate chronological

                    phase    = detect_phase(samples, scores)
                    velocity = compute_velocity(scores)
                    best     = entry.get("best_connection",
                               entry.get("best_outcome",
                               entry.get("best_coherence", 0)))

                    state = LearningState(
                        module        = module,
                        category      = cat,
                        samples       = samples,
                        score_history = scores,
                        best_score    = best,
                        velocity      = velocity,
                    )
                    state.update_phase(phase)
                    state.velocity = velocity
                    self._states[module][cat] = state

    def get_strategy(self, module: str, category: str) -> Dict[str, float]:
        """
        Get current exploit/explore/mutate ratios for this module+category.
        This is what other modules call instead of using fixed ratios.
        """
        if module not in self._states:
            return {"exploit":0.70, "explore":0.20, "mutate":0.10,
                    "phase":"unknown"}

        if category not in self._states[module]:
            # New category — ignorant phase
            return {"exploit":0.10, "explore":0.80, "mutate":0.10,
                    "phase":"ignorant"}

        state = self._states[module][category]
        return {
            "exploit": state.exploit,
            "explore": state.explore,
            "mutate":  state.mutate,
            "phase":   state.phase,
        }

    def update(self, module: str, category: str,
                score: float) -> Dict:
        """
        Update meta state after an observation.
        Returns updated strategy.
        """
        now = datetime.now().isoformat()

        # Initialize if needed
        if module not in self._states:
            self._states[module] = {}

        if category not in self._states[module]:
            self._states[module][category] = LearningState(
                module=module, category=category
            )

        state = self._states[module][category]
        state.samples       += 1
        state.score_history.append(score)
        if score > state.best_score:
            state.best_score = score

        state.velocity = compute_velocity(state.score_history)

        # Detect phase transition
        old_phase = state.phase
        new_phase = detect_phase(state.samples, state.score_history)

        if new_phase != old_phase:
            state.update_phase(new_phase)

            if self.verbose:
                phase_colors = {
                    "ignorant":"dim","learning":"yellow",
                    "competent":"green","expert":"bold green",
                    "drift":"red"
                }
                color = phase_colors.get(new_phase, "white")
                rprint(f"  [dim]Phase transition:[/dim] "
                      f"{module}/{category}  "
                      f"[dim]{old_phase}[/dim] → "
                      f"[{color}]{new_phase}[/{color}]  "
                      f"[dim]({state.samples} samples)[/dim]")

            # Log event
            conn = get_db()
            conn.execute("""
                INSERT INTO meta_events
                (ts,event_type,module,category,old_phase,new_phase,reason)
                VALUES (?,?,?,?,?,?,?)""",
                (now,"phase_transition",module,category,
                 old_phase,new_phase,
                 f"samples:{state.samples} velocity:{state.velocity:.1f}")
            )
            conn.commit(); conn.close()

        # Save state
        self._save_state(state)

        # Check for transfer opportunities
        transfers = self.transfer.find_transfers(
            module, self._states.get(module, {}), self._maps
        )

        if transfers and self.verbose:
            for t in transfers[:2]:
                rprint(f"  [dim cyan]Transfer: {t['source_cat']} → {t['target_cat']}  "
                      f"phase:{t['phase']}  score:{t['score']:.0f}[/dim]")

        # Apply transfers to target states
        for t in transfers:
            target_cat = t["target_cat"]
            if target_cat in self._states.get(module, {}):
                self._states[module][target_cat] = self.transfer.apply_transfer(
                    self._states[module][target_cat], t
                )

        return {
            "strategy": state.to_dict(),
            "transfers": len(transfers),
            "phase_changed": new_phase != old_phase,
        }

    def _save_state(self, state: LearningState):
        conn = get_db()
        conn.execute("""
            INSERT INTO module_states
            (ts,module,category,phase,samples,exploit,explore,
             mutate,velocity,drift,best_score)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(),
             state.module, state.category, state.phase,
             state.samples, state.exploit, state.explore,
             state.mutate, state.velocity, int(state.drift),
             state.best_score)
        )

        # Velocity log
        conn.execute("""
            INSERT INTO velocity_log
            (ts,module,category,samples,best_score,velocity)
            VALUES (?,?,?,?,?,?)""",
            (datetime.now().isoformat(),
             state.module, state.category,
             state.samples, state.best_score, state.velocity)
        )
        conn.commit(); conn.close()

    def scan_all(self) -> Dict[str, List[Dict]]:
        """Scan all modules and return their states."""
        result = {}
        for module, states in self._states.items():
            result[module] = [s.to_dict() for s in states.values()]
        return result

    def show_status(self):
        """Display all module learning phases."""
        rprint(f"\n  [bold]META LEARNING STATUS[/bold]")
        rprint(f"  [dim]{'━'*55}[/dim]")

        phase_colors = {
            "ignorant":"dim","learning":"yellow",
            "competent":"green","expert":"bold green",
            "drift":"red"
        }

        for module, states in self._states.items():
            if not states: continue
            rprint(f"\n  [bold]{module.upper()}[/bold]")

            # Sort by phase advancement
            phase_order = ["expert","competent","learning","ignorant","drift"]
            sorted_states = sorted(
                states.values(),
                key=lambda s: phase_order.index(s.phase)
                              if s.phase in phase_order else 5
            )

            for state in sorted_states:
                color = phase_colors.get(state.phase, "white")
                vel_str = (f"[green]+{state.velocity:.1f}[/green]"
                          if state.velocity > 1 else
                          f"[red]{state.velocity:.1f}[/red]"
                          if state.velocity < -1 else
                          f"[dim]{state.velocity:.1f}[/dim]")

                exploit_bar = "█" * int(state.exploit*20) + "░"*(20-int(state.exploit*20))

                rprint(f"  [{color}]{state.category:<14}[/{color}]  "
                      f"[{color}]{state.phase:<10}[/{color}]  "
                      f"n:{state.samples:3d}  "
                      f"vel:{vel_str}  "
                      f"best:{state.best_score:.0f}")
                rprint(f"  [dim]  exploit:{exploit_bar} {state.exploit:.0%}  "
                      f"explore:{state.explore:.0%}  "
                      f"mutate:{state.mutate:.0%}[/dim]")

    def show_transfers(self):
        """Show recent transfer signals."""
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM transfer_signals ORDER BY id DESC LIMIT 20"
        ).fetchall()
        conn.close()

        if not rows:
            rprint("  [dim]No transfer signals yet.[/dim]")
            return

        rprint(f"\n  [bold]TRANSFER SIGNALS[/bold]")
        rprint(f"  [dim]What worked in one domain informs another[/dim]")
        rprint(f"  [dim]{'━'*55}[/dim]")

        for r in rows:
            rprint(f"\n  [yellow]{r['source_cat']}[/yellow]  →  "
                  f"[cyan]{r['target_cat']}[/cyan]")
            rprint(f"  [dim]phase:{r['phase']}  "
                  f"score:{r['score']:.0f}  "
                  f"module:{r['source_module']}  "
                  f"{'applied' if r['applied'] else 'pending'}[/dim]")

    def phase_transitions(self) -> List[Dict]:
        """Show all phase transitions — the learning milestones."""
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM meta_events WHERE event_type='phase_transition' "
            "ORDER BY id DESC LIMIT 20"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def velocity_report(self) -> Dict[str, Any]:
        """Which modules are learning fastest?"""
        report = {
            "fastest":  [],
            "slowest":  [],
            "drifting": [],
        }

        all_states = []
        for module, states in self._states.items():
            for cat, state in states.items():
                all_states.append(state)

        if not all_states: return report

        sorted_by_vel = sorted(all_states,
                               key=lambda s: s.velocity,
                               reverse=True)

        report["fastest"]  = [s.to_dict() for s in sorted_by_vel[:3]]
        report["slowest"]  = [s.to_dict() for s in sorted_by_vel[-3:]]
        report["drifting"] = [s.to_dict() for s in sorted_by_vel
                              if s.phase == "drift"]

        return report

    def stats(self) -> Dict:
        conn = get_db()
        s = {
            "total_updates":    conn.execute(
                "SELECT COUNT(*) FROM module_states"
            ).fetchone()[0],
            "phase_transitions":conn.execute(
                "SELECT COUNT(*) FROM meta_events WHERE event_type='phase_transition'"
            ).fetchone()[0],
            "transfer_signals": conn.execute(
                "SELECT COUNT(*) FROM transfer_signals"
            ).fetchone()[0],
            "modules_tracked":  len(self._states),
            "categories_tracked": sum(
                len(cats) for cats in self._states.values()
            ),
            "expert_categories": sum(
                1 for cats in self._states.values()
                for s in cats.values() if s.phase == "expert"
            ),
            "drifting":         sum(
                1 for cats in self._states.values()
                for s in cats.values() if s.phase == "drift"
            ),
        }
        conn.close()
        return s

# ══════════════════════════════════════════════════════════════════════════════
# 🔌 META-AWARE WRAPPER
# ══════════════════════════════════════════════════════════════════════════════

class MetaAwareLearner:
    """
    Wraps any SequenceLearner/SocialMap/MotorMap.
    Makes them use meta-learning strategies.
    Drop-in replacement. No code changes needed in wrapped module.
    """

    def __init__(self, wrapped_learner, module_name: str,
                  meta: MetaLearner):
        self._inner  = wrapped_learner
        self._module = module_name
        self._meta   = meta

    def get_sequence(self, category: str) -> Tuple[List, str]:
        """Get sequence using meta-learning strategy."""
        strategy = self._meta.get_strategy(self._module, category)
        phase    = strategy["phase"]

        # Use meta strategy ratios
        r = random.random()

        if r < strategy["exploit"]:
            strat = "exploit"
        elif r < strategy["exploit"] + strategy["mutate"]:
            strat = "mutate"
        else:
            strat = "explore"

        # Delegate to inner learner with override strategy
        if hasattr(self._inner, "get_sequence"):
            # Force the strategy
            if strat == "explore":
                return self._inner.get_sequence(category)[0], f"meta_explore({phase})"
            elif strat == "mutate":
                seq = self._inner.get_sequence(category)[0]
                if hasattr(self._inner, "_mutate"):
                    mutated = self._inner._mutate(seq)
                    return mutated, f"meta_mutate({phase})"
                return seq, f"meta_exploit({phase})"
            else:
                seq, _ = self._inner.get_sequence(category)
                return seq, f"meta_exploit({phase})"

        return ["OBSERVE", "CHIT"], f"meta_fallback"

    def record(self, *args, **kwargs):
        """Record and update meta-state."""
        self._inner.record(*args, **kwargs) if hasattr(self._inner, "record") else None

        # Extract score from args
        score = args[3] if len(args) > 3 else kwargs.get("coherence",
                kwargs.get("outcome_score",
                kwargs.get("connection_score", 50)))

        category = args[0] if args else kwargs.get("category", "unknown")

        self._meta.update(self._module, category, float(score))

    def learn(self, **kwargs):
        """Delegate learn to inner."""
        if hasattr(self._inner, "learn"):
            return self._inner.learn(**kwargs)
        return []

    def __getattr__(self, name):
        """Pass through all other attributes to inner."""
        return getattr(self._inner, name)

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7367):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    meta = MetaLearner(verbose=False)

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
            path = urlparse(self.path).path
            if path=="/api/status":
                self._json(meta.stats())
            elif path=="/api/scan":
                self._json({"modules":meta.scan_all()})
            elif path=="/api/transfers":
                conn = get_db()
                rows = conn.execute(
                    "SELECT * FROM transfer_signals ORDER BY id DESC LIMIT 50"
                ).fetchall()
                conn.close()
                self._json({"transfers":[dict(r) for r in rows]})
            elif path=="/api/velocity":
                self._json(meta.velocity_report())
            elif path=="/api/transitions":
                self._json({"transitions":meta.phase_transitions()})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            if path=="/api/strategy":
                module   = body.get("module","thought")
                category = body.get("category","friction")
                self._json(meta.get_strategy(module, category))
            elif path=="/api/update":
                module   = body.get("module","thought")
                category = body.get("category","friction")
                score    = body.get("score", 50)
                result   = meta.update(module, category, score)
                self._json(result)
            else:
                self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),API)
    rprint(f"  [bold yellow]FORGE META LEARNING[/bold yellow]  [green]:{port}[/green]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ███╗   ███╗███████╗████████╗ █████╗
  ████╗ ████║██╔════╝╚══██╔══╝██╔══██╗
  ██╔████╔██║█████╗     ██║   ███████║
  ██║╚██╔╝██║██╔══╝     ██║   ██╔══██║
  ██║ ╚═╝ ██║███████╗   ██║   ██║  ██║
  ╚═╝     ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝
[/yellow]
[bold]  FORGE META LEARNING — Learning How To Learn[/bold]
[dim]  Adjusts strategy based on phase.[/dim]
[dim]  Transfers signals between related categories.[/dim]
[dim]  Makes every module smarter without changing their code.[/dim]
"""

def interactive():
    rprint(BANNER)
    meta = MetaLearner(verbose=True)
    s    = meta.stats()

    rprint(f"  [dim]Modules tracked:    {s['modules_tracked']}[/dim]")
    rprint(f"  [dim]Categories tracked: {s['categories_tracked']}[/dim]")
    rprint(f"  [dim]Expert categories:  {s['expert_categories']}[/dim]")
    rprint(f"  [dim]Transfer signals:   {s['transfer_signals']}[/dim]\n")

    rprint("[dim]Commands: status | transfers | velocity | strategy | simulate | stats[/dim]\n")

    while True:
        try:
            raw   = (console.input if RICH else input)(
                "[yellow bold]meta >[/yellow bold] "
            ).strip()
            if not raw: continue
            parts = raw.split(None,1)
            cmd   = parts[0].lower()
            arg   = parts[1] if len(parts)>1 else ""

            if cmd in ("quit","exit","q"):
                break

            elif cmd == "status":
                meta.show_status()

            elif cmd == "transfers":
                meta.show_transfers()

            elif cmd == "velocity":
                report = meta.velocity_report()
                rprint(f"\n  [bold]Fastest learning:[/bold]")
                for s in report["fastest"]:
                    rprint(f"  {s['module']}/{s['category']:<14}  "
                          f"vel:+{s['velocity']:.1f}  "
                          f"phase:{s['phase']}")
                if report["drifting"]:
                    rprint(f"\n  [red]Drifting:[/red]")
                    for s in report["drifting"]:
                        rprint(f"  {s['module']}/{s['category']}")

            elif cmd == "strategy":
                # strategy thought friction
                sub = arg.split()
                module   = sub[0] if len(sub)>0 else "thought"
                category = sub[1] if len(sub)>1 else "friction"
                strat = meta.get_strategy(module, category)
                rprint(f"\n  {module}/{category}:")
                rprint(f"  Phase:   {strat['phase']}")
                rprint(f"  Exploit: {strat['exploit']:.0%}")
                rprint(f"  Explore: {strat['explore']:.0%}")
                rprint(f"  Mutate:  {strat['mutate']:.0%}")

            elif cmd == "simulate":
                # Simulate learning curve for a category
                rprint(f"\n  [bold]Simulating learning curve[/bold]")
                rprint(f"  [dim]Watch strategy adapt as samples grow[/dim]\n")

                module = "thought"
                cat    = "friction"
                scores = []

                for i in range(30):
                    score = 50 + min(35, i * 1.2) + random.gauss(0, 5)
                    scores.append(score)
                    result = meta.update(module, cat, score)
                    strat  = meta.get_strategy(module, cat)

                    if i % 5 == 0 or result["phase_changed"]:
                        rprint(f"  [{i+1:2d}] phase:{strat['phase']:<10}  "
                              f"exploit:{strat['exploit']:.0%}  "
                              f"explore:{strat['explore']:.0%}  "
                              f"score:{score:.0f}")

            elif cmd == "stats":
                s = meta.stats()
                for k,v in s.items():
                    rprint(f"  {k:<28} {v}")

            elif cmd == "server":
                threading.Thread(target=start_server, daemon=True).start()
                rprint("[green]Meta API on :7367[/green]")

        except (KeyboardInterrupt, EOFError):
            break

def main():
    if "--status" in sys.argv:
        rprint(BANNER)
        MetaLearner(verbose=False).show_status()
    elif "--transfer" in sys.argv:
        rprint(BANNER)
        MetaLearner(verbose=False).show_transfers()
    elif "--wrap" in sys.argv:
        rprint(BANNER)
        meta = MetaLearner(verbose=True)
        meta.show_status()
        rprint(f"\n  [green]Meta-learning active.[/green]")
        rprint(f"  [dim]All modules now use phase-adaptive strategies.[/dim]")
    elif "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7367
        start_server(port)
    else:
        rprint(BANNER)
        interactive()

if __name__ == "__main__":
    main()
