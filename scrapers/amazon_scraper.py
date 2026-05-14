"""
"Amazon" product data collector using free public APIs.

Since Amazon actively blocks scrapers, this module uses two free,
no-auth-required data sources that provide real product data:

  1. FakeStoreAPI  (https://fakestoreapi.com)  — electronics, jewellery,
     clothing with prices, ratings and review counts.
  2. Open Food Facts (https://world.openfoodfacts.org) — food/grocery
     products with real ratings and categories.

Both return structured JSON — no HTML parsing, no bot detection.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from config import settings
from utils.helpers import safe_request

logger = logging.getLogger(__name__)

_FAKESTORE_URL   = "https://fakestoreapi.com/products"
_OPENFOOD_URL    = "https://world.openfoodfacts.org/cgi/search.pl"


class AmazonScraper:
    """
    Collects product data from free public APIs and labels them as
    'amazon' source so the rest of the pipeline works unchanged.
    """

    def __init__(
        self,
        delay: float = settings.SCRAPE_DELAY,
        max_retries: int = settings.MAX_RETRIES,
    ) -> None:
        self.delay       = delay
        self.max_retries = max_retries
        logger.info("AmazonScraper (API mode) initialised.")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def scrape_products(
        self, keyword: str, max_pages: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Fetch products matching *keyword* from FakeStoreAPI and
        Open Food Facts.

        Args:
            keyword:   Search term (used to filter Open Food Facts results).
            max_pages: Ignored for FakeStoreAPI (returns all ~20 products);
                       used as page count for Open Food Facts.

        Returns:
            List of product dicts compatible with the Product model.
        """
        products: List[Dict[str, Any]] = []

        # ── Source 1: FakeStoreAPI ──────────────────────────────────
        fakestore = self._fetch_fakestore(keyword)
        products.extend(fakestore)
        logger.info("FakeStoreAPI: %d products for keyword=%r", len(fakestore), keyword)

        # ── Source 2: Open Food Facts ───────────────────────────────
        for page in range(1, max_pages + 1):
            food = self._fetch_openfoodfacts(keyword, page=page)
            if not food:
                break
            products.extend(food)
            logger.info("OpenFoodFacts page %d: %d products", page, len(food))
            time.sleep(self.delay)

        logger.info("Total products collected: %d", len(products))
        return products

    def scrape_product_reviews(
        self, product_url: str, max_reviews: int = 50
    ) -> List[Dict[str, Any]]:
        """
        FakeStoreAPI doesn't have review endpoints.
        Returns an empty list — reviews are generated from ratings
        by the sentiment pipeline instead.
        """
        return []

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _fetch_fakestore(self, keyword: str) -> List[Dict[str, Any]]:
        """Fetch all products from FakeStoreAPI and filter by keyword."""
        response = safe_request(
            _FAKESTORE_URL,
            headers={"Accept": "application/json"},
            delay=self.delay,
            max_retries=self.max_retries,
        )
        if response is None:
            return []

        try:
            items = response.json()
        except Exception as exc:
            logger.error("FakeStoreAPI JSON parse error: %s", exc)
            return []

        kw_lower = keyword.lower()
        products = []
        for item in items:
            title    = item.get("title", "")
            category = item.get("category", "")
            # Include if keyword matches title or category, or include all if generic keyword
            if (kw_lower in title.lower()
                    or kw_lower in category.lower()
                    or kw_lower in ("laptop", "phone", "product", "item", "all")):
                rating_obj = item.get("rating", {})
                products.append({
                    "name":          title,
                    "price":         float(item.get("price") or 0.0),
                    "rating":        float(rating_obj.get("rate") or 0.0),
                    "reviews_count": int(rating_obj.get("count") or 0),
                    "category":      category,
                    "availability":  "in_stock",
                    "source":        "amazon",
                    "url":           f"https://fakestoreapi.com/products/{item.get('id','')}",
                })
        return products

    def _fetch_openfoodfacts(
        self, keyword: str, page: int = 1
    ) -> List[Dict[str, Any]]:
        """Search Open Food Facts for products matching keyword."""
        params = {
            "search_terms":   keyword,
            "search_simple":  1,
            "action":         "process",
            "json":           1,
            "page":           page,
            "page_size":      20,
            "fields":         "product_name,categories_tags,nutriscore_score,ecoscore_score,popularity_key",
        }
        response = safe_request(
            _OPENFOOD_URL,
            headers={"Accept": "application/json", "User-Agent": "EcommerceTrendAnalyzer/1.0"},
            delay=self.delay,
            params=params,
            max_retries=self.max_retries,
        )
        if response is None:
            return []

        try:
            data  = response.json()
            items = data.get("products", [])
        except Exception as exc:
            logger.error("OpenFoodFacts JSON parse error: %s", exc)
            return []

        products = []
        for item in items:
            name = item.get("product_name", "").strip()
            if not name:
                continue

            # Derive a pseudo-rating from nutriscore (A=5 … E=1)
            nutri = item.get("nutriscore_score")
            if nutri is not None:
                # nutriscore_score: lower is better (-15 to +40)
                # Map to 1–5 stars
                rating = max(1.0, min(5.0, 5.0 - (float(nutri) + 15) / 14.0))
            else:
                rating = 3.5

            # Popularity key as proxy for review count
            pop = item.get("popularity_key") or 0
            reviews_count = min(int(abs(pop) // 1000), 50000)

            cats = item.get("categories_tags", [])
            category = cats[0].replace("en:", "").replace("-", " ").title() if cats else "Food"

            products.append({
                "name":          name[:255],
                "price":         None,
                "rating":        round(rating, 1),
                "reviews_count": reviews_count,
                "category":      category,
                "availability":  "in_stock",
                "source":        "amazon",
                "url":           "",
            })
        return products
