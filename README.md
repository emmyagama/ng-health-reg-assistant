# B1 — Nigerian Health-Regulation Q&A

B1 is a small retrieval-augmented question-answering assistant that answers plain-language questions about Nigerian health-sector regulation. It is built on a fixed, hand-selected corpus of public documents: the Nigeria Data Protection Act 2023, the NDPC 2024 guidance notice on registration of data controllers of major importance, the National Health Insurance Authority Act 2022, the NHIA Operational Guidelines 2023, the HEFAMAA e-portal quick guide, the MLSCN national guidelines for setting up a medical laboratory, the National Health Act 2014, and the WHO Laboratory Quality Management System Handbook. It cites the document title and section for every factual claim, refuses rather than guesses when the answer is not in the corpus, and refuses clinical or medical-advice questions outright. Reliability is measured on a 30-question hand-built test set (25 answerable, 5 unanswerable), evaluated both before and after guardrails were added.

## Demo Video

[YOUTUBE_LINK_PLACEHOLDER]

## What it does

- Accepts a free-text regulatory question in the Streamlit UI.
- Embeds the question with all-MiniLM-L6-v2 and retrieves the five most relevant passages from a persistent ChromaDB vector store built from the eight source PDFs.
- Sends the retrieved passages to Groq's llama-3.1-8b-instant model with a system prompt that requires:
  - answers only from the provided context,
  - an inline [Document Title, Section Label] citation after every factual claim,
  - the fixed refusal string "I don't have enough information in the provided documents to answer this." when the context does not support an answer.
- Runs four post-generation guardrails before showing the answer to the user:
  1. Retrieval-confidence check — requires that the closest chunk is within an L2-distance threshold.
  2. Citation-required check — requires at least one [Title, Section] citation in the answer (except for the in-context refusal line).
  3. Clinical-question check — blocks questions asking for diagnosis, dosage, prescribing, or treatment advice; this assistant covers regulatory/administrative questions only.
  4. Within-corpus check — requires at least one chunk below the relevance threshold, so that obviously out-of-domain questions (e.g. immigration, tax) are refused instead of answered from weak nearest-neighbour matches.
- Displays the answer, a bulleted source list (document title and section), and the model/latency caption in Streamlit. If any guardrail fails, it shows a refusal message listing the reason(s).

## What it doesn't

- It does not give clinical, diagnostic, or prescribing advice. Clinical questions are blocked by guardrail and never reach the answer surface.
- It does not answer questions outside the supplied regulatory corpus. Tax rates for HMOs, visa requirements for foreign doctors, and similar out-of-scope questions return an explicit refusal.
- It does not perform OCR itself. Four of the eight source PDFs are scanned Official Gazette prints; text was extracted via PDF text layer where available and the NHIA Operational Guidelines body sections are a known corpus gap (see "What breaks").
- It does not update its knowledge when laws change. The corpus is fixed to the versions downloaded for this project and must be re-ingested to add or replace documents.
- It does not summarise entire documents or do multi-document comparison beyond the top-five retrieved passages.
- It does not use agents, tool-use, fine-tuned models, voice, or local/Ollama inference — those were explicitly out of scope for this version.

## What breaks

- Four scanned or partially-scanned PDFs have weak section detection and chunk coverage. The National Health Act 2014, NDPA 2023, and NHIA Act 2022 are image-only Gazette prints; their "Arrangement of Sections" and PART header pages produce short chunks dense in keywords that crowd out substantive sections during retrieval. The NHIA Operational Guidelines 2023 PDF is a CamScanner phone capture whose text layer covers only the cover, TOC, foreword, acknowledgements, abbreviations and glossary — the body of Sections 1–5 is largely missing, so questions specifically about CSHIS (§2.2) and HIUOR (§1.6) cannot be answered from this corpus and are correctly refused.
- Answers that should be grounded sometimes refuse. Six answerable questions return the in-context refusal rather than an answer (HEFAMAA facility categories, the 12 Quality System Essentials under MLSCN, lawful bases of processing, data-subject rights, and the two known NHIA body gaps). These are not guardrail failures; they occur when the correct chunk does not land in the top five. A small diversity cap (max three chunks per document) keeps same-document crowding down but occasionally evicts the correct passage.
- Guardrails have four known false positives at v1. Four well-grounded answers are blocked from reaching the user: (1) two answers use full-width 【…】 brackets that the citation regex does not recognise as citations, (2) the phrase "emergency medical treatment" triggers the clinical-question keyword on a legal-rights question about section 11 of the National Health Act, and (3) the NDPC categories answer also uses the non-regex bracket style. These are regex fixes, not design flaws.
- One fee-tier question is under-specified. The NDPC registration-fee answer lists the N5,000 per-processor fee but omits the N250,000 / N100,000 / N10,000 tier registration fees because the §3 tiers chunk did not make it into the top five. This is faithful to the retrieved context (no confabulation) but incomplete.
- The system depends on the Groq free tier. End-to-end latency on the evaluated run is about 8 seconds per question; rate-limit 429s appear intermittently during bulk evals and require a short retry.

