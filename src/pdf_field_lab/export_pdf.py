"""Create a new PDF with editable AcroForm widgets over the original pages."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ArrayObject, BooleanObject, DictionaryObject,
                           NameObject, NumberObject, TextStringObject)

from .models import FieldSpec


def _is_native_strategy(strategy: str) -> bool:
    return strategy.startswith("native")


def _stream(writer: PdfWriter, content: bytes) -> Any:
    from pypdf.generic import DecodedStreamObject
    stream = DecodedStreamObject()
    stream.set_data(content)
    return writer._add_object(stream)


def _empty_appearance(writer: PdfWriter) -> DictionaryObject:
    return DictionaryObject({NameObject("/N"): _stream(writer, b"")})


def _check_appearance(writer: PdfWriter, width: float, height: float) -> DictionaryObject:
    # A small X is a viewer-independent normal appearance for checkbox/radio
    # widgets. It is only used when the user selects the widget later.
    y = max(2.0, height * 0.22)
    content = f"q 1 0 0 1 0 0 cm 1 w 2 {y} m {width-2} {height-y} l 2 {height-y} m {width-2} {y} l S Q".encode()
    yes = _stream(writer, content)
    off = _stream(writer, b"")
    return DictionaryObject({NameObject("/N"): DictionaryObject({
        NameObject("/Off"): off, NameObject("/Yes"): yes})})


def _widget(writer: PdfWriter, page_index: int, rect: list[float], name: str,
            field_type: str = "/Tx", *, parent: Any = None,
            appearance: DictionaryObject | None = None, flags: int | None = None) -> DictionaryObject:
    widget: dict[str, Any] = {
        "/Type": "/Annot", "/Subtype": "/Widget", "/Rect": rect,
        "/F": 4, "/FT": field_type, "/T": name, "/V": "",
        "/DA": "/Helv 7 Tf 0 g", "/Border": [0, 0, 0],
    }
    if parent is not None:
        widget.pop("/FT", None)
        widget.pop("/T", None)
        widget["/Parent"] = parent
    if flags is not None:
        widget["/Ff"] = flags
    if appearance is not None:
        widget["/AP"] = appearance
    return writer.add_annotation(page_index, widget)


def _add_text(writer: PdfWriter, acro_fields: ArrayObject, page_index: int,
              page_height: float, field: FieldSpec, name: str, rect: list[float], *, multiline: bool = False) -> None:
    widget = _widget(writer, page_index, rect, name, "/Tx", flags=4096 if multiline else None)
    acro_fields.append(widget.indirect_reference)


def _add_checkboxes(writer: PdfWriter, acro_fields: ArrayObject, page_index: int,
                    page_height: float, field: FieldSpec, name: str, radio: bool = False) -> None:
    options = field.options
    if not options:
        options = [{"value": "selected", "bbox": field.bbox.as_dict()}]
    if radio and len(options) > 1:
        parent = DictionaryObject({
            NameObject("/FT"): NameObject("/Btn"),
            NameObject("/Ff"): NumberObject(32768),
            NameObject("/T"): TextStringObject(name),
            NameObject("/V"): NameObject("/Off"),
            NameObject("/Kids"): ArrayObject(),
        })
        parent_ref = writer._add_object(parent)
        acro_fields.append(parent_ref)
        for index, option in enumerate(options):
            box = option["bbox"]
            x, y, w, h = box["x"], box["y"], box["width"], box["height"]
            rect = [x, page_height-y-h, x+w, page_height-y]
            appearance = _check_appearance(writer, w, h)
            widget = _widget(writer, page_index, rect, f"{name}_{index}", parent=parent_ref, appearance=appearance)
            widget[NameObject("/AS")] = NameObject("/Off")
            normal = widget[NameObject("/AP")][NameObject("/N")]
            # Each radio kid gets its own export name while the parent enforces
            # one-of-many selection.
            on_name = NameObject("/Yes")
            normal[on_name] = normal.pop(NameObject("/Yes"))
            parent[NameObject("/Kids")].append(widget.indirect_reference)
    else:
        for index, option in enumerate(options):
            box = option["bbox"]
            x, y, w, h = box["x"], box["y"], box["width"], box["height"]
            rect = [x, page_height-y-h, x+w, page_height-y]
            widget = _widget(writer, page_index, rect, f"{name}_{index}", "/Btn",
                             appearance=_check_appearance(writer, w, h))
            widget[NameObject("/AS")] = NameObject("/Off")
            widget[NameObject("/V")] = NameObject("/Off")
            acro_fields.append(widget.indirect_reference)


def _field_rects(field: FieldSpec) -> list[tuple[str, dict[str, float]]]:
    if field.kind == "composite" and field.options:
        return [(str(option["value"]), option["bbox"]) for option in field.options]
    return [(field.id, field.bbox.as_dict())]


def export_editable(input_path: Path, output_path: Path, fields: list[FieldSpec]) -> dict[str, Any]:
    reader = PdfReader(str(input_path), strict=False)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    # Native widgets already are editable. Preserve their original AcroForm
    # rather than replacing it with duplicate widgets at the same coordinates.
    native_only = bool(fields) and all(_is_native_strategy(field.editable_strategy) for field in fields)
    if native_only:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix="pdf-field-lab-", suffix=".pdf", dir=output_path.parent)
        os.close(fd)
        temp_path = Path(tmp_name)
        try:
            with temp_path.open("wb") as handle:
                writer.write(handle)
            temp_path.replace(output_path)
        finally:
            temp_path.unlink(missing_ok=True)
        reopened = PdfReader(str(output_path), strict=False)
        return {"output": str(output_path), "created_logical_fields": [field.id for field in fields],
                "reopen_pages": len(reopened.pages),
                "reopen_native_fields": len(reopened.get_fields() or {})}
    existing_acroform = writer._root_object.get(NameObject("/AcroForm"))
    if existing_acroform is not None:
        # Keep the cloned field tree, including inherited /FT, /Ff, /Opt,
        # parent/kid relationships, and existing widget appearances. Mixed
        # reconstruction is additive: inferred fields are appended below.
        acro_form = existing_acroform.get_object() if hasattr(existing_acroform, "get_object") else existing_acroform
        existing_fields = acro_form.get(NameObject("/Fields"), ArrayObject())
        acro_fields = existing_fields.get_object() if hasattr(existing_fields, "get_object") else existing_fields
        if not isinstance(acro_fields, ArrayObject):
            acro_fields = ArrayObject(acro_fields)
            acro_form[NameObject("/Fields")] = acro_fields
        acro_form[NameObject("/NeedAppearances")] = BooleanObject(True)
    else:
        acro_fields = ArrayObject()
        acro_form = DictionaryObject({
            NameObject("/Fields"): acro_fields,
            NameObject("/NeedAppearances"): BooleanObject(True),
            NameObject("/DA"): TextStringObject("/Helv 7 Tf 0 g"),
        })
        # Declare the standard Helvetica resource explicitly. Without /DR some
        # pypdf versions can still reopen the file but warn while regenerating
        # appearances because /Helv is not resolvable.
        helv = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        resources = DictionaryObject({
            NameObject("/Font"): DictionaryObject({
                NameObject("/Helv"): writer._add_object(helv),
            })
        })
        acro_form[NameObject("/DR")] = writer._add_object(resources)
        writer._root_object[NameObject("/AcroForm")] = writer._add_object(acro_form)

    created: list[str] = []
    for field in fields:
        page_index = field.page - 1
        page_height = float(writer.pages[page_index].mediabox.height)
        if field.kind in {"choice"}:
            _add_checkboxes(writer, acro_fields, page_index, page_height, field, field.id,
                            radio=field.editable_strategy == "acroform-radio")
            created.append(field.id)
            continue
        if field.kind == "image":
            # The image area itself is not a text widget. A text note makes the
            # empty target discoverable without pretending an image upload is a
            # native PDF field. The later image-placement adapter can replace it.
            _add_text(writer, acro_fields, page_index, page_height, field,
                      f"{field.id}_image_note", field.bbox.to_pdf_rect(page_height))
            created.append(field.id)
            continue
        if field.kind == "signature":
            _add_text(writer, acro_fields, page_index, page_height, field,
                      f"{field.id}_signature_note", field.bbox.to_pdf_rect(page_height))
            created.append(field.id)
            continue
        for suffix, box in _field_rects(field):
            rect = [box["x"], page_height-box["y"]-box["height"],
                    box["x"]+box["width"], page_height-box["y"]]
            widget_name = field.id if suffix == field.id else f"{field.id}_{suffix}"
            _add_text(writer, acro_fields, page_index, page_height, field,
                      widget_name, rect, multiline=field.kind == "textarea")
        created.append(field.id)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="pdf-field-lab-", suffix=".pdf", dir=output_path.parent)
    os.close(fd)
    temp_path = Path(tmp_name)
    try:
        with temp_path.open("wb") as handle:
            writer.write(handle)
        temp_path.replace(output_path)
    finally:
        temp_path.unlink(missing_ok=True)
    reopened = PdfReader(str(output_path), strict=False)
    return {"output": str(output_path), "created_logical_fields": created,
            "reopen_pages": len(reopened.pages),
            "reopen_native_fields": len(reopened.get_fields() or {})}
