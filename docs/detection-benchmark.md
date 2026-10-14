# Detection benchmark and exploration map

Date: 2026-09-10

## Purpose

The detector must work across native forms, flat vector forms, image-only
scans, and ordinary PDFs without presenting layout geometry as user inputs.
This document separates evidence sources and defines the first reproducible
field-level evaluation. It is an evaluation contract, not a claim of universal
accuracy.

## Evidence families

| Family | What it can prove | Current source | Status |
|---|---|---|---|
| Native | Exact AcroForm/XFA widget presence and widget geometry | Local PDF-editor corpus | Structural truth; should outrank inference |
| Reviewed profile | Human-reviewed semantics for a known template fingerprint | Form-6 profile and source PDF | 33 logical targets; template-specific |
| Vector geometry plus text | Drawn rectangles, rules, lines, nearby labels, and labeled whitespace | Local calibration fixture and controlled gold set | Calibration 4/4 positives, 0/5 hard-negative promotions; controlled gold 18/18 positives |
| Raster CV plus OCR | Visual contours, OCR labels, and scanned whitespace | Image-only calibration and controlled gold set | Calibration 4/4 positives; controlled gold 18/18 positives; all review-required |
| Proxy layout labels | Document regions or form entities useful for representation learning | FUNSD and DocLayNet local datasets | Not fillable-field gold labels |
| Model output | Advisory type or ranking signal | `artifacts/model/target-classifier.joblib` | Cannot override geometry, semantics, or review |

## Reproducible calibration command

The reviewed calibration PDF and label manifest live in the sibling project and
are read-only inputs:

```bash
uv run python scripts/evaluate_detector.py \
  --pdf ~/Projects/pdf_editor (local sibling, not public)/benchmark/results/detector-calibration/detector-calibration.pdf \
  --labels ~/Projects/pdf_editor (local sibling, not public)/benchmark/results/detector-calibration/detector_calibration_labels.json
```

The evaluator validates the manifest SHA-256, converts reviewed lower-left
coordinates to top-origin coordinates, performs one-to-one positive matching,
allows a specific vertical tolerance for thin underlines, and reports:

- positive recall and matched geometry overlap
- hard-negative false-positive rate
- unmatched prediction false-positive count, precision, and F1
- required type accuracy
- reviewed-label similarity and association rate
- duplicate candidate pairs regardless of predicted kind

The current vector calibration result is 4/4 unique positives, 0/5 hard-negative
false positives, 100% required-type accuracy for the reviewed checkbox, 100%
label-association recall, and no duplicate semantic targets. The image-only
calibration independently recovers the same four typed controls, including a
borderless whitespace field. The receipt is preserved at
`artifacts/detector-calibration-evaluation.json`.

## Controlled gold-set workflow

The reproducible authored gold-set workflow is:

```bash
uv run python scripts/build_goldset.py
```

The script creates three independent privacy-safe form families:

- employment application
- travel consent
- vendor onboarding

Each family is emitted as a flat vector PDF, a PDF with native text and choice
widgets, and an image-only flattened PDF. The reviewed target manifest is
authored before detector execution and includes text, textarea, date, choice,
image, and signature targets plus one decorative-divider hard negative. The native
representation is evaluated structurally because image and signature targets
are intentionally visual overlays rather than AcroForm widgets.

The latest receipt is:

| Measure | Result |
|---|---:|
| Independent families | 3 |
| Representations | 9, three per family |
| Vector positive recall and precision | 18/18, 1.0 |
| Image-only positive recall and precision | 18/18, 1.0 |
| Vector and image-only type accuracy | 18/18 each |
| Vector and image-only label association | 18/18 each |
| Hard-negative false positives | 0/6 |
| Duplicate target pairs | 0 |
| Native fields per native PDF | 4 |

The machine-readable artifacts are:

- `artifacts/goldset/goldset-manifest.json`
- `artifacts/goldset/summary.json`
- `artifacts/goldset/<family>/<representation>-labels.json`
- `artifacts/goldset/<family>/<representation>-evaluation.json`
- `artifacts/goldset/visual/contact-sheet.png`

