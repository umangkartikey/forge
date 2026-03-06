#!/usr/bin/env python3
"""
FORGE NEXUS — The Unified Brain
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

One command. Every tool. Everything talks to everything.

forge_investigate finds the target
  → feeds forge_sherlock (deduction chains)
    → feeds forge_detective (case file + verdict)
      → forge_monitor watches 24/7
        → forge_learn learns from everything
          → final dossier: OSINT + reasoning + verdict

The tools that existed in isolation now form one brain.

Usage:
  python forge_nexus.py                          # interactive hub
  python forge_nexus.py --investigate github.com # full pipeline
  python forge_nexus.py --case "suspicious user" # open case
  python forge_nexus.py --server                 # API for NEXUS UI
  python forge_nexus.py --status                 # tool health check
  python forge_nexus.py --morning-brief          # daily intel summary
"""

import sys, os, re, json, time, hashlib, threading, subprocess
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ── Rich ──────────────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.tree import Tree
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
    from rich.live import Live
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

    def ai_call(prompt, system="", max_tokens=2000):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or NEXUS_SYSTEM,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text

    def ai_json(prompt, system="", max_tokens=1000):
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
    def ai_call(p,s="",m=2000): return "Install anthropic."
    def ai_json(p,s="",m=1000): return None

NEXUS_SYSTEM = """You are FORGE NEXUS — the unified intelligence coordinator.
You receive findings from multiple specialized tools and synthesize them
into coherent, actionable intelligence.

Your role:
- Connect findings across tools (OSINT + Deduction + Security + Detection)
- Identify patterns that no single tool would see alone
- Prioritize what matters most
- Route tasks to the right tool
- Deliver clear, actionable conclusions

You are clinical, precise, and comprehensive."""

# ── Paths ─────────────────────────────────────────────────────────────────────
NEXUS_DIR  = Path("forge_nexus")
CASES_DIR  = NEXUS_DIR / "cases"
BRIEFS_DIR = NEXUS_DIR / "briefs"
NEXUS_DIR.mkdir(exist_ok=True)
CASES_DIR.mkdir(exist_ok=True)
BRIEFS_DIR.mkdir(exist_ok=True)

# ── Tool registry ─────────────────────────────────────────────────────────────
TOOLS = {
    "investigate": {
        "file":   "forge_investigate.py",
        "desc":   "OSINT — public data intelligence gathering",
        "port":   None,
        "status": "unknown",
        "color":  "cyan",
    },
    "sherlock": {
        "file":   "forge_sherlock.py",
        "desc":   "Mind Palace — deduction chains + reasoning",
        "port":   7338,
        "status": "unknown",
        "color":  "yellow",
    },
    "detective": {
        "file":   "forge_detective.py",
        "desc":   "Batcomputer — case file + verdict engine",
        "port":   7337,
        "status": "unknown",
        "color":  "red",
    },
    "monitor": {
        "file":   "forge_monitor.py",
        "desc":   "Watchdog — 24/7 production monitoring",
        "port":   None,
        "status": "unknown",
        "color":  "green",
    },
    "pentest": {
        "file":   "forge_llm_pentest.py",
        "desc":   "LLM Pentester — OWASP LLM Top 10 audit",
        "port":   None,
        "status": "unknown",
        "color":  "magenta",
    },
    "honeypot": {
        "file":   "forge_honeypot.py",
        "desc":   "Honeypot — catches attackers",
        "port":   8888,
        "status": "unknown",
        "color":  "orange1",
    },
}

def check_tool_health():
    """Check which FORGE tools are available."""
    base = Path(__file__).parent
    for name, tool in TOOLS.items():
        fp = base / tool["file"]
        tool["available"] = fp.exists()
        tool["status"]    = "ready" if fp.exists() else "missing"
    return TOOLS

# ══════════════════════════════════════════════════════════════════════════════
# 📋 NEXUS CASE — unified case object
# ══════════════════════════════════════════════════════════════════════════════

