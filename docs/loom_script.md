# Loom demo — shot list (video not yet recorded)

`LOOM_RECORDED = no`. This file is the shot list for a 3–5 minute screen
recording; nothing here has been filmed. When recorded, link the video
from the README and from `deliverables/sample-go-live-evidence-pack.md`.

Target runtime: 3–4 minutes. One take, screen + voice, no edits beyond
trimming dead air. Every command shown must be copy-pasteable from the
README.

---

## Shot 1 — What it is (0:00–0:20)

Screen: repo README top, scrolled to the one-line description.

Say: this is a question-answering assistant over eight Nigerian health
regulation PDFs. It answers only from those documents, cites every claim
to a document and section, and refuses what the documents cannot answer.
The rest of this video is me proving that, not asserting it.

## Shot 2 — One question, end to end (0:20–1:10)

Screen: terminal, repo root. Then `python app.py` (Streamlit) if a browser
is available; otherwise `python src/ask.py "..."` style one-shot if the
repo exposes it — otherwise run the guarded answer path directly.

Say: watch one compliance question go through retrieval, generation, and
the four guardrails. The answer names its section; the guardrail stack
would block a clinical question, a fabricated citation, or a
clearly-out-of-corpus question before display.

Show at least one refused question in the same shot so the refusal is
seen, not just described.

## Shot 3 — The evidence, not the demo (1:10–2:20)

Screen: README evaluation table (`analysis/render_results.py --check`).

Say: every number in that table is generated from a committed 50-question
run, not typed. `--check` fails the build if a document drifts from the
run. Point at three rows: recall@5 0.379 (the weak layer, stated as
weak), refusal correctness 1.000 (25/25), hallucination rate 0.000 after
guardrails against 0.080 before them — 2 of 25 raw answers were
fabricated and both were intercepted.

## Shot 4 — The failure register (2:20–3:00)

Screen: generated failure-counts table in `notes/failure_modes.md`.

Say: this is what is wrong with it, counted per class with question ids.
Five over-refusals, all the model's own; two correct refusals on a
documented corpus gap; one over-answer on that same gap (Q22), which I am
not hiding because it is uncomfortable. The NHIA guidance PDF is a scan
whose body was never recovered — that is my corpus's fault, and it is
documented in `data/SOURCES_STATUS.md`.

## Shot 5 — Reproduce it yourself (3:00–3:40)

Screen: fresh clone in a temp directory (or reference
`docs/reproduction_log.md` and show the build running).

Say: one command sequence, zero manual steps, about twenty minutes to a
verified 8/8 corpus and 1,218 chunks — 20 min 7 s on the second stranger
test, 21 min 7 s on the first. The sha256 lockfile pins every
source; `download_corpus.py --verify` re-checks all eight. If you can
clone and run this, the numbers above are yours to falsify.

## Shot 6 — Close (3:40–4:00)

Screen: `docs/method_note.md` top.

Say: the point was never that it answers well — it is that when it is
wrong, the wrongness is counted, attributed to a layer, and published.
MIT licence, open repo, contact in the README.

---

## Not in the video

- Any claim not backed by a committed artefact.
- The words "production ready". It is not; the README's limitations
  sections say why.
- Live API failures or rate-limit retries (mention them in Shot 3 if
  they occur; do not re-shoot).
