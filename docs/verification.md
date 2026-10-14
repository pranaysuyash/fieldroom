# Verification receipt

Run date: 2026-09-10

Receipts below are point-in-time evidence for the date shown; they are not
kept continuously current. Re-run the affected commands after detector or
gate changes and record a new dated receipt rather than editing old ones
(the test count, for example, grew from 53 to 71 by 2026-09-17).

Environment:

- `uv 0.12.7`
- CPython `3.13.3`, project-local `.venv`
- `uv pip check`: passed after browser, training, and cloud-entrypoint install, 95 packages compatible
- `uv.lock`: generated in the project workspace and tracked in Git (the
  earlier "no Git commit made" note is stale)

Commands and results:

| Command | Result | Evidence |
|---|---|---|
| `node --check browser/app.js && .venv/bin/python -m pytest -q` | 53 passed, 7 dependency/runtime deprecation warnings | Tier 2, S1; includes signature presence/missing-slot detection, session audit snapshot persistence, mixed-representation page routing, manifest-to-export revision binding, lexical counterexamples, inferred-target pending authority, label intent, textarea, dataset geometry, native multiline, cross-type duplicate contracts, multi-row Form-6 grid fill, real-PDF child geometry assertions, label repository privacy checks, license metadata, and the default training-eligibility gate |
| Rendered text-fill regression | Initial regression exposed `OFFICE-EXAMPLE` stored in `/V` but clipped to `OFFICE-EXAM` in rendered text; fitted widget appearance now preserves the complete value in a fresh PyMuPDF read | Tier 2, S2; defect reproduced then fixed |
| `python -m pdf_field_lab.cli analyze ...` | 33 logical fields, 49 vector candidates, 0 native fields | Tier 2/3 local integration receipt for the reviewed Form-6 profile |
| OpenCV probe at 150 DPI | 2 pages, 7,189 contours, 293 rectangular contours | visual evidence only, not semantic recall |
| Tesseract probe at 150 DPI | 925 words, mean confidence 86.23/93.60 by page | OCR evidence only |
| `qpdf --check` on editable and filled outputs | passed | structural PDF integrity |
| Fresh `pypdf.PdfReader` reopen | 2 pages, 52 fields | output object-graph receipt |
| SHA-256 source comparison | Desktop and project fixture both `2cf1421343c22676f15eff0ec6f31a4df6e7f7975dc0f3d88d2b29a1dcc79d34` | source-preservation receipt |
| Raster render with `pdftoppm` | pages rendered for visual inspection | local visual observation, not external viewer proof |
| Fresh CLI export/fill round trip | 33 logical targets, 52 reopened widgets, both outputs pass `qpdf --check` | Tier 2/3 local integration receipt |
| `.venv/bin/python scripts/train_target_model.py` | 8,734 records, 0.3778 group-disjoint holdout accuracy, 0.2500 holdout macro-F1; Form-6 family fully held out | Tier 2, S1; mixed reviewed/proxy supervision, not field-level gold proof; FUNSD test split excluded; geometry normalized |
| `.venv/bin/python -c 'import modal_train'` | `modal_entrypoint_import=ok` | Tier 2, S1; definition/import only, no remote submission |
| `uv run pytest -q tests/test_semantic_detection.py` | 2 passed; calibration fixture recovered 4 positives and promoted 0 hard negatives | Tier 2, S1; local deterministic detector calibration |
| `uv run python ... detect_semantic_targets(detector-calibration.pdf)` | `Applicant Name:` text, `Agree to terms:` choice, `Date:` date, and `Address:` whitespace target; no duplicate label targets | Tier 1/2; read-only comparison against the sibling human-reviewed fixture |
| `uv run pytest -q tests/test_raster_cv.py` | 2 passed; an image-only calibration recovered the same 4 typed targets, including borderless whitespace, with all targets review-required | Tier 2, S1; local OCR/CV calibration |
| `.venv/bin/python scripts/system_corpus_benchmark.py --max-per-category 6 --render-count 24` | 21,188 PDFs inventoried, 20,138 evaluation candidates, 146 stratified deep samples, 94 logical targets, 88 native fields, 14,292 vector diagnostics, 50 raster-deferred samples, and 2 recorded deep-analysis errors | Tier 4 visual plus Tier 2 receipt, S1; local system corpus |
| `uv run python scripts/system_corpus_benchmark.py --root ~ --disable-default-exclusions --collect-only --output-dir artifacts/system-corpus/all-pdfs-collect-pass-v3` | 22,426 PDFs inventoried with `0` excluded (`disable-default-exclusions`), 13 unreadable in inventory metadata, and `33` files under `~/Projects/pdf_editor (local sibling, not public)/benchmark/datasets` included | Tier 2, S2 local structural inventory |
| `uv run python scripts/system_corpus_benchmark.py --manifest-path artifacts/system-corpus/all-pdfs-collect-pass-v3/inventory.jsonl --disable-default-exclusions --analyze-all --manifest-start 0 --manifest-limit 500` | 500 candidates analyzed; 1,734 logical targets, 1,734 total strategy events, 1,802 native fields, 36,726 vector diagnostics, 15 analysis errors, 118 raster-deferrals (runbook-first manifest slice) | Tier 2, S3 local analysis (deterministic candidate ordering) |
| `uv run python scripts/system_corpus_benchmark.py --manifest-path artifacts/system-corpus/all-pdfs-collect-pass-v3/inventory.jsonl --disable-default-exclusions --analyze-all --manifest-start 500 --manifest-limit 500` | Next 500 candidates analyzed; 431 logical targets, 431 strategy events, 1 native field, 38,715 vector diagnostics, 1 analysis error, 464 raster-deferrals (second manifest slice) | Tier 2, S3 local analysis (chunked reproducibility) |
| `uv run python scripts/system_corpus_benchmark.py --manifest-path artifacts/system-corpus/all-pdfs-collect-pass-v3/inventory.jsonl --disable-default-exclusions --analyze-all --manifest-start 5948 --manifest-limit 234` | Complete current `~/Projects/pdf_editor (local sibling, not public)` family: 234 analyzed, 2,095 logical targets, 1,284 native fields, 1,208 vector diagnostics, 16 analysis errors, 132 raster-deferrals; regenerated v2 visual receipt from measured records | Tier 2 plus Tier 4 visual, S3 deterministic family pass; includes the 33 downloaded dataset/fixture PDFs |
| `uv run python scripts/system_corpus_benchmark.py --manifest-path artifacts/system-corpus/pdf-editor-all-pass-v2/inventory.jsonl --disable-default-exclusions --analyze-all --manifest-start 150 --manifest-limit 20 --run-raster` | Bounded CV/OCR pass: 20 analyzed, 154 logical targets, 143 native fields, 26 vector diagnostics, 1 unreadable input, and 2 raster targets; `raster_requested=true` is recorded in the receipt | Tier 2 plus Tier 4 visual, S1 bounded raster execution; not scanned-form recall proof |
| `uv run python scripts/system_corpus_benchmark.py --manifest-path artifacts/system-corpus/user-folders-collect-v1/inventory.jsonl --disable-default-exclusions --analyze-all --max-analysis-bytes 20000000` | All 1,390 PDFs in Desktop, Documents, and Downloads analyzed; 1,017 logical proposals, 103 native fields, 109,273 vector diagnostics, 4 analysis errors, 999 raster-deferrals; 20 MB budget recorded | Tier 2 plus Tier 4 visual, S3 local real-user-folder stress pass; not field-level recall proof |
| `uv run python scripts/system_corpus_benchmark.py --manifest-path artifacts/system-corpus/user-folders-all-pass-v2/inventory.jsonl --disable-default-exclusions --analyze-all --manifest-start 3 --manifest-limit 1 --run-raster --max-analysis-bytes 20000000` | `Form6_preview.pdf` executed through CV/OCR and produced 4 review-required targets across a 3-page scanned form; visual comparison found substantial missed regions | Tier 4 visual plus Tier 2 receipt, S1; explicit real-world recall gap |
| `.venv/bin/python scripts/build_goldset.py` | 3 independent families x 3 representations; vector and image-only 18/18 recall and precision 1.0; 18/18 type and label association in both lanes; 0/6 hard-negative false positives; 0 duplicate pairs; 4 native fields per native PDF | Tier 2 plus Tier 4 visual, S1; authored controlled fixture, not real-world generalization proof |
| Fresh local server from current source on an isolated port | `GET /health` returned `status=ok`, and `GET /` returned the Fieldroom landing page; existing port 8790 process was not reused as current-source proof | Tier 4 local runtime; no production, browser-device, or hosted claim |

