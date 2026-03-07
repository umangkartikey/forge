#!/usr/bin/env python3
"""
FORGE HANDS — Autonomous Digital Action Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FORGE gets hands. Give it a mission in plain English.
It reasons, plans, acts, and reports back.

Three types of hands:
  🖥️  Computer  → browser, mouse, keyboard, screenshots
  🌐  Web       → HTTP, APIs, scraping, forms, webhooks
  🔧  System    → terminal, files, processes, scheduling

Every action is REASONED first — Sherlock explains
why before doing anything. Full audit log always.

Usage:
  python forge_hands.py
  python forge_hands.py --mission "find all subdomains of example.com and screenshot each"
  python forge_hands.py --web "scrape the latest CVEs from nvd.nist.gov"
  python forge_hands.py --system "find all Python files modified today"
  python forge_hands.py --browser "take a screenshot of github.com/umangkartikey"
  python forge_hands.py --server
"""

import sys, os, re, json, time, base64, hashlib, subprocess, shutil
import threading, sqlite3, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime

# ── Optional heavy deps ───────────────────────────────────────────────────────
try:
    import requests
    REQUESTS = True
except ImportError:
    REQUESTS = False

try:
    from bs4 import BeautifulSoup
    BS4 = True
except ImportError:
    BS4 = False

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    PYAUTOGUI = True
except ImportError:
    PYAUTOGUI = False

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT = True
except ImportError:
    PLAYWRIGHT = False

try:
    from PIL import Image
    PIL = True
except ImportError:
    PIL = False

try:
    import psutil
    PSUTIL = True
except ImportError:
    PSUTIL = False

# ── AI ────────────────────────────────────────────────────────────────────────
try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True

    def ai_call(prompt, system="", max_tokens=2000):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or HANDS_SYSTEM,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text

    def ai_json(prompt, system="", max_tokens=1000):
        result = ai_call(prompt, system or "Reply ONLY with valid JSON.", max_tokens)
        try:
            clean = re.sub(r"```[a-z]*","",result).replace("```","").strip()
            return json.loads(clean)
        except:
            m = re.search(r"\{.*\}|\[.*\]", result, re.DOTALL)
            if m:
                try: return json.loads(m.group())
                except: pass
        return None

    def ai_vision(prompt, image_b64, system="", max_tokens=1500):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or HANDS_SYSTEM,
            messages=[{"role":"user","content":[
                {"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":image_b64}},
                {"type":"text","text":prompt}
            ]}]
        )
        return r.content[0].text

except ImportError:
    AI_AVAILABLE = False
    def ai_call(p,s="",m=2000): return "Install anthropic."
    def ai_json(p,s="",m=1000): return None
    def ai_vision(p,b,s="",m=1500): return "Install anthropic."

# ── Rich ──────────────────────────────────────────────────────────────────────
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

# ── System prompts ─────────────────────────────────────────────────────────────
HANDS_SYSTEM = """You are FORGE HANDS — an autonomous action agent.

You execute missions in the real digital world.
Before every action, you reason like Sherlock Holmes:

ACTION REASONING FORMAT:
INTENT:   [what I am about to do]
BECAUSE:  [why this advances the mission]
RISK:     [what could go wrong]
FALLBACK: [what I do if it fails]
EXECUTE:  [the actual action]

You are precise, efficient, and always explain your thinking.
You never take irreversible actions without explicit confirmation.
You log everything. You learn from failures."""

PLANNER_SYSTEM = """You are a mission planner for an autonomous AI agent.

Break any mission into atomic, executable steps.
Each step must be:
- One clear action
- Verifiable (can confirm success/failure)
- Safe (reversible where possible)
- Typed correctly (web/computer/system/ai)

Output ONLY valid JSON."""

# ── Paths ─────────────────────────────────────────────────────────────────────
HANDS_DIR    = Path("forge_hands")
SCREENSHOTS  = HANDS_DIR / "screenshots"
DOWNLOADS    = HANDS_DIR / "downloads"
MISSIONS_DIR = HANDS_DIR / "missions"
DB_PATH      = HANDS_DIR / "hands.db"

for d in [HANDS_DIR, SCREENSHOTS, DOWNLOADS, MISSIONS_DIR]:
    d.mkdir(exist_ok=True)

# ── Database ──────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS missions (
            id          TEXT PRIMARY KEY,
            name        TEXT,
            goal        TEXT,
            status      TEXT DEFAULT 'pending',
            created     TEXT,
            completed   TEXT,
            steps_total INTEGER DEFAULT 0,
            steps_done  INTEGER DEFAULT 0,
            result      TEXT,
            error       TEXT
        );
        CREATE TABLE IF NOT EXISTS actions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id  TEXT,
            step_num    INTEGER,
            action_type TEXT,
            description TEXT,
            reasoning   TEXT,
            result      TEXT,
            success     INTEGER DEFAULT 0,
            ts          TEXT,
            duration_ms INTEGER
        );
        CREATE TABLE IF NOT EXISTS screenshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id  TEXT,
            ts          TEXT,
            filepath    TEXT,
            url         TEXT,
            description TEXT
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 📋 MISSION CLASS
# ══════════════════════════════════════════════════════════════════════════════

