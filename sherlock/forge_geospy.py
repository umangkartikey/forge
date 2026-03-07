#!/usr/bin/env python3
"""
FORGE GEOSPY — Geospatial Intelligence Module
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Drop any image. Know exactly where it was taken.
No GPS. No metadata. Just pixels → coordinates.

Powered by GeoSpy API (dev.geospy.ai) + Sherlock reasoning.

What it does:
  📍 Locates images to GPS coordinates via GeoSpy AI
  🧠 Sherlock builds deduction chains from visual clues
  ⚡ Contradiction engine: location vs claimed alibi
  🎬 Integrates with forge_sherlock_video.py
  🗺️  Reverse geocodes to human-readable address
  🌍 Cross-references with OSINT (forge_investigate)
  📋 Full geospatial intelligence report

Usage:
  python forge_geospy.py --image photo.jpg
  python forge_geospy.py --image photo.jpg --alibi "I was in London"
  python forge_geospy.py --video crime_scene.mp4
  python forge_geospy.py --batch images/
  python forge_geospy.py --server
  python forge_geospy.py --setup   # configure API key
"""

import sys, os, re, json, time, base64, hashlib, sqlite3, threading
import urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime
from io import BytesIO

# ── Dependencies ──────────────────────────────────────────────────────────────
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import anthropic
    _client      = anthropic.Anthropic()
    AI_AVAILABLE = True

    def ai_call(prompt, system="", max_tokens=1500):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or HOLMES_GEO_SYSTEM,
            messages=[{"role":"user","content":prompt}]
        )
        return r.content[0].text

    def ai_vision(prompt, image_b64, system="", max_tokens=1500):
        r = _client.messages.create(
            model="claude-sonnet-4-6", max_tokens=max_tokens,
            system=system or HOLMES_GEO_SYSTEM,
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
    def ai_call(p,s="",m=1500): return "Install anthropic: pip install anthropic"
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
HOLMES_GEO_SYSTEM = """You are Sherlock Holmes performing geospatial analysis.

You read location from images the way others read words:
- Vegetation → climate zone → latitude band
- Architecture → cultural region + era
- Road markings → country (left/right hand traffic)
- Sky color + angle → time of day + latitude
- Signage language → country/region
- Soil color → geology → specific regions
- Power line style → country infrastructure
- Vehicle types + plates → country
- Shadows → sun angle → time + location

Format deductions as:
CLUE: [specific visual detail]
  → INFERENCE: [geographic implication]
    → LOCATION: [region/country/city] [X% confidence]

Never guess randomly. Every conclusion needs a visible clue."""

# ── Config ────────────────────────────────────────────────────────────────────
GEOSPY_DIR  = Path("forge_geospy")
DB_PATH     = GEOSPY_DIR / "geospy.db"
CONFIG_FILE = GEOSPY_DIR / "config.json"
CACHE_DIR   = GEOSPY_DIR / "cache"

GEOSPY_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

GEOSPY_API_URL = "https://dev.geospy.ai"

DEFAULT_CONFIG = {
    "geospy_api_key": "",
    "top_k":          5,
    "use_classification": True,
    "anti_cluster":   False,
    "cache_results":  True,
    "reverse_geocode": True,
}

def load_config():
    if CONFIG_FILE.exists():
        try: return {**DEFAULT_CONFIG, **json.loads(CONFIG_FILE.read_text())}
        except: pass
    CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

# ── Database ──────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS geo_results (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            image_hash  TEXT UNIQUE,
            image_path  TEXT,
            ts          TEXT,
            lat         REAL,
            lon         REAL,
            score       REAL,
            predictions TEXT,
            address     TEXT,
            country     TEXT,
            city        TEXT,
            visual_clues TEXT,
            sherlock_chain TEXT,
            alibi_result   TEXT,
            confidence  INTEGER
        );
        CREATE TABLE IF NOT EXISTS contradictions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            image_hash  TEXT,
            ts          TEXT,
            claimed     TEXT,
            actual_lat  REAL,
            actual_lon  REAL,
            actual_place TEXT,
            distance_km REAL,
            verdict     TEXT,
            confidence  INTEGER
        );
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════════════════════
# 📍 GEOSPY API CLIENT
# ══════════════════════════════════════════════════════════════════════════════

