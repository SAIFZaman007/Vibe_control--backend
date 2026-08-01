"""FavoriteFilter model — lets a user bookmark style presets they like."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FavoriteFilter(Base):
    __tablename__ = "favorite_filters"
    # A user cannot favorite the same style twice.
    __table_args__ = (UniqueConstraint("owner_id", "style_key", name="uq_owner_style"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    style_key: Mapped[str] = mapped_column(String(80), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="favorites")
