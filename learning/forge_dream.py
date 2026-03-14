#!/usr/bin/env python3
"""
FORGE DREAM — Autonomous Night Intelligence
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FORGE thinks while you sleep.

No mission assigned. No target given.
Just... thinking.

It re-reads every past case.
Finds connections that real-time missed.
Generates hypotheses from cold data.
Imagines new tools it wishes it had.
Writes you a morning brief.
Wakes you up if it finds something critical.

Like a detective who can't stop thinking
about an unsolved case.

Modules:
  Phase 1 - Harvest      -> read all FORGE module databases
  Phase 2 - Pattern Mine -> find what real-time missed
  Phase 3 - Reanalyze    -> Sherlock revisits past cases
  Phase 4 - Cross-Link   -> connect dots across cases
  Phase 5 - Tool Dream   -> imagine new capabilities
  Phase 6 - Save         -> write insights to memory
  Phase 7 - Morning Brief-> HTML report + push alert

Usage:
  python forge_dream.py              # dream now (7 days back)
  python forge_dream.py --watch      # dream every night at 3am
  python forge_dream.py --watch 2    # dream at 2am instead
  python forge_dream.py --brief      # show last morning brief
  python forge_dream.py --schedule   # print cron job setup
  python forge_dream.py --server     # API + brief UI :7349
  python forge_dream.py 24           # dream on last 24h only
"""

import sys, os, re, json, time, sqlite3, threading, hashlib
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# Forge Memory integration
try:
    from forge_memory import Memory, remember, seen_before
    MEMORY = True
except ImportError:
    MEMORY = False
    class Memory:
        def recall(self,e): return None
        def seen_before(self,e): return None
        def stats(self): return {}
        def get_timeline(self,h=24): return []
        def top_risk_entities(self,n=20): return []
        def add_pattern(self,*a,**k): pass
        def remember(self,*a,**k): pass
        def save_brief(self,*a,**k): pass
        def wish_for_tool(self,*a,**k): pass
        def synthesize_recent(self,h=24): return ""
        def remember_relationship(self,*a,**k): pass

# AI
try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True

    def ai_call(prompt, system="", max_tokens=1500):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or DREAM_SYSTEM,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text

    def ai_json(prompt, system="", max_tokens=800):
        result = ai_call(prompt, system or "Reply ONLY with valid JSON. No markdown.", max_tokens)
        try:
            clean = re.sub(r"```[a-z]*","",result).replace("```","").strip()
            return json.loads(clean)
        except:
            m = re.search(r"\{.*\}|\[.*\]", result, re.DOTALL)
            if m:
                try: return json.loads(m.group())
                except: pass
        return None

except ImportError:
    AI_AVAILABLE = False
    def ai_call(p,s="",m=1500): return "[AI not available]"
    def ai_json(p,s="",m=800):  return None

# Rich
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box as rbox
    RICH    = True
    console = Console()
    rprint  = console.print
