"""
General-purpose utility functions used across the project.
"""

import base64
import io
import logging
import random
import re
import time
from typing import Any, Generator, List, Optional

import requests

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# User-agent pool
# ------------------------------------------------------------------ #

_USER_AGENTS: List[str] = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
        "Gecko/20100101 Firefox/125.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.4.1 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
    ),
]


# ------------------------------------------------------------------ #
# Public helpers
# ------------------------------------------------------------------ #

def clean_price(price_str: str) -> Optional[float]:
    """
    Parse a price string to a float.

    Handles formats like "$29.99", "₹1,299", "29.99", "1,299.00", etc.

    Args:
        price_str: Raw price string from a web page.

    Returns:
        Price as a float, or None if parsing fails.
    """
    if not price_str:
        return None
    # Remove currency symbols, whitespace, and thousands separators
    cleaned = re.sub(r"[^\d.,]", "", price_str.strip())
    # Handle Indian number format: 1,29,999 → 129999
    cleaned = cleaned.replace(",", "")
    # If multiple dots remain (e.g. "1.299.00"), keep only the last one
    parts = cleaned.split(".")
    if len(parts) > 2:
        cleaned = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        logger.debug("Could not parse price: %r", price_str)
        return None


def clean_rating(rating_str: str) -> Optional[float]:
    """
    Parse a rating string to a float.

    Handles formats like "4.5 out of 5", "4.5", "4", "4.5 stars", etc.

    Args:
        rating_str: Raw rating string from a web page.

    Returns:
        Rating as a float, or None if parsing fails.
    """
    if not rating_str:
        return None
    # Extract the first decimal/integer number
    match = re.search(r"(\d+(?:\.\d+)?)", rating_str)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    logger.debug("Could not parse rating: %r", rating_str)
    return None


def rotate_user_agent() -> str:
    """
    Return a random User-Agent string from the built-in pool.

    Returns:
        A User-Agent string.
    """
    return random.choice(_USER_AGENTS)


def safe_request(
    url: str,
    headers: Optional[dict] = None,
    delay: float = 1.0,
    params: Optional[dict] = None,
    max_retries: int = 3,
    timeout: int = 15,
) -> Optional[requests.Response]:
    """
    Perform an HTTP GET request with automatic retries and error handling.

    Args:
        url: Target URL.
        headers: Optional HTTP headers dict.
        delay: Seconds to wait before the first request (rate limiting).
        params: Optional query parameters dict.
        max_retries: Number of retry attempts on transient errors.
        timeout: Request timeout in seconds.

    Returns:
        :class:`requests.Response` on success, or ``None`` on failure.
    """
    time.sleep(delay)

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(
                url,
                headers=headers or {},
                params=params,
                timeout=timeout,
            )
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                # Rate limited — back off exponentially
                wait = delay * (2 ** attempt)
                logger.warning(
                    "Rate limited (429) on %s. Waiting %.1fs before retry %d/%d.",
                    url,
                    wait,
                    attempt,
                    max_retries,
                )
                time.sleep(wait)
            elif response.status_code in (403, 404):
                logger.warning(
                    "HTTP %d for %s. Not retrying.", response.status_code, url
                )
                return None
            else:
                logger.warning(
                    "HTTP %d for %s (attempt %d/%d).",
                    response.status_code,
                    url,
                    attempt,
                    max_retries,
                )
        except requests.exceptions.Timeout:
            logger.warning("Timeout on %s (attempt %d/%d).", url, attempt, max_retries)
        except requests.exceptions.ConnectionError as exc:
            logger.warning(
                "Connection error on %s (attempt %d/%d): %s", url, attempt, max_retries, exc
            )
        except Exception as exc:
            logger.error("Unexpected error requesting %s: %s", url, exc)
            return None

        if attempt < max_retries:
            time.sleep(delay * attempt)

    logger.error("All %d attempts failed for %s.", max_retries, url)
    return None


def encode_chart_to_base64(fig) -> str:
    """
    Convert a Matplotlib figure to a base64-encoded PNG string.

    Args:
        fig: A :class:`matplotlib.figure.Figure` instance.

    Returns:
        Base64-encoded PNG string (suitable for embedding in HTML ``<img>`` tags).
    """
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    buf.close()
    return encoded


def chunk_list(lst: List[Any], size: int) -> Generator[List[Any], None, None]:
    """
    Split a list into chunks of at most *size* elements.

    Args:
        lst: The list to split.
        size: Maximum chunk size.

    Yields:
        Sub-lists of length <= *size*.

    Example::

        list(chunk_list([1, 2, 3, 4, 5], 2))
        # → [[1, 2], [3, 4], [5]]
    """
    for i in range(0, len(lst), size):
        yield lst[i : i + size]
