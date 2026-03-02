#!/usr/bin/env python3
"""
⚒️  FORGE — Ethical Hacker Toolkit
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A collection of legit security & pentesting tools for:
  • Learning networking & security concepts
  • CTF challenges
  • Testing YOUR OWN systems
  • Security research

Tools included:
  1. 🔍 Port Scanner          — TCP connect scan with banner grabbing
  2. 🌐 HTTP Header Inspector  — Analyze security headers
  3. 🔑 Password Analyzer      — Strength check + breach check
  4. 🔐 Hash Cracker           — MD5/SHA wordlist attack
  5. 📡 Ping Sweeper           — Discover live hosts on a subnet
  6. 🕵️  Subdomain Finder      — Enumerate subdomains
  7. 🧩 Caesar/ROT13 Cipher    — Encode/decode classic ciphers
  8. 📦 Steganography          — Hide/reveal messages in text
  9. 🛡️  SQL Injection Tester   — Check YOUR site for SQLi hints
  10. 🔓 Password Generator     — Cryptographically secure passwords

Usage: python forge_hacker_toolkit.py
"""

import socket, threading, hashlib, secrets, string, time, re, sys
import subprocess, json, base64
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.parse import urlparse, urljoin
from urllib.error import URLError, HTTPError
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Colors ────────────────────────────────────────────────────────────────────
R="\033[91m"; G="\033[92m"; Y="\033[93m"; B="\033[94m"
M="\033[95m"; C="\033[96m"; W="\033[97m"; DIM="\033[2m"; RESET="\033[0m"; BOLD="\033[1m"

def banner():
    print(f"""
{C}{BOLD}
  ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
  ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
  █████╗  ██║   ██║██████╔╝██║  ███╗█████╗
  ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝
  ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
  ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
{RESET}{Y}  ⚔️   Ethical Hacker Toolkit  —  For learning & CTFs only{RESET}
{DIM}  Only use on systems you own or have permission to test.{RESET}
""")

def menu():
    print(f"\n{BOLD}{C}  ╔══ TOOLS ═══════════════════════════════╗{RESET}")
    tools = [
        ("1", "🔍 Port Scanner",         "TCP scan with banner grabbing"),
        ("2", "🌐 HTTP Header Inspector", "Security header analysis"),
        ("3", "🔑 Password Analyzer",     "Strength + breach database check"),
        ("4", "🔐 Hash Cracker",          "MD5/SHA1/SHA256 wordlist attack"),
        ("5", "📡 Ping Sweeper",          "Find live hosts on subnet"),
        ("6", "🕵️  Subdomain Finder",     "Enumerate subdomains"),
        ("7", "🧩 Cipher Tool",           "Caesar, ROT13, Base64"),
        ("8", "📦 Steganography",         "Hide/reveal text messages"),
        ("9", "🛡️  SQLi Tester",          "SQL injection hint checker"),
        ("0", "🔓 Password Generator",    "Cryptographically secure"),
        ("q", "Exit", ""),
    ]
    for num, name, desc in tools:
        if num == "q":
            print(f"{C}  ╠══════════════════════════════════════════╣{RESET}")
            print(f"{C}  ║  {Y}q{RESET}  Exit{' '*38}{C}║{RESET}")
        else:
            print(f"{C}  ║  {Y}{num}{RESET}  {name:<24} {DIM}{desc:<16}{RESET}{C}║{RESET}")
    print(f"{C}  ╚══════════════════════════════════════════╝{RESET}")
    return input(f"\n{BOLD}FORGE > {RESET}").strip().lower()

# ══════════════════════════════════════════════════════════════════════════════
# 1. 🔍 PORT SCANNER
# ══════════════════════════════════════════════════════════════════════════════

