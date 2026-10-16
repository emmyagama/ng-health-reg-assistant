#!/usr/bin/env bash
# Build the vector store from a clean clone in one command:
#
#   bash scripts/build.sh
#
# Steps: acquire + validate the corpus, verify it against the committed
# lockfile, chunk it, embed it.  OCR for textless PDFs happens inside
# download_corpus.py, so there is no manual step.
#
# Requires Python 3.10-3.12 (rapidocr-onnxruntime, used for content
# verification of the one scanned PDF, publishes no 3.13 wheel).
set -euo pipefail

cd "$(dirname "$0")/.."

# --- pick an interpreter that satisfies 3.10 <= v < 3.13 --------------
if [ -z "${PYTHON:-}" ]; then
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 \
       && "$candidate" -c "import sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] < (3,13) else 1)" 2>/dev/null; then
      PYTHON="$candidate"
      break
    fi
  done
fi
if [ -z "${PYTHON:-}" ]; then
  echo "ERROR: no Python 3.10-3.12 interpreter found (python3/python)." >&2
  echo "       rapidocr-onnxruntime==1.4.4 has no wheel for Python >= 3.13." >&2
  exit 1
fi
echo "Using $PYTHON ($("$PYTHON" --version 2>&1))"

START=$(date +%s)

"$PYTHON" download_corpus.py --retry 3
"$PYTHON" download_corpus.py --verify
"$PYTHON" src/chunker.py
"$PYTHON" src/embed_store.py

END=$(date +%s)
CHUNKS=$("$PYTHON" -c "import json;print(len(json.load(open('data/processed/all_chunks.json',encoding='utf-8'))))")
echo "BUILD OK: ${CHUNKS} chunks in $((END - START))s ($(((END - START) / 60))m $(((END - START) % 60))s)"
