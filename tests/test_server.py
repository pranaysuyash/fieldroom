import base64
import hashlib
import io
import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from PIL import Image

from pdf_field_lab.server import (SESSION_ROOT, SESSION_TTL_SECONDS, SESSIONS, Session,
                                  app, _AUDIT_PATH, _canonical_sha256)


FIXTURE = Path(__file__).parents[1] / "data" / "samples" / "RAr0Lq2Avu.pdf"
LOCAL_CONFIG = Path(__file__).parent / "local" / "medpiper.local.json"

_requires_medpiper = pytest.mark.skipif(
    not LOCAL_CONFIG.is_file(),
    reason="local Medpiper fixture not configured; see tests/local/README.md",
)


def _medpiper_config():
    return json.loads(LOCAL_CONFIG.read_text(encoding="utf-8"))


def _accept_all(manifest):
    accepted = {**manifest, "targets": [
        {**target, "status": "accepted"} for target in manifest["targets"]
    ]}
    return accepted


def _png_data_url() -> str:
    output = io.BytesIO()
    Image.new("RGB", (16, 20), (225, 55, 55)).save(output, format="PNG")
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def test_browser_session_upload_page_and_export_flow():
    with TestClient(app) as client, FIXTURE.open("rb") as handle:
        response = client.post("/api/sessions", files={"file": ("form6.pdf", handle, "application/pdf")})
    assert response.status_code == 200, response.text
    session = response.json()
    assert session["session_id"]
    assert len(session["pages"]) == 2
    assert len(session["targets"]) == 33

    with TestClient(app) as client:
        pending = client.post(f"/api/sessions/{session['session_id']}/export", json={"values": {}})
        assert pending.status_code == 409
        updated = client.put(f"/api/sessions/{session['session_id']}/manifest",
                             json=_accept_all(session["manifest"]))
        assert updated.status_code == 200, updated.text
        assert updated.json()["revision"] == 1
        page = client.get(session["pages"][0]["image_url"])
        assert page.status_code == 200
        assert page.headers["content-type"].startswith("image/png")
        exported = client.post(f"/api/sessions/{session['session_id']}/export", json={
            "values": {"F6-01": "BROWSER-OFFICE", "F6-04": _png_data_url()}
        })
        assert exported.status_code == 200, exported.text
        receipt = exported.json()
        assert "F6-01" in receipt["fill"]["text_fields_filled"]
        assert "F6-04" in receipt["fill"]["image_or_signature_regions_placed"]
        download = client.get(receipt["download_url"])
        assert download.status_code == 200
        reader = PdfReader(io.BytesIO(download.content), strict=False)
        assert len(reader.pages) == 2
        assert len(reader.get_fields() or {}) >= 33


def test_manifest_rejects_stale_revision_and_out_of_bounds_page():
    with TestClient(app) as client, FIXTURE.open("rb") as handle:
        response = client.post("/api/sessions", files={"file": ("form6.pdf", handle, "application/pdf")})
    assert response.status_code == 200
    session = response.json()
    manifest = _accept_all(session["manifest"])
    manifest["targets"][0]["page"] = 999
    with TestClient(app) as client:
        invalid = client.put(f"/api/sessions/{session['session_id']}/manifest", json=manifest)
        assert invalid.status_code == 422
        stale = client.put(f"/api/sessions/{session['session_id']}/manifest",
                           json=_accept_all(session["manifest"]))
        assert stale.status_code == 200
        conflict = client.put(f"/api/sessions/{session['session_id']}/manifest",
                              json=_accept_all(session["manifest"]))
        assert conflict.status_code == 409
        assert client.get(f"/api/sessions/{session['session_id']}/pages/0.png").status_code == 404
        assert client.get(f"/api/sessions/{session['session_id']}/pages/999.png").status_code == 404


