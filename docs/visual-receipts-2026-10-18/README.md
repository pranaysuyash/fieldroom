# Viewer receipts: exported Form-6 (2026-10-18)

Tier 4 receipts for the viewer-compatibility register item, produced via the
runbook in `docs/runbooks/viewer-verification.md`.

## What was exported

- `exported-r1.pdf`: Form-6 export at manifest revision 1 (all targets
  accepted; F6-05 = "VIEWER CHECK" in the character grid; required
  relative-fields filled from the FFL-D-requiredness-map draft).
- `export-receipt.json`: the export receipt (source hash, manifest revision
  and hash, values hash, output hash).
- `preview-window.png`: macOS Preview window capture of the export.

## Automated floor results (same build)

- Strict pypdf parse: pass (2 pages, no exceptions).
- PyMuPDF reopen and render: pass.
- qpdf structural check: pass (CI run 38788071091 includes it).
- Note: pypdf text extraction does not find "VIEWER CHECK" as a contiguous
  string because the character-grid fill places one glyph per printed box;
  the visual receipt below is the meaningful check for grid fills.

## Preview (macOS) observations

- Opens cleanly, no repair prompt; 2 pages; thumbnails render.
- "VIEWER CHECK" renders one letter per printed box in field 1(a), matching
  the character-grid fill design.
- Required relative-name field shows its value on the correct line.
- **Observation for the human pass:** in the captured window, the relative-
  type radio options all appear marked, though only "father" was answered.
  Verify at full resolution whether the radio-state export marks every
  option (would be an export fidelity defect and a new register item) or
  whether this is a Preview rendering artifact at this zoom level.

## Still owed

Acrobat Reader pass and a browser-viewer pass, plus the print-preview check,
by a human with those applications (runbook section 2).
