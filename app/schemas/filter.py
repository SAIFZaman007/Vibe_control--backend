"""Schemas for favorite (bookmarked) style filters."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FavoriteCreate(BaseModel):
    style_key: str


class FavoritePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    style_key: str
    created_at: datetime
