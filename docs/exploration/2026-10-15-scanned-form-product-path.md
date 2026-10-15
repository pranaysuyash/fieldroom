# Exploration record: scanned forms as the product frontier

Date: 2026-10-15
Companion items: IDEA_PAD 136 (miss taxonomy), register rows FFL-MIX-007 and
the scanned-form P0 gates. This note sequences the scanned-form work as a
PRODUCT decision, not only a detection-quality one.

## Question

Fieldroom's review-fill loop works on native and vector-text documents. What
is the evidence-backed path to scanned forms, and what does each candidate
path actually buy the product?

## Evidence in hand

- The bounded 20-file raster slice executed CV/OCR and recovered only 2
  raster targets, both on the synthetic handwritten fixture
  (docs/open-items.md, raster-recall gate).
- Form6_preview visually contains address blocks, grids, photo, disability,
  and signature regions while the generic lanes recovered only 4
  review-required targets (same register row).
- The public demo document is a clean vector-text government form: the easy
  case. Real paperwork that needs this tool is predominantly scanned.
- The review loop now has governed receipts and an ingesting label builder
  (FFL-HQ-006/FLY-011), so any scan improvement is measurable against human
  labels — but there are almost no reviewed real-scan labels yet
  (review queue 0/38, no document-disjoint gold set).

## Candidate paths, and what each one is worth

1. **Preprocessing first (deskew, denoise, contrast, DPI normalization).**
   Cheapest, bounded, testable against the same fixtures. Worth doing before
   any model-adjacent work because every later lane benefits. Falsifier: if
   normalized renders do not change recovered-target counts on Form6_preview,
   preprocessing is not the bottleneck.
2. **Region/layout reasoning (R03/IDEA-136).** The Form6_preview miss
   taxonomy work: classify every miss as threshold / cue-vocabulary /
   region-merge / lane-routing before touching algorithms. Produces the
   dominant-miss-class ordering that all later effort should follow.
3. **Gold acquisition (R04/IDEA-137).** 10-20 real scanned forms across 5+
   families with hand-reviewed manifests under the redacted-locator schema.
   Without this, nothing can be claimed, and the review loop is now good
   enough to produce it — which is exactly why reviewer throughput (shipped
   2026-10-15) had to come first.
4. **Learned region proposals.** Explicitly parked behind 1-3; the RANK-007
   park decision and the absence of scan gold make this unfundable now.

## Sequencing conclusion

The dependency order is: reviewer throughput (shipped) → preprocessing bake-off
(1) → miss taxonomy (2) → gold acquisition in parallel with (2) → only then
consider (4). Item 1 is a bounded experiment runnable against existing
fixtures; items 2 and 3 share the same review sessions.

## Falsifier for the whole frontier

If preprocessing plus taxonomy-driven fixes still recover fewer than half of
the visually confirmed regions on Form6_preview, the honest product position
is that scanned forms are out of scope for this architecture generation, and
the register should say so instead of keeping an unfalsifiable open gate.
