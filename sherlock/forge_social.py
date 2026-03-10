#!/usr/bin/env python3
"""
FORGE SOCIAL — Social Graph Intelligence Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Map who knows who. Find hidden connections.
Trace narratives. Expose fake networks.

Modules:
  🕸️  Graph Engine        → relationship graphs, weighted edges, communities
  🔍 Social OSINT        → GitHub, Reddit, HackerNews, domain chains
  🧠 Sherlock Analysis   → AI reads social graphs like crime scenes
  👥 Persona Profiler    → writing style, posting patterns, alt accounts
  🎭 Fake Detector       → bots, coordinated behavior, follower farms
  🌊 Influence Tracker   → trace origin + spread of any narrative
  🔗 Connection Finder   → 6 degrees, shortest path, hidden links
  🌐 Graph UI            → d3.js force-directed interactive graph

Usage:
  python forge_social.py                          # interactive
  python forge_social.py --profile <username>     # profile someone
  python forge_social.py --graph <username>       # build social graph
  python forge_social.py --connect A B            # find connection between two
  python forge_social.py --fake <username>        # fake account analysis
  python forge_social.py --github <username>      # GitHub network
  python forge_social.py --server                 # API + live graph UI :7347
"""

import sys, os, re, json, time, hashlib, sqlite3, threading
import urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime
from collections import defaultdict, deque

# ── Optional deps ──────────────────────────────────────────────────────────────
try:
    import requests
    REQUESTS = True
except ImportError:
    REQUESTS = False

# ── AI ─────────────────────────────────────────────────────────────────────────
try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True

    def ai_call(prompt, system="", max_tokens=1500):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or SOCIAL_SYSTEM,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text

    def ai_json(prompt, system="", max_tokens=800):
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
    def ai_json(p,s="",m=800): return None

# ── Rich ────────────────────────────────────────────────────────────────────────
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

# ── System prompt ───────────────────────────────────────────────────────────────
SOCIAL_SYSTEM = """You are FORGE SOCIAL — a social network intelligence analyst.

You read social graphs the way Holmes reads a crime scene.
Every connection is a clue. Every pattern tells a story.

Your analysis format:
OBSERVATION: [what the graph/data shows]
  → INFERENCE: [what this pattern means]
    → CONCLUSION: [finding] [confidence%]
    → SIGNIFICANCE: [why this matters]

You understand:
- Normal social graph properties (scale-free, small world)
- Bot/fake account signatures (age, activity, ratio anomalies)
- Coordinated inauthentic behavior (synchronized posting, follower farms)
- Hidden connector nodes (bridge between communities)
- Influence cascade patterns (how narratives spread)
- Alt account fingerprints (writing style, timing, topic overlap)

Always be specific. Name the pattern. Give confidence. Show evidence."""

# ── Paths ───────────────────────────────────────────────────────────────────────
SOCIAL_DIR   = Path("forge_social")
GRAPHS_DIR   = SOCIAL_DIR / "graphs"
PROFILES_DIR = SOCIAL_DIR / "profiles"
CACHE_DIR    = SOCIAL_DIR / "cache"
DB_PATH      = SOCIAL_DIR / "social.db"

for d in [SOCIAL_DIR, GRAPHS_DIR, PROFILES_DIR, CACHE_DIR]:
    d.mkdir(exist_ok=True)

# ── Database ────────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS entities (
            id           TEXT PRIMARY KEY,
            name         TEXT,
            platform     TEXT,
            username     TEXT,
            url          TEXT,
            followers    INTEGER DEFAULT 0,
            following    INTEGER DEFAULT 0,
            posts        INTEGER DEFAULT 0,
            created      TEXT,
            bio          TEXT,
            location     TEXT,
            verified     INTEGER DEFAULT 0,
            bot_score    REAL DEFAULT 0,
            influence    REAL DEFAULT 0,
            community    TEXT,
            first_seen   TEXT,
            last_updated TEXT,
            raw_data     TEXT
        );
        CREATE TABLE IF NOT EXISTS edges (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            src          TEXT,
            dst          TEXT,
            relation     TEXT,
            weight       REAL DEFAULT 1.0,
            platform     TEXT,
            ts           TEXT,
            UNIQUE(src,dst,relation)
        );
        CREATE TABLE IF NOT EXISTS posts (
            id           TEXT PRIMARY KEY,
            entity_id    TEXT,
            platform     TEXT,
            content      TEXT,
            ts           TEXT,
            likes        INTEGER DEFAULT 0,
            shares       INTEGER DEFAULT 0,
            replies      INTEGER DEFAULT 0,
            url          TEXT,
            sentiment    REAL DEFAULT 0,
            topics       TEXT
        );
        CREATE TABLE IF NOT EXISTS investigations (
            id           TEXT PRIMARY KEY,
            target       TEXT,
            ts           TEXT,
            findings     TEXT,
            graph_data   TEXT,
            verdict      TEXT
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 🕸️ GRAPH ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class SocialGraph:
    """
    Core graph data structure.
    Nodes = entities (people, orgs, accounts)
    Edges = relationships (follows, collaborates, mentions)
    """

    def __init__(self, name="default"):
        self.name     = name
        self.nodes    = {}   # id → {name, platform, attrs...}
        self.edges    = []   # [{src, dst, relation, weight, ts}]
        self.adj      = defaultdict(set)   # adjacency list
        self.radj     = defaultdict(set)   # reverse adjacency
        self.communities = {}  # node_id → community_id

    def add_node(self, node_id, **attrs):
        """Add entity to graph."""
        if node_id not in self.nodes:
            self.nodes[node_id] = {"id":node_id, **attrs}
        else:
            self.nodes[node_id].update(attrs)
        return self.nodes[node_id]

    def add_edge(self, src, dst, relation="follows", weight=1.0, platform="", ts=""):
        """Add relationship between two entities."""
        edge = {
            "src":      src,
            "dst":      dst,
            "relation": relation,
            "weight":   weight,
            "platform": platform,
            "ts":       ts or datetime.now().isoformat(),
        }
        # Deduplicate
        key = (src, dst, relation)
        if key not in {(e["src"],e["dst"],e["relation"]) for e in self.edges}:
            self.edges.append(edge)
            self.adj[src].add(dst)
            self.radj[dst].add(src)
        return edge

    def neighbors(self, node_id, direction="out"):
        """Get neighbors of a node."""
        if direction == "out":
            return set(self.adj.get(node_id, set()))
        elif direction == "in":
            return set(self.radj.get(node_id, set()))
        else:
            return self.adj.get(node_id,set()) | self.radj.get(node_id,set())

    def degree(self, node_id):
        """Degree centrality metrics."""
        out_ = len(self.adj.get(node_id, set()))
        in_  = len(self.radj.get(node_id, set()))
        return {"out": out_, "in": in_, "total": out_+in_}

    def shortest_path(self, src, dst):
        """BFS shortest path between two nodes."""
        if src not in self.nodes or dst not in self.nodes:
            return None
        if src == dst:
            return [src]

        visited = {src}
        queue   = deque([[src]])

        while queue:
            path = queue.popleft()
            node = path[-1]
            for neighbor in self.adj.get(node, set()) | self.radj.get(node, set()):
                if neighbor == dst:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])
        return None

    def common_neighbors(self, a, b):
        """Find nodes connected to both a and b."""
        a_neighbors = self.adj.get(a,set()) | self.radj.get(a,set())
        b_neighbors = self.adj.get(b,set()) | self.radj.get(b,set())
        return a_neighbors & b_neighbors

    def detect_communities(self):
        """Simple community detection via connected components."""
        visited    = set()
        community  = 0
        components = {}

        def dfs(node, cid):
            visited.add(node)
            components[node] = cid
            for neighbor in self.adj.get(node,set()) | self.radj.get(node,set()):
                if neighbor not in visited:
                    dfs(neighbor, cid)

        for node in self.nodes:
            if node not in visited:
                dfs(node, community)
                community += 1

        self.communities = components

        # Count sizes
        sizes = defaultdict(int)
        for cid in components.values():
            sizes[cid] += 1
        return components, dict(sizes)

    def influence_scores(self):
        """
        Simple PageRank-like influence score.
        Nodes with many in-edges from influential nodes = high score.
        """
        scores  = {n: 1.0 for n in self.nodes}
        damping = 0.85
        iters   = 20

        for _ in range(iters):
            new_scores = {}
            for node in self.nodes:
                in_neighbors = self.radj.get(node, set())
                rank = (1 - damping)
                for src in in_neighbors:
                    out_degree = max(len(self.adj.get(src,set())), 1)
                    rank += damping * (scores.get(src, 1.0) / out_degree)
                new_scores[node] = rank
            scores = new_scores

        # Normalize 0-100
        max_score = max(scores.values()) if scores else 1
        return {n: round(s/max_score*100, 1) for n,s in scores.items()}

    def top_influencers(self, n=10):
        """Get top N most influential nodes."""
        scores = self.influence_scores()
        return sorted(scores.items(), key=lambda x:-x[1])[:n]

    def bridge_nodes(self):
        """
        Find bridge nodes — removing them disconnects the graph.
        These are key connectors between communities.
        """
        bridges = []
        for node in self.nodes:
            # Nodes that connect different communities
            neighbors = self.adj.get(node,set()) | self.radj.get(node,set())
            comms = {self.communities.get(n) for n in neighbors if n in self.communities}
            if len(comms) > 1:
                bridges.append({
                    "node":       node,
                    "name":       self.nodes[node].get("name", node),
                    "communities":len(comms),
                    "connections":len(neighbors),
                })
        return sorted(bridges, key=lambda x:-x["communities"])

    def to_dict(self):
        """Serialize graph for JSON/UI."""
        scores = self.influence_scores()
        self.detect_communities()
        return {
            "nodes": [
                {
                    **v,
                    "influence":  scores.get(k, 0),
                    "community":  self.communities.get(k, 0),
                    "in_degree":  len(self.radj.get(k,set())),
                    "out_degree": len(self.adj.get(k,set())),
                }
                for k, v in self.nodes.items()
            ],
            "edges": self.edges,
            "stats": {
                "nodes":       len(self.nodes),
                "edges":       len(self.edges),
                "communities": len(set(self.communities.values())),
            }
        }

    def save(self):
        """Save graph to disk."""
        fp = GRAPHS_DIR / f"{self.name}.json"
        fp.write_text(json.dumps(self.to_dict(), default=str, indent=2))
        return str(fp)

    @classmethod
    def load(cls, name):
        """Load graph from disk."""
        fp = GRAPHS_DIR / f"{name}.json"
        if not fp.exists(): return None
        data  = json.loads(fp.read_text())
        graph = cls(name)
        for node in data.get("nodes",[]):
            graph.add_node(node["id"], **{k:v for k,v in node.items() if k!="id"})
        for edge in data.get("edges",[]):
            graph.add_edge(edge["src"],edge["dst"],
                          edge.get("relation",""),edge.get("weight",1.0),
                          edge.get("platform",""),edge.get("ts",""))
        return graph