def grab_banner(host, port, timeout=1.5):
    """Try to grab service banner."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(timeout)
            try:
                s.send(b"HEAD / HTTP/1.0\r\n\r\n")
                banner = s.recv(256).decode("utf-8", errors="ignore").strip()
                return banner[:80] if banner else ""
            except:
                return ""
    except:
        return ""

COMMON_SERVICES = {
    21:"FTP", 22:"SSH", 23:"Telnet", 25:"SMTP", 53:"DNS",
    80:"HTTP", 110:"POP3", 143:"IMAP", 443:"HTTPS", 445:"SMB",
    3306:"MySQL", 3389:"RDP", 5432:"PostgreSQL", 6379:"Redis",
    8080:"HTTP-Alt", 8443:"HTTPS-Alt", 27017:"MongoDB",
}

def scan_port(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except:
        return False

def tool_port_scanner():
    print(f"\n{BOLD}{C}🔍  PORT SCANNER{RESET}")
    print(f"{DIM}Performs TCP connect scan. Only scan hosts you own/have permission to test.{RESET}\n")

    host = input(f"  Target host/IP {DIM}(e.g. 127.0.0.1 or localhost){RESET}: ").strip()
    if not host: host = "127.0.0.1"

    port_input = input(f"  Ports {DIM}(e.g. 1-1024, 80,443,22, or 'common'){RESET}: ").strip()

    # Parse ports
    ports = []
    if port_input == "common" or port_input == "":
        ports = list(COMMON_SERVICES.keys())
    elif "-" in port_input:
        try:
            start, end = port_input.split("-")
            ports = list(range(int(start), int(end)+1))
        except:
            print(f"{R}  Invalid range.{RESET}"); return
    elif "," in port_input:
        try:
            ports = [int(p.strip()) for p in port_input.split(",")]
        except:
            print(f"{R}  Invalid port list.{RESET}"); return
    else:
        try:
            ports = list(range(1, int(port_input)+1))
        except:
            ports = list(COMMON_SERVICES.keys())

    threads = int(input(f"  Threads {DIM}[50]{RESET}: ").strip() or "50")
    grab    = input(f"  Grab banners? {DIM}(y/n) [n]{RESET}: ").strip().lower() == "y"

    # Resolve host
    try:
        ip = socket.gethostbyname(host)
        print(f"\n  {G}Target:{RESET} {host} ({ip})")
        print(f"  {G}Ports:{RESET}  {len(ports)} to scan")
        print(f"  {G}Start:{RESET}  {datetime.now().strftime('%H:%M:%S')}\n")
    except socket.gaierror:
        print(f"{R}  Could not resolve host: {host}{RESET}"); return

    open_ports = []
    start_time = time.time()
    scanned    = [0]
    lock       = threading.Lock()

    def scan_worker(port):
        if scan_port(ip, port):
            svc     = COMMON_SERVICES.get(port, "unknown")
            banner  = grab_banner(ip, port) if grab else ""
            with lock:
                open_ports.append((port, svc, banner))
                print(f"  {G}OPEN{RESET}  {BOLD}{port:>5}{RESET}/tcp  {Y}{svc:<12}{RESET}  {DIM}{banner[:60]}{RESET}")
        with lock:
            scanned[0] += 1

    print(f"  {'PORT':<8} {'STATE':<8} {'SERVICE':<14} {'BANNER'}")
    print(f"  {'─'*60}")

    with ThreadPoolExecutor(max_workers=threads) as ex:
        futures = {ex.submit(scan_worker, p): p for p in ports}
        for _ in as_completed(futures):
            pass

    elapsed = round(time.time() - start_time, 2)
    print(f"\n  {'─'*60}")
    print(f"  {G}{len(open_ports)} open port(s){RESET} found in {elapsed}s")

    if open_ports:
        print(f"\n  {BOLD}Summary:{RESET}")
        for port, svc, bnr in sorted(open_ports):
            print(f"    {G}●{RESET} {port}/tcp  {svc}")

# ══════════════════════════════════════════════════════════════════════════════
# 2. 🌐 HTTP HEADER INSPECTOR
# ══════════════════════════════════════════════════════════════════════════════

SECURITY_HEADERS = {
    "Strict-Transport-Security": ("HSTS", G, "Enforces HTTPS connections"),
    "Content-Security-Policy":   ("CSP",  G, "Prevents XSS attacks"),
    "X-Frame-Options":           ("XFO",  G, "Prevents clickjacking"),
    "X-Content-Type-Options":    ("XCTO", G, "Prevents MIME sniffing"),
    "Referrer-Policy":           ("RP",   G, "Controls referrer info"),
    "Permissions-Policy":        ("PP",   G, "Controls browser features"),
    "X-XSS-Protection":          ("XSS",  Y, "Legacy XSS filter (deprecated)"),
    "Server":                    ("SRV",  R, "⚠️  Reveals server software"),
    "X-Powered-By":              ("XPB",  R, "⚠️  Reveals tech stack"),
    "X-AspNet-Version":          ("ASP",  R, "⚠️  Reveals .NET version"),
}

def tool_http_inspector():
    print(f"\n{BOLD}{C}🌐  HTTP HEADER INSPECTOR{RESET}")
    print(f"{DIM}Analyzes HTTP security headers for hardening issues.{RESET}\n")

    url = input(f"  URL {DIM}(e.g. https://example.com){RESET}: ").strip()
    if not url: url = "https://example.com"
    if not url.startswith("http"): url = "https://" + url

    try:
        req  = Request(url, headers={"User-Agent": "FORGE-Security-Scanner/1.0"})
        resp = urlopen(req, timeout=10)
        headers = dict(resp.headers)
        status  = resp.status
        print(f"\n  {G}Connected!{RESET} Status: {BOLD}{status}{RESET}  URL: {url}\n")
    except HTTPError as e:
        headers = dict(e.headers)
        status  = e.code
        print(f"\n  {Y}HTTP {status}{RESET}  URL: {url}\n")
    except Exception as e:
        print(f"  {R}Error: {e}{RESET}"); return

    print(f"  {'HEADER':<35} {'VALUE':<45} STATUS")
    print(f"  {'─'*90}")

    found = set()
    for raw_header, val in sorted(headers.items()):
        for sec_header, (abbr, color, desc) in SECURITY_HEADERS.items():
            if raw_header.lower() == sec_header.lower():
                found.add(sec_header)
                indicator = "✅" if color == G else ("⚠️" if color == Y else "🔴")
                print(f"  {color}{raw_header:<35}{RESET} {str(val)[:44]:<45} {indicator}")
                if color == R:
                    print(f"  {DIM}  └─ Risk: {desc}{RESET}")

    # Missing security headers
    missing = [h for h in SECURITY_HEADERS if h not in found
               and SECURITY_HEADERS[h][1] == G]
    if missing:
        print(f"\n  {R}Missing security headers:{RESET}")
        for h in missing:
            _, _, desc = SECURITY_HEADERS[h]
            print(f"    {R}✗{RESET}  {h:<35} {DIM}{desc}{RESET}")

    # Security score
    present = len([h for h in found if SECURITY_HEADERS[h][1] == G])
    total   = len([h for h,v in SECURITY_HEADERS.items() if v[1] == G])
    score   = round(present / total * 100)
    color   = G if score >= 70 else (Y if score >= 40 else R)
    print(f"\n  Security Score: {color}{BOLD}{score}%{RESET}  ({present}/{total} headers present)")

    # All headers
    if input(f"\n  Show all headers? {DIM}(y/n){RESET}: ").lower() == "y":
        print(f"\n  {BOLD}All response headers:{RESET}")
        for k, v in sorted(headers.items()):
            print(f"    {DIM}{k:<35}{RESET} {str(v)[:60]}")

# ══════════════════════════════════════════════════════════════════════════════
# 3. 🔑 PASSWORD ANALYZER
# ══════════════════════════════════════════════════════════════════════════════

def check_pwned(password):
    """Check HaveIBeenPwned API (k-anonymity — only sends first 5 chars of hash)."""
    try:
        sha1 = hashlib.sha1(password.encode()).hexdigest().upper()
        prefix, suffix = sha1[:5], sha1[5:]
        req  = Request(f"https://api.pwnedpasswords.com/range/{prefix}",
                       headers={"User-Agent":"FORGE-Security-Scanner"})
        resp = urlopen(req, timeout=5).read().decode()
        for line in resp.splitlines():
            h, count = line.split(":")
            if h == suffix:
                return int(count)
        return 0
    except:
        return -1  # Could not check

def analyze_password_strength(pw):
    score  = 0
    issues = []
    tips   = []

    checks = [
        (len(pw) >= 8,   10, "Length ≥ 8",        "Use at least 8 characters"),
        (len(pw) >= 12,  15, "Length ≥ 12",       "Use at least 12 characters"),
        (len(pw) >= 16,  15, "Length ≥ 16",       "Longer is always better"),
        (bool(re.search(r"[A-Z]", pw)), 10, "Uppercase", "Add uppercase letters"),
        (bool(re.search(r"[a-z]", pw)), 10, "Lowercase", "Add lowercase letters"),
        (bool(re.search(r"\d",    pw)), 10, "Numbers",   "Add numbers"),
        (bool(re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]", pw)), 15,
         "Special chars", "Add special characters (!@#$...)"),
        (not bool(re.search(r"(.)\1{2,}", pw)), 5, "No repeats", "Avoid repeated characters"),
        (not any(word in pw.lower() for word in ["password","pass","123","abc","qwerty","admin","letmein"]),
         10, "No common words", "Avoid common words"),
    ]

    for passed, points, label, tip in checks:
        if passed:
            score += points
            issues.append((G, "✓", label))
        else:
            issues.append((R, "✗", label))
            tips.append(tip)

    return min(score, 100), issues, tips

def tool_password_analyzer():
    print(f"\n{BOLD}{C}🔑  PASSWORD ANALYZER{RESET}")
    print(f"{DIM}Checks strength and breach status using k-anonymity (safe to use).{RESET}\n")

    import getpass
    try:
        pw = getpass.getpass(f"  Enter password {DIM}(hidden){RESET}: ")
    except:
        pw = input(f"  Enter password: ")

    if not pw:
        print(f"  {R}No password entered.{RESET}"); return

    score, issues, tips = analyze_password_strength(pw)
    color = G if score >= 75 else (Y if score >= 45 else R)
    label = "STRONG" if score >= 75 else ("MEDIUM" if score >= 45 else "WEAK")

    print(f"\n  {BOLD}Strength Analysis:{RESET}")
    for clr, sym, desc in issues:
        print(f"    {clr}{sym}{RESET}  {desc}")

    bar_len = 30
    filled  = int(score/100 * bar_len)
    bar     = "█" * filled + "░" * (bar_len - filled)
    print(f"\n  Score: {color}{BOLD}{score}/100  {label}{RESET}")
    print(f"  [{color}{bar}{RESET}]")

    if tips:
        print(f"\n  {Y}Tips to improve:{RESET}")
        for tip in tips: print(f"    → {tip}")

    # Entropy
    charset = 0
    if re.search(r"[a-z]", pw): charset += 26
    if re.search(r"[A-Z]", pw): charset += 26
    if re.search(r"\d",    pw): charset += 10
    if re.search(r"[^a-zA-Z0-9]", pw): charset += 32
    entropy = len(pw) * (charset.bit_length() if charset else 0)
    print(f"\n  Entropy: ~{entropy} bits  {DIM}(>60 = good, >100 = excellent){RESET}")

    # Breach check
    print(f"\n  {Y}Checking breach database...{RESET}", end="", flush=True)
    count = check_pwned(pw)
    if count == -1:
        print(f"\r  {Y}⚠️  Could not reach breach database (offline?){RESET}")
    elif count == 0:
        print(f"\r  {G}✅  Not found in any known breach database{RESET}         ")
    else:
        print(f"\r  {R}🔴  PWNED! Found {count:,} times in breach databases!{RESET}    ")
        print(f"  {R}    → Change this password immediately!{RESET}")

# ══════════════════════════════════════════════════════════════════════════════
# 4. 🔐 HASH CRACKER
# ══════════════════════════════════════════════════════════════════════════════

def detect_hash_type(h):
    h = h.strip()
    if   len(h) == 32:  return ["md5"]
    elif len(h) == 40:  return ["sha1"]
    elif len(h) == 56:  return ["sha224"]
    elif len(h) == 64:  return ["sha256"]
    elif len(h) == 96:  return ["sha384"]
    elif len(h) == 128: return ["sha512"]
    return ["md5","sha1","sha256"]

def crack_hash(target_hash, wordlist_path=None, hash_types=None):
    target = target_hash.strip().lower()
    types  = hash_types or detect_hash_type(target)

    # Built-in mini wordlist if no file provided
    builtin = [
        "password","123456","password123","admin","letmein","welcome",
        "monkey","dragon","master","sunshine","princess","football",
        "shadow","superman","michael","jessica","abc123","qwerty",
        "iloveyou","trustno1","login","passw0rd","batman","123456789",
        "1234567","12345678","11111111","test","guest","root","toor",
        "pass","hello","secret","changeme","default","hunter2","1q2w3e",
    ]

    words = builtin
    if wordlist_path:
        try:
            with open(wordlist_path, "r", encoding="utf-8", errors="ignore") as f:
                words = [l.strip() for l in f if l.strip()]
            print(f"  {G}Loaded {len(words):,} words from {wordlist_path}{RESET}")
        except:
            print(f"  {Y}Could not load wordlist, using built-in ({len(builtin)} words){RESET}")

    print(f"  Types: {', '.join(types)}  |  Words: {len(words):,}")
    print(f"\n  {'─'*50}")

    found = None
    tried = 0
    start = time.time()

    for word in words:
        tried += 1
        for variants in [word, word.capitalize(), word.upper(),
                         word+"1", word+"123", word+"!"]:
            for ht in types:
                h = hashlib.new(ht, variants.encode()).hexdigest()
                if h == target:
                    found = (variants, ht)
                    break
            if found: break
        if found: break
        if tried % 500 == 0:
            elapsed = time.time() - start
            rate = tried / elapsed if elapsed > 0 else 0
            print(f"  {DIM}Tried {tried:,} | {rate:.0f}/s{RESET}", end="\r")

    elapsed = round(time.time() - start, 3)
    print(f"  Tried {tried:,} words in {elapsed}s                    ")
    print(f"  {'─'*50}")

    if found:
        word, ht = found
        print(f"\n  {G}{BOLD}🔓  CRACKED!{RESET}")
        print(f"  Hash type: {Y}{ht.upper()}{RESET}")
        print(f"  Password:  {G}{BOLD}{word}{RESET}")
    else:
        print(f"\n  {R}Not found in wordlist.{RESET}")
        print(f"  {DIM}Try a larger wordlist like rockyou.txt{RESET}")

def tool_hash_cracker():
    print(f"\n{BOLD}{C}🔐  HASH CRACKER{RESET}")
    print(f"{DIM}Dictionary attack on MD5/SHA1/SHA256/SHA512 hashes.{RESET}\n")

    target = input(f"  Hash to crack: ").strip()
    if not target: return

    types = detect_hash_type(target)
    print(f"  {Y}Detected type(s):{RESET} {', '.join(t.upper() for t in types)}")

    wordlist = input(f"  Wordlist path {DIM}(Enter for built-in){RESET}: ").strip() or None
    crack_hash(target, wordlist, types)

    # Also offer to hash something
    if input(f"\n  Hash a word? {DIM}(y/n){RESET}: ").lower() == "y":
        word = input(f"  Word to hash: ").strip()
        if word:
            print(f"\n  {BOLD}Hashes of '{word}':{RESET}")
            for algo in ["md5","sha1","sha256","sha512"]:
                h = hashlib.new(algo, word.encode()).hexdigest()
                print(f"    {Y}{algo.upper():<8}{RESET} {h}")

# ══════════════════════════════════════════════════════════════════════════════
# 5. 📡 PING SWEEPER
# ══════════════════════════════════════════════════════════════════════════════

def ping_host(ip):
    try:
        flag = "-n" if sys.platform == "win32" else "-c"
        result = subprocess.run(
            ["ping", flag, "1", "-W", "1", str(ip)],
            capture_output=True, text=True, timeout=3
        )
        return result.returncode == 0
    except:
        return False

def tcp_check(ip, port=80, timeout=0.5):
    try:
        with socket.create_connection((str(ip), port), timeout=timeout):
            return True
    except:
        return False

def tool_ping_sweeper():
    print(f"\n{BOLD}{C}📡  PING SWEEPER{RESET}")
    print(f"{DIM}Discovers live hosts on a subnet. Only scan networks you own/manage.{RESET}\n")

    subnet = input(f"  Subnet {DIM}(e.g. 192.168.1 for 192.168.1.0/24){RESET}: ").strip()
    if not subnet:
        subnet = "127.0.0"

    method = input(f"  Method {DIM}[ping/tcp]{RESET}: ").strip().lower() or "tcp"
    threads = int(input(f"  Threads {DIM}[50]{RESET}: ").strip() or "50")

    print(f"\n  {G}Sweeping {subnet}.0/24...{RESET}\n")
    print(f"  {'HOST':<20} {'STATUS':<10} {'HOSTNAME'}")
    print(f"  {'─'*55}")

    live_hosts = []
    start = time.time()
    lock  = threading.Lock()

    def check(i):
        ip = f"{subnet}.{i}"
        if i == 0 or i == 255: return
        alive = False
        if method == "ping":
            alive = ping_host(ip)
        else:
            alive = tcp_check(ip, 80) or tcp_check(ip, 443) or tcp_check(ip, 22)

        if alive:
            try:
                hostname = socket.gethostbyaddr(ip)[0]
            except:
                hostname = "─"
            with lock:
                live_hosts.append(ip)
                print(f"  {G}●{RESET}  {ip:<18} {G}ALIVE{RESET}     {DIM}{hostname}{RESET}")

    with ThreadPoolExecutor(max_workers=threads) as ex:
        list(ex.map(check, range(1, 255)))

    elapsed = round(time.time() - start, 1)
    print(f"\n  {'─'*55}")
    print(f"  {G}{len(live_hosts)} live host(s){RESET} found in {elapsed}s")

# ══════════════════════════════════════════════════════════════════════════════
# 6. 🕵️ SUBDOMAIN FINDER
# ══════════════════════════════════════════════════════════════════════════════

COMMON_SUBDOMAINS = [
    "www","mail","ftp","localhost","webmail","smtp","pop","ns1","ns2",
    "blog","dev","staging","api","app","admin","portal","vpn","remote",
    "beta","test","shop","cdn","static","assets","media","img","images",
    "mobile","m","secure","login","dashboard","support","help","docs",
    "git","gitlab","github","jenkins","jira","confluence","wiki","forum",
    "cpanel","whm","autodiscover","autoconfig","mx","exchange","owa",
    "db","database","mysql","redis","mongo","elasticsearch","kibana",
    "grafana","prometheus","status","monitor","metrics","logs",
]

def tool_subdomain_finder():
    print(f"\n{BOLD}{C}🕵️   SUBDOMAIN FINDER{RESET}")
    print(f"{DIM}DNS brute-force to discover subdomains. Use on domains you own.{RESET}\n")

    domain = input(f"  Domain {DIM}(e.g. example.com){RESET}: ").strip()
    if not domain: return
    domain = domain.replace("http://","").replace("https://","").split("/")[0]

    threads  = int(input(f"  Threads {DIM}[30]{RESET}: ").strip() or "30")
    wordlist = input(f"  Custom wordlist {DIM}(Enter for built-in){RESET}: ").strip()

    words = COMMON_SUBDOMAINS
    if wordlist:
        try:
            with open(wordlist) as f:
                words = [l.strip() for l in f if l.strip()]
            print(f"  {G}Loaded {len(words)} words{RESET}")
        except:
            print(f"  {Y}Using built-in wordlist ({len(words)} words){RESET}")

    print(f"\n  {G}Scanning {domain} with {len(words)} subdomains...{RESET}\n")
    print(f"  {'SUBDOMAIN':<45} {'IP':<18} {'STATUS'}")
    print(f"  {'─'*70}")

    found = []
    lock  = threading.Lock()

    def check_sub(word):
        full = f"{word}.{domain}"
        try:
            ips = socket.getaddrinfo(full, None)
            ip  = ips[0][4][0]
            # Try HTTP
            status = "─"
            try:
                req  = Request(f"http://{full}", headers={"User-Agent":"FORGE"})
                resp = urlopen(req, timeout=3)
                status = str(resp.status)
            except HTTPError as e:
                status = str(e.code)
            except:
                pass
            with lock:
                found.append((full, ip, status))
                color = G if status.startswith("2") else (Y if status.startswith("3") else R)
                print(f"  {G}●{RESET}  {full:<43} {ip:<18} {color}{status}{RESET}")
        except:
            pass

    with ThreadPoolExecutor(max_workers=threads) as ex:
        list(ex.map(check_sub, words))

    print(f"\n  {'─'*70}")
    print(f"  {G}{len(found)} subdomain(s){RESET} discovered")
    if found:
        print(f"\n  {BOLD}Found:{RESET}")
        for sub, ip, status in sorted(found):
            print(f"    {G}→{RESET}  {sub}  {DIM}({ip}){RESET}")

# ══════════════════════════════════════════════════════════════════════════════
# 7. 🧩 CIPHER TOOL
# ══════════════════════════════════════════════════════════════════════════════

def caesar_cipher(text, shift, decode=False):
    if decode: shift = -shift
    result = ""
    for ch in text:
        if ch.isalpha():
            base = ord("A") if ch.isupper() else ord("a")
            result += chr((ord(ch) - base + shift) % 26 + base)
        else:
            result += ch
    return result

def vigenere(text, key, decode=False):
    key    = key.upper()
    result = ""
    ki     = 0
    for ch in text:
        if ch.isalpha():
            shift = ord(key[ki % len(key)]) - ord("A")
            if decode: shift = -shift
            base  = ord("A") if ch.isupper() else ord("a")
            result += chr((ord(ch) - base + shift) % 26 + base)
            ki += 1
        else:
            result += ch
    return result

def tool_cipher():
    print(f"\n{BOLD}{C}🧩  CIPHER TOOL{RESET}")
    print(f"{DIM}Classic ciphers for CTF challenges.{RESET}\n")

    ciphers = [
        ("1", "Caesar cipher"),
        ("2", "ROT13"),
        ("3", "Vigenère cipher"),
        ("4", "Base64 encode/decode"),
        ("5", "XOR cipher"),
        ("6", "Brute-force Caesar"),
    ]
    for n, name in ciphers:
        print(f"  {Y}{n}{RESET}  {name}")

    choice = input(f"\n  Choice: ").strip()
    text   = input(f"  Text:   ").strip()

    if choice == "1":
        shift  = int(input(f"  Shift amount: ").strip() or "3")
        action = input(f"  Encode/Decode {DIM}[e/d]{RESET}: ").strip().lower()
        result = caesar_cipher(text, shift, action == "d")
        print(f"\n  {G}Result: {BOLD}{result}{RESET}")

    elif choice == "2":
        result = caesar_cipher(text, 13)
        print(f"\n  {G}ROT13: {BOLD}{result}{RESET}")

    elif choice == "3":
        key    = input(f"  Key word: ").strip() or "KEY"
        action = input(f"  Encode/Decode {DIM}[e/d]{RESET}: ").strip().lower()
        result = vigenere(text, key, action == "d")
        print(f"\n  {G}Result: {BOLD}{result}{RESET}")

    elif choice == "4":
        action = input(f"  Encode/Decode {DIM}[e/d]{RESET}: ").strip().lower()
        if action == "d":
            try:
                result = base64.b64decode(text.encode()).decode("utf-8","ignore")
            except:
                result = "Invalid Base64"
        else:
            result = base64.b64encode(text.encode()).decode()
        print(f"\n  {G}Result: {BOLD}{result}{RESET}")

    elif choice == "5":
        key    = int(input(f"  XOR key (0-255): ").strip() or "42")
        result = "".join(chr(ord(c) ^ key) for c in text)
        hex_r  = " ".join(f"{ord(c):02x}" for c in result)
        print(f"\n  {G}Result (text): {BOLD}{result}{RESET}")
        print(f"  {G}Result (hex):  {BOLD}{hex_r}{RESET}")

    elif choice == "6":
        print(f"\n  {BOLD}Brute-forcing all 25 Caesar shifts:{RESET}\n")
        for shift in range(1, 26):
            decoded = caesar_cipher(text, shift, decode=True)
            print(f"  {Y}Shift {shift:>2}{RESET}:  {decoded}")

# ══════════════════════════════════════════════════════════════════════════════
# 8. 📦 STEGANOGRAPHY (Text)
# ══════════════════════════════════════════════════════════════════════════════

def text_steg_hide(message, cover_text):
    """Hide message in cover text using zero-width characters."""
    # Zero-width space = 0, zero-width non-joiner = 1
    ZWS  = "\u200b"  # bit 0
    ZWNJ = "\u200c"  # bit 1
    SEP  = "\u200d"  # separator

    binary = "".join(f"{ord(c):08b}" for c in message) + "00000000"  # null terminator
    hidden = SEP.join(ZWS if b=="0" else ZWNJ for b in binary)
    return cover_text + "\n" + hidden

def text_steg_reveal(steg_text):
    """Extract hidden message from steganographic text."""
    ZWS  = "\u200b"
    ZWNJ = "\u200c"
    SEP  = "\u200d"

    # Find hidden section
    if SEP not in steg_text:
        return None
    parts  = steg_text.split("\n")
    hidden = ""
    for part in parts:
        if ZWS in part or ZWNJ in part:
            hidden = part; break
    if not hidden: return None

    bits   = "".join("0" if c == ZWS else "1" for c in hidden if c in (ZWS, ZWNJ))
    result = ""
    for i in range(0, len(bits)-7, 8):
        byte = bits[i:i+8]
        if len(byte) < 8: break
        val  = int(byte, 2)
        if val == 0: break
        result += chr(val)
    return result if result else None

def tool_steganography():
    print(f"\n{BOLD}{C}📦  TEXT STEGANOGRAPHY{RESET}")
    print(f"{DIM}Hide secret messages in plain text using zero-width Unicode chars.{RESET}\n")
    print(f"  {Y}1{RESET}  Hide a message")
    print(f"  {Y}2{RESET}  Reveal a message")

    choice = input(f"\n  Choice: ").strip()

    if choice == "1":
        print(f"  {DIM}Enter cover text (the innocent-looking text):{RESET}")
        cover = input(f"  Cover text: ").strip() or "Nothing to see here!"
        secret = input(f"  Secret message: ").strip()
        if not secret: return

        result = text_steg_hide(secret, cover)
        print(f"\n  {G}Steganographic text created!{RESET}")
        print(f"  {DIM}(Contains hidden zero-width characters){RESET}")
        print(f"\n  ┌─ Output ───────────────────────────────────")
        print(f"  │ {result.split(chr(10))[0]}")
        print(f"  │ {DIM}[+ hidden layer: {len(secret)} chars]{RESET}")
        print(f"  └────────────────────────────────────────────")
        print(f"\n  {DIM}Copy the full output including hidden chars:{RESET}")
        print(result)

    elif choice == "2":
        print(f"  {DIM}Paste the steganographic text (including hidden chars):{RESET}")
        lines = []
        print(f"  {DIM}(Enter blank line to finish){RESET}")
        while True:
            line = input()
            if not line: break
            lines.append(line)
        text = "\n".join(lines)

        secret = text_steg_reveal(text)
        if secret:
            print(f"\n  {G}{BOLD}🔍  Hidden message found!{RESET}")
            print(f"  Message: {G}{BOLD}{secret}{RESET}")
        else:
            print(f"\n  {Y}No hidden message detected.{RESET}")
            print(f"  {DIM}(Text may not contain zero-width chars){RESET}")

# ══════════════════════════════════════════════════════════════════════════════
# 9. 🛡️ SQL INJECTION TESTER
# ══════════════════════════════════════════════════════════════════════════════

SQLi_PAYLOADS = [
    ("'",                    "Single quote"),
    ("''",                   "Double single quote"),
    ("1 OR 1=1",             "Classic OR injection"),
    ("1' OR '1'='1",         "String OR injection"),
    ("1; DROP TABLE users",  "Statement terminator"),
    ("1 UNION SELECT NULL",  "UNION injection"),
    ("' AND 1=2 UNION SELECT version()--", "Version extraction"),
    ("1 AND SLEEP(2)",       "Time-based blind"),
    ("' OR SLEEP(2)--",      "Sleep injection"),
    ("admin'--",             "Comment bypass"),
    ("1/*",                  "Inline comment"),
    ("1' #",                 "Hash comment (MySQL)"),
]

SQLi_ERRORS = [
    "sql", "syntax", "mysql", "oracle", "microsoft", "odbc",
    "jdbc", "sqlite", "postgresql", "warning:", "error in your sql",
    "unclosed quotation", "unterminated string", "you have an error",
    "supplied argument is not a valid mysql", "column count doesn't match",
]

def tool_sqli_tester():
    print(f"\n{BOLD}{C}🛡️   SQL INJECTION HINT TESTER{RESET}")
    print(f"{DIM}Tests YOUR web app for SQLi indicators. Only use on sites you own!{RESET}\n")

    url = input(f"  Target URL with parameter {DIM}(e.g. http://localhost/item?id=1){RESET}: ").strip()
    if not url: return

    parsed = urlparse(url)
    if "=" not in parsed.query:
        print(f"  {R}URL must contain a query parameter (e.g. ?id=1){RESET}"); return

    param  = parsed.query.split("=")[0]
    base   = url.split("?")[0]

    print(f"\n  {G}Testing {url}{RESET}")
    print(f"  {G}Parameter: {param}{RESET}\n")
    print(f"  {'PAYLOAD':<40} {'STATUS':<8} {'INDICATOR'}")
    print(f"  {'─'*70}")

    vulnerable_hints = []

    for payload, desc in SQLi_PAYLOADS:
        test_url = f"{base}?{param}={payload}"
        try:
            req  = Request(test_url, headers={"User-Agent":"FORGE-Security-Scanner"})
            resp = urlopen(req, timeout=5)
            body = resp.read(4096).decode("utf-8","ignore").lower()
            code = resp.status

            # Check for SQL error strings
            found_errors = [e for e in SQLi_ERRORS if e in body]
            if found_errors:
                vulnerable_hints.append((payload, desc, found_errors[0]))
                print(f"  {R}⚠️ {RESET}  {payload:<38} {str(code):<8} {R}SQL error: {found_errors[0]}{RESET}")
            else:
                print(f"  {G}✓{RESET}   {payload:<38} {str(code):<8} {DIM}No obvious indicator{RESET}")
        except HTTPError as e:
            print(f"  {Y}?{RESET}   {payload:<38} {str(e.code):<8} {Y}HTTP error{RESET}")
        except Exception as e:
            print(f"  {R}✗{RESET}   {payload:<38} {'ERR':<8} {DIM}{str(e)[:30]}{RESET}")
        time.sleep(0.1)  # Be polite

    print(f"\n  {'─'*70}")
    if vulnerable_hints:
        print(f"  {R}{BOLD}⚠️   {len(vulnerable_hints)} potential SQLi indicator(s) detected!{RESET}")
        for payload, desc, error in vulnerable_hints:
            print(f"    {R}→{RESET}  {desc}: [{payload}] triggered '{error}'")
        print(f"\n  {Y}Recommendation: Sanitize all user inputs, use parameterized queries!{RESET}")
    else:
        print(f"  {G}✅  No obvious SQL injection indicators found.{RESET}")
        print(f"  {DIM}(This is not a guarantee — manual testing is more thorough){RESET}")

# ══════════════════════════════════════════════════════════════════════════════
# 10. 🔓 PASSWORD GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def generate_password(length=16, use_upper=True, use_lower=True,
                      use_digits=True, use_special=True, exclude=""):
    charset = ""
    if use_lower:   charset += string.ascii_lowercase
    if use_upper:   charset += string.ascii_uppercase
    if use_digits:  charset += string.digits
    if use_special: charset += "!@#$%^&*()-_=+[]{}|;:,.<>?"
    charset = "".join(c for c in charset if c not in exclude)
    if not charset: return ""

    while True:
        pwd = "".join(secrets.choice(charset) for _ in range(length))
        # Ensure at least one of each required type
        checks = [
            (not use_lower   or any(c in string.ascii_lowercase for c in pwd)),
            (not use_upper   or any(c in string.ascii_uppercase for c in pwd)),
            (not use_digits  or any(c in string.digits for c in pwd)),
            (not use_special or any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in pwd)),
        ]
        if all(checks): return pwd

def generate_passphrase(words=4):
    """Generate a memorable passphrase from a built-in word list."""
    word_list = [
        "apple","brave","cloud","dance","eagle","flame","grace","happy",
        "igloo","joker","kite","lemon","mango","night","ocean","piano",
        "queen","river","solar","tiger","ultra","vivid","water","xenon",
        "yacht","zebra","amber","blaze","crisp","drift","ember","frost",
        "globe","haste","iris","jewel","karma","laser","maple","nexus",
        "orbit","pixel","quark","radar","storm","thorn","umbra","vapor",
    ]
    return "-".join(secrets.choice(word_list) for _ in range(words))

def tool_password_generator():
    print(f"\n{BOLD}{C}🔓  PASSWORD GENERATOR{RESET}")
    print(f"{DIM}Cryptographically secure using secrets module.{RESET}\n")

    length  = int(input(f"  Length {DIM}[16]{RESET}: ").strip() or "16")
    count   = int(input(f"  How many to generate {DIM}[10]{RESET}: ").strip() or "10")
    spec    = input(f"  Include special chars? {DIM}(y/n) [y]{RESET}: ").strip().lower() != "n"
    exclude = input(f"  Exclude chars {DIM}(e.g. 0Ol1 for ambiguous chars){RESET}: ").strip()

    print(f"\n  {BOLD}Generated Passwords:{RESET}")
    print(f"  {'─'*50}")

    passwords = []
    for i in range(count):
        pwd = generate_password(length, True, True, True, spec, exclude)
        passwords.append(pwd)
        score, _, _ = analyze_password_strength(pwd)
        color = G if score >= 75 else Y
        bar   = "█" * int(score/10) + "░" * (10 - int(score/10))
        print(f"  {G}{i+1:>2}.{RESET}  {BOLD}{pwd}{RESET}  {color}[{bar}]{RESET} {score}%")

    print(f"\n  {BOLD}Passphrases (more memorable):{RESET}")
    print(f"  {'─'*50}")
    for i in range(3):
        pp = generate_passphrase(4)
        print(f"  {Y}{i+1}.{RESET}  {BOLD}{pp}{RESET}")

    print(f"\n  {DIM}Tip: Use a password manager to store these safely.{RESET}")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

TOOLS = {
    "1": tool_port_scanner,
    "2": tool_http_inspector,
    "3": tool_password_analyzer,
    "4": tool_hash_cracker,
    "5": tool_ping_sweeper,
    "6": tool_subdomain_finder,
    "7": tool_cipher,
    "8": tool_steganography,
    "9": tool_sqli_tester,
    "0": tool_password_generator,
}

def main():
    banner()
    while True:
        choice = menu()
        if choice in ("q", "quit", "exit"):
            print(f"\n  {C}⚒️   FORGE Hacker Toolkit — Stay ethical! 🔥{RESET}\n")
            break
        elif choice in TOOLS:
            try:
                TOOLS[choice]()
            except KeyboardInterrupt:
                print(f"\n  {Y}Interrupted.{RESET}")
            except Exception as e:
                print(f"\n  {R}Error: {e}{RESET}")
            input(f"\n  {DIM}Press Enter to continue...{RESET}")
        else:
            print(f"  {R}Invalid choice.{RESET}")

if __name__ == "__main__":
    main()
