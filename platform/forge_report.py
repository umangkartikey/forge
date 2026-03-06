#!/usr/bin/env python3
"""
FORGE REPORT — Intelligence Report Generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Takes any FORGE case JSON and generates a stunning,
professional HTML intelligence report. Shareable. Printable.

Usage:
  python forge_report.py --case forge_nexus/cases/abc123.json
  python forge_report.py --all             # all cases in forge_nexus/cases/
  python forge_report.py --output ./reports/
  python forge_report.py --case <json> --open  # auto-open in browser
"""

import sys, os, re, json, time, hashlib
from pathlib import Path
from datetime import datetime

# ── AI ────────────────────────────────────────────────────────────────────────
try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True

    def ai_call(prompt, system="", max_tokens=2000):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or "You are a professional intelligence analyst.",
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text

except ImportError:
    AI_AVAILABLE = False
    def ai_call(p, s="", m=2000): return ""

BASE     = Path(__file__).parent
OUT_DIR  = BASE / "forge_reports"
OUT_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# 📄 HTML REPORT TEMPLATE
# ══════════════════════════════════════════════════════════════════════════════

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>FORGE Report — {title}</title>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=IBM+Plex+Mono:wght@300;400;600&family=IBM+Plex+Sans:ital,wght@0,300;0,400;0,600;1,400&display=swap" rel="stylesheet">
<style>
:root {{
  --bg:    #08060e;
  --card:  #0f0d18;
  --border:#2a2640;
  --gold:  #c89b3c;
  --red:   #cc2200;
  --blue:  #2266ff;
  --green: #00cc66;
  --dim:   #444;
  --text:  #d0cce0;
  --head:  #f0ecff;
}}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:var(--bg); color:var(--text); font-family:'IBM Plex Sans',sans-serif; }}

.report-wrap {{ max-width:1100px; margin:0 auto; padding:40px 24px 80px; }}

/* Header */
.rpt-header {{
  border-bottom:2px solid var(--gold);
  padding-bottom:24px; margin-bottom:40px;
  display:flex; align-items:flex-start; justify-content:space-between;
}}
.rpt-title {{
  font-family:'Bebas Neue',sans-serif;
  font-size:42px; letter-spacing:4px; color:var(--gold);
  line-height:1;
}}
.rpt-sub {{
  font-family:'IBM Plex Mono',monospace;
  font-size:11px; letter-spacing:3px; color:var(--dim);
  margin-top:6px;
}}
.rpt-meta {{
  text-align:right;
  font-family:'IBM Plex Mono',monospace; font-size:10px;
  color:var(--dim); line-height:2;
}}
.rpt-meta span {{ color:var(--gold); }}

