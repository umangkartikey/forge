#!/usr/bin/env python3
"""
FORGE OBSERVE — Real Eyes, Real Observation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Camera → OBSERVE → Chit → Chitan → Vichar → Understanding

Not answering questions about the world.
Watching the world. And thinking about what it sees.

That is not AI answering questions.
That is AI paying attention.

Inspired by: Observation → Chit → Chitan → Vichar → Character → Future
             (Arjun: The Warrior Prince)

Input Sources:
  Webcam       → live frame capture
  Pi Camera    → Raspberry Pi integration
  Image file   → analyze a saved image
  RTSP stream  → IP camera / security cam
  Screen       → watch the screen itself

Modes:
  --watch      continuous watching, thinks when interesting
  --snapshot   single frame, think about this moment
  --compare    two frames, what changed?
  --alert      only think when anomaly detected
  --image      analyze a specific image file

Pipeline:
  Frame captured
      ↓
  Vision: what is here? (Claude Vision API)
      ↓
  Interest score: is this worth thinking about?
      ↓
  forge_think v3: pipeline emerges from what is SEEN
      ↓
  forge_memory: remembers what was observed
      ↓
  forge_dream: overnight synthesis of all observations

Usage:
  python forge_observe.py --snapshot          # think about right now
  python forge_observe.py --watch             # continuous watching
  python forge_observe.py --image photo.jpg   # analyze image
  python forge_observe.py --compare a.jpg b.jpg  # what changed?
  python forge_observe.py --alert             # alert mode only
  python forge_observe.py --server            # API :7352
"""

import sys, os, re, json, time, sqlite3, threading, hashlib, base64
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

# Memory + Think integration
try:
    from forge_memory import Memory
    MEMORY = True
except ImportError:
    MEMORY = False
    class Memory:
        def remember(self,*a,**k): pass
        def recall(self,e): return None

try:
    from forge_think import EmergentThinkEngine
    THINK = True
except ImportError:
    THINK = False
    class EmergentThinkEngine:
        def __init__(self,**k): pass
        def think(self,q,context=""): return {"output":q,"emerged_pipeline":["OBSERVE"],"coherence":50,"duration_s":0,"novel_pipeline":False,"phase_count":1}

# Camera
try:
    import cv2
    CV2 = True
except ImportError:
    CV2 = False

# Pi Camera
try:
    from picamera2 import Picamera2
    PICAM = True
except ImportError:
    PICAM = False

# Screen capture
try:
    import PIL.ImageGrab
    SCREEN = True
except ImportError:
    SCREEN = False

# AI Vision
try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True

    def vision_call(image_b64: str, prompt: str, max_tokens=800) -> str:
        r = _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": "image/jpeg",
                            "data":       image_b64,
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            }]
        )
        return r.content[0].text

    def ai_call(prompt, system="", max_tokens=600):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system, messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text

    def ai_json(prompt, system="", max_tokens=300):
        result = ai_call(prompt, system or "Reply ONLY with valid JSON.", max_tokens)
        try:
            clean = re.sub(r"```[a-z]*","",result).replace("```","").strip()
            return json.loads(clean)
        except:
            m = re.search(r"\{.*\}", result, re.DOTALL)
            if m:
                try: return json.loads(m.group())
                except: pass
        return None

except ImportError:
    AI_AVAILABLE = False
    def vision_call(b, p, m=800): return f"[Vision unavailable] Scene: unknown"
    def ai_call(p,s="",m=600):   return "[AI unavailable]"
    def ai_json(p,s="",m=300):   return None

# Rich
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

# ── Paths ────────────────────────────────────────────────────────────────────
OBSERVE_DIR = Path("forge_observe")
OBSERVE_DIR.mkdir(exist_ok=True)
FRAMES_DIR  = OBSERVE_DIR / "frames"
FRAMES_DIR.mkdir(exist_ok=True)
OBSERVE_DB  = OBSERVE_DIR / "observe.db"

INTEREST_THRESHOLD = 60   # 0-100, below this = not worth thinking about
WATCH_INTERVAL     = 30   # seconds between frames in watch mode
MAX_FRAME_SIZE     = 800  # resize large frames to this width

