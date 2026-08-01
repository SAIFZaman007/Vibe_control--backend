"""Schemas for style presets and processed-image records."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StylePreset(BaseModel):
    """A selectable artistic style shown in the frontend gallery."""

    key: str
    name: str
    description: str
    thumbnail_url: str


class ProcessedImagePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    style_key: str
    original_url: str
    output_url: str
    created_at: datetime
