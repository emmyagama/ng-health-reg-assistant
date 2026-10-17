# How I built a Nigerian health-regulation assistant that shows its work

*A plain-language companion to `docs/method_note.md`. No repo paths, no
internal jargon — just what it does, how it was measured, and what is
wrong with it.*

## The problem

A diagnostic-centre manager in Nigeria needs to know something simple —
must my facility be registered before it opens, what records must I keep,
what does the NHIA say about my obligations — and the answer is spread
across eight long PDFs from six different bodies. Searching them by hand
takes an afternoon. Keyword search misses the section that answers the
question because the section never uses the words in the query.

I built an assistant that takes a plain-English question, finds the most
relevant passages in those eight documents, and answers using only those
passages — naming the document and section for every claim. If the
documents don't cover the question, it says so instead of guessing. If
the question asks for medical advice, it refuses: the sources are
regulatory, not clinical.

## Why "shows its work" is the point

Language models write confident, well-sourced-sounding text that is
invented. For a facility manager deciding whether their lab is compliant,
a hallucinated threshold is worse than no answer. Asking the model to be
honest is not a safety feature.

So the system is built the other way around: the answer must point at the
document and section it came from, and a stack of guardrails sits between
the model and the user. One checks that highly relevant passages were
actually found; one checks that the answer cites something; one blocks
clinical questions outright; one catches questions clearly outside the
corpus. Everything the model says before those checks is recorded next to
everything the user sees after them, so the two surfaces can be compared.

## How I measured whether it lies

Fifty hand-built questions. Twenty-five answerable from the documents.
Twenty-five deliberately unanswerable, stratified so that refusing them
is not easy mode: nine ask for clinical advice, six ask about regulatory
topics the documents don't cover (tax, immigration, customs), four are
near-misses that look like they belong, and four mix clinical vocabulary
into regulatory questions.

On the clean run:

- **All 25 unanswerable questions were refused.** Zero fabricated answers
  reached the user. Before the guardrails existed, the raw model
  produced two — both clinical-flavoured, both intercepted.
- **Citation correctness is 0.907**: 49 of 54 inline citations point at
  a section that was actually in the provided context. Four of the five
  misses are retrieval gaps; the fifth (Q16) is a chunk-label artefact
  that makes the metric understate correctness by one.
- **Per-claim groundedness was scored by hand for every answer shown to
  the user**: mean 0.794 over 18 of 18. Refusals are not scored as
  zeroes; a refusal is judged by whether refusing was right.
- **The weak layer is retrieval, and it is named as such.** Recall@5
  against a graded gold set is 0.379. When an answerable question gets
  no answer, in most cases the right passage never entered the top five.
  That is the first thing to fix, and the gold set exists so any fix can
  be falsifiable rather than vibes.

## What is honestly wrong with it

The worst failure is a corpus failure wearing a model costume: the NHIA
Operational Guidelines PDF is a phone scan whose body text was never
recovered. Two questions that depend on it are correctly refused. One
question straddles the gap and was half-answered — the grounded half
cites the Act itself, the other half extrapolates from a heading. That
answer is counted in the failure register as an over-answer, not buried
in an average, and the human score it received (0.7) is flagged as an
open question rather than presented as settled.

It does not keep up with legal change, does not remember conversations,
does not give medical advice, and is not a compliance certification. It
answers from eight fixed documents and shows where every claim came from.

## The claim I care about

Not that this assistant is good — that when it is wrong, the wrongness is
counted per class, attributed to the layer that caused it, keyed to
question ids, and published next to the things that work. A stranger can
clone the repository, rebuild the corpus in about twenty minutes, and
falsify every number.
