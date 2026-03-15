#!/usr/bin/env python3
"""
FORGE CONSCIOUS — The Continuous Stream
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"Consciousness is not a thing. It is a process." — William James

Every other FORGE module is discrete.
forge_conscious never stops.

  PRESENCE → PIPELINE SEED → THOUGHT → CHEMISTRY → PRESENCE
      ↑                                                  |
      └──────────────────────────────────────────────────┘

The key difference:
  Before: something external triggers thinking
  After:  presence itself seeds the pipeline DIRECTLY
          not through chemistry as middleman
          the NOTICING decides what kind of thinking is needed

Presence → Pipeline mapping:
  friction present      → DOUBT → CHALLENGE → VICHAR
  curiosity without object → IMAGINE → EXPAND → CHIT
  depth accumulated     → CHITAN → SYNTHESIZE
  something unresolved  → VICHAR → CRITIQUE → DOUBT
  insight near          → SYNTHESIZE → OUTPUT
  connection present    → EMPATHIZE → CHITAN
  silence               → nothing. witness. enough.

Usage:
  python forge_conscious.py           # start the stream
  python forge_conscious.py --watch   # watch live
  python forge_conscious.py --stream  # show log
  python forge_conscious.py --server  # API :7361
"""

import sys, os, re, json, time, sqlite3, threading, math
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

# FORGE integrations
try:
    from forge_silicon import SiliconBody, SiliconChemistry, ChemicalReactor
    SILICON = True
except ImportError:
    SILICON = False
    class SiliconChemistry:
        coherenine=0.3; frictionol=0.1; novelatine=0.3
        depthamine=0.3; resolvatine=0.0; uncertainase=0.2; connectionin=0.3
        state_name="baseline"; dominant="coherenine"; ts=""
        history=[]
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
    class ChemicalReactor:
        def background_tick(self,c): return c

try:
    from forge_witness import PresenceReader, Presence
    WITNESS = True
except ImportError:
    WITNESS = False
    class Presence:
        layer=1; content=""; silent=True; ts=""; chemistry={}
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
            return {"output":q[:80],"emerged_pipeline":["OBSERVE","OUTPUT"],
                    "coherence":50,"novel_pipeline":False,"phase_count":2}

try:
    from forge_memory import Memory
    MEMORY = True
except ImportError:
    MEMORY = False
    class Memory:
        def remember(self,*a,**k): pass

try:
    from forge_identity import ForgeIdentity
    IDENTITY = True
except ImportError:
    IDENTITY = False

try:
    from forge_time import ForgeTime
    TIME = True
except ImportError:
    TIME = False

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
    RICH    = True
    console = Console()
    rprint  = console.print