# ══════════════════════════════════════════════════════════════════════════════
# 🔍 SOCIAL OSINT — Data Harvesters
# ══════════════════════════════════════════════════════════════════════════════

def _fetch(url, headers=None, timeout=10):
    """HTTP GET with fallback."""
    hdrs = {
        "User-Agent": "Mozilla/5.0 (compatible; FORGE-Social/1.0)",
        "Accept":     "application/json,text/html,*/*",
        **(headers or {})
    }
    try:
        if REQUESTS:
            r = requests.get(url, headers=hdrs, timeout=timeout)
            ct = r.headers.get("content-type","")
            return r.json() if "json" in ct else r.text, r.status_code
        else:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8","replace")
                try: return json.loads(raw), resp.status
                except: return raw, resp.status
    except Exception as e:
        return None, 0

class GitHubHarvester:
    """GitHub public API — no auth for basic data."""

    BASE = "https://api.github.com"

    def get_user(self, username):
        """Get GitHub user profile."""
        data, status = _fetch(f"{self.BASE}/users/{username}")
        if not data or status != 200: return None
        return {
            "id":        f"github:{username}",
            "name":      data.get("name") or username,
            "username":  username,
            "platform":  "github",
            "bio":       data.get("bio",""),
            "location":  data.get("location",""),
            "followers": data.get("followers",0),
            "following": data.get("following",0),
            "posts":     data.get("public_repos",0),
            "created":   data.get("created_at",""),
            "url":       data.get("html_url",""),
            "company":   data.get("company",""),
        }

    def get_followers(self, username, limit=30):
        """Get follower list."""
        data, _ = _fetch(f"{self.BASE}/users/{username}/followers?per_page={limit}")
        if not data or not isinstance(data,list): return []
        return [{"username":u["login"],"id":f"github:{u['login']}"} for u in data]

    def get_following(self, username, limit=30):
        """Get following list."""
        data, _ = _fetch(f"{self.BASE}/users/{username}/following?per_page={limit}")
        if not data or not isinstance(data,list): return []
        return [{"username":u["login"],"id":f"github:{u['login']}"} for u in data]

    def get_repos(self, username, limit=20):
        """Get user repositories."""
        data, _ = _fetch(
            f"{self.BASE}/users/{username}/repos?sort=stars&per_page={limit}"
        )
        if not data or not isinstance(data,list): return []
        return [
            {
                "name":     r["name"],
                "stars":    r.get("stargazers_count",0),
                "forks":    r.get("forks_count",0),
                "language": r.get("language",""),
                "url":      r.get("html_url",""),
                "topics":   r.get("topics",[]),
            }
            for r in data
        ]

    def get_repo_contributors(self, owner, repo, limit=20):
        """Get contributors to a repo — natural collaboration network."""
        data, _ = _fetch(
            f"{self.BASE}/repos/{owner}/{repo}/contributors?per_page={limit}"
        )
        if not data or not isinstance(data,list): return []
        return [
            {"username":c["login"],"id":f"github:{c['login']}","contributions":c.get("contributions",0)}
            for c in data
        ]

    def build_network(self, username, depth=1, limit=20):
        """Build GitHub social graph."""
        graph = SocialGraph(f"github_{username}")
        rprint(f"  [dim]Building GitHub network for {username} (depth={depth})...[/dim]")

        # Root node
        profile = self.get_user(username)
        if not profile:
            rprint(f"  [red]User not found: {username}[/red]")
            return graph

        root_id = profile["id"]
        graph.add_node(root_id, **profile)
        self._save_entity(profile)

        to_process = [(username, 0)]
        processed  = set()

        while to_process:
            uname, current_depth = to_process.pop(0)
            if uname in processed or current_depth > depth: continue
            processed.add(uname)
            uid = f"github:{uname}"

            rprint(f"    [dim]→ {uname} (depth {current_depth})[/dim]")

            # Add followers
            for f in self.get_followers(uname, limit):
                fid = f["id"]
                if fid not in graph.nodes:
                    fp = self.get_user(f["username"])
                    if fp:
                        graph.add_node(fid, **fp)
                        self._save_entity(fp)
                graph.add_edge(fid, uid, "follows", platform="github")

                if current_depth < depth:
                    to_process.append((f["username"], current_depth+1))

            # Add following
            for f in self.get_following(uname, limit):
                fid = f["id"]
                if fid not in graph.nodes:
                    fp = self.get_user(f["username"])
                    if fp:
                        graph.add_node(fid, **fp)
                        self._save_entity(fp)
                graph.add_edge(uid, fid, "follows", platform="github")

            # Add repo collaborators
            repos = self.get_repos(uname, 5)
            for repo in repos[:3]:
                contribs = self.get_repo_contributors(uname, repo["name"], 10)
                for c in contribs:
                    cid = c["id"]
                    if cid != uid:
                        if cid not in graph.nodes:
                            cp = self.get_user(c["username"])
                            if cp:
                                graph.add_node(cid, **cp)
                                self._save_entity(cp)
                        graph.add_edge(uid, cid, "collaborates",
                                      weight=min(c["contributions"]/10, 5.0),
                                      platform="github")
            time.sleep(0.5)  # rate limit

        rprint(f"  [green]Graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges[/green]")
        return graph

    def _save_entity(self, profile):
        conn = get_db()
        conn.execute("""
            INSERT OR REPLACE INTO entities
            (id,name,platform,username,url,followers,following,posts,bio,location,first_seen,last_updated)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (profile["id"],profile.get("name",""),profile.get("platform",""),
             profile.get("username",""),profile.get("url",""),
             profile.get("followers",0),profile.get("following",0),
             profile.get("posts",0),profile.get("bio",""),
             profile.get("location",""),
             datetime.now().isoformat(),datetime.now().isoformat())
        )
        conn.commit(); conn.close()

class RedditHarvester:
    """Reddit public API — no auth needed."""

    BASE = "https://www.reddit.com"

    def get_user(self, username):
        """Get Reddit user profile."""
        data, status = _fetch(
            f"{self.BASE}/user/{username}/about.json",
            headers={"Accept":"application/json"}
        )
        if not data or status != 200: return None
        d = data.get("data",{}) if isinstance(data,dict) else {}
        created = datetime.fromtimestamp(d.get("created_utc",0)).isoformat() if d.get("created_utc") else ""
        return {
            "id":        f"reddit:{username}",
            "name":      d.get("name",username),
            "username":  username,
            "platform":  "reddit",
            "followers": d.get("subreddit",{}).get("subscribers",0),
            "posts":     d.get("link_karma",0) + d.get("comment_karma",0),
            "created":   created,
            "verified":  int(d.get("verified",False)),
            "url":       f"https://reddit.com/u/{username}",
            "bio":       d.get("subreddit",{}).get("public_description",""),
        }

    def get_posts(self, username, limit=25):
        """Get user's recent posts + comments."""
        posts = []

        # Posts
        data, _ = _fetch(
            f"{self.BASE}/user/{username}/submitted.json?limit={limit}",
            headers={"Accept":"application/json"}
        )
        if data and isinstance(data,dict):
            for item in data.get("data",{}).get("children",[]):
                p = item.get("data",{})
                posts.append({
                    "id":      p.get("id",""),
                    "content": p.get("title","") + " " + p.get("selftext","")[:200],
                    "ts":      datetime.fromtimestamp(p.get("created_utc",0)).isoformat(),
                    "likes":   p.get("score",0),
                    "shares":  p.get("num_comments",0),
                    "url":     "https://reddit.com" + p.get("permalink",""),
                    "subreddit": p.get("subreddit",""),
                })

        return posts

    def get_subreddit_network(self, subreddit, limit=30):
        """Map who posts together in a subreddit — community graph."""
        graph = SocialGraph(f"reddit_{subreddit}")
        data, _ = _fetch(
            f"{self.BASE}/r/{subreddit}/hot.json?limit={limit}",
            headers={"Accept":"application/json"}
        )
        if not data or not isinstance(data,dict): return graph

        posts = data.get("data",{}).get("children",[])
        sub_node = f"r/{subreddit}"
        graph.add_node(sub_node, name=f"r/{subreddit}", platform="reddit",
                      node_type="subreddit")

        for post in posts:
            p      = post.get("data",{})
            author = p.get("author","")
            if not author or author == "[deleted]": continue

            aid = f"reddit:{author}"
            if aid not in graph.nodes:
                graph.add_node(aid, name=author, username=author,
                              platform="reddit", id=aid)
            graph.add_edge(aid, sub_node, "posts_in",
                          weight=float(p.get("score",1)),
                          platform="reddit")
        return graph

class HackerNewsHarvester:
    """HackerNews public API."""

    BASE = "https://hacker-news.firebaseio.com/v0"

    def get_user(self, username):
        """Get HN user profile."""
        data, status = _fetch(f"{self.BASE}/user/{username}.json")
        if not data or status != 200: return None
        return {
            "id":       f"hn:{username}",
            "name":     username,
            "username": username,
            "platform": "hackernews",
            "posts":    data.get("karma",0),
            "created":  datetime.fromtimestamp(data.get("created",0)).isoformat(),
            "bio":      data.get("about","")[:200],
            "url":      f"https://news.ycombinator.com/user?id={username}",
        }

    def get_recent_items(self, username, limit=10):
        """Get user's recent posts."""
        data, _ = _fetch(f"{self.BASE}/user/{username}.json")
        if not data: return []

        items = data.get("submitted",[])[:limit]
        posts = []
        for item_id in items:
            item, _ = _fetch(f"{self.BASE}/item/{item_id}.json")
            if item and isinstance(item,dict):
                posts.append({
                    "id":      str(item_id),
                    "content": item.get("title","") or item.get("text","")[:200],
                    "ts":      datetime.fromtimestamp(item.get("time",0)).isoformat(),
                    "likes":   item.get("score",0),
                    "url":     item.get("url",""),
                    "type":    item.get("type",""),
                })
            time.sleep(0.2)
        return posts

class DomainHarvester:
    """Domain/WHOIS ownership chain analysis."""

    def whois_lookup(self, domain):
        """WHOIS data via public API."""
        try:
            data, _ = _fetch(f"https://api.whoapi.com/?domain={domain}&r=whois&apikey=free")
            if not data: return {}
            return data if isinstance(data,dict) else {}
        except: return {}

    def rdap_lookup(self, domain):
        """RDAP lookup — modern WHOIS alternative."""
        try:
            data, status = _fetch(f"https://rdap.org/domain/{domain}")
            if not data or status != 200: return {}
            if not isinstance(data,dict): return {}

            result = {
                "domain":     domain,
                "registered": "",
                "registrar":  "",
                "registrant": "",
                "emails":     [],
                "nameservers":[],
            }

            # Extract entities
            for entity in data.get("entities",[]):
                roles = entity.get("roles",[])
                vcard = entity.get("vcardArray",[])
                if vcard and len(vcard) > 1:
                    for item in vcard[1]:
                        if item[0] == "email":
                            result["emails"].append(item[3])
                        if item[0] == "fn" and "registrant" in roles:
                            result["registrant"] = item[3]

            for ns in data.get("nameservers",[]):
                result["nameservers"].append(ns.get("ldhName",""))

            return result
        except: return {}

    def build_domain_network(self, domains):
        """
        Connect domains that share registrant email/nameserver.
        Reveals ownership clusters.
        """
        graph = SocialGraph("domain_network")
        domain_data = {}

        for domain in domains:
            rprint(f"  [dim]RDAP: {domain}[/dim]")
            rdap = self.rdap_lookup(domain)
            domain_data[domain] = rdap
            nid  = f"domain:{domain}"
            graph.add_node(nid, name=domain, platform="domain",
                          registrant=rdap.get("registrant",""),
                          emails=rdap.get("emails",[]))
            time.sleep(0.5)

        # Connect by shared email
        for d1, data1 in domain_data.items():
            for d2, data2 in domain_data.items():
                if d1 >= d2: continue
                shared_emails = set(data1.get("emails",[])) & set(data2.get("emails",[]))
                shared_ns     = set(data1.get("nameservers",[])) & set(data2.get("nameservers",[]))

                if shared_emails:
                    graph.add_edge(f"domain:{d1}",f"domain:{d2}",
                                  "shared_registrant",
                                  weight=len(shared_emails)*2.0,
                                  platform="domain")
                elif shared_ns:
                    graph.add_edge(f"domain:{d1}",f"domain:{d2}",
                                  "shared_nameserver",
                                  weight=float(len(shared_ns)),
                                  platform="domain")
        return graph

# ══════════════════════════════════════════════════════════════════════════════
# 👥 PERSONA PROFILER
# ══════════════════════════════════════════════════════════════════════════════

PERSONA_PROMPT = """You are FORGE building a persona profile from social data.

Entity: {name} ({platform})
Profile data: {profile}
Recent posts: {posts}
Network position: {network}

Build a complete persona profile:

## IDENTITY
Who is this person? What do they do? Real or constructed?

## WRITING STYLE FINGERPRINT
Vocabulary level, sentence structure, punctuation habits,
emotional register, unique phrases or patterns.

## TOPIC FINGERPRINT
What topics does this person consistently engage with?
What do they avoid? What drives their posting?

## POSTING BEHAVIOR
Time patterns, frequency, consistency.
Does it look human or automated?

## NETWORK POSITION
Are they an influencer, lurker, connector, amplifier?
What communities do they bridge?

## BOT/FAKE PROBABILITY
Based on all signals:
- Account age vs activity ratio
- Follower/following ratio
- Posting consistency
- Content originality
- Network authenticity

Score: X/100 (0=definitely human, 100=definitely bot)

## SHERLOCK VERDICT
One paragraph. What is the real story of this account?"""

WRITING_FINGERPRINT_PROMPT = """Analyze these text samples for writing style fingerprint.

Samples from {name}:
{samples}

Extract:
1. Vocabulary level (simple/medium/advanced)
2. Average sentence length
3. Punctuation style (heavy/light/unusual)
4. Emotional register (neutral/positive/negative/volatile)
5. Unique phrases or expressions they repeat
6. Topics they consistently mention
7. What time zone do posting hours suggest?
8. Estimated education level
9. Native English speaker? (yes/no/unsure)
10. Likely age range

Return as JSON:
{{"vocab_level":"medium","avg_sentence_length":12,"punctuation":"light",
"emotional_register":"neutral","unique_phrases":[],"topics":[],
"timezone_guess":"UTC+5","education":"college","native_english":true,
"age_range":"25-35","bot_indicators":[],"human_indicators":[]}}"""

class PersonaProfiler:
    """Build complete profiles of social entities."""

    def profile(self, username, platform="github"):
        """Build complete persona profile."""
        rprint(f"\n[bold]👥 PROFILING: {username} ({platform})[/bold]")

        profile_data = {}
        posts        = []
        graph_data   = {}

        if platform == "github":
            h = GitHubHarvester()
            profile_data = h.get_user(username) or {}
            repos        = h.get_repos(username, 10)
            # Synthesize posts from repo names/descriptions
            posts = [{"content": f"{r['name']}: stars={r['stars']} lang={r['language']}"}
                    for r in repos]
            profile_data["repos"] = repos

        elif platform == "reddit":
            h = RedditHarvester()
            profile_data = h.get_user(username) or {}
            posts        = h.get_posts(username, 20)
            self._save_posts(username, platform, posts)

        elif platform == "hackernews":
            h = HackerNewsHarvester()
            profile_data = h.get_user(username) or {}
            posts        = h.get_recent_items(username, 10)

        if not profile_data:
            rprint(f"  [red]No data found for {username} on {platform}[/red]")
            return None

        # Writing fingerprint
        fingerprint = {}
        if posts and AI_AVAILABLE:
            samples = "\n".join(
                p.get("content","")[:100]
                for p in posts[:10]
                if p.get("content")
            )
            if samples:
                fingerprint = ai_json(
                    WRITING_FINGERPRINT_PROMPT.format(
                        name=username, samples=samples[:1500]
                    ),
                    max_tokens=500
                ) or {}

        # Full persona analysis
        analysis = ""
        if AI_AVAILABLE:
            analysis = ai_call(
                PERSONA_PROMPT.format(
                    name     = username,
                    platform = platform,
                    profile  = json.dumps(profile_data, default=str)[:600],
                    posts    = json.dumps([p.get("content","")[:80] for p in posts[:8]])[:400],
                    network  = f"followers:{profile_data.get('followers',0)} following:{profile_data.get('following',0)}",
                ),
                max_tokens=1200
            )

        result = {
            "username":    username,
            "platform":    platform,
            "profile":     profile_data,
            "posts":       posts[:10],
            "fingerprint": fingerprint,
            "analysis":    analysis,
            "ts":          datetime.now().isoformat(),
        }

        # Save
        fp = PROFILES_DIR / f"{platform}_{username}.json"
        fp.write_text(json.dumps(result, default=str, indent=2))

        if analysis:
            rprint(Panel(analysis[:700], border_style="yellow",
                        title=f"👥 Persona: {username}"))

        return result

    def _save_posts(self, username, platform, posts):
        conn = get_db()
        for p in posts:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO posts (id,entity_id,platform,content,ts,likes,shares,url) VALUES (?,?,?,?,?,?,?,?)",
                    (p.get("id",hashlib.md5(p.get("content","").encode()).hexdigest()[:12]),
                     f"{platform}:{username}", platform,
                     p.get("content","")[:500], p.get("ts",""),
                     p.get("likes",0), p.get("shares",0), p.get("url",""))
                )
            except: pass
        conn.commit(); conn.close()

    def compare_writing_styles(self, profile_a, profile_b):
        """Check if two accounts have similar writing styles — alt account detection."""
        if not AI_AVAILABLE: return None

        posts_a = [p.get("content","")[:100] for p in profile_a.get("posts",[])[:8]]
        posts_b = [p.get("content","")[:100] for p in profile_b.get("posts",[])[:8]]

        return ai_json(
            f"Compare writing styles of two accounts:\n\n"
            f"Account A ({profile_a.get('username','')}):\n{json.dumps(posts_a)[:500]}\n\n"
            f"Account B ({profile_b.get('username','')}):\n{json.dumps(posts_b)[:500]}\n\n"
            "Are these the same person?\n"
            "JSON: {{\"same_person_probability\":75,\"reasoning\":\"...\","
            "\"shared_patterns\":[],\"differences\":[]}}",
            max_tokens=400
        )

