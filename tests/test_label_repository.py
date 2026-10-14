import json
from pathlib import Path
import importlib.util

import pytest

from pdf_field_lab.label_policy import LabelPolicyError, load_trainable_records

ROOT = Path(__file__).parents[1]
LABEL_ROOT = ROOT / "data" / "labels"


def _records():
    return [json.loads(line) for line in (LABEL_ROOT / "records.jsonl").read_text().splitlines() if line]


def test_label_repository_has_no_pdf_payloads_and_records_tested_families():
    records = _records()
    assert len(records) >= 13
    assert {record["family_id"] for record in records} >= {
        "form6-family", "medpiper-financial-statement-family",
        "employment-application", "travel-consent", "vendor-onboarding",
    }
    assert not list(LABEL_ROOT.rglob("*.pdf"))
    payload_paths = [LABEL_ROOT / "records.jsonl", LABEL_ROOT / "review-queue.jsonl"]
    payload_paths.extend((LABEL_ROOT / "annotations").glob("*.json"))
    text = "\n".join(path.read_text(errors="ignore") for path in payload_paths)
    assert "raw_pdf_bytes" not in text
    assert "signature_pixels" not in text


def test_pending_real_records_are_not_training_eligible():
    records = _records()
    for record in records:
        if record["annotation"]["status"] == "pending":
            assert record["split"]["role"] == "not-for-training"


def test_every_record_declares_license_and_default_training_view_is_empty():
    records = _records()
    assert all(record["provenance"].get("license") for record in records)
    receipt = json.loads((LABEL_ROOT / "trainable-receipt.json").read_text())
    view = (LABEL_ROOT / "trainable.jsonl").read_text().splitlines()
    assert receipt["policy"]["include_proxy"] is False
    assert receipt["eligible_records"] == 0
    assert view == []


def test_proxy_view_requires_explicit_development_opt_in(tmp_path, monkeypatch):
    script = ROOT / "scripts" / "build_trainable_label_view.py"
    spec = importlib.util.spec_from_file_location("trainable_view", script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "LABEL_ROOT", LABEL_ROOT)
    monkeypatch.setattr(module, "OUTPUT", tmp_path / "proxy.jsonl")
    monkeypatch.setattr(module, "RECEIPT", tmp_path / "proxy-receipt.json")
    receipt = module.build(include_proxy=True)
    assert receipt["eligible_records"] == 9
    assert receipt["policy"]["include_proxy"] is True
    assert receipt["policy"]["allowed_split_roles"] == ["development"]
    assert receipt["source_records_sha256"]
    assert receipt["view_sha256"]


