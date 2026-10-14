# Review-session runbook (first human review pass)

Date: 2026-10-14. This is the one-command path from "nothing reviewed" to
"governed correction volume in the label repository". Pranay is the named
reviewer; the whole loop runs locally and nothing leaves the machine.

## 0. Preconditions

- Dependencies available (throwaway venv or your own `.venv`): core + `dev`.
- `qpdf` and `tesseract` present is nice-to-have; the session works without.
- `data/samples/RAr0Lq2Avu.pdf` (blank Form-6) is the first review target;
  the Medpiper document re-links via `PDF_FIELD_LAB_MEDPIPER_PDF` when you
  want a second, harder one.

## 1. Start the session

```bash
export PDF_FIELD_LAB_REVIEWER=pranay
uvicorn pdf_field_lab.server:app --port 8787
```

Open `http://127.0.0.1:8787` and upload the Form-6 sample. The reviewer name
is operator attestation, not authentication — it is recorded on every review
event and receipt.

## 2. Review

Work page by page through the field list:

- **Accept** (✓ / "mark reviewed") when the detected region, type, and label
  are right.
- **Reject** a target the detector invented (signal: `false-positive`).
- **Draw manually** anything real the detector missed (signal:
  `detector-miss` — this is the gold-dust data).
- **Move/resize** wrong boxes (signal: `geometry-correction`).

Every manifest save writes review events plus a hash-bound receipt
(`review-receipts.jsonl` in the session directory, exported via
`GET /api/sessions/{id}/review-receipts.jsonl`).

## 3. Export the evidence

```bash
SESSION_ID=<from the session payload or browser network tab>
curl -s "http://127.0.0.1:8787/api/sessions/$SESSION_ID/review-candidates.jsonl" \
  -o review-candidates-form6.jsonl
curl -s "http://127.0.0.1:8787/api/sessions/$SESSION_ID/review-receipts.jsonl" \
  -o review-receipts-form6.jsonl
```

Keep both files; they are the provenance a future `verified` label record
will cite (`review_receipt` must carry `receipt_sha256` + matching reviewer).

## 4. Ingest into the label repository

```bash
python3 scripts/build_label_repository.py \
  --review-candidates review-candidates-form6.jsonl
```

Candidates enter as `pending`, `not-for-training` records keyed by source
hash; they survive plain rebuilds. Nothing is training-eligible until you
promote a record to `verified` with a receipt — and the fail-closed gate
(enforced in `label_policy.py`) will refuse any record whose receipt lacks a
`receipt_sha256` or whose reviewer does not match.

## 5. What this feeds

- **FLY-011 correction volume** → the measurable output of the review loop.
- **GOV-001** → the first real review receipt (machinery already proven on a
  synthetic fixture in `tests/test_verified_fixture.py`).
- **RANK-007** → the parked advisory model can only be un-parked by ≥20
  verified, document-disjoint corrections in a family — this is where those
  would come from.

## Note on scope

Do not review `tests/local/` fixtures or anything outside your own
documents. The corpus is currently Form-6 (blank) and, on request, the
Medpiper financial statement. A document-disjoint gold set needs 5–10
independent families — sourcing those is the open R04 exploration item, not
part of this runbook.
