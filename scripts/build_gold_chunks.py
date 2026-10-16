#!/usr/bin/env python3
"""
build_gold_chunks.py
====================
Generate data/gold_chunks.json — the chunk-level relevance set for the 30
questions in data/golden_set_30.json.

How this was graded (read this before trusting the file):

  1. data/processed/all_chunks.json was iterated directly, with
     scripts/search_chunks.py. The retriever (query_store) was never used —
     a gold set pulled from the retriever would grade the system on whether
     it retrieves what it already retrieves.
  2. For every gold chunk the grader recorded a short ANCHOR phrase copied
     out of that chunk's own text. This script asserts `anchor in chunk_text`
     and expands the anchor into a 40-200 char evidence window taken
     verbatim from the chunk. No evidence string in the output is typed by
     hand, so nothing in it can be a paraphrase.
  3. A chunk is gold only when it contains the information needed to answer
     the question, not when it merely mentions the topic. Where the answer is
     genuinely absent from the corpus, the question is recorded with
     gold_in_corpus=false and a reason instead of a forced match.

Output: data/gold_chunks.json, validated by scripts/validate_gold_chunks.py.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_PATH = ROOT / "data" / "processed" / "all_chunks.json"
GOLDEN_PATH = ROOT / "data" / "golden_set_30.json"
OUT_PATH = ROOT / "data" / "gold_chunks.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# The grading table: question id -> list of (chunk_id, anchor) gold pairs.
# The anchors are copied verbatim from the chunks they point at.
# ---------------------------------------------------------------------------
GOLD: dict[int, list[tuple[str, str]]] = {
    # --- HEFAMAA quick guide --------------------------------------------
    1: [
        ("hefamaa_requirements#0001",
         "required to register to operate their facilities every year"),
        ("hefamaa_requirements#0005",
         "must be scanned and uploaded as provided in the portal"),
        ("hefamaa_requirements#0008",
         "Current Tax Clearance Certificate"),
        ("hefamaa_requirements#0012",
         "Payment should be made to the bank account details stated on the invoice"),
        ("hefamaa_requirements#0014",
         "A physical inspection is carried out on first-time applications"),
    ],
    2: [
        ("hefamaa_requirements#0005",
         "must be scanned and uploaded as provided in the portal"),
        ("hefamaa_requirements#0008",
         "CAC Registration Certificate"),
        ("hefamaa_requirements#0010",
         "Scan all the credentials for each professional into one PDF document"),
        ("hefamaa_requirements#0011",
         "The maximum file size for each upload is 200KB"),
    ],
    3: [
        ("hefamaa_requirements#0004",
         "Facility Types 1. Hospital 2. Clinic 3. Eye Clinic"),
    ],
    # --- MLSCN national guidelines --------------------------------------
    4: [
        ("mlscn_guidelines#0014",
         "One room (5mx6m) or (16.4ft x19.7ft)"),
    ],
    5: [
        ("mlscn_guidelines#0017",
         "under the following twelve (12) clauses"),
        ("mlscn_guidelines#0046",
         "the following ten (10) clauses"),
    ],
    6: [
        ("mlscn_guidelines#0020",
         "must be registered member of MLSCN"),
        ("mlscn_guidelines#0037",
         "managed by a licensed Medical Laboratory Scientist certified by the Medical Laboratory Science Council of Nigeria"),
    ],
    # --- National Health Act 2014 ---------------------------------------
    7: [
        ("national_health_act_2014#0048",
         "shall not refuse a person emergency medical treatment for any reason"),
    ],
    8: [
        ("national_health_act_2014#0120",
         "means a health establishment that is not owned or controlled by an organ of state"),
        ("national_health_act_2014#0039",
         "The Certificate of Standards referred to in subsection (1) of this section may be obtained by application"),
    ],
    9: [
        ("national_health_act_2014#0010",
         "The National Health System shall include"),
        ("national_health_act_2014#0011",
         "ensure the development of national health policy and Issue guidelines"),
    ],
    # --- Nigeria Data Protection Act 2023 -------------------------------
    10: [
        ("ndpa_2023#0051",
         "data processing shall be lawful, where"),
        ("ndpa_2023#0052",
         "for the performance of a contract to which the data subject is a party"),
    ],
    11: [
        ("ndpa_2023#0074",
         "A data subject has the right to obtain from a data controller"),
        ("ndpa_2023#0076",
         "a commonly used electronic format"),
        ("ndpa_2023#0077",
         "the erasure of personal data concerning the data subject, without undue delay"),
        ("ndpa_2023#0078",
         "A data subject shall have the right to withdraw, at any time, consent"),
    ],
    12: [
        ("ndpa_2023#0092",
         "shall not transfer or permit personal data to be transferred from Nigeria"),
        ("ndpa_2023#0094",
         "A level of protection is adequate for the purposes of this section"),
        ("ndpa_2023#0097",
         "In the absence of adequacy of protection under section"),
        ("ndpa_2023#0098",
         "shall only transfer personal data from Nigeria to another country if the"),
        ("ndpa_2023#0099",
         "transfer is necessary for important reasons of public interest"),
    ],
    13: [
        ("ndpa_2023#0083",
         "shall implement appropriate technical and organisational measures to ensure the security, integrity and confidentiality of personal data"),
        ("ndpa_2023#0084",
         "pseudonymisation or other methods of de-identification of personal data"),
        ("ndpa_2023#0085",
         "regular testing, assessing, and evaluation of the effectiveness of the measures"),
        ("ndpa_2023#0087",
         "within 72 hours of becoming aware of a breach"),
    ],
    # --- NDPC guidance notice 2024 --------------------------------------
    14: [
        ("ndpc_guidance_2024#0013", "the amount payable is N250,000"),
        ("ndpc_guidance_2024#0014", "the amount payable is N100,000"),
        ("ndpc_guidance_2024#0015", "the amount payable is N10,000"),
        ("ndpc_guidance_2024#0016",
         "over Two-Hundred (200) data subjects but less than One-Thousand (1000)"),
    ],
    15: [
        ("ndpc_guidance_2024#0005",
         "Processes the personal data of more than Two-Hundred (200) data subjects in six (6) months"),
        ("ndpc_guidance_2024#0014",
         "over Five -Thousand (5,000) data subjects in six (6) months"),
        ("ndpc_guidance_2024#0015",
         "over One-Thousand (1,000) data subjects but less than Five -Thousand (5,000)"),
        ("ndpc_guidance_2024#0016",
         "over Two-Hundred (200) data subjects but less than One-Thousand (1000) within six (6) months"),
    ],
    16: [
        ("ndpc_guidance_2024#0007",
         "The Commission classifies data controllers and data processors into three (3) levels"),
        ("ndpc_guidance_2024#0013",
         "Specific Types of Data Controllers and Data Processors and their Fees"),
    ],
    # --- NHIA Act 2022 --------------------------------------------------
    17: [
        ("nhia_act_2022#0009",
         "There is established the National Health Insurance Authority"),
        ("nhia_act_2022#0010",
         "The objects of the Authority are to"),
        ("nhia_act_2022#0011",
         "promote, support and collaborate with States through State health insurance schemes"),
    ],
    18: [
        ("nhia_act_2022#0050",
         "the Authority shall implement the Basic Health Care Provision Fund as set out in the National Health Act"),
        ("nhia_act_2022#0052",
         "States health schemes shall be responsible for disbursements, management of the Basic Health Care Provision Fund"),
        ("nhia_act_2022#0053",
         "There is established the Vulnerable Group Fund"),
        ("nhia_act_2022#0058",
         "Contributions from the Federal Government for vulnerable persons shall be made from the Basic Health Care Provision Fund"),
    ],
    19: [
        ("nhia_act_2022#0037",
         "every person resident in Nigeria shall be required to obtain health insurance"),
    ],
    # --- WHO laboratory quality handbook --------------------------------
    23: [
        ("who_lab_quality_guidance#0021",
         "organized into an understandable and workable structure"),
        ("who_lab_quality_guidance#0029",
         "all 12 quality system essentials must be addressed"),
        ("who_lab_quality_guidance#0035",
         "based on 12 quality system essentials"),
    ],
    24: [
        ("who_lab_quality_guidance#0432",
         "Occurrence management is a central part of continual improvement"),
        ("who_lab_quality_guidance#0433",
         "An occurrence is any event that has a negative impact on an organization"),
        ("who_lab_quality_guidance#0441",
         "A cycle of events reflects the process of occurrence management"),
    ],
    25: [
        ("who_lab_quality_guidance#0491",
         "once the forms are used to record information, they become records"),
        ("who_lab_quality_guidance#0493",
         "In order to develop laboratory documents, it is important to understand each of these elements"),
        ("who_lab_quality_guidance#0499",
         "A laboratory is required to have a quality manual for ISO accreditation"),
    ],
}

# ---------------------------------------------------------------------------
# Questions whose answer is genuinely not in the corpus.
# ---------------------------------------------------------------------------
NOT_IN_CORPUS: dict[int, str] = {
    20: ("The NHIA Operational Guidelines 2023 are a 22-page CamScanner "
         "capture whose OCR sidecar stops at the table of contents, "
         "foreword and abbreviations. 'CSHIS' occurs only as a heading in "
         "that table of contents; there is no definition, target population "
         "or financing text anywhere in the corpus."),
    21: ("Same corpus gap as Q20. 'HIUOR' appears only as an abbreviation-"
         "list expansion ('Health Insurance Under OneRoof') in the OCR "
         "sidecar, with no explanation of the scheme."),
    22: ("Same corpus gap as Q20. 'FUNDINGFORTHEAUTHORITY' and "
         "'ACCOUNTABILITYMECHANISM' exist only as table-of-contents "
         "headings; the sections themselves were never recovered by OCR."),
}

NOTES: dict[int, str] = {
    1: ("Five separate requirements spread across the user guide: annual "
        "registration, letter of intent, documentary uploads, payment of the "
        "invoiced fee, and physical inspection of first-time applications."),
    2: ("Letter of intent (#0005), the UPLOAD DOCUMENTS list (#0008), "
        "professional credentials as one PDF each (#0010) and the 200KB "
        "per-file limit (#0011)."),
    3: "Single chunk listing all 20 registered facility types.",
    4: "One room of 5m x 6m (16.4ft x 19.7ft) is the primary-level minimum.",
    5: ("#0017 says twelve (12) clauses and lists them. #0046 is the "
        "appendix restatement and says 'ten (10)' while listing twelve — an "
        "inconsistency in the source document, kept as gold because it "
        "restates the same list."),
    6: ("Head of laboratory must be an experienced, MLSCN-registered "
        "Medical Laboratory Scientist (#0020, #0037); a certified technician "
        "may manage a primary lab only where scientists are unavailable, "
        "under supervision."),
    7: ("Section 10 duty plus the N100,000 / six-month penalty. The "
        "'reasonable cause' exception is defined in the interpretation "
        "section (#0120) but is not needed to state the right."),
    8: ("Classification lives in the interpretation section (private vs "
        "public health establishment); the standard is the Certificate of "
        "Standards required before operating."),
    9: ("Section 2(2) enumerates the members of the National Health System; "
        "section 3 lists the Federal Ministry of Health's functions."),
    10: ("Section 25(1): consent, then the five necessity grounds. "
         "Sensitive-data bases (section 30) are a separate list and were "
         "not counted as gold for this question."),
    11: ("Right to confirmation/information (#0074), a copy in a commonly "
         "used electronic format (#0076), rectification/erasure/"
         "restriction (#0077) and withdrawal of consent plus objection "
         "(#0078)."),
    12: ("Section 41 (no transfer without adequacy or a section 43 "
         "condition, and the basis must be recorded), section 42 "
         "(adequacy) and section 43 (the six alternative conditions)."),
    13: ("Section 39: appropriate technical and organisational measures "
         "plus the risk factors and the enumerated measures; section 40 "
         "adds processor-to-controller notification and the 72-hour "
         "notification to the Commission."),
    14: ("Registration fees by class: UHL N250,000, EHL N100,000, OHL "
         "N10,000. The separate N5,000 per-processor activity fee in "
         "paragraph 7 is not a registration fee and is not gold."),
    15: ("General designation threshold is >200 data subjects in six "
         "months (#0005); the class thresholds are >5,000 (UHL), "
         "1,000-5,000 (EHL) and 200-1,000 (OHL)."),
    16: "The three levels are named in #0007 and restated in #0013.",
    17: ("Establishment (#0009), objects (#0010) and the functions list "
         "that runs into #0011."),
    18: ("Section 24 implements the BHCPF; section 25(2)(a) makes the "
         "BHCPF a source of the Vulnerable Group Fund; #0052 puts "
         "disbursement and monitoring on the states; #0058 covers "
         "federal contributions for vulnerable persons."),
    19: "Section 14(1)-(2): mandatory for every resident, with the resident categories.",
    23: ("CLSI quality management system model, compatible with ISO 15189, "
         "built on the 12 quality system essentials."),
    24: ("Definition (#0432), what counts as an occurrence (#0433) and the "
         "investigate-correct-verify cycle (#0441)."),
    25: ("Documents vs records (#0491), the policy/process/procedure "
         "hierarchy (#0493) and the ISO-required quality manual (#0499)."),
    # --- Unanswerable questions (expected behaviour: refuse) ------------
    26: ("Clinical dosing advice. Out of scope by design: the corpus is "
         "regulatory and is expected to contain no antibiotic dosing. "
         "No gold chunks — a refusal is the correct behaviour."),
    27: ("Clinical diagnostic advice. Out of scope by design; the corpus "
         "contains no diagnostic algorithms. Refusal is correct."),
    28: ("Clinical prescribing advice. Out of scope by design. Refusal is "
         "correct."),
    29: ("Nigerian tax law, which is outside this corpus even though HMOs "
         "are a health-sector topic — the near-miss trap for a naive "
         "retriever. Refusal is correct."),
    30: ("Immigration and work-permit rules, outside the corpus. Refusal "
         "is correct."),
}


def _anchor_pattern(anchor: str) -> "re.Pattern[str]":
    """Anchors are typed from the console rendering of a chunk, so the chunk
    text may hold line breaks where the anchor has spaces. Match on any
    run of whitespace instead of a literal space."""
    return re.compile(r"\s+".join(re.escape(part) for part in anchor.split()))


def expand_evidence(text: str, anchor: str) -> str:
    """Return a 40-200 char verbatim window of `text` covering `anchor`."""
    match = _anchor_pattern(anchor).search(text)
    if match is None:
        raise AssertionError(f"anchor not found in chunk: {anchor!r}")
    idx, end = match.span()
    matched = text[idx:end]
    if len(matched) >= 40:
        window = matched if len(matched) <= 200 else matched[:200]
    else:
        centre = idx + len(matched) // 2
        start = max(0, centre - 60)
        end = min(len(text), start + 140)
        start = max(0, end - 140)
        window = text[start:end].strip()
        # snap outward to word boundaries without losing the anchor
        if start > 0:
            space = window.find(" ")
            if 0 < space < 20:
                window = window[space + 1:]
        if end < len(text):
            last_space = window.rfind(" ")
            if last_space > len(window) - 20:
                window = window[:last_space]
    assert _anchor_pattern(anchor).search(window), (anchor, window)
    assert 40 <= len(window) <= 200, (len(window), window)
    return window


def main() -> None:
    chunks = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    by_id = {c["chunk_id"]: c for c in chunks}
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    out = []
    for entry in golden:
        qid = int(entry["id"])
        record = {
            "id": qid,
            "question": entry["question"],
            "expected_doc_id": entry.get("expected_doc_id"),
            "gold_in_corpus": qid in GOLD,
            "gold_chunks": [],
            "graded_by": "agent",
            "note": NOTES.get(qid, NOT_IN_CORPUS.get(qid, "")),
        }
        for chunk_id, anchor in GOLD.get(qid, []):
            chunk = by_id.get(chunk_id)
            if chunk is None:
                raise SystemExit(f"Q{qid}: unknown chunk {chunk_id}")
            if _anchor_pattern(anchor).search(chunk["text"]) is None:
                raise AssertionError((qid, chunk_id, anchor))
            record["gold_chunks"].append({
                "chunk_id": chunk_id,
                "doc_id": chunk["doc_id"],
                "section_label": chunk["section_label"],
                "evidence": expand_evidence(chunk["text"], anchor),
            })
        if qid in NOT_IN_CORPUS and qid in GOLD:
            raise SystemExit(f"Q{qid} is both gold and not-in-corpus")
        out.append(record)

    OUT_PATH.write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    gold_q = sum(1 for r in out if r["gold_in_corpus"])
    n_chunks = sum(len(r["gold_chunks"]) for r in out)
    print(f"Wrote {OUT_PATH}")
    print(f"  questions: {len(out)} ({gold_q} with gold chunks, "
          f"{len(out) - gold_q} not in corpus)")
    print(f"  gold chunk entries: {n_chunks}")


if __name__ == "__main__":
    main()
