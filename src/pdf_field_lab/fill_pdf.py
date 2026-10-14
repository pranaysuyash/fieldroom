"""Fill reconstructed widgets and place local images into image regions.

This module deliberately does not implement cryptographic PDF signing. A
signature image or thumb-impression scan is a visual placement, and remains
reviewable content rather than a claim of legal digital signature validity.
"""

from __future__ import annotations

import json
import base64
import os
import tempfile
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .models import FieldSpec


def _profile_lookup(fields: list[FieldSpec]) -> dict[str, FieldSpec]:
    return {field.id: field for field in fields}


def _page_widgets(writer: PdfWriter):
    for page_index, page in enumerate(writer.pages):
        for annotation_ref in page.get("/Annots", []) or []:
            annotation = annotation_ref.get_object()
            if annotation.get("/Subtype") != "/Widget":
                continue
            parent = annotation.get("/Parent")
            parent_obj = parent.get_object() if parent is not None else annotation
            yield page_index, annotation, parent_obj


def _set_choice(writer: PdfWriter, field: FieldSpec, value: Any) -> bool:
    options = field.options or [{"value": "selected"}]
    selected = {str(value)} if isinstance(value, str) else {str(v) for v in (value or [])}
    matched = False
    for _, annotation, parent in _page_widgets(writer):
        parent_name = str(parent.get("/T", ""))
        if parent_name != field.id and not parent_name.startswith(f"{field.id}_"):
            continue
        kids = parent.get("/Kids")
        if kids is not None:
            parent[NameObject("/V")] = NameObject("/Off")
            for index, child_ref in enumerate(kids):
                child = child_ref.get_object()
                is_selected = index < len(options) and str(options[index]["value"]) in selected
                child[NameObject("/AS")] = NameObject("/Yes" if is_selected else "/Off")
                if is_selected:
                    parent[NameObject("/V")] = NameObject("/Yes")
                    matched = True
        else:
            name = str(annotation.get("/T", ""))
            try:
                index = int(name.rsplit("_", 1)[-1])
            except ValueError:
                index = -1
            is_selected = index >= 0 and index < len(options) and str(options[index]["value"]) in selected
            annotation[NameObject("/AS")] = NameObject("/Yes" if is_selected else "/Off")
            annotation[NameObject("/V")] = NameObject("/Yes" if is_selected else "/Off")
            matched = matched or is_selected
    return matched


def _image_overlay(writer: PdfWriter, fields: list[FieldSpec], values: dict[str, Any]) -> list[str]:
    """Merge local image placements into pages and return placed field IDs."""
    placed: list[str] = []
    by_id = _profile_lookup(fields)
    per_page: dict[int, list[tuple[FieldSpec, Path]]] = {}
    temp_images: list[Path] = []
    for field_id, raw_path in values.items():
        field = by_id.get(field_id)
        if field is None or field.kind not in {"image", "signature"}:
            continue
        if isinstance(raw_path, dict):
            raw_path = raw_path.get("data_url") or raw_path.get("path")
        if isinstance(raw_path, str) and raw_path.startswith("data:"):
            header, encoded = raw_path.split(",", 1)
            extension = ".png" if "png" in header.lower() else ".jpg"
            fd, temp_name = tempfile.mkstemp(prefix="pdf-field-upload-", suffix=extension)
            os.close(fd)
            image_path = Path(temp_name)
            image_path.write_bytes(base64.b64decode(encoded))
            temp_images.append(image_path)
        else:
            image_path = Path(str(raw_path)).expanduser()
        if not image_path.is_file():
            raise FileNotFoundError(f"image for {field_id} does not exist: {image_path}")
        per_page.setdefault(field.page - 1, []).append((field, image_path))

    try:
        for page_index, placements in per_page.items():
            page = writer.pages[page_index]
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            fd, temp_name = tempfile.mkstemp(prefix="pdf-field-image-", suffix=".pdf")
            os.close(fd)
            try:
                overlay_path = Path(temp_name)
                drawing = canvas.Canvas(str(overlay_path), pagesize=(width, height))
                for field, image_path in placements:
                    x, y, w, h = field.bbox.x, field.bbox.y, field.bbox.width, field.bbox.height
                    drawing.drawImage(ImageReader(str(image_path)), x, height - y - h, width=w, height=h,
                                      preserveAspectRatio=True, anchor="c", mask="auto")
                    placed.append(field.id)
                drawing.save()
                overlay_page = PdfReader(str(overlay_path), strict=False).pages[0]
                page.merge_page(overlay_page)
            finally:
                Path(temp_name).unlink(missing_ok=True)
    finally:
        for temp_image in temp_images:
            temp_image.unlink(missing_ok=True)
    return placed


