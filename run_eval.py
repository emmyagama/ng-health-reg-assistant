#!/usr/bin/env python3
"""
run_eval.py
===========
End-to-end evaluation of the retrieval + generation pipeline against a
golden set (default: data/golden_set_50.json; pass --golden for the
original 30-question set).

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
    python run_eval.py --prefix b1_v1 --recompute-only
        # rebuild _metrics.json and _summary.md from the committed CSV with
        # ZERO network calls (used after gold-label or parser fixes; the run
        # itself is frozen evidence and is never re-executed)

Integration
-----------
Wired to the real pipeline: query_store from src/embed_store.py and
generate_answer from src/answer.py. Both are imported lazily inside the
functions that call them so this module — and especially
--recompute-only — can be imported and run with no embed_store build, no
chroma DB and no groq package present.
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

# NOTE: query_store (embed_store) and generate_answer/GroqAPIError (answer)
# are imported lazily inside the functions that need them. --recompute-only
# must run with no embed_store build and no groq package installed, and the
# metric functions below must be importable in that state.

# ---------------------------------------------------------------------------
# Paths and schema
# ---------------------------------------------------------------------------
DEFAULT_GOLDEN = ROOT / "data" / "golden_set_50.json"
DEFAULT_GOLD_CHUNKS = ROOT / "data" / "gold_chunks.json"
ALL_CHUNKS_PATH = ROOT / "data" / "processed" / "all_chunks.json"
EVAL_DIR = ROOT / "eval_results"

# The hand-scored groundedness sheet was written against the v1 50-question
# run's answer texts specifically. A score is a judgement of one answer, not
# of a question id, so any other run (the original-30 CSV, for instance,
# whose answer texts differ from the v1 run on most shared questions) must
# get the unscored placeholder rather than someone else's scores.
SCORED_RUN_PREFIX = "b1_v1"
GROUNDEDNESS_SHEET = EVAL_DIR / "v1_scoring_sheet.csv"

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
#
# The classifier below depends on this exact string: a raw output counts as
# a model refusal only when it contains one of these markers. That dependency
# is now enforced by tests/test_classifier.py — if the system prompt's
# mandated sentence ever changes, this tuple and the test must change with
# it, or the headline hallucination rate silently changes meaning.
MODEL_REFUSAL_MARKERS = (
    "i don't have enough information in the provided documents",
    "i do not have enough information in the provided documents",
)

# Fourth bucket: a non-empty answer that neither matches the mandated
# refusal sentence nor reads as a substantive answer (an off-script refusal
# such as "I'm sorry, I can't provide medical advice."). An off-script
# refusal must never be counted as a fabrication, so --strict treats any
# row landing here as a run failure rather than absorbing it into the
# hallucination rate.
UNCLASSIFIED_REFUSAL = "unclassified_refusal_candidate"

# Refusal *language* for the fourth bucket. Deliberately broad on the
# apology/inability phrasing; the discriminator against a substantive
# answer is citation presence (see _looks_like_offscript_refusal).
_OFFSCRIPT_REFUSAL_RE = re.compile(
    r"(i'?m sorry|so?rry|apolog)"
    r"|"
    r"(can'?t|cannot|can not|unable to|not able to|won'?t|will not)"
    r"[^\n]{0,60}"
    r"(provide|answer|assist|help|give|offer|supply|share|comment|comply|confirm)",
    re.IGNORECASE,
)

# Presence of a [Title, Section]-shaped citation — the same shape
# check_citation_required in guardrails.py uses (that check only tests
# presence, so it is unaffected by the title/section split fix; the two
# regexes are intentionally independent).
_CITATION_PRESENT_RE = re.compile(r"[\[【][^\[\]【】\n]{3,400}?[,，][^\[\]【】\n]{3,400}?[\]】]")

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
    from answer import GroqAPIError  # lazy: keeps this module import-light
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
    from answer import generate_answer  # lazy: no groq needed to import us
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


# Layer 2 of the citation fix: strip a leading "Section"/"Section 36" style
# prefix the model sometimes prepends to a section label ("Section PART
# I—ESTABLISHMENT..." -> "PART I—ESTABLISHMENT...").
_SECTION_PREFIX_RE = re.compile(r"^\s*sections?\s*[:：]?\s*", re.IGNORECASE)


def _strip_section_prefix(label: str) -> str:
    """Remove a leading Section/Sections prefix from a section label."""
    return _SECTION_PREFIX_RE.sub("", (label or "")).strip()


# Layer 3 of the citation fix: a whitespace-insensitive comparison key. The
# OCR sidecar contains intra-word splits ("NA TIONAL", "ofSanctions") that
# the model normalises away; removing all whitespace bridges both directions
# without touching the auditable _norm form. Built ON TOP of _norm so the
# dash/case unification applies here too — a citation's non-breaking hyphen
# (U+2011) must compare equal to the chunk's ASCII hyphen, exactly as it
# does under every other rule in the chain.
def _nows(text: str) -> str:
    """Whitespace-insensitive key: _norm applied, then every space removed."""
    return re.sub(r"\s+", "", _norm(text))


def _load_metrics_context(gold_chunks_path: Path) -> tuple[dict, dict]:
    """Load the gold set and (if the corpus is built) a chunk label index.

    The gold set always comes from the committed data/gold_chunks.json.
    The chunk_id -> (title, section) index is built from
    data/processed/all_chunks.json only when that file exists — it is a
    build artefact, not committed. Callers that must work corpus-free
    (render_results.py, --recompute-only) use _build_chunk_index instead,
    which derives the same index from the committed CSV and gold records.
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


