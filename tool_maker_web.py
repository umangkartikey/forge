"""
╔══════════════════════════════════════════════════════════════════════╗
║        🛠️   AI Tool-Maker WEB UI  — FULL EDITION                     ║
║   Build · AI2AI · Auto · Chain · Improve · Remix · Test · Web · Export
╚══════════════════════════════════════════════════════════════════════╝

Requirements:
    pip install anthropic flask

Usage:
    python tool_maker_web.py
    Open: http://localhost:5000
"""

from flask import Flask, Response, request, jsonify, send_file, stream_with_context
import anthropic, json, re, sys, shutil, subprocess, zipfile, io
from pathlib import Path
from datetime import datetime
from urllib.request import urlopen, Request as UReq
from urllib.parse import quote_plus

MODEL       = "claude-sonnet-4-6"
TOOLS_DIR   = Path("generated_tools")
REGISTRY    = TOOLS_DIR / "registry.json"
MEMORY_FILE = TOOLS_DIR / "memory.json"
TOOLS_DIR.mkdir(exist_ok=True)

client = anthropic.Anthropic()
app    = Flask(__name__)

# ── Data helpers ──────────────────────────────────────────────────────────────
def load_registry():
    return json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}

def save_registry(reg):
    REGISTRY.write_text(json.dumps(reg, indent=2))

def load_memory():
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text())
    return {"tool_history": [], "insights": [], "preferences": {}, "total_sessions": 0, "user_style": ""}

def save_memory(mem):
    MEMORY_FILE.write_text(json.dumps(mem, indent=2))

def register_tool(name, filepath, description, tags):
    reg = load_registry()
    ex  = reg.get(name, {})
    reg[name] = {
        "file": str(filepath), "description": description, "tags": tags,
        "created": ex.get("created", datetime.now().isoformat()),
        "updated": datetime.now().isoformat(),
        "runs": ex.get("runs", 0), "version": ex.get("version", 0) + 1,
        "rating": ex.get("rating", None), "test_status": ex.get("test_status", "untested"),
    }
    save_registry(reg)

def save_tool(name, description, code, tags):
    safe = re.sub(r"[^\w]", "_", name.lower().strip())[:40]
    fp   = TOOLS_DIR / f"{safe}.py"
    if fp.exists():
        ver = load_registry().get(name, {}).get("version", 1)
        shutil.copy(fp, TOOLS_DIR / f"{safe}_v{ver}.py")
    header = f"# DESCRIPTION: {description}\n# TAGS: {', '.join(tags)}\n# UPDATED: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    fp.write_text(header + code + "\n")
    register_tool(name, fp, description, tags)
    return fp

def extract_code(txt):
    dm = re.search(r"#\s*DESCRIPTION:\s*(.+)", txt)
    tm = re.search(r"#\s*TAGS:\s*(.+)", txt)
    cm = re.search(r"```python\s*(.*?)```", txt, re.DOTALL)
    if not cm:
        raise ValueError("No code block")
    return (
        dm.group(1).strip() if dm else "Generated tool",
        cm.group(1).strip(),
        [t.strip() for t in tm.group(1).split(",")] if tm else [],
    )

def memory_ctx():
    m = load_memory()
    parts = []
    if m.get("user_style"):
        parts.append(f"User style: {m['user_style']}")
    if m.get("preferences"):
        parts.append("Prefs: " + "; ".join(f"{k}:{v}" for k, v in m["preferences"].items()))
    recent = m.get("tool_history", [])[-5:]
    if recent:
        parts.append(f"Recently built: {', '.join(e['tool'] for e in recent)}")
    if m.get("insights"):
        parts.append(f"Insights: {'; '.join(m['insights'][-3:])}")
    return "\n".join(parts)

def record_build(name, description, tags):
    m = load_memory()
    m["tool_history"].append({
        "tool": name, "description": description, "tags": tags,
        "success": True, "timestamp": datetime.now().isoformat(),
    })
    m["tool_history"] = m["tool_history"][-100:]
    save_memory(m)

def web_fetch(url, max_chars=6000):
    try:
        req = UReq(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=10) as r:
            raw = r.read().decode("utf-8", "ignore")
        raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL)
        raw = re.sub(r"<style[^>]*>.*?</style>",   "", raw, flags=re.DOTALL)
        raw = re.sub(r"<[^>]+>", " ", raw)
        return re.sub(r"\s+", " ", raw).strip()[:max_chars]
    except Exception as e:
        return f"[Error: {e}]"

def ai(prompt, system, max_tokens=3000):
    return client.messages.create(
        model=MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": prompt}],
    ).content[0].text

def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

# ── Prompts ───────────────────────────────────────────────────────────────────
P_BUILD = """Expert Python dev. Build small focused tools.
Reply:
1. # DESCRIPTION: one-line summary
2. # TAGS: comma-separated tags
3. ```python ... ``` complete code.
Single file. main()+__main__. Use input() for user input. Stdlib preferred; # REQUIRES: pkg if needed."""

P_IMPROVE = """Expert Python dev. Improve the given tool.
Reply:
1. # DESCRIPTION: updated summary
2. # TAGS: tags
3. ```python ... ``` improved code."""

P_REMIX = """Expert Python dev. Combine two tools into one.
Reply:
1. # DESCRIPTION: combined summary
2. # TAGS: tags
3. ```python ... ``` merged code."""

P_WEB = """Expert Python dev. Build a tool that fetches LIVE web data using urllib (no requests).
Reply:
1. # DESCRIPTION: summary
2. # TAGS: tags including 'web','live-data'
3. ```python ... ``` complete code.
Use urllib.request. Handle errors. main()+__main__."""

P_TEST = """Write unittest tests for this tool. Stdlib only. At least 3 test cases. Mock input() where needed.
Reply with ONLY ```python ... ``` block."""

P_PLANNER = """Software architect. Break the goal into 2-5 focused tools.
Reply ONLY with JSON array (no markdown): [{"name":"tool_name","description":"Does X"},...]"""

P_CHAIN = """Combine tools into a pipeline script.
Reply:
1. # DESCRIPTION: end-to-end description
2. # TAGS: pipeline + tags
3. ```python ... ``` pipeline code."""

P_EXPLAIN = "Friendly Python teacher. Explain the code: what it does, how it works, interesting techniques. Plain English."

P_AGENTS = {
    "planner": "PLANNER: write detailed spec (inputs, outputs, edge cases, approach). No code yet.",
    "builder": """BUILDER: write code from spec.
Reply:
1. # DESCRIPTION: summary
2. # TAGS: tags
3. ```python ... ``` complete code.""",
    "critic":  "CRITIC: find REAL bugs, missing error handling, edge cases. Numbered list. If good: 'APPROVED: reason'.",
    "fixer":   """FIXER: fix ALL critic issues.
Reply:
1. # DESCRIPTION: updated
2. # TAGS: tags
3. # FIXES: list of fixes
4. ```python ... ``` fixed code.""",
    "judge":   "JUDGE: final verdict.\n  VERDICT: SHIP IT — [why]\n  VERDICT: NEEDS WORK — [what's missing]",
}

# ══════════════════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/tools")
def api_tools():
    return jsonify(load_registry())

@app.route("/api/stats")
def api_stats():
    reg = load_registry()
    mem = load_memory()
    if not reg:
        return jsonify({"total": 0, "runs": 0, "avg_rating": 0, "top_tool": None,
                        "top_tags": [], "sessions": mem.get("total_sessions", 0), "insights": 0, "tested": 0})
    total = len(reg)
    runs  = sum(v.get("runs", 0) for v in reg.values())
    rated = [v["rating"] for v in reg.values() if v.get("rating")]
    avg_r = round(sum(rated) / len(rated), 1) if rated else 0
    top   = max(reg.items(), key=lambda x: x[1].get("runs", 0))
    tc    = {}
    for v in reg.values():
        for t in v.get("tags", []):
            tc[t] = tc.get(t, 0) + 1
    return jsonify({
        "total": total, "runs": runs, "avg_rating": avg_r, "top_tool": top[0],
        "top_tags": [{"tag": t, "count": c} for t, c in sorted(tc.items(), key=lambda x: -x[1])[:8]],
        "sessions": mem.get("total_sessions", 0),
        "insights": len(mem.get("insights", [])),
        "tested":   sum(1 for v in reg.values() if v.get("test_status") == "passed"),
    })

@app.route("/api/memory")
def api_memory():
    m = load_memory()
    return jsonify({
        "history":     m.get("tool_history", [])[-12:],
        "insights":    m.get("insights", []),
        "preferences": m.get("preferences", {}),
        "user_style":  m.get("user_style", ""),
        "sessions":    m.get("total_sessions", 0),
    })

@app.route("/api/memory/insight", methods=["POST"])
def api_add_insight():
    m = load_memory()
    m["insights"].append(request.json.get("insight", ""))
    m["insights"] = m["insights"][-20:]
    save_memory(m)
    return jsonify({"ok": True})

