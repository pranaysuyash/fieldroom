"""Canonical data contracts for the extraction pipeline.

Coordinates use PDF points with a top-left origin for human-facing reports.
The exporter converts them to the PDF's bottom-left coordinate system at its
single boundary, which keeps detection and semantic profiles easy to audit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


FieldKind = Literal["text", "textarea", "date", "choice", "image", "signature", "composite"]
SourceKind = Literal["native", "vector", "raster_cv", "ocr", "template_profile", "model", "manual"]
SignatureStatus = Literal["present", "missing", "uncertain"]


@dataclass(frozen=True)
class BBox:
    x: float
    y: float
    width: float
    height: float

    def to_pdf_rect(self, page_height: float) -> list[float]:
        """Return [x0, y0, x1, y1] using PDF bottom-left coordinates."""
        return [self.x, page_height - self.y - self.height,
                self.x + self.width, page_height - self.y]

    def as_dict(self) -> dict[str, float]:
        return {k: round(v, 3) for k, v in asdict(self).items()}


@dataclass
class Evidence:
    source: SourceKind
    score: float
    detail: str
    observed: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FieldSpec:
    id: str
    page: int
    label: str
    kind: FieldKind
    bbox: BBox
    editable_strategy: str
    review_required: bool = True
    required: bool = False
    conditional_on: str | None = None
    options: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)
    input_mode: str = "single"
    max_length: int | None = None
    label_entities: list[dict[str, Any]] = field(default_factory=list)
    grid_rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def component(self) -> str:
        """Return the browser component that should edit this target.

        This is intentionally derived from the semantic kind. The UI contract
        is richer than an AcroForm widget: image and signature targets are
        interactive app components even when their PDF export is an overlay.
        """
        return {
            "text": "text-field",
            "textarea": "text-area",
            "date": "date-field",
            "choice": "choice-group",
            "image": "photo-dropzone",
            "signature": "signature-pad",
            "composite": "composite-field",
        }[self.kind]

    @property
    def selection_mode(self) -> str | None:
        """Return the user-facing choice behavior when this is a choice."""
        if self.kind != "choice":
            return None
        return "radio" if self.editable_strategy == "acroform-radio" else "checkbox"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "page": self.page,
            "label": self.label,
            "kind": self.kind,
            "component": self.component,
            "selection_mode": self.selection_mode,
            "bbox": self.bbox.as_dict(),
            "editable_strategy": self.editable_strategy,
            "review_required": self.review_required,
            "required": self.required,
            "conditional_on": self.conditional_on,
            "options": self.options,
            "evidence": [item.as_dict() for item in self.evidence],
            "confidence": round(self.confidence, 3),
            "notes": self.notes,
            "input_mode": self.input_mode,
            "max_length": self.max_length,
            "label_entities": self.label_entities,
            "grid_rows": self.grid_rows,
        }


@dataclass
class SignatureObservation:
    """Review-only evidence about an expected signer slot on the source page.

    This is deliberately not a FieldSpec. Existing ink is document evidence,
    while an editable signature target is an action the user may choose later.
    Keeping the contracts separate prevents audit observations from becoming
    replacement widgets during export.
    """

    id: str
    page: int
    signer: str
    role: str
    bbox: BBox
    status: SignatureStatus
    confidence: float
    evidence: list[Evidence] = field(default_factory=list)
    review_required: bool = True
    source_refs: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.signer} · {self.role}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "page": self.page,
            "label": self.label,
            "signer": self.signer,
            "role": self.role,
            "bbox": self.bbox.as_dict(),
            "status": self.status,
            "confidence": round(self.confidence, 3),
            "evidence": [item.as_dict() for item in self.evidence],
            "review_required": self.review_required,
            "source_refs": self.source_refs,
        }


@dataclass
class PdfInspection:
    path: str
    sha256: str
    pages: int
    page_sizes: list[dict[str, float]]
    metadata: dict[str, Any]
    native_fields: list[dict[str, Any]]
    annotations: list[dict[str, Any]]
    text_chars_by_page: list[int]
    raster_backend: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisReport:
    schema: str
    input: PdfInspection
    logical_fields: list[FieldSpec]
    vector_candidates: list[FieldSpec]
    backend_status: dict[str, str]
    warnings: list[str] = field(default_factory=list)
    signature_observations: list[SignatureObservation] = field(default_factory=list)
    audit_log: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "input": self.input.as_dict(),
            "logical_fields": [item.as_dict() for item in self.logical_fields],
            "vector_candidates": [item.as_dict() for item in self.vector_candidates],
            "backend_status": self.backend_status,
            "warnings": self.warnings,
            "signature_observations": [item.as_dict() for item in self.signature_observations],
            "audit_log": self.audit_log,
        }
