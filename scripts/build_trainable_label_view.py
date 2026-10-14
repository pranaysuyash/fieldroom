"""Build the only label view that model-training jobs are allowed to consume.

The repository is the source of truth for provenance and review state. This
derived view deliberately contains records, not PDF bytes or completed values.
By default it admits only human-verified annotations in trainable splits.
Proxy labels require an explicit development-only flag.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pdf_field_lab.label_policy import LabelPolicyError, read_jsonl, validate_trainable_records

ROOT = Path(__file__).resolve().parents[1]
LABEL_ROOT = ROOT / "data" / "labels"
OUTPUT = LABEL_ROOT / "trainable.jsonl"
RECEIPT = LABEL_ROOT / "trainable-receipt.json"


def _records() -> list[dict[str, Any]]:
    return read_jsonl(LABEL_ROOT / "records.jsonl")


def _eligible(record: dict[str, Any], include_proxy: bool) -> bool:
    status = record["annotation"]["status"]
    role = record["split"]["role"]
    allowed_statuses = {"verified"}
    if include_proxy:
        allowed_statuses.add("proxy")
    return status in allowed_statuses and role == "development"


def build(*, include_proxy: bool = False) -> dict[str, Any]:
    records = _records()
    eligible = [record for record in records if _eligible(record, include_proxy)]
    # A record that looks eligible but fails provenance or manifest checks must
    # stop the build. Silently excluding it would make an apparently healthy
    # receipt conceal a labeling or authorization defect.
    validate_trainable_records(eligible, LABEL_ROOT, include_proxy=include_proxy)
    excluded_by_status: dict[str, int] = {}
    excluded_by_role: dict[str, int] = {}
    for record in records:
        if record in eligible:
            continue
        status = record["annotation"]["status"]
        role = record["split"]["role"]
        excluded_by_status[status] = excluded_by_status.get(status, 0) + 1
        excluded_by_role[role] = excluded_by_role.get(role, 0) + 1

    view_payload = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in eligible
    ).encode("utf-8")
    OUTPUT.write_bytes(view_payload)
    source_records_path = LABEL_ROOT / "records.jsonl"
    source_records_sha256 = hashlib.sha256(source_records_path.read_bytes()).hexdigest()
    view_sha256 = hashlib.sha256(view_payload).hexdigest()
    receipt = {
        "schema": "pdf-field-lab.trainable-label-view.v2",
        "source": "data/labels/records.jsonl",
        "source_records_sha256": source_records_sha256,
        "view_sha256": view_sha256,
        "eligible_record_ids": [record["id"] for record in eligible],
        "eligible_records": len(eligible),
        "policy": {
            "allowed_statuses": ["proxy", "verified"] if include_proxy else ["verified"],
            "allowed_split_roles": ["development"],
            "include_proxy": include_proxy,
        },
        "excluded_records": len(records) - len(eligible),
        "excluded_by_status": excluded_by_status,
        "excluded_by_role": excluded_by_role,
    }
    RECEIPT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-proxy",
        action="store_true",
        help="include controlled proxy labels for development calibration only",
    )
    args = parser.parse_args()
    try:
        receipt = build(include_proxy=args.include_proxy)
    except (LabelPolicyError, OSError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