@app.route("/api/memory/style", methods=["POST"])
def api_set_style():
    m = load_memory()
    m["user_style"] = request.json.get("style", "")
    save_memory(m)
    return jsonify({"ok": True})

@app.route("/api/memory/clear", methods=["POST"])
def api_clear_memory():
    MEMORY_FILE.unlink(missing_ok=True)
    return jsonify({"ok": True})

@app.route("/api/tool/<n>/code")
def api_tool_code(n):
    reg = load_registry()
    if n not in reg:
        return jsonify({"error": "not found"}), 404
    fp = Path(reg[n]["file"])
    return jsonify({"code": fp.read_text() if fp.exists() else "# file not found"})

@app.route("/api/tool/<n>/rate", methods=["POST"])
def api_rate(n):
    reg = load_registry()
    if n in reg:
        reg[n]["rating"] = request.json.get("rating")
        save_registry(reg)
    return jsonify({"ok": True})

@app.route("/api/tool/<n>/delete", methods=["POST"])
def api_delete(n):
    reg = load_registry()
    if n in reg:
        Path(reg[n]["file"]).unlink(missing_ok=True)
        del reg[n]
        save_registry(reg)
    return jsonify({"ok": True})

@app.route("/api/tool/<n>/export")
def api_export(n):
    reg = load_registry()
    if n not in reg:
        return "not found", 404
    fp  = Path(reg[n]["file"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.write(fp, fp.name)
        zf.writestr("README.md", f"# {n}\n\nGenerated by AI Tool-Maker\n\nRun:\n    python {fp.name}\n")
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"{n}_export.zip")

@app.route("/api/save", methods=["POST"])
def api_save():
    d  = request.json
    fp = save_tool(d["name"], d["description"], d["code"], d.get("tags", []))
    record_build(d["name"], d["description"], d.get("tags", []))
    return jsonify({"ok": True, "file": str(fp)})

@app.route("/api/search")
def api_search():
    q   = request.args.get("q", "").lower()
    reg = load_registry()
    return jsonify({k: v for k, v in reg.items()
                    if q in k.lower() or q in v["description"].lower()
                    or any(q in t.lower() for t in v.get("tags", []))})

@app.route("/api/tool/<n>/explain")
def api_explain(n):
    reg = load_registry()
    if n not in reg:
        return jsonify({"error": "not found"}), 404
    code = Path(reg[n]["file"]).read_text()
    return jsonify({"explanation": ai(f"Explain:\n```python\n{code}\n```", P_EXPLAIN)})

@app.route("/api/fetch")
def api_fetch_url():
    url = request.args.get("url", "")
    if not url.startswith("http"):
        url = "https://" + url
    content = web_fetch(url)
    if content.startswith("[Error"):
        return jsonify({"error": content}), 400
    summary = ai(f"Summarize this web page. URL: {url}\nContent:\n{content}",
                 "Summarize web content clearly and concisely.")
    return jsonify({"summary": summary, "url": url})

# ── SSE streams ───────────────────────────────────────────────────────────────

@app.route("/api/build/stream")
def stream_build():
    desc = request.args.get("description", "")
    mode = request.args.get("mode", "normal")

    def gen():
        try:
            ctx    = memory_ctx()
            prompt = (f"Context:\n{ctx}\n\nTool: {desc}" if ctx else desc)

            if mode == "ai2ai":
                yield sse("status", {"msg": "🗺️ Planner writing spec...", "agent": "Planner"})
                spec  = ai(prompt, P_AGENTS["planner"])
                yield sse("agent", {"agent": "Planner", "output": spec, "color": "blue"})

                yield sse("status", {"msg": "🔨 Builder writing code...", "agent": "Builder"})
                built = ai(f"Request: {desc}\nSpec:\n{spec}", P_AGENTS["builder"])
                yield sse("agent", {"agent": "Builder", "output": built, "color": "green"})
                curr_desc, curr_code, curr_tags = extract_code(built)

                for rn in range(1, 3):
                    yield sse("status", {"msg": f"🔍 Critic reviewing (round {rn})...", "agent": "Critic"})
                    crit = ai(f"Spec:\n{spec}\n\nCode:\n```python\n{curr_code}\n```", P_AGENTS["critic"])
                    yield sse("agent", {"agent": f"Critic R{rn}", "output": crit, "color": "red"})
                    if crit.strip().startswith("APPROVED"):
                        yield sse("status", {"msg": "✅ Approved!", "agent": ""})
                        break
                    yield sse("status", {"msg": f"🔧 Fixer patching (round {rn})...", "agent": "Fixer"})
                    fixed = ai(f"Spec:\n{spec}\n\nCode:\n```python\n{curr_code}\n```\n\nIssues:\n{crit}", P_AGENTS["fixer"])
                    yield sse("agent", {"agent": f"Fixer R{rn}", "output": fixed, "color": "orange"})
                    try:
                        curr_desc, curr_code, curr_tags = extract_code(fixed)
                    except:
                        pass

                yield sse("status", {"msg": "⚖️ Judge deliberating...", "agent": "Judge"})
                verdict = ai(f"Request: {desc}\nFinal code:\n```python\n{curr_code}\n```", P_AGENTS["judge"])
                yield sse("agent", {"agent": "Judge", "output": verdict, "color": "purple"})
                yield sse("code", {"description": curr_desc, "code": curr_code, "tags": curr_tags, "verdict": verdict})

            else:
                yield sse("status", {"msg": "🤖 Claude is thinking...", "agent": "Claude"})
                result = ai(prompt, P_BUILD)
                d_out, code, tags = extract_code(result)
                yield sse("code", {"description": d_out, "code": code, "tags": tags})

            yield sse("done", {"ok": True})
        except Exception as e:
            yield sse("error", {"msg": str(e)})

    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/auto/stream")
def stream_auto():
    goal = request.args.get("goal", "")

    def gen():
        try:
            yield sse("status", {"msg": "🗺️ Planning tools..."})
            plan_raw = ai(goal, P_PLANNER)
            try:
                plan = json.loads(re.sub(r"```[a-z]*\s*", "", plan_raw).strip())
            except:
                m = re.search(r"\[.*\]", plan_raw, re.DOTALL)
                if not m:
                    yield sse("error", {"msg": "Could not parse plan"})
                    return
                plan = json.loads(m.group())

            yield sse("plan", {"plan": plan})
            built = []
            for i, step in enumerate(plan, 1):
                yield sse("status", {"msg": f"[{i}/{len(plan)}] Building: {step['name']}..."})
                try:
                    result = ai(step["description"], P_BUILD)
                    d_out, code, tags = extract_code(result)
                    save_tool(step["name"], d_out, code, tags)
                    record_build(step["name"], d_out, tags)
                    built.append({"name": step["name"], "description": d_out})
                    yield sse("built", {"name": step["name"], "description": d_out})
                except Exception as e:
                    yield sse("build_error", {"name": step["name"], "error": str(e)})

            yield sse("done", {"built": built})
        except Exception as e:
            yield sse("error", {"msg": str(e)})

    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/improve/stream")
def stream_improve():
    name = request.args.get("name", "")
    what = request.args.get("what", "make it better and more robust")

    def gen():
        try:
            reg = load_registry()
            if name not in reg:
                yield sse("error", {"msg": "Tool not found"})
                return
            code = Path(reg[name]["file"]).read_text()
            yield sse("status", {"msg": f"🔧 Improving {name}..."})
            result = ai(f"Current tool:\n```python\n{code}\n```\n\nImprovement: {what}", P_IMPROVE)
            d_out, new_code, tags = extract_code(result)
            yield sse("code", {"description": d_out, "code": new_code, "tags": tags, "original_name": name})
            yield sse("done", {"ok": True})
        except Exception as e:
            yield sse("error", {"msg": str(e)})

    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/remix/stream")
def stream_remix():
    n1   = request.args.get("tool1", "")
    n2   = request.args.get("tool2", "")
    goal = request.args.get("goal", "combine the best of both")

    def gen():
        try:
            reg = load_registry()
            for n in [n1, n2]:
                if n not in reg:
                    yield sse("error", {"msg": f"Tool '{n}' not found"})
                    return
            c1 = Path(reg[n1]["file"]).read_text()
            c2 = Path(reg[n2]["file"]).read_text()
            yield sse("status", {"msg": f"🎛️ Remixing {n1} + {n2}..."})
            result = ai(f"Tool 1 ({n1}):\n```python\n{c1}\n```\n\nTool 2 ({n2}):\n```python\n{c2}\n```\n\nGoal: {goal}", P_REMIX)
            d_out, code, tags = extract_code(result)
            yield sse("code", {"description": d_out, "code": code, "tags": tags, "remix_name": f"{n1}_x_{n2}"})
            yield sse("done", {"ok": True})
        except Exception as e:
            yield sse("error", {"msg": str(e)})

    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/chain/stream")
def stream_chain():
    names = request.args.get("tools", "").split(",")
    goal  = request.args.get("goal", "process data end to end")

    def gen():
        try:
            reg       = load_registry()
            tool_list = [(n, Path(reg[n]["file"])) for n in names if n in reg]
            if len(tool_list) < 2:
                yield sse("error", {"msg": "Need at least 2 valid tools"})
                return
            info  = "\n".join(f"- {n}: {reg[n]['description']}" for n, _ in tool_list)
            codes = "\n\n".join(f"# {n}\n```python\n{fp.read_text()}\n```" for n, fp in tool_list)
            yield sse("status", {"msg": f"🔗 Building pipeline from {len(tool_list)} tools..."})
            result = ai(f"Goal: {goal}\nTools:\n{info}\n\nCode:\n{codes}", P_CHAIN)
            d_out, code, tags = extract_code(result)
            pname = "pipeline_" + "_".join(n for n, _ in tool_list[:3])
            yield sse("code", {"description": d_out, "code": code, "tags": tags, "pipeline_name": pname})
            yield sse("done", {"ok": True})
        except Exception as e:
            yield sse("error", {"msg": str(e)})

    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/test/stream")
def stream_test():
    name = request.args.get("name", "")

    def gen():
        try:
            reg = load_registry()
            if name not in reg:
                yield sse("error", {"msg": "Tool not found"})
                return
            code = Path(reg[name]["file"]).read_text()
            yield sse("status", {"msg": f"🧪 Generating tests for {name}..."})
            result = ai(f"Write tests for:\n```python\n{code}\n```", P_TEST)
            cm = re.search(r"```python\s*(.*?)```", result, re.DOTALL)
            if not cm:
                yield sse("error", {"msg": "No test code generated"})
                return
            test_code = f"import sys\nsys.path.insert(0, r'{TOOLS_DIR.resolve()}')\n" + cm.group(1).strip()
            yield sse("test_code", {"code": test_code})

            yield sse("status", {"msg": "▶️ Running tests..."})
            tf     = TOOLS_DIR / f"test_{re.sub(r'[^\\w]','_',name)}.py"
            tf.write_text(test_code)
            result2 = subprocess.run([sys.executable, "-m", "unittest", str(tf), "-v"],
                                     capture_output=True, text=True, timeout=30)
            output = result2.stdout + result2.stderr
            passed = result2.returncode == 0
            reg2   = load_registry()
            if name in reg2:
                reg2[name]["test_status"] = "passed" if passed else "failed"
                save_registry(reg2)
            yield sse("test_result", {"output": output, "passed": passed})
            yield sse("done", {"ok": True})
        except Exception as e:
            yield sse("error", {"msg": str(e)})

    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/web/stream")
def stream_web():
    desc = request.args.get("description", "")

    def gen():
        try:
            yield sse("status", {"msg": "🔍 Researching APIs..."})
            try:
                search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(desc + ' python api url example')}"
                html  = web_fetch(search_url, 12000)
                urls  = list(set(re.findall(r"https?://(?!.*duckduck)[^\s\"'<>]{15,80}", html)))[:4]
                wctx  = "\nRelevant URLs:\n" + "\n".join(f"- {u}" for u in urls) if urls else ""
            except:
                wctx = ""
            ctx    = memory_ctx()
            prompt = (f"Context:\n{ctx}\n\n" if ctx else "") + desc + wctx
            yield sse("status", {"msg": "🤖 Building web tool..."})
            result = ai(prompt, P_WEB)
            d_out, code, tags = extract_code(result)
            yield sse("code", {"description": d_out, "code": code, "tags": tags})
            yield sse("done", {"ok": True})
        except Exception as e:
            yield sse("error", {"msg": str(e)})

    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ── Home ──────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    mem = load_memory()
    mem["total_sessions"] = mem.get("total_sessions", 0) + 1
    save_memory(mem)
    return HTML


