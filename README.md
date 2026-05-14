# E-Commerce Trend Analyzer

An AI-powered platform that scrapes product data from Amazon and Flipkart, collects trending keywords from Reddit and Google Trends, performs sentiment analysis on reviews, and uses machine learning to predict which products will trend next month.

---

## Features

- **Multi-source scraping** — Amazon, Flipkart, Reddit, Google Trends
- **Sentiment analysis** — TextBlob-powered review scoring
- **Trend scoring** — composite score from rating, reviews, price, and sentiment
- **ML predictions** — RandomForestRegressor predicts next-month trend scores
- **REST API** — FastAPI with auto-generated Swagger docs
- **Dashboard** — Flask + Bootstrap 5 dark-themed dashboard with live charts

---

## Project Structure

```
ecommerce-trend-analyzer/
├── requirements.txt
├── README.md
├── .env.example
├── config.py               # Centralised settings (reads from .env)
├── main.py                 # CLI entry point
├── database/
│   ├── models.py           # SQLAlchemy ORM models
│   └── db.py               # Engine, session factory, init_db
├── scrapers/
│   ├── amazon_scraper.py
│   ├── flipkart_scraper.py
│   └── reddit_scraper.py
├── analytics/
│   ├── sentiment.py        # TextBlob sentiment analysis
│   ├── trends.py           # Trend scoring & aggregation
│   └── predictor.py        # scikit-learn ML predictor
├── api/
│   ├── app.py              # FastAPI app factory
│   └── routes/
│       ├── products.py
│       ├── trends.py
│       ├── sentiment.py
│       └── scraping.py
├── dashboard/
│   ├── app.py              # Flask dashboard
│   ├── charts.py           # Matplotlib/Seaborn chart generator
│   └── templates/
│       └── index.html      # Bootstrap 5 dark dashboard
└── utils/
    └── helpers.py          # Shared utilities
```

---

## Quick Start

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd ecommerce-trend-analyzer
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your Reddit API credentials
```

Get Reddit credentials at <https://www.reddit.com/prefs/apps> (create a "script" app).

### 3. Run the full pipeline

```bash
# Scrape, analyse, and predict in one command
python main.py --mode all --keyword "wireless headphones"
```

### 4. Start the API

```bash
python main.py --mode api
# Swagger UI: http://localhost:8000/docs
```

### 5. Start the dashboard

```bash
python main.py --mode dashboard
# Dashboard: http://localhost:5000
```

---

## CLI Reference

| Command | Description |
|---|---|
| `python main.py --mode api` | Start FastAPI server (port 8000) |
| `python main.py --mode dashboard` | Start Flask dashboard (port 5000) |
| `python main.py --mode scrape --keyword "laptop"` | Scrape all sources for keyword |
| `python main.py --mode analyze` | Run sentiment analysis on all reviews |
| `python main.py --mode predict` | Train model and generate predictions |
| `python main.py --mode all --keyword "laptop"` | Full pipeline |

---

## API Endpoints

### Products
| Method | Path | Description |
|---|---|---|
| GET | `/products` | List products (paginated, filterable) |
| GET | `/products/{id}` | Single product with reviews & prediction |
| GET | `/products/trending` | Top trending products by score |
| POST | `/products` | Create product (testing/seeding) |

### Trends
| Method | Path | Description |
|---|---|---|
| GET | `/trends` | Trend data (filterable by keyword/platform) |
| GET | `/trends/categories` | Category comparison stats |
| GET | `/trends/heatmap` | Sentiment heatmap data |
| GET | `/trends/google?keywords=laptop,phone` | Google Trends data |
| GET | `/trends/keyword/{keyword}` | Time-series for a keyword |

### Sentiment
| Method | Path | Description |
|---|---|---|
| GET | `/sentiment/product/{id}` | Sentiment summary for a product |
| POST | `/sentiment/analyze` | Analyse a single text |
| POST | `/sentiment/analyze/batch` | Analyse multiple texts |
| GET | `/sentiment/overview` | Overall sentiment distribution |

### Scraping
| Method | Path | Description |
|---|---|---|
| POST | `/scrape/amazon` | Trigger async Amazon scrape |
| POST | `/scrape/flipkart` | Trigger async Flipkart scrape |
| POST | `/scrape/reddit` | Trigger async Reddit collection |
| GET | `/scrape/status` | All job statuses |
| GET | `/scrape/status/{job_id}` | Single job status |

---

## Database Models

| Model | Description |
|---|---|
| `Product` | Scraped product (name, price, rating, source, …) |
| `Review` | Product review with sentiment score |
| `TrendData` | Keyword trend scores from Reddit / Google Trends |
| `Prediction` | ML-generated trend predictions |
| `AnalyticsReport` | Stored analytics reports (JSON) |

Default database: `sqlite:///./ecommerce_trends.db`  
Set `DATABASE_URL` in `.env` to use PostgreSQL or MySQL.

---

## Configuration

All settings are read from environment variables (or `.env`):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./ecommerce_trends.db` | SQLAlchemy connection string |
| `API_HOST` | `0.0.0.0` | FastAPI bind host |
| `API_PORT` | `8000` | FastAPI port |
| `DASHBOARD_HOST` | `0.0.0.0` | Flask bind host |
| `DASHBOARD_PORT` | `5000` | Flask port |
| `REDDIT_CLIENT_ID` | — | Reddit app client ID |
| `REDDIT_CLIENT_SECRET` | — | Reddit app client secret |
| `REDDIT_USER_AGENT` | `EcommerceTrendAnalyzer/1.0` | Reddit API user agent |
| `SCRAPE_DELAY` | `2.0` | Seconds between scrape requests |
| `MAX_RETRIES` | `3` | HTTP retry attempts |
| `MODEL_PATH` | `./models/trend_predictor.joblib` | Saved ML model path |

---

## Notes

- Web scraping Amazon and Flipkart may violate their Terms of Service. Use responsibly and only for educational/research purposes.
- The ML model requires at least 5 products in the database to train. Run a scrape first.
- Reddit API credentials are required for Reddit trend collection. Google Trends works without credentials via pytrends.
