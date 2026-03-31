"""
FORGE Brain Launcher — forge_launcher.py
=========================================
One command. Starts everything. Shows everything.

Launches all 16 FORGE cognitive architecture modules in the
correct dependency order, waits for health checks, then shows
a live unified dashboard.

Usage:
  python forge_launcher.py              # launch all modules
  python forge_launcher.py --check      # health check only
  python forge_launcher.py --stop       # stop all modules
  python forge_launcher.py --status     # show status dashboard
  python forge_launcher.py --module temporal  # launch one module

Architecture launched (in order):
  Tier 1 — Perception & Emotion (no dependencies)
    forge_temporal.py       :7778
    forge_salience.py       :7784
    forge_visual.py         :7789
    forge_limbic.py         :7785
    forge_neuromodulator.py :7787
    forge_amygdala.py       :7792

  Tier 2 — Social & Memory (depends on Tier 1)
    forge_bridge.py         :7781
    forge_hippocampus.py    :7780

  Tier 3 — Decision & Action (depends on Tier 1+2)
    forge_prefrontal.py     :7779
    forge_sensorimotor.py   :7788
    forge_basal_ganglia.py  :7791

  Tier 4 — Coordination (depends on all)
    forge_thalamus.py       :7790
    forge_dmn.py            :7783
    forge_swarm_v2.py       :7782

  Tier 5 — Orchestration (depends on everything)
    forge_orchestrator_v2.py :7786
"""

import os
import sys
import time
import json
import signal
import subprocess
import threading
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich.columns import Columns
    from rich.rule import Rule
    from rich.align import Align
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.prompt import Confirm
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ─── Module Registry ──────────────────────────────────────────────────────────

