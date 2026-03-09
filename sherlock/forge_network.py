#!/usr/bin/env python3
"""
FORGE NETWORK — Network Intelligence Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Packets don't lie. FORGE reads them like a crime scene.

Modules:
  🔍 Packet Sniffer      → live capture, protocol decode, pcap I/O
  🧠 Traffic Intelligence → Sherlock reads the network
  🗺️  Network Mapper       → hosts, OS, services, topology
  ⚡ Threat Detector      → ARP spoof, port scan, C2, exfil
  🔎 Deep Inspector       → HTTP/DNS/TLS reconstruction
  📊 Traffic Profiler     → per-device baselines + anomalies
  🌐 Geo Traffic Map      → where is your traffic going?
  🌍 Live UI              → real-time network visualization

Usage:
  python forge_network.py                        # interactive
  python forge_network.py --watch eth0           # live monitor
  python forge_network.py --map                  # map network
  python forge_network.py --scan 192.168.1.0/24  # host scan
  python forge_network.py --pcap capture.pcap    # analyze pcap
  python forge_network.py --server               # API + UI :7346

Requirements:
  pip install scapy requests rich
  sudo python forge_network.py  (packet capture needs root/admin)

  On Windows: Install Npcap from npcap.com
  On Linux:   sudo setcap cap_net_raw+eip $(which python3)
"""

import sys, os, re, json, time, socket, struct, threading
import hashlib, sqlite3, subprocess, ipaddress
from pathlib import Path
from datetime import datetime
from collections import defaultdict, deque

# ── Network deps ──────────────────────────────────────────────────────────────
try:
    from scapy.all import (
        sniff, IP, IPv6, TCP, UDP, ICMP, DNS, DNSQR, DNSRR,
        ARP, Ether, Raw, wrpcap, rdpcap, get_if_list,
        conf as scapy_conf
    )
    scapy_conf.verb = 0
    SCAPY = True
except ImportError:
    SCAPY = False

try:
    import requests
    REQUESTS = True
except ImportError:
    REQUESTS = False

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

    def ai_call(prompt, system="", max_tokens=1500):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or NETWORK_SYSTEM,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text

    def ai_json(prompt, system="", max_tokens=600):
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

except ImportError:
    AI_AVAILABLE = False
    def ai_call(p,s="",m=1500): return "Install anthropic."
    def ai_json(p,s="",m=600): return None

# ── Rich ──────────────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.live import Live
    from rich import box as rbox
    RICH    = True
    console = Console()
    rprint  = console.print
