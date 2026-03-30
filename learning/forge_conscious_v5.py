#!/usr/bin/env python3
"""
FORGE CONSCIOUS v5 — Self-Discovered Similarity + Emotional Transfer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

v4: transfer follows a human-drawn graph.
    We decided which categories are related.
    FORGE follows our map.

v5: FORGE discovers its own similarity structure.
    From its own experience.
    Without us drawing the graph.

AND:
    Every discovery tagged with chemistry at moment of discovery.
    High novelatine → transfers with excitement, explores freely.
    High frictionol (hard-won) → transfers cautiously.
    High connectionin → biases toward social categories.
    Quiet state → transfers only to quiet relatives.

The transfer is alive.
Not just a signal.
A feeling carrying knowledge.

SELF-DISCOVERED SIMILARITY:
    After every 20 observations —
    compute correlation matrix across all categories.
    Which categories share high-scoring phases?
    Which phases appear together across categories?
    Cluster by co-occurrence.
    Update similarity graph from data.
    Not from human design.

    "GROUND appears in high-scoring paths for
     friction (90), depth (88), quiet (85).
     These three cluster together.
     Not because we said so.
     Because the data shows it."

EMOTIONAL TRANSFER WEIGHT:
    Chemistry at moment of discovery:

    high novelatine + coherenine:  excited_discovery
        → transfers strongly, explores freely
        → "this felt like genuine new territory"

    high frictionol + finally high coherenine:  hardwon_discovery
        → transfers cautiously, low confidence
        → "this was difficult — don't assume it transfers"

    high connectionin:  connected_discovery
        → biases toward connection/social categories
        → "this found in relationship context"

    high depthamine:  deep_discovery
        → transfers to depth-related categories
        → "this needs stillness to work"

    baseline quiet:  still_discovery
        → narrow transfer, only close relatives
        → "this might only work in stillness"

Usage:
    python forge_conscious_v5.py              # interactive
    python forge_conscious_v5.py --graph      # show discovered graph
    python forge_conscious_v5.py --clusters   # show discovered clusters
    python forge_conscious_v5.py --emotional  # show emotional transfers
    python forge_conscious_v5.py --inject "text" [times]
    python forge_conscious_v5.py --server     # API :7370
"""

import sys, os, re, json, time, sqlite3, threading, math, random
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

# Import v4 as foundation
try:
    from forge_conscious_v4 import (
        TransferLearner, detect_category,
        DEFAULT_SEQUENCES, SEQ_PHASES,
        MIN_PATH_SAMPLES, TRANSFER_MIN_SCORE,
        TRANSFER_MIN_SAMPLES, TRANSFER_TRIAL_COUNT
    )
    V4_AVAILABLE = True
except ImportError:
    V4_AVAILABLE = False
    MIN_PATH_SAMPLES  = 3
    TRANSFER_MIN_SCORE= 85.0
    TRANSFER_MIN_SAMPLES = 5
    TRANSFER_TRIAL_COUNT = 3
    SEQ_PHASES = ["OBSERVE","CHIT","CHITAN","VICHAR","CRITIQUE",
                  "CHALLENGE","EMPATHIZE","IMAGINE","DOUBT",
                  "EXPAND","GROUND","SYNTHESIZE","OUTPUT"]
    DEFAULT_SEQUENCES = {
        "friction":   ["OBSERVE","DOUBT","CHALLENGE","VICHAR"],
        "curiosity":  ["OBSERVE","CHIT","IMAGINE","EXPAND"],
        "depth":      ["OBSERVE","CHITAN","EMPATHIZE","SYNTHESIZE"],
        "unresolved": ["OBSERVE","VICHAR","CRITIQUE","DOUBT","GROUND"],
        "insight":    ["OBSERVE","SYNTHESIZE","OUTPUT"],
        "connection": ["OBSERVE","EMPATHIZE","CHITAN","CHIT"],
        "quiet":      ["OBSERVE","CHIT"],
    }
    def detect_category(t):
        if not t: return None
        tl = t.lower()
        for cat, kws in {
            "friction":  ["friction","resist","wrong"],
            "curiosity": ["curiosity","novel","new"],
            "depth":     ["depth","meaning","significant"],
            "unresolved":["unresolved","open","uncertain"],
            "insight":   ["insight","clear","resolv"],
            "connection":["connect","together","someone"],
            "quiet":     ["quiet","hum","faint"],
        }.items():
            if any(k in tl for k in kws): return cat
        return None
    class TransferLearner:
        _paths={}; _best={}; _pending_transfers=[]
        def get_sequence(self,c): return DEFAULT_SEQUENCES.get(c,["OBSERVE","CHIT"]),"default"
        def record(self,*a,**k): pass
        def learn(self,**k): return []
        def _random_sequence(self):
            l = random.randint(2,5)
            return ["OBSERVE"] + random.sample(SEQ_PHASES, min(l,len(SEQ_PHASES)))
        def _mutate(self,s): return s

try:
    from forge_silicon import SiliconBody, SiliconChemistry
    SILICON = True