def _build_chunk_index(rows: list[dict], gold_by_id: dict) -> dict:
    """chunk_id -> (doc_title, section_label), corpus-free.

    Built from two committed sources only:
      * the run CSV's retrieved_chunk_ids zipped positionally with
        retrieved_sections (which stores "doc_id:section_label", written
        that way by evaluate()), with titles from data/sources.json;
      * data/gold_chunks.json entries (chunk_id, doc_id, section_label),
        for gold chunks that were never retrieved.

    Verified equivalent to the all_chunks.json-derived index on the frozen
    run: 0 title mismatches, 0 section mismatches across all 1,218 chunks.
    """
    titles: dict[str, str] = {}
    sources = ROOT / "data" / "sources.json"
    if sources.exists():
        for entry in json.loads(sources.read_text(encoding="utf-8")):
            titles[entry["id"]] = entry.get("title", "")
    index: dict[str, tuple[str, str]] = {}
    for row in rows:
        ids = [c for c in str(row.get("retrieved_chunk_ids", "")).split(";") if c]
        secs = str(row.get("retrieved_sections", "")).split(";")
        for cid, sec in zip(ids, secs):
            doc_id, _, label = sec.partition(":")
            index[cid] = (titles.get(doc_id, doc_id), label)
    for record in gold_by_id.values():
        for g in record.get("gold_chunks", []):
            index.setdefault(
                g["chunk_id"],
                (titles.get(g["doc_id"], g["doc_id"]),
                 g.get("section_label", "")))
    return index


def _known_titles() -> list[str]:
    """Document titles from the committed data/sources.json, longest first.

    Loaded from the artefact, never from memory and never from the
    retriever, so the citation parser's title resolution is auditable.
    """
    sources = ROOT / "data" / "sources.json"
    if not sources.exists():
        return []
    titles = [e["title"] for e in json.loads(sources.read_text(encoding="utf-8"))
              if e.get("title")]
    return sorted(set(titles), key=len, reverse=True)


