"""Optional Modal entrypoint for the advisory target model.

This file is intentionally cloud-ready but does not submit a job by import.
Run it only after the operator has authenticated Modal and accepted the bounded
compute scope. It receives metadata records, not user-uploaded PDF bytes.
"""

from __future__ import annotations

import json
from typing import Any

import modal

from pdf_field_lab.label_policy import load_trainable_examples
from pdf_field_lab.target_model import train_target_model


app = modal.App("pdf-field-lab-target-model")
image = modal.Image.debian_slim(python_version="3.13").pip_install(
    "joblib>=1.4", "scikit-learn>=1.6")


@app.function(image=image, timeout=1800, cpu=4, memory=8192)
def train_remote(records: list[dict[str, Any]]) -> dict[str, Any]:
    _, receipt = train_target_model(records)
    return receipt


@app.local_entrypoint()
def main() -> None:
    records, _ = load_trainable_examples("data/labels", include_proxy=False)
    if not records:
        raise RuntimeError("no training-eligible records; build and review the governed label view first")
    receipt = train_remote.remote(records)
    print(json.dumps(receipt, indent=2))