def test_trainable_loader_rejects_stale_view_after_source_records_change(tmp_path, monkeypatch):
    label_root = tmp_path / "data" / "labels"
    label_root.mkdir(parents=True)
    project_root = tmp_path
    manifest = project_root / "artifacts" / "goldset" / "fixture-labels.json"
    manifest.parent.mkdir(parents=True)
    source_hash = "a" * 64
    manifest.write_text(json.dumps({
        "schema": "pdf-field-lab.gold-labels.v1",
        "sourceSha256": source_hash,
        "cases": [{
            "id": "fixture.name", "pageIndex": 0, "class": "text",
            "expected": "detected", "target": {"x": 1, "y": 1, "width": 10, "height": 10},
        }],
    }), encoding="utf-8")
    record = {
        "id": "fixture-v1",
        "family_id": "fixture-family",
        "source": {
            "sha256": source_hash, "locator_kind": "project-artifact",
            "privacy_class": "controlled", "page_count": 1, "page_sizes": [],
        },
        "provenance": {
            "source_kind": "controlled-positive-fixture", "lineage": "pytest",
            "license": "project-authored",
        },
        "annotation": {"status": "proxy", "target_manifest": "artifacts/goldset/fixture-labels.json"},
        "split": {"role": "development"},
    }
    records_path = label_root / "records.jsonl"
    records_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    script = ROOT / "scripts" / "build_trainable_label_view.py"
    spec = importlib.util.spec_from_file_location("trainable_view_stale", script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "LABEL_ROOT", label_root)
    monkeypatch.setattr(module, "OUTPUT", label_root / "trainable.jsonl")
    monkeypatch.setattr(module, "RECEIPT", label_root / "trainable-receipt.json")
    module.build(include_proxy=True)

    records_path.write_text(records_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(LabelPolicyError, match="records.jsonl hash differs"):
        load_trainable_records(label_root, include_proxy=True)


def test_training_entrypoint_consumes_governed_view_not_legacy_builder():
    source = (ROOT / "scripts" / "train_target_model.py").read_text(encoding="utf-8")
    assert "load_trainable_examples" in source
    assert "build_training_records" not in source


def test_real_signature_annotation_is_redacted_and_preserves_occupancy():
    annotation = json.loads((LABEL_ROOT / "annotations/real-medpiper-signed-fy2024-25-v1.json").read_text())
    assert annotation["status"] == "pending"
    assert annotation["targets"]
    assert {target["expected"] for target in annotation["targets"]} == {"present", "missing"}
    assert all(target["identity"] == "redacted" for target in annotation["targets"])


def test_verified_annotations_are_preserved_across_rebuild(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    label_root = repo / "data" / "labels"
    label_root.mkdir(parents=True)

    artifacts = repo / "artifacts"
    (artifacts / "goldset").mkdir(parents=True)
    (artifacts / "system-corpus").mkdir()

    (artifacts / "form6-current-analysis.json").write_text(
        json.dumps({
            "input": {
                "sha256": "current-form6-sha",
                "pages": 2,
                "metadata": {"/Producer": "pytest"},
                "page_sizes": [{"width": 612.0, "height": 792.0}, {"width": 612.0, "height": 792.0}],
            },
            "logical_fields": [
                {"id": "F6-01", "page": 1, "kind": "text", "bbox": {"x": 0, "y": 0, "width": 1, "height": 1}, "label": "Name"},
            ],
        }),
        encoding="utf-8",
    )
    (artifacts / "medpiper-current-analysis.json").write_text(
        json.dumps({
            "input": {
                "sha256": "current-medpiper-sha",
                "pages": 2,
                "metadata": {"/Producer": "pytest"},
                "page_sizes": [{"width": 612.0, "height": 792.0}, {"width": 612.0, "height": 792.0}],
            },
            "signature_observations": [
                {"page": 1, "status": "missing", "bbox": {"x": 1, "y": 1, "width": 2, "height": 2}, "role": "Partner"},
            ],
        }),
        encoding="utf-8",
    )
    (artifacts / "system-corpus" / "summary.json").write_text(json.dumps({"items": []}), encoding="utf-8")
    (artifacts / "goldset" / "goldset-manifest.json").write_text(json.dumps({"families": []}), encoding="utf-8")

    manual_annotation = {
        "schema": "pdf-field-lab.annotation.v1",
        "status": "verified",
        "source_sha256": "current-form6-sha",
        "human_touched": True,
        "targets": [{"id": "v1", "page": 1, "class": "text", "bbox": {"x": 100, "y": 100, "width": 20, "height": 10},
                    "expected": "verified", "label": "Human note"}],
    }
    (label_root / "annotations").mkdir(exist_ok=True)
    (label_root / "annotations" / "real-form6-desktop-v1.json").write_text(
        json.dumps(manual_annotation), encoding="utf-8"
    )
    (label_root / "records.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "id": "real-form6-desktop-v1",
                    "family_id": "form6-family",
                    "source": {
                        "locator_kind": "local-path",
                        "locator": "data/samples/RAr0Lq2Avu.pdf",
                        "sha256": "current-form6-sha",
                    },
                    "provenance": {
                        "source_kind": "real-user-probe",
                        "producer": "pytest",
                        "license": "not-applicable-user-supplied-local",
                        "lineage": "prior",
                    },
                    "annotation": {
                        "status": "verified",
                        "target_manifest": "annotations/real-form6-desktop-v1.json",
                        "target_count": 1,
                        "reviewer": "alice",
                    },
                    "split": {"role": "not-for-training", "reason": "prior"},
                }
            ) + "\n"
        ),
        encoding="utf-8",
    )

    script = ROOT / "scripts" / "build_label_repository.py"
    spec = importlib.util.spec_from_file_location("label_repository", script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "ROOT", repo)
    monkeypatch.setattr(module, "LABEL_ROOT", label_root)
    monkeypatch.setattr(module, "FORM6_ANALYSIS", artifacts / "form6-current-analysis.json")
    monkeypatch.setattr(module, "MEDPIPER_ANALYSIS", artifacts / "medpiper-current-analysis.json")

    module.main([])

    rebuilt_record = json.loads((label_root / "records.jsonl").read_text().splitlines()[0])
    rebuilt_annotation = json.loads((label_root / "annotations/real-form6-desktop-v1.json").read_text())
    assert rebuilt_record["annotation"]["status"] == "verified"
    assert rebuilt_record["annotation"]["reviewer"] == "alice"
    assert rebuilt_annotation["human_touched"] is True


