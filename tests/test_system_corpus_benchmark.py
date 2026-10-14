import json
import sys
from pathlib import Path

from PIL import Image
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from system_corpus_benchmark import _detector_summary, _read_manifest, _render_contact_sheet


def test_read_manifest_accepts_jsonl_plain_paths_arrays_and_relative_entries(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        "\n".join([
            json.dumps({"path": "/tmp/absolute.pdf"}),
            json.dumps({"file": "relative.pdf"}),
            json.dumps([{"pdf": "array.pdf"}, "relative.pdf"]),
            "plain.pdf",
        ]) + "\n",
        encoding="utf-8",
    )

    assert _read_manifest(manifest) == [
        Path("/tmp/absolute.pdf"),
        tmp_path / "relative.pdf",
        tmp_path / "array.pdf",
        tmp_path / "plain.pdf",
    ]


def test_contact_sheet_renders_measured_detector_targets(tmp_path):
    source = tmp_path / "fixture.pdf"
    drawing = canvas.Canvas(str(source), pagesize=(200, 300))
    drawing.drawString(20, 270, "Name:")
    drawing.save()

    result = _render_contact_sheet([{
        "path": str(source),
        "source_bucket": "test",
        "category": "form_or_agreement",
        "detector": {"page_one_targets": [{
            "bbox": {"x": 20, "y": 20, "width": 80, "height": 18},
            "kind": "text",
        }]},
    }], tmp_path / "visual")

    assert result["rendered_count"] == 1
    image = Image.open(result["contact_sheet"]).convert("RGB")
    assert any(pixel == (23, 107, 135) for pixel in image.getdata())


def test_detector_summary_skips_oversized_input_before_pdfplumber(tmp_path):
    record = {"path": str(tmp_path / "large.pdf"), "size_bytes": 21}

    summary = _detector_summary(record, max_analysis_bytes=20)

    assert summary["analysis_error"] is None
    assert summary["skipped_reason"] == "size_bytes>20"