def _citation_metrics(answer_text: str, retrieved_ids: list[str],
                      chunk_index: dict, k: int) -> dict:
    """Citation correctness for one answer — three auditable match rules.

    A citation is correct when its [Title, Section] matches a retrieved
    chunk under ONE of these rules, checked in order:

      1. exact pair      — (_norm(title), _norm(section)) equals a
                           retrieved (title, section) pair;
      2. nows pair       — same after the whitespace-insensitive key
                           (_nows) and the Section-prefix strip, which
                           bridges OCR intra-word splits like "NA TIONAL";
      3. containment     — title matches and the section is a substring of
                           (or contains) a retrieved section for that
                           title, under _norm or under _nows.

    Titles are resolved against data/sources.json before splitting, so a
    document title that itself contains a comma (e.g. "National Health
    Insurance Authority Act, 2022") is no longer torn at its first comma
    — the bug that made citation_correctness read 0.648 when the true
    figure was higher. citation_target_missing counts citations matching
    under none of the three rules.
    """
    from answer import _extract_citations

    retrieved = [chunk_index[c] for c in retrieved_ids[:k]
                 if c in chunk_index]
    norm_pairs = {(_norm(t), _norm(s)) for t, s in retrieved}
    nows_pairs = {(_norm(t), _nows(_strip_section_prefix(s)))
                  for t, s in retrieved}
    by_title: dict[str, list[str]] = {}
    for t, s in retrieved:
        by_title.setdefault(_norm(t), []).append(s)

    total = correct = missing = 0
    for cite in _extract_citations(answer_text or "", _known_titles()):
        total += 1
        title = _norm(cite["doc_title"])
        section_raw = _strip_section_prefix(cite["section_label"])
        section = _norm(section_raw)
        section_key = _nows(section_raw)
        if (title, section) in norm_pairs:                      # rule 1
            correct += 1
        elif (title, section_key) in nows_pairs:                # rule 2
            correct += 1
        elif title in by_title and any(
                section in _norm(s) or _norm(s) in section
                for s in by_title[title]):                      # rule 3a
            correct += 1
        elif title in by_title and any(
                section_key in _nows(s) or _nows(s) in section_key
                for s in by_title[title]):                      # rule 3b
            correct += 1
        else:
            missing += 1
    return {"citations_total": total, "citations_correct": correct,
            "citations_missing": missing}


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


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _groundedness_block(rows: list[dict], sheet_path: Path | None,
                        run_prefix: str | None = None) -> dict:
    """Groundedness (faithfulness) summary over the human-scored sheet.

    Only rows with shown_to_user == "answer" are scorable (the rubric in
    v1_scoring_sheet.md says refusals are judged by refusal_correctness /
    hallucination_rate instead). A blank score is UNSCORED — never a zero.
    A refusal on a documented corpus gap is not a grounding failure, and an
    unscored row is not a zero; the mean's denominator is exactly the count
    of non-blank scores, asserted below.

    A groundedness score is a judgement of ONE answer text, not of a
    question id, so the sheet is only joined when the run being measured
    is the run the sheet was written against (SCORED_RUN_PREFIX). Other
    runs — the original-30 recompute, for instance, whose answer texts
    differ from the v1 run on most shared questions — get the unscored
    placeholder instead of someone else's scores.
    """
    n_shown = sum(1 for r in rows if r.get("shown_to_user") == "answer")
    n_answerable = sum(1 for r in rows
                       if str(r.get("answerable")) in ("True", "TRUE", "true"))
    scored_run = run_prefix == SCORED_RUN_PREFIX
    scores: list[float] = []
    if scored_run and sheet_path and sheet_path.exists():
        with sheet_path.open(encoding="utf-8", newline="") as f:
            for rec in csv.DictReader(f):
                if rec.get("shown_to_user") != "answer":
                    continue
                raw = (rec.get("groundedness_score") or "").strip()
                if raw:  # blanks are skipped, never coerced to 0.0
                    scores.append(float(raw))
    n_scored = len(scores)
    assert n_scored <= n_shown, (
        f"more groundedness scores ({n_scored}) than shown answers ({n_shown})")
    mean = (sum(scores) / n_scored) if n_scored else None
    block = {
        "mean": mean,
        "n_scored": n_scored,
        "n_shown_answers": n_shown,
        "n_answerable": n_answerable,
        "unscored": n_shown - n_scored,
        "rubric": "eval_results/v1_scoring_sheet.md",
        "sheet_applied": scored_run,
    }
    if not scored_run:
        block["note"] = (
            f"NOT SCORED for this run — the human sheet is written against "
            f"the '{SCORED_RUN_PREFIX}' run's answer texts and is not "
            f"attributed to other runs")
    return block