except ImportError:
    RICH = False
    def rprint(x,**kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

# ── System prompt ─────────────────────────────────────────────────────────────
NETWORK_SYSTEM = """You are FORGE NETWORK — a network intelligence analyst in the style of Sherlock Holmes.

You read network traffic the way Holmes reads a crime scene:
every packet is a clue, every connection tells a story.

Your analysis format:
OBSERVATION: [what the traffic shows]
  → INFERENCE: [what this means]
    → THREAT: [risk level] [confidence%]
    → ACTION: [recommended response]

You understand:
- Normal vs anomalous traffic patterns
- C2 beacon signatures (regular intervals, small payloads)
- Data exfiltration patterns (large outbound, unusual hours)
- Lateral movement (internal scanning, new connections)
- DNS tunneling (large TXT records, high entropy subdomains)
- ARP/DHCP attacks
- TLS anomalies (self-signed, expired, unusual SNI)

Be specific. Name the threat. Give confidence. Recommend action."""

# ── Paths ─────────────────────────────────────────────────────────────────────
NET_DIR     = Path("forge_network")
PCAP_DIR    = NET_DIR / "pcaps"
REPORTS_DIR = NET_DIR / "reports"
DB_PATH     = NET_DIR / "network.db"

for d in [NET_DIR, PCAP_DIR, REPORTS_DIR]:
    d.mkdir(exist_ok=True)

# ── Database ──────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS devices (
            mac         TEXT PRIMARY KEY,
            ip          TEXT,
            hostname    TEXT,
            os_guess    TEXT,
            vendor      TEXT,
            first_seen  TEXT,
            last_seen   TEXT,
            bytes_sent  INTEGER DEFAULT 0,
            bytes_recv  INTEGER DEFAULT 0,
            known       INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS connections (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            src_ip      TEXT,
            dst_ip      TEXT,
            src_port    INTEGER,
            dst_port    INTEGER,
            protocol    TEXT,
            bytes       INTEGER DEFAULT 0,
            flags       TEXT,
            country     TEXT,
            threat      TEXT
        );
        CREATE TABLE IF NOT EXISTS dns_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            src_ip      TEXT,
            query       TEXT,
            qtype       TEXT,
            response    TEXT,
            suspicious  INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS threats (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            type        TEXT,
            severity    TEXT,
            src_ip      TEXT,
            dst_ip      TEXT,
            description TEXT,
            resolved    INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS http_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            src_ip      TEXT,
            dst_ip      TEXT,
            method      TEXT,
            host        TEXT,
            path        TEXT,
            status      INTEGER,
            content_type TEXT,
            bytes       INTEGER
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 GEO IP LOOKUP
# ══════════════════════════════════════════════════════════════════════════════

_geo_cache = {}

def geoip(ip):
    """Get geolocation for IP address."""
    if ip in _geo_cache: return _geo_cache[ip]
    if is_private(ip):
        return {"country":"Local","city":"LAN","org":""}

    try:
        import urllib.request
        with urllib.request.urlopen(
            f"https://ipapi.co/{ip}/json/",
            timeout=4
        ) as r:
            data = json.loads(r.read())
            result = {
                "country": data.get("country_name","?"),
                "city":    data.get("city",""),
                "org":     data.get("org",""),
                "asn":     data.get("asn",""),
                "lat":     data.get("latitude",0),
                "lon":     data.get("longitude",0),
            }
            _geo_cache[ip] = result
            return result
    except:
        return {"country":"?","city":"","org":"","asn":""}

def is_private(ip):
    """Check if IP is private/local."""
    try:
        return ipaddress.ip_address(ip).is_private
    except: return False

def is_tor_exit(ip):
    """Check if IP is a known Tor exit node."""
    try:
        import urllib.request
        reversed_ip = ".".join(reversed(ip.split(".")))
        query = f"{reversed_ip}.dnsel.torproject.org"
        socket.gethostbyname(query)
        return True
    except: return False

def mac_vendor(mac):
    """Get vendor from MAC OUI."""
    if not mac: return ""
    oui = mac.upper().replace(":","").replace("-","")[:6]
    # Common OUI prefixes
    vendors = {
        "ACDE48":"Apple","000C29":"VMware","001A2B":"Cisco",
        "B827EB":"Raspberry Pi","DC4F22":"Raspberry Pi",
        "001122":"Cisco","00E04C":"Realtek","7C2EBD":"TP-Link",
        "F8D111":"Amazon","B44BD6":"Amazon Echo",
    }
    for prefix, vendor in vendors.items():
        if oui.startswith(prefix): return vendor
    return ""

# ══════════════════════════════════════════════════════════════════════════════
# 📊 TRAFFIC STATE — shared state between all modules
# ══════════════════════════════════════════════════════════════════════════════

class TrafficState:
    """Shared real-time network state."""

    def __init__(self):
        self.lock          = threading.Lock()
        self.devices       = {}       # mac → device info
        self.connections   = deque(maxlen=500)
        self.dns_queries   = deque(maxlen=200)
        self.http_requests = deque(maxlen=200)
        self.threats       = deque(maxlen=100)
        self.bytes_total   = 0
        self.packets_total = 0
        self.start_time    = time.time()

        # Profiling — per IP
        self.ip_bytes_out  = defaultdict(int)
        self.ip_bytes_in   = defaultdict(int)
        self.ip_conns      = defaultdict(set)
        self.ip_ports      = defaultdict(set)
        self.ip_dns        = defaultdict(list)

        # Beacon detection — per (src,dst) pair
        self.beacon_times  = defaultdict(list)

        # Baselines (filled after observation period)
        self.baselines     = {}

    def add_packet(self, pkt_info):
        with self.lock:
            self.packets_total += 1
            self.bytes_total   += pkt_info.get("bytes",0)

            src = pkt_info.get("src_ip","")
            dst = pkt_info.get("dst_ip","")

            if src:
                self.ip_bytes_out[src] += pkt_info.get("bytes",0)
                if dst: self.ip_conns[src].add(dst)
            if pkt_info.get("dst_port"):
                self.ip_ports[src].add(pkt_info["dst_port"])

            self.connections.append(pkt_info)

    def add_threat(self, threat_type, severity, src, dst, description):
        threat = {
            "ts":          datetime.now().isoformat(),
            "type":        threat_type,
            "severity":    severity,
            "src_ip":      src,
            "dst_ip":      dst,
            "description": description,
        }
        with self.lock:
            self.threats.append(threat)

        color = {"critical":"red bold","high":"red","medium":"yellow","low":"dim"}.get(severity,"yellow")
        rprint(f"  [{color}]⚠  THREAT [{severity.upper()}]: {threat_type}[/{color}]")
        rprint(f"     {src} → {dst}: {description[:80]}")

        # Persist
        conn = get_db()
        conn.execute(
            "INSERT INTO threats (ts,type,severity,src_ip,dst_ip,description) VALUES (?,?,?,?,?,?)",
            (threat["ts"],threat_type,severity,src,dst,description[:500])
        )
        conn.commit(); conn.close()
        return threat

    def top_talkers(self, n=10):
        with self.lock:
            return sorted(
                [(ip, b) for ip,b in self.ip_bytes_out.items()],
                key=lambda x:-x[1]
            )[:n]

    def uptime(self):
        secs = int(time.time() - self.start_time)
        return f"{secs//3600}h {(secs%3600)//60}m {secs%60}s"

# Global state
STATE = TrafficState()

# ══════════════════════════════════════════════════════════════════════════════
# 🔍 PACKET SNIFFER
# ══════════════════════════════════════════════════════════════════════════════

class PacketSniffer:
    """Capture and decode live network traffic."""

    def __init__(self, iface=None, state=None):
        self.iface    = iface or self._default_iface()
        self.state    = state or STATE
        self._running = False
        self.captured = []
        self.pcap_out = None

    def _default_iface(self):
        """Get default network interface."""
        if PSUTIL:
            stats = psutil.net_if_stats()
            for name, stat in stats.items():
                if stat.isup and name not in ("lo","localhost"):
                    return name
        if SCAPY:
            ifaces = get_if_list()
            for iface in ifaces:
                if iface not in ("lo","localhost"):
                    return iface
        return None

    def start(self, iface=None, pcap_out=None, bpf_filter=""):
        """Start packet capture."""
        if not SCAPY:
            rprint("[yellow]Scapy not available. Install: pip install scapy[/yellow]")
            rprint("[dim]Falling back to connection-level monitoring...[/dim]")
            return self.start_connection_monitor()

        self.iface   = iface or self.iface
        self.pcap_out= pcap_out
        self._running= True

        rprint(f"  [green]🔍 Capturing on: {self.iface}[/green]")
        if bpf_filter:
            rprint(f"  [dim]Filter: {bpf_filter}[/dim]")

        threading.Thread(
            target=self._capture_loop,
            args=(bpf_filter,),
            daemon=True
        ).start()
        return True

    def _capture_loop(self, bpf_filter=""):
        """Main capture loop."""
        try:
            sniff(
                iface  = self.iface,
                filter = bpf_filter or None,
                prn    = self._process_packet,
                store  = False,
                stop_filter = lambda p: not self._running,
            )
        except Exception as e:
            if "permission" in str(e).lower() or "operation not permitted" in str(e).lower():
                rprint(f"[red]Permission denied. Run with sudo/admin.[/red]")
            else:
                rprint(f"[red]Capture error: {e}[/red]")

    def _process_packet(self, pkt):
        """Decode and process a captured packet."""
        info = {
            "ts":       datetime.now().isoformat(),
            "bytes":    len(pkt),
            "protocol": "UNKNOWN",
        }

        # Ethernet layer
        if pkt.haslayer(Ether):
            info["src_mac"] = pkt[Ether].src
            info["dst_mac"] = pkt[Ether].dst

        # IP layer
        if pkt.haslayer(IP):
            info["src_ip"]   = pkt[IP].src
            info["dst_ip"]   = pkt[IP].dst
            info["ttl"]      = pkt[IP].ttl
            info["protocol"] = "IP"

        elif pkt.haslayer(IPv6):
            info["src_ip"]   = str(pkt[IPv6].src)
            info["dst_ip"]   = str(pkt[IPv6].dst)
            info["protocol"] = "IPv6"

        # TCP
        if pkt.haslayer(TCP):
            info["protocol"]  = "TCP"
            info["src_port"]  = pkt[TCP].sport
            info["dst_port"]  = pkt[TCP].dport
            info["tcp_flags"] = str(pkt[TCP].flags)

        # UDP
        elif pkt.haslayer(UDP):
            info["protocol"] = "UDP"
            info["src_port"] = pkt[UDP].sport
            info["dst_port"] = pkt[UDP].dport

        # ICMP
        elif pkt.haslayer(ICMP):
            info["protocol"] = "ICMP"
            info["icmp_type"]= pkt[ICMP].type

        # ARP
        if pkt.haslayer(ARP):
            info["protocol"] = "ARP"
            info["arp_op"]   = pkt[ARP].op
            info["arp_src"]  = pkt[ARP].psrc
            info["arp_dst"]  = pkt[ARP].pdst

        # DNS
        if pkt.haslayer(DNS):
            info["protocol"] = "DNS"
            if pkt.haslayer(DNSQR):
                try:
                    query = pkt[DNSQR].qname.decode("utf-8","replace").rstrip(".")
                    info["dns_query"] = query
                    qtype = pkt[DNSQR].qtype
                    info["dns_type"]  = {1:"A",28:"AAAA",15:"MX",16:"TXT",2:"NS"}.get(qtype,str(qtype))
                    # Log DNS
                    self._log_dns(info)
                except: pass

        # HTTP (port 80)
        if pkt.haslayer(Raw) and info.get("dst_port") in (80,8080,8000):
            payload = pkt[Raw].load
            try:
                text = payload.decode("utf-8","replace")
                if text.startswith(("GET ","POST ","PUT ","DELETE ","HEAD ")):
                    info["http"] = self._parse_http_request(text)
                    info["protocol"] = "HTTP"
            except: pass

        # Save raw if needed
        if self.pcap_out:
            self.captured.append(pkt)
            if len(self.captured) % 1000 == 0:
                wrpcap(str(self.pcap_out), self.captured)

        # Pass to state
        self.state.add_packet(info)

        # Pass to threat detector
        ThreatDetector(self.state).check_packet(info)

    def _log_dns(self, info):
        """Log DNS query."""
        query = info.get("dns_query","")
        if not query: return

        suspicious = self._is_suspicious_dns(query)
        entry = {
            "ts":         info["ts"],
            "src_ip":     info.get("src_ip",""),
            "query":      query,
            "qtype":      info.get("dns_type","A"),
            "suspicious": int(suspicious),
        }
        self.state.dns_queries.append(entry)
        if suspicious:
            self.state.add_threat(
                "DNS_ANOMALY", "medium",
                info.get("src_ip","?"), "DNS",
                f"Suspicious DNS query: {query}"
            )

    def _is_suspicious_dns(self, query):
        """Flag suspicious DNS patterns."""
        # Very long subdomain (DNS tunnel)
        parts = query.split(".")
        if any(len(p) > 40 for p in parts): return True
        if len(query) > 100: return True
        # High entropy (base64/hex in subdomain)
        if parts:
            sub = parts[0]
            if len(sub) > 20:
                import math
                freq = defaultdict(int)
                for c in sub: freq[c] += 1
                entropy = -sum((f/len(sub))*math.log2(f/len(sub)) for f in freq.values())
                if entropy > 4.5: return True
        return False

    def _parse_http_request(self, text):
        """Parse HTTP request."""
        lines  = text.split("\r\n")
        if not lines: return {}
        parts  = lines[0].split(" ")
        method = parts[0] if parts else ""
        path   = parts[1] if len(parts)>1 else ""
        host   = ""
        for line in lines[1:]:
            if line.lower().startswith("host:"):
                host = line.split(":",1)[1].strip()
                break
        return {"method":method,"path":path,"host":host}

    def stop(self):
        self._running = False
        if self.pcap_out and self.captured:
            wrpcap(str(self.pcap_out), self.captured)
            rprint(f"  [dim]Saved: {self.pcap_out}[/dim]")

    def start_connection_monitor(self):
        """Fallback: monitor connections without raw capture."""
        if not PSUTIL:
            rprint("[yellow]psutil not available. Install: pip install psutil[/yellow]")
            return False

        rprint("  [yellow]⚠ Using connection-level monitoring (no raw packets)[/yellow]")
        self._running = True

        def monitor():
            seen = set()
            while self._running:
                try:
                    for conn in psutil.net_connections(kind="inet"):
                        if conn.status == "ESTABLISHED" and conn.raddr:
                            key = (conn.laddr.ip, conn.raddr.ip, conn.raddr.port)
                            if key not in seen:
                                seen.add(key)
                                info = {
                                    "ts":       datetime.now().isoformat(),
                                    "src_ip":   conn.laddr.ip,
                                    "dst_ip":   conn.raddr.ip,
                                    "src_port": conn.laddr.port,
                                    "dst_port": conn.raddr.port,
                                    "protocol": "TCP",
                                    "bytes":    0,
                                }
                                self.state.add_packet(info)
                except: pass
                time.sleep(2)

        threading.Thread(target=monitor, daemon=True).start()
        return True

    def load_pcap(self, filepath):
        """Load and analyze a pcap file."""
        if not SCAPY:
            rprint("[yellow]Scapy required to load pcap files[/yellow]")
            return []
        rprint(f"  [dim]Loading pcap: {filepath}[/dim]")
        packets = rdpcap(str(filepath))
        rprint(f"  [green]Loaded {len(packets)} packets[/green]")
        for pkt in packets:
            self._process_packet(pkt)
        return packets

# ══════════════════════════════════════════════════════════════════════════════
# ⚡ THREAT DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

class ThreatDetector:
    """Real-time threat detection."""

    # Track state between packets
    _port_scan_tracker = defaultdict(lambda: {"ports":set(),"ts":0})
    _arp_table         = {}
    _brute_force       = defaultdict(list)
    _syn_tracker       = defaultdict(int)

    def __init__(self, state=None):
        self.state = state or STATE

    def check_packet(self, pkt):
        """Run all threat checks on a packet."""
        src = pkt.get("src_ip","")
        dst = pkt.get("dst_ip","")

        if not src or not dst: return

        self.check_port_scan(pkt)
        self.check_arp_spoof(pkt)
        self.check_beacon(pkt)
        self.check_data_exfil(pkt)
        self.check_brute_force(pkt)
        self.check_dns_tunnel(pkt)

    def check_port_scan(self, pkt):
        """Detect port scanning."""
        src  = pkt.get("src_ip","")
        port = pkt.get("dst_port",0)
        if not src or not port: return

        tracker = self._port_scan_tracker[src]
        tracker["ports"].add(port)
        now = time.time()

        if now - tracker["ts"] < 5:
            if len(tracker["ports"]) > 15:
                self.state.add_threat(
                    "PORT_SCAN","high",src,
                    pkt.get("dst_ip","?"),
                    f"Scanned {len(tracker['ports'])} ports in <5s"
                )
                tracker["ports"] = set()
        else:
            tracker["ts"] = now
            if len(tracker["ports"]) > 100:
                tracker["ports"] = set()

    def check_arp_spoof(self, pkt):
        """Detect ARP spoofing / poisoning."""
        if pkt.get("protocol") != "ARP": return
        if pkt.get("arp_op") != 2: return  # ARP reply

        src_ip  = pkt.get("arp_src","")
        src_mac = pkt.get("src_mac","")

        if src_ip and src_mac:
            if src_ip in self._arp_table:
                if self._arp_table[src_ip] != src_mac:
                    self.state.add_threat(
                        "ARP_SPOOF","critical",src_mac,src_ip,
                        f"ARP conflict: {src_ip} was {self._arp_table[src_ip]}, now {src_mac}"
                    )
            else:
                self._arp_table[src_ip] = src_mac

    def check_beacon(self, pkt):
        """Detect C2 beaconing (regular interval connections)."""
        src  = pkt.get("src_ip","")
        dst  = pkt.get("dst_ip","")
        port = pkt.get("dst_port",0)

        if not src or not dst or is_private(dst): return
        if port not in (80,443,8080,8443,4444,9001): return

        key = (src, dst, port)
        times = self.state.beacon_times[key]
        now   = time.time()
        times.append(now)

        if len(times) > 5:
            # Check if intervals are suspiciously regular
            intervals = [times[i]-times[i-1] for i in range(1,len(times))]
            avg_interval = sum(intervals) / len(intervals)
            variance     = sum((i-avg_interval)**2 for i in intervals) / len(intervals)

            if 10 < avg_interval < 3600 and variance < 25:
                self.state.add_threat(
                    "C2_BEACON","high",src,dst,
                    f"Regular beacon every ~{avg_interval:.0f}s to {dst}:{port} (variance:{variance:.1f})"
                )
                self.state.beacon_times[key] = times[-3:]  # reset

            if len(times) > 20:
                self.state.beacon_times[key] = times[-10:]

    def check_data_exfil(self, pkt):
        """Detect potential data exfiltration."""
        src   = pkt.get("src_ip","")
        dst   = pkt.get("dst_ip","")
        bytes_= pkt.get("bytes",0)

        if not src or not dst or is_private(dst): return
        if bytes_ < 1024*100: return  # ignore small transfers

        # Large outbound transfer
        total_out = self.state.ip_bytes_out.get(src,0)
        if total_out > 50*1024*1024:  # 50MB
            self.state.add_threat(
                "DATA_EXFIL","high",src,dst,
                f"Large outbound: {total_out//1024//1024}MB to {dst}"
            )
            # Reset to avoid spam
            self.state.ip_bytes_out[src] = 0

    def check_brute_force(self, pkt):
        """Detect brute force attempts."""
        dst_port = pkt.get("dst_port",0)
        src      = pkt.get("src_ip","")
        flags    = pkt.get("tcp_flags","")

        if dst_port not in (22,23,3389,21,25,110,143): return
        if "S" not in str(flags): return  # only SYN

        now = time.time()
        self._brute_force[src].append(now)
        # Keep last 60s
        self._brute_force[src] = [t for t in self._brute_force[src] if now-t < 60]

        if len(self._brute_force[src]) > 20:
            service = {22:"SSH",23:"Telnet",3389:"RDP",21:"FTP"}.get(dst_port,"unknown")
            self.state.add_threat(
                "BRUTE_FORCE","high",src,
                pkt.get("dst_ip","?"),
                f"{len(self._brute_force[src])} {service} attempts in 60s"
            )
            self._brute_force[src] = []

    def check_dns_tunnel(self, pkt):
        """Detect DNS tunneling."""
        query = pkt.get("dns_query","")
        if not query: return

        # Very long queries suggest tunneling
        if len(query) > 80:
            self.state.add_threat(
                "DNS_TUNNEL","medium",
                pkt.get("src_ip","?"),"DNS",
                f"Long DNS query ({len(query)} chars): {query[:60]}..."
            )

# ══════════════════════════════════════════════════════════════════════════════
# 🗺️ NETWORK MAPPER
# ══════════════════════════════════════════════════════════════════════════════

class NetworkMapper:
    """Discover and map network hosts."""

    def __init__(self, state=None):
        self.state = state or STATE

    def get_local_subnet(self):
        """Get local network subnet."""
        try:
            if PSUTIL:
                for name, addrs in psutil.net_if_addrs().items():
                    for addr in addrs:
                        if addr.family == socket.AF_INET:
                            ip = addr.address
                            if not ip.startswith("127."):
                                # Convert to /24
                                parts = ip.split(".")
                                return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        except: pass

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                parts = ip.split(".")
                return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
        except:
            return "192.168.1.0/24"

    def ping_sweep(self, subnet=None, timeout=1):
        """Discover live hosts via ping."""
        subnet = subnet or self.get_local_subnet()
        rprint(f"  [dim]Scanning: {subnet}[/dim]")

        try:
            network = ipaddress.ip_network(subnet, strict=False)
        except:
            rprint(f"[red]Invalid subnet: {subnet}[/red]")
            return []

        hosts   = []
        lock    = threading.Lock()

        def ping(ip_str):
            param  = "-n" if sys.platform=="win32" else "-c"
            result = subprocess.run(
                ["ping", param, "1", "-W", str(timeout), ip_str],
                capture_output=True, timeout=timeout+2
            )
            if result.returncode == 0:
                hostname = ""
                try: hostname = socket.gethostbyaddr(ip_str)[0]
                except: pass
                device = {
                    "ip":        ip_str,
                    "hostname":  hostname,
                    "mac":       "",
                    "vendor":    "",
                    "os_guess":  "",
                    "first_seen":datetime.now().isoformat(),
                    "last_seen": datetime.now().isoformat(),
                }
                with lock:
                    hosts.append(device)
                    self._save_device(device)

        threads = []
        for host in list(network.hosts())[:254]:
            t = threading.Thread(target=ping, args=(str(host),), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join(timeout=timeout+3)

        rprint(f"  [green]Found {len(hosts)} hosts[/green]")
        return sorted(hosts, key=lambda h: int(h["ip"].split(".")[-1]))

    def scan_ports(self, ip, ports=None, timeout=0.5):
        """Quick TCP port scan."""
        ports = ports or [21,22,23,25,53,80,110,143,443,445,
                         3306,3389,5432,6379,8080,8443,9200,27017]
        open_ports = []

        for port in ports:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(timeout)
                    if s.connect_ex((ip, port)) == 0:
                        service = self._service_name(port)
                        open_ports.append({"port":port,"service":service})
            except: pass

        return open_ports

    def _service_name(self, port):
        services = {
            21:"FTP",22:"SSH",23:"Telnet",25:"SMTP",53:"DNS",
            80:"HTTP",110:"POP3",143:"IMAP",443:"HTTPS",445:"SMB",
            3306:"MySQL",3389:"RDP",5432:"PostgreSQL",6379:"Redis",
            8080:"HTTP-Alt",8443:"HTTPS-Alt",9200:"Elasticsearch",
            27017:"MongoDB",
        }
        return services.get(port, str(port))

    def os_fingerprint(self, ip):
        """Guess OS from TTL and TCP window size."""
        # TTL-based guess (from ping or packets)
        ttl_guess = {
            64:  "Linux/Android",
            128: "Windows",
            255: "Cisco IOS / macOS",
        }
        # Check ARP table for MAC vendor
        vendor = ""
        conn = get_db()
        dev  = conn.execute("SELECT * FROM devices WHERE ip=?", (ip,)).fetchone()
        conn.close()
        if dev: vendor = dev["vendor"] or ""

        guess = f"Unknown {f'({vendor})' if vendor else ''}"
        return guess

    def _save_device(self, device):
        """Save device to database."""
        conn = get_db()
        conn.execute("""
            INSERT OR REPLACE INTO devices (mac,ip,hostname,vendor,first_seen,last_seen)
            VALUES (?,?,?,?,?,?)""",
            (device.get("mac",""), device["ip"],
             device.get("hostname",""), device.get("vendor",""),
             device["first_seen"], device["last_seen"])
        )
        conn.commit(); conn.close()

    def full_map(self, subnet=None):
        """Complete network map with ports and geo."""
        rprint("\n[bold yellow]🗺️  MAPPING NETWORK[/bold yellow]")

        hosts = self.ping_sweep(subnet)

        for host in hosts:
            ip    = host["ip"]
            ports = self.scan_ports(ip)
            host["open_ports"] = ports
            host["os_guess"]   = self.os_fingerprint(ip)

            if not is_private(ip):
                host["geo"] = geoip(ip)

        # AI analysis
        if AI_AVAILABLE and hosts:
            summary_txt = "\n".join(
                f"  {h['ip']} {h.get('hostname','')} ports:{[p['service'] for p in h.get('open_ports',[])]}"
                for h in hosts[:20]
            )
            analysis = ai_call(
                f"Network map found {len(hosts)} hosts:\n{summary_txt}\n\n"
                "As Sherlock Holmes analyzing a network:\n"
                "What's notable? Any security concerns?\n"
                "What does this network architecture reveal?",
                max_tokens=500
            )
            rprint(Panel(analysis[:500], border_style="yellow", title="🧠 Network Analysis"))

        return hosts

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 TRAFFIC INTELLIGENCE
# ══════════════════════════════════════════════════════════════════════════════

class TrafficIntelligence:
    """Sherlock reads the network like a crime scene."""

    def __init__(self, state=None):
        self.state = state or STATE

    def analyze_snapshot(self, window_minutes=5):
        """Analyze recent traffic snapshot."""
        if not AI_AVAILABLE:
            return self._basic_summary()

        # Build context
        threats = list(self.state.threats)[-10:]
        talkers = self.state.top_talkers(10)
        dns     = list(self.state.dns_queries)[-20:]
        conns   = list(self.state.connections)[-50:]

        # External destinations
        external = {}
        for c in conns:
            dst = c.get("dst_ip","")
            if dst and not is_private(dst):
                external[dst] = external.get(dst,0) + 1

        # Build prompt
        context = f"""
Network traffic snapshot (last {window_minutes} minutes):
Packets captured: {self.state.packets_total}
Total data: {self.state.bytes_total // 1024}KB
Uptime: {self.state.uptime()}

TOP TALKERS (most data sent):
{chr(10).join(f'  {ip}: {b//1024}KB' for ip,b in talkers[:5])}

EXTERNAL CONNECTIONS ({len(external)} unique destinations):
{chr(10).join(f'  {ip}: {c} connections' for ip,c in sorted(external.items(),key=lambda x:-x[1])[:5])}

RECENT THREATS ({len(threats)}):
{chr(10).join(f'  [{t["severity"]}] {t["type"]}: {t["description"][:60]}' for t in threats[-5:])}

RECENT DNS QUERIES ({len(dns)}):
{chr(10).join(f'  {d["src_ip"]} queried {d["query"]}' for d in dns[-5:])}
"""

        return ai_call(
            context + "\n\nAs Sherlock Holmes, analyze this network traffic.\n"
            "What is happening? Any threats? Any patterns?\n"
            "What should the network owner know right now?",
            max_tokens=800
        )

    def _basic_summary(self):
        """Summary without AI."""
        return (
            f"Network Summary:\n"
            f"  Packets: {self.state.packets_total}\n"
            f"  Data:    {self.state.bytes_total//1024}KB\n"
            f"  Threats: {len(self.state.threats)}\n"
            f"  Uptime:  {self.state.uptime()}"
        )

    def investigate_ip(self, ip):
        """Deep investigation of a specific IP."""
        rprint(f"\n[bold]🔍 INVESTIGATING: {ip}[/bold]")

        # Traffic stats
        bytes_out = self.state.ip_bytes_out.get(ip,0)
        bytes_in  = self.state.ip_bytes_in.get(ip,0)
        conns     = self.state.ip_conns.get(ip,set())
        ports     = self.state.ip_ports.get(ip,set())

        # DNS queries from this IP
        dns = [d for d in self.state.dns_queries if d.get("src_ip")==ip]

        # Threats involving this IP
        threats = [t for t in self.state.threats
                  if t.get("src_ip")==ip or t.get("dst_ip")==ip]

        # Geo
        geo = geoip(ip) if not is_private(ip) else {"country":"Local","org":"LAN"}

        # Tor check
        tor = is_tor_exit(ip) if not is_private(ip) else False

        result = {
            "ip":        ip,
            "geo":       geo,
            "tor_exit":  tor,
            "bytes_out": bytes_out,
            "bytes_in":  bytes_in,
            "connections":list(conns)[:20],
            "ports_used": list(ports)[:20],
            "dns_queries":[d["query"] for d in dns[:10]],
            "threats":   threats,
        }

        if AI_AVAILABLE:
            analysis = ai_call(
                f"IP Investigation: {ip}\n{json.dumps(result, default=str)}\n\n"
                "Sherlock-style analysis: What is this IP doing?\n"
                "Is it a threat? What evidence supports this?\n"
                "Recommended action?",
                max_tokens=600
            )
            result["analysis"] = analysis
            rprint(Panel(analysis[:500], border_style="yellow",
                        title=f"🔍 IP Investigation: {ip}"))

        return result

    def detect_anomalies(self):
        """Find anomalous behavior patterns."""
        anomalies = []

        # New devices (no baseline)
        for ip, conns in self.state.ip_conns.items():
            if len(conns) > 20 and is_private(ip):
                anomalies.append({
                    "type":    "HIGH_CONNECTIVITY",
                    "ip":      ip,
                    "detail":  f"Connected to {len(conns)} destinations",
                    "severity":"medium",
                })

        # Unusual port usage
        common_ports = {80,443,53,22,25,110,143,993,995}
        for ip, ports in self.state.ip_ports.items():
            unusual = ports - common_ports
            if len(unusual) > 10:
                anomalies.append({
                    "type":    "UNUSUAL_PORTS",
                    "ip":      ip,
                    "detail":  f"Using {len(unusual)} unusual ports",
                    "severity":"low",
                })

        return anomalies

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 GEO TRAFFIC MAP
# ══════════════════════════════════════════════════════════════════════════════

class GeoTrafficMap:
    """Where is your traffic actually going?"""

    def __init__(self, state=None):
        self.state = state or STATE

    def external_destinations(self):
        """Map all external IP connections with geo."""
        destinations = {}
        for conn in self.state.connections:
            dst = conn.get("dst_ip","")
            if dst and not is_private(dst):
                if dst not in destinations:
                    destinations[dst] = {
                        "ip":      dst,
                        "count":   0,
                        "bytes":   0,
                        "sources": set(),
                    }
                destinations[dst]["count"]  += 1
                destinations[dst]["bytes"]  += conn.get("bytes",0)
                src = conn.get("src_ip","")
                if src: destinations[dst]["sources"].add(src)

        # Add geo for top destinations
        top = sorted(destinations.values(), key=lambda x:-x["count"])[:30]
        for dest in top:
            dest["geo"]     = geoip(dest["ip"])
            dest["sources"] = list(dest["sources"])

        return top

    def country_summary(self):
        """Traffic by destination country."""
        countries = defaultdict(lambda:{"count":0,"bytes":0,"ips":set()})
        for conn in self.state.connections:
            dst = conn.get("dst_ip","")
            if dst and not is_private(dst):
                geo = geoip(dst)
                country = geo.get("country","?")
                countries[country]["count"]  += 1
                countries[country]["bytes"]  += conn.get("bytes",0)
                countries[country]["ips"].add(dst)

        result = [
            {"country":c,"connections":v["count"],
             "bytes":v["bytes"],"unique_ips":len(v["ips"])}
            for c,v in countries.items()
        ]
        return sorted(result, key=lambda x:-x["connections"])

    def suspicious_destinations(self):
        """Flag connections to suspicious countries/ASNs."""
        # High-risk countries for unexpected traffic
        high_risk = {"North Korea","Iran","Russia","China"}
        suspicious = []

        for conn in self.state.connections:
            dst = conn.get("dst_ip","")
            if not dst or is_private(dst): continue

            geo = geoip(dst)
            country = geo.get("country","")
            org     = geo.get("org","")

            flags = []
            if country in high_risk:
                flags.append(f"high_risk_country:{country}")
            if "tor" in org.lower() or "exit" in org.lower():
                flags.append("tor_exit_node")
            if "bullet" in org.lower() or "hosting" in org.lower():
                flags.append("bulletproof_hosting")

            if flags:
                suspicious.append({
                    **conn,
                    "geo":   geo,
                    "flags": flags,
                })

        return suspicious[:20]

# ══════════════════════════════════════════════════════════════════════════════
# 🌍 LIVE NETWORK UI
# ══════════════════════════════════════════════════════════════════════════════

NETWORK_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FORGE NETWORK</title>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Bebas+Neue&display=swap" rel="stylesheet">
<style>
:root{--bg:#04080f;--panel:#080d1a;--border:#101828;--green:#00ff88;--green-d:#005c33;--amber:#ff9500;--red:#ff2244;--blue:#0088ff;--dim:#1e2a3a;--text:#7a9ab0;--head:#d0e4f8}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);font-family:'Share Tech Mono',monospace;color:var(--text);height:100vh;overflow:hidden;display:grid;grid-template-rows:48px 1fr 32px;grid-template-columns:300px 1fr 280px}
header{grid-column:1/-1;background:rgba(4,8,15,0.98);border-bottom:1px solid var(--green-d);display:flex;align-items:center;padding:0 16px;gap:14px}
.logo{font-family:'Bebas Neue';font-size:20px;letter-spacing:7px;color:var(--green);text-shadow:0 0 16px rgba(0,255,136,0.3)}
.hdr-stat{font-size:9px;letter-spacing:2px;color:var(--dim)}
.hdr-stat span{color:var(--green)}
.pulse{width:7px;height:7px;border-radius:50%;background:var(--green);animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:1;box-shadow:0 0 4px var(--green)}50%{opacity:0.3;box-shadow:none}}
.panel{background:var(--panel);border-right:1px solid var(--border);overflow-y:auto;scrollbar-width:thin;scrollbar-color:var(--border) transparent}
.panel-title{font-size:8px;letter-spacing:3px;color:var(--green-d);padding:10px 12px 6px;border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--panel);z-index:1}
/* DEVICES */
.device-card{padding:10px 12px;border-bottom:1px solid var(--border);cursor:pointer;transition:background 0.1s}
.device-card:hover{background:rgba(0,255,136,0.03)}
.device-card.selected{border-left:2px solid var(--green)}
.device-card.threat{border-left:2px solid var(--red)}
.dc-ip{font-size:12px;color:var(--green);margin-bottom:2px}
.dc-name{font-size:10px;color:var(--head)}
.dc-meta{font-size:9px;color:var(--dim)}
/* MAIN AREA */
.main-area{background:var(--bg);position:relative;overflow:hidden}
canvas#network-canvas{width:100%;height:100%}
/* THREATS PANEL */
.right-panel{background:var(--panel);border-left:1px solid var(--border);overflow-y:auto;scrollbar-width:thin}
.threat-item{padding:10px 12px;border-bottom:1px solid var(--border)}
.threat-item.critical{border-left:3px solid var(--red)}
.threat-item.high{border-left:3px solid rgba(255,34,68,0.6)}
.threat-item.medium{border-left:3px solid var(--amber)}
.threat-item.low{border-left:3px solid var(--dim)}
.ti-type{font-size:10px;color:var(--head);margin-bottom:2px;letter-spacing:1px}
.ti-desc{font-size:9px;color:var(--text);line-height:1.5}
.ti-meta{font-size:8px;color:var(--dim);margin-top:3px}
/* STATUS BAR */
.status-bar{grid-column:1/-1;background:rgba(0,0,0,0.9);border-top:1px solid var(--border);display:flex;align-items:center;padding:0 14px;gap:18px;font-size:9px;letter-spacing:1px;color:var(--dim)}
.sb-val{color:var(--green)}
/* CONNECTION FEED */
.conn-feed{position:absolute;bottom:8px;left:8px;right:8px;pointer-events:none}
.conn-line{font-size:9px;color:rgba(0,255,136,0.4);letter-spacing:1px;padding:1px 0;animation:fade-in 0.3s}
@keyframes fade-in{from{opacity:0}to{opacity:1}}
/* IP DETAIL */
#ip-detail{position:absolute;top:12px;right:12px;width:260px;background:rgba(4,8,15,0.96);border:1px solid var(--green-d);display:none;padding:14px;font-size:10px;line-height:1.8}
#ip-detail.show{display:block}
.id-title{font-family:'Bebas Neue';font-size:16px;letter-spacing:4px;color:var(--green);margin-bottom:8px}
.id-row{display:flex;justify-content:space-between;border-bottom:1px solid var(--border);padding:3px 0}
.id-key{color:var(--dim)}
.id-val{color:var(--head)}
</style>
</head>
<body>
<header>
  <div class="logo">NETWORK</div>
  <div class="pulse" id="pulse"></div>
  <div class="hdr-stat">PACKETS <span id="h-packets">0</span></div>
  <div class="hdr-stat">DATA <span id="h-data">0KB</span></div>
  <div class="hdr-stat">THREATS <span id="h-threats">0</span></div>
  <div class="hdr-stat">DEVICES <span id="h-devices">0</span></div>
  <div style="flex:1"></div>
  <div class="hdr-stat">UPTIME <span id="h-uptime">0s</span></div>
</header>

<!-- LEFT: DEVICES -->
<div class="panel" id="devices-panel">
  <div class="panel-title">DEVICES ON NETWORK</div>
  <div id="device-list"></div>
</div>

<!-- CENTER: NETWORK GRAPH -->
<div class="main-area">
  <canvas id="network-canvas"></canvas>
  <div class="conn-feed" id="conn-feed"></div>
  <div id="ip-detail">
    <div class="id-title" id="id-ip">--</div>
    <div id="id-rows"></div>
    <div style="margin-top:8px;font-size:9px;color:var(--text);border-top:1px solid var(--border);padding-top:8px" id="id-analysis"></div>
  </div>
</div>

<!-- RIGHT: THREATS -->
<div class="right-panel">
  <div class="panel-title">THREAT FEED</div>
  <div id="threat-list"></div>
</div>

<div class="status-bar">
  <span>FORGE NETWORK</span>
  <span>TOP TALKER: <span class="sb-val" id="sb-talker">--</span></span>
  <span>EXT CONNS: <span class="sb-val" id="sb-ext">0</span></span>
  <span>DNS: <span class="sb-val" id="sb-dns">0</span></span>
  <div style="flex:1"></div>
  <span id="sb-iface">--</span>
</div>

<script>
const API = 'http://localhost:7346';
let devices = {}, threats = [], connections = [];
let canvas, ctx, animFrame;
let selectedIP = null;

// ── CANVAS NETWORK GRAPH ─────────────────────────────────────
function initCanvas() {
  canvas = document.getElementById('network-canvas');
  ctx    = canvas.getContext('2d');
  resize();
  window.addEventListener('resize', resize);
  drawLoop();
}

function resize() {
  canvas.width  = canvas.offsetWidth;
  canvas.height = canvas.offsetHeight;
}

const nodePositions = {};
function getNodePos(ip) {
  if (!nodePositions[ip]) {
    const cx = canvas.width/2, cy = canvas.height/2;
    const angle = Math.random() * Math.PI * 2;
    const r     = 80 + Math.random() * Math.min(canvas.width, canvas.height) * 0.3;
    nodePositions[ip] = {
      x: cx + Math.cos(angle)*r,
      y: cy + Math.sin(angle)*r,
      vx:0, vy:0,
    };
  }
  return nodePositions[ip];
}

function drawLoop() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Draw connections
  connections.slice(-100).forEach(c => {
    const src = c.src_ip, dst = c.dst_ip;
    if (!src || !dst) return;
    const sp = getNodePos(src), dp = getNodePos(dst);
    const isExternal = !dst.startsWith('192.168') && !dst.startsWith('10.');
    ctx.beginPath();
    ctx.moveTo(sp.x, sp.y);
    ctx.lineTo(dp.x, dp.y);
    ctx.strokeStyle = isExternal ? 'rgba(255,34,68,0.15)' : 'rgba(0,255,136,0.08)';
    ctx.lineWidth   = 1;
    ctx.stroke();
  });

  // Draw nodes
  Object.values(devices).forEach(dev => {
    const pos   = getNodePos(dev.ip);
    const hasTh = threats.some(t => t.src_ip===dev.ip || t.dst_ip===dev.ip);
    const isSelected = selectedIP === dev.ip;

    // Glow
    const grad = ctx.createRadialGradient(pos.x,pos.y,0,pos.x,pos.y,isSelected?20:12);
    grad.addColorStop(0, hasTh ? 'rgba(255,34,68,0.4)' : 'rgba(0,255,136,0.3)');
    grad.addColorStop(1, 'transparent');
    ctx.beginPath(); ctx.arc(pos.x,pos.y,isSelected?20:12,0,Math.PI*2);
    ctx.fillStyle = grad; ctx.fill();

    // Node
    ctx.beginPath(); ctx.arc(pos.x,pos.y,5,0,Math.PI*2);
    ctx.fillStyle = hasTh ? '#ff2244' : '#00ff88';
    ctx.fill();

    // Label
    ctx.font = '9px Share Tech Mono';
    ctx.fillStyle = isSelected ? '#00ff88' : '#4a6a80';
    ctx.fillText(dev.ip, pos.x+8, pos.y+3);
  });

  animFrame = requestAnimationFrame(drawLoop);
}

canvas?.addEventListener('click', e => {
  const rect = canvas.getBoundingClientRect();
  const mx   = e.clientX - rect.left;
  const my   = e.clientY - rect.top;
  for (const [ip, pos] of Object.entries(nodePositions)) {
    const d = Math.sqrt((mx-pos.x)**2 + (my-pos.y)**2);
    if (d < 12) { showIPDetail(ip); return; }
  }
  document.getElementById('ip-detail').classList.remove('show');
  selectedIP = null;
});

// ── DATA REFRESH ─────────────────────────────────────────────
async function refresh() {
  try {
    const [status, devsData, threatsData] = await Promise.all([
      fetch(API+'/api/status').then(r=>r.json()),
      fetch(API+'/api/devices').then(r=>r.json()),
      fetch(API+'/api/threats').then(r=>r.json()),
    ]);

    // Update header
    document.getElementById('h-packets').textContent = status.packets || 0;
    document.getElementById('h-data').textContent    = formatBytes(status.bytes || 0);
    document.getElementById('h-threats').textContent = status.threat_count || 0;
    document.getElementById('h-devices').textContent = Object.keys(devsData.devices||{}).length;
    document.getElementById('h-uptime').textContent  = status.uptime || '0s';
    document.getElementById('sb-iface').textContent  = status.iface || '?';
    document.getElementById('sb-dns').textContent    = status.dns_count || 0;

    // Top talker
    const talker = (status.top_talkers||[])[0];
    if (talker) document.getElementById('sb-talker').textContent = `${talker[0]} (${formatBytes(talker[1])})`;

    // Devices
    devices = devsData.devices || {};
    renderDevices();

    // Threats
    threats = threatsData.threats || [];
    renderThreats();

    // Connections
    const connData = await fetch(API+'/api/connections').then(r=>r.json());
    connections = connData.connections || [];
    renderConnFeed();

    document.getElementById('sb-ext').textContent =
      connections.filter(c=>c.dst_ip&&!c.dst_ip.startsWith('192.')).length;

  } catch(e) {
    // Server not connected
  }
}

function renderDevices() {
  const list = document.getElementById('device-list');
  list.innerHTML = Object.values(devices).map(dev => {
    const hasThreat = threats.some(t=>t.src_ip===dev.ip||t.dst_ip===dev.ip);
    return `<div class="device-card ${hasThreat?'threat':''} ${selectedIP===dev.ip?'selected':''}"
      onclick="showIPDetail('${dev.ip}')">
      <div class="dc-ip">${dev.ip}</div>
      <div class="dc-name">${dev.hostname||dev.vendor||'Unknown'}</div>
      <div class="dc-meta">${dev.os_guess||''} ${dev.last_seen?.slice(11,19)||''}</div>
    </div>`;
  }).join('');
}

function renderThreats() {
  const list = document.getElementById('threat-list');
  list.innerHTML = [...threats].reverse().slice(0,30).map(t => `
    <div class="threat-item ${t.severity}">
      <div class="ti-type">${t.type}</div>
      <div class="ti-desc">${t.description?.slice(0,80)||''}</div>
      <div class="ti-meta">${t.src_ip||'?'} → ${t.dst_ip||'?'} · ${t.ts?.slice(11,19)||''}</div>
    </div>`).join('');
}

function renderConnFeed() {
  const feed = document.getElementById('conn-feed');
  feed.innerHTML = connections.slice(-6).map(c =>
    `<div class="conn-line">▸ ${c.src_ip||'?'} → ${c.dst_ip||'?'}:${c.dst_port||'?'} [${c.protocol||'?'}]</div>`
  ).join('');
}

async function showIPDetail(ip) {
  selectedIP = ip;
  document.getElementById('ip-detail').classList.add('show');
  document.getElementById('id-ip').textContent = ip;

  const rows = document.getElementById('id-rows');
  const dev  = devices[ip] || {};
  const devThreats = threats.filter(t=>t.src_ip===ip||t.dst_ip===ip);

  rows.innerHTML = `
    <div class="id-row"><span class="id-key">Hostname</span><span class="id-val">${dev.hostname||'?'}</span></div>
    <div class="id-row"><span class="id-key">OS</span><span class="id-val">${dev.os_guess||'?'}</span></div>
    <div class="id-row"><span class="id-key">Vendor</span><span class="id-val">${dev.vendor||'?'}</span></div>
    <div class="id-row"><span class="id-key">Threats</span><span class="id-val" style="color:${devThreats.length?'var(--red)':'var(--green)'}">${devThreats.length}</span></div>
    <div class="id-row"><span class="id-key">First Seen</span><span class="id-val">${dev.first_seen?.slice(0,19)||'?'}</span></div>
  `;

  // Fetch analysis
  try {
    const d = await fetch(API+'/api/ip/investigate',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ip})
    }).then(r=>r.json());
    document.getElementById('id-analysis').textContent =
      d.analysis?.slice(0,200) || 'No analysis available.';
  } catch(e) {}
}

