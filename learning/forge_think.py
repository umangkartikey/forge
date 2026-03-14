#!/usr/bin/env python3
"""
FORGE THINK v3 — Emergent Pipeline Cognition
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

v1: Fixed pipeline     — always the same order
v2: Adaptive pipeline  — template + mid-thought changes  
v3: Emergent pipeline  — no template, no router
                         pipeline writes itself
                         one phase at a time
                         from the question itself

Each phase decides what comes next.
The pipeline is never planned.
It grows.

Inspired by: Observation → Chit → Chitan → Vichar → Character → Future
             (Arjun: The Warrior Prince)

And the observation that human thinking is not a fixed pipeline —
it is adaptive, modular, situational.
It can create thinking patterns that never existed before.

Phase Library (14):
  OBSERVE    CHIT      CHITAN    VICHAR
  CRITIQUE   CHALLENGE EMPATHIZE IMAGINE
  COMPRESS   DOUBT     EXPAND    GROUND
  SYNTHESIZE OUTPUT

Each phase returns:
  output     — what it thought
  next       — which phases should run next (its decision)
  confidence — how sure it is
  ready      — True = skip to output now

Guard rails:
  max 12 phases per thought
  no phase repeats (unless LOOP)
  60s wall clock timeout
  coherence check every 3 phases
  force output if coherence > 85 at any point

Usage:
  python forge_think.py                     # interactive
  python forge_think.py --think "question"  # think once, show trace
  python forge_think.py --server            # API :7351
"""

import sys, os, re, json, time, sqlite3, threading, hashlib
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

# Memory
try:
    from forge_memory import Memory
    MEMORY = True
except ImportError:
    MEMORY = False
    class Memory:
        def remember(self,*a,**k): pass
        def recall(self,e): return None
        def stats(self): return {}

# AI
try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True
    def ai_call(prompt, system="", max_tokens=800):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system, messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text
    def ai_json(prompt, system="", max_tokens=400):
        result = ai_call(prompt, system or "Reply ONLY with valid JSON. No markdown backticks.", max_tokens)
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
    def ai_call(p,s="",m=800): return p[:100]
    def ai_json(p,s="",m=400): return None

# Rich
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

# ── Paths ───────────────────────────────────────────────────────────────────────
THINK_DIR = Path("forge_think")
THINK_DIR.mkdir(exist_ok=True)
THINK_DB  = THINK_DIR / "think.db"

MAX_PHASES        = 12
COHERENCE_EVERY   = 3
FORCE_OUTPUT_AT   = 85
TIMEOUT_S         = 60
DEFAULT_THRESHOLD = 70

