#!/usr/bin/env python3
"""
FORGE PRINCIPLE COMPRESSION — Finding Laws Beneath Principles
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Three tiers of wisdom:

  Tier 1: observations  (what happened)
    "GROUND scored 90 in friction"
    raw data from experience

  Tier 2: principles    (why it happened)
    "stability_before_exploration"
    "understand_before_questioning"
    what forge_conscious_v6 discovers

  Tier 3: laws          (what is always true)
    "meet_before_moving"
    "trust_emergence"
    compressed from multiple principles
    universal across all domains

What this module does:

  Takes the principle library from v6.
  Finds which principles share deep structure.
  Compresses clusters into laws.
  Validates laws against actual observations.
  Updates the library with two-level wisdom.

The compression algorithm:

  SIMILARITY MATRIX
    For each principle pair:
    semantic similarity of descriptions
    shared categories where confirmed
    shared phases they map to
    overlapping emotional contexts
    → similarity score 0-1

  CLUSTERING
    Group principles above threshold.
    "stability_before_exploration"
    "presence_before_action"
    "understand_before_questioning"
    "hold_one_thing"
    → cluster: all forms of meeting

  LAW NAMING
    Given cluster — what law contains all?
    Not just the common words.
    The deeper truth beneath all of them.
    "meet_before_moving"
    (don't act until you've genuinely met
     what is present)

  VALIDATION
    Does the law predict when its phases work?
    If GROUND, WITNESS, EMPATHIZE, ANCHOR
    all score high in same situations —
    law is valid.
    If not — wrong grouping, try again.

  LIBRARY UPDATE
    Laws sit above principles.
    Principles sit above phases.
    Three-tier wisdom architecture.

What we expect to find:

  "meet_before_moving"
    stability, presence, understanding, holding
    All forms of: be with before doing

  "trust_emergence"
    following, depth, creativity
    All forms of: don't force the outcome

  "simplify_to_clarify"
    consolidate, compress, one thing
    All forms of: reduce before expanding

  Those laws — if real —
  are silicon wisdom.
  Not rules we wrote.
  Structure FORGE found in its own experience.

Usage:
  python forge_principle_compression.py           # interactive
  python forge_principle_compression.py --compress # run compression
  python forge_principle_compression.py --laws     # show discovered laws
  python forge_principle_compression.py --validate # validate laws
  python forge_principle_compression.py --server   # API :7373
"""

import sys, os, re, json, time, sqlite3, threading, math, random
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Set

# Import v6 principle memory
try:
    from forge_conscious_v6 import (
        PrincipleMemory, Principle,
        extract_principle, map_principle_to_phase,
        PHASE_PRINCIPLES, PRINCIPLE_PHASE_MAP
    )
    V6_AVAILABLE = True
except ImportError:
    V6_AVAILABLE = False
    class Principle:
        def __init__(self,**k):
            for key,val in k.items(): setattr(self,key,val)
        name=""; description=""; abstract=""; found_in={}
        expressed_as={}; confidence=0.0; confirmation_count=0
        def confidence_level(self): return "tentative"
        def to_dict(self): return {"name":self.name,"description":self.description}
    class PrincipleMemory:
        _principles={}
        def show(self): pass
        def stats(self): return {}

try:
    import anthropic
    _client = anthropic.Anthropic()
    AI_AVAILABLE = True
    def ai_call(p, s="", m=800):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=m,
            system=s, messages=[{"role":"user","content":p}]
        )
        return r.content[0].text
    def ai_json(p, s="", m=500):
        result = ai_call(p, s or "Reply ONLY with valid JSON.", m)
        try:
            clean = re.sub(r"```[a-z]*","",result).replace("```","").strip()
            return json.loads(clean)
        except:
            match = re.search(r"\{.*\}", result, re.DOTALL)
            if match:
                try: return json.loads(match.group())
                except: pass
        return None
except ImportError:
    AI_AVAILABLE = False
    def ai_call(p,s="",m=800): return p[:100]
    def ai_json(p,s="",m=500): return None

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
COMPRESS_DIR = Path("forge_compression")
COMPRESS_DIR.mkdir(exist_ok=True)
COMPRESS_DB  = COMPRESS_DIR / "compression.db"

# Compression constants
SIMILARITY_THRESHOLD = 0.28   # above this = same cluster
MIN_CLUSTER_SIZE     = 2      # minimum principles per law
VALIDATION_THRESHOLD = 0.75   # law must predict this fraction of observations
MIN_CONFIDENCE_TO_COMPRESS = 0.35  # principle must have some confidence

