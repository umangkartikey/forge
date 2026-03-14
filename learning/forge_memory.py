#!/usr/bin/env python3
"""
FORGE MEMORY — Persistent Intelligence Memory
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FORGE never forgets.

Every IP, domain, person, pattern, threat —
remembered forever. Cross-referenced instantly.
Gets smarter with every investigation.

FORGE month 1 vs FORGE month 6 = completely different.

Modules:
  🧠 Memory Store     → unified SQLite across all FORGE modules
  🔍 Recall Engine    → "I have seen this before"
  📈 Learning Engine  → outcome tracking, confidence calibration
  🔗 Relationship Map → how entities connect across cases
  🌐 Memory API       → simple interface for all modules

Usage:
  from forge_memory import Memory

  mem = Memory()

  # Remember something
  mem.remember("185.12.34.56", "port_scan", confidence=0.8, source="forge_network")
  mem.remember("evil.com",     "c2_domain",  confidence=0.95, source="forge_ghost")

  # Recall everything known
  facts = mem.recall("185.12.34.56")

  # Have we seen this before?
  history = mem.seen_before("185.12.34.56")

  # Find similar past events
  matches = mem.pattern_match("port scan from eastern europe")

  # Mark outcome (was it a real threat?)
  mem.confirm("185.12.34.56", "port_scan", confirmed=True)

  # Forget (GDPR)
  mem.forget("personal_email@example.com")

CLI:
  python forge_memory.py                    # interactive
  python forge_memory.py --recall <entity>  # recall entity
  python forge_memory.py --stats            # memory statistics
  python forge_memory.py --timeline         # event timeline
  python forge_memory.py --server           # API :7348
"""

import sys, os, re, json, time, hashlib, sqlite3, threading
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# ── AI ─────────────────────────────────────────────────────────────────────────
try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True

    def ai_call(prompt, system="", max_tokens=1000):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or MEMORY_SYSTEM,
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
    def ai_call(p,s="",m=1000): return "Install anthropic."
    def ai_json(p,s="",m=600):  return None

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

MEMORY_SYSTEM = """You are FORGE MEMORY — the long-term intelligence of the FORGE system.

You synthesize patterns across weeks and months of data.
You connect dots that real-time analysis missed.
You reason like Sherlock Holmes with perfect recall.

When recalling an entity, you provide:
- Everything known about it across all cases
- Temporal patterns (how has it behaved over time?)
- Connections to other known entities
- Risk assessment based on full history
- Recommended action

Format: clear, structured, intelligence-grade analysis."""

# ── Paths ───────────────────────────────────────────────────────────────────────
MEMORY_DIR = Path("forge_memory")
MEMORY_DIR.mkdir(exist_ok=True)
DB_PATH    = MEMORY_DIR / "memory.db"

# ── Entity types ────────────────────────────────────────────────────────────────
ENTITY_TYPES = {
    "ip":       r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$",
    "domain":   r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
    "mac":      r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$",
    "email":    r"^[^@]+@[^@]+\.[^@]+$",
    "username": r"^@?[a-zA-Z0-9_.-]{2,50}$",
    "hash":     r"^[0-9a-fA-F]{32,64}$",
    "url":      r"^https?://",
    "phone":    r"^\+?[\d\s\-()]{7,20}$",
}

def detect_entity_type(entity):
    """Auto-detect entity type from value."""
    for etype, pattern in ENTITY_TYPES.items():
        if re.match(pattern, str(entity)):
            return etype
    return "unknown"

def entity_id(entity, etype=None):
    """Create stable entity ID."""
    etype = etype or detect_entity_type(entity)
    return f"{etype}:{str(entity).lower().strip()}"

