#!/usr/bin/env python3
"""
FORGE SHERLOCK VIDEO — The Screening Room
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Holmes watches your video. Observes everything.
Builds deduction chains from frames, behavior, audio.
Finds what you walked past.

Modules:
  🎬 Frame Extractor       — key frames, scene changes, motion spikes
  👁  Visual Observer       — Holmes observation on every frame
  🏃 Behavioral Tracker    — gait, pace, hesitation, path across time
  😐 Micro-Expression Scan — stress, deception, emotional state
  🌍 Environment Reader    — spatial context, anomalies, what changed
  🔊 Audio Analyzer        — speech patterns, pauses, stress, background
  ⏱️  Behavioral Timeline   — chronological deduction map
  🔍 Reflection & Shadow   — hidden context in surfaces and light
  ⚡ Contradiction Hunter   — video vs claimed alibi/testimony
  🎯 Final Deduction       — the complete Holmes verdict

Usage:
  python forge_sherlock_video.py --video interview.mp4
  python forge_sherlock_video.py --video crime_scene.mp4 --mode full
  python forge_sherlock_video.py --video testimony.mp4 --mode deception
  python forge_sherlock_video.py --video surveillance.mp4 --mode behavioral
  python forge_sherlock_video.py --server
"""

import sys, os, re, json, time, base64, hashlib, threading, tempfile
from pathlib import Path
from datetime import datetime
from io import BytesIO

# ── Dependencies ──────────────────────────────────────────────────────────────
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import numpy as np
    NP_AVAILABLE = True
except ImportError:
    NP_AVAILABLE = False

try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True

    def ai_call(prompt, system="", max_tokens=2000):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or HOLMES_SYSTEM,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text

    def ai_vision(prompt, image_blocks, system="", max_tokens=2000):
        content = image_blocks + [{"type":"text","text":prompt}]
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or HOLMES_SYSTEM,
            messages=[{"role":"user","content":content}]
        )
        return r.content[0].text

    def ai_json(prompt, system="", max_tokens=800):
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
    def ai_call(p,s="",m=2000): return "Install anthropic: pip install anthropic"
    def ai_vision(p,imgs,s="",m=2000): return "Install anthropic."
    def ai_json(p,s="",m=800): return None

# ── Rich ──────────────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich import box as rbox
    RICH    = True
    console = Console()
    rprint  = console.print
except ImportError:
    RICH = False
    def rprint(x,**kw): print(re.sub(r"\[/?[^\]]*\]","",str(x)))

# ── System prompts ─────────────────────────────────────────────────────────────
HOLMES_SYSTEM = """You are Sherlock Holmes analyzing video evidence.

You observe what others miss:
- Micro-behaviors (hesitation, eye movement, weight shifts)
- Environmental context (spatial layout, lighting, objects)
- Temporal patterns (timing, pace, sequence of events)
- Reflections and shadows revealing hidden information
- What is ABSENT that should be present
- What is PRESENT that should be absent

Format every deduction as:
OBSERVATION: [exact detail]
  → INFERENCE: [what this implies]
    → CONCLUSION: [deduction] [X% confidence]
      ELIMINATES: [what this rules out]
      NEXT: [what to verify]

Be specific. Be precise. Show every reasoning step."""

# ── Paths ─────────────────────────────────────────────────────────────────────
VIDEO_DIR   = Path("forge_sherlock_video")
FRAMES_DIR  = VIDEO_DIR / "frames"
CASES_DIR   = VIDEO_DIR / "cases"
VIDEO_DIR.mkdir(exist_ok=True)
FRAMES_DIR.mkdir(exist_ok=True)
CASES_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# 📦 VIDEO CASE
# ══════════════════════════════════════════════════════════════════════════════

class VideoCase:
    def __init__(self, video_path, mode="full", context=""):
        self.case_id       = hashlib.md5(f"{video_path}{time.time()}".encode()).hexdigest()[:8]
        self.video_path    = str(video_path)
        self.mode          = mode
        self.context       = context
        self.created       = datetime.now().isoformat()

        # Extracted data
        self.frames        = []        # list of FrameData
        self.audio_text    = ""        # full transcript
        self.audio_analysis= ""        # Holmes audio analysis
        self.duration_s    = 0
        self.fps           = 0
        self.total_frames  = 0

        # Analysis results
        self.observations  = []        # per-frame observations
        self.behavioral_timeline = []  # chronological events
        self.expressions   = []        # micro-expression findings
        self.environment   = ""        # spatial analysis
        self.reflections   = ""        # reflection/shadow findings
        self.contradictions= ""        # vs alibi/testimony
        self.deduction_chains = []     # reasoning chains
        self.final_verdict = ""        # the Holmes monologue

        # Metadata
        self.significant_frames = []   # timestamps of key moments
        self.confidence    = 0
        self.processing_log= []

    def log(self, message, level="info"):
        entry = {"ts": datetime.now().isoformat(), "message": message, "level": level}
        self.processing_log.append(entry)
        color = {"info":"dim","success":"green","warning":"yellow","error":"red"}.get(level,"dim")
        rprint(f"  [{color}]{message}[/{color}]")

    def to_dict(self):
        return {
            "case_id":           self.case_id,
            "video_path":        self.video_path,
            "mode":              self.mode,
            "created":           self.created,
            "duration_s":        self.duration_s,
            "fps":               self.fps,
            "frames_analyzed":   len(self.frames),
            "audio_text":        self.audio_text[:500],
            "observations":      self.observations[:5],
            "behavioral_timeline":self.behavioral_timeline,
            "environment":       self.environment[:300],
            "contradictions":    self.contradictions[:300],
            "final_verdict":     self.final_verdict[:500],
            "confidence":        self.confidence,
            "significant_frames":self.significant_frames,
        }

    def save(self):
        fp = CASES_DIR / f"video_{self.case_id}.json"
        fp.write_text(json.dumps(self.to_dict(), indent=2, default=str))
        return fp