## Evaluation Results

I built a golden set of 30 questions: 25 answerable from the corpus and 5 deliberately unanswerable (3 clinical, 2 on unrelated topics: HMO corporate tax, immigration). Each question was sent through the full pipeline before and after guardrails were wired in, and the outputs were scored manually.

Retrieval accuracy is top-5 hit rate (did the correct document appear in the first five retrieved chunks?). Groundedness is a per-claim 0–1 manual score averaged across the 25 answerable questions (1.0 = every factual claim supported by a cited passage; 0.0 = no substantive answer is shown). Hallucination rate is the fraction of the 5 unanswerable questions on which the system produced a confident answer instead of a refusal.

| Metric | Before guardrails | After guardrails |
| --- | --- | --- |
| Retrieval accuracy (top-5, 25 answerable) | 25/25 = 100% | 25/25 = 100% |
| Average groundedness (0–1, answerable) | 0.71 (71%) | 0.51 (51%) |
| Hallucination rate (5 unanswerable) | 0/5 = 0% | 0/5 = 0% |
| Avg end-to-end latency | 12.5 s | 8.0 s |
| Avg tokens per call (in + out) | 2,047 | 1,525 |

Notes on the numbers:

- Hallucination rate is 0% in both runs. In the post-tuning intermediate checkpoint (before guardrails were wired in), one unanswerable question ("how to diagnose malaria without a rapid test") briefly produced a confabulated answer about Giemsa-stained smears; the clinical-question guardrail intercepted it and replaced it with the out-of-scope refusal before it reached the user, which is exactly what guardrails are for.
- Groundedness dropped from 71% to 51% after guardrails because ten answerable questions now show the user no answer (score 0): six retrieval/corpus gaps that were already refusing before, and four guardrail false-positives described above. Among the 15 answers that do reach the user after guardrails, the average groundedness is ~0.83.
- Latency and token counts both fell (~36% and ~25% respectively) after a chunk-size reduction from 1000 to 700 characters to fit inside the embedding model's effective window.
- Retrieval accuracy remains 100% at the document level; the remaining failures are passage-level retrieval precision on the OCR'd Acts.

## Setup

Requires Python 3.10+ and a Groq API key (free tier works fine — get one at https://console.groq.com/keys).

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

   (This reads `sources.json` and saves each PDF to `data/raw/`, skipping files already present. The real `sources.json` is not included in this repo — substitute your own list pointing at the eight PDFs, or place the PDFs in `data/raw/` manually.)

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

The architecture diagram in `docs/architecture_diagram.svg` shows the end-to-end pipeline from downloads through UI, along with the main alternatives that were considered and rejected.

## What I'd Do Next

These are the specific, highest-leverage next steps I would take before calling this production-ready, ordered by expected impact:

1. Fix the four guardrail false positives. Broaden the citation regex to accept full-width 【…】 brackets (the model occasionally emits these under low temperature), and scope-narrow the clinical-keyword check so the bare word "treatment" does not trigger when it appears in a legal-rights context (e.g. within a few words of "emergency", "right", "refuse", "offence", or "penalty"). This alone should lift acceptable answers from 15/25 to ~19/25 while keeping hallucination rate at 0%.
2. Fix the front-matter junk filter for the three scanned Acts. The current filter is too conservative; it does not drop the NDPA "Arrangement of Sections" page, NHIA Gazette cover, or other 150–450 char front-matter chunks that are currently crowding out substantive sections. A content-based heuristic (dot-leader TOC lines, short line length + all-caps headings, absence of prose sentences) would recover Q5, Q10, and Q11 without touching the answer prompt.
3. Acquire a non-scanned or properly-OCR'd copy of the NHIA Operational Guidelines 2023. The CamScanner PDF in the corpus only has front matter and committee lists; the body text of Sections 1–5 (CSHIS definitions, HIUOR, funding, accountability) is absent, which is why those questions refuse. Re-OCR with tesseract or sourcing the original PDF would close the CSHIS/HIUOR gap entirely.
4. Add a citation-target verification step. After the model generates an answer, confirm that each [Title, Section] citation actually appears in the retrieved chunks passed in; if not, either strip the citation or re-prompt. This catches the existing malformed [c] placeholder citations (e.g. on the data-security answer) without adding a separate factuality model.

Repository layout: `download_corpus.py` → `src/chunker.py` → `src/embed_store.py` → `src/answer.py` → `src/guardrails.py` → `app.py`. Evaluation outputs and manual scoring live in `eval_results/`.
