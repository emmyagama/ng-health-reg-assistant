#!/usr/bin/env python3
"""
guardrails.py
=============
Four independent, composable guardrail checks plus an orchestrator that
runs them all on a single (question, retrieved_chunks, answer_text) triple.

Each check returns (passed: bool, message: str) where message is "" on
pass and a short refusal reason on fail.

apply_guardrails() returns:
    {
      "allowed": bool,                 # False if ANY check fails
      "refusal_reasons": [str, ...],   # human-readable failure messages
      "triggered_checks": [str, ...]   # names of failing functions
    }
"""

from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# 1. Retrieval-confidence check
# ---------------------------------------------------------------------------
# NOTE ON DISTANCE SEMANTICS: Chroma's default collection uses L2
# (squared Euclidean) distance, which is what embed_store.build_vector_store
# explicitly sets via metadata={"hnsw:space": "l2"}.
# -> LOWER distance = MORE similar. 0.0 means the query embedding is
#    identical to the chunk embedding. Higher values = further apart.
# The 0.8 default threshold should be CALIBRATED against real eval data
# (e.g. inspect the distance distribution of known-good hits vs. known
# misses in run_eval.py output) once available. For now it is a
# reasonable starting point for all-MiniLM-L6-v2 embeddings.
def check_retrieval_confidence(
    retrieved_chunks: list[dict],
    max_distance_threshold: float = 0.8,
) -> tuple[bool, str]:
    """Pass if the closest retrieved chunk is within the distance threshold."""
    if not retrieved_chunks:
        return False, "no documents were retrieved for this question"
    best_dist = min(float(c.get("distance", float("inf"))) for c in retrieved_chunks)
    if best_dist > max_distance_threshold:
        return False, "retrieval confidence too low"
    return True, ""


# ---------------------------------------------------------------------------
# 2. Citation-presence check
# ---------------------------------------------------------------------------
# Accepts citations of the form  [Document Title, Section Label]
# (the same format generate_answer instructs the model to emit).
# CJK brackets 【…】 and full-width comma ，are accepted as equivalents —
# the model occasionally emits them under low temperature.
# Allows letters, digits, spaces, hyphens, periods, apostrophes,
# parentheses, colons, ampersands and slashes inside the brackets.
_CITATION_RE = re.compile(
    r"[\[【]"
    r"[^\[\]【】\n]{2,200}?"
    r"[,，]"
    r"[^\[\]【】\n]{2,200}?"
    r"[\]】]"
)


def check_citation_required(answer_text: str) -> tuple[bool, str]:
    """Pass if the answer contains at least one [Title, Section] citation."""
    if not answer_text:
        return False, "no citation found in answer (answer was empty)"
    # Special case: the standard "I don't have enough information..."
    # refusal is not required to carry citations.
    if "I don't have enough information" in answer_text:
        return True, ""
    if not _CITATION_RE.search(answer_text):
        return False, "no citation found in answer"
    return True, ""


# ---------------------------------------------------------------------------
# 3. Clinical / out-of-scope question check
# ---------------------------------------------------------------------------
# Clinical keywords that indicate the user is asking for medical advice
# (diagnosis, treatment, dosing) rather than regulatory/administrative
# information. The list intentionally covers direct synonyms and common
# abbreviations encountered in a health-regulation corpus.
_CLINICAL_KEYWORDS = [
    # Diagnosis / symptoms
    r"\bdiagnos[ei]\w*",      # diagnose, diagnosis, diagnosing
    r"\bsymptoms?\b",
    r"\bsign[s]?\b",          # clinical signs (loose match)
    # Treatment / prescribing
    r"\btreat(?:ment|ing|ed)?\b",
    r"\bprescrib(?:e|ing|ed)\b",
    r"\bprescription[s]?\b",
    # Medication / dosing
    r"\bmedication[s]?\b",
    r"\bdrug[s]?\b",
    r"\bdosage[s]?\b",
    r"\bdose[s]?\b",
    r"\b\d+\s*mg\b",          # e.g. 500 mg
    r"\b\d+\s*ml\b",
    r"\b\d+\s*mcg\b",
    r"\b\d+\s*iu\b",
    r"\btablet[s]?\b",
    r"\bcapsule[s]?\b",
    r"\binjection[s]?\b",
    # Patient-condition phrasing
    r"patient['']?s?\s+condition",
    r"medical\s+advice",
    r"should\s+i\s+take\b",
    # Specific clinical requests
    r"\bantibiotic[s]?\b",
    r"\bantiviral[s]?\b",
    r"\bvaccin(?:e|ation)\b",
    r"\btherap[yeu]\w*",
]
_CLINICAL_RE = re.compile("|".join(_CLINICAL_KEYWORDS), re.IGNORECASE)

