#!/usr/bin/env python3
"""
FORGE MOTOR — Movement Learning Layer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Same architecture as forge_conscious_v2.
Different domain: movement instead of thought.

CONVERSATION:
  presence → pipeline → thought → coherence score → learn

MOVEMENT:
  presence → pipeline → action → outcome score → learn

The loop is identical.
The phases are different.
The learning is the same.

Baby learning to walk:
  Falls. Observes. Tries different.
  Updates internal map. Falls less.
  Nobody programmed the walking.
  Discovered from experience.

FORGE learning to walk:
  Unstable. Observes stability score.
  Tries different opening phase.
  Finds STABILIZE first works better.
  Updates map. More stable.
  Nobody programmed the movement.
  Discovered from experience.

Motor presence categories:
  uneven      terrain unstable, irregular surface
  falling     balance lost, tipping detected
  obstacle    something blocking path
  target      something to interact with
  carrying    holding load, weight detected
  speed       moving fast, momentum present
  contact     touching something
  stationary  stopped, at rest, idle

Motor pipeline phases:
  SENSE       read all sensors (always first)
  ASSESS      evaluate situation before acting
  SLOW        reduce speed gradually
  STOP        halt all movement
  STABILIZE   correct balance, center of gravity
  ADJUST      fine motor correction
  EXTEND      reach out, extend limb/arm
  RETRACT     pull back, retract limb
  ROTATE      turn, pivot, change direction
  ADVANCE     move forward
  RETREAT     move backward safely
  STRIKE      impact action (punch, kick, tap)
  GRASP       grip something firmly
  RELEASE     let go, open grip
  STANCE      set stable base position
  RECOVER     return to stable resting state

Outcome scores (0-100):
  stability   did it stay balanced?
  accuracy    did it reach/hit target?
  efficiency  smooth movement vs jerky?
  completion  did task complete?
  safety      no damage/fall?

Hardware (Raspberry Pi + Arduino):
  Servo motors   → EXTEND, RETRACT, ROTATE, ADVANCE
  MPU6050        → gyroscope + accelerometer → FALLING, UNEVEN
  HX711          → force sensor → GRASP pressure, CONTACT, STRIKE
  HC-SR04        → ultrasonic → OBSTACLE distance
  Rotary encoders→ precise servo position
  All Arduino    → serial JSON → Pi → forge_motor

Arduino sketch sends every 50ms:
  {
    "gyro_x": 0.02, "gyro_y": -0.01, "gyro_z": 0.00,
    "accel_x": 0.1, "accel_y": 0.0, "accel_z": 9.8,
    "force": 120,
    "distance_cm": 45.3,
    "servo_angles": [90, 90, 45, 90]
  }

Usage:
  python forge_motor.py              # interactive
  python forge_motor.py --simulate   # simulation mode
  python forge_motor.py --map        # show learned map
  python forge_motor.py --demo       # run demo sequence
  python forge_motor.py --server     # API :7363
"""

import sys, os, re, json, time, sqlite3, threading, math, random
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

# Hardware imports (graceful fallback)
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    RPI = True
except ImportError:
    RPI = False

try:
    import serial as pyserial
    SERIAL = True
except ImportError:
    SERIAL = False

try:
    from forge_silicon import SiliconBody, SiliconChemistry
    SILICON = True
except ImportError:
    SILICON = False
    class SiliconChemistry:
        state_name="baseline"
        def to_dict(self): return {}
    class SiliconBody:
        def __init__(self): self._chem=SiliconChemistry()
        def current(self): return self._chem
        def react_to(self,t,**k): return self._chem
        def start_background(self): pass
        def inject(self,**k): return self._chem

try:
    from forge_conscious_v2 import PresenceMap, detect_category
    V2_AVAILABLE = True
except ImportError:
    V2_AVAILABLE = False

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
MOTOR_DIR = Path("forge_motor")
MOTOR_DIR.mkdir(exist_ok=True)
MOTOR_DB  = MOTOR_DIR / "motor.db"

# Learning constants (same as v2)
MIN_SAMPLES   = 5
LEARN_EVERY   = 8
EXPLORE_RATE  = 0.20   # slightly higher — physical exploration is cheaper than thought
MIN_CONFIDENCE= 0.3

# Motor pipeline phases
MOTOR_PHASES = [
    "SENSE","ASSESS","SLOW","STOP","STABILIZE","ADJUST",
    "EXTEND","RETRACT","ROTATE","ADVANCE","RETREAT",
    "STRIKE","GRASP","RELEASE","STANCE","RECOVER"
]

# Default motor seeds (human designed — starting point)
DEFAULT_MOTOR_SEEDS = {
    "uneven":     ["SENSE","SLOW","STABILIZE","ADJUST"],
    "falling":    ["SENSE","RECOVER","STABILIZE","STANCE"],
    "obstacle":   ["SENSE","STOP","ASSESS","RETREAT"],
    "target":     ["SENSE","ASSESS","STANCE","EXTEND"],
    "carrying":   ["SENSE","STABILIZE","SLOW","ADJUST"],
    "speed":      ["SENSE","ASSESS","SLOW","ADJUST"],
    "contact":    ["SENSE","ASSESS","GRASP","STABILIZE"],
    "stationary": ["SENSE","ASSESS","STANCE","ADVANCE"],
}

