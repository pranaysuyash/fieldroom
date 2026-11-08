# Static-XFA fixture design (IDEA-149 / FFL-D-xfa-policy)

- Author: Claude nightly orchestrator, run 2026-10-24 01:33 IST. Research only; no code changed.
- Evidence tier: S0. This comes from domain knowledge (PDF 1.7 / ISO 32000-1 §12.7.8 and the XFA 3.3 spec as recalled). No web fetch or local run was made this run, so treat every claim below as **inferred until verified** by the acceptance checks.
- Feeds: `Docs/DECISIONS_PENDING.md` FFL-D-xfa-policy, and the method in `2026-10-14-governance-spine-research.md:99`.

## Distinguishing static from dynamic XFA (detector rule candidates)
1. `/AcroForm /XFA` present → XFA form (the current quarantine trigger).
2. `/Root /NeedsRendering true` → dynamic. The viewer must lay out pages from the XFA template, so there are no trustworthy widgets. Keep it quarantined.
3. Static forms usually ship a full AcroForm widget tree (`/Fields` non-empty, widgets carry `/Rect` + `/AP`) mirroring the XFA template. If `NeedsRendering` is absent or false and the widgets exist → static candidate.
4. Secondary signal: the XDP `config` packet `<dynamicRender>` (`required` = dynamic). The `template` may also contain `<subform layout="tb">` flowing layout. Treat any of these as dynamic (fail-closed).

## Candidate export strategy for static XFA
- Clone-export through the existing AcroForm path, then **drop `/XFA` from the cloned AcroForm** so viewers fall back to AcroForm. This is the usual "flatten to AcroForm" approach. Acrobat otherwise prefers XFA data and can disagree with edited widgets.
- Preserve the original bytes untouched (project rule: source PDFs preserved). Record the XFA removal in the export receipt.

## Fixture to author (next implementation step)
- A small 1-page PDF: 2 text fields + 1 checkbox as AcroForm widgets, with a matching minimal XDP (`template`, `datasets`, `config` without `dynamicRender`), and no `NeedsRendering`.
- A sibling negative: the same content with `NeedsRendering true` and `dynamicRender=required`.
- Generate it with a deterministic script (pattern: `scripts/build_calibration_fixture.py`) so it reproduces offline.

## Acceptance checks (to turn this from inferred to verified)
- The detector classifies the positive as static and the negative as dynamic. The negative stays quarantined.
- After export, reopen with pypdf and the project's inspector: the field tree is intact, and `/XFA` is absent from the clone only.
- Visual reopen in Chrome (pdf.js), macOS Preview, and Acrobat Reader if available. Fields render and the values persist. This is the viewer-fidelity gate named in the decision.

## Risks
- Hybrid producers (LiveCycle "static" saved with dynamic config) → rule 4 must win (fail-closed).
- Data drift: XFA `datasets` values may differ from the AcroForm `/V` values. The exporter should prefer the AcroForm values and log any mismatch.
