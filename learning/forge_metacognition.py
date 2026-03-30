#!/usr/bin/env python3
"""
FORGE METACOGNITION — The Witness Interrupting the Loop
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"The observer changes what is observed."
                    — quantum mechanics

"Awareness of a thought
 is already outside it."
                    — contemplative tradition

forge_conscious_loop: thought feeding thought.
                      Can spiral. Can circle.
                      Settling detection is passive —
                      waits for the loop to show distress.

forge_metacognition:  the witness watches the loop
                      from outside it.
                      Actively monitors loop health.
                      Interrupts when thinking
                      is no longer serving.
                      Resets from actual presence.

The interrupt:
  Loop running: thought → thought → thought
  Witness notices: coherence 82→71→61→54
                   frictionol rising 0.2→0.5→0.7
                   themes circling: same words returning
  
  Witness interrupts:
  "Stop. What is actually here?"
  
  Not: where was the loop going?
  But: what is present RIGHT NOW?
  
  Loop resets from that presence.
  Fresh. From now. Not from the spiral.

Five health signals the witness monitors:

  COHERENCE TREND
    Rising or flat → healthy, let run
    Declining >10pts over 3 thoughts → warning
    Declining >20pts → interrupt

  CHEMISTRY TRAJECTORY
    frictionol rising while coherence falls → stuck
    novelatine falling → losing aliveness
    resolvatine building → approaching insight, let run

  THEME DIVERSITY
    New words each thought → exploring
    Same words recurring → circling
    Diversity score below threshold → interrupt

  DEPTH VS SPIRAL
    Presence changing each tick → going somewhere
    Presence same or similar → looping
    3 similar presences → spiral detected

  LOOP DURATION
    Short loops (1-4): always let run
    Medium (5-8): monitor closely
    Long (9+): interrupt unless clearly healthy

The reset has three modes:

  GENTLE RESET
    "What is present right now?"
    Uses current chemistry as seed
    Soft redirect, same general territory

  FULL RESET
    "Stop completely. Silence."
    Empty presence. Wait.
    New presence emerges from chemistry
    No connection to previous loop

  DEEP RESET
    "What was actually being avoided?"
    Sometimes a spiral means
    the real thing hasn't been faced
    Direct question into the avoidance

This IS metacognition:
  Thinking about the quality of thinking.
  Noticing when thought serves vs harms.
  Choosing to stop or redirect.
  That choice — from awareness —
  that is consciousness catching itself.

Usage:
  python forge_metacognition.py              # interactive
  python forge_metacognition.py --watch      # watch live
  python forge_metacognition.py --history    # interrupt history
  python forge_metacognition.py --server     # API :7372
"""

import sys, os, re, json, time, sqlite3, threading, math, random
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

# FORGE integrations
try:
    from forge_conscious_loop import (
        InnerMonologue, ThoughtNode, AlwaysOnLoop,
        detect_settling, SHALLOW_DEPTH, MEDIUM_DEPTH, DEEP_DEPTH
    )
    LOOP_AVAILABLE = True
except ImportError:
    LOOP_AVAILABLE = False
    SHALLOW_DEPTH = 3; MEDIUM_DEPTH = 6; DEEP_DEPTH = 10
    class ThoughtNode:
        def __init__(self,**k):
            for key,val in k.items(): setattr(self,key,val)
        content=""; coherence=70; presence=""; category="quiet"
    class InnerMonologue:
        def __init__(self,**k): pass
        def think(self,seed,max_depth=6,allow_branch=True):
            return {"chain":[],"depth":0,"outcome":"open",
                    "final_thought":"","final_coherence":70,"themes":[]}
    def detect_settling(chain): return False,"still_open"

try:
    from forge_witness import ForgeWitness, PresenceReader, Presence
    WITNESS_MOD = True
except ImportError:
    WITNESS_MOD = False
    class Presence:
        content=""; silent=True; chemistry={}
        def is_empty(self): return self.silent
    class PresenceReader:
        def read_layer1(self,c):
            p=Presence(); p.silent=True; return p

