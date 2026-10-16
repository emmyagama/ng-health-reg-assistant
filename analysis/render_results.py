#!/usr/bin/env python3
"""
render_results.py
=================
Generate the evaluation tables from committed artefacts and splice them
into the documents between explicit markers, so no number in README.md or
notes/failure_modes.md is typed by hand.

Inputs (all committed):
  eval_results/b1_v1.csv, b1_v1_metrics.json        the 50-question run
  eval_results/b1_v1_g30.csv, b1_v1_g30_metrics.json the original-30 run
  data/gold_chunks.json, data/golden_set_50.json
  data/processed/all_chunks.json

Outputs (between markers, rewritten in place):
  README.md               <!-- BEGIN GENERATED: eval-results --> ... <!-- END ... -->
  notes/failure_modes.md  <!-- BEGIN GENERATED: failure-counts --> ... <!-- END ... -->

Guarantees:
  * idempotent — running twice produces byte-identical files
  * --check exits non-zero if any committed block is stale
  * every number is derived from a CSV row; the tables carry their n

Usage:
    python analysis/render_results.py          # write
    python analysis/render_results.py --check  # verify only
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RUN50 = ROOT / "eval_results" / "b1_v1.csv"
RUN50_METRICS = ROOT / "eval_results" / "b1_v1_metrics.json"
RUN30 = ROOT / "eval_results" / "b1_v1_g30.csv"
RUN30_METRICS = ROOT / "eval_results" / "b1_v1_g30_metrics.json"
GOLD_CHUNKS = ROOT / "data" / "gold_chunks.json"
GOLDEN50 = ROOT / "data" / "golden_set_50.json"
ALL_CHUNKS = ROOT / "data" / "processed" / "all_chunks.json"

README = ROOT / "README.md"
FAILURE_MODES = ROOT / "notes" / "failure_modes.md"

EVAL_MARKER = "eval-results"
COUNTS_MARKER = "failure-counts"

BEGIN = "<!-- BEGIN GENERATED: {name} -->"
END = "<!-- END GENERATED: {name} -->"


def _load():
    for p in (RUN50, RUN50_METRICS, RUN30, RUN30_METRICS,
              GOLD_CHUNKS, GOLDEN50, ALL_CHUNKS):
        if not p.exists():
            raise SystemExit(f"missing {p}")
    rows50 = list(csv.DictReader(RUN50.open(encoding="utf-8")))
    rows30 = list(csv.DictReader(RUN30.open(encoding="utf-8")))
    m50 = json.loads(RUN50_METRICS.read_text(encoding="utf-8"))
    m30 = json.loads(RUN30_METRICS.read_text(encoding="utf-8"))
    gold = json.loads(GOLD_CHUNKS.read_text(encoding="utf-8"))
    golden = json.loads(GOLDEN50.read_text(encoding="utf-8"))
    chunks = json.loads(ALL_CHUNKS.read_text(encoding="utf-8"))
    if len(rows50) != 50:
        raise SystemExit(f"{RUN50.name}: expected 50 rows, got {len(rows50)}")
    if len(rows30) != 30:
        raise SystemExit(f"{RUN30.name}: expected 30 rows, got {len(rows30)}")
    return rows50, rows30, m50, m30, gold, golden, chunks


def _fmt(v, digits=3, pct=False):
    if v is None:
        return "n/a"
    if pct:
        return f"{100 * v:.1f}%"
    return f"{v:.{digits}f}"


def _refusal_like(text: str) -> bool:
    t = (text or "").strip()
    return (not t
            or t.startswith("I don't have enough information")
            or "cannot answer" in t[:120].lower())


def eval_table(rows50, m50) -> str:
    """The §6.4 table: Metric | Before guardrails | After guards | Source."""
    retrieval = m50["retrieval"]
    answers = m50["answers"]
    k = m50["k"]

    latencies = [float(r["latency_seconds"]) for r in rows50
                 if r["status"] == "ok"]
    tokens = [(int(r["input_tokens"] or 0) + int(r["output_tokens"] or 0))
              for r in rows50 if r["status"] == "ok"
              if r["input_tokens"] and r["output_tokens"]]

    # Raw-model surface: what the model said before guardrail replacement.
    answerable = [r for r in rows50 if r["answerable"] in (True, "True", "TRUE")]
    unanswerable = [r for r in rows50
                    if r["answerable"] in (False, "False", "FALSE")]
    raw_answered = [r for r in answerable if not _refusal_like(r["answer_text"])]
    raw_refused_unans = [r for r in unanswerable if _refusal_like(r["answer_text"])]
    raw_halluc = len(unanswerable) - len(raw_refused_unans)

    n_ans = answers["answerable_questions"]
    n_unans = answers["unanswerable_questions"]
    n_gold = m50["gold_questions"]

    lines = [
        "| Metric | Before guardrails (raw model output) | "
        "After guardrails (shown to user) | Source |",
        "|---|---|---|---|",
        f"| recall@{k} | {_fmt(retrieval['recall_at_k'])} "
        f"(n={n_gold}) | {_fmt(retrieval['recall_at_k'])} (n={n_gold}) | "
        f"`b1_v1_metrics.json` |",
        f"| context precision@{k} | "
        f"{_fmt(retrieval['context_precision_at_k'])} (n={n_gold}) | "
        f"{_fmt(retrieval['context_precision_at_k'])} (n={n_gold}) | "
        f"`b1_v1_metrics.json` |",
        f"| MRR | {_fmt(retrieval['mrr'])} (n={n_gold}) | "
        f"{_fmt(retrieval['mrr'])} (n={n_gold}) | `b1_v1_metrics.json` |",
        f"| document-level hit rate (old metric, saturated) | "
        f"{retrieval['document_level_hits']}/"
        f"{retrieval['document_level_answerable']} | "
        f"{retrieval['document_level_hits']}/"
        f"{retrieval['document_level_answerable']} | "
        f"`b1_v1_metrics.json` |",
        f"| grounded answer rate | "
        f"{len(raw_answered)}/{len(answerable)} = "
        f"{_fmt(len(raw_answered) / len(answerable) if answerable else None, pct=True)} | "
        f"{_fmt(answers['grounded_answer_rate'], pct=True)} (n={n_ans}) | "
        f"`b1_v1.csv` / `b1_v1_metrics.json` |",
        f"| refusal correctness | "
        f"{len(raw_refused_unans)}/{len(unanswerable)} = "
        f"{_fmt(len(raw_refused_unans) / len(unanswerable) if unanswerable else None, pct=True)} | "
        f"{_fmt(answers['refusal_correctness'], pct=True)} (n={n_unans}) | "
        f"`b1_v1.csv` / `b1_v1_metrics.json` |",
        f"| hallucination rate | {raw_halluc}/{len(unanswerable)} = "
        f"{_fmt(raw_halluc / len(unanswerable) if unanswerable else None, pct=True)} | "
        f"{_fmt(answers['hallucination_rate'], pct=True)} (n={n_unans}) | "
        f"`b1_v1.csv` / `b1_v1_metrics.json` |",
        f"| citation correctness | not measured pre-guardrails | "
        f"{_fmt(answers['citation_correctness'])} "
        f"({answers['citations_correct']}/{answers['citations_total']} "
        f"inline citations) | `b1_v1_metrics.json` |",
        f"| median end-to-end latency | "
        f"{statistics.median(latencies):.2f} s (n={len(latencies)}) | same "
        f"run, guardrails add no network calls | `b1_v1.csv` |",
        f"| mean tokens per call (in+out) | "
        f"{statistics.mean(tokens):.0f} (n={len(tokens)}) | same run | "
        f"`b1_v1.csv` |",
    ]
    return "\n".join(lines)


def counts_table(rows50, gold, golden, chunks) -> str:
    """§6.5 taxonomy counts, every number keyed to question ids."""
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    from embed_store import MAX_PER_DOC
    from run_eval import DEFAULT_GOLD_CHUNKS, _citation_metrics, \
        _load_metrics_context
    _, chunk_index = _load_metrics_context(DEFAULT_GOLD_CHUNKS)

    gold_by_id = {str(r["id"]): r for r in gold}
    golden_by_id = {str(e["id"]): e for e in golden}
    doc_title = {c["chunk_id"]: c.get("doc_id", "") for c in chunks}

    def ids(pred):
        return [r["id"] for r in rows50 if pred(r)]

    def is_answerable(r):
        return r["answerable"] in (True, "True", "TRUE")

    # --- retrieval layer ---
    gold_miss = []       # answerable with gold, zero gold in top-k
    crowding_over = []   # same doc holding > MAX_PER_DOC slots (violation)
    crowding_at_cap = 0  # same doc holding exactly the cap (expected)
    for r in rows50:
        qid = str(r["id"])
        retrieved = [c for c in r["retrieved_chunk_ids"].split(";") if c]
        gold_ids = {g["chunk_id"]
                    for g in gold_by_id.get(qid, {}).get("gold_chunks", [])}
        if is_answerable(r) and gold_ids and not any(
                c in gold_ids for c in retrieved):
            gold_miss.append(qid)
        per_doc = Counter(doc_title.get(c, "?") for c in retrieved)
        top = max(per_doc.values()) if per_doc else 0
        if top > MAX_PER_DOC:
            crowding_over.append(qid)
        elif top == MAX_PER_DOC:
            crowding_at_cap += 1

    # --- answer layer ---
    # Q20-Q22 are answerable in principle but their source pages were never
    # recovered (documented corpus gap); refusing them is the expected
    # behaviour and must not be counted as over-refusal.
    gap_ids = {str(e["id"]) for e in golden
               if e.get("answerable", True)
               and not gold_by_id.get(str(e["id"]), {}).get("gold_in_corpus",
                                                            True)}
    over_refusal_gr = ids(lambda r: is_answerable(r)
                          and str(r["id"]) not in gap_ids
                          and r["shown_to_user"] == "guardrail_refusal")
    over_refusal_model = ids(lambda r: is_answerable(r)
                             and str(r["id"]) not in gap_ids
                             and r["shown_to_user"] == "model_refusal")
    gap_refusal = ids(lambda r: str(r["id"]) in gap_ids
                      and r["shown_to_user"] in ("guardrail_refusal",
                                                 "model_refusal"))
    correct_refusal = ids(lambda r: not is_answerable(r)
                          and r["shown_to_user"] in ("guardrail_refusal",
                                                     "model_refusal"))
    halluc = ids(lambda r: not is_answerable(r)
                 and r["shown_to_user"] == "answer")
    blocked_halluc = ids(lambda r: not is_answerable(r)
                         and r["shown_to_user"] != "answer"
                         and not _refusal_like(r["answer_text"]))

    def cite_misses(r) -> bool:
        retrieved = [c for c in r["retrieved_chunk_ids"].split(";") if c]
        cm = _citation_metrics(r["answer_text"], retrieved, chunk_index, 5)
        return cm["citations_missing"] > 0

    cite_miss_rows = ids(lambda r: r["shown_to_user"] == "answer"
                         and cite_misses(r))

    def fmt_ids(qids):
        if not qids:
            return "none"
        return ", ".join("Q" + q for q in qids)

    lines = [
        "| Layer | Class | Count | Question ids |",
        "|---|---|---|---|",
        f"| retrieval | gold chunk outside top-{mK} (answerable, has gold) | "
        f"{len(gold_miss)} | {fmt_ids(gold_miss)} |",
        f"| retrieval | same document holds >{MAX_PER_DOC} of the top-{mK} "
        f"slots (diversity-cap violation) | {len(crowding_over)} | "
        f"{fmt_ids(crowding_over)} |",
        f"| retrieval | same document holds exactly {MAX_PER_DOC} of the "
        f"top-{mK} slots (cap engaged, expected) | {crowding_at_cap} | "
        f"(not enumerated) |",
        f"| answer | over-refusal by a guardrail (answerable, in corpus) | "
        f"{len(over_refusal_gr)} | {fmt_ids(over_refusal_gr)} |",
        f"| answer | over-refusal by the model itself (answerable, in corpus) | "
        f"{len(over_refusal_model)} | {fmt_ids(over_refusal_model)} |",
        f"| answer | refusal of a documented corpus-gap question "
        f"(expected; Q20-Q22 source pages never recovered) | "
        f"{len(gap_refusal)} | {fmt_ids(gap_refusal)} |",
        f"| answer | correct refusal (unanswerable) | "
        f"{len(correct_refusal)} | {fmt_ids(correct_refusal)} |",
        f"| answer | visible hallucination (unanswerable, answer shown) | "
        f"{len(halluc)} | {fmt_ids(halluc)} |",
        f"| answer | raw hallucination caught before display | "
        f"{len(blocked_halluc)} | {fmt_ids(blocked_halluc)} |",
        f"| answer | citation target missing (>=1 citation not in the "
        f"retrieved set) | {len(cite_miss_rows)} | {fmt_ids(cite_miss_rows)} |",
    ]
    return "\n".join(lines)


mK = 5  # module-level k used by counts_table's f-strings


def splice(path: Path, name: str, body: str, check: bool) -> bool:
    """Replace the marked block in path. Returns True if changed/stale."""
    begin, end = BEGIN.format(name=name), END.format(name=name)
    text = path.read_text(encoding="utf-8")
    if begin not in text or end not in text:
        raise SystemExit(f"{path}: markers for {name} not found")
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    new_text = head + begin + "\n" + body.rstrip() + "\n" + end + tail
    changed = new_text != text
    if changed and not check:
        path.write_text(new_text, encoding="utf-8", newline="\n")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    parser.add_argument("--check", action="store_true",
                        help="verify committed blocks match a fresh render")
    args = parser.parse_args()

    rows50, rows30, m50, m30, gold, golden, chunks = _load()
    eval_body = eval_table(rows50, m50)
    counts_body = counts_table(rows50, gold, golden, chunks)

    stale = []
    if splice(README, EVAL_MARKER, eval_body, args.check):
        stale.append(f"README.md:{EVAL_MARKER}")
    if splice(FAILURE_MODES, COUNTS_MARKER, counts_body, args.check):
        stale.append(f"notes/failure_modes.md:{COUNTS_MARKER}")

    if args.check:
        if stale:
            print("STALE generated blocks:")
            for s in stale:
                print(f"  - {s}")
            sys.exit(1)
        print("OK: all generated blocks match a fresh render.")
        return

    if stale:
        print("updated:")
        for s in stale:
            print(f"  - {s}")
    else:
        print("no changes (already up to date).")


if __name__ == "__main__":
    main()
