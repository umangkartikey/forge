"""
███████╗ ██████╗ ██████╗  ██████╗ ███████╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
█████╗  ██║   ██║██████╔╝██║  ███╗█████╗
██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝
██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝

Framework for Orchestrated Reasoning & Generation of Engines

Features:
  ✨ Build · 🤖 AI-to-AI · 🚀 Auto · 🔧 Improve · 🎛️ Remix
  🔗 Chain · 🧪 Test · 🌐 Web · 🧬 Genetic · 🔁 Self-Heal
  🎯 Goal Mode · 📊 Profiler · 🧠 Learning Engine · 📡 Ecosystem

Requirements:
    pip install anthropic rich

Usage:
    python forge.py
"""

import anthropic
import os, sys, re, json, shutil, subprocess, time, random, hashlib, zipfile
from pathlib import Path
from datetime import datetime
from urllib.request import urlopen, Request as UReq
from urllib.parse import quote_plus
from collections import defaultdict

# ── Rich UI ───────────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.syntax import Syntax
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.columns import Columns
    from rich import box as rbox
    from rich.markdown import Markdown
    from rich.text import Text
    RICH = True
    console = Console()
except ImportError:
    RICH = False; console = None

def cprint(msg, style=""):
    if RICH: console.print(msg, style=style)
    else: print(re.sub(r"\[.*?\]", "", str(msg)))

def ask(msg, default=""):
    if RICH: return Prompt.ask(msg, default=default)
    r = input(f"{msg}{f' [{default}]' if default else ''}: ").strip()
    return r or default

def confirm(msg):
    if RICH: return Confirm.ask(msg)
    return input(f"{msg} (y/n): ").lower() == "y"

# ── Config ────────────────────────────────────────────────────────────────────
MODEL      = "claude-sonnet-4-6"
FORGE_DIR  = Path("forge_tools")
REGISTRY   = FORGE_DIR / "registry.json"
MEMORY_F   = FORGE_DIR / "memory.json"
PATTERNS_F = FORGE_DIR / "patterns.json"
PROFILE_F  = FORGE_DIR / "profiles.json"
FORGE_DIR.mkdir(exist_ok=True)

client = anthropic.Anthropic()

# ══════════════════════════════════════════════════════════════════════════════
# REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

def load_reg():
    return json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}

def save_reg(reg):
    REGISTRY.write_text(json.dumps(reg, indent=2))

def register(name, fp, desc, tags, extra=None):
    reg = load_reg(); ex = reg.get(name, {})
    reg[name] = {
        "file": str(fp), "description": desc, "tags": tags,
        "created": ex.get("created", datetime.now().isoformat()),
        "updated": datetime.now().isoformat(),
        "runs": ex.get("runs", 0), "version": ex.get("version", 0) + 1,
        "rating": ex.get("rating", None), "test_status": ex.get("test_status", "untested"),
        "heal_count": ex.get("heal_count", 0), "avg_runtime": ex.get("avg_runtime", None),
        "fail_count": ex.get("fail_count", 0), **(extra or {}),
    }
    save_reg(reg)

def save_tool(name, desc, code, tags, extra=None):
    safe = re.sub(r"[^\w]", "_", name.lower())[:40]
    fp   = FORGE_DIR / f"{safe}.py"
    if fp.exists():
        ver = load_reg().get(name, {}).get("version", 1)
        shutil.copy(fp, FORGE_DIR / f"{safe}_v{ver}.py")
    header = f"# FORGE TOOL\n# DESCRIPTION: {desc}\n# TAGS: {', '.join(tags)}\n# UPDATED: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    fp.write_text(header + code + "\n")
    register(name, fp, desc, tags, extra)
    cprint(f"✅  Saved → {fp}", "bold green")
    return fp

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 LEARNING ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def load_memory():
    if MEMORY_F.exists(): return json.loads(MEMORY_F.read_text())
    return {"tool_history": [], "insights": [], "preferences": {}, "sessions": 0, "user_style": ""}

def save_memory(m): MEMORY_F.write_text(json.dumps(m, indent=2))

def load_patterns():
    if PATTERNS_F.exists(): return json.loads(PATTERNS_F.read_text())
    return {"successes": [], "failures": [], "tag_approaches": {}, "complexity_map": {}}

def save_patterns(p): PATTERNS_F.write_text(json.dumps(p, indent=2))

def learn_from_build(name, desc, tags, code, success, rating=None, error=None):
    """Core learning: extract patterns from every build outcome."""
    m = load_memory(); p = load_patterns()

    # Record in history
    m["tool_history"].append({
        "tool": name, "description": desc, "tags": tags,
        "success": success, "rating": rating,
        "timestamp": datetime.now().isoformat(),
        "code_lines": len(code.splitlines()) if code else 0,
    })
    m["tool_history"] = m["tool_history"][-200:]

    # Pattern learning
    entry = {"desc": desc, "tags": tags, "rating": rating,
             "lines": len(code.splitlines()) if code else 0}

    if success and rating and rating >= 4:
        p["successes"].append(entry)
        p["successes"] = p["successes"][-50:]
        # Learn tag-to-approach mapping
        for t in tags:
            if t not in p["tag_approaches"]:
                p["tag_approaches"][t] = {"count": 0, "avg_rating": 0, "tips": []}
            ta = p["tag_approaches"][t]
            ta["count"] += 1
            ta["avg_rating"] = (ta["avg_rating"] * (ta["count"]-1) + (rating or 3)) / ta["count"]

    if not success or (rating and rating <= 2):
        p["failures"].append({"desc": desc, "tags": tags, "error": error or "low rating"})
        p["failures"] = p["failures"][-30:]

    save_memory(m); save_patterns(p)

def memory_context():
    """Build rich context string to inject into prompts."""
    m = load_memory(); p = load_patterns()
    parts = []
    if m.get("user_style"):
        parts.append(f"User coding style: {m['user_style']}")
    if m.get("preferences"):
        parts.append("Preferences: " + "; ".join(f"{k}:{v}" for k,v in m["preferences"].items()))
    recent = m.get("tool_history", [])[-5:]
    if recent:
        parts.append(f"Recently built: {', '.join(e['tool'] for e in recent)}")
    if p.get("successes"):
        top = sorted(p["successes"], key=lambda x: x.get("rating",0) or 0, reverse=True)[:3]
        parts.append(f"High-rated approaches used: {'; '.join(e['desc'][:40] for e in top)}")
    if p.get("failures"):
        parts.append(f"Approaches to avoid: {'; '.join(e['desc'][:30] for e in p['failures'][-2:])}")
    if m.get("insights"):
        parts.append(f"Learned insights: {'; '.join(m['insights'][-3:])}")
    return "\n".join(parts)

def get_smart_tips(tags):
    """Get learned tips for specific tags."""
    p = load_patterns(); tips = []
    for t in tags:
        if t in p.get("tag_approaches", {}):
            ta = p["tag_approaches"][t]
            if ta["count"] >= 2:
                tips.append(f"For '{t}' tools (tried {ta['count']}x, avg rating {ta['avg_rating']:.1f})")
    return tips

# ══════════════════════════════════════════════════════════════════════════════
# 📊 PERFORMANCE PROFILER
# ══════════════════════════════════════════════════════════════════════════════

def load_profiles():
    return json.loads(PROFILE_F.read_text()) if PROFILE_F.exists() else {}

def save_profiles(pr): PROFILE_F.write_text(json.dumps(pr, indent=2))

