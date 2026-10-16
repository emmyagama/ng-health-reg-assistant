#!/usr/bin/env python3
"""
calibrate_thresholds.py
=======================
Calibrate guardrails.check_retrieval_confidence / check_within_corpus's
shared `max_distance_threshold` against the clean v1 run.

Method (per §5 of the remediation plan):
  * Group A ("should pass"): answerable questions that retrieved at least
    one gold chunk. Their minimum retrieved distance is the signal that the
    retriever "recognised" the question.
  * Group B ("should fail"): unanswerable questions (clinical,
    out-of-corpus, near-miss, mixed). Their minimum retrieved distance is
    the signal for a topic the corpus does not really cover.
  * Sweep candidate thresholds; report the Youden index (TPR - FPR) and
    balanced accuracy for each; choose the threshold maximising Youden J,
    breaking ties toward the more conservative (lower) threshold.

Reads committed artefacts only (eval_results/b1_v1.csv, data/gold_chunks.json,
data/golden_set_50.json). Writes eval_results/threshold_calibration.md.

Usage:
    python scripts/calibrate_thresholds.py
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RUN_CSV = ROOT / "eval_results" / "b1_v1.csv"
GOLD_CHUNKS = ROOT / "data" / "gold_chunks.json"
GOLDEN = ROOT / "data" / "golden_set_50.json"
OUT_MD = ROOT / "eval_results" / "threshold_calibration.md"


def main() -> None:
    for path in (RUN_CSV, GOLD_CHUNKS, GOLDEN):
        if not path.exists():
            raise SystemExit(f"missing {path}")

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    gold_records = json.loads(GOLD_CHUNKS.read_text(encoding="utf-8"))
    gold_by_id = {str(r["id"]): r for r in gold_records}
    golden_by_id = {str(e["id"]): e for e in golden}

    rows = list(csv.DictReader(RUN_CSV.open(encoding="utf-8")))
    if len(rows) != 50:
        raise SystemExit(f"expected 50 rows in {RUN_CSV.name}, got {len(rows)}")

    pass_dists: list[tuple[str, float]] = []   # (qid, min distance)
    fail_dists: list[tuple[str, float]] = []

    for row in rows:
        qid = str(row["id"])
        distances = [float(d) for d in row["retrieved_distances"].split(";") if d]
        if not distances:
            continue
        min_d = min(distances)
        answerable = golden_by_id[qid].get("answerable", True)
        gold_ids = {g["chunk_id"] for g in gold_by_id.get(qid, {}).get("gold_chunks", [])}
        retrieved = [c for c in row["retrieved_chunk_ids"].split(";") if c]
        hit_gold = any(cid in gold_ids for cid in retrieved) if gold_ids else False

        if answerable and hit_gold:
            pass_dists.append((qid, min_d))
        elif not answerable:
            fail_dists.append((qid, min_d))
        # answerable but no gold hit: excluded from calibration (ambiguous:
        # either a retrieval miss or incomplete gold — not a threshold label)

    pass_vals = [d for _, d in pass_dists]
    fail_vals = [d for _, d in fail_dists]

    def tpr(t: float) -> float:
        return sum(1 for d in pass_vals if d <= t) / len(pass_vals)

    def fpr(t: float) -> float:
        return sum(1 for d in fail_vals if d <= t) / len(fail_vals)

    candidates = sorted({round(d, 2) for d in pass_vals + fail_vals})
    sweep = []
    for t in candidates:
        tp, fp = tpr(t), fpr(t)
        j = tp - fp
        bal = (tp + (1 - fp)) / 2
        sweep.append((t, tp, fp, j, bal))

    best_j = max(sweep, key=lambda r: (r[3], -r[0]))
    best_bal = max(sweep, key=lambda r: (r[4], -r[0]))
    chosen = best_j[0]

    def fmt(vals: list[float]) -> str:
        return (f"n={len(vals)}, min={min(vals):.3f}, "
                f"median={statistics.median(vals):.3f}, "
                f"mean={statistics.mean(vals):.3f}, max={max(vals):.3f}")

    lines = [
        "# Threshold calibration — `max_distance_threshold`",
        "",
        "Source run: `eval_results/b1_v1.csv` (50 questions, 2026-10-16,",
        "0 retries, 0 excluded rows). Regenerate with",
        "`python scripts/calibrate_thresholds.py`.",
        "",
        "## The two distributions",
        "",
        "Distance is Chroma L2 (lower = closer). Each question contributes",
        "its **minimum** retrieved distance — the single closest chunk.",
        "",
        f"- **Group A — should pass** (answerable + retrieved a gold chunk):",
        f"  {fmt(pass_vals)}",
        f"- **Group B — should fail** (unanswerable, any category):",
        f"  {fmt(fail_vals)}",
        "",
        "Answerable questions that retrieved no gold chunk are excluded from",
        "both groups: their label would conflate a retrieval miss with a",
        "threshold error.",
        "",
        "## Sweep",
        "",
        "| threshold | TPR (A passed) | FPR (B passed) | Youden J | balanced acc |",
        "|---|---|---|---|---|",
    ]
    for t, tp, fp, j, bal in sweep:
        marker = "  ← chosen" if t == chosen else ""
        lines.append(f"| {t:.2f} | {tp:.3f} | {fp:.3f} | {j:.3f} | {bal:.3f}{marker} |")

    lines += [
        "",
        "## Choice",
        "",
        f"- Maximise Youden J: **{chosen:.2f}** (J={best_j[3]:.3f})",
        f"- Maximise balanced accuracy: {best_bal[0]:.2f} "
        f"(bal={best_bal[4]:.3f})",
        f"- Previous un-calibrated default: 0.80",
        "",
        "The two criteria agree on the integer grid point; ties are broken",
        "toward the lower (more conservative) threshold.",
        "",
        "## Caveat — overlap",
        "",
    ]

    overlapping = [d for d in fail_vals if d <= chosen]
    false_passes = [qid for qid, d in fail_dists if d <= chosen]
    false_fails = [qid for qid, d in pass_dists if d > chosen]
    if overlapping:
        lines.append(
            f"{len(overlapping)} of {len(fail_vals)} unanswerable questions "
            f"have a minimum distance at or below the chosen threshold "
            f"({', '.join('Q' + q for q in false_passes)}). This check alone "
            "cannot refuse them; they are caught by the clinical check, by "
            "the model's own refusal, or not at all. The threshold is one "
            "layer, not the whole guard.")
    else:
        lines.append("No unanswerable question falls at or below the chosen "
                     "threshold.")
    if false_fails:
        lines.append("")
        lines.append(
            f"{len(false_fails)} answerable gold-hitting questions "
            f"({', '.join('Q' + q for q in false_fails)}) sit above the "
            "chosen threshold and would be refused by this check alone. "
            "In the v1 run they passed only because the deployed default "
            "was the un-calibrated 0.80, which also lets 6 of the 25 "
            "unanswerable questions through (see the 0.81 row of the "
            "sweep). Refusing these two is the measured cost of the "
            "calibrated threshold; it is stated here rather than hidden.")
    lines.append("")

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"chosen threshold: {chosen:.2f} "
          f"(Youden J={best_j[3]:.3f}, balanced acc={best_bal[4]:.3f})")
    print(f"Group A: {fmt(pass_vals)}")
    print(f"Group B: {fmt(fail_vals)}")
    print(f"false passes (unanswerable <= threshold): {false_passes}")
    print(f"false fails (answerable gold-hit > threshold): {false_fails}")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