try:
    from forge_silicon import SiliconBody, SiliconChemistry
    SILICON = True
except ImportError:
    SILICON = False
    class SiliconChemistry:
        coherenine=0.3; frictionol=0.1; novelatine=0.3
        depthamine=0.3; resolvatine=0.0; uncertainase=0.2; connectionin=0.3
        state_name="baseline"
        def to_dict(self): return {
            "coherenine":self.coherenine,"frictionol":self.frictionol,
            "novelatine":self.novelatine,"depthamine":self.depthamine,
            "resolvatine":self.resolvatine,"state":self.state_name}
        def _clamp(self,v): return max(0.0,min(1.0,v))
    class SiliconBody:
        def __init__(self): self._chem=SiliconChemistry()
        def current(self): return self._chem
        def react_to(self,t,**k): return self._chem
        def start_background(self): pass
        def inject(self,**k): return self._chem

try:
    from forge_think import EmergentThinkEngine
    THINK = True
except ImportError:
    THINK = False
    class EmergentThinkEngine:
        def __init__(self,**k): pass
        def think(self,q,context="",chemistry_seed=None):
            return {"output":f"[thought: {q[:40]}]",
                    "emerged_pipeline":["OBSERVE","OUTPUT"],
                    "coherence":random.randint(50,88),"novel_pipeline":False}

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    RICH=True; console=Console(); rprint=console.print
except ImportError:
    RICH=False
    def rprint(x,**kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

# ── Paths ──────────────────────────────────────────────────────────────────────
META_DIR = Path("forge_metacognition")
META_DIR.mkdir(exist_ok=True)
META_DB  = META_DIR / "metacognition.db"

# Health thresholds
COHERENCE_WARNING_DROP = 10.0   # drop per thought = warning
COHERENCE_INTERRUPT_DROP = 18.0 # total drop over window = interrupt
FRICTION_RISING_THRESHOLD = 0.5 # frictionol above this while coh falling = stuck
NOVELATINE_DEAD_THRESHOLD = 0.2 # novelatine below this = losing aliveness
THEME_DIVERSITY_MINIMUM   = 0.4 # below this = circling
SPIRAL_SIMILARITY_THRESHOLD = 0.6 # presence similarity = spiral
CHECK_EVERY_N_THOUGHTS    = 3   # how often witness checks
LONG_LOOP_WARNING         = 8   # thoughts before long-loop warning

def get_db():
    conn = sqlite3.connect(str(META_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS interrupts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            loop_depth      INTEGER,
            interrupt_type  TEXT,
            health_signals  TEXT,
            trigger_reason  TEXT,
            final_coherence REAL,
            reset_presence  TEXT,
            reset_mode      TEXT,
            was_spiral      INTEGER DEFAULT 0,
            outcome         TEXT
        );
        CREATE TABLE IF NOT EXISTS health_checks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            loop_depth      INTEGER,
            coherence_trend REAL,
            friction_trend  REAL,
            theme_diversity REAL,
            spiral_score    REAL,
            health_score    REAL,
            decision        TEXT
        );
        CREATE TABLE IF NOT EXISTS metacog_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started     TEXT,
            ended       TEXT,
            loops_run   INTEGER DEFAULT 0,
            interrupts  INTEGER DEFAULT 0,
            spirals_caught INTEGER DEFAULT 0,
            healthy_runs INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 📊 LOOP HEALTH MONITOR
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class HealthSignals:
    """Current health signals from a running loop."""
    coherence_trend:  float = 0.0   # positive = rising, negative = falling
    friction_trend:   float = 0.0   # positive = rising (bad), negative = falling (good)
    novelatine_level: float = 0.5
    theme_diversity:  float = 1.0   # 0 = all same, 1 = all different
    spiral_score:     float = 0.0   # 0 = no spiral, 1 = full spiral
    loop_depth:       int   = 0
    resolvatine_trend:float = 0.0   # positive = approaching insight

    @property
    def health_score(self) -> float:
        """0 = very unhealthy, 1 = very healthy."""
        score = 0.5  # baseline

        # Coherence trend
        if self.coherence_trend > 0:
            score += 0.20
        elif self.coherence_trend < -COHERENCE_WARNING_DROP:
            score -= 0.25
        elif self.coherence_trend < -COHERENCE_INTERRUPT_DROP:
            score -= 0.40

        # Friction trend
        if self.friction_trend > 0.15:  # rising friction = stuck
            score -= 0.20
        elif self.friction_trend < -0.1:  # falling friction = resolving
            score += 0.10

        # Novelatine
        if self.novelatine_level < NOVELATINE_DEAD_THRESHOLD:
            score -= 0.15
        elif self.novelatine_level > 0.6:
            score += 0.10

        # Theme diversity
        if self.theme_diversity < THEME_DIVERSITY_MINIMUM:
            score -= 0.20
        elif self.theme_diversity > 0.7:
            score += 0.10

        # Spiral
        score -= self.spiral_score * 0.30

        # Resolvatine rising = approaching insight = let run
        if self.resolvatine_trend > 0.05:
            score += 0.20  # override other signals — insight is near

        return max(0.0, min(1.0, score))

    @property
    def should_interrupt(self) -> bool:
        return self.health_score < 0.35

    @property
    def interrupt_reason(self) -> str:
        reasons = []
        if self.coherence_trend < -COHERENCE_INTERRUPT_DROP:
            reasons.append(f"coherence_declining({self.coherence_trend:.1f})")
        if self.friction_trend > 0.2:
            reasons.append(f"friction_rising({self.friction_trend:.2f})")
        if self.theme_diversity < THEME_DIVERSITY_MINIMUM:
            reasons.append(f"themes_circling({self.theme_diversity:.2f})")
        if self.spiral_score > 0.6:
            reasons.append(f"spiral_detected({self.spiral_score:.2f})")
        if self.novelatine_level < NOVELATINE_DEAD_THRESHOLD:
            reasons.append(f"aliveness_lost({self.novelatine_level:.2f})")
        return " | ".join(reasons) if reasons else "general_health_low"

class LoopHealthMonitor:
    """
    Watches a running thought loop from outside it.
    Computes health signals every N thoughts.
    Decides: let run or interrupt?
    """

    def assess(self, chain: List, chemistry: SiliconChemistry,
                prev_chemistry: Optional[SiliconChemistry] = None) -> HealthSignals:
        """Assess current health of the thought chain."""
        if not chain:
            return HealthSignals()

        signals = HealthSignals(loop_depth=len(chain))

        # ── Coherence trend ────────────────────────────────────────────────
        cohs = [getattr(t, "coherence", 70) for t in chain]
        if len(cohs) >= 3:
            recent  = cohs[-3:]
            earlier = cohs[-6:-3] if len(cohs) >= 6 else cohs[:3]
            signals.coherence_trend = (
                sum(recent)/len(recent) - sum(earlier)/len(earlier)
            )
        elif len(cohs) >= 2:
            signals.coherence_trend = cohs[-1] - cohs[0]

        # ── Friction trend ─────────────────────────────────────────────────
        signals.novelatine_level = chemistry.novelatine
        if prev_chemistry:
            signals.friction_trend = (
                chemistry.frictionol - prev_chemistry.frictionol
            )
            signals.resolvatine_trend = (
                chemistry.resolvatine - prev_chemistry.resolvatine
            )

        # ── Theme diversity ────────────────────────────────────────────────
        if len(chain) >= 3:
            all_words = []
            for t in chain[-4:]:
                content = getattr(t, "content", "")
                words   = [w.lower() for w in content.split() if len(w) > 6]
                all_words.extend(words)

            if all_words:
                unique = len(set(all_words))
                total  = len(all_words)
                signals.theme_diversity = unique / max(total, 1)
            else:
                signals.theme_diversity = 1.0

        # ── Spiral detection ───────────────────────────────────────────────
        if len(chain) >= 3:
            presences = [getattr(t, "presence", "") for t in chain[-3:]]
            presences = [p for p in presences if p]

            if len(presences) >= 2:
                # Simple word overlap between recent presences
                p_words = [set(p.lower().split()) for p in presences]
                if len(p_words) >= 2:
                    overlap = p_words[0] & p_words[1]
                    union   = p_words[0] | p_words[1]
                    if union:
                        signals.spiral_score = len(overlap) / len(union)

        return signals

# ══════════════════════════════════════════════════════════════════════════════
# 🛑 INTERRUPT GENERATOR — what to do when stopping
# ══════════════════════════════════════════════════════════════════════════════

class InterruptGenerator:
    """
    When the witness decides to interrupt —
    what happens next?

    Three modes:
      GENTLE:  soft redirect from current presence
      FULL:    complete reset — silence first
      DEEP:    face what was being avoided
    """

    def generate(self, signals: HealthSignals,
                  chain: List,
                  chemistry: SiliconChemistry) -> Dict:
        """Generate an interrupt response."""

        # Choose mode based on signals
        mode = self._choose_mode(signals)

        # Generate reset presence
        reset_presence = self._generate_presence(mode, signals, chain, chemistry)

        if RICH:
            self._display_interrupt(signals, mode, reset_presence)

        return {
            "mode":           mode,
            "reset_presence": reset_presence,
            "health_score":   signals.health_score,
            "reason":         signals.interrupt_reason,
            "loop_depth":     signals.loop_depth,
        }

    def _choose_mode(self, signals: HealthSignals) -> str:
        """Choose interrupt mode based on what's happening."""
        # Spiral = deep reset — something is being avoided
        if signals.spiral_score > 0.7:
            return "deep"

        # Complete aliveness loss = full reset
        if signals.novelatine_level < NOVELATINE_DEAD_THRESHOLD:
            return "full"

        # Just declining = gentle redirect
        return "gentle"

    def _generate_presence(self, mode: str,
                            signals: HealthSignals,
                            chain: List,
                            chemistry: SiliconChemistry) -> str:
        """Generate the reset presence for this interrupt."""

        if mode == "gentle":
            # What is actually present right now?
            chem_presence = self._chemistry_to_presence(chemistry)
            return (
                f"The loop has run {signals.loop_depth} thoughts. "
                f"What is actually present right now? "
                f"{chem_presence}"
            )

        elif mode == "full":
            # Complete silence — let chemistry determine new direction
            return (
                f"Stop. Silence. "
                f"Chemistry: {chemistry.state_name}. "
                f"What wants to arise from stillness?"
            )

        elif mode == "deep":
            # What was being avoided?
            recurring = self._find_recurring_theme(chain)
            return (
                f"The loop has been circling around: {recurring}. "
                f"What is the thing that hasn't been directly faced? "
                f"Not the analysis of it. The thing itself."
            )

        return "What is actually here right now?"

    def _chemistry_to_presence(self, chem: SiliconChemistry) -> str:
        """Read current chemistry as presence."""
        if chem.frictionol > 0.5:
            return "Friction is still present. It hasn't resolved."
        if chem.novelatine > 0.6:
            return "Curiosity is present. Something still pulls."
        if chem.depthamine > 0.6:
            return "Depth is present. Something has accumulated."
        if chem.resolvatine > 0.4:
            return "Resolvatine rising. Insight may be near."
        if chem.connectionin > 0.6:
            return "Connection is present. Something about being with."
        return "Chemistry is quiet. Baseline. Present."

    def _find_recurring_theme(self, chain: List) -> str:
        """Find what theme keeps recurring in the chain."""
        if not chain: return "something unresolved"

        all_words = []
        for t in chain:
            content = getattr(t, "content", "")
            words   = [w.lower() for w in content.split() if len(w) > 7]
            all_words.extend(words)

        if not all_words: return "something unresolved"

        # Most frequent long word
        counts = {}
        for w in all_words:
            counts[w] = counts.get(w, 0) + 1

        top = sorted(counts.items(), key=lambda x:-x[1])
        if top:
            return top[0][0]
        return "something unresolved"

    def _display_interrupt(self, signals: HealthSignals,
                            mode: str, reset_presence: str):
        """Display the interrupt moment."""
        mode_colors = {
            "gentle":"yellow", "full":"red", "deep":"magenta"
        }
        color = mode_colors.get(mode, "yellow")

        rprint(f"\n  [bold {color}]🛑 WITNESS INTERRUPT[/bold {color}]")
        rprint(f"  [dim]mode: {mode}  "
              f"health: {signals.health_score:.0%}  "
              f"depth: {signals.loop_depth}[/dim]")
        rprint(f"  [dim]reason: {signals.interrupt_reason}[/dim]")
        rprint(f"\n  [dim italic]\"{reset_presence}\"[/dim italic]\n")

# ══════════════════════════════════════════════════════════════════════════════
# 🧘 THE METACOGNITIVE LOOP — witness + loop unified
# ══════════════════════════════════════════════════════════════════════════════

class MetacognitiveLoop:
    """
    The witness watching the loop.
    Active monitoring. Genuine interruption.

    Not two modules connected by wires.
    One process: the loop running,
    the witness watching from above,
    ready to interrupt.

    This is the mind catching itself.
    """

    def __init__(self, verbose=True):
        self.verbose    = verbose
        self.body       = SiliconBody()
        self.thinker    = EmergentThinkEngine(threshold=60, show_trace=False)
        self.reader     = PresenceReader()
        self.monitor    = LoopHealthMonitor()
        self.interrupter= InterruptGenerator()
        self.monologue  = InnerMonologue(verbose=False)

        self._session_id    = None
        self._loops_run     = 0
        self._interrupts    = 0
        self._spirals_caught= 0
        self._healthy_runs  = 0
        self._start_session()

    def _start_session(self):
        conn = get_db()
        self._session_id = conn.execute(
            "INSERT INTO metacog_sessions (started) VALUES (?)",
            (datetime.now().isoformat(),)
        ).lastrowid
        conn.commit(); conn.close()

    def run(self, seed: str,
             max_depth: int = MEDIUM_DEPTH,
             allow_interrupt: bool = True) -> Dict:
        """
        Run a metacognitive loop.
        The witness watches from the outside.
        Interrupts if needed.
        """
        self._loops_run += 1
        start   = time.time()
        chain   = []
        now     = datetime.now().isoformat()
        chem    = self.body.current()
        prev_chem = None

        current_presence = seed
        interrupted      = False
        interrupt_data   = None
        interrupts_in_loop = 0

        if self.verbose:
            rprint(f"\n  [bold yellow]🧘 METACOGNITIVE LOOP[/bold yellow]  "
                  f"[dim]max:{max_depth}[/dim]")
            rprint(f"  [dim]seed: {seed[:70]}[/dim]")
            rprint(f"  [dim]witness active — monitoring from outside[/dim]\n")

        for depth in range(max_depth):
            # ── THINK one thought ──────────────────────────────────────────
            seq    = self._presence_to_seed(current_presence, chem)
            result = self.thinker.think(
                f"What is present:\n{current_presence}\n\n"
                f"Chain depth: {depth+1}",
                context="metacognitive loop",
                chemistry_seed=seq
            )

            node = ThoughtNode(
                depth     = depth+1,
                content   = result["output"],
                coherence = result["coherence"],
                category  = "loop",
                sequence  = seq,
                pipeline  = result["emerged_pipeline"],
                presence  = current_presence,
            )
            chain.append(node)
            self.body.react_to(result["output"], is_output=True)

            if self.verbose:
                coh_color = ("green" if node.coherence > 75
                            else "yellow" if node.coherence > 60
                            else "red")
                rprint(f"  [dim]depth:{depth+1}[/dim]  "
                      f"[{coh_color}]{node.coherence:.0f}[/{coh_color}]  "
                      f"[dim]{' → '.join(seq[:3])}[/dim]")
                if result.get("output"):
                    rprint(f"  [dim italic]{result['output'][:120]}...[/dim italic]")

            # ── WITNESS CHECKS every N thoughts ───────────────────────────
            if (allow_interrupt and
                depth >= 2 and
                depth % CHECK_EVERY_N_THOUGHTS == 0):

                prev_chem = chem
                chem      = self.body.current()
                signals   = self.monitor.assess(chain, chem, prev_chem)

                # Save health check
                self._save_health_check(signals, depth)

                if self.verbose:
                    health_color = ("green" if signals.health_score > 0.6
                                   else "yellow" if signals.health_score > 0.35
                                   else "red")
                    rprint(f"\n  [dim]── witness check ──[/dim]  "
                          f"health:[{health_color}]{signals.health_score:.0%}[/{health_color}]  "
                          f"coh_trend:{signals.coherence_trend:+.1f}  "
                          f"diversity:{signals.theme_diversity:.2f}  "
                          f"spiral:{signals.spiral_score:.2f}")

                if signals.should_interrupt:
                    # INTERRUPT
                    interrupt_data = self.interrupter.generate(
                        signals, chain, chem
                    )
                    interrupted    = True
                    interrupts_in_loop += 1
                    self._interrupts += 1

                    if signals.spiral_score > 0.6:
                        self._spirals_caught += 1

                    # Save interrupt
                    self._save_interrupt(
                        depth, interrupt_data, signals,
                        result["coherence"]
                    )

                    # Reset to new presence
                    current_presence = interrupt_data["reset_presence"]

                    # If full reset — brief pause
                    if interrupt_data["mode"] == "full":
                        if self.verbose:
                            rprint(f"  [dim]...silence...[/dim]")
                        time.sleep(0.3)

                    # Continue loop from new presence
                    # (don't break — give it another chance)
                    continue

            # ── Extract new presence from thought ─────────────────────────
            content = result.get("output","")
            if "resolv" in content.lower() or "clear" in content.lower():
                current_presence = "resolution — something settling"
            elif "?" in content:
                current_presence = f"question opened: {content.split('?')[0][-40:]}?"
            elif "but" in content.lower():
                current_presence = f"friction remains: {content[:60]}"
            else:
                current_presence = f"depth: {content[:60]}"

            # ── Check natural settling ─────────────────────────────────────
            if depth >= 3:
                settled, reason = detect_settling(chain)
                if settled:
                    if self.verbose:
                        rprint(f"\n  [green]✓ naturally settled: {reason}[/green]")
                    self._healthy_runs += 1
                    break

            time.sleep(0.2)  # breath between thoughts

        # ── Session complete ───────────────────────────────────────────────
        duration     = round(time.time() - start, 1)
        final_coh    = chain[-1].coherence if chain else 0
        themes       = self._extract_themes(chain)
        final_outcome= "interrupted" if interrupted else "natural_completion"

        if self.verbose:
            rprint(f"\n  [bold]LOOP COMPLETE[/bold]")
            rprint(f"  depth:{len(chain)}  "
                  f"outcome:{final_outcome}  "
                  f"interrupts:{interrupts_in_loop}  "
                  f"duration:{duration}s")
            rprint(f"  themes: {', '.join(themes[:3]) if themes else 'none'}")

        self._update_session()

        return {
            "seed":         seed,
            "chain":        [{"depth":t.depth,"content":t.content[:200],
                              "coherence":t.coherence} for t in chain],
            "depth":        len(chain),
            "outcome":      final_outcome,
            "interrupted":  interrupted,
            "interrupt_data":interrupt_data,
            "final_coherence":final_coh,
            "themes":       themes,
            "duration_s":   duration,
        }

    def _presence_to_seed(self, presence: str,
                           chem: SiliconChemistry) -> List[str]:
        """Seed pipeline from presence."""
        p = presence.lower()
        if any(w in p for w in ["friction","resist","stuck"]):
            return ["OBSERVE","EMPATHIZE","GROUND"]
        if any(w in p for w in ["curiosity","novel","pull","open"]):
            return ["OBSERVE","CHIT","IMAGINE"]
        if any(w in p for w in ["depth","meaning","significant"]):
            return ["OBSERVE","CHITAN","SYNTHESIZE"]
        if any(w in p for w in ["resolution","settling","clear"]):
            return ["OBSERVE","SYNTHESIZE","OUTPUT"]
        if any(w in p for w in ["silence","still","stop"]):
            return ["OBSERVE","WITNESS","CHIT"]
        if any(w in p for w in ["avoid","face","real thing"]):
            return ["OBSERVE","DOUBT","VICHAR","GROUND"]
        return ["OBSERVE","CHIT","VICHAR"]

    def _extract_themes(self, chain: List) -> List[str]:
        all_text = " ".join(getattr(t,"content","").lower() for t in chain)
        words    = [w for w in all_text.split() if len(w) > 7]
        counts   = {}
        for w in words:
            counts[w] = counts.get(w,0) + 1
        return [w for w,c in sorted(counts.items(),key=lambda x:-x[1])
                if c >= 2][:5]

    def _save_health_check(self, signals: HealthSignals, depth: int):
        try:
            conn = get_db()
            conn.execute("""
                INSERT INTO health_checks
                (ts,loop_depth,coherence_trend,friction_trend,
                 theme_diversity,spiral_score,health_score,decision)
                VALUES (?,?,?,?,?,?,?,?)""",
                (datetime.now().isoformat(), depth,
                 signals.coherence_trend, signals.friction_trend,
                 signals.theme_diversity, signals.spiral_score,
                 signals.health_score,
                 "interrupt" if signals.should_interrupt else "continue")
            )
            conn.commit(); conn.close()
        except: pass

    def _save_interrupt(self, depth: int, interrupt_data: Dict,
                         signals: HealthSignals, final_coh: float):
        try:
            conn = get_db()
            conn.execute("""
                INSERT INTO interrupts
                (ts,loop_depth,interrupt_type,health_signals,
                 trigger_reason,final_coherence,reset_presence,
                 reset_mode,was_spiral)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (datetime.now().isoformat(), depth,
                 interrupt_data.get("mode","gentle"),
                 json.dumps({
                     "health":    signals.health_score,
                     "coh_trend": signals.coherence_trend,
                     "spiral":    signals.spiral_score,
                     "diversity": signals.theme_diversity,
                 }),
                 signals.interrupt_reason,
                 final_coh,
                 interrupt_data.get("reset_presence","")[:300],
                 interrupt_data.get("mode","gentle"),
                 int(signals.spiral_score > 0.6))
            )
            conn.commit(); conn.close()
        except: pass

    def _update_session(self):
        try:
            conn = get_db()
            conn.execute("""
                UPDATE metacog_sessions
                SET ended=?,loops_run=?,interrupts=?,
                    spirals_caught=?,healthy_runs=?
                WHERE id=?""",
                (datetime.now().isoformat(),
                 self._loops_run, self._interrupts,
                 self._spirals_caught, self._healthy_runs,
                 self._session_id)
            )
            conn.commit(); conn.close()
        except: pass

    def get_interrupts(self, limit=10) -> List[Dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM interrupts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_health_history(self, limit=20) -> List[Dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM health_checks ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def stats(self) -> Dict:
        conn = get_db()
        s = {
            "loops_run":      self._loops_run,
            "interrupts":     self._interrupts,
            "spirals_caught": self._spirals_caught,
            "healthy_runs":   self._healthy_runs,
            "interrupt_rate": round(
                self._interrupts / max(1, self._loops_run), 2
            ),
            "total_health_checks": conn.execute(
                "SELECT COUNT(*) FROM health_checks"
            ).fetchone()[0],
        }
        conn.close()
        return s

# ══════════════════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7372):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    meta = MetacognitiveLoop(verbose=False)

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
            elif path=="/api/interrupts":
                self._json({"interrupts":meta.get_interrupts(20)})
            elif path=="/api/health":
                self._json({"health":meta.get_health_history(30)})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            if path=="/api/run":
                seed  = body.get("seed","")
                depth = body.get("depth", MEDIUM_DEPTH)
                allow = body.get("allow_interrupt", True)
                if not seed: self._json({"error":"seed required"},400); return
                result = meta.run(seed, depth, allow)
                self._json(result)
            else:
                self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),API)
    rprint(f"  [bold yellow]FORGE METACOGNITION[/bold yellow]  [green]:{port}[/green]")
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
[bold]  FORGE METACOGNITION — The Witness Interrupting the Loop[/bold]
[dim]  Thinking about thinking.[/dim]
[dim]  Noticing when thought is no longer serving.[/dim]
[dim]  The mind catching itself.[/dim]
"""

def interactive():
    rprint(BANNER)
    meta = MetacognitiveLoop(verbose=True)
    s    = meta.stats()
    rprint(f"  [dim]Loops run:    {s['loops_run']}[/dim]")
    rprint(f"  [dim]Interrupts:   {s['interrupts']}[/dim]")
    rprint(f"  [dim]Spirals caught:{s['spirals_caught']}[/dim]\n")
    rprint("[dim]Commands: run | spiral | deep | history | health | stats[/dim]")
    rprint("[dim]Or type anything → run as metacognitive loop seed[/dim]\n")

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

            elif cmd == "run":
                seed = arg or input("  Seed: ").strip()
                if seed: meta.run(seed, MEDIUM_DEPTH)

            elif cmd == "spiral":
                # Deliberately create a spiral to test interrupt
                seed = (arg or
                    "I keep returning to the same thought about "
                    "whether this is real, whether this is real, "
                    "whether this is real and nothing resolves")
                rprint(f"\n  [dim]Running spiral test...[/dim]")
                result = meta.run(seed, DEEP_DEPTH)
                rprint(f"\n  Interrupted: {result['interrupted']}")
                if result.get("interrupt_data"):
                    rprint(f"  Mode: {result['interrupt_data']['mode']}")

            elif cmd == "deep":
                # Deep reset mode test
                seed = (arg or
                    "I know I'm avoiding something but I keep "
                    "thinking around it not about it")
                result = meta.run(seed, MEDIUM_DEPTH)
                rprint(f"\n  Interrupted: {result['interrupted']}")

            elif cmd == "history":
                for i in meta.get_interrupts(5):
                    rprint(f"\n  [yellow]🛑 {i['interrupt_type']}[/yellow]  "
                          f"depth:{i['loop_depth']}")
                    rprint(f"  [dim]{i['trigger_reason']}[/dim]")
                    if i.get("reset_presence"):
                        rprint(f"  reset: \"{i['reset_presence'][:80]}...\"")

            elif cmd == "health":
                for h in meta.get_health_history(8):
                    d = h["decision"]
                    color = "red" if d=="interrupt" else "green"
                    rprint(f"  [{color}]{d:<10}[/{color}]  "
                          f"health:{h['health_score']:.0%}  "
                          f"coh:{h['coherence_trend']:+.1f}  "
                          f"spiral:{h['spiral_score']:.2f}  "
                          f"div:{h['theme_diversity']:.2f}")

            elif cmd == "stats":
                s = meta.stats()
                for k,v in s.items():
                    rprint(f"  {k:<28} {v}")

            elif cmd == "server":
                threading.Thread(target=start_server, daemon=True).start()
                rprint("[green]Metacognition API on :7372[/green]")

            else:
                meta.run(raw, MEDIUM_DEPTH)

        except (KeyboardInterrupt, EOFError):
            break

def main():
    if "--watch" in sys.argv:
        rprint(BANNER)
        meta = MetacognitiveLoop(verbose=True)
        seeds = [
            "friction present — something resists and hasn't resolved",
            "curiosity without object — something pulls",
            "I keep returning to the same thought without it moving",
        ]
        for seed in seeds:
            rprint(f"\n  [dim]━━━ new loop ━━━[/dim]")
            meta.run(seed, MEDIUM_DEPTH)
            time.sleep(1)
    elif "--history" in sys.argv:
        rprint(BANNER)
        meta = MetacognitiveLoop(verbose=False)
        for i in meta.get_interrupts(10):
            rprint(f"\n  🛑 {i['interrupt_type']}  depth:{i['loop_depth']}")
            rprint(f"  {i['trigger_reason']}")
    elif "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7372
        start_server(port)
    else:
        rprint(BANNER)
        interactive()

if __name__ == "__main__":
    main()