The seven warnings are upstream Starlette/httpx/anyio and PyMuPDF/OpenCV
deprecation warnings and did not fail the suite. No browser, device, provider, production, legal, or external
viewer evidence is claimed.

## Browser runtime receipt

| Surface | Result | Evidence |
|---|---|---|
| `uvicorn pdf_field_lab.server:app --host 127.0.0.1 --port 8790` | started and served the app | Tier 4 local runtime observation |
| `GET /` | Fieldroom landing page loaded with title and upload surface | Tier 4 browser observation |
| Browser upload of `RAr0Lq2Avu.pdf` | two page thumbnails, 33 targets, and labeled overlays rendered | Tier 4 browser observation |
| Browser field map | 33 targets summarized as 15 Text, 1 Date, 5 Choice, 1 Photo, 2 Signature, and 9 Other; All/Text/Date/Choice/Photo/Signature/Other/Review filters rendered | Tier 4 browser observation |
| Browser Photo filter and inspector | one photo target isolated; inspector exposed `PHOTO` plus upload/drop interaction and plain-language guidance | Tier 4 browser observation |
| Browser Signature filter and inspector | two signature targets isolated; applicant signature selection moved to page 2 and exposed Draw/Type/Upload modes | Tier 4 browser observation |
| Browser inline composite editor | selecting `Assembly constituency number and name` created number/name inputs over the page; one name string was entered and stored as a structured object; ✓ marked the target reviewed and moved progress to 3% | Tier 4 browser observation |
| Text target inline editor | selected text target opened an input over the PDF with 92% reviewed-profile confidence; ✓ acceptance marked it reviewed | Tier 4 browser observation |
| Checkbox-review contract hardening | ✓ now validates data presence before setting `accepted`, and an empty inline value now keeps targets in pending state with a toast prompt | Tier 2 static + local runtime proof (manual local session) |
| Photo target inspector | `PHOTO DROPZONE`, upload control, review metadata | Tier 4 browser observation |
| Signature target inspector | `SIGNATURE PAD` with Draw, Type, Upload modes | Tier 4 browser observation |
| Browser export | `POST /api/sessions/{id}/export` returned 200 for the structured `F6-02.name` value, reopened as a two-page/52-widget PDF, and the download endpoint returned 200 | Tier 3/4 local integration observation |
| `qpdf --check` on browser export | no syntax or stream encoding errors | Tier 2/3 local integration receipt |
| Generic promotion regression | Synthetic PDF with one labeled box and one unlabeled box promoted only the labeled box; the unlabeled geometry remained a vector candidate | Tier 2, S1 |
| Table-grid precision regression | Invoice-like repeated row-and-column geometry with a field-like `Month` header emitted zero logical targets while retaining raw vector diagnostics | Tier 2, S1 |
| Fresh API upload of Medpiper after detector restart | 20 pages, 0 logical targets, 236 vector diagnostics; no generic fields shown to the editor | Tier 4 local runtime and Tier 3 API observation |
| Medpiper signature audit | 12 expected signer slots; 9 present and 3 missing. One expected signer is missing on pages 2, 3, and 20; the two remaining signers are present on pages 1, 2, 3, and 20 (signer identities are redacted from public docs; the full names live only in the untracked local test fixture). `analysis.json` and `audit_log` retain the source hash and detector version | Tier 2/3, S1; review-only observation lane, not editable targets |
| Medpiper source visual comparison at 160 DPI | Page 1 visibly contains all three signatures. Page 20 visibly contains the two director signatures and one empty expected signing area. Page 18 has no signing block and produced no observation | Tier 4 local visual observation supported by image-object and raster occupancy checks |
| Fresh API upload of Form-6 after detector restart | 2 pages, 33 typed logical targets, 49 vector diagnostics; target kinds were 15 text, 1 date, 5 choice, 1 photo, 2 signature, and 9 composite | Tier 4 local runtime and Tier 3 API observation |
| High-resolution visual audit of Form-6 source pages and corrected target overlay | Found two uncovered multi-row name grids, an undifferentiated mobile grid, missing Aadhaar digits and disability percentage, label-overlapping child regions, and a signature band touching its caption; canonical profile and renderer were corrected, with separate row/option outlines and ordered export geometry | Tier 4 visual observation supported by Tier 1 geometry inspection; not a complete recall proof |
| Form-6 grid regression | `F6-05` preserves 14 upper-row cells plus 28 lower-row cells and `F6-12` preserves two 10-cell mobile rows as one user-facing field; child geometry assertions and row-by-row fill tests pass | Tier 2, S1; geometry is source-specific and remains review-required |
| Fresh current-source browser upload of controlled typed gold form on isolated port 8791 | 6 targets rendered as Text, Text area, Date, Choice, Photo, and Signature; textarea accepted a complete answer once with one ✓ and manifest `PUT` returned 200; photo inspector exposed only `PHOTO FIELD` plus Upload/drop behavior | Tier 4 browser/runtime observation; current source, local-only |
| Committed text fill feedback and export appearance | After ✓, text and composite values render as persistent green committed overlays and the toast says `filled on page`; a Form-6 export containing `OFFICE-EXAMPLE` reopens with the complete value in PyMuPDF text extraction and the rendered page image | Tier 2/4 local evidence; current source and sample PDF |
| Browser abstention and field taxonomy contract | Zero active targets display `No editable targets found` at 0% instead of 100% reviewed and expose `Draw a field manually`; choices share one visible family with `single-select` or `multi-select`; composites render named groups such as Constituency, Address, Identity, and Date + place | Tier 2 static contract plus Tier 4 current-source asset/runtime evidence; no-target visual interaction still needs a fresh automated browser upload receipt |
| Isolated current-source runtime | Port 8791 restarted after the latest profile and browser corrections; current browser asset exposes positioned Form-6 row/option outlines and distinct Choice subtype labels; ambient port 8790 process was not modified | Tier 4 runtime ownership receipt |
| Mixed-representation page routing regression | A synthetic three-page composition retained a native target on page 1, a vector target on page 2, and a raster target on page 3; the overlapping vector duplicate on page 1 was suppressed; fresh Form-6 and Medpiper analyses remained 33 and 0 logical targets respectively | Tier 2, S1 plus Tier 3 local real-PDF integration; does not prove page classification recall |
| Manifest-to-export revision regression | A real API flow uploaded Form-6 as `editable.pdf`, moved `F6-01`, rejected `F6-02`, added `manual-added`, exported revision 1, and verified the moved widget, removed composite widgets, added widget, source hash, manifest hash, and output hash | Tier 2, S1 plus Tier 4 local API flow; browser interaction and native-field preservation remain separate gates |
| Generic lexical and review-authority regression | `Account no:`, `Phone no:`, and `Candidate name:` remain text; Unicode survives label normalization; inferred photo and signature candidates create pending manifest entries instead of accepted entries | Tier 2, S1; English lexical coverage and multilingual semantics remain open |
| Label repository build | Builder produced 13 records: 9 controlled proxy records and 4 pending records, including sanitized Form-6 and Medpiper annotation manifests; no PDFs or signature/photo pixels are stored | Tier 2, S1; source files remain local references |
| Trainable label view gate | Default view contains 0 records and excludes all 4 pending plus 9 proxy records; explicit `--include-proxy` produces 9 development records and a receipt | Tier 2, S1; no model job was run from the view |
| Overlay hierarchy visual refinement | Fresh Chrome upload of the real Form-6 source showed 19 page-1 targets, including 10 groups; ordinary review targets use transparent 1px outlines, grouped targets use a light rounded perimeter, and child regions have no filled boxes | Tier 4 local visual/runtime evidence plus browser contract tests; source geometry and export behavior unchanged |

