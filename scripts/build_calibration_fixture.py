"""Author the in-repo detector calibration fixture and label manifest.

The calibration PDF is generated, not scanned: every rectangle, rule, and
label is placed at a known coordinate so the reviewed manifest can be written
before detection runs. The fixture exercises the four calibrated positive
behaviors (labeled rectangle, checkbox square, underline, labeled whitespace)
plus decorative geometry that must be abstained from. Output lands under
artifacts/calibration/ and is fully reproducible offline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = letter  # 612 x 792, reportlab origin is lower-left


def _draw_fixture(path: Path) -> None:
    canvas_obj = canvas.Canvas(str(path), pagesize=letter)
    canvas_obj.setFont("Helvetica", 11)

    # Decorative hard negatives first: rules and blocks that must never
    # surface as editable fields.
    canvas_obj.setLineWidth(1.0)
    canvas_obj.line(48, 740, 564, 740)          # header rule
    canvas_obj.line(48, 60, 564, 60)            # footer rule
    canvas_obj.setLineWidth(0.6)
    canvas_obj.line(48, 300, 564, 300)          # table separator 1
    canvas_obj.line(48, 270, 564, 270)          # table separator 2
    canvas_obj.rect(430, 680, 110, 40)          # logo-like block

    # Positive 1: labeled rectangle (text field).
    canvas_obj.drawString(60, 700, "Applicant Name:")
    canvas_obj.setLineWidth(0.8)
    canvas_obj.rect(170, 694, 220, 22)

    # Positive 2: checkbox square (choice field).
    canvas_obj.drawString(60, 640, "Agree to terms:")
    canvas_obj.rect(160, 634, 14, 14)

    # Positive 3: underline (date field).
    canvas_obj.drawString(60, 580, "Date of Birth:")
    canvas_obj.setLineWidth(0.8)
    canvas_obj.line(150, 570, 300, 570)

    # Positive 4: labeled whitespace (address text area). Placed well below
    # the underline: the whitespace lane abstains when any geometry sits
    # within 48 points vertically of the label word.
    canvas_obj.drawString(60, 490, "Address:")

    canvas_obj.save()


def _labels_manifest(pdf_path: Path) -> dict:
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    return {
        "schema": "pdf-field-lab.detector-calibration-labels",
        "version": {"major": 1, "minor": 0},
        "fixture": str(pdf_path),
        "sourceSha256": digest,
        "coordinateSpace": {"unit": "points", "origin": "lowerLeft", "pageBox": "crop"},
        "policy": {
            "positiveMatchIoU": 0.25,
            "hardNegativeFalsePositiveRate": 0,
            "requiredPositiveRecall": 1,
            "labelAssociationEvidence": ["textLabel", "spatialRelationship"],
            "reviewRequired": True,
        },
        "cases": [
            {
                "id": "cal-rect-name",
                "reviewedRegionID": "reviewed:cal:applicant-name-box",
                "pageIndex": 0,
                "class": "vectorRectangle",
                "expected": "detected",
                "hardNegative": False,
                "expectedLabel": "Applicant Name",
                "requiredFieldType": "text",
                "target": {"x": 170, "y": 694, "width": 220, "height": 22},
                "requiredEvidence": ["vectorRectangle"],
            },
            {
                "id": "cal-checkbox-terms",
                "reviewedRegionID": "reviewed:cal:agree-terms-box",
                "pageIndex": 0,
                "class": "checkbox",
                "expected": "detected",
                "hardNegative": False,
                "expectedLabel": "Agree to terms",
                "requiredFieldType": "checkbox",
                "target": {"x": 160, "y": 634, "width": 14, "height": 14},
                "requiredEvidence": ["checkboxSquare"],
            },
            {
                "id": "cal-underline-dob",
                "reviewedRegionID": "reviewed:cal:dob-underline",
                "pageIndex": 0,
                "class": "underline",
                "expected": "detected",
                "hardNegative": False,
                "expectedLabel": "Date of Birth",
                "requiredFieldType": "date",
                "target": {"x": 150, "y": 570, "width": 150, "height": 16},
                "requiredEvidence": ["underlineRule"],
            },
            {
                "id": "cal-whitespace-address",
                "reviewedRegionID": "reviewed:cal:address-whitespace",
                "pageIndex": 0,
                "class": "whitespace",
                "expected": "detected",
                "hardNegative": False,
                "expectedLabel": "Address",
                # The emitted whitespace region is single-line height, so the
                # detector's honest type is text; textarea requires a taller
                # multi-line region.
                "requiredFieldType": "text",
                "target": {"x": 110, "y": 478, "width": 226, "height": 26},
                "requiredEvidence": ["labeledWhitespace"],
            },
            {
                "id": "cal-hn-header-rule",
                "reviewedRegionID": "reviewed:cal:header-rule",
                "pageIndex": 0,
                "class": "decorativeRule",
                "expected": "abstain",
                "hardNegative": True,
                "target": {"x": 48, "y": 738, "width": 516, "height": 5},
            },
            {
                "id": "cal-hn-footer-rule",
                "reviewedRegionID": "reviewed:cal:footer-rule",
                "pageIndex": 0,
                "class": "decorativeRule",
                "expected": "abstain",
                "hardNegative": True,
                "target": {"x": 48, "y": 58, "width": 516, "height": 5},
            },
            {
                "id": "cal-hn-table-rule-1",
                "reviewedRegionID": "reviewed:cal:table-rule-1",
                "pageIndex": 0,
                "class": "decorativeRule",
                "expected": "abstain",
                "hardNegative": True,
                "target": {"x": 48, "y": 298, "width": 516, "height": 5},
            },
            {
                "id": "cal-hn-table-rule-2",
                "reviewedRegionID": "reviewed:cal:table-rule-2",
                "pageIndex": 0,
                "class": "decorativeRule",
                "expected": "abstain",
                "hardNegative": True,
                "target": {"x": 48, "y": 268, "width": 516, "height": 5},
            },
            {
                "id": "cal-hn-logo-block",
                "reviewedRegionID": "reviewed:cal:logo-block",
                "pageIndex": 0,
                "class": "decorativeBlock",
                "expected": "abstain",
                "hardNegative": True,
                "target": {"x": 430, "y": 680, "width": 110, "height": 40},
            },
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/calibration"))
    args = parser.parse_args(argv)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = args.output_dir / "detector-calibration.pdf"
    labels_path = args.output_dir / "detector-calibration-labels.json"

    _draw_fixture(pdf_path)
    manifest = _labels_manifest(pdf_path)
    labels_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "pdf": str(pdf_path),
        "labels": str(labels_path),
        "sha256": manifest["sourceSha256"],
        "positives": sum(1 for case in manifest["cases"] if not case["hardNegative"]),
        "hard_negatives": sum(1 for case in manifest["cases"] if case["hardNegative"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
