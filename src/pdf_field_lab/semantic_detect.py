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
_IMAGE_WORDS = ("photo", "photograph", "passport photo", "upload image", "paste photo", "logo", "picture")
_SIGNATURE_WORDS = ("signature", "sign here", "signed", "applicant sign", "authorised sign")
_DATE_WORDS = ("date", "dob", "birth")
_CHOICE_WORDS = (
    "select", "choose", "gender", "sex", "male", "female", "yes", "no", "category",
    "agree", "accept", "subscribe", "check", "option",
)
_TEXTAREA_WORDS = ("address", "comments", "remarks", "description", "reason", "details", "additional information", "notes")
_FIELD_CUE_WORDS = {
    "name", "address", "number", "no", "email", "phone", "mobile", "id",
    "account", "contact", "place", "description", "signature", "sign", "photo",
    "date", "dob", "birth", "month", "year", "select", "choose", "gender",
    "sex", "male", "female", "yes", "no", "agree", "accept", "subscribe", "check",
    "photograph", "logo", "picture", "comments", "remarks", "reason", "details", "additional", "notes",
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
    if any(word in tokens for word in _DATE_WORDS):
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


def _nearby_label(words: list[dict], region: BBox) -> str:
    # Prefer a complete authored line immediately to the left or above. A
    # printed underline often sits below its label, while a checkbox can sit
    # below the first word of a longer instruction.
    lines = _word_lines(words)
    heights = [float(word["bottom"] - word["top"]) for word in words]
    median_height = sorted(heights)[len(heights) // 2] if heights else 0.0
    coordinate_scale = max(1.0, min(3.0, median_height / 11.0))
    left: list[tuple[float, list[dict]]] = []
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
        if (left_aligned and line_x1 <= region.x + 5
                and line_x1 >= max(0, region.x - 280 * coordinate_scale)
                and vertical_gap <= 32 * coordinate_scale):
            left.append((vertical_gap + abs(line_x1 - region.x) * 0.08, line))

        horizontal_gap = max(region.x - line_x1,
                             line_x0 - (region.x + region.width), 0)
        if (line_bottom <= region.y + 4 * coordinate_scale
                and vertical_gap <= 48 * coordinate_scale
                and horizontal_gap <= 120 * coordinate_scale):
            above.append((vertical_gap + horizontal_gap * 0.08, line))

    candidates = left or above
    if not candidates:
        return ""
    _, selected = min(candidates, key=lambda item: item[0])
    return " ".join(word["text"] for word in selected)


def _label_is_form_like(label: str) -> bool:
    """Reject coherent prose before it can become a semantic field label."""
    text = _clean(label)
    tokens = text.split()
    if not tokens or len(tokens) > 8:
        return False
    if len(tokens) <= 6 and label.rstrip().endswith(":"):
        return True
    if len(tokens) <= 2:
        return True
    phrase_words = _FIELD_CUE_WORDS | {
        "of", "or", "to", "and", "father", "mother", "husband", "wife", "applicant",
    }
    return len(tokens) <= 4 and all(token in phrase_words for token in tokens)


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


def detect_semantic_targets(path: Path, *, model: Any | None = None) -> list[FieldSpec]:
    """Detect a conservative, generic target set from text and vector geometry."""
    targets: list[FieldSpec] = []
    with pdfplumber.open(str(path)) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            words = page.extract_words() or []
            index = 0
            geometry_regions: list[BBox] = []
            all_geometry_regions: list[BBox] = []
            for rect in page.rects:
                width = float(rect["x1"] - rect["x0"])
                height = float(rect["bottom"] - rect["top"])
                is_checkbox = 7 <= width <= 32 and 7 <= height <= 32 and abs(width - height) <= 4
                is_line = width >= 24 and height <= 2.0
                is_large = width >= 55 and height >= 20 and width / max(height, 1) < 18.0
                if is_checkbox or is_line or is_large:
                    all_geometry_regions.append(BBox(round(float(rect["x0"]), 3),
                                                      round(float(rect["top"]), 3),
                                                      round(width, 3), round(height, 3)))
            for line in page.lines:
                width = abs(float(line["x1"] - line["x0"]))
                height = abs(float(line["bottom"] - line["top"]))
                if width >= 24 and height <= 3.0:
                    all_geometry_regions.append(BBox(
                        round(float(min(line["x0"], line["x1"])), 3),
                        round(float(line["top"] - max(1.0, line.get("linewidth", 1.0))), 3),
                        round(width, 3),
                        round(max(3.0, line.get("linewidth", 1.0) * 2), 3),
                    ))
            for rect in page.rects:
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
                    # Keep this geometry in vector_candidates, but do not make
                    # an unlabeled line or table cell an editable browser field.
                    continue
                if not label.rstrip().endswith(":") and _is_grid_like(region, all_geometry_regions):
                    # Table headers can contain field-like words such as
                    # Month, Account, or Name. Repeated row-and-column
                    # geometry is stronger evidence of layout than a lone
                    # header token is evidence of an editable field.
                    continue
                if width <= 32 and height <= 32:
                    detail = "near-square rectangle"
                elif height <= 2.0:
                    detail = "long thin rectangle"
                else:
                    detail = "large rectangle"
                targets.append(_target(page_number, index, region, label, float(page.height), detail, model))
                index += 1
            # Lines and underlines are common entry affordances. Convert them
            # to a small review region so label association can be evaluated.
            for line in page.lines:
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
                targets.append(_target(page_number, index, region, label, float(page.height),
                                       "long thin vector line", model))
                index += 1
            # A short, colon-terminated field label can identify an empty
            # whitespace region when the source PDF has no drawn border.
            for word in words:
                line_words = [candidate for candidate in words
                              if candidate["x0"] <= word["x1"]
                              and candidate["x1"] >= max(0, word["x0"] - 190)
                              and abs(candidate["top"] - word["top"]) <= 4]
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
                if region.x + region.width > float(page.width):
                    region = BBox(region.x, region.y, max(24.0, float(page.width) - region.x - 8), region.height)
                if region.width < 24:
                    continue
                if any(existing.page == page_number and
                       abs(existing.bbox.x - region.x) < 12 and
                       abs(existing.bbox.y - region.y) < 18 for existing in targets):
                    continue
                targets.append(_target(page_number, index, region, label, float(page.height),
                                       "field-like text label with trailing whitespace", model))
                index += 1
    return _dedupe(targets)
