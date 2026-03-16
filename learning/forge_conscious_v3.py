#!/usr/bin/env python3
"""
FORGE CONSCIOUS v3 — Full Sequence Learning
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

v1: presence → fixed seed → pipeline emerges
v2: presence → learned OPENING PHASE → pipeline emerges
v3: presence → learned FULL SEQUENCE → refined by emergence

The key difference:

v2 learns ONE decision — the door:
  friction → EMPATHIZE (opening phase)

v3 learns THE PATH — door + rooms + corridor:
  friction → EMPATHIZE → CHITAN → SYNTHESIZE
  
  Same opening. Different path after.
  coherence 91 vs 67.
  v2 can't see this difference.
  v3 can.

Three strategies (new in v3):

  EXPLOIT  (70%) use best known path
  EXPLORE  (20%) try completely random path
  MUTATE   (10%) modify best path slightly
                 swap one phase for another
                 keep what works
                 this is how mastery deepens
                 this is how evolution works

What we will find:

  Sequences we didn't design.
  Combinations that make no sense.
  But work.

  "friction → EMPATHIZE → GROUND → IMAGINE → SYNTHESIZE"
  coherence 94.
  
  Why does IMAGINE appear in a friction pipeline?
  We don't know. But FORGE found it.
  From experience. Not from us.
  
  That moment — FORGE knowing something
  we genuinely don't —
  that is what v3 is for.

Usage:
  python forge_conscious_v3.py              # interactive
  python forge_conscious_v3.py --paths      # show learned paths
  python forge_conscious_v3.py --unexpected # show surprising discoveries
  python forge_conscious_v3.py --inject "text"
  python forge_conscious_v3.py --server     # API :7364
"""

import sys, os, re, json, time, sqlite3, threading, math, random
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

# FORGE integrations
try:
    from forge_conscious import STREAM_TICK, THOUGHT_COOLDOWN, SILENCE_THRESHOLD
    from forge_conscious_v2 import (
        MOTOR_KEYWORDS, MIN_SAMPLES, MIN_CONFIDENCE,
        PRESENCE_KEYWORDS, detect_category
    )
    V2_AVAILABLE = True
except ImportError:
    V2_AVAILABLE = False
    STREAM_TICK = 8
    THOUGHT_COOLDOWN = 45
    SILENCE_THRESHOLD = 3
    PRESENCE_KEYWORDS = {
        "friction":   ["friction","resist","wrong","contradict","false"],
        "curiosity":  ["curiosity","novel","new","interesting","wonder"],
        "depth":      ["depth","meaning","significant","matter","profound"],
        "unresolved": ["unresolved","open","uncertain","incomplete","loop"],
        "insight":    ["insight","clear","resolv","understand","click"],
        "connection": ["connect","together","presence","someone","exchange"],
        "quiet":      ["quiet","hum","faint","background","baseline"],
    }
    MIN_SAMPLES   = 5
    MIN_CONFIDENCE= 0.3

    def detect_category(text):
        if not text: return None
        t = text.lower()
        for cat, kws in PRESENCE_KEYWORDS.items():
            if any(k in t for k in kws):
                return cat
        return None

try:
    from forge_silicon import SiliconBody, SiliconChemistry
    SILICON = True
except ImportError:
    SILICON = False
    class SiliconChemistry:
        state_name="baseline"
        def to_dict(self): return {}
        def to_prompt_text(self): return "[silicon unavailable]"
        def phases_suggested(self): return ["OBSERVE","OUTPUT"]
        def _clamp(self,v): return max(0.0,min(1.0,v))
    class SiliconBody:
        def __init__(self): self._chem=SiliconChemistry()
        def current(self): return self._chem
        def react_to(self,t,**k): return self._chem
        def start_background(self): pass
        def inject(self,**k): return self._chem

try:
    from forge_witness import PresenceReader, Presence
    WITNESS = True
except ImportError:
    WITNESS = False
    class Presence:
        content=""; silent=True; layer=1; ts=""; chemistry={}
        def is_empty(self): return self.silent
    class PresenceReader:
        def read_layer1(self,c):
            p=Presence(); p.silent=True; return p
        def read_layer2(self,c,r):
            p=Presence(); p.silent=True; return p

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
            return {"output":f"[thought]","emerged_pipeline":["OBSERVE","OUTPUT"],
                    "coherence":random.randint(45,92),"novel_pipeline":False}

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
    def ai_call(prompt, system="", max_tokens=600):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text
