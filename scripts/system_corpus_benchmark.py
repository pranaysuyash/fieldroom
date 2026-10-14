"""Inventory and benchmark user-owned PDFs outside the downloaded datasets.

The receipt deliberately stores structural and detector summaries rather than
extracted text or field labels. Source PDFs remain in place and are never
copied or uploaded by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
import sys
from typing import Iterable

import fitz
from PIL import Image, ImageDraw, ImageFont

from pdf_field_lab.analysis import analyze


MAX_INSPECTION_PAGES = 80

try:
    fitz.TOOLS.mupdf_display_errors(False)
except AttributeError:
    pass

_HOME = Path.home()

DEFAULT_ROOTS = (
    _HOME / "Desktop",
    _HOME / "Documents",
    _HOME / "Downloads",
    _HOME / "Projects",
)

# These are corpus or generated families, not independent user-document
# evaluation data. They remain discoverable in the inventory with a reason.
EXCLUDED_MARKERS = (
    "/benchmark/",
    "/benchmark/datasets/",
    "/benchmark/results/",
    "/benchmarks/",
    "/Digitized_file_model_1/",
    "/corpus_global/",
    "/corpus_lob/",
    "/corpus_sweep",
    "/datasets/",
    "/node_modules/",
    "/.codex-test-tmp/",
    "/.venv/",
    "/.git/",
    "/pdf_form_field_lab/artifacts/",
)

CLASS_RULES = (
    ("identity", r"aadhaar|passport|pan\b|identity|voter|form6|form_?6"),
    ("form_or_agreement", r"form|application|consent|agreement|shareholder|authorization|aoa|moa"),
    ("financial_statement", r"financial|statement|balance|audit|itr|tax|gst|invoice|receipt|premium|repayment|sanction|loan"),
    ("travel_or_ticket", r"ticket|itinerary|flight|hotel|travel|singapore|cleartrip|air[_ ]india|spicejet"),
    ("scan_or_photo", r"docscan|scanner|whatsapp|image|scan|screenshot|photo"),
    ("resume_or_certificate", r"resume|cv\b|cover.?letter|certificate|completion|profile"),
    ("policy_or_legal", r"policy|insurance|legal|contract|soc|disaster|compliance"),
    ("long_text", r"book|ebook|guide|glossary|paper|report|manual|course|slides|learning"),
)


def _normalized_path(path: Path) -> str:
    return str(path.resolve()).replace(os.sep, "/")


def _read_manifest(path: Path) -> list[Path]:
    records: list[Path] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                candidate = Path(line)
                records.append(candidate if candidate.is_absolute() else path.parent / candidate)
            else:
                payloads = payload if isinstance(payload, list) else [payload]
                for item in payloads:
                    if isinstance(item, str):
                        selected = item
                    elif isinstance(item, dict):
                        selected = item.get("path") or item.get("file") or item.get("pdf")
                    else:
                        selected = None
                    if selected:
                        candidate = Path(selected)
                        records.append(candidate if candidate.is_absolute() else path.parent / candidate)
    seen: set[str] = set()
    ordered: list[Path] = []
    for candidate in records:
        normalized = _normalized_path(candidate)
        if normalized not in seen:
            seen.add(normalized)
            ordered.append(candidate)
    return ordered


def _is_excluded(
    path: Path,
    *,
    include_excluded_substrings: tuple[str, ...] = (),
    disable_default_exclusions: bool = False,
) -> str | None:
    if disable_default_exclusions:
        return None
    normalized = _normalized_path(path)
    include_paths = tuple(item for item in include_excluded_substrings if item)
    for include in include_paths:
        if include in normalized:
            return None
    for marker in EXCLUDED_MARKERS:
        if marker in normalized:
            return marker.strip("/")
    return None


def _iter_pdfs(roots: Iterable[Path]) -> Iterable[Path]:
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = [name for name in dirnames if name not in {".git", ".venv", "node_modules"}]
            for filename in filenames:
                if not filename.lower().endswith(".pdf"):
                    continue
                path = Path(directory) / filename
                key = _normalized_path(path)
                if key not in seen:
                    seen.add(key)
                    yield path


def _iter_candidates(roots: tuple[Path, ...], manifest_path: Path | None) -> list[Path]:
    if manifest_path is not None:
        return _read_manifest(manifest_path)
    return list(_iter_pdfs(roots))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _light_inventory(
    path: Path,
    *,
    include_excluded_substrings: tuple[str, ...] = (),
    disable_default_exclusions: bool = False,
) -> dict:
    try:
        with path.open("rb") as handle:
            header = handle.read(8)
    except Exception as exc:
        excluded_reason = _is_excluded(
            path,
            include_excluded_substrings=include_excluded_substrings,
            disable_default_exclusions=disable_default_exclusions,
        )
        return {
            "path": str(path),
            "source_bucket": _source_bucket(path),
            "category": _classify(path),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "extension": path.suffix.lower(),
            "pdf_header": "",
            "excluded_reason": excluded_reason,
            "inventory_only": bool(excluded_reason),
            "light_read_error": f"{type(exc).__name__}: {str(exc)[:240]}",
            "readable": False,
            "error_type": type(exc).__name__,
        }
    excluded_reason = _is_excluded(
        path,
        include_excluded_substrings=include_excluded_substrings,
        disable_default_exclusions=disable_default_exclusions,
    )
    return {
        "path": str(path),
        "source_bucket": _source_bucket(path),
        "category": _classify(path),
        "size_bytes": path.stat().st_size,
        "extension": path.suffix.lower(),
        "pdf_header": header.decode("latin-1", errors="replace"),
        "excluded_reason": excluded_reason,
        "inventory_only": bool(excluded_reason),
        "readable": None,
    }


def _classify(path: Path) -> str:
    name = path.name.lower()
    for category, pattern in CLASS_RULES:
        if re.search(pattern, name):
            return category
    normalized = _normalized_path(path).lower()
    if "/books/" in normalized or "/educational/" in normalized:
        return "long_text"
    if "/itr/" in normalized:
        return "financial_statement"
    return "other"


def _source_bucket(path: Path) -> str:
    normalized = _normalized_path(path)
    for bucket, name in (
        (str(_HOME / "Desktop") + "/", "Desktop"),
        (str(_HOME / "Documents") + "/", "Documents"),
        (str(_HOME / "Downloads") + "/", "Downloads"),
        (str(_HOME / "Projects") + "/", "Projects"),
    ):
        if normalized.startswith(bucket):
            return name
    return "other"


def _inspect(
    path: Path,
    *,
    include_excluded_substrings: tuple[str, ...] = (),
    disable_default_exclusions: bool = False,
) -> dict:
    excluded_reason = _is_excluded(
        path,
        include_excluded_substrings=include_excluded_substrings,
        disable_default_exclusions=disable_default_exclusions,
    )
    record = {
        "path": str(path),
        "source_bucket": _source_bucket(path),
        "category": _classify(path),
        "size_bytes": path.stat().st_size,
        "excluded_reason": excluded_reason,
    }
    if excluded_reason:
        # Dataset/corpus material is inventoried for coverage only. Avoid
        # hashing or parsing potentially huge training corpora during an
        # evaluation run, and never let them enter detector scoring.
        record.update({
            "readable": None,
            "inventory_only": True,
            "sha256": None,
        })
        return record
    record["sha256"] = _sha256(path)
    try:
        document = fitz.open(path)
        page_count = len(document)
        if page_count > MAX_INSPECTION_PAGES:
            record.update({
                "readable": True,
                "structural_only": True,
                "structural_only_reason": f"page_count>{MAX_INSPECTION_PAGES}",
                "pages": page_count,
                "page_sizes": [],
                "encrypted": bool(document.is_encrypted),
                "text_chars_by_page": [],
                "text_chars": None,
                "image_pages": None,
                "native_widgets": None,
                "annotations": None,
                "image_only": None,
                "text_poor_pages": None,
            })
            document.close()
            return record
        text_chars: list[int] = []
        image_pages = 0
        native_widgets = 0
        annotations = 0
        for page in document:
            try:
                text_chars.append(len(page.get_text("text")))
                if page.get_images(full=True):
                    image_pages += 1
                widgets = page.widgets()
                if widgets:
                    native_widgets += sum(1 for _ in widgets)
                annots = page.annots()
                if annots:
                    annotations += sum(1 for _ in annots)
            except Exception as exc:
                # Preserve a structural record even when one damaged page
                # cannot be decoded. The file remains a failed candidate.
                record.update({
                    "readable": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:240],
                    "failed_page": page.number + 1,
                })
                document.close()
                return record
        record.update({
            "readable": True,
            "pages": len(document),
            "page_sizes": [
                {"width": round(page.rect.width, 2), "height": round(page.rect.height, 2)}
                for page in document
            ],
            "encrypted": bool(document.is_encrypted),
            "text_chars_by_page": text_chars,
            "text_chars": sum(text_chars),
            "image_pages": image_pages,
            "native_widgets": native_widgets,
            "annotations": annotations,
            "image_only": bool(text_chars) and not any(text_chars) and image_pages > 0,
            "text_poor_pages": sum(chars < 100 for chars in text_chars),
        })
        document.close()
    except Exception as exc:  # Inventory must continue past malformed PDFs.
        record.update({
            "readable": False,
            "error_type": type(exc).__name__,
            "error": str(exc)[:240],
        })
    return record


def _stratified_sample(records: list[dict], max_per_category: int) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in records:
        if record.get("excluded_reason") or record.get("readable") is False:
            continue
        groups[(record["source_bucket"], record["category"])].append(record)
    chosen: list[dict] = []
    for key in sorted(groups):
        chosen.extend(sorted(groups[key], key=lambda item: item["path"])[:max_per_category])
    return chosen


def _detector_summary(
    record: dict,
    *,
    run_raster: bool = False,
    max_analysis_bytes: int = 0,
) -> dict:
    if max_analysis_bytes > 0 and record.get("size_bytes", 0) > max_analysis_bytes:
        return {
            "analysis_error": None,
            "skipped_reason": f"size_bytes>{max_analysis_bytes}",
            "logical_field_count": None,
            "logical_kinds": {},
            "editable_strategies": {},
            "vector_candidate_count": None,
            "native_field_count": None,
            "warnings": ["Detector skipped oversized input at benchmark boundary."],
            "backend_status": {},
            "page_one_targets": [],
        }
    if record.get("structural_only"):
        return {
            "analysis_error": None,
            "skipped_reason": record.get("structural_only_reason"),
            "logical_field_count": None,
            "logical_kinds": {},
            "editable_strategies": {},
            "vector_candidate_count": None,
            "native_field_count": None,
            "warnings": [],
            "backend_status": {},
            "page_one_targets": [],
        }
    if record.get("readable") is False:
        return {
            "analysis_error": record.get("error_type", "unreadable"),
            "skipped_reason": "structural_inventory_failed",
            "logical_field_count": None,
            "logical_kinds": {},
            "editable_strategies": {},
            "vector_candidate_count": None,
            "native_field_count": None,
            "warnings": [],
            "backend_status": {},
            "page_one_targets": [],
        }
    try:
        # Raster/OCR remains opt-in and bounded. The default system pass is
        # vector/native only; selected slices can explicitly exercise the
        # slower CV/OCR lane without making the all-system inventory opaque.
        report = analyze(Path(record["path"]), run_raster=run_raster)
        kinds = Counter(field.kind for field in report.logical_fields)
        strategies = Counter(field.editable_strategy for field in report.logical_fields)
        backend_status = dict(report.backend_status)
        if record.get("text_poor_pages") and not run_raster:
            backend_status["raster_execution"] = "deferred-bounded-system-pass"
        return {
            "analysis_error": None,
            "skipped_reason": None,
            "logical_field_count": len(report.logical_fields),
            "logical_kinds": dict(sorted(kinds.items())),
            "editable_strategies": dict(sorted(strategies.items())),
            "vector_candidate_count": len(report.vector_candidates),
            "native_field_count": len(report.input.native_fields),
            "warnings": report.warnings,
            "backend_status": backend_status,
            "page_one_targets": [
                {
                    "page": field.page,
                    "kind": field.kind,
                    "bbox": field.bbox.as_dict(),
                    "confidence": field.confidence,
                    "review_required": field.review_required,
                }
                for field in report.logical_fields
                if field.page == 1
            ],
        }
    except Exception as exc:
        return {
            "analysis_error": f"{type(exc).__name__}: {str(exc)[:240]}",
            "skipped_reason": None,
            "logical_field_count": None,
            "logical_kinds": {},
            "editable_strategies": {},
            "vector_candidate_count": None,
            "native_field_count": None,
            "warnings": [],
            "backend_status": {},
            "page_one_targets": [],
        }


def _render_contact_sheet(records: list[dict], output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    cards: list[tuple[dict, Image.Image]] = []
    for record in records:
        try:
            document = fitz.open(record["path"])
            if not len(document):
                continue
            page = document[0]
            matrix = fitz.Matrix(1.15, 1.15)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            image.thumbnail((360, 480))
            overlay = ImageDraw.Draw(image)
            colors = {
                "text": "#176b87",
                "date": "#8b5cf6",
                "choice": "#d97706",
                "image": "#059669",
                "signature": "#dc2626",
                "composite": "#7c3aed",
            }
            page_width, page_height = page.rect.width, page.rect.height
            targets = record.get("detector", {}).get("page_one_targets", [])
            for target in targets:
                bbox = target["bbox"]
                x0 = bbox["x"] / page_width * image.width
                y0 = bbox["y"] / page_height * image.height
                x1 = (bbox["x"] + bbox["width"]) / page_width * image.width
                y1 = (bbox["y"] + bbox["height"]) / page_height * image.height
                overlay.rectangle((x0, y0, x1, y1), outline=colors.get(target["kind"], "#111827"), width=2)
            cards.append((record, image.copy()))
            document.close()
        except Exception:
            continue

    if not cards:
        return {"rendered_count": 0, "contact_sheet": None}

    columns = 4
    card_width, card_height = 400, 550
    rows = (len(cards) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * card_width, rows * card_height), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    rendered = []
    for index, (record, image) in enumerate(cards):
        x = (index % columns) * card_width
        y = (index // columns) * card_height
        sheet.paste(image, (x + (card_width - image.width) // 2, y + 8))
        target_count = len(record.get("detector", {}).get("page_one_targets", []))
        caption = f"{record['source_bucket']} / {record['category']} / targets={target_count}\n"
        caption += Path(record["path"]).name[:54]
        draw.text((x + 8, y + 495), caption, fill="black", font=font)
        rendered.append({"path": record["path"], "category": record["category"]})
    sheet_path = output / "contact-sheet.png"
    sheet.save(sheet_path)
    return {"rendered_count": len(rendered), "contact_sheet": str(sheet_path), "pages": rendered}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", type=Path, dest="roots")
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=None,
        help="Optional jsonl/plain list of PDF paths to use as input candidates.",
    )
    parser.add_argument("--max-per-category", type=int, default=6)
    parser.add_argument("--render-count", type=int, default=24)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/system-corpus"))
    parser.add_argument("--disable-default-exclusions", action="store_true")
    parser.add_argument(
        "--include-excluded-substring",
        action="append",
        default=[],
        metavar="SUBSTRING",
        help="Force include paths that still match default exclusion markers.",
    )
    parser.add_argument("--analyze-all", action="store_true")
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Run full inventory and skip detector analysis.",
    )
    parser.add_argument("--max-analysis-records", type=int, default=0)
    parser.add_argument("--manifest-start", type=int, default=0)
    parser.add_argument("--manifest-limit", type=int, default=0)
    parser.add_argument(
        "--run-raster",
        action="store_true",
        help="Run the bounded CV/OCR semantic lane for this analysis slice.",
    )
    parser.add_argument(
        "--max-analysis-bytes",
        type=int,
        default=0,
        help="Skip detector analysis above this file size while retaining inventory metadata.",
    )
    parser.add_argument("--progress-every", type=int, default=50)
    args = parser.parse_args()
    roots = tuple(args.roots or DEFAULT_ROOTS)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    include_substrings = tuple(args.include_excluded_substring)
    manifest_start = max(0, args.manifest_start)
    manifest_limit = max(0, args.manifest_limit)
    candidate_paths = sorted(_iter_candidates(roots, args.manifest_path), key=str)
    if manifest_start:
        candidate_paths = candidate_paths[manifest_start:]
    if manifest_limit > 0:
        candidate_paths = candidate_paths[:manifest_limit]

    # Stage one is intentionally lightweight across the complete local corpus.
    # Deep parsing is reserved for the deterministic stratified sample.
    inventory = [
        _light_inventory(
            path,
            include_excluded_substrings=include_substrings,
            disable_default_exclusions=args.disable_default_exclusions,
        )
        for path in candidate_paths
    ]

    candidates = [record for record in inventory if not record.get("excluded_reason")]
    if args.collect_only:
        analysis_records = []
        benchmark_records = []
    else:
        if args.analyze_all:
            analysis_records = candidates
        else:
            analysis_records = _stratified_sample(candidates, args.max_per_category)
        if args.max_analysis_records > 0:
            analysis_records = analysis_records[: args.max_analysis_records]
        benchmark_records = []
        for index, record in enumerate(analysis_records, start=1):
            measured = dict(record)
            measured.update(_inspect(
                Path(record["path"]),
                include_excluded_substrings=include_substrings,
                disable_default_exclusions=args.disable_default_exclusions,
            ))
            measured["detector"] = _detector_summary(
                measured,
                run_raster=args.run_raster,
                max_analysis_bytes=max(0, args.max_analysis_bytes),
            )
            benchmark_records.append(measured)
            if args.progress_every and index % args.progress_every == 0:
                print(
                    f"[analysis] processed {index}/{len(analysis_records)} candidates",
                    file=sys.stderr,
                    flush=True,
                )

    detail_by_path = {record["path"]: record for record in benchmark_records}
    for index, record in enumerate(inventory):
        if record["path"] in detail_by_path:
            inventory[index] = detail_by_path[record["path"]]
    inventory_path = output_dir / "inventory.jsonl"
    with inventory_path.open("w", encoding="utf-8") as handle:
        for record in inventory:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    # Render the measured records, not the pre-analysis inventory records. The
    # detector overlays live under record["detector"], so using analysis_records
    # here would silently produce target-free contact sheets even when analysis
    # found native or inferred fields.
    visual_records = benchmark_records[:args.render_count] if not args.collect_only else []
    visual = _render_contact_sheet(visual_records, output_dir / "visual")
    summary = {
        "schema": "pdf-field-lab.system-corpus-benchmark.v1",
        "roots": [str(root) for root in roots],
        "manifest_path": str(args.manifest_path) if args.manifest_path else None,
        "manifest_start": manifest_start,
        "manifest_limit": manifest_limit,
        "candidates_requested": len(candidate_paths),
        "exclusion_markers": list(EXCLUDED_MARKERS),
        "default_exclusions_disabled": args.disable_default_exclusions,
        "included_exclusion_substrings": list(include_substrings),
        "collect_only": args.collect_only,
        "raster_requested": args.run_raster,
        "max_analysis_bytes": max(0, args.max_analysis_bytes),
        "inventory_count": len(inventory),
        "analysis_count": len(analysis_records),
        "readable_count": sum(item.get("readable") is True for item in inventory),
        "unreadable_count": sum(item.get("readable") is False for item in inventory),
        "readability_unknown_count": sum(item.get("readable") is None for item in inventory),
        "excluded_count": sum(bool(item.get("excluded_reason")) for item in inventory),
        "inventory_only_count": sum(bool(item.get("inventory_only")) for item in inventory),
        "evaluation_candidate_count": len(candidates),
        "sample_count": len(benchmark_records),
        "inventory_by_bucket": dict(sorted(Counter(item["source_bucket"] for item in inventory).items())),
        "inventory_by_category": dict(sorted(Counter(item["category"] for item in inventory).items())),
        "candidate_by_bucket": dict(sorted(Counter(item["source_bucket"] for item in candidates).items())),
        "candidate_by_category": dict(sorted(Counter(item["category"] for item in candidates).items())),
        "detector_totals": {
            "logical_fields": sum(item["detector"]["logical_field_count"] or 0 for item in benchmark_records),
            "vector_candidates": sum(item["detector"]["vector_candidate_count"] or 0 for item in benchmark_records),
            "native_fields": sum(item["detector"]["native_field_count"] or 0 for item in benchmark_records),
            "analysis_errors": sum(bool(item["detector"]["analysis_error"]) for item in benchmark_records),
            "raster_deferred": sum(
                item["detector"]["backend_status"].get("raster_execution")
                == "deferred-bounded-system-pass"
                for item in benchmark_records
            ),
            "logical_kinds": dict(sorted(Counter(
                kind
                for item in benchmark_records
                for kind, count in item["detector"].get("logical_kinds", {}).items()
                for _ in range(count)
            ).items())),
            "editable_strategies": dict(sorted(Counter(
                strategy
                for item in benchmark_records
                for strategy, count in item["detector"].get("editable_strategies", {}).items()
                for _ in range(count)
            ).items())),
        },
        "analysis_candidates_count": len(analysis_records),
        "analysis_skipped_due_to_collect_only": args.collect_only,
        "visual": visual,
        "inventory_path": str(inventory_path),
        "benchmark_path": str(output_dir / "benchmark.json"),
        "privacy_note": "No extracted page text or field labels are stored in this receipt.",
    }
    benchmark_path = output_dir / "benchmark.json"
    benchmark_path.write_text(json.dumps(benchmark_records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
