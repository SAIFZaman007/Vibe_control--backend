"""Expose all models so `from app import models` registers them on the metadata."""

from app.models.filter import FavoriteFilter
from app.models.image import ProcessedImage
from app.models.otp import EmailOTP
from app.models.user import User

__all__ = ["User", "ProcessedImage", "FavoriteFilter", "EmailOTP"]
