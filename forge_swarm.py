#!/usr/bin/env python3
"""
███████╗ ██████╗ ██████╗  ██████╗ ███████╗    ███████╗██╗    ██╗ █████╗ ██████╗ ███╗   ███╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝    ██╔════╝██║    ██║██╔══██╗██╔══██╗████╗ ████║
█████╗  ██║   ██║██████╔╝██║  ███╗█████╗      ███████╗██║ █╗ ██║███████║██████╔╝██╔████╔██║
██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝      ╚════██║██║███╗██║██╔══██║██╔══██╗██║╚██╔╝██║
██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗    ███████║╚███╔███╔╝██║  ██║██║  ██║██║ ╚═╝ ██║
╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝    ╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝

FORGE SWARM — Self-Replicating Multi-Agent Hive Mind

How it works:
  1. COORDINATOR spawns N WORKER copies of itself
  2. Workers run in parallel, each attacking a sub-task
  3. All instances share a HIVE MIND (file-based message bus)
  4. New modules built by ANY worker propagate to ALL others instantly
  5. Workers can spawn their OWN sub-workers for deep parallelism
  6. Coordinator aggregates all findings into a unified report

Modes:
  swarm <target>        — Auto-split target into tasks, spawn workers
  replicate <n>         — Clone FORGE N times into separate dirs
  hive                  — View live hive mind state
  workers               — Monitor all running workers
  broadcast <msg>       — Send command to all workers

Requirements: pip install anthropic rich
Usage: python forge_swarm.py
"""

import sys, os, json, re, time, shutil, socket, threading, subprocess
import hashlib, secrets, queue, signal
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Rich ──────────────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.layout import Layout
    from rich.live import Live
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich.prompt import Prompt
    from rich import box as rbox
    from rich.text import Text
    RICH = True
    console = Console()
    def rprint(x, **kw): console.print(x, **kw)
