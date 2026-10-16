# GitHub repository settings — manual checklist

`gh` is not installed in the delivery environment and no `GH_TOKEN` /
`GITHUB_TOKEN` was available, so nothing below has been applied via API.
Each item is a copy-paste for the repository owner
(github.com/emmyagama/ng-health-reg-assistant). None of it is required
for the code or the numbers to be correct; all of it is required for a
stranger to find and trust the repo.

## Description (About panel)

```
Nigerian health-regulation Q&A assistant. Answers only from eight public
regulatory PDFs, cites every claim to document and section, refuses what
the corpus cannot answer. Measured on a 50-question gold set: refusal
correctness 1.000, hallucination 0.000 after guardrails, recall@5 0.379
(the weak layer, published).
```

## Topics

```
nigerian-law
health-regulation
retrieval-augmented-generation
rag
grounded-answering
citation-verification
healthtech
nlp
python
evaluation
```

## Default branch

`main` — must be the default. `b1-remediation` is merged and deletable
once CI on `main` is observed (see the release notes in `CHANGELOG.md`).

## Releases

Create a GitHub Release for the `v1.1.0` tag (v1.0.0 exists but is
superseded — leave the tag, mark the release notes "superseded by
v1.1.0"). Release-notes body: use the `CHANGELOG.md` v1.1.0 section.

## README badge

The CI badge in the README points at `.github/workflows/ci.yml`. It is
only honest if the workflow is green on `main`; if Actions is disabled
or the badge 404s, remove the badge line rather than shipping a red or
dead one.

## Issues / Discussions

Optional. If enabled, pin one issue template that asks for: the question
asked, the answer shown, the cited sections, and the run id. The system
cites sections; bug reports that quote them are actionable.

## What NOT to set

- No "production ready" topic or description claim — the README's
  limitations sections contradict it on purpose.
- No secrets in Actions secrets that the workflows do not read. The CI
  workflow needs no API key by design (self-tests run without one).
