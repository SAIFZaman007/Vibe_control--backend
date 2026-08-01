"""
Authentication routes: registration, login (JWT), and email verification.

The design keeps auth logic isolated and thin so the client's planned "custom
authentication system" (roles, org accounts, OAuth, etc.) can extend it cleanly.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core import security
from app.database import get_db
from app.models.user import User
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserPublic
from app.services import email as email_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name.strip(),
        hashed_password=security.hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Fire off a verification email (logged to console when EMAIL_ENABLED is False).
    token = security.create_email_verification_token(user.id)
    email_service.send_verification_email(user.email, user.full_name, token)

    return user


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    """
    OAuth2 password flow. `username` field carries the email.

    Using the standard form makes the interactive /docs "Authorize" button work
    out of the box.
    """
    user = db.query(User).filter(User.email == form_data.username.lower()).first()
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

    access_token = security.create_access_token(user.id)
    return Token(access_token=access_token)


@router.post("/verify-email", response_model=UserPublic)
def verify_email(token: str, db: Session = Depends(get_db)):
    user_id = security.decode_token(token, expected_purpose="email_verify")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link.",
        )
    user = db.get(User, int(user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    user.is_verified = True
    db.commit()
    db.refresh(user)
    return user
