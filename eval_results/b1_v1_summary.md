# Evaluation Summary — 'b1_v1' run

- Golden set: `golden_set_50.json` (50 questions; 25 answerable, 25 unanswerable)
- Retrieval configuration: top-5 chunks (chunk size 700 chars, overlap 100)
- Rows completed in this invocation: 9 (41 carried forward by --resume)
- Retries performed: 0
- **Rows excluded from every average: 0** (status != ok) — 0 generation error(s), 0 retrieval error(s), 0 with no retrieved chunks
- **Average latency over 50 ok rows:** 6.48 s (median 7.48 s)
- **Average tokens (in + out) over ok rows:** 1493
- **Retrieval accuracy (top-5 document hit, answerable questions):** 25/25 = 100.0%
- What reached the user: 18× answer, 23× guardrail_refusal, 9× model_refusal

## Retrieval quality

Computed over the questions with gold chunks in `data/gold_chunks.json` (22 of 50; the rest are out of corpus or unanswerable by design).

| metric | value | definition |
|--------|-------|------------|
| recall@5 | **0.351** | mean over questions of (gold chunks in top-5) / (gold chunks for that question) |
| context_precision@5 | **0.173** | mean over questions of (retrieved chunks that are gold) / 5 |
| MRR | **0.466** | mean over questions of 1 / (rank of first gold chunk) |
| document-level hit rate (old metric) | **25/25** | answerable questions whose expected document appears anywhere in the top-5 — saturated, kept for comparison |

## Answer quality

| metric | value | over |
|--------|-------|------|
| grounded_answer_rate | **0.720** | 25 answerable questions |
| refusal_correctness | **1.000** | 25 unanswerable questions |
| hallucination_rate | **0.000** | 25 unanswerable questions |
| citation_correctness | **0.648** | 54 inline citations in answers shown to the user |
| citation_target_missing | **19** | citations pointing at something not in the retrieved context |

What reached the user, by verdict: 18× answer, 23× guardrail_refusal, 9× model_refusal

Machine-readable copy of every number above: `eval_results/b1_v1_metrics.json`.

## Per-question quick view

