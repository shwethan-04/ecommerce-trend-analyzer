"""
Configuration management for the E-Commerce Trend Analyzer.
Reads settings from environment variables / .env file with sensible defaults.
"""

import os
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()


class Config:
    """Central configuration object populated from environment variables."""

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./ecommerce_trends.db")

    # ------------------------------------------------------------------ #
    # API server
    # ------------------------------------------------------------------ #
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # ------------------------------------------------------------------ #
    # Dashboard (Flask)
    # ------------------------------------------------------------------ #
    # Render injects PORT automatically — use it if present
    DASHBOARD_HOST: str = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    DASHBOARD_PORT: int = int(os.getenv("PORT", os.getenv("DASHBOARD_PORT", "5000")))

    # ------------------------------------------------------------------ #
    # Scraping
    # ------------------------------------------------------------------ #
    SCRAPE_DELAY: float = float(os.getenv("SCRAPE_DELAY", "2.0"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))

    # ------------------------------------------------------------------ #
    # ML model
    # ------------------------------------------------------------------ #
    MODEL_PATH: str = os.getenv("MODEL_PATH", "./models/trend_predictor.joblib")

    # ------------------------------------------------------------------ #
    # Misc
    # ------------------------------------------------------------------ #
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Subreddits to monitor for e-commerce trends
    ECOMMERCE_SUBREDDITS: list = [
        "deals",
        "BuyItForLife",
        "frugal",
        "onlineshopping",
        "AmazonDeals",
    ]

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Config DATABASE_URL={self.DATABASE_URL!r} "
            f"API_HOST={self.API_HOST!r} API_PORT={self.API_PORT}>"
        )


# Singleton instance used throughout the project
settings = Config()
