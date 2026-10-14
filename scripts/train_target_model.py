#!/usr/bin/env python3
"""Train the advisory target reranker from local, provenance-tagged records."""

from __future__ import annotations

import json
import argparse
from pathlib import Path

from pdf_field_lab.label_policy import LabelPolicyError, load_trainable_examples
from pdf_field_lab.target_model import save_target_model, train_target_model


ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-proxy",
        action="store_true",
        help="train only from a trainable view explicitly built with proxy opt-in",
    )
    parser.add_argument("--label-root", type=Path, default=ROOT / "data" / "labels")
    parser.add_argument("--artifact-dir", type=Path, default=ROOT / "artifacts" / "model")
    args = parser.parse_args(argv)
    try:
        records, view_receipt = load_trainable_examples(
            args.label_root, include_proxy=args.include_proxy
        )
    except LabelPolicyError as exc:
        parser.error(str(exc))
    if not records:
        parser.error("no training-eligible records; review and authorize labels before training")

    model, receipt = train_target_model(records)
    artifact_dir = args.artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    save_target_model(model, artifact_dir / "target-classifier.joblib")
    receipt["label_view"] = {
        "schema": view_receipt.get("schema"),
        "source_records_sha256": view_receipt.get("source_records_sha256"),
        "view_sha256": view_receipt.get("view_sha256"),
        "eligible_record_ids": view_receipt.get("eligible_record_ids", []),
        "include_proxy": args.include_proxy,
    }
    (artifact_dir / "training-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