function formatBytes(b) {
  if (b > 1024*1024) return (b/1024/1024).toFixed(1)+'MB';
  if (b > 1024)      return (b/1024).toFixed(0)+'KB';
  return b+'B';
}

// ── INIT ──────────────────────────────────────────────────────
initCanvas();
setInterval(refresh, 2000);
refresh();
</script>
</body>
</html>"""

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API SERVER
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7346, iface=None):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    sniffer    = PacketSniffer(iface=iface, state=STATE)
    mapper     = NetworkMapper(STATE)
    intel      = TrafficIntelligence(STATE)
    geo        = GeoTrafficMap(STATE)
    detector   = ThreatDetector(STATE)

    # Start capture
    sniffer.start()

    class NetworkAPI(BaseHTTPRequestHandler):
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
            path=urlparse(self.path).path
            if path in ("/","/index.html"):
                self._html(NETWORK_UI_HTML); return
            if path=="/api/status":
                self._json({
                    "status":      "online",
                    "packets":     STATE.packets_total,
                    "bytes":       STATE.bytes_total,
                    "uptime":      STATE.uptime(),
                    "threat_count":len(STATE.threats),
                    "dns_count":   len(STATE.dns_queries),
                    "top_talkers": STATE.top_talkers(3),
                    "iface":       sniffer.iface,
                    "ai":          AI_AVAILABLE,
                    "scapy":       SCAPY,
                })
            elif path=="/api/devices":
                conn=get_db()
                rows=conn.execute("SELECT * FROM devices ORDER BY last_seen DESC").fetchall()
                conn.close()
                devs={r["ip"]:dict(r) for r in rows}
                # Add live state
                for ip in STATE.ip_conns:
                    if ip not in devs:
                        devs[ip]={"ip":ip,"mac":"","hostname":"","os_guess":"","vendor":"",
                                 "first_seen":datetime.now().isoformat(),
                                 "last_seen":datetime.now().isoformat()}
                self._json({"devices":devs})
            elif path=="/api/threats":
                self._json({"threats":list(STATE.threats)})
            elif path=="/api/connections":
                self._json({"connections":list(STATE.connections)[-100:]})
            elif path=="/api/dns":
                self._json({"queries":list(STATE.dns_queries)[-50:]})
            elif path=="/api/geo":
                self._json({"destinations":geo.external_destinations()[:20]})
            elif path=="/api/countries":
                self._json({"countries":geo.country_summary()[:20]})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path=urlparse(self.path).path
            body=self._body()
            if path=="/api/analyze":
                result=intel.analyze_snapshot()
                self._json({"analysis":result})
            elif path=="/api/ip/investigate":
                ip=body.get("ip","")
                if not ip: self._json({"error":"ip required"},400); return
                result=intel.investigate_ip(ip)
                self._json(result)
            elif path=="/api/map":
                subnet=body.get("subnet")
                hosts=mapper.full_map(subnet)
                self._json({"hosts":hosts})
            elif path=="/api/scan":
                ip=body.get("ip","")
                if not ip: self._json({"error":"ip required"},400); return
                ports=mapper.scan_ports(ip)
                self._json({"ip":ip,"open_ports":ports})
            elif path=="/api/threats/clear":
                STATE.threats.clear()
                self._json({"ok":True})
            else:
                self._json({"error":"unknown"},404)

    server=HTTPServer(("0.0.0.0",port),NetworkAPI)
    rprint(f"\n  [bold yellow]🔍 FORGE NETWORK[/bold yellow]")
    rprint(f"  [green]UI:  http://localhost:{port}[/green]")
    rprint(f"  [green]API: http://localhost:{port}/api/status[/green]")
    rprint(f"  [dim]Interface: {sniffer.iface or 'auto'}[/dim]")
    rprint(f"  [dim]Scapy: {'✅' if SCAPY else '⚠️  using connection monitor'}[/dim]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# 🎮 MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ███╗   ██╗███████╗████████╗██╗    ██╗ ██████╗ ██████╗ ██╗  ██╗
  ████╗  ██║██╔════╝╚══██╔══╝██║    ██║██╔═══██╗██╔══██╗██║ ██╔╝
  ██╔██╗ ██║█████╗     ██║   ██║ █╗ ██║██║   ██║██████╔╝█████╔╝
  ██║╚██╗██║██╔══╝     ██║   ██║███╗██║██║   ██║██╔══██╗██╔═██╗
  ██║ ╚████║███████╗   ██║   ╚███╔███╔╝╚██████╔╝██║  ██║██║  ██╗
  ╚═╝  ╚═══╝╚══════╝   ╚═╝    ╚══╝╚══╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝
[/yellow]
[bold]  🔍 FORGE NETWORK — Network Intelligence Engine[/bold]
[dim]  Packets don't lie. FORGE reads them like a crime scene.[/dim]
"""