MODULES = [
    # Tier 1 — Perception & Emotion
    {
        "id":    "temporal",
        "file":  "forge_temporal.py",
        "port":  7778,
        "emoji": "🧠",
        "name":  "Temporal Cortex",
        "role":  "Bilateral perception",
        "tier":  1,
        "color": "cyan",
        "health_endpoint": "/status",
        "description": "Perceives the world through bilateral sensory streams",
    },
    {
        "id":    "salience",
        "file":  "forge_salience.py",
        "port":  7784,
        "emoji": "🎯",
        "name":  "Salience Network",
        "role":  "Priority gating",
        "tier":  1,
        "color": "bright_red",
        "health_endpoint": "/status",
        "description": "Determines what deserves attention — interrupt or filter",
    },
    {
        "id":    "visual",
        "file":  "forge_visual.py",
        "port":  7789,
        "emoji": "👁",
        "name":  "Visual Network",
        "role":  "Dual visual streams",
        "tier":  1,
        "color": "blue",
        "health_endpoint": "/status",
        "description": "Ventral (what) + Dorsal (where) visual processing",
    },
    {
        "id":    "limbic",
        "file":  "forge_limbic.py",
        "port":  7785,
        "emoji": "💗",
        "name":  "Limbic System",
        "role":  "Emotion + drives",
        "tier":  1,
        "color": "magenta",
        "health_endpoint": "/status",
        "description": "Emotional states, intrinsic drives, reward evaluation",
    },
    {
        "id":    "neuromodulator",
        "file":  "forge_neuromodulator.py",
        "port":  7787,
        "emoji": "🧪",
        "name":  "Neuromodulator",
        "role":  "Chemical layer",
        "tier":  1,
        "color": "yellow",
        "health_endpoint": "/status",
        "description": "Cortisol, dopamine, serotonin, NE, oxytocin dynamics",
    },
    {
        "id":    "amygdala",
        "file":  "forge_amygdala.py",
        "port":  7792,
        "emoji": "😨",
        "name":  "Amygdala",
        "role":  "Fear + hijack",
        "tier":  1,
        "color": "red",
        "health_endpoint": "/status",
        "description": "Fast fear tagging, conditioned memory, emotional hijack",
    },
    # Tier 2 — Social & Memory
    {
        "id":    "bridge",
        "file":  "forge_bridge.py",
        "port":  7781,
        "emoji": "🔗",
        "name":  "Social Bridge",
        "role":  "Perception ↔ Social",
        "tier":  2,
        "color": "blue",
        "health_endpoint": "/stats",
        "description": "Bidirectional temporal↔social pipeline with enrichment",
    },
    {
        "id":    "hippocampus",
        "file":  "forge_hippocampus.py",
        "port":  7780,
        "emoji": "📚",
        "name":  "Hippocampus",
        "role":  "Long-term memory",
        "tier":  2,
        "color": "green",
        "health_endpoint": "/status",
        "description": "Memory consolidation, novelty detection, forgetting curve",
    },
    # Tier 3 — Decision & Action
    {
        "id":    "prefrontal",
        "file":  "forge_prefrontal.py",
        "port":  7779,
        "emoji": "👔",
        "name":  "Prefrontal Cortex",
        "role":  "Executive decisions",
        "tier":  3,
        "color": "yellow",
        "health_endpoint": "/status",
        "description": "Goal management, decision engine, impulse filtering",
    },
    {
        "id":    "sensorimotor",
        "file":  "forge_sensorimotor.py",
        "port":  7788,
        "emoji": "⚡",
        "name":  "Sensorimotor",
        "role":  "Reflex + programs",
        "tier":  3,
        "color": "orange3",
        "health_endpoint": "/status",
        "description": "Three-tier response: reflex (8ms) / fast (50ms) / deliberate",
    },
    {
        "id":    "basal_ganglia",
        "file":  "forge_basal_ganglia.py",
        "port":  7791,
        "emoji": "🔄",
        "name":  "Basal Ganglia",
        "role":  "Habits + selection",
        "tier":  3,
        "color": "cyan",
        "health_endpoint": "/status",
        "description": "Go/NoGo action selection, habit formation, reward gating",
    },
    # Tier 4 — Coordination
    {
        "id":    "thalamus",
        "file":  "forge_thalamus.py",
        "port":  7790,
        "emoji": "🔀",
        "name":  "Thalamus",
        "role":  "Consciousness gating",
        "tier":  4,
        "color": "bright_cyan",
        "health_endpoint": "/status",
        "description": "Central relay, 11 module gates, 6 consciousness states",
    },
    {
        "id":    "dmn",
        "file":  "forge_dmn.py",
        "port":  7783,
        "emoji": "💭",
        "name":  "Default Mode Network",
        "role":  "Idle reflection",
        "tier":  4,
        "color": "dim",
        "health_endpoint": "/status",
        "description": "Mind wandering, future simulation, self-model, narrative",
    },
    {
        "id":    "swarm",
        "file":  "forge_swarm_v2.py",
        "port":  7782,
        "emoji": "🐝",
        "name":  "Cognitive Swarm",
        "role":  "Collective action",
        "tier":  4,
        "color": "yellow",
        "health_endpoint": "/status",
        "description": "8 cognitive agents with trust mesh and consensus voting",
    },
    # Tier 5 — Orchestration
    {
        "id":    "orchestrator",
        "file":  "forge_orchestrator_v2.py",
        "port":  7786,
        "emoji": "🎯",
        "name":  "Orchestrator v2",
        "role":  "Master wiring",
        "tier":  5,
        "color": "bright_white",
        "health_endpoint": "/status",
        "description": "Full pipeline: salience→temporal→bridge→limbic→prefrontal→memory→swarm→dmn",
    },
]

# Port lookup
PORT_MAP = {m["id"]: m["port"] for m in MODULES}
FILE_MAP = {m["id"]: m["file"] for m in MODULES}

console = Console() if HAS_RICH else None

# ─── Process Manager ──────────────────────────────────────────────────────────

class ProcessManager:
    def __init__(self, base_dir: Path):
        self.base_dir  = base_dir
        self.processes: dict[str, subprocess.Popen] = {}
        self.pid_file  = base_dir / ".forge_pids.json"
        self.log_dir   = base_dir / "logs"
        self.log_dir.mkdir(exist_ok=True)

    def launch(self, module: dict) -> tuple[bool, str]:
        mid      = module["id"]
        filepath = self.base_dir / module["file"]

        if not filepath.exists():
            return False, f"File not found: {filepath}"

        log_file = self.log_dir / f"{mid}.log"
        try:
            with open(log_file, "w") as log:
                proc = subprocess.Popen(
                    [sys.executable, str(filepath), "--api"],
                    stdout=log,
                    stderr=log,
                    cwd=str(self.base_dir)
                )
            self.processes[mid] = proc
            self._save_pids()
            return True, f"PID {proc.pid}"
        except Exception as e:
            return False, str(e)

    def stop(self, mid: str) -> bool:
        if mid in self.processes:
            try:
                self.processes[mid].terminate()
                self.processes[mid].wait(timeout=3)
                del self.processes[mid]
                self._save_pids()
                return True
            except Exception:
                try:
                    self.processes[mid].kill()
                except Exception:
                    pass
        return False

    def stop_all(self):
        for mid in list(self.processes.keys()):
            self.stop(mid)
        # Clean up pid file
        if self.pid_file.exists():
            self.pid_file.unlink()

    def is_running(self, mid: str) -> bool:
        if mid not in self.processes:
            return False
        return self.processes[mid].poll() is None

    def _save_pids(self):
        pids = {
            mid: proc.pid
            for mid, proc in self.processes.items()
            if proc.poll() is None
        }
        with open(self.pid_file, "w") as f:
            json.dump({"pids": pids, "started": datetime.now().isoformat()}, f)

    def get_log_tail(self, mid: str, lines: int = 5) -> list[str]:
        log_file = self.log_dir / f"{mid}.log"
        if not log_file.exists():
            return []
        try:
            with open(log_file, "r") as f:
                all_lines = f.readlines()
            return [l.rstrip() for l in all_lines[-lines:]]
        except Exception:
            return []


