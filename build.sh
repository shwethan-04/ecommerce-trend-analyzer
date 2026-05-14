#!/usr/bin/env bash
set -e

echo "=== Installing dependencies ==="
pip install -r requirements.txt

echo "=== Downloading TextBlob corpora ==="
python -c "import textblob; textblob.download_corpora()" 2>/dev/null || \
python -m textblob.download_corpora 2>/dev/null || \
python -c "import nltk; nltk.download('punkt'); nltk.download('averaged_perceptron_tagger')" || true

echo "=== Initialising database ==="
python -c "
import sys, os
sys.path.insert(0, os.getcwd())
from database.db import init_db
init_db()
print('DB initialised.')
"

echo "=== Seeding data ==="
python main.py --mode all --keyword "laptop" || true
python main.py --mode scrape --keyword "smartphone" || true

echo "=== Build complete ==="
