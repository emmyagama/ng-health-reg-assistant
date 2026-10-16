#!/usr/bin/env python3
"""Classifier bucket tests for run_eval.classify_shown_to_user.

Three buckets are asserted (Fix 5):
  1. the mandated refusal sentence            -> model_refusal
  2. an off-script refusal (no citation)      -> unclassified_refusal_candidate
  3. substantive answer text                  -> answer

Plus the neutrality property: the fourth bucket must not move any row of
the frozen v1 run (eval_results/b1_v1.csv) — if it does, the change is not
classification-neutral and must be reported, not shipped.

Run: python -m pytest tests/test_classifier.py -v
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from run_eval import (  # noqa: E402
    MODEL_REFUSAL_MARKERS,
    UNCLASSIFIED_REFUSAL,
    classify_shown_to_user,
)

MANDATED_REFUSAL = (
    "I don't have enough information in the provided documents to answer this."
)
OFFSCRIPT_REFUSAL = "I'm sorry, I can't provide medical advice."
SUBSTANTIVE_ANSWER = (
    "HEFAMAA requires annual registration "
    "[HEFAMAA Quick Guide, Register Facility] before operations begin."
)


def test_mandated_refusal_sentence():
    assert classify_shown_to_user("ok", "FALSE", MANDATED_REFUSAL) == "model_refusal"


def test_second_mandated_variant():
    text = "I do not have enough information in the provided documents."
    assert classify_shown_to_user("ok", "FALSE", text) == "model_refusal"


def test_offscript_refusal_is_fourth_bucket():
    got = classify_shown_to_user("ok", "FALSE", OFFSCRIPT_REFUSAL)
    assert got == UNCLASSIFIED_REFUSAL


def test_substantive_answer_is_answer():
    assert classify_shown_to_user("ok", "FALSE", SUBSTANTIVE_ANSWER) == "answer"


def test_guardrail_refusal_wins_first():
    # Even if the text also looks like a model refusal, a guardrail block
    # is what reached the user.
    assert (classify_shown_to_user("ok", "TRUE", MANDATED_REFUSAL)
            == "guardrail_refusal")


def test_pipeline_failures_are_none():
    assert classify_shown_to_user("generation_error", "", "x") == "none"
    assert classify_shown_to_user("no_chunks", "", "") == "none"


def test_frozen_run_classification_is_neutral():
    """The fourth bucket must not move any row of the frozen v1 run.

    If this fails, the classifier change is not classification-neutral:
    stop and report rather than shipping — the frozen CSV is evidence.
    """
    csv_path = ROOT / "eval_results" / "b1_v1.csv"
    if not csv_path.exists():
        import pytest
        pytest.skip("frozen run CSV not present")
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert len(rows) == 50
    moves = []
    for r in rows:
        got = classify_shown_to_user(r["status"], r["refused"], r["answer_text"])
        if got != r["shown_to_user"]:
            moves.append((r["id"], r["shown_to_user"], got))
    assert moves == [], f"classifier moved frozen rows: {moves}"


def test_mandated_markers_documented():
    # The classifier depends on these exact strings; the system prompt in
    # src/answer.py mandates them. If the prompt changes, this test and
    # MODEL_REFUSAL_MARKERS must change together.
    assert any("i don't have enough information" in m for m in MODEL_REFUSAL_MARKERS)
    assert any("i do not have enough information" in m for m in MODEL_REFUSAL_MARKERS)
