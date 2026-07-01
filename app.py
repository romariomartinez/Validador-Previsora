from __future__ import annotations

import argparse
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

import cgi
import json
import mimetypes
import re
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from rules import AMPAROS, BOXES, RAMOS, TIPOS_CUENTA, get_requirements, serialize_requirement
from validator import StoredUpload, process_auto_run, process_run, safe_run_id


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"
RUNS_DIR = DATA_DIR / "runs"
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024


def json_response(handler: BaseHTTPRequestHandler, data: object, status: int = 200) -> None:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: BaseHTTPRequestHandler, message: str, status: int = 400) -> None:
    body = message.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


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


def save_upload(field: cgi.FieldStorage, box: str, run_dir: Path) -> StoredUpload | None:
    if not field.filename:
        return None
    rel_name = sanitize_relative_name(field.filename)
    target = run_dir / "input" / box / rel_name
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("wb") as output:
        shutil.copyfileobj(field.file, output)

    return StoredUpload(box=box, path=target, relative_name=rel_name)


class PrevisoraHandler(BaseHTTPRequestHandler):
    server_version = "PrevisoraRadicador/0.1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            return self.serve_file(STATIC_DIR / "index.html")
        if path.startswith("/static/"):
            rel = path.removeprefix("/static/")
            return self.serve_file(STATIC_DIR / sanitize_relative_name(rel))
        if path == "/api/options":
            return json_response(
                self,
                {
                    "ramos": RAMOS,
                    "amparos": AMPAROS,
                    "tipos_cuenta": TIPOS_CUENTA,
                    "boxes": BOXES,
                },
            )
        if path == "/api/requirements":
            return self.handle_requirements(parsed.query)
        if path.startswith("/download/"):
            return self.handle_download(path)

        return text_response(self, "No encontrado", 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/process":
            return self.handle_process()
        if parsed.path == "/api/process-auto":
            return self.handle_auto_process()
        return text_response(self, "No encontrado", 404)

    def serve_file(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            if STATIC_DIR.resolve() not in resolved.parents and resolved != (STATIC_DIR / "index.html").resolve():
                return text_response(self, "Ruta no permitida", 403)
            if not resolved.exists() or not resolved.is_file():
                return text_response(self, "No encontrado", 404)
            content = resolved.read_bytes()
        except OSError:
            return text_response(self, "No se pudo leer el archivo", 500)

        mime = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def handle_requirements(self, query: str) -> None:
        params = parse_qs(query)
        ramo = params.get("ramo", ["SOAT"])[0]
        amparo = params.get("amparo", ["Gasto Medico"])[0]
        tipo = params.get("tipo_cuenta", ["Factura Presentada Por Primera Vez"])[0]
        pdf_mode = params.get("pdf_furips_furtran", ["false"])[0] == "true"
        try:
            requirements = get_requirements(ramo, amparo, tipo, pdf_mode)
        except KeyError as exc:
            return json_response(self, {"error": str(exc)}, 400)
        return json_response(self, {"requirements": [serialize_requirement(item) for item in requirements]})

    def handle_download(self, path: str) -> None:
        raw = path.removeprefix("/download/")
        parts = [part for part in raw.split("/") if part]
        if len(parts) < 2:
            return text_response(self, "Ruta de descarga invalida", 400)
        run_id = sanitize_relative_name(parts[0])
        rel = sanitize_relative_name("/".join(parts[1:]))
        target = (RUNS_DIR / run_id / rel).resolve()
        run_root = (RUNS_DIR / run_id).resolve()
        if run_root not in target.parents and target != run_root:
            return text_response(self, "Ruta no permitida", 403)
        if not target.exists() or not target.is_file():
            return text_response(self, "No encontrado", 404)

        content = target.read_bytes()
        mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
        self.end_headers()
        self.wfile.write(content)

    def handle_process(self) -> None:
        form = self.read_form()
        if form is None:
            return

        metadata = self.read_metadata(form)

        run_dir = RUNS_DIR / safe_run_id()
        run_dir.mkdir(parents=True, exist_ok=True)
        stored: list[StoredUpload] = []

        for box in BOXES:
            key = f"files_{box}"
            fields = form[key] if key in form else []
            if not isinstance(fields, list):
                fields = [fields]
            for field in fields:
                if getattr(field, "filename", None):
                    saved = save_upload(field, box, run_dir)
                    if saved:
                        stored.append(saved)

        try:
            result = process_run(run_dir, RUNS_DIR, metadata, stored)
        except KeyError as exc:
            return json_response(self, {"error": str(exc)}, 400)
        except Exception as exc:
            return json_response(self, {"error": f"Error procesando lote: {exc}"}, 500)

        return json_response(self, result)

    def handle_auto_process(self) -> None:
        form = self.read_form()
        if form is None:
            return

        metadata = self.read_metadata(form)

        run_dir = RUNS_DIR / safe_run_id()
        run_dir.mkdir(parents=True, exist_ok=True)
        stored: list[StoredUpload] = []

        fields = form["files_AUTO"] if "files_AUTO" in form else []
        if not isinstance(fields, list):
            fields = [fields]
        for field in fields:
            if getattr(field, "filename", None):
                saved = save_upload(field, "INBOX", run_dir)
                if saved:
                    stored.append(saved)

        try:
            result = process_auto_run(run_dir, RUNS_DIR, metadata, stored)
        except KeyError as exc:
            return json_response(self, {"error": str(exc)}, 400)
        except Exception as exc:
            return json_response(self, {"error": f"Error procesando lote automatico: {exc}"}, 500)

        return json_response(self, result)

    def read_form(self) -> cgi.FieldStorage | None:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > MAX_UPLOAD_BYTES:
            json_response(self, {"error": "El cargue supera 1 GB."}, 413)
            return None

        return cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": self.headers.get("Content-Type"),
                "CONTENT_LENGTH": str(content_length),
            },
        )

    def read_metadata(self, form: cgi.FieldStorage) -> dict[str, str]:
        return {
            "nit": (form.getfirst("nit", "") or "").strip(),
            "factura": (form.getfirst("factura", "") or "").strip(),
            "sucursal": (form.getfirst("sucursal", "") or "").strip(),
            "ramo": form.getfirst("ramo", "SOAT"),
            "amparo": form.getfirst("amparo", "Gasto Medico"),
            "tipo_cuenta": form.getfirst("tipo_cuenta", "Factura Presentada Por Primera Vez"),
            "pdf_furips_furtran": form.getfirst("pdf_furips_furtran", "false"),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Radicador Previsora local")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((args.host, args.port), PrevisoraHandler)
    print(f"Previsora Radicador en http://{args.host}:{args.port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
