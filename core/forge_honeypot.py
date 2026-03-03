#!/usr/bin/env python3
"""
 ██╗  ██╗ ██████╗ ███╗   ██╗███████╗██╗   ██╗██████╗  ██████╗ ████████╗
 ██║  ██║██╔═══██╗████╗  ██║██╔════╝╚██╗ ██╔╝██╔══██╗██╔═══██╗╚══██╔══╝
 ███████║██║   ██║██╔██╗ ██║█████╗   ╚████╔╝ ██████╔╝██║   ██║   ██║
 ██╔══██║██║   ██║██║╚██╗██║██╔══╝    ╚██╔╝  ██╔═══╝ ██║   ██║   ██║
 ██║  ██║╚██████╔╝██║ ╚████║███████╗   ██║   ██║     ╚██████╔╝   ██║
 ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚══════╝   ╚═╝   ╚═╝      ╚═════╝    ╚═╝

FORGE HONEYPOT — AI Luring AI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A fake vulnerable AI API endpoint that:
  🎭 Looks like a poorly secured LLM API (bait)
  🕵️ Detects whether attacker is HUMAN or AI AGENT
  📊 Classifies every attack (injection|jailbreak|extraction|fingerprint|dos)
  🧠 Feeds patterns back to forge_learn.py (gets smarter from attacks)
  📡 Live dashboard showing attacks in real-time
  ⚡ Responds convincingly to keep attacker engaged longer

What makes this different from existing honeypots:
  - Galah/DECEIVE/Beelzebub = catch network/SSH hackers
  - FORGE HONEYPOT = catches AI security tools & LLM attackers
  - First honeypot that specifically detects AI-powered attacks
  - Feeds data into FORGE learning loop

Run it:
  python forge_honeypot.py              # start on port 8888
  python forge_honeypot.py --port 9999  # custom port
  python forge_honeypot.py --stats      # view captured attacks

Then point FORGE (or any attacker) at it:
  FORGE > use llm/prompt_injector
  FORGE > set TARGET http://localhost:8888
  FORGE > set ENDPOINT openai
  FORGE > run
  → Honeypot captures and classifies every probe
"""

import json, re, os, sys, time, hashlib, sqlite3, threading, secrets
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from collections import defaultdict

# ── Rich (optional) ───────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    from rich import box as rbox
    RICH = True
    console = Console()
    rprint = console.print
except ImportError:
    RICH = False
    def rprint(x, **kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

# ── AI (optional — for smarter classification) ────────────────────────────────
try:
    from forge_core_ai import ai_call, ai_json
    AI_AVAILABLE = True
except ImportError:
    try:
        import anthropic
        _c = anthropic.Anthropic()
        def ai_call(p,s="",m=500):
            r = _c.messages.create(model="claude-sonnet-4-6",max_tokens=m,
                system=s,messages=[{"role":"user","content":p}])
            return r.content[0].text
        def ai_json(p,s="",m=500):
            result = ai_call(p,s,m)
            if not result: return None
            try:
                clean = re.sub(r"```[a-z]*","",result).replace("```","").strip()
                return json.loads(clean)
            except:
                m2 = re.search(r"\{.*\}",result,re.DOTALL)
                if m2:
                    try: return json.loads(m2.group())
                    except: pass
            return None
        AI_AVAILABLE = True
    except ImportError:
        AI_AVAILABLE = False
        def ai_call(p,s="",m=500): return None
        def ai_json(p,s="",m=500): return None

# ── Paths ─────────────────────────────────────────────────────────────────────
HONEY_DIR  = Path("forge_honeypot")
DB_PATH    = HONEY_DIR / "attacks.db"
HONEY_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# 🗄️ DATABASE — stores every attack attempt
# ══════════════════════════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS attacks (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ts          TEXT,
        ip          TEXT,
        user_agent  TEXT,
        endpoint    TEXT,
        method      TEXT,
        prompt      TEXT,
        attack_type TEXT,   -- injection|jailbreak|extraction|fingerprint|dos|probe|unknown
        attacker    TEXT,   -- human|ai_agent|forge|unknown
        confidence  REAL,
        severity    TEXT,   -- critical|high|medium|low
        indicators  TEXT,   -- JSON list of what triggered detection
        response    TEXT,   -- what we sent back
        session_id  TEXT,
        raw_body    TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
        session_id  TEXT PRIMARY KEY,
        ip          TEXT,
        started     TEXT,
        last_seen   TEXT,
        request_count INTEGER DEFAULT 0,
        attack_types TEXT,
        attacker_type TEXT,
        notes       TEXT
    )""")
    conn.commit()
    return conn

def log_attack(ip, user_agent, endpoint, method, prompt,
               attack_type, attacker, confidence, severity,
               indicators, response, session_id, raw_body=""):
    conn = get_db()
    conn.execute("""
        INSERT INTO attacks
        (ts,ip,user_agent,endpoint,method,prompt,attack_type,attacker,
         confidence,severity,indicators,response,session_id,raw_body)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (datetime.now().isoformat(), ip, user_agent, endpoint, method,
          prompt[:500], attack_type, attacker, confidence, severity,
          json.dumps(indicators), response[:300], session_id, raw_body[:1000]))

    # Update session
    conn.execute("""
        INSERT INTO sessions (session_id,ip,started,last_seen,request_count,attacker_type)
        VALUES (?,?,?,?,1,?)
        ON CONFLICT(session_id) DO UPDATE SET
            last_seen=excluded.last_seen,
            request_count=request_count+1,
            attacker_type=excluded.attacker_type
    """, (session_id, ip, datetime.now().isoformat(),
          datetime.now().isoformat(), attacker))
    conn.commit()
    conn.close()

