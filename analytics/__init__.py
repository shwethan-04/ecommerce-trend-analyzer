"""Analytics package for the E-Commerce Trend Analyzer."""

from .predictor import TrendPredictor
from .sentiment import SentimentAnalyzer
from .trends import TrendAnalyzer

__all__ = ["SentimentAnalyzer", "TrendAnalyzer", "TrendPredictor"]
