import pytest

from pdf_field_lab.manifest import ManifestValidationError, create_manifest, validate_manifest
from pdf_field_lab.models import BBox, FieldSpec


PAGE = [{"width": 200.0, "height": 300.0}]


def _target(status="pending"):
    return {
        "id": "field-1", "page": 1, "label": "Name", "kind": "text",
        "bbox": {"x": 20, "y": 30, "width": 80, "height": 18},
        "editable_strategy": "acroform-text", "status": status,
    }


def test_manifest_preserves_rejected_target_but_excludes_it_from_export():
    manifest = validate_manifest({"revision": 0, "targets": [_target("rejected")]}, PAGE)
    assert manifest.targets[0]["status"] == "rejected"
    assert manifest.active_targets == []
    assert manifest.field_specs() == []


def test_manifest_rejects_duplicate_and_non_finite_geometry():
    with pytest.raises(ManifestValidationError, match="unique"):
        validate_manifest({"revision": 0, "targets": [_target(), _target()]}, PAGE)
    bad = _target()
    bad["bbox"]["x"] = "nan"
    with pytest.raises(ManifestValidationError, match="finite"):
        validate_manifest({"revision": 0, "targets": [bad]}, PAGE)


def test_manifest_created_from_field_specs_starts_pending_when_review_required():
    field = FieldSpec("manual", 1, "Name", "text", BBox(10, 10, 40, 12), "acroform-text")
    manifest = create_manifest([field])
    assert manifest.revision == 0
    assert manifest.targets[0]["status"] == "pending"
