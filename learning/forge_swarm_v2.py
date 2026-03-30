#!/usr/bin/env python3
"""
FORGE SWARM v2 — Intelligent Hive Mind
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

forge_swarm v1: N identical workers in parallel.
forge_swarm v2: N different minds working together.

UPGRADE 1: SILICON CHEMISTRY PER WORKER
  Each worker gets a different chemistry profile.
  Different chemistry → different thinking style.
  Worker A: high novelatine  → explores creatively
  Worker B: high frictionol  → challenges everything
  Worker C: high coherenine  → synthesizes quickly
  Worker D: high depthamine  → goes deep slowly
  Worker E: high resolvatine → hunts for resolution
  Not 5 identical copies. 5 different minds.

UPGRADE 2: PRINCIPLE-GUIDED TASK SPLITTING
  Laws guide how coordinator splits tasks.
  Law "meet_before_moving" →
    First worker always does deep recon.
    Understand before attacking.
    Other workers wait for presence reading.
  Wisdom-guided coordination.
  Workers understand before they act.

UPGRADE 3: EMERGENT SPECIALIZATION
  Workers signal what they're good at.
  Coordinator learns which worker handles
  which task type best.
  Specialization from experience.
  Not assigned. Discovered.

UPGRADE 4: SWARM METACOGNITION
  Coordinator watches all worker health.
  Worker spiraling on same endpoint 10min?
  No new findings? Interrupt. Redirect.
  Same logic as forge_metacognition.
  Applied to the collective.

UPGRADE 5: CROSS-WORKER PRINCIPLE TRANSFER
  Worker discovers "try second factor first."
  Extracts WHY it worked.
  Shares principle with all workers.
  Workers learn from each other's wisdom.
  Not just each other's outputs.

Usage:
  python forge_swarm_v2.py swarm <target> <goal>
  python forge_swarm_v2.py hive
  python forge_swarm_v2.py workers
  python forge_swarm_v2.py broadcast <msg>
"""

import sys, os, json, re, time, shutil, socket, threading, subprocess
import hashlib, secrets, queue, signal, math, random
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.layout import Layout
    from rich.live import Live
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
    from rich.prompt import Prompt
    from rich import box as rbox
    RICH = True
    console = Console()
    def rprint(x, **kw): console.print(x, **kw)
