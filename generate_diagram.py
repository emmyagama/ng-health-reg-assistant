#!/usr/bin/env python3
"""
generate_diagram.py
===================
Render docs/architecture_diagram.svg — a top-to-bottom RAG pipeline flow
diagram with 8 main stages, connecting arrows, an arrowhead marker, and
three right-side "rejected alternative" annotations.

Uses only svgwrite (pure-Python; pip install svgwrite).

Run:
    python generate_diagram.py
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import svgwrite
from svgwrite import cm, mm, px                     # noqa: F401  (used indirectly)
from svgwrite.container import Group
from svgwrite.shapes import Rect, Line
from svgwrite.text import Text


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
OUT_PATH = Path("docs/architecture_diagram.svg")

# Canvas
WIDTH = 980
LEFT_MARGIN = 60
RIGHT_MARGIN = 60
TOP_MARGIN = 50
BOTTOM_MARGIN = 50

# Main flow boxes
BOX_W = 540
BOX_H = 68
BOX_X = LEFT_MARGIN
BOX_PAD_X = 18        # inner left/right padding for text
BOX_PAD_Y = 12        # inner top padding for first line of text
BOX_RX = 10           # rounded-corner radius
BOX_FILL = "#E8F0FE"  # very light blue
BOX_STROKE = "#1F3A5F"
BOX_STROKE_W = 1.5

# Spacing between boxes (arrow sits in this gap)
GAP = 46
BOX_TEXT_SIZE = 15
BOX_FONT = "DejaVu Sans, Arial, Helvetica, sans-serif"
TEXT_COLOR = "#111111"

# Arrows
ARROW_COLOR = "#222222"
ARROW_W = 1.8
ARROWHEAD_W = 10
ARROWHEAD_H = 12

# Annotations (right side)
ANNO_X = BOX_X + BOX_W + 36          # left edge of annotation boxes
ANNO_W = 280
ANNO_MAX_H = 72
ANNO_PAD_X = 12
ANNO_PAD_Y = 8
ANNO_FILL = "#FFF4D6"                # very light amber
ANNO_STROKE = "#B88B3A"
ANNO_STROKE_W = 1.0
ANNO_DASH = "4,3"
ANNO_TEXT_SIZE = 12
ANNO_FONT = "DejaVu Sans, Arial, Helvetica, sans-serif"

# Title
TITLE = "Nigerian Health-Regulation RAG — Pipeline Architecture"
TITLE_SIZE = 20
TITLE_COLOR = "#0D1F33"


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------
STAGES = [
    "Public documents (NDPA, NDPC, NHIA, HEFAMAA, MLSCN, National Health Act,"
    " ISO 15189, WHO)",
    "download_corpus.py → data/raw/ (PDFs, never committed to git)",
    "chunker.py → section-aware chunks with overlap → all_chunks.json",
    "embed_store.py → all-MiniLM-L6-v2 embeddings → ChromaDB (persistent"
    " vector store)",
    "User question → query_store() → top-5 relevant chunks (retrieval)",
    "answer.py → Groq LLM (llama-3.1-8b-instant) → answer with citations",
    "guardrails.py → 4 checks: retrieval confidence, citation required,"
    " clinical refusal, out-of-corpus refusal",
    "Streamlit UI → shows answer + sources, OR a refusal message",
]

# Annotations: (index of the stage they attach to, text).
# Indexes are 0-based into STAGES.
ANNOTATIONS = [
    (3, "Rejected: FAISS (Chroma chosen for simpler built-in persistence)"),
    (5, "Rejected: fine-tuning, agents, voice (explicitly out of scope)"),
    (5, "Rejected: Ollama local fallback (Groq free tier sufficient; adds unused"
        " setup weight)"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def wrap_text(text: str, max_chars: int) -> list[str]:
    """Greedy word-wrap by character width."""
    return textwrap.wrap(
        text,
        width=max_chars,
        break_long_words=False,
        break_on_hyphens=False,
    )


def add_rounded_box(
    dwg: svgwrite.Drawing,
    x: float, y: float, w: float, h: float, rx: float,
    fill: str, stroke: str, stroke_w: float,
) -> None:
    dwg.add(Rect(
        insert=(x, y), size=(w, h), rx=rx, ry=rx,
        fill=fill, stroke=stroke, stroke_width=stroke_w,
    ))


def add_multiline_text(
    dwg: svgwrite.Drawing,
    x: float, y: float,
    lines: list[str],
    font_size: int, font_family: str, color: str,
    line_height: float | None = None,
    anchor: str = "start",
    weight: str = "normal",
) -> None:
    if line_height is None:
        line_height = font_size * 1.30
    for i, line in enumerate(lines):
        dwg.add(Text(
            line,
            insert=(x, y + i * line_height),
            font_size=font_size,
            font_family=font_family,
            fill=color,
            font_weight=weight,
            text_anchor=anchor,
        ))


def add_arrow(
    dwg: svgwrite.Drawing,
    x1: float, y1: float, x2: float, y2: float,
    color: str, stroke_w: float,
    marker_ref: str,
) -> None:
    dwg.add(Line(
        start=(x1, y1), end=(x2, y2),
        stroke=color, stroke_width=stroke_w,
        marker_end=marker_ref,
    ))


def add_dotted_connector(
    dwg: svgwrite.Drawing,
    x1: float, y1: float, x2: float, y2: float,
    color: str, stroke_w: float, dash: str,
) -> None:
    dwg.add(Line(
        start=(x1, y1), end=(x2, y2),
        stroke=color, stroke_width=stroke_w,
        stroke_dasharray=dash,
    ))


def calc_box_height(lines: list[str], font_size: int, pad_y: int) -> float:
    line_height = font_size * 1.30
    return 2 * pad_y + line_height * (len(lines) - 1) + font_size


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------
def main() -> None:
    # Wrap text per box and compute per-box heights so spacing stays even.
    max_chars_main = int((BOX_W - 2 * BOX_PAD_X) / (BOX_TEXT_SIZE * 0.55))
    wrapped = [wrap_text(s, max_chars_main) for s in STAGES]
    heights = [calc_box_height(lines, BOX_TEXT_SIZE, BOX_PAD_Y) for lines in wrapped]

    # Determine y position of each box top.
    y_tops: list[float] = []
    y = TOP_MARGIN + TITLE_SIZE + 30
    for h in heights:
        y_tops.append(y)
        y += h + GAP
    total_height = int(y - GAP + BOTTOM_MARGIN)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    dwg = svgwrite.Drawing(
        filename=str(OUT_PATH),
        size=(f"{WIDTH}px", f"{total_height}px"),
        viewBox=f"0 0 {WIDTH} {total_height}",
    )

    # --- Arrowhead marker ---
    arrow = dwg.marker(
        insert=(ARROWHEAD_W, ARROWHEAD_H / 2),
        size=(ARROWHEAD_W, ARROWHEAD_H),
        orient="auto",
        id="arrowhead",
    )
    arrow.add(dwg.polygon(
        points=[(0, 0), (ARROWHEAD_W, ARROWHEAD_H / 2), (0, ARROWHEAD_H)],
        fill=ARROW_COLOR,
    ))
    dwg.defs.add(arrow)
    arrow_ref = arrow.get_funciri()

    # --- Title ---
    dwg.add(Text(
        TITLE,
        insert=(WIDTH / 2, TOP_MARGIN + TITLE_SIZE),
        font_size=TITLE_SIZE,
        font_family=BOX_FONT,
        fill=TITLE_COLOR,
        text_anchor="middle",
        font_weight="bold",
    ))

    # --- Main flow boxes ---
    for i, (lines, h, yt) in enumerate(zip(wrapped, heights, y_tops)):
        add_rounded_box(
            dwg, BOX_X, yt, BOX_W, h, BOX_RX,
            fill=BOX_FILL, stroke=BOX_STROKE, stroke_w=BOX_STROKE_W,
        )
        add_multiline_text(
            dwg,
            BOX_X + BOX_PAD_X,
            yt + BOX_PAD_Y + BOX_TEXT_SIZE,
            lines,
            font_size=BOX_TEXT_SIZE,
            font_family=BOX_FONT,
            color=TEXT_COLOR,
        )

    # --- Arrows between consecutive boxes ---
    for i in range(len(heights) - 1):
        x = BOX_X + BOX_W / 2
        y_start = y_tops[i] + heights[i]
        y_end = y_tops[i + 1]
        # Stop the line a few pixels short so the arrowhead sits against
        # the next box's top border rather than protruding inside.
        add_arrow(dwg, x, y_start, x, y_end - 2, ARROW_COLOR, ARROW_W, arrow_ref)

    # --- Annotations (right side) ---
    # Track vertical positions so two annotations on stage 6 don't overlap.
    max_chars_anno = int((ANNO_W - 2 * ANNO_PAD_X) / (ANNO_TEXT_SIZE * 0.55))

    # Group annotations by target stage so we can stack them.
    from collections import defaultdict
    per_stage: dict[int, list[str]] = defaultdict(list)
    for stage_idx, text in ANNOTATIONS:
        per_stage[stage_idx].append(text)

    for stage_idx, texts in per_stage.items():
        # anchor y = centre of the target box
        target_y_center = y_tops[stage_idx] + heights[stage_idx] / 2

        # Compute each annotation box height and stack downward from
        # target_y_center, offsetting so the group is centered on the target.
        anno_wrapped = [wrap_text(t, max_chars_anno) for t in texts]
        anno_heights = [calc_box_height(lw, ANNO_TEXT_SIZE, ANNO_PAD_Y)
                        for lw in anno_wrapped]
        total_h = sum(anno_heights) + 10 * (len(anno_heights) - 1)
        cur_y = target_y_center - total_h / 2

        for lw, ah in zip(anno_wrapped, anno_heights):
            add_rounded_box(
                dwg, ANNO_X, cur_y, ANNO_W, ah, BOX_RX,
                fill=ANNO_FILL, stroke=ANNO_STROKE, stroke_w=ANNO_STROKE_W,
            )
            add_multiline_text(
                dwg,
                ANNO_X + ANNO_PAD_X,
                cur_y + ANNO_PAD_Y + ANNO_TEXT_SIZE,
                lw,
                font_size=ANNO_TEXT_SIZE,
                font_family=ANNO_FONT,
                color="#4A3A1A",
            )
            # Dotted connector from middle-left of annotation to right edge of
            # the main box at the same horizontal centreline.
            add_dotted_connector(
                dwg,
                BOX_X + BOX_W,
                cur_y + ah / 2,
                ANNO_X,
                cur_y + ah / 2,
                color=ANNO_STROKE,
                stroke_w=1.2,
                dash=ANNO_DASH,
            )
            cur_y += ah + 10

    dwg.save()

    # --- Verification summary ---
    num_main_boxes = len(STAGES)
    num_anno_boxes = sum(len(v) for v in per_stage.values())
    arrow_count = num_main_boxes - 1
    connector_count = num_anno_boxes
    size_bytes = OUT_PATH.stat().st_size
    print(f"Wrote {OUT_PATH}")
    print(f"  canvas:         {WIDTH} x {total_height} px")
    print(f"  main boxes:     {num_main_boxes}")
    print(f"  annotation boxes:{num_anno_boxes}")
    print(f"  main arrows:    {arrow_count}")
    print(f"  dotted connectors:{connector_count}")
    print(f"  file size:      {size_bytes:,} bytes")


if __name__ == "__main__":
    main()
