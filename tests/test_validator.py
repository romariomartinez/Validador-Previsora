import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validator import StoredUpload, process_auto_run, process_run


class ValidatorTests(unittest.TestCase):
    def make_file(self, root: Path, box: str, name: str, content: bytes = b"x") -> StoredUpload:
        path = root / "input" / box / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return StoredUpload(box=box, path=path, relative_name=name)

    def test_soat_gasto_medico_primera_vez_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "run1"
            run.mkdir(parents=True)
            uploads = [
                self.make_file(run, "FURIPS", "Furips 1.txt"),
                self.make_file(run, "FURIPS", "Furips 2.txt"),
                self.make_file(run, "CUV", "CUV.json", json.dumps({"ok": True}).encode()),
                self.make_file(run, "RIPS", "RIPS.json", json.dumps({"ok": True}).encode()),
                self.make_file(run, "SOPORTES", "FEV_999999999_A999999999.pdf"),
                self.make_file(run, "SOPORTES", "HAM_999999999_A999999999.pdf"),
                self.make_file(run, "SOPORTES", "PDX_999999999_A999999999.pdf"),
                self.make_file(run, "SOPORTES", "Furips_999999999_A999999999.pdf"),
            ]
            result = process_run(
                run,
                root / "runs",
                {
                    "nit": "999999999",
                    "factura": "A999999999",
                    "sucursal": "",
                    "ramo": "SOAT",
                    "amparo": "Gasto Medico",
                    "tipo_cuenta": "Factura Presentada Por Primera Vez",
                    "pdf_furips_furtran": "false",
                },
                uploads,
            )
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["summary"]["ready_zips"], 4)

    def test_missing_required_support_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "run1"
            run.mkdir(parents=True)
            uploads = [
                self.make_file(run, "SOPORTES", "CRC_999999999_A999999999.pdf"),
            ]
            result = process_run(
                run,
                root / "runs",
                {
                    "nit": "999999999",
                    "factura": "A999999999",
                    "sucursal": "",
                    "ramo": "SOAT",
                    "amparo": "Gasto Medico",
                    "tipo_cuenta": "Aceptacion",
                    "pdf_furips_furtran": "false",
                },
                uploads,
            )
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["summary"]["ready_zips"], 0)
            messages = " ".join(item["message"] for item in result["issues"])
            self.assertIn("HEV", messages)

    def test_auto_builder_classifies_and_builds_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "run1"
            run.mkdir(parents=True)
            uploads = [
                self.make_file(run, "INBOX", "Furips 1.txt"),
                self.make_file(run, "INBOX", "Furips 2.txt"),
                self.make_file(run, "INBOX", "CUV.json", json.dumps({"ok": True}).encode()),
                self.make_file(run, "INBOX", "RIPS.json", json.dumps({"ok": True}).encode()),
                self.make_file(run, "INBOX", "FEV_999999999_A999999999.pdf"),
                self.make_file(run, "INBOX", "HAM_999999999_A999999999.pdf"),
                self.make_file(run, "INBOX", "PDX_999999999_A999999999.pdf"),
                self.make_file(run, "INBOX", "Furips_999999999_A999999999.pdf"),
            ]
            result = process_auto_run(
                run,
                root / "runs",
                {
                    "nit": "999999999",
                    "factura": "A999999999",
                    "sucursal": "",
                    "ramo": "SOAT",
                    "amparo": "Gasto Medico",
                    "tipo_cuenta": "Factura Presentada Por Primera Vez",
                    "pdf_furips_furtran": "false",
                },
                uploads,
            )
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["summary"]["ready_zips"], 4)
            boxes = {item["box"] for item in result["classification"]}
            self.assertIn("SOPORTES", boxes)
            self.assertIn("RIPS", boxes)
            self.assertIn("CUV", boxes)

    def test_auto_builder_blocks_ambiguous_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "run1"
            run.mkdir(parents=True)
            uploads = [
                self.make_file(run, "INBOX", "datos.json", json.dumps({"ok": True}).encode()),
                self.make_file(run, "INBOX", "Furips 1.txt"),
                self.make_file(run, "INBOX", "Furips 2.txt"),
                self.make_file(run, "INBOX", "FEV_999999999_A999999999.pdf"),
                self.make_file(run, "INBOX", "HAM_999999999_A999999999.pdf"),
                self.make_file(run, "INBOX", "PDX_999999999_A999999999.pdf"),
                self.make_file(run, "INBOX", "Furips_999999999_A999999999.pdf"),
            ]
            result = process_auto_run(
                run,
                root / "runs",
                {
                    "nit": "999999999",
                    "factura": "A999999999",
                    "sucursal": "",
                    "ramo": "SOAT",
                    "amparo": "Gasto Medico",
                    "tipo_cuenta": "Factura Presentada Por Primera Vez",
                    "pdf_furips_furtran": "false",
                },
                uploads,
            )
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["summary"]["ready_zips"], 0)
            messages = " ".join(item["message"] for item in result["issues"])
            self.assertIn("CUV o RIPS", messages)


if __name__ == "__main__":
    unittest.main()
