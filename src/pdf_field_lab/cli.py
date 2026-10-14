"""Command-line interface for inspect, analyze, and export."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analysis import analyze
from .export_pdf import export_editable
from .fill_pdf import fill_editable, load_values
from .profiles.form6 import form6_fields


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect and reconstruct editable PDF form regions")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze_parser = sub.add_parser("analyze")
    analyze_parser.add_argument("input", type=Path)
    analyze_parser.add_argument("--json", type=Path, required=True)
    analyze_parser.add_argument("--run-cv", action="store_true")
    analyze_parser.add_argument("--run-ocr", action="store_true")
    export_parser = sub.add_parser("export")
    export_parser.add_argument("input", type=Path)
    export_parser.add_argument("--pdf", type=Path, required=True)
    export_parser.add_argument("--json", type=Path, required=True)
    fill_parser = sub.add_parser("fill")
    fill_parser.add_argument("template", type=Path)
    fill_parser.add_argument("data", type=Path, help="JSON object keyed by logical field ID")
    fill_parser.add_argument("--pdf", type=Path, required=True)
    fill_parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args(argv)

    input_path = args.input if args.command in {"analyze", "export"} else args.template
    report = analyze(input_path, run_cv=getattr(args, "run_cv", False),
                     run_ocr=getattr(args, "run_ocr", False))
    if args.command == "analyze":
        _write_json(args.json, report.as_dict())
        print(json.dumps({"logical_fields": len(report.logical_fields),
                          "vector_candidates": len(report.vector_candidates),
                          "native_fields": len(report.input.native_fields),
                          "output": str(args.json)}, indent=2))
        return 0

    if args.command == "fill":
        profile = report.logical_fields
        # Exported Form-6 templates have a changed file hash. Recover the
        # explicit profile by its stable generated namespace until profile
        # provenance is stamped into the PDF catalog.
        if (any(str(item.get("name", "")).startswith("F6-")
                for item in (report.input.native_fields or []))
                and all(field.editable_strategy == "native" for field in profile)):
            # Generated Form-6 widget names include composite suffixes such as
            # F6-02_number. Recover the reviewed logical profile instead of
            # exposing those implementation-level widget names to the CLI.
            profile = form6_fields()
        result = fill_editable(args.template, args.pdf, profile, load_values(args.data))
        _write_json(args.json, {"analysis": report.as_dict(), "fill": result})
        print(json.dumps(result, indent=2))
        return 0

    result = export_editable(args.input, args.pdf, report.logical_fields)
    result["analysis_json"] = str(args.json)
    _write_json(args.json, {"analysis": report.as_dict(), "export": result})
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
