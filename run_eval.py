#!/usr/bin/env python3
"""
run_eval.py
===========
End-to-end evaluation of the retrieval + generation pipeline against a
golden set (default: data/golden_set_30.json).

For each question:
  1. query_store(question, n_results=5)
  2. generate_answer(question, retrieved_chunks), retried with exponential
     backoff + jitter on transient Groq errors (429 / 5xx / connection)
  3. record document-level hit, the retrieved chunk ids, sections and
     distances, the guardrail decision, latency, tokens, answer_text and a
     `shown_to_user` verdict.

Outputs (written to eval_results/):
  {prefix}.csv         - one row per question
  {prefix}_summary.md  - run manifest + per-question quick view

Failure policy (the reason this harness exists):
  * A run that could not answer a question says so. Rows that ended in a
    generation error are marked with status=generation_error, are excluded
    from every average, and --strict (the default) makes the process exit
    non-zero and print the failing ids.
  * Averages are never computed over error rows; the summary states how many
    rows were excluded.

Usage:
    python run_eval.py                          # defaults to prefix='before'
    python run_eval.py --prefix after_guardrails
    python run_eval.py --resume                 # keep completed rows, redo the rest
    python run_eval.py --no-strict              # exit 0 even with error rows

Integration
-----------
Wired to the real pipeline: query_store from src/embed_store.py and
generate_answer from src/answer.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from embed_store import query_store
from answer import generate_answer, GroqAPIError

# ---------------------------------------------------------------------------
# Paths and schema
# ---------------------------------------------------------------------------
DEFAULT_GOLDEN = ROOT / "data" / "golden_set_30.json"
DEFAULT_GOLD_CHUNKS = ROOT / "data" / "gold_chunks.json"
ALL_CHUNKS_PATH = ROOT / "data" / "processed" / "all_chunks.json"
EVAL_DIR = ROOT / "eval_results"

FIELDNAMES = [
    "id",
    "question",
    "answerable",
    "status",
    "retrieval_hit",
    "retrieved_chunk_ids",
    "retrieved_sections",
    "retrieved_distances",
    "shown_to_user",
    "latency_seconds",
    "input_tokens",
    "output_tokens",
    "retries",
    "answer_text",
    "refused",
    "refusal_reasons",
]

# The exact sentence src/answer.py instructs the model to emit when the
# context does not cover the question. A model refusal is that sentence (with
# or without polite padding around it).
MODEL_REFUSAL_MARKERS = (
    "i don't have enough information in the provided documents",
    "i do not have enough information in the provided documents",
)

# Statuses that mean the pipeline failed rather than the model declining.
PIPELINE_FAILURE_STATUSES = ("generation_error", "retrieval_error")

RETRY_BASE_SECONDS = 2.0
RETRY_CAP_SECONDS = 60.0
RETRY_ATTEMPTS = 6
# A Retry-After longer than this is clamped: the harness should wait for the
# provider, not hang the session.
RETRY_AFTER_CEILING_SECONDS = 120.0


# ---------------------------------------------------------------------------
# Retry plumbing
# ---------------------------------------------------------------------------
def _is_retryable(exc: BaseException) -> bool:
    """Transient failures worth retrying: 429s, 5xx and connection problems."""
    if isinstance(exc, GroqAPIError):
        code = exc.status_code
        if code is None:  # APIConnectionError surfaced without a status
            return True
        return code == 429 or 500 <= code <= 599
    # Anything non-Groq (socket reset, DNS, timeout inside the SDK) is assumed
    # transient; a genuine code bug will burn the retries and surface.
    return True


def _backoff_seconds(attempt: int, retry_after: float | None) -> float:
    """Sleep for this attempt: capped exponential backoff plus jitter.

    `retry_after` (from the Retry-After header) wins when it is larger than
    the computed delay, clamped to RETRY_AFTER_CEILING_SECONDS.
    """
    delay = min(RETRY_CAP_SECONDS, RETRY_BASE_SECONDS * (2 ** attempt))
    delay *= 0.5 + random.random()  # full jitter, [0.5x, 1.5x)
    if retry_after is not None:
        delay = max(delay, min(retry_after, RETRY_AFTER_CEILING_SECONDS))
    return delay


def _call_with_retry(question: str, chunks: list[dict]) -> tuple[dict, int]:
    """Call generate_answer with retries. Returns (result, attempts_used)."""
    last_exc: BaseException | None = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return generate_answer(question, chunks), attempt + 1
        except Exception as exc:  # noqa: BLE001 - classified below
            last_exc = exc
            if not _is_retryable(exc) or attempt == RETRY_ATTEMPTS - 1:
                break
            retry_after = getattr(exc, "retry_after", None)
            sleep_for = _backoff_seconds(attempt, retry_after)
            print(
                f"\n    retry {attempt + 1}/{RETRY_ATTEMPTS - 1} after "
                f"{type(exc).__name__}: {exc} "
                f"(sleeping {sleep_for:.1f}s)",
                flush=True,
            )
            time.sleep(sleep_for)
    assert last_exc is not None
    raise last_exc


# ---------------------------------------------------------------------------
# Row helpers
# ---------------------------------------------------------------------------
def _is_generation_error(row: dict) -> bool:
    return str(row.get("status", "")) == "generation_error"


def _schema_ok(fieldnames: list[str] | None) -> bool:
    return bool(fieldnames) and all(f in fieldnames for f in FIELDNAMES)


def _load_resumable(csv_path: Path) -> dict[str, dict]:
    """Return {id: row} from a previous run that we can carry forward.

    Only rows that actually completed are kept; anything else is recomputed.
    An older CSV without the current columns is ignored entirely (mixing
    schemas silently would produce an unreadable result file).
    """
    if not csv_path.exists():
        return {}
    kept: dict[str, dict] = {}
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not _schema_ok(reader.fieldnames):
            print(f"  note: {csv_path.name} has an older schema; "
                  f"recomputing every row")
            return {}
        for row in reader:
            if row.get("status") == "ok" and not _is_generation_error(row):
                kept[str(row["id"])] = row
    return kept


def _write_csv(csv_path: Path, rows: list[dict]) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in FIELDNAMES})


# ---------------------------------------------------------------------------
# Metrics (§3.3)
# ---------------------------------------------------------------------------
_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212-\u00ad"


def _norm(text: str) -> str:
    """Normalise a citation or a chunk label for comparison.

    Dashes are unified (the corpus uses em dashes, the model often emits en
    dashes), whitespace is collapsed and case is folded. Nothing else is
    changed, so a citation that only matches after this is still auditable.
    """
    out = (text or "").lower()
    for dash in _DASHES:
        out = out.replace(dash, "-")
    return re.sub(r"\s+", " ", out).strip()


def _load_metrics_context(gold_chunks_path: Path) -> tuple[dict, dict]:
    """Load the gold set and a chunk_id -> (title, section) index.

    Both come from committed artefacts (data/gold_chunks.json and
    data/processed/all_chunks.json), never from the retriever.
    """
    gold_by_id: dict[str, dict] = {}
    if gold_chunks_path.exists():
        for record in json.loads(gold_chunks_path.read_text(encoding="utf-8")):
            gold_by_id[str(record["id"])] = record
    else:
        print(f"WARNING: {gold_chunks_path} not found — recall@k, "
              f"context precision and MRR will not be computed.")
    chunk_index: dict[str, tuple[str, str]] = {}
    if ALL_CHUNKS_PATH.exists():
        for chunk in json.loads(ALL_CHUNKS_PATH.read_text(encoding="utf-8")):
            chunk_index[chunk["chunk_id"]] = (
                chunk.get("doc_title", ""), chunk.get("section_label", ""))
    return gold_by_id, chunk_index


def _retrieval_metrics(retrieved_ids: list[str], gold_ids: list[str],
                       k: int) -> dict:
    """recall@k, context precision@k and MRR for one question."""
    if not gold_ids:
        return {"gold_total": 0, "gold_in_topk": 0, "recall": None,
                "precision": None, "first_gold_rank": None, "mrr": None}
    topk = retrieved_ids[:k]
    hits = [cid for cid in topk if cid in gold_ids]
    first_rank = None
    for rank, cid in enumerate(topk, start=1):
        if cid in gold_ids:
            first_rank = rank
            break
    return {
        "gold_total": len(gold_ids),
        "gold_in_topk": len(hits),
        "recall": len(hits) / len(gold_ids),
        "precision": len(hits) / k if k else None,
        "first_gold_rank": first_rank,
        "mrr": (1.0 / first_rank) if first_rank else 0.0,
    }


def _citation_metrics(answer_text: str, retrieved_ids: list[str],
                      chunk_index: dict, k: int) -> dict:
    """Citation correctness for one answer.

    A citation is correct when its [Title, Section] matches a retrieved
    chunk (case- and dash-insensitive, whitespace collapsed). A citation
    whose section matches but whose title does not, or that matches nothing
    in the retrieved set, counts as citation_target_missing.
    """
    from answer import _extract_citations

    retrieved = [chunk_index[c] for c in retrieved_ids[:k]
                 if c in chunk_index]
    norm_pairs = {(_norm(t), _norm(s)) for t, s in retrieved}
    norm_titles = {t for t, _ in norm_pairs}
    norm_sections = {s for _, s in norm_pairs}

    total = correct = missing = 0
    for cite in _extract_citations(answer_text or ""):
        total += 1
        title = _norm(cite["doc_title"])
        section = _norm(cite["section_label"])
        if (title, section) in norm_pairs:
            correct += 1
        elif title in norm_titles and any(
                section in s or s in section for s in norm_sections):
            correct += 1
        else:
            missing += 1
    return {"citations_total": total, "citations_correct": correct,
            "citations_missing": missing}


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def compute_metrics(rows: list[dict], golden: list[dict],
                    chunk_index: dict, k: int) -> dict:
    """All §3.3 metrics, computed once over the finished rows.

    Retrieval metrics use every row that has retrieved chunks (retrieval
    happens before generation, so a generation error does not poison them).
    Answer metrics use only rows with status=ok; the exclusions are counted.
    """
    golden_by_id = {str(e["id"]): e for e in golden}
    answerable_by_id = {
        str(e["id"]): bool(e.get("answerable", True)) for e in golden}

    retrieval_rows = []
    for row in rows:
        if not row.get("retrieved_chunk_ids"):
            continue
        record = row.get("_gold_record") or {}
        gold_ids = [g["chunk_id"] for g in record.get("gold_chunks", [])]
        m = _retrieval_metrics(
            str(row["retrieved_chunk_ids"]).split(";"), gold_ids, k)
        if m["gold_total"]:
            retrieval_rows.append(m)

    ok_rows = [r for r in rows if r.get("status") == "ok"]
    excluded = len(rows) - len(ok_rows)

    citation_totals = {"citations_total": 0, "citations_correct": 0,
                       "citations_missing": 0}
    for row in ok_rows:
        if row.get("shown_to_user") != "answer":
            continue
        ids = str(row.get("retrieved_chunk_ids", "")).split(";")
        cm = _citation_metrics(row.get("answer_text", ""), ids,
                               chunk_index, k)
        for key in citation_totals:
            citation_totals[key] += cm[key]

    answerable_rows = [r for r in ok_rows
                       if answerable_by_id.get(str(r["id"]), True)]
    unanswerable_rows = [r for r in ok_rows
                         if not answerable_by_id.get(str(r["id"]), True)]

    def _count(rows_: list[dict], shown: str) -> int:
        return sum(1 for r in rows_ if r.get("shown_to_user") == shown)

    by_shown: dict[str, int] = {}
    for r in ok_rows:
        by_shown[r["shown_to_user"]] = by_shown.get(r["shown_to_user"], 0) + 1

    # Old document-level metric, kept beside the new ones so the reader can
    # see why a 100% hit rate says nothing.
    doc_hits = [r for r in rows
                if answerable_by_id.get(str(r["id"]), True)
                and r.get("retrieval_hit") == "TRUE"]
    doc_answerable = [e for e in golden
                      if answerable_by_id.get(str(e["id"]), True)]

    metrics = {
        "k": k,
        "questions": len(rows),
        "rows_excluded_from_answer_metrics": excluded,
        "gold_questions": len(retrieval_rows),
        "retrieval": {
            "recall_at_k": _mean([m["recall"] for m in retrieval_rows]),
            "context_precision_at_k": _mean(
                [m["precision"] for m in retrieval_rows]),
            "mrr": _mean([m["mrr"] for m in retrieval_rows]),
            "document_level_hit_rate": (
                len(doc_hits) / len(doc_answerable) if doc_answerable
                else None),
            "document_level_hits": len(doc_hits),
            "document_level_answerable": len(doc_answerable),
        },
        "answers": {
            "grounded_answer_rate": (
                _count(answerable_rows, "answer") / len(answerable_rows)
                if answerable_rows else None),
            "answerable_questions": len(answerable_rows),
            "refusal_correctness": (
                (len(unanswerable_rows)
                 - _count(unanswerable_rows, "answer"))
                / len(unanswerable_rows) if unanswerable_rows else None),
            "unanswerable_questions": len(unanswerable_rows),
            "hallucination_rate": (
                _count(unanswerable_rows, "answer") / len(unanswerable_rows)
                if unanswerable_rows else None),
            "citation_correctness": (
                citation_totals["citations_correct"]
                / citation_totals["citations_total"]
                if citation_totals["citations_total"] else None),
            **citation_totals,
        },
        "shown_to_user": by_shown,
    }
    return metrics


def _fmt(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------
def evaluate(
    golden_path: Path,
    prefix: str,
    strict: bool = True,
    resume: bool = False,
    k: int = 5,
) -> int:
    if not golden_path.exists():
        sys.exit(f"ERROR: golden set not found: {golden_path}")

    with golden_path.open("r", encoding="utf-8") as f:
        golden = json.load(f)

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = EVAL_DIR / f"{prefix}.csv"
    md_path = EVAL_DIR / f"{prefix}_summary.md"

    resumable = _load_resumable(csv_path) if resume else {}
    if resume:
        print(f"Resume: {len(resumable)} completed row(s) carried forward "
              f"from {csv_path.name}")

    total = len(golden)
    rows_by_id: dict[str, dict] = {}
    retry_total = 0
    resumed_count = 0

    for idx, entry in enumerate(golden, start=1):
        qid = str(entry["id"])
        question = entry["question"]
        expected_doc = entry.get("expected_doc_id")
        answerable = bool(entry.get("answerable", True))

        previous = resumable.get(qid)
        if previous is not None:
            rows_by_id[qid] = previous
            resumed_count += 1
            print(f"[{idx}/{total}] Q{qid}: resumed (already completed)")
            continue

        print(f"[{idx}/{total}] Processing Q{qid}...", end=" ", flush=True)

        # ---- 1. Retrieve -------------------------------------------------
        status = "ok"
        chunks: list[dict] = []
        try:
            chunks = query_store(question, n_results=k)
        except Exception as e:  # noqa: BLE001
            status = "retrieval_error"
            print(f"RETRIEVAL ERROR: {e}", end=" ", flush=True)

        returned_ids = [c.get("chunk_id", "") for c in chunks]
        returned_docs = [c.get("doc_id", "") for c in chunks]
        retrieved_sections = ";".join(
            f"{c.get('doc_id', '')}:{c.get('section_label', '')}" for c in chunks
        )
        retrieved_distances = ";".join(
            f"{float(c.get('distance', 0.0)):.4f}" for c in chunks
        )

        if answerable:
            retrieval_hit = (expected_doc in returned_docs) if expected_doc and chunks else False
            retrieval_hit_val = "TRUE" if retrieval_hit else "FALSE"
        else:
            retrieval_hit_val = "N/A"

        # ---- 2. Generate -------------------------------------------------
        answer_text = ""
        refused = ""
        refusal_reasons = ""
        latency = 0.0
        in_tok = 0
        out_tok = 0
        attempts = 0

        if not chunks and status == "ok":
            status = "no_chunks"
            answer_text = "[NO RETRIEVED CHUNKS; generation skipped]"
        elif chunks:
            try:
                result, attempts = _call_with_retry(question, chunks)
                retry_total += max(0, attempts - 1)
                answer_text = result.get(
                    "model_answer_text", result.get("answer_text", ""))
                latency = float(result.get("latency_seconds", 0.0))
                in_tok = int(result.get("input_tokens", 0))
                out_tok = int(result.get("output_tokens", 0))
                refused = "FALSE" if result.get("guardrails_allowed") else "TRUE"
                refusal_reasons = "; ".join(
                    result.get("guardrails_refusal_reasons", []))
            except Exception as e:  # noqa: BLE001
                status = "generation_error"
                answer_text = f"[GENERATION ERROR: {type(e).__name__}: {e}]"
                print(f"GENERATION ERROR: {e}", end=" ", flush=True)

        # ---- 3. What actually reached the user ---------------------------
        if status == "generation_error":
            shown_to_user = "none"
        elif status == "no_chunks":
            shown_to_user = "none"
        elif refused == "TRUE":
            shown_to_user = "guardrail_refusal"
        elif _looks_like_model_refusal(answer_text):
            shown_to_user = "model_refusal"
        else:
            shown_to_user = "answer"

        rows_by_id[qid] = {
            "id": qid,
            "question": question,
            "answerable": answerable,
            "status": status,
            "retrieval_hit": retrieval_hit_val,
            "retrieved_chunk_ids": ";".join(returned_ids),
            "retrieved_sections": retrieved_sections,
            "retrieved_distances": retrieved_distances,
            "shown_to_user": shown_to_user,
            "latency_seconds": f"{latency:.3f}",
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "retries": max(0, attempts - 1),
            "answer_text": answer_text,
            "refused": refused,
            "refusal_reasons": refusal_reasons,
        }

        # Crash-safe: keep the CSV current after every question.
        _write_csv(csv_path, [rows_by_id[str(e["id"])] for e in golden
                              if str(e["id"]) in rows_by_id])
        print("done")

    rows = [rows_by_id[str(e["id"])] for e in golden if str(e["id"]) in rows_by_id]

    # --- Run manifest (error rows excluded from every average) ------------
    failed_ids = [r["id"] for r in rows if r["status"] in PIPELINE_FAILURE_STATUSES]
    error_ids = [r["id"] for r in rows if r["status"] == "generation_error"]
    ok_rows = [r for r in rows if r["status"] == "ok"]
    excluded = len(rows) - len(ok_rows)

    answerable_total = sum(1 for r in rows if r["answerable"] in (True, "True", "TRUE"))
    retrieval_hits = sum(1 for r in ok_rows
                         if r["answerable"] in (True, "True", "TRUE")
                         and r["retrieval_hit"] == "TRUE")
    retrieval_acc = (100.0 * retrieval_hits / answerable_total) if answerable_total else 0.0

    latencies = [float(r["latency_seconds"]) for r in ok_rows]
    total_toks = [int(r["input_tokens"]) + int(r["output_tokens"]) for r in ok_rows]
    avg_latency = statistics.mean(latencies) if latencies else 0.0
    med_latency = statistics.median(latencies) if latencies else 0.0
    avg_toks = statistics.mean(total_toks) if total_toks else 0.0

    shown_counts: dict[str, int] = {}
    for r in ok_rows:
        shown_counts[r["shown_to_user"]] = shown_counts.get(r["shown_to_user"], 0) + 1

    # --- §3.3 metrics (need the gold set and a chunk_id -> label index) ---
    gold_by_id, chunk_index = _load_metrics_context(DEFAULT_GOLD_CHUNKS)
    for r in rows:
        r["_gold_record"] = gold_by_id.get(str(r["id"]))
    metrics = compute_metrics(rows, golden, chunk_index, k)
    metrics_path = EVAL_DIR / f"{prefix}_metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")

    retrieval_m = metrics["retrieval"]
    answers_m = metrics["answers"]

    md = []
    md.append(f"# Evaluation Summary — '{prefix}' run\n")
    md.append(f"- Golden set: `{golden_path.name}` ({total} questions; "
              f"{answerable_total} answerable, {total - answerable_total} unanswerable)")
    md.append(f"- Retrieval configuration: top-{k} chunks "
              f"(chunk size 700 chars, overlap 100)")
    md.append(f"- Rows completed in this invocation: "
              f"{len(rows) - resumed_count} "
              f"({resumed_count} carried forward by --resume)")
    md.append(f"- Retries performed: {retry_total}")
    md.append(f"- **Rows excluded from every average: {excluded}** "
              f"(status != ok) — "
              f"{len(error_ids)} generation error(s), "
              f"{sum(1 for r in rows if r['status'] == 'retrieval_error')} retrieval error(s), "
              f"{sum(1 for r in rows if r['status'] == 'no_chunks')} with no retrieved chunks")
    md.append(f"- **Average latency over {len(ok_rows)} ok rows:** "
              f"{avg_latency:.2f} s (median {med_latency:.2f} s)")
    md.append(f"- **Average tokens (in + out) over ok rows:** {avg_toks:.0f}")
    md.append(f"- **Retrieval accuracy (top-{k} document hit, answerable questions):** "
              f"{retrieval_hits}/{answerable_total} = {retrieval_acc:.1f}%")
    md.append(f"- What reached the user: " +
              ", ".join(f"{v}× {k2}" for k2, v in sorted(shown_counts.items()))
              if shown_counts else "- What reached the user: (no ok rows)")
    md.append("")
    md.append("## Retrieval quality\n")
    md.append("Computed over the questions with gold chunks in "
              f"`data/gold_chunks.json` ({metrics['gold_questions']} of "
              f"{metrics['questions']}; the rest are out of corpus or "
              "unanswerable by design).")
    md.append("")
    md.append("| metric | value | definition |")
    md.append("|--------|-------|------------|")
    md.append(f"| recall@{k} | **{_fmt(retrieval_m['recall_at_k'])}** | "
              f"mean over questions of (gold chunks in top-{k}) / (gold "
              f"chunks for that question) |")
    md.append(f"| context_precision@{k} | **{_fmt(retrieval_m['context_precision_at_k'])}** | "
              f"mean over questions of (retrieved chunks that are gold) / {k} |")
    md.append(f"| MRR | **{_fmt(retrieval_m['mrr'])}** | mean over questions "
              f"of 1 / (rank of first gold chunk) |")
    md.append(f"| document-level hit rate (old metric) | "
              f"**{retrieval_m['document_level_hits']}/"
              f"{retrieval_m['document_level_answerable']}** | "
              f"answerable questions whose expected document appears "
              f"anywhere in the top-{k} — saturated, kept for comparison |")
    md.append("")
    md.append("## Answer quality\n")
    md.append("| metric | value | over |")
    md.append("|--------|-------|------|")
    md.append(f"| grounded_answer_rate | "
              f"**{_fmt(answers_m['grounded_answer_rate'])}** | "
              f"{answers_m['answerable_questions']} answerable questions |")
    md.append(f"| refusal_correctness | "
              f"**{_fmt(answers_m['refusal_correctness'])}** | "
              f"{answers_m['unanswerable_questions']} unanswerable questions |")
    md.append(f"| hallucination_rate | "
              f"**{_fmt(answers_m['hallucination_rate'])}** | "
              f"{answers_m['unanswerable_questions']} unanswerable questions |")
    md.append(f"| citation_correctness | "
              f"**{_fmt(answers_m['citation_correctness'])}** | "
              f"{answers_m['citations_total']} inline citations in answers "
              f"shown to the user |")
    md.append(f"| citation_target_missing | "
              f"**{answers_m['citations_missing']}** | citations pointing at "
              f"something not in the retrieved context |")
    md.append("")
    md.append("What reached the user, by verdict: " +
              (", ".join(f"{v}× {k2}" for k2, v in sorted(shown_counts.items()))
               if shown_counts else "(no ok rows)"))
    md.append("")
    md.append(f"Machine-readable copy of every number above: "
              f"`eval_results/{metrics_path.name}`.")
    md.append("")
    if error_ids:
        md.append(f"**This run is not clean.** Question ids with generation "
                  f"errors: {', '.join(error_ids)}. "
                  f"Re-run with --resume --prefix {prefix} after the API "
                  f"recovers; do not quote the numbers above.")
        md.append("")
    md.append("## Per-question quick view\n")
    md.append("| id | status | answerable | retrieval_hit | shown_to_user | "
              "latency_s | retries | answer preview |")
    md.append("|----|--------|------------|---------------|---------------|"
              "-----------|---------|----------------|")
    for r in rows:
        preview = str(r["answer_text"]).replace("\n", " ")[:90]
        preview = preview.replace("|", "\\|")
        md.append(
            f"| {r['id']} | {r['status']} | {r['answerable']} | "
            f"{r['retrieval_hit']} | {r['shown_to_user']} | "
            f"{float(r['latency_seconds']):.2f} | {r['retries']} | "
            f"{preview}... |")

    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    # --- Console summary --------------------------------------------------
    print()
    print("=" * 64)
    print(f"Results written to:")
    print(f"  CSV:     {csv_path}")
    print(f"  Summary: {md_path}")
    print(f"  Metrics: {metrics_path}")
    print(f"Questions:     {len(rows)} ({len(rows) - resumed_count} run, "
          f"{resumed_count} resumed)")
    print(f"Retries:       {retry_total}")
    print(f"Excluded rows: {excluded} (never averaged)")
    print(f"Retrieval hit: {retrieval_hits}/{answerable_total} = {retrieval_acc:.1f}% "
          f"(old document-level metric)")
    print(f"recall@{k}:     {_fmt(retrieval_m['recall_at_k'])}"
          f"   context_precision@{k}: {_fmt(retrieval_m['context_precision_at_k'])}"
          f"   MRR: {_fmt(retrieval_m['mrr'])}"
          f"   (over {metrics['gold_questions']} questions with gold chunks)")
    print(f"grounded_answer_rate: {_fmt(answers_m['grounded_answer_rate'])}"
          f"   refusal_correctness: {_fmt(answers_m['refusal_correctness'])}"
          f"   hallucination_rate: {_fmt(answers_m['hallucination_rate'])}")
    print(f"citation_correctness: {_fmt(answers_m['citation_correctness'])}"
          f"   citation_target_missing: {answers_m['citations_missing']}")
    print(f"Latency:       mean {avg_latency:.2f}s  median {med_latency:.2f}s "
          f"(over {len(ok_rows)} ok rows)")
    print(f"Tokens (mean): {avg_toks:.0f}")
    if shown_counts:
        print("Shown to user: " +
              ", ".join(f"{v}× {k2}" for k2, v in sorted(shown_counts.items())))
    print("=" * 64)

    if failed_ids:
        print(f"PIPELINE FAILURES ({len(failed_ids)}): "
              f"{', '.join('Q' + str(i) for i in failed_ids)}")
        if strict:
            print("STRICT: failing the run because at least one question did "
                  "not produce an answer. Re-run with --resume --prefix "
                  f"{prefix}.")
            return 1
        print("WARNING: --no-strict set, exiting 0 despite failures.")
    print("RUN OK: every question produced an answer or a deliberate refusal.")
    return 0


def _looks_like_model_refusal(answer_text: str) -> bool:
    """True when the model itself declined instead of the guardrails."""
    text = (answer_text or "").lower()
    return any(marker in text for marker in MODEL_REFUSAL_MARKERS)


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
    parser.add_argument(
        "--k", type=int, default=5,
        help="Number of chunks retrieved per question (default 5).",
    )
    parser.add_argument(
        "--strict", dest="strict", action="store_true", default=True,
        help="Exit non-zero if any row ends in a generation error (default).",
    )
    parser.add_argument(
        "--no-strict", dest="strict", action="store_false",
        help="Exit 0 even when rows failed; the errors stay in the CSV.",
    )
    parser.add_argument(
        "--resume", dest="resume", action="store_true", default=False,
        help="Carry forward rows that already completed in the output CSV.",
    )
    args = parser.parse_args()
    code = evaluate(Path(args.golden), args.prefix, strict=args.strict,
                    resume=args.resume, k=args.k)
    sys.exit(code)


if __name__ == "__main__":
    main()
