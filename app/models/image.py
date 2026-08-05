"""
ProcessedImage model — one row per stylized image a user creates.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

class ProcessedImage(Base):
    __tablename__ = "processed_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    title: Mapped[str] = mapped_column(String(160), default="Untitled")
    # The style preset key (e.g. "starry_night") or "custom" for uploaded styles.
    style_key: Mapped[str] = mapped_column(String(80), nullable=False)

    # Stored filenames (relative to UPLOAD_DIR / OUTPUT_DIR).
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    output_filename: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="images")