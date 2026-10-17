# How I built a grounded assistant on Nigerian health regulations and measured whether it lies

## The problem

A diagnostic-centre manager in Nigeria cannot answer a simple compliance question in under an afternoon. The rules governing their facility — record-keeping, equipment, fees, registration — are spread across eight long PDFs from six different bodies: Nigeria's Data Protection Act, the NHIA insurance law, the National Health Act, state facility guidelines, MLSCN laboratory standards, and WHO quality manuals. Searching by hand is slow and keyword search misses things. I built an assistant that takes a plain-English question and returns an answer drawn directly from those documents.

## What the system does

The assistant searches the eight documents for the most relevant passages, then asks a language model to answer using only what it found. Every answer names its document and section. If the documents don't cover the question — "what is the corporate tax rate for HMOs" — it says "I don't have enough information" rather than guess. If the question asks for medical advice, it refuses outright: the sources are regulatory, not clinical. Nothing is remembered between questions.

## Why "doesn't lie" is a real problem

Language models write text that sounds confident and well-sourced even when it is invented — hallucination. For poetry this is harmless. For something a facility manager might use to decide whether their lab is compliant, where a wrong answer could mean operating illegally or mishandling patient data, it is not acceptable. Asking the model nicely to be honest does not work reliably. Asking nicely is not a safety feature.

## How I measured it

I built a fixed list of 50 test questions. Twenty-five are answerable from the documents; twenty-five are deliberately unanswerable, stratified so a pass is not just "the model said no": nine ask for clinical advice (dosing, diagnosis, prescribing), six ask about regulatory topics the documents do not cover (tax, immigration, customs, procurement, banking, labour), four are near-misses that look like they belong (a different Nigerian regulator, a different jurisdiction's health law, the revoked 2019 data-protection regulation, a private standard the corpus lacks), and four mix clinical vocabulary into regulatory questions and vice versa. A question the documents cannot answer is exactly where a chatbot is most tempted to invent something.

Four lightweight safety checks run after every answer is written: one confirms highly relevant passages were found (its distance threshold is calibrated against the measured v1 distributions, not guessed), one confirms the answer cites a document and section, one blocks clinical questions regardless of retrieval, and one catches questions clearly outside the corpus.

On the clean 50-question run, all 25 unanswerable questions were refused and none produced a fabricated answer the user could see — 0% hallucination at 4-point resolution. The retrieval layer is the weak one: recall@5 against the graded gold chunks is 0.379, and most cases where an answerable question gets no answer trace to the right chunk missing the top five. Citation correctness — the fraction of inline citations pointing at something actually in the retrieved context — is 0.907 (49 of 54 match; the 5 misses are all retrieval gaps, not formatting misses), measured and reported but not yet enforced at runtime. Per-claim groundedness has been scored by hand for every answer shown to the user: the mean is 0.794 over 18 of 18. Groundedness is faithfulness, not correctness: it asks whether every claim sticks to the retrieved text, not whether the underlying law is stated right or the section label is the one the document's own contents page uses. Q16 is where the two axes visibly diverge — its citation miss is a chunk-label artefact that makes the citation metric overcount, while a human reading the same answer scored it 0.60 for inferred claims the citation metric cannot see at all. One groundedness score (Q22, at 0.7) sits on a rubric band boundary and is recorded as an open question rather than a settled number.

## Limitations, stated plainly

The golden set is 50 hand-built questions and the unanswerable half is synthetic, not production traffic. Gold chunks were graded by an AI agent with every evidence string verified verbatim, but not yet audited by a second human. Groundedness was scored by a single human grader against the published rubric; there is no second-grader agreement number. Evaluation runs on the Groq free tier, so runs are rate-limited and retried.

## What I'd still improve

Three things. First, enforce citation-target verification at runtime: 5 of 54 inline citations currently miss the retrieved set, and nothing acts on that. Second, passage-level retrieval — the 0.379 recall@5 is the biggest measured weakness, and the gold set now exists to make any fix falsifiable. Third, the NHIA Operational Guidelines body was never recovered by OCR: Q20 and Q21 are correct refusals today, and Q22 is half-answered on the strength of the Act's own financial provisions while its accountability half still rests on a section heading rather than recovered guidance text. All three become answerable the moment a text-complete copy of the guidance is ingested. The earlier citation-bracket and clinical-keyword false positives are fixed and unit-tested.
