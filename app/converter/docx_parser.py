"""
DOCX parser: converts a .docx file into a list of Page dicts.

Each Page dict:
    {
        "id":      str   – unique slug for this page,
        "title":   str   – page title (from Heading 1),
        "content": str   – inner HTML body for the page,
    }

Strategy:
- Split at every Heading 1 paragraph.
- If the document has no Heading 1 the whole document becomes a single page
  using the filename stem (caller may override the title later).
- Headings 2/3 become <h2>/<h3>.
- Lists → <ul>/<ol><li>.
- Paragraphs → <p>.
- Tables → <table>.
- Inline bold/italic/underline are preserved.
"""

from __future__ import annotations

import io
import re
import uuid
from typing import BinaryIO

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_docx(stream: BinaryIO) -> list[dict]:
    doc = Document(stream)
    raw_pages = _split_into_pages(doc)
    return [_render_page(raw) for raw in raw_pages]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    """Turn a title into a safe ASCII slug."""
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text or "page"


def _is_heading1(para: Paragraph) -> bool:
    name = para.style.name
    return name.startswith("Heading 1") or name.startswith("Titulo 1") or name.startswith("Título 1")


def _is_heading(para: Paragraph) -> int | None:
    """Return heading level (1-3) or None."""
    name = para.style.name
    for level in (1, 2, 3):
        if (
            name.startswith(f"Heading {level}")
            or name.startswith(f"Titulo {level}")
            or name.startswith(f"Título {level}")
        ):
            return level
    return None


def _para_to_html(para: Paragraph) -> str:
    """Convert a Paragraph to an HTML string (no wrapping tag)."""
    parts = []
    for run in para.runs:
        text = run.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if run.bold:
            text = f"<strong>{text}</strong>"
        if run.italic:
            text = f"<em>{text}</em>"
        if run.underline:
            text = f"<u>{text}</u>"
        parts.append(text)
    return "".join(parts)


def _table_to_html(table: Table) -> str:
    rows_html = []
    for row in table.rows:
        cells_html = "".join(
            f"<td>{cell.text.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')}</td>"
            for cell in row.cells
        )
        rows_html.append(f"<tr>{cells_html}</tr>")
    return "<table class='exe-table table table-bordered'><tbody>" + "".join(rows_html) + "</tbody></table>"


def _list_style(para: Paragraph) -> str | None:
    """Return 'ul' or 'ol' if the paragraph is a list item, else None."""
    name = para.style.name
    if "List Bullet" in name:
        return "ul"
    if "List Number" in name:
        return "ol"
    # Fallback: check numPr
    numPr = para._p.find(qn("w:pPr"))
    if numPr is not None:
        numId = numPr.find(qn("w:numId")) if numPr is not None else None
        if numId is not None:
            return "ul"
    return None


def _split_into_pages(doc: Document) -> list[dict]:
    """
    Split document body into sections bounded by Heading 1.
    Returns a list of dicts: {"title": str, "elements": list}.
    """
    pages: list[dict] = []
    current: dict | None = None

    for block in doc.element.body:
        tag = block.tag.split("}")[-1] if "}" in block.tag else block.tag

        if tag == "p":
            para = Paragraph(block, doc)
            if _is_heading1(para):
                current = {"title": para.text.strip(), "elements": []}
                pages.append(current)
            else:
                if current is None:
                    current = {"title": "", "elements": []}
                    pages.append(current)
                current["elements"].append(("p", para))
        elif tag == "tbl":
            table = Table(block, doc)
            if current is None:
                current = {"title": "", "elements": []}
                pages.append(current)
            current["elements"].append(("table", table))

    # If nothing found, return empty list so caller can raise a 422.
    return pages


def _render_page(raw: dict) -> dict:
    """Convert a raw page dict into a rendered page dict with HTML content."""
    title = raw["title"] or "Página"
    page_id = f"page-{_slug(title)}-{uuid.uuid4().hex[:8]}"

    html_parts: list[str] = []
    pending_list: list[str] | None = None
    pending_list_type: str | None = None

    def flush_list():
        nonlocal pending_list, pending_list_type
        if pending_list:
            tag = pending_list_type or "ul"
            html_parts.append(f"<{tag}>{''.join(pending_list)}</{tag}>")
            pending_list = None
            pending_list_type = None

    for kind, element in raw["elements"]:
        if kind == "table":
            flush_list()
            html_parts.append(_table_to_html(element))
            continue

        para: Paragraph = element
        heading_level = _is_heading(para)

        if heading_level and heading_level > 1:
            flush_list()
            tag = f"h{heading_level}"
            html_parts.append(f"<{tag}>{_para_to_html(para)}</{tag}>")
            continue

        list_type = _list_style(para)
        if list_type:
            if pending_list_type and pending_list_type != list_type:
                flush_list()
            if pending_list is None:
                pending_list = []
                pending_list_type = list_type
            pending_list.append(f"<li>{_para_to_html(para)}</li>")
            continue

        flush_list()
        inner = _para_to_html(para)
        if inner.strip():
            html_parts.append(f"<p>{inner}</p>")

    flush_list()

    return {
        "id": page_id,
        "title": title,
        "content": "\n".join(html_parts),
    }
