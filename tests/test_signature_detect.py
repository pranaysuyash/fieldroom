import json
from pathlib import Path

import pytest

from pdf_field_lab.analysis import analyze


LOCAL_CONFIG = Path(__file__).parent / "local" / "medpiper.local.json"

pytestmark = pytest.mark.skipif(
    not LOCAL_CONFIG.is_file(),
    reason="local Medpiper fixture not configured; see tests/local/README.md",
)


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
