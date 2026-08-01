"""Favorite-filter routes (async): bookmark the style presets a user likes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.filter import FavoriteFilter
from app.models.user import User
from app.schemas.filter import FavoriteCreate, FavoritePublic
from app.services import style_catalog

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


@router.get("", response_model=list[FavoritePublic])
async def list_favorites(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(FavoriteFilter)
        .where(FavoriteFilter.owner_id == current_user.id)
        .order_by(FavoriteFilter.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=FavoritePublic, status_code=status.HTTP_201_CREATED)
async def add_favorite(
    payload: FavoriteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.style_key not in style_catalog.PRESET_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown style_key."
        )
    fav = FavoriteFilter(owner_id=current_user.id, style_key=payload.style_key)
    db.add(fav)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Already in favorites."
        )
    await db.refresh(fav)
    return fav


@router.delete("/{style_key}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(
    style_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FavoriteFilter).where(
            FavoriteFilter.owner_id == current_user.id,
            FavoriteFilter.style_key == style_key,
        )
    )
    fav = result.scalar_one_or_none()
    if fav is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not favorited.")
    await db.delete(fav)
    await db.commit()