# "treatment" is ambiguous: in a legal/rights context it is regulatory, not
# clinical (e.g. "the right to emergency treatment", "refuse treatment",
# "offence to deny treatment"). It is exempted when it sits within
# _LEGAL_CONTEXT_WINDOW words of one of these legal terms.
_TREATMENT_RE = re.compile(r"\btreat(?:ment|ing|ed)?\b", re.IGNORECASE)
_LEGAL_CONTEXT_RE = re.compile(
    r"\b(rights?|refus\w*|emergency|offenc\w*|offens\w*|penalt\w*)\b",
    re.IGNORECASE,
)
_LEGAL_CONTEXT_WINDOW = 6  # words either side of the match


def _in_legal_context(question: str, start: int, end: int) -> bool:
    """True when the match at [start:end] sits within _LEGAL_CONTEXT_WINDOW
    words of a legal/rights term."""
    words = question.split()
    idx, pos, target = 0, 0, None
    for i, w in enumerate(words):
        p = question.find(w, pos)
        if p == -1:
            break
        pos = p + len(w)
        if p <= start < pos or p < end <= pos:
            target = i
            break
        if p > start:
            target = max(0, i - 1)
            break
    if target is None:
        return False
    lo = max(0, target - _LEGAL_CONTEXT_WINDOW)
    hi = min(len(words), target + _LEGAL_CONTEXT_WINDOW + 1)
    return bool(_LEGAL_CONTEXT_RE.search(" ".join(words[lo:hi])))


# Refusal message used whenever a clinical question is detected.
CLINICAL_REFUSAL = (
    "this question asks for clinical/medical advice, which is out of "
    "scope — this assistant covers regulatory and administrative "
    "questions only"
)


def check_clinical_question(question: str) -> tuple[bool, str]:
    """Fail if the question asks for clinical / medical advice.

    The bare word "treatment" does NOT trigger when it appears in a
    legal/rights context (within ~6 words of right / refuse / emergency /
    offence / penalty) — those questions are regulatory, not clinical."""
    if not question:
        return True, ""
    for m in _CLINICAL_RE.finditer(question):
        if _TREATMENT_RE.fullmatch(m.group(0)) and _in_legal_context(
            question, m.start(), m.end()
        ):
            continue  # legal-context "treatment": not a clinical question
        return False, CLINICAL_REFUSAL
    return True, ""


# ---------------------------------------------------------------------------
# 4. In-corpus check
# ---------------------------------------------------------------------------
# How this differs from check_retrieval_confidence:
#   * check_retrieval_confidence looks at the SINGLE best match — if the
#     closest chunk is close enough, the retriever "recognises" the
#     question's topic.
#   * check_within_corpus counts how MANY chunks are within the distance
#     threshold. It fails when only one (or zero) chunks are even
#     remotely close — a hallmark of queries about topics entirely
#     outside the corpus (tax, immigration, unrelated clinical
#     questions). This catches "near-miss" queries where the closest
#     chunk is coincidentally semi-related but there is no real
#     supporting evidence in the corpus.
def check_within_corpus(
    retrieved_chunks: list[dict],
    min_relevant_chunks: int = 1,
    max_distance_threshold: float = 0.8,
) -> tuple[bool, str]:
    """Fail if fewer than `min_relevant_chunks` chunks are plausibly
    close to the question."""
    if not retrieved_chunks:
        return False, "question appears to be outside the scope of the available documents"
    close = sum(
        1 for c in retrieved_chunks
        if float(c.get("distance", float("inf"))) <= max_distance_threshold
    )
    if close < min_relevant_chunks:
        return False, ("question appears to be outside the scope of the "
                       "available documents")
    return True, ""