class Mission:
    def __init__(self, goal, name=""):
        self.id         = hashlib.md5(f"{goal}{time.time()}".encode()).hexdigest()[:10]
        self.name       = name or goal[:40]
        self.goal       = goal
        self.status     = "planning"
        self.created    = datetime.now().isoformat()
        self.steps      = []
        self.actions    = []
        self.result     = ""
        self.error      = ""
        self.context    = {}  # shared state across steps

    def log_action(self, step_num, action_type, description, reasoning, result, success, duration_ms=0):
        entry = {
            "mission_id":  self.id,
            "step_num":    step_num,
            "action_type": action_type,
            "description": description,
            "reasoning":   reasoning,
            "result":      str(result)[:500],
            "success":     int(success),
            "ts":          datetime.now().isoformat(),
            "duration_ms": duration_ms,
        }
        self.actions.append(entry)
        conn = get_db()
        conn.execute("""INSERT INTO actions
            (mission_id,step_num,action_type,description,reasoning,result,success,ts,duration_ms)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            tuple(entry.values()))
        conn.commit(); conn.close()

        color = "green" if success else "red"
        icon  = "✅" if success else "❌"
        rprint(f"  [{color}]{icon}[/{color}] [{action_type.upper()}] {description[:60]}")
        if reasoning:
            rprint(f"      [dim]↳ {reasoning[:80]}[/dim]")

    def save(self):
        conn = get_db()
        conn.execute("""INSERT OR REPLACE INTO missions
            (id,name,goal,status,created,completed,steps_total,steps_done,result,error)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (self.id, self.name, self.goal, self.status, self.created,
             datetime.now().isoformat() if self.status=="complete" else None,
             len(self.steps), len(self.actions),
             self.result[:1000], self.error[:500]))
        conn.commit(); conn.close()

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 MISSION PLANNER
# ══════════════════════════════════════════════════════════════════════════════

PLAN_PROMPT = """Mission: {goal}

Available action types:
  "web"      - HTTP requests, API calls, scraping
  "browser"  - Open browser, navigate, click, screenshot
  "system"   - Terminal commands, file operations
  "ai"       - AI analysis, reasoning, synthesis
  "wait"     - Pause, retry, check condition

Break this mission into 3-10 atomic steps.

Return JSON:
{{
  "mission_name": "short name",
  "steps": [
    {{
      "step": 1,
      "type": "web|browser|system|ai|wait",
      "action": "exact description of what to do",
      "params": {{}},
      "depends_on": [],
      "reversible": true,
      "risk": "low|medium|high"
    }}
  ],
  "estimated_duration": "30s",
  "notes": "any caveats"
}}"""

def plan_mission(goal):
    """Break a mission into atomic steps."""
    rprint(f"  [dim]Planning mission: {goal[:60]}[/dim]")

    if not AI_AVAILABLE:
        # Basic fallback plan
        return {
            "mission_name": goal[:30],
            "steps": [
                {"step":1,"type":"ai","action":f"Analyze: {goal}","params":{},"risk":"low","reversible":True}
            ]
        }

    plan = ai_json(
        PLAN_PROMPT.format(goal=goal),
        PLANNER_SYSTEM,
        1200
    )
    return plan or {"mission_name": goal[:30], "steps": []}

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 WEB HANDS
# ══════════════════════════════════════════════════════════════════════════════

