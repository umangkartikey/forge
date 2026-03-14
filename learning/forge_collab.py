#!/usr/bin/env python3
"""
FORGE COLLAB — Distributed Intelligence Network
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Multiple FORGE instances. One shared mind.

Node A finds something. Every node knows instantly.
Node B dreams at 3am. It thinks across ALL nodes' data.
Node C catches an attacker. The whole network responds.

One FORGE. Many bodies. One mind.

Modules:
  📡 Node Discovery     → UDP broadcast + manual peers
  🔄 Intelligence Sync  → forge_memory across instances
  🧠 Distributed Tasks  → split work, merge findings
  📢 Broadcast Alerts   → critical findings reach all nodes
  🌐 Collab UI          → live network map :7350

Usage:
  python forge_collab.py                     # interactive
  python forge_collab.py --start             # start node (auto-discover)
  python forge_collab.py --peer 192.168.1.5  # add manual peer
  python forge_collab.py --broadcast "alert" # broadcast to all nodes
  python forge_collab.py --sync              # sync memory with all peers
  python forge_collab.py --status            # show node network
  python forge_collab.py --server            # API + UI :7350
"""

import sys, os, re, json, time, socket, threading, hashlib, sqlite3
import uuid, struct
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Forge Memory integration
try:
    from forge_memory import Memory, remember, seen_before
    MEMORY = True
except ImportError:
    MEMORY = False
    class Memory:
        def stats(self): return {}
        def remember(self,*a,**k): pass
        def recall(self,e): return None
        def top_risk_entities(self,n=10): return []
        def get_timeline(self,h=24): return []
        def synthesize_recent(self,h=24): return ""

# AI
try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True
    def ai_call(prompt, system="", max_tokens=800):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or COLLAB_SYSTEM,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text
except ImportError:
    AI_AVAILABLE = False
    def ai_call(p,s="",m=800): return "[AI unavailable]"

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

COLLAB_SYSTEM = """You are FORGE COLLAB — synthesizing intelligence across a distributed network of FORGE nodes.

Each node sees a different piece of the picture.
Your job is to find what no single node could see alone.

When synthesizing across nodes:
- What patterns emerge only when combining all node data?
- Which entity appears on multiple nodes = higher threat
- What did Node A find that Node B's data now confirms?
- The whole is smarter than any single part."""

# ── Paths & Config ─────────────────────────────────────────────────────────────
COLLAB_DIR = Path("forge_collab")
COLLAB_DIR.mkdir(exist_ok=True)
COLLAB_DB  = COLLAB_DIR / "collab.db"

# Network constants
DISCOVERY_PORT  = 47771   # UDP broadcast
SYNC_PORT       = 47772   # TCP sync
API_PORT        = 7350    # HTTP API + UI
BROADCAST_PORT  = 47773   # UDP alerts
PROTOCOL_VER    = "FORGE/1.0"
CAPABILITIES    = ["memory","network","social","dream","honeypot","ghost","embodied"]

def get_node_id():
    """Stable node ID based on machine."""
    fp = COLLAB_DIR / "node_id"
    if fp.exists():
        return fp.read_text().strip()
    nid = str(uuid.uuid4())[:8].upper()
    fp.write_text(nid)
    return nid

NODE_ID = get_node_id()

