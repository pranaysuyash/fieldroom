from pdf_field_lab.models import PdfInspection
from pdf_field_lab.native_detect import detect_native_targets


def test_native_dropdown_is_typed_as_choice_and_keeps_native_strategy():
    inspection = PdfInspection(
        path="dropdown.pdf", sha256="test", pages=1,
        page_sizes=[{"width": 612.0, "height": 792.0}], metadata={},
        native_fields=[{
            "name": "country", "/FT": "/Ch", "/Opt": ["India", "Japan"],
        }],
        annotations=[{
            "page": 1, "subtype": "/Widget", "field_type": "/Ch",
            "name": "country", "rect": [72, 700, 200, 724], "flags": 0,
            "options": ["India", "Japan"],
        }],
        text_chars_by_page=[100],
    )

    targets = detect_native_targets(inspection)

    assert len(targets) == 1
    assert targets[0].kind == "choice"
    assert targets[0].editable_strategy == "native-choice"
    assert [item["value"] for item in targets[0].options] == ["India", "Japan"]
