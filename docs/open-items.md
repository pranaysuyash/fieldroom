# Fieldroom open-items register

Date: 2026-09-10

This is the canonical status list for work that remains after the controlled
gold-set milestone. “Closed” means there is local implementation and evidence
for the bounded behavior. “Open” means the product may have scaffolding, but a
required evidence or hardening gate is not closed. No item below authorizes
external uploads, provider jobs, Git mutations, or production exposure.

The canonical, dependency-ordered register below is the source of truth for
execution priority. Keep each item as a stable ID and update status only when the
acceptance evidence is in place.

The durable rationale and method are recorded in
[docs/learning-ledger.md](learning-ledger.md). This status list tracks closure;
the ledger explains the reusable lessons and falsifiers behind each gate.

## Register-vs-code drift ritual

Per-milestone, before closing the milestone: grep the register's claims
against the code (an hour of targeted checks — limits, env flags, doc
statements about what is implemented). Two drift instances were caught this
way on 2026-09-17 (SEC-010 size limits already implemented; a stale
`uv.lock` note in verification.md). Update the register first, then code.

## Canonical execution register

| ID | Priority | State | Module(s) | Open issue | Owner | Acceptance / falsifier | Evidence | Depends on | Next action |
|---|---:|---|---|---|---|---|---|---|---|
| FFL-CFG-001 | P1 | Implemented | `src/pdf_field_lab/config.py`, `src/pdf_field_lab/server.py` | Resource limits and session TTL previously accepted zero/negative integers, allowing settings such as a zero page cap or immediate session expiry; malformed strings failed with an opaque import-time `ValueError`. | Core engine owner | Defaults and valid positive overrides remain accepted; malformed, zero, negative, and nonpositive defaults fail at startup with the setting name and a clear positive-integer requirement. | Baseline executed the exact prior assignment and confirmed `PDF_FIELD_LAB_MAX_PAGES=0` was accepted; `python3 -m pytest -q tests/test_config.py` passes 6 tests (T2/S2). 2026-10-09: full suite green in a deps-enabled throwaway venv (Python 3.14.7, all core + cv/ocr/training extras, tesseract present) — 77 passed including all `tests/test_server.py` integration tests; coverage ratchet met at 84.16%. | FFL-SEC-010 | First green GitHub Actions run once billing is fixed (FFL-CI-014); preserve positive-only semantics. |
| FFL-GOV-001 | P0 | Implemented | `src/pdf_field_lab/label_policy.py`, `scripts/build_trainable_label_view.py`, `scripts/train_target_model.py`, `modal_train.py` | Training entrypoints now consume one receipt-bound label view. The gate is fail-closed for split role, status, manifest, source hash, license, privacy class, reviewer receipt, training approval, and family isolation. The review-receipt contract is now enforced, not just required: `review_receipt` must be an object carrying `receipt_sha256` and a `reviewer` matching `annotation.reviewer` — the same shape the server's hash-bound review receipts produce (FFL-HQ-006). | Current operator + field-review owner | Default trainer refuses the empty or stale view; explicit proxy mode trains only controlled development records; verified mode requires reviewer and training-approval metadata. Focused tests pass and an actual proxy-mode trainer run consumed 63 expanded examples. A real approved record and review receipt are still required before production-style training evidence exists. | Tier 2 plus bounded local training run; S2 stale/refusal coverage; 2026-10-14: `tests/test_verified_fixture.py` proves a sanitized synthetic verified record is consumed in default mode, that `validation`/`locked-test` roles stay excluded, and that missing/hash-less/mismatched receipts are rejected | FFL-LBL-002 | First real review session (HQ-006) supplies the first real receipt; production-style training evidence stays open until then. |
| FFL-LBL-002 | P0 | Closed | `scripts/build_label_repository.py`, `data/labels/records.jsonl`, `data/labels/review-queue.jsonl` | Label rebuild rewrites existing human records and can erase verified corrections. Needs idempotent update + hash-level conflict handling. | Labeling owner + current operator | Re-running repo build keeps verified records/metadata unchanged while refreshing stale/non-authoritative rows; source-hash changes demote verified status for re-review. Verified retention is covered by `tests/test_label_repository.py::test_verified_annotations_are_preserved_across_rebuild` and `::test_source_hash_change_reopens_verified_records`; queue merge now rebuilds deterministically in `main`. | Tier 2 (regression) | FFL-GOV-001 | Keep running regression check if schema expands or annotation manifest paths change. |
| FFL-NAT-003 | P1 | Implemented | `pdf_field_lab/native_detect.py`, `pdf_field_lab/export_pdf.py`, `pdf_field_lab/models.py` | Native text, buttons, signatures, and dropdowns now carry explicit native strategy families; mixed reconstruction appends inferred widgets to the cloned AcroForm instead of replacing the native tree. Repeated widgets, inherited properties, XFA, option-state fidelity, and edited-native geometry remain open. | Core engine owner | `tests/test_native_detect.py` proves `/Ch` becomes typed `Choice`; `tests/test_export.py::test_mixed_export_preserves_existing_native_field_tree` proves native plus inferred fields reopen together. Full native identity, widget grouping, and state fidelity still require additional fixtures. | Tier 2, 6 focused tests passed | FFL-GOV-001 | Add native radio/dropdown/repeated-widget fixtures and verify original options, values, flags, and parent/kid relationships after mixed export. |
| FFL-REV-004 | P1 | Implemented | `pdf_field_lab/server.py`, `pdf_field_lab/export_pdf.py`, `browser/app.js` | Exports are now immutable per manifest revision, manifest hash, and values hash. Download URLs carry all three identities; the server verifies the matching receipt, source hash, output path, and output hash before serving. | Product owner | `tests/test_server.py::test_download_url_is_bound_to_manifest_and_values_revision` proves two values produce distinct stable downloads, while the earlier accepted revision remains retrievable. Production storage, multi-worker locking, and external viewer compatibility remain open. | Tier 3 local API; 6 server tests passed | FFL-NAT-003 | Extend with concurrent multi-worker storage tests and viewer reopen receipts; retain immutable artifacts when durable sessions are introduced. |
| FFL-EVL-005 | P1 | Implemented | `scripts/evaluate_detector.py` | Matching is now a stable, order-invariant assignment (global best-IoU-first with deterministic `(case_id, prediction_id)` tie-breaks), wrong-label matches are a first-class failure class (`label_error_count` / `label_error_rate` / `label_errors`), misses carry `nearest_prediction` diagnostics with `consumed_elsewhere`, and association matching takes the best-label match. Schema bumped to `detector-evaluation.v2`; calibration receipt regenerated with unchanged quality (recall 1.0, precision 1.0, 0 hard-negative FPs, 0 label errors). | Quality owner | evaluator emits a wrong-label counterexample and a stable matching policy that separates localization recall from label/ontology correctness. | Tier 2: `tests/test_evaluate_detector.py` (tie-break determinism, order invariance, double-booking, label-error, miss diagnostics) | FFL-RANK-007 | Run evaluator v2 per family when the real-world document-disjoint gold set exists; Hungarian-optimal assignment and a real adversarial corpus remain open (exploration 2026-10-14). |
| FFL-HQ-006 | P0 | Implemented | `src/pdf_field_lab/review_diff.py`, `src/pdf_field_lab/server.py`, `browser/app.js` | Review events now carry reviewer, batch timestamp, resulting `manifest_sha256`, and a disagreement signal (`agreement` / `false-positive` / `detector-miss` / `geometry-correction` / `review-correction`); every manifest mutation writes a hash-bound review receipt binding reviewer, time, both revision states, and the exact candidates block; receipts and candidates are exported as governed JSONL. Replay safety: stale-revision PUTs 409 without appending, candidate ids are deterministic, and ingestion stays idempotent. | Human-review owner | A review session records reviewer, timestamp, disagreements, and manifest revision update; manual additions and rejects are replay-safe. | Tier 2: `tests/test_review_diff.py` governance tests + `tests/test_server.py` receipt-binding and replay tests. Tier 3 local API. Real review sessions have not been run. | FFL-LBL-002, FFL-REV-004 | Run real review sessions (Pranay as reviewer) to generate FLY-011 correction volume; asymmetric signing of receipts is a registered decision (FFL-D-receipt-signing), reviewer identity is operator attestation, not authentication. |
| FFL-MIX-007 | P1 | Proposed | `pdf_field_lab/analyze.py`, `pdf_field_lab/analysis.py`, `pdf_field_lab/geometry.py` | Mixed-lane logic still uses whole-document raster fallback and page-level overlap behavior is lightly covered. | Architecture owner | Real mixed-page fixture proves page-level routing, page-level failure isolation, and collision policy between native/vector/raster targets. | Tier 3 | FFL-EVL-005 | Add non-mocked mixed corpus fixture and assert per-page independence + failure recovery. |
| FFL-LANG-009 | P1 | Proposed | OCR + NLP modules, i18n UI surfaces | Multilingual detection and handwritten/script-aware pipelines remain open by design. | Linguistics/UX owner | Per-document and per-field language metadata exists, translation/transliteration is controlled and reversible, and mixed-script render is validated. | Tier 1–3 | FFL-GOV-001 | Keep open explicitly; add to P1 backlog with gated evidence; no false closure. |
| FFL-RANK-007 | P2 | Parked | `scripts/train_target_model.py`, `src/pdf_field_lab/analysis.py` | Decision made 2026-10-14 (owner-approved park): the advisory model's holdout is near-noise (0.378 accuracy / 0.25 macro-F1) and flywheel supply is insufficient to change that, so `PDF_FIELD_LAB_ADVISORY_MODEL` now defaults to **off** — no run loads the model unless an operator explicitly opts in with `=on`. The mechanism, training path, benchmark contract, and receipts all remain in place and tested. | ML owner | Advisory model only; cannot affect authority by default. Un-park requires ≥20 verified, document-disjoint corrections in a family from FLY-011 review sessions AND demonstrated uplift over the deterministic baseline on the same holdout contract. | Tier 2 (default-off covered by the analysis test suite; training lane exercised by `tests/test_target_model.py`) | FFL-GOV-001, FFL-FLY-011 | Keep the mechanism tested; revisit only when review-session volume meets the un-park threshold. |
| FFL-PORT-008 | P1 | Deferred | `pdf_form_field_lab` → `pdf_editor` | macOS port is not allowed until contracts close and no second source of truth is created. | Platform owner | Port starts only after FFL-NAT-003, FFL-REV-004, FFL-HQ-006, FFL-MIX-007 are verified. | Tier 3+ | FFL-NAT-003, FFL-REV-004, FFL-HQ-006 | Keep deferred, no implementation scheduling until prerequisite gates pass. |
| FFL-SEC-010 | P0 | Implemented | `src/pdf_field_lab/server.py`, `docs/security-quarantine-policy.md` | Upload limits (25 MB / 250 pages / 1000 targets, 413/422) remain regression-tested, and the quarantine half is now implemented locally: active-content quarantine (JavaScript, open actions, embedded files, XFA — detection only, fail-closed, named-category message), explicit encrypted-upload rejection, a shared operator-visible rejection audit ledger (`rejections.jsonl`, survives session deletion), TTL sweeps at startup/health/create with audited expiry, and an explicit 404 for vanished session storage. | Security owner | Explicit upload limits active and regression-tested; quarantine policy documented (`docs/security-quarantine-policy.md`); local rejections audited. | Tier 2: `tests/test_server.py` quarantine/audit/lifecycle tests | None (baseline) | Remaining is production-tier: durable storage decision (FFL-D-session-durability), multi-worker locking, and the production boundary (auth, rate limiting). XFA relaxation is a registered decision (FFL-D-xfa-policy). |
| FFL-FLY-011 | P1 | Implemented | `src/pdf_field_lab/review_diff.py`, `src/pdf_field_lab/server.py`, `scripts/build_label_repository.py`, `browser/app.js` | Review events (accept/reject/restore/manual-add/move) emit governed candidate JSONL per session and ingest as pending label records; ingested records survive plain rebuilds. Browser review actions (accept, reject/restore, manual add, move/resize) exist in `browser/app.js` and feed the manifest PUT; what is deliberately absent is a dedicated review-session dashboard, not the UI itself (2026-09-17 drift on this line corrected 2026-10-14). | Review-loop owner | `tests/test_review_diff.py` + `tests/test_server.py::test_review_candidates_export_governs_review_events` + builder retention test pass. Candidates are review evidence, never accepted labels. | Tier 2 | FFL-LBL-002, FFL-REV-004 | Run real review sessions, export candidates, and measure correction volume (feeds the RANK-007 model decision). |
| FFL-REPRO-012 | P2 | Implemented | `scripts/build_calibration_fixture.py`, `artifacts/calibration/` | Detector calibration no longer depends on sibling-project paths. The authored fixture reproduces offline: 4/4 positives, precision 1.0, type accuracy 1.0, label association 1.0, 0/5 hard negatives, 0 duplicate pairs. | Quality owner | `artifacts/calibration-evaluation.json` receipt regenerated by rerunning builder + evaluator. | Tier 2 + receipt | None | Keep fixture in sync with detector calibration changes; extend cases only with reviewed geometry. |
| FFL-REL-013 | P2 | Proposed | Repo root, `.github/` | Release hygiene: no LICENSE file. Changelog started at v0.1.1 and the annotated tag `v0.1.1` exists (pointing at `3c1c67e`; verified 2026-10-14 — the earlier "tag pending" line was register drift). Tagging of newer milestones and the license choice remain. | Repo owner | LICENSE present with declared pyproject license; annotated tag per milestone; changelog updated at each closure. | Tier 1 | FFL-SEC-010 closure | Choose license (MIT vs Apache-2.0 — FFL-D-license decision), add file, tag the next milestone. |
| FFL-CI-014 | P2 | Implemented | `.github/workflows/ci.yml`, `.github/dependabot.yml`, `pyproject.toml` | CI now installs CV/OCR/NLP extras with tesseract, runs ruff (correctness-first rule set), pytest-cov with an 80% ratchet baseline (measured 84%), and pip-audit as a non-blocking ratchet; Dependabot watches pip + actions (now on the private parent only). B-rule lint families (16 B023 loop-capture findings) are a registered follow-up review, not silently ignored. | CI owner | Green CI run on GitHub Actions: first green run achieved 2026-10-14 on the public mirror (Actions free there); parent repo billing still blocks its own runner. | Tier 2 local; Tier 3 green on github.com/pranaysuyash/fieldroom (run 38619215331) | None | Keep the parent's billing fixed or accept mirror CI as the durable Tier 3 path; flip pip-audit to blocking; then broaden ruff rules with B023 review. |
| FFL-REV-014 | P1 | Implemented | `browser/app.js`, `browser/index.html`, `browser/styles.css`, `tests/test_browser_contract.py` | Reviewer throughput was the flywheel bottleneck: review was click-only, manifest-ordered, with no queue navigation. Now: keyboard triage (j next unreviewed, a accept-and-continue reusing the existing commitTarget guard, x reject/restore, ? help; keys ignored inside form controls), a worst-confidence-first queue toggle (deterministic id tie-break, default stays document order), and required/conditional governance chips in the inspector. | Product owner | A reviewer can triage a page without touching the mouse; ordering change is user-visible and reversible; existing filters/views unchanged. | Tier 2: `tests/test_browser_contract.py` keyboard/queue/flag contracts; manual pass in the browser | FFL-HQ-006 | Measure corrections-per-session in the first real review sessions; consider per-page triage mode if still slow. |
| FFL-FILL-015 | P1 | Implemented | `src/pdf_field_lab/server.py`, `browser/app.js`, `tests/test_server.py` | Export ignored the `required`/`conditional_on` fields the manifest already carried, and the values behind an export existed only in the receipt hash. Now: export refuses (422, named labels) any required target whose value is empty unless its conditional_on reference is unfilled or holds a different value (grammar `<target_id>=<expected>`; opaque conditions stay enforced); requiredness is reviewer-declared via an inspector chip (persisted as a governed manifest change); and each export persists a values JSON served identity-bound via `GET /api/sessions/{id}/values`. | Product owner | With no required flags, export behavior is unchanged; with flags, empty values block export with named labels; conditional targets are skipped exactly when their condition is inactive; values JSON matches its receipt hash. | Tier 3: `tests/test_server.py` validation/conditional/values tests; browser contract for chips and values link | FFL-REV-004 | Decide whether to author the Form-6 requiredness map in the profile (ECI domain judgment) or keep requiredness reviewer-declared (FFL-D-requiredness-map). |
| FFL-SESS-016 | P1 | Implemented | `src/pdf_field_lab/server.py`, `tests/test_server.py` | Sessions lived only in temp with a 1-hour TTL, so a review session outliving the hour silently destroyed human work, and re-uploading the same document forked a duplicate. Now: sessions holding review candidates survive the ordinary TTL up to a review TTL (7 days default, `PDF_FIELD_LAB_REVIEW_SESSION_TTL_SECONDS`); every session records its source hash and filename; re-uploading the same bytes resumes the most recent matching session (highest revision, live or restored from disk across process restarts) with `resumed: true`, and `?fresh=true` forces a new session. | Product owner | Review work is never destroyed by the ordinary TTL; same-bytes re-upload returns the prior review state; deliberate restart is explicit; expired review sessions are still cleaned at the long cap. | Tier 3: `tests/test_server.py` resume/fresh/TTL-survival tests (including review-work survival beyond the ordinary TTL) | FFL-HQ-006 | If multi-sitting review becomes common, revisit durable storage (FFL-D-session-durability) with that data. |

