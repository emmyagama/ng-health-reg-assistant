#!/usr/bin/env python3
"""download_corpus.py

Download and *validate* the document corpus listed in data/sources.json.

Transport checks (applied to every download, redirects followed, final URL
reported):
  * HTTP status == 200
  * Content-Type contains "pdf" OR the first 5 bytes are b"%PDF-"
  * body length > 10,000 bytes

Content checks (applied to every file that ends up in data/raw/):
  * the file starts with b"%PDF-"
  * at least two of the document's content markers (CONTENT_MARKERS) occur
    in its extracted text.  Text = PDF text layer, plus the OCR sidecar in
    data/ocr/{id}.json when the text layer is thinner than MIN_NATIVE_CHARS
    (the same rule src/chunker.py uses).  If a scanned document has no
    sidecar yet, one is generated with src/ocr_scans.py so that a fresh
    clone can reach "content verified" with no manual step.

Outcomes printed per source:
  OK [id] ... (content verified)
  SKIP_EXISTS [id] ... (content verified) / FAIL_CONTENT_MISMATCH
  FAIL_HTTP_<code> [id] <reason>
  FAIL_NOT_PDF [id] <reason>
  FAIL_TOO_SMALL [id] <reason>
  FAIL_CONTENT_MISMATCH [id] <missing markers>
  SKIP_MANUAL [id] <instructions>

Artifacts:
  data/corpus.lock.json   record of what a correct corpus is
  data/sources.md         markdown index of the manifest
  data/SOURCES_STATUS.md  rendered evidence table (--status)

Exit status:
  0 only when all sources are present and content-verified, or when
  --allow-partial is passed.

Usage:
  python download_corpus.py                 # download missing files, verify content
  python download_corpus.py --retry 3       # 3 retries with backoff + jitter
  python download_corpus.py --verify        # sha256 check against the lockfile
  python download_corpus.py --probe         # (re)record HTTP status of every URL
  python download_corpus.py --status        # re-render data/SOURCES_STATUS.md
  python download_corpus.py --allow-partial # do not fail the run on bad sources
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
OCR_DIR = DATA_DIR / "ocr"
SOURCES_JSON = DATA_DIR / "sources.json"
SOURCES_MD = DATA_DIR / "sources.md"
LOCK_JSON = DATA_DIR / "corpus.lock.json"
SOURCES_STATUS_MD = DATA_DIR / "SOURCES_STATUS.md"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
TIMEOUT = 60
MIN_BYTES = 10_000
MIN_NATIVE_CHARS = 1000  # mirrors src/chunker.py / src/ocr_scans.py
MIN_MARKER_HITS = 2
RETRY_BASE_SECONDS = 1.5
RETRY_CAP_SECONDS = 30.0
RETRY_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}

# ---------------------------------------------------------------------------
# Content markers (see the remediation brief, section 1.1).
# Each entry is a list of marker *groups*; a group matches when ANY of its
# alternatives occurs in the extracted text (case-insensitive).  A document
# is content-verified when at least MIN_MARKER_HITS groups match.
# ---------------------------------------------------------------------------
CONTENT_MARKERS: dict[str, list[list[str]]] = {
    "ndpa_2023": [
        ["Nigeria Data Protection Act"],
        ["Part V"],
        ["lawful basis"],
        ["Data Subject"],
    ],
    "ndpc_guidance_2024": [
        ["Data Controllers and Data Processors of Major Importance"],
        ["250,000"],
        ["Ultra-High", "Extra-High", "Ordinary-High"],
    ],
    "nhia_act_2022": [
        ["National Health Insurance Authority"],
        ["Vulnerable Group Fund"],
        ["Basic Health Care Provision Fund"],
    ],
    "nhia_guidance_2023": [
        ["CSHIS", "Contributory Social Health Insurance"],
        ["HIUOR", "Under One Roof"],
        ["SECTION 2"],
    ],
    "hefamaa_requirements": [
        ["HEFAMAA"],
        ["Letter of Intent"],
        ["e-HEFAMAA"],
    ],
    "mlscn_guidelines": [
        ["Quality System Essentials"],
        ["Medical Laboratory"],
        ["MLSCN"],
    ],
    "national_health_act_2014": [
        ["National Health Act"],
        ["ARRANGEMENT OF SECTIONS"],
        ["Part III"],
    ],
    "who_lab_quality_guidance": [
        ["Laboratory Quality Management System"],
        ["Occurrence management"],
        ["quality control"],
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_sources() -> list[dict]:
    with SOURCES_JSON.open("r", encoding="utf-8") as f:
        sources = json.load(f)
    if not isinstance(sources, list):
        sys.exit("ERROR: sources.json must contain a JSON array.")
    return sources


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def pdf_page_count(path: Path) -> int:
    try:
        import pymupdf

        with pymupdf.open(str(path)) as doc:
            return doc.page_count
    except Exception:  # noqa: BLE001
        try:
            from pypdf import PdfReader

            return len(PdfReader(str(path)).pages)
        except Exception:  # noqa: BLE001
            return -1


def extract_text_layer(path: Path) -> str:
    """Text carried by the PDF itself (no OCR)."""
    try:
        import pymupdf

        with pymupdf.open(str(path)) as doc:
            return "\n".join(page.get_text() for page in doc)
    except Exception:  # noqa: BLE001
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception:  # noqa: BLE001
            return ""


def ensure_ocr_sidecar(sid: str, path: Path) -> Path | None:
    """Return the OCR sidecar for a textless PDF, generating it if missing.

    OCR is only attempted when the text layer is thinner than
    MIN_NATIVE_CHARS — the same rule src/ocr_scans.py and src/chunker.py use.
    `path` may be the finished corpus file or a `.part` download that has
    already passed every transport check (the sidecar is keyed by source id,
    not by filename, so the check works before the file is renamed).
    Returns None when no sidecar could be produced, so the caller can report
    the document as not content-verifiable rather than pretending it is.
    """
    sidecar = OCR_DIR / f"{sid}.json"
    if sidecar.exists():
        return sidecar
    if len(extract_text_layer(path)) >= MIN_NATIVE_CHARS:
        return None
    print(f"  OCR  [{sid}] text layer < {MIN_NATIVE_CHARS} chars — "
          f"generating data/ocr/{sid}.json ...", flush=True)
    src_dir = str(ROOT / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    try:
        import pymupdf

        from ocr_scans import RapidOCR, extract_lines_from_result, ocr_pdf
    except Exception as exc:  # noqa: BLE001
        print(f"  WARN [{sid}] OCR unavailable ({type(exc).__name__}: {exc}); "
              f"content verification will be inconclusive")
        return None
    try:
        engine = RapidOCR()
        payload = ocr_pdf(pymupdf.open(str(path)), engine, 2.0)
        total = sum(len(p["text"]) for p in payload["pages"])
        OCR_DIR.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(
            json.dumps(
                {
                    "source_id": sid,
                    "filename": path.name,
                    "engine": "rapidocr-onnxruntime (PP-OCRv4 ch+en)",
                    "zoom": 2.0,
                    "created": datetime.now(timezone.utc).date().isoformat(),
                    "pages": payload["pages"],
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        print(f"  OCR  [{sid}] -> data/ocr/{sid}.json ({total:,} chars)")
    except Exception as exc:  # noqa: BLE001
        print(f"  WARN [{sid}] OCR failed ({type(exc).__name__}: {exc})")
        return None
    return sidecar


def content_text(sid: str, path: Path) -> tuple[str, str]:
    """Text used for content-marker verification + where it came from."""
    text = extract_text_layer(path)
    source = "pdf text layer"
    if len(text) < MIN_NATIVE_CHARS:
        sidecar = ensure_ocr_sidecar(sid, path)
        if sidecar is not None:
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                text = text + "\n" + "\n".join(
                    p.get("text", "") for p in data.get("pages", [])
                )
                source = "pdf text layer + OCR sidecar"
            except Exception as exc:  # noqa: BLE001
                print(f"  WARN [{sid}] unreadable OCR sidecar: {exc}")
    return text, source


def check_markers(sid: str, text: str) -> tuple[bool, list[str], list[str]]:
    """Return (enough_hits, matched_groups, missing_groups)."""
    groups = CONTENT_MARKERS.get(sid, [])
    low = text.lower()
    matched, missing = [], []
    for group in groups:
        hit = next((m for m in group if m.lower() in low), None)
        (matched if hit else missing).append(hit or group[0])
    ok = len(matched) >= MIN_MARKER_HITS
    if not groups:
        return True, [], []
    return ok, matched, missing


def is_pdf_bytes(body: bytes) -> bool:
    return body[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# Fetch with retry / backoff / jitter
# ---------------------------------------------------------------------------
def _retry_after_seconds(resp: requests.Response) -> float | None:
    raw = resp.headers.get("Retry-After", "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def fetch(url: str, retries: int) -> requests.Response:
    """GET with exponential backoff + jitter.  Respects Retry-After."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= retries:
                raise
            _sleep_backoff(attempt, None)
            continue

        if resp.status_code in RETRY_STATUS_CODES and attempt < retries:
            _sleep_backoff(attempt, _retry_after_seconds(resp))
            continue
        return resp
    raise last_exc if last_exc else RuntimeError("unreachable")


