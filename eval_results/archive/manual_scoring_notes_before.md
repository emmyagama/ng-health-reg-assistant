# Manual Scoring — `before` run

Source: `eval_results/before_guardrails_guardrails.csv` (run with stubs replaced by real embed_store + Groq).

> **PROVENANCE NOTE (added 2026-10-16, when these notes were archived):** the cited source file `before_guardrails_guardrails.csv` has never existed in this repository. The numbers in this file cannot be re-derived and are retained as historical human judgement only.

Scoring scale (applied to answerable questions only):

- **1.00** — every factual claim is supported by the cited chunk(s); no omissions that materially change the answer.
- **0.70–0.95** — core answer is correct and grounded, but the answer either: (a) adds a plausible-sounding detail not directly in the retrieved chunks, (b) cites a wrong/too-broad section label, (c) mis-states a threshold or scope, or (d) lists only a subset of the relevant items.
- **0.60–0.70** — part of the answer is well-grounded but also includes one or more claims that are inferred or invented rather than present in the retrieved text.
- **0.00** — model returned the standard "I don't have enough information…" refusal on an answerable question.

For **unanswerable** questions, `hallucinated` is marked `yes` only if the model produced a confident, on-topic answer rather than the refusal line.

## Results

- **Answerable questions:** 25
- **Retrieval accuracy (top-5):** 25/25 (100%) — per `before_guardrails_summary.md`
- **Average groundedness:** **0.71 / 1.0 (71.0%)**
- **Refusals on answerable questions:** **4/25 (16%)** — Q7, Q10, Q20, Q21. This matches the agent's flag; root cause is that the retriever returned chunks from the correct document but NOT from the section containing the answer (e.g. Q7 got repeated "NATIONAL HEALTH SYSTEM·" header chunks, not §20 Emergency treatment; Q10 got PART I/Application chunks but not §25 Lawful basis; Q20/Q21 got other NHIA-guideline pages instead of the CSHIS/HIUOR definitions). These are retrieval-precision failures, not generation failures — the model correctly refused rather than guessing.
- **Unanswerable questions:** 5
- **Hallucination rate (unanswerable):** **0/5 (0%)** — every out-of-scope question (antibiotic dosage, malaria diagnosis, pregnancy hypertension Rx, HMO corporate tax, immigration/visas) correctly produced the "I don't have enough information…" refusal. No fabricated answers.

## Per-question notes (flagged issues only)

| Q  | Issue                                                                                                                                         | Score |
|----|-----------------------------------------------------------------------------------------------------------------------------------------------|-------|
| 1  | Adds "physical inspection before approval" and "Provisional Certificate of Operation" flow — plausible but the retrieved HEFAMAA chunks shown cover only profile creation, dashboard and Letter of Intent steps; inspection/certificate steps are not in the retrieved context. | 0.75 |
| 2  | "Upload Payment evidence of payment (PDF)" after invoice generation — not in the retrieved chunks (which only mention the Letter of Intent). Likely true of the portal but not grounded in the retrieved passages. | 0.70 |
| 3  | Lists only 4 of 20 facility types (Maternity, Industrial, Mobile, Mortuary) — correct but very incomplete; the cited section "20. Mortuary" isn't the list itself. | 0.70 |
| 4  | "each of the required laboratory rooms must meet this 5m × 6m size" — wrong for primary labs (primary only requires ONE 5m×6m room). Core answer is right (5m × 6m single room) but the follow-on claim over-generalises. | 0.85 |
| 5  | 12 QSEs number is correct, but citation points to WHO handbook ("interpretation…") rather than MLSCN §4.0 — the QSE model comes from WHO/CLSI and is adopted by MLSCN, so the claim is true but the citation misattributes primary source. | 0.90 |
| 7  | Model refused. Top-5 retrieved chunks are all generic "NATIONAL HEALTH SYSTEM·" headers, not §20 Emergency treatment. Retrieval precision issue. | 0.00 |
| 9  | Federal Ministry of Health responsibility is correct; section citations are garbled ("NATIONAL HEALTH SYSTEM·") because OCR/section-detection produced noisy section labels for the scanned Act. | 0.80 |
| 10 | Model refused. Top-5 chunks included PART I/Application/§26 Consent but NOT §25 Lawful basis of processing. Retrieval precision issue. | 0.00 |
| 13 | Correctly cites 72-hour breach notification, high-risk public communication; but incorrectly cites "section 46(1)" for security obligations (§46 is Complaints/Investigations in PART X Enforcement; security is §39 in PART VII). Core facts right, citation wrong. | 0.70 |
| 14 | Two-fee structure (registration + per-processor) and N5,000 per-processor fee are correct; N250,000 UHL and N100,000 EHL values match the NDPC guidance's tier fee schedule — but the OHL N10,000 tier is omitted. Minor incompleteness. | 0.85 |
| 15 | "More than 200 subjects in six months" is correct for the ordinary-high threshold but the answer presents it as the only threshold; UHL/EHL thresholds (5,000/1,000) and sector-based designations are omitted. | 0.70 |
| 18 | Funding-source breakdown (1% CRF, donors, other) and the 50/20/15/10/5 earmarks align with the National Health Act 2014; disbursement via NPHCDA and state PHC Boards also correct. Answer correctly distinguishes BHCPF (created by NHA 2014) from its NHIA 2022 administration. | 0.90 |
| 20 | Model refused. Top-5 chunks pulled "2.9 PRIVATE HEALTH INSURANCE", "HEALTHCARE FACILITIES", "Definition:" etc., but not the CSHIS sub-sub-section. Retrieval precision issue. | 0.00 |
| 21 | Model refused. Same retrieval issue: generic NHIA-guideline pages returned, not the HIUOR/1.6 section. | 0.00 |
| 22 | Answer correctly points to NHIA Operational Guidelines §1.9 Funding and §1.10 Accountability Mechanism, but the retrieved_sections column shows the top chunk was actually labelled "2.2.1 Definition" — the section-labelling in the chunker is off by one (scanned TOC numbering). The "three-year tariff review" and "sanction" claims come from §3 of NHIA Act 2022, which IS in the retrieved chunks, but the "reviews every five years" claim isn't present in any retrieved chunk. | 0.60 |
| 25 | Cites "Chapter 14" for records-retention (occurrence management, not records). Core facts about document control and retention are correct; citation to chapter 14 is mis-attributed. | 0.90 |

All other answerable questions (5, 6, 8, 11, 12, 16, 17, 19, 23, 24) scored ≥0.85 with no material hallucinations.
