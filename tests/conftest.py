"""Shared helpers for the server test-suite.

fill_required_values mirrors the server's required/conditional semantics
(src/pdf_field_lab/server.py::_required_condition_active and _value_filled)
so tests can produce a complete values payload the way a reviewer would.
"""

from __future__ import annotations

from typing import Any


def _value_filled(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_value_filled(item) for item in value.values())
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def _condition_active(target: dict[str, Any], values: dict[str, Any],
                      by_id: dict[str, dict[str, Any]]) -> bool:
    condition = target.get("conditional_on")
    if not isinstance(condition, str) or "=" not in condition:
        return True
    ref_id, _, expected = condition.partition("=")
    ref_value = values.get(ref_id.strip())
    if expected.strip() == "!":
        return not _value_filled(ref_value)
    if not _value_filled(ref_value):
        return False
    expected = expected.strip()
    if not expected or expected == "*":
        return True
    if isinstance(ref_value, dict):
        return expected in ref_value
    return str(ref_value) == expected


def _dummy_value(target: dict[str, Any]) -> Any:
    kind = target["kind"]
    if kind in {"image", "signature"}:
        return "data:image/png;base64,iVBORw0KGgo="
    if kind == "date":
        return "2000-01-01"
    if kind == "choice":
        options = target.get("options") or []
        return options[0]["value"] if options else "selected"
    if kind == "composite":
        options = target.get("options") or []
        if options:
            return {option["value"]: "T" for option in options}
        return "Test"
    return "Test value"


def fill_required_values(manifest: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return values covering every active required target whose condition
    holds, with `overrides` applied last."""
    values: dict[str, Any] = dict(overrides or {})
    active = [t for t in manifest.get("targets", []) if t.get("status") != "rejected"]
    by_id = {t["id"]: t for t in active}
    for target in active:
        if not target.get("required") or target["id"] in values:
            continue
        if not _condition_active(target, values, by_id):
            continue
        if not _value_filled(values.get(target["id"])):
            values[target["id"]] = _dummy_value(target)
    return values
