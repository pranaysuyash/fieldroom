# Fieldroom detection learning ledger

Date opened: 2026-09-10

This is the durable learning record for the generalized PDF field-reconstruction
work. It captures what was observed, what was inferred, what was implemented,
what remains unknown, and how a future model or macOS port must be evaluated.
It is evidence-linked, not a claim that arbitrary-PDF detection is solved.

## Doctrine alignment

This ledger follows the project instruction stack and the canonical doctrine
family. The active sources are:

- `~/AGENTS.md`
- `~/Projects/AGENTS.md`
- `~/Projects/pdf_form_field_lab/AGENTS.md`
- `~/Projects/pdf_form_field_lab/OPERATING_DOCTRINE.md`
- `~/Projects/agent-start (local control plane)/doctrines/EXPLORATION_DOCTRINE.md`
- `~/Projects/agent-start (local control plane)/doctrines/RESEARCH_DOCTRINE.md`
- `~/Projects/agent-start (local control plane)/doctrines/ARCHITECTURE_DOCTRINE.md`
- `~/Projects/agent-start (local control plane)/doctrines/TESTING_DOCTRINE.md`
- `~/Projects/agent-start (local control plane)/doctrines/DOCUMENTATION_DOCTRINE.md`
- `~/Projects/pdf_form_field_lab/Docs/context/agent-start/AGENT_KICKOFF_PROMPT.txt`
- `~/Projects/pdf_form_field_lab/Docs/context/agent-start/SESSION_CONTEXT.md`

The canonical doctrine family lives in
`~/Projects/agent-start (local control plane)/doctrines/`. Generated context is a
compiled aid, not a second authority. This document is project knowledge and
does not replace the active doctrine files.

The method applied here is:

1. Establish the user outcome and the trust boundary.
2. Inspect current source, runtime, tests, fixtures, sibling references, and
   real local documents before proposing a new path.
3. Separate structural observation, semantic inference, visual review, model
   evidence, and export behavior.
4. Preserve useful parallel work and record ownership boundaries.
5. Implement one canonical path with explicit abstention and recovery states.
6. Verify with targeted tests, integration flows, visual inspection, and
   falsifiers proportional to risk.
7. Record uncertainty, evidence tier, sensitivity, open risks, and the next
   owner action.

## 2026-09-10 review checkpoint: independent findings that changed priority

An independent review pass in this session re-ordered priorities before further
ML work:

- Core closure must happen before model promotion: training eligibility and label
  ingestion integrity are preconditions for any ranking or autoresearch job.
- Idempotent governance is required for labels: `build_label_repository` must
  preserve verified records across rebuilds; otherwise human corrections are not
  stable and cannot be used as authority.
- Native preservation is a separate track from inferred overlays; native field
  identity, strategy labels, repeated widgets, and merge semantics need one
  contract before broader routing changes.
- Export/download revision binding is non-negotiable: stale revisions can silently
  serve mismatched outputs and weaken review trust.
- Evaluator quality matters as much as detector quality: wrong-label counterexamples
  and non-order-sensitive matching prevent overfitting to happy-path fixtures.
- The macOS port remains deferred intentionally until closed gates are met; this
  avoids creating a second mutable source of truth too early.

These points are now captured as explicit canonical IDs in
[`docs/open-items.md`](open-items.md), with statuses and dependencies.

## 2026-09-10 system-corpus expansion and visual-evidence correction

The full local discovery pass found `22,426` PDFs under `~`, with
`33` under the downloaded `pdf_editor/benchmark/datasets` path. A complete
`pdf_editor` family slice covered `234` files, including native widget fixtures,
OCR/image-only fixtures, generated benchmark outputs, and malformed-input
stress cases. This is discovery and execution evidence, not a field-level gold
set. The source files remain in place and are not training inputs by default.

