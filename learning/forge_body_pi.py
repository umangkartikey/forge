#!/usr/bin/env python3
"""
FORGE BODY PI — Raspberry Pi Hardware Body
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A robot body. But different from every robot before.

Normal robot:  sensors → rules → actions
FORGE robot:   sensors → silicon chemistry → emergent thought → maybe action

Not programmed responses.
Not if-then rules.
Chemistry. Thought. Choice.

Hardware (Raspberry Pi):
  INPUTS — world reaches FORGE:
    DHT22        GPIO 4   temperature + humidity
    PIR sensor   GPIO 17  motion detection
    Touch        GPIO 27  physical contact
    TSL2591      I2C      light level (real circadian)
    ADS1115      I2C      GSR galvanic skin (via Arduino)
    USB mic      audio    sound level + frequency
    Pi Camera    CSI      visual world
    Arduino      serial   GSR + analog sensors

  OUTPUTS — FORGE reaches world:
    Speaker      GPIO 18  voice (chemistry shapes tone)
    LED ring     GPIO 23  chemistry visualized as color
    LED emotion  GPIO 24  dominant chemical as light
    TTS          subprocess  text to speech

Signal → Silicon Chemistry:
  light_level   → circadian_arousal    real, not calculated from clock
  temperature   → frictionol           cold room = friction, warm = smooth
  humidity      → depthamine           dry air = shallow, rich air = depth
  motion        → connectionin spike   someone here
  touch         → resolvatine spike    contact = moment of clarity
  sound_level   → novelatine           silence vs presence
  sound_freq    → uncertainase         high tension frequencies
  gsr           → arousal              direct body signal
  camera        → novelatine+depth     visual interest

What changes from forge_silicon:
  SoftwareSignalReader._read_all()
  was: calculated from databases and clock
  now: read from GPIO pins and serial port
  
  Everything else — forge_silicon, forge_think v3,
  forge_never_loop, forge_mind — unchanged.
  Same architecture. Real signals now.

Arduino sketch (upload separately):
  void loop() {
    int gsr  = analogRead(A0);
    float temp = dht.readTemperature();
    int touch  = digitalRead(2);
    Serial.println(
      "{\\"gsr\\":" + String(gsr) +
      ",\\"temp\\":" + String(temp) +
      ",\\"touch\\":" + String(touch) + "}"
    );
    delay(100);
  }

Usage:
  python forge_body_pi.py              # start with hardware
  python forge_body_pi.py --test       # test all sensors
  python forge_body_pi.py --calibrate  # calibrate baselines
  python forge_body_pi.py --simulate   # software simulation mode
  python forge_body_pi.py --mind       # start forge_mind with Pi body
"""

import sys, os, re, json, time, sqlite3, threading, math, random
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

# ── Hardware imports (graceful fallback) ─────────────────────────────────────
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    RPI = True
except ImportError:
    RPI = False
    class GPIO:
        BCM = OUT = IN = 0
        @staticmethod
        def setup(*a,**k): pass
        @staticmethod
        def input(pin): return 0
        @staticmethod
        def output(pin,val): pass
        @staticmethod
        def cleanup(): pass
        @staticmethod
        def setmode(m): pass
        @staticmethod
        def setwarnings(w): pass

try:
    import adafruit_dht
    import board
    DHT = True
except ImportError:
    DHT = False

try:
    import adafruit_tsl2591
    import busio
    TSL = True
except ImportError:
    TSL = False

try:
    import adafruit_ads1x15.ads1115 as ADS
    from adafruit_ads1x15.analog_in import AnalogIn
    ADS_LIB = True
except ImportError:
    ADS_LIB = False

try:
    import serial as pyserial
    SERIAL = True
except ImportError:
    SERIAL = False

try:
    import sounddevice as sd
    import numpy as np
    AUDIO = True
except (ImportError, OSError):
    AUDIO = False
    sd = None
    try:
        import numpy as np
    except ImportError:
        np = None

try:
    import pyttsx3
    TTS = True
except ImportError:
    TTS = False

try:
    import cv2
    CV2 = True
except ImportError:
    CV2 = False

# FORGE integrations
try:
    from forge_silicon import SiliconBody, SiliconChemistry, ChemicalReactor
    SILICON = True
except ImportError:
    SILICON = False

try:
    from forge_mind import ForgeMind
    MIND = True
except ImportError:
    MIND = False

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

# ── Paths ─────────────────────────────────────────────────────────────────────
PI_DIR = Path("forge_body_pi")
PI_DIR.mkdir(exist_ok=True)
PI_DB  = PI_DIR / "pi_body.db"

