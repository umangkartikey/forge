#!/usr/bin/env python3
"""
███████╗ ██████╗ ██████╗  ██████╗ ███████╗    ██╗     ███████╗ █████╗ ██████╗ ███╗   ██╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝    ██║     ██╔════╝██╔══██╗██╔══██╗████╗  ██║
█████╗  ██║   ██║██████╔╝██║  ███╗█████╗      ██║     █████╗  ███████║██████╔╝██╔██╗ ██║
██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝      ██║     ██╔══╝  ██╔══██║██╔══██╗██║╚██╗██║
██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗    ███████╗███████╗██║  ██║██║  ██║██║ ╚████║
╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝    ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝

FORGE LEARN — Self-Improving Learning Engine

The brain that makes FORGE smarter every single run.

How it works:
  Every run → captured in SQLite brain
  Findings rated by AI (signal vs noise)
  Patterns extracted automatically
  System prompts evolved via genetic algorithm
  Next run starts smarter

Usage:
  python forge_learn.py              # interactive mode
  python forge_learn.py --record     # record a run's results
  python forge_learn.py --evolve     # evolve prompts now
  python forge_learn.py --status     # show brain stats
"""

import sqlite3, json, re, sys, os, time, hashlib, shutil
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# ── Try rich ──────────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.syntax import Syntax
    from rich.prompt import Prompt, Confirm
    from rich import box as rbox
    RICH = True
    console = Console()
    def rprint(x, **kw): console.print(x, **kw)
    def ask(msg, default=""): return Prompt.ask(msg, default=default)
    def confirm(msg): return Confirm.ask(msg)
except ImportError:
    RICH = False
    def rprint(x, **kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))
    def ask(msg, default=""): return input(f"{msg} [{default}]: ").strip() or default
    def confirm(msg): return input(f"{msg} (y/n): ").lower() == "y"

# ── Try anthropic ─────────────────────────────────────────────────────────────
try:
    import anthropic
    AI_CLIENT    = anthropic.Anthropic()
    AI_AVAILABLE = True
except ImportError:
    AI_CLIENT    = None
    AI_AVAILABLE = False

MODEL = "claude-sonnet-4-6"

# ── Paths ─────────────────────────────────────────────────────────────────────
LEARN_DIR      = Path("forge_learn")
BRAIN_DB       = LEARN_DIR / "brain.db"
PATTERNS_F     = LEARN_DIR / "patterns.json"
EVOLVED_DIR    = LEARN_DIR / "evolved_prompts"
SNAPSHOTS_DIR  = LEARN_DIR / "snapshots"