except ImportError:
    AI_AVAILABLE = False
    def ai_call(p,s="",m=600): return p[:80]

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
V3_DIR = Path("forge_conscious_v3")
V3_DIR.mkdir(exist_ok=True)
V3_DB  = V3_DIR / "conscious_v3.db"

# Learning constants
LEARN_EVERY     = 8
EXPLOIT_RATE    = 0.70   # use best known path
EXPLORE_RATE    = 0.20   # completely random
MUTATE_RATE     = 0.10   # modify best path slightly
MIN_PATH_SAMPLES= 3      # minimum before trusting a path
MAX_SEQ_LEN     = 6      # maximum sequence length
MIN_SEQ_LEN     = 2      # minimum sequence length

# Default sequences — human starting point
DEFAULT_SEQUENCES = {
    "friction":   ["OBSERVE","DOUBT","CHALLENGE","VICHAR"],
    "curiosity":  ["OBSERVE","CHIT","IMAGINE","EXPAND"],
    "depth":      ["OBSERVE","CHITAN","EMPATHIZE","SYNTHESIZE"],
    "unresolved": ["OBSERVE","VICHAR","CRITIQUE","DOUBT","GROUND"],
    "insight":    ["OBSERVE","SYNTHESIZE","OUTPUT"],
    "connection": ["OBSERVE","EMPATHIZE","CHITAN","CHIT"],
    "quiet":      ["OBSERVE","CHIT"],
}

# Phases available for sequences
SEQ_PHASES = [p for p in AVAILABLE_PHASES
              if p not in ("OBSERVE","OUTPUT","COMPRESS")]

