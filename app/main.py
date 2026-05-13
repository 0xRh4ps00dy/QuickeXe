import io
import os
import uuid
import tempfile
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

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

ALLOWED_EXTENSIONS = {".docx", ".pdf"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/convert")
async def convert(file: UploadFile = File(...)):
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
        pages = parse_docx(io.BytesIO(content))
    else:
        pages = parse_pdf(io.BytesIO(content))

    if not pages:
        raise HTTPException(
            status_code=422,
            detail="No se pudo extraer contenido del archivo. Comprueba que el documento tiene texto digital y está bien estructurado.",
        )

    zip_bytes = build_package(
        title=stem,
        pages=pages,
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