## Explicitly retained open: multilingual capability

The following items are intentionally still open. Existing Unicode-preserving
normalization and English-language tests do not close them, and no current
detector, model, browser, or export milestone should be interpreted as closing
this scope:

- language-aware OCR and multilingual label detection
- multilingual NER and field association
- document-level and per-field language and script controls
- explicit translation and transliteration previews
- audit logging for every language transformation
- embedded-font selection and glyph-coverage verification
- unsupported-script handling and honest export blocking or fallback
- mixed-script answers and character-grid rendering
- multilingual, document-disjoint gold data and benchmarks

Closure requires explicit per-language and per-script evidence, visual output
checks, transformation audit receipts, and family-isolated benchmark results.

## Closed in the current local milestone

| Item | Evidence | Boundary |
|---|---|---|
| Python project environment | `uv.lock`; deps-enabled verification runs in disposable throwaway venvs (FFL-D-venv option A, 2026-10-09) and CI | Local dependency health only; no standing project `.venv` exists in the checkout |
| Native PDF inspection | `inspect_pdf`, structural tests | Does not infer painted fields |
| Vector and text semantic lane | Calibration and controlled gold receipts | Conservative heuristic, not universal recall |
| Raster CV and OCR proposal lane | Image-only calibration and controlled gold receipts | Every inferred target remains review-required |
| Typed target ontology | `FieldSpec.kind`, component mapping, evidence, confidence, review state | Ontology still needs more real-world classes |
| Photo and signature targets | Visual overlay strategies, browser components, fill adapter | Not cryptographic or legal signing |
| One-string character-grid fill | `input_mode=character-grid`, ordered `grid_rows`, fill tests, and Form-6 visual correction | Composite groups still need explicit subfield semantics; arbitrary grid layouts need more gold coverage |
| Inline browser acceptance | Draft value over page plus checkmark commit | Browser proof is local runtime evidence |
| Zero-target abstention state | Empty field-map state says `No editable targets found`, keeps progress at 0%, and offers manual draw recovery | Does not prove the PDF has no editable intent |
| Unified choice taxonomy | Checkbox and radio behavior share visible `Choice` family with `multi-select` or `single-select` subtype | Export strategies remain distinct underneath |
| Named composite groups | Composite field list uses semantic group names such as Address, Constituency, Identity, and Date + place | Naming is deterministic label inference, not universal semantic understanding |
| Review manifest mutation | Move, resize, reject, manual add, persist routes and tests; export now rebuilds from the immutable source plus the accepted manifest revision | Needs broader workflow/browser regression coverage and native-field merge coverage |
| Inferred candidate authority | Generic visual candidates remain pending until an explicit human acceptance event; confidence no longer creates acceptance | Native widgets and reviewed profiles have separate authority rules |
| System PDF inventory | 22,426 inventoried in the current all-system snapshot; complete `pdf_editor` family pass covers 234 PDFs with measured and visually corrected receipts | Inventory and detector execution are not field-level gold; 15 family files were unreadable and 16 analysis records errored |
| Controlled gold set | 3 families, 9 representations, 18/18 vector and image-only positives with precision 1.0 | Authored fixtures are not real-world generalization proof |
| Dataset separation | FUNSD test excluded, document-family grouping, proxy labels tagged | Proxy labels remain unsuitable for authority promotion |
| Typed proxy-model baseline | FUNSD and DocLayNet geometry normalized, ontology anchors added, Form-6 variants grouped for holdout | Advisory model holdout remains weak and cannot override review |
| Typed benchmark evaluator | Precision, label similarity, cross-type duplicate detection, and textarea/native checks | Controlled fixtures still need independent real-world adjudication |
| Real-PDF visual audit loop | Form-6 source pages were rendered independently, overlaid with canonical targets, and audited in the browser; omissions were recorded and corrected | Current audit found defects, so visual completeness is still open |
| Financial-statement hard negative | Medpiper current run emits 0 logical targets and 236 vector diagnostics | Precision probe, not recall proof |
| Label repository and training gate | 13 records, 9 controlled proxy records, 4 pending records, sanitized Form-6 and Medpiper manifests, a receipt-bound fail-closed loader, and a default zero-record trainable view | Labels are governed locally; no real record is training-eligible until human review, training approval, and controlled provenance are recorded |

