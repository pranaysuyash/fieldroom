"""Runtime capability discovery for honest per-run receipts."""

from __future__ import annotations

import importlib.util
import shutil


def capability_status() -> dict[str, str]:
    """Report availability, without implying that a backend ran."""
    return {
        "structural_pdf": "active",
        "text_coordinates": "active",
        "vector_geometry": "active",
        "opencv": "installed" if importlib.util.find_spec("cv2") else "not-installed",
        "numpy": "installed" if importlib.util.find_spec("numpy") else "not-installed",
        "pytesseract": "installed" if importlib.util.find_spec("pytesseract") else "not-installed",
        "tesseract_binary": "installed" if shutil.which("tesseract") else "not-installed",
        "spacy": "installed" if importlib.util.find_spec("spacy") else "not-installed",
        "ocr_execution": "not-requested",
        "cv_execution": "not-requested",
        "nlp_execution": "rule-based-profile",
    }
