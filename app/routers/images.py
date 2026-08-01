"""
Image routes — the core product surface.

  GET  /api/styles                    list available style presets
  POST /api/images/stylize            upload an image + apply a style (AI)
  GET  /api/images                    list the current user's creations
  GET  /api/images/{id}               metadata for one creation
  GET  /api/images/{id}/file          stream original/output (ownership checked)
  DELETE /api/images/{id}             delete a creation and its files

Files are streamed through ownership-checked endpoints rather than served as
open static assets, so one user can never read another user's images.
"""

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.image import ProcessedImage
from app.models.user import User
from app.schemas.image import ProcessedImagePublic, StylePreset
from app.services import storage, style_catalog
from app.services.style_transfer import stylize_to_file

router = APIRouter(prefix="/api", tags=["images"])


def _to_public(img: ProcessedImage) -> dict:
    return {
        "id": img.id,
        "title": img.title,
        "style_key": img.style_key,
        "original_url": f"/api/images/{img.id}/file?variant=original",
        "output_url": f"/api/images/{img.id}/file?variant=output",
        "created_at": img.created_at,
    }


@router.get("/styles", response_model=list[StylePreset])
def list_styles():
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
    db: Session = Depends(get_db),
):
    """
    Apply a style to an uploaded image.

    Provide either a preset `style_key`, or `style_key="custom"` together with a
    `custom_style` image to transfer an arbitrary style you upload.
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

    # 1. Persist the content image.
    original_filename = await storage.save_upload(image, storage.UPLOAD_DIR)

    # 2. Persist the custom style image if provided.
    custom_style_path = None
    if using_custom:
        custom_name = await storage.save_upload(custom_style, storage.UPLOAD_DIR)
        custom_style_path = storage.upload_path(custom_name)

    # 3. Run style transfer -> output file.
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

    # 4. Record the job.
    record = ProcessedImage(
        owner_id=current_user.id,
        title=(title or "Untitled").strip()[:160],
        style_key=style_key,
        original_filename=original_filename,
        output_filename=output_filename,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _to_public(record)


@router.get("/images", response_model=list[ProcessedImagePublic])
def list_images(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    images = (
        db.query(ProcessedImage)
        .filter(ProcessedImage.owner_id == current_user.id)
        .order_by(ProcessedImage.created_at.desc())
        .all()
    )
    return [_to_public(i) for i in images]


def _get_owned(image_id: int, user: User, db: Session) -> ProcessedImage:
    img = db.get(ProcessedImage, image_id)
    if img is None or img.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found.")
    return img


@router.get("/images/{image_id}", response_model=ProcessedImagePublic)
def get_image(
    image_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _to_public(_get_owned(image_id, current_user, db))


@router.get("/images/{image_id}/file")
def get_image_file(
    image_id: int,
    variant: Literal["original", "output"] = "output",
    download: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream the original or stylized file. Ownership is enforced here."""
    img = _get_owned(image_id, current_user, db)
    if variant == "original":
        path = storage.upload_path(img.original_filename)
    else:
        path = storage.output_path(img.output_filename)

    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing.")

    filename = f"vibe-control-{img.style_key}-{img.id}.jpg" if download else None
    return FileResponse(
        path,
        media_type="image/jpeg",
        filename=filename,  # setting filename adds Content-Disposition: attachment
    )


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(
    image_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    img = _get_owned(image_id, current_user, db)
    storage.safe_remove(storage.upload_path(img.original_filename))
    storage.safe_remove(storage.output_path(img.output_filename))
    db.delete(img)
    db.commit()