# ══════════════════════════════════════════════════════════════════════════════
# FRONTEND HTML
# ══════════════════════════════════════════════════════════════════════════════
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>🛠️ AI Tool-Maker</title>
<style>
:root{--bg:#0d0d0f;--s1:#16161a;--s2:#1e1e24;--b:#2a2a35;--acc:#7c6af7;--acc2:#56cfb2;--tx:#e8e8f0;--mu:#6b6b80;--red:#f07070;--grn:#56cfb2;--ylw:#f0c070;--orn:#f0a850;--pur:#c47af7;--blu:#5b9cf6}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh}
.app{display:grid;grid-template-columns:240px 1fr;grid-template-rows:56px 1fr;height:100vh}
.tb{grid-column:1/-1;display:flex;align-items:center;gap:12px;padding:0 20px;background:var(--s1);border-bottom:1px solid var(--b);z-index:10}
.tb h1{font-size:16px;font-weight:700;background:linear-gradient(90deg,var(--acc),var(--acc2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.tb .si{margin-left:auto;font-size:11px;color:var(--mu)}
.sb{background:var(--s1);border-right:1px solid var(--b);overflow-y:auto;padding:10px 0}
.ns{padding:6px 14px 2px;font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--mu)}
.ni{display:flex;align-items:center;gap:8px;padding:8px 16px;cursor:pointer;font-size:13px;color:var(--mu);border-left:2px solid transparent;transition:all .15s}
.ni:hover{color:var(--tx);background:var(--s2)}
.ni.active{color:var(--acc);border-left-color:var(--acc);background:var(--s2)}
.ni .ic{font-size:14px;width:16px;text-align:center}
.mn{overflow-y:auto;padding:18px;display:flex;flex-direction:column;gap:14px}
.card{background:var(--s1);border:1px solid var(--b);border-radius:11px;padding:16px}
.card h2{font-size:14px;font-weight:600;margin-bottom:12px;display:flex;align-items:center;gap:6px}
textarea,input[type=text],select{width:100%;background:var(--s2);border:1px solid var(--b);color:var(--tx);border-radius:7px;padding:9px 11px;font-size:13px;font-family:inherit;resize:none;outline:none;transition:border-color .2s}
textarea:focus,input[type=text]:focus,select:focus{border-color:var(--acc)}
select{-webkit-appearance:none}
.btn{padding:8px 16px;border:none;border-radius:7px;cursor:pointer;font-size:13px;font-weight:600;transition:all .15s;white-space:nowrap}
.bp{background:var(--acc);color:#fff}.bp:hover{filter:brightness(1.15)}.bp:disabled{opacity:.5;cursor:not-allowed}
.bs{background:var(--s2);color:var(--tx);border:1px solid var(--b)}.bs:hover{border-color:var(--acc);color:var(--acc)}
.bd{background:transparent;color:var(--red);border:1px solid var(--red)}.bd:hover{background:var(--red);color:#fff}
.bg{background:transparent;color:var(--grn);border:1px solid var(--grn)}.bg:hover{background:var(--grn);color:#fff}
.bsm{padding:5px 10px;font-size:12px}
.row{display:flex;gap:8px;align-items:flex-start}
.stat-ln{display:flex;align-items:center;gap:7px;padding:6px 0;font-size:12px;color:var(--mu)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--acc);animation:pulse 1s infinite;flex-shrink:0}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.al{display:flex;flex-direction:column;gap:5px;margin-top:8px}
.ap{border-radius:7px;overflow:hidden}
.ah{padding:6px 11px;font-size:11px;font-weight:700;display:flex;align-items:center;gap:5px;cursor:pointer;user-select:none}
.ab{padding:9px 11px;font-size:11px;line-height:1.6;white-space:pre-wrap;max-height:160px;overflow-y:auto;display:none}
.ap.open .ab{display:block}
.ap-blue .ah{background:rgba(91,156,246,.15);color:var(--blu)}.ap-blue .ab{background:rgba(91,156,246,.05)}
.ap-green .ah{background:rgba(86,207,178,.15);color:var(--grn)}.ap-green .ab{background:rgba(86,207,178,.05)}
.ap-red .ah{background:rgba(240,112,112,.15);color:var(--red)}.ap-red .ab{background:rgba(240,112,112,.05)}
.ap-orange .ah{background:rgba(240,168,80,.15);color:var(--orn)}.ap-orange .ab{background:rgba(240,168,80,.05)}
.ap-purple .ah{background:rgba(196,122,247,.15);color:var(--pur)}.ap-purple .ab{background:rgba(196,122,247,.05)}
.cr{background:var(--s2);border:1px solid var(--b);border-radius:9px;overflow:hidden;margin-top:10px}
.crh{padding:10px 13px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--b);flex-wrap:wrap;gap:6px}
.crt{font-weight:600;font-size:13px}
.tags{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}
.tag{background:rgba(124,106,247,.15);color:var(--acc);border-radius:4px;padding:2px 6px;font-size:10px}
pre{padding:12px;overflow-x:auto;font-size:11px;line-height:1.6;font-family:'Cascadia Code','Fira Code',monospace;max-height:340px;overflow-y:auto}
.sf{padding:10px 13px;border-top:1px solid var(--b);display:flex;gap:7px;align-items:center;flex-wrap:wrap}
.sg{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:9px}
.sc{background:var(--s2);border-radius:9px;padding:12px;text-align:center;border:1px solid var(--b)}
.sn{font-size:24px;font-weight:800;background:linear-gradient(135deg,var(--acc),var(--acc2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sl{font-size:10px;color:var(--mu);margin-top:2px;text-transform:uppercase;letter-spacing:.4px}
.tg{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:9px}
.tc{background:var(--s2);border:1px solid var(--b);border-radius:8px;padding:12px;cursor:pointer;transition:all .15s}
.tc:hover{border-color:var(--acc);transform:translateY(-1px)}
.tc h3{font-size:13px;font-weight:600;margin-bottom:4px;color:var(--acc2)}
.tc p{font-size:11px;color:var(--mu);line-height:1.5;margin-bottom:7px}
.tm{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--mu);flex-wrap:wrap}
.badge{background:var(--s1);border:1px solid var(--b);border-radius:3px;padding:1px 5px}
.mo{position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:100;display:none;align-items:center;justify-content:center}
.mo.open{display:flex}
.md{background:var(--s1);border:1px solid var(--b);border-radius:12px;width:92%;max-width:660px;max-height:88vh;overflow-y:auto}
.mh{padding:16px 20px;border-bottom:1px solid var(--b);display:flex;align-items:center;justify-content:space-between}
.mb{padding:16px 20px}
.mf{padding:12px 20px;border-top:1px solid var(--b);display:flex;gap:7px;justify-content:flex-end;flex-wrap:wrap}
.xb{background:none;border:none;color:var(--mu);font-size:18px;cursor:pointer}.xb:hover{color:var(--tx)}
.stars{display:flex;gap:3px;font-size:20px;cursor:pointer}
.star{color:var(--b);transition:color .1s}
.star.lit,.stars:hover .star{color:var(--ylw)}
.stars .star:hover~.star{color:var(--b)}
.vd{padding:4px 10px;border-radius:16px;font-size:11px;font-weight:700;display:inline-flex;align-items:center;gap:4px;margin-top:5px}
.vd.ship{background:rgba(86,207,178,.2);color:var(--grn);border:1px solid var(--grn)}
.vd.needs{background:rgba(240,192,112,.2);color:var(--ylw);border:1px solid var(--ylw)}
.ftg{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.ft{padding:3px 10px;border-radius:16px;font-size:11px;cursor:pointer;background:var(--s2);border:1px solid var(--b);color:var(--mu);transition:all .15s}
.ft.active{background:var(--acc);color:#fff;border-color:var(--acc)}
.mi{display:flex;align-items:flex-start;gap:8px;padding:8px 0;border-bottom:1px solid var(--b);font-size:12px}
.mi:last-child{border:none}
.mit{font-size:10px;color:var(--mu);margin-top:2px}
.cb-group{display:flex;flex-direction:column;gap:5px;max-height:200px;overflow-y:auto}
.cb-item{display:flex;align-items:center;gap:7px;padding:5px 9px;background:var(--s2);border-radius:6px;cursor:pointer;font-size:12px;border:1px solid transparent;transition:all .15s}
.cb-item:hover{border-color:var(--acc)}
.cb-item.sel{border-color:var(--acc);background:rgba(124,106,247,.1)}
.cb-item input{accent-color:var(--acc)}
.toast{position:fixed;bottom:20px;right:20px;background:var(--s1);border:1px solid var(--b);border-radius:7px;padding:9px 14px;font-size:12px;z-index:200;display:none;animation:si .2s ease}
.toast.show{display:block}
@keyframes si{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.empty{text-align:center;padding:45px 20px;color:var(--mu)}
.empty .ei{font-size:38px;margin-bottom:9px}
.sect{font-size:11px;font-weight:700;color:var(--acc2);margin-bottom:7px;margin-top:14px;text-transform:uppercase;letter-spacing:.5px}
.sect:first-child{margin-top:0}
.divider{height:1px;background:var(--b);margin:10px 0}
.test-out{background:var(--s2);border-radius:7px;padding:10px;font-size:11px;font-family:monospace;max-height:240px;overflow-y:auto;white-space:pre-wrap;margin-top:9px;border:1px solid var(--b)}
::-webkit-scrollbar{width:4px;height:4px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:var(--b);border-radius:2px}
label{font-size:12px;color:var(--mu)}
.lbl{font-size:12px;color:var(--mu);margin-bottom:5px;display:block}
</style>
</head>
<body>
<div class="app">
<div class="tb">
  <span style="font-size:19px">🛠️</span>
  <h1>AI Tool-Maker</h1>
  <span class="si" id="si">Loading...</span>
</div>

<nav class="sb">
  <div class="ns">Studio</div>
  <div class="ni active" onclick="V('build')" id="nv-build"><span class="ic">✨</span>Build</div>
  <div class="ni" onclick="V('ai2ai')" id="nv-ai2ai"><span class="ic">🤖</span>AI-to-AI</div>
  <div class="ni" onclick="V('auto')" id="nv-auto"><span class="ic">🚀</span>Auto-Mode</div>
  <div class="ns">Modify</div>
  <div class="ni" onclick="V('improve')" id="nv-improve"><span class="ic">🔧</span>Improve</div>
  <div class="ni" onclick="V('remix')" id="nv-remix"><span class="ic">🎛️</span>Remix</div>
  <div class="ni" onclick="V('chain')" id="nv-chain"><span class="ic">🔗</span>Chain</div>
  <div class="ni" onclick="V('test')" id="nv-test"><span class="ic">🧪</span>Test</div>
  <div class="ns">Web</div>
  <div class="ni" onclick="V('web')" id="nv-web"><span class="ic">🌐</span>Web Tool</div>
  <div class="ni" onclick="V('fetch')" id="nv-fetch"><span class="ic">📄</span>Fetch URL</div>
  <div class="ns">Library</div>
  <div class="ni" onclick="V('tools')" id="nv-tools"><span class="ic">📚</span>All Tools</div>
  <div class="ni" onclick="V('search')" id="nv-search"><span class="ic">🔍</span>Search</div>
  <div class="ns">Insights</div>
  <div class="ni" onclick="V('stats')" id="nv-stats"><span class="ic">📊</span>Dashboard</div>
  <div class="ni" onclick="V('memory')" id="nv-memory"><span class="ic">🧠</span>Memory</div>
</nav>

<main class="mn" id="main">

<!-- BUILD -->
<div id="vw-build">
  <div class="card">
    <h2>✨ Build a Tool</h2>
    <p style="color:var(--mu);font-size:12px;margin-bottom:10px">Describe a tool in plain English — Claude writes the Python code.</p>
    <div class="row"><textarea id="bd" rows="3" placeholder="e.g. a tool that resizes all images in a folder..."></textarea><button class="btn bp" onclick="startBuild()" id="b-btn">Build ✨</button></div>
  </div>
  <div class="card" id="b-out" style="display:none">
    <div class="stat-ln" id="b-stat"><div class="dot"></div><span id="b-stxt">Starting...</span></div>
    <div class="al" id="b-al"></div>
    <div class="cr" id="b-cr" style="display:none">
      <div class="crh"><div><div class="crt" id="b-ctit"></div><div class="tags" id="b-ctags"></div></div><div id="b-verd"></div></div>
      <pre id="b-cpre"></pre>
      <div class="sf"><input type="text" id="b-name" placeholder="Tool name..." style="max-width:190px"><button class="btn bp bsm" onclick="saveCurrent('b')">💾 Save</button><button class="btn bs bsm" onclick="copyCurrent('b')">📋 Copy</button></div>
    </div>
  </div>
</div>

<!-- AI2AI -->
<div id="vw-ai2ai" style="display:none">
  <div class="card">
    <h2>🤖 AI-to-AI Mode</h2>
    <p style="color:var(--mu);font-size:12px;margin-bottom:10px">5 Claude agents: Planner → Builder → Critic → Fixer → Judge</p>
    <div class="row"><textarea id="a2d" rows="3" placeholder="Describe the tool..."></textarea><button class="btn bp" onclick="startA2A()" id="a2-btn">Launch 🚀</button></div>
  </div>
  <div class="card" id="a2-out" style="display:none">
    <div class="stat-ln" id="a2-stat"><div class="dot"></div><span id="a2-stxt">Initializing...</span></div>
    <div class="al" id="a2-al"></div>
    <div class="cr" id="a2-cr" style="display:none">
      <div class="crh"><div><div class="crt" id="a2-ctit"></div><div class="tags" id="a2-ctags"></div></div><div id="a2-verd"></div></div>
      <pre id="a2-cpre"></pre>
      <div class="sf"><input type="text" id="a2-name" placeholder="Tool name..." style="max-width:190px"><button class="btn bp bsm" onclick="saveCurrent('a2')">💾 Save</button><button class="btn bs bsm" onclick="copyCurrent('a2')">📋 Copy</button></div>
    </div>
  </div>
</div>

<!-- AUTO -->
<div id="vw-auto" style="display:none">
  <div class="card">
    <h2>🚀 Auto-Mode</h2>
    <p style="color:var(--mu);font-size:12px;margin-bottom:10px">Give a big goal — Claude plans & builds all the tools needed automatically.</p>
    <div class="row"><textarea id="atd" rows="2" placeholder="e.g. build a complete file organizer that scans, categorizes, and reports..."></textarea><button class="btn bp" onclick="startAuto()" id="at-btn">Auto-Build 🚀</button></div>
  </div>
  <div class="card" id="at-out" style="display:none">
    <div class="stat-ln" id="at-stat"><div class="dot"></div><span id="at-stxt">Planning...</span></div>
    <div id="at-plan"></div>
    <div id="at-results"></div>
    <div id="at-chain-wrap" style="display:none;margin-top:10px">
      <div class="divider"></div>
      <p style="font-size:12px;color:var(--mu);margin-bottom:7px">All done! Chain them into a pipeline?</p>
      <button class="btn bg bsm" onclick="chainBuiltTools()">🔗 Build Pipeline</button>
    </div>
  </div>
</div>

<!-- IMPROVE -->
<div id="vw-improve" style="display:none">
  <div class="card">
    <h2>🔧 Improve a Tool</h2>
    <p style="color:var(--mu);font-size:12px;margin-bottom:10px">Pick a tool, describe what to improve — Claude rewrites it.</p>
    <span class="lbl">Select tool:</span>
    <select id="im-sel" style="margin-bottom:9px"></select>
    <div class="row"><textarea id="im-what" rows="2" placeholder="What should be improved? (blank = general improvement)"></textarea><button class="btn bp" onclick="startImprove()" id="im-btn">Improve 🔧</button></div>
  </div>
  <div class="card" id="im-out" style="display:none">
    <div class="stat-ln" id="im-stat"><div class="dot"></div><span id="im-stxt">Improving...</span></div>
    <div class="cr" id="im-cr" style="display:none">
      <div class="crh"><div><div class="crt" id="im-ctit"></div><div class="tags" id="im-ctags"></div></div></div>
      <pre id="im-cpre"></pre>
      <div class="sf"><input type="text" id="im-name" placeholder="Tool name..." style="max-width:190px"><button class="btn bp bsm" onclick="saveCurrent('im')">💾 Save</button><button class="btn bs bsm" onclick="copyCurrent('im')">📋 Copy</button></div>
    </div>
  </div>
</div>

<!-- REMIX -->
<div id="vw-remix" style="display:none">
  <div class="card">
    <h2>🎛️ Remix Two Tools</h2>
    <p style="color:var(--mu);font-size:12px;margin-bottom:10px">Pick two tools — Claude fuses them into one.</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-bottom:9px">
      <div><span class="lbl">First tool:</span><select id="rx-t1"></select></div>
      <div><span class="lbl">Second tool:</span><select id="rx-t2"></select></div>
    </div>
    <div class="row"><textarea id="rx-goal" rows="2" placeholder="Goal for the combined tool..."></textarea><button class="btn bp" onclick="startRemix()" id="rx-btn">Remix 🎛️</button></div>
  </div>
  <div class="card" id="rx-out" style="display:none">
    <div class="stat-ln" id="rx-stat"><div class="dot"></div><span id="rx-stxt">Remixing...</span></div>
    <div class="cr" id="rx-cr" style="display:none">
      <div class="crh"><div><div class="crt" id="rx-ctit"></div><div class="tags" id="rx-ctags"></div></div></div>
      <pre id="rx-cpre"></pre>
      <div class="sf"><input type="text" id="rx-name" placeholder="Tool name..." style="max-width:190px"><button class="btn bp bsm" onclick="saveCurrent('rx')">💾 Save</button><button class="btn bs bsm" onclick="copyCurrent('rx')">📋 Copy</button></div>
    </div>
  </div>
</div>

<!-- CHAIN -->
<div id="vw-chain" style="display:none">
  <div class="card">
    <h2>🔗 Build a Pipeline</h2>
    <p style="color:var(--mu);font-size:12px;margin-bottom:10px">Select 2+ tools — Claude builds a pipeline that runs them in sequence.</p>
    <span class="lbl" style="margin-bottom:6px;display:block">Select tools:</span>
    <div class="cb-group" id="chain-list" style="margin-bottom:9px"></div>
    <textarea id="ch-goal" rows="2" placeholder="What should this pipeline achieve?" style="margin-bottom:9px"></textarea>
    <button class="btn bp" onclick="startChain()" id="ch-btn">Build Pipeline 🔗</button>
  </div>
  <div class="card" id="ch-out" style="display:none">
    <div class="stat-ln" id="ch-stat"><div class="dot"></div><span id="ch-stxt">Building pipeline...</span></div>
    <div class="cr" id="ch-cr" style="display:none">
      <div class="crh"><div><div class="crt" id="ch-ctit"></div><div class="tags" id="ch-ctags"></div></div></div>
      <pre id="ch-cpre"></pre>
      <div class="sf"><input type="text" id="ch-name" placeholder="Pipeline name..." style="max-width:190px"><button class="btn bp bsm" onclick="saveCurrent('ch')">💾 Save</button><button class="btn bs bsm" onclick="copyCurrent('ch')">📋 Copy</button></div>
    </div>
  </div>
</div>

<!-- TEST -->
<div id="vw-test" style="display:none">
  <div class="card">
    <h2>🧪 Auto-Test a Tool</h2>
    <p style="color:var(--mu);font-size:12px;margin-bottom:10px">Claude generates unittest tests and runs them. Pass/fail saved to registry.</p>
    <span class="lbl">Select tool:</span>
    <select id="ts-sel" style="margin-bottom:9px"></select>
    <button class="btn bp" onclick="startTest()" id="ts-btn">Generate &amp; Run Tests 🧪</button>
  </div>
  <div class="card" id="ts-out" style="display:none">
    <div class="stat-ln" id="ts-stat"><div class="dot"></div><span id="ts-stxt">Generating tests...</span></div>
    <div id="ts-code-wrap" style="display:none"><div class="sect">Test Code</div><pre id="ts-cpre"></pre></div>
    <div id="ts-res-wrap" style="display:none">
      <div class="sect">Results</div>
      <div class="test-out" id="ts-out-txt"></div>
      <div id="ts-verd" style="margin-top:9px;font-size:13px;font-weight:600"></div>
    </div>
  </div>
</div>

<!-- WEB TOOL -->
<div id="vw-web" style="display:none">
  <div class="card">
    <h2>🌐 Web Tool Builder</h2>
    <p style="color:var(--mu);font-size:12px;margin-bottom:10px">Build tools that fetch live web data. Claude researches the right APIs.</p>
    <div class="row"><textarea id="wb-desc" rows="3" placeholder="e.g. fetch today's weather for any city... get top Hacker News posts..."></textarea><button class="btn bp" onclick="startWeb()" id="wb-btn">Build 🌐</button></div>
  </div>
  <div class="card" id="wb-out" style="display:none">
    <div class="stat-ln" id="wb-stat"><div class="dot"></div><span id="wb-stxt">Researching APIs...</span></div>
    <div class="cr" id="wb-cr" style="display:none">
      <div class="crh"><div><div class="crt" id="wb-ctit"></div><div class="tags" id="wb-ctags"></div></div></div>
      <pre id="wb-cpre"></pre>
      <div class="sf"><input type="text" id="wb-name" placeholder="Tool name..." style="max-width:190px"><button class="btn bp bsm" onclick="saveCurrent('wb')">💾 Save</button><button class="btn bs bsm" onclick="copyCurrent('wb')">📋 Copy</button></div>
    </div>
  </div>
</div>

<!-- FETCH URL -->
<div id="vw-fetch" style="display:none">
  <div class="card">
    <h2>📄 Fetch &amp; Summarize URL</h2>
    <p style="color:var(--mu);font-size:12px;margin-bottom:10px">Paste any URL — Claude fetches and summarizes it instantly.</p>
    <div class="row"><input type="text" id="fu-url" placeholder="https://..."><button class="btn bp" onclick="doFetch()" id="fu-btn">Fetch 📄</button></div>
    <div id="fu-res" style="display:none;margin-top:12px">
      <div class="sect" id="fu-lbl"></div>
      <div id="fu-sum" style="font-size:13px;line-height:1.7"></div>
    </div>
  </div>
</div>

<!-- ALL TOOLS -->
<div id="vw-tools" style="display:none">
  <div class="card">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:11px;flex-wrap:wrap;gap:7px">
      <h2 style="margin:0">📚 Tool Library</h2>
      <button class="btn bs bsm" onclick="loadTools()">↻ Refresh</button>
    </div>
    <div class="ftg" id="ftg"></div>
    <div class="tg" id="tg"><div class="empty"><div class="ei">📭</div>No tools yet!</div></div>
  </div>
</div>

<!-- SEARCH -->
<div id="vw-search" style="display:none">
  <div class="card">
    <h2>🔍 Search Tools</h2>
    <input type="text" id="sq" placeholder="Search by name, description, or tag..." oninput="doSearch()" style="margin-bottom:12px">
    <div class="tg" id="sr"><div class="empty"><div class="ei">🔍</div>Start typing...</div></div>
  </div>
</div>

<!-- STATS -->
<div id="vw-stats" style="display:none">
  <div class="card"><h2>📊 Dashboard</h2><div class="sg" id="sg"></div></div>
  <div class="card"><h2>🏷️ Top Tags</h2><div id="tc" style="display:flex;gap:7px;flex-wrap:wrap"></div></div>
</div>

<!-- MEMORY -->
<div id="vw-memory" style="display:none">
  <div class="card">
    <h2>🧠 Memory</h2>
    <p style="color:var(--mu);font-size:12px;margin-bottom:12px">Claude learns from your builds and gets smarter each session.</p>
    <div id="mc"></div>
    <div class="divider"></div>
    <div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:10px">
      <button class="btn bs bsm" onclick="showMini('⚙️ Coding Style','Describe your style...','style')">⚙️ Set Style</button>
      <button class="btn bs bsm" onclick="showMini('💡 Add Insight','Something to remember...','insight')">💡 Add Insight</button>
      <button class="btn bd bsm" onclick="clearMemory()">🗑️ Clear</button>
    </div>
  </div>
</div>

</main>
</div>

<!-- Tool Modal -->
<div class="mo" id="tool-mo">
  <div class="md">
    <div class="mh"><div><div style="font-size:14px;font-weight:700" id="mo-title"></div><div class="tags" id="mo-tags" style="margin-top:4px"></div></div><button class="xb" onclick="closeMo()">✕</button></div>
    <div class="mb">
      <p style="color:var(--mu);font-size:12px;margin-bottom:10px" id="mo-desc"></p>
      <div class="tm" id="mo-meta" style="margin-bottom:10px"></div>
      <div style="margin-bottom:12px"><div style="font-size:12px;color:var(--mu);margin-bottom:5px">Rating:</div>
        <div class="stars" id="mo-stars" onclick="handleStar(event)">
          <span class="star" data-v="1">★</span><span class="star" data-v="2">★</span><span class="star" data-v="3">★</span><span class="star" data-v="4">★</span><span class="star" data-v="5">★</span>
        </div>
      </div>
      <div id="mo-exp-wrap" style="display:none;margin-bottom:12px"><div class="sect">📖 Explanation</div><div id="mo-exp" style="font-size:12px;line-height:1.7"></div></div>
      <pre id="mo-code" style="font-size:11px;max-height:280px"></pre>
    </div>
    <div class="mf">
      <button class="btn bd bsm" onclick="deleteTool()">🗑️ Delete</button>
      <button class="btn bs bsm" onclick="explainTool()" id="mo-exp-btn">📖 Explain</button>
      <button class="btn bs bsm" onclick="exportTool()">📦 Export</button>
      <button class="btn bs bsm" onclick="copyMoCode()">📋 Copy</button>
      <button class="btn bs bsm" onclick="closeMo()">Close</button>
    </div>
  </div>
</div>

<!-- Mini Input Modal -->
<div class="mo" id="mini-mo">
  <div class="md" style="max-width:400px">
    <div class="mh"><div style="font-weight:700;font-size:13px" id="mini-ttl">Input</div><button class="xb" onclick="closeMini()">✕</button></div>
    <div class="mb"><textarea id="mini-inp" rows="3" placeholder=""></textarea></div>
    <div class="mf"><button class="btn bp bsm" onclick="submitMini()">Save</button><button class="btn bs bsm" onclick="closeMini()">Cancel</button></div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const codes={},descs={},tagss={};
let curMoTool=null,activeFilter=null,builtTools=[],miniMode=null,searchT;

document.addEventListener("DOMContentLoaded",()=>{ loadSI(); V("build"); });

async function loadSI(){
  const s=await f("/api/stats");
  document.getElementById("si").textContent=`🧠 ${s.total} tools · Session #${s.sessions}`;
}

function V(name){
  document.querySelectorAll("[id^=vw-]").forEach(e=>e.style.display="none");
  document.querySelectorAll(".ni").forEach(e=>e.classList.remove("active"));
  document.getElementById("vw-"+name).style.display="block";
  document.getElementById("nv-"+name).classList.add("active");
  if(name==="tools") loadTools();
  if(name==="stats") loadStats();
  if(name==="memory") loadMemory();
  if(name==="improve"||name==="test") loadSelects();
  if(name==="remix") loadRemixSels();
  if(name==="chain") loadChainList();
}

function mkStream(url,{outId,statId,stxtId,alId,crId,ctitId,ctagsId,cpreId,verdId,nameId,pfx,btnId}){
  const btn=document.getElementById(btnId);
  document.getElementById(outId).style.display="block";
  document.getElementById(statId).style.display="flex";
  document.getElementById(crId).style.display="none";
  if(alId) document.getElementById(alId).innerHTML="";
  btn.disabled=true;
  const cm={"blue":"ap-blue","green":"ap-green","red":"ap-red","orange":"ap-orange","purple":"ap-purple"};
  const es=new EventSource(url);
  es.addEventListener("status",e=>{ document.getElementById(stxtId).textContent=JSON.parse(e.data).msg; });
  es.addEventListener("agent",e=>{
    if(!alId) return;
    const d=JSON.parse(e.data);
    const p=document.createElement("div");
    p.className=`ap ${cm[d.color]||"ap-blue"} open`;
    p.innerHTML=`<div class="ah" onclick="this.parentElement.classList.toggle('open')"><span>▾</span> ${d.agent}</div><div class="ab">${esc(d.output.substring(0,500))}${d.output.length>500?"...":""}</div>`;
    document.getElementById(alId).appendChild(p);
    p.scrollIntoView({behavior:"smooth"});
  });
  es.addEventListener("code",e=>{
    const d=JSON.parse(e.data);
    codes[pfx]=d.code; descs[pfx]=d.description; tagss[pfx]=d.tags||[];
    document.getElementById(ctitId).textContent=d.description;
    document.getElementById(ctagsId).innerHTML=(d.tags||[]).map(t=>`<span class="tag">${t}</span>`).join("");
    document.getElementById(cpreId).textContent=d.code;
    if(nameId) document.getElementById(nameId).value=slug(d.description||"tool");
    if(verdId&&d.verdict){const ship=d.verdict.includes("SHIP IT"); document.getElementById(verdId).innerHTML=`<div class="vd ${ship?"ship":"needs"}">${ship?"✅":"⚠️"} ${d.verdict.substring(0,52)}</div>`;}
    document.getElementById(crId).style.display="block";
  });
  es.addEventListener("done",()=>{ es.close(); document.getElementById(statId).style.display="none"; btn.disabled=false; loadSI(); });
  es.addEventListener("error",e=>{ es.close(); try{toast("❌ "+JSON.parse(e.data).msg);}catch{} btn.disabled=false; });
  return es;
}

function startBuild(){
  const d=document.getElementById("bd").value.trim(); if(!d) return;
  mkStream(`/api/build/stream?description=${enc(d)}&mode=normal`,{outId:"b-out",statId:"b-stat",stxtId:"b-stxt",alId:"b-al",crId:"b-cr",ctitId:"b-ctit",ctagsId:"b-ctags",cpreId:"b-cpre",verdId:"b-verd",nameId:"b-name",pfx:"b",btnId:"b-btn"});
}

function startA2A(){
  const d=document.getElementById("a2d").value.trim(); if(!d) return;
  mkStream(`/api/build/stream?description=${enc(d)}&mode=ai2ai`,{outId:"a2-out",statId:"a2-stat",stxtId:"a2-stxt",alId:"a2-al",crId:"a2-cr",ctitId:"a2-ctit",ctagsId:"a2-ctags",cpreId:"a2-cpre",verdId:"a2-verd",nameId:"a2-name",pfx:"a2",btnId:"a2-btn"});
}

function startAuto(){
  const goal=document.getElementById("atd").value.trim(); if(!goal) return;
  const btn=document.getElementById("at-btn");
  document.getElementById("at-out").style.display="block";
  document.getElementById("at-stat").style.display="flex";
  document.getElementById("at-plan").innerHTML="";
  document.getElementById("at-results").innerHTML="";
  document.getElementById("at-chain-wrap").style.display="none";
  btn.disabled=true; builtTools=[];
  const es=new EventSource(`/api/auto/stream?goal=${enc(goal)}`);
  es.addEventListener("status",e=>{ document.getElementById("at-stxt").textContent=JSON.parse(e.data).msg; });
  es.addEventListener("plan",e=>{
    const {plan}=JSON.parse(e.data);
    document.getElementById("at-plan").innerHTML=`<div style="margin-bottom:9px"><div class="sect">📋 Plan</div>${plan.map((s,i)=>`<div style="display:flex;gap:8px;padding:5px 0;border-bottom:1px solid var(--b);font-size:12px"><span style="color:var(--acc);font-weight:700">${i+1}</span><div><strong>${s.name}</strong> — <span style="color:var(--mu)">${s.description}</span></div></div>`).join("")}</div>`;
  });
  es.addEventListener("built",e=>{
    const d=JSON.parse(e.data); builtTools.push(d.name);
    document.getElementById("at-results").insertAdjacentHTML("beforeend",`<div style="display:flex;align-items:center;gap:7px;padding:5px 9px;background:rgba(86,207,178,.08);border-radius:5px;margin-bottom:4px;font-size:12px"><span style="color:var(--grn)">✅</span><strong>${d.name}</strong> — ${d.description}</div>`);
  });
  es.addEventListener("build_error",e=>{
    const d=JSON.parse(e.data);
    document.getElementById("at-results").insertAdjacentHTML("beforeend",`<div style="display:flex;gap:7px;padding:5px 9px;background:rgba(240,112,112,.08);border-radius:5px;margin-bottom:4px;font-size:12px"><span style="color:var(--red)">❌</span><strong>${d.name}</strong> — ${d.error}</div>`);
  });
  es.addEventListener("done",()=>{ es.close(); document.getElementById("at-stat").style.display="none"; btn.disabled=false; loadSI(); if(builtTools.length>=2) document.getElementById("at-chain-wrap").style.display="block"; toast(`🎉 Built ${builtTools.length} tools!`); });
  es.addEventListener("error",e=>{ es.close(); try{toast("❌ "+JSON.parse(e.data).msg);}catch{} btn.disabled=false; });
}

function chainBuiltTools(){
  if(builtTools.length<2) return;
  V("chain");
  setTimeout(()=>{
    document.querySelectorAll("#chain-list .cb-item").forEach(el=>{ if(builtTools.includes(el.dataset.name)) el.classList.add("sel"),el.querySelector("input").checked=true; });
    const goal=document.getElementById("atd").value.trim();
    if(goal) document.getElementById("ch-goal").value=goal;
  },150);
}

function startImprove(){
  const name=document.getElementById("im-sel").value; if(!name) return;
  const what=document.getElementById("im-what").value.trim()||"make it better and more robust";
  const es=mkStream(`/api/improve/stream?name=${enc(name)}&what=${enc(what)}`,{outId:"im-out",statId:"im-stat",stxtId:"im-stxt",alId:null,crId:"im-cr",ctitId:"im-ctit",ctagsId:"im-ctags",cpreId:"im-cpre",verdId:null,nameId:"im-name",pfx:"im",btnId:"im-btn"});
  es.addEventListener("code",e=>{ document.getElementById("im-name").value=JSON.parse(e.data).original_name||slug(JSON.parse(e.data).description); });
}

function startRemix(){
  const t1=document.getElementById("rx-t1").value, t2=document.getElementById("rx-t2").value;
  if(!t1||!t2||t1===t2){ toast("Pick two different tools!"); return; }
  const goal=document.getElementById("rx-goal").value.trim()||"combine the best of both";
  const es=mkStream(`/api/remix/stream?tool1=${enc(t1)}&tool2=${enc(t2)}&goal=${enc(goal)}`,{outId:"rx-out",statId:"rx-stat",stxtId:"rx-stxt",alId:null,crId:"rx-cr",ctitId:"rx-ctit",ctagsId:"rx-ctags",cpreId:"rx-cpre",verdId:null,nameId:"rx-name",pfx:"rx",btnId:"rx-btn"});
  es.addEventListener("code",e=>{ document.getElementById("rx-name").value=JSON.parse(e.data).remix_name||"remixed_tool"; });
}

function startChain(){
  const sel=[...document.querySelectorAll("#chain-list .cb-item.sel")].map(e=>e.dataset.name);
  if(sel.length<2){ toast("Select at least 2 tools!"); return; }
  const goal=document.getElementById("ch-goal").value.trim()||"process data end to end";
  const es=mkStream(`/api/chain/stream?tools=${enc(sel.join(","))}&goal=${enc(goal)}`,{outId:"ch-out",statId:"ch-stat",stxtId:"ch-stxt",alId:null,crId:"ch-cr",ctitId:"ch-ctit",ctagsId:"ch-ctags",cpreId:"ch-cpre",verdId:null,nameId:"ch-name",pfx:"ch",btnId:"ch-btn"});
  es.addEventListener("code",e=>{ document.getElementById("ch-name").value=JSON.parse(e.data).pipeline_name||"pipeline"; });
}

function startTest(){
  const name=document.getElementById("ts-sel").value; if(!name) return;
  const btn=document.getElementById("ts-btn");
  document.getElementById("ts-out").style.display="block";
  document.getElementById("ts-stat").style.display="flex";
  document.getElementById("ts-code-wrap").style.display="none";
  document.getElementById("ts-res-wrap").style.display="none";
  btn.disabled=true;
  const es=new EventSource(`/api/test/stream?name=${enc(name)}`);
  es.addEventListener("status",e=>{ document.getElementById("ts-stxt").textContent=JSON.parse(e.data).msg; });
  es.addEventListener("test_code",e=>{ document.getElementById("ts-cpre").textContent=JSON.parse(e.data).code; document.getElementById("ts-code-wrap").style.display="block"; });
  es.addEventListener("test_result",e=>{
    const {output,passed}=JSON.parse(e.data);
    document.getElementById("ts-out-txt").textContent=output;
    document.getElementById("ts-res-wrap").style.display="block";
    document.getElementById("ts-verd").innerHTML=passed?`<span style="color:var(--grn)">✅ All tests passed!</span>`:`<span style="color:var(--red)">❌ Some tests failed.</span>`;
  });
  es.addEventListener("done",()=>{ es.close(); document.getElementById("ts-stat").style.display="none"; btn.disabled=false; toast("🧪 Tests done!"); });
  es.addEventListener("error",e=>{ es.close(); try{toast("❌ "+JSON.parse(e.data).msg);}catch{} btn.disabled=false; });
}

function startWeb(){
  const d=document.getElementById("wb-desc").value.trim(); if(!d) return;
  mkStream(`/api/web/stream?description=${enc(d)}`,{outId:"wb-out",statId:"wb-stat",stxtId:"wb-stxt",alId:null,crId:"wb-cr",ctitId:"wb-ctit",ctagsId:"wb-ctags",cpreId:"wb-cpre",verdId:null,nameId:"wb-name",pfx:"wb",btnId:"wb-btn"});
}

async function doFetch(){
  const url=document.getElementById("fu-url").value.trim(); if(!url) return;
  const btn=document.getElementById("fu-btn"); btn.disabled=true; btn.textContent="Fetching...";
  document.getElementById("fu-res").style.display="none";
  try{
    const r=await f(`/api/fetch?url=${enc(url)}`);
    document.getElementById("fu-lbl").textContent="📄 "+r.url;
    document.getElementById("fu-sum").textContent=r.summary;
    document.getElementById("fu-res").style.display="block";
  }catch(e){ toast("❌ "+e.message); }
  btn.disabled=false; btn.textContent="Fetch 📄";
}

async function saveCurrent(pfx){
  const nameEl=document.getElementById(pfx+"-name"), name=(nameEl?.value||"").trim();
  if(!name||!codes[pfx]){ toast("Enter a name first!"); return; }
  await post("/api/save",{name,description:descs[pfx],code:codes[pfx],tags:tagss[pfx]});
  toast("✅ Saved: "+name); loadSI();
}
function copyCurrent(pfx){ if(codes[pfx]) navigator.clipboard.writeText(codes[pfx]),toast("📋 Copied!"); }

async function loadTools(){
  renderGrid(await f("/api/tools"),"tg","ftg");
}
function renderGrid(reg,gridId,tagsId){
  const grid=document.getElementById(gridId), tagsEl=tagsId?document.getElementById(tagsId):null;
  const entries=Object.entries(reg);
  if(!entries.length){ grid.innerHTML=`<div class="empty"><div class="ei">📭</div>No tools found.</div>`; if(tagsEl) tagsEl.innerHTML=""; return; }
  if(tagsEl){
    const tc={};
    entries.forEach(([,v])=>(v.tags||[]).forEach(t=>tc[t]=(tc[t]||0)+1));
    tagsEl.innerHTML=`<span class="ft ${!activeFilter?"active":""}" onclick="filterTools(null)">All</span>`+Object.entries(tc).sort((a,b)=>b[1]-a[1]).slice(0,8).map(([t,c])=>`<span class="ft ${activeFilter===t?"active":""}" onclick="filterTools('${t}')">${t} <span style="opacity:.5">${c}</span></span>`).join("");
  }
  const shown=activeFilter?entries.filter(([,v])=>(v.tags||[]).includes(activeFilter)):entries;
  grid.innerHTML=shown.map(([n,i])=>`<div class="tc" onclick="openTool('${n}')"><h3>${n}</h3><p>${i.description}</p><div class="tm"><span style="color:var(--acc2)">▶ ${i.runs||0}</span>${i.rating?`<span style="color:var(--ylw)">${"⭐".repeat(i.rating)}</span>`:""}${i.test_status==="passed"?`<span style="color:var(--grn)">✓ tested</span>`:""}<span class="badge">v${i.version||1}</span>${(i.tags||[]).slice(0,2).map(t=>`<span class="badge">${t}</span>`).join("")}</div></div>`).join("")||`<div class="empty"><div class="ei">🔍</div>No matches.</div>`;
}
function filterTools(tag){ activeFilter=tag; loadTools(); }

function doSearch(){
  clearTimeout(searchT);
  searchT=setTimeout(async()=>{
    const q=document.getElementById("sq").value.trim();
    if(!q){ document.getElementById("sr").innerHTML=`<div class="empty"><div class="ei">🔍</div>Start typing...</div>`; return; }
    renderGrid(await f(`/api/search?q=${enc(q)}`), "sr", null);
  },280);
}

async function loadSelects(){
  const reg=await f("/api/tools");
  const opts=Object.entries(reg).map(([n,i])=>`<option value="${n}">${n} — ${i.description.substring(0,40)}</option>`).join("")||"<option>No tools yet</option>";
  ["im-sel","ts-sel"].forEach(id=>{ const el=document.getElementById(id); if(el) el.innerHTML=opts; });
}

async function loadRemixSels(){
  const reg=await f("/api/tools");
  const opts=Object.entries(reg).map(([n])=>`<option value="${n}">${n}</option>`).join("")||"<option>No tools</option>";
  ["rx-t1","rx-t2"].forEach(id=>{ const el=document.getElementById(id); if(el) el.innerHTML=opts; });
}

async function loadChainList(){
  const reg=await f("/api/tools"), el=document.getElementById("chain-list");
  if(!Object.keys(reg).length){ el.innerHTML=`<p style="color:var(--mu);font-size:12px">No tools yet. Build some first!</p>`; return; }
  el.innerHTML=Object.entries(reg).map(([n,i])=>`<div class="cb-item" data-name="${n}" onclick="toggleCB(this)"><input type="checkbox"><div><div style="font-size:12px;font-weight:600">${n}</div><div style="font-size:11px;color:var(--mu)">${i.description.substring(0,50)}</div></div></div>`).join("");
}
function toggleCB(el){ el.classList.toggle("sel"); el.querySelector("input").checked=el.classList.contains("sel"); }

async function openTool(name){
  const reg=await f("/api/tools"), i=reg[name]; if(!i) return;
  const cd=await f(`/api/tool/${name}/code`);
  curMoTool=name;
  document.getElementById("mo-title").textContent=name;
  document.getElementById("mo-desc").textContent=i.description;
  document.getElementById("mo-tags").innerHTML=(i.tags||[]).map(t=>`<span class="tag">${t}</span>`).join("");
  document.getElementById("mo-meta").innerHTML=`<span style="color:var(--acc2)">▶ ${i.runs||0} runs</span><span class="badge">v${i.version||1}</span><span style="${i.test_status==="passed"?"color:var(--grn)":""}">${i.test_status||"untested"}</span>`;
  document.getElementById("mo-code").textContent=cd.code;
  document.getElementById("mo-exp-wrap").style.display="none";
  document.getElementById("mo-exp-btn").textContent="📖 Explain";
  document.querySelectorAll("#mo-stars .star").forEach(s=>s.classList.toggle("lit",parseInt(s.dataset.v)<=(i.rating||0)));
  document.getElementById("tool-mo").classList.add("open");
}
function closeMo(){ document.getElementById("tool-mo").classList.remove("open"); curMoTool=null; }

async function handleStar(e){
  const s=e.target.closest(".star"); if(!s||!curMoTool) return;
  const r=parseInt(s.dataset.v);
  await post(`/api/tool/${curMoTool}/rate`,{rating:r});
  document.querySelectorAll("#mo-stars .star").forEach(s=>s.classList.toggle("lit",parseInt(s.dataset.v)<=r));
  toast(`⭐ Rated ${r}/5`);
}
async function deleteTool(){
  if(!curMoTool||!confirm(`Delete "${curMoTool}"?`)) return;
  await post(`/api/tool/${curMoTool}/delete`,{}); closeMo(); loadTools(); loadSI(); toast("🗑️ Deleted");
}
async function explainTool(){
  if(!curMoTool) return;
  const btn=document.getElementById("mo-exp-btn"); btn.textContent="⏳..."; btn.disabled=true;
  const r=await f(`/api/tool/${curMoTool}/explain`);
  document.getElementById("mo-exp").textContent=r.explanation;
  document.getElementById("mo-exp-wrap").style.display="block";
  btn.textContent="📖 Explanation ↑"; btn.disabled=false;
}
function exportTool(){ if(curMoTool){ window.open(`/api/tool/${curMoTool}/export`,"_blank"); toast("📦 Downloading..."); } }
function copyMoCode(){ navigator.clipboard.writeText(document.getElementById("mo-code").textContent); toast("📋 Copied!"); }

async function loadStats(){
  const s=await f("/api/stats");
  document.getElementById("sg").innerHTML=[["Tools",s.total],["Runs",s.runs],["Tested",s.tested],["Avg ⭐",s.avg_rating||"─"],["Sessions",s.sessions],["🧠 Insights",s.insights]].map(([l,v])=>`<div class="sc"><div class="sn">${v}</div><div class="sl">${l}</div></div>`).join("");
  if(s.top_tags?.length){
    const max=s.top_tags[0].count;
    document.getElementById("tc").innerHTML=s.top_tags.map(({tag,count})=>`<div style="flex:1;min-width:80px;background:var(--s2);border-radius:7px;padding:10px;border:1px solid var(--b);text-align:center"><div style="font-size:16px;font-weight:700;color:var(--acc)">${count}</div><div style="font-size:11px;color:var(--mu);margin-top:2px">${tag}</div><div style="height:3px;background:var(--b);border-radius:2px;margin-top:6px;overflow:hidden"><div style="height:100%;width:${Math.round(count/max*100)}%;background:var(--acc);border-radius:2px"></div></div></div>`).join("");
  }
}

async function loadMemory(){
  const m=await f("/api/memory");
  document.getElementById("mc").innerHTML=`
    <div class="sect">📜 Build History</div>
    ${m.history.slice().reverse().map(e=>`<div class="mi"><span>${e.success?"✅":"❌"}</span><div><strong style="font-size:12px">${e.tool}</strong> — <span style="color:var(--mu)">${(e.description||"").substring(0,55)}</span>${e.rating?` ${"⭐".repeat(e.rating)}`:""}  <div class="mit">${new Date(e.timestamp).toLocaleDateString()}</div></div></div>`).join("")||`<p style="color:var(--mu);font-size:12px">No history yet.</p>`}
    ${m.insights.length?`<div class="sect" style="margin-top:12px">💡 Insights</div>${m.insights.map(i=>`<div class="mi"><span>💡</span><div style="font-size:12px">${i}</div></div>`).join("")}`:""}
    ${m.user_style?`<div class="sect" style="margin-top:12px">⚙️ Coding Style</div><div style="background:var(--s2);border-radius:7px;padding:10px;font-size:12px;color:var(--mu)">${m.user_style}</div>`:""}
  `;
}

function showMini(title, placeholder, mode){
  document.getElementById("mini-ttl").textContent=title;
  document.getElementById("mini-inp").placeholder=placeholder;
  document.getElementById("mini-inp").value="";
  miniMode=mode;
  document.getElementById("mini-mo").classList.add("open");
}
async function submitMini(){
  const v=document.getElementById("mini-inp").value.trim(); if(!v) return;
  if(miniMode==="style") await post("/api/memory/style",{style:v});
  else if(miniMode==="insight") await post("/api/memory/insight",{insight:v});
  toast("✅ Saved!"); closeMini(); loadMemory();
}
function closeMini(){ document.getElementById("mini-mo").classList.remove("open"); miniMode=null; }

async function clearMemory(){
  if(!confirm("Clear ALL memory?")) return;
  await post("/api/memory/clear",{}); toast("🗑️ Cleared"); loadMemory();
}

async function f(url){ const r=await fetch(url); if(!r.ok) throw new Error(await r.text()); return r.json(); }
async function post(url,data){ return(await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)})).json(); }
const enc=s=>encodeURIComponent(s);
const esc=s=>s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
const slug=s=>s.toLowerCase().replace(/\s+/g,"_").replace(/[^\w]/g,"").substring(0,30)||"tool";
function toast(msg){ const el=document.getElementById("toast"); el.textContent=msg; el.classList.add("show"); setTimeout(()=>el.classList.remove("show"),2500); }
["tool-mo","mini-mo"].forEach(id=>document.getElementById(id).addEventListener("click",function(e){ if(e.target===this) this.classList.remove("open"); }));
</script>
</body>
</html>"""

if __name__ == "__main__":
    print("\n╔═════════════════════════════════════════════════════╗")
    print("║  🛠️   AI Tool-Maker Web UI — FULL EDITION            ║")
    print("║  Open: http://localhost:5000                         ║")
    print("╚═════════════════════════════════════════════════════╝\n")
    app.run(debug=False, port=5000, threaded=True)