# ══════════════════════════════════════════════════════════════════════════════
# 🗄️ DATABASE SETUP
# ══════════════════════════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        PRAGMA journal_mode=WAL;

        -- Core entities table
        CREATE TABLE IF NOT EXISTS entities (
            id           TEXT PRIMARY KEY,
            value        TEXT NOT NULL,
            type         TEXT NOT NULL,
            first_seen   TEXT,
            last_seen    TEXT,
            seen_count   INTEGER DEFAULT 1,
            risk_score   REAL DEFAULT 0.0,
            confirmed    INTEGER DEFAULT 0,
            tags         TEXT DEFAULT '[]',
            notes        TEXT DEFAULT ''
        );

        -- Facts about entities
        CREATE TABLE IF NOT EXISTS facts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id    TEXT NOT NULL,
            fact_type    TEXT NOT NULL,
            fact_value   TEXT,
            confidence   REAL DEFAULT 0.5,
            source       TEXT,
            module       TEXT,
            case_id      TEXT,
            ts           TEXT,
            confirmed    INTEGER DEFAULT -1,  -- -1=unknown, 0=false, 1=true
            FOREIGN KEY (entity_id) REFERENCES entities(id)
        );

        -- Events (timestamped things that happened)
        CREATE TABLE IF NOT EXISTS events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id    TEXT,
            event_type   TEXT,
            description  TEXT,
            severity     TEXT DEFAULT 'info',
            source       TEXT,
            module       TEXT,
            case_id      TEXT,
            ts           TEXT,
            data         TEXT DEFAULT '{}'
        );

        -- Relationships between entities
        CREATE TABLE IF NOT EXISTS relationships (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_a     TEXT,
            entity_b     TEXT,
            relation     TEXT,
            strength     REAL DEFAULT 1.0,
            first_seen   TEXT,
            last_seen    TEXT,
            evidence     TEXT,
            UNIQUE(entity_a, entity_b, relation)
        );

        -- Patterns (recurring behaviors detected over time)
        CREATE TABLE IF NOT EXISTS patterns (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id    TEXT,
            pattern_type TEXT,
            description  TEXT,
            confidence   REAL DEFAULT 0.5,
            occurrences  INTEGER DEFAULT 1,
            first_seen   TEXT,
            last_seen    TEXT,
            evidence     TEXT DEFAULT '[]'
        );

        -- Learning outcomes (was our analysis correct?)
        CREATE TABLE IF NOT EXISTS outcomes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id    TEXT,
            fact_type    TEXT,
            predicted    TEXT,
            actual       TEXT,
            correct      INTEGER,
            ts           TEXT,
            notes        TEXT
        );

        -- Tool / capability gaps discovered
        CREATE TABLE IF NOT EXISTS tool_wishes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT,
            description  TEXT,
            capability   TEXT,
            priority     INTEGER DEFAULT 5,
            source       TEXT,
            ts           TEXT,
            built        INTEGER DEFAULT 0
        );

        -- Morning brief history
        CREATE TABLE IF NOT EXISTS briefs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           TEXT,
            title        TEXT,
            content      TEXT,
            insights_count INTEGER DEFAULT 0,
            top_finding  TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_facts_entity    ON facts(entity_id);
        CREATE INDEX IF NOT EXISTS idx_events_entity   ON events(entity_id);
        CREATE INDEX IF NOT EXISTS idx_events_ts       ON events(ts);
        CREATE INDEX IF NOT EXISTS idx_facts_type      ON facts(fact_type);
        CREATE INDEX IF NOT EXISTS idx_entities_type   ON entities(type);
        CREATE INDEX IF NOT EXISTS idx_entities_risk   ON entities(risk_score);
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 CORE MEMORY CLASS
# ══════════════════════════════════════════════════════════════════════════════

