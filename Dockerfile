# syntax=docker/dockerfile:1
# ---- Vibe Control backend (FastAPI + uv) ----
FROM python:3.12-slim AS base

# System deps for Pillow/numpy wheels are already present in slim; add curl for uv.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install uv (fast Python package manager).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (better layer caching).
COPY pyproject.toml ./
# Add `--extra ai` here if you want the TensorFlow engine baked into the image.
RUN uv pip install --system --no-cache -r <(uv pip compile pyproject.toml 2>/dev/null || echo "") \
    || uv pip install --system --no-cache \
       fastapi "uvicorn[standard]" sqlalchemy pydantic pydantic-settings \
       email-validator python-multipart pyjwt bcrypt pillow numpy

# Copy the application code.
COPY app ./app

# Create runtime dirs.
RUN mkdir -p uploads outputs

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