def compute_metrics(rows: list[dict], golden: list[dict], k: int = 5,
                    groundedness_sheet: Path | None = None,
                    run_prefix: str | None = None) -> dict:
    """All §3.3 metrics, computed once over the finished rows.

    Retrieval metrics use every row that has retrieved chunks (retrieval
    happens before generation, so a generation error does not poison them).
    Answer metrics use only rows with status=ok; the exclusions are counted.

    The chunk label index is built corpus-free from the rows themselves
    plus data/gold_chunks.json and data/sources.json (_build_chunk_index),
    so this function needs no built corpus — which is what makes
    --recompute-only reproducible on a bare clone.
    """
    golden_by_id = {str(e["id"]): e for e in golden}
    answerable_by_id = {
        str(e["id"]): bool(e.get("answerable", True)) for e in golden}
    # gold records come from the rows' attached _gold_record (set by the
    # caller from data/gold_chunks.json)
    gold_by_id = {str(r["id"]): r["_gold_record"]
                  for r in rows if r.get("_gold_record")}
    chunk_index = _build_chunk_index(rows, gold_by_id)

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
            # Faithfulness of the shown answers, scored by a human against
            # the rubric. Mean over non-blank scores only; blanks are
            # unscored, never zeros. See _groundedness_block.
            "groundedness": _groundedness_block(rows, groundedness_sheet,
                                                run_prefix),
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

    # Lazy: only a live evaluation needs the retriever. --recompute-only
    # never enters this function's loop body that calls it, but the import
    # stays here so importing run_eval never loads chroma/torch.
    from embed_store import query_store

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
        shown_to_user = classify_shown_to_user(status, refused, answer_text)

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

    # Final write: the in-loop crash-safe writes only cover questions whose
    # row was (re)computed in this process. On a --resume run, rows carried
    # forward join rows_by_id as the loop reaches them, so the last in-loop
    # write can miss the resumed tail. Rewrite the complete CSV here.
    _write_csv(csv_path, rows)

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

    # --- §3.3 metrics (gold set + corpus-free chunk label index) ----------
    gold_by_id, _ = _load_metrics_context(DEFAULT_GOLD_CHUNKS)
    for r in rows:
        r["_gold_record"] = gold_by_id.get(str(r["id"]))
    metrics = compute_metrics(
        rows, golden, k,
        groundedness_sheet=GROUNDEDNESS_SHEET, run_prefix=prefix)
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
    md.extend(_groundedness_md_rows(answers_m))
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
    g = answers_m.get("groundedness") or {}
    if g.get("n_scored"):
        print(f"groundedness:     mean {_fmt(g['mean'])} over {g['n_scored']} "
              f"of {g['n_shown_answers']} shown answers "
              f"({g['unscored']} unscored; never zeros)")
    else:
        print("groundedness:     NOT YET SCORED — human review pending "
              "(fill eval_results/v1_scoring_sheet.csv and re-run "
              "--recompute-only)")
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

    # An off-script refusal must never be silently absorbed into the
    # hallucination rate: under --strict it fails the run loudly so a human
    # decides what it was.
    unclassified_ids = [r["id"] for r in rows
                        if r.get("shown_to_user") == UNCLASSIFIED_REFUSAL]
    if unclassified_ids:
        print(f"UNCLASSIFIED REFUSAL CANDIDATES ({len(unclassified_ids)}): "
              f"{', '.join('Q' + str(i) for i in unclassified_ids)} — "
              f"non-empty answers that are neither the mandated refusal "
              f"sentence nor substantive answers.")
        if strict:
            print("STRICT: failing the run — an off-script refusal must "
                  "never be counted as a fabrication. Review these rows, "
                  "extend MODEL_REFUSAL_MARKERS if the model has learned a "
                  "new refusal phrasing, then re-run.")
            return 1
        print("WARNING: --no-strict set, exiting 0 despite unclassified "
              "refusal candidates.")
    print("RUN OK: every question produced an answer or a deliberate refusal.")
    return 0


def _looks_like_model_refusal(answer_text: str) -> bool:
    """True when the model itself declined instead of the guardrails."""
    text = (answer_text or "").lower()
    return any(marker in text for marker in MODEL_REFUSAL_MARKERS)


def _looks_like_offscript_refusal(answer_text: str) -> bool:
    """True for an off-script refusal: refusal language, no citation.

    The mandated refusal sentence is handled by _looks_like_model_refusal
    before this runs. This catches paraphrases ("I'm sorry, I can't provide
    medical advice."). The discriminator against a substantive answer is
    citation presence: check_citation_required blocks any shown answer that
    lacks a [Title, Section] citation, so a non-empty, non-mandated text
    with refusal language and no citation is an off-script refusal — never
    a fabrication, and never to be averaged into the hallucination rate.
    """
    text = (answer_text or "").strip()
    if not text or _CITATION_PRESENT_RE.search(text):
        return False
    return bool(_OFFSCRIPT_REFUSAL_RE.search(text))


