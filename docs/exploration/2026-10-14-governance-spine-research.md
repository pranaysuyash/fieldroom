# Exploration record: governance spine research pass

Date: 2026-10-14

Companion to the 2026-10-14 implementation pass (FFL-HQ-006 review receipts,
FFL-SEC-010 quarantine/audit/lifecycle, FFL-EVL-005 stable matching and
wrong-label metrics, FFL-GOV-001 receipt contract). Each item states the
question, evidence in hand, the method that answers it, and the falsifier.
Workspace-map entries: IDEA_PAD 138-142.

## R06 — Explicit multilingual input contract

- **Question:** what is the smallest honest contract for per-document and
  per-field language/script handling that FFL-LANG-009 can close against,
  before any multilingual detection work starts?
- **Evidence in hand:** multilingual is explicitly retained open; current
  Unicode-preserving normalization and English tests close nothing. The
  existing evidence-tier vocabulary (T1-T5) and review receipt chain now
  provide the provenance shape a language transcript would need.
- **Method:** draft the contract as a schema note, not code: per-document
  `language`/`script` metadata, per-field overrides, reversible
  translate/transliterate preview actions with audit receipts, and explicit
  unsupported-script abstention in export. Validate the contract against two
  bilingual fixture forms before any OCR routing work.
- **Falsifier:** if no bilingual fixture can be authored under the
  local-privacy policy (no real personal data), the contract cannot be
  evidence-closed and stays a design note — no false closure.
- **Decision owner:** Pranay (whether to fund the bilingual fixture authoring
  at all this quarter).

## D04 — Dataset license statements (FUNSD, DocLayNet)

- **Question:** what exact license terms govern the two candidate evaluation
  datasets, so `data/labels/README.md` can state them without hedging?
- **Evidence in hand (2026-10-14):**
  - **DocLayNet: CDLA-Permissive-1.0**, verified from the primary source
    (`github.com/DS4SD/DocLayNet` LICENSE file, Linux Foundation CDLA
    Permissive 1.0 text). Citation of Pfitzmann et al., KDD 2022
    (arXiv:2206.01062) requested by the repo.
  - **FUNSD: primary source unverifiable today.** The official site
    (`guillaumejaume.site/funsd`) no longer resolves; HF mirrors carry no
    license tag. Community understanding is research-use with citation of
    Jaume, Ekenel, Thiran (ICDAR 2019 workshops), but that is not a
    primary-source quote.
- **Method:** record DocLayNet's terms in `data/labels/README.md` now;
  record FUNSD as citation-required research use with an explicit
  "confirm against the distributed archive before any redistribution or
  commercial use" gate. The dead official site is itself a finding:
  provenance for FUNSD depends on an archive copy, which is also an input
  to the R04 gold-acquisition plan.
- **Falsifier:** if the archived FUNSD terms turn out to restrict
  redistribution of derivatives, FUNSD-derived evaluation artifacts must be
  rebuilt as access-on-demand rather than committed.
- **Decision owner:** none needed unless FUNSD terms block; proceed with the
  hedged README statement.

## EVL-005 follow-up — real-world wrong-label corpus

- **Question:** does the new `label_error_rate` metric separate real
  ontology confusion from fixture artifacts once run against the
  document-disjoint gold set (P0) rather than synthetic calibration?
- **Evidence in hand:** evaluator v2 emits `label_error_count`,
  `label_error_rate`, `label_errors`, miss diagnostics with
  `nearest_prediction` (including `consumed_elsewhere`), and a stable
  order-invariant assignment (schema `detector-evaluation.v2`). Calibration
  regenerated: 4/4 recall, precision 1.0, label_error_count 0.
- **Method:** when the real gold set exists, run evaluator v2 per family and
  cluster `label_errors` by (expected kind, predicted kind) pairs; the
  dominant pair becomes the ontology-anchors work item.
- **Falsifier:** if `label_error_rate` is ~0 while humans still flag wrong
  labels in review sessions, the label-similarity threshold (0.5, token
  Jaccard) is too loose and needs anchor-aware similarity.
- **Decision owner:** none; feeds the P0 gold-set milestone.

## SEC follow-up — session durability boundary

- **Question:** when must sessions move from the OS temp directory to
  durable, permissioned storage?
- **Evidence in hand:** the 2026-10-14 pass hardened the ephemeral path
  (startup/health/create TTL sweeps, audited expiry, vanished-storage 404)
  and the audit ledger itself is temp-scoped. Sessions surviving restart is
  a product requirement only if review sessions become multi-sitting.
- **Method:** decide with the review-session workflow data: if a real review
  session on a 250-page document regularly exceeds one sitting, durable
  storage with deletion semantics becomes P1; otherwise keep ephemeral.
- **Falsifier:** if no session is ever interrupted before TTL (one hour),
  durability adds attack surface without value.
- **Decision owner:** Pranay (registered in DECISIONS_PENDING as
  FFL-D-session-durability).

## NAT/SEC follow-up — XFA quarantine policy

- **Question:** is fail-closed XFA quarantine the right long-term policy, or
  should AcroForm+XFA coexistence be supported for editing?
- **Evidence in hand:** XFA-bearing uploads are now quarantined with a
  named-category message. FFL-NAT-003 lists XFA coexistence as open on the
  detection side. Dynamic XFA forms cannot be safely edited by cloning the
  AcroForm tree.
- **Method:** author a static-XFA fixture (AcroForm fields + XFA packet with
  matching content), prove clone-export reopens correctly in viewers, and
  only then consider relaxing quarantine for static XFA while keeping
  dynamic XFA quarantined.
- **Falsifier:** if any mainstream viewer renders the fixture's dynamic XFA
  over the cloned tree, the static/dynamic split is not enforceable and
  blanket quarantine stands.
- **Decision owner:** Pranay (registered as FFL-D-xfa-policy; default stays
  quarantined until the fixture evidence exists).
