"""
Image routes (async) — the core product surface.
"""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models.favorite_image import FavoriteImage
from app.models.image import ProcessedImage
from app.models.user import User
from app.schemas.image import FavoriteImagePublic, ProcessedImagePublic, StylePreset
from app.services import storage, style_catalog
from app.services.style_transfer import stylize_to_file
from app.services.video_transfer import VideoProcessingError, stylize_video_to_file

router = APIRouter(prefix="/api", tags=["images"])

# Map stored-file extensions to how we serve them and whether they're video.
_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm"}
_MEDIA_TYPE_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
}


def _is_video_filename(name: str) -> bool:
    return Path(name).suffix.lower() in _VIDEO_SUFFIXES


def _to_public(img: ProcessedImage, favorited_ids: frozenset[int] = frozenset()) -> dict:
    return {
        "id": img.id,
        "title": img.title,
        "style_key": img.style_key,
        "original_url": f"/api/images/{img.id}/file?variant=original",
        "output_url": f"/api/images/{img.id}/file?variant=output",
        "media_type": "video" if _is_video_filename(img.output_filename) else "image",
        "created_at": img.created_at,
        "is_favorite": img.id in favorited_ids,
    }


@router.get("/styles", response_model=list[StylePreset])
async def list_styles():
    """Public list of the artistic vibes a user can apply."""
    return style_catalog.get_presets_public()


@router.post(
    "/images/stylize",
    response_model=ProcessedImagePublic,
    status_code=status.HTTP_201_CREATED,
)
async def stylize(
    image: UploadFile = File(...),
    style_key: str = Form(...),
    title: str = Form("Untitled"),
    custom_style: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Apply a style to an uploaded image **or video**.

    The same endpoint accepts an image or a video in `image`. A video is stylized
    frame-by-frame with the same engine and returned as a new video; an image is
    returned as a new image. Provide either a preset `style_key`, or
    `style_key="custom"` with a `custom_style` image to transfer an uploaded style.
    """
    using_custom = style_key == "custom"
    if not using_custom and style_key not in style_catalog.PRESET_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown style_key."
        )
    if using_custom and custom_style is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A custom style requires a custom_style image.",
        )

    is_video = storage.is_video_upload(image)
    if is_video and not settings.VIDEO_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Video uploads are currently disabled.",
        )

    # 1. Persist the uploaded content (image or video).
    if is_video:
        original_filename = await storage.save_video_upload(image, storage.UPLOAD_DIR)
    else:
        original_filename = await storage.save_upload(image, storage.UPLOAD_DIR)

    # 2. Persist the custom style image if provided (a style is always an image).
    custom_style_path = None
    if using_custom:
        custom_name = await storage.save_upload(custom_style, storage.UPLOAD_DIR)
        custom_style_path = storage.upload_path(custom_name)

    # 3. Run style transfer -> output file (video is CPU-heavy, so off the event loop).
    if is_video:
        output_filename = storage.new_video_output_name()
        try:
            await run_in_threadpool(
                stylize_video_to_file,
                storage.upload_path(original_filename),
                storage.output_path(output_filename),
                style_key,
                custom_style_path,
            )
        except VideoProcessingError as exc:
            storage.safe_remove(storage.upload_path(original_filename))
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        except Exception:
            storage.safe_remove(storage.upload_path(original_filename))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Video processing failed. Please try a different clip.",
            )
    else:
        output_filename = storage.new_output_name()
        try:
            stylize_to_file(
                content_path=storage.upload_path(original_filename),
                output_path=storage.output_path(output_filename),
                style_key=style_key,
                custom_style_path=custom_style_path,
            )
        except Exception:
            storage.safe_remove(storage.upload_path(original_filename))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Style transfer failed. Please try a different image.",
            )

    # 4. Record the job (same model + fields for images and videos).
    record = ProcessedImage(
        owner_id=current_user.id,
        title=(title or "Untitled").strip()[:160],
        style_key=style_key,
        original_filename=original_filename,
        output_filename=output_filename,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _to_public(record)


async def _favorited_ids_for(user: User, db: AsyncSession) -> frozenset[int]:
    result = await db.execute(
        select(FavoriteImage.image_id).where(FavoriteImage.owner_id == user.id)
    )
    return frozenset(result.scalars().all())


@router.get("/images", response_model=list[ProcessedImagePublic])
async def list_images(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ProcessedImage)
        .where(ProcessedImage.owner_id == current_user.id)
        .order_by(ProcessedImage.created_at.desc())
    )
    favorited_ids = await _favorited_ids_for(current_user, db)
    return [_to_public(i, favorited_ids) for i in result.scalars().all()]


async def _get_owned(image_id: int, user: User, db: AsyncSession) -> ProcessedImage:
    img = await db.get(ProcessedImage, image_id)
    if img is None or img.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found.")
    return img


@router.get("/images/{image_id}", response_model=ProcessedImagePublic)
async def get_image(
    image_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    img = await _get_owned(image_id, current_user, db)
    result = await db.execute(
        select(FavoriteImage.id).where(
            FavoriteImage.owner_id == current_user.id, FavoriteImage.image_id == img.id
        )
    )
    is_fav = result.scalar_one_or_none() is not None
    return _to_public(img, frozenset({img.id}) if is_fav else frozenset())


@router.get("/images/{image_id}/file")
async def get_image_file(
    image_id: int,
    variant: Literal["original", "output"] = "output",
    download: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream the original or stylized file. Ownership is enforced here."""
    img = await _get_owned(image_id, current_user, db)
    if variant == "original":
        path = storage.upload_path(img.original_filename)
    else:
        path = storage.output_path(img.output_filename)

    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing.")

    suffix = path.suffix.lower()
    media_type = _MEDIA_TYPE_BY_SUFFIX.get(suffix, "application/octet-stream")
    filename = f"vibe-control-{img.style_key}-{img.id}{suffix}" if download else None
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,  # setting filename adds Content-Disposition: attachment
    )


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(
    image_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    img = await _get_owned(image_id, current_user, db)
    storage.safe_remove(storage.upload_path(img.original_filename))
    storage.safe_remove(storage.output_path(img.output_filename))
    # Clean up any favorite row explicitly rather than relying on cascade:
    # SQLite doesn't enforce ondelete="CASCADE" unless PRAGMA foreign_keys is
    # turned on (it isn't, here), and img was fetched with a plain db.get()
    # rather than an eager-loaded relationship, so an ORM-level cascade
    # wouldn't reliably fire either. This keeps deletes correct on both
    # SQLite (dev) and Postgres (prod) without depending on either.
    await db.execute(sa_delete(FavoriteImage).where(FavoriteImage.image_id == img.id))
    await db.delete(img)
    await db.commit()


@router.post(
    "/images/{image_id}/favorite",
    response_model=FavoriteImagePublic,
    status_code=status.HTTP_201_CREATED,
)
async def favorite_image(
    image_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bookmark one of the current user's own creations."""
    img = await _get_owned(image_id, current_user, db)
    fav = FavoriteImage(owner_id=current_user.id, image_id=img.id)
    db.add(fav)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Already favorited."
        )
    await db.refresh(fav)
    return fav


@router.delete("/images/{image_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
async def unfavorite_image(
    image_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    img = await _get_owned(image_id, current_user, db)
    result = await db.execute(
        select(FavoriteImage).where(
            FavoriteImage.owner_id == current_user.id, FavoriteImage.image_id == img.id
        )
    )
    fav = result.scalar_one_or_none()
    if fav is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not favorited.")
    await db.delete(fav)
    await db.commit()