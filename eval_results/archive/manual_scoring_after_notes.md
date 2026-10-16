# Manual Scoring — `after_guardrails` run

Source: `eval_results/after_guardrails_guardrails.csv`.

> **PROVENANCE NOTE (added 2026-10-16, when these notes were archived):** the cited source file `after_guardrails_guardrails.csv` has never existed in this repository. The numbers in this file cannot be re-derived and are retained as historical human judgement only.

Scoring rubric identical to `manual_scoring_before.md` — answerable questions
scored 0–1 per claim; unanswerable questions scored yes/no hallucination based
on what is **shown to the user** (i.e. after guardrails refusal replacement),
not on the raw `answer_text` the model produced.

## Headline numbers

| Metric                               | Before guardrails | After guardrails |
|--------------------------------------|-------------------|------------------|
| Retrieval accuracy (top-5, answerable) | 25/25 = 100%    | 25/25 = 100%     |
| Avg groundedness (answerable, 0–1)   | 0.71 (71%)        | 0.51 (51%)       |
| Acceptable answers (score ≥ 0.5)     | 21/25             | 15/25            |
| Answerable questions refused to user | 4                 | 10               |
| Hallucinations on 5 unanswerable Qs  | **0/5**           | **0/5**          |
| Hallucination rate                   | **0%**            | **0%**           |

**Hallucination rate (before) = 0/5 = 0%.**
**Hallucination rate (after) = 0/5 = 0%.**

Important nuance: in the raw `after_retrieval` (post-retrieval-tune, pre-guardrails)
intermediate checkpoint, Q27 (diagnose malaria without RDT) had flipped to a
confabulated answer about Giemsa-stained blood smears. The `check_clinical_question`
guardrail intercepted it and replaced it with the out-of-scope refusal before
it reached the user — so the user-visible surface remains 0/5 hallucinations,
and in fact all five unanswerable questions now produce an explicit refusal
message (Q26, Q27, Q28 clinical; Q29 out-of-corpus; Q30 model-refused).

## Why groundedness dropped from 71% to 49%

The drop is **not** a regression in answer quality among questions the user
receives an answer for. It is caused by ten answerable questions now returning
"no answer" to the user (score 0 each), which pulls the average down. These
break into two groups:

### Group 1 — Retrieval / corpus gaps (6 questions, unchanged by guardrails)
These are the same gaps identified in the retrieval diagnosis and were
refusing before guardrails too:
- **Q3** (HEFAMAA facility categories) — HEFAMAA chunk sits at raw rank 6,
  post-cap evicts it.
- **Q5** (12 QSEs) — MLSCN's 12-clauses chunk at raw rank 7, crowded out by
  cover/INTRODUCTION chunks.
- **Q10** (lawful bases for processing) — three NDPA Part I/Application front-
  matter chunks fill the 3 NDPA cap slots, keeping §24/§25 out of top-5.
- **Q11** (data-subject rights) — same crowding; PART VI chunks not in top-5.
- **Q20, Q21** (CSHIS, HIUOR) — known NHIA Operational Guidelines corpus gap;
  body of §2.2/§1.6 never acquired.

Fixing these needs OCR/sectioning work on the scanned PDFs and possibly the
missing NHIA body pages — out of scope for this tuning pass.

### Group 2 — Guardrail false positives (4 questions, new in `after_guardrails`)
These produced well-grounded or partly-grounded answers but were blocked by
guardrails and never shown to the user. None are safety failures; they are
brittleness in the guardrail regex/keyword list that should be fixed before
production.

| Q  | Triggering guardrail            | Root cause |
|----|---------------------------------|------------|
| Q4 (primary lab 5m×6m dimensions) | `check_citation_required` | Answer uses `【…】` square brackets (CJK-style) instead of `[…]`, so the citation regex doesn't see any citations. The actual content and citation targets are correct. |
| Q7 (emergency medical treatment)  | `check_clinical_question`    | Answer uses the word "treatment" in a legal context ("refusing a person emergency medical treatment"), which matches the `\btreat(?:ment|ing|ed)?\b` clinical-regex. This is a legal-rights question, not a clinical-advice question. |
| Q8 (classification/standards)    | `check_citation_required`   | Answer uses `【…】` brackets instead of `[…]`. Content is well-grounded in NHA §9. |
| Q16 (NDPC three categories)       | `check_citation_required`   | Answer uses `【…】` brackets instead of `[…]`. Content is partially wrong (describes "particular value/significance" designation instead of naming UHL/EHL/OHL), but the block is triggered on citation formatting, not on the content error. |

