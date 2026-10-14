"""Small, dependency-free configuration validation helpers."""

from __future__ import annotations

import os


def positive_int_env(name: str, default: int) -> int:
    """Read a positive integer setting or fail clearly during startup."""
    if default <= 0:
        raise ValueError(f"default for {name} must be a positive integer")

    raw_value = os.environ.get(name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError:
        raise ValueError(f"{name} must be a positive integer") from None
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value