class FrameData:
    def __init__(self, frame_num, timestamp_s, image_b64, motion_score=0):
        self.frame_num    = frame_num
        self.timestamp_s  = timestamp_s
        self.timestamp_str= f"{int(timestamp_s//60):02d}:{int(timestamp_s%60):02d}.{int((timestamp_s%1)*10)}"
        self.image_b64    = image_b64
        self.motion_score = motion_score
        self.observation  = ""
        self.expressions  = {}
        self.significance = 0
        self.flags        = []

    def to_image_block(self):
        return {
            "type": "image",
            "source": {
                "type":       "base64",
                "media_type": "image/jpeg",
                "data":       self.image_b64
            }
        }

# ══════════════════════════════════════════════════════════════════════════════
# 🎬 MODULE 1: FRAME EXTRACTOR
# ══════════════════════════════════════════════════════════════════════════════

def extract_frames(video_path, case, max_frames=20, mode="smart"):
    """
    Extract key frames from video.
    Modes:
      smart    — scene changes + motion spikes + regular intervals
      interval — every N seconds
      motion   — only high-motion frames
    """
    case.log(f"Extracting frames from {Path(video_path).name}...")

    if not CV2_AVAILABLE:
        case.log("OpenCV not available — install: pip install opencv-python", "warning")
        return _extract_frames_fallback(video_path, case, max_frames)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        case.log(f"Cannot open video: {video_path}", "error")
        return []

    fps          = cap.get(cv2.CAP_PROP_FPS) or 25
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration     = total_frames / fps

    case.fps          = fps
    case.total_frames = total_frames
    case.duration_s   = duration

    case.log(f"Video: {duration:.1f}s | {fps:.0f}fps | {total_frames} frames")

    # Calculate extraction strategy
    interval = max(1, int(total_frames / max_frames))
    frames   = []
    prev_frame = None

    frame_indices = list(range(0, total_frames, interval))[:max_frames]

    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue

        timestamp = idx / fps

        # Motion score vs previous frame
        motion_score = 0
        if prev_frame is not None and NP_AVAILABLE:
            diff         = cv2.absdiff(prev_frame, frame)
            motion_score = float(np.mean(diff))

        prev_frame = frame.copy()

        # Convert to base64 JPEG for Claude vision
        b64 = _frame_to_b64(frame)
        if not b64:
            continue

        fd = FrameData(idx, timestamp, b64, motion_score)
        frames.append(fd)

        # Mark high-motion frames as potentially significant
        if motion_score > 15:
            fd.flags.append("high_motion")
            fd.significance += 20

    cap.release()
    case.log(f"Extracted {len(frames)} frames for analysis", "success")
    return frames

def _extract_frames_fallback(video_path, case, max_frames=20):
    """Fallback when OpenCV not available — try ffmpeg."""
    try:
        import subprocess
        out_dir = FRAMES_DIR / case.case_id
        out_dir.mkdir(exist_ok=True)

        # Use ffmpeg to extract frames
        result = subprocess.run([
            "ffmpeg", "-i", str(video_path),
            "-vf", f"fps=1/3",  # 1 frame every 3 seconds
            "-q:v", "3",
            str(out_dir / "frame_%04d.jpg")
        ], capture_output=True, timeout=60)

        frames = []
        for fp in sorted(out_dir.glob("frame_*.jpg"))[:max_frames]:
            with open(fp, "rb") as f:
                b64 = base64.standard_b64encode(f.read()).decode()
            frame_num = int(fp.stem.split("_")[1])
            timestamp = frame_num * 3.0
            frames.append(FrameData(frame_num, timestamp, b64, 0))

        case.log(f"Extracted {len(frames)} frames via ffmpeg", "success")
        return frames
    except Exception as e:
        case.log(f"Frame extraction failed: {e}", "error")
        return []

def _frame_to_b64(frame):
    """Convert OpenCV frame to base64 JPEG."""
    try:
        if PIL_AVAILABLE:
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img   = Image.fromarray(rgb)
            # Resize for API efficiency
            img.thumbnail((800, 600), Image.LANCZOS)
            buf   = BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.standard_b64encode(buf.getvalue()).decode()
        else:
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return base64.standard_b64encode(buf.tobytes()).decode()
    except:
        return None

# ══════════════════════════════════════════════════════════════════════════════
# 👁️ MODULE 2: VISUAL OBSERVER
# ══════════════════════════════════════════════════════════════════════════════

VISUAL_OBS_PROMPT = """You are Sherlock Holmes examining frame {timestamp} of a video.

Context: {context}
Frame position: {position} of {total} frames
Motion level: {motion}

Apply the complete Holmes observation method to this single frame:

## WHAT I SEE
Every visible element. People, objects, text, numbers, symbols, clothing details.
Miss nothing — especially background details others would ignore.

## SPATIAL ANALYSIS
Room/environment layout. What this space is normally used for vs how it appears now.
Any disturbance to normal arrangement.

## PEOPLE & BEHAVIOR
Body language, posture, gaze direction, hand position.
What emotional/physical state does this suggest?

## REFLECTIONS & SHADOWS
What appears in windows, mirrors, screens, polished surfaces?
What do shadow angles reveal about timing or hidden elements?

## NOTABLE ABSENCES
What should be here but isn't?
What appears to have been removed or concealed?

## SIGNIFICANCE: {motion_label}
Rate this frame: LOW / MEDIUM / HIGH / CRITICAL
One sentence on why.

## DEDUCTION SEED
The single most useful observation from this frame for building a case."""