The first visual contact sheets exposed a benchmark defect: the detector had
measured native targets, but the renderer received pre-analysis inventory
records, so captions and overlays showed `targets=0`. The fix routes measured
benchmark records to the renderer and adds a pixel-level regression that fails
if the target outline is absent. This is a reusable lesson: every evidence
renderer must consume the same canonical measured record as the report summary.

The `pdf_editor` receipt reports `2,095` logical targets, `1,284` native fields,
`1,208` vector diagnostics, `16` analysis errors, and `132` text-poor records
with raster intentionally deferred. A bounded raster-enabled slice executed
CV/OCR on `20` records and found `2` raster targets on the synthetic handwritten
completion sample. Visual inspection showed that several clean OCR fixtures are
plain narrative documents with no editable affordance, so zero targets there is
correct precision behavior. The remaining real-scan recall question is still
open and requires reviewed positive and negative examples, not more threshold
tuning.

The benchmark now supports explicit `--run-raster` execution and resumable
manifest slices. This keeps the expensive CV/OCR lane observable and bounded,
while preserving a fast all-system structural inventory. Relative manifest paths
are resolved beside the manifest and arrays/plain paths are accepted; a focused
regression failed before the path fix and passes afterward (S2).

## Decision and outcome

The product outcome is a browser-based workflow where a person uploads an
arbitrary PDF and receives a reviewable reconstruction of editable intent:

- text, multiline text, date, number, identifier, and address-like fields
- checkboxes and radio groups presented as one consistent Choice family
- grouped or composite inputs such as names, addresses, dates, and grids
- photo regions with drag, drop, upload, crop, and fit behavior
- signature regions with draw, type, and upload behavior
- existing signature ink and missing expected signature slots for audit review
- labels, confidence, source lane, geometry, review state, and abstention
- an accepted manifest that controls export and can be audited later

“Editable” has two meanings and they must not be confused:

1. Native PDF form fields are actual AcroForm or compatible interactive objects.
2. Reconstructed targets are app-managed overlays or newly exported widgets and
   assets positioned over an otherwise painted document.

Photo and signature targets can be first-class app components without being
native PDF fields. Signature ink found in an input document is evidence for
review and audit, not a cryptographic signature or legal-signing assertion.

## Core architecture learned from the work

The robust design is a staged, page-routed pipeline:

```text
source PDF
    |
    +--> native object inspection -------------------+
    |                                                |
    +--> text and vector geometry -------------------+--> page composition
    |                                                |
    +--> raster rendering, CV, and OCR --------------+
                                                     |
                                candidates with evidence and confidence
                                                     |
                         semantic typing and label/geometry association
                                                     |
                             deduplication and abstention decisions
                                                     |
                         pending review manifest and visual editor surface
                                                     |
                         accepted manifest revision plus audit receipt
                                                     |
             export from immutable source + accepted manifest, then reopen
```

The page is the correct routing unit. A document can contain native widgets on
one page, painted vector form surfaces on another, and image-only content on a
third. A document-wide detector choice loses useful evidence. Page-level
composition also lets one lane fail without erasing unrelated targets from
another lane.

The source PDF remains immutable. Analysis produces evidence. The browser or
review API promotes, moves, resizes, rejects, retypes, or adds targets. Export
rebuilds from the immutable source plus the accepted manifest revision. It must
not export from a stale render, an earlier session object, or detector output
that bypassed review.

## What each detection lane taught us

### Native PDF inspection

Native fields are the highest-authority source for fields that actually exist in
the PDF object graph. They provide names, widget geometry, field types, values,
and choice options that painted content cannot reliably recover.

Lessons:

- inspect field trees, widget annotations, inherited properties, repeated
  widgets, radio groups, dropdowns, multiline flags, rotation, and appearance
  streams
- do not assume a field has one widget or that a widget name is semantically
  useful
- preserve native fields when exporting instead of flattening them into a
  painted-only reconstruction
- test native choice groups, repeated widgets, and mixed native plus inferred
  pages independently
- native presence does not prove that every visible blank area is a field

### Text and vector geometry

