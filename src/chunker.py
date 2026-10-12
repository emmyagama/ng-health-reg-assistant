#!/usr/bin/env python3
"""chunker.py

Split the raw PDF corpus in data/raw/ into retrieval-sized text chunks and
write them to data/processed/chunks.jsonl.

Each chunk keeps its provenance (source id, title, issuing body, section
heading, starting page) so the assistant can cite the document and section
behind every answer.

Strategy:
  1. Extract text page by page with pypdf.
  2. Drop running headers/footers (lines repeated across pages) and bare
     page numbers.
  3. Detect section headers (PART/SECTION/CHAPTER, numbered headings,
     roman numerals, ALL-CAPS lines, known legal section words).
  4. If a document yields zero headers, print a "no headers detected"
     fallback warning and chunk that document by fixed-size windows
     instead.
  5. Pack lines into chunks up to --max-chars with --overlap chars of
     overlap carried between chunks.

Usage:
    python src/chunker.py
    python src/chunker.py --max-chars 700 --overlap 100
"""

import argparse
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

# Windows consoles default to cp1252; force UTF-8 for the warning glyphs.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
SOURCES_JSON = ROOT / "data" / "sources.json"
OCR_DIR = ROOT / "data" / "ocr"
DEFAULT_OUT = ROOT / "data" / "processed" / "chunks.jsonl"

REPEAT_PAGES = 3
MIN_SECTION_CHARS = 400
MIN_NATIVE_CHARS = 1000

# Keep chunks comfortably inside all-MiniLM-L6-v2's 256-token window
# (~4 chars/token): 700 chars ~= 175 tokens.
DEFAULT_MAX_CHARS = 700
DEFAULT_OVERLAP_CHARS = 100

# Running-header filter: a short line that repeats on this many pages is a
# page header/footer, not body text or a section heading.
PAGE_NUMBER_RE = re.compile(r"^\s*(?:page\s+)?-?\s*\d{1,4}\s*-?\s*$", re.I)
PAGE_LABEL_RE = re.compile(r"^\s*page\s+\d+(\s+of\s+\d+)?\s*$", re.I)

HEADING_PATTERNS = [
    re.compile(
        r"^(PART|SECTION|CHAPTER|SCHEDULE|ANNEXE?|APPENDIX|SUBSIDIARY"
        r"\s+SCHEDULE)\b",
        re.I,
    ),
    re.compile(r"^\d{1,2}(?:\.\d{1,2}){0,2}\.?\s+\S"),
    re.compile(r"^[IVXLC]{1,7}\.\s+\S"),
    re.compile(
        r"^(INTRODUCTION|INTERPRETATION|DEFINITIONS?|OBJECTIVES?|APPLICATION|"
        r"CITATION|SHORT\s+TITLE|GENERAL\s+PROVISIONS|PRELIMINARY)\b",
        re.I,
    ),
    # HEFAMAA quick-guide step pages ("How it works – Register Facility").
    re.compile(r"^How it works [\-\u2013]\s*.+"),
]
CAPS_HEADING_MIN_WORDS = 2
CAPS_HEADING_MAX_WORDS = 14
CAPS_HEADING_MAX_CHARS = 95
NUMBERED_HEADING_MAX_CHARS = 95
NUMBERED_HEADING_MAX_WORDS = 14

# ---------------------------------------------------------------------------
# Heading-quality guards (bucket D): OCR ghost lines / body fragments must not
# be promoted to section headings. Rejected candidates keep the previous valid
# label (they are treated as body text).
# ---------------------------------------------------------------------------
# Ends with OCR interpunct or other "sentence" punctuation.
HEADING_TRAIL_PUNCT_RE = re.compile(r"[·;:,]\s*$")
HEADING_TRAIL_PAREN_RE = re.compile(r"\)\s*\.?$")
HEADING_SEMICOLON_RE = re.compile(r";")
# Trailing connective words are the tell-tale of a mid-sentence clause.
HEADING_CONNECTIVE_END_RE = re.compile(
    r"\b(and|or|of|to|for|the|in|by|with|under|as|is|are|from|at|on)\s*\.?$", re.I
)
# Single words that only look like headings when seen out of context.
BODY_FRAGMENT_SINGLE_WORDS = {"application"}

