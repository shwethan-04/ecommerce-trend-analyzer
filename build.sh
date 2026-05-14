#!/usr/bin/env bash
set -e

echo "=== Installing dependencies ==="
pip install -r requirements.txt

echo "=== Downloading TextBlob corpora ==="
python -c "
import nltk
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)
nltk.download('averaged_perceptron_tagger', quiet=True)
nltk.download('averaged_perceptron_tagger_eng', quiet=True)
" || true

echo "=== Initialising database ==="
python -c "
import sys, os
sys.path.insert(0, os.getcwd())
from database.db import init_db
init_db()
print('DB tables created.')
"

echo "=== Build complete — data will be seeded on first startup ==="