for d in [LEARN_DIR, EVOLVED_DIR, SNAPSHOTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 SQLITE BRAIN
# ══════════════════════════════════════════════════════════════════════════════

def get_db():
    """Get SQLite connection with all tables initialized."""
    conn = sqlite3.connect(str(BRAIN_DB))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      TEXT UNIQUE,
            target      TEXT,
            goal        TEXT,
            mode        TEXT,       -- swarm|autopilot|meta|build
            started_at  TEXT,
            finished_at TEXT,
            worker_count INTEGER DEFAULT 1,
            finding_count INTEGER DEFAULT 0,
            modules_built INTEGER DEFAULT 0,
            score       REAL DEFAULT 0,    -- AI-rated overall run quality 0-10
            notes       TEXT
        );

        CREATE TABLE IF NOT EXISTS findings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      TEXT,
            worker_id   TEXT,
            type        TEXT,       -- open_port|ssl_issue|tech_stack|dir_found|etc
            severity    TEXT,       -- critical|high|medium|low|info
            target      TEXT,
            data        TEXT,       -- JSON
            signal_score REAL,      -- AI-rated: 0-10 (how useful/actionable)
            noise_score  REAL,      -- AI-rated: 0-10 (how noisy/irrelevant)
            confirmed   INTEGER DEFAULT 0,
            ts          TEXT
        );

        CREATE TABLE IF NOT EXISTS modules (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT,
            version      INTEGER DEFAULT 1,
            run_id       TEXT,
            built_by     TEXT,
            description  TEXT,
            code_hash    TEXT,
            success_rate REAL DEFAULT 0,
            avg_runtime  REAL DEFAULT 0,
            times_used   INTEGER DEFAULT 0,
            times_failed INTEGER DEFAULT 0,
            rating       REAL DEFAULT 0,   -- 0-10
            ts           TEXT
        );

        CREATE TABLE IF NOT EXISTS patterns (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern     TEXT,
            category    TEXT,       -- target_type|finding_type|timing|approach
            frequency   INTEGER DEFAULT 1,
            confidence  REAL DEFAULT 0.5,
            first_seen  TEXT,
            last_seen   TEXT,
            runs_seen   TEXT,       -- JSON list of run_ids
            actionable  INTEGER DEFAULT 0,  -- 1 = use this in planning
            action      TEXT        -- what to do when this pattern is seen
        );

        CREATE TABLE IF NOT EXISTS prompts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT,       -- swarm_planner|worker_ai|autopilot|etc
            version     INTEGER DEFAULT 1,
            content     TEXT,
            performance REAL DEFAULT 0,  -- avg score of runs using this prompt
            uses        INTEGER DEFAULT 0,
            wins        INTEGER DEFAULT 0,
            created_at  TEXT,
            parent_id   INTEGER,    -- NULL = original, INT = evolved from this
            mutation    TEXT        -- what changed vs parent
        );

        CREATE TABLE IF NOT EXISTS insights (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            insight     TEXT,
            source      TEXT,       -- run_id or 'manual'
            confidence  REAL DEFAULT 0.5,
            used_count  INTEGER DEFAULT 0,
            helpful     INTEGER DEFAULT 0,
            harmful     INTEGER DEFAULT 0,
            ts          TEXT
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 📥 CAPTURE — Record run results into brain
# ══════════════════════════════════════════════════════════════════════════════

def capture_run(target, goal, mode, findings=None, modules_built=None,
                worker_count=1, notes=""):
    """Record a complete run into the brain."""
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(target.encode()).hexdigest()[:6]}"
    conn   = get_db()
    c      = conn.cursor()

    c.execute("""
        INSERT INTO runs (run_id,target,goal,mode,started_at,worker_count,
                          finding_count,modules_built,notes)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (run_id, target, goal, mode, datetime.now().isoformat(),
          worker_count, len(findings or []), len(modules_built or []), notes))

    # Insert findings
    for f in (findings or []):
        c.execute("""
            INSERT INTO findings (run_id,worker_id,type,severity,target,data,ts)
            VALUES (?,?,?,?,?,?,?)
        """, (run_id, f.get("from","unknown"), f.get("type","unknown"),
              f.get("severity","info"), target,
              json.dumps(f.get("data",""), default=str),
              f.get("ts", datetime.now().isoformat())))

    # Insert modules
    for m in (modules_built or []):
        name = m.get("module", m.get("name","unknown"))
        code = m.get("code","")
        c.execute("""
            INSERT INTO modules (name,run_id,built_by,description,code_hash,ts)
            VALUES (?,?,?,?,?,?)
        """, (name, run_id, m.get("built_by","unknown"),
              m.get("description",""),
              hashlib.md5(code.encode()).hexdigest() if code else "",
              datetime.now().isoformat()))

    conn.commit()
    conn.close()
    return run_id

def capture_from_swarm_hive(hive_root=None):
    """Auto-import findings from a swarm run's hive mind."""
    if hive_root is None:
        hive_root = Path("forge_swarm") / "hive"

    memory_f = hive_root / "memory.json"
    mods_f   = hive_root / "modules.json"

    if not memory_f.exists():
        rprint("[yellow]No hive memory found. Run a swarm first.[/yellow]")
        return None

    memory  = json.loads(memory_f.read_text())
    mods    = json.loads(mods_f.read_text()) if mods_f.exists() else {}

    target   = memory.get("target","unknown")
    goal     = memory.get("goal","unknown")
    findings = memory.get("findings",[])

    mod_list = [{"name":k,"description":v.get("description",""),
                 "built_by":v.get("built_by","")} for k,v in mods.items()]

    run_id = capture_run(target, goal, "swarm", findings, mod_list,
                         notes=f"Auto-imported from hive at {datetime.now()}")
    rprint(f"[green]✅  Captured run {run_id}: {len(findings)} findings, {len(mod_list)} modules[/green]")
    return run_id

# ══════════════════════════════════════════════════════════════════════════════
# ⭐ RATE — AI scores findings for signal vs noise
# ══════════════════════════════════════════════════════════════════════════════

RATING_PROMPT = """You are a security triage expert. Rate this finding.

Finding type: {type}
Severity: {severity}
Data: {data}

Rate on two dimensions (0-10):
- signal_score: How actionable/important is this? (10 = critical vuln, 0 = useless noise)
- noise_score: How noisy/irrelevant? (10 = pure noise, 0 = very clean signal)

Also extract:
- key_fact: one sentence summary of what matters
- action: what a pentester should do with this finding

Reply ONLY with JSON:
{{"signal_score": 7.5, "noise_score": 2.0, "key_fact": "...", "action": "..."}}"""

RUN_RATING_PROMPT = """Rate this security assessment run overall.

Target: {target}
Mode: {mode}
Findings: {finding_count} total
Severity breakdown: {severity_breakdown}
Modules built: {modules_built}

Rate 0-10 where:
10 = found critical vulnerabilities, highly actionable
5  = found interesting info, some actionable items
0  = found nothing useful

Reply ONLY with JSON:
{{"score": 7.2, "reason": "...", "top_finding": "...", "missed_opportunities": ["..."]}}"""

def rate_findings(run_id=None):
    """AI rates all unrated findings in the brain."""
    if not AI_AVAILABLE:
        rprint("[yellow]AI not available for rating. Using heuristic scores.[/yellow]")
        _heuristic_rate(run_id)
        return

    conn = get_db()
    c    = conn.cursor()

    query = "SELECT * FROM findings WHERE signal_score IS NULL"
    if run_id:
        query += f" AND run_id = '{run_id}'"
    query += " LIMIT 50"

    findings = c.execute(query).fetchall()
    rprint(f"\n[cyan]Rating {len(findings)} findings...[/cyan]")

    rated = 0
    for f in findings:
        prompt = RATING_PROMPT.format(
            type=f["type"], severity=f["severity"],
            data=str(f["data"])[:300]
        )
        try:
            result = AI_CLIENT.messages.create(
                model=MODEL, max_tokens=300, system="Security analyst. Reply only JSON.",
                messages=[{"role":"user","content":prompt}]
            ).content[0].text
            clean  = re.sub(r"```[a-z]*\s*","",result).strip()
            rating = json.loads(clean)
            c.execute("""
                UPDATE findings SET signal_score=?, noise_score=? WHERE id=?
            """, (rating.get("signal_score",5), rating.get("noise_score",5), f["id"]))
            rated += 1
            rprint(f"  [dim]signal={rating.get('signal_score',0):.1f} noise={rating.get('noise_score',0):.1f}  {f['type'][:30]}[/dim]")
        except Exception as e:
            rprint(f"  [red]Rating error: {e}[/red]")
        time.sleep(0.3)

    conn.commit()
    conn.close()
    rprint(f"[green]✅  Rated {rated} findings[/green]")

def _heuristic_rate(run_id=None):
    """Rate findings without AI using heuristic rules."""
    conn = get_db()
    c    = conn.cursor()
    SIGNAL = {"critical":9,"high":7,"medium":5,"low":3,"info":2}
    NOISE  = {"critical":1,"high":2,"medium":4,"low":6,"info":7}
    q = "SELECT * FROM findings WHERE signal_score IS NULL"
    if run_id: q += f" AND run_id='{run_id}'"
    for f in c.execute(q).fetchall():
        sev = f["severity"]
        c.execute("UPDATE findings SET signal_score=?,noise_score=? WHERE id=?",
                  (SIGNAL.get(sev,5), NOISE.get(sev,5), f["id"]))
    conn.commit(); conn.close()

def rate_run(run_id):
    """AI rates an overall run."""
    if not AI_AVAILABLE:
        rprint("[dim]Skipping run rating — AI offline[/dim]"); return

    conn = get_db()
    c    = conn.cursor()
    run  = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not run: rprint(f"[red]Run not found: {run_id}[/red]"); return

    findings = c.execute("SELECT severity,COUNT(*) as n FROM findings WHERE run_id=? GROUP BY severity",
                         (run_id,)).fetchall()
    breakdown = {f["severity"]:f["n"] for f in findings}

    prompt = RUN_RATING_PROMPT.format(
        target         = run["target"],
        mode           = run["mode"],
        finding_count  = run["finding_count"],
        severity_breakdown = json.dumps(breakdown),
        modules_built  = run["modules_built"]
    )
    try:
        result = AI_CLIENT.messages.create(
            model=MODEL, max_tokens=400, system="Security expert. Reply only JSON.",
            messages=[{"role":"user","content":prompt}]
        ).content[0].text
        clean  = re.sub(r"```[a-z]*\s*","",result).strip()
        rating = json.loads(clean)
        score  = rating.get("score",5)
        c.execute("UPDATE runs SET score=?,notes=? WHERE run_id=?",
                  (score, rating.get("reason",""), run_id))
        conn.commit()
        rprint(f"\n  [bold]Run score:[/bold] [{'green' if score>=7 else 'yellow' if score>=4 else 'red'}]{score}/10[/]")
        rprint(f"  [dim]{rating.get('reason','')}[/dim]")
        if rating.get("missed_opportunities"):
            rprint(f"\n  [yellow]Missed:[/yellow]")
            for m in rating.get("missed_opportunities",[]):
                rprint(f"    [yellow]→[/yellow] {m}")
    except Exception as e:
        rprint(f"[red]Run rating error: {e}[/red]")
    conn.close()

# ══════════════════════════════════════════════════════════════════════════════
# 🔍 EXTRACT — Pull patterns from accumulated runs
# ══════════════════════════════════════════════════════════════════════════════

PATTERN_EXTRACTOR = """You are a security intelligence analyst.

Analyze these security findings from multiple runs and extract reusable patterns.

Findings:
{findings}

Extract patterns like:
- "Redis (port 6379) is frequently exposed on internal /24 networks"
- "WordPress sites almost always have /wp-admin exposed"
- "SSH on non-standard ports often has weaker credentials"
- "Sites with X-Powered-By headers are more likely to have other info leaks"

For each pattern, specify what action FORGE should take automatically when it's detected.

Reply ONLY with JSON array:
[
  {{
    "pattern": "description of the pattern",
    "category": "target_type|finding_type|timing|approach|correlation",
    "confidence": 0.0-1.0,
    "actionable": true/false,
    "action": "what FORGE should automatically do when this is seen",
    "frequency_hint": "how often you see this in the data"
  }}
]"""

def extract_patterns(min_runs=2):
    """Extract recurring patterns from all run data."""
    conn = get_db()
    c    = conn.cursor()

    # Get high-signal findings from recent runs
    findings = c.execute("""
        SELECT f.type, f.severity, f.data, f.target, r.mode, r.target as run_target
        FROM findings f JOIN runs r ON f.run_id = r.run_id
        WHERE (f.signal_score IS NULL OR f.signal_score >= 4)
        ORDER BY f.ts DESC LIMIT 100
    """).fetchall()

    if len(findings) < 3:
        rprint("[yellow]Not enough findings yet. Run more scans first.[/yellow]")
        conn.close(); return []

    rprint(f"\n[cyan]Analyzing {len(findings)} findings for patterns...[/cyan]")

    findings_text = "\n".join(
        f"- [{f['severity']}] {f['type']}: {str(f['data'])[:100]}"
        for f in findings
    )

    if not AI_AVAILABLE:
        rprint("[yellow]AI offline — using frequency-based patterns[/yellow]")
        patterns = _frequency_patterns(findings)
    else:
        try:
            result = AI_CLIENT.messages.create(
                model=MODEL, max_tokens=2000,
                system="Security intelligence analyst. Reply only JSON array.",
                messages=[{"role":"user","content":
                           PATTERN_EXTRACTOR.format(findings=findings_text)}]
            ).content[0].text
            clean    = re.sub(r"```[a-z]*\s*","",result).strip()
            patterns = json.loads(clean)
        except Exception as e:
            rprint(f"[red]Pattern extraction error: {e}[/red]")
            patterns = []

    # Save to brain
    new_count = 0
    for p in patterns:
        existing = c.execute(
            "SELECT * FROM patterns WHERE pattern=?", (p.get("pattern",""),)
        ).fetchone()
        if existing:
            c.execute("""
                UPDATE patterns SET frequency=frequency+1, last_seen=?, confidence=?
                WHERE id=?
            """, (datetime.now().isoformat(), p.get("confidence",0.5), existing["id"]))
        else:
            c.execute("""
                INSERT INTO patterns (pattern,category,confidence,first_seen,last_seen,actionable,action)
                VALUES (?,?,?,?,?,?,?)
            """, (p.get("pattern",""), p.get("category","finding_type"),
                  p.get("confidence",0.5), datetime.now().isoformat(),
                  datetime.now().isoformat(), int(p.get("actionable",False)),
                  p.get("action","")))
            new_count += 1

    conn.commit()
    conn.close()

    # Also save human-readable patterns file
    all_patterns = [dict(p) for p in patterns]
    PATTERNS_F.write_text(json.dumps(all_patterns, indent=2))

    rprint(f"[green]✅  Extracted {len(patterns)} patterns ({new_count} new)[/green]")
    return patterns

def _frequency_patterns(findings):
    """Fallback pattern extraction without AI."""
    type_count = defaultdict(int)
    for f in findings:
        type_count[f["type"]] += 1
    return [
        {"pattern": f"'{k}' appears frequently ({v} times)",
         "category":"finding_type","confidence":min(v/10,1.0),
         "actionable":v>=3,"action":f"Always check for {k}"}
        for k,v in sorted(type_count.items(),key=lambda x:-x[1])[:10]
    ]

def get_patterns_for_target(target, target_type="domain"):
    """Get relevant patterns for a specific target type."""
    conn = get_db()
    c    = conn.cursor()
    patterns = c.execute("""
        SELECT * FROM patterns
        WHERE actionable=1 AND confidence >= 0.5
        ORDER BY frequency DESC, confidence DESC
        LIMIT 20
    """).fetchall()
    conn.close()
    return [dict(p) for p in patterns]

# ══════════════════════════════════════════════════════════════════════════════
# 🧬 EVOLVE — Genetic algorithm on system prompts
# ══════════════════════════════════════════════════════════════════════════════

MUTATOR_PROMPT = """You are a prompt engineer improving an AI system prompt.

The current prompt has performance score: {score}/10
It's used for: {purpose}

Current prompt:
---
{prompt}
---

Recent run feedback:
{feedback}

Missed opportunities:
{missed}

Create an IMPROVED version that:
1. Addresses the missed opportunities
2. Incorporates learned patterns
3. Is more specific and actionable
4. Keeps what worked

Learned patterns to incorporate:
{patterns}

Reply with ONLY the improved prompt text (no preamble, no explanation, no markdown)."""

CROSSOVER_PROMPT = """You are a prompt engineer creating a hybrid prompt.

Combine the best parts of these two prompts into one superior version.

Prompt A (score {score_a}/10):
---
{prompt_a}
---

Prompt B (score {score_b}/10):
---
{prompt_b}
---

Create a hybrid that takes the strongest elements from each.
Reply with ONLY the new prompt text."""

def evolve_prompt(prompt_name, generations=3, population=4):
    """Run genetic algorithm on a system prompt."""
    rprint(f"\n[magenta bold]🧬 EVOLVING PROMPT: {prompt_name}[/magenta bold]")
    rprint(f"[dim]Generations: {generations} | Population: {population}[/dim]\n")

    if not AI_AVAILABLE:
        rprint("[red]AI required for prompt evolution.[/red]"); return None

    conn = get_db()
    c    = conn.cursor()

    # Get current best prompt
    current = c.execute("""
        SELECT * FROM prompts WHERE name=?
        ORDER BY performance DESC, version DESC LIMIT 1
    """, (prompt_name,)).fetchone()

    if not current:
        rprint(f"[yellow]No prompt found: {prompt_name}. Use 'prompts add' to seed one.[/yellow]")
        conn.close(); return None

    # Get run feedback
    recent_runs = c.execute("""
        SELECT score, notes FROM runs ORDER BY started_at DESC LIMIT 10
    """).fetchall()
    feedback = "\n".join(f"- Score {r['score']}: {r['notes'][:60]}" for r in recent_runs if r["notes"])

    missed_items = c.execute("""
        SELECT notes FROM runs WHERE notes LIKE '%missed%' ORDER BY started_at DESC LIMIT 5
    """).fetchall()
    missed = "\n".join(f"- {m['notes'][:80]}" for m in missed_items) or "None recorded"

    patterns = get_patterns_for_target("*")
    patterns_text = "\n".join(f"- {p['pattern']}" for p in patterns[:10]) or "No patterns yet"

    population_prompts = [dict(current)]
    best_score = current["performance"] or 5.0

    for gen in range(1, generations+1):
        rprint(f"\n[cyan]Generation {gen}/{generations}[/cyan]  (best score: {best_score:.1f}/10)")
        new_variants = []

        # Mutation — improve existing prompts
        for i in range(population // 2):
            parent = population_prompts[i % len(population_prompts)]
            rprint(f"  🔬 Mutating variant {i+1}...")
            try:
                result = AI_CLIENT.messages.create(
                    model=MODEL, max_tokens=2000,
                    system="Expert prompt engineer. Improve AI system prompts.",
                    messages=[{"role":"user","content": MUTATOR_PROMPT.format(
                        score   = parent.get("performance",5),
                        purpose = prompt_name,
                        prompt  = parent["content"],
                        feedback= feedback or "No feedback yet",
                        missed  = missed,
                        patterns= patterns_text,
                    )}]
                ).content[0].text
                new_variants.append({
                    "name":      prompt_name,
                    "content":   result.strip(),
                    "parent_id": parent.get("id"),
                    "mutation":  f"gen{gen}_mutant_{i+1}",
                    "performance": parent.get("performance",5) + 0.1,  # optimistic start
                })
                rprint(f"  [green]✓[/green] Mutant {i+1} created ({len(result)} chars)")
            except Exception as e:
                rprint(f"  [red]✗ Mutation failed: {e}[/red]")

        # Crossover — combine best two
        if len(population_prompts) >= 2:
            rprint(f"  🔀 Crossover...")
            try:
                p1, p2 = population_prompts[0], population_prompts[1]
                result = AI_CLIENT.messages.create(
                    model=MODEL, max_tokens=2000,
                    system="Expert prompt engineer.",
                    messages=[{"role":"user","content": CROSSOVER_PROMPT.format(
                        score_a=p1.get("performance",5), prompt_a=p1["content"],
                        score_b=p2.get("performance",5), prompt_b=p2["content"],
                    )}]
                ).content[0].text
                new_variants.append({
                    "name":      prompt_name,
                    "content":   result.strip(),
                    "parent_id": p1.get("id"),
                    "mutation":  f"gen{gen}_crossover",
                    "performance": max(p1.get("performance",5), p2.get("performance",5)) + 0.2,
                })
                rprint(f"  [green]✓[/green] Crossover created")
            except Exception as e:
                rprint(f"  [red]✗ Crossover failed: {e}[/red]")

        # Save new variants
        for v in new_variants:
            ver = (c.execute("SELECT MAX(version) as m FROM prompts WHERE name=?",
                             (prompt_name,)).fetchone()["m"] or 0) + 1
            c.execute("""
                INSERT INTO prompts (name,version,content,performance,parent_id,mutation,created_at)
                VALUES (?,?,?,?,?,?,?)
            """, (v["name"], ver, v["content"], v.get("performance",5),
                  v.get("parent_id"), v.get("mutation",""), datetime.now().isoformat()))
            conn.commit()

        # Update population — keep best
        all_variants = c.execute("""
            SELECT * FROM prompts WHERE name=? ORDER BY performance DESC LIMIT ?
        """, (prompt_name, population)).fetchall()
        population_prompts = [dict(v) for v in all_variants]

        if population_prompts:
            best_score = population_prompts[0].get("performance",5)

    # Save winner to file
    winner = population_prompts[0] if population_prompts else None
    if winner:
        out_fp = EVOLVED_DIR / f"{prompt_name}_v{winner.get('version',1)}.txt"
        out_fp.write_text(winner["content"])
        rprint(f"\n[green bold]🏆 EVOLUTION COMPLETE[/green bold]")
        rprint(f"  Best score:    {winner.get('performance',0):.1f}/10")
        rprint(f"  Generations:   {generations}")
        rprint(f"  Saved to:      {out_fp}")

    conn.close()
    return winner

def get_best_prompt(name, fallback=None):
    """Get the current best performing prompt for a given purpose."""
    conn = get_db()
    c    = conn.cursor()
    row  = c.execute("""
        SELECT content FROM prompts WHERE name=? ORDER BY performance DESC LIMIT 1
    """, (name,)).fetchone()
    conn.close()
    return row["content"] if row else fallback

# ══════════════════════════════════════════════════════════════════════════════
# 💡 INSIGHTS — Distilled knowledge
# ══════════════════════════════════════════════════════════════════════════════

INSIGHT_EXTRACTOR = """You are a security knowledge distiller.

Based on all these runs and findings, what are the 5 most important things FORGE has learned?
These should be actionable insights that improve future scans.

Runs summary: {runs}
Top patterns: {patterns}
High-signal findings: {findings}

Reply ONLY with JSON array of insights:
[
  {{
    "insight": "Clear, actionable statement of what was learned",
    "confidence": 0.0-1.0,
    "applies_to": "all|internal|web|cloud|etc"
  }}
]"""

def extract_insights():
    """Distill all accumulated knowledge into key insights."""
    conn = get_db()
    c    = conn.cursor()

    runs = c.execute("SELECT target,mode,score,notes FROM runs ORDER BY started_at DESC LIMIT 20").fetchall()
    patterns = c.execute("SELECT pattern,frequency,confidence FROM patterns WHERE actionable=1 ORDER BY frequency DESC LIMIT 10").fetchall()
    findings = c.execute("""
        SELECT type,severity,data FROM findings
        WHERE signal_score>=7 ORDER BY signal_score DESC LIMIT 20
    """).fetchall()

    if not runs:
        rprint("[yellow]No runs recorded yet.[/yellow]"); conn.close(); return []

    if not AI_AVAILABLE:
        rprint("[dim]Using heuristic insights (AI offline)[/dim]")
        insights = [{"insight":f"Pattern '{p['pattern'][:50]}' seen {p['frequency']} times",
                     "confidence":p["confidence"],"applies_to":"all"} for p in patterns[:5]]
    else:
        try:
            result = AI_CLIENT.messages.create(
                model=MODEL, max_tokens=1500,
                system="Security knowledge distiller. Reply only JSON.",
                messages=[{"role":"user","content": INSIGHT_EXTRACTOR.format(
                    runs=json.dumps([dict(r) for r in runs], default=str),
                    patterns=json.dumps([dict(p) for p in patterns], default=str),
                    findings=json.dumps([dict(f) for f in findings][:10], default=str),
                )}]
            ).content[0].text
            clean    = re.sub(r"```[a-z]*\s*","",result).strip()
            insights = json.loads(clean)
        except Exception as e:
            rprint(f"[red]Insight extraction error: {e}[/red]")
            insights = []

    # Save insights
    for ins in insights:
        existing = c.execute("SELECT id FROM insights WHERE insight=?",
                             (ins.get("insight",""),)).fetchone()
        if not existing:
            c.execute("INSERT INTO insights (insight,confidence,ts,source) VALUES (?,?,?,?)",
                      (ins.get("insight",""), ins.get("confidence",0.5),
                       datetime.now().isoformat(), "auto_extracted"))
    conn.commit()
    conn.close()

    rprint(f"[green]✅  Extracted {len(insights)} insights[/green]")
    return insights

def inject_insights_into_prompt(base_prompt, target=None):
    """Inject learned patterns and insights into a prompt before use."""
    conn = get_db()
    c    = conn.cursor()

    patterns = get_patterns_for_target(target or "*")
    insights = c.execute("""
        SELECT insight FROM insights WHERE confidence>=0.6
        ORDER BY used_count ASC, confidence DESC LIMIT 8
    """).fetchall()
    conn.close()

    if not patterns and not insights:
        return base_prompt

    injections = "\n\n[FORGE LEARNED INTELLIGENCE]\n"
    if insights:
        injections += "Key insights from previous runs:\n"
        for ins in insights:
            injections += f"- {ins['insight']}\n"
    if patterns:
        injections += "\nActionable patterns:\n"
        for p in patterns[:6]:
            injections += f"- {p['pattern']}"
            if p.get("action"):
                injections += f" → {p['action']}"
            injections += "\n"

    return base_prompt + injections

# ══════════════════════════════════════════════════════════════════════════════
# 📊 DISPLAY — Stats and dashboards
# ══════════════════════════════════════════════════════════════════════════════

def show_status():
    """Show the brain's current state."""
    conn = get_db()
    c    = conn.cursor()

    runs      = c.execute("SELECT COUNT(*) as n FROM runs").fetchone()["n"]
    findings  = c.execute("SELECT COUNT(*) as n FROM findings").fetchone()["n"]
    modules   = c.execute("SELECT COUNT(*) as n FROM modules").fetchone()["n"]
    patterns  = c.execute("SELECT COUNT(*) as n FROM patterns").fetchone()["n"]
    insights  = c.execute("SELECT COUNT(*) as n FROM insights").fetchone()["n"]
    prompts   = c.execute("SELECT COUNT(*) as n FROM prompts").fetchone()["n"]

    avg_score = c.execute("SELECT AVG(score) as s FROM runs WHERE score>0").fetchone()["s"] or 0
    top_run   = c.execute("SELECT target,score FROM runs WHERE score>0 ORDER BY score DESC LIMIT 1").fetchone()
    sev_dist  = c.execute("SELECT severity,COUNT(*) as n FROM findings GROUP BY severity").fetchall()

    if RICH:
        console.print(Panel.fit(
            f"[bold cyan]🧠  FORGE BRAIN STATUS[/bold cyan]\n\n"
            f"  [bold]Runs recorded:[/bold]     [green]{runs}[/green]\n"
            f"  [bold]Findings stored:[/bold]   [yellow]{findings}[/yellow]\n"
            f"  [bold]Modules tracked:[/bold]   [magenta]{modules}[/magenta]\n"
            f"  [bold]Patterns learned:[/bold]  [cyan]{patterns}[/cyan]\n"
            f"  [bold]Insights:[/bold]          [blue]{insights}[/blue]\n"
            f"  [bold]Evolved prompts:[/bold]   [magenta]{prompts}[/magenta]\n"
            f"  [bold]Avg run score:[/bold]     [{'green' if avg_score>=7 else 'yellow' if avg_score>=4 else 'red'}]{avg_score:.1f}/10[/]\n"
            + (f"  [bold]Best run:[/bold]         [green]{top_run['target']} ({top_run['score']:.1f}/10)[/green]\n" if top_run else ""),
            border_style="cyan", title="Brain"
        ))

        if sev_dist:
            t = Table(title="Findings by Severity", border_style="yellow", box=rbox.SIMPLE)
            t.add_column("Severity", style="bold")
            t.add_column("Count",    style="white")
            t.add_column("Bar",      style="dim")
            total = sum(r["n"] for r in sev_dist)
            colors = {"critical":"red","high":"orange3","medium":"yellow","low":"green","info":"dim"}
            for row in sorted(sev_dist, key=lambda x: ["critical","high","medium","low","info"].index(x["severity"]) if x["severity"] in ["critical","high","medium","low","info"] else 99):
                pct = int(row["n"]/max(total,1)*20)
                color = colors.get(row["severity"],"dim")
                t.add_row(f"[{color}]{row['severity']}[/{color}]",
                          str(row["n"]), "█"*pct)
            console.print(t)
    else:
        print(f"\n🧠  FORGE BRAIN: {runs} runs | {findings} findings | {patterns} patterns | score {avg_score:.1f}/10")

    conn.close()

def show_patterns():
    """Display learned patterns."""
    conn = get_db()
    patterns = conn.execute("""
        SELECT * FROM patterns ORDER BY frequency DESC, confidence DESC LIMIT 30
    """).fetchall()
    conn.close()

    if not patterns:
        rprint("[dim]No patterns yet. Run 'extract' after some scans.[/dim]"); return

    if RICH:
        t = Table(title="🔍 Learned Patterns", border_style="cyan", show_lines=True, box=rbox.ROUNDED)
        t.add_column("#",          style="dim",        width=4)
        t.add_column("Pattern",    style="white",       width=45)
        t.add_column("Freq",       style="green",       width=5)
        t.add_column("Conf",       style="cyan",        width=6)
        t.add_column("Action",     style="yellow dim",  width=30)
        for i, p in enumerate(patterns, 1):
            conf_bar = "█"*int(p["confidence"]*5)+"░"*(5-int(p["confidence"]*5))
            t.add_row(str(i), p["pattern"][:44], str(p["frequency"]),
                      f"{conf_bar}", (p["action"] or "─")[:29])
        console.print(t)
    else:
        for p in patterns:
            print(f"  [{p['frequency']}x] {p['pattern'][:60]}")

def show_runs(n=10):
    """Display recent runs."""
    conn  = get_db()
    runs  = conn.execute(
        "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (n,)
    ).fetchall()
    conn.close()

    if not runs:
        rprint("[dim]No runs yet.[/dim]"); return

    if RICH:
        t = Table(title="📋 Recent Runs", border_style="blue", show_lines=True, box=rbox.ROUNDED)
        t.add_column("Run ID",     style="dim",         width=24)
        t.add_column("Target",     style="bold white",  width=20)
        t.add_column("Mode",       style="cyan",        width=8)
        t.add_column("Findings",   style="yellow",      width=9)
        t.add_column("Score",      style="bold",        width=8)
        t.add_column("Date",       style="dim",         width=12)
        for r in runs:
            score = r["score"] or 0
            color = "green" if score>=7 else ("yellow" if score>=4 else "red") if score>0 else "dim"
            t.add_row(r["run_id"][:22], r["target"][:19], r["mode"],
                      str(r["finding_count"]),
                      f"[{color}]{score:.1f}[/{color}]" if score else "─",
                      (r["started_at"] or "")[:10])
        console.print(t)
    else:
        for r in runs:
            print(f"  {r['run_id'][:20]} | {r['target'][:20]} | score {r['score'] or '?'}")

def show_insights():
    """Display distilled insights."""
    conn     = get_db()
    insights = conn.execute(
        "SELECT * FROM insights ORDER BY confidence DESC LIMIT 20"
    ).fetchall()
    conn.close()

    if not insights:
        rprint("[dim]No insights yet. Run 'learn' after some scans.[/dim]"); return

    rprint(f"\n[bold cyan]💡 FORGE INSIGHTS ({len(insights)})[/bold cyan]\n")
    for i, ins in enumerate(insights, 1):
        conf  = ins["confidence"]
        color = "green" if conf>=0.8 else ("yellow" if conf>=0.5 else "dim")
        rprint(f"  [{color}]{i:>2}.[/{color}]  {ins['insight']}")
        rprint(f"      [dim]confidence: {conf:.0%}[/dim]")

# ══════════════════════════════════════════════════════════════════════════════
# 🔄 FULL LEARNING LOOP
# ══════════════════════════════════════════════════════════════════════════════

def run_full_loop(run_id=None):
    """Execute the complete learning loop after a run."""
    rprint(f"\n[magenta bold]🔁 RUNNING FULL LEARNING LOOP[/magenta bold]\n")

    steps = [
        ("📥 Rating findings",    lambda: rate_findings(run_id)),
        ("📊 Rating run",         lambda: rate_run(run_id) if run_id else None),
        ("🔍 Extracting patterns",lambda: extract_patterns()),
        ("💡 Distilling insights",lambda: extract_insights()),
    ]
    for label, fn in steps:
        rprint(f"  [cyan]{label}...[/cyan]")
        try:
            fn()
        except Exception as e:
            rprint(f"  [red]Error: {e}[/red]")

    rprint(f"\n[green bold]✅ Learning loop complete. FORGE is smarter.[/green bold]")
    show_status()

def auto_learn_from_swarm():
    """One-command: import swarm results + run full learning loop."""
    rprint(f"\n[cyan]🧠 Auto-learning from last swarm run...[/cyan]")
    run_id = capture_from_swarm_hive()
    if run_id:
        run_full_loop(run_id)

# ══════════════════════════════════════════════════════════════════════════════
# 🖥️ INTERACTIVE CONSOLE
# ══════════════════════════════════════════════════════════════════════════════

def banner():
    rprint(f"""
[cyan][bold]
  ███████╗ ██████╗ ██████╗  ██████╗ ███████╗    ██╗     ███████╗ █████╗ ██████╗ ███╗   ██╗
  ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝    ██║     ██╔════╝██╔══██╗██╔══██╗████╗  ██║
  █████╗  ██║   ██║██████╔╝██║  ███╗█████╗      ██║     █████╗  ███████║██████╔╝██╔██╗ ██║
  ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝      ██║     ██╔══╝  ██╔══██║██╔══██╗██║╚██╗██║
  ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗    ███████╗███████╗██║  ██║██║  ██║██║ ╚████║
  ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝    ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝
[/bold][/cyan]
[magenta bold]  Self-Improving Learning Engine — FORGE gets smarter every run[/magenta bold]
[dim]  Brain: {BRAIN_DB}  |  AI: {'✅' if AI_AVAILABLE else '❌ offline'}[/dim]
""")

def main():
    banner()

    # Handle CLI args
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "--status":   show_status(); return
        if cmd == "--learn":    auto_learn_from_swarm(); return
        if cmd == "--patterns": extract_patterns(); show_patterns(); return
        if cmd == "--evolve":
            name = sys.argv[2] if len(sys.argv)>2 else "swarm_planner"
            evolve_prompt(name); return
        if cmd == "--import":
            hive = Path(sys.argv[2]) if len(sys.argv)>2 else None
            rid  = capture_from_swarm_hive(hive)
            if rid: run_full_loop(rid)
            return

    COMMANDS = {
        "status":   (show_status,               "Show brain stats"),
        "runs":     (show_runs,                 "Show recent runs"),
        "patterns": (show_patterns,             "Show learned patterns"),
        "insights": (show_insights,             "Show distilled insights"),
        "learn":    (auto_learn_from_swarm,     "Import swarm results + run full loop"),
        "rate":     (lambda: rate_findings(),   "Rate unscored findings"),
        "extract":  (lambda: extract_patterns(),"Extract patterns from all runs"),
        "distill":  (lambda: extract_insights(),"Distill key insights"),
        "loop":     (lambda: run_full_loop(),   "Run full learning loop now"),
        "evolve":   (lambda: evolve_prompt(
                        ask("Prompt name", "swarm_planner"),
                        int(ask("Generations","3")),
                        int(ask("Population","4"))
                    ),                          "Evolve a system prompt"),
        "help":     (None,                      "Show commands"),
    }

    rprint("[dim]Commands: " + " | ".join(COMMANDS.keys()) + "[/dim]\n")

    while True:
        try:
            raw = (console.input("[bold magenta]forge-learn >[/bold magenta] ")
                   if RICH else input("forge-learn > ")).strip()
        except (KeyboardInterrupt, EOFError):
            rprint("\n[cyan]⚒️  FORGE LEARN — Brain saved. 🔥[/cyan]"); break

        if not raw: continue
        parts = raw.split(); cmd = parts[0].lower()

        if cmd in ("exit","quit","q"):
            rprint("[cyan]⚒️  FORGE LEARN — Brain saved. 🔥[/cyan]"); break
        elif cmd == "help":
            rprint("\n[bold]Commands:[/bold]")
            for k,(fn,desc) in COMMANDS.items():
                rprint(f"  [yellow]{k:<12}[/yellow] {desc}")
        elif cmd in COMMANDS and COMMANDS[cmd][0]:
            try: COMMANDS[cmd][0]()
            except Exception as e: rprint(f"[red]Error: {e}[/red]")
        else:
            rprint(f"[dim]Unknown: '{cmd}'. Type 'help'.[/dim]")

if __name__ == "__main__":
    main()
