"""
Application configuration.

All settings are read from environment variables (or a local `.env` file) using
pydantic-settings. This keeps secrets and environment-specific values out of the
source code, which is a requirement for any production / enterprise deployment.
"""

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Core app ---
    APP_NAME: str = "Vibe Control"
    ENVIRONMENT: str = "development"  # development | production
    DEBUG: bool = True

    # --- Database ---
    # Async by default. Local dev uses aiosqlite; production uses asyncpg (Postgres).
    #   local: sqlite+aiosqlite:///./vibe_control.db
    #   prod:  postgresql+asyncpg://USER:PASS@HOST:5432/DB
    DATABASE_URL: str = "sqlite+aiosqlite:///./vibe_control.db"

    # --- Security / JWT ---
    # Generate a strong secret with:  python -c "import secrets; print(secrets.token_urlsafe(64))"
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    EMAIL_VERIFICATION_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # --- Email OTP (signup verification) ---
    OTP_LENGTH: int = 6
    OTP_EXPIRE_MINUTES: int = 10  # code validity window
    OTP_MAX_ATTEMPTS: int = 5  # wrong tries before the code is invalidated
    OTP_RESEND_COOLDOWN_SECONDS: int = 60  # min gap between "resend code" requests

    # --- CORS ---
    # Comma-separated list of allowed origins for the browser frontend.
    BACKEND_CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- File uploads ---
    UPLOAD_DIR: str = "uploads"
    OUTPUT_DIR: str = "outputs"
    MAX_UPLOAD_MB: int = 15
    ALLOWED_IMAGE_TYPES: str = "image/jpeg,image/png,image/webp"

    # --- AI style-transfer engine ---
    # "tfhub"    -> local, free, open-source (TensorFlow Hub Magenta model)
    # "replicate"-> optional paid API for higher quality / generative / video
    STYLE_ENGINE: str = "tfhub"
    TFHUB_MODEL_URL: str = (
        "https://tfhub.dev/google/magenta/arbitrary-image-stylization-v1-256/2"
    )
    STYLE_OUTPUT_MAX_DIM: int = 1024  # cap output size for speed/memory
    REPLICATE_API_TOKEN: str = ""  # only needed if STYLE_ENGINE == "replicate"

    # --- SMTP / email ---
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "Vibe Control <no-reply@vibecontrol.app>"
    SMTP_TLS: bool = True
    EMAIL_ENABLED: bool = False  # keep False in dev to skip real sending

    # Public URL of the frontend, used when building links inside emails.
    FRONTEND_URL: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_image_types(self) -> List[str]:
        return [t.strip() for t in self.ALLOWED_IMAGE_TYPES.split(",") if t.strip()]

    @field_validator("SECRET_KEY")
    @classmethod
    def _warn_default_secret(cls, v: str) -> str:
        # We do not hard-fail here so the app boots in dev, but production
        # deployments should always override this value.
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so settings are parsed only once per process."""
    return Settings()


settings = get_settings()