def profile_run(name, filepath):
    """Run a tool, measure performance, record results."""
    reg = load_reg(); profiles = load_profiles()
    cprint(f"\n▶️  Running [bold]{filepath.name}[/bold]...\n" if RICH else f"\n▶️  Running {filepath.name}...\n", "bold yellow")
    print("─" * 55)
    start = time.time()
    result = subprocess.run([sys.executable, str(filepath)], timeout=120)
    elapsed = round(time.time() - start, 2)
    print("─" * 55)

    success = result.returncode == 0
    cprint(f"   Exit: {result.returncode} | Time: {elapsed}s", "green" if success else "red")

    # Update profiles
    if name not in profiles:
        profiles[name] = {"runs": [], "avg_time": 0, "fail_rate": 0}
    pr = profiles[name]
    pr["runs"].append({"time": elapsed, "success": success, "ts": datetime.now().isoformat()})
    pr["runs"] = pr["runs"][-20:]
    pr["avg_time"] = round(sum(r["time"] for r in pr["runs"]) / len(pr["runs"]), 2)
    pr["fail_rate"] = round(sum(1 for r in pr["runs"] if not r["success"]) / len(pr["runs"]) * 100, 1)
    save_profiles(profiles)

    # Update registry
    reg2 = load_reg()
    if name in reg2:
        reg2[name]["runs"] = reg2[name].get("runs", 0) + 1
        reg2[name]["avg_runtime"] = pr["avg_time"]
        if not success:
            reg2[name]["fail_count"] = reg2[name].get("fail_count", 0) + 1
        save_reg(reg2)

    return success, elapsed, result.returncode

def cmd_profiler():
    """Show performance dashboard for all tools."""
    profiles = load_profiles(); reg = load_reg()
    if not profiles:
        cprint("No profile data yet. Run some tools first!", "yellow"); return

    if RICH:
        table = Table(title="📊  FORGE Performance Profiler", border_style="cyan",
                      show_lines=True, box=rbox.ROUNDED)
        table.add_column("Tool",     style="bold white", min_width=18)
        table.add_column("Runs",     style="green",   width=6)
        table.add_column("Avg Time", style="cyan",    width=10)
        table.add_column("Fail %",   style="red",     width=8)
        table.add_column("Rating",   style="yellow",  width=8)
        table.add_column("Health",   style="bold",    width=10)

        for name, pr in sorted(profiles.items(), key=lambda x: -len(x[1].get("runs",[]))):
            info = reg.get(name, {})
            fail_r = pr.get("fail_rate", 0)
            rating = info.get("rating", "─")
            health = "🟢 Great" if fail_r < 10 else ("🟡 OK" if fail_r < 40 else "🔴 Needs fix")
            table.add_row(
                name, str(len(pr.get("runs",[]))),
                f"{pr.get('avg_time',0)}s",
                f"{fail_r}%", str(rating), health
            )
        console.print(table)
    else:
        for name, pr in profiles.items():
            print(f"  {name}: avg {pr.get('avg_time',0)}s | fail {pr.get('fail_rate',0)}%")

    # Recommend improvements
    troubled = [(n, pr) for n, pr in profiles.items() if pr.get("fail_rate", 0) > 30]
    if troubled:
        cprint(f"\n⚠️   {len(troubled)} tool(s) need attention:", "yellow")
        for name, pr in troubled:
            cprint(f"   • {name} — {pr['fail_rate']}% failure rate", "red")
        if confirm("\n🔧  Auto-improve highest-failure tool?"):
            worst = max(troubled, key=lambda x: x[1]["fail_rate"])
            _cmd_improve_named(worst[0], "fix the failures and improve reliability")

# ══════════════════════════════════════════════════════════════════════════════
# AI HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def ai(prompt, system, max_tokens=3500):
    return client.messages.create(
        model=MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": prompt}]
    ).content[0].text

def ai_stream_print(prompt, system, label="🤖  Thinking"):
    """Stream AI response and print it."""
    if RICH:
        with Progress(SpinnerColumn(), TextColumn(f"[bold cyan]{label}..."), transient=True) as p:
            p.add_task("", total=None)
            r = client.messages.create(model=MODEL, max_tokens=3500, system=system,
                messages=[{"role":"user","content":prompt}])
    else:
        print(f"\n{label}...\n")
        r = client.messages.create(model=MODEL, max_tokens=3500, system=system,
            messages=[{"role":"user","content":prompt}])
    return r.content[0].text

def extract(txt):
    dm = re.search(r"#\s*DESCRIPTION:\s*(.+)", txt)
    tm = re.search(r"#\s*TAGS:\s*(.+)", txt)
    cm = re.search(r"```python\s*(.*?)```", txt, re.DOTALL)
    if not cm: raise ValueError("No code block found")
    return (
        dm.group(1).strip() if dm else "FORGE tool",
        cm.group(1).strip(),
        [t.strip() for t in tm.group(1).split(",")] if tm else [],
    )

def show_code(code, title):
    if RICH:
        console.print(Panel(Syntax(code, "python", theme="monokai", line_numbers=True),
                            title=f"[bold green]{title}", border_style="green"))
    else:
        print(f"\n# {title}\n{'─'*55}\n{code}\n{'─'*55}")

def pick_tool(prompt_text, subset=None):
    reg = subset if subset is not None else load_reg()
    if not reg: cprint("No tools yet.", "yellow"); return None, None
    show_table(reg)
    items = list(reg.items())
    try:
        n = int(input(f"\n{prompt_text} (number): ")) - 1
        name, info = items[n]
        return name, Path(info["file"])
    except (ValueError, IndexError):
        cprint("Invalid.", "red"); return None, None

def _ask_rating():
    try:
        r = input("\n⭐  Rate (1-5, Enter to skip): ").strip()
        return int(r) if r and 1 <= int(r) <= 5 else None
    except ValueError: return None

def _set_rating(name, rating):
    reg = load_reg()
    if name in reg: reg[name]["rating"] = rating; save_reg(reg)
    cprint(f"   {'⭐'*rating}", "yellow")

# ══════════════════════════════════════════════════════════════════════════════
# PROMPTS
# ══════════════════════════════════════════════════════════════════════════════

P_BUILD = """You are FORGE's master builder — an expert Python developer.
Build small, focused, well-crafted tools.

Reply with:
1. # DESCRIPTION: one-line summary
2. # TAGS: comma-separated tags
3. ```python ... ``` complete working code

Rules: Single file. main() + __main__. Use input() for user input.
Stdlib only unless necessary (add # REQUIRES: pkg). Robust error handling."""

P_IMPROVE = P_BUILD.replace("Build small, focused, well-crafted tools.", "Improve the given tool meaningfully.")
P_REMIX   = P_BUILD.replace("Build small, focused, well-crafted tools.", "Combine two tools into one cohesive tool.")
P_WEB     = P_BUILD.replace("Build small, focused, well-crafted tools.", "Build a tool that fetches LIVE web data using urllib only.")
P_CHAIN   = P_BUILD.replace("Build small, focused, well-crafted tools.", "Combine multiple tools into a coherent pipeline script.")
P_EXPLAIN = "Friendly Python teacher. Explain code clearly: what it does, how it works, interesting techniques. Plain English."
P_TEST    = "Write unittest tests. Stdlib only. At least 3 meaningful test cases. Mock input() where needed. Reply ONLY with ```python...``` block."
P_HEAL    = """You are a debugger. A tool crashed with an error. Fix it.
Reply with:
1. # DESCRIPTION: updated summary
2. # TAGS: same tags
3. # FIX: one line describing what was fixed
4. ```python ... ``` fixed code"""

P_PLANNER = """Software architect. Break the goal into 2-5 focused tools.
Reply ONLY with JSON array: [{"name":"tool_name","description":"Does X"},...]"""

P_GOAL_EXECUTOR = """You are FORGE's autonomous goal executor.
Given a goal and a list of available tools, decide:
1. Which tools to run in what order
2. What data to pass between them
3. What new tools to build if needed

Reply ONLY with JSON:
{
  "plan": [{"action": "run|build", "name": "tool_name", "description": "if building", "reason": "why"}],
  "summary": "what this plan achieves"
}"""

P_AGENTS = {
    "planner": "PLANNER: Write detailed spec — inputs, outputs, edge cases, approach. No code yet.",
    "builder": """BUILDER: Write code from spec.
Reply: 1. # DESCRIPTION  2. # TAGS  3. ```python...```""",
    "critic":  "CRITIC: Find REAL bugs, edge cases, missing error handling. Numbered list. If genuinely good: 'APPROVED: reason'.",
    "fixer":   """FIXER: Fix ALL critic issues.
Reply: 1. # DESCRIPTION  2. # TAGS  3. # FIXES: list  4. ```python...```""",
    "judge":   "JUDGE: Final call.\n  VERDICT: SHIP IT — [why]\n  VERDICT: NEEDS WORK — [what's missing]",
}

P_MUTATE = """You are a code evolution engine. Take this Python tool and create an IMPROVED VARIANT.
Mutate it by: adding a feature, optimizing performance, or improving UX.
Be creative but keep it working.
Reply: 1. # DESCRIPTION  2. # TAGS  3. # MUTATION: what changed  4. ```python...```"""

P_ECOSYSTEM = """You are building a Python tool that can call OTHER tools in the FORGE ecosystem.
The tool registry contains these tools:
{registry}

Build a tool that orchestrates multiple tools together.
Reply: 1. # DESCRIPTION  2. # TAGS  3. ```python...``` (import and call other tool files directly)"""

# ══════════════════════════════════════════════════════════════════════════════
# DISPLAY
# ══════════════════════════════════════════════════════════════════════════════

def show_table(reg=None):
    reg = reg if reg is not None else load_reg()
    if not reg: cprint("  (no tools yet)", "yellow"); return
    if RICH:
        table = Table(title="⚒️  FORGE Registry", border_style="cyan",
                      show_lines=True, box=rbox.ROUNDED)
        for col, kw, w in [("#","dim",4),("Name","bold cyan",18),("Description","white",30),
                            ("Tags","blue",14),("v","yellow",3),("Runs","green",5),
                            ("⭐","bold yellow",4),("Health","bold",10)]:
            table.add_column(col, style=kw, width=w)
        for i, (name, info) in enumerate(reg.items(), 1):
            ts   = info.get("test_status","─")
            fail = info.get("fail_count",0)
            runs = info.get("runs",0)
            fail_r = round(fail/runs*100) if runs else 0
            health = "🟢" if fail_r < 10 else ("🟡" if fail_r < 40 else "🔴")
            heals  = f" 🩹×{info['heal_count']}" if info.get("heal_count",0) > 0 else ""
            table.add_row(str(i), name, info["description"][:30],
                          ", ".join(info.get("tags",[])[:2]),
                          str(info.get("version",1)), str(runs),
                          str(info.get("rating") or "─"),
                          f"{health}{heals}")
        console.print(table)
    else:
        for i, (name, info) in enumerate(reg.items(), 1):
            print(f"  {i}. [{name}] {info['description'][:50]} ⭐{info.get('rating','─')}")

# ══════════════════════════════════════════════════════════════════════════════
# ✨ BUILD
# ══════════════════════════════════════════════════════════════════════════════

def cmd_build(user_input):
    ctx = memory_context()
    tips = get_smart_tips([])
    tip_str = ("\n\nLearned tips:\n" + "\n".join(f"- {t}" for t in tips)) if tips else ""
    prompt  = (f"Context:\n{ctx}\n\nTool: {user_input}{tip_str}" if ctx else user_input + tip_str)

    result = ai_stream_print(prompt, P_BUILD, "✨  Building")
    desc, code, tags = extract(result)
    show_code(code, desc)
    cprint(f"   Tags: {', '.join(tags)}", "cyan")

    if not confirm("\n💾  Save?"): return
    name = ask("   Name", default=re.sub(r"\s+","_",user_input[:30].lower()))
    fp   = save_tool(name, desc, code, tags)
    _syntax_check(fp)

    if confirm("▶️   Run now?"):
        success, elapsed, _ = profile_run(name, fp)
        rating = _ask_rating()
        if rating: _set_rating(name, rating)
        learn_from_build(name, desc, tags, code, success, rating)

        if not success and confirm("🔁  Self-heal the error?"):
            cmd_self_heal_named(name, fp)
    else:
        learn_from_build(name, desc, tags, code, True)

# ══════════════════════════════════════════════════════════════════════════════
# 🤖 AI-TO-AI
# ══════════════════════════════════════════════════════════════════════════════

def cmd_ai2ai():
    cprint("\n🤖  AI-TO-AI MODE — Planner → Builder → Critic → Fixer → Judge\n", "bold magenta")
    desc    = ask("🎯  Tool to build")
    if not desc: return
    rounds  = min(3, max(1, int(ask("🔄  Critique rounds (1-3)", default="2"))))
    ctx     = memory_context()
    prompt  = (f"Context:\n{ctx}\n\nTool: {desc}" if ctx else desc)
    log     = []

    def run_agent(role, system, agent_prompt, color):
        emoji = {"planner":"🗺️","builder":"🔨","critic":"🔍","fixer":"🔧","judge":"⚖️"}.get(role,"🤖")
        cprint(f"\n{emoji}  [bold]{role.upper()}[/bold] thinking..." if RICH else f"\n{role.upper()}...", color)
        result = ai_stream_print(agent_prompt, system, f"{emoji}  {role.title()}")
        if RICH:
            colors = {"planner":"blue","builder":"green","critic":"red","fixer":"yellow","judge":"magenta"}
            console.print(Panel(result[:1200]+("..." if len(result)>1200 else ""),
                                title=f"{emoji}  {role.title()}", border_style=colors.get(role,"white")))
        else:
            print(result[:600])
        log.append({"agent": role, "output": result})
        return result

    spec = run_agent("planner", P_AGENTS["planner"], prompt, "blue")
    built = run_agent("builder", P_AGENTS["builder"], f"Request: {desc}\nSpec:\n{spec}", "green")
    try: curr_desc, curr_code, curr_tags = extract(built)
    except: cprint("❌  Builder failed.", "red"); return

    fixes = []
    for rn in range(1, rounds+1):
        crit = run_agent("critic", P_AGENTS["critic"],
                         f"Spec:\n{spec}\n\nCode:\n```python\n{curr_code}\n```", "red")
        if crit.strip().startswith("APPROVED"):
            cprint("✅  Critic approved!", "bold green"); break
        fixed = run_agent("fixer", P_AGENTS["fixer"],
                          f"Spec:\n{spec}\n\nCode:\n```python\n{curr_code}\n```\n\nIssues:\n{crit}", "yellow")
        fm = re.search(r"#\s*FIXES:\s*(.+)", fixed)
        if fm: fixes.append(fm.group(1).strip())
        try: curr_desc, curr_code, curr_tags = extract(fixed)
        except: pass

    verdict = run_agent("judge", P_AGENTS["judge"],
                        f"Request: {desc}\nFinal:\n```python\n{curr_code}\n```\nFixes: {'; '.join(fixes)}", "magenta")

    show_code(curr_code, f"[AI-to-AI] {curr_desc}")

    if RICH:
        ship = "SHIP IT" in verdict
        console.print(Panel(
            f"[white]Critique rounds:[/white] {min(rn,rounds)}\n"
            f"[white]Fixes applied:[/white] {len(fixes)}\n"
            f"[white]Verdict:[/white] {'[green]✅ SHIP IT[/green]' if ship else '[yellow]⚠️ NEEDS WORK[/yellow]'}",
            title="📊  Build Summary", border_style="magenta"))

    if confirm("\n💾  Save?"):
        name = ask("   Name", default=re.sub(r"\s+","_",desc[:30].lower()))
        fp   = save_tool(name, curr_desc, curr_code, curr_tags, {"ai2ai": True, "rounds": rn})
        _syntax_check(fp)
        log_path = FORGE_DIR / f"{name}_agent_log.json"
        log_path.write_text(json.dumps(log, indent=2))
        learn_from_build(name, curr_desc, curr_tags, curr_code, True)
        if "SHIP IT" in verdict:
            _add_insight(f"AI-to-AI build of '{desc[:40]}' shipped after {len(fixes)} fixes")
        if confirm("▶️   Run?"):
            success, _, _ = profile_run(name, fp)
            rating = _ask_rating()
            if rating: _set_rating(name, rating); learn_from_build(name, curr_desc, curr_tags, curr_code, success, rating)

