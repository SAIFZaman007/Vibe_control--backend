"""
Authentication routes (async): registration + 6-digit OTP email verification.

Signup flow
-----------
1. POST /api/auth/register        -> creates an (unverified) account, emails a code
2. POST /api/auth/verify-otp      -> checks the code, verifies the account, returns a JWT
3. POST /api/auth/resend-otp      -> re-sends a code (rate-limited)

Forgot password flow
---------------------
4. POST /api/auth/forgot-password -> emails a reset link if the account exists
5. POST /api/auth/reset-password  -> consumes the link's token, sets a new password
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.database import get_db
from app.models.user import User
from app.schemas.otp import MessageResponse, OTPResend, OTPVerify, RegisterResponse
from app.schemas.password_reset import ForgotPasswordRequest, ResetPasswordConfirm
from app.schemas.token import Token
from app.schemas.user import UserCreate
from app.services import otp as otp_service
from app.services import password_reset as password_reset_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await _get_user_by_email(db, payload.email)
    if existing:
        if existing.is_verified:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )
        # Unverified re-registration: resend a code (respecting the cooldown) so
        # the user isn't stuck, without creating a duplicate account.
        try:
            await otp_service.resend_otp(db, existing)
        except HTTPException as exc:
            if exc.status_code != status.HTTP_429_TOO_MANY_REQUESTS:
                raise
        return RegisterResponse(
            message="We sent a verification code to your email.", email=existing.email
        )

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name.strip(),
        hashed_password=security.hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Generate + email the OTP.
    await otp_service.issue_otp(db, user)

    return RegisterResponse(
        message="We sent a verification code to your email.", email=user.email
    )


@router.post("/verify-otp", response_model=Token)
async def verify_otp(payload: OTPVerify, db: AsyncSession = Depends(get_db)):
    user = await _get_user_by_email(db, payload.email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
        )
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already verified. Please log in.",
        )

    # Raises with a clear message on any failure; marks the user verified on success.
    await otp_service.verify_user_otp(db, user, payload.code.strip())

    # Auto-login: return an access token now that the account is verified.
    return Token(access_token=security.create_access_token(user.id))


@router.post("/resend-otp", response_model=MessageResponse)
async def resend_otp(payload: OTPResend, db: AsyncSession = Depends(get_db)):
    user = await _get_user_by_email(db, payload.email)
    # Don't reveal whether the email exists; respond the same either way.
    if user is None or user.is_verified:
        return MessageResponse(message="If that account needs verification, a code has been sent.")
    await otp_service.resend_otp(db, user)
    return MessageResponse(message="A new verification code has been sent.")


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """OAuth2 password flow. `username` carries the email."""
    user = await _get_user_by_email(db, form_data.username)
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled."
        )
    if not user.is_verified:
        # 403 with a stable, machine-readable detail the frontend routes on.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="EMAIL_NOT_VERIFIED",
        )

    return Token(access_token=security.create_access_token(user.id))


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Always responds identically — never reveals whether the email exists."""
    user = await _get_user_by_email(db, payload.email)
    if user is not None and user.is_active:
        try:
            await password_reset_service.request_password_reset(db, user)
        except HTTPException as exc:
            if exc.status_code != status.HTTP_429_TOO_MANY_REQUESTS:
                raise
    return MessageResponse(
        message="If an account exists for that email, we've sent a reset link."
    )


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(payload: ResetPasswordConfirm, db: AsyncSession = Depends(get_db)):
    await password_reset_service.reset_password(db, payload.token, payload.new_password)