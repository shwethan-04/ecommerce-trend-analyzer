"""
FastAPI router for trend-related endpoints.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("", response_model=List[Dict[str, Any]])
def get_trends(
    keyword: Optional[str] = Query(None, description="Filter by keyword"),
    platform: Optional[str] = Query(None, description="Filter by platform"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    Return trend data records, optionally filtered by keyword and/or platform.
    """
    from database.models import TrendData

    query = db.query(TrendData)
    if keyword:
        query = query.filter(TrendData.keyword.ilike(f"%{keyword}%"))
    if platform:
        query = query.filter(TrendData.platform == platform.lower())

    rows = query.order_by(TrendData.date.desc()).limit(limit).all()

    return [
        {
            "id": r.id,
            "keyword": r.keyword,
            "platform": r.platform,
            "score": r.score,
            "date": r.date.isoformat() if r.date else None,
            "category": r.category,
        }
        for r in rows
    ]


@router.get("/categories", response_model=List[Dict[str, Any]])
def get_category_comparison(db: Session = Depends(get_db)):
    """
    Return aggregated statistics per product category.
    """
    from analytics.trends import TrendAnalyzer

    analyzer = TrendAnalyzer()
    return analyzer.compare_categories(db)


@router.get("/heatmap", response_model=Dict[str, Any])
def get_sentiment_heatmap(db: Session = Depends(get_db)):
    """
    Return sentiment heatmap data (categories × sources matrix).
    """
    from analytics.trends import TrendAnalyzer

    analyzer = TrendAnalyzer()
    return analyzer.generate_heatmap_data(db)


@router.get("/google", response_model=List[Dict[str, Any]])
def get_google_trends(
    keywords: str = Query(..., description="Comma-separated list of keywords"),
):
    """
    Fetch Google Trends interest-over-time data for the given keywords.

    Keywords should be comma-separated, e.g. ``?keywords=laptop,headphones``.
    """
    from scrapers.reddit_scraper import RedditScraper

    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not kw_list:
        return []

    scraper = RedditScraper()
    return scraper.get_google_trends(kw_list)


@router.get("/keyword/{keyword}", response_model=List[Dict[str, Any]])
def get_keyword_popularity(keyword: str, db: Session = Depends(get_db)):
    """
    Return time-series popularity data for a specific keyword.
    """
    from analytics.trends import TrendAnalyzer

    analyzer = TrendAnalyzer()
    return analyzer.get_popularity_over_time(keyword, db)