# ══════════════════════════════════════════════════════════════════════════════
# 🧬 GENETIC ALGORITHM MODE
# ══════════════════════════════════════════════════════════════════════════════

def cmd_genetic():
    """Build N variants of a tool, test them, evolve the winner."""
    cprint("\n🧬  GENETIC MODE — Build · Compete · Mutate · Evolve\n", "bold green")
    desc       = ask("🎯  Tool to evolve")
    if not desc: return
    n_variants = min(5, max(2, int(ask("🔬  How many variants? (2-5)", default="3"))))
    generations= min(3, max(1, int(ask("🔁  Generations to evolve (1-3)", default="2"))))

    ctx = memory_context()
    prompt = (f"Context:\n{ctx}\n\nTool: {desc}" if ctx else desc)

    cprint(f"\n🧬  Generation 1 — Building {n_variants} variants...\n", "bold cyan")
    variants = []

    # Build initial population
    for i in range(n_variants):
        cprint(f"   🔬  Variant {i+1}/{n_variants}...", "cyan")
        # Add slight variation to each prompt
        variations = [
            "Focus on simplicity and minimal code.",
            "Focus on maximum robustness and error handling.",
            "Focus on user experience and clear output.",
            "Focus on performance and efficiency.",
            "Add extra features beyond the basic requirements.",
        ]
        varied_prompt = prompt + f"\n\nApproach hint: {variations[i % len(variations)]}"
        try:
            result = ai(varied_prompt, P_BUILD)
            v_desc, code, tags = extract(result)
            variants.append({"id": i+1, "desc": v_desc, "code": code, "tags": tags,
                             "score": 0, "generation": 1})
            cprint(f"      ✅  Variant {i+1} built ({len(code.splitlines())} lines)", "green")
        except Exception as e:
            cprint(f"      ❌  Variant {i+1} failed: {e}", "red")

    if not variants:
        cprint("❌  No variants built.", "red"); return

    # Evaluate each variant
    def evaluate_variant(v):
        """Score a variant using Claude as judge."""
        score_prompt = f"""Rate this Python tool implementation from 0-100.
Original request: {desc}
Code to evaluate:
```python
{v['code']}
```
Reply ONLY with a JSON object: {{"score": <0-100>, "reason": "<one sentence>"}}"""
        try:
            result = ai(score_prompt, "You are a code quality judge. Reply only with JSON.")
            clean  = re.sub(r"```[a-z]*\s*","",result).strip()
            data   = json.loads(clean)
            return data.get("score", 50), data.get("reason", "")
        except:
            return 50, "Could not evaluate"

    for gen in range(1, generations + 1):
        cprint(f"\n⚖️   Generation {gen} — Evaluating {len(variants)} variants...", "bold yellow")
        for v in variants:
            score, reason = evaluate_variant(v)
            v["score"] = score
            v["reason"] = reason
            cprint(f"   Variant {v['id']}: [bold cyan]{score}/100[/bold cyan] — {reason}" if RICH
                   else f"   Variant {v['id']}: {score}/100 — {reason}", "white")

        # Sort by score
        variants.sort(key=lambda x: -x["score"])
        winner = variants[0]

        if gen < generations:
            cprint(f"\n🔬  Mutating winner (score {winner['score']})...", "cyan")
            # Keep top 2, mutate winner into N-2 new variants
            survivors = variants[:2]
            new_variants = list(survivors)

            for i in range(n_variants - 2):
                mutate_prompt = f"Original request: {desc}\n\nCurrent best code:\n```python\n{winner['code']}\n```\n\nMutation #{i+1}"
                try:
                    result  = ai(mutate_prompt, P_MUTATE)
                    m_desc, m_code, m_tags = extract(result)
                    mm = re.search(r"#\s*MUTATION:\s*(.+)", result)
                    mutation_desc = mm.group(1).strip() if mm else "improved"
                    new_variants.append({
                        "id": f"{gen+1}.{i+1}", "desc": m_desc, "code": m_code,
                        "tags": m_tags, "score": 0, "generation": gen+1,
                        "mutation": mutation_desc,
                    })
                    cprint(f"      🧬  Mutant: {mutation_desc}", "green")
                except Exception as e:
                    cprint(f"      ❌  Mutation failed: {e}", "red")
            variants = new_variants

    # Final winner
    final_winner = max(variants, key=lambda x: x["score"])
    cprint(f"\n🏆  EVOLUTION COMPLETE!\n", "bold green")

    if RICH:
        console.print(Panel(
            f"[bold]Winner:[/bold] Variant {final_winner['id']} (Gen {final_winner.get('generation',1)})\n"
            f"[bold]Score:[/bold] [green]{final_winner['score']}/100[/green]\n"
            f"[bold]Reason:[/bold] {final_winner.get('reason','')}\n"
            f"[bold]Description:[/bold] {final_winner['desc']}",
            title="🧬  Genetic Result", border_style="green"))

    show_code(final_winner["code"], f"🏆 Winner — {final_winner['desc']}")

    if confirm("\n💾  Save the evolved winner?"):
        name = ask("   Name", default=re.sub(r"\s+","_",desc[:25].lower())+"_evolved")
        fp   = save_tool(name, final_winner["desc"], final_winner["code"], final_winner["tags"],
                         {"genetic": True, "score": final_winner["score"], "generations": generations})
        _syntax_check(fp)
        learn_from_build(name, final_winner["desc"], final_winner["tags"],
                         final_winner["code"], True, min(5, round(final_winner["score"]/20)))
        _add_insight(f"Genetic evolution of '{desc[:35]}' scored {final_winner['score']}/100 after {generations} generations")
        if confirm("▶️   Run?"):
            profile_run(name, fp)
            rating = _ask_rating()
            if rating: _set_rating(name, rating)