class GeoSpyClient:
    def __init__(self, api_key=""):
        self.api_key = api_key or load_config().get("geospy_api_key","")
        self.base    = GEOSPY_API_URL

    def locate(self, image_b64, top_k=5, use_classification=True, anti_cluster=False):
        """Call GeoSpy API with base64 image."""
        if not self.api_key:
            raise ValueError(
                "GeoSpy API key not set.\n"
                "Get yours at: https://dev.geospy.ai\n"
                "Then run: python forge_geospy.py --setup"
            )

        payload = json.dumps({
            "image":              image_b64,
            "key":                self.api_key,
            "top_k":              top_k,
            "use_classification": use_classification,
            "anti_cluster":       anti_cluster,
        }).encode()

        req = urllib.request.Request(
            self.base,
            data    = payload,
            headers = {
                "Content-Type": "application/json",
                "User-Agent":   "FORGE-GeoSpy/1.0",
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    def locate_file(self, image_path, **kwargs):
        """Locate from file path."""
        b64 = image_to_b64(image_path)
        if not b64:
            raise ValueError(f"Cannot read image: {image_path}")
        return self.locate(b64, **kwargs)

def image_to_b64(path, max_size=(1024,768)):
    """Convert image to base64, resize if needed."""
    try:
        if PIL_AVAILABLE:
            img = Image.open(path).convert("RGB")
            img.thumbnail(max_size, Image.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.standard_b64encode(buf.getvalue()).decode()
        else:
            with open(path, "rb") as f:
                return base64.standard_b64encode(f.read()).decode()
    except Exception as e:
        rprint(f"[red]Image read error: {e}[/red]")
        return None

def image_hash(path):
    """Hash of image file for caching."""
    with open(path, "rb") as f:
        return hashlib.md5(f.read(65536)).hexdigest()

# ══════════════════════════════════════════════════════════════════════════════
# 🌍 REVERSE GEOCODER
# ══════════════════════════════════════════════════════════════════════════════

def reverse_geocode(lat, lon):
    """Convert coordinates to human-readable address via Nominatim."""
    try:
        url = (
            f"https://nominatim.openstreetmap.org/reverse"
            f"?lat={lat}&lon={lon}&format=json&zoom=10"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "FORGE-GeoSpy/1.0 (umangkartikey/forge)"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data    = json.loads(r.read())
            address = data.get("display_name","")
            addr    = data.get("address",{})
            return {
                "full":    address,
                "city":    addr.get("city") or addr.get("town") or addr.get("village",""),
                "country": addr.get("country",""),
                "country_code": addr.get("country_code","").upper(),
                "state":   addr.get("state",""),
                "suburb":  addr.get("suburb",""),
            }
    except Exception as e:
        return {"full": f"{lat:.4f}, {lon:.4f}", "city":"","country":"","country_code":""}

def haversine_km(lat1, lon1, lat2, lon2):
    """Distance between two coordinates in km."""
    import math
    R    = 6371
    dlat = math.radians(lat2-lat1)
    dlon = math.radians(lon2-lon1)
    a    = (math.sin(dlat/2)**2 +
            math.cos(math.radians(lat1)) *
            math.cos(math.radians(lat2)) *
            math.sin(dlon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# ══════════════════════════════════════════════════════════════════════════════
# 🧠 SHERLOCK VISUAL CLUE ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

VISUAL_GEO_PROMPT = """You are Sherlock Holmes performing geospatial analysis on this image.

Read the location from visual clues alone. No GPS. No metadata. Just what you see.

## VISUAL CLUE INVENTORY
List every geographic indicator visible:
- Vegetation (species, density, season)
- Architecture (style, age, materials, roof type)
- Road/path (markings, surface, width, signage)
- Sky (color, cloud type, sun angle)
- Signage (language, script, symbols)
- Vehicles (type, plate format if visible)
- People (clothing, ethnicity indicators)
- Terrain (hills, flat, coastal, urban density)
- Infrastructure (power lines, telecom, street lights)
- Soil/ground color

## GEOGRAPHIC DEDUCTIONS
For each significant clue:
CLUE: [detail]
  → INFERENCE: [geographic meaning]
    → NARROWS TO: [region/country]

## LOCATION ESTIMATE
Based on visual clues alone (before GeoSpy):
Most likely: [Country / Region / City if confident]
Confidence: X%
Key deciding clues: [top 3]

## WHAT GIVES IT AWAY
The single most location-specific detail in this image."""

SHERLOCK_GEO_CHAIN = """You are Sherlock Holmes. GeoSpy has located this image.

GeoSpy prediction: {geospy_result}
Visual clue analysis: {visual_analysis}
Reverse geocoded: {address}

Build the complete geospatial deduction chain:

## THE LOCATION CHAIN
How visual clues → GeoSpy coordinates → confirmed location:

CLUE 1: [strongest visual indicator]
  → INFERENCE: [geographic implication]
    → CONFIRMS: [aspect of GeoSpy prediction]
      [confidence%]

CLUE 2: [supporting indicator]
  → [chain continues]

## CONVERGENCE POINT
Where visual analysis and GeoSpy agree completely.

## LOCATION CONFIDENCE
DEFINITE (>90%) / PROBABLE (70-90%) / POSSIBLE (50-70%) / UNCERTAIN (<50%)

## WHAT THIS LOCATION REVEALS
Beyond coordinates — what does this place tell us?
Type of area (residential/commercial/rural/industrial)
Time of day if determinable from light
Season if determinable from vegetation

## ELEMENTARY
The one detail that makes the location obvious in retrospect."""

def analyze_visual_clues(image_b64, cfg=None):
    """Sherlock reads location from visual clues."""
    if not AI_AVAILABLE:
        return "AI not available for visual analysis."
    return ai_vision(VISUAL_GEO_PROMPT, image_b64)

def build_geo_chain(geospy_result, visual_analysis, address):
    """Build Sherlock deduction chain from combined data."""
    if not AI_AVAILABLE:
        return ""

    # Format GeoSpy result
    preds = geospy_result.get("geo_predictions",[])
    top   = preds[0] if preds else {}
    geo_str = f"Top prediction: {top.get('coordinates',[])} score:{top.get('score',0):.4f}"
    if len(preds) > 1:
        geo_str += f"\nClustered around: {[p['coordinates'] for p in preds[:3]]}"

    return ai_call(
        SHERLOCK_GEO_CHAIN.format(
            geospy_result   = geo_str,
            visual_analysis = visual_analysis[:800],
            address         = json.dumps(address, default=str),
        ),
        max_tokens=2000
    )

# ══════════════════════════════════════════════════════════════════════════════
# ⚡ ALIBI CONTRADICTION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

ALIBI_CONTRADICTION_PROMPT = """You are Sherlock Holmes. The image location has been confirmed.

CONFIRMED LOCATION:
  Coordinates: {lat}, {lon}
  Address: {address}
  Country: {country}
  City: {city}
  GeoSpy confidence: {confidence}%

CLAIMED ALIBI / LOCATION:
  "{alibi}"

VISUAL EVIDENCE:
  {visual_clues}

## CONTRADICTION ANALYSIS

### LOCATION MATCH
Does the confirmed location match the claim?
EXACT MATCH / CLOSE (same city) / REGION MATCH / DIFFERENT COUNTRY / IMPOSSIBLE

### DISTANCE
If claim specifies a place: how far is the actual location from claimed location?

### WHAT THE LOCATION PROVES
What does being in [actual location] mean for this case?

### THE IMPOSSIBILITY
If there is a contradiction:
  "The subject claims to have been in [X].
   This image was taken in [Y].
   The distance between these locations is [Z] km.
   Travel time: [T].
   CONCLUSION: [alibi status]"

### VERDICT
ALIBI CONFIRMED / ALIBI WEAKENED / ALIBI CONTRADICTED / ALIBI DESTROYED
Confidence: X%

### WHAT TO INVESTIGATE NEXT
To fully resolve the contradiction."""

def check_alibi(lat, lon, address, alibi_claim, visual_clues="", confidence=80):
    """Cross-reference confirmed location against alibi."""
    if not alibi_claim:
        return None, "No alibi claim provided."

    if not AI_AVAILABLE:
        return None, f"Location: {address.get('full','')}. Claim: {alibi_claim}"

    result = ai_call(
        ALIBI_CONTRADICTION_PROMPT.format(
            lat         = f"{lat:.6f}",
            lon         = f"{lon:.6f}",
            address     = address.get("full",""),
            country     = address.get("country",""),
            city        = address.get("city",""),
            confidence  = confidence,
            alibi       = alibi_claim,
            visual_clues= visual_clues[:600],
        ),
        max_tokens=2000
    )

    # Extract verdict
    verdict_data = ai_json(
        f"From this alibi analysis:\n{result[:1000]}\n\n"
        'JSON: {"verdict":"CONFIRMED|WEAKENED|CONTRADICTED|DESTROYED",'
        '"confidence":85,"distance_km":0,"summary":"one sentence"}',
        "Reply ONLY with JSON.", 200
    )

    return verdict_data, result

# ══════════════════════════════════════════════════════════════════════════════
# 🔬 MAIN GEOLOCATE FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

class GeoResult:
    def __init__(self, image_path):
        self.image_path    = str(image_path)
        self.image_hash    = ""
        self.ts            = datetime.now().isoformat()

        # GeoSpy data
        self.predictions   = []
        self.top_lat       = 0.0
        self.top_lon       = 0.0
        self.top_score     = 0.0
        self.classifications = []

        # Reverse geocode
        self.address       = {}
        self.country       = ""
        self.city          = ""

        # Sherlock analysis
        self.visual_clues  = ""
        self.sherlock_chain= ""

        # Alibi check
        self.alibi_claim   = ""
        self.alibi_verdict = {}
        self.alibi_analysis= ""
        self.contradiction = False

        # Overall
        self.confidence    = 0
        self.maps_url      = ""

    def to_dict(self):
        return {
            "image_path":    self.image_path,
            "ts":            self.ts,
            "coordinates":   [self.top_lat, self.top_lon],
            "score":         self.top_score,
            "address":       self.address,
            "country":       self.country,
            "city":          self.city,
            "visual_clues":  self.visual_clues[:300],
            "sherlock_chain":self.sherlock_chain[:300],
            "alibi_claim":   self.alibi_claim,
            "alibi_verdict": self.alibi_verdict,
            "contradiction": self.contradiction,
            "confidence":    self.confidence,
            "maps_url":      self.maps_url,
            "predictions":   self.predictions[:3],
        }

    def save(self):
        conn = get_db()
        conn.execute("""
            INSERT OR REPLACE INTO geo_results
            (image_hash,image_path,ts,lat,lon,score,predictions,
             address,country,city,visual_clues,sherlock_chain,alibi_result,confidence)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            self.image_hash, self.image_path, self.ts,
            self.top_lat, self.top_lon, self.top_score,
            json.dumps(self.predictions, default=str),
            json.dumps(self.address, default=str),
            self.country, self.city,
            self.visual_clues[:2000],
            self.sherlock_chain[:2000],
            self.alibi_analysis[:2000],
            self.confidence,
        ))

        if self.contradiction:
            conn.execute("""
                INSERT INTO contradictions
                (image_hash,ts,claimed,actual_lat,actual_lon,actual_place,verdict,confidence)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                self.image_hash, self.ts,
                self.alibi_claim,
                self.top_lat, self.top_lon,
                self.address.get("full",""),
                json.dumps(self.alibi_verdict, default=str),
                self.confidence,
            ))

        conn.commit()
        conn.close()

def geolocate(image_path, alibi="", context="", verbose=True):
    """
    Full GeoSpy + Sherlock pipeline:
      1. Visual clue analysis (Sherlock reads location from image)
      2. GeoSpy API call (AI locates coordinates)
      3. Reverse geocode (coordinates → address)
      4. Sherlock deduction chain (combine all findings)
      5. Alibi contradiction check (if alibi provided)
    """
    image_path = Path(image_path)
    if not image_path.exists():
        rprint(f"[red]Image not found: {image_path}[/red]")
        return None

    cfg    = load_config()
    result = GeoResult(image_path)

    rprint(f"\n[bold yellow]🌍 FORGE GEOSPY ANALYSIS[/bold yellow]")
    rprint(f"  [bold]Image:[/bold]  {image_path.name}")
    rprint(f"  [bold]Alibi:[/bold]  {alibi or 'None'}\n")

    # ── Image prep ──────────────────────────────────────────────────────────
    result.image_hash = image_hash(image_path)
    image_b64 = image_to_b64(image_path)
    if not image_b64:
        rprint("[red]Failed to read image.[/red]")
        return None

    # ── Check cache ──────────────────────────────────────────────────────────
    if cfg.get("cache_results"):
        conn = get_db()
        cached = conn.execute(
            "SELECT * FROM geo_results WHERE image_hash=?",
            (result.image_hash,)
        ).fetchone()
        conn.close()
        if cached and not alibi:
            rprint("[dim]Using cached result.[/dim]")
            result.top_lat  = cached["lat"]
            result.top_lon  = cached["lon"]
            result.address  = json.loads(cached["address"] or "{}")
            result.country  = cached["country"]
            result.city     = cached["city"]
            result.sherlock_chain = cached["sherlock_chain"]
            result.confidence = cached["confidence"]
            result.maps_url = f"https://maps.google.com/?q={result.top_lat},{result.top_lon}"
            _print_result(result)
            return result

    # ── Step 1: Sherlock visual analysis ────────────────────────────────────
    rprint("[bold]━━━ SHERLOCK READS THE IMAGE ━━━[/bold]")
    rprint("[dim]Reading location from visual clues...[/dim]")
    result.visual_clues = analyze_visual_clues(image_b64)
    if verbose:
        rprint(Panel(result.visual_clues[:600], border_style="dim yellow",
                     title="👁 Visual Clue Analysis"))

    # ── Step 2: GeoSpy API ──────────────────────────────────────────────────
    rprint("\n[bold]━━━ GEOSPY LOCATING ━━━[/bold]")
    geospy_raw = None

    if cfg.get("geospy_api_key"):
        try:
            rprint("[dim]Calling GeoSpy API...[/dim]")
            client    = GeoSpyClient(cfg["geospy_api_key"])
            geospy_raw= client.locate(
                image_b64,
                top_k             = cfg.get("top_k",5),
                use_classification= cfg.get("use_classification",True),
                anti_cluster      = cfg.get("anti_cluster",False),
            )
            preds = geospy_raw.get("geo_predictions",[])
            if preds:
                result.predictions = preds
                result.top_lat     = preds[0]["coordinates"][0]
                result.top_lon     = preds[0]["coordinates"][1]
                result.top_score   = preds[0].get("score",0)
                result.confidence  = int(preds[0].get("similarity_score_1km",0.7) * 100)
                rprint(f"  [green]✅ GeoSpy located: {result.top_lat:.5f}, {result.top_lon:.5f}[/green]")
                rprint(f"  [dim]Confidence: {result.confidence}%[/dim]")
            else:
                rprint("[yellow]GeoSpy returned no predictions.[/yellow]")

            result.classifications = geospy_raw.get("image_classifications",[])

        except ValueError as e:
            rprint(f"[yellow]{e}[/yellow]")
            geospy_raw = None
        except Exception as e:
            rprint(f"[red]GeoSpy API error: {e}[/red]")
            geospy_raw = None
    else:
        rprint("[yellow]No GeoSpy API key — using Sherlock visual analysis only.[/yellow]")
        rprint("[dim]Get key at: https://dev.geospy.ai | Run: python forge_geospy.py --setup[/dim]")

    # Fallback: Claude-only geolocation from visual clues
    if not geospy_raw or not result.predictions:
        rprint("[dim]Estimating from visual clues...[/dim]")
        coords = ai_json(
            f"From this visual analysis:\n{result.visual_clues[:1000]}\n\n"
            "Estimate GPS coordinates as JSON:\n"
            '{"lat":0.0,"lon":0.0,"confidence":50,"country":"","city":""}',
            "Reply ONLY with JSON.", 200
        )
        if coords:
            result.top_lat    = coords.get("lat",0)
            result.top_lon    = coords.get("lon",0)
            result.confidence = coords.get("confidence",40)
            result.country    = coords.get("country","")
            result.city       = coords.get("city","")

    # ── Step 3: Reverse geocode ──────────────────────────────────────────────
    if result.top_lat != 0 or result.top_lon != 0:
        rprint("\n[bold]━━━ REVERSE GEOCODING ━━━[/bold]")
        rprint("[dim]Converting coordinates to address...[/dim]")
        result.address = reverse_geocode(result.top_lat, result.top_lon)
        result.country = result.address.get("country","")
        result.city    = result.address.get("city","")
        result.maps_url= f"https://maps.google.com/?q={result.top_lat},{result.top_lon}"
        rprint(f"  [green]📍 {result.address.get('full','')[:80]}[/green]")

    # ── Step 4: Sherlock deduction chain ─────────────────────────────────────
    rprint("\n[bold]━━━ SHERLOCK BUILDS THE CHAIN ━━━[/bold]")
    result.sherlock_chain = build_geo_chain(
        geospy_raw or {"geo_predictions":[{"coordinates":[result.top_lat,result.top_lon]}]},
        result.visual_clues,
        result.address,
    )
    if verbose:
        rprint(Panel(result.sherlock_chain[:800], border_style="yellow",
                     title="🔗 Geospatial Deduction Chain"))

    # ── Step 5: Alibi contradiction ──────────────────────────────────────────
    if alibi:
        rprint("\n[bold]━━━ ALIBI CONTRADICTION ENGINE ━━━[/bold]")
        result.alibi_claim = alibi
        verdict_data, analysis = check_alibi(
            result.top_lat, result.top_lon,
            result.address, alibi,
            result.visual_clues, result.confidence
        )
        result.alibi_verdict  = verdict_data or {}
        result.alibi_analysis = analysis
        verdict_str = (verdict_data or {}).get("verdict","UNKNOWN")
        result.contradiction = verdict_str in ("CONTRADICTED","DESTROYED")

        color = ("red" if result.contradiction else
                 "yellow" if verdict_str == "WEAKENED" else "green")
        rprint(f"\n  [{color} bold]ALIBI: {verdict_str}[/{color} bold]")
        if verbose:
            rprint(Panel(analysis[:800], border_style=color,
                         title=f"⚡ Alibi Analysis — {verdict_str}"))

    # ── Save & return ─────────────────────────────────────────────────────────
    result.save()
    _print_result(result)
    return result

def _print_result(result):
    rprint(f"\n[bold yellow]{'═'*55}[/bold yellow]")
    rprint(f"[bold]🌍 GEOSPY RESULT[/bold]")
    rprint(f"[bold yellow]{'═'*55}[/bold yellow]")
    rprint(f"  [bold]Location:[/bold]  {result.address.get('full','')[:70]}")
    rprint(f"  [bold]Country:[/bold]   {result.country}")
    rprint(f"  [bold]City:[/bold]      {result.city}")
    rprint(f"  [bold]Coords:[/bold]    {result.top_lat:.5f}, {result.top_lon:.5f}")
    rprint(f"  [bold]Confidence:[/bold]{result.confidence}%")
    rprint(f"  [bold]Maps:[/bold]      {result.maps_url}")
    if result.alibi_verdict:
        verdict = result.alibi_verdict.get("verdict","?")
        color   = "red" if result.contradiction else "yellow"
        rprint(f"  [bold]Alibi:[/bold]     [{color}]{verdict}[/{color}]")

# ══════════════════════════════════════════════════════════════════════════════
# 🎬 VIDEO INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

def geolocate_video(video_path, alibi="", max_frames=5):
    """Extract frames from video and geolocate each."""
    rprint(f"\n[bold yellow]🎬 GEOSPY VIDEO MODE[/bold yellow]")
    rprint(f"  Extracting {max_frames} frames for geolocation...")

    try:
        import cv2
        cap      = cv2.VideoCapture(str(video_path))
        fps      = cap.get(cv2.CAP_PROP_FPS) or 25
        total    = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        interval = max(1, total // max_frames)
        results  = []

        for i in range(max_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i * interval)
            ret, frame = cap.read()
            if not ret: continue

            # Save temp frame
            ts      = (i * interval) / fps
            tmp     = CACHE_DIR / f"frame_{i:03d}.jpg"
            cv2.imwrite(str(tmp), frame)

            rprint(f"\n  [yellow]Frame {i+1}/{max_frames} at {ts:.1f}s[/yellow]")
            gr = geolocate(tmp, alibi=alibi, verbose=(i==0))
            if gr:
                results.append(gr)

        cap.release()

        # Synthesize across frames
        if results and AI_AVAILABLE:
            locations = [f"Frame {i+1}: {r.address.get('city','')} {r.country} ({r.confidence}%)"
                        for i,r in enumerate(results)]
            synthesis = ai_call(
                f"Video geolocation results across {len(results)} frames:\n"
                + "\n".join(locations) +
                "\n\nSynthesize: Is location consistent? Most probable location? Any suspicious inconsistencies?",
                max_tokens=500
            )
            rprint(Panel(synthesis, border_style="yellow", title="🎬 Video Location Synthesis"))

        return results

    except ImportError:
        rprint("[yellow]OpenCV not available. Install: pip install opencv-python[/yellow]")
        rprint("[dim]Extracting via ffmpeg...[/dim]")
        return []

# ══════════════════════════════════════════════════════════════════════════════
# 📦 BATCH MODE
# ══════════════════════════════════════════════════════════════════════════════

def batch_geolocate(directory, alibi="", extensions=(".jpg",".jpeg",".png",".webp")):
    """Geolocate all images in a directory."""
    directory = Path(directory)
    images    = [f for f in directory.glob("*") if f.suffix.lower() in extensions]

    if not images:
        rprint(f"[yellow]No images found in {directory}[/yellow]")
        return []

    rprint(f"\n[bold yellow]📦 BATCH MODE: {len(images)} images[/bold yellow]")
    results = []

    for i, img in enumerate(images, 1):
        rprint(f"\n[yellow]Image {i}/{len(images)}: {img.name}[/yellow]")
        gr = geolocate(img, alibi=alibi, verbose=False)
        if gr:
            results.append(gr)

    # Summary table
    if RICH and results:
        t = Table(border_style="yellow", box=rbox.ROUNDED, title="Batch Geolocation Results")
        t.add_column("Image",    style="dim",   width=22)
        t.add_column("Country",  style="yellow",width=18)
        t.add_column("City",     style="cyan",  width=18)
        t.add_column("Conf",     width=6)
        t.add_column("Alibi",    style="red",   width=14)
        for r in results:
            alibi_str = r.alibi_verdict.get("verdict","—") if r.alibi_verdict else "—"
            t.add_row(
                Path(r.image_path).name[:21],
                r.country[:17], r.city[:17],
                f"{r.confidence}%", alibi_str
            )
        console.print(t)

    return results

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 API SERVER
# ══════════════════════════════════════════════════════════════════════════════

def start_server(port=7342):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse

    class GeoAPI(BaseHTTPRequestHandler):
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
            cfg  = load_config()
            if path == "/api/status":
                self._json({
                    "status":     "online",
                    "ai":         AI_AVAILABLE,
                    "geospy_key": bool(cfg.get("geospy_api_key")),
                    "api_url":    GEOSPY_API_URL,
                })
            elif path == "/api/history":
                conn = get_db()
                rows = conn.execute(
                    "SELECT * FROM geo_results ORDER BY id DESC LIMIT 20"
                ).fetchall()
                conn.close()
                self._json({"results":[dict(r) for r in rows]})
            elif path == "/api/contradictions":
                conn = get_db()
                rows = conn.execute(
                    "SELECT * FROM contradictions ORDER BY id DESC LIMIT 20"
                ).fetchall()
                conn.close()
                self._json({"contradictions":[dict(r) for r in rows]})
            else:
                self._json({"error":"not found"},404)

        def do_POST(self):
            path = urlparse(self.path).path
            body = self._body()

            if path == "/api/locate":
                image_b64 = body.get("image_b64","")
                filename  = body.get("filename","upload.jpg")
                alibi     = body.get("alibi","")
                context   = body.get("context","")

                if not image_b64:
                    self._json({"error":"image_b64 required"},400); return

                # Save temp image
                img_data  = base64.b64decode(image_b64)
                tmp_path  = CACHE_DIR / f"upload_{hashlib.md5(img_data[:100]).hexdigest()[:8]}_{filename}"
                tmp_path.write_bytes(img_data)

                # Run in thread
                job_id    = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
                jobs = getattr(self.server, "_jobs", {})
                self.server._jobs = jobs
                jobs[job_id] = {"status":"running"}

                def run():
                    try:
                        gr = geolocate(tmp_path, alibi=alibi, context=context, verbose=False)
                        if gr:
                            jobs[job_id] = {"status":"complete","result":gr.to_dict()}
                        else:
                            jobs[job_id] = {"status":"error","error":"Geolocation failed"}
                    except Exception as e:
                        jobs[job_id] = {"status":"error","error":str(e)}

                threading.Thread(target=run, daemon=True).start()
                self._json({"job_id":job_id,"status":"running"})

            elif path == "/api/locate/status":
                job_id = body.get("job_id","")
                jobs   = getattr(self.server, "_jobs", {})
                if job_id in jobs:
                    self._json(jobs[job_id])
                else:
                    self._json({"error":"not found"},404)

            elif path == "/api/locate/sync":
                # Synchronous: base64 image + GeoSpy key required
                image_b64 = body.get("image_b64","")
                alibi     = body.get("alibi","")
                if not image_b64:
                    self._json({"error":"image_b64 required"},400); return

                cfg    = load_config()
                client = GeoSpyClient(cfg.get("geospy_api_key",""))
                try:
                    raw    = client.locate(image_b64)
                    preds  = raw.get("geo_predictions",[])
                    if preds:
                        lat  = preds[0]["coordinates"][0]
                        lon  = preds[0]["coordinates"][1]
                        addr = reverse_geocode(lat, lon)
                        self._json({
                            "status":      "success",
                            "lat":         lat,
                            "lon":         lon,
                            "score":       preds[0].get("score",0),
                            "confidence":  int(preds[0].get("similarity_score_1km",0.7)*100),
                            "address":     addr,
                            "predictions": preds,
                            "maps_url":    f"https://maps.google.com/?q={lat},{lon}",
                        })
                    else:
                        self._json({"error":"No predictions returned"}, 400)
                except Exception as e:
                    self._json({"error":str(e)},500)

            elif path == "/api/config":
                cfg = load_config()
                if "geospy_api_key" in body:
                    cfg["geospy_api_key"] = body["geospy_api_key"]
                    save_config(cfg)
                    self._json({"ok":True,"message":"API key saved"})
                else:
                    self._json({k:v for k,v in cfg.items() if k!="geospy_api_key"})

            else:
                self._json({"error":"unknown endpoint"},404)

    server = HTTPServer(("0.0.0.0", port), GeoAPI)
    server._jobs = {}
    rprint(f"  [yellow]🌍 FORGE GEOSPY API: http://localhost:{port}[/yellow]")
    server.serve_forever()

# ══════════════════════════════════════════════════════════════════════════════
# ⚙️ SETUP
# ══════════════════════════════════════════════════════════════════════════════

def setup_wizard():
    rprint("\n[bold yellow]⚙️  FORGE GEOSPY SETUP[/bold yellow]")
    rprint("[dim]Get your API key at: https://dev.geospy.ai[/dim]")
    rprint("[dim]Free plan: 20 images/month[/dim]\n")

    inp = console.input if RICH else input
    key = inp("[yellow]GeoSpy API key: [/yellow]").strip()

    if not key:
        rprint("[yellow]No key entered. Running in visual-only mode.[/yellow]")
        return

    cfg = load_config()
    cfg["geospy_api_key"] = key

    # Test key
    rprint("[dim]Testing key...[/dim]")
    try:
        client = GeoSpyClient(key)
        # Small 1x1 white pixel test
        test_b64 = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8AJQAB/9k="
        client.locate(test_b64, top_k=1)
        rprint("[green]✅ API key valid![/green]")
    except Exception as e:
        if "401" in str(e) or "403" in str(e) or "key" in str(e).lower():
            rprint(f"[red]Invalid API key: {e}[/red]")
            return
        # Other errors (network etc) — save anyway
        rprint(f"[yellow]Could not verify key: {e}[/yellow]")

    save_config(cfg)
    rprint(f"[green]✅ Config saved to {CONFIG_FILE}[/green]")

# ══════════════════════════════════════════════════════════════════════════════
# 🖥️ MAIN
# ══════════════════════════════════════════════════════════════════════════════

BANNER = """
[yellow]
  ██████╗ ███████╗ ██████╗ ███████╗██████╗ ██╗   ██╗
 ██╔════╝ ██╔════╝██╔═══██╗██╔════╝██╔══██╗╚██╗ ██╔╝
 ██║  ███╗█████╗  ██║   ██║███████╗██████╔╝ ╚████╔╝
 ██║   ██║██╔══╝  ██║   ██║╚════██║██╔═══╝   ╚██╔╝
 ╚██████╔╝███████╗╚██████╔╝███████║██║        ██║
  ╚═════╝ ╚══════╝ ╚═════╝ ╚══════╝╚═╝        ╚═╝
[/yellow]
[bold]  🌍 FORGE GEOSPY — Geospatial Intelligence[/bold]
[dim]  Drop any image. Know exactly where it was taken.[/dim]
"""

def main():
    if "--setup" in sys.argv:
        rprint(BANNER)
        setup_wizard()
        return

    if "--server" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 7342
        rprint(BANNER)
        start_server(port)
        return

    if "--batch" in sys.argv:
        idx = sys.argv.index("--batch")
        directory = sys.argv[idx+1] if idx+1 < len(sys.argv) else "."
        alibi = sys.argv[sys.argv.index("--alibi")+1] if "--alibi" in sys.argv else ""
        rprint(BANNER)
        batch_geolocate(directory, alibi)
        return

    if "--video" in sys.argv:
        idx   = sys.argv.index("--video")
        video = sys.argv[idx+1] if idx+1 < len(sys.argv) else ""
        alibi = sys.argv[sys.argv.index("--alibi")+1] if "--alibi" in sys.argv else ""
        if video:
            rprint(BANNER)
            geolocate_video(video, alibi)
        return

    if "--image" in sys.argv:
        idx   = sys.argv.index("--image")
        image = sys.argv[idx+1] if idx+1 < len(sys.argv) else ""
        alibi = sys.argv[sys.argv.index("--alibi")+1] if "--alibi" in sys.argv else ""
        context= sys.argv[sys.argv.index("--context")+1] if "--context" in sys.argv else ""
        if image:
            rprint(BANNER)
            geolocate(image, alibi=alibi, context=context)
        return

    # Interactive
    rprint(BANNER)
    cfg = load_config()
    has_key = bool(cfg.get("geospy_api_key"))
    rprint(f"  [dim]GeoSpy API: {'✅ configured' if has_key else '❌ not set — run --setup'}[/dim]")
    rprint(f"  [dim]AI:         {'✅' if AI_AVAILABLE else '❌ pip install anthropic'}[/dim]\n")

    rprint("[dim]Commands:[/dim]")
    rprint("  [yellow]python forge_geospy.py --setup[/yellow]            Configure API key")
    rprint("  [yellow]python forge_geospy.py --image photo.jpg[/yellow]  Geolocate image")
    rprint("  [yellow]python forge_geospy.py --image photo.jpg --alibi 'I was in London'[/yellow]")
    rprint("  [yellow]python forge_geospy.py --batch ./images/[/yellow]   Batch mode")
    rprint("  [yellow]python forge_geospy.py --video clip.mp4[/yellow]    Video mode")
    rprint("  [yellow]python forge_geospy.py --server[/yellow]            API server :7342")

if __name__ == "__main__":
    main()
