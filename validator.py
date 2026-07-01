from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from rules import BOXES, PDF_MAX_MB, SUPPORT_PREFIXES, Requirement, get_requirements, required_boxes, serialize_requirement


PDF_NAME_PATTERN = re.compile(r"^(?P<prefix>[A-Za-z]+)_[A-Za-z0-9.-]+_[A-Za-z0-9.-]+\.pdf$", re.IGNORECASE)


@dataclass
class StoredUpload:
    box: str
    path: Path
    relative_name: str


@dataclass
class FileItem:
    box: str
    name: str
    size: int
    source_path: Path
    zip_member: str | None = None

    @property
    def suffix(self) -> str:
        return Path(self.name).suffix.lower()

    @property
    def basename(self) -> str:
        return Path(self.name).name

    @property
    def lower_name(self) -> str:
        return self.basename.lower()

    def read_bytes(self, limit: int = 25 * 1024 * 1024) -> bytes:
        if self.size > limit:
            raise ValueError("Archivo demasiado grande para leer en memoria.")
        if self.zip_member:
            with zipfile.ZipFile(self.source_path) as zf:
                return zf.read(self.zip_member)
        return self.source_path.read_bytes()


def bytes_to_mb(value: int) -> float:
    return round(value / (1024 * 1024), 2)


def issue(level: str, message: str, box: str | None = None, file: str | None = None) -> dict[str, str]:
    data = {"level": level, "message": message}
    if box:
        data["box"] = box
    if file:
        data["file"] = file
    return data


def safe_run_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{datetime.now().microsecond:06d}"


def build_inventory(stored_uploads: Iterable[StoredUpload]) -> tuple[list[FileItem], list[dict[str, str]]]:
    files: list[FileItem] = []
    issues: list[dict[str, str]] = []

    for upload in stored_uploads:
        if upload.path.suffix.lower() != ".zip":
            files.append(
                FileItem(
                    box=upload.box,
                    name=upload.relative_name,
                    size=upload.path.stat().st_size,
                    source_path=upload.path,
                )
            )
            continue

        try:
            with zipfile.ZipFile(upload.path) as zf:
                bad = zf.testzip()
                if bad:
                    issues.append(issue("error", f"El ZIP esta corrupto en la entrada {bad}.", upload.box, upload.relative_name))
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    files.append(
                        FileItem(
                            box=upload.box,
                            name=info.filename,
                            size=info.file_size,
                            source_path=upload.path,
                            zip_member=info.filename,
                        )
                    )
        except zipfile.BadZipFile:
            issues.append(issue("error", "El archivo tiene extension .zip pero no se pudo abrir.", upload.box, upload.relative_name))

    return files, issues


def normalize_text(value: str) -> str:
    return re.sub(r"[\s_-]+", " ", value.lower()).strip()


def matches_requirement(item: FileItem, requirement: Requirement) -> bool:
    if item.box != requirement.box:
        return False

    name = item.basename
    lower = item.lower_name

    if requirement.kind == "any_ext":
        return item.suffix in {pattern.lower() for pattern in requirement.patterns}

    if requirement.kind == "txt_contains":
        if item.suffix != ".txt":
            return False
        normalized = normalize_text(name)
        return any(normalize_text(pattern) in normalized for pattern in requirement.patterns)

    if requirement.kind == "pdf_prefix":
        if item.suffix != ".pdf":
            return False
        return any(lower.startswith(f"{pattern.lower()}_") for pattern in requirement.patterns)

    if requirement.kind == "pdf_any_prefix":
        if item.suffix != ".pdf":
            return False
        return any(lower.startswith(f"{pattern.lower()}_") for pattern in requirement.patterns)

    return False


