# Changelog

## v1.0.0 (2026-10-16)

**B1 v1.0.0 — reproducible corpus, calibrated guardrails, measured retrieval evaluation.**

This release is what was found, including what could not be fixed. The numbers below come from one clean 50-question run of the committed harness (`eval_results/b1_v1.csv`, zero retries, zero excluded rows) and are regenerable by a third party.

### What the metrics are

- **Hallucination rate 0.000 (0/25) and refusal correctness 1.000 (25/25)** — measured on 25 synthetic unanswerable questions. This is a floor with 4-point resolution, not a guarantee. Before guardrails intercepted them, the raw model produced two fabricated answers (Q27, Q48); both were caught by the clinical-question check before display.
- **Grounded answer rate 0.720 (18/25)** — the fraction of answerable questions whose displayed answer carries at least one inline citation.
- **Median latency 7.48 s, mean 1,493 tokens per call** — on a rate-limited free-tier LLM endpoint.

### What the metrics are not

- **Recall@5 = 0.351 (n=22) is the real headline.** Document-level hit rate reads 1.000 (25/25) but that metric is saturated and hides the defect: passage-level retrieval fails to surface the graded gold chunk in the top five on 7 of 22 answerable questions (Q3, Q5, Q8, Q10, Q11, Q14, Q16). This is the largest measured defect and is unfixed.
- **Citation correctness is 0.648 (35/54)** — nineteen inline citations in ten displayed answers point at something not in the retrieved context. This is measured, published, and not yet enforced at runtime.
- **Per-claim groundedness is NOT YET SCORED** (`eval_results/v1_scoring_sheet.csv`, column intentionally blank pending a human second pass).

### Corpus limitation

The NHIA Operational Guidelines 2023 is a CamScanner capture whose body was never recovered by OCR. Q20–Q22 are therefore correct refusals on a documented corpus gap, not product failures — and the NHIA guidance's front matter outranks its parent Act on those questions. Eight of eight corpus PDFs are content-verified with a sha256 lockfile; 1,218 section-aware chunks (700 chars, 100 overlap).

### Limitations list

1. 50 questions; the unanswerable half is synthetic by design.
2. Gold chunks are agent-graded with every evidence string verified verbatim, but not yet audited by a second human grader.
3. Retrieval diversity cap engaged on 46/50 questions (`embed_store.MAX_PER_DOC = 3`), which is working as designed but may be suppressing useful recall.
4. Rank is unstable between an Act and its sibling guidance document on 19 of 50 questions, in both directions.
5. Evaluation ran against a rate-limited free-tier endpoint; the harness retries with jitter and supports `--resume`, but a production SLA is not claimed.
6. No compliance claim is made, by this software or this release, about any facility or jurisdiction.

### Reproducibility

A stranger test from a fresh clone of `b1-remediation` completed one documented command sequence with zero manual steps in **21 minutes 7 seconds** (8/8 documents verified, 1,218 chunks). `bash scripts/build.sh` then `python run_eval.py --prefix b1_v1 --strict --resume` then `python analysis/render_results.py` regenerate every table in this file.

### Fixed in this release

- Resume-crash CSV loss (final post-loop write of the full row set).
- Guardrail over-refusal: zero on all 50 questions, against a pre-calibration threshold of 0.80 that would have false-failed Q7 and Q15 and let Q45 through.
- Diversity-cap violations (>3 chunks from one document): zero.
- README, architecture note, method note, and failure-modes register rewritten so every prose claim matches the code and the committed data; tables are now generated, with a `--check` drift guard in CI.

### Licence

MIT. Copyright © 2026 Okoliko Emmanuel Agama.
