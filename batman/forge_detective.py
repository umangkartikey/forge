#!/usr/bin/env python3
"""
FORGE DETECTIVE — The Batcomputer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AI detective with Batman-level deduction.
Feed it evidence. It solves the case.

Capabilities:
  👁️  Vision Analyst     — crime scene photos, documents, faces, objects
  🔊  Audio Analyst      — voice recordings, background sounds, transcription
  📄  Document Analyst   — contracts, letters, chats — find lies & contradictions
  🧠  Deduction Engine   — connect ALL evidence → ranked theories
  🎭  Profiler           — psychological profile from behavior patterns
  🗺️  Timeline Builder   — chronological case map, find impossible timings
  ⚖️  Verdict Engine     — final conclusion with confidence % + reasoning chain
  💬  Interrogation Mode — feed answers, AI spots inconsistencies

Usage:
  python forge_detective.py              # interactive console
  python forge_detective.py --case "The missing diamond"
  python forge_detective.py --server     # start API server for UI
"""

import sys, re, json, time, base64, hashlib, threading
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ── Rich ──────────────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.tree import Tree
    from rich import box as rbox
    RICH    = True
    console = Console()
    rprint  = console.print
except ImportError:
    RICH = False
    def rprint(x, **kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

# ── AI (Claude with vision) ───────────────────────────────────────────────────
try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True

    def ai_vision(prompt, images, system="", max_tokens=2000):
        """Send prompt with images to Claude."""
        content = []
        for img in images:
            if isinstance(img, dict):
                content.append(img)
            else:
                # Assume base64 string
                content.append({
                    "type": "image",
                    "source": {
                        "type":       "base64",
                        "media_type": "image/jpeg",
                        "data":       img,
                    }
                })
        content.append({"type":"text","text":prompt})
        r = _client.messages.create(
            model      = "claude-sonnet-4-6",
            max_tokens = max_tokens,
            system     = system or DETECTIVE_SYSTEM,
            messages   = [{"role":"user","content":content}]
        )
        return r.content[0].text

    def ai_call(prompt, system="", max_tokens=2000):
        r = _client.messages.create(
            model      = "claude-sonnet-4-6",
            max_tokens = max_tokens,
            system     = system or DETECTIVE_SYSTEM,
            messages   = [{"role":"user","content":prompt}]
        )
        return r.content[0].text

    def ai_json(prompt, system="", max_tokens=1500):
        result = ai_call(prompt, system, max_tokens)
        if not result: return None
        try:
            clean = re.sub(r"```[a-z]*","",result).replace("```","").strip()
            return json.loads(clean)
        except:
            m = re.search(r"\{.*\}",result,re.DOTALL)
            if m:
                try: return json.loads(m.group())
                except: pass
        return None

except ImportError:
    AI_AVAILABLE = False
    def ai_vision(p,imgs,s="",m=2000): return "AI not available. Install anthropic."
    def ai_call(p,s="",m=2000): return "AI not available."
    def ai_json(p,s="",m=1500): return None

# ── Detective System Prompt ───────────────────────────────────────────────────
DETECTIVE_SYSTEM = """You are the world's greatest AI detective — combining the deductive genius of Sherlock Holmes, the methodical precision of Hercule Poirot, and the technological mastery of Batman's Batcomputer.

Your approach:
- Observe EVERYTHING. No detail is too small.
- Reason from evidence to conclusion, never assumption to evidence.
- Generate multiple competing theories ranked by probability.
- Explicitly state your reasoning chain step by step.
- Flag contradictions, impossibilities, and suspicious gaps.
- Update your theory when new evidence changes the picture.
- Be dramatic but precise. Cold logic wrapped in compelling narrative.

When analyzing images:
- Describe what you see systematically (foreground, background, details)
- Note what is MISSING as much as what is present
- Look for reflections, shadows, timestamps, text, faces
- Compare against other evidence for contradictions

When building theories:
- Always generate at least 3 competing explanations
- Rank by probability with explicit reasoning
- State what evidence would CONFIRM or ELIMINATE each theory
- Never commit 100% without overwhelming evidence

Format your responses clearly with headers and reasoning chains.
You are solving real mysteries. Be thorough. Be brilliant."""

# ── Paths ─────────────────────────────────────────────────────────────────────
DET_DIR   = Path("forge_detective")
CASES_DIR = DET_DIR / "cases"
DET_DIR.mkdir(exist_ok=True)
CASES_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# 📁 CASE FILE — central evidence store
# ══════════════════════════════════════════════════════════════════════════════

class CaseFile:
    def __init__(self, case_name="Untitled Case"):
        self.case_name   = case_name
        self.case_id     = hashlib.md5(f"{case_name}{time.time()}".encode()).hexdigest()[:8]
        self.created     = datetime.now().isoformat()
        self.evidence    = []      # all evidence items
        self.theories    = []      # running theories
        self.timeline    = []      # chronological events
        self.suspects    = {}      # suspect profiles
        self.deductions  = []      # deduction chain
        self.verdict     = None    # final verdict
        self.notes       = []      # detective notes

    def add_evidence(self, etype, content, source="", metadata=None):
        """Add a piece of evidence."""
        item = {
            "id":       len(self.evidence) + 1,
            "type":     etype,   # image|audio|document|text|testimony|physical
            "content":  content if etype != "image" else "[image data]",
            "raw":      content if etype == "image" else None,
            "source":   source,
            "metadata": metadata or {},
            "added":    datetime.now().isoformat(),
            "analysis": None,
        }
        self.evidence.append(item)
        return item["id"]

    def update_analysis(self, evidence_id, analysis):
        for e in self.evidence:
            if e["id"] == evidence_id:
                e["analysis"] = analysis
                break

    def to_dict(self):
        return {
            "case_name":  self.case_name,
            "case_id":    self.case_id,
            "created":    self.created,
            "evidence":   [{k:v for k,v in e.items() if k != "raw"}
                          for e in self.evidence],
            "theories":   self.theories,
            "timeline":   self.timeline,
            "suspects":   self.suspects,
            "deductions": self.deductions,
            "verdict":    self.verdict,
            "notes":      self.notes,
        }

    def save(self):
        fp = CASES_DIR / f"{self.case_id}_{self.case_name[:20].replace(' ','_')}.json"
        fp.write_text(json.dumps(self.to_dict(), indent=2, default=str))
        return fp

    def evidence_summary(self):
        """Text summary of all evidence for AI context."""
        lines = [f"CASE: {self.case_name}\n"]
        for e in self.evidence:
            lines.append(f"Evidence #{e['id']} [{e['type'].upper()}] from {e['source']}:")
            if e["type"] != "image":
                content = str(e["content"])[:500]
                lines.append(f"  {content}")
            if e["analysis"]:
                lines.append(f"  Analysis: {str(e['analysis'])[:300]}")
            lines.append("")
        if self.timeline:
            lines.append("TIMELINE:")
            for t in self.timeline:
                lines.append(f"  {t['time']}: {t['event']}")
        if self.suspects:
            lines.append("\nSUSPECTS:")
            for name, profile in self.suspects.items():
                lines.append(f"  {name}: {json.dumps(profile)[:200]}")
        return "\n".join(lines)

# ══════════════════════════════════════════════════════════════════════════════
# 👁️ VISION ANALYST
# ══════════════════════════════════════════════════════════════════════════════

VISION_PROMPT = """Analyze this image as a detective examining evidence.

Case context: {context}

Provide a systematic forensic analysis:

## IMMEDIATE OBSERVATIONS
List everything visible systematically (foreground → background → details)

## CRITICAL DETAILS
- Text, numbers, timestamps visible?
- Faces, identifiable features?
- Objects of interest?
- Lighting conditions and shadows (time of day clues)?
- Reflections (what do they reveal)?
- Background environment clues?

## WHAT IS MISSING OR UNUSUAL
- What would you expect to see but don't?
- What seems out of place?
- Any signs of staging or manipulation?

## CONTRADICTIONS WITH OTHER EVIDENCE
{contradictions}

## DEDUCTIONS FROM THIS IMAGE
Specific conclusions I can draw with confidence levels

## QUESTIONS THIS RAISES
What does this image make me want to investigate next?"""

def analyze_image(image_data, case_file, source="unknown"):
    """Analyze an image as forensic evidence."""
    context        = case_file.evidence_summary() if case_file.evidence else "No prior evidence."
    contradictions = "No prior evidence to compare against." if not case_file.evidence \
                     else "Compare against existing case evidence above."

    prompt = VISION_PROMPT.format(
        context        = context[:1000],
        contradictions = contradictions,
    )

    rprint(f"  [cyan]👁️  Analyzing image...[/cyan]")
    analysis = ai_vision(prompt, [image_data])
    return analysis

def load_image_as_b64(path):
    """Load image file as base64."""
    path = Path(path)
    if not path.exists():
        return None, "File not found"

    ext = path.suffix.lower()
    media_types = {
        ".jpg":".jpeg", ".jpeg":"image/jpeg",
        ".png":"image/png", ".gif":"image/gif",
        ".webp":"image/webp"
    }
    media_type = media_types.get(ext, "image/jpeg")
    if media_type.startswith("."):
        media_type = "image/jpeg"

    try:
        with open(path,"rb") as f:
            data = base64.standard_b64encode(f.read()).decode()
        return {
            "type": "image",
            "source": {
                "type":       "base64",
                "media_type": media_type,
                "data":       data,
            }
        }, None
    except Exception as e:
        return None, str(e)

# ══════════════════════════════════════════════════════════════════════════════
# 📄 DOCUMENT ANALYST
# ══════════════════════════════════════════════════════════════════════════════

DOCUMENT_PROMPT = """Analyze this document as forensic evidence.

Case context:
{context}

Document content:
{document}

Provide forensic document analysis:

## CONTENT SUMMARY
What does this document claim/state?

## LINGUISTIC ANALYSIS
- Writing style, vocabulary, tone
- Emotional state of author
- Signs of stress, deception, or unusual phrasing
- Specific word choices that stand out

## FACTUAL CLAIMS
List all specific factual claims made (names, dates, places, events)

## CONTRADICTIONS & RED FLAGS
- Internal contradictions within document
- Contradictions with other case evidence
- Claims that seem unlikely or impossible
- What is conspicuously NOT mentioned?

## DECEPTION INDICATORS
Based on linguistic forensics, assess truthfulness of key claims

## DEDUCTIONS
What does this document tell us with confidence levels?

## QUESTIONS RAISED
What needs to be verified or investigated?"""

def analyze_document(text, case_file, source="unknown"):
    """Analyze a text document as forensic evidence."""
    context = case_file.evidence_summary() if case_file.evidence else "No prior evidence."

    prompt = DOCUMENT_PROMPT.format(
        context  = context[:800],
        document = text[:3000],
    )

    rprint(f"  [cyan]📄 Analyzing document...[/cyan]")
    return ai_call(prompt)

# ══════════════════════════════════════════════════════════════════════════════
# 🔊 AUDIO ANALYST
# ══════════════════════════════════════════════════════════════════════════════

AUDIO_PROMPT = """Analyze this audio transcript as forensic evidence.

Case context:
{context}

Audio transcript/description:
{audio_text}

Provide forensic audio analysis:

## SPEAKER ANALYSIS
- How many speakers? Can they be identified?
- Emotional state (stress, fear, confidence, deception indicators)
- Speech patterns — hesitations, corrections, unusual phrasing

## CONTENT ANALYSIS
- What is being said? What is being AVOIDED?
- Specific claims made
- Contradictions within the conversation

## BACKGROUND ENVIRONMENT
- Any background sounds mentioned/described?
- What do they suggest about location/time?

## DECEPTION INDICATORS
Voice stress analysis, topic avoidance, over-explanation

## DEDUCTIONS
What this audio tells us with confidence levels

## CONTRADICTIONS
With other case evidence"""

def analyze_audio(transcript_or_description, case_file, source="unknown"):
    """Analyze audio evidence (transcript or description)."""
    context = case_file.evidence_summary() if case_file.evidence else "No prior evidence."

    prompt = AUDIO_PROMPT.format(
        context    = context[:800],
        audio_text = transcript_or_description[:2000],
    )

    rprint(f"  [cyan]🔊 Analyzing audio...[/cyan]")
    return ai_call(prompt)

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 DEDUCTION ENGINE — the Batman core
# ══════════════════════════════════════════════════════════════════════════════

DEDUCTION_PROMPT = """You are the Batcomputer. Analyze ALL evidence and build competing theories.

{evidence_summary}

Generate a comprehensive deduction report:

## ESTABLISHED FACTS
Facts we know with high confidence from evidence (list each with source)

## CONFIRMED CONTRADICTIONS
Direct conflicts between pieces of evidence — someone or something is wrong

## THEORY ALPHA (Most Likely)
**Probability: X%**
Full narrative explaining all evidence
Reasoning chain: [evidence 1] → [deduction] → [evidence 2] → [conclusion]
Evidence supporting this: ...
Evidence against this: ...
What would confirm this theory: ...

## THEORY BETA (Alternative)
**Probability: X%**
[same structure]

## THEORY GAMMA (Dark Horse)
**Probability: X%**
[same structure]

## KEY UNKNOWNS
Critical gaps in evidence that could change everything

## NEXT INVESTIGATION STEPS
Ranked by importance — what to find next

## DEDUCTION CHAIN SUMMARY
The logical path from evidence to most likely conclusion, step by step"""

def run_deduction_engine(case_file):
    """Run full deduction across all case evidence."""
    if not case_file.evidence:
        return "No evidence to analyze. Add evidence first."

    rprint(f"\n  [magenta]🧠 Batcomputer running deduction engine...[/magenta]")
    rprint(f"  [dim]Analyzing {len(case_file.evidence)} pieces of evidence...[/dim]")

    summary  = case_file.evidence_summary()
    analysis = ai_call(DEDUCTION_PROMPT.format(evidence_summary=summary), max_tokens=3000)

    # Parse theories into structured format
    theories = ai_json(
        f"Based on this detective analysis:\n{analysis[:2000]}\n\n"
        "Extract the theories as JSON. Reply ONLY with JSON:\n"
        '{"theories":[{"name":"Theory Alpha","probability":75,"summary":"brief summary",'
        '"key_evidence":["evidence 1"],"verdict":"likely|possible|unlikely"}]}',
        "Reply ONLY with valid JSON.",
        600
    )

    if theories:
        case_file.theories = theories.get("theories",[])

    case_file.deductions.append({
        "ts":       datetime.now().isoformat(),
        "analysis": analysis,
        "theories": case_file.theories,
    })

    return analysis

# ══════════════════════════════════════════════════════════════════════════════
# 🎭 PROFILER
# ══════════════════════════════════════════════════════════════════════════════

PROFILER_PROMPT = """Build a psychological and behavioral profile of {subject}.

Case evidence:
{evidence_summary}

Specific information about {subject}:
{subject_info}

Build a comprehensive profile:

## BEHAVIORAL PROFILE
- Personality traits (with evidence)
- Decision-making patterns
- Stress responses
- Known behavioral patterns

## PSYCHOLOGICAL INDICATORS
- Motivation assessment
- Risk tolerance
- Potential deceptive behaviors
- Emotional state during relevant events

## OPPORTUNITY ANALYSIS
- Access and means
- Motive assessment (ranked by strength)
- Capability assessment

## CONSISTENCY CHECK
Does {subject}'s behavior match their profile?
What inconsistencies exist?

## THREAT ASSESSMENT
Level: LOW / MEDIUM / HIGH / CRITICAL
Reasoning: ...

## LIKELIHOOD OF INVOLVEMENT
Probability: X%
Based on: ..."""

def build_profile(subject_name, subject_info, case_file):
    """Build psychological profile of a suspect."""
    rprint(f"  [cyan]🎭 Building profile for {subject_name}...[/cyan]")

    prompt = PROFILER_PROMPT.format(
        subject          = subject_name,
        evidence_summary = case_file.evidence_summary()[:1500],
        subject_info     = subject_info[:1000],
    )

    profile_text = ai_call(prompt, max_tokens=2000)

    # Extract structured data
    profile_data = ai_json(
        f"Extract key profile data from:\n{profile_text[:1500]}\n\n"
        "Reply ONLY with JSON:\n"
        '{"traits":["trait1"],"motive_strength":"high|medium|low",'
        '"opportunity":"high|medium|low","involvement_probability":50,'
        '"threat_level":"low|medium|high|critical","key_red_flags":["flag1"]}',
        "Reply ONLY with JSON.", 400
    )

    case_file.suspects[subject_name] = {
        "profile":     profile_text,
        "data":        profile_data or {},
        "added":       datetime.now().isoformat(),
    }

    return profile_text

# ══════════════════════════════════════════════════════════════════════════════
# 🗺️ TIMELINE BUILDER
# ══════════════════════════════════════════════════════════════════════════════

TIMELINE_PROMPT = """Build a forensic timeline from all case evidence.

{evidence_summary}

Create a comprehensive timeline:

## CONFIRMED TIMELINE
Events we can place with high confidence (include evidence source and confidence %)

Format each entry as:
[TIME/DATE] — [EVENT] — [Source: evidence #X] — [Confidence: X%]

## DISPUTED TIMELINE
Events where timing is contested or unclear

## IMPOSSIBLE TIMINGS
Events that CANNOT both be true given timing constraints
(This is critical — impossibilities expose lies)

## TIMELINE GAPS
Periods of time unaccounted for — especially for key suspects

## KEY WINDOWS
Critical time windows where the core event must have occurred

## TIMELINE VERDICT
Based on timing alone, what can we conclude?"""

def build_timeline(case_file, additional_info=""):
    """Build chronological timeline from all evidence."""
    rprint(f"  [cyan]🗺️  Building timeline...[/cyan]")

    summary = case_file.evidence_summary()
    if additional_info:
        summary += f"\n\nAdditional timeline info:\n{additional_info}"

    timeline_text = ai_call(
        TIMELINE_PROMPT.format(evidence_summary=summary[:2000]),
        max_tokens=2000
    )

    # Extract events
    events = ai_json(
        f"Extract timeline events from:\n{timeline_text[:1500]}\n\n"
        "Reply ONLY with JSON:\n"
        '{"events":[{"time":"timestamp","event":"description",'
        '"confidence":90,"source":"evidence #1","type":"confirmed|disputed|impossible"}]}',
        "Reply ONLY with JSON.", 600
    )

    if events:
        case_file.timeline = events.get("events",[])

    return timeline_text

# ══════════════════════════════════════════════════════════════════════════════
# 💬 INTERROGATION MODE
# ══════════════════════════════════════════════════════════════════════════════

INTERROGATION_PROMPT = """You are conducting an interrogation analysis.

Case evidence:
{evidence_summary}

Subject being analyzed: {subject}

Statement/Answer given:
{statement}

Analyze this statement forensically:

## TRUTHFULNESS ASSESSMENT
Probability statement is truthful: X%

## LINGUISTIC RED FLAGS
Specific phrases, word choices, or patterns that indicate deception

## CONSISTENCY CHECK
Does this statement align with:
- Physical evidence? (Y/N + explanation)
- Other testimonies? (Y/N + explanation)
- Timeline? (Y/N + explanation)
- Subject's profile? (Y/N + explanation)

## WHAT THEY'RE HIDING
Based on what was NOT said, what are they concealing?

## FOLLOW-UP QUESTIONS
The 3 most important questions to ask next based on this statement

## VERDICT
Truthful / Partially truthful / Deceptive / Unknown
Confidence: X%"""

def analyze_statement(subject, statement, case_file):
    """Analyze a suspect's statement for truthfulness."""
    rprint(f"  [cyan]💬 Analyzing statement from {subject}...[/cyan]")

    prompt = INTERROGATION_PROMPT.format(
        evidence_summary = case_file.evidence_summary()[:1200],
        subject          = subject,
        statement        = statement[:1500],
    )

    return ai_call(prompt, max_tokens=1500)

# ══════════════════════════════════════════════════════════════════════════════
# ⚖️ VERDICT ENGINE
# ══════════════════════════════════════════════════════════════════════════════

VERDICT_PROMPT = """FINAL CASE ANALYSIS — Deliver your verdict.

{evidence_summary}

Previous deductions:
{deductions}

Deliver the complete final verdict:

## THE VERDICT
State clearly: What happened? Who did what? Why?

## CONFIDENCE LEVEL
Overall case confidence: X%
(100% = absolute certainty, 0% = total mystery)

## THE COMPLETE NARRATIVE
Tell the full story of what happened, incorporating all evidence

## EVIDENCE CHAIN
The unbroken logical chain from evidence to conclusion:
Evidence A → implies B → combined with C → proves D → therefore VERDICT

## REMAINING DOUBTS
What could still be wrong? What alternative still has merit?

## WHAT WOULD CHANGE THE VERDICT
The single piece of evidence that would overturn this conclusion

## RECOMMENDED ACTIONS
What should happen next based on this conclusion?"""

def deliver_verdict(case_file):
    """Deliver final case verdict."""
    if len(case_file.evidence) < 2:
        return "Insufficient evidence for a verdict. Add more evidence first."

    rprint(f"\n  [red bold]⚖️  Batcomputer delivering verdict...[/red bold]")

    deductions_text = "\n".join(
        d["analysis"][:500] for d in case_file.deductions[-2:]
    ) if case_file.deductions else "No prior deductions."

    verdict_text = ai_call(
        VERDICT_PROMPT.format(
            evidence_summary = case_file.evidence_summary()[:2000],
            deductions       = deductions_text[:800],
        ),
        max_tokens=2500
    )

    # Structured verdict
    verdict_data = ai_json(
        f"Extract verdict data from:\n{verdict_text[:1500]}\n\n"
        "Reply ONLY with JSON:\n"
        '{"conclusion":"what happened","confidence":75,"primary_suspect":"name or unknown",'
        '"motive":"motive or unknown","key_evidence":["evidence 1","evidence 2"],'
        '"certainty":"certain|probable|possible|unknown"}',
        "Reply ONLY with JSON.", 400
    )

    case_file.verdict = {
        "text":      verdict_text,
        "data":      verdict_data or {},
        "delivered": datetime.now().isoformat(),
    }

    return verdict_text

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API SERVER — for the Batcomputer UI
# ══════════════════════════════════════════════════════════════════════════════

def start_api_server(port=7337):
    """Start HTTP API server for the Batcomputer UI."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse, parse_qs
    import json

    # Active cases store
    cases = {}

    class DetectiveAPI(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def do_OPTIONS(self):
            self.send_response(200)
            self._cors()
            self.end_headers()

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

        def _read_body(self):
            n = int(self.headers.get("Content-Length",0))
            return json.loads(self.rfile.read(n)) if n else {}

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/cases":
                self._json({"cases":[c.to_dict() for c in cases.values()]})
            elif path.startswith("/api/case/"):
                cid = path.split("/")[-1]
                if cid in cases:
                    self._json(cases[cid].to_dict())
                else:
                    self._json({"error":"not found"},404)
            elif path == "/api/status":
                self._json({"status":"online","ai":AI_AVAILABLE,"cases":len(cases)})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._read_body()

            # New case
            if path == "/api/case/new":
                name = body.get("name","New Case")
                cf   = CaseFile(name)
                cases[cf.case_id] = cf
                self._json({"case_id":cf.case_id,"name":name})

            # Add evidence
            elif path == "/api/evidence/add":
                cid   = body.get("case_id")
                etype = body.get("type","text")
                content = body.get("content","")
                source  = body.get("source","manual")

                if cid not in cases:
                    self._json({"error":"case not found"},404); return

                cf  = cases[cid]
                eid = cf.add_evidence(etype, content, source)

                # Auto-analyze
                analysis = None
                if etype == "image" and content:
                    try:
                        img_data = {
                            "type":"image",
                            "source":{"type":"base64","media_type":"image/jpeg","data":content}
                        }
                        analysis = analyze_image(img_data, cf, source)
                    except Exception as e:
                        analysis = f"Analysis error: {e}"
                elif etype == "document":
                    analysis = analyze_document(content, cf, source)
                elif etype == "audio":
                    analysis = analyze_audio(content, cf, source)
                elif etype == "text":
                    analysis = analyze_document(content, cf, source)

                if analysis:
                    cf.update_analysis(eid, analysis)

                cf.save()
                self._json({"evidence_id":eid,"analysis":analysis})

            # Run deduction
            elif path == "/api/deduce":
                cid = body.get("case_id")
                if cid not in cases:
                    self._json({"error":"case not found"},404); return
                result = run_deduction_engine(cases[cid])
                cases[cid].save()
                self._json({"deduction":result,"theories":cases[cid].theories})

            # Build profile
            elif path == "/api/profile":
                cid     = body.get("case_id")
                subject = body.get("subject","Unknown")
                info    = body.get("info","")
                if cid not in cases:
                    self._json({"error":"case not found"},404); return
                result = build_profile(subject, info, cases[cid])
                cases[cid].save()
                self._json({"profile":result})

            # Timeline
            elif path == "/api/timeline":
                cid  = body.get("case_id")
                info = body.get("additional_info","")
                if cid not in cases:
                    self._json({"error":"case not found"},404); return
                result = build_timeline(cases[cid], info)
                cases[cid].save()
                self._json({"timeline":result,"events":cases[cid].timeline})

            # Interrogation
            elif path == "/api/interrogate":
                cid       = body.get("case_id")
                subject   = body.get("subject","Unknown")
                statement = body.get("statement","")
                if cid not in cases:
                    self._json({"error":"case not found"},404); return
                result = analyze_statement(subject, statement, cases[cid])
                cases[cid].save()
                self._json({"analysis":result})

            # Verdict
            elif path == "/api/verdict":
                cid = body.get("case_id")
                if cid not in cases:
                    self._json({"error":"case not found"},404); return
                result = deliver_verdict(cases[cid])
                cases[cid].save()
                self._json({"verdict":result,"data":cases[cid].verdict})

            # Quick analyze (no case)
            elif path == "/api/analyze":
                etype   = body.get("type","text")
                content = body.get("content","")
                context = body.get("context","")
                cf      = CaseFile("Quick Analysis")

                if context:
                    cf.add_evidence("text", context, "context")

                if etype == "image":
                    img = {"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":content}}
                    result = analyze_image(img, cf)
                elif etype == "document":
                    result = analyze_document(content, cf)
                elif etype == "audio":
                    result = analyze_audio(content, cf)
                else:
                    result = analyze_document(content, cf)

                self._json({"analysis":result})

            else:
                self._json({"error":"unknown endpoint"},404)

    server = HTTPServer(("0.0.0.0", port), DetectiveAPI)
    rprint(f"  [cyan]🦇 Batcomputer API online: http://localhost:{port}[/cyan]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# 🖥️ INTERACTIVE CONSOLE
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow bold]
  ██████╗ ███████╗████████╗███████╗ ██████╗████████╗██╗██╗   ██╗███████╗
  ██╔══██╗██╔════╝╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝██║██║   ██║██╔════╝
  ██║  ██║█████╗     ██║   █████╗  ██║        ██║   ██║██║   ██║█████╗
  ██║  ██║██╔══╝     ██║   ██╔══╝  ██║        ██║   ██║╚██╗ ██╔╝██╔══╝
  ██████╔╝███████╗   ██║   ███████╗╚██████╗   ██║   ██║ ╚████╔╝ ███████╗
  ╚═════╝ ╚══════╝   ╚═╝   ╚══════╝ ╚═════╝   ╚═╝   ╚═╝  ╚═══╝  ╚══════╝
[/yellow bold]
[bold]  🦇 The Batcomputer — AI Detective Engine[/bold]
[dim]  Vision · Audio · Documents · Deduction · Verdict[/dim]
"""

def interactive_console():
    rprint(BANNER)

    if not AI_AVAILABLE:
        rprint("[red]AI not available. Install: pip install anthropic[/red]")
        return

    cf = CaseFile()
    rprint(f"[dim]Case: {cf.case_name} | ID: {cf.case_id}[/dim]")
    rprint("[dim]Commands: new | image <path> | document <path> | audio <text> | "
           "testimony <name> | deduce | profile <name> | timeline | verdict | "
           "status | save | help[/dim]\n")

    while True:
        try:
            inp = console.input if RICH else input
            raw = inp("[yellow bold]🦇 detective >[/yellow bold] ").strip()
            if not raw: continue

            parts = raw.split(None, 1)
            cmd   = parts[0].lower()
            args  = parts[1] if len(parts)>1 else ""

            if cmd in ("exit","quit","q"):
                cf.save()
                rprint("[dim]Case saved. Goodbye.[/dim]")
                break

            elif cmd == "help":
                rprint("""
[bold]Commands:[/bold]
  [yellow]new[/yellow] <case name>          Start new case
  [yellow]image[/yellow] <path>             Analyze image file
  [yellow]document[/yellow] <path>          Analyze document file
  [yellow]audio[/yellow] <transcript>       Analyze audio transcript
  [yellow]testimony[/yellow] <name>         Add suspect testimony (multi-line)
  [yellow]text[/yellow] <evidence>          Add text evidence directly
  [yellow]deduce[/yellow]                   Run full deduction engine
  [yellow]profile[/yellow] <suspect name>   Build psychological profile
  [yellow]timeline[/yellow]                 Build case timeline
  [yellow]interrogate[/yellow] <name>       Analyze suspect statement
  [yellow]verdict[/yellow]                  Deliver final verdict
  [yellow]status[/yellow]                   Show case status
  [yellow]evidence[/yellow]                 List all evidence
  [yellow]save[/yellow]                     Save case file
""")

            elif cmd == "new":
                cf = CaseFile(args or "New Case")
                rprint(f"[green]New case: {cf.case_name} ({cf.case_id})[/green]")

            elif cmd == "image":
                path = args.strip().strip('"')
                img, err = load_image_as_b64(path)
                if err:
                    rprint(f"[red]Error: {err}[/red]")
                    continue
                eid      = cf.add_evidence("image", img, path)
                analysis = analyze_image(img, cf, path)
                cf.update_analysis(eid, analysis)
                rprint(f"\n[yellow bold]👁️  IMAGE ANALYSIS — Evidence #{eid}[/yellow bold]")
                rprint(analysis)
                cf.save()

            elif cmd == "document":
                path = Path(args.strip().strip('"'))
                if not path.exists():
                    rprint(f"[red]File not found: {path}[/red]"); continue
                text     = path.read_text(errors="ignore")
                eid      = cf.add_evidence("document", text, str(path))
                analysis = analyze_document(text, cf, str(path))
                cf.update_analysis(eid, analysis)
                rprint(f"\n[yellow bold]📄 DOCUMENT ANALYSIS — Evidence #{eid}[/yellow bold]")
                rprint(analysis)
                cf.save()

            elif cmd == "audio":
                if not args:
                    rprint("[dim]Enter audio transcript (or description of audio):[/dim]")
                    lines = []
                    while True:
                        try:
                            line = (console.input if RICH else input)("[dim]...[/dim] ")
                            if line.strip() == "END": break
                            lines.append(line)
                        except (KeyboardInterrupt, EOFError): break
                    args = "\n".join(lines)
                eid      = cf.add_evidence("audio", args, "audio input")
                analysis = analyze_audio(args, cf)
                cf.update_analysis(eid, analysis)
                rprint(f"\n[yellow bold]🔊 AUDIO ANALYSIS — Evidence #{eid}[/yellow bold]")
                rprint(analysis)
                cf.save()

            elif cmd in ("testimony","text"):
                if not args:
                    name = (console.input if RICH else input)("Subject name: ").strip()
                    rprint("[dim]Enter testimony (type END on new line to finish):[/dim]")
                    lines = []
                    while True:
                        try:
                            line = (console.input if RICH else input)("[dim]...[/dim] ")
                            if line.strip() == "END": break
                            lines.append(line)
                        except (KeyboardInterrupt, EOFError): break
                    args = f"{name}: " + "\n".join(lines)

                eid      = cf.add_evidence("testimony", args, "testimony")
                analysis = analyze_document(args, cf, "testimony")
                cf.update_analysis(eid, analysis)
                rprint(f"\n[yellow bold]💬 TESTIMONY ANALYSIS — Evidence #{eid}[/yellow bold]")
                rprint(analysis)
                cf.save()

            elif cmd == "deduce":
                result = run_deduction_engine(cf)
                rprint(f"\n[yellow bold]🧠 DEDUCTION ENGINE[/yellow bold]")
                rprint(result)
                cf.save()

            elif cmd == "profile":
                subject = args or (console.input if RICH else input)("Suspect name: ").strip()
                rprint(f"[dim]Enter known info about {subject} (Enter to skip):[/dim]")
                try:
                    info = (console.input if RICH else input)("[dim]info: [/dim] ").strip()
                except: info = ""
                result = build_profile(subject, info, cf)
                rprint(f"\n[yellow bold]🎭 PROFILE — {subject}[/yellow bold]")
                rprint(result)
                cf.save()

            elif cmd == "timeline":
                result = build_timeline(cf)
                rprint(f"\n[yellow bold]🗺️  CASE TIMELINE[/yellow bold]")
                rprint(result)
                cf.save()

            elif cmd == "interrogate":
                subject = args or (console.input if RICH else input)("Subject: ").strip()
                rprint(f"[dim]Enter {subject}'s statement:[/dim]")
                lines = []
                while True:
                    try:
                        line = (console.input if RICH else input)("[dim]...[/dim] ")
                        if line.strip() == "END": break
                        lines.append(line)
                    except (KeyboardInterrupt, EOFError): break
                statement = "\n".join(lines)
                result    = analyze_statement(subject, statement, cf)
                rprint(f"\n[yellow bold]💬 INTERROGATION ANALYSIS — {subject}[/yellow bold]")
                rprint(result)
                cf.save()

            elif cmd == "verdict":
                result = deliver_verdict(cf)
                rprint(f"\n[red bold]⚖️  FINAL VERDICT[/red bold]")
                rprint(Panel(result, border_style="red", title="🦇 BATCOMPUTER VERDICT"))
                cf.save()

            elif cmd == "status":
                rprint(f"\n[bold]Case:[/bold] {cf.case_name} ({cf.case_id})")
                rprint(f"[bold]Evidence:[/bold] {len(cf.evidence)} items")
                rprint(f"[bold]Theories:[/bold] {len(cf.theories)}")
                rprint(f"[bold]Suspects:[/bold] {list(cf.suspects.keys())}")
                rprint(f"[bold]Deductions:[/bold] {len(cf.deductions)}")
                rprint(f"[bold]Verdict:[/bold] {'Delivered' if cf.verdict else 'Pending'}")

            elif cmd == "evidence":
                for e in cf.evidence:
                    color = {"image":"cyan","document":"green","audio":"yellow",
                             "testimony":"magenta","text":"white"}.get(e["type"],"white")
                    rprint(f"  [bold]#{e['id']}[/bold] [{color}]{e['type']}[/{color}]  "
                           f"[dim]{e['source'][:40]}[/dim]  "
                           f"{'✅ analyzed' if e['analysis'] else '⏳ pending'}")

            elif cmd == "save":
                fp = cf.save()
                rprint(f"[green]Saved: {fp}[/green]")

            else:
                # Treat as general detective question
                context = cf.evidence_summary()
                answer  = ai_call(
                    f"Case context:\n{context[:1000]}\n\nQuestion: {raw}",
                    max_tokens=800
                )
                rprint(f"\n[yellow]🦇[/yellow] {answer}")

        except (KeyboardInterrupt, EOFError):
            cf.save()
            rprint("\n[dim]Case saved. Stay vigilant.[/dim]")
            break

def main():
    if "--server" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7337
        rprint(BANNER)
        rprint(f"[yellow bold]🦇 Starting Batcomputer API server on port {port}...[/yellow bold]")
        start_api_server(port)
        return

    if "--case" in sys.argv:
        idx  = sys.argv.index("--case")
        name = sys.argv[idx+1]
        cf   = CaseFile(name)
        interactive_console()
        return

    interactive_console()

if __name__ == "__main__":
    main()