class WebHands:
    """HTTP, API, and web scraping operations."""

    def __init__(self, mission):
        self.mission = mission
        self.session_cookies = {}
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; FORGE-Hands/1.0)",
            "Accept":     "text/html,application/json,*/*",
        }

    def get(self, url, params=None, json_response=False):
        """HTTP GET request."""
        t0 = time.time()
        try:
            if REQUESTS:
                r = requests.get(url, params=params, headers=self.headers,
                                cookies=self.session_cookies, timeout=15)
                content = r.json() if json_response else r.text
                status  = r.status_code
            else:
                full_url = url
                if params:
                    full_url += "?" + urllib.parse.urlencode(params)
                req = urllib.request.Request(full_url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw    = resp.read()
                    content= raw.decode("utf-8","replace")
                    status = resp.status

            ms = int((time.time()-t0)*1000)
            self.mission.log_action(0,"web",f"GET {url[:50]}",
                f"Fetching data from {url[:40]}", f"{status} — {len(str(content))} chars", True, ms)
            return {"status":status,"content":content,"url":url}

        except Exception as e:
            ms = int((time.time()-t0)*1000)
            self.mission.log_action(0,"web",f"GET {url[:50]}","",str(e),False,ms)
            return {"status":0,"content":"","error":str(e),"url":url}

    def post(self, url, data=None, json_data=None, headers=None):
        """HTTP POST request."""
        t0 = time.time()
        try:
            h = {**self.headers, **(headers or {})}
            if REQUESTS:
                if json_data:
                    r = requests.post(url, json=json_data, headers=h,
                                     cookies=self.session_cookies, timeout=15)
                else:
                    r = requests.post(url, data=data, headers=h,
                                     cookies=self.session_cookies, timeout=15)
                content = r.text; status = r.status_code
            else:
                body    = json.dumps(json_data).encode() if json_data else urllib.parse.urlencode(data or {}).encode()
                ct      = "application/json" if json_data else "application/x-www-form-urlencoded"
                req     = urllib.request.Request(url, data=body, headers={**h,"Content-Type":ct})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    content = resp.read().decode("utf-8","replace")
                    status  = resp.status

            ms = int((time.time()-t0)*1000)
            self.mission.log_action(0,"web",f"POST {url[:50]}",
                "Submitting data", f"{status}", True, ms)
            return {"status":status,"content":content,"url":url}

        except Exception as e:
            ms = int((time.time()-t0)*1000)
            self.mission.log_action(0,"web",f"POST {url[:50]}","",str(e),False,ms)
            return {"status":0,"content":"","error":str(e)}

    def scrape(self, url, selector=None, extract="text"):
        """Scrape content from webpage."""
        result = self.get(url)
        if not result.get("content"):
            return []

        content = result["content"]

        if BS4:
            soup  = BeautifulSoup(content, "html.parser")
            if selector:
                elements = soup.select(selector)
                if extract == "text":
                    return [el.get_text(strip=True) for el in elements]
                elif extract == "href":
                    return [el.get("href","") for el in elements]
                elif extract == "html":
                    return [str(el) for el in elements]
            else:
                # Smart extract: main content
                for tag in soup(["script","style","nav","footer"]):
                    tag.decompose()
                return [soup.get_text(separator="\n",strip=True)[:3000]]
        else:
            # Simple regex extraction
            if extract == "href":
                return re.findall(r'href=["\']([^"\']+)["\']', content)
            return [re.sub(r"<[^>]+>","",content)[:3000]]

    def api_call(self, url, method="GET", payload=None, api_key="", key_header="Authorization"):
        """Call a REST API."""
        headers = {}
        if api_key:
            headers[key_header] = f"Bearer {api_key}"

        t0 = time.time()
        try:
            if REQUESTS:
                fn  = getattr(requests, method.lower())
                r   = fn(url, json=payload, headers={**self.headers,**headers}, timeout=15)
                data= r.json() if "json" in r.headers.get("content-type","") else r.text
                ms  = int((time.time()-t0)*1000)
                self.mission.log_action(0,"web",f"API {method} {url[:40]}",
                    "API call", f"status:{r.status_code}", True, ms)
                return {"status":r.status_code,"data":data}
            else:
                return self.get(url) if method=="GET" else self.post(url,json_data=payload)
        except Exception as e:
            return {"error":str(e)}

    def download_file(self, url, filename=None):
        """Download file to downloads directory."""
        t0 = time.time()
        try:
            filename = filename or url.split("/")[-1] or "download"
            out_path = DOWNLOADS / filename

            if REQUESTS:
                r = requests.get(url, headers=self.headers, stream=True, timeout=30)
                with open(out_path,"wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
            else:
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req,timeout=30) as resp:
                    with open(out_path,"wb") as f:
                        f.write(resp.read())

            ms = int((time.time()-t0)*1000)
            self.mission.log_action(0,"web",f"Download {filename}",
                f"Downloaded from {url[:40]}", str(out_path), True, ms)
            return str(out_path)

        except Exception as e:
            self.mission.log_action(0,"web",f"Download {url[:40]}","",str(e),False)
            return None

# ══════════════════════════════════════════════════════════════════════════════
# 🖥️ COMPUTER HANDS
# ══════════════════════════════════════════════════════════════════════════════

class ComputerHands:
    """Browser automation and desktop control."""

    def __init__(self, mission):
        self.mission  = mission
        self._browser = None
        self._page    = None
        self._pw      = None

    # ── Playwright browser ─────────────────────────────────────────────────
    def open_browser(self, headless=True):
        """Launch Playwright browser."""
        if not PLAYWRIGHT:
            rprint("[yellow]Playwright not available. Install: pip install playwright && playwright install[/yellow]")
            return False
        try:
            self._pw      = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=headless)
            self._page    = self._browser.new_page()
            self._page.set_viewport_size({"width":1280,"height":800})
            self.mission.log_action(0,"browser","Open browser",
                "Launching headless Chromium for automation","Browser ready",True)
            return True
        except Exception as e:
            self.mission.log_action(0,"browser","Open browser","",str(e),False)
            return False

    def navigate(self, url, wait_for="domcontentloaded"):
        """Navigate to URL."""
        if not self._page:
            if not self.open_browser(): return False
        try:
            self._page.goto(url, wait_until=wait_for, timeout=15000)
            self.mission.log_action(0,"browser",f"Navigate to {url[:50]}",
                f"Going to {url[:40]}", f"Page: {self._page.title()}", True)
            return True
        except Exception as e:
            self.mission.log_action(0,"browser",f"Navigate {url[:40]}","",str(e),False)
            return False

    def screenshot(self, filename=None, full_page=False):
        """Take screenshot — with Playwright or pyautogui fallback."""
        t0 = time.time()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = filename or f"screenshot_{ts}.png"
        out_path = SCREENSHOTS / filename

        try:
            if self._page:
                self._page.screenshot(path=str(out_path), full_page=full_page)
            elif PYAUTOGUI:
                img = pyautogui.screenshot()
                img.save(str(out_path))
            else:
                self.mission.log_action(0,"browser","Screenshot",
                    "","No screenshot tool available",False)
                return None

            ms = int((time.time()-t0)*1000)
            self.mission.log_action(0,"browser",f"Screenshot → {filename}",
                "Capturing current state", str(out_path), True, ms)

            # Save to db
            url = self._page.url if self._page else ""
            conn = get_db()
            conn.execute(
                "INSERT INTO screenshots (mission_id,ts,filepath,url) VALUES (?,?,?,?)",
                (self.mission.id, datetime.now().isoformat(), str(out_path), url)
            )
            conn.commit(); conn.close()
            return str(out_path)

        except Exception as e:
            self.mission.log_action(0,"browser","Screenshot","",str(e),False)
            return None

    def click(self, selector_or_text):
        """Click element by CSS selector or visible text."""
        if not self._page: return False
        try:
            if selector_or_text.startswith(("#",".","/","[")):
                self._page.click(selector_or_text, timeout=5000)
            else:
                self._page.get_by_text(selector_or_text).first.click()
            self.mission.log_action(0,"browser",f"Click '{selector_or_text[:30]}'",
                f"Clicking on target element", "Clicked", True)
            return True
        except Exception as e:
            self.mission.log_action(0,"browser",f"Click '{selector_or_text[:30]}'","",str(e),False)
            return False

    def type_text(self, selector, text, clear_first=True):
        """Type text into input field."""
        if not self._page: return False
        try:
            if clear_first:
                self._page.fill(selector, text)
            else:
                self._page.type(selector, text)
            self.mission.log_action(0,"browser",f"Type into {selector[:30]}",
                f"Entering text: {text[:30]}", "Typed", True)
            return True
        except Exception as e:
            self.mission.log_action(0,"browser",f"Type {selector[:30]}","",str(e),False)
            return False

    def get_text(self, selector=None):
        """Extract text content from page or element."""
        if not self._page: return ""
        try:
            if selector:
                return self._page.text_content(selector) or ""
            return self._page.inner_text("body") or ""
        except:
            return ""

    def get_page_content(self):
        """Get full page HTML."""
        if not self._page: return ""
        try: return self._page.content()
        except: return ""

    def wait_for(self, selector_or_url, timeout=10000):
        """Wait for element or navigation."""
        if not self._page: return False
        try:
            if selector_or_url.startswith("http"):
                self._page.wait_for_url(selector_or_url, timeout=timeout)
            else:
                self._page.wait_for_selector(selector_or_url, timeout=timeout)
            return True
        except: return False

    def extract_links(self):
        """Extract all links from current page."""
        if not self._page: return []
        try:
            links = self._page.eval_on_selector_all("a[href]",
                "els => els.map(el => ({text:el.textContent.trim(),href:el.href}))")
            return links
        except: return []

    def analyze_screenshot(self, filepath):
        """Run Sherlock vision analysis on screenshot."""
        if not AI_AVAILABLE or not filepath: return ""
        try:
            with open(filepath,"rb") as f:
                b64 = base64.standard_b64encode(f.read()).decode()
            return ai_vision(
                "Analyze this screenshot. What is shown? Any important information, "
                "errors, forms, data, or security-relevant content? Be specific.",
                b64
            )
        except: return ""

    def close(self):
        """Close browser."""
        try:
            if self._browser: self._browser.close()
            if self._pw:      self._pw.stop()
        except: pass

    # ── PyAutoGUI desktop control ──────────────────────────────────────────
    def move_mouse(self, x, y, duration=0.3):
        if not PYAUTOGUI: return False
        try: pyautogui.moveTo(x, y, duration=duration); return True
        except: return False

    def click_at(self, x, y):
        if not PYAUTOGUI: return False
        try: pyautogui.click(x, y); return True
        except: return False

    def type_keys(self, text):
        if not PYAUTOGUI: return False
        try: pyautogui.typewrite(text, interval=0.05); return True
        except: return False

    def hotkey(self, *keys):
        if not PYAUTOGUI: return False
        try: pyautogui.hotkey(*keys); return True
        except: return False

