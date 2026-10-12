#!/usr/bin/env python3
"""ocr_scans.py

OCR the raw PDFs in data/raw/ that have no usable text layer (scanned
gazettes, CamScanner copies) and write per-page text sidecars to
data/ocr/{source_id}.json. src/chunker.py picks these up automatically.

A PDF is considered "no usable text" when page extraction yields fewer
than --min-chars characters in total.

Usage:
    python src/ocr_scans.py                 # OCR every textless PDF
    python src/ocr_scans.py --only nhia_guidance_2023
    python src/ocr_scans.py --force         # redo even if a sidecar exists

Requires: pymupdf, rapidocr-onnxruntime (see requirements.txt).
"""

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pymupdf
from pypdf import PdfReader
from rapidocr_onnxruntime import RapidOCR

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
SOURCES_JSON = ROOT / "data" / "sources.json"
OCR_DIR = ROOT / "data" / "ocr"

DEFAULT_MIN_CHARS = 1000
DEFAULT_ZOOM = 2.0


def native_chars(path: Path) -> int:
    try:
        reader = PdfReader(str(path))
        return sum(len(p.extract_text() or "") for p in reader.pages)
    except Exception:
        return 0


def extract_lines_from_result(result) -> list[str]:
    """Normalize any RapidOCR return shape into a list of text lines."""
    if not result:
        return []
    if isinstance(result, tuple):
        result = result[0]
    if not result:
        return []
    lines = []
    for item in result:
        if isinstance(item, dict):
            text = item.get("text", "")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            text = item[1]
        else:
            text = str(item)
        text = str(text).strip()
        if text:
            lines.append(text)
    return lines


def ocr_pdf(path: Path, ocr: RapidOCR, zoom: float) -> dict:
    doc = pymupdf.open(str(path))
    pages = []
    for i, page in enumerate(doc, 1):
        start = time.perf_counter()
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        result = ocr(pix.tobytes("png"))
        lines = extract_lines_from_result(result)
        elapsed = time.perf_counter() - start
        print(f"  page {i:3d}/{len(doc)}: {len(lines):4d} lines "
              f"({elapsed:.1f}s)", flush=True)
        pages.append({"page": i, "text": "\n".join(lines)})
    doc.close()
    return {"pages": pages}


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR textless corpus PDFs.")
    parser.add_argument("--min-chars", type=int, default=DEFAULT_MIN_CHARS)
    parser.add_argument("--zoom", type=float, default=DEFAULT_ZOOM)
    parser.add_argument("--only", type=str, default="",
                        help="comma-separated source ids to process")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    sources = json.loads(SOURCES_JSON.read_text(encoding="utf-8"))
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    OCR_DIR.mkdir(parents=True, exist_ok=True)

    engine = None
    done, skipped, missing = [], [], []

    for entry in sources:
        sid = entry.get("id", "?")
        fname = entry.get("filename", "")
        if only and sid not in only:
            continue
        path = RAW_DIR / fname
        sidecar = OCR_DIR / f"{sid}.json"

        if not path.exists():
            missing.append(sid)
            continue

        chars = native_chars(path)
        if chars >= args.min_chars:
            print(f"SKIP [{sid}] native text OK ({chars:,} chars)")
            continue
        if sidecar.exists() and not args.force:
            print(f"SKIP [{sid}] sidecar exists ({sidecar.name})")
            continue

        print(f"OCR  [{sid}] {fname} — native text {chars:,} chars "
              f"< {args.min_chars:,}", flush=True)
        if engine is None:
            engine = RapidOCR()

        t0 = time.perf_counter()
        payload = ocr_pdf(path, engine, args.zoom)
        elapsed = time.perf_counter() - t0

        total = sum(len(p["text"]) for p in payload["pages"])
        sidecar.write_text(
            json.dumps(
                {
                    "source_id": sid,
                    "filename": fname,
                    "engine": "rapidocr-onnxruntime (PP-OCRv4 ch+en)",
                    "zoom": args.zoom,
                    "created": date.today().isoformat(),
                    "pages": payload["pages"],
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        print(f"  -> {total:,} chars in {elapsed:.0f}s -> {sidecar.name}",
              flush=True)
        done.append((sid, total, elapsed))

    print("\n" + "=" * 60)
    if done:
        print("OCR'd:")
        for sid, total, elapsed in done:
            print(f"  {sid:34s} {total:>8,} chars  {elapsed:>6.0f}s")
    else:
        print("Nothing OCR'd.")
    if missing:
        print(f"Missing files: {', '.join(missing)}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