class Memory:
    """
    FORGE's long-term memory.
    Used by ALL modules to share intelligence across time.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # Warm cache for frequently accessed entities
        self._cache = {}
        self._cache_ts = {}
        self._cache_ttl = 300  # 5 min

    # ── REMEMBER ──────────────────────────────────────────────────────────────

    def remember(self, entity, fact_type, fact_value="", confidence=0.7,
                 source="forge", module="", case_id="", severity="info",
                 data=None):
        """
        Core memory write.
        Remember a fact about an entity.

        mem.remember("185.12.34.56", "port_scan",    confidence=0.8)
        mem.remember("evil.com",     "c2_domain",    confidence=0.95)
        mem.remember("john@evil.com","email_found",  fact_value="whois record")
        """
        etype  = detect_entity_type(entity)
        eid    = entity_id(entity, etype)
        now    = datetime.now().isoformat()

        with self._lock:
            conn = get_db()
            try:
                # Upsert entity
                existing = conn.execute(
                    "SELECT * FROM entities WHERE id=?", (eid,)
                ).fetchone()

                if existing:
                    conn.execute("""
                        UPDATE entities SET
                            last_seen  = ?,
                            seen_count = seen_count + 1,
                            risk_score = MAX(risk_score, ?)
                        WHERE id=?""",
                        (now, confidence * 100, eid)
                    )
                else:
                    conn.execute("""
                        INSERT INTO entities (id,value,type,first_seen,last_seen,risk_score)
                        VALUES (?,?,?,?,?,?)""",
                        (eid, str(entity), etype, now, now, confidence * 100)
                    )

                # Insert fact
                conn.execute("""
                    INSERT INTO facts
                    (entity_id,fact_type,fact_value,confidence,source,module,case_id,ts)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (eid, fact_type, str(fact_value)[:1000],
                     confidence, source, module, case_id, now)
                )

                # Insert event
                conn.execute("""
                    INSERT INTO events
                    (entity_id,event_type,description,severity,source,module,case_id,ts,data)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (eid, fact_type,
                     f"{fact_type}: {str(fact_value)[:200]}",
                     severity, source, module, case_id, now,
                     json.dumps(data or {}))
                )

                conn.commit()

                # Invalidate cache
                self._cache.pop(eid, None)

                rprint(f"  [dim]🧠 Memory: {entity} → {fact_type} ({confidence:.0%})[/dim]")

            finally:
                conn.close()

        return eid

    def remember_relationship(self, entity_a, entity_b, relation,
                              strength=1.0, evidence=""):
        """Remember a relationship between two entities."""
        eid_a = entity_id(entity_a)
        eid_b = entity_id(entity_b)
        now   = datetime.now().isoformat()

        # Ensure both entities exist
        self.remember(entity_a, "entity_created", source="relationship")
        self.remember(entity_b, "entity_created", source="relationship")

        with self._lock:
            conn = get_db()
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO relationships
                    (entity_a,entity_b,relation,strength,first_seen,last_seen,evidence)
                    VALUES (?,?,?,?,
                        COALESCE((SELECT first_seen FROM relationships
                                  WHERE entity_a=? AND entity_b=? AND relation=?),?),
                        ?,?)""",
                    (eid_a, eid_b, relation, strength,
                     eid_a, eid_b, relation, now,
                     now, evidence[:500])
                )
                conn.commit()
            finally:
                conn.close()

    def add_pattern(self, entity, pattern_type, description, confidence=0.7, evidence=None):
        """Record a recurring behavioral pattern."""
        eid = entity_id(entity)
        now = datetime.now().isoformat()

        with self._lock:
            conn = get_db()
            try:
                existing = conn.execute("""
                    SELECT id, occurrences, confidence FROM patterns
                    WHERE entity_id=? AND pattern_type=?""",
                    (eid, pattern_type)
                ).fetchone()

                if existing:
                    # Update existing pattern — increase confidence
                    new_conf = min((existing["confidence"] + confidence) / 2 + 0.05, 1.0)
                    conn.execute("""
                        UPDATE patterns SET
                            occurrences = occurrences + 1,
                            confidence  = ?,
                            last_seen   = ?,
                            description = ?
                        WHERE id=?""",
                        (new_conf, now, description, existing["id"])
                    )
                else:
                    conn.execute("""
                        INSERT INTO patterns
                        (entity_id,pattern_type,description,confidence,first_seen,last_seen,evidence)
                        VALUES (?,?,?,?,?,?,?)""",
                        (eid, pattern_type, description[:500], confidence,
                         now, now, json.dumps(evidence or []))
                    )
                conn.commit()
            finally:
                conn.close()

    # ── RECALL ────────────────────────────────────────────────────────────────

    def recall(self, entity, full=False):
        """
        Recall everything known about an entity.

        Returns complete intelligence dossier.
        """
        eid   = entity_id(entity)
        now_t = time.time()

        # Check cache
        if eid in self._cache and (now_t - self._cache_ts.get(eid,0)) < self._cache_ttl:
            return self._cache[eid]

        conn = get_db()
        try:
            # Entity record
            ent = conn.execute(
                "SELECT * FROM entities WHERE id=?", (eid,)
            ).fetchone()

            if not ent:
                return None

            # All facts
            facts = conn.execute(
                "SELECT * FROM facts WHERE entity_id=? ORDER BY ts DESC",
                (eid,)
            ).fetchall()

            # Recent events
            events = conn.execute("""
                SELECT * FROM events WHERE entity_id=?
                ORDER BY ts DESC LIMIT 50""",
                (eid,)
            ).fetchall()

            # Patterns
            patterns = conn.execute(
                "SELECT * FROM patterns WHERE entity_id=? ORDER BY confidence DESC",
                (eid,)
            ).fetchall()

            # Relationships
            rels_out = conn.execute("""
                SELECT r.*, e.value as other_value, e.type as other_type
                FROM relationships r
                JOIN entities e ON e.id = r.entity_b
                WHERE r.entity_a=? ORDER BY r.strength DESC LIMIT 20""",
                (eid,)
            ).fetchall()

            rels_in = conn.execute("""
                SELECT r.*, e.value as other_value, e.type as other_type
                FROM relationships r
                JOIN entities e ON e.id = r.entity_a
                WHERE r.entity_b=? ORDER BY r.strength DESC LIMIT 20""",
                (eid,)
            ).fetchall()

            result = {
                "entity":        dict(ent),
                "facts":         [dict(f) for f in facts[:20 if not full else 100]],
                "events":        [dict(e) for e in events],
                "patterns":      [dict(p) for p in patterns],
                "relationships": {
                    "outgoing": [dict(r) for r in rels_out],
                    "incoming": [dict(r) for r in rels_in],
                },
                "summary": {
                    "fact_count":     len(facts),
                    "event_count":    len(events),
                    "pattern_count":  len(patterns),
                    "relationship_count": len(rels_out)+len(rels_in),
                    "risk_score":     ent["risk_score"],
                    "first_seen":     ent["first_seen"],
                    "last_seen":      ent["last_seen"],
                    "seen_count":     ent["seen_count"],
                },
            }

            # Cache result
            self._cache[eid]    = result
            self._cache_ts[eid] = now_t

            return result

        finally:
            conn.close()

    def seen_before(self, entity):
        """
        Quick check: have we seen this entity before?
        Returns history summary or None.
        """
        eid  = entity_id(entity)
        conn = get_db()
        try:
            ent = conn.execute(
                "SELECT * FROM entities WHERE id=?", (eid,)
            ).fetchone()
            if not ent: return None

            facts = conn.execute("""
                SELECT fact_type, COUNT(*) as count, MAX(ts) as last_ts, MAX(confidence) as max_conf
                FROM facts WHERE entity_id=?
                GROUP BY fact_type ORDER BY last_ts DESC LIMIT 10""",
                (eid,)
            ).fetchall()

            return {
                "seen":       True,
                "first_seen": ent["first_seen"],
                "last_seen":  ent["last_seen"],
                "seen_count": ent["seen_count"],
                "risk_score": ent["risk_score"],
                "fact_types": [dict(f) for f in facts],
            }
        finally:
            conn.close()

    def pattern_match(self, description, entity_type=None, limit=10):
        """
        Find entities with similar patterns.
        Simple keyword matching across descriptions.
        """
        words   = [w.lower() for w in description.split() if len(w) > 3]
        results = []

        conn = get_db()
        try:
            # Search patterns
            for word in words[:5]:
                rows = conn.execute("""
                    SELECT p.*, e.value, e.type, e.risk_score
                    FROM patterns p
                    JOIN entities e ON e.id = p.entity_id
                    WHERE p.description LIKE ?
                    AND (? IS NULL OR e.type=?)
                    ORDER BY p.confidence DESC LIMIT ?""",
                    (f"%{word}%", entity_type, entity_type, limit)
                ).fetchall()

                for row in rows:
                    if row["entity_id"] not in {r.get("entity_id") for r in results}:
                        results.append(dict(row))

            # Also search facts
            for word in words[:3]:
                rows = conn.execute("""
                    SELECT f.*, e.value, e.type, e.risk_score
                    FROM facts f
                    JOIN entities e ON e.id = f.entity_id
                    WHERE f.fact_value LIKE ? OR f.fact_type LIKE ?
                    AND (? IS NULL OR e.type=?)
                    ORDER BY f.confidence DESC LIMIT ?""",
                    (f"%{word}%", f"%{word}%", entity_type, entity_type, limit)
                ).fetchall()

                for row in rows:
                    if row["entity_id"] not in {r.get("entity_id") for r in results}:
                        results.append(dict(row))

        finally:
            conn.close()

        return results[:limit]

    def get_timeline(self, hours=24, entity=None, severity=None):
        """Get event timeline."""
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        conn  = get_db()
        try:
            if entity:
                eid  = entity_id(entity)
                rows = conn.execute("""
                    SELECT e.*, en.value as entity_value
                    FROM events e
                    JOIN entities en ON en.id = e.entity_id
                    WHERE e.entity_id=? AND e.ts > ?
                    ORDER BY e.ts DESC""",
                    (eid, since)
                ).fetchall()
            else:
                where = "AND severity=?" if severity else ""
                args  = [since] + ([severity] if severity else [])
                rows  = conn.execute(f"""
                    SELECT e.*, en.value as entity_value
                    FROM events e
                    JOIN entities en ON en.id = e.entity_id
                    WHERE e.ts > ? {where}
                    ORDER BY e.ts DESC LIMIT 200""",
                    args
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def top_risk_entities(self, limit=20, entity_type=None):
        """Get highest risk entities."""
        conn = get_db()
        try:
            where = "WHERE type=?" if entity_type else ""
            args  = ([entity_type] if entity_type else []) + [limit]
            rows  = conn.execute(f"""
                SELECT * FROM entities
                {where}
                ORDER BY risk_score DESC, seen_count DESC
                LIMIT ?""", args
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_relationships(self, entity, depth=2):
        """Get entity relationship network up to depth."""
        eid     = entity_id(entity)
        visited = set()
        graph   = {"nodes":[], "edges":[]}
        queue   = [(eid, 0)]

        conn = get_db()
        try:
            while queue:
                current, d = queue.pop(0)
                if current in visited or d > depth: continue
                visited.add(current)

                ent = conn.execute(
                    "SELECT * FROM entities WHERE id=?", (current,)
                ).fetchone()
                if ent:
                    graph["nodes"].append(dict(ent))

                # Outgoing
                rels = conn.execute("""
                    SELECT * FROM relationships
                    WHERE entity_a=? OR entity_b=?""",
                    (current, current)
                ).fetchall()

                for rel in rels:
                    edge = dict(rel)
                    graph["edges"].append(edge)
                    other = rel["entity_b"] if rel["entity_a"]==current else rel["entity_a"]
                    if other not in visited:
                        queue.append((other, d+1))
        finally:
            conn.close()

        return graph

    # ── LEARNING ──────────────────────────────────────────────────────────────

    def confirm(self, entity, fact_type, confirmed=True, notes=""):
        """Mark a fact as confirmed or false positive."""
        eid  = entity_id(entity)
        now  = datetime.now().isoformat()
        conn = get_db()
        try:
            # Update the most recent matching fact
            conn.execute("""
                UPDATE facts SET confirmed=?
                WHERE entity_id=? AND fact_type=?
                AND id=(SELECT id FROM facts WHERE entity_id=? AND fact_type=?
                        ORDER BY ts DESC LIMIT 1)""",
                (int(confirmed), eid, fact_type, eid, fact_type)
            )

            # Record outcome
            conn.execute("""
                INSERT INTO outcomes (entity_id,fact_type,predicted,actual,correct,ts,notes)
                VALUES (?,?,?,?,?,?,?)""",
                (eid, fact_type, fact_type,
                 fact_type if confirmed else "false_positive",
                 int(confirmed), now, notes)
            )

            # Update risk score
            if confirmed:
                conn.execute("""
                    UPDATE entities SET
                        confirmed  = 1,
                        risk_score = MIN(risk_score + 10, 100)
                    WHERE id=?""", (eid,)
                )
            else:
                # False positive — reduce risk
                conn.execute("""
                    UPDATE entities SET
                        risk_score = MAX(risk_score - 15, 0)
                    WHERE id=?""", (eid,)
                )

            conn.commit()
            self._cache.pop(eid, None)
        finally:
            conn.close()

    def accuracy_stats(self):
        """How accurate has FORGE been?"""
        conn = get_db()
        try:
            total    = conn.execute("SELECT COUNT(*) as n FROM outcomes").fetchone()["n"]
            correct  = conn.execute(
                "SELECT COUNT(*) as n FROM outcomes WHERE correct=1"
            ).fetchone()["n"]
            fp_count = conn.execute(
                "SELECT COUNT(*) as n FROM outcomes WHERE correct=0"
            ).fetchone()["n"]

            by_type  = conn.execute("""
                SELECT fact_type, COUNT(*) as total,
                       SUM(correct) as correct_count
                FROM outcomes GROUP BY fact_type
                ORDER BY total DESC LIMIT 10""").fetchall()

            return {
                "total_outcomes": total,
                "correct":        correct,
                "false_positives":fp_count,
                "accuracy":       round(correct/max(total,1)*100, 1),
                "by_type":        [dict(r) for r in by_type],
            }
        finally:
            conn.close()

    # ── FORGET ────────────────────────────────────────────────────────────────

    def forget(self, entity, reason="gdpr_request"):
        """
        Remove all memory of an entity.
        GDPR compliance.
        """
        eid  = entity_id(entity)
        conn = get_db()
        try:
            conn.execute("DELETE FROM facts         WHERE entity_id=?", (eid,))
            conn.execute("DELETE FROM events        WHERE entity_id=?", (eid,))
            conn.execute("DELETE FROM patterns      WHERE entity_id=?", (eid,))
            conn.execute("DELETE FROM outcomes      WHERE entity_id=?", (eid,))
            conn.execute("DELETE FROM relationships WHERE entity_a=? OR entity_b=?", (eid,eid))
            conn.execute("DELETE FROM entities      WHERE id=?",        (eid,))
            conn.commit()
            self._cache.pop(eid, None)
            rprint(f"  [dim]🧠 Forgotten: {entity} ({reason})[/dim]")
        finally:
            conn.close()

    # ── STATS ─────────────────────────────────────────────────────────────────

    def stats(self):
        """Memory statistics."""
        conn = get_db()
        try:
            return {
                "total_entities":     conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                "total_facts":        conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0],
                "total_events":       conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
                "total_patterns":     conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0],
                "total_relationships":conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0],
                "high_risk_entities": conn.execute(
                    "SELECT COUNT(*) FROM entities WHERE risk_score > 70"
                ).fetchone()[0],
                "confirmed_threats":  conn.execute(
                    "SELECT COUNT(*) FROM entities WHERE confirmed=1"
                ).fetchone()[0],
                "entity_types":       dict(conn.execute(
                    "SELECT type, COUNT(*) FROM entities GROUP BY type"
                ).fetchall()),
                "db_size_kb":         round(DB_PATH.stat().st_size/1024, 1) if DB_PATH.exists() else 0,
            }
        finally:
            conn.close()

    # ── AI ANALYSIS ───────────────────────────────────────────────────────────

    def analyze_entity(self, entity):
        """Full AI-powered analysis of everything known about an entity."""
        data = self.recall(entity, full=True)
        if not data:
            return f"No memory of {entity}."

        if not AI_AVAILABLE:
            return json.dumps(data["summary"], indent=2)

        facts_txt    = "\n".join(
            f"  [{f['confidence']:.0%}] {f['fact_type']}: {f['fact_value'][:80]}"
            for f in data["facts"][:15]
        )
        patterns_txt = "\n".join(
            f"  [{p['occurrences']}x] {p['pattern_type']}: {p['description'][:80]}"
            for p in data["patterns"][:5]
        )
        rels_txt     = "\n".join(
            f"  {r['relation']} → {r['other_value']}"
            for r in data["relationships"]["outgoing"][:5]
        )

        return ai_call(
            f"FORGE MEMORY — Full Entity Analysis\n\n"
            f"Entity: {entity}\n"
            f"Type: {data['entity']['type']}\n"
            f"First seen: {data['summary']['first_seen']}\n"
            f"Times encountered: {data['summary']['seen_count']}\n"
            f"Risk score: {data['summary']['risk_score']:.0f}/100\n\n"
            f"Known facts:\n{facts_txt}\n\n"
            f"Behavioral patterns:\n{patterns_txt or 'None detected'}\n\n"
            f"Relationships:\n{rels_txt or 'None known'}\n\n"
            "Sherlock-style full analysis:\n"
            "What is this entity? What have we learned over time?\n"
            "What does the pattern tell us? What is the risk?\n"
            "What should we do?",
            max_tokens=800
        )

    def synthesize_recent(self, hours=24):
        """AI synthesis of everything that happened recently."""
        timeline = self.get_timeline(hours=hours)
        top_risk = self.top_risk_entities(10)

        if not timeline and not top_risk:
            return "No recent events in memory."

        if not AI_AVAILABLE:
            return f"{len(timeline)} events in last {hours}h."

        recent_txt = "\n".join(
            f"  {e['ts'][:19]} [{e['severity']}] {e['entity_value']}: {e['event_type']}"
            for e in timeline[:20]
        )
        risk_txt   = "\n".join(
            f"  {r['value']} ({r['type']}) risk:{r['risk_score']:.0f} seen:{r['seen_count']}x"
            for r in top_risk[:5]
        )

        return ai_call(
            f"FORGE MEMORY — {hours}h Intelligence Summary\n\n"
            f"Events ({len(timeline)} total):\n{recent_txt}\n\n"
            f"Top risk entities:\n{risk_txt}\n\n"
            "Synthesize this into an intelligence briefing:\n"
            "What happened? What patterns emerged?\n"
            "What requires immediate attention?\n"
            "What can wait?",
            max_tokens=700
        )

    def wish_for_tool(self, name, description, capability, priority=5, source="dream"):
        """Record a tool that FORGE wishes it had."""
        conn = get_db()
        try:
            conn.execute("""
                INSERT INTO tool_wishes (name,description,capability,priority,source,ts)
                VALUES (?,?,?,?,?,?)""",
                (name, description, capability, priority, source,
                 datetime.now().isoformat())
            )
            conn.commit()
            rprint(f"  [dim]🛠 Tool wish: {name}[/dim]")
        finally:
            conn.close()

    def save_brief(self, title, content, insights_count=0, top_finding=""):
        """Save morning brief to history."""
        conn = get_db()
        try:
            conn.execute("""
                INSERT INTO briefs (ts,title,content,insights_count,top_finding)
                VALUES (?,?,?,?,?)""",
                (datetime.now().isoformat(), title, content[:5000],
                 insights_count, top_finding[:500])
            )
            conn.commit()
        finally:
            conn.close()

