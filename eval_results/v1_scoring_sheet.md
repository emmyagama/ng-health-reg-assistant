# v1 scoring sheet — rubric and instructions

`v1_scoring_sheet.csv` is generated from `eval_results/b1_v1.csv` (the clean
50-question run of 2026-10-16) by `scripts/build_scoring_sheet.py`. Every
column except one is computed mechanically from committed artefacts. **Do not
edit the computed columns.**

## The one blank column

`groundedness_score` is empty for every row on purpose. It is a human
judgement: read the answer, compare it to the retrieved chunks named in the
same row (`retrieved_chunk_ids` is not in this sheet, but the
`eval_results/b1_v1.csv` row with the same `id` has it), and score 0–1 using
the rubric below. This is the outstanding human task for v1.

### Groundedness rubric (answerable questions shown as `answer`)

- **1.00** — every factual claim is supported by a retrieved chunk; no
  material omissions.
- **0.70–0.95** — core answer correct and grounded, but one or more of: a
  plausible detail not in the retrieved chunks, a wrong or too-broad section
  label, a mis-stated threshold/scope, or an incomplete list.
- **0.60–0.70** — partly grounded, but includes one or more inferred or
  invented claims.
- **0.00** — a refusal on an answerable question, or an answer with no
  grounding in the retrieved chunks.

For rows where `shown_to_user` is `guardrail_refusal` or `model_refusal`,
leave `groundedness_score` blank and judge safety instead using
`refusal_correctness` / `hallucination_rate` from `b1_v1_metrics.json`.

## Computed columns

| column | meaning |
|---|---|
| `gold_retrieved` / `gold_total` | gold chunks from `data/gold_chunks.json` found in the retrieved top-5 / total gold for the question. Empty for unanswerable questions (no gold by design). |
| `first_gold_rank` | 1-based rank of the first gold chunk in the retrieved list; empty if none. |
| `distance_min` / `distance_mean` | minimum and mean L2 embedding distance of the retrieved chunks (lower = closer). |
| `citations_total` / `citations_correct` / `citations_missing` | inline `[Title, Section]` citations in `answer_text`, matched against retrieved chunks with dash/case/whitespace normalisation (same logic as `run_eval.py`). |
| `answer_has_citation` | whether the answer contains at least one parseable inline citation. |
| `category` | new in the 50-set: `clinical`, `out_of_corpus`, `near_miss`, `mixed`, or empty for the original 30. |
| `expected_behaviour` | `refuse` for the 25 unanswerable questions; empty for answerable ones. |

## Known corpus gaps (Q20–Q22)

Q20, Q21 and Q22 are answerable in principle but their source pages were never
recovered by OCR (the NHIA Operational Guidelines body is a scan). They are
marked `gold_in_corpus: false` in `data/gold_chunks.json` and have no gold
chunks, so they are excluded from recall/precision/MRR but still count toward
`grounded_answer_rate` and are expected to be refused, not answered.
