#!/usr/bin/env python3
"""
test_retrieval.py
=================
Evaluate top-5 retrieval accuracy on the 10-question golden set
(data/golden_retrieval_10.json).

For each question we call query_store(question, n_results=5), check whether
the expected doc_id appears among the returned chunks' doc_ids, report a
per-question YES/NO (and rank if found), then print + write a summary CSV
to eval_results/retrieval_test_10.csv.

Run from the project root:

    python src/test_retrieval.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from embed_store import query_store


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = ROOT / "data" / "golden_retrieval_10.json"
EVAL_DIR = ROOT / "eval_results"
EVAL_CSV = EVAL_DIR / "retrieval_test_10.csv"


def main() -> None:
    if not GOLDEN_PATH.exists():
        sys.exit(f"ERROR: golden set not found at {GOLDEN_PATH}")

    with GOLDEN_PATH.open("r", encoding="utf-8") as f:
        golden = json.load(f)

    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    hits = 0

    for entry in golden:
        question = entry["question"]
        expected = entry["expected_doc_id"]

        results = query_store(question, n_results=5)
        returned_doc_ids = [r["doc_id"] for r in results]

        found = expected in returned_doc_ids
        rank = returned_doc_ids.index(expected) + 1 if found else None
        if found:
            hits += 1

        q_trunc = question if len(question) <= 60 else question[:57] + "..."
        status = f"YES (rank {rank})" if found else "NO"
        print(f"Q: {q_trunc:60s}  expected={expected:40s}  {status}")

        rows.append({
            "question": question,
            "expected_doc_id": expected,
            "found": found,
            "rank": rank if found else "",
            "returned_doc_ids": ";".join(returned_doc_ids),
        })

    total = len(golden)
    pct = 100.0 * hits / total if total else 0.0
    summary = f"Retrieval accuracy: {hits}/{total} ({pct:.0f}%)"
    print()
    print(summary)

    # Write CSV
    with EVAL_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["question", "expected_doc_id", "found", "rank",
                         "returned_doc_ids"])
        for r in rows:
            writer.writerow([r["question"], r["expected_doc_id"],
                             "YES" if r["found"] else "NO",
                             r["rank"], r["returned_doc_ids"]])
        writer.writerow([])
        writer.writerow(["SUMMARY", summary])

    print(f"\nWrote results to {EVAL_CSV}")


if __name__ == "__main__":
    main()