# ══════════════════════════════════════════════════════════════════════════════
# 🎭 FAKE NETWORK DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

BOT_SCORE_PROMPT = """Score this account for bot/fake probability.

Account data:
{data}

Scoring criteria:
- Account age < 6 months: +15 points
- Following > 10x followers: +20 points
- Zero or very few original posts: +25 points
- Posting at unusual hours consistently: +15 points
- Bio is empty or generic: +10 points
- Username has numbers at end: +5 points
- Very high activity for follower count: +10 points
- Follower accounts themselves look fake: +15 points

Return JSON:
{{"bot_score":45,"verdict":"SUSPICIOUS","reasoning":"...",
"red_flags":[],"green_flags":[],"recommendation":"investigate further"}}"""

COORDINATED_BEHAVIOR_PROMPT = """Analyze these accounts for coordinated inauthentic behavior.

Accounts:
{accounts}

Check for:
1. Similar creation dates (within same week/month)
2. Similar posting schedules
3. Identical or near-identical content
4. Same follower/following patterns
5. Same topics/hashtags always
6. Amplification chains (A retweets B retweets C...)

JSON: {{"coordinated":true,"confidence":85,"pattern":"...",
"likely_operator_count":1,"evidence":[],"verdict":"..."}}"""

class FakeDetector:
    """Detect bots, fake accounts, and coordinated behavior."""

    def score_account(self, profile_data):
        """Score an account for bot probability 0-100."""
        score  = 0
        flags  = []

        followers = profile_data.get("followers", 0)
        following = profile_data.get("following", 0)
        posts     = profile_data.get("posts", 0)
        created   = profile_data.get("created", "")
        bio       = profile_data.get("bio", "")
        username  = profile_data.get("username", "")

        # Follower ratio
        if following > 0 and followers > 0:
            ratio = following / max(followers, 1)
            if ratio > 10:
                score += 20
                flags.append(f"following/followers ratio: {ratio:.0f}x")

        # Account age
        if created:
            try:
                age_days = (datetime.now() - datetime.fromisoformat(created[:19])).days
                if age_days < 30:
                    score += 25; flags.append("account < 30 days old")
                elif age_days < 180:
                    score += 10; flags.append("account < 6 months old")
            except: pass

        # Empty bio
        if not bio:
            score += 10; flags.append("empty bio")

        # Username pattern (numbers at end = bot signal)
        if re.search(r'\d{4,}$', username):
            score += 8; flags.append("numeric suffix in username")

        # Very low activity
        if followers > 1000 and posts < 10:
            score += 15; flags.append("high followers, very few posts")

        # Very high following with zero posts
        if following > 500 and posts == 0:
            score += 20; flags.append("follows many, posts nothing")

        score = min(score, 100)
        verdict = (
            "LIKELY BOT" if score > 70 else
            "SUSPICIOUS" if score > 40 else
            "PROBABLY HUMAN" if score > 20 else
            "LIKELY HUMAN"
        )

        result = {
            "bot_score": score,
            "verdict":   verdict,
            "red_flags": flags,
        }

        # AI enhancement
        if AI_AVAILABLE:
            ai_result = ai_json(
                BOT_SCORE_PROMPT.format(
                    data=json.dumps(profile_data, default=str)[:600]
                ),
                max_tokens=400
            )
            if ai_result:
                result.update(ai_result)
                result["bot_score"] = (score + ai_result.get("bot_score",score)) // 2

        return result

    def detect_coordinated(self, profiles):
        """Check if multiple accounts are coordinated."""
        if len(profiles) < 2: return {}

        # Quick heuristics
        created_dates = []
        for p in profiles:
            c = p.get("profile",{}).get("created","")
            if c:
                try: created_dates.append(datetime.fromisoformat(c[:19]))
                except: pass

        # Check if accounts created within same month
        same_month_count = 0
        if len(created_dates) > 1:
            for i, d1 in enumerate(created_dates):
                for d2 in created_dates[i+1:]:
                    if abs((d1-d2).days) < 30:
                        same_month_count += 1

        result = {
            "accounts_analyzed": len(profiles),
            "same_creation_month": same_month_count,
        }

        if AI_AVAILABLE:
            ai_result = ai_json(
                COORDINATED_BEHAVIOR_PROMPT.format(
                    accounts=json.dumps([
                        {
                            "username": p.get("username",""),
                            "platform": p.get("platform",""),
                            "profile":  {k:v for k,v in p.get("profile",{}).items()
                                       if k in ("followers","following","posts","created","bio")},
                        }
                        for p in profiles[:10]
                    ], default=str)[:1500]
                ),
                max_tokens=500
            )
            if ai_result:
                result.update(ai_result)

        return result

    def find_follower_farms(self, graph):
        """Detect follower farm patterns in a social graph."""
        farms = []

        # Nodes with many in-edges but no out-edges = passive "followers"
        for node_id, node in graph.nodes.items():
            in_  = len(graph.radj.get(node_id,set()))
            out_ = len(graph.adj.get(node_id,set()))

            if in_ > 50 and out_ == 0:
                farms.append({
                    "node":     node_id,
                    "name":     node.get("name",node_id),
                    "followers":in_,
                    "following":out_,
                    "pattern":  "passive_follower_farm",
                })

        return farms

