# Viewer-verification runbook (export compatibility)

Date: 2026-10-15. Companion to `tests/test_export_compat.py`, which runs the
automated floor on every test pass: strict pypdf parse, PyMuPDF reopen and
render, and qpdf structural validation when the binary is present. Those are
Tier 2/3 receipts. This runbook is the Tier 4/5 human pass for release-facing
milestones; do it once per export-machinery change, not per commit.

## 1. Produce the receipt set

```bash
export PDF_FIELD_LAB_REVIEWER=pranay
uvicorn pdf_field_lab.server:app --port 8787
```

Upload `data/samples/RAr0Lq2Avu.pdf`, accept the targets, fill at least one
text field, export, and keep both downloads (PDF + values JSON). Note the
revision and hashes from the export receipt response.

## 2. Reopen matrix

For each viewer, record: opens without repair prompt; page count 2; the
filled value is visible on the correct field; print preview renders.

- Acrobat Reader (or full Acrobat if available)
- macOS Preview
- Safari and Chrome built-in viewers
- One PDF/A validator pass (veraPDF if installed) as information only

## 3. Record the receipts

Create `docs/visual-audit-<date>-export-viewers.md` with per-viewer
pass/fail, the export revision and hashes, and screenshots of any defect.
Defects become register items; do not fix silently inside this runbook pass.

## 4. Scope

This runbook covers reopen fidelity of exports. Visual export fidelity for
photo/signature placement and print scale is a separate register item and
needs the overlay comparison loop from `docs/visual-audit-2026-09-10.md`.
