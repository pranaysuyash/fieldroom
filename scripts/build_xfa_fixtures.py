"""Author deterministic static-XFA and dynamic-XFA fixture PDFs.

Implements the fixture step of docs/exploration/2026-10-24-static-xfa-fixture-design.md.
Both PDFs are synthetic: one page, two AcroForm text fields and one checkbox
whose widgets mirror a minimal XDP packet set (template, datasets, config).

- ``static-xfa.pdf``: no ``/NeedsRendering``, config without ``dynamicRender``,
  fixed-position template. Classification candidate: static.
- ``dynamic-xfa.pdf``: ``/Root /NeedsRendering true``, ``dynamicRender`` set to
  ``required``, and a flowing ``layout="tb"`` subform. Must stay quarantined.

Output defaults to a scratch directory under the system temp dir (never
data/samples or artifacts/). Output is byte-reproducible: reportlab runs with
``invariant=1`` and pypdf writes no random trailer ID.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DecodedStreamObject,
    NameObject,
    TextStringObject,
)
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

STATIC_NAME = "static-xfa.pdf"
DYNAMIC_NAME = "dynamic-xfa.pdf"

# (name, kind, x, y, width, height, value)
FIELDS = (
    ("full_name", "text", 170, 694, 220, 22, "Ada Example"),
    ("city", "text", 170, 654, 220, 22, "Springfield"),
    ("agree", "check", 170, 618, 14, 14, None),
)

_XDP_NS = "http://ns.adobe.com/xdp/"


def _template_packet(*, dynamic: bool) -> str:
    layout = "tb" if dynamic else "position"
    return (
        '<template xmlns="http://www.xfa.org/schema/xfa-template/3.3/">'
        f'<subform name="form1" layout="{layout}">'
        '<pageSet><pageArea name="Page1"><contentArea x="0.25in" y="0.25in" w="8in" h="10.5in"/></pageArea></pageSet>'
        '<field name="full_name"><ui><textEdit/></ui></field>'
        '<field name="city"><ui><textEdit/></ui></field>'
        '<field name="agree"><ui><checkButton/></ui></field>'
        "</subform></template>"
    )


def _datasets_packet() -> str:
    return (
        '<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">'
        '<xfa:data><form1><full_name>Ada Example</full_name><city>Springfield</city>'
        "<agree>0</agree></form1></xfa:data></xfa:datasets>"
    )


def _config_packet(*, dynamic: bool) -> str:
    # Static fixture omits dynamicRender entirely (the note's positive case).
    common = "<common><dynamicRender>required</dynamicRender></common>" if dynamic else "<common/>"
    return f'<config xmlns="http://www.xfa.org/schema/xci/3.0/"><agent name="designer">{common}</agent></config>'


def build_xdp(*, dynamic: bool) -> str:
    """Return the full XDP document for the requested variant."""
    return (
        f'<xdp:xdp xmlns:xdp="{_XDP_NS}">'
        f"{_config_packet(dynamic=dynamic)}{_template_packet(dynamic=dynamic)}{_datasets_packet()}"
        "</xdp:xdp>"
    )


def _base_pdf_bytes() -> bytes:
    buffer = io.BytesIO()
    canvas_obj = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    canvas_obj.setFont("Helvetica", 11)
    canvas_obj.drawString(60, 700, "Full name:")
    canvas_obj.drawString(60, 660, "City:")
    canvas_obj.drawString(60, 622, "Agree:")
    form = canvas_obj.acroForm
    for name, kind, x, y, width, height, value in FIELDS:
        if kind == "text":
            form.textfield(name=name, x=x, y=y, width=width, height=height, value=value or "",
                           borderStyle="solid", forceBorder=True)
        else:
            form.checkbox(name=name, x=x, y=y, size=width, checked=False, borderStyle="solid", forceBorder=True)
    canvas_obj.save()
    return buffer.getvalue()


def build_fixture_bytes(*, dynamic: bool) -> bytes:
    """Build one fixture PDF in memory; identical input yields identical bytes."""
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(_base_pdf_bytes())))
    xdp = build_xdp(dynamic=dynamic)
    packets = ArrayObject()
    for label, start, end in _split_packets(xdp):
        stream = DecodedStreamObject()
        stream.set_data(xdp[start:end].encode("utf-8"))
        packets.append(TextStringObject(label))
        packets.append(writer._add_object(stream))
    acroform = writer._root_object["/AcroForm"]
    acroform[NameObject("/XFA")] = packets
    if dynamic:
        writer._root_object[NameObject("/NeedsRendering")] = BooleanObject(True)
    writer.add_metadata({"/Title": "xfa-dynamic-fixture" if dynamic else "xfa-static-fixture"})
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _split_packets(xdp: str):
    """Yield (packet label, start, end) offsets for the top-level XDP children."""
    for label, tag in (("config", "<config"), ("template", "<template"), ("datasets", "<xfa:datasets")):
        start = xdp.index(tag)
        close = {"config": "</config>", "template": "</template>", "datasets": "</xfa:datasets>"}[label]
        end = xdp.index(close) + len(close)
        yield label, start, end


def build_fixtures(output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {"static": output_dir / STATIC_NAME, "dynamic": output_dir / DYNAMIC_NAME}
    for variant, path in paths.items():
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing fixture: {path}")
        path.write_bytes(build_fixture_bytes(dynamic=variant == "dynamic"))
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Target directory (default: a new temp directory). Existing files are never overwritten.")
    args = parser.parse_args(argv)
    output_dir = args.output_dir or Path(tempfile.mkdtemp(prefix="ffl-xfa-fixtures-"))
    paths = build_fixtures(output_dir)
    print(json.dumps({
        variant: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for variant, path in paths.items()
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