# ══════════════════════════════════════════════════════════════════════════════
# 🌊 INFLUENCE TRACKER
# ══════════════════════════════════════════════════════════════════════════════

class InfluenceTracker:
    """Trace information flow through social networks."""

    def analyze_influence_flow(self, graph):
        """Analyze how influence flows through the graph."""
        scores    = graph.influence_scores()
        top       = graph.top_influencers(10)
        bridges   = graph.bridge_nodes()
        comms, sizes = graph.detect_communities()

        result = {
            "top_influencers":  top,
            "bridge_nodes":     bridges[:5],
            "communities":      len(sizes),
            "community_sizes":  sorted(sizes.values(), reverse=True)[:5],
        }

        if AI_AVAILABLE and top:
            top_names = [
                f"{graph.nodes[n].get('name',n)}: {s:.1f}"
                for n,s in top[:5] if n in graph.nodes
            ]
            bridge_names = [
                f"{b['name']} (bridges {b['communities']} communities)"
                for b in bridges[:3]
            ]

            analysis = ai_call(
                f"Social network influence analysis:\n\n"
                f"Top influencers: {top_names}\n"
                f"Bridge nodes: {bridge_names}\n"
                f"Communities: {len(sizes)} (sizes: {sorted(sizes.values(),reverse=True)[:3]})\n"
                f"Total nodes: {len(graph.nodes)}, edges: {len(graph.edges)}\n\n"
                "As Sherlock Holmes:\n"
                "Who really controls this network?\n"
                "What do the bridge nodes reveal?\n"
                "Is there coordinated behavior?\n"
                "What is the hidden power structure?",
                max_tokens=700
            )
            result["analysis"] = analysis
            rprint(Panel(analysis[:600], border_style="yellow",
                        title="🌊 Influence Analysis"))

        return result

    def trace_narrative(self, posts, topic):
        """Trace how a topic/narrative spread."""
        # Sort by time
        sorted_posts = sorted(posts, key=lambda p: p.get("ts",""))
        if not sorted_posts: return {}

        # Find origin
        origin = sorted_posts[0]

        # Build cascade
        cascade = []
        for i, post in enumerate(sorted_posts):
            cascade.append({
                "order":    i+1,
                "entity":   post.get("entity_id",""),
                "ts":       post.get("ts",""),
                "reach":    post.get("likes",0) + post.get("shares",0),
                "content":  post.get("content","")[:100],
            })

        result = {
            "topic":    topic,
            "origin":   origin,
            "cascade":  cascade[:20],
            "total_posts": len(sorted_posts),
        }

        if AI_AVAILABLE:
            result["analysis"] = ai_call(
                f"Narrative trace for topic: {topic}\n\n"
                f"Origin: {json.dumps(origin, default=str)[:200]}\n"
                f"Cascade ({len(cascade)} posts):\n"
                + "\n".join(f"  T+{i}: {c['entity']} reach:{c['reach']}" for i,c in enumerate(cascade[:8]))
                + "\n\nIs this organic spread or coordinated?\n"
                  "Who originated it? Who amplified it?\n"
                  "What is the velocity — natural or artificial?",
                max_tokens=400
            )

        return result

