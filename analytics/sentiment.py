"""
Sentiment analysis using TextBlob.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """
    Performs sentiment analysis on product reviews using TextBlob.

    TextBlob's polarity score ranges from -1.0 (very negative) to +1.0
    (very positive).  Scores are mapped to three labels:
      - positive  : polarity >  0.1
      - negative  : polarity < -0.1
      - neutral   : -0.1 <= polarity <= 0.1
    """

    POSITIVE_THRESHOLD = 0.1
    NEGATIVE_THRESHOLD = -0.1

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def analyze_text(self, text: str) -> Dict[str, Any]:
        """
        Analyse the sentiment of a single text string.

        Args:
            text: The text to analyse.

        Returns:
            Dict with keys:
              - sentiment (str): "positive" | "negative" | "neutral"
              - score (float): polarity score in [-1.0, 1.0]
              - subjectivity (float): subjectivity score in [0.0, 1.0]
        """
        try:
            from textblob import TextBlob

            blob = TextBlob(text)
            score: float = blob.sentiment.polarity
            subjectivity: float = blob.sentiment.subjectivity
        except Exception as exc:
            logger.error("TextBlob analysis failed: %s", exc)
            score = 0.0
            subjectivity = 0.0

        return {
            "sentiment": self.classify_sentiment(score),
            "score": round(score, 4),
            "subjectivity": round(subjectivity, 4),
        }

    def analyze_reviews(
        self, reviews_list: List[str]
    ) -> Dict[str, Any]:
        """
        Batch-analyse a list of review texts.

        Args:
            reviews_list: List of review text strings.

        Returns:
            Dict with keys:
              - results (list): per-review analysis dicts
              - average_score (float): mean polarity
              - sentiment_counts (dict): counts per label
              - overall_sentiment (str): dominant sentiment label
        """
        if not reviews_list:
            return {
                "results": [],
                "average_score": 0.0,
                "sentiment_counts": {"positive": 0, "negative": 0, "neutral": 0},
                "overall_sentiment": "neutral",
            }

        results = [self.analyze_text(text) for text in reviews_list]
        scores = [r["score"] for r in results]
        average_score = sum(scores) / len(scores)

        counts: Dict[str, int] = {"positive": 0, "negative": 0, "neutral": 0}
        for r in results:
            counts[r["sentiment"]] += 1

        overall = max(counts, key=lambda k: counts[k])

        return {
            "results": results,
            "average_score": round(average_score, 4),
            "sentiment_counts": counts,
            "overall_sentiment": overall,
        }

    def get_product_sentiment_summary(
        self, product_id: int, db: Session
    ) -> Dict[str, Any]:
        """
        Query the database for all reviews of *product_id* and return
        aggregated sentiment statistics.

        Args:
            product_id: Primary key of the product.
            db: Active SQLAlchemy session.

        Returns:
            Dict with keys:
              - product_id (int)
              - total_reviews (int)
              - average_score (float)
              - sentiment_counts (dict)
              - overall_sentiment (str)
        """
        from database.models import Review

        reviews = (
            db.query(Review).filter(Review.product_id == product_id).all()
        )

        if not reviews:
            return {
                "product_id": product_id,
                "total_reviews": 0,
                "average_score": 0.0,
                "sentiment_counts": {"positive": 0, "negative": 0, "neutral": 0},
                "overall_sentiment": "neutral",
            }

        scores = [r.sentiment_score for r in reviews]
        average_score = sum(scores) / len(scores)

        counts: Dict[str, int] = {"positive": 0, "negative": 0, "neutral": 0}
        for r in reviews:
            label = r.sentiment if r.sentiment in counts else "neutral"
            counts[label] += 1

        overall = max(counts, key=lambda k: counts[k])

        return {
            "product_id": product_id,
            "total_reviews": len(reviews),
            "average_score": round(average_score, 4),
            "sentiment_counts": counts,
            "overall_sentiment": overall,
        }

    def classify_sentiment(self, score: float) -> str:
        """
        Map a polarity score to a sentiment label.

        Args:
            score: Polarity value in [-1.0, 1.0].

        Returns:
            "positive", "negative", or "neutral".
        """
        if score > self.POSITIVE_THRESHOLD:
            return "positive"
        if score < self.NEGATIVE_THRESHOLD:
            return "negative"
        return "neutral"

    def analyze_and_store_reviews(
        self,
        product_id: int,
        review_texts: List[str],
        db: Session,
    ) -> int:
        """
        Analyse a list of review texts and persist them to the database.

        Args:
            product_id: FK to the parent product.
            review_texts: Raw review strings.
            db: Active SQLAlchemy session.

        Returns:
            Number of reviews stored.
        """
        from database.models import Review

        stored = 0
        for text in review_texts:
            if not text.strip():
                continue
            analysis = self.analyze_text(text)
            review = Review(
                product_id=product_id,
                text=text[:2000],  # cap length
                sentiment=analysis["sentiment"],
                sentiment_score=analysis["score"],
            )
            db.add(review)
            stored += 1

        try:
            db.commit()
            logger.info("Stored %d reviews for product_id=%d", stored, product_id)
        except Exception as exc:
            db.rollback()
            logger.error("Failed to store reviews: %s", exc)
            stored = 0

        return stored
