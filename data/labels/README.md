# Fieldroom label repository

This directory is the canonical annotation layer for generalized PDF field
detection. It is not a copy of the PDF corpus and it is not a Git repository by
itself. Raw PDFs remain at their existing local locations and are referenced by
hash and locator only.

## Safety and authority rules

- Never copy source PDFs, completed values, photos, or signature pixels here.
- A source hash identifies a document version but does not make it public or
  transferable. Keep this repository local when the source is sensitive.
- Detector output is evidence, not ground truth. A label record starts
  `pending` unless it is an authored controlled fixture or has a reviewer and
  verification receipt.
- `verified` means a human reviewed the source render and annotation. It does
  not mean the detector is correct on the whole document population.
- Pending, rejected, and proxy labels are excluded from training by default.
- All derivatives of one template family share a family ID and split. A flat,
  native, scanned, translated, or completed derivative cannot become an
  independent test example.
- Signature labels record only the slot geometry, occupancy status, and review
  evidence. They do not store signer names, signature images, or legal claims.

## Files

- `schema.json`: versioned record and annotation contract.
- `records.jsonl`: one record per tested document or controlled representation.
- `review-queue.jsonl`: pending real-document records requiring human review.
- `annotations/`: sanitized target manifests, never source PDFs.
- `splits.json`: split policy and locked-test rules.
- `trainable.jsonl`: generated, policy-filtered view for model jobs.
- `trainable-receipt.json`: counts and policy used to build that view.

The repository is seeded with the current Form-6 probe, the Medpiper financial
statement probe, the nine controlled gold representations, the read-only
calibration fixture, and the system-corpus benchmark snapshot. The controlled
fixtures are authored labels, not human real-world confirmation. The real PDF
records are pending and are marked not-for-training until reviewed.

## Review workflow

1. Open the referenced source locally and render every page at readable DPI.
2. Review target type, writable extent, label association, group membership,
   existing versus empty signature slot, and abstention regions.
3. Record reviewer identity, timestamp, disagreements, and adjudication in the
   annotation record. Do not put entered values or source pixels in this tree.
4. Change the record status to `verified` only after the visual review receipt
   exists.
5. Keep validation and locked-test records immutable after their split is
   locked. Corrections become a new revision in the same family, not a silent
   rewrite.

Training should consume a generated view of records whose status, split role,
license, privacy policy, manifest hash, and review receipt all permit use. It
must never train directly from `records.jsonl` by assuming every record is
authoritative. Run `.venv/bin/python scripts/build_trainable_label_view.py`
before a training job. The trainer validates the view and receipt again, so a
manually edited or stale JSONL cannot become an implicit source of truth.

Only `development` records can train. A verified record additionally needs a
reviewer, verification timestamp, review receipt, and explicit
`provenance.training_approval.status=approved`. The default view currently
contains zero records because the real probes are pending and the controlled
records are proxy labels. Use `--include-proxy` only for a clearly named
development calibration experiment; the receipt records that choice, and the
default view must be rebuilt afterward.

## Upstream dataset licenses

Both upstream datasets are used locally as proxy/layout supervision only.
Neither is redistributed from this repository, and no trained derivative may
be redistributed until the license statements below are re-verified against
the exact snapshot used.

- **FUNSD** (`benchmark/datasets/funsd` in the sibling reference tree): the
  canonical site (guillaumejaume.github.io/FUNSD) carries a copyright notice
  but states no explicit license name on its landing page. License status:
  **unverified**. Re-checked 2026-10-14: the author site no longer resolves
  and public mirrors carry no license tag, so the primary source remains
  unlocatable; treat as all-rights-reserved until the author's license
  statement is located and recorded here (exploration note:
  `docs/exploration/2026-10-14-governance-spine-research.md`, D04).
- **DocLayNet** (`benchmark/datasets/doclaynet`): Community Data License
  Agreement – Permissive, Version 1.0 (CDLA-Permissive-1.0), copyright IBM.
  Permits broad use with attribution and notice-preservation requirements;
  re-read the shipped LICENSE file before any redistribution of derivatives.