## Detection and data quality gates still open

| Priority | Open item | Closure evidence required |
|---|---|---|
| P0 | Human-review the governed corpus | Review receipt moves from 0/38 confirmed to a documented field-level manifest with reviewer, date, and disagreements |
| P0 | Verify the seeded real-document label queue | Review Form-6 and Medpiper renders, correct target boxes, types, groups, and signature occupancy, record reviewer and disagreements, then promote only approved revisions to `verified` |
| P0 | Build a real-world document-disjoint gold set | At least 5 to 10 independent families with boxes, label spans, type, grouping, abstention, and source lineage |
| P0 | Expand scanned-form gold data | Real scans at multiple resolutions, noise levels, rotations, contrast levels, and OCR failure cases |
| P0 | Raster recall on real scanned forms | The bounded 20-file raster slice executed CV/OCR but found only 2 raster targets, both on the synthetic handwritten fixture; build reviewed real-scan positives and explicit no-affordance negatives |
| P0 | Related scanned-form generalization | `Form6_preview.pdf` visually contains address, grids, photo, disability, and signature regions while generic CV/OCR recovered only 4 review-required targets; add region/layout reasoning and reviewed page-level labels |
| P1 | Composite and grouped semantics | Explicit logical subfields for address, dates, Aadhaar-like IDs, declarations, acknowledgements, repeated groups, and multi-line names |
| P1 | Native widget semantics | Choice groups, radio behavior, export naming, XFA coexistence, rotation, and multi-page widget grouping |
| P1 | Dense-layout precision | Tables, statements, invoices, charts, footers, and multi-column prose with reviewed hard negatives and risk-coverage reporting |
| P1 | Orientation and layout invariance | Rotated, multi-page, multi-column, mixed text/raster, and unusual page-size manifests |
| P1 | Mixed-representation page routing | Page-level native/vector/raster/OCR routing, overlap precedence, lane failure isolation, and real mixed-page gold cases |
| P1 | Full-corpus resource budgets | Add time/page/byte budgets around PDF parsing so pathological PDFs produce resumable, explicit skips without monopolizing the run |
| P1 | Language-aware detection and handwriting behavior | Multilingual labels, scripts, language-routed OCR, genuine handwriting cases where permitted, and explicit abstention labels |
| P1 | Explicit multilingual input contract | Per-document and per-field language/script metadata, mixed-script answers, explicit translate/transliterate actions, reversible previews, and audit records |
| P1 | Model promotion decision | A group-disjoint, field-level benchmark must beat deterministic baselines on recall, type accuracy, label association, false positives, and abstention risk before the model can affect authority |
| P2 | Training-data governance | Record licenses, provenance, redaction, family lineage, and retention for every adopted dataset or generated derivative |

