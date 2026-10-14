"""Derive governed label candidates from human review manifest changes.

Review actions (accept, reject, restore, manual add, geometry correction) are
the raw material for a real-document gold set. This module turns the delta
between two manifest revisions into candidate records. It is deliberately a
pure function of the two manifests: persistence stays with the session, and
label promotion stays with the canonical label repository builder. A candidate
is review evidence, never an accepted label.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

MANUAL_ID_PREFIX = "manual-"

_REVIEW_STATUSES = {"accepted", "rejected", "pending"}

# Disagreement semantics: each event classifies how the human verdict relates
# to what the detector proposed. added-detection and removed carry no
# disagreement because no human counter-decision is involved yet.
_EVENT_SIGNALS = {
    "accepted": "agreement",
    "rejected": "false-positive",
    "added-manual": "detector-miss",
    "moved": "geometry-correction",
    "restored": "review-correction",
    "added-detection": None,
    "removed": None,
}


def _snapshot(target: dict[str, Any]) -> dict[str, Any]:
    box = target.get("bbox") or {}
    return {
        "id": target.get("id"),
        "page": target.get("page"),
        "label": target.get("label"),
        "kind": target.get("kind"),
        "status": target.get("status"),
        "bbox": {key: box.get(key) for key in ("x", "y", "width", "height")},
    }


def _is_manual(target: dict[str, Any]) -> bool:
    target_id = str(target.get("id", ""))
    if target_id.startswith(MANUAL_ID_PREFIX):
        return True
    for item in target.get("evidence") or []:
        if isinstance(item, dict) and item.get("source") == "manual":
            return True
    return False


def review_candidates(
    previous_manifest: dict[str, Any],
    current_manifest: dict[str, Any],
    *,
    source_sha256: str,
    session_id: str,
    reviewer: str | None = None,
    recorded_at: str | None = None,
    manifest_sha256: str | None = None,
) -> list[dict[str, Any]]:
    """Return one candidate per review event between two manifest revisions.

    Events: accepted, rejected, restored, added-manual, added-detection,
    removed, moved. Deterministic order (current revision order, then event
    name) keeps the emitted JSONL stable for idempotent ingestion.

    reviewer, recorded_at, and manifest_sha256 are caller-supplied review
    governance context (FFL-HQ-006): they bind every event to the operator who
    made it, the moment of the batch, and the exact resulting manifest state.
    They stay optional so this function remains a pure function of its inputs.
    """

    previous = {str(item.get("id")): item for item in previous_manifest.get("targets", [])}
    candidates: list[dict[str, Any]] = []

    def emit(target: dict[str, Any], event: str, detail: dict[str, Any] | None = None) -> None:
        record: dict[str, Any] = {
            "candidate_id": f"r{current_manifest.get('revision', 0)}-{target.get('id')}-{event}",
            "event": event,
            "revision": current_manifest.get("revision"),
            "session_id": session_id,
            "source_sha256": source_sha256,
            "manual": _is_manual(target),
            "signal": _EVENT_SIGNALS.get(event),
            "target": _snapshot(target),
        }
        if reviewer is not None:
            record["reviewer"] = reviewer
        if recorded_at is not None:
            record["recorded_at"] = recorded_at
        if manifest_sha256 is not None:
            record["manifest_sha256"] = manifest_sha256
        if detail:
            record["detail"] = detail
        candidates.append(record)

    for target in current_manifest.get("targets", []):
        target_id = str(target.get("id"))
        before = previous.get(target_id)
        status = target.get("status")
        if before is None:
            emit(target, "added-manual" if _is_manual(target) else "added-detection")
            continue
        previous_status = before.get("status")
        if status != previous_status:
            if status == "accepted":
                emit(target, "accepted")
            elif status == "rejected":
                emit(target, "rejected")
            elif previous_status == "rejected" and status in _REVIEW_STATUSES:
                emit(target, "restored")
        if _box_changed(before, target):
            emit(target, "moved", detail={"previous_bbox": _snapshot(before)["bbox"]})

    for target_id, target in previous.items():
        if target_id not in {str(item.get("id")) for item in current_manifest.get("targets", [])}:
            emit(target, "removed")
    return candidates


def _box_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    first = _snapshot(before)["bbox"]
    second = _snapshot(after)["bbox"]
    return any(first.get(key) != second.get(key) for key in ("x", "y", "width", "height"))


def candidates_to_jsonl(candidates: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in candidates)


def candidate_record_stub(candidate: dict[str, Any]) -> dict[str, Any]:
    """Convert one review candidate into a pending label-repository record.

    The repository builder owns identity, family grouping, and merge rules;
    this only shapes the payload so the governed pipeline can ingest it.

    annotation.reviewer stays None deliberately: that field records the person
    who verified the *label*, which happens only at promotion. The session
    reviewer is trace evidence and lives in provenance.lineage and notes.
    """

    target = candidate.get("target", {})
    sha = str(candidate.get("source_sha256", ""))
    record_id = f"review-{sha[:12]}-{candidate.get('candidate_id', 'unknown')}"
    trace = (
        f"human review event '{candidate.get('event')}' at manifest revision "
        f"{candidate.get('revision')}"
    )
    if candidate.get("reviewer"):
        trace += f" by reviewer '{candidate.get('reviewer')}'"
    if candidate.get("manifest_sha256"):
        trace += f" (manifest_sha256 {candidate.get('manifest_sha256')})"
    if candidate.get("recorded_at"):
        trace += f" recorded {candidate.get('recorded_at')}"
    notes = [
        f"Review candidate ({candidate.get('event')}) for target "
        f"'{target.get('id')}' kind={target.get('kind')} page={target.get('page')}."
    ]
    if candidate.get("signal"):
        notes.append(f"Review signal: {candidate.get('signal')}.")
    return {
        "id": record_id,
        "family_id": f"review-session-{sha[:12]}",
        "source": {
            "locator_kind": "session-manifest",
            "locator": f"session/{candidate.get('session_id', 'unknown')}",
            "sha256": sha,
            "privacy_class": "user-sensitive",
        },
        "provenance": {
            "source_kind": "review-session",
            "producer": "fieldroom-review",
            "license": "not-applicable-user-supplied-local",
            "lineage": trace,
        },
        "annotation": {
            "status": "pending",
            "reviewer": None,
            "target_count": 1,
            "target_manifest": None,
            "notes": notes,
            "review_target": deepcopy(target),
        },
        "split": {"role": "not-for-training", "reason": "review-session candidate pending human confirmation"},
    }
