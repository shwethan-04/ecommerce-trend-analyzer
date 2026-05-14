"""
Trend analysis and scoring for products and categories.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    """
    Computes trend scores, identifies trending products, and generates
    aggregated analytics for categories and time series.
    """

    # Weights for the composite trend score
    RATING_WEIGHT = 0.35
    REVIEWS_WEIGHT = 0.30
    PRICE_WEIGHT = 0.20
    SENTIMENT_WEIGHT = 0.15

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def calculate_trend_score(self, product_data: Dict[str, Any]) -> float:
        """
        Compute a composite trend score (0–100) for a single product.

        Inputs (all optional, defaults to neutral values if missing):
          - rating (float): 0–5
          - reviews_count (int): raw count
          - price (float): product price
          - avg_category_price (float): average price in the same category
          - sentiment_score (float): -1 to 1

        Returns:
            Trend score in [0.0, 100.0].
        """
        rating = float(product_data.get("rating") or 0.0)
        reviews_count = int(product_data.get("reviews_count") or 0)
        price = float(product_data.get("price") or 0.0)
        avg_price = float(product_data.get("avg_category_price") or price or 1.0)
        sentiment = float(product_data.get("sentiment_score") or 0.0)

        # Normalise each component to [0, 1]
        rating_norm = min(rating / 5.0, 1.0)

        # Log-scale reviews to avoid domination by outliers
        import math

        reviews_norm = min(math.log1p(reviews_count) / math.log1p(100_000), 1.0)

        # Price competitiveness: cheaper than average → higher score
        if avg_price > 0 and price > 0:
            price_ratio = avg_price / price  # >1 means cheaper than avg
            price_norm = min(price_ratio / 2.0, 1.0)
        else:
            price_norm = 0.5  # neutral

        # Sentiment: map [-1, 1] → [0, 1]
        sentiment_norm = (sentiment + 1.0) / 2.0

        score = (
            self.RATING_WEIGHT * rating_norm
            + self.REVIEWS_WEIGHT * reviews_norm
            + self.PRICE_WEIGHT * price_norm
            + self.SENTIMENT_WEIGHT * sentiment_norm
        ) * 100.0

        return round(score, 2)

    def identify_trending_products(
        self, db: Session, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Query all products from the database, compute their trend scores,
        and return the top *limit* ranked by score.

        Args:
            db: Active SQLAlchemy session.
            limit: Maximum number of products to return.

        Returns:
            List of product dicts enriched with a ``trend_score`` key.
        """
        from database.models import Product, Review
        from sqlalchemy import func

        products = db.query(Product).all()
        if not products:
            return []

        # Compute average sentiment per product
        sentiment_map: Dict[int, float] = {}
        rows = (
            db.query(Review.product_id, func.avg(Review.sentiment_score))
            .group_by(Review.product_id)
            .all()
        )
        for pid, avg_sent in rows:
            sentiment_map[pid] = float(avg_sent or 0.0)

        # Compute average price per category
        cat_price_map: Dict[Optional[str], float] = {}
        cat_rows = (
            db.query(Product.category, func.avg(Product.price))
            .filter(Product.price.isnot(None))
            .group_by(Product.category)
            .all()
        )
        for cat, avg_p in cat_rows:
            cat_price_map[cat] = float(avg_p or 0.0)

        scored: List[Dict[str, Any]] = []
        for p in products:
            data = {
                "id": p.id,
                "name": p.name,
                "price": p.price,
                "rating": p.rating,
                "reviews_count": p.reviews_count,
                "category": p.category,
                "source": p.source,
                "url": p.url,
                "availability": p.availability,
                "avg_category_price": cat_price_map.get(p.category, p.price or 0.0),
                "sentiment_score": sentiment_map.get(p.id, 0.0),
            }
            data["trend_score"] = self.calculate_trend_score(data)
            scored.append(data)

        scored.sort(key=lambda x: x["trend_score"], reverse=True)
        return scored[:limit]

    def compare_categories(self, db: Session) -> List[Dict[str, Any]]:
        """
        Aggregate product statistics per category.

        Returns:
            List of dicts per category:
            {category, product_count, avg_rating, avg_price, avg_trend_score}.
        """
        from database.models import Product
        from sqlalchemy import func

        rows = (
            db.query(
                Product.category,
                func.count(Product.id).label("product_count"),
                func.avg(Product.rating).label("avg_rating"),
                func.avg(Product.price).label("avg_price"),
            )
            .group_by(Product.category)
            .all()
        )

        result = []
        for row in rows:
            result.append(
                {
                    "category": row.category or "Unknown",
                    "product_count": row.product_count,
                    "avg_rating": round(float(row.avg_rating or 0.0), 2),
                    "avg_price": round(float(row.avg_price or 0.0), 2),
                }
            )

        return result

    def get_popularity_over_time(
        self, keyword: str, db: Session
    ) -> List[Dict[str, Any]]:
        """
        Return time-series trend data for *keyword* from the TrendData table.

        Args:
            keyword: The keyword to look up.
            db: Active SQLAlchemy session.

        Returns:
            List of {date, score, platform} dicts ordered by date.
        """
        from database.models import TrendData

        rows = (
            db.query(TrendData)
            .filter(TrendData.keyword.ilike(f"%{keyword}%"))
            .order_by(TrendData.date.asc())
            .all()
        )

        return [
            {
                "date": r.date.isoformat() if r.date else None,
                "score": r.score,
                "platform": r.platform,
                "keyword": r.keyword,
            }
            for r in rows
        ]

    def generate_heatmap_data(self, db: Session) -> Dict[str, Any]:
        """
        Build a sentiment heatmap matrix: rows = categories, columns = sources.

        Returns:
            Dict with keys:
              - categories (list[str])
              - sources (list[str])
              - matrix (list[list[float]]): avg sentiment score per cell
        """
        from database.models import Product, Review
        from sqlalchemy import func

        rows = (
            db.query(
                Product.category,
                Product.source,
                func.avg(Review.sentiment_score).label("avg_sentiment"),
            )
            .join(Review, Review.product_id == Product.id)
            .group_by(Product.category, Product.source)
            .all()
        )

        if not rows:
            return {"categories": [], "sources": [], "matrix": []}

        categories = sorted({r.category or "Unknown" for r in rows})
        sources = sorted({r.source for r in rows})

        # Build lookup
        lookup: Dict[tuple, float] = {}
        for r in rows:
            cat = r.category or "Unknown"
            lookup[(cat, r.source)] = round(float(r.avg_sentiment or 0.0), 4)

        matrix = [
            [lookup.get((cat, src), 0.0) for src in sources]
            for cat in categories
        ]

        return {"categories": categories, "sources": sources, "matrix": matrix}