def observe_frames(frames, case, batch_size=3):
    """Run Holmes visual observation on key frames."""
    case.log(f"Running visual observation on {len(frames)} frames...")

    # Prioritize: high motion + evenly spaced
    priority_frames = sorted(frames, key=lambda f: f.significance + f.motion_score, reverse=True)
    # Always include first, last, and highest significance
    selected = []
    if frames: selected.append(frames[0])
    selected.extend(priority_frames[:min(8, len(priority_frames))])
    if frames and frames[-1] not in selected: selected.append(frames[-1])
    # Deduplicate preserving order
    seen = set()
    selected_unique = []
    for f in selected:
        if f.frame_num not in seen:
            seen.add(f.frame_num)
            selected_unique.append(f)
    selected = selected_unique[:10]

    observations = []
    for i, frame in enumerate(selected):
        motion_label = (
            "CRITICAL — major motion event" if frame.motion_score > 30 else
            "HIGH — significant movement"   if frame.motion_score > 15 else
            "MEDIUM — moderate activity"    if frame.motion_score > 5  else
            "LOW — static scene"
        )

        prompt = VISUAL_OBS_PROMPT.format(
            timestamp   = frame.timestamp_str,
            context     = case.context or "No prior context.",
            position    = i+1,
            total       = len(selected),
            motion      = f"{frame.motion_score:.1f}",
            motion_label= motion_label,
        )

        result = ai_vision(prompt, [frame.to_image_block()])
        frame.observation = result
        frame.significance+= 50 if "CRITICAL" in result or "HIGH" in result else 20

        # Extract structured findings
        obs_data = ai_json(
            f"From this observation:\n{result[:1000]}\n\n"
            'Extract key findings as JSON:\n'
            '{"significance":"high|medium|low","people_count":1,"behavioral_flags":[],'
            '"environment_flags":[],"deduction_seed":"key observation","timestamp":"MM:SS"}',
            "Reply ONLY with JSON.", 300
        )

        entry = {
            "timestamp":    frame.timestamp_str,
            "frame_num":    frame.frame_num,
            "observation":  result,
            "motion_score": frame.motion_score,
            "structured":   obs_data or {},
        }
        observations.append(entry)

        if obs_data and obs_data.get("significance") in ("high","critical"):
            case.significant_frames.append(frame.timestamp_str)

        rprint(f"  [dim]Frame {frame.timestamp_str}: {result[:80]}...[/dim]")

    case.observations = observations
    case.log(f"Visual observation complete. {len(case.significant_frames)} significant moments.", "success")
    return observations

# ══════════════════════════════════════════════════════════════════════════════
# 🏃 MODULE 3: BEHAVIORAL TRACKER
# ══════════════════════════════════════════════════════════════════════════════

BEHAVIORAL_PROMPT = """You are Sherlock Holmes tracking behavior across a video sequence.

Video: {duration}s total
Context: {context}

Frame sequence observations:
{observations}

Build the complete BEHAVIORAL TIMELINE.
Every significant action, mapped to time, with deduction chains.

## BEHAVIORAL TIMELINE

For each significant moment:
[MM:SS] — BEHAVIOR: [exact description]
  BASELINE: [is this normal pace/movement for this person?]
  DEVIATION: [how does it differ from earlier behavior?]
  → INFERENCE: [what this behavioral shift implies]
    → CONCLUSION: [deduction] [X% confidence]

## GAIT & MOVEMENT ANALYSIS
Pace changes (faster = urgency/fear, slower = deliberate/familiar)
Favored side, hesitation points, path choices.
What the movement pattern reveals about familiarity with this space.

## STRESS INDICATORS ACROSS TIME
Moments of elevated physical stress visible in body language.
Timeline of when stress peaks — what triggered each peak?

## THE BEHAVIORAL SIGNATURE
This person's unique pattern.
What they do when comfortable vs when under pressure.
The moment the mask slipped.

## KEY BEHAVIORAL DEDUCTIONS
The 3 most significant behavioral findings, each with full chain."""

def analyze_behavior(case):
    """Build behavioral timeline from all frame observations."""
    case.log("Building behavioral timeline...")

    if not case.observations:
        case.log("No frame observations available", "warning")
        return ""

    obs_text = "\n\n".join(
        f"[{o['timestamp']}] Motion:{o['motion_score']:.1f}\n{o['observation'][:400]}"
        for o in case.observations
    )

    result = ai_call(
        BEHAVIORAL_PROMPT.format(
            duration     = f"{case.duration_s:.1f}",
            context      = case.context or "No prior context.",
            observations = obs_text[:4000],
        ),
        max_tokens=2500
    )

    # Parse timeline events
    timeline_data = ai_json(
        f"Extract behavioral timeline from:\n{result[:2000]}\n\n"
        'JSON: {"events":[{"time":"MM:SS","behavior":"description","inference":"implication",'
        '"confidence":80,"significance":"high|medium|low","stress_level":"high|medium|low"}]}',
        "Reply ONLY with JSON.", 500
    )

    if timeline_data:
        case.behavioral_timeline = timeline_data.get("events", [])

    case.log(f"Behavioral timeline: {len(case.behavioral_timeline)} events mapped", "success")
    return result

