"""
Reddit scraper using Reddit's public JSON API (no credentials required).

Reddit serves JSON at https://www.reddit.com/r/<sub>/hot.json — no OAuth,
no API key, just a descriptive User-Agent header as required by Reddit's
API rules.

Also includes Google Trends data collection via pytrends.
"""

import logging
import time
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import settings
from utils.helpers import chunk_list, rotate_user_agent, safe_request

logger = logging.getLogger(__name__)

# Reddit's public JSON endpoint — no auth needed
_REDDIT_BASE   = "https://www.reddit.com"
_REDDIT_SEARCH = "https://www.reddit.com/search.json"

# Reddit requires a unique, descriptive User-Agent or it returns 429/403
_REDDIT_UA = "Mozilla/5.0 (compatible; EcommerceTrendAnalyzer/1.0; +https://github.com/trend-analyzer)"

# Slightly longer delay for Reddit to avoid 429s
_REDDIT_DELAY = max(settings.SCRAPE_DELAY, 2.0)


class RedditScraper:
    """
    Collects trending keywords and product mentions from Reddit using the
    public JSON API (no API key or OAuth required), and fetches Google
    Trends data via pytrends.
    """

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get_trending_keywords(
        self,
        subreddits: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Fetch hot posts from e-commerce subreddits via the public JSON API
        and extract trending product keywords.

        Args:
            subreddits: Subreddit names without the r/ prefix.
                        Defaults to settings.ECOMMERCE_SUBREDDITS.
            limit: Max posts to fetch per subreddit (Reddit caps at 100).

        Returns:
            List of dicts: {keyword, score, platform, date, category}.
        """
        if subreddits is None:
            subreddits = settings.ECOMMERCE_SUBREDDITS

        word_scores: Counter = Counter()

        for sub_name in subreddits:
            posts = self._fetch_subreddit_posts(sub_name, limit=min(limit, 100))
            for post in posts:
                text  = post.get("title", "") + " " + post.get("selftext", "")
                score = post.get("score", 1)
                for word in self._extract_keywords(text):
                    word_scores[word] += score
            logger.info("r/%s: processed %d posts.", sub_name, len(posts))
            time.sleep(_REDDIT_DELAY)

        now = datetime.utcnow()
        results = [
            {
                "keyword":  keyword,
                "score":    float(score),
                "platform": "reddit",
                "date":     now,
                "category": None,
            }
            for keyword, score in word_scores.most_common(50)
        ]

        logger.info("Extracted %d trending keywords from Reddit.", len(results))
        return results

    def analyze_product_mentions(self, keyword: str) -> List[Dict[str, Any]]:
        """
        Search Reddit for posts mentioning *keyword* using the public
        search JSON endpoint.

        Args:
            keyword: Product or brand name to search for.

        Returns:
            List of dicts: {title, score, url, subreddit, created_utc, text}.
        """
        headers  = self._build_headers()
        params   = {"q": keyword, "sort": "relevance", "limit": 50, "type": "link"}
        response = safe_request(
            _REDDIT_SEARCH,
            headers=headers,
            delay=_REDDIT_DELAY,
            params=params,
            max_retries=settings.MAX_RETRIES,
        )

        if response is None:
            logger.warning("No response from Reddit search for %r.", keyword)
            return []

        mentions: List[Dict[str, Any]] = []
        try:
            data  = response.json()
            posts = data.get("data", {}).get("children", [])
            for child in posts:
                p = child.get("data", {})
                mentions.append({
                    "title":       p.get("title", ""),
                    "score":       p.get("score", 0),
                    "url":         p.get("url", ""),
                    "subreddit":   p.get("subreddit", ""),
                    "created_utc": datetime.utcfromtimestamp(p.get("created_utc", 0)),
                    "text":        (p.get("selftext") or "")[:500],
                })
        except Exception as exc:
            logger.error("Error parsing Reddit search results: %s", exc)

        logger.info("Found %d Reddit mentions for %r.", len(mentions), keyword)
        return mentions

    def get_google_trends(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch Google Trends interest-over-time data for *keywords* via pytrends.

        Args:
            keywords: Search terms (pytrends supports up to 5 per request).

        Returns:
            List of dicts: {keyword, score, platform, date, category}.
        """
        try:
            from pytrends.request import TrendReq
        except ImportError:
            logger.error("pytrends is not installed. Run: pip install pytrends")
            return []

        results: List[Dict[str, Any]] = []

        for batch in chunk_list(keywords, 5):
            try:
                pytrends = TrendReq(hl="en-US", tz=360)
                pytrends.build_payload(batch, cat=0, timeframe="today 3-m", geo="")
                interest_df = pytrends.interest_over_time()

                if interest_df.empty:
                    logger.info("Google Trends returned no data for batch: %s", batch)
                    continue

                for kw in batch:
                    if kw not in interest_df.columns:
                        continue
                    for date_idx, score in interest_df[kw].items():
                        results.append({
                            "keyword":  kw,
                            "score":    float(score),
                            "platform": "google_trends",
                            "date":     date_idx.to_pydatetime()
                                        if hasattr(date_idx, "to_pydatetime")
                                        else datetime.utcnow(),
                            "category": None,
                        })

                time.sleep(1.0)  # be polite to Google Trends

            except Exception as exc:
                logger.error("Google Trends error for batch %s: %s", batch, exc)

        logger.info("Fetched %d Google Trends data points.", len(results))
        return results

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _fetch_subreddit_posts(
        self, subreddit: str, limit: int = 100, sort: str = "hot"
    ) -> List[Dict[str, Any]]:
        """
        Fetch posts from a subreddit using the public .json endpoint.

        Args:
            subreddit: Subreddit name (no r/ prefix).
            limit: Number of posts (max 100 per Reddit's API).
            sort: "hot" | "new" | "top" | "rising"

        Returns:
            List of post data dicts.
        """
        url     = f"{_REDDIT_BASE}/r/{subreddit}/{sort}.json"
        headers = self._build_headers()
        params  = {"limit": limit, "raw_json": 1}

        response = safe_request(
            url,
            headers=headers,
            delay=_REDDIT_DELAY,
            params=params,
            max_retries=settings.MAX_RETRIES,
        )

        if response is None:
            logger.warning("Could not fetch r/%s.", subreddit)
            return []

        try:
            data  = response.json()
            posts = data.get("data", {}).get("children", [])
            return [child.get("data", {}) for child in posts]
        except Exception as exc:
            logger.error("Error parsing r/%s JSON: %s", subreddit, exc)
            return []

    @staticmethod
    def _build_headers() -> Dict[str, str]:
        """
        Build request headers for Reddit's public API.
        Reddit requires a descriptive User-Agent — generic browser UAs
        often get rate-limited.
        """
        return {
            "User-Agent": _REDDIT_UA,
            "Accept":     "application/json",
        }

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """
        Extract meaningful product-related keywords from text.
        Filters stop-words and short tokens.
        """
        import re

        STOP_WORDS = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "is", "it", "this", "that",
            "was", "are", "be", "been", "have", "has", "had", "do", "does",
            "did", "will", "would", "could", "should", "may", "might", "i",
            "my", "me", "we", "our", "you", "your", "he", "she", "they",
            "their", "what", "which", "who", "how", "when", "where", "why",
            "not", "no", "so", "if", "as", "up", "out", "about", "just",
            "get", "got", "can", "its", "any", "all", "more", "also",
            "like", "one", "new", "use", "used", "using", "need", "want",
            "good", "best", "great", "really", "very", "much", "still",
            "even", "only", "than", "then", "now", "here", "there", "too",
        }

        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
        return [w for w in words if w not in STOP_WORDS]
