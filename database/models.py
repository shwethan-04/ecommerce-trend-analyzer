"""
SQLAlchemy ORM models for the E-Commerce Trend Analyzer.
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .db import Base


class Product(Base):
    """Represents a scraped product from Amazon or Flipkart."""

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(512), nullable=False, index=True)
    price = Column(Float, nullable=True)
    rating = Column(Float, nullable=True)
    reviews_count = Column(Integer, default=0)
    category = Column(String(128), nullable=True, index=True)
    availability = Column(String(64), default="unknown")
    source = Column(String(32), nullable=False)          # "amazon" | "flipkart"
    url = Column(String(1024), nullable=True)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="product", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Product id={self.id} name={self.name!r} source={self.source!r}>"


class Review(Base):
    """Stores individual product reviews with sentiment analysis results."""

    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    sentiment = Column(String(16), default="neutral")    # positive | negative | neutral
    sentiment_score = Column(Float, default=0.0)         # -1.0 to 1.0
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    product = relationship("Product", back_populates="reviews")

    def __repr__(self) -> str:
        return (
            f"<Review id={self.id} product_id={self.product_id} "
            f"sentiment={self.sentiment!r}>"
        )


class TrendData(Base):
    """Stores keyword trend scores from Reddit / Google Trends."""

    __tablename__ = "trend_data"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String(256), nullable=False, index=True)
    platform = Column(String(64), nullable=False)        # "reddit" | "google_trends"
    score = Column(Float, default=0.0)
    date = Column(DateTime, default=datetime.utcnow, index=True)
    category = Column(String(128), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<TrendData id={self.id} keyword={self.keyword!r} "
            f"platform={self.platform!r} score={self.score}>"
        )


class Prediction(Base):
    """ML-generated trend predictions for products."""

    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    predicted_score = Column(Float, nullable=False)
    confidence = Column(Float, default=0.0)              # 0.0 – 1.0
    prediction_date = Column(DateTime, default=datetime.utcnow)
    target_month = Column(String(7), nullable=True)      # e.g. "2024-07"

    # Relationships
    product = relationship("Product", back_populates="predictions")

    def __repr__(self) -> str:
        return (
            f"<Prediction id={self.id} product_id={self.product_id} "
            f"predicted_score={self.predicted_score:.2f}>"
        )


class AnalyticsReport(Base):
    """Stores generated analytics reports as JSON blobs."""

    __tablename__ = "analytics_reports"

    id = Column(Integer, primary_key=True, index=True)
    report_type = Column(String(64), nullable=False, index=True)
    data_json = Column(Text, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<AnalyticsReport id={self.id} report_type={self.report_type!r} "
            f"generated_at={self.generated_at}>"
        )