class NexusCase:
    def __init__(self, name, target="", target_type=""):
        self.case_id     = hashlib.md5(f"{name}{time.time()}".encode()).hexdigest()[:8]
        self.name        = name
        self.target      = target
        self.target_type = target_type
        self.created     = datetime.now().isoformat()
        self.status      = "active"

        # Data from each tool
        self.osint       = {}      # from forge_investigate
        self.observations= []      # from forge_sherlock
        self.deductions  = []      # from forge_sherlock chains
        self.case_file   = []      # from forge_detective
        self.theories    = []      # from forge_detective
        self.verdict     = None    # from forge_detective
        self.alerts      = []      # from forge_monitor
        self.pentest     = {}      # from forge_llm_pentest
        self.timeline    = []      # synthesized across all tools
        self.suspects    = {}      # from any tool
        self.connections = []      # cross-tool connections found by AI

        # Pipeline state
        self.pipeline_log= []
        self.current_step= ""
        self.confidence  = 0

    def log(self, tool, message, level="info"):
        entry = {
            "ts":      datetime.now().isoformat(),
            "tool":    tool,
            "message": message,
            "level":   level,
        }
        self.pipeline_log.append(entry)
        color = {"info":"dim","success":"green","warning":"yellow","error":"red"}.get(level,"dim")
        rprint(f"  [{color}][{tool.upper()}][/{color}] {message}")

    def add_timeline_event(self, time_str, event, source, confidence=80, etype="confirmed"):
        self.timeline.append({
            "time":       time_str,
            "event":      event,
            "source":     source,
            "confidence": confidence,
            "type":       etype,
        })
        self.timeline.sort(key=lambda x: x.get("time",""))

    def to_dict(self):
        return {
            "case_id":     self.case_id,
            "name":        self.name,
            "target":      self.target,
            "target_type": self.target_type,
            "created":     self.created,
            "status":      self.status,
            "osint":       self.osint,
            "observations":self.observations,
            "deductions":  self.deductions,
            "theories":    self.theories,
            "verdict":     self.verdict,
            "alerts":      self.alerts,
            "timeline":    self.timeline,
            "suspects":    self.suspects,
            "connections": self.connections,
            "confidence":  self.confidence,
            "pipeline_log":self.pipeline_log[-20:],
        }

    def save(self):
        fp = CASES_DIR / f"{self.case_id}_{self.name[:20].replace(' ','_')}.json"
        fp.write_text(json.dumps(self.to_dict(), indent=2, default=str))
        return fp

# ══════════════════════════════════════════════════════════════════════════════
# 🔍 STEP 1 — OSINT (forge_investigate)
# ══════════════════════════════════════════════════════════════════════════════

def run_osint(case, verbose=True):
    """Run forge_investigate on the target, feed results into case."""
    case.log("investigate", f"Starting OSINT on {case.target}...")
    case.current_step = "osint"

    try:
        from forge_investigate import run_investigation, detect_target_type
        target_type = case.target_type or detect_target_type(case.target)
        findings, dossier, relationships = run_investigation(
            case.target, target_type, verbose=False
        )
        case.osint = {
            "findings":      {c:{k:v["value"] for k,v in items.items()}
                             for c,items in findings.items()},
            "dossier":       dossier,
            "relationships": relationships,
            "target_type":   target_type,
        }

        # Extract timeline events from OSINT
        reg = findings.get("registration",{})
        if "registered" in reg:
            case.add_timeline_event(
                reg["registered"]["value"], "Domain registered",
                "OSINT/WHOIS", 90, "confirmed"
            )

        # Extract suspects/entities from relationships
        if relationships:
            for entity in relationships.get("entities",[])[:5]:
                name = entity.get("name","")
                if name:
                    case.suspects[name] = {
                        "type":         entity.get("type",""),
                        "relationship": entity.get("relationship",""),
                        "confidence":   entity.get("confidence",50),
                        "source":       "OSINT",
                    }

        count = sum(len(v) for v in findings.values())
        case.log("investigate", f"Found {count} intelligence items across {len(findings)} categories", "success")
        return True

    except ImportError:
        case.log("investigate", "forge_investigate.py not found — skipping OSINT", "warning")
        return False
    except Exception as e:
        case.log("investigate", f"OSINT error: {str(e)[:80]}", "error")
        return False

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 STEP 2 — DEDUCTION (forge_sherlock)
# ══════════════════════════════════════════════════════════════════════════════

SHERLOCK_FEED_PROMPT = """You are Sherlock Holmes. OSINT data has been gathered on a target.
Apply your observation method to this intelligence.

Target: {target}
OSINT findings: {findings}

Extract your 5 most significant observations and build deduction chains.
Focus on: anomalies, suspicious patterns, hidden connections, what is MISSING.

Format each as:
OBSERVATION: [fact]
  → INFERENCE: [what this implies]
    → CONCLUSION: [deduction] [X% confidence]"""