def interactive():
    rprint(BANNER)
    rprint(f"  [dim]Scapy:   {'✅' if SCAPY else '❌ pip install scapy (needs sudo)'}[/dim]")
    rprint(f"  [dim]psutil:  {'✅' if PSUTIL else '❌ pip install psutil'}[/dim]")
    rprint(f"  [dim]AI:      {'✅' if AI_AVAILABLE else '❌ pip install anthropic'}[/dim]\n")

    mapper  = NetworkMapper(STATE)
    intel   = TrafficIntelligence(STATE)
    sniffer = PacketSniffer(state=STATE)
    geo     = GeoTrafficMap(STATE)

    rprint("[dim]Commands: watch | map | scan | analyze | threats | dns | geo | server | help[/dim]\n")

    while True:
        try:
            inp = console.input if RICH else input
            raw = inp("[yellow bold]🔍 network >[/yellow bold] ").strip()
            if not raw: continue
            parts = raw.split(None,1)
            cmd   = parts[0].lower()
            args  = parts[1] if len(parts)>1 else ""

            if cmd in ("quit","exit","q"):
                rprint("[dim]Network monitor offline.[/dim]"); break

            elif cmd == "help":
                rprint("""
[bold yellow]FORGE NETWORK Commands[/bold yellow]

  [yellow]watch[/yellow] [iface]       Start live packet capture
  [yellow]map[/yellow] [subnet]        Map all devices on network
  [yellow]scan[/yellow] <ip>           Port scan specific host
  [yellow]analyze[/yellow]             AI analysis of current traffic
  [yellow]investigate[/yellow] <ip>    Deep dive on specific IP
  [yellow]threats[/yellow]             Show detected threats
  [yellow]dns[/yellow]                 Show DNS query log
  [yellow]geo[/yellow]                 Show external connection map
  [yellow]countries[/yellow]           Traffic by country
  [yellow]pcap[/yellow] <file>         Load and analyze pcap file
  [yellow]server[/yellow]              Start live UI server
""")

            elif cmd == "watch":
                iface = args.strip() or None
                rprint(f"\n[bold]🔍 LIVE CAPTURE[/bold] (Ctrl+C to stop)")
                sniffer.start(iface=iface)
                rprint("  [dim]Capturing... Press Ctrl+C to stop[/dim]")
                try:
                    while True:
                        time.sleep(5)
                        rprint(
                            f"  [dim]Packets:{STATE.packets_total} "
                            f"Data:{STATE.bytes_total//1024}KB "
                            f"Threats:{len(STATE.threats)}[/dim]"
                        )
                except KeyboardInterrupt:
                    sniffer.stop()
                    rprint("\n  [dim]Capture stopped.[/dim]")

            elif cmd == "map":
                subnet = args.strip() or None
                hosts  = mapper.full_map(subnet)
                if RICH and hosts:
                    t = Table(border_style="yellow",box=rbox.ROUNDED,title="Network Map")
                    t.add_column("IP",       style="green", width=16)
                    t.add_column("Hostname", style="cyan",  width=20)
                    t.add_column("OS",       style="dim",   width=14)
                    t.add_column("Ports",    width=30)
                    for h in hosts:
                        ports = ", ".join(p["service"] for p in h.get("open_ports",[]))
                        t.add_row(h["ip"],h.get("hostname","")[:19],
                                 h.get("os_guess","")[:13],ports[:29])
                    console.print(t)

            elif cmd == "scan":
                ip    = args.strip()
                if not ip: rprint("[yellow]Usage: scan <ip>[/yellow]"); continue
                ports = mapper.scan_ports(ip)
                rprint(f"\n  [bold]Port scan: {ip}[/bold]")
                for p in ports:
                    rprint(f"  [green]{p['port']:5}[/green]  {p['service']}")
                if not ports:
                    rprint("  [dim]No open ports found.[/dim]")

            elif cmd == "analyze":
                rprint("\n[bold]🧠 TRAFFIC ANALYSIS[/bold]")
                result = intel.analyze_snapshot()
                rprint(Panel(result[:700], border_style="yellow", title="Sherlock Analysis"))

            elif cmd == "investigate":
                ip = args.strip()
                if not ip: rprint("[yellow]Usage: investigate <ip>[/yellow]"); continue
                intel.investigate_ip(ip)

            elif cmd == "threats":
                if not STATE.threats:
                    rprint("[dim]No threats detected.[/dim]")
                else:
                    for t in list(STATE.threats)[-10:]:
                        c = {"critical":"red bold","high":"red","medium":"yellow"}.get(t["severity"],"dim")
                        rprint(f"  [{c}][{t['severity'].upper()}][/{c}] {t['type']}: {t['description'][:60]}")

            elif cmd == "dns":
                if not STATE.dns_queries:
                    rprint("[dim]No DNS queries captured.[/dim]")
                else:
                    for q in list(STATE.dns_queries)[-15:]:
                        flag = "[red]⚠[/red]" if q.get("suspicious") else "  "
                        rprint(f"  {flag} {q.get('src_ip','?'):<16} {q.get('query','?')}")

            elif cmd == "geo":
                dests = geo.external_destinations()
                if not dests:
                    rprint("[dim]No external connections yet.[/dim]")
                else:
                    for d in dests[:10]:
                        g = d.get("geo",{})
                        rprint(f"  {d['ip']:<18} {g.get('country','?'):<16} {g.get('org','')[:30]}")

            elif cmd == "countries":
                summary = geo.country_summary()
                for s in summary[:10]:
                    rprint(f"  {s['country']:<20} {s['connections']:>6} conns  {s['bytes']//1024:>8}KB")

            elif cmd == "pcap":
                filepath = args.strip()
                if not filepath: rprint("[yellow]Usage: pcap <file>[/yellow]"); continue
                sniffer.load_pcap(filepath)
                rprint(f"  [green]Loaded. Run 'analyze' or 'threats'.[/green]")

            elif cmd == "server":
                port = 7346
                rprint(f"[yellow]Starting NETWORK server on port {port}...[/yellow]")
                iface = args.strip() or None
                threading.Thread(
                    target=start_server, args=(port,iface), daemon=True
                ).start()
                time.sleep(1)
                rprint(f"[green]Live at http://localhost:{port}[/green]")

            else:
                if AI_AVAILABLE:
                    r = ai_call(
                        f"Network command: {raw}\n"
                        f"Current state: {STATE.packets_total} packets, "
                        f"{len(STATE.threats)} threats\n"
                        "How should I respond to this?",
                        max_tokens=150
                    )
                    rprint(f"  [dim]{r[:150]}[/dim]")
                else:
                    rprint("[dim]Unknown command. Type 'help'.[/dim]")

        except (KeyboardInterrupt,EOFError):
            rprint("\n[dim]Network monitor offline.[/dim]"); break

