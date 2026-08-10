"""
PasswordResetToken model — stores a hashed, expiring "forgot password" link per user.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # One active reset link per user — requesting a new one invalidates the last.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    # SHA-256 digest of the token, NOT bcrypt. The raw token carries 256 bits of
    # entropy (see services/password_reset.py), so — unlike a password or a short
    # numeric OTP — a fast, deterministic hash doesn't weaken it, and it lets us
    # look the row up by an indexed column in a single query instead of scanning
    # every outstanding token and bcrypt-comparing each one.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship()