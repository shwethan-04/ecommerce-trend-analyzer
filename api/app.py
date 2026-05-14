"""
FastAPI application factory and startup configuration.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import products, scraping, sentiment, trends

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI instance with all routers and middleware attached.
    """
    app = FastAPI(
        title="E-Commerce Trend Analyzer API",
        description=(
            "REST API for scraping, analysing, and predicting e-commerce "
            "product trends from Amazon, Flipkart, and Reddit."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ------------------------------------------------------------------ #
    # CORS middleware
    # ------------------------------------------------------------------ #
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # Tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------ #
    # Routers
    # ------------------------------------------------------------------ #
    app.include_router(products.router)
    app.include_router(trends.router)
    app.include_router(sentiment.router)
    app.include_router(scraping.router)

    # ------------------------------------------------------------------ #
    # Startup / shutdown events
    # ------------------------------------------------------------------ #
    @app.on_event("startup")
    async def on_startup() -> None:
        """Initialise the database on application startup."""
        from database.db import init_db

        logger.info("Application starting up…")
        init_db()
        logger.info("Database ready.")

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        logger.info("Application shutting down.")

    # ------------------------------------------------------------------ #
    # Health-check endpoint
    # ------------------------------------------------------------------ #
    @app.get("/health", tags=["health"])
    async def health_check():
        """Simple liveness probe."""
        return {"status": "ok"}

    return app


# Module-level app instance (used by uvicorn)
app = create_app()