def test_source_hash_change_reopens_verified_records(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    label_root = repo / "data" / "labels"
    label_root.mkdir(parents=True)

    artifacts = repo / "artifacts"
    (artifacts / "goldset").mkdir(parents=True)
    (artifacts / "system-corpus").mkdir()

    (artifacts / "form6-current-analysis.json").write_text(
        json.dumps({
            "input": {
                "sha256": "next-form6-sha",
                "pages": 2,
                "metadata": {"/Producer": "pytest"},
                "page_sizes": [{"width": 612.0, "height": 792.0}, {"width": 612.0, "height": 792.0}],
            },
            "logical_fields": [
                {"id": "F6-01", "page": 1, "kind": "text", "bbox": {"x": 0, "y": 0, "width": 1, "height": 1}, "label": "Name"},
            ],
        }),
        encoding="utf-8",
    )
    (artifacts / "medpiper-current-analysis.json").write_text(
        json.dumps({
            "input": {
                "sha256": "current-medpiper-sha",
                "pages": 2,
                "metadata": {"/Producer": "pytest"},
                "page_sizes": [{"width": 612.0, "height": 792.0}, {"width": 612.0, "height": 792.0}],
            },
            "signature_observations": [],
        }),
        encoding="utf-8",
    )
    (artifacts / "system-corpus" / "summary.json").write_text(json.dumps({"items": []}), encoding="utf-8")
    (artifacts / "goldset" / "goldset-manifest.json").write_text(json.dumps({"families": []}), encoding="utf-8")

    (label_root / "annotations").mkdir(exist_ok=True)
    (label_root / "annotations" / "real-form6-desktop-v1.json").write_text(json.dumps({
        "schema": "pdf-field-lab.annotation.v1",
        "status": "verified",
        "source_sha256": "stale-sha",
        "targets": [],
    }), encoding="utf-8")
    (label_root / "records.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "id": "real-form6-desktop-v1",
                    "family_id": "form6-family",
                    "source": {
                        "locator_kind": "local-path",
                        "locator": "data/samples/RAr0Lq2Avu.pdf",
                        "sha256": "stale-form6-sha",
                    },
                    "provenance": {
                        "source_kind": "real-user-probe",
                        "producer": "pytest",
                        "license": "not-applicable-user-supplied-local",
                        "lineage": "prior",
                    },
                    "annotation": {
                        "status": "verified",
                        "target_manifest": "annotations/real-form6-desktop-v1.json",
                        "target_count": 1,
                        "reviewer": "alice",
                    },
                    "split": {"role": "not-for-training", "reason": "prior"},
                }
            ) + "\n"
        ),
        encoding="utf-8",
    )

    script = ROOT / "scripts" / "build_label_repository.py"
    spec = importlib.util.spec_from_file_location("label_repository", script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "ROOT", repo)
    monkeypatch.setattr(module, "LABEL_ROOT", label_root)
    monkeypatch.setattr(module, "FORM6_ANALYSIS", artifacts / "form6-current-analysis.json")
    monkeypatch.setattr(module, "MEDPIPER_ANALYSIS", artifacts / "medpiper-current-analysis.json")

    module.main([])

    rebuilt_record = json.loads((label_root / "records.jsonl").read_text().splitlines()[0])
    assert rebuilt_record["annotation"]["status"] == "pending"
    assert rebuilt_record["annotation"].get("reviewer") is None


def test_retain_ingested_records_preserves_review_session_state_across_rebuilds():
    """FFL-FLY-011 guarantee: ingested candidates survive plain rebuilds."""

    import sys

    sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
    import build_label_repository as builder

    generated = [{"id": "real-form6-desktop-v1", "source": {"locator_kind": "local-path"},
                  "annotation": {"status": "pending"}, "split": {"role": "not-for-training"}}]
    existing = {
        "review-abc123-r1-a-accepted": {
            "id": "review-abc123-r1-a-accepted",
            "source": {"locator_kind": "session-manifest", "sha256": "a" * 64},
            "annotation": {"status": "verified", "reviewer": "alice"},
            "split": {"role": "development"},
        },
        "real-medpiper-signed-fy2024-25-v1": {
            "id": "real-medpiper-signed-fy2024-25-v1",
            "source": {"locator_kind": "local-redacted"},
            "annotation": {"status": "pending"},
            "split": {"role": "not-for-training"},
        },
    }
    retained = builder._retain_ingested_records(generated, existing)
    ids = [record["id"] for record in retained]
    assert ids == ["real-form6-desktop-v1", "review-abc123-r1-a-accepted"]
    assert retained[1]["annotation"]["status"] == "verified"
