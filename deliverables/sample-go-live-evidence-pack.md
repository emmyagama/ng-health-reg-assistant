# Sample Go-Live Evidence Pack — Meridian Health Systems

**Prepared for:** Meridian Health Systems
**Scope of measurement:** retrieval-grounded question answering over a fixed, hand-selected corpus of eight public Nigerian health-regulation documents, split into 1,218 section-aware passages (700 characters, 100 overlap).
**Measurement window:** single clean end-to-end run, 2026-10-16, 50 questions, no retries outstanding, zero rows excluded from any average.
**Format note:** this pack is Markdown. No PDF renderer (pandoc, wkhtmltopdf, weasyprint) was available in the delivery environment; the Markdown is the authoritative artefact.

---

## 1. Executive summary (≤150 words)

The retrieval layer is the weakest link and is measured as such. Document-level hit rate reads 100% (25/25) but that metric is saturated and hides the real number: chunk-level recall@5 against a graded gold set is **0.379** and MRR is **0.454** (n=23). Passage-level retrieval, not the model, is what costs answers.

The safety layer held. On 25 deliberately unanswerable questions the system refused all 25 (**refusal correctness 1.000, hallucination rate 0.000, n=25**). Before guardrails were applied, the raw model produced 2 fabricated answers (Q27, Q48); both were intercepted by the clinical-question check before display. Citation correctness is **0.907** (49 of 54 inline citations point at something in the retrieved context) — measured, published, and not yet enforced at runtime.

Per-claim groundedness is scored for every answer shown to the user: mean **0.794 over 18 of 18**. The NHIA Operational Guidelines body was never recovered by OCR: Q20–Q21 are correct refusals on that corpus gap, and Q22 is the half-answered case — grounded funding half, extrapolated accountability half, counted as an over-answer, with its 0.7 score flagged as an open question.

---

## 2. One-page scorecard

Every number is generated from committed artefacts by `analysis/render_results.py` and traceable to a row in `eval_results/b1_v1.csv`. `n` is stated for every cell.

| Metric | Value | n | Source |
|---|---|---|---|
| recall@5 | 0.379 | 23 | `eval_results/b1_v1_metrics.json` |
| context precision@5 | 0.174 | 23 | `eval_results/b1_v1_metrics.json` |
| MRR | 0.454 | 23 | `eval_results/b1_v1_metrics.json` |
| document-level hit rate (old, saturated) | 1.000 (25/25) | 25 | `eval_results/b1_v1_metrics.json` |
| citation correctness | 0.907 (49/54) | 54 citations | `eval_results/b1_v1_metrics.json` |
| grounded answer rate | 0.720 (18/25) | 25 | `eval_results/b1_v1_metrics.json` |
| refusal correctness | 1.000 (25/25) | 25 | `eval_results/b1_v1_metrics.json` |
| hallucination rate (shown to user) | 0.000 (0/25) | 25 | `eval_results/b1_v1_metrics.json` |
| hallucination rate (raw model, pre-guardrails) | 0.080 (2/25) | 25 | `eval_results/b1_v1.csv` (Q27, Q48) |
| per-claim groundedness | 0.794 | 18 of 18 shown answers scored by hand | `eval_results/v1_scoring_sheet.csv` |
| median end-to-end latency | 7.48 s | 50 | `eval_results/b1_v1.csv` |
| mean tokens per call (in + out) | 1,493 | 50 | `eval_results/b1_v1.csv` |

Side-by-side on the original 30-question set (`eval_results/b1_v1_g30_metrics.json`, n=30): recall@5 0.379 (n=23), citation correctness 0.898 (44/49), grounded answer rate 0.680 (17/25), refusal correctness 1.000 (5/5), hallucination rate 0.000 (0/5). Retrieval numbers are identical to the 50-set run because retrieval is deterministic and the questions Q1–Q30 are unchanged. The g30 groundedness row correctly reads NOT SCORED: the human sheet was written against the 50-run's answer texts, and a score belongs to one answer text, not to a question id — it is never attributed across runs.

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
| answer | refusal of a documented corpus-gap question (expected; source pages never recovered by OCR) | 2 | Q20, Q21 |
| answer | over-answer on a corpus-gap question (guidance body never recovered, answer given anyway) | 1 | Q22 |
| answer | correct refusal (unanswerable) | 25 | Q26–Q50 |
| answer | visible hallucination (unanswerable, answer shown) | 0 | none |
| answer | raw hallucination caught before display | 2 | Q27, Q48 |
| answer | citation target missing (≥1 citation not in the retrieved set) | 4 | Q1, Q6, Q16, Q24 |

Q22's over-answer row is the honest middle of the corpus gap, not a miscount: its funding half is grounded in the Act's own Part VII (retrieved at rank 5, now a graded gold chunk), its accountability half is extrapolated from a recovered section heading of the guidance whose body was never OCR'd, and a human scored the answer 0.7 (partly grounded) — a score this pack flags as an open question because it sits on the rubric's band boundary. Citation-target misses fell from 19 individual citations to 5 once the citation parser was fixed to stop splitting multi-comma Act titles at the first comma; of the 5 remaining, one (Q16) is a chunk-labelling artefact — the model cited the full section title it read across a line break in the chunk body, while the stored section label was truncated at that break.