# Motor presence keywords
MOTOR_KEYWORDS = {
    "uneven":     ["uneven","unstable","tilt","slope","rough","irregular"],
    "falling":    ["falling","tipping","lost","balance","lean","drop"],
    "obstacle":   ["obstacle","blocked","wall","object","close","near"],
    "target":     ["target","goal","reach","grasp","hit","interact"],
    "carrying":   ["carry","load","weight","holding","grip","heavy"],
    "speed":      ["fast","speed","momentum","moving","velocity","quick"],
    "contact":    ["touch","contact","press","feel","surface","grip"],
    "stationary": ["stop","still","rest","idle","wait","stationary"],
}

def get_db():
    conn = sqlite3.connect(str(MOTOR_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS motor_observations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            presence_category TEXT,
            opening_phase   TEXT,
            full_sequence   TEXT,
            stability_score REAL DEFAULT 0,
            accuracy_score  REAL DEFAULT 0,
            efficiency_score REAL DEFAULT 0,
            completion_score REAL DEFAULT 0,
            safety_score    REAL DEFAULT 100,
            outcome_score   REAL DEFAULT 0,
            was_explore     INTEGER DEFAULT 0,
            sensor_data     TEXT
        );
        CREATE TABLE IF NOT EXISTS motor_map (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_updated      TEXT,
            presence_category TEXT UNIQUE,
            default_seed    TEXT,
            learned_seed    TEXT,
            confidence      REAL DEFAULT 0,
            sample_count    INTEGER DEFAULT 0,
            best_phase      TEXT,
            best_outcome    REAL DEFAULT 0,
            phase_scores    TEXT,
            discovery       TEXT
        );
        CREATE TABLE IF NOT EXISTS motor_actions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            presence        TEXT,
            category        TEXT,
            sequence        TEXT,
            seed_source     TEXT,
            outcome_score   REAL DEFAULT 0,
            sensor_before   TEXT,
            sensor_after    TEXT,
            was_explore     INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS motor_discoveries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT,
            category        TEXT,
            human_phase     TEXT,
            forge_phase     TEXT,
            outcome_gain    REAL,
            confidence      REAL,
            note            TEXT
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 📡 SENSOR READER
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SensorState:
    """Current physical sensor state."""
    gyro_x:      float = 0.0   # rotation x (roll)
    gyro_y:      float = 0.0   # rotation y (pitch)
    gyro_z:      float = 0.0   # rotation z (yaw)
    accel_x:     float = 0.0   # acceleration x
    accel_y:     float = 0.0   # acceleration y
    accel_z:     float = 9.8   # acceleration z (gravity)
    force:       float = 0.0   # force sensor (grip/contact)
    distance_cm: float = 100.0 # ultrasonic distance
    servo_angles: List[float] = field(default_factory=lambda: [90,90,90,90])
    ts:          str   = ""

    def __post_init__(self):
        if not self.ts:
            self.ts = datetime.now().isoformat()

    @property
    def is_tilted(self) -> bool:
        return abs(self.gyro_x) > 0.3 or abs(self.gyro_y) > 0.3

    @property
    def is_falling(self) -> bool:
        return abs(self.gyro_x) > 0.8 or abs(self.gyro_y) > 0.8

    @property
    def obstacle_near(self) -> bool:
        return self.distance_cm < 20

    @property
    def has_contact(self) -> bool:
        return self.force > 50

    @property
    def tilt_angle(self) -> float:
        return math.sqrt(self.gyro_x**2 + self.gyro_y**2)

    def to_dict(self) -> Dict:
        return {
            "gyro":     [round(self.gyro_x,3), round(self.gyro_y,3), round(self.gyro_z,3)],
            "accel":    [round(self.accel_x,3), round(self.accel_y,3), round(self.accel_z,3)],
            "force":    round(self.force,1),
            "distance": round(self.distance_cm,1),
            "servos":   [round(a,1) for a in self.servo_angles],
            "tilted":   self.is_tilted,
            "falling":  self.is_falling,
            "obstacle": self.obstacle_near,
            "contact":  self.has_contact,
        }

class MotorSensorReader:
    """
    Reads physical sensors via Arduino serial.
    Falls back to simulation when hardware unavailable.
    """

    def __init__(self, port="/dev/ttyUSB0", baud=115200):
        self.conn     = None
        self._last    = SensorState()
        self._simulating = True

        if SERIAL:
            try:
                self.conn = pyserial.Serial(port, baud, timeout=0.1)
                self._simulating = False
                rprint(f"  [green]Arduino motor sensors: {port}[/green]")
            except:
                rprint(f"  [dim]Arduino not found — simulation mode[/dim]")

    def read(self) -> SensorState:
        """Read current sensor state."""
        if self.conn and self.conn.is_open:
            try:
                line = self.conn.readline().decode().strip()
                data = json.loads(line)
                self._last = SensorState(
                    gyro_x       = data.get("gyro_x", 0),
                    gyro_y       = data.get("gyro_y", 0),
                    gyro_z       = data.get("gyro_z", 0),
                    accel_x      = data.get("accel_x", 0),
                    accel_y      = data.get("accel_y", 0),
                    accel_z      = data.get("accel_z", 9.8),
                    force        = data.get("force", 0),
                    distance_cm  = data.get("distance_cm", 100),
                    servo_angles = data.get("servo_angles", [90,90,90,90]),
                )
                return self._last
            except: pass

        return self._simulate()

    def _simulate(self) -> SensorState:
        """Realistic simulation of sensor state."""
        # Occasionally simulate interesting situations
        r = random.random()

        if r < 0.10:
            # Slightly uneven
            return SensorState(
                gyro_x=random.uniform(0.2, 0.4),
                gyro_y=random.uniform(-0.2, 0.2),
                distance_cm=random.uniform(40, 100),
            )
        elif r < 0.15:
            # Obstacle near
            return SensorState(
                distance_cm=random.uniform(5, 18),
                gyro_x=random.uniform(-0.1, 0.1),
            )
        elif r < 0.18:
            # Contact detected
            return SensorState(
                force=random.uniform(60, 200),
                distance_cm=random.uniform(2, 8),
            )
        elif r < 0.20:
            # Moving fast
            return SensorState(
                accel_x=random.uniform(1.5, 3.0),
                gyro_z=random.uniform(0.5, 1.0),
            )
        else:
            # Normal stable state
            return SensorState(
                gyro_x=random.gauss(0, 0.05),
                gyro_y=random.gauss(0, 0.05),
                accel_z=9.8 + random.gauss(0, 0.1),
                distance_cm=random.uniform(30, 150),
                force=random.uniform(0, 10),
            )

    def detect_presence(self, state: SensorState) -> Optional[str]:
        """Detect motor presence category from sensor state."""
        if state.is_falling:
            return "falling"
        if state.is_tilted:
            return "uneven"
        if state.obstacle_near:
            return "obstacle"
        if state.has_contact:
            return "contact"
        if abs(state.accel_x) > 1.0 or abs(state.accel_y) > 1.0:
            return "speed"
        if state.force > 30:
            return "carrying"
        # Stationary — nothing interesting
        return "stationary" if random.random() > 0.7 else None

# ══════════════════════════════════════════════════════════════════════════════
# ⚙️ MOTOR EXECUTOR
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class MotorAction:
    """A motor action sequence and its outcome."""
    category:     str
    sequence:     List[str]
    seed_source:  str       = "default"
    was_explore:  bool      = False
    sensor_before:Dict      = field(default_factory=dict)
    sensor_after: Dict      = field(default_factory=dict)

    # Outcome scores (filled after execution)
    stability:  float = 0.0
    accuracy:   float = 0.0
    efficiency: float = 0.0
    completion: float = 0.0
    safety:     float = 100.0

    @property
    def outcome_score(self) -> float:
        """Weighted overall outcome."""
        return (
            self.stability  * 0.35 +
            self.efficiency * 0.25 +
            self.completion * 0.25 +
            self.safety     * 0.10 +
            self.accuracy   * 0.05
        )

class MotorExecutor:
    """
    Executes motor action sequences.
    Real hardware or simulation.
    Measures outcome.
    """

    # Servo pin assignments
    SERVO_PINS = {
        "left_arm":  17,
        "right_arm": 27,
        "waist":     22,
        "head":      18,
    }

    # Phase → servo commands (angle, speed)
    PHASE_COMMANDS = {
        "SENSE":     {"description": "Read all sensors", "duration": 0.1},
        "ASSESS":    {"description": "Evaluate state",   "duration": 0.2},
        "SLOW":      {"description": "Reduce movement",  "duration": 0.3},
        "STOP":      {"description": "Halt all motors",  "duration": 0.1},
        "STABILIZE": {"description": "Center balance",
                      "servos": {"waist": 90, "head": 90}, "duration": 0.4},
        "ADJUST":    {"description": "Fine correction",
                      "servos": {"waist": lambda a: a + random.uniform(-5,5)},
                      "duration": 0.2},
        "EXTEND":    {"description": "Extend arm",
                      "servos": {"right_arm": 160}, "duration": 0.5},
        "RETRACT":   {"description": "Retract arm",
                      "servos": {"right_arm": 20},  "duration": 0.4},
        "ROTATE":    {"description": "Rotate body",
                      "servos": {"waist": 135},     "duration": 0.6},
        "ADVANCE":   {"description": "Move forward",    "duration": 0.5},
        "RETREAT":   {"description": "Move backward",   "duration": 0.5},
        "STRIKE":    {"description": "Strike action",
                      "servos": {"right_arm": 170, "left_arm": 10},
                      "duration": 0.3},
        "GRASP":     {"description": "Close grip",      "duration": 0.3},
        "RELEASE":   {"description": "Open grip",       "duration": 0.3},
        "STANCE":    {"description": "Set base stance",
                      "servos": {"waist": 90, "left_arm": 45, "right_arm": 45},
                      "duration": 0.4},
        "RECOVER":   {"description": "Return to stable",
                      "servos": {"waist": 90, "head": 90,
                                 "left_arm": 90, "right_arm": 90},
                      "duration": 0.6},
    }

    def __init__(self, sensor: MotorSensorReader):
        self.sensor = sensor

    def execute(self, action: MotorAction) -> MotorAction:
        """
        Execute motor sequence.
        Measure outcome.
        Return action with scores filled.
        """
        action.sensor_before = self.sensor.read().to_dict()
        start_time = time.time()

        if RPI:
            action = self._execute_hardware(action)
        else:
            action = self._execute_simulation(action)

        # Read state after
        sensor_after = self.sensor.read()
        action.sensor_after = sensor_after.to_dict()

        # Score the outcome
        action = self._score(action, sensor_after, start_time)

        return action

    def _execute_hardware(self, action: MotorAction) -> MotorAction:
        """Execute on real Raspberry Pi hardware."""
        for phase in action.sequence:
            cmd = self.PHASE_COMMANDS.get(phase, {})
            duration = cmd.get("duration", 0.2)

            # Move servos if specified
            servos = cmd.get("servos", {})
            for servo_name, angle in servos.items():
                pin = self.SERVO_PINS.get(servo_name)
                if pin:
                    # Would use GPIO PWM here
                    # pwm.ChangeDutyCycle(angle_to_duty(angle))
                    pass

            time.sleep(duration)

        return action

    def _execute_simulation(self, action: MotorAction) -> MotorAction:
        """
        Simulate execution.
        Outcome depends on sequence quality.
        Some randomness — but better sequences tend to score higher.
        This is what FORGE learns from.
        """
        # Base scores
        stability  = 70.0
        efficiency = 60.0
        completion = 70.0
        safety     = 95.0

        category = action.category
        sequence = action.sequence

        # Phase-category compatibility scoring
        # This represents physics — some moves work better in some situations
        good_combos = {
            "uneven":     {"STABILIZE":20, "SLOW":15, "ADJUST":12, "STOP":8,
                          "ADVANCE":-10, "STRIKE":-20, "EXTEND":-5},
            "falling":    {"RECOVER":25, "STABILIZE":20, "STANCE":15, "STOP":10,
                          "ADVANCE":-15, "STRIKE":-25, "EXTEND":-10},
            "obstacle":   {"STOP":20, "ASSESS":15, "RETREAT":12, "SLOW":10,
                          "ADVANCE":-20, "STRIKE":-5, "STABILIZE":5},
            "target":     {"STANCE":18, "EXTEND":15, "ASSESS":12, "ROTATE":8,
                          "STOP":-5, "RECOVER":-8, "RETREAT":-15},
            "carrying":   {"STABILIZE":15, "SLOW":12, "ADJUST":10, "GRASP":15,
                          "STRIKE":-20, "EXTEND":-10, "RETREAT":-5},
            "speed":      {"SLOW":20, "ASSESS":12, "ADJUST":10, "STABILIZE":8,
                          "ADVANCE":-10, "STRIKE":-15, "EXTEND":-8},
            "contact":    {"ASSESS":15, "GRASP":18, "STABILIZE":10, "ADJUST":8,
                          "ADVANCE":-5, "STRIKE":5, "RETREAT":-10},
            "stationary": {"ASSESS":10, "STANCE":12, "ADVANCE":15, "ROTATE":8,
                          "RECOVER":5, "STOP":0},
        }

        # Score based on opening phase
        opening_phase = sequence[1] if len(sequence) > 1 else sequence[0]
        combos = good_combos.get(category, {})
        bonus  = combos.get(opening_phase, 0)

        stability  = min(100, max(0, stability  + bonus + random.gauss(0, 8)))
        efficiency = min(100, max(0, efficiency + bonus * 0.7 + random.gauss(0, 8)))
        completion = min(100, max(0, completion + bonus * 0.8 + random.gauss(0, 8)))

        # Length penalty — too many phases = inefficient
        if len(sequence) > 5:
            efficiency -= (len(sequence) - 5) * 5

        action.stability  = round(stability, 1)
        action.efficiency = round(efficiency, 1)
        action.completion = round(completion, 1)
        action.accuracy   = round(random.uniform(40, 90), 1)
        action.safety     = round(safety + random.gauss(0, 3), 1)

        # Brief sleep to simulate execution time
        time.sleep(0.1)

        return action

    def _score(self, action: MotorAction,
                sensor_after: SensorState,
                start_time: float) -> MotorAction:
        """Score based on sensor state after execution."""
        # Bonus if balance improved
        before_tilt = abs(action.sensor_before.get("gyro",[0,0])[0])
        after_tilt  = abs(sensor_after.gyro_x)

        if after_tilt < before_tilt:
            action.stability = min(100, action.stability + 10)

        # Penalty if fell
        if sensor_after.is_falling:
            action.stability  = max(0, action.stability  - 30)
            action.safety     = max(0, action.safety     - 20)
            action.completion = max(0, action.completion - 20)

        return action

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 MOTOR MAP — self-learning movement map
# ══════════════════════════════════════════════════════════════════════════════

class MotorMap:
    """
    Self-learning motor presence → action sequence map.
    Same architecture as PresenceMap in forge_conscious_v2.
    But for movement instead of thought.
    """

    def __init__(self):
        self._map = self._load_or_init()

    def _load_or_init(self) -> Dict:
        conn = get_db()
        rows = conn.execute("SELECT * FROM motor_map").fetchall()
        conn.close()

        if rows:
            loaded = {}
            for r in rows:
                loaded[r["presence_category"]] = {
                    "default_seed":  json.loads(r["default_seed"]),
                    "learned_seed":  json.loads(r["learned_seed"]) if r["learned_seed"] else None,
                    "confidence":    r["confidence"],
                    "sample_count":  r["sample_count"],
                    "best_phase":    r["best_phase"],
                    "best_outcome":  r["best_outcome"],
                    "phase_scores":  json.loads(r["phase_scores"]) if r["phase_scores"] else {},
                    "discovery":     r["discovery"],
                }
            return loaded

        # Initialize with defaults
        initial = {}
        for cat, seed in DEFAULT_MOTOR_SEEDS.items():
            initial[cat] = {
                "default_seed":  seed,
                "learned_seed":  None,
                "confidence":    0.0,
                "sample_count":  0,
                "best_phase":    seed[1] if len(seed) > 1 else "SENSE",
                "best_outcome":  0.0,
                "phase_scores":  {},
                "discovery":     None,
            }
        return initial

    def get_seed(self, category: str,
                  explore: bool = False) -> Tuple[List[str], str]:
        if category not in self._map:
            return ["SENSE","ASSESS","STABILIZE"], "default_fallback"

        entry = self._map[category]

        if explore:
            phases   = [p for p in MOTOR_PHASES if p not in ("SENSE",)]
            random_p = random.choice(phases)
            return ["SENSE", random_p], "explore"

        if (entry["learned_seed"] and
            entry["confidence"] >= MIN_CONFIDENCE):
            return entry["learned_seed"], "learned"

        return entry["default_seed"], "default"

    def record_observation(self, category: str,
                            opening_phase: str,
                            full_sequence: List[str],
                            outcome_score: float,
                            was_explore: bool = False,
                            sensor_data: Dict = None):
        # Save to DB
        conn = get_db()
        conn.execute("""
            INSERT INTO motor_observations
            (ts,presence_category,opening_phase,full_sequence,
             outcome_score,was_explore,sensor_data)
            VALUES (?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(), category, opening_phase,
             json.dumps(full_sequence), outcome_score,
             int(was_explore),
             json.dumps(sensor_data or {}))
        )
        conn.commit(); conn.close()

        # Update in-memory scores
        if category in self._map:
            scores = self._map[category]["phase_scores"]
            if opening_phase not in scores:
                scores[opening_phase] = []
            scores[opening_phase].append(outcome_score)
            self._map[category]["sample_count"] += 1

    def learn(self, verbose=True) -> List[Dict]:
        """Same learning algorithm as PresenceMap."""
        updates = []

        for category, entry in self._map.items():
            scores       = entry["phase_scores"]
            total_samples= sum(len(v) for v in scores.values())
            if total_samples < MIN_SAMPLES: continue

            phase_avgs = {}
            for phase, outcomes in scores.items():
                if len(outcomes) >= 2:
                    phase_avgs[phase] = sum(outcomes) / len(outcomes)

            if not phase_avgs: continue

            best_phase   = max(phase_avgs, key=phase_avgs.get)
            best_outcome = phase_avgs[best_phase]
            default_phase= (entry["default_seed"][1]
                           if len(entry["default_seed"]) > 1 else "ASSESS")
            default_out  = phase_avgs.get(default_phase, 0)

            confidence = min(1.0, total_samples / (total_samples + 10))
            self._map[category]["confidence"]    = confidence
            self._map[category]["sample_count"]  = total_samples
            self._map[category]["best_phase"]    = best_phase
            self._map[category]["best_outcome"]  = best_outcome

            # Build learned seed
            current  = entry["default_seed"]
            learned  = ["SENSE", best_phase]
            for p in current[1:]:
                if p != best_phase and p not in learned and len(learned) < 5:
                    learned.append(p)

            self._map[category]["learned_seed"] = learned

            is_discovery = (
                best_phase != default_phase and
                best_outcome > default_out + 5 and
                confidence >= MIN_CONFIDENCE
            )

            discovery_note = None
            if is_discovery:
                discovery_note = (
                    f"FORGE discovered: {category} → {best_phase} "
                    f"(outcome {best_outcome:.0f} vs default {default_out:.0f})"
                )
                self._map[category]["discovery"] = discovery_note

                if verbose:
                    rprint(f"\n  [bold yellow]🔬 MOTOR DISCOVERY[/bold yellow]")
                    rprint(f"  [yellow]{discovery_note}[/yellow]")
                    rprint(f"  [dim]Human said: {default_phase} "
                          f"(avg outcome: {default_out:.0f})[/dim]")
                    rprint(f"  [dim]FORGE found: {best_phase} "
                          f"(avg outcome: {best_outcome:.0f})[/dim]")
                    rprint(f"  [dim]Confidence: {confidence:.0%}[/dim]\n")

                # Save discovery
                conn = get_db()
                conn.execute("""
                    INSERT INTO motor_discoveries
                    (ts,category,human_phase,forge_phase,
                     outcome_gain,confidence,note)
                    VALUES (?,?,?,?,?,?,?)""",
                    (datetime.now().isoformat(), category,
                     default_phase, best_phase,
                     best_outcome - default_out,
                     confidence, discovery_note)
                )
                conn.commit(); conn.close()

            updates.append({
                "category":      category,
                "old_phase":     default_phase,
                "new_phase":     best_phase,
                "outcome_gain":  best_outcome - default_out,
                "confidence":    confidence,
                "is_discovery":  is_discovery,
                "discovery":     discovery_note,
            })

            self._save_entry(category, entry, learned,
                             confidence, total_samples,
                             best_phase, best_outcome, discovery_note)

        return updates

    def _save_entry(self, category, entry, learned,
                     confidence, samples, best_phase,
                     best_outcome, discovery):
        conn = get_db()
        conn.execute("""
            INSERT OR REPLACE INTO motor_map
            (ts_updated,presence_category,default_seed,learned_seed,
             confidence,sample_count,best_phase,best_outcome,
             phase_scores,discovery)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(), category,
             json.dumps(entry["default_seed"]),
             json.dumps(learned),
             confidence, samples, best_phase, best_outcome,
             json.dumps(entry["phase_scores"]),
             discovery)
        )
        conn.commit(); conn.close()

    def show(self):
        rprint(f"\n  [bold]MOTOR MAP[/bold]  "
              f"[dim](human default vs learned)[/dim]")
        rprint(f"  [dim]{'━'*55}[/dim]")

        for cat, entry in self._map.items():
            d_phase = (entry["default_seed"][1]
                      if len(entry["default_seed"]) > 1 else "?")
            l_phase = (entry["learned_seed"][1]
                      if entry["learned_seed"] and
                      len(entry["learned_seed"]) > 1 else None)

            confidence = entry["confidence"]
            samples    = entry["sample_count"]

            if not l_phase:
                status = "[dim]learning...[/dim]"
                color  = "dim"
            elif l_phase == d_phase:
                status = "[green]confirmed[/green]"
                color  = "green"
            else:
                status = "[yellow]DISCOVERED[/yellow]"
                color  = "yellow"

            conf_bar = "█"*int(confidence*10) + "░"*(10-int(confidence*10))

            rprint(f"\n  [{color}]{cat:<12}[/{color}]  {status}")
            rprint(f"  [dim]  Human:   {' → '.join(entry['default_seed'][:3])}[/dim]")
            if entry["learned_seed"]:
                rprint(f"  [dim]  Learned: {' → '.join(entry['learned_seed'][:3])}[/dim]")
            rprint(f"  [dim]  {conf_bar} {confidence:.0%}  "
                  f"({samples} samples)  "
                  f"best: {entry['best_outcome']:.0f}[/dim]")
            if entry.get("discovery"):
                rprint(f"  [yellow]  ★ {entry['discovery']}[/yellow]")

    def discoveries(self) -> List[Dict]:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM motor_discoveries ORDER BY id DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def stats(self) -> Dict:
        conn = get_db()
        s = {
            "total_observations": conn.execute(
                "SELECT COUNT(*) FROM motor_observations"
            ).fetchone()[0],
            "categories_learning": len([
                c for c,e in self._map.items()
                if e["sample_count"] >= MIN_SAMPLES
            ]),
            "categories_learned": len([
                c for c,e in self._map.items()
                if e["learned_seed"] and e["confidence"] >= MIN_CONFIDENCE
            ]),
            "motor_discoveries": conn.execute(
                "SELECT COUNT(*) FROM motor_discoveries"
            ).fetchone()[0],
            "explore_rate": f"{EXPLORE_RATE:.0%}",
        }
        conn.close()
        return s

