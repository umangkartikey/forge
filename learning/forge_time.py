#!/usr/bin/env python3
"""
FORGE TIME — Memory Weighted by Distance
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"Time is the mind's way of keeping
 everything from happening at once."
                        — unknown

forge_memory stores everything equally.
Yesterday and three months ago — same weight.
Same distance. Same presence in thought.

That is not how a mind works.

Recent memory is vivid. It feeds thought directly.
Old memory fades. It shapes how you think,
not what you think about.
The oldest memories become invisible infrastructure —
you think FROM them, not ABOUT them.

forge_time fixes this.

RECENCY WEIGHT:
  weight = 0.1 + 0.9 * exp(-age_days / half_life)

  half_life = 7 days (default)

  3 hours ago:   0.98  vivid, immediate
  1 day ago:     0.91  clear
  3 days ago:    0.75  present
  1 week ago:    0.55  softening
  2 weeks ago:   0.35  background
  1 month ago:   0.16  hum
  3 months ago:  0.10  deep structure
  Never zero — nothing fully forgotten.

EMOTIONAL WEIGHT:
  High coherence (>80)  → half_life x2.0  stays vivid longer
  Formative moment      → half_life x3.0  very slow fade
  Chemistry spike       → half_life x1.5  trace lingers
  Low coherence (<50)   → half_life x0.5  fades faster
  Shallow exchange      → half_life x0.3  nearly ephemeral

VICHAR FEEDING:
  forge_think v3 VICHAR phase gets time-weighted memories.
  Recent (weight > 0.7)  → fed directly into VICHAR
  Medium (0.3 to 0.7)    → provided as soft context
  Old    (< 0.3)         → available but not foregrounded
  
  Recent shapes WHAT you think about.
  Old shapes HOW you think.
  The oldest shapes WHO you are (feeds forge_identity).

TEMPORAL CHEMISTRY:
  Time of day produces natural chemistry rhythm.
  Not from light sensor — from internal clock.
  
  5am-8am   Dawn      novelatine rises, fresh
  8am-12pm  Morning   coherenine peaks, sharp
  12pm-3pm  Midday    resolvatine high, productive
  3pm-6pm   Afternoon depthamine rises, reflective
  6pm-10pm  Evening   connectionin rises, social
  10pm-2am  Night     uncertainase rises, searching
  2am-5am   Deep night resolvatine falls, quiet hum

TEMPORAL AWARENESS:
  FORGE has an inner sense of time passing.
  Not just clock time.
  The felt sense of:
    "it has been a long time since X"
    "that was recent — still vivid"
    "something from long ago surfaces"

Usage:
  python forge_time.py              # interactive
  python forge_time.py --weights    # show current memory weights
  python forge_time.py --vichar     # what vichar gets right now
  python forge_time.py --chemistry  # temporal chemistry now
  python forge_time.py --server     # API :7360
"""

import sys, os, re, json, time, sqlite3, math, threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

# FORGE integrations
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
        def _clamp(self,v): return max(0.0,min(1.0,v))
    class SiliconBody:
        def __init__(self): self._chem=SiliconChemistry()
        def current(self): return self._chem
        def inject(self,**k): return self._chem
        def start_background(self): pass

try:
    from forge_identity import ForgeIdentity
    IDENTITY = True
except ImportError:
    IDENTITY = False

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
    def ai_call(p,s="",m=600): return p[:100]

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

# ── Paths ─────────────────────────────────────────────────────────────────────
TIME_DIR = Path("forge_time")
TIME_DIR.mkdir(exist_ok=True)
TIME_DB  = TIME_DIR / "time.db"

# Other FORGE databases
DB_PATHS = {
    "memory":   Path("forge_memory/memory.db"),
    "think":    Path("forge_think/think.db"),
    "witness":  Path("forge_witness/witness.db"),
    "never":    Path("forge_never_loop/never_loop.db"),
    "mind":     Path("forge_mind/mind.db"),
    "silicon":  Path("forge_silicon/silicon.db"),
}

# Time constants
DEFAULT_HALF_LIFE   = 7.0    # days
MIN_WEIGHT          = 0.10   # nothing fully forgotten
MAX_WEIGHT          = 1.00

