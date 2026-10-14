# Architecture and decision record

Date: 2026-09-09

## Objective

Make flat PDF forms inspectable and reconstructable as editable documents while
preserving the source and clearly separating observed geometry from inferred
semantics.

## Chosen architecture

`inspect_pdf` owns source metadata and native-field truth. `static_detect` owns
raw geometry candidates. `semantic_detect` first normalizes words into visual
text lines, then joins one compact form-like line to a nearby rectangle,
checkbox, underline, or labeled whitespace region. `profiles` owns reviewed
template semantics.
`analysis` composes native, generic, raster, OCR, and reviewed-profile lanes.
`export_pdf` owns the one-way boundary from top-origin target coordinates to
PDF widget coordinates. `fill_pdf` owns values and visual asset placement.
`server` exposes the same target contract to the browser, while `browser/` is
only a client and never becomes a second semantic source of truth.

`analysis` composes these lanes per page for unknown PDFs. A mixed document can
therefore retain native widgets on one page, vector proposals on another, and
raster/OCR proposals on a text-poor page. Native geometry suppresses only an
overlapping inferred proposal; it does not suppress unrelated painted fields
elsewhere on the same page.

`training_data` builds weakly supervised records without copying user PDFs.
The canonical `data/labels` repository governs future field-level supervision.
Its derived `trainable.jsonl` view is the only permitted model input: default
training admits verified development or validation records, while proxy labels
require an explicit development-only flag.
`target_model` trains and loads an optional lightweight reranker. Its output is
added as `model` evidence to generic targets, but it cannot override the
deterministic kind, geometry, or review requirement. `modal_train.py` is an
external-compute adapter for metadata-only experiments and is not part of the
default local runtime.

The reusable rationale for this staged architecture, including the CV, OCR,
NLP, geometry, signature, dataset, review, export, and training lessons, is
maintained in [docs/learning-ledger.md](learning-ledger.md). New detector or
model changes should append evidence and falsifiers there rather than creating
an unlinked retrospective.

The central product object is a `FieldSpec` target with a derived browser
component. Its `kind` describes meaning, its `bbox` describes the document
region, its evidence and confidence explain why it exists, and its
`editable_strategy` describes export behavior. This permits a photo or
signature region to be interactive without pretending the original PDF had an
AcroForm field there.

This keeps a candidate detector from silently becoming an editor and makes it
possible to replace a profile with OCR/CV/ML evidence later.

The browser presents the same contract through a type-first field map. Users
can filter targets by Text, Date, Choice, Photo, Signature, Group, or Review,
then reach the same target either from the index or its page overlay. Type is
not inferred from color alone: each target has a plain-language label, icon,
accessible name, interaction description, and review status. Choice is one
visible family with `single-select` and `multi-select` behavior subtypes.
Composite targets use deterministic semantic group labels such as Address
group or Constituency group, while zero active targets are represented as an
abstention state with a manual-add recovery path rather than 100% reviewed.

Text, date, choice, and composite targets use a canvas-local draft editor. A
checkmark commits the draft into the session values and the human-reviewed
set. Composite targets expose their option bboxes as coordinated sub-inputs,
while `input_mode="character-grid"` keeps a single string in the contract and
defers per-cell rendering to the PDF fill adapter.

## Multilingual fill contract

Multilingual filling is part of the product boundary even though the first
release does not promise every script or translation workflow. The system keeps
four concerns separate:

- `interface_language`: the language used by Fieldroom controls and guidance.
- `document_language` and `document_script`: the language and writing system
  observed in labels and instructions in the source PDF.
- `input_language` and `input_script`: the language and writing system the user
  chooses for a particular answer. A field may contain mixed scripts, such as a
  name in Devanagari with a Latin passport spelling and Arabic numerals.
- `output_font`: the embedded font and glyph coverage used by the exported PDF.

The current and future behavior follows these rules:

- Preserve source labels and the exact user-entered Unicode answer by default.
- Never silently translate, transliterate, normalize a name, or change a
  script. Any future `translate` or `transliterate` action must be explicit,
  previewable, reversible, and recorded in the audit log.
- Treat dates, numbers, identifiers, and character grids as formatting and
  validation concerns, not as translation concerns.
