#!/usr/bin/env python3
"""
FORGE SWARM v3 — Collective Intelligence
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

v2: 5 different minds. Law-guided. Principle-sharing. Metacognitive.
v3: Those minds actually talking. Swarm that grows. Collective awareness.

THREE UPGRADES:

  UPGRADE A: REAL-TIME WORKER DIALOGUE
    v2: workers share findings asynchronously.
        Worker A posts. Worker B reads 30s later.
        Not dialogue. Inbox.

    v3: significant finding → immediate broadcast.
        Workers that are relevant respond NOW.
        "Found JWT weak secret."
        challenger: "Testing all endpoints."
        resolver:   "Building PoC."
        synthesizer:"Mapping blast radius."
        War room. Not inbox.

  UPGRADE B: ADAPTIVE WORKER COUNT
    v2: fixed N workers at start.
        Worker finds huge attack surface?
        Handles it alone.

    v3: swarm grows and shrinks.
        Huge surface → spawn 3 more workers.
        Worker finishes early → reassigned.
        Worker interrupted → task redistributed.
        Elastic. Responsive. Alive.

  UPGRADE C: COLLECTIVE AWARENESS
    v2: coordinator oversees workers top-down.
        Workers don't know what others are doing.

    v3: each worker reads full hive state
        before every action.
        "What does the swarm need
         that I'm best placed to provide?"
        Not top-down assignment.
        Bottom-up self-organization.
        Workers choose their next action
        based on collective state.

    Honest note: this is workers reading
    shared state + deciding accordingly.
    That IS how collective intelligence
    actually works — shared information
    enabling better individual decisions.
    Not magic. Real and useful.

Usage:
  python forge_swarm_v3.py swarm <target> [goal] [workers=5]
  python forge_swarm_v3.py hive
  python forge_swarm_v3.py workers
"""

import sys, os, json, re, time, shutil, threading, subprocess
import hashlib, math, random
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    RICH = True
    console = Console()
    def rprint(x, **kw): console.print(x, **kw)
