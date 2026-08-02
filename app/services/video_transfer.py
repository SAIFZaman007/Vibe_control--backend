"""
Video style-transfer.

Mirrors the image pipeline: a video is decoded, each frame is stylized with the
SAME engine as images (`style_transfer.stylize_pil` — tfhub with Pillow fallback),
and the frames are re-encoded to an MP4. The original audio track is muxed back in.

Everything here is open-source:
  * imageio + imageio-ffmpeg read/write the video. The ffmpeg binary ships *inside*
    the imageio-ffmpeg wheel, so there is no system ffmpeg to install — clean for
    Docker / Coolify.
  * The stylization itself is the local tfhub/pillow engine (no paid API).

To keep jobs quick and bounded (important for a synchronous request), we cap the
clip length, the output resolution, and the output frame rate.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image

from app.config import settings
from app.services import style_catalog
from app.services.style_transfer import stylize_pil

logger = logging.getLogger("vibe.video")


class VideoProcessingError(Exception):
    """Raised for user-facing video problems (unreadable, too long, no frames)."""


def _even(n: int) -> int:
    """Nearest even integer >= 2 (yuv420p / libx264 require even dimensions)."""
    n = int(round(n))
    if n < 2:
        return 2
    return n if n % 2 == 0 else n - 1


def _target_size(width: int, height: int) -> tuple[int, int]:
    """Downscale to fit VIDEO_OUTPUT_MAX_DIM (never upscale); force even dims."""
    max_dim = settings.VIDEO_OUTPUT_MAX_DIM
    scale = min(1.0, max_dim / max(width, height))
    return _even(width * scale), _even(height * scale)


def _resolve_style_image(
    style_key: str, custom_style_path: str | Path | None
) -> Image.Image | None:
    """Load the style reference image once (custom upload or preset)."""
    if custom_style_path is not None:
        return Image.open(custom_style_path).convert("RGB")
    ref = style_catalog.style_reference_path(style_key)
    if ref is not None and Path(ref).exists():
        return Image.open(ref).convert("RGB")
    return None


def _mux_audio(silent_video: Path, source_with_audio: Path, output: Path) -> bool:
    """
    Copy the stylized (silent) video and add the source's audio track.

    Best-effort: returns True on success. `-map 1:a:0?` makes audio optional, so a
    source without audio still succeeds (producing a video-only file).
    """
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y",
        "-i", str(silent_video),
        "-i", str(source_with_audio),
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0?",
        "-shortest",
        str(output),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
        if proc.returncode == 0 and output.exists() and output.stat().st_size > 0:
            return True
        logger.warning("Audio mux failed (rc=%s); keeping silent video.", proc.returncode)
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.warning("Audio mux errored (%s); keeping silent video.", exc)
    return False


def stylize_video_to_file(
    content_path: str | Path,
    output_path: str | Path,
    style_key: str,
    custom_style_path: str | Path | None = None,
) -> None:
    """
    Stylize every frame of `content_path` and write an MP4 to `output_path`.

    Raises VideoProcessingError for problems the user can act on (unreadable file,
    clip too long). The signature mirrors `style_transfer.stylize_to_file`.
    """
    content_path = Path(content_path)
    output_path = Path(output_path)

    try:
        reader = imageio.get_reader(content_path)
    except Exception as exc:
        raise VideoProcessingError("Could not read the video file.") from exc

    meta = reader.get_meta_data()
    fps = meta.get("fps") or 0
    if not fps or fps <= 0:
        fps = 24.0

    # Reject over-long clips up front when the duration is known.
    duration = meta.get("duration")
    if duration and duration > settings.MAX_VIDEO_SECONDS + 0.5:
        reader.close()
        raise VideoProcessingError(
            f"Video is too long. Please upload a clip up to {settings.MAX_VIDEO_SECONDS} seconds."
        )

    # Subsample frames to cap the output frame rate (preserves real-time duration).
    cap = settings.VIDEO_OUTPUT_FPS_CAP
    stride = max(1, round(fps / cap)) if fps > cap else 1
    out_fps = fps / stride

    # Hard safety nets so a mis-reported fps/duration can't run away.
    max_input_frames = int((settings.MAX_VIDEO_SECONDS + 1) * fps) + 2
    max_output_frames = int(settings.MAX_VIDEO_SECONDS * out_fps) + 2

    style_img = _resolve_style_image(style_key, custom_style_path)

    tmp_silent = Path(tempfile.mkstemp(suffix=".mp4")[1])
    writer = None
    target: tuple[int, int] | None = None
    written = 0

    try:
        for index, frame in enumerate(reader):
            if index > max_input_frames:
                reader.close()
                if writer is not None:
                    writer.close()
                raise VideoProcessingError(
                    f"Video is too long. Please upload a clip up to "
                    f"{settings.MAX_VIDEO_SECONDS} seconds."
                )
            if index % stride != 0:
                continue
            if written >= max_output_frames:
                break

            img = Image.fromarray(frame).convert("RGB")
            if target is None:
                target = _target_size(img.width, img.height)
                writer = imageio.get_writer(
                    tmp_silent,
                    fps=out_fps,
                    codec="libx264",
                    macro_block_size=1,
                    pixelformat="yuv420p",
                    ffmpeg_log_level="error",
                    output_params=["-preset", "veryfast", "-movflags", "+faststart", "-crf", "23"],
                )

            if img.size != target:
                img = img.resize(target, Image.LANCZOS)

            styled = stylize_pil(img, style_key, style_img)
            if styled.size != target:  # keep every frame identical in size
                styled = styled.resize(target, Image.LANCZOS)

            writer.append_data(np.asarray(styled))
            written += 1

        reader.close()
        if writer is None or written == 0:
            raise VideoProcessingError("The video contained no readable frames.")
        writer.close()
        writer = None

        # Add the original audio back (best-effort; falls back to silent video).
        if not _mux_audio(tmp_silent, content_path, output_path):
            shutil.copyfile(tmp_silent, output_path)
    finally:
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass
        try:
            tmp_silent.unlink(missing_ok=True)
        except OSError:
            pass