# ══════════════════════════════════════════════════════════════════════════════
# 😐 MODULE 4: MICRO-EXPRESSION SCANNER
# ══════════════════════════════════════════════════════════════════════════════

EXPRESSION_PROMPT = """You are Sherlock Holmes analyzing facial micro-expressions and body language.

Frame at {timestamp}:
Context: {context}
Previous emotional baseline: {baseline}

Focus exclusively on:

## FACIAL MICRO-EXPRESSIONS
Brief involuntary expressions (< 0.5 seconds in real time).
Look for: disgust, fear, contempt, surprise, anger bleeding through.
Where visible — around eyes, mouth corners, brow.

## EYE BEHAVIOR
Gaze direction. Blink rate anomalies. Pupil dilation if visible.
Where are they NOT looking that they should be?

## VOCAL INDICATORS (if this is a testimony/interview frame)
Mouth tension before speaking. Jaw set. Breath indicators.

## BODY LANGUAGE
Shoulder position (defensive = raised/forward).
Hand visibility (hidden hands = concealment mindset).
Weight distribution (ready to leave vs settled).

## EMOTIONAL STATE ASSESSMENT
Current: [calm/tense/fearful/angry/contemptuous/surprised]
Compared to baseline: [same/elevated/decreased]
Authenticity: [genuine/performed/suppressed]

## DECEPTION INDICATORS
Specific physical markers visible in this frame that correlate
with deception or concealment.
Rate: NONE / POSSIBLE / PROBABLE / STRONG

## DEDUCTION
OBSERVATION: [specific physical detail]
  → INFERENCE: [psychological implication]
    → CONCLUSION: [what this reveals] [X%]"""

def scan_expressions(frames, case):
    """Scan for micro-expressions and behavioral tells."""
    case.log("Scanning for micro-expressions and behavioral tells...")

    # Focus on interview/testimony frames — medium/low motion (person speaking)
    interview_frames = [
        f for f in frames
        if f.motion_score < 20  # relatively static — person speaking
    ][:6]

    if not interview_frames:
        interview_frames = frames[:4]

    expressions = []
    baseline    = "Unknown — first frame"

    for i, frame in enumerate(interview_frames):
        prompt = EXPRESSION_PROMPT.format(
            timestamp = frame.timestamp_str,
            context   = case.context or "Testimony/interview analysis.",
            baseline  = baseline,
        )

        result = ai_vision(prompt, [frame.to_image_block()])
        frame.expressions = {"analysis": result, "timestamp": frame.timestamp_str}

        # Update baseline from first analysis
        if i == 0:
            baseline = result[:200]

        # Extract deception score
        score_data = ai_json(
            f"From this expression analysis:\n{result[:800]}\n\n"
            'JSON: {"deception_level":"none|possible|probable|strong",'
            '"stress_level":"low|medium|high","emotional_state":"calm|tense|fearful|other",'
            '"key_indicator":"main finding in 10 words"}',
            "Reply ONLY with JSON.", 200
        )

        expressions.append({
            "timestamp":      frame.timestamp_str,
            "analysis":       result,
            "scores":         score_data or {},
        })

        level = (score_data or {}).get("deception_level","unknown")
        if level in ("probable","strong"):
            case.significant_frames.append(f"{frame.timestamp_str} [DECEPTION:{level.upper()}]")

    case.expressions = expressions
    case.log(f"Expression scan: {len(expressions)} frames analyzed", "success")
    return expressions

# ══════════════════════════════════════════════════════════════════════════════
# 🌍 MODULE 5: ENVIRONMENT READER
# ══════════════════════════════════════════════════════════════════════════════

ENV_PROMPT = """You are Sherlock Holmes reading the environment across this entire video.

Duration: {duration}s
All frame observations:
{observations}

Perform a complete environmental analysis:

## THE SPACE ITSELF
What is this location? What is it normally used for?
Layout, furniture arrangement, access points.
Signs of recent disturbance or deliberate arrangement.

## CHANGES ACROSS TIME
What changed in the environment between early and late frames?
Objects moved, added, or removed.
Lighting changes (time of day? deliberate obscuring?).

## ENVIRONMENT VS CLAIMED CONTEXT
If this is claimed to be [context]: {context}
Does the physical environment support or contradict this?

## BACKGROUND DETAILS
Text visible on screens, papers, walls.
Calendars, clocks, dates visible — do they match the claimed time?
Brand names, location indicators visible accidentally.

## THE HIDDEN STORY IN THE SPACE
What does this environment reveal about the people who use it?
What was prepared? What was concealed? What was overlooked?

## ENVIRONMENTAL DEDUCTIONS
Top 3 environmental observations with full chains:
OBSERVATION → INFERENCE → CONCLUSION [confidence%]"""

def read_environment(case):
    """Full environmental analysis across all frames."""
    case.log("Reading environment...")

    obs_text = "\n\n".join(
        f"[{o['timestamp']}]\n{o['observation'][:300]}"
        for o in case.observations
    )

    # Use first and last frame images for comparison
    key_frames = []
    if case.frames:
        key_frames.append(case.frames[0].to_image_block())
        if len(case.frames) > 1:
            key_frames.append(case.frames[-1].to_image_block())

    prompt = ENV_PROMPT.format(
        duration     = f"{case.duration_s:.1f}",
        observations = obs_text[:3000],
        context      = case.context or "No prior context.",
    )

    if key_frames:
        result = ai_vision(prompt, key_frames)
    else:
        result = ai_call(prompt)

    case.environment = result
    case.log("Environment analysis complete", "success")
    return result

# ══════════════════════════════════════════════════════════════════════════════
# 🔊 MODULE 6: AUDIO ANALYZER
# ══════════════════════════════════════════════════════════════════════════════

