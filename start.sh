#!/usr/bin/env bash
set -e

echo "=== Downloading TextBlob corpora ==="
python -c "
import nltk
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)
nltk.download('averaged_perceptron_tagger', quiet=True)
" || true

echo "=== Initialising database ==="
python -c "
import sys, os
sys.path.insert(0, os.getcwd())
from database.db import init_db
init_db()
print('DB ready.')
"

echo "=== Seeding data (scrape + analyze + predict) ==="
python main.py --mode scrape --keyword "laptop" || true
python main.py --mode scrape --keyword "smartphone" || true
python main.py --mode analyze || true
python main.py --mode predict || true

echo "=== Starting web server ==="
exec gunicorn "dashboard.app:app" \
  --bind "0.0.0.0:$PORT" \
  --workers 1 \
  --timeout 120 \
  --preload
