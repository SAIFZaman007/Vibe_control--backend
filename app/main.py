"""
Vibe Control — FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
    await init_db()  
    style_catalog.ensure_style_assets() 
    yield
    # --- shutdown ---
    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=f"{settings.APP_NAME} API",
    version="1.0.0",
    description="Style-transfer studio — upload an image, apply a vibe, download the result.",
    lifespan=lifespan,
)

# --- Error safeguard (added FIRST so it sits *inside* CORS) -----------------
@app.middleware("http")
async def catch_unhandled_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:  # noqa: BLE001
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error."}
        )


# --- CORS (added LAST so it is the OUTERMOST middleware) --------------------
_origins = settings.cors_origins
_allow_all = "*" in _origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allow_all else _origins,
    allow_credentials=not _allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
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