# ══════════════════════════════════════════════════════════════════════════════
# 🔗 CONNECTION FINDER
# ══════════════════════════════════════════════════════════════════════════════

class ConnectionFinder:
    """Find hidden connections between entities."""

    def find_path(self, graph, entity_a, entity_b):
        """Find shortest path between two entities."""
        path = graph.shortest_path(entity_a, entity_b)
        if not path:
            return {"connected": False, "degrees": None, "path": []}

        # Name the path
        named_path = []
        for node_id in path:
            node = graph.nodes.get(node_id,{})
            named_path.append({
                "id":       node_id,
                "name":     node.get("name", node_id),
                "platform": node.get("platform",""),
            })

        result = {
            "connected": True,
            "degrees":   len(path)-1,
            "path":      named_path,
        }

        if AI_AVAILABLE:
            path_desc = " → ".join(n["name"] for n in named_path)
            result["analysis"] = ai_call(
                f"Connection path found:\n{path_desc}\n\n"
                f"Entity A: {entity_a}\n"
                f"Entity B: {entity_b}\n"
                f"Degrees of separation: {len(path)-1}\n\n"
                "What does this connection reveal?\n"
                "Is this a surprising link or expected?\n"
                "What is the significance?",
                max_tokens=300
            )

        return result

    def find_common_connections(self, graph, entity_a, entity_b):
        """Find all common connections between two entities."""
        common = graph.common_neighbors(entity_a, entity_b)

        named_common = []
        for nid in common:
            node = graph.nodes.get(nid,{})
            named_common.append({
                "id":       nid,
                "name":     node.get("name",nid),
                "platform": node.get("platform",""),
                "influence":graph.influence_scores().get(nid,0),
            })

        named_common.sort(key=lambda x:-x["influence"])

        result = {
            "entity_a": entity_a,
            "entity_b": entity_b,
            "common_count": len(common),
            "common_nodes": named_common[:20],
        }

        if AI_AVAILABLE and common:
            result["analysis"] = ai_call(
                f"Common connections between {entity_a} and {entity_b}:\n"
                f"{len(common)} shared connections\n"
                f"Top: {[n['name'] for n in named_common[:5]]}\n\n"
                "What does this overlap reveal?\n"
                "Are these two entities likely to know each other?",
                max_tokens=250
            )

        return result

    def find_hidden_links(self, entity_a, entity_b, platforms=None):
        """
        Multi-platform connection search.
        Check GitHub, Reddit, domains for any overlap.
        """
        platforms = platforms or ["github","reddit","domain"]
        evidence  = []

        rprint(f"\n[bold]🔗 FINDING LINKS: {entity_a} ↔ {entity_b}[/bold]")

        if "github" in platforms:
            # Check if they contribute to same repos
            gh = GitHubHarvester()
            # Get repos for both
            a_repos = {r["name"] for r in gh.get_repos(entity_a, 20)}
            b_repos = {r["name"] for r in gh.get_repos(entity_b, 20)}
            shared  = a_repos & b_repos
            if shared:
                evidence.append({
                    "platform": "github",
                    "type":     "shared_repos",
                    "detail":   f"Both contribute to: {list(shared)[:5]}",
                    "strength": len(shared),
                })

            # Check mutual following
            a_following = {f["username"] for f in gh.get_following(entity_a, 50)}
            b_following = {f["username"] for f in gh.get_following(entity_b, 50)}
            shared_follows = a_following & b_following
            if shared_follows:
                evidence.append({
                    "platform": "github",
                    "type":     "common_following",
                    "detail":   f"Both follow: {list(shared_follows)[:5]}",
                    "strength": len(shared_follows),
                })

        result = {
            "entity_a":      entity_a,
            "entity_b":      entity_b,
            "evidence_count":len(evidence),
            "evidence":      evidence,
            "connected":     len(evidence) > 0,
        }

        if AI_AVAILABLE and evidence:
            result["analysis"] = ai_call(
                f"Hidden connection evidence between {entity_a} and {entity_b}:\n"
                f"{json.dumps(evidence, default=str)[:800]}\n\n"
                "What is the probability these entities know each other?\n"
                "What does the pattern of connections reveal?\n"
                "Sherlock-style deduction.",
                max_tokens=400
            )

        return result

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 GRAPH UI — force-directed d3.js visualization
# ══════════════════════════════════════════════════════════════════════════════

