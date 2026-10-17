# v1 scoring sheet — rubric and instructions

`v1_scoring_sheet.csv` is generated from `eval_results/b1_v1.csv` (the clean
50-question run of 2026-10-16) by `scripts/build_scoring_sheet.py`. Every
column except one is computed mechanically from committed artefacts. **Do not
edit the computed columns.** To regenerate, always pass `--preserve-scores`:
it carries the human scores across by id and refuses to write a sheet that
would lose one (the bare script will not overwrite scored rows).

## The human column

`groundedness_score` is a human judgement: read the answer, compare it to the
retrieved chunks named in the same row (`eval_results/b1_v1.csv` with the
same `id` carries `retrieved_chunk_ids`), and score 0–1 using the rubric
below. **It has now been scored for all 18 answers shown to the user on the
v1 run (mean 0.794).** A blank score means unscored — never zero — and
`run_eval.py` excludes blanks from both numerator and denominator while
reporting the coverage beside the mean, so a partial sheet cannot pass as a
full one. The scores were assigned by a single human grader; there is no
second-grader agreement number.

One score is recorded as an open question rather than a settled number:
Q22's **0.7** sits exactly on the band boundary below (the rubric overlaps
at 0.70). Q22 is the corpus-gap question whose funding half is grounded in
the Act's Part VII and whose accountability half extrapolates from a
recovered section heading of the guidance whose body was never OCR'd; a
stricter reading of the 0.60–0.70 band ("partly grounded, includes inferred
claims") would score it lower, a more lenient reading of the 0.70–0.95 band
("a plausible detail not in the retrieved chunks") would score it higher.
The published 0.794 mean includes Q22 at 0.7; moving Q22 alone within the
0.60–0.80 range would move the mean by about ±0.01.

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

## Known corpus gaps (Q20–Q21; Q22 is half a gap)

Q20 and Q21 ask about the NHIA Operational Guidelines body, whose source
pages were never recovered by OCR (the PDF is a CamScanner capture). They
are marked `gold_in_corpus: false` in `data/gold_chunks.json` and have no
gold chunks, so they are excluded from recall/precision/MRR but still count
toward `grounded_answer_rate`. Both were correctly refused on the v1 run
and belong in the refusal-correctness counts, not the over-refusal counts.

Q22 straddles the gap and was treated accordingly. Its funding half is
answered by the Act's own Part VII — recovered text — so Q22 now carries
one graded gold chunk (`nhia_act_2022#0075`, evidence "The Authority shall
apply the Funds at its disposal", verified verbatim) and is included in the
retrieval metrics, which is why `gold_questions` reads 23 rather than 22.
Its accountability half still depends on guidance pages that were never
recovered; on the v1 run the model answered that half from a recovered
section heading, so `notes/failure_modes.md` counts Q22 in the over-answer
class on a corpus-gap question — it is neither a correct refusal (it was
answered) nor a clean answer (half of it is not in the corpus). The
groundedness score of 0.7 for Q22 is flagged above as an open question, not
a settled number.