# Sequential bare-numbered list items (1. 2. 3. ...) are list content, not
# sections -- but decimal headings (4.1, 8.3.1) always are sections.
BARE_LIST_ITEM_RE = re.compile(r"^\d{1,2}\.\s+\S")
DECIMAL_HEADING_RE = re.compile(r"^\d{1,2}(?:\.\d{1,2})+")
LIST_RUN_MIN_ITEMS = 5  # more than ~4 bare-number items in a row = a list
# Short, sentence-unfinished lines are word-wraps of the item above
# ("4. Diagnostic Center (Lab, Scan, X-Ray" / "and EEG)"), not paragraphs,
# so they do not end a list run. Real body text (long, or ending . ? !) does.
LIST_BRIDGE_MAX_CHARS = 60
LIST_BRIDGE_END_RE = re.compile(r"[.?!]$")
# A bare item longer than this carries its first sentence -> it is a numbered
# section heading, not a list entry, and it breaks/skips list suppression.
LIST_ITEM_MAX_CHARS = 60


def looks_like_body_fragment(line: str) -> bool:
    """True when a heading candidate is really a piece of body text."""
    s = line.strip()
    if not s:
        return True
    if len(s) <= 1:
        return True
    if HEADING_TRAIL_PUNCT_RE.search(s):
        return True
    if HEADING_TRAIL_PAREN_RE.search(s):
        return True
    if HEADING_SEMICOLON_RE.search(s):
        return True
    if s[0].islower():
        return True
    if HEADING_CONNECTIVE_END_RE.search(s):
        return True
    if s.lower() in BODY_FRAGMENT_SINGLE_WORDS:
        return True
    return False


def _bare_list_item(line: str) -> bool:
    """A '1. Foo' style list item (not a decimal section heading)."""
    return bool(BARE_LIST_ITEM_RE.match(line)) and not DECIMAL_HEADING_RE.match(line)


def _bridges_list_run(line: str) -> bool:
    """True for a short line-wrapped continuation of the item above."""
    s = line.strip()
    if not s or len(s) > LIST_BRIDGE_MAX_CHARS:
        return False
    return not LIST_BRIDGE_END_RE.search(s)