GRAPH_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FORGE SOCIAL GRAPH</title>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Bebas+Neue&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<style>
:root{--bg:#04080f;--panel:#080d1a;--border:#101828;--green:#00ff88;--green-d:#005c33;--amber:#ff9500;--red:#ff2244;--blue:#0088ff;--dim:#1e2a3a;--text:#7a9ab0;--head:#d0e4f8}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);font-family:'Share Tech Mono',monospace;color:var(--text);height:100vh;overflow:hidden;display:grid;grid-template-rows:48px 1fr 32px;grid-template-columns:1fr 300px}
header{grid-column:1/-1;background:rgba(4,8,15,0.98);border-bottom:1px solid var(--green-d);display:flex;align-items:center;padding:0 16px;gap:14px}
.logo{font-family:'Bebas Neue';font-size:20px;letter-spacing:7px;color:var(--green);text-shadow:0 0 16px rgba(0,255,136,0.3)}
.hdr-stat{font-size:9px;letter-spacing:2px;color:var(--dim)}
.hdr-stat span{color:var(--green)}
#graph-area{position:relative;overflow:hidden}
svg{width:100%;height:100%}
.node circle{stroke-width:1.5;cursor:pointer;transition:r 0.2s}
.node circle:hover{stroke-width:3}
.node text{font-size:9px;fill:#4a6a80;pointer-events:none;letter-spacing:0.5px}
.link{stroke-opacity:0.4;stroke-width:1}
.node.selected circle{stroke-width:3;filter:drop-shadow(0 0 6px currentColor)}
.panel{background:var(--panel);border-left:1px solid var(--border);overflow-y:auto;scrollbar-width:thin;display:flex;flex-direction:column}
.panel-section{padding:12px;border-bottom:1px solid var(--border)}
.sec-title{font-size:8px;letter-spacing:3px;color:var(--green-d);margin-bottom:10px}
.entity-name{font-family:'Bebas Neue';font-size:18px;letter-spacing:3px;color:var(--green);margin-bottom:6px}
.stat-row{display:flex;justify-content:space-between;font-size:10px;padding:3px 0;border-bottom:1px solid rgba(16,24,40,0.5)}
.stat-key{color:var(--dim)}
.stat-val{color:var(--head)}
.bot-bar{height:6px;background:var(--dim);border-radius:2px;margin:6px 0}
.bot-fill{height:100%;border-radius:2px;transition:width 0.5s}
.analysis-text{font-size:10px;line-height:1.7;color:var(--text);white-space:pre-wrap;padding:10px 12px;border-bottom:1px solid var(--border);max-height:300px;overflow-y:auto}
.search-area{padding:10px 12px;border-bottom:1px solid var(--border)}
.search-input{width:100%;background:rgba(0,0,0,0.4);border:1px solid var(--border);color:var(--head);font-family:'Share Tech Mono';font-size:11px;padding:8px;outline:none}
.search-input:focus{border-color:var(--green-d)}
.btn-sm{font-family:'Share Tech Mono';font-size:9px;letter-spacing:2px;padding:7px 10px;border:1px solid;background:transparent;cursor:pointer;text-transform:uppercase;margin-top:6px;width:100%}
.btn-green{color:var(--green);border-color:var(--green-d)}
.btn-green:hover{background:rgba(0,255,136,0.1)}
.top-list{padding:8px 12px}
.top-item{display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--dim);cursor:pointer}
.top-rank{font-size:10px;color:var(--green-d);width:18px}
.top-name{font-size:10px;color:var(--head);flex:1}
.top-score{font-size:9px;color:var(--dim)}
.status-bar{grid-column:1/-1;background:rgba(0,0,0,0.9);border-top:1px solid var(--border);display:flex;align-items:center;padding:0 14px;gap:18px;font-size:9px;color:var(--dim)}
.sb-val{color:var(--green)}
.community-legend{padding:8px 12px;display:flex;flex-wrap:wrap;gap:6px}
.comm-badge{font-size:8px;padding:2px 6px;border-radius:2px;letter-spacing:1px}
.spinner{display:none;text-align:center;padding:16px;color:var(--green-d);font-size:9px;animation:pulse 0.8s infinite}
.spinner.show{display:block}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.3}}
</style>
</head>
<body>
<header>
  <div class="logo">SOCIAL</div>
  <div class="hdr-stat">NODES <span id="h-nodes">0</span></div>
  <div class="hdr-stat">EDGES <span id="h-edges">0</span></div>
  <div class="hdr-stat">COMMUNITIES <span id="h-comms">0</span></div>
  <div style="flex:1"></div>
  <div class="hdr-stat" id="h-graph-name">NO GRAPH LOADED</div>
</header>

<div id="graph-area">
  <svg id="graph-svg">
    <defs>
      <marker id="arrow" viewBox="0 -3 8 6" refX="16" refY="0" markerWidth="6" markerHeight="6" orient="auto">
        <path d="M0,-3L8,0L0,3" fill="rgba(0,255,136,0.3)"/>
      </marker>
    </defs>
    <g id="graph-g"></g>
  </svg>
</div>

<div class="panel">
  <div class="search-area">
    <div class="sec-title">LOAD GRAPH</div>
    <input class="search-input" id="username-input" placeholder="GitHub username...">
    <button class="btn-sm btn-green" onclick="loadGraph()">BUILD GRAPH</button>
    <div class="spinner" id="load-spinner">BUILDING NETWORK...</div>
  </div>

  <div class="panel-section" id="entity-panel">
    <div class="sec-title">SELECTED ENTITY</div>
    <div style="color:var(--dim);font-size:10px">Click a node to inspect</div>
  </div>

  <div class="panel-section">
    <div class="sec-title">TOP INFLUENCERS</div>
    <div class="top-list" id="top-influencers">
      <div style="color:var(--dim);font-size:9px">Load a graph first</div>
    </div>
  </div>

  <div class="panel-section">
    <div class="sec-title">COMMUNITIES</div>
    <div class="community-legend" id="community-legend"></div>
  </div>
</div>

<div class="status-bar">
  <span>FORGE SOCIAL</span>
  <span>DENSITY: <span class="sb-val" id="sb-density">0</span></span>
  <span>TOP INFLUENCER: <span class="sb-val" id="sb-top">--</span></span>
  <span>AVG DEGREE: <span class="sb-val" id="sb-degree">0</span></span>
</div>

<script>
const API = 'http://localhost:7347';
let simulation = null, graphData = null;

const COMM_COLORS = ['#00ff88','#0088ff','#ff9500','#ff2244','#aa44ff','#00ccff','#ffcc00'];

function initGraph() {
  const svg = d3.select('#graph-svg');
  const g   = d3.select('#graph-g');

  // Zoom
  svg.call(d3.zoom().scaleExtent([0.1,4]).on('zoom', e => g.attr('transform',e.transform)));
}

function renderGraph(data) {
  graphData = data;
  const nodes = data.nodes || [];
  const edges = data.edges || [];

  document.getElementById('h-nodes').textContent = nodes.length;
  document.getElementById('h-edges').textContent = edges.length;
  document.getElementById('h-graph-name').textContent = data.name || 'GRAPH';

  const comms = [...new Set(nodes.map(n=>n.community))];
  document.getElementById('h-comms').textContent = comms.length;

  // Stats
  const avgDeg = edges.length > 0 ? (edges.length * 2 / nodes.length).toFixed(1) : 0;
  const density= nodes.length > 1 ? (edges.length / (nodes.length*(nodes.length-1))).toFixed(4) : 0;
  document.getElementById('sb-degree').textContent  = avgDeg;
  document.getElementById('sb-density').textContent = density;

  // Top influencer
  const top = nodes.sort((a,b)=>b.influence-a.influence)[0];
  if (top) document.getElementById('sb-top').textContent = top.name || top.id;

  // Node map
  const nodeMap = {};
  nodes.forEach(n => nodeMap[n.id] = n);

  const svg = d3.select('#graph-svg');
  const g   = d3.select('#graph-g');
  g.selectAll('*').remove();

  const w = svg.node().clientWidth;
  const h = svg.node().clientHeight;

  // Build link objects
  const links = edges.map(e => ({
    source: e.src, target: e.dst,
    relation: e.relation, weight: e.weight || 1,
  })).filter(l => nodeMap[l.source] && nodeMap[l.target]);

  // Force simulation
  simulation = d3.forceSimulation(nodes)
    .force('link',    d3.forceLink(links).id(d=>d.id).distance(80).strength(0.3))
    .force('charge',  d3.forceManyBody().strength(-120))
    .force('center',  d3.forceCenter(w/2, h/2))
    .force('collide', d3.forceCollide(20));

  // Draw edges
  const link = g.append('g').selectAll('line')
    .data(links).join('line')
    .attr('class','link')
    .style('stroke', d => d.relation==='collaborates' ? '#0088ff' : 'rgba(0,255,136,0.25)')
    .style('stroke-width', d => Math.sqrt(d.weight||1));

  // Draw nodes
  const node = g.append('g').selectAll('.node')
    .data(nodes).join('g')
    .attr('class','node')
    .call(d3.drag()
      .on('start', (e,d)=>{ if(!e.active) simulation.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })
      .on('drag',  (e,d)=>{ d.fx=e.x; d.fy=e.y; })
      .on('end',   (e,d)=>{ if(!e.active) simulation.alphaTarget(0); d.fx=null; d.fy=null; })
    )
    .on('click', (e,d) => showEntity(d));

  node.append('circle')
    .attr('r', d => 5 + Math.sqrt(d.influence||0) * 0.8)
    .style('fill', d => COMM_COLORS[d.community % COMM_COLORS.length] + '22')
    .style('stroke', d => COMM_COLORS[d.community % COMM_COLORS.length]);

  node.append('text')
    .attr('dx', 10).attr('dy', 3)
    .text(d => (d.name||d.id).slice(0,16));

  simulation.on('tick', () => {
    link.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y)
        .attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);
    node.attr('transform',d=>`translate(${d.x||0},${d.y||0})`);
  });

  // Top influencers list
  const topNodes = [...nodes].sort((a,b)=>b.influence-a.influence).slice(0,8);
  document.getElementById('top-influencers').innerHTML = topNodes.map((n,i) =>
    `<div class="top-item" onclick="focusNode('${n.id}')">
      <div class="top-rank">${i+1}</div>
      <div class="top-name">${n.name||n.id}</div>
      <div class="top-score">${n.influence?.toFixed(0)||0}</div>
    </div>`
  ).join('');

  // Community legend
  document.getElementById('community-legend').innerHTML = comms.slice(0,7).map((c,i) =>
    `<div class="comm-badge" style="background:${COMM_COLORS[i%COMM_COLORS.length]}22;color:${COMM_COLORS[i%COMM_COLORS.length]};border:1px solid ${COMM_COLORS[i%COMM_COLORS.length]}44">
      C${c}
    </div>`
  ).join('');
}

