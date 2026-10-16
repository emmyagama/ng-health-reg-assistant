# Evaluation Summary — 'b1_v1_g30' run

- Golden set: `golden_set_30.json` (30 questions; 25 answerable, 5 unanswerable)
- Retrieval configuration: top-5 chunks (chunk size 700 chars, overlap 100)
- Source: recomputed offline from `b1_v1_g30.csv` by `run_eval.py --recompute-only` (no API call made)
- Retries recorded in the CSV: 0
- **Rows excluded from every average: 0** (status != ok)
- What reached the user: 17× answer, 5× guardrail_refusal, 8× model_refusal

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
| grounded_answer_rate | **0.680** | 25 answerable |
| refusal_correctness | **1.000** | 5 unanswerable |
| hallucination_rate | **0.000** | 5 unanswerable |
| citation_correctness | **0.898** | 49 inline citations |
| citation_target_missing | **5** | citations not in the retrieved set |
| groundedness (faithfulness of shown answers) | **NOT SCORED for this run — the human sheet is written against the 'b1_v1' run's answer texts and is not attributed to other runs** | not attributed across runs |

Machine-readable copy: `eval_results/b1_v1_g30_metrics.json`.
