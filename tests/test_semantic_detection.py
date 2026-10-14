from pathlib import Path

from reportlab.pdfgen import canvas

from pdf_field_lab.manifest import create_manifest
from pdf_field_lab.semantic_detect import classify_label, detect_semantic_targets
from pdf_field_lab.models import BBox


def test_generic_promotion_requires_an_explicit_field_cue(tmp_path):
    source = tmp_path / "labeled-and-unlabeled.pdf"
    drawing = canvas.Canvas(str(source), pagesize=(612, 792))
    drawing.drawString(100, 700, "Name")
    drawing.rect(160, 688, 20, 18)
    drawing.drawString(100, 500, "Table")
    drawing.rect(160, 488, 20, 18)
    drawing.save()

    targets = detect_semantic_targets(Path(source))

    assert len(targets) == 1
    assert targets[0].kind == "text"


def test_calibration_fixture_recovers_labeled_regions_without_promoting_hard_negatives(tmp_path):
    """A small reviewed fixture protects recall and precision together."""
    source = tmp_path / "detector-calibration.pdf"
    drawing = canvas.Canvas(str(source), pagesize=(612, 792))

    drawing.setFont("Helvetica", 12)
    drawing.drawString(72, 720, "Applicant Name:")
    drawing.rect(180, 700, 300, 32)
    drawing.drawString(72, 630, "Agree to terms:")
    drawing.rect(72, 600, 16, 16)
    drawing.drawString(72, 540, "Date:")
    drawing.line(180, 520, 320, 520)
    drawing.drawString(72, 450, "Address:")
    drawing.showPage()

    # These shapes resemble form geometry but have no field-like language.
    drawing.drawString(72, 720, "Section")
    drawing.rect(180, 700, 300, 32)
    drawing.drawString(72, 630, "Note")
    drawing.rect(72, 600, 16, 16)
    drawing.drawString(72, 540, "Decorative")
    drawing.line(180, 520, 320, 520)
    drawing.save()

    targets = detect_semantic_targets(Path(source))
    page_one = [target for target in targets if target.page == 1]
    page_two = [target for target in targets if target.page == 2]

    assert len(page_one) == 4
    assert page_two == []
    assert {(target.kind, target.label) for target in page_one} == {
        ("text", "Applicant Name:"),
        ("choice", "Agree to terms:"),
        ("date", "Date:"),
        ("text", "Address:"),
    }
    assert any(target.bbox.width >= 290 and target.bbox.height >= 30 for target in page_one)
    assert any(target.kind == "choice" and target.bbox.width <= 20 for target in page_one)
    assert any(target.kind == "date" and target.bbox.width >= 130 for target in page_one)


def test_repeated_table_geometry_does_not_promote_header_words(tmp_path):
    source = tmp_path / "table-negative.pdf"
    drawing = canvas.Canvas(str(source), pagesize=(612, 792))
    drawing.setFont("Helvetica", 10)
    drawing.drawString(72, 720, "Month")
    for row in range(3):
        y = 680 - row * 30
        for column in range(3):
            x = 72 + column * 110
            drawing.line(x, y, x + 90, y)
    drawing.save()

    targets = detect_semantic_targets(Path(source))

    assert targets == []


def test_large_box_uses_its_above_label_not_unrelated_text_below(tmp_path):
    source = tmp_path / "photo-with-footer.pdf"
    drawing = canvas.Canvas(str(source), pagesize=(612, 792))
    drawing.setFont("Helvetica", 11)
    drawing.drawString(380, 440, "Passport photo:")
    drawing.rect(380, 322, 140, 110)
    drawing.setFont("Helvetica", 9)
    drawing.drawString(72, 300, "Reviewer note: this is explanatory text")
    drawing.save()

    targets = detect_semantic_targets(Path(source))

    assert len(targets) == 1
    assert targets[0].kind == "image"
    assert targets[0].label == "Passport photo:"


def test_short_choice_cues_do_not_match_inside_textarea_words():
    kind, score, _ = classify_label("Travel notes:", region=BBox(72, 520, 300, 62), page_height=792)

    assert kind == "textarea"
    assert score == 0.72


def test_identifier_and_name_labels_do_not_match_short_date_or_choice_substrings():
    account_kind, _, _ = classify_label("Account no:", region=BBox(72, 520, 220, 18), page_height=792)
    phone_kind, _, _ = classify_label("Phone no:", region=BBox(72, 520, 220, 18), page_height=792)
    candidate_kind, _, _ = classify_label("Candidate name:", region=BBox(72, 520, 220, 18), page_height=792)

    assert account_kind == "text"
    assert phone_kind == "text"
    assert candidate_kind == "text"


def test_inferred_photo_and_signature_targets_begin_pending(tmp_path):
    source = tmp_path / "visual-targets.pdf"
    drawing = canvas.Canvas(str(source), pagesize=(612, 792))
    drawing.drawString(380, 440, "Passport photo:")
    drawing.rect(380, 322, 140, 110)
    drawing.drawString(72, 260, "Applicant signature:")
    drawing.line(180, 240, 420, 240)
    drawing.save()

    targets = detect_semantic_targets(source)
    manifest = create_manifest(targets)

    assert {target.kind for target in targets} == {"image", "signature"}
    assert all(target.review_required for target in targets)
    assert all(target["status"] == "pending" for target in manifest.targets)


def test_tall_address_region_is_multiline_and_exposes_intent_entity(tmp_path):
    source = tmp_path / "textarea.pdf"
    drawing = canvas.Canvas(str(source), pagesize=(612, 792))
    drawing.drawString(72, 700, "Residential address:")
    drawing.rect(180, 570, 300, 110)
    drawing.save()

    targets = detect_semantic_targets(Path(source))

    assert len(targets) == 1
    assert targets[0].kind == "textarea"
    assert any(entity["type"] == "ADDRESS_FIELD" for entity in targets[0].label_entities)


def test_thin_signature_line_is_manifest_safe(tmp_path):
    source = tmp_path / "signature-line.pdf"
    drawing = canvas.Canvas(str(source), pagesize=(612, 792))
    drawing.drawString(72, 700, "Applicant signature:")
    drawing.line(180, 680, 420, 680)
    drawing.save()

    targets = detect_semantic_targets(Path(source))

    assert len(targets) == 1
    assert targets[0].kind == "signature"
    assert targets[0].bbox.height >= 4