Many forms are painted documents. Their editable intent is encoded indirectly in
text labels, rectangles, lines, whitespace, checkbox geometry, and repeated
character cells.

Lessons:

- geometry alone creates false positives in tables, financial statements,
  borders, rules, charts, footers, and decorative layouts
- a rectangle becomes a stronger candidate only when geometry, nearby label
  language, whitespace, layout role, and document context agree
- line-level underlines and colon-labelled whitespace need separate handling
  from rectangles
- wide shallow rectangles are common hard negatives in statements and tables
- geometry deduplication must be symmetric and cross-type, not only exact-ID
  based
- a candidate’s usable interior differs from its outer border; child grids and
  option boxes need their own coordinates
- text extraction can lose Unicode or truncate nearby labels if normalization
  and search windows are too narrow

The useful deterministic rule is not “find every box.” It is “promote only a
field-like surface with a field-like cue and a reliable spatial relationship;
retain the rest as reviewable diagnostics or abstain.”

### Computer vision and OCR

OpenCV helps recover visual structure such as contours, lines, rectangular
regions, image occupancy, and repeated grid geometry. OCR helps recover labels
when the PDF has no usable text layer. Neither is semantic truth by itself.

Lessons:

- CV is particularly useful for image-only forms, borderless whitespace,
  checkboxes, photo boxes, signature-slot occupancy, and grid structure
- contour counts are diagnostics, not field recall
- OCR confidence measures recognition confidence, not whether a rectangle is
  intended for user input
- render at controlled DPI and preserve page-coordinate normalization
- route OCR to text-poor pages instead of paying its cost or adding noise to
  text-rich pages unnecessarily
- every inferred CV/OCR target begins pending and carries its source lane,
  geometry, label evidence, and confidence
- scanned, rotated, noisy, low-contrast, multilingual, and handwriting cases
  require dedicated gold data rather than optimistic threshold changes

### Semantic NLP and label association

NLP is most valuable for typing and association after candidate generation. It
should not be asked to hallucinate geometry or overwrite observed structure.

Lessons:

- labels must be associated by spatial proximity, reading order, alignment,
  container membership, and wording, not nearest-text distance alone
- exact token boundaries matter: `Account no:` and `Phone no:` are text cues,
  not Choice cues; `Candidate name:` is not a date cue
- Unicode-preserving normalization is necessary for international labels
- labels must remain readable in the review surface; truncating context makes
  the user unsure which field they are filling
- a single user answer should be allowed to populate a structured group, then
  be split deterministically into child cells or subfields where the schema
  supports it
- composite targets need explicit group names and child semantics instead of a
  generic Other bucket
- the visible taxonomy must be consistent: Choice with a single-select or
  multi-select subtype is clearer than separate summary and inspector names
- NER can suggest entities such as person, organization, address, or date, but
  entity recognition is not equivalent to writable-field detection

### Signature and photo reasoning

A blank photo area is not a form field in the source PDF, but it is still an
important app target. The same applies to a signature line or expected signing
slot.

Lessons:

- photo and signature are product-level target classes with dedicated fill
  adapters, not text-field labels
- distinguish an expected empty slot from existing ink
- use source visuals, nearby role captions, repeated signing structures, image
  objects, and occupancy analysis together
- never infer a signer identity from a nearby name without a review decision
- preserve only geometry, occupancy, role, and redacted audit metadata in
  privacy-sensitive label records
- a present signature should be reviewable as source evidence; a missing one
  should be surfaced as an actionable audit finding
- output signature modes are draw, type, and upload, but the result is still
  content placed into the PDF, not a legal digital-signature claim

The Medpiper financial statement was the key hard-negative lesson. Generic
field detection correctly converged to zero editable targets while the separate
signature audit retained 12 expected slots, 9 present and 3 missing. That
separation prevents ordinary tables and prose from becoming input fields while
still supporting signature audit use cases.

## Review and authority lessons

The detector is a proposal engine. The review manifest is the authority layer.

