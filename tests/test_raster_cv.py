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


def test_shaded_faint_and_skewed_scan_recovers_targets(tmp_path):
    import cv2
    import numpy as np

    source = tmp_path / "degraded-source.pdf"
    drawing = canvas.Canvas(str(source), pagesize=(612, 792))
    drawing.setFont("Helvetica", 12)
    drawing.setStrokeColorRGB(0.62, 0.62, 0.62)
    drawing.drawString(72, 748, "Applicant Name:")
    drawing.rect(180, 700, 300, 32)
    drawing.drawString(72, 630, "Agree to terms:")
    drawing.rect(72, 600, 16, 16)
    drawing.drawString(72, 540, "Date:")
    drawing.line(180, 520, 320, 520)
    drawing.save()

    source_doc = fitz.open(str(source))
    try:
        pix = source_doc[0].get_pixmap(matrix=fitz.Matrix(150 / 72.0, 150 / 72.0), alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n).copy()
    finally:
        source_doc.close()

    # Apply uneven scanner illumination gradient (drops background below 200 on one side)
    # and a 1.6-degree scanner skew.
    y_grad = np.linspace(0.76, 1.0, img.shape[0], dtype=np.float32)[:, None, None]
    x_grad = np.linspace(0.78, 1.0, img.shape[1], dtype=np.float32)[None, :, None]
    shaded = np.clip(img.astype(np.float32) * y_grad * x_grad, 0, 255).astype(np.uint8)
    center = (shaded.shape[1] * 0.5, shaded.shape[0] * 0.5)
    rot = cv2.getRotationMatrix2D(center, 1.6, 1.0)
    skewed = cv2.warpAffine(
        shaded,
        rot,
        (shaded.shape[1], shaded.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(210, 210, 210),
    )
    ok, png_bytes = cv2.imencode(".png", skewed)
    assert ok

    degraded_pdf = tmp_path / "degraded-scan.pdf"
    flattened = fitz.open()
    try:
        page = flattened.new_page(width=612, height=792)
        page.insert_image(page.rect, stream=png_bytes.tobytes())
        flattened.save(str(degraded_pdf))
    finally:
        flattened.close()

    targets = detect_raster_targets(degraded_pdf, dpi=150, max_per_page=20)
    kinds = {t.kind for t in targets}
    assert "text" in kinds
    assert "choice" in kinds or "date" in kinds
    assert len(targets) >= 3


def test_detect_raster_targets_page_filter_and_isolation(tmp_path, monkeypatch):
    import pdf_field_lab.raster_cv as rcv

    source = tmp_path / "two-page-scan.pdf"
    drawing = canvas.Canvas(str(source), pagesize=(612, 792))
    drawing.setFont("Helvetica", 12)
    drawing.drawString(72, 748, "Applicant Name:")
    drawing.rect(180, 700, 300, 32)
    drawing.showPage()
    drawing.setFont("Helvetica", 12)
    drawing.drawString(72, 748, "Email:")
    drawing.rect(180, 700, 300, 32)
    drawing.save()

    routed_targets = detect_raster_targets(source, dpi=120, pages={2})
    assert routed_targets
    assert all(target.page == 2 for target in routed_targets)

    orig_ocr = rcv._extract_ocr_words
    calls = []

    def flaky_ocr(image):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("synthetic OCR failure on page 1")
        return orig_ocr(image)

    monkeypatch.setattr(rcv, "_extract_ocr_words", flaky_ocr)
    warnings = []
    isolated_targets = detect_raster_targets(source, dpi=120, warnings_out=warnings)
    assert any(target.page == 2 for target in isolated_targets)
    assert any("Raster detection failed on page 1" in warning for warning in warnings)

