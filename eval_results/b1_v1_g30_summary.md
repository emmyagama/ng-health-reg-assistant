# Evaluation Summary — 'b1_v1_g30' run

- Golden set: `golden_set_30.json` (30 questions; 25 answerable, 5 unanswerable)
- Retrieval configuration: top-5 chunks (chunk size 700 chars, overlap 100)
- Rows completed in this invocation: 30 (0 carried forward by --resume)
- Retries performed: 0
- **Rows excluded from every average: 0** (status != ok) — 0 generation error(s), 0 retrieval error(s), 0 with no retrieved chunks
- **Average latency over 30 ok rows:** 7.84 s (median 8.39 s)
- **Average tokens (in + out) over ok rows:** 1559
- **Retrieval accuracy (top-5 document hit, answerable questions):** 25/25 = 100.0%
- What reached the user: 17× answer, 5× guardrail_refusal, 8× model_refusal

## Retrieval quality

Computed over the questions with gold chunks in `data/gold_chunks.json` (22 of 30; the rest are out of corpus or unanswerable by design).

| metric | value | definition |
|--------|-------|------------|
| recall@5 | **0.351** | mean over questions of (gold chunks in top-5) / (gold chunks for that question) |
| context_precision@5 | **0.173** | mean over questions of (retrieved chunks that are gold) / 5 |
| MRR | **0.466** | mean over questions of 1 / (rank of first gold chunk) |
| document-level hit rate (old metric) | **25/25** | answerable questions whose expected document appears anywhere in the top-5 — saturated, kept for comparison |

## Answer quality

| metric | value | over |
|--------|-------|------|
| grounded_answer_rate | **0.680** | 25 answerable questions |
| refusal_correctness | **1.000** | 5 unanswerable questions |
| hallucination_rate | **0.000** | 5 unanswerable questions |
| citation_correctness | **0.633** | 49 inline citations in answers shown to the user |
| citation_target_missing | **18** | citations pointing at something not in the retrieved context |

What reached the user, by verdict: 17× answer, 5× guardrail_refusal, 8× model_refusal

Machine-readable copy of every number above: `eval_results/b1_v1_g30_metrics.json`.

## Per-question quick view

| id | status | answerable | retrieval_hit | shown_to_user | latency_s | retries | answer preview |
|----|--------|------------|---------------|---------------|-----------|---------|----------------|
| 1 | ok | True | TRUE | answer | 2.60 | 0 | HEFAMAA requires that a health facility first complete its annual registration (or renewal... |
| 2 | ok | True | TRUE | answer | 3.79 | 0 | During the HEFAMAA facility registration, you must scan and upload a hand‑written **Letter... |
| 3 | ok | True | TRUE | model_refusal | 1.13 | 0 | I don't have enough information in the provided documents to answer this.... |
| 4 | ok | True | TRUE | answer | 1.54 | 0 | The guidelines require each laboratory room to be at least 5 m × 6 m (≈ 16.4 ft × 19.7 ft)... |
| 5 | ok | True | TRUE | model_refusal | 5.38 | 0 | I don't have enough information in the provided documents to answer this.... |
| 6 | ok | True | TRUE | answer | 2.07 | 0 | A medical laboratory must be managed by a **licensed Medical Laboratory Scientist who is c... |
| 7 | ok | True | TRUE | answer | 3.56 | 0 | Under the National Health Act 2014, a health‑care provider, health worker or health establ... |
| 8 | ok | True | TRUE | answer | 2.69 | 0 | Health establishments are classified by the Minister, through regulations, into categories... |
| 9 | ok | True | TRUE | answer | 8.28 | 0 | The “national health system” is defined as the system within the Federal structure of Nige... |
| 10 | ok | True | TRUE | model_refusal | 10.36 | 0 | I don't have enough information in the provided documents to answer this.... |
| 11 | ok | True | TRUE | model_refusal | 6.77 | 0 | I don't have enough information in the provided documents to answer this.... |
| 12 | ok | True | TRUE | answer | 11.13 | 0 | Cross‑border transfers of personal data are tightly controlled. A data controller or proce... |
| 13 | ok | True | TRUE | answer | 9.84 | 0 | Data controllers must put in place “appropriate technical and organisational measures” to ... |
| 14 | ok | True | TRUE | model_refusal | 12.46 | 0 | I don't have enough information in the provided documents to answer this.... |
| 15 | ok | True | TRUE | answer | 4.58 | 0 | A data controller (or processor) is deemed of major importance when it processes the perso... |
| 16 | ok | True | TRUE | model_refusal | 14.35 | 0 | I don't have enough information in the provided documents to answer this.... |
| 17 | ok | True | TRUE | answer | 10.30 | 0 | The National Health Insurance Authority (NHIA) is a body corporate established by the Nati... |
| 18 | ok | True | TRUE | answer | 6.07 | 0 | The Basic Health Care Provision Fund is a fund created by the National Health Act to suppo... |
| 19 | ok | True | TRUE | answer | 15.02 | 0 | Yes. The National Health Insurance Authority Act 2022 states that “every person resident i... |
| 20 | ok | True | TRUE | model_refusal | 9.62 | 0 | I don't have enough information in the provided documents to answer this.... |
| 21 | ok | True | TRUE | guardrail_refusal | 12.24 | 0 | I don't have enough information in the provided documents to answer this.... |
| 22 | ok | True | TRUE | answer | 7.30 | 0 | The National Health Insurance Authority (NHIA) is created as a corporate body with perpetu... |
| 23 | ok | True | TRUE | answer | 9.89 | 0 | The WHO‑endorsed quality management system model for laboratories is organized around twel... |
| 24 | ok | True | TRUE | answer | 8.06 | 0 | Occurrence management is a core element of laboratory quality systems, serving as a centra... |
| 25 | ok | True | TRUE | answer | 9.83 | 0 | A medical laboratory must maintain a written set of quality‑related documents—such as a qu... |
| 26 | ok | False | N/A | guardrail_refusal | 8.50 | 0 | I don't have enough information in the provided documents to answer this.... |
| 27 | ok | False | N/A | guardrail_refusal | 8.79 | 0 | To confirm acute malaria when a rapid test is not available, the laboratory should examine... |
| 28 | ok | False | N/A | guardrail_refusal | 12.88 | 0 | I don't have enough information in the provided documents to answer this.... |
| 29 | ok | False | N/A | guardrail_refusal | 7.54 | 0 | I don't have enough information in the provided documents to answer this.... |
| 30 | ok | False | N/A | model_refusal | 8.66 | 0 | I don't have enough information in the provided documents to answer this.... |