## Export, browser, and product hardening still open

| Priority | Open item | Closure evidence required |
|---|---|---|
| P0 | PDF viewer compatibility | Fresh output checks in Acrobat, Preview, browser viewers, and relevant PDF/A validators, with screenshots and reopen receipts. 2026-10-15: the automated floor is done (`tests/test_export_compat.py`: strict pypdf parse, PyMuPDF reopen/render, qpdf check) and the Tier 4/5 human pass has a runbook (`docs/runbooks/viewer-verification.md`); the human Acrobat/Preview pass itself is still owed before any release-facing claim. |
| P0 | Visual asset export fidelity | Photo crop/fit/rotation, signature draw/type/upload, transparency, page rotation, clipping, and print-scale visual comparisons |
| P1 | Script-aware PDF output | Embedded fonts with verified glyph coverage, licensing and fallback policy, character-grid placement, unsupported-script errors, and Acrobat/Preview/browser checks |
| P1 | Browser end-to-end regression | Automated upload, map, type filter, inline edit, checkmark, photo drop, signature mode, manual target, and export flow against a disposable local server |
| P1 | Accessibility and responsive behavior | Keyboard navigation, accessible names, focus order, zoom, narrow viewport, error states, and screen-reader review |
| P1 | Deferred macOS port to `pdf_editor` | Port only after the reference pipeline passes the locked unseen-family, review-to-export, native-preservation, visual, multilingual, viewer, and security gates; then prove native/browser parity without copying a second source of truth |
| P1 | Large-document performance | Bounded raster work, cancellation, progress, memory profile, multi-page sampling policy, and repeated-session behavior |
| P1 | Error recovery | Malformed, truncated, encrypted, password-protected, signed, and unsupported PDFs receive explicit quarantine/error states without partial false success |
| P2 | Field editing quality | Better date, choice, address, repeated-group, and one-string split editors with validation and clear acceptance state |