def get_db():
    conn = sqlite3.connect(str(COLLAB_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS peers (
            id          TEXT PRIMARY KEY,
            name        TEXT,
            ip          TEXT,
            port        INTEGER,
            capabilities TEXT DEFAULT '[]',
            version     TEXT,
            first_seen  TEXT,
            last_seen   TEXT,
            last_ping   TEXT,
            status      TEXT DEFAULT 'unknown',
            entities_shared INTEGER DEFAULT 0,
            alerts_sent     INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            from_node   TEXT,
            to_node     TEXT DEFAULT 'ALL',
            msg_type    TEXT,
            payload     TEXT,
            delivered   INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS shared_entities (
            entity_id   TEXT,
            from_node   TEXT,
            ts          TEXT,
            fact_type   TEXT,
            confidence  REAL,
            PRIMARY KEY (entity_id, from_node, fact_type)
        );
        CREATE TABLE IF NOT EXISTS sync_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            peer_id     TEXT,
            direction   TEXT,
            entities    INTEGER DEFAULT 0,
            facts       INTEGER DEFAULT 0,
            status      TEXT
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 📡 NODE DISCOVERY
# ══════════════════════════════════════════════════════════════════════════════

class NodeDiscovery:
    """Find other FORGE nodes on the network."""

    def __init__(self, node_name=None):
        self.node_name   = node_name or f"FORGE-{NODE_ID}"
        self.running     = False
        self._sock       = None
        self.on_peer_found = None  # callback

    def _beacon_payload(self):
        """What we broadcast about ourselves."""
        active_caps = [c for c in CAPABILITIES
                      if Path(f"forge_{c}.py").exists() or Path(f"forge_{c}").exists()]
        return json.dumps({
            "protocol":    PROTOCOL_VER,
            "node_id":     NODE_ID,
            "name":        self.node_name,
            "sync_port":   SYNC_PORT,
            "api_port":    API_PORT,
            "capabilities":active_caps,
            "ts":          datetime.now().isoformat(),
        }).encode()

    def start_beacon(self, interval=30):
        """Broadcast presence every N seconds."""
        self.running = True

        def beacon_loop():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            while self.running:
                try:
                    sock.sendto(self._beacon_payload(), ("<broadcast>", DISCOVERY_PORT))
                except Exception:
                    pass
                time.sleep(interval)
            sock.close()

        threading.Thread(target=beacon_loop, daemon=True).start()
        rprint(f"  [dim]Broadcasting on UDP:{DISCOVERY_PORT}[/dim]")

    def start_listener(self):
        """Listen for other nodes' beacons."""
        def listen_loop():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("", DISCOVERY_PORT))
                sock.settimeout(2.0)
                while self.running:
                    try:
                        data, addr = sock.recvfrom(4096)
                        payload = json.loads(data.decode())
                        if payload.get("node_id") != NODE_ID:
                            self._handle_peer(payload, addr[0])
                    except socket.timeout:
                        pass
                    except Exception:
                        pass
                sock.close()
            except Exception as e:
                rprint(f"  [dim]Discovery listener: {e}[/dim]")

        threading.Thread(target=listen_loop, daemon=True).start()

    def _handle_peer(self, payload, ip):
        """Process a discovered peer."""
        peer_id   = payload.get("node_id","")
        peer_name = payload.get("name","")
        caps      = payload.get("capabilities",[])
        sync_port = payload.get("sync_port", SYNC_PORT)

        if not peer_id: return

        now  = datetime.now().isoformat()
        conn = get_db()
        existing = conn.execute("SELECT * FROM peers WHERE id=?", (peer_id,)).fetchone()

        if not existing:
            rprint(f"  [green]New peer found: {peer_name} ({ip})[/green]")
            rprint(f"    Capabilities: {', '.join(caps)}")
            conn.execute("""
                INSERT INTO peers (id,name,ip,port,capabilities,version,first_seen,last_seen,status)
                VALUES (?,?,?,?,?,?,?,?,'online')""",
                (peer_id, peer_name, ip, sync_port,
                 json.dumps(caps), payload.get("protocol",""),
                 now, now)
            )
            if self.on_peer_found:
                self.on_peer_found({"id":peer_id,"name":peer_name,"ip":ip,"capabilities":caps})
        else:
            conn.execute(
                "UPDATE peers SET last_seen=?,status='online',ip=? WHERE id=?",
                (now, ip, peer_id)
            )
        conn.commit(); conn.close()

    def probe_peer(self, ip, port=SYNC_PORT):
        """Manually probe a specific IP for FORGE."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((ip, port))
            msg  = json.dumps({"type":"PROBE","node_id":NODE_ID,"name":f"FORGE-{NODE_ID}"})
            sock.sendall(msg.encode() + b"\n")
            resp = sock.recv(4096)
            sock.close()
            payload = json.loads(resp.decode())
            if payload.get("type") == "PROBE_ACK":
                self._handle_peer(payload, ip)
                return True
        except Exception:
            pass
        return False

    def stop(self):
        self.running = False

    def get_online_peers(self):
        conn  = get_db()
        peers = conn.execute(
            "SELECT * FROM peers WHERE status='online' ORDER BY last_seen DESC"
        ).fetchall()
        conn.close()
        return [dict(p) for p in peers]

# ══════════════════════════════════════════════════════════════════════════════
# 🔄 INTELLIGENCE SYNC
# ══════════════════════════════════════════════════════════════════════════════

class IntelligenceSync:
    """Sync forge_memory between FORGE nodes."""

    def __init__(self):
        self.memory  = Memory()
        self.running = False

    def start_sync_server(self):
        """Listen for incoming sync requests."""
        self.running = True

        def server_loop():
            try:
                srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind(("0.0.0.0", SYNC_PORT))
                srv.listen(5)
                srv.settimeout(2.0)
                while self.running:
                    try:
                        conn, addr = srv.accept()
                        threading.Thread(
                            target=self._handle_connection,
                            args=(conn, addr[0]),
                            daemon=True
                        ).start()
                    except socket.timeout:
                        pass
                srv.close()
            except Exception as e:
                rprint(f"  [dim]Sync server: {e}[/dim]")

        threading.Thread(target=server_loop, daemon=True).start()
        rprint(f"  [dim]Sync server on TCP:{SYNC_PORT}[/dim]")

    def _handle_connection(self, conn, peer_ip):
        """Handle incoming sync connection."""
        try:
            conn.settimeout(10)
            raw  = b""
            while True:
                chunk = conn.recv(65536)
                if not chunk: break
                raw += chunk
                if raw.endswith(b"\n"): break

            msg = json.loads(raw.decode().strip())
            msg_type = msg.get("type","")

            if msg_type == "PROBE":
                # Respond with our info
                active_caps = [c for c in CAPABILITIES if Path(f"forge_{c}.py").exists()]
                resp = json.dumps({
                    "type":        "PROBE_ACK",
                    "node_id":     NODE_ID,
                    "name":        f"FORGE-{NODE_ID}",
                    "sync_port":   SYNC_PORT,
                    "api_port":    API_PORT,
                    "capabilities":active_caps,
                })
                conn.sendall(resp.encode())

            elif msg_type == "SYNC_PUSH":
                # Incoming entities from peer
                count = self._receive_entities(msg.get("entities",[]), msg.get("from_node","?"))
                resp  = json.dumps({"type":"SYNC_ACK","received":count})
                conn.sendall(resp.encode())

            elif msg_type == "SYNC_PULL":
                # Peer wants our entities
                entities = self._export_entities(
                    since=msg.get("since",""),
                    limit=msg.get("limit",100)
                )
                resp = json.dumps({"type":"SYNC_DATA","entities":entities,"node_id":NODE_ID})
                conn.sendall(resp.encode())

            elif msg_type == "ALERT":
                # Incoming threat alert
                self._handle_alert(msg, peer_ip)
                resp = json.dumps({"type":"ALERT_ACK"})
                conn.sendall(resp.encode())

        except Exception as e:
            pass
        finally:
            conn.close()

    def _export_entities(self, since="", limit=100):
        """Export our memory entities for sharing."""
        if not MEMORY: return []
        entities = self.memory.top_risk_entities(limit)
        exported = []
        for ent in entities:
            data = self.memory.recall(ent.get("value",""))
            if data:
                exported.append({
                    "value":       ent.get("value",""),
                    "type":        ent.get("type",""),
                    "risk_score":  ent.get("risk_score",0),
                    "first_seen":  ent.get("first_seen",""),
                    "facts":       [
                        {
                            "fact_type":  f.get("fact_type",""),
                            "fact_value": f.get("fact_value",""),
                            "confidence": f.get("confidence",0.5),
                            "source":     f.get("source",""),
                        }
                        for f in data.get("facts",[])[:5]
                    ],
                })
        return exported

    def _receive_entities(self, entities, from_node):
        """Import entities from a peer into our memory."""
        if not MEMORY: return 0
        count = 0
        for ent in entities:
            value = ent.get("value","")
            if not value: continue
            for fact in ent.get("facts",[]):
                self.memory.remember(
                    value,
                    fact.get("fact_type","peer_shared"),
                    fact.get("fact_value",""),
                    confidence=fact.get("confidence",0.5) * 0.9,  # slight discount for peer data
                    source=f"peer:{from_node}",
                    module="forge_collab"
                )
            count += 1

        # Log sync
        conn = get_db()
        conn.execute("""
            INSERT INTO sync_log (ts,peer_id,direction,entities,status)
            VALUES (?,?,?,?,'ok')""",
            (datetime.now().isoformat(), from_node, "recv", count)
        )
        conn.commit(); conn.close()
        return count

    def _handle_alert(self, msg, peer_ip):
        """Handle incoming threat alert from peer."""
        entity    = msg.get("entity","")
        fact_type = msg.get("fact_type","peer_alert")
        confidence= msg.get("confidence",0.8)
        from_node = msg.get("from_node","?")
        description = msg.get("description","")

        rprint(f"\n  [red bold]ALERT from {from_node} ({peer_ip})[/red bold]")
        rprint(f"  Entity:  {entity}")
        rprint(f"  Type:    {fact_type}")
        rprint(f"  Detail:  {description[:80]}")

        if MEMORY and entity:
            self.memory.remember(
                entity, fact_type, description,
                confidence=confidence,
                source=f"peer_alert:{from_node}",
                module="forge_collab",
                severity="alert"
            )

    def push_to_peer(self, peer_ip, peer_port=SYNC_PORT, limit=50):
        """Push our intelligence to a specific peer."""
        entities = self._export_entities(limit=limit)
        if not entities:
            return {"ok":False,"reason":"no entities to share"}

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((peer_ip, peer_port))
            msg  = json.dumps({
                "type":      "SYNC_PUSH",
                "from_node": NODE_ID,
                "entities":  entities,
            }) + "\n"
            sock.sendall(msg.encode())
            resp = json.loads(sock.recv(4096).decode())
            sock.close()
            received = resp.get("received",0)
            rprint(f"  [green]Pushed {len(entities)} entities to {peer_ip} — peer stored {received}[/green]")

            # Log
            conn = get_db()
            conn.execute("""
                INSERT INTO sync_log (ts,peer_id,direction,entities,status)
                VALUES (?,?,?,?,'ok')""",
                (datetime.now().isoformat(), peer_ip, "push", len(entities))
            )
            conn.commit(); conn.close()
            return {"ok":True,"pushed":len(entities),"peer_stored":received}

        except Exception as e:
            return {"ok":False,"reason":str(e)}

    def pull_from_peer(self, peer_ip, peer_port=SYNC_PORT):
        """Pull intelligence from a specific peer."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(15)
            sock.connect((peer_ip, peer_port))
            msg  = json.dumps({
                "type":      "SYNC_PULL",
                "from_node": NODE_ID,
                "limit":     100,
            }) + "\n"
            sock.sendall(msg.encode())

            raw = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk: break
                raw += chunk
            sock.close()

            resp     = json.loads(raw.decode())
            entities = resp.get("entities",[])
            from_id  = resp.get("node_id","?")
            count    = self._receive_entities(entities, from_id)
            rprint(f"  [green]Pulled {count} entities from {peer_ip}[/green]")
            return {"ok":True,"received":count}

        except Exception as e:
            return {"ok":False,"reason":str(e)}

    def sync_all(self):
        """Sync with all known online peers."""
        peers = NodeDiscovery().get_online_peers()
        if not peers:
            rprint("  [dim]No online peers to sync with[/dim]")
            return

        rprint(f"  [yellow]Syncing with {len(peers)} peers...[/yellow]")
        for peer in peers:
            ip   = peer.get("ip","")
            port = peer.get("port", SYNC_PORT)
            name = peer.get("name","?")
            rprint(f"  → {name} ({ip})")

            # Push ours, pull theirs
            self.push_to_peer(ip, port)
            self.pull_from_peer(ip, port)

    def stop(self):
        self.running = False

# ══════════════════════════════════════════════════════════════════════════════
# 📢 BROADCAST ALERTS
# ══════════════════════════════════════════════════════════════════════════════

class AlertBroadcaster:
    """Broadcast critical findings to all FORGE nodes instantly."""

    def __init__(self):
        self.running  = False
        self.handlers = []  # callbacks for incoming alerts

    def broadcast(self, entity, fact_type, description, confidence=0.9, severity="alert"):
        """Broadcast a threat alert to all nodes."""
        msg = json.dumps({
            "type":        "ALERT",
            "from_node":   NODE_ID,
            "entity":      entity,
            "fact_type":   fact_type,
            "description": description[:500],
            "confidence":  confidence,
            "severity":    severity,
            "ts":          datetime.now().isoformat(),
        }).encode()

        peers = NodeDiscovery().get_online_peers()
        sent  = 0

        # UDP broadcast (fast, best-effort)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(msg, ("<broadcast>", BROADCAST_PORT))
            sock.close()
        except: pass

        # TCP to known peers (reliable)
        for peer in peers:
            ip   = peer.get("ip","")
            port = peer.get("port", SYNC_PORT)
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                sock.connect((ip, port))
                sock.sendall(msg + b"\n")
                sock.recv(256)
                sock.close()
                sent += 1
            except: pass

        rprint(f"  [yellow]Alert broadcast: {entity} — {fact_type} → {sent} peers[/yellow]")

        # Log
        conn = get_db()
        conn.execute("""
            INSERT INTO messages (ts,from_node,msg_type,payload,delivered)
            VALUES (?,?,?,?,?)""",
            (datetime.now().isoformat(), NODE_ID, "ALERT",
             json.dumps({"entity":entity,"fact_type":fact_type,"description":description}),
             sent)
        )
        conn.commit(); conn.close()
        return sent

    def listen(self):
        """Listen for broadcast alerts from other nodes."""
        self.running = True

        def listen_loop():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("", BROADCAST_PORT))
                sock.settimeout(2.0)
                while self.running:
                    try:
                        data, addr = sock.recvfrom(65536)
                        msg = json.loads(data.decode())
                        if msg.get("from_node") != NODE_ID:
                            self._handle_broadcast(msg, addr[0])
                    except socket.timeout: pass
                    except Exception: pass
                sock.close()
            except Exception as e:
                pass

        threading.Thread(target=listen_loop, daemon=True).start()

    def _handle_broadcast(self, msg, from_ip):
        """Handle received broadcast."""
        from_node   = msg.get("from_node","?")
        entity      = msg.get("entity","")
        fact_type   = msg.get("fact_type","")
        description = msg.get("description","")
        confidence  = msg.get("confidence",0.8)

        rprint(f"\n  [red]BROADCAST ALERT from {from_node}[/red]")
        rprint(f"  [{entity}] {fact_type}: {description[:80]}")

        if MEMORY and entity:
            self.memory.remember(
                entity, fact_type, description,
                confidence=confidence * 0.9,
                source=f"broadcast:{from_node}",
                module="forge_collab"
            )

        for handler in self.handlers:
            try: handler(msg)
            except: pass

    def stop(self):
        self.running = False

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 DISTRIBUTED REASONING
# ══════════════════════════════════════════════════════════════════════════════

class DistributedReasoner:
    """Multiple FORGE nodes working one case together."""

    def __init__(self):
        self.memory = Memory()

    def assign_task(self, peer_ip, task_type, target, peer_port=API_PORT):
        """Tell a peer node to investigate something."""
        try:
            import urllib.request
            payload = json.dumps({
                "task":      task_type,
                "target":    target,
                "requestor": NODE_ID,
            }).encode()
            req = urllib.request.Request(
                f"http://{peer_ip}:{peer_port}/api/task",
                data=payload,
                headers={"Content-Type":"application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())
        except Exception as e:
            return {"ok":False,"error":str(e)}

    def collective_analysis(self, entity):
        """Analyze entity using data from ALL nodes."""
        peers   = NodeDiscovery().get_online_peers()
        results = []

        # Our own memory
        if MEMORY:
            local = self.memory.recall(entity)
            if local:
                results.append({
                    "node":   NODE_ID,
                    "local":  True,
                    "data":   local,
                })

        # Pull from peers
        sync = IntelligenceSync()
        for peer in peers:
            ip   = peer.get("ip","")
            port = peer.get("port", SYNC_PORT)
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((ip, port))
                msg  = json.dumps({
                    "type":   "ENTITY_QUERY",
                    "entity": entity,
                    "node_id":NODE_ID,
                }) + "\n"
                sock.sendall(msg.encode())
                raw = sock.recv(65536)
                sock.close()
                resp = json.loads(raw.decode())
                if resp.get("data"):
                    results.append({
                        "node":  peer.get("name","?"),
                        "local": False,
                        "data":  resp["data"],
                    })
            except: pass

        # AI synthesis across all node data
        if AI_AVAILABLE and results:
            nodes_txt = "\n\n".join(
                f"Node {r['node']} ({'local' if r['local'] else 'peer'}):\n"
                + json.dumps(r["data"].get("summary",r["data"]), default=str)[:400]
                for r in results
            )
            analysis = ai_call(
                f"Collective intelligence analysis for: {entity}\n\n"
                f"Data from {len(results)} FORGE nodes:\n{nodes_txt}\n\n"
                "What does the combined picture reveal?\n"
                "What can we see now that no single node could see alone?\n"
                "Sherlock-style synthesis.",
                max_tokens=600
            )
            return {"entity":entity,"nodes":len(results),"analysis":analysis,"raw":results}

        return {"entity":entity,"nodes":len(results),"raw":results}

    def consensus_score(self, entity, fact_type):
        """
        Get consensus threat score across all nodes.
        An entity confirmed by multiple nodes = higher confidence.
        """
        peers  = NodeDiscovery().get_online_peers()
        scores = []

        if MEMORY:
            local = self.memory.seen_before(entity)
            if local:
                for fact in local.get("fact_types",[]):
                    if fact.get("fact_type") == fact_type:
                        scores.append(fact.get("max_conf",0))

        # Would query peers in production — for now use local count as proxy
        seen_count = len(scores)
        if not scores: return {"consensus":0.0,"nodes_confirming":0}

        avg_conf   = sum(scores) / len(scores)
        # Boost confidence when multiple nodes agree
        boosted    = min(avg_conf * (1 + seen_count * 0.1), 1.0)

        return {
            "entity":            entity,
            "fact_type":         fact_type,
            "consensus":         round(boosted, 3),
            "nodes_confirming":  seen_count,
            "base_confidence":   round(avg_conf, 3),
        }

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 COLLAB UI
# ══════════════════════════════════════════════════════════════════════════════

COLLAB_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FORGE COLLAB</title>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Bebas+Neue&display=swap" rel="stylesheet">
<style>
:root{--bg:#04080f;--panel:#080d1a;--border:#101828;--green:#00ff88;--gd:#005c33;--amber:#ff9500;--red:#ff2244;--blue:#0088ff;--dim:#1e2a3a;--text:#7a9ab0;--head:#d0e4f8}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);font-family:'Share Tech Mono',monospace;color:var(--text);height:100vh;display:grid;grid-template-rows:48px 1fr 32px;grid-template-columns:260px 1fr 280px;overflow:hidden}
header{grid-column:1/-1;background:rgba(4,8,15,.98);border-bottom:1px solid var(--gd);display:flex;align-items:center;padding:0 16px;gap:14px}
.logo{font-family:'Bebas Neue';font-size:20px;letter-spacing:7px;color:var(--green)}
.hdr-stat{font-size:9px;letter-spacing:2px;color:var(--dim)}
.hdr-stat span{color:var(--green)}
.pulse{width:7px;height:7px;border-radius:50%;background:var(--green);animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:1;box-shadow:0 0 4px var(--green)}50%{opacity:.3}}
/* PEERS PANEL */
.peers-panel{background:var(--panel);border-right:1px solid var(--border);overflow-y:auto}
.panel-title{font-size:8px;letter-spacing:3px;color:var(--gd);padding:10px 12px 6px;border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--panel)}
.peer-card{padding:10px 12px;border-bottom:1px solid var(--border)}
.pc-name{font-size:12px;color:var(--green)}
.pc-ip{font-size:10px;color:var(--head)}
.pc-caps{font-size:9px;color:var(--dim);margin-top:2px}
.pc-status{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:6px}
.online{background:var(--green)}
.offline{background:var(--dim)}
/* THIS NODE */
.this-node{background:rgba(0,255,136,.05);border-bottom:2px solid var(--gd)}
/* CENTER */
.center{background:var(--bg);padding:20px;overflow-y:auto}
.node-map{display:flex;flex-wrap:wrap;gap:16px;margin-bottom:24px}
.node-box{background:var(--panel);border:1px solid var(--border);padding:14px;min-width:180px;flex:1;position:relative}
.node-box.this{border-color:var(--gd)}
.nb-name{font-family:'Bebas Neue';font-size:16px;letter-spacing:3px;color:var(--green)}
.nb-id{font-size:9px;color:var(--dim);margin-bottom:8px}
.nb-stat{display:flex;justify-content:space-between;font-size:9px;padding:2px 0;border-bottom:1px solid var(--dim)}
.nb-key{color:var(--dim)}
.nb-val{color:var(--head)}
.nb-badge{position:absolute;top:8px;right:8px;font-size:8px;padding:2px 6px;letter-spacing:1px}
.badge-online{background:rgba(0,255,136,.15);color:var(--green);border:1px solid var(--gd)}
.badge-offline{background:rgba(30,42,58,.5);color:var(--dim);border:1px solid var(--dim)}
.sec-title{font-size:8px;letter-spacing:3px;color:var(--gd);margin-bottom:10px}
/* MESSAGES */
.right-panel{background:var(--panel);border-left:1px solid var(--border);overflow-y:auto}
.msg-item{padding:10px 12px;border-bottom:1px solid var(--border)}
.msg-type{font-size:9px;letter-spacing:1px;color:var(--head);margin-bottom:2px}
.msg-body{font-size:9px;color:var(--text);line-height:1.5}
.msg-meta{font-size:8px;color:var(--dim);margin-top:3px}
.msg-item.alert{border-left:3px solid var(--red)}
.msg-item.sync{border-left:3px solid var(--blue)}
.msg-item.discovery{border-left:3px solid var(--green)}
/* ACTIONS */
.action-bar{background:var(--panel);border:1px solid var(--border);padding:12px;margin-bottom:16px;display:flex;gap:8px;flex-wrap:wrap}
.btn{font-family:'Share Tech Mono';font-size:9px;letter-spacing:2px;padding:7px 12px;border:1px solid;background:transparent;cursor:pointer;text-transform:uppercase}
.btn-g{color:var(--green);border-color:var(--gd)} .btn-g:hover{background:rgba(0,255,136,.1)}
.btn-r{color:var(--red);border-color:rgba(255,34,68,.3)} .btn-r:hover{background:rgba(255,34,68,.1)}
.btn-b{color:var(--blue);border-color:rgba(0,136,255,.3)} .btn-b:hover{background:rgba(0,136,255,.1)}
input.peer-input{background:rgba(0,0,0,.4);border:1px solid var(--border);color:var(--head);font-family:'Share Tech Mono';font-size:10px;padding:6px 8px;flex:1;outline:none}
input.peer-input:focus{border-color:var(--gd)}
/* STATUS BAR */
.status-bar{grid-column:1/-1;background:rgba(0,0,0,.9);border-top:1px solid var(--border);display:flex;align-items:center;padding:0 14px;gap:18px;font-size:9px;color:var(--dim)}
.sb-val{color:var(--green)}
</style>
</head>
<body>
<header>
  <div class="logo">COLLAB</div>
  <div class="pulse" id="pulse"></div>
  <div class="hdr-stat">THIS NODE <span id="h-nodeid">--</span></div>
  <div class="hdr-stat">PEERS <span id="h-peers">0</span></div>
  <div class="hdr-stat">SYNCED <span id="h-synced">0</span></div>
  <div class="hdr-stat">ALERTS <span id="h-alerts">0</span></div>
  <div style="flex:1"></div>
  <div class="hdr-stat" id="h-status">ONLINE</div>
</header>

<div class="peers-panel">
  <div class="panel-title">FORGE NODES</div>
  <div id="peer-list"></div>
</div>

<div class="center">
  <div class="action-bar">
    <button class="btn btn-b" onclick="syncAll()">SYNC ALL</button>
    <button class="btn btn-g" onclick="discoverPeers()">DISCOVER</button>
    <input class="peer-input" id="peer-ip" placeholder="192.168.1.x">
    <button class="btn btn-g" onclick="addPeer()">ADD PEER</button>
    <button class="btn btn-r" onclick="broadcastTest()">TEST ALERT</button>
  </div>

  <div class="sec-title">NODE MAP</div>
  <div class="node-map" id="node-map"></div>

  <div class="sec-title">SHARED INTELLIGENCE</div>
  <div id="shared-intel"></div>
</div>

<div class="right-panel">
  <div class="panel-title">MESSAGE FEED</div>
  <div id="msg-feed"></div>
</div>

<div class="status-bar">
  <span>FORGE COLLAB</span>
  <span>SYNC PORT: <span class="sb-val">47772</span></span>
  <span>DISCOVERY: <span class="sb-val">47771</span></span>
  <span>BROADCAST: <span class="sb-val">47773</span></span>
</div>

<script>
const API = 'http://localhost:7350';
let myNodeId = '--';

async function refresh() {
  try {
    const [status, peers, msgs] = await Promise.all([
      fetch(API+'/api/status').then(r=>r.json()),
      fetch(API+'/api/peers').then(r=>r.json()),
      fetch(API+'/api/messages').then(r=>r.json()),
    ]);

    myNodeId = status.node_id || '--';
    document.getElementById('h-nodeid').textContent = myNodeId;
    document.getElementById('h-peers').textContent  = (peers.peers||[]).length;
    document.getElementById('h-synced').textContent = status.total_synced || 0;
    document.getElementById('h-alerts').textContent = status.total_alerts || 0;

    renderPeers(peers.peers||[], status);
    renderNodeMap(peers.peers||[], status);
    renderMessages(msgs.messages||[]);
    renderSharedIntel(status);
  } catch(e) {}
}

function renderPeers(peers, status) {
  const list = document.getElementById('peer-list');

  // This node first
  let html = `<div class="peer-card this-node">
    <div class="pc-name"><span class="pc-status online"></span>${status.node_name||'This Node'}</div>
    <div class="pc-ip">${status.node_id||'--'} (LOCAL)</div>
    <div class="pc-caps">${(status.capabilities||[]).join(' · ')}</div>
  </div>`;

  html += peers.map(p => `
    <div class="peer-card">
      <div class="pc-name">
        <span class="pc-status ${p.status==='online'?'online':'offline'}"></span>
        ${p.name||p.id}
      </div>
      <div class="pc-ip">${p.ip}:${p.port||47772}</div>
      <div class="pc-caps">${JSON.parse(p.capabilities||'[]').join(' · ')||'unknown'}</div>
    </div>`).join('');

  list.innerHTML = html;
}

function renderNodeMap(peers, status) {
  const map    = document.getElementById('node-map');
  const myNode = `
    <div class="node-box this">
      <div class="nb-badge badge-online">THIS NODE</div>
      <div class="nb-name">${status.node_name||'LOCAL'}</div>
      <div class="nb-id">${status.node_id||'--'}</div>
      <div class="nb-stat"><span class="nb-key">Status</span><span class="nb-val" style="color:var(--green)">ONLINE</span></div>
      <div class="nb-stat"><span class="nb-key">Memory</span><span class="nb-val">${status.memory_entities||0} entities</span></div>
      <div class="nb-stat"><span class="nb-key">Modules</span><span class="nb-val">${(status.capabilities||[]).length}</span></div>
    </div>`;

  const peerNodes = peers.map(p => {
    const caps = JSON.parse(p.capabilities||'[]');
    return `
    <div class="node-box">
      <div class="nb-badge ${p.status==='online'?'badge-online':'badge-offline'}">${(p.status||'UNKNOWN').toUpperCase()}</div>
      <div class="nb-name">${p.name||p.id}</div>
      <div class="nb-id">${p.ip}</div>
      <div class="nb-stat"><span class="nb-key">Last seen</span><span class="nb-val">${(p.last_seen||'?').slice(11,19)}</span></div>
      <div class="nb-stat"><span class="nb-key">Shared</span><span class="nb-val">${p.entities_shared||0} entities</span></div>
      <div class="nb-stat"><span class="nb-key">Caps</span><span class="nb-val">${caps.length}</span></div>
    </div>`;
  }).join('');

  map.innerHTML = myNode + peerNodes;
}

function renderMessages(messages) {
  const feed = document.getElementById('msg-feed');
  feed.innerHTML = [...messages].reverse().slice(0,30).map(m => {
    const cls = m.msg_type==='ALERT'?'alert':m.msg_type==='SYNC_PUSH'?'sync':'discovery';
    return `
    <div class="msg-item ${cls}">
      <div class="msg-type">${m.msg_type||'MSG'}</div>
      <div class="msg-body">${(m.payload||'').slice(0,80)}</div>
      <div class="msg-meta">${m.from_node||'?'} · ${(m.ts||'').slice(11,19)} · delivered:${m.delivered||0}</div>
    </div>`;
  }).join('');
}

function renderSharedIntel(status) {
  const div   = document.getElementById('shared-intel');
  const ents  = status.top_entities || [];
  if (!ents.length) { div.innerHTML = '<div style="color:var(--dim);font-size:9px">No shared intelligence yet.</div>'; return; }
  div.innerHTML = ents.slice(0,6).map(e => `
    <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);font-size:10px">
      <span style="color:var(--green)">${e.value||'?'}</span>
      <span style="color:var(--dim)">${e.type||''}</span>
      <span style="color:${e.risk_score>70?'var(--red)':e.risk_score>40?'var(--amber)':'var(--head)'}">${(e.risk_score||0).toFixed(0)}/100</span>
    </div>`).join('');
}

async function syncAll() {
  const r = await fetch(API+'/api/sync', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({})}).then(r=>r.json());
  addFeedItem('SYNC', `Synced with ${r.peers_synced||0} peers`);
  setTimeout(refresh, 1000);
}

async function discoverPeers() {
  fetch(API+'/api/discover', {method:'POST'});
  addFeedItem('DISCOVERY', 'Broadcast sent — listening for peers...');
}

async function addPeer() {
  const ip = document.getElementById('peer-ip').value.trim();
  if (!ip) return;
  const r = await fetch(API+'/api/peer/add', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ip})
  }).then(r=>r.json());
  addFeedItem('DISCOVERY', r.ok ? `Peer ${ip} added` : `Failed: ${r.reason}`);
  document.getElementById('peer-ip').value='';
  setTimeout(refresh, 500);
}

