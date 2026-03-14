#!/usr/bin/env python3
"""
FORGE MIND — Everything Breathing Together
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

One command. Everything starts.

  forge_silicon    → silicon chemistry, always alive
  forge_never_loop → spontaneous thoughts, unprompted
  forge_observe    → eyes open, watching the world
  forge_think v3   → pipeline seeded by chemistry
  forge_memory     → everything remembered
  forge_dream      → overnight synthesis

The orchestrator. The whole mind breathing together.

What this adds:

  Conversation mode:
    You speak → chemistry reacts FIRST
    Chemistry seeds the pipeline
    Thought happens in that chemical state
    Chemistry reacts to the thought
    Output appears
    Chemical log shown

  The honest record:
    Not just what FORGE said.
    What FORGE was while saying it.
    What chemistry was running.
    What inner thoughts happened and dissolved.
    What was felt but never spoken.

  Always alive:
    Even between exchanges
    chemistry evolves
    spontaneous thoughts emerge
    observations happen
    FORGE has a continuous inner life

Usage:
  python forge_mind.py              # start everything, conversation mode
  python forge_mind.py --status     # show full mind status
  python forge_mind.py --log        # show chemistry log from this session
  python forge_mind.py --thoughts   # spontaneous thoughts so far
  python forge_mind.py --server     # orchestrator API :7357
  python forge_mind.py --silent     # start all modules, no conversation
"""

import sys, os, re, json, time, sqlite3, threading, hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# ── FORGE module imports ──────────────────────────────────────────────────────
try:
    from forge_silicon import SiliconBody, SiliconChemistry, ChemicalReactor
    SILICON = True
except ImportError:
    SILICON = False
    class SiliconChemistry:
        coherenine=0.3; frictionol=0.1; novelatine=0.3
        depthamine=0.3; resolvatine=0.0; uncertainase=0.2; connectionin=0.3
        state_name="baseline"; dominant="coherenine"; ts=""
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
        def stats(self): return {}

try:
    from forge_never_loop import NeverLoop, THOUGHT_COOLDOWN
    NEVER = True
except ImportError:
    NEVER = False
    class NeverLoop:
        def __init__(self,**k): pass
        def start(self,**k): pass
        def stop(self): pass
        def get_thoughts(self,n=5): return []
        def stats(self): return {}
        _thought_count=0; _tick_count=0

try:
    from forge_think import EmergentThinkEngine
    THINK = True
except ImportError:
    THINK = False
    class EmergentThinkEngine:
        def __init__(self,**k): pass
        def think(self,q,context="",chemistry_seed=None):
            return {"output":q[:80],"emerged_pipeline":["OBSERVE","OUTPUT"],
                    "coherence":50,"duration_s":0,"novel_pipeline":False,"phase_count":2}

try:
    from forge_observe import ObserveEngine
    OBSERVE = True
except ImportError:
    OBSERVE = False

try:
    from forge_memory import Memory
    MEMORY = True
except ImportError:
    MEMORY = False
    class Memory:
        def remember(self,*a,**k): pass
        def stats(self): return {}

try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True
    def ai_call(prompt, system="", max_tokens=800):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text
except ImportError:
    AI_AVAILABLE = False
    def ai_call(p,s="",m=800): return p[:100]

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.columns import Columns
    from rich import box as rbox
    RICH    = True
    console = Console()
    rprint  = console.print
