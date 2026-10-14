"""Local browser application for PDF target detection and editing."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader

from datetime import datetime, timezone

from .analysis import analyze
from .config import positive_int_env
from .export_pdf import export_editable
from . import review_diff
from .fill_pdf import fill_editable
from .manifest import (ManifestValidationError, ReviewManifest, create_manifest,
                       validate_manifest)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BROWSER_ROOT = PROJECT_ROOT / "browser"
SESSION_ROOT = Path(tempfile.gettempdir()) / "pdf-field-lab-sessions"
SESSION_ROOT.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = positive_int_env("PDF_FIELD_LAB_MAX_UPLOAD_BYTES", 25 * 1024 * 1024)
MAX_PAGES = positive_int_env("PDF_FIELD_LAB_MAX_PAGES", 250)
MAX_TARGETS = positive_int_env("PDF_FIELD_LAB_MAX_TARGETS", 1000)
SESSION_TTL_SECONDS = positive_int_env("PDF_FIELD_LAB_SESSION_TTL_SECONDS", 3600)


@dataclass
class Session:
    id: str
    display_filename: str
    directory: Path
    source: Path
    editable: Path
    report: Any
    manifest: ReviewManifest
    lock: threading.RLock
    created_at: float
    security: dict[str, str]


SESSIONS: dict[str, Session] = {}
_AUDIT_PATH = SESSION_ROOT / "rejections.jsonl"
_audit_lock = threading.Lock()
app = FastAPI(title="PDF Field Lab", version="0.1.1")
app.mount("/assets", StaticFiles(directory=str(BROWSER_ROOT)), name="assets")


def _audit_event(record: dict[str, Any]) -> None:
    """Append one operator-visible governance event to the shared audit ledger.

    The ledger lives outside per-session directories so rejections survive the
    session cleanup that immediately follows them. It must never mask the
    operator-facing error, so write failures are swallowed by design.
    """
    entry = {"recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
    try:
        with _audit_lock, _AUDIT_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        pass


def _upload_reject(status: int, detail: str, kind: str = "upload-rejected",
                   filename: str | None = None) -> None:
    """Audit a session-creation rejection, then raise it."""
    _audit_event({
        "kind": kind,
        "status": status,
        "detail": detail[:300],
        "filename": filename,
    })
    raise HTTPException(status_code=status, detail=detail)


def _reviewer_identity() -> str:
    """Local operator attestation for review events.

    This is trace, not authentication: in a local-first single-operator tool
    the reviewer name is an explicit, recorded identity (env-configured), not
    a security boundary. Cryptographic reviewer signing is a separate decision.
    """
    return os.environ.get("PDF_FIELD_LAB_REVIEWER", "").strip() or "local-operator"


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cleanup_expired_sessions() -> None:
    """Remove only app-owned, UUID-shaped session directories past the TTL."""
    now = time.time()
    for directory in SESSION_ROOT.iterdir():
        if not directory.is_dir() or len(directory.name) != 32:
            continue
        try:
            if now - directory.stat().st_mtime > SESSION_TTL_SECONDS:
                shutil.rmtree(directory)
                SESSIONS.pop(directory.name, None)
                _audit_event({
                    "kind": "session-expired",
                    "status": 200,
                    "detail": "session directory removed after TTL",
                    "session_id": directory.name,
                })
        except FileNotFoundError:
            continue


def _active_content_report(path: Path) -> dict[str, bool]:
    """Detect executable or attached active content without executing anything.

    Categories (FFL-SEC-010 quarantine policy): document-level JavaScript,
    open actions, embedded files, and XFA. Detection only; nothing here runs
    or extracts the payload.
    """
    reader = PdfReader(str(path), strict=False)
    if reader.is_encrypted:
        return {}

    def _resolve(node: Any) -> Any:
        return node.get_object() if hasattr(node, "get_object") else node

    root = _resolve(reader.trailer.get("/Root")) or {}
    report: dict[str, bool] = {}
    if root.get("/OpenAction") is not None:
        report["open-action"] = True
    names = _resolve(root.get("/Names"))
    if names is not None and names.get("/JavaScript") is not None:
        report["javascript"] = True
    if names is not None and names.get("/EmbeddedFiles") is not None:
        report["embedded-files"] = True
    acroform = _resolve(root.get("/AcroForm"))
    if acroform is not None and acroform.get("/XFA") is not None:
        report["xfa"] = True
    return report


def _structural_scan(path: Path) -> dict[str, str]:
    """Run bounded local file checks without claiming malware detection."""
    qpdf = shutil.which("qpdf")
    qpdf_status = "not-configured"
    if qpdf:
        try:
            completed = subprocess.run(
                [qpdf, "--check", str(path)], capture_output=True, text=True,
                timeout=15, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            _upload_reject(422, "PDF structural validation timed out", kind="structural-scan-failed")
        if completed.returncode != 0:
            _upload_reject(422, "PDF structural validation failed", kind="structural-scan-failed")
        qpdf_status = "passed"
    scanner = shutil.which("clamscan") or shutil.which("clamdscan")
    malware_status = "not-configured"
    if scanner:
        try:
            completed = subprocess.run(
                [scanner, "--no-summary", str(path)], capture_output=True, text=True,
                timeout=30, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            _upload_reject(422, "malware scanner timed out", kind="structural-scan-failed")
        if completed.returncode != 0:
            _upload_reject(422, "local malware scanner rejected the upload", kind="malware-rejected")
        malware_status = "passed"
    return {"qpdf": qpdf_status, "malware_scanner": malware_status}


def _session_or_404(session_id: str) -> Session:
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not session.directory.is_dir():
        # The OS temp cleaner can remove a live session behind the process's
        # back; a zombie in-memory session must fail explicitly, not 500.
        SESSIONS.pop(session_id, None)
        _audit_event({
            "kind": "session-storage-vanished",
            "status": 404,
            "detail": "session directory disappeared while session was live",
            "session_id": session_id,
        })
        raise HTTPException(status_code=404, detail="session storage expired")
    return session


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_sha256(manifest: ReviewManifest) -> str:
    payload = json.dumps(manifest.as_dict(), ensure_ascii=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _values_sha256(values: dict[str, Any]) -> str:
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _render_pages(source: Path, directory: Path) -> list[str]:
    page_urls: list[str] = []
    document = fitz.open(str(source))
    try:
        for page_number, page in enumerate(document, 1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            output = directory / f"page-{page_number}.png"
            pixmap.save(str(output))
            page_urls.append(f"/api/sessions/{{session_id}}/pages/{page_number}.png")
    finally:
        document.close()
    return page_urls


def _payload(session: Session) -> dict[str, Any]:
    report = session.report.as_dict()
    page_urls = [url.replace("{session_id}", session.id)
                 for url in _render_page_url_list(session.source)]
    return {
        "session_id": session.id,
        "filename": session.display_filename,
        "pages": [{"number": index + 1, "image_url": url}
                  for index, url in enumerate(page_urls)],
        "targets": session.manifest.targets,
        "manifest": session.manifest.as_dict(),
        "vector_candidates": report["vector_candidates"],
        "input": report["input"],
        "backend_status": report["backend_status"],
        "warnings": report["warnings"],
        "signature_observations": report["signature_observations"],
        "audit_log": report["audit_log"],
        "security": session.security,
    }


def _render_page_url_list(source: Path) -> list[str]:
    document = fitz.open(str(source))
    try:
        count = len(document)
    finally:
        document.close()
    return [f"/api/sessions/{{session_id}}/pages/{number}.png" for number in range(1, count + 1)]


# Startup sweep: sessions left by a previous process still expire on their
# TTL instead of surviving as unbounded temp residue.
_cleanup_expired_sessions()


@app.get("/", response_class=FileResponse)
def index() -> FileResponse:
    return FileResponse(BROWSER_ROOT / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    _cleanup_expired_sessions()
    return {"status": "ok", "service": "pdf-field-lab"}


@app.post("/api/sessions")
async def create_session(file: UploadFile = File(...)) -> dict[str, Any]:
    _cleanup_expired_sessions()
    filename = Path(file.filename or "upload.pdf").name
    if not filename.lower().endswith(".pdf"):
        _upload_reject(415, "upload a PDF file", filename=filename)
    data = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > MAX_UPLOAD_BYTES:
            _upload_reject(413, f"PDF exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit", filename=filename)
    if not data.startswith(b"%PDF"):
        _upload_reject(415, "file does not look like a PDF", filename=filename)
    session_id = uuid.uuid4().hex
    directory = SESSION_ROOT / session_id
    directory.mkdir(parents=True, exist_ok=False)
    # Keep the user-facing filename as metadata. A reserved source path avoids
    # collisions when someone uploads a file named editable.pdf or filled.pdf.
    source = directory / "source.pdf"
    source.write_bytes(bytes(data))
    try:
        security = _structural_scan(source)
        encrypted = False
        with fitz.open(str(source)) as document:
            encrypted = bool(document.needs_pass)
            if len(document) == 0:
                _upload_reject(422, "PDF has no pages", filename=filename)
            if len(document) > MAX_PAGES:
                _upload_reject(413, f"PDF exceeds the {MAX_PAGES}-page limit", filename=filename)
        if encrypted:
            _upload_reject(422, "PDF is password-protected; encrypted uploads are not accepted",
                           kind="upload-encrypted", filename=filename)
        active_content = _active_content_report(source)
        if active_content:
            _upload_reject(
                422,
                f"PDF quarantined: active content present ({', '.join(sorted(active_content))})",
                kind="upload-quarantined",
                filename=filename,
            )
        security["active_content"] = "none"
        report = analyze(source, run_cv=True, run_ocr=False)
        (directory / "analysis.json").write_text(
            json.dumps(report.as_dict(), indent=2) + "\n", encoding="utf-8")
        editable = directory / "editable.pdf"
        export_editable(source, editable, report.logical_fields)
        _render_pages(source, directory)
    except Exception as exc:
        shutil.rmtree(directory, ignore_errors=True)
        if isinstance(exc, HTTPException):
            raise
        detail = f"could not analyze PDF: {exc}"
        _audit_event({"kind": "analysis-failed", "status": 422, "detail": detail[:300], "filename": filename})
        raise HTTPException(status_code=422, detail=detail) from exc
    manifest = create_manifest(report.logical_fields)
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(json.dumps(manifest.as_dict(), indent=2) + "\n", encoding="utf-8")
    session = Session(
        id=session_id,
        display_filename=filename,
        directory=directory,
        source=source,
        editable=editable,
        report=report,
        manifest=manifest,
        lock=threading.RLock(),
        created_at=time.time(),
        security=security,
    )
    SESSIONS[session_id] = session
    return _payload(session)


@app.get("/api/sessions/{session_id}/manifest")
def get_manifest(session_id: str) -> dict[str, Any]:
    session = _session_or_404(session_id)
    with session.lock:
        return session.manifest.as_dict()


@app.put("/api/sessions/{session_id}/manifest")
async def update_manifest(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    session = _session_or_404(session_id)
    reviewer = payload.get("reviewer")
    if reviewer is None:
        reviewer = _reviewer_identity()
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise HTTPException(status_code=422, detail="reviewer must be a non-empty string")
    reviewer = reviewer.strip()
    with session.lock:
        expected_revision = session.manifest.revision
        try:
            incoming_revision = int(payload.get("revision"))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="manifest revision must be an integer") from exc
        if incoming_revision != expected_revision:
            raise HTTPException(status_code=409, detail={
                "message": "manifest changed; reload the latest review state",
                "manifest": session.manifest.as_dict(),
            })
        try:
            incoming = validate_manifest(payload, session.report.input.page_sizes,
                                         max_targets=MAX_TARGETS)
        except (ManifestValidationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        incoming.revision = expected_revision + 1
        previous_manifest = session.manifest.as_dict()
        previous_manifest_sha256 = _manifest_sha256(session.manifest)
        manifest_sha256 = _manifest_sha256(incoming)
        recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        source_sha256 = _sha256(session.source)
        candidates = review_diff.review_candidates(
            previous_manifest, incoming.as_dict(),
            source_sha256=source_sha256, session_id=session_id,
            reviewer=reviewer, recorded_at=recorded_at, manifest_sha256=manifest_sha256)
        if candidates:
            candidates_block = review_diff.candidates_to_jsonl(candidates)
            candidates_path = session.directory / "review-candidates.jsonl"
            with candidates_path.open("a", encoding="utf-8") as handle:
                handle.write(candidates_block)
            signals: dict[str, int] = {}
            for item in candidates:
                signal = item.get("signal")
                if signal:
                    signals[signal] = signals.get(signal, 0) + 1
            # Hash-bound review receipt (FFL-HQ-006): binds reviewer, time,
            # both revision states, and the exact candidate block. This is an
            # integrity chain, not a cryptographic signature.
            receipt: dict[str, Any] = {
                "session_id": session_id,
                "reviewer": reviewer,
                "recorded_at": recorded_at,
                "revision": incoming.revision,
                "previous_revision": expected_revision,
                "manifest_sha256": manifest_sha256,
                "previous_manifest_sha256": previous_manifest_sha256,
                "source_sha256": source_sha256,
                "event_count": len(candidates),
                "signals": signals,
                "candidates_sha256": hashlib.sha256(candidates_block.encode("utf-8")).hexdigest(),
            }
            receipt["receipt_sha256"] = _canonical_sha256(receipt)
            with (session.directory / "review-receipts.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")
            (session.directory / "latest-review-receipt.json").write_text(
                json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        session.manifest = incoming
        temp_path = session.directory / "manifest.json.tmp"
        temp_path.write_text(json.dumps(incoming.as_dict(), indent=2) + "\n", encoding="utf-8")
        temp_path.replace(session.directory / "manifest.json")
        return incoming.as_dict()


@app.get("/api/sessions/{session_id}/review-receipts.jsonl")
def review_receipts(session_id: str) -> FileResponse:
    """Governed review-session receipts binding reviewer, time, and revision.

    A receipt is the hash-bound provenance a promoted label record cites as
    its review_receipt; it proves who reviewed what, when, against which
    manifest state. It is not accepted-label authority by itself.
    """

    session = _session_or_404(session_id)
    receipts_path = session.directory / "review-receipts.jsonl"
    if not receipts_path.is_file():
        raise HTTPException(status_code=404, detail="no review receipts recorded for this session")
    return FileResponse(receipts_path, media_type="application/x-ndjson",
                        filename=f"review-receipts-{session_id}.jsonl")


@app.get("/api/sessions/{session_id}/review-candidates.jsonl")
def review_candidates(session_id: str) -> FileResponse:
    """Governed export of review events as label-repository candidate JSONL.

    Candidates are review evidence for the canonical label builder; they are
    never accepted labels by themselves.
    """

    session = _session_or_404(session_id)
    candidates_path = session.directory / "review-candidates.jsonl"
    if not candidates_path.is_file():
        raise HTTPException(status_code=404, detail="no review candidates recorded for this session")
    return FileResponse(candidates_path, media_type="application/x-ndjson",
                        filename=f"review-candidates-{session_id}.jsonl")


@app.get("/api/sessions/{session_id}/pages/{page_number}.png")
def page_image(session_id: str, page_number: int) -> FileResponse:
    session = _session_or_404(session_id)
    if page_number < 1 or page_number > session.report.input.pages:
        raise HTTPException(status_code=404, detail="page not found")
    image = session.directory / f"page-{page_number}.png"
    if not image.is_file():
        raise HTTPException(status_code=404, detail="page not found")
    return FileResponse(image, media_type="image/png")


@app.post("/api/sessions/{session_id}/export")
async def export_session(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    session = _session_or_404(session_id)
    with session.lock:
        manifest = session.manifest
        if manifest.pending_count:
            raise HTTPException(status_code=409, detail=f"review {manifest.pending_count} target(s) before export")
        values = payload.get("values", {})
        if not isinstance(values, dict):
            raise HTTPException(status_code=422, detail="values must be an object keyed by target ID")
        active_fields = manifest.field_specs()
        manifest_revision = manifest.revision
        manifest_sha256 = _manifest_sha256(manifest)
        values_sha256 = _values_sha256(values)
        # Rebuild from the immutable source for every accepted manifest
        # revision. The upload-time scaffold is only a derived cache and is not
        # allowed to hide moved, rejected, added, or retyped targets.
        try:
            export_editable(session.source, session.editable, active_fields)
            output = session.directory / (
                f"filled-r{manifest_revision}-{manifest_sha256[:16]}-{values_sha256[:16]}.pdf"
            )
            result = fill_editable(session.editable, output, active_fields, values)
        except (KeyError, FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        source_sha256 = _sha256(session.source)
        output_sha256 = _sha256(output)
        result.update({
            "source_sha256": source_sha256,
            "manifest_revision": manifest_revision,
            "manifest_sha256": manifest_sha256,
            "values_sha256": values_sha256,
            "output_sha256": output_sha256,
            "output_filename": output.name,
        })
        receipt = {
            "session_id": session_id,
            "source_sha256": source_sha256,
            "manifest_revision": manifest_revision,
            "manifest_sha256": manifest_sha256,
            "values_sha256": values_sha256,
            "output_sha256": output_sha256,
            "fill": result,
            "output_filename": output.name,
            "download_url": (
                f"/api/sessions/{session_id}/download?revision={manifest_revision}"
                f"&manifest_sha256={manifest_sha256}&values_sha256={values_sha256}"
            ),
        }
        receipt_path = session.directory / (
            f"export-receipt-r{manifest_revision}-{manifest_sha256[:16]}-{values_sha256[:16]}.json"
        )
        receipt_path.write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        (session.directory / "latest-export-receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


@app.get("/api/sessions/{session_id}/download")
def download(session_id: str, revision: int | None = None,
             manifest_sha256: str | None = None,
             values_sha256: str | None = None) -> FileResponse:
    session = _session_or_404(session_id)
    with session.lock:
        receipt_path = session.directory / "latest-export-receipt.json"
        if revision is not None or manifest_sha256 is not None or values_sha256 is not None:
            if revision is None or manifest_sha256 is None or values_sha256 is None:
                raise HTTPException(status_code=400, detail="revision, manifest_sha256, and values_sha256 are required together")
            receipt_path = session.directory / (
                f"export-receipt-r{revision}-{manifest_sha256[:16]}-{values_sha256[:16]}.json"
            )
        if not receipt_path.is_file():
            raise HTTPException(status_code=404, detail="export revision not found")
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail="export receipt is invalid") from exc
        if revision is not None and (
            receipt.get("manifest_revision") != revision
            or receipt.get("manifest_sha256") != manifest_sha256
            or receipt.get("values_sha256") != values_sha256
        ):
            raise HTTPException(status_code=409, detail="export identity does not match its receipt")
        if receipt.get("source_sha256") != _sha256(session.source):
            raise HTTPException(status_code=409, detail="source changed since export")
        output_name = receipt.get("output_filename")
        if not isinstance(output_name, str) or Path(output_name).name != output_name:
            raise HTTPException(status_code=500, detail="export receipt has an unsafe output path")
        output = session.directory / output_name
        if not output.is_file():
            raise HTTPException(status_code=404, detail="export output not found")
        if receipt.get("output_sha256") != _sha256(output):
            raise HTTPException(status_code=409, detail="export output hash does not match its receipt")
        return FileResponse(output, media_type="application/pdf", filename="editable-form.pdf")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("pdf_field_lab.server:app", host="127.0.0.1", port=8787, reload=False)