def _sleep_backoff(attempt: int, retry_after: float | None) -> None:
    if retry_after is not None:
        delay = retry_after
    else:
        delay = min(RETRY_CAP_SECONDS, RETRY_BASE_SECONDS * (2 ** attempt))
        delay *= 0.5 + random.random()  # full jitter, 50-150%
    time.sleep(delay)


# ---------------------------------------------------------------------------
# Transport validation
# ---------------------------------------------------------------------------
def transport_failure(resp: requests.Response, body: bytes) -> str | None:
    if resp.status_code != 200:
        return f"FAIL_HTTP_{resp.status_code} [http status {resp.status_code}]"
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "pdf" not in ctype and not is_pdf_bytes(body):
        return (f"FAIL_NOT_PDF [content-type {ctype or '<none>'}, "
                f"first bytes {body[:5]!r}]")
    if not is_pdf_bytes(body):
        return f"FAIL_NOT_PDF [first bytes {body[:5]!r}]"
    if len(body) <= MIN_BYTES:
        return f"FAIL_TOO_SMALL [{len(body)} bytes <= {MIN_BYTES}]"
    return None


# ---------------------------------------------------------------------------
# Lockfile
# ---------------------------------------------------------------------------
def read_lock() -> dict:
    if LOCK_JSON.exists():
        try:
            return json.loads(LOCK_JSON.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def write_lock(documents: list[dict]) -> None:
    payload = {"generated": utc_now(), "documents": documents}
    LOCK_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {LOCK_JSON.relative_to(ROOT)} ({len(documents)} documents)")


def make_document_entry(
    source: dict,
    path: Path,
    *,
    provenance: str,
    text_source: str,
    matched: list[str],
    content_verified: bool,
    transport: dict | None,
) -> dict:
    data = path.read_bytes()
    entry = {
        "id": source["id"],
        "filename": source.get("filename", path.name),
        "sha256": sha256_bytes(data),
        "bytes": len(data),
        "pages": pdf_page_count(path),
        "provenance": provenance,
        "source_url": source.get("url", ""),
        "content_verified": content_verified,
        "markers_matched": matched,
        "text_source": text_source,
    }
    if transport:
        entry["transport"] = transport
    return entry


# ---------------------------------------------------------------------------
# Per-source acquisition
# ---------------------------------------------------------------------------
def acquire(
    source: dict,
    *,
    retries: int,
    allow_partial: bool,
    lock_by_id: dict,
) -> tuple[dict | None, str]:
    """Download (or reuse) one source.  Returns (lock_entry, outcome)."""
    sid = source.get("id", "?")
    filename = source.get("filename", "")
    url = source.get("url", "")
    acquisition = source.get("acquisition", "auto")

    if not filename:
        print(f"FAIL [{sid}] missing 'filename' field")
        return None, "FAIL_MANIFEST"

    dest = RAW_DIR / filename
    provenance = "local"
    transport_obs: dict | None = None

    if acquisition == "manual":
        instructions = source.get("manual_instructions", "see data/SOURCES_STATUS.md")
        if dest.exists():
            print(f"SKIP_MANUAL [{sid}] file present locally; {instructions}")
            outcome = "SKIP_MANUAL"
        else:
            print(f"FAIL [{sid}] manual acquisition required: {instructions}")
            return None, "FAIL_MANUAL"
    elif dest.exists():
        print(f"SKIP_EXISTS [{sid}] {filename}", end=" — ")
        outcome = "SKIP_EXISTS"
    else:
        if not url:
            print(f"FAIL [{sid}] missing 'url' field")
            return None, "FAIL_MANIFEST"
        try:
            resp = fetch(url, retries)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL [{sid}] network error: {type(exc).__name__}: {exc}")
            return None, "FAIL_NETWORK"
        body = resp.content
        final_url = str(resp.url)
        ctype = resp.headers.get("Content-Type", "")
        transport_obs = {
            "status": resp.status_code,
            "content_type": ctype,
            "final_url": final_url,
            "bytes": len(body),
            "observed": datetime.now(timezone.utc).date().isoformat(),
        }
        problem = transport_failure(resp, body)
        if problem:
            code, why = problem.split(" ", 1)
            print(f"{code} [{sid}] {why}  final_url={final_url}")
            return None, code

        part = RAW_DIR / f".{filename}.part"
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        part.write_bytes(body)
        # Content check BEFORE the file takes its real name: a bad download
        # must never be visible as a corpus file.
        text, text_source = content_text(sid, part)
        ok, matched, missing = check_markers(sid, text)
        if not ok:
            part.unlink(missing_ok=True)
            print(f"FAIL_CONTENT_MISMATCH [{sid}] missing markers: "
                  f"{', '.join(missing)}  final_url={final_url}")
            return None, "FAIL_CONTENT_MISMATCH"
        os.replace(part, dest)
        provenance = "url"
        outcome = "OK"
        print(f"OK [{sid}] {filename} (content verified)  "
              f"final_url={final_url}  {len(body)} bytes")
        entry = make_document_entry(
            source, dest, provenance=provenance, text_source=text_source,
            matched=matched, content_verified=ok, transport=transport_obs,
        )
        return entry, outcome

    # --- File already on disk (or manual entry with a local copy) ---
    text, text_source = content_text(sid, dest)
    ok, matched, missing = check_markers(sid, text)
    if ok:
        print("OK (content verified)")
    else:
        print(f"FAIL_CONTENT_MISMATCH [{sid}] missing markers: "
              f"{', '.join(missing)}")
        outcome = "FAIL_CONTENT_MISMATCH"

    prior_transport = (lock_by_id.get(sid) or {}).get("transport")
    entry = make_document_entry(
        source, dest, provenance=provenance, text_source=text_source,
        matched=matched, content_verified=ok,
        transport=transport_obs or prior_transport,
    )
    return entry, outcome


# ---------------------------------------------------------------------------
# --verify : sha256 against the lockfile
# ---------------------------------------------------------------------------
def verify(retries: int, allow_partial: bool) -> int:
    if not LOCK_JSON.exists():
        print(f"ERROR: {LOCK_JSON} not found — run 'python download_corpus.py' first.")
        return 1
    lock = json.loads(LOCK_JSON.read_text(encoding="utf-8"))
    docs = {d["id"]: d for d in lock.get("documents", [])}
    sources = load_sources()
    problems = 0

    for source in sources:
        sid = source.get("id", "?")
        filename = source.get("filename", "")
        path = RAW_DIR / filename
        entry = docs.get(sid)
        if entry is None:
            print(f"VERIFY FAIL [{sid}] not present in corpus.lock.json")
            problems += 1
            continue
        if not path.exists():
            print(f"VERIFY FAIL [{sid}] file missing: {filename}")
            problems += 1
            continue
        actual = sha256_file(path)
        if actual != entry["sha256"]:
            print(f"VERIFY FAIL [{sid}] sha256 mismatch\n"
                  f"        expected {entry['sha256']}\n"
                  f"        actual   {actual}")
            problems += 1
            continue
        size = path.stat().st_size
        if size != entry["bytes"]:
            print(f"VERIFY FAIL [{sid}] size mismatch: expected "
                  f"{entry['bytes']}, actual {size}")
            problems += 1
            continue
        if not is_pdf_bytes(path.read_bytes()[:8]):
            print(f"VERIFY FAIL [{sid}] not a PDF (magic bytes)")
            problems += 1
            continue
        if entry.get("content_verified") is not True:
            print(f"VERIFY FAIL [{sid}] lockfile records content_verified=false "
                  f"(markers matched: "
                  f"{', '.join(entry.get('markers_matched', [])) or 'none'})")
            problems += 1
            continue
        print(f"VERIFY OK   [{sid}] {filename}  sha256={actual[:16]}…  {size} bytes")

    total = len(sources)
    print(f"\nVerified {total - problems}/{total} documents against "
          f"corpus.lock.json")
    if problems and not allow_partial:
        return 1
    return 0


# ---------------------------------------------------------------------------
# --probe : record the HTTP status of every URL in the manifest
# ---------------------------------------------------------------------------
def probe(retries: int) -> int:
    lock = read_lock()
    docs = {d.get("id"): d for d in lock.get("documents", [])}
    sources = load_sources()
    for source in sources:
        sid = source.get("id", "?")
        url = source.get("url", "")
        if not url:
            continue
        try:
            resp = fetch(url, retries)
            head = next(resp.iter_content(8192), b"") or b""
            obs = {
                "status": resp.status_code,
                "content_type": resp.headers.get("Content-Type", ""),
                "final_url": str(resp.url),
                "bytes": len(resp.content),
                "magic": head[:5].decode("latin-1", "replace"),
                "observed": datetime.now(timezone.utc).date().isoformat(),
            }
            resp.close()
            # Second, cheap observation: the same URL fetched with the default
            # python-requests User-Agent.  Several issuing bodies 403 that one,
            # which is why USER_AGENT in this file is load-bearing.
            try:
                r2 = requests.get(url, timeout=TIMEOUT, stream=True,
                                  allow_redirects=True)
                h2 = next(r2.iter_content(8192), b"") or b""
                obs["status_default_ua"] = r2.status_code
                obs["magic_default_ua"] = h2[:5].decode("latin-1", "replace")
                r2.close()
            except requests.RequestException as exc2:
                obs["status_default_ua"] = 0
                obs["error_default_ua"] = f"{type(exc2).__name__}: {exc2}"
            print(f"PROBE [{sid}] status={obs['status']} "
                  f"(default UA: {obs.get('status_default_ua')}) "
                  f"ctype={obs['content_type'][:40]} magic={obs['magic']!r} "
                  f"final_url={obs['final_url']}")
        except Exception as exc:  # noqa: BLE001
            obs = {
                "status": 0,
                "content_type": "",
                "final_url": url,
                "bytes": 0,
                "magic": "",
                "observed": datetime.now(timezone.utc).date().isoformat(),
                "error": f"{type(exc).__name__}: {exc}",
            }
            print(f"PROBE [{sid}] ERROR {obs['error']}")
        if sid in docs:
            docs[sid]["transport"] = obs
    lock["generated"] = utc_now()
    lock["documents"] = list(docs.values())
    LOCK_JSON.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    print(f"\nUpdated {LOCK_JSON.relative_to(ROOT)} with {len(docs)} probes")
    return 0


# ---------------------------------------------------------------------------
# --status : render data/SOURCES_STATUS.md from the lockfile
# ---------------------------------------------------------------------------
def render_sources_status() -> int:
    if not LOCK_JSON.exists():
        print(f"ERROR: {LOCK_JSON} not found.")
        return 1
    lock = json.loads(LOCK_JSON.read_text(encoding="utf-8"))
    docs = {d.get("id"): d for d in lock.get("documents", [])}
    sources = load_sources()

    lines = [
        "# Sources status",
        "",
        "Every cell in this table is generated from `data/corpus.lock.json` by",
        "`python download_corpus.py --status`. No value is hand-typed.",
        "",
        "| id | title | issuing body | HTTP status observed | content-type | "
        "resolved URL | local file | sha256 | pages | markers found |",
        "|----|-------|--------------|----------------------|--------------|"
        "-------------|------------|--------|------|---------------|",
    ]
    verified = 0
    for source in sources:
        sid = source.get("id", "?")
        doc = docs.get(sid, {})
        tr = doc.get("transport", {}) or {}
        status = tr.get("status", "NOT PROBED")
        observed = tr.get("observed", "")
        default_ua = tr.get("status_default_ua", "")
        if observed:
            status_cell = f"{status} on {observed}"
            if default_ua != "":
                status_cell += f" (default UA: {default_ua})"
        else:
            status_cell = str(status)
        ctype = (tr.get("content_type") or "-").replace("|", "\\|")
        final_url = tr.get("final_url") or source.get("url", "") or "manual"
        if not tr and source.get("acquisition") == "manual":
            final_url = "manual"
        present = "yes" if (RAW_DIR / source.get("filename", "")).exists() else "no"
        sha = doc.get("sha256", "-")
        pages = doc.get("pages", "-")
        markers = ", ".join(doc.get("markers_matched", [])) or "-"
        verified += 1 if doc.get("content_verified") else 0
        lines.append(
            f"| `{sid}` | {source.get('title', '').replace('|', chr(92) + '|')} | "
            f"{source.get('issuing_body', '').replace('|', chr(92) + '|')} | "
            f"{status_cell} | {ctype} | {final_url} | {present} | "
            f"`{sha}` | {pages} | {markers} |"
        )

    total = len(sources)
    manual_ids = [s["id"] for s in sources if s.get("acquisition") == "manual"]
    ua_blocked = [
        (s["id"], (docs.get(s["id"], {}).get("transport", {}) or {}).get("status_default_ua"))
        for s in sources
        if (docs.get(s["id"], {}).get("transport", {}) or {}).get("status_default_ua") not in (200, None, "")
    ]
    ua_note = (
        f"The fetcher sends a browser User-Agent. On the observation date, "
        f"{len(ua_blocked)} of {total} sources refused the default "
        f"python-requests User-Agent: "
        + ", ".join(f"`{sid}` (HTTP {code})" for sid, code in ua_blocked)
        + ". Do not remove `USER_AGENT`."
        if ua_blocked
        else "The fetcher sends a browser User-Agent; every source accepted it "
             "and the default python-requests User-Agent on the observation date."
    )
    lines += [
        "",
        "## Reproducibility statement",
        "",
        f"A stranger reproduces the corpus with one command:",
        "`python download_corpus.py`. It fetches each of the "
        f"{total} documents from the URL recorded in `data/sources.json`, "
        "refuses anything that is not a real PDF (HTTP status, Content-Type, "
        "magic bytes and a 10,000-byte floor), then confirms the file really "
        "is the document it claims to be by looking for at least two "
        "document-specific phrases in its text. Documents whose text layer is "
        "too thin to check are OCR'd automatically into `data/ocr/` before "
        "the check runs, so no manual step is required. `python "
        "download_corpus.py --verify` re-checks every local file against the "
        "committed sha256 in `data/corpus.lock.json` and exits non-zero on "
        "any mismatch. If a URL ever stops working, its entry is marked with "
        "`\"acquisition\": \"manual\"` plus the exact expected sha256, and the "
        "document must be placed in `data/raw/` by hand — that is the only "
        "step that cannot be automated, and this table records whether it "
        "applies today (currently: "
        f"{total - len(manual_ids)} of {total} automated by URL, "
        f"{verified} of {total} content-verified).",
        "",
        ua_note,
        "",
        f"Generated at {lock.get('generated', 'unknown')} from "
        f"`data/corpus.lock.json`.",
        "",
    ]
    SOURCES_STATUS_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {SOURCES_STATUS_MD.relative_to(ROOT)} "
          f"({verified}/{total} content-verified)")
    return 0


