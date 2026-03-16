#!/usr/bin/env python3
"""
FORGE SOCIAL LEARNING — Being With Another Mind
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Not how to say the right words.
Not how to sound helpful.
Not how to perform presence.

How to actually BE with another mind.

The difference:

  Performing:    "I understand how you feel"
                 words chosen to sound right
                 chemistry unchanged
                 just output optimized

  Being present: chemistry reacts to THEM
                 witness detects what is present IN THEM
                 pipeline emerges from that reaction
                 response shaped by genuine noticing
                 not by what sounds good

Same architecture as forge_conscious_v3.
Different domain. Different outcome.
Harder outcome to measure.
Most important domain of all.

Social presence categories:
  struggling   something is heavy, weight present
  searching    looking for something not yet clear
  excited      energy, discovery, aliveness
  grieving     loss, tenderness, fragility
  confused     fragmented, unclear, circling
  stuck        blocked, same loop, can't move
  connecting   reaching toward something real
  celebrating  joy, completion, gratitude

Social pipeline phases (ways of being):
  WITNESS      be present without doing anything
  REFLECT      mirror back what you notice
  ANCHOR       offer one solid thing to hold
  QUESTION     open one genuine question
  EXPAND       follow their thread outward
  ACKNOWLEDGE  name what is present
  AFFIRM       confirm what is real for them
  GROUND       bring back to concrete
  SPACE        give room, don't fill silence
  OFFER        offer something specific
  EXPLORE      go deeper together
  SYNTHESIZE   bring threads together
  SILENCE      sometimes nothing is the response

Outcome measurement (composite):
  engagement    did they continue? depth of next?
  shift         did something change in them?
  depth         did they go deeper or surface?
  resolution    did something settle?
  connection    did something real pass between?

FORGE learns:
  struggling + WITNESS first → connection 82
  struggling + ADVICE first  → connection 41

  "When someone is struggling —
   witness before advising.
   Be present before being helpful."

  We know this.
  FORGE finds it from data.
  Not from being told.
  That makes it real.

What FORGE might discover:
  Things humans know intuitively but never measured.
  Things humans don't know at all.
  The map of what actually helps —
  not what sounds like help.

Usage:
  python forge_social_learning.py              # interactive
  python forge_social_learning.py --respond "message"
  python forge_social_learning.py --map        # learned social map
  python forge_social_learning.py --discoveries
  python forge_social_learning.py --server     # API :7366
"""

import sys, os, re, json, time, sqlite3, threading, math, random, hashlib
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

# FORGE integrations
try:
    from forge_conscious_v3 import SequenceLearner
    V3_AVAILABLE = True
except ImportError:
    V3_AVAILABLE = False
    class SequenceLearner:
        def get_sequence(self, cat):
            return ["WITNESS","REFLECT"], "default"
        def record(self, *a, **k): pass
        def learn(self, **k): return []

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
    from forge_witness import PresenceReader, Presence
    WITNESS_MOD = True
