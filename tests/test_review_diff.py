"""Pure-function tests for the review-candidate flywheel."""

from pdf_field_lab.review_diff import (
    candidate_record_stub,
    candidates_to_jsonl,
    review_candidates,
)


def _manifest(targets, revision=1):
    return {"revision": revision, "targets": targets}


def _target(target_id, *, status="pending", x=10.0, label="Name"):
    return {
        "id": target_id,
        "page": 1,
        "label": label,
        "kind": "text",
        "status": status,
        "bbox": {"x": x, "y": 40.0, "width": 120.0, "height": 18.0},
        "evidence": [],
    }


def _events(candidates):
    return sorted((item["event"], item["target"]["id"]) for item in candidates)


def test_accept_reject_and_restore_are_distinct_events():
    previous = _manifest([_target("a"), _target("b"), _target("c", status="rejected")])
    current = _manifest([
        dict(_target("a"), status="accepted"),
        dict(_target("b"), status="rejected"),
        dict(_target("c"), status="pending"),
    ], revision=2)
    candidates = review_candidates(previous, current, source_sha256="f" * 64, session_id="s1")
    assert _events(candidates) == [("accepted", "a"), ("rejected", "b"), ("restored", "c")]
    assert all(item["revision"] == 2 for item in candidates)
    assert all(item["source_sha256"] == "f" * 64 for item in candidates)


def test_manual_add_detection_move_and_remove():
    previous = _manifest([_target("keep", x=10.0), _target("gone")])
    manual = _target("manual-1", label="Drawn by hand")
    moved = _target("keep", x=25.0)
    current = _manifest([moved, manual], revision=3)
    candidates = review_candidates(previous, current, source_sha256="a" * 64, session_id="s2")
    assert _events(candidates) == [("added-manual", "manual-1"), ("moved", "keep"), ("removed", "gone")]
    moved_event = next(item for item in candidates if item["event"] == "moved")
    assert moved_event["detail"]["previous_bbox"]["x"] == 10.0
    assert moved_event["manual"] is False
    assert next(item for item in candidates if item["event"] == "added-manual")["manual"] is True


def test_jsonl_roundtrip_is_stable_and_idempotent():
    previous = _manifest([_target("a")])
    current = _manifest([dict(_target("a"), status="accepted")], revision=1)
    first = candidates_to_jsonl(review_candidates(previous, current, source_sha256="b" * 64, session_id="s3"))
    second = candidates_to_jsonl(review_candidates(previous, current, source_sha256="b" * 64, session_id="s3"))
    assert first == second
    assert first.endswith("\n")


def test_candidate_record_stub_shapes_pending_repository_record():
    previous = _manifest([_target("a")])
    current = _manifest([dict(_target("a"), status="accepted")], revision=1)
    candidate = review_candidates(previous, current, source_sha256="c" * 64, session_id="s4")[0]
    record = candidate_record_stub(candidate)
    assert record["id"] == f"review-{'c' * 12}-{candidate['candidate_id']}"
    assert record["family_id"] == f"review-session-{'c' * 12}"
    assert record["annotation"]["status"] == "pending"
    assert record["annotation"]["reviewer"] is None
    assert record["split"]["role"] == "not-for-training"
    assert record["source"]["privacy_class"] == "user-sensitive"


def test_governance_context_binds_reviewer_time_and_manifest_state():
    previous = _manifest([_target("a"), _target("b")])
    current = _manifest([
        dict(_target("a"), status="accepted"),
        dict(_target("b"), status="rejected"),
    ], revision=2)
    candidates = review_candidates(
        previous, current, source_sha256="d" * 64, session_id="s5",
        reviewer="pranay", recorded_at="2026-10-09T12:00:00+00:00",
        manifest_sha256="e" * 64,
    )
    assert all(item["reviewer"] == "pranay" for item in candidates)
    assert all(item["recorded_at"] == "2026-10-09T12:00:00+00:00" for item in candidates)
    assert all(item["manifest_sha256"] == "e" * 64 for item in candidates)
    signals = {item["event"]: item["signal"] for item in candidates}
    assert signals["accepted"] == "agreement"
    assert signals["rejected"] == "false-positive"


def test_signal_taxonomy_covers_miss_correction_and_restore():
    previous = _manifest([_target("det"), _target("rej", status="rejected")])
    moved = {**_target("det"), "bbox": {**_target("det")["bbox"], "x": 30.0}}
    manual = _target("manual-9")
    detected_add = _target("new-det")
    current = _manifest([moved, dict(_target("rej")), manual, detected_add], revision=4)
    candidates = review_candidates(previous, current, source_sha256="f" * 64, session_id="s6")
    signals = {item["event"]: item["signal"] for item in candidates}
    assert signals["moved"] == "geometry-correction"
    assert signals["restored"] == "review-correction"
    assert signals["added-manual"] == "detector-miss"
    assert signals["added-detection"] is None


def test_governance_fields_stay_absent_when_not_supplied():
    previous = _manifest([_target("a")])
    current = _manifest([dict(_target("a"), status="accepted")], revision=1)
    candidate = review_candidates(previous, current, source_sha256="1" * 64, session_id="s7")[0]
    assert "reviewer" not in candidate
    assert "recorded_at" not in candidate
    assert "manifest_sha256" not in candidate
    assert candidate["signal"] == "agreement"


def test_stub_keeps_label_authority_null_while_recording_session_trace():
    previous = _manifest([_target("a")])
    current = _manifest([dict(_target("a"), status="accepted")], revision=1)
    candidate = review_candidates(
        previous, current, source_sha256="2" * 64, session_id="s8",
        reviewer="pranay", recorded_at="2026-10-09T12:00:00+00:00",
        manifest_sha256="3" * 64,
    )[0]
    record = candidate_record_stub(candidate)
    assert record["annotation"]["reviewer"] is None
    assert "pranay" in record["provenance"]["lineage"]
    assert "3" * 64 in record["provenance"]["lineage"]
    assert any("agreement" in note for note in record["annotation"]["notes"])
