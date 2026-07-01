from dataclasses import dataclass, replace
from typing import Iterable


BOXES = {
    "CUV": {
        "label": "Caja CUV",
        "limit_mb": 100,
        "output_name": "01_CUV.zip",
    },
    "RIPS": {
        "label": "Caja RIPS JSON",
        "limit_mb": 100,
        "output_name": "02_RIPS_JSON.zip",
    },
    "FURIPS": {
        "label": "Caja FURIPS",
        "limit_mb": 100,
        "output_name": "03_FURIPS.zip",
    },
    "FURTRAN": {
        "label": "Caja FURTRAN",
        "limit_mb": 100,
        "output_name": "03_FURTRAN.zip",
    },
    "SOPORTES": {
        "label": "Caja de soportes",
        "limit_mb": 500,
        "output_name": "04_SOPORTES.zip",
    },
}

PDF_MAX_MB = 20

RAMOS = ("SOAT", "AP")
AMPAROS = ("Gasto Medico", "Gasto Transporte")
TIPOS_CUENTA = (
    "Factura Presentada Por Primera Vez",
    "Respuesta a una Objecion",
    "Aceptacion",
)

SUPPORT_PREFIXES = {
    "FEV": "Factura electronica",
    "EPI": "Historia clinica",
    "HAM": "Historia clinica",
    "HAU": "Historia clinica",
    "HAO": "Historia clinica",
    "PDX": "Documentos soporte historia clinica",
    "FURIPS": "Furips en PDF",
    "FURTRAN": "Furtran en PDF",
    "FMO": "Factura de osteosintesis",
    "CRC": "Otros archivos / respuesta",
    "HEV": "Nota contable",
    "RAN": "Documento de reclamacion",
}

HISTORIA_PREFIXES = ("EPI", "HAM", "HAU", "HAO")


@dataclass(frozen=True)
class Requirement:
    code: str
    label: str
    box: str
    kind: str
    required: bool
    patterns: tuple[str, ...] = ()
    note: str = ""


def req(
    code: str,
    label: str,
    box: str,
    kind: str,
    required: bool,
    patterns: Iterable[str] = (),
    note: str = "",
) -> Requirement:
    return Requirement(code, label, box, kind, required, tuple(patterns), note)


COMMON_SUPPORT_OPTIONALS = (
    req("fmo_pdf", "FMO - Factura de osteosintesis", "SOPORTES", "pdf_prefix", False, ("FMO",)),
)