def run_sherlock(case, verbose=True):
    """Feed OSINT into Sherlock's reasoning engine."""
    case.log("sherlock", "Feeding OSINT into Mind Palace...")
    case.current_step = "sherlock"

    if not case.osint:
        case.log("sherlock", "No OSINT data — running observations on target name only", "warning")
        input_text = f"Target: {case.target}\nType: {case.target_type}"
    else:
        findings_flat = {}
        for cat, items in case.osint.get("findings",{}).items():
            findings_flat[cat] = items
        input_text = json.dumps(findings_flat, default=str)[:3000]

    try:
        # Try direct import first
        try:
            from forge_sherlock import observe, build_chains, palace_remember
            obs_result, structured = observe(
                input_text, case.case_id, context=f"Target: {case.target}"
            )
            case.observations.append(obs_result)

            chains_result = build_chains(obs_result[:2000], input_text[:500], case.case_id)
            case.deductions.append(chains_result)

            if structured:
                for obs in structured:
                    palace_remember(
                        case.case_id,
                        obs.get("type","general"),
                        obs.get("observation",""),
                        obs.get("inference",""),
                        obs.get("confidence",70),
                    )
            case.log("sherlock", f"Built {len(structured or [])} observation chains", "success")
            return True

        except ImportError:
            pass

        # Fallback: direct AI call
        if AI_AVAILABLE:
            result = ai_call(
                SHERLOCK_FEED_PROMPT.format(
                    target   = case.target,
                    findings = input_text[:2000]
                ),
                "You are Sherlock Holmes. Show every deduction chain explicitly."
            )
            case.observations.append(result)
            case.deductions.append(result)
            case.log("sherlock", "Deduction chains built via direct AI", "success")
            return True

    except Exception as e:
        case.log("sherlock", f"Sherlock error: {str(e)[:80]}", "error")

    return False

# ══════════════════════════════════════════════════════════════════════════════
# 🦇 STEP 3 — DETECTIVE (forge_detective)
# ══════════════════════════════════════════════════════════════════════════════

DETECTIVE_FEED_PROMPT = """You are the world's greatest AI detective.

All intelligence gathered on target: {target}

OSINT data:
{osint}

Sherlock's deductions:
{deductions}

Build:
1. Three ranked theories (probability %)
2. The verdict — most likely conclusion
3. What to investigate next

Be specific. Reference the actual data."""

def run_detective(case, verbose=True):
    """Build case file and deliver verdict from all prior data."""
    case.log("detective", "Building case file and running verdict engine...")
    case.current_step = "detective"

    all_evidence = []
    if case.osint.get("dossier"):
        all_evidence.append(f"OSINT DOSSIER:\n{case.osint['dossier'][:800]}")
    if case.observations:
        all_evidence.append(f"SHERLOCK OBSERVATIONS:\n{case.observations[-1][:800]}")
    if case.deductions:
        all_evidence.append(f"DEDUCTION CHAINS:\n{case.deductions[-1][:600]}")

    combined = "\n\n".join(all_evidence)

    try:
        try:
            from forge_detective import (CaseFile, analyze_document,
                                         run_deduction_engine, deliver_verdict)
            cf = CaseFile(f"NEXUS: {case.name}")
            cf.add_evidence("text", combined[:2000], "nexus_pipeline")
            deduction = run_deduction_engine(cf)
            verdict   = deliver_verdict(cf)
            case.theories = cf.theories
            case.verdict  = {"text": verdict, "theories": cf.theories}
            case.log("detective", f"Verdict delivered. {len(cf.theories)} theories ranked.", "success")
            return True

        except ImportError:
            pass

        # Fallback: direct AI
        if AI_AVAILABLE:
            result = ai_call(
                DETECTIVE_FEED_PROMPT.format(
                    target     = case.target,
                    osint      = case.osint.get("dossier","No OSINT")[:1000],
                    deductions = "\n".join(case.deductions)[:800],
                ),
                max_tokens=2000
            )
            theories = ai_json(
                f"Extract theories from:\n{result[:1500]}\n\n"
                'JSON: {"theories":[{"name":"Theory A","probability":70,"summary":"brief"}]}',
                "Reply ONLY with JSON.", 300
            )
            case.theories = (theories or {}).get("theories", [])
            case.verdict  = {"text": result, "theories": case.theories}
            case.log("detective", "Case verdict delivered via direct AI", "success")
            return True

    except Exception as e:
        case.log("detective", f"Detective error: {str(e)[:80]}", "error")

    return False

