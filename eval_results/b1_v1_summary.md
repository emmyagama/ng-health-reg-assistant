# Evaluation Summary — 'b1_v1' run

- Golden set: `golden_set_50.json` (50 questions; 25 answerable, 25 unanswerable)
- Retrieval configuration: top-5 chunks (chunk size 700 chars, overlap 100)
- Source: recomputed offline from `b1_v1.csv` by `run_eval.py --recompute-only` (no API call made)
- Retries recorded in the CSV: 0
- **Rows excluded from every average: 0** (status != ok)
- What reached the user: 18× answer, 23× guardrail_refusal, 9× model_refusal

## Retrieval quality

| metric | value | definition |
|--------|-------|------------|
| recall@5 | **0.379** | mean over 23 questions with gold |
| context_precision@5 | **0.174** | mean |
| MRR | **0.454** | mean |
| document-level hit rate (old metric) | **25/25** | saturated |

## Answer quality

| metric | value | over |
|--------|-------|------|
| grounded_answer_rate | **0.720** | 25 answerable |
| refusal_correctness | **1.000** | 25 unanswerable |
| hallucination_rate | **0.000** | 25 unanswerable |
| citation_correctness | **0.907** | 54 inline citations |
| citation_target_missing | **5** | citations not in the retrieved set |
| groundedness (faithfulness of shown answers) | **0.794** | mean over the 18 of 18 shown answers scored by hand (0 unscored, never zeros); the remaining 7 of 25 answerable questions were refused — see grounded_answer_rate |

Machine-readable copy: `eval_results/b1_v1_metrics.json`.
