import pytest

from pdf_field_lab.target_model import train_target_model
from pdf_field_lab.training_data import _doclaynet_records, _funsd_records


def test_advisory_target_model_trains_and_records_provenance():
    records = []
    examples = {
        "text": "full name",
        "date": "date of birth",
        "choice": "gender choice",
        "image": "passport photo",
        "signature": "applicant signature",
        "textarea": "additional comments",
        "negative": "page header",
    }
    for kind, label in examples.items():
        for index in range(2):
            records.append({
                "source": "synthetic-test", "group": f"{kind}-group",
                "label": label, "kind": kind, "bbox": [10, 10 + index, 100, 20],
                "page_width": 600, "page_height": 800, "supervision": "synthetic-test",
            })
    _, receipt = train_target_model(records)
    assert receipt["record_count"] == 14
    assert receipt["supervision"] == "weak-and-reviewed-mixed; not a field-level gold benchmark"
    assert set(receipt["class_counts"]) == set(examples)


def test_local_proxy_dataset_geometry_is_normalized():
    # The FUNSD/DocLayNet corpora live in the machine-local sibling project
    # and are deliberately not distributed; skip where they are absent
    # (CI, fresh clones) instead of failing on an environment gap.
    if not _funsd_records() and not _doclaynet_records():
        pytest.skip("local sibling proxy datasets not available")
    funsd = _funsd_records()
    doclaynet = _doclaynet_records()

    assert funsd and doclaynet
    assert all(record["bbox"][2] >= 0 and record["bbox"][3] >= 0 for record in funsd)
    assert all(record["bbox"][2] > 0 and record["bbox"][3] > 0 for record in doclaynet)
