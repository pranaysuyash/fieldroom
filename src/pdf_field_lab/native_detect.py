"""Turn native PDF widgets into the same browser target contract."""

from __future__ import annotations

from .models import BBox, Evidence, FieldSpec, PdfInspection


def detect_native_targets(inspection: PdfInspection) -> list[FieldSpec]:
    """Preserve native field names and annotation geometry for editing."""
    targets: list[FieldSpec] = []
    field_info = {str(item.get("name")): item for item in inspection.native_fields}
    for index, annotation in enumerate(inspection.annotations):
        if annotation.get("subtype") != "/Widget":
            continue
        name = str(annotation.get("name") or f"native-{index:04d}")
        rect = annotation.get("rect") or []
        page = int(annotation.get("page", 1))
        if len(rect) != 4 or page > len(inspection.page_sizes):
            continue
        page_height = inspection.page_sizes[page - 1]["height"]
        x0, y0, x1, y1 = rect
        bbox = BBox(float(x0), page_height - float(y1), float(x1 - x0), float(y1 - y0))
        info = field_info.get(name, {})
        field_type = str(info.get("/FT", info.get("FT", annotation.get("field_type", ""))))
        flags = int(info.get("/Ff", info.get("Ff", annotation.get("flags", 0))) or 0)
        options = info.get("/Opt", info.get("Opt", annotation.get("options"))) or []
        if field_type == "/Sig":
            kind = "signature"
            component = "signature-pad"
            strategy = "native-digital-signature"
        elif field_type == "/Btn":
            kind = "choice"
            component = "choice-group"
            strategy = "native-radio" if flags & 32768 else "native-checkbox"
        elif field_type == "/Ch":
            kind = "choice"
            component = "choice-group"
            strategy = "native-choice"
        else:
            kind = "textarea" if flags & 4096 else "text"
            component = "text-field"
            strategy = "native"
        normalized_options = []
        if isinstance(options, list):
            normalized_options = [{"value": str(option), "label": str(option)} for option in options]
        targets.append(FieldSpec(
            id=name, page=page, label=name, kind=kind, bbox=bbox,
            editable_strategy=strategy, review_required=False, confidence=0.99,
            options=normalized_options,
            evidence=[Evidence("native", 0.99, "native PDF widget annotation")],
            notes=[f"Browser component: {component}. Native field semantics preserved."],
        ))
    return targets