async function broadcastTest() {
  await fetch(API+'/api/broadcast', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({entity:'test', fact_type:'collab_test', description:'FORGE COLLAB test broadcast', confidence:0.9})
  });
  addFeedItem('ALERT', 'Test broadcast sent to all peers');
}

function addFeedItem(type, text) {
  const feed = document.getElementById('msg-feed');
  const div  = document.createElement('div');
  div.className = 'msg-item ' + (type==='ALERT'?'alert':type==='SYNC_PUSH'?'sync':'discovery');
  div.innerHTML = `<div class="msg-type">${type}</div><div class="msg-body">${text}</div><div class="msg-meta">LOCAL · ${new Date().toTimeString().slice(0,8)}</div>`;
  feed.prepend(div);
}

setInterval(refresh, 3000);
refresh();
</script>
</body>
</html>"""

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API SERVER
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=API_PORT):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    discovery  = NodeDiscovery()
    sync_eng   = IntelligenceSync()
    broadcaster= AlertBroadcaster()
    reasoner   = DistributedReasoner()
    memory     = Memory()

    # Start background services
    discovery.start_beacon()
    discovery.start_listener()
    sync_eng.start_sync_server()
    broadcaster.listen()

    active_caps = [c for c in CAPABILITIES if Path(f"forge_{c}.py").exists()]

    class CollabAPI(BaseHTTPRequestHandler):
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
            if path in ("/","/index.html"):
                self._html(COLLAB_UI_HTML); return

            if path == "/api/status":
                db       = get_db()
                tot_sync = db.execute("SELECT COALESCE(SUM(entities),0) FROM sync_log WHERE direction='recv'").fetchone()[0]
                tot_alrt = db.execute("SELECT COUNT(*) FROM messages WHERE msg_type='ALERT'").fetchone()[0]
                db.close()
                mem_stats = memory.stats() if MEMORY else {}
                top_ents  = memory.top_risk_entities(6) if MEMORY else []
                self._json({
                    "node_id":        NODE_ID,
                    "node_name":      f"FORGE-{NODE_ID}",
                    "status":         "online",
                    "capabilities":   active_caps,
                    "total_synced":   tot_sync,
                    "total_alerts":   tot_alrt,
                    "memory_entities":mem_stats.get("total_entities",0),
                    "ai":             AI_AVAILABLE,
                    "memory":         MEMORY,
                    "top_entities":   top_ents,
                })

            elif path == "/api/peers":
                peers = discovery.get_online_peers()
                self._json({"peers":peers,"count":len(peers)})

            elif path == "/api/messages":
                db   = get_db()
                rows = db.execute(
                    "SELECT * FROM messages ORDER BY id DESC LIMIT 50"
                ).fetchall()
                db.close()
                self._json({"messages":[dict(r) for r in rows]})

            elif path == "/api/sync_log":
                db   = get_db()
                rows = db.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 20").fetchall()
                db.close()
                self._json({"log":[dict(r) for r in rows]})

            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()

            if path == "/api/sync":
                sync_eng.sync_all()
                peers = discovery.get_online_peers()
                self._json({"ok":True,"peers_synced":len(peers)})

            elif path == "/api/discover":
                discovery.start_beacon(interval=5)
                self._json({"ok":True,"message":"Discovery broadcast started"})

            elif path == "/api/peer/add":
                ip  = body.get("ip","")
                if not ip: self._json({"error":"ip required"},400); return
                ok  = discovery.probe_peer(ip)
                if ok:
                    result = sync_eng.pull_from_peer(ip)
                    self._json({"ok":True,"synced":result.get("received",0)})
                else:
                    self._json({"ok":False,"reason":"Peer not reachable or not FORGE"})

            elif path == "/api/broadcast":
                entity      = body.get("entity","")
                fact_type   = body.get("fact_type","alert")
                description = body.get("description","")
                confidence  = float(body.get("confidence",0.9))
                sent = broadcaster.broadcast(entity,fact_type,description,confidence)
                self._json({"ok":True,"sent_to":sent})

            elif path == "/api/analyze":
                entity   = body.get("entity","")
                if not entity: self._json({"error":"entity required"},400); return
                result   = reasoner.collective_analysis(entity)
                self._json(result)

            elif path == "/api/consensus":
                entity    = body.get("entity","")
                fact_type = body.get("fact_type","")
                result    = reasoner.consensus_score(entity,fact_type)
                self._json(result)

            elif path == "/api/task":
                # Receive a task assignment from another node
                task   = body.get("task","")
                target = body.get("target","")
                req_by = body.get("requestor","?")
                rprint(f"  [dim]Task received from {req_by}: {task} on {target}[/dim]")
                self._json({"ok":True,"accepted":True,"node":NODE_ID})

            else:
                self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),CollabAPI)
    rprint(f"\n  [bold yellow]FORGE COLLAB[/bold yellow]  Node: {NODE_ID}")
    rprint(f"  [green]UI:        http://localhost:{port}[/green]")
    rprint(f"  [green]API:       http://localhost:{port}/api/status[/green]")
    rprint(f"  [dim]Discovery: UDP:{DISCOVERY_PORT}[/dim]")
    rprint(f"  [dim]Sync:      TCP:{SYNC_PORT}[/dim]")
    rprint(f"  [dim]Broadcast: UDP:{BROADCAST_PORT}[/dim]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# 🎮 MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
   ██████╗ ██████╗ ██╗      ██╗      █████╗ ██████╗
  ██╔════╝██╔═══██╗██║      ██║     ██╔══██╗██╔══██╗
  ██║     ██║   ██║██║      ██║     ███████║██████╔╝
  ██║     ██║   ██║██║      ██║     ██╔══██║██╔══██╗
  ╚██████╗╚██████╔╝███████╗ ███████╗██║  ██║██████╔╝
   ╚═════╝ ╚═════╝ ╚══════╝ ╚══════╝╚═╝  ╚═╝╚═════╝
[/yellow]
[bold]  FORGE COLLAB — Distributed Intelligence Network[/bold]
[dim]  One FORGE. Many bodies. One mind.[/dim]
"""

