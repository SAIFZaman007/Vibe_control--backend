"""Expose all models so `from app import models` registers them on the metadata."""

from app.models.favorite_image import FavoriteImage
from app.models.filter import FavoriteFilter
from app.models.image import ProcessedImage
from app.models.otp import EmailOTP
from app.models.password_reset import PasswordResetToken
from app.models.user import User

__all__ = [
    "User",
    "ProcessedImage",
    "FavoriteFilter",
    "FavoriteImage",
    "EmailOTP",
    "PasswordResetToken",
]