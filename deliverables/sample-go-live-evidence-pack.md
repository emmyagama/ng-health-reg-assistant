# Sample Go-Live Evidence Pack — Meridian Health Systems

**Prepared for:** Meridian Health Systems
**Scope of measurement:** retrieval-grounded question answering over a fixed, hand-selected corpus of eight public Nigerian health-regulation documents, split into 1,218 section-aware passages (700 characters, 100 overlap).
**Measurement window:** single clean end-to-end run, 2026-10-16, 50 questions, no retries outstanding, zero rows excluded from any average.
**Format note:** this pack is Markdown. No PDF renderer (pandoc, wkhtmltopdf, weasyprint) was available in the delivery environment; the Markdown is the authoritative artefact.

---

## 1. Executive summary (≤150 words)

The retrieval layer is the weakest link and is measured as such. Document-level hit rate reads 100% (25/25) but that metric is saturated and hides the real number: chunk-level recall@5 against a graded gold set is **0.351** and MRR is **0.466** (n=22). Passage-level retrieval, not the model, is what costs answers.

The safety layer held. On 25 deliberately unanswerable questions the system refused all 25 (**refusal correctness 1.000, hallucination rate 0.000, n=25**). Before guardrails were applied, the raw model produced 2 fabricated answers (Q27, Q48); both were intercepted by the clinical-question check before display. Citation correctness is **0.648** (35 of 54 inline citations point at something in the retrieved context) — measured, published, and not yet enforced at runtime.

Two things are honestly not done: per-claim groundedness is unscored (`NOT YET SCORED — human review pending`), and the NHIA Operational Guidelines body was never recovered by OCR, so Q20–Q22 are correct refusals on a corpus gap.

---

## 2. One-page scorecard

Every number is generated from committed artefacts by `analysis/render_results.py` and traceable to a row in `eval_results/b1_v1.csv`. `n` is stated for every cell.

| Metric | Value | n | Source |
|---|---|---|---|
| recall@5 | 0.351 | 22 | `eval_results/b1_v1_metrics.json` |
| context precision@5 | 0.173 | 22 | `eval_results/b1_v1_metrics.json` |
| MRR | 0.466 | 22 | `eval_results/b1_v1_metrics.json` |
| document-level hit rate (old, saturated) | 1.000 (25/25) | 25 | `eval_results/b1_v1_metrics.json` |
| citation correctness | 0.648 (35/54) | 54 citations | `eval_results/b1_v1_metrics.json` |
| grounded answer rate | 0.720 (18/25) | 25 | `eval_results/b1_v1_metrics.json` |
| refusal correctness | 1.000 (25/25) | 25 | `eval_results/b1_v1_metrics.json` |
| hallucination rate (shown to user) | 0.000 (0/25) | 25 | `eval_results/b1_v1_metrics.json` |
| hallucination rate (raw model, pre-guardrails) | 0.080 (2/25) | 25 | `eval_results/b1_v1.csv` (Q27, Q48) |
| median end-to-end latency | 7.48 s | 50 | `eval_results/b1_v1.csv` |
| mean tokens per call (in + out) | 1,493 | 50 | `eval_results/b1_v1.csv` |
| per-claim groundedness | **NOT YET SCORED — human review pending** | — | `eval_results/v1_scoring_sheet.csv` (column blank by design) |

Side-by-side on the original 30-question set (`eval_results/b1_v1_g30_metrics.json`, n=30): recall@5 0.351 (n=22), citation correctness 0.633 (31/49), grounded answer rate 0.680 (17/25), refusal correctness 1.000 (5/5), hallucination rate 0.000 (0/5). Retrieval numbers are identical because retrieval is deterministic and the questions Q1–Q30 are unchanged.

---

## 3. Failure register (counted, generated)

Source: the generated block in `notes/failure_modes.md`, which reads `eval_results/b1_v1.csv`. Each class carries its count and the question ids so any claim can be opened against a row.

