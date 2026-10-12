#!/usr/bin/env python3
"""
answer.py
=========
Generate a grounded, cited answer to a regulatory question using a Groq
chat model, given retrieved document chunks from embed_store.query_store().

Core function:
    generate_answer(question, retrieved_chunks, model=...) -> dict

The model is instructed (via system prompt) to:
  * answer ONLY from the provided context,
  * cite every factual claim as [Doc Title, Section Label] inline,
  * say "I don't have enough information in the provided documents to
    answer this" if the context doesn't cover the question.

Return dict keys:
    question, answer_text (post-guardrails, may be a refusal),
    model_answer_text (raw model output), citations_found,
    guardrails_allowed, guardrails_refusal_reasons,
    guardrails_triggered_checks, latency_seconds,
    input_tokens, output_tokens, model_used
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from guardrails import apply_guardrails

# ---------------------------------------------------------------------------
# Load env
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


# ---------------------------------------------------------------------------
# Citation regex
# ---------------------------------------------------------------------------
# Matches citations of the form   [Some Document Title, Section Label]
# The content inside brackets may contain letters, digits, spaces, hyphens,
# periods, apostrophes, parentheses and colons. CJK brackets 【…】 (and the
# full-width comma ，) are accepted as equivalents — the model occasionally
# emits them under low temperature.
# The bracket pair must not span across a period followed by a new sentence
# starting with a capital, but we keep the pattern permissive and let
# downstream cleaning handle it.
_CITATION_RE = re.compile(
    r"[\[【]"               # opening bracket (ASCII or CJK)
    r"([^\[\]【】\n]{3,200}?)" # citation body (no nested brackets / newlines)
    r"[,，]"                # comma separating title from section
    r"([^\[\]【】\n]{3,200}?)" # section label
    r"[\]】]",                # closing bracket (ASCII or CJK)
)


def _extract_citations(answer_text: str) -> list[dict]:
    """Return a list of {"doc_title", "section_label"} dicts for every
    [Title, Section] citation found in answer_text."""
    out = []
    for m in _CITATION_RE.finditer(answer_text):
        out.append({
            "doc_title": m.group(1).strip(),
            "section_label": m.group(2).strip(),
        })
    return out


# ---------------------------------------------------------------------------
# Core answer generation
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a precise regulatory Q&A assistant specialising in Nigerian "
    "health-sector law and guidance. You MUST follow these rules strictly:\n\n"
    "1. Answer ONLY using the information provided in the CONTEXT blocks "
    "below. Do not use outside knowledge or guesswork.\n"
    "2. After EVERY factual claim, cite its source inline in square brackets "
    "in exactly this form: [Document Title, Section Label]. Use the exact "
    "document title and section label printed at the top of each CONTEXT "
    "block. Example: 'HEFAMAA requires annual registration [HEFAMAA Quick "
    "Guide, Register Facility].'\n"
    "3. If a claim is supported by multiple sources you may cite several "
    "bracketed citations in a row: [Doc A, Section 1] [Doc B, Part II].\n"
    "4. If the CONTEXT does not contain enough information to answer the "
    "question, respond with exactly: "
    "\"I don't have enough information in the provided documents to answer "
    "this.\"\n"
    "5. If the question asks about fees, rates, amounts or tiers and the "
    "CONTEXT lists more than one, enumerate EVERY tier/fee with its exact "
    "naira (₦) amount — do not cite only one and omit the rest.\n"
    "6. Keep answers concise and well-structured (1–3 short paragraphs). "
    "Do NOT include a preamble or a references section beyond the inline "
    "citations.\n"
)


def _build_user_message(question: str, retrieved_chunks: list[dict]) -> str:
    """Render retrieved chunks + the question into a single user message."""
    parts = ["CONTEXT (use only these passages to answer):\n"]
    for i, chunk in enumerate(retrieved_chunks, start=1):
        title = chunk.get("doc_title", "Unknown")
        section = chunk.get("section_label", "")
        body = chunk.get("text", "").strip()
        parts.append(f"[{i}] DOCUMENT: {title}  |  SECTION: {section}")
        parts.append(body)
        parts.append("")  # blank line between chunks
    parts.append(f"QUESTION: {question}")
    parts.append("")
    parts.append("Answer the QUESTION using only the CONTEXT above, with "
                 "inline [Document Title, Section Label] citations after "
                 "every factual claim.")
    return "\n".join(parts)


def _build_guardrail_refusal(refusal_reasons: list[str]) -> str:
    """Render the user-facing refusal that replaces a blocked answer."""
    lines = [
        "I can't answer this question.",
        "",
        "This assistant only covers Nigerian health-sector regulation and "
        "administration. Reasons:",
    ]
    lines.extend(f"- {reason}" for reason in refusal_reasons)
    return "\n".join(lines)


def generate_answer(
    question: str,
    retrieved_chunks: list[dict],
    model: str = "openai/gpt-oss-120b",
) -> dict:
    """Call the Groq chat completions API with grounded context and return
    the answer + metadata.

    The model's raw output is passed through guardrails.apply_guardrails()
    (question, retrieved_chunks, answer_text). When a check fails the
    returned `answer_text` is replaced with a refusal that lists the
    refusal_reasons; the untouched model output stays in
    `model_answer_text`."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY not found in environment / .env file."
        )

    # Imported here so the module can still be imported for citation tests
    # without requiring the groq package to be installed.
    import groq
    from groq import Groq

    client = Groq(api_key=api_key)

    user_msg = _build_user_message(question, retrieved_chunks)

    start = time.perf_counter()
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,  # low temperature for factual groundedness
        )
    except groq.AuthenticationError as e:
        raise RuntimeError(f"Groq authentication failed: {e}") from e
    except groq.APIConnectionError as e:
        raise RuntimeError(f"Could not reach Groq API: {e}") from e
    except groq.APIStatusError as e:
        raise RuntimeError(f"Groq API error (HTTP {e.status_code}): {e.message}") from e

    latency = time.perf_counter() - start

    answer_text = completion.choices[0].message.content.strip()
    in_tokens = completion.usage.prompt_tokens
    out_tokens = completion.usage.completion_tokens

    decision = apply_guardrails(question, retrieved_chunks, answer_text)
    shown_text = answer_text
    if not decision["allowed"]:
        shown_text = _build_guardrail_refusal(decision["refusal_reasons"])

    return {
        "question": question,
        "answer_text": shown_text,
        "model_answer_text": answer_text,
        "citations_found": _extract_citations(shown_text),
        "guardrails_allowed": decision["allowed"],
        "guardrails_refusal_reasons": decision["refusal_reasons"],
        "guardrails_triggered_checks": decision["triggered_checks"],
        "latency_seconds": round(latency, 3),
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "model_used": model,
    }


