#!/usr/bin/env python3
"""Inventory every candidate corpus file: filename | first bytes | pages | size | sha256.

Reproducible evidence helper. Flags any file whose first bytes are not %PDF-.
Usage: python scripts/inventory.py [root ...]
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

try:
    import fitz  # pymupdf
except ImportError:  # pragma: no cover
    fitz = None


def page_count(path: pathlib.Path) -> str:
    if path.read_bytes()[:5] != b"%PDF-":
        return "n/a (not a PDF)"
    if fitz is None:
        return "n/a (pymupdf missing)"
    try:
        with fitz.open(path) as doc:
            return str(doc.page_count)
    except Exception as exc:  # noqa: BLE001
        return f"n/a ({type(exc).__name__})"


def main(argv: list[str]) -> int:
    roots = [pathlib.Path(a) for a in argv] or [pathlib.Path("data/raw")]
    files: list[pathlib.Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"))
    print(f"{'filename':45} {'first8':12} {'pages':>8} {'bytes':>10} sha256")
    bad = []
    for p in files:
        data = p.read_bytes()
        magic = data[:8]
        ok = data[:5] == b"%PDF-"
        if not ok:
            bad.append(p.name)
        print(f"{p.name:45} {magic!r:12} {page_count(p):>8} {len(data):>10} {hashlib.sha256(data).hexdigest()}")
    if bad:
        print("NON-PDF FILES:", ", ".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
