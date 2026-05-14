"""
"Flipkart" product data collector using free public APIs.

Uses two no-auth sources:
  1. DummyJSON  (https://dummyjson.com/products) — 100 realistic products
     across electronics, beauty, furniture, groceries, etc.
  2. Open Library Search (https://openlibrary.org/search.json) — books
     as a "Books & Media" category with real ratings.

Products are labelled source='flipkart' so the pipeline treats them
as a separate data source for comparison charts.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from config import settings
from utils.helpers import safe_request

logger = logging.getLogger(__name__)

_DUMMYJSON_URL  = "https://dummyjson.com/products"
_OPENLIBRARY_URL = "https://openlibrary.org/search.json"


class FlipkartScraper:
    """
    Collects product data from free public APIs and labels them as
    'flipkart' source so the rest of the pipeline works unchanged.
    """

    def __init__(
        self,
        delay: float = settings.SCRAPE_DELAY,
        max_retries: int = settings.MAX_RETRIES,
    ) -> None:
        self.delay       = delay
        self.max_retries = max_retries
        logger.info("FlipkartScraper (API mode) initialised.")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def scrape_products(
        self, keyword: str, max_pages: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Fetch products from DummyJSON and Open Library.

        Args:
            keyword:   Search term.
            max_pages: Pages to fetch from Open Library (20 items/page).

        Returns:
            List of product dicts compatible with the Product model.
        """
        products: List[Dict[str, Any]] = []

        # ── Source 1: DummyJSON ─────────────────────────────────────
        dummy = self._fetch_dummyjson(keyword)
        products.extend(dummy)
        logger.info("DummyJSON: %d products for keyword=%r", len(dummy), keyword)

        # ── Source 2: Open Library (books) ──────────────────────────
        for page in range(1, max_pages + 1):
            books = self._fetch_openlibrary(keyword, page=page)
            if not books:
                break
            products.extend(books)
            logger.info("OpenLibrary page %d: %d products", page, len(books))
            time.sleep(self.delay)

        logger.info("Total Flipkart-source products: %d", len(products))
        return products

    def scrape_product_reviews(
        self, product_url: str, max_reviews: int = 50
    ) -> List[Dict[str, Any]]:
        """No review endpoint available — returns empty list."""
        return []

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _fetch_dummyjson(self, keyword: str) -> List[Dict[str, Any]]:
        """
        Search DummyJSON products by keyword.
        Falls back to fetching all products if search returns nothing.
        """
        # Try search endpoint first
        search_url = f"{_DUMMYJSON_URL}/search"
        response = safe_request(
            search_url,
            headers={"Accept": "application/json"},
            delay=self.delay,
            params={"q": keyword, "limit": 50},
            max_retries=self.max_retries,
        )

        if response is None:
            return []

        try:
            data  = response.json()
            items = data.get("products", [])
        except Exception as exc:
            logger.error("DummyJSON parse error: %s", exc)
            return []

        # If search returned nothing, fetch all products
        if not items:
            response2 = safe_request(
                _DUMMYJSON_URL,
                headers={"Accept": "application/json"},
                delay=self.delay,
                params={"limit": 100},
                max_retries=self.max_retries,
            )
            if response2:
                try:
                    items = response2.json().get("products", [])
                except Exception:
                    pass

        products = []
        for item in items:
            products.append({
                "name":          item.get("title", "Unknown")[:255],
                "price":         float(item.get("price") or 0.0),
                "rating":        float(item.get("rating") or 0.0),
                "reviews_count": int(item.get("stock") or 0),  # use stock as proxy
                "category":      (item.get("category") or "general").replace("-", " ").title(),
                "availability":  "in_stock" if (item.get("stock") or 0) > 0 else "out_of_stock",
                "source":        "flipkart",
                "url":           item.get("thumbnail", ""),
            })
        return products

    def _fetch_openlibrary(
        self, keyword: str, page: int = 1
    ) -> List[Dict[str, Any]]:
        """Search Open Library for books matching keyword."""
        params = {
            "q":      keyword,
            "fields": "title,author_name,ratings_average,ratings_count,subject",
            "limit":  20,
            "page":   page,
        }
        response = safe_request(
            _OPENLIBRARY_URL,
            headers={"Accept": "application/json"},
            delay=self.delay,
            params=params,
            max_retries=self.max_retries,
        )
        if response is None:
            return []

        try:
            data  = response.json()
            items = data.get("docs", [])
        except Exception as exc:
            logger.error("OpenLibrary parse error: %s", exc)
            return []

        products = []
        for item in items:
            title = item.get("title", "").strip()
            if not title:
                continue
            rating        = float(item.get("ratings_average") or 3.5)
            reviews_count = int(item.get("ratings_count") or 0)
            subjects      = item.get("subject", [])
            category      = subjects[0].title() if subjects else "Books"

            products.append({
                "name":          title[:255],
                "price":         None,
                "rating":        round(min(rating, 5.0), 1),
                "reviews_count": reviews_count,
                "category":      category[:128],
                "availability":  "in_stock",
                "source":        "flipkart",
                "url":           "",
            })
        return products
