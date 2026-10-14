from pathlib import Path

from pdf_field_lab.profiles.form6 import FORM6_SHA256, form6_fields, matches_form6
from pdf_field_lab.models import BBox, FieldSpec


FIXTURE = Path(__file__).parents[1] / "data" / "samples" / "RAr0Lq2Avu.pdf"


def test_form6_profile_has_all_reviewed_targets():
    fields = form6_fields()
    assert len(fields) == 33
    assert [field.id for field in fields] == [f"F6-{i:02d}" for i in range(1, 34)]
    assert all(field.review_required for field in fields)


def test_field_kind_has_a_stable_browser_component():
    expected = {
        "text": "text-field",
        "date": "date-field",
        "choice": "choice-group",
        "image": "photo-dropzone",
        "signature": "signature-pad",
        "composite": "composite-field",
    }
    for kind, component in expected.items():
        target = FieldSpec("test", 1, "Test", kind, BBox(0, 0, 10, 10), "overlay")
        assert target.component == component


def test_form6_fingerprint_matches_fixture():
    assert matches_form6(FIXTURE)
    assert len(FORM6_SHA256) == 64
