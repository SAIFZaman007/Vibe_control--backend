"""
Security primitives: password hashing and JWT handling.

We use `bcrypt` directly (rather than passlib) to avoid version-compatibility
issues, and `PyJWT` for signing/verifying tokens. This module is intentionally
small and self-contained so the "custom authentication system" the client
reserved space for can be built on top of it without surprises.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.config import settings

# --- Password hashing -------------------------------------------------------


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with a per-password random salt."""
    pwd_bytes = plain_password.encode("utf-8")
    hashed = bcrypt.hashpw(pwd_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Constant-time comparison of a plaintext password against its hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


# --- JSON Web Tokens --------------------------------------------------------


def _create_token(subject: str, expires_delta: timedelta, purpose: str) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + expires_delta,
        "purpose": purpose,  # "access" or "email_verify"
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(subject: str | int) -> str:
    return _create_token(
        str(subject),
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        purpose="access",
    )


def create_email_verification_token(subject: str | int) -> str:
    return _create_token(
        str(subject),
        timedelta(minutes=settings.EMAIL_VERIFICATION_EXPIRE_MINUTES),
        purpose="email_verify",
    )


def decode_token(token: str, expected_purpose: str) -> str | None:
    """Return the token subject if valid and of the expected purpose, else None."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except jwt.PyJWTError:
        return None

    if payload.get("purpose") != expected_purpose:
        return None
    return payload.get("sub")
