# Architecture Note — B1 Health-Regulation Q&A

## Overview

B1 is a retrieval-augmented question-answering assistant for Nigerian health-sector regulation. It answers plain-English questions about a fixed corpus of eight public documents (the NDPA, NDPC guidance, NHIA Act, HEFAMAA requirements, MLSCN guidelines, National Health Act 2014, and WHO laboratory-quality guidance), cites the document and section behind every claim, and refuses — rather than guesses — on questions outside the corpus or asking for clinical advice. The system is intentionally small: one retriever, one LLM call per question, no agents, no user state.

## Data Flow

Documents are downloaded as PDFs, split into passages, embedded, and persisted to a local vector store. At query time the user's question is embedded against the same model, the five closest passages are retrieved, and those passages plus the question are sent to a hosted LLM with a system prompt requiring in-context answers and [Document, Section] citations. Four lightweight rule-based guardrails inspect the retrieved set and the generated answer before it is shown; failures are replaced with a refusal message listing reasons. Results are presented in a Streamlit UI that shows the answer, sources, latency, and model. A top-to-bottom diagram of this flow — including the rejected alternatives noted below — is in `docs/architecture_diagram.svg`.

![Architecture diagram](architecture_diagram.svg)

## Key Decisions

**Chunking.** A custom section-aware splitter divides each document into 700-character passages with 100 characters of overlap (the values in `src/chunker.py` since the file was committed; shorter prose claims elsewhere in this repo's history described tuning sessions that were never committed). It first splits on legal-style headers (Parts, Sections, Schedules, Articles), then on paragraph (double-newline) boundaries, falling back to sentence boundaries for any paragraph larger than the chunk limit. Generic fixed-length splitting would have sliced across section boundaries; with legal material that matters because section titles are what get surfaced as citations, and destroying those boundaries makes the citation field unreliable. The corpus yields **1,218 chunks**.

**Embedding model.** Passages are embedded locally with all-MiniLM-L6-v2 from sentence-transformers. The model runs on CPU with no external call, so there is zero per-query embedding cost and no rate-limit ceiling. Larger embeddings (e.g. bge-large, Cohere/OpenAI hosted endpoints) would give marginally better recall, but for a corpus of 1,218 chunks on a single topic domain the smaller model was sufficient and dramatically simpler to operate.

**Vector store.** ChromaDB runs as a persistent local store on disk. FAISS would have been marginally faster at query time, but Chroma ships with built-in persistence, collection management, and add/skip-idempotency semantics without extra glue code. At this corpus size (1,218 vectors) performance is not a constraint, so the operational simplicity wins.

**LLM.** Groq's hosted openai/gpt-oss-120b is used for generation. The free tier and sub-second generation speed mattered for iteration: the evaluation harness runs 50 questions through the full pipeline end-to-end and needs to be re-run after every change, which would be painful against a slow or paid endpoint. Answer quality is good enough that no more expensive model was needed for the regulatory-question task.

**Guardrails.** Four independent rule-based checks run after generation: (1) retrieval confidence (closest chunk within a distance threshold), (2) at least one well-formed citation, (3) clinical-question block (diagnosis, dosing, prescribing, treatment advice), and (4) minimum number of relevant chunks (out-of-corpus refusal). These are layered on the output of the model rather than folded into the system prompt, because prompt-only instruction proved unreliable in testing — on the intermediate checkpoint a clinical question produced a plausible but unsafe answer that a prompt instruction alone did not prevent, while a post-generation check reliably intercepted it.

**Threshold calibration.** The distance threshold shared by checks (1) and (4) started as an unmeasured guess of 0.8. It is now calibrated against the 50-question v1 run: the per-question minimum retrieved distance for answerable gold-hitting questions (median 0.472) versus unanswerable questions (median 1.010) separates best at 0.70 on both Youden's J and balanced accuracy. The old 0.8 let 6 of 25 unanswerable questions through this check; the calibrated value refuses 24 of 25 and would also refuse two answerable questions (Q7, Q15) — a published cost, not a hidden one. The full sweep, both distributions and the caveats are in `eval_results/threshold_calibration.md`; the value lives in `src/guardrails.py` as `CALIBRATED_MAX_DISTANCE` with a round-trip self-test.

**Evaluation methodology.** `run_eval.py` runs the frozen retrieval configuration (700/100 chunks, top-5, at most 3 chunks per document — `embed_store.MAX_PER_DOC`) over a hand-built golden set — 25 answerable questions with agent-graded gold chunks whose evidence strings are verified verbatim, and 25 unanswerable questions in four strata (clinical, out-of-corpus, near-miss, mixed). Each run records, per question: the retrieved chunk ids, sections and distances; the raw model output; the guardrail decision; latency; tokens; and what was ultimately shown to the user. Metrics (recall@5, context precision@5, MRR, citation correctness, grounded answer rate, refusal correctness, hallucination rate) are computed in-harness from committed artefacts and written to `eval_results/{prefix}_metrics.json`; the README tables are generated from those files by `analysis/render_results.py`, which fails `--check` if any document drifts from the run. The harness retries transient API errors with exponential backoff and supports `--resume` and `--strict`, so a run cannot end half-answered and still exit zero.

## What Was Rejected and Why

- **Fine-tuning** — unnecessary; a 30-question test set does not justify training, and RAG + prompt already handles the task.
- **Agents / tool use / multi-step reasoning** — adds latency and failure modes without benefit for single-hop regulatory lookups.
- **Voice, multi-language, chat history, user accounts, mobile client** — product-scope expansions beyond a single-turn Q&A prototype.
- **Ollama local fallback** — adds setup weight and binary dependencies with no practical benefit while the Groq free tier handles the load.
- **FAISS as the primary store** — see above; manual index persistence was not worth the engineering for this corpus size.