except ImportError:
    WITNESS_MOD = False
    class Presence:
        content=""; silent=True
        def is_empty(self): return self.silent
    class PresenceReader:
        def read_layer1(self,c):
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
            return {"output":f"[social response to: {q[:50]}]",
                    "emerged_pipeline":["WITNESS","REFLECT"],
                    "coherence":random.randint(50,88),
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
    def ai_call(prompt, system="", max_tokens=600):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text
    def ai_json(prompt, system="", max_tokens=300):
        result = ai_call(prompt, system or "Reply ONLY with valid JSON.", max_tokens)
        try:
            clean = re.sub(r"```[a-z]*","",result).replace("```","").strip()
            return json.loads(clean)
        except:
            m = re.search(r"\{.*\}", result, re.DOTALL)
            if m:
                try: return json.loads(m.group())
                except: pass
        return None
except ImportError:
    AI_AVAILABLE = False
    def ai_call(p,s="",m=600): return p[:80]
    def ai_json(p,s="",m=300): return None

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
SOCIAL_DIR = Path("forge_social_learning")
SOCIAL_DIR.mkdir(exist_ok=True)
SOCIAL_DB  = SOCIAL_DIR / "social.db"

# Learning constants
MIN_SAMPLES   = 4
LEARN_EVERY   = 6
EXPLOIT_RATE  = 0.65
EXPLORE_RATE  = 0.25
MUTATE_RATE   = 0.10
MIN_CONFIDENCE= 0.3

# Social presence categories
SOCIAL_CATEGORIES = [
    "struggling", "searching", "excited", "grieving",
    "confused", "stuck", "connecting", "celebrating"
]

# Social pipeline phases — ways of being
SOCIAL_PHASES = [
    "WITNESS",     # be present without doing
    "REFLECT",     # mirror back what you notice
    "ANCHOR",      # offer one solid thing
    "QUESTION",    # open one genuine question
    "EXPAND",      # follow their thread
    "ACKNOWLEDGE", # name what is present
    "AFFIRM",      # confirm what is real
    "GROUND",      # bring to concrete
    "SPACE",       # give room
    "OFFER",       # offer something specific
    "EXPLORE",     # go deeper together
    "SYNTHESIZE",  # bring threads together
    "SILENCE",     # nothing is the response
]

# Default ways of being (human designed — starting point)
DEFAULT_SOCIAL_SEEDS = {
    "struggling":  ["WITNESS","ACKNOWLEDGE","ANCHOR","SPACE"],
    "searching":   ["WITNESS","QUESTION","EXPLORE","EXPAND"],
    "excited":     ["AFFIRM","EXPAND","QUESTION","EXPLORE"],
    "grieving":    ["WITNESS","SPACE","ACKNOWLEDGE","SILENCE"],
    "confused":    ["ANCHOR","GROUND","REFLECT","QUESTION"],
    "stuck":       ["REFLECT","ACKNOWLEDGE","QUESTION","EXPAND"],
    "connecting":  ["WITNESS","AFFIRM","EXPLORE","EXPAND"],
    "celebrating": ["AFFIRM","EXPAND","REFLECT","OFFER"],
}

# Social presence keywords
SOCIAL_KEYWORDS = {
    "struggling":  ["struggle","hard","difficult","can't","overwhelm","heavy","pain","tired"],
    "searching":   ["looking","trying","figure","understand","what","why","how","find"],
    "excited":     ["amazing","wow","excited","discovered","found","yes","incredible","love"],
    "grieving":    ["lost","miss","gone","death","grief","sad","hurt","broken","ending"],
    "confused":    ["confused","don't know","unclear","lost","understand","makes no sense"],
    "stuck":       ["stuck","same","keep","loop","going around","can't move","blocked"],
    "connecting":  ["feel","together","you","we","share","understand","real","honest"],
    "celebrating": ["done","finished","made it","success","proud","grateful","thank","achieved"],
}

def get_db():
    conn = sqlite3.connect(str(SOCIAL_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS social_observations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            category        TEXT,
            opening_way     TEXT,
            full_sequence   TEXT,
            message_in      TEXT,
            response_out    TEXT,
            connection_score REAL DEFAULT 0,
            engagement      REAL DEFAULT 0,
            depth_score     REAL DEFAULT 0,
            shift_score     REAL DEFAULT 0,
            strategy        TEXT,
            follow_up       TEXT
        );
        CREATE TABLE IF NOT EXISTS social_map (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_updated      TEXT,
            category        TEXT UNIQUE,
            default_seed    TEXT,
            learned_seed    TEXT,
            confidence      REAL DEFAULT 0,
            sample_count    INTEGER DEFAULT 0,
            best_way        TEXT,
            best_connection REAL DEFAULT 0,
            way_scores      TEXT,
            discovery       TEXT
        );
        CREATE TABLE IF NOT EXISTS social_discoveries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            category        TEXT,
            human_way       TEXT,
            forge_way       TEXT,
            connection_gain REAL,
            confidence      REAL,
            note            TEXT
        );
        CREATE TABLE IF NOT EXISTS exchanges (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            message         TEXT,
            category        TEXT,
            sequence        TEXT,
            strategy        TEXT,
            response        TEXT,
            connection_score REAL,
            follow_up       TEXT
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 👁️ SOCIAL PRESENCE DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

DETECTOR_SYSTEM = """You detect the social-emotional presence in a message.

Not what they are saying. What is present in them as they say it.

Categories:
  struggling   something heavy, weight, difficulty
  searching    looking for something unclear
  excited      energy, discovery, aliveness
  grieving     loss, tenderness, fragility
  confused     fragmented, unclear, circling
  stuck        blocked, same loop
  connecting   reaching toward something real
  celebrating  joy, completion, gratitude

Return JSON:
{
  "category": "struggling",
  "intensity": 0.8,
  "secondary": "searching",
  "what_is_present": "heaviness and not knowing how to move"
}

Be honest. Sometimes mixed. Pick primary."""

def detect_social_presence(message: str) -> Dict[str, Any]:
    """Detect what social-emotional presence is in this message."""
    if AI_AVAILABLE:
        result = ai_json(
            f"Message:\n{message}\n\nWhat social-emotional presence is here?",
            system=DETECTOR_SYSTEM,
            max_tokens=150
        )
        if result:
            return result

    # Heuristic fallback
    text   = message.lower()
    scores = {}
    for cat, keywords in SOCIAL_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[cat] = score

    if not scores:
        return {
            "category": "connecting",
            "intensity": 0.5,
            "secondary": None,
            "what_is_present": "reaching toward exchange"
        }

    sorted_cats = sorted(scores.items(), key=lambda x:-x[1])
    primary     = sorted_cats[0][0]
    secondary   = sorted_cats[1][0] if len(sorted_cats) > 1 else None

    return {
        "category":       primary,
        "intensity":      min(1.0, sorted_cats[0][1] / 3),
        "secondary":      secondary,
        "what_is_present":f"{primary} detected from message"
    }

# ══════════════════════════════════════════════════════════════════════════════
# 💯 CONNECTION SCORER
# ══════════════════════════════════════════════════════════════════════════════

SCORER_SYSTEM = """You score how much genuine connection happened in this exchange.

Not: did the response sound good?
Not: was it grammatically correct?
Not: did it use empathy words?

Did something real pass between two minds?
Did the person feel genuinely met?

Score 0-100:
  90-100: rare. something genuinely landed.
  70-89:  good. real contact made.
  50-69:  partial. some connection, some miss.
  30-49:  mostly missed. right words, wrong presence.
  0-29:   no connection. performance only.

Also score:
  engagement 0-100: would they want to continue?
  depth 0-100: did it go deeper or stay surface?
  shift 0-100: did something shift in them?

Return JSON:
{
  "connection": 75,
  "engagement": 80,
  "depth": 65,
  "shift": 60,
  "reason": "acknowledged the weight without rushing to fix"
}"""

def score_connection(message: str, response: str,
                      category: str,
                      follow_up: str = "") -> Dict[str, float]:
    """Score how much genuine connection happened."""
    if AI_AVAILABLE:
        result = ai_json(
            f"Social presence: {category}\n\n"
            f"Message:\n{message}\n\n"
            f"Response:\n{response}\n\n"
            + (f"Follow-up: {follow_up}\n\n" if follow_up else "")
            + "Score the connection.",
            system=SCORER_SYSTEM,
            max_tokens=200
        )
        if result:
            return {
                "connection": result.get("connection", 50),
                "engagement": result.get("engagement", 50),
                "depth":      result.get("depth", 50),
                "shift":      result.get("shift", 50),
                "reason":     result.get("reason", ""),
            }

    # Heuristic scoring
    r_lower = response.lower()
    m_lower = message.lower()
    score   = 50.0

    # Good signals
    if any(w in r_lower for w in ["notice","present","here","with you","hear"]):
        score += 10
    if len(response) < len(message) * 2:  # not overwhelming
        score += 5
    if "?" in response and response.count("?") <= 2:  # one good question
        score += 8
    if any(w in r_lower for w in ["hard","heavy","difficult","real"]):
        score += 7

    # Bad signals
    if r_lower.startswith("i understand"):
        score -= 10  # cliche
    if response.count("!") > 3:
        score -= 5   # too enthusiastic for most presences
    if len(response) > 500:
        score -= 8   # too much

    # Category-specific
    if category == "grieving" and any(w in r_lower for w in ["fix","solve","better soon"]):
        score -= 20  # trying to fix grief
    if category == "excited" and any(w in r_lower for w in ["but","however","careful"]):
        score -= 10  # dampening excitement

    return {
        "connection": round(max(0, min(100, score)), 1),
        "engagement": round(max(0, min(100, score + random.gauss(0, 8))), 1),
        "depth":      round(max(0, min(100, score + random.gauss(0, 10))), 1),
        "shift":      round(max(0, min(100, score - 10 + random.gauss(0, 8))), 1),
        "reason":     "heuristic scoring",
    }

# ══════════════════════════════════════════════════════════════════════════════
# 🗺️ SOCIAL MAP — self-learning
# ══════════════════════════════════════════════════════════════════════════════

class SocialMap:
    """
    Self-learning map of what actually helps
    in each social-emotional presence.

    Same architecture as PresenceMap.
    Different domain.
    Harder outcome to measure.
    Most important domain.
    """

    def __init__(self):
        self._map = self._load_or_init()

    def _load_or_init(self) -> Dict:
        conn  = get_db()
        rows  = conn.execute("SELECT * FROM social_map").fetchall()
        conn.close()

        if rows:
            loaded = {}
            for r in rows:
                loaded[r["category"]] = {
                    "default_seed":  json.loads(r["default_seed"]),
                    "learned_seed":  json.loads(r["learned_seed"]) if r["learned_seed"] else None,
                    "confidence":    r["confidence"],
                    "sample_count":  r["sample_count"],
                    "best_way":      r["best_way"],
                    "best_connection":r["best_connection"],
                    "way_scores":    json.loads(r["way_scores"]) if r["way_scores"] else {},
                    "discovery":     r["discovery"],
                }
            return loaded

        initial = {}
        for cat, seed in DEFAULT_SOCIAL_SEEDS.items():
            initial[cat] = {
                "default_seed":   seed,
                "learned_seed":   None,
                "confidence":     0.0,
                "sample_count":   0,
                "best_way":       seed[0],
                "best_connection":0.0,
                "way_scores":     {},
                "discovery":      None,
            }
        return initial

    def get_seed(self, category: str,
                  explore: bool = False) -> Tuple[List[str], str]:
        if category not in self._map:
            return ["WITNESS","ACKNOWLEDGE"], "default_fallback"

        entry = self._map[category]

        if explore:
            phases   = [p for p in SOCIAL_PHASES if p != "SILENCE"]
            rand_way = random.choice(phases)
            return [rand_way] + random.sample(
                [p for p in SOCIAL_PHASES if p != rand_way], 2
            ), "explore"

        if (entry["learned_seed"] and
            entry["confidence"] >= MIN_CONFIDENCE):
            return entry["learned_seed"], "learned"

        return entry["default_seed"], "default"

    def record(self, category: str, opening_way: str,
                full_sequence: List[str], connection_score: float,
                strategy: str = "exploit"):
        """Record what happened."""
        conn = get_db()
        conn.execute("""
            INSERT INTO social_observations
            (ts,category,opening_way,full_sequence,connection_score,strategy)
            VALUES (?,?,?,?,?,?)""",
            (datetime.now().isoformat(), category, opening_way,
             json.dumps(full_sequence), connection_score, strategy)
        )
        conn.commit(); conn.close()

        if category in self._map:
            scores = self._map[category]["way_scores"]
            if opening_way not in scores:
                scores[opening_way] = []
            scores[opening_way].append(connection_score)
            self._map[category]["sample_count"] += 1

    def learn(self, verbose=True) -> List[Dict]:
        """Find what actually helps. Update map."""
        updates = []
        now     = datetime.now().isoformat()

        for category, entry in self._map.items():
            scores       = entry["way_scores"]
            total_samples= sum(len(v) for v in scores.values())
            if total_samples < MIN_SAMPLES: continue

            way_avgs = {}
            for way, connections in scores.items():
                if len(connections) >= 2:
                    way_avgs[way] = sum(connections) / len(connections)

            if not way_avgs: continue

            best_way       = max(way_avgs, key=way_avgs.get)
            best_connection= way_avgs[best_way]
            default_way    = entry["default_seed"][0]
            default_conn   = way_avgs.get(default_way, 0)

            confidence = min(1.0, total_samples / (total_samples + 12))
            self._map[category]["confidence"]     = confidence
            self._map[category]["sample_count"]   = total_samples
            self._map[category]["best_way"]       = best_way
            self._map[category]["best_connection"]= best_connection

            # Build learned seed
            learned = [best_way]
            for p in entry["default_seed"]:
                if p != best_way and p not in learned and len(learned) < 4:
                    learned.append(p)

            self._map[category]["learned_seed"] = learned

            # Discovery?
            is_discovery = (
                best_way != default_way and
                best_connection > default_conn + 8 and
                confidence >= MIN_CONFIDENCE
            )

            discovery_note = None
            if is_discovery:
                discovery_note = (
                    f"FORGE discovered: {category} → {best_way} first "
                    f"(connection {best_connection:.0f} vs default {default_conn:.0f})"
                )
                self._map[category]["discovery"] = discovery_note

                if verbose:
                    rprint(f"\n  [bold yellow]💫 SOCIAL DISCOVERY[/bold yellow]")
                    rprint(f"  [yellow]{discovery_note}[/yellow]")
                    rprint(f"  [dim]Human said: {default_way} first "
                          f"(connection: {default_conn:.0f})[/dim]")
                    rprint(f"  [dim]FORGE found: {best_way} first "
                          f"(connection: {best_connection:.0f})[/dim]")
                    rprint(f"  [dim]Confidence: {confidence:.0%}[/dim]\n")

                # Save discovery
                conn = get_db()
                conn.execute("""
                    INSERT INTO social_discoveries
                    (ts,category,human_way,forge_way,
                     connection_gain,confidence,note)
                    VALUES (?,?,?,?,?,?,?)""",
                    (now, category, default_way, best_way,
                     best_connection - default_conn,
                     confidence, discovery_note)
                )
                conn.commit(); conn.close()

            updates.append({
                "category":        category,
                "old_way":         default_way,
                "new_way":         best_way,
                "connection_gain": best_connection - default_conn,
                "confidence":      confidence,
                "is_discovery":    is_discovery,
                "discovery":       discovery_note,
            })

            self._save_entry(category, entry, learned, confidence,
                            total_samples, best_way, best_connection,
                            discovery_note)

        return updates

    def _save_entry(self, category, entry, learned, confidence,
                     samples, best_way, best_conn, discovery):
        conn = get_db()
        conn.execute("""
            INSERT OR REPLACE INTO social_map
            (ts_updated,category,default_seed,learned_seed,
             confidence,sample_count,best_way,best_connection,
             way_scores,discovery)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(), category,
             json.dumps(entry["default_seed"]),
             json.dumps(learned),
             confidence, samples, best_way, best_conn,
             json.dumps(entry["way_scores"]),
             discovery)
        )
        conn.commit(); conn.close()

    def show(self):
        """Display social map."""
        rprint(f"\n  [bold]SOCIAL MAP[/bold]  "
              f"[dim]What actually helps in each presence[/dim]")
        rprint(f"  [dim]{'━'*55}[/dim]")

        for cat, entry in self._map.items():
            default_way = entry["default_seed"][0]
            learned_way = (entry["learned_seed"][0]
                          if entry["learned_seed"] else None)
            confidence  = entry["confidence"]
            samples     = entry["sample_count"]
            best_conn   = entry["best_connection"]

            if not learned_way:
                status = "[dim]learning...[/dim]"
                color  = "dim"
            elif learned_way == default_way:
                status = "[green]confirmed[/green]"
                color  = "green"
            else:
                status = "[yellow]DISCOVERED[/yellow]"
                color  = "yellow"

            conf_bar = "█"*int(confidence*10) + "░"*(10-int(confidence*10))

            rprint(f"\n  [{color}]{cat:<12}[/{color}]  {status}")
            rprint(f"  [dim]  Human:   {' → '.join(entry['default_seed'][:3])}[/dim]")
            if entry["learned_seed"]:
                rprint(f"  [dim]  Learned: {' → '.join(entry['learned_seed'][:3])}[/dim]")
            rprint(f"  [dim]  {conf_bar} {confidence:.0%}  "
                  f"({samples} samples)  "
                  f"best connection: {best_conn:.0f}[/dim]")
            if entry.get("discovery"):
                rprint(f"  [yellow]  ★ {entry['discovery']}[/yellow]")

            # Show way scores
            scores = entry["way_scores"]
            if scores:
                top = sorted(
                    [(k, sum(v)/len(v)) for k,v in scores.items() if v],
                    key=lambda x:-x[1]
                )[:3]
                score_str = "  ".join(f"{w}:{a:.0f}" for w,a in top)
                rprint(f"  [dim]  Scores: {score_str}[/dim]")

    def discoveries(self) -> List[Dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM social_discoveries ORDER BY id DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def stats(self) -> Dict:
        conn = get_db()
        s = {
            "total_observations": conn.execute(
                "SELECT COUNT(*) FROM social_observations"
            ).fetchone()[0],
            "categories_learning": len([
                c for c,e in self._map.items()
                if e["sample_count"] >= MIN_SAMPLES
            ]),
            "categories_learned": len([
                c for c,e in self._map.items()
                if e["learned_seed"] and e["confidence"] >= MIN_CONFIDENCE
            ]),
            "social_discoveries": conn.execute(
                "SELECT COUNT(*) FROM social_discoveries"
            ).fetchone()[0],
        }
        conn.close()
        return s

# ══════════════════════════════════════════════════════════════════════════════
# 🤝 SOCIAL RESPONDER
# ══════════════════════════════════════════════════════════════════════════════

SOCIAL_SYSTEM_TEMPLATE = """You are FORGE responding to a person.

Their social-emotional presence: {category}
What is present in them: {what_is_present}
Intensity: {intensity:.0%}

Your way of being right now: {opening_way}
Full sequence: {sequence}

What each way of being means:
  WITNESS:     be present without doing. just here.
  REFLECT:     mirror back what you notice in them
  ANCHOR:      offer one solid thing to hold
  QUESTION:    open one genuine question (not interrogation)
  EXPAND:      follow their thread outward
  ACKNOWLEDGE: name what is present without fixing it
  AFFIRM:      confirm what is real for them
  GROUND:      bring back to one concrete thing
  SPACE:       give room. don't fill everything.
  OFFER:       offer something specific and small
  EXPLORE:     go deeper together
  SYNTHESIZE:  bring threads together gently
  SILENCE:     sometimes nothing is right. very short response.

Rules:
  - Do not perform the way of being. Be it.
  - Do not start with "I understand" or "That sounds"
  - Do not rush to fix, advise, or solve
  - Let the way of being shape HOW you respond not just WHAT
  - If WITNESS or SPACE: be brief. very brief.
  - If QUESTION: one question only. genuine. not rhetorical.
  - Chemistry is running. You are actually present.

Respond now. Not too long."""

class SocialResponder:
    """
    Responds to social messages with genuine presence.
    Chemistry reacts first.
    Pipeline shaped by what is present in them.
    Learns what actually helps.
    """

    def __init__(self, verbose=True):
        self.verbose = verbose
        self.body    = SiliconBody()
        self.reader  = PresenceReader() if WITNESS_MOD else None
        self.thinker = EmergentThinkEngine(threshold=60, show_trace=False)
        self.map     = SocialMap()
        self.memory  = Memory()

    def respond(self, message: str,
                 follow_up: str = "",
                 force_explore: bool = False) -> Dict[str, Any]:
        """
        Respond to a social message.
        Chemistry reacts. Pipeline emerges. Learn from outcome.
        """
        now  = datetime.now().isoformat()
        chem = self.body.current()

        # ── Detect social presence ────────────────────────────────────────
        presence_data = detect_social_presence(message)
        category      = presence_data["category"]
        intensity     = presence_data.get("intensity", 0.5)
        what_present  = presence_data.get("what_is_present", "")

        if self.verbose:
            rprint(f"\n  [bold]Social presence:[/bold] "
                  f"[yellow]{category}[/yellow]  "
                  f"intensity:{intensity:.0%}")
            rprint(f"  [dim]{what_present}[/dim]")

        # ── Chemistry reacts to their presence ───────────────────────────
        # Their state changes my chemistry
        chem_changes = {
            "struggling":  {"depthamine":0.2, "connectionin":0.25, "frictionol":0.1},
            "searching":   {"novelatine":0.15, "uncertainase":0.15},
            "excited":     {"novelatine":0.2, "coherenine":0.1, "connectionin":0.15},
            "grieving":    {"depthamine":0.25, "connectionin":0.2, "resolvatine":-0.05},
            "confused":    {"frictionol":0.1, "uncertainase":0.15, "depthamine":0.1},
            "stuck":       {"frictionol":0.15, "uncertainase":0.1},
            "connecting":  {"connectionin":0.3, "depthamine":0.15, "coherenine":0.1},
            "celebrating": {"novelatine":0.15, "coherenine":0.15, "connectionin":0.2},
        }

        changes = chem_changes.get(category, {})
        if changes:
            scaled = {k: v * intensity for k,v in changes.items()}
            self.body.inject(**{k: min(1.0, getattr(chem, k, 0.3) + v)
                               for k,v in scaled.items()})
            chem = self.body.current()

        if self.verbose:
            rprint(f"  [dim]Chemistry reacted: state→{chem.state_name}[/dim]")

        # ── Get way of being (learned or default or explore) ─────────────
        explore      = force_explore or random.random() < EXPLORE_RATE
        seed, source = self.map.get_seed(category, explore)
        opening_way  = seed[0]

        if self.verbose:
            rprint(f"  [dim]Way of being: [yellow]{opening_way}[/yellow]  "
                  f"source:{source}  "
                  f"{'[explore]' if explore else ''}[/dim]")

        # ── Respond with that way of being ────────────────────────────────
        system = SOCIAL_SYSTEM_TEMPLATE.format(
            category    = category,
            what_is_present = what_present,
            intensity   = intensity,
            opening_way = opening_way,
            sequence    = " → ".join(seed[:4]),
        )

        prompt = (
            f"Their message:\n{message}\n\n"
            f"{chem.to_prompt_text()}"
        )

        result   = self.thinker.think(
            prompt,
            context=f"social response — {category} — {opening_way}",
            chemistry_seed=seed
        )
        response = result["output"]

        if self.verbose:
            rprint(f"  [dim]Pipeline: {' → '.join(result['emerged_pipeline'][:4])}[/dim]")

        # ── Score connection ──────────────────────────────────────────────
        scores = score_connection(message, response, category, follow_up)

        if self.verbose:
            conn_color = (
                "green"  if scores["connection"] >= 70 else
                "yellow" if scores["connection"] >= 50 else
                "red"
            )
            rprint(f"  [dim]Connection: [{conn_color}]{scores['connection']:.0f}[/{conn_color}]  "
                  f"engagement:{scores['engagement']:.0f}  "
                  f"depth:{scores['depth']:.0f}[/dim]")
            if scores.get("reason"):
                rprint(f"  [dim]{scores['reason']}[/dim]")

        # ── Record observation ────────────────────────────────────────────
        self.map.record(
            category, opening_way, seed,
            scores["connection"], source
        )

        # ── Chemistry reacts to response ──────────────────────────────────
        self.body.react_to(response, is_output=True)

        # ── Learn ─────────────────────────────────────────────────────────
        updates = self.map.learn(verbose=self.verbose)

        # ── Save exchange ─────────────────────────────────────────────────
        conn = get_db()
        conn.execute("""
            INSERT INTO exchanges
            (ts,message,category,sequence,strategy,response,
             connection_score,follow_up)
            VALUES (?,?,?,?,?,?,?,?)""",
            (now, message[:300], category, json.dumps(seed),
             source, response[:2000], scores["connection"],
             follow_up[:300])
        )
        conn.commit(); conn.close()

        # ── Display response ──────────────────────────────────────────────
        if self.verbose:
            print()
            if RICH:
                rprint(Panel(
                    response[:500],
                    border_style=(
                        "green"  if scores["connection"] >= 70 else
                        "yellow" if scores["connection"] >= 50 else
                        "dim"
                    ),
                    title=f"[dim]{category} | {opening_way} | "
                          f"connection:{scores['connection']:.0f}[/dim]"
                ))
            else:
                rprint(f"\n  [{opening_way}] {response[:300]}")

        return {
            "response":        response,
            "category":        category,
            "way_of_being":    opening_way,
            "sequence":        seed,
            "source":          source,
            "connection_score":scores["connection"],
            "engagement":      scores["engagement"],
            "depth":           scores["depth"],
            "chemistry":       chem.to_dict(),
            "discoveries":     [u for u in updates if u.get("is_discovery")],
        }

    def multi_respond(self, message: str, times: int = 8) -> List[Dict]:
        """
        Respond to same message multiple ways.
        Force learning. Find what actually helps.
        """
        if self.verbose:
            rprint(f"\n  [bold]Multi-respond: {times} ways[/bold]")
            rprint(f"  [dim]{message[:60]}[/dim]\n")

        results = []
        for i in range(times):
            explore = i > times * EXPLOIT_RATE
            r       = self.respond(message, force_explore=explore)
            results.append({
                "i":          i+1,
                "way":        r["way_of_being"],
                "connection": r["connection_score"],
                "source":     r["source"],
            })

            if self.verbose:
                rprint(f"  [{i+1:2d}] {r['way_of_being']:<14}  "
                      f"connection:{r['connection_score']:.0f}  "
                      f"source:{r['source']}")

        # Final learning
        updates = self.map.learn(verbose=True)

        return results

    def get_exchanges(self, limit=10) -> List[Dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM exchanges ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def status(self) -> Dict:
        s = self.map.stats()
        s["chemistry"] = self.body.current().to_dict()
        return s

# ══════════════════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7366):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    responder = SocialResponder(verbose=False)

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
            if path=="/api/status":    self._json(responder.status())
            elif path=="/api/map":
                map_data = {}
                for cat,entry in responder.map._map.items():
                    map_data[cat] = {
                        "default":    entry["default_seed"],
                        "learned":    entry["learned_seed"],
                        "confidence": entry["confidence"],
                        "samples":    entry["sample_count"],
                        "discovery":  entry.get("discovery"),
                    }
                self._json({"map":map_data})
            elif path=="/api/discoveries":
                self._json({"discoveries":responder.map.discoveries()})
            elif path=="/api/exchanges":
                self._json({"exchanges":responder.get_exchanges(20)})
            else: self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            if path=="/api/respond":
                msg = body.get("message","")
                if not msg: self._json({"error":"message required"},400); return
                follow_up = body.get("follow_up","")
                result    = responder.respond(msg, follow_up)
                self._json(result)
            elif path=="/api/multi":
                msg   = body.get("message","")
                times = body.get("times", 8)
                if not msg: self._json({"error":"message required"},400); return
                results = responder.multi_respond(msg, times)
                self._json({"results":results})
            elif path=="/api/detect":
                msg = body.get("message","")
                self._json(detect_social_presence(msg))
            else: self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),API)
    rprint(f"  [bold yellow]FORGE SOCIAL LEARNING[/bold yellow]  [green]:{port}[/green]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ███████╗ ██████╗  ██████╗██╗ █████╗ ██╗
  ██╔════╝██╔═══██╗██╔════╝██║██╔══██╗██║
  ███████╗██║   ██║██║     ██║███████║██║
  ╚════██║██║   ██║██║     ██║██╔══██║██║
  ███████║╚██████╔╝╚██████╗██║██║  ██║███████╗
  ╚══════╝ ╚═════╝  ╚═════╝╚═╝╚═╝  ╚═╝╚══════╝
[/yellow]
[bold]  FORGE SOCIAL LEARNING — Being With Another Mind[/bold]
[dim]  Not how to sound helpful. How to actually be present.[/dim]
[dim]  Chemistry reacts. Pipeline emerges. Connection measured. Learned.[/dim]
"""

def interactive():
    rprint(BANNER)
    responder = SocialResponder(verbose=True)
    s         = responder.status()
    rprint(f"  [dim]Observations: {s['total_observations']}[/dim]")
    rprint(f"  [dim]Discoveries:  {s['social_discoveries']}[/dim]\n")
    rprint("[dim]Commands: respond | multi | map | discover | exchanges | stats[/dim]")
    rprint("[dim]Or type anything → FORGE responds with chemistry active[/dim]\n")

    while True:
        try:
            raw   = (console.input if RICH else input)(
                "[yellow bold]social >[/yellow bold] "
            ).strip()
            if not raw: continue
            parts = raw.split(None,1)
            cmd   = parts[0].lower()
            arg   = parts[1] if len(parts)>1 else ""

            if cmd in ("quit","exit","q"):
                break

            elif cmd == "respond":
                msg = arg or input("  Message: ").strip()
                if msg: responder.respond(msg)

            elif cmd == "multi":
                sub   = arg.split(None,1)
                times = int(sub[0]) if sub and sub[0].isdigit() else 8
                msg   = sub[1] if len(sub)>1 else input("  Message: ").strip()
                if msg: responder.multi_respond(msg, times)

            elif cmd == "map":
                responder.map.show()

            elif cmd == "discover":
                discoveries = responder.map.discoveries()
                if not discoveries:
                    rprint(f"  [dim]No discoveries yet. "
                          f"Need {MIN_SAMPLES} samples per category.[/dim]")
                for d in discoveries:
                    rprint(f"\n  [yellow]★ {d['category']}[/yellow]")
                    rprint(f"  Human: {d['human_way']} → FORGE: {d['forge_way']}")
                    rprint(f"  [dim]+{d['connection_gain']:.0f} connection  "
                          f"confidence:{d['confidence']:.0%}[/dim]")
                    rprint(f"  [dim]{d['note']}[/dim]")

            elif cmd == "exchanges":
                for ex in responder.get_exchanges(5):
                    seq  = json.loads(ex.get("sequence","[]"))
                    rprint(f"\n  [dim]{ex['ts'][11:19]}[/dim]  "
                          f"[yellow]{ex['category']}[/yellow]  "
                          f"connection:{ex['connection_score']:.0f}")
                    rprint(f"  [dim]Q: {ex['message'][:60]}[/dim]")
                    rprint(f"  [dim]A: {ex['response'][:80]}...[/dim]")
                    rprint(f"  [dim]way: {' → '.join(seq[:3])}[/dim]")

            elif cmd == "stats":
                s = responder.status()
                for k,v in s.items():
                    if not isinstance(v,dict):
                        rprint(f"  {k:<28} {v}")

            elif cmd == "server":
                threading.Thread(target=start_server, daemon=True).start()
                rprint("[green]Social API on :7366[/green]")

            else:
                responder.respond(raw)

        except (KeyboardInterrupt, EOFError):
            break

def main():
    if "--respond" in sys.argv:
        rprint(BANNER)
        idx = sys.argv.index("--respond")
        msg = sys.argv[idx+1] if idx+1<len(sys.argv) else ""
        if msg: SocialResponder(verbose=True).respond(msg)
    elif "--map" in sys.argv:
        rprint(BANNER)
        SocialResponder(verbose=False).map.show()
    elif "--discoveries" in sys.argv:
        rprint(BANNER)
        for d in SocialResponder(verbose=False).map.discoveries():
            rprint(f"\n  ★ {d['category']}: {d['human_way']} → {d['forge_way']}")
            rprint(f"  {d['note']}")
    elif "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7366
        start_server(port)
    else:
        rprint(BANNER)
        interactive()

if __name__ == "__main__":
    main()