# ---------------------------------------------------------------------------
# Citation regex self-tests (runnable directly)
# ---------------------------------------------------------------------------
def _run_citation_regex_tests() -> None:
    """Ad-hoc tests of citation detection — printed when this script is
    executed standalone with no real retrieval/API available."""
    test_cases = [
        (
            "well-formatted citation",
            "HEFAMAA requires annual registration "
            "[HEFAMAA Quick Guide, Register Facility] before operations begin.",
            True,  # expect detection
        ),
        (
            "no citation",
            "HEFAMAA requires annual registration before operations begin.",
            False,
        ),
        (
            "malformed citation (missing brackets)",
            "HEFAMAA requires annual registration "
            "HEFAMAA Quick Guide, Register Facility before operations begin.",
            False,
        ),
    ]
    print("--- Citation regex self-tests ---")
    for label, text, should_find in test_cases:
        cites = _extract_citations(text)
        found = len(cites) > 0
        status = "PASS" if found == should_find else "FAIL"
        print(f"  [{status}] {label}")
        print(f"          text:   {text[:100]}{'...' if len(text)>100 else ''}")
        print(f"          cites:  {cites}")
        print()


# ---------------------------------------------------------------------------
# __main__ demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # First run citation-regex self-tests (these need no API key).
    _run_citation_regex_tests()

    # Try to import the real retriever; fall back to fake chunks if that
    # fails (no embed_store built yet, no chroma DB, etc.).
    fake_fallback_used = False
    question = "What does HEFAMAA require for facility accreditation?"

    try:
        # NOTE: when integrating with the real pipeline, this import is the
        # normal path. We try it first so a genuine embed_store wins.
        from embed_store import query_store  # type: ignore
        chunks = query_store(question, n_results=5)
        if not chunks:
            raise RuntimeError("query_store returned empty results")
    except Exception as e:
        print(f"(embed_store unavailable: {type(e).__name__}: {e})")
        print("Falling back to 3 fake retrieved chunks for demo.\n")
        fake_fallback_used = True
        chunks = [
            {
                "chunk_id": "fake_001",
                "doc_id": "hefamaa_quickguide",
                "doc_title": "HEFAMAA Quick Guide",
                "section_label": "How it works - Register Facility",
                "text": (
                    "Operators of Healthcare Facilities in Lagos are, by law, "
                    "required to register their facilities every year. A complete "
                    "registration must be submitted through the e-HEFAMAA portal "
                    "along with a scanned Letter of Intent addressed to the "
                    "Commissioner of Health."
                ),
                "distance": 0.31,
            },
            {
                "chunk_id": "fake_002",
                "doc_id": "hefamaa_quickguide",
                "doc_title": "HEFAMAA Quick Guide",
                "section_label": "How it works - Facility Types",
                "text": (
                    "Registered facility types include hospitals, clinics, eye "
                    "clinics, diagnostic centres, dental clinics, dialysis centres, "
                    "medical laboratories, maternity centres, mortuaries and others."
                ),
                "distance": 0.63,
            },
            {
                "chunk_id": "fake_003",
                "doc_id": "mlscn_guidelines",
                "doc_title": "MLSCN National Guidelines",
                "section_label": "Section 4 - Quality System Requirements",
                "text": (
                    "Medical laboratories must develop and implement a quality "
                    "management system covering organisation, personnel, equipment, "
                    "process control and facility safety."
                ),
                "distance": 0.92,
            },
        ]

    print(f"Question: {question}")
    print(f"Using {'FAKE fallback' if fake_fallback_used else 'real retrieved'} "
          f"chunks ({len(chunks)}).\n")

    try:
        result = generate_answer(question, chunks)
        print("--- ANSWER ---")
        print(result["answer_text"])
        print()
        print(f"Citations detected: {len(result['citations_found'])}")
        for c in result["citations_found"]:
            print(f"  - [{c['doc_title']}, {c['section_label']}]")
        print(f"Latency: {result['latency_seconds']}s | "
              f"tokens in/out: {result['input_tokens']}/{result['output_tokens']} | "
              f"model: {result['model_used']}")
    except RuntimeError as e:
        print(f"\nAPI call skipped/failed (expected in this environment): {e}")
        print("The citation regex tests above already verified citation parsing.")
        sys.exit(0)
