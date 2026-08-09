"""
User model — stores account and authentication data.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)

    # We never store raw passwords — only a bcrypt hash.
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # Reserved for the custom authentication system (roles/permissions).
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships — cascade delete keeps the database clean when a user leaves.
    images: Mapped[list["ProcessedImage"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    favorites: Mapped[list["FavoriteFilter"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    favorite_images: Mapped[list["FavoriteImage"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )