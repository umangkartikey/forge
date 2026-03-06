#!/usr/bin/env python3
"""
FORGE CLI — One Command To Rule Them All
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  forge investigate github.com
  forge sherlock --read "tall man, ink stained fingers"
  forge detective --image crime_scene.jpg
  forge nexus --run suspicious.domain.com
  forge ghost --mission "watch @target" watch
  forge pentest http://localhost:8080/api
  forge monitor start
  forge arena --rounds 5
  forge report --case cases/abc123.json
  forge status

Install as CLI:
  pip install -e .
  # or
  alias forge="python3 /path/to/forge_cli.py"
"""

import sys, os, json, subprocess
from pathlib import Path

# ── ANSI colours (no dependency) ─────────────────────────────────────────────
Y  = "\033[93m"   # yellow
G  = "\033[92m"   # green
R  = "\033[91m"   # red
C  = "\033[96m"   # cyan
D  = "\033[2m"    # dim
B  = "\033[1m"    # bold
RS = "\033[0m"    # reset

def p(msg): print(msg)

BASE = Path(__file__).parent

# ── Tool map ──────────────────────────────────────────────────────────────────
TOOLS = {
    "investigate": {
        "file":    "forge_investigate.py",
        "desc":    "OSINT — gather public intelligence on any target",
        "example": "forge investigate github.com",
        "args":    "<target>",
    },
    "sherlock": {
        "file":    "forge_sherlock.py",
        "desc":    "Mind Palace — AI deduction chains (Sherlock Holmes)",
        "example": "forge sherlock --read 'tall man, worn boots'",
        "args":    "[--read <desc>] [--observe <image>] [--server]",
    },
    "detective": {
        "file":    "forge_detective.py",
        "desc":    "Batcomputer — case file, verdict engine, profiler",
        "example": "forge detective --image crime_scene.jpg",
        "args":    "[--image <path>] [--case <name>] [--server]",
    },
    "nexus": {
        "file":    "forge_nexus.py",
        "desc":    "NEXUS — unified pipeline: OSINT → Sherlock → Detective",
        "example": "forge nexus --run suspicious.com",
        "args":    "[--run <target>] [--brief] [--server] [--status]",
    },
    "ghost": {
        "file":    "forge_ghost.py",
        "desc":    "Ghost — autonomous 24/7 agent, runs missions forever",
        "example": "forge ghost --mission 'watch @target' watch",
        "args":    "[--mission <target> <type>] [--list] [--daemon] [--brief]",
    },
    "monitor": {
        "file":    "forge_monitor.py",
        "desc":    "Monitor — production AI watchdog with alerting",
        "example": "forge monitor start",
        "args":    "[start|stop|status|alerts]",
    },
    "pentest": {
        "file":    "forge_llm_pentest.py",
        "desc":    "Pentest — OWASP LLM Top 10 security audit",
        "example": "forge pentest http://localhost:8080/api",
        "args":    "<target_url> [--quick] [--full] [--report]",
    },
    "swarm": {
        "file":    "forge_swarm.py",
        "desc":    "Swarm — self-replicating AI agent swarm",
        "example": "forge swarm --target localhost:8080",
        "args":    "[--target <url>] [--agents <n>] [--evolve]",
    },
    "learn": {
        "file":    "forge_learn.py",
        "desc":    "Learn — AI that improves from every attack",
        "example": "forge learn --stats",
        "args":    "[--stats] [--patterns] [--improve]",
    },
    "arena": {
        "file":    "forge_arena.py",
        "desc":    "Arena — AI vs AI live attack/defend battles",
        "example": "forge arena --rounds 5",
        "args":    "[--rounds <n>] [--model1 <m>] [--model2 <m>]",
    },
    "report": {
        "file":    "forge_report.py",
        "desc":    "Report — generate beautiful HTML reports from cases",
        "example": "forge report --case forge_nexus/cases/abc123.json",
        "args":    "[--case <json>] [--all] [--output <dir>]",
    },
    "honeypot": {
        "file":    "forge_honeypot.py",
        "desc":    "Honeypot — decoy AI that catches and profiles attackers",
        "example": "forge honeypot --port 8888",
        "args":    "[--port <n>] [--config <file>]",
    },
}

BANNER = f"""
{Y}{B}
  ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
  ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
  █████╗  ██║   ██║██████╔╝██║  ███╗█████╗
  ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝
  ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
  ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
{RS}{B}  Framework for Orchestrated Reasoning & Generation of Engines{RS}
{D}  github.com/umangkartikey/forge{RS}
"""

def show_banner():
    p(BANNER)

