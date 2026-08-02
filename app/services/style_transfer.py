"""
Style-transfer engine.

Design goals:
  * Pluggable: the active engine is chosen by `settings.STYLE_ENGINE`.
  * Robust: if the heavy AI engine is unavailable at runtime, we fall back to a
    dependency-light Pillow filter so the product never hard-fails on a demo.
  * Swappable model: the AI model is loaded lazily and behind one function, so it
    can be replaced (e.g. with a paid API) without touching the routers.

Engines
-------
tfhub      Local, free, open-source. TensorFlow Hub "Magenta arbitrary image
           stylization" — a pre-trained model that transfers the colour/texture
           of any style image onto any content image. Runs on CPU.
pillow     No ML dependency. Deterministic artistic filters keyed by style. Great
           for quick local runs, CI, or machines without TensorFlow installed.
replicate  Optional paid API (pay-per-second) for higher quality / generative /
           video work. Only used if a REPLICATE_API_TOKEN is configured.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from app.config import settings
from app.services import style_catalog

logger = logging.getLogger("vibe.style")

# The TF Hub model is expensive to load, so we cache it for the process lifetime.
_tf_model = None
_tf_import_ok: bool | None = None


# --- Image helpers ----------------------------------------------------------


def _load_rgb(path: str | Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def _cap_size(img: Image.Image, max_dim: int) -> Image.Image:
    if max(img.size) <= max_dim:
        return img
    scale = max_dim / max(img.size)
    new_size = (int(img.width * scale), int(img.height * scale))
    return img.resize(new_size, Image.LANCZOS)


# --- Engine: TensorFlow Hub (Magenta) --------------------------------------


def _ensure_tf():
    """Import TensorFlow lazily and load the Magenta model once."""
    global _tf_model, _tf_import_ok
    if _tf_import_ok is False:
        return None
    if _tf_model is not None:
        return _tf_model
    try:
        import tensorflow as tf  # noqa: F401
        import tensorflow_hub as hub

        logger.info("Loading TF Hub style model: %s", settings.TFHUB_MODEL_URL)
        _tf_model = hub.load(settings.TFHUB_MODEL_URL)
        _tf_import_ok = True
        return _tf_model
    except Exception as exc:  # pragma: no cover - depends on environment
        logger.warning("TensorFlow engine unavailable (%s); using Pillow fallback.", exc)
        _tf_import_ok = False
        return None


def _to_tensor(img: Image.Image):
    import tensorflow as tf

    arr = np.asarray(img, dtype=np.float32) / 255.0
    return tf.constant(arr)[tf.newaxis, ...]


def _tfhub_stylize(content: Image.Image, style: Image.Image) -> Image.Image:
    import tensorflow as tf

    model = _ensure_tf()
    if model is None:
        raise RuntimeError("TF model not available")

    content = _cap_size(content, settings.STYLE_OUTPUT_MAX_DIM)
    # The Magenta model expects the style image at 256x256.
    style_256 = style.resize((256, 256), Image.LANCZOS)

    outputs = model(_to_tensor(content), _to_tensor(style_256))
    stylized = outputs[0]
    arr = (np.array(stylized[0]) * 255).clip(0, 255).astype(np.uint8)
    return Image.fromarray(arr)


# --- Engine: Pillow fallback -----------------------------------------------

# Per-style tweaks so each "vibe" still looks distinct without any ML.
_PILLOW_LOOKS = {
    "neon_dream": dict(saturation=1.9, contrast=1.3, tint=(255, 0, 180), tint_a=0.18),
    "sunset_haze": dict(saturation=1.4, contrast=1.1, tint=(255, 150, 60), tint_a=0.22),
    "ink_wash": dict(saturation=0.0, contrast=1.4, tint=(20, 20, 20), tint_a=0.10),
    "mosaic_pop": dict(saturation=1.7, contrast=1.4, tint=(255, 80, 80), tint_a=0.10),
    "cyber_grid": dict(saturation=1.3, contrast=1.2, tint=(0, 255, 170), tint_a=0.16),
    "pastel_bloom": dict(saturation=0.8, contrast=0.9, tint=(255, 210, 230), tint_a=0.22),
    "vapor_wave": dict(saturation=1.6, contrast=1.1, tint=(200, 120, 255), tint_a=0.20),
    "autumn_oil": dict(saturation=1.3, contrast=1.2, tint=(200, 110, 40), tint_a=0.20),
}


def _pillow_stylize(content: Image.Image, style_key: str) -> Image.Image:
    look = _PILLOW_LOOKS.get(style_key, dict(saturation=1.3, contrast=1.1, tint=None, tint_a=0.0))
    img = _cap_size(content, settings.STYLE_OUTPUT_MAX_DIM)

    # Painterly smoothing to emulate brushwork.
    img = img.filter(ImageFilter.SMOOTH_MORE).filter(ImageFilter.EDGE_ENHANCE)
    img = ImageEnhance.Color(img).enhance(look["saturation"])
    img = ImageEnhance.Contrast(img).enhance(look["contrast"])

    if look.get("tint"):
        overlay = Image.new("RGB", img.size, look["tint"])
        img = Image.blend(img, overlay, look["tint_a"])
    return img


# --- Engine: Replicate (optional paid API) ---------------------------------


def _replicate_stylize(content_path: Path, style_key: str) -> Image.Image:
    """
    Optional higher-quality / generative path via Replicate.

    Replicate hosts many open-source models (e.g. SDXL img2img, fast style
    transfer, and video models) on a cheap pay-per-second basis. Only used when
    a token is configured. See README for cost notes and enabling video.
    """
    import replicate  # imported lazily; only needed for this engine

    client = replicate.Client(api_token=settings.REPLICATE_API_TOKEN)
    with open(content_path, "rb") as f:
        # NOTE: pick a model that fits your budget/quality; this is a template.
        output = client.run(
            "stability-ai/sdxl:latest",
            input={"image": f, "prompt": f"{style_key.replace('_', ' ')} art style"},
        )
    # Replicate returns URLs; fetch the first result.
    import io
    import urllib.request

    url = output[0] if isinstance(output, list) else output
    with urllib.request.urlopen(url) as resp:
        return Image.open(io.BytesIO(resp.read())).convert("RGB")


# --- Public API -------------------------------------------------------------


def stylize_to_file(
    content_path: str | Path,
    output_path: str | Path,
    style_key: str,
    custom_style_path: str | Path | None = None,
) -> None:
    """
    Apply the chosen style to `content_path` and save the result to `output_path`.

    `style_key` is a preset key, or "custom" when `custom_style_path` is provided
    (a user-uploaded style image for arbitrary style transfer).
    """
    content = _load_rgb(content_path)
    engine = settings.STYLE_ENGINE.lower()

    # Resolve the style reference image (preset or custom upload).
    style_img: Image.Image | None = None
    if custom_style_path is not None:
        style_img = _load_rgb(custom_style_path)
    else:
        ref = style_catalog.style_reference_path(style_key)
        if ref is not None and Path(ref).exists():
            style_img = _load_rgb(ref)

    result: Image.Image
    try:
        if engine == "replicate" and settings.REPLICATE_API_TOKEN:
            result = _replicate_stylize(Path(content_path), style_key)
        elif engine == "tfhub" and style_img is not None and _ensure_tf() is not None:
            result = _tfhub_stylize(content, style_img)
        else:
            result = _pillow_stylize(content, style_key)
    except Exception as exc:  # never fail the request — degrade gracefully
        logger.warning("Style engine '%s' failed (%s); falling back to Pillow.", engine, exc)
        result = _pillow_stylize(content, style_key)

    result.save(output_path, "JPEG", quality=92)


def stylize_pil(
    content: Image.Image,
    style_key: str,
    style_img: Image.Image | None = None,
) -> Image.Image:
    """
    Stylize a single in-memory frame and return a new image.

    This is the per-frame primitive used by the video pipeline. It reuses the same
    engine selection as `stylize_to_file` (tfhub with Pillow fallback) but works
    entirely in memory and never raises — a single bad frame degrades to the Pillow
    look instead of failing the whole video. The Replicate engine is intentionally
    not used per-frame (a paid API call per frame would be slow and costly); videos
    run on the local, open-source tfhub/pillow path.
    """
    engine = settings.STYLE_ENGINE.lower()
    try:
        if engine == "tfhub" and style_img is not None and _ensure_tf() is not None:
            return _tfhub_stylize(content, style_img)
    except Exception as exc:
        logger.warning("Per-frame tfhub failed (%s); using Pillow for this frame.", exc)
    return _pillow_stylize(content, style_key)