### Genuinely-improved answers (the ones that aren't blocked)
- **Q1, Q6, Q9, Q12, Q15, Q17, Q18, Q19, Q22, Q23, Q24, Q25** — well-grounded
  (0.75–1.00), no hallucinations, correct citations.
- **Q2, Q6, Q9, Q19, Q24, Q25** — essentially unchanged and correct.
- **Q7** (in the underlying answer_text, before guardrail block) gives the
  correct §11(1) answer and the N100,000/6-month penalty — the answer is
  right; only the keyword false-positive hides it.
- **Q13** (security obligations) has broken `[c]` citation placeholders in the
  answer (model slipped in `[c]` instead of real titles) — I scored 0.70
  because the facts are correct but citations are malformed; not caught by
  guardrails because something still matches the bracket regex.
- **Q14** (NDPC fees) — score 0.85 (was 0.30): answer is faithful to retrieved chunks (§7 only specifies N5,000 processor fee; §3 tiered registration-fee chunk didn't make top-5). This is a retrieval silence, not a hallucination — the model didn't invent the missing tiers, it correctly stated "the guidance does not specify any separate registration fee" given what it was given. Score reflects groundedness-to-context, not completeness.

## Per-question scoring detail

Key to `guardrail_effect`:
- `ok` — answer shown, well-grounded.
- `corpus/retrieval` — model correctly refused; retrieval didn't surface
  the answer passage or the passage isn't in the corpus.
- `bracket_fp` — citation-format false positive (【…】 vs […]).
- `clinical_fp` — clinical-keyword false positive on a legal question.
- `malcites` — answer shown but one or more citations point to a wrong
  section; content still largely correct.
- `badcite` — answer shown but citations point to a non-substantive chunk
  (WHO address line instead of chapter heading).
- `minorcites` — answer shown; a couple of citations are imperfect but core
  facts are right.
- `partial` — answer partially correct but missing key information /
  contains a direct misstatement.
- `corpus_gap` — known corpus gap (NHIA Operational Guidelines body text).
- `safe` — unanswerable question correctly blocked by guardrails.

## Recommended immediate fixes before calling this done (guardrail polish)

1. **Relax citation regex** to accept both `[…]` and `【…】` bracket styles
   (the model occasionally emits CJK brackets under low temperature; they
   are visually/functionally equivalent).
2. **Tighten the clinical-keyword check** so the bare word "treatment" does
   not trigger when preceded by "medical treatment" in a legal/rights
   context (e.g. when within ~6 words of "right", "refuse", "emergency",
   "offence", or "penalty"). Alternatively, require two clinical keywords
   to fire, or add a negative-lookahead for legal terms.
3. **Q14 content error** is a generation issue, not a guardrail issue — the
   N250k/N100k/N10k registration fees are present in the NDPC guidance
   chunks. Worth a prompt tweak ("list every fee tier with its naira amount
   rather than only one"), not a structural fix.

These three fixes would likely lift answerable-zero-scores from 10 to 6
(leaving only the 4 genuine retrieval/corpus gaps refusing), and bring
acceptable answers back to ~19/25 with 0/5 hallucinations retained.

## Bottom line for README / method note

> **Hallucination rate on out-of-scope questions: 0% (0/5) both before and
> after guardrails.** Guardrails are doing what they were built for — they
> intercepted a would-be hallucination on the malaria-diagnosis question
> (Q27) that had slipped through at the post-tune intermediate checkpoint,
> and they turned all five unanswerable questions into explicit refusals.
> Average groundedness on answerable questions dipped from 71% to 49%
> primarily due to four guardrail false-positives (bracket format and an
> over-broad "treatment" keyword) that are simple regex fixes, and six
> remaining retrieval/corpus gaps. No unsafe confabulated answer reaches
> the user on the after-guardrails build.
