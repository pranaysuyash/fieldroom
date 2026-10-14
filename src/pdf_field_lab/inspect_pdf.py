"""Structural and text-layer inspection with no mutation of the source PDF."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pdfplumber
from pypdf import PdfReader

from .models import PdfInspection


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)


def inspect_pdf(path: Path) -> PdfInspection:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    reader = PdfReader(str(path), strict=False)
    native = []
    for name, info in (reader.get_fields() or {}).items():
        native.append({"name": name, **{str(k): _jsonable(v) for k, v in info.items()}})

    annotations: list[dict[str, Any]] = []
    sizes: list[dict[str, float]] = []
    for page_number, page in enumerate(reader.pages, 1):
        box = page.mediabox
        sizes.append({"width": float(box.width), "height": float(box.height)})
        for annotation in page.get("/Annots", []) or []:
            obj = annotation.get_object()
            annotations.append({
                "page": page_number,
                "subtype": str(obj.get("/Subtype", "")),
                "field_type": str(obj.get("/FT", "")),
                "name": str(obj.get("/T", "")),
                "rect": [float(x) for x in obj.get("/Rect", [])],
                "flags": int(obj.get("/Ff", 0) or 0),
                "options": _jsonable(obj.get("/Opt")),
                "button_value": str(obj.get("/AS", "")),
            })

    chars: list[int] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            chars.append(len(page.extract_text() or ""))

    return PdfInspection(
        path=str(path), sha256=digest, pages=len(reader.pages), page_sizes=sizes,
        metadata={str(k): _jsonable(v) for k, v in (reader.metadata or {}).items()},
        native_fields=native, annotations=annotations, text_chars_by_page=chars,
    )
