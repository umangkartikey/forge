#!/usr/bin/env python3
"""
███████╗ ██████╗ ██████╗  ██████╗ ███████╗    ███╗   ███╗███████╗████████╗ █████╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝    ████╗ ████║██╔════╝╚══██╔══╝██╔══██╗
█████╗  ██║   ██║██████╔╝██║  ███╗█████╗      ██╔████╔██║█████╗     ██║   ███████║
██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝      ██║╚██╔╝██║██╔══╝     ██║   ██╔══██║
██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗    ██║ ╚═╝ ██║███████╗   ██║   ██║  ██║
╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝    ╚═╝     ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝

FORGE META — Metasploit-style Framework + Adaptive Intelligence Engine

Two systems in one:
  🎯 META FRAMEWORK  — use/set/run module system like Metasploit
  🧠 ADAPTIVE FORGE  — detects situations, builds tools it doesn't have YET

Requirements: pip install anthropic rich
Usage: python forge_meta.py
"""

import sys, os, json, re, socket, threading, hashlib, time, shutil
import subprocess, zipfile, io, secrets, string
from pathlib import Path
from datetime import datetime
from urllib.request import urlopen, Request as UReq
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# ── Try rich ──────────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.syntax import Syntax
    from rich.prompt import Prompt
    from rich.text import Text
    from rich import box as rbox
    RICH = True
    console = Console()
    def rprint(x, **kw): console.print(x, **kw)
    def rpanel(content, title="", border="cyan"):
        console.print(Panel(content, title=title, border_style=border))
except ImportError:
    RICH = False
    def rprint(x, **kw): print(re.sub(r"\[/?[a-zA-Z_ ]*\]","",str(x)))
    def rpanel(content, title="", border="cyan"): print(f"\n── {title} ──\n{content}\n")

# ── Try anthropic ─────────────────────────────────────────────────────────────
try:
    import anthropic
    AI_CLIENT = anthropic.Anthropic()
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    AI_CLIENT = None

MODEL = "claude-sonnet-4-6"

# ── Dirs ──────────────────────────────────────────────────────────────────────
META_DIR   = Path("forge_meta")
MODULES_DIR= META_DIR / "modules"
SESSIONS_F = META_DIR / "sessions.json"
WORKSPACE_F= META_DIR / "workspace.json"
ADAPT_DIR  = META_DIR / "adaptive_tools"
ADAPT_LOG  = META_DIR / "adapt_log.json"

