# Changelog

## v1.1.0 (2026-10-17)

**B1 v1.1.0 — the post-audit fix release: corrected claims, a scored groundedness column, and a CI that passes on a bare clone.**

Supersedes the numbers published under v1.0.0 (below): every v1.0.0
metric claim affected by this release is restated here. The run CSV itself
(`eval_results/b1_v1.csv`, the frozen evidence) is byte-identical to the
v1.0.0 run — no question was re-asked, no answer was edited.

### What changed in the numbers, and why

- **Citation correctness 0.648 → 0.907 (49/54).** The citation parser was
  splitting multi-comma document titles at the first comma
  ("National Health Insurance Authority Act, 2022" was parsed as title
  "National Health Insurance Authority Act"). It now resolves titles
  against `data/sources.json` before any split. This is a measurement
  fix, not a behaviour fix: 14 of the 19 previously-missing citations were
  the parser's own error. The 5 real misses (Q1, Q6, Q16, Q24) are
  genuine retrieval gaps, listed per question in the failure register;
  one of them (Q16) is a chunk-label truncation artefact that makes the
  metric overcount by one, and it is left that way rather than tuned.
- **Recall@5 0.351 → 0.379, MRR 0.466 → 0.454, gold questions 22 → 23.**
  Q22's question had two halves; its funding half is answered by the
  NHIA Act's own Part VII, which is recovered text the retriever did
  surface at rank 5. That chunk (`nhia_act_2022#0075`) is now a graded
  gold chunk with verbatim evidence. Retrieval did not change; the gold
  set gained the half of the question the corpus actually contains.
- **Per-claim groundedness: scored, mean 0.794 over 18 of 18 shown
  answers.** The human scoring column, blank in v1.0.0, is filled against
  the rubric in `eval_results/v1_scoring_sheet.md`. Blank means unscored,
  never zero; refusals are judged by refusal correctness instead of being
  averaged in as 0; the coverage is printed beside the mean. The sheet is
  joined into metrics only for the run whose answer texts it was written
  against (`SCORED_RUN_PREFIX`) — a score judges one answer, not a
  question id, and the original-30 recompute correctly reports NOT
  SCORED rather than borrowing scores from other answers.
- **Q22's 0.7 score is flagged as an open question**, not settled: it
  sits exactly on the rubric's 0.60/0.70 band boundary, and the report
  records both readings.

### What changed in the classification

The shown-answer taxonomy gained a fourth bucket,
`unclassified_refusal_candidate`: an off-script refusal (no mandated
sentence, no citation, not an answer) now fails loudly instead of being
silently counted as a refusal. Unit-tested in `tests/test_classifier.py`
(three buckets asserted, plus neutrality: the fourth bucket moves zero
rows of the frozen run) and wired into CI.

### Q20–Q22, stated once and correctly

Q20 and Q21 ask about NHIA guidance pages that were never recovered by
OCR and were correctly refused. Q22 straddles the gap: answered on the
grounded funding half, extrapolated on the accountability half from a
recovered section heading, scored 0.7 by hand, and counted in the
failure register as an **over-answer on a corpus-gap question** — not
folded into an average, not relabelled a refusal.

### CI and reproducibility

- The first CI run failed: `render_results.py --check` needed the built
  corpus, which a bare clone does not have. The renderer is now
  corpus-free (diversity counts parse doc ids from the run CSV itself;
  citation matching uses a label index built from committed artefacts).
  CI now passes on **both matrix legs (3.10, 3.12)**, including the
  drift check, the self-tests, and the new classifier tests — on a bare
  clone.
- A second sterile stranger test (2026-10-17, fresh GitHub clone of the
  fixed head, empty `data/` directories): **20 min 7 s**, 0 manual steps,
  **8/8 content-verified**, 1,218 chunks, self-tests green, `--check`
  green. Full log and the pre-merge audit's 403 findings in
  `docs/reproduction_log.md`.

### New human-task scaffolding

`scripts/spotcheck_gold.py` (seeded gold-audit worksheet for the second
human pass), `docs/loom_script.md` (demo shot list; video not recorded),
`docs/GITHUB_SETTINGS.md` (manual repo settings; gh unavailable),
`docs/method_note_public.md` (plain-language companion).

### Licence

MIT. Copyright © 2026 Okoliko Emmanuel Agama.

---

## v1.0.0 (2026-10-16) — superseded by v1.1.0

**B1 v1.0.0 — reproducible corpus, calibrated guardrails, measured retrieval evaluation.**

This release is what was found, including what could not be fixed. The numbers below come from one clean 50-question run of the committed harness (`eval_results/b1_v1.csv`, zero retries, zero excluded rows) and are regenerable by a third party. **Metric claims corrected by v1.1.0: recall@5 0.351 (now 0.379, Q22 gold added), citation correctness 0.648 (now 0.907, parser fix), groundedness NOT YET SCORED (now scored, 0.794 over 18/18), "Q20–Q22 correct refusals" (now Q20–Q21 refused, Q22 half-answered).**

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