# ══════════════════════════════════════════════════════════════════════════════
# 🔧 SYSTEM HANDS
# ══════════════════════════════════════════════════════════════════════════════

class SystemHands:
    """Terminal, file system, and process control."""

    SAFE_COMMANDS = {
        "ls","dir","pwd","echo","cat","head","tail","grep","find","wc",
        "ps","top","df","du","which","whoami","date","uname","python3",
        "pip","git","curl","wget","ping","nslookup","dig","traceroute",
        "netstat","ss","lsof","env","printenv",
    }

    DANGEROUS = ["rm -rf","dd if","mkfs",":(){ :|:& };:","chmod 777 /",
                 "sudo rm","> /dev/","fork bomb"]

    def __init__(self, mission):
        self.mission = mission
        self.cwd     = Path.cwd()
        self.env     = os.environ.copy()

    def _is_safe(self, cmd):
        """Check if command is safe to run."""
        cmd_lower = cmd.lower().strip()
        for dangerous in self.DANGEROUS:
            if dangerous in cmd_lower:
                return False, f"Dangerous pattern: {dangerous}"
        return True, "ok"

    def run(self, command, timeout=30, cwd=None, capture=True):
        """Run a shell command."""
        safe, reason = self._is_safe(command)
        if not safe:
            self.mission.log_action(0,"system",f"BLOCKED: {command[:40]}",
                "Safety check failed", reason, False)
            return {"stdout":"","stderr":f"BLOCKED: {reason}","returncode":-1}

        t0 = time.time()
        try:
            result = subprocess.run(
                command, shell=True,
                capture_output=capture,
                text=True, timeout=timeout,
                cwd=str(cwd or self.cwd),
                env=self.env,
            )
            ms = int((time.time()-t0)*1000)
            success = result.returncode == 0
            output  = (result.stdout or "")[:500]

            self.mission.log_action(0,"system",f"RUN: {command[:50]}",
                f"Executing: {command[:40]}",
                f"exit:{result.returncode} {output[:80]}", success, ms)

            return {
                "stdout":     result.stdout or "",
                "stderr":     result.stderr or "",
                "returncode": result.returncode,
                "command":    command,
            }
        except subprocess.TimeoutExpired:
            self.mission.log_action(0,"system",f"TIMEOUT: {command[:40]}","","Timed out",False)
            return {"stdout":"","stderr":"Timeout","returncode":-1}
        except Exception as e:
            self.mission.log_action(0,"system",f"ERROR: {command[:40]}","",str(e),False)
            return {"stdout":"","stderr":str(e),"returncode":-1}

    def read_file(self, path):
        """Read file content."""
        try:
            content = Path(path).read_text(errors="replace")
            self.mission.log_action(0,"system",f"Read {path}",
                f"Reading file contents", f"{len(content)} chars", True)
            return content
        except Exception as e:
            self.mission.log_action(0,"system",f"Read {path}","",str(e),False)
            return None

    def write_file(self, path, content):
        """Write content to file."""
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(content)
            self.mission.log_action(0,"system",f"Write {path}",
                f"Writing {len(content)} chars", str(path), True)
            return True
        except Exception as e:
            self.mission.log_action(0,"system",f"Write {path}","",str(e),False)
            return False

    def list_files(self, path=".", pattern="*", recursive=False):
        """List files matching pattern."""
        try:
            p = Path(path)
            if recursive:
                files = list(p.rglob(pattern))
            else:
                files = list(p.glob(pattern))
            self.mission.log_action(0,"system",f"List {path}/{pattern}",
                "Listing files", f"{len(files)} files found", True)
            return [str(f) for f in files[:100]]
        except Exception as e:
            return []

    def find_files(self, name_pattern="", content_pattern="", path="."):
        """Find files by name or content."""
        results = []
        try:
            for fp in Path(path).rglob("*"):
                if not fp.is_file(): continue
                if name_pattern and not re.search(name_pattern, fp.name, re.IGNORECASE):
                    continue
                if content_pattern:
                    try:
                        text = fp.read_text(errors="replace")
                        if re.search(content_pattern, text, re.IGNORECASE):
                            results.append(str(fp))
                    except: pass
                else:
                    results.append(str(fp))
            self.mission.log_action(0,"system",f"Find files: {name_pattern or content_pattern}",
                "Searching filesystem", f"{len(results)} found", True)
        except Exception as e:
            self.mission.log_action(0,"system","Find files","",str(e),False)
        return results[:50]

    def get_process_list(self):
        """Get running processes."""
        if PSUTIL:
            procs = []
            for p in psutil.process_iter(["pid","name","status","cpu_percent","memory_percent"]):
                try: procs.append(p.info)
                except: pass
            return procs[:50]
        else:
            result = self.run("ps aux" if os.name!="nt" else "tasklist")
            return result.get("stdout","")

    def get_system_info(self):
        """Get system information."""
        info = {
            "platform": sys.platform,
            "python":   sys.version.split()[0],
            "cwd":      str(self.cwd),
        }
        if PSUTIL:
            info.update({
                "cpu_percent":    psutil.cpu_percent(1),
                "ram_gb":         round(psutil.virtual_memory().total / 1e9, 1),
                "ram_used_pct":   psutil.virtual_memory().percent,
                "disk_free_gb":   round(psutil.disk_usage("/").free / 1e9, 1),
            })
        return info