## Generalization check: Medpiper financial statement

The user-supplied signed financial statement (20 pages, local path redacted
from public docs) was inspected and uploaded through a temporary local transport
copy. The
original was not modified or added to the project. Static inspection found 20
pages, no native fields, no annotations, a substantial text layer, and a valid
`qpdf --check` result.

The first generic run exposed 231 user-facing targets, all sourced from vector
geometry. The detector was then recalibrated around three failures: wide
shallow entry rectangles, underlines represented as authored lines rather than
rectangles, and labeled whitespace with no border. A line-level label join,
compact form-surface gate, symmetric geometry deduplication, and removal of the
page-position signature guess followed. The current direct analysis reports
zero generic logical targets and 236 review-only vector candidates. The
separate signature audit reports 12 expected slots, 9 present and 3 missing.
That is the expected conservative result for this financial statement: it has
no verified form affordances, and its table/prose geometry must not appear as
editable fields. This is a precision result, not proof of universal recall.

The current source server runs on isolated port 8791 and the API session data
contract exposes the signature observations to the browser renderer. The CUA
browser surface loaded the current Fieldroom shell, but its evaluator does not
provide a file-input setter or the page’s real JavaScript context, so a fresh
interactive Medpiper upload could not be attached through that automation
surface. The page-1/page-20 source renders and API/session assertions are the
current visual and runtime evidence. Browser proof is local-only. It does not
prove production concurrency, durable storage, malware safety, legal signature
validity, external viewer compatibility, or semantic recall on arbitrary PDF
populations.

No Modal job was submitted. The credential audit found no project `.env`,
Modal token environment variables, or local `.modal.toml`; the cloud entrypoint
is prepared but intentionally unauthenticated and unexecuted.