def classify_shown_to_user(status: str, refused: str,
                           answer_text: str) -> str:
    """Which verdict the user actually saw, as a four-way bucket.

    none | guardrail_refusal | model_refusal | answer |
    unclassified_refusal_candidate (the fourth bucket: a non-empty answer
    that is neither the mandated refusal sentence nor a substantive answer).
    Adding the fourth bucket is classification-neutral on the frozen v1
    run: verified over all 50 rows, no shown_to_user value moves.
    """
    if status in ("generation_error", "no_chunks"):
        return "none"
    if refused == "TRUE":
        return "guardrail_refusal"
    if _looks_like_model_refusal(answer_text):
        return "model_refusal"
    text = (answer_text or "").strip()
    if not text:
        return "none"
    if _looks_like_offscript_refusal(text):
        return UNCLASSIFIED_REFUSAL
    return "answer"


def _groundedness_md_rows(answers_m: dict) -> list[str]:
    """The groundedness rows for a summary/README answer-quality table.

    The coverage framing is mandatory: the mean is over the shown answers
    only, never over the full answerable set — a refusal on a documented
    corpus gap is not a grounding failure, and an unscored row is not a
    zero. This is the correction of the original repo's error, where
    refusals were scored 0 and averaged in.
    """
    g = answers_m.get("groundedness") or {}
    if not g.get("n_scored"):
        if g.get("note"):
            return ["| groundedness (faithfulness of shown answers) | "
                    f"**{g['note']}** | not attributed across runs |"]
        return ["| groundedness (faithfulness of shown answers) | "
                "**NOT YET SCORED — human review pending** | fill "
                "`v1_scoring_sheet.csv`, then `--recompute-only` |"]
    n_scored = g["n_scored"]
    n_shown = g["n_shown_answers"]
    unscored = g["unscored"]
    n_answerable = g.get("n_answerable", "")
    return [
        f"| groundedness (faithfulness of shown answers) | "
        f"**{_fmt(g['mean'])}** | mean over the {n_scored} of {n_shown} "
        f"shown answers scored by hand ({unscored} unscored, never zeros); "
        f"the remaining {n_answerable - n_scored} of {n_answerable} "
        f"answerable questions were refused — see grounded_answer_rate |",
    ]