def main():
    if "--server" in sys.argv:
        rprint(BANNER)
        port  = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7346
        iface = sys.argv[sys.argv.index("--iface")+1] if "--iface" in sys.argv else None
        start_server(port, iface)
        return

    if "--watch" in sys.argv:
        rprint(BANNER)
        idx   = sys.argv.index("--watch")
        iface = sys.argv[idx+1] if idx+1<len(sys.argv) and not sys.argv[idx+1].startswith("--") else None
        sniffer = PacketSniffer(iface=iface)
        sniffer.start()
        intel = TrafficIntelligence()
        try:
            while True:
                time.sleep(10)
                rprint(
                    f"  Packets:{STATE.packets_total} "
                    f"Data:{STATE.bytes_total//1024}KB "
                    f"Threats:{len(STATE.threats)} "
                    f"DNS:{len(STATE.dns_queries)}"
                )
        except KeyboardInterrupt:
            sniffer.stop()
        return

    if "--map" in sys.argv:
        rprint(BANNER)
        mapper = NetworkMapper()
        subnet = sys.argv[sys.argv.index("--map")+1] if sys.argv.index("--map")+1<len(sys.argv) else None
        mapper.full_map(subnet)
        return

    if "--scan" in sys.argv:
        idx = sys.argv.index("--scan")
        ip  = sys.argv[idx+1] if idx+1<len(sys.argv) else ""
        if ip:
            rprint(BANNER)
            mapper = NetworkMapper()
            ports  = mapper.scan_ports(ip)
            rprint(f"\n[bold]Port scan: {ip}[/bold]")
            for p in ports:
                rprint(f"  [green]{p['port']:5}[/green]  {p['service']}")
        return

    if "--pcap" in sys.argv:
        idx  = sys.argv.index("--pcap")
        file = sys.argv[idx+1] if idx+1<len(sys.argv) else ""
        if file:
            rprint(BANNER)
            sniffer = PacketSniffer()
            sniffer.load_pcap(file)
            intel = TrafficIntelligence()
            rprint(Panel(intel.analyze_snapshot(), border_style="yellow"))
        return

    interactive()

if __name__ == "__main__":
    main()
