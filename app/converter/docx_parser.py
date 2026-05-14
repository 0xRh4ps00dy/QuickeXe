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
- Headings 2/3 become <h3>/<h4>.
- Lists → <ul>/<ol><li>.
- Paragraphs → <p>.
- Tables → <table>.
- Inline bold/italic/underline are preserved.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from typing import BinaryIO

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_docx(stream: BinaryIO) -> tuple[list[dict], list[dict]]:
    doc = Document(stream)
    media = _MediaRegistry(doc)
    raw_pages = _split_into_pages(doc)
    return [_render_page(raw, doc, media) for raw in raw_pages], media.assets


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


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_TITLE_STOPWORDS = {
    "a",
    "al",
    "amb",
    "and",
    "as",
    "at",
    "by",
    "con",
    "da",
    "das",
    "de",
    "del",
    "des",
    "do",
    "dos",
    "e",
    "el",
    "en",
    "et",
    "for",
    "from",
    "i",
    "in",
    "la",
    "las",
    "le",
    "les",
    "los",
    "of",
    "o",
    "on",
    "or",
    "para",
    "per",
    "por",
    "que",
    "sense",
    "sin",
    "the",
    "to",
    "un",
    "una",
    "unos",
    "unas",
    "u",
    "und",
    "y",
}


