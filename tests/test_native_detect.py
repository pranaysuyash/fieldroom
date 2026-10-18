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


def test_hierarchical_parent_child_acroform_widgets_inherit_type_flags_and_disambiguate_ids(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, NumberObject, TextStringObject
    from pdf_field_lab.inspect_pdf import inspect_pdf

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    parent_field = DictionaryObject({
        NameObject("/T"): TextStringObject("applicant_gender"),
        NameObject("/TU"): TextStringObject("Applicant Gender"),
        NameObject("/FT"): NameObject("/Btn"),
        NameObject("/Ff"): NumberObject(32768),
        NameObject("/Opt"): ArrayObject([TextStringObject("Female"), TextStringObject("Male")]),
    })
    parent_ref = writer._add_object(parent_field)

    child1 = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/Rect"): ArrayObject([FloatObject(72), FloatObject(700), FloatObject(88), FloatObject(716)]),
        NameObject("/Parent"): parent_ref,
    })
    child2 = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/Rect"): ArrayObject([FloatObject(140), FloatObject(700), FloatObject(156), FloatObject(716)]),
        NameObject("/Parent"): parent_ref,
    })
    child1_ref = writer._add_object(child1)
    child2_ref = writer._add_object(child2)
    parent_field[NameObject("/Kids")] = ArrayObject([child1_ref, child2_ref])
    page[NameObject("/Annots")] = ArrayObject([child1_ref, child2_ref])
    writer._root_object[NameObject("/AcroForm")] = DictionaryObject({
        NameObject("/Fields"): ArrayObject([parent_ref]),
    })

    pdf_path = tmp_path / "hierarchical-radio.pdf"
    with pdf_path.open("wb") as handle:
        writer.write(handle)

    inspected = inspect_pdf(pdf_path)
    targets = detect_native_targets(inspected)

    assert len(targets) == 2
    assert [t.id for t in targets] == ["applicant_gender", "applicant_gender-2"]
    assert all(t.kind == "choice" for t in targets)
    assert all(t.editable_strategy == "native-radio" for t in targets)
    assert all(t.label == "Applicant Gender" for t in targets)
    assert [opt["value"] for opt in targets[0].options] == ["Female", "Male"]