def validate_json_files(files: Iterable[FileItem]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for item in files:
        if item.suffix != ".json":
            continue
        try:
            json.loads(item.read_bytes().decode("utf-8-sig"))
        except UnicodeDecodeError:
            issues.append(issue("error", "El JSON no esta codificado como UTF-8.", item.box, item.name))
        except json.JSONDecodeError as exc:
            issues.append(issue("error", f"JSON invalido: linea {exc.lineno}, columna {exc.colno}.", item.box, item.name))
        except ValueError as exc:
            issues.append(issue("warning", str(exc), item.box, item.name))
    return issues


def validate_support_names(files: Iterable[FileItem], nit: str = "", factura: str = "") -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    nit = nit.strip()
    factura = factura.strip()

    for item in files:
        if item.box != "SOPORTES":
            continue
        if item.suffix != ".pdf":
            issues.append(issue("error", "La caja de soportes solo debe contener PDFs.", item.box, item.name))
            continue

        if item.size > PDF_MAX_MB * 1024 * 1024:
            issues.append(issue("error", f"El PDF supera {PDF_MAX_MB} MB.", item.box, item.name))

        match = PDF_NAME_PATTERN.match(item.basename)
        if not match:
            issues.append(
                issue(
                    "warning",
                    "El nombre no sigue el patron PREFIJO_NIT_FACTURA.pdf.",
                    item.box,
                    item.name,
                )
            )
            continue

        prefix = match.group("prefix").upper()
        if prefix not in SUPPORT_PREFIXES:
            issues.append(issue("warning", f"Prefijo de soporte no reconocido: {prefix}.", item.box, item.name))

        parts = item.basename[:-4].split("_", 2)
        if nit and len(parts) >= 2 and parts[1].lower() != nit.lower():
            issues.append(issue("warning", f"El NIT del nombre ({parts[1]}) no coincide con el NIT digitado.", item.box, item.name))
        if factura and len(parts) >= 3 and parts[2].lower() != factura.lower():
            issues.append(
                issue(
                    "warning",
                    f"El numero de factura del nombre ({parts[2]}) no coincide con el digitado.",
                    item.box,
                    item.name,
                )
            )

    return issues


def validate_box_sizes(stored_uploads: Iterable[StoredUpload], files: Iterable[FileItem]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    raw_by_box: dict[str, int] = {box: 0 for box in BOXES}
    zip_counts: dict[str, int] = {box: 0 for box in BOXES}
    raw_counts: dict[str, int] = {box: 0 for box in BOXES}

    for upload in stored_uploads:
        limit = BOXES[upload.box]["limit_mb"] * 1024 * 1024
        size = upload.path.stat().st_size
        if upload.path.suffix.lower() == ".zip":
            zip_counts[upload.box] += 1
            if size > limit:
                issues.append(issue("error", f"El ZIP supera el limite de {BOXES[upload.box]['limit_mb']} MB.", upload.box, upload.relative_name))
        else:
            raw_counts[upload.box] += 1
            raw_by_box[upload.box] += size

    for item in files:
        if item.zip_member and item.size > BOXES[item.box]["limit_mb"] * 1024 * 1024:
            issues.append(issue("error", "Un archivo interno del ZIP supera el limite de la caja.", item.box, item.name))

    for box, total in raw_by_box.items():
        limit_mb = BOXES[box]["limit_mb"]
        if total > limit_mb * 1024 * 1024:
            issues.append(issue("error", f"Los archivos sueltos suman {bytes_to_mb(total)} MB y superan {limit_mb} MB.", box))

    for box in BOXES:
        if zip_counts[box] > 0 and raw_counts[box] > 0:
            issues.append(issue("error", "No mezcles ZIPs y archivos sueltos en la misma caja.", box))
        if zip_counts[box] > 1:
            issues.append(issue("error", "Carga solo un ZIP por caja.", box))

    return issues


def safe_extract_member_name(name: str) -> str | None:
    cleaned = name.replace("\\", "/")
    parts = []
    for part in cleaned.split("/"):
        part = part.strip().strip(".")
        if not part:
            continue
        if part in {"..", "."}:
            return None
        part = re.sub(r"[^A-Za-z0-9._ -]", "_", part)
        if part:
            parts.append(part)
    return "/".join(parts) if parts else None


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def expand_auto_uploads(run_dir: Path, raw_uploads: Iterable[StoredUpload]) -> tuple[list[StoredUpload], list[dict[str, str]]]:
    uploads: list[StoredUpload] = []
    issues: list[dict[str, str]] = []
    extract_root = run_dir / "auto_extraidos"

    for upload in raw_uploads:
        if upload.path.suffix.lower() != ".zip":
            uploads.append(upload)
            continue

        try:
            with zipfile.ZipFile(upload.path) as zf:
                bad = zf.testzip()
                if bad:
                    issues.append(issue("error", f"El ZIP esta corrupto en la entrada {bad}.", file=upload.relative_name))
                    continue
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    safe_name = safe_extract_member_name(info.filename)
                    if not safe_name:
                        issues.append(issue("error", "El ZIP contiene una ruta no permitida.", file=info.filename))
                        continue
                    target = unique_path(extract_root / Path(upload.relative_name).stem / safe_name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    uploads.append(
                        StoredUpload(
                            box="INBOX",
                            path=target,
                            relative_name=f"{upload.relative_name}/{safe_name}",
                        )
                    )
        except zipfile.BadZipFile:
            issues.append(issue("error", "El archivo tiene extension .zip pero no se pudo abrir.", file=upload.relative_name))

    return uploads, issues


def requirement_box_is_present(stored_uploads: Iterable[StoredUpload], requirement: Requirement) -> bool:
    files, _ = build_inventory(stored_uploads)
    return any(matches_requirement(item, requirement) for item in files)


def classify_named_upload(upload: StoredUpload, requirements: tuple[Requirement, ...]) -> tuple[str | None, str]:
    name = Path(upload.relative_name).name
    lower = name.lower()
    normalized = normalize_text(name)
    suffix = Path(name).suffix.lower()

    if suffix == ".pdf":
        return "SOPORTES", "PDF enviado a soportes"

    if suffix == ".json":
        if "rips" in lower or "rip" in lower:
            return "RIPS", "JSON identificado como RIPS por nombre"
        if "cuv" in lower:
            return "CUV", "JSON identificado como CUV por nombre"
        return None, "JSON sin nombre CUV/RIPS"

    if suffix == ".txt":
        for requirement in requirements:
            if requirement.kind == "txt_contains" and any(normalize_text(pattern) in normalized for pattern in requirement.patterns):
                return requirement.box, f"TXT identificado como {requirement.label}"
        if "cuv" in lower:
            return "CUV", "TXT identificado como CUV por nombre"
        return None, "TXT sin nombre CUV/FURIPS/FURTRAN"

    return None, "Extension no reconocida para armado automatico"


def classify_auto_uploads(
    run_dir: Path,
    metadata: dict[str, str],
    raw_uploads: list[StoredUpload],
) -> tuple[list[StoredUpload], list[dict[str, object]], list[dict[str, str]]]:
    requirements = get_requirements(
        metadata["ramo"],
        metadata["amparo"],
        metadata["tipo_cuenta"],
        metadata.get("pdf_furips_furtran") == "true",
    )
    expanded_uploads, issues = expand_auto_uploads(run_dir, raw_uploads)
    classified: list[StoredUpload] = []
    rows: list[dict[str, object]] = []
    pending_json: list[tuple[StoredUpload, str]] = []
    pending_txt: list[tuple[StoredUpload, str]] = []

    for upload in expanded_uploads:
        box, reason = classify_named_upload(upload, requirements)
        if box:
            assigned = StoredUpload(box=box, path=upload.path, relative_name=upload.relative_name)
            classified.append(assigned)
            rows.append(
                {
                    "file": upload.relative_name,
                    "box": box,
                    "box_label": BOXES[box]["label"],
                    "reason": reason,
                }
            )
            continue

        suffix = Path(upload.relative_name).suffix.lower()
        if suffix == ".json":
            pending_json.append((upload, reason))
        elif suffix == ".txt":
            pending_txt.append((upload, reason))
        else:
            rows.append({"file": upload.relative_name, "box": "", "box_label": "", "reason": reason})
            issues.append(issue("warning", reason, file=upload.relative_name))

    def assign(upload: StoredUpload, box: str, reason: str) -> None:
        assigned = StoredUpload(box=box, path=upload.path, relative_name=upload.relative_name)
        classified.append(assigned)
        rows.append(
            {
                "file": upload.relative_name,
                "box": box,
                "box_label": BOXES[box]["label"],
                "reason": reason,
            }
        )

    for upload, reason in pending_json:
        has_cuv = any(item.box == "CUV" for item in classified)
        has_rips = any(item.box == "RIPS" for item in classified)
        needs_cuv = any(item.box == "CUV" and item.required for item in requirements)
        needs_rips = any(item.box == "RIPS" and item.required for item in requirements)

        if needs_rips and not has_rips and (has_cuv or not needs_cuv):
            assign(upload, "RIPS", "JSON asignado a RIPS porque era la unica caja JSON pendiente")
        elif needs_cuv and not has_cuv and (has_rips or not needs_rips):
            assign(upload, "CUV", "JSON asignado a CUV porque era la unica caja JSON pendiente")
        else:
            rows.append({"file": upload.relative_name, "box": "", "box_label": "", "reason": reason})
            issues.append(
                issue(
                    "error",
                    "No pude decidir si este JSON es CUV o RIPS. Renombralo incluyendo CUV o RIPS.",
                    file=upload.relative_name,
                )
            )

    for upload, reason in pending_txt:
        has_cuv = any(item.box == "CUV" for item in classified)
        needs_cuv = any(item.box == "CUV" and item.required for item in requirements)
        missing_named_txt = [
            req
            for req in requirements
            if req.required and req.kind == "txt_contains" and not requirement_box_is_present(classified, req)
        ]

        if needs_cuv and not has_cuv and not missing_named_txt:
            assign(upload, "CUV", "TXT asignado a CUV porque no habia CUV pendiente por nombre")
        else:
            rows.append({"file": upload.relative_name, "box": "", "box_label": "", "reason": reason})
            issues.append(
                issue(
                    "error",
                    "No pude clasificar este TXT. Renombralo como CUV, Furips 1, Furips 2 o Furtran segun corresponda.",
                    file=upload.relative_name,
                )
            )

    return classified, rows, issues


def validate_requirements(files: Iterable[FileItem], requirements: Iterable[Requirement]) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    file_list = list(files)
    requirement_rows: list[dict[str, object]] = []
    issues: list[dict[str, str]] = []

    for requirement in requirements:
        matches = [item.name for item in file_list if matches_requirement(item, requirement)]
        ok = bool(matches)
        requirement_rows.append(
            {
                **serialize_requirement(requirement),
                "ok": ok,
                "matches": matches,
            }
        )
        if requirement.required and not ok:
            issues.append(
                issue(
                    "error",
                    f"Falta obligatorio: {requirement.label}.",
                    requirement.box,
                )
            )

    return requirement_rows, issues


def create_ready_zips(run_dir: Path, stored_uploads: Iterable[StoredUpload]) -> list[dict[str, str]]:
    ready_dir = run_dir / "ready"
    ready_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[dict[str, str]] = []
    uploads_by_box: dict[str, list[StoredUpload]] = {box: [] for box in BOXES}

    for upload in stored_uploads:
        uploads_by_box.setdefault(upload.box, []).append(upload)

    for box, uploads in uploads_by_box.items():
        if not uploads:
            continue

        output_path = ready_dir / BOXES[box]["output_name"]
        zip_uploads = [item for item in uploads if item.path.suffix.lower() == ".zip"]
        raw_uploads = [item for item in uploads if item.path.suffix.lower() != ".zip"]

        if len(zip_uploads) == 1 and not raw_uploads:
            shutil.copy2(zip_uploads[0].path, output_path)
        elif not zip_uploads:
            with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for item in raw_uploads:
                    zf.write(item.path, arcname=item.relative_name.replace("\\", "/"))
        else:
            continue

        outputs.append(
            {
                "box": box,
                "label": BOXES[box]["label"],
                "filename": str(output_path.relative_to(run_dir)).replace("\\", "/"),
                "size_mb": bytes_to_mb(output_path.stat().st_size),
            }
        )

    return outputs


def scan_duplicate_history(runs_root: Path, current_run: Path, metadata: dict[str, str]) -> list[dict[str, str]]:
    nit = metadata.get("nit", "").strip().lower()
    factura = metadata.get("factura", "").strip().lower()
    if not nit or not factura:
        return []

    filters = (
        metadata.get("ramo", ""),
        metadata.get("amparo", ""),
        metadata.get("tipo_cuenta", ""),
    )
    issues: list[dict[str, str]] = []
    now = datetime.now(timezone.utc)

    for report in runs_root.glob("*/report.json"):
        if current_run in report.parents:
            continue
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        meta = data.get("metadata", {})
        if meta.get("nit", "").strip().lower() != nit:
            continue
        if meta.get("factura", "").strip().lower() != factura:
            continue
        old_filters = (
            meta.get("ramo", ""),
            meta.get("amparo", ""),
            meta.get("tipo_cuenta", ""),
        )
        if old_filters != filters:
            continue
        created_raw = data.get("created_at")
        try:
            created_at = datetime.fromisoformat(created_raw)
        except (TypeError, ValueError):
            continue
        hours = (now - created_at).total_seconds() / 3600
        if hours <= 48:
            issues.append(
                issue(
                    "warning",
                    f"Hay una preparacion previa para el mismo NIT/factura/filtros hace {round(hours, 1)} horas. Previsora puede rechazar si ya existe radicado dentro de 48 horas.",
                )
            )
            break

    return issues


def process_run(
    run_dir: Path,
    runs_root: Path,
    metadata: dict[str, str],
    stored_uploads: list[StoredUpload],
    extra_issues: list[dict[str, str]] | None = None,
    classification: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    requirements = get_requirements(
        metadata["ramo"],
        metadata["amparo"],
        metadata["tipo_cuenta"],
        metadata.get("pdf_furips_furtran") == "true",
    )
    files, inventory_issues = build_inventory(stored_uploads)
    requirement_rows, requirement_issues = validate_requirements(files, requirements)
    issues = []
    issues.extend(inventory_issues)
    issues.extend(extra_issues or [])
    issues.extend(requirement_issues)
    issues.extend(validate_box_sizes(stored_uploads, files))
    issues.extend(validate_json_files(files))
    issues.extend(validate_support_names(files, metadata.get("nit", ""), metadata.get("factura", "")))
    issues.extend(scan_duplicate_history(runs_root, run_dir, metadata))

    if metadata.get("pdf_furips_furtran") == "true":
        issues.append(
            issue(
                "info",
                "PDF Furips/Furtran activo: las cajas individuales FURIPS/FURTRAN se validan como opcionales cuando aplica.",
            )
        )

    req_boxes = required_boxes(requirements)
    for box in req_boxes:
        if not any(item.box == box for item in files):
            issues.append(issue("error", "No se cargaron archivos en una caja requerida.", box))

    error_count = sum(1 for item in issues if item["level"] == "error")
    warning_count = sum(1 for item in issues if item["level"] == "warning")
    status = "error" if error_count else "warning" if warning_count else "ok"
    ready_zips = []
    if error_count:
        issues.append(
            issue(
                "info",
                "Paquetes bloqueados: corrige los errores obligatorios antes de generar ZIPs listos para radicar.",
            )
        )
    else:
        ready_zips = create_ready_zips(run_dir, stored_uploads)

    result: dict[str, object] = {
        "run_id": run_dir.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "metadata": metadata,
        "summary": {
            "files": len(files),
            "errors": error_count,
            "warnings": warning_count,
            "ready_zips": len(ready_zips),
        },
        "issues": issues,
        "requirements": requirement_rows,
        "files": [
            {
                "box": item.box,
                "box_label": BOXES[item.box]["label"],
                "name": item.name,
                "size_mb": bytes_to_mb(item.size),
                "from_zip": bool(item.zip_member),
            }
            for item in files
        ],
        "ready_zips": ready_zips,
    }
    if classification is not None:
        result["classification"] = classification

    (run_dir / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_report(run_dir / "reporte_validacion.md", result)
    return result


def process_auto_run(run_dir: Path, runs_root: Path, metadata: dict[str, str], raw_uploads: list[StoredUpload]) -> dict[str, object]:
    metadata = {**metadata, "modo": "automatico"}
    classified, classification, classification_issues = classify_auto_uploads(run_dir, metadata, raw_uploads)
    return process_run(
        run_dir,
        runs_root,
        metadata,
        classified,
        extra_issues=classification_issues,
        classification=classification,
    )


def write_markdown_report(path: Path, result: dict[str, object]) -> None:
    metadata = result["metadata"]
    lines = [
        "# Reporte de validacion Previsora",
        "",
        f"- Estado: {result['status']}",
        f"- Run: {result['run_id']}",
        f"- Fecha: {result['created_at']}",
        f"- NIT: {metadata.get('nit', '')}",
        f"- Factura/Lote: {metadata.get('factura', '')}",
        f"- Ramo: {metadata.get('ramo', '')}",
        f"- Amparo: {metadata.get('amparo', '')}",
        f"- Tipo cuenta: {metadata.get('tipo_cuenta', '')}",
        "",
        "## Hallazgos",
        "",
    ]

    issues = result.get("issues", [])
    if issues:
        for item in issues:
            box = f" [{item.get('box')}]" if item.get("box") else ""
            file = f" - {item.get('file')}" if item.get("file") else ""
            lines.append(f"- {item.get('level', '').upper()}{box}: {item.get('message')}{file}")
    else:
        lines.append("- Sin errores ni advertencias.")

    lines.extend(["", "## ZIPs listos", ""])
    zips = result.get("ready_zips", [])
    if zips:
        for item in zips:
            lines.append(f"- {item['label']}: {item['filename']} ({item['size_mb']} MB)")
    else:
        lines.append("- No se generaron ZIPs.")

    path.write_text("\n".join(lines), encoding="utf-8")
