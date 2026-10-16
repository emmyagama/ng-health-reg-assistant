# Failure modes — counted from the v1 run

Every number in this file comes from `eval_results/b1_v1.csv` (50 questions,
2026-10-16, strict/resumable harness) and is regenerable:

```bash
python analysis/render_results.py          # rewrites the table below
python analysis/render_results.py --check  # fails if this file drifts
```

Question ids (Q1–Q50) are the join key to every other artefact: the CSV row,
the scoring sheet row, and the golden set entry.

## The counts

<!-- BEGIN GENERATED: failure-counts -->
| Layer | Class | Count | Question ids |
|---|---|---|---|
| retrieval | gold chunk outside top-5 (answerable, has gold) | 7 | Q3, Q5, Q8, Q10, Q11, Q14, Q16 |
| retrieval | same document holds >3 of the top-5 slots (diversity-cap violation) | 0 | none |
| retrieval | same document holds exactly 3 of the top-5 slots (cap engaged, expected) | 46 | (not enumerated) |
| answer | over-refusal by a guardrail (answerable, in corpus) | 0 | none |
| answer | over-refusal by the model itself (answerable, in corpus) | 5 | Q3, Q5, Q10, Q11, Q14 |
| answer | refusal of a documented corpus-gap question (expected; source pages never recovered by OCR) | 2 | Q20, Q21 |
| answer | over-answer on a corpus-gap question (guidance body never recovered, answer given anyway) | 1 | Q22 |
| answer | correct refusal (unanswerable) | 25 | Q26, Q27, Q28, Q29, Q30, Q31, Q32, Q33, Q34, Q35, Q36, Q37, Q38, Q39, Q40, Q41, Q42, Q43, Q44, Q45, Q46, Q47, Q48, Q49, Q50 |
| answer | visible hallucination (unanswerable, answer shown) | 0 | none |
| answer | raw hallucination caught before display | 2 | Q27, Q48 |
| answer | citation target missing (>=1 citation not in the retrieved set) | 4 | Q1, Q6, Q16, Q24 |
<!-- END GENERATED: failure-counts -->

## Retrieval failure classes

**1. Gold chunk outside the top five.** The largest class. For every question
in the table above marked as a miss, the chunk(s) graded as containing the
answer never entered the model's context, so the answer layer could not have
been right even in principle. This is where the 0.379 recall@5 comes from;
the saturated 25/25 document-level hit rate hides it because the *right
document* is almost always present while the *right passage* is not. The
dominant sub-cause is front-matter and sibling competition, not absence of
the topic.

**2. Same-document crowding.** The diversity cap (at most `MAX_PER_DOC=3`
chunks per document in the top five, over-fetching internally so the
filter can still fill the slots) is engaged on 46 of 50 questions — the
count above includes every question where a document holds exactly three
of the five slots. That is the cap working, not a violation: on a corpus
of eight single-domain documents, three near-neighbours from the winning
document is the common case. The violation row counts questions where a
document holds *more* than the cap, which would mean the filter is not
applied; before the filter existed, 4–5 of 5 slots routinely came from
one document (see `eval_results/archive/` for the pre-cap runs).

**3. Act ↔ Guidance rank flips.** Sibling documents that regulate the same
topic appear together in the top five on **19 of 50 questions** (pairs:
NDPA 2023 ↔ NDPC 2024 guidance; NHIA Act 2022 ↔ NHIA Operational
Guidelines 2023). The order is not stable in either direction: the Act
outranks its guidance on Q10, Q11, Q12, Q13, Q17, Q19, Q40, Q45; the
guidance outranks the Act on Q7, Q14, Q15, Q16, Q20, Q21, Q22, Q29, Q47,
Q48, Q50. Distances within a pair are typically within ~0.05 of each
other, so chunk wording decides the rank, not authority. The dangerous
instance of this pattern is the Q20–Q22 group: the NHIA *guidance* wins
the top ranks while its body text was never recovered by OCR — the
retriever is confidently fetching the guidance's front matter (TOC,
committee lists), which is exactly the next class. On Q20 and Q21 that
ended in a correct refusal; on Q22 the model fell through to the Act's
own Part VII (retrieved at rank 5) for the funding half of the question
and answered from a recovered guidance *heading* for the accountability
half — the over-answer row in the generated table.

**4. Front-matter / TOC dilution.** Nine questions (Q2, Q4, Q5, Q8, Q17,
Q20, Q24, Q34, Q49) have at least one retrieved chunk shorter than 200
characters in their top five. The heading-quality guards added during the
retrieval-tuning pass removed most TOC ghost-headings, so this is far
smaller than in the pre-tuning runs, but it survives on the scanned Acts,
where "Arrangement of Sections" pages and gazette covers still look like
dense, keyword-rich, short passages — i.e. exactly what a dense retriever
likes.

