"""
Password reset service — issue and verify "forgot password" email links.

Security properties:
  * The token is a 256-bit value from `secrets.token_urlsafe`, so brute-forcing
    it is infeasible regardless of hashing speed. We store its SHA-256 digest
    (see models/password_reset.py for why that's safe here) rather than bcrypt.
  * Links expire (PASSWORD_RESET_EXPIRE_MINUTES) and are single-use — the row
    is deleted the moment it's consumed, expired, or superseded by a new request.
  * Requests are rate-limited (PASSWORD_RESET_COOLDOWN_SECONDS) to prevent
    email abuse, mirroring the signup OTP flow.
  * The router never reveals whether a given email has an account — see
    routers/auth.py — this module only runs once that check has passed.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import security
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.services import email as email_service


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(dt: datetime) -> datetime:
    """Normalise a datetime to tz-aware UTC (SQLite returns naive datetimes)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def _get_token_by_user(db: AsyncSession, user_id: int) -> PasswordResetToken | None:
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _get_token_by_hash(db: AsyncSession, token_hash: str) -> PasswordResetToken | None:
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    return result.scalar_one_or_none()


async def request_password_reset(db: AsyncSession, user: User) -> None:
    """Issue a fresh reset link for `user` and email it. Upserts one row/user."""
    existing = await _get_token_by_user(db, user.id)
    now = _now()

    if existing is not None:
        elapsed = (now - _ensure_utc(existing.last_sent_at)).total_seconds()
        remaining = settings.PASSWORD_RESET_COOLDOWN_SECONDS - elapsed
        if remaining > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {int(remaining) + 1}s before requesting another reset link.",
            )

    raw_token = secrets.token_urlsafe(32)
    expires = now + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES)

    if existing is None:
        existing = PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(raw_token),
            expires_at=expires,
            last_sent_at=now,
        )
        db.add(existing)
    else:
        existing.token_hash = _hash_token(raw_token)
        existing.expires_at = expires
        existing.last_sent_at = now

    await db.commit()

    # Send after commit so we never email a link that isn't actually stored.
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"
    email_service.send_password_reset_email(user.email, user.full_name, reset_url)


async def reset_password(db: AsyncSession, raw_token: str, new_password: str) -> None:
    """Validate a reset token and set the new password.

    Raises HTTPException with a clear message on any failure path.
    """
    record = await _get_token_by_hash(db, _hash_token(raw_token))
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has already been used.",
        )

    if _now() > _ensure_utc(record.expires_at):
        await db.delete(record)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has expired. Please request a new one.",
        )

    user = await db.get(User, record.user_id)
    if user is None:
        await db.delete(record)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="This reset link is invalid."
        )

    # Success — set the new password and consume the token.
    user.hashed_password = security.hash_password(new_password)
    await db.delete(record)
    await db.commit()