The contact sheet was independently reviewed after the latest run. Target
boxes aligned with their authored text, choice, photo/logo, and signature
regions in all nine cards. This workflow is an authored controlled positive
set, not a human-reviewed real-world set. It must not be used to claim
universal recall, multilingual robustness, handwriting robustness, or legal
signature validity.

## Local system-corpus verification

The reusable system-corpus harness is
`scripts/system_corpus_benchmark.py`. It performs a lightweight inventory over
Desktop, Documents, Downloads, and Projects, then runs the canonical analyzer
on a deterministic stratified sample of up to six documents per category and
source bucket. It renders the first page of the first 24 sampled documents into a
contact sheet with page-one logical-target overlays.

The latest run produced:

| Measure | Result |
|---|---:|
| PDFs inventoried | 21,188 |
| Inventory-only dataset, benchmark, generated, or dependency files | 1,050 |
| Evaluation candidates | 20,138 |
| Deep detector sample | 146 |
| Native fields observed in sample | 88 |
| Logical targets emitted | 94 |
| Raw vector diagnostics | 14,292 |
| Text-poor samples with raster deferred | 50 |
| Deep analysis errors | 2 |

The 94 logical targets break down into 40 text, 17 textarea, 13 choice, 13
signature, 1 image, 1 date, and 9 composite targets. These are counts, not
accuracy, because the sampled system corpus has no field-level gold manifest.

The machine-readable artifacts are:

- `artifacts/system-corpus/summary.json`
- `artifacts/system-corpus/inventory.jsonl`
- `artifacts/system-corpus/benchmark.json`
- `artifacts/system-corpus/visual/contact-sheet.png`

The visual check found correct page proportions and no clipping or coordinate
inversion across identity pages, signed forms, phone scans, statements,
resumes, reports, tickets, and policy material. Logical overlays remain
review-required unless they come from native widgets or a reviewed template
profile. The invoice benchmark hard negative was separately probed after the
table-grid suppression change and now emits zero logical targets while
retaining its raw vector diagnostics.

The two deep analysis errors were retained as boundary evidence: one malformed
skill-example PDF returned `PdfStreamError`, and one encrypted or closed policy
schedule returned `ValueError`. They are not counted as detector successes or
silently dropped. The harness also records one unreadable candidate from the
structural inventory.

A broader system pass has also been run over the full `~` tree
using `--disable-default-exclusions`, with a manifest-based chunking mode to keep
coverage auditable and resumable. The manifest collected `22,426` PDFs and confirmed
`33` files from `~/Projects/pdf_editor (local sibling, not public)/benchmark/datasets` plus
`201` other pdf_editor PDFs are included in the inventory. We then ran two
deterministic 500-file slices from the same manifest:

- `all-pdfs-manifest-batch-00` analyzed the first 500 entries and reported 1,734
  logical targets, 15 analysis errors, and 118 raster-deferrals.
- `all-pdfs-manifest-batch-01` analyzed the next 500 entries and reported 431
  logical targets (1 error, 464 raster-deferrals).

The complete `pdf_editor` family was then selected from the current inventory by
recomputing its manifest range (`start=5948`, `limit=234`) rather than relying on
an assumed offset. The v2 pass analyzed all 234 PDFs, including all 33 files in
`benchmark/datasets`, and reported 2,095 logical targets, 1,284 native fields,
1,208 vector diagnostics, 16 analysis errors, and 132 text-poor records whose
raster lane was intentionally deferred. A high-resolution contact sheet was
visually inspected after fixing the renderer to consume measured detector
records; native checkbox/radio/text targets now appear in the overlay artifact.

A bounded raster-enabled slice of 20 `pdf_editor` records executed CV/OCR on
text-poor pages. It produced 154 logical targets, 143 native fields, 26 vector
diagnostics, one unreadable input, and two raster targets on the synthetic
handwritten completion sample. The clean OCR samples correctly produced no
targets because their visuals contain narrative text but no blank field
affordances. This is a lane-execution and precision observation, not universal
scanned-form recall.

The first attempt to analyze all user-folder PDFs was interrupted after a
21 MB, nine-page image-heavy PDF spent several minutes in recursive text-layout
resolution. The failure is preserved as a harness hardening finding. Full
system runs now support `--max-analysis-bytes`; oversized files remain in the
inventory and are marked as resource-budget skips rather than being reported as
empty or unreadable documents.

The completed user-folder pass analyzed all `1,390` PDFs from Desktop,
Documents, and Downloads with a `20,000,000` byte analysis budget. It reported
`1,017` logical proposals, `103` native fields, `109,273` vector diagnostics,
`4` analysis errors, and `999` raster-deferrals. Visual inspection of the first
24 real-user pages showed correct abstention on narrative resumes, tickets, and
handwritten list scans, while the real `RAr0Lq2Avu.pdf` produced `19` page-one
targets in the generic holdout pass. A related `Form6_preview.pdf` was then
run through CV/OCR: it produced `4` review-required targets, but visual
comparison confirmed substantial misses across address, grids, photo,
disability, and signature regions. This is the current highest-value recall
case for the scanned-form gold set.

These chunked batches are intentionally not a final corpus recall claim yet, but
they establish end-to-end repeatability over all folders and the learning/ml
dataset region without relying on legacy exclusion filters.

## Corpus map

The local PDF-editor corpus contains the following evaluation slices:

- native and XFA forms: exact widget extraction, choice controls, rotation,
  navigation, and XFA coexistence
- flat and vector geometry: authored boxes, rules, grids, sparse forms, and
  dense layout negatives
- scanned and OCR: clean English, noisy scans, low contrast, small fonts,
  printed scans, dense paragraphs, rotated certificates, and simulated scans
- mixed content: text plus raster, multi-page layouts, and hybrid forms
- hard negatives: plain text, multi-column prose, charts, graphics-heavy pages,
  headers and footers, metadata-only documents, and financial statements
- sensitive or malformed inputs: encrypted, truncated, invalid-structure, and
  signed-invalid fixtures for boundary and failure handling

The manifest at
`~/Projects/pdf_editor (local sibling, not public)/benchmark/results/governed-corpus-manifest.json`
describes 38 fixtures across 15 document classes. It is not treated as a
field-label gold set. The human-reviewed calibration manifest is the only
current direct semantic benchmark.

The read-only corpus exploration recorded these additional governance facts:

- The governed corpus human-review report currently says `confirmedCount: 0`,
  `totalFixtures: 38`, and `status: pending`. It must not be described as a
  reviewed semantic gold set until that gate is completed.
- Native samples such as public sample forms, PDFKit widget fixtures,
  incremental widget fixtures, and XFA fixtures are valuable for native-widget
  preservation, coordinate handling, and export compatibility. They do not
  label fields painted into a flat page.
- FUNSD and DocLayNet are proxy supervision. FUNSD supplies document-layout and
  entity-like signals, while DocLayNet supplies layout classes. Neither is a
  reviewed target manifest for this product's fillable-field ontology.
- The current Form-6 profile and calibration fixture are useful development
  evidence, but exact-template recognition and derivatives of the same source
  must remain one document family. They cannot also serve as a hidden
  generalization benchmark.
- The handwritten fixture is simulated-font content, not genuine handwriting.
  It is useful for robustness probing, but it cannot support a claim about
  handwriting recognition or handwriting-field detection.

### Exact local evidence paths

These paths are retained as read-only corpus references, not copied into the
product's training artifacts:

| Evidence slice | Path or family | Use | Boundary |
|---|---|---|---|
| Reviewed calibration | `~/Projects/pdf_editor (local sibling, not public)/benchmark/results/detector-calibration/` | Vector positives, label association, and hard negatives | Small reviewed fixture, not generalization proof |
| Governed inventory | `~/Projects/pdf_editor (local sibling, not public)/benchmark/results/governed-corpus-manifest.json` | Fixture and class inventory | Human review still pending |
| Review status | `~/Projects/pdf_editor (local sibling, not public)/benchmark/results/human-visual-confirmation/human-review-gate-report.json` | Confirmation gate receipt | Currently 0 of 38 confirmed |
| Native widgets | `public-sample-form.pdf`, `2026-08-23-pdfkit-widgets/fixture.pdf`, native incremental fixtures, XFA fixtures under `corpus-sweep-2026-08-25/` | Widget preservation and structural extraction | Not flat-field semantic gold |
| OCR and scans | `scanned-noisy.pdf`, `printed-scan.pdf`, `clean-english.pdf`, `noisy-invoice.pdf`, `low-contrast.pdf`, `small-font.pdf` | Raster/OCR robustness | OCR truth is transcription, not field semantics |
| Rotation and hybrid | `rotation-corpus/`, `rotated-hybrid-90.pdf`, `rotated-certificate.pdf`, `geometry.pdf` | Coordinate and orientation robustness | Requires reviewed target manifests |
| Simulated handwriting | `governed-corpus/handwritten-simulated-entries.pdf` | Abstention and robustness probe | Simulated font, not genuine handwriting |

The directory prefix for entries without an absolute path is
`~/Projects/pdf_editor (local sibling, not public)/benchmark/results/`. Before any future
benchmark run, record the source hash, document family, producer lineage, and
review status in the manifest so an apparent new sample cannot silently be a
derivative of an existing one.

## Leakage and validity rules

1. Do not train and evaluate on the same PDF or a byte-identical derivative.
2. Keep template profiles, label augmentations, FUNSD entities, and DocLayNet
   regions tagged by supervision strength.
3. Do not call a layout region such as `picture` or `question` a fillable field
   without a reviewed field-level mapping.
4. Split by document family and template, not by cropped region, so near-copy
   pages do not cross train and test boundaries.
5. Keep source PDFs and completed personal documents out of training artifacts.
6. Report abstention and false-positive rate alongside recall. A high recall
   detector that floods a prose PDF with fields is not useful.
7. Treat source hash, producer family, template lineage, export lineage, and
   corpus-sweep ancestry as duplicate-control signals. Different filenames are
   not evidence of independent documents.
8. Treat any result as provisional while the governed corpus human-review gate
   remains pending.

The training loader now defaults to FUNSD `train.json` only, normalizes FUNSD
endpoint boxes and the local DocLayNet `box` convention, and the advisory
classifier uses a group-disjoint holdout. The current model receipt records
8,734 records, 0.3778 holdout accuracy, and 0.2500 holdout macro-F1 with the
entire Form-6 family held out. The textarea class has only three reviewed
anchors, so this score is evidence of a small proxy baseline, not production
semantic classification. The model remains advisory and is not a detector
authority.

The evaluator now measures one-to-one geometry, expected-label similarity,
unmatched proposal precision/F1, cross-type duplicate overlap, and native
multiline/radio metadata where available. The controlled gold set reports
18/18 typed targets in each semantic lane, but that result is intentionally
bounded to three authored families.

The canonical future manifest should carry at least `document_id`,
`document_family_id`, source SHA-256, split, language, handwriting status,
provenance, review status, and target records with normalized coordinates,
intent, field type, label span, group, evidence, abstention, and detector
version. Evaluation should use one-to-one matching and report precision,
recall, F1, IoU, label association, type accuracy, duplicate pairs, and
risk-coverage for abstentions. These fields make it possible to distinguish a
real generalization gain from template memorization or a proxy-task gain.

## Next benchmark slices

The controlled gold set closes the first authored milestone. The next gold set
should be assembled in this order:

1. Five to ten distinct real-world flat vector forms with reviewed boxes, underlines,
   checkboxes, signatures, photographs, and whitespace fields.
2. Their image-only flattened versions at multiple scan qualities to test
   vector versus OCR/CV invariance.
3. Rotated and multi-column variants with page-coordinate checks.
4. Multilingual labels and handwriting-like entries with explicit abstention
   labels where OCR is not reliable.
5. Prose, invoices, statements, charts, and layout-heavy hard negatives.

Each reviewed target should record page, coordinate origin, bbox, kind,
label association, grouping, required evidence families, and whether abstention
is the expected result. Type, geometry, and association should be scored
separately so a model cannot hide a type error behind a good box overlap.