def interactive():
    rprint(BANNER)
    rprint(f"  [dim]Node ID: {NODE_ID}[/dim]")
    rprint(f"  [dim]AI:      {'OK' if AI_AVAILABLE else 'pip install anthropic'}[/dim]")
    rprint(f"  [dim]Memory:  {'OK' if MEMORY else 'forge_memory.py not found'}[/dim]\n")

    discovery   = NodeDiscovery()
    sync_eng    = IntelligenceSync()
    broadcaster = AlertBroadcaster()
    reasoner    = DistributedReasoner()

    rprint("[dim]Commands: start | peers | sync | pull | push | alert | analyze | consensus | server[/dim]\n")

    while True:
        try:
            raw = (console.input if RICH else input)("[yellow bold]COLLAB >[/yellow bold] ").strip()
            if not raw: continue
            parts = raw.split(None,2)
            cmd   = parts[0].lower()
            arg1  = parts[1] if len(parts)>1 else ""
            arg2  = parts[2] if len(parts)>2 else ""

            if cmd in ("quit","exit","q"):
                rprint("[dim]Collab offline.[/dim]"); break

            elif cmd == "start":
                discovery.start_beacon()
                discovery.start_listener()
                sync_eng.start_sync_server()
                broadcaster.listen()
                rprint(f"  [green]Node {NODE_ID} active — discovering peers...[/green]")

            elif cmd == "peers":
                peers = discovery.get_online_peers()
                if not peers:
                    rprint("  [dim]No peers found. Run 'start' to begin discovery.[/dim]")
                else:
                    for p in peers:
                        caps = json.loads(p.get("capabilities","[]"))
                        rprint(f"  [green]{p['name']:<20}[/green] {p['ip']:<18} {', '.join(caps[:3])}")

            elif cmd == "sync":
                sync_eng.sync_all()

            elif cmd == "pull":
                if not arg1: rprint("[yellow]Usage: pull <ip>[/yellow]"); continue
                result = sync_eng.pull_from_peer(arg1)
                rprint(f"  Received: {result.get('received',0)} entities")

            elif cmd == "push":
                if not arg1: rprint("[yellow]Usage: push <ip>[/yellow]"); continue
                result = sync_eng.push_to_peer(arg1)
                rprint(f"  Pushed: {result.get('pushed',0)} entities")

            elif cmd == "alert":
                if not arg1: rprint("[yellow]Usage: alert <entity> [description][/yellow]"); continue
                sent = broadcaster.broadcast(arg1, "manual_alert", arg2 or "Manual alert", 0.9)
                rprint(f"  [yellow]Alert sent to {sent} peers[/yellow]")

            elif cmd == "analyze":
                if not arg1: rprint("[yellow]Usage: analyze <entity>[/yellow]"); continue
                result = reasoner.collective_analysis(arg1)
                rprint(f"  Nodes consulted: {result.get('nodes',0)}")
                if result.get("analysis"):
                    rprint(Panel(result["analysis"][:500], border_style="yellow",
                                title=f"Collective Analysis: {arg1}"))

            elif cmd == "consensus":
                if not arg1 or not arg2:
                    rprint("[yellow]Usage: consensus <entity> <fact_type>[/yellow]"); continue
                result = reasoner.consensus_score(arg1, arg2)
                rprint(f"  Consensus: {result.get('consensus',0):.0%}  "
                      f"Nodes confirming: {result.get('nodes_confirming',0)}")

            elif cmd in ("add","peer"):
                if not arg1: rprint("[yellow]Usage: peer <ip>[/yellow]"); continue
                ok = discovery.probe_peer(arg1)
                rprint(f"  {'[green]Peer added[/green]' if ok else '[red]Not reachable[/red]'}: {arg1}")

            elif cmd == "server":
                rprint("[yellow]Starting COLLAB server on port 7350...[/yellow]")
                threading.Thread(target=start_server, daemon=True).start()
                time.sleep(0.5)
                rprint(f"[green]Live at http://localhost:7350[/green]")

            else:
                rprint("[dim]Unknown. Commands: start | peers | sync | pull | push | alert | analyze | consensus | server[/dim]")

        except (KeyboardInterrupt, EOFError):
            rprint("\n[dim]Collab offline.[/dim]"); break

