"""Fail-closed policy for turning reviewed label records into model input.

The generated ``trainable.jsonl`` file is a cache, not an authority.  This
module validates both the source records and the receipt that describes the
cache, so every training entry point shares one policy boundary.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class LabelPolicyError(ValueError):
    """Raised when label data cannot prove that it is safe to train on."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    ).encode("utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise LabelPolicyError(f"missing label file: {path}")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LabelPolicyError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise LabelPolicyError(f"label row at {path}:{line_number} is not an object")
        records.append(value)
    return records


def _project_root(label_root: Path) -> Path:
    return label_root.resolve().parents[1]


def _manifest_path(record: dict[str, Any], label_root: Path) -> Path | None:
    reference = record.get("annotation", {}).get("target_manifest")
    if not reference or reference == "external-sibling-manifest":
        return None
    root = _project_root(label_root)
    candidate = (root / str(reference)).resolve()
    if not candidate.is_relative_to(root):
        raise LabelPolicyError(f"manifest escapes project root: {reference}")
    return candidate


def _manifest_source_hash(manifest: dict[str, Any]) -> str | None:
    return manifest.get("source_sha256") or manifest.get("sourceSha256")


def _manifest_targets(manifest: dict[str, Any]) -> list[Any] | None:
    if isinstance(manifest.get("targets"), list):
        return manifest["targets"]
    if isinstance(manifest.get("cases"), list):
        return manifest["cases"]
    return None


def _record_errors(record: dict[str, Any], label_root: Path, *, include_proxy: bool) -> list[str]:
    errors: list[str] = []
    record_id = record.get("id", "<missing-id>")
    required = {"id", "family_id", "source", "provenance", "annotation", "split"}
    errors.extend(f"missing record key {key}" for key in sorted(required - record.keys()))
    if errors:
        return errors

    source = record["source"]
    provenance = record["provenance"]
    annotation = record["annotation"]
    split = record["split"]
    for key in ("sha256", "locator_kind", "privacy_class"):
        if not source.get(key):
            errors.append(f"missing source.{key}")
    for key in ("source_kind", "lineage", "license"):
        if not provenance.get(key):
            errors.append(f"missing provenance.{key}")
    if not record["family_id"]:
        errors.append("family_id must be non-empty")

    status = annotation.get("status")
    role = split.get("role")
    allowed_statuses = {"verified"} | ({"proxy"} if include_proxy else set())
    if status not in allowed_statuses:
        errors.append(f"status {status!r} is not allowed by this training mode")
    if role != "development":
        errors.append(f"split role {role!r} is not trainable; only development is allowed")

    license_name = str(provenance.get("license", "")).strip().lower()
    if not license_name or license_name.startswith("not-") or license_name.startswith("inherited-"):
        errors.append("license is missing, unrecorded, or inherited without adoption approval")

    if status == "proxy":
        if not include_proxy:
            errors.append("proxy labels require explicit development opt-in")
        if source.get("privacy_class") != "controlled":
            errors.append("proxy labels must be controlled")
        if license_name != "project-authored":
            errors.append("proxy labels must be project-authored")
    elif status == "verified":
        if not isinstance(annotation.get("reviewer"), str) or not annotation["reviewer"].strip():
            errors.append("verified labels require annotation.reviewer")
        if not isinstance(annotation.get("verified_at"), str) or not annotation["verified_at"].strip():
            errors.append("verified labels require annotation.verified_at")
        receipt = annotation.get("review_receipt")
        if not receipt:
            errors.append("verified labels require annotation.review_receipt")
        elif not isinstance(receipt, dict):
            errors.append("annotation.review_receipt must be an object")
        else:
            if not str(receipt.get("receipt_sha256", "")).strip():
                errors.append("verified labels require review_receipt.receipt_sha256")
            receipt_reviewer = str(receipt.get("reviewer", "")).strip()
            annotation_reviewer = str(annotation.get("reviewer", "")).strip()
            if not receipt_reviewer:
                errors.append("verified labels require review_receipt.reviewer")
            elif receipt_reviewer != annotation_reviewer:
                errors.append("review_receipt.reviewer must match annotation.reviewer")
        approval = provenance.get("training_approval")
        if not isinstance(approval, dict) or approval.get("status") != "approved":
            errors.append("verified labels require provenance.training_approval.status=approved")

    manifest = _manifest_path(record, label_root)
    if manifest is None:
        errors.append("field-level target manifest is required")
    elif not manifest.is_file():
        errors.append(f"target manifest does not exist: {manifest}")
    else:
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"target manifest is invalid JSON: {exc}")
        else:
            if not isinstance(payload, dict):
                errors.append("target manifest must be an object")
            else:
                manifest_hash = _manifest_source_hash(payload)
                if manifest_hash and manifest_hash != source.get("sha256"):
                    errors.append("target manifest source hash does not match record source hash")
                targets = _manifest_targets(payload)
                if targets is None:
                    errors.append("target manifest has no targets or cases list")
                elif not targets:
                    errors.append("target manifest has no field-level targets")
                elif len({str(item.get("id")) for item in targets if isinstance(item, dict)}) != len(targets):
                    errors.append("target manifest has duplicate or malformed target ids")
                if status == "verified" and payload.get("status") not in {"verified", "gold-authored"}:
                    errors.append("verified record requires a verified annotation manifest")

    return [f"{record_id}: {error}" for error in errors]


