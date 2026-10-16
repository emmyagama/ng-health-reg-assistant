# Archived evaluation runs

These files are kept, not deleted, so the numbers that used to live in the
README can always be traced back to the run that produced them.

## `after_guardrails_INVALID_429.csv`

The "after guardrails" evaluation run of 2026-09-27. **28 of its 30 rows** are
`[GENERATION ERROR: RuntimeError: Groq API error (HTTP 429): ...]`, because the
Groq free-tier rate limit was hit mid-run and the harness had no retry and no
`--resume`. The `refused` column is empty for exactly those 28 rows, so the
run measured the rate limiter, not the pipeline. Do not quote any number from
this file. Replaced by the strict, resumable harness in `run_eval.py` (§2) and
by any run named `eval_results/b1_v*.csv` that it produces.

## `after_guardrails_summary_INVALID_429.md`

The summary written for that same failed run. It reports "avg latency 0.17 s /
avg tokens 97", which are artefacts of 28 rows that returned no answer at all —
averages computed over error rows, exactly what `run_eval.py` now refuses to
do. Kept only as evidence of the failure mode. Replaced by the generated
`*_summary.md` files, which state how many rows were excluded from every
average.