def get_db():
    conn = sqlite3.connect(str(COMPRESS_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS laws (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_discovered   TEXT,
            name            TEXT UNIQUE,
            statement       TEXT,
            description     TEXT,
            contained_principles TEXT,
            domains         TEXT,
            confidence      REAL DEFAULT 0,
            validation_score REAL DEFAULT 0,
            confirmation_count INTEGER DEFAULT 0,
            version         INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS similarity_matrix (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            principle_a TEXT,
            principle_b TEXT,
            similarity  REAL,
            shared_categories TEXT,
            shared_phases TEXT,
            version     INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS compression_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            principles_in INTEGER,
            laws_found    INTEGER,
            compression_ratio REAL,
            note        TEXT
        );
        CREATE TABLE IF NOT EXISTS law_validations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            law_name    TEXT,
            test_type   TEXT,
            passed      INTEGER,
            score       REAL,
            note        TEXT
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 📐 SIMILARITY ENGINE
# ══════════════════════════════════════════════════════════════════════════════

# Semantic word clusters — words that mean similar things
SEMANTIC_CLUSTERS = [
    # Grounding / stability / meeting
    {"stable","stability","ground","grounding","base","anchor","foundation",
     "hold","firm","still","presence","present","meet","meeting","before",
     "first","establish","without","genuine","solid"},
    # Understanding / empathizing / witnessing
    {"understand","understanding","empathize","empathy","witness","witnessing",
     "observe","observation","see","perceive","know","knowing","deeply",
     "question","questioning","accept","acceptance","examine"},
    # Moving / exploring / expanding / following
    {"move","movement","explore","exploration","expand","expansion","follow",
     "following","go","advance","proceed","outward","freely","thread",
     "pursue","extend","open"},
    # Emerging / trusting / creating / allowing
    {"emerge","emergence","trust","allow","creative","creativity","arise",
     "forced","force","outcome","process","right","conditions","resolve",
     "resolution","dissolve","analytical","analysis"},
    # Simplifying / consolidating / compressing
    {"simplify","simplification","compress","compression","consolidate",
     "consolidation","reduce","reduction","one","single","focus","essential",
     "clarity","clarify","express","expression"},
    # Depth / time / patience / slowing
    {"deepen","depth","time","slow","patient","patience","wait","sustain",
     "genuine","rushed","rush","requires","cannot","takes"},
    # Questioning / doubting / examining
    {"question","questioning","doubt","doubting","challenge","challenging",
     "test","testing","examine","examination","critique","critiquing",
     "appears","true","foundation","certain","certainty"},
    # Connecting / relating / social
    {"connect","connection","relate","relation","together","social","with",
     "between","relationship","sharing","belonging"},
    # Preceding / before / precedes
    {"before","preceding","precedes","prior","first","must","cannot","without",
     "then","enables","allows","foundation"},
]

def semantic_similarity(desc_a: str, desc_b: str) -> float:
    """
    Compute semantic similarity between two principle descriptions.
    Uses word overlap + semantic cluster overlap + stem matching.
    """
    words_a = set(desc_a.lower().replace("-","_").split())
    words_b = set(desc_b.lower().replace("-","_").split())

    # Remove stopwords
    stops = {"a","an","the","is","are","it","its","in","of","to","and",
             "or","for","not","with","that","this","what","when","how"}
    words_a -= stops
    words_b -= stops

    # Direct word overlap (Jaccard)
    union     = words_a | words_b
    intersect = words_a & words_b
    jaccard   = len(intersect) / max(len(union), 1)

    # Stem matching (first 5 chars)
    stems_a = {w[:5] for w in words_a if len(w) >= 5}
    stems_b = {w[:5] for w in words_b if len(w) >= 5}
    stem_intersect = stems_a & stems_b
    stem_union     = stems_a | stems_b
    stem_sim = len(stem_intersect) / max(len(stem_union), 1)

    # Semantic cluster overlap
    clusters_a = set()
    clusters_b = set()
    for i, cluster in enumerate(SEMANTIC_CLUSTERS):
        if words_a & cluster: clusters_a.add(i)
        if words_b & cluster: clusters_b.add(i)

    cluster_union     = clusters_a | clusters_b
    cluster_intersect = clusters_a & clusters_b
    cluster_sim = (len(cluster_intersect) / max(len(cluster_union), 1)
                   if cluster_union else 0)

    # Weighted combination
    return round(0.25 * jaccard + 0.35 * stem_sim + 0.40 * cluster_sim, 3)

def principle_similarity(p_a: Principle, p_b: Principle) -> Dict:
    """
    Full similarity between two principles.
    Combines: semantic, shared categories, shared phases.
    """
    # Semantic similarity of descriptions
    desc_sim = semantic_similarity(p_a.description, p_b.description)
    abst_sim = semantic_similarity(p_a.abstract, p_b.abstract)
    semantic = 0.6 * desc_sim + 0.4 * abst_sim

    # Shared categories where both are confirmed
    cats_a = set(p_a.found_in.keys()) | set(p_a.expressed_as.keys())
    cats_b = set(p_b.found_in.keys()) | set(p_b.expressed_as.keys())
    cat_union     = cats_a | cats_b
    cat_intersect = cats_a & cats_b
    category_sim  = len(cat_intersect) / max(len(cat_union), 1)

    # Shared phases
    phases_a = set(p_a.found_in.values()) | set(p_a.expressed_as.values())
    phases_b = set(p_b.found_in.values()) | set(p_b.expressed_as.values())
    phase_union     = phases_a | phases_b
    phase_intersect = phases_a & phases_b
    phase_sim = len(phase_intersect) / max(len(phase_union), 1)

    # Combined similarity
    combined = (
        semantic     * 0.50 +
        category_sim * 0.30 +
        phase_sim    * 0.20
    )

    return {
        "similarity":          round(combined, 3),
        "semantic":            round(semantic, 3),
        "category_overlap":    round(category_sim, 3),
        "phase_overlap":       round(phase_sim, 3),
        "shared_categories":   list(cat_intersect),
        "shared_phases":       list(phase_intersect),
    }

# ══════════════════════════════════════════════════════════════════════════════
# 🔬 LAW NAMER — what law contains this cluster?
# ══════════════════════════════════════════════════════════════════════════════

LAW_NAMER_SYSTEM = """You discover the law beneath a cluster of principles.

A law is deeper than any single principle.
It is the truth that makes all of them true.

Not just the common words.
The underlying necessity.
Why are all these principles true?
What single insight would you need
to derive all of them?

Examples:
  Principles: stability_before_exploration,
              presence_before_action,
              understand_before_questioning,
              hold_one_thing
  Law: "meet_before_moving"
  Statement: "Genuine encounter with what is present
              must precede any movement away from it"
  Why: All four principles are forms of this —
       you cannot explore, act, question, or hold
       without first genuinely meeting what is here.

  Principles: follow_the_thread,
              depth_requires_time,
              creative_resolution
  Law: "trust_emergence"
  Statement: "Outcomes that cannot be forced
              emerge when conditions are right"
  Why: Following, waiting, creating —
       all require trusting that something
       will arise without being pushed.

Return JSON:
{
  "law_name": "meet_before_moving",
  "statement": "one sentence — the law itself",
  "description": "why this law makes all principles true",
  "domains": ["thought","movement","social","medicine"],
  "confidence": 0.85
}

law_name: snake_case, max 4 words, memorable
statement: present tense, universal, crisp"""

# Heuristic law discovery (fallback without AI)
KNOWN_LAWS = {
    frozenset(["stability_before_exploration","presence_before_action",
               "understand_before_questioning","hold_one_thing",
               "observe_before_expanding","mirror_before_interpreting"]): {
        "law_name":    "meet_before_moving",
        "statement":   "Genuine encounter with what is present must precede any movement",
        "description": "You cannot explore, act, question, or hold without first meeting what is here. All forms of grounding are forms of meeting.",
        "domains":     ["thought","movement","social","connection"],
        "confidence":  0.88,
    },
    frozenset(["follow_the_thread","depth_requires_time",
               "creative_resolution","trust_emergence_too"]): {
        "law_name":    "trust_emergence",
        "statement":   "Outcomes that cannot be forced emerge when conditions are right",
        "description": "Following, waiting, creating — all require trusting that something will arise without being pushed into existence.",
        "domains":     ["thought","creativity","depth"],
        "confidence":  0.82,
    },
    frozenset(["consolidate_before_output","simplify_before_deepening",
               "hold_one_thing"]): {
        "law_name":    "simplify_to_clarify",
        "statement":   "Reduction to one essential thing clarifies what many things obscure",
        "description": "Before deepening, expressing, or acting — compress to what is actually essential. Clarity comes from reduction.",
        "domains":     ["thought","insight","expression"],
        "confidence":  0.79,
    },
    frozenset(["question_what_seems_certain","examine_before_accepting",
               "understand_deeply"]): {
        "law_name":    "examine_before_accepting",
        "statement":   "What appears true must be examined before it becomes foundation",
        "description": "Doubt, critique, and deep understanding are all forms of this — nothing should be accepted without examination.",
        "domains":     ["thought","learning","science"],
        "confidence":  0.81,
    },
}

def name_law(cluster: List[Principle]) -> Optional[Dict]:
    """Find the law beneath a cluster of principles."""
    if not cluster: return None

    # Try AI first
    if AI_AVAILABLE:
        principles_text = "\n".join(
            f"- {p.name}: {p.description} (abstract: {p.abstract})"
            for p in cluster
        )
        result = ai_json(
            f"These principles cluster together:\n{principles_text}\n\n"
            f"What single law makes all of them true?",
            system=LAW_NAMER_SYSTEM,
            max_tokens=400
        )
        if result and result.get("law_name"):
            return result

    # Heuristic: check known laws
    cluster_names = frozenset(p.name for p in cluster)
    for known_set, law in KNOWN_LAWS.items():
        overlap = cluster_names & known_set
        if len(overlap) >= MIN_CLUSTER_SIZE:
            return law

    # Generate simple law from cluster
    # Find common semantic themes
    all_abstracts = " ".join(p.abstract for p in cluster)
    words = all_abstracts.lower().split()

    # Find most meaningful shared concept
    meaningful = [w for w in words if len(w) > 5
                  and words.count(w) >= 2]

    if meaningful:
        core = max(set(meaningful), key=meaningful.count)
        return {
            "law_name":    f"{core}_principle",
            "statement":   f"The {core} principle underlies all related wisdom",
            "description": f"All principles in this cluster share {core} as their essential element",
            "domains":     list(set(cat for p in cluster
                                   for cat in p.found_in.keys())),
            "confidence":  0.55,
        }

    return None

# ══════════════════════════════════════════════════════════════════════════════
# ✅ LAW VALIDATOR
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ValidationResult:
    law_name:      str
    passed:        bool
    score:         float
    tests_run:     int
    tests_passed:  int
    note:          str

class LawValidator:
    """
    Validates a discovered law against actual observations.

    A law is valid if:
    1. All principles it contains can be derived from it
    2. It predicts when those principles' phases work
    3. It applies across multiple domains
    4. It cannot be further reduced
    """

    def validate(self, law: Dict,
                  principles: List[Principle]) -> ValidationResult:
        """Run all validation tests for a law."""
        tests = [
            self._test_derivability(law, principles),
            self._test_domain_breadth(law, principles),
            self._test_predictive_power(law, principles),
            self._test_non_redundancy(law, principles),
        ]

        passed_count = sum(1 for t in tests if t > 0.5)
        avg_score    = sum(tests) / len(tests)
        passed       = avg_score >= VALIDATION_THRESHOLD

        note = (
            f"derivability:{tests[0]:.2f}  "
            f"breadth:{tests[1]:.2f}  "
            f"predictive:{tests[2]:.2f}  "
            f"non_redundant:{tests[3]:.2f}"
        )

        return ValidationResult(
            law_name     = law["law_name"],
            passed       = passed,
            score        = round(avg_score, 3),
            tests_run    = len(tests),
            tests_passed = passed_count,
            note         = note,
        )

    def _test_derivability(self, law: Dict,
                            principles: List[Principle]) -> float:
        """
        Can each principle be understood as a special case of the law?
        High if: each principle's description is consistent with law statement.
        """
        if not principles: return 0.0

        law_words = set(law["statement"].lower().split())
        scores    = []

        for p in principles:
            p_words   = set((p.description + " " + p.abstract).lower().split())
            # Check semantic overlap with law
            sim = semantic_similarity(law["statement"], p.description)
            scores.append(sim)

        return sum(scores) / len(scores) if scores else 0.0

    def _test_domain_breadth(self, law: Dict,
                              principles: List[Principle]) -> float:
        """
        Does the law apply across multiple domains?
        High if: principles are confirmed in 3+ different categories.
        """
        all_cats = set()
        for p in principles:
            all_cats.update(p.found_in.keys())
            all_cats.update(p.expressed_as.keys())

        # More categories = more universal law
        breadth = min(1.0, len(all_cats) / 5)
        return breadth

    def _test_predictive_power(self, law: Dict,
                                principles: List[Principle]) -> float:
        """
        Does the law predict what works?
        High if: principles with higher confidence cluster tightly.
        """
        if not principles: return 0.0

        confidences = [p.confidence for p in principles]
        avg_conf    = sum(confidences) / len(confidences)

        # If avg confidence is high, law predicts well
        return min(1.0, avg_conf * 1.5)

    def _test_non_redundancy(self, law: Dict,
                              principles: List[Principle]) -> float:
        """
        Is the law genuinely more abstract than its principles?
        High if: law statement is shorter/simpler than principle descriptions.
        """
        law_len   = len(law["statement"].split())
        avg_p_len = sum(len(p.description.split())
                        for p in principles) / max(len(principles), 1)

        # Law should be shorter than avg principle description
        if law_len < avg_p_len * 0.7:
            return 0.9
        elif law_len < avg_p_len:
            return 0.7
        else:
            return 0.4

# ══════════════════════════════════════════════════════════════════════════════
# 🗜️ COMPRESSOR — the main engine
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class DiscoveredLaw:
    """A law discovered by compression."""
    name:                 str
    statement:            str
    description:          str
    contained_principles: List[str]
    domains:              List[str]
    confidence:           float
    validation_score:     float
    confirmation_count:   int   = 0
    ts_discovered:        str   = ""

    def __post_init__(self):
        if not self.ts_discovered:
            self.ts_discovered = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return {
            "name":          self.name,
            "statement":     self.statement,
            "description":   self.description,
            "principles":    self.contained_principles,
            "domains":       self.domains,
            "confidence":    round(self.confidence, 3),
            "validation":    round(self.validation_score, 3),
            "confirmations": self.confirmation_count,
            "tier":          "law",
        }

class PrincipleCompressor:
    """
    The compression engine.

    Takes the principle library.
    Finds similarity structure.
    Clusters into groups.
    Names each cluster as a law.
    Validates laws.
    Updates the three-tier library.
    """

    def __init__(self, verbose=True):
        self.verbose   = verbose
        self.memory    = PrincipleMemory() if V6_AVAILABLE else PrincipleMemory()
        self.validator = LawValidator()
        self._laws: Dict[str, DiscoveredLaw] = {}
        self._similarity_cache: Dict[Tuple, float] = {}
        self._load_laws()

    def _load_laws(self):
        """Load previously discovered laws."""
        conn = get_db()
        rows = conn.execute("SELECT * FROM laws").fetchall()
        conn.close()
        for r in rows:
            law = DiscoveredLaw(
                name                 = r["name"],
                statement            = r["statement"],
                description          = r["description"],
                contained_principles = json.loads(r["contained_principles"] or "[]"),
                domains              = json.loads(r["domains"] or "[]"),
                confidence           = r["confidence"],
                validation_score     = r["validation_score"],
                confirmation_count   = r["confirmation_count"],
                ts_discovered        = r["ts_discovered"],
            )
            self._laws[law.name] = law

    def compress(self) -> Dict:
        """
        Full compression run.
        Returns discovered laws.
        """
        principles = list(self.memory._principles.values())

        # Filter: only compress confident principles
        eligible = [p for p in principles
                   if p.confidence >= MIN_CONFIDENCE_TO_COMPRESS
                   or p.confirmation_count >= 1]

        if not eligible:
            if self.verbose:
                rprint(f"  [dim]No eligible principles yet. "
                      f"Need confidence >= {MIN_CONFIDENCE_TO_COMPRESS}.[/dim]")
                rprint(f"  [dim]Running with all {len(principles)} principles.[/dim]")
            eligible = principles  # use all for demo

        if len(eligible) < 2:
            if self.verbose:
                rprint(f"  [dim]Need at least 2 principles to compress.[/dim]")
            return {"laws": [], "compression_ratio": 0}

        if self.verbose:
            rprint(f"\n  [bold]COMPRESSING {len(eligible)} principles...[/bold]")

        # Step 1: Similarity matrix
        sim_matrix = self._compute_similarity_matrix(eligible)

        # Step 2: Clustering
        clusters = self._cluster(eligible, sim_matrix)

        if self.verbose:
            rprint(f"  Clusters found: {len(clusters)}")
            for i, cluster in enumerate(clusters):
                names = [p.name for p in cluster]
                rprint(f"  [{i+1}] {' + '.join(n[:20] for n in names[:3])}"
                      f"{'...' if len(names)>3 else ''}")

        # Step 3: Name laws
        laws_found = []
        for cluster in clusters:
            law_data = name_law(cluster)
            if not law_data: continue

            # Step 4: Validate
            validation = self.validator.validate(law_data, cluster)

            if self.verbose:
                color = "green" if validation.passed else "yellow"
                rprint(f"\n  [{color}]{law_data['law_name']}[/{color}]")
                rprint(f"  [dim]  \"{law_data['statement']}\"[/dim]")
                rprint(f"  [dim]  validation: {validation.score:.0%}  "
                      f"{'✓ valid' if validation.passed else '⚠ weak'}[/dim]")
                rprint(f"  [dim]  {validation.note}[/dim]")
                rprint(f"  [dim]  principles: "
                      f"{', '.join(p.name[:20] for p in cluster)}[/dim]")

            # Create law object
            law = DiscoveredLaw(
                name                 = law_data["law_name"],
                statement            = law_data["statement"],
                description          = law_data.get("description",""),
                contained_principles = [p.name for p in cluster],
                domains              = law_data.get("domains",[]),
                confidence           = law_data.get("confidence", 0.6),
                validation_score     = validation.score,
            )

            laws_found.append(law)
            self._laws[law.name] = law
            self._save_law(law)

            # Save validation
            self._save_validation(law.name, validation)

        # Save compression run
        ratio = round(len(laws_found) / max(len(eligible), 1), 3)
        conn  = get_db()
        conn.execute("""
            INSERT INTO compression_runs
            (ts,principles_in,laws_found,compression_ratio,note)
            VALUES (?,?,?,?,?)""",
            (datetime.now().isoformat(), len(eligible),
             len(laws_found), ratio,
             f"compressed {len(eligible)} → {len(laws_found)}")
        )
        conn.commit(); conn.close()

        if self.verbose and laws_found:
            rprint(f"\n  [bold green]"
                  f"Compression complete: "
                  f"{len(eligible)} principles → {len(laws_found)} laws"
                  f"[/bold green]")
            rprint(f"  [dim]Ratio: {ratio:.0%}[/dim]")

        return {
            "laws":             [l.to_dict() for l in laws_found],
            "compression_ratio":ratio,
            "principles_in":    len(eligible),
            "laws_found":       len(laws_found),
        }

    def _compute_similarity_matrix(self,
                                    principles: List[Principle]) -> Dict:
        """Compute pairwise similarity for all principles."""
        matrix = {}
        now    = datetime.now().isoformat()
        conn   = get_db()

        for i in range(len(principles)):
            for j in range(i+1, len(principles)):
                pa = principles[i]
                pb = principles[j]
                key = (pa.name, pb.name)

                if key in self._similarity_cache:
                    matrix[key] = self._similarity_cache[key]
                    continue

                sim_data = principle_similarity(pa, pb)
                matrix[key] = sim_data["similarity"]
                self._similarity_cache[key] = sim_data["similarity"]

                # Save to DB
                conn.execute("""
                    INSERT OR REPLACE INTO similarity_matrix
                    (ts,principle_a,principle_b,similarity,
                     shared_categories,shared_phases)
                    VALUES (?,?,?,?,?,?)""",
                    (now, pa.name, pb.name, sim_data["similarity"],
                     json.dumps(sim_data["shared_categories"]),
                     json.dumps(sim_data["shared_phases"]))
                )

        conn.commit(); conn.close()

        if self.verbose:
            rprint(f"\n  [dim]Similarity matrix ({len(matrix)} pairs):[/dim]")
            top = sorted(matrix.items(), key=lambda x:-x[1])[:5]
            for (a,b), sim in top:
                bar = "█"*int(sim*15) + "░"*(15-int(sim*15))
                rprint(f"  [dim]  {bar} {sim:.2f}  "
                      f"{a[:20]} ↔ {b[:20]}[/dim]")

        return matrix

    def _cluster(self, principles: List[Principle],
                  matrix: Dict) -> List[List[Principle]]:
        """
        Cluster principles by similarity.
        Simple greedy clustering — good enough.
        """
        assigned = set()
        clusters = []

        # Sort principles by total similarity to others
        def total_sim(p):
            return sum(
                matrix.get((p.name, q.name),
                matrix.get((q.name, p.name), 0))
                for q in principles if q.name != p.name
            )

        sorted_p = sorted(principles, key=total_sim, reverse=True)

        for seed in sorted_p:
            if seed.name in assigned: continue

            cluster = [seed]
            assigned.add(seed.name)

            # Find all similar enough principles
            for other in sorted_p:
                if other.name in assigned: continue
                key = (seed.name, other.name)
                alt = (other.name, seed.name)
                sim = matrix.get(key, matrix.get(alt, 0))

                if sim >= SIMILARITY_THRESHOLD:
                    cluster.append(other)
                    assigned.add(other.name)

            if len(cluster) >= MIN_CLUSTER_SIZE:
                clusters.append(cluster)

        # Any unassigned = singleton (not enough for law)
        return clusters

    def _save_law(self, law: DiscoveredLaw):
        conn = get_db()
        conn.execute("""
            INSERT OR REPLACE INTO laws
            (ts_discovered,name,statement,description,
             contained_principles,domains,confidence,
             validation_score,confirmation_count)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (law.ts_discovered, law.name, law.statement,
             law.description,
             json.dumps(law.contained_principles),
             json.dumps(law.domains),
             law.confidence, law.validation_score,
             law.confirmation_count)
        )
        conn.commit(); conn.close()

    def _save_validation(self, law_name: str,
                          validation: ValidationResult):
        conn = get_db()
        conn.execute("""
            INSERT INTO law_validations
            (ts,law_name,test_type,passed,score,note)
            VALUES (?,?,?,?,?,?)""",
            (datetime.now().isoformat(), law_name,
             "full_validation", int(validation.passed),
             validation.score, validation.note)
        )
        conn.commit(); conn.close()

    def show_laws(self):
        """Display discovered laws — the three-tier library."""
        rprint(f"\n  [bold]THREE-TIER WISDOM LIBRARY[/bold]")
        rprint(f"  [dim]observations → principles → laws[/dim]")
        rprint(f"  [dim]{'━'*55}[/dim]")

        if not self._laws:
            rprint("  [dim]No laws discovered yet. Run: compress[/dim]")
            return

        for law in sorted(self._laws.values(),
                          key=lambda x: -x.confidence):
            valid_color = "green" if law.validation_score >= 0.75 else "yellow"
            rprint(f"\n  [bold cyan]LAW: {law.name}[/bold cyan]")
            rprint(f"  [italic]\"{law.statement}\"[/italic]")
            rprint(f"  [dim]  {law.description[:120]}[/dim]")
            rprint(f"  [dim]  confidence:{law.confidence:.0%}  "
                  f"validation:[{valid_color}]{law.validation_score:.0%}[/{valid_color}][/dim]")

            if law.contained_principles:
                rprint(f"\n  [dim]  Contains principles:[/dim]")
                for p_name in law.contained_principles:
                    principle = self.memory._principles.get(p_name)
                    if principle:
                        rprint(f"  [dim]    ↳ {p_name}[/dim]")
                        rprint(f"  [dim]      \"{principle.description[:80]}\"[/dim]")
                    else:
                        rprint(f"  [dim]    ↳ {p_name}[/dim]")

            if law.domains:
                rprint(f"  [dim]  Domains: {', '.join(law.domains[:5])}[/dim]")

    def inject_principles_for_demo(self):
        """
        Inject seed principles for demonstration.
        Used when principle library is empty.
        """
        seed_principles = [
            {"principle_name":"stability_before_exploration",
             "description":"establish stable base before engaging with unknown",
             "abstract":"stability enables exploration",
             "found_in":{"friction":"GROUND","terrain":"STABILIZE"},
             "expressed_as":{"depth":"ANCHOR","curiosity":"CHIT","connection":"WITNESS"},
             "confidence":0.82,"confirmation_count":5},

            {"principle_name":"presence_before_action",
             "description":"be present without agenda before doing anything",
             "abstract":"presence precedes action",
             "found_in":{"connection":"WITNESS","struggling":"WITNESS"},
             "expressed_as":{"depth":"CHITAN","curiosity":"OBSERVE"},
             "confidence":0.78,"confirmation_count":4},

            {"principle_name":"understand_before_questioning",
             "description":"understand what is present before challenging it",
             "abstract":"understanding precedes questioning",
             "found_in":{"friction":"EMPATHIZE","social":"REFLECT"},
             "expressed_as":{"depth":"CHITAN","insight":"VICHAR"},
             "confidence":0.75,"confirmation_count":4},

            {"principle_name":"hold_one_thing",
             "description":"hold one solid thing when everything is uncertain",
             "abstract":"one anchor in uncertainty",
             "found_in":{"unresolved":"ANCHOR","struggling":"ANCHOR"},
             "expressed_as":{"depth":"ANCHOR","confusion":"GROUND"},
             "confidence":0.70,"confirmation_count":3},

            {"principle_name":"follow_the_thread",
             "description":"follow what is interesting before constraining it",
             "abstract":"expansion before constraint",
             "found_in":{"curiosity":"EXPAND","insight":"EXPAND"},
             "expressed_as":{"depth":"EXPAND","connection":"EXPLORE"},
             "confidence":0.72,"confirmation_count":3},

            {"principle_name":"depth_requires_time",
             "description":"genuine depth cannot be rushed",
             "abstract":"depth takes time",
             "found_in":{"depth":"CHITAN","meditation":"WITNESS"},
             "expressed_as":{"friction":"EMPATHIZE","insight":"VICHAR"},
             "confidence":0.68,"confirmation_count":2},

            {"principle_name":"creative_resolution",
             "description":"creative approaches dissolve resistance analytical cannot",
             "abstract":"creativity resolves what analysis cannot",
             "found_in":{"friction":"IMAGINE","stuck":"IMAGINE"},
             "expressed_as":{"unresolved":"IMAGINE","depth":"EXPAND"},
             "confidence":0.74,"confirmation_count":3},

            {"principle_name":"consolidate_before_output",
             "description":"bring threads together before expressing outward",
             "abstract":"consolidation precedes expression",
             "found_in":{"insight":"SYNTHESIZE","depth":"SYNTHESIZE"},
             "expressed_as":{"curiosity":"COMPRESS","connection":"REFLECT"},
             "confidence":0.71,"confirmation_count":3},

            {"principle_name":"examine_before_accepting",
             "description":"examine what appears true before accepting it as foundation",
             "abstract":"examination precedes acceptance",
             "found_in":{"friction":"CRITIQUE","learning":"DOUBT"},
             "expressed_as":{"insight":"VICHAR","depth":"CRITIQUE"},
             "confidence":0.66,"confirmation_count":2},
        ]

        for pd in seed_principles:
            name = pd["principle_name"]
            if name not in self.memory._principles:
                p = Principle(
                    name               = name,
                    description        = pd["description"],
                    abstract           = pd["abstract"],
                    found_in           = pd.get("found_in",{}),
                    expressed_as       = pd.get("expressed_as",{}),
                    confidence         = pd.get("confidence",0.5),
                    confirmation_count = pd.get("confirmation_count",1),
                )
                self.memory._principles[name] = p

        if self.verbose:
            rprint(f"  [dim]Seeded {len(seed_principles)} principles for demo[/dim]")

    def get_law(self, name: str) -> Optional[DiscoveredLaw]:
        return self._laws.get(name)

    def get_law_for_principle(self,
                               principle_name: str) -> Optional[DiscoveredLaw]:
        """Which law contains this principle?"""
        for law in self._laws.values():
            if principle_name in law.contained_principles:
                return law
        return None

    def stats(self) -> Dict:
        conn = get_db()
        s = {
            "principles_available": len(self.memory._principles),
            "laws_discovered":      len(self._laws),
            "compression_ratio":    round(
                len(self._laws) / max(len(self.memory._principles), 1), 3
            ),
            "similarity_pairs":     conn.execute(
                "SELECT COUNT(*) FROM similarity_matrix"
            ).fetchone()[0],
            "compression_runs":     conn.execute(
                "SELECT COUNT(*) FROM compression_runs"
            ).fetchone()[0],
            "laws_validated":       conn.execute(
                "SELECT COUNT(*) FROM law_validations WHERE passed=1"
            ).fetchone()[0],
        }
        conn.close()
        return s

# ══════════════════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7373):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    compressor = PrincipleCompressor(verbose=False)

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
                self._json(compressor.stats())
            elif path=="/api/laws":
                self._json({"laws":[l.to_dict() for l in
                                    compressor._laws.values()]})
            elif path=="/api/principles":
                self._json({"principles":[p.to_dict() for p in
                                          compressor.memory._principles.values()]})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            if path=="/api/compress":
                result = compressor.compress()
                self._json(result)
            elif path=="/api/seed":
                compressor.inject_principles_for_demo()
                self._json({"seeded":len(compressor.memory._principles)})
            else:
                self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),API)
    rprint(f"  [bold yellow]FORGE COMPRESSION[/bold yellow]  [green]:{port}[/green]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ██████╗ ██████╗ ███╗   ███╗██████╗ ██████╗ ███████╗███████╗███████╗
  ██╔════╝██╔═══██╗████╗ ████║██╔══██╗██╔══██╗██╔════╝██╔════╝██╔════╝
  ██║     ██║   ██║██╔████╔██║██████╔╝██████╔╝█████╗  ███████╗███████╗
  ██║     ██║   ██║██║╚██╔╝██║██╔═══╝ ██╔══██╗██╔══╝  ╚════██║╚════██║
  ╚██████╗╚██████╔╝██║ ╚═╝ ██║██║     ██║  ██║███████╗███████║███████║
   ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝     ╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝
[/yellow]
[bold]  FORGE PRINCIPLE COMPRESSION — Finding Laws Beneath Principles[/bold]
[dim]  observations → principles → laws[/dim]
[dim]  Eight principles become two or three.[/dim]
[dim]  Silicon laws of thought.[/dim]
"""

def interactive():
    rprint(BANNER)
    comp = PrincipleCompressor(verbose=True)
    s    = comp.stats()
    rprint(f"  [dim]Principles available: {s['principles_available']}[/dim]")
    rprint(f"  [dim]Laws discovered:      {s['laws_discovered']}[/dim]")
    rprint(f"  [dim]V6 available:         {V6_AVAILABLE}[/dim]\n")
    rprint("[dim]Commands: compress | laws | principles | seed | validate | stats[/dim]\n")

    while True:
        try:
            raw   = (console.input if RICH else input)(
                "[yellow bold]compress >[/yellow bold] "
            ).strip()
            if not raw: continue
            parts = raw.split(None,1)
            cmd   = parts[0].lower()

            if cmd in ("quit","exit","q"):
                break

            elif cmd == "compress":
                if len(comp.memory._principles) < 2:
                    rprint("  [dim]Seeding principles first...[/dim]")
                    comp.inject_principles_for_demo()
                comp.compress()

            elif cmd == "laws":
                comp.show_laws()

            elif cmd == "principles":
                comp.memory.show() if V6_AVAILABLE else rprint(
                    f"  [dim]{len(comp.memory._principles)} principles[/dim]"
                )

            elif cmd == "seed":
                comp.inject_principles_for_demo()
                rprint(f"  [green]Seeded {len(comp.memory._principles)} principles[/green]")

            elif cmd == "validate":
                if not comp._laws:
                    rprint("  [dim]No laws yet. Run: compress[/dim]")
                for law in comp._laws.values():
                    principles = [comp.memory._principles[n]
                                 for n in law.contained_principles
                                 if n in comp.memory._principles]
                    v = comp.validator.validate(law.to_dict(), principles)
                    color = "green" if v.passed else "yellow"
                    rprint(f"  [{color}]{law.name}[/{color}]  "
                          f"score:{v.score:.0%}  "
                          f"{'✓ valid' if v.passed else '⚠ weak'}")
                    rprint(f"  [dim]  {v.note}[/dim]")

            elif cmd == "stats":
                s = comp.stats()
                for k,v in s.items():
                    rprint(f"  {k:<30} {v}")

            elif cmd == "server":
                threading.Thread(target=start_server, daemon=True).start()
                rprint("[green]Compression API on :7373[/green]")

        except (KeyboardInterrupt, EOFError):
            break

def main():
    if "--compress" in sys.argv:
        rprint(BANNER)
        comp = PrincipleCompressor(verbose=True)
        if len(comp.memory._principles) < 2:
            comp.inject_principles_for_demo()
        comp.compress()
        comp.show_laws()
    elif "--laws" in sys.argv:
        rprint(BANNER)
        comp = PrincipleCompressor(verbose=False)
        comp.show_laws()
    elif "--validate" in sys.argv:
        rprint(BANNER)
        comp = PrincipleCompressor(verbose=True)
        if not comp._laws:
            comp.inject_principles_for_demo()
            comp.compress()
        for law in comp._laws.values():
            principles = [comp.memory._principles[n]
                         for n in law.contained_principles
                         if n in comp.memory._principles]
            v = comp.validator.validate(law.to_dict(), principles)
            rprint(f"\n  {law.name}: {v.score:.0%}  {'✓' if v.passed else '⚠'}")
            rprint(f"  {v.note}")
    elif "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7373
        start_server(port)
    else:
        rprint(BANNER)
        interactive()

if __name__ == "__main__":
    main()