def _character_grid_overlay(writer: PdfWriter, fields: list[FieldSpec], values: dict[str, Any]) -> list[str]:
    """Render one user-entered string across a printed character grid."""
    placed: list[str] = []
    by_id = _profile_lookup(fields)
    per_page: dict[int, list[tuple[FieldSpec, str]]] = {}
    for field_id, raw_value in values.items():
        field = by_id.get(field_id)
        if field is None or field.input_mode != "character-grid":
            continue
        value = str(raw_value or "").replace("\n", " ").strip()
        if field.max_length:
            value = value[:field.max_length]
        per_page.setdefault(field.page - 1, []).append((field, value))

    for page_index, placements in per_page.items():
        page = writer.pages[page_index]
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        fd, temp_name = tempfile.mkstemp(prefix="pdf-field-grid-", suffix=".pdf")
        os.close(fd)
        try:
            overlay_path = Path(temp_name)
            drawing = canvas.Canvas(str(overlay_path), pagesize=(width, height))
            for field, value in placements:
                rows = field.grid_rows or [{
                    "bbox": field.bbox.as_dict(),
                    "cell_count": field.max_length or max(1, len(value)),
                }]
                offset = 0
                for row in rows:
                    row_box = row["bbox"]
                    cell_count = max(1, int(row["cell_count"]))
                    cell_width = float(row_box["width"]) / cell_count
                    font_size = min(10.0, max(6.0, float(row_box["height"]) * 0.72))
                    drawing.setFont("Helvetica", font_size)
                    baseline = (height - float(row_box["y"]) - float(row_box["height"])
                                + max(1.0, (float(row_box["height"]) - font_size) / 2))
                    for index in range(cell_count):
                        if offset >= len(value):
                            break
                        character = value[offset]
                        offset += 1
                        if character.isspace():
                            continue
                        center_x = float(row_box["x"]) + (index + 0.5) * cell_width
                        drawing.drawCentredString(center_x, baseline, character)
                placed.append(field.id)
            drawing.save()
            overlay_page = PdfReader(str(overlay_path), strict=False).pages[0]
            page.merge_page(overlay_page)
        finally:
            Path(temp_name).unlink(missing_ok=True)
    return placed


def _fit_text_appearances(writer: PdfWriter, text_values: dict[str, str]) -> None:
    """Set a readable default appearance that keeps values inside each widget."""
    for page in writer.pages:
        for reference in page.get("/Annots", []):
            annotation = reference.get_object()
            name = str(annotation.get("/T", ""))
            value = text_values.get(name)
            rect = annotation.get("/Rect")
            if value is None or not rect or len(rect) != 4:
                continue
            width = max(4.0, float(rect[2]) - float(rect[0]) - 6.0)
            # Helvetica is approximately 0.52 em per character. Keep the
            # existing 7 pt appearance for normal answers and shrink only when
            # the value would otherwise be clipped by the widget width.
            font_size = min(7.0, max(4.0, width / max(1.0, len(value) * 0.52)))
            annotation[NameObject("/DA")] = TextStringObject(
                f"/Helv {font_size:.2f} Tf 0 g"
            )


def fill_editable(template_path: Path, output_path: Path, fields: list[FieldSpec], values: dict[str, Any]) -> dict[str, Any]:
    reader = PdfReader(str(template_path), strict=False)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    profile = _profile_lookup(fields)
    text_values: dict[str, str] = {}
    character_values: dict[str, Any] = {}
    choices: dict[str, Any] = {}
    image_values: dict[str, Any] = {}
    for field_id, value in values.items():
        field = profile.get(field_id)
        if field is None:
            raise KeyError(f"unknown logical field: {field_id}")
        if field.kind == "choice":
            choices[field_id] = value
        elif field.kind in {"image", "signature"}:
            image_values[field_id] = value
        elif field.input_mode == "character-grid":
            character_values[field_id] = value
        elif field.kind == "composite" and field.options and isinstance(value, dict):
            for suffix, part in value.items():
                text_values[f"{field_id}_{suffix}"] = str(part)
        else:
            text_values[field_id] = str(value)

    if text_values:
        _fit_text_appearances(writer, text_values)
        writer.update_page_form_field_values(None, text_values, auto_regenerate=True)
    matched_choices = [field_id for field_id, value in choices.items()
                       if _set_choice(writer, profile[field_id], value)]
    placed_character_grids = _character_grid_overlay(writer, fields, character_values)
    placed_images = _image_overlay(writer, fields, image_values)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="pdf-field-fill-", suffix=".pdf", dir=output_path.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        with temp_path.open("wb") as handle:
            writer.write(handle)
        temp_path.replace(output_path)
    finally:
        temp_path.unlink(missing_ok=True)
    reopened = PdfReader(str(output_path), strict=False)
    return {
        "output": str(output_path),
        "text_fields_filled": sorted(text_values),
        "character_grid_fields_filled": sorted(placed_character_grids),
        "choice_fields_matched": sorted(matched_choices),
        "image_or_signature_regions_placed": sorted(placed_images),
        "reopen_pages": len(reopened.pages),
        "reopen_native_fields": len(reopened.get_fields() or {}),
    }


def load_values(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("fill data must be a JSON object keyed by logical field ID")
    return data