# ---------------------------------------------------------------------------
# Emission-time junk filter (bucket A): front/back-matter and TOC fragments
# carry high lexical overlap with any question about the Act but contain no
# answer content. Rules:
#   1. body < 80 chars AND a junk-regex match (short fragments)
#      (also covers the legacy "section_label == document title" rule)
#   2. section_label is a known front-matter phrase (any body length)
#   3. committee-list / acknowledgements page (>6 personal-name lines)
#   4. TOC dot-leader / page-number lines are >30% of the body
#   5. bodies longer than 500 chars are never dropped unless rule 4 matched
# ---------------------------------------------------------------------------
JUNK_MIN_CHARS = 80
JUNK_PROSE_MIN_CHARS = 500
TRAILING_INTERPUNCT_RE = re.compile(r"[·]\s*$")
TOC_DOT_LEADER_RE = re.compile(r"\.\s*\.\s*\.|\.{3,}|\.\s{2,}\.")
TOC_PAGE_NUMBER_RE = re.compile(r"(?:\.{4,}|…|\.{2,}\s*)\d{1,4}\s*$")
FRONT_MATTER_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"ARRANGEMENT OF SECTIONS?",
        r"TABLE OF CONTENTS?",
        r"OFFICIAL GAZETTE",
        r"Government Notice",
        r"Annual Subscription",
        r"FGP \d+/\d+",
        r"Printed and Published by the Federal Government Printer",
        r"I ASSENT",
        r"Clerk to the National Assembly",
        r"ISBN",
        r"© National Health Insurance Authority",
        r"CamScanner",
    ]
]
# Rule 2: phrases that mark a front-matter SECTION LABEL outright (the
# whole chunk under such a label is front matter, whatever its length).
FRONT_MATTER_LABEL_PHRASES = [
    "ARRANGEMENT OF SECTIONS",
    "ARRANGEMENT OF SECTION",
    "EXPLANATORY MEMORANDUM",
    "TABLE OF CONTENT",
    "TABLE OF CONTENTS",
    "OFFICIAL GAZETTE",
    "GOVERNMENT NOTICE",
    "PRINTED AND PUBLISHED BY THE FEDERAL GOVERNMENT PRINTER",
    "FGP",
    "ANNUAL SUBSCRIPTION",
    "I ASSENT",
    "CLERK TO THE NATIONAL ASSEMBLY",
    "CAMSCANNER",
    "ISBN",
    "© NATIONAL HEALTH INSURANCE AUTHORITY",
]
# Rule 3: personal-name detection for committee/contributor lists.
_HONORIFIC_RE = re.compile(
    r"^(?:Prof\.?|Dr\.?|Mr\.?|Mrs\.?|Ms\.?|Engr\.?|Barr\.?|Rev\.?|Chief|"
    r"Alhaji|Alhaja|Sir|Hon\.?|Arc\.?|Arch\.?)\s+",
    re.I,
)
_POSTNOMINAL_RE = re.compile(
    r",?\s+(?:Ph\.?D|M\.?Sc|B\.?Sc|MBBS|MPH|LLM|LLB|RN|RM|FWACS|FMCP|"
    r"MBChB|Esq\.?|PGDE|OND|HND|M\.?Eng|B\.?Eng|FICS|ICEN)\s*$",
    re.I,
)
_NAME_WORD_RE = re.compile(r"^[A-Z][A-Za-z'\-]*\.?$")
_LEADING_NUMBER_RE = re.compile(r"^\d{1,3}[.)]\s+")
MIN_NAME_LINES_FOR_LIST = 6


def _looks_like_person_name(line: str) -> bool:
    """True for a title-case 2-4 word personal name, e.g.
    '36. Prof. Ayuba Zoakah Ibrahim, Jos University Teaching Hospital'."""
    s = line.strip()
    if not (6 <= len(s) <= 90):
        return False
    if any(ch.isdigit() for ch in s):
        s = _LEADING_NUMBER_RE.sub("", s).strip()
        if any(ch.isdigit() for ch in s):
            return False
    s = _HONORIFIC_RE.sub("", s)
    s = s.split(",")[0]  # affiliation on the same line or the next
    s = _POSTNOMINAL_RE.sub("", s).rstrip(".,;-")
    words = s.split()
    if not (2 <= len(words) <= 4):
        return False
    return all(_NAME_WORD_RE.match(w) for w in words)


def _is_committee_list(text: str) -> bool:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) <= MIN_NAME_LINES_FOR_LIST:
        return False
    return sum(1 for ln in lines if _looks_like_person_name(ln)) > MIN_NAME_LINES_FOR_LIST


