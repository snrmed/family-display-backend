# Config defaults; override via env vars
import os

RAW6_PALETTE = (255,255,255), (0,0,0), (230,0,0), (250,220,0), (0,90,200), (0,160,100)

def _env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.lower() in ('1','true','yes','on')

# Curated prompt themes for e‑ink‑friendly abstract/poster art
THEMES = [
    "bold abstract geometric collage, kid-friendly, high contrast, flat poster colors, paper cut shapes",
    "playful abstract waves and blobs, graphic poster, vibrant flat color blocks, soft paper texture",
    "minimal Bauhaus geometry, primary shapes, clean layout, poster design, balanced composition",
    "circles and arcs motif, layered stickers, cutout style, high contrast, children’s art poster",
    "paper collage with rounded shapes, gentle gradients to flat blocks, modern nursery poster",
    "grid-based poster, stripes and dots, pop-art flavor, crisp edges, screenprint feel",
    "tape & sticker scrapbook look, bright solids, chunky shapes, whimsical composition"
]

# Rotate themes by weekday (Mon=0..Sun=6)
WEEKDAY_THEME_INDEX = {0:0, 1:1, 2:2, 3:3, 4:4, 5:5, 6:6}

CFG = {
    "width": int(os.getenv("WIDTH", 800)),
    "height": int(os.getenv("HEIGHT", 480)),
    "variants_per_week": int(os.getenv("VARIANTS_PER_WEEK", 4)),
    "overlay_style": os.getenv("OVERLAY_STYLE", "glass"),  # glass | card | minimal
    "use_hf": _env_bool("USE_HF", True),
    # Default high-aesthetic model; overridden by GEN_SPEED_MODE or HF_MODEL
    "hf_model": os.getenv("HF_MODEL", "playgroundai/playground-v2.5-1024px-aesthetic"),
    "gen_speed_mode": _env_bool("GEN_SPEED_MODE", False),  # if true => use SDXL-Turbo
    "project_id": os.getenv("PROJECT_ID"),
    "gcs_bucket": os.getenv("GCS_BUCKET"),
    "region": os.getenv("REGION", "australia-southeast1"),
    "signed_urls": _env_bool("SIGNED_URLS", False),
    "raw6_map": _env_bool("RAW6_MAP", False),
}
