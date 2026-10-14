"""Build a provenance-preserving weak-supervision corpus for target ranking.

The local corpora describe related but non-identical concepts. Records retain
their source and supervision strength so a future learned detector cannot be
mistaken for a directly labeled form-field benchmark.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import FieldSpec
from .label_ner import entity_types
from .profiles.form6 import form6_fields


# The sibling reference project is machine-local; default to the standard
# workspace layout and allow an override so no absolute user path is baked in.
DOC_EDITOR_ROOT = Path(os.environ.get(
    "PDF_FIELD_LAB_SIBLING_ROOT",
    str(Path.home() / "Projects" / "pdf_editor"),
))
FUNSD_ROOT = DOC_EDITOR_ROOT / "benchmark" / "datasets" / "funsd" / "data"
DOCLAYNET_ROOT = DOC_EDITOR_ROOT / "benchmark" / "datasets" / "doclaynet" / "data"


def _record(*, source: str, group: str, label: str, kind: str, bbox: list[float],
            page_width: float, page_height: float, supervision: str) -> dict[str, Any]:
    return {
        "source": source,
        "group": group,
        "label": label,
        "kind": kind,
        "bbox": bbox,
        "page_width": page_width,
        "page_height": page_height,
        "supervision": supervision,
    }


def _profile_records() -> list[dict[str, Any]]:
    records = []
    variants = {
        "date": ["date", "date of birth", "dob"],
        "image": ["photo", "passport photograph", "upload photo"],
        "signature": ["signature", "sign here", "applicant signature"],
    }
    for field in form6_fields():
        base = _record(
            source="form6-profile", group="form6", label=field.label,
            kind=field.kind if field.kind != "composite" else "text",
            bbox=[field.bbox.x, field.bbox.y, field.bbox.width, field.bbox.height],
            page_width=595.28, page_height=841.89, supervision="reviewed-semantic")
        records.append(base)
        for variant in variants.get(base["kind"], []):
            records.append({**base, "label": variant,
                            "group": "form6",
                            "supervision": "reviewed-semantic-label-augmentation"})
    return records


def _ontology_anchor_records() -> list[dict[str, Any]]:
    """Small reviewed anchors for classes absent from layout proxy datasets."""
    anchors = (
        ("Address and locality", "textarea"),
        ("Additional comments", "textarea"),
        ("Describe the reason", "textarea"),
        ("Email address", "text"),
        ("Phone number", "text"),
        ("Select one option", "choice"),
        ("Choose yes or no", "choice"),
        ("Passport photograph upload", "image"),
        ("Authorized signature", "signature"),
    )
    return [_record(source="ontology-anchors", group="ontology-anchors", label=label,
                    kind=kind, bbox=[0, 0, 1, 1], page_width=1, page_height=1,
                    supervision="reviewed-ontology-anchor") for label, kind in anchors]


def _funsd_records(splits: tuple[str, ...] = ("train",)) -> list[dict[str, Any]]:
    """Load only explicitly permitted FUNSD splits.

    The test split is deliberately excluded from the default advisory corpus.
    It remains available for a future external evaluation, never as training
    input for this project.
    """
    records = []
    for split in splits:
        path = FUNSD_ROOT / f"{split}.json"
        if not path.is_file():
            continue
        for document in json.loads(path.read_text(encoding="utf-8")):
            for entity in document.get("entities", []):
                entity_type = str(entity.get("type", "")).lower()
                kind = "text" if entity_type in {"question", "answer"} else "negative"
                raw_box = [float(value) for value in entity.get("box", [0, 0, 0, 0])]
                if len(raw_box) != 4:
                    continue
                # FUNSD stores [x0, y0, x1, y1]. The field contract stores
                # [x, y, width, height], unlike the local DocLayNet export.
                x0, y0, x1, y1 = raw_box
                bbox = [x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0)]
                records.append(_record(
                    source=f"funsd-{split}", group=f"funsd-{split}",
                    label=str(entity.get("text", "")), kind=kind,
                    bbox=bbox,
                    page_width=1000, page_height=1000, supervision="entity-proxy"))
    return records


def _doclaynet_records() -> list[dict[str, Any]]:
    path = DOCLAYNET_ROOT / "train_sample.json"
    if not path.is_file():
        return []
    records = []
    for page in json.loads(path.read_text(encoding="utf-8")):
        for region in page.get("regions", []):
            class_name = str(region.get("category", region.get("class", region.get("type", ""))))
            kind = "image" if class_name.lower() == "picture" else "negative"
            records.append(_record(
                source="doclaynet-train-sample", group="doclaynet-train-sample",
                label=class_name, kind=kind,
                # This downloaded export uses [x, y, width, height] under
                # `box`, not the COCO-style `bbox` key.
                bbox=[float(value) for value in region.get("box", [0, 0, 0, 0])],
                page_width=float(page.get("width", 1)), page_height=float(page.get("height", 1)),
                supervision="layout-proxy"))
    return records


def build_training_records() -> list[dict[str, Any]]:
    """Return local records without copying source PDFs or sensitive content."""
    records = _profile_records() + _ontology_anchor_records() + _funsd_records() + _doclaynet_records()
    if not records:
        raise RuntimeError("no local training/evaluation records were found")
    return records


def field_features(record: dict[str, Any] | FieldSpec) -> dict[str, float | str]:
    """Convert a target or corpus record into stable, auditable features."""
    if isinstance(record, FieldSpec):
        label = record.label
        bbox = [record.bbox.x, record.bbox.y, record.bbox.width, record.bbox.height]
        page_width, page_height = 595.28, 841.89
    else:
        label = str(record.get("label", ""))
        bbox = list(record.get("bbox", [0, 0, 0, 0]))
        page_width = float(record.get("page_width", 1))
        page_height = float(record.get("page_height", 1))
    normalized = " ".join(label.lower().replace("/", " ").split())
    x, y, width, height = [float(value) for value in bbox]
    words = set(normalized.split())
    return {
        "label": normalized,
        "has_photo_cue": float(any(word in normalized for word in ("photo", "photograph", "picture"))),
        "has_signature_cue": float(any(word in normalized for word in ("signature", "signed", "sign"))),
        "has_date_cue": float(any(word in normalized for word in ("date", "dob", "birth"))),
        "has_choice_cue": float(any(word in words for word in ("choice", "select", "gender", "male", "female", "yes", "no"))),
        "has_textarea_cue": float(any(word in normalized for word in ("address", "comments", "remarks", "description", "reason", "details", "additional", "notes"))),
        "label_entity_count": float(len(entity_types(label))),
        "has_person_name_entity": float("PERSON_NAME_FIELD" in entity_types(label)),
        "has_email_entity": float("EMAIL_FIELD" in entity_types(label)),
        "has_date_entity": float("DATE_FIELD" in entity_types(label)),
        "has_photo_entity": float("PHOTO_FIELD" in entity_types(label)),
        "has_signature_entity": float("SIGNATURE_FIELD" in entity_types(label)),
        "has_choice_entity": float("CHOICE_FIELD" in entity_types(label)),
        "has_textarea_entity": float("TEXT_AREA_FIELD" in entity_types(label)),
        "has_numeric_cue": float(any(character.isdigit() for character in normalized)),
        "label_word_count": float(len(words)),
        "x_norm": x / max(page_width, 1), "y_norm": y / max(page_height, 1),
        "width_norm": width / max(page_width, 1), "height_norm": height / max(page_height, 1),
        "area_norm": (width * height) / max(page_width * page_height, 1),
        "aspect_ratio": width / max(height, 1),
    }
