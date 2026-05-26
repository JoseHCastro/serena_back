"""
Serena Backend — FastAPI Application Entry Point

Initializes the FastAPI app with:
  - CORS middleware
  - Global exception handlers
  - API v1 router
  - Health check endpoint
  - Lifespan events (startup/shutdown logging)
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown events.

    Args:
        app: The FastAPI application instance.

    Yields:
        None: Control is yielded to the running application.
    """
    configure_logging()
    logger.info("Starting {} v{}", settings.APP_NAME, settings.APP_VERSION)
    yield
    logger.info("Shutting down {}", settings.APP_NAME)


def create_app() -> FastAPI:
    """Factory function that creates and configures the FastAPI application.

    Returns:
        FastAPI: The fully configured application instance.
    """
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Backend API for Serena — an AI-powered biometric emotional analysis "
            "platform for psychotherapy centers."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # -------------------------------------------------------------------------
    # CORS Middleware
    # -------------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -------------------------------------------------------------------------
    # Global exception handlers
    # -------------------------------------------------------------------------
    register_exception_handlers(app)

    # -------------------------------------------------------------------------
    # API Routers
    # -------------------------------------------------------------------------
    app.include_router(api_v1_router)

    # -------------------------------------------------------------------------
    # Root Route
    # -------------------------------------------------------------------------
    @app.get("/", tags=["Root"], summary="Welcome Endpoint")
    async def root() -> dict:
        """Return a simple welcome message for the API.

        Returns:
            dict: Welcome message and API details.
        """
        return {
            "message": "Welcome to Serena API",
            "version": settings.APP_VERSION,
            "docs": "/docs",
            "health": "/health",
        }

    # -------------------------------------------------------------------------
    # Health check (no auth required — used by Docker healthcheck)
    # -------------------------------------------------------------------------
    @app.get("/health", tags=["Health"], summary="Health check")
    async def health() -> dict:
        """Return a simple health status for load balancer / Docker checks.

        Returns:
            dict: Status and application version.
        """
        return {"status": "ok", "version": settings.APP_VERSION}

    return app


app = create_app()