Target state should be explicit:

```text
detected -> pending review -> accepted or corrected
                         \-> rejected or abstained
```

Native fields can have a separate authority rule because they are observed
interactive objects, but inferred photo, signature, text, and composite targets
must not become accepted merely because their confidence exceeds a threshold.

The review UI should show:

- the full associated label and page number
- target type and subtype
- source lane and confidence
- proposed value or structured input shape
- the exact writable extent, including child cells
- related group members
- a visible draft value over the page
- one checkmark to accept the whole answer
- an edit path that supports one string and deterministic splitting
- reject, retype, resize, move, and manual-add controls
- missing or uncertain state rather than false completeness

The review surface should make the next action obvious. “100% reviewed” is
incorrect when no targets were proposed. A zero-target document should say
`No editable targets found`, remain at 0%, and offer manual drawing plus an
explanation that the detector may have abstained.

Review changes must persist as a manifest revision. The export receipt should
include source hash, manifest revision, manifest hash, and output hash. Reopen
the exported file and inspect its widgets and rendered appearance before
claiming the answer was filled.

## Product-specific corrections that became general rules

The following defects were not one-off patches. They became generalized rules:

| Observed defect | General rule now recorded |
|---|---|
| User could not tell which composite field they were filling | Keep full label context and show named group plus child structure inline |
| User had to fill every character cell separately | Accept one logical answer, then split into ordered rows or cells |
| A checkmark changed status but not visible content | Show a committed overlay and verify export appearance, not just state |
| Generic financial-statement rectangles became fields | Require semantic cue plus spatially associated geometry and retain diagnostics |
| `Account no:` and `Phone no:` were classified as Choice | Use token boundaries and exclude standalone `no` from Choice cues |
| `Candidate name:` was classified as Date | Use exact date tokens, not substring matching |
| Unicode labels were damaged | Normalize with Unicode-aware word boundaries |
| Inferred photo and signature targets auto-accepted | All inferred targets start pending, independent of confidence |
| Manifest edits did not control export | Rebuild output from source plus accepted manifest revision |
| Uploading a file named `editable.pdf` collided with server output | Store a collision-safe physical source and preserve display filename separately |
| Form-6 child boxes overlapped labels and missed lower rows | Model parent groups, rows, options, and usable interiors explicitly |
| Native and inferred lanes suppressed unrelated page content | Compose detections per page and suppress only overlapping duplicates |
| Review overlays visually covered the source form | Use transparent low-contrast outlines for ordinary targets, a light rounded perimeter for groups, and stronger tint only on hover, selection, or committed values |

## Case-study lessons

### Form-6

Form-6 is a useful calibration document because it contains dense painted form
structure, character grids, choices, photo space, signatures, and composite
groups. It is not a universal PDF benchmark.

The initial visual audit found uncovered multi-row name grids, an
undifferentiated mobile grid, missing Aadhaar digits and disability percentage,
label-overlapping child regions, and a signature band touching its caption.
The correction was not a larger list of labels. It was a better representation
of parent groups, row geometry, option geometry, ordered children, and review
semantics.

Current local evidence for this document is 33 typed logical targets and 49
vector diagnostics. Its annotation record is pending human verification.

### Medpiper financial statement

Medpiper is a precision and abstention probe. Its tables, rules, page furniture,
and prose are visually rich but are not ordinary editable form targets. It also
contains signatures that matter for audit.

The correct architecture uses two outputs:

1. generic editable-target detection, currently zero logical targets
2. a separate signature observation lane, currently 12 expected slots with 9
   present and 3 missing

This is a reusable pattern for contracts, financial statements, approvals, and
signed reports. A document may be non-editable in the generic sense while still
having audit-relevant visual observations.

## Dataset and model lessons

The controlled gold set contains three authored families with flat-vector,
native-widget, and image-only representations. It is valuable for pipeline
regression, but it is not evidence of arbitrary-document generalization.

