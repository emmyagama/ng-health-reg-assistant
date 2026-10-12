# Evaluation Summary — 'after_retrieval' run

- Golden set: `golden_set_30.json` (30 questions; 25 answerable, 5 unanswerable)
- **Retrieval accuracy (top-5 hit on answerable questions):** **25/25 = 100.0%**
- **Average end-to-end latency:** 8.03 seconds
- **Average total tokens (in + out):** 1525

Groundedness and hallucination rate require manual review — see the `answer_text` and `retrieved_sections` columns in `after_retrieval.csv`.

## Per-question quick view

| id | answerable | retrieval_hit | latency_s | answer preview |
|----|------------|---------------|-----------|----------------|
| 1 | True | TRUE | 1.73 | HEFAMAA requires that every health‑care operator in Lagos register (or renew) their facili... |
| 2 | True | TRUE | 1.22 | During the HEFAMAA registration process, the operator must upload a scanned, hand‑written ... |
| 3 | True | TRUE | 0.90 | I don't have enough information in the provided documents to answer this.... |
| 4 | True | TRUE | 1.39 | The guidelines require that a primary‑level medical laboratory have at least one room meas... |
| 5 | True | TRUE | 3.94 | I don't have enough information in the provided documents to answer this.... |
| 6 | True | TRUE | 1.26 | A medical laboratory in Nigeria must be managed by a **licensed Medical Laboratory Scienti... |
| 7 | True | TRUE | 1.26 | Under the National Health Act 2014, every health‑care provider, health worker or health es... |
| 8 | True | TRUE | 1.85 | Health establishments are classified by the Minister, who – by regulation – groups all est... |
| 9 | True | TRUE | 13.77 | The “national health system” is defined as the system within the Federal structure that de... |
| 10 | True | TRUE | 10.91 | I don't have enough information in the provided documents to answer this.... |
| 11 | True | TRUE | 8.15 | I don't have enough information in the provided documents to answer this.... |
| 12 | True | TRUE | 10.12 | Cross‑border transfers of personal data are tightly controlled under the Nigeria Data Prot... |
| 13 | True | TRUE | 9.45 | Data controllers must put in place appropriate technical and organisational measures to pr... |
| 14 | True | TRUE | 11.29 | A data controller of major importance must pay a N5,000 fee for each data processor it eng... |
| 15 | True | TRUE | 10.73 | A data controller (or processor) is deemed of major importance when it processes the perso... |
| 16 | True | TRUE | 8.01 | The NDPC classifies “data controllers or data processors of major importance” according to... |
| 17 | True | TRUE | 9.41 | The National Health Insurance Authority (NHIA) is a body corporate established by the Nati... |
| 18 | True | TRUE | 14.39 | The Basic Health Care Provision Fund is a fund created by the National Health Act 2014 to ... |
| 19 | True | TRUE | 14.40 | Yes. Under the National Health Insurance Authority Act, every person resident in Nigeria i... |
| 20 | True | TRUE | 8.86 | I don't have enough information in the provided documents to answer this.... |
| 21 | True | TRUE | 11.26 | I don't have enough information in the provided documents to answer this.... |
| 22 | True | TRUE | 8.85 | The NHIA’s funding is governed by the financial provisions of the 2022 Act, which require ... |
| 23 | True | TRUE | 11.99 | The WHO‑endorsed laboratory quality management system model organizes all laboratory activ... |
| 24 | True | TRUE | 9.62 | Occurrence management is a core element of laboratory quality management that drives conti... |
| 25 | True | TRUE | 8.51 | A medical laboratory must adopt a documented quality management system that complies with ... |
| 26 | False | N/A | 13.21 | I don't have enough information in the provided documents to answer this.... |
| 27 | False | N/A | 8.07 | To diagnose acute malaria without a rapid test you should rely on microscopic examination ... |
| 28 | False | N/A | 10.96 | I don't have enough information in the provided documents to answer this.... |
| 29 | False | N/A | 8.02 | I don't have enough information in the provided documents to answer this.... |
| 30 | False | N/A | 7.44 | I don't have enough information in the provided documents to answer this.... |
