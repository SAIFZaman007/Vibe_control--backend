"""
Vibe Control — FastAPI application entry point.

Run in development with:
    uv run uvicorn app.main:app --reload

Interactive API docs are available at /docs once running.
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
    await init_db()  # async: create tables if they don't exist
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

# --- Error safeguard (added FIRST so it sits *inside* CORS) -----------------
# If a route raises an unhandled exception, Starlette's default 500 response is
# generated OUTSIDE the CORS middleware and therefore has no CORS headers — which
# makes the browser report a real server error as a misleading "CORS policy"
# error. Catching it here and returning a JSONResponse lets the response flow back
# out through the CORS middleware, so errors are always debuggable from the client.
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
# The frontend authenticates with a bearer token (not cookies), so credentials
# aren't required. The CORS spec forbids combining `Access-Control-Allow-Origin: *`
# with credentials, so when a wildcard origin is configured we disable credentials
# to keep the wildcard valid. For production, list your exact frontend origin.
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