except ImportError:
    SILICON = False
    class SiliconChemistry:
        coherenine=0.3; frictionol=0.1; novelatine=0.3
        depthamine=0.3; resolvatine=0.0; uncertainase=0.2; connectionin=0.3
        state_name="baseline"
        def to_dict(self): return {
            "coherenine":self.coherenine,"frictionol":self.frictionol,
            "novelatine":self.novelatine,"depthamine":self.depthamine,
            "resolvatine":self.resolvatine,"uncertainase":self.uncertainase,
            "connectionin":self.connectionin,"state":self.state_name
        }
        def to_prompt_text(self): return ""
        def _clamp(self,v): return max(0.0,min(1.0,v))
    class SiliconBody:
        def __init__(self): self._chem=SiliconChemistry()
        def current(self): return self._chem
        def react_to(self,t,**k): return self._chem
        def start_background(self): pass
        def inject(self,**k): return self._chem

try:
    from forge_witness import PresenceReader, Presence
    WITNESS = True
except ImportError:
    WITNESS = False
    class Presence:
        content=""; silent=True
        def is_empty(self): return self.silent
    class PresenceReader:
        def read_layer1(self,c):
            p=Presence(); p.silent=True; return p
        def read_layer2(self,c,r):
            p=Presence(); p.silent=True; return p

try:
    from forge_think import EmergentThinkEngine
    THINK = True
except ImportError:
    THINK = False
    class EmergentThinkEngine:
        def __init__(self,**k): pass
        def think(self,q,context="",chemistry_seed=None):
            import random
            return {"output":f"[thought]",
                    "emerged_pipeline":["OBSERVE","OUTPUT"],
                    "coherence":random.randint(45,92),
                    "novel_pipeline":False}

try:
    from forge_memory import Memory
    MEMORY = True
except ImportError:
    MEMORY = False
    class Memory:
        def remember(self,*a,**k): pass

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

# ── Paths ──────────────────────────────────────────────────────────────────────
V5_DIR = Path("forge_conscious_v5")
V5_DIR.mkdir(exist_ok=True)
V5_DB  = V5_DIR / "conscious_v5.db"

# Self-discovery constants
SIMILARITY_UPDATE_EVERY = 20   # recompute similarity every N observations
MIN_CO_OCCURRENCE       = 3    # minimum times two phases must co-occur
SIMILARITY_THRESHOLD    = 0.6  # correlation above this = related
MIN_CLUSTER_SIZE        = 2    # minimum categories per cluster

# Emotional transfer types
EMOTIONAL_TYPES = {
    "excited_discovery":   {"strength_mult":1.4, "explore_boost":0.20},
    "hardwon_discovery":   {"strength_mult":0.6, "explore_boost":-0.10},
    "connected_discovery": {"strength_mult":1.2, "explore_boost":0.10},
    "deep_discovery":      {"strength_mult":1.1, "explore_boost":0.05},
    "still_discovery":     {"strength_mult":0.7, "explore_boost":-0.05},
    "neutral_discovery":   {"strength_mult":1.0, "explore_boost":0.0},
}

