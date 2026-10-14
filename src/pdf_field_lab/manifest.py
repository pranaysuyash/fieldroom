"""Canonical mutable review manifest for browser editing.

Detection produces evidence. The review manifest owns the user-corrected target
set that is persisted and consumed by export. Keeping this boundary explicit
prevents browser-only edits from disappearing at the export boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import BBox, Evidence, FieldSpec


MANIFEST_SCHEMA = "pdf-form-field-lab.review-manifest.v1"
TARGET_STATUSES = {"pending", "accepted", "rejected"}
FIELD_KINDS = {"text", "textarea", "date", "choice", "image", "signature", "composite"}
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ManifestValidationError(ValueError):
    """A client-supplied manifest violates the editable target contract."""


@dataclass
class ReviewManifest:
    revision: int
    targets: list[dict[str, Any]]

    @property
    def active_targets(self) -> list[dict[str, Any]]:
        return [target for target in self.targets if target["status"] != "rejected"]

    @property
    def pending_count(self) -> int:
        return sum(target["status"] == "pending" for target in self.active_targets)

    def field_specs(self) -> list[FieldSpec]:
        return [_field_from_target(target) for target in self.active_targets]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": MANIFEST_SCHEMA,
            "revision": self.revision,
            "targets": self.targets,
            "pending_count": self.pending_count,
        }


def _field_from_target(target: dict[str, Any]) -> FieldSpec:
    bbox = target["bbox"]
    evidence = [Evidence(
        source=item["source"], score=float(item["score"]),
        detail=str(item["detail"]), observed=bool(item.get("observed", True)),
    ) for item in target.get("evidence", [])]
    return FieldSpec(
        id=target["id"], page=target["page"], label=target["label"],
        kind=target["kind"], bbox=BBox(**bbox),
        editable_strategy=target.get("editable_strategy", "acroform-text"),
        review_required=target.get("status") != "accepted",
        required=bool(target.get("required", False)),
        conditional_on=target.get("conditional_on"),
        options=target.get("options", []), evidence=evidence,
        confidence=float(target.get("confidence", 0.0)),
        notes=target.get("notes", []), input_mode=target.get("input_mode", "single"),
        max_length=target.get("max_length"),
        label_entities=target.get("label_entities", []),
        grid_rows=target.get("grid_rows", []),
    )


def _normal_number(value: Any, *, name: str, minimum: float | None = None) -> float:
    if isinstance(value, bool):
        raise ManifestValidationError(f"{name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ManifestValidationError(f"{name} must be a number") from exc
    if number != number or number in {float("inf"), float("-inf")}:
        raise ManifestValidationError(f"{name} must be finite")
    if minimum is not None and number < minimum:
        raise ManifestValidationError(f"{name} must be at least {minimum:g}")
    return round(number, 3)


def _normalize_target(raw: Any, page_sizes: list[dict[str, float]]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ManifestValidationError("each target must be an object")
    target_id = str(raw.get("id", ""))
    if not _ID_PATTERN.fullmatch(target_id):
        raise ManifestValidationError("target IDs must be safe, non-empty identifiers")
    try:
        page = int(raw.get("page"))
    except (TypeError, ValueError) as exc:
        raise ManifestValidationError(f"target {target_id} has an invalid page") from exc
    if page < 1 or page > len(page_sizes):
        raise ManifestValidationError(f"target {target_id} is outside the document pages")
    kind = raw.get("kind")
    if kind not in FIELD_KINDS:
        raise ManifestValidationError(f"target {target_id} has an unsupported type")
    status = raw.get("status", "pending")
    if status not in TARGET_STATUSES:
        raise ManifestValidationError(f"target {target_id} has an unsupported review status")
    label = str(raw.get("label", "")).strip()
    if not label or len(label) > 240:
        raise ManifestValidationError(f"target {target_id} needs a label of 1-240 characters")
    raw_box = raw.get("bbox")
    if not isinstance(raw_box, dict):
        raise ManifestValidationError(f"target {target_id} needs a bounding box")
    box = {key: _normal_number(raw_box.get(key), name=f"{target_id}.{key}", minimum=0)
           for key in ("x", "y")}
    box.update({key: _normal_number(raw_box.get(key), name=f"{target_id}.{key}", minimum=4)
                for key in ("width", "height")})
    page_size = page_sizes[page - 1]
    if box["x"] + box["width"] > page_size["width"] + 0.5:
        raise ManifestValidationError(f"target {target_id} extends beyond the page width")
    if box["y"] + box["height"] > page_size["height"] + 0.5:
        raise ManifestValidationError(f"target {target_id} extends beyond the page height")
    evidence = raw.get("evidence", [])
    if not isinstance(evidence, list):
        raise ManifestValidationError(f"target {target_id} evidence must be a list")
    normalized_evidence = []
    for item in evidence[:8]:
        if not isinstance(item, dict):
            continue
        normalized_evidence.append({
            "source": str(item.get("source", "manual")),
            "score": max(0.0, min(1.0, float(item.get("score", 0.0)))),
            "detail": str(item.get("detail", ""))[:500],
            "observed": bool(item.get("observed", True)),
        })
    if not normalized_evidence:
        normalized_evidence = [{"source": "manual", "score": 1.0,
                                "detail": "Target added or corrected during review",
                                "observed": True}]
    raw_grid_rows = raw.get("grid_rows", [])
    if not isinstance(raw_grid_rows, list):
        raise ManifestValidationError(f"target {target_id} grid_rows must be a list")
    normalized_grid_rows = []
    for row_index, row in enumerate(raw_grid_rows[:16]):
        if not isinstance(row, dict) or not isinstance(row.get("bbox"), dict):
            raise ManifestValidationError(f"target {target_id} grid row {row_index} is invalid")
        try:
            cell_count = int(row.get("cell_count"))
        except (TypeError, ValueError) as exc:
            raise ManifestValidationError(f"target {target_id} grid row {row_index} has an invalid cell count") from exc
        if cell_count < 1 or cell_count > 100:
            raise ManifestValidationError(f"target {target_id} grid row {row_index} has an invalid cell count")
        row_box = row["bbox"]
        row_normalized = {
            "x": _normal_number(row_box.get("x"), name=f"{target_id}.grid_rows[{row_index}].x", minimum=0),
            "y": _normal_number(row_box.get("y"), name=f"{target_id}.grid_rows[{row_index}].y", minimum=0),
            "width": _normal_number(row_box.get("width"), name=f"{target_id}.grid_rows[{row_index}].width", minimum=4),
            "height": _normal_number(row_box.get("height"), name=f"{target_id}.grid_rows[{row_index}].height", minimum=4),
        }
        if (row_normalized["x"] + row_normalized["width"] > page_size["width"] + 0.5
                or row_normalized["y"] + row_normalized["height"] > page_size["height"] + 0.5):
            raise ManifestValidationError(f"target {target_id} grid row {row_index} extends beyond the page")
        if (row_normalized["x"] < box["x"] - 0.5
                or row_normalized["y"] < box["y"] - 0.5
                or row_normalized["x"] + row_normalized["width"] > box["x"] + box["width"] + 0.5
                or row_normalized["y"] + row_normalized["height"] > box["y"] + box["height"] + 0.5):
            raise ManifestValidationError(f"target {target_id} grid row {row_index} is outside its target")
        normalized_grid_rows.append({"bbox": row_normalized, "cell_count": cell_count})
    return {
        "id": target_id, "page": page, "label": label, "kind": kind,
        "component": raw.get("component"), "bbox": box,
        "editable_strategy": str(raw.get("editable_strategy", "acroform-text")),
        "status": status, "required": bool(raw.get("required", False)),
        "conditional_on": raw.get("conditional_on"),
        "options": raw.get("options", []) if isinstance(raw.get("options", []), list) else [],
        "evidence": normalized_evidence,
        "confidence": max(0.0, min(1.0, float(raw.get("confidence", 0.0)))),
        "notes": [str(note)[:500] for note in raw.get("notes", [])[:8]]
        if isinstance(raw.get("notes", []), list) else [],
        "input_mode": str(raw.get("input_mode", "single")),
        "max_length": raw.get("max_length"),
        "label_entities": raw.get("label_entities", []) if isinstance(raw.get("label_entities", []), list) else [],
        "grid_rows": normalized_grid_rows,
    }


def create_manifest(fields: list[FieldSpec]) -> ReviewManifest:
    targets = []
    for field in fields:
        target = field.as_dict()
        target["status"] = "pending" if field.review_required else "accepted"
        targets.append(target)
    return ReviewManifest(revision=0, targets=targets)


def validate_manifest(payload: Any, page_sizes: list[dict[str, float]], *, max_targets: int = 1000) -> ReviewManifest:
    if not isinstance(payload, dict):
        raise ManifestValidationError("manifest must be an object")
    try:
        revision = int(payload.get("revision"))
    except (TypeError, ValueError) as exc:
        raise ManifestValidationError("manifest revision must be an integer") from exc
    if revision < 0:
        raise ManifestValidationError("manifest revision cannot be negative")
    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, list) or len(raw_targets) > max_targets:
        raise ManifestValidationError(f"manifest targets must be a list of at most {max_targets} items")
    targets = [_normalize_target(raw, page_sizes) for raw in raw_targets]
    ids = [target["id"] for target in targets]
    if len(ids) != len(set(ids)):
        raise ManifestValidationError("manifest target IDs must be unique")
    return ReviewManifest(revision=revision, targets=targets)