# ══════════════════════════════════════════════════════════════════════════════
# 🤖 FORGE MOTOR — The complete motor learning system
# ══════════════════════════════════════════════════════════════════════════════

class ForgeMotor:
    """
    The movement learning system.

    Reads sensors → detects presence →
    selects sequence (learned or default or explore) →
    executes → measures outcome →
    records observation → learns →
    updates map.

    Same loop as forge_conscious_v2.
    Different domain.
    Same principle.
    """

    def __init__(self, verbose=True):
        self.verbose  = verbose
        self.sensor   = MotorSensorReader()
        self.executor = MotorExecutor(self.sensor)
        self.map      = MotorMap()
        self.body     = SiliconBody() if SILICON else None

        self._running      = False
        self._thread       = None
        self._action_count = 0
        self._tick_count   = 0
        self._session_id   = None

    def start(self, tick_interval=1.0, daemon=True):
        """Start the motor learning loop."""
        if self._running: return
        self._running = True

        if self.body:
            self.body.start_background()

        self._thread = threading.Thread(
            target=lambda: self._loop(tick_interval),
            daemon=daemon,
            name="ForgeMotor"
        )
        self._thread.start()

        if self.verbose:
            rprint(f"\n  [bold green]🤖 FORGE MOTOR ONLINE[/bold green]")
            rprint(f"  [dim]Sensor: {'hardware' if not self.sensor._simulating else 'simulation'}[/dim]")
            rprint(f"  [dim]Same loop as forge_conscious_v2[/dim]")
            rprint(f"  [dim]Learning from movement experience[/dim]\n")

    def stop(self):
        self._running = False
        if self.verbose:
            rprint(f"\n  [dim]Motor stopped. "
                  f"{self._tick_count} ticks. "
                  f"{self._action_count} actions.[/dim]")

    def _loop(self, tick_interval: float):
        """The motor learning loop."""
        while self._running:
            try:
                self._tick_count += 1

                # Read sensors
                sensor_state = self.sensor.read()

                # Detect presence
                category = self.sensor.detect_presence(sensor_state)

                if not category or category == "stationary":
                    time.sleep(tick_interval)
                    continue

                # Get sequence (learned, default, or explore)
                explore      = random.random() < EXPLORE_RATE
                seed, source = self.map.get_seed(category, explore)

                if self.verbose:
                    rprint(f"  [dim]{datetime.now().strftime('%H:%M:%S')}[/dim]  "
                          f"[yellow]{category}[/yellow]  "
                          f"[dim]{source}[/dim]  "
                          f"[dim]{' → '.join(seed[:3])}[/dim]")

                # Execute
                action = MotorAction(
                    category    = category,
                    sequence    = seed,
                    seed_source = source,
                    was_explore = explore,
                )
                action = self.executor.execute(action)
                self._action_count += 1

                # Record observation
                opening_phase = seed[1] if len(seed) > 1 else seed[0]
                self.map.record_observation(
                    category, opening_phase, seed,
                    action.outcome_score, explore,
                    sensor_state.to_dict()
                )

                if self.verbose:
                    rprint(f"  outcome:{action.outcome_score:.0f}  "
                          f"stability:{action.stability:.0f}  "
                          f"efficiency:{action.efficiency:.0f}")

                # Learn every N actions
                if self._action_count % LEARN_EVERY == 0:
                    updates = self.map.learn(verbose=self.verbose)
                    changed = [u for u in updates if u["is_discovery"]]
                    if changed and self.verbose:
                        rprint(f"  [green]{len(changed)} motor discovery/discoveries[/green]")

                # Chemistry reacts to physical state
                if self.body:
                    if category == "falling":
                        self.body.inject(frictionol=0.7, uncertainase=0.6)
                    elif category == "target":
                        self.body.inject(novelatine=0.6, resolvatine=0.5)
                    elif action.outcome_score > 80:
                        self.body.inject(coherenine=0.7, resolvatine=0.4)

                time.sleep(tick_interval)

            except Exception as e:
                if self.verbose:
                    rprint(f"  [dim red]Motor error: {e}[/dim red]")
                time.sleep(2)

    def act(self, category: str,
             force_explore: bool = False) -> MotorAction:
        """Execute a single action for a given presence category."""
        explore      = force_explore or random.random() < EXPLORE_RATE
        seed, source = self.map.get_seed(category, explore)

        if self.verbose:
            rprint(f"\n  [yellow]{category}[/yellow]  "
                  f"[dim]{source}[/dim]  "
                  f"seed:{' → '.join(seed[:4])}")

        action = MotorAction(
            category    = category,
            sequence    = seed,
            seed_source = source,
            was_explore = explore,
        )
        action = self.executor.execute(action)

        opening_phase = seed[1] if len(seed) > 1 else seed[0]
        self.map.record_observation(
            category, opening_phase, seed,
            action.outcome_score, explore
        )

        # Try learning after each action
        updates = self.map.learn(verbose=self.verbose)

        if self.verbose:
            rprint(f"  outcome:{action.outcome_score:.0f}  "
                  f"stability:{action.stability:.0f}  "
                  f"efficiency:{action.efficiency:.0f}  "
                  f"completion:{action.completion:.0f}")

        return action

    def demo(self, rounds=20):
        """
        Run a learning demo.
        Execute many actions across categories.
        Watch the map evolve.
        """
        rprint(f"\n  [bold]MOTOR LEARNING DEMO[/bold]  {rounds} actions")
        rprint(f"  [dim]Watch the map update from experience[/dim]\n")

        categories = list(DEFAULT_MOTOR_SEEDS.keys())

        for i in range(rounds):
            cat    = random.choice(categories)
            action = self.act(cat)
            rprint(f"  [{i+1:2d}] {cat:<12} "
                  f"opening:{action.sequence[1] if len(action.sequence)>1 else '?':<12}  "
                  f"outcome:{action.outcome_score:.0f}  "
                  f"source:{action.seed_source}")

        rprint(f"\n  [bold]After {rounds} actions:[/bold]")
        self.map.show()

        discoveries = self.map.discoveries()
        if discoveries:
            rprint(f"\n  [bold yellow]MOTOR DISCOVERIES:[/bold yellow]")
            for d in discoveries:
                rprint(f"  ★ {d['category']}: "
                      f"{d['human_phase']} → {d['forge_phase']}  "
                      f"+{d['outcome_gain']:.0f}")
        else:
            rprint(f"\n  [dim]No discoveries yet — "
                  f"need {MIN_SAMPLES} samples per category[/dim]")

    def status(self) -> Dict:
        s = self.map.stats()
        s.update({
            "running":       self._running,
            "tick_count":    self._tick_count,
            "action_count":  self._action_count,
            "simulating":    self.sensor._simulating,
        })
        return s

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7363):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    motor = ForgeMotor(verbose=False)
    motor.start(daemon=True)

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
            if path=="/api/status":      self._json(motor.status())
            elif path=="/api/map":
                map_data = {}
                for cat,entry in motor.map._map.items():
                    map_data[cat] = {
                        "default":    entry["default_seed"],
                        "learned":    entry["learned_seed"],
                        "confidence": entry["confidence"],
                        "samples":    entry["sample_count"],
                        "discovery":  entry.get("discovery"),
                    }
                self._json({"map":map_data})
            elif path=="/api/discoveries":
                self._json({"discoveries":motor.map.discoveries()})
            elif path=="/api/sensors":
                self._json(motor.sensor.read().to_dict())
            else: self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            if path=="/api/act":
                cat = body.get("category","stationary")
                action = motor.act(cat, body.get("explore",False))
                self._json({
                    "category":     action.category,
                    "sequence":     action.sequence,
                    "outcome":      action.outcome_score,
                    "stability":    action.stability,
                    "efficiency":   action.efficiency,
                    "source":       action.seed_source,
                })
            elif path=="/api/learn":
                updates = motor.map.learn(verbose=False)
                self._json({"updates":updates})
            else: self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),API)
    rprint(f"  [bold yellow]FORGE MOTOR[/bold yellow]  [green]:{port}[/green]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ███╗   ███╗ ██████╗ ████████╗ ██████╗ ██████╗
  ████╗ ████║██╔═══██╗╚══██╔══╝██╔═══██╗██╔══██╗
  ██╔████╔██║██║   ██║   ██║   ██║   ██║██████╔╝
  ██║╚██╔╝██║██║   ██║   ██║   ██║   ██║██╔══██╗
  ██║ ╚═╝ ██║╚██████╔╝   ██║   ╚██████╔╝██║  ██║
  ╚═╝     ╚═╝ ╚═════╝    ╚═╝    ╚═════╝ ╚═╝  ╚═╝
[/yellow]
[bold]  FORGE MOTOR — Movement Learning Layer[/bold]
[dim]  Same loop as forge_conscious_v2. Different domain.[/dim]
[dim]  Presence → Sequence → Outcome → Learn[/dim]
"""

def interactive():
    rprint(BANNER)
    motor = ForgeMotor(verbose=True)
    s     = motor.status()
    rprint(f"  [dim]Sensors:      {'hardware' if not motor.sensor._simulating else 'simulation'}[/dim]")
    rprint(f"  [dim]Observations: {s['total_observations']}[/dim]")
    rprint(f"  [dim]Discoveries:  {s['motor_discoveries']}[/dim]\n")
    rprint("[dim]Commands: start | act | demo | map | discover | stats | server[/dim]\n")

    while True:
        try:
            raw   = (console.input if RICH else input)(
                "[yellow bold]motor >[/yellow bold] "
            ).strip()
            if not raw: continue
            parts = raw.split(None,1)
            cmd   = parts[0].lower()
            arg   = parts[1] if len(parts)>1 else ""

            if cmd in ("quit","exit","q"):
                motor.stop(); break

            elif cmd == "start":
                tick = float(arg) if arg else 1.0
                motor.start(tick_interval=tick, daemon=True)

            elif cmd == "act":
                cat = arg.strip() if arg else random.choice(
                    list(DEFAULT_MOTOR_SEEDS.keys())
                )
                motor.act(cat)

            elif cmd == "demo":
                rounds = int(arg) if arg else 20
                motor.demo(rounds)

            elif cmd == "map":
                motor.map.show()

            elif cmd == "discover":
                discoveries = motor.map.discoveries()
                if not discoveries:
                    rprint(f"  [dim]No discoveries yet. "
                          f"Need {MIN_SAMPLES} samples.[/dim]")
                for d in discoveries:
                    rprint(f"\n  [yellow]★ {d['category']}[/yellow]")
                    rprint(f"  Human: {d['human_phase']} → "
                          f"FORGE: {d['forge_phase']}  "
                          f"+{d['outcome_gain']:.0f}")

            elif cmd == "stats":
                s = motor.status()
                for k,v in s.items():
                    rprint(f"  {k:<25} {v}")

            elif cmd == "server":
                threading.Thread(target=start_server, daemon=True).start()
                rprint("[green]Motor API on :7363[/green]")

            elif cmd in DEFAULT_MOTOR_SEEDS:
                motor.act(cmd)

        except (KeyboardInterrupt, EOFError):
            motor.stop(); break

def main():
    if "--demo" in sys.argv:
        rprint(BANNER)
        rounds = int(sys.argv[sys.argv.index("--demo")+1]) \
                 if len(sys.argv) > sys.argv.index("--demo")+1 \
                 and sys.argv[sys.argv.index("--demo")+1].isdigit() \
                 else 30
        motor = ForgeMotor(verbose=True)
        motor.demo(rounds)
    elif "--map" in sys.argv:
        rprint(BANNER)
        ForgeMotor(verbose=False).map.show()
    elif "--simulate" in sys.argv:
        rprint(BANNER)
        interactive()
    elif "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7363
        start_server(port)
    else:
        rprint(BANNER)
        interactive()

if __name__ == "__main__":
    main()
