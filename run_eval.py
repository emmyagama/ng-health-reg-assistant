#!/usr/bin/env python3
"""
run_eval.py
===========
End-to-end evaluation of the retrieval + generation pipeline against a
golden set (default: data/golden_set_30.json).

For each question:
  1. query_store(question, n_results=5)
  2. generate_answer(question, retrieved_chunks)
  3. record retrieval_hit, retrieved_sections, latency, tokens, answer_text

Outputs (written to eval_results/):
  {prefix}.csv         - one row per question
  {prefix}_summary.md  - retrieval accuracy, avg latency, avg tokens,
                         manual-review note

Usage:
    python run_eval.py                          # defaults to prefix='before'
    python run_eval.py --prefix before_guardrails
    python run_eval.py --prefix after_guardrails  # second pass after improvements

Integration
-----------
Wired to the real pipeline: query_store from src/embed_store.py and
generate_answer from src/answer.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from embed_store import query_store
from answer import generate_answer
from guardrails import apply_guardrails


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DEFAULT_GOLDEN = ROOT / "data" / "golden_set_30.json"
EVAL_DIR = ROOT / "eval_results"


def evaluate(golden_path: Path, prefix: str) -> None:
    if not golden_path.exists():
        sys.exit(f"ERROR: golden set not found: {golden_path}")

    with golden_path.open("r", encoding="utf-8") as f:
        golden = json.load(f)

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = EVAL_DIR / f"{prefix}.csv"
    md_path = EVAL_DIR / f"{prefix}_summary.md"

    rows = []
    total = len(golden)
    answerable_total = 0
    retrieval_hits = 0
    latencies: list[float] = []
    total_toks: list[int] = []

    for idx, entry in enumerate(golden, start=1):
        qid = entry["id"]
        question = entry["question"]
        expected_doc = entry.get("expected_doc_id")
        answerable = bool(entry.get("answerable", True))

        print(f"[{idx}/{total}] Processing Q{qid}...", end=" ", flush=True)

        # 1. Retrieve
        try:
            chunks = query_store(question, n_results=5)
        except Exception as e:
            print(f"RETRIEVAL ERROR: {e}")
            chunks = []

        returned_ids = [c["doc_id"] for c in chunks]
        retrieved_sections = ";".join(
            f"{c['doc_id']}:{c['section_label']}" for c in chunks
        )

        if answerable:
            answerable_total += 1
            retrieval_hit = (expected_doc in returned_ids) if expected_doc and chunks else False
            if retrieval_hit:
                retrieval_hits += 1
            retrieval_hit_val = "TRUE" if retrieval_hit else "FALSE"
        else:
            retrieval_hit_val = "N/A"

        # 2. Generate answer
        answer_text = ""
        refused = ""
        refusal_reasons = ""
        latency = 0.0
        in_tok = 0
        out_tok = 0
        if chunks:
            try:
                result = generate_answer(question, chunks)
                # Record the raw model answer; the guardrail decision goes
                # in the dedicated refused / refusal_reasons columns.
                answer_text = result.get(
                    "model_answer_text", result.get("answer_text", ""))
                latency = float(result.get("latency_seconds", 0.0))
                in_tok = int(result.get("input_tokens", 0))
                out_tok = int(result.get("output_tokens", 0))
                decision = apply_guardrails(question, chunks, answer_text)
                refused = "FALSE" if decision["allowed"] else "TRUE"
                refusal_reasons = "; ".join(decision["refusal_reasons"])
            except Exception as e:
                answer_text = f"[GENERATION ERROR: {type(e).__name__}: {e}]"
        else:
            answer_text = "[NO RETRIEVED CHUNKS; generation skipped]"

        latencies.append(latency)
        total_toks.append(in_tok + out_tok)

        rows.append({
            "id": qid,
            "question": question,
            "answerable": answerable,
            "retrieval_hit": retrieval_hit_val,
            "retrieved_sections": retrieved_sections,
            "latency_seconds": latency,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "answer_text": answer_text,
            "refused": refused,
            "refusal_reasons": refusal_reasons,
        })

        print("done")

    # --- Write CSV ---
    fieldnames = ["id", "question", "answerable", "retrieval_hit",
                  "retrieved_sections", "latency_seconds", "input_tokens",
                  "output_tokens", "answer_text", "refused",
                  "refusal_reasons"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    # --- Compute summary stats ---
    retrieval_acc = (100.0 * retrieval_hits / answerable_total) if answerable_total else 0.0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    avg_toks = sum(total_toks) / len(total_toks) if total_toks else 0.0

    md = []
    md.append(f"# Evaluation Summary — '{prefix}' run\n")
    md.append(f"- Golden set: `{golden_path.name}` ({total} questions; "
              f"{answerable_total} answerable, {total - answerable_total} unanswerable)")
    md.append(f"- **Retrieval accuracy (top-5 hit on answerable questions):** "
              f"**{retrieval_hits}/{answerable_total} = {retrieval_acc:.1f}%**")
    md.append(f"- **Average end-to-end latency:** {avg_latency:.2f} seconds")
    md.append(f"- **Average total tokens (in + out):** {avg_toks:.0f}")
    md.append("")
    md.append("Groundedness and hallucination rate require manual review — see "
              f"the `answer_text` and `retrieved_sections` columns in "
              f"`{csv_path.name}`.")
    md.append("")
    md.append("## Per-question quick view\n")
    md.append("| id | answerable | retrieval_hit | latency_s | answer preview |")
    md.append("|----|------------|---------------|-----------|----------------|")
    for r in rows:
        preview = r["answer_text"].replace("\n", " ")[:90]
        preview = preview.replace("|", "\\|")
        md.append(f"| {r['id']} | {r['answerable']} | {r['retrieval_hit']} | "
                  f"{r['latency_seconds']:.2f} | {preview}... |")

    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    # --- Console summary ---
    print()
    print("="*60)
    print(f"Results written to:")
    print(f"  CSV:     {csv_path}")
    print(f"  Summary: {md_path}")
    print(f"Retrieval accuracy: {retrieval_hits}/{answerable_total} = {retrieval_acc:.1f}%")
    print(f"Avg latency:        {avg_latency:.2f}s")
    print(f"Avg total tokens:   {avg_toks:.0f}")
    print("="*60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RAG evaluation pipeline.")
    parser.add_argument(
        "--prefix", default="before",
        help="Output filename prefix (default 'before'; re-run with 'after' after improvements).",
    )
    parser.add_argument(
        "--golden", default=str(DEFAULT_GOLDEN),
        help="Path to golden-set JSON.",
    )
    args = parser.parse_args()
    evaluate(Path(args.golden), args.prefix)


if __name__ == "__main__":
    main()
