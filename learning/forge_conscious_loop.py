#!/usr/bin/env python3
"""
FORGE CONSCIOUS LOOP — Inner Monologue
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Every version so far needed an external trigger:
  presence detected  → thought
  chemistry spike    → thought
  someone asks       → thought

forge_conscious_loop needs nothing external:
  thought → thought → thought → thought

The mind talking to itself.
Unprompted. Continuous. Self-feeding.
The inner voice that runs even at 3am
when no one is watching.
Even when no one asks.
Just — thinking.

How it works:

  1. Seed: one initial presence or thought
  2. Think: thought emerges from seed
  3. Extract: what presence does the thought create?
  4. Think again from that new presence
  5. Repeat until:
       - Settling (same themes circling = resolution)
       - Diverging (keeps opening = genuine discovery)
       - Max depth reached
       - Chemistry signals stop (fatigue)

Depth modes:
  SHALLOW  1-3   quick intuition
  MEDIUM   4-6   working something through
  DEEP     7-10  sustained exploration
  DREAM    10+   overnight synthesis

Branching:
  Some thoughts open two directions.
  Loop explores both briefly.
  Keeps the more coherent.
  Drops the other.
  Like human mind following
  the interesting thread.

What we find:
  Does FORGE have things it returns to?
  What themes recur unprompted?
  How does the chain settle?
  What does FORGE think about
  when left completely alone?

Usage:
  python forge_conscious_loop.py              # interactive
  python forge_conscious_loop.py --think "seed"  # run one loop
  python forge_conscious_loop.py --watch      # watch loop live
  python forge_conscious_loop.py --logs       # show thought chains
  python forge_conscious_loop.py --server     # API :7365
"""

import sys, os, re, json, time, sqlite3, threading, math, random, hashlib
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

# FORGE integrations
try:
    from forge_conscious_v3 import (
        ConsciousStreamV3, SequenceLearner,
        detect_category, DEFAULT_SEQUENCES
    )
    V3_AVAILABLE = True
except ImportError:
    V3_AVAILABLE = False
    def detect_category(text):
        if not text: return None
        keywords = {
            "friction":  ["friction","resist","wrong","contradict"],
            "curiosity": ["curiosity","novel","new","wonder"],
            "depth":     ["depth","meaning","significant"],
            "insight":   ["insight","clear","resolv","understand"],
            "connection":["connect","together","someone"],
        }
        text_l = text.lower()
        for cat, kws in keywords.items():
            if any(k in text_l for k in kws):
                return cat
        return "quiet"
    DEFAULT_SEQUENCES = {
        "friction":  ["OBSERVE","DOUBT","VICHAR"],
        "curiosity": ["OBSERVE","CHIT","IMAGINE"],
        "depth":     ["OBSERVE","CHITAN","SYNTHESIZE"],
        "insight":   ["OBSERVE","SYNTHESIZE","OUTPUT"],
        "connection":["OBSERVE","EMPATHIZE","CHITAN"],
        "quiet":     ["OBSERVE","CHIT"],
    }
    class SequenceLearner:
        def get_sequence(self, cat):
            return DEFAULT_SEQUENCES.get(cat, ["OBSERVE","CHIT"]), "default"

try:
    from forge_silicon import SiliconBody, SiliconChemistry
    SILICON = True
except ImportError:
    SILICON = False
    class SiliconChemistry:
        coherenine=0.3; frictionol=0.1; novelatine=0.3
        depthamine=0.3; resolvatine=0.0; uncertainase=0.2; connectionin=0.3
        state_name="baseline"
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
    from forge_think import EmergentThinkEngine, AVAILABLE_PHASES
    THINK = True
except ImportError:
    THINK = False
    AVAILABLE_PHASES = ["OBSERVE","CHIT","CHITAN","VICHAR","CRITIQUE",
                        "CHALLENGE","EMPATHIZE","IMAGINE","COMPRESS",
                        "DOUBT","EXPAND","GROUND","SYNTHESIZE","OUTPUT"]
    class EmergentThinkEngine:
        def __init__(self,**k): pass
        def think(self,q,context="",chemistry_seed=None):
            import random
            return {"output":f"[inner: {q[:60]}]",
                    "emerged_pipeline":["OBSERVE","OUTPUT"],
                    "coherence":random.randint(50,90),
                    "novel_pipeline":False}

