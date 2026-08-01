# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy uv binary directly
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency definition
COPY pyproject.toml ./

# Install dependencies into system Python directly
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy application source code
COPY app ./app

# Create required runtime directories
RUN mkdir -p uploads outputs

EXPOSE 8000

# Healthcheck running every 30 seconds
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/').read()" || exit 1

# Execute uvicorn via python module invocation
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]