SCENARIOS: dict[tuple[str, str, str], tuple[Requirement, ...]] = {
    (
        "SOAT",
        "Gasto Medico",
        "Factura Presentada Por Primera Vez",
    ): (
        req("furips_1_txt", "Furips 1 TXT", "FURIPS", "txt_contains", True, ("furips 1", "furips_1", "furips1")),
        req("furips_2_txt", "Furips 2 TXT", "FURIPS", "txt_contains", True, ("furips 2", "furips_2", "furips2")),
        req("fev_pdf", "FEV - Factura electronica", "SOPORTES", "pdf_prefix", True, ("FEV",)),
        req("historia_pdf", "Historia clinica", "SOPORTES", "pdf_any_prefix", True, HISTORIA_PREFIXES),
        req("pdx_pdf", "PDX - Soportes de historia clinica", "SOPORTES", "pdf_prefix", True, ("PDX",)),
        req("furips_pdf", "Furips PDF", "SOPORTES", "pdf_prefix", True, ("FURIPS",)),
        *COMMON_SUPPORT_OPTIONALS,
        req("crc_pdf", "CRC - Otros archivos", "SOPORTES", "pdf_prefix", False, ("CRC",)),
        req("cuv_file", "CUV TXT o JSON", "CUV", "any_ext", True, (".txt", ".json")),
        req("rips_json", "RIPS JSON", "RIPS", "any_ext", True, (".json",)),
    ),
    (
        "SOAT",
        "Gasto Medico",
        "Respuesta a una Objecion",
    ): (
        req("fev_pdf", "FEV - Factura electronica", "SOPORTES", "pdf_prefix", False, ("FEV",)),
        req("historia_pdf", "Historia clinica", "SOPORTES", "pdf_any_prefix", True, HISTORIA_PREFIXES),
        req("pdx_pdf", "PDX - Soportes de historia clinica", "SOPORTES", "pdf_prefix", True, ("PDX",)),
        req("furips_pdf", "Furips PDF", "SOPORTES", "pdf_prefix", False, ("FURIPS",)),
        req("crc_pdf", "CRC - Otros archivos", "SOPORTES", "pdf_prefix", True, ("CRC",)),
    ),
    (
        "SOAT",
        "Gasto Medico",
        "Aceptacion",
    ): (
        req("hev_pdf", "HEV - Nota contable", "SOPORTES", "pdf_prefix", True, ("HEV",)),
        req("crc_pdf", "CRC - Otros archivos", "SOPORTES", "pdf_prefix", True, ("CRC",)),
    ),
    (
        "SOAT",
        "Gasto Transporte",
        "Factura Presentada Por Primera Vez",
    ): (
        req("furtran_txt", "Furtran TXT", "FURTRAN", "txt_contains", True, ("furtran", "futran")),
        req("furips_2_txt", "Furips 2 TXT", "FURIPS", "txt_contains", True, ("furips 2", "furips_2", "furips2")),
        req("fev_pdf", "FEV - Factura electronica", "SOPORTES", "pdf_prefix", True, ("FEV",)),
        req("historia_pdf", "Historia clinica", "SOPORTES", "pdf_any_prefix", True, HISTORIA_PREFIXES),
        req("pdx_pdf", "PDX - Soportes de historia clinica", "SOPORTES", "pdf_prefix", True, ("PDX",)),
        req("furtran_pdf", "Furtran PDF", "SOPORTES", "pdf_prefix", True, ("FURTRAN",)),
        req("crc_pdf", "CRC - Otros archivos", "SOPORTES", "pdf_prefix", False, ("CRC",)),
        req("cuv_file", "CUV TXT o JSON", "CUV", "any_ext", True, (".txt", ".json")),
        req("rips_json", "RIPS JSON", "RIPS", "any_ext", True, (".json",)),
    ),
    (
        "SOAT",
        "Gasto Transporte",
        "Respuesta a una Objecion",
    ): (
        req("fev_pdf", "FEV - Factura electronica", "SOPORTES", "pdf_prefix", False, ("FEV",)),
        req("historia_pdf", "Historia clinica", "SOPORTES", "pdf_any_prefix", True, HISTORIA_PREFIXES),
        req("pdx_pdf", "PDX - Soportes de historia clinica", "SOPORTES", "pdf_prefix", True, ("PDX",)),
        req("furtran_pdf", "Furtran PDF", "SOPORTES", "pdf_prefix", False, ("FURTRAN",)),
        req("crc_pdf", "CRC - Otros archivos", "SOPORTES", "pdf_prefix", True, ("CRC",)),
    ),
    (
        "SOAT",
        "Gasto Transporte",
        "Aceptacion",
    ): (
        req("hev_pdf", "HEV - Nota contable", "SOPORTES", "pdf_prefix", True, ("HEV",)),
        req("crc_pdf", "CRC - Otros archivos", "SOPORTES", "pdf_prefix", True, ("CRC",)),
    ),
    (
        "AP",
        "Gasto Medico",
        "Factura Presentada Por Primera Vez",
    ): (
        req("fev_pdf", "FEV - Factura electronica", "SOPORTES", "pdf_prefix", True, ("FEV",)),
        req("historia_pdf", "Historia clinica", "SOPORTES", "pdf_any_prefix", True, HISTORIA_PREFIXES),
        req("pdx_pdf", "PDX - Soportes de historia clinica", "SOPORTES", "pdf_prefix", True, ("PDX",)),
        *COMMON_SUPPORT_OPTIONALS,
        req("ran_pdf", "RAN - Documento reclamacion", "SOPORTES", "pdf_prefix", True, ("RAN",)),
        req("crc_pdf", "CRC - Otros archivos", "SOPORTES", "pdf_prefix", False, ("CRC",)),
        req("cuv_file", "CUV TXT o JSON", "CUV", "any_ext", True, (".txt", ".json")),
        req("rips_json", "RIPS JSON", "RIPS", "any_ext", True, (".json",)),
    ),
    (
        "AP",
        "Gasto Medico",
        "Respuesta a una Objecion",
    ): (
        req("crc_pdf", "CRC - Otros archivos", "SOPORTES", "pdf_prefix", True, ("CRC",)),
    ),
    (
        "AP",
        "Gasto Medico",
        "Aceptacion",
    ): (
        req("hev_pdf", "HEV - Nota contable", "SOPORTES", "pdf_prefix", True, ("HEV",)),
        req("crc_pdf", "CRC - Otros archivos", "SOPORTES", "pdf_prefix", True, ("CRC",)),
    ),
    (
        "AP",
        "Gasto Transporte",
        "Factura Presentada Por Primera Vez",
    ): (
        req("fev_pdf", "FEV - Factura electronica", "SOPORTES", "pdf_prefix", True, ("FEV",)),
        req("historia_pdf", "Historia clinica", "SOPORTES", "pdf_any_prefix", True, HISTORIA_PREFIXES),
        req("pdx_pdf", "PDX - Soportes de historia clinica", "SOPORTES", "pdf_prefix", True, ("PDX",)),
        *COMMON_SUPPORT_OPTIONALS,
        req("ran_pdf", "RAN - Documento reclamacion", "SOPORTES", "pdf_prefix", True, ("RAN",)),
        req("hev_pdf", "HEV - Nota contable", "SOPORTES", "pdf_prefix", False, ("HEV",)),
        req("crc_pdf", "CRC - Otros archivos", "SOPORTES", "pdf_prefix", True, ("CRC",)),
        req("cuv_file", "CUV TXT o JSON", "CUV", "any_ext", True, (".txt", ".json")),
        req("rips_json", "RIPS JSON", "RIPS", "any_ext", True, (".json",)),
    ),
    (
        "AP",
        "Gasto Transporte",
        "Respuesta a una Objecion",
    ): (
        req("crc_pdf", "CRC - Otros archivos", "SOPORTES", "pdf_prefix", True, ("CRC",)),
    ),
    (
        "AP",
        "Gasto Transporte",
        "Aceptacion",
    ): (
        req("hev_pdf", "HEV - Nota contable", "SOPORTES", "pdf_prefix", True, ("HEV",)),
        req("crc_pdf", "CRC - Otros archivos", "SOPORTES", "pdf_prefix", True, ("CRC",)),
    ),
}