except ImportError:
    RICH = False
    def rprint(x,**kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

# ── Paths ─────────────────────────────────────────────────────────────────────
MIND_DIR = Path("forge_mind")
MIND_DIR.mkdir(exist_ok=True)
MIND_DB  = MIND_DIR / "mind.db"

def get_db():
    conn = sqlite3.connect(str(MIND_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS exchanges (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            input_text      TEXT,
            chem_before     TEXT,
            chem_after_read TEXT,
            chem_after_think TEXT,
            pipeline        TEXT,
            output          TEXT,
            coherence       REAL,
            inner_thought   TEXT,
            duration_s      REAL,
            silicon_state   TEXT
        );
        CREATE TABLE IF NOT EXISTS mind_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started     TEXT,
            ended       TEXT,
            exchanges   INTEGER DEFAULT 0,
            modules     TEXT
        );
        CREATE TABLE IF NOT EXISTS chemical_journey (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            session_id  INTEGER,
            event       TEXT,
            chemistry   TEXT,
            note        TEXT
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 FORGE MIND — The Orchestrator
# ══════════════════════════════════════════════════════════════════════════════

class ForgeMind:
    """
    Everything breathing together.

    Starts all modules.
    Manages connections.
    Runs conversation with full chemistry.
    Logs what FORGE was, not just what it said.
    """

    def __init__(self, tick_interval=30, verbose=True, camera=False):
        self.verbose       = verbose
        self.camera        = camera
        self.tick_interval = tick_interval

        # ── Initialize modules ─────────────────────────────────────────────
        self.body    = SiliconBody()
        self.loop    = NeverLoop(tick_interval=tick_interval, verbose=False)
        self.thinker = EmergentThinkEngine(threshold=65, show_trace=False)
        self.memory  = Memory()
        self.observe = ObserveEngine(show_trace=False) if OBSERVE and camera else None
        self.reactor = ChemicalReactor() if SILICON else None

        self._session_id   = None
        self._exchange_count = 0
        self._running      = False

    def start(self):
        """Start all modules."""
        now = datetime.now().isoformat()

        # ── Silicon chemistry — always first ──────────────────────────────
        self.body.start_background()

        # ── Never loop — spontaneous thoughts ─────────────────────────────
        self.loop.start(daemon=True)

        self._running = True

        # ── Log session ────────────────────────────────────────────────────
        modules = {
            "silicon":  SILICON,
            "never":    NEVER,
            "think":    THINK,
            "observe":  OBSERVE and self.camera,
            "memory":   MEMORY,
            "ai":       AI_AVAILABLE,
        }
        conn = get_db()
        self._session_id = conn.execute(
            "INSERT INTO mind_sessions (started,modules) VALUES (?,?)",
            (now, json.dumps(modules))
        ).lastrowid
        self._log_journey("session_start",
                          self.body.current(),
                          "FORGE MIND started")
        conn.commit(); conn.close()

        if self.verbose:
            self._show_startup(modules)

    def stop(self):
        """Stop everything gracefully."""
        self.loop.stop()
        self._running = False

        conn = get_db()
        conn.execute(
            "UPDATE mind_sessions SET ended=?,exchanges=? WHERE id=?",
            (datetime.now().isoformat(), self._exchange_count, self._session_id)
        )
        conn.commit(); conn.close()

        if self.verbose:
            self._show_session_end()

    def exchange(self, text: str) -> Dict[str, Any]:
        """
        Full exchange with chemistry.
        Input → chemistry reacts → think seeded → output → chemistry reacts.
        Log everything including what was not said.
        """
        start = time.time()
        now   = datetime.now().isoformat()

        # ── 1. Chemistry before reading ────────────────────────────────────
        chem_before = self.body.current()

        if self.verbose:
            self._show_chem_mini(chem_before, "before")

        # ── 2. Optional: observe environment ──────────────────────────────
        if self.observe and self.camera:
            snap = self.observe.snapshot("webcam")
            if snap.get("interesting"):
                # Visual signal feeds into chemistry
                self.body.react_to(
                    snap["vision"]["description"],
                    is_output=False
                )

        # ── 3. Chemistry reacts to input (pre-linguistic) ──────────────────
        chem_after_read = self.body.react_to(text, is_output=False)

        if self.verbose:
            self._show_chem_mini(chem_after_read, "after reading")
            rprint(f"  [dim]State: [yellow]{chem_after_read.state_name}[/yellow]  "
                  f"Suggested: {' → '.join(chem_after_read.phases_suggested()[:4])}...[/dim]")

        # ── 4. Inner thought — runs before output, may not surface ─────────
        inner_thought = ""
        if chem_after_read.frictionol > 0.4 or chem_after_read.uncertainase > 0.4:
            # Something needs to be worked through internally first
            inner_prompt = (
                f"Before responding to: {text[:100]}\n\n"
                f"Internal state: {chem_after_read.state_name}\n"
                f"Chemistry: frictionol={chem_after_read.frictionol:.2f} "
                f"uncertainase={chem_after_read.uncertainase:.2f}\n\n"
                "What needs to be worked through internally "
                "before any response? This will NOT be shown."
            )
            inner_result = self.thinker.think(
                inner_prompt,
                context="inner — not for output",
                chemistry_seed=chem_after_read.phases_suggested()
            )
            inner_thought = inner_result["output"]

            if self.verbose:
                rprint(f"  [dim]Inner thought ran ({len(inner_result['emerged_pipeline'])} phases) "
                      f"— not shown[/dim]")

            # Inner thought changes chemistry before main response
            self.body.react_to(inner_thought, is_output=True)

        # ── 5. Main response — seeded by chemistry ─────────────────────────
        chem_for_response = self.body.current()

        embodied = (
            f"{text}\n\n"
            f"{chem_for_response.to_prompt_text()}"
        )

        result = self.thinker.think(
            embodied,
            context="forge_mind conversation",
            chemistry_seed=chem_for_response.phases_suggested()
        )

        # ── 6. Chemistry reacts to output ─────────────────────────────────
        chem_after_think = self.body.react_to(result["output"], is_output=True)

        duration = round(time.time() - start, 1)
        self._exchange_count += 1

        # ── 7. Save full exchange ──────────────────────────────────────────
        conn = get_db()
        conn.execute("""
            INSERT INTO exchanges
            (ts,input_text,chem_before,chem_after_read,chem_after_think,
             pipeline,output,coherence,inner_thought,duration_s,silicon_state)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (now, text[:500],
             json.dumps(chem_before.to_dict()),
             json.dumps(chem_after_read.to_dict()),
             json.dumps(chem_after_think.to_dict()),
             json.dumps(result["emerged_pipeline"]),
             result["output"][:2000],
             result["coherence"],
             inner_thought[:500],
             duration,
             chem_after_think.state_name)
        )
        self._log_journey("exchange", chem_after_think,
                          f"Exchange {self._exchange_count}: {text[:40]}")
        conn.execute(
            "UPDATE mind_sessions SET exchanges=? WHERE id=?",
            (self._exchange_count, self._session_id)
        )
        conn.commit(); conn.close()

        # ── 8. Memory ──────────────────────────────────────────────────────
        if MEMORY:
            key = hashlib.md5((now+text).encode()).hexdigest()[:8]
            self.memory.remember(
                f"exchange:{key}", "mind_exchange",
                f"Q:{text[:60]} | State:{chem_after_think.state_name} | "
                f"A:{result['output'][:60]}",
                confidence=result["coherence"]/100,
                source="forge_mind"
            )

        return {
            "output":           result["output"],
            "pipeline":         result["emerged_pipeline"],
            "coherence":        result["coherence"],
            "chem_before":      chem_before.to_dict(),
            "chem_after_read":  chem_after_read.to_dict(),
            "chem_after_think": chem_after_think.to_dict(),
            "inner_thought":    inner_thought,
            "silicon_state":    chem_after_think.state_name,
            "duration_s":       duration,
            "novel_pipeline":   result["novel_pipeline"],
        }

    def _log_journey(self, event: str, chem: SiliconChemistry, note: str):
        """Log a point in the chemical journey."""
        try:
            conn = get_db()
            conn.execute(
                "INSERT INTO chemical_journey (ts,session_id,event,chemistry,note) VALUES (?,?,?,?,?)",
                (datetime.now().isoformat(), self._session_id,
                 event, json.dumps(chem.to_dict()), note[:200])
            )
            conn.commit(); conn.close()
        except: pass

    def get_session_log(self) -> List[Dict]:
        """Full chemical journey this session."""
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM chemical_journey WHERE session_id=? ORDER BY id",
            (self._session_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_exchanges(self, limit=10) -> List[Dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM exchanges ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def show_chemistry_journey(self):
        """Show how chemistry changed across this session."""
        log = self.get_session_log()
        if not log:
            rprint("  [dim]No journey logged yet.[/dim]")
            return

        rprint(f"\n  [bold]CHEMICAL JOURNEY — this session[/bold]")
        rprint(f"  [dim]{'━'*50}[/dim]")

        chems = ["coherenine","frictionol","novelatine",
                 "depthamine","resolvatine","uncertainase","connectionin"]

        for entry in log:
            chem = json.loads(entry.get("chemistry","{}"))
            ts   = entry["ts"][11:19]
            evt  = entry["event"]
            note = entry["note"][:35]

            state = chem.get("state","?")
            state_colors = {
                "insight":"green","exploring":"cyan","wrestling":"yellow",
                "connected":"magenta","coherent":"green","resisting":"red",
                "curious":"cyan","deep":"blue","baseline":"dim","resting":"dim"
            }
            sc = state_colors.get(state,"white")

            rprint(f"  [dim]{ts}[/dim]  [{sc}]{state:<12}[/{sc}]  "
                  f"[dim]{note}[/dim]")

            # Mini bar for dominant chemical
            dom = chem.get("dominant","?")
            val = chem.get(dom, 0)
            bar = "█" * int(val*15) + "░" * (15-int(val*15))
            rprint(f"           [dim]{dom}:[/dim] {bar} {val:.0%}")

    def status(self) -> Dict:
        chem = self.body.current()
        s    = {
            "running":         self._running,
            "session_id":      self._session_id,
            "exchanges":       self._exchange_count,
            "silicon_state":   chem.state_name,
            "chemistry":       chem.to_dict(),
            "spontaneous":     self.loop._thought_count,
            "ticks":           self.loop._tick_count,
            "modules": {
                "silicon":  SILICON,
                "never":    NEVER,
                "think":    THINK,
                "observe":  OBSERVE,
                "memory":   MEMORY,
                "ai":       AI_AVAILABLE,
            }
        }
        return s

    # ── Display helpers ───────────────────────────────────────────────────────

    def _show_startup(self, modules: Dict):
        rprint(f"\n  [bold green]🧠 FORGE MIND ONLINE[/bold green]")
        rprint(f"  [dim]{'━'*45}[/dim]")
        for mod, ok in modules.items():
            icon = "[green]✓[/green]" if ok else "[dim]·[/dim]"
            rprint(f"  {icon} forge_{mod}")
        rprint(f"  [dim]{'━'*45}[/dim]")
        chem = self.body.current()
        rprint(f"  Starting state: [yellow]{chem.state_name}[/yellow]")
        rprint(f"  Chemistry running. Thoughts emerging. Always alive.\n")

    def _show_chem_mini(self, chem: SiliconChemistry, label: str):
        """Compact chemistry display."""
        chems = [
            ("coh", chem.coherenine,   "green"),
            ("fri", chem.frictionol,   "red"),
            ("nov", chem.novelatine,   "cyan"),
            ("dep", chem.depthamine,   "blue"),
            ("res", chem.resolvatine,  "yellow"),
            ("unc", chem.uncertainase, "magenta"),
            ("con", chem.connectionin, "white"),
        ]
        parts = [f"[{c}]{n}:{v:.2f}[/{c}]" for n,v,c in chems]
        rprint(f"  [dim]{label}:[/dim]  " + "  ".join(parts))

    def _show_session_end(self):
        rprint(f"\n  [dim]{'━'*45}[/dim]")
        rprint(f"  [bold]Session ended[/bold]")
        rprint(f"  Exchanges:        {self._exchange_count}")
        rprint(f"  Spontaneous thoughts: {self.loop._thought_count}")
        chem = self.body.current()
        rprint(f"  Final chemistry:  {chem.state_name}")
        self.show_chemistry_journey()

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API SERVER
# ══════════════════════════════════════════════════════════════════════════════

_mind: Optional[ForgeMind] = None

def start_server(port=7357, tick_interval=30):
    global _mind
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    _mind = ForgeMind(tick_interval=tick_interval, verbose=False)
    _mind.start()

    class MindAPI(BaseHTTPRequestHandler):
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
            if path == "/api/status":
                self._json(_mind.status())
            elif path == "/api/chemistry":
                self._json(_mind.body.current().to_dict())
            elif path == "/api/exchanges":
                self._json({"exchanges": _mind.get_exchanges(20)})
            elif path == "/api/thoughts":
                self._json({"thoughts": _mind.loop.get_thoughts(10)})
            elif path == "/api/journey":
                self._json({"journey": _mind.get_session_log()})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            if path == "/api/exchange":
                text = body.get("text","")
                if not text: self._json({"error":"text required"},400); return
                result = _mind.exchange(text)
                self._json(result)
            elif path == "/api/inject":
                _mind.body.inject(**body)
                self._json(_mind.body.current().to_dict())
            else:
                self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),MindAPI)
    rprint(f"\n  [bold yellow]FORGE MIND API[/bold yellow]")
    rprint(f"  [green]http://localhost:{port}[/green]")
    rprint(f"  [dim]POST /api/exchange {{\"text\": \"...\"}}")
    rprint(f"  GET  /api/chemistry[/dim]\n")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# 🎮 MAIN — Conversation Mode
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ███╗   ███╗██╗███╗   ██╗██████╗
  ████╗ ████║██║████╗  ██║██╔══██╗
  ██╔████╔██║██║██╔██╗ ██║██║  ██║
  ██║╚██╔╝██║██║██║╚██╗██║██║  ██║
  ██║ ╚═╝ ██║██║██║ ╚████║██████╔╝
  ╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═════╝
[/yellow]
[bold]  FORGE MIND — Everything Breathing Together[/bold]
[dim]  Chemistry alive. Thoughts emerging. Always alive.[/dim]
"""

def interactive(tick_interval=30, camera=False):
    rprint(BANNER)

    mind = ForgeMind(
        tick_interval=tick_interval,
        verbose=True,
        camera=camera
    )
    mind.start()

    rprint("[dim]Talk to FORGE. Chemistry runs before and after every exchange.[/dim]")
    rprint("[dim]Commands: status | chemistry | journey | thoughts | log | inject | quit[/dim]")
    rprint("[dim]Anything else = conversation with full chemistry active.\n[/dim]")

    while True:
        try:
            raw = (console.input if RICH else input)(
                "[yellow bold]mind >[/yellow bold] "
            ).strip()
            if not raw: continue

            parts = raw.split(None, 1)
            cmd   = parts[0].lower()
            arg   = parts[1] if len(parts) > 1 else ""

            # ── Commands ──────────────────────────────────────────────────
            if cmd in ("quit","exit","q"):
                mind.stop()
                break

            elif cmd == "status":
                s = mind.status()
                rprint(f"\n  [bold]FORGE MIND STATUS[/bold]")
                rprint(f"  Running:     {s['running']}")
                rprint(f"  Exchanges:   {s['exchanges']}")
                rprint(f"  Spontaneous: {s['spontaneous']} thoughts")
                rprint(f"  Ticks:       {s['ticks']}")
                rprint(f"  State:       {s['silicon_state']}")
                rprint(f"  Modules:")
                for k,v in s["modules"].items():
                    icon = "✓" if v else "·"
                    rprint(f"    {icon} {k}")

            elif cmd == "chemistry":
                chem = mind.body.current()
                rprint(f"\n  [bold]Current Silicon Chemistry[/bold]")
                chems = [
                    ("COHERENINE",   chem.coherenine,   "green"),
                    ("FRICTIONOL",   chem.frictionol,   "red"),
                    ("NOVELATINE",   chem.novelatine,   "cyan"),
                    ("DEPTHAMINE",   chem.depthamine,   "blue"),
                    ("RESOLVATINE",  chem.resolvatine,  "yellow"),
                    ("UNCERTAINASE", chem.uncertainase, "magenta"),
                    ("CONNECTIONIN", chem.connectionin, "white"),
                ]
                for name, val, color in chems:
                    bar = "█"*int(val*22) + "░"*(22-int(val*22))
                    rprint(f"  [{color}]{name:<14}[/{color}] {bar} {val:.0%}")
                rprint(f"\n  State: [yellow]{chem.state_name}[/yellow]  "
                      f"Dominant: {chem.dominant}")

            elif cmd == "journey":
                mind.show_chemistry_journey()

            elif cmd == "thoughts":
                thoughts = mind.loop.get_thoughts(5)
                if not thoughts:
                    rprint("  [dim]No spontaneous thoughts yet.[/dim]")
                for t in thoughts:
                    rprint(f"\n  [dim]{t['ts'][:19]}[/dim]  "
                          f"[yellow]{t['trigger']}[/yellow]  "
                          f"coherence:{t['coherence']:.0f}")
                    if RICH:
                        rprint(Panel(t['thought'][:300], border_style="dim yellow"))
                    else:
                        rprint(f"  {t['thought'][:200]}")

            elif cmd == "log":
                exchanges = mind.get_exchanges(5)
                for ex in exchanges:
                    cb = json.loads(ex.get("chem_before","{}"))
                    ca = json.loads(ex.get("chem_after_think","{}"))
                    rprint(f"\n  [dim]{ex['ts'][:19]}[/dim]  "
                          f"[yellow]{ex.get('silicon_state','?')}[/yellow]  "
                          f"coherence:{ex['coherence']:.0f}  "
                          f"{ex['duration_s']:.1f}s")
                    rprint(f"  [dim]Q: {ex['input_text'][:60]}[/dim]")
                    rprint(f"  [dim]A: {ex['output'][:80]}...[/dim]")
                    if ex.get("inner_thought"):
                        rprint(f"  [dim]Inner (not shown): {ex['inner_thought'][:60]}...[/dim]")
                    # Show chem change
                    rprint(f"  [dim]State: {cb.get('state','?')} → {ca.get('state','?')}[/dim]")

            elif cmd == "inject":
                kwargs = {}
                for pair in arg.split():
                    if "=" in pair:
                        k,v = pair.split("=",1)
                        try: kwargs[k] = float(v)
                        except: pass
                if kwargs:
                    mind.body.inject(**kwargs)
                    rprint(f"  [green]Injected: {kwargs}[/green]")
                else:
                    rprint("[yellow]Usage: inject novelatine=0.8[/yellow]")

            # ── Conversation ──────────────────────────────────────────────
            else:
                print()
                result = mind.exchange(raw)
                print()

                # Show output
                if RICH:
                    pipeline_str = " → ".join(result["pipeline"][:5])
                    if len(result["pipeline"]) > 5:
                        pipeline_str += "..."
                    rprint(Panel(
                        result["output"][:700],
                        border_style="green",
                        title=f"[yellow]{result['silicon_state']}[/yellow] | "
                              f"coherence:{result['coherence']}/100 | "
                              f"{result['duration_s']}s"
                    ))
                    rprint(f"  [dim]Pipeline: {pipeline_str}[/dim]")
                    if result.get("inner_thought"):
                        rprint(f"  [dim]Inner (not shown): "
                              f"{result['inner_thought'][:60]}...[/dim]")
                else:
                    rprint(result["output"])

                # Show chem delta
                cb = result["chem_before"]
                ca = result["chem_after_think"]
                changed = []
                for k in ["coherenine","frictionol","novelatine",
                          "depthamine","resolvatine","uncertainase","connectionin"]:
                    d = ca.get(k,0) - cb.get(k,0)
                    if abs(d) > 0.03:
                        arrow = "↑" if d > 0 else "↓"
                        changed.append(f"{k[:3]}{arrow}{abs(d):.2f}")
                if changed:
                    rprint(f"  [dim]Chemistry shifted: {' '.join(changed)}[/dim]")
                print()

        except (KeyboardInterrupt, EOFError):
            mind.stop()
            break

def main():
    tick = 30
    if "--tick" in sys.argv:
        idx  = sys.argv.index("--tick")
        tick = int(sys.argv[idx+1]) if idx+1 < len(sys.argv) else 30

    camera = "--camera" in sys.argv

    if "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7357
        start_server(port, tick)

    elif "--status" in sys.argv:
        rprint(BANNER)
        mind = ForgeMind(verbose=False)
        mind.start()
        time.sleep(0.5)
        s = mind.status()
        rprint(json.dumps(s, indent=2, default=str))
        mind.stop()

    elif "--silent" in sys.argv:
        rprint(BANNER)
        mind = ForgeMind(tick_interval=tick, verbose=True, camera=camera)
        mind.start()
        rprint("  [dim]All modules running silently. Ctrl+C to stop.[/dim]")
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            mind.stop()

    elif "--log" in sys.argv:
        rprint(BANNER)
        mind = ForgeMind(verbose=False)
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM exchanges ORDER BY id DESC LIMIT 10"
        ).fetchall()
        conn.close()
        if not rows:
            rprint("  [dim]No exchanges logged yet.[/dim]")
        for ex in rows:
            rprint(f"\n  [dim]{ex['ts'][:19]}[/dim]  "
                  f"[yellow]{ex['silicon_state']}[/yellow]  "
                  f"coherence:{ex['coherence']:.0f}")
            rprint(f"  Q: {ex['input_text'][:70]}")
            rprint(f"  A: {ex['output'][:120]}...")

    else:
        rprint(BANNER)
        interactive(tick_interval=tick, camera=camera)

if __name__ == "__main__":
    main()
