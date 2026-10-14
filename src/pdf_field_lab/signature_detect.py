"""Conservative review-only detection of expected and occupied signature slots."""

from __future__ import annotations

from pathlib import Path

from .models import BBox, Evidence, SignatureObservation


_ROLE_WORDS = {
    "partner", "director", "trustee", "proprietor", "secretary", "chairperson",
    "authorized", "authorised", "signatory", "accountant", "deponent",
}


def _words_for_signature_block(page) -> list[dict]:
    words = []
    for item in page.get_text("words"):
        x0, y0, x1, y1, text, block, line, word = item
        text = str(text).strip()
        if text:
            words.append({"x0": float(x0), "y0": float(y0), "x1": float(x1),
                          "y1": float(y1), "text": text, "block": block,
                          "line": line, "word": word})
    return words


def _same_line_name(words: list[dict], role_word: dict) -> str | None:
    candidates = [item for item in words
                  if item["block"] == role_word["block"]
                  and item["y1"] <= role_word["y0"] + 1.5
                  and role_word["y0"] - item["y1"] <= 18
                  and item["x0"] >= role_word["x0"] - 7
                  and item["x0"] <= role_word["x0"] + 105]
    if not candidates:
        return None
    name_line = min(candidates, key=lambda item: (role_word["y0"] - item["y1"], item["line"]))
    selected = [item for item in candidates if item["line"] == name_line["line"]]
    selected.sort(key=lambda item: item["x0"])
    return " ".join(item["text"] for item in selected) or None


def _role_slots(page) -> list[dict]:
    words = _words_for_signature_block(page)
    roles = [item for item in words
             if item["text"].lower().rstrip(":") in _ROLE_WORDS
             and item["y0"] >= page.rect.height * 0.55]
    if len(roles) < 2:
        return []
    slots = []
    for role_word in roles:
        signer = _same_line_name(words, role_word)
        if not signer:
            continue
        name_words = [item for item in words
                      if item["block"] == role_word["block"]
                      and item["text"] in signer.split()
                      and item["y0"] < role_word["y0"]]
        name_y = min((item["y0"] for item in name_words), default=role_word["y0"] - 10)
        x = max(0.0, role_word["x0"] - 5.0)
        slots.append({
            "signer": signer,
            "role": role_word["text"].rstrip(":").title(),
            "bbox": BBox(x, max(0.0, name_y - 40.0), 105.0, 38.0),
        })
    return slots if len(slots) >= 2 else []


def _image_rects(page) -> list[tuple[str, BBox]]:
    seen: set[tuple[str, int, int, int, int]] = set()
    rects = []
    for info in page.get_image_info(xrefs=True):
        rect = info["bbox"]
        bbox = BBox(float(rect[0]), float(rect[1]), float(rect[2] - rect[0]),
                    float(rect[3] - rect[1]))
        key = (str(info.get("xref", "")), round(bbox.x), round(bbox.y),
               round(bbox.width), round(bbox.height))
        if key in seen:
            continue
        seen.add(key)
        rects.append((str(info.get("xref", "")), bbox))
    return rects


def _intersection(first: BBox, second: BBox) -> float:
    x0 = max(first.x, second.x)
    y0 = max(first.y, second.y)
    x1 = min(first.x + first.width, second.x + second.width)
    y1 = min(first.y + first.height, second.y + second.height)
    area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    return area / (second.width * second.height) if second.width and second.height else 0.0


def detect_signature_observations(path: Path, *, dpi: int = 144) -> list[SignatureObservation]:
    """Find signer slots and classify their occupancy without creating fields.

    Printed name and role text is the expected-slot anchor. An embedded image
    or dark raster ink inside that bounded slot is occupancy evidence. Results
    remain review-only and abstain on pages without a multi-signer block.
    """
    import cv2
    import numpy as np
    import pymupdf

    document = pymupdf.open(str(path))
    observations: list[SignatureObservation] = []
    scale = dpi / 72.0
    try:
        for page_number, page in enumerate(document, 1):
            slots = _role_slots(page)
            if not slots:
                continue
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height, pixmap.width, pixmap.n)
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            image_rects = _image_rects(page)
            for slot_index, slot in enumerate(slots, 1):
                bbox = slot["bbox"]
                x0 = max(0, int(bbox.x * scale))
                y0 = max(0, int(bbox.y * scale))
                x1 = min(pixmap.width, int((bbox.x + bbox.width) * scale))
                y1 = min(pixmap.height, int((bbox.y + bbox.height) * scale))
                crop = gray[y0:y1, x0:x1]
                dark_ratio = float((crop < 190).mean()) if crop.size else 0.0
                embedded = [(xref, rect) for xref, rect in image_rects
                            if _intersection(rect, bbox) >= 0.30]
                source_refs = [f"image-xref:{xref}" for xref, _ in embedded if xref]
                if embedded:
                    status = "present"
                    confidence = 0.97
                    detail = "expected signer slot contains an embedded image object"
                elif dark_ratio >= 0.003:
                    status = "present"
                    confidence = min(0.86, 0.58 + dark_ratio * 2.0)
                    detail = f"expected signer slot contains raster ink; dark-pixel ratio={dark_ratio:.4f}"
                elif dark_ratio <= 0.0005:
                    status = "missing"
                    confidence = 0.93
                    detail = "printed signer slot is empty in the rendered page"
                else:
                    status = "uncertain"
                    confidence = 0.55
                    detail = f"slot occupancy is ambiguous; dark-pixel ratio={dark_ratio:.4f}"
                observations.append(SignatureObservation(
                    id=f"signature-{page_number}-{slot_index:02d}", page=page_number,
                    signer=slot["signer"], role=slot["role"], bbox=bbox,
                    status=status, confidence=confidence,
                    evidence=[Evidence("raster_cv", confidence, detail)],
                    source_refs=source_refs,
                ))
    finally:
        document.close()
    return observations
