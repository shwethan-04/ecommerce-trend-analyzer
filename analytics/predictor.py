"""
ML-based trend predictor using scikit-learn.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class TrendPredictor:
    """
    Trains a RandomForestRegressor to predict a product's trend score
    for the next month, based on features derived from product metadata
    and sentiment analysis.

    The trained model is persisted to disk with joblib so it can be
    reloaded without retraining on every startup.
    """

    def __init__(self, model_path: Optional[str] = None) -> None:
        from config import settings

        self.model_path = model_path or settings.MODEL_PATH
        self.model = None
        self.feature_columns: List[str] = []
        self._category_encoder: Dict[str, int] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def prepare_features(
        self, product_data: Dict[str, Any]
    ) -> Optional[np.ndarray]:
        """
        Engineer a feature vector from raw product data.

        Features:
          1. rating (normalised 0–1)
          2. log(reviews_count + 1) normalised
          3. sentiment_score (already -1 to 1)
          4. price_normalised (0–1, capped at 99th percentile)
          5. category_encoded (integer label)

        Args:
            product_data: Dict with keys rating, reviews_count,
                          sentiment_score, price, category.

        Returns:
            1-D numpy array of features, or None on error.
        """
        try:
            import math

            rating = float(product_data.get("rating") or 0.0) / 5.0
            reviews = math.log1p(int(product_data.get("reviews_count") or 0)) / math.log1p(100_000)
            sentiment = float(product_data.get("sentiment_score") or 0.0)
            price_raw = float(product_data.get("price") or 0.0)
            # Normalise price to [0, 1] using a soft cap of $10,000
            price_norm = min(price_raw / 10_000.0, 1.0)
            category = str(product_data.get("category") or "unknown").lower()
            cat_enc = float(
                self._category_encoder.get(
                    category, len(self._category_encoder)
                )
            )

            return np.array(
                [rating, reviews, sentiment, price_norm, cat_enc],
                dtype=np.float64,
            )
        except Exception as exc:
            logger.error("Feature preparation failed: %s", exc)
            return None

    def train(self, db) -> bool:
        """
        Load all products + their sentiment from the database, compute
        trend scores as labels, and train a RandomForestRegressor.

        Args:
            db: Active SQLAlchemy session.

        Returns:
            True if training succeeded, False otherwise.
        """
        from analytics.trends import TrendAnalyzer
        from database.models import Product, Review
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.model_selection import train_test_split
        from sqlalchemy import func

        logger.info("Starting model training…")

        products = db.query(Product).all()
        if len(products) < 5:
            logger.warning(
                "Not enough data to train (%d products). Need at least 5.",
                len(products),
            )
            return False

        # Build category encoder from current data
        categories = list({p.category or "unknown" for p in products})
        self._category_encoder = {cat.lower(): i for i, cat in enumerate(categories)}

        # Sentiment averages
        sentiment_map: Dict[int, float] = {}
        rows = (
            db.query(Review.product_id, func.avg(Review.sentiment_score))
            .group_by(Review.product_id)
            .all()
        )
        for pid, avg_s in rows:
            sentiment_map[pid] = float(avg_s or 0.0)

        # Category average prices
        cat_price_map: Dict[Optional[str], float] = {}
        cat_rows = (
            db.query(Product.category, func.avg(Product.price))
            .filter(Product.price.isnot(None))
            .group_by(Product.category)
            .all()
        )
        for cat, avg_p in cat_rows:
            cat_price_map[cat] = float(avg_p or 0.0)

        analyzer = TrendAnalyzer()
        X_list, y_list = [], []

        for p in products:
            product_dict = {
                "rating": p.rating,
                "reviews_count": p.reviews_count,
                "price": p.price,
                "category": p.category,
                "avg_category_price": cat_price_map.get(p.category, p.price or 0.0),
                "sentiment_score": sentiment_map.get(p.id, 0.0),
            }
            features = self.prepare_features(product_dict)
            if features is None:
                continue
            label = analyzer.calculate_trend_score(product_dict)
            X_list.append(features)
            y_list.append(label)

        if len(X_list) < 5:
            logger.warning("Insufficient valid feature vectors (%d).", len(X_list))
            return False

        X = np.array(X_list)
        y = np.array(y_list)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        self.model = RandomForestRegressor(
            n_estimators=100, random_state=42, n_jobs=-1
        )
        self.model.fit(X_train, y_train)

        score = self.model.score(X_test, y_test)
        logger.info("Model trained. R² on test set: %.4f", score)

        self._save_model()
        return True

    def predict(self, product_id: int, db) -> Optional[Dict[str, Any]]:
        """
        Predict the trend score for a single product.

        Args:
            product_id: Primary key of the product.
            db: Active SQLAlchemy session.

        Returns:
            Dict with predicted_score, confidence, target_month, or None.
        """
        if self.model is None:
            logger.warning("Model not loaded. Call load_or_train() first.")
            return None

        from database.models import Product, Review
        from sqlalchemy import func

        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            logger.warning("Product %d not found.", product_id)
            return None

        avg_sentiment = (
            db.query(func.avg(Review.sentiment_score))
            .filter(Review.product_id == product_id)
            .scalar()
        ) or 0.0

        product_dict = {
            "rating": product.rating,
            "reviews_count": product.reviews_count,
            "price": product.price,
            "category": product.category,
            "sentiment_score": float(avg_sentiment),
        }

        features = self.prepare_features(product_dict)
        if features is None:
            return None

        predicted = float(self.model.predict(features.reshape(1, -1))[0])
        predicted = max(0.0, min(100.0, predicted))

        # Confidence: use std of tree predictions as a proxy
        tree_preds = np.array(
            [tree.predict(features.reshape(1, -1))[0] for tree in self.model.estimators_]
        )
        std = float(np.std(tree_preds))
        confidence = max(0.0, min(1.0, 1.0 - std / 50.0))

        target_month = (
            datetime.utcnow().replace(day=1) + __import__("datetime").timedelta(days=32)
        ).strftime("%Y-%m")

        return {
            "product_id": product_id,
            "predicted_score": round(predicted, 2),
            "confidence": round(confidence, 4),
            "target_month": target_month,
        }

    def batch_predict(self, db) -> int:
        """
        Generate predictions for all products and store them in the
        Prediction table.

        Args:
            db: Active SQLAlchemy session.

        Returns:
            Number of predictions stored.
        """
        from database.models import Prediction, Product

        if self.model is None:
            logger.warning("Model not loaded. Call load_or_train() first.")
            return 0

        products = db.query(Product).all()
        stored = 0

        for product in products:
            result = self.predict(product.id, db)
            if result is None:
                continue

            prediction = Prediction(
                product_id=product.id,
                predicted_score=result["predicted_score"],
                confidence=result["confidence"],
                target_month=result["target_month"],
            )
            db.add(prediction)
            stored += 1

        try:
            db.commit()
            logger.info("Stored %d predictions.", stored)
        except Exception as exc:
            db.rollback()
            logger.error("Failed to store predictions: %s", exc)
            stored = 0

        return stored

    def load_or_train(self, db) -> bool:
        """
        Attempt to load a saved model from disk; train a new one if not found.

        Args:
            db: Active SQLAlchemy session.

        Returns:
            True if a model is ready, False otherwise.
        """
        if self._load_model():
            logger.info("Loaded existing model from %s", self.model_path)
            return True

        logger.info("No saved model found. Training a new one…")
        return self.train(db)

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _save_model(self) -> None:
        """Persist the trained model and encoder to disk."""
        import joblib

        os.makedirs(os.path.dirname(self.model_path) or ".", exist_ok=True)
        payload = {
            "model": self.model,
            "category_encoder": self._category_encoder,
        }
        joblib.dump(payload, self.model_path)
        logger.info("Model saved to %s", self.model_path)

    def _load_model(self) -> bool:
        """Load a previously saved model from disk."""
        if not os.path.exists(self.model_path):
            return False
        try:
            import joblib

            payload = joblib.load(self.model_path)
            self.model = payload["model"]
            self._category_encoder = payload.get("category_encoder", {})
            return True
        except Exception as exc:
            logger.error("Failed to load model: %s", exc)
            return False
