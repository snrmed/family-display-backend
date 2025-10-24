from __future__ import annotations
from datetime import date, datetime
from PIL import Image, ImageDraw, ImageFont
import random

from config import RAW6_PALETTE, THEMES, WEEKDAY_THEME_INDEX, CFG

def iso_week_str(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"

def weekday_theme() -> str:
    idx = WEEKDAY_THEME_INDEX.get(datetime.utcnow().weekday(), 0)
    return THEMES[idx % len(THEMES)]

def _try_fonts(candidates, size):
    for name in candidates:
        try:
            return ImageFont.truetype(name, size=size)
        except Exception:
            continue
    return None

def load_font(_preferred_path: str, size: int):
    # Try preferred TTF path first (assets or custom system path)
    try:
        return ImageFont.truetype(_preferred_path, size=size)
    except Exception:
        pass
    # Try custom fonts fetched by Dockerfile
    f = _try_fonts(["/usr/share/fonts/truetype/custom/Nunito-ExtraBold.ttf",
                    "/usr/share/fonts/truetype/custom/Baloo2-Bold.ttf"], size)
    if f: return f
    # Roboto
    f = _try_fonts(["Roboto-Bold.ttf", "/usr/share/fonts/truetype/roboto/Roboto-Bold.ttf",
                    "Roboto-Regular.ttf"], size)
    if f: return f
    # DejaVu
    f = _try_fonts(["DejaVuSans-Bold.ttf", "DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"], size)
    if f: return f
    # Last resort
    return ImageFont.load_default()

def pick_fallback_bg(W: int, H: int):
    img = Image.new("RGB", (W, H), (255,255,255))
    dr = ImageDraw.Draw(img)
    for _ in range(20):
        x0 = random.randint(0, W-60); y0 = random.randint(0, H-60)
        x1 = x0 + random.randint(40, 260); y1 = y0 + random.randint(40, 220)
        color = (random.randint(0,255), random.randint(0,255), random.randint(0,255))
        if random.random() < 0.5:
            dr.ellipse([x0,y0,x1,y1], fill=color)
        else:
            dr.rectangle([x0,y0,x1,y1], fill=color)
    return img

def nearest_palette_color(rgb, palette):
    r,g,b = rgb
    best = None
    bestd = 1e9
    for pr,pg,pb in palette:
        d = (r-pr)**2 + (g-pg)**2 + (b-pb)**2
        if d < bestd:
            bestd = d
            best = (pr,pg,pb)
    return best

def map_to_raw6(img):
    img = img.convert("RGB")
    W,H = img.size
    px = img.load()
    pal = RAW6_PALETTE
    for y in range(H):
        for x in range(W):
            px[x,y] = nearest_palette_color(px[x,y], pal)
    return img