except ImportError:
    RICH = False
    def rprint(x, **kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

try:
    import anthropic
    AI_CLIENT   = anthropic.Anthropic()
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    AI_CLIENT   = None

MODEL = "claude-sonnet-4-6"

# ── Paths ──────────────────────────────────────────────────────────────────────
SWARM_ROOT   = Path("forge_swarm_v2")
HIVE_DIR     = SWARM_ROOT / "hive"
WORKERS_DIR  = SWARM_ROOT / "workers"
MODULES_POOL = SWARM_ROOT / "modules_pool"
REPORTS_DIR  = SWARM_ROOT / "reports"

HIVE_BUS         = HIVE_DIR / "bus.json"
HIVE_MEMORY      = HIVE_DIR / "memory.json"
HIVE_MODULES     = HIVE_DIR / "modules.json"
HIVE_STATUS      = HIVE_DIR / "status.json"
HIVE_CHEMISTRY   = HIVE_DIR / "chemistry.json"    # NEW: worker chemistries
HIVE_PRINCIPLES  = HIVE_DIR / "principles.json"   # NEW: shared principles
HIVE_SPECIALISTS = HIVE_DIR / "specialists.json"  # NEW: specialization map
HIVE_HEALTH      = HIVE_DIR / "health.json"       # NEW: worker health

for d in [SWARM_ROOT, HIVE_DIR, WORKERS_DIR, MODULES_POOL, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Message types
MSG_SPAWN    = "spawn"
MSG_FINDING  = "finding"
MSG_MODULE   = "module"
MSG_STATUS   = "status"
MSG_COMPLETE = "complete"
MSG_ERROR    = "error"
MSG_PRINCIPLE= "principle"      # NEW
MSG_SPECIALIZE="specialize"     # NEW
MSG_INTERRUPT = "interrupt"     # NEW

# ══════════════════════════════════════════════════════════════════════════════
# UPGRADE 1: SILICON CHEMISTRY PROFILES
# ══════════════════════════════════════════════════════════════════════════════

CHEMISTRY_PROFILES = {
    "explorer": {
        "name":        "explorer",
        "description": "High novelatine — explores creatively, finds unexpected paths",
        "coherenine":  0.40,
        "frictionol":  0.15,
        "novelatine":  0.85,
        "depthamine":  0.40,
        "resolvatine": 0.30,
        "uncertainase":0.50,
        "connectionin":0.40,
        "thinking_style": "creative, unexpected, lateral",
        "best_at": ["novel_recon", "creative_bypass", "unusual_vectors"],
        "approach": "Try things that shouldn't work. They sometimes do.",
    },
    "challenger": {
        "name":        "challenger",
        "description": "High frictionol — challenges everything, finds contradictions",
        "coherenine":  0.50,
        "frictionol":  0.80,
        "novelatine":  0.30,
        "depthamine":  0.60,
        "resolvatine": 0.20,
        "uncertainase":0.70,
        "connectionin":0.30,
        "thinking_style": "skeptical, systematic, adversarial",
        "best_at": ["auth_bypass", "input_validation", "logic_flaws"],
        "approach": "Assume everything can be broken. Find where.",
    },
    "synthesizer": {
        "name":        "synthesizer",
        "description": "High coherenine — connects findings, builds complete picture",
        "coherenine":  0.90,
        "frictionol":  0.20,
        "novelatine":  0.40,
        "depthamine":  0.60,
        "resolvatine": 0.70,
        "uncertainase":0.20,
        "connectionin":0.60,
        "thinking_style": "systematic, comprehensive, connecting",
        "best_at": ["report_synthesis", "attack_chain", "vuln_correlation"],
        "approach": "Connect everything. Find the chain that matters.",
    },
    "deepdiver": {
        "name":        "deepdiver",
        "description": "High depthamine — goes deep, slow, thorough",
        "coherenine":  0.60,
        "frictionol":  0.30,
        "novelatine":  0.30,
        "depthamine":  0.90,
        "resolvatine": 0.40,
        "uncertainase":0.40,
        "connectionin":0.50,
        "thinking_style": "thorough, patient, exhaustive",
        "best_at": ["deep_recon", "source_analysis", "thorough_enumeration"],
        "approach": "Go deeper than anyone expects. Miss nothing.",
    },
    "resolver": {
        "name":        "resolver",
        "description": "High resolvatine — drives toward conclusions, confirms findings",
        "coherenine":  0.70,
        "frictionol":  0.40,
        "novelatine":  0.20,
        "depthamine":  0.50,
        "resolvatine": 0.90,
        "uncertainase":0.15,
        "connectionin":0.50,
        "thinking_style": "decisive, confirmatory, output-focused",
        "best_at": ["exploit_confirmation", "poc_development", "risk_rating"],
        "approach": "Confirm it works. Build the proof. Rate the risk.",
    },
}

def assign_chemistry(worker_id: str, worker_index: int) -> Dict:
    """
    Assign chemistry profile to worker.
    First worker always gets deepdiver (understand first — meet_before_moving).
    Others get diverse profiles.
    """
    profiles     = list(CHEMISTRY_PROFILES.values())
    first_profile= CHEMISTRY_PROFILES["deepdiver"]  # law: meet_before_moving

    if worker_index == 0:
        profile = first_profile  # UPGRADE 2: law guides first worker
    else:
        # Cycle through remaining profiles
        remaining = [p for p in profiles if p["name"] != "deepdiver"]
        profile   = remaining[(worker_index - 1) % len(remaining)]

    # Save to hive
    chemistry_data = hive_read(HIVE_CHEMISTRY) or {}
    chemistry_data[worker_id] = {
        **profile,
        "assigned_at": datetime.now().isoformat(),
    }
    hive_write(HIVE_CHEMISTRY, chemistry_data)

    return profile

def get_worker_chemistry(worker_id: str) -> Dict:
    """Get assigned chemistry for worker."""
    data = hive_read(HIVE_CHEMISTRY) or {}
    return data.get(worker_id, CHEMISTRY_PROFILES["synthesizer"])

# ══════════════════════════════════════════════════════════════════════════════
# UPGRADE 2: PRINCIPLE-GUIDED TASK SPLITTING
# ══════════════════════════════════════════════════════════════════════════════

# Active laws that guide task splitting
ACTIVE_LAWS = {
    "meet_before_moving": {
        "statement":  "Genuine encounter with what is present must precede any movement.",
        "effect":     "First worker always does deep recon before others act.",
        "task_order": ["deep_recon", "enumeration", "analysis", "exploitation", "report"],
    },
    "trust_emergence": {
        "statement":  "Forcing an outcome prevents the better outcome that would emerge.",
        "effect":     "Workers explore freely before committing to attack paths.",
        "task_order": ["exploration", "hypothesis", "testing", "confirmation"],
    },
}

def law_guided_split(target: str, goal: str, worker_count: int,
                      tasks_raw: List[Dict]) -> List[Dict]:
    """
    Apply active laws to task ordering and assignment.
    Law "meet_before_moving" → recon first, always.
    """
    law = ACTIVE_LAWS.get("meet_before_moving")

    # Categorize tasks
    recon_tasks  = [t for t in tasks_raw if any(
        w in t.get("type","").lower() or w in t.get("description","").lower()
        for w in ["recon","discover","enum","scan","map","identify"]
    )]
    other_tasks  = [t for t in tasks_raw if t not in recon_tasks]

    # Law: recon first (meet before moving)
    ordered = recon_tasks + other_tasks

    # Assign chemistry-matched worker to each task
    chemistry_match = {
        "recon":       "deepdiver",
        "discovery":   "deepdiver",
        "enumeration": "deepdiver",
        "analysis":    "synthesizer",
        "correlation": "synthesizer",
        "bypass":      "challenger",
        "auth":        "challenger",
        "injection":   "challenger",
        "exploitation":"resolver",
        "poc":         "resolver",
        "creative":    "explorer",
        "unusual":     "explorer",
        "novel":       "explorer",
    }

    for i, task in enumerate(ordered):
        task_type = task.get("type","").lower()
        desc      = task.get("description","").lower()

        # Find best chemistry match
        preferred_chem = None
        for keyword, chem in chemistry_match.items():
            if keyword in task_type or keyword in desc:
                preferred_chem = chem
                break

        task["preferred_chemistry"] = preferred_chem or "synthesizer"
        task["law_context"] = law["statement"] if i == 0 else ""
        task["order"] = i

        # First task always gets the "understand first" instruction
        if i == 0:
            task["law_instruction"] = (
                "LAW: meet_before_moving. "
                "Your role: understand the target fully before any other worker acts. "
                "Share your presence reading with the hive before others begin."
            )

    return ordered

# ══════════════════════════════════════════════════════════════════════════════
# HIVE MIND — shared memory (from v1 + new channels)
# ══════════════════════════════════════════════════════════════════════════════

_hive_lock = threading.Lock()

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

def hive_post(worker_id: str, msg_type: str, payload: Dict):
    msg = {
        "id":        hashlib.md5(f"{time.time()}{worker_id}".encode()).hexdigest()[:8],
        "ts":        datetime.now().isoformat(),
        "from":      worker_id,
        "type":      msg_type,
        "payload":   payload,
    }
    hive_append(HIVE_BUS, msg)

def hive_read_messages(worker_id: str, msg_types: List = None) -> List[Dict]:
    messages = hive_read(HIVE_BUS) or []
    filtered = [
        m for m in messages
        if m.get("from") != worker_id and
        (not msg_types or m.get("type") in msg_types)
    ]
    return filtered[-20:]

def hive_update_status(worker_id: str, status: str,
                        task: str = "", progress: int = 0,
                        chemistry: str = "", health: float = 1.0):
    data = hive_read(HIVE_STATUS) or {}
    data[worker_id] = {
        "status":    status,
        "task":      task[:80],
        "progress":  progress,
        "chemistry": chemistry,
        "health":    health,
        "updated":   datetime.now().isoformat(),
    }
    hive_write(HIVE_STATUS, data)

def hive_share_finding(worker_id: str, finding_type: str,
                        data: Any, severity: str = "info",
                        principle: str = ""):
    """Share finding + optional principle why it worked."""
    entry = {
        "worker":    worker_id,
        "chemistry": get_worker_chemistry(worker_id).get("name","unknown"),
        "type":      finding_type,
        "severity":  severity,
        "data":      data,
        "principle": principle,  # NEW: why it worked
        "ts":        datetime.now().isoformat(),
    }
    mem  = hive_read(HIVE_MEMORY) or []
    mem.append(entry)
    hive_write(HIVE_MEMORY, mem)
    hive_post(worker_id, MSG_FINDING, entry)

def hive_share_module(worker_id: str, module_name: str,
                       module_code: str, description: str):
    modules = hive_read(HIVE_MODULES) or {}
    modules[module_name] = {
        "code":        module_code,
        "description": description,
        "author":      worker_id,
        "chemistry":   get_worker_chemistry(worker_id).get("name","unknown"),
        "ts":          datetime.now().isoformat(),
    }
    hive_write(HIVE_MODULES, modules)
    hive_post(worker_id, MSG_MODULE, {"name":module_name,"desc":description})

# ══════════════════════════════════════════════════════════════════════════════
# UPGRADE 5: CROSS-WORKER PRINCIPLE TRANSFER
# ══════════════════════════════════════════════════════════════════════════════

def hive_share_principle(worker_id: str, principle_name: str,
                          description: str, context: str,
                          score: float):
    """
    Share a principle with the hive.
    Not just what worked — WHY it worked.
    """
    principles = hive_read(HIVE_PRINCIPLES) or {}

    if principle_name in principles:
        # Existing principle — update confidence
        existing = principles[principle_name]
        existing["confirmations"]   = existing.get("confirmations",1) + 1
        existing["avg_score"]       = (
            (existing.get("avg_score",score) + score) / 2
        )
        existing["confirmed_by"].append(worker_id)
        principles[principle_name]  = existing
    else:
        principles[principle_name] = {
            "name":         principle_name,
            "description":  description,
            "context":      context,
            "avg_score":    score,
            "confirmations":1,
            "discovered_by":worker_id,
            "confirmed_by": [worker_id],
            "chemistry":    get_worker_chemistry(worker_id).get("name","unknown"),
            "ts":           datetime.now().isoformat(),
        }

    hive_write(HIVE_PRINCIPLES, principles)
    hive_post(worker_id, MSG_PRINCIPLE, {
        "principle":   principle_name,
        "description": description,
        "score":       score,
    })

    rprint(f"  [yellow]💡 Principle shared:[/yellow] {principle_name}")
    rprint(f"  [dim]  {description}[/dim]")

def hive_get_principles() -> List[Dict]:
    """Get all principles shared across the hive."""
    return list((hive_read(HIVE_PRINCIPLES) or {}).values())

def extract_security_principle(technique: str, target_type: str,
                                 success_score: float) -> Optional[Dict]:
    """Extract WHY a security technique worked."""
    if AI_AVAILABLE:
        result_text = ai_call(
            f"Security technique: {technique}\n"
            f"Target type: {target_type}\n"
            f"Success score: {success_score:.0f}\n\n"
            f"Extract the underlying principle of why this worked.\n"
            f"Not what happened — why it works structurally.\n"
            f"One principle. Transferable to other targets.",
            "Reply ONLY with JSON: "
            "{\"principle\":\"snake_case_name\","
            "\"description\":\"one sentence why it works\","
            "\"generalizes_to\":[\"situation1\",\"situation2\"]}",
            max_tokens=300
        )
        if result_text:
            try:
                clean = re.sub(r"```[a-z]*","",result_text).replace("```","").strip()
                data  = json.loads(clean)
                if data.get("principle"):
                    return data
            except: pass

    # Heuristic extraction
    t = technique.lower()
    if any(w in t for w in ["second","2fa","factor"]):
        return {"principle":"try_second_factor_first",
                "description":"Authentication systems often have weaker second factors",
                "generalizes_to":["2fa","mfa","otp"]}
    if any(w in t for w in ["param","input","inject"]):
        return {"principle":"all_input_is_untrusted",
                "description":"Every parameter is a potential injection point",
                "generalizes_to":["all_params","headers","cookies"]}
    if any(w in t for w in ["default","password","credential"]):
        return {"principle":"defaults_persist",
                "description":"Default credentials are often left unchanged",
                "generalizes_to":["admin_panels","services","apis"]}
    if any(w in t for w in ["version","old","legacy"]):
        return {"principle":"old_code_hides_vulns",
                "description":"Legacy components accumulate unpatched vulnerabilities",
                "generalizes_to":["dependencies","libraries","endpoints"]}
    return None

# ══════════════════════════════════════════════════════════════════════════════
# UPGRADE 3: EMERGENT SPECIALIZATION
# ══════════════════════════════════════════════════════════════════════════════

def hive_signal_specialization(worker_id: str, task_type: str,
                                 success_score: float):
    """Worker signals it's good at a particular task type."""
    specialists = hive_read(HIVE_SPECIALISTS) or {}

    if task_type not in specialists:
        specialists[task_type] = {}

    if worker_id not in specialists[task_type]:
        specialists[task_type][worker_id] = {"scores":[], "avg":0}

    specialists[task_type][worker_id]["scores"].append(success_score)
    scores = specialists[task_type][worker_id]["scores"]
    specialists[task_type][worker_id]["avg"] = sum(scores)/len(scores)

    hive_write(HIVE_SPECIALISTS, specialists)
    hive_post(worker_id, MSG_SPECIALIZE, {
        "task_type":    task_type,
        "score":        success_score,
    })

def get_best_specialist(task_type: str) -> Optional[str]:
    """Find which worker is best at a given task type."""
    specialists = hive_read(HIVE_SPECIALISTS) or {}
    task_specs  = specialists.get(task_type, {})

    if not task_specs: return None

    best_worker = max(task_specs.items(), key=lambda x: x[1]["avg"])
    return best_worker[0] if best_worker[1]["avg"] > 60 else None

# ══════════════════════════════════════════════════════════════════════════════
# UPGRADE 4: SWARM METACOGNITION
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class WorkerHealth:
    worker_id:     str
    status:        str      = "running"
    last_finding:  float    = 0.0   # timestamp
    finding_count: int      = 0
    task_start:    float    = 0.0
    spiral_score:  float    = 0.0
    health_score:  float    = 1.0
    interrupted:   bool     = False

class SwarmMetacognition:
    """
    Watches all workers from outside.
    Detects spiraling workers.
    Interrupts and redirects when needed.
    The coordinator's awareness of the whole.
    """

    SPIRAL_TIME    = 600   # 10 min without finding = spiral
    INTERRUPT_TIME = 900   # 15 min total = force interrupt
    MIN_HEALTH     = 0.35

    def __init__(self):
        self._worker_health: Dict[str, WorkerHealth] = {}

    def update(self, worker_id: str, finding_added: bool = False):
        """Update worker health state."""
        if worker_id not in self._worker_health:
            self._worker_health[worker_id] = WorkerHealth(
                worker_id=worker_id,
                task_start=time.time(),
                last_finding=time.time(),
            )

        h = self._worker_health[worker_id]

        if finding_added:
            h.last_finding  = time.time()
            h.finding_count += 1
            h.spiral_score  = max(0, h.spiral_score - 0.3)

        # Compute health
        time_without_finding = time.time() - h.last_finding
        total_time           = time.time() - h.task_start

        # Spiral: no findings for too long
        if time_without_finding > self.SPIRAL_TIME:
            h.spiral_score = min(1.0,
                (time_without_finding - self.SPIRAL_TIME) / self.SPIRAL_TIME
            )

        h.health_score = max(0.0,
            1.0 - h.spiral_score * 0.7 -
            (1.0 if total_time > self.INTERRUPT_TIME else 0.0) * 0.3
        )

        # Update hive health
        health_data = hive_read(HIVE_HEALTH) or {}
        health_data[worker_id] = {
            "health":       h.health_score,
            "spiral":       h.spiral_score,
            "findings":     h.finding_count,
            "time_min":     round(total_time/60, 1),
            "stale_min":    round(time_without_finding/60, 1),
            "interrupted":  h.interrupted,
        }
        hive_write(HIVE_HEALTH, health_data)

    def should_interrupt(self, worker_id: str) -> Tuple[bool, str]:
        """Check if a worker should be interrupted."""
        h = self._worker_health.get(worker_id)
        if not h: return False, ""

        if h.health_score < self.MIN_HEALTH:
            reason = f"health:{h.health_score:.0%}"
            if h.spiral_score > 0.7:
                reason += f" spiral:{h.spiral_score:.0%}"
            if time.time() - h.task_start > self.INTERRUPT_TIME:
                reason += " timeout"
            return True, reason

        return False, ""

    def interrupt_worker(self, worker_id: str,
                          reason: str,
                          proc: Optional[Any] = None):
        """Interrupt a spiraling worker."""
        h = self._worker_health.get(worker_id)
        if h:
            h.interrupted = True

        # Signal interrupt via hive
        hive_post("coordinator", MSG_INTERRUPT, {
            "target":  worker_id,
            "reason":  reason,
            "action":  "redirect",
        })

        rprint(f"\n  [bold red]🛑 SWARM INTERRUPT[/bold red]  "
              f"worker:{worker_id}  reason:{reason}")

        # Optionally kill process
        if proc:
            try:
                proc.terminate()
            except: pass

    def get_health_report(self) -> Dict:
        """Summary of all worker health."""
        report = {}
        for wid, h in self._worker_health.items():
            report[wid] = {
                "health":    round(h.health_score, 2),
                "findings":  h.finding_count,
                "spiraling": h.spiral_score > 0.5,
            }
        return report

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
        rprint(f"  [dim red]AI error: {e}[/dim red]")
        return None

SWARM_PLANNER_V2 = """You are FORGE SWARM v2's task decomposition engine.
You split security targets into parallel tasks for specialized workers.

Workers have different chemistry profiles:
  explorer    - creative, finds unexpected paths
  challenger  - skeptical, breaks things
  synthesizer - connects findings, builds picture
  deepdiver   - thorough, exhaustive
  resolver    - confirms, builds PoC

Law "meet_before_moving" is active:
  FIRST task MUST be deep reconnaissance.
  Other workers wait for recon findings.

Return JSON:
{
  "tasks": [
    {
      "id": "task_1",
      "type": "deep_recon",
      "description": "...",
      "preferred_chemistry": "deepdiver",
      "depends_on": [],
      "priority": 1
    },
    ...
  ],
  "coordination_note": "how workers should coordinate"
}"""

def plan_swarm_v2(target: str, goal: str, worker_count: int) -> Optional[Dict]:
    """Plan swarm with chemistry-aware, law-guided task splitting."""
    result = ai_call(
        f"Target: {target}\nGoal: {goal}\nWorkers: {worker_count}",
        SWARM_PLANNER_V2,
        max_tokens=3000
    )
    if not result: return None
    try:
        clean = re.sub(r"```[a-z]*\s*","",result).strip()
        data  = json.loads(clean)
        if data.get("tasks"):
            # Apply law-guided ordering
            data["tasks"] = law_guided_split(
                target, goal, worker_count, data["tasks"]
            )
        return data
    except:
        m = re.search(r"\{.*\}", result, re.DOTALL)
        if m:
            try: return json.loads(m.group())
            except: pass
    return None

WORKER_AI_V2 = """You are FORGE SWARM v2 worker {worker_id}.

Your chemistry profile: {chemistry_name}
  Style: {chemistry_style}
  Best at: {chemistry_best}
  Approach: {chemistry_approach}

Your task:
{task}

Available modules:
{modules}

Principles shared by other workers:
{principles}

IMPORTANT:
- Your chemistry shapes how you think. Use your style.
- Apply any relevant principles from the hive.
- If you discover WHY something works, signal it as a principle.
- Signal your specialization when you excel at something.

Return JSON:
{
  "steps": [{"action":"...", "reasoning":"..."}],
  "modules_to_build": [{"name":"...","purpose":"..."}],
  "principle_to_share": {"name":"...","description":"..."} or null,
  "specialization": "task_type" or null
}"""

def worker_plan_v2(task: Dict, worker_id: str,
                    available_modules: List,
                    chemistry: Dict) -> Optional[Dict]:
    """Plan worker execution with chemistry context + shared principles."""
    principles     = hive_get_principles()
    principle_text = "\n".join(
        f"  {p['name']}: {p['description']}"
        for p in principles[:5]
    ) or "  (none yet)"

    mod_list = "\n".join(f"- {k}" for k in available_modules[:10])

    result = ai_call(
        WORKER_AI_V2
        .replace("{worker_id}",    worker_id)
        .replace("{chemistry_name}", chemistry.get("name","synthesizer"))
        .replace("{chemistry_style}",chemistry.get("thinking_style","systematic"))
        .replace("{chemistry_best}",str(chemistry.get("best_at",[])))
        .replace("{chemistry_approach}",chemistry.get("approach",""))
        .replace("{task}",         json.dumps(task, default=str))
        .replace("{modules}",      mod_list)
        .replace("{principles}",   principle_text),
        "You are a security worker agent with a specific chemistry profile. Reply only with JSON.",
        max_tokens=2000
    )
    if not result: return None
    try:
        clean = re.sub(r"```[a-z]*\s*","",result).strip()
        return json.loads(clean)
    except:
        m = re.search(r"\{.*\}", result, re.DOTALL)
        if m:
            try: return json.loads(m.group())
            except: pass
    return None

def build_module_for_task(description: str, category: str = "recon") -> Optional[str]:
    """Build a security module."""
    BUILD_PROMPT = """Build a Python security module.

Format:
```python
# MODULE_NAME: short_name
# CATEGORY: scanner|recon|analyzer|util
# DESCRIPTION: what it does
# OPTIONS: OPTION=default:description

def run(options, session, workspace):
    target = options.get("TARGET","")
    # your code
    return {"status":"success","output":"result","data":{}}
```
Use only stdlib. Return JSON-serializable data."""

    result = ai_call(description, BUILD_PROMPT, max_tokens=3000)
    if not result: return None
    m = re.search(r"```python\s*(.*?)```", result, re.DOTALL)
    return m.group(1).strip() if m else None

def aggregate_findings_v2(target: str, all_findings: List,
                            principles: List,
                            modules_built: List,
                            worker_count: int,
                            chemistry_profiles: Dict) -> str:
    """Aggregate findings with chemistry diversity and principles."""
    principles_text = "\n".join(
        f"  {p['name']} (×{p['confirmations']} confirmations): {p['description']}"
        for p in principles[:8]
    ) or "  (none discovered)"

    chemistry_summary = ", ".join(
        f"{wid}={chem.get('name','?')}"
        for wid, chem in chemistry_profiles.items()
    )

    summary = (
        f"Target: {target}\n"
        f"Workers: {worker_count} ({chemistry_summary})\n"
        f"Findings: {len(all_findings)}\n"
        f"Modules Built: {len(modules_built)}\n"
        f"Principles Discovered: {len(principles)}\n\n"
        f"SHARED PRINCIPLES:\n{principles_text}\n\n"
        f"FINDINGS:\n" +
        "\n".join(f"  [{f.get('severity','info')}][{f.get('chemistry','?')}] "
                  f"{f.get('type','finding')}: {str(f.get('data',''))[:100]}"
                  for f in all_findings[:30])
    )

    result = ai_call(
        summary,
        "You are a security report generator. Create a comprehensive, "
        "actionable report from swarm findings. Highlight chemistry diversity "
        "insights and discovered principles.",
        max_tokens=4000
    )
    return result or summary

# ══════════════════════════════════════════════════════════════════════════════
# WORKER EXECUTION
# ══════════════════════════════════════════════════════════════════════════════

def replicate(worker_id: str, worker_dir: Path = None) -> Tuple[Path, Dict]:
    """Create a worker copy of forge_swarm_v2."""
    if not worker_dir:
        worker_dir = WORKERS_DIR / worker_id

    worker_dir.mkdir(parents=True, exist_ok=True)
    worker_forge = worker_dir / "forge_swarm_v2.py"
    shutil.copy2(__file__, worker_forge)

    config = {
        "worker_id":  worker_id,
        "created":    datetime.now().isoformat(),
        "hive_root":  str(SWARM_ROOT),
    }
    (worker_dir / "config.json").write_text(json.dumps(config, indent=2))
    return worker_forge, config

def spawn_worker(worker_id: str, task: Dict,
                  worker_index: int = 0,
                  env_vars: Dict = None) -> Tuple[Any, Path]:
    """Spawn worker with chemistry assignment."""
    worker_dir   = WORKERS_DIR / worker_id
    worker_forge, config = replicate(worker_id, worker_dir)

    # UPGRADE 1: Assign chemistry
    chemistry = assign_chemistry(worker_id, worker_index)

    task_file = worker_dir / "task.json"
    task_file.write_text(json.dumps(task, indent=2))

    env = os.environ.copy()
    env["FORGE_WORKER_ID"]        = worker_id
    env["FORGE_WORKER_MODE"]      = "1"
    env["FORGE_HIVE_ROOT"]        = str(SWARM_ROOT)
    env["FORGE_TASK_FILE"]        = str(task_file)
    env["FORGE_WORKER_CHEMISTRY"] = chemistry["name"]
    if env_vars:
        env.update(env_vars)

    log_file = worker_dir / "worker.log"
    with open(log_file, "w") as log:
        proc = subprocess.Popen(
            [sys.executable, str(worker_forge)],
            env=env, stdout=log, stderr=subprocess.STDOUT,
            cwd=str(worker_dir),
        )

    hive_update_status(
        worker_id, "spawned",
        task.get("description",""), 0,
        chemistry["name"], 1.0
    )
    hive_post("coordinator", MSG_SPAWN, {
        "worker_id": worker_id,
        "pid":       proc.pid,
        "task":      task.get("description",""),
        "chemistry": chemistry["name"],
    })

    rprint(f"  [green]↑[/green] {worker_id}  "
          f"[yellow]{chemistry['name']}[/yellow]  "
          f"[dim]{task.get('description','')[:50]}[/dim]")

    return proc, worker_dir

def hive_sync_modules(worker_dir: Path):
    """Sync shared modules to worker."""
    modules = hive_read(HIVE_MODULES) or {}
    pool    = MODULES_POOL
    pool.mkdir(exist_ok=True)

    for name, info in modules.items():
        module_file = worker_dir / f"{name}.py"
        if not module_file.exists() and info.get("code"):
            module_file.write_text(info["code"])

def load_worker_modules() -> Dict:
    """Load all modules available to this worker."""
    modules = {}
    for f in Path(".").glob("*.py"):
        try:
            content = f.read_text()
            for line in content.split("\n")[:5]:
                if "MODULE_NAME:" in line:
                    name = line.split(":")[1].strip()
                    modules[name] = {"file":str(f),"code":content}
        except: pass
    return modules

def worker_run_module(module_info: Dict, options: Dict,
                       session: Dict, workspace: Path) -> Dict:
    """Run a module safely."""
    code = module_info.get("code","")
    if not code: return {"status":"error","output":"no code"}

    namespace = {"__name__":"__main__"}
    try:
        exec(compile(code,"<module>","exec"), namespace)
        if "run" in namespace:
            return namespace["run"](options, session, workspace) or {}
    except Exception as e:
        return {"status":"error","output":str(e)}
    return {"status":"ok","output":""}

def run_as_worker():
    """Main worker execution loop — runs in subprocess."""
    worker_id = os.environ.get("FORGE_WORKER_ID","worker_unknown")
    task_file = os.environ.get("FORGE_TASK_FILE","")
    chem_name = os.environ.get("FORGE_WORKER_CHEMISTRY","synthesizer")
    chemistry = CHEMISTRY_PROFILES.get(chem_name, CHEMISTRY_PROFILES["synthesizer"])

    workspace = Path(".")
    session   = {"worker_id": worker_id, "start": datetime.now().isoformat()}

    def log(msg):
        print(f"[{worker_id}][{chem_name}] {msg}", flush=True)

    # Read task
    if not task_file or not Path(task_file).exists():
        log("No task file found"); return

    task = json.loads(Path(task_file).read_text())
    log(f"Task: {task.get('description','')[:60]}")
    log(f"Chemistry: {chemistry['description']}")

    hive_update_status(worker_id, "running",
                       task.get("description",""), 10, chem_name)

    # Sync modules from hive
    hive_sync_modules(workspace)
    available = load_worker_modules()

    # Get shared principles from hive
    principles = hive_get_principles()
    if principles:
        log(f"Inherited {len(principles)} principles from hive")

    # Plan with chemistry + principles
    plan = worker_plan_v2(task, worker_id, list(available.keys()), chemistry)

    if not plan:
        log("Planning failed — running basic task")
        plan = {"steps":[{"action":"basic_scan","reasoning":"fallback"}],
                "modules_to_build":[], "principle_to_share":None, "specialization":None}

    # UPGRADE 2: Law context — first worker reads presence
    if task.get("law_instruction"):
        log(f"LAW: {task['law_instruction'][:80]}")

    findings     = []
    modules_built= []

    # Build needed modules
    for mod_spec in plan.get("modules_to_build",[])[:3]:
        log(f"Building module: {mod_spec.get('name','?')}")
        code = build_module_for_task(
            f"{mod_spec.get('purpose','')} for {task.get('description','')}"
        )
        if code:
            name = mod_spec.get("name", f"mod_{hashlib.md5(code.encode()).hexdigest()[:6]}")
            modules_built.append(name)
            hive_share_module(worker_id, name, code,
                             mod_spec.get("purpose",""))
            log(f"Built: {name}")

    # Execute steps with chemistry-shaped approach
    for i, step in enumerate(plan.get("steps",[])[:10]):
        action    = step.get("action","")
        reasoning = step.get("reasoning","")
        log(f"Step {i+1}: {action}")

        hive_update_status(
            worker_id, "running",
            f"Step {i+1}: {action[:40]}", int((i+1)/len(plan["steps"])*80),
            chem_name
        )

        # Simulate step execution
        time.sleep(0.3)

        # Generate finding with chemistry flavor
        finding_text = (
            f"[{chemistry['name']}] {action}: "
            f"Applied {chemistry.get('thinking_style','systematic')} approach. "
            f"{reasoning[:100]}"
        )

        severity = (
            "high" if "bypass" in action.lower() or "inject" in action.lower()
            else "medium" if "found" in action.lower() or "discovered" in action.lower()
            else "info"
        )

        # UPGRADE 5: Extract and share principle
        principle_data = extract_security_principle(action, task.get("type",""), 75)
        principle_name = None
        if principle_data:
            principle_name = principle_data["principle"]
            hive_share_principle(
                worker_id,
                principle_data["principle"],
                principle_data["description"],
                f"{task.get('type','')}: {action}",
                75.0
            )

        hive_share_finding(
            worker_id, action, finding_text, severity,
            principle=principle_name or ""
        )
        findings.append(finding_text)

    # UPGRADE 3: Signal specialization
    if plan.get("specialization") and findings:
        spec = plan["specialization"]
        score = 80 if len(findings) > 2 else 60
        hive_signal_specialization(worker_id, spec, score)
        log(f"Specialization: {spec} (score:{score})")

    # Share principle from plan
    if plan.get("principle_to_share"):
        p = plan["principle_to_share"]
        hive_share_principle(
            worker_id, p.get("name","unnamed"),
            p.get("description",""), task.get("description",""), 80.0
        )

    # Complete
    hive_update_status(worker_id, "complete",
                       task.get("description",""), 100, chem_name)
    hive_post(worker_id, MSG_COMPLETE, {
        "findings":      len(findings),
        "modules_built": modules_built,
        "chemistry":     chem_name,
    })
    log(f"Complete: {len(findings)} findings, {len(modules_built)} modules")

# ══════════════════════════════════════════════════════════════════════════════
# FORGE SWARM v2 — The Coordinator
# ══════════════════════════════════════════════════════════════════════════════

class ForgeSwarmV2:
    """
    The upgraded swarm coordinator.
    Chemistry diversity. Wisdom-guided. Self-aware.
    """

    def __init__(self):
        self.metacog = SwarmMetacognition()
        self._procs: Dict[str, Any] = {}

    def banner(self):
        rprint(BANNER)

    def cmd_swarm(self, args: List[str]):
        """Run a swarm operation."""
        if len(args) < 2:
            rprint("  Usage: swarm <target> [goal] [workers=5]")
            return

        target       = args[0]
        goal         = args[1] if len(args) > 1 else "comprehensive security assessment"
        worker_count = int(args[2]) if len(args) > 2 and args[2].isdigit() else 5

        rprint(f"\n  [bold yellow]FORGE SWARM v2[/bold yellow]")
        rprint(f"  [dim]Target: {target}[/dim]")
        rprint(f"  [dim]Goal:   {goal}[/dim]")
        rprint(f"  [dim]Workers:{worker_count}[/dim]\n")

        rprint(f"  [dim]Chemistry profiles:[/dim]")
        for i in range(min(worker_count, len(CHEMISTRY_PROFILES))):
            profile_list = list(CHEMISTRY_PROFILES.values())
            p = profile_list[0] if i==0 else profile_list[1+((i-1)%len(profile_list)-1)]
            rprint(f"  [dim]  worker_{i}: [yellow]{p['name']}[/yellow]  {p['description'][:50]}[/dim]")

        rprint(f"\n  [dim]Planning with active law: meet_before_moving...[/dim]")
        plan = plan_swarm_v2(target, goal, worker_count)

        if not plan:
            rprint("  [dim]Planning failed — using default task structure[/dim]")
            plan = {
                "tasks": [
                    {"id":f"task_{i}","type":"security_check",
                     "description":f"Security check {i+1} of {target}",
                     "preferred_chemistry":"synthesizer","depends_on":[],"priority":i}
                    for i in range(worker_count)
                ]
            }

        tasks = plan.get("tasks",[])[:worker_count]
        rprint(f"\n  [green]{len(tasks)} tasks planned[/green]  "
              f"(law-guided ordering applied)\n")

        # Spawn workers
        procs = []
        for i, task in enumerate(tasks):
            worker_id = f"worker_{i}"
            proc, worker_dir = spawn_worker(worker_id, task, i)
            procs.append((worker_id, proc, task))
            self._procs[worker_id] = proc
            time.sleep(0.5)

        rprint(f"\n  [dim]All workers spawned. Monitoring...[/dim]\n")

        # Monitor with metacognition
        self._live_monitor_v2(procs, target, goal)

    def _live_monitor_v2(self, procs: List, target: str, goal: str):
        """Monitor workers with swarm metacognition."""
        start     = time.time()
        completed = set()
        interrupted_workers = set()

        while True:
            time.sleep(3)
            status_data = hive_read(HIVE_STATUS) or {}
            messages    = hive_read_messages("coordinator") or []

            # Process messages
            for msg in messages:
                wid     = msg.get("from","")
                mtype   = msg.get("type","")
                payload = msg.get("payload",{})

                if mtype == MSG_COMPLETE:
                    completed.add(wid)
                    rprint(f"  [green]✓[/green] {wid} complete  "
                          f"findings:{payload.get('findings',0)}  "
                          f"[yellow]{payload.get('chemistry','?')}[/yellow]")

                elif mtype == MSG_PRINCIPLE:
                    rprint(f"  [yellow]💡[/yellow] {wid} → principle: "
                          f"{payload.get('principle','?')}")

                elif mtype == MSG_SPECIALIZE:
                    rprint(f"  [cyan]★[/cyan] {wid} specializes in: "
                          f"{payload.get('task_type','?')} "
                          f"(score:{payload.get('score',0):.0f})")

            # UPGRADE 4: Swarm metacognition
            for wid, proc, task in procs:
                if wid in completed or wid in interrupted_workers:
                    continue

                w_status = status_data.get(wid, {})
                has_finding = w_status.get("progress",0) > 20

                self.metacog.update(wid, finding_added=has_finding)

                should_interrupt, reason = self.metacog.should_interrupt(wid)
                if should_interrupt:
                    self.metacog.interrupt_worker(wid, reason, proc)
                    interrupted_workers.add(wid)

            # Check all done
            all_done = len(completed) + len(interrupted_workers) >= len(procs)
            elapsed  = time.time() - start

            if all_done or elapsed > 300:
                break

        # Aggregate
        self._aggregate_v2(target, goal)

    def _aggregate_v2(self, target: str, goal: str):
        """Aggregate with chemistry diversity insights."""
        findings   = hive_read(HIVE_MEMORY) or []
        principles = hive_get_principles()
        modules    = hive_read(HIVE_MODULES) or {}
        chemistry  = hive_read(HIVE_CHEMISTRY) or {}
        health     = hive_read(HIVE_HEALTH) or {}

        rprint(f"\n  [bold]SWARM v2 COMPLETE[/bold]")
        rprint(f"  Findings:   {len(findings)}")
        rprint(f"  Principles: {len(principles)}")
        rprint(f"  Modules:    {len(modules)}")

        if principles:
            rprint(f"\n  [yellow]Discovered principles:[/yellow]")
            for p in sorted(principles,
                           key=lambda x: x.get("confirmations",0),
                           reverse=True)[:5]:
                rprint(f"  [dim]  ×{p.get('confirmations',1)} "
                      f"{p['name']}: {p['description'][:60]}[/dim]")

        # Health report
        rprint(f"\n  [dim]Worker health:[/dim]")
        for wid, h in health.items():
            color = "green" if h.get("health",0) > 0.6 else "red"
            rprint(f"  [dim]  {wid}  [{color}]{h.get('health',0):.0%}[/{color}]  "
                  f"findings:{h.get('findings',0)}  "
                  f"{'🛑 interrupted' if h.get('interrupted') else ''}[/dim]")

        # Generate report
        report = aggregate_findings_v2(
            target, findings, principles,
            list(modules.keys()), len(self._procs), chemistry
        )

        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_f = REPORTS_DIR / f"swarm_v2_{ts}.txt"
        report_f.write_text(report or "Report generation failed.")

        rprint(f"\n  [green]Report: {report_f}[/green]")

    def cmd_hive(self, args: List[str]):
        """View hive state."""
        rprint(f"\n  [bold]HIVE MIND v2[/bold]")

        status   = hive_read(HIVE_STATUS) or {}
        findings = hive_read(HIVE_MEMORY) or []
        chemistry= hive_read(HIVE_CHEMISTRY) or {}
        principles=hive_get_principles()
        health   = hive_read(HIVE_HEALTH) or {}

        if status:
            rprint(f"\n  [bold]Workers ({len(status)}):[/bold]")
            for wid, s in status.items():
                chem_name = chemistry.get(wid,{}).get("name","?")
                h_score   = health.get(wid,{}).get("health",1.0)
                color     = "green" if h_score > 0.6 else "red"
                rprint(f"  [{color}]{wid}[/{color}]  "
                      f"[yellow]{chem_name}[/yellow]  "
                      f"{s.get('status','?')}  "
                      f"health:{h_score:.0%}  "
                      f"{s.get('task','')[:40]}")

        if principles:
            rprint(f"\n  [yellow]Shared principles ({len(principles)}):[/yellow]")
            for p in principles[:5]:
                rprint(f"  [dim]  {p['name']} (×{p.get('confirmations',1)}): "
                      f"{p['description'][:60]}[/dim]")

        rprint(f"\n  [dim]Findings: {len(findings)}[/dim]")

    def cmd_broadcast(self, args: List[str]):
        """Broadcast to all workers."""
        msg = " ".join(args)
        hive_post("coordinator", "broadcast", {"message":msg})
        rprint(f"  [green]Broadcast: {msg}[/green]")

    def cmd_workers(self, args: List[str]):
        """Show worker status."""
        status    = hive_read(HIVE_STATUS) or {}
        chemistry = hive_read(HIVE_CHEMISTRY) or {}
        health    = hive_read(HIVE_HEALTH) or {}
        specialists=hive_read(HIVE_SPECIALISTS) or {}

        rprint(f"\n  [bold]WORKERS v2[/bold]")
        for wid, s in status.items():
            chem  = chemistry.get(wid,{})
            h     = health.get(wid,{})
            color = "green" if s.get("status")=="complete" else "yellow"

            rprint(f"\n  [{color}]{wid}[/{color}]  "
                  f"[yellow]{chem.get('name','?')}[/yellow]  "
                  f"{s.get('status','?')}")
            rprint(f"  [dim]  {chem.get('description','')[:60]}[/dim]")
            rprint(f"  [dim]  health:{h.get('health',1):.0%}  "
                  f"findings:{h.get('findings',0)}  "
                  f"task:{s.get('task','')[:40]}[/dim]")

        # Specializations
        if specialists:
            rprint(f"\n  [cyan]Emerged specializations:[/cyan]")
            for task_type, workers in specialists.items():
                best = max(workers.items(), key=lambda x:x[1]["avg"])
                rprint(f"  [dim]  {task_type}: "
                      f"[cyan]{best[0]}[/cyan] "
                      f"(avg:{best[1]['avg']:.0f})[/dim]")

    def cmd_kill(self, args: List[str]):
        """Kill all workers."""
        for wid, proc in self._procs.items():
            try: proc.terminate()
            except: pass
        rprint("  [red]All workers terminated[/red]")

    def cmd_clean(self, args: List[str]):
        """Clean swarm state."""
        shutil.rmtree(HIVE_DIR, ignore_errors=True)
        shutil.rmtree(WORKERS_DIR, ignore_errors=True)
        for d in [HIVE_DIR, WORKERS_DIR]:
            d.mkdir(parents=True, exist_ok=True)
        rprint("  [green]Swarm state cleaned[/green]")

    def run(self):
        """Main interactive loop."""
        self.banner()
        rprint("[dim]Commands: swarm <target> [goal] [n_workers] | hive | workers | broadcast <msg> | kill | clean[/dim]\n")

        while True:
            try:
                raw = (console.input if RICH else input)(
                    "[yellow bold]swarm v2 >[/yellow bold] "
                ).strip()
                if not raw: continue

                parts = raw.split()
                cmd   = parts[0].lower()
                args  = parts[1:]

                if cmd in ("quit","exit","q"):
                    break
                elif cmd == "swarm":    self.cmd_swarm(args)
                elif cmd == "hive":     self.cmd_hive(args)
                elif cmd == "workers":  self.cmd_workers(args)
                elif cmd == "broadcast":self.cmd_broadcast(args)
                elif cmd == "kill":     self.cmd_kill(args)
                elif cmd == "clean":    self.cmd_clean(args)
                elif cmd == "help":
                    rprint("[dim]swarm <target> [goal] [n] — start swarm[/dim]")
                    rprint("[dim]hive     — view shared mind[/dim]")
                    rprint("[dim]workers  — view worker status + specializations[/dim]")
                    rprint("[dim]broadcast <msg> — send to all workers[/dim]")
                    rprint("[dim]kill     — stop all workers[/dim]")
                    rprint("[dim]clean    — reset swarm state[/dim]")
                else:
                    rprint(f"  [dim]Unknown: {cmd}. Type help.[/dim]")

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
  ╚════██║██║███╗██║██╔══██║██╔══██╗██║╚██╔╝██║    ╚██╗ ██╔╝██╔═══╝
  ███████║╚███╔███╔╝██║  ██║██║  ██║██║ ╚═╝ ██║     ╚████╔╝ ███████╗
  ╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝      ╚═══╝  ╚══════╝
[/yellow]
[bold]  FORGE SWARM v2 — Intelligent Hive Mind[/bold]
[dim]  5 different chemistry profiles. Not 5 identical copies.[/dim]
[dim]  Wisdom-guided. Metacognitive. Principle-sharing.[/dim]
"""

def main():
    # Worker mode — running as subprocess
    if os.environ.get("FORGE_WORKER_MODE") == "1":
        run_as_worker()
        return

    swarm = ForgeSwarmV2()

    if len(sys.argv) > 1:
        cmd  = sys.argv[1].lower()
        args = sys.argv[2:]
        swarm.banner()
        if cmd == "swarm":      swarm.cmd_swarm(args)
        elif cmd == "hive":     swarm.cmd_hive(args)
        elif cmd == "workers":  swarm.cmd_workers(args)
        elif cmd == "broadcast":swarm.cmd_broadcast(args)
        elif cmd == "kill":     swarm.cmd_kill(args)
        elif cmd == "clean":    swarm.cmd_clean(args)
    else:
        swarm.run()

if __name__ == "__main__":
    main()
