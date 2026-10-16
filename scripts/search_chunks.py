#!/usr/bin/env python3
"""
search_chunks.py
================
Read data/processed/all_chunks.json directly and print matching chunks.

This is the tool used to grade data/gold_chunks.json. It deliberately does
NOT go anywhere near the retriever: a gold set assembled from query_store()
would grade the system on whether it retrieves what it already retrieves.

Usage:
    python scripts/search_chunks.py --doc hefamaa_requirements
    python scripts/search_chunks.py --grep "room|dimension"
    python scripts/search_chunks.py --doc mlscn_guidelines --grep "16 ft"
    python scripts/search_chunks.py --id mlscn_guidelines#0014
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNKS = ROOT / "data" / "processed" / "all_chunks.json"

# Windows consoles default to cp1252; OCR output contains full-width commas
# and other characters that would otherwise crash the print below.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    parser.add_argument("--doc", help="Only chunks from this doc_id.")
    parser.add_argument("--grep", help="Regex over the chunk text.")
    parser.add_argument("--id", help="Print exactly this chunk_id.")
    parser.add_argument("--min-chars", type=int, default=0,
                        help="Skip chunks shorter than this.")
    parser.add_argument("--context", type=int, default=700,
                        help="Characters of chunk text to print (0 = all).")
    args = parser.parse_args()

    if not CHUNKS.exists():
        raise SystemExit(f"missing {CHUNKS} - run scripts/build.sh first")
    chunks = json.loads(CHUNKS.read_text(encoding="utf-8"))
    pattern = re.compile(args.grep) if args.grep else None

    shown = 0
    for chunk in chunks:
        if args.id and chunk.get("chunk_id") != args.id:
            continue
        if args.doc and chunk.get("doc_id") != args.doc:
            continue
        text = chunk.get("text", "")
        if len(text) < args.min_chars:
            continue
        if pattern and not pattern.search(text):
            continue
        shown += 1
        preview = text if args.context == 0 else text[: args.context]
        print("=" * 78)
        print(f"{chunk.get('chunk_id')}  [{chunk.get('doc_id')}]  "
              f"{len(text)} chars")
        print(f"  section: {chunk.get('section_label')}")
        print("-" * 78)
        print(preview.replace("\n", " "))
    print("=" * 78)
    print(f"{shown} chunk(s) matched out of {len(chunks)}.")


if __name__ == "__main__":
    main()
