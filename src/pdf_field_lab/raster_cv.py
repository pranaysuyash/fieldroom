"""Optional raster evidence lanes.

The CV and OCR results are measurements used to enrich review evidence. They
are never promoted directly to semantic fields by this module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import BBox, Evidence, FieldSpec


def _render_pages(path: Path, dpi: int = 150):
    import pymupdf
    scale = dpi / 72.0
    matrix = pymupdf.Matrix(scale, scale)
    document = pymupdf.open(str(path))
    try:
        for page in document:
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            yield pixmap
    finally:
        document.close()


def run_cv_probe(path: Path, dpi: int = 150) -> dict[str, Any]:
    """Count rectangular raster contours as review-only visual evidence."""
    import cv2
    import numpy as np

    pages = []
    for page_number, pixmap in enumerate(_render_pages(path, dpi), 1):
        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        threshold = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY_INV)[1]
        contours, _ = cv2.findContours(threshold, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        rectangles = 0
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 30:
                continue
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
            x, y, width, height = cv2.boundingRect(contour)
            if len(approx) == 4 and width >= 12 and height >= 12:
                rectangles += 1
        pages.append({"page": page_number, "width": pixmap.width, "height": pixmap.height,
                      "contours": len(contours), "rectangular_contours": rectangles})
    return {"dpi": dpi, "pages": pages, "note": "visual evidence only; no semantic promotion"}


def run_ocr_probe(path: Path, dpi: int = 150) -> dict[str, Any]:
    """Run local Tesseract and retain aggregate confidence evidence only."""
    import pytesseract
    from pytesseract import Output
    from PIL import Image

    pages = []
    for page_number, pixmap in enumerate(_render_pages(path, dpi), 1):
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        data = pytesseract.image_to_data(image, output_type=Output.DICT, config="--psm 6")
        confidences = [float(value) for value in data.get("conf", []) if str(value).strip() not in {"", "-1"}]
        words = [text for text in data.get("text", []) if text.strip()]
        pages.append({"page": page_number, "words": len(words),
                      "mean_confidence": round(sum(confidences) / len(confidences), 2) if confidences else 0.0})
    return {"dpi": dpi, "pages": pages, "note": "OCR evidence only; profile remains authoritative"}


def detect_raster_targets(path: Path, dpi: int = 150, *, max_per_page: int = 80) -> list[FieldSpec]:
    """Find review-only semantic targets on pages without a usable text layer.

    CV supplies candidate rectangles and OCR supplies nearby labels. Neither is
    authoritative: a rectangle is promoted only when OCR contains an explicit
    field cue. This keeps scanned documents on the same conservative contract as
    vector PDFs while retaining raster provenance.
    """
    import cv2
    import numpy as np
    import pytesseract
    from PIL import Image
    from pytesseract import Output

    from .semantic_detect import _has_explicit_field_cue, _nearby_label, classify_label
    from .label_ner import extract_label_entities

    def overlap_ratio(first: BBox, second: BBox) -> float:
        x0 = max(first.x, second.x)
        y0 = max(first.y, second.y)
        x1 = min(first.x + first.width, second.x + second.width)
        y1 = min(first.y + first.height, second.y + second.height)
        intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
        smaller_area = min(first.width * first.height, second.width * second.height)
        return intersection / smaller_area if smaller_area else 0.0

    targets: list[FieldSpec] = []
    for page_number, pixmap in enumerate(_render_pages(path, dpi), 1):
        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        threshold = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY_INV)[1]
        contours, _ = cv2.findContours(threshold, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        ocr = pytesseract.image_to_data(Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples),
                                        output_type=Output.DICT, config="--psm 6")
        words = []
        for index, text in enumerate(ocr.get("text", [])):
            text = str(text).strip()
            if not text:
                continue
            words.append({
                "text": text,
                "x0": float(ocr["left"][index]), "top": float(ocr["top"][index]),
                "x1": float(ocr["left"][index] + ocr["width"][index]),
                "bottom": float(ocr["top"][index] + ocr["height"][index]),
            })
        page_scale = dpi / 72.0
        seen: set[tuple[int, int, int, int, str]] = set()
        candidates: list[FieldSpec] = []
        geometry_regions: list[BBox] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
            x, y, width, height = cv2.boundingRect(contour)
            is_square = (7 * page_scale <= width <= 32 * page_scale and
                         7 * page_scale <= height <= 32 * page_scale and
                         abs(width - height) <= 4 * page_scale)
            is_line = width >= 24 * page_scale and height <= 6 * page_scale
            is_large = (width >= 55 * page_scale and height >= 20 * page_scale
                        and width / max(height, 1) < 18.0)
            # A one-pixel raster line can have near-zero filled area even
            # though its bounding geometry is a strong signature/underline
            # candidate. Let line geometry survive the area gate.
            if area < 30 and not is_line:
                continue
            if (len(approx) != 4 and not is_line) or width < 12 or (height < 2 and not is_line):
                continue
            if not (is_square or is_line or is_large):
                continue
            region = BBox(round(x / page_scale, 3), round(y / page_scale, 3),
                          round(width / page_scale, 3), round(height / page_scale, 3))
            pixel_region = BBox(float(x), float(y), float(width), float(height))
            geometry_regions.append(region)
            label = _nearby_label(words, pixel_region)
            if not _has_explicit_field_cue(label):
                continue
            kind, score, detail = classify_label(label, region=region, page_height=pixmap.height / page_scale)
            strategy = "visual-overlay-image" if kind in {"image", "signature"} else "acroform-checkbox" if kind == "choice" else "acroform-text"
            key = (round(region.x), round(region.y), round(region.width), round(region.height), kind)
            if key in seen or any(existing.kind == kind and overlap_ratio(existing.bbox, region) >= 0.65
                                   for existing in candidates):
                continue
            seen.add(key)
            candidates.append(FieldSpec(
                id=f"raster-target-{page_number}-{len(candidates):04d}", page=page_number,
                label=label or "OCR-labeled field", kind=kind, bbox=region,
                editable_strategy=strategy, review_required=True, confidence=min(score, 0.79),
                evidence=[Evidence("raster_cv", min(score, 0.79),
                                   f"OCR label plus rectangular raster contour; {detail}")],
                notes=["Raster/OCR candidate; confirm position and meaning before export."],
                label_entities=extract_label_entities(label),
            ))
            if len(candidates) >= max_per_page:
                break

        # A scanned form can use blank space after a label instead of a drawn
        # border. Mirror the vector detector's whitespace lane in OCR space,
        # while retaining the lower-confidence raster provenance.
        if len(candidates) < max_per_page:
            for word in words:
                if not str(word["text"]).endswith(":"):
                    continue
                line_words = [candidate for candidate in words
                              if candidate["x0"] <= word["x1"]
                              and candidate["x1"] >= max(0, word["x0"] - 190 * page_scale)
                              and abs(candidate["top"] - word["top"]) <= 4 * page_scale]
                line_words.sort(key=lambda candidate: candidate["x0"])
                label = " ".join(candidate["text"] for candidate in line_words)
                if not _has_explicit_field_cue(label):
                    continue
                same_line = [candidate for candidate in words
                             if candidate["x0"] >= word["x1"]
                             and candidate["top"] <= word["bottom"] + 4 * page_scale
                             and candidate["bottom"] >= word["top"] - 4 * page_scale]
                if any(candidate["x0"] - word["x1"] < 120 * page_scale for candidate in same_line):
                    continue
                label_region = BBox(float(word["x1"] + 8 * page_scale),
                                    float(word["top"] - 2 * page_scale),
                                    220 * page_scale, 24 * page_scale)

                def geometry_near_label(region: BBox) -> bool:
                    label_x0 = float(word["x0"])
                    label_x1 = float(word["x1"])
                    region_x0 = region.x * page_scale
                    region_x1 = (region.x + region.width) * page_scale
                    if region_x1 < label_x0:
                        horizontal_gap = label_x0 - region_x1
                    elif label_x1 < region_x0:
                        horizontal_gap = region_x0 - label_x1
                    else:
                        horizontal_gap = 0.0
                    region_y0 = region.y * page_scale
                    region_y1 = (region.y + region.height) * page_scale
                    vertical_gap = max(region_y0 - word["bottom"],
                                       word["top"] - region_y1, 0)
                    return horizontal_gap <= 120 * page_scale and vertical_gap <= 48 * page_scale

                if any(geometry_near_label(region) for region in geometry_regions):
                    continue
                region = BBox(round(label_region.x / page_scale, 3),
                              round(label_region.y / page_scale, 3),
                              round(min(label_region.width, pixmap.width - label_region.x) / page_scale, 3),
                              24.0)
                if region.width < 24:
                    continue
                kind, score, detail = classify_label(label, region=region,
                                                      page_height=pixmap.height / page_scale)
                key = (round(region.x), round(region.y), round(region.width), round(region.height), kind)
                if key in seen or any(existing.kind == kind and overlap_ratio(existing.bbox, region) >= 0.65
                                       for existing in candidates):
                    continue
                seen.add(key)
                candidates.append(FieldSpec(
                    id=f"raster-target-{page_number}-{len(candidates):04d}", page=page_number,
                    label=label, kind=kind, bbox=region,
                    editable_strategy="visual-overlay-image" if kind in {"image", "signature"}
                    else "acroform-checkbox" if kind == "choice" else "acroform-text",
                    review_required=True, confidence=min(score, 0.79),
                    evidence=[Evidence("ocr", min(score, 0.79),
                                       f"OCR field label plus raster whitespace; {detail}")],
                    notes=["Raster/OCR whitespace candidate; confirm width and meaning before export."],
                    label_entities=extract_label_entities(label),
                ))
                if len(candidates) >= max_per_page:
                    break
        targets.extend(candidates)
    return targets
