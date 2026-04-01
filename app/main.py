"""
Application entry point.

Run locally:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.routes.extract import router as extract_router

# ---------------------------------------------------------------------------
# Logging — configure once here so all modules share the same format
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

settings = get_settings()


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown hooks)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """
    Code before `yield` runs at startup; code after runs at shutdown.
    Add DB connections, model warm-up, etc. here as the project grows.
    """
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    logger.info("LLM endpoint: %s", settings.llm_url)
    yield
    logger.info("Shutting down %s", settings.app_name)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

app.include_router(extract_router)


# ---------------------------------------------------------------------------
# Core routes
# ---------------------------------------------------------------------------

@app.get("/", tags=["Meta"])
async def root() -> dict[str, str]:
    return {"message": f"{settings.app_name} is running!"}


@app.get("/health", tags=["Meta"])
async def app_health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(_, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": f"An unexpected error occurred: {exc}",
        },
    )