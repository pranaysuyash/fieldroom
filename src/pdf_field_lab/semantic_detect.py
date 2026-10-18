"""Generic semantic target detection for browser-first PDF editing.

The detector is intentionally evidence-led. It combines nearby text with
geometry, then emits a reviewable target. It does not silently convert every
line or table cell into a high-confidence field.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pdfplumber

from .models import BBox, Evidence, FieldSpec
from .label_ner import extract_label_entities


_NORMALIZE = re.compile(r"[^\w]+", re.UNICODE)
_ENUM_PREFIX = re.compile(r"^(?:\*?\s*\([0-9a-zA-Z]+\)\s*)+|^[0-9]+[.)]\s*")
_PAREN_QUALIFIER = re.compile(r"\([^)]*\)")
_UNDERSCORE_RUN = re.compile(r"_{4,}")
_IMAGE_WORDS = ("photo", "photograph", "passport photo", "upload image", "paste photo", "pasting", "logo", "picture")
_SIGNATURE_WORDS = ("signature", "sign here", "signed", "applicant sign", "authorised sign")
_DATE_WORDS = ("date", "dob", "birth")
_CHOICE_WORDS = (
    "select", "choose", "gender", "sex", "male", "female", "yes", "no", "category",
    "agree", "accept", "subscribe", "check", "option",
)
_TEXTAREA_WORDS = ("address", "comments", "remarks", "description", "reason", "details", "additional information", "notes")
_FIELD_CUE_WORDS = {
    "name", "surname", "middle", "first", "address", "number", "no", "email", "phone",
    "mobile", "id", "account", "contact", "place", "description", "signature", "sign",
    "photo", "date", "dob", "birth", "month", "year", "select", "choose", "gender",
    "sex", "male", "female", "yes", "no", "agree", "accept", "subscribe", "check",
    "photograph", "logo", "picture", "comments", "remarks", "reason", "details",
    "additional", "notes", "aadhaar", "pan", "passport", "license", "certificate",
    "epic", "constituency", "district", "state", "ut", "village", "town", "tehsil",
    "taluqa", "mandal", "pin", "code", "house", "apartment", "street", "locality",
    "father", "mother", "husband", "wife", "guardian", "disability", "locomotive",
    "visual", "deaf", "dumb", "relationship",
}


def _clean(value: str) -> str:
    return _NORMALIZE.sub(" ", value.lower()).strip()


def classify_label(label: str, *, region: BBox, page_height: float) -> tuple[str, float, str]:
    text = _clean(label)
    tokens = text.split()
    if any(word in text for word in _IMAGE_WORDS):
        return "image", 0.9, "nearby label contains an image/photo cue"
    if any(word in text for word in _SIGNATURE_WORDS):
        return "signature", 0.92, "nearby label contains a signature cue"
    if any(word in tokens for word in _DATE_WORDS) and not any(
        loc in tokens for loc in ("place", "village", "town", "district", "state", "certificate")
    ):
        return "date", 0.78, "nearby label contains a date cue"
    # Match whole tokens so the short cue "no" cannot classify "notes" or
    # "notice" as a choice field.
    if any(word in tokens for word in _CHOICE_WORDS if word != "no"):
        return "choice", 0.7, "nearby label contains a choice cue"
    if (region.height >= 36 and any(word in text for word in _TEXTAREA_WORDS)):
        return "textarea", 0.72, "nearby label and tall region suggest multiline text"
    return "text", 0.5 if label else 0.28, "text rule or rectangle needs label review"


def _word_lines(words: list[dict]) -> list[list[dict]]:
    """Group extracted words into the visual lines a reader sees."""
    heights = [float(word["bottom"] - word["top"]) for word in words]
    median_height = sorted(heights)[len(heights) // 2] if heights else 0.0
    # OCR coordinates are pixels, so a fixed four-pixel tolerance becomes too
    # strict as the render DPI rises. Keep vector extraction behavior stable,
    # while allowing adjacent OCR words from one baseline to stay together.
    line_tolerance = max(4.0, min(8.0, median_height * 0.45))
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda item: (item["top"], item["x0"])):
        matching = next((line for line in lines
                         if abs(word["top"] - line[0]["top"]) <= line_tolerance), None)
        if matching is None:
            lines.append([word])
        else:
            matching.append(word)
    return [sorted(line, key=lambda item: item["x0"]) for line in lines]


def _split_line_segments(line: list[dict], max_gap: float) -> list[list[dict]]:
    if not line:
        return []
    segments: list[list[dict]] = [[line[0]]]
    for word in line[1:]:
        prev = segments[-1][-1]
        if float(word["x0"]) - float(prev["x1"]) > max_gap:
            segments.append([word])
        else:
            segments[-1].append(word)
    return segments


def _nearby_label(words: list[dict], region: BBox) -> str:
    # Prefer a complete authored line immediately to the left, right (for
    # checkboxes), or above. Split wide horizontal gaps so side-by-side form
    # columns do not merge into a single overlong line.
    raw_lines = _word_lines(words)
    heights = [float(word["bottom"] - word["top"]) for word in words]
    median_height = sorted(heights)[len(heights) // 2] if heights else 0.0
    coordinate_scale = max(1.0, min(3.0, median_height / 11.0))
    lines: list[list[dict]] = []
    for raw_line in raw_lines:
        lines.extend(_split_line_segments(raw_line, max_gap=24.0 * coordinate_scale))

    is_checkbox = (
        region.width <= 32 * coordinate_scale
        and region.height <= 32 * coordinate_scale
        and abs(region.width - region.height) <= 6 * coordinate_scale
    )

    left: list[tuple[float, list[dict]]] = []
    right: list[tuple[float, list[dict]]] = []
    above: list[tuple[float, list[dict]]] = []
    for line in lines:
        line_x0 = line[0]["x0"]
        line_x1 = line[-1]["x1"]
        line_top = min(word["top"] for word in line)
        line_bottom = max(word["bottom"] for word in line)
        vertical_gap = max(region.y - line_bottom,
                           line_top - (region.y + region.height), 0)
        left_aligned = (line_bottom >= region.y - 8 * coordinate_scale
                        and line_top <= region.y + region.height + 8 * coordinate_scale)
        if (left_aligned and line_x1 <= region.x + 5 * coordinate_scale
                and line_x1 >= max(0, region.x - 280 * coordinate_scale)
                and vertical_gap <= 32 * coordinate_scale):
            left.append((vertical_gap + abs(line_x1 - region.x) * 0.08, line))

        if (is_checkbox and left_aligned
                and region.x + region.width - 3 * coordinate_scale <= line_x0 <= region.x + region.width + 24 * coordinate_scale):
            trimmed: list[dict] = []
            for word in line:
                if str(word["text"]).lower() == "or" and trimmed:
                    break
                trimmed.append(word)
                if len(trimmed) >= 5:
                    break
            if trimmed:
                right.append((abs(line_x0 - (region.x + region.width)) * 0.08 + vertical_gap, trimmed))

        horizontal_gap = max(region.x - line_x1,
                             line_x0 - (region.x + region.width), 0)
        if (line_bottom <= region.y + 4 * coordinate_scale
                and vertical_gap <= 48 * coordinate_scale
                and horizontal_gap <= 120 * coordinate_scale):
            above.append((vertical_gap + horizontal_gap * 0.08, line))

    if is_checkbox and right:
        _, selected = min(right, key=lambda item: item[0])
        return " ".join(word["text"] for word in selected)
    candidates = left or right or above
    if not candidates:
        return ""
    _, selected = min(candidates, key=lambda item: item[0])
    return " ".join(word["text"] for word in selected)


def _label_is_form_like(label: str) -> bool:
    """Reject coherent prose before it can become a semantic field label."""
    raw = _ENUM_PREFIX.sub("", label.strip()).strip()
    raw_no_parens = _PAREN_QUALIFIER.sub(" ", raw).strip()
    text = _clean(raw_no_parens)
    tokens = text.split()
    if not tokens:
        text = _clean(raw)
        tokens = text.split()
    if not tokens or len(tokens) > 9:
        return False
    if raw.endswith(".") and not raw.lower().endswith(("no.", "sr.", "dr.", "mr.", "ms.", "st.")):
        return False
    if len(tokens) <= 7 and (raw.rstrip().endswith(":") or ":-" in raw):
        return True
    if len(tokens) <= 2:
        return True
    phrase_words = _FIELD_CUE_WORDS | {
        "of", "or", "to", "and", "in", "by", "for", "self", "any", "other",
        "applicant", "relative", "family", "member", "official", "language",
        "english", "block", "letters", "followed", "specify", "full", "post", "office",
    }
    return len(tokens) <= 6 and all(token in phrase_words for token in tokens)


def _has_explicit_field_cue(label: str) -> bool:
    """Require a compact, field-like phrase before geometry becomes a target."""
    return _label_is_form_like(label) and bool(_FIELD_CUE_WORDS.intersection(_clean(label).split()))


def _is_grid_like(region: BBox, regions: list[BBox]) -> bool:
    """Recognize repeated row-and-column geometry as table structure."""
    row_peers = sum(
        1 for other in regions
        if other is not region
        and abs(other.y - region.y) <= 6
        and other.width >= 24
    )
    column_peers = sum(
        1 for other in regions
        if other is not region
        and abs(other.x - region.x) <= 6
        and other.height <= max(4, region.height + 2)
    )
    return row_peers >= 1 and column_peers >= 1


def _reconstruct_raw_boxes(rects: list[dict], tol: float = 2.5) -> list[BBox]:
    """Reconstruct closed boxes drawn as 4 thin border segments (top, bottom, left, right)."""
    horiz: list[tuple[float, float, float, float]] = []
    vert: list[tuple[float, float, float, float]] = []
    for r in rects:
        x0, top, x1, bottom = float(r["x0"]), float(r["top"]), float(r["x1"]), float(r["bottom"])
        w = x1 - x0
        h = bottom - top
        if w >= 6.0 and h <= 3.0:
            horiz.append((x0, top, x1, bottom))
        elif h >= 6.0 and w <= 3.0:
            vert.append((x0, top, x1, bottom))
    boxes: list[BBox] = []
    horiz.sort(key=lambda item: (item[1], item[0]))
    for i, (tx0, ttop, tx1, tbot) in enumerate(horiz):
        for bx0, btop, bx1, bbot in horiz[i + 1 :]:
            box_h = bbot - ttop
            if box_h < 6.0:
                continue
            if box_h > 240.0:
                break
            if abs(tx0 - bx0) <= tol and abs(tx1 - bx1) <= tol:
                has_left = any(
                    abs(vx0 - tx0) <= tol and vtop <= tbot + tol and vbot >= btop - tol
                    for vx0, vtop, _, vbot in vert
                )
                has_right = any(
                    abs(vx1 - tx1) <= tol and vtop <= tbot + tol and vbot >= btop - tol
                    for _, vtop, vx1, vbot in vert
                )
                if has_left and has_right:
                    boxes.append(
                        BBox(
                            round(min(tx0, bx0), 3),
                            round(ttop, 3),
                            round(max(tx1, bx1) - min(tx0, bx0), 3),
                            round(box_h, 3),
                        )
                    )
                    break
    return boxes


def _reconstruct_collinear_boxes(rects: list[dict], tol: float = 2.5) -> list[BBox]:
    """Merge collinear vertical/horizontal border segments to recover multi-row frames (e.g. photo box)."""
    horiz_raw: list[tuple[float, float, float, float]] = []
    vert_raw: list[tuple[float, float, float, float]] = []
    for r in rects:
        x0, top, x1, bottom = float(r["x0"]), float(r["top"]), float(r["x1"]), float(r["bottom"])
        w = x1 - x0
        h = bottom - top
        if w >= 4.0 and h <= 3.0:
            horiz_raw.append((x0, top, x1, bottom))
        elif h >= 4.0 and w <= 3.0:
            vert_raw.append((x0, top, x1, bottom))

    horiz_raw.sort(key=lambda s: (round(s[1], 1), s[0]))
    horiz: list[tuple[float, float, float, float]] = []
    for seg in horiz_raw:
        if horiz and abs(seg[1] - horiz[-1][1]) <= 2.0 and seg[0] <= horiz[-1][2] + 2.0:
            prev = horiz[-1]
            horiz[-1] = (min(prev[0], seg[0]), min(prev[1], seg[1]), max(prev[2], seg[2]), max(prev[3], seg[3]))
        else:
            horiz.append(seg)

    vert_raw.sort(key=lambda s: (round(s[0], 1), s[1]))
    vert: list[tuple[float, float, float, float]] = []
    for seg in vert_raw:
        if vert and abs(seg[0] - vert[-1][0]) <= 2.0 and seg[1] <= vert[-1][3] + 2.0:
            prev = vert[-1]
            vert[-1] = (min(prev[0], seg[0]), min(prev[1], seg[1]), max(prev[2], seg[2]), max(prev[3], seg[3]))
        else:
            vert.append(seg)

    boxes: list[BBox] = []
    horiz.sort(key=lambda item: (item[1], item[0]))
    for i, (tx0, ttop, tx1, tbot) in enumerate(horiz):
        for bx0, btop, bx1, bbot in horiz[i + 1 :]:
            box_h = bbot - ttop
            if box_h < 40.0:
                continue
            if box_h > 240.0:
                break
            if abs(tx0 - bx0) <= tol and abs(tx1 - bx1) <= tol:
                has_left = any(
                    abs(vx0 - tx0) <= tol and vtop <= tbot + tol and vbot >= btop - tol
                    for vx0, vtop, _, vbot in vert
                )
                has_right = any(
                    abs(vx1 - tx1) <= tol and vtop <= tbot + tol and vbot >= btop - tol
                    for _, vtop, vx1, vbot in vert
                )
                if has_left and has_right:
                    boxes.append(
                        BBox(
                            round(min(tx0, bx0), 3),
                            round(ttop, 3),
                            round(max(tx1, bx1) - min(tx0, bx0), 3),
                            round(box_h, 3),
                        )
                    )
                    break
    return boxes


def _cluster_character_grids(boxes: list[BBox]) -> tuple[list[BBox], set[int]]:
    """Group horizontal runs of >=5 adjacent character cells into a single comb-grid BBox."""
    cell_indices = [
        idx for idx, b in enumerate(boxes)
        if 10.0 <= b.width <= 26.0 and 10.0 <= b.height <= 22.0
    ]
    by_row: dict[int, list[tuple[int, BBox]]] = {}
    for idx in cell_indices:
        b = boxes[idx]
        row_key = next((rk for rk in by_row if abs(rk - round(b.y)) <= 2), round(b.y))
        by_row.setdefault(row_key, []).append((idx, b))

    grid_bboxes: list[BBox] = []
    used_indices: set[int] = set()
    for _, row_items in sorted(by_row.items()):
        row_items.sort(key=lambda item: item[1].x)
        runs: list[list[tuple[int, BBox]]] = []
        for idx, b in row_items:
            if not runs:
                runs.append([(idx, b)])
                continue
            prev_b = runs[-1][-1][1]
            gap = b.x - (prev_b.x + prev_b.width)
            if -3.0 <= gap <= 4.0 and abs(b.height - prev_b.height) <= 2.5:
                runs[-1].append((idx, b))
            else:
                runs.append([(idx, b)])
        for run in runs:
            if len(run) >= 5:
                for idx, _ in run:
                    used_indices.add(idx)
                x0 = min(b.x for _, b in run)
                y0 = min(b.y for _, b in run)
                x1 = max(b.x + b.width for _, b in run)
                y1 = max(b.y + b.height for _, b in run)
                grid_bboxes.append(BBox(round(x0, 3), round(y0, 3), round(x1 - x0, 3), round(y1 - y0, 3)))
    return grid_bboxes, used_indices


def _normalize_page_rotation(
    words: list[dict], rects: list[dict], lines: list[dict], rot: int, page_w: float, page_h: float
) -> tuple[list[dict], list[dict], list[dict], float, float]:
    """Unrotate extracted primitives into upright coordinates when a page carries /Rotate."""
    rot = rot % 360
    if rot == 0:
        return words, rects, lines, page_w, page_h

    def _map_box(x0: float, top: float, x1: float, bottom: float) -> tuple[float, float, float, float]:
        if rot == 90:
            return top, page_w - x1, bottom, page_w - x0
        if rot == 180:
            return page_w - x1, page_h - bottom, page_w - x0, page_h - top
        if rot == 270:
            return page_h - bottom, x0, page_h - top, x1
        return x0, top, x1, bottom

    new_words: list[dict] = []
    for w in words:
        nx0, ntop, nx1, nbot = _map_box(float(w["x0"]), float(w["top"]), float(w["x1"]), float(w["bottom"]))
        txt = str(w["text"])
        if rot == 180 and len(txt) > 1 and not txt.isupper():
            txt = txt[::-1]
        new_words.append({**w, "text": txt, "x0": nx0, "top": ntop, "x1": nx1, "bottom": nbot})

    new_rects: list[dict] = []
    for r in rects:
        nx0, ntop, nx1, nbot = _map_box(float(r["x0"]), float(r["top"]), float(r["x1"]), float(r["bottom"]))
        new_rects.append({**r, "x0": nx0, "top": ntop, "x1": nx1, "bottom": nbot})

    new_lines: list[dict] = []
    for ln in lines:
        nx0, ntop, nx1, nbot = _map_box(
            float(min(ln["x0"], ln["x1"])),
            float(min(ln["top"], ln["bottom"])),
            float(max(ln["x0"], ln["x1"])),
            float(max(ln["top"], ln["bottom"])),
        )
        new_lines.append({**ln, "x0": nx0, "top": ntop, "x1": nx1, "bottom": nbot})

    if rot in (90, 270):
        return new_words, new_rects, new_lines, page_h, page_w
    return new_words, new_rects, new_lines, page_w, page_h


def _map_bbox_to_rotated(bbox: BBox, rot: int, upright_w: float, upright_h: float) -> BBox:
    rot = rot % 360
    if rot == 0:
        return bbox
    x0, top, x1, bottom = bbox.x, bbox.y, bbox.x + bbox.width, bbox.y + bbox.height
    if rot == 90:
        rx0, rtop, rx1, rbot = upright_h - bottom, x0, upright_h - top, x1
    elif rot == 180:
        rx0, rtop, rx1, rbot = upright_w - x1, upright_h - bottom, upright_w - x0, upright_h - top
    elif rot == 270:
        rx0, rtop, rx1, rbot = top, upright_w - x1, bottom, upright_w - x0
    else:
        return bbox
    return BBox(round(rx0, 3), round(rtop, 3), round(rx1 - rx0, 3), round(rbot - rtop, 3))


def _target(page_number: int, index: int, region: BBox, label: str,
            page_height: float, detail: str, model: Any | None = None) -> FieldSpec:
    # The review manifest requires a usable four-point hit area. Preserve thin
    # visual lines while normalizing their interactive height at this boundary.
    region = BBox(region.x, region.y, max(4.0, region.width), max(4.0, region.height))
    kind, score, semantic_detail = classify_label(label, region=region, page_height=page_height)
    if kind in {"image", "signature"}:
        strategy = "visual-overlay-image"
    elif kind == "choice":
        strategy = "acroform-checkbox"
    else:
        strategy = "acroform-text"
    evidence = [Evidence("vector", score, f"{detail}; {semantic_detail}")]
    notes = ["Generic detection; confirm or adjust this target before final submission."]
    if model is not None:
        from .target_model import model_evidence
        predicted, model_score = model_evidence(model, FieldSpec(
            id="model-probe", page=page_number, label=label, kind=kind,
            bbox=region, editable_strategy=strategy))
        evidence.append(Evidence("model", model_score,
                                 f"advisory target classifier predicts {predicted}"))
        notes.append("Model output is advisory evidence trained from proxy labels; it does not override geometry or review.")
    return FieldSpec(
        id=f"target-{page_number}-{index:04d}", page=page_number,
        label=label or "Unlabeled field", kind=kind, bbox=region,
        # Confidence ranks an inferred proposal but never creates a human
        # acceptance event. Native widgets are the only non-pending lane.
        editable_strategy=strategy, review_required=True,
        confidence=score,
        label_entities=extract_label_entities(label),
        evidence=evidence,
        notes=notes,
    )


def _dedupe(candidates: Iterable[FieldSpec]) -> list[FieldSpec]:
    seen: set[tuple[int, int, int, int, str]] = set()
    result: list[FieldSpec] = []
    for candidate in candidates:
        key = (candidate.page, round(candidate.bbox.x), round(candidate.bbox.y),
               round(candidate.bbox.width), candidate.kind)
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def detect_semantic_targets(
    path: Path,
    *,
    model: Any | None = None,
    warnings_out: list[str] | None = None,
) -> list[FieldSpec]:
    """Detect a conservative, generic target set from text and vector geometry."""
    targets: list[FieldSpec] = []
    page_rotations: dict[int, int] = {}
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path), strict=False)
        for pno, p_obj in enumerate(reader.pages, 1):
            page_rotations[pno] = int(p_obj.get("/Rotate", 0) or 0) % 360
    except Exception:
        pass

    with pdfplumber.open(str(path)) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            try:
                rot = page_rotations.get(page_number, 0)
                raw_words = page.extract_words() or []
                words, page_rects, page_lines, page_width, page_height = _normalize_page_rotation(
                    raw_words, list(page.rects), list(page.lines), rot, float(page.width), float(page.height)
                )
                index = 0
                geometry_regions: list[BBox] = []
                all_geometry_regions: list[BBox] = []
                for rect in page_rects:
                    width = float(rect["x1"] - rect["x0"])
                    height = float(rect["bottom"] - rect["top"])
                    is_checkbox = 7 <= width <= 32 and 7 <= height <= 32 and abs(width - height) <= 4
                    is_line = width >= 24 and height <= 2.0
                    is_large = width >= 55 and height >= 20 and width / max(height, 1) < 18.0
                    if is_checkbox or is_line or is_large:
                        all_geometry_regions.append(BBox(round(float(rect["x0"]), 3),
                                                          round(float(rect["top"]), 3),
                                                          round(width, 3), round(height, 3)))
                for line in page_lines:
                    width = abs(float(line["x1"] - line["x0"]))
                    height = abs(float(line["bottom"] - line["top"]))
                    if width >= 24 and height <= 3.0:
                        all_geometry_regions.append(BBox(
                            round(float(min(line["x0"], line["x1"])), 3),
                            round(float(line["top"] - max(1.0, line.get("linewidth", 1.0))), 3),
                            round(width, 3),
                            round(max(3.0, line.get("linewidth", 1.0) * 2), 3),
                        ))
                for rect in page_rects:
                    width = float(rect["x1"] - rect["x0"])
                    height = float(rect["bottom"] - rect["top"])
                    if not (7 <= width <= 32 and 7 <= height <= 32 and abs(width - height) <= 4):
                        if not (width >= 24 and height <= 2.0):
                            if not (width >= 55 and height >= 20 and width / max(height, 1) < 18.0):
                                continue
                    region = BBox(round(float(rect["x0"]), 3), round(float(rect["top"]), 3),
                                  round(width, 3), round(height, 3))
                    geometry_regions.append(region)
                    label = _nearby_label(words, region)
                    if not _has_explicit_field_cue(label):
                        continue
                    if not label.rstrip().endswith(":") and _is_grid_like(region, all_geometry_regions):
                        continue
                    if width <= 32 and height <= 32:
                        detail = "near-square rectangle"
                    elif height <= 2.0:
                        detail = "long thin rectangle"
                    else:
                        detail = "large rectangle"
                    mapped_reg = _map_bbox_to_rotated(region, rot, page_width, page_height)
                    targets.append(_target(page_number, index, mapped_reg, label, page_height, detail, model))
                    index += 1
                # Lines and underlines are common entry affordances. Convert them
                # to a small review region so label association can be evaluated.
                for line in page_lines:
                    width = abs(float(line["x1"] - line["x0"]))
                    height = abs(float(line["bottom"] - line["top"]))
                    if width < 24 or height > 3.0:
                        continue
                    region = BBox(round(float(min(line["x0"], line["x1"])), 3),
                                  round(float(line["top"] - max(1.0, line.get("linewidth", 1.0))), 3),
                                  round(width, 3), round(max(3.0, line.get("linewidth", 1.0) * 2), 3))
                    geometry_regions.append(region)
                    label = _nearby_label(words, region)
                    if not _has_explicit_field_cue(label):
                        continue
                    if not label.rstrip().endswith(":") and _is_grid_like(region, all_geometry_regions):
                        continue
                    mapped_reg = _map_bbox_to_rotated(region, rot, page_width, page_height)
                    targets.append(_target(page_number, index, mapped_reg, label, page_height,
                                           "long thin vector line", model))
                    index += 1

                # Reconstruct 4-border boxes and character comb-grids when forms draw
                # borders as thin hairline rectangles rather than closed PDF rects.
                raw_boxes = _reconstruct_raw_boxes(page_rects)
                comb_grids, used_raw_indices = _cluster_character_grids(raw_boxes)
                non_grid_boxes = [b for i, b in enumerate(raw_boxes) if i not in used_raw_indices]
                collinear_boxes = _reconstruct_collinear_boxes(page_rects)

                for grid_box in comb_grids:
                    geometry_regions.append(grid_box)
                    label = _nearby_label(words, grid_box)
                    if not _has_explicit_field_cue(label):
                        continue
                    mapped_reg = _map_bbox_to_rotated(grid_box, rot, page_width, page_height)
                    targets.append(_target(page_number, index, mapped_reg, label, page_height,
                                           "reconstructed character comb-grid", model))
                    index += 1

                for cbox in non_grid_boxes:
                    if 7 <= cbox.width <= 32 and 7 <= cbox.height <= 32 and abs(cbox.width - cbox.height) <= 6:
                        geometry_regions.append(cbox)
                        label = _nearby_label(words, cbox)
                        if not _has_explicit_field_cue(label):
                            continue
                        mapped_reg = _map_bbox_to_rotated(cbox, rot, page_width, page_height)
                        cand = _target(page_number, index, mapped_reg, label, page_height,
                                       "reconstructed 4-border checkbox", model)
                        cand.kind = "choice"
                        cand.editable_strategy = "acroform-checkbox"
                        targets.append(cand)
                        index += 1

                for frame_box in collinear_boxes:
                    if 55 <= frame_box.width <= 220 and 55 <= frame_box.height <= 220:
                        inside_words = [
                            w["text"] for w in words
                            if w["x0"] >= frame_box.x - 4 and w["x1"] <= frame_box.x + frame_box.width + 4
                            and w["top"] >= frame_box.y - 4 and w["bottom"] <= frame_box.y + frame_box.height + 4
                        ]
                        inside_text = _clean(" ".join(inside_words))
                        if any(cue in inside_text for cue in ("photograph", "passport photo", "paste photo", "pasting")):
                            geometry_regions.append(frame_box)
                            lbl = " ".join(inside_words[:6])
                            mapped_reg = _map_bbox_to_rotated(frame_box, rot, page_width, page_height)
                            cand = _target(page_number, index, mapped_reg, lbl, page_height,
                                           "segmented photo box", model)
                            cand.kind = "image"
                            cand.editable_strategy = "visual-overlay-image"
                            targets.append(cand)
                            index += 1

                # Inline underscore blanks ('Date:_______', 'Village/Town_______', etc.)
                for line in _word_lines(words):
                    for w_idx, w in enumerate(line):
                        txt = str(w["text"])
                        m = _UNDERSCORE_RUN.search(txt)
                        if not m:
                            continue
                        x0, top, x1, bottom = float(w["x0"]), float(w["top"]), float(w["x1"]), float(w["bottom"])
                        total_len = max(1, len(txt))
                        blank_x0 = x0 + (x1 - x0) * (m.start() / total_len)
                        blank_w = max(24.0, (x1 - x0) * ((m.end() - m.start()) / total_len))
                        prefix = txt[: m.start()].strip()
                        preceding: list[str] = []
                        for pw in line[:w_idx]:
                            if _UNDERSCORE_RUN.search(str(pw["text"])):
                                preceding = []
                                continue
                            if float(w["x0"]) - float(pw["x1"]) <= 180.0:
                                preceding.append(str(pw["text"]))
                        if prefix:
                            preceding.append(prefix)
                        label = " ".join(preceding[-6:]).strip()
                        if not _has_explicit_field_cue(label):
                            continue
                        region = BBox(round(blank_x0, 3), round(top, 3), round(blank_w, 3),
                                      round(max(4.0, bottom - top), 3))
                        geometry_regions.append(region)
                        mapped_reg = _map_bbox_to_rotated(region, rot, page_width, page_height)
                        targets.append(_target(page_number, index, mapped_reg, label, page_height,
                                               "inline underscore blank", model))
                        index += 1

                # A short, colon-terminated field label can identify an empty
                # whitespace region when the source PDF has no drawn border.
                for word in words:
                    if _UNDERSCORE_RUN.search(str(word["text"])):
                        continue
                    line_words = [candidate for candidate in words
                                  if candidate["x0"] <= word["x1"]
                                  and candidate["x1"] >= max(0, word["x0"] - 190)
                                  and abs(candidate["top"] - word["top"]) <= 4
                                  and not _UNDERSCORE_RUN.search(str(candidate["text"]))]
                    line_words.sort(key=lambda candidate: candidate["x0"])
                    label = " ".join(candidate["text"] for candidate in line_words)
                    if not str(word["text"]).endswith(":") or not _has_explicit_field_cue(label):
                        continue
                    same_line = [candidate for candidate in words
                                 if candidate["x0"] >= word["x1"]
                                 and candidate["top"] <= word["bottom"] + 4
                                 and candidate["bottom"] >= word["top"] - 4]
                    if any(candidate["x0"] - word["x1"] < 120 for candidate in same_line):
                        continue
                    def geometry_near_label(region: BBox) -> bool:
                        if region.x + region.width < word["x0"]:
                            horizontal_gap = word["x0"] - (region.x + region.width)
                        elif word["x1"] < region.x:
                            horizontal_gap = region.x - word["x1"]
                        else:
                            horizontal_gap = 0.0
                        vertical_gap = max(region.y - word["bottom"],
                                           word["top"] - (region.y + region.height), 0)
                        return horizontal_gap <= 120 and vertical_gap <= 48

                    if any(geometry_near_label(region) for region in geometry_regions):
                        continue
                    region = BBox(round(float(word["x1"] + 8), 3),
                                  round(float(word["top"] - 2), 3), 220.0, 24.0)
                    if region.x + region.width > page_width:
                        region = BBox(region.x, region.y, max(24.0, page_width - region.x - 8), region.height)
                    if region.width < 24:
                        continue
                    mapped_reg = _map_bbox_to_rotated(region, rot, page_width, page_height)
                    if any(existing.page == page_number and
                           abs(existing.bbox.x - mapped_reg.x) < 12 and
                           abs(existing.bbox.y - mapped_reg.y) < 18 for existing in targets):
                        continue
                    targets.append(_target(page_number, index, mapped_reg, label, page_height,
                                           "field-like text label with trailing whitespace", model))
                    index += 1
            except Exception as exc:
                if warnings_out is not None:
                    warnings_out.append(
                        f"Semantic detection failed on page {page_number}: {type(exc).__name__}"
                    )
                continue
    return _dedupe(targets)