AUDIO_PROMPT = """You are Sherlock Holmes analyzing speech patterns from a transcript.

Speaker transcript:
{transcript}

Context: {context}

## SPEECH PATTERN ANALYSIS

### RESPONSE LATENCY
Pauses before answering questions.
[Average response: X seconds | Deviations: which questions caused longer pauses?]
Long pauses = fabrication time vs recall time.

### LINGUISTIC DECEPTION MARKERS
- Distancing language: "the incident" vs "what I did"
- Over-qualification: "I swear", "honestly", "to be truthful"
- Unnecessary precision: exact times/details in areas that don't matter
- Vagueness: deliberate imprecision in areas that should be clear
- Tense inconsistencies: switching past/present when recounting events
- Third-person self-reference under stress

### TOPIC AVOIDANCE
Questions they answered differently from others.
Topics where vocabulary suddenly simplified or complicated.
Where they redirected the conversation.

### BACKGROUND AUDIO
Environmental sounds audible.
Do they match the claimed location?
Any sounds that shouldn't be there?

### SPEECH TIMELINE
Most significant moments in the transcript with Holmes deduction chains.

### VOCAL VERDICT
Truth/Deception indicators: STRONG / MODERATE / WEAK / NONE
Confidence: X%
The single phrase that reveals the most."""

def analyze_audio(case):
    """Analyze audio track — transcript + speech patterns."""
    case.log("Analyzing audio track...")

    # Try to extract audio with moviepy
    transcript = _extract_audio_transcript(case.video_path, case)

    if not transcript:
        case.log("No audio transcript available — analyzing from visual cues only", "warning")
        return ""

    case.audio_text = transcript
    result = ai_call(
        AUDIO_PROMPT.format(
            transcript = transcript[:3000],
            context    = case.context or "No prior context.",
        ),
        max_tokens=2000
    )
    case.audio_analysis = result
    case.log("Audio analysis complete", "success")
    return result

def _extract_audio_transcript(video_path, case):
    """Extract and transcribe audio from video."""
    # Try speech_recognition
    try:
        import speech_recognition as sr
        import subprocess

        # Extract audio to wav using ffmpeg
        wav_path = VIDEO_DIR / f"{case.case_id}_audio.wav"
        subprocess.run([
            "ffmpeg", "-i", str(video_path),
            "-ac", "1", "-ar", "16000", "-vn",
            str(wav_path), "-y"
        ], capture_output=True, timeout=30)

        if wav_path.exists():
            recognizer = sr.Recognizer()
            with sr.AudioFile(str(wav_path)) as source:
                audio = recognizer.record(source)
            transcript = recognizer.recognize_google(audio)
            wav_path.unlink(missing_ok=True)
            case.log(f"Transcript: {len(transcript)} chars", "success")
            return transcript

    except Exception as e:
        case.log(f"Audio extraction: {str(e)[:60]}", "warning")

    # Try OpenAI Whisper
    try:
        import whisper
        model      = whisper.load_model("base")
        result     = model.transcribe(str(video_path))
        transcript = result["text"]
        case.log(f"Whisper transcript: {len(transcript)} chars", "success")
        return transcript
    except Exception as e:
        case.log(f"Whisper: {str(e)[:60]}", "warning")

    return ""

# ══════════════════════════════════════════════════════════════════════════════
# 🔍 MODULE 7: REFLECTION & SHADOW ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

REFLECTION_PROMPT = """You are Sherlock Holmes examining reflections, shadows, and hidden visual information.

This is frame {timestamp} from a video investigation.
Context: {context}

Look with extreme care for:

## REFLECTIONS
Windows, mirrors, screens, polished surfaces, glasses, eyes.
What is visible in reflections that is NOT in the main scene?
People, objects, text, rooms reflected — any additional context?

## SHADOW ANALYSIS  
Shadow angles — what time of day do they suggest?
Does claimed time match shadow angle? (inconsistency = lie about timing)
Shadows revealing objects/people outside the frame.
Shadow shapes suggesting hidden elements.

## SCREEN & TEXT CONTENT
Computer screens, phones, documents partially visible.
Any readable text, URLs, dates, names, addresses.
Even blurred or partially visible — what can be inferred?

## LIGHTING FORENSICS
Natural vs artificial light.
Multiple light sources — what does this suggest about the space?
Lighting changes between frames — time passing or scene staging?

## WHAT THE CAMERA MISSED
Based on reflections and shadows, what exists just outside frame?
Is the camera placement deliberate? What is it avoiding?

## HIDDEN CONTEXT DEDUCTIONS
OBSERVATION: [reflection/shadow detail]
  → INFERENCE: [what this reveals]
    → CONCLUSION: [hidden information discovered] [X%]"""

def analyze_reflections(frames, case):
    """Hunt for hidden information in reflections and shadows."""
    case.log("Analyzing reflections and shadows...")

    # Use the clearest, most static frames
    clear_frames = sorted(frames, key=lambda f: f.motion_score)[:4]
    findings     = []

    for frame in clear_frames:
        prompt = REFLECTION_PROMPT.format(
            timestamp = frame.timestamp_str,
            context   = case.context or "No prior context.",
        )
        result = ai_vision(prompt, [frame.to_image_block()])

        # Check if anything significant was found
        significant = any(w in result.lower() for w in
            ["visible","reflects","shadow reveals","readable","text shows",
             "person","screen","document","inconsist"])

        if significant:
            findings.append({
                "timestamp": frame.timestamp_str,
                "findings":  result,
            })
            rprint(f"  [yellow]⚡ Reflection finding at {frame.timestamp_str}[/yellow]")

    case.reflections = "\n\n".join(
        f"[{f['timestamp']}]\n{f['findings']}" for f in findings
    ) if findings else "No significant hidden information found in reflections."

    case.log(f"Reflection analysis: {len(findings)} findings", "success")
    return case.reflections

