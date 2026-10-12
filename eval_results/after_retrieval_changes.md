# After-Retrieval Change Log

Scope: retrieval-level fixes only (approved fix menu A/B/C/D). No guardrails, no answer-prompt
changes, no model / `max_seq_length` changes, `run_eval.py` untouched.

## 1. Source edits

### `src/chunker.py`
| Change | Function / symbol | Detail |
|---|---|---|
| B. Smaller chunks | module defaults `DEFAULT_MAX_CHARS`, `DEFAULT_OVERLAP_CHARS` | 2,000 → **700** chars, 100 → **100** chars overlap; argparse defaults updated (`--max-chars`, `--overlap`). `max_seq_length` left at 256. |
| D. Heading guards | `HEADING_TRAIL_PUNCT_RE`, `HEADING_TRAIL_PAREN_RE`, `HEADING_SEMICOLON_RE`, `HEADING_CONNECTIVE_END_RE`, `BODY_FRAGMENT_SINGLE_WORDS`, `looks_like_body_fragment()` | Reject heading candidates ending in `· ; : ,` or trailing `)`; reject body fragments (`Application`, `section 46 (1) of this Act ; and`, `Chapter 14).`). |
| D. List suppression | `BARE_LIST_ITEM_RE`, `DECIMAL_HEADING_RE`, `LIST_RUN_MIN_ITEMS=5`, `LIST_BRIDGE_MAX_CHARS=60`, `LIST_ITEM_MAX_CHARS=60`, `_bare_list_item()`, `_bridges_list_run()`, `heading_flags()` | Runs of ≥5 sequential bare-number items (HEFAMAA 1–20 facility list) are no longer promoted to sections; they stay body text under the previous valid label. Decimal headings (`4.1`, `8.3.1`, `Section 12`) still detected. |
| D. New pattern | `HEADING_PATTERNS` | Added `^How it works [-–] .+`. |
| A. Junk filter | `JUNK_MIN_CHARS=80`, `TRAILING_INTERPUNCT_RE`, `TOC_DOT_LEADER_RE`, `FRONT_MATTER_PATTERNS`, `_normalize_title()`, `junk_reason()`, emission loop in `main()` | Drop a chunk only if body < 80 chars **and** it matches TOC dot-leader / trailing interpunct / listed front-matter phrases; also drop when normalized `section_label == document title`. Per-doc drop log + phrase-hit diagnostics (kept-not-dropped) printed. |

### `src/embed_store.py`
| Change | Function / symbol | Detail |
|---|---|---|
| C. Query expansion | `QUERY_ACRONYM_EXPANSIONS`, `_expand_query()` | Expands standalone acronyms (CSHIS, HIUOR, BHCPF, QMS, MLSCN, NDPC, NDPA, NHIA, HEFAMAA) to spelled forms; expansion appended to the query before encoding only. |
| C. Doc diversity | `INTERNAL_FETCH_K=10`, `MAX_PER_DOC=2`, `query_store()` | Fetch k=10 from Chroma (over-fetch loop if diversity filter cannot fill `n_results`), keep ≤2 chunks per `doc_id` (closest first), return top `n_results`. Public signature `n_results=5` unchanged. |

### Rebuilt artifacts (not source edits)
`data/processed/*` and `chroma_db/*` deleted and rebuilt with the new defaults
(`venv\Scripts\python.exe src\chunker.py` then `build_vector_store()`).

### Deliberately untouched
`run_eval.py`, `answer.py` (system prompt), `guardrails.py`, MiniLM `max_seq_length=256`,
all PDFs / OCR sidecars, retrieval thresholds.

## 2. Corpus / build statistics (recomputed in-memory after rebuild)

Per-document kept / dropped / front-matter-phrase hits kept:

| source_id | chunks kept | dropped | phrase-hits kept | headers |
|---|---:|---:|---:|---:|
| ndpa_2023 | 159 | 0 | 5 | 79 |
| ndpc_guidance_2024 | 21 | 0 | 0 | 10 |
| nhia_act_2022 | 106 | 0 | 5 | 68 |
| nhia_guidance_2023 | 44 | 0 | 1 | 29 |
| hefamaa_requirements | 16 | 0 | 0 | 27 |
| mlscn_guidelines | 52 | 0 | 1 | 54 |
| national_health_act_2014 | 124 | 0 | 1 | 38 |
| who_lab_quality_guidance | 742 | 0 | 2 | 103 |
| **TOTAL** | **1,264** | **0** | **15** | 408 |

- Chunk sizes: min 77, **median 663**, mean 622.1, **max 699**, chunks over 700 chars: **0**.
- Junk filter dropped **nothing** in this corpus (the `<80 chars` gate means every TOC /
  front-matter line sits inside a longer chunk); 15 substantive chunks containing
  front-matter phrases were kept and logged as intended.