| Layer | Class | Count | Question ids |
|---|---|---|---|
| retrieval | gold chunk outside top-5 (answerable, has gold) | 7 | Q3, Q5, Q8, Q10, Q11, Q14, Q16 |
| retrieval | diversity-cap violation (>3 chunks from one document) | 0 | none |
| retrieval | cap engaged (exactly 3 chunks from one document) | 46 | (not enumerated) |
| answer | over-refusal by a guardrail (answerable, in corpus) | 0 | none |
| answer | over-refusal by the model itself (answerable, in corpus) | 5 | Q3, Q5, Q10, Q11, Q14 |
| answer | refusal of a documented corpus-gap question (expected) | 2 | Q20, Q21 |
| answer | correct refusal (unanswerable) | 25 | Q26–Q50 |
| answer | visible hallucination (unanswerable, answer shown) | 0 | none |
| answer | raw hallucination caught before display | 2 | Q27, Q48 |
| answer | citation target missing (≥1 citation not in the retrieved set) | 10 | Q1, Q6, Q7, Q9, Q16, Q17, Q18, Q19, Q22, Q24 |

Two additional patterns are counted in `notes/failure_modes.md` and restated here because they are the mechanisms behind the numbers above:

- **Act ↔ Guidance rank flips:** on 19 of 50 questions, an Act and its sibling guidance document both appear in the top five. The rank order is not stable in either direction (the Act outranks its guidance on 8 questions; the guidance outranks the Act on 11). The dangerous instance is Q20–Q22, where the NHIA guidance wins top ranks on front matter alone because its body was never recovered by OCR.
- **Front-matter / TOC dilution:** 9 of 50 questions have at least one retrieved chunk shorter than 200 characters in their top five. Heading-quality guards removed most TOC ghost-headings; what survives is concentrated on the scanned Acts.

---

## 4. Fix list, ranked by risk

| Rank | Fix | What it unblocks | How it is verified |
|---|---|---|---|
| 1 | Passage-level retrieval (raise INTERNAL_FETCH_K before the diversity cap; or section-label-aware re-ranking; or a hard filter that never lets front-matter chunks occupy a slot) | The 7 gold-miss questions (Q3, Q5, Q8, Q10, Q11, Q14, Q16) and, through them, most of the 5 model over-refusals. This is the single largest measured defect. | Re-run `python run_eval.py --prefix b1_v1 --strict --resume`; recall@5 and the gold-miss count in the failure register move or they do not. |
| 2 | Citation-target verification at runtime (after generation, confirm each [Title, Section] appears in the retrieved set; strip or re-prompt on a miss) | The 19 citations in 10 displayed answers that currently point outside the provided context (citation correctness 0.648). | Citation correctness rises toward 1.0 on the same run; `citations_missing` in `b1_v1_metrics.json` falls. |
| 3 | Acquire a text-complete copy of the NHIA Operational Guidelines 2023 (the current PDF is a CamScanner capture whose body was never recovered) | Q20–Q22 become answerable instead of correct refusals; the Act ↔ Guidance front-matter failure on that pair disappears. | `data/gold_chunks.json` gains gold chunks for Q20–Q22; `validate_gold_chunks.py` passes; the corpus-gap refusal class in the failure register drops to 0. |
| 4 | Human second pass on the gold chunks (currently agent-graded with every evidence string verified verbatim, but not audited by a second grader) | Raises the trustworthiness of every retrieval metric built on the gold set. | A second grader's disagreements are recorded; metrics are recomputed against the audited set. |
| 5 | Score the `groundedness_score` column in `eval_results/v1_scoring_sheet.csv` | Closes the last unmeasured number in the scorecard. | The column is no longer blank; the rubric in `v1_scoring_sheet.md` was applied by a human reader. |

---

## 5. Method note (short form)

- **Gold set.** 50 hand-built questions: 25 answerable, 25 unanswerable across four strata (clinical, out-of-corpus, near-miss, mixed). The unanswerable half is synthetic by design, because a question the documents cannot answer is where a chatbot is most tempted to invent.
- **Gold chunks.** For the 25 answerable questions, the chunk(s) that actually contain the answer were graded by an AI agent; every evidence string was verified as a verbatim substring of its chunk by `scripts/validate_gold_chunks.py`. Not yet audited by a second human.
- **What recall@5 does and does not capture.** It measures whether the graded gold chunks appear in the retrieved top five. It does not measure whether the model used them correctly, whether a non-gold chunk also contained a usable answer, or whether the gold grading itself is complete.
- **Citation correctness.** An inline `[Title, Section]` citation is correct when its normalised (dash, case, whitespace) title+section matches a retrieved chunk, with a section-substring fallback. It catches citations pointing outside the provided context; it does not judge whether a matched citation supports the adjacent claim.
- **Groundedness rubric.** 1.0 = every factual claim supported by a retrieved chunk; 0.70–0.95 = correct and grounded with a minor omission or a mis-scoped detail; 0.60–0.70 = partly grounded with one or more inferred claims; 0.0 = refusal on an answerable question or no grounding at all. The column is blank because it requires a human reading each answer.
- **Honest limitations.** 50 questions; synthetic unanswerables; agent-graded gold; groundedness not yet scored; evaluation on a rate-limited free-tier LLM endpoint, with retries and `--resume` in the harness. A 0% hallucination rate on 25 synthetic unanswerable questions is a floor with 4-point resolution, not a guarantee.

