"""
FORGE Prefrontal Cortex — forge_prefrontal.py
==============================================
AI analog of the prefrontal cortex — the executive brain.
The CEO that takes perception and turns it into intelligent action.

Receives input from forge_temporal.py perception events.
Dispatches decisions to other FORGE modules.

Modules:
  GoalManager          — active goals, priority stack
  DecisionEngine       — weighs options, picks best action
  ImpulseFilter        — suppresses rash/dangerous decisions
  WorkingMemoryBuffer  — holds live context across reasoning steps
  RiskAssessor         — predicts consequences before acting
  ExecutivePlanner     — builds multi-step action sequences
  PerceptionIntegrator — receives from forge_temporal
  ActionDispatcher     — fires plans to other FORGE modules
"""

import json
import time
import uuid
import sqlite3
import threading
import math
from datetime import datetime
from collections import deque
from typing import Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.layout import Layout
    from rich.text import Text
    from rich.columns import Columns
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

try:
    from flask import Flask, request, jsonify
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

# ─── Constants ────────────────────────────────────────────────────────────────

DB_PATH  = "forge_prefrontal.db"
API_PORT = 7779
VERSION  = "1.0.0"

console = Console() if HAS_RICH else None

# ─── Enums ────────────────────────────────────────────────────────────────────

class Priority(Enum):
    CRITICAL = 5
    HIGH     = 4
    MEDIUM   = 3
    LOW      = 2
    IDLE     = 1

class ActionStatus(Enum):
    PENDING   = "PENDING"
    APPROVED  = "APPROVED"
    VETOED    = "VETOED"
    EXECUTING = "EXECUTING"
    COMPLETE  = "COMPLETE"
    FAILED    = "FAILED"

class GoalStatus(Enum):
    ACTIVE    = "ACTIVE"
    PAUSED    = "PAUSED"
    ACHIEVED  = "ACHIEVED"
    ABANDONED = "ABANDONED"

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class Goal:
    id:          str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:        str = ""
    description: str = ""
    priority:    int = Priority.MEDIUM.value
    status:      str = GoalStatus.ACTIVE.value
    progress:    float = 0.0
    created:     str = field(default_factory=lambda: datetime.now().isoformat())
    deadline:    Optional[str] = None
    subgoals:    list = field(default_factory=list)
    dependencies:list = field(default_factory=list)
    success_criteria: str = ""

@dataclass
class Option:
    id:           str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    action:       str = ""
    rationale:    str = ""
    risk_score:   float = 0.0
    reward_score: float = 0.0
    feasibility:  float = 1.0
    time_cost:    int = 1        # estimated steps
    utility:      float = 0.0   # computed

@dataclass
class ExecutionPlan:
    id:          str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal_id:     str = ""
    steps:       list = field(default_factory=list)
    status:      str = ActionStatus.PENDING.value
    risk:        float = 0.0
    confidence:  float = 0.0
    created:     str = field(default_factory=lambda: datetime.now().isoformat())
    completed:   Optional[str] = None
    outcome:     str = ""
    vetoed_by:   str = ""

@dataclass
class WorkingMemoryFrame:
    id:          str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:   str = field(default_factory=lambda: datetime.now().isoformat())
    context:     dict = field(default_factory=dict)
    active_goals:list = field(default_factory=list)
    threat_level:int = 0
    focus:       str = ""
    reasoning_chain: list = field(default_factory=list)

@dataclass
class DecisionRecord:
    id:          str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp:   str = field(default_factory=lambda: datetime.now().isoformat())
    context:     str = ""
    options:     list = field(default_factory=list)
    chosen:      str = ""
    vetoed:      list = field(default_factory=list)
    confidence:  float = 0.0
    reasoning:   str = ""
    outcome:     str = ""

# ─── Database ─────────────────────────────────────────────────────────────────

