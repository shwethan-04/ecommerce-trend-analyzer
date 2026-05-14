"""
Flask dashboard application.
"""

import logging
from typing import Any, Dict

from flask import Flask, jsonify, render_template, request

logger = logging.getLogger(__name__)


def _auto_seed() -> None:
    """
    Seed the database with product data on first startup if it is empty.
    Runs in a background thread so it does not block the server from starting.
    """
    import threading

    def _seed():
        try:
            from database.db import db_session
            from database.models import Product
            from sqlalchemy import func

            with db_session() as db:
                count = db.query(func.count(Product.id)).scalar() or 0

            if count > 0:
                logger.info("DB already has %d products — skipping auto-seed.", count)
                return

            logger.info("DB is empty — running auto-seed pipeline...")
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

            # Import pipeline runners
            from main import run_scrape, run_analysis, run_predictions

            for keyword in ["laptop", "smartphone", "headphones"]:
                try:
                    run_scrape(keyword)
                except Exception as exc:
                    logger.warning("Seed scrape failed for %r: %s", keyword, exc)

            try:
                run_analysis()
            except Exception as exc:
                logger.warning("Seed analysis failed: %s", exc)

            try:
                run_predictions()
            except Exception as exc:
                logger.warning("Seed predictions failed: %s", exc)

            logger.info("Auto-seed complete.")
        except Exception as exc:
            logger.error("Auto-seed error: %s", exc)

    t = threading.Thread(target=_seed, daemon=True)
    t.start()



def create_dashboard_app() -> Flask:
    """
    Create and configure the Flask dashboard application.

    Returns:
        Configured Flask instance.
    """
    import os

    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    app = Flask(__name__, template_folder=template_dir)

    # Ensure DB tables exist and seed data if empty
    from database.db import init_db
    init_db()
    _auto_seed()

    # ------------------------------------------------------------------ #
    # Routes
    # ------------------------------------------------------------------ #

    @app.route("/")
    def index():
        """Render the main dashboard page."""
        return render_template("index.html")

    @app.route("/api/chart/<chart_type>")
    def get_chart(chart_type: str):
        """Return a base64-encoded chart PNG as JSON."""
        import traceback
        from dashboard.charts import ChartGenerator
        from database.db import db_session

        generator = ChartGenerator()

        try:
            with db_session() as db:
                if chart_type == "trending_bar":
                    from analytics.trends import TrendAnalyzer
                    data = TrendAnalyzer().identify_trending_products(db, limit=15)
                    chart = generator.trending_products_bar(data)

                elif chart_type == "rating_distribution":
                    from database.models import Product
                    products = db.query(Product).all()
                    data = [{"rating": p.rating} for p in products]
                    chart = generator.rating_distribution(data)

                elif chart_type == "sentiment_heatmap":
                    from analytics.trends import TrendAnalyzer
                    heatmap_data = TrendAnalyzer().generate_heatmap_data(db)
                    chart = generator.sentiment_heatmap(heatmap_data)

                elif chart_type == "popularity_line":
                    from database.models import TrendData
                    rows = db.query(TrendData).order_by(TrendData.date.asc()).limit(500).all()
                    data = [
                        {
                            "date": r.date.isoformat() if r.date else "",
                            "score": r.score,
                            "keyword": r.keyword,
                        }
                        for r in rows
                    ]
                    chart = generator.popularity_line_chart(data)

                elif chart_type == "category_pie":
                    from analytics.trends import TrendAnalyzer
                    data = TrendAnalyzer().compare_categories(db)
                    chart = generator.category_pie_chart(data)

                else:
                    return jsonify({"error": f"Unknown chart type: {chart_type}"}), 400

            return jsonify({"chart": chart, "type": chart_type})

        except Exception as exc:
            tb = traceback.format_exc()
            logger.error("Chart generation failed for %s:\n%s", chart_type, tb)
            return jsonify({"error": str(exc), "detail": tb}), 500

    @app.route("/api/debug")
    def debug_info():
        """Return DB stats and any import errors — useful for diagnosing 500s."""
        import sys
        info = {"python": sys.version, "status": "ok", "errors": []}
        try:
            from database.db import db_session
            from database.models import Product, Review, TrendData
            from sqlalchemy import func
            with db_session() as db:
                info["products"]   = db.query(func.count(Product.id)).scalar()
                info["reviews"]    = db.query(func.count(Review.id)).scalar()
                info["trend_data"] = db.query(func.count(TrendData.id)).scalar()
        except Exception as exc:
            info["errors"].append(str(exc))
            info["status"] = "db_error"
        try:
            import matplotlib
            info["matplotlib"] = matplotlib.__version__
        except Exception as exc:
            info["errors"].append(f"matplotlib: {exc}")
        try:
            import seaborn
            info["seaborn"] = seaborn.__version__
        except Exception as exc:
            info["errors"].append(f"seaborn: {exc}")
        return jsonify(info)

    @app.route("/api/products/trending")
    def get_trending_products():
        """Return top trending products (mirrors the FastAPI endpoint for the dashboard)."""
        from analytics.trends import TrendAnalyzer
        from database.db import db_session

        try:
            limit = int(request.args.get("limit", 20))
            with db_session() as db:
                data = TrendAnalyzer().identify_trending_products(db, limit=limit)
            return jsonify(data)
        except Exception as exc:
            logger.error("Trending products fetch failed: %s", exc)
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/data/summary")
    def get_summary() -> Any:
        """
        Return high-level summary statistics for the dashboard cards.

        Returns JSON with:
          - total_products (int)
          - avg_rating (float)
          - positive_sentiment_pct (float)
          - trending_keywords (list[str])
          - total_reviews (int)
          - sources (dict)
        """
        from database.db import db_session
        from database.models import Product, Review, TrendData
        from sqlalchemy import func

        try:
            with db_session() as db:
                total_products = db.query(func.count(Product.id)).scalar() or 0
                avg_rating = db.query(func.avg(Product.rating)).scalar() or 0.0
                total_reviews = db.query(func.count(Review.id)).scalar() or 0

                # Positive sentiment percentage
                pos_count = (
                    db.query(func.count(Review.id))
                    .filter(Review.sentiment == "positive")
                    .scalar()
                    or 0
                )
                positive_pct = (
                    round(pos_count / total_reviews * 100, 1) if total_reviews > 0 else 0.0
                )

                # Top trending keywords from TrendData
                kw_rows = (
                    db.query(TrendData.keyword, func.sum(TrendData.score).label("total"))
                    .group_by(TrendData.keyword)
                    .order_by(func.sum(TrendData.score).desc())
                    .limit(10)
                    .all()
                )
                trending_keywords = [r.keyword for r in kw_rows]

                # Products per source
                source_rows = (
                    db.query(Product.source, func.count(Product.id).label("count"))
                    .group_by(Product.source)
                    .all()
                )
                sources = {r.source: r.count for r in source_rows}

            return jsonify(
                {
                    "total_products": total_products,
                    "avg_rating": round(float(avg_rating), 2),
                    "positive_sentiment_pct": positive_pct,
                    "trending_keywords": trending_keywords,
                    "total_reviews": total_reviews,
                    "sources": sources,
                }
            )
        except Exception as exc:
            logger.error("Summary data fetch failed: %s", exc)
            return jsonify({"error": str(exc)}), 500

    return app


# Module-level app instance
app = create_dashboard_app()
