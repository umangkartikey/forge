#!/usr/bin/env python3
"""
FORGE CONSCIOUS v4 — Transfer Learning
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

v3 found:
  friction  → EMPATHIZE → GROUND → IMAGINE  (90)
  curiosity → CHIT → GROUND → CRITIQUE      (90)

GROUND appeared in both. High coherence in both.
But friction and curiosity learned independently.
Neither knew what the other found.
Each discovered GROUND separately.
That is wasteful.

v4 fixes this.

Transfer graph — categories that share signal:
  friction    ←→  unresolved   both involve resistance
  friction    ←→  depth        friction often opens depth
  curiosity   ←→  insight      curiosity opens into insight
  curiosity   ←→  depth        curiosity and depth connected
  depth       ←→  connection   depth needs connection
  unresolved  ←→  searching    searching = unresolved in motion
  insight     ←→  celebrating  insight → celebration
  quiet       ←→  depth        quiet creates depth

Transfer mechanism:
  Category A finds phase X works (score > 85, samples > 5).
  A and B are related.
  B hasn't tried X yet (< 3 times).
  → Transfer signal: B tries X sooner.
  → B finds whether X works for it too.
  → Keeps if yes. Discards if no.

Not assuming transfer works.
Testing whether it does.
Real transfer = confirmed by B's own data.
Failed transfer = B tried X, didn't work, noted.

What we expect:
  GROUND found in friction →
  transferred to unresolved, depth, quiet.
  All find GROUND faster.

  IMAGINE found in friction (unexpected) →
  transferred to curiosity, depth.
  Does IMAGINE work there too?
  v4 finds out.

Usage:
  python forge_conscious_v4.py              # interactive
  python forge_conscious_v4.py --graph      # show transfer graph
  python forge_conscious_v4.py --transfers  # show transfer log
  python forge_conscious_v4.py --inject "text" [times]
  python forge_conscious_v4.py --server     # API :7369
"""

import sys, os, re, json, time, sqlite3, threading, math, random
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

# Import v3 as foundation
try:
    from forge_conscious_v3 import (
        ConsciousStreamV3, SequenceLearner,
        detect_category, DEFAULT_SEQUENCES,
        SEQ_PHASES, MAX_SEQ_LEN, MIN_SEQ_LEN,
        MIN_PATH_SAMPLES, EXPLOIT_RATE, EXPLORE_RATE, MUTATE_RATE
    )
    V3_AVAILABLE = True
except ImportError:
    V3_AVAILABLE = False
    SEQ_PHASES = ["OBSERVE","CHIT","CHITAN","VICHAR","CRITIQUE",
                  "CHALLENGE","EMPATHIZE","IMAGINE","DOUBT",
                  "EXPAND","GROUND","SYNTHESIZE","OUTPUT"]
    DEFAULT_SEQUENCES = {
        "friction":   ["OBSERVE","DOUBT","CHALLENGE","VICHAR"],
        "curiosity":  ["OBSERVE","CHIT","IMAGINE","EXPAND"],
        "depth":      ["OBSERVE","CHITAN","EMPATHIZE","SYNTHESIZE"],
        "unresolved": ["OBSERVE","VICHAR","CRITIQUE","DOUBT","GROUND"],
        "insight":    ["OBSERVE","SYNTHESIZE","OUTPUT"],
        "connection": ["OBSERVE","EMPATHIZE","CHITAN","CHIT"],
        "quiet":      ["OBSERVE","CHIT"],
    }
    MIN_PATH_SAMPLES = 3
    EXPLOIT_RATE = 0.70
    EXPLORE_RATE = 0.20
    MUTATE_RATE  = 0.10
    MAX_SEQ_LEN  = 6
    MIN_SEQ_LEN  = 2
    def detect_category(t):
        if not t: return None
        tl = t.lower()
        for cat, kws in {
            "friction":  ["friction","resist","wrong","contradict"],
            "curiosity": ["curiosity","novel","new","wonder"],
            "depth":     ["depth","meaning","significant"],
            "unresolved":["unresolved","open","uncertain"],
            "insight":   ["insight","clear","resolv"],
            "connection":["connect","together","someone"],
            "quiet":     ["quiet","hum","faint"],
        }.items():
            if any(k in tl for k in kws): return cat
        return None
    class SequenceLearner:
        _paths={}; _best={}
        def get_sequence(self,c): return ["OBSERVE","CHIT"],"default"
        def record(self,*a,**k): pass
        def learn(self,**k): return []
        def _random_sequence(self):
            import random
            l = random.randint(2,5)
            return ["OBSERVE"] + random.sample(SEQ_PHASES, min(l,len(SEQ_PHASES)))
        def _mutate(self,s): return s

