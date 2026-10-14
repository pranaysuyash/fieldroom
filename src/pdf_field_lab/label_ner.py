"""Deterministic field-label intent extraction.

This is a small NER-like layer for form labels. It extracts product ontology
entities from label text, but it does not pretend to identify real-world people
or organizations. Geometry and human review remain authoritative.
"""

from __future__ import annotations

import re
from typing import Any


_NORMALIZE = re.compile(r"[^\w]+", re.UNICODE)

_INTENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("PERSON_NAME_FIELD", ("name", "applicant", "traveler", "passenger", "contact person")),
    ("EMAIL_FIELD", ("email", "e mail", "mail id")),
    ("PHONE_FIELD", ("phone", "mobile", "telephone", "contact number")),
    ("ADDRESS_FIELD", ("address", "residence", "street", "city", "state", "pin code", "postal")),
    ("DATE_FIELD", ("date", "dob", "birth", "month", "year")),
    ("IDENTIFIER_FIELD", ("number", " no", "id", "account", "aadhaar", "passport")),
    ("PHOTO_FIELD", ("photo", "photograph", "picture", "image", "logo", "upload")),
    ("SIGNATURE_FIELD", ("signature", "sign here", "signed", "thumb impression")),
    ("CHOICE_FIELD", ("select", "choose", "checkbox", "radio", "agree", "accept", "gender", "option", "yes", "no")),
    ("TEXT_AREA_FIELD", ("comments", "remarks", "description", "explain", "reason", "additional information", "details")),
)


def normalize_label(label: str) -> str:
    return _NORMALIZE.sub(" ", label.lower()).strip()


def extract_label_entities(label: str) -> list[dict[str, Any]]:
    """Return stable intent entities with the matched cue and character span."""
    normalized = normalize_label(label)
    entities: list[dict[str, Any]] = []
    for entity_type, cues in _INTENT_RULES:
        for cue in cues:
            match = re.search(rf"(?<!\w){re.escape(cue.strip())}(?!\w)", normalized)
            if match:
                entities.append({
                    "type": entity_type,
                    "cue": cue.strip(),
                    "start": match.start(),
                    "end": match.end(),
                    "source": "label-rule",
                })
                break
    # "Passport photo" is an image interaction, not an identifier input. Keep
    # passport-number labels eligible for IDENTIFIER_FIELD by suppressing only
    # the photo-context collision.
    if any(entity["type"] == "PHOTO_FIELD" for entity in entities):
        entities = [entity for entity in entities if entity["type"] != "IDENTIFIER_FIELD"]
    return entities


def entity_types(label: str) -> list[str]:
    return [str(entity["type"]) for entity in extract_label_entities(label)]