def _is_title_like_text(text: str) -> bool:
    words = re.findall(r"[\wÀ-ÿ]+", text, flags=re.UNICODE)
    if len(words) < 2:
        return False

    title_like_words = 0
    for word in words:
        if word.isupper():
            title_like_words += 1
            continue
        if word[:1].isupper() and word[1:].islower():
            title_like_words += 1
            continue
        if any(char.isalpha() for char in word):
            return False

    return title_like_words >= max(2, len(words) // 2)


def _sentence_case_from_title_like(text: str) -> str:
    parts = re.split(r"(\s+)", text)
    result: list[str] = []
    capitalize_next = True

    for part in parts:
        if not part:
            continue
        if part.isspace():
            result.append(part)
            continue

        match = re.match(r"^([^\wÀ-ÿ]*)([\wÀ-ÿ][\wÀ-ÿ'’\-]*)([^\wÀ-ÿ]*)$", part, flags=re.UNICODE)
        if not match:
            result.append(part)
            if part.endswith((".", "!", "?")):
                capitalize_next = True
            continue

        prefix, word, suffix = match.groups()
        lower_word = word.lower()

        if capitalize_next:
            # First word or word after punctuation: capitalize
            normalized_word = lower_word[:1].upper() + lower_word[1:]
        elif word.isupper():
            # Word is completely uppercase: convert to lowercase
            normalized_word = lower_word
        elif lower_word in _TITLE_STOPWORDS:
            # Stopwords (de, la, en, etc.): keep lowercase
            normalized_word = lower_word
        elif any(char.isupper() for char in word[1:]) or any(char.isdigit() for char in word):
            # Mixed case or has digits: preserve
            normalized_word = word
        else:
            # Regular word: lowercase
            normalized_word = lower_word

        result.append(prefix + normalized_word + suffix)
        capitalize_next = suffix.endswith((".", "!", "?"))

    return "".join(result)


def _normalize_all_caps_text(text: str) -> str:
    """Normalize title-like text to sentence case, keeping mixed-case text unchanged."""
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return text
    if any(char.islower() for char in letters) and not _is_title_like_text(text):
        return text
    if not _is_title_like_text(text):
        if any(char.isupper() for char in letters):
            first_upper = re.search(r"[A-ZÀ-Ý]", text)
            if first_upper is None:
                return text
            normalized = text.lower()
            chars = list(normalized)
            for index, char in enumerate(chars):
                if char.isalpha():
                    chars[index] = char.upper()
                    break
            return "".join(chars)
        return text
    return _sentence_case_from_title_like(text)


def _video_embed_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None

    netloc = parsed.netloc.lower()
    path = parsed.path or ""

    if "youtube.com" in netloc:
        video_id = parse_qs(parsed.query).get("v", [""])[0]
        if video_id:
            return (
                f'<div class="exe-video"><iframe src="https://www.youtube.com/embed/{video_id}" '
                'title="Video" loading="lazy" allowfullscreen></iframe></div>'
            )

    if "youtu.be" in netloc:
        video_id = path.strip("/")
        if video_id:
            return (
                f'<div class="exe-video"><iframe src="https://www.youtube.com/embed/{video_id}" '
                'title="Video" loading="lazy" allowfullscreen></iframe></div>'
            )

    if "vimeo.com" in netloc:
        video_id = path.strip("/")
        if video_id.isdigit():
            return (
                f'<div class="exe-video"><iframe src="https://player.vimeo.com/video/{video_id}" '
                'title="Video" loading="lazy" allowfullscreen></iframe></div>'
            )

    lower_path = path.lower()
    if lower_path.endswith((".mp4", ".webm", ".ogg")):
        safe_url = _escape_html(url)
        return f'<video controls preload="metadata" src="{safe_url}"></video>'

    return None


class _MediaRegistry:
    def __init__(self, doc: Document):
        self._doc = doc
        self._assets: list[dict] = []
        self._rid_to_filename: dict[str, str] = {}

    @property
    def assets(self) -> list[dict]:
        return self._assets

    def register_embed(self, rid: str) -> str | None:
        if rid in self._rid_to_filename:
            return self._rid_to_filename[rid]

        part = self._doc.part.related_parts.get(rid)
        if part is None:
            return None

        ext = Path(str(part.partname)).suffix.lower() or ".bin"
        filename = f"media-{len(self._assets) + 1:03d}{ext}"
        self._rid_to_filename[rid] = filename
        self._assets.append(
            {
                "filename": filename,
                "content": part.blob,
                "content_type": getattr(part, "content_type", "application/octet-stream"),
            }
        )
        return filename


def _image_tags_from_run(run, media: _MediaRegistry) -> str:
    tags: list[str] = []
    for blip in run._element.xpath(".//*[local-name()='blip']"):
        rid = blip.get(qn("r:embed"))
        if not rid:
            continue
        filename = media.register_embed(rid)
        if not filename:
            continue
        tags.append(f'<img src="{{{{context_path}}}}/{filename}" alt="Imagen" class="img-fluid" />')
    return "".join(tags)


def _para_to_html(para: Paragraph, media: _MediaRegistry) -> str:
    """Convert a Paragraph to an HTML string (no wrapping tag)."""
    parts = []
    for run in para.runs:
        text = _escape_html(_normalize_all_caps_text(run.text))
        if run.bold:
            text = f"<strong>{text}</strong>"
        if run.italic:
            text = f"<em>{text}</em>"
        if run.underline:
            text = f"<u>{text}</u>"
        parts.append(text + _image_tags_from_run(run, media))
    return "".join(parts)


def _table_to_html(table: Table) -> str:
    rows_html = []
    for row in table.rows:
        cells_html = "".join(
            f"<td>{_escape_html(_normalize_all_caps_text(cell.text))}</td>"
            for cell in row.cells
        )
        rows_html.append(f"<tr>{cells_html}</tr>")
    return "<table class='exe-table table table-bordered'><tbody>" + "".join(rows_html) + "</tbody></table>"


def _list_style(para: Paragraph) -> str | None:
    """Return 'ul' or 'ol' if the paragraph is a list item, else None."""
    text = para.text.strip()
    
    # If paragraph has almost no text, it's probably an image/media container, not a list
    if len(text) < 2:
        return None
    
    
    # If paragraph contains an image/embedded media, don't treat as list
    # (images/media shouldn't be list items)
    for run in para.runs:
        if run._element.xpath(".//*[local-name()='blip']"):  # Has embedded image
            return None
    
    name = para.style.name.lower()
    
    # Common bullet/unordered list style names
    bullet_patterns = [
        "list bullet",
        "lista con vi",
        "viñeta",
        "vineta",
        "bullet",
        "list paragraph",  # Common base for custom list styles
        "blk list",
        "bloque list",
        "listado",
    ]
    
    # Common numbered/ordered list style names
    number_patterns = [
        "list number",
        "lista numer",
        "numerada",
        "number",
        "listado num",
        "blk list num",
    ]
    
    for pattern in bullet_patterns:
        if pattern in name:
            return "ul"
    
    for pattern in number_patterns:
        if pattern in name:
            return "ol"
    
    # Check numbering properties in paragraph XML (but only if there's significant text)
    ppr = para._p.pPr
    if ppr is not None and ppr.numPr is not None and ppr.numPr.numId is not None:
        # Check text patterns to determine ordered vs unordered
        if re.match(r"^\d+[\.)]\s+", text):
            return "ol"
        if re.match(r"^[a-zA-Z][\.)]\s+", text):
            return "ol"
        if re.match(r"^[•·*-]\s+", text):  # Common bullet characters
            return "ul"
        
        # If numPr exists but pattern unclear, default to ul
        return "ul"
    
    # Additional fallback: check text patterns at start
    # Check for bullet-like prefixes at start of text
    if re.match(r"^[•·*-]\s+", text):
        return "ul"
    
    # Check for numbered prefixes (1. 2. 3. or 1) 2) 3))
    if re.match(r"^\d+[\.)]\s+", text):
        return "ol"
    
    # Check for lettered prefixes (a. b. c. or a) b) c))
    if re.match(r"^[a-zA-Z][\.)]\s+", text):
        return "ol"
    
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
                current = {"title": _normalize_all_caps_text(para.text.strip()), "elements": []}
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

    # If the document starts with content before the first Heading 1,
    # merge that intro into the first titled page to avoid a phantom "Página".
    if len(pages) > 1 and not pages[0]["title"] and pages[1]["title"]:
        pages[1]["elements"] = pages[0]["elements"] + pages[1]["elements"]
        pages = pages[1:]

    # If nothing found, return empty list so caller can raise a 422.
    return pages


def _render_page(raw: dict, doc: Document, media: _MediaRegistry) -> dict:
    """Convert a raw page dict into a rendered page dict with HTML content."""
    title = _normalize_all_caps_text(raw["title"] or "Página")
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
            # Keep a lower in-page hierarchy because page title already renders as <h1>.
            tag = f"h{min(6, heading_level + 1)}"
            html_parts.append(f"<{tag}>{_para_to_html(para, media)}</{tag}>")
            continue

        list_type = _list_style(para)
        if list_type:
            if pending_list_type and pending_list_type != list_type:
                flush_list()
            if pending_list is None:
                pending_list = []
                pending_list_type = list_type
            # Get the HTML content for this list item
            item_html = _para_to_html(para, media).strip()
            # Only add non-empty list items
            if item_html:
                pending_list.append(f"<li>{item_html}</li>")
            continue

        flush_list()
        video_html = _video_embed_from_url(para.text.strip())
        if video_html:
            html_parts.append(video_html)
            continue

        inner = _para_to_html(para, media)
        if inner.strip():
            html_parts.append(f"<p>{inner}</p>")

    flush_list()

    return {
        "id": page_id,
        "title": title,
        "content": "\n".join(html_parts),
    }
