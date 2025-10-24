# FrameOS / Family Display Backend
Now with:
- **Default HF model**: `playgroundai/playground-v2.5-1024px-aesthetic`
- **Speed mode**: set `GEN_SPEED_MODE=true` to use `stabilityai/sdxl-turbo`
- **Prompt THEMES**: curated styles + weekday rotation (Mon–Sun)

Env summary:
- `USE_HF=true` (default) — enable HF generation
- `HF_MODEL` — overrides model (else see defaults above)
- `GEN_SPEED_MODE=true|false` — turbo switch (defaults to false)
- `VARIANTS_PER_WEEK` — default 4
- `RAW6_MAP=true|false` — optional palette mapping
