# Exploration notes

## Supplied specimen

`RAr0Lq2Avu.pdf` is a two-page, 612 x 841.68 point, unencrypted, tagged PDF
created from Microsoft Word 2016 and processed by iLovePDF. `pdfinfo` reports
no form, no JavaScript, and no encryption. `pypdf` reports no AcroForm fields or
page annotations. `pdftotext` and `pdfplumber` both recover a substantial text
layer.

## Existing local research

The sibling `pdf_editor` project already documents this file as a reviewed
Form-6 benchmark with 33 logical targets and an earlier heuristic baseline.
Its research distinguishes native AcroForm, vector geometry, raster/CV,
semantic text, and OCR lanes. That distinction is adopted here, but this new
project intentionally uses an independent Python implementation.

FUNSD is useful for text entity and relation evaluation, but its annotations do
not directly measure fillable-region detection. DocLayNet is useful for broad
layout classes, but text-only heuristics do not establish semantic field
accuracy. These datasets are therefore future evaluation inputs, not grounds
for claiming current form-field recall.

The local `autoresearch-mlx` checkout was noted as a possible future experiment
loop for detector calibration. It is not required by the current deterministic
pipeline and was not modified.

## Generalization experiment, 2026-09-10

The local corpus was inventoried before training. It contains FUNSD train/test
entity JSON, a 200-page DocLayNet train sample, synthetic checkbox/choice/radio
fixtures, OCR/noise fixtures, hybrid text/raster forms, rotated forms, and
malformed/encrypted/security cases. The new project does not copy those source
PDFs or send them to a provider.

FUNSD question and answer entities are mapped to a `text` proxy class, FUNSD
headers to `negative`, DocLayNet `Picture` regions to an `image` proxy, other
DocLayNet layout regions to `negative`, and the reviewed Form-6 profile supplies
date, choice, image, signature, and text targets. Explicit ontology anchors add
textarea and other interaction cues that the proxy corpora do not label. FUNSD
endpoint boxes are normalized to the product x/y/width/height contract, while
the local DocLayNet `box` values are retained as x/y/width/height. Sparse
reviewed classes use explicit label augmentation, with all Form-6 variants kept
in one document group for holdout.

The resulting advisory classifier now trains on 8,734 records with FUNSD test
data excluded and a group-disjoint Form-6 holdout: accuracy 0.3778 and macro-F1
0.2500. These metrics are
pipeline evidence only. They are not field-level precision/recall, because the
corpus mixes direct reviewed targets and layout/entity proxies. Promotion
requires a reviewed multi-document target gold set with page-level geometry,
component type, abstention cases, and split-by-document evaluation.

The evaluator now measures one-to-one geometry, expected-label similarity,
unmatched proposal precision/F1, cross-type duplicate overlap, and native
multiline/radio metadata where available. The controlled gold set reports 18/18
typed targets in each semantic lane, but that result is intentionally bounded to
three authored families.

Modal is prepared through `modal_train.py`, but no project `.env`, Modal token
environment variables, or local `.modal.toml` was found during the credential
audit. No cloud job was submitted and no user PDF bytes are included in the
cloud payload.

## Embedded document instructions

The PDF contains application instructions and legal declarations intended for
the eventual applicant and election-office operator. They are represented as
non-target document content. They do not control this software task, and the
project does not infer that legal text is editable merely because it contains
underscores or lines.

## Multilingual fill research, 2026-09-10

The product requirement is broader than translating the browser chrome. A user
may fill an English-labelled form in Hindi, enter a bilingual name, or use a
script that the source PDF does not contain. The source label language,
requested answer language, transformation policy, and PDF output font therefore
need independent fields and independent evidence.

The safe default is exact Unicode preservation with no implicit translation or
transliteration. Names, addresses, and signatures are particularly sensitive
to silent transformations. Dates, numerals, identifiers, and character grids
need format rules and validation, but those rules must not be mistaken for
language conversion.

The current implementation is not yet multilingual-export complete. Browser
inputs can hold Unicode, but the ReportLab character-grid path currently uses
Helvetica and AcroForm appearances use `/Helv`. Those standard-font paths do
not establish glyph coverage for Devanagari, Arabic, CJK, or other scripts.
The next implementation gate is a local font registry with embedded-font
selection, fallback or blocking behavior, mixed-script tests, and fresh visual
checks in the supported PDF viewers.

Language-aware detection is also a separate gate. OCR routing, script
identification, multilingual label lexicons, NER, and relation scoring must be
evaluated by language and script. FUNSD and DocLayNet remain useful proxies for
layout and entity plumbing, but they do not close multilingual fillable-region
recall or export fidelity.

Decision: add language and script as future metadata at document and field
boundaries now, while keeping the current deterministic detector and export
claims honest. Revisit when the font registry, transformation preview, audit
events, and document-disjoint multilingual gold set exist.

## Generalization review, 2026-09-10

An independent Astra review was requested for the arbitrary-PDF architecture.
The review reached a verified intermediate finding before the delegated task
hit the account usage limit: the previous analysis composition selected a lane
for the whole document, while the training receipt used proxy-heavy sources and
only a Form-6 holdout. The first issue was corrected in the canonical analysis
composition by merging native, generic, and raster lanes per page with
geometric overlap precedence. The second remains open: the current model is an
advisory experiment, not evidence of field-level generalization.

This change does not turn Form-6 into the product boundary. The reviewed profile
still supplies high-quality calibration for that fingerprint, while unknown
documents use the page-composed generic pipeline and retain review-required
status. The falsifier for the new composition is a mixed-page benchmark where a
native page, vector page, and image-only page have independently adjudicated
targets and the merge either drops a non-overlapping field or retains a
duplicate overlapping proposal.

The review also identified two export and authority defects that are now
addressed. Server export rebuilds from the immutable source and accepted
manifest revision, and generic inferred candidates remain pending until an
explicit human acceptance event. Exact-token lexical matching prevents
identifier and name labels from being misclassified as choice or date fields.
The focused API regression verifies move, reject, manual add, collision-safe
source storage, and source/manifest/output hash binding. These are reusable
pipeline invariants; they do not establish native widget-tree preservation or
arbitrary-document recall.
