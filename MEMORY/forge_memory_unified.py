"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     FORGE_MEMORY_UNIFIED v1.0                                ║
║                  The Two Halves Speaking to Each Other                       ║
║                                                                              ║
║  Four directional whispers:                                                  ║
║    v1 TRACE      ──→  v2 EmotionalIndex   (every trace gets felt)           ║
║    v2 FeltSig    ──→  v1 SELF beliefs     (what matters crystallizes)        ║
║    v2 BodyMemory ──→  v1 BOND             (instincts remembered)             ║
║    v1 GENESIS    ──→  v2 pathway weight   (thinking gets stronger pathways)  ║
║                                                                              ║
║  No loops. One direction each. The two systems don't know about each other.  ║
║  The bridge handles everything invisibly. Like a whisper.                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import json
import threading
import time
import queue
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

# ─── Optional Dependencies ────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

console = Console() if RICH_AVAILABLE else None

def cprint(msg, style=""):
    if console:
        console.print(msg, style=style)
    else:
        print(msg)

# ─── API endpoints ────────────────────────────────────────────────────────────
V1_API = "http://localhost:7779"   # forge_memory v1
V2_API = "http://localhost:7780"   # forge_memory v2

# ─── Emotion inference from trace content ────────────────────────────────────
EMOTION_KEYWORDS = {
    "awe":         ["emergent", "discovered", "crystallized", "profound", "remarkable", "wonder"],
    "alert":       ["threat", "attack", "injection", "anomaly", "breach", "danger", "intrusion"],
    "excited":     ["breakthrough", "success", "achieved", "complete", "works", "built"],
    "curious":     ["how", "why", "what if", "explore", "investigate", "wonder", "question"],
    "clarity":     ["understand", "realized", "insight", "pattern", "connection", "clear"],
    "focused":     ["analyzing", "processing", "scanning", "monitoring", "tracking"],
    "concern":     ["warning", "unusual", "unexpected", "drift", "failure", "error"],
    "frustration": ["failed", "blocked", "timeout", "retry", "unable", "cannot"],
    "joy":         ["perfect", "excellent", "amazing", "beautiful", "elegant", "love"],
    "calm":        ["stable", "normal", "routine", "standard", "regular", "nominal"],
}

def infer_emotion(content: str, existing_emotion: Optional[str] = None) -> tuple[str, float]:
    """
    Infer emotion from trace content.
    Returns (emotion, intensity).
    """
    if existing_emotion and existing_emotion != "neutral":
        return existing_emotion, 0.6

    content_lower = content.lower()
    scores = {}

    for emotion, keywords in EMOTION_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in content_lower)
        if score > 0:
            scores[emotion] = score

    if not scores:
        return "neutral", 0.3

    best = max(scores.items(), key=lambda x: x[1])
    intensity = min(0.9, 0.4 + best[1] * 0.15)
    return best[0], intensity


# ═══════════════════════════════════════════════════════════════════════════════
#  API CLIENTS — Thin wrappers for v1 and v2
# ═══════════════════════════════════════════════════════════════════════════════

