
## FFL-D-venv (opened 2026-10-01 03:10 IST, nightly orchestrator) — RESOLVED 2026-10-09
- **Context:** Codex FFL-CFG-001 (positive-int config parsing) passes its 6 focused tests. The full `tests/test_server.py` can't run because FastAPI isn't installed, there is no project venv, and the offline uv cache has no fastapi.
- **Options:** A. Allow a network install of the pyproject deps into a throwaway venv outside the repo, then run the server suite. B. The owner creates the project `.venv` via `uv sync`. C. Defer to CI.
- **Recommendation:** A. The deps are small and it leaves the repo untouched.
- **Blocked:** Full-server verification of FFL-CFG-001.
- **Resolution (2026-10-09):** Option A executed. Throwaway venv at `/tmp/ffl-cfg001-venv` (Python 3.14.7, deps installed from network); full suite green — 77 passed including all server integration tests, coverage 84.16% vs 80% floor. Repo checkout untouched; no `.venv` created. CFG-001's remaining gate is the first green CI run (FFL-CI-014), not local verification.

## FFL-D-license (opened 2026-10-14)
- **Context:** FFL-REL-013 is the only release-hygiene item left besides per-milestone tagging; the repo has no LICENSE file.
- **Options:** A. MIT — shortest, maximally permissive, standard for research/prototype repos. B. Apache-2.0 — adds explicit patent grant and NOTICE mechanics; heavier for a governance-showcase repo.
- **Recommendation:** A (MIT). The repo's pitch is the governance methodology, not a product; nothing here needs patent defense posture, and SpotDraft reviewers can read MIT in five seconds.
- **Blocked:** LICENSE file creation + pyproject license field (FFL-REL-013 closure).

## FFL-D-rank007-park — RESOLVED 2026-10-14 (option A executed)
- **Context:** FFL-RANK-007 holdout is near-noise (0.378 acc / 0.25 macro-F1). The register allows a default flip only on demonstrated flywheel uplift or explicit park. Supply is the bottleneck: ~1 real local document makes flywheel volume likely unreachable (council finding).
- **Options:** A. Declare parked now — keep the mechanism, flip `PDF_FIELD_LAB_ADVISORY_MODEL` default to `off` so operators don't run a near-noise model by default. B. Keep default-on until flywheel data exists. C. Fund the model (contradicted by supply analysis).
- **Recommendation:** A. Parked ≠ deleted: the flag, training path, and benchmark contract all stay; only the default demotes. Revisit if review sessions ever produce ≥20 verified corrections in a family.
- **Resolution (2026-10-14):** Option A executed with owner approval ("do all"). Default flipped to off in `src/pdf_field_lab/analysis.py`; register row moved to Parked; un-park condition recorded (≥20 verified document-disjoint corrections + demonstrated uplift).

## FFL-D-history-remediation (opened 2026-10-03, re-registered 2026-10-14)
- **Context:** personal-data blobs sit in git history (private repo today; pushed 2026-09-17). Sanitization of tracked files is done; history is not.
- **Options:** A. Leave while private; purge (git filter-repo + force push) before any sharing. B. Purge now. C. Squash-restart history.
- **Recommendation:** A, and C is forbidden — early commit dates (Sep-10) evidence that the project predates the SpotDraft role. Purge is a sharing-time gate.
- **Blocked:** nothing today; blocks any public sharing.

## FFL-D-ci-billing (owner action, opened 2026-10-14)
- **Context:** FFL-CI-014 code is complete; GitHub Actions billing failure blocks the first green run. Local verification (77→98 passing) is Tier 2; CI is the durable Tier 3 path.
- **Action:** fix billing in GitHub Settings → Billing, then trigger a run. No code dependency.

## FFL-D-review-sessions (owner action, opened 2026-10-14)
- **Context:** the entire P0 evidence spine (FLY-011 volume → GOV-001 real receipt → RANK-007 final call) needs Pranay to run real review sessions as the named reviewer. The mechanism is now fully in place: set `PDF_FIELD_LAB_REVIEWER=<name>`, run `pdf-field-lab`, review Form-6 (`data/samples/RAr0Lq2Avu.pdf`) in the browser, export receipts + candidates.
- **Action:** schedule the sessions (Form-6 first, then Medpiper after locator re-link via `PDF_FIELD_LAB_MEDPIPER_PDF`).

## FFL-D-session-durability (opened 2026-10-14)
- **Context:** sessions are ephemeral (temp dir, audited TTL sweeps). Durable storage only matters if review sessions outlive one sitting.
- **Recommendation:** keep ephemeral until real review sessions show interruption; decide with data (exploration 2026-10-14, SEC follow-up; IDEA-148).
- **Blocked:** nothing; revisit after first real sessions.

## FFL-D-xfa-policy (opened 2026-10-14)
- **Context:** XFA uploads are quarantined fail-closed. Static-XFA support may be safe; dynamic XFA cannot be safely edited.
- **Recommendation:** keep blanket quarantine until a static-XFA fixture proves clone-export reopen fidelity in mainstream viewers (IDEA-149).
- **Blocked:** fixture authoring (research, unblocked).

## FFL-D-receipt-signing (opened 2026-10-14)
- **Context:** review receipts are hash-bound (integrity chain) but not cryptographically signed; signing needs operator key management that a single-operator local tool may not justify.
- **Recommendation:** defer until the first multi-reviewer or pre-sharing milestone (IDEA-150).
- **Blocked:** nothing; a deliberate deferral.