def validate_trainable_records(
    records: list[dict[str, Any]], label_root: Path, *, include_proxy: bool = False
) -> None:
    errors: list[str] = []
    ids: set[str] = set()
    family_roles: dict[str, str] = {}
    for record in records:
        record_id = record.get("id")
        if record_id in ids:
            errors.append(f"duplicate record id: {record_id}")
        ids.add(str(record_id))
        errors.extend(_record_errors(record, label_root, include_proxy=include_proxy))
        family_id = record.get("family_id")
        role = record.get("split", {}).get("role")
        if family_id and family_id in family_roles and family_roles[family_id] != role:
            errors.append(f"family {family_id} crosses split roles")
        elif family_id:
            family_roles[family_id] = role
    if errors:
        raise LabelPolicyError("\n".join(errors))


def training_examples_from_records(
    records: list[dict[str, Any]], label_root: Path
) -> list[dict[str, Any]]:
    """Expand governed label records into the model's feature-record contract."""
    examples: list[dict[str, Any]] = []
    for record in records:
        manifest = _manifest_path(record, label_root)
        if manifest is None:
            raise LabelPolicyError(f"{record.get('id')}: cannot expand without a manifest")
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        targets = _manifest_targets(payload) or []
        page_sizes = record.get("source", {}).get("page_sizes", [])
        for index, target in enumerate(targets):
            if not isinstance(target, dict):
                raise LabelPolicyError(f"{record.get('id')}: target {index} is not an object")
            raw_bbox = target.get("target") or target.get("bbox")
            if not isinstance(raw_bbox, dict):
                raise LabelPolicyError(f"{record.get('id')}: target {index} has no bbox")
            try:
                bbox = [
                    float(raw_bbox["x"]), float(raw_bbox["y"]),
                    float(raw_bbox["width"]), float(raw_bbox["height"]),
                ]
            except (KeyError, TypeError, ValueError) as exc:
                raise LabelPolicyError(f"{record.get('id')}: target {index} has invalid bbox") from exc
            page_index = target.get("pageIndex")
            if page_index is None:
                page_index = max(0, int(target.get("page", 1)) - 1)
            page_index = int(page_index)
            size = page_sizes[page_index] if page_index < len(page_sizes) else {}
            class_name = str(target.get("requiredFieldType") or target.get("class", "")).lower()
            is_negative = bool(target.get("hardNegative")) or target.get("expected") in {"absent", "negative"}
            kind = "negative" if is_negative else {
                "checkbox": "choice",
                "radio": "choice",
                "composite": "composite",
            }.get(class_name, class_name)
            if kind not in {"text", "textarea", "date", "number", "identifier", "choice", "image", "signature", "composite", "negative"}:
                raise LabelPolicyError(f"{record.get('id')}: unsupported target class {class_name!r}")
            examples.append({
                "source": f"label:{record['id']}",
                "record_id": record["id"],
                "group": record["family_id"],
                "label": str(target.get("expectedLabel") or target.get("label", "")),
                "kind": kind,
                "bbox": bbox,
                "page_width": float(size.get("width", 1)),
                "page_height": float(size.get("height", 1)),
                "supervision": "verified-label" if record["annotation"]["status"] == "verified" else "proxy-label",
            })
    return examples


def load_trainable_examples(
    label_root: Path, *, include_proxy: bool = False
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load, validate, and expand the receipt-bound view for a trainer."""
    records, receipt = load_trainable_records(label_root, include_proxy=include_proxy)
    examples = training_examples_from_records(records, label_root)
    if not examples:
        raise LabelPolicyError("trainable label view contains no field-level examples")
    return examples, receipt


def load_trainable_records(label_root: Path, *, include_proxy: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load a receipt-bound trainable view and validate it again at consumption."""
    label_root = label_root.resolve()
    view_path = label_root / "trainable.jsonl"
    receipt_path = label_root / "trainable-receipt.json"
    if not receipt_path.is_file():
        raise LabelPolicyError(f"missing trainable receipt: {receipt_path}")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LabelPolicyError(f"invalid trainable receipt: {exc}") from exc
    policy = receipt.get("policy", {})
    if policy.get("include_proxy") is not include_proxy:
        raise LabelPolicyError("trainable receipt mode does not match requested training mode")
    if policy.get("allowed_split_roles") != ["development"]:
        raise LabelPolicyError("trainable receipt does not declare the fail-closed development-only policy")

    records_path = label_root / "records.jsonl"
    source_hash = _sha256_bytes(records_path.read_bytes()) if records_path.is_file() else None
    if source_hash != receipt.get("source_records_sha256"):
        raise LabelPolicyError("trainable view is stale: records.jsonl hash differs from its receipt")
    records = read_jsonl(view_path)
    if _sha256_bytes(_jsonl_bytes(records)) != receipt.get("view_sha256"):
        raise LabelPolicyError("trainable view is stale: trainable.jsonl hash differs from its receipt")
    if [record.get("id") for record in records] != receipt.get("eligible_record_ids", []):
        raise LabelPolicyError("trainable view ids differ from its receipt")
    validate_trainable_records(records, label_root, include_proxy=include_proxy)
    return records, receipt
