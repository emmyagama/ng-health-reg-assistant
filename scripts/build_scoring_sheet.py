#!/usr/bin/env python3
"""
build_scoring_sheet.py
======================
Generate eval_results/v1_scoring_sheet.csv — one row per question of the
50-question v1 run, with every metric that can be computed mechanically and
a blank `groundedness_score` column for the human reader.

The rubric lives in the companion file eval_results/v1_scoring_sheet.md.
Do not invent groundedness scores: that column stays empty until a human
reads each answer.

Usage:
    python scripts/build_scoring_sheet.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from run_eval import _citation_metrics, _norm  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GOLDEN = ROOT / "data" / "golden_set_50.json"
GOLD_CHUNKS = ROOT / "data" / "gold_chunks.json"
ALL_CHUNKS = ROOT / "data" / "processed" / "all_chunks.json"
RUN_CSV = ROOT / "eval_results" / "b1_v1.csv"
OUT_CSV = ROOT / "eval_results" / "v1_scoring_sheet.csv"
OUT_MD = ROOT / "eval_results" / "v1_scoring_sheet.md"

FIELDNAMES = [
    "id",
    "question",
    "answerable",
    "category",
    "expected_behaviour",
    "shown_to_user",
    "status",
    "refusal_reasons",
    "retrieval_hit",
    "gold_retrieved",
    "gold_total",
    "first_gold_rank",
    "distance_min",
    "distance_mean",
    "citations_total",
    "citations_correct",
    "citations_missing",
    "answer_has_citation",
    "latency_seconds",
    "output_tokens",
    "groundedness_score",
]


def main() -> None:
    for path in (GOLDEN, GOLD_CHUNKS, ALL_CHUNKS, RUN_CSV):
        if not path.exists():
            raise SystemExit(f"missing {path}")

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    gold_records = json.loads(GOLD_CHUNKS.read_text(encoding="utf-8"))
    chunks = json.loads(ALL_CHUNKS.read_text(encoding="utf-8"))

    golden_by_id = {str(e["id"]): e for e in golden}
    gold_by_id = {str(r["id"]): r for r in gold_records}
    chunk_index = {
        c["chunk_id"]: (c.get("doc_title", ""), c.get("section_label", ""))
        for c in chunks}

    rows = list(csv.DictReader(RUN_CSV.open(encoding="utf-8")))
    if len(rows) != len(golden):
        print(f"WARNING: {RUN_CSV.name} has {len(rows)} rows, "
              f"golden set has {len(golden)} questions")

    out_rows = []
    for row in rows:
        qid = str(row["id"])
        entry = golden_by_id.get(qid, {})
        record = gold_by_id.get(qid, {})
        gold_ids = [g["chunk_id"] for g in record.get("gold_chunks", [])]
        retrieved = [c for c in row["retrieved_chunk_ids"].split(";") if c]

        gold_retrieved = sum(1 for cid in gold_ids if cid in retrieved)
        first_rank = next(
            (i + 1 for i, cid in enumerate(retrieved) if cid in gold_ids), "")

        distances = [float(d) for d in row["retrieved_distances"].split(";")
                     if d]
        dist_min = min(distances) if distances else ""
        dist_mean = (sum(distances) / len(distances)) if distances else ""

        cm = _citation_metrics(row["answer_text"], retrieved, chunk_index, 5)
        has_citation = "yes" if cm["citations_total"] else "no"

        out_rows.append({
            "id": qid,
            "question": row["question"],
            "answerable": row["answerable"],
            "category": entry.get("category", ""),
            "expected_behaviour": entry.get("expected_behaviour", ""),
            "shown_to_user": row["shown_to_user"],
            "status": row["status"],
            "refusal_reasons": row["refusal_reasons"],
            "retrieval_hit": row["retrieval_hit"],
            "gold_retrieved": gold_retrieved if gold_ids else "",
            "gold_total": len(gold_ids) if gold_ids else "",
            "first_gold_rank": first_rank,
            "distance_min": f"{dist_min:.4f}" if dist_min != "" else "",
            "distance_mean": f"{dist_mean:.4f}" if dist_mean != "" else "",
            "citations_total": cm["citations_total"],
            "citations_correct": cm["citations_correct"],
            "citations_missing": cm["citations_missing"],
            "answer_has_citation": has_citation,
            "latency_seconds": row["latency_seconds"],
            "output_tokens": row["output_tokens"],
            "groundedness_score": "",
        })

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(out_rows)

    answered = sum(1 for r in out_rows if r["shown_to_user"] == "answer")
    blank = sum(1 for r in out_rows if r["groundedness_score"] == "")
    print(f"wrote {OUT_CSV} — {len(out_rows)} rows, "
          f"{answered} shown as answers, {blank} groundedness scores blank")
    print(f"rubric: {OUT_MD}")


if __name__ == "__main__":
    main()
