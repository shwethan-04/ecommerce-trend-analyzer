"""
Chart generation using Matplotlib and Seaborn.
All public methods return base64-encoded PNG strings.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ── Shared palette ───────────────────────────────────────────────────────────
_BG      = "#080d14"
_BG_CARD = "#111c2d"
_BORDER  = "#1e2d42"
_TEXT    = "#e8f0fe"
_MUTED   = "#7a90b0"
_COLORS  = [
    "#0ea5e9", "#10b981", "#f59e0b", "#f43f5e", "#818cf8",
    "#38bdf8", "#34d399", "#fbbf24", "#fb7185", "#a5b4fc",
]

import matplotlib
matplotlib.use("Agg")  # must be set before any other matplotlib import


def _apply_dark_style(fig, ax):
    """Apply consistent dark theme to a figure/axes pair."""
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG_CARD)
    ax.tick_params(colors=_TEXT, labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor(_BORDER)


class ChartGenerator:
    """
    Generates visualisation charts for the dashboard.
    All methods return a base64-encoded PNG string.
    """

    # ------------------------------------------------------------------ #
    # Trending products bar
    # ------------------------------------------------------------------ #

    def trending_products_bar(
        self, products_data: List[Dict[str, Any]], top_n: int = 15
    ) -> str:
        """Horizontal bar chart of top trending products by trend score."""
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
        import matplotlib.colors as mcolors
        import numpy as np
        from utils.helpers import encode_chart_to_base64

        data = sorted(
            products_data, key=lambda x: x.get("trend_score", 0), reverse=True
        )[:top_n]

        if not data:
            return self._empty_chart("No trending products data available.\nRun: python main.py --mode scrape --keyword laptop")

        names  = [
            (d["name"][:42] + "…") if len(d["name"]) > 42 else d["name"]
            for d in data
        ]
        scores = [d.get("trend_score", 0) for d in data]

        fig, ax = plt.subplots(figsize=(10, max(4, len(names) * 0.55)))
        _apply_dark_style(fig, ax)

        # Safe colormap — works on all matplotlib versions
        cmap      = cm.get_cmap("YlGnBu") if hasattr(cm, "get_cmap") else plt.colormaps["YlGnBu"]
        s_min, s_max = min(scores), max(scores) + 1e-9
        norm_vals = [(s - s_min) / (s_max - s_min) for s in scores]
        bar_colors = [cmap(v) for v in norm_vals]

        bars = ax.barh(
            names[::-1], scores[::-1],
            color=bar_colors[::-1],
            edgecolor=_BORDER, linewidth=0.5,
        )
        ax.set_xlabel("Trend Score", color=_MUTED, fontsize=9)
        ax.set_title("Top Trending Products", color=_TEXT, fontsize=13,
                     fontweight="bold", pad=14)

        for bar, score in zip(bars, scores[::-1]):
            ax.text(
                bar.get_width() + 0.4,
                bar.get_y() + bar.get_height() / 2,
                f"{score:.1f}",
                va="center", color=_MUTED, fontsize=8,
            )

        ax.set_xlim(0, max(scores) * 1.18)
        plt.tight_layout()
        result = encode_chart_to_base64(fig)
        plt.close(fig)
        return result

    # ------------------------------------------------------------------ #
    # Rating distribution
    # ------------------------------------------------------------------ #

    def rating_distribution(self, products_data: List[Dict[str, Any]]) -> str:
        """Histogram of product ratings."""
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
        import numpy as np
        from utils.helpers import encode_chart_to_base64

        ratings = [
            float(d["rating"])
            for d in products_data
            if d.get("rating") is not None
        ]

        if not ratings:
            return self._empty_chart("No rating data available.\nRun a scrape first.")

        fig, ax = plt.subplots(figsize=(8, 4.5))
        _apply_dark_style(fig, ax)

        cmap = cm.get_cmap("RdYlGn") if hasattr(cm, "get_cmap") else plt.colormaps["RdYlGn"]

        n, bins, patches = ax.hist(
            ratings, bins=20, range=(0, 5),
            edgecolor=_BORDER, linewidth=0.4,
        )
        for patch, left in zip(patches, bins[:-1]):
            patch.set_facecolor(cmap(left / 5.0))

        mean_val = float(np.mean(ratings))
        ax.axvline(
            mean_val, color=_COLORS[2], linestyle="--", linewidth=1.5,
            label=f"Mean: {mean_val:.2f}",
        )
        ax.set_xlabel("Rating (0–5)", color=_MUTED, fontsize=9)
        ax.set_ylabel("Products", color=_MUTED, fontsize=9)
        ax.set_title("Rating Distribution", color=_TEXT, fontsize=13,
                     fontweight="bold", pad=14)
        ax.legend(facecolor=_BG_CARD, labelcolor=_TEXT, fontsize=8, framealpha=0.8)

        plt.tight_layout()
        result = encode_chart_to_base64(fig)
        plt.close(fig)
        return result

    # ------------------------------------------------------------------ #
    # Sentiment heatmap
    # ------------------------------------------------------------------ #

    def sentiment_heatmap(self, heatmap_data: Dict[str, Any]) -> str:
        """Seaborn heatmap of sentiment score by category × source."""
        import matplotlib.pyplot as plt
        import numpy as np
        import seaborn as sns
        from utils.helpers import encode_chart_to_base64

        categories = heatmap_data.get("categories", [])
        sources    = heatmap_data.get("sources", [])
        matrix     = heatmap_data.get("matrix", [])

        if not categories or not sources or not matrix:
            return self._empty_chart(
                "No sentiment heatmap data.\nReviews are needed — run analyze mode first."
            )

        data = np.array(matrix, dtype=float)
        rows = max(4, len(categories) * 0.7)
        cols = max(6, len(sources) * 2.4)

        fig, ax = plt.subplots(figsize=(cols, rows))
        fig.patch.set_facecolor(_BG)

        sns.heatmap(
            data,
            xticklabels=sources,
            yticklabels=categories,
            annot=True,
            fmt=".2f",
            cmap="coolwarm",
            vmin=-1, vmax=1,
            ax=ax,
            linewidths=0.4,
            linecolor=_BORDER,
            annot_kws={"size": 9},
        )
        ax.set_facecolor(_BG_CARD)
        ax.set_title(
            "Sentiment Heatmap (Category × Source)",
            color=_TEXT, fontsize=13, fontweight="bold", pad=14,
        )
        ax.tick_params(colors=_TEXT, labelsize=8)
        plt.setp(ax.get_xticklabels(), color=_TEXT)
        plt.setp(ax.get_yticklabels(), color=_TEXT)

        cbar = ax.collections[0].colorbar
        if cbar:
            cbar.ax.tick_params(colors=_MUTED, labelsize=8)

        plt.tight_layout()
        result = encode_chart_to_base64(fig)
        plt.close(fig)
        return result

    # ------------------------------------------------------------------ #
    # Popularity line chart
    # ------------------------------------------------------------------ #

    def popularity_line_chart(self, time_series_data: List[Dict[str, Any]]) -> str:
        """Line chart of keyword popularity over time."""
        import matplotlib.pyplot as plt
        from collections import defaultdict
        from utils.helpers import encode_chart_to_base64

        if not time_series_data:
            return self._empty_chart(
                "No trend data yet.\nRun: python main.py --mode scrape --keyword laptop"
            )

        series: Dict[str, list] = defaultdict(list)
        for point in time_series_data:
            series[point["keyword"]].append((point["date"], point["score"]))

        # Limit to top 8 keywords by total score to keep chart readable
        top_keywords = sorted(
            series.keys(),
            key=lambda k: sum(s for _, s in series[k]),
            reverse=True,
        )[:8]

        fig, ax = plt.subplots(figsize=(10, 4.5))
        _apply_dark_style(fig, ax)

        for i, keyword in enumerate(top_keywords):
            pts    = sorted(series[keyword], key=lambda x: x[0])
            dates  = [p[0] for p in pts]
            scores = [p[1] for p in pts]
            color  = _COLORS[i % len(_COLORS)]
            ax.plot(
                dates, scores, label=keyword,
                color=color, linewidth=2,
                marker="o", markersize=3,
                markerfacecolor=color, markeredgewidth=0,
            )
            ax.fill_between(dates, scores, alpha=0.07, color=color)

        ax.set_xlabel("Date", color=_MUTED, fontsize=9)
        ax.set_ylabel("Trend Score", color=_MUTED, fontsize=9)
        ax.set_title("Keyword Popularity Over Time", color=_TEXT, fontsize=13,
                     fontweight="bold", pad=14)
        ax.legend(facecolor=_BG_CARD, labelcolor=_TEXT, fontsize=8,
                  framealpha=0.8, loc="upper left")
        ax.grid(axis="y", color=_BORDER, linewidth=0.5, linestyle="--", alpha=0.6)

        fig.autofmt_xdate()
        plt.tight_layout()
        result = encode_chart_to_base64(fig)
        plt.close(fig)
        return result

    # ------------------------------------------------------------------ #
    # Category donut chart
    # ------------------------------------------------------------------ #

    def category_pie_chart(self, category_data: List[Dict[str, Any]]) -> str:
        """Donut chart of product distribution by category."""
        import matplotlib.pyplot as plt
        from utils.helpers import encode_chart_to_base64

        filtered = [
            d for d in category_data
            if d.get("product_count", 0) > 0
        ]

        if not filtered:
            return self._empty_chart("No category data.\nRun a scrape first.")

        labels = [d.get("category") or "Unknown" for d in filtered]
        sizes  = [d["product_count"] for d in filtered]

        fig, ax = plt.subplots(figsize=(8, 5.5))
        fig.patch.set_facecolor(_BG)
        ax.set_facecolor(_BG)

        wedges, texts, autotexts = ax.pie(
            sizes,
            labels=labels,
            autopct="%1.1f%%",
            colors=_COLORS[: len(labels)],
            startangle=140,
            wedgeprops={"edgecolor": _BG, "linewidth": 2, "width": 0.65},
            pctdistance=0.78,
        )
        for text in texts:
            text.set_color(_TEXT)
            text.set_fontsize(9)
        for autotext in autotexts:
            autotext.set_color(_BG)
            autotext.set_fontsize(8)
            autotext.set_fontweight("bold")

        ax.set_title("Products by Category", color=_TEXT, fontsize=13,
                     fontweight="bold", pad=14)

        plt.tight_layout()
        result = encode_chart_to_base64(fig)
        plt.close(fig)
        return result

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _empty_chart(message: str) -> str:
        """Return a placeholder chart with a helpful message."""
        import matplotlib.pyplot as plt
        from utils.helpers import encode_chart_to_base64

        fig, ax = plt.subplots(figsize=(7, 3))
        fig.patch.set_facecolor(_BG)
        ax.set_facecolor(_BG_CARD)
        ax.text(
            0.5, 0.5, message,
            ha="center", va="center",
            color=_MUTED, fontsize=10,
            transform=ax.transAxes,
            linespacing=1.8,
        )
        ax.axis("off")
        result = encode_chart_to_base64(fig)
        plt.close(fig)
        return result