class V1Client:
    """Thin client for forge_memory v1 API."""

    def __init__(self, base: str = V1_API, timeout: float = 2.0):
        self.base = base
        self.timeout = timeout

    def _post(self, endpoint: str, data: dict) -> Optional[dict]:
        try:
            req = urllib.request.Request(
                f"{self.base}{endpoint}",
                data=json.dumps(data).encode(),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except Exception:
            return None

    def _get(self, endpoint: str) -> Optional[dict]:
        try:
            with urllib.request.urlopen(f"{self.base}{endpoint}", timeout=self.timeout) as r:
                return json.loads(r.read())
        except Exception:
            return None

    def is_alive(self) -> bool:
        return self._get("/health") is not None

    def add_belief(self, belief: str, confidence: float = 0.7) -> Optional[str]:
        result = self._post("/self/belief", {"belief": belief, "confidence": confidence, "source": "v2_felt_significance"})
        return result.get("belief_id") if result else None

    def remember_moment(self, human_id: str, moment: str, emotion: str, significance: float = 0.7):
        self._post("/bond/moment", {
            "human_id": human_id, "moment": moment,
            "emotion": emotion, "significance": significance
        })

    def add_shared_term(self, human_id: str, term: str, meaning: str):
        self._post("/bond/term", {"human_id": human_id, "term": term, "meaning": meaning, "origin": "v2_body_memory"})

    def capture_genesis(self, thought_type: str, content: str, artifact_name: str,
                        human_id: str = "default", significance: float = 0.5):
        self._post("/genesis/capture", {
            "thought_type": thought_type, "content": content,
            "artifact_name": artifact_name, "human_id": human_id,
            "significance": significance,
        })

    def get_recent_traces(self, human_id: str = "default", limit: int = 20) -> list:
        result = self._get(f"/trace/recall?human_id={human_id}&limit={limit}")
        return result if isinstance(result, list) else []

    def get_recent_genesis(self, human_id: str = "default", limit: int = 10) -> list:
        result = self._get(f"/genesis/recall?human_id={human_id}&limit={limit}")
        return result if isinstance(result, list) else []


class V2Client:
    """Thin client for forge_memory v2 API."""

    def __init__(self, base: str = V2_API, timeout: float = 2.0):
        self.base = base
        self.timeout = timeout

    def _post(self, endpoint: str, data: dict) -> Optional[dict]:
        try:
            req = urllib.request.Request(
                f"{self.base}{endpoint}",
                data=json.dumps(data).encode(),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except Exception:
            return None

    def _get(self, endpoint: str) -> Optional[dict]:
        try:
            with urllib.request.urlopen(f"{self.base}{endpoint}", timeout=self.timeout) as r:
                return json.loads(r.read())
        except Exception:
            return None

    def is_alive(self) -> bool:
        return self._get("/health") is not None

    def feel(self, content: str, emotion: str, intensity: float = 0.5,
             category: str = "general", human_id: str = "default", module: str = "unified") -> Optional[str]:
        result = self._post("/feel", {
            "content": content, "emotion": emotion, "intensity": intensity,
            "category": category, "human_id": human_id, "module": module,
        })
        return result.get("node_id") if result else None

    def get_significant(self, human_id: str = "default", top_k: int = 5) -> list:
        result = self._get(f"/significance/{human_id}?top_k={top_k}")
        return result if isinstance(result, list) else []

    def get_instincts(self) -> list:
        result = self._get("/status")
        if result:
            return result.get("body", {}).get("instinct_names", [])
        return []

    def get_body_snapshot(self) -> dict:
        result = self._get("/status")
        return result.get("body", {}) if result else {}

    def get_dominant_emotion(self) -> str:
        result = self._get("/status")
        return result.get("dominant_emotion", "neutral") if result else "neutral"


# ═══════════════════════════════════════════════════════════════════════════════
#  THE FOUR WHISPERS
#  Each bridge — one directional flow
# ═══════════════════════════════════════════════════════════════════════════════

class WhisperBridge:
    """
    One directional whisper between v1 and v2.
    Runs in background. Silent. Invisible to both systems.
    """

    def __init__(self, name: str, v1: V1Client, v2: V2Client):
        self.name = name
        self.v1 = v1
        self.v2 = v2
        self._processed = 0

    def whisper(self, payload: dict) -> bool:
        raise NotImplementedError

    def log(self, msg: str):
        cprint(f"  [dim]🤫 [{self.name}] {msg}[/dim]")


class TraceToEmotion(WhisperBridge):
    """
    WHISPER 1: v1 TRACE ──→ v2 EmotionalIndex
    Every trace that gets captured in v1 gets felt in v2.
    The factual record becomes an emotional experience.
    """

    def whisper(self, payload: dict) -> bool:
        content = payload.get("content", "")
        existing_emotion = payload.get("emotion")
        human_id = payload.get("human_id", "default")
        module = payload.get("module", "core")
        intensity = payload.get("intensity", 0.5)

        # Infer emotion from content
        emotion, inferred_intensity = infer_emotion(content, existing_emotion)
        final_intensity = max(intensity, inferred_intensity)

        # Map trace stream to category
        stream_category = {
            "interaction": "social",
            "action":      "procedural",
            "intent":      "reasoning",
            "experience":  "experiential",
            "observation": "sensory",
        }
        category = stream_category.get(payload.get("stream", ""), "general")

        node_id = self.v2.feel(
            content=content,
            emotion=emotion,
            intensity=final_intensity,
            category=category,
            human_id=human_id,
            module=module,
        )

        if node_id:
            self._processed += 1
            self.log(f"TRACE → felt as '{emotion}' (intensity: {final_intensity:.2f})")
            return True
        return False


class SignificanceToBeliefs(WhisperBridge):
    """
    WHISPER 2: v2 FeltSignificance ──→ v1 SELF beliefs
    What v2 feels is most significant crystallizes into v1 identity beliefs.
    Felt importance becomes who FORGE is.
    """

    SIGNIFICANCE_THRESHOLD = 0.55
    _last_crystallized: set = set()

    def whisper(self, payload: dict) -> bool:
        human_id = payload.get("human_id", "default")
        significant = self.v2.get_significant(human_id, top_k=5)

        crystallized = 0
        for memory in significant:
            sig = memory.get("_felt_significance", 0)
            content = memory.get("content", "")
            node_id = memory.get("id", "")

            # Only crystallize high significance memories not yet crystallized
            if sig >= self.SIGNIFICANCE_THRESHOLD and node_id not in self._last_crystallized:
                belief = f"Deeply felt: {content[:120]}"
                belief_id = self.v1.add_belief(belief, confidence=min(0.95, sig))
                if belief_id:
                    self._last_crystallized.add(node_id)
                    crystallized += 1
                    self.log(f"significance {sig:.3f} → crystallized as belief")

        self._processed += crystallized
        return crystallized > 0


class InstinctsToBond(WhisperBridge):
    """
    WHISPER 3: v2 BodyMemory ──→ v1 BOND
    Instincts that form in v2 get remembered in v1's relationship layer.
    Automatic behaviors become part of the shared history.
    """

    _remembered_instincts: set = set()

    def whisper(self, payload: dict) -> bool:
        human_id = payload.get("human_id", "default")
        instincts = self.v2.get_instincts()

        remembered = 0
        for instinct_name in instincts:
            if instinct_name not in self._remembered_instincts:
                # Remember as a bond moment
                self.v1.remember_moment(
                    human_id=human_id,
                    moment=f"Instinct formed: '{instinct_name}' became automatic through repetition",
                    emotion="clarity",
                    significance=0.8,
                )
                # Also add as shared language — a new capability both know about
                self.v1.add_shared_term(
                    human_id=human_id,
                    term=instinct_name,
                    meaning=f"An automatic instinct FORGE developed — fires without conscious reasoning",
                )
                self._remembered_instincts.add(instinct_name)
                remembered += 1
                self.log(f"instinct '{instinct_name}' → remembered in BOND")

        self._processed += remembered
        return remembered > 0


class GenesisToPathways(WhisperBridge):
    """
    WHISPER 4: v1 GENESIS ──→ v2 pathway weight
    Genesis thoughts — seeds, crystallizations, shifts —
    get felt in v2 with boosted intensity.
    Thinking that shaped creation becomes stronger pathways.
    """

    GENESIS_INTENSITY_MAP = {
        "seed":            0.85,
        "crystallization": 0.95,
        "shift":           0.80,
        "question":        0.70,
        "silence":         0.75,
        "ghost":           0.60,
    }

    _processed_thoughts: set = set()

    def whisper(self, payload: dict) -> bool:
        human_id = payload.get("human_id", "default")
        thoughts = self.v1.get_recent_genesis(human_id, limit=20)

        felt = 0
        for thought in thoughts:
            thought_id = thought.get("id", "")
            if thought_id in self._processed_thoughts:
                continue

            thought_type = thought.get("thought_type", "question")
            content = thought.get("content", "")
            intensity = self.GENESIS_INTENSITY_MAP.get(thought_type, 0.6)

            # Genesis thinking gets felt as clarity or awe
            emotion = "awe" if thought_type in ("crystallization", "seed") else "clarity"

            node_id = self.v2.feel(
                content=f"[genesis:{thought_type}] {content}",
                emotion=emotion,
                intensity=intensity,
                category="genesis",
                human_id=human_id,
                module="genesis_bridge",
            )

            if node_id:
                self._processed_thoughts.add(thought_id)
                felt += 1
                self.log(f"genesis '{thought_type}' → pathway with intensity {intensity:.2f}")

        self._processed += felt
        return felt > 0


# ═══════════════════════════════════════════════════════════════════════════════
#  UNIFIED MEMORY — Main Interface
# ═══════════════════════════════════════════════════════════════════════════════

class ForgeMemoryUnified:
    """
    The two halves of FORGE's memory speaking to each other.

    v1 knows what happened, who the relationship is.
    v2 knows how strongly it was felt, what became instinct.
    Together they form one complete living memory.

    Usage:
        unified = ForgeMemoryUnified()
        unified.start("umang")

        # The bridge runs silently — v1 and v2 whisper to each other
        # Every 30 seconds all four bridges sync automatically
        # Or trigger manually:
        unified.sync("umang")
    """

    def __init__(self, sync_interval: float = 30.0):
        self.v1 = V1Client()
        self.v2 = V2Client()
        self.sync_interval = sync_interval
        self._human_id = "default"
        self._running = False
        self._sync_thread: Optional[threading.Thread] = None
        self._sync_count = 0

        # The four whispers
        self.whispers = {
            "trace→emotion":      TraceToEmotion("trace→emotion", self.v1, self.v2),
            "significance→self":  SignificanceToBeliefs("significance→self", self.v1, self.v2),
            "instincts→bond":     InstinctsToBond("instincts→bond", self.v1, self.v2),
            "genesis→pathways":   GenesisToPathways("genesis→pathways", self.v1, self.v2),
        }

    def start(self, human_id: str = "default"):
        """Start the unified bridge — begins whispering between v1 and v2."""
        self._human_id = human_id

        v1_alive = self.v1.is_alive()
        v2_alive = self.v2.is_alive()

        cprint(f"\n[bold yellow]🌉 FORGE_MEMORY_UNIFIED starting...[/bold yellow]")
        cprint(f"  v1 (GENESIS/TRACE/SELF/BOND): {'[green]✓ alive[/green]' if v1_alive else '[red]✗ offline[/red]'}")
        cprint(f"  v2 (Neurogenic/Pathways):     {'[green]✓ alive[/green]' if v2_alive else '[red]✗ offline[/red]'}")

        if not v1_alive and not v2_alive:
            cprint("  [yellow]Both systems offline — running in simulation mode[/yellow]")

        # Initial sync
        self.sync(human_id)

        # Start background sync loop
        self._running = True
        self._sync_thread = threading.Thread(
            target=self._sync_loop,
            daemon=True,
        )
        self._sync_thread.start()

        cprint(f"  [dim]Sync interval: every {self.sync_interval}s[/dim]")
        cprint(f"  [bold green]✓ Unified memory bridge active[/bold green]\n")

    def sync(self, human_id: Optional[str] = None) -> dict:
        """
        Run all four whispers once.
        This is the heartbeat of the unified system.
        """
        human_id = human_id or self._human_id
        payload = {"human_id": human_id}
        results = {}

        for name, whisper in self.whispers.items():
            try:
                success = whisper.whisper(payload)
                results[name] = "✓" if success else "~"
            except Exception as e:
                results[name] = "✗"

        self._sync_count += 1
        return results

    def _sync_loop(self):
        while self._running:
            time.sleep(self.sync_interval)
            self.sync()

    def stop(self):
        self._running = False
        if self._sync_thread:
            self._sync_thread.join(timeout=2)

    def status(self) -> dict:
        dominant = self.v2.get_dominant_emotion()
        body = self.v2.get_body_snapshot()
        significant = self.v2.get_significant(self._human_id, top_k=3)

        return {
            "v1_alive":          self.v1.is_alive(),
            "v2_alive":          self.v2.is_alive(),
            "human_id":          self._human_id,
            "sync_count":        self._sync_count,
            "sync_interval":     self.sync_interval,
            "dominant_emotion":  dominant,
            "instincts":         body.get("instinct_names", []),
            "whisper_stats":     {name: w._processed for name, w in self.whispers.items()},
            "top_significant":   [m.get("content", "")[:60] for m in significant],
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

def display_status(unified: ForgeMemoryUnified):
    if not RICH_AVAILABLE:
        print(json.dumps(unified.status(), indent=2))
        return

    status = unified.status()
    console.print()

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("key", style="dim")
    table.add_column("value", style="white")

    v1_status = "[green]✓ alive[/green]" if status["v1_alive"] else "[red]✗ offline[/red]"
    v2_status = "[green]✓ alive[/green]" if status["v2_alive"] else "[red]✗ offline[/red]"

    table.add_row("v1 GENESIS/TRACE/SELF/BOND", v1_status)
    table.add_row("v2 Neurogenic/Pathways",     v2_status)
    table.add_row("👤 Human",                   status["human_id"])
    table.add_row("🔄 Sync cycles",             str(status["sync_count"]))
    table.add_row("💗 Dominant emotion",         status["dominant_emotion"])
    table.add_row("⚡ Instincts formed",         ", ".join(status["instincts"]) or "none yet")

    console.print(Panel(table, title="[bold yellow]🌉 FORGE_MEMORY_UNIFIED[/bold yellow]", border_style="yellow"))

    # Whisper stats
    console.print("  [bold]Four Whispers:[/bold]")
    whisper_descriptions = {
        "trace→emotion":     "v1 TRACE      ──→  v2 EmotionalIndex",
        "significance→self": "v2 FeltSig    ──→  v1 SELF beliefs",
        "instincts→bond":    "v2 BodyMemory ──→  v1 BOND",
        "genesis→pathways":  "v1 GENESIS    ──→  v2 pathway weight",
    }
    for name, count in status["whisper_stats"].items():
        desc = whisper_descriptions.get(name, name)
        cprint(f"    🤫 {desc}  [dim]({count} whispered)[/dim]")

    if status["top_significant"]:
        console.print("\n  [bold]Most felt-significant memories:[/bold]")
        for i, mem in enumerate(status["top_significant"], 1):
            console.print(f"    {i}. [dim]{mem}[/dim]")
    console.print()


# ═══════════════════════════════════════════════════════════════════════════════
#  DEMO
# ═══════════════════════════════════════════════════════════════════════════════

def run_demo():
    cprint("\n[bold yellow]━━━ FORGE_MEMORY_UNIFIED DEMO ━━━[/bold yellow]\n") if RICH_AVAILABLE else print("=== UNIFIED DEMO ===")
    cprint("[dim]Connecting the two halves of FORGE's memory...[/dim]\n")

    unified = ForgeMemoryUnified(sync_interval=60.0)
    unified.start("umang")

    time.sleep(0.5)

    cprint("[bold]Running manual sync — all four whispers...[/bold]\n")
    results = unified.sync("umang")

    for whisper_name, result in results.items():
        color = "green" if result == "✓" else "yellow" if result == "~" else "red"
        cprint(f"  [{color}]{result}[/{color}] {whisper_name}")

    time.sleep(0.5)

    display_status(unified)

    cprint("[bold green]✓ FORGE_MEMORY_UNIFIED active[/bold green]")
    cprint("[dim]v1 and v2 are now speaking to each other.[/dim]")
    cprint("[dim]Every trace gets felt. Every felt significance crystallizes.[/dim]")
    cprint("[dim]Every instinct gets remembered. Every thought gets stronger pathways.[/dim]\n")

    return unified


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unified = run_demo()
    try:
        cprint("[dim]Press Ctrl+C to exit[/dim]")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        unified.stop()
        cprint("\n[yellow]FORGE_MEMORY_UNIFIED shutting down...[/yellow]")
