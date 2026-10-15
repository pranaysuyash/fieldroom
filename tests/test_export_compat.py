"""Viewer-compatibility receipts for exported PDFs (FFL export hardening).

Automated Tier 2/3 reopen checks: every exported PDF must parse cleanly
under a second, independent PDF stack (pypdf) and render under PyMuPDF,
and pass qpdf structural validation when the binary is present. Manual
Acrobat/Preview/browser checks are a Tier 4 runbook
(docs/runbooks/viewer-verification.md); this suite is the always-on floor.
"""

import shutil
import subprocess
from pathlib import Path

import fitz
from fastapi.testclient import TestClient
from pypdf import PdfReader

from pdf_field_lab.server import app

FIXTURE = Path(__file__).parents[1] / "data" / "samples" / "RAr0Lq2Avu.pdf"


def _exported_pdf_bytes():
    with TestClient(app) as client, FIXTURE.open("rb") as handle:
        response = client.post("/api/sessions?fresh=true", files={"file": ("form6.pdf", handle, "application/pdf")})
    assert response.status_code == 200, response.text
    session = response.json()
    manifest = session["manifest"]
    for target in manifest["targets"]:
        if target["status"] == "pending":
            target["status"] = "accepted"
    with TestClient(app) as client:
        put = client.put(f"/api/sessions/{session['session_id']}/manifest", json=manifest)
        assert put.status_code == 200, put.text
        export = client.post(f"/api/sessions/{session['session_id']}/export",
                             json={"values": {"F6-05": "Compat Check"}})
        assert export.status_code == 200, export.text
        pdf = client.get(export.json()["download_url"])
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF")
        return pdf.content, len(session["pages"])


def test_exported_pdf_reopens_under_pypdf_strict_reading():
    content, page_count = _exported_pdf_bytes()
    import io
    reader = PdfReader(io.BytesIO(content), strict=True)
    assert len(reader.pages) == page_count


def test_exported_pdf_reopens_and_renders_under_pymupdf():
    content, page_count = _exported_pdf_bytes()
    with fitz.open(stream=content, filetype="pdf") as document:
        assert len(document) == page_count
        rendered = document[0].get_pixmap(matrix=fitz.Matrix(1.0, 1.0), alpha=False)
        assert rendered.width > 0 and rendered.height > 0


def test_exported_pdf_passes_qpdf_structural_check_when_available():
    qpdf = shutil.which("qpdf")
    if not qpdf:
        import pytest
        pytest.skip("qpdf not installed")
    content, _ = _exported_pdf_bytes()
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(content)
        handle.flush()
        completed = subprocess.run([qpdf, "--check", handle.name],
                                   capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