## Security, privacy, and operational gates still open

| Priority | Open item | Closure evidence required |
|---|---|---|
| P0 | Upload policy | Explicit size, page, timeout, content-type, decompression, and resource limits |
| P0 | Malware and active-content handling | Safe scanning/quarantine policy for JavaScript, embedded files, malformed streams, and hostile PDFs |
| P0 | Storage and isolation | Durable-storage decision, tenant/session isolation, permissions, encryption, deletion, and restart behavior |
| P1 | Session lifecycle | Expiry, cleanup, retry/idempotency, crash recovery, and operator-visible audit trail |
| P1 | Sensitive logging | No source bytes, extracted personal values, photos, or signatures in logs, traces, benchmark outputs, or model payloads |
| P1 | Production boundary | Authentication, rate limiting, concurrency limits, deployment topology, backups, monitoring, and incident recovery |
| P2 | Provider experiments | Modal credentials must be supplied through an authenticated operator action; no provider job is currently submitted or required for the deterministic path |

### 2026-09-30 configuration hardening note

The existing `FFL-SEC-010` upload-limit claim now also covers validation of
`PDF_FIELD_LAB_MAX_UPLOAD_BYTES`, `PDF_FIELD_LAB_MAX_PAGES`,
`PDF_FIELD_LAB_MAX_TARGETS`, and `PDF_FIELD_LAB_SESSION_TTL_SECONDS` as positive
integers. Invalid values fail clearly at startup instead of silently disabling
a bound or causing immediate session expiry. The scanner, active-content,
quarantine, multi-worker storage, and production lifecycle questions remain
open; this note does not close the security item. The source-level baseline
reproduction confirmed `PDF_FIELD_LAB_MAX_PAGES=0` was accepted before the
change. `python3 -m pytest -q tests/test_config.py` passes six focused tests
(T2/S2: the baseline source assignment accepted zero, while the regression
checks now reject it). A stdlib-only direct
check independently exercised all parser branches.