def test_export_rebuilds_from_accepted_manifest_revision():
    with TestClient(app) as client, FIXTURE.open("rb") as handle:
        response = client.post("/api/sessions", files={"file": ("editable.pdf", handle, "application/pdf")})
    assert response.status_code == 200, response.text
    session = response.json()
    manifest = _accept_all(session["manifest"])
    moved = manifest["targets"][0]
    moved["bbox"] = {**moved["bbox"], "x": moved["bbox"]["x"] - 40, "y": moved["bbox"]["y"] + 8}
    manifest["targets"][1]["status"] = "rejected"
    manifest["targets"].append({
        "id": "manual-added",
        "page": 1,
        "label": "Manual field",
        "kind": "text",
        "component": "text-field",
        "bbox": {"x": 80, "y": 180, "width": 120, "height": 16},
        "editable_strategy": "acroform-text",
        "status": "accepted",
        "evidence": [{"source": "manual", "score": 1, "detail": "test"}],
    })

    with TestClient(app) as client:
        updated = client.put(f"/api/sessions/{session['session_id']}/manifest", json=manifest)
        assert updated.status_code == 200, updated.text
        exported = client.post(f"/api/sessions/{session['session_id']}/export", json={"values": {}})
        assert exported.status_code == 200, exported.text
        receipt = exported.json()
        downloaded = client.get(receipt["download_url"])
    assert downloaded.status_code == 200

    reader = PdfReader(io.BytesIO(downloaded.content), strict=False)
    field_names = set((reader.get_fields() or {}).keys())
    assert "F6-01" in field_names
    assert "F6-02_number" not in field_names
    assert "manual-added" in field_names
    f6_01 = next(
        annotation_ref.get_object()
        for annotation_ref in reader.pages[0]["/Annots"]
        if annotation_ref.get_object().get("/T") == "F6-01"
    )
    assert round(float(f6_01["/Rect"][0]), 3) == 465
    assert round(float(f6_01["/Rect"][1]), 3) == 763.68
    assert receipt["manifest_revision"] == 1
    assert receipt["output_sha256"] == hashlib.sha256(downloaded.content).hexdigest()
    assert receipt["source_sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert session["filename"] == "editable.pdf"


def test_download_url_is_bound_to_manifest_and_values_revision():
    with TestClient(app) as client, FIXTURE.open("rb") as handle:
        response = client.post("/api/sessions", files={"file": ("editable.pdf", handle, "application/pdf")})
    assert response.status_code == 200, response.text
    session = response.json()
    manifest = _accept_all(session["manifest"])
    with TestClient(app) as client:
        updated = client.put(f"/api/sessions/{session['session_id']}/manifest", json=manifest)
        assert updated.status_code == 200, updated.text
        first = client.post(f"/api/sessions/{session['session_id']}/export", json={
            "values": {"F6-01": "FIRST-VALUE"},
        })
        second = client.post(f"/api/sessions/{session['session_id']}/export", json={
            "values": {"F6-01": "SECOND-VALUE"},
        })
        assert first.status_code == 200 and second.status_code == 200
        first_receipt = first.json()
        second_receipt = second.json()
        assert first_receipt["manifest_revision"] == second_receipt["manifest_revision"]
        assert first_receipt["values_sha256"] != second_receipt["values_sha256"]
        assert first_receipt["download_url"] != second_receipt["download_url"]
        first_download = client.get(first_receipt["download_url"])
        second_download = client.get(second_receipt["download_url"])
    assert first_download.status_code == 200
    assert second_download.status_code == 200
    assert first_download.content != second_download.content


def test_upload_rejects_non_pdf_and_oversized_content():
    with TestClient(app) as client:
        non_pdf = client.post("/api/sessions", files={"file": ("notes.pdf", b"not a pdf", "application/pdf")})
        assert non_pdf.status_code == 415
        oversized = client.post("/api/sessions", files={"file": ("large.pdf", b"%PDF-" + b"x" * (25 * 1024 * 1024), "application/pdf")})
        assert oversized.status_code == 413


def test_upload_rejects_page_limit():
    writer = PdfWriter()
    for _ in range(251):
        writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    with TestClient(app) as client:
        response = client.post("/api/sessions", files={"file": ("many-pages.pdf", buffer, "application/pdf")})
    assert response.status_code == 413
    assert "page limit" in response.json()["detail"]


def test_manifest_rejects_target_limit():
    with TestClient(app) as client, FIXTURE.open("rb") as handle:
        response = client.post("/api/sessions", files={"file": ("form6.pdf", handle, "application/pdf")})
    assert response.status_code == 200
    session = response.json()
    manifest = _accept_all(session["manifest"])
    template = manifest["targets"][0]
    targets = []
    for index in range(1001):
        item = deepcopy(template)
        item["id"] = f"limit-{index}"
        item["status"] = "pending"
        targets.append(item)
    manifest["targets"] = targets
    with TestClient(app) as client:
        response = client.put(f"/api/sessions/{session['session_id']}/manifest", json=manifest)
    assert response.status_code == 422
    assert "at most 1000" in response.json()["detail"]


def test_review_candidates_export_governs_review_events():
    with TestClient(app) as client, FIXTURE.open("rb") as handle:
        created = client.post("/api/sessions", files={"file": ("form6.pdf", handle, "application/pdf")})
    assert created.status_code == 200
    session = created.json()

    with TestClient(app) as client:
        untouched = client.get(f"/api/sessions/{session['session_id']}/review-candidates.jsonl")
        assert untouched.status_code == 404

        manifest = session["manifest"]
        manifest["targets"][0]["status"] = "accepted"
        moved = manifest["targets"][1]
        moved["bbox"]["x"] = moved["bbox"]["x"] + 3
        manual = deepcopy(manifest["targets"][2])
        manual.update({"id": "manual-check", "label": "Manually added field", "status": "pending"})
        manifest["targets"].append(manual)
        updated = client.put(f"/api/sessions/{session['session_id']}/manifest", json=manifest)
        assert updated.status_code == 200, updated.text

        exported = client.get(f"/api/sessions/{session['session_id']}/review-candidates.jsonl")
        assert exported.status_code == 200
        events = [json.loads(line) for line in exported.text.splitlines() if line.strip()]
        by_event = {item["event"] for item in events}
        assert {"accepted", "moved", "added-manual"} <= by_event
        manual_event = next(item for item in events if item["event"] == "added-manual")
        assert manual_event["manual"] is True
        assert manual_event["target"]["id"] == "manual-check"
        assert len(manual_event["source_sha256"]) == 64


@_requires_medpiper
def test_medpiper_upload_exposes_signature_audit_without_editable_targets():
    config = _medpiper_config()
    with TestClient(app) as client, Path(config["pdf"]).open("rb") as handle:
        response = client.post("/api/sessions", files={"file": ("medpiper.pdf", handle, "application/pdf")})
    assert response.status_code == 200, response.text
    session = response.json()
    assert session["targets"] == []
    assert len(session["signature_observations"]) == 12
    missing = [item for item in session["signature_observations"]
               if item["page"] in {2, 20} and item["signer"] == config["missing_signer"]]
    assert len(missing) == 2
    assert all(item["status"] == "missing" for item in missing)
    assert len(session["audit_log"]) == 12
    analysis_snapshot = SESSION_ROOT / session["session_id"] / "analysis.json"
    assert analysis_snapshot.is_file()


def _audit_lines():
    if not _AUDIT_PATH.is_file():
        return []
    return [json.loads(line) for line in _AUDIT_PATH.read_text().splitlines() if line]


def test_manifest_change_writes_hash_bound_review_receipt(monkeypatch):
    monkeypatch.setenv("PDF_FIELD_LAB_REVIEWER", "test-reviewer")
    with TestClient(app) as client, FIXTURE.open("rb") as handle:
        response = client.post("/api/sessions", files={"file": ("form6.pdf", handle, "application/pdf")})
    assert response.status_code == 200
    session = response.json()
    manifest = _accept_all(session["manifest"])
    with TestClient(app) as client:
        updated = client.put(f"/api/sessions/{session['session_id']}/manifest", json=manifest)
        assert updated.status_code == 200
        receipts_response = client.get(f"/api/sessions/{session['session_id']}/review-receipts.jsonl")
    assert receipts_response.status_code == 200
    receipt = json.loads(receipts_response.text.splitlines()[-1])
    assert receipt["reviewer"] == "test-reviewer"
    assert receipt["revision"] == session["manifest"]["revision"] + 1
    assert receipt["previous_revision"] == session["manifest"]["revision"]
    assert receipt["recorded_at"]
    assert receipt["manifest_sha256"] != receipt["previous_manifest_sha256"]
    assert receipt["event_count"] > 0
    assert receipt["signals"]["agreement"] == receipt["event_count"]
    content_sha = _canonical_sha256({k: v for k, v in receipt.items() if k != "receipt_sha256"})
    assert receipt["receipt_sha256"] == content_sha
    candidates = client.get(f"/api/sessions/{session['session_id']}/review-candidates.jsonl")
    assert hashlib.sha256(candidates.text.encode("utf-8")).hexdigest() == receipt["candidates_sha256"]


def test_stale_revision_replay_records_no_second_receipt():
    with TestClient(app) as client, FIXTURE.open("rb") as handle:
        response = client.post("/api/sessions", files={"file": ("form6.pdf", handle, "application/pdf")})
    session = response.json()
    manifest = _accept_all(session["manifest"])
    with TestClient(app) as client:
        first = client.put(f"/api/sessions/{session['session_id']}/manifest", json=manifest)
        assert first.status_code == 200
        replay = client.put(f"/api/sessions/{session['session_id']}/manifest", json=manifest)
        assert replay.status_code == 409
        receipts_response = client.get(f"/api/sessions/{session['session_id']}/review-receipts.jsonl")
    assert len(receipts_response.text.splitlines()) == 1


def test_active_content_is_quarantined_with_operator_visible_reason():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_js("app.alert(1);")
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    audit_before = len(_audit_lines())
    with TestClient(app) as client:
        response = client.post("/api/sessions", files={"file": ("active.pdf", buffer, "application/pdf")})
    assert response.status_code == 422
    assert "quarantined" in response.json()["detail"]
    assert "javascript" in response.json()["detail"]
    new_lines = _audit_lines()[audit_before:]
    assert any(item["kind"] == "upload-quarantined" for item in new_lines)


def test_encrypted_pdf_is_rejected_and_audited():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    audit_before = len(_audit_lines())
    with TestClient(app) as client:
        response = client.post("/api/sessions", files={"file": ("locked.pdf", buffer, "application/pdf")})
    assert response.status_code == 422
    new_lines = _audit_lines()[audit_before:]
    # With qpdf on PATH the structural scan rejects it first; without qpdf the
    # encrypted-upload check does. Either way the rejection must be audited.
    assert any(item["kind"] in {"upload-encrypted", "structural-scan-failed"} for item in new_lines)


def test_upload_rejections_are_recorded_in_shared_audit_ledger():
    audit_before = len(_audit_lines())
    with TestClient(app) as client:
        response = client.post("/api/sessions", files={"file": ("notes.pdf", b"not a pdf", "application/pdf")})
    assert response.status_code == 415
    new_lines = _audit_lines()[audit_before:]
    assert any(item["kind"] == "upload-rejected" and item["status"] == 415 for item in new_lines)


def test_expired_session_directories_are_swept_and_audited():
    import os
    import time
    stale_dir = SESSION_ROOT / ("0" * 32)
    stale_dir.mkdir(parents=True, exist_ok=True)
    old = time.time() - (SESSION_TTL_SECONDS + 60)
    os.utime(stale_dir, (old, old))
    audit_before = len(_audit_lines())
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
    assert not stale_dir.exists()
    new_lines = _audit_lines()[audit_before:]
    assert any(item["kind"] == "session-expired" for item in new_lines)


def test_vanished_session_storage_returns_explicit_404(tmp_path):
    import threading
    ghost = Session(
        id="f" * 32, display_filename="ghost.pdf", directory=tmp_path / "vanished",
        source=tmp_path / "vanished" / "source.pdf", editable=tmp_path / "vanished" / "e.pdf",
        report=None, manifest=None, lock=threading.RLock(), created_at=0.0, security={})
    SESSIONS[ghost.id] = ghost
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/sessions/{ghost.id}/manifest")
        assert response.status_code == 404
        assert response.json()["detail"] == "session storage expired"
        assert ghost.id not in SESSIONS
    finally:
        SESSIONS.pop(ghost.id, None)
