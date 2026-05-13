"""
Package builder: takes a list of Page dicts and produces a ZIP bytes object
with the same layout that eXeLearning expects when importing a web export.

ZIP layout:
    <title>/
        content.xml
        index.html
        html/
            <page-slug>.html
        content/
            css/
                base.css
        libs/   (copied from exe_base/libs)
        theme/  (copied from exe_base/theme)
"""

from __future__ import annotations

import io
import time
import uuid
import zipfile
from pathlib import Path
from typing import BinaryIO

from jinja2 import Environment, FileSystemLoader, select_autoescape


def build_package(
    title: str,
    pages: list[dict],
    base_assets_dir: Path,
) -> bytes:
    """
    Build and return the ZIP bytes of an eXeLearning-compatible web export.

    Args:
        title:           Project title (from uploaded filename stem).
        pages:           List of {"id", "title", "content"} dicts.
        base_assets_dir: Path to the exe_base directory containing libs/ and theme/.
    """
    templates_dir = Path(__file__).resolve().parent.parent / "templates" / "exe_package"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )

    ode_id = _make_id()
    ode_version_id = _make_id()
    timestamp = str(int(time.time() * 1000))

    # Build nav entries for index and inner pages
    # First page is "index" (rendered as index.html)
    first_page = pages[0]
    rest_pages = pages[1:]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        prefix = _safe_filename(title)

        # ── content.xml ──────────────────────────────────────────────────
        content_xml = env.get_template("content.xml.j2").render(
            ode_id=ode_id,
            ode_version_id=ode_version_id,
            title=title,
            timestamp=timestamp,
            pages=pages,
        )
        zf.writestr(f"{prefix}/content.xml", content_xml)

        # ── index.html (first page) ───────────────────────────────────────
        index_html = env.get_template("index.html.j2").render(
            title=title,
            page=first_page,
            all_pages=pages,
            is_first=True,
            next_page=rest_pages[0] if rest_pages else None,
        )
        zf.writestr(f"{prefix}/index.html", index_html)

        # ── html/<slug>.html for each remaining page ──────────────────────
        for i, page in enumerate(rest_pages):
            prev_page = pages[i]  # pages[i] because rest_pages[i] == pages[i+1]
            next_page = rest_pages[i + 1] if i + 1 < len(rest_pages) else None
            page_html = env.get_template("page.html.j2").render(
                title=title,
                page=page,
                all_pages=pages,
                prev_page=prev_page,
                next_page=next_page,
            )
            slug = _page_filename(page)
            zf.writestr(f"{prefix}/html/{slug}", page_html)

        # ── content/css/base.css ──────────────────────────────────────────
        base_css_src = base_assets_dir / "content" / "css" / "base.css"
        if base_css_src.exists():
            zf.write(str(base_css_src), f"{prefix}/content/css/base.css")
        else:
            zf.writestr(f"{prefix}/content/css/base.css", "/* base */\n")

        # ── libs/ ─────────────────────────────────────────────────────────
        _copy_dir(zf, base_assets_dir / "libs", f"{prefix}/libs")

        # ── theme/ ────────────────────────────────────────────────────────
        _copy_dir(zf, base_assets_dir / "theme", f"{prefix}/theme")

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_id() -> str:
    return uuid.uuid4().hex.upper()[:20]


def _safe_filename(text: str) -> str:
    import re
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text or "paquete"


def _page_filename(page: dict) -> str:
    """Return the HTML filename for a non-index page (relative to html/)."""
    import re
    slug = page["id"]
    # use slug as-is: it was built by the parsers and is already safe
    return f"{slug}.html"


def _copy_dir(zf: zipfile.ZipFile, src_dir: Path, zip_prefix: str) -> None:
    """Recursively add all files from src_dir into zf under zip_prefix."""
    if not src_dir.exists():
        return
    for file_path in src_dir.rglob("*"):
        if file_path.is_file():
            arcname = zip_prefix + "/" + file_path.relative_to(src_dir).as_posix()
            zf.write(str(file_path), arcname)