- Permit mixed-script answers when the field semantics allow them. A language
  choice is metadata for routing and validation, not a restriction that erases
  valid user input.
- Before export, check the selected font for glyph coverage, embedding, field
  size, and viewer compatibility. An unsupported script is an honest export
  error or review warning, never a successful PDF with invisible characters.

The planned per-field metadata is intentionally additive and is not yet an
active API requirement:

```json
{
  "input_language": "hi",
  "input_script": "Devanagari",
  "transform": "none",
  "output_font": "Noto Sans Devanagari",
  "output_font_status": "needs-embedded-font"
}
```

Detection and NLP should use document language and script as evidence for OCR
routing, label lexicons, NER, and field association, while preserving the same
abstention and human-review rules as the Latin-script lane. Training and
evaluation must report results by language, script, document family, and field
type rather than hiding weak-script performance in one aggregate score.

## macOS porting boundary

This Python/browser project is the reference implementation and experiment
surface. It must not be ported into the sibling `pdf_editor` macOS project
until the behavior is close to production quality on unseen documents. The
sibling project remains outside this project's ownership boundary during this
phase.

The port gate requires all of the following:

- A locked, document-disjoint benchmark with independent real-world families,
  typed fields, usable writing extents, grouping, abstention, and hard
  negatives, with no unresolved critical recall or precision defect.
- Review-manifest edits proven end to end: move, resize, reject, add, retype,
  accept, fill, export, reopen, and visually compare against the accepted
  revision.
- Native PDF field-tree preservation proven for text, multiline, dropdown,
  checkbox, radio, repeated-widget, and digital-signature cases.
- Visual asset behavior proven for photo and signature placement, including
  empty-versus-present audit observations and print-scale rendering.
- Script-aware output gates proven for every language and font family claimed
  by the product, including exact-value preservation and unsupported-script
  handling.
- Browser, independent-parser, Preview, and Acrobat checks with no open
  source-integrity or export-fidelity blocker.
- Security, upload limits, session isolation, cleanup, and sensitive logging
  decisions closed for the target macOS product boundary.

The future port should share the stable ontology, manifest schema, benchmark
fixtures, golden receipts, and falsification tests. The PDF implementation
itself should be a native macOS adapter behind those contracts, not a copied
second semantic source of truth. Porting becomes a new task only after this
gate is reviewed and explicitly authorized.

## Alternatives considered

- A single OCR-first pipeline was rejected because this specimen has a reliable
  text layer and vector grids, and OCR would lose exact PDF coordinates.
- A VLM-only detector was rejected because coordinate hallucination and source
  provenance would be difficult to audit. A later optional model may name or
  classify candidates, but it must snap to observed geometry.
- Editing the original PDF in place was rejected because it risks irreversible
  source drift and complicates output validation.

## Invariants

- Original input bytes are never written by analysis or export.
- Native form fields outrank inferred candidates.
- Every inferred field carries source, score, label, bbox, and review state.
- Image and signature regions are not represented as text fields semantically.
- Composite field groups remain visible until subfield semantics are explicit.
- Generic promotion requires both a field-like language cue and a spatially
  associated geometry or an explicit colon-label whitespace fallback.
- A coherent prose line, isolated geometry, table rule, or page-position guess
  must abstain from becoming a semantic target.
- Export must reopen and expose an AcroForm field inventory.
- Browser sessions keep uploaded source and derived files under a temporary
  process-local directory. No upload is claimed to survive a server restart.
- Learned output is advisory until a document-disjoint, field-level gold set
  demonstrates target-type and geometry quality.

## Known limits and revisit triggers

The local browser loop and visual asset adapter now exist. The detector has a
controlled, authored three-family gold set spanning flat vector, native-widget,
and image-only representations. It recovers all 15 authored positive targets in
both vector and image-only semantic lanes, with zero authored divider false
positives. This is controlled-fixture evidence, not a claim about arbitrary
documents.

The next detection gate is a reviewed, document-disjoint real-world gold set.
Raster/OCR targets remain review-required proposals. Do not call this legal or
production-ready until output fidelity, session lifecycle, security,
image/signature handling, and external viewer compatibility are independently
verified.

The mixed-representation composition path is now covered by a focused test,
but this is pipeline evidence rather than recall evidence. It does not prove
that each page was correctly recognized as native, vector, raster, or OCR.
