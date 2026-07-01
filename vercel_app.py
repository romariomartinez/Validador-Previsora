from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile

from rules import AMPAROS, BOXES, RAMOS, TIPOS_CUENTA, get_requirements, serialize_requirement
from validator import StoredUpload, process_auto_run, process_run, safe_run_id


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
if os.environ.get("VERCEL"):
    RUNS_DIR = Path(tempfile.gettempdir()) / "previsora-radicador" / "runs"
else:
    RUNS_DIR = ROOT / "data" / "runs"
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024

app = FastAPI(title="Radicador Previsora")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def sanitize_relative_name(name: str) -> str:
    cleaned = unquote(name or "archivo")
    cleaned = cleaned.replace("\\", "/")
    parts = []
    for part in cleaned.split("/"):
        part = part.strip().strip(".")
        part = re.sub(r"[^A-Za-z0-9._ -]", "_", part)
        if part:
            parts.append(part)
    return "/".join(parts) or "archivo"


async def save_upload(upload: UploadFile, box: str, run_dir: Path) -> StoredUpload | None:
    if not upload.filename:
        return None
    rel_name = sanitize_relative_name(upload.filename)
    target = run_dir / "input" / box / rel_name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as output:
        shutil.copyfileobj(upload.file, output)
    await upload.close()
    return StoredUpload(box=box, path=target, relative_name=rel_name)


def read_form_value(form: object, key: str, default: str = "") -> str:
    value = form.get(key, default)
    if isinstance(value, UploadFile):
        return default
    return str(value or default).strip()


def read_metadata(form: object) -> dict[str, str]:
    return {
        "nit": read_form_value(form, "nit"),
        "factura": read_form_value(form, "factura"),
        "sucursal": read_form_value(form, "sucursal"),
        "ramo": read_form_value(form, "ramo", "SOAT"),
        "amparo": read_form_value(form, "amparo", "Gasto Medico"),
        "tipo_cuenta": read_form_value(form, "tipo_cuenta", "Factura Presentada Por Primera Vez"),
        "pdf_furips_furtran": read_form_value(form, "pdf_furips_furtran", "false"),
    }


async def parse_form(request: Request) -> object | JSONResponse:
    content_length = int(request.headers.get("content-length", "0") or "0")
    if content_length > MAX_UPLOAD_BYTES:
        return JSONResponse({"error": "El cargue supera 1 GB."}, status_code=413)
    return await request.form()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/options")
async def options() -> dict[str, object]:
    return {
        "ramos": RAMOS,
        "amparos": AMPAROS,
        "tipos_cuenta": TIPOS_CUENTA,
        "boxes": BOXES,
    }


@app.get("/api/requirements")
async def requirements(
    ramo: str = "SOAT",
    amparo: str = "Gasto Medico",
    tipo_cuenta: str = "Factura Presentada Por Primera Vez",
    pdf_furips_furtran: str = "false",
) -> JSONResponse:
    try:
        items = get_requirements(ramo, amparo, tipo_cuenta, pdf_furips_furtran == "true")
    except KeyError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"requirements": [serialize_requirement(item) for item in items]})


@app.post("/api/process")
async def process_manual(request: Request) -> JSONResponse:
    form = await parse_form(request)
    if isinstance(form, JSONResponse):
        return form

    metadata = read_metadata(form)
    run_dir = RUNS_DIR / safe_run_id()
    run_dir.mkdir(parents=True, exist_ok=True)

    stored: list[StoredUpload] = []
    for box in BOXES:
        key = f"files_{box}"
        for value in form.getlist(key):
            if isinstance(value, UploadFile) and value.filename:
                saved = await save_upload(value, box, run_dir)
                if saved:
                    stored.append(saved)

    try:
        result = process_run(run_dir, RUNS_DIR, metadata, stored)
    except KeyError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": f"Error procesando lote: {exc}"}, status_code=500)
    return JSONResponse(result)


@app.post("/api/process-auto")
async def process_auto(request: Request) -> JSONResponse:
    form = await parse_form(request)
    if isinstance(form, JSONResponse):
        return form

    metadata = read_metadata(form)
    run_dir = RUNS_DIR / safe_run_id()
    run_dir.mkdir(parents=True, exist_ok=True)

    stored: list[StoredUpload] = []
    for value in form.getlist("files_AUTO"):
        if isinstance(value, UploadFile) and value.filename:
            saved = await save_upload(value, "INBOX", run_dir)
            if saved:
                stored.append(saved)

    try:
        result = process_auto_run(run_dir, RUNS_DIR, metadata, stored)
    except KeyError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": f"Error procesando lote automatico: {exc}"}, status_code=500)
    return JSONResponse(result)


@app.get("/download/{run_id}/{file_path:path}")
async def download(run_id: str, file_path: str) -> Response:
    safe_run_id_value = sanitize_relative_name(run_id)
    safe_file_path = sanitize_relative_name(file_path)
    target = (RUNS_DIR / safe_run_id_value / safe_file_path).resolve()
    run_root = (RUNS_DIR / safe_run_id_value).resolve()
    if run_root not in target.parents and target != run_root:
        return PlainTextResponse("Ruta no permitida", status_code=403)
    if not target.exists() or not target.is_file():
        return PlainTextResponse("No encontrado", status_code=404)

    content = target.read_bytes()
    mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    headers = {"Content-Disposition": f'attachment; filename="{target.name}"'}
    return Response(content, media_type=mime, headers=headers)


@app.get("/{path:path}")
async def spa_fallback(path: str) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