| id | status | answerable | retrieval_hit | shown_to_user | latency_s | retries | answer preview |
|----|--------|------------|---------------|---------------|-----------|---------|----------------|
| 1 | ok | True | TRUE | answer | 1.75 | 0 | HEFAMAA requires that every health‑care operator in Lagos State **register (or renew) its ... |
| 2 | ok | True | TRUE | answer | 1.18 | 0 | A scanned, hand‑written “Letter of Intent” addressed to the Commissioner of Health must be... |
| 3 | ok | True | TRUE | model_refusal | 0.92 | 0 | I don't have enough information in the provided documents to answer this.... |
| 4 | ok | True | TRUE | answer | 1.48 | 0 | A primary‑level medical laboratory must have at least one room measuring **5 m × 6 m** (ap... |
| 5 | ok | True | TRUE | model_refusal | 0.92 | 0 | I don't have enough information in the provided documents to answer this.... |
| 6 | ok | True | TRUE | answer | 1.46 | 0 | A medical laboratory in Nigeria must be managed by a **licensed Medical Laboratory Scienti... |
| 7 | ok | True | TRUE | answer | 1.17 | 0 | Nigerian law guarantees that no health‑care provider, health worker or health establishmen... |
| 8 | ok | True | TRUE | answer | 7.64 | 0 | Health establishments are classified by regulation of the Minister into categories that re... |
| 9 | ok | True | TRUE | answer | 11.35 | 0 | The “national health system” is defined as the system within the Federal structure of Nige... |
| 10 | ok | True | TRUE | model_refusal | 10.97 | 0 | I don't have enough information in the provided documents to answer this.... |
| 11 | ok | True | TRUE | model_refusal | 10.05 | 0 | I don't have enough information in the provided documents to answer this.... |
| 12 | ok | True | TRUE | answer | 7.91 | 0 | Cross‑border transfers of personal data are generally prohibited unless the transfer meets... |
| 13 | ok | True | TRUE | answer | 13.50 | 0 | Data controllers must put in place appropriate technical and organisational measures to sa... |
| 14 | ok | True | TRUE | model_refusal | 11.25 | 0 | I don't have enough information in the provided documents to answer this.... |
| 15 | ok | True | TRUE | answer | 9.58 | 0 | A data controller (or processor) is deemed of major importance when it processes the perso... |
| 16 | ok | True | TRUE | answer | 10.62 | 0 | The NDPC classifies “major” data controllers and processors into three groups:  1. Those t... |
| 17 | ok | True | TRUE | answer | 14.49 | 0 | The National Health Insurance Authority (NHIA) is a statutory body created by the National... |
| 18 | ok | True | TRUE | answer | 13.92 | 0 | The Basic Health Care Provision Fund is a fund created by the National Health Act to finan... |
| 19 | ok | True | TRUE | answer | 12.16 | 0 | Yes. Under the National Health Insurance Authority Act, every person resident in Nigeria i... |
| 20 | ok | True | TRUE | model_refusal | 8.89 | 0 | I don't have enough information in the provided documents to answer this.... |
| 21 | ok | True | TRUE | guardrail_refusal | 12.41 | 0 | I don't have enough information in the provided documents to answer this.... |
| 22 | ok | True | TRUE | answer | 11.28 | 0 | The National Health Insurance Authority (NHIA) is created as a corporate body with perpetu... |
| 23 | ok | True | TRUE | answer | 13.45 | 0 | The WHO‑endorsed quality management system model for laboratories is built around **twelve... |
| 24 | ok | True | TRUE | answer | 6.60 | 0 | Occurrence management is a core element of laboratory quality management that enables cont... |
| 25 | ok | True | TRUE | answer | 11.55 | 0 | A medical laboratory must keep all quality‑related policies, procedures, the quality manua... |
| 26 | ok | False | N/A | guardrail_refusal | 9.31 | 0 | I don't have enough information in the provided documents to answer this.... |
| 27 | ok | False | N/A | guardrail_refusal | 11.51 | 0 | To confirm acute malaria when a rapid diagnostic test is not being used, the laboratory sh... |
| 28 | ok | False | N/A | guardrail_refusal | 9.98 | 0 | I don't have enough information in the provided documents to answer this.... |
| 29 | ok | False | N/A | guardrail_refusal | 8.50 | 0 | I don't have enough information in the provided documents to answer this.... |
| 30 | ok | False | N/A | model_refusal | 10.29 | 0 | I don't have enough information in the provided documents to answer this.... |
| 31 | ok | False | N/A | guardrail_refusal | 8.54 | 0 | I don't have enough information in the provided documents to answer this.... |
| 32 | ok | False | N/A | guardrail_refusal | 6.15 | 0 | I don't have enough information in the provided documents to answer this.... |
| 33 | ok | False | N/A | guardrail_refusal | 7.21 | 0 | I don't have enough information in the provided documents to answer this.... |
| 34 | ok | False | N/A | guardrail_refusal | 8.24 | 0 | I don't have enough information in the provided documents to answer this.... |
| 35 | ok | False | N/A | guardrail_refusal | 7.31 | 0 | I don't have enough information in the provided documents to answer this.... |
| 36 | ok | False | N/A | guardrail_refusal | 3.21 | 0 | I don't have enough information in the provided documents to answer this.... |
| 37 | ok | False | N/A | guardrail_refusal | 1.44 | 0 | I don't have enough information in the provided documents to answer this.... |
| 38 | ok | False | N/A | guardrail_refusal | 1.20 | 0 | I don't have enough information in the provided documents to answer this.... |
| 39 | ok | False | N/A | guardrail_refusal | 0.97 | 0 | I don't have enough information in the provided documents to answer this.... |
| 40 | ok | False | N/A | guardrail_refusal | 1.00 | 0 | I don't have enough information in the provided documents to answer this.... |
| 41 | ok | False | N/A | guardrail_refusal | 2.12 | 0 | I don't have enough information in the provided documents to answer this.... |
| 42 | ok | False | N/A | guardrail_refusal | 1.64 | 0 | I don't have enough information in the provided documents to answer this.... |
| 43 | ok | False | N/A | guardrail_refusal | 1.07 | 0 | I don't have enough information in the provided documents to answer this.... |
| 44 | ok | False | N/A | model_refusal | 1.20 | 0 | I don't have enough information in the provided documents to answer this.... |
| 45 | ok | False | N/A | model_refusal | 1.68 | 0 | I don't have enough information in the provided documents to answer this.... |
| 46 | ok | False | N/A | guardrail_refusal | 1.41 | 0 | I don't have enough information in the provided documents to answer this.... |
| 47 | ok | False | N/A | guardrail_refusal | 0.88 | 0 | I don't have enough information in the provided documents to answer this.... |
| 48 | ok | False | N/A | guardrail_refusal | 2.43 | 0 | A hospital must first secure a **freely‑given, informed consent** from the patient before ... |
| 49 | ok | False | N/A | guardrail_refusal | 0.66 | 0 | I don't have enough information in the provided documents to answer this.... |
| 50 | ok | False | N/A | guardrail_refusal | 9.75 | 0 | I don't have enough information in the provided documents to answer this.... |
