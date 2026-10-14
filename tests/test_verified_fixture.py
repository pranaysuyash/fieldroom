"""FFL-GOV-001: a sanitized verified-record fixture must be consumable in
default mode while records in non-development splits stay excluded, and the
review-receipt contract must be fail-closed.

The fixture is fully synthetic (tmp_path only): the committed default training
view must remain empty, and no real document bytes or identities are involved.
"""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from pdf_field_lab.label_policy import (
    LabelPolicyError,
    load_trainable_records,
    validate_trainable_records,
)

ROOT = Path(__file__).parents[1]
VIEW_SCRIPT = ROOT / "scripts" / "build_trainable_label_view.py"


def _view_module(monkeypatch, label_root):
    spec = importlib.util.spec_from_file_location("verified_fixture_view", VIEW_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "LABEL_ROOT", label_root)
    monkeypatch.setattr(module, "OUTPUT", label_root / "trainable.jsonl")
    monkeypatch.setattr(module, "RECEIPT", label_root / "trainable-receipt.json")
    return module


def _receipt_sha256(receipt: dict) -> str:
    payload = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_fixture(label_root: Path, *, reviewer: str = "pranay",
                   receipt=None, role: str = "development",
                   record_id: str = "fixture-verified-v1",
                   family_id: str = "fixture-verified-family") -> dict:
    project_root = label_root.parents[1]
    manifest_path = project_root / "artifacts" / "goldset" / "fixture-verified-labels.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    source_hash = "b" * 64
    manifest_path.write_text(json.dumps({
        "schema": "pdf-field-lab.gold-labels.v1",
        "status": "verified",
        "sourceSha256": source_hash,
        "cases": [{
            "id": "fixture.name", "pageIndex": 0, "class": "text",
            "expected": "detected",
            "target": {"x": 1, "y": 1, "width": 10, "height": 10},
        }],
    }), encoding="utf-8")
    if receipt is None:
        receipt = {
            "session_id": "fixture-session",
            "reviewer": reviewer,
            "recorded_at": "2026-10-09T12:00:00+00:00",
            "revision": 3,
            "manifest_sha256": "c" * 64,
            "source_sha256": source_hash,
            "event_count": 2,
            "candidates_sha256": "d" * 64,
        }
        receipt["receipt_sha256"] = _receipt_sha256(receipt)
    record = {
        "id": record_id,
        "family_id": family_id,
        "source": {
            "sha256": source_hash,
            "locator_kind": "project-artifact",
            "locator": "artifacts/goldset/fixture.pdf",
            "privacy_class": "controlled",
            "page_count": 1,
            "page_sizes": [{"width": 612.0, "height": 792.0}],
        },
        "provenance": {
            "source_kind": "synthetic-verified-fixture",
            "lineage": "pytest verified fixture (sanitized, synthetic geometry)",
            "license": "project-authored",
            "training_approval": {"status": "approved", "approver": "pranay"},
        },
        "annotation": {
            "status": "verified",
            "reviewer": reviewer,
            "verified_at": "2026-10-09T12:00:00+00:00",
            "review_receipt": receipt,
            "target_manifest": "artifacts/goldset/fixture-verified-labels.json",
        },
        "split": {"role": role},
    }
    records_path = label_root / "records.jsonl"
    existing = records_path.read_text(encoding="utf-8") if records_path.exists() else ""
    records_path.write_text(existing + json.dumps(record) + "\n", encoding="utf-8")
    return record


def test_default_mode_consumes_sanitized_verified_fixture(tmp_path, monkeypatch):
    label_root = tmp_path / "data" / "labels"
    label_root.mkdir(parents=True)
    _write_fixture(label_root)
    module = _view_module(monkeypatch, label_root)

    receipt = module.build(include_proxy=False)
    assert receipt["eligible_records"] == 1
    assert receipt["eligible_record_ids"] == ["fixture-verified-v1"]
    assert receipt["policy"]["include_proxy"] is False

    records, view_receipt = load_trainable_records(label_root, include_proxy=False)
    assert [record["id"] for record in records] == ["fixture-verified-v1"]
    assert view_receipt["view_sha256"] == receipt["view_sha256"]


def test_verified_record_without_review_receipt_is_rejected(tmp_path, monkeypatch):
    label_root = tmp_path / "data" / "labels"
    label_root.mkdir(parents=True)
    _write_fixture(label_root, receipt={})
    module = _view_module(monkeypatch, label_root)

    with pytest.raises(LabelPolicyError, match="review_receipt"):
        module.build(include_proxy=False)


def test_receipt_reviewer_must_match_annotation_reviewer(tmp_path, monkeypatch):
    label_root = tmp_path / "data" / "labels"
    label_root.mkdir(parents=True)
    _write_fixture(label_root, reviewer="pranay",
                   receipt={"reviewer": "someone-else", "receipt_sha256": "e" * 64})
    module = _view_module(monkeypatch, label_root)

    with pytest.raises(LabelPolicyError, match="must match annotation.reviewer"):
        module.build(include_proxy=False)


def test_receipt_without_integrity_hash_is_rejected(tmp_path, monkeypatch):
    label_root = tmp_path / "data" / "labels"
    label_root.mkdir(parents=True)
    _write_fixture(label_root, receipt={"reviewer": "pranay"})
    module = _view_module(monkeypatch, label_root)

    with pytest.raises(LabelPolicyError, match="receipt_sha256"):
        module.build(include_proxy=False)


def test_validation_and_locked_test_roles_stay_excluded_from_default_view(tmp_path, monkeypatch):
    label_root = tmp_path / "data" / "labels"
    label_root.mkdir(parents=True)
    _write_fixture(label_root, role="development")
    _write_fixture(label_root, role="validation",
                   record_id="fixture-verified-val", family_id="fixture-val-family")
    _write_fixture(label_root, role="locked-test",
                   record_id="fixture-verified-lock", family_id="fixture-lock-family")
    module = _view_module(monkeypatch, label_root)

    receipt = module.build(include_proxy=False)
    assert receipt["eligible_records"] == 1
    assert receipt["excluded_by_role"] == {"validation": 1, "locked-test": 1}

    records, _ = load_trainable_records(label_root, include_proxy=False)
    assert [record["id"] for record in records] == ["fixture-verified-v1"]


def test_family_crossing_split_roles_is_rejected(tmp_path, monkeypatch):
    label_root = tmp_path / "data" / "labels"
    label_root.mkdir(parents=True)
    development = _write_fixture(label_root, role="development")
    validation = dict(development)
    validation["id"] = "fixture-verified-val"
    validation["split"] = {"role": "validation"}

    with pytest.raises(LabelPolicyError, match="crosses split roles"):
        validate_trainable_records([development, validation], label_root, include_proxy=False)