def get_requirements(
    ramo: str,
    amparo: str,
    tipo_cuenta: str,
    pdf_furips_furtran: bool = False,
) -> tuple[Requirement, ...]:
    key = (ramo, amparo, tipo_cuenta)
    if key not in SCENARIOS:
        raise KeyError(f"No hay reglas para {key}")

    requirements = SCENARIOS[key]
    if not pdf_furips_furtran:
        return requirements

    individual_codes = {"furips_1_txt", "furips_2_txt", "furtran_txt"}
    adjusted = []
    for item in requirements:
        if item.code in individual_codes and item.required:
            adjusted.append(
                replace(
                    item,
                    required=False,
                    note="Marcado opcional porque se activo PDF Furips/Furtran.",
                )
            )
        else:
            adjusted.append(item)
    return tuple(adjusted)


def requirement_groups(requirements: Iterable[Requirement]) -> dict[str, list[Requirement]]:
    grouped: dict[str, list[Requirement]] = {box: [] for box in BOXES}
    for item in requirements:
        grouped.setdefault(item.box, []).append(item)
    return grouped


def required_boxes(requirements: Iterable[Requirement]) -> set[str]:
    return {item.box for item in requirements if item.required}


def serialize_requirement(item: Requirement) -> dict[str, object]:
    return {
        "code": item.code,
        "label": item.label,
        "box": item.box,
        "box_label": BOXES[item.box]["label"],
        "kind": item.kind,
        "required": item.required,
        "patterns": list(item.patterns),
        "note": item.note,
    }