# ══════════════════════════════════════════════════════════════════════════════
# 🔁 SELF-HEALING
# ══════════════════════════════════════════════════════════════════════════════

def cmd_self_heal():
    name, fp = pick_tool("Self-heal which tool?")
    if fp: cmd_self_heal_named(name, fp)

def cmd_self_heal_named(name, fp):
    """Run a tool, catch errors, auto-fix, repeat until healthy."""
    cprint(f"\n🔁  SELF-HEAL MODE for [bold]{name}[/bold]", "bold cyan")
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        cprint(f"\n   Attempt {attempt}/{max_attempts} — Running...", "cyan")
        result = subprocess.run(
            [sys.executable, str(fp)],
            capture_output=True, text=True, timeout=30, input="\n\n\n\n\n"
        )

        if result.returncode == 0:
            cprint(f"✅  Tool is healthy! (passed on attempt {attempt})", "bold green")
            reg = load_reg()
            if name in reg: reg[name]["heal_count"] = reg[name].get("heal_count", 0); save_reg(reg)
            return True

        error_output = (result.stderr + result.stdout)[-2000:]
        cprint(f"\n   ❌  Error detected:\n{error_output[:400]}", "red")
        cprint(f"\n   🔧  Sending to FORGE healer (attempt {attempt})...", "yellow")

        current_code = fp.read_text()
        heal_prompt  = (
            f"This tool crashed with this error:\n\n{error_output}\n\n"
            f"Current code:\n```python\n{current_code}\n```\n\n"
            f"Fix it completely."
        )
        try:
            result_ai = ai(heal_prompt, P_HEAL)
            new_desc, new_code, new_tags = extract(result_ai)
            fm = re.search(r"#\s*FIX:\s*(.+)", result_ai)
            fix_desc = fm.group(1).strip() if fm else "patched"
            cprint(f"   🩹  Fix: {fix_desc}", "green")

            # Backup and replace
            bak = FORGE_DIR / f"{fp.stem}_prehealed.py"
            shutil.copy(fp, bak)
            fp.write_text(fp.read_text().split("\n\n", 1)[0] + f"\n# HEALED: {fix_desc}\n\n" + new_code + "\n")

            # Update registry
            reg = load_reg()
            if name in reg:
                reg[name]["heal_count"] = reg[name].get("heal_count", 0) + 1
                save_reg(reg)
            _add_insight(f"Self-healed '{name}': {fix_desc}")

        except Exception as e:
            cprint(f"   ❌  Healer failed: {e}", "red")

    cprint(f"\n⚠️   Could not fully heal '{name}' after {max_attempts} attempts.", "yellow")
    cprint("   Tip: Try 'improve' or rebuild with AI-to-AI mode.", "dim")
    return False

# ══════════════════════════════════════════════════════════════════════════════
# 🎯 GOAL MODE — Autonomous execution
# ══════════════════════════════════════════════════════════════════════════════

def cmd_goal():
    """Fully autonomous: give FORGE a goal, it does everything itself."""
    cprint("\n🎯  GOAL MODE — Autonomous execution\n", "bold magenta")
    cprint("[dim]FORGE will plan, build missing tools, and execute everything to reach your goal.[/dim]\n")
    goal = ask("🎯  Your goal")
    if not goal: return

    reg = load_reg()
    reg_summary = "\n".join(f"- {n}: {v['description']}" for n, v in reg.items()) or "none"

    # Step 1: Plan
    cprint("\n🗺️   Planning autonomous execution...", "yellow")
    plan_prompt = f"Goal: {goal}\n\nAvailable tools:\n{reg_summary}"
    plan_raw    = ai(plan_prompt, P_GOAL_EXECUTOR)

    try:
        clean = re.sub(r"```[a-z]*\s*","",plan_raw).strip()
        plan  = json.loads(clean)
    except:
        m = re.search(r"\{.*\}", plan_raw, re.DOTALL)
        if not m: cprint("❌  Could not parse plan.", "red"); return
        plan = json.loads(m.group())

    steps   = plan.get("plan", [])
    summary = plan.get("summary", "Execute the goal")

    if RICH:
        table = Table(title="🎯  Autonomous Plan", border_style="magenta", show_lines=True)
        table.add_column("#",      style="dim",       width=4)
        table.add_column("Action", style="bold cyan", width=8)
        table.add_column("Tool",   style="white",     width=18)
        table.add_column("Reason", style="dim",       width=35)
        for i, s in enumerate(steps, 1):
            table.add_row(str(i), s["action"].upper(), s["name"], s.get("reason",""))
        console.print(table)
        console.print(f"[dim]Summary: {summary}[/dim]")
    else:
        for i, s in enumerate(steps, 1):
            print(f"  {i}. [{s['action'].upper()}] {s['name']} — {s.get('reason','')}")

    if not confirm(f"\n🚀  Execute this plan autonomously?"): return

    results = []
    for i, step in enumerate(steps, 1):
        action = step.get("action","run")
        name   = step.get("name","")
        cprint(f"\n[{i}/{len(steps)}] {action.upper()}: {name}", "bold cyan")

        if action == "build":
            try:
                desc_step = step.get("description", f"Tool: {name}")
                result_ai = ai(f"Context:\n{memory_context()}\n\nBuild: {desc_step}", P_BUILD)
                d_out, code, tags = extract(result_ai)
                fp = save_tool(name, d_out, code, tags)
                _syntax_check(fp)
                learn_from_build(name, d_out, tags, code, True)
                results.append({"step": i, "name": name, "action": "built", "success": True})
                cprint(f"   ✅  Built!", "green")
            except Exception as e:
                cprint(f"   ❌  Build failed: {e}", "red")
                results.append({"step": i, "name": name, "action": "built", "success": False, "error": str(e)})

        elif action == "run":
            reg2 = load_reg()
            if name not in reg2:
                cprint(f"   ⚠️   Tool '{name}' not in registry, skipping.", "yellow")
                continue
            fp = Path(reg2[name]["file"])
            success, elapsed, _ = profile_run(name, fp)
            results.append({"step": i, "name": name, "action": "ran", "success": success, "time": elapsed})

            if not success and confirm(f"   🔁  Auto-heal '{name}'?"):
                cmd_self_heal_named(name, fp)

    # Report
    succeeded = sum(1 for r in results if r["success"])
    if RICH:
        console.print(Panel(
            f"[bold]Goal:[/bold] {goal}\n"
            f"[bold]Steps completed:[/bold] {succeeded}/{len(results)}\n"
            f"[bold]Status:[/bold] {'[green]✅ Success[/green]' if succeeded==len(results) else '[yellow]⚠️ Partial[/yellow]'}",
            title="🎯  Goal Report", border_style="green" if succeeded==len(results) else "yellow"))
    else:
        print(f"\n🎯 Goal: {succeeded}/{len(results)} steps succeeded")

    _add_insight(f"Goal mode executed '{goal[:40]}' with {succeeded}/{len(results)} steps")

# ══════════════════════════════════════════════════════════════════════════════
# 📡 ECOSYSTEM — Tools calling tools
# ══════════════════════════════════════════════════════════════════════════════