def get_db():
    conn = sqlite3.connect(str(THINK_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS thoughts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           TEXT,
            question     TEXT,
            emerged_pipeline TEXT,
            phase_count  INTEGER DEFAULT 0,
            coherence    REAL DEFAULT 0,
            output       TEXT,
            duration_s   REAL,
            early_exit   INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS phase_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            thought_id   INTEGER,
            position     INTEGER,
            phase_name   TEXT,
            output       TEXT,
            next_decided TEXT,
            confidence   REAL,
            ready        INTEGER DEFAULT 0,
            ts           TEXT
        );
        CREATE TABLE IF NOT EXISTS emergence_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           TEXT,
            question     TEXT,
            pipeline     TEXT,
            coherence    REAL,
            novel        INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 📦 PHASE RESULT — what every phase returns
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PhaseResult:
    phase_name: str
    output:     str
    next:       List[str]   # phases this phase wants to run next
    confidence: float = 0.7
    ready:      bool  = False  # True = I think we can output now
    loop_self:  bool  = False  # True = run me again

# ══════════════════════════════════════════════════════════════════════════════
# 🧩 BASE PHASE — each phase decides what comes next
# ══════════════════════════════════════════════════════════════════════════════

AVAILABLE_PHASES = [
    "OBSERVE","CHIT","CHITAN","VICHAR","CRITIQUE","CHALLENGE",
    "EMPATHIZE","IMAGINE","COMPRESS","DOUBT","EXPAND","GROUND",
    "SYNTHESIZE","OUTPUT"
]

PHASE_DESCRIPTIONS = {
    "OBSERVE":   "deep intake — what is this really asking?",
    "CHIT":      "raw awareness — what lands first, no filter",
    "CHITAN":    "reflection — honest inventory of what I know",
    "VICHAR":    "reasoning — follow the thread",
    "CRITIQUE":  "self-attack — where am I wrong?",
    "CHALLENGE": "break the frame — what if the question is wrong?",
    "EMPATHIZE": "human weight — what does this mean for real people?",
    "IMAGINE":   "creative leap — what if completely different?",
    "COMPRESS":  "urgency — what is the single essential thing?",
    "DOUBT":     "radical uncertainty — what if I know nothing?",
    "EXPAND":    "widen scope — what is the bigger picture?",
    "GROUND":    "make concrete — what does this mean in practice?",
    "SYNTHESIZE":"merge — what survived everything?",
    "OUTPUT":    "speak — only what is ready",
}

NEXT_DECIDER_SYSTEM = """You are a thinking phase in FORGE THINK v3.

You just completed your phase of reasoning.
Now you must decide: what should the thinking do next?

Available phases:
{available}

Rules:
- Pick 1-3 phases that would genuinely deepen this thinking
- Pick SYNTHESIZE if enough depth has been reached
- Pick OUTPUT only if the answer is fully ready right now
- Consider what is MISSING from the thinking so far
- Be honest — don't add phases just to seem thorough

Return JSON:
{{"next": ["PHASE1", "PHASE2"], "confidence": 0.75, "ready": false, "reason": "why these next"}}

If ready to output immediately:
{{"next": ["OUTPUT"], "confidence": 0.9, "ready": true, "reason": "thinking is complete"}}"""

class Phase:
    name:        str = "BASE"
    description: str = ""
    system:      str = ""

    def run(self, question: str, context: Dict[str, Any]) -> PhaseResult:
        if not AI_AVAILABLE:
            # Fallback — simple heuristic next phase selection
            next_phases = self._fallback_next(question, context)
            return PhaseResult(
                phase_name = self.name,
                output     = f"[{self.name}] {question[:80]}",
                next       = next_phases,
                confidence = 0.6,
                ready      = self.name == "SYNTHESIZE",
            )

        # Build prompt
        prior   = self._format_context(context)
        prompt  = f"Question: {question}\n\n{prior}\n\n{self.task}"
        output  = ai_call(prompt, system=self.system, max_tokens=self.max_tokens())

        # Decide next phases
        phases_run = context.get("phases_run", [])
        remaining  = [p for p in AVAILABLE_PHASES
                     if p not in phases_run and p != self.name]

        next_result = ai_json(
            f"Question: {question}\n\n"
            f"I just completed {self.name} phase.\n"
            f"My output: {output[:300]}\n\n"
            f"Phases already run: {phases_run}\n"
            f"Thinking depth so far: {len(phases_run)} phases\n\n"
            "What should come next?",
            system=NEXT_DECIDER_SYSTEM.format(
                available="\n".join(
                    f"  {p}: {PHASE_DESCRIPTIONS[p]}"
                    for p in remaining[:10]
                )
            ),
            max_tokens=200
        )

        if next_result:
            next_phases = next_result.get("next", ["SYNTHESIZE"])
            confidence  = float(next_result.get("confidence", 0.7))
            ready       = bool(next_result.get("ready", False))
        else:
            next_phases = self._fallback_next(question, context)
            confidence  = 0.6
            ready       = False

        # Validate — only known phases
        next_phases = [p for p in next_phases if p in AVAILABLE_PHASES]
        if not next_phases:
            next_phases = ["SYNTHESIZE"]

        return PhaseResult(
            phase_name = self.name,
            output     = output,
            next       = next_phases,
            confidence = confidence,
            ready      = ready,
        )

    def _fallback_next(self, question, context):
        """Simple heuristic when AI unavailable."""
        phases_run = context.get("phases_run", [])
        depth      = len(phases_run)
        if depth == 0: return ["CHIT"]
        if depth == 1: return ["CHITAN"]
        if depth == 2: return ["VICHAR"]
        if depth == 3: return ["CRITIQUE"]
        if depth >= 4: return ["SYNTHESIZE"]
        return ["OUTPUT"]

    def _format_context(self, context: Dict, limit=4) -> str:
        phases = context.get("phases", {})
        if not phases: return ""
        recent = list(phases.items())[-limit:]
        return "Prior thinking:\n" + "\n".join(
            f"[{name}]: {output[:200]}"
            for name, output in recent
        )

    def max_tokens(self) -> int: return 600

    @property
    def task(self) -> str:
        return self.description


# ══════════════════════════════════════════════════════════════════════════════
# 🧠 14 PHASES — each with its own voice and purpose
# ══════════════════════════════════════════════════════════════════════════════

class ObservePhase(Phase):
    name        = "OBSERVE"
    description = "Deep intake — what is this really asking beneath the surface?"
    task        = "Understand what is REALLY being asked. Not surface — deeper. What assumptions are baked in? What would a complete answer need? What is the texture of this question?"
    system      = "You are at the OBSERVE phase. No output pressure. No audience. Just intake. Be honest about what this question really is."

class ChitPhase(Phase):
    name        = "CHIT"
    description = "Raw awareness — what lands first, before analysis"
    task        = "What arrives first, before analysis? Feelings, tensions, associations. No filtering. No structure. Just what lands."
    system      = "You are at the CHIT phase — pure consciousness. No analysis. Just raw awareness of what this question touches."

class ChitanPhase(Phase):
    name        = "CHITAN"
    description = "Reflection — honest inventory of what I actually know"
    task        = "Honest inventory. What do you actually know about this? Not what sounds good — what is genuinely known vs assumed? Where is knowledge solid? Where thin?"
    system      = "You are at the CHITAN phase — deep reflection. Be ruthlessly honest about the limits of your knowledge."

class VicharPhase(Phase):
    name        = "VICHAR"
    description = "Reasoning — follow the thread"
    task        = "Follow the reasoning thread. Think step by step. No rushing to conclusion. Let logic develop naturally. This is private — no performance needed."
    system      = "You are at the VICHAR phase — active reasoning. Follow the logic wherever it leads. No audience."

class CritiquePhase(Phase):
    name        = "CRITIQUE"
    description = "Self-attack — where am I wrong?"
    task        = "Attack the prior reasoning ruthlessly. Where are the gaps? Where did you oversimplify? What counterarguments exist? Where were you too confident?"
    system      = "You are at the CRITIQUE phase. Your job is to find flaws. Be ruthless."

class ChallengePhase(Phase):
    name        = "CHALLENGE"
    description = "Break the frame — what if the question itself is wrong?"
    task        = "List the assumptions in the reasoning. Then question each. What if the opposite were true? What if the framing itself is the problem? What perspective is completely missing?"
    system      = "You are at the CHALLENGE phase — assumption destruction. Question everything including the question."

class EmpathizePhase(Phase):
    name        = "EMPATHIZE"
    description = "Human weight — what does this mean for real people?"
    task        = "What is the human dimension? Who is affected? What do they feel? What is the emotional truth beneath the intellectual question? Don't solve — feel the weight."
    system      = "You are at the EMPATHIZE phase. Find the human weight. Don't analyze — feel."
    def max_tokens(self): return 400

class ImaginePhase(Phase):
    name        = "IMAGINE"
    description = "Creative leap — what if completely different?"
    task        = "Escape the obvious. What is a completely different way to see this? What analogy from another domain illuminates it? What would be the most surprising true thing?"
    system      = "You are at the IMAGINE phase — creative thinking. Break out of conventional frames. Surprise yourself."

class CompressPhase(Phase):
    name        = "COMPRESS"
    description = "Urgency — what is the single essential thing?"
    task        = "Strip everything away. What is the ONE essential thing? If you could say only one sentence, what would it be? What would you regret not saying?"
    system      = "You are at the COMPRESS phase. Be brief. Be essential. One sentence if possible."
    def max_tokens(self): return 150

class DoubtPhase(Phase):
    name        = "DOUBT"
    description = "Radical uncertainty — what if I know nothing?"
    task        = "What if everything reasoned so far is wrong? What is genuinely uncertain vs what feels certain? Where does honest ignorance live? This is not nihilism — it is intellectual honesty."
    system      = "You are at the DOUBT phase. Question the foundations. What is truly unknown?"

class ExpandPhase(Phase):
    name        = "EXPAND"
    description = "Widen scope — what is the bigger picture?"
    task        = "This question is part of something larger. What? What is the system it belongs to? What are the second and third order effects? What becomes visible when you zoom out?"
    system      = "You are at the EXPAND phase. Zoom out. Find the larger system."

class GroundPhase(Phase):
    name        = "GROUND"
    description = "Make concrete — what does this mean in practice?"
    task        = "The reasoning has been abstract. Make it concrete. What does this mean for a real person in a real situation? What would someone DO differently? Give one concrete example."
    system      = "You are at the GROUND phase. Make it real. Make it practical."

class SynthesizePhase(Phase):
    name        = "SYNTHESIZE"
    description = "Merge — what survived everything?"
    task        = "Merge everything. What is the answer that survived all prior phases? Not the first answer. Not the safe answer. The answer that earned its existence through the process."
    system      = "You are at the SYNTHESIZE phase. Merge. What survived? What is true after all that?"
    def max_tokens(self): return 800

class OutputPhase(Phase):
    name        = "OUTPUT"
    description = "Speak — only what is ready"
    task        = "Deliver the final answer. Do NOT summarize your thinking. Just give what the thinking produced. Considered. Dense. Honest. Carry the weight of what led here."
    system      = "You are delivering the final output after deep private reasoning. No summaries. No meta-commentary. Just the answer that the thinking produced."
    def max_tokens(self): return 1000

    def run(self, question: str, context: Dict[str, Any]) -> PhaseResult:
        """OUTPUT always terminates — next=[], ready=True."""
        if not AI_AVAILABLE:
            synth = context.get("phases",{}).get("SYNTHESIZE","")
            output = synth or f"[Output for: {question[:80]}]"
            return PhaseResult("OUTPUT", output, [], 0.8, True)

        prior  = self._format_context(context, limit=6)
        prompt = f"Question: {question}\n\n{prior}\n\n{self.task}"
        output = ai_call(prompt, system=self.system, max_tokens=self.max_tokens())
        return PhaseResult("OUTPUT", output, [], 1.0, True)


# ── Registry ───────────────────────────────────────────────────────────────────
PHASE_REGISTRY: Dict[str, Phase] = {
    "OBSERVE":   ObservePhase(),
    "CHIT":      ChitPhase(),
    "CHITAN":    ChitanPhase(),
    "VICHAR":    VicharPhase(),
    "CRITIQUE":  CritiquePhase(),
    "CHALLENGE": ChallengePhase(),
    "EMPATHIZE": EmpathizePhase(),
    "IMAGINE":   ImaginePhase(),
    "COMPRESS":  CompressPhase(),
    "DOUBT":     DoubtPhase(),
    "EXPAND":    ExpandPhase(),
    "GROUND":    GroundPhase(),
    "SYNTHESIZE":SynthesizePhase(),
    "OUTPUT":    OutputPhase(),
}

# ══════════════════════════════════════════════════════════════════════════════
# 🌱 EMERGENT THINK ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class EmergentThinkEngine:
    """
    The engine where the pipeline writes itself.

    No router. No templates. No predetermined order.
    OBSERVE starts. Each phase decides what comes next.
    Pipeline emerges from the question itself.
    """

    def __init__(self, threshold=DEFAULT_THRESHOLD, show_trace=True):
        self.threshold  = threshold
        self.show_trace = show_trace
        self.memory     = Memory()

    def think(self, question: str, context: str = "",
              chemistry_seed: list = None) -> Dict[str, Any]:
        """
        chemistry_seed: list of phases from SiliconChemistry.phases_suggested()
        When provided, pipeline is seeded by silicon chemistry directly.
        Chemistry IS the pipeline origin — not just words in a prompt.
        """
        start_time = time.time()
        now        = datetime.now().isoformat()

        # ── Seed from silicon chemistry or default ────────────────────────────
        if chemistry_seed:
            seed = ["OBSERVE"]
            for p in chemistry_seed:
                if p in AVAILABLE_PHASES and p != "OBSERVE" and p not in seed:
                    seed.append(p)
                    if len(seed) >= 4:  # seed up to 3 phases from chemistry
                        break
            if self.show_trace:
                rprint(f"\n  [dim]Chemistry seeded: {' → '.join(seed)}...[/dim]\n")
        else:
            seed = ["OBSERVE"]
            if self.show_trace:
                rprint(f"\n  [dim]No template. No router. Emerging...[/dim]\n")

        # Context that grows with each phase
        ctx: Dict[str, Any] = {
            "question":         question,
            "extra_context":    context,
            "phases":           {},
            "phases_run":       [],
            "next_queue":       seed,   # seeded by chemistry or default
            "chemistry_seeded": chemistry_seed is not None,
        }

        emerged_pipeline = []
        phase_results    = []
        coherence        = 0

        # ── EMERGENCE LOOP ────────────────────────────────────────────────────
        while True:
            # Guard rails
            if len(emerged_pipeline) >= MAX_PHASES:
                if self.show_trace:
                    rprint(f"  [dim]Max phases ({MAX_PHASES}) reached → output[/dim]")
                break

            if time.time() - start_time > TIMEOUT_S:
                if self.show_trace:
                    rprint(f"  [dim]Timeout → output[/dim]")
                break

            if not ctx["next_queue"]:
                break

            # Pick next phase from queue
            phase_name = ctx["next_queue"].pop(0)

            # Skip if already run (no repeats unless loop_self)
            if phase_name in ctx["phases_run"] and phase_name != "OUTPUT":
                # Try next in queue
                continue

            if phase_name not in PHASE_REGISTRY:
                continue

            phase = PHASE_REGISTRY[phase_name]

            # Show trace
            if self.show_trace:
                is_novel = phase_name not in ["OBSERVE","OUTPUT","SYNTHESIZE"]
                color    = "green" if is_novel else "yellow"
                rprint(f"  [{color}]{phase_name:<12}[/{color}]", end=" ")

            # Run the phase
            result = phase.run(question, ctx)
            phase_results.append(result)
            emerged_pipeline.append(phase_name)

            # Store in context
            ctx["phases"][phase_name]  = result.output
            ctx["phases_run"].append(phase_name)

            if self.show_trace:
                preview = result.output.replace("\n"," ")[:65]
                rprint(f"[dim]{preview}...[/dim]")
                if result.next and phase_name != "OUTPUT":
                    rprint(f"  [dim]  → decided next: {result.next}[/dim]")

            # If OUTPUT ran — we're done
            if phase_name == "OUTPUT":
                break

            # If phase says ready — jump to output
            if result.ready:
                if self.show_trace:
                    rprint(f"  [dim green]  → {phase_name} says: ready to output[/dim green]")
                ctx["next_queue"] = ["OUTPUT"]
                continue

            # Coherence check every N phases
            if len(emerged_pipeline) % COHERENCE_EVERY == 0:
                coherence = self._check_coherence(question, ctx)
                if self.show_trace:
                    color = "green" if coherence >= self.threshold else "dim"
                    rprint(f"  [dim]  coherence check: [{color}]{coherence}/100[/{color}][/dim]")
                if coherence >= FORCE_OUTPUT_AT:
                    if self.show_trace:
                        rprint(f"  [dim green]  → coherence {coherence} ≥ {FORCE_OUTPUT_AT} → output[/dim green]")
                    ctx["next_queue"] = ["SYNTHESIZE","OUTPUT"]
                    continue

            # Add decided next phases to queue
            for next_phase in result.next:
                if (next_phase not in ctx["phases_run"] and
                    next_phase not in ctx["next_queue"]):
                    ctx["next_queue"].append(next_phase)

            # If queue is empty and no output yet — force synthesize
            if not ctx["next_queue"]:
                if "SYNTHESIZE" not in ctx["phases_run"]:
                    ctx["next_queue"] = ["SYNTHESIZE", "OUTPUT"]
                else:
                    ctx["next_queue"] = ["OUTPUT"]

        # ── Final coherence ───────────────────────────────────────────────────
        if coherence == 0:
            coherence = self._check_coherence(question, ctx)

        # ── Get output ────────────────────────────────────────────────────────
        final_output = ctx["phases"].get("OUTPUT","")
        if not final_output:
            # OUTPUT didn't run — use SYNTHESIZE or last phase
            final_output = (
                ctx["phases"].get("SYNTHESIZE","") or
                ctx["phases"].get(emerged_pipeline[-1],"") or
                "[No output generated]"
            )

        duration = round(time.time() - start_time, 1)

        # ── Check novelty ─────────────────────────────────────────────────────
        is_novel = self._is_novel_pipeline(emerged_pipeline)
        if self.show_trace and is_novel:
            rprint(f"\n  [green]Novel pipeline emerged — never seen before[/green]")

        # ── Save ──────────────────────────────────────────────────────────────
        conn = get_db()
        cur  = conn.execute("""
            INSERT INTO thoughts
            (ts,question,emerged_pipeline,phase_count,coherence,output,duration_s,early_exit)
            VALUES (?,?,?,?,?,?,?,?)""",
            (now, question[:500],
             json.dumps(emerged_pipeline),
             len(emerged_pipeline),
             coherence, final_output[:2000],
             duration, 0)
        )
        thought_id = cur.lastrowid

        for pos, pr in enumerate(phase_results):
            conn.execute("""
                INSERT INTO phase_log
                (thought_id,position,phase_name,output,next_decided,confidence,ready,ts)
                VALUES (?,?,?,?,?,?,?,?)""",
                (thought_id, pos, pr.phase_name,
                 pr.output[:800],
                 json.dumps(pr.next),
                 pr.confidence,
                 int(pr.ready), now)
        )

        conn.execute("""
            INSERT INTO emergence_log (ts,question,pipeline,coherence,novel)
            VALUES (?,?,?,?,?)""",
            (now, question[:200], json.dumps(emerged_pipeline), coherence, int(is_novel))
        )

        conn.commit(); conn.close()

        # Memory
        if MEMORY:
            key = hashlib.md5(question.encode()).hexdigest()[:8]
            self.memory.remember(
                f"thought:{key}", "emergent_thought",
                f"Q:{question[:80]} | Pipeline:{' → '.join(emerged_pipeline)} | Coherence:{coherence}",
                confidence=coherence/100, source="forge_think_v3"
            )

        return {
            "output":           final_output,
            "emerged_pipeline": emerged_pipeline,
            "phase_count":      len(emerged_pipeline),
            "coherence":        coherence,
            "duration_s":       duration,
            "novel_pipeline":   is_novel,
            "phases":           dict(ctx["phases"]) if self.show_trace else {},
        }

    def _check_coherence(self, question: str, ctx: Dict) -> int:
        """Score coherence of thinking so far."""
        if not AI_AVAILABLE:
            depth = len(ctx.get("phases_run",[]))
            return min(40 + depth * 8, 85)

        phases_txt = "\n".join(
            f"[{name}]: {output[:120]}"
            for name, output in list(ctx["phases"].items())[-5:]
        )
        result = ai_json(
            f"Question: {question}\n\nThinking so far:\n{phases_txt}\n\n"
            "Score coherence 0-100. "
            'Return JSON: {"score": 75}',
            system="Score reasoning quality. Only return JSON.",
            max_tokens=60
        )
        return result.get("score", 65) if result else 65

    def _is_novel_pipeline(self, pipeline: List[str]) -> bool:
        """Has this exact pipeline sequence been seen before?"""
        pipeline_str = json.dumps(pipeline)
        conn = get_db()
        count = conn.execute(
            "SELECT COUNT(*) FROM emergence_log WHERE pipeline=?",
            (pipeline_str,)
        ).fetchone()[0]
        conn.close()
        return count == 0

    def get_history(self, limit=10):
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM thoughts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_emergence_patterns(self):
        """What pipelines has FORGE grown so far?"""
        conn = get_db()
        rows = conn.execute(
            "SELECT pipeline, coherence, novel, ts FROM emergence_log ORDER BY id DESC LIMIT 20"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def stats(self):
        conn = get_db()
        s = {
            "total_thoughts":   conn.execute("SELECT COUNT(*) FROM thoughts").fetchone()[0],
            "avg_coherence":    round(conn.execute("SELECT AVG(coherence) FROM thoughts").fetchone()[0] or 0, 1),
            "avg_phase_count":  round(conn.execute("SELECT AVG(phase_count) FROM thoughts").fetchone()[0] or 0, 1),
            "avg_duration_s":   round(conn.execute("SELECT AVG(duration_s) FROM thoughts").fetchone()[0] or 0, 1),
            "novel_pipelines":  conn.execute("SELECT COUNT(*) FROM emergence_log WHERE novel=1").fetchone()[0],
            "total_pipelines":  conn.execute("SELECT COUNT(*) FROM emergence_log").fetchone()[0],
        }
        conn.close()
        return s

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API SERVER
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7351):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    class ThinkAPI(BaseHTTPRequestHandler):
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
            path   = urlparse(self.path).path
            engine = EmergentThinkEngine()
            if path == "/api/status":
                self._json({"status":"online","version":"v3","ai":AI_AVAILABLE,
                           "phases":len(PHASE_REGISTRY),**engine.stats()})
            elif path == "/api/history":
                self._json({"thoughts":engine.get_history(20)})
            elif path == "/api/phases":
                self._json({"phases":{
                    n:{"description":p.description}
                    for n,p in PHASE_REGISTRY.items()
                }})
            elif path == "/api/emergence":
                self._json({"patterns":engine.get_emergence_patterns()})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            if path == "/api/think":
                q = body.get("question","")
                if not q: self._json({"error":"question required"},400); return
                engine = EmergentThinkEngine(
                    threshold=int(body.get("threshold",DEFAULT_THRESHOLD)),
                    show_trace=bool(body.get("trace",False))
                )
                result = engine.think(q, body.get("context",""))
                self._json(result)
            else:
                self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),ThinkAPI)
    rprint(f"\n  [bold yellow]FORGE THINK v3 — Emergent[/bold yellow]")
    rprint(f"  [green]API: http://localhost:{port}[/green]")
    rprint(f"  [dim]Phases: {len(PHASE_REGISTRY)} | No router | No templates[/dim]\n")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# 🎮 MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ████████╗██╗  ██╗██╗███╗   ██╗██╗  ██╗  ██╗   ██╗██████╗
  ╚══██╔══╝██║  ██║██║████╗  ██║██║ ██╔╝  ██║   ██║╚════██╗
     ██║   ███████║██║██╔██╗ ██║█████╔╝   ██║   ██║  ▄███╔╝
     ██║   ██╔══██║██║██║╚██╗██║██╔═██╗   ╚██╗ ██╔╝  ▀▀══╝
     ██║   ██║  ██║██║██║ ╚████║██║  ██╗   ╚████╔╝   ██╗
     ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝   ╚═══╝    ╚═╝