# ── Module-level singleton ────────────────────────────────────────────────────
_memory_instance = None

def get_memory():
    """Get global Memory instance (singleton)."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = Memory()
    return _memory_instance

# ── Convenience functions for other FORGE modules ─────────────────────────────

def remember(entity, fact_type, fact_value="", confidence=0.7,
             source="forge", module="", **kwargs):
    """Quick remember — used by all FORGE modules."""
    return get_memory().remember(entity, fact_type, fact_value,
                                confidence, source, module, **kwargs)

def recall(entity):
    """Quick recall — used by all FORGE modules."""
    return get_memory().recall(entity)

def seen_before(entity):
    """Quick seen_before check — used by all FORGE modules."""
    return get_memory().seen_before(entity)

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API SERVER
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7348):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    mem = Memory()

    class MemoryAPI(BaseHTTPRequestHandler):
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
            if path=="/api/stats":
                self._json(mem.stats())
            elif path=="/api/timeline":
                self._json({"events":mem.get_timeline(24)})
            elif path=="/api/top_risk":
                self._json({"entities":mem.top_risk_entities(20)})
            elif path=="/api/accuracy":
                self._json(mem.accuracy_stats())
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path=urlparse(self.path).path
            body=self._body()

            if path=="/api/remember":
                eid = mem.remember(
                    body.get("entity",""),
                    body.get("fact_type",""),
                    body.get("fact_value",""),
                    float(body.get("confidence",0.7)),
                    body.get("source","api"),
                    body.get("module",""),
                )
                self._json({"ok":True,"entity_id":eid})

            elif path=="/api/recall":
                entity = body.get("entity","")
                if not entity: self._json({"error":"entity required"},400); return
                result = mem.recall(entity)
                self._json(result or {"error":"not found"})

            elif path=="/api/seen_before":
                entity = body.get("entity","")
                result = mem.seen_before(entity)
                self._json(result or {"seen":False})

            elif path=="/api/analyze":
                entity = body.get("entity","")
                result = mem.analyze_entity(entity)
                self._json({"analysis":result})

            elif path=="/api/confirm":
                mem.confirm(body.get("entity",""),body.get("fact_type",""),
                           body.get("confirmed",True),body.get("notes",""))
                self._json({"ok":True})

            elif path=="/api/forget":
                mem.forget(body.get("entity",""),body.get("reason","request"))
                self._json({"ok":True})

            elif path=="/api/pattern_match":
                results=mem.pattern_match(body.get("description",""),body.get("type"))
                self._json({"matches":results})

            elif path=="/api/synthesize":
                hours=int(body.get("hours",24))
                result=mem.synthesize_recent(hours)
                self._json({"synthesis":result})

            elif path=="/api/relationship":
                mem.remember_relationship(
                    body.get("entity_a",""),body.get("entity_b",""),
                    body.get("relation",""),float(body.get("strength",1.0)),
                    body.get("evidence","")
                )
                self._json({"ok":True})

            else:
                self._json({"error":"unknown"},404)

    server=HTTPServer(("0.0.0.0",port),MemoryAPI)
    rprint(f"  [yellow]🧠 FORGE MEMORY API: http://localhost:{port}[/yellow]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# 🎮 MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ███╗   ███╗███████╗███╗   ███╗ ██████╗ ██████╗ ██╗   ██╗
  ████╗ ████║██╔════╝████╗ ████║██╔═══██╗██╔══██╗╚██╗ ██╔╝
  ██╔████╔██║█████╗  ██╔████╔██║██║   ██║██████╔╝ ╚████╔╝
  ██║╚██╔╝██║██╔══╝  ██║╚██╔╝██║██║   ██║██╔══██╗  ╚██╔╝
  ██║ ╚═╝ ██║███████╗██║ ╚═╝ ██║╚██████╔╝██║  ██║   ██║
  ╚═╝     ╚═╝╚══════╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝
[/yellow]
[bold]  🧠 FORGE MEMORY — Persistent Intelligence Memory[/bold]
[dim]  FORGE never forgets. Gets smarter every day.[/dim]
"""