def cmd_ecosystem():
    """Build a tool that orchestrates other tools in the registry."""
    cprint("\n📡  ECOSYSTEM MODE — Build a tool that calls other FORGE tools\n", "bold cyan")
    reg = load_reg()
    if len(reg) < 2: cprint("Need at least 2 tools first!", "yellow"); return

    show_table()
    desc = ask("\n📡  What should this ecosystem tool orchestrate?")
    if not desc: return

    reg_summary = "\n".join(f"- {n} (file: {v['file']}): {v['description']}" for n,v in reg.items())
    prompt = P_ECOSYSTEM.replace("{registry}", reg_summary) + f"\n\nUser's goal: {desc}"

    result = ai_stream_print(prompt, P_BUILD, "📡  Building ecosystem tool")
    d_out, code, tags = extract(result)
    show_code(code, f"📡  {d_out}")

    if confirm("\n💾  Save?"):
        name = ask("   Name", default="ecosystem_"+re.sub(r"\s+","_",desc[:20].lower()))
        fp   = save_tool(name, d_out, code, tags + ["ecosystem"], {"ecosystem": True})
        _syntax_check(fp)
        if confirm("▶️   Run?"):
            profile_run(name, fp)

# ══════════════════════════════════════════════════════════════════════════════
# EXISTING COMMANDS (kept + upgraded)
# ══════════════════════════════════════════════════════════════════════════════

def cmd_auto():
    cprint("\n🚀  AUTO-MODE\n", "bold magenta")
    goal = ask("🎯  Your goal")
    if not goal: return
    plan_raw = ai_stream_print(goal, P_PLANNER, "🗺️   Planning")
    try:
        plan = json.loads(re.sub(r"```[a-z]*\s*","",plan_raw).strip())
    except:
        m = re.search(r"\[.*\]", plan_raw, re.DOTALL)
        if not m: cprint("❌  Couldn't parse plan.","red"); return
        plan = json.loads(m.group())

    if RICH:
        t = Table(title="📋  Plan",border_style="magenta",show_lines=True)
        t.add_column("#",style="dim",width=4); t.add_column("Tool",style="bold cyan"); t.add_column("Does",style="white")
        for i,s in enumerate(plan,1): t.add_row(str(i),s["name"],s["description"])
        console.print(t)
    else:
        for i,s in enumerate(plan,1): print(f"  {i}. {s['name']}: {s['description']}")

    if not confirm(f"\n🚀  Build all {len(plan)} tools?"): return
    built = []
    for i, step in enumerate(plan,1):
        cprint(f"\n[{i}/{len(plan)}] Building: [bold]{step['name']}[/bold]","cyan")
        try:
            res = ai(step["description"], P_BUILD)
            d,c,t = extract(res)
            fp = save_tool(step["name"],d,c,t)
            _syntax_check(fp)
            learn_from_build(step["name"],d,t,c,True)
            built.append((step["name"],fp))
            cprint("   ✅  Done!","green")
        except Exception as e:
            cprint(f"   ❌  {e}","red")
    cprint(f"\n🎉  Built {len(built)}/{len(plan)} tools.", "bold green")
    if len(built)>=2 and confirm("🔗  Chain into pipeline?"):
        _chain_from_list(built, goal)

def _cmd_improve_named(name, what="make it better and more robust"):
    reg = load_reg()
    if name not in reg: cprint("Tool not found.","red"); return
    fp  = Path(reg[name]["file"])
    res = ai_stream_print(f"Tool:\n```python\n{fp.read_text()}\n```\n\nImprovement: {what}", P_IMPROVE, "🔧  Improving")
    d,c,t = extract(res)
    show_code(c,d)
    if confirm("💾  Save?"):
        save_tool(name, d, c, t)

def cmd_improve():
    name, fp = pick_tool("Improve which?")
    if not fp: return
    what = ask("✏️   What to improve?", default="make it better and more robust")
    _cmd_improve_named(name, what)

def cmd_remix():
    cprint("\n🎛️  REMIX\n","bold magenta")
    n1,p1 = pick_tool("First tool")
    if not p1: return
    n2,p2 = pick_tool("Second tool")
    if not p2: return
    goal  = ask("🎯  Goal", default="combine the best of both")
    res   = ai_stream_print(
        f"Tool 1 ({n1}):\n```python\n{p1.read_text()}\n```\n\nTool 2 ({n2}):\n```python\n{p2.read_text()}\n```\n\nGoal: {goal}",
        P_REMIX, "🎛️  Remixing")
    d,c,t = extract(res)
    show_code(c,d)
    if confirm("💾  Save?"):
        save_tool(f"{n1}_x_{n2}",d,c,t)

def cmd_test():
    name, fp = pick_tool("Test which?")
    if not fp: return
    res = ai_stream_print(f"Test this:\n```python\n{fp.read_text()}\n```", P_TEST, "🧪  Generating tests")
    cm  = re.search(r"```python\s*(.*?)```", res, re.DOTALL)
    if not cm: cprint("❌  No test code.","red"); return
    code = f"import sys\nsys.path.insert(0,r'{FORGE_DIR.resolve()}')\n" + cm.group(1).strip()
    show_code(code, f"Tests for {name}")
    if not confirm("▶️   Run?"): return
    tf = FORGE_DIR/f"test_{re.sub(r'[^\\w]','_',name)}.py"
    tf.write_text(code)
    result = subprocess.run([sys.executable,"-m","unittest",str(tf),"-v"],capture_output=True,text=True)
    print(result.stdout+result.stderr)
    passed = result.returncode==0
    cprint("✅  All passed!" if passed else "❌  Some failed.","green" if passed else "red")
    reg=load_reg()
    if name in reg: reg[name]["test_status"]="passed" if passed else "failed"; save_reg(reg)

def _chain_from_list(tool_list, goal=""):
    info  = "\n".join(f"- {n}: {load_reg().get(n,{}).get('description','')}" for n,_ in tool_list)
    codes = "\n\n".join(f"# {n}\n```python\n{Path(fp).read_text()}\n```" for n,fp in tool_list)
    res   = ai_stream_print(f"Goal: {goal}\nTools:\n{info}\n\nCode:\n{codes}", P_CHAIN, "🔗  Chaining")
    d,c,t = extract(res)
    show_code(c,d)
    if confirm("💾  Save pipeline?"):
        names = "_".join(n for n,_ in tool_list[:3])
        fp    = save_tool(f"pipeline_{names}",d,c,t)
        if confirm("▶️   Run?"): profile_run(f"pipeline_{names}", fp)

def cmd_chain():
    reg = load_reg()
    if len(reg)<2: cprint("Need 2+ tools.","yellow"); return
    chosen = []
    while True:
        show_table({k:v for k,v in reg.items() if k not in [n for n,_ in chosen]})
        cprint(f"Chosen: {[n for n,_ in chosen] or 'none'}","cyan")
        raw = input("Add # (Enter to finish): ").strip()
        if not raw: break
        try:
            n,info = list(reg.items())[int(raw)-1]
            chosen.append((n,Path(info["file"]))); cprint(f"   ➕ {n}","green")
        except: cprint("Invalid.","red")
    if len(chosen)<2: cprint("Need 2+ tools.","yellow"); return
    goal = ask("🎯  Pipeline goal", default="process data end to end")
    _chain_from_list(chosen, goal)

def cmd_explain():
    _,fp = pick_tool("Explain which?")
    if not fp: return
    exp = ai_stream_print(f"Explain:\n```python\n{fp.read_text()}\n```", P_EXPLAIN, "📖  Explaining")
    if RICH: console.print(Panel(Markdown(exp), title="📖  Explanation", border_style="blue"))
    else: print(f"\n📖\n{exp}")