# ─── Health Checker ───────────────────────────────────────────────────────────

class HealthChecker:
    def __init__(self, timeout: float = 3.0):
        self.timeout = timeout
        self.session = requests.Session() if HAS_REQUESTS else None

    def ping(self, module: dict) -> tuple[bool, float]:
        if not self.session:
            return False, 0.0
        url = f"http://127.0.0.1:{module['port']}{module['health_endpoint']}"
        t0  = time.time()
        try:
            r = self.session.get(url, timeout=self.timeout)
            ms= (time.time()-t0)*1000
            return r.status_code == 200, round(ms, 1)
        except Exception:
            return False, round((time.time()-t0)*1000, 1)

    def check_all(self) -> dict[str, tuple[bool, float]]:
        results = {}
        for mod in MODULES:
            ok, ms = self.ping(mod)
            results[mod["id"]] = (ok, ms)
        return results

    def wait_for(self, module: dict,
                 timeout_secs: float = 15.0,
                 interval: float = 0.5) -> bool:
        deadline = time.time() + timeout_secs
        while time.time() < deadline:
            ok, _ = self.ping(module)
            if ok: return True
            time.sleep(interval)
        return False


# ─── Dashboard ────────────────────────────────────────────────────────────────

class Dashboard:
    def __init__(self, health: HealthChecker, proc: ProcessManager):
        self.health = health
        self.proc   = proc
        self.start_time = datetime.now()
        self._results: dict = {}

    def refresh(self):
        self._results = self.health.check_all()

    def render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=5),
            Layout(name="body"),
            Layout(name="footer", size=4)
        )
        layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )

        layout["header"].update(self._render_header())
        layout["left"].update(self._render_module_grid())
        layout["right"].update(self._render_tier_map())
        layout["footer"].update(self._render_footer())
        return layout

    def _render_header(self) -> Panel:
        alive   = sum(1 for ok,_ in self._results.values() if ok)
        total   = len(MODULES)
        uptime  = round((datetime.now()-self.start_time).total_seconds(), 0)
        status  = "FULLY OPERATIONAL" if alive==total else f"{alive}/{total} MODULES LIVE"
        color   = "green" if alive==total else "yellow" if alive>total//2 else "red"
        return Panel(
            Align.center(Text(
                f"⬡ FORGE COGNITIVE ARCHITECTURE  |  "
                f"{status}  |  "
                f"Uptime: {int(uptime)}s  |  "
                f"{datetime.now().strftime('%H:%M:%S')}",
                style=f"bold {color}"
            )),
            style=color, border_style=color
        )

    def _render_module_grid(self) -> Panel:
        t = Table(box=box.SIMPLE, show_header=True, expand=True)
        t.add_column("", width=3)
        t.add_column("Module",   style="bold", width=18)
        t.add_column("Role",     width=16)
        t.add_column("Port",     justify="right", width=6)
        t.add_column("Status",   width=8)
        t.add_column("Latency",  justify="right", width=8)

        current_tier = 0
        for mod in MODULES:
            if mod["tier"] != current_tier:
                current_tier = mod["tier"]
                tier_names = {1:"PERCEPTION & EMOTION",2:"SOCIAL & MEMORY",
                              3:"DECISION & ACTION",4:"COORDINATION",5:"ORCHESTRATION"}
                t.add_row("","","","",
                          f"[dim]── Tier {current_tier}: {tier_names.get(current_tier,'')} ──[/dim]",
                          "")

            ok, ms  = self._results.get(mod["id"], (False, 0.0))
            color   = mod["color"]
            status  = "[green]● LIVE[/green]" if ok else "[red]○ DOWN[/red]"
            lat     = f"[{'green' if ms<100 else 'yellow' if ms<500 else 'red'}]{ms:.0f}ms[/]" if ok else "[dim]—[/dim]"

            t.add_row(
                mod["emoji"],
                f"[{color}]{mod['name']}[/{color}]",
                f"[dim]{mod['role']}[/dim]",
                f"[dim]:{mod['port']}[/dim]",
                status, lat
            )
        return Panel(t, title="[bold]MODULE REGISTRY[/bold]", border_style="dim")

    def _render_tier_map(self) -> Panel:
        tiers = {1:[],2:[],3:[],4:[],5:[]}
        for mod in MODULES:
            ok,_ = self._results.get(mod["id"],(False,0.0))
            tiers[mod["tier"]].append((mod, ok))

        lines = []
        lines.append("[bold]COGNITIVE PIPELINE[/bold]\n")
        lines.append("  Signal In")
        lines.append("     │")

        tier_labels = {
            1: "Perception & Emotion",
            2: "Social & Memory",
            3: "Decision & Action",
            4: "Coordination",
            5: "Orchestration"
        }

        for tier_num in range(1, 6):
            mods = tiers[tier_num]
            alive= sum(1 for _,ok in mods if ok)
            total= len(mods)
            tc   = "green" if alive==total else "yellow" if alive>0 else "red"
            lines.append(f"  [{tc}]┌─ Tier {tier_num}: {tier_labels[tier_num]}[/{tc}]")
            for mod, ok in mods:
                sc = "green" if ok else "red"
                lines.append(
                    f"  [{sc}]│  {mod['emoji']} {mod['name']:<18}[/{sc}]"
                    f"[dim]:{mod['port']}[/dim]"
                )
            lines.append(f"  [{tc}]└{'─'*35}[/{tc}]")
            if tier_num < 5:
                lines.append("     │")

        lines.append("     │")
        lines.append("  Response Out")

        return Panel("\n".join(lines),
                    title="[bold]Pipeline Architecture[/bold]",
                    border_style="dim")

    def _render_footer(self) -> Panel:
        alive   = sum(1 for ok,_ in self._results.values() if ok)
        total   = len(MODULES)
        avg_lat = round(
            sum(ms for _,ms in self._results.values()) / max(len(self._results),1), 1
        )
        return Panel(
            f"[dim]Alive: [green]{alive}[/green]/{total}  |  "
            f"Avg latency: {avg_lat}ms  |  "
            f"[bold]Press Ctrl+C to stop all modules and exit[/bold][/dim]",
            border_style="dim"
        )