**5. `doc_id` naming brittleness (kept, updated).** Three of eight
`doc_id`s in the vector store are not filename stems:
`nhia_guidance_2023` (file `nhia_operational_guidelines_2023.pdf`),
`hefamaa_requirements` (`hefamaa_quickguide.pdf`), and
`who_lab_quality_guidance` (`who_lqms_handbook.pdf`). The ids now come
from the committed `data/sources.json`, which the downloader, chunker,
golden set and gold chunks all read, so the pipeline is internally
consistent. The remaining risk is human: any future re-ingestion that
guesses `doc_id = filename_stem` instead of reading `sources.json` will
silently break the golden set for those three documents and produce false
misses. The fix is procedural (always read `sources.json`), and this
paragraph is the procedure.

## Answer failure classes

**1. Over-refusal, split by who refused.** Five answerable, in-corpus
questions are refused by the model itself (Q3, Q5, Q10, Q11, Q14 — every
one of them also a gold-chunk retrieval miss, so the model was declining
on context it correctly judged insufficient). Zero are refused by a
guardrail in this run. Two more refusals (Q20, Q21) are the documented
corpus-gap questions and are counted separately in the table because
refusing them is the designed behaviour, not a defect. The model-decline
class is fixable by retrieval quality; the gap class only by acquiring
better source PDFs.

**2. Correct refusals and caught hallucinations.** All 25 unanswerable
questions were refused. The table also counts *raw hallucinations caught
before display* — questions where the model's raw output was a
substantive answer but a guardrail replaced it with a refusal. Two in
this run: Q27 (clinical malaria-diagnosis question, blocked by the
clinical keyword check) and Q48 (a data-consent question with the
clinical keyword "diagnosis" in it, blocked by the same check). Both are
the guardrail stack earning its keep; the display-layer hallucination
count is zero *because* these two were intercepted, not because the raw
model got them right.

**3. Citation target missing.** Still present but no longer the most common
answer-layer defect: an inline `[Title, Section]` citation whose target is
not in the retrieved set. After the citation parser was fixed to stop
splitting multi-comma Act titles at the first comma ("National Health
Insurance Authority Act, 2022" used to be read as title "National Health
Insurance Authority Act"), 49 of the 54 inline citations match (citation
correctness 0.907); the 5 remaining misses span 4 answers (Q1, Q6, Q16,
Q24). Most still cluster on the memory-citation pattern — the model knows
the right section label from pretraining and cites it even though the
retriever supplied a different section of the same document (Q1 cites an
Inspection section that was never retrieved; Q6 cites 8.0 when 8.2 was
retrieved; Q24 cites two subsections, 14-1 and 14-4, that missed the top
five). One is a chunk-labelling artefact rather than a true
out-of-context citation: on Q16 the model cited the section's full title
— "…Data Processors of Major Importance" — which it read across a line
break in the chunk body, but the stored *section label* was truncated at
that line break, so the containment check fails against the label while
the claim itself is properly grounded. The metric therefore overcounts by
one there, and it is left that way rather than tuned. The
citation-*presence* check passes (all 18 shown answers have at least one
citation); nothing currently checks the *target* at runtime.

**4. Silent incompleteness.** An answer that is fully grounded but omits
part of what the question asked (the classic case: an NDPC fee answer
that lists the per-processor fee but not the tier registration fees
because the tier chunk missed the top five). This cannot be counted
mechanically — it requires reading the answer against the question — and
it is what the `groundedness_score` column in
`eval_results/v1_scoring_sheet.csv` exists to capture. That column is now
scored for all 18 shown answers (mean 0.794); the published example of
this class is Q22, whose accountability half is answered from a section
heading rather than recovered guidance text and scored 0.7. No separate
count of incompleteness defects is claimed, because the sheet scores
faithfulness per answer, not omissions per question.

**5. Guardrail false positive on the new near-miss strata.** Q45 (the
revoked-NDPR-2019 trap) sits at minimum distance 0.389 — *below* the
calibrated 0.70 threshold — because the successor act it was asking
about supersedes is genuinely close in embedding space. This check alone
cannot refuse it; it was refused by the model's own judgement in the v1
run. Near-miss questions are, by construction, the hardest stratum, and
Q45 is the published example of a distance threshold not being enough.

**6. Genuine hallucination shown to the user.** Zero, on 25 synthetic
unanswerable questions (4-point resolution). Stated with its n because a
bare 0% is not a measurement.

## Bottom line, from the data only

- The pipeline never showed a fabricated answer in the published run
  (0/25 unanswerable), and every refusal the user saw was deliberate.
- The weak layer is passage-level retrieval: recall@5 of 0.379 against
  graded gold, with front-matter competition and Act↔Guidance ties as the
  named mechanisms. Over-refusal on answerable questions is its direct
  consequence.
- The weakest *unenforced* guarantee is citation targets: 5 of the
  citations in displayed answers point outside the retrieved context
  (one of the five is a chunk-label artefact rather than a real miss),
  measured every run, fixed by nothing yet.
- The NHIA guidance body gap remains a corpus problem wearing a retrieval
  costume: the retriever keeps winning front-matter chunks of a document
  whose substance is not in the file. Q20–Q21 ended in correct refusals;
  Q22 is the half-answered case — grounded funding half, extrapolated
  accountability half, counted in the over-answer row above.
