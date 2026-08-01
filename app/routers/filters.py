"""Favorite-filter routes: bookmark the style presets a user likes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.filter import FavoriteFilter
from app.models.user import User
from app.schemas.filter import FavoriteCreate, FavoritePublic
from app.services import style_catalog

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


@router.get("", response_model=list[FavoritePublic])
def list_favorites(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return (
        db.query(FavoriteFilter)
        .filter(FavoriteFilter.owner_id == current_user.id)
        .order_by(FavoriteFilter.created_at.desc())
        .all()
    )


@router.post("", response_model=FavoritePublic, status_code=status.HTTP_201_CREATED)
def add_favorite(
    payload: FavoriteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.style_key not in style_catalog.PRESET_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown style_key."
        )
    fav = FavoriteFilter(owner_id=current_user.id, style_key=payload.style_key)
    db.add(fav)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Already in favorites."
        )
    db.refresh(fav)
    return fav


@router.delete("/{style_key}", status_code=status.HTTP_204_NO_CONTENT)
def remove_favorite(
    style_key: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fav = (
        db.query(FavoriteFilter)
        .filter(
            FavoriteFilter.owner_id == current_user.id,
            FavoriteFilter.style_key == style_key,
        )
        .first()
    )
    if fav is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not favorited.")
    db.delete(fav)
    db.commit()
