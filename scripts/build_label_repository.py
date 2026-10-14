"""Build privacy-safe label records from explicitly tested local evidence.

This script stores annotations and provenance, never PDF bytes. Real-document
records are pending and redacted until a human reviews the rendered source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LABEL_ROOT = ROOT / "data" / "labels"
# Real absolute paths must never be checked in. Form-6 uses the committed
# byte-identical sample; the signed financial statement is resolved from the
# environment when the local operator wants a re-linkable locator, and is
# stored as a redacted pseudonym otherwise.
FORM6_SOURCE = ROOT / "data" / "samples" / "RAr0Lq2Avu.pdf"
FORM6_LOCATOR = str(FORM6_SOURCE.relative_to(ROOT))
_MEDPIPER_ENV_PATH = os.environ.get("PDF_FIELD_LAB_MEDPIPER_PDF")
MEDPIPER_SOURCE = _MEDPIPER_ENV_PATH or "local://user-supplied/signed-financial-statement.pdf"
_MEDPIPER_LOCATOR_KIND = "local-path" if _MEDPIPER_ENV_PATH else "local-redacted"
FORM6_ANALYSIS = ROOT / "artifacts" / "form6-current-analysis.json"
MEDPIPER_ANALYSIS = ROOT / "artifacts" / "medpiper-current-analysis.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _analysis(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _records_from_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    existing: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        existing[record["id"]] = record
    return existing


def _annotation_path_for_record(record: dict[str, Any]) -> Path | None:
    target_ref = record["annotation"].get("target_manifest")
    if target_ref and target_ref.startswith("annotations/"):
        return LABEL_ROOT / target_ref
    return None


def _merge_record(record: dict[str, Any], existing: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    """Merge a newly generated record with a previous version.

    Returns (merged_record, preserve_annotation_file).

    Rules:
    - Do not overwrite verified records unless source hash changed.
    - If source hash changed, force verification states back to pending.
    - Preserve existing annotation object for verified status while preserving refreshed
      source metadata from the new proposal.
    """
    if not existing:
        return record, False

    merged = deepcopy(existing)
    merged.update({
        "source": record["source"],
        "provenance": record["provenance"],
    })

    existing_status = existing["annotation"].get("status")

    existing_annotation = existing["annotation"]
    desired_annotation = record["annotation"]

    existing_source_hash = existing.get("source", {}).get("sha256")
    desired_source_hash = record.get("source", {}).get("sha256")
    source_unchanged = existing_source_hash == desired_source_hash

    if existing_status == "verified":
        merged["annotation"] = existing_annotation
        merged["annotation"].update({
            "notes": desired_annotation.get("notes", existing_annotation.get("notes", [])),
            "target_count": desired_annotation.get("target_count", existing_annotation.get("target_count")),
        })
        merged["split"] = record["split"]
        if source_unchanged:
            return merged, True

    # Source changed: verified labels should not survive silently.
    if existing_status == "verified" and not source_unchanged:
        merged["annotation"] = desired_annotation
        merged["annotation"]["status"] = "pending"
        merged["annotation"]["notes"] = [
            "Source hash changed after verification; verification must be re-run.",
            *(desired_annotation.get("notes") or []),
        ]
        merged["annotation"].pop("reviewer", None)
        merged["split"] = record["split"]
        return merged, False

    # Non-verified records keep human notes if present, while refreshing machine policy.
    merged_annotation = deepcopy(desired_annotation)
    if "reviewer" in existing_annotation:
        merged_annotation["reviewer"] = existing_annotation.get("reviewer")
    if "notes" in existing_annotation and existing_annotation["notes"]:
        merged_annotation.setdefault("notes", existing_annotation["notes"])
    merged_annotation["status"] = existing_status
    merged["annotation"] = merged_annotation
    merged["split"] = record["split"]
    return merged, False


def _page_sizes(report: dict[str, Any]) -> list[dict[str, float]]:
    return report["input"]["page_sizes"]


def _field_targets(report: dict[str, Any]) -> list[dict[str, Any]]:
    targets = []
    for field in report["logical_fields"]:
        targets.append({
            "id": field["id"],
            "page": field["page"],
            "class": field["kind"],
            "bbox": field["bbox"],
            "expected": "detected",
            "label": field["label"],
            "required_field_type": field["kind"],
            "source": "reviewed-profile-calibration",
        })
    return targets


def _signature_targets(report: dict[str, Any]) -> list[dict[str, Any]]:
    counters: dict[int, int] = {}
    targets = []
    for observation in report["signature_observations"]:
        page = int(observation["page"])
        counters[page] = counters.get(page, 0) + 1
        status = observation["status"]
        targets.append({
            "id": f"page-{page}-signature-slot-{counters[page]}",
            "page": page,
            "class": "existing-signature-ink" if status == "present" else "missing-signature-slot",
            "bbox": observation["bbox"],
            "expected": status,
            "role": observation.get("role", "redacted"),
            "identity": "redacted",
            "source": "signature-observation.v1",
        })
    return targets


def _record(record_id: str, family_id: str, source: dict[str, Any], provenance: dict[str, Any],
            annotation: dict[str, Any], split: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record_id,
        "family_id": family_id,
        "source": source,
        "provenance": provenance,
        "annotation": annotation,
        "split": split,
    }


def _build_records() -> list[dict[str, Any]]:
    form6 = _analysis(FORM6_ANALYSIS)
    medpiper = _analysis(MEDPIPER_ANALYSIS)
    records: list[dict[str, Any]] = []
    records.append(_record(
        "real-form6-desktop-v1", "form6-family",
        {"locator_kind": "local-path", "locator": FORM6_LOCATOR,
         "sha256": form6["input"]["sha256"], "page_count": form6["input"]["pages"],
         "page_sizes": _page_sizes(form6), "privacy_class": "user-sensitive"},
        {"source_kind": "real-user-probe", "producer": form6["input"]["metadata"].get("/Producer"),
         "license": "not-applicable-user-supplied-local",
         "lineage": "supplied Form-6 probe; reviewed profile calibration only"},
        {"status": "pending", "target_manifest": "annotations/real-form6-desktop-v1.json",
         "target_count": len(form6["logical_fields"]), "reviewer": None,
         "notes": ["Review every page and child grid extent before any training use."]},
        {"role": "not-for-training", "reason": "real user-sensitive probe pending human review"},
    ))
    records.append(_record(
        "real-medpiper-signed-fy2024-25-v1", "medpiper-financial-statement-family",
        {"locator_kind": _MEDPIPER_LOCATOR_KIND, "locator": str(MEDPIPER_SOURCE),
         "sha256": medpiper["input"]["sha256"], "page_count": medpiper["input"]["pages"],
         "page_sizes": _page_sizes(medpiper), "privacy_class": "user-sensitive"},
        {"source_kind": "real-user-probe", "producer": medpiper["input"]["metadata"].get("/Producer"),
         "license": "not-applicable-user-supplied-local",
         "lineage": "signed financial statement; signature audit probe only"},
        {"status": "pending", "target_manifest": "annotations/real-medpiper-signed-fy2024-25-v1.json",
         "target_count": len(medpiper["signature_observations"]), "reviewer": None,
         "notes": ["Review existing versus empty signature slots. Signer identity is redacted here."]},
        {"role": "not-for-training", "reason": "sensitive signed document pending human review"},
    ))

    gold_manifest = json.loads((ROOT / "artifacts/goldset/goldset-manifest.json").read_text(encoding="utf-8"))
    for family in gold_manifest["families"]:
        for representation in family["representations"]:
            records.append(_record(
                f"gold-{family['document_family_id']}-{representation['representation']}",
                family["document_family_id"],
                {"locator_kind": "project-artifact", "locator": representation["path"],
                 "sha256": representation["source_sha256"], "page_count": 1,
                 "page_sizes": [{"width": 612.0, "height": 792.0}], "privacy_class": "controlled"},
                {"source_kind": "controlled-positive-fixture", "producer": "build_goldset.py",
                 "license": "project-authored",
                 "lineage": "authored family; representation derivative"},
                {"status": "proxy", "target_manifest": representation["labels"],
                 "evaluation": representation["evaluation"], "reviewer": None,
                 "notes": ["Authored controlled label, not human real-world confirmation."]},
                {"role": "development", "reason": "controlled plumbing and calibration only"},
            ))

    records.extend([
        _record(
            "sibling-detector-calibration-v1", "sibling-calibration-family",
            {"locator_kind": "sibling-read-only",
             "locator": "~/Projects/pdf_editor/benchmark/results/detector-calibration/detector-calibration.pdf",
             "sha256": "recorded-in-sibling-label-manifest", "page_count": 2,
             "page_sizes": [], "privacy_class": "controlled"},
            {"source_kind": "sibling-reviewed-calibration", "producer": "pdf_editor",
             "license": "inherited-external-reference-not-adopted",
             "lineage": "read-only calibration reference"},
            {"status": "pending", "target_manifest": "external-sibling-manifest",
             "target_count": None, "reviewer": None,
             "notes": ["Do not copy source or labels here; reconcile only after independent review."]},
            {"role": "not-for-training", "reason": "external reference and split not independently governed"},
        ),
        _record(
            "system-corpus-snapshot-2026-09-10", "system-corpus-collection-2026-09-10",
            {"locator_kind": "collection-snapshot", "locator": "artifacts/system-corpus/summary.json",
             "sha256": _sha256(ROOT / "artifacts/system-corpus/summary.json"), "page_count": None,
             "page_sizes": [], "privacy_class": "collection-metadata"},
            {"source_kind": "system-corpus-benchmark", "producer": "system_corpus_benchmark.py",
             "license": "not-recorded-not-trainable",
             "lineage": "146 deep samples from local inventory"},
            {"status": "pending", "target_manifest": None, "target_count": 94,
             "reviewer": None,
             "notes": ["Execution inventory only; no field-level labels exist."]},
            {"role": "not-for-training", "reason": "no field-level gold annotations"},
        ),
    ])
    return records


def _write_annotation_if_needed(record: dict[str, Any], preserve_annotation_file: bool, refresh_targets: bool) -> None:
    if not refresh_targets or preserve_annotation_file:
        return

    manifest = _annotation_path_for_record(record)
    if not manifest:
        return
    manifest.parent.mkdir(parents=True, exist_ok=True)

    if record["id"] == "real-form6-desktop-v1":
        payload = {
            "schema": "pdf-field-lab.annotation.v1",
            "status": "pending",
            "source_sha256": record["source"]["sha256"],
            "targets": _field_targets(_analysis(FORM6_ANALYSIS)),
        }
        manifest.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    elif record["id"] == "real-medpiper-signed-fy2024-25-v1":
        payload = {
            "schema": "pdf-field-lab.annotation.v1",
            "status": "pending",
            "source_sha256": record["source"]["sha256"],
            "targets": _signature_targets(_analysis(MEDPIPER_ANALYSIS)),
        }
        manifest.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _review_candidate_records(paths: list[Path]) -> list[dict[str, Any]]:
    """Convert session review-candidate JSONL into pending repository records.

    Uses the canonical candidate shape from pdf_field_lab.review_diff so the
    server export and this builder cannot drift apart.
    """

    from pdf_field_lab.review_diff import candidate_record_stub

    records: list[dict[str, Any]] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            candidate = json.loads(line)
            records.append(candidate_record_stub(candidate))
    return records


def _retain_ingested_records(
    merged_records: list[dict[str, Any]], existing_records: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Keep previously ingested review-candidate records across rebuilds.

    Candidate records only re-enter ``generated`` when their source JSONL is
    passed again. Dropping them on a plain rebuild would erase human review
    state (the FFL-LBL-002 failure mode), so any existing record that entered
    through the review-session pipeline is carried forward as-is.
    """

    present = {record["id"] for record in merged_records}
    retained = list(merged_records)
    for record_id, record in existing_records.items():
        if record_id in present:
            continue
        if record.get("source", {}).get("locator_kind") == "session-manifest":
            retained.append(record)
    return retained


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--review-candidates", type=Path, action="append", default=[],
        help="review-candidate JSONL exports (from the session endpoint) to "
             "ingest as pending records; idempotent across reruns")
    args = parser.parse_args(argv)

    LABEL_ROOT.mkdir(parents=True, exist_ok=True)
    annotations = LABEL_ROOT / "annotations"
    annotations.mkdir(parents=True, exist_ok=True)

    generated = _build_records()
    generated.extend(_review_candidate_records(args.review_candidates))
    existing_records = _records_from_jsonl(LABEL_ROOT / "records.jsonl")
    merged_records = []
    for record in generated:
        existing = existing_records.get(record["id"])
        merged_record, preserve_annotation_file = _merge_record(record, existing)

        target_ref = merged_record["annotation"].get("target_manifest")
        if target_ref and not target_ref.startswith("annotations/"):
            merged_record["annotation"]["linked_only"] = True

        should_refresh_annotation = merged_record["annotation"].get("status") != "verified"
        _write_annotation_if_needed(merged_record, preserve_annotation_file, should_refresh_annotation)
        merged_records.append(merged_record)

    merged_records = _retain_ingested_records(merged_records, existing_records)

    (LABEL_ROOT / "records.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in merged_records),
        encoding="utf-8",
    )
    pending = [record for record in merged_records if record["annotation"]["status"] == "pending"]
    (LABEL_ROOT / "review-queue.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in pending),
        encoding="utf-8",
    )
    print(json.dumps({"records": len(merged_records), "pending_review": len(pending),
                      "label_root": str(LABEL_ROOT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
