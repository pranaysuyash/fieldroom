# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
milestone-based semver.

## [Unreleased]

### Added

- Governed review sessions (FFL-HQ-006): review events carry reviewer,
  timestamp, manifest hash, and disagreement signal; every manifest mutation
  writes a hash-bound review receipt exported via
  `GET /api/sessions/{id}/review-receipts.jsonl`.
- Upload quarantine (FFL-SEC-010): active-content detection (JavaScript,
  open actions, embedded files, XFA), explicit encrypted-PDF rejection, and
  a shared rejection audit ledger; policy in
  `docs/security-quarantine-policy.md`.
- Evaluator v2 (FFL-EVL-005): stable order-invariant matching,
  wrong-label failure class, and miss diagnostics.
- Enforced review-receipt contract in the training gate (FFL-GOV-001).
- Automated sanitized public mirror to
  [fieldroom](https://github.com/pranaysuyash/fieldroom) with a fail-closed
  export gate (`tools/export_public.py`).
- Review-session runbook (`docs/runbooks/review-session.md`).
- Reviewer keyboard triage (FFL-REV-014): j jumps to the next unreviewed
  target, a accepts and continues, x rejects/restores, ? shows shortcuts;
  queue can be sorted worst-confidence-first.
- Required-field governance (FFL-FILL-015): reviewers can mark targets
  required; export refuses empty required values by name, respecting
  `conditional_on` conditions; each export also persists a values JSON
  served identity-bound via `GET /api/sessions/{id}/values`.
- Resumable review sessions (FFL-SESS-016): re-uploading the same document
  resumes the previous review state; sessions holding review candidates
  survive the ordinary TTL up to a 7-day review TTL.
- Viewer-compatibility receipts: automated reopen checks (strict pypdf,
  PyMuPDF render, qpdf) plus a human viewer-pass runbook
  (`docs/runbooks/viewer-verification.md`).

### Changed

- **RANK-007 park decision:** the advisory target model is parked;
  `PDF_FIELD_LAB_ADVISORY_MODEL` now defaults to `off` (opt-in `=on`).
- CI installs the `training` extras so the model lane is tested.

## [0.1.1] - 2026-09-17

### Added

- Review-candidate flywheel (`FFL-FLY-011`): manifest revisions now emit
  governed label candidates (`GET /api/sessions/{id}/review-candidates.jsonl`)
  and `scripts/build_label_repository.py --review-candidates` ingests them as
  pending records; ingested records survive plain rebuilds.
- In-repo detector calibration fixture (`FFL-REPRO-012`):
  `scripts/build_calibration_fixture.py` + evaluator receipt under
  `artifacts/calibration/`; 4/4 positives, precision 1.0, 0/5 hard negatives.
- Upload-limit regression tests for bytes, page-count, and target-count 413
  and 422 paths (`server.py`).
- Operator switch `PDF_FIELD_LAB_ADVISORY_MODEL=off` (`FFL-RANK-007`).
- CI depth: ruff gate, pytest-cov with an 80% ratchet, pip-audit (non-blocking
  ratchet), CV/OCR lanes exercised, Dependabot for pip and actions.

### Changed

- Privacy remediation: signer identities in docs replaced by roles; label
  locators are repo-relative or `local-redacted` pseudonyms; real-document
  test inputs live in the untracked `tests/local/` fixture.

### Fixed

- CI collected no tests: `httpx` was missing from the `dev` extra.

## [0.1.0] - 2026-09-10

- Initial public snapshot: staged detection pipeline (native, vector,
  raster/CV, OCR), Form-6 reviewed profile, browser review surface,
  revision-bound exports, controlled gold set (18/18, precision 1.0,
  0/6 hard negatives), governed label repository, and the system-corpus
  inventory tooling.