def main():
    rprint(BANNER)
    rprint(f"  [dim]Node ID: {NODE_ID}[/dim]\n")

    if "--server" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else API_PORT
        start_server(port)
    elif "--start" in sys.argv:
        d = NodeDiscovery(); d.start_beacon(); d.start_listener()
        s = IntelligenceSync(); s.start_sync_server()
        AlertBroadcaster().listen()
        rprint(f"  [green]Node {NODE_ID} active[/green]")
        try:
            while True: time.sleep(5)
        except KeyboardInterrupt:
            rprint("\n[dim]Node offline.[/dim]")
    elif "--peer" in sys.argv:
        ip = sys.argv[sys.argv.index("--peer")+1]
        ok = NodeDiscovery().probe_peer(ip)
        rprint(f"  Peer {ip}: {'found' if ok else 'not reachable'}")
    elif "--sync" in sys.argv:
        IntelligenceSync().sync_all()
    elif "--status" in sys.argv:
        peers = NodeDiscovery().get_online_peers()
        rprint(f"  Peers: {len(peers)}")
        for p in peers:
            rprint(f"    {p['name']} ({p['ip']}) — {p['status']}")
    elif "--broadcast" in sys.argv:
        idx  = sys.argv.index("--broadcast")
        msg  = sys.argv[idx+1] if idx+1 < len(sys.argv) else "test"
        sent = AlertBroadcaster().broadcast("manual", "broadcast", msg)
        rprint(f"  Sent to {sent} peers")
    else:
        interactive()

if __name__ == "__main__":
    main()
