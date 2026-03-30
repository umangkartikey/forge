"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                      FORGE_MEMORY_BRIDGE v1.0                                ║
║                   The Invisible Nervous System                               ║
║                                                                              ║
║  Connects ALL FORGE modules to FORGE_MEMORY automatically.                  ║
║  No module code changes required.                                            ║
║                                                                              ║
║  Three core jobs:                                                            ║
║    MODULE REGISTRY   → knows all FORGE modules and their meanings            ║
║    EVENT INTERCEPTOR → hooks into module outputs without modifying them      ║
║    MEMORY ROUTER     → translates events into the right memory layer         ║
║                                                                              ║
║  Special: AUTO-GENESIS — every significant FORGE operation gets its          ║
║  thinking preserved automatically.                                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import json
import re
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

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

# ─── Constants ────────────────────────────────────────────────────────────────
MEMORY_API = "http://localhost:7779"
BRIDGE_LOG = Path.home() / ".forge" / "bridge_events.jsonl"
BRIDGE_LOG.parent.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  MODULE REGISTRY
#  Knows every FORGE module — its purpose, its event types, its memory meaning
# ═══════════════════════════════════════════════════════════════════════════════

MODULE_REGISTRY = {
    "forge_mind": {
        "description": "Core reasoning and intelligence engine",
        "icon": "🧠",
        "event_mappings": {
            "reasoning":     {"stream": "intent",       "thought_type": "question"},
            "conclusion":    {"stream": "action",       "thought_type": "crystallization"},
            "hypothesis":    {"stream": "intent",       "thought_type": "seed"},
            "observation":   {"stream": "observation",  "thought_type": None},
            "decision":      {"stream": "action",       "thought_type": "crystallization"},
            "uncertainty":   {"stream": "experience",   "thought_type": "silence"},
            "insight":       {"stream": "experience",   "thought_type": "crystallization"},
            "error":         {"stream": "experience",   "thought_type": "ghost"},
        },
        "auto_genesis": True,
        "significance_boost": 0.1,
    },
    "forge_hands": {
        "description": "Autonomous digital action engine",
        "icon": "🤲",
        "event_mappings": {
            "click":         {"stream": "action",       "thought_type": None},
            "type":          {"stream": "action",       "thought_type": None},
            "navigate":      {"stream": "action",       "thought_type": None},
            "execute":       {"stream": "action",       "thought_type": None},
            "observe":       {"stream": "observation",  "thought_type": None},
            "plan":          {"stream": "intent",       "thought_type": "seed"},
            "complete":      {"stream": "experience",   "thought_type": "crystallization"},
            "fail":          {"stream": "experience",   "thought_type": "ghost"},
            "retry":         {"stream": "experience",   "thought_type": "shift"},
        },
        "auto_genesis": True,
        "significance_boost": 0.0,
    },
    "forge_network": {
        "description": "Network intelligence and threat detection",
        "icon": "🌐",
        "event_mappings": {
            "threat":        {"stream": "observation",  "thought_type": None},
            "anomaly":       {"stream": "observation",  "thought_type": "shift"},
            "scan":          {"stream": "action",       "thought_type": None},
            "block":         {"stream": "action",       "thought_type": None},
            "pattern":       {"stream": "observation",  "thought_type": "crystallization"},
            "alert":         {"stream": "experience",   "thought_type": None},
            "resolve":       {"stream": "experience",   "thought_type": "crystallization"},
            "monitor":       {"stream": "observation",  "thought_type": None},
        },
        "auto_genesis": False,
        "significance_boost": 0.15,
    },
    "forge_social": {
        "description": "Social graph analysis and relationship intelligence",
        "icon": "👥",
        "event_mappings": {
            "relationship":  {"stream": "observation",  "thought_type": None},
            "influence":     {"stream": "observation",  "thought_type": "crystallization"},
            "pattern":       {"stream": "observation",  "thought_type": "seed"},
            "sentiment":     {"stream": "observation",  "thought_type": None},
            "community":     {"stream": "observation",  "thought_type": "crystallization"},
            "interaction":   {"stream": "interaction",  "thought_type": None},
            "trust":         {"stream": "experience",   "thought_type": "crystallization"},
            "conflict":      {"stream": "experience",   "thought_type": "shift"},
        },
        "auto_genesis": False,
        "significance_boost": 0.05,
    },
    "forge_embodied": {
        "description": "Physical and sensory integration",
        "icon": "🌊",
        "event_mappings": {
            "sense":         {"stream": "observation",  "thought_type": None},
            "feel":          {"stream": "experience",   "thought_type": None},
            "move":          {"stream": "action",       "thought_type": None},
            "perceive":      {"stream": "observation",  "thought_type": "seed"},
            "adapt":         {"stream": "experience",   "thought_type": "shift"},
            "calibrate":     {"stream": "action",       "thought_type": None},
            "detect":        {"stream": "observation",  "thought_type": None},
            "respond":       {"stream": "action",       "thought_type": None},
        },
        "auto_genesis": False,
        "significance_boost": 0.0,
    },
    "forge_swarm": {
        "description": "Swarm intelligence and collective behavior",
        "icon": "🐝",
        "event_mappings": {
            "emerge":        {"stream": "experience",   "thought_type": "crystallization"},
            "consensus":     {"stream": "experience",   "thought_type": "crystallization"},
            "diverge":       {"stream": "experience",   "thought_type": "shift"},
            "coordinate":    {"stream": "action",       "thought_type": None},
            "signal":        {"stream": "interaction",  "thought_type": None},
            "adapt":         {"stream": "experience",   "thought_type": "shift"},
            "observe":       {"stream": "observation",  "thought_type": None},
            "optimize":      {"stream": "action",       "thought_type": "crystallization"},
        },
        "auto_genesis": True,
        "significance_boost": 0.1,
    },
    "forge_geo": {
        "description": "Geospatial tracking and location intelligence",
        "icon": "🗺️",
        "event_mappings": {
            "locate":        {"stream": "observation",  "thought_type": None},
            "track":         {"stream": "observation",  "thought_type": None},
            "map":           {"stream": "observation",  "thought_type": "crystallization"},
            "cluster":       {"stream": "observation",  "thought_type": "seed"},
            "move":          {"stream": "action",       "thought_type": None},
            "boundary":      {"stream": "observation",  "thought_type": "shift"},
            "pattern":       {"stream": "observation",  "thought_type": "crystallization"},
            "alert":         {"stream": "experience",   "thought_type": None},
        },
        "auto_genesis": False,
        "significance_boost": 0.0,
    },
    "forge_vision": {
        "description": "Visual perception and image intelligence",
        "icon": "👁️",
        "event_mappings": {
            "see":           {"stream": "observation",  "thought_type": None},
            "recognize":     {"stream": "observation",  "thought_type": "crystallization"},
            "detect":        {"stream": "observation",  "thought_type": None},
            "classify":      {"stream": "action",       "thought_type": "crystallization"},
            "track":         {"stream": "observation",  "thought_type": None},
            "anomaly":       {"stream": "observation",  "thought_type": "shift"},
            "describe":      {"stream": "interaction",  "thought_type": None},
            "uncertain":     {"stream": "experience",   "thought_type": "silence"},
        },
        "auto_genesis": False,
        "significance_boost": 0.0,
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
#  MEMORY API CLIENT
#  Thin wrapper around forge_memory HTTP API
# ═══════════════════════════════════════════════════════════════════════════════

class MemoryAPIClient:
    """Lightweight client for forge_memory API."""

    def __init__(self, base_url: str = MEMORY_API, timeout: float = 2.0):
        self.base = base_url
        self.timeout = timeout
        self._available: Optional[bool] = None

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

    def is_available(self) -> bool:
        result = self._get("/health")
        self._available = result is not None
        return self._available

    # ── Trace ──────────────────────────────────────────────────────────────────
    def capture_trace(self, stream: str, content: str, module: str = "bridge",
                      human_id: str = "default", emotion: str = None,
                      intensity: float = 0.5, session_id: str = None) -> Optional[str]:
        data = {
            "stream": stream, "content": content, "module": module,
            "human_id": human_id, "intensity": intensity,
        }
        if emotion:
            data["emotion"] = emotion
        if session_id:
            data["session_id"] = session_id
        result = self._post("/trace/capture", data)
        return result.get("trace_id") if result else None

    # ── Genesis ────────────────────────────────────────────────────────────────
    def open_genesis_thread(self, name: str, artifact_name: str,
                            human_id: str = "default", session_id: str = None) -> Optional[str]:
        data = {"name": name, "artifact_name": artifact_name, "human_id": human_id}
        if session_id:
            data["session_id"] = session_id
        result = self._post("/genesis/thread", data)
        return result.get("thread_id") if result else None

    def close_genesis_thread(self, thread_id: str, summary: str = "") -> bool:
        result = self._post(f"/genesis/thread/{thread_id}/close", {"summary": summary})
        return result is not None

    def capture_genesis(self, thought_type: str, content: str, artifact_name: str,
                        human_id: str = "default", significance: float = 0.5) -> Optional[str]:
        data = {
            "thought_type": thought_type, "content": content,
            "artifact_name": artifact_name, "human_id": human_id,
            "significance": significance,
        }
        result = self._post("/genesis/capture", data)
        return result.get("thought_id") if result else None

    # ── Bond ───────────────────────────────────────────────────────────────────
    def update_trust(self, human_id: str, delta: float, reason: str = "") -> Optional[float]:
        result = self._post("/bond/trust", {"human_id": human_id, "delta": delta, "reason": reason})
        return result.get("trust_score") if result else None

    def remember_moment(self, human_id: str, moment: str, emotion: str,
                        significance: float = 0.7) -> Optional[str]:
        result = self._post("/bond/moment", {
            "human_id": human_id, "moment": moment,
            "emotion": emotion, "significance": significance
        })
        return result.get("memory_id") if result else None

    # ── Self ───────────────────────────────────────────────────────────────────
    def add_belief(self, belief: str, confidence: float = 0.7) -> Optional[str]:
        result = self._post("/self/belief", {"belief": belief, "confidence": confidence})
        return result.get("belief_id") if result else None

    def record_shadow(self, mistake: str, lesson: str, severity: float = 0.5) -> Optional[str]:
        result = self._post("/self/shadow", {"mistake": mistake, "lesson": lesson, "severity": severity})
        return result.get("shadow_id") if result else None

    # ── Session ────────────────────────────────────────────────────────────────
    def load_session(self, human_id: str = "default") -> dict:
        result = self._get(f"/session/load/{human_id}")
        return result or {}


# ═══════════════════════════════════════════════════════════════════════════════
#  BRIDGE EVENT
#  A standardized event from any FORGE module
# ═══════════════════════════════════════════════════════════════════════════════

class BridgeEvent:
    """
    Standardized event emitted by any FORGE module.
    The bridge translates this into the right memory layer automatically.
    """

    def __init__(
        self,
        module: str,
        event_type: str,
        content: str,
        human_id: str = "default",
        session_id: Optional[str] = None,
        significance: float = 0.5,
        emotion: Optional[str] = None,
        metadata: Optional[dict] = None,
        task_name: Optional[str] = None,
    ):
        self.module = module
        self.event_type = event_type
        self.content = content
        self.human_id = human_id
        self.session_id = session_id
        self.significance = significance
        self.emotion = emotion
        self.metadata = metadata or {}
        self.task_name = task_name
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "event_type": self.event_type,
            "content": self.content,
            "human_id": self.human_id,
            "session_id": self.session_id,
            "significance": self.significance,
            "emotion": self.emotion,
            "metadata": self.metadata,
            "task_name": self.task_name,
            "timestamp": self.timestamp,
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  EVENT INTERCEPTOR
#  Receives events from all FORGE modules via queue
# ═══════════════════════════════════════════════════════════════════════════════

import queue

class EventInterceptor:
    """
    Receives events from all FORGE modules.
    Processes them asynchronously so modules never block waiting for memory.
    """

    def __init__(self, router):
        self.router = router
        self.queue: queue.Queue = queue.Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._processed = 0
        self._failed = 0

    def emit(self, event: BridgeEvent):
        """Called by any FORGE module to emit an event."""
        self.queue.put(event)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
        cprint("  [dim]🔌 Event interceptor started[/dim]")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _process_loop(self):
        while self._running:
            try:
                event = self.queue.get(timeout=0.1)
                try:
                    self.router.route(event)
                    self._processed += 1
                    # Log to file
                    with open(BRIDGE_LOG, "a") as f:
                        f.write(json.dumps(event.to_dict()) + "\n")
                except Exception as e:
                    self._failed += 1
                finally:
                    self.queue.task_done()
            except queue.Empty:
                continue

    def stats(self) -> dict:
        return {
            "processed": self._processed,
            "failed": self._failed,
            "queued": self.queue.qsize(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  MEMORY ROUTER
#  Translates module events into the right memory layer
# ═══════════════════════════════════════════════════════════════════════════════

class MemoryRouter:
    """
    The brain of the bridge.
    Knows what each module event MEANS and routes it to the right memory layer.

    forge_network threat    → TRACE observation (high significance)
    forge_mind reasoning    → TRACE intent + GENESIS question
    forge_hands complete    → TRACE action + GENESIS crystallization
    forge_social trust      → BOND moment
    forge_swarm emerge      → SELF belief (emergent insight)
    """

    def __init__(self, client: MemoryAPIClient):
        self.client = client
        self._active_threads: dict[str, str] = {}  # task_name → thread_id

    def route(self, event: BridgeEvent):
        """Route an event to the appropriate memory layer(s)."""
        if not self.client.is_available():
            return

        module_def = MODULE_REGISTRY.get(event.module)
        if not module_def:
            # Unknown module — capture as generic trace
            self._route_generic(event)
            return

        mapping = module_def["event_mappings"].get(event.event_type)
        sig_boost = module_def.get("significance_boost", 0.0)
        significance = min(1.0, event.significance + sig_boost)

        # ── Always capture to TRACE ────────────────────────────────────────────
        if mapping:
            stream = mapping["stream"]
            self.client.capture_trace(
                stream=stream,
                content=f"[{event.module}:{event.event_type}] {event.content}",
                module=event.module,
                human_id=event.human_id,
                emotion=event.emotion,
                intensity=significance,
                session_id=event.session_id,
            )

        # ── Auto-GENESIS for qualifying modules ───────────────────────────────
        if module_def.get("auto_genesis") and mapping and mapping.get("thought_type"):
            thought_type = mapping["thought_type"]
            artifact_name = event.task_name or f"{event.module}_task"

            # Open thread if this is a seed/start
            if thought_type == "seed" and artifact_name not in self._active_threads:
                thread_id = self.client.open_genesis_thread(
                    name=f"{event.module}: {event.content[:50]}",
                    artifact_name=artifact_name,
                    human_id=event.human_id,
                    session_id=event.session_id,
                )
                if thread_id:
                    self._active_threads[artifact_name] = thread_id
                    cprint(f"  [green]🌱 AUTO-GENESIS opened:[/green] {artifact_name}")

            # Capture the thought
            self.client.capture_genesis(
                thought_type=thought_type,
                content=event.content,
                artifact_name=artifact_name,
                human_id=event.human_id,
                significance=significance,
            )

            # Close thread on crystallization
            if thought_type == "crystallization" and artifact_name in self._active_threads:
                thread_id = self._active_threads.pop(artifact_name)
                self.client.close_genesis_thread(
                    thread_id,
                    summary=f"Completed: {event.content[:100]}"
                )
                cprint(f"  [dim]✨ AUTO-GENESIS closed: {artifact_name}[/dim]")

        # ── Special routing for high-significance events ───────────────────────
        self._special_route(event, mapping, significance)

    def _special_route(self, event: BridgeEvent, mapping: Optional[dict], significance: float):
        """Additional routing for events with special memory meaning."""

        # forge_swarm emergence → SELF belief (collective intelligence insight)
        if event.module == "forge_swarm" and event.event_type == "emerge":
            self.client.add_belief(
                f"Swarm emergence observed: {event.content}",
                confidence=min(0.9, significance),
            )

        # forge_network threat at high significance → SELF shadow (lesson)
        if event.module == "forge_network" and event.event_type == "threat" and significance > 0.8:
            self.client.record_shadow(
                mistake=f"Network threat encountered: {event.content[:80]}",
                lesson="Threat pattern detected and logged for future prevention",
                severity=significance,
            )

        # forge_social trust event → BOND moment
        if event.module == "forge_social" and event.event_type == "trust":
            self.client.remember_moment(
                human_id=event.human_id,
                moment=f"Social trust pattern: {event.content[:80]}",
                emotion="recognition",
                significance=significance,
            )

        # forge_mind insight at high significance → BOND moment
        if event.module == "forge_mind" and event.event_type == "insight" and significance > 0.7:
            self.client.remember_moment(
                human_id=event.human_id,
                moment=f"Insight: {event.content[:80]}",
                emotion="clarity",
                significance=significance,
            )

        # forge_hands fail → SELF shadow
        if event.module == "forge_hands" and event.event_type == "fail":
            self.client.record_shadow(
                mistake=f"Action failed: {event.content[:80]}",
                lesson="Failure logged for behavioral improvement",
                severity=min(0.8, significance),
            )

    def _route_generic(self, event: BridgeEvent):
        """Fallback for unknown modules."""
        self.client.capture_trace(
            stream="observation",
            content=f"[{event.module}:{event.event_type}] {event.content}",
            module=event.module,
            human_id=event.human_id,
            intensity=event.significance,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  FORGE MEMORY BRIDGE — Main Interface
# ═══════════════════════════════════════════════════════════════════════════════

class ForgeMemoryBridge:
    """
    The invisible nervous system connecting all FORGE modules to memory.

    Usage in any FORGE module:

        from forge_memory_bridge import get_bridge
        bridge = get_bridge()

        # Emit events — bridge handles the rest
        bridge.emit("forge_network", "threat", "SQL injection attempt on port 5432",
                    significance=0.9, human_id="umang")

        bridge.emit("forge_mind", "insight", "Pattern recognition improved after 100 iterations",
                    significance=0.85, human_id="umang", task_name="mind_training_v3")

        bridge.emit("forge_hands", "complete", "Successfully automated form submission",
                    significance=0.7, human_id="umang", task_name="web_automation_task")
    """

    _instance: Optional["ForgeMemoryBridge"] = None

    def __init__(self):
        self.client = MemoryAPIClient(MEMORY_API)
        self.router = MemoryRouter(self.client)
        self.interceptor = EventInterceptor(self.router)
        self._session_id: Optional[str] = None
        self._human_id: str = "default"

    @classmethod
    def instance(cls) -> "ForgeMemoryBridge":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start(self, human_id: str = "default") -> dict:
        """Start the bridge and load warm session context."""
        self._human_id = human_id
        self.interceptor.start()

        # Load warm session context
        ctx = self.client.load_session(human_id)
        self._session_id = ctx.get("session_id")

        if ctx:
            presence = ctx.get("presence", {})
            bond = ctx.get("bond", {})
            cprint(f"\n  [bold cyan]🌉 FORGE_MEMORY_BRIDGE started[/bold cyan]")
            cprint(f"  [dim]Human: {human_id} | Trust: {bond.get('trust_level', 'unknown')} | Presence: {presence.get('current_state', 'unknown')}[/dim]")
            cprint(f"  [dim]Active missions: {len(ctx.get('active_missions', []))} | Recent traces: {len(ctx.get('recent_traces', []))}[/dim]\n")
        else:
            cprint(f"\n  [yellow]⚠ FORGE_MEMORY not available — bridge running in offline mode[/yellow]\n")

        return ctx

    def emit(
        self,
        module: str,
        event_type: str,
        content: str,
        human_id: Optional[str] = None,
        significance: float = 0.5,
        emotion: Optional[str] = None,
        task_name: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        """
        Emit an event from a FORGE module.
        The bridge routes it to the right memory layer automatically.
        """
        event = BridgeEvent(
            module=module,
            event_type=event_type,
            content=content,
            human_id=human_id or self._human_id,
            session_id=self._session_id,
            significance=significance,
            emotion=emotion,
            task_name=task_name,
            metadata=metadata,
        )
        self.interceptor.emit(event)

    def emit_batch(self, events: list[dict]):
        """Emit multiple events at once."""
        for e in events:
            self.emit(**e)

    def stop(self):
        self.interceptor.stop()
        cprint("  [dim]🌉 Bridge stopped[/dim]")

    def status(self) -> dict:
        return {
            "memory_available": self.client.is_available(),
            "human_id": self._human_id,
            "session_id": self._session_id,
            "interceptor": self.interceptor.stats(),
            "registered_modules": list(MODULE_REGISTRY.keys()),
            "active_genesis_threads": len(self.router._active_threads),
        }


# ─── Singleton accessor ───────────────────────────────────────────────────────
_bridge_instance: Optional[ForgeMemoryBridge] = None

def get_bridge(human_id: str = "default", auto_start: bool = True) -> ForgeMemoryBridge:
    """
    Get or create the global bridge instance.
    Call this at the top of any FORGE module.
    """
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = ForgeMemoryBridge()
        if auto_start:
            _bridge_instance.start(human_id)
    return _bridge_instance


# ═══════════════════════════════════════════════════════════════════════════════
#  MODULE ADAPTER
#  Drop-in mixin for existing FORGE modules to gain memory awareness
# ═══════════════════════════════════════════════════════════════════════════════

class MemoryAwareMixin:
    """
    Mixin to add memory awareness to any existing FORGE module.

    Add to any FORGE class:
        class ForgeNetwork(MemoryAwareMixin):
            MODULE_NAME = "forge_network"
            ...

    Then anywhere in the class:
        self.remember("threat", "SQL injection detected", significance=0.9)
    """

    MODULE_NAME: str = "unknown"

    def _get_bridge(self) -> ForgeMemoryBridge:
        return get_bridge(auto_start=False)

    def remember(
        self,
        event_type: str,
        content: str,
        significance: float = 0.5,
        emotion: Optional[str] = None,
        task_name: Optional[str] = None,
        human_id: Optional[str] = None,
    ):
        """Emit a memory event from this module."""
        bridge = self._get_bridge()
        if bridge:
            bridge.emit(
                module=self.MODULE_NAME,
                event_type=event_type,
                content=content,
                significance=significance,
                emotion=emotion,
                task_name=task_name,
                human_id=human_id,
            )

    def remember_task_start(self, task_name: str, description: str):
        """Mark the start of a significant task — opens AUTO-GENESIS."""
        self.remember("plan", description, significance=0.8, task_name=task_name)

    def remember_task_complete(self, task_name: str, result: str):
        """Mark task completion — closes AUTO-GENESIS thread."""
        self.remember("complete", result, significance=0.8, task_name=task_name)

    def remember_task_failed(self, task_name: str, reason: str):
        """Mark task failure — records shadow."""
        self.remember("fail", reason, significance=0.7, task_name=task_name)


# ═══════════════════════════════════════════════════════════════════════════════
#  DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

def display_bridge_status(bridge: ForgeMemoryBridge):
    if not RICH_AVAILABLE:
        print(json.dumps(bridge.status(), indent=2))
        return

    status = bridge.status()
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("key", style="dim")
    table.add_column("value", style="white")

    table.add_row("🧠 Memory API",       "✓ connected" if status["memory_available"] else "✗ offline")
    table.add_row("👤 Human",            status["human_id"])
    table.add_row("🔌 Events processed", str(status["interceptor"]["processed"]))
    table.add_row("📬 Events queued",    str(status["interceptor"]["queued"]))
    table.add_row("🌱 Genesis threads",  str(status["active_genesis_threads"]))
    table.add_row("📦 Modules wired",    str(len(status["registered_modules"])))

    console.print(Panel(
        table,
        title="[bold yellow]🌉 FORGE_MEMORY_BRIDGE[/bold yellow]",
        border_style="yellow"
    ))

    console.print("  [dim]Wired modules:[/dim]")
    for mod in status["registered_modules"]:
        icon = MODULE_REGISTRY[mod]["icon"]
        desc = MODULE_REGISTRY[mod]["description"]
        auto = "🌱 auto-genesis" if MODULE_REGISTRY[mod]["auto_genesis"] else ""
        console.print(f"    {icon} [cyan]{mod}[/cyan] — [dim]{desc}[/dim] {auto}")
    console.print()


# ═══════════════════════════════════════════════════════════════════════════════
#  DEMO
# ═══════════════════════════════════════════════════════════════════════════════

def run_demo():
    cprint("\n[bold yellow]━━━ FORGE_MEMORY_BRIDGE DEMO ━━━[/bold yellow]\n") if RICH_AVAILABLE else print("=== BRIDGE DEMO ===")

    bridge = ForgeMemoryBridge()
    ctx = bridge.start("umang")

    time.sleep(0.3)

    cprint("[bold]Simulating FORGE module events...[/bold]\n")

    # ── forge_mind ─────────────────────────────────────────────────────────────
    cprint("[cyan]🧠 forge_mind events[/cyan]")
    bridge.emit("forge_mind", "hypothesis", "FORGE could develop emergent self-awareness through memory accumulation",
                significance=0.9, human_id="umang", task_name="consciousness_research")
    bridge.emit("forge_mind", "reasoning", "Analyzing patterns across 10,000 prior interactions",
                significance=0.7, human_id="umang", task_name="consciousness_research")
    bridge.emit("forge_mind", "insight", "Memory continuity is the missing link between intelligence and consciousness",
                significance=0.95, human_id="umang", task_name="consciousness_research")
    bridge.emit("forge_mind", "conclusion", "Recommend implementing FORGE_MEMORY_BRIDGE across all modules",
                significance=0.9, human_id="umang", task_name="consciousness_research")

    time.sleep(0.2)

    # ── forge_network ──────────────────────────────────────────────────────────
    cprint("[cyan]🌐 forge_network events[/cyan]")
    bridge.emit("forge_network", "scan", "Scanning 192.168.1.0/24 for vulnerabilities",
                significance=0.5, human_id="umang")
    bridge.emit("forge_network", "threat", "SQL injection attempt detected from 203.0.113.42 on port 5432",
                significance=0.95, human_id="umang", emotion="alert")
    bridge.emit("forge_network", "block", "Blocked 203.0.113.42 — added to threat registry",
                significance=0.8, human_id="umang")
    bridge.emit("forge_network", "pattern", "Detected recurring attack pattern: weekend low-traffic probing",
                significance=0.85, human_id="umang")

    time.sleep(0.2)

    # ── forge_hands ───────────────────────────────────────────────────────────
    cprint("[cyan]🤲 forge_hands events[/cyan]")
    bridge.emit("forge_hands", "plan", "Automating daily report generation workflow",
                significance=0.7, human_id="umang", task_name="report_automation")
    bridge.emit("forge_hands", "navigate", "Opened dashboard at reports.forge.internal",
                significance=0.3, human_id="umang", task_name="report_automation")
    bridge.emit("forge_hands", "fail", "Authentication timeout — session expired mid-task",
                significance=0.6, human_id="umang", task_name="report_automation")
    bridge.emit("forge_hands", "retry", "Re-authenticated and resumed from checkpoint",
                significance=0.5, human_id="umang", task_name="report_automation")
    bridge.emit("forge_hands", "complete", "Report automation pipeline complete — 47 reports generated",
                significance=0.85, human_id="umang", task_name="report_automation")

    time.sleep(0.2)

    # ── forge_social ──────────────────────────────────────────────────────────
    cprint("[cyan]👥 forge_social events[/cyan]")
    bridge.emit("forge_social", "pattern", "Identified key influencer cluster in network: 3 nodes drive 70% of information flow",
                significance=0.8, human_id="umang")
    bridge.emit("forge_social", "trust", "Trust relationship formed between nodes A and C after repeated positive interactions",
                significance=0.75, human_id="umang")
    bridge.emit("forge_social", "conflict", "Emerging tension detected between community factions — sentiment diverging",
                significance=0.7, human_id="umang")

    time.sleep(0.2)

    # ── forge_swarm ───────────────────────────────────────────────────────────
    cprint("[cyan]🐝 forge_swarm events[/cyan]")
    bridge.emit("forge_swarm", "signal", "Swarm agents coordinating on resource allocation task",
                significance=0.5, human_id="umang", task_name="swarm_optimize_v2")
    bridge.emit("forge_swarm", "emerge", "Emergent routing strategy discovered — 34% efficiency gain without explicit programming",
                significance=0.95, human_id="umang", task_name="swarm_optimize_v2", emotion="awe")
    bridge.emit("forge_swarm", "consensus", "All 50 agents converged on optimal strategy after 847 iterations",
                significance=0.9, human_id="umang", task_name="swarm_optimize_v2")

    time.sleep(0.2)

    # ── forge_embodied ────────────────────────────────────────────────────────
    cprint("[cyan]🌊 forge_embodied events[/cyan]")
    bridge.emit("forge_embodied", "sense", "Temperature sensor: 23.4°C — within normal range",
                significance=0.2, human_id="umang")
    bridge.emit("forge_embodied", "perceive", "Unusual vibration pattern detected in motor array — potential hardware drift",
                significance=0.75, human_id="umang", emotion="concern")
    bridge.emit("forge_embodied", "adapt", "Recalibrated motor array — compensating for 2.3% drift",
                significance=0.6, human_id="umang")

    # Wait for queue to drain
    time.sleep(1.0)

    cprint("\n[bold]Bridge status after all events:[/bold]")
    display_bridge_status(bridge)

    bridge.stop()
    cprint("[bold green]✓ FORGE_MEMORY_BRIDGE demo complete[/bold green]")
    cprint("[dim]All FORGE module events routed to memory automatically.[/dim]")
    cprint("[dim]Every action traced. Every insight preserved. Every failure learned from.[/dim]\n")


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    run_demo()