Two additional patterns are counted in `notes/failure_modes.md` and restated here because they are the mechanisms behind the numbers above:

- **Act ↔ Guidance rank flips:** on 19 of 50 questions, an Act and its sibling guidance document both appear in the top five. The rank order is not stable in either direction (the Act outranks its guidance on 8 questions; the guidance outranks the Act on 11). The dangerous instance is the Q20–Q22 group, where the NHIA guidance wins top ranks on front matter alone because its body was never recovered by OCR: Q20 and Q21 ended in correct refusals, and Q22 fell through to the Act's financial provisions for the funding half of the question while answering the accountability half from a recovered heading.
- **Front-matter / TOC dilution:** 9 of 50 questions have at least one retrieved chunk shorter than 200 characters in their top five. Heading-quality guards removed most TOC ghost-headings; what survives is concentrated on the scanned Acts.

---

## 4. Fix list, ranked by risk

| Rank | Fix | What it unblocks | How it is verified |
|---|---|---|---|
| 1 | Passage-level retrieval (raise INTERNAL_FETCH_K before the diversity cap; or section-label-aware re-ranking; or a hard filter that never lets front-matter chunks occupy a slot) | The 7 gold-miss questions (Q3, Q5, Q8, Q10, Q11, Q14, Q16) and, through them, most of the 5 model over-refusals. This is the single largest measured defect. | Re-run `python run_eval.py --prefix b1_v1 --strict --resume`; recall@5 and the gold-miss count in the failure register move or they do not. |
| 2 | Citation-target verification at runtime (after generation, confirm each [Title, Section] appears in the retrieved set; strip or re-prompt on a miss) | The 5 citations in 4 displayed answers that currently point outside the provided context (citation correctness 0.907; one of the five is a chunk-label artefact rather than a real miss). | Citation correctness rises toward 1.0 on the same run; `citations_missing` in `b1_v1_metrics.json` falls. |
| 3 | Acquire a text-complete copy of the NHIA Operational Guidelines 2023 (the current PDF is a CamScanner capture whose body was never recovered) | Q20–Q21 become answerable instead of correct refusals; Q22's accountability half becomes answerable instead of extrapolated; the Act ↔ Guidance front-matter failure on that group disappears. | `data/gold_chunks.json` gains gold chunks for Q20 and Q21; `validate_gold_chunks.py` passes; the corpus-gap refusal class in the failure register drops to 0. |
| 4 | Human second pass on the gold chunks (currently agent-graded with every evidence string verified verbatim, but not audited by a second grader) | Raises the trustworthiness of every retrieval metric built on the gold set. | A second grader's disagreements are recorded; metrics are recomputed against the audited set. |
| 5 | Citation-sufficiency verification: does the cited passage actually support the claim built on it? (Q22's failure mode — the citation target exists in the retrieved set but does not carry the accountability claim the sentence makes) | Closes the guardrail blind spot that let Q22's extrapolated half through: distance checks see a highly relevant Act chunk, target matching sees a present citation, and neither can read the passage. Start as an evaluation metric before trusting it as a runtime guardrail. | A sufficiency metric separates Q22 from the 17 fully grounded shown answers on the same frozen run; only then wire it into the guardrail stack. |

---

## 5. Method note (short form)

- **Gold set.** 50 hand-built questions: 25 answerable, 25 unanswerable across four strata (clinical, out-of-corpus, near-miss, mixed). The unanswerable half is synthetic by design, because a question the documents cannot answer is where a chatbot is most tempted to invent.
- **Gold chunks.** For the 25 answerable questions, the chunk(s) that actually contain the answer were graded by an AI agent; every evidence string was verified as a verbatim substring of its chunk by `scripts/validate_gold_chunks.py`. Not yet audited by a second human.
- **What recall@5 does and does not capture.** It measures whether the graded gold chunks appear in the retrieved top five. It does not measure whether the model used them correctly, whether a non-gold chunk also contained a usable answer, or whether the gold grading itself is complete.
- **Citation correctness.** An inline `[Title, Section]` citation is correct when it matches a retrieved chunk under any of four auditable rules, in order: exact title+section pair; whitespace-insensitive pair; normalised title containment with section containment (dash, case, whitespace normalised); and the whitespace-insensitive form of that containment. Multi-comma titles ("National Health Insurance Authority Act, 2022") are resolved against the known document titles before any split is attempted, so they are no longer broken at the first comma. It catches citations pointing outside the provided context; it does not judge whether a matched citation supports the adjacent claim, and it overcounts by one on Q16 (a chunk-label truncation artefact, documented in `notes/failure_modes.md`).
- **Groundedness rubric.** 1.0 = every factual claim supported by a retrieved chunk; 0.70–0.95 = correct and grounded with a minor omission or a mis-scoped detail; 0.60–0.70 = partly grounded with one or more inferred claims; 0.0 = refusal on an answerable question or no grounding at all. The column is now scored for all 18 answers shown to the user (mean 0.794); blanks would mean unscored, never zero, and the mean's denominator is exactly the count of non-blank scores. One score — Q22's 0.7 — sits on a band boundary and is recorded as an open question in `eval_results/v1_scoring_sheet.md`, not as a settled number.
- **Honest limitations.** 50 questions; synthetic unanswerables; agent-graded gold, not second-audited; groundedness scored by a single human grader with no second-grader agreement number; evaluation on a rate-limited free-tier LLM endpoint, with retries and `--resume` in the harness. A 0% hallucination rate on 25 synthetic unanswerable questions is a floor with 4-point resolution, not a guarantee.

---

## 6. Evidence index

| Claim in this pack | Committed file | Where |
|---|---|---|
| recall@5 = 0.379, n=23 | `eval_results/b1_v1_metrics.json` | `retrieval.recall_at_k` |
| context precision@5 = 0.174, MRR = 0.454 | `eval_results/b1_v1_metrics.json` | `retrieval.context_precision_at_k`, `retrieval.mrr` |
| document-level hit rate = 25/25 | `eval_results/b1_v1_metrics.json` | `retrieval.document_level_hits` / `document_level_answerable` |
| citation correctness = 0.907 (49/54) | `eval_results/b1_v1_metrics.json` | `answers.citation_correctness`, `citations_correct`/`citations_total` |
| grounded answer rate = 0.720 (18/25) | `eval_results/b1_v1_metrics.json` | `answers.grounded_answer_rate` |
| refusal correctness = 1.000 (25/25), hallucination = 0.000 | `eval_results/b1_v1_metrics.json` | `answers.refusal_correctness`, `answers.hallucination_rate` |
| raw hallucination = 2/25 (Q27, Q48) | `eval_results/b1_v1.csv` | rows id=27, id=48; `shown_to_user` ≠ answer while `answer_text` is substantive |
| per-claim groundedness = 0.794 over 18 of 18 shown answers | `eval_results/b1_v1_metrics.json`, `eval_results/v1_scoring_sheet.csv` | `answers.groundedness`; `groundedness_score` column |
| median latency 7.48 s, mean tokens 1,493 | `eval_results/b1_v1.csv` | `latency_seconds`, `input_tokens`+`output_tokens` over 50 rows |
| every failure-register count and question id | `notes/failure_modes.md` | generated block between `BEGIN/END GENERATED: failure-counts` markers |
| threshold 0.70, both distributions, the sweep, the Q45/Q7/Q15 caveat | `eval_results/threshold_calibration.md` | whole file; regenerable via `scripts/calibrate_thresholds.py` |
| groundedness rubric, the Q22 open question, and the blank-for-refusals rule | `eval_results/v1_scoring_sheet.md`, `eval_results/v1_scoring_sheet.csv` | rubric section; `groundedness_score` column |
| stranger-test wall-clock (21 min 7 s, 0 manual steps, 1,218 chunks) | `docs/reproduction_log.md` | Phase 1 section |
| corpus integrity (8/8 content-verified, sha256 lockfile) | `data/corpus.lock.json`, `data/SOURCES_STATUS.md` | whole files |
| original-30 comparison numbers | `eval_results/b1_v1_g30_metrics.json` | whole file |
| the eval table in the README is generated, not typed | `analysis/render_results.py`, `README.md` | `--check` exits non-zero if the committed block is stale |

---

## 7. Out-of-scope statement

This pack is an evidence report, not legal advice, not a compliance opinion, not a certification, and not a guarantee of any future result. Nothing here should be read as a statement that any facility complies with any regulation. The measurement harness is delivered as-is; Meridian's engineers own any fixes, and the ranked fix list in §4 is a recommendation, not a commitment. No part of this engagement rebuilds the product, guarantees an improvement, or warrants that the measured rates will hold on a different corpus, a different model, or production traffic.

---

## 8. Reproducibility claim

A stranger test was performed twice from a fresh clone of GitHub, most
recently on the delivered head: one documented command sequence, zero
manual steps, **20 minutes 7 seconds** wall-clock, ending in 8/8
content-verified documents, 1,218 chunks, and a passing drift check on
the bare clone (`docs/reproduction_log.md`, second-stranger-test section).
On that basis:

> Every number in this pack can be regenerated from the delivered scripts by a third party in under 30 minutes — `bash scripts/build.sh` for the corpus and index, then `python run_eval.py --prefix b1_v1 --strict --resume` and `python analysis/render_results.py` for the tables — assuming a Groq API key on the free tier. The per-claim groundedness score is the one number a machine cannot produce: it is human judgement, scored per answer against the rubric in `eval_results/v1_scoring_sheet.md` (mean 0.794 over 18 of 18 shown answers) and joined into the metrics only for the run whose answer texts it was written against — never estimated, never attributed across runs.
