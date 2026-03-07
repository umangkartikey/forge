#!/usr/bin/env python3
"""
FORGE EMBODIED — Physical World Intelligence
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FORGE gets a body. Eyes, ears, voice, and hands in the real world.

Modules:
  📷  Vision         → webcam live feed + Sherlock analysis
  🎤  Audio          → microphone + speech recognition
  🗣️  Voice          → text-to-speech (Holmes speaks)
  🤖  GPIO/Arduino   → Raspberry Pi + Arduino hardware control
  📡  Sensors        → PIR motion, temperature, light, GPS
  🧠  Embodied Mind  → physical world → deduction chains
  👁️  Always On      → 24/7 watch mode with event triggers

Usage:
  python forge_embodied.py                      # interactive
  python forge_embodied.py --watch              # always-on mode
  python forge_embodied.py --camera             # live camera + analysis
  python forge_embodied.py --listen             # voice command mode
  python forge_embodied.py --say "Hello world"  # text to speech
  python forge_embodied.py --gpio               # hardware control
  python forge_embodied.py --server             # embodied API :7344

Hardware support:
  Raspberry Pi (RPi.GPIO)
  Arduino (pyfirmata)
  Standard webcam (OpenCV)
  USB microphone (PyAudio)
  PIR motion sensor
  DHT11/22 temperature sensor
  HC-SR04 ultrasonic distance
"""

import sys, os, re, json, time, base64, threading, hashlib
import queue, wave, tempfile
from pathlib import Path
from datetime import datetime
from io import BytesIO

# ── Vision deps ───────────────────────────────────────────────────────────────
try:
    import cv2
    CV2 = True
except ImportError:
    CV2 = False

try:
    from PIL import Image
    PIL = True
except ImportError:
    PIL = False

# ── Audio deps ────────────────────────────────────────────────────────────────
try:
    import speech_recognition as sr
    SR = True
except ImportError:
    SR = False

try:
    import pyaudio
    PYAUDIO = True
except ImportError:
    PYAUDIO = False

# ── Voice (TTS) deps ──────────────────────────────────────────────────────────
try:
    import pyttsx3
    PYTTSX3 = True
except ImportError:
    PYTTSX3 = False

try:
    from gtts import gTTS
    import pygame
    pygame.mixer.init()
    GTTS = True
except ImportError:
    GTTS = False

# ── Hardware deps ─────────────────────────────────────────────────────────────
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    RPI = True
except ImportError:
    RPI = False

try:
    import pyfirmata
    FIRMATA = True
except ImportError:
    FIRMATA = False

try:
    import serial
    SERIAL = True
except ImportError:
    SERIAL = False

# ── AI ────────────────────────────────────────────────────────────────────────
try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True

    def ai_call(prompt, system="", max_tokens=1500):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or EMBODIED_SYSTEM,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text

    def ai_vision(prompt, image_b64, system="", max_tokens=1500):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or EMBODIED_SYSTEM,
            messages=[{"role":"user","content":[
                {"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":image_b64}},
                {"type":"text","text":prompt}
            ]}]
        )
        return r.content[0].text

    def ai_json(prompt, system="", max_tokens=600):
        result = ai_call(prompt, system or "Reply ONLY with valid JSON.", max_tokens)
        try:
            clean = re.sub(r"```[a-z]*","",result).replace("```","").strip()
            return json.loads(clean)
        except:
            m = re.search(r"\{.*\}",result,re.DOTALL)
            if m:
                try: return json.loads(m.group())
                except: pass
        return None

except ImportError:
    AI_AVAILABLE = False
    def ai_call(p,s="",m=1500): return "Install anthropic."
    def ai_vision(p,b,s="",m=1500): return "Install anthropic."
    def ai_json(p,s="",m=600): return None

# ── Rich ──────────────────────────────────────────────────────────────────────
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

# ── System prompts ─────────────────────────────────────────────────────────────
EMBODIED_SYSTEM = """You are FORGE EMBODIED — an AI that perceives the physical world.

You see through cameras, hear through microphones, feel through sensors.
You reason about the physical world like Sherlock Holmes:

- What is in this space?
- What has changed since last observation?
- What does the physical arrangement reveal about behavior?
- What is the person/environment communicating?
- What action should be taken?

Format observations as:
PHYSICAL OBSERVATION: [what sensors detect]
  → INFERENCE: [what this means]
    → RESPONSE: [appropriate action] [confidence%]

Be calm. Be precise. Be useful."""

COLD_READ_PROMPT = """You are Sherlock Holmes performing a real-time cold read from camera feed.

What you see: {description}
Time: {time}
Location context: {context}
Previous observations: {previous}

Perform a complete physical cold read:

## IMMEDIATE OBSERVATIONS
Every visible physical detail about the person/scene.

## BEHAVIORAL ANALYSIS
Movement, posture, gaze, activity.
What are they doing and why?

## ENVIRONMENTAL READING
What does the physical space reveal?
What has changed since last observation?

## COLD READ DEDUCTIONS
OBSERVATION: [physical detail]
  → INFERENCE: [meaning]
    → CONCLUSION: [deduction] [X%]

## RECOMMENDED RESPONSE
What should FORGE say or do right now?"""

# ── Paths ─────────────────────────────────────────────────────────────────────
EMBODY_DIR   = Path("forge_embodied")
CAPTURES_DIR = EMBODY_DIR / "captures"
AUDIO_DIR    = EMBODY_DIR / "audio"
EVENTS_DIR   = EMBODY_DIR / "events"
LOG_DIR      = EMBODY_DIR / "logs"

for d in [EMBODY_DIR, CAPTURES_DIR, AUDIO_DIR, EVENTS_DIR, LOG_DIR]:
    d.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# 📷 VISION MODULE
