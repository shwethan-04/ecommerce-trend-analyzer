"""
Entry point for the E-Commerce Trend Analyzer.

Usage examples
--------------
Start the REST API:
    python main.py --mode api

Start the Flask dashboard:
    python main.py --mode dashboard

Scrape products for a keyword:
    python main.py --mode scrape --keyword "wireless headphones"

Run sentiment analysis on unanalysed reviews:
    python main.py --mode analyze

Train the ML model and generate predictions:
    python main.py --mode predict

Run the full pipeline (scrape → analyse → predict):
    python main.py --mode all --keyword "laptop"
"""

import argparse
import logging
import sys

# ------------------------------------------------------------------ #
# Logging setup (must happen before any project imports)
# ------------------------------------------------------------------ #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Mode runners
# ------------------------------------------------------------------ #

def run_api() -> None:
    """Start the FastAPI server with uvicorn."""
    import uvicorn

    from config import settings

    logger.info("Starting FastAPI server on %s:%d", settings.API_HOST, settings.API_PORT)
    uvicorn.run(
        "api.app:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level="info",
    )


def run_dashboard() -> None:
    """Start the Flask dashboard server."""
    from config import settings
    from dashboard.app import app

    logger.info(
        "Starting Flask dashboard on %s:%d",
        settings.DASHBOARD_HOST,
        settings.DASHBOARD_PORT,
    )
    app.run(
        host=settings.DASHBOARD_HOST,
        port=settings.DASHBOARD_PORT,
        debug=settings.DEBUG,
    )


def run_scrape(keyword: str) -> None:
    """
    Run all scrapers for *keyword* and persist results to the database.

    Args:
        keyword: Search term to scrape.
    """
    from database.db import db_session, init_db
    from database.models import Product, Review, TrendData
    from scrapers.amazon_scraper import AmazonScraper
    from scrapers.flipkart_scraper import FlipkartScraper
    from scrapers.reddit_scraper import RedditScraper

    init_db()

    logger.info("=== Scraping keyword: %r ===", keyword)

    # Amazon
    logger.info("--- Amazon ---")
    amazon = AmazonScraper()
    amazon_products = amazon.scrape_products(keyword, max_pages=3)
    logger.info("Amazon: %d products found.", len(amazon_products))

    # Flipkart
    logger.info("--- Flipkart ---")
    flipkart = FlipkartScraper()
    flipkart_products = flipkart.scrape_products(keyword, max_pages=3)
    logger.info("Flipkart: %d products found.", len(flipkart_products))

    # Reddit
    logger.info("--- Reddit ---")
    reddit = RedditScraper()
    reddit_trends = reddit.get_trending_keywords()
    logger.info("Reddit: %d trending keywords.", len(reddit_trends))

    # Google Trends
    logger.info("--- Google Trends ---")
    google_trends = reddit.get_google_trends([keyword])
    logger.info("Google Trends: %d data points.", len(google_trends))

    # Persist to DB and auto-generate synthetic reviews from ratings
    from analytics.sentiment import SentimentAnalyzer
    from database.models import Review

    analyzer = SentimentAnalyzer()

    # Review templates keyed by sentiment bucket
    _POSITIVE_REVIEWS = [
        "Absolutely love this product! Exceeded all my expectations.",
        "Great quality and fast delivery. Would definitely buy again.",
        "Highly recommend this to anyone looking for a reliable option.",
        "Fantastic value for money. Works perfectly.",
        "Very happy with this purchase. Top notch quality.",
        "Outstanding product. Does exactly what it promises.",
        "Best purchase I've made this year. Totally worth it.",
    ]
    _NEUTRAL_REVIEWS = [
        "It's okay. Does the job but nothing special.",
        "Average product. Met basic expectations.",
        "Decent quality for the price. Not amazing but acceptable.",
        "Works as described. Nothing more, nothing less.",
        "Fairly standard. Would consider alternatives next time.",
    ]
    _NEGATIVE_REVIEWS = [
        "Disappointed with the quality. Expected much better.",
        "Not worth the price. Would not recommend.",
        "Had issues from day one. Poor build quality.",
        "Stopped working after a week. Very frustrating.",
        "Does not match the description at all. Misleading.",
    ]

    import random

    def _reviews_for_rating(rating: float, count: int = 3):
        """Generate synthetic review texts based on product rating."""
        reviews = []
        for _ in range(count):
            if rating >= 4.0:
                reviews.append(random.choice(_POSITIVE_REVIEWS))
            elif rating >= 3.0:
                reviews.append(random.choice(_NEUTRAL_REVIEWS))
            else:
                reviews.append(random.choice(_NEGATIVE_REVIEWS))
        return reviews

    with db_session() as db:
        saved_products = 0
        saved_reviews  = 0

        for p in amazon_products + flipkart_products:
            product = Product(
                name=p["name"],
                price=p.get("price"),
                rating=p.get("rating"),
                reviews_count=p.get("reviews_count", 0),
                category=p.get("category"),
                availability=p.get("availability", "unknown"),
                source=p["source"],
                url=p.get("url"),
            )
            db.add(product)
            db.flush()  # get product.id

            # Generate 3–5 synthetic reviews per product
            rating = p.get("rating") or 3.0
            num_reviews = random.randint(3, 5)
            for text in _reviews_for_rating(rating, num_reviews):
                result = analyzer.analyze_text(text)
                review = Review(
                    product_id=product.id,
                    text=text,
                    sentiment=result["sentiment"],
                    sentiment_score=result["score"],
                )
                db.add(review)
                saved_reviews += 1

            saved_products += 1

        for t in reddit_trends + google_trends:
            trend = TrendData(
                keyword=t["keyword"],
                platform=t["platform"],
                score=t["score"],
                date=t["date"],
                category=t.get("category"),
            )
            db.add(trend)

    total = len(amazon_products) + len(flipkart_products)
    logger.info(
        "Scrape complete. Saved %d products, %d reviews, %d trend records.",
        total, saved_reviews, len(reddit_trends) + len(google_trends),
    )


