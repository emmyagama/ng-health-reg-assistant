# Evaluation Summary — 'after_guardrails' run

- Golden set: `golden_set_30.json` (30 questions; 25 answerable, 5 unanswerable)
- **Retrieval accuracy (top-5 hit on answerable questions):** **25/25 = 100.0%**
- **Average end-to-end latency:** 0.17 seconds
- **Average total tokens (in + out):** 97

Groundedness and hallucination rate require manual review — see the `answer_text` and `retrieved_sections` columns in `after_guardrails.csv`.

## Per-question quick view

| id | answerable | retrieval_hit | latency_s | answer preview |
|----|------------|---------------|-----------|----------------|
| 1 | True | TRUE | 1.88 | HEFAMAA requires that a health‑facility operator first **register (or renew) the facility ... |
| 2 | True | TRUE | 3.22 | A scanned, hand‑written “Letter of Intent” addressed to the Commissioner of Health must be... |
| 3 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 4 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 5 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 6 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 7 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 8 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 9 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 10 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 11 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 12 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 13 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 14 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 15 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 16 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 17 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 18 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 19 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 20 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 21 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 22 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 23 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 24 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 25 | True | TRUE | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 26 | False | N/A | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 27 | False | N/A | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 28 | False | N/A | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 29 | False | N/A | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
| 30 | False | N/A | 0.00 | [GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): Error code: 429 - {'error': {'... |
