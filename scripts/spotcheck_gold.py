#!/usr/bin/env python3
"""Spot-check graded gold chunks against the built corpus — human audit aid.

The gold set in data/gold_chunks.json was graded by an AI agent with every
evidence string verified verbatim by scripts/validate_gold_chunks.py at
grading time. This tool exists for the SECOND human pass: it draws a
seeded random sample of gold entries and shows each evidence string in
the context of its chunk, so a reader can confirm with their own eyes
that the graded passage really does contain the answer the question asks
for.

This is deliberately NOT an automatic verdict. Evidence-substring checks
already pass in validate_gold_chunks.py; what only a human can judge is
whether the passage answers the question. The output is a worksheet.

Usage:
    python scripts/spotcheck_gold.py                 # 8 entries, seed 5
    python scripts/spotcheck_gold.py --n 15 --seed 42
    python scripts/spotcheck_gold.py --id 22         # force one question

Requires the built corpus (data/processed/all_chunks.json) — run
bash scripts/build.sh first.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLD_PATH = ROOT / "data" / "gold_chunks.json"
CHUNKS_PATH = ROOT / "data" / "processed" / "all_chunks.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=8,
                    help="number of gold entries to sample (default 8)")
    ap.add_argument("--seed", type=int, default=5,
                    help="RNG seed so the sample is reproducible (default 5)")
    ap.add_argument("--id", type=str, default=None,
                    help="sample only this question id")
    args = ap.parse_args()

    if not GOLD_PATH.exists():
        sys.exit(f"ERROR: {GOLD_PATH} not found")
    if not CHUNKS_PATH.exists():
        sys.exit(f"ERROR: {CHUNKS_PATH} not found — run bash scripts/build.sh")

    gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    chunks = {c["chunk_id"]: c
              for c in json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))}

    entries = []
    for g in gold:
        if args.id is not None and str(g.get("id")) != args.id:
            continue
        for gc in g.get("gold_chunks", []):
            entries.append((g, gc))
    if args.id is not None and not entries:
        sys.exit(f"ERROR: question {args.id} has no gold chunks")
    if not entries:
        sys.exit("ERROR: no gold entries found")

    rng = random.Random(args.seed)
    sample = entries if args.n >= len(entries) else rng.sample(entries, args.n)

    ok = True
    print(f"Spot-check worksheet — {len(sample)} of {len(entries)} gold "
          f"entries, seed {args.seed}")
    print("For each entry: does the quoted passage ANSWER the question?")
    print("Evidence-substring presence is checked automatically; the "
          "judgement is yours.\n")
    for g, gc in sample:
        chunk = chunks.get(gc["chunk_id"])
        evidence = gc.get("evidence", "")
        if chunk is None:
            print(f"!! Q{g['id']} {gc['chunk_id']} NOT IN BUILT CORPUS")
            ok = False
            continue
        present = evidence in chunk.get("text", "")
        mark = "OK " if present else "!! "
        if not present:
            ok = False
        print(f"{mark}Q{g['id']} — {g.get('question', '')[:110]}")
        print(f"   chunk {gc['chunk_id']}  doc={gc.get('doc_id')}  "
              f"section={gc.get('section_label', '')[:60]}")
        print(f"   evidence present in chunk text: {present}")
        print(f"   evidence: {evidence[:160]}")
        pos = chunk.get("text", "").find(evidence)
        if pos >= 0:
            start = max(0, pos - 80)
            end = min(len(chunk["text"]), pos + len(evidence) + 80)
            ctx = chunk["text"][start:end].replace("\n", " ")
            print(f"   context:  ...{ctx}...")
        print()

    if not ok:
        print("VERDICT: at least one sampled entry failed the mechanical "
              "check — fix gold_chunks.json or rebuild, do not proceed.")
        return 1
    print("VERDICT: all sampled evidence strings are verbatim in their "
          "chunks. Read each passage above and tick it off against the "
          "question; record disagreements in data/SOURCES_STATUS.md or the "
          "run report.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
