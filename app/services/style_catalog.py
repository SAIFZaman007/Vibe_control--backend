"""
Style catalog.

Defines the artistic "vibes" a user can apply and generates a reference image +
thumbnail for each one. The reference images are generated *procedurally* from a
colour palette and a pattern, so they are 100% original and carry no third-party
copyright — important because arbitrary style transfer copies colour and texture
from the style image.

The generated files live in `app/styles/`:
  <key>.jpg        -> full style reference used by the AI engine
  <key>_thumb.jpg  -> small thumbnail shown in the frontend gallery
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
from PIL import Image

STYLES_DIR = Path(__file__).resolve().parent.parent / "styles"
STYLES_DIR.mkdir(parents=True, exist_ok=True)

# Each preset: key, display name, description, palette (RGB), and a pattern.
PRESETS: list[dict] = [
    {
        "key": "neon_dream",
        "name": "Neon Dream",
        "description": "Electric magenta and cyan glow with a nightlife pulse.",
        "palette": [(255, 0, 153), (0, 224, 255), (120, 0, 255), (20, 0, 40)],
        "pattern": "waves",
    },
    {
        "key": "sunset_haze",
        "name": "Sunset Haze",
        "description": "Warm dusk gradient of gold, coral and soft violet.",
        "palette": [(255, 94, 58), (255, 179, 71), (255, 105, 140), (58, 22, 84)],
        "pattern": "gradient",
    },
    {
        "key": "ink_wash",
        "name": "Ink Wash",
        "description": "Monochrome brushwork with calm, papery contrast.",
        "palette": [(15, 15, 15), (90, 90, 90), (200, 200, 200), (245, 243, 236)],
        "pattern": "brush",
    },
    {
        "key": "mosaic_pop",
        "name": "Mosaic Pop",
        "description": "Bold tiled colour blocks with a playful pop feel.",
        "palette": [(230, 57, 70), (29, 53, 87), (244, 162, 97), (42, 157, 143)],
        "pattern": "mosaic",
    },
    {
        "key": "cyber_grid",
        "name": "Cyber Grid",
        "description": "Dark teal circuitry lit by neon-green gridlines.",
        "palette": [(6, 20, 24), (0, 255, 170), (0, 120, 130), (180, 255, 220)],
        "pattern": "grid",
    },
    {
        "key": "pastel_bloom",
        "name": "Pastel Bloom",
        "description": "Soft lavender, mint and blush in a gentle wash.",
        "palette": [(255, 209, 220), (204, 204, 255), (198, 239, 206), (255, 245, 230)],
        "pattern": "waves",
    },
    {
        "key": "vapor_wave",
        "name": "Vapor Wave",
        "description": "Retro pink-and-blue haze with a dreamy horizon.",
        "palette": [(255, 113, 206), (1, 205, 254), (185, 103, 255), (5, 255, 161)],
        "pattern": "gradient",
    },
    {
        "key": "autumn_oil",
        "name": "Autumn Oil",
        "description": "Thick oil strokes in amber, rust and deep umber.",
        "palette": [(153, 46, 22), (221, 120, 40), (240, 190, 90), (60, 30, 15)],
        "pattern": "brush",
    },
]

PRESET_KEYS = {p["key"] for p in PRESETS}


# --- Pattern generators -----------------------------------------------------


def _lerp(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def _gradient(size, palette) -> Image.Image:
    w, h = size
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    stops = palette
    for y in range(h):
        t = y / max(h - 1, 1)
        seg = t * (len(stops) - 1)
        i = min(int(seg), len(stops) - 2)
        color = _lerp(stops[i], stops[i + 1], seg - i)
        arr[y, :, :] = color
    return Image.fromarray(arr)


def _waves(size, palette) -> Image.Image:
    w, h = size
    # Vectorised sinusoidal blend of an accent colour over a base gradient.
    base = np.asarray(_gradient(size, palette), dtype=np.float32)
    xs = np.linspace(0, 6 * math.pi, w)
    ys = np.linspace(0, 6 * math.pi, h)
    wave = (np.sin(xs)[None, :] + np.sin(ys)[:, None]) * 0.25 + 0.5
    accent = np.array(palette[0], dtype=np.float32)
    out = base * (1 - wave[..., None] * 0.5) + accent * (wave[..., None] * 0.5)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def _mosaic(size, palette, tile=48) -> Image.Image:
    w, h = size
    rng = random.Random(sum(palette[0]))
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            color = rng.choice(palette)
            arr[y : y + tile, x : x + tile] = color
    return Image.fromarray(arr)


def _grid(size, palette) -> Image.Image:
    from PIL import ImageDraw

    w, h = size
    img = _gradient(size, [palette[0], palette[2]])
    draw = ImageDraw.Draw(img)
    line = palette[1]
    step = 40
    for x in range(0, w, step):
        draw.line([(x, 0), (x, h)], fill=line, width=2)
    for y in range(0, h, step):
        draw.line([(0, y), (w, y)], fill=line, width=2)
    return img


def _brush(size, palette) -> Image.Image:
    from PIL import ImageDraw

    w, h = size
    rng = random.Random(sum(palette[-1]) + 7)
    img = Image.new("RGB", size, palette[-1])
    draw = ImageDraw.Draw(img)
    for _ in range(900):
        x = rng.randint(0, w)
        y = rng.randint(0, h)
        length = rng.randint(20, 90)
        angle = rng.uniform(0, math.pi)
        x2 = int(x + length * math.cos(angle))
        y2 = int(y + length * math.sin(angle))
        color = rng.choice(palette[:-1])
        draw.line([(x, y), (x2, y2)], fill=color, width=rng.randint(3, 10))
    return img


_GENERATORS = {
    "gradient": _gradient,
    "waves": _waves,
    "mosaic": _mosaic,
    "grid": _grid,
    "brush": _brush,
}


def _make_style_image(preset: dict, size=(512, 512)) -> Image.Image:
    gen = _GENERATORS[preset["pattern"]]
    return gen(size, preset["palette"]).convert("RGB")


def ensure_style_assets() -> None:
    """Generate any missing style reference images / thumbnails. Idempotent."""
    for preset in PRESETS:
        ref_path = STYLES_DIR / f"{preset['key']}.jpg"
        thumb_path = STYLES_DIR / f"{preset['key']}_thumb.jpg"
        if ref_path.exists() and thumb_path.exists():
            continue
        img = _make_style_image(preset)
        img.save(ref_path, "JPEG", quality=90)
        img.resize((256, 256)).save(thumb_path, "JPEG", quality=85)


def get_presets_public(static_prefix: str = "/static/styles") -> list[dict]:
    """Return preset metadata with a public thumbnail URL for the API."""
    return [
        {
            "key": p["key"],
            "name": p["name"],
            "description": p["description"],
            "thumbnail_url": f"{static_prefix}/{p['key']}_thumb.jpg",
        }
        for p in PRESETS
    ]


def style_reference_path(style_key: str) -> Path | None:
    """Filesystem path to a preset's full style reference image, or None."""
    if style_key not in PRESET_KEYS:
        return None
    return STYLES_DIR / f"{style_key}.jpg"