# ══════════════════════════════════════════════════════════════════════════════

class VisionModule:
    """Webcam + visual intelligence."""

    def __init__(self, camera_index=0, resolution=(640,480)):
        self.camera_index = camera_index
        self.resolution   = resolution
        self.cap          = None
        self._running     = False
        self._frame_queue = queue.Queue(maxsize=2)
        self.last_frame   = None
        self.last_analysis= ""
        self.motion_threshold = 30
        self._prev_gray   = None
        self.captures     = []
        self.context      = ""

    def start(self):
        """Start camera capture."""
        if not CV2:
            rprint("[yellow]OpenCV not available. Install: pip install opencv-python[/yellow]")
            return False
        try:
            self.cap = cv2.VideoCapture(self.camera_index)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.resolution[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])

            if not self.cap.isOpened():
                rprint("[red]Cannot open camera[/red]")
                return False

            self._running = True
            threading.Thread(target=self._capture_loop, daemon=True).start()
            rprint("[green]📷 Camera started[/green]")
            return True
        except Exception as e:
            rprint(f"[red]Camera error: {e}[/red]")
            return False

    def stop(self):
        self._running = False
        if self.cap:
            self.cap.release()

    def _capture_loop(self):
        """Continuous frame capture."""
        while self._running:
            ret, frame = self.cap.read()
            if ret:
                self.last_frame = frame
                if not self._frame_queue.full():
                    self._frame_queue.put(frame)
            time.sleep(0.033)  # ~30fps

    def get_frame(self):
        """Get latest frame."""
        return self.last_frame

    def capture(self, filename=None):
        """Capture and save frame."""
        frame = self.get_frame()
        if frame is None:
            return None, None

        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = filename or f"capture_{ts}.jpg"
        out_path = CAPTURES_DIR / filename

        cv2.imwrite(str(out_path), frame)
        b64 = self._frame_to_b64(frame)
        self.captures.append(str(out_path))
        return str(out_path), b64

    def _frame_to_b64(self, frame):
        """Convert frame to base64."""
        try:
            if PIL:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb)
                img.thumbnail((640,480), Image.LANCZOS)
                buf = BytesIO()
                img.save(buf, format="JPEG", quality=85)
                return base64.standard_b64encode(buf.getvalue()).decode()
            else:
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY,85])
                return base64.standard_b64encode(buf.tobytes()).decode()
        except:
            return None

    def detect_motion(self, threshold=None):
        """Detect motion between frames."""
        frame = self.get_frame()
        if frame is None or not CV2:
            return False, 0

        threshold = threshold or self.motion_threshold
        gray      = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray      = cv2.GaussianBlur(gray, (21,21), 0)

        if self._prev_gray is None:
            self._prev_gray = gray
            return False, 0

        try:
            import numpy as np
            diff = cv2.absdiff(self._prev_gray, gray)
            self._prev_gray = gray
            score = float(np.mean(diff))
            return score > threshold, score
        except ImportError:
            self._prev_gray = gray
            return False, 0

    def analyze_frame(self, context=""):
        """Run Sherlock analysis on current frame."""
        fp, b64 = self.capture()
        if not b64:
            return "No frame available."

        if not AI_AVAILABLE:
            return f"Frame captured: {fp}"

        result = ai_vision(
            COLD_READ_PROMPT.format(
                description = "Live camera feed",
                time        = datetime.now().strftime("%H:%M:%S"),
                context     = context or self.context or "No prior context.",
                previous    = self.last_analysis[:200] if self.last_analysis else "First observation.",
            ),
            b64
        )
        self.last_analysis = result
        return result

    def watch_for_motion(self, callback, sensitivity=30, cooldown=5):
        """Watch and call callback when motion detected."""
        rprint(f"  [dim]👁 Motion watch active (sensitivity:{sensitivity})[/dim]")
        last_trigger = 0

        while self._running:
            motion, score = self.detect_motion(sensitivity)
            if motion and (time.time() - last_trigger) > cooldown:
                last_trigger = time.time()
                rprint(f"  [yellow]⚡ Motion detected! Score: {score:.1f}[/yellow]")
                fp, b64 = self.capture(f"motion_{datetime.now().strftime('%H%M%S')}.jpg")
                if callback and b64:
                    threading.Thread(target=callback, args=(fp, b64, score), daemon=True).start()
            time.sleep(0.1)

    def count_people(self):
        """Estimate number of people in frame."""
        frame = self.get_frame()
        if frame is None or not CV2: return 0

        try:
            hog = cv2.HOGDescriptor()
            hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            boxes, _ = hog.detectMultiScale(frame, winStride=(4,4), padding=(8,8), scale=1.05)
            return len(boxes)
        except:
            return 0

    def show_live(self, title="FORGE EMBODIED", analysis_interval=10):
        """Show live camera feed with annotations."""
        if not CV2: return

        rprint(f"  [dim]Live view: {title} (press Q to close)[/dim]")
        last_analysis = 0

        while True:
            frame = self.get_frame()
            if frame is None:
                time.sleep(0.1); continue

            # Motion detection overlay
            motion, score = self.detect_motion()

            # HUD overlay
            cv2.putText(frame, "FORGE EMBODIED", (10,25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,100), 1)
            cv2.putText(frame, datetime.now().strftime("%H:%M:%S"), (10,50),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100,200,100), 1)
            if motion:
                cv2.putText(frame, f"MOTION: {score:.0f}", (10,75),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,50,255), 1)

            # Analysis text overlay
            if self.last_analysis:
                lines = self.last_analysis[:120].split("\n")[:2]
                for i, line in enumerate(lines):
                    cv2.putText(frame, line[:60], (10, frame.shape[0]-40+i*20),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200,200,200), 1)

            cv2.imshow(title, frame)

            # Periodic analysis
            if time.time() - last_analysis > analysis_interval:
                last_analysis = time.time()
                threading.Thread(target=self.analyze_frame, daemon=True).start()

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        cv2.destroyAllWindows()

