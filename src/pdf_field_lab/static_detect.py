"""Conservative visual candidate detection for flat/vector PDFs.

This detector is deliberately not a semantic field detector. It reports
geometry that may be useful for review and lets the Form-6 profile provide the
semantic, document-specific contract. That prevents table borders and dense
character grids from being silently promoted to user-editable fields.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pdfplumber

from .models import BBox, Evidence, FieldSpec


def _rounded(value: float) -> float:
    return round(float(value), 3)


def _candidate(page_number: int, index: int, kind: str, rect: dict, detail: str, score: float) -> FieldSpec:
    return FieldSpec(
        id=f"vector-{page_number}-{index:04d}", page=page_number,
        label="unlabeled geometric candidate", kind=kind, bbox=BBox(
            _rounded(rect["x0"]), _rounded(rect["top"]),
            _rounded(rect["x1"] - rect["x0"]), _rounded(rect["bottom"] - rect["top"])),
        editable_strategy="review-only candidate", review_required=True,
        confidence=score, evidence=[Evidence("vector", score, detail)],
        notes=["Geometry only; not a semantic field contract."],
    )


def _dedupe(candidates: Iterable[FieldSpec]) -> list[FieldSpec]:
    seen: set[tuple[int, int, int, int, str]] = set()
    result = []
    for item in candidates:
        key = (item.page, round(item.bbox.x), round(item.bbox.y),
               round(item.bbox.width), item.kind)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def detect_vector_candidates(path: Path) -> list[FieldSpec]:
    output: list[FieldSpec] = []
    with pdfplumber.open(str(path)) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            index = 0
            for rect in page.rects:
                width = rect["x1"] - rect["x0"]
                height = rect["bottom"] - rect["top"]
                # Small square-like geometry is a checkbox/radio candidate.
                if 7 <= width <= 32 and 7 <= height <= 32 and abs(width - height) <= 4:
                    output.append(_candidate(page_number, index, "choice", rect,
                                             "near-square vector rectangle", 0.72))
                    index += 1
                # Large isolated rectangles are possible image/signature regions,
                # but table cells are common, so confidence remains low.
                elif width >= 55 and height >= 20 and width / max(height, 1) < 18.0:
                    output.append(_candidate(page_number, index, "image", rect,
                                             "large rectangle; could be image/signature or table cell", 0.42))
                    index += 1
            # Keep explicitly authored long lines as review-only underline
            # candidates. They may be entry strokes or ordinary document rules.
            for rect in page.rects:
                width = rect["x1"] - rect["x0"]
                height = rect["bottom"] - rect["top"]
                if width >= 24 and height <= 2.0:
                    output.append(_candidate(page_number, index, "text", rect,
                                             "thin vector rule; label association required", 0.38))
                    index += 1
            for line in page.lines:
                width = abs(float(line["x1"] - line["x0"]))
                height = abs(float(line["bottom"] - line["top"]))
                if width >= 24 and height <= 3.0:
                    rect = {"x0": min(float(line["x0"]), float(line["x1"])),
                            "x1": max(float(line["x0"]), float(line["x1"])),
                            "top": float(line["top"] - max(1.0, line.get("linewidth", 1.0))),
                            "bottom": float(line["top"] + max(1.0, line.get("linewidth", 1.0)))}
                    output.append(_candidate(page_number, index, "text", rect,
                                             "long vector line; label association required", 0.38))
                    index += 1
    return _dedupe(output)
