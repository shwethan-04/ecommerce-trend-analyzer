"""
FastAPI router for product-related endpoints.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import Product, Review

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/products", tags=["products"])


# ------------------------------------------------------------------ #
# Pydantic schemas
# ------------------------------------------------------------------ #

class ProductCreate(BaseModel):
    """Schema for creating a product via the API (testing / seeding)."""

    name: str
    price: Optional[float] = None
    rating: Optional[float] = None
    reviews_count: int = 0
    category: Optional[str] = None
    availability: str = "unknown"
    source: str
    url: Optional[str] = None


class ProductOut(BaseModel):
    """Schema for serialising a product."""

    id: int
    name: str
    price: Optional[float]
    rating: Optional[float]
    reviews_count: int
    category: Optional[str]
    availability: str
    source: str
    url: Optional[str]

    class Config:
        from_attributes = True


# ------------------------------------------------------------------ #
# Endpoints
# ------------------------------------------------------------------ #

@router.get("", response_model=Dict[str, Any])
def list_products(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    category: Optional[str] = Query(None, description="Filter by category"),
    source: Optional[str] = Query(None, description="Filter by source (amazon/flipkart)"),
    db: Session = Depends(get_db),
):
    """
    List products with optional pagination and filtering.

    Returns paginated product list with total count and page metadata.
    """
    query = db.query(Product)

    if category:
        query = query.filter(Product.category.ilike(f"%{category}%"))
    if source:
        query = query.filter(Product.source == source.lower())

    total = query.count()
    products = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "items": [ProductOut.model_validate(p) for p in products],
    }


@router.get("/trending", response_model=List[Dict[str, Any]])
def get_trending_products(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return the top trending products ranked by composite trend score."""
    from analytics.trends import TrendAnalyzer

    analyzer = TrendAnalyzer()
    trending = analyzer.identify_trending_products(db, limit=limit)
    return trending


@router.get("/{product_id}", response_model=Dict[str, Any])
def get_product(product_id: int, db: Session = Depends(get_db)):
    """
    Return a single product with its reviews and latest prediction.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    reviews = (
        db.query(Review)
        .filter(Review.product_id == product_id)
        .limit(50)
        .all()
    )

    from database.models import Prediction

    prediction = (
        db.query(Prediction)
        .filter(Prediction.product_id == product_id)
        .order_by(Prediction.prediction_date.desc())
        .first()
    )

    return {
        "id": product.id,
        "name": product.name,
        "price": product.price,
        "rating": product.rating,
        "reviews_count": product.reviews_count,
        "category": product.category,
        "availability": product.availability,
        "source": product.source,
        "url": product.url,
        "scraped_at": product.scraped_at.isoformat() if product.scraped_at else None,
        "reviews": [
            {
                "id": r.id,
                "text": r.text,
                "sentiment": r.sentiment,
                "sentiment_score": r.sentiment_score,
            }
            for r in reviews
        ],
        "prediction": {
            "predicted_score": prediction.predicted_score,
            "confidence": prediction.confidence,
            "target_month": prediction.target_month,
        }
        if prediction
        else None,
    }


@router.post("", response_model=ProductOut, status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    """
    Create a product record directly (useful for testing / data seeding).
    """
    product = Product(**payload.model_dump())
    db.add(product)
    try:
        db.commit()
        db.refresh(product)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to create product: %s", exc)
        raise HTTPException(status_code=500, detail="Could not create product")

    return product