def _is_toc_page(text: str) -> bool:
    """True when >30% of the body lines are TOC dot-leader / page-number lines."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    toc = sum(1 for ln in lines if TOC_PAGE_NUMBER_RE.search(ln.strip())
              or TOC_DOT_LEADER_RE.search(ln))
    return toc / len(lines) > 0.30


def _normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def junk_reason(section: str, text: str, doc_title: str, filename: str) -> tuple[int, str] | None:
    """Return (rule_number, reason) when the chunk should be dropped, else None."""
    body = (text or "").strip()
    label = (section or "").strip()
    low_label = label.lower()

    # Legacy guard: a chunk labelled with the document's own title is front
    # matter only when its body is short (protects substantive sections such
    # as the repeated 'NATIONAL HEALTH SYSTEM·' headers).
    norm_label = _normalize_title(label)
    if len(body) < 150 and norm_label and (
        norm_label == _normalize_title(doc_title)
        or norm_label == _normalize_title(filename)
        or norm_label == _normalize_title(Path(filename or "").stem)
    ):
        return (1, "section_label == document title (body < 150)")

    # Rule 4 first: TOC pages are dropped regardless of length (rule 5).
    if _is_toc_page(body) or TOC_DOT_LEADER_RE.search(label):
        return (4, "TOC dot-leader / page-number lines > 30% of body")

    # Rule 5: anything longer than this is prose and is protected.
    if len(body) > JUNK_PROSE_MIN_CHARS:
        return None

    # Rule 2: section_label itself names a front-matter page.
    for phrase in FRONT_MATTER_LABEL_PHRASES:
        if phrase in low_label:
            return (2, f"front-matter section_label ({phrase})")

    # Rule 3: committee / acknowledgements / contributor lists.
    if _is_committee_list(body):
        return (3, "committee-list / acknowledgements page (personal names)")

    # Rule 1: short body + junk regex.
    if len(body) >= JUNK_MIN_CHARS:
        return None
    if TRAILING_INTERPUNCT_RE.search(label):
        return (1, "short body + OCR interpunct label")
    if TOC_DOT_LEADER_RE.search(body):
        return (1, "short body + TOC dot leader")
    for pat in FRONT_MATTER_PATTERNS:
        if pat.search(body):
            return (1, f"short body + front matter ({pat.pattern})")
    return None


def load_sources() -> list[dict]:
    with SOURCES_JSON.open("r", encoding="utf-8") as f:
        return json.load(f)


def is_real_pdf(path: Path) -> bool:
    with path.open("rb") as f:
        return f.read(5) == b"%PDF-"


def extract_pages(path: Path) -> list[tuple[int, str]]:
    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append((i + 1, text))
    return pages


def drop_boilerplate(pages: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    """Remove bare page numbers and lines repeated across pages."""
    per_page_lines = []
    for page_no, text in pages:
        lines = []
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line or PAGE_NUMBER_RE.match(line) or PAGE_LABEL_RE.match(line):
                continue
            lines.append((page_no, line))
        per_page_lines.append(lines)

    if len(per_page_lines) >= REPEAT_PAGES:
        counts: dict[str, int] = {}
        for lines in per_page_lines:
            for _, line in lines:
                counts[line] = counts.get(line, 0) + 1
        repeated = {
            line
            for line, n in counts.items()
            if n >= REPEAT_PAGES and len(line) <= 120
        }
        per_page_lines = [
            [(p, l) for p, l in lines if l not in repeated]
            for lines in per_page_lines
        ]

    return per_page_lines


def is_heading(line: str) -> bool:
    if len(line) > 120:
        return False
    if looks_like_body_fragment(line):
        return False
    words = line.split()
    for pattern in HEADING_PATTERNS:
        if not pattern.match(line):
            continue
        if pattern.pattern.startswith("^\\d") or pattern.pattern.startswith("^[IVXLC]"):
            if len(line) > NUMBERED_HEADING_MAX_CHARS or len(words) > NUMBERED_HEADING_MAX_WORDS:
                continue
        return True
    if line.isupper() and any(c.isalpha() for c in line):
        if CAPS_HEADING_MIN_WORDS <= len(words) <= CAPS_HEADING_MAX_WORDS:
            if len(line) <= CAPS_HEADING_MAX_CHARS:
                return True
    return False


def heading_flags(lines_by_page: list[list[tuple[int, str]]]) -> list[list[bool]]:
    """Per-line 'treat as section heading' flags.

    Base decision is is_heading(). On top of that, a run of more than
    LIST_RUN_MIN_ITEMS-1 short bare-numbered list items ("1. Foo", "2. Bar")
    that are not separated by real body text is list content and is never
    promoted -- e.g. HEFAMAA's 20 facility types, gazette Arrangement-of-
    Sections entries. Long bare items (a numbered section whose first
    sentence is on the heading line) and decimal headings (4.1, 8.3.1)
    always break the run and are never suppressed.
    """
    flat = [line for lines in lines_by_page for _, line in lines]
    raw = [is_heading(line) for line in flat]
    suppressed = [False] * len(flat)

    i, n = 0, len(flat)
    while i < n:
        line = flat[i]
        if _bare_list_item(line) and len(line) <= LIST_ITEM_MAX_CHARS:
            j, items = i, 0
            while j < n:
                lj = flat[j]
                if _bare_list_item(lj):
                    if len(lj) > LIST_ITEM_MAX_CHARS:
                        break  # numbered section w/ first sentence: real heading
                    items += 1
                    j += 1
                elif _bridges_list_run(lj):
                    j += 1
                else:
                    break
            if items >= LIST_RUN_MIN_ITEMS:
                for k in range(i, j):
                    if _bare_list_item(flat[k]):
                        suppressed[k] = True
            i = j if j > i else i + 1
        else:
            i += 1

    flags: list[list[bool]] = []
    idx = 0
    for lines in lines_by_page:
        page_flags = []
        for _ in lines:
            page_flags.append(raw[idx] and not suppressed[idx])
            idx += 1
        flags.append(page_flags)
    return flags


def build_sections(lines_by_page: list[list[tuple[int, str]]]):
    """Split a document into (title, page_start, lines) sections."""
    sections = []
    title, page_start, buf = "", None, []
    flags = heading_flags(lines_by_page)

    for lines, page_flags in zip(lines_by_page, flags):
        for (page_no, line), is_head in zip(lines, page_flags):
            if is_head:
                sections.append((title, page_start if page_start else page_no, buf))
                title, page_start, buf = line, page_no, [(page_no, line)]
            else:
                if page_start is None:
                    page_start = page_no
                buf.append((page_no, line))
    sections.append((title, page_start if page_start else 1, buf))

    sections = [(t, p, b) for t, p, b in sections if b]
    return merge_small_sections(sections)


def merge_small_sections(sections):
    """Fold sections smaller than MIN_SECTION_CHARS into the next section."""
    merged = []
    pend_title, pend_page, pend_lines = "", 1, []

    for title, page, lines in sections:
        if not pend_lines:
            pend_page = page
        pend_lines.extend(lines)
        if title:
            pend_title = title
        size = sum(len(l) for _, l in pend_lines)
        if size >= MIN_SECTION_CHARS:
            merged.append((pend_title, pend_page, pend_lines))
            pend_title, pend_lines = "", []

    if pend_lines:
        if merged:
            last_title, last_page, last_lines = merged[-1]
            merged[-1] = (last_title, last_page, last_lines + pend_lines)
        else:
            merged.append((pend_title, pend_page, pend_lines))

    return merged


def pack_lines(lines, max_chars, overlap_chars):
    """Pack (page, line) tuples into chunk dicts with overlap."""
    chunks = []
    cur = []

    def flush(buf):
        text = "\n".join(l for _, l in buf)
        chunks.append({"page_start": buf[0][0], "text": text})

    def overlap_tail(buf):
        tail, size = [], 0
        for item in reversed(buf):
            if size + len(item[1]) + 1 > overlap_chars and tail:
                break
            tail.insert(0, item)
            size += len(item[1]) + 1
        return tail

    for item in lines:
        added = len(item[1]) + 1
        if cur and sum(len(l) + 1 for _, l in cur) + added > max_chars:
            flush(cur)
            cur = overlap_tail(cur)
        cur.append(item)

    if cur:
        text = "\n".join(l for _, l in cur)
        if not chunks or chunks[-1]["text"] != text:
            flush(cur)

    return chunks


def chunk_document(lines_by_page, max_chars, overlap_chars, headers_found):
    """Return (chunks, used_fallback)."""
    if headers_found:
        sections = build_sections(lines_by_page)
        chunks = []
        for title, page, lines in sections:
            for c in pack_lines(lines, max_chars, overlap_chars):
                chunks.append({"section": title, **c})
        return chunks, False

    flat = [item for lines in lines_by_page for item in lines]
    chunks = [
        {"section": "", **c}
        for c in pack_lines(flat, max_chars, overlap_chars)
    ]
    return chunks, True


def main() -> int:
    parser = argparse.ArgumentParser(description="Chunk the raw PDF corpus.")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP_CHARS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not SOURCES_JSON.exists():
        sys.exit(f"ERROR: {SOURCES_JSON} not found.")
    if not RAW_DIR.exists():
        sys.exit(f"ERROR: {RAW_DIR} not found. Run python download_corpus.py first.")

    sources = load_sources()
    print(f"Sources in manifest: {len(sources)}")
    print(f"Chunk size: {args.max_chars} chars, overlap ~{args.overlap} chars\n")

    all_chunks = []
    skipped = []
    no_header_docs = []
    no_text_docs = []
    ocr_docs = []
    per_doc = []
    junk_drops: dict[str, int] = {}
    junk_rule_counts: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0}
    junk_drop_log: list[tuple[str, int, str]] = []
    phrase_hits: dict[str, int] = {}

    for entry in sources:
        sid = entry.get("id", "?")
        fname = entry.get("filename", "")
        path = RAW_DIR / fname

        if not path.exists():
            skipped.append((sid, fname, "file missing"))
            print(f"SKIP [{sid}] {fname} — file missing")
            continue
        if not is_real_pdf(path):
            skipped.append((sid, fname, "not a real PDF"))
            print(f"SKIP [{sid}] {fname} — not a real PDF (HTML/error page?)")
            continue

        try:
            pages = extract_pages(path)
        except Exception as e:
            skipped.append((sid, fname, f"unreadable: {type(e).__name__}"))
            print(f"SKIP [{sid}] {fname} — unreadable ({type(e).__name__}: {e})")
            continue

        lines_by_page = drop_boilerplate(pages)
        native_chars = sum(len(l) for lines in lines_by_page for _, l in lines)
        used_ocr = False

        if native_chars < MIN_NATIVE_CHARS:
            sidecar = OCR_DIR / f"{sid}.json"
            if sidecar.exists():
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                ocr_pages = [
                    (p.get("page", i + 1), p.get("text", ""))
                    for i, p in enumerate(data.get("pages", []))
                ]
                lines_by_page = drop_boilerplate(ocr_pages)
                used_ocr = True
                ocr_docs.append(sid)
                print(f"OCR  [{sid}] native text {native_chars:,} chars — "
                      f"using sidecar {sidecar.name}")

        flags = heading_flags(lines_by_page)
        headers_found = sum(1 for page_flags in flags for f in page_flags if f)
        total_lines = sum(len(lines) for lines in lines_by_page)

        if total_lines == 0:
            no_text_docs.append(sid)
            print(f"WARN [{sid}] {fname} — no extractable text (scanned "
                  f"images?) — run: python src/ocr_scans.py --only {sid}")
            per_doc.append((sid, fname, 0, headers_found, False, used_ocr))
            continue

        if headers_found == 0:
            no_header_docs.append(sid)
            print(
                f"WARN [{sid}] {fname} — no headers detected "
                f"(the 'no headers detected' fallback warning); "
                f"using fixed-size chunking"
            )

        chunks, used_fallback = chunk_document(
            lines_by_page, args.max_chars, args.overlap, headers_found
        )

        # Emission-time junk filter (rules 1-4; see junk_reason).
        doc_title = entry.get("title", "")
        kept = []
        for c in chunks:
            result = junk_reason(c["section"], c["text"], doc_title, fname)
            if result:
                rule, reason = result
                junk_drops[sid] = junk_drops.get(sid, 0) + 1
                junk_rule_counts[rule] = junk_rule_counts.get(rule, 0) + 1
                junk_drop_log.append((sid, rule, reason))
                continue
            kept.append(c)
        # Diagnostic only: front-matter phrases inside substantive-length
        # chunks are reported but NOT dropped (the >500-char prose
        # protection keeps real prose that merely mentions these phrases).
        for c in kept:
            for pat in FRONT_MATTER_PATTERNS:
                if pat.search(c["text"]):
                    phrase_hits[sid] = phrase_hits.get(sid, 0) + 1
                    break

        for i, c in enumerate(kept, 1):
            all_chunks.append(
                {
                    "chunk_id": f"{sid}#{i:04d}",
                    "source_id": sid,
                    "filename": fname,
                    "title": doc_title,
                    "issuing_body": entry.get("issuing_body", ""),
                    "section": c["section"],
                    "page_start": c["page_start"],
                    "text": c["text"],
                }
            )
        per_doc.append((sid, fname, len(kept), headers_found, used_fallback,
                        used_ocr))

    print("\n" + "=" * 72)
    print(f"{'source_id':32s} {'chunks':>7s} {'headers':>8s}  fallback  ocr")
    print("-" * 72)
    for sid, fname, n, h, fb, ocr in per_doc:
        print(f"{sid:32s} {n:7d} {h:8d}  {'YES' if fb else '-':8s}  "
              f"{'YES' if ocr else '-'}")
    print("=" * 72)

    total_drops = sum(junk_drops.values())
    print(f"\nJunk chunks dropped: {total_drops} "
          f"({junk_rule_counts.get(1, 0)}/{junk_rule_counts.get(2, 0)}/"
          f"{junk_rule_counts.get(3, 0)}/{junk_rule_counts.get(4, 0)})")
    print("Per-doc drops: " + ", ".join(
        f"{sid}={junk_drops.get(sid, 0)}" for sid, *_ in per_doc
    ))

    print("\nJunk filter (emission) — dropped chunks per doc:")
    for sid, fname, n, h, fb, ocr in per_doc:
        drops = junk_drops.get(sid, 0)
        phrase = phrase_hits.get(sid, 0)
        note = f"{drops} dropped"
        if phrase:
            note += f"  (+{phrase} kept: front-matter phrase in prose-length chunk)"
        print(f"  {sid:32s} {note}")
    if not total_drops:
        print("  (none — no chunk met any junk rule)")
    if junk_drop_log:
        print("\n  Drop reasons:")
        reason_counts: dict[str, int] = {}
        for _sid, rule, reason in junk_drop_log:
            reason_counts[f"rule{rule}: {reason}"] = reason_counts.get(
                f"rule{rule}: {reason}", 0) + 1
        for reason, n in sorted(reason_counts.items(), key=lambda kv: -kv[1]):
            print(f"    {n:4d}  {reason}")
    print(f"  TOTAL DROPPED: {total_drops}")

    if skipped:
        print("\nSkipped files:")
        for sid, fname, why in skipped:
            print(f"  [{sid}] {fname} — {why}")

    if no_text_docs:
        print(f"\nDocuments with no extractable text: {', '.join(no_text_docs)}")

    if ocr_docs:
        print(f"Documents chunked from OCR sidecars: {', '.join(ocr_docs)}")

    print(f"\nDocuments triggering the 'no headers detected' fallback warning: "
          f"{', '.join(no_header_docs) if no_header_docs else 'none'}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    # Secondary export in the schema embed_store.py expects
    # (chunk_id / text / doc_id / doc_title / section_label + our extras).
    all_chunks_path = args.out.parent / "all_chunks.json"
    embed_chunks = [
        {
            **c,
            "doc_id": c["source_id"],
            "doc_title": c["title"] or c["filename"],
            "section_label": c["section"],
        }
        for c in all_chunks
    ]
    all_chunks_path.write_text(
        json.dumps(embed_chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Wrote {len(all_chunks)} chunks -> {args.out}")
    print(f"Wrote {len(embed_chunks)} chunks -> {all_chunks_path} "
          f"(embed_store.py input)")
    print(f"TOTAL CHUNKS: {len(all_chunks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
