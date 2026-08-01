"""
File-storage helpers.

Centralises upload validation (type + size), safe unique filenames, and path
resolution for the uploads/outputs directories. Keeping this here means every
route saves files the same, safe way.
"""

import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.config import settings

UPLOAD_DIR = Path(settings.UPLOAD_DIR)
OUTPUT_DIR = Path(settings.OUTPUT_DIR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_EXT_BY_TYPE = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def _validate_image(file: UploadFile, data: bytes) -> None:
    if file.content_type not in settings.allowed_image_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {', '.join(settings.allowed_image_types)}",
        )
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max {settings.MAX_UPLOAD_MB} MB.",
        )
    # Verify the bytes really are a decodable image (don't trust the header).
    try:
        from io import BytesIO

        Image.open(BytesIO(data)).verify()
    except (UnidentifiedImageError, Exception):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File is not a valid image."
        )


async def save_upload(file: UploadFile, directory: Path) -> str:
    """Validate and persist an uploaded image. Returns the stored filename."""
    data = await file.read()
    _validate_image(file, data)
    ext = _EXT_BY_TYPE.get(file.content_type, ".img")
    filename = f"{uuid.uuid4().hex}{ext}"
    (directory / filename).write_bytes(data)
    return filename


def upload_path(filename: str) -> Path:
    return UPLOAD_DIR / filename


def output_path(filename: str) -> Path:
    return OUTPUT_DIR / filename


def new_output_name() -> str:
    return f"{uuid.uuid4().hex}.jpg"


def safe_remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