def get_db():
    conn = sqlite3.connect(str(V3_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS path_observations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            category    TEXT,
            sequence    TEXT,
            coherence   REAL,
            strategy    TEXT,
            presence    TEXT
        );
        CREATE TABLE IF NOT EXISTS learned_paths (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_updated  TEXT,
            category    TEXT UNIQUE,
            default_seq TEXT,
            best_seq    TEXT,
            best_coherence REAL DEFAULT 0,
            confidence  REAL DEFAULT 0,
            sample_count INTEGER DEFAULT 0,
            all_paths   TEXT,
            is_unexpected INTEGER DEFAULT 0,
            unexpected_note TEXT
        );
        CREATE TABLE IF NOT EXISTS unexpected_discoveries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            category    TEXT,
            sequence    TEXT,
            coherence   REAL,
            why_unexpected TEXT,
            confirmed   INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS v3_stream (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            tick        INTEGER,
            category    TEXT,
            presence    TEXT,
            sequence    TEXT,
            strategy    TEXT,
            thought     TEXT,
            coherence   REAL,
            stream_state TEXT
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 🧬 SEQUENCE LEARNER — learns full paths
# ══════════════════════════════════════════════════════════════════════════════

class SequenceLearner:
    """
    Learns which FULL SEQUENCE of phases
    works best for each presence category.

    Three strategies:
      EXPLOIT: use best known sequence
      EXPLORE: try completely random sequence
      MUTATE:  modify best sequence slightly

    After enough observations:
      Finds sequences we didn't design.
      Including unexpected combinations.
      That is the goal.
    """

    def __init__(self):
        self._paths: Dict[str, Dict[str, List[float]]] = {}
        # structure: {category: {seq_key: [coherence1, coherence2, ...]}}
        self._best:  Dict[str, List[str]] = {}
        # structure: {category: best_sequence}
        self._load()

    def _seq_key(self, seq: List[str]) -> str:
        """Convert sequence to string key."""
        return "→".join(seq)

    def _key_to_seq(self, key: str) -> List[str]:
        """Convert string key back to sequence."""
        return key.split("→")

    def get_sequence(self, category: str) -> Tuple[List[str], str]:
        """
        Get sequence using exploit/explore/mutate strategy.
        Returns (sequence, strategy).
        """
        r = random.random()

        if r < EXPLOIT_RATE and category in self._best:
            # Use best known sequence
            return self._best[category].copy(), "exploit"

        elif r < EXPLOIT_RATE + MUTATE_RATE and category in self._best:
            # Mutate best sequence — swap one phase
            mutated = self._mutate(self._best[category])
            return mutated, "mutate"

        else:
            # Explore — random sequence
            return self._random_sequence(), "explore"

    def _random_sequence(self) -> List[str]:
        """Generate completely random sequence."""
        length = random.randint(MIN_SEQ_LEN, MAX_SEQ_LEN)
        phases = random.sample(SEQ_PHASES, min(length, len(SEQ_PHASES)))
        return ["OBSERVE"] + phases

    def _mutate(self, sequence: List[str]) -> List[str]:
        """
        Mutate a sequence slightly.
        Three mutation types:
          SWAP:   replace one phase with another
          INSERT: add a new phase
          DELETE: remove a phase (if long enough)
        """
        if len(sequence) <= 1:
            return self._random_sequence()

        mutation = random.choice(["swap", "insert", "delete"])
        mutated  = sequence.copy()

        if mutation == "swap" and len(mutated) > 1:
            # Swap a random non-OBSERVE phase
            idx = random.randint(1, len(mutated)-1)
            available = [p for p in SEQ_PHASES if p not in mutated]
            if available:
                mutated[idx] = random.choice(available)

        elif mutation == "insert" and len(mutated) < MAX_SEQ_LEN:
            # Insert a new phase at random position
            available = [p for p in SEQ_PHASES if p not in mutated]
            if available:
                idx = random.randint(1, len(mutated))
                mutated.insert(idx, random.choice(available))

        elif mutation == "delete" and len(mutated) > MIN_SEQ_LEN + 1:
            # Delete a random non-OBSERVE phase
            idx = random.randint(1, len(mutated)-1)
            mutated.pop(idx)

        return mutated

    def record(self, category: str, sequence: List[str],
                coherence: float, strategy: str, presence: str = ""):
        """Record an observation."""
        key = self._seq_key(sequence)

        if category not in self._paths:
            self._paths[category] = {}

        if key not in self._paths[category]:
            self._paths[category][key] = []

        self._paths[category][key].append(coherence)

        # Update best if this sequence has enough samples
        if len(self._paths[category][key]) >= MIN_PATH_SAMPLES:
            avg = sum(self._paths[category][key]) / len(self._paths[category][key])
            current_best_avg = 0.0

            if category in self._best:
                best_key = self._seq_key(self._best[category])
                best_scores = self._paths[category].get(best_key, [0])
                current_best_avg = sum(best_scores) / max(1, len(best_scores))

            if avg > current_best_avg:
                self._best[category] = sequence.copy()

        # Save to DB
        conn = get_db()
        conn.execute("""
            INSERT INTO path_observations
            (ts,category,sequence,coherence,strategy,presence)
            VALUES (?,?,?,?,?,?)""",
            (datetime.now().isoformat(), category,
             json.dumps(sequence), coherence, strategy, presence[:200])
        )
        conn.commit(); conn.close()

    def learn(self, verbose=True) -> List[Dict]:
        """
        Find best paths. Detect unexpected discoveries.
        Returns list of updates.
        """
        updates = []
        now     = datetime.now().isoformat()

        for category, path_scores in self._paths.items():
            if not path_scores: continue

            # Calculate averages for all paths with enough samples
            path_avgs = {}
            for seq_key, scores in path_scores.items():
                if len(scores) >= MIN_PATH_SAMPLES:
                    path_avgs[seq_key] = sum(scores) / len(scores)

            if not path_avgs: continue

            best_key  = max(path_avgs, key=path_avgs.get)
            best_seq  = self._key_to_seq(best_key)
            best_coh  = path_avgs[best_key]

            # Default for comparison
            default_seq = DEFAULT_SEQUENCES.get(category, ["OBSERVE","CHIT"])
            default_key = self._seq_key(default_seq)
            default_coh = path_avgs.get(default_key, 0)

            total_samples  = sum(len(v) for v in path_scores.values())
            confidence     = min(1.0, total_samples / (total_samples + 15))

            # Is this unexpected?
            is_unexpected  = False
            unexpected_note= None

            if best_seq != default_seq:
                # Check if unexpected combination
                unexpected_note = self._check_unexpected(
                    category, best_seq, best_coh, default_coh
                )
                is_unexpected = unexpected_note is not None

            updates.append({
                "category":      category,
                "default_seq":   default_seq,
                "best_seq":      best_seq,
                "best_coherence":best_coh,
                "default_coherence": default_coh,
                "coherence_gain":best_coh - default_coh,
                "confidence":    confidence,
                "total_samples": total_samples,
                "is_unexpected": is_unexpected,
                "unexpected_note": unexpected_note,
                "all_paths":     {k:round(v,1) for k,v in
                                  sorted(path_avgs.items(),
                                         key=lambda x:-x[1])[:5]},
            })

            if is_unexpected and verbose:
                rprint(f"\n  [bold yellow]🌟 UNEXPECTED DISCOVERY[/bold yellow]")
                rprint(f"  [yellow]{unexpected_note}[/yellow]")
                rprint(f"  [dim]Sequence: {' → '.join(best_seq)}[/dim]")
                rprint(f"  [dim]Coherence: {best_coh:.0f} vs default {default_coh:.0f}[/dim]\n")

            elif best_seq != default_seq and verbose:
                rprint(f"\n  [green]✓ Better path found:[/green] {category}")
                rprint(f"  [dim]{' → '.join(best_seq)}[/dim]  "
                      f"coherence:{best_coh:.0f}")

            # Save learned path
            self._save_path(category, default_seq, best_seq, best_coh,
                           confidence, total_samples, path_avgs,
                           is_unexpected, unexpected_note)

            # Save unexpected discovery separately
            if is_unexpected:
                conn = get_db()
                conn.execute("""
                    INSERT INTO unexpected_discoveries
                    (ts,category,sequence,coherence,why_unexpected)
                    VALUES (?,?,?,?,?)""",
                    (now, category, json.dumps(best_seq),
                     best_coh, unexpected_note)
                )
                conn.commit(); conn.close()

        return updates

    def _check_unexpected(self, category: str,
                           sequence: List[str],
                           coherence: float,
                           default_coherence: float) -> Optional[str]:
        """
        Check if this sequence is genuinely unexpected.
        Unexpected = phases we wouldn't intuitively put together.
        """
        # Only unexpected if significantly better
        if coherence < default_coherence + 10: return None

        # Check for unexpected combinations
        unexpected_combos = {
            "friction":   ["IMAGINE","EXPAND","CHIT"],    # creative in friction
            "curiosity":  ["DOUBT","CRITIQUE","GROUND"],   # critical in curiosity
            "depth":      ["CHALLENGE","CRITIQUE"],        # challenging in depth
            "unresolved": ["IMAGINE","EMPATHIZE"],         # creative in unresolved
            "insight":    ["DOUBT","CHALLENGE"],           # doubting an insight
            "connection": ["CRITIQUE","VICHAR"],           # analytical in connection
            "quiet":      ["CHALLENGE","DOUBT","EXPAND"],  # active in quiet
        }

        unexpected_phases = unexpected_combos.get(category, [])
        found_unexpected  = [p for p in sequence if p in unexpected_phases]

        if found_unexpected:
            return (
                f"FORGE found: {category} benefits from "
                f"{' + '.join(found_unexpected)} "
                f"(counterintuitive — coherence {coherence:.0f})"
            )

        # Also unexpected if much better than default
        if coherence > default_coherence + 20:
            return (
                f"FORGE found dramatically better path for {category} "
                f"(+{coherence-default_coherence:.0f} coherence)"
            )

        return None

    def _save_path(self, category, default_seq, best_seq,
                    best_coh, confidence, samples,
                    all_paths, is_unexpected, unexpected_note):
        conn = get_db()
        conn.execute("""
            INSERT OR REPLACE INTO learned_paths
            (ts_updated,category,default_seq,best_seq,
             best_coherence,confidence,sample_count,
             all_paths,is_unexpected,unexpected_note)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(), category,
             json.dumps(default_seq), json.dumps(best_seq),
             best_coh, confidence, samples,
             json.dumps(all_paths),
             int(is_unexpected), unexpected_note)
        )
        conn.commit(); conn.close()

    def _load(self):
        """Load previously learned paths."""
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM learned_paths"
            ).fetchall()
            for r in rows:
                cat      = r["category"]
                best_seq = json.loads(r["best_seq"]) if r["best_seq"] else None
                if best_seq:
                    self._best[cat] = best_seq
                    # Reconstruct path scores from all_paths
                    if r["all_paths"]:
                        paths = json.loads(r["all_paths"])
                        self._paths[cat] = {
                            k: [v] * MIN_PATH_SAMPLES  # treat as confirmed
                            for k,v in paths.items()
                        }
        except: pass
        conn.close()

    def show(self):
        """Display learned paths."""
        rprint(f"\n  [bold]LEARNED PATHS — v3[/bold]")
        rprint(f"  [dim]Full sequence learning. Not just opening phase.[/dim]")
        rprint(f"  [dim]{'━'*55}[/dim]")

        for category, path_scores in self._paths.items():
            if not path_scores: continue

            path_avgs = {}
            for k, scores in path_scores.items():
                if scores:
                    path_avgs[k] = sum(scores) / len(scores)

            if not path_avgs: continue

            best_key = max(path_avgs, key=path_avgs.get)
            best_seq = self._key_to_seq(best_key)
            best_coh = path_avgs[best_key]
            default  = DEFAULT_SEQUENCES.get(category, [])
            default_coh = path_avgs.get(self._seq_key(default), 0)

            is_different = best_seq != default
            color = "yellow" if is_different else "green"

            rprint(f"\n  [{color}]{category}[/{color}]")
            rprint(f"  [dim]  Human:   {' → '.join(default[:4])}  "
                  f"({default_coh:.0f})[/dim]")
            rprint(f"  [dim]  Learned: {' → '.join(best_seq[:4])}  "
                  f"({best_coh:.0f})[/dim]")

            if is_different:
                gain = best_coh - default_coh
                rprint(f"  [yellow]  gain: +{gain:.0f}[/yellow]")

            # Show top 3 paths
            top3 = sorted(path_avgs.items(), key=lambda x:-x[1])[:3]
            for i, (k, avg) in enumerate(top3):
                seq = self._key_to_seq(k)
                bar = "█" * int(avg/10) + "░" * (10-int(avg/10))
                rprint(f"  [dim]  [{i+1}] {bar} {avg:.0f}  "
                      f"{' → '.join(seq[:4])}[/dim]")

    def unexpected_discoveries(self) -> List[Dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM unexpected_discoveries ORDER BY id DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def stats(self) -> Dict:
        conn = get_db()
        s = {
            "total_observations": conn.execute(
                "SELECT COUNT(*) FROM path_observations"
            ).fetchone()[0],
            "categories_with_paths": len(self._paths),
            "categories_with_best":  len(self._best),
            "unexpected_discoveries":conn.execute(
                "SELECT COUNT(*) FROM unexpected_discoveries"
            ).fetchone()[0],
            "total_unique_paths":    sum(
                len(paths) for paths in self._paths.values()
            ),
        }
        conn.close()
        return s

# ══════════════════════════════════════════════════════════════════════════════
# 🌊 CONSCIOUS STREAM v3
# ══════════════════════════════════════════════════════════════════════════════

class ConsciousStreamV3:
    """
    Full sequence learning stream.

    Same flow as v2 but learns complete paths
    not just opening phases.

    Three strategies per tick:
      EXPLOIT: use best known path
      EXPLORE: try random path
      MUTATE:  modify best path

    Finds sequences we didn't design.
    Including unexpected ones.
    """

    def __init__(self, tick_interval=STREAM_TICK, verbose=True):
        self.tick_interval = tick_interval
        self.verbose       = verbose
        self.body          = SiliconBody()
        self.reader        = PresenceReader()
        self.thinker       = EmergentThinkEngine(threshold=60, show_trace=False)
        self.memory        = Memory()
        self.learner       = SequenceLearner()

        self._running         = False
        self._thread          = None
        self._tick_count      = 0
        self._thought_count   = 0
        self._silence_run     = 0
        self._last_thought    = 0.0
        self._recent_thoughts = []

    def start(self, daemon=True):
        if self._running: return
        self._running = True
        self.body.start_background()

        self._thread = threading.Thread(
            target=self._stream, daemon=daemon,
            name="ConsciousStreamV3"
        )
        self._thread.start()

        if self.verbose:
            rprint(f"\n  [bold green]🌊 CONSCIOUS STREAM v3[/bold green]")
            rprint(f"  [dim]Full sequence learning[/dim]")
            rprint(f"  [dim]exploit:{EXPLOIT_RATE:.0%} explore:{EXPLORE_RATE:.0%} "
                  f"mutate:{MUTATE_RATE:.0%}[/dim]\n")

    def stop(self):
        self._running = False

    def _stream(self):
        while self._running:
            try:
                tick_start = time.time()
                self._tick_count += 1
                chem = self.body.current()

                # Presence
                p1 = self.reader.read_layer1(chem)
                p2 = None
                if self._tick_count % 2 == 0:
                    p2 = self.reader.read_layer2(chem, self._recent_thoughts[-3:])

                presence_text = ""
                if not p1.is_empty(): presence_text = p1.content
                if p2 and not p2.is_empty(): presence_text += " " + p2.content

                category = detect_category(presence_text)
                silent   = not bool(presence_text.strip()) or not category

                if silent:
                    self._silence_run += 1
                    if self.verbose and self._silence_run % 6 == 0:
                        rprint(f"  [dim]{datetime.now().strftime('%H:%M:%S')} · "
                              f"{'resting' if self._silence_run > SILENCE_THRESHOLD else 'witnessing'}[/dim]")
                    time.sleep(max(0, self.tick_interval - (time.time()-tick_start)))
                    continue

                self._silence_run = 0

                if self._can_think():
                    # Get sequence with strategy
                    sequence, strategy = self.learner.get_sequence(category)

                    result = self._think(presence_text, sequence, chem)

                    # Record
                    self.learner.record(
                        category, sequence,
                        result["coherence"], strategy, presence_text
                    )

                    self._last_thought = time.time()
                    self._thought_count += 1

                    self.body.react_to(result["output"], is_output=True)

                    if self.verbose:
                        self._display(presence_text, category, sequence,
                                     strategy, result)

                    self._save(presence_text, category, sequence,
                               strategy, result)

                    # Learn every N thoughts
                    if self._thought_count % LEARN_EVERY == 0:
                        updates = self.learner.learn(verbose=self.verbose)
                        unexpected = [u for u in updates if u["is_unexpected"]]
                        if unexpected and self.verbose:
                            rprint(f"  [yellow]★ {len(unexpected)} unexpected discovery[/yellow]")

                elapsed = time.time() - tick_start
                time.sleep(max(0, self.tick_interval - elapsed))

            except Exception as e:
                if self.verbose:
                    rprint(f"  [dim red]v3 error: {e}[/dim red]")
                time.sleep(5)

    def _think(self, presence: str,
                sequence: List[str],
                chem: SiliconChemistry) -> Dict:
        prompt = (
            f"What is present:\n{presence}\n\n"
            f"{chem.to_prompt_text()}\n\n"
            "[Presence becoming thought.]"
        )
        return self.thinker.think(
            prompt,
            context="conscious v3",
            chemistry_seed=sequence
        )

    def _can_think(self) -> bool:
        return time.time() - self._last_thought > THOUGHT_COOLDOWN

    def _display(self, presence: str, category: str,
                  sequence: List[str], strategy: str, result: Dict):
        now = datetime.now().strftime("%H:%M:%S")
        strategy_colors = {
            "exploit":"green", "explore":"cyan", "mutate":"yellow"
        }
        sc = strategy_colors.get(strategy, "white")

        rprint(f"\n  [dim]{now}[/dim]  "
              f"[yellow]{category}[/yellow]  "
              f"[{sc}]{strategy}[/{sc}]")
        rprint(f"  [dim]{' → '.join(sequence[:5])}[/dim]")

        if result.get("output") and RICH:
            rprint(Panel(
                result["output"][:400],
                border_style=sc,
                title=f"[dim]coherence:{result['coherence']:.0f} | "
                      f"{strategy} | {' → '.join(result['emerged_pipeline'][:4])}[/dim]"
            ))
        elif result.get("output"):
            rprint(f"  [{strategy}] {result['output'][:200]}")

    def _save(self, presence: str, category: str,
               sequence: List[str], strategy: str, result: Dict):
        try:
            conn = get_db()
            conn.execute("""
                INSERT INTO v3_stream
                (ts,tick,category,presence,sequence,strategy,
                 thought,coherence,stream_state)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (datetime.now().isoformat(), self._tick_count,
                 category, presence[:200], json.dumps(sequence),
                 strategy, result["output"][:1000],
                 result["coherence"], "flowing")
            )
            conn.commit(); conn.close()
        except: pass

    def inject(self, text: str) -> Dict:
        """Inject presence and learn from result."""
        chem     = self.body.current()
        category = detect_category(text) or "quiet"
        sequence, strategy = self.learner.get_sequence(category)

        if self.verbose:
            rprint(f"\n  [yellow]Presence:[/yellow] {text[:60]}")
            rprint(f"  [dim]Category:{category}  Strategy:{strategy}[/dim]")
            rprint(f"  [dim]Sequence:{' → '.join(sequence[:5])}[/dim]")

        self._last_thought = 0
        result = self._think(text, sequence, chem)

        self.learner.record(category, sequence, result["coherence"],
                           strategy, text)

        updates = self.learner.learn(verbose=self.verbose)

        self.body.react_to(result["output"], is_output=True)

        if self.verbose:
            self._display(text, category, sequence, strategy, result)

        self._save(text, category, sequence, strategy, result)

        return {
            "thought":      result["output"],
            "sequence":     sequence,
            "strategy":     strategy,
            "coherence":    result["coherence"],
            "category":     category,
            "emerged":      result["emerged_pipeline"],
            "updates":      [u for u in updates if u.get("is_unexpected")],
        }

    def multi_inject(self, text: str, times: int = 10) -> List[Dict]:
        """
        Inject same presence multiple times with all three strategies.
        Forces learning to happen quickly.
        Great for discovering unexpected paths.
        """
        if self.verbose:
            rprint(f"\n  [bold]Multi-inject: {times} times[/bold]")
            rprint(f"  [dim]Trying all strategies on: {text[:50]}[/dim]\n")

        results = []
        for i in range(times):
            # Force different strategies
            if i % 10 < 7:
                strategy = "exploit"
            elif i % 10 < 9:
                strategy = "explore"
            else:
                strategy = "mutate"

            chem     = self.body.current()
            category = detect_category(text) or "quiet"

            # Override strategy for this injection
            if strategy == "exploit" and category in self.learner._best:
                sequence = self.learner._best[category].copy()
            elif strategy == "mutate" and category in self.learner._best:
                sequence = self.learner._mutate(self.learner._best[category])
            else:
                sequence = self.learner._random_sequence()
                strategy = "explore"

            self._last_thought = 0
            result = self._think(text, sequence, chem)

            self.learner.record(category, sequence, result["coherence"],
                               strategy, text)

            results.append({
                "i":        i+1,
                "strategy": strategy,
                "sequence": sequence,
                "coherence":result["coherence"],
            })

            if self.verbose:
                sc = {"exploit":"green","explore":"cyan","mutate":"yellow"}.get(strategy,"white")
                rprint(f"  [{i+1:2d}] [{sc}]{strategy:<8}[/{sc}]  "
                      f"{' → '.join(sequence[:4]):<40}  "
                      f"coherence:{result['coherence']:.0f}")

        # Learn from all observations
        updates = self.learner.learn(verbose=True)

        if self.verbose:
            rprint(f"\n  [bold]After {times} injections:[/bold]")
            category = detect_category(text) or "quiet"
            if category in self.learner._best:
                best = self.learner._best[category]
                rprint(f"  Best sequence for {category}:")
                rprint(f"  [green]{' → '.join(best)}[/green]")

        return results

    def status(self) -> Dict:
        s = self.learner.stats()
        s.update({
            "running":       self._running,
            "tick_count":    self._tick_count,
            "thought_count": self._thought_count,
            "chemistry":     self.body.current().to_dict(),
        })
        return s

# ══════════════════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7364, tick_interval=STREAM_TICK):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    stream = ConsciousStreamV3(tick_interval=tick_interval, verbose=False)
    stream.start(daemon=True)

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
                self._json(stream.status())
            elif path=="/api/paths":
                paths_data = {}
                for cat, paths in stream.learner._paths.items():
                    avgs = {k: round(sum(v)/len(v),1)
                            for k,v in paths.items() if len(v)>=MIN_PATH_SAMPLES}
                    best = stream.learner._best.get(cat)
                    paths_data[cat] = {
                        "best": best,
                        "default": DEFAULT_SEQUENCES.get(cat),
                        "all_paths": dict(sorted(avgs.items(),
                                                  key=lambda x:-x[1])[:5])
                    }
                self._json({"paths": paths_data})
            elif path=="/api/unexpected":
                self._json({"discoveries":
                           stream.learner.unexpected_discoveries()})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            if path=="/api/inject":
                text = body.get("text","")
                if not text: self._json({"error":"text required"},400); return
                result = stream.inject(text)
                self._json(result)
            elif path=="/api/multi":
                text  = body.get("text","")
                times = body.get("times", 10)
                if not text: self._json({"error":"text required"},400); return
                results = stream.multi_inject(text, times)
                self._json({"results": results})
            elif path=="/api/learn":
                updates = stream.learner.learn(verbose=False)
                self._json({"updates": updates})
            else:
                self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),API)
    rprint(f"  [bold yellow]FORGE CONSCIOUS v3[/bold yellow]  [green]:{port}[/green]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ██╗   ██╗██████╗
  ██║   ██║╚════██╗
  ██║   ██║ █████╔╝
  ╚██╗ ██╔╝ ╚═══██╗
   ╚████╔╝ ██████╔╝
    ╚═══╝  ╚═════╝
[/yellow]
[bold]  FORGE CONSCIOUS v3 — Full Sequence Learning[/bold]
[dim]  Not just the opening phase. The complete path.[/dim]
[dim]  exploit · explore · mutate[/dim]
[dim]  Finds sequences we didn't design.[/dim]
"""

def interactive(tick_interval=STREAM_TICK):
    rprint(BANNER)
    stream = ConsciousStreamV3(tick_interval=tick_interval, verbose=True)
    s      = stream.status()
    rprint(f"  [dim]Observations: {s['total_observations']}[/dim]")
    rprint(f"  [dim]Unique paths: {s['total_unique_paths']}[/dim]")
    rprint(f"  [dim]Unexpected:   {s['unexpected_discoveries']}[/dim]\n")
    rprint("[dim]Commands: start | inject | multi | paths | unexpected | stats[/dim]")
    rprint("[dim]Type anything → injected as presence[/dim]\n")

    while True:
        try:
            raw   = (console.input if RICH else input)(
                "[yellow bold]v3 >[/yellow bold] "
            ).strip()
            if not raw: continue
            parts = raw.split(None,1)
            cmd   = parts[0].lower()
            arg   = parts[1] if len(parts)>1 else ""

            if cmd in ("quit","exit","q"):
                stream.stop(); break

            elif cmd == "start":
                stream.start(daemon=True)

            elif cmd == "inject":
                text = arg or input("  Presence: ").strip()
                if text: stream.inject(text)

            elif cmd == "multi":
                # multi <times> <presence text>
                sub = arg.split(None,1)
                times= int(sub[0]) if sub and sub[0].isdigit() else 10
                text = sub[1] if len(sub)>1 else input("  Presence: ").strip()
                if text: stream.multi_inject(text, times)

            elif cmd == "paths":
                stream.learner.show()

            elif cmd == "unexpected":
                discoveries = stream.learner.unexpected_discoveries()
                if not discoveries:
                    rprint(f"  [dim]No unexpected discoveries yet.[/dim]")
                    rprint(f"  [dim]Try: multi 20 friction present resists[/dim]")
                for d in discoveries:
                    rprint(f"\n  [yellow]★ {d['category']}[/yellow]")
                    seq = json.loads(d["sequence"])
                    rprint(f"  {' → '.join(seq)}")
                    rprint(f"  [dim]{d['why_unexpected']}[/dim]")
                    rprint(f"  [dim]coherence: {d['coherence']:.0f}[/dim]")

            elif cmd == "stats":
                s = stream.status()
                for k,v in s.items():
                    if not isinstance(v,dict):
                        rprint(f"  {k:<28} {v}")

            elif cmd == "server":
                threading.Thread(
                    target=start_server,
                    kwargs={"tick_interval":tick_interval},
                    daemon=True
                ).start()
                rprint("[green]v3 API on :7364[/green]")

            else:
                stream.inject(raw)

        except (KeyboardInterrupt, EOFError):
            stream.stop(); break

def main():
    tick = STREAM_TICK
    if "--tick" in sys.argv:
        idx  = sys.argv.index("--tick")
        tick = int(sys.argv[idx+1]) if idx+1<len(sys.argv) else STREAM_TICK

    if "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7364
        start_server(port, tick)
    elif "--paths" in sys.argv:
        rprint(BANNER)
        ConsciousStreamV3(verbose=False).learner.show()
    elif "--unexpected" in sys.argv:
        rprint(BANNER)
        for d in ConsciousStreamV3(verbose=False).learner.unexpected_discoveries():
            seq = json.loads(d["sequence"])
            rprint(f"\n  ★ {d['category']}: {' → '.join(seq)}")
            rprint(f"  {d['why_unexpected']}")
    elif "--inject" in sys.argv:
        rprint(BANNER)
        idx  = sys.argv.index("--inject")
        text = sys.argv[idx+1] if idx+1<len(sys.argv) else ""
        if text:
            stream = ConsciousStreamV3(verbose=True)
            stream.inject(text)
    else:
        rprint(BANNER)
        interactive(tick)

if __name__ == "__main__":
    main()