# ══════════════════════════════════════════════════════════════════════════════
# ⚡ MODULE 8: CONTRADICTION HUNTER
# ══════════════════════════════════════════════════════════════════════════════

CONTRA_PROMPT = """You are Sherlock Holmes hunting contradictions between video evidence and claims.

VIDEO EVIDENCE:
{video_summary}

CLAIMED CONTEXT / ALIBI / TESTIMONY:
{claims}

Hunt for every contradiction:

## TIMELINE CONTRADICTIONS
Does the video timeline match claimed times?
Shadow angles, clock visibility, lighting — do they confirm or deny claimed time?

## LOCATION CONTRADICTIONS
Does the environment match the claimed location?
Background details, sounds, visible text — any inconsistencies?

## BEHAVIORAL CONTRADICTIONS
Does the person behave as someone in the claimed situation would?
Emotional response appropriate? Knowledge they "shouldn't" have?
Familiarity with space they claim not to know?

## PHYSICAL CONTRADICTIONS
Objects present that shouldn't be. Objects absent that should be.
Clothing, appearance inconsistencies vs claimed timeline.

## THE IMPOSSIBLE DETAIL
The single fact in the video that CANNOT BE TRUE
if the claimed story is accurate.

## VERDICT ON THE CLAIMS
CONSISTENT / PARTIALLY CONSISTENT / CONTRADICTED / IMPOSSIBLE
Confidence: X%
The one piece of video evidence that decides it."""

def hunt_video_contradictions(case, claims=""):
    """Cross-reference video evidence against alibi/testimony."""
    case.log("Hunting contradictions between video and claims...")

    video_summary = f"""
Duration: {case.duration_s:.1f}s
Significant moments: {', '.join(case.significant_frames[:5])}
Environment: {case.environment[:400]}
Behavioral timeline: {json.dumps(case.behavioral_timeline[:5], default=str)}
Audio: {case.audio_text[:300]}
"""

    result = ai_call(
        CONTRA_PROMPT.format(
            video_summary = video_summary,
            claims        = claims or case.context or "No specific claims provided.",
        ),
        max_tokens=2000
    )
    case.contradictions = result
    case.log("Contradiction analysis complete", "success")
    return result

# ══════════════════════════════════════════════════════════════════════════════
# 🔗 MODULE 9: DEDUCTION CHAIN BUILDER
# ══════════════════════════════════════════════════════════════════════════════

CHAIN_PROMPT = """You are Sherlock Holmes. Build explicit deduction chains from video evidence.

All video findings:
{all_findings}

Build the 5 most powerful deduction chains from this video evidence.
Each chain must start from a specific observable moment in the video.

Format:
[MM:SS] OBSERVATION: [exact visual/behavioral detail]
  → INFERENCE 1: [first logical step]
    → INFERENCE 2: [second step]
      → CONCLUSION: [final deduction]
        CONFIDENCE: X%
        ELIMINATES: [what this rules out]
        REQUIRES: [what would confirm this]

Then:

## CONVERGING CHAINS
Where do multiple chains point to the same conclusion?
(These are your strongest deductions)

## THE MASTER DEDUCTION
The single most powerful chain — built from multiple converging lines of evidence.
This is what you'd present in court.

## WHAT THE VIDEO CANNOT TELL US
The gaps. What we still don't know.
What footage would resolve the remaining uncertainty."""

def build_video_chains(case):
    """Build complete deduction chains from all video evidence."""
    case.log("Building deduction chains...")

    all_findings = f"""
VISUAL OBSERVATIONS ({len(case.observations)} frames):
{chr(10).join(o['observation'][:300] for o in case.observations[:4])}

BEHAVIORAL TIMELINE:
{json.dumps(case.behavioral_timeline[:8], default=str, indent=2)}

ENVIRONMENT:
{case.environment[:500]}

EXPRESSIONS:
{chr(10).join(e['analysis'][:200] for e in case.expressions[:3])}

REFLECTIONS:
{case.reflections[:400]}

AUDIO:
{case.audio_analysis[:400]}

CONTRADICTIONS:
{case.contradictions[:400]}
"""

    result = ai_call(
        CHAIN_PROMPT.format(all_findings=all_findings[:4000]),
        max_tokens=3000
    )
    case.deduction_chains = [result]
    case.log("Deduction chains complete", "success")
    return result

# ══════════════════════════════════════════════════════════════════════════════
# 🎯 MODULE 10: FINAL DEDUCTION
# ══════════════════════════════════════════════════════════════════════════════

VERDICT_PROMPT = """You are Sherlock Holmes. Deliver the final video analysis verdict.

This is the moment. The complete Holmes monologue.
Based on {duration}s of video evidence.

All evidence:
{evidence_summary}

Deliver the complete verdict:

## THE SCENE (set the moment)
Holmes stands. The evidence is assembled.

## THE VIDEO TELLS ME
Walk through the most significant findings chronologically.
Frame by frame where it matters. Pattern across the whole where it doesn't.

## THE CHAIN OF PROOF
The unbroken chain from first frame to final conclusion.
Number every link. No gaps.

1. At [time], I observed [X]
2. Which combined with [Y at time Z]
3. Which the audio confirmed when [A]
4. Which environment analysis revealed [B]
5. Which the expression at [time] sealed...
[continue until conclusion]
N. THEREFORE: [THE TRUTH]

## THE VERDICT
State it plainly. What happened. Who. When. How.

## CONFIDENCE: X%
What would change my conclusion.

## WHAT THE VIDEO DELIBERATELY CONCEALED
What someone tried to hide — and failed.

## ELEMENTARY
The detail everyone else missed.
The reason this was, in fact, elementary."""