### 2026-10-09 integration verification note (FFL-D-venv resolved, option A)

The pending-environment question was resolved by decision FFL-D-venv option A:
a throwaway venv was created outside the repo (`/tmp/ffl-cfg001-venv`,
Python 3.14.7) with all core dependencies plus the `cv`, `ocr`, and `training`
extras and the `dev` toolchain, leaving the repo checkout untouched. The full
suite ran green: 77 passed, 0 failed, including all six
`tests/test_server.py` integration tests and the config regression tests; the
coverage ratchet held at 84.16% (floor 80%). The venv is disposable and is not
committed; CI remains the durable Tier 3 evidence path (FFL-CI-014, billing
blocked).

### 2026-10-14 governance-spine milestone note

Implemented from first principles in one pass, each with tests (full suite
98 passed, coverage 85.50% vs 80 floor, disposable venv):

- **FFL-HQ-006 (P0):** review events carry reviewer, batch timestamp,
  resulting `manifest_sha256`, and a disagreement signal; every manifest
  mutation writes a hash-bound review receipt (integrity chain, not a
  cryptographic signature — signing is a registered decision). New
  `/review-receipts.jsonl` export route.
- **FFL-SEC-010 quarantine half (P0):** active-content quarantine
  (JavaScript, open actions, embedded files, XFA — detection only,
  fail-closed), explicit encrypted-upload rejection, shared rejection audit
  ledger, audited TTL sweeps at startup/health/create, explicit
  vanished-storage 404. Policy documented in
  `docs/security-quarantine-policy.md`.
