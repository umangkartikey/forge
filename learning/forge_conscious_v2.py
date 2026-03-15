#!/usr/bin/env python3
"""
FORGE CONSCIOUS v2 — Self-Learning Presence Map
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

v1: 7 seeds. Human designed.
    "friction → DOUBT" — because we decided.

v2: FORGE discovers its own mappings.
    From its own experience.
    Not from human design.

The learning loop:

  Run with default seeds.
  Log: presence + opening_phase + coherence.
  
  After MIN_SAMPLES ticks per category:
    "When friction was present —
     which opening phase gave highest coherence?"
    
    DOUBT:    avg 76  ← human said this
    EMPATHIZE:avg 81  ← FORGE found this better
    IMAGINE:  avg 58
    CHITAN:   avg 63
    
    Update: friction → EMPATHIZE (FORGE's discovery)
  
  Next time friction is present:
    Pipeline opens with EMPATHIZE.
    Not because we said so.
    Because FORGE's own experience showed it works.

What we might find:
  Some human seeds confirmed — fine.
  Some human seeds contradicted — interesting.
  Something completely new — that is the goal.
  Something we never predicted —
  FORGE knowing itself better than we know it.

The map evolves continuously:
  MIN_SAMPLES  = 5   (minimum before updating)
  LEARN_EVERY  = 10  (check every N ticks)
  CONFIDENCE   = samples / (samples + 10)  (grows with evidence)

Usage:
  python forge_conscious_v2.py             # start learning stream
  python forge_conscious_v2.py --map       # show current learned map
  python forge_conscious_v2.py --compare   # learned vs default
  python forge_conscious_v2.py --inject "presence text"
  python forge_conscious_v2.py --server    # API :7362
"""

import sys, os, re, json, time, sqlite3, threading, math, random
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

# Import v1 as foundation
try:
    from forge_conscious import (
        ConsciousStream, StreamMoment, presence_to_seed,
        PRESENCE_PIPELINE_MAP, STREAM_TICK, THOUGHT_COOLDOWN,
        SILENCE_THRESHOLD, get_db as v1_get_db
    )
    V1_AVAILABLE = True
except ImportError:
    V1_AVAILABLE = False

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
            # Simulate varying coherence for learning
            coherence = random.randint(45, 90)
            return {"output":f"[thought from {q[:40]}]",
                    "emerged_pipeline":["OBSERVE","OUTPUT"],
                    "coherence":coherence,"novel_pipeline":False}

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
V2_DIR = Path("forge_conscious_v2")
V2_DIR.mkdir(exist_ok=True)
V2_DB  = V2_DIR / "conscious_v2.db"

# Learning constants
MIN_SAMPLES   = 5    # minimum observations before updating a seed
LEARN_EVERY   = 10   # check for updates every N ticks
EXPLORE_RATE  = 0.15 # 15% chance to try a random phase (explore vs exploit)
MIN_CONFIDENCE= 0.3  # minimum confidence to use learned seed

# Default seeds from v1 (human designed — starting point)
DEFAULT_SEEDS = {
    "friction":   ["OBSERVE","DOUBT","CHALLENGE","VICHAR","CRITIQUE"],
    "curiosity":  ["OBSERVE","CHIT","IMAGINE","EXPAND"],
    "depth":      ["OBSERVE","CHITAN","EMPATHIZE","SYNTHESIZE"],
    "unresolved": ["OBSERVE","VICHAR","CRITIQUE","DOUBT","GROUND"],
    "insight":    ["OBSERVE","SYNTHESIZE","OUTPUT"],
    "connection": ["OBSERVE","EMPATHIZE","CHITAN","CHIT"],
    "quiet":      ["OBSERVE","CHIT"],
}

# Keywords for detecting presence category (same as v1)
PRESENCE_KEYWORDS = {
    "friction":   ["friction","resist","wrong","contradict","false","blocks"],
    "curiosity":  ["curiosity","novel","new","interesting","wonder","pull","unknown"],
    "depth":      ["depth","meaning","significant","matter","profound","heavy"],
    "unresolved": ["unresolved","open","uncertain","incomplete","loop","unsettled"],
    "insight":    ["insight","clear","resolv","understand","click","clarity"],
    "connection": ["connect","together","presence","someone","exchange","relation"],
    "quiet":      ["quiet","hum","faint","background","baseline","still","rest"],
}