FUNSD and DocLayNet geometry are useful sources for weak or proxy supervision,
layout normalization, and model experiments. Their labels do not automatically
mean “fillable PDF field.” Dataset semantics must be mapped into the Fieldroom
ontology and marked with provenance.

The current lightweight model is advisory. The observed baseline was 8,734
records with group-disjoint holdout accuracy 0.3778 and macro-F1 0.2500. FUNSD
test data was excluded, and the Form-6 family was held out. This is a useful
baseline and a useful warning, not a promotion case.

The repository now enforces a safer progression:

```text
tested source
    -> sanitized annotation record
    -> human review and adjudication
    -> family-isolated split
    -> trainable view
    -> frozen benchmark
    -> optional model experiment
    -> promotion review
```

Model promotion requires a document-disjoint, field-level benchmark that beats
the deterministic baseline on recall, type accuracy, label association,
geometry quality, duplicate control, false-positive rate, and abstention risk.
The model may rank or enrich candidates before that point, but cannot override
geometry, ontology, source provenance, or review authority.

Autoresearch, Modal, and any remote training service are experiment surfaces,
not evidence shortcuts. A remote run needs a frozen evaluation set, a privacy
and license decision, an explicit input schema, cost and latency receipts,
failure recovery, and a reproducible local comparison. No Modal job has been
submitted for this project.

## Label governance lessons

The label repository at `data/labels/` is canonical for field-level
supervision. It stores:

- source hash and non-sensitive locator
- page count and normalized page geometry
- typed target boxes and expected state
- group and role information
- present versus missing signature occupancy
- reviewer, status, revision, disagreement, and provenance metadata
- family lineage and split role
- license or adoption status

It must never store:

- raw PDF bytes
- completed form values
- photo pixels
- signature pixels
- unredacted signer names

The current seed contains 13 records: 9 controlled proxy records and 4 pending
records. The default `trainable.jsonl` contains zero records. This is a healthy
state until the real Form-6 and Medpiper annotations are visually reviewed.

The system-corpus benchmark currently has a collection snapshot with 146 deep
samples and 94 logical proposals, not field-level gold labels. It must not be
treated as training data until each adopted document has a reviewed manifest,
family assignment, and provenance decision.

## Evidence model learned from the work

Every claim should carry both evidence tier and sensitivity:

- Tier 0: assumption or design hypothesis
- Tier 1: static source or manifest inspection
- Tier 2: targeted deterministic test or PDF reopen check
- Tier 3: local API or integration flow
- Tier 4: local browser, runtime, or visual observation
- Tier 5: production-like, external viewer, provider, or deployed evidence

Sensitivity labels:

- S0: test exists
- S1: test passes
- S2: defect reproduced, then fixed and retested
- S3: deliberate mutation makes the check fail

Important distinctions:

- a passing test proves the checked invariant, not universal correctness
- a visual screenshot proves the observed render, not semantic recall
- OCR confidence proves recognition confidence, not field intent
- a model metric proves the chosen split and labels, not production quality
- a local server proves local runtime behavior, not deployment safety
- a source signature observation proves visual occupancy, not legal validity

## Experiment protocol for future improvement

Every detection experiment should use the following record:

1. Hypothesis: one sentence that could be falsified.
2. Baseline: current deterministic and model behavior on a frozen set.
3. Scope: document families, representations, page types, and exclusions.
4. Change: one detector, data, threshold, or representation change.
5. Metrics: recall, precision, type accuracy, association, geometry IoU,
   duplicate rate, abstention rate, latency, and memory where relevant.
6. Visual sample: source page, proposals, accepted labels, and hard negatives.
7. Failure taxonomy: missed target, false positive, bad type, bad grouping,
   bad geometry, stale export, unsafe data, or unsupported input.
8. Falsifier: the result that would reject the proposed change.
9. Decision: retain, revert, isolate as proxy, or promote behind review.
10. Receipt: exact source hashes, code version, commands, output hashes, and
    unresolved risks.

