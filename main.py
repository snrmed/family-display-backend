from fastapi import FastAPI, Response
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse
from datetime import datetime, date
from pydantic import BaseModel
from typing import Optional, List
from io import BytesIO
from PIL import Image, ImageDraw
import os, random

from config import CFG, THEMES
from storage import GCSClient
from utils import iso_week_str, load_font, pick_fallback_bg, map_to_raw6, weekday_theme
from deduper import hash_bytes, collect_existing_hashes
from hf_gen import generate_image

app = FastAPI(title="Family Display Backend", version="1.4.0")

class GenerateRequest(BaseModel):
    week: Optional[str] = None
    n_variants: Optional[int] = None
    prompts: Optional[List[str]] = None  # optional custom prompts

@app.get("/", response_class=PlainTextResponse)
def health():
    return "ok"

@app.get("/setup", response_class=HTMLResponse)
def setup(city: str = "Darwin", variant: int = 0):
    html = (
        "<html><head><title>Family Display Setup</title></head><body style='font-family:sans-serif;'>"
        "<h2>Family Display</h2>"
        f"<p>City: <b>{city}</b> &nbsp; Variant: <b>{variant}</b></p>"
        "<p>Preview frame:</p>"
        f"<img src='/v1/frame?city={city}&variant={variant}' style='border:1px solid #ccc;max-width:90%;'>"
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
    W, H = CFG["width"], CFG["height"]
    week = iso_week_str(date.today())
    gcs = GCSClient()

    bg_key = f"packs/{week}/variant_{variant}.png"
    bg = gcs.read_image(bg_key)
    if bg is None:
        bg = pick_fallback_bg(W, H)

    img = bg.convert("RGB").copy()
    draw = ImageDraw.Draw(img)

    font_big = load_font("/usr/share/fonts/truetype/custom/Nunito-ExtraBold.ttf", 60)
    font_med = load_font("/usr/share/fonts/truetype/custom/Baloo2-Bold.ttf", 36)
    font_small = load_font("/usr/share/fonts/truetype/custom/Nunito-ExtraBold.ttf", 24)

    today_str = datetime.now().strftime("%A, %d %b %Y")
    pad = 20
    banner_h = 80
    overlay = Image.new("RGBA", (W, banner_h), (255,255,255,220))
    img.paste(overlay, (0, 0), overlay)
    draw.text((pad, 10), f"{city}", font=font_big, fill=(0,0,0))
    draw.text((pad, 50), today_str, font=font_small, fill=(50,50,50))

    card_h = 120
    y0 = H - card_h - 10
    card = Image.new("RGBA", (W - 2*pad, card_h), (255,255,255,230))
    img.paste(card, (pad, y0), card)
    joke = "I told my computer I needed a break — it said 'No problem, I'll go to sleep.'"
    draw.text((pad+20, y0+20), "Dad joke", font=font_med, fill=(0,0,0))
    draw.text((pad+20, y0+60), joke, font=font_small, fill=(40,40,40))

    if CFG["raw6_map"]:
        img = map_to_raw6(img)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")

def _model_choice() -> str:
    if CFG["gen_speed_mode"]:
        return os.getenv("HF_MODEL", "stabilityai/sdxl-turbo")
    return os.getenv("HF_MODEL", CFG["hf_model"])

def _procedural_bg(W: int, H: int) -> Image.Image:
    return pick_fallback_bg(W, H)

@app.post("/pack/generate", response_class=JSONResponse)
def pack_generate(req: GenerateRequest):
    # Determine week and target count
    if req.week in (None, "auto"):
        week = iso_week_str(date.today())
    else:
        week = req.week
    n = req.n_variants or CFG["variants_per_week"]

    gcs = GCSClient()
    W, H = CFG["width"], CFG["height"]

    # Load existing manifest to dedupe
    manifest_key = f"packs/{week}/manifest.json"
    manifest = gcs.read_json(manifest_key) or {"week": week, "items": []}
    existing_hashes = collect_existing_hashes(manifest)
    items = manifest.get("items", [])

    # Build prompts: weekday theme + shuffled variations
    base_theme = weekday_theme()
    base_prompts = [
        base_theme,
        base_theme + ", grain paper texture, collage poster",
        base_theme + ", layered stickers, drop shadows",
        base_theme + ", screenprint look, halftone accents",
        base_theme + ", soft vignette around edges"
    ]
    prompts = (req.prompts or []) + base_prompts
    random.shuffle(prompts)

    # Try to create n new unique images
    attempts_limit = n * 8
    attempts = 0
    created = 0
    model = _model_choice()

    while created < n and attempts < attempts_limit:
        attempts += 1
        img_bytes = None

        if CFG["use_hf"]:
            prompt = random.choice(prompts)
            img_bytes = generate_image(prompt=prompt, model=model)

        if not img_bytes:
            im = _procedural_bg(W, H)
            buf = BytesIO()
            im.save(buf, format="PNG")
            img_bytes = buf.getvalue()

        h = hash_bytes(img_bytes)
        if h in existing_hashes:
            continue

        variant_idx = len(items)
        key = f"packs/{week}/variant_{variant_idx}.png"
        gcs.write_bytes(key, img_bytes)

        items.append({"variant": variant_idx, "key": key, "hash": h, "model": model})
        existing_hashes.add(h)
        created += 1

    manifest = {"week": week, "items": items, "count": len(items)}
    gcs.write_json(manifest_key, manifest)
    return {"status": "ok", "week": week, "added": created, "total": len(items), "model": model}
