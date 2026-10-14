from pathlib import Path

from PIL import Image
from pypdf import PdfReader
import pymupdf

from pdf_field_lab.export_pdf import export_editable
from pdf_field_lab.fill_pdf import fill_editable
from pdf_field_lab.models import BBox, FieldSpec
from pdf_field_lab.profiles.form6 import form6_fields


FIXTURE = Path(__file__).parents[1] / "data" / "samples" / "RAr0Lq2Avu.pdf"


def test_fill_text_choice_and_image_placement(tmp_path):
    editable = tmp_path / "editable.pdf"
    output = tmp_path / "filled.pdf"
    photo = tmp_path / "photo.png"
    Image.new("RGB", (32, 48), (220, 40, 40)).save(photo)
    export_editable(FIXTURE, editable, form6_fields())
    result = fill_editable(editable, output, form6_fields(), {
        "F6-01": "OFFICE-EXAMPLE",
        "F6-09": "father",
        "F6-04": str(photo),
    })
    assert result["reopen_pages"] == 2
    assert "F6-09" in result["choice_fields_matched"]
    assert "F6-04" in result["image_or_signature_regions_placed"]
    fields = PdfReader(str(output)).get_fields() or {}
    assert fields["F6-01"]["/V"] == "OFFICE-EXAMPLE"
    document = pymupdf.open(str(output))
    try:
        assert "OFFICE-EXAMPLE" in document[0].get_text()
    finally:
        document.close()


def test_character_grid_accepts_one_string_and_reports_visual_placement(tmp_path):
    editable = tmp_path / "grid-editable.pdf"
    output = tmp_path / "grid-filled.pdf"
    target = FieldSpec(
        id="grid-name", page=1, label="Name", kind="text",
        bbox=BBox(80, 250, 140, 16), editable_strategy="character-grid",
        input_mode="character-grid", max_length=10,
    )
    export_editable(FIXTURE, editable, [target])
    result = fill_editable(editable, output, [target], {"grid-name": "Alice"})
    assert result["character_grid_fields_filled"] == ["grid-name"]
    assert result["text_fields_filled"] == []
    assert output.is_file()


def test_form6_name_grid_preserves_both_printed_rows_and_fills_them(tmp_path):
    fields = form6_fields()
    official_name = next(field for field in fields if field.id == "F6-05")
    assert official_name.bbox.y == 209
    assert official_name.bbox.height == 29
    assert [row["cell_count"] for row in official_name.grid_rows] == [14, 28]

    editable = tmp_path / "grid-rows-editable.pdf"
    output = tmp_path / "grid-rows-filled.pdf"
    export_editable(FIXTURE, editable, fields)
    result = fill_editable(editable, output, fields, {
        "F6-05": "Asha Dorje",
    })
    assert result["character_grid_fields_filled"] == ["F6-05"]
    assert output.is_file()


def test_form6_visual_audit_preserves_mobile_and_mixed_child_regions():
    fields = {field.id: field for field in form6_fields()}
    mobile = fields["F6-12"]
    assert mobile.input_mode == "character-grid"
    assert [row["cell_count"] for row in mobile.grid_rows] == [10, 10]
    assert mobile.grid_rows[0]["bbox"]["y"] == 489
    assert mobile.grid_rows[1]["bbox"]["y"] == 503

    aadhaar = {item["value"]: item["bbox"] for item in fields["F6-14"].options}
    assert aadhaar["aadhaar_digits"] == {"x": 205, "y": 560, "width": 233, "height": 14}

    disability = {item["value"]: item["bbox"] for item in fields["F6-24"].options}
    assert disability["percentage"] == {"x": 125, "y": 250, "width": 18, "height": 18}

    family = {item["value"]: item["bbox"] for item in fields["F6-25"].options}
    assert family["name"]["y"] == 296
    assert family["epic"]["y"] == 316

    date_place = {item["value"]: item["bbox"] for item in fields["F6-29"].options}
    assert date_place["date"]["x"] == 45
    assert date_place["place"]["x"] == 45
    assert fields["F6-30"].bbox.height == 14


def test_composite_field_accepts_structured_subfields_from_one_task(tmp_path):
    editable = tmp_path / "composite-editable.pdf"
    output = tmp_path / "composite-filled.pdf"
    target = FieldSpec(
        id="constituency", page=1, label="Constituency", kind="composite",
        bbox=BBox(80, 250, 140, 16), editable_strategy="acroform-multiline",
        options=[
            {"value": "number", "label": "Number", "bbox": BBox(80, 250, 30, 16).as_dict()},
            {"value": "name", "label": "Name", "bbox": BBox(110, 250, 110, 16).as_dict()},
        ],
    )
    export_editable(FIXTURE, editable, [target])
    result = fill_editable(editable, output, [target], {
        "constituency": {"number": "12", "name": "Central"},
    })
    assert set(result["text_fields_filled"]) == {"constituency_number", "constituency_name"}
    assert output.is_file()
