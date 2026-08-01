"""
Vibe Control — FastAPI application entry point.

Run in development with:
    uv run uvicorn app.main:app --reload

Interactive API docs are available at /docs once running.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routers import auth, filters, images, users
from app.services import style_catalog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vibe")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    logger.info("Starting %s (%s)", settings.APP_NAME, settings.ENVIRONMENT)
    init_db()  # create tables if they don't exist
    style_catalog.ensure_style_assets()  # generate style thumbnails/refs once
    yield
    # --- shutdown ---
    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=f"{settings.APP_NAME} API",
    version="1.0.0",
    description="AI style-transfer studio — upload an image, apply a vibe, download the result.",
    lifespan=lifespan,
)

# CORS — allow the React frontend origin(s) to call the API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve only the non-sensitive style thumbnails as static assets.
_styles_dir = Path(__file__).resolve().parent / "styles"
app.mount("/static/styles", StaticFiles(directory=_styles_dir), name="styles")

# Routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(images.router)
app.include_router(filters.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "app": settings.APP_NAME, "engine": settings.STYLE_ENGINE}


@app.get("/", tags=["meta"])
def root():
    return {"message": "Vibe Control API. See /docs for interactive documentation."}