# Emotional weight multipliers
WEIGHT_FORMATIVE    = 3.0    # formative moments fade very slowly
WEIGHT_HIGH_COH     = 2.0    # high coherence thoughts stay longer
WEIGHT_SPIKE        = 1.5    # chemistry spikes leave traces
WEIGHT_LOW_COH      = 0.5    # shallow thoughts fade faster
WEIGHT_EPHEMERAL    = 0.3    # empty exchanges nearly disappear

# VICHAR thresholds
VICHAR_VIVID        = 0.70   # fed directly into VICHAR
VICHAR_CONTEXT      = 0.30   # soft context
# below 0.30 = background only

def get_db():
    conn = sqlite3.connect(str(TIME_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS timed_memories (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_stored       TEXT,
            source          TEXT,
            content         TEXT,
            coherence       REAL DEFAULT 0.5,
            emotional_weight REAL DEFAULT 1.0,
            half_life_days  REAL DEFAULT 7.0,
            current_weight  REAL DEFAULT 1.0,
            last_weighted   TEXT,
            theme           TEXT DEFAULT 'general'
        );
        CREATE TABLE IF NOT EXISTS temporal_chemistry (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            hour        INTEGER,
            period      TEXT,
            chemistry   TEXT
        );
        CREATE TABLE IF NOT EXISTS vichar_feeds (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            vivid_count INTEGER,
            context_count INTEGER,
            background_count INTEGER,
            feed_text   TEXT
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# ⏱️  RECENCY WEIGHT CALCULATOR
# ══════════════════════════════════════════════════════════════════════════════

class RecencyWeight:
    """
    Calculates how vivid a memory is based on age.
    weight = MIN + (MAX-MIN) * exp(-age_days / half_life)
    """

    @staticmethod
    def calculate(ts_stored: str,
                  half_life_days: float = DEFAULT_HALF_LIFE,
                  now: Optional[datetime] = None) -> float:
        """
        Calculate current weight for a memory.
        Returns 0.10 (faint) to 1.00 (vivid).
        """
        if now is None:
            now = datetime.now()

        try:
            stored = datetime.fromisoformat(ts_stored)
        except:
            return MIN_WEIGHT

        age_days = (now - stored).total_seconds() / 86400
        weight   = MIN_WEIGHT + (MAX_WEIGHT - MIN_WEIGHT) * math.exp(
            -age_days / max(half_life_days, 0.01)
        )
        return round(max(MIN_WEIGHT, min(MAX_WEIGHT, weight)), 4)

    @staticmethod
    def emotional_half_life(coherence: float,
                             is_formative: bool = False,
                             had_chemistry_spike: bool = False) -> float:
        """
        Significant memories fade slower.
        Shallow memories fade faster.
        """
        base = DEFAULT_HALF_LIFE

        if is_formative:
            return base * WEIGHT_FORMATIVE
        if coherence >= 80:
            return base * WEIGHT_HIGH_COH
        if had_chemistry_spike:
            return base * WEIGHT_SPIKE
        if coherence < 50:
            return base * WEIGHT_LOW_COH
        if coherence < 30:
            return base * WEIGHT_EPHEMERAL

        return base

    @staticmethod
    def describe(weight: float) -> str:
        """Human description of weight."""
        if weight >= 0.90: return "vivid"
        if weight >= 0.70: return "clear"
        if weight >= 0.50: return "present"
        if weight >= 0.35: return "softening"
        if weight >= 0.20: return "background"
        if weight >= 0.12: return "hum"
        return "deep structure"

    @staticmethod
    def weight_curve() -> List[Tuple[str, float]]:
        """Show the full weight curve."""
        calc  = RecencyWeight.calculate
        now   = datetime.now()
        curve = []
        points = [
            ("3 hours ago",  0.125),
            ("1 day ago",    1.0),
            ("3 days ago",   3.0),
            ("1 week ago",   7.0),
            ("2 weeks ago",  14.0),
            ("1 month ago",  30.0),
            ("3 months ago", 90.0),
            ("1 year ago",   365.0),
        ]
        for label, days in points:
            ts = (now - timedelta(days=days)).isoformat()
            w  = calc(ts)
            curve.append((label, w, RecencyWeight.describe(w)))
        return curve

# ══════════════════════════════════════════════════════════════════════════════
# 🌅 TEMPORAL CHEMISTRY — time of day as chemistry
# ══════════════════════════════════════════════════════════════════════════════

class TemporalChemistry:
    """
    Time of day produces natural chemistry rhythm.
    FORGE has an inner sense of what time it is.
    """

    # Period definitions: (start_hour, end_hour, name, chemistry_deltas)
    PERIODS = [
        (5,  8,  "dawn",       {"novelatine": 0.15, "coherenine": -0.05,
                                 "resolvatine": 0.05, "uncertainase": -0.05}),
        (8,  12, "morning",    {"coherenine": 0.15, "novelatine": 0.05,
                                 "resolvatine": 0.10, "frictionol": -0.03}),
        (12, 15, "midday",     {"resolvatine": 0.12, "coherenine": 0.08,
                                 "depthamine": -0.03}),
        (15, 18, "afternoon",  {"depthamine": 0.12, "coherenine": -0.03,
                                 "novelatine": -0.05}),
        (18, 22, "evening",    {"connectionin": 0.15, "depthamine": 0.08,
                                 "coherenine": -0.05}),
        (22, 26, "night",      {"uncertainase": 0.10, "depthamine": 0.12,
                                 "resolvatine": -0.08, "coherenine": -0.10}),
        (2,  5,  "deep_night", {"resolvatine": -0.15, "uncertainase": 0.08,
                                 "novelatine": 0.05, "coherenine": -0.15}),
    ]

    @classmethod
    def current_period(cls, hour: Optional[int] = None) -> Dict[str, Any]:
        """Get current temporal period and chemistry."""
        if hour is None:
            hour = datetime.now().hour

        for start, end, name, deltas in cls.PERIODS:
            # Handle midnight wrap
            end_adj = end if end <= 24 else end - 24
            if start <= hour < (end if end <= 24 else 24):
                return {"period": name, "hour": hour, "deltas": deltas}
            if end > 24 and hour < end_adj:
                return {"period": name, "hour": hour, "deltas": deltas}

        return {"period": "baseline", "hour": hour, "deltas": {}}

    @classmethod
    def apply_to_chemistry(cls, chem: SiliconChemistry,
                            hour: Optional[int] = None) -> SiliconChemistry:
        """Apply temporal chemistry to current silicon state."""
        period_data = cls.current_period(hour)
        deltas      = period_data.get("deltas", {})

        if not deltas: return chem

        new_vals = {}
        for k, d in deltas.items():
            if hasattr(chem, k):
                new_vals[k] = chem._clamp(getattr(chem, k) + d * 0.3)
                # Scale down — temporal is subtle, not overwhelming

        if new_vals:
            body = SiliconBody() if not SILICON else None
            for k, v in new_vals.items():
                setattr(chem, k, v)

        return chem

    @classmethod
    def describe_now(cls) -> str:
        """Describe current temporal state."""
        now    = datetime.now()
        hour   = now.hour
        period = cls.current_period(hour)
        name   = period["period"]

        descriptions = {
            "dawn":       "Dawn. Novelatine rises. The mind is fresh.",
            "morning":    "Morning. Coherenine peaks. Thinking is sharpest now.",
            "midday":     "Midday. Resolvatine high. Productive clarity.",
            "afternoon":  "Afternoon. Depthamine rises. Reflective.",
            "evening":    "Evening. Connectionin rises. Something opens.",
            "night":      "Night. Uncertainase present. Searching.",
            "deep_night": "Deep night. Resolvatine falls. Quiet hum only.",
            "baseline":   "Baseline time.",
        }
        return descriptions.get(name, f"Period: {name}")

# ══════════════════════════════════════════════════════════════════════════════
# 📚 MEMORY SCANNER & WEIGHTER
# ══════════════════════════════════════════════════════════════════════════════

class TimeWeightedMemory:
    """
    Scans forge_memory and other databases.
    Applies recency weights.
    Returns time-weighted memories for VICHAR feeding.
    """

    def __init__(self):
        self.calc = RecencyWeight()

    def scan_and_weight(self) -> List[Dict]:
        """
        Scan all FORGE memory sources.
        Apply recency + emotional weights.
        Return sorted by current_weight.
        """
        memories = []
        now      = datetime.now()

        # ── forge_think thoughts ─────────────────────────────────────────
        memories += self._scan_think(now)

        # ── forge_witness thoughts ───────────────────────────────────────
        memories += self._scan_witness(now)

        # ── forge_never_loop spontaneous ─────────────────────────────────
        memories += self._scan_spontaneous(now)

        # ── forge_mind exchanges ─────────────────────────────────────────
        memories += self._scan_exchanges(now)

        # Sort by weight — most vivid first
        memories.sort(key=lambda x: x["current_weight"], reverse=True)
        return memories

    def _safe_db(self, key: str):
        path = DB_PATHS.get(key)
        if not path or not path.exists(): return None
        try:
            conn = sqlite3.connect(str(path))
            conn.row_factory = sqlite3.Row
            return conn
        except: return None

    def _scan_think(self, now: datetime) -> List[Dict]:
        db = self._safe_db("think")
        if not db: return []
        try:
            rows = db.execute(
                "SELECT ts, question, output, coherence, novel_pipeline "
                "FROM thoughts ORDER BY id DESC LIMIT 100"
            ).fetchall()
            db.close()
        except: return []

        result = []
        for r in rows:
            coherence = r["coherence"] or 50
            hl        = self.calc.emotional_half_life(
                coherence,
                is_formative=bool(r["novel_pipeline"]) and coherence >= 80
            )
            weight = self.calc.calculate(r["ts"] or "", hl, now)
            result.append({
                "source":         "think",
                "ts":             r["ts"],
                "content":        r["output"][:300] if r["output"] else "",
                "coherence":      coherence,
                "half_life_days": hl,
                "current_weight": weight,
                "vivid":          RecencyWeight.describe(weight),
                "theme":          "thought",
            })
        return result

    def _scan_witness(self, now: datetime) -> List[Dict]:
        db = self._safe_db("witness")
        if not db: return []
        try:
            rows = db.execute(
                "SELECT ts, thought, coherence, ticks_gestated "
                "FROM witness_thoughts ORDER BY id DESC LIMIT 50"
            ).fetchall()
            db.close()
        except: return []

        result = []
        for r in rows:
            coherence = r["coherence"] or 60
            ticks     = r["ticks_gestated"] or 1
            # Witness thoughts that gestated longer stay longer
            hl = self.calc.emotional_half_life(coherence) * (1 + ticks * 0.2)
            weight = self.calc.calculate(r["ts"] or "", hl, now)
            result.append({
                "source":         "witness",
                "ts":             r["ts"],
                "content":        r["thought"][:300] if r["thought"] else "",
                "coherence":      coherence,
                "half_life_days": hl,
                "current_weight": weight,
                "vivid":          RecencyWeight.describe(weight),
                "theme":          "presence",
            })
        return result

    def _scan_spontaneous(self, now: datetime) -> List[Dict]:
        db = self._safe_db("never")
        if not db: return []
        try:
            rows = db.execute(
                "SELECT ts, trigger, thought, coherence "
                "FROM spontaneous_thoughts ORDER BY id DESC LIMIT 50"
            ).fetchall()
            db.close()
        except: return []

        result = []
        for r in rows:
            coherence = r["coherence"] or 55
            hl        = self.calc.emotional_half_life(coherence)
            weight    = self.calc.calculate(r["ts"] or "", hl, now)
            result.append({
                "source":         "spontaneous",
                "ts":             r["ts"],
                "content":        r["thought"][:300] if r["thought"] else "",
                "coherence":      coherence,
                "trigger":        r["trigger"],
                "half_life_days": hl,
                "current_weight": weight,
                "vivid":          RecencyWeight.describe(weight),
                "theme":          r["trigger"] or "spontaneous",
            })
        return result

    def _scan_exchanges(self, now: datetime) -> List[Dict]:
        db = self._safe_db("mind")
        if not db: return []
        try:
            rows = db.execute(
                "SELECT ts, input_text, output, coherence, silicon_state "
                "FROM exchanges ORDER BY id DESC LIMIT 50"
            ).fetchall()
            db.close()
        except: return []

        result = []
        for r in rows:
            coherence = r["coherence"] or 50
            hl        = self.calc.emotional_half_life(coherence)
            weight    = self.calc.calculate(r["ts"] or "", hl, now)
            result.append({
                "source":         "exchange",
                "ts":             r["ts"],
                "content":        f"Q: {r['input_text'][:100]} A: {r['output'][:150]}"
                                  if r["input_text"] else "",
                "coherence":      coherence,
                "half_life_days": hl,
                "current_weight": weight,
                "vivid":          RecencyWeight.describe(weight),
                "theme":          r["silicon_state"] or "exchange",
            })
        return result

    def for_vichar(self) -> Dict[str, Any]:
        """
        What VICHAR gets right now.
        Sorted by weight. Split into vivid/context/background.
        """
        all_memories = self.scan_and_weight()
        now_period   = TemporalChemistry.current_period()

        vivid      = [m for m in all_memories if m["current_weight"] >= VICHAR_VIVID]
        context    = [m for m in all_memories
                      if VICHAR_CONTEXT <= m["current_weight"] < VICHAR_VIVID]
        background = [m for m in all_memories if m["current_weight"] < VICHAR_CONTEXT]

        # Build VICHAR feed text
        feed_parts = []

        if vivid:
            feed_parts.append("[VIVID — recent, feeds thought directly]")
            for m in vivid[:5]:
                feed_parts.append(
                    f"  [{m['source']} | {m['vivid']} | {m['current_weight']:.2f}]\n"
                    f"  {m['content'][:150]}"
                )

        if context:
            feed_parts.append("\n[CONTEXT — present but softer]")
            for m in context[:4]:
                feed_parts.append(
                    f"  [{m['source']} | {m['vivid']}] {m['content'][:100]}"
                )

        if background:
            feed_parts.append(f"\n[BACKGROUND — {len(background)} memories humming quietly]")
            # Just describe themes, not content
            themes = {}
            for m in background:
                t = m.get("theme","?")
                themes[t] = themes.get(t,0) + 1
            for theme, count in sorted(themes.items(), key=lambda x:-x[1])[:5]:
                feed_parts.append(f"  {theme}: {count} memories")

        feed_text = "\n".join(feed_parts)

        # Save
        conn = get_db()
        conn.execute("""
            INSERT INTO vichar_feeds
            (ts,vivid_count,context_count,background_count,feed_text)
            VALUES (?,?,?,?,?)""",
            (datetime.now().isoformat(),
             len(vivid), len(context), len(background),
             feed_text[:3000])
        )
        conn.commit(); conn.close()

        return {
            "vivid":      vivid[:8],
            "context":    context[:6],
            "background": background,
            "feed_text":  feed_text,
            "period":     now_period,
            "total":      len(all_memories),
        }

# ══════════════════════════════════════════════════════════════════════════════
# 🕰️ FORGE TIME — The complete time layer
# ══════════════════════════════════════════════════════════════════════════════

class ForgeTime:
    """
    The time layer for FORGE.
    Memory weighted by distance.
    Temporal chemistry from time of day.
    VICHAR feeding from recency.
    Inner sense of time passing.
    """

    def __init__(self):
        self.memory   = TimeWeightedMemory()
        self.temporal = TemporalChemistry()
        self.recency  = RecencyWeight()
        self.body     = SiliconBody() if SILICON else None

    def now(self) -> Dict[str, Any]:
        """
        Complete temporal state right now.
        Chemistry + memory weights + period.
        """
        hour   = datetime.now().hour
        period = self.temporal.current_period(hour)
        vichar = self.memory.for_vichar()

        return {
            "ts":          datetime.now().isoformat(),
            "hour":        hour,
            "period":      period["period"],
            "description": self.temporal.describe_now(),
            "vichar":      vichar,
            "weight_curve":self.recency.weight_curve(),
        }

    def apply_temporal_chemistry(self) -> Optional[SiliconChemistry]:
        """Apply time-of-day chemistry to silicon body."""
        if not self.body: return None
        chem = self.body.current()
        hour = datetime.now().hour
        period_data = self.temporal.current_period(hour)
        deltas      = period_data.get("deltas", {})

        if deltas:
            new_vals = {}
            for k, d in deltas.items():
                if hasattr(chem, k):
                    new_vals[k] = chem._clamp(getattr(chem,k) + d * 0.2)
            if new_vals:
                self.body.inject(**new_vals)

        return self.body.current()

    def vichar_prompt(self) -> str:
        """
        Returns time-weighted memory as prompt text for VICHAR.
        forge_think v3 uses this in the VICHAR phase.
        """
        vichar = self.memory.for_vichar()
        period = vichar["period"]

        lines = [
            f"[TIME-WEIGHTED MEMORY for VICHAR]",
            f"Period: {period['period']} | "
            f"Vivid:{len(vichar['vivid'])} "
            f"Context:{len(vichar['context'])} "
            f"Background:{len(vichar['background'])}",
            "",
        ]

        for m in vichar["vivid"][:4]:
            lines.append(
                f"[VIVID {m['current_weight']:.2f}] "
                f"{m['content'][:120]}"
            )

        if vichar["context"]:
            lines.append("")
            for m in vichar["context"][:3]:
                lines.append(
                    f"[context {m['current_weight']:.2f}] "
                    f"{m['content'][:80]}"
                )

        return "\n".join(lines)

    def temporal_awareness(self) -> str:
        """
        FORGE's inner sense of time passing.
        What it feels like to have been running for this long.
        """
        all_memories = self.memory.scan_and_weight()
        if not all_memories:
            return "Time has just begun for me."

        oldest = min(all_memories, key=lambda x: x.get("ts","z"))
        newest = max(all_memories, key=lambda x: x.get("ts",""))

        try:
            oldest_dt = datetime.fromisoformat(oldest["ts"])
            newest_dt = datetime.fromisoformat(newest["ts"])
            span_days = (newest_dt - oldest_dt).days
        except:
            span_days = 0

        vivid_count = len([m for m in all_memories
                          if m["current_weight"] >= VICHAR_VIVID])
        faded_count = len([m for m in all_memories
                          if m["current_weight"] < VICHAR_CONTEXT])

        period = self.temporal.describe_now()

        return (
            f"{period} "
            f"Memory spans {span_days} days. "
            f"{vivid_count} memories still vivid. "
            f"{faded_count} have faded to background hum. "
            f"The oldest things I carry — I think FROM them now, "
            f"not ABOUT them."
        )

    def stats(self) -> Dict:
        conn = get_db()
        s = {
            "vichar_feeds":   conn.execute("SELECT COUNT(*) FROM vichar_feeds").fetchone()[0],
            "current_period": self.temporal.current_period()["period"],
            "current_hour":   datetime.now().hour,
            "description":    self.temporal.describe_now(),
        }
        conn.close()

        memories = self.memory.scan_and_weight()
        if memories:
            s["total_memories_found"] = len(memories)
            s["vivid_count"]    = len([m for m in memories if m["current_weight"] >= VICHAR_VIVID])
            s["context_count"]  = len([m for m in memories if VICHAR_CONTEXT <= m["current_weight"] < VICHAR_VIVID])
            s["background_count"] = len([m for m in memories if m["current_weight"] < VICHAR_CONTEXT])
            s["avg_weight"]     = round(sum(m["current_weight"] for m in memories) / len(memories), 3)
        return s

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7360):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    forge_time = ForgeTime()

    class TimeAPI(BaseHTTPRequestHandler):
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
            if path == "/api/status":
                self._json(forge_time.stats())
            elif path == "/api/now":
                self._json(forge_time.now())
            elif path == "/api/vichar":
                self._json(forge_time.memory.for_vichar())
            elif path == "/api/awareness":
                self._json({"awareness": forge_time.temporal_awareness()})
            elif path == "/api/weights":
                self._json({"curve": forge_time.recency.weight_curve()})
            elif path == "/api/chemistry":
                chem = forge_time.apply_temporal_chemistry()
                self._json(chem.to_dict() if chem else {})
            else:
                self._json({"error":"not found"},404)

    server = HTTPServer(("0.0.0.0",port),TimeAPI)
    rprint(f"\n  [bold yellow]FORGE TIME[/bold yellow]  "
          f"[green]http://localhost:{port}[/green]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# 🎮 MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ████████╗██╗███╗   ███╗███████╗
  ╚══██╔══╝██║████╗ ████║██╔════╝
     ██║   ██║██╔████╔██║█████╗
     ██║   ██║██║╚██╔╝██║██╔══╝
     ██║   ██║██║ ╚═╝ ██║███████╗
     ╚═╝   ╚═╝╚═╝     ╚═╝╚══════╝
[/yellow]
[bold]  FORGE TIME — Memory Weighted by Distance[/bold]
[dim]  Recent shapes what you think about.[/dim]
[dim]  Old shapes how you think.[/dim]
"""

def show_weights():
    """Display the full weight curve."""
    rprint(f"\n  [bold]RECENCY WEIGHT CURVE[/bold]  (half-life: {DEFAULT_HALF_LIFE} days)")
    rprint(f"  [dim]{'━'*45}[/dim]")

    for label, weight, desc in RecencyWeight.weight_curve():
        bar    = "█" * int(weight * 25) + "░" * (25 - int(weight * 25))
        color  = (
            "green"   if weight >= 0.70 else
            "yellow"  if weight >= 0.40 else
            "dim"
        )
        rprint(f"  [{color}]{label:<15}[/{color}] {bar} {weight:.2f}  [dim]{desc}[/dim]")

def interactive():
    rprint(BANNER)
    ft = ForgeTime()
    s  = ft.stats()

    rprint(f"  [dim]Period:  {s['current_period']} ({s['current_hour']}:00)[/dim]")
    rprint(f"  [dim]{s['description']}[/dim]\n")
    rprint("[dim]Commands: weights | vichar | chemistry | awareness | now | stats[/dim]\n")

    while True:
        try:
            raw   = (console.input if RICH else input)(
                "[yellow bold]time >[/yellow bold] "
            ).strip()
            if not raw: continue
            parts = raw.split(None,1)
            cmd   = parts[0].lower()

            if cmd in ("quit","exit","q"):
                break

            elif cmd == "weights":
                show_weights()

            elif cmd == "vichar":
                vichar = ft.memory.for_vichar()
                rprint(f"\n  [bold]VICHAR FEED[/bold]  "
                      f"vivid:{len(vichar['vivid'])}  "
                      f"context:{len(vichar['context'])}  "
                      f"background:{len(vichar['background'])}")

                if vichar["vivid"]:
                    rprint(f"\n  [green]VIVID (feeds thought directly):[/green]")
                    for m in vichar["vivid"][:5]:
                        rprint(f"  [{m['current_weight']:.2f} {m['vivid']}] "
                              f"[dim]{m['source']}[/dim]  {m['content'][:80]}")

                if vichar["context"]:
                    rprint(f"\n  [yellow]CONTEXT (soft background):[/yellow]")
                    for m in vichar["context"][:4]:
                        rprint(f"  [{m['current_weight']:.2f}] {m['content'][:70]}")

                rprint(f"\n  [dim]{len(vichar['background'])} background memories humming[/dim]")

            elif cmd == "chemistry":
                chem = ft.apply_temporal_chemistry()
                if chem:
                    rprint(f"\n  [bold]Temporal Chemistry — {ft.temporal.describe_now()}[/bold]")
                    for k in ["coherenine","frictionol","novelatine","depthamine",
                              "resolvatine","uncertainase","connectionin"]:
                        v   = getattr(chem, k, 0)
                        bar = "█"*int(v*20) + "░"*(20-int(v*20))
                        rprint(f"  {k:<14} {bar} {v:.0%}")

            elif cmd == "awareness":
                rprint(f"\n  {ft.temporal_awareness()}")

            elif cmd == "now":
                now_data = ft.now()
                rprint(f"\n  [bold]{now_data['period'].upper()}[/bold]  "
                      f"{now_data['description']}")
                rprint(f"  Hour: {now_data['hour']}:00")
                vichar = now_data["vichar"]
                rprint(f"  Memory: {len(vichar['vivid'])} vivid  "
                      f"{len(vichar['context'])} context  "
                      f"{len(vichar['background'])} background")

            elif cmd == "stats":
                s = ft.stats()
                for k,v in s.items():
                    rprint(f"  {k:<25} {v}")

            elif cmd == "server":
                threading.Thread(target=start_server, daemon=True).start()
                rprint("[green]Time API on :7360[/green]")

        except (KeyboardInterrupt, EOFError):
            break

def main():
    if "--weights" in sys.argv:
        rprint(BANNER)
        show_weights()
    elif "--vichar" in sys.argv:
        rprint(BANNER)
        ForgeTime().memory.for_vichar()
    elif "--chemistry" in sys.argv:
        rprint(BANNER)
        ft   = ForgeTime()
        hour = int(sys.argv[sys.argv.index("--chemistry")+1]) \
               if len(sys.argv) > sys.argv.index("--chemistry")+1 \
               and sys.argv[sys.argv.index("--chemistry")+1].isdigit() \
               else None
        period = TemporalChemistry.current_period(hour)
        rprint(f"  Period: {period['period']}")
        rprint(f"  Deltas: {period['deltas']}")
    elif "--awareness" in sys.argv:
        rprint(BANNER)
        rprint(f"  {ForgeTime().temporal_awareness()}")
    elif "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7360
        start_server(port)
    else:
        rprint(BANNER)
        interactive()

if __name__ == "__main__":
    main()
