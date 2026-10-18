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


def _resolve_widget_hierarchy(obj: Any) -> dict[str, Any]:
    """Resolve inherited AcroForm field attributes across /Parent dictionaries."""
    name_parts: list[str] = []
    field_type = ""
    flags = 0
    options = None
    alternate_name = ""
    current = obj
    visited: set[int] = set()
    depth = 0
    while current is not None and depth < 16:
        try:
            resolved = current.get_object() if hasattr(current, "get_object") else current
        except Exception:
            break
        if not isinstance(resolved, dict) or id(resolved) in visited:
            break
        visited.add(id(resolved))
        raw_t = resolved.get("/T")
        if raw_t is not None and str(raw_t).strip():
            name_parts.append(str(raw_t).strip())
        if not field_type and resolved.get("/FT"):
            field_type = str(resolved.get("/FT", ""))
        if not flags and resolved.get("/Ff"):
            try:
                flags = int(resolved.get("/Ff", 0) or 0)
            except (TypeError, ValueError):
                pass
        if options is None and resolved.get("/Opt") is not None:
            options = _jsonable(resolved.get("/Opt"))
        if not alternate_name and resolved.get("/TU"):
            alternate_name = str(resolved.get("/TU", "")).strip()
        current = resolved.get("/Parent")
        depth += 1

    qualified_name = ".".join(reversed(name_parts))
    return {
        "field_type": field_type,
        "name": qualified_name,
        "flags": flags,
        "options": options,
        "alternate_name": alternate_name,
    }


def inspect_pdf(path: Path) -> PdfInspection:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    reader = PdfReader(str(path), strict=False)
    native = []
    seen_native_names: set[str] = set()
    try:
        raw_fields = reader.get_fields() or {}
    except Exception:
        raw_fields = {}
    for name, info in raw_fields.items():
        seen_native_names.add(str(name))
        native.append({"name": name, **{str(k): _jsonable(v) for k, v in info.items()}})

    annotations: list[dict[str, Any]] = []
    sizes: list[dict[str, float]] = []
    for page_number, page in enumerate(reader.pages, 1):
        box = page.mediabox
        sizes.append({"width": float(box.width), "height": float(box.height)})
        for annotation in page.get("/Annots", []) or []:
            obj = annotation.get_object()
            inherited = _resolve_widget_hierarchy(obj)
            subtype = str(obj.get("/Subtype", ""))
            annotations.append({
                "page": page_number,
                "subtype": subtype,
                "field_type": inherited["field_type"],
                "name": inherited["name"],
                "alternate_name": inherited["alternate_name"],
                "rect": [float(x) for x in obj.get("/Rect", [])],
                "flags": inherited["flags"],
                "options": inherited["options"],
                "button_value": str(obj.get("/AS", "")),
            })
            if subtype == "/Widget" and inherited["name"] and inherited["name"] not in seen_native_names:
                seen_native_names.add(inherited["name"])
                native.append({
                    "name": inherited["name"],
                    "/FT": inherited["field_type"],
                    "/Ff": inherited["flags"],
                    "/Opt": inherited["options"],
                    "/TU": inherited["alternate_name"],
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
