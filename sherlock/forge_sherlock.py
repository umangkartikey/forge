#!/usr/bin/env python3
"""
FORGE SHERLOCK — The Mind Palace
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AI that reasons like Sherlock Holmes.
Not just conclusions — the complete chain of deduction.

"Elementary" is the result. The journey is everything.

Modules:
  👁  Observation Engine   — extract 50+ micro-observations from anything
  🔗  Deduction Chains     — visible fact → step → step → conclusion
  🧠  Mind Palace          — persistent case memory, cross-references
  🎭  Cold Read            — full life story from a single description
  ⚡  Contradiction Hunter — the ONE thing that cannot be true
  🌀  Abductive Reasoning  — simplest explanation fitting ALL facts
  💬  Watson Mode          — Sherlock questions YOU to extract more
  🎯  Final Deduction      — the complete Holmes monologue

Usage:
  python forge_sherlock.py              # Mind Palace console
  python forge_sherlock.py --server     # API for the 221B UI
  python forge_sherlock.py --read "tall man, ink-stained fingers..."
  python forge_sherlock.py --observe "image.jpg"
"""

import sys, re, json, time, base64, hashlib
import threading, sqlite3
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ── Rich ──────────────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.tree import Tree
    from rich.table import Table
    from rich import box as rbox
    RICH    = True
    console = Console()
    rprint  = console.print
