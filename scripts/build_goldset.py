"""Build and evaluate controlled native, vector, and image-only gold forms.

The generated forms are privacy-safe positive controls. Their reviewed target
manifest is authored before detector execution, so it cannot be contaminated
by detector proposals. Real-world documents still require human adjudication.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from pdf_field_lab.inspect_pdf import inspect_pdf
from pdf_field_lab.models import BBox, FieldSpec
from pdf_field_lab.native_detect import detect_native_targets
from pdf_field_lab.raster_cv import detect_raster_targets
from pdf_field_lab.semantic_detect import detect_semantic_targets

from evaluate_detector import evaluate


PAGE_WIDTH, PAGE_HEIGHT = letter
OUTPUT_ROOT = Path("artifacts/goldset")

FAMILIES: tuple[dict[str, Any], ...] = (
    {
        "id": "employment-application",
        "title": "Employment Application",
        "targets": (
            ("applicant-name", "Applicant name:", "text", 72, 100, 260, 24),
            ("birth-date", "Date of birth:", "date", 72, 154, 150, 24),
            ("work-authorized", "Agree to work terms:", "choice", 72, 208, 18, 18),
            ("application-notes", "Additional comments:", "textarea", 72, 510, 300, 62),
            ("passport-photo", "Passport photo:", "image", 380, 360, 140, 110),
            ("applicant-signature", "Applicant signature:", "signature", 72, 300, 310, 3),
        ),
    },
    {
        "id": "travel-consent",
        "title": "Travel Consent Form",
        "targets": (
            ("traveler-name", "Traveler full name:", "text", 72, 92, 360, 24),
            ("travel-date", "Travel date:", "date", 72, 148, 180, 24),
            ("consent", "I agree to the travel terms:", "choice", 72, 204, 18, 18),
            ("travel-notes", "Travel notes:", "textarea", 72, 520, 300, 62),
            ("traveler-photo", "Recent photograph:", "image", 390, 260, 130, 100),
            ("guardian-signature", "Guardian signature:", "signature", 72, 400, 330, 3),
        ),
    },
    {
        "id": "vendor-onboarding",
        "title": "Vendor Onboarding",
        "targets": (
            ("company-name", "Company name:", "text", 72, 96, 260, 24),
            ("contact-email", "Contact email:", "text", 72, 150, 260, 24),
            ("accept-terms", "Accept terms:", "choice", 72, 204, 18, 18),
            ("business-details", "Business details:", "textarea", 72, 510, 300, 62),
            ("company-logo", "Company logo:", "image", 400, 230, 120, 90),
            ("authorized-signature", "Authorized signature:", "signature", 72, 300, 300, 3),
        ),
    },
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bottom_y(top: float, height: float) -> float:
    return PAGE_HEIGHT - top - height


def _draw_target(drawing: canvas.Canvas, target: tuple[Any, ...], native: bool) -> None:
    _, label, kind, x, top, width, height = target
    bottom = _bottom_y(top, height)
    drawing.setFont("Helvetica", 11)
    drawing.drawString(x, _bottom_y(top - 20, 11), label)
    drawing.setStrokeColorRGB(0.25, 0.25, 0.25)
    if kind == "choice":
        drawing.rect(x, bottom, width, height, stroke=1, fill=0)
        if native:
            drawing.acroForm.checkbox(name=target[0], x=x, y=bottom, buttonStyle="check",
                                      borderWidth=1, size=height, checked=False)
    elif kind == "image":
        drawing.rect(x, bottom, width, height, stroke=1, fill=0)
        drawing.setFont("Helvetica", 9)
        drawing.drawCentredString(x + width / 2, bottom + height / 2, "PHOTO / UPLOAD")
    elif kind == "signature":
        drawing.line(x, bottom, x + width, bottom)
    else:
        drawing.rect(x, bottom, width, height, stroke=1, fill=0)
        if native:
            drawing.acroForm.textfield(name=target[0], x=x, y=bottom, width=width,
                                       height=height, borderWidth=0, forceBorder=False)


def _write_variant(path: Path, family: dict[str, Any], *, native: bool) -> None:
    drawing = canvas.Canvas(str(path), pagesize=letter)
    drawing.setTitle(f"Gold set {family['title']}")
    drawing.setFont("Helvetica-Bold", 18)
    drawing.drawString(72, PAGE_HEIGHT - 52, family["title"])
    drawing.setFont("Helvetica", 9)
    drawing.drawString(72, PAGE_HEIGHT - 68, "Controlled reviewed fixture. Do not use as a real application.")
    for target in family["targets"]:
        _draw_target(drawing, target, native)
    drawing.setStrokeColorRGB(0.75, 0.75, 0.75)
    drawing.line(72, PAGE_HEIGHT - 470, 540, PAGE_HEIGHT - 470)
    drawing.setFont("Helvetica", 9)
    drawing.drawString(72, PAGE_HEIGHT - 490, "Reviewer note: every target is intentionally visible and typed.")
    drawing.save()


def _flatten_to_image(source: Path, output: Path) -> None:
    with fitz.open(str(source)) as source_doc:
        output_doc = fitz.open()
        for page in source_doc:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
            output_page = output_doc.new_page(width=page.rect.width, height=page.rect.height)
            output_page.insert_image(output_page.rect, stream=pixmap.tobytes("png"))
        output_doc.save(str(output))
        output_doc.close()


def _field_specs(family: dict[str, Any]) -> list[FieldSpec]:
    fields = []
    for target_id, label, kind, x, top, width, height in family["targets"]:
        observed_top = top + 2 if kind == "signature" else top
        observed_height = max(height, 4)
        fields.append(FieldSpec(
            id=f"{family['id']}.{target_id}", page=1, label=label, kind=kind,
            bbox=BBox(x, observed_top, width, observed_height),
            editable_strategy="visual-overlay-image" if kind in {"image", "signature"}
            else "acroform-checkbox" if kind == "choice" else "acroform-text",
            review_required=False, confidence=1.0,
            notes=["Authored reviewed gold target"],
        ))
    return fields


def _labels_for(path: Path, family: dict[str, Any]) -> dict[str, Any]:
    cases = []
    for field, target in zip(_field_specs(family), family["targets"], strict=True):
        _, _, kind, x, top, width, height = target
        if kind == "signature":
            top += 2
            height = max(height, 4)
        cases.append({
            "id": field.id,
            "pageIndex": 0,
            "class": "checkbox" if kind == "choice" else kind,
            "expected": "detected",
            "hardNegative": False,
            "requiredFieldType": "choice" if kind == "choice" else kind,
            "expectedLabel": target[1],
            "target": {
                "x": x,
                "y": _bottom_y(top, height),
                "width": width,
                "height": height,
            },
        })
    # The footer divider is intentionally visible geometry, but it is not a
    # writable affordance. Keeping it in every representation makes the
    # controlled receipt include a real abstention denominator.
    cases.append({
        "id": f"{family['id']}.hard-negative-footer-divider",
        "pageIndex": 0,
        "class": "underline",
        "expected": "abstain",
        "hardNegative": True,
        "target": {
            "x": 72,
            "y": _bottom_y(470, 3),
            "width": 468,
            "height": 3,
        },
    })
    return {
        "schema": "pdf-field-lab.gold-labels.v1",
        "sourceSha256": _sha256(path),
        "policy": {"positiveMatchIoU": 0.25},
        "cases": cases,
    }


def _render_contact_sheet(cards: list[dict[str, Any]], output: Path) -> str | None:
    if not cards:
        return None
    columns = 3
    card_width, card_height = 420, 570
    rows = (len(cards) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * card_width, rows * card_height), "white")
    font = ImageFont.load_default()
    for index, card in enumerate(cards):
        with fitz.open(card["path"]) as document:
            page = document[0]
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            image.thumbnail((380, 500))
            draw = ImageDraw.Draw(image)
            colors = {"text": "#176b87", "textarea": "#0f766e", "date": "#8b5cf6", "choice": "#d97706",
                      "image": "#059669", "signature": "#dc2626"}
            for target in card["expected_targets"]:
                bbox = target["bbox"]
                draw.rectangle((
                    bbox["x"] / page.rect.width * image.width,
                    bbox["y"] / page.rect.height * image.height,
                    (bbox["x"] + bbox["width"]) / page.rect.width * image.width,
                    (bbox["y"] + bbox["height"]) / page.rect.height * image.height,
                ), outline="#111827", width=1)
            for target in card["predictions"]:
                bbox = target["bbox"]
                draw.rectangle((
                    bbox["x"] / page.rect.width * image.width,
                    bbox["y"] / page.rect.height * image.height,
                    (bbox["x"] + bbox["width"]) / page.rect.width * image.width,
                    (bbox["y"] + bbox["height"]) / page.rect.height * image.height,
                ), outline=colors.get(target["kind"], "#7c3aed"), width=2)
        x = (index % columns) * card_width
        y = (index // columns) * card_height
        sheet.paste(image, (x + (card_width - image.width) // 2, y + 8))
        caption = f"{card['family']} / {card['representation']}\n"
        caption += f"pred={len(card['predictions'])} gold={len(card['expected_targets'])}"
        if "positive_recall" in card.get("evaluation", {}):
            caption += f" recall={card['evaluation']['positive_recall']} precision={card['evaluation']['precision']}"
        ImageDraw.Draw(sheet).text((x + 8, y + 515), caption, fill="black", font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    return str(output)


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    variants: list[dict[str, Any]] = []
    visual_cards: list[dict[str, Any]] = []
    for family in FAMILIES:
        family_dir = OUTPUT_ROOT / family["id"]
        family_dir.mkdir(parents=True, exist_ok=True)
        flat = family_dir / "flat-vector.pdf"
        native = family_dir / "native-widgets.pdf"
        image_only = family_dir / "image-only.pdf"
        _write_variant(flat, family, native=False)
        _write_variant(native, family, native=True)
        _flatten_to_image(flat, image_only)
        family_manifest = {
            "document_family_id": family["id"],
            "review_status": "gold-authored",
            "source_kind": "controlled-positive-fixture",
            "targets": [field.as_dict() | {"status": "accepted"} for field in _field_specs(family)],
            "representations": [],
        }
        for representation, path, detector in (
            ("flat-vector", flat, "semantic"),
            ("native-widgets", native, "native"),
            ("image-only", image_only, "raster"),
        ):
            labels = _labels_for(path, family)
            labels_path = family_dir / f"{representation}-labels.json"
            labels_path.write_text(json.dumps(labels, indent=2) + "\n", encoding="utf-8")
            if detector == "native":
                inspection = inspect_pdf(path)
                predictions = detect_native_targets(inspection)
                evaluation = {
                    "representation": representation,
                    "native_field_count": len(inspection.native_fields),
                    "native_field_names": [item.get("name") for item in inspection.native_fields],
                    "native_target_kinds": {kind: sum(1 for target in predictions if target.kind == kind)
                                            for kind in ("text", "textarea", "choice", "signature")},
                    "native_radio_targets": sum(1 for target in predictions if target.editable_strategy == "acroform-radio"),
                    "native_multiline_targets": sum(1 for target in predictions if target.kind == "textarea"),
                }
            else:
                evaluation = evaluate(path, labels_path, detector=detector)
                evaluation["representation"] = representation
                predictions = detect_semantic_targets(path) if detector == "semantic" else detect_raster_targets(path)
            receipt_path = family_dir / f"{representation}-evaluation.json"
            receipt_path.write_text(json.dumps(evaluation, indent=2) + "\n", encoding="utf-8")
            family_manifest["representations"].append({
                "representation": representation,
                "path": str(path),
                "source_sha256": _sha256(path),
                "labels": str(labels_path),
                "evaluation": str(receipt_path),
                "detector": detector,
            })
            visual_cards.append({
                "family": family["id"],
                "representation": representation,
                "path": str(path),
                "expected_targets": [field.as_dict() for field in _field_specs(family)],
                "predictions": [target.as_dict() for target in predictions],
                "evaluation": evaluation,
            })
        manifest_path = family_dir / "gold-manifest.json"
        manifest_path.write_text(json.dumps(family_manifest, indent=2) + "\n", encoding="utf-8")
        variants.append(family_manifest)

    manifest = {
        "schema": "pdf-field-lab.goldset.v1",
        "review_status": "gold-authored-controlled-not-human-real-world",
        "families": variants,
        "visual_contact_sheet": str(OUTPUT_ROOT / "visual" / "contact-sheet.png"),
    }
    manifest_path = OUTPUT_ROOT / "goldset-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    visual_path = _render_contact_sheet(visual_cards, OUTPUT_ROOT / "visual" / "contact-sheet.png")
    summary = {
        "schema": "pdf-field-lab.goldset-receipt.v1",
        "family_count": len(FAMILIES),
        "representation_count": len(visual_cards),
        "representations": {key: sum(1 for card in visual_cards if card["representation"] == key)
                             for key in ("flat-vector", "native-widgets", "image-only")},
        "flat_vector_positive_recall": [
            card["evaluation"]["positive_recall"] for card in visual_cards
            if card["representation"] == "flat-vector"
        ],
        "image_only_positive_recall": [
            card["evaluation"]["positive_recall"] for card in visual_cards
            if card["representation"] == "image-only"
        ],
        "flat_vector_type_accuracy": [
            card["evaluation"]["type_accuracy"] for card in visual_cards
            if card["representation"] == "flat-vector"
        ],
        "image_only_type_accuracy": [
            card["evaluation"]["type_accuracy"] for card in visual_cards
            if card["representation"] == "image-only"
        ],
        "flat_vector_label_association_rate": [
            card["evaluation"]["label_association_rate"] for card in visual_cards
            if card["representation"] == "flat-vector"
        ],
        "image_only_label_association_rate": [
            card["evaluation"]["label_association_rate"] for card in visual_cards
            if card["representation"] == "image-only"
        ],
        "flat_vector_hard_negative_false_positive_rate": [
            card["evaluation"]["hard_negative_false_positive_rate"] for card in visual_cards
            if card["representation"] == "flat-vector"
        ],
        "image_only_hard_negative_false_positive_rate": [
            card["evaluation"]["hard_negative_false_positive_rate"] for card in visual_cards
            if card["representation"] == "image-only"
        ],
        "flat_vector_duplicate_pairs": [
            card["evaluation"]["duplicate_pairs"] for card in visual_cards
            if card["representation"] == "flat-vector"
        ],
        "image_only_duplicate_pairs": [
            card["evaluation"]["duplicate_pairs"] for card in visual_cards
            if card["representation"] == "image-only"
        ],
        "native_field_counts": [
            card["evaluation"]["native_field_count"] for card in visual_cards
            if card["representation"] == "native-widgets"
        ],
        "visual_contact_sheet": visual_path,
        "manifest": str(manifest_path),
        "privacy_note": "Generated controlled fixtures only; no user PDF bytes copied.",
    }
    (OUTPUT_ROOT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
