from pathlib import Path

from pdf_field_lab.analysis import analyze


FIXTURE = Path(__file__).parents[1] / "data" / "samples" / "RAr0Lq2Avu.pdf"


def test_flat_form_has_no_native_fields_and_profile_is_loaded():
    report = analyze(FIXTURE)
    assert report.input.pages == 2
    assert report.input.native_fields == []
    assert len(report.logical_fields) == 33
    assert report.input.text_chars_by_page[0] > 1000
    assert report.input.text_chars_by_page[1] > 1000


def test_vector_lane_produces_candidates_without_claiming_semantics():
    report = analyze(FIXTURE)
    assert report.vector_candidates
    assert all(candidate.review_required for candidate in report.vector_candidates)
    assert all(candidate.label == "unlabeled geometric candidate" for candidate in report.vector_candidates)


def test_profile_ids_are_unique_and_bounds_are_on_page():
    report = analyze(FIXTURE)
    for field in report.logical_fields:
        page = report.input.page_sizes[field.page - 1]
        assert 0 <= field.bbox.x < page["width"]
        assert 0 <= field.bbox.y < page["height"]
        assert field.bbox.x + field.bbox.width <= page["width"] + 1
        assert field.bbox.y + field.bbox.height <= page["height"] + 1