function showEntity(d) {
  const panel = document.getElementById('entity-panel');
  const botColor = d.bot_score > 70 ? 'var(--red)' : d.bot_score > 40 ? 'var(--amber)' : 'var(--green)';

  panel.innerHTML = `
    <div class="sec-title">ENTITY</div>
    <div class="entity-name">${d.name||d.id}</div>
    <div style="font-size:9px;color:var(--dim);margin-bottom:8px">${d.platform||''} · ${d.username||''}</div>
    <div class="stat-row"><span class="stat-key">Influence</span><span class="stat-val">${d.influence?.toFixed(1)||0}</span></div>
    <div class="stat-row"><span class="stat-key">Followers</span><span class="stat-val">${d.followers||0}</span></div>
    <div class="stat-row"><span class="stat-key">Following</span><span class="stat-val">${d.following||0}</span></div>
    <div class="stat-row"><span class="stat-key">Posts</span><span class="stat-val">${d.posts||0}</span></div>
    <div class="stat-row"><span class="stat-key">In-degree</span><span class="stat-val">${d.in_degree||0}</span></div>
    <div class="stat-row"><span class="stat-key">Community</span><span class="stat-val">${d.community||0}</span></div>
    <div style="margin-top:8px;font-size:8px;letter-spacing:2px;color:var(--dim)">BOT SCORE</div>
    <div class="bot-bar"><div class="bot-fill" style="width:${d.bot_score||0}%;background:${botColor}"></div></div>
    <div style="font-size:10px;color:${botColor}">${d.bot_score||0}% — ${d.verdict||'UNKNOWN'}</div>
    ${d.url ? `<a href="${d.url}" target="_blank" style="color:var(--green-d);font-size:9px;display:block;margin-top:8px">OPEN PROFILE ↗</a>` : ''}
  `;

  // Highlight in graph
  d3.selectAll('.node').classed('selected', n => n.id === d.id);
}

function focusNode(nodeId) {
  if (!graphData) return;
  const node = graphData.nodes.find(n=>n.id===nodeId);
  if (node) showEntity(node);
  if (simulation) {
    const n = simulation.nodes().find(n=>n.id===nodeId);
    if (n) {
      const svg = document.getElementById('graph-svg');
      const cx  = svg.clientWidth/2, cy = svg.clientHeight/2;
      d3.select('#graph-svg').transition().duration(750)
        .call(d3.zoom().transform, d3.zoomIdentity.translate(cx-n.x,cy-n.y).scale(1.5));
    }
  }
}

async function loadGraph() {
  const username = document.getElementById('username-input').value.trim();
  if (!username) return;

  document.getElementById('load-spinner').classList.add('show');
  try {
    const r = await fetch(API+'/api/graph/build', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({username, platform:'github', depth:1})
    });
    const d = await r.json();
    if (d.graph) {
      renderGraph({...d.graph, name:`github:${username}`});
    }
  } catch(e) {
    console.error(e);
  }
  document.getElementById('load-spinner').classList.remove('show');
}

// Load existing graph on start
async function loadLatestGraph() {
  try {
    const d = await fetch(API+'/api/graphs').then(r=>r.json());
    if (d.graphs && d.graphs.length > 0) {
      const latest = d.graphs[0];
      const gd = await fetch(API+`/api/graph/${latest}`).then(r=>r.json());
      if (gd.graph) renderGraph({...gd.graph, name:latest});
    }
  } catch(e) {}
}

initGraph();
loadLatestGraph();
</script>
</body>
</html>"""

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API SERVER
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7347):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    profiler   = PersonaProfiler()
    fake_det   = FakeDetector()
    influence  = InfluenceTracker()
    connector  = ConnectionFinder()
    gh         = GitHubHarvester()

    class SocialAPI(BaseHTTPRequestHandler):
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
                self._html(GRAPH_UI_HTML); return
            if path=="/api/status":
                self._json({"status":"online","ai":AI_AVAILABLE})
            elif path=="/api/graphs":
                files=sorted(GRAPHS_DIR.glob("*.json"),
                            key=lambda f:f.stat().st_mtime,reverse=True)
                self._json({"graphs":[f.stem for f in files[:10]]})
            elif path.startswith("/api/graph/"):
                name=path.split("/")[-1]
                g=SocialGraph.load(name)
                if g: self._json({"graph":g.to_dict()})
                else: self._json({"error":"not found"},404)
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path=urlparse(self.path).path
            body=self._body()

            if path=="/api/graph/build":
                username = body.get("username","")
                platform = body.get("platform","github")
                depth    = min(int(body.get("depth",1)),2)
                if not username: self._json({"error":"username required"},400); return

                def build():
                    if platform=="github":
                        g = gh.build_network(username, depth=depth)
                    else:
                        g = SocialGraph(username)
                    g.save()
                    return g

                graph = build()
                self._json({"graph":graph.to_dict(),"saved":graph.name})

            elif path=="/api/profile":
                username = body.get("username","")
                platform = body.get("platform","github")
                if not username: self._json({"error":"username required"},400); return
                result = profiler.profile(username, platform)
                self._json(result or {"error":"profile failed"})

            elif path=="/api/fake/score":
                username = body.get("username","")
                platform = body.get("platform","github")
                if not username: self._json({"error":"username required"},400); return
                if platform=="github":
                    profile = gh.get_user(username) or {}
                else:
                    profile = {}
                score = fake_det.score_account(profile)
                self._json(score)

            elif path=="/api/connect":
                a = body.get("entity_a","")
                b = body.get("entity_b","")
                graph_name = body.get("graph","")
                if not a or not b: self._json({"error":"entity_a and entity_b required"},400); return
                g = SocialGraph.load(graph_name) if graph_name else SocialGraph()
                result = connector.find_path(g, a, b)
                self._json(result)

            elif path=="/api/influence":
                graph_name = body.get("graph","")
                g = SocialGraph.load(graph_name)
                if not g: self._json({"error":"graph not found"},404); return
                result = influence.analyze_influence_flow(g)
                self._json(result)

            elif path=="/api/investigate":
                target   = body.get("target","")
                platform = body.get("platform","github")
                if not target: self._json({"error":"target required"},400); return
                profile = profiler.profile(target, platform)
                if profile:
                    profile_data = profile.get("profile",{})
                    bot_score    = fake_det.score_account(profile_data)
                    self._json({**profile, "bot_analysis":bot_score})
                else:
                    self._json({"error":"investigation failed"})

            else:
                self._json({"error":"unknown"},404)

    server=HTTPServer(("0.0.0.0",port),SocialAPI)
    rprint(f"\n  [bold yellow]🕸️  FORGE SOCIAL[/bold yellow]")
    rprint(f"  [green]Graph UI: http://localhost:{port}[/green]")
    rprint(f"  [green]API:      http://localhost:{port}/api/status[/green]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# 🎮 MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ███████╗ ██████╗  ██████╗██╗ █████╗ ██╗
  ██╔════╝██╔═══██╗██╔════╝██║██╔══██╗██║
  ███████╗██║   ██║██║     ██║███████║██║
  ╚════██║██║   ██║██║     ██║██╔══██║██║
  ███████║╚██████╔╝╚██████╗██║██║  ██║███████╗
  ╚══════╝ ╚═════╝  ╚═════╝╚═╝╚═╝  ╚═╝╚══════╝
[/yellow]
[bold]  🕸️  FORGE SOCIAL — Social Graph Intelligence[/bold]
[dim]  Map who knows who. Trace every connection. Expose fake networks.[/dim]
"""