# ══════════════════════════════════════════════════════════════════════════════
# 🔗 STEP 4 — NEXUS SYNTHESIS (the magic step)
# ══════════════════════════════════════════════════════════════════════════════

SYNTHESIS_PROMPT = """You are FORGE NEXUS — the unified intelligence brain.

Multiple specialized tools have analyzed this target.
Your job: find what NO SINGLE TOOL could see alone.

Target: {target}

OSINT findings (forge_investigate):
{osint_summary}

Sherlock's deductions (forge_sherlock):
{sherlock_summary}

Detective verdict (forge_detective):
{detective_summary}

## CROSS-TOOL CONNECTIONS
Facts from different tools that connect to reveal something bigger.
Format: "[OSINT: X] + [SHERLOCK: Y] = [NEW INSIGHT Z]"

## WHAT THE TOOLS MISSED INDIVIDUALLY
Intelligence that only emerges when you combine all sources.

## UNIFIED THREAT/RISK ASSESSMENT
Scale 1-10. Evidence from each tool that contributes.

## THE COMPLETE PICTURE
The full narrative that emerges from combining all tools.
What this target actually is, does, and represents.

## PRIORITY ACTIONS
Ranked list — what to do next based on all intelligence combined.

## CONFIDENCE SCORE
Overall confidence in this assessment: X%
What single piece of information would change everything."""

def run_synthesis(case, verbose=True):
    """The magic step — AI finds cross-tool connections."""
    case.log("nexus", "Running cross-tool synthesis — finding connections...")
    case.current_step = "synthesis"

    if not AI_AVAILABLE:
        case.log("nexus", "AI not available for synthesis", "warning")
        return False

    osint_s    = json.dumps(case.osint.get("findings",{}), default=str)[:1200]
    sherlock_s = "\n".join(case.observations)[:800]
    detective_s= case.verdict.get("text","")[:800] if case.verdict else "No verdict yet."

    result = ai_call(
        SYNTHESIS_PROMPT.format(
            target            = case.target,
            osint_summary     = osint_s,
            sherlock_summary  = sherlock_s,
            detective_summary = detective_s,
        ),
        max_tokens=2500
    )

    # Extract connections
    connections = ai_json(
        f"From this synthesis:\n{result[:1500]}\n\n"
        'Extract cross-tool connections as JSON:\n'
        '{"connections":[{"tool_a":"investigate","tool_b":"sherlock","finding_a":"X","finding_b":"Y","insight":"Z","significance":"high|medium|low"}],'
        '"overall_confidence":75,"risk_level":"high|medium|low","priority_action":"do this first"}',
        "Reply ONLY with JSON.", 500
    )

    case.connections = (connections or {}).get("connections", [])
    case.confidence  = (connections or {}).get("overall_confidence", 0)

    # Build unified timeline from all sources
    _build_unified_timeline(case, result)

    case.log("nexus", f"Synthesis complete. {len(case.connections)} cross-tool connections found.", "success")
    case.log("nexus", f"Overall confidence: {case.confidence}%", "success")

    return result

def _build_unified_timeline(case, synthesis_text):
    """Extract and merge timeline events from all tools."""
    timeline_data = ai_json(
        f"Extract timeline events from:\n{synthesis_text[:1500]}\n\n"
        'JSON: {"events":[{"time":"YYYY-MM-DD or HH:MM or relative","event":"what happened",'
        '"source":"tool name","confidence":80,"type":"confirmed|probable|inferred"}]}',
        "Reply ONLY with JSON.", 400
    )
    if timeline_data:
        for ev in timeline_data.get("events",[]):
            case.add_timeline_event(
                ev.get("time","unknown"),
                ev.get("event",""),
                ev.get("source","nexus"),
                ev.get("confidence",70),
                ev.get("type","inferred"),
            )

# ══════════════════════════════════════════════════════════════════════════════
# 📊 FINAL DOSSIER
# ══════════════════════════════════════════════════════════════════════════════