Useful experiments include:

- page-level routing ablations on mixed native, vector, and raster documents
- label-window and association ablations on dense forms and tables
- OCR and CV robustness across DPI, skew, noise, contrast, and rotation
- composite-group splitting on names, addresses, identifiers, and dates
- native widget preservation with radio, dropdown, multiline, inheritance,
  repeated widgets, rotation, and XFA cases
- signature-slot occupancy on signed and unsigned reports
- multilingual labels and answer rendering with explicit script metadata
- document-disjoint model comparison against the deterministic baseline
- deliberate mutation tests for training leakage, duplicate suppression, and
  manifest-to-export binding

## Open questions and falsifiers

| Question | Current answer | Falsifier or closure evidence |
|---|---|---|
| Can one generic detector cover arbitrary PDFs? | Not established | Independent family-disjoint benchmark with recall and abstention reporting |
| Can CV identify photo and signature regions? | It can propose useful regions and occupancy evidence | Reviewed scanned and painted cases across layouts and resolutions |
| Can NLP reliably associate labels? | It improves typing and association when geometry constrains it | Adversarial dense-layout set with label swaps and hard negatives |
| Should confidence auto-accept inferred targets? | No | A risk-approved benchmark and review policy would be required to change this |
| Can proxy datasets train production semantics? | They can support advisory calibration only | Provenance-mapped, field-level real gold set with promotion metrics |
| Can a signed PDF be edited safely? | Only with explicit signature invalidation and viewer policy | Acrobat, Preview, browser, and PDF/A compatibility receipts |
| Can the macOS app share this pipeline? | Yes after contracts and evidence stabilize | Native/browser parity on the locked unseen-family suite |
| Can remote training improve the model? | Unknown and currently unsubmitted | Frozen local baseline, privacy approval, cost receipt, and reproducible gain |

## Next actions and ownership

The next coherent work sequence is:

1. Build a browser review queue that opens the real source, shows all proposed
   targets and abstentions, and writes reviewed annotation revisions.
2. Have the user verify Form-6 and Medpiper visually, including missing
   signatures and missed or rejected fields.
3. Add at least 5 to 10 independent real document families with field-level
   labels and hard negatives.
4. Rebuild the trainable view and record the promotion receipt.
5. Rewire the advisory training command to consume that view and never bypass
   its policy.
6. Run a frozen document-disjoint benchmark and mutation-sensitive checks.
7. Only then evaluate autoresearch, Modal, or a tiny model improvement loop.
8. Close export, viewer, multilingual, security, storage, and browser
   end-to-end gates before porting to `pdf_editor`.

The revisit trigger for this ledger is any change to the ontology, detection
authority, label schema, training source, export contract, or macOS port
boundary. Append a dated decision rather than silently rewriting the rationale.

## 2026-09-10 Receipt-bound training gate

- Objective: make the label repository the actual authority for every local
  and future remote training entrypoint.
- Finding: the earlier trainer consumed `training_data.build_training_records()`
  directly, while `data/labels/trainable.jsonl` was only a documented side
  artifact. That allowed the implementation to claim a gate without proving
  that the trainer used it.
- Decision: `src/pdf_field_lab/label_policy.py` is the canonical policy and
  consumption boundary. The generated view is receipt-bound by source-record
  and view hashes, and is revalidated at training time. Only `development`
  records are eligible. Proxy records require explicit development opt-in and
  controlled, project-authored provenance. Verified records additionally
  require reviewer identity, verification time, review receipt, and explicit
  training approval.
- Adapter boundary: label records remain auditable document-level revisions;
  `training_examples_from_records` expands their manifests into typed model
  examples while retaining record and family lineage. This prevents one
  document representation from becoming an untraceable flat row.
- Evidence: focused label/model tests pass; the default trainer refuses the
  current empty view; explicit proxy mode consumed 9 governed records and 63
  typed examples with a family-disjoint holdout; the default view was rebuilt
  afterward. Evidence is local Tier 2 plus a bounded local training run, not
  production or real-world quality proof.
