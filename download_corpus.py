#!/usr/bin/env python3
"""download_corpus.py

Download a corpus of documents from a sources.json manifest, generate a
Markdown index of the sources, and optionally verify that every expected
file exists on disk.

Usage:
    python download_corpus.py              # download missing files + write sources.md
    python download_corpus.py --verify     # only check every file exists
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
SOURCES_JSON = DATA_DIR / "sources.json"
SOURCES_MD = DATA_DIR / "sources.md"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
TIMEOUT = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_sources() -> list[dict]:
    """Load and return the list of source entries from sources.json."""
    with SOURCES_JSON.open("r", encoding="utf-8") as f:
        sources = json.load(f)
    if not isinstance(sources, list):
        sys.exit("ERROR: sources.json must contain a JSON array.")
    return sources


def download_one(entry: dict) -> tuple[str, str]:
    """Attempt to download a single entry.

    Returns a status string: "ok", "skipped", or "failed".
    The second element is a human-readable message (used for failure detail).
    """
    sid = entry.get("id", "?")
    title = entry.get("title", "")
    url = entry.get("url", "")
    filename = entry.get("filename", "")

    if not filename:
        return "failed", f"missing 'filename' field"

    dest = RAW_DIR / filename
    if dest.exists():
        print(f"SKIP (already exists): {filename}")
        return "skipped", ""

    if not url:
        return "failed", "missing 'url' field"

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        return "failed", f"HTTP {resp.status_code}: {e}"
    except requests.exceptions.Timeout:
        return "failed", f"timeout after {TIMEOUT}s"
    except requests.exceptions.ConnectionError as e:
        return "failed", f"connection error: {e}"
    except requests.exceptions.RequestException as e:
        return "failed", f"request error: {e}"

    # Write the file
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        f.write(resp.content)

    print(f"OK   {filename}")
    return "ok", ""


def generate_sources_md(sources: list[dict]) -> None:
    """Write data/sources.md as a markdown table of all entries."""
    today = date.today().isoformat()

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
        pub = e.get("published_date", "")
        fname = e.get("filename", "")
        lines.append(
            f"| {sid} | {title} | {body} | {url} | {pub} | {today} | {fname} |"
        )

    SOURCES_MD.parent.mkdir(parents=True, exist_ok=True)
    SOURCES_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {SOURCES_MD}")


def verify(sources: list[dict]) -> int:
    """Check that every filename exists in data/raw/. Returns count of missing."""
    missing = []
    for e in sources:
        fname = e.get("filename", "")
        sid = e.get("id", "?")
        if not fname:
            missing.append((sid, "<no filename>"))
            continue
        if not (RAW_DIR / fname).exists():
            missing.append((sid, fname))

    if missing:
        print("\nMISSING files:")
        for sid, fname in missing:
            print(f"  [{sid}] {fname}")
    else:
        print("\nAll expected files are present in data/raw/ — OK.")

    print(f"Missing: {len(missing)} / {len(sources)}")
    return len(missing)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download a document corpus listed in data/sources.json."
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only verify that every expected file exists in data/raw/.",
    )
    args = parser.parse_args()

    if not SOURCES_JSON.exists():
        sys.exit(f"ERROR: {SOURCES_JSON} not found.")

    sources = load_sources()
    print(f"Loaded {len(sources)} source entr{'y' if len(sources)==1 else 'ies'} "
          f"from {SOURCES_JSON}\n")

    if args.verify:
        missing = verify(sources)
        sys.exit(0 if missing == 0 else 1)

    # --- Download phase ---
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    succeeded = 0
    failed = 0
    skipped = 0

    for entry in sources:
        sid = entry.get("id", "?")
        title = entry.get("title", "")
        status, detail = download_one(entry)
        if status == "ok":
            succeeded += 1
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1
            print(f"FAIL [{sid}] {title} — {detail}")

    # --- Summary ---
    total = len(sources)
    print(f"\n{'='*50}")
    print(f"Summary: {succeeded} succeeded, {failed} failed, {skipped} skipped "
          f"(total {total})")
    print(f"{'='*50}")

    # --- Generate sources.md ---
    generate_sources_md(sources)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