def interactive():
    rprint(BANNER)
    mem = Memory()
    s   = mem.stats()
    rprint(f"  [dim]Entities:      {s['total_entities']}[/dim]")
    rprint(f"  [dim]Facts:         {s['total_facts']}[/dim]")
    rprint(f"  [dim]High Risk:     {s['high_risk_entities']}[/dim]")
    rprint(f"  [dim]DB Size:       {s['db_size_kb']}KB[/dim]\n")
    rprint("[dim]Commands: recall | remember | timeline | risk | stats | analyze | confirm | forget | server[/dim]\n")

    while True:
        try:
            inp = console.input if RICH else input
            raw = inp("[yellow bold]🧠 memory >[/yellow bold] ").strip()
            if not raw: continue
            parts = raw.split(None, 2)
            cmd   = parts[0].lower()
            args  = parts[1] if len(parts)>1 else ""
            args2 = parts[2] if len(parts)>2 else ""

            if cmd in ("quit","exit","q"):
                rprint("[dim]Memory offline.[/dim]"); break

            elif cmd == "recall":
                if not args: rprint("[yellow]Usage: recall <entity>[/yellow]"); continue
                history = mem.seen_before(args)
                if not history:
                    rprint(f"  [dim]No memory of: {args}[/dim]")
                else:
                    rprint(f"\n  [bold]Memory: {args}[/bold]")
                    rprint(f"  First seen:  {history['first_seen'][:19]}")
                    rprint(f"  Last seen:   {history['last_seen'][:19]}")
                    rprint(f"  Encountered: {history['seen_count']}x")
                    rprint(f"  Risk score:  {history['risk_score']:.0f}/100")
                    rprint(f"\n  [bold]Known facts:[/bold]")
                    for f in history["fact_types"][:8]:
                        rprint(f"    [{f['max_conf']:.0%}] {f['fact_type']} ({f['count']}x) — last: {f['last_ts'][:10]}")
                    # Full AI analysis
                    analysis = mem.analyze_entity(args)
                    rprint(Panel(analysis[:600], border_style="yellow",
                                title=f"🧠 Memory Analysis: {args}"))

            elif cmd == "remember":
                if not args or not args2:
                    rprint("[yellow]Usage: remember <entity> <fact_type>[/yellow]"); continue
                mem.remember(args, args2, source="manual", confidence=0.9)
                rprint(f"  [green]Remembered: {args} → {args2}[/green]")

            elif cmd == "timeline":
                hours   = int(args) if args.isdigit() else 24
                events  = mem.get_timeline(hours=hours)
                rprint(f"\n  [bold]Timeline: last {hours}h ({len(events)} events)[/bold]")
                for e in events[:15]:
                    sev   = e.get("severity","info")
                    color = {"alert":"red","warning":"yellow","info":"dim"}.get(sev,"dim")
                    rprint(f"  [{color}]{e['ts'][11:19]}[/{color}]  {e['entity_value']:<20} {e['event_type']}")

            elif cmd == "risk":
                entities = mem.top_risk_entities(15)
                if RICH:
                    t = Table(border_style="yellow", box=rbox.ROUNDED, title="Top Risk Entities")
                    t.add_column("Entity",     style="green",  width=25)
                    t.add_column("Type",       style="dim",    width=10)
                    t.add_column("Risk",       width=8)
                    t.add_column("Seen",       width=6)
                    t.add_column("Last Seen",  width=12)
                    for e in entities:
                        risk_color = "red" if e["risk_score"]>70 else "yellow" if e["risk_score"]>40 else "green"
                        t.add_row(
                            e["value"][:24], e["type"],
                            f"[{risk_color}]{e['risk_score']:.0f}[/{risk_color}]",
                            str(e["seen_count"]),
                            e["last_seen"][:10] if e["last_seen"] else ""
                        )
                    console.print(t)
                else:
                    for e in entities:
                        print(f"  {e['value']:<25} {e['risk_score']:.0f}/100 seen:{e['seen_count']}x")

            elif cmd == "stats":
                s = mem.stats()
                rprint(f"\n  [bold]🧠 FORGE MEMORY STATS[/bold]")
                rprint(f"  Entities:       {s['total_entities']}")
                rprint(f"  Facts:          {s['total_facts']}")
                rprint(f"  Events:         {s['total_events']}")
                rprint(f"  Patterns:       {s['total_patterns']}")
                rprint(f"  Relationships:  {s['total_relationships']}")
                rprint(f"  High risk:      {s['high_risk_entities']}")
                rprint(f"  Confirmed:      {s['confirmed_threats']}")
                rprint(f"  DB size:        {s['db_size_kb']}KB")
                rprint(f"\n  [bold]By type:[/bold]")
                for etype, count in s["entity_types"].items():
                    rprint(f"    {etype:<12} {count}")
                acc = mem.accuracy_stats()
                if acc["total_outcomes"]:
                    rprint(f"\n  [bold]Accuracy:[/bold] {acc['accuracy']}% ({acc['correct']}/{acc['total_outcomes']})")

            elif cmd == "analyze":
                if not args: rprint("[yellow]Usage: analyze <entity>[/yellow]"); continue
                analysis = mem.analyze_entity(args)
                rprint(Panel(analysis[:700], border_style="yellow",
                            title=f"🧠 Analysis: {args}"))

            elif cmd == "confirm":
                if not args or not args2:
                    rprint("[yellow]Usage: confirm <entity> <fact_type>[/yellow]"); continue
                mem.confirm(args, args2, confirmed=True)
                rprint(f"  [green]Confirmed: {args} → {args2}[/green]")

            elif cmd == "false":
                if not args or not args2:
                    rprint("[yellow]Usage: false <entity> <fact_type>[/yellow]"); continue
                mem.confirm(args, args2, confirmed=False)
                rprint(f"  [dim]False positive: {args} → {args2}[/dim]")

            elif cmd == "forget":
                if not args: rprint("[yellow]Usage: forget <entity>[/yellow]"); continue
                mem.forget(args)
                rprint(f"  [dim]Forgotten: {args}[/dim]")

            elif cmd == "synthesize":
                hours  = int(args) if args.isdigit() else 24
                result = mem.synthesize_recent(hours)
                rprint(Panel(result[:700], border_style="yellow",
                            title=f"🧠 {hours}h Intelligence Synthesis"))

            elif cmd == "server":
                rprint("[yellow]Starting MEMORY server on port 7348...[/yellow]")
                threading.Thread(target=start_server, daemon=True).start()
                time.sleep(0.5)
                rprint("[green]Memory API running on :7348[/green]")

            else:
                if AI_AVAILABLE:
                    r = ai_call(
                        f"Memory query: {raw}\n"
                        f"Memory stats: {json.dumps(mem.stats())}\n"
                        "How should FORGE memory respond?",
                        max_tokens=150
                    )
                    rprint(f"  [dim]{r[:150]}[/dim]")
                else:
                    rprint("[dim]Unknown command. Type 'help'.[/dim]")

        except (KeyboardInterrupt, EOFError):
            rprint("\n[dim]Memory offline.[/dim]"); break

def main():
    if "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7348
        start_server(port)
        return

    if "--recall" in sys.argv:
        idx    = sys.argv.index("--recall")
        entity = sys.argv[idx+1] if idx+1 < len(sys.argv) else ""
        if entity:
            rprint(BANNER)
            mem      = Memory()
            analysis = mem.analyze_entity(entity)
            rprint(Panel(analysis, border_style="yellow", title=f"🧠 {entity}"))
        return

    if "--stats" in sys.argv:
        rprint(BANNER)
        mem = Memory()
        s   = mem.stats()
        for k,v in s.items():
            rprint(f"  {k}: {v}")
        return

    if "--timeline" in sys.argv:
        rprint(BANNER)
        hours  = int(sys.argv[sys.argv.index("--timeline")+1]) if len(sys.argv) > sys.argv.index("--timeline")+1 else 24
        mem    = Memory()
        events = mem.get_timeline(hours)
        for e in events[:30]:
            print(f"  {e['ts'][:19]}  {e['entity_value']:<20}  {e['event_type']}")
        return

    interactive()

if __name__ == "__main__":
    main()
