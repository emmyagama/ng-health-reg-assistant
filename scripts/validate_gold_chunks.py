#!/usr/bin/env python3
"""
validate_gold_chunks.py
=======================
Anti-fabrication check for data/gold_chunks.json.

The one rule that matters: every `evidence` string must be a verbatim
substring of the chunk it claims to come from. If this script fails, the
gold set is wrong and no metric computed from it may be published.

Only Q1-Q30 have gold chunks. Q31-Q50 are unanswerable by design and are
correctly absent from gold_chunks.json.

Usage:
    python scripts/validate_gold_chunks.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLD_CHUNKS = ROOT / "data" / "gold_chunks.json"
GOLDEN = ROOT / "data" / "golden_set_50.json"
ALL_CHUNKS = ROOT / "data" / "processed" / "all_chunks.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    for path in (GOLD_CHUNKS, GOLDEN, ALL_CHUNKS):
        if not path.exists():
            raise SystemExit(f"missing {path}")

    gold = json.loads(GOLD_CHUNKS.read_text(encoding="utf-8"))
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    chunks = json.loads(ALL_CHUNKS.read_text(encoding="utf-8"))
    by_id = {c["chunk_id"]: c for c in chunks}
    golden_by_id = {int(e["id"]): e for e in golden}

    failures: list[str] = []
    checked_evidence = 0

    # gold_chunks.json has a record for every graded question (ids 1..30):
    # answerable ones carry gold_chunks, unanswerable ones carry a refusal
    # record with gold_in_corpus=false. The 20 new unanswerable questions
    # (Q31-Q50) were never graded and are legitimately absent, so parity is
    # against the graded subset, not the full golden set.
    graded_ids = [int(r["id"]) for r in gold]
    if graded_ids != sorted(golden_by_id)[:len(graded_ids)]:
        failures.append(
            f"gold_chunks ids {graded_ids[:5]}... are not a prefix of the "
            f"golden set ids")
    if len(graded_ids) != 30:
        failures.append(
            f"expected gold records for the graded 30 questions, got "
            f"{len(graded_ids)}")

    for record in gold:
        qid = int(record["id"])
        entry = golden_by_id.get(qid)
        if entry is None:
            failures.append(f"Q{qid}: no such question in the golden set")
            continue

        answerable = bool(entry.get("answerable", True))
        in_corpus = bool(record.get("gold_in_corpus"))
        gold_list = record.get("gold_chunks", [])
        note = str(record.get("note", "")).strip()

        if record.get("graded_by") != "agent":
            failures.append(f"Q{qid}: graded_by must be 'agent'")
        if not note:
            failures.append(f"Q{qid}: missing note")
        if in_corpus and not gold_list:
            failures.append(f"Q{qid}: gold_in_corpus true but no gold chunks")
        if not in_corpus and gold_list:
            failures.append(f"Q{qid}: gold_in_corpus false but gold chunks present")
        if answerable and not in_corpus:
            # Legitimate: the question is in scope for the project but the
            # corpus does not contain the answer (Q20-Q22, whose NHIA
            # guidance body was never recovered by OCR). The note must say so.
            if "corpus" not in note.lower():
                failures.append(
                    f"Q{qid}: answerable but not-in-corpus, and the note "
                    f"does not explain the corpus gap")
        if not answerable and in_corpus:
            failures.append(
                f"Q{qid}: unanswerable question marked gold_in_corpus true")

        seen: set[str] = set()
        for gc in gold_list:
            cid = gc.get("chunk_id", "")
            if cid in seen:
                failures.append(f"Q{qid}: duplicate gold chunk {cid}")
            seen.add(cid)

            chunk = by_id.get(cid)
            if chunk is None:
                failures.append(f"Q{qid}: unknown chunk {cid}")
                continue
            if gc.get("doc_id") != chunk["doc_id"]:
                failures.append(
                    f"Q{qid}/{cid}: doc_id {gc.get('doc_id')!r} != "
                    f"chunk doc_id {chunk['doc_id']!r}")
            evidence = gc.get("evidence", "")
            if not (40 <= len(evidence) <= 200):
                failures.append(
                    f"Q{qid}/{cid}: evidence length {len(evidence)} "
                    f"outside 40-200")
            if evidence not in chunk["text"]:
                failures.append(
                    f"Q{qid}/{cid}: EVIDENCE IS NOT A VERBATIM SUBSTRING "
                    f"OF THE CHUNK — this is the fabrication guard")
            else:
                checked_evidence += 1

    total_gold = sum(len(r.get("gold_chunks", [])) for r in gold)
    in_corpus_q = sum(1 for r in gold if r.get("gold_in_corpus"))
    print(f"questions:            {len(gold)}")
    print(f"gold_in_corpus=true:  {in_corpus_q}")
    print(f"gold chunk entries:   {total_gold}")
    print(f"evidence verified:    {checked_evidence}")

    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  - {f}")
        raise SystemExit(1)
    print("\nGOLD SET VALID: every evidence string is a verbatim substring "
          "of its chunk.")


if __name__ == "__main__":
    main()