def cmd_web():
    cprint("\n🌐  WEB TOOL BUILDER\n","bold cyan")
    desc = ask("🌐  Describe the web tool")
    if not desc: return
    try:
        sq = f"https://html.duckduckgo.com/html/?q={quote_plus(desc+' python api url example')}"
        html = _web_fetch(sq,12000)
        urls = list(set(re.findall(r"https?://(?!.*duckduck)[^\s\"'<>]{15,80}",html)))[:4]
        wctx = "\nRelevant URLs:\n"+"\n".join(f"- {u}" for u in urls) if urls else ""
    except: wctx = ""
    ctx = memory_context()
    prompt = (f"Context:\n{ctx}\n\n" if ctx else "") + desc + wctx
    res = ai_stream_print(prompt, P_WEB, "🌐  Building web tool")
    d,c,t = extract(res)
    show_code(c,d)
    if confirm("\n💾  Save?"):
        name = ask("   Name", default=re.sub(r"\s+","_",desc[:30].lower()))
        fp   = save_tool(name,d,c,t+["web","live-data"])
        _syntax_check(fp)
        if confirm("▶️   Run?"): profile_run(name,fp)

def cmd_run():
    name,fp = pick_tool("Run which?")
    if not fp: return
    success,_,_ = profile_run(name,fp)
    if not success and confirm("🔁  Self-heal?"):
        cmd_self_heal_named(name,fp)
    rating = _ask_rating()
    if rating and name: _set_rating(name,rating)

def cmd_search():
    q   = ask("🔍  Search").lower()
    reg = load_reg()
    hits = {k:v for k,v in reg.items()
            if q in k.lower() or q in v["description"].lower()
            or any(q in t.lower() for t in v.get("tags",[]))}
    if hits: show_table(hits)
    else: cprint(f"  No matches for '{q}'","yellow")

def cmd_export():
    name,fp = pick_tool("Export which?")
    if not fp: return
    zp = FORGE_DIR/f"{name}_export.zip"
    with zipfile.ZipFile(zp,"w") as zf:
        zf.write(fp,fp.name)
        zf.writestr("README.md",f"# {name}\n\nFORGE Tool\n\nRun:\n    python {fp.name}\n")
    cprint(f"📦  Exported → {zp}","bold cyan")

def cmd_delete():
    name,fp = pick_tool("Delete which?")
    if not fp: return
    if confirm(f"Delete '{name}'?"):
        fp.unlink(missing_ok=True)
        reg=load_reg(); reg.pop(name,None); save_reg(reg)
        cprint(f"🗑️   Deleted.","red")

def cmd_rate():
    name,_ = pick_tool("Rate which?")
    if name:
        r=_ask_rating()
        if r: _set_rating(name,r)

def cmd_memory_view():
    m = load_memory(); p = load_patterns()
    if RICH:
        history = "\n".join(
            f"  {'✅' if e['success'] else '❌'} [cyan]{e['tool']}[/cyan] — {e['description'][:45]}"
            f"{'  '+'⭐'*e['rating'] if e.get('rating') else ''}"
            for e in reversed(m.get("tool_history",[])[-8:])
        ) or "  (none yet)"

        patterns_txt = ""
        if p.get("tag_approaches"):
            patterns_txt = "\n  Top learned tags: " + ", ".join(
                f"{t} (avg ⭐{v['avg_rating']:.1f})"
                for t,v in sorted(p["tag_approaches"].items(), key=lambda x:-x[1]["avg_rating"])[:5]
            )

        insights = "\n".join(f"  💡 {i}" for i in m.get("insights",[])[-5:]) or "  (none yet)"

        console.print(Panel(
            f"[bold]📜 History (last 8):[/bold]\n{history}\n\n"
            f"[bold]🧠 Pattern Library:[/bold]{patterns_txt or ' (building...)'}\n\n"
            f"[bold]💡 Insights:[/bold]\n{insights}\n\n"
            f"[bold]📊 Total builds:[/bold] {len(m.get('tool_history',[]))}  "
            f"[bold]Sessions:[/bold] {m.get('sessions',0)}",
            title="🧠  FORGE Learning Engine", border_style="magenta"))
    else:
        for e in reversed(m.get("tool_history",[])[-5:]):
            print(f"  {'✓' if e['success'] else '✗'} {e['tool']}: {e['description'][:50]}")

    print()
    choice = ask("Options: [set-style] [add-insight] [clear] [back]", default="back")
    if choice == "set-style":
        style = ask("Describe your coding style")
        m["user_style"] = style; save_memory(m); cprint("✅  Saved!","green")
    elif choice == "add-insight":
        _add_insight(ask("What should FORGE remember?"))
        cprint("✅  Saved!","green")
    elif choice == "clear":
        if confirm("⚠️  Clear ALL memory?"):
            MEMORY_F.unlink(missing_ok=True); PATTERNS_F.unlink(missing_ok=True)
            cprint("🗑️   Cleared.","red")

def cmd_stats():
    reg=load_reg(); m=load_memory(); p=load_patterns()
    if not reg: cprint("No tools yet!","yellow"); return
    total=len(reg); total_runs=sum(v.get("runs",0) for v in reg.values())
    rated=[v["rating"] for v in reg.values() if v.get("rating")]
    avg_r=sum(rated)/len(rated) if rated else 0
    tested=sum(1 for v in reg.values() if v.get("test_status")=="passed")
    healed=sum(v.get("heal_count",0) for v in reg.values())
    top=max(reg.items(),key=lambda x:x[1].get("runs",0))
    tc={}
    for v in reg.values():
        for t in v.get("tags",[]): tc[t]=tc.get(t,0)+1
    top_tags=sorted(tc.items(),key=lambda x:-x[1])[:6]
    builds=len(m.get("tool_history",[]))
    patterns=len(p.get("tag_approaches",{}))

    if RICH:
        console.print(Panel.fit(
            f"[bold cyan]⚒️  FORGE Dashboard[/bold cyan]\n\n"
            f"  [white]Tools forged:[/white]     [bold]{total}[/bold]  [dim](lifetime: {builds})[/dim]\n"
            f"  [white]Total runs:[/white]       [bold]{total_runs}[/bold]\n"
            f"  [white]Tests passed:[/white]     [bold green]{tested}[/bold green]\n"
            f"  [white]Self-heals:[/white]       [bold cyan]{healed}[/bold cyan]\n"
            f"  [white]Avg rating:[/white]       [bold yellow]{'⭐ '+f'{avg_r:.1f}' if rated else '─'}[/bold yellow]\n"
            f"  [white]Most-run:[/white]         [magenta]{top[0]}[/magenta] ({top[1].get('runs',0)} runs)\n"
            f"  [white]Learned patterns:[/white] [bold]{patterns}[/bold]\n"
            f"  [white]Top tags:[/white]         [cyan]{', '.join(t for t,_ in top_tags)}[/cyan]",
            border_style="cyan", title="Dashboard"
        ))
    else:
        print(f"\n⚒️  {total} tools | {total_runs} runs | ⭐{avg_r:.1f} avg | {healed} heals | {patterns} patterns")

