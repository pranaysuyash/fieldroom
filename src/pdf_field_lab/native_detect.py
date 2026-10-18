"""Turn native PDF widgets into the same browser target contract."""

from __future__ import annotations

from .models import BBox, Evidence, FieldSpec, PdfInspection


def detect_native_targets(inspection: PdfInspection) -> list[FieldSpec]:
    """Preserve native field names and annotation geometry for editing."""
    targets: list[FieldSpec] = []
    field_info: dict[str, dict] = {}
    for item in inspection.native_fields:
        full_name = str(item.get("name") or "")
        if full_name:
            field_info[full_name] = item
        short_name = str(item.get("/T") or item.get("T") or "")
        if short_name and short_name not in field_info:
            field_info[short_name] = item

    seen_ids: dict[str, int] = {}
    for index, annotation in enumerate(inspection.annotations):
        if annotation.get("subtype") != "/Widget":
            continue
        base_name = str(annotation.get("name") or f"native-{index:04d}")
        leaf_name = base_name.rsplit(".", 1)[-1]
        rect = annotation.get("rect") or []
        page = int(annotation.get("page", 1))
        if len(rect) != 4 or page > len(inspection.page_sizes):
            continue
        page_height = inspection.page_sizes[page - 1]["height"]
        x0, y0, x1, y1 = rect
        bbox = BBox(float(x0), page_height - float(y1), float(x1 - x0), float(y1 - y0))
        info = field_info.get(base_name) or field_info.get(leaf_name) or {}
        field_type = str(annotation.get("field_type") or info.get("/FT") or info.get("FT") or "")
        flags = int(annotation.get("flags") or info.get("/Ff") or info.get("Ff") or 0)
        options = annotation.get("options") or info.get("/Opt") or info.get("Opt") or []
        alt_label = str(annotation.get("alternate_name") or info.get("/TU") or info.get("TU") or "").strip()
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
            for option in options:
                if isinstance(option, (list, tuple)) and len(option) >= 2:
                    normalized_options.append({"value": str(option[0]), "label": str(option[1])})
                else:
                    normalized_options.append({"value": str(option), "label": str(option)})

        count = seen_ids.get(base_name, 0) + 1
        seen_ids[base_name] = count
        target_id = base_name if count == 1 else f"{base_name}-{count}"
        label = alt_label or base_name
        targets.append(FieldSpec(
            id=target_id, page=page, label=label, kind=kind, bbox=bbox,
            editable_strategy=strategy, review_required=False, confidence=0.99,
            options=normalized_options,
            evidence=[Evidence("native", 0.99, "native PDF widget annotation")],
            notes=[f"Browser component: {component}. Native field semantics preserved."],
        ))
    return targets
