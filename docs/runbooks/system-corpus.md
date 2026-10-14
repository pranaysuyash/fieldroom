# System PDF corpus runbook

Status: active local verification procedure

Owner: pdf-form-field-lab detector and review workflow

Last materially reviewed: 2026-09-10

## Purpose

This runbook defines how to discover, analyze, and visually inspect PDFs across
the local machine without confusing corpus coverage with field-level accuracy.
Original PDFs are never copied, uploaded, or modified by the benchmark.
Receipts store paths, structural metadata, hashes for analyzed candidates, and
target summaries, not extracted values or page text.

## Corpus roles

The local corpus is intentionally split by role:

- The sibling project's `benchmark/datasets/` tree is dataset and fixture
  material. FUNSD and DocLayNet are proxy/layout supervision sources, while the
  checkbox, radio, and choice fixtures are deterministic behavior tests.
- Other PDFs under the operator's home folders (`~/Desktop`, `~/Documents`,
  `~/Downloads`, and `~/Projects`) are discovery, stress, and holdout material.
  They are not training
  data merely because the detector produced a candidate.
- A document becomes trainable only after a reviewed, document-disjoint label
  manifest records field geometry, type, label association, grouping,
  abstentions, provenance, and reviewer status.

The full system inventory currently includes every discovered PDF under
`~` when default exclusions are disabled. That deliberately includes
temporary and generated paths so discovery coverage is measurable. Such paths
must be filtered by an explicit reviewed split before model use.

## Commands

Create a fresh full inventory:

```bash
uv run python scripts/system_corpus_benchmark.py \
  --root ~ \
  --disable-default-exclusions \
  --collect-only \
  --output-dir artifacts/system-corpus/all-pdfs-collect-pass-v3
```

Analyze a deterministic slice from that inventory. `--manifest-start` and
`--manifest-limit` make long runs resumable without changing the ordering:

```bash
uv run python scripts/system_corpus_benchmark.py \
  --manifest-path artifacts/system-corpus/all-pdfs-collect-pass-v3/inventory.jsonl \
  --disable-default-exclusions \
  --analyze-all \
  --manifest-start 0 \
  --manifest-limit 500 \
  --max-analysis-bytes 20000000 \
  --progress-every 50 \
  --output-dir artifacts/system-corpus/all-pdfs-manifest-batch-00
```

Run the slower CV/OCR semantic lane only for a bounded slice:

```bash
uv run python scripts/system_corpus_benchmark.py \
  --manifest-path artifacts/system-corpus/all-pdfs-collect-pass-v3/inventory.jsonl \
  --disable-default-exclusions \
  --analyze-all \
  --manifest-start 0 \
  --manifest-limit 50 \
  --max-analysis-bytes 20000000 \
  --run-raster \
  --progress-every 10 \
  --output-dir artifacts/system-corpus/raster-manifest-batch-00
```

Analyze all currently discovered PDFs under `pdf_editor`, including its local
datasets and fixtures, by finding that path family in the full inventory and
running a manifest slice. Do not infer the slice offset from a stale report;
recompute it from the current inventory first:

```bash
uv run python - <<'PY'
import json
from pathlib import Path

inventory = Path("artifacts/system-corpus/all-pdfs-collect-pass-v3/inventory.jsonl")
rows = [json.loads(line) for line in inventory.read_text().splitlines() if line.strip()]
indices = [i for i, row in enumerate(rows) if "/Projects/pdf_editor/" in row["path"]]
print({"start": min(indices), "limit": len(indices), "paths": [rows[i]["path"] for i in indices[:5]]})
PY
```

## How to interpret receipts

- `inventory_count` proves discovery only.
- `readable_count` and `unreadable_count` describe structural access, not
  semantic quality.
- `analysis_count` proves that the detector executed for that slice.
- `logical_fields` are proposals. Native widgets are authoritative; inferred
  vector, OCR, CV, signature, photo, and composite targets remain review-bound.
- `raster_deferred` means a text-poor document was deliberately not sent
  through the expensive raster lane. It is an explicit unknown, not a negative.
- `analysis_errors` are preserved failure evidence and must be investigated or
  excluded with a documented reason before a release claim.
- Contact sheets are visual navigation and regression evidence, not a recall
  metric. A field can be semantically missed without any box being drawn.

## Review and training gate

For every adopted real document, create or update a label record through the
canonical label repository. The reviewer must be able to accept, reject, move,
resize, rename, group, or manually add a target. Empty signature slots and
observed signature ink are separate records: the former is a missing expected
slot, while the latter is a review-only audit observation until a user chooses
an actual signature action.

Promote a model only after a document-disjoint benchmark demonstrates an
improvement over the deterministic baseline on recall, type accuracy, label
association, duplicate suppression, false positives, and abstention risk. FUNSD
and DocLayNet can help pretrain or calibrate representations, but they do not
constitute fillable-field gold labels.

## Current evidence and next bounded unit

The 2026-09-10 collection pass inventoried 22,426 PDFs, including 33 files in
the downloaded dataset path. The first two 500-document slices have been
executed and visually rendered. They are useful coverage evidence, not a claim
that all 22,426 documents have perfect field recall. The next bounded unit is
the `pdf_editor` family pass followed by a raster-enabled slice and human review
of missed or suspicious targets.

For full-corpus runs, use `--max-analysis-bytes` as a declared resource budget.
An oversized file remains in `inventory.jsonl` and receives a transparent
`size_bytes>...` detector skip. This was added after a 21 MB nine-page PDF
consumed several minutes inside recursive `pdfplumber` layout resolution.