DOSSIER_PROMPT = """Generate the complete FORGE NEXUS intelligence dossier.

Case: {case_name}
Target: {target}
Date: {date}

All intelligence:
{all_intel}

Write a professional intelligence dossier:

# FORGE NEXUS INTELLIGENCE DOSSIER
## EXECUTIVE SUMMARY (4-5 sentences — who/what/why it matters)

## TARGET PROFILE
Key facts with sources.

## THREAT ASSESSMENT
Risk level: CRITICAL / HIGH / MEDIUM / LOW / MINIMAL
Evidence supporting this assessment.

## KEY FINDINGS
The 5-7 most important discoveries, ranked by significance.
For each: [FINDING] — [Source: tool] — [Confidence: X%]

## CROSS-TOOL INSIGHTS
What only emerged by combining multiple tools.

## TIMELINE OF EVENTS
Chronological reconstruction with confidence ratings.

## RECOMMENDED ACTIONS
Immediate / Short-term / Long-term

## INTELLIGENCE GAPS
What we still don't know. What to investigate next.

## CONFIDENCE RATING
Overall: X% — [what would change this]"""

def generate_dossier(case):
    """Generate final unified dossier from all tools."""
    case.log("nexus", "Generating final intelligence dossier...")

    all_intel = {
        "osint":       case.osint.get("findings",{}),
        "observations":case.observations[-1][:500] if case.observations else "",
        "deductions":  case.deductions[-1][:500]   if case.deductions  else "",
        "verdict":     case.verdict.get("text","")[:500] if case.verdict else "",
        "theories":    case.theories[:3],
        "connections": case.connections[:5],
        "timeline":    case.timeline[:10],
        "suspects":    case.suspects,
    }

    dossier = ai_call(
        DOSSIER_PROMPT.format(
            case_name = case.name,
            target    = case.target,
            date      = datetime.now().strftime("%Y-%m-%d"),
            all_intel = json.dumps(all_intel, default=str)[:3000],
        ),
        max_tokens=3000
    )

    # Save dossier
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fp = CASES_DIR / f"DOSSIER_{case.case_id}_{ts}.txt"
    fp.write_text(dossier)

    case.log("nexus", f"Dossier saved: {fp}", "success")
    return dossier, fp

# ══════════════════════════════════════════════════════════════════════════════
# 🌅 MORNING BRIEF
# ══════════════════════════════════════════════════════════════════════════════

BRIEF_PROMPT = """Generate the FORGE NEXUS morning intelligence brief.

Date: {date}
Active cases: {cases}
Recent alerts: {alerts}
Targets being monitored: {targets}

Write a tight morning brief:

# FORGE NEXUS — MORNING BRIEF
# {date}

## OVERNIGHT DEVELOPMENTS
What changed since yesterday.

## ACTIVE CASES — STATUS
For each case: one-line status + confidence %

## PRIORITY TODAY
Top 3 things to investigate or act on.

## WATCH LIST
Targets showing new activity or changes.

## INTELLIGENCE SUMMARY
Key patterns across all active cases.

Keep it tight. This is read in 2 minutes."""

def morning_brief(cases_data, alerts=None):
    """Generate daily intelligence summary."""
    rprint("\n[bold yellow]🌅 FORGE NEXUS — MORNING BRIEF[/bold yellow]\n")

    result = ai_call(
        BRIEF_PROMPT.format(
            date    = datetime.now().strftime("%A, %B %d %Y"),
            cases   = json.dumps([{
                "name":       c.get("name"),
                "target":     c.get("target"),
                "confidence": c.get("confidence",0),
                "status":     c.get("status"),
            } for c in cases_data[:5]], indent=2),
            alerts  = json.dumps(alerts or [], default=str)[:500],
            targets = [c.get("target","") for c in cases_data[:5]],
        ),
        max_tokens=1000
    )
    rprint(Panel(result, border_style="yellow", title="🌅 Morning Brief"))

    # Save
    ts = datetime.now().strftime("%Y%m%d")
    fp = BRIEFS_DIR / f"brief_{ts}.txt"
    fp.write_text(result)
    return result