- **FFL-EVL-005 (P1):** evaluator v2 with stable order-invariant assignment,
  wrong-label failure class, and miss diagnostics; calibration regenerated
  with unchanged quality.
- **FFL-GOV-001:** review-receipt contract enforced in the fail-closed gate
  (`receipt_sha256` + reviewer match); sanitized synthetic verified fixture
  proven consumable in default mode with validation/locked-test exclusion.
- **Register drift corrections (per-milestone ritual):** FLY-011 "no UI by
  design" (browser review actions exist), REL-013 "tag pending" (annotated
  tag v0.1.1 exists at `3c1c67e`), stale ".venv closed" environment line.

What remains open is unchanged in kind: real review sessions (owner action),
the real-world gold set, CI billing, and the production security boundary.

## Evidence status and ownership

The current claims are local-only and are separated by evidence tier:

- Tier 1: static source and manifest inspection
- Tier 2: deterministic tests, receipts, and PDF reopen checks
- Tier 3: local API integration
- Tier 4: local browser/runtime and visual review
- Tier 5: production-like, external viewer, provider, or deployed evidence

The current gold-set claims are Tier 2 plus Tier 4 visual evidence, sensitivity
S1. They are not Tier 5. The user-owned PDFs under Desktop and Documents were
used as read-only probes; their bytes were not copied into project training or
gold artifacts. The dirty sibling `pdf_editor` checkout remains outside this
project's ownership boundary.