---

## 6. Evidence index

| Claim in this pack | Committed file | Where |
|---|---|---|
| recall@5 = 0.351, n=22 | `eval_results/b1_v1_metrics.json` | `retrieval.recall_at_k` |
| context precision@5 = 0.173, MRR = 0.466 | `eval_results/b1_v1_metrics.json` | `retrieval.context_precision_at_k`, `retrieval.mrr` |
| document-level hit rate = 25/25 | `eval_results/b1_v1_metrics.json` | `retrieval.document_level_hits` / `document_level_answerable` |
| citation correctness = 0.648 (35/54) | `eval_results/b1_v1_metrics.json` | `answers.citation_correctness`, `citations_correct`/`citations_total` |
| grounded answer rate = 0.720 (18/25) | `eval_results/b1_v1_metrics.json` | `answers.grounded_answer_rate` |
| refusal correctness = 1.000 (25/25), hallucination = 0.000 | `eval_results/b1_v1_metrics.json` | `answers.refusal_correctness`, `answers.hallucination_rate` |
| raw hallucination = 2/25 (Q27, Q48) | `eval_results/b1_v1.csv` | rows id=27, id=48; `shown_to_user` ≠ answer while `answer_text` is substantive |
| median latency 7.48 s, mean tokens 1,493 | `eval_results/b1_v1.csv` | `latency_seconds`, `input_tokens`+`output_tokens` over 50 rows |
| every failure-register count and question id | `notes/failure_modes.md` | generated block between `BEGIN/END GENERATED: failure-counts` markers |
| threshold 0.70, both distributions, the sweep, the Q45/Q7/Q15 caveat | `eval_results/threshold_calibration.md` | whole file; regenerable via `scripts/calibrate_thresholds.py` |
| groundedness rubric and the blank column | `eval_results/v1_scoring_sheet.md`, `eval_results/v1_scoring_sheet.csv` | rubric section; `groundedness_score` column |
| stranger-test wall-clock (21 min 7 s, 0 manual steps, 1,218 chunks) | `docs/reproduction_log.md` | Phase 1 section |
| corpus integrity (8/8 content-verified, sha256 lockfile) | `data/corpus.lock.json`, `data/SOURCES_STATUS.md` | whole files |
| original-30 comparison numbers | `eval_results/b1_v1_g30_metrics.json` | whole file |
| the eval table in the README is generated, not typed | `analysis/render_results.py`, `README.md` | `--check` exits non-zero if the committed block is stale |

---

## 7. Out-of-scope statement

This pack is an evidence report, not legal advice, not a compliance opinion, not a certification, and not a guarantee of any future result. Nothing here should be read as a statement that any facility complies with any regulation. The measurement harness is delivered as-is; Meridian's engineers own any fixes, and the ranked fix list in §4 is a recommendation, not a commitment. No part of this engagement rebuilds the product, guarantees an improvement, or warrants that the measured rates will hold on a different corpus, a different model, or production traffic.

---

## 8. Reproducibility claim

A stranger test was performed from a fresh clone: one documented command sequence, zero manual steps, **21 minutes 7 seconds** wall-clock, ending in 8/8 content-verified documents and 1,218 chunks (`docs/reproduction_log.md`). On that basis:

> Every number in this pack can be regenerated from the delivered scripts by a third party in under 30 minutes — `bash scripts/build.sh` for the corpus and index, then `python run_eval.py --prefix b1_v1 --strict --resume` and `python analysis/render_results.py` for the tables — assuming a Groq API key on the free tier. The one number that cannot be regenerated by a machine is the per-claim groundedness score, which is marked `NOT YET SCORED` rather than estimated.