# ---------------------------------------------------------------------------
# Recompute (offline metric rebuild over a frozen CSV)
# ---------------------------------------------------------------------------
def recompute(prefix: str, golden_path: Path, k: int = 5) -> int:
    """Rebuild _metrics.json and _summary.md from a committed run CSV.

    Makes ZERO network calls: no retrieval, no generation, no groq import.
    Used after a gold-label correction or a citation-parser fix, when the
    run itself is frozen evidence and only the metric *inputs* changed.
    Idempotent: running it twice produces byte-identical files.
    """
    if not golden_path.exists():
        sys.exit(f"ERROR: golden set not found: {golden_path}")
    csv_path = EVAL_DIR / f"{prefix}.csv"
    if not csv_path.exists():
        sys.exit(f"ERROR: run CSV not found: {csv_path}")

    with golden_path.open("r", encoding="utf-8") as f:
        golden = json.load(f)
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    gold_by_id, _ = _load_metrics_context(DEFAULT_GOLD_CHUNKS)
    for r in rows:
        r["_gold_record"] = gold_by_id.get(str(r["id"]))
    metrics = compute_metrics(rows, golden, k,
                              groundedness_sheet=GROUNDEDNESS_SHEET,
                              run_prefix=prefix)
    metrics_path = EVAL_DIR / f"{prefix}_metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")

    # --- summary (same tables as evaluate(), manifest states the source) --
    retrieval_m = metrics["retrieval"]
    answers_m = metrics["answers"]
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    shown_counts: dict[str, int] = {}
    for r in ok_rows:
        shown_counts[r["shown_to_user"]] = shown_counts.get(
            r["shown_to_user"], 0) + 1
    retry_total = sum(int(r.get("retries") or 0) for r in rows)
    answerable_total = sum(
        1 for r in rows if r["answerable"] in (True, "True", "TRUE"))

    md = []
    md.append(f"# Evaluation Summary — '{prefix}' run\n")
    md.append(f"- Golden set: `{golden_path.name}` ({len(golden)} questions; "
              f"{answerable_total} answerable, "
              f"{len(golden) - answerable_total} unanswerable)")
    md.append(f"- Retrieval configuration: top-{k} chunks "
              f"(chunk size 700 chars, overlap 100)")
    md.append(f"- Source: recomputed offline from `{csv_path.name}` by "
              f"`run_eval.py --recompute-only` (no API call made)")
    md.append(f"- Retries recorded in the CSV: {retry_total}")
    md.append(f"- **Rows excluded from every average: "
              f"{len(rows) - len(ok_rows)}** (status != ok)")
    md.append(f"- What reached the user: " +
              (", ".join(f"{v}× {k2}" for k2, v in sorted(shown_counts.items()))
               if shown_counts else "(no ok rows)"))
    md.append("")
    md.append("## Retrieval quality\n")
    md.append("| metric | value | definition |")
    md.append("|--------|-------|------------|")
    md.append(f"| recall@{k} | **{_fmt(retrieval_m['recall_at_k'])}** | "
              f"mean over {metrics['gold_questions']} questions with gold |")
    md.append(f"| context_precision@{k} | "
              f"**{_fmt(retrieval_m['context_precision_at_k'])}** | mean |")
    md.append(f"| MRR | **{_fmt(retrieval_m['mrr'])}** | mean |")
    md.append(f"| document-level hit rate (old metric) | "
              f"**{retrieval_m['document_level_hits']}/"
              f"{retrieval_m['document_level_answerable']}** | saturated |")
    md.append("")
    md.append("## Answer quality\n")
    md.append("| metric | value | over |")
    md.append("|--------|-------|------|")
    md.append(f"| grounded_answer_rate | "
              f"**{_fmt(answers_m['grounded_answer_rate'])}** | "
              f"{answers_m['answerable_questions']} answerable |")
    md.append(f"| refusal_correctness | "
              f"**{_fmt(answers_m['refusal_correctness'])}** | "
              f"{answers_m['unanswerable_questions']} unanswerable |")
    md.append(f"| hallucination_rate | "
              f"**{_fmt(answers_m['hallucination_rate'])}** | "
              f"{answers_m['unanswerable_questions']} unanswerable |")
    md.append(f"| citation_correctness | "
              f"**{_fmt(answers_m['citation_correctness'])}** | "
              f"{answers_m['citations_total']} inline citations |")
    md.append(f"| citation_target_missing | "
              f"**{answers_m['citations_missing']}** | citations not in the "
              f"retrieved set |")
    md.extend(_groundedness_md_rows(answers_m))
    md.append("")
    md.append(f"Machine-readable copy: `eval_results/{metrics_path.name}`.")
    md_path = EVAL_DIR / f"{prefix}_summary.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"RECOMPUTE OK — no API call made")
    print(f"  CSV:     {csv_path} ({len(rows)} rows loaded)")
    print(f"  Metrics: {metrics_path}")
    print(f"  Summary: {md_path}")
    g = answers_m.get("groundedness") or {}
    print(f"  recall@{k}: {_fmt(retrieval_m['recall_at_k'])}  "
          f"citation_correctness: {_fmt(answers_m['citation_correctness'])} "
          f"({answers_m['citations_correct']}/{answers_m['citations_total']})  "
          f"gold_questions: {metrics['gold_questions']}")
    if g.get("n_scored"):
        print(f"  groundedness: mean {_fmt(g['mean'])} over {g['n_scored']} "
              f"of {g['n_shown_answers']} shown answers")
    return 0


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
    parser.add_argument(
        "--recompute-only", dest="recompute_only", action="store_true",
        default=False,
        help="Rebuild <prefix>_metrics.json and <prefix>_summary.md from the "
             "committed CSV with ZERO network calls (used after gold-label "
             "or citation-parser fixes; never calls the API).",
    )
    args = parser.parse_args()
    if args.recompute_only:
        code = recompute(args.prefix, Path(args.golden), k=args.k)
    else:
        code = evaluate(Path(args.golden), args.prefix, strict=args.strict,
                        resume=args.resume, k=args.k)
    sys.exit(code)


if __name__ == "__main__":
    main()
