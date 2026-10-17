# B1 — Nigerian Health-Regulation Q&A

[![CI](https://github.com/emmyagama/ng-health-reg-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/emmyagama/ng-health-reg-assistant/actions/workflows/ci.yml)

B1 is a small retrieval-augmented question-answering assistant that answers plain-language questions about Nigerian health-sector regulation. It is built on a fixed, hand-selected corpus of public documents: the Nigeria Data Protection Act 2023, the NDPC 2024 guidance notice on registration of data controllers of major importance, the National Health Insurance Authority Act 2022, the NHIA Operational Guidelines 2023, the HEFAMAA e-portal quick guide, the MLSCN national guidelines for setting up a medical laboratory, the National Health Act 2014, and the WHO Laboratory Quality Management System Handbook. It cites the document title and section for every factual claim, refuses rather than guesses when the answer is not in the corpus, and refuses clinical or medical-advice questions outright. Reliability is measured on a 50-question hand-built test set (25 answerable, 25 deliberately unanswerable) and every published number is generated from the committed run by `analysis/render_results.py`.

## Demo Video

<!-- TODO (human): 90-second Loom walkthrough of the sample scorecard -->

## What it does

- Accepts a free-text regulatory question in the Streamlit UI.
- Embeds the question with all-MiniLM-L6-v2 and retrieves the five most relevant passages from a persistent ChromaDB vector store built from the eight source PDFs (chunked at 700 characters with 100 characters of overlap, section-aware).
- Sends the retrieved passages to Groq's openai/gpt-oss-120b model with a system prompt that requires:
  - answers only from the provided context,
  - an inline [Document Title, Section Label] citation after every factual claim,
  - the fixed refusal string "I don't have enough information in the provided documents to answer this." when the context does not support an answer.
- Runs four post-generation guardrails before showing the answer to the user:
  1. Retrieval-confidence check — requires that the closest chunk is within a calibrated L2-distance threshold (0.70, calibrated against the v1 run; see `eval_results/threshold_calibration.md`).
  2. Citation-required check — requires at least one [Title, Section] citation in the answer (except for the in-context refusal line). Accepts ASCII and full-width 【…】 brackets and commas, which the model occasionally emits.
  3. Clinical-question check — blocks questions asking for diagnosis, dosage, prescribing, or treatment advice; the bare word "treatment" is exempt in legal-rights contexts (near "emergency", "right", "refuse", "offence", "penalty").
  4. Within-corpus check — requires at least one chunk below the same calibrated threshold, so obviously out-of-domain questions (immigration, tax) are refused instead of answered from weak nearest-neighbour matches.
- Displays the answer, a bulleted source list (document title and section), and the model/latency caption in Streamlit. If any guardrail fails, it shows a refusal message listing the reason(s).

## What it doesn't

- It does not give clinical, diagnostic, or prescribing advice. Clinical questions are blocked by guardrail and never reach the answer surface.
- It does not answer questions outside the supplied regulatory corpus. Tax rates, visa requirements, procurement law, and similar out-of-scope questions return an explicit refusal.
- It does not keep up with legal change. The corpus is fixed to the versions downloaded for this project and must be re-ingested to add or replace documents. The revoked NDPR 2019 is not in the corpus; the live NDPA 2023 is, and a question about the revoked regulation is expected to be refused.
- It does not summarise entire documents or do multi-document comparison beyond the top-five retrieved passages.
- It does not use agents, tool-use, fine-tuned models, voice, or local/Ollama inference — those were explicitly out of scope for this version.
- It does not recover text that the source PDFs do not contain. OCR (`src/ocr_scans.py`, rapidocr-onnxruntime) runs automatically during the build for textless PDFs, but it can only extract what the scan actually shows (see "What breaks").

## What breaks

- **The NHIA Operational Guidelines body is missing from the corpus.** The PDF is a CamScanner phone capture. Its text layer and the OCR sidecar together cover only the cover, table of contents, foreword, acknowledgements and glossary — the bodies of Sections 1–5 (CSHIS, HIUOR) were never recovered. Questions Q20 and Q21 ask about exactly that material and are correctly refused. Q22 straddles the gap: its funding half is answered by the Act's own Part VII (recovered, and now a graded gold chunk), so it was answered there, while its accountability half extrapolates from a recovered section heading in the guidance's front matter — the model was scored 0.7 (partly grounded) for this, and the failure register counts it as an over-answer on a corpus-gap question, not a clean answer. This is a corpus gap and a documented guardrail blind spot in one: the distance check sees a highly relevant Act chunk and the citation it quotes does exist in the retrieved set, so no guardrail can fire — target matching alone cannot see that a cited passage does not support the claim next to it.
- **Passage-level retrieval is the weak layer.** Document-level hit rate is saturated at 25/25, but recall@5 against the chunk-level gold set is 0.379 and MRR is 0.454 (23 questions with graded gold chunks). Most over-refusals trace to the correct chunk missing the top five, not to the guardrails.
- **Over-refusal on answerable questions.** 18 of 25 answerable questions are shown an answer. Of the 7 that are not, 2 are the documented corpus-gap questions (Q20, Q21) being refused as designed, and 5 are true over-refusals — all of them the model itself declining on weak retrieval (Q3, Q5, Q10, Q11, Q14), none of them a guardrail false positive in this run. The per-question split is in the generated failure-counts table in `notes/failure_modes.md`.
- **Citation targets sometimes miss.** 5 of the 54 inline citations in displayed answers fail to match a retrieved title/section pair (citation correctness 0.907; the other 49 match). Four of the 5 are genuine retrieval gaps; the fifth (Q16) is a chunk-label artefact that makes the metric understate correctness by one — the cited chunk was retrieved, but the stored label is truncated and the citation carries a tail the label never has. The earlier parser defect (multi-comma Act titles split at the first comma) accounted for 14 of the previous 19 misses. These are measured and reported, not stripped at runtime — see "What I'd Do Next".
- **The system depends on the Groq free tier.** End-to-end latency on the v1 run averages ~6.5 s per question. Bulk runs hit connection errors or 429s; the harness retries with jitter and `--resume` completes the run, but a fresh full run takes several minutes and a working network.

## Evaluation Results

The golden set has 50 questions: 25 answerable from the corpus and 25 deliberately unanswerable — 9 clinical (dosing, diagnosis, prescribing), 6 clearly out-of-corpus regulatory (tax, immigration, customs, procurement, banking, labour), 4 near-miss (a different Nigerian regulator, a different jurisdiction, a superseded regulation, a private standard), and 4 mixed (clinical vocabulary wrapped around a regulatory question, and vice versa); the original 30 questions are unchanged and can be re-run with `--golden data/golden_set_30.json`.

One clean pass through the strict, resumable harness records both surfaces: what the raw model said, and what the guardrails let through. Every number in the table below is generated from `eval_results/b1_v1.csv` by `analysis/render_results.py` — none is typed by hand. The script is idempotent and `--check` fails if this file drifts from the run.

<!-- BEGIN GENERATED: eval-results -->
| Metric | Before guardrails (raw model output) | After guardrails (shown to user) | Source |
|---|---|---|---|
| recall@5 | 0.379 (n=23) | 0.379 (n=23) | `b1_v1_metrics.json` |
| context precision@5 | 0.174 (n=23) | 0.174 (n=23) | `b1_v1_metrics.json` |
| MRR | 0.454 (n=23) | 0.454 (n=23) | `b1_v1_metrics.json` |
| document-level hit rate (old metric, saturated) | 25/25 | 25/25 | `b1_v1_metrics.json` |
| grounded answer rate | 18/25 = 72.0% | 72.0% (n=25) | `b1_v1.csv` / `b1_v1_metrics.json` |
| refusal correctness | 23/25 = 92.0% | 100.0% (n=25) | `b1_v1.csv` / `b1_v1_metrics.json` |
| hallucination rate | 2/25 = 8.0% | 0.0% (n=25) | `b1_v1.csv` / `b1_v1_metrics.json` |
| citation correctness | not measured pre-guardrails | 0.907 (49/54 inline citations) | `b1_v1_metrics.json` |
| groundedness (faithfulness of shown answers) | not measured pre-guardrails | 0.794 over 18 of 18 shown answers scored by hand (0 unscored, never zeros) | `b1_v1_metrics.json` / `v1_scoring_sheet.csv` |
| median end-to-end latency | 7.48 s (n=50) | same run, guardrails add no network calls | `b1_v1.csv` |
| mean tokens per call (in+out) | 1493 (n=50) | same run | `b1_v1.csv` |
<!-- END GENERATED: eval-results -->

Notes on the numbers:

- Hallucination rate is 0% after guardrails on both the 25-question unanswerable pool (n=25, 4-point resolution) and the original 5 (in `b1_v1_g30_metrics.json`). Before guardrails the raw model hallucinated on 2 of 25 (Q27, a clinical malaria-diagnosis question, and Q48, a consent question with a clinical keyword); both were intercepted by the clinical guardrail before display — which is precisely the failure mode the guardrails exist for, and the reason a 0% that only counts the shown surface would be the wrong number to publish.
- Groundedness (per-claim 0–1 over the answers shown to the user) is scored: mean 0.794 across all 18 shown answers. The scoring sheet with the rubric is `eval_results/v1_scoring_sheet.csv`; a blank `groundedness_score` means unscored and is never counted as a zero — on this run every shown answer is scored (18 of 18). One score is flagged for review rather than treated as settled: Q22's 0.7 sits exactly on the rubric's band boundary (0.60–0.70 "partly grounded" vs 0.70–0.95 "minor omission"), and the run report records it as an open question. Historical hand scores against the pre-remediation pipeline are in `eval_results/archive/` and are not comparable to this run.
- Retrieval metrics are computed only over the 23 answerable questions with graded gold chunks. Q20 and Q21 have no gold because their source pages were never recovered (corpus gap above). Q22 was given one gold chunk — the Act's Part VII funding passage, verified verbatim — once its funding half proved in-corpus; its accountability half remains a gap, which is why the failure register counts Q22 as an over-answer on a corpus-gap question rather than a clean answer.
- The old document-level hit rate is shown only for contrast: it reads 100% in every run we have done and cannot distinguish a good retrieval from a bad one.

## Limitations of these measurements

- The golden set is 50 questions, hand-built by one person, and the unanswerable half is synthetic — it is not a sample of production traffic. A 0% hallucination rate on synthetic refusals is a floor, not a guarantee.
- Gold chunks for the 25 answerable questions were graded by an AI agent and every evidence string was verified verbatim against the chunk text (`scripts/validate_gold_chunks.py`); they have not been audited by a second human grader.
- Groundedness is scored for every answer shown to the user (18 of 18 on this run), but it is one person's judgement against a rubric, not a second gold set; the scorecard always states the coverage next to the mean so a partial sheet cannot pass as a full one.
- The evaluation runs on the Groq free tier, so runs are rate-limited and retried; latency figures include that retry behaviour.
- Citation correctness is a string match against the retrieved set (dash/case/whitespace normalised). It catches citations that point outside the provided context; it does not judge whether a matched citation supports the claim next to it.

## Method and architecture

- `docs/method_note.md` — why the corpus and the golden set were built the way they were, in plain language.
- `docs/architecture_note.md` — the pipeline, the alternatives that were considered and rejected, and the guardrail calibration.
- `eval_results/threshold_calibration.md` — how the 0.70 distance threshold was chosen, with both distributions and the sweep.
- `eval_results/v1_scoring_sheet.md` — the groundedness rubric and what each column means.

## Setup

Requires Python 3.10–3.12 (the OCR dependency `rapidocr-onnxruntime` has no wheel for 3.13+) and a Groq API key (free tier works fine — get one at https://console.groq.com/keys).

One command builds everything from a fresh clone — download (with content verification against `data/corpus.lock.json`), OCR sidecars for textless PDFs, chunking, embedding — and was measured end-to-end twice by stranger tests from a fresh GitHub clone: the second run (2026-10-17, on the v1.1.0 head) finished in **20 min 7 s** with zero manual steps, and the first run (2026-10-16, the Phase 1 publication gate on the then-active `b1-remediation` branch) took 21 min 7 s (both in `docs/reproduction_log.md`):

```bash
bash scripts/build.sh
```

Corpus-acquisition caveat: the corpus is pinned by SHA-256 and content-verified against document-specific markers. On the author's machine all eight sources resolve directly and the full build was measured end to end. Two hosts (`ndpc.gov.ng`, `iris.who.int`) are known to refuse datacentre IP ranges; where a source cannot be fetched, `download_corpus.py` exits non-zero and names it rather than silently substituting a non-PDF, and `data/SOURCES_STATUS.md` records the observation date, the status per source, and the manual-placement path with expected hashes.

Or step by step:

1. Clone the repository and change into it:

   ```bash
   git clone <repo-url> b1
   cd b1
   ```

2. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate      # on Windows: .venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root with your Groq key:

   ```
   GROQ_API_KEY=gsk_your_key_here
   ```

5. Download the source documents into `data/raw/`:

   ```bash
   python download_corpus.py
   ```

   This reads the committed `data/sources.json`, downloads each PDF, and validates every file by sha256 (`data/corpus.lock.json`) **and** by content markers before accepting it. `python download_corpus.py --verify` re-checks an existing `data/raw/`; `--status` prints the current state. The URLs, licences and validation evidence for each document are in `data/SOURCES_STATUS.md`.

6. Chunk the corpus into section-aware passages:

   ```bash
   python src/chunker.py
   ```

   This writes `data/processed/all_chunks.json`.

7. Embed the chunks into a persistent ChromaDB vector store:

   ```bash
   python src/embed_store.py
   ```

   This writes the `chroma_db/` directory.

8. Launch the Streamlit UI:

   ```bash
   streamlit run app.py
   ```

9. (Optional) Re-run the evaluation and regenerate every published number:

   ```bash
   python run_eval.py --prefix b1_v1 --strict --resume
   python analysis/render_results.py
   python analysis/render_results.py --check
   ```

The architecture diagram in `docs/architecture_diagram.svg` shows the end-to-end pipeline from downloads through UI, along with the main alternatives that were considered and rejected.

## What I'd Do Next

1. **Citation-target verification at runtime.** The harness measures citation correctness (0.907; 5 of 54 citations miss) but the app does not act on it. After generation, confirm each [Title, Section] citation appears in the retrieved set; strip or re-prompt on a miss. The parser now resolves multi-comma Act titles, so what remains is exactly the class a runtime check should catch: a citation naming a section the model was not given.
2. **Passage-level retrieval.** Recall@5 of 0.379 against graded gold is the biggest measured weakness. Options in order of cheapness: raise INTERNAL_FETCH_K before the diversity cap, section-label-aware re-ranking, or a hard filter that never lets front-matter/TOC chunks occupy a slot. Each is falsifiable against the existing gold set.
3. **Citation-sufficiency verification.** Target matching cannot see Q22's failure: the cited accountability passage exists in the retrieved set but does not support the claim built on it. The next check is semantic — does the cited passage say what the sentence says? — which is a model-graded check, not a string one, and should start as an evaluation metric before it is trusted as a runtime guardrail.
4. **A human second pass on the gold chunks.** The gold set is agent-graded with verbatim evidence; one human audit would upgrade every retrieval metric built on it. Q22's new gold chunk and its groundedness score (0.7, on a band boundary) are the natural place to start.

Repository layout: `download_corpus.py` → `src/chunker.py` → `src/embed_store.py` → `src/answer.py` → `src/guardrails.py` → `app.py`. Evaluation harness: `run_eval.py`; published tables: `analysis/render_results.py`. Evaluation outputs live in `eval_results/`.

## Licence and contact

MIT — see [LICENSE](LICENSE). Copyright © 2026 Okoliko Emmanuel Agama.

How to cite: Okoliko Emmanuel Agama, *B1 — Nigerian Health-Regulation Q&A*, MIT-licensed source at <https://github.com/emmyagama/ng-health-reg-assistant>, v1.1.0 (2026).

Contact: emmyagama006@gmail.com