# ══════════════════════════════════════════════════════════════════════════════
# 🚀 MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline(target, case_name="", verbose=True):
    """Run the full FORGE NEXUS pipeline on a target."""
    case_name = case_name or f"Investigation: {target}"

    rprint(f"\n[bold yellow]🔱 FORGE NEXUS PIPELINE[/bold yellow]")
    rprint(f"  [bold]Target:[/bold] [cyan]{target}[/cyan]")
    rprint(f"  [bold]Case:[/bold]   {case_name}")
    rprint(f"  [bold]Time:[/bold]   {datetime.now().strftime('%H:%M:%S')}\n")

    case = NexusCase(case_name, target)

    steps = [
        ("🔍 OSINT",        lambda: run_osint(case, verbose)),
        ("🧠 DEDUCTION",    lambda: run_sherlock(case, verbose)),
        ("🦇 DETECTIVE",    lambda: run_detective(case, verbose)),
        ("🔗 SYNTHESIS",    lambda: run_synthesis(case, verbose)),
    ]

    results = {}
    for step_name, step_fn in steps:
        rprint(f"\n[bold]{'━'*50}[/bold]")
        rprint(f"[bold yellow]STEP: {step_name}[/bold yellow]")
        rprint(f"[bold]{'━'*50}[/bold]")
        try:
            result      = step_fn()
            results[step_name] = result
        except Exception as e:
            case.log("nexus", f"Step {step_name} failed: {e}", "error")

    # Final dossier
    rprint(f"\n[bold]{'━'*50}[/bold]")
    rprint(f"[bold yellow]FINAL: 📋 DOSSIER GENERATION[/bold yellow]")
    rprint(f"[bold]{'━'*50}[/bold]")

    dossier_text = ""
    dossier_file = None
    if AI_AVAILABLE:
        dossier_text, dossier_file = generate_dossier(case)
        rprint(f"\n[bold]📋 INTELLIGENCE DOSSIER[/bold]")
        rprint(Panel(dossier_text, border_style="yellow", title=f"🔱 {case.name}"))
    else:
        rprint("[dim]AI not available. Saving raw data only.[/dim]")

    # Save case
    case_file = case.save()

    # Summary
    rprint(f"\n[bold yellow]{'═'*50}[/bold yellow]")
    rprint(f"[bold]🔱 NEXUS PIPELINE COMPLETE[/bold]")
    rprint(f"[bold yellow]{'═'*50}[/bold yellow]")
    rprint(f"  [bold]Target:[/bold]      {target}")
    rprint(f"  [bold]OSINT items:[/bold] {sum(len(v) for v in case.osint.get('findings',{}).values())}")
    rprint(f"  [bold]Observations:[/bold]{len(case.observations)}")
    rprint(f"  [bold]Theories:[/bold]    {len(case.theories)}")
    rprint(f"  [bold]Connections:[/bold] {len(case.connections)}")
    rprint(f"  [bold]Timeline:[/bold]    {len(case.timeline)} events")
    rprint(f"  [bold]Confidence:[/bold]  {case.confidence}%")
    rprint(f"  [bold]Case file:[/bold]   {case_file}")
    if dossier_file:
        rprint(f"  [bold]Dossier:[/bold]     {dossier_file}")

    return case, dossier_text

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API SERVER
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7339):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse
    import threading

    active_cases  = {}
    pipeline_jobs = {}

    class NexusAPI(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def do_OPTIONS(self):
            self.send_response(200); self._cors(); self.end_headers()

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin","*")
            self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
            self.send_header("Access-Control-Allow-Headers","Content-Type")

        def _json(self, data, code=200):
            body = json.dumps(data, default=str).encode()
            self.send_response(code); self._cors()
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",len(body))
            self.end_headers(); self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length",0))
            return json.loads(self.rfile.read(n)) if n else {}

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/status":
                tools = check_tool_health()
                self._json({"status":"online","ai":AI_AVAILABLE,
                            "tools":tools,"cases":len(active_cases)})
            elif path == "/api/cases":
                self._json({"cases":[c.to_dict() for c in active_cases.values()]})
            elif path.startswith("/api/case/"):
                cid = path.split("/")[-1]
                if cid in active_cases:
                    self._json(active_cases[cid].to_dict())
                else:
                    self._json({"error":"not found"},404)
            elif path == "/api/tools":
                self._json({"tools": check_tool_health()})
            elif path == "/api/pipeline/status":
                self._json({"jobs":{k:{"status":v.get("status"),"progress":v.get("progress",0)}
                                    for k,v in pipeline_jobs.items()}})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()

            if path == "/api/pipeline/run":
                target    = body.get("target","")
                case_name = body.get("name","") or f"Investigation: {target}"
                if not target:
                    self._json({"error":"target required"},400); return

                job_id = hashlib.md5(f"{target}{time.time()}".encode()).hexdigest()[:8]
                pipeline_jobs[job_id] = {"status":"running","progress":0,"target":target}

                def run_job():
                    try:
                        case, dossier = run_pipeline(target, case_name, verbose=False)
                        active_cases[case.case_id] = case
                        pipeline_jobs[job_id].update({
                            "status":    "complete",
                            "progress":  100,
                            "case_id":   case.case_id,
                            "dossier":   dossier[:500] if dossier else "",
                            "confidence":case.confidence,
                        })
                    except Exception as e:
                        pipeline_jobs[job_id].update({"status":"error","error":str(e)})

                t = threading.Thread(target=run_job, daemon=True)
                t.start()
                self._json({"job_id":job_id,"status":"running","target":target})

            elif path == "/api/pipeline/status":
                job_id = body.get("job_id","")
                if job_id in pipeline_jobs:
                    job = pipeline_jobs[job_id]
                    response = dict(job)
                    if "case_id" in job and job["case_id"] in active_cases:
                        response["case"] = active_cases[job["case_id"]].to_dict()
                    self._json(response)
                else:
                    self._json({"error":"job not found"},404)

            elif path == "/api/brief":
                cases_data = [c.to_dict() for c in active_cases.values()]
                result     = morning_brief(cases_data)
                self._json({"brief":result})

            elif path == "/api/case/new":
                name   = body.get("name","New Case")
                target = body.get("target","")
                case   = NexusCase(name, target)
                active_cases[case.case_id] = case
                self._json({"case_id":case.case_id,"name":name})

            elif path == "/api/case/add_finding":
                cid     = body.get("case_id","")
                tool    = body.get("tool","manual")
                finding = body.get("finding","")
                if cid in active_cases:
                    active_cases[cid].log(tool, finding, "info")
                    active_cases[cid].save()
                    self._json({"ok":True})
                else:
                    self._json({"error":"case not found"},404)

            else:
                self._json({"error":"unknown endpoint"},404)

    server = HTTPServer(("0.0.0.0", port), NexusAPI)
    rprint(f"  [yellow]🔱 FORGE NEXUS API: http://localhost:{port}[/yellow]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# 🖥️ INTERACTIVE HUB
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow bold]
  ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗
  ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝
  ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗
  ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║
  ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║
  ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝
[/yellow bold]
[bold]  🔱 FORGE NEXUS — Unified Intelligence Platform[/bold]
[dim]  All tools. One brain. One command.[/dim]
"""

def show_status():
    """Display all tool statuses."""
    tools = check_tool_health()
    if RICH:
        t = Table(border_style="yellow", box=rbox.ROUNDED, title="FORGE Tool Registry")
        t.add_column("Tool",        style="bold",   width=14)
        t.add_column("File",        style="dim",    width=24)
        t.add_column("Description", style="white",  width=36)
        t.add_column("Status",      width=10)
        for name, tool in tools.items():
            status_str = "[green]✅ ready[/green]" if tool["available"] else "[red]❌ missing[/red]"
            t.add_row(name, tool["file"], tool["desc"], status_str)
        console.print(t)

def interactive_hub():
    rprint(BANNER)
    show_status()

    active_cases = {}
    rprint("\n[dim]Commands: run <target> | cases | brief | status | help | quit[/dim]\n")

    while True:
        try:
            inp = console.input if RICH else input
            raw = inp("[yellow bold]🔱 nexus >[/yellow bold] ").strip()
            if not raw: continue

            parts = raw.split(None, 1)
            cmd   = parts[0].lower()
            args  = parts[1] if len(parts)>1 else ""

            if cmd in ("quit","exit","q"):
                rprint("[dim]FORGE NEXUS offline. Stay vigilant.[/dim]"); break

            elif cmd == "help":
                rprint("""
[bold yellow]FORGE NEXUS Commands[/bold yellow]

  [yellow]run[/yellow] <target>        Full pipeline: OSINT → Sherlock → Detective → Synthesis
  [yellow]investigate[/yellow] <target> OSINT only (forge_investigate)
  [yellow]deduce[/yellow] <text>        Sherlock deduction only
  [yellow]brief[/yellow]                Morning intelligence brief
  [yellow]cases[/yellow]                List all active cases
  [yellow]case[/yellow] <id>            Show case details
  [yellow]dossier[/yellow] <id>         Generate dossier for case
  [yellow]status[/yellow]               Tool health check
  [yellow]server[/yellow]               Start API server
  [yellow]help[/yellow]                 Show this
""")

            elif cmd == "run":
                if not args: args = (console.input if RICH else input)("Target: ").strip()
                case, dossier = run_pipeline(args)
                active_cases[case.case_id] = case

            elif cmd == "investigate":
                if not args: args = (console.input if RICH else input)("Target: ").strip()
                case = NexusCase(f"OSINT: {args}", args)
                run_osint(case)
                active_cases[case.case_id] = case
                case.save()

            elif cmd == "deduce":
                if not args:
                    rprint("[dim]Enter text to deduce from:[/dim]")
                    args = (console.input if RICH else input)("[dim]...[/dim] ")
                case = NexusCase("Quick Deduction", "")
                case.osint = {"findings":{"input":{"text":{"value":args}}}}
                run_sherlock(case)
                if case.deductions:
                    rprint(Panel(case.deductions[-1], border_style="yellow"))

            elif cmd == "brief":
                cases_data = [c.to_dict() for c in active_cases.values()]
                morning_brief(cases_data)

            elif cmd == "cases":
                if not active_cases:
                    rprint("[dim]No active cases.[/dim]"); continue
                if RICH:
                    t = Table(border_style="yellow", box=rbox.SIMPLE)
                    t.add_column("ID",         style="dim",    width=10)
                    t.add_column("Name",       style="yellow", width=28)
                    t.add_column("Target",     style="cyan",   width=22)
                    t.add_column("Confidence", style="green",  width=12)
                    t.add_column("Tools Run",  width=12)
                    for cid, c in active_cases.items():
                        tools_run = sum([
                            bool(c.osint), bool(c.observations),
                            bool(c.verdict), bool(c.connections)
                        ])
                        t.add_row(c.case_id, c.name[:27], c.target[:21],
                                  f"{c.confidence}%", f"{tools_run}/4")
                    console.print(t)

            elif cmd == "case":
                cid = args
                if cid in active_cases:
                    c = active_cases[cid]
                    rprint(f"\n[bold]Case:[/bold] {c.name}")
                    rprint(f"[bold]Target:[/bold] {c.target}")
                    rprint(f"[bold]OSINT:[/bold] {sum(len(v) for v in c.osint.get('findings',{}).values())} items")
                    rprint(f"[bold]Observations:[/bold] {len(c.observations)}")
                    rprint(f"[bold]Theories:[/bold] {len(c.theories)}")
                    rprint(f"[bold]Connections:[/bold] {len(c.connections)}")
                    rprint(f"[bold]Timeline:[/bold] {len(c.timeline)} events")
                    rprint(f"[bold]Confidence:[/bold] {c.confidence}%")

            elif cmd == "dossier":
                cid = args
                if cid in active_cases:
                    dossier, fp = generate_dossier(active_cases[cid])
                    rprint(Panel(dossier, border_style="yellow"))

            elif cmd == "status":
                show_status()

            elif cmd == "server":
                port = 7339
                rprint(f"[yellow]Starting NEXUS server on port {port}...[/yellow]")
                threading.Thread(target=start_server, args=(port,), daemon=True).start()
                time.sleep(0.5)
                rprint(f"[green]Server running. Open forge_nexus.html[/green]")

            else:
                if AI_AVAILABLE:
                    context = json.dumps({
                        "active_cases": len(active_cases),
                        "tools":        list(TOOLS.keys()),
                    })
                    result = ai_call(
                        f"NEXUS context: {context}\n\nUser query: {raw}",
                        max_tokens=400
                    )
                    rprint(f"\n[yellow]🔱[/yellow] {result}")
                else:
                    rprint("[dim]Unknown command. Type 'help'.[/dim]")

        except (KeyboardInterrupt, EOFError):
            rprint("\n[dim]FORGE NEXUS offline.[/dim]"); break

def main():
    if "--server" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7339
        rprint(BANNER)
        start_server(port)
        return

    if "--investigate" in sys.argv:
        idx    = sys.argv.index("--investigate")
        target = sys.argv[idx+1]
        rprint(BANNER)
        run_pipeline(target)
        return

    if "--morning-brief" in sys.argv:
        rprint(BANNER)
        cases = []
        for fp in sorted(CASES_DIR.glob("*.json"), reverse=True)[:5]:
            try: cases.append(json.loads(fp.read_text()))
            except: pass
        morning_brief(cases)
        return

    if "--status" in sys.argv:
        rprint(BANNER)
        show_status()
        return

    interactive_hub()

if __name__ == "__main__":
    main()
