# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy uv binary directly
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first for optimal layer caching
COPY pyproject.toml ./
# Copy uv.lock if you have one, or comment out if you don't
# COPY uv.lock ./ 

# Install dependencies into system Python directly from pyproject.toml
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy application source code
COPY app ./app

# Create required runtime directories
RUN mkdir -p uploads outputs

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]