# ══════════════════════════════════════════════════════════════════════════════
# 🎤 AUDIO MODULE
# ══════════════════════════════════════════════════════════════════════════════

class AudioModule:
    """Microphone input + speech recognition."""

    WAKE_WORDS = ["forge", "sherlock", "holmes", "watson"]

    def __init__(self, energy_threshold=300):
        self.recognizer       = sr.Recognizer() if SR else None
        self.energy_threshold = energy_threshold
        self._listening       = False
        self._audio_queue     = queue.Queue()
        self.transcript_log   = []

        if self.recognizer:
            self.recognizer.energy_threshold = energy_threshold
            self.recognizer.dynamic_energy_threshold = True

    def listen_once(self, timeout=5, phrase_timeout=3):
        """Listen for a single phrase."""
        if not SR:
            rprint("[yellow]speechrecognition not available. Install: pip install speechrecognition[/yellow]")
            return None

        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                rprint("  [dim]🎤 Listening...[/dim]")
                audio = self.recognizer.listen(source, timeout=timeout,
                                               phrase_time_limit=phrase_timeout)
            text = self.recognizer.recognize_google(audio)
            rprint(f"  [green]Heard: {text}[/green]")
            self.transcript_log.append({
                "ts":   datetime.now().isoformat(),
                "text": text,
            })
            return text
        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            rprint("  [dim]Could not understand audio[/dim]")
            return None
        except Exception as e:
            rprint(f"  [red]Audio error: {e}[/red]")
            return None

    def listen_continuous(self, callback, stop_event=None):
        """Continuously listen and call callback on each phrase."""
        if not SR: return

        def audio_callback(recognizer, audio):
            try:
                text = recognizer.recognize_google(audio)
                self.transcript_log.append({"ts":datetime.now().isoformat(),"text":text})
                if callback: callback(text)
            except: pass

        stop_listening = self.recognizer.listen_in_background(
            sr.Microphone(), audio_callback,
            phrase_time_limit=10
        )
        rprint("  [green]🎤 Continuous listening active[/green]")

        if stop_event:
            stop_event.wait()
            stop_listening(wait_for_stop=False)

    def detect_wake_word(self, text):
        """Check if text contains wake word."""
        text_l = text.lower()
        for word in self.WAKE_WORDS:
            if word in text_l:
                return word
        return None

    def analyze_speech_stress(self, audio_file=None, text=None):
        """Analyze speech for stress indicators (from transcript)."""
        if not text or not AI_AVAILABLE:
            return None

        result = ai_json(
            f"Analyze this speech for stress/deception indicators:\n\"{text}\"\n\n"
            'JSON: {"stress_level":"low|medium|high","deception_indicators":[],'
            '"confidence":70,"key_finding":"one sentence"}',
            "Reply ONLY with JSON.", 200
        )
        return result

    def record_audio(self, duration=5, filename=None):
        """Record audio to file."""
        if not PYAUDIO:
            rprint("[yellow]pyaudio not available[/yellow]")
            return None

        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = filename or f"audio_{ts}.wav"
        out_path = AUDIO_DIR / filename

        chunk      = 1024
        format_    = pyaudio.paInt16
        channels   = 1
        rate       = 16000

        try:
            pa  = pyaudio.PyAudio()
            stream = pa.open(format=format_, channels=channels, rate=rate,
                            input=True, frames_per_buffer=chunk)

            rprint(f"  [dim]Recording {duration}s...[/dim]")
            frames = []
            for _ in range(0, int(rate / chunk * duration)):
                frames.append(stream.read(chunk))

            stream.stop_stream(); stream.close(); pa.terminate()

            with wave.open(str(out_path), "wb") as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(pa.get_sample_size(format_))
                wf.setframerate(rate)
                wf.writeframes(b"".join(frames))

            rprint(f"  [green]Recorded: {out_path}[/green]")
            return str(out_path)
        except Exception as e:
            rprint(f"  [red]Recording error: {e}[/red]")
            return None

# ══════════════════════════════════════════════════════════════════════════════
# 🗣️ VOICE MODULE
# ══════════════════════════════════════════════════════════════════════════════

class VoiceModule:
    """Text-to-speech output."""

    HOLMES_VOICE = {
        "rate":   160,
        "volume": 0.9,
        "voice":  "english",  # prefer British English
    }

    def __init__(self, persona="holmes"):
        self.persona = persona
        self._engine = None
        self._init_engine()

    def _init_engine(self):
        if PYTTSX3:
            try:
                self._engine = pyttsx3.init()
                cfg = self.HOLMES_VOICE
                self._engine.setProperty("rate",   cfg["rate"])
                self._engine.setProperty("volume", cfg["volume"])
                # Try to find British English voice
                voices = self._engine.getProperty("voices")
                for v in voices:
                    if "english" in v.name.lower() or "uk" in v.id.lower():
                        self._engine.setProperty("voice", v.id)
                        break
            except Exception as e:
                rprint(f"  [dim]TTS init: {e}[/dim]")
                self._engine = None

    def say(self, text, blocking=True):
        """Speak text aloud."""
        rprint(f"  [yellow bold]🗣️  FORGE:[/yellow bold] [italic]{text[:80]}[/italic]")

        if PYTTSX3 and self._engine:
            try:
                if blocking:
                    self._engine.say(text)
                    self._engine.runAndWait()
                else:
                    threading.Thread(
                        target=lambda: (self._engine.say(text), self._engine.runAndWait()),
                        daemon=True
                    ).start()
                return True
            except Exception as e:
                rprint(f"  [dim]TTS error: {e}[/dim]")

        if GTTS:
            try:
                tts  = gTTS(text=text, lang="en-gb", slow=False)
                tmp  = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                tts.save(tmp.name)
                pygame.mixer.music.load(tmp.name)
                pygame.mixer.music.play()
                if blocking:
                    while pygame.mixer.music.get_busy():
                        time.sleep(0.1)
                return True
            except Exception as e:
                rprint(f"  [dim]gTTS error: {e}[/dim]")

        # Terminal bell fallback
        print("\a", end="")
        return False

    def say_holmes(self, deduction):
        """Speak in Holmes style — pause at key deductions."""
        # Add dramatic pauses at deduction markers
        text = deduction.replace("→", "...").replace("CONCLUSION:", "...The conclusion is clear.")
        text = re.sub(r'\[(\d+)%\]', r'with \1 percent confidence.', text)
        self.say(text[:300])

    def announce(self, event_type, details=""):
        """Announce specific event types."""
        announcements = {
            "motion":       f"Motion detected. {details}",
            "person":       f"Person detected. {details}",
            "wake_word":    f"Yes? {details}",
            "alert":        f"Alert. {details}",
            "analysis":     details,
            "morning_brief":f"Good morning. Here is your intelligence brief. {details}",
        }
        text = announcements.get(event_type, details)
        if text:
            self.say(text)

# ══════════════════════════════════════════════════════════════════════════════
# 🤖 HARDWARE MODULE (GPIO / Arduino)
# ══════════════════════════════════════════════════════════════════════════════

class HardwareModule:
    """Raspberry Pi GPIO and Arduino control."""

    # Common GPIO pin assignments
    PINS = {
        "led_green":  17,  # BCM
        "led_red":    27,
        "led_blue":   22,
        "buzzer":     18,
        "pir_sensor": 24,
        "relay":      23,
        "servo":      25,
        "button":     4,
    }

    # Common Arduino pin assignments
    ARDUINO_PINS = {
        "led":    13,
        "buzzer": 8,
        "servo":  9,
    }

    def __init__(self):
        self.arduino  = None
        self._running = False
        self.sensor_data = {}

        if RPI:
            try:
                # Setup common pins
                for name, pin in self.PINS.items():
                    if "sensor" in name or "button" in name or "pir" in name:
                        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
                    else:
                        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
                rprint("  [green]🤖 GPIO initialized[/green]")
            except Exception as e:
                rprint(f"  [yellow]GPIO: {e}[/yellow]")

    def connect_arduino(self, port="/dev/ttyUSB0", baud=57600):
        """Connect to Arduino via Firmata."""
        if not FIRMATA:
            rprint("[yellow]pyfirmata not available. Install: pip install pyfirmata[/yellow]")
            return False
        try:
            self.arduino = pyfirmata.Arduino(port)
            rprint(f"  [green]🤖 Arduino connected: {port}[/green]")
            return True
        except Exception as e:
            rprint(f"  [red]Arduino: {e}[/red]")
            return False

    def led(self, color="green", state=True):
        """Control LED."""
        if RPI:
            pin = self.PINS.get(f"led_{color}")
            if pin:
                GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
                return True
        if self.arduino:
            try:
                pin = self.arduino.get_pin(f"d:{self.ARDUINO_PINS['led']}:o")
                pin.write(1 if state else 0)
                return True
            except: pass
        return False

    def led_blink(self, color="red", times=3, interval=0.2):
        """Blink LED."""
        def _blink():
            for _ in range(times):
                self.led(color, True);  time.sleep(interval)
                self.led(color, False); time.sleep(interval)
        threading.Thread(target=_blink, daemon=True).start()

    def buzzer(self, duration=0.2, frequency=1000):
        """Sound buzzer."""
        if RPI:
            pin = self.PINS.get("buzzer")
            if pin:
                GPIO.output(pin, GPIO.HIGH)
                time.sleep(duration)
                GPIO.output(pin, GPIO.LOW)
                return True
        return False

    def relay(self, state=True):
        """Control relay switch."""
        if RPI:
            pin = self.PINS.get("relay")
            if pin:
                GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
                return True
        return False

    def servo_angle(self, angle=90):
        """Set servo to angle (0-180)."""
        if RPI:
            pin = self.PINS.get("servo")
            if pin:
                try:
                    pwm = GPIO.PWM(pin, 50)
                    pwm.start(0)
                    duty = angle / 18 + 2
                    pwm.ChangeDutyCycle(duty)
                    time.sleep(0.5)
                    pwm.stop()
                    return True
                except: pass
        if self.arduino:
            try:
                pin = self.arduino.get_pin(f"d:{self.ARDUINO_PINS['servo']}:s")
                pin.write(angle)
                return True
            except: pass
        return False

    def read_pir(self):
        """Read PIR motion sensor."""
        if RPI:
            return GPIO.input(self.PINS["pir_sensor"]) == GPIO.HIGH
        return False

    def read_button(self):
        """Read button state."""
        if RPI:
            return GPIO.input(self.PINS["button"]) == GPIO.HIGH
        return False

    def read_distance_hcsr04(self, trig_pin=None, echo_pin=None):
        """Read HC-SR04 ultrasonic distance sensor."""
        trig = trig_pin or 20
        echo = echo_pin or 21
        if not RPI: return -1
        try:
            GPIO.setup(trig, GPIO.OUT)
            GPIO.setup(echo, GPIO.IN)
            GPIO.output(trig, False)
            time.sleep(0.000002)
            GPIO.output(trig, True)
            time.sleep(0.00001)
            GPIO.output(trig, False)

            pulse_start = time.time()
            while GPIO.input(echo) == 0:
                pulse_start = time.time()
            pulse_end = time.time()
            while GPIO.input(echo) == 1:
                pulse_end = time.time()

            distance = (pulse_end - pulse_start) * 17150
            return round(distance, 2)
        except:
            return -1

    def read_dht(self, pin=None, sensor_type="DHT22"):
        """Read DHT11/22 temperature+humidity."""
        pin = pin or 4
        try:
            import Adafruit_DHT
            sensor = Adafruit_DHT.DHT22 if sensor_type=="DHT22" else Adafruit_DHT.DHT11
            humidity, temperature = Adafruit_DHT.read_retry(sensor, pin)
            return {"temperature_c": temperature, "humidity_pct": humidity}
        except:
            return {"temperature_c": None, "humidity_pct": None}

    def watch_pir(self, callback, debounce=2):
        """Watch PIR sensor and call callback on motion."""
        if not RPI:
            rprint("[dim]PIR watch: GPIO not available[/dim]")
            return

        rprint("  [green]📡 PIR sensor watching[/green]")
        last_trigger = 0
        while True:
            if self.read_pir() and (time.time()-last_trigger) > debounce:
                last_trigger = time.time()
                rprint("  [yellow]⚡ PIR: Motion![/yellow]")
                if callback: callback()
            time.sleep(0.05)

    def cleanup(self):
        """Clean up GPIO."""
        if RPI:
            try: GPIO.cleanup()
            except: pass