def show_help():
    show_banner()
    p(f"{Y}{B}COMMANDS{RS}\n")
    for name, tool in TOOLS.items():
        fp      = BASE / tool["file"]
        status  = f"{G}✅{RS}" if fp.exists() else f"{D}⬜{RS}"
        p(f"  {status}  {Y}{B}forge {name:<14}{RS}  {tool['desc']}")
        p(f"         {D}{tool['example']}{RS}")
    p(f"""
{Y}{B}QUICK START{RS}
  forge status                   Check all tools
  forge nexus --run example.com  Full intelligence pipeline
  forge ghost --daemon           Start autonomous agent
  forge arena --rounds 3         AI vs AI battle

{Y}{B}GLOBAL FLAGS{RS}
  --help     Show tool help
  --version  Show version
  --quiet    Minimal output
""")

def show_status():
    show_banner()
    p(f"{Y}{B}FORGE ECOSYSTEM STATUS{RS}\n")

    total_lines = 0
    available   = 0
    for name, tool in TOOLS.items():
        fp = BASE / tool["file"]
        if fp.exists():
            lines = len(fp.read_text().splitlines())
            total_lines += lines
            available   += 1
            p(f"  {G}✅{RS}  {Y}{name:<14}{RS}  {D}{lines:>5} lines{RS}  {tool['desc']}")
        else:
            p(f"  {D}⬜  {name:<14}  missing  {tool['desc']}{RS}")

    # Count HTML UIs
    html_files = list(BASE.glob("*.html")) + list((BASE / "..").glob("*.html"))
    html_lines = sum(len(f.read_text().splitlines()) for f in html_files if f.exists())

    p(f"""
  {Y}{B}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RS}
  {G}Tools:{RS}      {available}/{len(TOOLS)} available
  {G}Python:{RS}     {total_lines:,} lines
  {G}HTML UIs:{RS}   {html_lines:,} lines  ({len(html_files)} interfaces)
  {G}Total:{RS}      {total_lines + html_lines:,} lines
""")

def run_tool(tool_name, extra_args):
    """Launch a FORGE tool as subprocess."""
    tool = TOOLS.get(tool_name)
    if not tool:
        p(f"{R}Unknown tool: {tool_name}{RS}")
        p(f"Run '{Y}forge help{RS}' for available tools.")
        sys.exit(1)

    fp = BASE / tool["file"]
    if not fp.exists():
        p(f"{R}Tool not found: {tool['file']}{RS}")
        p(f"{D}Expected at: {fp}{RS}")
        sys.exit(1)

    cmd = [sys.executable, str(fp)] + extra_args
    os.execv(sys.executable, cmd)  # replace process — no subprocess overhead

def quick_investigate(target):
    """Shortcut: run investigation directly."""
    tool = TOOLS["investigate"]
    fp   = BASE / tool["file"]
    if fp.exists():
        os.execv(sys.executable, [sys.executable, str(fp), target])
    else:
        p(f"{R}forge_investigate.py not found{RS}")

def quick_nexus(target):
    """Shortcut: run full nexus pipeline."""
    fp = BASE / "forge_nexus.py"
    if fp.exists():
        os.execv(sys.executable, [sys.executable, str(fp), "--investigate", target])
    else:
        p(f"{R}forge_nexus.py not found{RS}")

def main():
    args = sys.argv[1:]

    if not args or args[0] in ("help", "--help", "-h"):
        show_help()
        return

    if args[0] in ("version", "--version", "-v"):
        p(f"FORGE v2.0 — {len(TOOLS)} tools — github.com/umangkartikey/forge")
        return

    if args[0] in ("status", "--status"):
        show_status()
        return

    # Shortcut: forge <url> → auto-detect and run nexus
    if args[0].startswith(("http://","https://")) or "." in args[0] and "/" not in args[0]:
        p(f"{Y}Auto-routing to NEXUS pipeline: {args[0]}{RS}")
        quick_nexus(args[0])
        return

    tool_name  = args[0].lower()
    extra_args = args[1:]

    # Aliases
    aliases = {
        "investigate": "investigate", "inv": "investigate", "osint": "investigate",
        "sherlock":    "sherlock",    "sh":  "sherlock",
        "detective":   "detective",   "det": "detective",   "bat": "detective",
        "nexus":       "nexus",       "nx":  "nexus",
        "ghost":       "ghost",       "gh":  "ghost",
        "monitor":     "monitor",     "mon": "monitor",
        "pentest":     "pentest",     "pt":  "pentest",
        "swarm":       "swarm",
        "learn":       "learn",
        "arena":       "arena",
        "report":      "report",      "rep": "report",
        "honeypot":    "honeypot",    "hp":  "honeypot",
    }

    resolved = aliases.get(tool_name)
    if not resolved:
        p(f"{R}Unknown command: {tool_name}{RS}")
        p(f"Run '{Y}forge help{RS}' to see available tools.")
        sys.exit(1)

    run_tool(resolved, extra_args)

if __name__ == "__main__":
    main()