- Safety counters (post-edit): ghost `·`/`;`/`:` section labels **0**; HEFAMAA numeric-item
  fake sections **0** (facility list is body text under `How it works – Facility Types`);
  body-fragment labels **0**; HEFAMAA `How it works …` chunks **13**;
  MLSCN decimal headings (`8.3.1` etc.) intact.

### Known corpus gaps (not fixable at retrieval level)
Q20 / Q21 / Q22 reference the NHIA Operational Guidelines 2023, whose raw PDF is 22
front-matter pages (~25,460 OCR chars) — the substantive guidance is absent from the
corpus. Retrieval correctly returns the intro pages; these must be marked as corpus gaps
and excluded from final comparison. Q22 is partially answered from the NHIA Act instead.

## 3. Eval run

`venv\Scripts\python.exe run_eval.py --prefix after_retrieval` →
`eval_results/after_retrieval.csv`, `eval_results/after_retrieval_summary.md`.

(The first pass hit a transient Groq HTTP 429 on Q25; the same command was re-run once and
produced a clean 30/30 run. Retrieval results are byte-identical across both passes.)

| Metric | before_guardrails | after_retrieval |
|---|---:|---:|
| Retrieval accuracy (top-5 hit, 25 answerable) | 25/25 = 100% | 25/25 = 100% |
| Avg end-to-end latency | 12.53 s | **7.86 s** |
| Avg total tokens (in + out) | 2,047 | **1,528** |
| Refusals on answerable questions | 4 (Q7, Q10, Q20, Q21) | 6 (Q2, Q5, Q10, Q11, Q20, Q21) |
| Refusals on unanswerable questions (correct) | 5 (Q26–Q30) | 4 (Q26, Q28, Q29, Q30) |
| Answered unanswerable questions (wrong) | 0 | 1 (Q27) |

Existing checks still pass: `answer.py` citation regex self-tests (3/3) and
`src/test_retrieval.py` (10/10).

## 4. Effects on the 11 diagnosed questions

| Q | Bucket | Landed? | Evidence |
|---|---|---|---|
| Q7 emergency treatment (NHA §20) | B | **Yes** | `national_health_act_2014#0048` now at rank 2; model answers correctly. |
| Q9 "national health system" | D | **Yes** | Ghost `·` labels gone; `Interpretation` at rank 2; correct citation. |
| Q13 data-security measures | D | **Yes** | `section 46 (1) …` fragment label gone; `PART VII — D A TA SECURITY` at rank 2; correct answer. |
| Q17 NHIA establishment | A/B | **Yes** | TOC chunk no longer rank 1; `PART I—ESTABLISHMENT OF THE NA TIONAL HEALTH INSURANCE AUTHORITY` at rank 1. |
| Q25 WHO documentation requirements | D | **Yes** | `Chapter 14).` label gone; `16. Documents` at ranks 1–2; correct answer (Q25's first pass failed on a 429, not on retrieval). |
| Q22 NHIA guidance structure | — | Partial | Corpus gap; answered from the NHIA Act as before. |
| Q20 / Q21 NHIA Operational Guidelines | — | No (expected) | Corpus gap; refusal is the correct behaviour. |
| Q3 HEFAMAA facility categories | A/D | **No** | Label fixed (`How it works – Facility Types`), but the chunk sits outside the raw top-10; the per-doc cap gives HEFAMAA's 2 slots to other chunks. |
| Q5 MLSCN Quality System Essentials | B/C | **No** | Target chunk `mlscn_guidelines#0019` ("twelve (12) clauses") outside top-10; top-2 are cover-page chunks labelled `DECEMBER 2012`. |
| Q10 NDPA lawful bases | A | **No** | Junk filter dropped nothing (by design); `PART I—OBJECTIVES AND APPLICA TION` front-matter ×2 plus 2 NDPC chunks fill the top 5; the Part V body chunk is outside the fetched 10. |

## 5. Regressions introduced

- **Q2, Q5, Q11** flipped from answered to refusal (Q3, Q14 also refused in the first
  pass — these sit on the model's answer/refuse boundary and vary run to run).
- **Q27** (unanswerable: diagnosing malaria without a rapid test) flipped from a correct
  refusal to an answer built from MLSCN/WHO laboratory chunks — a new false answer that
  guardrails would have to catch.
- Mechanisms: (i) 700-char chunks plus query expansion changed raw ranking so target
  chunks of NDPA, MLSCN and HEFAMAA fall outside `INTERNAL_FETCH_K=10`; (ii) `MAX_PER_DOC=2`
  evicts the same document's winning chunk (Q3, Q5, Q10); (iii) the diversity filter admits
  weaker cross-document chunks (NDPC) that dilute the context.
