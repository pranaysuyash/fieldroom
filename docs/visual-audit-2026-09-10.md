# Visual audit: real user PDFs

Date: 2026-09-10

## Purpose

This audit checks whether the targets shown in the browser cover the actual
editable regions in the supplied PDFs. A semantic label count is not treated
as proof of visual completeness. The audit compares the source page render,
the canonical target manifest, and the live browser overlay.

## Evidence boundary

- Source PDFs were inspected locally and were not uploaded to an external
  service.
- Form-6 was inspected at 160 DPI for both pages and in the local browser at
  `127.0.0.1:8791`.
- The red-box comparison renders in `/tmp/pdf-field-audit.zfLM3E/` are
  disposable inspection artifacts and are not source-of-truth project data.
- The current audit is a Tier 4 local visual observation supported by Tier 1
  geometry inspection. It is not production or cross-viewer proof.

## Form-6 findings

The current profile has 33 logical targets. The semantic grouping is mostly
reasonable, but the visual comparison found these gaps or precision defects:

1. The official-language given-name region contains two printed rows of
   character cells. The current `F6-05` overlay covers only the lower row.
2. The English given-name region has the same two-row geometry. The current
   `F6-07` overlay covers only the lower row.
3. The mobile-number grid is a two-row, ten-cell-per-row layout. The original
   `F6-12` target treated it as one undifferentiated rectangle and could not
   export the string row by row.
4. The Aadhaar digit strip was absent from the original composite target;
   only the Aadhaar/no-Aadhaar boxes were represented.
5. The disability percentage input was absent from the original composite;
   only the certificate choices were represented.
6. The received-applicant-name region began over printed label text instead
   of beginning at the writable line.
7. The applicant-signature target included the printed signature label. It was
   narrowed to the PDF border-defined blank signing band above the label.
8. Several composite regions are semantically useful but visually broad. The
   browser now presents one grouped editor while retaining exact child
   regions for each number box, checkbox, line, or address cell.
9. The user-facing taxonomy is inconsistent: summary counts call radio
   groups `Choice`, while field-list labels call them `Radio`; composite
   groups appear as `Other`. This makes it harder to know what is being
   filled.

The visual audit therefore does **not** support a claim that all Form-6
fields are currently identified and editable.

## Confirmed coverage

The current profile does visibly cover the following major groups:

- office form number;
- both constituency number/name rows;
- photograph placement area;
- surname rows;
- relative type choices and relative name rows;
- mobile two-row grid and email regions;
- Aadhaar choices and number;
- gender choices;
- date of birth and age-proof choices;
- ordinary-residence address table;
- residence-proof choices and alternative document line;
- disability choices, description, percentage, and certificate choice;
- family-member name, relationship, and EPIC lines;
- declaration place, residence-since, enclosed document, date, and place;
- applicant signature area;
- acknowledgement number/date, received name, and office signature area.

Coverage of a major group does not imply exact child-region coverage.

## Medpiper findings

The Medpiper PDF is a 20-page signed financial statement with no native
AcroForm fields and no reviewed form profile. The live viewer shows the actual
pages and existing signatures, but currently promotes zero editable targets.
That abstention is not evidence that every visual mark was detected. It means
the current generic semantic lane has no sufficiently strong empty-field
contract. Existing signatures must be treated separately from empty signature
placeholders so that the editor does not accidentally invite replacement of
already-signed content.

The separate signature-observation lane now inspects the repeated signing block
when printed signer names and roles form a coherent group. On the supplied
Medpiper document it reports 12 expected signer slots across pages 1, 2, 3, and
20:

- 9 slots are present, backed by embedded signature-image intersections.
- 3 slots are missing, all for the Partner signatory on pages 2, 3, and 20.
- The two Director signatory slots are present on all four
  inspected pages.
- Page 18 produces no signature observations. Its director names occur inside
  a related-party table, not inside a signing block, so the block-level guard
  correctly avoids a false positive.

The page-20 visual check is therefore now explicit: the Partner signatory’s expected
signature area is outlined as `missing`, while the two director areas are
outlined as `present`. These observations remain review-only and are not
included in the editable target manifest.

Each observation is also written to the temporary session’s `analysis.json`
snapshot. The corresponding `audit_log` entry includes the observation ID,
page, signer, role, status, confidence, source SHA-256, and detector version
(`signature-observation.v1`). This provides a reproducible local audit record
for the current session TTL. It is not yet a durable, access-controlled,
multi-user compliance log.

The product should expose this distinction explicitly as:

- editable targets;
- review-only geometric candidates;
- existing visual ink/signatures;
- ordinary document content;
- manual targets added by the reviewer.

## Correction plan

1. Model multi-row character grids as one user-facing field with ordered child
   cell rows and a dedicated export mapping.
2. Corrected the mobile and received-name child geometry; keep these as
   source-specific regression fixtures.
3. Implemented in the current browser contract: use one visible `Choice`
   taxonomy with `single-select` and `multi-select` subtypes.
4. Implemented in the current browser contract: replace `Other` with
   meaningful composite group names in the field list.
5. Represent zero logical targets as an abstention state rather than `100%
   reviewed`, and expose the existing manual-add path from the empty field map.
6. Add a visual regression check that fails when a known writable region is
   outside its target or when a target overlaps a printed label beyond the
   allowed tolerance. The current test suite asserts the corrected known
   coordinates, but does not yet perform pixel-level overlap scoring.
7. Keep Medpiper in the benchmark as a non-form, signed-document negative
   case while adding a separate existing-ink inspection lane.

## Review status

Open. The current result is useful evidence, but it is not a complete
Form-6 field inventory and should not be described as perfect detection.
