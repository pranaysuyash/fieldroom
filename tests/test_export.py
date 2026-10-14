from pathlib import Path

from pypdf import PdfReader

from pdf_field_lab.export_pdf import export_editable
from pdf_field_lab.fill_pdf import fill_editable
from pdf_field_lab.inspect_pdf import inspect_pdf
from pdf_field_lab.native_detect import detect_native_targets
from pdf_field_lab.profiles.form6 import form6_fields
from pdf_field_lab.models import BBox, FieldSpec


FIXTURE = Path(__file__).parents[1] / "data" / "samples" / "RAr0Lq2Avu.pdf"


def test_export_reopens_and_creates_acroform(tmp_path):
    output = tmp_path / "form6-editable.pdf"
    result = export_editable(FIXTURE, output, form6_fields())
    assert result["reopen_pages"] == 2
    assert result["reopen_native_fields"] >= 33
    reader = PdfReader(str(output))
    assert len(reader.pages) == 2
    assert len(reader.get_fields() or {}) >= 33
    assert output.read_bytes() != FIXTURE.read_bytes()


def test_generic_choice_target_can_be_checked_and_exported(tmp_path):
    editable = tmp_path / "generic-editable.pdf"
    filled = tmp_path / "generic-filled.pdf"
    target = FieldSpec(
        id="generic-choice", page=1, label="Unlabeled checkbox", kind="choice",
        bbox=BBox(500, 100, 14, 14), editable_strategy="acroform-checkbox",
    )
    export_editable(FIXTURE, editable, [target])
    result = fill_editable(editable, filled, [target], {"generic-choice": "selected"})
    assert result["choice_fields_matched"] == ["generic-choice"]
    fields = PdfReader(str(filled)).get_fields() or {}
    assert fields["generic-choice_0"]["/V"] == "/Yes"


def test_textarea_export_preserves_multiline_native_semantics(tmp_path):
    editable = tmp_path / "textarea-editable.pdf"
    target = FieldSpec(
        id="comments", page=1, label="Additional comments:", kind="textarea",
        bbox=BBox(80, 120, 240, 70), editable_strategy="acroform-text",
    )

    export_editable(FIXTURE, editable, [target])
    targets = detect_native_targets(inspect_pdf(editable))

    assert len(targets) == 1
    assert targets[0].kind == "textarea"


def test_mixed_export_preserves_existing_native_field_tree(tmp_path):
    native_source = tmp_path / "native-source.pdf"
    mixed_output = tmp_path / "mixed-output.pdf"
    seed = FieldSpec(
        id="native-existing", page=1, label="Existing", kind="text",
        bbox=BBox(80, 120, 240, 24), editable_strategy="acroform-text",
    )
    export_editable(FIXTURE, native_source, [seed])
    native_target = detect_native_targets(inspect_pdf(native_source))[0]
    inferred = FieldSpec(
        id="inferred-added", page=1, label="Added review target", kind="text",
        bbox=BBox(80, 180, 240, 24), editable_strategy="acroform-text",
    )

    result = export_editable(native_source, mixed_output, [native_target, inferred])
    fields = PdfReader(str(mixed_output)).get_fields() or {}

    assert native_target.editable_strategy == "native"
    assert result["reopen_native_fields"] >= 2
    assert "native-existing" in fields
    assert "inferred-added" in fields