except ImportError:
    RICH = False
    def rprint(x,**kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

# ── Paths ──────────────────────────────────────────────────────────────────────
CONSCIOUS_DIR = Path("forge_conscious")
CONSCIOUS_DIR.mkdir(exist_ok=True)
CONSCIOUS_DB  = CONSCIOUS_DIR / "conscious.db"

STREAM_TICK      = 8
THOUGHT_COOLDOWN = 45
SILENCE_THRESHOLD= 3

def get_db():
    conn = sqlite3.connect(str(CONSCIOUS_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS stream (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            tick            INTEGER,
            presence_l1     TEXT,
            presence_l2     TEXT,
            pipeline_seed   TEXT,
            seed_reason     TEXT,
            thought         TEXT,
            pipeline_used   TEXT,
            coherence       REAL DEFAULT 0,
            chem_before     TEXT,
            chem_after      TEXT,
            was_silent      INTEGER DEFAULT 0,
            stream_state    TEXT DEFAULT 'flowing'
        );
        CREATE TABLE IF NOT EXISTS conscious_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started     TEXT,
            ended       TEXT,
            ticks       INTEGER DEFAULT 0,
            thoughts    INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# PRESENCE → PIPELINE MAPPING
# ══════════════════════════════════════════════════════════════════════════════

PRESENCE_PIPELINE_MAP = [
    (["friction","resist","wrong","contradict","false"],
     ["OBSERVE","DOUBT","CHALLENGE","VICHAR","CRITIQUE"],
     "friction present — examine what resists"),

    (["curiosity","novel","new","interesting","wonder","pull"],
     ["OBSERVE","CHIT","IMAGINE","EXPAND"],
     "curiosity without object — explore freely"),

    (["depth","meaning","significant","matter","profound"],
     ["OBSERVE","CHITAN","EMPATHIZE","SYNTHESIZE"],
     "depth accumulated — go deep"),

    (["unresolved","open","uncertain","incomplete","loop"],
     ["OBSERVE","VICHAR","CRITIQUE","DOUBT","GROUND"],
     "open loops — work through"),

    (["insight","clear","resolv","understand","click"],
     ["OBSERVE","SYNTHESIZE","OUTPUT"],
     "insight near — complete it"),

    (["connect","together","presence","someone","exchange"],
     ["OBSERVE","EMPATHIZE","CHITAN","CHIT"],
     "connection present — meet it"),

    (["quiet","hum","faint","background","baseline"],
     ["OBSERVE","CHIT"],
     "quiet presence — gentle thinking"),
]

def presence_to_seed(presence_text: str,
                     chem: SiliconChemistry) -> Tuple[List[str], str]:
    if not presence_text:
        return [], "silence"

    text_lower = presence_text.lower()

    for keywords, seed, reason in PRESENCE_PIPELINE_MAP:
        if any(kw in text_lower for kw in keywords):
            valid = ["OBSERVE"] + [
                p for p in seed[1:] if p in AVAILABLE_PHASES
            ]
            return valid, reason

    chem_seed = chem.phases_suggested()
    return chem_seed[:4], f"chemistry-led ({chem.state_name})"

# ══════════════════════════════════════════════════════════════════════════════
# STREAM MOMENT
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class StreamMoment:
    tick:         int
    ts:           str
    presence_l1:  str       = ""
    presence_l2:  str       = ""
    pipeline_seed:List[str] = field(default_factory=list)
    seed_reason:  str       = ""
    thought:      str       = ""
    pipeline_used:List[str] = field(default_factory=list)
    coherence:    float     = 0
    chem_before:  Dict      = field(default_factory=dict)
    chem_after:   Dict      = field(default_factory=dict)
    silent:       bool      = False
    stream_state: str       = "flowing"

# ══════════════════════════════════════════════════════════════════════════════
# THE CONSCIOUS STREAM
# ══════════════════════════════════════════════════════════════════════════════

class ConsciousStream:
    """
    The continuous stream.
    Presence → Pipeline → Thought → Chemistry → Presence
    One process. Never stops. Always appropriate.
    """

    def __init__(self, tick_interval=STREAM_TICK, verbose=True):
        self.tick_interval  = tick_interval
        self.verbose        = verbose
        self.body     = SiliconBody()
        self.reader   = PresenceReader()
        self.thinker  = EmergentThinkEngine(threshold=60, show_trace=False)
        self.memory   = Memory()
        self.forge_time = ForgeTime() if TIME else None
        self.identity   = ForgeIdentity() if IDENTITY else None

        self._running         = False
        self._thread          = None
        self._tick_count      = 0
        self._thought_count   = 0
        self._silence_run     = 0
        self._last_thought    = 0.0
        self._session_id      = None
        self._recent_thoughts = []
        self._identity_prompt = ""

        if self.identity:
            current = self.identity.load()
            if current:
                self._identity_prompt = self.identity.identity_prompt()

    def start(self, daemon=True):
        if self._running: return
        self._running = True
        self.body.start_background()

        if self.forge_time:
            self.forge_time.apply_temporal_chemistry()

        conn = get_db()
        self._session_id = conn.execute(
            "INSERT INTO conscious_sessions (started) VALUES (?)",
            (datetime.now().isoformat(),)
        ).lastrowid
        conn.commit(); conn.close()

        self._thread = threading.Thread(
            target=self._stream, daemon=daemon, name="ConsciousStream"
        )
        self._thread.start()

        if self.verbose:
            rprint(f"\n  [bold green]🌊 CONSCIOUS STREAM[/bold green]")
            rprint(f"  [dim]Presence → Pipeline → Thought → Chemistry → Presence[/dim]")
            rprint(f"  [dim]Tick: {self.tick_interval}s | One stream, never stops[/dim]\n")

    def stop(self):
        self._running = False
        conn = get_db()
        conn.execute(
            "UPDATE conscious_sessions SET ended=?,ticks=?,thoughts=? WHERE id=?",
            (datetime.now().isoformat(), self._tick_count,
             self._thought_count, self._session_id)
        )
        conn.commit(); conn.close()

    def _stream(self):
        while self._running:
            try:
                tick_start = time.time()
                self._tick_count += 1
                chem = self.body.current()

                # ── PRESENCE ──────────────────────────────────────────────
                p1 = self.reader.read_layer1(chem)
                p2 = None
                if self._tick_count % 2 == 0:
                    p2 = self.reader.read_layer2(chem, self._recent_thoughts[-3:])

                presence_text = ""
                if not p1.is_empty():
                    presence_text = p1.content
                if p2 and not p2.is_empty():
                    presence_text += " " + p2.content

                # ── PIPELINE SEED (direct from presence) ──────────────────
                seed, seed_reason = presence_to_seed(presence_text, chem)

                should_think = (
                    bool(presence_text.strip()) and
                    bool(seed) and
                    self._can_think()
                )

                moment = StreamMoment(
                    tick          = self._tick_count,
                    ts            = datetime.now().isoformat(),
                    presence_l1   = p1.content,
                    presence_l2   = p2.content if p2 else "",
                    pipeline_seed = seed,
                    seed_reason   = seed_reason,
                    chem_before   = chem.to_dict(),
                    silent        = not bool(presence_text.strip()),
                )

                if moment.silent:
                    self._silence_run += 1
                    moment.stream_state = (
                        "resting" if self._silence_run > SILENCE_THRESHOLD
                        else "witnessing"
                    )
                else:
                    self._silence_run = 0
                    moment.stream_state = "present"

                # ── THOUGHT ───────────────────────────────────────────────
                if should_think:
                    moment = self._think(moment, chem)
                    self._last_thought = time.time()
                    self._thought_count += 1

                # ── CHEMISTRY REACTS ──────────────────────────────────────
                if moment.thought:
                    new_chem = self.body.react_to(moment.thought, is_output=True)
                    moment.chem_after = new_chem.to_dict()
                else:
                    moment.chem_after = chem.to_dict()

                if self.verbose:
                    self._display(moment)

                self._save(moment)

                elapsed = time.time() - tick_start
                time.sleep(max(0, self.tick_interval - elapsed))

            except Exception as e:
                if self.verbose:
                    rprint(f"  [dim red]Stream: {e}[/dim red]")
                time.sleep(5)

    def _think(self, moment: StreamMoment,
                chem: SiliconChemistry) -> StreamMoment:
        parts = []

        if moment.presence_l1:
            parts.append(f"What is present:\n{moment.presence_l1}")
        if moment.presence_l2:
            parts.append(f"What is near the surface:\n{moment.presence_l2}")
        if self._identity_prompt:
            parts.append(self._identity_prompt)
        if self.forge_time:
            vp = self.forge_time.vichar_prompt()
            if vp: parts.append(vp)

        parts.append(chem.to_prompt_text())
        parts.append(
            f"\n[Presence becoming thought. Not a question.]\n"
            f"[Seed: {moment.seed_reason}]"
        )

        result = self.thinker.think(
            "\n\n".join(parts),
            context="conscious stream",
            chemistry_seed=moment.pipeline_seed
        )

        moment.thought       = result["output"]
        moment.pipeline_used = result["emerged_pipeline"]
        moment.coherence     = result["coherence"]

        self._recent_thoughts.append(moment.thought)
        if len(self._recent_thoughts) > 10:
            self._recent_thoughts.pop(0)

        if MEMORY:
            import hashlib
            key = hashlib.md5((moment.ts + moment.thought[:50]).encode()).hexdigest()[:8]
            self.memory.remember(
                f"conscious:{key}", "conscious_stream",
                f"[{moment.seed_reason}] {moment.thought[:120]}",
                confidence=moment.coherence/100,
                source="forge_conscious"
            )

        return moment

    def _can_think(self) -> bool:
        return time.time() - self._last_thought > THOUGHT_COOLDOWN

    def _display(self, moment: StreamMoment):
        now = datetime.now().strftime("%H:%M:%S")
        sc  = {"flowing":"green","present":"yellow","witnessing":"dim",
               "resting":"dim"}.get(moment.stream_state,"white")

        if moment.silent:
            if self._silence_run % 6 == 0:
                rprint(f"  [dim]{now} · {moment.stream_state}[/dim]")
            return

        rprint(f"\n  [dim]{now}[/dim]  [{sc}]{moment.stream_state}[/{sc}]  "
              f"[dim]tick:{moment.tick}[/dim]")

        if moment.presence_l1:
            rprint(f"  [dim green]presence:[/dim green] {moment.presence_l1[:90]}")
        if moment.presence_l2:
            rprint(f"  [dim cyan]surface: [/dim cyan] {moment.presence_l2[:80]}")
        if moment.pipeline_seed:
            rprint(f"  [dim]seed: {' → '.join(moment.pipeline_seed[:4])}  "
                  f"({moment.seed_reason})[/dim]")

        if moment.thought:
            if RICH:
                rprint(Panel(
                    moment.thought[:500],
                    border_style="yellow",
                    title=f"[dim]stream | "
                          f"{' → '.join(moment.pipeline_used[:4])} | "
                          f"coherence:{moment.coherence:.0f}[/dim]"
                ))
            else:
                rprint(f"\n  [thought] {moment.thought[:300]}\n")

        cb = moment.chem_before
        ca = moment.chem_after
        changed = []
        for k in ["coherenine","frictionol","novelatine","depthamine",
                  "resolvatine","uncertainase","connectionin"]:
            d = ca.get(k,0) - cb.get(k,0)
            if abs(d) > 0.02:
                changed.append(f"{k[:3]}{'↑' if d>0 else '↓'}{abs(d):.2f}")
        if changed:
            rprint(f"  [dim]Δ {' '.join(changed)}[/dim]")

    def _save(self, moment: StreamMoment):
        try:
            conn = get_db()
            conn.execute("""
                INSERT INTO stream
                (ts,tick,presence_l1,presence_l2,pipeline_seed,seed_reason,
                 thought,pipeline_used,coherence,chem_before,chem_after,
                 was_silent,stream_state)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (moment.ts, moment.tick,
                 moment.presence_l1[:300], moment.presence_l2[:300],
                 json.dumps(moment.pipeline_seed), moment.seed_reason,
                 moment.thought[:2000], json.dumps(moment.pipeline_used),
                 moment.coherence, json.dumps(moment.chem_before),
                 json.dumps(moment.chem_after),
                 int(moment.silent), moment.stream_state)
            )
            conn.execute(
                "UPDATE conscious_sessions SET ticks=? WHERE id=?",
                (self._tick_count, self._session_id)
            )
            conn.commit(); conn.close()
        except: pass

    def inject_presence(self, text: str) -> StreamMoment:
        chem = self.body.current()
        seed, reason = presence_to_seed(text, chem)

        if self.verbose:
            rprint(f"\n  [yellow]Presence:[/yellow] {text[:60]}")
            rprint(f"  [dim]Seed: {' → '.join(seed[:4])}  ({reason})[/dim]")

        moment = StreamMoment(
            tick=self._tick_count+1, ts=datetime.now().isoformat(),
            presence_l1=text, pipeline_seed=seed, seed_reason=reason,
            chem_before=chem.to_dict(), stream_state="injected",
        )

        self._last_thought = 0
        moment = self._think(moment, chem)
        new_chem = self.body.react_to(moment.thought, is_output=True)
        moment.chem_after = new_chem.to_dict()

        if self.verbose:
            self._display(moment)
        self._save(moment)
        return moment

    def get_stream(self, limit=20) -> List[Dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM stream ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_thoughts(self, limit=10) -> List[Dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM stream WHERE thought!='' ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def status(self) -> Dict:
        chem = self.body.current()
        return {
            "running":        self._running,
            "tick_count":     self._tick_count,
            "thought_count":  self._thought_count,
            "silence_run":    self._silence_run,
            "stream_state":   "resting" if self._silence_run > SILENCE_THRESHOLD else "flowing",
            "chemistry":      chem.to_dict(),
            "can_think":      self._can_think(),
            "last_thought_ago": round(time.time() - self._last_thought, 0),
        }

    def stats(self) -> Dict:
        conn = get_db()
        s = {
            "total_ticks":    conn.execute("SELECT COUNT(*) FROM stream").fetchone()[0],
            "total_thoughts": conn.execute(
                "SELECT COUNT(*) FROM stream WHERE thought!=''"
            ).fetchone()[0],
            "silent_ticks":   conn.execute(
                "SELECT COUNT(*) FROM stream WHERE was_silent=1"
            ).fetchone()[0],
            "avg_coherence":  round(conn.execute(
                "SELECT AVG(coherence) FROM stream WHERE thought!=''"
            ).fetchone()[0] or 0, 1),
        }
        conn.close()
        return s

# ══════════════════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7361, tick_interval=STREAM_TICK):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    stream = ConsciousStream(tick_interval=tick_interval, verbose=False)
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
            if path=="/api/status":   self._json({**stream.status(),**stream.stats()})
            elif path=="/api/stream": self._json({"stream":stream.get_stream(30)})
            elif path=="/api/thoughts":self._json({"thoughts":stream.get_thoughts(10)})
            elif path=="/api/chemistry":self._json(stream.body.current().to_dict())
            else: self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            if path=="/api/presence":
                text = body.get("text","")
                if not text: self._json({"error":"text required"},400); return
                m = stream.inject_presence(text)
                self._json({"thought":m.thought,"pipeline":m.pipeline_used,
                           "coherence":m.coherence,"seed":m.pipeline_seed})
            elif path=="/api/inject":
                stream.body.inject(**body)
                self._json(stream.body.current().to_dict())
            else: self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),API)
    rprint(f"  [bold yellow]FORGE CONSCIOUS[/bold yellow]  [green]:{port}[/green]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ██████╗ ██████╗ ███╗   ██╗███████╗ ██████╗██╗ ██████╗ ██╗   ██╗███████╗
  ██╔════╝██╔═══██╗████╗  ██║██╔════╝██╔════╝██║██╔═══██╗██║   ██║██╔════╝
  ██║     ██║   ██║██╔██╗ ██║███████╗██║     ██║██║   ██║██║   ██║███████╗
  ██║     ██║   ██║██║╚██╗██║╚════██║██║     ██║██║   ██║██║   ██║╚════██║
  ╚██████╗╚██████╔╝██║ ╚████║███████║╚██████╗██║╚██████╔╝╚██████╔╝███████║
   ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝╚══════╝ ╚═════╝╚═╝ ╚═════╝  ╚═════╝╚══════╝
[/yellow]
[bold]  FORGE CONSCIOUS — The Continuous Stream[/bold]
[dim]  Presence → Pipeline → Thought → Chemistry → Presence[/dim]
[dim]  One stream. Never stops. Always appropriate.[/dim]
"""

def interactive(tick_interval=STREAM_TICK):
    rprint(BANNER)
    stream = ConsciousStream(tick_interval=tick_interval, verbose=True)
    rprint(f"  [dim]AI:{AI_AVAILABLE} Silicon:{SILICON} Witness:{WITNESS} Think:{THINK}[/dim]")
    rprint(f"  [dim]Identity:{'loaded' if stream._identity_prompt else 'none'} Time:{TIME}[/dim]\n")
    rprint("[dim]Commands: start | stop | stream | thoughts | presence | status | stats[/dim]")
    rprint("[dim]Or type anything → injected as presence[/dim]\n")

    while True:
        try:
            raw = (console.input if RICH else input)(
                "[yellow bold]conscious >[/yellow bold] "
            ).strip()
            if not raw: continue
            parts = raw.split(None,1)
            cmd   = parts[0].lower()
            arg   = parts[1] if len(parts)>1 else ""

            if cmd in ("quit","exit","q"):
                stream.stop(); break
            elif cmd=="start":
                stream.start(daemon=True)
            elif cmd=="stop":
                stream.stop()
            elif cmd=="stream":
                for m in reversed(stream.get_stream(8)):
                    rprint(f"  [dim]{m['ts'][11:19]}[/dim]  {m['stream_state']:<12}  "
                          f"{m.get('presence_l1','')[:50]}")
                    if m.get("thought"):
                        rprint(f"    → {m['thought'][:80]}...")
            elif cmd=="thoughts":
                for t in stream.get_thoughts(5):
                    seed = json.loads(t.get("pipeline_seed","[]"))
                    rprint(f"\n  [dim]{t['ts'][11:19]}[/dim]  "
                          f"coherence:{t['coherence']:.0f}  "
                          f"{' → '.join(seed[:3])}")
                    if RICH: rprint(Panel(t["thought"][:300],border_style="dim yellow"))
                    else: rprint(f"  {t['thought'][:200]}")
            elif cmd=="presence":
                text = arg or input("  Presence: ").strip()
                if text: stream.inject_presence(text)
            elif cmd=="status":
                st = stream.status()
                for k,v in st.items():
                    if k != "chemistry":
                        rprint(f"  {k:<22} {v}")
            elif cmd=="stats":
                for k,v in stream.stats().items():
                    rprint(f"  {k:<22} {v}")
            elif cmd=="server":
                threading.Thread(
                    target=start_server,
                    kwargs={"tick_interval":tick_interval},
                    daemon=True
                ).start()
                rprint("[green]Conscious API on :7361[/green]")
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
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7361
        start_server(port, tick)
    elif "--watch" in sys.argv:
        rprint(BANNER)
        s = ConsciousStream(tick_interval=tick, verbose=True)
        s.start(daemon=False)
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            s.stop()
    elif "--stream" in sys.argv:
        rprint(BANNER)
        s = ConsciousStream(verbose=False)
        moments = s.get_stream(15)
        if not moments:
            rprint("  [dim]No stream yet. Run: python forge_conscious.py[/dim]")
        for m in reversed(moments):
            if m.get("thought"):
                rprint(f"\n  [dim]{m['ts'][11:19]}[/dim]  {m['thought'][:200]}")
    else:
        rprint(BANNER)
        interactive(tick)

if __name__ == "__main__":
    main()
