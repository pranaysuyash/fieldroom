"""Optional raster evidence lanes.

The CV and OCR results are measurements used to enrich review evidence. They
are never promoted directly to semantic fields by this module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import BBox, Evidence, FieldSpec


def _render_pages(path: Path, dpi: int = 150, *, pages: set[int] | None = None):
    import pymupdf
    scale = dpi / 72.0
    matrix = pymupdf.Matrix(scale, scale)
    document = pymupdf.open(str(path))
    try:
        for index, page in enumerate(document, 1):
            if pages is not None and index not in pages:
                continue
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            if pages is not None:
                yield index, pixmap
            else:
                yield pixmap
    finally:
        document.close()


def _estimate_skew_angle(mask, page_scale: float) -> float:
    """Estimate small scanner skew angle in degrees from horizontal form structure."""
    import cv2
    import numpy as np

    lines = cv2.HoughLinesP(
        mask,
        rho=1.0,
        theta=np.pi / 1800.0,
        threshold=max(25, int(35 * page_scale)),
        minLineLength=max(30, int(45 * page_scale)),
        maxLineGap=max(4, int(8 * page_scale)),
    )
    if lines is None:
        return 0.0
    angles: list[float] = []
    for entry in lines:
        coords = entry.reshape(-1)
        if coords.size < 4:
            continue
        x1, y1, x2, y2 = coords[:4]
        dx = float(x2 - x1)
        dy = float(y2 - y1)
        if abs(dx) < 20 * page_scale:
            continue
        angle = float(np.degrees(np.arctan2(dy, dx)))
        if -6.5 <= angle <= 6.5:
            angles.append(angle)
    if len(angles) < 2:
        return 0.0
    median_angle = float(np.median(angles))
    return median_angle if abs(median_angle) >= 0.35 else 0.0


def _preprocess_scan_page(image, page_scale: float):
    """Normalize illumination, deskew small rotations, and build a contour mask + OCR image.

    Returns ``(binary_mask, ocr_pil_image, skew_degrees)``. On clean digital-white
    raster pages this reduces to the classic threshold while recovering boxes and
    underlines on shaded, low-contrast, faint-stroke, or slightly skewed scans.
    """
    import cv2
    import numpy as np
    from PIL import Image

    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    sigma = max(15.0, round(12.0 * page_scale, 1))
    background = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma)
    diff = cv2.subtract(background, gray)

    # Estimate paper noise floor from the lower 75% of pixel differences
    noise_floor = float(np.percentile(diff, 75))
    if noise_floor > 2.0:
        # Light median filter suppresses salt-and-pepper scanner speckle before diff
        denoised_gray = cv2.medianBlur(gray, 3)
        background = cv2.GaussianBlur(denoised_gray, (0, 0), sigmaX=sigma)
        diff = cv2.subtract(background, denoised_gray)
        noise_floor = float(np.percentile(diff, 75))

    foreground_samples = diff[diff > max(4.0, noise_floor + 3.0)]
    stroke_strength = float(np.percentile(foreground_samples, 85)) if foreground_samples.size else 0.0
    if stroke_strength > 0.0 and stroke_strength < 48.0:
        # Faint/washed-out strokes: lower threshold proportionally above noise floor
        cutoff = max(8, int(max(noise_floor * 2.5 + 5.0, stroke_strength * 0.42)))
    else:
        cutoff = max(18, min(34, int(noise_floor * 3.0 + 16.0)))

    mask = cv2.threshold(diff, cutoff, 255, cv2.THRESH_BINARY)[1]

    skew_angle = _estimate_skew_angle(mask, page_scale)
    if abs(skew_angle) >= 0.35:
        height, width = gray.shape[:2]
        center = (width / 2.0, height / 2.0)
        rot_mat = cv2.getRotationMatrix2D(center, skew_angle, 1.0)
        gray = cv2.warpAffine(gray, rot_mat, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        mask = cv2.warpAffine(mask, rot_mat, (width, height), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        background = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma)
        diff = cv2.subtract(background, gray)

    # Enhance OCR image when background is dark/shaded or strokes are faint
    bg_median = float(np.median(gray))
    if bg_median < 235.0 or (0.0 < stroke_strength < 55.0):
        scale_factor = 255.0 / max(stroke_strength, 32.0)
        enhanced = np.clip(255.0 - diff.astype(np.float32) * min(scale_factor, 4.5), 0, 255).astype(np.uint8)
        ocr_pil = Image.fromarray(enhanced).convert("RGB")
    else:
        ocr_pil = Image.fromarray(gray).convert("RGB")

    return mask, ocr_pil, skew_angle


def run_cv_probe(path: Path, dpi: int = 150) -> dict[str, Any]:
    """Count rectangular raster contours as review-only visual evidence."""
    import cv2
    import numpy as np

    pages = []
    page_scale = dpi / 72.0
    for page_number, pixmap in enumerate(_render_pages(path, dpi), 1):
        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
        threshold, _, skew_angle = _preprocess_scan_page(image, page_scale)
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
                      "contours": len(contours), "rectangular_contours": rectangles,
                      "skew_degrees": round(skew_angle, 2)})
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


def _extract_ocr_words(ocr_image) -> list[dict[str, Any]]:
    import pytesseract
    from pytesseract import Output

    ocr = pytesseract.image_to_data(ocr_image, output_type=Output.DICT, config="--psm 6")
    words: list[dict[str, Any]] = []
    for index, text in enumerate(ocr.get("text", [])):
        text = str(text).strip()
        if not text:
            continue
        words.append({
            "text": text,
            "x0": float(ocr["left"][index]),
            "top": float(ocr["top"][index]),
            "x1": float(ocr["left"][index] + ocr["width"][index]),
            "bottom": float(ocr["top"][index] + ocr["height"][index]),
        })
    return words


def detect_raster_targets(
    path: Path,
    dpi: int = 150,
    *,
    max_per_page: int = 80,
    pages: set[int] | None = None,
    warnings_out: list[str] | None = None,
) -> list[FieldSpec]:
    """Find review-only semantic targets on pages without a usable text layer.

    CV supplies candidate rectangles and OCR supplies nearby labels. Neither is
    authoritative: a rectangle is promoted only when OCR contains an explicit
    field cue. This keeps scanned documents on the same conservative contract as
    vector PDFs while retaining raster provenance.
    """
    import cv2
    import numpy as np

    from .semantic_detect import (
        _clean,
        _cluster_character_grids,
        _has_explicit_field_cue,
        _nearby_label,
        classify_label,
    )
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
    page_scale = dpi / 72.0
    rendered_iter = (
        _render_pages(path, dpi, pages=pages)
        if pages is not None
        else enumerate(_render_pages(path, dpi), 1)
    )
    for page_number, pixmap in rendered_iter:
        try:
            image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
            threshold, ocr_image, _ = _preprocess_scan_page(image, page_scale)
            contours, _ = cv2.findContours(threshold, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            words = _extract_ocr_words(ocr_image)
        except Exception as exc:
            if warnings_out is not None:
                warnings_out.append(f"Raster detection failed on page {page_number}: {type(exc).__name__}")
            continue
        words_pts = [
            {
                "text": w["text"],
                "x0": float(w["x0"]) / page_scale,
                "top": float(w["top"]) / page_scale,
                "x1": float(w["x1"]) / page_scale,
                "bottom": float(w["bottom"]) / page_scale,
            }
            for w in words
        ]
        seen: set[tuple[int, int, int, int, str]] = set()
        candidates: list[FieldSpec] = []
        geometry_regions: list[BBox] = []

        # Cluster adjacent character-box contours into comb-grid rows before individual contour evaluation
        raw_boxes_pts: list[BBox] = []
        seen_box_pts: set[tuple[int, int, int, int]] = set()
        for contour in contours:
            x, y, width, height = cv2.boundingRect(contour)
            w_pt, h_pt = width / page_scale, height / page_scale
            x_pt, y_pt = x / page_scale, y / page_scale
            if 10.0 <= w_pt <= 26.0 and 10.0 <= h_pt <= 22.0:
                bkey = (round(x_pt / 2) * 2, round(y_pt / 2) * 2, round(w_pt / 2) * 2, round(h_pt / 2) * 2)
                if bkey not in seen_box_pts:
                    seen_box_pts.add(bkey)
                    raw_boxes_pts.append(BBox(round(x_pt, 3), round(y_pt, 3), round(w_pt, 3), round(h_pt, 3)))

        comb_grids, _ = _cluster_character_grids(raw_boxes_pts)
        for grid_box in comb_grids:
            geometry_regions.append(grid_box)
            label = _nearby_label(words_pts, grid_box)
            if not _has_explicit_field_cue(label):
                continue
            kind, score, detail = classify_label(label, region=grid_box, page_height=pixmap.height / page_scale)
            strategy = "acroform-text"
            key = (round(grid_box.x), round(grid_box.y), round(grid_box.width), round(grid_box.height), kind)
            if key in seen or any(existing.kind == kind and overlap_ratio(existing.bbox, grid_box) >= 0.65
                                   for existing in candidates):
                continue
            seen.add(key)
            candidates.append(FieldSpec(
                id=f"raster-target-{page_number}-{len(candidates):04d}", page=page_number,
                label=label, kind=kind, bbox=grid_box,
                editable_strategy=strategy, review_required=True, confidence=min(score, 0.79),
                evidence=[Evidence("raster_cv", min(score, 0.79),
                                   f"OCR label plus raster character comb-grid; {detail}")],
                notes=["Raster/OCR candidate; confirm position and meaning before export."],
                label_entities=extract_label_entities(label),
            ))
            if len(candidates) >= max_per_page:
                break

        for contour in contours:
            if len(candidates) >= max_per_page:
                break
            area = cv2.contourArea(contour)
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
            x, y, width, height = cv2.boundingRect(contour)
            is_square = (11 * page_scale <= width <= 32 * page_scale and
                         11 * page_scale <= height <= 32 * page_scale and
                         abs(width - height) <= 5 * page_scale)
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
            if any(overlap_ratio(grid_box, region) >= 0.5 for grid_box in comb_grids):
                continue
            geometry_regions.append(region)
            label = _nearby_label(words_pts, region)
            if is_large and 55 <= region.width <= 220 and 55 <= region.height <= 220:
                inside_words = [
                    w["text"] for w in words_pts
                    if w["x0"] >= region.x - 4 and w["x1"] <= region.x + region.width + 4
                    and w["top"] >= region.y - 4 and w["bottom"] <= region.y + region.height + 4
                ]
                inside_text = _clean(" ".join(inside_words))
                if any(cue in inside_text for cue in ("photograph", "passport photo", "paste photo", "pasting")):
                    label = " ".join(inside_words[:6])
            if not _has_explicit_field_cue(label):
                continue
            kind, score, detail = classify_label(label, region=region, page_height=pixmap.height / page_scale)
            if is_square and kind == "text":
                kind = "choice"
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

        # Choice-cue family: a small near-square or circular contour is a
        # checkable affordance even when its adjacent text carries no explicit
        # field cue ("Father", "Aadhaar Card"). The miss taxonomy measured
        # these as the dominant raster gap (12/21 misses at zero overlap), so
        # geometry alone proposes them; confidence stays low and review stays
        # required, preserving the conservative contract above.
        if len(candidates) < max_per_page:
            choice_regions: list[BBox] = []
            for contour in contours:
                x, y, width, height = cv2.boundingRect(contour)
                w_pt, h_pt = width / page_scale, height / page_scale
                if not (9.0 <= w_pt <= 26.0 and 9.0 <= h_pt <= 26.0
                        and abs(w_pt - h_pt) <= 6.0):
                    continue
                area = cv2.contourArea(contour)
                if area < 22:
                    continue
                perimeter = cv2.arcLength(contour, True)
                circularity = (4 * np.pi * area / (perimeter * perimeter)
                               if perimeter > 0 else 0.0)
                quadrilateral = len(cv2.approxPolyDP(contour, 0.03 * perimeter, True)) == 4
                if not quadrilateral and circularity < 0.55:
                    # Radio circles never approximate to four vertices; accept
                    # them by circularity instead of the shape filter above.
                    continue
                region = BBox(round(x / page_scale, 3), round(y / page_scale, 3),
                              round(w_pt, 3), round(h_pt, 3))
                if any(overlap_ratio(grid_box, region) >= 0.5 for grid_box in comb_grids):
                    continue
                if any(overlap_ratio(existing.bbox, region) >= 0.5 for existing in candidates):
                    continue
                choice_regions.append(region)
            for region in choice_regions:
                if len(candidates) >= max_per_page:
                    break
                center_y = region.y + region.height / 2.0
                row_peers = sum(
                    1 for other in choice_regions
                    if other is not region
                    and abs((other.y + other.height / 2.0) - center_y) <= 4.0)
                label = _nearby_label(words_pts, region) or "Checkable option"
                key = (round(region.x), round(region.y), round(region.width), round(region.height), "choice")
                if key in seen or any(existing.kind == "choice"
                                      and overlap_ratio(existing.bbox, region) >= 0.65
                                      for existing in candidates):
                    continue
                seen.add(key)
                candidates.append(FieldSpec(
                    id=f"raster-target-{page_number}-{len(candidates):04d}", page=page_number,
                    label=label, kind="choice", bbox=region,
                    editable_strategy="acroform-radio" if row_peers else "acroform-checkbox",
                    review_required=True, confidence=0.55,
                    evidence=[Evidence("raster_cv", 0.55,
                                       f"Choice-sized contour ({'radio row' if row_peers else 'standalone'}); "
                                       "geometry cue without explicit label cue")],
                    notes=["Raster/OCR candidate; confirm position and meaning before export."],
                    label_entities=extract_label_entities(label) if label != "Checkable option" else [],
                ))

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
