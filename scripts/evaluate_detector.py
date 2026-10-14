"""Evaluate semantic detector output against a reviewed PDF label manifest.

The evaluator is deliberately separate from detection. It consumes reviewed
regions, converts their lower-left coordinates to the detector's top-origin
coordinate space, and reports recall, hard-negative false positives, type
accuracy, label association, and duplicate control.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import fitz

from pdf_field_lab.models import BBox, FieldSpec
from pdf_field_lab.raster_cv import detect_raster_targets
from pdf_field_lab.semantic_detect import detect_semantic_targets


def _iou(first: BBox, second: BBox) -> float:
    x0 = max(first.x, second.x)
    y0 = max(first.y, second.y)
    x1 = min(first.x + first.width, second.x + second.width)
    y1 = min(first.y + first.height, second.y + second.height)
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = first.width * first.height + second.width * second.height - intersection
    return intersection / union if union else 0.0


def _horizontal_overlap(first: BBox, second: BBox) -> float:
    overlap = max(0.0, min(first.x + first.width, second.x + second.width)
                  - max(first.x, second.x))
    return overlap / min(first.width, second.width) if min(first.width, second.width) else 0.0


def _label_similarity(expected: str, predicted: str) -> float:
    """Compare reviewed and predicted labels without requiring punctuation equality."""
    expected_tokens = set("".join(character.lower() if character.isalnum() else " " for character in expected).split())
    predicted_tokens = set("".join(character.lower() if character.isalnum() else " " for character in predicted).split())
    if not expected_tokens or not predicted_tokens:
        return 0.0
    intersection = expected_tokens & predicted_tokens
    return len(intersection) / max(len(expected_tokens), len(predicted_tokens))


def _reviewed_bbox(case: dict[str, Any], page_height: float) -> BBox:
    target = case["target"]
    return BBox(float(target["x"]), page_height - float(target["y"]) - float(target["height"]),
                float(target["width"]), float(target["height"]))


def _is_match(case: dict[str, Any], expected: BBox, predicted: FieldSpec, threshold: float) -> bool:
    if _iou(expected, predicted.bbox) >= threshold:
        return True
    # A one-point underline is represented as a narrow review region by the
    # detector, while reviewed labels often cover the full writable height.
    # Match it by horizontal coverage and a small vertical boundary distance.
    if (case.get("class") == "underline"
            and predicted.bbox.height <= max(8.0, expected.height * 4)
            and _horizontal_overlap(expected, predicted.bbox) >= 0.7):
        expected_bottom = expected.y + expected.height
        predicted_bottom = predicted.bbox.y + predicted.bbox.height
        return min(abs(expected.y - predicted_bottom),
                   abs(predicted.bbox.y - expected_bottom)) <= 10
    return False


def _stable_assignment(
    positive_cases: list[dict[str, Any]],
    predictions: list[FieldSpec],
    page_heights: list[float],
    threshold: float,
) -> dict[str, dict[str, Any]]:
    """Assign predictions to positive cases with a stable matching policy.

    Greedy per-case iteration is order-sensitive: a wrong label or an
    overlapping near-duplicate can steal a match depending on manifest order.
    This policy sorts all geometric candidate edges globally by descending
    IoU with deterministic (case_id, prediction_id) tie-breaking, then takes
    greedily. For unique ids the assignment is invariant to input order, so
    localization recall is measured independently of manifest layout (FFL-EVL-005).
    Label and type agreement stay post-match metrics on purpose: they measure
    ontology correctness, not geometry.
    """
    edges: list[dict[str, Any]] = []
    for case in positive_cases:
        page_index = int(case["pageIndex"])
        expected = _reviewed_bbox(case, page_heights[page_index])
        for prediction in predictions:
            if prediction.page != page_index + 1:
                continue
            if not _is_match(case, expected, prediction, threshold):
                continue
            edges.append({
                "iou": _iou(expected, prediction.bbox),
                "case_id": str(case["id"]),
                "prediction_id": str(prediction.id),
                "prediction": prediction,
            })
    edges.sort(key=lambda edge: (-edge["iou"], edge["case_id"], edge["prediction_id"]))
    taken_cases: set[str] = set()
    used_predictions: set[str] = set()
    assignment: dict[str, dict[str, Any]] = {}
    for edge in edges:
        if edge["case_id"] in taken_cases or edge["prediction_id"] in used_predictions:
            continue
        taken_cases.add(edge["case_id"])
        used_predictions.add(edge["prediction_id"])
        assignment[edge["case_id"]] = edge
    return assignment


def _miss_diagnostics(case: dict[str, Any], predictions: list[FieldSpec],
                      page_heights: list[float], used_predictions: set[str]) -> dict[str, Any]:
    """Explain a miss: nearest same-page prediction, its label, and whether it
    was already consumed by another case (wrong-label counterexample evidence)."""
    page_index = int(case["pageIndex"])
    expected = _reviewed_bbox(case, page_heights[page_index])
    same_page = [prediction for prediction in predictions if prediction.page == page_index + 1]
    detail: dict[str, Any] = {"id": case["id"], "matched": False, "iou": 0.0}
    if not same_page:
        return detail
    nearest = max(same_page, key=lambda prediction: (_iou(expected, prediction.bbox), str(prediction.id)))
    detail["nearest_prediction"] = {
        "predicted_id": nearest.id,
        "iou": round(_iou(expected, nearest.bbox), 3),
        "label": nearest.label,
        "kind": nearest.kind,
        "consumed_elsewhere": str(nearest.id) in used_predictions,
    }
    return detail


def _label_error_entry(case: dict[str, Any], edge: dict[str, Any]) -> dict[str, Any] | None:
    """A matched positive with an unassociated label is a wrong-label
    counterexample: right region, wrong ontology. It must be visible as its
    own failure class, not silently absorbed into localization recall."""
    predicted = edge["prediction"]
    similarity = _label_similarity(case.get("expectedLabel", ""), predicted.label)
    if similarity >= 0.5:
        return None
    return {
        "case_id": case["id"],
        "expected_label": case.get("expectedLabel", ""),
        "predicted_id": predicted.id,
        "predicted_label": predicted.label,
        "iou": round(edge["iou"], 3),
    }


def _duplicate_pairs(predictions: list[FieldSpec]) -> int:
    return sum(
        1 for index, first in enumerate(predictions)
        for second in predictions[index + 1:]
        if first.page == second.page
        and _iou(first.bbox, second.bbox) >= 0.65
    )


def evaluate(pdf_path: Path, labels_path: Path, *, detector: str = "semantic") -> dict[str, Any]:
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    expected_sha = labels.get("sourceSha256")
    actual_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    if expected_sha and expected_sha != actual_sha:
        raise ValueError(f"label manifest hash does not match PDF: {pdf_path}")

    with fitz.open(str(pdf_path)) as document:
        page_heights = [float(page.rect.height) for page in document]
    if detector == "semantic":
        predictions = detect_semantic_targets(pdf_path)
    elif detector == "raster":
        predictions = detect_raster_targets(pdf_path)
    else:
        raise ValueError(f"unsupported detector: {detector}")
    cases = labels.get("cases", [])
    positive_cases = [case for case in cases
                      if not case.get("hardNegative")
                      and case.get("expected") == "detected"
                      and case.get("class") != "labelAssociation"]
    association_cases = [case for case in cases
                         if not case.get("hardNegative")
                         and case.get("expected") == "detected"
                         and case.get("class") == "labelAssociation"]
    negative_cases = [case for case in cases if case.get("hardNegative") and case.get("expected") == "abstain"]
    threshold = float(labels.get("policy", {}).get("positiveMatchIoU", 0.25))
    assignment = _stable_assignment(positive_cases, predictions, page_heights, threshold)
    used_predictions = {str(edge["prediction_id"]) for edge in assignment.values()}
    positive_matches: list[dict[str, Any]] = []
    label_errors: list[dict[str, Any]] = []
    for case in positive_cases:
        edge = assignment.get(str(case["id"]))
        if edge is None:
            positive_matches.append(
                _miss_diagnostics(case, predictions, page_heights, used_predictions))
            continue
        predicted = edge["prediction"]
        similarity = _label_similarity(case.get("expectedLabel", ""), predicted.label)
        positive_matches.append({
            "id": case["id"], "matched": True, "iou": round(edge["iou"], 3),
            "predicted_id": predicted.id, "predicted_kind": predicted.kind,
            "label": predicted.label,
            "label_similarity": round(similarity, 3),
            "label_associated": similarity >= 0.5,
        })
        error_entry = _label_error_entry(case, edge)
        if error_entry is not None:
            label_errors.append(error_entry)
    matched_count = sum(item["matched"] for item in positive_matches)

    negative_matches = []
    for case in negative_cases:
        page_index = int(case["pageIndex"])
        expected = _reviewed_bbox(case, page_heights[page_index])
        matched = [
            {"predicted_id": prediction.id, "iou": round(_iou(expected, prediction.bbox), 3),
             "label": prediction.label}
            for prediction in predictions
            if prediction.page == page_index + 1 and _is_match(case, expected, prediction, threshold)
        ]
        negative_matches.append({"id": case["id"], "false_positive": bool(matched), "matches": matched})

    association_matches = []
    for case in association_cases:
        page_index = int(case["pageIndex"])
        expected = _reviewed_bbox(case, page_heights[page_index])
        matches = [prediction for prediction in predictions
                   if prediction.page == page_index + 1
                   and _is_match(case, expected, prediction, threshold)]
        best = max(
            matches,
            key=lambda prediction: (
                _label_similarity(case.get("expectedLabel", ""), prediction.label),
                _iou(expected, prediction.bbox),
                str(prediction.id),
            ),
        ) if matches else None
        association_matches.append({
            "id": case["id"], "matched": bool(best),
            "label_associated": bool(
                best and _label_similarity(case.get("expectedLabel", ""), best.label) >= 0.5),
        })

    typed_cases = [item for item in positive_matches
                   if next((case for case in positive_cases if case["id"] == item["id"]), {}).get("requiredFieldType")]
    type_correct = 0
    for item in typed_cases:
        case = next(case for case in positive_cases if case["id"] == item["id"])
        type_correct += item.get("predicted_kind") == {"checkbox": "choice"}.get(case["requiredFieldType"], case["requiredFieldType"])
    return {
        "schema": "pdf-field-lab.detector-evaluation.v2",
        "pdf": str(pdf_path),
        "labels": str(labels_path),
        "detector": detector,
        "source_sha256": actual_sha,
        "policy": {"positive_match_iou": threshold},
        "prediction_count": len(predictions),
        "positive_cases": len(positive_cases),
        "positive_matches": matched_count,
        "positive_recall": round(matched_count / len(positive_cases), 3) if positive_cases else 1.0,
        "false_positive_predictions": len(predictions) - matched_count,
        "precision": round(matched_count / len(predictions), 3) if predictions else 1.0,
        "f1": round((2 * matched_count) / (len(predictions) + len(positive_cases)), 3)
        if predictions or positive_cases else 1.0,
        "hard_negative_cases": len(negative_cases),
        "hard_negative_false_positives": sum(item["false_positive"] for item in negative_matches),
        "hard_negative_false_positive_rate": round(sum(item["false_positive"] for item in negative_matches) / len(negative_cases), 3) if negative_cases else 0.0,
        "typed_cases": len(typed_cases),
        "type_correct": type_correct,
        "type_accuracy": round(type_correct / len(typed_cases), 3) if typed_cases else 1.0,
        "label_association_rate": round(sum(item.get("label_associated", False) for item in positive_matches) / len(positive_matches), 3) if positive_matches else 0.0,
        "label_error_count": len(label_errors),
        "label_error_rate": round(len(label_errors) / matched_count, 3) if matched_count else 0.0,
        "label_errors": label_errors,
        "association_cases": len(association_cases),
        "association_matches": sum(item["matched"] for item in association_matches),
        "association_recall": round(sum(item["matched"] for item in association_matches) / len(association_cases), 3) if association_cases else 1.0,
        "duplicate_pairs": _duplicate_pairs(predictions),
        "positive_details": positive_matches,
        "association_details": association_matches,
        "hard_negative_details": negative_matches,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--detector", choices=("semantic", "raster"), default="semantic")
    args = parser.parse_args()
    result = evaluate(args.pdf, args.labels, detector=args.detector)
    serialized = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")


if __name__ == "__main__":
    main()
