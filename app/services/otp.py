"""
OTP service — issue, resend, and verify signup verification codes.

Security properties:
  * Codes are random and cryptographically generated.
  * Only a bcrypt hash of the code is stored; the plaintext is only emailed.
  * Codes expire (OTP_EXPIRE_MINUTES) and allow a limited number of wrong
    attempts (OTP_MAX_ATTEMPTS) before being invalidated — this makes a 6-digit
    code safe against brute force.
  * Resends are rate-limited (OTP_RESEND_COOLDOWN_SECONDS) to prevent email abuse.
"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import security
from app.models.otp import EmailOTP
from app.models.user import User
from app.services import email as email_service


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(dt: datetime) -> datetime:
    """Normalise a datetime to tz-aware UTC (SQLite returns naive datetimes)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def _get_otp(db: AsyncSession, user_id: int) -> EmailOTP | None:
    result = await db.execute(select(EmailOTP).where(EmailOTP.user_id == user_id))
    return result.scalar_one_or_none()


async def issue_otp(db: AsyncSession, user: User) -> None:
    """Generate a fresh code, store its hash, and email it. Upserts one row/user."""
    code = security.generate_otp_code()
    otp = await _get_otp(db, user.id)
    now = _now()
    expires = now + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

    if otp is None:
        otp = EmailOTP(
            user_id=user.id,
            code_hash=security.hash_otp(code),
            expires_at=expires,
            attempts=0,
            last_sent_at=now,
        )
        db.add(otp)
    else:
        otp.code_hash = security.hash_otp(code)
        otp.expires_at = expires
        otp.attempts = 0
        otp.last_sent_at = now

    await db.commit()

    # Send after commit so the user only gets a code that's actually stored.
    email_service.send_otp_email(user.email, user.full_name, code)


async def resend_otp(db: AsyncSession, user: User) -> None:
    """Re-issue a code, enforcing the resend cooldown."""
    otp = await _get_otp(db, user.id)
    if otp is not None:
        elapsed = (_now() - _ensure_utc(otp.last_sent_at)).total_seconds()
        remaining = settings.OTP_RESEND_COOLDOWN_SECONDS - elapsed
        if remaining > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {int(remaining) + 1}s before requesting a new code.",
            )
    await issue_otp(db, user)


async def verify_user_otp(db: AsyncSession, user: User, code: str) -> None:
    """Validate a submitted code. On success, mark the user verified.

    Raises HTTPException with a clear message on any failure path.
    """
    otp = await _get_otp(db, user.id)
    if otp is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No verification code found. Please request a new one.",
        )

    if _now() > _ensure_utc(otp.expires_at):
        await db.delete(otp)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This code has expired. Please request a new one.",
        )

    if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
        await db.delete(otp)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many incorrect attempts. Please request a new code.",
        )

    if not security.verify_otp(code, otp.code_hash):
        otp.attempts += 1
        await db.commit()
        remaining = settings.OTP_MAX_ATTEMPTS - otp.attempts
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Incorrect code. {remaining} attempt(s) left.",
        )

    # Success — verify the account and consume the code.
    user.is_verified = True
    await db.delete(otp)
    await db.commit()