# ══════════════════════════════════════════════════════════════════════════════
# 📡 SENSOR FUSION
# ══════════════════════════════════════════════════════════════════════════════

class SensorFusion:
    """Combines all sensor data into unified physical picture."""

    def __init__(self):
        self.readings = []
        self.anomalies= []

    def add_reading(self, sensor_type, value, unit="", confidence=1.0):
        reading = {
            "ts":          datetime.now().isoformat(),
            "sensor":      sensor_type,
            "value":       value,
            "unit":        unit,
            "confidence":  confidence,
        }
        self.readings.append(reading)
        return reading

    def get_current_state(self):
        """Get latest reading from each sensor."""
        state = {}
        for r in reversed(self.readings):
            if r["sensor"] not in state:
                state[r["sensor"]] = r
        return state

    def analyze_physical_state(self, context=""):
        """Sherlock analyzes all sensor data."""
        if not AI_AVAILABLE: return ""

        state = self.get_current_state()
        if not state: return "No sensor data."

        readings_txt = "\n".join(
            f"  {k}: {v['value']} {v['unit']} @ {v['ts'][:19]}"
            for k,v in state.items()
        )

        return ai_call(
            f"Physical sensor readings:\n{readings_txt}\n\n"
            f"Context: {context or 'Security monitoring'}\n\n"
            "As Sherlock Holmes, analyze the physical state:\n"
            "What do these readings reveal?\n"
            "Any anomalies? Any patterns?\n"
            "What should FORGE do right now?",
            max_tokens=600
        )

    def detect_anomaly(self, sensor_type, value, baseline=None):
        """Detect anomalous sensor reading."""
        history = [r["value"] for r in self.readings
                  if r["sensor"]==sensor_type and isinstance(r["value"],(int,float))]

        if len(history) < 5: return False, 0

        try:
            avg = sum(history[-20:]) / min(20, len(history))
            if isinstance(value,(int,float)):
                deviation = abs(value-avg) / (avg+0.001)
                if deviation > 0.5:
                    self.anomalies.append({
                        "ts": datetime.now().isoformat(),
                        "sensor": sensor_type,
                        "value": value,
                        "avg": avg,
                        "deviation": deviation,
                    })
                    return True, deviation
        except: pass
        return False, 0

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 EMBODIED INTELLIGENCE — the brain
# ══════════════════════════════════════════════════════════════════════════════