class PrefrontalDB:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init()

    def _init(self):
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS goals (
                    id TEXT PRIMARY KEY, name TEXT, description TEXT,
                    priority INTEGER, status TEXT, progress REAL,
                    created TEXT, deadline TEXT, subgoals TEXT,
                    dependencies TEXT, success_criteria TEXT
                );
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY, goal_id TEXT, steps TEXT,
                    status TEXT, risk REAL, confidence REAL,
                    created TEXT, completed TEXT, outcome TEXT, vetoed_by TEXT
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY, timestamp TEXT, context TEXT,
                    options TEXT, chosen TEXT, vetoed TEXT,
                    confidence REAL, reasoning TEXT, outcome TEXT
                );
                CREATE TABLE IF NOT EXISTS working_memory (
                    id TEXT PRIMARY KEY, timestamp TEXT, context TEXT,
                    active_goals TEXT, threat_level INTEGER,
                    focus TEXT, reasoning_chain TEXT
                );
            """)
            self.conn.commit()

    def save_goal(self, g: Goal):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO goals VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (g.id, g.name, g.description, g.priority, g.status,
                  g.progress, g.created, g.deadline,
                  json.dumps(g.subgoals), json.dumps(g.dependencies),
                  g.success_criteria))
            self.conn.commit()

    def save_plan(self, p: ExecutionPlan):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO plans VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (p.id, p.goal_id, json.dumps(p.steps), p.status,
                  p.risk, p.confidence, p.created, p.completed,
                  p.outcome, p.vetoed_by))
            self.conn.commit()

    def save_decision(self, d: DecisionRecord):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO decisions VALUES (?,?,?,?,?,?,?,?,?)
            """, (d.id, d.timestamp, d.context, json.dumps(d.options),
                  d.chosen, json.dumps(d.vetoed), d.confidence,
                  d.reasoning, d.outcome))
            self.conn.commit()

    def get_goals(self, status=None):
        with self.lock:
            if status:
                return self.conn.execute(
                    "SELECT * FROM goals WHERE status=? ORDER BY priority DESC", (status,)
                ).fetchall()
            return self.conn.execute(
                "SELECT * FROM goals ORDER BY priority DESC"
            ).fetchall()

    def get_plans(self, limit=20):
        with self.lock:
            return self.conn.execute(
                "SELECT * FROM plans ORDER BY created DESC LIMIT ?", (limit,)
            ).fetchall()

    def get_decisions(self, limit=20):
        with self.lock:
            return self.conn.execute(
                "SELECT id, timestamp, chosen, confidence, reasoning FROM decisions ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()

# ─── Goal Manager ─────────────────────────────────────────────────────────────

class GoalManager:
    """Maintains the active goal stack and priority ordering."""

    def __init__(self, db: PrefrontalDB):
        self.db = db
        self.goals: dict[str, Goal] = {}
        self._load_defaults()

    def _load_defaults(self):
        defaults = [
            Goal(name="SYSTEM_INTEGRITY",
                 description="Maintain stable, secure system operation",
                 priority=Priority.CRITICAL.value,
                 success_criteria="No critical threats unaddressed"),
            Goal(name="SITUATIONAL_AWARENESS",
                 description="Continuously monitor and understand environment",
                 priority=Priority.HIGH.value,
                 success_criteria="All perception streams active"),
            Goal(name="RESOURCE_EFFICIENCY",
                 description="Optimize resource usage across all modules",
                 priority=Priority.MEDIUM.value,
                 success_criteria="CPU/memory within thresholds"),
            Goal(name="LEARNING_AND_ADAPTATION",
                 description="Improve decision quality over time",
                 priority=Priority.LOW.value,
                 success_criteria="Decision confidence trending upward"),
        ]
        for g in defaults:
            self.goals[g.id] = g
            self.db.save_goal(g)

    def add_goal(self, name: str, description: str,
                 priority: int = Priority.MEDIUM.value,
                 deadline: str = None,
                 success_criteria: str = "") -> Goal:
        g = Goal(name=name, description=description,
                 priority=priority, deadline=deadline,
                 success_criteria=success_criteria)
        self.goals[g.id] = g
        self.db.save_goal(g)
        return g

    def get_active(self) -> list[Goal]:
        active = [g for g in self.goals.values() if g.status == GoalStatus.ACTIVE.value]
        return sorted(active, key=lambda g: g.priority, reverse=True)

    def top_goal(self) -> Optional[Goal]:
        active = self.get_active()
        return active[0] if active else None

    def update_progress(self, goal_id: str, progress: float, status: str = None):
        if goal_id in self.goals:
            self.goals[goal_id].progress = max(0.0, min(1.0, progress))
            if status:
                self.goals[goal_id].status = status
            self.db.save_goal(self.goals[goal_id])

    def prioritize_by_threat(self, threat_level: int):
        """Elevate SYSTEM_INTEGRITY goal when threat is high."""
        for g in self.goals.values():
            if g.name == "SYSTEM_INTEGRITY":
                if threat_level >= 3:
                    g.priority = Priority.CRITICAL.value
                elif threat_level >= 1:
                    g.priority = Priority.HIGH.value
                else:
                    g.priority = Priority.CRITICAL.value  # always critical baseline
                self.db.save_goal(g)

    def summary(self) -> list[dict]:
        return [{"id": g.id, "name": g.name, "priority": g.priority,
                 "status": g.status, "progress": g.progress}
                for g in self.get_active()]


# ─── Risk Assessor ────────────────────────────────────────────────────────────

class RiskAssessor:
    """Predicts consequences before acting — looks before leaping."""

    DANGEROUS_ACTIONS = [
        "delete", "shutdown", "override", "bypass", "force", "disable",
        "terminate", "erase", "broadcast", "expose", "escalate_all"
    ]
    SAFE_ACTIONS = [
        "monitor", "log", "alert", "report", "pause", "verify",
        "request_confirmation", "snapshot", "notify", "analyze"
    ]

    def assess(self, action: str, context: dict) -> dict:
        action_lower = action.lower()
        threat = context.get("threat_level", 0)

        base_risk = 0.1
        for word in self.DANGEROUS_ACTIONS:
            if word in action_lower:
                base_risk += 0.25

        for word in self.SAFE_ACTIONS:
            if word in action_lower:
                base_risk -= 0.05

        # Threat amplifies risk of aggressive actions
        threat_multiplier = 1.0 + (threat * 0.1)
        final_risk = min(1.0, max(0.0, base_risk * threat_multiplier))

        irreversible = any(w in action_lower for w in ["delete","erase","terminate","shutdown"])
        cascading    = any(w in action_lower for w in ["broadcast","escalate","override"])

        consequences = self._predict_consequences(action_lower, threat)

        return {
            "risk_score":    round(final_risk, 2),
            "risk_label":    "CRITICAL" if final_risk > 0.8 else
                             "HIGH"     if final_risk > 0.6 else
                             "MEDIUM"   if final_risk > 0.3 else "LOW",
            "irreversible":  irreversible,
            "cascading":     cascading,
            "consequences":  consequences,
            "safe_to_proceed": final_risk < 0.5 and not irreversible
        }

    def _predict_consequences(self, action: str, threat: int) -> list:
        consequences = []
        if "monitor" in action:     consequences.append("Increased observability — no side effects")
        if "alert" in action:       consequences.append("Notification sent — triggers response chain")
        if "shutdown" in action:    consequences.append("⚠ SERVICE INTERRUPTION — all dependent modules halted")
        if "delete" in action:      consequences.append("⚠ IRREVERSIBLE DATA LOSS")
        if "override" in action:    consequences.append("⚠ Bypasses safety checks — cascading risk")
        if "log" in action:         consequences.append("Audit trail created — forensic value")
        if "verify" in action:      consequences.append("Confirmation required — delays action by 1 step")
        if "notify" in action:      consequences.append("Human or system notified — response latency varies")
        if not consequences:        consequences.append("Action effect unclear — additional analysis needed")
        return consequences


# ─── Impulse Filter ───────────────────────────────────────────────────────────

class ImpulseFilter:
    """The brain's brakes — suppresses rash, dangerous, or premature decisions."""

    VETO_RULES = [
        ("risk_score > 0.8",       "Risk exceeds safety threshold"),
        ("irreversible + low_conf", "Irreversible action with low confidence"),
        ("no_active_goal",          "No active goal justifies this action"),
        ("threat_0 + aggressive",   "Aggressive action with no threat present"),
        ("cascading + unverified",  "Cascading action without verification step"),
    ]

    def evaluate(self, option: Option, risk: dict, context: dict) -> tuple[bool, str]:
        threat  = context.get("threat_level", 0)
        vetoed  = False
        reason  = ""

        # Hard veto: extreme risk
        if risk["risk_score"] > 0.85:
            return True, f"VETOED: Risk score {risk['risk_score']} exceeds 0.85 hard limit"

        # Hard veto: irreversible + low confidence
        if risk["irreversible"] and option.feasibility < 0.6:
            return True, "VETOED: Irreversible action blocked — insufficient confidence"

        # Hard veto: cascading without verify step
        if risk["cascading"] and "verify" not in option.action.lower():
            return True, "VETOED: Cascading action requires verification step first"

        # Soft veto: aggressive action with no threat
        aggressive_words = ["terminate","force","disable","override","shutdown"]
        is_aggressive = any(w in option.action.lower() for w in aggressive_words)
        if is_aggressive and threat == 0:
            return True, "VETOED: Aggressive action unjustified — threat level is NONE"

        # Soft veto: low utility
        if option.utility < 0.15:
            return True, f"VETOED: Utility {round(option.utility,2)} too low to justify action"

        return False, ""

    def impulse_check(self, options: list[Option], risk_map: dict, context: dict) -> tuple[list, list]:
        approved = []
        vetoed   = []
        for opt in options:
            risk = risk_map.get(opt.id, {})
            is_vetoed, reason = self.evaluate(opt, risk, context)
            if is_vetoed:
                opt_dict = asdict(opt)
                opt_dict["veto_reason"] = reason
                vetoed.append(opt_dict)
            else:
                approved.append(opt)
        return approved, vetoed


# ─── Working Memory Buffer ────────────────────────────────────────────────────

class WorkingMemoryBuffer:
    """Holds live context across reasoning steps — the scratchpad of thought."""

    def __init__(self, capacity=12):
        self.capacity  = capacity
        self.frames: deque[WorkingMemoryFrame] = deque(maxlen=capacity)
        self.current: Optional[WorkingMemoryFrame] = None

    def new_frame(self, context: dict, goals: list, threat: int, focus: str) -> WorkingMemoryFrame:
        frame = WorkingMemoryFrame(
            context=context,
            active_goals=goals,
            threat_level=threat,
            focus=focus
        )
        self.current = frame
        self.frames.append(frame)
        return frame

    def add_reasoning(self, step: str):
        if self.current:
            self.current.reasoning_chain.append({
                "step": len(self.current.reasoning_chain) + 1,
                "thought": step,
                "time": datetime.now().isoformat()
            })

    def recall(self, n=3) -> list[WorkingMemoryFrame]:
        return list(self.frames)[-n:]

    def context_summary(self) -> dict:
        if not self.current:
            return {"status": "empty"}
        return {
            "focus":          self.current.focus,
            "threat_level":   self.current.threat_level,
            "active_goals":   len(self.current.active_goals),
            "reasoning_steps":len(self.current.reasoning_chain),
            "frame_id":       self.current.id
        }


# ─── Decision Engine ──────────────────────────────────────────────────────────

class DecisionEngine:
    """Weighs options using multi-criteria utility function."""

    WEIGHTS = {
        "reward":      0.35,
        "feasibility": 0.25,
        "risk_inv":    0.25,   # inverted risk — lower risk = higher score
        "time_inv":    0.15,   # inverted time cost
    }

    def generate_options(self, context: dict) -> list[Option]:
        threat  = context.get("threat_level", 0)
        anomaly = context.get("anomaly", False)
        focus   = context.get("focus", "")

        options = []

        # Always available base options
        options.append(Option(
            action="monitor_and_log",
            rationale="Continue passive observation, record all events",
            risk_score=0.05, reward_score=0.4, feasibility=1.0, time_cost=1
        ))
        options.append(Option(
            action="analyze_deeper",
            rationale="Run additional analysis passes on current data",
            risk_score=0.1, reward_score=0.5, feasibility=0.95, time_cost=2
        ))

        # Threat-scaled options
        if threat >= 1:
            options.append(Option(
                action="elevate_alert_status",
                rationale="Raise system alert level, increase monitoring frequency",
                risk_score=0.15, reward_score=0.65, feasibility=0.9, time_cost=1
            ))
            options.append(Option(
                action="notify_supervisory_system",
                rationale="Send alert to higher-level oversight module",
                risk_score=0.1, reward_score=0.6, feasibility=0.95, time_cost=1
            ))

        if threat >= 2:
            options.append(Option(
                action="request_verification",
                rationale="Pause and request human or system confirmation before proceeding",
                risk_score=0.05, reward_score=0.7, feasibility=0.85, time_cost=3
            ))
            options.append(Option(
                action="isolate_affected_subsystem",
                rationale="Quarantine the flagged component to prevent spread",
                risk_score=0.35, reward_score=0.75, feasibility=0.8, time_cost=2
            ))

        if threat >= 3:
            options.append(Option(
                action="activate_defensive_protocols",
                rationale="Deploy full defensive posture across all FORGE modules",
                risk_score=0.4, reward_score=0.85, feasibility=0.75, time_cost=2
            ))
            options.append(Option(
                action="snapshot_and_preserve_state",
                rationale="Create system snapshot before any further action",
                risk_score=0.1, reward_score=0.8, feasibility=0.9, time_cost=1
            ))

        if threat >= 4:
            options.append(Option(
                action="emergency_containment",
                rationale="Maximum containment — lock down all non-essential processes",
                risk_score=0.55, reward_score=0.95, feasibility=0.7, time_cost=1
            ))
            options.append(Option(
                action="terminate_threat_source",
                rationale="Identify and terminate the source of the threat",
                risk_score=0.75, reward_score=0.9, feasibility=0.6, time_cost=2
            ))

        if anomaly:
            options.append(Option(
                action="run_anomaly_deep_scan",
                rationale="Focused deep scan on anomalous signals",
                risk_score=0.1, reward_score=0.65, feasibility=0.9, time_cost=2
            ))

        # Compute utility for each
        for opt in options:
            opt.utility = self._utility(opt)

        return sorted(options, key=lambda o: o.utility, reverse=True)

    def _utility(self, opt: Option) -> float:
        risk_inv = 1.0 - opt.risk_score
        time_inv = 1.0 / max(opt.time_cost, 1)
        u = (self.WEIGHTS["reward"]      * opt.reward_score +
             self.WEIGHTS["feasibility"] * opt.feasibility  +
             self.WEIGHTS["risk_inv"]    * risk_inv         +
             self.WEIGHTS["time_inv"]    * time_inv)
        return round(u, 3)

    def select_best(self, approved: list[Option]) -> Optional[Option]:
        if not approved:
            return None
        return max(approved, key=lambda o: o.utility)


# ─── Executive Planner ────────────────────────────────────────────────────────

class ExecutivePlanner:
    """Turns a chosen option into a sequenced multi-step execution plan."""

    STEP_TEMPLATES = {
        "monitor_and_log":           ["initialize_log_session", "activate_stream_capture", "set_review_interval_60s"],
        "analyze_deeper":            ["snapshot_current_state", "run_semantic_pass", "run_temporal_correlation", "compile_report"],
        "elevate_alert_status":      ["record_current_baseline", "increment_alert_level", "notify_all_modules", "await_confirmation"],
        "notify_supervisory_system": ["compose_alert_packet", "attach_perception_snapshot", "transmit_to_supervisor", "log_transmission"],
        "request_verification":      ["pause_autonomous_action", "compose_verification_request", "transmit_request", "await_response_30s"],
        "isolate_affected_subsystem":["identify_blast_radius", "sever_subsystem_connections", "snapshot_subsystem_state", "begin_forensic_analysis"],
        "activate_defensive_protocols":["broadcast_threat_level", "activate_forge_network_shield", "activate_forge_hands_lockdown", "begin_continuous_monitoring"],
        "snapshot_and_preserve_state":["halt_write_operations_temp", "capture_full_system_state", "compress_and_store", "resume_operations"],
        "emergency_containment":     ["broadcast_emergency_signal", "lock_all_non_essential_processes", "preserve_audit_trail", "await_executive_override"],
        "terminate_threat_source":   ["verify_threat_identification", "request_confirmation", "execute_targeted_termination", "post_action_audit"],
        "run_anomaly_deep_scan":     ["focus_temporal_cortex", "cross_reference_baselines", "generate_anomaly_report", "update_threat_model"],
    }

    def build(self, option: Option, goal: Optional[Goal], risk: dict) -> ExecutionPlan:
        steps = self.STEP_TEMPLATES.get(option.action, [f"execute_{option.action}", "log_outcome"])

        # Insert verification if risk is medium+
        if risk.get("risk_score", 0) > 0.3 and "request_confirmation" not in steps:
            steps = ["verify_prerequisites"] + steps

        plan = ExecutionPlan(
            goal_id    = goal.id if goal else "no_goal",
            steps      = steps,
            status     = ActionStatus.APPROVED.value,
            risk       = risk.get("risk_score", 0.0),
            confidence = option.utility
        )
        return plan


# ─── Perception Integrator ────────────────────────────────────────────────────

class PerceptionIntegrator:
    """Receives forge_temporal PerceptionEvents and translates them for PFC."""

    def ingest(self, perception_event: dict) -> dict:
        bound    = perception_event.get("bound", {}) or {}
        emotional= perception_event.get("emotional", {}) or {}
        social   = perception_event.get("social", {}) or {}
        visual   = perception_event.get("visual", {}) or {}
        auditory = perception_event.get("auditory", {}) or {}
        semantic = perception_event.get("semantic", {}) or {}

        return {
            "threat_level":   bound.get("threat_level", 0),
            "threat_label":   bound.get("threat_label", "NONE"),
            "anomaly":        perception_event.get("anomaly", False),
            "conclusion":     perception_event.get("conclusion", ""),
            "dominant_emotion": emotional.get("dominant", "neutral"),
            "social_risk":    social.get("social_risk", "LOW"),
            "inferred_intent":social.get("inferred_intent", "NEUTRAL"),
            "scene_type":     visual.get("scene_type", "UNCLASSIFIED"),
            "speech_rate":    auditory.get("speech_rate", "NORMAL"),
            "semantic_inference": semantic.get("inference", "GENERAL_CONTEXT"),
            "focus":          self._determine_focus(bound, visual, social, auditory)
        }

    def _determine_focus(self, bound, visual, social, auditory) -> str:
        threat = bound.get("threat_level", 0)
        if threat >= 4:    return "EMERGENCY_RESPONSE"
        if threat >= 3:    return "THREAT_NEUTRALIZATION"
        if threat >= 2:    return "ANOMALY_INVESTIGATION"
        if threat >= 1:    return "ELEVATED_MONITORING"
        intent = social.get("inferred_intent","")
        if "INTRUSION" in intent: return "SECURITY_RESPONSE"
        if "COERCIVE"  in intent: return "ENTITY_ASSESSMENT"
        return "ROUTINE_OPERATION"


# ─── Action Dispatcher ────────────────────────────────────────────────────────

class ActionDispatcher:
    """Fires execution plans to the appropriate FORGE modules."""

    MODULE_MAP = {
        "forge_network":   ["activate_forge_network_shield", "sever_subsystem_connections"],
        "forge_hands":     ["activate_forge_hands_lockdown", "execute_targeted_termination"],
        "forge_temporal":  ["focus_temporal_cortex", "run_semantic_pass", "run_temporal_correlation"],
        "forge_social":    ["entity_assessment", "cross_reference_baselines"],
        "forge_core":      ["broadcast_threat_level", "broadcast_emergency_signal",
                            "log_transmission", "preserve_audit_trail"],
        "self":            ["initialize_log_session", "snapshot_current_state",
                            "pause_autonomous_action", "verify_prerequisites",
                            "request_confirmation", "compose_alert_packet"]
    }

    def dispatch(self, plan: ExecutionPlan) -> list[dict]:
        dispatch_log = []
        for step in plan.steps:
            target = self._find_target(step)
            entry = {
                "step":      step,
                "target":    target,
                "status":    "DISPATCHED",
                "timestamp": datetime.now().isoformat()
            }
            dispatch_log.append(entry)
        plan.status = ActionStatus.EXECUTING.value
        return dispatch_log

    def _find_target(self, step: str) -> str:
        for module, steps in self.MODULE_MAP.items():
            if step in steps:
                return module
        return "forge_core"


# ─── Main Prefrontal Cortex ───────────────────────────────────────────────────

class ForgePrefrontalCortex:
    def __init__(self):
        self.db          = PrefrontalDB()
        self.goals       = GoalManager(self.db)
        self.risk        = RiskAssessor()
        self.impulse     = ImpulseFilter()
        self.working_mem = WorkingMemoryBuffer()
        self.decision    = DecisionEngine()
        self.planner     = ExecutivePlanner()
        self.integrator  = PerceptionIntegrator()
        self.dispatcher  = ActionDispatcher()
        self.decisions:  list[DecisionRecord] = []
        self.plans:      list[ExecutionPlan]  = []

    def process(self, perception_event: dict = None,
                raw_context: dict = None) -> dict:
        """
        Full executive cycle:
        perceive → frame → generate → assess → filter → decide → plan → dispatch
        """

        # 1. Integrate perception
        if perception_event:
            ctx = self.integrator.ingest(perception_event)
        else:
            ctx = raw_context or {"threat_level": 0, "anomaly": False, "focus": "ROUTINE_OPERATION"}

        threat = ctx.get("threat_level", 0)

        # 2. Update goals based on threat
        self.goals.prioritize_by_threat(threat)
        active_goals = self.goals.get_active()
        top_goal     = self.goals.top_goal()

        # 3. Load working memory frame
        frame = self.working_mem.new_frame(
            context=ctx,
            goals=[g.name for g in active_goals],
            threat=threat,
            focus=ctx.get("focus", "ROUTINE_OPERATION")
        )
        self.working_mem.add_reasoning(f"Threat level: {threat}. Focus: {frame.focus}")
        self.working_mem.add_reasoning(f"Top goal: {top_goal.name if top_goal else 'none'}")

        # 4. Generate options
        options = self.decision.generate_options(ctx)
        self.working_mem.add_reasoning(f"Generated {len(options)} candidate actions")

        # 5. Assess risk for each option
        risk_map = {}
        for opt in options:
            risk_map[opt.id] = self.risk.assess(opt.action, ctx)

        # 6. Impulse filter — veto dangerous options
        approved, vetoed = self.impulse.impulse_check(options, risk_map, ctx)
        self.working_mem.add_reasoning(
            f"Impulse filter: {len(approved)} approved, {len(vetoed)} vetoed"
        )

        # 7. Select best approved option
        chosen = self.decision.select_best(approved)
        if not chosen:
            chosen = Option(action="monitor_and_log",
                           rationale="Fallback — all options vetoed",
                           risk_score=0.05, reward_score=0.3,
                           feasibility=1.0, time_cost=1, utility=0.4)

        self.working_mem.add_reasoning(f"Decision: {chosen.action} (utility={chosen.utility})")

        # 8. Build execution plan
        chosen_risk = risk_map.get(chosen.id, self.risk.assess(chosen.action, ctx))
        plan = self.planner.build(chosen, top_goal, chosen_risk)
        self.plans.append(plan)
        self.db.save_plan(plan)

        # 9. Dispatch
        dispatch_log = self.dispatcher.dispatch(plan)

        # 10. Record decision
        rec = DecisionRecord(
            context   = ctx.get("focus","?"),
            options   = [o.action for o in options[:5]],
            chosen    = chosen.action,
            vetoed    = [v["action"] for v in vetoed],
            confidence= chosen.utility,
            reasoning = " → ".join([r["thought"] for r in frame.reasoning_chain])
        )
        self.decisions.append(rec)
        self.db.save_decision(rec)

        return {
            "decision":      chosen.action,
            "rationale":     chosen.rationale,
            "utility":       chosen.utility,
            "risk":          chosen_risk,
            "plan":          asdict(plan),
            "dispatch_log":  dispatch_log,
            "vetoed_count":  len(vetoed),
            "vetoed":        vetoed[:3],
            "top_goal":      top_goal.name if top_goal else "none",
            "focus":         frame.focus,
            "threat_level":  threat,
            "working_memory":self.working_mem.context_summary(),
            "reasoning":     [r["thought"] for r in frame.reasoning_chain]
        }

    def get_status(self) -> dict:
        return {
            "version":         VERSION,
            "total_decisions": len(self.decisions),
            "total_plans":     len(self.plans),
            "active_goals":    len(self.goals.get_active()),
            "working_memory":  self.working_mem.context_summary(),
            "goal_summary":    self.goals.summary(),
        }


# ─── Rich UI ──────────────────────────────────────────────────────────────────

def render_decision(result: dict):
    if not HAS_RICH:
        print(f"\n[DECISION] {result['decision']} | Threat={result['threat_level']} | Utility={result['utility']}")
        return

    threat = result["threat_level"]
    tc = {0:"green", 1:"yellow", 2:"orange3", 3:"red", 4:"bright_red"}.get(threat, "white")

    # Header
    console.print(Panel(
        Text(f"⬡ FORGE PREFRONTAL CORTEX  |  Focus: {result['focus']}  |  Threat: {threat}",
             style=f"bold {tc}"),
        border_style=tc
    ))

    # Reasoning chain
    reasoning_table = Table(box=box.SIMPLE, show_header=False, expand=True)
    reasoning_table.add_column("Step", style="dim cyan", width=4)
    reasoning_table.add_column("Thought", style="white")
    for i, thought in enumerate(result["reasoning"], 1):
        reasoning_table.add_row(f"{i}.", thought)

    # Plan steps
    plan_table = Table(box=box.SIMPLE, show_header=False, expand=True)
    plan_table.add_column("Step", style="dim", width=4)
    plan_table.add_column("Action", style="cyan")
    plan_table.add_column("Target", style="dim magenta")
    for entry in result["dispatch_log"]:
        plan_table.add_row("▶", entry["step"], entry["target"])

    # Risk panel
    risk = result["risk"]
    rc = "green" if risk["risk_score"] < 0.3 else \
         "yellow" if risk["risk_score"] < 0.6 else "red"

    risk_table = Table(box=box.SIMPLE, show_header=False, expand=True)
    risk_table.add_column("Metric", style="dim")
    risk_table.add_column("Value")
    risk_table.add_row("Risk Score",   f"[{rc}]{risk['risk_score']}[/{rc}]")
    risk_table.add_row("Risk Label",   f"[{rc}]{risk['risk_label']}[/{rc}]")
    risk_table.add_row("Irreversible", "⚠ YES" if risk["irreversible"] else "✓ NO")
    risk_table.add_row("Cascading",    "⚠ YES" if risk["cascading"]    else "✓ NO")
    risk_table.add_row("Safe",         "✓ YES" if risk["safe_to_proceed"] else "✗ NO")
    for c in risk["consequences"]:
        risk_table.add_row("→", c[:50])

    # Vetoed options
    vetoed_table = Table(box=box.SIMPLE, show_header=False, expand=True)
    vetoed_table.add_column("Action", style="dim red")
    vetoed_table.add_column("Reason", style="red")
    for v in result["vetoed"]:
        vetoed_table.add_row(v.get("action","?")[:25], v.get("veto_reason","?")[:45])
    if not result["vetoed"]:
        vetoed_table.add_row("—", "No vetoes this cycle")

    console.print(Columns([
        Panel(reasoning_table, title="[bold cyan]REASONING CHAIN[/bold cyan]",  border_style="cyan"),
        Panel(risk_table,      title="[bold yellow]RISK ASSESSMENT[/bold yellow]", border_style="yellow"),
    ]))
    console.print(Columns([
        Panel(plan_table,      title=f"[bold green]EXECUTION PLAN — {result['decision']}[/bold green]", border_style="green"),
        Panel(vetoed_table,    title="[bold red]IMPULSE FILTER — VETOED[/bold red]", border_style="red"),
    ]))

    console.print(Panel(
        Text(f"✦ DECISION: {result['decision'].upper()}\n"
             f"  Rationale: {result['rationale']}\n"
             f"  Goal: {result['top_goal']}  |  Utility: {result['utility']}  |  Confidence: {round(result['utility']*100)}%",
             style=f"bold {tc}"),
        title=f"[bold {tc}]EXECUTIVE OUTPUT[/bold {tc}]",
        border_style=tc
    ))


def run_demo():
    if HAS_RICH:
        console.print(Panel.fit(
            "[bold cyan]FORGE PREFRONTAL CORTEX[/bold cyan]\n"
            "[dim]Executive intelligence — perception to action[/dim]\n"
            f"[dim]Version {VERSION}[/dim]",
            border_style="cyan"
        ))

    pfc = ForgePrefrontalCortex()

    scenarios = [
        {
            "label": "ROUTINE — Normal operation",
            "event": {"bound": {"threat_level": 0, "threat_label": "NONE"},
                      "anomaly": False, "conclusion": "All clear",
                      "emotional": {"dominant": "neutral"},
                      "social": {"social_risk": "LOW", "inferred_intent": "NEUTRAL"},
                      "visual": {"scene_type": "INDOOR_TECHNICAL"},
                      "auditory": {"speech_rate": "NORMAL"},
                      "semantic": {"inference": "GENERAL_CONTEXT"}}
        },
        {
            "label": "ELEVATED — Suspicious entity detected",
            "event": {"bound": {"threat_level": 2, "threat_label": "MEDIUM"},
                      "anomaly": True, "conclusion": "Anomalies detected",
                      "emotional": {"dominant": "fear"},
                      "social": {"social_risk": "MEDIUM", "inferred_intent": "COERCIVE_DEMAND"},
                      "visual": {"scene_type": "LOW_VISIBILITY"},
                      "auditory": {"speech_rate": "FAST"},
                      "semantic": {"inference": "TECHNICAL_CONTEXT"}}
        },
        {
            "label": "CRITICAL — Intrusion + weapon + distress",
            "event": {"bound": {"threat_level": 4, "threat_label": "CRITICAL"},
                      "anomaly": True, "conclusion": "CRITICAL ALERT",
                      "emotional": {"dominant": "anger"},
                      "social": {"social_risk": "HIGH", "inferred_intent": "INTRUSION_ATTEMPT"},
                      "visual": {"scene_type": "UNCLASSIFIED", "threat_objects": 2},
                      "auditory": {"speech_rate": "FAST", "anomaly_detected": True},
                      "semantic": {"inference": "THREAT_SEMANTIC"}}
        },
    ]

    for scenario in scenarios:
        if HAS_RICH:
            console.print(f"\n[bold dim]━━━ {scenario['label']} ━━━[/bold dim]")
        result = pfc.process(perception_event=scenario["event"])
        render_decision(result)
        time.sleep(0.3)

    if HAS_RICH:
        status = pfc.get_status()
        st = Table(title="PREFRONTAL CORTEX STATUS", box=box.DOUBLE, border_style="cyan")
        st.add_column("Metric", style="cyan")
        st.add_column("Value")
        st.add_row("Version",         status["version"])
        st.add_row("Total Decisions", str(status["total_decisions"]))
        st.add_row("Total Plans",     str(status["total_plans"]))
        st.add_row("Active Goals",    str(status["active_goals"]))
        for g in status["goal_summary"]:
            st.add_row(f"  ↳ {g['name']}", f"priority={g['priority']} progress={g['progress']}")
        console.print(st)


# ─── HTTP API ─────────────────────────────────────────────────────────────────

def run_api(pfc: ForgePrefrontalCortex):
    if not HAS_FLASK:
        return
    app = Flask(__name__)

    @app.route("/think", methods=["POST"])
    @app.route("/process", methods=["POST"])
    def process():
        data = request.json or {}
        result = pfc.process(
            perception_event=data.get("perception_event"),
            raw_context=data.get("context")
        )
        return jsonify(result)

    @app.route("/goals", methods=["GET"])
    def goals():
        return jsonify(pfc.goals.summary())

    @app.route("/goals", methods=["POST"])
    def add_goal():
        data = request.json or {}
        g = pfc.goals.add_goal(
            name=data.get("name","unnamed"),
            description=data.get("description",""),
            priority=data.get("priority", Priority.MEDIUM.value)
        )
        return jsonify(asdict(g))

    @app.route("/decisions", methods=["GET"])
    def decisions():
        rows = pfc.db.get_decisions(20)
        return jsonify([{"id":r[0],"timestamp":r[1],"chosen":r[2],
                         "confidence":r[3],"reasoning":r[4]} for r in rows])

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify(pfc.get_status())

    app.run(host="0.0.0.0", port=API_PORT, debug=False)


# ─── Entry ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    pfc = ForgePrefrontalCortex()

    if "--api" in sys.argv:
        t = threading.Thread(target=run_api, args=(pfc,), daemon=True)
        t.start()

    run_demo()