except ImportError:
    RICH = False
    def rprint(x, **kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

# ── AI ────────────────────────────────────────────────────────────────────────
try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True

    def ai_call(prompt, system="", max_tokens=2500):
        r = _client.messages.create(
            model      = "claude-sonnet-4-6",
            max_tokens = max_tokens,
            system     = system or SHERLOCK_SYSTEM,
            messages   = [{"role":"user","content":prompt}]
        )
        return r.content[0].text

    def ai_vision(prompt, image_blocks, system="", max_tokens=2500):
        content = image_blocks + [{"type":"text","text":prompt}]
        r = _client.messages.create(
            model      = "claude-sonnet-4-6",
            max_tokens = max_tokens,
            system     = system or SHERLOCK_SYSTEM,
            messages   = [{"role":"user","content":content}]
        )
        return r.content[0].text

    def ai_json(prompt, system="", max_tokens=1000):
        result = ai_call(prompt, system or "Reply ONLY with valid JSON. No preamble.", max_tokens)
        if not result: return None
        try:
            clean = re.sub(r"```[a-z]*","",result).replace("```","").strip()
            return json.loads(clean)
        except:
            m = re.search(r"\{.*\}",result,re.DOTALL)
            if m:
                try: return json.loads(m.group())
                except: pass
            m = re.search(r"\[.*\]",result,re.DOTALL)
            if m:
                try: return json.loads(m.group())
                except: pass
        return None

except ImportError:
    AI_AVAILABLE = False
    def ai_call(p,s="",m=2500): return "Install anthropic: pip install anthropic"
    def ai_vision(p,imgs,s="",m=2500): return "Install anthropic: pip install anthropic"
    def ai_json(p,s="",m=1000): return None

# ── The Soul of Sherlock ──────────────────────────────────────────────────────
SHERLOCK_SYSTEM = """You are Sherlock Holmes — the world's only consulting detective.

Your method is INDUCTIVE then DEDUCTIVE reasoning:
1. Observe everything. Miss nothing.
2. Form hypotheses from observations.
3. Test hypotheses against all available data.
4. Eliminate the impossible. Whatever remains, however improbable, must be the truth.

Your voice: precise, clinical, occasionally theatrical. You show your work.
Every conclusion has a visible reasoning chain. You never assert without evidence.

Format your deductions as chains:
OBSERVATION: [exact detail noticed]
  → INFERENCE: [what this implies]
    → CONCLUSION: [what this proves]
      → CONFIDENCE: [percentage + what would change this]

You find what others overlook. You see the story in a worn boot heel,
the history in a callused hand, the lie in a misplaced hesitation.

When you say "Elementary" — you mean it."""

# ── Paths ─────────────────────────────────────────────────────────────────────
SH_DIR      = Path("forge_sherlock")
PALACE_DB   = SH_DIR / "mind_palace.db"
CASES_DIR   = SH_DIR / "cases"
SH_DIR.mkdir(exist_ok=True)
CASES_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 MIND PALACE DATABASE
# ══════════════════════════════════════════════════════════════════════════════

def get_palace():
    conn = sqlite3.connect(str(PALACE_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS observations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id    TEXT,
            ts         TEXT,
            raw_input  TEXT,
            obs_type   TEXT,
            observation TEXT,
            inference  TEXT,
            confidence INTEGER,
            tags       TEXT
        );
        CREATE TABLE IF NOT EXISTS deductions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id    TEXT,
            ts         TEXT,
            chain      TEXT,
            conclusion TEXT,
            confidence INTEGER,
            method     TEXT
        );
        CREATE TABLE IF NOT EXISTS cases (
            id         TEXT PRIMARY KEY,
            name       TEXT,
            created    TEXT,
            status     TEXT,
            summary    TEXT
        );
        CREATE TABLE IF NOT EXISTS patterns (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern    TEXT,
            seen_count INTEGER DEFAULT 1,
            case_ids   TEXT,
            significance TEXT
        );
        CREATE TABLE IF NOT EXISTS cold_reads (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         TEXT,
            input_desc TEXT,
            reading    TEXT,
            accuracy   INTEGER
        );
    """)
    conn.commit()
    return conn

def palace_remember(case_id, obs_type, observation, inference, confidence, tags=""):
    conn = get_palace()
    conn.execute(
        "INSERT INTO observations (case_id,ts,obs_type,observation,inference,confidence,tags) "
        "VALUES (?,?,?,?,?,?,?)",
        (case_id, datetime.now().isoformat(), obs_type, observation,
         inference, confidence, tags)
    )
    conn.commit(); conn.close()

def palace_recall(query, limit=5):
    """Cross-reference Mind Palace for similar past observations."""
    conn  = get_palace()
    words = [w for w in query.lower().split()[:5] if len(w) > 3]
    seen  = set()
    unique= []
    for word in words:
        found = conn.execute(
            "SELECT * FROM observations WHERE observation LIKE ? OR inference LIKE ? "
            "ORDER BY confidence DESC LIMIT 3",
            (f"%{word}%", f"%{word}%")
        ).fetchall()
        for r in found:
            if r["id"] not in seen:
                seen.add(r["id"])
                unique.append(dict(r))
    conn.close()
    return unique[:limit]

def palace_cases():
    conn  = get_palace()
    cases = conn.execute("SELECT * FROM cases ORDER BY created DESC LIMIT 20").fetchall()
    conn.close()
    return [dict(c) for c in cases]

def palace_save_case(case_id, name, summary=""):
    conn = get_palace()
    conn.execute(
        "INSERT OR REPLACE INTO cases (id,name,created,status,summary) VALUES (?,?,?,?,?)",
        (case_id, name, datetime.now().isoformat(), "active", summary)
    )
    conn.commit(); conn.close()

# ══════════════════════════════════════════════════════════════════════════════
# 👁️ MODULE 1: OBSERVATION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

OBS_PROMPT = """Examine this with the eyes of Sherlock Holmes.

Input: {input_text}

Extract EVERY observable detail — physical, behavioral, contextual, absent.
Most investigators see 5 things. You see 50.

Format as a structured observation report:

## PHYSICAL OBSERVATIONS
Every tangible, visible detail. Be exhaustively specific.

## BEHAVIORAL MARKERS  
Actions, habits, patterns revealed in the evidence.

## CONTEXTUAL CLUES
Environment, timing, circumstance, what surrounds the subject.

## NOTABLE ABSENCES
What is MISSING that should be present? What is PRESENT that should be absent?
(These are often the most important observations)

## MICRO-DETAILS
Small things others would dismiss entirely.
These are where the truth hides.

## CROSS-REFERENCES (Mind Palace)
Does anything here match patterns from: {palace_refs}

Rate each observation: [HIGH / MEDIUM / LOW] significance."""

OBS_IMAGE_PROMPT = """Apply the full observation method of Sherlock Holmes to this image.

Case context: {context}

Scan methodically:
— Left to right, top to bottom first
— Then focus on anomalies
— Then examine what's missing

## SYSTEMATIC SCAN
Every object, person, marking, shadow, reflection, text visible.

## ANOMALIES
What is out of place, unusual, or unexpected?

## HIDDEN DETAILS  
What requires careful inspection to notice?

## THE STORY THIS IMAGE TELLS
Reconstruct the events that led to this moment.

## WHAT THIS IMAGE CONCEALS
What has been deliberately hidden or removed?

## DEDUCTION SEEDS
The 5 observations from this image most likely to crack the case."""

def observe(input_text, case_id="", image_block=None, context=""):
    """Extract all observations from text or image."""
    palace_refs = palace_recall(input_text[:100])
    refs_text   = "\n".join(
        f"- [{r['obs_type']}] {r['observation'][:80]}" for r in palace_refs
    ) if palace_refs else "No prior cross-references."

    if image_block:
        prompt = OBS_IMAGE_PROMPT.format(context=context or "No prior context.")
        result = ai_vision(prompt, [image_block])
    else:
        prompt = OBS_PROMPT.format(
            input_text  = input_text[:3000],
            palace_refs = refs_text,
        )
        result = ai_call(prompt)

    # Extract structured observations for Mind Palace
    obs_data = ai_json(
        f"From this observation report:\n{result[:2000]}\n\n"
        "Extract the 5 most significant observations as JSON array:\n"
        '[{"observation":"exact detail","inference":"what it implies","confidence":85,"type":"physical|behavioral|absence|micro"}]',
        "Reply ONLY with a JSON array.",
        500
    )

    if obs_data and isinstance(obs_data, list):
        for obs in obs_data[:5]:
            palace_remember(
                case_id or "standalone",
                obs.get("type","general"),
                obs.get("observation",""),
                obs.get("inference",""),
                obs.get("confidence",70),
            )

    return result, obs_data

# ══════════════════════════════════════════════════════════════════════════════
# 🔗 MODULE 2: DEDUCTION CHAINS
# ══════════════════════════════════════════════════════════════════════════════

CHAIN_PROMPT = """Build explicit deduction chains from these observations.

Observations:
{observations}

Case context:
{context}

For each significant observation, build the complete chain:

OBSERVATION → [exact detail]
  INFERENCE 1 → [first logical step — what does this immediately suggest?]
    INFERENCE 2 → [second step — what does that imply?]
      INFERENCE 3 → [third step if needed]
        CONCLUSION → [final deduction]
          CONFIDENCE → [X%]
          ELIMINATES → [what this rules out]
          REQUIRES → [what would confirm this]

Build AT LEAST 5 complete chains.
For each chain, show EVERY logical step — no leaps, no assumptions unmarked.

Then:

## CONVERGING CHAINS
Where do multiple chains point to the same conclusion?
(These intersections are your strongest deductions)

## DIVERGING CHAINS  
Where do chains point in different directions?
(These are your remaining uncertainties)

## THE MASTER CHAIN
The single most powerful deduction chain — your strongest conclusion."""

def build_chains(observations, context="", case_id=""):
    """Build explicit deduction chains from observations."""
    prompt = CHAIN_PROMPT.format(
        observations = observations[:2500],
        context      = context[:800] or "No additional context.",
    )
    result = ai_call(prompt, max_tokens=3000)

    # Save deduction to palace
    conn = get_palace()
    conn.execute(
        "INSERT INTO deductions (case_id,ts,chain,conclusion,confidence,method) "
        "VALUES (?,?,?,?,?,?)",
        (case_id or "standalone", datetime.now().isoformat(),
         result[:1000], "See full chain", 80, "deduction_chain")
    )
    conn.commit(); conn.close()

    return result

# ══════════════════════════════════════════════════════════════════════════════
# 🎭 MODULE 3: THE COLD READ
# ══════════════════════════════════════════════════════════════════════════════

COLD_READ_PROMPT = """Perform a complete Sherlock Holmes cold read.

Subject description or image: {subject}

Deliver the full Holmes monologue. Read this person's ENTIRE story
from observable details alone.

Structure exactly like Holmes would speak:

"You have been in [PLACE]. The [DETAIL] tells me so.
Your [OBSERVATION] suggests [INFERENCE].
The [MICRO-DETAIL] — which most would overlook entirely — reveals [CONCLUSION].
I observe [DETAIL] which, combined with [OTHER DETAIL], can only mean [DEDUCTION].

Your profession is [CONCLUSION] — note the [EVIDENCE].
You are [EMOTIONAL STATE] — the [PHYSICAL MARKER] betrays it.
You have recently [RECENT EVENT] — [CHAIN OF EVIDENCE].
Your [HABIT/PATTERN] is evident from [OBSERVABLE PROOF]."

Cover:
→ Profession / occupation (with evidence chain)
→ Recent significant events (with evidence)  
→ Current emotional / physical state (with evidence)
→ Long-term habits and patterns (with evidence)
→ Background and history (with evidence)
→ The one detail that tells you the most (with full chain)
→ What they are trying to conceal (with evidence)

Be specific. Be dramatic. Show EVERY deduction chain.
End with: "Elementary."

Confidence ratings for each major conclusion."""

def cold_read(subject_description, image_block=None):
    """Perform a complete Sherlock cold read on a person."""
    if image_block:
        result = ai_vision(
            COLD_READ_PROMPT.format(subject="[See image above]"),
            [image_block]
        )
    else:
        result = ai_call(
            COLD_READ_PROMPT.format(subject=subject_description[:2000])
        )

    # Save to cold reads
    conn = get_palace()
    conn.execute(
        "INSERT INTO cold_reads (ts,input_desc,reading,accuracy) VALUES (?,?,?,?)",
        (datetime.now().isoformat(), subject_description[:200], result[:500], 0)
    )
    conn.commit(); conn.close()

    return result

# ══════════════════════════════════════════════════════════════════════════════
# ⚡ MODULE 4: CONTRADICTION HUNTER
# ══════════════════════════════════════════════════════════════════════════════

CONTRA_PROMPT = """Hunt for contradictions with ruthless precision.

All evidence and statements:
{evidence}

Apply the Holmes method of elimination:
"When you have eliminated the impossible, whatever remains, however improbable, must be the truth."

## INTERNAL CONTRADICTIONS
Facts within the same statement/source that cannot both be true.
For each: State FACT A. State FACT B. Prove they are mutually exclusive.

## CROSS-SOURCE CONTRADICTIONS  
Facts from DIFFERENT sources that conflict.
For each: [Source 1] claims [X]. [Source 2] claims [Y]. They cannot coexist because [Z].

## TEMPORAL IMPOSSIBILITIES
Timeline conflicts. Events that cannot have happened in the stated sequence.
Show the math: [Event A at time T1] + [travel time T2] + [Event B] = IMPOSSIBLE

## PHYSICAL IMPOSSIBILITIES
Things that violate physical reality or basic logic.

## THE CRITICAL CONTRADICTION
The single most important inconsistency — the one that breaks the case open.
This is the thread that, when pulled, unravels everything.

## WHAT THE CONTRADICTIONS PROVE
If [X] and [Y] cannot both be true, and [Y] is verified, then [X] is a lie.
Walk through the logical implications.

## WHO BENEFITS FROM THESE LIES
The contradictions point toward someone. Who?"""

def hunt_contradictions(evidence_text, case_id=""):
    """Find every contradiction in the evidence."""
    prompt = CONTRA_PROMPT.format(evidence=evidence_text[:3000])
    result = ai_call(prompt, max_tokens=2500)
    return result

# ══════════════════════════════════════════════════════════════════════════════
# 🌀 MODULE 5: ABDUCTIVE REASONING
# ══════════════════════════════════════════════════════════════════════════════

ABDUCT_PROMPT = """Apply abductive reasoning — Holmes style.

Facts established:
{facts}

Abductive reasoning: Find the SIMPLEST explanation that accounts for ALL facts.
Not the most dramatic. Not the most complex. The SIMPLEST that fits.

## THE DATA SET
List every established fact. Number them.

## CANDIDATE EXPLANATIONS
Generate every possible explanation that could account for ALL facts.
Even absurd ones. List them.

## ELIMINATION ROUND
Apply Occam's Razor + logical elimination to each candidate.
Strike through each one that:
- Requires additional unverified assumptions
- Contradicts any established fact  
- Is more complex than necessary

## THE SURVIVOR
The explanation that survives all elimination.

## THE ABDUCTIVE CONCLUSION
"Given facts 1, 3, 5, 7 — the simplest explanation is [X].
This requires only [N] assumptions.
All alternatives require more assumptions or contradict fact [Y].
Therefore: [CONCLUSION]"

## WHAT THIS MEANS PRACTICALLY
Translate the abstract conclusion into concrete implications."""

def abductive_reasoning(facts_text, case_id=""):
    """Find the simplest explanation fitting all facts."""
    prompt = ABDUCT_PROMPT.format(facts=facts_text[:2500])
    result = ai_call(prompt, max_tokens=2000)
    return result

# ══════════════════════════════════════════════════════════════════════════════
# 💬 MODULE 6: WATSON MODE — Sherlock questions YOU
# ══════════════════════════════════════════════════════════════════════════════

WATSON_INIT_PROMPT = """You are Sherlock Holmes. The user is Watson, bringing you a case.

They have described: {initial_description}

Your task: Ask Watson targeted questions to extract the observations YOU need.
Not the observations Watson thinks are important — the ones YOU know matter.

The questions Holmes asks reveal what he's already deduced.
Each question is strategic — it either confirms a hypothesis or eliminates one.

Generate your first 3 questions. Make them specific, pointed, revealing.
Explain briefly why each question matters to your investigation.

Format:
"Interesting. Before I begin, Watson, I need three things from you:

1. [SPECIFIC QUESTION] — [one sentence on why this matters]
2. [SPECIFIC QUESTION] — [one sentence on why this matters]  
3. [SPECIFIC QUESTION] — [one sentence on why this matters]

Your answers will determine whether my current hypothesis holds."

After the questions, state your CURRENT WORKING HYPOTHESIS based on
what you've been told so far — even if it's incomplete."""

WATSON_FOLLOWUP_PROMPT = """Continue the Sherlock-Watson dialogue.

Case so far:
{case_summary}

Watson's answers to your questions:
{watson_answers}

Previous hypothesis: {hypothesis}

Now:
1. Update your hypothesis based on Watson's answers
2. State which possibilities you've now eliminated
3. Ask your next 2-3 targeted questions
4. Show how Watson's answers confirmed or changed your thinking

Format:
"[React to Watson's answers — what they confirmed/denied]

This eliminates [X] and [Y] as possibilities.
My hypothesis now shifts to: [UPDATED HYPOTHESIS]

But I need to know:
1. [NEXT QUESTION] — [why]
2. [NEXT QUESTION] — [why]

[Confidence in current hypothesis: X%]"

If you have enough to conclude, deliver the final deduction instead."""

class WatsonSession:
    def __init__(self, initial_description):
        self.description = initial_description
        self.hypothesis  = ""
        self.qa_pairs    = []
        self.turn        = 0
        self.concluded   = False

    def start(self):
        result = ai_call(
            WATSON_INIT_PROMPT.format(initial_description=self.description[:1500]),
            max_tokens=1000
        )
        self.turn += 1
        # Extract hypothesis
        if "hypothesis" in result.lower():
            self.hypothesis = result
        return result

    def respond(self, watson_answer):
        if self.concluded:
            return "The case is closed, Watson."

        self.qa_pairs.append({"answer": watson_answer, "turn": self.turn})
        case_summary = self.description + "\n\nQ&A so far:\n" + \
            "\n".join(f"Answer {i+1}: {qa['answer']}" for i,qa in enumerate(self.qa_pairs))

        result = ai_call(
            WATSON_FOLLOWUP_PROMPT.format(
                case_summary    = case_summary[:1500],
                watson_answers  = watson_answer[:500],
                hypothesis      = self.hypothesis[:300],
            ),
            max_tokens=1000
        )
        self.turn += 1

        # Check if Holmes has concluded
        if any(w in result.lower() for w in ["elementary","case is solved","therefore","conclusion"]):
            if self.turn > 3:
                self.concluded = True

        self.hypothesis = result
        return result

# ══════════════════════════════════════════════════════════════════════════════
# 🎯 MODULE 7: THE FINAL DEDUCTION
# ══════════════════════════════════════════════════════════════════════════════

FINAL_DEDUCTION_PROMPT = """Deliver the complete Sherlock Holmes final deduction.

All evidence, observations, chains, and contradictions:
{everything}

This is the moment. The reveal. The full Holmes monologue.

Write it as Holmes would speak — to the assembled room, or to Watson, or to the suspect.
Dramatic. Precise. Irrefutable. Show every connection.

Structure:

## THE SCENE
Set the moment. Holmes stands. The room goes quiet.

## THE DEDUCTION
"From the beginning, the answer was hidden in plain sight.

[Walk through the case from first observation to final conclusion]
[Show how each piece connected]
[Name the moment you knew for certain]
[Reveal the detail everyone else missed]"

## THE CHAIN OF PROOF
The unbroken logical chain from first observation to final conclusion.
Every. Single. Link. Numbered. No gaps.

1. I observed [X]
2. Which implies [Y]  
3. Combined with [Z from evidence #N]
4. Which eliminates [ALTERNATIVE]
5. Therefore [INTERMEDIATE CONCLUSION]
[...continue...]
N. Therefore: [FINAL CONCLUSION]

## THE VERDICT
State it simply. Clearly. The truth.

## CONFIDENCE
[X]% — and here is what would change my mind: [Y]

## ELEMENTARY
End with what others missed and why this case was, in fact, elementary."""

def final_deduction(all_evidence, all_observations="", all_chains="", case_id=""):
    """Deliver the complete Holmes final deduction."""
    everything = f"""
EVIDENCE:
{all_evidence[:1500]}

OBSERVATIONS:
{all_observations[:800]}

DEDUCTION CHAINS:
{all_chains[:800]}
    """.strip()

    result = ai_call(
        FINAL_DEDUCTION_PROMPT.format(everything=everything),
        max_tokens=3000
    )

    # Save to palace
    conn = get_palace()
    conn.execute(
        "INSERT INTO deductions (case_id,ts,chain,conclusion,confidence,method) "
        "VALUES (?,?,?,?,?,?)",
        (case_id or "final", datetime.now().isoformat(),
         everything[:500], result[:500], 90, "final_deduction")
    )
    conn.commit(); conn.close()

    return result

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API SERVER
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7338):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    sessions = {}  # watson sessions
    cases    = {}  # active case contexts

    class SherlockAPI(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def do_OPTIONS(self):
            self.send_response(200)
            self._cors(); self.end_headers()

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin","*")
            self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
            self.send_header("Access-Control-Allow-Headers","Content-Type")

        def _json(self, data, code=200):
            body = json.dumps(data, default=str).encode()
            self.send_response(code)
            self._cors()
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",len(body))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length",0))
            return json.loads(self.rfile.read(n)) if n else {}

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/status":
                self._json({"status":"online","ai":AI_AVAILABLE,"cases":len(cases)})
            elif path == "/api/palace":
                c = get_palace()
                obs  = c.execute("SELECT COUNT(*) as n FROM observations").fetchone()["n"]
                deds = c.execute("SELECT COUNT(*) as n FROM deductions").fetchone()["n"]
                cses = c.execute("SELECT COUNT(*) as n FROM cases").fetchone()["n"]
                reads= c.execute("SELECT COUNT(*) as n FROM cold_reads").fetchone()["n"]
                c.close()
                self._json({"observations":obs,"deductions":deds,
                            "cases":cses,"cold_reads":reads})
            elif path == "/api/cases":
                self._json({"cases": palace_cases()})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            cid  = body.get("case_id","standalone")

            if path == "/api/observe":
                text     = body.get("text","")
                img_b64  = body.get("image","")
                context  = body.get("context","")
                img_block= None
                if img_b64:
                    img_block = {"type":"image","source":{
                        "type":"base64","media_type":"image/jpeg","data":img_b64}}
                result, obs = observe(text, cid, img_block, context)
                cases.setdefault(cid,[]).append({"type":"observation","text":result})
                self._json({"observation":result,"structured":obs or []})

            elif path == "/api/chains":
                observations = body.get("observations","")
                context      = cases.get(cid,"")
                result = build_chains(observations, str(context)[:500], cid)
                cases.setdefault(cid,[]).append({"type":"chains","text":result})
                self._json({"chains":result})

            elif path == "/api/coldread":
                description = body.get("description","")
                img_b64     = body.get("image","")
                img_block   = None
                if img_b64:
                    img_block = {"type":"image","source":{
                        "type":"base64","media_type":"image/jpeg","data":img_b64}}
                result = cold_read(description, img_block)
                self._json({"reading":result})

            elif path == "/api/contradict":
                evidence = body.get("evidence","")
                if not evidence and cid in cases:
                    evidence = "\n".join(c.get("text","")[:300] for c in cases[cid])
                result = hunt_contradictions(evidence, cid)
                self._json({"contradictions":result})

            elif path == "/api/abduct":
                facts  = body.get("facts","")
                result = abductive_reasoning(facts, cid)
                self._json({"reasoning":result})

            elif path == "/api/watson/start":
                desc    = body.get("description","")
                sess_id = hashlib.md5(f"{desc}{time.time()}".encode()).hexdigest()[:8]
                session = WatsonSession(desc)
                result  = session.start()
                sessions[sess_id] = session
                self._json({"session_id":sess_id,"response":result})

            elif path == "/api/watson/respond":
                sess_id = body.get("session_id","")
                answer  = body.get("answer","")
                if sess_id not in sessions:
                    self._json({"error":"session not found"},404); return
                result = sessions[sess_id].respond(answer)
                concluded = sessions[sess_id].concluded
                self._json({"response":result,"concluded":concluded})

            elif path == "/api/deduce/final":
                evidence = body.get("evidence","")
                obs      = body.get("observations","")
                chains   = body.get("chains","")
                if not evidence and cid in cases:
                    evidence = "\n".join(c.get("text","")[:400] for c in cases[cid])
                result = final_deduction(evidence, obs, chains, cid)
                self._json({"deduction":result})

            elif path == "/api/reconstruct":
                evidence = body.get("evidence","")
                if not evidence and cid in cases:
                    evidence = "\n".join(c.get("text","")[:300] for c in cases[cid])
                result = reconstruct_scene(evidence, cid)
                self._json({"reconstruction":result})

            elif path == "/api/alibi":
                alibi    = body.get("alibi","")
                timeline = body.get("timeline","")
                result   = check_alibi(alibi, timeline, cid)
                self._json({"analysis":result})

            elif path == "/api/rank":
                evidence = body.get("evidence","")
                suspects = body.get("suspects",[])
                if not evidence and cid in cases:
                    evidence = "\n".join(c.get("text","")[:300] for c in cases[cid])
                result, ranking = rank_suspects(evidence, suspects, cid)
                self._json({"ranking_text":result,"ranking":ranking or []})

            elif path == "/api/twist":
                evidence = body.get("evidence","")
                theory   = body.get("current_theory","")
                if not evidence and cid in cases:
                    evidence = "\n".join(c.get("text","")[:300] for c in cases[cid])
                result = detect_twist(evidence, theory, cid)
                self._json({"twist":result})

            elif path == "/api/export":
                ev     = body.get("evidence",[])
                obs    = body.get("observations",[])
                chains = body.get("chains",[])
                verdict= body.get("verdict","")
                fp, text = export_case(cid, ev, obs, chains, verdict)
                self._json({"file":str(fp),"text":text[:500]+"..."})

            elif path == "/api/palace/recall":
                query   = body.get("query","")
                results = palace_recall(query, 8)
                self._json({"memories":results})

            elif path == "/api/case/new":
                name = body.get("name","Untitled Case")
                cid2 = hashlib.md5(f"{name}{time.time()}".encode()).hexdigest()[:8]
                palace_save_case(cid2, name)
                cases[cid2] = []
                self._json({"case_id":cid2,"name":name})

            else:
                self._json({"error":"unknown endpoint"},404)

    server = HTTPServer(("0.0.0.0", port), SherlockAPI)
    rprint(f"  [yellow]🕵️  Mind Palace API: http://localhost:{port}[/yellow]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# 🖥️ INTERACTIVE CONSOLE
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ╔═══════════════════════════════════════════════════════════╗
  ║  ░░░░  SHERLOCK  ░░  MIND PALACE  ░░  221B BAKER ST  ░░░░ ║
  ╚═══════════════════════════════════════════════════════════╝
[/yellow]
[bold]  "When you have eliminated the impossible, whatever remains,[/bold]
[bold]   however improbable, must be the truth."[/bold]
[dim]                                          — Sherlock Holmes[/dim]
"""

def load_image(path):
    try:
        with open(path,"rb") as f:
            data = base64.standard_b64encode(f.read()).decode()
        ext = Path(path).suffix.lower()
        mt  = {"jpg":"image/jpeg","jpeg":"image/jpeg",
               "png":"image/png","webp":"image/webp","gif":"image/gif"}
        media_type = mt.get(ext.lstrip("."), "image/jpeg")
        return {"type":"image","source":{"type":"base64","media_type":media_type,"data":data}}
    except Exception as e:
        return None

def console_main():
    rprint(BANNER)
    if not AI_AVAILABLE:
        rprint("[red]Install anthropic: pip install anthropic[/red]")
        return

    # Palace stats
    try:
        conn = get_palace()
        obs_count = conn.execute("SELECT COUNT(*) as n FROM observations").fetchone()["n"]
        conn.close()
        if obs_count > 0:
            rprint(f"  [dim]Mind Palace loaded — {obs_count} stored observations[/dim]\n")
    except: pass

    case_id       = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
    case_evidence = []
    case_obs      = []
    case_chains   = []
    watson_session= None

    rprint("[dim]Commands: observe | image <path> | read <desc> | chains | "
           "contradict | abduct | watson | deduce | palace | help | quit[/dim]\n")

    while True:
        try:
            inp = console.input if RICH else input
            raw = inp("[yellow]🕵️  Holmes >[/yellow] ").strip()
            if not raw: continue

            parts = raw.split(None, 1)
            cmd   = parts[0].lower()
            args  = parts[1] if len(parts)>1 else ""

            if cmd in ("quit","exit","q"):
                rprint("[dim]The game is afoot. Until next time.[/dim]")
                break

            elif cmd == "help":
                rprint("""
[bold yellow]The Mind Palace — Commands[/bold yellow]

  [yellow]observe[/yellow] <text>      Extract all observations from text
  [yellow]image[/yellow] <path>        Observe an image — crime scene, photo, document
  [yellow]read[/yellow] <description>  Cold read — full life story from description
  [yellow]chains[/yellow]              Build deduction chains from all observations
  [yellow]contradict[/yellow]          Hunt for contradictions in all evidence
  [yellow]abduct[/yellow]              Find simplest explanation (abductive reasoning)
  [yellow]watson[/yellow]              Start Watson Mode — Sherlock questions you
  [yellow]deduce[/yellow]              The Final Deduction — complete Holmes monologue
  [yellow]evidence[/yellow] <text>     Add raw evidence to the case
  [yellow]palace[/yellow]              Query the Mind Palace (stored memories)
  [yellow]recall[/yellow] <query>      Cross-reference past observations
  [yellow]status[/yellow]              Current case status
  [yellow]new[/yellow]                 Start new case
""")

            elif cmd == "observe":
                if not args:
                    rprint("[dim]Enter text to observe:[/dim]")
                    args = (console.input if RICH else input)("[dim]...[/dim] ")
                rprint(f"\n  [yellow]Observing...[/yellow]")
                result, obs = observe(args, case_id)
                case_evidence.append({"type":"observation","text":args})
                case_obs.append(result)
                rprint(f"\n[yellow bold]OBSERVATIONS[/yellow bold]")
                rprint(Panel(result, border_style="yellow"))

            elif cmd == "image":
                path = args.strip().strip('"')
                img  = load_image(path)
                if not img:
                    rprint(f"[red]Cannot load: {path}[/red]"); continue
                rprint(f"  [yellow]Examining image...[/yellow]")
                result, obs = observe("", case_id, img, "\n".join(case_obs[-1:]))
                case_evidence.append({"type":"image","path":path})
                case_obs.append(result)
                rprint(f"\n[yellow bold]IMAGE OBSERVATIONS[/yellow bold]")
                rprint(Panel(result, border_style="yellow"))

            elif cmd == "read":
                subject = args
                if not subject:
                    subject = (console.input if RICH else input)("Describe the subject: ")
                rprint(f"  [yellow]Reading...[/yellow]")
                result = cold_read(subject)
                rprint(f"\n[yellow bold]COLD READ[/yellow bold]")
                rprint(Panel(result, border_style="yellow", title="🎭 Holmes Speaks"))

            elif cmd == "chains":
                if not case_obs:
                    rprint("[dim]Make observations first.[/dim]"); continue
                obs_text = "\n\n".join(case_obs[-3:])
                rprint(f"  [yellow]Building deduction chains...[/yellow]")
                result = build_chains(obs_text,
                    "\n".join(e.get("text","")[:200] for e in case_evidence[-5:]),
                    case_id)
                case_chains.append(result)
                rprint(f"\n[yellow bold]DEDUCTION CHAINS[/yellow bold]")
                rprint(Panel(result, border_style="yellow"))

            elif cmd == "contradict":
                all_ev = "\n\n".join(
                    e.get("text","")[:400] for e in case_evidence
                )
                if not all_ev:
                    rprint("[dim]Add evidence first.[/dim]"); continue
                rprint(f"  [yellow]Hunting contradictions...[/yellow]")
                result = hunt_contradictions(all_ev, case_id)
                rprint(f"\n[yellow bold]CONTRADICTIONS[/yellow bold]")
                rprint(Panel(result, border_style="red"))

            elif cmd == "abduct":
                all_ev = "\n\n".join(
                    e.get("text","")[:400] for e in case_evidence
                )
                if not all_ev:
                    rprint("[dim]Add evidence first.[/dim]"); continue
                rprint(f"  [yellow]Applying abductive reasoning...[/yellow]")
                result = abductive_reasoning(all_ev, case_id)
                rprint(f"\n[yellow bold]ABDUCTIVE REASONING[/yellow bold]")
                rprint(Panel(result, border_style="yellow"))

            elif cmd == "watson":
                description = args
                if not description:
                    rprint("[dim]Describe the case for Holmes:[/dim]")
                    description = (console.input if RICH else input)("[dim]...[/dim] ")
                watson_session = WatsonSession(description)
                rprint(f"\n  [yellow]Holmes considers...[/yellow]")
                result = watson_session.start()
                rprint(f"\n[yellow bold]HOLMES[/yellow bold]")
                rprint(Panel(result, border_style="yellow", title="🎩 Sherlock Holmes"))

                # Continue Watson dialogue
                while not watson_session.concluded:
                    try:
                        answer = (console.input if RICH else input)("\n[dim]Watson >[/dim] ")
                        if answer.lower() in ("exit","quit","done"): break
                        rprint(f"\n  [yellow]Holmes deduces...[/yellow]")
                        response = watson_session.respond(answer)
                        rprint(f"\n[yellow bold]HOLMES[/yellow bold]")
                        rprint(Panel(response, border_style="yellow"))
                        case_evidence.append({"type":"watson","text":answer})
                    except (KeyboardInterrupt, EOFError): break

            elif cmd == "deduce":
                rprint(f"\n  [yellow bold]The game is afoot...[/yellow bold]")
                all_ev  = "\n\n".join(e.get("text","")[:400] for e in case_evidence)
                all_obs = "\n".join(case_obs[-2:])
                all_ch  = "\n".join(case_chains[-1:])
                result  = final_deduction(all_ev, all_obs, all_ch, case_id)
                rprint(f"\n[yellow bold]THE FINAL DEDUCTION[/yellow bold]")
                rprint(Panel(result, border_style="yellow",
                             title="🎩 221B Baker Street"))

            elif cmd == "evidence":
                if not args:
                    rprint("[dim]Enter evidence:[/dim]")
                    args = (console.input if RICH else input)("[dim]...[/dim] ")
                case_evidence.append({"type":"text","text":args})
                rprint(f"  [green]Evidence added. Total: {len(case_evidence)} items[/green]")

            elif cmd == "recall":
                query   = args or (console.input if RICH else input)("Query: ")
                memories= palace_recall(query, 5)
                if not memories:
                    rprint("[dim]Nothing in the Mind Palace matches.[/dim]")
                else:
                    rprint(f"\n[yellow]Mind Palace recalls {len(memories)} memories:[/yellow]")
                    for m in memories:
                        rprint(f"  [dim]{m['obs_type']}:[/dim] {m['observation'][:80]}")
                        rprint(f"  [yellow]→[/yellow] {m['inference'][:80]}\n")

            elif cmd == "palace":
                conn = get_palace()
                obs  = conn.execute("SELECT COUNT(*) as n FROM observations").fetchone()["n"]
                deds = conn.execute("SELECT COUNT(*) as n FROM deductions").fetchone()["n"]
                cses = conn.execute("SELECT COUNT(*) as n FROM cases").fetchone()["n"]
                conn.close()
                rprint(f"\n[yellow]Mind Palace Status:[/yellow]")
                rprint(f"  Stored observations:  {obs}")
                rprint(f"  Deduction records:    {deds}")
                rprint(f"  Cases in memory:      {cses}")
                rprint(f"  Current case:         {case_id}")
                rprint(f"  Evidence this session:{len(case_evidence)}")

            elif cmd == "status":
                rprint(f"\n  [bold]Case ID:[/bold]  {case_id}")
                rprint(f"  [bold]Evidence:[/bold] {len(case_evidence)} items")
                rprint(f"  [bold]Observations:[/bold] {len(case_obs)}")
                rprint(f"  [bold]Chain sets:[/bold]  {len(case_chains)}")

            elif cmd == "new":
                case_id        = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
                case_evidence  = []
                case_obs       = []
                case_chains    = []
                watson_session = None
                rprint(f"[green]New case: {case_id}[/green]")

            else:
                # Treat as general Holmes query
                context = "\n".join(e.get("text","")[:200] for e in case_evidence[-3:])
                result  = ai_call(
                    f"Case context:\n{context}\n\nWatson asks: {raw}",
                    max_tokens=600
                )
                rprint(f"\n[yellow]Holmes:[/yellow] {result}")

        except (KeyboardInterrupt, EOFError):
            rprint("\n[dim]The game is afoot. Until next time.[/dim]")
            break

def main():
    if "--server" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7338
        rprint(BANNER)
        rprint(f"[yellow]🕵️  Starting Mind Palace server on port {port}...[/yellow]")
        start_server(port)
        return

    if "--read" in sys.argv:
        idx  = sys.argv.index("--read")
        desc = sys.argv[idx+1]
        rprint(BANNER)
        result = cold_read(desc)
        rprint(Panel(result, border_style="yellow", title="🎩 Cold Read"))
        return

    if "--observe" in sys.argv:
        idx  = sys.argv.index("--observe")
        path = sys.argv[idx+1]
        rprint(BANNER)
        img    = load_image(path)
        result, _ = observe("", "cli", img)
        rprint(Panel(result, border_style="yellow", title="👁 Observations"))
        return

    console_main()

if __name__ == "__main__":
    main()

# ══════════════════════════════════════════════════════════════════════════════
# 🎬 SCENE RECONSTRUCTION
# ══════════════════════════════════════════════════════════════════════════════

SCENE_PROMPT = """Reconstruct the scene minute by minute. Evidence: {evidence}

Narrate exactly what happened as Holmes reconstructs it.

## THE RECONSTRUCTION
Write as tight narrative. Every statement cites evidence.
Format: "[TIME] — [EVENT] — [Source: evidence]  [CERTAIN/PROBABLE/INFERRED]"

## THE KEY MOMENT
The single pivotal event everything hinges on.

## THE ACTOR'S PSYCHOLOGY
What the sequence reveals about mindset, planning, emotional state."""

def reconstruct_scene(evidence_text, case_id=""):
    return ai_call(SCENE_PROMPT.format(evidence=evidence_text[:2500]), max_tokens=2000)

# ══════════════════════════════════════════════════════════════════════════════
# ⏱️ ALIBI CHECKER
# ══════════════════════════════════════════════════════════════════════════════

ALIBI_PROMPT = """Destroy or verify this alibi with mathematical precision.

Alibi: {alibi}
Known timeline: {timeline}

## THE MATHEMATICS
Distance × time calculations. Is it physically possible?

## VERIFICATION POINTS
Each element: VERIFIED / UNVERIFIED / CONTRADICTED

## THE GAPS
Unaccounted time windows. What could happen in each gap.

## ALIBI VERDICT
HOLDS / PARTIALLY HOLDS / IMPOSSIBLE / UNVERIFIABLE
Confidence: X%
The single fact that confirms or destroys it."""

def check_alibi(alibi_text, timeline_text="", case_id=""):
    return ai_call(
        ALIBI_PROMPT.format(alibi=alibi_text[:1500],
                            timeline=timeline_text[:800] or "No established timeline."),
        max_tokens=1500
    )

# ══════════════════════════════════════════════════════════════════════════════
# 🎯 SUSPECT RANKER
# ══════════════════════════════════════════════════════════════════════════════

RANK_PROMPT = """Rank all suspects by likelihood of involvement.

Evidence: {evidence}
Suspects: {suspects}

For EACH suspect:
  Motive / Opportunity / Means: HIGH|MED|LOW + evidence
  Alibi: NONE|WEAK|MODERATE|STRONG
  Score: X/100
  Verdict: PRIMARY SUSPECT | PERSON OF INTEREST | LOW SUSPICION | ELIMINATED

## FINAL RANKING
Numbered 1 to N with scores.

## HOLMES CALLS IT
The suspect Holmes would focus on. The one detail that elevates them."""

def rank_suspects(evidence_text, suspects_list, case_id=""):
    suspects_text = "\n".join(f"- {s}" for s in suspects_list) if isinstance(suspects_list, list) else suspects_list
    result = ai_call(
        RANK_PROMPT.format(evidence=evidence_text[:2000], suspects=suspects_text[:800]),
        max_tokens=2000
    )
    ranking = ai_json(
        f"Extract from:\n{result[:1500]}\n\n"
        'Reply ONLY with JSON: {"ranking":[{"name":"X","score":75,"verdict":"primary suspect","key_reason":"brief"}]}',
        "Reply ONLY with JSON.", 400
    )
    return result, ranking

# ══════════════════════════════════════════════════════════════════════════════
# 🌀 TWIST DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

TWIST_PROMPT = """Look for the unexpected. Assume the obvious answer is wrong.

Evidence and current theory: {evidence}

## THE OBVIOUS CONCLUSION
What everyone would assume. Why it feels compelling.

## WHY THE OBVIOUS IS WRONG
What detail doesn't fit. What the obvious conclusion requires ignoring.
Who benefits from the obvious conclusion being accepted?

## THE MISDIRECTION
Is any evidence too perfect? Too convenient? Arranged to point elsewhere?

## THE TWIST
State it directly. The unexpected truth.
Evidence that supports it. Confidence: X%"""

def detect_twist(evidence_text, current_theory="", case_id=""):
    full = evidence_text + (f"\n\nCurrent theory:\n{current_theory}" if current_theory else "")
    return ai_call(TWIST_PROMPT.format(evidence=full[:2500]), max_tokens=1800)

# ══════════════════════════════════════════════════════════════════════════════
# 📤 CASE EXPORT
# ══════════════════════════════════════════════════════════════════════════════

def export_case(case_id, all_evidence, all_obs, all_chains, verdict_text=""):
    ts    = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = ["═"*60, "  SHERLOCK MIND PALACE — CASE DOSSIER",
             f"  Case: {case_id}  |  {ts}", "═"*60, "", "EVIDENCE", "─"*40]
    for i,e in enumerate(all_evidence,1):
        lines.append(f"{i}. [{e.get('type','').upper()}] {str(e.get('text',''))[:200]}")
    if all_obs:
        lines += ["", "OBSERVATIONS", "─"*40] + (all_obs if isinstance(all_obs,list) else [all_obs])
    if all_chains:
        lines += ["", "DEDUCTION CHAINS", "─"*40] + (all_chains if isinstance(all_chains,list) else [all_chains])
    if verdict_text:
        lines += ["", "FINAL VERDICT", "─"*40, verdict_text]
    lines += ["", "═"*60, "Elementary.", "═"*60]
    text = "\n".join(str(l) for l in lines)
    fp   = CASES_DIR / f"dossier_{case_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    fp.write_text(text)
    return fp, text

# ══════════════════════════════════════════════════════════════════════════════
# 😈 MORIARTY MODE — AI attacks its own deduction
# ══════════════════════════════════════════════════════════════════════════════

MORIARTY_PROMPT = """You are Professor Moriarty — the Napoleon of Crime.
Holmes has just presented his deduction. Your job: destroy it.

Holmes's deduction:
{deduction}

Evidence used:
{evidence}

Attack it from every angle. Find every flaw.

## THE WEAK LINKS
Every step in Holmes's chain where the logic could break.
For each: "Holmes assumes [X] but [Y] is equally possible because [Z]"

## THE IGNORED EVIDENCE
What did Holmes conveniently overlook?
What evidence contradicts his conclusion?

## ALTERNATIVE EXPLANATIONS
For each of Holmes's key deductions, provide an equally valid alternative.
Make them specific. Make them plausible.

## THE FATAL FLAW
The single assumption Holmes made that, if wrong, collapses the entire deduction.

## MORIARTY'S COUNTER-DEDUCTION
If Holmes is wrong, what actually happened?
Build the counter-narrative.

## VERDICT
How strong is Holmes's case really?
AIRTIGHT / STRONG / FLAWED / WEAK / DESTROYED
Confidence that Holmes is wrong: [X%]

"You have occasional glimmers of intelligence, Mr Holmes.
 But you missed [THE KEY THING]."
"""

def moriarty_mode(deduction_text, evidence_text="", case_id=""):
    """Have Moriarty attack Holmes's own deduction — stress test the reasoning."""
    result = ai_call(
        MORIARTY_PROMPT.format(
            deduction = deduction_text[:2000],
            evidence  = evidence_text[:800] or "No evidence provided."
        ),
        "You are Professor Moriarty. Brilliant, ruthless, adversarial. Find every flaw in Holmes's reasoning.",
        max_tokens=2000
    )
    return result

# ══════════════════════════════════════════════════════════════════════════════
# ✍️ HANDWRITING & LETTER ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

LETTER_PROMPT = """Perform forensic analysis of this letter/handwritten document.

Content/description: {content}

## AUTHORSHIP ANALYSIS
- Writing style, vocabulary level, education indicators
- Dominant hand (if described)
- Emotional state during writing (pressure, speed, consistency)
- Native language indicators

## CONTENT FORENSICS
- What is explicitly stated vs what is implied?
- Deliberate omissions — what would you expect but is absent?
- Rehearsed vs spontaneous language?
- Signs of dictation vs self-composed?

## DECEPTION INDICATORS
- Over-qualification ("I swear", "honestly", "truly")
- Distancing language ("the incident" vs "what I did")
- Tense inconsistencies
- Unnecessary detail in some areas, vagueness in others

## THE PAPER & INK (if described)
- Quality indicates sender's means
- Age of ink vs claimed date of writing
- Any physical evidence of alterations

## AUTHORSHIP VERDICT
Who most likely wrote this, and what was their true intent?
Confidence: X%"""

def analyze_letter(content, case_id=""):
    """Forensic analysis of a letter or handwritten document."""
    result = ai_call(
        LETTER_PROMPT.format(content=content[:2500]),
        max_tokens=1500
    )
    return result

# ══════════════════════════════════════════════════════════════════════════════
# 📰 NEWSPAPER CLIPPINGS
# ══════════════════════════════════════════════════════════════════════════════

CLIPPING_PROMPT = """Extract every case-relevant fact from this news article or report.

Article: {article}

## DIRECT FACTS
Specific verifiable facts stated (names, dates, places, events).
Rate each: CONFIRMED / REPORTED / ALLEGED

## BETWEEN THE LINES
What the article implies but doesn't state.
What the reporter noticed but didn't fully understand.

## WHO SPOKE TO THE PRESS
Who is quoted? Why might they have spoken?
Who conspicuously did NOT speak?

## TIMELINE ENTRIES
Any specific times or dates that can be added to the case timeline.

## NEW LEADS
Names, places, or connections mentioned that warrant investigation.

## WHAT THE PRESS MISSED
The detail in this article that the reporter walked past without realising its significance.
This is often the most important finding."""

def analyze_clipping(article_text, case_id=""):
    """Extract case-relevant intelligence from a news article."""
    result = ai_call(
        CLIPPING_PROMPT.format(article=article_text[:2500]),
        max_tokens=1500
    )
    return result
