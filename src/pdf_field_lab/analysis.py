"""Pipeline orchestration and capability reporting."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from .capabilities import capability_status
from .inspect_pdf import inspect_pdf
from .models import AnalysisReport
from .native_detect import detect_native_targets
from .profiles.form6 import form6_fields, matches_form6
from .semantic_detect import detect_semantic_targets
from .static_detect import detect_vector_candidates
from .signature_detect import detect_signature_observations


def _overlap_ratio(first, second) -> float:
    """Return intersection over the smaller target area."""
    if first.page != second.page:
        return 0.0
    x0 = max(first.bbox.x, second.bbox.x)
    y0 = max(first.bbox.y, second.bbox.y)
    x1 = min(first.bbox.x + first.bbox.width, second.bbox.x + second.bbox.width)
    y1 = min(first.bbox.y + first.bbox.height, second.bbox.y + second.bbox.height)
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    smaller_area = min(
        first.bbox.width * first.bbox.height,
        second.bbox.width * second.bbox.height,
    )
    return intersection / smaller_area if smaller_area else 0.0


def _merge_page_lanes(native, generic, raster):
    """Compose page-local evidence without letting one PDF lane hide another.

    Native widgets are authoritative when an inferred target overlaps them.
    Generic vector proposals outrank raster proposals for the same region.
    Non-overlapping candidates from every page-local lane remain available for
    review because a single PDF can mix representations across pages.
    """
    merged = []
    for candidate in [*native, *generic, *raster]:
        if any(_overlap_ratio(candidate, existing) >= 0.65 for existing in merged):
            continue
        merged.append(candidate)
    return sorted(merged, key=lambda item: (item.page, item.bbox.y, item.bbox.x, item.id))


@lru_cache(maxsize=2)
def _load_advisory_model(model_path: str):
    from .target_model import load_target_model
    return load_target_model(Path(model_path))


def analyze(path: Path, *, run_cv: bool = False, run_ocr: bool = False,
            run_raster: bool = True) -> AnalysisReport:
    inspection = inspect_pdf(path)
    vector = detect_vector_candidates(path)
    model_path = Path(os.environ.get(
        "PDF_FIELD_LAB_MODEL",
        str(Path(__file__).resolve().parents[2] / "artifacts" / "model" / "target-classifier.joblib")))
    # RANK-007 park decision (2026-10-14): the advisory model is parked — its
    # holdout is near-noise and flywheel supply is insufficient. It stays
    # opt-in via PDF_FIELD_LAB_ADVISORY_MODEL=on so the mechanism and its
    # receipts remain exercisable, but no run loads it by default.
    advisory_requested = os.environ.get("PDF_FIELD_LAB_ADVISORY_MODEL", "off").strip().lower() \
        not in {"off", "0", "false", "no"}
    model = None
    if advisory_requested and model_path.is_file():
        model = _load_advisory_model(str(model_path))
    generic = detect_semantic_targets(path, model=model)
    native = detect_native_targets(inspection)
    raster = []
    raster_attempted = False
    signature_observations = []
    warnings = []
    profile_matched = matches_form6(path)
    if profile_matched:
        logical = form6_fields()
    else:
        if run_raster and any(chars < 100 for chars in inspection.text_chars_by_page):
            try:
                from .raster_cv import detect_raster_targets
                raster_attempted = True
                raster = detect_raster_targets(path)
            except (ImportError, OSError, RuntimeError) as exc:
                warnings.append(f"Raster semantic detection unavailable: {type(exc).__name__}")
        logical = _merge_page_lanes(native, generic, raster)
        warnings.append("No reviewed semantic profile matched this PDF fingerprint; generic targets require review.")
        if native and (generic or raster):
            warnings.append("Detection lanes were merged per page; native widgets take precedence only for overlapping regions.")
    if not inspection.native_fields:
        warnings.append("No native AcroForm fields found; logical fields are reconstructed candidates.")
    if any(chars < 100 for chars in inspection.text_chars_by_page):
        warnings.append("At least one page is text-poor; OCR/CV should be enabled for scanned inputs.")
    try:
        signature_observations = detect_signature_observations(path)
    except (ImportError, OSError, RuntimeError) as exc:
        warnings.append(f"Signature observation lane unavailable: {type(exc).__name__}")
    backend_status = capability_status()
    backend_status.update({
        "template_profile": "matched" if profile_matched else "not-matched",
        "generic_semantic_detection": "executed",
        "native_target_detection": "executed" if native else "none-found",
        "target_model": ("loaded-advisory" if model is not None else "not-loaded")
        if advisory_requested else "disabled-by-operator",
        "raster_semantic_detection": "executed" if raster_attempted else "not-needed-or-no-candidates",
        "raster_target_count": str(len(raster)),
        "ocr_selection": "page-routed-by-text-density",
        "cv_execution": "not-requested",
        "ocr_execution": "not-requested",
        "signature_observation_detection": "executed" if signature_observations else "no-multi-signer-block-found",
        "signature_observation_count": str(len(signature_observations)),
    })
    if run_cv:
        from .raster_cv import run_cv_probe
        backend_status["cv_execution"] = "executed"
        backend_status["cv_probe"] = str(run_cv_probe(path))
    if run_ocr:
        from .raster_cv import run_ocr_probe
        backend_status["ocr_execution"] = "executed"
        backend_status["ocr_probe"] = str(run_ocr_probe(path))
    audit_log = [{
        "event": "signature_slot_inspected",
        "observation_id": item.id,
        "page": item.page,
        "signer": item.signer,
        "role": item.role,
        "status": item.status,
        "confidence": round(item.confidence, 3),
        "source_sha256": inspection.sha256,
        "detector": "signature-observation.v1",
    } for item in signature_observations]
    return AnalysisReport(
        schema="pdf-form-field-lab.analysis.v1",
        input=inspection,
        logical_fields=logical,
        vector_candidates=vector,
        backend_status=backend_status,
        warnings=warnings,
        signature_observations=signature_observations,
        audit_log=audit_log,
    )
