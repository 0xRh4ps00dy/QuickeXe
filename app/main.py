import io
import base64
import re
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.converter.docx_parser import parse_docx
from app.converter.pdf_parser import parse_pdf
from app.converter.package_builder import build_package

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="DOCX/PDF → eXeLearning package converter")

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

app.mount(
    "/exe_preview",
    StaticFiles(directory=str(BASE_DIR / "exe_base")),
    name="exe_preview",
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

ALLOWED_EXTENSIONS = {".docx", ".pdf"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


def _inline_preview_assets(pages: list[dict], assets: list[dict]) -> list[dict]:
    if not assets:
        return pages

    assets_map = {
        asset["filename"]: f"data:{asset.get('content_type', 'application/octet-stream')};base64,{base64.b64encode(asset['content']).decode('ascii')}"
        for asset in assets
    }

    src_patterns = [
        re.compile(r"content/resources/([^\"'\s>]+)"),
        re.compile(r"\{\{context_path\}\}/([^\"'\s>]+)"),
    ]

    preview_pages: list[dict] = []
    for page in pages:
        content = page.get("content", "")
        for src_pattern in src_patterns:
            content = src_pattern.sub(
                lambda match: assets_map.get(match.group(1), match.group(0)),
                content,
            )
        preview_pages.append({**page, "content": content})

    return preview_pages


async def _extract_pages_from_upload(file: UploadFile) -> tuple[str, list[dict], list[dict]]:
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Solo se aceptan archivos .docx o .pdf",
        )

    content = await file.read()

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="El archivo supera el límite de 50 MB",
        )

    stem = Path(filename).stem

    if suffix == ".docx":
        pages, assets = parse_docx(io.BytesIO(content))
    else:
        pages, assets = parse_pdf(io.BytesIO(content))

    if not pages:
        raise HTTPException(
            status_code=422,
            detail="No se pudo extraer contenido del archivo. Comprueba que el documento tiene texto digital y está bien estructurado.",
        )

    return stem, pages, assets


@app.post("/preview")
async def preview(file: UploadFile = File(...)):
    stem, pages, assets = await _extract_pages_from_upload(file)
    preview_pages = _inline_preview_assets(pages, assets)
    return {
        "title": stem,
        "pages": preview_pages,
        "page_count": len(preview_pages),
    }


@app.post("/convert")
async def convert(file: UploadFile = File(...)):
    stem, pages, assets = await _extract_pages_from_upload(file)

    zip_bytes = build_package(
        title=stem,
        pages=pages,
        assets=assets,
        base_assets_dir=BASE_DIR / "exe_base",
    )

    safe_stem = "".join(c for c in stem if c.isalnum() or c in "-_") or "paquete"
    download_name = f"{safe_stem}_exe.zip"

    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
            "Content-Length": str(len(zip_bytes)),
        },
    )
