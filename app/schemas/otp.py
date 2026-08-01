"""Schemas for the OTP-based signup verification flow."""

from pydantic import BaseModel, EmailStr, Field


class RegisterResponse(BaseModel):
    """Returned after registration — no token yet, verification is required first."""

    message: str
    email: EmailStr


class OTPVerify(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=10)


class OTPResend(BaseModel):
    email: EmailStr


class MessageResponse(BaseModel):
    message: str
