import io
import base64
import re
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Form, Query
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


def _safe_zip_name(stem: str) -> str:
    safe_stem = "".join(c for c in stem if c.isalnum() or c in "-_") or "paquete"
    return f"{safe_stem}_exe.zip"


def _resolve_output_dir(output_dir: str) -> Path:
    normalized = (output_dir or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Debes indicar un directorio de salida valido.")

    path = Path(normalized).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()

    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo crear el directorio de salida: {path}",
        ) from exc

    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"La ruta no es un directorio: {path}")

    return path


def _resolve_browse_dir(raw_path: str | None) -> Path:
    candidate = (raw_path or "").strip()
    if not candidate:
        return Path.home().resolve()

    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()

    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Directorio no valido: {path}")

    return path


@app.get("/directories")
async def list_directories(path: str | None = Query(default=None)):
    current = _resolve_browse_dir(path)

    try:
        directories = sorted(
            [entry for entry in current.iterdir() if entry.is_dir()],
            key=lambda item: item.name.lower(),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=f"Sin permisos para leer: {current}") from exc

    parent = None if current.parent == current else str(current.parent)

    return {
        "current_path": str(current),
        "parent_path": parent,
        "directories": [{"name": d.name, "path": str(d)} for d in directories],
        "shortcuts": [
            {"name": "Inicio", "path": str(Path.home().resolve())},
            {"name": "Proyecto", "path": str(Path.cwd().resolve())},
        ],
    }


@app.post("/convert")
async def convert(
    files: list[UploadFile] = File(...),
    output_dir: str | None = Form(default=None),
):
    if not files:
        raise HTTPException(status_code=400, detail="No se han recibido archivos para convertir.")

    output_dir = (output_dir or "").strip()

    if len(files) > 1 and not output_dir:
        raise HTTPException(
            status_code=400,
            detail="Para convertir varios archivos debes indicar un directorio de salida.",
        )

    converted: list[dict] = []
    errors: list[dict] = []

    for upload in files:
        try:
            stem, pages, assets = await _extract_pages_from_upload(upload)
            zip_bytes = build_package(
                title=stem,
                pages=pages,
                assets=assets,
                base_assets_dir=BASE_DIR / "exe_base",
            )
            converted.append(
                {
                    "source": upload.filename or stem,
                    "download_name": _safe_zip_name(stem),
                    "zip_bytes": zip_bytes,
                }
            )
        except HTTPException as exc:
            errors.append(
                {
                    "source": upload.filename or "(sin nombre)",
                    "error": exc.detail,
                }
            )

    if not converted:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No se pudo convertir ningun archivo.",
                "errors": errors,
            },
        )

    if not output_dir and len(converted) == 1:
        first = converted[0]
        zip_bytes = first["zip_bytes"]
        return StreamingResponse(
            io.BytesIO(zip_bytes),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{first["download_name"]}"',
                "Content-Length": str(len(zip_bytes)),
            },
        )

    destination = _resolve_output_dir(output_dir)
    saved_files: list[dict] = []

    for item in converted:
        out_path = destination / item["download_name"]
        out_path.write_bytes(item["zip_bytes"])
        saved_files.append(
            {
                "source": item["source"],
                "output": str(out_path),
                "filename": item["download_name"],
            }
        )

    return {
        "message": f"{len(saved_files)} archivo(s) convertido(s) en {destination}",
        "output_dir": str(destination),
        "saved_files": saved_files,
        "errors": errors,
    }