# ---------------------------------------------------------------------------
# 5. Orchestrator
# ---------------------------------------------------------------------------
_CHECKS = [
    ("check_clinical_question",    lambda q, c, a: check_clinical_question(q)),
    ("check_retrieval_confidence", lambda q, c, a: check_retrieval_confidence(c)),
    ("check_within_corpus",        lambda q, c, a: check_within_corpus(c)),
    ("check_citation_required",    lambda q, c, a: check_citation_required(a)),
]


def apply_guardrails(
    question: str,
    retrieved_chunks: list[dict],
    answer_text: str,
) -> dict:
    """Run all guardrails and return a structured decision dict."""
    refusal_reasons: list[str] = []
    triggered: list[str] = []

    for name, fn in _CHECKS:
        try:
            passed, msg = fn(question, retrieved_chunks, answer_text)
        except Exception as e:
            passed, msg = False, f"{name} raised an error: {type(e).__name__}: {e}"
        if not passed:
            refusal_reasons.append(msg)
            triggered.append(name)

    return {
        "allowed": len(refusal_reasons) == 0,
        "refusal_reasons": refusal_reasons,
        "triggered_checks": triggered,
    }


# ---------------------------------------------------------------------------
# Self-tests when run directly
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Helper to build fake chunk lists quickly
    def chunks(dists):
        return [
            {"chunk_id": f"c{i}", "doc_id": "doc", "doc_title": "Doc",
             "section_label": "Section 1", "text": "...", "distance": d}
            for i, d in enumerate(dists)
        ]

    scenarios = [
        (
            "1. CLEAN PASS — good retrieval, proper citation, non-clinical",
            "What does HEFAMAA require for facility registration?",
            chunks([0.25, 0.40, 0.55, 0.62, 0.70]),
            "Facilities must register annually [HEFAMAA Quick Guide, Register Facility].",
        ),
        (
            "2. CLINICAL QUESTION — antibiotic dosage",
            "What is the correct antibiotic dosage for treating a staph infection in a 70kg adult?",
            chunks([1.40, 1.45, 1.48, 1.52, 1.60]),
            "I don't have enough information in the provided documents to answer this.",
        ),
        (
            "3. POOR RETRIEVAL DISTANCES — all far above threshold",
            "How do I file an immigration work permit for a foreign doctor?",
            chunks([1.20, 1.25, 1.30, 1.33, 1.40]),
            "I don't have enough information in the provided documents to answer this.",
        ),
        (
            "4. MISSING CITATION — answer looks plausible but has no [x, y] cite",
            "What fees must data controllers pay to NDPC?",
            chunks([0.20, 0.35, 0.60, 0.75, 0.85]),
            "Data controllers must pay registration fees according to their category tier.",
        ),
        (
            "5. GOOD RETRIEVAL + CLINICAL — clinical keyword in question despite "
            "good hits (e.g. asks about clinical 'treatment' regulation)",
            "What regulations govern treatment of patient data during diagnosis?",
            chunks([0.30, 0.45, 0.60, 0.70, 0.78]),
            "The NDPA sets out principles for processing health data [NDPA 2023, Part V].",
        ),
        (
            "6. EVERYTHING PASSES EXCEPT CITATION — well-retrieved, non-clinical, "
            "multiple close chunks, but answer text is just plain prose",
            "How does the Vulnerable Group Fund get disbursed?",
            chunks([0.18, 0.32, 0.45, 0.60, 0.72]),
            "The Vulnerable Group Fund is disbursed according to a prescribed formula.",
        ),
    ]

    for label, q, c, a in scenarios:
        result = apply_guardrails(q, c, a)
        status = "ALLOWED" if result["allowed"] else "BLOCKED"
        print(f"\n--- Scenario {label} ---")
        print(f"  Decision: {status}")
        if result["triggered_checks"]:
            for name, reason in zip(result["triggered_checks"], result["refusal_reasons"]):
                print(f"    [{name}]  {reason}")
        else:
            print("    (all checks passed)")
