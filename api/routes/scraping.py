"""
FastAPI router for triggering scraping jobs.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scrape", tags=["scraping"])

# In-memory job status store (replace with Redis/DB for production)
_job_status: Dict[str, Dict[str, Any]] = {}


# ------------------------------------------------------------------ #
# Pydantic schemas
# ------------------------------------------------------------------ #

class ScrapeRequest(BaseModel):
    """Common request body for scraping endpoints."""

    keyword: str
    max_pages: int = 3


class RedditScrapeRequest(BaseModel):
    """Request body for Reddit scraping."""

    subreddits: Optional[list] = None
    limit: int = 100


# ------------------------------------------------------------------ #
# Background task helpers
# ------------------------------------------------------------------ #

def _run_amazon_scrape(job_id: str, keyword: str, max_pages: int) -> None:
    """Background task: scrape Amazon and persist results."""
    from database.db import db_session
    from database.models import Product
    from scrapers.amazon_scraper import AmazonScraper

    _job_status[job_id]["status"] = "running"
    try:
        scraper = AmazonScraper()
        products = scraper.scrape_products(keyword, max_pages=max_pages)

        with db_session() as db:
            for p in products:
                product = Product(
                    name=p["name"],
                    price=p.get("price"),
                    rating=p.get("rating"),
                    reviews_count=p.get("reviews_count", 0),
                    category=p.get("category"),
                    availability=p.get("availability", "unknown"),
                    source="amazon",
                    url=p.get("url"),
                )
                db.add(product)

        _job_status[job_id].update(
            {
                "status": "completed",
                "products_found": len(products),
                "completed_at": datetime.utcnow().isoformat(),
            }
        )
        logger.info("Amazon scrape job %s completed: %d products", job_id, len(products))
    except Exception as exc:
        logger.error("Amazon scrape job %s failed: %s", job_id, exc)
        _job_status[job_id].update({"status": "failed", "error": str(exc)})


def _run_flipkart_scrape(job_id: str, keyword: str, max_pages: int) -> None:
    """Background task: scrape Flipkart and persist results."""
    from database.db import db_session
    from database.models import Product
    from scrapers.flipkart_scraper import FlipkartScraper

    _job_status[job_id]["status"] = "running"
    try:
        scraper = FlipkartScraper()
        products = scraper.scrape_products(keyword, max_pages=max_pages)

        with db_session() as db:
            for p in products:
                product = Product(
                    name=p["name"],
                    price=p.get("price"),
                    rating=p.get("rating"),
                    reviews_count=p.get("reviews_count", 0),
                    category=p.get("category"),
                    availability=p.get("availability", "unknown"),
                    source="flipkart",
                    url=p.get("url"),
                )
                db.add(product)

        _job_status[job_id].update(
            {
                "status": "completed",
                "products_found": len(products),
                "completed_at": datetime.utcnow().isoformat(),
            }
        )
        logger.info("Flipkart scrape job %s completed: %d products", job_id, len(products))
    except Exception as exc:
        logger.error("Flipkart scrape job %s failed: %s", job_id, exc)
        _job_status[job_id].update({"status": "failed", "error": str(exc)})


def _run_reddit_scrape(job_id: str, subreddits: Optional[list], limit: int) -> None:
    """Background task: collect Reddit trends and persist results."""
    from database.db import db_session
    from database.models import TrendData
    from scrapers.reddit_scraper import RedditScraper

    _job_status[job_id]["status"] = "running"
    try:
        scraper = RedditScraper()
        trends = scraper.get_trending_keywords(subreddits=subreddits, limit=limit)

        with db_session() as db:
            for t in trends:
                trend = TrendData(
                    keyword=t["keyword"],
                    platform=t["platform"],
                    score=t["score"],
                    date=t["date"],
                    category=t.get("category"),
                )
                db.add(trend)

        _job_status[job_id].update(
            {
                "status": "completed",
                "keywords_found": len(trends),
                "completed_at": datetime.utcnow().isoformat(),
            }
        )
        logger.info("Reddit scrape job %s completed: %d keywords", job_id, len(trends))
    except Exception as exc:
        logger.error("Reddit scrape job %s failed: %s", job_id, exc)
        _job_status[job_id].update({"status": "failed", "error": str(exc)})


# ------------------------------------------------------------------ #
# Endpoints
# ------------------------------------------------------------------ #

@router.post("/amazon", response_model=Dict[str, Any], status_code=202)
def trigger_amazon_scrape(
    payload: ScrapeRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger an asynchronous Amazon scraping job for the given keyword.
    Returns a job ID that can be polled via GET /scrape/status/{job_id}.
    """
    import uuid

    job_id = str(uuid.uuid4())
    _job_status[job_id] = {
        "job_id": job_id,
        "source": "amazon",
        "keyword": payload.keyword,
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
    }
    background_tasks.add_task(
        _run_amazon_scrape, job_id, payload.keyword, payload.max_pages
    )
    return _job_status[job_id]


@router.post("/flipkart", response_model=Dict[str, Any], status_code=202)
def trigger_flipkart_scrape(
    payload: ScrapeRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger an asynchronous Flipkart scraping job for the given keyword.
    """
    import uuid

    job_id = str(uuid.uuid4())
    _job_status[job_id] = {
        "job_id": job_id,
        "source": "flipkart",
        "keyword": payload.keyword,
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
    }
    background_tasks.add_task(
        _run_flipkart_scrape, job_id, payload.keyword, payload.max_pages
    )
    return _job_status[job_id]


@router.post("/reddit", response_model=Dict[str, Any], status_code=202)
def trigger_reddit_scrape(
    payload: RedditScrapeRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger an asynchronous Reddit trend-collection job.
    """
    import uuid

    job_id = str(uuid.uuid4())
    _job_status[job_id] = {
        "job_id": job_id,
        "source": "reddit",
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
    }
    background_tasks.add_task(
        _run_reddit_scrape, job_id, payload.subreddits, payload.limit
    )
    return _job_status[job_id]


@router.get("/status", response_model=Dict[str, Any])
def get_all_job_statuses():
    """Return the status of all scraping jobs."""
    return {"jobs": list(_job_status.values())}


@router.get("/status/{job_id}", response_model=Dict[str, Any])
def get_job_status(job_id: str):
    """Return the status of a specific scraping job."""
    if job_id not in _job_status:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_status[job_id]
