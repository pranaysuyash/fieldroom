import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from evaluate_detector import (
    _duplicate_pairs,
    _is_match,
    _label_error_entry,
    _miss_diagnostics,
    _stable_assignment,
)

from pdf_field_lab.models import BBox, FieldSpec


def _spec(spec_id, label="Name", x=10.0, y=10.0):
    return FieldSpec(
        id=spec_id, page=1, label=label, kind="text",
        bbox=BBox(x, y, 100, 20), editable_strategy="acroform-text",
    )


def test_underline_tolerance_does_not_match_a_thick_box_at_the_same_boundary():
    case = {"class": "underline"}
    expected = BBox(72, 470, 468, 3)
    photo_box = FieldSpec(
        id="photo", page=1, label="Passport photo:", kind="image",
        bbox=BBox(380, 360, 140, 110), editable_strategy="visual-overlay-image",
    )

    assert not _is_match(case, expected, photo_box, threshold=0.25)


def test_overlapping_predictions_are_duplicates_even_when_kinds_differ():
    first = FieldSpec(id="first", page=1, label="Name", kind="text",
                      bbox=BBox(10, 10, 100, 24), editable_strategy="acroform-text")
    second = FieldSpec(id="second", page=1, label="Name", kind="textarea",
                       bbox=BBox(10, 10, 100, 24), editable_strategy="acroform-text")

    assert _duplicate_pairs([first, second]) == 1


def _contested_setup():
    """Two equal-geometry cases and two equal-geometry predictions: every
    candidate edge has identical IoU, so only a deterministic tie-break gives
    a stable assignment (the old per-case greedy relied on set order)."""
    cases = [
        {"id": "case-a", "pageIndex": 0, "class": "text", "expected": "detected",
         "target": {"x": 10, "y": 10, "width": 100, "height": 20}},
        {"id": "case-b", "pageIndex": 0, "class": "text", "expected": "detected",
         "target": {"x": 10, "y": 10, "width": 100, "height": 20}},
    ]
    # Page height 792 converts a label-space y of 10 to detector-space y of 762.
    predictions = [_spec("pred-1", y=762.0), _spec("pred-2", y=762.0)]
    return cases, predictions


def test_stable_assignment_ties_break_deterministically_and_order_invariantly():
    cases, predictions = _contested_setup()
    page_heights = [792.0]
    baseline = _stable_assignment(cases, predictions, page_heights, threshold=0.25)
    assert baseline["case-a"]["prediction_id"] == "pred-1"
    assert baseline["case-b"]["prediction_id"] == "pred-2"

    reversed_cases = list(reversed(cases))
    reversed_predictions = list(reversed(predictions))
    shuffled = _stable_assignment(reversed_cases, reversed_predictions, page_heights, threshold=0.25)
    assert {case_id: edge["prediction_id"] for case_id, edge in shuffled.items()} == {
        "case-a": "pred-1", "case-b": "pred-2",
    }


def test_stable_assignment_never_double_books_a_prediction():
    cases, predictions = _contested_setup()
    assignment = _stable_assignment(cases, predictions[:1], [792.0], threshold=0.25)
    used = [edge["prediction_id"] for edge in assignment.values()]
    assert len(used) == len(set(used))


def test_wrong_label_match_is_reported_as_its_own_failure_class():
    case = {"id": "case-a", "expectedLabel": "Full legal name"}
    edge = {"iou": 0.92, "prediction": _spec("pred-1", label="Total amount due")}
    entry = _label_error_entry(case, edge)
    assert entry == {
        "case_id": "case-a",
        "expected_label": "Full legal name",
        "predicted_id": "pred-1",
        "predicted_label": "Total amount due",
        "iou": 0.92,
    }
    assert _label_error_entry(case, {"iou": 0.9, "prediction": _spec("pred-1", label="Full Name")}) is None


def test_miss_diagnostics_expose_nearest_prediction_and_consumption():
    case = {"id": "case-a", "pageIndex": 0, "class": "text", "expected": "detected",
            "target": {"x": 10, "y": 10, "width": 100, "height": 20}}
    far_prediction = _spec("pred-9", label="Unrelated note", x=400.0, y=600.0)
    page_heights = [792.0]

    free = _miss_diagnostics(case, [far_prediction], page_heights, used_predictions=set())
    assert free["matched"] is False
    assert free["nearest_prediction"]["predicted_id"] == "pred-9"
    assert free["nearest_prediction"]["consumed_elsewhere"] is False

    consumed = _miss_diagnostics(case, [far_prediction], page_heights,
                                 used_predictions={"pred-9"})
    assert consumed["nearest_prediction"]["consumed_elsewhere"] is True

    empty = _miss_diagnostics(case, [], page_heights, used_predictions=set())
    assert empty == {"id": "case-a", "matched": False, "iou": 0.0}
