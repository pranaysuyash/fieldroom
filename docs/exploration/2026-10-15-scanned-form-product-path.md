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

## Measured result (2026-10-15, tools/scan_bakeoff.py)

The bake-off ran against a synthetic scan proxy: the Form-6 fixture rendered
to 200-DPI images (clean) plus a degraded variant (0.8-degree rotation,
sigma-12 noise), eight cells total (clean/degraded x none/denoise/contrast/
combined), each fed through the unchanged raster lane. Findings:

- Vector lane on the original: 36 targets. Raster lane on the identical
  rendered content: 22 (clean, no preprocessing) at best; 25 on
  degraded+combined. The raster gap versus vector is ~14 regions on the same
  pixels, before any real-scan artifacts are involved.
- Preprocessing does not dominate: denoise LOSES targets on clean input
  (22 -> 16) and contrast loses one (21); on degraded input combined gains
  (22 -> 25) but denoise/contrast lose. No variant is safe everywhere.
- Mild degradation barely moves the lane (22 -> 22 plain), so degradation is
  not the first-order bottleneck either.

Conclusion (revising the sequencing above): preprocessing is NOT the
bottleneck; the raster lane's region-proposal vocabulary is. The next bounded
step is the miss taxonomy (which 14 regions are missing, classified), and
preprocessing should only be applied where a specific classified miss calls
for it. The synthetic-raster caveat stands: a render is not a real scan; the
documented real-scan failure (2 targets) involves characteristics this proxy
does not reproduce, which strengthens the case for real-scan gold (IDEA-137).

## Falsifier for the whole frontier

If preprocessing plus taxonomy-driven fixes still recover fewer than half of
the visually confirmed regions on Form6_preview, the honest product position
is that scanned forms are out of scope for this architecture generation, and
the register should say so instead of keeping an unfalsifiable open gate.
Against the proxy, recovery is already 61% of vector count; the real-test
version of this falsifier still needs real-scan gold (IDEA-137).