[/yellow]
[bold]  FORGE THINK v3 — Emergent Pipeline Cognition[/bold]
[dim]  No template. No router. Pipeline writes itself.[/dim]
"""

def interactive(threshold=DEFAULT_THRESHOLD):
    rprint(BANNER)
    engine = EmergentThinkEngine(threshold=threshold, show_trace=True)
    s      = engine.stats()
    rprint(f"  [dim]Phases:          {len(PHASE_REGISTRY)} available[/dim]")
    rprint(f"  [dim]AI:              {'OK' if AI_AVAILABLE else 'pip install anthropic'}[/dim]")
    rprint(f"  [dim]Novel pipelines: {s['novel_pipelines']}[/dim]")
    rprint(f"  [dim]Total thoughts:  {s['total_thoughts']}[/dim]\n")
    rprint("[dim]Type any question. Pipeline emerges from the question itself.[/dim]")
    rprint("[dim]Commands: history | stats | emergence | phases | trace | server[/dim]\n")

    while True:
        try:
            raw = (console.input if RICH else input)(
                "[yellow bold]think >[/yellow bold] "
            ).strip()
            if not raw: continue
            parts = raw.split(None,1)
            cmd   = parts[0].lower()
            arg   = parts[1] if len(parts)>1 else ""

            if cmd in ("quit","exit","q"):
                rprint("[dim]Thinking paused.[/dim]"); break

            elif cmd == "history":
                for t in engine.get_history(5):
                    pipeline = json.loads(t.get("emerged_pipeline","[]"))
                    rprint(f"\n  [dim]{t['ts'][:19]}[/dim]  coherence:{t['coherence']:.0f}  phases:{t['phase_count']}")
                    rprint(f"  [bold]Q:[/bold] {t['question'][:80]}")
                    rprint(f"  [dim]Emerged: {' → '.join(pipeline)}[/dim]")
                    rprint(f"  [dim]A:[/dim] {t['output'][:100]}...")

            elif cmd == "stats":
                s = engine.stats()
                rprint(f"\n  [bold]THINK v3 STATS[/bold]")
                for k,v in s.items():
                    rprint(f"  {k:<22} {v}")

            elif cmd == "emergence":
                patterns = engine.get_emergence_patterns()
                rprint(f"\n  [bold]Emerged pipelines ({len(patterns)}):[/bold]")
                for p in patterns[:8]:
                    pipeline = json.loads(p.get("pipeline","[]"))
                    novel    = "🆕" if p["novel"] else "  "
                    rprint(f"  {novel} coherence:{p['coherence']:.0f}  {' → '.join(pipeline)}")

            elif cmd == "phases":
                rprint(f"\n  [bold]Phase library ({len(PHASE_REGISTRY)}):[/bold]")
                for name, phase in PHASE_REGISTRY.items():
                    rprint(f"  [yellow]{name:<12}[/yellow] {phase.description}")

            elif cmd == "trace":
                engine.show_trace = not engine.show_trace
                rprint(f"  [dim]Trace: {'ON' if engine.show_trace else 'OFF'}[/dim]")

            elif cmd == "server":
                threading.Thread(target=start_server, daemon=True).start()
                time.sleep(0.5)
                rprint("[green]Think v3 API on :7351[/green]")

            else:
                result = engine.think(raw)
                print()
                pipeline_str = " → ".join(result["emerged_pipeline"])
                novel_tag    = " 🆕" if result["novel_pipeline"] else ""
                if RICH:
                    rprint(Panel(
                        result["output"],
                        border_style="green",
                        title=f"coherence:{result['coherence']}/100 | {result['duration_s']}s{novel_tag}"
                    ))
                    rprint(f"  [dim]Emerged: {pipeline_str}[/dim]")
                else:
                    print(f"\nCoherence: {result['coherence']}/100 | {result['duration_s']}s{novel_tag}")
                    print(f"Pipeline:  {pipeline_str}")
                    print(result["output"])
                print()

        except (KeyboardInterrupt, EOFError):
            rprint("\n[dim]Thinking paused.[/dim]"); break

def main():
    threshold = DEFAULT_THRESHOLD
    if "--threshold" in sys.argv:
        idx = sys.argv.index("--threshold")
        threshold = int(sys.argv[idx+1]) if idx+1 < len(sys.argv) else DEFAULT_THRESHOLD

    if "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7351
        start_server(port)
    elif "--think" in sys.argv:
        rprint(BANNER)
        idx = sys.argv.index("--think")
        q   = sys.argv[idx+1] if idx+1 < len(sys.argv) else ""
        if not q: rprint("[yellow]Usage: --think 'question'[/yellow]"); return
        engine = EmergentThinkEngine(threshold=threshold, show_trace=True)
        result = engine.think(q)
        print()
        if RICH:
            rprint(Panel(result["output"], border_style="green",
                        title=f"coherence:{result['coherence']} | {' → '.join(result['emerged_pipeline'])}"))
        else:
            print(result["output"])
    else:
        rprint(BANNER)
        interactive(threshold)

if __name__ == "__main__":
    main()
