"""
FastAPI router for sentiment analysis endpoints.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sentiment", tags=["sentiment"])


# ------------------------------------------------------------------ #
# Pydantic schemas
# ------------------------------------------------------------------ #

class TextAnalysisRequest(BaseModel):
    """Request body for on-the-fly text sentiment analysis."""

    text: str


class BatchAnalysisRequest(BaseModel):
    """Request body for batch text sentiment analysis."""

    texts: List[str]


# ------------------------------------------------------------------ #
# Endpoints
# ------------------------------------------------------------------ #

@router.get("/product/{product_id}", response_model=Dict[str, Any])
def get_product_sentiment(product_id: int, db: Session = Depends(get_db)):
    """
    Return aggregated sentiment statistics for all reviews of a product.
    """
    from analytics.sentiment import SentimentAnalyzer
    from database.models import Product

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    analyzer = SentimentAnalyzer()
    return analyzer.get_product_sentiment_summary(product_id, db)


@router.post("/analyze", response_model=Dict[str, Any])
def analyze_text(payload: TextAnalysisRequest):
    """
    Analyse the sentiment of a single text string on the fly.
    """
    from analytics.sentiment import SentimentAnalyzer

    analyzer = SentimentAnalyzer()
    return analyzer.analyze_text(payload.text)


@router.post("/analyze/batch", response_model=Dict[str, Any])
def analyze_batch(payload: BatchAnalysisRequest):
    """
    Analyse the sentiment of multiple texts in a single request.
    """
    from analytics.sentiment import SentimentAnalyzer

    if not payload.texts:
        raise HTTPException(status_code=400, detail="texts list cannot be empty")

    analyzer = SentimentAnalyzer()
    return analyzer.analyze_reviews(payload.texts)


@router.get("/overview", response_model=Dict[str, Any])
def get_sentiment_overview(db: Session = Depends(get_db)):
    """
    Return overall sentiment distribution across all reviews in the database.
    """
    from database.models import Review
    from sqlalchemy import func

    rows = (
        db.query(Review.sentiment, func.count(Review.id).label("count"))
        .group_by(Review.sentiment)
        .all()
    )

    total = sum(r.count for r in rows)
    distribution = {r.sentiment: r.count for r in rows}

    # Ensure all three labels are present
    for label in ("positive", "negative", "neutral"):
        distribution.setdefault(label, 0)

    percentages = {
        label: round(count / total * 100, 2) if total > 0 else 0.0
        for label, count in distribution.items()
    }

    avg_score = (
        db.query(func.avg(Review.sentiment_score)).scalar() or 0.0
    )

    return {
        "total_reviews": total,
        "distribution": distribution,
        "percentages": percentages,
        "average_score": round(float(avg_score), 4),
    }