/* Confidence big */
.conf-hero {{
  background:var(--card); border:1px solid var(--border);
  border-left:4px solid var(--gold);
  padding:24px 30px; margin-bottom:32px;
  display:flex; align-items:center; gap:32px;
}}
.conf-num {{
  font-family:'Bebas Neue',sans-serif;
  font-size:80px; color:var(--gold); line-height:1;
  text-shadow: 0 0 40px rgba(200,155,60,0.3);
}}
.conf-label {{
  font-family:'IBM Plex Mono',monospace;
  font-size:9px; letter-spacing:3px; color:var(--dim);
  margin-bottom:6px;
}}
.conf-verdict {{
  font-family:'IBM Plex Sans',sans-serif;
  font-size:17px; color:var(--head); line-height:1.6;
  font-style:italic; max-width:600px;
}}
.risk-badge {{
  display:inline-block;
  font-family:'IBM Plex Mono',monospace;
  font-size:10px; letter-spacing:3px; font-weight:600;
  padding:4px 12px; margin-top:10px;
  text-transform:uppercase;
}}
.risk-critical {{ background:rgba(204,34,0,0.25); color:#ff4422; border:1px solid #cc2200; }}
.risk-high     {{ background:rgba(204,34,0,0.15); color:#ff6644; border:1px solid #993300; }}
.risk-medium   {{ background:rgba(200,155,60,0.15); color:#c89b3c; border:1px solid #6b5020; }}
.risk-low      {{ background:rgba(0,204,102,0.1); color:#00cc66; border:1px solid #006633; }}

/* Sections */
.section {{ margin-bottom:36px; }}
.section-title {{
  font-family:'Bebas Neue',sans-serif;
  font-size:14px; letter-spacing:5px; color:var(--gold);
  border-bottom:1px solid var(--border); padding-bottom:8px; margin-bottom:20px;
}}

/* Cards */
.card-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; }}
.card {{
  background:var(--card); border:1px solid var(--border);
  padding:18px 20px;
}}
.card-type {{
  font-family:'IBM Plex Mono',monospace; font-size:8px;
  letter-spacing:3px; color:var(--dim); margin-bottom:8px;
  text-transform:uppercase;
}}
.card-title {{
  font-family:'IBM Plex Sans',sans-serif; font-weight:600;
  font-size:14px; color:var(--head); margin-bottom:8px; line-height:1.4;
}}
.card-body {{
  font-family:'IBM Plex Sans',sans-serif; font-size:13px;
  color:var(--text); line-height:1.6; font-style:italic;
}}
.card-conf {{
  font-family:'IBM Plex Mono',monospace; font-size:10px;
  color:var(--gold); margin-top:10px; font-weight:600;
}}

/* Timeline */
.timeline {{ position:relative; padding-left:30px; }}
.timeline::before {{
  content:''; position:absolute; left:8px; top:0; bottom:0;
  width:2px; background:linear-gradient(var(--gold), transparent);
}}
.tl-item {{ position:relative; margin-bottom:24px; }}
.tl-dot {{
  position:absolute; left:-26px; top:5px;
  width:10px; height:10px; border-radius:50%;
  border:2px solid var(--gold); background:var(--bg);
}}
.tl-dot.confirmed {{ background:var(--green); border-color:var(--green); }}
.tl-dot.probable  {{ background:var(--gold);  border-color:var(--gold); }}
.tl-dot.inferred  {{ background:var(--dim);   border-color:var(--dim); }}
.tl-dot.impossible{{ background:var(--red);   border-color:var(--red); }}
.tl-time {{
  font-family:'IBM Plex Mono',monospace; font-size:10px;
  color:var(--blue); letter-spacing:1px; margin-bottom:4px;
}}
.tl-event {{
  font-family:'IBM Plex Sans',sans-serif; font-size:14px;
  color:var(--text); line-height:1.5;
}}
.tl-source {{
  font-family:'IBM Plex Mono',monospace; font-size:9px;
  color:var(--dim); margin-top:4px; letter-spacing:1px;
}}
.tl-badge {{
  display:inline-block; font-family:'IBM Plex Mono',monospace;
  font-size:8px; letter-spacing:2px; padding:2px 8px; margin-left:8px;
  text-transform:uppercase; vertical-align:middle;
}}
.badge-confirmed  {{ color:var(--green); border:1px solid rgba(0,204,102,0.4); }}
.badge-probable   {{ color:var(--gold);  border:1px solid rgba(200,155,60,0.4); }}
.badge-inferred   {{ color:var(--dim);   border:1px solid rgba(68,68,68,0.4); }}
.badge-impossible {{ color:var(--red);   border:1px solid rgba(204,34,0,0.4); }}

/* Suspect table */
.suspect-row {{
  display:flex; align-items:center; gap:16px;
  border-bottom:1px solid var(--border); padding:14px 0;
}}
.suspect-rank {{
  font-family:'Bebas Neue',sans-serif; font-size:32px;
  color:var(--dim); width:32px; flex-shrink:0;
}}
.suspect-rank.rank-1 {{ color:var(--red); }}
.suspect-name {{
  font-family:'IBM Plex Sans',sans-serif; font-weight:600;
  font-size:15px; color:var(--head); flex:1;
}}
.suspect-reason {{
  font-family:'IBM Plex Sans',sans-serif; font-size:12px;
  color:var(--dim); font-style:italic;
}}
.suspect-score {{
  font-family:'IBM Plex Mono',monospace; font-size:22px;
  font-weight:600; color:var(--gold); margin-left:auto;
}}
.suspect-verdict {{
  font-family:'IBM Plex Mono',monospace; font-size:8px;
  letter-spacing:2px; text-transform:uppercase; padding:3px 8px;
}}
.sv-primary  {{ color:var(--red);  border:1px solid rgba(204,34,0,0.4); }}
.sv-interest {{ color:var(--gold); border:1px solid rgba(200,155,60,0.4); }}
.sv-low      {{ color:var(--dim);  border:1px solid var(--border); }}

/* Connection row */
.conn-row {{
  background:var(--card); border:1px solid var(--border);
  border-left:3px solid var(--blue);
  padding:14px 18px; margin-bottom:10px;
}}
.conn-tools {{
  font-family:'IBM Plex Mono',monospace; font-size:9px;
  letter-spacing:3px; color:var(--blue); margin-bottom:6px;
}}
.conn-insight {{
  font-family:'IBM Plex Sans',sans-serif; font-size:14px;
  color:var(--text); line-height:1.5; font-style:italic;
}}
.conn-sig {{
  display:inline-block; font-family:'IBM Plex Mono',monospace;
  font-size:8px; letter-spacing:2px; padding:2px 8px; margin-top:8px;
}}
.sig-high   {{ color:var(--red);   border:1px solid rgba(204,34,0,0.4); }}
.sig-medium {{ color:var(--gold);  border:1px solid rgba(200,155,60,0.4); }}
.sig-low    {{ color:var(--dim);   border:1px solid var(--border); }}

/* Deduction chain */
.chain-wrap {{
  background:var(--card); border:1px solid var(--border);
  border-top:2px solid var(--gold); padding:18px; margin-bottom:12px;
}}
.chain-title {{
  font-family:'IBM Plex Sans',sans-serif; font-weight:600;
  font-size:14px; color:var(--head); margin-bottom:12px;
}}
.chain-step {{
  font-family:'IBM Plex Mono',monospace; font-size:11px;
  color:#8899bb; padding:4px 0 4px 16px;
  border-left:1px solid rgba(200,155,60,0.3);
  margin:4px 0;
}}
.chain-arrow {{ color:var(--gold); margin-right:6px; }}
.chain-conclusion {{ color:var(--gold); font-weight:600; }}

/* OSINT grid */
.osint-cat {{ margin-bottom:20px; }}
.osint-cat-title {{
  font-family:'IBM Plex Mono',monospace; font-size:9px;
  letter-spacing:3px; color:var(--dim); margin-bottom:10px;
  text-transform:uppercase;
}}
.osint-item {{
  display:flex; gap:12px; padding:8px 0;
  border-bottom:1px solid rgba(42,38,64,0.5);
  align-items:baseline;
}}
.osint-key {{
  font-family:'IBM Plex Mono',monospace; font-size:10px;
  color:var(--dim); width:160px; flex-shrink:0; letter-spacing:1px;
}}
.osint-val {{
  font-family:'IBM Plex Sans',sans-serif; font-size:13px;
  color:var(--text); word-break:break-all;
}}

/* Pipeline log */
.log-line {{
  font-family:'IBM Plex Mono',monospace; font-size:10px;
  padding:4px 0; border-bottom:1px solid rgba(42,38,64,0.3);
  display:flex; gap:10px;
}}
.log-ts   {{ color:var(--dim); flex-shrink:0; }}
.log-tool {{ color:var(--gold); width:80px; flex-shrink:0; }}
.log-msg  {{ color:var(--text); }}
.log-info    {{ }} 
.log-success {{ color:var(--green); }}
.log-warning {{ color:var(--gold); }}
.log-error   {{ color:var(--red); }}

/* Footer */
.rpt-footer {{
  margin-top:60px; padding-top:20px;
  border-top:1px solid var(--border);
  font-family:'IBM Plex Mono',monospace; font-size:9px;
  color:var(--dim); letter-spacing:2px;
  display:flex; justify-content:space-between;
}}

/* Print */
@media print {{
  body {{ background:#fff; color:#000; }}
  .rpt-header, .conf-hero, .card, .chain-wrap, .conn-row {{ border-color:#ccc; background:#f8f8f8; }}
  .rpt-title, .conf-num {{ color:#1a1209; }}
}}
</style>
</head>
<body>
<div class="report-wrap">

<!-- HEADER -->
<div class="rpt-header">
  <div>
    <div class="rpt-title">FORGE NEXUS</div>
    <div class="rpt-sub">INTELLIGENCE REPORT — {case_id}</div>
    <div style="font-family:'IBM Plex Sans',sans-serif;font-size:18px;color:#d0cce0;margin-top:8px;font-style:italic">{target}</div>
  </div>
  <div class="rpt-meta">
    <div>Generated <span>{date}</span></div>
    <div>Case ID <span>{case_id}</span></div>
    <div>Tools Run <span>{tools_run}</span></div>
    <div>Evidence <span>{evidence_count}</span></div>
  </div>
</div>

<!-- CONFIDENCE HERO -->
<div class="conf-hero">
  <div class="conf-num">{confidence}%</div>
  <div>
    <div class="conf-label">OVERALL CONFIDENCE</div>
    <div class="conf-verdict">{verdict_summary}</div>
    <span class="risk-badge risk-{risk_level}">{risk_level} risk</span>
  </div>
</div>

{executive_summary_section}
{osint_section}
{timeline_section}
{suspects_section}
{deductions_section}
{connections_section}
{pipeline_log_section}

<!-- FOOTER -->
<div class="rpt-footer">
  <span>FORGE NEXUS — Intelligence Platform — github.com/umangkartikey/forge</span>
  <span>{date}</span>
</div>

</div>
</body>
</html>"""

# ══════════════════════════════════════════════════════════════════════════════
# 🏗️ SECTION BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def build_executive_summary(case, ai_summary=""):
    """Build executive summary section."""
    if not ai_summary and AI_AVAILABLE:
        findings_txt = json.dumps({
            "target":      case.get("target",""),
            "confidence":  case.get("confidence",0),
            "verdict":     str(case.get("verdict",""))[:300],
            "theories":    case.get("theories",[])[:2],
            "connections": case.get("connections",[])[:3],
        }, default=str)
        ai_summary = ai_call(
            f"Write a 3-sentence executive summary for this intelligence report:\n{findings_txt}",
            "You are a professional intelligence analyst. Be precise and concise.",
            max_tokens=300
        )

    if not ai_summary:
        ai_summary = f"Intelligence gathered on target {case.get('target','')}. Analysis complete."

    return f"""
<div class="section">
  <div class="section-title">Executive Summary</div>
  <div style="font-family:'IBM Plex Sans',sans-serif;font-size:16px;color:#d0cce0;
       line-height:1.8;font-style:italic;padding:20px;background:var(--card);
       border-left:4px solid var(--gold);">
    {ai_summary}
  </div>
</div>"""

def build_osint_section(case):
    findings = case.get("osint", {}).get("findings", {})
    if not findings:
        return ""

    cats_html = ""
    for cat, items in findings.items():
        if not items: continue
        items_html = ""
        for key, val in items.items():
            val_str = str(val)[:200] if not isinstance(val, dict) else json.dumps(val)[:200]
            items_html += f"""
          <div class="osint-item">
            <div class="osint-key">{key}</div>
            <div class="osint-val">{val_str}</div>
          </div>"""
        cats_html += f"""
        <div class="osint-cat">
          <div class="osint-cat-title">{cat}</div>
          {items_html}
        </div>"""

    return f"""
<div class="section">
  <div class="section-title">OSINT Intelligence</div>
  {cats_html}
</div>"""

def build_timeline_section(case):
    timeline = case.get("timeline", [])
    if not timeline:
        return ""

    items_html = ""
    for ev in timeline[:15]:
        t    = ev.get("type", "inferred")
        conf = ev.get("confidence", 70)
        items_html += f"""
      <div class="tl-item">
        <div class="tl-dot {t}"></div>
        <div class="tl-time">{ev.get('time','?')}</div>
        <div class="tl-event">
          {ev.get('event','')}
          <span class="tl-badge badge-{t}">{t}</span>
        </div>
        <div class="tl-source">{ev.get('source','?')} — {conf}% confidence</div>
      </div>"""

    return f"""
<div class="section">
  <div class="section-title">Timeline of Events</div>
  <div class="timeline">
    {items_html}
  </div>
</div>"""

def build_suspects_section(case):
    suspects = case.get("suspects", {})
    theories = case.get("theories", [])

    rows_html = ""
    # From suspects dict
    for i, (name, data) in enumerate(suspects.items()):
        verdict   = data.get("relationship", data.get("type", "person of interest"))
        sv_class  = "sv-primary" if i == 0 else "sv-interest"
        rank_class= "rank-1" if i == 0 else ""
        rows_html += f"""
      <div class="suspect-row">
        <div class="suspect-rank {rank_class}">{i+1}</div>
        <div>
          <div class="suspect-name">{name}</div>
          <div class="suspect-reason">{data.get('source','OSINT')} — conf: {data.get('confidence',50)}%</div>
        </div>
        <span class="suspect-verdict {sv_class}">{verdict}</span>
        <div class="suspect-score">{data.get('confidence',50)}</div>
      </div>"""

    # From theories
    theories_html = ""
    for i, theory in enumerate(theories[:3]):
        prob = theory.get("probability", 0)
        bar_w= min(100, int(prob))
        theories_html += f"""
      <div style="margin-bottom:16px">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px">
          <span style="font-family:'IBM Plex Mono',monospace;font-size:11px;color:#d0cce0">
            {theory.get('name', f'Theory {i+1}')}
          </span>
          <span style="font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--gold)">{prob}%</span>
        </div>
        <div style="background:rgba(42,38,64,0.5);height:4px;border-radius:2px">
          <div style="background:var(--gold);height:4px;width:{bar_w}%;border-radius:2px;transition:width 1s"></div>
        </div>
        <div style="font-family:'IBM Plex Sans',sans-serif;font-size:12px;color:var(--dim);
             margin-top:4px;font-style:italic">{theory.get('summary','')[:120]}</div>
      </div>"""

    if not rows_html and not theories_html:
        return ""

    return f"""
<div class="section">
  <div class="section-title">Entities & Theories</div>
  {'<div>' + rows_html + '</div>' if rows_html else ''}
  {('<div style="margin-top:24px"><div style="font-family:IBM Plex Mono,monospace;font-size:9px;letter-spacing:3px;color:var(--dim);margin-bottom:16px">RANKED THEORIES</div>' + theories_html + '</div>') if theories_html else ''}
</div>"""

def build_deductions_section(case):
    observations = case.get("observations", [])
    deductions   = case.get("deductions", [])

    if not observations and not deductions:
        return ""

    chains_html = ""
    for i, chain_text in enumerate((deductions or observations)[:3]):
        # Parse into steps if contains arrows
        steps = [s.strip() for s in str(chain_text)[:800].split("→") if s.strip()]
        if len(steps) > 1:
            steps_html = "".join(
                f'<div class="chain-step {"chain-conclusion" if j==len(steps)-1 else ""}">'
                f'{"" if j==0 else "<span class=\"chain-arrow\">→</span>"}{s}</div>'
                for j, s in enumerate(steps[:6])
            )
        else:
            steps_html = f'<div class="chain-step">{str(chain_text)[:400]}</div>'

        chains_html += f"""
      <div class="chain-wrap">
        <div class="chain-title">Deduction Chain #{i+1}</div>
        {steps_html}
      </div>"""

    return f"""
<div class="section">
  <div class="section-title">Deduction Chains (Sherlock)</div>
  {chains_html}
</div>"""

def build_connections_section(case):
    connections = case.get("connections", [])
    if not connections:
        return ""

    rows_html = ""
    for conn in connections[:6]:
        tool_a = conn.get("tool_a","")
        tool_b = conn.get("tool_b","")
        tools  = f"{tool_a} + {tool_b}" if tool_a and tool_b else "CROSS-TOOL"
        sig    = conn.get("significance","medium").lower()
        rows_html += f"""
      <div class="conn-row">
        <div class="conn-tools">{tools.upper()} — NEXUS CONNECTION</div>
        <div class="conn-insight">{conn.get('insight','')}</div>
        <span class="conn-sig sig-{sig}">{sig.upper()} SIGNIFICANCE</span>
      </div>"""

    return f"""
<div class="section">
  <div class="section-title">Cross-Tool Connections (NEXUS)</div>
  {rows_html}
</div>"""

def build_pipeline_log_section(case):
    log = case.get("pipeline_log", [])
    if not log:
        return ""

    rows_html = ""
    for entry in log[-20:]:
        level  = entry.get("level","info")
        rows_html += f"""
      <div class="log-line log-{level}">
        <div class="log-ts">{str(entry.get('ts',''))[:19]}</div>
        <div class="log-tool">[{entry.get('tool','?').upper()}]</div>
        <div class="log-msg">{entry.get('message','')[:120]}</div>
      </div>"""

    return f"""
<div class="section">
  <div class="section-title">Pipeline Log</div>
  <div style="background:var(--card);border:1px solid var(--border);padding:16px;">
    {rows_html}
  </div>
</div>"""

# ══════════════════════════════════════════════════════════════════════════════
# 🎨 REPORT GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def generate_report(case_data, output_dir=None):
    """Generate a complete HTML report from case data."""
    output_dir = Path(output_dir) if output_dir else OUT_DIR
    output_dir.mkdir(exist_ok=True)

    case       = case_data
    case_id    = case.get("case_id", hashlib.md5(str(time.time()).encode()).hexdigest()[:8])
    target     = case.get("target", "Unknown Target")
    confidence = case.get("confidence", 0)
    date       = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Verdict summary
    verdict_obj = case.get("verdict", {})
    if isinstance(verdict_obj, dict):
        verdict_summary = verdict_obj.get("text","")[:200]
    else:
        verdict_summary = str(verdict_obj)[:200]

    if not verdict_summary:
        verdict_summary = f"Intelligence analysis complete for {target}."

    # Risk level
    risk_level = "low"
    if confidence > 80: risk_level = "high"
    elif confidence > 60: risk_level = "medium"

    # Tool run count
    tools_run = sum([
        bool(case.get("osint")),
        bool(case.get("observations")),
        bool(case.get("deductions")),
        bool(case.get("connections")),
        bool(case.get("timeline")),
    ])

    # Evidence count
    evidence_count = (
        sum(len(v) for v in case.get("osint",{}).get("findings",{}).values()) +
        len(case.get("timeline",[])) +
        len(case.get("connections",[]))
    )

    # Build sections
    exec_summary  = build_executive_summary(case)
    osint_section = build_osint_section(case)
    timeline_sec  = build_timeline_section(case)
    suspects_sec  = build_suspects_section(case)
    deductions_sec= build_deductions_section(case)
    connections_sec=build_connections_section(case)
    pipeline_sec  = build_pipeline_log_section(case)

    html = HTML_TEMPLATE.format(
        title                  = target,
        case_id                = case_id,
        target                 = target,
        date                   = date,
        confidence             = confidence,
        verdict_summary        = verdict_summary,
        risk_level             = risk_level,
        tools_run              = tools_run,
        evidence_count         = evidence_count,
        executive_summary_section = exec_summary,
        osint_section          = osint_section,
        timeline_section       = timeline_sec,
        suspects_section       = suspects_sec,
        deductions_section     = deductions_sec,
        connections_section    = connections_sec,
        pipeline_log_section   = pipeline_sec,
    )

    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    fp  = output_dir / f"report_{case_id}_{ts}.html"
    fp.write_text(html)
    return fp, html

def generate_from_file(json_path, output_dir=None, auto_open=False):
    """Load case JSON and generate report."""
    path = Path(json_path)
    if not path.exists():
        print(f"File not found: {json_path}")
        sys.exit(1)

    case = json.loads(path.read_text())
    fp, _ = generate_report(case, output_dir)
    print(f"✅ Report generated: {fp}")

    if auto_open:
        import webbrowser
        webbrowser.open(f"file://{fp.resolve()}")

    return fp

def generate_all(cases_dir=None, output_dir=None):
    """Generate reports for all cases in directory."""
    search_dirs = [
        Path("forge_nexus/cases"),
        Path("forge_detective/cases"),
        Path("forge_sherlock/cases"),
    ]
    if cases_dir:
        search_dirs = [Path(cases_dir)]

    count = 0
    for d in search_dirs:
        if not d.exists(): continue
        for fp in sorted(d.glob("*.json")):
            try:
                case = json.loads(fp.read_text())
                rp, _ = generate_report(case, output_dir)
                print(f"  ✅ {rp.name}")
                count += 1
            except Exception as e:
                print(f"  ❌ {fp.name}: {e}")

    print(f"\nGenerated {count} reports → {output_dir or OUT_DIR}")

def main():
    args  = sys.argv[1:]

    if not args or "--help" in args:
        print("""
forge_report.py — FORGE Intelligence Report Generator

Usage:
  python forge_report.py --case <json_file>   Generate report from case
  python forge_report.py --all                All cases in forge_nexus/cases/
  python forge_report.py --output <dir>       Output directory
  python forge_report.py --open               Auto-open in browser

Examples:
  python forge_report.py --case forge_nexus/cases/abc123.json
  python forge_report.py --all --output ./reports/
""")
        return

    output_dir = None
    if "--output" in args:
        idx        = args.index("--output")
        output_dir = args[idx+1] if idx+1 < len(args) else None

    auto_open = "--open" in args

    if "--all" in args:
        cases_dir = None
        if "--cases" in args:
            idx = args.index("--cases")
            cases_dir = args[idx+1] if idx+1 < len(args) else None
        generate_all(cases_dir, output_dir)
        return

    if "--case" in args:
        idx = args.index("--case")
        fp  = args[idx+1] if idx+1 < len(args) else None
        if fp:
            generate_from_file(fp, output_dir, auto_open)
            return

    # If a JSON file is passed directly
    for arg in args:
        if arg.endswith(".json") and Path(arg).exists():
            generate_from_file(arg, output_dir, auto_open)
            return

    print("Specify --case <file> or --all")

if __name__ == "__main__":
    main()
