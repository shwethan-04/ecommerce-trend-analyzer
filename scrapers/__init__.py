"""Scrapers package for the E-Commerce Trend Analyzer."""

from .amazon_scraper import AmazonScraper
from .flipkart_scraper import FlipkartScraper
from .reddit_scraper import RedditScraper

__all__ = ["AmazonScraper", "FlipkartScraper", "RedditScraper"]