def interactive():
    rprint(BANNER)
    rprint(f"  [dim]AI:       {'✅' if AI_AVAILABLE else '❌ pip install anthropic'}[/dim]")
    rprint(f"  [dim]Requests: {'✅' if REQUESTS else '⬜ pip install requests'}[/dim]\n")

    gh      = GitHubHarvester()
    reddit  = RedditHarvester()
    hn      = HackerNewsHarvester()
    profiler= PersonaProfiler()
    fake    = FakeDetector()
    connect = ConnectionFinder()

    rprint("[dim]Commands: graph | profile | fake | connect | reddit | hn | server | help[/dim]\n")

    while True:
        try:
            inp = console.input if RICH else input
            raw = inp("[yellow bold]🕸️  social >[/yellow bold] ").strip()
            if not raw: continue
            parts = raw.split(None,2)
            cmd   = parts[0].lower()
            args  = parts[1] if len(parts)>1 else ""
            args2 = parts[2] if len(parts)>2 else ""

            if cmd in ("quit","exit","q"):
                rprint("[dim]Social graph offline.[/dim]"); break

            elif cmd == "help":
                rprint("""
[bold yellow]FORGE SOCIAL Commands[/bold yellow]

  [yellow]graph[/yellow] <github_user>      Build GitHub social graph
  [yellow]profile[/yellow] <user> [platform] Full persona profile
  [yellow]fake[/yellow] <github_user>       Bot/fake account score
  [yellow]connect[/yellow] <user_a> <user_b> Find hidden connections
  [yellow]reddit[/yellow] <username>        Reddit user profile
  [yellow]hn[/yellow] <username>            HackerNews user profile
  [yellow]graphs[/yellow]                   List saved graphs
  [yellow]influence[/yellow] <graph_name>   Analyze influence in graph
  [yellow]server[/yellow]                   Start graph UI server
""")

            elif cmd == "graph":
                if not args: rprint("[yellow]Usage: graph <username>[/yellow]"); continue
                rprint(f"\n[bold]Building graph for {args}...[/bold]")
                graph = gh.build_network(args, depth=1, limit=15)
                graph.save()

                top = graph.top_influencers(5)
                if RICH:
                    t = Table(border_style="yellow",box=rbox.ROUNDED,title=f"Top Influencers: {args}")
                    t.add_column("Rank",    style="dim",   width=5)
                    t.add_column("Account", style="green", width=25)
                    t.add_column("Score",   width=8)
                    t.add_column("In",      width=6)
                    for i,(nid,score) in enumerate(top,1):
                        node = graph.nodes.get(nid,{})
                        deg  = graph.degree(nid)
                        t.add_row(str(i),node.get("name",nid)[:24],
                                 f"{score:.1f}",str(deg["in"]))
                    console.print(t)

                inf = InfluenceTracker()
                inf.analyze_influence_flow(graph)
                rprint(f"\n  [dim]Saved: {GRAPHS_DIR}/{graph.name}.json[/dim]")
                rprint(f"  [dim]Open UI: python forge_social.py --server[/dim]")

            elif cmd == "profile":
                platform = args2 or "github"
                if not args: rprint("[yellow]Usage: profile <username> [platform][/yellow]"); continue
                profiler.profile(args, platform)

            elif cmd == "fake":
                if not args: rprint("[yellow]Usage: fake <username>[/yellow]"); continue
                profile = gh.get_user(args)
                if not profile:
                    rprint(f"  [red]User not found: {args}[/red]"); continue
                score = fake.score_account(profile)
                color = "red" if score["bot_score"]>70 else "yellow" if score["bot_score"]>40 else "green"
                rprint(f"\n  [{color}]BOT SCORE: {score['bot_score']}/100 — {score['verdict']}[/{color}]")
                for flag in score.get("red_flags",[]):
                    rprint(f"  [red]⚠ {flag}[/red]")
                if score.get("reasoning"):
                    rprint(f"\n  [dim]{score['reasoning'][:200]}[/dim]")

            elif cmd == "connect":
                if not args or not args2:
                    rprint("[yellow]Usage: connect <user_a> <user_b>[/yellow]"); continue
                rprint(f"\n[bold]Finding connections: {args} ↔ {args2}[/bold]")
                result = connect.find_hidden_links(args, args2, ["github"])
                rprint(f"\n  [{'green' if result['connected'] else 'dim'}]Connected: {result['connected']}[/]")
                rprint(f"  Evidence points: {result['evidence_count']}")
                for ev in result.get("evidence",[]):
                    rprint(f"  [yellow]→ {ev['type']}: {ev['detail'][:60]}[/yellow]")
                if result.get("analysis"):
                    rprint(Panel(result["analysis"][:400], border_style="yellow",
                                title="🔗 Connection Analysis"))

            elif cmd == "reddit":
                if not args: rprint("[yellow]Usage: reddit <username>[/yellow]"); continue
                profile = reddit.get_user(args)
                if profile:
                    rprint(f"\n  [bold]{profile['name']}[/bold] (reddit)")
                    rprint(f"  Karma:   {profile['posts']}")
                    rprint(f"  Created: {profile['created'][:10]}")
                    profiler.profile(args, "reddit")
                else:
                    rprint(f"  [red]User not found: {args}[/red]")

            elif cmd == "hn":
                if not args: rprint("[yellow]Usage: hn <username>[/yellow]"); continue
                profile = hn.get_user(args)
                if profile:
                    rprint(f"\n  [bold]{profile['name']}[/bold] (HackerNews)")
                    rprint(f"  Karma:   {profile['posts']}")
                    rprint(f"  Created: {profile['created'][:10]}")
                    if profile.get("bio"):
                        rprint(f"  Bio:     {profile['bio'][:100]}")
                else:
                    rprint(f"  [red]User not found: {args}[/red]")

            elif cmd == "graphs":
                files = sorted(GRAPHS_DIR.glob("*.json"),
                              key=lambda f:f.stat().st_mtime, reverse=True)
                if files:
                    for f in files[:10]:
                        g = SocialGraph.load(f.stem)
                        if g:
                            rprint(f"  [green]{f.stem:<30}[/green] {len(g.nodes)} nodes, {len(g.edges)} edges")
                else:
                    rprint("[dim]No graphs saved. Run 'graph <username>' first.[/dim]")

            elif cmd == "influence":
                if not args:
                    rprint("[yellow]Usage: influence <graph_name>[/yellow]"); continue
                g = SocialGraph.load(args)
                if not g: rprint(f"[red]Graph not found: {args}[/red]"); continue
                inf = InfluenceTracker()
                inf.analyze_influence_flow(g)

            elif cmd == "server":
                rprint("[yellow]Starting SOCIAL server on port 7347...[/yellow]")
                threading.Thread(target=start_server, daemon=True).start()
                time.sleep(0.5)
                rprint("[green]Graph UI live at http://localhost:7347[/green]")

            else:
                if AI_AVAILABLE:
                    r = ai_call(f"Social intelligence query: {raw}", max_tokens=150)
                    rprint(f"  [dim]{r[:150]}[/dim]")
                else:
                    rprint("[dim]Unknown command. Type 'help'.[/dim]")

        except (KeyboardInterrupt,EOFError):
            rprint("\n[dim]Social graph offline.[/dim]"); break

def main():
    if "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7347
        start_server(port)
        return

    if "--profile" in sys.argv:
        idx = sys.argv.index("--profile")
        username = sys.argv[idx+1] if idx+1 < len(sys.argv) else ""
        platform = sys.argv[idx+2] if idx+2 < len(sys.argv) and not sys.argv[idx+2].startswith("--") else "github"
        if username:
            rprint(BANNER)
            PersonaProfiler().profile(username, platform)
        return

    if "--graph" in sys.argv:
        idx = sys.argv.index("--graph")
        username = sys.argv[idx+1] if idx+1 < len(sys.argv) else ""
        if username:
            rprint(BANNER)
            g = GitHubHarvester().build_network(username, depth=1)
            g.save()
            InfluenceTracker().analyze_influence_flow(g)
        return

    if "--fake" in sys.argv:
        idx = sys.argv.index("--fake")
        username = sys.argv[idx+1] if idx+1 < len(sys.argv) else ""
        if username:
            rprint(BANNER)
            profile = GitHubHarvester().get_user(username) or {}
            score   = FakeDetector().score_account(profile)
            rprint(f"\nBot Score: {score['bot_score']}/100 — {score['verdict']}")
        return

    if "--connect" in sys.argv:
        idx = sys.argv.index("--connect")
        a   = sys.argv[idx+1] if idx+1 < len(sys.argv) else ""
        b   = sys.argv[idx+2] if idx+2 < len(sys.argv) else ""
        if a and b:
            rprint(BANNER)
            ConnectionFinder().find_hidden_links(a, b)
        return

    interactive()

if __name__ == "__main__":
    main()
