# Reproduction log

Recorded wall-clock measurements for a third-party build of this repository.
Times are from the `b1-remediation` branch on a Windows 10 machine with an
otherwise normal developer environment (Git Bash, Python 3.11.9, ~40 Mbit/s
home broadband). They are measurements, not estimates.

## 2026-10-16 — Phase 1 stranger test (the publication gate)

Commands run, in order, from a clean state:

```bash
cd /tmp && rm -rf b1-stranger
git clone --branch b1-remediation https://github.com/emmyagama/ng-health-reg-assistant.git b1-stranger
cd b1-stranger
python -m venv .venv && source .venv/Scripts/activate
python -m pip install -r requirements.txt
time bash scripts/build.sh
```

| step | wall-clock |
| --- | --- |
| `git clone` | 9 s |
| `python -m venv .venv` | 20 s |
| `pip install -r requirements.txt` | 9 min 35 s (575 s) |
| `bash scripts/build.sh` | 11 min 3 s (663 s) |
| **total** | **21 min 7 s (1267 s)** |

Result: **`BUILD OK: 1218 chunks in 661s`**, exit code 0.

- Manual steps: **0**. One command after the install.
- Corpus: 8/8 sources downloaded and content-verified against
  `data/corpus.lock.json`; NHIA Operational Guidelines OCR'd to a
  25,460-char sidecar in 411 s.
- Chunk count: **1,218**, identical to the count produced by a build on the
  author's machine, per document:

  | source id | chunks |
  | --- | --- |
  | `ndpa_2023` | 159 |
  | `ndpc_guidance_2024` | 21 |
  | `nhia_act_2022` | 105 |
  | `nhia_guidance_2023` | 44 (from the OCR sidecar) |
  | `hefamaa_requirements` | 16 |
  | `mlscn_guidelines` | 49 |
  | `national_health_act_2014` | 124 |
  | `who_lab_quality_guidance` | 700 |

Caveats that a stranger should know about:

- **Python must be 3.10–3.12.** `rapidocr-onnxruntime==1.4.4` has no wheel for
  Python 3.13, so `pip install` fails there. `scripts/build.sh` refuses such an
  interpreter and falls back to the next one on `PATH`.
- The `pip install` time above was measured with a **warm pip cache** (the
  wheels had been downloaded earlier in the same session). A machine with a
  cold cache downloads roughly 500 MB of wheels on top of this.
- The Hugging Face cache was **cold** for this run (`HF_HOME` pointed at an
  empty directory), so the `all-MiniLM-L6-v2` download (~90 MB) is included in
  the `build.sh` time.
- The clone used `--branch b1-remediation` because the work is not merged to
  `main` yet. Once it is, `git clone <repo>` alone is the documented path.
- The bulk of the build time is the OCR of the 22-page NHIA scan
  (~7 min, CPU-only) and embedding 1,218 chunks (~1.5 min).

## 2026-10-16 — clean-venv dependency audit

`python -m venv` on Python 3.11.9, then `pip install -r requirements.txt`:
exit 0 in 615 s, `pip check` clean, and this all imports:

```python
import sentence_transformers, chromadb
from sentence_transformers import SentenceTransformer
SentenceTransformer("all-MiniLM-L6-v2")
```

with **no `torchvision` installed**. `torchvision` was therefore removed from
the requirements; it was never imported by this repository.
`numpy` and `pandas` were removed for the same reason (no importer here;
streamlit and chromadb still pull them in transitively, see
`requirements.lock.txt`).
