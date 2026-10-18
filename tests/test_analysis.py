from pathlib import Path

from pdf_field_lab import analysis
from pdf_field_lab.models import BBox, Evidence, FieldSpec, PdfInspection


def _target(identifier: str, page: int, x: float, y: float, source: str) -> FieldSpec:
    return FieldSpec(
        id=identifier,
        page=page,
        label=identifier,
        kind="text",
        bbox=BBox(x, y, 80, 20),
        editable_strategy="acroform-text",
        confidence=0.9,
        evidence=[Evidence(source, 0.9, "test evidence")],
    )


def test_analysis_merges_mixed_representation_pages(monkeypatch, tmp_path):
    source = Path(tmp_path) / "mixed.pdf"
    source.write_bytes(b"placeholder")
    inspection = PdfInspection(
        path=str(source),
        sha256="test-sha",
        pages=3,
        page_sizes=[{"width": 612.0, "height": 792.0}] * 3,
        metadata={},
        native_fields=[{"name": "native-page-1"}],
        annotations=[],
        text_chars_by_page=[500, 50, 50],
    )
    native = [_target("native-page-1", 1, 40, 40, "native")]
    generic = [
        _target("duplicate-inferred-page-1", 1, 40, 40, "vector"),
        _target("vector-page-2", 2, 40, 40, "vector"),
    ]
    raster = [_target("raster-page-3", 3, 40, 40, "raster_cv")]
    monkeypatch.setattr(analysis, "inspect_pdf", lambda path: inspection)
    monkeypatch.setattr(analysis, "detect_vector_candidates", lambda path: [])
    monkeypatch.setattr(analysis, "detect_semantic_targets", lambda path, model=None: generic)
    monkeypatch.setattr(analysis, "detect_native_targets", lambda inspected: native)
    monkeypatch.setattr(analysis, "matches_form6", lambda path: False)
    monkeypatch.setattr(analysis, "detect_signature_observations", lambda path: [])
    monkeypatch.setattr(
        "pdf_field_lab.raster_cv.detect_raster_targets",
        lambda path: raster,
    )

    report = analysis.analyze(source)

    assert [field.id for field in report.logical_fields] == [
        "native-page-1",
        "vector-page-2",
        "raster-page-3",
    ]
    assert report.backend_status["raster_semantic_detection"] == "executed"
    assert any("merged per page" in warning for warning in report.warnings)


def test_analysis_real_multi_page_mixed_pdf_routes_raster_to_text_poor_pages_only(tmp_path):
    import fitz
    from reportlab.pdfgen import canvas

    # Build a real 3-page mixed-representation PDF:
    # Page 1: text-rich page (>= 100 chars) with a native AcroForm widget + overlapping vector box + non-overlapping vector box
    # Page 2: text-rich flat vector page (>= 100 chars) with a vector field
    # Page 3: image-only scanned page (0 text chars) with a scanned field box
    vector_pdf = tmp_path / "pages-1-2.pdf"
    drawing = canvas.Canvas(str(vector_pdf), pagesize=(612, 792))
    drawing.setFont("Helvetica", 11)
    drawing.drawString(
        72, 755,
        "Section 1 Instructions: Complete applicant identity details below carefully before proceeding to page two.",
    )
    drawing.drawString(72, 708, "Applicant Name:")
    drawing.rect(180, 696, 260, 26)
    drawing.acroForm.textfield(
        name="native_applicant_name",
        x=180,
        y=696,
        width=260,
        height=26,
        value="",
    )
    drawing.drawString(72, 648, "Email:")
    drawing.rect(180, 636, 260, 26)
    drawing.showPage()

    drawing.setFont("Helvetica", 11)
    drawing.drawString(
        72, 755,
        "Section 2 Instructions: Provide contact phone and residential address information on this vector form page.",
    )
    drawing.drawString(72, 708, "Mobile Number:")
    drawing.rect(180, 696, 260, 26)
    drawing.save()

    scan_source = tmp_path / "scan-page-source.pdf"
    scan_canvas = canvas.Canvas(str(scan_source), pagesize=(612, 792))
    scan_canvas.setFont("Helvetica", 12)
    scan_canvas.drawString(72, 748, "Account Number:")
    scan_canvas.rect(180, 700, 300, 32)
    scan_canvas.save()

    scan_doc = fitz.open(str(scan_source))
    try:
        scan_pix = scan_doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        scan_png = scan_pix.tobytes("png")
    finally:
        scan_doc.close()

    mixed_pdf = tmp_path / "real-mixed-3page.pdf"
    combined = fitz.open(str(vector_pdf))
    try:
        page3 = combined.new_page(width=612, height=792)
        page3.insert_image(page3.rect, stream=scan_png)
        combined.save(str(mixed_pdf))
    finally:
        combined.close()

    report = analysis.analyze(mixed_pdf)

    # Page 1 & 2 are text-rich (>= 100 chars), only Page 3 is text-poor (0 chars).
    assert report.backend_status["raster_routed_pages"] == "3"
    by_page = {1: [], 2: [], 3: []}
    for field in report.logical_fields:
        by_page[field.page].append(field)

    # Page 1 keeps native_applicant_name (suppressing overlapping vector box) AND keeps non-overlapping Email vector box.
    page1_ids = [f.id for f in by_page[1]]
    assert "native_applicant_name" in page1_ids
    assert any(f.label == "Email:" and f.review_required for f in by_page[1])
    assert len([f for f in by_page[1] if abs(f.bbox.y - (792 - 696 - 26)) < 6]) == 1

    # Page 2 recovers Mobile Number from generic vector lane.
    assert any("Mobile" in f.label for f in by_page[2])

    # Page 3 recovers Account Number from raster_cv lane.
    assert any(any(ev.source == "raster_cv" for ev in f.evidence) for f in by_page[3])


def test_semantic_detect_isolates_per_page_failure(tmp_path, monkeypatch):
    from reportlab.pdfgen import canvas
    from pdf_field_lab.semantic_detect import detect_semantic_targets

    pdf_path = tmp_path / "two-page-vector.pdf"
    drawing = canvas.Canvas(str(pdf_path), pagesize=(612, 792))
    drawing.setFont("Helvetica", 12)
    drawing.drawString(72, 708, "Applicant Name:")
    drawing.rect(180, 696, 240, 26)
    drawing.showPage()
    drawing.setFont("Helvetica", 12)
    drawing.drawString(72, 708, "Email:")
    drawing.rect(180, 696, 240, 26)
    drawing.save()

    import pdfplumber
    orig_open = pdfplumber.open

    class _FaultyPageWrapper:
        def __init__(self, real_pdf):
            self._real_pdf = real_pdf
            self.pages = [self._wrap(p, idx) for idx, p in enumerate(real_pdf.pages, 1)]

        def _wrap(self, page, idx):
            if idx == 1:
                class _BrokenPage:
                    def extract_words(self):
                        raise ValueError("corrupt font stream on page 1")
                return _BrokenPage()
            return page

        def __enter__(self):
            self._real_pdf.__enter__()
            return self

        def __exit__(self, *args):
            return self._real_pdf.__exit__(*args)

    monkeypatch.setattr(pdfplumber, "open", lambda p: _FaultyPageWrapper(orig_open(p)))
    warnings = []
    targets = detect_semantic_targets(pdf_path, warnings_out=warnings)
    assert any(t.page == 2 and t.label == "Email:" for t in targets)
    assert any("Semantic detection failed on page 1: ValueError" in w for w in warnings)

