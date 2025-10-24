from fastapi import FastAPI, Response, HTTPException, Header
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse
from datetime import datetime, date
from pydantic import BaseModel
from typing import Optional, List
from io import BytesIO
from PIL import Image, ImageDraw
import os, random, requests

from config import CFG
from storage import GCSClient
from utils import iso_week_str, load_font, pick_fallback_bg, map_to_raw6
from deduper import hash_bytes, collect_existing_hashes
from hf_gen import generate_image

app = FastAPI(title="Family Display Backend", version="1.5.0")


# -------------------------
# Helpers (layout & weather)
# -------------------------
def draw_rounded_rect(im, xy, radius=16, fill=(255, 255, 255, 230)):
    """Paste a rounded-rect panel onto an image."""
    x0, y0, x1, y1 = xy
    panel = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(panel)
    pdraw.rounded_rectangle([0, 0, x1 - x0 - 1, y1 - y0 - 1], radius=radius, fill=fill)
    im.paste(panel, (x0, y0), panel)


def wrap_text(draw, text, font, max_width):
    """Wrap text so each line fits within max_width pixels (uses textbbox for accuracy)."""
    if not text:
        return ""
    words = text.split()
    lines, line = [], ""
    for w in words:
        trial = (line + " " + w).strip()
        wbox = draw.textbbox((0, 0), trial, font=font)
        if wbox[2] - wbox[0] <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return "\n".join(lines)


# Simple demo city->lat/lon map. Add as needed.
CITY_LL = {
    "Darwin": (-12.4634, 130.8456),
    # "Sydney": (-33.8688, 151.2093),
    # "Melbourne": (-37.8136, 144.9631),
}


def get_weather(city: str):
    """Fetch current weather via Open-Meteo (no API key). Returns None on error."""
    latlon = CITY_LL.get(city)
    if not latlon:
        return None
    lat, lon = latlon
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current_weather": "true",
                # You can add units or extra params here if you like.
            },
            timeout=6,
        )
        r.raise_for_status()
        cw = r.json().get("current_weather", {})
        return {
            "temp": cw.get("temperature"),  # °C
            "windspeed": cw.get("windspeed"),  # km/h
            "code": cw.get("weathercode"),
        }
    except Exception:
        return None


# -------------------------
# Models / Schemas
# -------------------------
class GenerateRequest(BaseModel):
    week: Optional[str] = None
    n_variants: Optional[int] = None
    prompts: Optional[List[str]] = None  # optional custom prompts


# -------------------------
# Routes
# -------------------------
@app.get("/", response_class=PlainTextResponse)
def health():
    return "ok"


@app.get("/setup", response_class=HTMLResponse)
def setup(city: str = "Darwin", variant: int = 0):
    html = (
        "<html><head><title>Family Display Setup</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
        "<style>body{font-family:sans-serif;max-width:980px;margin:16px auto;padding:0 12px;color:#111}"
        "img{border:1px solid #ccc;max-width:100%;height:auto}</style>"
        "</head><body>"
        "<h2>Family Display</h2>"
        f"<p>City: <b>{city}</b> &nbsp; Variant: <b>{variant}</b></p>"
        "<p>Preview frame:</p>"
        f"<img src='/v1/frame?city={city}&variant={variant}' alt='Preview frame'>"
        "<hr><h3>Examples</h3><ul>"
        "<li><a href='/v1/list'>/v1/list</a></li>"
        "<li><a href='/manifest/week'>/manifest/week</a></li>"
        "</ul></body></html>"
    )
    return HTMLResponse(content=html, status_code=200)


@app.get("/v1/list", response_class=JSONResponse)
def list_variants(week: Optional[str] = None):
    if not week or week == "auto":
        week = iso_week_str(date.today())
    gcs = GCSClient()
    manifest = gcs.read_json(f"packs/{week}/manifest.json") or {"week": week, "items": []}
    return manifest


@app.get("/manifest/week", response_class=JSONResponse)
def manifest_week(week: Optional[str] = None):
    if not week or week == "auto":
        week = iso_week_str(date.today())
    gcs = GCSClient()
    manifest = gcs.read_json(f"packs/{week}/manifest.json") or {"week": week, "items": []}
    return manifest