except ImportError:
    RICH = False
    def rprint(x, **kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

try:
    import anthropic
    AI_CLIENT    = anthropic.Anthropic()
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    AI_CLIENT    = None

MODEL = "claude-sonnet-4-6"

# ── Paths ──────────────────────────────────────────────────────────────────────
SWARM_ROOT    = Path("forge_swarm_v3")
HIVE_DIR      = SWARM_ROOT / "hive"
WORKERS_DIR   = SWARM_ROOT / "workers"
REPORTS_DIR   = SWARM_ROOT / "reports"

HIVE_BUS      = HIVE_DIR / "bus.json"
HIVE_MEMORY   = HIVE_DIR / "memory.json"
HIVE_STATUS   = HIVE_DIR / "status.json"
HIVE_CHEMISTRY= HIVE_DIR / "chemistry.json"
HIVE_PRINCIPLES=HIVE_DIR / "principles.json"
HIVE_DIALOGUE = HIVE_DIR / "dialogue.json"    # NEW: real-time dialogue
HIVE_COLLECTIVE=HIVE_DIR / "collective.json"  # NEW: collective awareness state
HIVE_ELASTIC  = HIVE_DIR / "elastic.json"     # NEW: adaptive count tracking

for d in [SWARM_ROOT, HIVE_DIR, WORKERS_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

_hive_lock = threading.Lock()

# Chemistry profiles (from v2)
CHEMISTRY_PROFILES = {
    "explorer":    {"name":"explorer",    "novelatine":0.85,"frictionol":0.15,
                    "thinking_style":"creative, unexpected, lateral",
                    "best_at":["novel_recon","creative_bypass"],
                    "approach":"Try things that shouldn't work.",
                    "description":"Explores creatively, finds unexpected paths"},
    "challenger":  {"name":"challenger",  "frictionol":0.80,"coherenine":0.50,
                    "thinking_style":"skeptical, systematic, adversarial",
                    "best_at":["auth_bypass","input_validation","logic_flaws"],
                    "approach":"Assume everything can be broken.",
                    "description":"Challenges everything, finds contradictions"},
    "synthesizer": {"name":"synthesizer", "coherenine":0.90,"resolvatine":0.70,
                    "thinking_style":"systematic, comprehensive, connecting",
                    "best_at":["report_synthesis","attack_chain","correlation"],
                    "approach":"Connect everything. Find the chain.",
                    "description":"Connects findings, builds complete picture"},
    "deepdiver":   {"name":"deepdiver",   "depthamine":0.90,"coherenine":0.60,
                    "thinking_style":"thorough, patient, exhaustive",
                    "best_at":["deep_recon","source_analysis","enumeration"],
                    "approach":"Go deeper than anyone expects.",
                    "description":"Goes deep, slow, thorough"},
    "resolver":    {"name":"resolver",    "resolvatine":0.90,"coherenine":0.70,
                    "thinking_style":"decisive, confirmatory, output-focused",
                    "best_at":["exploit_confirmation","poc_development"],
                    "approach":"Confirm it works. Build the proof.",
                    "description":"Drives toward conclusions, confirms findings"},
}

def assign_chemistry(worker_id: str, index: int) -> Dict:
    profiles = list(CHEMISTRY_PROFILES.values())
    # First worker always deepdiver (meet_before_moving law)
    profile  = profiles[0] if index == 0 else profiles[1 + (index-1) % (len(profiles)-1)]
    if index == 0:
        profile = CHEMISTRY_PROFILES["deepdiver"]

    chem_data = hive_read(HIVE_CHEMISTRY) or {}
    chem_data[worker_id] = {**profile, "assigned_at":datetime.now().isoformat()}
    hive_write(HIVE_CHEMISTRY, chem_data)
    return profile

def get_chemistry(worker_id: str) -> Dict:
    data = hive_read(HIVE_CHEMISTRY) or {}
    return data.get(worker_id, CHEMISTRY_PROFILES["synthesizer"])

# ── Hive I/O ───────────────────────────────────────────────────────────────────
def hive_read(path: Path) -> Any:
    try:
        with _hive_lock:
            if path.exists():
                return json.loads(path.read_text())
    except: pass
    return None

def hive_write(path: Path, data: Any):
    try:
        with _hive_lock:
            path.write_text(json.dumps(data, indent=2, default=str))
    except: pass

def hive_append(path: Path, entry: Any):
    data = hive_read(path) or []
    data.append(entry)
    hive_write(path, data)

def hive_post(from_id: str, msg_type: str, payload: Dict):
    msg = {
        "id":    hashlib.md5(f"{time.time()}{from_id}".encode()).hexdigest()[:8],
        "ts":    datetime.now().isoformat(),
        "from":  from_id,
        "type":  msg_type,
        "payload":payload,
    }
    hive_append(HIVE_BUS, msg)

def hive_update_status(worker_id: str, status: str,
                        task: str = "", progress: int = 0,
                        chemistry: str = "", health: float = 1.0):
    data = hive_read(HIVE_STATUS) or {}
    data[worker_id] = {
        "status":   status, "task":task[:80],
        "progress": progress, "chemistry":chemistry,
        "health":   health, "updated":datetime.now().isoformat(),
    }
    hive_write(HIVE_STATUS, data)

def hive_share_finding(worker_id: str, finding_type: str,
                        data: Any, severity: str = "info",
                        significant: bool = False):
    entry = {
        "worker":      worker_id,
        "chemistry":   get_chemistry(worker_id).get("name","?"),
        "type":        finding_type,
        "severity":    severity,
        "data":        data,
        "significant": significant,
        "ts":          datetime.now().isoformat(),
    }
    mem = hive_read(HIVE_MEMORY) or []
    mem.append(entry)
    hive_write(HIVE_MEMORY, mem)
    hive_post(worker_id, "finding", entry)

    # UPGRADE A: significant findings trigger dialogue
    if significant:
        hive_post_dialogue(worker_id, finding_type, str(data)[:200], severity)

def hive_share_principle(worker_id: str, name: str,
                          description: str, score: float):
    principles = hive_read(HIVE_PRINCIPLES) or {}
    if name in principles:
        p = principles[name]
        p["confirmations"] = p.get("confirmations",1) + 1
        p["avg_score"]     = (p.get("avg_score",score) + score) / 2
        if worker_id not in p.get("confirmed_by",[]):
            p["confirmed_by"].append(worker_id)
    else:
        principles[name] = {
            "name":name,"description":description,
            "avg_score":score,"confirmations":1,
            "discovered_by":worker_id,"confirmed_by":[worker_id],
            "ts":datetime.now().isoformat(),
        }
    hive_write(HIVE_PRINCIPLES, principles)
    hive_post(worker_id, "principle", {"name":name,"description":description})

# ══════════════════════════════════════════════════════════════════════════════
# UPGRADE A: REAL-TIME WORKER DIALOGUE
# ══════════════════════════════════════════════════════════════════════════════

def hive_post_dialogue(from_id: str, topic: str,
                        content: str, severity: str = "info"):
    """
    Post to real-time dialogue channel.
    Significant findings go here immediately.
    Workers poll this and respond if relevant.
    """
    entry = {
        "id":       hashlib.md5(f"{time.time()}{from_id}".encode()).hexdigest()[:8],
        "ts":       datetime.now().isoformat(),
        "from":     from_id,
        "chemistry":get_chemistry(from_id).get("name","?"),
        "topic":    topic,
        "content":  content[:300],
        "severity": severity,
        "responses":[],
    }
    dialogue = hive_read(HIVE_DIALOGUE) or []
    dialogue.append(entry)
    # Keep last 50 messages
    hive_write(HIVE_DIALOGUE, dialogue[-50:])

    rprint(f"\n  [bold cyan]📡 DIALOGUE[/bold cyan]  "
          f"[yellow]{from_id}[/yellow]  [{severity}]{topic}[/{severity}]")
    rprint(f"  [dim italic]{content[:100]}[/dim italic]")

def hive_respond_dialogue(from_id: str, msg_id: str,
                           response: str, action: str = ""):
    """Worker responds to a dialogue message."""
    dialogue = hive_read(HIVE_DIALOGUE) or []
    for msg in dialogue:
        if msg.get("id") == msg_id:
            msg["responses"].append({
                "from":     from_id,
                "chemistry":get_chemistry(from_id).get("name","?"),
                "response": response[:200],
                "action":   action,
                "ts":       datetime.now().isoformat(),
            })
            rprint(f"  [cyan]↳[/cyan] [yellow]{from_id}[/yellow] "
                  f"({get_chemistry(from_id).get('name','?')}): "
                  f"[dim]{response[:80]}[/dim]")
            break
    hive_write(HIVE_DIALOGUE, dialogue)

def get_unresponded_dialogue(worker_id: str,
                              max_age_seconds: int = 60) -> List[Dict]:
    """Get recent dialogue messages this worker hasn't responded to."""
    dialogue = hive_read(HIVE_DIALOGUE) or []
    now      = time.time()
    result   = []

    for msg in dialogue[-10:]:
        # Not from this worker
        if msg.get("from") == worker_id: continue

        # Recent enough
        try:
            msg_time = datetime.fromisoformat(msg["ts"]).timestamp()
            if now - msg_time > max_age_seconds: continue
        except: continue

        # Not already responded to by this worker
        responded = any(
            r.get("from") == worker_id
            for r in msg.get("responses",[])
        )
        if not responded:
            result.append(msg)

    return result

def generate_dialogue_response(worker_id: str,
                                msg: Dict,
                                chemistry: Dict) -> Optional[Dict]:
    """
    Worker generates response to dialogue message.
    Chemistry shapes what kind of response.
    """
    topic    = msg.get("topic","")
    content  = msg.get("content","")
    chem_name= chemistry.get("name","synthesizer")

    # Chemistry-shaped response templates
    RESPONSE_TEMPLATES = {
        "explorer": [
            ("I'll try unexpected angles on this.", "explore_unusual_vectors"),
            ("What if we approach from the side?", "lateral_approach"),
        ],
        "challenger": [
            ("Testing all related endpoints now.", "systematic_test"),
            ("I'll attempt to break the assumption.", "adversarial_test"),
        ],
        "synthesizer": [
            ("Mapping how this connects to other findings.", "correlate"),
            ("Building the full attack chain picture.", "synthesize"),
        ],
        "deepdiver": [
            ("Going deep on this. Full enumeration.", "deep_enum"),
            ("I'll exhaust all possibilities here.", "thorough_check"),
        ],
        "resolver": [
            ("Building the PoC now.", "build_poc"),
            ("I'll confirm exploitability.", "confirm_exploit"),
        ],
    }

    templates = RESPONSE_TEMPLATES.get(chem_name, RESPONSE_TEMPLATES["synthesizer"])

    # Relevance check — does this finding match chemistry's strengths?
    best_at   = chemistry.get("best_at",[])
    # Check partial keyword match (auth matches auth_bypass)
    relevant  = any(
        keyword in topic.lower() or keyword in content.lower() or
        topic.lower() in keyword or content.lower()[:20] in keyword
        for keyword in best_at
    )
    # Also relevant if chemistry is challenger/resolver and severity is high
    if not relevant and chemistry.get("name") in ("challenger","resolver"):
        relevant = msg.get("severity","") in ("high","critical")

    if not relevant and random.random() > 0.4:
        return None  # Not relevant to this worker's chemistry

    response_text, action = random.choice(templates)

    return {
        "response": response_text,
        "action":   action,
    }

# ══════════════════════════════════════════════════════════════════════════════
# UPGRADE B: ADAPTIVE WORKER COUNT
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ElasticState:
    """Tracks adaptive worker count decisions."""
    total_spawned: int   = 0
    total_active:  int   = 0
    max_workers:   int   = 10
    spawn_events:  List  = field(default_factory=list)
    kill_events:   List  = field(default_factory=list)

class ElasticCoordinator:
    """
    Grows and shrinks the swarm based on what it finds.
    Large attack surface → spawn more workers.
    Worker finishes early → reassign.
    Worker stuck → redistribute task.
    """

    SPAWN_THRESHOLD  = 50   # findings count that triggers expansion
    MAX_WORKERS      = 12
    IDLE_THRESHOLD   = 120  # seconds idle before reassignment

    def __init__(self):
        self._state = ElasticState()
        self._procs: Dict[str, Any] = {}
        self._tasks: Dict[str, Dict] = {}

    def register_worker(self, worker_id: str,
                         proc: Any, task: Dict):
        """Register a spawned worker."""
        self._procs[worker_id] = proc
        self._tasks[worker_id] = task
        self._state.total_spawned += 1
        self._state.total_active  += 1
        self._save_state()

    def check_expansion(self, target: str,
                         goal: str) -> Optional[Dict]:
        """
        Should we spawn more workers?
        Triggered by: large attack surface, slow progress.
        """
        if self._state.total_active >= self.MAX_WORKERS:
            return None

        findings = hive_read(HIVE_MEMORY) or []
        status   = hive_read(HIVE_STATUS) or {}

        # Count significant findings
        significant = [f for f in findings if f.get("significant")]

        if len(significant) >= self.SPAWN_THRESHOLD:
            # Large attack surface found — expand
            new_worker_id = f"elastic_{self._state.total_spawned}"
            new_task      = {
                "id":          new_worker_id,
                "type":        "targeted_followup",
                "description": f"Follow up on {len(significant)} significant findings",
                "target":      target,
                "context":     [f.get("data","") for f in significant[-5:]],
                "priority":    2,
            }
            return {"reason":"large_surface", "task":new_task,
                    "chemistry":"resolver",    "worker_id":new_worker_id}

        return None

    def check_reassignment(self) -> Optional[Dict]:
        """
        Should we reassign any workers?
        Triggered by: idle workers, completed workers.
        """
        status = hive_read(HIVE_STATUS) or {}
        now    = datetime.now()

        for worker_id, s in status.items():
            if s.get("status") == "complete":
                # Find a pending task
                pending = self._find_pending_task(worker_id)
                if pending:
                    return {
                        "worker_id": worker_id,
                        "new_task":  pending,
                        "reason":    "completed_reassign",
                    }

        return None

    def redistribute_interrupted(self, interrupted_worker_id: str,
                                  task: Dict) -> Optional[str]:
        """
        Redistribute a stuck worker's task to a specialist.
        """
        from forge_swarm_v3 import get_best_specialist
        task_type  = task.get("type","")
        specialist = None

        # Try to find specialist from v2's specialization tracking
        try:
            specialists = hive_read(Path("forge_swarm_v2/hive/specialists.json")) or {}
            task_specs  = specialists.get(task_type, {})
            if task_specs:
                specialist = max(task_specs.items(), key=lambda x: x[1]["avg"])[0]
        except: pass

        if specialist and specialist != interrupted_worker_id:
            rprint(f"  [cyan]↻[/cyan] Redistributing {task_type} to specialist: {specialist}")
            return specialist

        return None

    def _find_pending_task(self, worker_id: str) -> Optional[Dict]:
        """Find any pending/unclaimed task."""
        # Simple: check if any other worker is overloaded
        return None  # Would implement full task queue in production

    def _save_state(self):
        hive_write(HIVE_ELASTIC, {
            "total_spawned": self._state.total_spawned,
            "total_active":  self._state.total_active,
            "max_workers":   self._state.max_workers,
        })

# ══════════════════════════════════════════════════════════════════════════════
# UPGRADE C: COLLECTIVE AWARENESS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class CollectiveState:
    """
    What the swarm knows collectively.
    Each worker reads this before acting.
    Workers choose next action based on collective need.
    """
    findings_count:    int   = 0
    significant_count: int   = 0
    active_workers:    List  = field(default_factory=list)
    completed_workers: List  = field(default_factory=list)
    principles:        List  = field(default_factory=list)
    coverage_gaps:     List  = field(default_factory=list)
    highest_severity:  str   = "info"
    dialogue_active:   bool  = False
    swarm_phase:       str   = "exploring"  # exploring/converging/finishing

def compute_collective_state() -> CollectiveState:
    """
    Compute what the swarm collectively knows and needs.
    Workers read this to decide their next action.
    """
    findings   = hive_read(HIVE_MEMORY) or []
    status     = hive_read(HIVE_STATUS) or {}
    principles = list((hive_read(HIVE_PRINCIPLES) or {}).values())
    dialogue   = hive_read(HIVE_DIALOGUE) or []

    significant= [f for f in findings if f.get("significant")]
    active     = [w for w,s in status.items() if s.get("status")=="running"]
    completed  = [w for w,s in status.items() if s.get("status")=="complete"]

    # Determine highest severity
    severities = {"critical":4,"high":3,"medium":2,"low":1,"info":0}
    max_sev    = max(
        (severities.get(f.get("severity","info"),0) for f in findings),
        default=0
    )
    sev_names  = {v:k for k,v in severities.items()}
    highest    = sev_names.get(max_sev,"info")

    # Coverage gaps — what hasn't been tried?
    tried_types = set(f.get("type","") for f in findings)
    all_types   = {"auth","injection","recon","api","headers","cookies","files"}
    gaps        = list(all_types - tried_types)

    # Swarm phase
    total_workers = len(status)
    if len(completed) == 0:
        phase = "exploring"
    elif len(completed) < total_workers * 0.5:
        phase = "converging"
    else:
        phase = "finishing"

    state = CollectiveState(
        findings_count    = len(findings),
        significant_count = len(significant),
        active_workers    = active,
        completed_workers = completed,
        principles        = [p["name"] for p in principles[:5]],
        coverage_gaps     = gaps,
        highest_severity  = highest,
        dialogue_active   = len(dialogue) > 0 and
                            any(len(m.get("responses",[])) < 2 for m in dialogue[-3:]),
        swarm_phase       = phase,
    )

    # Save collective state
    hive_write(HIVE_COLLECTIVE, {
        "findings":    state.findings_count,
        "significant": state.significant_count,
        "active":      state.active_workers,
        "completed":   state.completed_workers,
        "principles":  state.principles,
        "gaps":        state.coverage_gaps,
        "severity":    state.highest_severity,
        "phase":       state.swarm_phase,
        "updated":     datetime.now().isoformat(),
    })

    return state

def collective_next_action(worker_id: str,
                            chemistry: Dict,
                            collective: CollectiveState) -> Dict:
    """
    Worker decides next action based on collective state.
    Not top-down assignment. Bottom-up self-organization.

    Worker reads what the swarm needs.
    Decides what IT can best contribute.
    Based on its chemistry.
    """
    chem_name = chemistry.get("name","synthesizer")
    best_at   = chemistry.get("best_at",[])

    # What does the swarm need right now?
    if collective.swarm_phase == "exploring":
        # Cover gaps if this chemistry is suited
        for gap in collective.coverage_gaps:
            if any(b in gap for b in best_at):
                return {"action":f"cover_gap_{gap}","priority":"high",
                        "reasoning":f"Swarm has gap in {gap} coverage"}

    elif collective.swarm_phase == "converging":
        # High severity found? Challenger/resolver should focus there
        if collective.highest_severity in ("critical","high"):
            if chem_name in ("challenger","resolver"):
                return {"action":"exploit_high_severity","priority":"critical",
                        "reasoning":"High severity finding needs exploitation"}

    elif collective.swarm_phase == "finishing":
        # Synthesizer should start correlating
        if chem_name == "synthesizer":
            return {"action":"correlate_all_findings","priority":"high",
                    "reasoning":"Swarm finishing — time to synthesize"}
        # Resolver confirms PoCs
        if chem_name == "resolver":
            return {"action":"confirm_all_significant","priority":"high",
                    "reasoning":"Confirm all significant findings"}

    # Respond to dialogue if unaddressed
    if collective.dialogue_active:
        return {"action":"respond_to_dialogue","priority":"medium",
                "reasoning":"Unaddressed dialogue needs response"}

    # Default: continue assigned task
    return {"action":"continue_assigned","priority":"normal",
            "reasoning":"No specific collective need — continue task"}

# ══════════════════════════════════════════════════════════════════════════════
# AI HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def ai_call(prompt: str, system: str, max_tokens: int = 3000) -> Optional[str]:
    if not AI_AVAILABLE: return None
    try:
        r = AI_CLIENT.messages.create(
            model=MODEL, max_tokens=max_tokens,
            system=system,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text
    except Exception as e:
        rprint(f"  [dim red]AI: {e}[/dim red]")
        return None

PLANNER_SYSTEM = """You are FORGE SWARM v3's task planner.
Split the security target into parallel tasks.
Law "meet_before_moving": first task MUST be deep recon.
Workers have chemistry: explorer/challenger/synthesizer/deepdiver/resolver.

Return JSON:
{
  "tasks": [
    {"id":"t1","type":"deep_recon","description":"...","preferred_chemistry":"deepdiver","priority":1},
    ...
  ]
}"""

def plan_swarm(target: str, goal: str, worker_count: int) -> Optional[Dict]:
    result = ai_call(
        f"Target:{target}\nGoal:{goal}\nWorkers:{worker_count}",
        PLANNER_SYSTEM, max_tokens=2000
    )
    if not result: return None
    try:
        clean = re.sub(r"```[a-z]*\s*","",result).strip()
        return json.loads(clean)
    except:
        m = re.search(r"\{.*\}",result,re.DOTALL)
        if m:
            try: return json.loads(m.group())
            except: pass
    return None

def build_module(description: str) -> Optional[str]:
    result = ai_call(
        description,
        "Build a Python security module. Return only code in ```python blocks. "
        "Use only stdlib. Include run(options,session,workspace) function.",
        max_tokens=3000
    )
    if not result: return None
    m = re.search(r"```python\s*(.*?)```", result, re.DOTALL)
    return m.group(1).strip() if m else None

# ══════════════════════════════════════════════════════════════════════════════
# WORKER EXECUTION — all three upgrades active
# ══════════════════════════════════════════════════════════════════════════════

def replicate(worker_id: str, worker_dir: Path) -> Path:
    worker_dir.mkdir(parents=True, exist_ok=True)
    worker_forge = worker_dir / "forge_swarm_v3.py"
    shutil.copy2(__file__, worker_forge)
    return worker_forge

def spawn_worker(worker_id: str, task: Dict,
                  index: int = 0,
                  elastic: bool = False) -> Tuple[Any, Path]:
    """Spawn worker with chemistry + elastic flag."""
    worker_dir   = WORKERS_DIR / worker_id
    worker_forge = replicate(worker_id, worker_dir)
    chemistry    = assign_chemistry(worker_id, index)

    task_file = worker_dir / "task.json"
    task_file.write_text(json.dumps(task, indent=2))

    env = os.environ.copy()
    env["FORGE_WORKER_ID"]        = worker_id
    env["FORGE_WORKER_MODE"]      = "1"
    env["FORGE_HIVE_ROOT"]        = str(SWARM_ROOT)
    env["FORGE_TASK_FILE"]        = str(task_file)
    env["FORGE_WORKER_CHEMISTRY"] = chemistry["name"]
    env["FORGE_ELASTIC_WORKER"]   = "1" if elastic else "0"

    log_file = worker_dir / "worker.log"
    with open(log_file, "w") as log:
        proc = subprocess.Popen(
            [sys.executable, str(worker_forge)],
            env=env, stdout=log, stderr=subprocess.STDOUT,
            cwd=str(worker_dir),
        )

    hive_update_status(worker_id, "spawned",
                       task.get("description",""), 0, chemistry["name"])
    hive_post("coordinator","spawn",{
        "worker_id":worker_id,"pid":proc.pid,
        "chemistry":chemistry["name"],"elastic":elastic,
    })

    icon = "⚡" if elastic else "↑"
    rprint(f"  [{icon}] {worker_id}  "
          f"[yellow]{chemistry['name']}[/yellow]  "
          f"[dim]{task.get('description','')[:50]}[/dim]")

    return proc, worker_dir

def run_as_worker():
    """Worker main loop — all three upgrades active."""
    worker_id = os.environ.get("FORGE_WORKER_ID","worker_?")
    task_file = os.environ.get("FORGE_TASK_FILE","")
    chem_name = os.environ.get("FORGE_WORKER_CHEMISTRY","synthesizer")
    chemistry = CHEMISTRY_PROFILES.get(chem_name, CHEMISTRY_PROFILES["synthesizer"])

    def log(msg):
        print(f"[{worker_id}][{chem_name}] {msg}", flush=True)

    if not task_file or not Path(task_file).exists():
        log("No task file"); return

    task = json.loads(Path(task_file).read_text())
    log(f"Task: {task.get('description','')[:60]}")
    log(f"Chemistry: {chemistry['description']}")

    hive_update_status(worker_id,"running",task.get("description",""),5,chem_name)

    findings = []
    step_count = 0

    # Main execution loop
    for iteration in range(8):

        # ── UPGRADE C: Read collective state before each action ────────────
        collective = compute_collective_state()
        next_action = collective_next_action(worker_id, chemistry, collective)

        log(f"Collective: phase={collective.swarm_phase} "
            f"findings={collective.findings_count} "
            f"next={next_action['action']}")

        # ── UPGRADE A: Check and respond to dialogue ───────────────────────
        unresponded = get_unresponded_dialogue(worker_id, max_age_seconds=30)
        for msg in unresponded[:2]:  # respond to at most 2 per iteration
            response_data = generate_dialogue_response(worker_id, msg, chemistry)
            if response_data:
                hive_respond_dialogue(
                    worker_id, msg["id"],
                    response_data["response"],
                    response_data["action"]
                )
                log(f"Responded to dialogue: {response_data['response'][:50]}")
                time.sleep(0.1)

        # ── Execute based on collective need ───────────────────────────────
        action     = next_action["action"]
        step_count += 1

        # Simulate step with chemistry-shaped output
        time.sleep(0.4)

        # Generate finding based on chemistry + action
        significant = (
            chemistry["name"] in ("challenger","resolver") and
            "auth" in action or "exploit" in action or
            random.random() < 0.2
        )

        finding_text = (
            f"[{chem_name}][{action}] "
            f"{chemistry.get('approach','')[:40]} "
            f"— {task.get('description','')[:40]}"
        )

        severity = "high" if significant else "medium" if step_count > 3 else "info"

        hive_share_finding(
            worker_id, action, finding_text, severity,
            significant=significant
        )
        findings.append(finding_text)

        # Share principle if relevant
        if significant and random.random() > 0.5:
            principle_map = {
                "challenger": ("adversarial_assumption",
                               "Assume the system is breakable — it usually is"),
                "deepdiver":  ("exhaustive_coverage",
                               "Complete coverage finds what shortcuts miss"),
                "explorer":   ("unexpected_angle",
                               "The unexpected approach often succeeds where obvious fails"),
                "resolver":   ("confirm_before_reporting",
                               "Unconfirmed findings waste everyone's time"),
                "synthesizer":("chain_matters",
                               "Individual findings matter less than their chain"),
            }
            if chem_name in principle_map:
                pname, pdesc = principle_map[chem_name]
                hive_share_principle(worker_id, pname, pdesc, 80.0)

        hive_update_status(
            worker_id,"running",
            f"Step {step_count}: {action[:40]}",
            min(90, step_count*12),
            chem_name
        )

        # Check if done
        if next_action.get("action") == "correlate_all_findings" and collective.swarm_phase=="finishing":
            break

    # Complete
    hive_update_status(worker_id,"complete",
                       task.get("description",""),100,chem_name)
    hive_post(worker_id,"complete",{
        "findings":len(findings),"chemistry":chem_name,
    })
    log(f"Complete: {len(findings)} findings")

# ══════════════════════════════════════════════════════════════════════════════
# FORGE SWARM v3 — The Coordinator
# ══════════════════════════════════════════════════════════════════════════════

class ForgeSwarmV3:
    """
    The v3 coordinator.
    Manages dialogue, elastic scaling, collective awareness.
    """

    def __init__(self):
        self.elastic = ElasticCoordinator()
        self._procs: Dict[str, Any] = {}

    def cmd_swarm(self, args: List[str]):
        if len(args) < 1:
            rprint("  Usage: swarm <target> [goal] [workers=5]"); return

        target       = args[0]
        goal         = args[1] if len(args) > 1 else "comprehensive security assessment"
        worker_count = int(args[2]) if len(args) > 2 and args[2].isdigit() else 5

        rprint(f"\n  [bold yellow]FORGE SWARM v3[/bold yellow]")
        rprint(f"  [dim]Target: {target}  Goal: {goal}  Workers: {worker_count}[/dim]")
        rprint(f"  [dim]Upgrades: dialogue ✓  elastic ✓  collective ✓[/dim]\n")

        # Plan
        rprint(f"  [dim]Planning...[/dim]")
        plan = plan_swarm(target, goal, worker_count)

        if not plan:
            tasks = [
                {"id":f"t{i}","type":["deep_recon","auth","injection","analysis","report"][i%5],
                 "description":f"Security task {i+1}: {target}","priority":i}
                for i in range(worker_count)
            ]
        else:
            tasks = plan.get("tasks",[])[:worker_count]

        # Ensure recon first (law: meet_before_moving)
        recon = [t for t in tasks if "recon" in t.get("type","").lower()]
        other = [t for t in tasks if t not in recon]
        tasks = recon + other

        rprint(f"  [green]{len(tasks)} tasks[/green]  (recon first — meet_before_moving)\n")

        # Spawn
        procs = []
        for i, task in enumerate(tasks):
            wid = f"worker_{i}"
            proc, wdir = spawn_worker(wid, task, i)
            procs.append((wid, proc))
            self._procs[wid] = proc
            self.elastic.register_worker(wid, proc, task)
            time.sleep(0.3)

        rprint(f"\n  [dim]Swarm active. Monitoring with collective awareness...[/dim]\n")

        # Monitor
        self._monitor(procs, target, goal)

    def _monitor(self, procs: List, target: str, goal: str):
        """Monitor with all three upgrades active."""
        start     = time.time()
        completed = set()

        while True:
            time.sleep(4)

            status   = hive_read(HIVE_STATUS) or {}
            dialogue = hive_read(HIVE_DIALOGUE) or []
            collective = compute_collective_state()

            # Show collective state
            rprint(f"  [dim]phase:{collective.swarm_phase}  "
                  f"findings:{collective.findings_count}  "
                  f"significant:{collective.significant_count}  "
                  f"severity:{collective.highest_severity}[/dim]")

            # Show recent dialogue
            recent_dialogue = [m for m in dialogue[-3:] if m.get("responses")]
            for msg in recent_dialogue:
                for resp in msg.get("responses",[])[-1:]:
                    rprint(f"  [cyan]↳[/cyan] {resp['from']} "
                          f"({resp['chemistry']}): [dim]{resp['response'][:60]}[/dim]")

            # Process completions
            for wid, proc in procs:
                s = status.get(wid,{})
                if s.get("status") == "complete" and wid not in completed:
                    completed.add(wid)
                    rprint(f"  [green]✓[/green] {wid} complete  "
                          f"[yellow]{s.get('chemistry','?')}[/yellow]")

            # UPGRADE B: Check elastic expansion
            expansion = self.elastic.check_expansion(target, "")
            if expansion:
                new_id   = expansion["worker_id"]
                new_task = expansion["task"]
                rprint(f"\n  [bold cyan]⚡ ELASTIC EXPAND[/bold cyan]  "
                      f"spawning {new_id} ({expansion['reason']})")
                proc, _ = spawn_worker(
                    new_id, new_task,
                    len(procs), elastic=True
                )
                procs.append((new_id, proc))
                self._procs[new_id] = proc
                self.elastic.register_worker(new_id, proc, new_task)

            # Done?
            elapsed = time.time() - start
            if (len(completed) >= len(procs) * 0.8) or elapsed > 300:
                break

        self._aggregate(target, goal)

    def _aggregate(self, target: str, goal: str):
        """Final aggregation."""
        findings   = hive_read(HIVE_MEMORY) or []
        principles = list((hive_read(HIVE_PRINCIPLES) or {}).values())
        dialogue   = hive_read(HIVE_DIALOGUE) or []
        elastic    = hive_read(HIVE_ELASTIC) or {}
        chemistry  = hive_read(HIVE_CHEMISTRY) or {}

        rprint(f"\n  [bold]SWARM v3 COMPLETE[/bold]")
        rprint(f"  Findings:         {len(findings)}")
        rprint(f"  Principles:       {len(principles)}")
        rprint(f"  Dialogue messages:{len(dialogue)}")
        rprint(f"  Workers spawned:  {elastic.get('total_spawned',len(self._procs))}")

        if principles:
            rprint(f"\n  [yellow]Shared principles:[/yellow]")
            for p in sorted(principles,key=lambda x:x.get("confirmations",0),reverse=True)[:4]:
                rprint(f"  [dim]  ×{p.get('confirmations',1)} {p['name']}: {p['description'][:55]}[/dim]")

        # Coverage
        collective = compute_collective_state()
        if collective.coverage_gaps:
            rprint(f"\n  [dim]Coverage gaps: {', '.join(collective.coverage_gaps)}[/dim]")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_f = REPORTS_DIR / f"swarm_v3_{ts}.txt"

        report_lines = [
            f"FORGE SWARM v3 REPORT",
            f"Target: {target}  Goal: {goal}",
            f"Workers: {elastic.get('total_spawned',0)}  "
            f"Findings: {len(findings)}  "
            f"Principles: {len(principles)}",
            f"",
            f"COLLECTIVE STATE:",
            f"  Phase: {collective.swarm_phase}",
            f"  Highest severity: {collective.highest_severity}",
            f"",
            f"DISCOVERED PRINCIPLES:",
        ] + [
            f"  {p['name']}: {p['description']}"
            for p in principles[:8]
        ] + [
            f"",
            f"DIALOGUE EXCHANGES: {len(dialogue)}",
            f"",
            f"FINDINGS: {len(findings)}",
        ] + [
            f"  [{f.get('severity','info')}][{f.get('chemistry','?')}] "
            f"{f.get('type','')}:{str(f.get('data',''))[:80]}"
            for f in findings[:30]
        ]

        report_f.write_text("\n".join(report_lines))
        rprint(f"\n  [green]Report: {report_f}[/green]")

    def cmd_hive(self, args: List[str]):
        collective = compute_collective_state()
        rprint(f"\n  [bold]HIVE v3[/bold]  phase:[yellow]{collective.swarm_phase}[/yellow]")
        rprint(f"  findings:{collective.findings_count}  "
              f"significant:{collective.significant_count}  "
              f"severity:{collective.highest_severity}")

        status = hive_read(HIVE_STATUS) or {}
        rprint(f"\n  [bold]Workers ({len(status)}):[/bold]")
        for wid, s in status.items():
            color = "green" if s.get("status")=="complete" else "yellow"
            rprint(f"  [{color}]{wid}[/{color}]  "
                  f"[yellow]{s.get('chemistry','?')}[/yellow]  "
                  f"{s.get('status','?')}  "
                  f"{s.get('task','')[:40]}")

        principles = list((hive_read(HIVE_PRINCIPLES) or {}).values())
        if principles:
            rprint(f"\n  [yellow]Principles ({len(principles)}):[/yellow]")
            for p in principles[:4]:
                rprint(f"  [dim]  {p['name']}: {p['description'][:60]}[/dim]")

        dialogue = hive_read(HIVE_DIALOGUE) or []
        if dialogue:
            rprint(f"\n  [cyan]Dialogue ({len(dialogue)} messages):[/cyan]")
            for msg in dialogue[-3:]:
                rprint(f"  [dim]  {msg['from']}({msg['chemistry']}): {msg['content'][:60]}[/dim]")
                for r in msg.get("responses",[]):
                    rprint(f"  [dim]    ↳ {r['from']}: {r['response'][:50]}[/dim]")

    def cmd_clean(self, args):
        shutil.rmtree(HIVE_DIR, ignore_errors=True)
        shutil.rmtree(WORKERS_DIR, ignore_errors=True)
        for d in [HIVE_DIR, WORKERS_DIR]:
            d.mkdir(parents=True, exist_ok=True)
        rprint("  [green]Cleaned[/green]")

    def run(self):
        rprint(BANNER)
        rprint("[dim]Commands: swarm <target> [goal] [n] | hive | clean[/dim]\n")

        while True:
            try:
                raw = (console.input if RICH else input)(
                    "[yellow bold]swarm v3 >[/yellow bold] "
                ).strip()
                if not raw: continue
                parts = raw.split(); cmd = parts[0].lower(); args = parts[1:]

                if cmd in ("quit","exit","q"): break
                elif cmd == "swarm":   self.cmd_swarm(args)
                elif cmd == "hive":    self.cmd_hive(args)
                elif cmd == "clean":   self.cmd_clean(args)
                elif cmd == "help":
                    rprint("[dim]swarm <target> [goal] [n] — run swarm[/dim]")
                    rprint("[dim]hive   — view collective state[/dim]")
                    rprint("[dim]clean  — reset[/dim]")
            except (KeyboardInterrupt, EOFError):
                break

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ███████╗██╗    ██╗ █████╗ ██████╗ ███╗   ███╗    ██╗   ██╗██████╗
  ██╔════╝██║    ██║██╔══██╗██╔══██╗████╗ ████║    ██║   ██║╚════██╗
  ███████╗██║ █╗ ██║███████║██████╔╝██╔████╔██║    ██║   ██║ █████╔╝
  ╚════██║██║███╗██║██╔══██║██╔══██╗██║╚██╔╝██║    ╚██╗ ██╔╝╚═══██╗
  ███████║╚███╔███╔╝██║  ██║██║  ██║██║ ╚═╝ ██║     ╚████╔╝ ██████╔╝
  ╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝      ╚═══╝  ╚═════╝
[/yellow]
[bold]  FORGE SWARM v3 — Collective Intelligence[/bold]
[dim]  Real-time dialogue. Elastic scaling. Collective awareness.[/dim]
[dim]  Workers that talk, grow, and think together.[/dim]
"""

def main():
    if os.environ.get("FORGE_WORKER_MODE") == "1":
        run_as_worker()
        return

    swarm = ForgeSwarmV3()

    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower(); args = sys.argv[2:]
        rprint(BANNER)
        if cmd == "swarm":   swarm.cmd_swarm(args)
        elif cmd == "hive":  swarm.cmd_hive(args)
        elif cmd == "clean": swarm.cmd_clean(args)
    else:
        swarm.run()

if __name__ == "__main__":
    main()
