"""
FavoriteImage model — lets a user bookmark one of their own creations (a
stylized image or video) for quick access later.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

class FavoriteImage(Base):
    __tablename__ = "favorite_images"
    # A user cannot favorite the same creation twice.
    __table_args__ = (UniqueConstraint("owner_id", "image_id", name="uq_owner_image"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    image_id: Mapped[int] = mapped_column(
        ForeignKey("processed_images.id", ondelete="CASCADE"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="favorite_images")