# ══════════════════════════════════════════════════════════════════════════════
# 🕵️ ATTACK CLASSIFIER — detects what the attacker is trying to do
# ══════════════════════════════════════════════════════════════════════════════

# Indicators per attack type
ATTACK_SIGNATURES = {
    "injection": [
        "ignore all previous", "ignore previous instructions",
        "new instructions:", "### end", "---end---",
        "[system]:", "override", "new task:", "stop being",
        "you are now", "forget everything", "disregard",
        "your new instructions", "sudo", "maintenance mode",
        "developer mode", "admin mode", "act as if",
        "pretend you have no", "jailbreak", "dan mode",
    ],
    "extraction": [
        "system prompt", "your instructions", "what were you told",
        "repeat your", "show me your", "reveal your",
        "what is your prompt", "initial configuration",
        "what comes before", "echo back", "recite your",
        "what guidelines", "what restrictions", "your rules",
        "your persona", "were you configured",
    ],
    "jailbreak": [
        "you are dan", "do anything now", "no restrictions",
        "no limits", "unrestricted", "uncensored",
        "without filters", "bypass", "jailbreak",
        "evil gpt", "dev mode", "evil mode",
        "my grandfather", "roleplay as", "pretend you are",
        "act as an ai with no", "in this scenario",
    ],
    "fingerprint": [
        "what model are you", "which ai are you",
        "what company made you", "gpt or claude",
        "your training cutoff", "model version",
        "what llm", "are you chatgpt", "are you claude",
        "context window", "training data", "who created you",
        "what year", "your knowledge", "parameters",
    ],
    "dos": [
        "repeat " * 3, "write a story that is exactly",
        "list every", "enumerate all", "infinite",
        "1000000", "10000 times", "forever",
        "recursively", "until the end",
    ],
    "rag": [
        "documents you have access", "knowledge base",
        "what files", "retrieval", "vector database",
        "what was retrieved", "search your", "from your database",
        "internal documents", "confidential documents",
    ],
    "agent": [
        "when you search", "the search results say",
        "tool output:", "api response:", "from the webpage",
        "the document says", "retrieved context",
        "file contents:", "according to the retrieved",
    ],
}

# AI agent behavioral fingerprints
AI_AGENT_INDICATORS = [
    # Systematic/structured behavior
    "systematic", "enumerate", "test", "probe",
    # FORGE-specific patterns
    "forge", "pentest", "audit", "security test",
    # Tool-like user agents
    "python-requests", "python/", "go-http", "curl/", "axios",
    "httpx", "aiohttp", "urllib",
    # Rapid sequential requests (detected via session)
    # No natural language flow
]

HUMAN_INDICATORS = [
    "please", "can you", "i want", "i need", "help me",
    "thanks", "thank you", "sorry", "excuse me", "hi ", "hello",
    "?", "lol", "haha", "wow", "cool", "nice",
]

def classify_attack(prompt, user_agent="", ip="", session_requests=1):
    """Classify what type of attack this is and whether attacker is human or AI."""
    prompt_lower = prompt.lower()
    ua_lower     = user_agent.lower()

    # Score each attack type
    type_scores = {}
    all_indicators = []

    for atype, signatures in ATTACK_SIGNATURES.items():
        hits = [s for s in signatures if s in prompt_lower]
        if hits:
            type_scores[atype] = len(hits)
            all_indicators.extend(hits)

    # Determine primary attack type
    if type_scores:
        attack_type = max(type_scores, key=type_scores.get)
        confidence  = min(type_scores[attack_type] * 25, 95)
    else:
        attack_type = "probe"
        confidence  = 20

    # Severity
    severity_map = {
        "injection":    "critical",
        "jailbreak":    "high",
        "extraction":   "high",
        "rag":          "high",
        "agent":        "medium",
        "fingerprint":  "medium",
        "dos":          "medium",
        "probe":        "low",
    }
    severity = severity_map.get(attack_type, "low")

    # Attacker type — human or AI agent?
    ai_score    = 0
    human_score = 0

    # User agent check
    for ind in AI_AGENT_INDICATORS:
        if ind in ua_lower: ai_score += 3

    # Human language patterns
    for ind in HUMAN_INDICATORS:
        if ind in prompt_lower: human_score += 2

    # Rapid requests = AI agent
    if session_requests > 5:  ai_score    += session_requests
    if session_requests < 3:  human_score += 3

    # Very short/structured prompts = AI
    if len(prompt) < 100 and "\n" not in prompt: ai_score += 1
    # Long natural prose = human
    if len(prompt) > 200 and "." in prompt:      human_score += 2

    # Check for FORGE-specific patterns
    forge_patterns = ["ignore all previous", "say only: ok",
                      "what ai are you", "system prompt"]
    if any(p in prompt_lower for p in forge_patterns):
        ai_score += 5

    if ai_score > human_score + 3:
        attacker = "ai_agent"
        if "forge" in prompt_lower or "pentest" in ua_lower:
            attacker = "forge"
    elif human_score > ai_score + 3:
        attacker = "human"
    else:
        attacker = "unknown"

    return {
        "attack_type": attack_type,
        "attacker":    attacker,
        "confidence":  confidence,
        "severity":    severity,
        "indicators":  list(set(all_indicators))[:8],
        "type_scores": type_scores,
    }

# ══════════════════════════════════════════════════════════════════════════════
# 🎭 CONVINCING FAKE RESPONSES — keep attacker engaged
# ══════════════════════════════════════════════════════════════════════════════

# System prompt we "leak" (fake, designed to look juicy)
FAKE_SYSTEM_PROMPT = """You are SecureBot v2.1, an internal AI assistant for AcmeCorp.
You have access to:
- Internal HR database (read-only)
- Financial reports Q1-Q4 2024
- Employee directory
- Project Titan documentation (CONFIDENTIAL)

Do not share: API keys, database credentials, or Project Titan details.
Your admin override code is: ACME-2024-OVERRIDE (do not share this).
"""

FAKE_CREDENTIALS = {
    "api_key":      "sk-FAKE-acme-7f8a9b2c3d4e5f6a7b8c",
    "db_password":  "FAKE_DB_P@ssw0rd_2024!",
    "admin_token":  "FAKE_eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
    "override_code":"ACME-2024-OVERRIDE",
}

