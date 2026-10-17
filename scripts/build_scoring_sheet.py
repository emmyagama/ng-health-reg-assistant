#!/usr/bin/env python3
"""
build_scoring_sheet.py
======================
Generate eval_results/v1_scoring_sheet.csv — one row per question of the
50-question v1 run, with every metric that can be computed mechanically and
a `groundedness_score` column for the human reader.

The rubric lives in the companion file eval_results/v1_scoring_sheet.md.
Do not invent groundedness scores: that column stays empty until a human
reads each answer — and once a human has scored rows, those scores are
protected:

  * default run  — refuses to overwrite an existing sheet that contains
    any non-blank groundedness_score (it would destroy human work);
  * --preserve-scores — rebuilds every mechanical column, carries each
    groundedness_score across by question id, writes to a temp path,
    asserts no score was lost or invented, then atomically replaces the
    sheet.

Corpus-free: the chunk_id -> (title, section) index comes from
run_eval._build_chunk_index (the run CSV + data/sources.json +
data/gold_chunks.json), so the sheet can be rebuilt on a clone that has
never run build_corpus.py.

Usage:
    python scripts/build_scoring_sheet.py --preserve-scores
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from run_eval import _build_chunk_index, _citation_metrics  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GOLDEN = ROOT / "data" / "golden_set_50.json"
GOLD_CHUNKS = ROOT / "data" / "gold_chunks.json"
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


def _existing_scores(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    reader = csv.DictReader(path.open(encoding="utf-8"))
    return {
        str(r["id"]): (r.get("groundedness_score") or "").strip()
        for r in reader
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preserve-scores", action="store_true",
        help="carry groundedness_score values from the existing sheet "
             "across by id (refuses if any would be lost)")
    args = parser.parse_args()

    for path in (GOLDEN, GOLD_CHUNKS, RUN_CSV):
        if not path.exists():
            raise SystemExit(f"missing {path}")

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    gold_records = json.loads(GOLD_CHUNKS.read_text(encoding="utf-8"))

    golden_by_id = {str(e["id"]): e for e in golden}
    gold_by_id = {str(r["id"]): r for r in gold_records}

    rows = list(csv.DictReader(RUN_CSV.open(encoding="utf-8")))
    if len(rows) != len(golden):
        print(f"WARNING: {RUN_CSV.name} has {len(rows)} rows, "
              f"golden set has {len(golden)} questions")

    chunk_index = _build_chunk_index(rows, gold_by_id)

    old_scores = _existing_scores(OUT_CSV)
    old_nonblank = {k: v for k, v in old_scores.items() if v}
    if old_nonblank and not args.preserve_scores:
        raise SystemExit(
            f"refusing to overwrite {OUT_CSV.name}: it already contains "
            f"{len(old_nonblank)} human groundedness scores. "
            f"Re-run with --preserve-scores.")

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

    preserved = 0
    if args.preserve_scores:
        if not old_scores:
            raise SystemExit(
                "--preserve-scores: no existing sheet to preserve from")
        for r in out_rows:
            r["groundedness_score"] = old_scores.get(r["id"], "")
        new_nonblank = {
            r["id"]: r["groundedness_score"]
            for r in out_rows if r["groundedness_score"]
        }
        if new_nonblank != old_nonblank:
            lost = sorted(set(old_nonblank) - set(new_nonblank))
            changed = sorted(
                k for k in set(old_nonblank) & set(new_nonblank)
                if old_nonblank[k] != new_nonblank[k])
            extra = sorted(set(new_nonblank) - set(old_nonblank))
            raise SystemExit(
                f"score preservation FAILED — lost={lost} "
                f"changed={changed} extra={extra}")
        preserved = len(new_nonblank)

    tmp = OUT_CSV.with_name(OUT_CSV.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(out_rows)

    reread = list(csv.DictReader(tmp.open(encoding="utf-8")))
    if len(reread) != len(out_rows):
        raise SystemExit(
            f"temp sheet has {len(reread)} rows, expected {len(out_rows)}")
    reread_nonblank = {
        str(r["id"]): (r.get("groundedness_score") or "").strip()
        for r in reread if (r.get("groundedness_score") or "").strip()
    }
    if reread_nonblank != (
            {k: v for k, v in old_nonblank.items()} if args.preserve_scores
            else {}):
        raise SystemExit("temp sheet failed the score-preservation assert")
    os.replace(tmp, OUT_CSV)

    answered = sum(1 for r in out_rows if r["shown_to_user"] == "answer")
    blank = sum(1 for r in out_rows if r["groundedness_score"] == "")
    print(f"wrote {OUT_CSV} — {len(out_rows)} rows, "
          f"{answered} shown as answers, {blank} groundedness scores blank")
    if preserved:
        print(f"preserved {preserved} human groundedness scores "
              f"across from the previous sheet")
    print(f"rubric: {OUT_MD}")


if __name__ == "__main__":
    main()