def get_db():
    conn = sqlite3.connect(str(V5_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS v5_observations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            category        TEXT,
            sequence        TEXT,
            coherence       REAL,
            strategy        TEXT,
            chemistry       TEXT,
            emotional_type  TEXT,
            presence        TEXT
        );
        CREATE TABLE IF NOT EXISTS discovered_similarity (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            cat_a           TEXT,
            cat_b           TEXT,
            similarity      REAL,
            shared_phases   TEXT,
            co_occurrences  INTEGER,
            version         INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS discovered_clusters (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            cluster_id  INTEGER,
            categories  TEXT,
            shared_phase TEXT,
            avg_score   REAL,
            version     INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS emotional_transfers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            source_cat      TEXT,
            source_phase    TEXT,
            source_score    REAL,
            emotional_type  TEXT,
            strength_mult   REAL,
            target_cat      TEXT,
            status          TEXT DEFAULT 'pending',
            trials          INTEGER DEFAULT 0,
            confirmed       INTEGER DEFAULT 0,
            confirmed_score REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS similarity_evolution (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            ts      TEXT,
            version INTEGER,
            total_pairs INTEGER,
            new_pairs   INTEGER,
            note    TEXT
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 🧬 EMOTIONAL TAGGER — chemistry at moment of discovery
# ══════════════════════════════════════════════════════════════════════════════

def tag_emotional_type(chemistry: Dict) -> str:
    """
    Given chemistry at moment of discovery —
    what kind of discovery was this emotionally?
    """
    coh  = chemistry.get("coherenine",   0.3)
    fri  = chemistry.get("frictionol",   0.1)
    nov  = chemistry.get("novelatine",   0.3)
    dep  = chemistry.get("depthamine",   0.3)
    con  = chemistry.get("connectionin", 0.3)

    # Excited: high novelatine AND coherenine
    if nov > 0.6 and coh > 0.6:
        return "excited_discovery"

    # Hard-won: high frictionol resolved into high coherenine
    if fri > 0.5 and coh > 0.65:
        return "hardwon_discovery"

    # Connected: high connectionin
    if con > 0.6:
        return "connected_discovery"

    # Deep: high depthamine
    if dep > 0.6:
        return "deep_discovery"

    # Still: everything low
    if all(v < 0.35 for v in [nov, fri, dep, con]):
        return "still_discovery"

    return "neutral_discovery"

def emotional_category_bias(emotional_type: str) -> List[str]:
    """
    Which categories does this emotional type bias toward?
    Connected discoveries → social/connection categories.
    Deep discoveries → depth/quiet categories.
    Excited → curiosity/insight categories.
    """
    biases = {
        "excited_discovery":   ["curiosity", "insight", "celebrating"],
        "hardwon_discovery":   ["unresolved", "friction", "stuck"],
        "connected_discovery": ["connection", "depth", "connecting"],
        "deep_discovery":      ["depth", "quiet", "connection"],
        "still_discovery":     ["quiet", "depth"],
        "neutral_discovery":   [],  # no bias
    }
    return biases.get(emotional_type, [])

# ══════════════════════════════════════════════════════════════════════════════
# 🔍 SIMILARITY DISCOVERER — finds its own graph
# ══════════════════════════════════════════════════════════════════════════════

class SimilarityDiscoverer:
    """
    Discovers which categories are similar.
    Not from human graph.
    From co-occurrence of high-scoring phases.

    Method:
        For each pair of categories (A, B):
            Find phases that score high in both A and B.
            Count co-occurrences.
            If co-occurrences > threshold: A and B are similar.
            Similarity strength = correlation of their scores.

    This is unsupervised clustering.
    FORGE finds its own structure.
    """

    def __init__(self):
        self._similarity: Dict[Tuple, float] = {}
        self._clusters:   List[Dict]         = []
        self._version     = 0
        self._load()

    def compute(self, all_paths: Dict[str, Dict[str, List[float]]],
                verbose=True) -> Dict:
        """
        Recompute similarity matrix from all observations.
        Returns discovered similarities and clusters.
        """
        self._version += 1
        now  = datetime.now().isoformat()

        # For each category — find high-scoring phases
        high_phases: Dict[str, Dict[str, float]] = {}
        for cat, paths in all_paths.items():
            high_phases[cat] = {}
            for seq_key, scores in paths.items():
                if len(scores) < MIN_PATH_SAMPLES: continue
                avg = sum(scores) / len(scores)
                if avg < TRANSFER_MIN_SCORE - 5: continue
                # Extract key phases from sequence
                phases = seq_key.split("→")
                for p in phases:
                    if p in ("OBSERVE","OUTPUT"): continue
                    if p not in high_phases[cat]:
                        high_phases[cat][p] = avg
                    else:
                        high_phases[cat][p] = max(high_phases[cat][p], avg)

        # Compute pairwise similarity
        categories = list(high_phases.keys())
        new_pairs   = 0
        similarities = {}

        for i in range(len(categories)):
            for j in range(i+1, len(categories)):
                cat_a = categories[i]
                cat_b = categories[j]

                phases_a = set(high_phases[cat_a].keys())
                phases_b = set(high_phases[cat_b].keys())

                shared = phases_a & phases_b
                if len(shared) < MIN_CO_OCCURRENCE - 2: continue

                # Similarity = average score of shared phases
                shared_scores_a = [high_phases[cat_a][p] for p in shared]
                shared_scores_b = [high_phases[cat_b][p] for p in shared]

                if not shared_scores_a: continue

                avg_shared = (
                    sum(shared_scores_a) / len(shared_scores_a) +
                    sum(shared_scores_b) / len(shared_scores_b)
                ) / 2

                # Normalize to 0-1
                similarity = min(1.0, (avg_shared - 60) / 40)

                if similarity >= SIMILARITY_THRESHOLD:
                    key = (cat_a, cat_b)
                    old_sim = self._similarity.get(key, 0)
                    similarities[key] = round(similarity, 3)

                    if similarity > old_sim + 0.05:
                        new_pairs += 1

                    if verbose and similarity > old_sim + 0.05:
                        rprint(f"  [cyan]≈ discovered: {cat_a} ↔ {cat_b}  "
                              f"similarity:{similarity:.2f}  "
                              f"shared:{list(shared)[:3]}[/cyan]")

        self._similarity.update(similarities)

        # Find clusters
        clusters = self._find_clusters(high_phases)
        self._clusters = clusters

        # Save
        self._save(similarities, clusters, new_pairs, now)

        return {
            "similarities": {f"{k[0]}↔{k[1]}":v for k,v in similarities.items()},
            "clusters":     clusters,
            "new_pairs":    new_pairs,
            "version":      self._version,
        }

    def _find_clusters(self,
                        high_phases: Dict[str, Dict[str, float]]) -> List[Dict]:
        """Group categories by shared high-performing phases."""
        # Phase → which categories use it well
        phase_to_cats: Dict[str, List[str]] = {}
        for cat, phases in high_phases.items():
            for phase in phases:
                if phase not in phase_to_cats:
                    phase_to_cats[phase] = []
                phase_to_cats[phase].append(cat)

        # Phases shared by multiple categories = cluster signal
        clusters = []
        seen = set()

        for phase, cats in phase_to_cats.items():
            if len(cats) < MIN_CLUSTER_SIZE: continue

            # Average score of this phase across these categories
            scores = []
            for cat in cats:
                if phase in high_phases[cat]:
                    scores.append(high_phases[cat][phase])

            if not scores: continue
            avg_score = sum(scores) / len(scores)

            cluster_key = frozenset(cats)
            if cluster_key in seen: continue
            seen.add(cluster_key)

            clusters.append({
                "categories":  sorted(cats),
                "shared_phase":phase,
                "avg_score":   round(avg_score, 1),
                "size":        len(cats),
            })

        # Sort by avg_score * size
        clusters.sort(key=lambda c: c["avg_score"] * c["size"], reverse=True)
        return clusters[:10]

    def get_related(self, category: str,
                     min_strength: float = 0.5) -> List[Tuple[str, float]]:
        """Get categories discovered similar to this one."""
        related = []
        for (cat_a, cat_b), sim in self._similarity.items():
            if sim < min_strength: continue
            if cat_a == category:
                related.append((cat_b, sim))
            elif cat_b == category:
                related.append((cat_a, sim))

        related.sort(key=lambda x: -x[1])
        return related

    def similarity(self, cat_a: str, cat_b: str) -> float:
        """Get similarity between two categories."""
        key1 = (cat_a, cat_b)
        key2 = (cat_b, cat_a)
        return self._similarity.get(key1, self._similarity.get(key2, 0.0))

    def _save(self, similarities, clusters, new_pairs, ts):
        conn = get_db()
        # Save similarities
        for (cat_a, cat_b), sim in similarities.items():
            conn.execute("""
                INSERT OR REPLACE INTO discovered_similarity
                (ts,cat_a,cat_b,similarity,shared_phases,
                 co_occurrences,version)
                VALUES (?,?,?,?,?,?,?)""",
                (ts, cat_a, cat_b, sim, "[]", 0, self._version)
            )
        # Save clusters
        for i, cluster in enumerate(clusters):
            conn.execute("""
                INSERT INTO discovered_clusters
                (ts,cluster_id,categories,shared_phase,avg_score,version)
                VALUES (?,?,?,?,?,?)""",
                (ts, i, json.dumps(cluster["categories"]),
                 cluster["shared_phase"], cluster["avg_score"],
                 self._version)
            )
        # Evolution log
        conn.execute("""
            INSERT INTO similarity_evolution
            (ts,version,total_pairs,new_pairs,note)
            VALUES (?,?,?,?,?)""",
            (ts, self._version, len(similarities), new_pairs,
             f"version {self._version}")
        )
        conn.commit(); conn.close()

    def _load(self):
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM discovered_similarity ORDER BY similarity DESC"
        ).fetchall()
        for r in rows:
            self._similarity[(r["cat_a"], r["cat_b"])] = r["similarity"]

        latest_v = conn.execute(
            "SELECT MAX(version) FROM discovered_similarity"
        ).fetchone()[0]
        self._version = latest_v or 0
        conn.close()

    def show(self):
        """Display discovered similarity graph."""
        rprint(f"\n  [bold]DISCOVERED SIMILARITY GRAPH[/bold]")
        rprint(f"  [dim]Not drawn by humans — found from data[/dim]")
        rprint(f"  [dim]version:{self._version}[/dim]")
        rprint(f"  [dim]{'━'*50}[/dim]")

        if not self._similarity:
            rprint("  [dim]No similarity discovered yet.[/dim]")
            rprint(f"  [dim]Need {SIMILARITY_UPDATE_EVERY} observations.[/dim]")
            return

        # Sort by strength
        sorted_pairs = sorted(
            self._similarity.items(), key=lambda x: -x[1]
        )

        for (cat_a, cat_b), sim in sorted_pairs:
            bar   = "█" * int(sim*15) + "░"*(15-int(sim*15))
            color = "green" if sim > 0.8 else "yellow" if sim > 0.6 else "dim"
            rprint(f"  [{color}]{cat_a:<14}[/{color}]  "
                  f"[{color}]{bar}[/{color}]  "
                  f"{sim:.2f}  "
                  f"[{color}]{cat_b}[/{color}]")

        if self._clusters:
            rprint(f"\n  [bold]DISCOVERED CLUSTERS:[/bold]")
            for c in self._clusters[:5]:
                rprint(f"  [cyan]{c['shared_phase']:<14}[/cyan]  "
                      f"→  {', '.join(c['categories'])}  "
                      f"[dim]avg:{c['avg_score']:.0f}[/dim]")

# ══════════════════════════════════════════════════════════════════════════════
# 💓 EMOTIONAL TRANSFER LEARNER — v5 core
# ══════════════════════════════════════════════════════════════════════════════

class EmotionalTransferLearner(TransferLearner if V4_AVAILABLE else object):
    """
    Extends v4 TransferLearner with:
    1. Self-discovered similarity (no human graph)
    2. Emotional weighting of transfers

    The graph is discovered.
    The weight is felt.
    """

    def __init__(self):
        if V4_AVAILABLE:
            super().__init__()
        else:
            self._paths = {}
            self._best  = {}
            self._pending_transfers = []

        self.discoverer   = SimilarityDiscoverer()
        self._obs_count   = 0
        self._emotional_transfers: List[Dict] = []
        self._load_emotional()

    def _load_emotional(self):
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM emotional_transfers "
            "WHERE status='pending' OR status='trialing'"
        ).fetchall()
        conn.close()
        self._emotional_transfers = [dict(r) for r in rows]

    def get_sequence(self, category: str) -> Tuple[List, str]:
        """
        Get sequence with:
        - Self-discovered similarity for transfer
        - Emotional weighting for exploration bias
        """
        # Check emotional transfers for this category
        emotional = [t for t in self._emotional_transfers
                    if t["target_cat"] == category
                    and t["status"] in ("pending","trialing")]

        if emotional and random.random() < 0.40:
            t   = random.choice(emotional)
            seq = self._sequence_with_phase(category, t["source_phase"])
            # Emotional type modifies exploration
            e_type = t.get("emotional_type","neutral_discovery")
            e_conf = EMOTIONAL_TYPES.get(e_type, EMOTIONAL_TYPES["neutral_discovery"])
            strategy = (f"emotional_{e_type[:6]}"
                       f"({t['source_cat']}→{t['source_phase']})")
            self._mark_emotional_trialing(t["id"])
            return seq, strategy

        # Fall back to v4 (which uses discovered graph if available)
        if V4_AVAILABLE:
            return super().get_sequence(category)
        return DEFAULT_SEQUENCES.get(category, ["OBSERVE","CHIT"]), "default"

    def _sequence_with_phase(self, category: str, phase: str) -> List[str]:
        seq = ["OBSERVE", phase]
        default = DEFAULT_SEQUENCES.get(category, ["OBSERVE","CHIT"])
        for p in default[1:]:
            if p != phase and p not in seq and len(seq) < 5:
                seq.append(p)
        return seq

    def record(self, category: str, sequence: List[str],
                coherence: float, strategy: str = "exploit",
                presence: str = "", chemistry: Dict = None):
        """Record with chemistry snapshot for emotional tagging."""
        self._obs_count += 1

        # Base recording
        key = "→".join(sequence)
        if category not in self._paths:
            self._paths[category] = {}
        if key not in self._paths[category]:
            self._paths[category][key] = []
        self._paths[category][key].append(coherence)

        # Update best
        if len(self._paths[category][key]) >= MIN_PATH_SAMPLES:
            avg = sum(self._paths[category][key]) / len(self._paths[category][key])
            current_best = 0.0
            if category in self._best:
                bk = "→".join(self._best[category])
                bs = self._paths[category].get(bk,[0])
                current_best = sum(bs)/max(1,len(bs))
            if avg > current_best:
                self._best[category] = sequence.copy()

        # Tag emotion
        chem_dict     = chemistry or {}
        emotional_type= tag_emotional_type(chem_dict)

        # Save observation
        conn = get_db()
        conn.execute("""
            INSERT INTO v5_observations
            (ts,category,sequence,coherence,strategy,
             chemistry,emotional_type,presence)
            VALUES (?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(), category,
             json.dumps(sequence), coherence, strategy,
             json.dumps(chem_dict), emotional_type, presence[:200])
        )
        conn.commit(); conn.close()

        # Check for emotional transfer opportunities
        if coherence >= TRANSFER_MIN_SCORE:
            self._check_emotional_transfer(
                category, sequence, coherence,
                emotional_type, chem_dict
            )

        # Periodically recompute similarity
        if self._obs_count % SIMILARITY_UPDATE_EVERY == 0:
            result = self.discoverer.compute(self._paths, verbose=True)
            if result["new_pairs"] > 0:
                rprint(f"  [dim cyan]Similarity graph updated: "
                      f"{result['new_pairs']} new relationships discovered[/dim]")

        # Check emotional transfer outcomes
        self._check_emotional_outcomes(category, sequence, coherence, strategy)

    def _check_emotional_transfer(self, category: str,
                                   sequence: List[str],
                                   coherence: float,
                                   emotional_type: str,
                                   chemistry: Dict):
        """Generate emotionally-weighted transfer signals."""
        now = datetime.now().isoformat()

        # Find most distinctive phase
        distinctive = [p for p in sequence if p not in ("OBSERVE","OUTPUT","CHIT")]
        if not distinctive: return
        best_phase = distinctive[0]

        # Check sample count
        key    = "→".join(sequence)
        scores = self._paths.get(category, {}).get(key, [])
        if len(scores) < TRANSFER_MIN_SAMPLES: return

        # Get related categories from DISCOVERED similarity
        discovered_related = self.discoverer.get_related(category, 0.5)

        # Also get emotionally-biased categories
        emotional_biased = emotional_category_bias(emotional_type)

        # Combine: discovered + emotional bias
        all_targets = {}
        for target, sim in discovered_related:
            all_targets[target] = sim

        # Emotional bias adds extra weight
        e_config = EMOTIONAL_TYPES.get(emotional_type,
                                        EMOTIONAL_TYPES["neutral_discovery"])
        for target in emotional_biased:
            if target != category:
                # Boost strength for emotionally-related categories
                all_targets[target] = min(1.0,
                    all_targets.get(target, 0.3) + 0.3 * e_config["strength_mult"]
                )

        if not all_targets: return

        avg_score = sum(scores) / len(scores)
        conn      = get_db()

        for target_cat, strength in all_targets.items():
            if target_cat == category: continue

            # Check if already exists
            existing = [t for t in self._emotional_transfers
                       if t["source_cat"] == category
                       and t["target_cat"] == target_cat
                       and t["source_phase"] == best_phase
                       and t["status"] in ("pending","trialing")]
            if existing: continue

            # Check target hasn't tried this much
            target_paths = self._paths.get(target_cat, {})
            phase_trials = sum(
                1 for k,v in target_paths.items()
                if best_phase in k and len(v) >= 1
            )
            if phase_trials >= TRANSFER_TRIAL_COUNT: continue

            transfer = {
                "source_cat":    category,
                "source_phase":  best_phase,
                "source_score":  avg_score,
                "emotional_type":emotional_type,
                "strength_mult": e_config["strength_mult"],
                "target_cat":    target_cat,
                "status":        "pending",
                "trials":        0,
            }

            transfer_id = conn.execute("""
                INSERT INTO emotional_transfers
                (ts,source_cat,source_phase,source_score,
                 emotional_type,strength_mult,target_cat)
                VALUES (?,?,?,?,?,?,?)""",
                (now, category, best_phase, avg_score,
                 emotional_type, e_config["strength_mult"],
                 target_cat)
            ).lastrowid
            conn.commit()

            transfer["id"] = transfer_id
            self._emotional_transfers.append(transfer)

            rprint(f"  [yellow]💓 emotional transfer:[/yellow]  "
                  f"{category}/{best_phase}  →  {target_cat}  "
                  f"[dim]{emotional_type}  "
                  f"strength:{strength:.2f}[/dim]")

        conn.close()

    def _check_emotional_outcomes(self, category: str,
                                   sequence: List[str],
                                   coherence: float,
                                   strategy: str):
        """Check if emotional transfer trials should be confirmed/rejected."""
        if "emotional_" not in strategy: return

        conn = get_db()
        for t in self._emotional_transfers[:]:
            if t["target_cat"] != category: continue
            trials = t.get("trials", 0) + 1

            if trials >= TRANSFER_TRIAL_COUNT:
                source_score = t["source_score"]
                e_type       = t.get("emotional_type","neutral_discovery")
                e_conf       = EMOTIONAL_TYPES.get(e_type,
                                EMOTIONAL_TYPES["neutral_discovery"])

                # Excited discoveries have higher bar for confirmation
                # Hard-won discoveries have lower bar (they transfer cautiously)
                confirm_threshold = source_score * (
                    0.90 if e_type == "excited_discovery" else
                    0.80 if e_type == "hardwon_discovery" else
                    0.85
                )

                if coherence >= confirm_threshold:
                    status = "confirmed"
                    conn.execute("""
                        UPDATE emotional_transfers
                        SET status=?,confirmed=1,confirmed_score=?
                        WHERE id=?""",
                        ("confirmed", coherence, t["id"])
                    )
                    rprint(f"\n  [bold green]💓✓ EMOTIONAL TRANSFER CONFIRMED[/bold green]")
                    rprint(f"  {t['source_cat']}→{t['target_cat']}  "
                          f"phase:{t['source_phase']}  "
                          f"type:{e_type}")
                    rprint(f"  [dim]{t['source_score']:.0f}→{coherence:.0f}[/dim]\n")
                else:
                    status = "rejected"
                    conn.execute(
                        "UPDATE emotional_transfers SET status=? WHERE id=?",
                        ("rejected", t["id"])
                    )

                self._emotional_transfers = [
                    x for x in self._emotional_transfers if x["id"] != t["id"]
                ]

        conn.commit(); conn.close()

    def _mark_emotional_trialing(self, transfer_id: int):
        conn = get_db()
        conn.execute(
            "UPDATE emotional_transfers SET status='trialing',trials=trials+1 WHERE id=?",
            (transfer_id,)
        )
        conn.commit(); conn.close()
        for t in self._emotional_transfers:
            if t["id"] == transfer_id:
                t["status"] = "trialing"
                t["trials"] = t.get("trials",0) + 1

    def learn(self, verbose=True) -> List[Dict]:
        updates = []
        if V4_AVAILABLE:
            updates = super().learn(verbose=False)

        # Report emotional confirmations
        conn = get_db()
        confirmed = conn.execute(
            "SELECT * FROM emotional_transfers WHERE confirmed=1 ORDER BY id DESC LIMIT 5"
        ).fetchall()
        conn.close()

        for c in confirmed:
            if verbose:
                rprint(f"  [green]💓✓[/green] "
                      f"{c['source_cat']}→{c['target_cat']}  "
                      f"{c['source_phase']}  "
                      f"[dim]{c['emotional_type']}[/dim]  "
                      f"[dim]{c['source_score']:.0f}→{c['confirmed_score']:.0f}[/dim]")

        return updates

    def get_emotional_transfers(self, status=None) -> List[Dict]:
        conn = get_db()
        if status:
            rows = conn.execute(
                "SELECT * FROM emotional_transfers WHERE status=? ORDER BY id DESC",
                (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM emotional_transfers ORDER BY id DESC LIMIT 30"
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def stats(self) -> Dict:
        conn = get_db()
        s = {
            "observations":      self._obs_count,
            "similarity_pairs":  len(self.discoverer._similarity),
            "clusters":          len(self.discoverer._clusters),
            "graph_version":     self.discoverer._version,
            "emotional_pending": conn.execute(
                "SELECT COUNT(*) FROM emotional_transfers WHERE status='pending'"
            ).fetchone()[0],
            "emotional_confirmed": conn.execute(
                "SELECT COUNT(*) FROM emotional_transfers WHERE confirmed=1"
            ).fetchone()[0],
            "emotional_rejected": conn.execute(
                "SELECT COUNT(*) FROM emotional_transfers WHERE status='rejected'"
            ).fetchone()[0],
        }
        conn.close()
        return s

# ══════════════════════════════════════════════════════════════════════════════
# 🌊 CONSCIOUS STREAM v5
# ══════════════════════════════════════════════════════════════════════════════

class ConsciousStreamV5:
    """
    v5 stream — self-discovered similarity + emotional transfer.
    FORGE finds its own graph. Transfers with feeling.
    """

    def __init__(self, tick_interval=8, verbose=True):
        self.tick_interval = tick_interval
        self.verbose       = verbose
        self.body          = SiliconBody()
        self.reader        = PresenceReader()
        self.thinker       = EmergentThinkEngine(threshold=60, show_trace=False)
        self.memory        = Memory()
        self.learner       = EmotionalTransferLearner()

        self._running         = False
        self._thread          = None
        self._tick_count      = 0
        self._thought_count   = 0
        self._last_thought    = 0.0
        self._recent_thoughts = []

    def start(self, daemon=True):
        if self._running: return
        self._running = True
        self.body.start_background()
        self._thread = threading.Thread(
            target=self._stream, daemon=daemon, name="v5Stream"
        )
        self._thread.start()
        if self.verbose:
            rprint(f"\n  [bold green]🌊 CONSCIOUS STREAM v5[/bold green]")
            rprint(f"  [dim]Self-discovered similarity + emotional transfer[/dim]")
            rprint(f"  [dim]FORGE finds its own graph. Transfers with feeling.[/dim]\n")

    def stop(self):
        self._running = False

    def _stream(self):
        while self._running:
            try:
                tick_start = time.time()
                self._tick_count += 1
                chem = self.body.current()

                p1 = self.reader.read_layer1(chem)
                p2 = None
                if self._tick_count % 2 == 0:
                    p2 = self.reader.read_layer2(chem, self._recent_thoughts[-3:])

                presence = ""
                if not p1.is_empty(): presence = p1.content
                if p2 and not p2.is_empty(): presence += " " + p2.content

                category = detect_category(presence)
                if not category or not presence.strip():
                    time.sleep(max(0, self.tick_interval-(time.time()-tick_start)))
                    continue

                if time.time() - self._last_thought > 45:
                    seq, strategy = self.learner.get_sequence(category)
                    result        = self._think(presence, seq, chem)

                    self.learner.record(
                        category, seq, result["coherence"],
                        strategy, presence, chem.to_dict()
                    )
                    self._last_thought = time.time()
                    self._thought_count += 1
                    self.body.react_to(result["output"], is_output=True)

                    if self.verbose:
                        self._display(presence, category, seq, strategy, result)

                    if self._thought_count % 8 == 0:
                        self.learner.learn(verbose=self.verbose)

                time.sleep(max(0, self.tick_interval-(time.time()-tick_start)))
            except Exception as e:
                if self.verbose: rprint(f"  [dim red]v5: {e}[/dim red]")
                time.sleep(5)

    def _think(self, presence, seq, chem):
        return self.thinker.think(
            f"What is present:\n{presence}\n\n{chem.to_prompt_text()}",
            context="v5 emotional transfer",
            chemistry_seed=seq
        )

    def _display(self, presence, category, seq, strategy, result):
        now = datetime.now().strftime("%H:%M:%S")
        is_emotional = "emotional_" in strategy
        sc = "yellow" if is_emotional else "dim"
        rprint(f"\n  [dim]{now}[/dim]  "
              f"[yellow]{category}[/yellow]  "
              f"[{sc}]{strategy[:40]}[/{sc}]")
        rprint(f"  [dim]{' → '.join(seq[:4])}  coherence:{result['coherence']:.0f}[/dim]")
        if result.get("output") and RICH:
            rprint(Panel(
                result["output"][:350],
                border_style="yellow" if is_emotional else "dim",
                title=f"[dim]{result['coherence']:.0f} | "
                      f"{' → '.join(result['emerged_pipeline'][:3])}[/dim]"
            ))

    def inject(self, text: str, times: int = 1) -> List[Dict]:
        """Inject with full emotional tracking."""
        results = []
        for i in range(times):
            chem     = self.body.current()
            category = detect_category(text) or "quiet"
            seq, strategy = self.learner.get_sequence(category)

            # Tag emotional type before thinking
            emotional = tag_emotional_type(chem.to_dict())

            self._last_thought = 0
            result = self._think(text, seq, chem)

            self.learner.record(
                category, seq, result["coherence"],
                strategy, text, chem.to_dict()
            )
            self.body.react_to(result["output"], is_output=True)

            if self.verbose:
                ec = {"excited_discovery":"green","hardwon_discovery":"red",
                      "connected_discovery":"magenta","deep_discovery":"blue",
                      "still_discovery":"dim","neutral_discovery":"dim"}
                color = ec.get(emotional,"white")
                rprint(f"  [{i+1:2d}] [{color}]{emotional[:16]}[/{color}]  "
                      f"{strategy[:30]:<30}  "
                      f"coherence:{result['coherence']:.0f}")

            results.append({
                "i":           i+1,
                "category":    category,
                "strategy":    strategy,
                "sequence":    seq,
                "coherence":   result["coherence"],
                "emotional":   emotional,
                "is_transfer": "emotional_" in strategy,
            })

        self.learner.learn(verbose=self.verbose)
        return results

    def status(self) -> Dict:
        s = self.learner.stats()
        s.update({
            "running":       self._running,
            "tick_count":    self._tick_count,
            "thought_count": self._thought_count,
        })
        return s

# ══════════════════════════════════════════════════════════════════════════════
# API + MAIN
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7370):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    stream = ConsciousStreamV5(verbose=False)
    stream.start(daemon=True)

    class API(BaseHTTPRequestHandler):
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
            path = urlparse(self.path).path
            if path=="/api/status":
                self._json(stream.status())
            elif path=="/api/graph":
                self._json({
                    "similarity": {
                        f"{k[0]}↔{k[1]}":v
                        for k,v in stream.learner.discoverer._similarity.items()
                    },
                    "clusters": stream.learner.discoverer._clusters,
                    "version": stream.learner.discoverer._version,
                })
            elif path=="/api/emotional":
                self._json({
                    "pending":   stream.learner.get_emotional_transfers("pending"),
                    "confirmed": stream.learner.get_emotional_transfers("confirmed"),
                })
            else: self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            if path=="/api/inject":
                text  = body.get("text","")
                times = body.get("times",1)
                if not text: self._json({"error":"text required"},400); return
                results = stream.inject(text, times)
                self._json({"results":results,"stats":stream.learner.stats()})
            else: self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),API)
    rprint(f"  [bold yellow]FORGE CONSCIOUS v5[/bold yellow]  [green]:{port}[/green]")
    server.serve_forever()

BANNER = """
[yellow]
  ██╗   ██╗███████╗
  ██║   ██║██╔════╝
  ██║   ██║███████╗
  ╚██╗ ██╔╝╚════██║
   ╚████╔╝ ███████║
    ╚═══╝  ╚══════╝
[/yellow]
[bold]  FORGE CONSCIOUS v5 — Self-Discovered Similarity + Emotional Transfer[/bold]
[dim]  FORGE finds its own graph. Not ours.[/dim]
[dim]  Transfers carry emotion. Not just score.[/dim]
"""

def interactive():
    rprint(BANNER)
    stream = ConsciousStreamV5(verbose=True)
    s      = stream.learner.stats()
    rprint(f"  [dim]Observations:    {s['observations']}[/dim]")
    rprint(f"  [dim]Similarity pairs:{s['similarity_pairs']} (discovered)[/dim]")
    rprint(f"  [dim]Clusters:        {s['clusters']}[/dim]")
    rprint(f"  [dim]V4 available:    {V4_AVAILABLE}[/dim]\n")
    rprint("[dim]Commands: inject | multi | graph | clusters | emotional | stats[/dim]")
    rprint("[dim]Or type anything → injected with emotional tagging[/dim]\n")

    while True:
        try:
            raw   = (console.input if RICH else input)(
                "[yellow bold]v5 >[/yellow bold] "
            ).strip()
            if not raw: continue
            parts = raw.split(None,1)
            cmd   = parts[0].lower()
            arg   = parts[1] if len(parts)>1 else ""

            if cmd in ("quit","exit","q"):
                stream.stop(); break

            elif cmd == "inject":
                text = arg or input("  Presence: ").strip()
                if text: stream.inject(text)

            elif cmd == "multi":
                sub   = arg.split(None,1)
                times = int(sub[0]) if sub and sub[0].isdigit() else 20
                text  = sub[1] if len(sub)>1 else input("  Presence: ").strip()
                if text:
                    rprint(f"\n  [bold]Multi-inject: {times} times[/bold]")
                    stream.inject(text, times)

            elif cmd == "graph":
                stream.learner.discoverer.show()

            elif cmd == "clusters":
                clusters = stream.learner.discoverer._clusters
                if not clusters:
                    rprint("  [dim]No clusters discovered yet.[/dim]")
                for c in clusters[:5]:
                    rprint(f"  [cyan]{c['shared_phase']:<12}[/cyan]  "
                          f"→  {', '.join(c['categories'])}  "
                          f"[dim]avg:{c['avg_score']:.0f}[/dim]")

            elif cmd == "emotional":
                pending   = stream.learner.get_emotional_transfers("pending")
                confirmed = stream.learner.get_emotional_transfers("confirmed")
                rprint(f"\n  Pending: {len(pending)}")
                for t in pending[:4]:
                    rprint(f"  [yellow]{t['source_cat']}→{t['target_cat']}[/yellow]  "
                          f"phase:{t['source_phase']}  "
                          f"[dim]{t['emotional_type']}  "
                          f"×{t['strength_mult']:.1f}[/dim]")
                if confirmed:
                    rprint(f"\n  Confirmed: {len(confirmed)}")
                    for t in confirmed[-3:]:
                        rprint(f"  [green]💓✓[/green] "
                              f"{t['source_cat']}→{t['target_cat']}  "
                              f"{t['source_phase']}")

            elif cmd == "stats":
                s = stream.status()
                for k,v in s.items():
                    if not isinstance(v,dict):
                        rprint(f"  {k:<28} {v}")

            elif cmd == "server":
                threading.Thread(target=start_server, daemon=True).start()
                rprint("[green]v5 API on :7370[/green]")

            else:
                stream.inject(raw)

        except (KeyboardInterrupt, EOFError):
            stream.stop(); break

def main():
    if "--graph" in sys.argv:
        rprint(BANNER)
        ConsciousStreamV5(verbose=False).learner.discoverer.show()
    elif "--emotional" in sys.argv:
        rprint(BANNER)
        tl = EmotionalTransferLearner()
        for t in tl.get_emotional_transfers():
            rprint(f"  {t['status']:<10}  {t['source_cat']}→{t['target_cat']}  "
                  f"{t['emotional_type']}")
    elif "--inject" in sys.argv:
        rprint(BANNER)
        idx   = sys.argv.index("--inject")
        text  = sys.argv[idx+1] if idx+1<len(sys.argv) else ""
        times = int(sys.argv[idx+2]) if idx+2<len(sys.argv) and sys.argv[idx+2].isdigit() else 1
        if text:
            ConsciousStreamV5(verbose=True).inject(text, times)
    elif "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7370
        start_server(port)
    else:
        rprint(BANNER)
        interactive()

if __name__ == "__main__":
    main()