- Falsifier: a trainer or Modal entrypoint that can train after a source/view
  hash change, from validation or locked-test data, or from a verified record
  lacking review and training approval. Add such cases before promoting any
  model beyond advisory use.
- Remaining work: create a sanitized verified fixture with a genuine review
  receipt, test default-mode consumption, and retain the real Form-6 and
  Medpiper records outside training until the user reviews them.

## 2026-09-10 Native AcroForm preservation boundary

- Objective: ensure generalized reconstruction is additive when a source PDF
  already contains native AcroForm widgets.
- Finding: native buttons and signatures were emitted with non-native strategy
  strings, and any mixed export replaced the source `/AcroForm` with a newly
  generated field array. A PDF containing native fields plus one inferred
  target could therefore lose the original field tree.
- Decision: native detection now uses explicit strategy families for text,
  checkbox, radio, dropdown, and digital signature widgets. Mixed export keeps
  the cloned `/AcroForm` and appends only newly reviewed widgets. A dropdown is
  typed as the user-facing `Choice` kind while retaining its native strategy.
- Evidence: a focused `/Ch` detection test and a native-plus-inferred export
  regression pass. Evidence is Tier 2 and does not establish Acrobat, Preview,
  XFA, PDF/A, or every viewer's behavior.
- Falsifier: any mixed export that drops an existing field name, `/Opt`, value,
  flag, parent/kid relationship, repeated widget, or native appearance; any
  native field treated as an inferred replacement without explicit policy.
- Remaining work: add fixtures for radio groups, dropdown values, inherited
  field properties, repeated widgets, XFA coexistence, rotated pages, and
  reviewed geometry edits. Keep cryptographic signature preservation distinct
  from visual signature placement.

## 2026-09-10 Export identity and download binding

- Objective: make the downloaded PDF unambiguously correspond to the reviewed
  manifest and entered values that produced it.
- Finding: the server wrote every export to `filled.pdf` and returned one shared
  download URL. A later edit, repeated export with different values, or a
  concurrent request could make an earlier receipt describe different bytes.
- Decision: output filenames and receipt paths are keyed by manifest revision,
  canonical manifest hash, and canonical values hash. The download URL carries
  those identities. The server reads the exact receipt, verifies the immutable
  source hash, rejects unsafe output paths, and rechecks the output hash before
  serving bytes. A latest-receipt pointer exists only as a compatibility
  convenience; identity-bearing URLs are the canonical browser path.
- Evidence: the server suite passes, including two same-revision exports with
  different values and successful retrieval of both historical outputs. This
  is local Tier 3 evidence, not multi-worker production-storage or external
  viewer proof.
- Falsifier: an identity-bearing URL serving a different manifest, values,
  source, or output hash; deletion or replacement of a prior immutable output;
  an export receipt that cannot be replayed to its exact output.
- Remaining work: prove concurrent multi-worker behavior once durable storage
  exists, add cleanup/retention semantics, and collect Acrobat, Preview,
  browser-viewer, and PDF/A reopen receipts.

## 2026-09-10 Repository launch and publication baseline

- Objective: establish this workspace as a real git-tracked project with a
  documented baseline and remote landing target.
- Action sequence completed: staged the full workspace after `.gitignore` hardening,
  ran a full local gate (`uv run pytest` with 53 passed), initialized local git,
  committed on `main`, created remote
  `https://github.com/pranaysuyash/pdf-form-field-lab`, and pushed `ca43892`.
- Evidence for this boundary:
  - working tree is clean after push
  - remote points to `origin` and tracks `origin/main`
  - full gate status S1 for baseline tests
- Doctrine alignment note: this baseline closes the initialization and publication
  lane before the next feature lane and before any macOS app porting work.
- Required revisit condition: any change to repository scope, hook policy, or
  privacy, training, and export boundaries should add a new dated ledger row.
