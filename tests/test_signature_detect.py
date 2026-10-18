import io
import json
import os
from pathlib import Path

import fitz
import pytest
from PIL import Image

from pdf_field_lab.analysis import analyze
from pdf_field_lab.signature_detect import detect_signature_observations


LOCAL_CONFIG = Path(__file__).parent / "local" / "medpiper.local.json"


def _medpiper_available() -> bool:
    if not LOCAL_CONFIG.is_file():
        return False
    try:
        cfg = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8"))
        pdf_path = Path(cfg.get("pdf", ""))
        return pdf_path.is_file() and os.access(pdf_path, os.R_OK)
    except OSError:
        return False


_requires_medpiper = pytest.mark.skipif(
    not _medpiper_available(),
    reason="local Medpiper fixture not configured or not readable in current sandbox; see tests/local/README.md",
)


@_requires_medpiper
def test_medpiper_signature_audit_detects_present_and_missing_slots():
    config = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8"))
    report = analyze(Path(config["pdf"]))
    observations = report.signature_observations
    order = config["page_one_order"]
    missing_signer = config["missing_signer"]

    page_one = [item for item in observations if item.page == 1]
    assert [(item.signer, item.status) for item in page_one] == [
        (name, "present") for name in order
    ]

    for page in (2, 20):
        page_map = {item.signer: item for item in observations if item.page == page}
        assert page_map[missing_signer].status == "missing"
        for name in order:
            if name != missing_signer:
                assert page_map[name].status == "present"

    assert not [item for item in observations if item.page == 18]
    assert len(report.audit_log) == len(observations)


def test_synthetic_multi_signer_audit_detects_embedded_ink_missing_and_abstains(tmp_path):
    pdf_path = tmp_path / "synthetic-multi-signer.pdf"
    doc = fitz.open()
    try:
        # Page 1: 3-signer block in lower half of page (y >= 0.55 * 792 = 435.6)
        page1 = doc.new_page(width=612, height=792)
        # Signer 1 (x=72): name at y=620, role at y=632 + embedded signature image in slot [67, 570, 172, 608]
        page1.insert_textbox(
            fitz.Rect(72, 610, 190, 650),
            "Alice Vance\nDirector",
            fontsize=10,
        )
        sig_img = io.BytesIO()
        Image.new("RGB", (60, 24), (20, 20, 80)).save(sig_img, format="PNG")
        page1.insert_image(fitz.Rect(75, 574, 160, 602), stream=sig_img.getvalue())

        # Signer 2 (x=240): name at y=620, role at y=632 + dark raster ink stroke in slot above name
        page1.insert_textbox(
            fitz.Rect(240, 610, 360, 650),
            "Bob Sterling\nPartner",
            fontsize=10,
        )
        shape = page1.new_shape()
        shape.draw_line(fitz.Point(245, 586), fitz.Point(325, 592))
        shape.draw_line(fitz.Point(250, 592), fitz.Point(315, 582))
        shape.finish(color=(0.05, 0.05, 0.05), width=2.2)
        shape.commit()

        # Signer 3 (x=410): name at y=620, role at y=632 + empty slot above name
        page1.insert_textbox(
            fitz.Rect(410, 610, 540, 650),
            "Clara Moreau\nSecretary",
            fontsize=10,
        )

        # Page 2: single role word only -> must abstain
        page2 = doc.new_page(width=612, height=792)
        page2.insert_textbox(
            fitz.Rect(72, 610, 200, 650),
            "Solo Person\nDirector",
            fontsize=10,
        )
        doc.save(str(pdf_path))
    finally:
        doc.close()

    observations = detect_signature_observations(pdf_path)
    assert len(observations) == 3
    by_signer = {obs.signer: obs for obs in observations}
    assert set(by_signer) == {"Alice Vance", "Bob Sterling", "Clara Moreau"}
    assert by_signer["Alice Vance"].status == "present"
    assert by_signer["Alice Vance"].source_refs
    assert by_signer["Bob Sterling"].status == "present"
    assert by_signer["Clara Moreau"].status == "missing"
    assert all(obs.page == 1 for obs in observations)

