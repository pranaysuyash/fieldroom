from pathlib import Path

import fitz
from reportlab.pdfgen import canvas

from pdf_field_lab.raster_cv import detect_raster_targets
from pdf_field_lab.raster_cv import run_cv_probe


FIXTURE = Path(__file__).parents[1] / "data" / "samples" / "RAr0Lq2Avu.pdf"


def test_opencv_probe_runs_against_fixture():
    result = run_cv_probe(FIXTURE, dpi=72)
    assert len(result["pages"]) == 2
    assert all(page["contours"] > 0 for page in result["pages"])


def test_image_only_calibration_recovers_raster_controls_and_whitespace(tmp_path):
    source = tmp_path / "vector-source.pdf"
    drawing = canvas.Canvas(str(source), pagesize=(612, 792))
    drawing.setFont("Helvetica", 12)
    drawing.drawString(72, 748, "Applicant Name:")
    drawing.rect(180, 700, 300, 32)
    drawing.drawString(72, 630, "Agree to terms:")
    drawing.rect(72, 600, 16, 16)
    drawing.drawString(72, 540, "Date:")
    drawing.line(180, 520, 320, 520)
    drawing.drawString(72, 450, "Address:")
    drawing.save()

    image_only = tmp_path / "image-only.pdf"
    source_document = fitz.open(str(source))
    try:
        pixmap = source_document[0].get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
        flattened = fitz.open()
        try:
            page = flattened.new_page(width=612, height=792)
            page.insert_image(page.rect, stream=pixmap.tobytes("png"))
            flattened.save(str(image_only))
        finally:
            flattened.close()
    finally:
        source_document.close()

    targets = detect_raster_targets(Path(image_only), dpi=120, max_per_page=20)

    assert len(targets) == 4
    assert {(target.kind, target.label) for target in targets} == {
        ("text", "Applicant Name:"),
        ("choice", "Agree to terms:"),
        ("date", "Date:"),
        ("text", "Address:"),
    }
    assert all(target.review_required for target in targets)


def test_raster_line_geometry_survives_thin_signature_rendering(tmp_path):
    source = tmp_path / "signature-source.pdf"
    drawing = canvas.Canvas(str(source), pagesize=(612, 792))
    drawing.setFont("Helvetica", 12)
    drawing.drawString(72, 470, "Authorized signature:")
    drawing.line(72, 440, 402, 440)
    drawing.save()

    image_only = tmp_path / "signature-image-only.pdf"
    source_document = fitz.open(str(source))
    try:
        pixmap = source_document[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        flattened = fitz.open()
        try:
            page = flattened.new_page(width=612, height=792)
            page.insert_image(page.rect, stream=pixmap.tobytes("png"))
            flattened.save(str(image_only))
        finally:
            flattened.close()
    finally:
        source_document.close()

    targets = detect_raster_targets(image_only, dpi=150, max_per_page=20)

    assert any(target.kind == "signature" and target.bbox.width >= 300
               for target in targets)