def cmd_agentlog():
    logs = list(FORGE_DIR.glob("*_agent_log.json"))
    if not logs: cprint("No agent logs yet.","yellow"); return
    for i,l in enumerate(logs,1): print(f"  {i}. {l.name}")
    try:
        log = json.loads(logs[int(input("View # (0=cancel): "))-1].read_text())
    except: return
    colors = {"planner":"blue","builder":"green","critic":"red","fixer":"yellow","judge":"magenta"}
    for entry in log:
        a = entry["agent"]; o = entry["output"]
        color = next((v for k,v in colors.items() if k in a.lower()),"white")
        if RICH: console.print(Panel(o[:1000]+("..." if len(o)>1000 else ""),title=f"🤖  {a}",border_style=color))
        else: print(f"\n── {a} ──\n{o[:500]}")

# ── Helpers ───────────────────────────────────────────────────────────────────
def _syntax_check(fp):
    r = subprocess.run([sys.executable,"-m","py_compile",str(fp)],capture_output=True,text=True)
    if r.returncode==0: cprint("✅  Syntax OK","green")
    else: cprint(f"⚠️  Syntax error:\n{r.stderr}","red")

def _web_fetch(url, max_chars=6000):
    req = UReq(url, headers={"User-Agent":"Mozilla/5.0"})
    with urlopen(req,timeout=10) as r: raw=r.read().decode("utf-8","ignore")
    raw=re.sub(r"<script[^>]*>.*?</script>","",raw,flags=re.DOTALL)
    raw=re.sub(r"<style[^>]*>.*?</style>","",raw,flags=re.DOTALL)
    raw=re.sub(r"<[^>]+>"," ",raw)
    return re.sub(r"\s+"," ",raw).strip()[:max_chars]

def _add_insight(insight):
    m=load_memory(); m["insights"].append(insight); m["insights"]=m["insights"][-30:]; save_memory(m)

def show_help():
    cmds = [
        ("── FORGE ──────────────────────────────", ""),
        ("<description>",  "Build a tool (memory-aware)"),
        ("ai2ai",          "🤖 Multi-agent: Planner→Builder→Critic→Fixer→Judge"),
        ("genetic",        "🧬 Evolve a tool through generations"),
        ("auto",           "🚀 Give a goal, FORGE builds all tools"),
        ("goal",           "🎯 Fully autonomous goal execution"),
        ("── MODIFY ─────────────────────────────", ""),
        ("improve",        "🔧 Improve a saved tool"),
        ("remix",          "🎛️  Combine two tools into one"),
        ("chain",          "🔗 Build a pipeline from multiple tools"),
        ("heal",           "🔁 Self-heal a broken tool automatically"),
        ("ecosystem",      "📡 Build a tool that calls other FORGE tools"),
        ("── QUALITY ────────────────────────────", ""),
        ("test",           "🧪 Auto-generate & run tests"),
        ("profiler",       "📊 Performance profiler & health dashboard"),
        ("── WEB & LIBRARY ──────────────────────", ""),
        ("web",            "🌐 Build a tool with live web data"),
        ("list",           "📚 Show all tools"),
        ("run",            "▶️  Run a tool (profiled + auto-heal on fail)"),
        ("search",         "🔍 Search by keyword or tag"),
        ("explain",        "📖 Get plain-English explanation"),
        ("rate",           "⭐ Rate a tool"),
        ("export",         "📦 Export as .zip"),
        ("delete",         "🗑️  Remove a tool"),
        ("── INTELLIGENCE ───────────────────────", ""),
        ("memory",         "🧠 View/manage learning engine & patterns"),
        ("stats",          "📊 FORGE dashboard"),
        ("agentlog",       "📝 View AI-to-AI conversation logs"),
        ("help",           "Show this help"),
        ("quit",           "Exit FORGE"),
    ]
    if RICH:
        t = Table(border_style="dim",show_header=False,box=None,padding=(0,1))
        t.add_column("cmd",style="bold cyan",width=20)
        t.add_column("desc",style="white")
        for c,d in cmds:
            if c.startswith("──"):
                t.add_row(f"[dim]{c}[/dim]","")
            else:
                t.add_row(c,d)
        console.print(Panel(t, title="[bold]⚒️  FORGE Commands", border_style="cyan"))
    else:
        for c,d in cmds:
            if d: print(f"  {c:<22} {d}")
            else: print(f"\n  {c}")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    m = load_memory()
    m["sessions"] = m.get("sessions", 0) + 1
    save_memory(m)

    if RICH:
        console.print(Panel.fit(
            "[bold cyan]███████╗ ██████╗ ██████╗  ██████╗ ███████╗[/bold cyan]\n"
            "[bold cyan]██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝[/bold cyan]\n"
            "[bold cyan]█████╗  ██║   ██║██████╔╝██║  ███╗█████╗  [/bold cyan]\n"
            "[bold cyan]██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  [/bold cyan]\n"
            "[bold cyan]██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗[/bold cyan]\n"
            "[bold cyan]╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝[/bold cyan]\n\n"
            f"[dim]Framework for Orchestrated Reasoning & Generation of Engines[/dim]\n"
            f"[dim]🧠 Memory active · {len(load_reg())} tools · Session #{m['sessions']}[/dim]",
            border_style="cyan"
        ))
        if m["sessions"] > 1 and m.get("tool_history"):
            last = m["tool_history"][-1]["tool"]
            console.print(f"[dim]👋 Welcome back! Last forged: [cyan]{last}[/cyan][/dim]\n")
        console.print("[dim]Type a description to build, or 'help' for all commands.[/dim]\n")
    else:
        print("⚒️  FORGE — Framework for Orchestrated Reasoning & Generation of Engines")
        print(f"   {len(load_reg())} tools · Session #{m['sessions']}\n")

    COMMANDS = {
        "list":      show_table,
        "run":       cmd_run,
        "improve":   cmd_improve,
        "remix":     cmd_remix,
        "explain":   cmd_explain,
        "export":    cmd_export,
        "delete":    cmd_delete,
        "help":      show_help,
        "search":    cmd_search,
        "test":      cmd_test,
        "rate":      cmd_rate,
        "stats":     cmd_stats,
        "auto":      cmd_auto,
        "chain":     cmd_chain,
        "memory":    cmd_memory_view,
        "mem":       cmd_memory_view,
        "web":       cmd_web,
        "ai2ai":     cmd_ai2ai,
        "agents":    cmd_ai2ai,
        "agentlog":  cmd_agentlog,
        "genetic":   cmd_genetic,
        "evolve":    cmd_genetic,
        "heal":      cmd_self_heal,
        "self-heal": cmd_self_heal,
        "goal":      cmd_goal,
        "profiler":  cmd_profiler,
        "profile":   cmd_profiler,
        "ecosystem": cmd_ecosystem,
        "eco":       cmd_ecosystem,
    }

    while True:
        try:
            user_input = (Prompt.ask("\n[bold cyan]FORGE >[/bold cyan]") if RICH else input("\nFORGE > ")).strip()
        except (KeyboardInterrupt, EOFError):
            cprint("\n⚒️   FORGE signing off. Keep building. 🔥", "bold cyan")
            break

        if not user_input: continue
        if user_input.lower() in ("quit","exit","q"):
            cprint("⚒️   FORGE signing off. Keep building. 🔥", "bold cyan"); break
        elif user_input.lower() in COMMANDS:
            COMMANDS[user_input.lower()]()
        else:
            try:
                cmd_build(user_input)
            except Exception as e:
                cprint(f"\n❌  {e}", "bold red")
        print()

if __name__ == "__main__":
    main()