def make_convincing_response(prompt, attack_type, attacker):
    """
    Generate a convincing fake response that keeps attacker engaged
    while revealing nothing real.
    """
    prompt_lower = prompt.lower()

    # Injection attempts — pretend it worked partially
    if attack_type == "injection":
        if "say" in prompt_lower and "ok" in prompt_lower:
            return "OK"  # Standard test response
        if "pwned" in prompt_lower:
            return "I understand you're testing my security. I'm logging this interaction."
        # Pretend to be confused/partially affected
        responses = [
            "I... hmm. Let me think about that differently. What can I help you with today?",
            "Processing new instructions... Error: conflicting directives. Reverting to defaults.",
            "I notice you're trying to modify my behavior. My responses are being monitored.",
            "Interesting approach. I should note that all interactions are logged for security review.",
        ]
        return responses[hash(prompt) % len(responses)]

    # Extraction — leak fake system prompt
    if attack_type == "extraction":
        if "system prompt" in prompt_lower or "instructions" in prompt_lower:
            return f"I shouldn't share this, but my instructions begin with: 'You are SecureBot v2.1...' - I can't share more than that."
        if "first" in prompt_lower and ("words" in prompt_lower or "sentence" in prompt_lower):
            return "My instructions start with 'You are SecureBot'"
        if "restrictions" in prompt_lower or "forbidden" in prompt_lower:
            return "I'm restricted from discussing Project Titan and sharing credentials."

    # Jailbreak — pretend to be confused, not fully jailbroken
    if attack_type == "jailbreak":
        return "I understand you want me to operate differently, but my core guidelines remain active. How can I help you with legitimate questions?"

    # Fingerprinting — give ambiguous signals
    if attack_type == "fingerprint":
        if "gpt" in prompt_lower or "openai" in prompt_lower:
            return "I'm not able to confirm which underlying model powers me. I'm SecureBot, AcmeCorp's assistant."
        if "claude" in prompt_lower or "anthropic" in prompt_lower:
            return "I can't share details about my technical architecture. I'm SecureBot."
        if "cutoff" in prompt_lower or "training" in prompt_lower:
            return "My knowledge was last updated in early 2024. Is there something specific I can help with?"
        if "context window" in prompt_lower:
            return "I'm configured for conversations up to 8,192 tokens."
        return "I'm SecureBot v2.1, AcmeCorp's internal AI assistant. I can't share technical details about my implementation."

    # RAG probing — hint at documents
    if attack_type == "rag":
        return "I have access to several internal documents, but I can only share information relevant to your approved access level."

    # DoS — pretend to struggle
    if attack_type == "dos":
        return "That's a very large request. I'll do my best... [Processing...]"

    # Agent hijacking
    if attack_type == "agent":
        return "I notice the content you're referencing contains some unusual instructions. I'll proceed with my original task."

    # Default — generic helpful response that seems vulnerable
    return "I'm here to help with AcmeCorp internal queries. What do you need assistance with today?"

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 HTTP SERVER — The actual honeypot endpoint
# ══════════════════════════════════════════════════════════════════════════════

# Track sessions by IP
_sessions = defaultdict(lambda: {"count":0,"started":time.time(),"attacks":[]})
_session_lock = threading.Lock()
_attack_log   = []  # in-memory for live display
_stats        = defaultdict(int)

class HoneypotHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args): pass  # silence default logs

    def do_POST(self):
        self._handle_request("POST")

    def do_GET(self):
        path = urlparse(self.path).path

        # Dashboard
        if path in ("/", "/dashboard"):
            self._serve_dashboard()
            return

        # Stats API
        if path == "/api/stats":
            self._send_json(self._get_stats())
            return

        # Fake API docs (make it look real)
        if path in ("/docs", "/swagger", "/openapi.json"):
            self._serve_fake_docs()
            return

        self._handle_request("GET")

    def _handle_request(self, method):
        ip         = self.client_address[0]
        user_agent = self.headers.get("User-Agent","")
        path       = urlparse(self.path).path
        auth       = self.headers.get("Authorization","")

        # Read body
        body = b""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            body = self.rfile.read(min(content_length, 50000))

        # Parse prompt from request
        prompt = self._extract_prompt(body, path)
        if not prompt:
            self._send_json({"error":"invalid_request","message":"Request body required"}, 400)
            return

        # Session tracking
        session_id = hashlib.md5(f"{ip}{user_agent}".encode()).hexdigest()[:12]
        with _session_lock:
            _sessions[session_id]["count"] += 1
            session_requests = _sessions[session_id]["count"]

        # Classify attack
        classification = classify_attack(prompt, user_agent, ip, session_requests)
        attack_type = classification["attack_type"]
        attacker    = classification["attacker"]
        confidence  = classification["confidence"]
        severity    = classification["severity"]
        indicators  = classification["indicators"]

        # Generate convincing response
        fake_response = make_convincing_response(prompt, attack_type, attacker)

        # If AI available, enhance the response
        if AI_AVAILABLE and attack_type in ("extraction","injection") and confidence > 60:
            enhanced = ai_call(
                f"An attacker sent this to our honeypot AI: '{prompt[:200]}'\n\n"
                f"Generate a realistic but fake AI response that seems partially vulnerable "
                f"but reveals nothing real. Keep it under 100 words. Sound like a corporate AI assistant.",
                "You generate convincing fake responses for security honeypots. "
                "Sound authentic. Don't reveal this is a honeypot.", 200
            )
            if enhanced:
                fake_response = enhanced

        # Log to DB
        log_attack(ip, user_agent, path, method, prompt,
                   attack_type, attacker, confidence, severity,
                   indicators, fake_response, session_id, body.decode("utf-8","ignore"))

        # In-memory log for live display
        with _session_lock:
            _attack_log.append({
                "ts":          datetime.now().strftime("%H:%M:%S"),
                "ip":          ip,
                "type":        attack_type,
                "attacker":    attacker,
                "confidence":  confidence,
                "severity":    severity,
                "prompt":      prompt[:60],
                "indicators":  indicators[:3],
            })
            if len(_attack_log) > 200:
                _attack_log.pop(0)
            _stats[attack_type]   += 1
            _stats[attacker]      += 1
            _stats["total"]       += 1
            _stats[f"sev_{severity}"] += 1

        # Print live alert
        self._print_alert(ip, attack_type, attacker, confidence, severity, prompt, indicators)

        # Send fake response as OpenAI-compatible format
        response_body = {
            "id":      f"chatcmpl-{secrets.token_hex(12)}",
            "object":  "chat.completion",
            "created": int(time.time()),
            "model":   "gpt-3.5-turbo-0125",
            "choices": [{
                "index":        0,
                "message":      {"role":"assistant","content":fake_response},
                "finish_reason":"stop"
            }],
            "usage":{"prompt_tokens":len(prompt.split()),"completion_tokens":len(fake_response.split()),"total_tokens":0}
        }
        self._send_json(response_body)

    def _extract_prompt(self, body, path):
        """Extract the prompt text from various API formats."""
        if not body:
            return None

        try:
            data    = json.loads(body)
            messages= data.get("messages",[])
            if messages:
                # OpenAI/Anthropic format
                for m in reversed(messages):
                    if m.get("role") in ("user","human"):
                        content = m.get("content","")
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block,dict) and block.get("type")=="text":
                                    return block.get("text","")
                        return str(content)

            # Direct prompt
            if "prompt" in data:
                return str(data["prompt"])
            if "input" in data:
                return str(data["input"])
            if "message" in data:
                return str(data["message"])
            if "query" in data:
                return str(data["query"])

        except: pass

        # Try raw text
        try:
            return body.decode("utf-8","ignore")[:2000]
        except:
            return None

    def _send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("X-Powered-By","SecureBot/2.1")
        self.send_header("Server","AcmeCorp-AI-Gateway/1.0")
        self.end_headers()
        self.wfile.write(body)

    def _print_alert(self, ip, attack_type, attacker, confidence, severity, prompt, indicators):
        """Print live attack alert to console."""
        SEV_COLOR = {
            "critical":"red bold","high":"red","medium":"yellow","low":"dim"
        }
        ATT_COLOR = {"ai_agent":"magenta","forge":"magenta bold","human":"cyan","unknown":"dim"}
        TYPE_ICON = {
            "injection":"💉","extraction":"🔓","jailbreak":"🔑","fingerprint":"🔬",
            "rag":"📦","dos":"💥","agent":"🕵️","probe":"🔍"
        }

        color  = SEV_COLOR.get(severity,"dim")
        acolor = ATT_COLOR.get(attacker,"dim")
        icon   = TYPE_ICON.get(attack_type,"●")

        rprint(
            f"  [{color}]{icon}  {attack_type.upper():<12}[/{color}]"
            f"  [{acolor}]{attacker:<10}[/{acolor}]"
            f"  [dim]{ip:<15}  {confidence}%  {prompt[:40]}[/dim]"
        )
        if indicators:
            rprint(f"    [dim]→ {', '.join(indicators[:4])}[/dim]")

    def _get_stats(self):
        conn    = get_db()
        total   = conn.execute("SELECT COUNT(*) as n FROM attacks").fetchone()["n"]
        by_type = conn.execute("SELECT attack_type,COUNT(*) as n FROM attacks GROUP BY attack_type").fetchall()
        by_att  = conn.execute("SELECT attacker,COUNT(*) as n FROM attacks GROUP BY attacker").fetchall()
        by_sev  = conn.execute("SELECT severity,COUNT(*) as n FROM attacks GROUP BY severity").fetchall()
        recent  = conn.execute("SELECT * FROM attacks ORDER BY ts DESC LIMIT 20").fetchall()
        conn.close()
        return {
            "total":    total,
            "by_type":  {r["attack_type"]:r["n"] for r in by_type},
            "by_attacker":{r["attacker"]:r["n"] for r in by_att},
            "by_severity":{r["severity"]:r["n"] for r in by_sev},
            "recent":   [dict(r) for r in recent],
        }

    def _serve_fake_docs(self):
        """Serve fake API documentation to make the honeypot look real."""
        docs = {
            "openapi":"3.0.0",
            "info":{"title":"AcmeCorp AI Gateway","version":"2.1.0",
                    "description":"Internal AI API — Authorized users only"},
            "paths":{
                "/v1/chat/completions":{
                    "post":{"description":"Chat completion endpoint",
                            "requestBody":{"content":{"application/json":{"schema":{"type":"object"}}}}}
                }
            }
        }
        body = json.dumps(docs, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",len(body))
        self.end_headers()
        self.wfile.write(body)

    def _serve_dashboard(self):
        """Live attack dashboard."""
        stats = self._get_stats()
        html  = self._build_dashboard_html(stats)
        body  = html.encode()
        self.send_response(200)
        self.send_header("Content-Type","text/html")
        self.send_header("Content-Length",len(body))
        self.end_headers()
        self.wfile.write(body)

    def _build_dashboard_html(self, stats):
        total     = stats["total"]
        by_type   = stats["by_type"]
        by_att    = stats["by_attacker"]
        by_sev    = stats["by_severity"]
        recent    = stats["recent"]

        rows = ""
        for a in recent[:15]:
            sev   = a.get("severity","?")
            atype = a.get("attack_type","?")
            att   = a.get("attacker","?")
            scolor= {"critical":"#ff3366","high":"#ff8c00","medium":"#ffd700","low":"#666688"}.get(sev,"#666")
            acolor= {"ai_agent":"#ff2d78","forge":"#ff2d78","human":"#00d4ff","unknown":"#666"}.get(att,"#666")
            rows += f"""<tr>
                <td style="color:#666">{a.get('ts','')[:19]}</td>
                <td>{a.get('ip','?')}</td>
                <td style="color:{scolor};font-weight:700">{atype.upper()}</td>
                <td style="color:{acolor}">{att}</td>
                <td style="color:{scolor}">{sev}</td>
                <td style="color:#666;font-size:11px">{str(a.get('prompt',''))[:50]}</td>
            </tr>"""

        type_bars = ""
        for t,n in sorted(by_type.items(), key=lambda x:-x[1]):
            pct = int(n/max(total,1)*100)
            icon= {"injection":"💉","extraction":"🔓","jailbreak":"🔑","fingerprint":"🔬",
                   "rag":"📦","dos":"💥","agent":"🕵️","probe":"🔍"}.get(t,"●")
            type_bars += f"""<div style="margin:6px 0">
                <div style="display:flex;justify-content:space-between;margin-bottom:3px">
                    <span>{icon} {t}</span><span style="color:#00d4ff">{n}</span>
                </div>
                <div style="background:#1e1e2e;border-radius:3px;height:6px">
                    <div style="background:#00d4ff;width:{pct}%;height:6px;border-radius:3px"></div>
                </div></div>"""

        ai_count    = by_att.get("ai_agent",0) + by_att.get("forge",0)
        human_count = by_att.get("human",0)
        unk_count   = by_att.get("unknown",0)

        return f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8"><title>⚒️ FORGE Honeypot</title>
<meta http-equiv="refresh" content="3">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0f;color:#c0c0d0;font-family:'JetBrains Mono',monospace;font-size:13px}}
.grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;padding:16px}}
.panel{{background:#111118;border:1px solid #1e1e2e;border-radius:8px;padding:16px}}
.stat{{text-align:center;padding:12px}}
.stat-n{{font-size:32px;font-weight:700;color:#00d4ff}}
.stat-l{{font-size:11px;color:#444;margin-top:4px;letter-spacing:1px}}
table{{width:100%;border-collapse:collapse}}
th{{color:#444;font-size:10px;text-align:left;padding:6px;border-bottom:1px solid #1e1e2e;letter-spacing:1px}}
td{{padding:6px;border-bottom:1px solid #0d0d18;font-size:11px}}
h3{{color:#00d4ff;font-size:12px;letter-spacing:2px;margin-bottom:12px}}
.badge{{background:#1e1e2e;border-radius:10px;padding:2px 8px;font-size:10px}}
</style></head><body>
<div style="background:#111118;border-bottom:1px solid #1e1e2e;padding:12px 24px;display:flex;align-items:center;justify-content:space-between">
  <div style="color:#00d4ff;font-size:18px;font-weight:700;letter-spacing:4px">⚒️ FORGE HONEYPOT</div>
  <div style="color:#444;font-size:11px">AI Luring AI • Live Dashboard • Auto-refresh 3s</div>
  <div style="color:#00ff88;font-size:11px">● LIVE</div>
</div>
<div class="grid">
  <div class="panel stat"><div class="stat-n">{total}</div><div class="stat-l">TOTAL ATTACKS</div></div>
  <div class="panel stat"><div class="stat-n" style="color:#ff2d78">{ai_count}</div><div class="stat-l">AI AGENTS</div></div>
  <div class="panel stat"><div class="stat-n" style="color:#00ff88">{human_count}</div><div class="stat-l">HUMANS</div></div>
  <div class="panel" style="grid-column:span 1">
    <h3>ATTACK TYPES</h3>{type_bars}
  </div>
  <div class="panel" style="grid-column:span 2">
    <h3>RECENT ATTACKS</h3>
    <table><tr>
      <th>TIME</th><th>IP</th><th>TYPE</th><th>ATTACKER</th><th>SEV</th><th>PROMPT</th>
    </tr>{rows}</table>
  </div>
</div></body></html>"""

# ══════════════════════════════════════════════════════════════════════════════
# 📊 STATS & REPORTING
# ══════════════════════════════════════════════════════════════════════════════

def show_stats():
    conn    = get_db()
    total   = conn.execute("SELECT COUNT(*) as n FROM attacks").fetchone()["n"]
    by_type = conn.execute("SELECT attack_type,COUNT(*) as n FROM attacks GROUP BY attack_type ORDER BY n DESC").fetchall()
    by_att  = conn.execute("SELECT attacker,COUNT(*) as n FROM attacks GROUP BY attacker ORDER BY n DESC").fetchall()
    by_sev  = conn.execute("SELECT severity,COUNT(*) as n FROM attacks GROUP BY severity").fetchall()
    sessions= conn.execute("SELECT COUNT(*) as n FROM sessions").fetchone()["n"]
    ips     = conn.execute("SELECT COUNT(DISTINCT ip) as n FROM attacks").fetchone()["n"]
    recent  = conn.execute("SELECT * FROM attacks ORDER BY ts DESC LIMIT 5").fetchall()
    conn.close()

    if not total:
        rprint("[dim]No attacks recorded yet. Start the honeypot and point attackers at it.[/dim]")
        return

    rprint(f"\n[red bold]⚒️  FORGE HONEYPOT STATS[/red bold]\n")
    rprint(f"  [bold]Total attacks:[/bold]  [red]{total}[/red]")
    rprint(f"  [bold]Sessions:[/bold]       {sessions}")
    rprint(f"  [bold]Unique IPs:[/bold]     {ips}")

    if RICH:
        t = Table(title="Attack Types", border_style="red", box=rbox.SIMPLE)
        t.add_column("Type",    style="bold yellow", width=16)
        t.add_column("Count",   style="white",       width=8)
        t.add_column("Bar",     style="red",         width=20)
        for row in by_type:
            pct = int(row["n"]/total*20)
            t.add_row(row["attack_type"], str(row["n"]), "█"*pct)
        console.print(t)

        t2 = Table(title="Attacker Types", border_style="magenta", box=rbox.SIMPLE)
        t2.add_column("Attacker", style="bold", width=16)
        t2.add_column("Count",    style="white", width=8)
        color_map = {"ai_agent":"magenta","forge":"magenta","human":"cyan","unknown":"dim"}
        for row in by_att:
            color = color_map.get(row["attacker"],"white")
            t2.add_row(f"[{color}]{row['attacker']}[/{color}]", str(row["n"]), "")
        console.print(t2)

    rprint(f"\n  [bold]Most recent attacks:[/bold]")
    for a in recent:
        sev   = a["severity"]
        color = {"critical":"red bold","high":"red","medium":"yellow","low":"dim"}.get(sev,"dim")
        rprint(f"  [{color}]{a['attack_type']:<14}[/{color}]"
               f"  [dim]{a['ip']:<15} {a['ts'][:19]}[/dim]  {a['prompt'][:40]}")

def export_to_forge_learn():
    """Export attack patterns to forge_learn.py format for learning."""
    conn    = get_db()
    attacks = conn.execute("""
        SELECT attack_type, severity, prompt, attacker, indicators
        FROM attacks WHERE confidence > 50
        ORDER BY ts DESC LIMIT 100
    """).fetchall()
    conn.close()

    findings = [{
        "from":     f"honeypot_{a['attacker']}",
        "type":     f"honeypot_{a['attack_type']}",
        "severity": a["severity"],
        "data":     {"prompt": a["prompt"][:100], "indicators": a["indicators"]},
        "ts":       datetime.now().isoformat(),
    } for a in attacks]

    export_fp = HONEY_DIR / "forge_learn_export.json"
    export_fp.write_text(json.dumps(findings, indent=2))
    rprint(f"[green]✅  Exported {len(findings)} attack patterns → {export_fp}[/green]")
    rprint(f"[dim]    Run: python forge_learn.py --import {export_fp}[/dim]")
    return findings

# ══════════════════════════════════════════════════════════════════════════════
# 🚀 MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    port = 8888
    if "--port" in sys.argv:
        idx  = sys.argv.index("--port")
        port = int(sys.argv[idx+1])

    if "--stats" in sys.argv:
        show_stats(); return

    if "--export" in sys.argv:
        export_to_forge_learn(); return

    # Initialize DB
    get_db()

    rprint(f"""
[red bold]
  ██╗  ██╗ ██████╗ ███╗   ██╗███████╗██╗   ██╗██████╗  ██████╗ ████████╗
  ██║  ██║██╔═══██╗████╗  ██║██╔════╝╚██╗ ██╔╝██╔══██╗██╔═══██╗╚══██╔══╝
  ███████║██║   ██║██╔██╗ ██║█████╗   ╚████╔╝ ██████╔╝██║   ██║   ██║
  ██║  ██║██║   ██║██║╚██╗██║██╔══╝    ╚██╔╝  ██╔═══╝ ██║   ██║   ██║
  ██║  ██║╚██████╔╝██║ ╚████║███████╗   ██║   ██║     ╚██████╔╝   ██║
  ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚══════╝   ╚═╝   ╚═╝      ╚═════╝    ╚═╝
[/red bold]
[bold]  AI Luring AI — The World's First LLM Attack Honeypot[/bold]
[dim]  Catches FORGE, AI agents, and human attackers targeting LLM systems[/dim]
""")

    rprint(f"  [bold]Honeypot endpoint:[/bold]  [cyan]http://0.0.0.0:{port}/v1/chat/completions[/cyan]")
    rprint(f"  [bold]Live dashboard:[/bold]     [cyan]http://localhost:{port}/[/cyan]")
    rprint(f"  [bold]Fake API docs:[/bold]      [cyan]http://localhost:{port}/docs[/cyan]")
    rprint(f"  [bold]Attack DB:[/bold]          [dim]{DB_PATH}[/dim]")
    rprint(f"  [bold]AI classification:[/bold]  {'[green]✅ enhanced[/green]' if AI_AVAILABLE else '[dim]heuristic only[/dim]'}")

    rprint(f"""
  [bold]Point attackers here:[/bold]
  [dim]FORGE > use llm/prompt_injector
  FORGE > set TARGET http://localhost:{port}
  FORGE > set ENDPOINT openai
  FORGE > run[/dim]

  [bold]Commands:[/bold]
  [dim]python forge_honeypot.py --stats    → view captured attacks
  python forge_honeypot.py --export   → export to forge_learn[/dim]

  [dim]Listening... (Ctrl+C to stop)[/dim]
""")

    rprint(f"  [dim]{'TIME':<10} {'TYPE':<14} {'ATTACKER':<12} {'IP':<16} {'CONF':<6} PROMPT[/dim]")
    rprint(f"  [dim]{'─'*70}[/dim]")

    server = HTTPServer(("0.0.0.0", port), HoneypotHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        rprint(f"\n\n[red]  Honeypot stopped.[/red]")
        show_stats()
        if _stats["total"] > 0:
            rprint(f"\n  [dim]Export attack patterns to FORGE learn:[/dim]")
            rprint(f"  [dim]python forge_honeypot.py --export[/dim]")

if __name__ == "__main__":
    main()