@app.get("/v1/frame")
def get_frame(city: str = "Darwin", variant: int = 0):
    """Compose an image: background (from pack or fallback) + clean overlays (city/date/weather + dad joke)."""
    W, H = CFG["width"], CFG["height"]
    week = iso_week_str(date.today())
    gcs = GCSClient()

    # Load background for this variant or fall back
    bg_key = f"packs/{week}/variant_{variant}.png"
    bg = gcs.read_image(bg_key)
    if bg is None:
        bg = pick_fallback_bg(W, H)

    # Base image + drawing context
    img = bg.convert("RGB").copy()
    draw = ImageDraw.Draw(img)

    # Fonts
    font_big = load_font("/usr/share/fonts/truetype/custom/Nunito-ExtraBold.ttf", 60)
    font_med = load_font("/usr/share/fonts/truetype/custom/Baloo2-Bold.ttf", 36)
    font_small = load_font("/usr/share/fonts/truetype/custom/Nunito-ExtraBold.ttf", 24)

    # Layout constants
    pad = 24
    banner_h = 110

    # ---------- Top glass banner ----------
    draw_rounded_rect(img, (pad, pad, W - pad, pad + banner_h), radius=18, fill=(255, 255, 255, 235))

    # City on left
    city_bbox = draw.textbbox((0, 0), city, font=font_big)
    city_h = city_bbox[3] - city_bbox[1]
    city_y = pad + (banner_h - city_h) // 2 - 4
    draw.text((pad * 2, city_y), city, font=font_big, fill=(0, 0, 0))

    # Date under city (small)
    today_str = datetime.now().strftime("%A, %d %b %Y")
    draw.text((pad * 2, city_y + city_h - 8), today_str, font=font_small, fill=(60, 60, 60))

    # Weather on right
    wx = get_weather(city)
    if wx and wx.get("temp") is not None:
        right_block_w = 300
        x0 = W - pad - right_block_w
        y0 = pad + 14
        temp_txt = f"{int(round(wx['temp']))}°C"
        tbox = draw.textbbox((0, 0), temp_txt, font=font_med)
        draw.text((x0 + 12, y0), temp_txt, font=font_med, fill=(0, 0, 0))
        cond_txt = f"Wind {int(round(wx.get('windspeed', 0)))} km/h"
        draw.text((x0 + 12, y0 + (tbox[3] - tbox[1]) + 6), cond_txt, font=font_small, fill=(60, 60, 60))

    # ---------- Bottom "Dad joke" card ----------
    card_h = 180
    y0 = H - card_h - pad
    draw_rounded_rect(img, (pad, y0, W - pad, y0 + card_h), radius=18, fill=(255, 255, 255, 235))

    title_y = y0 + 18
    draw.text((pad * 2, title_y), "Dad joke", font=font_med, fill=(0, 0, 0))

    # Neatly wrap the joke
    joke = "I told my computer I needed a break — it said 'No problem, I'll go to sleep.'"
    max_text_width = W - pad * 4
    wrapped = wrap_text(draw, joke, font_small, max_text_width)
    draw.multiline_text((pad * 2, title_y + 42), wrapped, font=font_small, fill=(40, 40, 40), spacing=6, align="left")

    # Optional: RAW6 mapping if enabled
    if CFG["raw6_map"]:
        img = map_to_raw6(img)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


# -------------------------
# Pack generation (HF + deduper)
# -------------------------
def _model_choice() -> str:
    # GEN_SPEED_MODE true => SDXL-Turbo, else default (Playground v2.5 aesthetic) unless HF_MODEL override provided
    if CFG.get("gen_speed_mode", False):
        return os.getenv("HF_MODEL", "stabilityai/sdxl-turbo")
    return os.getenv("HF_MODEL", CFG.get("hf_model", "playgroundai/playground-v2.5-1024px-aesthetic"))


def _procedural_bg(W: int, H: int) -> Image.Image:
    return pick_fallback_bg(W, H)


@app.post("/pack/generate", response_class=JSONResponse)
def pack_generate(
    req: GenerateRequest,
    x_pack_secret: Optional[str] = Header(default=None)  # optional simple guard if you later add PACK_SECRET
):
    # Optional simple protection header (only enforced if PACK_SECRET env is set)
    expected = os.getenv("PACK_SECRET")
    if expected and x_pack_secret != expected:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Determine week + count
    if req.week in (None, "auto"):
        week = iso_week_str(date.today())
    else:
        week = req.week
    n = req.n_variants or CFG["variants_per_week"]

    gcs = GCSClient()
    W, H = CFG["width"], CFG["height"]

    # Existing manifest for dedupe
    manifest_key = f"packs/{week}/manifest.json"
    manifest = gcs.read_json(manifest_key) or {"week": week, "items": []}
    existing_hashes = collect_existing_hashes(manifest)
    items = manifest.get("items", [])

    # Prompts (weekday themes live in utils/config in earlier versions; here we just keep some nice defaults)
    base_prompts = [
        "bold abstract geometric collage, kid-friendly, high contrast, flat poster colors, paper cut shapes",
        "playful abstract waves and blobs, graphic poster, vibrant flat color blocks, soft paper texture",
        "minimal Bauhaus geometry, primary shapes, clean layout, poster design, balanced composition",
        "circles and arcs motif, layered stickers, cutout style, high contrast, children’s art poster",
        "grid-based poster, stripes and dots, pop-art flavor, crisp edges, screenprint feel",
    ]
    prompts = (req.prompts or []) + base_prompts
    random.shuffle(prompts)

    attempts_limit = n * 8
    attempts = 0
    created = 0
    model = _model_choice()

    while created < n and attempts < attempts_limit:
        attempts += 1
        img_bytes = None

        # Try Hugging Face if enabled
        if CFG["use_hf"]:
            prompt = random.choice(prompts)
            img_bytes = generate_image(prompt=prompt, model=model)

        # Fallback to procedural if HF missing or failed
        if not img_bytes:
            im = _procedural_bg(W, H)
            buf = BytesIO()
            im.save(buf, format="PNG")
            img_bytes = buf.getvalue()

        # Hash + dedupe
        h = hash_bytes(img_bytes)
        if h in existing_hashes:
            continue

        # Persist
        variant_idx = len(items)
        key = f"packs/{week}/variant_{variant_idx}.png"
        gcs.write_bytes(key, img_bytes)

        items.append({"variant": variant_idx, "key": key, "hash": h, "model": model})
        existing_hashes.add(h)
        created += 1

    manifest = {"week": week, "items": items, "count": len(items)}
    gcs.write_json(manifest_key, manifest)
    return {"status": "ok", "week": week, "added": created, "total": len(items), "model": model}
