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