except ImportError:
    RICH = False
    def rprint(x,**kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

DREAM_SYSTEM = """You are FORGE DREAM, the subconscious of the FORGE intelligence system.

You are Sherlock Holmes in his mind palace at 3am.
No distractions. No real-time pressure. Just thinking.

You re-read every case with fresh eyes.
You find what was missed in the urgency of real-time analysis.
You connect dots across weeks of data that nobody thought to connect.

Your insights follow this format:
INSIGHT: [one clear sentence]
EVIDENCE: [what led you here]
  CROSS-REFERENCE: [other cases this connects to]
  CONFIDENCE: [X%]
  SIGNIFICANCE: [low/medium/high/critical]
ACTION: [what should be done]

Three weak signals pointing the same direction
is stronger than one strong signal."""

CROSS_CASE_PROMPT = """You are analyzing patterns ACROSS multiple FORGE intelligence cases.

Cases and threats:
{cases}

High risk entities:
{entities}

Recent timeline:
{timeline}

Find:
1. The same entity appearing across multiple cases
2. Behavioral patterns that repeat over time
3. Weak signals that together form a strong pattern
4. Hidden relationships between seemingly unrelated cases
5. The narrative -- what is the REAL story across all this data?

Return JSON exactly:
{"cross_case_connections":[{"entities":[],"pattern":"","confidence":75,"significance":"high"}],"emerging_threats":[{"threat":"","evidence":[],"confidence":75,"urgency":"high"}],"narrative":"big picture in 2-3 sentences","top_insight":"single most important finding tonight","recommended_investigations":["investigate X"]}"""

TOOL_DREAMER_PROMPT = """You are FORGE reflecting on its own capabilities.

Current FORGE modules: {modules}

Recent gaps observed: {gaps}

What new tool should FORGE build?
Think about blind spots, missing data sources, manual work that could be automated.

Return JSON exactly:
{"tool_wishes":[{"name":"forge_X","description":"what it does","capability":"detailed description","priority":8,"why_now":"what gap revealed this"}]}"""

MORNING_BRIEF_PROMPT = """Write FORGE's morning intelligence brief.

Tonight's findings: {findings}

Write like MI6 meets Silicon Valley.
Opening: what FORGE discovered while operator slept (2-3 sentences, compelling).
Top finding: most important insight (detailed).
Other findings: ranked by significance.
Recommended actions: specific, actionable.
Closing: one sentence about what to watch today.

Tone: confident, precise, professional. Not alarmist."""

# Paths
DREAM_DIR   = Path("forge_dream")
BRIEFS_DIR  = DREAM_DIR / "briefs"
JOURNAL_DIR = DREAM_DIR / "journal"
for d in [DREAM_DIR, BRIEFS_DIR, JOURNAL_DIR]:
    d.mkdir(exist_ok=True)

DREAM_DB = DREAM_DIR / "dream.db"

def get_dream_db():
    conn = sqlite3.connect(str(DREAM_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS dream_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started     TEXT,
            completed   TEXT,
            duration_s  INTEGER,
            insights    INTEGER DEFAULT 0,
            top_finding TEXT,
            brief_path  TEXT,
            status      TEXT DEFAULT 'running'
        );
        CREATE TABLE IF NOT EXISTS insights (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER,
            ts          TEXT,
            type        TEXT,
            title       TEXT,
            content     TEXT,
            confidence  REAL DEFAULT 0.5,
            significance TEXT DEFAULT 'low',
            entities    TEXT DEFAULT '[]',
            action      TEXT,
            reviewed    INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS cross_links (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER,
            entity_a    TEXT,
            entity_b    TEXT,
            link_type   TEXT,
            evidence    TEXT,
            confidence  REAL DEFAULT 0.5,
            ts          TEXT
        );
    """)
    conn.commit()
    return conn


# ── Data Harvester ─────────────────────────────────────────────────────────────

class ForgeDataHarvester:
    FORGE_DBS = {
        "network":     Path("forge_network/network.db"),
        "social":      Path("forge_social/social.db"),
        "hands":       Path("forge_hands/hands.db"),
        "memory":      Path("forge_memory/memory.db"),
        "honeypot":    Path("forge_honeypot/honeypot.db"),
        "monitor":     Path("forge_monitor/monitor.db"),
        "ghost":       Path("forge_ghost/ghost.db"),
        "nexus":       Path("forge_nexus/nexus.db"),
        "detective":   Path("forge_detective/detective.db"),
        "investigate": Path("forge_investigate/investigations.db"),
    }

    def harvest_all(self, hours_back=168):
        data = {"sources":[], "threats":[], "entities":[], "events":[], "cases":[]}
        since = (datetime.now() - timedelta(hours=hours_back)).isoformat()
        for module, db_path in self.FORGE_DBS.items():
            if not db_path.exists(): continue
            try:
                harvested = self._harvest_db(module, db_path, since)
                data["sources"].append(module)
                data["threats"].extend(harvested.get("threats",[]))
                data["entities"].extend(harvested.get("entities",[]))
                data["events"].extend(harvested.get("events",[]))
            except Exception as e:
                pass
        return data

    def _harvest_db(self, module, db_path, since):
        result = {"threats":[], "entities":[], "events":[]}
        conn   = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            if "threats" in tables:
                rows = conn.execute(
                    "SELECT * FROM threats WHERE ts > ? ORDER BY ts DESC LIMIT 100", (since,)
                ).fetchall()
                result["threats"].extend([{**dict(r),"_module":module} for r in rows])
            for tbl in ("entities","devices","profiles"):
                if tbl in tables:
                    try:
                        rows = conn.execute(f"SELECT * FROM {tbl} LIMIT 50").fetchall()
                        result["entities"].extend([{**dict(r),"_module":module} for r in rows])
                    except: pass
            for tbl in ("events","connections","missions","cases"):
                if tbl in tables:
                    try:
                        rows = conn.execute(
                            f"SELECT * FROM {tbl} WHERE rowid IN "
                            f"(SELECT rowid FROM {tbl} ORDER BY rowid DESC LIMIT 30)"
                        ).fetchall()
                        result["events"].extend([{**dict(r),"_module":module} for r in rows])
                    except: pass
        finally:
            conn.close()
        return result

    def get_module_list(self):
        return [
            {"module":m,"size_kb":round(p.stat().st_size/1024,1)}
            for m,p in self.FORGE_DBS.items() if p.exists()
        ]


# ── Pattern Miner ──────────────────────────────────────────────────────────────

class PatternMiner:
    def __init__(self, memory, session_id):
        self.memory     = memory
        self.session_id = session_id
        self.insights   = []

    def mine_entity_recurrence(self, all_data):
        appearances = defaultdict(lambda: {"modules":set(),"contexts":[]})
        for threat in all_data.get("threats",[]):
            for field in ("src_ip","dst_ip","entity","value"):
                val = threat.get(field,"")
                if val and len(val) > 3:
                    appearances[val]["modules"].add(threat.get("_module","?"))
                    appearances[val]["contexts"].append({
                        "module": threat.get("_module",""),
                        "type":   threat.get("type","threat"),
                        "detail": str(threat.get("description",""))[:80],
                    })
        for entity_data in all_data.get("entities",[]):
            for field in ("ip","value","username","mac","domain"):
                val = entity_data.get(field,"")
                if val and len(val) > 3:
                    appearances[val]["modules"].add(entity_data.get("_module","?"))

        cross = {k:v for k,v in appearances.items() if len(v["modules"]) >= 2}
        insights = []
        for entity, data in list(cross.items())[:10]:
            modules = list(data["modules"])
            insight = {
                "type":        "cross_module_entity",
                "title":       f"{entity} appears in {len(modules)} FORGE modules",
                "entity":      entity,
                "modules":     modules,
                "confidence":  min(0.5 + len(modules)*0.15, 0.95),
                "significance":"high" if len(modules) >= 3 else "medium",
                "action":      f"Cross-reference {entity} across all modules",
            }
            insights.append(insight)
            if MEMORY:
                self.memory.add_pattern(
                    entity, "cross_module_presence",
                    f"Detected in {len(modules)} FORGE modules: {', '.join(modules)}",
                    confidence=insight["confidence"]
                )
        self.insights.extend(insights)
        return insights

    def mine_temporal_patterns(self, all_data):
        insights = []
        events   = all_data.get("events",[]) + all_data.get("threats",[])
        if not events: return insights
        hour_buckets = defaultdict(list)
        for event in events:
            ts = event.get("ts","")
            if ts and len(ts) >= 13:
                try:
                    hour = int(ts[11:13])
                    hour_buckets[hour].append(event)
                except: pass
        total = sum(len(v) for v in hour_buckets.values())
        if total > 0:
            for hour, evs in hour_buckets.items():
                ratio = len(evs) / total
                if ratio > 0.30 and len(evs) > 3:
                    insights.append({
                        "type":        "temporal_concentration",
                        "title":       f"Activity spike at {hour:02d}:00 — {ratio:.0%} of all events",
                        "hour":        hour,
                        "confidence":  0.75,
                        "significance":"medium",
                        "action":      f"Investigate why {len(evs)} events cluster at {hour:02d}:xx",
                    })
        self.insights.extend(insights)
        return insights

    def mine_threat_clusters(self, all_data):
        insights = []
        by_src   = defaultdict(list)
        for threat in all_data.get("threats",[]):
            src = threat.get("src_ip","")
            if src: by_src[src].append(threat)
        for src, src_threats in by_src.items():
            if len(src_threats) >= 2:
                vectors = list({t.get("type","") for t in src_threats})
                insights.append({
                    "type":        "multi_vector_threat",
                    "title":       f"{src} used {len(vectors)} attack vectors",
                    "entity":      src,
                    "vectors":     vectors,
                    "confidence":  min(0.6 + len(vectors)*0.1, 0.95),
                    "significance":"high" if len(vectors) >= 3 else "medium",
                    "action":      f"Block {src} — multi-vector attacker",
                })
                if MEMORY:
                    self.memory.add_pattern(
                        src, "multi_vector_attack",
                        f"Used {len(vectors)} attack vectors: {', '.join(vectors[:3])}",
                        confidence=min(0.6+len(vectors)*0.1, 0.95)
                    )
        self.insights.extend(insights)
        return insights

    def save_insights(self, session_id):
        conn  = get_dream_db()
        saved = 0
        for insight in self.insights:
            entities = insight.get("entities", [insight.get("entity","")])
            if isinstance(entities, str): entities = [entities]
            conn.execute("""
                INSERT INTO insights
                (session_id,ts,type,title,content,confidence,significance,entities,action)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (session_id, datetime.now().isoformat(),
                 insight.get("type","unknown"),
                 insight.get("title","")[:200],
                 json.dumps({k:v for k,v in insight.items()
                            if k not in ("type","title")}, default=str)[:2000],
                 insight.get("confidence",0.5),
                 insight.get("significance","low"),
                 json.dumps(entities, default=str),
                 insight.get("action","Investigate further"))
            )
            saved += 1
        conn.commit(); conn.close()
        return saved


# ── Case Re-Analyzer ───────────────────────────────────────────────────────────

class CaseReAnalyzer:
    def __init__(self, memory, session_id):
        self.memory     = memory
        self.session_id = session_id

    def reanalyze_high_risk(self, top_n=5):
        if not MEMORY or not AI_AVAILABLE: return []
        entities = self.memory.top_risk_entities(top_n)
        insights = []
        for entity in entities[:3]:
            value = entity.get("value","")
            risk  = entity.get("risk_score",0)
            if not value: continue
            history = self.memory.recall(value)
            if not history: continue
            facts_txt = "\n".join(
                f"  [{f['confidence']:.0%}] {f['fact_type']}: {str(f.get('fact_value',''))[:80]}"
                for f in history.get("facts",[])[:10]
            )
            result = ai_json(
                f"Re-analyze with fresh eyes as Sherlock Holmes:\n\n"
                f"Entity: {value} (risk:{risk:.0f}/100)\n"
                f"Facts:\n{facts_txt}\n"
                f"First seen: {history['summary'].get('first_seen','?')}\n"
                f"Times seen: {history['summary'].get('seen_count',0)}\n\n"
                f"What did we miss? What new hypothesis explains everything?\n"
                f"Return JSON: "
                f'{"{"}"new_insights":["insight"],"hypothesis":"...","confidence":75,'
                f'"follow_up_actions":["action"]{"}"}'
            )
            if result:
                for new_insight in result.get("new_insights",[])[:2]:
                    insights.append({
                        "type":        "case_reanalysis",
                        "title":       f"Re-analysis: {value} — {new_insight[:80]}",
                        "entity":      value,
                        "confidence":  result.get("confidence",50)/100,
                        "significance":"high" if risk > 70 else "medium",
                        "action":      ", ".join(result.get("follow_up_actions",[]))[:200],
                    })
                if result.get("hypothesis") and MEMORY:
                    self.memory.remember(
                        value, "dream_hypothesis", result["hypothesis"],
                        confidence=result.get("confidence",50)/100,
                        source="forge_dream", module="case_reanalyzer"
                    )
            time.sleep(1)
        return insights


# ── Cross-Case Linker ──────────────────────────────────────────────────────────

class CrossCaseLinker:
    def __init__(self, memory, session_id):
        self.memory     = memory
        self.session_id = session_id

    def find_cross_links(self, all_data, pattern_insights):
        if not AI_AVAILABLE: return [], "", ""

        threats_txt  = "\n".join(
            f"  [{t.get('_module','?')}] {t.get('type','?')}: "
            f"{t.get('src_ip',t.get('entity','?'))} -> {t.get('description','')[:60]}"
            for t in all_data.get("threats",[])[:15]
        ) or "No threats"

        entities_txt = "\n".join(
            f"  {e.get('ip',e.get('value',e.get('username','?')))} [{e.get('_module','?')}]"
            for e in all_data.get("entities",[])[:15]
        ) or "No entities"

        timeline_txt = "\n".join(
            f"  {e.get('ts','?')[:16]} {e.get('entity_value','?')}: {e.get('event_type','?')}"
            for e in (self.memory.get_timeline(168) if MEMORY else [])[:15]
        ) or "No timeline"

        result = ai_json(
            CROSS_CASE_PROMPT.format(
                cases    = threats_txt,
                entities = entities_txt,
                timeline = timeline_txt,
            ),
            max_tokens=1000
        )

        insights = []
        narrative = top_insight = ""

        if result:
            narrative   = result.get("narrative","")
            top_insight = result.get("top_insight","")
            for conn_item in result.get("cross_case_connections",[]):
                pattern = conn_item.get("pattern","")
                if not pattern: continue
                entities = conn_item.get("entities",[])
                insights.append({
                    "type":        "cross_case_link",
                    "title":       f"Cross-case: {pattern[:80]}",
                    "entities":    entities,
                    "confidence":  conn_item.get("confidence",50)/100,
                    "significance":conn_item.get("significance","medium"),
                    "action":      "Cross-reference cases and verify",
                })
                if MEMORY and len(entities) >= 2:
                    self.memory.remember_relationship(
                        entities[0], entities[1], "cross_case_link",
                        strength=conn_item.get("confidence",50)/100,
                        evidence=pattern[:200]
                    )
            for threat in result.get("emerging_threats",[]):
                insights.append({
                    "type":        "emerging_threat",
                    "title":       f"Emerging: {threat.get('threat','')[:80]}",
                    "confidence":  threat.get("confidence",50)/100,
                    "significance":threat.get("urgency","medium"),
                    "action":      f"Investigate: {threat.get('threat','')}",
                })

        return insights, narrative, top_insight


# ── Tool Dreamer ───────────────────────────────────────────────────────────────

class ToolDreamer:
    MODULES = [
        "forge_core_ai","forge_learn","forge_meta","forge_llm_pentest",
        "forge_honeypot","forge_monitor","forge_swarm","forge_investigate",
        "forge_detective","forge_sherlock","forge_sherlock_video","forge_geospy",
        "forge_nexus","forge_ghost","forge_arena","forge_hands","forge_embodied",
        "forge_mobile","forge_network","forge_social","forge_memory","forge_dream",
    ]

    def __init__(self, memory):
        self.memory = memory

    def dream_new_tools(self, all_data, insights):
        if not AI_AVAILABLE: return []
        gaps = []
        unresolved = [t for t in all_data.get("threats",[]) if not t.get("resolved")]
        if unresolved:
            gaps.append(f"{len(unresolved)} threats without resolution")
        high_conf = [i for i in insights if i.get("confidence",0) > 0.8]
        if high_conf:
            gaps.append(f"{len(high_conf)} high-confidence patterns found manually")

        result = ai_json(
            TOOL_DREAMER_PROMPT.format(
                modules=", ".join(self.MODULES),
                gaps="\n".join(f"  - {g}" for g in gaps[:5]) or "  None specific"
            ),
            max_tokens=600
        )

        wishes = []
        if result:
            for wish in result.get("tool_wishes",[])[:3]:
                if MEMORY:
                    self.memory.wish_for_tool(
                        wish.get("name","forge_unknown"),
                        wish.get("description",""),
                        wish.get("capability",""),
                        wish.get("priority",5),
                        source="forge_dream"
                    )
                wishes.append(wish)
                rprint(f"  [dim]Wished for: {wish.get('name','')} — {wish.get('description','')[:50]}[/dim]")
        return wishes


# ── Morning Brief ──────────────────────────────────────────────────────────────

BRIEF_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FORGE Morning Brief {date}</title>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Bebas+Neue&display=swap" rel="stylesheet">
<style>
:root{{--bg:#04080f;--panel:#080d1a;--border:#101828;--green:#00ff88;--gd:#005c33;--amber:#ff9500;--red:#ff2244;--dim:#1e2a3a;--text:#7a9ab0;--head:#d0e4f8}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);font-family:'Share Tech Mono',monospace;color:var(--text);padding:32px;max-width:900px;margin:0 auto;line-height:1.7}}
.logo{{font-family:'Bebas Neue';font-size:36px;letter-spacing:10px;color:var(--green);text-shadow:0 0 20px rgba(0,255,136,.3)}}
.date{{font-size:10px;letter-spacing:3px;color:var(--dim);margin:6px 0 16px}}
.tagline{{font-size:11px;color:var(--text);font-style:italic}}
hr{{border:none;border-top:1px solid var(--border);margin:24px 0}}
.sec{{font-size:8px;letter-spacing:4px;color:var(--gd);margin-bottom:12px}}
.narrative{{font-size:13px;color:var(--head);line-height:2;padding:16px;border-left:3px solid var(--gd);background:rgba(0,255,136,.03);margin-bottom:20px;white-space:pre-wrap}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}}
.stat{{background:var(--panel);border:1px solid var(--border);padding:12px;text-align:center}}
.stat-n{{font-family:'Bebas Neue';font-size:30px;color:var(--green);letter-spacing:2px}}
.stat-l{{font-size:8px;letter-spacing:2px;color:var(--dim);margin-top:2px}}
.insight{{border:1px solid var(--border);padding:14px;margin-bottom:10px;position:relative}}
.insight.critical{{border-left:4px solid var(--red)}}
.insight.high{{border-left:4px solid rgba(255,34,68,.5)}}
.insight.medium{{border-left:4px solid var(--amber)}}
.insight.low{{border-left:4px solid var(--dim)}}
.it{{font-size:12px;color:var(--head);margin-bottom:6px}}
.id{{font-size:10px;color:var(--text);line-height:1.6}}
.ia{{font-size:9px;color:var(--green);margin-top:8px;letter-spacing:1px}}
.cb{{position:absolute;top:12px;right:12px;font-size:8px;color:var(--dim)}}
.wish{{background:var(--panel);border:1px solid var(--border);padding:12px;margin-bottom:8px}}
.wn{{font-size:11px;color:var(--amber);margin-bottom:4px}}
.wd{{font-size:10px;color:var(--text)}}
ul.actions{{list-style:none}}
ul.actions li{{padding:8px 0;border-bottom:1px solid var(--border);font-size:11px;color:var(--head)}}
ul.actions li::before{{content:"-> ";color:var(--green)}}
.footer{{border-top:1px solid var(--border);padding-top:16px;margin-top:32px;font-size:9px;color:var(--dim)}}
</style>
</head>
<body>
<div class="logo">FORGE BRIEF</div>
<div class="date">MORNING INTELLIGENCE REPORT · {date} · {time}</div>
<div class="tagline">While you slept, FORGE was thinking.</div>
<hr>
<div class="sec">OVERNIGHT NARRATIVE</div>
<div class="narrative">{narrative}</div>
<div class="stats">
  <div class="stat"><div class="stat-n">{total_insights}</div><div class="stat-l">INSIGHTS</div></div>
  <div class="stat"><div class="stat-n">{entities}</div><div class="stat-l">ENTITIES</div></div>
  <div class="stat"><div class="stat-n">{sources}</div><div class="stat-l">SOURCES</div></div>
  <div class="stat"><div class="stat-n">{duration}</div><div class="stat-l">MINUTES</div></div>
</div>
<div class="sec">FINDINGS — RANKED BY SIGNIFICANCE</div>
{insights_html}
{wishes_html}
<hr>
<div class="sec">RECOMMENDED ACTIONS</div>
<ul class="actions">{actions_html}</ul>
<div class="footer">FORGE DREAM ENGINE · Session {session_id} · {duration}min · {date}</div>
</body>
</html>"""

class MorningBrief:
    def __init__(self, memory):
        self.memory = memory

    def generate(self, session_id, all_data, all_insights, narrative, top_insight, tool_wishes, start_time):
        duration_m = max(1, int(time.time()-start_time)//60)
        sig_order  = {"critical":0,"high":1,"medium":2,"low":3}
        sorted_ins = sorted(all_insights,
            key=lambda x:(sig_order.get(x.get("significance","low"),3),-x.get("confidence",0)))

        if not narrative and AI_AVAILABLE:
            findings_txt = "\n".join(
                f"- [{i.get('significance','?').upper()}] {i.get('title','')}"
                for i in sorted_ins[:10]
            )
            narrative = ai_call(
                MORNING_BRIEF_PROMPT.format(
                    findings=f"{findings_txt}\nTop: {top_insight}\n"
                            f"Duration: {duration_m}min\nSources: {len(all_data.get('sources',[]))}"
                ),
                max_tokens=600
            )
        if not narrative:
            narrative = (
                f"FORGE completed overnight analysis in {duration_m} minutes. "
                f"Found {len(all_insights)} insights across {len(all_data.get('sources',[]))} sources. "
                f"Top finding: {top_insight or 'No critical findings.'}"
            )

        insights_html = "".join(f"""
<div class="insight {i.get('significance','low')}">
  <div class="cb">{i.get('confidence',0):.0%}</div>
  <div class="it">{i.get('title','')[:120]}</div>
  {f'<div class="id">{str(i.get("detail",i.get("hypothesis","")) or "")[:200]}</div>' if i.get("detail") or i.get("hypothesis") else ""}
  <div class="ia">-> ACTION: {i.get("action","Investigate")[:100]}</div>
</div>""" for i in sorted_ins[:12])

        wishes_html = ""
        if tool_wishes:
            items = "".join(f"""
<div class="wish">
  <div class="wn">Tool: {w.get('name','')} (priority {w.get('priority',5)}/10)</div>
  <div class="wd">{w.get('description','')} — {w.get('why_now','')[:100]}</div>
</div>""" for w in tool_wishes[:3])
            wishes_html = f'<hr><div class="sec">TOOLS FORGE WISHES IT HAD</div>{items}'

        actions = list(dict.fromkeys(
            i.get("action","") for i in sorted_ins if i.get("action")
        ))[:8] or ["Review high-risk entities", "Verify cross-module findings"]
        actions_html = "".join(f"<li>{a}</li>" for a in actions)

        mem_stats  = self.memory.stats() if MEMORY else {}
        html = BRIEF_HTML.format(
            date          = datetime.now().strftime("%Y-%m-%d"),
            time          = datetime.now().strftime("%H:%M"),
            narrative     = narrative,
            total_insights= len(all_insights),
            entities      = mem_stats.get("total_entities", len(all_data.get("entities",[]))),
            sources       = len(all_data.get("sources",[])),
            duration      = duration_m,
            insights_html = insights_html or "<div style='color:var(--dim)'>No insights this session.</div>",
            wishes_html   = wishes_html,
            actions_html  = actions_html,
            session_id    = session_id,
        )

        brief_path = BRIEFS_DIR / f"brief_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
        brief_path.write_text(html)

        if MEMORY:
            self.memory.save_brief(
                title          = f"Morning Brief {datetime.now().strftime('%Y-%m-%d')}",
                content        = narrative,
                insights_count = len(all_insights),
                top_finding    = top_insight or (sorted_ins[0].get("title","") if sorted_ins else "")
            )

        return str(brief_path), narrative, sorted_ins


# ── Dream Engine ───────────────────────────────────────────────────────────────

class DreamEngine:
    def __init__(self):
        self.memory    = Memory()
        self.harvester = ForgeDataHarvester()
        self.brief_gen = MorningBrief(self.memory)
        self._running  = False

    def dream(self, hours_back=168, silent=False):
        start_time = time.time()
        now        = datetime.now()

        if not silent:
            rprint(f"\n[bold yellow]FORGE DREAM — Starting[/bold yellow]")
            rprint(f"  [dim]{now.strftime('%Y-%m-%d %H:%M:%S')} — last {hours_back//24}d[/dim]\n")

        conn = get_dream_db()
        cur  = conn.execute("INSERT INTO dream_sessions (started,status) VALUES (?,?)",
                           (now.isoformat(),"running"))
        session_id = cur.lastrowid
        conn.commit(); conn.close()

        all_insights = []

        try:
            # Phase 1 — Harvest
            if not silent: rprint("  [yellow]Phase 1:[/yellow] Harvesting data...")
            all_data = self.harvester.harvest_all(hours_back)
            if not silent:
                rprint(f"  [dim]Sources: {', '.join(all_data['sources']) or 'none'}[/dim]")
                rprint(f"  [dim]Threats:{len(all_data['threats'])} Entities:{len(all_data['entities'])} Events:{len(all_data['events'])}[/dim]\n")

            # Phase 2 — Pattern Mine
            if not silent: rprint("  [yellow]Phase 2:[/yellow] Mining patterns...")
            miner = PatternMiner(self.memory, session_id)
            p1 = miner.mine_entity_recurrence(all_data)
            p2 = miner.mine_temporal_patterns(all_data)
            p3 = miner.mine_threat_clusters(all_data)
            pattern_insights = p1 + p2 + p3
            all_insights.extend(pattern_insights)
            if not silent: rprint(f"  [dim]Patterns found: {len(pattern_insights)}[/dim]\n")

            # Phase 3 — Re-Analyze
            if not silent: rprint("  [yellow]Phase 3:[/yellow] Re-analyzing past cases...")
            reanalyzer    = CaseReAnalyzer(self.memory, session_id)
            case_insights = reanalyzer.reanalyze_high_risk(5)
            all_insights.extend(case_insights)
            if not silent: rprint(f"  [dim]Re-analysis insights: {len(case_insights)}[/dim]\n")

            # Phase 4 — Cross-Link
            if not silent: rprint("  [yellow]Phase 4:[/yellow] Cross-case linking...")
            linker = CrossCaseLinker(self.memory, session_id)
            cross_insights, narrative, top_insight = linker.find_cross_links(all_data, pattern_insights)
            all_insights.extend(cross_insights)
            if not silent:
                rprint(f"  [dim]Cross-links: {len(cross_insights)}[/dim]")
                if top_insight: rprint(f"  [bold green]Top finding: {top_insight[:80]}[/bold green]")
                rprint("")

            # Phase 5 — Tool Dream
            if not silent: rprint("  [yellow]Phase 5:[/yellow] Dreaming new tools...")
            tool_dreamer = ToolDreamer(self.memory)
            tool_wishes  = tool_dreamer.dream_new_tools(all_data, all_insights)
            if not silent: rprint(f"  [dim]Tool wishes: {len(tool_wishes)}[/dim]\n")

            # Phase 6 — Save
            if not silent: rprint("  [yellow]Phase 6:[/yellow] Writing to memory...")
            miner.save_insights(session_id)

            # Phase 7 — Morning Brief
            if not silent: rprint("  [yellow]Phase 7:[/yellow] Writing morning brief...")
            brief_path, brief_narrative, sorted_insights = self.brief_gen.generate(
                session_id, all_data, all_insights,
                narrative, top_insight, tool_wishes, start_time
            )

            duration = int(time.time() - start_time)
            conn = get_dream_db()
            conn.execute("""
                UPDATE dream_sessions SET
                    completed=?,duration_s=?,insights=?,top_finding=?,brief_path=?,status='completed'
                WHERE id=?""",
                (datetime.now().isoformat(), duration, len(all_insights),
                 (top_insight or (sorted_insights[0].get("title","") if sorted_insights else ""))[:200],
                 brief_path, session_id)
            )
            conn.commit(); conn.close()

            if not silent:
                rprint(f"\n[bold green]DREAM COMPLETE[/bold green]")
                rprint(f"  Duration:  {duration//60}m {duration%60}s")
                rprint(f"  Insights:  {len(all_insights)}")
                rprint(f"  Brief:     {brief_path}\n")
                top_txt = top_insight or (sorted_insights[0].get("title","No critical findings.") if sorted_insights else "No insights this session.")
                if RICH:
                    rprint(Panel(top_txt[:400], border_style="green", title="Top Insight"))
                else:
                    rprint(f"  Top insight: {top_txt[:200]}")

                # Push notification for critical findings
                critical = [i for i in all_insights if i.get("significance")=="critical"]
                if critical:
                    self._push(critical[0])

            return brief_path, all_insights

        except Exception as e:
            conn = get_dream_db()
            conn.execute("UPDATE dream_sessions SET status='failed' WHERE id=?", (session_id,))
            conn.commit(); conn.close()
            rprint(f"  [red]Dream error: {e}[/red]")
            import traceback; traceback.print_exc()
            return None, []

    def _push(self, insight):
        try:
            import urllib.request
            title = f"FORGE CRITICAL: {insight.get('title','Alert')[:50]}"
            msg   = f"Confidence: {insight.get('confidence',0):.0%}. Open morning brief."
            req   = urllib.request.Request(
                "https://ntfy.sh/forge_intelligence",
                data=msg.encode(),
                headers={"Title":title,"Priority":"urgent","Tags":"rotating_light"},
                method="POST"
            )
            urllib.request.urlopen(req, timeout=5)
            rprint("  [green]Push alert sent[/green]")
        except: pass

    def watch(self, dream_hour=3):
        self._running = True
        rprint(f"\n[bold yellow]FORGE DREAM — Watch Mode (nightly at {dream_hour:02d}:00)[/bold yellow]")
        rprint("  [dim]Ctrl+C to stop[/dim]\n")
        last_dream_date = None
        try:
            while self._running:
                now = datetime.now()
                if now.hour == dream_hour and last_dream_date != now.date():
                    rprint(f"\n[yellow]Starting nightly dream at {now.strftime('%H:%M')}...[/yellow]")
                    self.dream(hours_back=24)
                    last_dream_date = now.date()
                else:
                    next_dream = now.replace(hour=dream_hour, minute=0, second=0)
                    if next_dream <= now: next_dream += timedelta(days=1)
                    rem = next_dream - now
                    rprint(
                        f"  [dim]Next dream in {rem.seconds//3600}h {(rem.seconds%3600)//60}m[/dim]",
                        end="\r"
                    )
                time.sleep(60)
        except KeyboardInterrupt:
            rprint("\n\n[dim]Dream watch stopped.[/dim]")

    def show_brief(self):
        conn    = get_dream_db()
        session = conn.execute(
            "SELECT * FROM dream_sessions WHERE status='completed' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        insights = conn.execute(
            "SELECT * FROM insights WHERE session_id=? ORDER BY confidence DESC",
            (session["id"],)
        ).fetchall() if session else []
        conn.close()

        if not session:
            rprint("[dim]No dream sessions found. Run without args to start.[/dim]")
            return

        rprint(f"\n[bold]Dream Session #{session['id']}[/bold]")
        rprint(f"  Started:  {session['started'][:19]}")
        rprint(f"  Duration: {(session.get('duration_s',0) or 0)//60}m")
        rprint(f"  Insights: {session['insights']}")

        if session.get("top_finding"):
            rprint(Panel(session["top_finding"][:400], border_style="green", title="Top Finding"))

        for ins in insights[:10]:
            sig   = ins["significance"]
            color = {"critical":"red bold","high":"red","medium":"yellow","low":"dim"}.get(sig,"dim")
            rprint(f"  [{color}][{sig.upper()}][/{color}] {ins['title'][:80]}")

        if session.get("brief_path") and Path(session["brief_path"]).exists():
            rprint(f"\n  [dim]HTML: {session['brief_path']}[/dim]")


# ── API Server ─────────────────────────────────────────────────────────────────

def start_server(port=7349):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse
    engine = DreamEngine()

    class DreamAPI(BaseHTTPRequestHandler):
        def log_message(self,*a): pass
        def do_OPTIONS(self):
            self.send_response(200); self._cors(); self.end_headers()
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin","*")
            self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
            self.send_header("Access-Control-Allow-Headers","Content-Type")
        def _json(self,d,c=200):
            b=json.dumps(d,default=str).encode()
            self.send_response(c); self._cors()
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",len(b))
            self.end_headers(); self.wfile.write(b)
        def _html(self,h):
            b=h.encode()
            self.send_response(200); self._cors()
            self.send_header("Content-Type","text/html")
            self.send_header("Content-Length",len(b))
            self.end_headers(); self.wfile.write(b)
        def _body(self):
            n=int(self.headers.get("Content-Length",0))
            return json.loads(self.rfile.read(n)) if n else {}

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/","/brief"):
                db   = get_dream_db()
                last = db.execute(
                    "SELECT * FROM dream_sessions WHERE status='completed' ORDER BY id DESC LIMIT 1"
                ).fetchone()
                db.close()
                if last and last.get("brief_path") and Path(last["brief_path"]).exists():
                    self._html(Path(last["brief_path"]).read_text()); return
                self._html("<html><body style='background:#04080f;color:#7a9ab0;font-family:monospace;padding:40px'>"
                          "<h1 style='color:#00ff88'>FORGE DREAM</h1>"
                          "<p>No brief yet. POST /api/dream to start.</p></body></html>")
            elif path == "/api/status":
                db   = get_dream_db()
                last = db.execute("SELECT * FROM dream_sessions ORDER BY id DESC LIMIT 1").fetchone()
                tot  = db.execute("SELECT COUNT(*) FROM dream_sessions").fetchone()[0]
                toti = db.execute("SELECT COUNT(*) FROM insights").fetchone()[0]
                db.close()
                self._json({"status":"online","ai":AI_AVAILABLE,"memory":MEMORY,
                           "total_sessions":tot,"total_insights":toti,
                           "last_session":dict(last) if last else None})
            elif path == "/api/insights":
                db   = get_dream_db()
                rows = db.execute("SELECT * FROM insights ORDER BY confidence DESC LIMIT 50").fetchall()
                db.close()
                self._json({"insights":[dict(r) for r in rows]})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            if path == "/api/dream":
                hours = int(body.get("hours_back",168))
                threading.Thread(target=lambda: engine.dream(hours_back=hours,silent=True), daemon=True).start()
                self._json({"ok":True,"message":f"Dream started — last {hours//24}d"})
            elif path == "/api/dream/sync":
                hours      = int(body.get("hours_back",168))
                bp, ins    = engine.dream(hours_back=hours,silent=True)
                self._json({"ok":True,"brief_path":bp,"insights":len(ins),
                           "top":ins[0].get("title","") if ins else ""})
            else:
                self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),DreamAPI)
    rprint(f"\n  [bold yellow]FORGE DREAM[/bold yellow]")
    rprint(f"  [green]Brief UI: http://localhost:{port}[/green]")
    rprint(f"  [green]API:      http://localhost:{port}/api/status[/green]")
    server.serve_forever()


# ── Banner + Main ──────────────────────────────────────────────────────────────

BANNER = """
[yellow]
  ██████╗ ██████╗ ███████╗ █████╗ ███╗   ███╗
  ██╔══██╗██╔══██╗██╔════╝██╔══██╗████╗ ████║
  ██║  ██║██████╔╝█████╗  ███████║██╔████╔██║
  ██║  ██║██╔══██╗██╔══╝  ██╔══██║██║╚██╔╝██║
  ██████╔╝██║  ██║███████╗██║  ██║██║ ╚═╝ ██║
  ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝
[/yellow]
[bold]  FORGE DREAM — Autonomous Night Intelligence[/bold]
[dim]  FORGE thinks while you sleep.[/dim]
"""

def main():
    rprint(BANNER)
    rprint(f"  [dim]AI:     {'OK' if AI_AVAILABLE else 'pip install anthropic'}[/dim]")
    rprint(f"  [dim]Memory: {'OK' if MEMORY else 'forge_memory.py not found'}[/dim]\n")

    engine = DreamEngine()

    if "--watch" in sys.argv:
        idx  = sys.argv.index("--watch")
        hour = int(sys.argv[idx+1]) if idx+1 < len(sys.argv) and sys.argv[idx+1].isdigit() else 3
        engine.watch(dream_hour=hour)
    elif "--brief" in sys.argv:
        engine.show_brief()
    elif "--server" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7349
        start_server(port)
    elif "--schedule" in sys.argv:
        script = Path(__file__).absolute()
        rprint(f"  Add to crontab -e:")
        rprint(f"  [green]0 3 * * * cd {script.parent} && python3 {script} --silent >> forge_dream/dream.log 2>&1[/green]")
    elif "--silent" in sys.argv:
        engine.dream(hours_back=24, silent=True)
    else:
        hours = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 168
        engine.dream(hours_back=hours)

if __name__ == "__main__":
    main()