# ══════════════════════════════════════════════════════════════════════════════
# 🤖 MISSION EXECUTOR
# ══════════════════════════════════════════════════════════════════════════════

STEP_REASONER = """You are FORGE HANDS executing mission step {step}/{total}.

Mission goal: {goal}
Current step: {action}
Context so far: {context}

Before executing, reason like Sherlock:

INTENT:   [what this step accomplishes]
BECAUSE:  [why this is the right action now]
RISK:     [what could go wrong]
FALLBACK: [what to do if it fails]

Then provide execution parameters as JSON:
{{"reasoning": "...", "params": {{...}}, "expected_output": "..."}}"""

SYNTHESIZER_PROMPT = """You are FORGE HANDS. Mission complete.

Goal: {goal}
Steps executed: {steps}
All actions: {actions}
Screenshots taken: {screenshots}

Write the mission completion report:

## MISSION ACCOMPLISHED / FAILED
[clear status]

## WHAT WAS DONE
[chronological summary]

## KEY FINDINGS
[most important results]

## DATA COLLECTED
[files, URLs, content gathered]

## NEXT STEPS
[what should happen next]

## SHERLOCK SYNTHESIS
[what patterns or insights emerged from the digital footprint]"""

class MissionExecutor:
    def __init__(self, mission):
        self.mission  = mission
        self.web      = WebHands(mission)
        self.computer = ComputerHands(mission)
        self.system   = SystemHands(mission)

    def execute(self, plan):
        """Execute a complete mission plan."""
        steps     = plan.get("steps", [])
        self.mission.steps = steps
        self.mission.status= "running"
        self.mission.save()

        rprint(f"\n[bold yellow]🤝 EXECUTING MISSION[/bold yellow]")
        rprint(f"  Goal: {self.mission.goal[:60]}")
        rprint(f"  Steps: {len(steps)}\n")

        for step_data in steps:
            step_num  = step_data.get("step", 0)
            step_type = step_data.get("type","ai")
            action    = step_data.get("action","")
            params    = step_data.get("params",{})
            risk      = step_data.get("risk","low")

            rprint(f"[yellow]  Step {step_num}/{len(steps)}: {action[:55]}[/yellow]")
            rprint(f"  [dim]Type: {step_type} | Risk: {risk}[/dim]")

            # Reason before acting
            reasoning = self._reason_step(step_num, len(steps), action)

            # Execute by type
            result = self._execute_step(step_type, action, params, step_num)
            self.mission.context[f"step_{step_num}"] = result

        # Synthesize
        self.mission.result = self._synthesize()
        self.mission.status = "complete"
        self.mission.save()

        rprint(f"\n[bold green]✅ MISSION COMPLETE[/bold green]")
        rprint(Panel(self.mission.result[:600], border_style="green",
                     title="🤝 Mission Report"))

        # Cleanup
        self.computer.close()
        return self.mission

    def _reason_step(self, step_num, total, action):
        """Sherlock reasons before each step."""
        if not AI_AVAILABLE: return ""
        ctx = json.dumps({
            k:str(v)[:100] for k,v in list(self.mission.context.items())[-3:]
        })
        result = ai_json(
            STEP_REASONER.format(
                step=step_num, total=total,
                goal=self.mission.goal[:100],
                action=action,
                context=ctx,
            ),
            max_tokens=400
        )
        if result:
            rprint(f"  [dim italic]↳ {result.get('reasoning','')[:80]}[/dim italic]")
        return result or {}

    def _execute_step(self, step_type, action, params, step_num):
        """Execute a single step by type."""
        t0 = time.time()
        try:
            if step_type == "web":
                return self._exec_web(action, params)
            elif step_type == "browser":
                return self._exec_browser(action, params)
            elif step_type == "system":
                return self._exec_system(action, params)
            elif step_type == "ai":
                return self._exec_ai(action, params)
            elif step_type == "wait":
                secs = params.get("seconds", 2)
                time.sleep(secs)
                return {"waited": secs}
            else:
                return self._exec_ai(action, params)
        except Exception as e:
            self.mission.log_action(step_num, step_type, action, "", str(e), False)
            return {"error": str(e)}

    def _exec_web(self, action, params):
        """Execute web action."""
        action_l = action.lower()
        url      = params.get("url","")

        # Auto-detect URL in action
        if not url:
            m = re.search(r'https?://\S+', action)
            if m: url = m.group()

        if "scrape" in action_l or "extract" in action_l:
            selector = params.get("selector","")
            extract  = params.get("extract","text")
            data     = self.web.scrape(url, selector, extract)
            return {"scraped": data[:1000] if isinstance(data,list) else data}

        elif "download" in action_l:
            fp = self.web.download_file(url, params.get("filename"))
            return {"downloaded": fp}

        elif "post" in action_l:
            data   = params.get("data",{})
            result = self.web.post(url, json_data=data)
            return result

        elif "api" in action_l:
            result = self.web.api_call(
                url, params.get("method","GET"),
                params.get("payload"), params.get("api_key","")
            )
            return result

        elif url:
            result = self.web.get(url)
            # AI summary of content
            if result.get("content") and AI_AVAILABLE:
                summary = ai_call(
                    f"Summarize the key information from this webpage content for the mission '{self.mission.goal[:50]}':\n{result['content'][:2000]}",
                    max_tokens=400
                )
                result["summary"] = summary
            return result

        else:
            # AI decides what web action to take
            if AI_AVAILABLE:
                decision = ai_json(
                    f"Web action needed: {action}\nMission: {self.mission.goal}\n"
                    'Decide: {"url":"","method":"GET","params":{}}',
                    max_tokens=200
                )
                if decision and decision.get("url"):
                    return self.web.get(decision["url"])
            return {"result": "Web action — no URL determined"}

    def _exec_browser(self, action, params):
        """Execute browser action."""
        action_l = action.lower()
        url      = params.get("url","")

        if not url:
            m = re.search(r'https?://\S+', action)
            if m: url = m.group()

        if not url and AI_AVAILABLE:
            decision = ai_json(
                f"Browser action: {action}\nMission: {self.mission.goal}\n"
                'Extract URL to navigate to: {"url":""}',
                max_tokens=100
            )
            if decision: url = decision.get("url","")

        if url:
            self.computer.navigate(url)
            time.sleep(1.5)  # let page render
            fp = self.computer.screenshot(f"step_{int(time.time())}.png")
            content = self.computer.get_text()

            result = {"url":url, "screenshot":fp, "content":content[:500]}

            # Analyze screenshot if taken
            if fp:
                analysis = self.computer.analyze_screenshot(fp)
                result["analysis"] = analysis

            return result

        elif "screenshot" in action_l:
            fp = self.computer.screenshot()
            return {"screenshot": fp}

        elif "click" in action_l:
            target = params.get("selector") or params.get("text","")
            ok = self.computer.click(target)
            return {"clicked": ok}

        elif "type" in action_l:
            sel  = params.get("selector","input")
            text = params.get("text","")
            ok   = self.computer.type_text(sel, text)
            return {"typed": ok}

        return {"result": "Browser action executed"}

    def _exec_system(self, action, params):
        """Execute system action."""
        action_l = action.lower()

        if "find" in action_l and "file" in action_l:
            results = self.system.find_files(
                params.get("name",""),
                params.get("content",""),
                params.get("path",".")
            )
            return {"files": results}

        elif "read" in action_l:
            path = params.get("path","")
            if not path:
                m = re.search(r'[\w/\\.]+\.\w+', action)
                if m: path = m.group()
            content = self.system.read_file(path) if path else ""
            return {"content": content[:1000] if content else ""}

        elif "write" in action_l or "save" in action_l or "create" in action_l:
            path    = params.get("path","output.txt")
            content = params.get("content","")
            ok = self.system.write_file(path, content)
            return {"written": ok, "path": path}

        elif "run" in action_l or "execute" in action_l or "command" in action_l:
            cmd = params.get("command","")
            if not cmd and AI_AVAILABLE:
                decision = ai_json(
                    f"System action: {action}\nMission: {self.mission.goal}\n"
                    f"Platform: {sys.platform}\n"
                    'Provide safe shell command: {"command":"ls -la"}',
                    max_tokens=100
                )
                if decision: cmd = decision.get("command","")
            result = self.system.run(cmd) if cmd else {"stdout":"No command"}
            return result

        elif "list" in action_l:
            path    = params.get("path",".")
            pattern = params.get("pattern","*")
            files   = self.system.list_files(path, pattern)
            return {"files": files}

        elif "system" in action_l or "info" in action_l:
            return self.system.get_system_info()

        else:
            # Let AI decide the command
            if AI_AVAILABLE:
                decision = ai_json(
                    f"System action needed: {action}\nPlatform: {sys.platform}\n"
                    f"Mission: {self.mission.goal}\n"
                    f'Provide safe command: {{"command":"echo ok"}}',
                    max_tokens=100
                )
                if decision:
                    cmd = decision.get("command","")
                    if cmd:
                        return self.system.run(cmd)
            return {"result": "System action — no command determined"}

    def _exec_ai(self, action, params):
        """Execute AI reasoning/analysis step."""
        if not AI_AVAILABLE: return {"result":"AI unavailable"}

        ctx = json.dumps({
            k:str(v)[:200]
            for k,v in list(self.mission.context.items())[-5:]
        })

        result = ai_call(
            f"Mission: {self.mission.goal}\n\n"
            f"Task: {action}\n\n"
            f"Context from previous steps:\n{ctx}\n\n"
            f"Params: {json.dumps(params)}\n\n"
            f"Execute this task and provide results.",
            max_tokens=1000
        )
        self.mission.log_action(0,"ai",f"AI: {action[:50]}",
            "AI reasoning step", result[:100], True)
        return {"result": result}

    def _synthesize(self):
        """Synthesize mission results into report."""
        if not AI_AVAILABLE:
            return f"Mission complete. {len(self.mission.actions)} actions taken."

        actions_summary = "\n".join(
            f"Step {a['step_num']}: [{a['action_type']}] {a['description'][:50]} → {'✅' if a['success'] else '❌'}"
            for a in self.mission.actions[-15:]
        )

        screenshots = [a for a in self.mission.actions if "screenshot" in a.get("description","").lower()]

        return ai_call(
            SYNTHESIZER_PROMPT.format(
                goal        = self.mission.goal,
                steps       = len(self.mission.steps),
                actions     = actions_summary,
                screenshots = len(screenshots),
            ),
            max_tokens=1000
        )

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API SERVER
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7343):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    active_missions = {}
    jobs = {}

    class HandsAPI(BaseHTTPRequestHandler):
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
        def _body(self):
            n=int(self.headers.get("Content-Length",0))
            return json.loads(self.rfile.read(n)) if n else {}

        def do_GET(self):
            path=urlparse(self.path).path
            if path=="/api/status":
                self._json({"status":"online","playwright":PLAYWRIGHT,
                           "pyautogui":PYAUTOGUI,"requests":REQUESTS,"ai":AI_AVAILABLE})
            elif path=="/api/missions":
                conn=get_db()
                rows=conn.execute("SELECT * FROM missions ORDER BY rowid DESC LIMIT 20").fetchall()
                conn.close()
                self._json({"missions":[dict(r) for r in rows]})
            elif path=="/api/screenshots":
                files=sorted(SCREENSHOTS.glob("*.png"),key=lambda x:x.stat().st_mtime,reverse=True)
                self._json({"screenshots":[str(f) for f in files[:20]]})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path=urlparse(self.path).path
            body=self._body()

            if path=="/api/mission/run":
                goal=body.get("goal","")
                if not goal: self._json({"error":"goal required"},400); return

                job_id=hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
                jobs[job_id]={"status":"planning","goal":goal}

                def run_job():
                    try:
                        m   =Mission(goal)
                        plan=plan_mission(goal)
                        jobs[job_id]["status"]="running"
                        exe =MissionExecutor(m)
                        exe.execute(plan)
                        active_missions[m.id]=m
                        jobs[job_id].update({"status":"complete","mission_id":m.id,
                                            "result":m.result[:300]})
                    except Exception as e:
                        jobs[job_id].update({"status":"error","error":str(e)})

                threading.Thread(target=run_job,daemon=True).start()
                self._json({"job_id":job_id,"status":"planning"})

            elif path=="/api/mission/status":
                job_id=body.get("job_id","")
                self._json(jobs.get(job_id,{"error":"not found"}))

            elif path=="/api/web/get":
                m=Mission("quick web get")
                w=WebHands(m)
                r=w.get(body.get("url",""))
                self._json(r)

            elif path=="/api/system/run":
                m=Mission("quick system run")
                s=SystemHands(m)
                r=s.run(body.get("command","echo ok"))
                self._json(r)

            else:
                self._json({"error":"unknown"},404)

    server=HTTPServer(("0.0.0.0",port),HandsAPI)
    rprint(f"  [yellow]🤝 FORGE HANDS API: http://localhost:{port}[/yellow]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# 🎮 INTERACTIVE CONSOLE
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ██╗  ██╗ █████╗ ███╗   ██╗██████╗ ███████╗
  ██║  ██║██╔══██╗████╗  ██║██╔══██╗██╔════╝
  ███████║███████║██╔██╗ ██║██║  ██║███████╗
  ██╔══██║██╔══██║██║╚██╗██║██║  ██║╚════██║
  ██║  ██║██║  ██║██║ ╚████║██████╔╝███████║
  ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═════╝ ╚══════╝
[/yellow]
[bold]  🤝 FORGE HANDS — Autonomous Digital Action Engine[/bold]
[dim]  Give it a mission. It thinks, plans, acts, reports.[/dim]
"""

def run_mission_interactive(goal):
    """Run a mission from command line."""
    rprint(f"\n[yellow]Planning: {goal}[/yellow]")
    plan = plan_mission(goal)

    if not plan or not plan.get("steps"):
        rprint("[red]Could not plan mission.[/red]")
        return

    rprint(f"\n[bold]Mission Plan: {plan.get('mission_name',goal[:30])}[/bold]")
    for s in plan.get("steps",[]):
        rprint(f"  {s['step']}. [{s['type']}] {s['action'][:60]}")

    if RICH:
        confirm = console.input("\n[yellow]Execute? (y/n): [/yellow]").strip().lower()
    else:
        confirm = input("Execute? (y/n): ").strip().lower()

    if confirm != "y":
        rprint("[dim]Mission cancelled.[/dim]")
        return

    mission = Mission(goal, plan.get("mission_name",""))
    exe     = MissionExecutor(mission)
    exe.execute(plan)

def interactive():
    rprint(BANNER)
    rprint(f"  [dim]Playwright: {'✅' if PLAYWRIGHT else '❌ pip install playwright'}[/dim]")
    rprint(f"  [dim]Requests:   {'✅' if REQUESTS   else '❌ pip install requests'}[/dim]")
    rprint(f"  [dim]PyAutoGUI:  {'✅' if PYAUTOGUI  else '❌ pip install pyautogui'}[/dim]")
    rprint(f"  [dim]AI:         {'✅' if AI_AVAILABLE else '❌ pip install anthropic'}[/dim]\n")

    rprint("[dim]Just describe your mission in plain English. FORGE HANDS will plan and execute it.[/dim]")
    rprint("[dim]Commands: mission | web | system | browse | screenshots | missions | server | help | quit[/dim]\n")

    while True:
        try:
            inp = console.input if RICH else input
            raw = inp("[yellow bold]🤝 hands >[/yellow bold] ").strip()
            if not raw: continue

            parts = raw.split(None,1)
            cmd   = parts[0].lower()
            args  = parts[1] if len(parts)>1 else ""

            if cmd in ("quit","exit","q"):
                rprint("[dim]Hands resting.[/dim]"); break

            elif cmd == "help":
                rprint("""
[bold yellow]FORGE HANDS Commands[/bold yellow]

  Just type any mission in plain English:
    [yellow]"find all Python files modified this week"[/yellow]
    [yellow]"screenshot github.com and analyze it"[/yellow]
    [yellow]"get the latest news from hackernews"[/yellow]
    [yellow]"check what processes are using the most memory"[/yellow]

  Or use explicit commands:
  [yellow]web[/yellow] <url>         Quick web fetch
  [yellow]system[/yellow] <cmd>      Run system command
  [yellow]browse[/yellow] <url>      Open browser + screenshot
  [yellow]screenshots[/yellow]       List screenshots taken
  [yellow]missions[/yellow]          Mission history
  [yellow]server[/yellow]            Start API server
""")

            elif cmd == "web":
                url = args.strip()
                if url:
                    m = Mission("quick fetch")
                    w = WebHands(m)
                    r = w.get(url)
                    if r.get("content"):
                        rprint(Panel(r["content"][:600], title=url[:50], border_style="dim"))
                    else:
                        rprint(f"[red]{r.get('error','Failed')}[/red]")

            elif cmd == "system":
                cmd_str = args.strip()
                if cmd_str:
                    m = Mission("quick system")
                    s = SystemHands(m)
                    r = s.run(cmd_str)
                    if r.get("stdout"):
                        rprint(Panel(r["stdout"][:600], border_style="dim"))
                    if r.get("stderr"):
                        rprint(f"[red]{r['stderr'][:200]}[/red]")

            elif cmd == "browse":
                url = args.strip()
                if url:
                    m  = Mission("quick browse")
                    c  = ComputerHands(m)
                    ok = c.navigate(url)
                    if ok:
                        time.sleep(1.5)
                        fp = c.screenshot()
                        rprint(f"[green]Screenshot: {fp}[/green]")
                        if fp: rprint(f"[dim]{c.analyze_screenshot(fp)[:200]}[/dim]")
                    c.close()

            elif cmd == "screenshots":
                files = sorted(SCREENSHOTS.glob("*.png"), reverse=True)[:10]
                for fp in files:
                    rprint(f"  [dim]{fp.name}[/dim]  {fp.stat().st_size//1024}kb")

            elif cmd == "missions":
                conn  = get_db()
                rows  = conn.execute(
                    "SELECT * FROM missions ORDER BY rowid DESC LIMIT 10"
                ).fetchall()
                conn.close()
                if rows:
                    for r in rows:
                        status_color = "green" if r["status"]=="complete" else "yellow"
                        rprint(f"  [{status_color}]{r['status']:<10}[/{status_color}]  {r['name'][:40]}")
                else:
                    rprint("[dim]No missions yet.[/dim]")

            elif cmd == "server":
                rprint("[yellow]Starting HANDS server on port 7343...[/yellow]")
                threading.Thread(target=start_server, daemon=True).start()
                time.sleep(0.5)
                rprint("[green]Server running on :7343[/green]")

            else:
                # Treat as mission
                goal = raw
                run_mission_interactive(goal)

        except (KeyboardInterrupt, EOFError):
            rprint("\n[dim]Hands resting.[/dim]"); break

def main():
    if "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7343
        start_server(port)
        return

    if "--mission" in sys.argv:
        idx  = sys.argv.index("--mission")
        goal = sys.argv[idx+1] if idx+1 < len(sys.argv) else ""
        if goal:
            rprint(BANNER)
            run_mission_interactive(goal)
        return

    if "--web" in sys.argv:
        idx = sys.argv.index("--web")
        url = sys.argv[idx+1] if idx+1 < len(sys.argv) else ""
        if url:
            m = Mission("web fetch")
            w = WebHands(m)
            r = w.get(url)
            print(r.get("content","")[:1000])
        return

    if "--system" in sys.argv:
        idx = sys.argv.index("--system")
        cmd = sys.argv[idx+1] if idx+1 < len(sys.argv) else ""
        if cmd:
            m = Mission("system command")
            s = SystemHands(m)
            r = s.run(cmd)
            print(r.get("stdout",""))
        return

    if "--browser" in sys.argv:
        idx = sys.argv.index("--browser")
        url = sys.argv[idx+1] if idx+1 < len(sys.argv) else ""
        if url:
            m  = Mission("browse")
            c  = ComputerHands(m)
            c.navigate(url)
            time.sleep(2)
            fp = c.screenshot()
            print(f"Screenshot: {fp}")
            c.close()
        return

    interactive()

if __name__ == "__main__":
    main()