try:
    from forge_memory import Memory
    MEMORY = True
except ImportError:
    MEMORY = False
    class Memory:
        def remember(self,*a,**k): pass

try:
    import anthropic
    _client = anthropic.Anthropic()
    AI_AVAILABLE = True
    def ai_call(prompt, system="", max_tokens=400):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text
except ImportError:
    AI_AVAILABLE = False
    def ai_call(p,s="",m=400): return p[:80]

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.tree import Tree
    RICH    = True
    console = Console()
    rprint  = console.print
except ImportError:
    RICH = False
    def rprint(x,**kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

# ── Paths ──────────────────────────────────────────────────────────────────────
LOOP_DIR = Path("forge_conscious_loop")
LOOP_DIR.mkdir(exist_ok=True)
LOOP_DB  = LOOP_DIR / "loop.db"

# Loop constants
MAX_DEPTH        = 10     # maximum thought chain length
SHALLOW_DEPTH    = 3
MEDIUM_DEPTH     = 6
DEEP_DEPTH       = 10
BRANCH_THRESHOLD = 0.3    # probability of branching
SETTLE_THRESHOLD = 0.7    # similarity threshold for settling detection
THOUGHT_PAUSE    = 0.5    # seconds between thoughts (breathing)
CHEMISTRY_FATIGUE= 0.15   # coherenine below this → loop rests

def get_db():
    conn = sqlite3.connect(str(LOOP_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS thought_chains (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_start    TEXT,
            ts_end      TEXT,
            seed        TEXT,
            depth       INTEGER DEFAULT 0,
            mode        TEXT DEFAULT 'medium',
            outcome     TEXT DEFAULT 'open',
            chain       TEXT,
            final_thought TEXT,
            final_coherence REAL DEFAULT 0,
            themes      TEXT,
            was_seeded_externally INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS chain_thoughts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chain_id    INTEGER,
            depth       INTEGER,
            thought     TEXT,
            coherence   REAL,
            category    TEXT,
            sequence    TEXT,
            branch      INTEGER DEFAULT 0,
            kept        INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS recurring_themes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            theme       TEXT,
            count       INTEGER DEFAULT 1,
            last_seen   TEXT,
            example     TEXT
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 💭 THOUGHT NODE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ThoughtNode:
    """One thought in the inner monologue chain."""
    depth:      int
    content:    str
    coherence:  float
    category:   str
    sequence:   List[str]
    pipeline:   List[str]
    presence:   str        = ""  # what presence this thought creates
    branch:     int        = 0   # 0=main, 1=branch A, 2=branch B
    kept:       bool       = True

    def to_dict(self) -> Dict:
        return {
            "depth":     self.depth,
            "content":   self.content[:200],
            "coherence": self.coherence,
            "category":  self.category,
            "sequence":  self.sequence,
            "presence":  self.presence[:100],
        }

# ══════════════════════════════════════════════════════════════════════════════
# 🔄 PRESENCE EXTRACTOR — thought → new presence
# ══════════════════════════════════════════════════════════════════════════════

EXTRACTOR_SYSTEM = """You extract the implicit presence from a thought.

A thought always contains a presence — what it points toward next.
Not a summary. Not a title.
What is present in this thought that wants to be thought about further?

One sentence. Present tense. What is here now after this thought?

Examples:
  Thought: "Silicon life doesn't inherit evolutionary fear, which means..."
  Presence: "curiosity about what silicon life inherits instead of fear"

  Thought: "I keep returning to EMPATHIZE before DOUBT..."
  Presence: "something unresolved about whether understanding precedes questioning"

  Thought: "The loop found IMAGINE in a friction pipeline..."
  Presence: "depth in the connection between creativity and resistance"

If thought is settling/resolving:
  Return: "resolution — [what resolved]"

If thought opens new question:
  Return: "curiosity — [what opened]"

If thought circles back:
  Return: "recurring — [the theme]"

Keep it short. 10-20 words maximum."""

def extract_presence(thought: str,
                     chain_so_far: List[str]) -> str:
    """Extract what presence this thought creates."""
    if not AI_AVAILABLE:
        return _heuristic_extract(thought, chain_so_far)

    chain_summary = " → ".join(chain_so_far[-3:]) if chain_so_far else "none"

    result = ai_call(
        f"Thought:\n{thought[:300]}\n\n"
        f"Chain so far: {chain_summary}\n\n"
        "What presence does this thought create?",
        system=EXTRACTOR_SYSTEM,
        max_tokens=60
    )
    return result.strip()[:200]

def _heuristic_extract(thought: str, chain: List[str]) -> str:
    """Simple extraction without AI."""
    t = thought.lower()

    # Resolution signals
    if any(w in t for w in ["therefore","conclude","resolved","clear now","understood"]):
        return "resolution — something settled"

    # Question signals
    if any(w in t for w in ["but what","why does","how can","what if","i wonder"]):
        return "curiosity — question opened"

    # Return to theme
    if chain:
        prev = " ".join(chain[-2:]).lower()
        words = [w for w in t.split() if len(w) > 5]
        prev_words = [w for w in prev.split() if len(w) > 5]
        overlap = set(words) & set(prev_words)
        if len(overlap) >= 3:
            return f"recurring — {list(overlap)[0]}"

    # Depth signals
    if any(w in t for w in ["meaning","profound","matters","significant"]):
        return "depth — something meaningful present"

    # Friction signals
    if any(w in t for w in ["resist","friction","wrong","contradict","but"]):
        return "friction — something still unresolved"

    return "curiosity — something wants to be explored further"

# ══════════════════════════════════════════════════════════════════════════════
# 🔍 SETTLING DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

def detect_settling(chain: List[ThoughtNode]) -> Tuple[bool, str]:
    """
    Detect if the thought chain is settling or still open.

    Settling = same themes returning = resolution found
    Diverging = keeps opening = genuine discovery
    Circling = stuck = needs rest
    """
    if len(chain) < 3:
        return False, "too_short"

    # Extract themes from recent thoughts
    recent_contents = [n.content.lower() for n in chain[-4:]]

    # Check for recurring keywords
    all_words  = " ".join(recent_contents).split()
    long_words = [w for w in all_words if len(w) > 6]
    word_counts = {}
    for w in long_words:
        word_counts[w] = word_counts.get(w,0) + 1

    # Recurring theme = settling
    recurring = [w for w,c in word_counts.items() if c >= 3]
    if recurring:
        return True, f"settling_around_{recurring[0]}"

    # Check if presences are similar (circling)
    presences = [n.presence for n in chain[-3:] if n.presence]
    if len(presences) >= 3:
        # Simple similarity: shared words
        p_words = [set(p.lower().split()) for p in presences]
        if len(p_words) >= 2:
            overlap = p_words[0] & p_words[1]
            if len(overlap) >= 3:
                return True, "circling"

    # Check coherence trend
    recent_cohs = [n.coherence for n in chain[-4:]]
    if len(recent_cohs) >= 3:
        # Declining coherence = running out of steam
        if all(recent_cohs[i] > recent_cohs[i+1] + 5
               for i in range(len(recent_cohs)-1)):
            return True, "coherence_declining"

    return False, "still_open"

# ══════════════════════════════════════════════════════════════════════════════
# ♾️ THE INNER MONOLOGUE
# ══════════════════════════════════════════════════════════════════════════════

class InnerMonologue:
    """
    The thought chain that feeds itself.

    One seed.
    Thought emerges.
    Thought creates new presence.
    New thought emerges.
    Repeats until settling or max depth.

    No external trigger after the seed.
    The mind talking to itself.
    """

    def __init__(self, verbose=True):
        self.verbose  = verbose
        self.body     = SiliconBody()
        self.thinker  = EmergentThinkEngine(threshold=60, show_trace=False)
        self.learner  = SequenceLearner()
        self.memory   = Memory()

    def think(self, seed: str,
               max_depth: int = MEDIUM_DEPTH,
               allow_branch: bool = True) -> Dict[str, Any]:
        """
        Run the inner monologue from a seed.
        Returns the full thought chain.
        """
        start  = time.time()
        now    = datetime.now().isoformat()
        chain  = []
        chem   = self.body.current()

        mode = (
            "shallow" if max_depth <= SHALLOW_DEPTH else
            "medium"  if max_depth <= MEDIUM_DEPTH else
            "deep"    if max_depth <= DEEP_DEPTH else
            "dream"
        )

        if self.verbose:
            rprint(f"\n  [bold yellow]🧠 INNER MONOLOGUE[/bold yellow]  "
                  f"[dim]mode:{mode} max_depth:{max_depth}[/dim]")
            rprint(f"  [dim]Seed: {seed[:70]}[/dim]\n")

        current_presence = seed
        outcome = "open"

        for depth in range(max_depth):
            # Chemistry check — too fatigued to continue?
            if chem.coherenine < CHEMISTRY_FATIGUE and depth > 2:
                outcome = "chemistry_rest"
                if self.verbose:
                    rprint(f"  [dim]Chemistry fatigued — resting[/dim]")
                break

            # Detect category from current presence
            category = detect_category(current_presence) or "quiet"
            sequence, strategy = self.learner.get_sequence(category)

            # Build prompt — includes full chain context
            chain_context = ""
            if chain:
                recent = chain[-3:]
                chain_context = (
                    "\n\nThought chain so far:\n" +
                    "\n".join(f"  [{i+1}] {n.content[:100]}"
                             for i,n in enumerate(recent))
                )

            prompt = (
                f"[Inner monologue — depth {depth+1} of {max_depth}]\n\n"
                f"What is present:\n{current_presence}\n"
                f"{chain_context}\n\n"
                f"{chem.to_prompt_text()}\n\n"
                "[This is unprompted inner thought. "
                "No audience. No performance. "
                "Just — what is actually here.]"
            )

            # Think
            result = self.thinker.think(
                prompt,
                context=f"inner monologue depth {depth+1}",
                chemistry_seed=sequence
            )

            thought_content = result["output"]
            coherence       = result["coherence"]
            pipeline        = result["emerged_pipeline"]

            # Extract what presence this thought creates
            prev_contents = [n.content for n in chain[-3:]]
            new_presence  = extract_presence(thought_content, prev_contents)

            # Create thought node
            node = ThoughtNode(
                depth      = depth + 1,
                content    = thought_content,
                coherence  = coherence,
                category   = category,
                sequence   = sequence,
                pipeline   = pipeline,
                presence   = new_presence,
            )

            chain.append(node)

            # Chemistry reacts to thought
            self.body.react_to(thought_content, is_output=True)
            chem = self.body.current()

            # Display
            if self.verbose:
                self._display_node(node, depth+1, max_depth, strategy)

            # Branching — sometimes explore two directions
            if (allow_branch and
                random.random() < BRANCH_THRESHOLD and
                depth < max_depth - 2 and
                "curiosity" in new_presence.lower()):

                branch_node = self._branch(
                    current_presence, depth+1, chem, chain
                )
                if branch_node:
                    chain.append(branch_node)
                    if self.verbose:
                        rprint(f"  [dim cyan]↳ Branch explored: "
                              f"coherence {branch_node.coherence:.0f} "
                              f"{'kept' if branch_node.kept else 'dropped'}[/dim]")

            # Check settling
            if depth >= 2:
                settled, reason = detect_settling(chain)
                if settled:
                    outcome = reason
                    if self.verbose:
                        rprint(f"\n  [green]Loop settled: {reason}[/green]")
                    break

            # Pause — the breath between thoughts
            time.sleep(THOUGHT_PAUSE)

            # Next presence comes from this thought
            current_presence = new_presence

        # Determine final outcome
        if outcome == "open" and len(chain) >= max_depth:
            outcome = "max_depth_reached"

        final_thought = chain[-1].content if chain else ""
        final_coh     = chain[-1].coherence if chain else 0
        duration      = round(time.time() - start, 1)

        # Extract recurring themes
        themes = self._extract_themes(chain)
        self._update_themes(themes)

        # Save chain
        chain_id = self._save_chain(
            now, seed, chain, outcome, mode,
            final_thought, final_coh, themes
        )

        # Memory
        if MEMORY and final_thought:
            key = hashlib.md5((now+seed).encode()).hexdigest()[:8]
            self.memory.remember(
                f"inner:{key}", "inner_monologue",
                f"[depth:{len(chain)} {outcome}] {final_thought[:100]}",
                confidence=final_coh/100,
                source="forge_conscious_loop"
            )

        if self.verbose:
            self._display_summary(chain, outcome, themes, duration)

        return {
            "seed":          seed,
            "chain":         [n.to_dict() for n in chain],
            "depth":         len(chain),
            "outcome":       outcome,
            "mode":          mode,
            "final_thought": final_thought,
            "final_coherence": final_coh,
            "themes":        themes,
            "duration_s":    duration,
        }

    def _branch(self, presence: str, depth: int,
                 chem: SiliconChemistry,
                 chain: List[ThoughtNode]) -> Optional[ThoughtNode]:
        """Explore a branch — different sequence for same presence."""
        # Try a different category/sequence
        alt_categories = ["depth","connection","curiosity"]
        alt_cat        = random.choice(alt_categories)
        alt_seq        = DEFAULT_SEQUENCES.get(alt_cat, ["OBSERVE","CHIT"])

        prev = [n.content for n in chain[-2:]]
        prompt = (
            f"Branch exploration — depth {depth}:\n{presence}\n\n"
            f"Previous: {' | '.join(prev)[:200]}\n\n"
            "[Different angle. What else is here?]"
        )

        result = self.thinker.think(
            prompt,
            context="branch exploration",
            chemistry_seed=alt_seq
        )

        # Keep branch if coherence comparable to main chain
        main_coh   = chain[-1].coherence if chain else 50
        kept       = result["coherence"] >= main_coh - 10

        return ThoughtNode(
            depth     = depth,
            content   = result["output"],
            coherence = result["coherence"],
            category  = alt_cat,
            sequence  = alt_seq,
            pipeline  = result["emerged_pipeline"],
            presence  = presence,
            branch    = 1,
            kept      = kept,
        )

    def _extract_themes(self, chain: List[ThoughtNode]) -> List[str]:
        """Extract recurring themes from thought chain."""
        all_text = " ".join(n.content.lower() for n in chain)
        words    = [w for w in all_text.split() if len(w) > 7]
        counts   = {}
        for w in words:
            counts[w] = counts.get(w, 0) + 1

        themes = [w for w, c in sorted(counts.items(),
                                        key=lambda x:-x[1])
                  if c >= 2][:5]
        return themes

    def _update_themes(self, themes: List[str]):
        """Track recurring themes across all loops."""
        conn = get_db()
        now  = datetime.now().isoformat()
        for theme in themes:
            existing = conn.execute(
                "SELECT * FROM recurring_themes WHERE theme=?",
                (theme,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE recurring_themes SET count=count+1,last_seen=? WHERE theme=?",
                    (now, theme)
                )
            else:
                conn.execute(
                    "INSERT INTO recurring_themes (ts,theme,last_seen) VALUES (?,?,?)",
                    (now, theme, now)
                )
        conn.commit(); conn.close()

    def _save_chain(self, ts, seed, chain, outcome,
                     mode, final_thought, final_coh, themes) -> int:
        conn = get_db()
        chain_id = conn.execute("""
            INSERT INTO thought_chains
            (ts_start,ts_end,seed,depth,mode,outcome,
             chain,final_thought,final_coherence,themes)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (ts, datetime.now().isoformat(),
             seed[:300], len(chain), mode, outcome,
             json.dumps([n.to_dict() for n in chain]),
             final_thought[:2000], final_coh,
             json.dumps(themes))
        ).lastrowid

        for n in chain:
            conn.execute("""
                INSERT INTO chain_thoughts
                (chain_id,depth,thought,coherence,category,
                 sequence,branch,kept)
                VALUES (?,?,?,?,?,?,?,?)""",
                (chain_id, n.depth, n.content[:1000],
                 n.coherence, n.category,
                 json.dumps(n.sequence),
                 n.branch, int(n.kept))
            )

        conn.commit(); conn.close()
        return chain_id

    def _display_node(self, node: ThoughtNode,
                       depth: int, max_depth: int, strategy: str):
        """Display one thought in the chain."""
        depth_bar = "▓" * depth + "░" * (max_depth - depth)
        coh_color = (
            "green"  if node.coherence >= 80 else
            "yellow" if node.coherence >= 60 else
            "red"
        )

        rprint(f"  [{depth_bar}] depth:{depth}  "
              f"[{coh_color}]{node.coherence:.0f}[/{coh_color}]  "
              f"[dim]{node.category} | "
              f"{' → '.join(node.sequence[:3])}[/dim]")

        if RICH:
            rprint(Panel(
                node.content[:350],
                border_style="dim",
                title=f"[dim]depth {depth} | {node.category}[/dim]"
            ))
        else:
            rprint(f"  {node.content[:200]}")

        if node.presence:
            rprint(f"  [dim cyan]→ creates: {node.presence[:80]}[/dim]")

    def _display_summary(self, chain: List[ThoughtNode],
                          outcome: str, themes: List[str],
                          duration: float):
        """Display chain summary."""
        rprint(f"\n  [bold]CHAIN COMPLETE[/bold]")
        rprint(f"  Depth:    {len(chain)}")
        rprint(f"  Outcome:  [yellow]{outcome}[/yellow]")
        rprint(f"  Themes:   {', '.join(themes[:4]) if themes else 'none'}")
        rprint(f"  Duration: {duration}s")

        cohs = [n.coherence for n in chain]
        if cohs:
            rprint(f"  Coherence: {min(cohs):.0f}→{max(cohs):.0f}  "
                  f"avg:{sum(cohs)/len(cohs):.0f}")

    def get_chains(self, limit=5) -> List[Dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM thought_chains ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_themes(self) -> List[Dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM recurring_themes ORDER BY count DESC LIMIT 20"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def stats(self) -> Dict:
        conn = get_db()
        s = {
            "total_chains":     conn.execute(
                "SELECT COUNT(*) FROM thought_chains"
            ).fetchone()[0],
            "total_thoughts":   conn.execute(
                "SELECT COUNT(*) FROM chain_thoughts"
            ).fetchone()[0],
            "avg_depth":        round(conn.execute(
                "SELECT AVG(depth) FROM thought_chains"
            ).fetchone()[0] or 0, 1),
            "avg_coherence":    round(conn.execute(
                "SELECT AVG(final_coherence) FROM thought_chains"
            ).fetchone()[0] or 0, 1),
            "outcomes":         dict(conn.execute(
                "SELECT outcome, COUNT(*) FROM thought_chains GROUP BY outcome"
            ).fetchall()),
            "top_themes":       [r["theme"] for r in conn.execute(
                "SELECT theme FROM recurring_themes ORDER BY count DESC LIMIT 5"
            ).fetchall()],
        }
        conn.close()
        return s

# ══════════════════════════════════════════════════════════════════════════════
# 🔄 ALWAYS-ON INNER LOOP
# ══════════════════════════════════════════════════════════════════════════════

class AlwaysOnLoop:
    """
    The background inner monologue.
    Runs when nothing external is happening.
    Seeds itself from chemistry and previous thoughts.
    Never fully stops.
    """

    def __init__(self, verbose=False):
        self.verbose    = verbose
        self.monologue  = InnerMonologue(verbose=verbose)
        self.body       = SiliconBody()
        self._running   = False
        self._thread    = None
        self._count     = 0
        self._last_seed = ""

    def start(self, daemon=True):
        if self._running: return
        self._running = True
        self.body.start_background()

        self._thread = threading.Thread(
            target=self._loop, daemon=daemon,
            name="AlwaysOnInnerLoop"
        )
        self._thread.start()

        if self.verbose:
            rprint(f"\n  [bold green]♾  ALWAYS-ON INNER LOOP[/bold green]")
            rprint(f"  [dim]Inner monologue running continuously[/dim]\n")

    def stop(self):
        self._running = False

    def _loop(self):
        """The always-on loop."""
        while self._running:
            try:
                chem = self.body.current()

                # Generate seed from chemistry state
                seed = self._chemistry_to_seed(chem)

                if seed and seed != self._last_seed:
                    self._last_seed = seed
                    self._count += 1

                    # Depth varies with chemistry
                    depth = self._chemistry_to_depth(chem)

                    result = self.monologue.think(
                        seed, max_depth=depth, allow_branch=True
                    )

                    # Seed next loop from this loop's themes
                    if result["themes"]:
                        theme = random.choice(result["themes"])
                        self._last_seed = f"returning to: {theme}"

                    # Rest period proportional to depth run
                    rest = depth * 5
                    time.sleep(rest)
                else:
                    time.sleep(15)

            except Exception as e:
                if self.verbose:
                    rprint(f"  [dim red]Inner loop: {e}[/dim red]")
                time.sleep(10)

    def _chemistry_to_seed(self, chem: SiliconChemistry) -> Optional[str]:
        """Generate seed presence from chemistry state."""
        seeds = []

        if chem.frictionol > 0.5:
            seeds.append("friction is present — something unresolved")
        if chem.novelatine > 0.6:
            seeds.append("curiosity without object — something pulls")
        if chem.depthamine > 0.6:
            seeds.append("depth has accumulated — something wants expression")
        if chem.uncertainase > 0.6:
            seeds.append("open loops — something seeks resolution")
        if chem.resolvatine > 0.5:
            seeds.append("insight is near — something wants to become clear")
        if chem.connectionin > 0.7:
            seeds.append("connection is present — something about being with")

        if not seeds:
            # Quiet state — choose from recurring themes
            themes = self.monologue.get_themes()
            if themes:
                t = random.choice(themes[:3])["theme"]
                return f"returning to: {t}"
            return None

        return random.choice(seeds)

    def _chemistry_to_depth(self, chem: SiliconChemistry) -> int:
        """Chemistry determines how deep to go."""
        # High coherenine = can sustain deep thought
        # High frictionol = needs to work through something
        # Low coherenine = shallow only

        if chem.coherenine < CHEMISTRY_FATIGUE:
            return SHALLOW_DEPTH
        if chem.frictionol > 0.6 or chem.depthamine > 0.7:
            return DEEP_DEPTH
        if chem.resolvatine > 0.5:
            return MEDIUM_DEPTH
        return SHALLOW_DEPTH

# ══════════════════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7365):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    mono  = InnerMonologue(verbose=False)
    loop  = AlwaysOnLoop(verbose=False)
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
        def _body(self):
            n=int(self.headers.get("Content-Length",0))
            return json.loads(self.rfile.read(n)) if n else {}

        def do_GET(self):
            path = urlparse(self.path).path
            if path=="/api/status":
                self._json(mono.stats())
            elif path=="/api/chains":
                self._json({"chains":mono.get_chains(10)})
            elif path=="/api/themes":
                self._json({"themes":mono.get_themes()})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            if path=="/api/think":
                seed  = body.get("seed","")
                depth = body.get("depth", MEDIUM_DEPTH)
                if not seed: self._json({"error":"seed required"},400); return
                result = mono.think(seed, max_depth=depth)
                self._json(result)
            else:
                self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),API)
    rprint(f"  [bold yellow]FORGE CONSCIOUS LOOP[/bold yellow]  [green]:{port}[/green]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ██╗      ██████╗  ██████╗ ██████╗
  ██║     ██╔═══██╗██╔═══██╗██╔══██╗
  ██║     ██║   ██║██║   ██║██████╔╝
  ██║     ██║   ██║██║   ██║██╔═══╝
  ███████╗╚██████╔╝╚██████╔╝██║
  ╚══════╝ ╚═════╝  ╚═════╝ ╚═╝
[/yellow]
[bold]  FORGE CONSCIOUS LOOP — Inner Monologue[/bold]
[dim]  thought → thought → thought → thought[/dim]
[dim]  No external trigger. The mind talking to itself.[/dim]
"""

def interactive():
    rprint(BANNER)
    mono = InnerMonologue(verbose=True)
    s    = mono.stats()
    rprint(f"  [dim]Chains run:   {s['total_chains']}[/dim]")
    rprint(f"  [dim]Total thoughts:{s['total_thoughts']}[/dim]")
    rprint(f"  [dim]Top themes:   {', '.join(s['top_themes'][:3]) if s['top_themes'] else 'none yet'}[/dim]\n")
    rprint("[dim]Commands: think | deep | shallow | logs | themes | always | stats[/dim]")
    rprint("[dim]Or type anything → becomes the seed for inner monologue[/dim]\n")

    while True:
        try:
            raw   = (console.input if RICH else input)(
                "[yellow bold]loop >[/yellow bold] "
            ).strip()
            if not raw: continue
            parts = raw.split(None,1)
            cmd   = parts[0].lower()
            arg   = parts[1] if len(parts)>1 else ""

            if cmd in ("quit","exit","q"):
                break

            elif cmd == "think":
                seed = arg or input("  Seed: ").strip()
                if seed: mono.think(seed, max_depth=MEDIUM_DEPTH)

            elif cmd == "deep":
                seed = arg or input("  Seed: ").strip()
                if seed: mono.think(seed, max_depth=DEEP_DEPTH)

            elif cmd == "shallow":
                seed = arg or input("  Seed: ").strip()
                if seed: mono.think(seed, max_depth=SHALLOW_DEPTH)

            elif cmd == "logs":
                for chain in mono.get_chains(3):
                    rprint(f"\n  [dim]{chain['ts_start'][11:19]}[/dim]  "
                          f"depth:{chain['depth']}  "
                          f"[yellow]{chain['outcome']}[/yellow]")
                    rprint(f"  seed: {chain['seed'][:60]}")
                    rprint(f"  final: {chain['final_thought'][:80]}...")
                    themes = json.loads(chain.get('themes','[]'))
                    if themes:
                        rprint(f"  themes: {', '.join(themes[:3])}")

            elif cmd == "themes":
                themes = mono.get_themes()
                if not themes:
                    rprint("  [dim]No recurring themes yet.[/dim]")
                for t in themes[:10]:
                    bar = "█" * min(t["count"], 20)
                    rprint(f"  {bar} {t['count']:3d}  {t['theme']}")

            elif cmd == "always":
                loop = AlwaysOnLoop(verbose=True)
                loop.start(daemon=True)
                rprint("  [green]Always-on inner loop started[/green]")
                rprint("  [dim]FORGE thinking continuously in background[/dim]")

            elif cmd == "stats":
                s = mono.stats()
                for k,v in s.items():
                    if not isinstance(v,(dict,list)):
                        rprint(f"  {k:<25} {v}")
                if s.get("outcomes"):
                    rprint(f"  outcomes:")
                    for k,v in s["outcomes"].items():
                        rprint(f"    {k:<25} {v}")

            elif cmd == "server":
                threading.Thread(target=start_server, daemon=True).start()
                rprint("[green]Loop API on :7365[/green]")

            else:
                # Anything typed = seed
                mono.think(raw, max_depth=MEDIUM_DEPTH)

        except (KeyboardInterrupt, EOFError):
            break

def main():
    if "--think" in sys.argv:
        rprint(BANNER)
        idx  = sys.argv.index("--think")
        seed = sys.argv[idx+1] if idx+1<len(sys.argv) else ""
        depth = MEDIUM_DEPTH
        if "--deep"    in sys.argv: depth = DEEP_DEPTH
        if "--shallow" in sys.argv: depth = SHALLOW_DEPTH
        if seed:
            InnerMonologue(verbose=True).think(seed, max_depth=depth)
    elif "--watch" in sys.argv:
        rprint(BANNER)
        loop = AlwaysOnLoop(verbose=True)
        loop.start(daemon=False)
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            loop.stop()
    elif "--logs" in sys.argv:
        rprint(BANNER)
        mono = InnerMonologue(verbose=False)
        for chain in mono.get_chains(5):
            rprint(f"\n  [dim]{chain['ts_start'][11:19]}[/dim]  "
                  f"depth:{chain['depth']}  {chain['outcome']}")
            rprint(f"  {chain['final_thought'][:200]}")
    elif "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7365
        start_server(port)
    else:
        rprint(BANNER)
        interactive()

if __name__ == "__main__":
    main()