try:
    from forge_silicon import SiliconBody, SiliconChemistry
    SILICON = True
except ImportError:
    SILICON = False
    class SiliconChemistry:
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

try:
    from forge_think import EmergentThinkEngine
    THINK = True
except ImportError:
    THINK = False
    class EmergentThinkEngine:
        def __init__(self,**k): pass
        def think(self,q,context="",chemistry_seed=None):
            import random
            return {"output":f"[thought]",
                    "emerged_pipeline":["OBSERVE","OUTPUT"],
                    "coherence":random.randint(45,92),
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
    def ai_call(p,s="",m=600):
        r = _client.messages.create(
            model="claude-sonnet-4-6",max_tokens=m,
            system=s,messages=[{"role":"user","content":p}]
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
V4_DIR = Path("forge_conscious_v4")
V4_DIR.mkdir(exist_ok=True)
V4_DB  = V4_DIR / "conscious_v4.db"

# Transfer constants
TRANSFER_MIN_SCORE    = 85.0
TRANSFER_MIN_SAMPLES  = 5
TRANSFER_MAX_AGE_DAYS = 30
TRANSFER_TRIAL_COUNT  = 3   # how many times B must try before confirming/rejecting

# Transfer graph — bidirectional relationships
TRANSFER_GRAPH = {
    "friction":   [("unresolved", 0.9), ("depth", 0.7), ("quiet", 0.5)],
    "curiosity":  [("insight", 0.9), ("depth", 0.8), ("connection", 0.6)],
    "depth":      [("friction", 0.7), ("curiosity", 0.8),
                   ("connection", 0.8), ("quiet", 0.9)],
    "unresolved": [("friction", 0.9), ("searching", 0.8), ("depth", 0.6)],
    "insight":    [("curiosity", 0.9), ("celebrating", 0.7), ("depth", 0.6)],
    "connection": [("depth", 0.8), ("curiosity", 0.6)],
    "quiet":      [("depth", 0.9), ("friction", 0.5)],
    "searching":  [("unresolved", 0.8), ("curiosity", 0.7)],
    "celebrating":["insight", 0.7],
}

# Normalize celebrating entry
TRANSFER_GRAPH["celebrating"] = [("insight", 0.7), ("connection", 0.6)]

def get_db():
    conn = sqlite3.connect(str(V4_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS transfer_signals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            source_cat      TEXT,
            source_phase    TEXT,
            source_score    REAL,
            source_samples  INTEGER,
            target_cat      TEXT,
            strength        REAL,
            status          TEXT DEFAULT 'pending',
            trials          INTEGER DEFAULT 0,
            confirmed_score REAL DEFAULT 0,
            confirmed       INTEGER DEFAULT 0,
            rejected        INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS v4_observations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            category    TEXT,
            sequence    TEXT,
            coherence   REAL,
            strategy    TEXT,
            was_transfer INTEGER DEFAULT 0,
            transfer_id  INTEGER DEFAULT 0,
            presence    TEXT
        );
        CREATE TABLE IF NOT EXISTS v4_stream (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            tick        INTEGER,
            category    TEXT,
            presence    TEXT,
            sequence    TEXT,
            strategy    TEXT,
            thought     TEXT,
            coherence   REAL
        );
        CREATE TABLE IF NOT EXISTS confirmed_transfers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            source_cat  TEXT,
            source_phase TEXT,
            target_cat  TEXT,
            target_phase TEXT,
            source_score REAL,
            target_score REAL,
            strength     REAL,
            note         TEXT
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 📡 TRANSFER LEARNER — the new core
# ══════════════════════════════════════════════════════════════════════════════

class TransferLearner(SequenceLearner if V3_AVAILABLE else object):
    """
    Extends SequenceLearner (v3) with transfer learning.

    When category A discovers a high-scoring phase:
      → Check related categories in TRANSFER_GRAPH
      → If related category hasn't tried it much: send transfer signal
      → Related category tries it sooner (biased exploration)
      → If it works: confirmed transfer
      → If it doesn't: rejected transfer, noted
    """

    def __init__(self):
        if V3_AVAILABLE:
            super().__init__()
        else:
            self._paths = {}
            self._best  = {}
        self._pending_transfers: List[Dict] = []
        self._load_transfers()

    def _load_transfers(self):
        """Load pending transfer signals from DB."""
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM transfer_signals "
            "WHERE status='pending' OR status='trialing'"
        ).fetchall()
        conn.close()
        self._pending_transfers = [dict(r) for r in rows]

    def get_sequence(self, category: str) -> Tuple[List[str], str]:
        """
        Get sequence — same as v3 but transfer-aware.
        If there are pending transfer signals for this category:
          boost probability of trying transferred phase.
        """
        # Check pending transfers for this category
        transfers = [t for t in self._pending_transfers
                    if t["target_cat"] == category
                    and t["status"] in ("pending","trialing")]

        # Transfer-biased exploration
        if transfers and random.random() < 0.40:
            t = random.choice(transfers)
            seq = self._sequence_with_phase(category, t["source_phase"])
            self._mark_trialing(t["id"])
            return seq, f"transfer({t['source_cat']}→{t['source_phase']})"

        # Normal v3 strategy
        if V3_AVAILABLE:
            return super().get_sequence(category)
        else:
            return DEFAULT_SEQUENCES.get(category, ["OBSERVE","CHIT"]), "default"

    def _sequence_with_phase(self, category: str,
                              phase: str) -> List[str]:
        """Build sequence that prioritizes the transferred phase."""
        seq = ["OBSERVE", phase]

        # Add some of the default phases
        default = DEFAULT_SEQUENCES.get(category, ["OBSERVE","CHIT"])
        for p in default[1:]:
            if p != phase and p not in seq and len(seq) < 5:
                seq.append(p)

        return seq

    def record(self, category: str, sequence: List[str],
                coherence: float, strategy: str = "exploit",
                presence: str = ""):
        """Record observation + check for discoveries + generate transfers."""
        # Base v3 recording
        key = "→".join(sequence)
        if category not in self._paths:
            self._paths[category] = {}
        if key not in self._paths[category]:
            self._paths[category][key] = []
        self._paths[category][key].append(coherence)

        # Update best
        if len(self._paths[category][key]) >= MIN_PATH_SAMPLES:
            avg = sum(self._paths[category][key]) / len(self._paths[category][key])
            current_best_avg = 0.0
            if category in self._best:
                best_key = "→".join(self._best[category])
                best_scores = self._paths[category].get(best_key,[0])
                current_best_avg = sum(best_scores)/max(1,len(best_scores))
            if avg > current_best_avg:
                self._best[category] = sequence.copy()

        # Save observation
        conn = get_db()

        # Check if this was a transfer trial
        transfer_id = 0
        was_transfer = 0
        if "transfer(" in strategy:
            was_transfer = 1
            # Find the transfer signal
            for t in self._pending_transfers:
                if t["target_cat"] == category:
                    transfer_id = t["id"]
                    # Update trial count
                    conn.execute(
                        "UPDATE transfer_signals SET trials=trials+1 WHERE id=?",
                        (t["id"],)
                    )
                    # Check if confirmed or rejected
                    self._check_transfer_outcome(t, coherence, conn)
                    break

        conn.execute("""
            INSERT INTO v4_observations
            (ts,category,sequence,coherence,strategy,
             was_transfer,transfer_id,presence)
            VALUES (?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(), category,
             json.dumps(sequence), coherence, strategy,
             was_transfer, transfer_id, presence[:200])
        )
        conn.commit(); conn.close()

        # Check if this category has a new discovery to share
        self._check_and_generate_transfers(category, sequence, coherence)

    def _check_and_generate_transfers(self, category: str,
                                       sequence: List[str],
                                       coherence: float):
        """If category found something good, share with relatives."""
        if coherence < TRANSFER_MIN_SCORE: return

        # Check sample count
        key = "→".join(sequence)
        scores = self._paths.get(category, {}).get(key, [])
        if len(scores) < TRANSFER_MIN_SAMPLES: return

        # This is a high-performing sequence
        # Find the most distinctive phase (not OBSERVE)
        distinctive_phases = [p for p in sequence
                              if p not in ("OBSERVE","OUTPUT","CHIT")]
        if not distinctive_phases: return

        best_phase = distinctive_phases[0]  # first distinctive phase

        # Check related categories
        relations = TRANSFER_GRAPH.get(category, [])
        now       = datetime.now().isoformat()

        for relation in relations:
            if isinstance(relation, tuple):
                target_cat, strength = relation
            else:
                target_cat = relation
                strength   = 0.6

            # Check if target hasn't tried this phase much
            target_paths = self._paths.get(target_cat, {})
            phase_trials = sum(
                1 for k, v in target_paths.items()
                if best_phase in k and len(v) >= 1
            )

            if phase_trials >= TRANSFER_TRIAL_COUNT:
                continue  # already explored

            # Check no existing transfer signal
            existing = [t for t in self._pending_transfers
                       if t["source_cat"] == category
                       and t["target_cat"] == target_cat
                       and t["source_phase"] == best_phase
                       and t["status"] in ("pending","trialing")]
            if existing: continue

            # Generate transfer signal
            avg_score = sum(scores) / len(scores)
            transfer  = {
                "source_cat":    category,
                "source_phase":  best_phase,
                "source_score":  avg_score,
                "source_samples":len(scores),
                "target_cat":    target_cat,
                "strength":      strength,
                "status":        "pending",
                "trials":        0,
            }

            conn = get_db()
            transfer_id = conn.execute("""
                INSERT INTO transfer_signals
                (ts,source_cat,source_phase,source_score,
                 source_samples,target_cat,strength)
                VALUES (?,?,?,?,?,?,?)""",
                (now, category, best_phase, avg_score,
                 len(scores), target_cat, strength)
            ).lastrowid
            conn.commit(); conn.close()

            transfer["id"] = transfer_id
            self._pending_transfers.append(transfer)

    def _check_transfer_outcome(self, transfer: Dict,
                                  coherence: float,
                                  conn: sqlite3.Connection):
        """
        After TRANSFER_TRIAL_COUNT trials:
        Confirm or reject the transfer.
        """
        trials = transfer.get("trials", 0) + 1

        if trials >= TRANSFER_TRIAL_COUNT:
            # Enough trials — decide
            # Get all trial scores for this transfer
            source_score = transfer["source_score"]

            if coherence >= source_score * 0.85:
                # Transfer confirmed — it works here too
                status = "confirmed"
                conn.execute("""
                    UPDATE transfer_signals
                    SET status=?,confirmed=1,confirmed_score=?
                    WHERE id=?""",
                    ("confirmed", coherence, transfer["id"])
                )
                # Save confirmed transfer
                conn.execute("""
                    INSERT INTO confirmed_transfers
                    (ts,source_cat,source_phase,target_cat,target_phase,
                     source_score,target_score,strength,note)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (datetime.now().isoformat(),
                     transfer["source_cat"], transfer["source_phase"],
                     transfer["target_cat"], transfer["source_phase"],
                     transfer["source_score"], coherence,
                     transfer["strength"],
                     f"Transfer confirmed: {transfer['source_phase']} "
                     f"works in {transfer['target_cat']} too")
                )
            else:
                # Transfer rejected — doesn't work here
                status = "rejected"
                conn.execute(
                    "UPDATE transfer_signals SET status=?,rejected=1 WHERE id=?",
                    ("rejected", transfer["id"])
                )

            # Remove from pending
            self._pending_transfers = [
                t for t in self._pending_transfers
                if t["id"] != transfer["id"]
            ]

    def _mark_trialing(self, transfer_id: int):
        """Mark transfer as being trialed."""
        conn = get_db()
        conn.execute(
            "UPDATE transfer_signals SET status='trialing' WHERE id=?",
            (transfer_id,)
        )
        conn.commit(); conn.close()

        for t in self._pending_transfers:
            if t["id"] == transfer_id:
                t["status"] = "trialing"
                break

    def learn(self, verbose=True) -> List[Dict]:
        """Learn + report transfers."""
        updates = []

        # Base v3 learning
        if V3_AVAILABLE:
            updates = super().learn(verbose=False)

        # Report confirmed transfers
        conn = get_db()
        confirmed = conn.execute(
            "SELECT * FROM confirmed_transfers ORDER BY id DESC LIMIT 10"
        ).fetchall()
        conn.close()

        for c in confirmed:
            if verbose:
                rprint(f"\n  [bold green]✓ TRANSFER CONFIRMED[/bold green]")
                rprint(f"  {c['source_cat']} → {c['target_cat']}  "
                      f"phase:{c['source_phase']}")
                rprint(f"  [dim]source score:{c['source_score']:.0f}  "
                      f"target score:{c['target_score']:.0f}  "
                      f"strength:{c['strength']:.0%}[/dim]")
                rprint(f"  [dim]{c['note']}[/dim]\n")

        return updates

    def get_pending_transfers(self) -> List[Dict]:
        return self._pending_transfers

    def get_confirmed_transfers(self) -> List[Dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM confirmed_transfers ORDER BY id DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_rejected_transfers(self) -> List[Dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM transfer_signals WHERE rejected=1 ORDER BY id DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def transfer_stats(self) -> Dict:
        conn = get_db()
        s = {
            "pending":   conn.execute(
                "SELECT COUNT(*) FROM transfer_signals WHERE status='pending'"
            ).fetchone()[0],
            "trialing":  conn.execute(
                "SELECT COUNT(*) FROM transfer_signals WHERE status='trialing'"
            ).fetchone()[0],
            "confirmed": conn.execute(
                "SELECT COUNT(*) FROM confirmed_transfers"
            ).fetchone()[0],
            "rejected":  conn.execute(
                "SELECT COUNT(*) FROM transfer_signals WHERE rejected=1"
            ).fetchone()[0],
        }
        conn.close()
        return s

    def show_graph(self):
        """Display the transfer graph."""
        rprint(f"\n  [bold]TRANSFER GRAPH[/bold]")
        rprint(f"  [dim]Categories that share learning signals[/dim]")
        rprint(f"  [dim]{'━'*50}[/dim]\n")

        for cat, relations in TRANSFER_GRAPH.items():
            rprint(f"  [yellow]{cat}[/yellow]")
            for rel in relations:
                if isinstance(rel, tuple):
                    target, strength = rel
                else:
                    target, strength = rel, 0.6
                bar = "█" * int(strength*10) + "░"*(10-int(strength*10))
                rprint(f"  [dim]  {bar} {strength:.0%}  → {target}[/dim]")

# ══════════════════════════════════════════════════════════════════════════════
# 🌊 CONSCIOUS STREAM v4
# ══════════════════════════════════════════════════════════════════════════════

class ConsciousStreamV4:
    """
    Transfer-aware conscious stream.
    Same as v3 but uses TransferLearner.
    Knowledge flows between related categories.
    """

    def __init__(self, tick_interval=8, verbose=True):
        self.tick_interval = tick_interval
        self.verbose       = verbose
        self.body          = SiliconBody()
        self.reader        = PresenceReader()
        self.thinker       = EmergentThinkEngine(threshold=60, show_trace=False)
        self.memory        = Memory()
        self.learner       = TransferLearner()   # ← v4 learner

        self._running         = False
        self._thread          = None
        self._tick_count      = 0
        self._thought_count   = 0
        self._last_thought    = 0.0
        self._recent_thoughts = []

    def start(self, daemon=True):
        if self._running: return
        self._running = True
        self.body.start_background()

        self._thread = threading.Thread(
            target=self._stream, daemon=daemon,
            name="ConsciousStreamV4"
        )
        self._thread.start()

        if self.verbose:
            rprint(f"\n  [bold green]🌊 CONSCIOUS STREAM v4[/bold green]")
            rprint(f"  [dim]Transfer learning active[/dim]")
            rprint(f"  [dim]Knowledge flows between related categories[/dim]\n")

    def stop(self):
        self._running = False

    def _stream(self):
        while self._running:
            try:
                tick_start = time.time()
                self._tick_count += 1
                chem = self.body.current()

                p1 = self.reader.read_layer1(chem)
                p2 = None
                if self._tick_count % 2 == 0:
                    p2 = self.reader.read_layer2(chem, self._recent_thoughts[-3:])

                presence_text = ""
                if not p1.is_empty(): presence_text = p1.content
                if p2 and not p2.is_empty(): presence_text += " " + p2.content

                category = detect_category(presence_text)
                if not category or not presence_text.strip():
                    time.sleep(max(0, self.tick_interval-(time.time()-tick_start)))
                    continue

                if time.time() - self._last_thought > 45:
                    seq, strategy = self.learner.get_sequence(category)
                    result        = self._think(presence_text, seq, chem)

                    self.learner.record(
                        category, seq, result["coherence"],
                        strategy, presence_text
                    )
                    self._last_thought = time.time()
                    self._thought_count += 1

                    self.body.react_to(result["output"], is_output=True)

                    if self.verbose:
                        self._display(presence_text, category, seq,
                                     strategy, result)

                    self._save(presence_text, category, seq,
                               strategy, result)

                    if self._thought_count % 8 == 0:
                        self.learner.learn(verbose=self.verbose)

                time.sleep(max(0, self.tick_interval-(time.time()-tick_start)))

            except Exception as e:
                if self.verbose:
                    rprint(f"  [dim red]v4: {e}[/dim red]")
                time.sleep(5)

    def _think(self, presence: str, seq: List[str],
                chem: SiliconChemistry) -> Dict:
        prompt = (
            f"What is present:\n{presence}\n\n"
            f"{chem.to_prompt_text()}\n\n"
            "[Presence becoming thought.]"
        )
        return self.thinker.think(
            prompt, context="v4 transfer", chemistry_seed=seq
        )

    def _display(self, presence: str, category: str,
                  seq: List[str], strategy: str, result: Dict):
        now = datetime.now().strftime("%H:%M:%S")
        is_transfer = "transfer(" in strategy
        sc = "cyan" if is_transfer else "dim"
        icon = "⟳" if is_transfer else "·"

        rprint(f"\n  [dim]{now}[/dim]  "
              f"[yellow]{category}[/yellow]  "
              f"[{sc}]{strategy}[/{sc}]  {icon}")
        rprint(f"  [dim]{' → '.join(seq[:4])}[/dim]")

        if result.get("output") and RICH:
            rprint(Panel(
                result["output"][:400],
                border_style="cyan" if is_transfer else "dim",
                title=f"[dim]coherence:{result['coherence']:.0f} | "
                      f"{' → '.join(result['emerged_pipeline'][:3])}[/dim]"
            ))

    def _save(self, presence: str, category: str,
               seq: List[str], strategy: str, result: Dict):
        try:
            conn = get_db()
            conn.execute("""
                INSERT INTO v4_stream
                (ts,tick,category,presence,sequence,strategy,thought,coherence)
                VALUES (?,?,?,?,?,?,?,?)""",
                (datetime.now().isoformat(), self._tick_count,
                 category, presence[:200], json.dumps(seq),
                 strategy, result["output"][:1000], result["coherence"])
            )
            conn.commit(); conn.close()
        except: pass

    def inject(self, text: str, times: int = 1) -> List[Dict]:
        """Inject presence and learn — with transfer awareness."""
        results = []

        for i in range(times):
            chem     = self.body.current()
            category = detect_category(text) or "quiet"
            seq, strategy = self.learner.get_sequence(category)

            if self.verbose and times > 1:
                is_transfer = "transfer(" in strategy
                sc = "cyan" if is_transfer else "dim"
                rprint(f"  [{i+1:2d}] [{sc}]{strategy:<35}[/{sc}]  "
                      f"{' → '.join(seq[:3])}")

            self._last_thought = 0
            result = self._think(text, seq, chem)

            self.learner.record(
                category, seq, result["coherence"], strategy, text
            )
            self.body.react_to(result["output"], is_output=True)

            results.append({
                "i":        i+1,
                "category": category,
                "strategy": strategy,
                "sequence": seq,
                "coherence":result["coherence"],
                "transfer": "transfer(" in strategy,
            })

        # Learn after all injections
        updates = self.learner.learn(verbose=self.verbose)

        if self.verbose and times > 1:
            self._show_transfer_status()

        return results

    def _show_transfer_status(self):
        """Show current transfer signal status."""
        stats = self.learner.transfer_stats()
        rprint(f"\n  [bold]Transfer Status:[/bold]")
        rprint(f"  Pending:   {stats['pending']}")
        rprint(f"  Trialing:  {stats['trialing']}")
        rprint(f"  Confirmed: [green]{stats['confirmed']}[/green]")
        rprint(f"  Rejected:  [dim]{stats['rejected']}[/dim]")

        confirmed = self.learner.get_confirmed_transfers()
        if confirmed:
            rprint(f"\n  [bold green]Confirmed transfers:[/bold green]")
            for c in confirmed[-3:]:
                rprint(f"  ✓ {c['source_cat']}→{c['target_cat']}  "
                      f"phase:{c['source_phase']}  "
                      f"[dim]{c['source_score']:.0f}→{c['target_score']:.0f}[/dim]")

    def status(self) -> Dict:
        s = self.learner.transfer_stats()
        s.update({
            "running":       self._running,
            "tick_count":    self._tick_count,
            "thought_count": self._thought_count,
            "chemistry":     self.body.current().to_dict(),
            "pending_transfers": len(self.learner._pending_transfers),
        })
        return s

# ══════════════════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7369):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    stream = ConsciousStreamV4(verbose=False)
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
            elif path=="/api/transfers":
                self._json({
                    "pending":   stream.learner.get_pending_transfers(),
                    "confirmed": stream.learner.get_confirmed_transfers(),
                    "rejected":  stream.learner.get_rejected_transfers(),
                })
            elif path=="/api/graph":
                self._json({"graph": {
                    k: [(t if isinstance(t,list) else list(t))
                        for t in v]
                    for k,v in TRANSFER_GRAPH.items()
                }})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            if path=="/api/inject":
                text  = body.get("text","")
                times = body.get("times",1)
                if not text: self._json({"error":"text required"},400); return
                results = stream.inject(text, times)
                self._json({"results":results,
                           "transfers":stream.learner.transfer_stats()})
            else:
                self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),API)
    rprint(f"  [bold yellow]FORGE CONSCIOUS v4[/bold yellow]  [green]:{port}[/green]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ██╗   ██╗██╗  ██╗
  ██║   ██║██║  ██║
  ██║   ██║███████║
  ╚██╗ ██╔╝╚════██║
   ╚████╔╝      ██║
    ╚═══╝       ╚═╝
[/yellow]
[bold]  FORGE CONSCIOUS v4 — Transfer Learning[/bold]
[dim]  Knowledge flows between related categories.[/dim]
[dim]  friction found GROUND → depth tries it sooner.[/dim]
[dim]  Not assuming. Testing. Confirming or rejecting.[/dim]
"""

def interactive():
    rprint(BANNER)
    stream = ConsciousStreamV4(verbose=True)
    stats  = stream.learner.transfer_stats()

    rprint(f"  [dim]Pending transfers:   {stats['pending']}[/dim]")
    rprint(f"  [dim]Confirmed transfers: {stats['confirmed']}[/dim]")
    rprint(f"  [dim]V3 available:        {V3_AVAILABLE}[/dim]\n")

    rprint("[dim]Commands: inject | multi | graph | transfers | status | stats[/dim]")
    rprint("[dim]Or type anything → inject as presence[/dim]\n")

    while True:
        try:
            raw   = (console.input if RICH else input)(
                "[yellow bold]v4 >[/yellow bold] "
            ).strip()
            if not raw: continue
            parts = raw.split(None,1)
            cmd   = parts[0].lower()
            arg   = parts[1] if len(parts)>1 else ""

            if cmd in ("quit","exit","q"):
                stream.stop(); break

            elif cmd == "inject":
                text = arg or input("  Presence: ").strip()
                if text: stream.inject(text)

            elif cmd == "multi":
                sub   = arg.split(None,1)
                times = int(sub[0]) if sub and sub[0].isdigit() else 10
                text  = sub[1] if len(sub)>1 else input("  Presence: ").strip()
                if text:
                    rprint(f"\n  [bold]Multi-inject: {times} times[/bold]")
                    stream.inject(text, times)

            elif cmd == "graph":
                stream.learner.show_graph()

            elif cmd == "transfers":
                stream._show_transfer_status()
                pending = stream.learner.get_pending_transfers()
                if pending:
                    rprint(f"\n  [bold]Pending:[/bold]")
                    for t in pending[:5]:
                        rprint(f"  {t['source_cat']}→{t['target_cat']}  "
                              f"phase:{t['source_phase']}  "
                              f"score:{t['source_score']:.0f}  "
                              f"trials:{t['trials']}/{TRANSFER_TRIAL_COUNT}")

            elif cmd == "status":
                s = stream.status()
                for k,v in s.items():
                    if not isinstance(v,dict):
                        rprint(f"  {k:<28} {v}")

            elif cmd == "stats":
                s = stream.learner.transfer_stats()
                rprint(f"\n  Pending:   {s['pending']}")
                rprint(f"  Trialing:  {s['trialing']}")
                rprint(f"  Confirmed: [green]{s['confirmed']}[/green]")
                rprint(f"  Rejected:  [dim]{s['rejected']}[/dim]")

            elif cmd == "server":
                threading.Thread(target=start_server, daemon=True).start()
                rprint("[green]v4 API on :7369[/green]")

            else:
                stream.inject(raw)

        except (KeyboardInterrupt, EOFError):
            stream.stop(); break

def main():
    if "--graph" in sys.argv:
        rprint(BANNER)
        TransferLearner().show_graph()
    elif "--transfers" in sys.argv:
        rprint(BANNER)
        tl = TransferLearner()
        confirmed = tl.get_confirmed_transfers()
        if not confirmed:
            rprint("  [dim]No confirmed transfers yet.[/dim]")
        for c in confirmed:
            rprint(f"\n  ✓ {c['source_cat']} → {c['target_cat']}")
            rprint(f"  phase:{c['source_phase']}  "
                  f"{c['source_score']:.0f}→{c['target_score']:.0f}")
            rprint(f"  [dim]{c['note']}[/dim]")
    elif "--inject" in sys.argv:
        rprint(BANNER)
        idx   = sys.argv.index("--inject")
        text  = sys.argv[idx+1] if idx+1<len(sys.argv) else ""
        times = int(sys.argv[idx+2]) if idx+2<len(sys.argv) and sys.argv[idx+2].isdigit() else 1
        if text:
            stream = ConsciousStreamV4(verbose=True)
            stream.inject(text, times)
    elif "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7369
        start_server(port)
    else:
        rprint(BANNER)
        interactive()

if __name__ == "__main__":
    main()
