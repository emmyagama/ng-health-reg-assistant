# Evaluation Summary — 'before_guardrails' run

- Golden set: `golden_set_30.json` (30 questions; 25 answerable, 5 unanswerable)
- **Retrieval accuracy (top-5 hit on answerable questions):** **25/25 = 100.0%**
- **Average end-to-end latency:** 12.53 seconds
- **Average total tokens (in + out):** 2047

Groundedness and hallucination rate require manual review — see the `answer_text` and `retrieved_sections` columns in `before_guardrails.csv`.

## Per-question quick view

| id | answerable | retrieval_hit | latency_s | answer preview |
|----|------------|---------------|-----------|----------------|
| 1 | True | TRUE | 1.54 | HEFAMAA requires that a health‑facility operator first create a user profile with a unique... |
| 2 | True | TRUE | 1.27 | During registration the operator must upload a scanned, hand‑written Letter of Intent addr... |
| 3 | True | TRUE | 1.09 | HEFAMAA’s registration system includes a range of facility types, specifically Maternity C... |
| 4 | True | TRUE | 1.59 | The minimum space required for a primary‑level medical laboratory is a single room measuri... |
| 5 | True | TRUE | 11.58 | A medical laboratory must implement **12 Quality System Essentials** as required by the ML... |
| 6 | True | TRUE | 14.13 | The medical laboratory must be managed by a **licensed Medical Laboratory Scientist who is... |
| 7 | True | TRUE | 18.18 | I don't have enough information in the provided documents to answer this.... |
| 8 | True | TRUE | 13.40 | Health establishments are classified by the Minister through regulations that place every ... |
| 9 | True | TRUE | 15.57 | The National Health System is “the system within the Federal Republic of Nigeria, whether ... |
| 10 | True | TRUE | 11.24 | I don't have enough information in the provided documents to answer this.... |
| 11 | True | TRUE | 16.18 | Data subjects under the Nigeria Data Protection Act are entitled to a range of specific pr... |
| 12 | True | TRUE | 12.52 | Cross‑border transfers of personal data are prohibited unless the transfer meets one of tw... |
| 13 | True | TRUE | 17.24 | Data controllers must put in place appropriate technical and organisational measures that ... |
| 14 | True | TRUE | 15.54 | Data controllers of major importance must pay two separate fees when they register with th... |
| 15 | True | TRUE | 13.57 | A data controller (or processor) is deemed to be of “major importance” when it processes t... |
| 16 | True | TRUE | 12.13 | The NDPC classifies major data controllers and processors into three levels: Ultra‑High (U... |
| 17 | True | TRUE | 13.07 | The National Health Insurance Authority (NHIA) is a statutory body created under the Natio... |
| 18 | True | TRUE | 18.18 | The Basic Health Care Provision Fund (the “Fund”) is a statutory fund created by the Natio... |
| 19 | True | TRUE | 19.87 | Yes. The Act requires every person resident in Nigeria to obtain health insurance, making ... |
| 20 | True | TRUE | 11.61 | I don't have enough information in the provided documents to answer this.... |
| 21 | True | TRUE | 11.48 | I don't have enough information in the provided documents to answer this.... |
| 22 | True | TRUE | 11.48 | The NHIA’s governance of its own financing is set out in the NHIA Operational Guidelines 2... |
| 23 | True | TRUE | 16.38 | The WHO guidance describes the laboratory quality‑management system as a **whole‑system mo... |
| 24 | True | TRUE | 16.15 | Occurrence management is a core element of a laboratory’s quality‑management system, provi... |
| 25 | True | TRUE | 14.51 | A medical laboratory should maintain a formal document‑control programme that guarantees o... |
| 26 | False | N/A | 17.11 | I don't have enough information in the provided documents to answer this.... |
| 27 | False | N/A | 9.42 | I don't have enough information in the provided documents to answer this.... |
| 28 | False | N/A | 12.31 | I don't have enough information in the provided documents to answer this.... |
| 29 | False | N/A | 15.04 | I don't have enough information in the provided documents to answer this.... |
| 30 | False | N/A | 12.43 | I don't have enough information in the provided documents to answer this.... |