# ─── Launcher ─────────────────────────────────────────────────────────────────

class ForgeLauncher:
    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(__file__).parent
        self.proc     = ProcessManager(self.base_dir)
        self.health   = HealthChecker()
        self.dashboard= Dashboard(self.health, self.proc)

    def check_dependencies(self) -> tuple[bool, list[str]]:
        missing = []
        if not HAS_REQUESTS:
            missing.append("requests  (pip install requests)")
        if not HAS_RICH:
            missing.append("rich      (pip install rich)")
        try:
            import flask
        except ImportError:
            missing.append("flask     (pip install flask)")
        return len(missing)==0, missing

    def check_files(self) -> tuple[bool, list[str]]:
        missing = []
        for mod in MODULES:
            path = self.base_dir / mod["file"]
            if not path.exists():
                missing.append(mod["file"])
        return len(missing)==0, missing

    def launch_all(self, verbose: bool = True):
        if HAS_RICH and verbose:
            console.print(Panel.fit(
                "[bold cyan]⬡ FORGE BRAIN LAUNCHER[/bold cyan]\n"
                "[dim]Starting all cognitive architecture modules...[/dim]",
                border_style="cyan"
            ))

        # Dependency check
        ok, missing_deps = self.check_dependencies()
        if not ok:
            if HAS_RICH:
                console.print("[red]Missing dependencies:[/red]")
                for d in missing_deps:
                    console.print(f"  [red]✗[/red] {d}")
                console.print("\nRun: pip install flask rich requests")
            sys.exit(1)

        # File check
        ok, missing_files = self.check_files()
        if not ok:
            if HAS_RICH:
                console.print("[yellow]Missing module files:[/yellow]")
                for f in missing_files:
                    console.print(f"  [yellow]?[/yellow] {f}")
                console.print(
                    "[dim]Make sure all forge_*.py files are in the same directory.[/dim]"
                )

        # Launch by tier
        tiers = {}
        for mod in MODULES:
            tiers.setdefault(mod["tier"], []).append(mod)

        if HAS_RICH and verbose:
            console.print()

        for tier_num in sorted(tiers.keys()):
            tier_mods = tiers[tier_num]
            tier_names= {1:"Perception & Emotion",2:"Social & Memory",
                         3:"Decision & Action",4:"Coordination",5:"Orchestration"}

            if HAS_RICH and verbose:
                console.print(
                    f"[bold dim]━━━ Tier {tier_num}: {tier_names.get(tier_num,'')} ━━━[/bold dim]"
                )

            # Launch all modules in this tier simultaneously
            for mod in tier_mods:
                filepath = self.base_dir / mod["file"]
                if not filepath.exists():
                    if HAS_RICH and verbose:
                        console.print(
                            f"  [dim]{mod['emoji']} {mod['name']:<20}[/dim]  "
                            f"[yellow]⚠ file not found[/yellow]"
                        )
                    continue

                launched, info = self.proc.launch(mod)
                if HAS_RICH and verbose:
                    status = "[green]✓ launched[/green]" if launched else f"[red]✗ {info}[/red]"
                    console.print(
                        f"  [{mod['color']}]{mod['emoji']} {mod['name']:<20}[/{mod['color']}]  "
                        f":{mod['port']}  {status}"
                    )

            # Wait for this tier to be healthy before launching next
            if HAS_RICH and verbose:
                console.print(f"  [dim]Waiting for Tier {tier_num} to be ready...[/dim]")

            wait_start = time.time()
            tier_ready = True
            for mod in tier_mods:
                filepath = self.base_dir / mod["file"]
                if not filepath.exists():
                    continue
                ready = self.health.wait_for(mod, timeout_secs=12.0)
                if not ready:
                    tier_ready = False
                    if HAS_RICH and verbose:
                        console.print(
                            f"  [yellow]⚠ {mod['name']} not responding — continuing anyway[/yellow]"
                        )

            elapsed = round(time.time()-wait_start, 1)
            if HAS_RICH and verbose:
                color = "green" if tier_ready else "yellow"
                console.print(
                    f"  [{color}]Tier {tier_num} ready in {elapsed}s[/{color}]\n"
                )

        if HAS_RICH and verbose:
            alive = sum(1 for ok,_ in self.health.check_all().values() if ok)
            total = len(MODULES)
            color = "green" if alive==total else "yellow"
            console.print(Panel(
                f"[bold {color}]{alive}/{total} modules online[/bold {color}]\n"
                f"[dim]Orchestrator at http://127.0.0.1:7786[/dim]\n"
                f"[dim]Send signals via POST /process[/dim]",
                title="[bold]FORGE Brain Online[/bold]",
                border_style=color
            ))

    def run_dashboard(self):
        """Show live updating dashboard."""
        if not HAS_RICH:
            self._run_simple_status()
            return

        try:
            with Live(self.dashboard.render(),
                     refresh_per_second=2,
                     screen=True) as live:
                while True:
                    self.dashboard.refresh()
                    live.update(self.dashboard.render())
                    time.sleep(0.5)
        except KeyboardInterrupt:
            pass

    def _run_simple_status(self):
        """Non-rich status output."""
        results = self.health.check_all()
        print("\nFORGE Brain Status")
        print("="*50)
        for mod in MODULES:
            ok, ms = results.get(mod["id"], (False, 0.0))
            status = "LIVE" if ok else "DOWN"
            print(f"  {mod['name']:<25} :{mod['port']}  {status}")
        alive = sum(1 for ok,_ in results.values() if ok)
        print(f"\n{alive}/{len(MODULES)} modules alive")

    def stop_all(self):
        if HAS_RICH:
            console.print("[yellow]Stopping all FORGE modules...[/yellow]")
        self.proc.stop_all()
        if HAS_RICH:
            console.print("[green]✓ All modules stopped[/green]")

    def launch_and_watch(self):
        """Launch all modules then show live dashboard."""
        self.launch_all(verbose=True)

        if HAS_RICH:
            console.print("\n[dim]Starting live dashboard — Ctrl+C to stop all...[/dim]\n")
            time.sleep(1)

        try:
            self.run_dashboard()
        except KeyboardInterrupt:
            pass
        finally:
            if HAS_RICH:
                console.print("\n")
                if Confirm.ask("[yellow]Stop all FORGE modules?[/yellow]"):
                    self.stop_all()
            else:
                self.stop_all()

    def quick_check(self):
        """Just check health of all modules."""
        if HAS_RICH:
            console.print(Panel.fit(
                "[bold cyan]⬡ FORGE Health Check[/bold cyan]",
                border_style="cyan"
            ))

        results = self.health.check_all()
        alive   = 0

        for mod in MODULES:
            ok, ms = results.get(mod["id"], (False, 0.0))
            if ok: alive += 1

            if HAS_RICH:
                status = "[green]● LIVE[/green]" if ok else "[red]○ DOWN[/red]"
                lat    = f"[dim]{ms:.0f}ms[/dim]" if ok else ""
                console.print(
                    f"  [{mod['color']}]{mod['emoji']} {mod['name']:<22}[/{mod['color']}]  "
                    f":{mod['port']}  {status}  {lat}"
                )
            else:
                print(f"  {'LIVE' if ok else 'DOWN'}  {mod['name']}")

        if HAS_RICH:
            color = "green" if alive==len(MODULES) else "yellow" if alive>0 else "red"
            console.print(
                f"\n[{color}]{alive}/{len(MODULES)} modules alive[/{color}]"
            )

    def launch_one(self, module_id: str):
        """Launch a single module by ID."""
        mod = next((m for m in MODULES if m["id"] == module_id), None)
        if not mod:
            ids = [m["id"] for m in MODULES]
            if HAS_RICH:
                console.print(f"[red]Unknown module: {module_id}[/red]")
                console.print(f"[dim]Available: {', '.join(ids)}[/dim]")
            return

        filepath = self.base_dir / mod["file"]
        if not filepath.exists():
            if HAS_RICH:
                console.print(f"[red]File not found: {mod['file']}[/red]")
            return

        if HAS_RICH:
            console.print(
                f"[{mod['color']}]{mod['emoji']} Launching {mod['name']}...[/{mod['color']}]"
            )

        launched, info = self.proc.launch(mod)
        if launched:
            ready = self.health.wait_for(mod, timeout_secs=10.0)
            if HAS_RICH:
                if ready:
                    console.print(f"[green]✓ {mod['name']} online at :{mod['port']}[/green]")
                else:
                    console.print(f"[yellow]⚠ {mod['name']} launched but not responding[/yellow]")
        else:
            if HAS_RICH:
                console.print(f"[red]✗ Failed to launch: {info}[/red]")


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="FORGE Brain Launcher — starts all cognitive architecture modules"
    )
    parser.add_argument("--check",  action="store_true", help="Health check only")
    parser.add_argument("--stop",   action="store_true", help="Stop all modules")
    parser.add_argument("--status", action="store_true", help="Show status dashboard")
    parser.add_argument("--module", type=str, metavar="ID",
                        help="Launch a single module by ID")
    parser.add_argument("--no-watch", action="store_true",
                        help="Launch without live dashboard")
    parser.add_argument("--dir", type=str, default=None,
                        help="Directory containing forge_*.py files")
    args = parser.parse_args()

    # Base directory
    if args.dir:
        base_dir = Path(args.dir)
    else:
        base_dir = Path(__file__).parent

    launcher = ForgeLauncher(base_dir)

    # Handle commands
    if args.check:
        launcher.quick_check()

    elif args.stop:
        launcher.stop_all()

    elif args.status:
        launcher.dashboard.refresh()
        if HAS_RICH:
            console.print(launcher.dashboard.render())
        else:
            launcher._run_simple_status()

    elif args.module:
        launcher.launch_one(args.module)

    elif args.no_watch:
        launcher.launch_all(verbose=True)

    else:
        # Default: launch everything + live dashboard
        launcher.launch_and_watch()


if __name__ == "__main__":
    # Handle Ctrl+C gracefully
    def sigint_handler(sig, frame):
        if HAS_RICH:
            console.print("\n[yellow]Interrupted — cleaning up...[/yellow]")
        sys.exit(0)

    signal.signal(signal.SIGINT, sigint_handler)
    main()