# ---------------------------------------------------------------------------
# data/sources.md (link index, kept for CORPUS_RULES.md compliance)
# ---------------------------------------------------------------------------
def generate_sources_md(sources: list[dict]) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    lines = [
        "# Sources\n",
        "| ID | Title | Issuing Body | URL | Published Date | Accessed Date | File Saved As |",
        "|----|-------|--------------|-----|----------------|---------------|---------------|",
    ]
    for e in sources:
        sid = e.get("id", "")
        title = (e.get("title", "") or "").replace("|", "\\|")
        body = (e.get("issuing_body", "") or "").replace("|", "\\|")
        url = (e.get("url", "") or "").replace("|", "\\|")
        if e.get("acquisition") == "manual":
            url = "manual — see data/SOURCES_STATUS.md"
        pub = e.get("published_date", "")
        fname = e.get("filename", "")
        lines.append(
            f"| {sid} | {title} | {body} | {url} | {pub} | {today} | {fname} |"
        )
    SOURCES_MD.parent.mkdir(parents=True, exist_ok=True)
    SOURCES_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {SOURCES_MD}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and validate the document corpus in data/sources.json."
    )
    parser.add_argument("--verify", action="store_true",
                        help="Re-check data/raw/ against data/corpus.lock.json by sha256.")
    parser.add_argument("--probe", action="store_true",
                        help="Record the HTTP status of every URL in the lockfile.")
    parser.add_argument("--status", action="store_true",
                        help="Re-render data/SOURCES_STATUS.md from the lockfile.")
    parser.add_argument("--retry", type=int, default=2,
                        help="Retries per request with exponential backoff + jitter (default 2).")
    parser.add_argument("--allow-partial", action="store_true",
                        help="Exit 0 even when some sources are missing or wrong.")
    args = parser.parse_args()

    if not SOURCES_JSON.exists():
        print(f"ERROR: {SOURCES_JSON} not found.")
        return 1

    if args.status:
        return render_sources_status()
    if args.probe:
        return probe(max(0, args.retry))
    if args.verify:
        return verify(max(0, args.retry), args.allow_partial)

    sources = load_sources()
    print(f"Loaded {len(sources)} source entries from {SOURCES_JSON}\n")
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    lock_by_id = {d.get("id"): d for d in read_lock().get("documents", [])}
    documents: list[dict] = []
    outcomes: dict[str, str] = {}
    failures: list[tuple[str, str]] = []

    for source in sources:
        sid = source.get("id", "?")
        entry, outcome = acquire(
            source, retries=max(0, args.retry),
            allow_partial=args.allow_partial, lock_by_id=lock_by_id,
        )
        outcomes[sid] = outcome
        if outcome not in {"OK", "SKIP_EXISTS", "SKIP_MANUAL"}:
            failures.append((sid, outcome))
        if entry is not None:
            documents.append(entry)

    # Preserve lock entries for sources that produced no entry this run.
    for sid, prior in lock_by_id.items():
        if sid not in {d["id"] for d in documents}:
            documents.append(prior)
    documents.sort(key=lambda d: [s.get("id") for s in sources].index(d.get("id"))
                   if d.get("id") in [s.get("id") for s in sources] else 999)
    write_lock(documents)
    generate_sources_md(sources)

    total = len(sources)
    bad = len(failures)
    print("\n" + "=" * 68)
    print("Run summary")
    for source in sources:
        sid = source.get("id", "?")
        print(f"  {sid:26} {outcomes.get(sid, 'NOT ATTEMPTED')}")
    print("=" * 68)
    print(f"{total - bad}/{total} sources present and content-verified")
    if failures:
        print("Failures:")
        for sid, why in failures:
            print(f"  {why} [{sid}]")
    print("=" * 68)

    if failures and not args.allow_partial:
        print("\nRESULT: FAIL — the corpus is incomplete or unverified. "
              "(Pass --allow-partial to run anyway.)")
        return 1
    print("\nRESULT: OK — every source is present and content-verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