except ImportError:
    RICH = False
    def rprint(x, **kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

# ── Anthropic ─────────────────────────────────────────────────────────────────
try:
    import anthropic
    AI_CLIENT  = anthropic.Anthropic()
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    AI_CLIENT  = None

MODEL = "claude-sonnet-4-6"

# ══════════════════════════════════════════════════════════════════════════════
# 🧬 SWARM CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

SWARM_ROOT   = Path("forge_swarm")
HIVE_DIR     = SWARM_ROOT / "hive"           # shared brain
WORKERS_DIR  = SWARM_ROOT / "workers"        # worker instances
MODULES_POOL = SWARM_ROOT / "modules_pool"   # shared module library
REPORTS_DIR  = SWARM_ROOT / "reports"        # aggregated results

HIVE_BUS     = HIVE_DIR / "bus.json"         # message bus
HIVE_MEMORY  = HIVE_DIR / "memory.json"      # shared findings
HIVE_MODULES = HIVE_DIR / "modules.json"     # module registry across swarm
HIVE_STATUS  = HIVE_DIR / "status.json"      # worker status map

for d in [SWARM_ROOT, HIVE_DIR, WORKERS_DIR, MODULES_POOL, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 HIVE MIND — Shared Memory & Message Bus
# ══════════════════════════════════════════════════════════════════════════════

_hive_lock = threading.Lock()

def hive_read(path):
    try:
        with _hive_lock:
            return json.loads(path.read_text()) if path.exists() else {}
    except: return {}

def hive_write(path, data):
    with _hive_lock:
        path.write_text(json.dumps(data, indent=2, default=str))

def hive_append(path, entry):
    """Thread-safe append to a hive list file."""
    with _hive_lock:
        existing = json.loads(path.read_text()) if path.exists() else []
        if not isinstance(existing, list): existing = []
        existing.append(entry)
        existing = existing[-500:]  # cap
        path.write_text(json.dumps(existing, indent=2, default=str))

# Message types
MSG_TASK_DONE    = "task_done"
MSG_MODULE_BUILT = "module_built"
MSG_FINDING      = "finding"
MSG_SPAWN        = "spawn"
MSG_KILL         = "kill"
MSG_STATUS       = "status"
MSG_BROADCAST    = "broadcast"

def hive_post(worker_id, msg_type, payload):
    """Post a message to the hive bus."""
    bus  = hive_read(HIVE_BUS)
    msgs = bus.get("messages", [])
    msgs.append({
        "id":        secrets.token_hex(4),
        "from":      worker_id,
        "type":      msg_type,
        "payload":   payload,
        "timestamp": datetime.now().isoformat(),
        "read_by":   [],
    })
    bus["messages"] = msgs[-200:]
    hive_write(HIVE_BUS, bus)

def hive_read_messages(worker_id, msg_types=None):
    """Read unread messages for this worker."""
    bus  = hive_read(HIVE_BUS)
    msgs = bus.get("messages",[])
    unread = []
    for m in msgs:
        if worker_id not in m.get("read_by",[]):
            if m.get("from") != worker_id:  # don't read own messages
                if not msg_types or m.get("type") in msg_types:
                    unread.append(m)
                    m["read_by"].append(worker_id)
    hive_write(HIVE_BUS, bus)
    return unread

def hive_update_status(worker_id, status, task="", progress=0):
    """Update this worker's status in the hive."""
    statuses = hive_read(HIVE_STATUS)
    statuses[worker_id] = {
        "status":   status,   # idle|running|building|done|dead
        "task":     task,
        "progress": progress,
        "updated":  datetime.now().isoformat(),
    }
    hive_write(HIVE_STATUS, statuses)

def hive_share_finding(worker_id, finding_type, data, severity="info"):
    """Share a finding with the entire hive."""
    memory = hive_read(HIVE_MEMORY)
    findings = memory.get("findings",[])
    findings.append({
        "from":     worker_id,
        "type":     finding_type,
        "data":     data,
        "severity": severity,
        "ts":       datetime.now().isoformat(),
    })
    memory["findings"] = findings[-1000:]
    hive_write(HIVE_MEMORY, memory)
    hive_post(worker_id, MSG_FINDING, {"type":finding_type,"severity":severity,"preview":str(data)[:100]})

def hive_share_module(worker_id, module_name, module_code, description):
    """Share a newly built module with ALL workers."""
    # Save to shared pool
    fp = MODULES_POOL / f"{module_name}.py"
    fp.write_text(module_code)

    # Update hive module registry
    mods = hive_read(HIVE_MODULES)
    mods[module_name] = {
        "built_by":    worker_id,
        "description": description,
        "file":        str(fp),
        "ts":          datetime.now().isoformat(),
    }
    hive_write(HIVE_MODULES, mods)

    # Broadcast to all workers
    hive_post(worker_id, MSG_MODULE_BUILT, {
        "module": module_name,
        "description": description,
        "file": str(fp),
    })

def hive_sync_modules(worker_dir):
    """Sync all shared pool modules into a worker's local module dir."""
    mods_dir = worker_dir / "modules"
    mods_dir.mkdir(exist_ok=True)
    pool_mods = list(MODULES_POOL.glob("*.py"))
    synced = 0
    for src in pool_mods:
        dst = mods_dir / src.name
        if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
            shutil.copy(src, dst)
            synced += 1
    return synced

# ══════════════════════════════════════════════════════════════════════════════
# 🧬 SELF-REPLICATION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

THIS_FILE = Path(globals().get("__file__", __import__("sys").argv[0])).resolve()

def replicate(worker_id, worker_dir=None):
    """Create a complete copy of FORGE in a new directory."""
    if worker_dir is None:
        worker_dir = WORKERS_DIR / worker_id
    worker_dir.mkdir(parents=True, exist_ok=True)

    # Copy this very file into the worker dir
    worker_forge = worker_dir / "forge_worker.py"
    shutil.copy(THIS_FILE, worker_forge)

    # Create worker config
    config = {
        "worker_id":    worker_id,
        "role":         "worker",
        "hive_root":    str(SWARM_ROOT),
        "worker_dir":   str(worker_dir),
        "created":      datetime.now().isoformat(),
        "parent":       os.getpid(),
    }
    (worker_dir / "config.json").write_text(json.dumps(config, indent=2))

    # Sync shared modules
    hive_sync_modules(worker_dir)

    return worker_forge, config

def spawn_worker(worker_id, task, env_vars=None):
    """Spawn a worker process — a real subprocess running its own FORGE copy."""
    worker_dir   = WORKERS_DIR / worker_id
    worker_forge, config = replicate(worker_id, worker_dir)

    # Write task file for the worker to pick up
    task_file = worker_dir / "task.json"
    task_file.write_text(json.dumps(task, indent=2))

    # Set up environment
    env = os.environ.copy()
    env["FORGE_WORKER_ID"]  = worker_id
    env["FORGE_WORKER_MODE"]= "1"
    env["FORGE_HIVE_ROOT"]  = str(SWARM_ROOT)
    env["FORGE_TASK_FILE"]  = str(task_file)
    if env_vars:
        env.update(env_vars)

    # Launch the worker subprocess
    log_file = worker_dir / "worker.log"
    with open(log_file, "w") as log:
        proc = subprocess.Popen(
            [sys.executable, str(worker_forge)],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            cwd=str(worker_dir),
        )

    hive_update_status(worker_id, "spawned", task.get("description",""), 0)
    hive_post("coordinator", MSG_SPAWN, {"worker_id":worker_id,"pid":proc.pid,"task":task.get("description","")})

    return proc, worker_dir

# ══════════════════════════════════════════════════════════════════════════════
# 🤖 AI SWARM PLANNER
# ══════════════════════════════════════════════════════════════════════════════

SWARM_PLANNER = """You are FORGE SWARM's task decomposition engine.

Given a target and goal, break it into parallel tasks that separate worker agents can execute simultaneously.

Each task must be:
- Independent (can run without waiting for others)
- Focused (one specific thing)
- Valuable (meaningful security finding)

Reply ONLY with JSON:
{
  "target": "the target",
  "strategy": "overall attack strategy",
  "tasks": [
    {
      "id": "worker_01",
      "name": "Port Discovery",
      "description": "Scan all TCP ports 1-10000",
      "type": "scan|recon|brute|build|analyze",
      "module": "scanner/portscan or null if needs building",
      "options": {"PORTS": "1-10000", "THREADS": "200"},
      "build_if_missing": "description of module to build if 'module' is null",
      "priority": 1,
      "can_parallel": true,
      "spawns_sub_workers": false
    }
  ],
  "aggregation_strategy": "how to combine all results"
}
"""

WORKER_AI = """You are a FORGE SWARM worker agent.

You have been given a specific task to execute autonomously.
You can:
1. Use existing modules
2. Build new modules if needed
3. Spawn sub-workers for parallel subtasks
4. Share findings with the hive

After completing your task, share ALL findings with the hive mind.
Be thorough. Think like a penetration tester.

Task: {task}
Available modules: {modules}

Reply with an execution plan as JSON:
{
  "steps": [
    {
      "action": "run|build|spawn_sub|share_finding",
      "module": "module/name or null",
      "build_description": "if building",
      "options": {},
      "finding_type": "if sharing",
      "spawn_task": "if spawning sub-worker"
    }
  ],
  "expected_findings": ["what you expect to discover"]
}
"""

AGGREGATOR_AI = """You are FORGE SWARM's intelligence aggregator.

Multiple parallel worker agents have completed their tasks.
Synthesize all findings into a unified threat intelligence report.

Include:
- Executive summary
- Critical findings (ranked by severity)
- Attack vectors discovered
- Modules built during the swarm
- Recommendations

Be specific. Reference actual findings from the data."""

def ai_call(prompt, system, max_tokens=3000):
    if not AI_AVAILABLE: return None
    try:
        r = AI_CLIENT.messages.create(
            model=MODEL, max_tokens=max_tokens, system=system,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text
    except Exception as e:
        rprint(f"[red]AI error: {e}[/red]")
        return None

def plan_swarm(target, goal):
    """AI plans the full swarm task decomposition."""
    result = ai_call(
        f"Target: {target}\nGoal: {goal}",
        SWARM_PLANNER, max_tokens=3000
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

def worker_plan_task(task, available_modules):
    """AI plans how a worker should execute its specific task."""
    mod_list = "\n".join(f"- {k}" for k in available_modules)
    result = ai_call(
        WORKER_AI.replace("{task}", json.dumps(task, default=str))
                 .replace("{modules}", mod_list),
        "You are a security worker agent. Reply only with JSON.", max_tokens=2000
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

def build_module_for_task(description, category="recon"):
    """Build a new module for a specific task."""
    BUILD_PROMPT = """Build a Python security module for FORGE META framework.

Module format:
```python
# MODULE_NAME: short_name
# CATEGORY: scanner|recon|analyzer|util
# DESCRIPTION: what it does
# OPTIONS: OPTION=default:description, ...

def run(options, session, workspace):
    target = options.get("TARGET","")
    # ... your code ...
    return {"status":"success","output":"result","data":{...}}
```

Use only stdlib. Robust error handling. Return JSON-serializable data."""

    result = ai_call(description, BUILD_PROMPT, max_tokens=3000)
    if not result: return None
    m = re.search(r"```python\s*(.*?)```", result, re.DOTALL)
    return m.group(1).strip() if m else None

def aggregate_findings(target, all_findings, modules_built, worker_count):
    """AI aggregates all worker findings into a unified report."""
    summary = f"Target: {target}\nWorkers: {worker_count}\nModules Built: {len(modules_built)}\n\n"
    summary += "FINDINGS:\n"
    for f in all_findings[-50:]:
        summary += f"  [{f.get('severity','info').upper()}] {f.get('type','')}: {str(f.get('data',''))[:150]}\n"
    if modules_built:
        summary += f"\nMODULES BUILT BY SWARM:\n"
        for m in modules_built:
            summary += f"  - {m.get('module','')}: {m.get('description','')}\n"

    return ai_call(summary[:5000], AGGREGATOR_AI, max_tokens=3000)

# ══════════════════════════════════════════════════════════════════════════════
# 👷 WORKER MODE — Runs when FORGE is spawned as a subprocess
# ══════════════════════════════════════════════════════════════════════════════

def load_worker_modules():
    """Load modules from both local dir and shared pool."""
    modules = {}
    search_dirs = [
        Path.cwd() / "modules",
        MODULES_POOL,
    ]
    for d in search_dirs:
        if not d.exists(): continue
        for fp in d.glob("*.py"):
            try:
                with open(fp) as f: src = f.read()
                nm = re.search(r"#\s*MODULE_NAME:\s*(.+)", src)
                ct = re.search(r"#\s*CATEGORY:\s*(.+)",    src)
                ds = re.search(r"#\s*DESCRIPTION:\s*(.+)", src)
                if nm:
                    modules[nm.group(1).strip()] = {
                        "file": str(fp),
                        "category": ct.group(1).strip() if ct else "util",
                        "description": ds.group(1).strip() if ds else fp.stem,
                    }
            except: pass
    return modules

def worker_run_module(module_info, options, session, workspace):
    """Dynamically load and run a module file."""
    import types
    try:
        with open(module_info["file"]) as f:
            src = f.read()
        mod = types.ModuleType("worker_mod")
        exec(compile(src, module_info["file"], "exec"), mod.__dict__)
        if hasattr(mod, "run"):
            return mod.run(options, session, workspace)
    except Exception as e:
        return {"status":"error","output":str(e)}
    return {"status":"error","output":"No run() in module"}

def run_as_worker():
    """Main function when running as a spawned worker."""
    worker_id = os.environ.get("FORGE_WORKER_ID","worker_unknown")
    task_file = Path(os.environ.get("FORGE_TASK_FILE","task.json"))

    # Load task
    task = {}
    if task_file.exists():
        task = json.loads(task_file.read_text())

    session   = {"worker_id": worker_id}
    workspace = {}
    results   = []

    def log(msg):
        with open("worker.log", "a") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")

    log(f"Worker {worker_id} started. Task: {task.get('name','?')}")
    hive_update_status(worker_id, "running", task.get("name",""), 0)

    # Sync modules from hive
    synced = hive_sync_modules(Path.cwd())
    log(f"Synced {synced} modules from hive pool")

    modules = load_worker_modules()
    log(f"Loaded {len(modules)} modules")

    task_type   = task.get("type","recon")
    target      = task.get("target","")
    module_name = task.get("module")
    options     = task.get("options",{})
    options["TARGET"] = target

    # Step 1: Try to use specified module
    if module_name and module_name in modules:
        log(f"Running module: {module_name}")
        hive_update_status(worker_id, "running", f"running {module_name}", 30)
        result = worker_run_module(modules[module_name], options, session, workspace)
        results.append(result)

        # Share findings
        if result.get("status") == "success":
            data = result.get("data", result.get("output",""))
            severity = "high" if result.get("open_ports") else "info"
            hive_share_finding(worker_id, f"{module_name}_result", data, severity)
            log(f"Shared finding: {result.get('output','')[:80]}")

    # Step 2: If no module or build needed, use AI to plan
    elif AI_AVAILABLE:
        log("No direct module match — asking AI to plan execution")
        hive_update_status(worker_id, "planning", "AI planning task", 10)
        worker_plan = worker_plan_task(task, list(modules.keys()))

        if worker_plan:
            steps = worker_plan.get("steps",[])
            for i, step in enumerate(steps):
                action = step.get("action","")
                progress = int((i/max(len(steps),1))*80)+10
                hive_update_status(worker_id, "running", f"step {i+1}/{len(steps)}", progress)

                if action == "run" and step.get("module"):
                    mod_name = step["module"]
                    if mod_name in modules:
                        opts = {**options, **step.get("options",{})}
                        result = worker_run_module(modules[mod_name], opts, session, workspace)
                        results.append(result)
                        if result.get("status") == "success":
                            hive_share_finding(worker_id, mod_name, result.get("output",""), "info")
                        log(f"Ran {mod_name}: {result.get('output','')[:60]}")

                elif action == "build":
                    desc = step.get("build_description","")
                    log(f"Building module: {desc}")
                    hive_update_status(worker_id, "building", desc[:40], progress)
                    code = build_module_for_task(desc)
                    if code:
                        # Extract name
                        nm = re.search(r"#\s*MODULE_NAME:\s*(.+)", code)
                        name = nm.group(1).strip() if nm else re.sub(r"\s+","_",desc[:20].lower())
                        # Save and share with hive
                        fp = Path.cwd() / "modules" / f"{name}.py"
                        fp.parent.mkdir(exist_ok=True)
                        fp.write_text(code)
                        hive_share_module(worker_id, name, code, desc)
                        log(f"Built and shared module: {name}")
                        # Run it
                        modules[name] = {"file":str(fp),"category":"util","description":desc}
                        result = worker_run_module(modules[name], options, session, workspace)
                        results.append(result)
                        if result.get("status") == "success":
                            hive_share_finding(worker_id, f"custom_{name}", result.get("output",""), "info")

                elif action == "share_finding":
                    hive_share_finding(worker_id, step.get("finding_type","finding"),
                                       step.get("data",""), step.get("severity","info"))

    # Step 3: Fallback — run basic recon
    else:
        log("No AI available. Running basic recon.")
        hive_update_status(worker_id, "running", "basic recon", 30)
        try:
            ip = socket.gethostbyname(target.replace("https://","").replace("http://","").split("/")[0])
            hive_share_finding(worker_id, "dns_resolution", {"target":target,"ip":ip}, "info")
            log(f"DNS: {target} → {ip}")
            results.append({"status":"success","output":f"Resolved {target} to {ip}"})
        except Exception as e:
            log(f"DNS failed: {e}")

    # Sync any new modules from hive before finishing
    hive_sync_modules(Path.cwd())

    # Mark done
    hive_update_status(worker_id, "done", task.get("name",""), 100)
    hive_post(worker_id, MSG_TASK_DONE, {
        "task":    task.get("name",""),
        "results": len(results),
        "output":  results[-1].get("output","") if results else "no output",
    })
    log(f"Worker done. Results: {len(results)}")

# ══════════════════════════════════════════════════════════════════════════════
# 🎯 COORDINATOR — Main swarm orchestrator
# ══════════════════════════════════════════════════════════════════════════════

class ForgeSwarm:
    def __init__(self):
        self.workers = {}      # id → process
        self.worker_dirs = {}  # id → Path
        self.tasks    = []
        self.findings = []
        self.modules_built = []
        self._monitor_thread = None
        self._running = False

    def banner(self):
        rprint(f"""
[cyan][bold]
  ███████╗ ██████╗ ██████╗  ██████╗ ███████╗    ███████╗██╗    ██╗ █████╗ ██████╗ ███╗   ███╗
  ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝    ██╔════╝██║    ██║██╔══██╗██╔══██╗████╗ ████║
  █████╗  ██║   ██║██████╔╝██║  ███╗█████╗      ███████╗██║ █╗ ██║███████║██████╔╝██╔████╔██║
  ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝      ╚════██║██║███╗██║██╔══██║██╔══██╗██║╚██╔╝██║
  ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗    ███████║╚███╔███╔╝██║  ██║██║  ██║██║ ╚═╝ ██║
  ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝    ╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝
[/bold][/cyan]
[magenta bold]  SELF-REPLICATING HIVE MIND — Each instance copies itself and runs in parallel[/magenta bold]
[dim]  AI {'✅' if AI_AVAILABLE else '❌'}  |  Workers: {len(self.workers)}  |  Hive modules: {len(hive_read(HIVE_MODULES))}[/dim]
""")

    # ── Monitor Thread ────────────────────────────────────────────────────────

    def start_monitor(self):
        """Background thread that watches hive bus and processes messages."""
        self._running = True
        def _monitor():
            while self._running:
                try:
                    self._process_hive_messages()
                    self._check_worker_health()
                except: pass
                time.sleep(1.5)
        self._monitor_thread = threading.Thread(target=_monitor, daemon=True)
        self._monitor_thread.start()

    def stop_monitor(self):
        self._running = False

    def _process_hive_messages(self):
        """Read hive bus and react to messages."""
        msgs = hive_read_messages("coordinator")
        for msg in msgs:
            mtype = msg.get("type","")
            payload = msg.get("payload",{})
            frm = msg.get("from","?")

            if mtype == MSG_MODULE_BUILT:
                mod_name = payload.get("module","")
                desc     = payload.get("description","")
                self.modules_built.append({"module":mod_name,"description":desc,"built_by":frm})
                rprint(f"\n  [magenta]🧬  [{frm}] built new module: [bold]{mod_name}[/bold][/magenta]")
                # Sync to all other workers immediately
                self._broadcast_module_sync()

            elif mtype == MSG_FINDING:
                self.findings.append({**payload,"from":frm,"ts":msg.get("timestamp","")})
                sev = payload.get("severity","info")
                color = {"critical":"red bold","high":"red","medium":"yellow","info":"dim"}.get(sev,"dim")
                rprint(f"  [{color}]🔍  [{frm}] {sev.upper()}: {payload.get('preview','')[:70]}[/{color}]")

            elif mtype == MSG_TASK_DONE:
                rprint(f"  [green]✅  [{frm}] task done: {payload.get('task','')} ({payload.get('results',0)} results)[/green]")

            elif mtype == MSG_STATUS:
                pass  # status updates handled by _check_worker_health

    def _check_worker_health(self):
        """Check if workers are still alive."""
        for wid, proc in list(self.workers.items()):
            if proc.poll() is not None:  # process finished
                statuses = hive_read(HIVE_STATUS)
                if statuses.get(wid,{}).get("status") not in ("done","dead"):
                    hive_update_status(wid, "dead", "", 0)

    def _broadcast_module_sync(self):
        """Tell all workers to sync new modules from pool."""
        for wid, wdir in self.worker_dirs.items():
            synced = hive_sync_modules(wdir)
            if synced > 0:
                rprint(f"  [dim]  Synced {synced} module(s) → {wid}[/dim]")

    # ── Core Commands ─────────────────────────────────────────────────────────

    def cmd_swarm(self, args):
        """Plan and launch full parallel swarm against a target."""
        rprint(f"\n[cyan bold]🐝  FORGE SWARM — Launching parallel attack[/cyan bold]\n")

        target = args[0] if args else input("  Target: ").strip()
        goal   = " ".join(args[1:]) if len(args)>1 else input(
            "  Goal [comprehensive security assessment]: ").strip() or "comprehensive security assessment"
        if not target: return

        if not AI_AVAILABLE:
            rprint("[red]AI required. pip install anthropic[/red]"); return

        rprint(f"  [bold]Target:[/bold] {target}")
        rprint(f"  [bold]Goal:[/bold]   {goal}")
        rprint(f"\n  [magenta]🧠 AI planning task decomposition...[/magenta]")

        plan = plan_swarm(target, goal)
        if not plan:
            rprint("[red]  Planning failed.[/red]"); return

        tasks    = plan.get("tasks",[])
        strategy = plan.get("strategy","")

        rprint(f"\n  [bold]Strategy:[/bold] {strategy[:80]}")

        if RICH:
            t = Table(title="🐝 Swarm Task Plan", border_style="magenta", show_lines=True, box=rbox.ROUNDED)
            t.add_column("Worker",   style="bold yellow", width=12)
            t.add_column("Task",     style="white",       width=22)
            t.add_column("Type",     style="cyan",        width=10)
            t.add_column("Module",   style="green",       width=22)
            t.add_column("Priority", style="dim",         width=9)
            for tk in tasks:
                mod = tk.get("module") or f"[magenta]build: {tk.get('build_if_missing','?')[:18]}[/magenta]"
                t.add_row(tk.get("id",""), tk.get("name",""), tk.get("type",""),
                          str(mod), str(tk.get("priority",1)))
            console.print(t)

        if not self._confirm(f"\n  🚀 Launch {len(tasks)} parallel workers?"):
            return

        # Start hive monitor
        self.start_monitor()
        rprint(f"\n  [dim]🧠 Hive mind monitor started[/dim]")

        # Initialize hive memory for this run
        hive_write(HIVE_MEMORY, {"target":target,"goal":goal,"findings":[],"started":datetime.now().isoformat()})
        hive_write(HIVE_BUS,    {"messages":[]})

        # Spawn workers
        rprint(f"\n  [cyan bold]🧬 Replicating FORGE × {len(tasks)}...[/cyan bold]\n")
        procs = []

        for tk in tasks:
            wid  = tk.get("id", f"worker_{len(self.workers):02d}")
            task = {**tk, "target": target}
            rprint(f"  [yellow]Spawning[/yellow]  {wid:<14} → {tk.get('name','')}")

            try:
                proc, wdir = spawn_worker(wid, task)
                self.workers[wid]     = proc
                self.worker_dirs[wid] = wdir
                procs.append((wid, proc))
                time.sleep(0.3)  # stagger launches
            except Exception as e:
                rprint(f"  [red]  ✗ Failed to spawn {wid}: {e}[/red]")

        rprint(f"\n  [green bold]🐝 Swarm active: {len(procs)} workers running in parallel[/green bold]")
        rprint(f"  [dim]Watching hive mind... (Ctrl+C to stop and aggregate)[/dim]\n")

        # Live monitor loop
        try:
            self._live_monitor(procs, target, goal)
        except KeyboardInterrupt:
            rprint(f"\n\n  [yellow]Interrupted — aggregating findings...[/yellow]")

        self._aggregate_and_report(target, goal)

    def _live_monitor(self, procs, target, goal):
        """Live status display while workers run."""
        start = time.time()
        while True:
            alive = [(wid, p) for wid, p in procs if p.poll() is None]
            done  = [(wid, p) for wid, p in procs if p.poll() is not None]

            statuses = hive_read(HIVE_STATUS)
            memory   = hive_read(HIVE_MEMORY)
            findings = memory.get("findings",[])
            mods     = hive_read(HIVE_MODULES)

            elapsed  = int(time.time()-start)
            mins, secs = divmod(elapsed, 60)

            if RICH:
                lines = [
                    f"[bold]Workers alive:[/bold]  [green]{len(alive)}[/green]  [dim]done: {len(done)}[/dim]",
                    f"[bold]Findings:[/bold]       [yellow]{len(findings)}[/yellow]",
                    f"[bold]Modules built:[/bold]  [magenta]{len(mods)}[/magenta]",
                    f"[bold]Time:[/bold]           {mins:02d}:{secs:02d}",
                    "",
                ]
                for wid, _ in procs:
                    st = statuses.get(wid,{})
                    status   = st.get("status","?")
                    task_str = st.get("task","")[:30]
                    prog     = st.get("progress",0)
                    color    = {"running":"cyan","building":"magenta","done":"green",
                                "dead":"red","spawned":"yellow","planning":"blue"}.get(status,"dim")
                    bar = "█"*int(prog/10)+"░"*(10-int(prog/10))
                    lines.append(f"  [{color}]{wid:<14}[/{color}] {status:<10} [{bar}] {task_str}")

                rprint("\r" + "\n".join(lines[:20]), end="")

            # Check if all done
            if not alive:
                rprint(f"\n\n  [green bold]All workers finished![/green bold]")
                break

            time.sleep(3)

    def _aggregate_and_report(self, target, goal):
        """Aggregate all worker findings and generate final report."""
        rprint(f"\n\n{'═'*62}")
        rprint(f"[cyan bold]  🧠 AGGREGATING HIVE MIND[/cyan bold]")
        rprint(f"{'═'*62}\n")

        memory  = hive_read(HIVE_MEMORY)
        findings= memory.get("findings",[])
        mods    = hive_read(HIVE_MODULES)

        # Collect worker logs
        rprint(f"  [bold]Workers:[/bold]    {len(self.workers)}")
        rprint(f"  [bold]Findings:[/bold]   {len(findings)}")
        rprint(f"  [bold]New modules:[/bold] {len(mods)}")

        if findings:
            rprint(f"\n  [bold]Top Findings:[/bold]")
            sev_order = {"critical":0,"high":1,"medium":2,"info":3}
            for f in sorted(findings, key=lambda x: sev_order.get(x.get("severity","info"),3))[:10]:
                sev   = f.get("severity","info")
                color = {"critical":"red bold","high":"red","medium":"yellow","info":"dim"}.get(sev,"dim")
                rprint(f"    [{color}]{sev.upper():<8}[/{color}] [{f.get('from','?')}]  {str(f.get('data',''))[:70]}")

        if mods:
            rprint(f"\n  [bold]Modules built by swarm:[/bold]")
            for name, info in mods.items():
                rprint(f"    [magenta]🔨[/magenta]  {name:<25} by {info.get('built_by','?')}  —  {info.get('description','')[:45]}")

        # AI aggregation report
        if AI_AVAILABLE and findings:
            rprint(f"\n  [magenta]📊 Generating unified intelligence report...[/magenta]")
            report = aggregate_findings(target, findings, list(mods.values()), len(self.workers))
            if report:
                rprint(f"\n[bold]{'═'*62}[/bold]")
                rprint(f"[bold cyan]  🛡️  SWARM INTELLIGENCE REPORT[/bold cyan]")
                rprint(f"[bold]{'═'*62}[/bold]\n")
                rprint(report)
                ts = datetime.now().strftime("%Y%m%d_%H%M")
                fp = REPORTS_DIR / f"swarm_{re.sub(r'[^\\w]','_',target)}_{ts}.txt"
                fp.write_text(f"FORGE SWARM Report\nTarget: {target}\nGoal: {goal}\nWorkers: {len(self.workers)}\n\n{report}")
                rprint(f"\n[green]  📄 Report: {fp}[/green]")

        self.stop_monitor()

    def cmd_replicate(self, args):
        """Manually replicate FORGE N times without assigning tasks."""
        n = int(args[0]) if args else int(input("  How many copies? ").strip() or "3")
        rprint(f"\n[cyan]🧬 Replicating FORGE × {n}...[/cyan]\n")

        for i in range(n):
            wid = f"clone_{i+1:02d}"
            worker_forge, config = replicate(wid)
            rprint(f"  [green]✅[/green]  {wid}  →  {worker_forge}")
            rprint(f"      [dim]Config: {config['worker_dir']}[/dim]")

        rprint(f"\n  [bold]{n} copies of FORGE created in:[/bold] {WORKERS_DIR}")
        rprint(f"  [dim]Each copy has its own directory, config, and module dir.[/dim]")
        rprint(f"  [dim]They share: {HIVE_DIR} (hive mind)[/dim]")
        rprint(f"  [dim]Run 'swarm <target>' to activate them with tasks.[/dim]")

    def cmd_hive(self, args):
        """Show live hive mind state."""
        rprint(f"\n[cyan bold]🧠  HIVE MIND STATE[/cyan bold]\n")

        memory   = hive_read(HIVE_MEMORY)
        statuses = hive_read(HIVE_STATUS)
        mods     = hive_read(HIVE_MODULES)
        bus      = hive_read(HIVE_BUS)
        msgs     = bus.get("messages",[])

        # Workers
        if RICH:
            t = Table(title="Workers", border_style="cyan", show_lines=True)
            t.add_column("ID",       style="bold yellow", width=16)
            t.add_column("Status",   style="bold",        width=12)
            t.add_column("Task",     style="white",       width=30)
            t.add_column("Progress", style="cyan",        width=14)
            t.add_column("Updated",  style="dim",         width=12)
            for wid, st in statuses.items():
                status = st.get("status","?")
                color  = {"running":"cyan","building":"magenta","done":"green","dead":"red"}.get(status,"dim")
                prog   = st.get("progress",0)
                bar    = "█"*int(prog/10)+"░"*(10-int(prog/10))
                upd    = st.get("updated","")[-8:-3] if st.get("updated") else "?"
                t.add_row(wid, f"[{color}]{status}[/{color}]", st.get("task","")[:29], f"[{bar}] {prog}%", upd)
            console.print(t)

        # Findings summary
        findings = memory.get("findings",[])
        rprint(f"\n  [bold]Findings:[/bold]  {len(findings)}")
        sev_counts = defaultdict(int)
        for f in findings: sev_counts[f.get("severity","info")] += 1
        for sev, count in sorted(sev_counts.items()):
            color = {"critical":"red bold","high":"red","medium":"yellow","info":"dim"}.get(sev,"dim")
            rprint(f"    [{color}]{sev:<10}[/{color}] {count}")

        # Modules
        rprint(f"\n  [bold]Hive Modules Built:[/bold]  {len(mods)}")
        for name, info in list(mods.items())[:8]:
            rprint(f"    [magenta]🔨[/magenta]  {name:<22} by {info.get('built_by','?')}")

        # Recent messages
        rprint(f"\n  [bold]Recent Bus Messages:[/bold]  {len(msgs)} total")
        for m in msgs[-6:]:
            ts  = m.get("timestamp","")[-8:-3]
            typ = m.get("type","?")
            frm = m.get("from","?")
            color = {"module_built":"magenta","finding":"yellow","task_done":"green","spawn":"cyan"}.get(typ,"dim")
            rprint(f"    [dim]{ts}[/dim]  [{color}]{typ:<15}[/{color}]  from {frm}")

    def cmd_workers(self, args):
        """Show running worker processes."""
        if not self.workers:
            rprint("[dim]No active workers. Run 'swarm <target>' to start.[/dim]"); return
        rprint(f"\n[bold]Active Workers ({len(self.workers)}):[/bold]")
        statuses = hive_read(HIVE_STATUS)
        for wid, proc in self.workers.items():
            alive  = proc.poll() is None
            st     = statuses.get(wid,{})
            color  = "green" if alive else "red"
            log_fp = self.worker_dirs.get(wid, Path(".")) / "worker.log"
            last   = ""
            if log_fp.exists():
                lines = log_fp.read_text().strip().split("\n")
                last  = lines[-1][:60] if lines else ""
            rprint(f"  [{color}]{'●' if alive else '✗'}[/{color}]  {wid:<16} pid={proc.pid:<8} {st.get('status','?'):<10} {last}")

    def cmd_broadcast(self, args):
        """Broadcast a message/command to all workers."""
        msg = " ".join(args) if args else input("  Message: ").strip()
        if not msg: return
        hive_post("coordinator", MSG_BROADCAST, {"message":msg})
        rprint(f"  [cyan]📡 Broadcast sent to {len(self.workers)} workers: {msg}[/cyan]")

    def cmd_kill(self, args):
        """Kill specific or all workers."""
        target = args[0] if args else "all"
        killed = 0
        for wid, proc in list(self.workers.items()):
            if target == "all" or wid == target:
                proc.terminate()
                hive_update_status(wid,"dead","killed",0)
                killed += 1
        rprint(f"  [red]Killed {killed} worker(s)[/red]")

    def cmd_clean(self, args):
        """Clean all worker dirs and hive state."""
        if not self._confirm("⚠️  Clean all worker directories and hive state?"):
            return
        shutil.rmtree(WORKERS_DIR, ignore_errors=True)
        shutil.rmtree(HIVE_DIR,    ignore_errors=True)
        shutil.rmtree(MODULES_POOL,ignore_errors=True)
        for d in [SWARM_ROOT, HIVE_DIR, WORKERS_DIR, MODULES_POOL, REPORTS_DIR]:
            d.mkdir(parents=True, exist_ok=True)
        self.workers = {}; self.worker_dirs = {}
        rprint("[green]✅ Cleaned.[/green]")

    def cmd_modules(self, args):
        """Show all modules in the shared hive pool."""
        pool = list(MODULES_POOL.glob("*.py"))
        hive_mods = hive_read(HIVE_MODULES)
        rprint(f"\n[magenta bold]🔨 Shared Module Pool ({len(pool)} modules)[/magenta bold]")
        if not pool:
            rprint("[dim]  No shared modules yet. Workers build them during swarm runs.[/dim]"); return
        for fp in pool:
            info = hive_mods.get(fp.stem,{})
            rprint(f"  [magenta]●[/magenta]  {fp.stem:<25} [dim]built by: {info.get('built_by','?')}[/dim]  {info.get('description','')[:45]}")

    def cmd_logs(self, args):
        """Show logs from a specific worker."""
        if not self.worker_dirs:
            rprint("[dim]No workers yet.[/dim]"); return
        wid = args[0] if args else list(self.worker_dirs.keys())[0]
        if wid not in self.worker_dirs:
            rprint(f"[red]Worker not found: {wid}[/red]"); return
        log_fp = self.worker_dirs[wid] / "worker.log"
        if not log_fp.exists():
            rprint("[dim]No log file.[/dim]"); return
        lines = log_fp.read_text().strip().split("\n")
        n = int(args[1]) if len(args) > 1 else 20
        rprint(f"\n[bold]Log: {wid} (last {n} lines)[/bold]")
        for line in lines[-n:]:
            rprint(f"  [dim]{line}[/dim]")

    def _confirm(self, msg):
        try:
            r = (console.input(f"[dim]{msg} (y/n)[/dim] ") if RICH else input(f"{msg} (y/n) ")).lower()
            return r == "y"
        except: return False

    def cmd_help(self, args):
        help_text = """[bold cyan]FORGE SWARM Commands:[/bold cyan]

[bold]Swarm Control:[/bold]
  [yellow]swarm[/yellow] <target> [goal]     Launch full parallel swarm
  [yellow]replicate[/yellow] <n>             Copy FORGE N times (no tasks)
  [yellow]workers[/yellow]                   Show running worker processes
  [yellow]kill[/yellow] [worker_id|all]      Kill worker(s)
  [yellow]broadcast[/yellow] <message>       Send command to all workers

[bold]Hive Mind:[/bold]
  [yellow]hive[/yellow]                      Live hive mind state
  [yellow]modules[/yellow]                   Show shared module pool
  [yellow]logs[/yellow] <worker_id> [n]      Show worker log

[bold]Utility:[/bold]
  [yellow]clean[/yellow]                     Wipe all workers and hive state
  [yellow]help[/yellow]                      This help
  [yellow]exit[/yellow]                      Exit FORGE SWARM

[bold]How it works:[/bold]
  [dim]1. 'swarm' decomposes target into parallel tasks
  2. FORGE copies itself into N worker directories
  3. Each worker runs as a real subprocess
  4. Workers share findings via the hive mind (forge_swarm/hive/)
  5. New modules built by any worker sync to ALL others
  6. Coordinator aggregates everything into a unified report[/dim]"""
        if RICH: console.print(Panel(help_text, border_style="cyan"))
        else: print(re.sub(r"\[/?[^\]]*\]","",help_text))

    def run(self):
        self.banner()
        COMMANDS = {
            "swarm":     self.cmd_swarm,
            "replicate": self.cmd_replicate,
            "clone":     self.cmd_replicate,
            "hive":      self.cmd_hive,
            "workers":   self.cmd_workers,
            "kill":      self.cmd_kill,
            "broadcast": self.cmd_broadcast,
            "modules":   self.cmd_modules,
            "logs":      self.cmd_logs,
            "clean":     self.cmd_clean,
            "help":      self.cmd_help,
            "?":         self.cmd_help,
        }
        rprint("[dim]Type 'help' | 'swarm <target>' to launch | 'replicate 3' to clone[/dim]\n")

        while True:
            try:
                raw = (console.input("[bold cyan]forge-swarm >[/bold cyan] ") if RICH
                       else input("forge-swarm > ")).strip()
            except (KeyboardInterrupt, EOFError):
                rprint("\n[cyan]⚒️  FORGE SWARM signing off. Stay ethical. 🔥[/cyan]"); break

            if not raw: continue
            parts = raw.split(); cmd = parts[0].lower(); args = parts[1:]
            if cmd in ("exit","quit","q"):
                rprint("[cyan]⚒️  FORGE SWARM — Stay ethical. 🔥[/cyan]"); break
            elif cmd in COMMANDS:
                try: COMMANDS[cmd](args)
                except Exception as e: rprint(f"[red]Error: {e}[/red]")
            else:
                rprint(f"[yellow]Unknown: '{cmd}'. Type 'help'.[/yellow]")

# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # If spawned as a worker subprocess, run in worker mode
    if os.environ.get("FORGE_WORKER_MODE") == "1":
        run_as_worker()
    else:
        # Run as coordinator
        swarm = ForgeSwarm()
        swarm.run()

if __name__ == "__main__":
    main()