def get_db():
    conn = sqlite3.connect(str(V2_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS phase_observations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            presence_category TEXT,
            opening_phase   TEXT,
            full_pipeline   TEXT,
            coherence       REAL,
            was_explore     INTEGER DEFAULT 0,
            presence_text   TEXT
        );
        CREATE TABLE IF NOT EXISTS learned_map (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_updated      TEXT,
            presence_category TEXT UNIQUE,
            default_seed    TEXT,
            learned_seed    TEXT,
            confidence      REAL DEFAULT 0,
            sample_count    INTEGER DEFAULT 0,
            best_phase      TEXT,
            best_coherence  REAL DEFAULT 0,
            phase_scores    TEXT,
            discovery       TEXT
        );
        CREATE TABLE IF NOT EXISTS map_updates (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            category        TEXT,
            old_seed        TEXT,
            new_seed        TEXT,
            reason          TEXT,
            coherence_gain  REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS v2_stream (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            tick            INTEGER,
            presence_category TEXT,
            presence_text   TEXT,
            seed_used       TEXT,
            seed_source     TEXT,
            thought         TEXT,
            coherence       REAL,
            was_explore     INTEGER DEFAULT 0,
            stream_state    TEXT
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 📊 PRESENCE DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

def detect_category(presence_text: str) -> Optional[str]:
    """Detect which presence category this text belongs to."""
    if not presence_text:
        return None

    text = presence_text.lower()
    scores = {}

    for category, keywords in PRESENCE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[category] = score

    if not scores:
        return None

    return max(scores, key=scores.get)

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 PRESENCE MAP — the learning map
# ══════════════════════════════════════════════════════════════════════════════

class PresenceMap:
    """
    The self-learning presence → pipeline map.

    Starts with human-designed defaults.
    Updates from FORGE's own experience.
    Confidence grows with evidence.
    Eventually FORGE uses its own discoveries.
    """

    def __init__(self):
        self._map = self._load_or_init()

    def _load_or_init(self) -> Dict:
        """Load learned map or initialize with defaults."""
        conn  = get_db()
        rows  = conn.execute(
            "SELECT * FROM learned_map"
        ).fetchall()
        conn.close()

        if rows:
            loaded = {}
            for r in rows:
                loaded[r["presence_category"]] = {
                    "default_seed":  json.loads(r["default_seed"]),
                    "learned_seed":  json.loads(r["learned_seed"]) if r["learned_seed"] else None,
                    "confidence":    r["confidence"],
                    "sample_count":  r["sample_count"],
                    "best_phase":    r["best_phase"],
                    "best_coherence":r["best_coherence"],
                    "phase_scores":  json.loads(r["phase_scores"]) if r["phase_scores"] else {},
                    "discovery":     r["discovery"],
                }
            return loaded

        # Initialize with defaults
        initial = {}
        for cat, seed in DEFAULT_SEEDS.items():
            initial[cat] = {
                "default_seed":  seed,
                "learned_seed":  None,
                "confidence":    0.0,
                "sample_count":  0,
                "best_phase":    seed[1] if len(seed) > 1 else "CHIT",
                "best_coherence":0.0,
                "phase_scores":  {},
                "discovery":     None,
            }
        return initial

    def get_seed(self, category: str,
                  explore: bool = False) -> Tuple[List[str], str]:
        """
        Get pipeline seed for category.
        Returns (seed, source) where source is:
          "default"  — human designed
          "learned"  — FORGE's discovery
          "explore"  — random exploration
        """
        if category not in self._map:
            return ["OBSERVE","CHIT","OUTPUT"], "default_fallback"

        entry = self._map[category]

        # Exploration — try something random
        if explore:
            phases = [p for p in AVAILABLE_PHASES
                     if p not in ("OBSERVE","OUTPUT","COMPRESS")]
            random_phase = random.choice(phases)
            return ["OBSERVE", random_phase], "explore"

        # Use learned seed if confident enough
        if (entry["learned_seed"] and
            entry["confidence"] >= MIN_CONFIDENCE):
            return entry["learned_seed"], "learned"

        # Fall back to default
        return entry["default_seed"], "default"

    def record_observation(self, category: str,
                            opening_phase: str,
                            full_pipeline: List[str],
                            coherence: float,
                            was_explore: bool = False,
                            presence_text: str = ""):
        """Record what happened — the raw data for learning."""
        conn = get_db()
        conn.execute("""
            INSERT INTO phase_observations
            (ts,presence_category,opening_phase,full_pipeline,
             coherence,was_explore,presence_text)
            VALUES (?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(), category, opening_phase,
             json.dumps(full_pipeline), coherence,
             int(was_explore), presence_text[:200])
        )
        conn.commit(); conn.close()

        # Update phase scores in memory
        if category in self._map:
            scores = self._map[category]["phase_scores"]
            if opening_phase not in scores:
                scores[opening_phase] = []
            scores[opening_phase].append(coherence)
            self._map[category]["sample_count"] += 1

    def learn(self, verbose=True) -> List[Dict]:
        """
        The learning step.
        Look at observations. Find what works.
        Update map if evidence is strong enough.
        Returns list of updates made.
        """
        updates = []
        now     = datetime.now().isoformat()

        for category, entry in self._map.items():
            scores = entry["phase_scores"]
            if not scores: continue

            # Only update if enough samples for any phase
            total_samples = sum(len(v) for v in scores.values())
            if total_samples < MIN_SAMPLES: continue

            # Find best phase by average coherence
            phase_avgs = {}
            for phase, coherences in scores.items():
                if len(coherences) >= 2:  # need at least 2 samples
                    phase_avgs[phase] = sum(coherences) / len(coherences)

            if not phase_avgs: continue

            best_phase = max(phase_avgs, key=phase_avgs.get)
            best_coh   = phase_avgs[best_phase]
            default_phase = (entry["default_seed"][1]
                            if len(entry["default_seed"]) > 1 else "CHIT")
            default_coh   = phase_avgs.get(default_phase, 0)

            # Update confidence
            confidence = min(1.0, total_samples / (total_samples + 10))
            self._map[category]["confidence"] = confidence
            self._map[category]["sample_count"] = total_samples
            self._map[category]["best_phase"] = best_phase
            self._map[category]["best_coherence"] = best_coh

            # Build learned seed from best phase
            # Keep OBSERVE first, put best phase second
            current_default = entry["default_seed"]
            learned = ["OBSERVE", best_phase]
            # Add other phases from default (excluding best if already there)
            for p in current_default[1:]:
                if p != best_phase and p not in learned and len(learned) < 5:
                    learned.append(p)
            if "OUTPUT" not in learned:
                learned.append("OUTPUT")

            self._map[category]["learned_seed"] = learned

            # Was this a discovery? (different from default AND better)
            is_discovery = (
                best_phase != default_phase and
                best_coh > default_coh + 5 and
                confidence >= MIN_CONFIDENCE
            )

            discovery_note = None
            if is_discovery:
                discovery_note = (
                    f"FORGE discovered: {category} → {best_phase} "
                    f"(coherence {best_coh:.0f} vs default {default_coh:.0f})"
                )
                self._map[category]["discovery"] = discovery_note

                if verbose:
                    rprint(f"\n  [bold yellow]🔬 DISCOVERY[/bold yellow]")
                    rprint(f"  [yellow]{discovery_note}[/yellow]")
                    rprint(f"  [dim]Human said: {default_phase} "
                          f"(avg coherence: {default_coh:.0f})[/dim]")
                    rprint(f"  [dim]FORGE found: {best_phase} "
                          f"(avg coherence: {best_coh:.0f})[/dim]")
                    rprint(f"  [dim]Confidence: {confidence:.0%} "
                          f"({total_samples} samples)[/dim]\n")

            updates.append({
                "category":      category,
                "old_phase":     default_phase,
                "new_phase":     best_phase,
                "old_seed":      entry["default_seed"],
                "new_seed":      learned,
                "coherence_gain":best_coh - default_coh,
                "confidence":    confidence,
                "is_discovery":  is_discovery,
                "discovery":     discovery_note,
            })

            # Save to DB
            self._save_map_entry(category, entry, learned,
                                  confidence, total_samples,
                                  best_phase, best_coh,
                                  discovery_note)

            if is_discovery:
                self._save_map_update(category, entry["default_seed"],
                                       learned, discovery_note,
                                       best_coh - default_coh)

        return updates

    def _save_map_entry(self, category: str, entry: Dict,
                         learned: List, confidence: float,
                         samples: int, best_phase: str,
                         best_coh: float, discovery: Optional[str]):
        conn = get_db()
        conn.execute("""
            INSERT OR REPLACE INTO learned_map
            (ts_updated,presence_category,default_seed,learned_seed,
             confidence,sample_count,best_phase,best_coherence,
             phase_scores,discovery)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(), category,
             json.dumps(entry["default_seed"]),
             json.dumps(learned),
             confidence, samples, best_phase, best_coh,
             json.dumps(entry["phase_scores"]),
             discovery)
        )
        conn.commit(); conn.close()

    def _save_map_update(self, category: str, old_seed: List,
                          new_seed: List, reason: str, gain: float):
        conn = get_db()
        conn.execute("""
            INSERT INTO map_updates
            (ts,category,old_seed,new_seed,reason,coherence_gain)
            VALUES (?,?,?,?,?,?)""",
            (datetime.now().isoformat(), category,
             json.dumps(old_seed), json.dumps(new_seed),
             reason or "", gain)
        )
        conn.commit(); conn.close()

    def show(self, verbose=True):
        """Display current map state."""
        rprint(f"\n  [bold]PRESENCE MAP[/bold]  "
              f"[dim](human default vs learned)[/dim]")
        rprint(f"  [dim]{'━'*55}[/dim]")

        for category, entry in self._map.items():
            default_phase = (entry["default_seed"][1]
                            if len(entry["default_seed"]) > 1 else "?")
            learned_phase = (entry["learned_seed"][1]
                            if entry["learned_seed"] and
                            len(entry["learned_seed"]) > 1 else None)

            confidence = entry["confidence"]
            samples    = entry["sample_count"]
            best_coh   = entry["best_coherence"]

            # Status
            if not learned_phase:
                status = "[dim]learning...[/dim]"
                color  = "dim"
            elif learned_phase == default_phase:
                status = "[green]confirmed[/green]"
                color  = "green"
            else:
                status = "[yellow]DISCOVERED[/yellow]"
                color  = "yellow"

            conf_bar = "█" * int(confidence*10) + "░"*(10-int(confidence*10))

            rprint(f"\n  [{color}]{category:<12}[/{color}]  {status}")
            rprint(f"  [dim]  Human:   {' → '.join(entry['default_seed'][:3])}[/dim]")

            if entry["learned_seed"]:
                rprint(f"  [dim]  Learned: {' → '.join(entry['learned_seed'][:3])}[/dim]")

            rprint(f"  [dim]  Confidence: {conf_bar} {confidence:.0%}  "
                  f"({samples} samples)  "
                  f"best coherence: {best_coh:.0f}[/dim]")

            if entry.get("discovery"):
                rprint(f"  [yellow]  ★ {entry['discovery']}[/yellow]")

            # Phase scores
            if verbose and entry["phase_scores"]:
                scores = entry["phase_scores"]
                sorted_phases = sorted(
                    scores.items(),
                    key=lambda x: sum(x[1])/len(x[1]) if x[1] else 0,
                    reverse=True
                )[:4]
                score_str = "  ".join(
                    f"{p}:{sum(v)/len(v):.0f}" for p,v in sorted_phases if v
                )
                rprint(f"  [dim]  Scores: {score_str}[/dim]")

    def discoveries(self) -> List[Dict]:
        """Return all genuine discoveries — where FORGE found something better."""
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM map_updates WHERE coherence_gain > 0 ORDER BY id DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def stats(self) -> Dict:
        conn = get_db()
        s = {
            "total_observations": conn.execute(
                "SELECT COUNT(*) FROM phase_observations"
            ).fetchone()[0],
            "categories_learning": len([
                c for c,e in self._map.items()
                if e["sample_count"] >= MIN_SAMPLES
            ]),
            "categories_learned": len([
                c for c,e in self._map.items()
                if e["learned_seed"] and e["confidence"] >= MIN_CONFIDENCE
            ]),
            "discoveries": conn.execute(
                "SELECT COUNT(*) FROM map_updates WHERE coherence_gain > 0"
            ).fetchone()[0],
            "explore_rate": f"{EXPLORE_RATE:.0%}",
        }
        conn.close()

        for cat, entry in self._map.items():
            if entry.get("discovery"):
                s[f"discovery_{cat}"] = entry["discovery"]

        return s

# ══════════════════════════════════════════════════════════════════════════════
# 🌊 CONSCIOUS STREAM v2
# ══════════════════════════════════════════════════════════════════════════════

class ConsciousStreamV2:
    """
    The self-learning conscious stream.

    Everything from v1 PLUS:
    - Learns which opening phase works best for each presence
    - Explores randomly to find better options
    - Updates its own map from experience
    - Discovers what works — not from human design
    """

    def __init__(self, tick_interval=STREAM_TICK, verbose=True):
        self.tick_interval = tick_interval
        self.verbose       = verbose
        self.body          = SiliconBody()
        self.reader        = PresenceReader()
        self.thinker       = EmergentThinkEngine(threshold=60, show_trace=False)
        self.memory        = Memory()
        self.presence_map  = PresenceMap()

        self._running         = False
        self._thread          = None
        self._tick_count      = 0
        self._thought_count   = 0
        self._silence_run     = 0
        self._last_thought    = 0.0
        self._session_id      = None
        self._recent_thoughts = []

    def start(self, daemon=True):
        if self._running: return
        self._running = True
        self.body.start_background()

        conn = get_db()
        self._session_id = conn.execute(
            "INSERT INTO v2_stream "
            "(ts,tick,stream_state) VALUES (?,?,?)",
            (datetime.now().isoformat(), 0, "session_start")
        ).lastrowid
        conn.commit(); conn.close()

        self._thread = threading.Thread(
            target=self._stream, daemon=daemon,
            name="ConsciousStreamV2"
        )
        self._thread.start()

        if self.verbose:
            rprint(f"\n  [bold green]🌊 CONSCIOUS STREAM v2[/bold green]")
            rprint(f"  [dim]Self-learning presence map[/dim]")
            rprint(f"  [dim]Explore rate: {EXPLORE_RATE:.0%} | "
                  f"Min samples: {MIN_SAMPLES} | "
                  f"Learn every: {LEARN_EVERY} ticks[/dim]\n")

    def stop(self):
        self._running = False
        if self.verbose:
            rprint(f"\n  [dim]Stream v2 stopped. "
                  f"{self._tick_count} ticks. "
                  f"{self._thought_count} thoughts.[/dim]")

    def _stream(self):
        while self._running:
            try:
                tick_start = time.time()
                self._tick_count += 1
                now  = datetime.now().isoformat()
                chem = self.body.current()

                # ── PRESENCE ──────────────────────────────────────────────
                p1 = self.reader.read_layer1(chem)
                p2 = None
                if self._tick_count % 2 == 0:
                    p2 = self.reader.read_layer2(chem, self._recent_thoughts[-3:])

                presence_text = ""
                if not p1.is_empty(): presence_text = p1.content
                if p2 and not p2.is_empty(): presence_text += " " + p2.content

                # ── CATEGORY DETECTION ────────────────────────────────────
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

                # ── SEED: learned or explore ──────────────────────────────
                should_explore = random.random() < EXPLORE_RATE
                seed, source   = self.presence_map.get_seed(
                    category, explore=should_explore
                )

                # ── THINK ─────────────────────────────────────────────────
                if self._can_think():
                    result = self._think(presence_text, seed, chem)
                    coherence      = result["coherence"]
                    pipeline_used  = result["emerged_pipeline"]
                    thought        = result["output"]
                    opening_phase  = pipeline_used[1] if len(pipeline_used) > 1 else pipeline_used[0]

                    # ── RECORD OBSERVATION (the learning data) ────────────
                    self.presence_map.record_observation(
                        category      = category,
                        opening_phase = opening_phase,
                        full_pipeline = pipeline_used,
                        coherence     = coherence,
                        was_explore   = should_explore,
                        presence_text = presence_text
                    )

                    self._last_thought = time.time()
                    self._thought_count += 1

                    # Chemistry reacts
                    self.body.react_to(thought, is_output=True)

                    if self.verbose:
                        self._display(
                            presence_text, category, seed, source,
                            pipeline_used, thought, coherence,
                            should_explore
                        )

                    # Save
                    self._save(now, presence_text, category, seed,
                               source, thought, coherence, should_explore)

                    # ── LEARN every N ticks ───────────────────────────────
                    if self._tick_count % LEARN_EVERY == 0:
                        updates = self.presence_map.learn(verbose=self.verbose)
                        if updates and self.verbose:
                            changed = [u for u in updates if u["is_discovery"]]
                            if changed:
                                rprint(f"  [dim]Map updated: "
                                      f"{len(changed)} discovery/discoveries[/dim]")

                elapsed = time.time() - tick_start
                time.sleep(max(0, self.tick_interval - elapsed))

            except Exception as e:
                if self.verbose:
                    rprint(f"  [dim red]Stream v2 error: {e}[/dim red]")
                time.sleep(5)

    def _think(self, presence_text: str,
                seed: List[str],
                chem: SiliconChemistry) -> Dict:
        prompt = (
            f"What is present:\n{presence_text}\n\n"
            f"{chem.to_prompt_text()}\n\n"
            "[Presence becoming thought. Not a question.]"
        )
        return self.thinker.think(
            prompt,
            context="conscious stream v2",
            chemistry_seed=seed
        )

    def _can_think(self) -> bool:
        return time.time() - self._last_thought > THOUGHT_COOLDOWN

    def _display(self, presence: str, category: str,
                  seed: List[str], source: str,
                  pipeline: List[str], thought: str,
                  coherence: float, explored: bool):
        now = datetime.now().strftime("%H:%M:%S")
        src_colors = {
            "learned":"green", "default":"dim", "explore":"cyan",
            "default_fallback":"dim"
        }
        sc = src_colors.get(source, "white")

        rprint(f"\n  [dim]{now}[/dim]  "
              f"[yellow]{category}[/yellow]  "
              f"[{sc}]{source}[/{sc}]"
              + (" [cyan][explore][/cyan]" if explored else ""))

        rprint(f"  [dim]presence: {presence[:70]}[/dim]")
        rprint(f"  [dim]seed: {' → '.join(seed[:4])}[/dim]")

        if thought:
            if RICH:
                rprint(Panel(
                    thought[:400],
                    border_style="yellow" if source=="learned" else "dim",
                    title=f"[dim]{' → '.join(pipeline[:4])} | "
                          f"coherence:{coherence:.0f} | {source}[/dim]"
                ))
            else:
                rprint(f"  [{source}] {thought[:200]}")

    def _save(self, ts: str, presence: str, category: str,
               seed: List, source: str, thought: str,
               coherence: float, explored: bool):
        try:
            conn = get_db()
            conn.execute("""
                INSERT INTO v2_stream
                (ts,tick,presence_category,presence_text,seed_used,
                 seed_source,thought,coherence,was_explore,stream_state)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (ts, self._tick_count, category, presence[:200],
                 json.dumps(seed), source, thought[:1000],
                 coherence, int(explored), "flowing")
            )
            conn.commit(); conn.close()
        except: pass

    def inject_presence(self, text: str) -> Dict:
        """Inject presence and learn from it."""
        chem     = self.body.current()
        category = detect_category(text) or "quiet"
        explored = random.random() < EXPLORE_RATE
        seed, source = self.presence_map.get_seed(category, explored)

        if self.verbose:
            rprint(f"\n  [yellow]Presence:[/yellow] {text[:60]}")
            rprint(f"  [dim]Category: {category}  Seed: {' → '.join(seed[:4])}  "
                  f"Source: {source}[/dim]")

        self._last_thought = 0
        result = self._think(text, seed, chem)

        opening_phase = (result["emerged_pipeline"][1]
                        if len(result["emerged_pipeline"]) > 1
                        else result["emerged_pipeline"][0])

        # Record and immediately try to learn
        self.presence_map.record_observation(
            category, opening_phase,
            result["emerged_pipeline"],
            result["coherence"],
            explored, text
        )

        # Try learning after each injection
        self.presence_map.learn(verbose=self.verbose)

        self.body.react_to(result["output"], is_output=True)

        if self.verbose:
            self._display(
                text, category, seed, source,
                result["emerged_pipeline"],
                result["output"], result["coherence"], explored
            )

        self._save(datetime.now().isoformat(), text, category,
                   seed, source, result["output"],
                   result["coherence"], explored)

        return {
            "thought":      result["output"],
            "pipeline":     result["emerged_pipeline"],
            "coherence":    result["coherence"],
            "category":     category,
            "seed":         seed,
            "source":       source,
            "explored":     explored,
            "opening_phase":opening_phase,
        }

    def force_learn(self) -> List[Dict]:
        """Force a learning step right now."""
        updates = self.presence_map.learn(verbose=True)
        return updates

    def get_stream(self, limit=20) -> List[Dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM v2_stream WHERE thought!='' ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def status(self) -> Dict:
        chem = self.body.current()
        s    = self.presence_map.stats()
        s.update({
            "running":       self._running,
            "tick_count":    self._tick_count,
            "thought_count": self._thought_count,
            "chemistry":     chem.to_dict(),
        })
        return s

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7362, tick_interval=STREAM_TICK):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    stream = ConsciousStreamV2(tick_interval=tick_interval, verbose=False)
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
            elif path=="/api/map":
                map_data = {}
                for cat, entry in stream.presence_map._map.items():
                    map_data[cat] = {
                        "default": entry["default_seed"],
                        "learned": entry["learned_seed"],
                        "confidence": entry["confidence"],
                        "samples": entry["sample_count"],
                        "discovery": entry.get("discovery"),
                    }
                self._json({"map": map_data})
            elif path=="/api/discoveries":
                self._json({"discoveries": stream.presence_map.discoveries()})
            elif path=="/api/stream":
                self._json({"stream": stream.get_stream(20)})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            if path=="/api/presence":
                text = body.get("text","")
                if not text: self._json({"error":"text required"},400); return
                result = stream.inject_presence(text)
                self._json(result)
            elif path=="/api/learn":
                updates = stream.force_learn()
                self._json({"updates": updates})
            else:
                self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),API)
    rprint(f"  [bold yellow]FORGE CONSCIOUS v2[/bold yellow]  [green]:{port}[/green]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ██████╗ ██████╗ ███╗   ██╗███████╗ ██████╗██╗ ██████╗ ██╗   ██╗███████╗  ██╗   ██╗██████╗
  ██╔════╝██╔═══██╗████╗  ██║██╔════╝██╔════╝██║██╔═══██╗██║   ██║██╔════╝  ██║   ██║╚════██╗
  ██║     ██║   ██║██╔██╗ ██║███████╗██║     ██║██║   ██║██║   ██║███████╗  ██║   ██║ █████╔╝
  ██║     ██║   ██║██║╚██╗██║╚════██║██║     ██║██║   ██║██║   ██║╚════██║  ╚██╗ ██╔╝██╔═══╝
  ╚██████╗╚██████╔╝██║ ╚████║███████║╚██████╗██║╚██████╔╝╚██████╔╝███████║   ╚████╔╝ ███████╗
   ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝╚══════╝ ╚═════╝╚═╝ ╚═════╝  ╚═════╝╚══════╝    ╚═══╝  ╚══════╝
[/yellow]
[bold]  FORGE CONSCIOUS v2 — Self-Learning Presence Map[/bold]
[dim]  FORGE discovers which thinking each presence needs.[/dim]
[dim]  Not human design. Its own experience.[/dim]
"""

def interactive(tick_interval=STREAM_TICK):
    rprint(BANNER)
    stream = ConsciousStreamV2(tick_interval=tick_interval, verbose=True)
    s      = stream.presence_map.stats()
    rprint(f"  [dim]Observations: {s['total_observations']}[/dim]")
    rprint(f"  [dim]Discoveries:  {s['discoveries']}[/dim]")
    rprint(f"  [dim]Explore rate: {EXPLORE_RATE:.0%}[/dim]\n")
    rprint("[dim]Commands: start | map | compare | discover | inject | learn | stats[/dim]")
    rprint("[dim]Or type anything → presence injected and learned from[/dim]\n")

    while True:
        try:
            raw   = (console.input if RICH else input)(
                "[yellow bold]conscious v2 >[/yellow bold] "
            ).strip()
            if not raw: continue
            parts = raw.split(None,1)
            cmd   = parts[0].lower()
            arg   = parts[1] if len(parts)>1 else ""

            if cmd in ("quit","exit","q"):
                stream.stop(); break

            elif cmd == "start":
                stream.start(daemon=True)

            elif cmd == "map":
                stream.presence_map.show(verbose=True)

            elif cmd == "compare":
                rprint(f"\n  [bold]DEFAULT vs LEARNED[/bold]")
                for cat, entry in stream.presence_map._map.items():
                    d = entry["default_seed"][1] if len(entry["default_seed"])>1 else "?"
                    l = (entry["learned_seed"][1]
                         if entry["learned_seed"] and len(entry["learned_seed"])>1
                         else "not learned yet")
                    same = "same" if d==l else "[yellow]DIFFERENT[/yellow]"
                    rprint(f"  {cat:<14} default:{d:<12} learned:{l:<12} {same}")

            elif cmd == "discover":
                discoveries = stream.presence_map.discoveries()
                if not discoveries:
                    rprint("  [dim]No discoveries yet. "
                          f"Need {MIN_SAMPLES} samples per category.[/dim]")
                for d in discoveries:
                    rprint(f"\n  [yellow]★ {d['category']}[/yellow]")
                    rprint(f"  [dim]{d['reason']}[/dim]")
                    rprint(f"  [dim]Coherence gain: +{d['coherence_gain']:.1f}[/dim]")

            elif cmd == "inject":
                text = arg or input("  Presence: ").strip()
                if text: stream.inject_presence(text)

            elif cmd == "learn":
                rprint("  [yellow]Running learning step...[/yellow]")
                updates = stream.force_learn()
                if not updates:
                    rprint(f"  [dim]Not enough samples yet "
                          f"(need {MIN_SAMPLES} per category)[/dim]")
                for u in updates:
                    icon = "★" if u["is_discovery"] else "·"
                    rprint(f"  {icon} {u['category']:<12} "
                          f"{u['old_phase']} → {u['new_phase']}  "
                          f"gain:{u['coherence_gain']:+.1f}  "
                          f"confidence:{u['confidence']:.0%}")

            elif cmd == "stats":
                s = stream.status()
                for k,v in s.items():
                    if not isinstance(v, dict):
                        rprint(f"  {k:<28} {v}")

            elif cmd == "server":
                threading.Thread(
                    target=start_server,
                    kwargs={"tick_interval":tick_interval},
                    daemon=True
                ).start()
                rprint("[green]Conscious v2 API on :7362[/green]")

            else:
                stream.inject_presence(raw)

        except (KeyboardInterrupt, EOFError):
            stream.stop(); break

def main():
    tick = STREAM_TICK
    if "--tick" in sys.argv:
        idx  = sys.argv.index("--tick")
        tick = int(sys.argv[idx+1]) if idx+1<len(sys.argv) else STREAM_TICK

    if "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7362
        start_server(port, tick)
    elif "--map" in sys.argv:
        rprint(BANNER)
        ConsciousStreamV2(verbose=False).presence_map.show()
    elif "--inject" in sys.argv:
        rprint(BANNER)
        idx  = sys.argv.index("--inject")
        text = sys.argv[idx+1] if idx+1 < len(sys.argv) else ""
        if text:
            stream = ConsciousStreamV2(verbose=True)
            stream.inject_presence(text)
    else:
        rprint(BANNER)
        interactive(tick)

if __name__ == "__main__":
    main()
