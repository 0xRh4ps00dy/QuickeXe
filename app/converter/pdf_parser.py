"""
PDF parser: converts a text-digital PDF into a list of Page dicts.

Each Page dict:
        {
                "id":      str,
                "title":   str,
                "content": str,  – inner HTML
        }

Strategy:
- Build one output page per PDF page to avoid losing content.
- Optionally use the first short line as page title when it looks like a heading.
- Render all remaining lines into paragraph blocks.
"""

from __future__ import annotations

import re
import uuid
from typing import BinaryIO

from pypdf import PdfReader


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_pdf(stream: BinaryIO) -> list[dict]:
    reader = PdfReader(stream)
    raw_text_pages = _extract_pages(reader)
    pages: list[dict] = []
    for idx, lines in enumerate(raw_text_pages):
        title, body_lines = _pick_title(lines, idx)
        pages.append(_render_section(title, body_lines, idx))
    return pages


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_HEADING_MAX_LEN = 90
_MAX_HEADING_WORDS = 12


def _extract_pages(reader: PdfReader) -> list[list[str]]:
    """Return a list of pages; each page is a list of lines."""
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        lines = [l.rstrip() for l in text.splitlines()]
        pages.append(lines)
    return pages


def _looks_like_heading(line: str) -> bool:
    """Conservative heading detector for first line of a page."""
    stripped = line.strip()
    if not stripped:
        return False
    words = stripped.split()
    if len(words) > _MAX_HEADING_WORDS:
        return False
    if len(stripped) > _HEADING_MAX_LEN:
        return False
    if stripped.isdigit():
        return False
    # Sentence endings usually indicate body text, not a section title.
    if stripped.endswith(".") or stripped.endswith(","):
        return False
    return True


def _pick_title(lines: list[str], idx: int) -> tuple[str, list[str]]:
    non_empty = [line.strip() for line in lines if line.strip()]
    default_title = f"Pagina {idx + 1}"
    if not non_empty:
        return default_title, []

    first = non_empty[0]
    if _looks_like_heading(first):
        body_started = False
        body: list[str] = []
        for line in lines:
            if not body_started and line.strip() == first:
                body_started = True
                continue
            if body_started:
                body.append(line)
        if any(l.strip() for l in body):
            return first, body

    return default_title, lines


def _slug(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text or "page"


def _render_section(title: str, lines: list[str], idx: int) -> dict:
    page_title = title.strip() or f"Pagina {idx + 1}"
    page_id = f"page-{_slug(page_title)}-{uuid.uuid4().hex[:8]}"

    html_parts: list[str] = []
    paragraph_buffer: list[str] = []

    def flush():
        text = " ".join(paragraph_buffer).strip()
        if text:
            escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html_parts.append(f"<p>{escaped}</p>")
        paragraph_buffer.clear()

    for line in lines:
        stripped = line.strip()
        if stripped:
            paragraph_buffer.append(stripped)
        else:
            flush()

    flush()

    return {
        "id": page_id,
        "title": page_title,
        "content": "\n".join(html_parts),
    }