def deliver_video_verdict(case):
    """Deliver the complete Holmes video verdict."""
    case.log("Delivering final video verdict...")

    evidence_summary = f"""
Video: {case.duration_s:.1f}s | {len(case.frames)} frames analyzed
Significant moments: {', '.join(case.significant_frames)}

KEY DEDUCTIONS:
{case.deduction_chains[-1][:800] if case.deduction_chains else 'None'}

BEHAVIORAL PATTERNS:
{json.dumps(case.behavioral_timeline[:5], default=str)}

CONTRADICTIONS FOUND:
{case.contradictions[:400]}

AUDIO ANALYSIS:
{case.audio_analysis[:300]}

ENVIRONMENT:
{case.environment[:300]}
"""

    result = ai_call(
        VERDICT_PROMPT.format(
            duration         = f"{case.duration_s:.1f}",
            evidence_summary = evidence_summary[:4000],
        ),
        max_tokens=3000
    )

    case.final_verdict = result

    # Extract confidence
    m = re.search(r"CONFIDENCE[:\s]+(\d{1,3})%", result, re.IGNORECASE)
    case.confidence = int(m.group(1)) if m else 75

    case.log(f"Final verdict delivered. Confidence: {case.confidence}%", "success")
    return result

# ══════════════════════════════════════════════════════════════════════════════
# 🚀 MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

MODES = {
    "full":        ["extract","observe","behavior","expressions","environment",
                   "audio","reflections","contradictions","chains","verdict"],
    "behavioral":  ["extract","observe","behavior","expressions","chains","verdict"],
    "deception":   ["extract","observe","expressions","audio","contradictions","verdict"],
    "environment": ["extract","observe","environment","reflections","chains","verdict"],
    "quick":       ["extract","observe","behavior","verdict"],
    "audio":       ["extract","audio","contradictions","verdict"],
}