def run_analysis() -> None:
    """
    Run sentiment analysis on all reviews that have not yet been analysed
    (sentiment == 'neutral' and sentiment_score == 0.0 is used as a proxy
    for 'unanalysed' since we store the result at scrape time; this function
    re-analyses all reviews to refresh scores).
    """
    from analytics.sentiment import SentimentAnalyzer
    from database.db import db_session, init_db
    from database.models import Review

    init_db()

    analyzer = SentimentAnalyzer()

    with db_session() as db:
        reviews = db.query(Review).all()
        if not reviews:
            logger.info("No reviews found in the database.")
            return

        updated = 0
        for review in reviews:
            result = analyzer.analyze_text(review.text)
            review.sentiment = result["sentiment"]
            review.sentiment_score = result["score"]
            updated += 1

        logger.info("Sentiment analysis complete. Updated %d reviews.", updated)


def run_predictions() -> None:
    """Train the ML model (or load a saved one) and generate predictions for all products."""
    from analytics.predictor import TrendPredictor
    from database.db import db_session, init_db

    init_db()

    predictor = TrendPredictor()

    with db_session() as db:
        ready = predictor.load_or_train(db)
        if not ready:
            logger.error("Could not load or train the model. Aborting predictions.")
            return

        count = predictor.batch_predict(db)
        logger.info("Predictions complete. Generated %d predictions.", count)


def run_all(keyword: str) -> None:
    """
    Run the full pipeline: scrape → analyse → predict.

    Args:
        keyword: Search term to use for scraping.
    """
    logger.info("=== Full pipeline start ===")
    run_scrape(keyword)
    run_analysis()
    run_predictions()
    logger.info("=== Full pipeline complete ===")


# ------------------------------------------------------------------ #
# CLI
# ------------------------------------------------------------------ #

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="E-Commerce Trend Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mode",
        choices=["api", "dashboard", "scrape", "analyze", "predict", "all"],
        required=True,
        help="Operation mode.",
    )
    parser.add_argument(
        "--keyword",
        default="laptop",
        help="Search keyword for scrape / all modes (default: 'laptop').",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    mode_map = {
        "api": run_api,
        "dashboard": run_dashboard,
        "scrape": lambda: run_scrape(args.keyword),
        "analyze": run_analysis,
        "predict": run_predictions,
        "all": lambda: run_all(args.keyword),
    }

    runner = mode_map.get(args.mode)
    if runner is None:
        logger.error("Unknown mode: %s", args.mode)
        sys.exit(1)

    try:
        runner()
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    except Exception as exc:
        logger.exception("Unhandled error in mode=%s: %s", args.mode, exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
