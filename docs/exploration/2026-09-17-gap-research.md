# Exploration record: council gap research pass

Date: 2026-09-17

Research record for the exploration items raised by the 2026-09-17 gap
council. Each item states the question, the evidence already in hand, the
method that would answer it, and the falsifier that would kill the working
hypothesis. Companion entries are filed in the workspace exploration map
(IDEA_PAD 135-139).

## R01 — Advisory model: park or fund?

- **Question:** should the advisory target-type model be demoted
  (`PDF_FIELD_LAB_ADVISORY_MODEL=off` as default), removed, or funded toward
  a promotable benchmark?
- **Evidence in hand:** current holdout is near-noise (accuracy 0.378,
  macro-F1 0.25; `docs/verification.md`). The model is already
  non-authoritative by construction. The operator switch now exists
  (FFL-RANK-007).
- **Method:** ship FFL-FLY-011, run real review sessions, and measure
  corrected-label volume per document family over 2-4 weeks. Retrain only
  when a family has >= 20 verified, document-disjoint corrections; evaluate
  against the deterministic baseline on the same holdout contract
  (family-isolated, hard negatives included, abstention risk reported).
- **Falsifier:** if flywheel volume stays below the retraining threshold for
  a month of real use, the fund branch is dead and park/remove wins.
- **Decision owner:** Pranay (registered as a user decision; the mechanism
  ships now, the default flip does not).

## R02 — Correction-volume measurement

- **Question:** how much usable gold data does real review activity produce?
- **Evidence in hand:** the flywheel emits one candidate per review event;
  `build_label_repository.py --review-candidates` ingests them as pending
  records, so volume is countable from `records.jsonl` lineage.
- **Method:** after each review batch, rebuild the repository and report
  counts by event type and family; watch pending -> verified conversion rate.
- **Falsifier:** if accepted-event candidates routinely duplicate geometry
  already covered by the reviewed Form-6 profile or the gold set, the
  flywheel adds no evaluation data and should be scoped down.

## R03 — Real-scan recall (Form6_preview gap)

- **Question:** why does generic CV/OCR recover only 4 review-required
  targets on `Form6_preview.pdf` while visual inspection shows address
  blocks, grids, photo, disability, and signature regions?
- **Evidence in hand:** bounded raster pass receipt (`user-folders-all-pass-v2`
  slice, 4 targets, "substantial missed regions" visually confirmed). The
  semantic whitespace lane abstains when geometry sits within 48 points
  vertically of a label word (confirmed while authoring the calibration
  fixture) — scanned-form label-to-region distances may routinely exceed
  lane tolerances.
- **Method:** render Form6_preview pages at 150-300 DPI, run the bounded
  raster lane, and diff detected vs. visually labeled regions per page;
  classify each miss (threshold, cue-vocabulary, region-merge, or
  page-routed-lane choice).
- **Falsifier:** if most misses are cue-vocabulary misses on Tamil/English
  mixed labels, the fix is multilingual cue work (FFL-LANG-009), not
  geometry tuning.

## R04 — Scanned-form gold acquisition

- **Question:** what real-scan corpus is sufficient to claim raster-lane
  recall?
- **Evidence in hand:** the controlled gold set covers image-only
  representations of authored families (18/18), but authored scans are not
  real-world generalization proof; the bounded 20-file raster slice found 2
  raster targets, both synthetic.
- **Method:** acquire 10-20 real scanned forms across at least 5 independent
  families (privacy policy: user-supplied local documents only, redacted
  locators, same provenance schema as the label repository); hand-review
  region manifests at the reviewed-region standard before any detector run.
- **Falsifier:** if fewer than 5 independent real families can be obtained
  under the privacy policy, the recall claim stays explicitly open rather
  than being closed with a biased corpus.

## R05 — Wrong-label evaluator counterexamples

- **Question:** can the evaluator separate localization recall from
  label-ontology correctness so wrong-label matches stop masking failures?
- **Evidence in hand:** `FFL-EVL-005` (proposed) documents the masking risk;
  the current matcher credits a match on geometry alone and reports label
  similarity separately but never fails a case on wrong label.
- **Method:** add adversarial fixtures where geometry matches but the label
  is wrong (swapped-label pairs), assert they are reported as
  `label_mismatch` instead of `matched`, and add an independent wrong-label
  metric to the receipt contract.
- **Falsifier:** if wrong-label cases cannot be constructed without also
  breaking the matcher's underline tolerance, the matcher needs redesign
  first (escalate to architecture review).

## R06 — Multilingual capability (retained open by design)

- **Question:** when does language-aware detection become roadmap-worthy?
- **Evidence in hand:** lexical cues are English-only
  (`_FIELD_CUE_WORDS`); R03 may show mixed-script labels are already the
  dominant miss class on real documents.
- **Method:** decide with R03's miss taxonomy in hand; keep multilingual
  closure gated on per-language, per-script evidence as the register already
  requires.
- **Falsifier:** n/a — this item gates other work, it is not falsifiable
  until R03 produces its miss taxonomy.