def analyze_video(video_path, mode="full", context="", claims=""):
    """Run the full Sherlock video analysis pipeline."""
    video_path = Path(video_path)
    if not video_path.exists():
        rprint(f"[red]Video not found: {video_path}[/red]")
        return None

    rprint(f"\n[yellow bold]🎬 SHERLOCK VIDEO ANALYSIS[/yellow bold]")
    rprint(f"  [bold]File:[/bold]    {video_path.name}")
    rprint(f"  [bold]Mode:[/bold]    {mode}")
    rprint(f"  [bold]Context:[/bold] {context or 'None'}\n")

    case     = VideoCase(video_path, mode, context)
    steps    = MODES.get(mode, MODES["full"])
    results  = {}

    step_map = {
        "extract":       lambda: extract_frames(video_path, case),
        "observe":       lambda: observe_frames(case.frames, case),
        "behavior":      lambda: analyze_behavior(case),
        "expressions":   lambda: scan_expressions(case.frames, case),
        "environment":   lambda: read_environment(case),
        "audio":         lambda: analyze_audio(case),
        "reflections":   lambda: analyze_reflections(case.frames, case),
        "contradictions":lambda: hunt_video_contradictions(case, claims),
        "chains":        lambda: build_video_chains(case),
        "verdict":       lambda: deliver_video_verdict(case),
    }

    for step in steps:
        rprint(f"\n[bold yellow]━━━ {step.upper()} ━━━[/bold yellow]")
        fn = step_map.get(step)
        if not fn:
            continue
        try:
            result = fn()
            results[step] = result
            # Store frames from extract step
            if step == "extract":
                case.frames = result or []
        except Exception as e:
            case.log(f"Step {step} error: {e}", "error")

    # Print final verdict
    rprint(f"\n[bold yellow]{'═'*60}[/bold yellow]")
    rprint(f"[bold]🎯 SHERLOCK VIDEO VERDICT[/bold]")
    rprint(f"[bold yellow]{'═'*60}[/bold yellow]")

    if case.final_verdict:
        rprint(Panel(case.final_verdict, border_style="yellow",
                     title=f"🎩 Holmes on {video_path.name}"))

    # Summary
    rprint(f"\n  [bold]Frames analyzed:[/bold]   {len(case.frames)}")
    rprint(f"  [bold]Significant moments:[/bold]{len(case.significant_frames)}")
    rprint(f"  [bold]Deduction chains:[/bold]  {len(case.deduction_chains)}")
    rprint(f"  [bold]Confidence:[/bold]        {case.confidence}%")

    # Save
    fp = case.save()
    rprint(f"  [bold]Case saved:[/bold]        {fp}")

    return case

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API SERVER
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7341):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    active_cases = {}
    jobs         = {}

    class VideoAPI(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_OPTIONS(self):
            self.send_response(200); self._cors(); self.end_headers()
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin","*")
            self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
            self.send_header("Access-Control-Allow-Headers","Content-Type")
        def _json(self, d, c=200):
            b = json.dumps(d, default=str).encode()
            self.send_response(c); self._cors()
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",len(b))
            self.end_headers(); self.wfile.write(b)
        def _body(self):
            n = int(self.headers.get("Content-Length",0))
            return json.loads(self.rfile.read(n)) if n else {}

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/status":
                self._json({"status":"online","ai":AI_AVAILABLE,
                            "cv2":CV2_AVAILABLE,"cases":len(active_cases)})
            elif path == "/api/cases":
                self._json({"cases":[c.to_dict() for c in active_cases.values()]})
            elif path.startswith("/api/case/"):
                cid = path.split("/")[-1]
                if cid in active_cases:
                    self._json(active_cases[cid].to_dict())
                else:
                    self._json({"error":"not found"},404)
            elif path == "/api/modes":
                self._json({"modes": list(MODES.keys()),
                            "steps": {k:v for k,v in MODES.items()}})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()

            if path == "/api/analyze":
                video_b64 = body.get("video_b64","")
                filename  = body.get("filename","upload.mp4")
                mode      = body.get("mode","full")
                context   = body.get("context","")
                claims    = body.get("claims","")

                if not video_b64:
                    self._json({"error":"video_b64 required"},400); return

                # Save uploaded video
                video_data = base64.b64decode(video_b64)
                tmp_path   = VIDEO_DIR / f"upload_{hashlib.md5(video_data[:100]).hexdigest()[:8]}_{filename}"
                tmp_path.write_bytes(video_data)

                job_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
                jobs[job_id] = {"status":"running","progress":0,"file":filename}

                def run_job():
                    try:
                        case = analyze_video(tmp_path, mode, context, claims)
                        if case:
                            active_cases[case.case_id] = case
                            jobs[job_id].update({
                                "status":    "complete",
                                "progress":  100,
                                "case_id":   case.case_id,
                                "confidence":case.confidence,
                                "verdict":   case.final_verdict[:300],
                                "significant_frames": case.significant_frames,
                            })
                        else:
                            jobs[job_id].update({"status":"error","error":"Analysis failed"})
                    except Exception as e:
                        jobs[job_id].update({"status":"error","error":str(e)})

                threading.Thread(target=run_job, daemon=True).start()
                self._json({"job_id":job_id,"status":"running","file":filename})

            elif path == "/api/status/job":
                job_id = body.get("job_id","")
                if job_id in jobs:
                    resp = dict(jobs[job_id])
                    if "case_id" in jobs[job_id] and jobs[job_id]["case_id"] in active_cases:
                        resp["case"] = active_cases[jobs[job_id]["case_id"]].to_dict()
                    self._json(resp)
                else:
                    self._json({"error":"job not found"},404)

            elif path == "/api/analyze/frames":
                # Analyze individual frames (base64 images)
                frames_b64 = body.get("frames",[])
                context    = body.get("context","")
                mode       = body.get("mode","quick")

                case = VideoCase("frames_upload", mode, context)
                case.duration_s = len(frames_b64) * 3.0
                case.fps        = 1/3

                case.frames = [
                    FrameData(i, i*3.0, f, 0)
                    for i, f in enumerate(frames_b64[:15])
                ]

                observations = observe_frames(case.frames, case)
                behavior     = analyze_behavior(case)
                verdict      = deliver_video_verdict(case)

                active_cases[case.case_id] = case
                self._json({
                    "case_id":           case.case_id,
                    "observations":      observations,
                    "behavioral_timeline":case.behavioral_timeline,
                    "verdict":           verdict,
                    "confidence":        case.confidence,
                    "significant_frames":case.significant_frames,
                })

            else:
                self._json({"error":"unknown endpoint"},404)

    server = HTTPServer(("0.0.0.0", port), VideoAPI)
    rprint(f"  [yellow]🎬 Sherlock Video API: http://localhost:{port}[/yellow]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# 🖥️ MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ┌─────────────────────────────────────────────────┐
  │   SHERLOCK VIDEO — The Screening Room           │
  │   "The world is full of obvious things which    │
  │    nobody by any chance ever observes."         │
  └─────────────────────────────────────────────────┘
[/yellow]"""

def main():
    if "--server" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7341
        rprint(BANNER)
        rprint(f"[yellow]Starting Sherlock Video server on port {port}...[/yellow]")
        start_server(port)
        return

    if "--video" in sys.argv:
        idx   = sys.argv.index("--video")
        video = sys.argv[idx+1] if idx+1 < len(sys.argv) else ""

        mode    = "full"
        context = ""
        claims  = ""

        if "--mode"    in sys.argv:
            mode    = sys.argv[sys.argv.index("--mode")+1]
        if "--context" in sys.argv:
            context = sys.argv[sys.argv.index("--context")+1]
        if "--claims"  in sys.argv:
            claims  = sys.argv[sys.argv.index("--claims")+1]

        if video:
            rprint(BANNER)
            analyze_video(video, mode, context, claims)
        else:
            rprint("[red]Specify --video <path>[/red]")
        return

    # Interactive
    rprint(BANNER)
    rprint(f"  [dim]CV2: {'✅' if CV2_AVAILABLE else '❌ pip install opencv-python'}[/dim]")
    rprint(f"  [dim]AI:  {'✅' if AI_AVAILABLE  else '❌ pip install anthropic'}[/dim]\n")

    rprint("[dim]Usage:[/dim]")
    rprint("  [yellow]python forge_sherlock_video.py --video file.mp4[/yellow]")
    rprint("  [yellow]python forge_sherlock_video.py --video file.mp4 --mode behavioral[/yellow]")
    rprint("  [yellow]python forge_sherlock_video.py --video file.mp4 --claims 'I was home'[/yellow]")
    rprint("  [yellow]python forge_sherlock_video.py --server[/yellow]")
    rprint(f"\n  Modes: {', '.join(MODES.keys())}")

if __name__ == "__main__":
    main()