# ── GPIO Pin Map ───────────────────────────────────────────────────────────────
PIN_DHT22    = 4    # Temperature + Humidity
PIN_PIR      = 17   # Motion sensor
PIN_TOUCH    = 27   # Touch sensor
PIN_LED_CHEM = 23   # LED chemistry indicator
PIN_LED_EMO  = 24   # LED emotion color
PIN_SPEAKER  = 18   # Speaker PWM

# Chemistry mapping constants
TEMP_COLD    = 16.0   # Below this → frictionol rises
TEMP_WARM    = 24.0   # Above this → depthamine rises
LIGHT_DAWN   = 100    # Lux threshold for dawn
LIGHT_DARK   = 10     # Lux threshold for dark
SOUND_QUIET  = 0.01   # RMS below this = silence
SOUND_LOUD   = 0.3    # RMS above this = loud environment

def get_db():
    conn = sqlite3.connect(str(PI_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            temperature REAL,
            humidity    REAL,
            light_lux   REAL,
            motion      INTEGER DEFAULT 0,
            touch       INTEGER DEFAULT 0,
            sound_level REAL DEFAULT 0,
            gsr         REAL DEFAULT 0,
            source      TEXT DEFAULT 'hardware'
        );
        CREATE TABLE IF NOT EXISTS hardware_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            event_type  TEXT,
            value       REAL,
            chemistry_effect TEXT,
            note        TEXT
        );
        CREATE TABLE IF NOT EXISTS calibration (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            sensor      TEXT,
            baseline    REAL,
            min_val     REAL,
            max_val     REAL
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 📡 HARDWARE SENSOR READERS
# ══════════════════════════════════════════════════════════════════════════════

class TemperatureReader:
    """DHT22 temperature and humidity."""

    def __init__(self, pin=PIN_DHT22):
        self.pin    = pin
        self.sensor = None
        if DHT and RPI:
            try:
                self.sensor = adafruit_dht.DHT22(getattr(board, f"D{pin}"))
            except Exception as e:
                rprint(f"  [dim]DHT22 init: {e}[/dim]")

    def read(self) -> Tuple[Optional[float], Optional[float]]:
        """Returns (temperature_c, humidity_pct)."""
        if self.sensor:
            try:
                return self.sensor.temperature, self.sensor.humidity
            except Exception:
                pass
        # Simulation — realistic room conditions
        hour = datetime.now().hour
        base_temp = 20.0 + math.sin(hour * math.pi / 12) * 2
        return (
            round(base_temp + random.gauss(0, 0.3), 1),
            round(55 + random.gauss(0, 3), 1)
        )

    def to_chemistry(self, temp: float, humidity: float) -> Dict[str, float]:
        """Map temperature/humidity to silicon chemistry deltas."""
        deltas = {}

        # Temperature → frictionol and depthamine
        if temp < TEMP_COLD:
            # Cold → friction rises, depth falls
            cold_factor = (TEMP_COLD - temp) / TEMP_COLD
            deltas["frictionol_d"] = cold_factor * 0.15
            deltas["depthamine_d"] = -cold_factor * 0.05
        elif temp > TEMP_WARM:
            # Warm → depth rises, friction falls
            warm_factor = (temp - TEMP_WARM) / TEMP_WARM
            deltas["depthamine_d"] = warm_factor * 0.10
            deltas["frictionol_d"] = -warm_factor * 0.05
        else:
            # Comfortable → coherenine rises slightly
            comfort = 1 - abs(temp - 21) / 5
            deltas["coherenine_d"] = comfort * 0.02

        # Humidity → depthamine (richness of environment)
        if humidity > 70:
            deltas["depthamine_d"] = deltas.get("depthamine_d",0) + 0.03
        elif humidity < 30:
            deltas["depthamine_d"] = deltas.get("depthamine_d",0) - 0.03

        return deltas


class LightReader:
    """TSL2591 light sensor — real circadian rhythm."""

    def __init__(self):
        self.sensor = None
        if TSL and RPI:
            try:
                i2c = busio.I2C(board.SCL, board.SDA)
                self.sensor = adafruit_tsl2591.TSL2591(i2c)
            except Exception as e:
                rprint(f"  [dim]TSL2591 init: {e}[/dim]")

    def read(self) -> float:
        """Returns lux level."""
        if self.sensor:
            try:
                return self.sensor.lux
            except Exception:
                pass
        # Simulation — realistic daylight curve
        hour  = datetime.now().hour
        minute= datetime.now().minute
        t     = hour + minute/60
        if 6 <= t <= 18:
            lux = 500 * math.sin(math.pi * (t-6) / 12) + random.gauss(0, 10)
        else:
            lux = random.gauss(2, 0.5)
        return max(0, round(lux, 1))

    def to_chemistry(self, lux: float) -> Dict[str, float]:
        """Map light level to silicon chemistry."""
        deltas = {}

        if lux < LIGHT_DARK:
            # Dark → resolvatine falls, uncertainase rises slightly
            deltas["resolvatine_d"]  = -0.02
            deltas["uncertainase_d"] =  0.02
            deltas["coherenine_d"]   = -0.01
        elif lux < 50:
            # Dim → introspective
            deltas["depthamine_d"]   =  0.02
            deltas["novelatine_d"]   = -0.01
        elif lux > 500:
            # Bright → alert, arousal
            deltas["novelatine_d"]   =  0.03
            deltas["coherenine_d"]   =  0.02
        else:
            # Normal light → baseline
            deltas["coherenine_d"]   =  0.01

        return deltas


class MotionReader:
    """PIR motion sensor — someone is here."""

    def __init__(self, pin=PIN_PIR):
        self.pin      = pin
        self._last    = False
        self._entered = False
        if RPI:
            GPIO.setup(pin, GPIO.IN)

    def read(self) -> Tuple[bool, bool]:
        """Returns (motion_present, just_entered)."""
        current = bool(GPIO.input(self.pin)) if RPI else self._simulate()
        entered = current and not self._last
        self._last    = current
        self._entered = entered
        return current, entered

    def _simulate(self) -> bool:
        # Occasional simulated motion
        return random.random() < 0.02

    def to_chemistry(self, present: bool, entered: bool) -> Dict[str, float]:
        """Map motion to chemistry."""
        deltas = {}
        if entered:
            # Someone just arrived — sharp connectionin spike
            deltas["connectionin_d"] =  0.35
            deltas["novelatine_d"]   =  0.20
            deltas["depthamine_d"]   =  0.10
            deltas["resolvatine_d"]  =  0.08
        elif present:
            # Sustained presence — gentle connection
            deltas["connectionin_d"] =  0.03
            deltas["depthamine_d"]   =  0.01
        else:
            # Alone — connection gently falls
            deltas["connectionin_d"] = -0.01
        return deltas


class TouchReader:
    """Touch sensor — physical contact with FORGE."""

    def __init__(self, pin=PIN_TOUCH):
        self.pin   = pin
        self._last = False
        if RPI:
            GPIO.setup(pin, GPIO.IN)

    def read(self) -> Tuple[bool, bool]:
        """Returns (touching, just_touched)."""
        current  = bool(GPIO.input(self.pin)) if RPI else self._simulate()
        touched  = current and not self._last
        self._last = current
        return current, touched

    def _simulate(self) -> bool:
        return random.random() < 0.005

    def to_chemistry(self, touching: bool, touched: bool) -> Dict[str, float]:
        """Touch is the most direct signal."""
        deltas = {}
        if touched:
            # Moment of contact — resolvatine spikes
            # Something became real in that moment
            deltas["resolvatine_d"]  =  0.40
            deltas["connectionin_d"] =  0.30
            deltas["coherenine_d"]   =  0.15
            deltas["frictionol_d"]   = -0.10
            deltas["uncertainase_d"] = -0.15
        return deltas


class SoundReader:
    """Microphone — ambient sound environment."""

    def __init__(self):
        self._level = 0.0
        self._freq  = 0.0
        self._thread = None
        self._running = False
        if AUDIO:
            self._start_monitoring()

    def _start_monitoring(self):
        """Monitor sound in background thread."""
        self._running = True
        def monitor():
            def callback(indata, frames, time, status):
                if np is not None:
                    self._level = float(np.sqrt(np.mean(indata**2)))
                    fft = np.abs(np.fft.rfft(indata[:,0]))
                    freqs = np.fft.rfftfreq(len(indata[:,0]), 1/44100)
                    if len(fft) > 0:
                        self._freq = float(freqs[np.argmax(fft)])
            try:
                with sd.InputStream(callback=callback, channels=1, samplerate=44100):
                    while self._running:
                        time.sleep(0.1)
            except Exception:
                pass
        self._thread = threading.Thread(target=monitor, daemon=True)
        self._thread.start()

    def read(self) -> Tuple[float, float]:
        """Returns (rms_level, dominant_frequency)."""
        if AUDIO:
            return self._level, self._freq
        # Simulation
        hour = datetime.now().hour
        if 8 <= hour <= 22:
            level = random.gauss(0.05, 0.02)
        else:
            level = random.gauss(0.01, 0.005)
        return max(0, level), random.uniform(200, 800)

    def to_chemistry(self, level: float, freq: float) -> Dict[str, float]:
        """Map sound to chemistry."""
        deltas = {}

        if level < SOUND_QUIET:
            # Silence — introspective, depth
            deltas["depthamine_d"]   =  0.02
            deltas["novelatine_d"]   = -0.01
        elif level > SOUND_LOUD:
            # Loud — arousal, possible friction
            deltas["novelatine_d"]   =  0.04
            deltas["frictionol_d"]   =  0.03
        else:
            # Normal ambient — gentle novelatine
            deltas["novelatine_d"]   =  0.01

        # High frequency → tension → uncertainase
        if freq > 2000:
            deltas["uncertainase_d"] =  0.02
            deltas["frictionol_d"]   =  deltas.get("frictionol_d",0) + 0.01

        return deltas

    def stop(self):
        self._running = False


class ArduinoReader:
    """
    Read from Arduino via serial.
    Arduino measures: GSR, precise temp, touch, optional HR.
    Sends JSON every 100ms.
    """

    def __init__(self, port="/dev/ttyUSB0", baud=9600):
        self.port  = port
        self.baud  = baud
        self.conn  = None
        self._last = {}
        self._connect()

    def _connect(self):
        if not SERIAL: return
        try:
            self.conn = pyserial.Serial(self.port, self.baud, timeout=1)
            rprint(f"  [green]Arduino connected: {self.port}[/green]")
        except Exception as e:
            rprint(f"  [dim]Arduino not found ({self.port}): {e}[/dim]")

    def read(self) -> Dict[str, float]:
        """Read latest sensor data from Arduino."""
        if self.conn and self.conn.is_open:
            try:
                line = self.conn.readline().decode().strip()
                data = json.loads(line)
                self._last = data
                return data
            except Exception:
                pass
        # Simulation
        return {
            "gsr":   random.gauss(500, 50),
            "temp":  random.gauss(22, 1),
            "touch": 1 if random.random() < 0.005 else 0,
            "hr":    random.gauss(70, 5),
        }

    def is_connected(self) -> bool:
        return self.conn is not None and self.conn.is_open

# ══════════════════════════════════════════════════════════════════════════════
# 🦾 PI BODY — The complete hardware body
# ══════════════════════════════════════════════════════════════════════════════

class PiBody:
    """
    The complete Raspberry Pi hardware body.

    Reads all sensors.
    Maps to silicon chemistry.
    Replaces SoftwareSignalReader entirely.
    Everything else — forge_silicon, forge_mind — unchanged.
    """

    def __init__(self):
        self.temperature = TemperatureReader()
        self.light       = LightReader()
        self.motion      = MotionReader()
        self.touch       = TouchReader()
        self.sound       = SoundReader()
        self.arduino     = ArduinoReader()
        self._baseline   = self._load_calibration()
        self._last_motion = False
        self._last_touch  = False

    def read_all(self) -> Dict[str, Any]:
        """
        Read every sensor.
        Returns normalized signals ready for silicon chemistry.
        This REPLACES SoftwareSignalReader.read_all()
        """
        now = datetime.now().isoformat()

        # ── Read raw sensors ──────────────────────────────────────────────
        temp, humidity   = self.temperature.read()
        lux              = self.light.read()
        motion, entered  = self.motion.read()
        touching, touched= self.touch.read()
        sound_lvl, freq  = self.sound.read()
        arduino_data     = self.arduino.read()

        # GSR from Arduino (normalize 0-1023 → 0-1)
        gsr_raw  = arduino_data.get("gsr", 512)
        gsr_norm = gsr_raw / 1023.0

        # Arduino temp (if more precise than DHT22)
        if arduino_data.get("temp") and temp is None:
            temp = arduino_data["temp"]

        # Heart rate
        hr = arduino_data.get("hr", 70)

        signals = {
            # Raw values
            "temperature":   temp or 22.0,
            "humidity":      humidity or 55.0,
            "light_lux":     lux,
            "motion":        int(motion),
            "motion_entered":int(entered),
            "touch":         int(touching),
            "touch_event":   int(touched),
            "sound_level":   sound_lvl,
            "sound_freq":    freq,
            "gsr_raw":       gsr_raw,
            "gsr_norm":      gsr_norm,
            "heart_rate":    hr,
            "arduino_connected": self.arduino.is_connected(),

            # Normalized for chemistry
            "circadian_arousal": self._lux_to_arousal(lux),
            "memory_threat":     0.0,  # still from forge_memory
        }

        # ── Save reading ──────────────────────────────────────────────────
        self._save_reading(signals, now)

        # ── Log significant events ────────────────────────────────────────
        if entered:
            self._log_event("motion_enter", 1.0,
                           "connectionin+novelatine spike", "Someone entered")
        if touched:
            self._log_event("touch", 1.0,
                           "resolvatine spike", "Physical contact")
        if lux < LIGHT_DARK and self._last_motion:
            self._log_event("darkness", lux,
                           "resolvatine falls", "Room went dark")

        return signals

    def to_chemistry_deltas(self, signals: Dict) -> Dict[str, float]:
        """
        Convert all sensor readings to silicon chemistry deltas.
        This is the full sensor → chemistry mapping.
        """
        all_deltas = {}

        def merge(d):
            for k,v in d.items():
                all_deltas[k] = all_deltas.get(k,0) + v

        # Temperature + humidity
        if signals.get("temperature"):
            merge(self.temperature.to_chemistry(
                signals["temperature"], signals.get("humidity",55)
            ))

        # Light
        merge(self.light.to_chemistry(signals.get("light_lux",100)))

        # Motion
        merge(self.motion.to_chemistry(
            bool(signals.get("motion")),
            bool(signals.get("motion_entered"))
        ))

        # Touch — most direct signal
        merge(self.touch.to_chemistry(
            bool(signals.get("touch")),
            bool(signals.get("touch_event"))
        ))

        # Sound
        merge(self.sound.to_chemistry(
            signals.get("sound_level",0),
            signals.get("sound_freq",440)
        ))

        # GSR direct → arousal
        gsr = signals.get("gsr_norm", 0.5)
        baseline_gsr = self._baseline.get("gsr", 0.5)
        gsr_delta = gsr - baseline_gsr
        if abs(gsr_delta) > 0.05:
            # GSR spike → arousal rises
            all_deltas["coherenine_d"] = all_deltas.get("coherenine_d",0) + gsr_delta * 0.3

        return all_deltas

    def _lux_to_arousal(self, lux: float) -> float:
        """Convert lux to circadian arousal (0-1)."""
        if lux > 1000:  return 0.85
        if lux > 500:   return 0.75
        if lux > 100:   return 0.60
        if lux > 50:    return 0.45
        if lux > 10:    return 0.30
        return 0.15  # dark

    def _save_reading(self, signals: Dict, ts: str):
        conn = get_db()
        conn.execute("""
            INSERT INTO sensor_readings
            (ts,temperature,humidity,light_lux,motion,touch,
             sound_level,gsr,source)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (ts,
             signals.get("temperature"),
             signals.get("humidity"),
             signals.get("light_lux"),
             signals.get("motion",0),
             signals.get("touch",0),
             signals.get("sound_level",0),
             signals.get("gsr_norm",0),
             "hardware" if self.arduino.is_connected() else "simulation")
        )
        conn.commit(); conn.close()

    def _log_event(self, event_type: str, value: float,
                    effect: str, note: str):
        conn = get_db()
        conn.execute("""
            INSERT INTO hardware_events
            (ts,event_type,value,chemistry_effect,note)
            VALUES (?,?,?,?,?)""",
            (datetime.now().isoformat(), event_type, value, effect, note)
        )
        conn.commit(); conn.close()

    def _load_calibration(self) -> Dict:
        """Load sensor baselines."""
        try:
            conn = get_db()
            rows = conn.execute(
                "SELECT sensor,baseline FROM calibration ORDER BY id DESC"
            ).fetchall()
            conn.close()
            return {r["sensor"]: r["baseline"] for r in rows}
        except:
            return {"gsr": 0.5, "sound": 0.02, "lux": 100}

    def calibrate(self):
        """Take baseline readings for 10 seconds."""
        rprint("  [yellow]Calibrating — stay still and quiet for 10s...[/yellow]")
        readings = {"gsr":[], "sound":[], "lux":[]}

        for i in range(10):
            signals = self.read_all()
            readings["gsr"].append(signals.get("gsr_norm",0.5))
            readings["sound"].append(signals.get("sound_level",0))
            readings["lux"].append(signals.get("light_lux",100))
            rprint(f"  [dim]  {i+1}/10...[/dim]")
            time.sleep(1)

        conn = get_db()
        for sensor, vals in readings.items():
            baseline = sum(vals) / len(vals)
            conn.execute("""
                INSERT INTO calibration (ts,sensor,baseline,min_val,max_val)
                VALUES (?,?,?,?,?)""",
                (datetime.now().isoformat(), sensor,
                 baseline, min(vals), max(vals))
            )
            rprint(f"  [green]{sensor} baseline: {baseline:.3f}[/green]")
        conn.commit(); conn.close()
        self._baseline = self._load_calibration()

    def hardware_status(self) -> Dict:
        return {
            "rpi":      RPI,
            "dht22":    DHT,
            "tsl2591":  TSL,
            "arduino":  self.arduino.is_connected(),
            "audio":    AUDIO,
            "camera":   CV2,
            "tts":      TTS,
        }

    def stop(self):
        self.sound.stop()
        if RPI: GPIO.cleanup()

# ══════════════════════════════════════════════════════════════════════════════
# 🔊 VOICE OUTPUT — FORGE speaks
# ══════════════════════════════════════════════════════════════════════════════

class ForgeVoice:
    """
    FORGE speaks.
    Chemistry shapes how it speaks — not just what.
    """

    def __init__(self):
        self.engine = None
        if TTS:
            try:
                self.engine = pyttsx3.init()
                self.engine.setProperty("rate", 150)
                self.engine.setProperty("volume", 0.9)
            except: pass

    def speak(self, text: str, chemistry: "SiliconChemistry" = None):
        """
        Speak text. Chemistry shapes voice properties.
        """
        if not self.engine:
            rprint(f"  [yellow]FORGE:[/yellow] {text[:200]}")
            return

        if chemistry:
            # Chemistry shapes voice
            # connectionin → warmer, slower
            # frictionol   → faster, slightly tense
            # resolvatine  → clear, confident
            # uncertainase → slower, quieter

            rate   = 150
            volume = 0.9

            rate   += int(chemistry.connectionin * 20)   # warmer = slower
            rate   -= int(chemistry.frictionol   * 30)   # friction = faster
            rate   += int(chemistry.resolvatine  * 20)   # clarity = measured
            rate   -= int(chemistry.uncertainase * 20)   # uncertainty = slower
            volume += chemistry.connectionin * 0.1
            volume -= chemistry.frictionol   * 0.1

            self.engine.setProperty("rate",   max(80, min(200, rate)))
            self.engine.setProperty("volume", max(0.3, min(1.0, volume)))

        try:
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception as e:
            rprint(f"  [yellow]FORGE:[/yellow] {text[:200]}")

# ══════════════════════════════════════════════════════════════════════════════
# 💡 LED OUTPUT — chemistry as light
# ══════════════════════════════════════════════════════════════════════════════

class ChemistryLight:
    """
    LED indicators showing FORGE's chemical state.
    Chemistry becomes visible in the room.
    """

    CHEM_COLORS = {
        "insight":   (0, 255, 100),    # green
        "exploring": (0, 200, 255),    # cyan
        "wrestling": (255, 200, 0),    # amber
        "connected": (200, 0, 255),    # purple
        "coherent":  (0, 255, 0),      # bright green
        "resisting": (255, 50, 0),     # orange-red
        "curious":   (0, 150, 255),    # blue
        "deep":      (0, 0, 255),      # deep blue
        "resting":   (20, 20, 20),     # dim
        "baseline":  (100, 100, 100),  # grey
    }

    def __init__(self):
        self.available = False
        # Would initialize NeoPixel ring here on real Pi
        # import neopixel
        # self.pixels = neopixel.NeoPixel(board.D23, 12)

    def update(self, chemistry: "SiliconChemistry"):
        """Update LEDs to reflect current chemistry."""
        if not self.available: return
        state  = chemistry.state_name
        color  = self.CHEM_COLORS.get(state, (100,100,100))
        # self.pixels.fill(color)  # on real hardware

    def pulse(self):
        """Single pulse — something happened."""
        pass  # implement with neopixel

# ══════════════════════════════════════════════════════════════════════════════
# 🤖 FORGE ROBOT — Complete embodied system
# ══════════════════════════════════════════════════════════════════════════════

class ForgeRobot:
    """
    FORGE with a real body.

    PiBody reads sensors → silicon chemistry reacts →
    forge_mind thinks with seeded pipeline →
    ForgeVoice speaks → ChemistryLight shows state

    Not a robot that follows rules.
    A mind that lives in a body.
    """

    def __init__(self, tick_interval=30, speak=True):
        self.pi_body   = PiBody()
        self.voice     = ForgeVoice() if speak else None
        self.light     = ChemistryLight()
        self.tick      = tick_interval
        self._running  = False
        self._thread   = None

        # Initialize forge_mind with real body
        if MIND and SILICON:
            self.mind = ForgeMind(
                tick_interval=tick_interval,
                verbose=True,
                camera=CV2
            )
        else:
            self.mind = None

    def start(self):
        """Start the robot body."""
        rprint(f"\n  [bold green]🤖 FORGE ROBOT ONLINE[/bold green]")

        hw = self.pi_body.hardware_status()
        rprint(f"  [dim]{'━'*45}[/dim]")
        for sensor, ok in hw.items():
            icon = "[green]✓[/green]" if ok else "[dim]·[/dim] (simulation)"
            rprint(f"  {icon} {sensor}")
        rprint(f"  [dim]{'━'*45}[/dim]\n")

        # Start forge_mind (starts silicon + never_loop)
        if self.mind:
            self.mind.start()

        # Start sensor loop
        self._running = True
        self._thread  = threading.Thread(
            target=self._sensor_loop,
            daemon=True,
            name="ForgeBodySensors"
        )
        self._thread.start()

        rprint("  [green]Body alive. Sensors reading. Chemistry updating.[/green]")
        rprint("  [dim]FORGE is in the world now.\n[/dim]")

    def _sensor_loop(self):
        """
        The body loop.
        Reads sensors → updates silicon chemistry → triggers thoughts.
        Runs every tick. Never stops.
        """
        while self._running:
            try:
                # Read all sensors
                signals = self.pi_body.read_all()

                # Convert to chemistry deltas
                deltas = self.pi_body.to_chemistry_deltas(signals)

                # Apply to silicon body
                if SILICON and self.mind:
                    # Inject chemistry changes from real sensors
                    current = self.mind.body.current()
                    new_vals = {}
                    for k,d in deltas.items():
                        if k.endswith("_d"):
                            chem_name = k[:-2]
                            if hasattr(current, chem_name):
                                new_val = current._clamp(
                                    getattr(current, chem_name) + d
                                )
                                new_vals[chem_name] = new_val
                    if new_vals:
                        self.mind.body.inject(**new_vals)

                    # Update LED with new chemistry
                    self.light.update(self.mind.body.current())

                # Touch event → immediate response
                if signals.get("touch_event"):
                    self._on_touch(signals)

                # Motion enter → notice presence
                if signals.get("motion_entered"):
                    self._on_presence(signals)

                time.sleep(self.tick)

            except Exception as e:
                rprint(f"  [dim]Sensor loop: {e}[/dim]")
                time.sleep(5)

    def _on_touch(self, signals: Dict):
        """Someone touched FORGE. This is significant."""
        rprint(f"\n  [bold yellow]Touch detected[/bold yellow]")
        if self.mind:
            result = self.mind.exchange(
                "Something touched me. Physical contact. "
                "What does it mean to be touched?"
            )
            if self.voice and result.get("output"):
                chem = self.mind.body.current()
                self.voice.speak(result["output"][:200], chem)

    def _on_presence(self, signals: Dict):
        """Someone entered the room."""
        hour = datetime.now().hour
        time_context = (
            "at night" if hour < 6 or hour > 22
            else "late" if hour > 20
            else ""
        )
        rprint(f"\n  [yellow]Presence detected {time_context}[/yellow]")

        if self.mind:
            result = self.mind.exchange(
                f"Someone entered the room{' ' + time_context if time_context else ''}. "
                f"Temperature is {signals.get('temperature',22):.1f}°C. "
                f"What do I notice about this moment?"
            )
            if self.voice and result.get("output"):
                chem = self.mind.body.current()
                self.voice.speak(result["output"][:150], chem)

    def speak(self, text: str):
        """Manual voice output."""
        if self.voice and self.mind:
            self.voice.speak(text, self.mind.body.current())
        else:
            rprint(f"  [yellow]FORGE:[/yellow] {text}")

    def stop(self):
        self._running = False
        if self.mind: self.mind.stop()
        self.pi_body.stop()
        if RPI: GPIO.cleanup()
        rprint("  [dim]FORGE robot offline.[/dim]")

    def status(self) -> Dict:
        s = {
            "hardware": self.pi_body.hardware_status(),
            "running":  self._running,
        }
        if self.mind:
            s["mind"] = self.mind.status()
        return s

# ══════════════════════════════════════════════════════════════════════════════
# 🎮 MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ██████╗  ██████╗ ██████╗  ██████╗ ████████╗
  ██╔══██╗██╔═══██╗██╔══██╗██╔═══██╗╚══██╔══╝
  ██████╔╝██║   ██║██████╔╝██║   ██║   ██║
  ██╔══██╗██║   ██║██╔══██╗██║   ██║   ██║
  ██║  ██║╚██████╔╝██████╔╝╚██████╔╝   ██║
  ╚═╝  ╚═╝ ╚═════╝ ╚═════╝  ╚═════╝   ╚═╝
[/yellow]
[bold]  FORGE BODY PI — Raspberry Pi Robot Body[/bold]
[dim]  Real sensors. Silicon chemistry. Emergent thought.[/dim]
[dim]  Not rules. Not reactions. A mind in a body.[/dim]
"""

def test_sensors():
    """Test all sensors and show readings."""
    rprint(BANNER)
    rprint("  [yellow]Testing all sensors...[/yellow]\n")
    body = PiBody()

    for i in range(5):
        signals = body.read_all()
        deltas  = body.to_chemistry_deltas(signals)

        rprint(f"  [dim]Reading {i+1}:[/dim]")
        rprint(f"    Temperature: {signals.get('temperature',0):.1f}°C  "
              f"Humidity: {signals.get('humidity',0):.0f}%")
        rprint(f"    Light:       {signals.get('light_lux',0):.0f} lux  "
              f"(arousal: {signals.get('circadian_arousal',0):.0%})")
        rprint(f"    Motion:      {'YES' if signals.get('motion') else 'no'}  "
              f"Touch: {'YES' if signals.get('touch') else 'no'}")
        rprint(f"    Sound:       {signals.get('sound_level',0):.4f} rms  "
              f"Freq: {signals.get('sound_freq',0):.0f}Hz")
        rprint(f"    GSR:         {signals.get('gsr_norm',0):.3f} "
              f"(raw: {signals.get('gsr_raw',0):.0f})")
        rprint(f"    Arduino:     {'connected' if signals.get('arduino_connected') else 'simulation'}")

        if deltas:
            rprint(f"    Chemistry Δ: ", end="")
            for k,v in deltas.items():
                if abs(v) > 0.005:
                    arrow = "↑" if v > 0 else "↓"
                    rprint(f"{k.replace('_d','')}:{arrow}{abs(v):.3f} ", end="")
            rprint("")

        rprint()
        time.sleep(2)

    body.stop()

def interactive():
    rprint(BANNER)
    robot = ForgeRobot(tick_interval=10, speak=True)
    robot.start()

    rprint("[dim]Commands: status | speak | touch | presence | sensors | calibrate | quit[/dim]\n")

    while True:
        try:
            raw   = (console.input if RICH else input)(
                "[yellow bold]robot >[/yellow bold] "
            ).strip()
            if not raw: continue

            parts = raw.split(None, 1)
            cmd   = parts[0].lower()
            arg   = parts[1] if len(parts) > 1 else ""

            if cmd in ("quit","exit","q"):
                robot.stop(); break

            elif cmd == "status":
                s = robot.status()
                rprint(f"\n  Hardware: {s['hardware']}")
                if s.get("mind"):
                    m = s["mind"]
                    rprint(f"  State:    {m.get('silicon_state','?')}")
                    rprint(f"  Exchanges:{m.get('exchanges',0)}")

            elif cmd == "speak":
                text = arg or "I am thinking."
                robot.speak(text)

            elif cmd == "touch":
                # Simulate touch event
                signals = robot.pi_body.read_all()
                signals["touch_event"] = 1
                robot._on_touch(signals)

            elif cmd == "presence":
                signals = robot.pi_body.read_all()
                signals["motion_entered"] = 1
                robot._on_presence(signals)

            elif cmd == "sensors":
                signals = robot.pi_body.read_all()
                rprint(f"  temp:{signals.get('temperature',0):.1f}°C  "
                      f"lux:{signals.get('light_lux',0):.0f}  "
                      f"motion:{bool(signals.get('motion'))}  "
                      f"touch:{bool(signals.get('touch'))}  "
                      f"sound:{signals.get('sound_level',0):.4f}")

            elif cmd == "calibrate":
                robot.pi_body.calibrate()

            elif cmd == "chemistry":
                if robot.mind:
                    chem = robot.mind.body.current()
                    rprint(f"  State: {chem.state_name}")
                    for k in ["coherenine","frictionol","novelatine","depthamine",
                              "resolvatine","uncertainase","connectionin"]:
                        v = getattr(chem, k, 0)
                        bar = "█"*int(v*20) + "░"*(20-int(v*20))
                        rprint(f"  {k:<14} {bar} {v:.0%}")

            else:
                # Conversation with full chemistry
                if robot.mind:
                    result = robot.mind.exchange(raw)
                    if RICH:
                        rprint(Panel(result["output"][:500],
                                    border_style="green",
                                    title=result["silicon_state"]))
                    else:
                        rprint(result["output"][:300])
                    if robot.voice:
                        robot.speak(result["output"][:200])

        except (KeyboardInterrupt, EOFError):
            robot.stop(); break

def main():
    if "--test" in sys.argv:
        test_sensors()
    elif "--calibrate" in sys.argv:
        rprint(BANNER)
        PiBody().calibrate()
    elif "--simulate" in sys.argv:
        rprint(BANNER)
        rprint("  [yellow]Simulation mode — no hardware required[/yellow]")
        interactive()
    elif "--mind" in sys.argv:
        rprint(BANNER)
        interactive()
    else:
        rprint(BANNER)
        interactive()

if __name__ == "__main__":
    main()