for d in [META_DIR, MODULES_DIR, ADAPT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Colors
R="\033[91m"; G="\033[92m"; Y="\033[93m"; B="\033[94m"
M="\033[95m"; C="\033[96m"; W="\033[97m"; DIM="\033[2m"; X="\033[0m"; BOLD="\033[1m"

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 ADAPTIVE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

ADAPT_PROMPT = """You are FORGE's Adaptive Intelligence Engine.

The user gave a command or situation that FORGE cannot handle with existing tools.
Your job is to:
1. Understand what capability is needed
2. Write a Python module that provides it
3. The module must fit into the FORGE META framework

FORGE META module format:
```python
# MODULE_NAME: short_name
# CATEGORY: scanner|analyzer|cracker|network|crypto|recon|exploit|util
# DESCRIPTION: what it does
# OPTIONS: OPTION_NAME=default:description, ...

def run(options, session, workspace):
    \"\"\"Main entry point. options=dict, session=dict, workspace=dict\"\"\"
    target = options.get("TARGET", "localhost")
    # ... do the work ...
    return {"status": "success", "data": {...}, "output": "human readable result"}
```

Respond with ONLY the Python module code in a ```python ... ``` block.
Make it work with stdlib only (no pip installs).
"""

SITUATION_ANALYZER = """You are FORGE's Situation Analyzer.

Analyze this user input and determine:
1. What they're trying to accomplish
2. What tool/capability is needed
3. What category it falls into
4. Whether it could be dangerous

Reply ONLY with JSON:
{
  "intent": "what user wants to do",
  "capability_needed": "short description of tool needed",
  "module_name": "snake_case_name",
  "category": "scanner|analyzer|cracker|network|crypto|recon|util",
  "options_needed": ["TARGET", "PORT", "WORDLIST"],
  "safe": true/false,
  "reason_if_unsafe": "explanation if not safe"
}
"""

def ai_call(prompt, system, max_tokens=3000):
    if not AI_AVAILABLE:
        return None
    try:
        r = AI_CLIENT.messages.create(
            model=MODEL, max_tokens=max_tokens, system=system,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text
    except Exception as e:
        rprint(f"[red]AI error: {e}[/red]")
        return None

def adapt_analyze_situation(user_input):
    """Analyze what the user wants and whether we can build it."""
    result = ai_call(
        f"User input: {user_input}\n\nAnalyze this request.",
        SITUATION_ANALYZER, max_tokens=500
    )
    if not result:
        return None
    try:
        clean = re.sub(r"```[a-z]*\s*","",result).strip()
        return json.loads(clean)
    except:
        m = re.search(r"\{.*\}", result, re.DOTALL)
        if m:
            try: return json.loads(m.group())
            except: pass
    return None

def adapt_build_module(situation, user_input):
    """Build a new module for a situation FORGE hasn't seen before."""
    prompt = f"""User wants to: {user_input}

Situation analysis:
- Intent: {situation.get('intent','')}
- Capability needed: {situation.get('capability_needed','')}
- Module name: {situation.get('module_name','')}
- Category: {situation.get('category','')}
- Options needed: {situation.get('options_needed',[])}

Build this module now."""

    result = ai_call(prompt, ADAPT_PROMPT, max_tokens=3000)
    if not result:
        return None

    m = re.search(r"```python\s*(.*?)```", result, re.DOTALL)
    if not m:
        return None

    return m.group(1).strip()

def adapt_save_module(name, code, situation):
    """Save an adaptively built module."""
    fp = MODULES_DIR / f"{name}.py"
    header = f"# ADAPTIVE MODULE — Built by FORGE for: {situation.get('intent','')}\n"
    header += f"# Built: {datetime.now().isoformat()}\n\n"
    fp.write_text(header + code)

    # Log it
    log = json.loads(ADAPT_LOG.read_text()) if ADAPT_LOG.exists() else []
    log.append({
        "module": name,
        "intent": situation.get("intent",""),
        "built": datetime.now().isoformat(),
        "category": situation.get("category","util"),
    })
    ADAPT_LOG.write_text(json.dumps(log, indent=2))

    return fp

def adapt_load_and_run(module_path, options, session, workspace):
    """Dynamically load and execute an adaptive module."""
    import importlib.util, types

    spec   = importlib.util.spec_from_file_location("adaptive_mod", module_path)
    module = types.ModuleType("adaptive_mod")

    try:
        with open(module_path) as f:
            source = f.read()
        exec(compile(source, str(module_path), "exec"), module.__dict__)
        if hasattr(module, "run"):
            return module.run(options, session, workspace)
        else:
            return {"status":"error","output":"Module has no run() function"}
    except Exception as e:
        return {"status":"error","output":f"Module error: {e}"}

# ══════════════════════════════════════════════════════════════════════════════
# 📦 BUILT-IN MODULES
# ══════════════════════════════════════════════════════════════════════════════

class Module:
    name        = "base"
    category    = "util"
    description = "Base module"
    options     = {}  # name: (default, description)
    _values     = {}

    def __init__(self):
        self._values = {k: v[0] for k, v in self.options.items()}

    def set(self, key, value):
        k = key.upper()
        if k in self.options:
            self._values[k] = value
            return True
        return False

    def get(self, key):
        return self._values.get(key.upper(), "")

    def show_options(self):
        if RICH:
            t = Table(title=f"Module: {self.name}", border_style="cyan", show_lines=True)
            t.add_column("Option",   style="bold yellow", width=18)
            t.add_column("Value",    style="white",       width=20)
            t.add_column("Required", style="red",         width=10)
            t.add_column("Description", style="dim",      width=30)
            for name, (default, desc) in self.options.items():
                val = self._values.get(name, default)
                req = "YES" if not default else "no"
                t.add_row(name, str(val) or "(not set)", req, desc)
            console.print(t)
        else:
            for name, (default, desc) in self.options.items():
                val = self._values.get(name, default)
                print(f"  {name:<18} {str(val):<20} {desc}")

    def run(self, session, workspace):
        raise NotImplementedError

# ── Module: Port Scanner ──────────────────────────────────────────────────────
class PortScannerModule(Module):
    name        = "scanner/portscan"
    category    = "scanner"
    description = "Multi-threaded TCP port scanner with banner grabbing"
    options     = {
        "TARGET":  ("",      "Target host or IP"),
        "PORTS":   ("common","Ports: 1-1024, 80,443, or 'common'"),
        "THREADS": ("100",   "Number of threads"),
        "TIMEOUT": ("0.8",   "Connection timeout (seconds)"),
        "BANNERS": ("false", "Grab service banners"),
    }

    SERVICES = {21:"FTP",22:"SSH",23:"Telnet",25:"SMTP",53:"DNS",
                80:"HTTP",110:"POP3",143:"IMAP",443:"HTTPS",445:"SMB",
                3306:"MySQL",3389:"RDP",5432:"PostgreSQL",6379:"Redis",
                8080:"HTTP-Alt",8443:"HTTPS-Alt",27017:"MongoDB",9200:"Elasticsearch"}

    def run(self, session, workspace):
        target  = self.get("TARGET")
        if not target: return {"status":"error","output":"TARGET not set"}

        port_str = self.get("PORTS")
        timeout  = float(self.get("TIMEOUT"))
        threads  = int(self.get("THREADS"))
        banners  = self.get("BANNERS").lower() == "true"

        # Parse ports
        if port_str == "common":
            ports = list(self.SERVICES.keys())
        elif "-" in port_str:
            s,e = port_str.split("-"); ports = list(range(int(s),int(e)+1))
        elif "," in port_str:
            ports = [int(p) for p in port_str.split(",")]
        else:
            try: ports = list(range(1,int(port_str)+1))
            except: ports = list(self.SERVICES.keys())

        try:
            ip = socket.gethostbyname(target)
        except: return {"status":"error","output":f"Cannot resolve: {target}"}

        rprint(f"\n[cyan]  Scanning {target} ({ip}) — {len(ports)} ports...[/cyan]\n")

        open_ports = []
        lock = threading.Lock()

        def scan(port):
            try:
                with socket.create_connection((ip,port),timeout=timeout):
                    svc = self.SERVICES.get(port,"unknown")
                    banner = ""
                    if banners:
                        try:
                            with socket.create_connection((ip,port),timeout=1) as s:
                                s.send(b"HEAD / HTTP/1.0\r\n\r\n")
                                banner = s.recv(128).decode("utf-8","ignore").split("\n")[0][:60]
                        except: pass
                    with lock:
                        open_ports.append({"port":port,"service":svc,"banner":banner})
                        rprint(f"  [green]OPEN[/green]  [bold]{port:>5}[/bold]/tcp  [yellow]{svc:<14}[/yellow]  [dim]{banner}[/dim]")
            except: pass

        with ThreadPoolExecutor(max_workers=threads) as ex:
            list(ex.map(scan, ports))

        # Store in session
        session["last_scan"] = {"target":target,"ip":ip,"open_ports":open_ports}
        workspace.setdefault("hosts",{})[ip] = {"ports":open_ports,"scanned":datetime.now().isoformat()}
        save_workspace(workspace)

        return {"status":"success","open_ports":open_ports,"target":target,"ip":ip,
                "output":f"Found {len(open_ports)} open ports on {target}"}

# ── Module: SSH Brute Force ───────────────────────────────────────────────────
class SSHBruteModule(Module):
    name        = "brute/ssh"
    category    = "cracker"
    description = "SSH login brute-forcer (your own systems only)"
    options     = {
        "TARGET":   ("",       "Target SSH host"),
        "PORT":     ("22",     "SSH port"),
        "USERNAME": ("root",   "Username to test"),
        "WORDLIST": ("",       "Path to password wordlist"),
        "DELAY":    ("0.1",    "Delay between attempts (seconds)"),
    }

    BUILTIN = ["password","123456","admin","root","toor","pass","test",
               "letmein","welcome","changeme","secret","qwerty","abc123"]

    def run(self, session, workspace):
        target   = self.get("TARGET"); port = int(self.get("PORT"))
        user     = self.get("USERNAME"); delay = float(self.get("DELAY"))
        wordlist = self.get("WORDLIST")

        if not target: return {"status":"error","output":"TARGET not set"}

        # Check if paramiko available (optional)
        try:
            import paramiko
            has_ssh = True
        except ImportError:
            has_ssh = False

        if not has_ssh:
            # Simulate/demo mode
            rprint(f"\n[yellow]  ⚠️  paramiko not installed — running in DEMO mode[/yellow]")
            rprint(f"  [dim]Install: pip install paramiko[/dim]\n")
            rprint(f"  [cyan]Would attempt SSH brute-force:[/cyan]")
            rprint(f"    Target:   {target}:{port}")
            rprint(f"    User:     {user}")

            words = self.BUILTIN
            if wordlist:
                try:
                    with open(wordlist) as f:
                        words = [l.strip() for l in f if l.strip()]
                except: pass

            rprint(f"    Wordlist: {len(words)} passwords")
            rprint(f"\n  [dim]Sample attempts that would be made:[/dim]")
            for pw in words[:5]:
                rprint(f"    [dim]→ {user}:{pw}[/dim]")
            if len(words) > 5:
                rprint(f"    [dim]... and {len(words)-5} more[/dim]")

            return {"status":"demo","output":"Demo mode — install paramiko for real testing"}

        # Real SSH brute force (only runs if paramiko installed)
        words = self.BUILTIN
        if wordlist:
            try:
                with open(wordlist) as f:
                    words = [l.strip() for l in f if l.strip()]
            except:
                rprint(f"  [yellow]Wordlist not found, using built-in ({len(self.BUILTIN)} words)[/yellow]")

        rprint(f"\n  [cyan]SSH Brute-Force: {user}@{target}:{port}[/cyan]")
        rprint(f"  [dim]{len(words)} passwords to try...[/dim]\n")

        for i, pw in enumerate(words):
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            rprint(f"  [dim]Trying {i+1}/{len(words)}: {user}:{pw}[/dim]", end="\r")
            try:
                ssh.connect(target, port=port, username=user, password=pw,
                           timeout=5, allow_agent=False, look_for_keys=False)
                rprint(f"\n  [green bold]🔓  SUCCESS! {user}:{pw}[/green bold]                    ")
                session["ssh_creds"] = {"host":target,"port":port,"user":user,"password":pw}
                ssh.close()
                return {"status":"success","credentials":{"user":user,"password":pw},
                        "output":f"Login found: {user}:{pw}"}
            except paramiko.AuthenticationException: pass
            except Exception as e: rprint(f"\n  [red]Connection error: {e}[/red]"); break
            time.sleep(delay)

        rprint(f"\n  [red]No credentials found.[/red]")
        return {"status":"failed","output":"No valid credentials found"}

# ── Module: HTTP Recon ────────────────────────────────────────────────────────
class HTTPReconModule(Module):
    name        = "recon/http"
    category    = "recon"
    description = "HTTP reconnaissance — headers, tech stack, directories"
    options     = {
        "TARGET":     ("",     "Target URL"),
        "DIRLIST":    ("true", "Enumerate common directories"),
        "HEADERS":    ("true", "Analyze security headers"),
        "TECH":       ("true", "Detect technology stack"),
        "TIMEOUT":    ("5",    "Request timeout"),
        "THREADS":    ("20",   "Directory scan threads"),
    }

    COMMON_DIRS = [
        "admin","login","wp-admin","phpmyadmin","api","v1","v2",".git",
        "backup","uploads","images","static","assets","config","db",
        "test","dev","staging","robots.txt","sitemap.xml",".env",
        "wp-content","wp-includes","includes","lib","src","app",
        "console","panel","manager","dashboard","portal","secure",
    ]

    TECH_SIGNATURES = {
        "WordPress":   ["wp-content","wp-includes","WordPress"],
        "Drupal":      ["Drupal","sites/default"],
        "Django":      ["csrfmiddlewaretoken","Django"],
        "Laravel":     ["laravel_session","Laravel"],
        "React":       ["__REACT_DEVTOOLS","react.js"],
        "Vue.js":      ["__vue__","vue.js"],
        "jQuery":      ["jquery","jQuery"],
        "Bootstrap":   ["bootstrap","Bootstrap"],
        "nginx":       ["nginx"],
        "Apache":      ["Apache","apache"],
        "PHP":         ["php","PHP","X-Powered-By: PHP"],
        "ASP.NET":     ["ASP.NET","__VIEWSTATE"],
    }

    def run(self, session, workspace):
        target = self.get("TARGET")
        if not target: return {"status":"error","output":"TARGET not set"}
        if not target.startswith("http"): target = "https://"+target
        timeout = int(self.get("TIMEOUT"))

        result = {"target":target,"headers":{},"tech":[],"dirs":[],"score":0}

        # 1. Fetch and analyze headers
        rprint(f"\n[cyan]  🌐 HTTP Recon: {target}[/cyan]\n")
        try:
            req  = UReq(target, headers={"User-Agent":"FORGE-Meta/1.0"})
            resp = urlopen(req, timeout=timeout)
            headers = dict(resp.headers)
            body    = resp.read(8192).decode("utf-8","ignore")
            code    = resp.status
        except HTTPError as e:
            headers = dict(e.headers); body = ""; code = e.code
        except Exception as e:
            return {"status":"error","output":str(e)}

        rprint(f"  [green]Status: {code}[/green]  Target: {target}")

        # Security headers
        if self.get("HEADERS").lower() == "true":
            rprint(f"\n  [bold]Security Headers:[/bold]")
            sec = {"Strict-Transport-Security":"HSTS","Content-Security-Policy":"CSP",
                   "X-Frame-Options":"XFO","X-Content-Type-Options":"XCTO",
                   "Server":"SRV (info leak)","X-Powered-By":"XPB (info leak)"}
            found_good = 0
            for h, label in sec.items():
                val = headers.get(h,"")
                if val:
                    is_risk = "info leak" in label
                    color = "red" if is_risk else "green"
                    rprint(f"    [{color}]{'⚠' if is_risk else '✓'}[/{color}]  {h}: [dim]{val[:55]}[/dim]")
                    if not is_risk: found_good += 1
                else:
                    if "info leak" not in label:
                        rprint(f"    [yellow]✗[/yellow]  [dim]{h}: missing[/dim]")
            result["score"] = round(found_good/4*100)
            rprint(f"\n  Security Score: [{'green' if result['score']>=70 else 'yellow'}]{result['score']}%[/]")
            result["headers"] = headers

        # Tech detection
        if self.get("TECH").lower() == "true":
            rprint(f"\n  [bold]Technology Detection:[/bold]")
            all_text = body + str(headers)
            detected = []
            for tech, sigs in self.TECH_SIGNATURES.items():
                if any(s.lower() in all_text.lower() for s in sigs):
                    detected.append(tech)
                    rprint(f"    [cyan]●[/cyan]  {tech}")
            result["tech"] = detected
            if not detected: rprint(f"    [dim]No signatures detected[/dim]")

        # Directory enumeration
        if self.get("DIRLIST").lower() == "true":
            rprint(f"\n  [bold]Directory Enumeration:[/bold] ({len(self.COMMON_DIRS)} paths)")
            found_dirs = []
            lock = threading.Lock()

            def check_dir(path):
                url = target.rstrip("/") + "/" + path
                try:
                    req  = UReq(url, headers={"User-Agent":"FORGE-Meta/1.0"})
                    resp = urlopen(req, timeout=timeout)
                    code = resp.status
                    if code < 400:
                        with lock:
                            found_dirs.append({"path":path,"code":code,"url":url})
                            color = "green" if code == 200 else "yellow"
                            rprint(f"    [{color}]{code}[/{color}]  {path}")
                except HTTPError as e:
                    if e.code not in (404, 403):
                        with lock:
                            found_dirs.append({"path":path,"code":e.code,"url":url})
                            rprint(f"    [dim]{e.code}  {path}[/dim]")
                except: pass

            threads_n = int(self.get("THREADS"))
            with ThreadPoolExecutor(max_workers=threads_n) as ex:
                list(ex.map(check_dir, self.COMMON_DIRS))

            result["dirs"] = found_dirs
            rprint(f"\n  Found {len(found_dirs)} accessible path(s)")

        # Store in workspace
        domain = target.replace("https://","").replace("http://","").split("/")[0]
        workspace.setdefault("targets",{})[domain] = result
        session["last_recon"] = result
        save_workspace(workspace)

        return {"status":"success","data":result,
                "output":f"Recon complete: {len(result['tech'])} techs, {len(result['dirs'])} dirs, score {result['score']}%"}

# ── Module: Hash Cracker ──────────────────────────────────────────────────────
class HashCrackModule(Module):
    name        = "cracker/hash"
    category    = "cracker"
    description = "Dictionary hash cracker (MD5/SHA1/SHA256/SHA512)"
    options     = {
        "HASH":     ("",  "Hash to crack"),
        "TYPE":     ("auto","Hash type: md5/sha1/sha256/sha512/auto"),
        "WORDLIST": ("",  "Wordlist path (blank = built-in)"),
        "RULES":    ("true","Apply common mutations (cap, +1, +123...)"),
    }

    BUILTIN = [
        "password","123456","admin","letmein","welcome","dragon","master",
        "sunshine","princess","monkey","shadow","superman","batman","qwerty",
        "password123","abc123","iloveyou","trustno1","hello","secret","test",
        "root","toor","pass","changeme","default","hunter2","guest","login",
    ]

    def run(self, session, workspace):
        target = self.get("HASH").strip().lower()
        if not target: return {"status":"error","output":"HASH not set"}

        htype = self.get("TYPE")
        if htype == "auto":
            lens = {32:"md5",40:"sha1",56:"sha224",64:"sha256",96:"sha384",128:"sha512"}
            htype = lens.get(len(target),"md5")
        rprint(f"\n  [cyan]Hash:[/cyan] {target[:32]}...  [cyan]Type:[/cyan] {htype.upper()}")

        words = self.BUILTIN
        wordlist = self.get("WORDLIST")
        if wordlist:
            try:
                with open(wordlist) as f:
                    words = [l.strip() for l in f if l.strip()]
                rprint(f"  [green]Loaded {len(words):,} words[/green]")
            except:
                rprint(f"  [yellow]Wordlist not found, using built-in[/yellow]")

        use_rules = self.get("RULES").lower() == "true"
        start = time.time()
        tried = 0

        rprint(f"  [dim]Cracking...[/dim]\n")
        for word in words:
            variants = [word]
            if use_rules:
                variants += [word.capitalize(), word.upper(), word+"1",
                             word+"123", word+"!", "1"+word, word+"2024"]
            for v in variants:
                tried += 1
                h = hashlib.new(htype, v.encode()).hexdigest()
                if h == target:
                    elapsed = round(time.time()-start, 3)
                    rprint(f"  [green bold]🔓  CRACKED in {elapsed}s after {tried:,} attempts![/green bold]")
                    rprint(f"  [bold]Password: [green]{v}[/green][/bold]")
                    session["cracked_hash"] = {"hash":target,"type":htype,"password":v}
                    workspace.setdefault("creds",[]).append({"hash":target,"plain":v})
                    save_workspace(workspace)
                    return {"status":"success","password":v,"attempts":tried,
                            "output":f"Cracked: {v} ({tried:,} attempts)"}

        elapsed = round(time.time()-start, 2)
        rprint(f"  [red]Not found.[/red] ({tried:,} tried in {elapsed}s)")
        return {"status":"failed","output":f"Not found in {tried:,} attempts"}

# ── Module: Network Sniffer Info ──────────────────────────────────────────────
class NetworkInfoModule(Module):
    name        = "recon/network"
    category    = "recon"
    description = "Local network information and interface discovery"
    options = {
        "VERBOSE": ("true", "Show detailed info"),
    }

    def run(self, session, workspace):
        rprint(f"\n  [cyan bold]📡 Network Information[/cyan bold]\n")
        info = {}

        # Hostname
        hostname = socket.gethostname()
        info["hostname"] = hostname
        rprint(f"  [bold]Hostname:[/bold]  {hostname}")

        # Local IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except:
            local_ip = "127.0.0.1"
        info["local_ip"] = local_ip
        rprint(f"  [bold]Local IP:[/bold]  {local_ip}")

        # All interfaces via ifconfig/ip
        try:
            r = subprocess.run(["ip","addr"], capture_output=True, text=True, timeout=3)
            if r.returncode == 0:
                ips = re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", r.stdout)
                rprint(f"  [bold]Interfaces:[/bold]")
                for ip in ips:
                    rprint(f"    [green]●[/green]  {ip}")
                info["all_ips"] = ips
        except: pass

        # DNS resolution test
        test_hosts = ["google.com","cloudflare.com","github.com"]
        rprint(f"\n  [bold]DNS Resolution:[/bold]")
        for h in test_hosts:
            try:
                ip = socket.gethostbyname(h)
                rprint(f"    [green]✓[/green]  {h} → {ip}")
            except:
                rprint(f"    [red]✗[/red]  {h} → failed")

        # Open ports on localhost
        rprint(f"\n  [bold]Listening Ports (localhost):[/bold]")
        common = [21,22,23,25,53,80,443,3306,5432,6379,8080,8443,27017,9200]
        listening = []
        for p in common:
            try:
                with socket.create_connection(("127.0.0.1",p), timeout=0.3):
                    svc = PortScannerModule.SERVICES.get(p,"unknown")
                    listening.append(p)
                    rprint(f"    [green]OPEN[/green]  {p:<6} {svc}")
            except: pass
        if not listening: rprint(f"    [dim]No common ports open locally[/dim]")
        info["listening"] = listening

        session["network_info"] = info
        return {"status":"success","data":info,"output":f"Network info collected, {len(listening)} local ports open"}

# ── Module: Password Generator ────────────────────────────────────────────────
class PassGenModule(Module):
    name        = "util/passgen"
    category    = "util"
    description = "Cryptographically secure password generator"
    options     = {
        "LENGTH":  ("16",   "Password length"),
        "COUNT":   ("10",   "Number of passwords"),
        "SPECIAL": ("true", "Include special characters"),
        "EXCLUDE": ("0O1lI","Characters to exclude"),
        "TYPE":    ("mixed","mixed / phrase / pin"),
    }

    WORDS = [
        "apple","brave","cloud","dance","eagle","flame","grace","happy",
        "igloo","joker","kite","lemon","mango","night","ocean","piano",
        "queen","river","solar","tiger","ultra","vivid","water","xenon",
        "yacht","zebra","amber","blaze","crisp","drift","ember","frost",
    ]

    def run(self, session, workspace):
        length  = int(self.get("LENGTH"))
        count   = int(self.get("COUNT"))
        special = self.get("SPECIAL").lower() == "true"
        exclude = self.get("EXCLUDE")
        ptype   = self.get("TYPE")

        rprint(f"\n  [cyan bold]🔓 Password Generator[/cyan bold]\n")

        charset = string.ascii_lowercase + string.ascii_uppercase + string.digits
        if special: charset += "!@#$%^&*()-_=+[]{}|;:,.<>?"
        charset = "".join(c for c in charset if c not in exclude)

        passwords = []

        if ptype == "phrase":
            for _ in range(count):
                words = [secrets.choice(self.WORDS) for _ in range(4)]
                num   = secrets.randbelow(9999)
                pw    = "-".join(words) + f"-{num}"
                passwords.append(pw)
                rprint(f"    [green]{pw}[/green]")
        elif ptype == "pin":
            for _ in range(count):
                pw = "".join(str(secrets.randbelow(10)) for _ in range(length))
                passwords.append(pw)
                rprint(f"    [green]{pw}[/green]")
        else:
            for _ in range(count):
                while True:
                    pw = "".join(secrets.choice(charset) for _ in range(length))
                    if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                            and any(c.isdigit() for c in pw)):
                        break
                passwords.append(pw)
                score = min(100, len(pw)*4 + (20 if special else 0))
                bar   = "█"*int(score/10)+"░"*(10-int(score/10))
                rprint(f"    [green]{pw}[/green]  [dim][{bar}] {score}%[/dim]")

        session["generated_passwords"] = passwords
        return {"status":"success","passwords":passwords,
                "output":f"Generated {len(passwords)} passwords"}

# ── Module: OSINT Recon ───────────────────────────────────────────────────────
class OSINTModule(Module):
    name        = "recon/osint"
    category    = "recon"
    description = "Open-source intelligence gathering (DNS, WHOIS, headers)"
    options     = {
        "TARGET":  ("", "Domain or IP to investigate"),
        "DEEP":    ("false","Deep scan (more requests)"),
    }

    def run(self, session, workspace):
        target = self.get("TARGET")
        if not target: return {"status":"error","output":"TARGET not set"}
        target = target.replace("http://","").replace("https://","").split("/")[0]

        rprint(f"\n  [cyan bold]🕵️  OSINT: {target}[/cyan bold]\n")
        data = {"target":target}

        # DNS lookups
        rprint(f"  [bold]DNS Records:[/bold]")
        record_types = ["A","AAAA","MX","NS","TXT","CNAME"]
        dns_results = {}
        for rtype in record_types:
            try:
                result = subprocess.run(
                    ["dig", "+short", rtype, target],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    records = [r.strip() for r in result.stdout.strip().split("\n") if r.strip()]
                    dns_results[rtype] = records
                    for r in records[:3]:
                        rprint(f"    [green]{rtype:<6}[/green]  {r}")
            except:
                # Fallback to socket
                if rtype == "A":
                    try:
                        ip = socket.gethostbyname(target)
                        dns_results["A"] = [ip]
                        rprint(f"    [green]A     [/green]  {ip}")
                    except: pass
        data["dns"] = dns_results

        # Reverse DNS
        for ip in dns_results.get("A",[])[:1]:
            try:
                hostname = socket.gethostbyaddr(ip)[0]
                rprint(f"    [green]rDNS  [/green]  {ip} → {hostname}")
                data["rdns"] = hostname
            except: pass

        # HTTP fingerprinting
        rprint(f"\n  [bold]HTTP Fingerprint:[/bold]")
        for scheme in ["https","http"]:
            url = f"{scheme}://{target}"
            try:
                req  = UReq(url, headers={"User-Agent":"Mozilla/5.0"})
                resp = urlopen(req, timeout=5)
                hdrs = dict(resp.headers)
                data["http"] = hdrs
                interesting = ["Server","X-Powered-By","X-Generator","X-Frame-Options",
                               "Content-Type","CF-Cache-Status","X-Cache"]
                for h in interesting:
                    if h in hdrs:
                        color = "red" if h in ("Server","X-Powered-By","X-Generator") else "dim"
                        rprint(f"    [{color}]{h}: {hdrs[h][:60]}[/{color}]")
                rprint(f"    [green]Status: {resp.status}[/green]  via {scheme.upper()}")
                break
            except: continue

        # Common subdomains check
        if self.get("DEEP").lower() == "true":
            rprint(f"\n  [bold]Quick Subdomain Check:[/bold]")
            for sub in ["www","mail","api","dev","staging","blog","admin"]:
                full = f"{sub}.{target}"
                try:
                    ip = socket.gethostbyname(full)
                    rprint(f"    [green]●[/green]  {full} → {ip}")
                    data.setdefault("subdomains",[]).append({"sub":full,"ip":ip})
                except: pass

        session["osint"] = data
        workspace.setdefault("targets",{})[target] = {**workspace.get("targets",{}).get(target,{}),"osint":data}
        save_workspace(workspace)

        return {"status":"success","data":data,
                "output":f"OSINT complete for {target}"}

# ══════════════════════════════════════════════════════════════════════════════
# 🗄️ WORKSPACE & SESSION
# ══════════════════════════════════════════════════════════════════════════════

def load_workspace():
    if WORKSPACE_F.exists():
        return json.loads(WORKSPACE_F.read_text())
    return {"name":"default","hosts":{},"targets":{},"creds":[],"notes":[],"created":datetime.now().isoformat()}

def save_workspace(ws):
    WORKSPACE_F.write_text(json.dumps(ws, indent=2))

def new_session():
    return {"id": secrets.token_hex(4), "started": datetime.now().isoformat(),
            "last_scan":None, "last_recon":None, "network_info":None,
            "cracked_hash":None, "generated_passwords":[], "osint":None}

# ══════════════════════════════════════════════════════════════════════════════
# 🎯 MODULE REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

BUILTIN_MODULES = {
    "scanner/portscan": PortScannerModule,
    "brute/ssh":        SSHBruteModule,
    "recon/http":       HTTPReconModule,
    "cracker/hash":     HashCrackModule,
    "recon/network":    NetworkInfoModule,
    "util/passgen":     PassGenModule,
    "recon/osint":      OSINTModule,
}

def load_all_modules():
    """Load built-in + dynamically built adaptive modules."""
    modules = dict(BUILTIN_MODULES)
    for f in MODULES_DIR.glob("*.py"):
        try:
            import importlib.util, types
            with open(f) as fp:
                src = fp.read()
            # Extract metadata
            nm = re.search(r"#\s*MODULE_NAME:\s*(.+)", src)
            ct = re.search(r"#\s*CATEGORY:\s*(.+)",    src)
            ds = re.search(r"#\s*DESCRIPTION:\s*(.+)", src)
            op = re.search(r"#\s*OPTIONS:\s*(.+)",     src)
            if nm:
                name = nm.group(1).strip()
                # Create dynamic module class
                opts = {}
                if op:
                    for opt_str in op.group(1).split(","):
                        parts = opt_str.strip().split("=", 1)
                        if len(parts) == 2:
                            k = parts[0].strip()
                            v_parts = parts[1].split(":", 1)
                            default = v_parts[0].strip()
                            desc    = v_parts[1].strip() if len(v_parts) > 1 else ""
                            opts[k] = (default, desc)

                # Build dynamic class
                class DynModule(Module):
                    pass
                DynModule.name        = name
                DynModule.category    = ct.group(1).strip() if ct else "util"
                DynModule.description = ds.group(1).strip() if ds else f.stem
                DynModule.options     = opts
                DynModule._source_file= f

                # Override run method
                exec(compile(src, str(f), "exec"), DynModule.__dict__)
                modules[name] = DynModule
        except Exception as e:
            pass
    return modules

# ══════════════════════════════════════════════════════════════════════════════
# 🖥️ META CONSOLE
# ══════════════════════════════════════════════════════════════════════════════

class ForgeMetaConsole:
    def __init__(self):
        self.modules    = load_all_modules()
        self.active_mod = None
        self.session    = new_session()
        self.workspace  = load_workspace()
        self.history    = []

    def banner(self):
        rprint(f"""
[cyan][bold]
  ███████╗ ██████╗ ██████╗  ██████╗ ███████╗    ███╗   ███╗███████╗████████╗ █████╗
  ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝    ████╗ ████║██╔════╝╚══██╔══╝██╔══██╗
  █████╗  ██║   ██║██████╔╝██║  ███╗█████╗      ██╔████╔██║█████╗     ██║   ███████║
  ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝      ██║╚██╔╝██║██╔══╝     ██║   ██╔══██║
  ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗    ██║ ╚═╝ ██║███████╗   ██║   ██║  ██║
  ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝    ╚═╝     ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝
[/bold][/cyan]
[dim]  Framework for Orchestrated Reasoning & Generation of Engines — Meta Edition[/dim]
[yellow]  🎯 Metasploit-style console  |  🧠 Adaptive AI engine  |  {len(self.modules)} modules loaded[/yellow]
[dim]  Session: {self.session['id']}  |  Type 'help' for commands[/dim]
""")

    def prompt(self):
        if self.active_mod:
            prefix = f"[bold cyan]forge-meta[/bold cyan][dim]({self.active_mod.name})[/dim][bold cyan] >[/bold cyan] "
        else:
            prefix = "[bold cyan]forge-meta >[/bold cyan] "
        if RICH:
            return console.input(prefix).strip()
        return input("forge-meta > ").strip()

    def cmd_help(self, args):
        help_text = """[bold cyan]FORGE META Commands:[/bold cyan]

[bold]Module Commands:[/bold]
  [yellow]search[/yellow] [keyword]          Search modules by name/category
  [yellow]use[/yellow] <module>              Load a module
  [yellow]info[/yellow] [module]             Show module info
  [yellow]show modules[/yellow]              List all modules
  [yellow]show options[/yellow]              Show current module options
  [yellow]show sessions[/yellow]             Show session data
  [yellow]show workspace[/yellow]            Show workspace data
  [yellow]set[/yellow] <OPTION> <value>      Set module option
  [yellow]unset[/yellow] <OPTION>            Clear module option
  [yellow]run[/yellow]                       Execute current module
  [yellow]back[/yellow]                      Exit current module

[bold]Adaptive Commands:[/bold]
  [yellow]adapt[/yellow] <description>       Build a NEW module for any situation
  [yellow]adapt list[/yellow]                Show adaptively built modules
  [yellow]adapt history[/yellow]             Show adaptation log

[bold]Workspace:[/bold]
  [yellow]workspace[/yellow]                 Show workspace info
  [yellow]workspace clear[/yellow]           Clear workspace
  [yellow]notes[/yellow] <text>              Add a note to workspace
  [yellow]creds[/yellow]                     Show collected credentials

[bold]Utility:[/bold]
  [yellow]session[/yellow]                   Show current session
  [yellow]history[/yellow]                   Show command history
  [yellow]clear[/yellow]                     Clear screen
  [yellow]exit[/yellow]                      Exit FORGE META"""
        rpanel(help_text, title="Help", border="cyan")

    def cmd_search(self, args):
        query = " ".join(args).lower() if args else ""
        modules = self.modules

        if RICH:
            t = Table(title="🔍  Module Search" + (f': "{query}"' if query else ""),
                      border_style="cyan", show_lines=True, box=rbox.ROUNDED)
            t.add_column("#",           style="dim",         width=4)
            t.add_column("Name",        style="bold yellow", width=25)
            t.add_column("Category",    style="cyan",        width=12)
            t.add_column("Description", style="white",       width=40)
            t.add_column("Type",        style="dim",         width=8)

            for i, (name, cls) in enumerate(sorted(modules.items()), 1):
                obj = cls() if isinstance(cls, type) else cls
                if query and query not in name.lower() and query not in obj.description.lower() and query not in obj.category.lower():
                    continue
                is_adaptive = hasattr(cls, '_source_file')
                t.add_row(str(i), name, obj.category, obj.description[:40],
                          "[magenta]adaptive[/magenta]" if is_adaptive else "[green]built-in[/green]")
            console.print(t)
        else:
            for name, cls in sorted(modules.items()):
                obj = cls() if isinstance(cls, type) else cls
                if not query or query in name or query in obj.description.lower():
                    print(f"  {name:<28} {obj.category:<12} {obj.description[:40]}")

    def cmd_use(self, args):
        if not args:
            rprint("[red]Usage: use <module_name>[/red]"); return

        name = args[0]
        # Partial match
        if name not in self.modules:
            matches = [k for k in self.modules if name in k]
            if len(matches) == 1:
                name = matches[0]
            elif len(matches) > 1:
                rprint(f"[yellow]Ambiguous: {', '.join(matches)}[/yellow]"); return
            else:
                rprint(f"[red]Module not found: {name}[/red]")
                rprint("[dim]Try 'search' or 'adapt <description>' to build it[/dim]"); return

        cls = self.modules[name]
        self.active_mod = cls() if isinstance(cls, type) else cls
        rprint(f"[green]✓[/green] Using module: [bold]{name}[/bold]")
        rprint(f"[dim]{self.active_mod.description}[/dim]")
        self.active_mod.show_options()

    def cmd_set(self, args):
        if not self.active_mod:
            rprint("[red]No module loaded. Use 'use <module>'[/red]"); return
        if len(args) < 2:
            rprint("[red]Usage: set <OPTION> <value>[/red]"); return
        key, val = args[0], " ".join(args[1:])
        if self.active_mod.set(key, val):
            rprint(f"  [green]{key}[/green] => [bold]{val}[/bold]")
        else:
            rprint(f"  [red]Unknown option: {key}[/red]")
            rprint(f"  [dim]Available: {', '.join(self.active_mod.options.keys())}[/dim]")

    def cmd_run(self, args):
        if not self.active_mod:
            rprint("[red]No module loaded. Use 'use <module>'[/red]"); return
        rprint(f"\n[cyan]⚡ Running: {self.active_mod.name}[/cyan]")
        start = time.time()
        try:
            result = self.active_mod.run(self.session, self.workspace)
            elapsed = round(time.time()-start, 2)
            status = result.get("status","unknown")
            color  = "green" if status=="success" else ("yellow" if status=="demo" else "red")
            rprint(f"\n[{color}]  {status.upper()}[/{color}]  [{elapsed}s]  {result.get('output','')}")
        except Exception as e:
            rprint(f"\n[red]  ERROR: {e}[/red]")

    def cmd_show(self, args):
        what = args[0].lower() if args else ""
        if what == "options":
            if self.active_mod: self.active_mod.show_options()
            else: rprint("[red]No module loaded[/red]")
        elif what == "modules":
            self.cmd_search([])
        elif what == "sessions":
            self._show_json(self.session, "Session Data")
        elif what == "workspace":
            self._show_json(self.workspace, "Workspace")
        else:
            rprint(f"[dim]Show: options | modules | sessions | workspace[/dim]")

    def _show_json(self, data, title):
        if RICH:
            import json as _json
            console.print(Panel(
                Syntax(_json.dumps(data, indent=2, default=str), "json",
                       theme="monokai", line_numbers=False),
                title=title, border_style="cyan"))
        else:
            print(json.dumps(data, indent=2, default=str))

    def cmd_info(self, args):
        name = args[0] if args else (self.active_mod.name if self.active_mod else None)
        if not name: rprint("[red]Usage: info <module>[/red]"); return
        cls = self.modules.get(name)
        if not cls: rprint(f"[red]Module not found: {name}[/red]"); return
        obj = cls() if isinstance(cls, type) else cls
        rpanel(
            f"[bold]Name:[/bold]        {obj.name}\n"
            f"[bold]Category:[/bold]    {obj.category}\n"
            f"[bold]Description:[/bold] {obj.description}\n"
            f"[bold]Options:[/bold]     {len(obj.options)}",
            title=f"ℹ️  {name}", border="blue")
        obj.show_options()

    # ── Adaptive Commands ─────────────────────────────────────────────────────

    def cmd_adapt(self, args):
        if not args:
            rprint("[red]Usage: adapt <description of what you need>[/red]")
            rprint("[dim]Example: adapt a tool that checks if a URL redirects[/dim]"); return

        if args[0] == "list":
            self._adapt_list(); return
        if args[0] == "history":
            self._adapt_history(); return

        description = " ".join(args)
        rprint(f"\n[magenta bold]🧠  ADAPTIVE ENGINE — Analyzing situation...[/magenta bold]")

        if not AI_AVAILABLE:
            rprint("[red]AI not available (anthropic not installed)[/red]")
            rprint("[dim]Install: pip install anthropic[/dim]"); return

        # Step 1: Analyze situation
        rprint(f"[dim]  Analyzing: \"{description}\"[/dim]")
        situation = adapt_analyze_situation(description)

        if not situation:
            rprint("[red]  Could not analyze situation. Try being more specific.[/red]"); return

        # Safety check
        if not situation.get("safe", True):
            rprint(f"[red bold]  ⛔ BLOCKED: {situation.get('reason_if_unsafe','Potentially harmful')}[/red bold]")
            rprint("[dim]  FORGE META only builds ethical security tools.[/dim]"); return

        # Show what we understood
        rprint(f"\n[green]  ✓ Understood:[/green]")
        rprint(f"    Intent:     [cyan]{situation.get('intent','')}[/cyan]")
        rprint(f"    Building:   [yellow]{situation.get('capability_needed','')}[/yellow]")
        rprint(f"    Module:     [bold]{situation.get('module_name','')}[/bold]")
        rprint(f"    Category:   {situation.get('category','util')}")

        # Check if we already have something similar
        existing = [k for k in self.modules if situation.get('module_name','') in k]
        if existing:
            rprint(f"\n[yellow]  Similar module exists: {existing[0]}[/yellow]")
            if not self._confirm("  Build anyway?"):
                rprint(f"[dim]  Try: use {existing[0]}[/dim]"); return

        # Step 2: Build the module
        rprint(f"\n[magenta]  🔨 Building module...[/magenta]")
        code = adapt_build_module(situation, description)

        if not code:
            rprint("[red]  Failed to build module.[/red]"); return

        # Step 3: Save and load
        module_name = situation.get("module_name","adaptive_tool")
        fp = adapt_save_module(module_name, code, situation)

        # Step 4: Validate syntax
        r = subprocess.run([sys.executable,"-m","py_compile",str(fp)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            rprint(f"[red]  Syntax error in generated module:[/red]")
            rprint(f"[dim]  {r.stderr[:200]}[/dim]")
            # Try to fix
            rprint("[yellow]  Auto-fixing...[/yellow]")
            fix_prompt = f"Fix this Python syntax error:\n{r.stderr}\n\nCode:\n```python\n{code}\n```"
            fixed = ai_call(fix_prompt, "Fix Python syntax errors. Reply with only ```python...``` block.", 2000)
            if fixed:
                fm = re.search(r"```python\s*(.*?)```", fixed, re.DOTALL)
                if fm:
                    code = fm.group(1).strip()
                    fp.write_text(f"# AUTO-FIXED\n\n" + code)
                    r2 = subprocess.run([sys.executable,"-m","py_compile",str(fp)],
                                        capture_output=True, text=True)
                    if r2.returncode != 0:
                        rprint("[red]  Could not fix. Module saved but may not work.[/red]")
                    else:
                        rprint("[green]  ✅ Fixed![/green]")

        # Step 5: Register and load
        self.modules = load_all_modules()

        rprint(f"\n[green bold]  ✅ NEW MODULE BUILT: {situation.get('category','util')}/{module_name}[/green bold]")
        rprint(f"[dim]  File: {fp}[/dim]")

        if self._confirm("\n  Load it now?"):
            full_name = f"{situation.get('category','util')}/{module_name}"
            if full_name in self.modules:
                self.cmd_use([full_name])
            else:
                # Try partial match
                matches = [k for k in self.modules if module_name in k]
                if matches:
                    self.cmd_use([matches[0]])
                else:
                    rprint(f"[yellow]  Module saved. Use 'search {module_name}' to find it.[/yellow]")

    def _adapt_list(self):
        adaptive = [k for k,v in self.modules.items() if hasattr(v,'_source_file')]
        if not adaptive:
            rprint("[dim]No adaptive modules built yet. Try 'adapt <description>'[/dim]"); return
        rprint(f"\n[magenta bold]🧠 Adaptive Modules ({len(adaptive)}):[/magenta bold]")
        for name in adaptive:
            cls = self.modules[name]
            obj = cls() if isinstance(cls, type) else cls
            rprint(f"  [magenta]●[/magenta]  [bold]{name}[/bold]  [dim]{obj.description[:50]}[/dim]")

    def _adapt_history(self):
        if not ADAPT_LOG.exists():
            rprint("[dim]No adaptation history yet.[/dim]"); return
        log = json.loads(ADAPT_LOG.read_text())
        rprint(f"\n[magenta bold]🧠 Adaptation History:[/magenta bold]")
        for entry in reversed(log[-10:]):
            ts = entry.get("built","")[:16]
            rprint(f"  [dim]{ts}[/dim]  [magenta]{entry.get('module','')}[/magenta]  {entry.get('intent','')[:55]}")

    def _confirm(self, msg):
        try:
            r = (console.input(f"[dim]{msg} (y/n)[/dim] ") if RICH else input(f"{msg} (y/n) ")).strip().lower()
            return r == "y"
        except: return False

    def cmd_workspace(self, args):
        what = args[0].lower() if args else ""
        if what == "clear":
            self.workspace = {"name":"default","hosts":{},"targets":{},"creds":[],"notes":[],"created":datetime.now().isoformat()}
            save_workspace(self.workspace); rprint("[green]Workspace cleared.[/green]")
        else:
            self._show_json(self.workspace, "🗄️ Workspace")

    def cmd_notes(self, args):
        if not args: rprint("[dim]Usage: notes <text>[/dim]"); return
        note = {"text":" ".join(args),"ts":datetime.now().isoformat()}
        self.workspace.setdefault("notes",[]).append(note)
        save_workspace(self.workspace)
        rprint(f"[green]✓ Note saved[/green]")

    def cmd_creds(self, args):
        creds = self.workspace.get("creds",[])
        if not creds: rprint("[dim]No credentials collected yet.[/dim]"); return
        rprint(f"\n[bold]Collected Credentials ({len(creds)}):[/bold]")
        for c in creds:
            rprint(f"  [green]●[/green]  {json.dumps(c)}")

    def cmd_session(self, args):
        self._show_json(self.session, "🔑 Session")

    def cmd_history(self, args):
        if not self.history: rprint("[dim]No history.[/dim]"); return
        for i, cmd in enumerate(self.history[-20:], 1):
            rprint(f"  [dim]{i:>3}[/dim]  {cmd}")

    def run(self):
        self.banner()

        COMMANDS = {
            "help":      self.cmd_help,
            "?":         self.cmd_help,
            "search":    self.cmd_search,
            "use":       self.cmd_use,
            "set":       self.cmd_set,
            "unset":     lambda a: self.active_mod.set(a[0],"") if self.active_mod and a else None,
            "run":       self.cmd_run,
            "execute":   self.cmd_run,
            "exploit":   self.cmd_run,
            "show":      self.cmd_show,
            "info":      self.cmd_info,
            "back":      lambda a: setattr(self,"active_mod",None) or rprint("[dim]Exited module.[/dim]"),
            "adapt":     self.cmd_adapt,
            "workspace": self.cmd_workspace,
            "notes":     self.cmd_notes,
            "creds":     self.cmd_creds,
            "session":   self.cmd_session,
            "history":   self.cmd_history,
            "clear":     lambda a: os.system("clear"),
            "reload":    lambda a: setattr(self,"modules",load_all_modules()) or rprint(f"[green]Reloaded {len(self.modules)} modules[/green]"),
        }

        while True:
            try:
                raw = self.prompt()
            except (KeyboardInterrupt, EOFError):
                rprint(f"\n[cyan]⚒️  FORGE META — Stay ethical. 🔥[/cyan]"); break

            if not raw: continue
            parts   = raw.split()
            cmd     = parts[0].lower()
            args    = parts[1:]

            if cmd in ("exit","quit","q"):
                rprint("[cyan]⚒️  FORGE META — Stay ethical. 🔥[/cyan]"); break

            self.history.append(raw)

            if cmd in COMMANDS:
                try:
                    COMMANDS[cmd](args)
                except Exception as e:
                    rprint(f"[red]Error: {e}[/red]")
            else:
                # ── ADAPTIVE FALLBACK — unknown command → try to build a module ──
                rprint(f"[yellow]  Unknown command: '{raw}'[/yellow]")
                if AI_AVAILABLE:
                    rprint(f"[dim]  Checking if FORGE can adapt to handle this...[/dim]")
                    self.cmd_adapt(raw.split())
                else:
                    rprint(f"[dim]  Type 'help' for available commands.[/dim]")
                    rprint(f"[dim]  Install anthropic for adaptive AI module building.[/dim]")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    meta = ForgeMetaConsole()
    meta.run()

if __name__ == "__main__":
    main()

# ══════════════════════════════════════════════════════════════════════════════
# 🗣️  NATURAL LANGUAGE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

NL_SYSTEM = """You are FORGE META's natural language interface.

Convert user plain-English input into structured commands.

Available modules: scanner/portscan, brute/ssh, recon/http, recon/network,
recon/osint, cracker/hash, util/passgen, and any user-built adaptive modules.

Reply ONLY with JSON:
{
  "action": "use_and_run | adapt | autopilot | map | info | search | help | unknown",
  "module": "module/name or null",
  "options": {"OPTION": "value"},
  "adapt_description": "what to build if action=adapt",
  "target": "target host/url/hash if present",
  "goal": "overall goal if action=autopilot or map",
  "confidence": 0.0-1.0,
  "explanation": "one line: what you understood"
}

Examples:
- "scan 192.168.1.1" → use_and_run scanner/portscan TARGET=192.168.1.1
- "crack this hash abc123..." → use_and_run cracker/hash HASH=abc123...
- "check headers on example.com" → use_and_run recon/http TARGET=example.com
- "make me 20 passwords" → use_and_run util/passgen COUNT=20
- "find subdomains of tesla.com" → adapt subdomain_finder
- "fully audit mysite.com" → autopilot target=mysite.com
- "map attack surface of 10.0.0.1" → map target=10.0.0.1
- "build a tool that checks SSL certs" → adapt ssl_checker
"""

def nl_parse(user_input, available_modules):
    """Parse natural language into a structured action."""
    mod_list = "\n".join(f"- {k}" for k in available_modules.keys())
    result = ai_call(
        f"User said: \"{user_input}\"\n\nAvailable modules:\n{mod_list}",
        NL_SYSTEM, max_tokens=600
    )
    if not result:
        return None
    try:
        clean = re.sub(r"```[a-z]*\s*", "", result).strip()
        return json.loads(clean)
    except:
        m = re.search(r"\{.*\}", result, re.DOTALL)
        if m:
            try: return json.loads(m.group())
            except: pass
    return None

# ══════════════════════════════════════════════════════════════════════════════
# 🗺️  ATTACK SURFACE MAPPER
# ══════════════════════════════════════════════════════════════════════════════

MAPPER_PLANNER = """You are FORGE META's Attack Surface Mapper.

Given a target and initial recon data, plan a comprehensive attack surface assessment.

You must:
1. List what to scan (ports, web, dns, etc.)
2. Identify what modules to use or build
3. Note what gaps exist (modules we'd need to build)

Reply ONLY with JSON:
{
  "target_type": "domain | ip | url | network",
  "phases": [
    {
      "phase": 1,
      "name": "Initial Recon",
      "modules": ["recon/osint", "recon/network"],
      "new_modules_needed": [],
      "reason": "why this phase"
    }
  ],
  "new_modules_to_build": [
    {
      "name": "ssl_checker",
      "description": "Check SSL cert validity and expiry",
      "category": "recon",
      "why_needed": "need to assess SSL posture"
    }
  ],
  "summary": "what this assessment covers"
}
"""

SURFACE_REPORT = """You are a security report writer.

Given an attack surface assessment with all scan results, write a professional
penetration test findings summary.

Include:
- Executive summary (3 sentences)
- Findings table (critical/high/medium/low)
- Key risks
- Recommendations

Format as clear text with sections. Be specific about findings from the data."""

def mapper_plan(target, recon_data=None):
    """Plan the full attack surface assessment."""
    prompt = f"Target: {target}\n"
    if recon_data:
        prompt += f"Initial data:\n{json.dumps(recon_data, indent=2, default=str)[:2000]}"
    result = ai_call(prompt, MAPPER_PLANNER, max_tokens=2000)
    if not result:
        return None
    try:
        clean = re.sub(r"```[a-z]*\s*", "", result).strip()
        return json.loads(clean)
    except:
        m = re.search(r"\{.*\}", result, re.DOTALL)
        if m:
            try: return json.loads(m.group())
            except: pass
    return None

def mapper_generate_report(target, all_results):
    """Generate a full security report from all findings."""
    summary = f"Target: {target}\n\nFindings:\n"
    for phase, results in all_results.items():
        summary += f"\n[Phase: {phase}]\n"
        for module, result in results.items():
            summary += f"  {module}: {result.get('output','')[:200]}\n"
            if "open_ports" in result:
                summary += f"    Open ports: {[p['port'] for p in result['open_ports']]}\n"
            if "tech" in result.get("data",{}):
                summary += f"    Tech stack: {result['data']['tech']}\n"
            if "dirs" in result.get("data",{}):
                summary += f"    Accessible dirs: {[d['path'] for d in result['data']['dirs']]}\n"

    return ai_call(summary[:4000], SURFACE_REPORT, max_tokens=2000)

# ══════════════════════════════════════════════════════════════════════════════
# 🤖 AUTOPILOT ENGINE
# ══════════════════════════════════════════════════════════════════════════════

AUTOPILOT_SYSTEM = """You are FORGE META's Autopilot — a fully autonomous security assessment engine.

Given a target and goal, create an execution plan that:
1. Uses existing modules where possible
2. Identifies gaps and builds new modules for them
3. Chains results between modules
4. Adapts based on what's discovered

Reply ONLY with JSON:
{
  "goal_understood": "what we're trying to achieve",
  "execution_plan": [
    {
      "step": 1,
      "action": "run_module | build_and_run | analyze_results",
      "module": "module/name",
      "options": {"OPTION": "value"},
      "build_description": "if action=build_and_run, what to build",
      "depends_on": null,
      "use_result_from": null,
      "reason": "why this step"
    }
  ],
  "expected_outcomes": ["what we expect to find"],
  "new_modules_needed": [
    {"name": "module_name", "description": "what it does", "category": "recon"}
  ]
}
"""

AUTOPILOT_ADAPTER = """You are FORGE META's dynamic step adapter.

Based on results from previous steps, decide what to do next.
You can add new steps, skip planned steps, or pivot entirely.

Previous plan step: {step}
Results so far: {results}

Should we:
1. Continue as planned?
2. Add new steps based on findings?
3. Build a new module to investigate something found?

Reply ONLY with JSON:
{
  "continue": true/false,
  "reason": "why",
  "add_steps": [
    {
      "action": "run_module | build_and_run",
      "module": "module/name",
      "options": {},
      "build_description": "if building",
      "reason": "what triggered this"
    }
  ],
  "insight": "key finding from this step"
}
"""

def autopilot_plan(target, goal, modules):
    """Create initial autopilot execution plan."""
    mod_list = "\n".join(f"- {k}: {modules[k]().description}" for k in modules)
    prompt = f"Target: {target}\nGoal: {goal}\n\nAvailable modules:\n{mod_list}"
    result = ai_call(prompt, AUTOPILOT_SYSTEM, max_tokens=3000)
    if not result:
        return None
    try:
        clean = re.sub(r"```[a-z]*\s*", "", result).strip()
        return json.loads(clean)
    except:
        m = re.search(r"\{.*\}", result, re.DOTALL)
        if m:
            try: return json.loads(m.group())
            except: pass
    return None

def autopilot_adapt_step(step, results_so_far, modules):
    """After each step, decide if we should pivot or add steps."""
    prompt = AUTOPILOT_ADAPTER.replace("{step}", json.dumps(step, default=str)) \
                              .replace("{results}", json.dumps(results_so_far, default=str)[:2000])
    result = ai_call(prompt, "You are a security assessment adapter. Reply only with JSON.", max_tokens=1000)
    if not result:
        return {"continue": True, "add_steps": [], "insight": ""}
    try:
        clean = re.sub(r"```[a-z]*\s*", "", result).strip()
        return json.loads(clean)
    except:
        return {"continue": True, "add_steps": [], "insight": ""}

# ══════════════════════════════════════════════════════════════════════════════
# 🖥️  UPGRADED FORGE META CONSOLE (v2)
# ══════════════════════════════════════════════════════════════════════════════

class ForgeMetaV2(ForgeMetaConsole):
    """Extended console with NL, Autopilot, and Attack Surface Mapper."""

    def __init__(self):
        super().__init__()
        self.nl_mode   = False   # natural language mode toggle
        self.autopilot_log = []

    def banner(self):
        rprint(f"""
[cyan][bold]
  ███████╗ ██████╗ ██████╗  ██████╗ ███████╗    ███╗   ███╗███████╗████████╗ █████╗
  ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝    ████╗ ████║██╔════╝╚══██╔══╝██╔══██╗
  █████╗  ██║   ██║██████╔╝██║  ███╗█████╗      ██╔████╔██║█████╗     ██║   ███████║
  ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝      ██║╚██╔╝██║██╔══╝     ██║   ██╔══██║
  ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗    ██║ ╚═╝ ██║███████╗   ██║   ██║  ██║
  ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝    ╚═╝     ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝
[/bold][/cyan]
[magenta bold]  v2 — Natural Language  ·  Attack Surface Mapper  ·  Full Autopilot  ·  Self-Building[/magenta bold]
[dim]  {len(self.modules)} modules loaded  ·  AI {'✅ ready' if AI_AVAILABLE else '❌ offline'}  ·  Type anything naturally or use commands[/dim]
""")

    def prompt(self):
        if self.nl_mode:
            prefix_str = "forge[NL] > "
            prefix_rich = "[bold magenta]forge[NL] >[/bold magenta] "
        elif self.active_mod:
            prefix_str  = f"forge({self.active_mod.name}) > "
            prefix_rich = f"[bold cyan]forge[/bold cyan][dim]({self.active_mod.name})[/dim][bold cyan] >[/bold cyan] "
        else:
            prefix_str  = "forge-meta > "
            prefix_rich = "[bold cyan]forge-meta >[/bold cyan] "

        if RICH:
            return console.input(prefix_rich).strip()
        return input(prefix_str).strip()

    # ── Natural Language ──────────────────────────────────────────────────────

    def cmd_nl(self, args):
        """Toggle natural language mode or process NL command directly."""
        if args:
            # Inline NL: nl scan 192.168.1.1
            self._handle_nl(" ".join(args))
        else:
            self.nl_mode = not self.nl_mode
            state = "[magenta]ON[/magenta]" if self.nl_mode else "[dim]OFF[/dim]"
            rprint(f"\n  🗣️  Natural Language Mode: {state}")
            if self.nl_mode:
                rprint(f"  [dim]Just type what you want. Examples:[/dim]")
                rprint(f"  [dim]  • 'scan 192.168.1.1 for open ports'[/dim]")
                rprint(f"  [dim]  • 'crack the hash 5f4dcc3b5aa765d6...'[/dim]")
                rprint(f"  [dim]  • 'build a tool that checks SSL certs'[/dim]")
                rprint(f"  [dim]  • 'fully audit example.com'[/dim]")
                rprint(f"  [dim]Type 'nl' again to turn off.[/dim]\n")

    def _handle_nl(self, user_input):
        if not AI_AVAILABLE:
            rprint("[red]AI not available — install anthropic for NL mode[/red]"); return

        rprint(f"\n  [dim]🗣️  Parsing: \"{user_input}\"...[/dim]")
        parsed = nl_parse(user_input, self.modules)

        if not parsed:
            rprint("[red]  Could not parse input. Try 'help' for commands.[/red]"); return

        action  = parsed.get("action","unknown")
        explain = parsed.get("explanation","")
        conf    = parsed.get("confidence",0)
        color   = "green" if conf > 0.7 else ("yellow" if conf > 0.4 else "red")

        rprint(f"  [{color}]Understood ({int(conf*100)}%):[/{color}] {explain}")

        if action == "use_and_run":
            module  = parsed.get("module")
            options = parsed.get("options", {})
            target  = parsed.get("target")
            if target and module:
                # Auto-set TARGET if detected
                options["TARGET"] = target
            if not module:
                rprint("[red]  Could not determine which module to use.[/red]"); return
            self.cmd_use([module])
            if self.active_mod:
                for k, v in options.items():
                    if v: self.active_mod.set(k, str(v))
                self.cmd_run([])

        elif action == "adapt":
            desc = parsed.get("adapt_description","")
            if not desc:
                desc = user_input
            self.cmd_adapt(desc.split())

        elif action == "autopilot":
            target = parsed.get("target","")
            goal   = parsed.get("goal","comprehensive security assessment")
            if not target:
                target = input("  Target: ").strip()
            self.cmd_autopilot([target, goal])

        elif action == "map":
            target = parsed.get("target","")
            if not target:
                target = input("  Target: ").strip()
            self.cmd_map([target])

        elif action == "info":
            self.cmd_info(parsed.get("module","").split("/")[1:])

        elif action == "search":
            self.cmd_search([parsed.get("target","")])

        elif action == "help":
            self.cmd_help([])

        else:
            rprint(f"  [yellow]Not sure how to handle that. Trying adapt...[/yellow]")
            self.cmd_adapt(user_input.split())

    # ── Attack Surface Mapper ─────────────────────────────────────────────────

    def cmd_map(self, args):
        """Full attack surface mapping with AI-planned phases."""
        rprint(f"\n[cyan bold]🗺️  ATTACK SURFACE MAPPER[/cyan bold]")
        rprint(f"[dim]Systematically maps an entire target's attack surface.[/dim]\n")

        target = " ".join(args) if args else input("  Target (domain/IP/URL): ").strip()
        if not target: return

        if not AI_AVAILABLE:
            rprint("[red]AI required for surface mapping. Install anthropic.[/red]"); return

        all_results = {}
        new_modules_built = []

        # Phase 0: Quick initial recon to inform the plan
        rprint(f"  [dim]Gathering initial data on {target}...[/dim]")
        initial_data = {}
        try:
            ip = socket.gethostbyname(target.replace("https://","").replace("http://","").split("/")[0])
            initial_data["ip"]       = ip
            initial_data["hostname"] = target
        except: pass

        # Ask AI to plan the full surface map
        rprint(f"\n  [magenta]🤖 AI planning attack surface assessment...[/magenta]")
        plan = mapper_plan(target, initial_data)

        if not plan:
            rprint("[red]  Could not generate plan. Check AI connection.[/red]"); return

        # Show plan
        rprint(f"\n  [bold]Assessment Plan:[/bold]  {plan.get('summary','')[:80]}")
        rprint(f"  [bold]Target type:[/bold]   {plan.get('target_type','unknown')}")
        rprint(f"  [bold]Phases:[/bold]        {len(plan.get('phases',[]))}")
        new_needed = plan.get("new_modules_to_build",[])
        if new_needed:
            rprint(f"  [bold]New modules:[/bold]  {len(new_needed)} will be built on-the-fly")

        if RICH:
            t = Table(border_style="cyan", show_lines=True, title="📋 Phases")
            t.add_column("#",       style="dim",       width=4)
            t.add_column("Phase",   style="bold white",width=20)
            t.add_column("Modules", style="cyan",      width=35)
            t.add_column("Build",   style="magenta",   width=18)
            for ph in plan.get("phases",[]):
                t.add_row(
                    str(ph.get("phase","")),
                    ph.get("name",""),
                    ", ".join(ph.get("modules",[])),
                    ", ".join(ph.get("new_modules_needed",[])) or "─"
                )
            console.print(t)

        if not self._confirm("\n  🚀 Begin surface mapping?"):
            return

        # Build any new modules needed BEFORE starting
        if new_needed:
            rprint(f"\n  [magenta]🔨 Pre-building {len(new_needed)} new module(s)...[/magenta]")
            for mod_spec in new_needed:
                rprint(f"\n    Building: [bold]{mod_spec['name']}[/bold] — {mod_spec['description']}")
                situation = {
                    "intent":             mod_spec["description"],
                    "capability_needed":  mod_spec["description"],
                    "module_name":        mod_spec["name"],
                    "category":           mod_spec.get("category","recon"),
                    "safe":               True,
                    "options_needed":     ["TARGET"],
                }
                code = adapt_build_module(situation, mod_spec["description"])
                if code:
                    fp = adapt_save_module(mod_spec["name"], code, situation)
                    r  = subprocess.run([sys.executable,"-m","py_compile",str(fp)],
                                        capture_output=True, text=True)
                    if r.returncode == 0:
                        rprint(f"    [green]✅ Built: {mod_spec['name']}[/green]")
                        new_modules_built.append(mod_spec["name"])
                    else:
                        rprint(f"    [yellow]⚠️  Syntax issue, skipping[/yellow]")
                else:
                    rprint(f"    [red]✗ Failed[/red]")

            # Reload modules
            self.modules = load_all_modules()
            rprint(f"\n  [green]Modules reloaded: {len(self.modules)} available[/green]")

        # Execute phases
        for ph in plan.get("phases",[]):
            phase_num  = ph.get("phase",0)
            phase_name = ph.get("name","")
            modules    = ph.get("modules",[]) + ph.get("new_modules_needed",[])

            rprint(f"\n{'━'*60}")
            rprint(f"[bold cyan]  Phase {phase_num}: {phase_name}[/bold cyan]")
            rprint(f"  [dim]{ph.get('reason','')}[/dim]")

            phase_results = {}
            for mod_name in modules:
                # Find module (exact or partial)
                cls = self.modules.get(mod_name)
                if not cls:
                    matches = [k for k in self.modules if mod_name in k or mod_name.replace("/","_") in k]
                    if matches:
                        cls = self.modules[matches[0]]
                        mod_name = matches[0]

                if not cls:
                    rprint(f"  [yellow]  ⚠️  Module not found: {mod_name}[/yellow]")
                    continue

                rprint(f"\n  [cyan]▶ {mod_name}[/cyan]")
                mod = cls()

                # Auto-set TARGET
                if "TARGET" in mod.options:
                    mod.set("TARGET", target)
                # Auto-set smart defaults for surface mapping
                if "PORTS" in mod.options: mod.set("PORTS","common")
                if "DEEP"  in mod.options: mod.set("DEEP","true")

                try:
                    result = mod.run(self.session, self.workspace)
                    phase_results[mod_name] = result
                    status = result.get("status","?")
                    color  = "green" if status == "success" else "yellow"
                    rprint(f"  [{color}]  ✓ {result.get('output','')[:80]}[/{color}]")
                except Exception as e:
                    rprint(f"  [red]  ✗ Error: {e}[/red]")
                    phase_results[mod_name] = {"status":"error","output":str(e)}

            all_results[phase_name] = phase_results

        # Generate report
        rprint(f"\n{'━'*60}")
        rprint(f"\n[magenta bold]📊 Generating Security Report...[/magenta bold]")
        report = mapper_generate_report(target, all_results)

        if report:
            rprint(f"\n[bold]{'═'*60}[/bold]")
            rprint(f"[bold cyan]  🛡️  ATTACK SURFACE REPORT: {target}[/bold cyan]")
            rprint(f"[bold]{'═'*60}[/bold]\n")
            rprint(report)

            # Save report
            ts         = datetime.now().strftime("%Y%m%d_%H%M")
            report_fp  = META_DIR / f"report_{re.sub(r'[^\\w]','_',target)}_{ts}.txt"
            report_fp.write_text(f"FORGE META Attack Surface Report\nTarget: {target}\nDate: {datetime.now()}\n\n{report}")
            rprint(f"\n[green]  📄 Report saved: {report_fp}[/green]")
            if new_modules_built:
                rprint(f"  [magenta]  🔨 {len(new_modules_built)} new module(s) built: {', '.join(new_modules_built)}[/magenta]")

    # ── Full Autopilot ────────────────────────────────────────────────────────

    def cmd_autopilot(self, args):
        """Fully autonomous assessment — plans, builds, runs, adapts, reports."""
        rprint(f"\n[magenta bold]🤖 FULL AUTOPILOT MODE[/magenta bold]")
        rprint(f"[dim]FORGE picks modules, builds missing ones, adapts to findings, writes report.[/dim]\n")

        if not AI_AVAILABLE:
            rprint("[red]AI required for autopilot. Install anthropic.[/red]"); return

        target = args[0] if args else input("  Target: ").strip()
        goal   = " ".join(args[1:]) if len(args)>1 else input(
            f"  Goal [comprehensive security assessment]: ").strip() or "comprehensive security assessment"
        if not target: return

        rprint(f"\n  [bold]Target:[/bold] {target}")
        rprint(f"  [bold]Goal:[/bold]   {goal}\n")

        # Phase 1: AI plans everything
        rprint(f"  [magenta]🧠 Planning autonomous assessment...[/magenta]")
        plan = autopilot_plan(target, goal, self.modules)

        if not plan:
            rprint("[red]  Planning failed. Check AI connection.[/red]"); return

        rprint(f"\n  [green]Goal understood:[/green] {plan.get('goal_understood','')[:80]}")
        steps     = plan.get("execution_plan",[])
        new_mods  = plan.get("new_modules_needed",[])

        if RICH:
            t = Table(border_style="magenta", show_lines=True, title="🤖 Autopilot Plan")
            t.add_column("#",      style="dim",         width=4)
            t.add_column("Action", style="bold yellow", width=14)
            t.add_column("Module", style="cyan",        width=22)
            t.add_column("Reason", style="dim",         width=35)
            for s in steps:
                action = s.get("action","")
                name   = s.get("module","") or s.get("build_description","")[:20]
                color  = "magenta" if "build" in action else "cyan"
                t.add_row(str(s.get("step","")),
                          f"[{color}]{action}[/{color}]",
                          name, s.get("reason","")[:34])
            console.print(t)

        if new_mods:
            rprint(f"\n  [magenta]New modules to build:[/magenta]")
            for m in new_mods:
                rprint(f"    [magenta]●[/magenta]  {m['name']} — {m['description']}")

        if not self._confirm(f"\n  🚀 Launch autopilot ({len(steps)} steps)?"):
            return

        # Phase 2: Pre-build required new modules
        if new_mods:
            rprint(f"\n  [magenta bold]🔨 Pre-building required modules...[/magenta bold]")
            for mod_spec in new_mods:
                rprint(f"\n    [dim]Building: {mod_spec['name']}...[/dim]")
                situation = {
                    "intent":            mod_spec["description"],
                    "capability_needed": mod_spec["description"],
                    "module_name":       mod_spec["name"],
                    "category":          mod_spec.get("category","util"),
                    "safe":              True,
                }
                code = adapt_build_module(situation, mod_spec["description"])
                if code:
                    fp = adapt_save_module(mod_spec["name"], code, situation)
                    r  = subprocess.run([sys.executable,"-m","py_compile",str(fp)],
                                        capture_output=True, text=True)
                    if r.returncode == 0:
                        rprint(f"    [green]✅ {mod_spec['name']}[/green]")
                    else:
                        rprint(f"    [yellow]⚠️  {mod_spec['name']} has issues[/yellow]")
                else:
                    rprint(f"    [red]✗ {mod_spec['name']} failed[/red]")
            self.modules = load_all_modules()
            rprint(f"\n  [green]Modules ready: {len(self.modules)} total[/green]")

        # Phase 3: Execute steps with live adaptation
        all_results = {}
        insights    = []
        extra_steps = []
        executed    = 0

        all_plan_steps = steps + extra_steps  # dynamic — grows as AI adds steps

        i = 0
        while i < len(all_plan_steps):
            step = all_plan_steps[i]
            i += 1
            action      = step.get("action","")
            module_name = step.get("module","")
            options     = step.get("options",{})
            step_n      = step.get("step", executed+1)

            rprint(f"\n{'─'*60}")
            rprint(f"[bold]  Step {step_n}/{len(all_plan_steps)}[/bold]  [{action}]  [cyan]{module_name or step.get('build_description','')[:30]}[/cyan]")
            rprint(f"  [dim]{step.get('reason','')}[/dim]")

            result = None

            if action == "build_and_run":
                desc = step.get("build_description","")
                if not desc:
                    rprint("  [yellow]No description for build step.[/yellow]")
                    i += 1; continue

                rprint(f"  [magenta]🔨 Building: {desc[:50]}[/magenta]")
                safe_name = re.sub(r"[^\w]","_",desc[:25].lower())
                situation = {
                    "intent":            desc,
                    "capability_needed": desc,
                    "module_name":       safe_name,
                    "category":          "recon",
                    "safe":              True,
                }
                code = adapt_build_module(situation, desc)
                if code:
                    fp  = adapt_save_module(safe_name, code, situation)
                    r   = subprocess.run([sys.executable,"-m","py_compile",str(fp)],
                                         capture_output=True, text=True)
                    if r.returncode == 0:
                        rprint(f"  [green]✅ Built! Running...[/green]")
                        self.modules = load_all_modules()
                        result = adapt_load_and_run(fp, {**options,"TARGET":target}, self.session, self.workspace)
                        rprint(f"  [cyan]{result.get('output','')[:80]}[/cyan]")
                    else:
                        rprint(f"  [red]Build syntax error — skipping[/red]")
                else:
                    rprint(f"  [red]Build failed — skipping[/red]")

            elif action in ("run_module","analyze_results"):
                cls = self.modules.get(module_name)
                if not cls:
                    matches = [k for k in self.modules if module_name and module_name in k]
                    if matches: cls = self.modules[matches[0]]; module_name = matches[0]

                if not cls:
                    rprint(f"  [yellow]Module not found: {module_name} — skipping[/yellow]")
                else:
                    mod = cls()
                    # Smart option injection
                    if "TARGET" in mod.options: mod.set("TARGET", target)
                    for k,v in options.items():
                        if v: mod.set(k, str(v))
                    # Pass useful context from previous results
                    if "open_ports" in str(all_results):
                        ports = [str(p["port"]) for r in all_results.values()
                                 for p in r.get("open_ports",[])
                                 if isinstance(r,dict)]
                        if ports and "PORT" in mod.options:
                            mod.set("PORT", ports[0])

                    try:
                        result = mod.run(self.session, self.workspace)
                        status = result.get("status","?")
                        color  = "green" if status=="success" else "yellow"
                        rprint(f"  [{color}]✓ {result.get('output','')[:80]}[/{color}]")
                        all_results[module_name] = result
                    except Exception as e:
                        rprint(f"  [red]✗ {e}[/red]")
                        result = {"status":"error","output":str(e)}

            executed += 1
            if result: all_results[f"step_{step_n}_{module_name}"] = result

            # Phase 4: Adaptive re-planning after each step
            if result and AI_AVAILABLE and executed % 2 == 0:
                rprint(f"  [dim]🧠 Adapting based on findings...[/dim]")
                adaptation = autopilot_adapt_step(step, all_results, self.modules)

                if adaptation.get("insight"):
                    insights.append(adaptation["insight"])
                    rprint(f"  [yellow]💡 {adaptation['insight']}[/yellow]")

                new_steps = adaptation.get("add_steps",[])
                if new_steps:
                    rprint(f"  [magenta]➕ Adding {len(new_steps)} adaptive step(s) based on findings[/magenta]")
                    for ns in new_steps:
                        ns["step"] = len(all_plan_steps) + 1
                        all_plan_steps.append(ns)

            if executed >= 15:  # Safety cap
                rprint(f"  [yellow]  Step limit reached (15). Finalizing...[/yellow]")
                break

        # Final report
        rprint(f"\n{'═'*60}")
        rprint(f"[magenta bold]  📊 AUTOPILOT COMPLETE — Generating Report...[/magenta bold]")
        rprint(f"{'═'*60}")
        rprint(f"\n  Steps executed:    {executed}")
        rprint(f"  Insights found:    {len(insights)}")
        rprint(f"  New modules built: {len([s for s in all_plan_steps if 'build' in s.get('action','')])} ")

        if insights:
            rprint(f"\n  [bold]Key Findings:[/bold]")
            for ins in insights:
                rprint(f"    [yellow]💡[/yellow]  {ins}")

        report = mapper_generate_report(target, all_results)
        if report:
            rprint(f"\n[bold]{'═'*60}[/bold]")
            rprint(report)
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            fp = META_DIR / f"autopilot_{re.sub(r'[^\\w]','_',target)}_{ts}.txt"
            fp.write_text(f"FORGE META Autopilot Report\nTarget: {target}\nGoal: {goal}\nDate: {datetime.now()}\n\nInsights:\n" +
                         "\n".join(f"- {i}" for i in insights) + "\n\n" + report)
            rprint(f"\n[green]  📄 Report: {fp}[/green]")

        self.autopilot_log.append({"target":target,"goal":goal,"steps":executed,
                                   "insights":insights,"ts":datetime.now().isoformat()})

    # ── Override run() to add new commands and NL fallback ───────────────────

    def run(self):
        self.banner()

        COMMANDS = {
            "help":      self.cmd_help,
            "?":         self.cmd_help,
            "search":    self.cmd_search,
            "use":       self.cmd_use,
            "set":       self.cmd_set,
            "unset":     lambda a: self.active_mod.set(a[0],"") if self.active_mod and a else None,
            "run":       self.cmd_run,
            "execute":   self.cmd_run,
            "exploit":   self.cmd_run,
            "show":      self.cmd_show,
            "info":      self.cmd_info,
            "back":      lambda a: setattr(self,"active_mod",None) or rprint("[dim]Exited module.[/dim]"),
            "adapt":     self.cmd_adapt,
            "workspace": self.cmd_workspace,
            "notes":     self.cmd_notes,
            "creds":     self.cmd_creds,
            "session":   self.cmd_session,
            "history":   self.cmd_history,
            "clear":     lambda a: os.system("clear"),
            "reload":    lambda a: setattr(self,"modules",load_all_modules()) or
                         rprint(f"[green]Reloaded {len(self.modules)} modules[/green]"),
            # NEW COMMANDS
            "nl":        self.cmd_nl,
            "language":  self.cmd_nl,
            "map":       self.cmd_map,
            "surface":   self.cmd_map,
            "autopilot": self.cmd_autopilot,
            "auto":      self.cmd_autopilot,
            "pilot":     self.cmd_autopilot,
        }

        rprint(f"[dim]💡 New: 'nl' = natural language mode | 'map <target>' = surface mapper | 'autopilot <target>' = full auto[/dim]\n")

        while True:
            try:
                raw = self.prompt()
            except (KeyboardInterrupt, EOFError):
                rprint(f"\n[cyan]⚒️  FORGE META — Stay ethical. 🔥[/cyan]"); break

            if not raw: continue
            parts = raw.split()
            cmd   = parts[0].lower()
            args  = parts[1:]

            if cmd in ("exit","quit","q"):
                rprint("[cyan]⚒️  FORGE META — Stay ethical. 🔥[/cyan]"); break

            self.history.append(raw)

            if self.nl_mode and cmd not in COMMANDS:
                # Everything is NL when mode is on
                self._handle_nl(raw)
            elif cmd in COMMANDS:
                try: COMMANDS[cmd](args)
                except Exception as e: rprint(f"[red]Error: {e}[/red]")
            else:
                # Unknown command — try NL first, then adapt
                if AI_AVAILABLE:
                    rprint(f"[dim]  🗣️  Treating as natural language...[/dim]")
                    self._handle_nl(raw)
                else:
                    rprint(f"[yellow]  Unknown: '{cmd}'. Type 'help'.[/yellow]")

# ══════════════════════════════════════════════════════════════════════════════
# Override main to use v2
# ══════════════════════════════════════════════════════════════════════════════

def main():
    meta = ForgeMetaV2()
    meta.run()