def get_db():
    conn = sqlite3.connect(str(OBSERVE_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS observations (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ts            TEXT,
            source        TEXT,
            frame_path    TEXT,
            scene_desc    TEXT,
            objects       TEXT,
            people_count  INTEGER DEFAULT 0,
            anomalies     TEXT,
            interest_score INTEGER DEFAULT 0,
            thought       TEXT,
            pipeline      TEXT,
            coherence     REAL DEFAULT 0,
            mood          TEXT,
            time_of_day   TEXT,
            duration_s    REAL
        );
        CREATE TABLE IF NOT EXISTS watch_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started     TEXT,
            ended       TEXT,
            frames      INTEGER DEFAULT 0,
            thoughts    INTEGER DEFAULT 0,
            source      TEXT
        );
        CREATE TABLE IF NOT EXISTS anomalies (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            obs_id      INTEGER,
            description TEXT,
            severity    TEXT,
            notified    INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 📸 FRAME CAPTURE
# ══════════════════════════════════════════════════════════════════════════════

class FrameCapture:
    """Capture frames from any source."""

    def from_webcam(self, camera_id=0) -> Optional[bytes]:
        """Capture single frame from webcam."""
        if not CV2:
            return self._placeholder_frame("webcam")
        try:
            cap   = cv2.VideoCapture(camera_id)
            ret, frame = cap.read()
            cap.release()
            if not ret: return None
            frame = self._resize(frame)
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return buf.tobytes()
        except Exception as e:
            rprint(f"  [dim]Webcam: {e}[/dim]")
            return None

    def from_picam(self) -> Optional[bytes]:
        """Capture from Raspberry Pi camera."""
        if not PICAM:
            return self._placeholder_frame("picam")
        try:
            cam = Picamera2()
            cam.start()
            time.sleep(0.5)
            frame = cam.capture_array()
            cam.stop()
            if CV2:
                frame = self._resize(frame)
                _, buf = cv2.imencode(".jpg", frame)
                return buf.tobytes()
            return None
        except Exception as e:
            rprint(f"  [dim]PiCam: {e}[/dim]")
            return None

    def from_file(self, path: str) -> Optional[bytes]:
        """Load image from file."""
        try:
            p = Path(path)
            if not p.exists():
                rprint(f"  [red]File not found: {path}[/red]")
                return None
            if CV2:
                frame = cv2.imread(str(p))
                if frame is None: return None
                frame = self._resize(frame)
                _, buf = cv2.imencode(".jpg", frame)
                return buf.tobytes()
            else:
                return p.read_bytes()
        except Exception as e:
            rprint(f"  [dim]File load: {e}[/dim]")
            return None

    def from_screen(self) -> Optional[bytes]:
        """Capture the screen."""
        if not SCREEN:
            return self._placeholder_frame("screen")
        try:
            img = PIL.ImageGrab.grab()
            if CV2:
                import numpy as np
                frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                frame = self._resize(frame)
                _, buf = cv2.imencode(".jpg", frame)
                return buf.tobytes()
            return None
        except Exception as e:
            rprint(f"  [dim]Screen: {e}[/dim]")
            return None

    def from_rtsp(self, url: str) -> Optional[bytes]:
        """Capture single frame from RTSP stream."""
        if not CV2:
            return self._placeholder_frame("rtsp")
        try:
            cap   = cv2.VideoCapture(url)
            ret, frame = cap.read()
            cap.release()
            if not ret: return None
            frame = self._resize(frame)
            _, buf = cv2.imencode(".jpg", frame)
            return buf.tobytes()
        except Exception as e:
            rprint(f"  [dim]RTSP: {e}[/dim]")
            return None

    def _resize(self, frame, max_w=MAX_FRAME_SIZE):
        """Resize frame keeping aspect ratio."""
        if not CV2: return frame
        h, w = frame.shape[:2]
        if w > max_w:
            scale = max_w / w
            frame = cv2.resize(frame, (max_w, int(h * scale)))
        return frame

    def _placeholder_frame(self, source: str) -> bytes:
        """When camera not available — return placeholder description."""
        # Return a simple gray JPEG or just signal via special bytes
        return b"PLACEHOLDER:" + source.encode()

    def save_frame(self, frame_bytes: bytes, ts: str) -> str:
        """Save frame to disk, return path."""
        if frame_bytes.startswith(b"PLACEHOLDER:"):
            return ""
        fname = FRAMES_DIR / f"frame_{ts.replace(':','-').replace(' ','_')}.jpg"
        fname.write_bytes(frame_bytes)
        return str(fname)

    def to_base64(self, frame_bytes: bytes) -> str:
        """Convert frame bytes to base64 for Vision API."""
        if frame_bytes.startswith(b"PLACEHOLDER:"):
            return ""
        return base64.standard_b64encode(frame_bytes).decode()

# ══════════════════════════════════════════════════════════════════════════════
# 👁️ VISION ANALYZER — what does FORGE see?
# ══════════════════════════════════════════════════════════════════════════════

VISION_SYSTEM = """You are FORGE's visual cortex — the first layer of observation.

Describe what you see with the awareness of someone who notices everything.
Not a dry inventory. A living description.

Include:
- Scene type and setting
- People (count, approximate age, what they're doing, body language)
- Objects and their arrangement
- Lighting, time of day, atmosphere
- Anything unusual, out of place, or worth attention
- The emotional tone of the scene

End with:
INTEREST: [0-100] — how worthy is this of deeper thought?
ANOMALY: [yes/no] — is something unusual or concerning here?
MOOD: [one word — calm/tense/lonely/busy/peaceful/urgent/etc]"""

INTEREST_SYSTEM = """You decide if a visual observation is worth deeper thinking.

Score 0-100:
  0-30:  Nothing interesting. Empty room, blank scene, no change.
  31-59: Mildly interesting. Normal activity, nothing unusual.
  60-79: Worth thinking about. Something notable in the scene.
  80-100: Definitely think about this. Unusual, important, or meaningful.

Return JSON: {"score": 72, "reason": "brief reason", "anomaly": false}"""

class VisionAnalyzer:
    """Analyze what the camera sees."""

    def analyze(self, frame_b64: str, context: str = "") -> Dict[str, Any]:
        """Full visual analysis of a frame."""
        if not frame_b64:
            return self._no_vision_fallback()

        if not AI_AVAILABLE:
            return self._no_vision_fallback()

        now     = datetime.now()
        tod     = self._time_of_day(now.hour)
        prompt  = (
            f"Time: {now.strftime('%H:%M')} ({tod})\n"
            f"Context: {context or 'General observation'}\n\n"
            "What do you see?"
        )

        description = vision_call(frame_b64, prompt, max_tokens=600)

        # Extract structured data from description
        interest    = self._extract_interest(description)
        anomaly     = "ANOMALY: yes" in description.upper()
        mood        = self._extract_mood(description)
        people      = self._count_people(description)
        objects     = self._extract_objects(description)
        anomaly_desc= self._extract_anomaly_desc(description) if anomaly else ""

        return {
            "description":  description,
            "interest":     interest,
            "anomaly":      anomaly,
            "anomaly_desc": anomaly_desc,
            "mood":         mood,
            "people_count": people,
            "objects":      objects,
            "time_of_day":  tod,
            "ts":           now.isoformat(),
        }

    def _extract_interest(self, desc: str) -> int:
        m = re.search(r"INTEREST:\s*(\d+)", desc, re.IGNORECASE)
        return int(m.group(1)) if m else 50

    def _extract_mood(self, desc: str) -> str:
        m = re.search(r"MOOD:\s*(\w+)", desc, re.IGNORECASE)
        return m.group(1).lower() if m else "neutral"

    def _count_people(self, desc: str) -> int:
        # Simple heuristic
        desc_lower = desc.lower()
        if "no one" in desc_lower or "empty" in desc_lower: return 0
        if "one person" in desc_lower or "a person" in desc_lower: return 1
        if "two people" in desc_lower: return 2
        if "several people" in desc_lower or "group" in desc_lower: return 3
        m = re.search(r"(\d+)\s+people", desc_lower)
        return int(m.group(1)) if m else 0

    def _extract_objects(self, desc: str) -> List[str]:
        # Extract key objects mentioned
        common = ["laptop","phone","desk","chair","window","door",
                  "book","cup","coffee","monitor","keyboard","bed",
                  "table","plant","light","bag","car","person"]
        found = [o for o in common if o in desc.lower()]
        return found[:8]

    def _extract_anomaly_desc(self, desc: str) -> str:
        # Find the sentence mentioning the anomaly
        for sent in desc.split("."):
            if any(w in sent.lower() for w in ["unusual","strange","unexpected","anomaly","alert","concern"]):
                return sent.strip()
        return ""

    def _time_of_day(self, hour: int) -> str:
        if 5  <= hour < 12: return "morning"
        if 12 <= hour < 17: return "afternoon"
        if 17 <= hour < 21: return "evening"
        return "night"

    def compare_frames(self, desc1: str, desc2: str) -> Dict[str, Any]:
        """What changed between two observations?"""
        if not AI_AVAILABLE:
            return {"changes": "AI unavailable", "significant": False, "delta_interest": 0}

        result = ai_call(
            f"Frame 1 observation:\n{desc1}\n\n"
            f"Frame 2 observation:\n{desc2}\n\n"
            "What changed? What is significant? What stayed the same?\n"
            "Rate significance of change 0-100.",
            system="You compare two visual observations and find what changed.",
            max_tokens=400
        )

        sig_match = re.search(r"(\d+)", result)
        sig_score = int(sig_match.group(1)) if sig_match else 50

        return {
            "changes":     result,
            "significant": sig_score > 60,
            "delta_score": sig_score,
        }

    def _no_vision_fallback(self) -> Dict[str, Any]:
        """When no camera or AI available."""
        now = datetime.now()
        return {
            "description":  f"[No visual input] Time: {now.strftime('%H:%M')}",
            "interest":     30,
            "anomaly":      False,
            "anomaly_desc": "",
            "mood":         "unknown",
            "people_count": 0,
            "objects":      [],
            "time_of_day":  self._time_of_day(now.hour),
            "ts":           now.isoformat(),
        }

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 OBSERVE ENGINE — connects eyes to thought
# ══════════════════════════════════════════════════════════════════════════════

class ObserveEngine:
    """
    The bridge between camera and thought.

    Camera → Vision → Interest check → forge_think v3 → Memory
    """

    def __init__(self, interest_threshold=INTEREST_THRESHOLD, show_trace=True):
        self.threshold  = interest_threshold
        self.show_trace = show_trace
        self.capture    = FrameCapture()
        self.vision     = VisionAnalyzer()
        self.memory     = Memory()
        self.thinker    = EmergentThinkEngine(threshold=65, show_trace=show_trace)

    def snapshot(self, source="webcam", source_arg=None) -> Dict[str, Any]:
        """Capture one frame, analyze, and think about it."""
        start = time.time()
        now   = datetime.now().isoformat()

        if self.show_trace:
            rprint(f"\n  [yellow]👁  Capturing from {source}...[/yellow]")

        # ── Capture ───────────────────────────────────────────────────────────
        frame_bytes = self._capture(source, source_arg)
        frame_b64   = self.capture.to_base64(frame_bytes) if frame_bytes else ""
        frame_path  = self.capture.save_frame(frame_bytes, now[:19]) if frame_bytes else ""

        # ── Vision Analysis ───────────────────────────────────────────────────
        if self.show_trace:
            rprint(f"  [yellow]👁  Analyzing scene...[/yellow]")

        vision = self.vision.analyze(frame_b64)

        if self.show_trace:
            mood_color = {
                "tense":"red","urgent":"red","lonely":"cyan",
                "busy":"yellow","peaceful":"green","calm":"green"
            }.get(vision["mood"], "white")
            rprint(f"  [dim]Scene:    {vision['description'][:100]}...[/dim]")
            rprint(f"  [dim]Interest: [yellow]{vision['interest']}/100[/yellow]  "
                  f"Mood: [{mood_color}]{vision['mood']}[/{mood_color}]  "
                  f"People: {vision['people_count']}[/dim]")

        # ── Interest check ────────────────────────────────────────────────────
        if vision["interest"] < self.threshold:
            if self.show_trace:
                rprint(f"  [dim]Interest {vision['interest']} < {self.threshold} — not worth thinking about[/dim]")
            return {
                "thought":    None,
                "vision":     vision,
                "pipeline":   [],
                "interesting":False,
                "duration_s": round(time.time()-start,1),
            }

        if self.show_trace:
            rprint(f"  [green]Worth thinking about ({vision['interest']}/100) — emerging pipeline...[/green]\n")

        # ── Think about what was seen ─────────────────────────────────────────
        # The "question" for forge_think is the visual description — not text
        visual_question = (
            f"I am observing: {vision['description']}\n\n"
            f"Time: {vision['time_of_day']} | Mood: {vision['mood']} | "
            f"People: {vision['people_count']}\n"
            + (f"ANOMALY DETECTED: {vision['anomaly_desc']}\n" if vision['anomaly'] else "")
            + "\nWhat is happening here? What does this mean?"
        )

        thought = self.thinker.think(visual_question, context="Visual observation")

        # ── Save ──────────────────────────────────────────────────────────────
        conn = get_db()
        obs_id = conn.execute("""
            INSERT INTO observations
            (ts,source,frame_path,scene_desc,objects,people_count,
             anomalies,interest_score,thought,pipeline,coherence,
             mood,time_of_day,duration_s)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (now, source, frame_path,
             vision["description"][:1000],
             json.dumps(vision["objects"]),
             vision["people_count"],
             vision["anomaly_desc"][:500],
             vision["interest"],
             thought["output"][:2000],
             json.dumps(thought["emerged_pipeline"]),
             thought["coherence"],
             vision["mood"],
             vision["time_of_day"],
             round(time.time()-start,1))
        ).lastrowid

        # Log anomaly separately
        if vision["anomaly"]:
            severity = "high" if vision["interest"] > 80 else "medium"
            conn.execute("""
                INSERT INTO anomalies (ts,obs_id,description,severity)
                VALUES (?,?,?,?)""",
                (now, obs_id, vision["anomaly_desc"][:500], severity)
            )
            if self.show_trace:
                rprint(f"  [red]⚠  Anomaly logged: {vision['anomaly_desc'][:60]}[/red]")

        conn.commit(); conn.close()

        # Write to forge_memory
        if MEMORY:
            key = hashlib.md5((now+source).encode()).hexdigest()[:8]
            self.memory.remember(
                f"observation:{key}",
                "visual_observation",
                f"Saw: {vision['description'][:80]} | Thought: {thought['output'][:80]}",
                confidence=thought["coherence"]/100,
                source="forge_observe",
                module="forge_observe"
            )

        duration = round(time.time()-start, 1)

        return {
            "thought":     thought["output"],
            "vision":      vision,
            "pipeline":    thought["emerged_pipeline"],
            "coherence":   thought["coherence"],
            "interesting": True,
            "anomaly":     vision["anomaly"],
            "duration_s":  duration,
            "obs_id":      obs_id,
        }

    def compare(self, source_a: str, source_b: str) -> Dict[str, Any]:
        """Compare two images — what changed?"""
        rprint(f"\n  [yellow]👁  Loading frames for comparison...[/yellow]")

        ba = self.capture.from_file(source_a)
        bb = self.capture.from_file(source_b)

        va = self.vision.analyze(self.capture.to_base64(ba) if ba else "",
                                  "First observation")
        vb = self.vision.analyze(self.capture.to_base64(bb) if bb else "",
                                  "Second observation")

        rprint(f"  [dim]Frame A: {va['description'][:80]}...[/dim]")
        rprint(f"  [dim]Frame B: {vb['description'][:80]}...[/dim]")

        comparison = self.vision.compare_frames(va["description"], vb["description"])

        rprint(f"\n  [yellow]What changed:[/yellow]")
        rprint(f"  {comparison['changes'][:300]}")

        # Think about the change
        if comparison["significant"]:
            change_question = (
                f"Something changed between two observations.\n\n"
                f"Before: {va['description'][:200]}\n"
                f"After:  {vb['description'][:200]}\n\n"
                f"Change: {comparison['changes'][:200]}\n\n"
                "What does this change mean?"
            )
            thought = self.thinker.think(change_question)
            return {**comparison, "thought": thought["output"],
                    "pipeline": thought["emerged_pipeline"]}

        return {**comparison, "thought": None, "pipeline": []}

    def watch(self, source="webcam", source_arg=None,
              interval=WATCH_INTERVAL, max_frames=None):
        """Continuously watch and think."""
        rprint(f"\n  [bold yellow]👁  FORGE OBSERVE — Watch Mode[/bold yellow]")
        rprint(f"  [dim]Source: {source} | Interval: {interval}s | Threshold: {self.threshold}[/dim]")
        rprint(f"  [dim]Ctrl+C to stop[/dim]\n")

        conn    = get_db()
        sess_id = conn.execute(
            "INSERT INTO watch_sessions (started,source) VALUES (?,?)",
            (datetime.now().isoformat(), source)
        ).lastrowid
        conn.commit(); conn.close()

        frames  = 0
        thoughts= 0
        last_desc = ""

        try:
            while True:
                if max_frames and frames >= max_frames:
                    break

                frames += 1
                rprint(f"  [dim]Frame {frames} — {datetime.now().strftime('%H:%M:%S')}[/dim]")

                result = self.snapshot(source, source_arg)

                if result["interesting"]:
                    thoughts += 1
                    if self.show_trace and result.get("thought"):
                        rprint(Panel(
                            result["thought"][:400],
                            border_style="green",
                            title=f"Thought {thoughts} | pipeline: {' → '.join(result['pipeline'][:4])}..."
                        ))

                last_desc = result["vision"]["description"]

                # Update session
                conn = get_db()
                conn.execute(
                    "UPDATE watch_sessions SET frames=?,thoughts=?,ended=? WHERE id=?",
                    (frames, thoughts, datetime.now().isoformat(), sess_id)
                )
                conn.commit(); conn.close()

                time.sleep(interval)

        except KeyboardInterrupt:
            rprint(f"\n  [dim]Watch stopped. Frames: {frames} | Thoughts: {thoughts}[/dim]")

        return {"frames": frames, "thoughts": thoughts}

    def _capture(self, source: str, arg=None) -> Optional[bytes]:
        if source == "webcam":
            return self.capture.from_webcam(arg or 0)
        elif source == "picam":
            return self.capture.from_picam()
        elif source == "screen":
            return self.capture.from_screen()
        elif source == "rtsp" and arg:
            return self.capture.from_rtsp(arg)
        elif source == "file" and arg:
            return self.capture.from_file(arg)
        elif arg and Path(arg).exists():
            return self.capture.from_file(arg)
        return None

    def get_history(self, limit=10):
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM observations ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_anomalies(self, limit=20):
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM anomalies ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def stats(self):
        conn = get_db()
        s = {
            "total_observations": conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0],
            "total_thoughts":     conn.execute("SELECT COUNT(*) FROM observations WHERE thought IS NOT NULL").fetchone()[0],
            "total_anomalies":    conn.execute("SELECT COUNT(*) FROM anomalies").fetchone()[0],
            "avg_interest":       round(conn.execute("SELECT AVG(interest_score) FROM observations").fetchone()[0] or 0,1),
            "avg_coherence":      round(conn.execute("SELECT AVG(coherence) FROM observations").fetchone()[0] or 0,1),
            "watch_sessions":     conn.execute("SELECT COUNT(*) FROM watch_sessions").fetchone()[0],
            "sources_seen":       dict(conn.execute(
                "SELECT source, COUNT(*) FROM observations GROUP BY source"
            ).fetchall()),
        }
        conn.close()
        return s

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API SERVER
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7352):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    class ObserveAPI(BaseHTTPRequestHandler):
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
            path   = urlparse(self.path).path
            engine = ObserveEngine(show_trace=False)
            if path == "/api/status":
                self._json({"status":"online","ai":AI_AVAILABLE,
                           "cv2":CV2,"picam":PICAM,**engine.stats()})
            elif path == "/api/history":
                self._json({"observations":engine.get_history(20)})
            elif path == "/api/anomalies":
                self._json({"anomalies":engine.get_anomalies(20)})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()
            engine = ObserveEngine(
                interest_threshold=int(body.get("threshold", INTEREST_THRESHOLD)),
                show_trace=False
            )

            if path == "/api/snapshot":
                source = body.get("source","webcam")
                arg    = body.get("source_arg", None)
                result = engine.snapshot(source, arg)
                self._json(result)

            elif path == "/api/analyze":
                # Analyze base64 image sent directly
                image_b64 = body.get("image_b64","")
                if not image_b64:
                    self._json({"error":"image_b64 required"},400); return
                vision  = engine.vision.analyze(image_b64, body.get("context",""))
                thought = None
                if vision["interest"] >= engine.threshold:
                    q = f"I observe: {vision['description']}\nWhat is happening here?"
                    t = engine.thinker.think(q)
                    thought = t["output"]
                self._json({"vision":vision,"thought":thought})

            elif path == "/api/watch/start":
                # Start watch in background thread
                source   = body.get("source","webcam")
                interval = int(body.get("interval", WATCH_INTERVAL))
                threading.Thread(
                    target=engine.watch,
                    kwargs={"source":source,"interval":interval,"max_frames":body.get("max_frames")},
                    daemon=True
                ).start()
                self._json({"ok":True,"watching":source,"interval":interval})

            else:
                self._json({"error":"unknown"},404)

    server = HTTPServer(("0.0.0.0",port),ObserveAPI)
    rprint(f"\n  [bold yellow]FORGE OBSERVE[/bold yellow]")
    rprint(f"  [green]API: http://localhost:{port}[/green]")
    rprint(f"  [dim]CV2: {'OK' if CV2 else 'pip install opencv-python'}[/dim]")
    rprint(f"  [dim]AI:  {'OK' if AI_AVAILABLE else 'pip install anthropic'}[/dim]\n")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# 🎮 MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
   ██████╗ ██████╗ ███████╗███████╗██████╗ ██╗   ██╗███████╗
  ██╔═══██╗██╔══██╗██╔════╝██╔════╝██╔══██╗██║   ██║██╔════╝
  ██║   ██║██████╔╝███████╗█████╗  ██████╔╝██║   ██║█████╗
  ██║   ██║██╔══██╗╚════██║██╔══╝  ██╔══██╗╚██╗ ██╔╝██╔══╝
  ╚██████╔╝██████╔╝███████║███████╗██║  ██║ ╚████╔╝ ███████╗
   ╚═════╝ ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝
[/yellow]
[bold]  FORGE OBSERVE — Real Eyes, Real Observation[/bold]
[dim]  Camera → Vision → Interest → forge_think v3 → Memory[/dim]
"""

def interactive():
    rprint(BANNER)
    engine = ObserveEngine(show_trace=True)
    s      = engine.stats()

    rprint(f"  [dim]AI Vision: {'OK' if AI_AVAILABLE else 'pip install anthropic'}[/dim]")
    rprint(f"  [dim]Camera:    {'OK (OpenCV)' if CV2 else 'pip install opencv-python'}[/dim]")
    rprint(f"  [dim]PiCam:     {'OK' if PICAM else 'not detected'}[/dim]")
    rprint(f"  [dim]Observations so far: {s['total_observations']}[/dim]\n")

    rprint("[dim]Commands:[/dim]")
    rprint("[dim]  snapshot [webcam|picam|screen]  — observe right now[/dim]")
    rprint("[dim]  image <path>                    — analyze image file[/dim]")
    rprint("[dim]  watch [interval_s]              — continuous watching[/dim]")
    rprint("[dim]  compare <img1> <img2>           — what changed?[/dim]")
    rprint("[dim]  history | anomalies | stats     — review[/dim]")
    rprint("[dim]  server                          — start API :7352[/dim]\n")

    while True:
        try:
            raw   = (console.input if RICH else input)(
                "[yellow bold]observe >[/yellow bold] "
            ).strip()
            if not raw: continue
            parts = raw.split()
            cmd   = parts[0].lower()
            args  = parts[1:]

            if cmd in ("quit","exit","q"):
                rprint("[dim]Eyes closed.[/dim]"); break

            elif cmd == "snapshot":
                source = args[0] if args else "webcam"
                result = engine.snapshot(source)
                if result.get("thought"):
                    rprint(Panel(result["thought"][:600], border_style="green",
                                title=f"Observation | interest:{result['vision']['interest']} | "
                                      f"pipeline:{' → '.join(result['pipeline'][:4])}..."))

            elif cmd == "image":
                if not args: rprint("[yellow]Usage: image <path>[/yellow]"); continue
                result = engine.snapshot("file", args[0])
                if result.get("thought"):
                    rprint(Panel(result["thought"][:600], border_style="green",
                                title=f"Image Analysis | {args[0]}"))
                elif not result["interesting"]:
                    rprint(f"  [dim]Not interesting enough ({result['vision']['interest']}/100)[/dim]")

            elif cmd == "watch":
                interval = int(args[0]) if args and args[0].isdigit() else WATCH_INTERVAL
                engine.watch(interval=interval)

            elif cmd == "compare":
                if len(args) < 2: rprint("[yellow]Usage: compare <img1> <img2>[/yellow]"); continue
                result = engine.compare(args[0], args[1])
                if result.get("thought"):
                    rprint(Panel(result["thought"][:500], border_style="cyan",
                                title="What Changed"))

            elif cmd == "history":
                obs = engine.get_history(5)
                for o in obs:
                    rprint(f"\n  [dim]{o['ts'][:19]}[/dim]  interest:{o['interest_score']}  mood:{o['mood']}")
                    rprint(f"  [dim]Scene: {(o['scene_desc'] or '')[:80]}...[/dim]")
                    if o.get("thought"):
                        rprint(f"  [dim]Thought: {o['thought'][:100]}...[/dim]")

            elif cmd == "anomalies":
                anom = engine.get_anomalies(5)
                if not anom:
                    rprint("  [dim]No anomalies detected yet[/dim]")
                for a in anom:
                    rprint(f"  [red]⚠  {a['ts'][:19]} [{a['severity']}] {a['description'][:80]}[/red]")

            elif cmd == "stats":
                s = engine.stats()
                rprint(f"\n  [bold]OBSERVE STATS[/bold]")
                for k,v in s.items():
                    if isinstance(v,dict):
                        rprint(f"  {k}:")
                        for kk,vv in v.items(): rprint(f"    {kk:<15} {vv}")
                    else:
                        rprint(f"  {k:<25} {v}")

            elif cmd == "server":
                threading.Thread(target=start_server, daemon=True).start()
                time.sleep(0.5)
                rprint("[green]Observe API on :7352[/green]")

            else:
                rprint("[dim]snapshot | image | watch | compare | history | anomalies | stats | server[/dim]")

        except (KeyboardInterrupt, EOFError):
            rprint("\n[dim]Eyes closed.[/dim]"); break

def main():
    if "--server" in sys.argv:
        rprint(BANNER)
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7352
        start_server(port)

    elif "--snapshot" in sys.argv:
        rprint(BANNER)
        source = sys.argv[sys.argv.index("--snapshot")+1] \
                 if sys.argv.index("--snapshot")+1 < len(sys.argv) \
                    and not sys.argv[sys.argv.index("--snapshot")+1].startswith("--") \
                 else "webcam"
        engine = ObserveEngine(show_trace=True)
        result = engine.snapshot(source)
        if result.get("thought"):
            rprint(Panel(result["thought"], border_style="green",
                        title=f"Observation | {' → '.join(result['pipeline'])}"))

    elif "--image" in sys.argv:
        rprint(BANNER)
        idx  = sys.argv.index("--image")
        path = sys.argv[idx+1] if idx+1 < len(sys.argv) else ""
        if not path: rprint("[yellow]Usage: --image <path>[/yellow]"); return
        engine = ObserveEngine(show_trace=True)
        result = engine.snapshot("file", path)
        if result.get("thought"):
            rprint(Panel(result["thought"], border_style="green", title=path))

    elif "--watch" in sys.argv:
        rprint(BANNER)
        idx      = sys.argv.index("--watch")
        interval = int(sys.argv[idx+1]) \
                   if idx+1 < len(sys.argv) and sys.argv[idx+1].isdigit() \
                   else WATCH_INTERVAL
        source   = "webcam"
        if "--source" in sys.argv:
            source = sys.argv[sys.argv.index("--source")+1]
        ObserveEngine(show_trace=True).watch(source=source, interval=interval)

    elif "--compare" in sys.argv:
        rprint(BANNER)
        idx = sys.argv.index("--compare")
        if idx+2 < len(sys.argv):
            ObserveEngine(show_trace=True).compare(sys.argv[idx+1], sys.argv[idx+2])

    else:
        rprint(BANNER)
        interactive()

if __name__ == "__main__":
    main()