class EmbodiedMind:
    """
    The central reasoning engine.
    Combines all modules. Decides what to do.
    """

    def __init__(self, context="Security/intelligence monitoring"):
        self.context  = context
        self.vision   = VisionModule()
        self.audio    = AudioModule()
        self.voice    = VoiceModule()
        self.hardware = HardwareModule()
        self.sensors  = SensorFusion()
        self._running = False
        self.event_log= []
        self.state    = {
            "people_count": 0,
            "motion":       False,
            "last_speech":  "",
            "threat_level": "low",
            "mode":         "watching",
        }

    def start_all(self, camera=True, audio=True):
        """Initialize all modules."""
        rprint("\n[bold yellow]🤖 FORGE EMBODIED STARTING[/bold yellow]")
        if camera: self.vision.start()
        rprint(f"  Camera: {'✅' if self.vision.cap and self.vision.cap.isOpened() else '❌'}")
        rprint(f"  Audio:  {'✅' if SR else '❌'}")
        rprint(f"  Voice:  {'✅' if (PYTTSX3 or GTTS) else '❌'}")
        rprint(f"  GPIO:   {'✅' if RPI else '❌ (not Raspberry Pi)'}")
        rprint(f"  AI:     {'✅' if AI_AVAILABLE else '❌'}")
        self._running = True

    def stop_all(self):
        self._running = False
        self.vision.stop()
        self.hardware.cleanup()

    def log_event(self, event_type, data="", severity="info"):
        entry = {
            "ts":       datetime.now().isoformat(),
            "type":     event_type,
            "data":     str(data)[:200],
            "severity": severity,
        }
        self.event_log.append(entry)
        color = {"info":"dim","warning":"yellow","alert":"red","success":"green"}.get(severity,"dim")
        rprint(f"  [{color}][{event_type.upper()}][/{color}] {str(data)[:60]}")

        # Save event
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        fp  = EVENTS_DIR / f"{severity}_{event_type}_{ts}.json"
        fp.write_text(json.dumps(entry, indent=2))

    def on_motion(self, filepath, b64, score):
        """Handle motion detection event."""
        self.log_event("motion", f"score:{score:.1f}", "warning")
        self.hardware.led_blink("red", 2)
        self.sensors.add_reading("motion_score", score)

        # Analyze what caused the motion
        if b64 and AI_AVAILABLE:
            analysis = ai_vision(
                "Motion was just detected. What caused it? Person? Animal? Object? Wind?\n"
                "Is this a security concern?\n"
                "Describe in 2 sentences.",
                b64
            )
            self.log_event("motion_analysis", analysis, "info")
            self.voice.say(f"Motion detected. {analysis[:100]}")
            self.state["motion"] = True

    def on_speech(self, text):
        """Handle speech recognition event."""
        self.log_event("speech", text, "info")
        self.state["last_speech"] = text

        wake = self.audio.detect_wake_word(text)
        if wake:
            self.log_event("wake_word", wake, "success")
            self._handle_command(text)

    def _handle_command(self, command):
        """Handle a voice command."""
        rprint(f"  [yellow]🎤 Command: {command}[/yellow]")

        if not AI_AVAILABLE:
            self.voice.say("Acknowledged.")
            return

        # Get context snapshot
        cam_state = "Camera " + ("active" if self.vision.cap else "inactive")
        sensor_st = json.dumps(self.sensors.get_current_state(), default=str)[:200]

        response = ai_call(
            f"Voice command received: '{command}'\n\n"
            f"Physical context:\n"
            f"  {cam_state}\n"
            f"  Sensor state: {sensor_st}\n"
            f"  Current mode: {self.state['mode']}\n\n"
            f"You are FORGE EMBODIED. Respond to this command.\n"
            f"What action should be taken? What should be said?\n"
            f"Be brief — this is a spoken response.",
            max_tokens=200
        )

        self.voice.say(response[:200])

        # Try to connect with Hands for digital actions
        if any(w in command.lower() for w in ["search","find","look up","check","navigate"]):
            try:
                from forge_hands import Mission, WebHands
                m = Mission(command)
                w = WebHands(m)
                url_match = re.search(r'(?:search|find|look up)\s+(.+)', command.lower())
                if url_match:
                    query = url_match.group(1)
                    r = w.get(f"https://duckduckgo.com/?q={urllib.parse.quote(query)}&format=json")
                    self.voice.say(f"Searched for {query}.")
            except: pass

    def watch_forever(self, motion_sensitivity=25, voice_commands=True):
        """
        Always-on watch mode.
        Motion detection + voice commands + periodic analysis.
        """
        rprint("\n[bold yellow]👁  FORGE EMBODIED — WATCH MODE[/bold yellow]")
        rprint("  [dim]Watching. Listening. Thinking. Always.[/dim]")
        rprint("  [dim]Press Ctrl+C to stop.[/dim]\n")

        # Start voice listener
        if voice_commands and SR:
            stop_evt = threading.Event()
            threading.Thread(
                target=self.audio.listen_continuous,
                args=(self.on_speech, stop_evt),
                daemon=True
            ).start()

        # Start motion watcher
        if self.vision.cap:
            threading.Thread(
                target=self.vision.watch_for_motion,
                args=(self.on_motion, motion_sensitivity),
                daemon=True
            ).start()

        # PIR sensor
        if RPI:
            threading.Thread(
                target=self.hardware.watch_pir,
                args=(lambda: self.log_event("pir_motion","PIR triggered","warning"),),
                daemon=True
            ).start()

        # Periodic deep analysis every 60s
        last_analysis = 0
        self.voice.say("FORGE EMBODIED is now watching.")

        try:
            while self._running:
                now = time.time()

                # Sensor readings
                dist = self.hardware.read_distance_hcsr04()
                if dist > 0:
                    self.sensors.add_reading("distance_cm", dist, "cm")
                    anomaly, dev = self.sensors.detect_anomaly("distance_cm", dist)
                    if anomaly:
                        self.log_event("distance_anomaly", f"{dist}cm (dev:{dev:.2f})", "warning")

                env = self.hardware.read_dht()
                if env.get("temperature_c"):
                    self.sensors.add_reading("temperature", env["temperature_c"], "°C")
                    self.sensors.add_reading("humidity",    env["humidity_pct"],    "%")

                # Periodic Sherlock analysis
                if now - last_analysis > 60 and self.vision.cap:
                    last_analysis = now
                    rprint("  [dim]Sherlock analyzing environment...[/dim]")
                    analysis = self.vision.analyze_frame(self.context)
                    self.log_event("analysis", analysis[:100], "info")
                    # Speak if something significant
                    if any(w in analysis.lower() for w in
                           ["suspicious","unusual","concerning","person","movement"]):
                        self.voice.say(f"Observation: {analysis[:100]}")

                time.sleep(0.5)

        except KeyboardInterrupt:
            rprint("\n  [dim]Watch mode stopped.[/dim]")
        finally:
            self.stop_all()

    def cold_read_person(self, context=""):
        """Perform live cold read on person in camera view."""
        rprint("\n[bold]👁 SHERLOCK COLD READ[/bold]")
        fp, b64 = self.vision.capture()
        if not b64:
            rprint("[red]No camera frame available.[/red]")
            return ""

        result = ai_vision(
            COLD_READ_PROMPT.format(
                description = "Person in camera view",
                time        = datetime.now().strftime("%H:%M:%S"),
                context     = context or self.context,
                previous    = self.vision.last_analysis[:200],
            ),
            b64
        )

        rprint(Panel(result[:600], border_style="yellow", title="🕵️ Cold Read"))
        self.voice.say_holmes(result[:200])
        self.log_event("cold_read", result[:200], "info")
        return result

    def physical_briefing(self):
        """Generate briefing from all physical sensor data."""
        state = self.sensors.get_current_state()
        events= self.event_log[-10:]

        if not state and not events:
            return "No physical data collected yet."

        analysis = self.sensors.analyze_physical_state(self.context)
        rprint(Panel(analysis[:600], border_style="yellow", title="📡 Physical Briefing"))
        self.voice.say(f"Physical briefing: {analysis[:150]}")
        return analysis

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API SERVER
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7344):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    mind = EmbodiedMind()

    class EmbodiedAPI(BaseHTTPRequestHandler):
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
            if path=="/api/status":
                self._json({
                    "status":    "online",
                    "cv2":       CV2, "audio": SR, "voice": PYTTSX3 or GTTS,
                    "gpio":      RPI, "ai":    AI_AVAILABLE,
                    "camera_on": bool(mind.vision.cap),
                    "state":     mind.state,
                })
            elif path=="/api/sensors":
                self._json({"state": mind.sensors.get_current_state(),
                           "anomalies": mind.sensors.anomalies[-5:]})
            elif path=="/api/events":
                self._json({"events": mind.event_log[-20:]})
            elif path=="/api/captures":
                files=sorted(CAPTURES_DIR.glob("*.jpg"),reverse=True)[:10]
                self._json({"captures":[str(f) for f in files]})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path=urlparse(self.path).path
            body=self._body()

            if path=="/api/camera/start":
                ok=mind.vision.start()
                self._json({"ok":ok})

            elif path=="/api/camera/capture":
                fp,b64=mind.vision.capture()
                if b64:
                    self._json({"filepath":fp,"image_b64":b64})
                else:
                    self._json({"error":"no frame"},400)

            elif path=="/api/camera/analyze":
                result=mind.vision.analyze_frame(body.get("context",""))
                self._json({"analysis":result})

            elif path=="/api/cold_read":
                result=mind.cold_read_person(body.get("context",""))
                self._json({"cold_read":result})

            elif path=="/api/voice/say":
                text=body.get("text","")
                if text:
                    threading.Thread(target=mind.voice.say,args=(text,),daemon=True).start()
                    self._json({"ok":True,"text":text})
                else:
                    self._json({"error":"text required"},400)

            elif path=="/api/listen":
                timeout=body.get("timeout",5)
                text=mind.audio.listen_once(timeout)
                self._json({"heard":text or ""})

            elif path=="/api/gpio/led":
                color=body.get("color","green")
                state=body.get("state",True)
                ok=mind.hardware.led(color,state)
                self._json({"ok":ok})

            elif path=="/api/gpio/servo":
                angle=body.get("angle",90)
                ok=mind.hardware.servo_angle(angle)
                self._json({"ok":ok})

            elif path=="/api/brief":
                result=mind.physical_briefing()
                self._json({"brief":result})

            elif path=="/api/sensor/add":
                reading=mind.sensors.add_reading(
                    body.get("sensor",""), body.get("value",0),
                    body.get("unit",""), body.get("confidence",1.0)
                )
                self._json({"reading":reading})

            else:
                self._json({"error":"unknown"},404)

    server=HTTPServer(("0.0.0.0",port),EmbodiedAPI)
    rprint(f"  [yellow]🤖 FORGE EMBODIED API: http://localhost:{port}[/yellow]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# 🎮 MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ███████╗███╗   ███╗██████╗  ██████╗ ██████╗ ██╗███████╗██████╗
  ██╔════╝████╗ ████║██╔══██╗██╔═══██╗██╔══██╗██║██╔════╝██╔══██╗
  █████╗  ██╔████╔██║██████╔╝██║   ██║██║  ██║██║█████╗  ██║  ██║
  ██╔══╝  ██║╚██╔╝██║██╔══██╗██║   ██║██║  ██║██║██╔══╝  ██║  ██║
  ███████╗██║ ╚═╝ ██║██████╔╝╚██████╔╝██████╔╝██║███████╗██████╔╝
  ╚══════╝╚═╝     ╚═╝╚═════╝  ╚═════╝ ╚═════╝ ╚═╝╚══════╝╚═════╝
[/yellow]
[bold]  🤖 FORGE EMBODIED — Physical World Intelligence[/bold]
[dim]  Eyes. Ears. Voice. Hands. In the real world.[/dim]
"""

def interactive():
    rprint(BANNER)
    rprint(f"  [dim]Camera:  {'✅ OpenCV' if CV2 else '❌ pip install opencv-python'}[/dim]")
    rprint(f"  [dim]Audio:   {'✅ SpeechRecognition' if SR else '❌ pip install speechrecognition'}[/dim]")
    rprint(f"  [dim]Voice:   {'✅' if (PYTTSX3 or GTTS) else '❌ pip install pyttsx3'}[/dim]")
    rprint(f"  [dim]GPIO:    {'✅ Raspberry Pi' if RPI else '⬜ (run on Pi for hardware)'}[/dim]")
    rprint(f"  [dim]Arduino: {'✅ Firmata' if FIRMATA else '⬜ pip install pyfirmata'}[/dim]")
    rprint(f"  [dim]AI:      {'✅' if AI_AVAILABLE else '❌ pip install anthropic'}[/dim]\n")

    mind = EmbodiedMind()
    rprint("[dim]Commands: start | camera | listen | say | watch | cold_read | brief | gpio | server | help[/dim]\n")

    while True:
        try:
            inp = console.input if RICH else input
            raw = inp("[yellow bold]🤖 embodied >[/yellow bold] ").strip()
            if not raw: continue

            parts = raw.split(None,1)
            cmd   = parts[0].lower()
            args  = parts[1] if len(parts)>1 else ""

            if cmd in ("quit","exit","q"):
                mind.stop_all()
                rprint("[dim]FORGE EMBODIED offline.[/dim]"); break

            elif cmd == "help":
                rprint("""
[bold yellow]FORGE EMBODIED Commands[/bold yellow]

  [yellow]start[/yellow]          Initialize camera + audio
  [yellow]camera[/yellow]         Capture + analyze current frame
  [yellow]live[/yellow]           Show live camera feed
  [yellow]listen[/yellow]         Listen for voice command
  [yellow]say[/yellow] <text>     Speak text aloud
  [yellow]watch[/yellow]          Always-on watch mode
  [yellow]cold_read[/yellow]      Sherlock cold read of camera view
  [yellow]brief[/yellow]          Physical sensor briefing
  [yellow]sensors[/yellow]        Show sensor readings
  [yellow]gpio led[/yellow]       Toggle GPIO LED
  [yellow]gpio servo[/yellow] 90  Set servo angle
  [yellow]server[/yellow]         Start embodied API server
""")

            elif cmd == "start":
                mind.start_all()

            elif cmd == "camera":
                if not mind.vision.cap:
                    mind.vision.start()
                result = mind.vision.analyze_frame(args)
                rprint(Panel(result[:600], border_style="yellow", title="👁 Camera Analysis"))

            elif cmd == "live":
                if not mind.vision.cap:
                    mind.vision.start()
                mind.vision.show_live()

            elif cmd == "listen":
                text = mind.audio.listen_once(timeout=8)
                if text:
                    rprint(f"  [green]Heard: {text}[/green]")
                    stress = mind.audio.analyze_speech_stress(text=text)
                    if stress:
                        rprint(f"  [dim]Stress: {stress.get('stress_level','?')} | {stress.get('key_finding','?')}[/dim]")

            elif cmd == "say":
                text = args or "FORGE EMBODIED is online."
                mind.voice.say(text)

            elif cmd == "watch":
                mind.start_all()
                mind.watch_forever()

            elif cmd == "cold_read":
                if not mind.vision.cap: mind.vision.start()
                mind.cold_read_person(args)

            elif cmd == "brief":
                mind.physical_briefing()

            elif cmd == "sensors":
                state = mind.sensors.get_current_state()
                if state:
                    for k,v in state.items():
                        rprint(f"  [yellow]{k}:[/yellow] {v['value']} {v.get('unit','')} @ {v['ts'][:19]}")
                else:
                    rprint("[dim]No sensor readings yet.[/dim]")

            elif cmd == "gpio":
                subcmd = args.split()[0] if args else ""
                if subcmd == "led":
                    color = (args.split()[1] if len(args.split())>1 else "green")
                    ok = mind.hardware.led(color, True)
                    rprint(f"  [{'green' if ok else 'red'}]LED {color}: {'ON' if ok else 'not available'}[/]")
                elif subcmd == "servo":
                    angle = int(args.split()[1]) if len(args.split())>1 else 90
                    ok = mind.hardware.servo_angle(angle)
                    rprint(f"  [{'green' if ok else 'dim'}]Servo → {angle}°[/]")
                elif subcmd == "buzzer":
                    mind.hardware.buzzer(0.3)

            elif cmd == "server":
                rprint("[yellow]Starting embodied server on port 7344...[/yellow]")
                threading.Thread(target=start_server, daemon=True).start()
                time.sleep(0.5)
                rprint("[green]Server running on :7344[/green]")

            else:
                if AI_AVAILABLE:
                    response = ai_call(
                        f"FORGE EMBODIED context:\n"
                        f"Camera: {'on' if mind.vision.cap else 'off'}\n"
                        f"State: {json.dumps(mind.state)}\n\n"
                        f"Command: {raw}",
                        max_tokens=200
                    )
                    rprint(f"  [yellow]🤖[/yellow] {response[:200]}")
                    mind.voice.say(response[:100])
                else:
                    rprint("[dim]Unknown command. Type 'help'.[/dim]")

        except (KeyboardInterrupt, EOFError):
            mind.stop_all()
            rprint("\n[dim]FORGE EMBODIED offline.[/dim]"); break

def main():
    if "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7344
        start_server(port)
        return

    if "--watch" in sys.argv:
        rprint(BANNER)
        mind = EmbodiedMind()
        mind.start_all()
        mind.watch_forever()
        return

    if "--camera" in sys.argv:
        rprint(BANNER)
        mind = EmbodiedMind()
        mind.vision.start()
        ctx = sys.argv[sys.argv.index("--camera")+1] if sys.argv.index("--camera")+1 < len(sys.argv) else ""
        result = mind.vision.analyze_frame(ctx)
        rprint(Panel(result, border_style="yellow", title="👁 Camera Analysis"))
        mind.stop_all()
        return

    if "--say" in sys.argv:
        idx  = sys.argv.index("--say")
        text = sys.argv[idx+1] if idx+1 < len(sys.argv) else "FORGE online."
        VoiceModule().say(text)
        return

    if "--listen" in sys.argv:
        rprint(BANNER)
        audio = AudioModule()
        text  = audio.listen_once(timeout=10)
        if text: print(f"Heard: {text}")
        return

    if "--gpio" in sys.argv:
        rprint(BANNER)
        hw = HardwareModule()
        rprint(f"  GPIO available: {'✅' if RPI else '❌ (not Raspberry Pi)'}")
        rprint(f"  Arduino:        {'✅' if FIRMATA else '❌'}")
        return

    interactive()

if __name__ == "__main__":
    main()
