"""Reviewed semantic profile for the supplied Election Commission Form-6.

The profile is a bootstrap for this exact template fingerprint. It is not a
claim that arbitrary Indian government forms share these coordinates. Every
entry remains review-required, including high-confidence text boxes, because
the source is a flat PDF and the profile is a semantic prior.
"""

from __future__ import annotations

from pathlib import Path

from ..models import BBox, Evidence, FieldSpec

FORM6_SHA256 = "2cf1421343c22676f15eff0ec6f31a4df6e7f7975dc0f3d88d2b29a1dcc79d34"


def _f(fid: str, page: int, label: str, kind: str, x: float, y: float, w: float, h: float,
       strategy: str = "acroform-text", *, required: bool = False,
       conditional_on: str | None = None, options: list[dict] | None = None,
       confidence: float = 0.92, notes: list[str] | None = None,
       input_mode: str = "single", max_length: int | None = None,
       grid_rows: list[dict] | None = None) -> FieldSpec:
    return FieldSpec(
        id=fid, page=page, label=label, kind=kind, bbox=BBox(x, y, w, h),
        editable_strategy=strategy, review_required=True, required=required,
        conditional_on=conditional_on, options=options or [], confidence=confidence,
        evidence=[Evidence("template_profile", confidence, "reviewed Form-6 semantic profile")],
        notes=notes or [], input_mode=input_mode, max_length=max_length,
        grid_rows=grid_rows or [],
    )


def _choice_options(items: list[tuple[str, float, float, float, float]]) -> list[dict]:
    return [{"value": value, "label": value, "bbox": BBox(x, y, w, h).as_dict()}
            for value, x, y, w, h in items]


def form6_fields() -> list[FieldSpec]:
    # Bboxes are top-origin PDF points. They intentionally cover the writable
    # area, not the printed label, so they can be directly overlaid as widgets.
    return [
        _f("F6-01", 1, "Office form number", "text", 505, 56, 76, 14, required=False),
        _f("F6-02", 1, "Assembly constituency number and name", "composite", 304, 128, 286, 25,
           options=[{"value": "number", "label": "number", "bbox": BBox(304, 128, 26, 25).as_dict()},
                    {"value": "name", "label": "name", "bbox": BBox(390, 128, 200, 25).as_dict()}]),
        _f("F6-03", 1, "Parliamentary constituency number and name", "composite", 304, 142, 286, 26,
           options=[{"value": "number", "label": "number", "bbox": BBox(304, 142, 26, 26).as_dict()},
                    {"value": "name", "label": "name", "bbox": BBox(390, 142, 200, 26).as_dict()}],
           conditional_on="union_territory_without_legislative_assembly"),
        _f("F6-04", 1, "Recent unsigned passport-size photograph", "image", 478, 205, 101, 183,
           strategy="image-placement", notes=["Preserve aspect ratio; reject non-image input."]),
        _f("F6-05", 1, "Official-language given name", "text", 29, 209, 461, 29,
           notes=["Type the full name once; the export adapter distributes characters across the printed boxes.",
                  "Unicode/script validation is required.",
                  "The printed grid has an upper 14-cell row followed by a lower 28-cell row."],
           input_mode="character-grid", max_length=35,
           grid_rows=[{"bbox": BBox(243, 209, 246, 14).as_dict(), "cell_count": 14},
                      {"bbox": BBox(29, 223, 461, 14).as_dict(), "cell_count": 28}]),
        _f("F6-06", 1, "Official-language surname", "text", 114, 251, 359, 29,
           notes=["Type the full surname once; the export adapter distributes characters across the printed boxes."],
           input_mode="character-grid", max_length=28),
        _f("F6-07", 1, "English given name in block letters", "text", 30, 307, 443, 28,
           notes=["Type the full name once; the export adapter distributes characters across the printed boxes."],
           input_mode="character-grid", max_length=35,
           grid_rows=[{"bbox": BBox(244, 307, 229, 14).as_dict(), "cell_count": 13},
                      {"bbox": BBox(31, 321, 442, 14).as_dict(), "cell_count": 25}]),
        _f("F6-08", 1, "English surname in block letters", "text", 114, 340, 359, 29,
           notes=["Type the full surname once; the export adapter distributes characters across the printed boxes."],
           input_mode="character-grid", max_length=28),
        _f("F6-09", 1, "Relative type", "choice", 18, 388, 430, 49, "acroform-radio",
           options=_choice_options([("father", 32, 389, 22, 18), ("mother", 130, 389, 22, 18),
                                    ("husband", 248, 389, 22, 18), ("wife", 364, 389, 22, 18),
                                    ("legal_guardian_or_guru", 32, 410, 22, 18)])),
        _f("F6-10", 1, "Relative name in official language", "text", 17, 430, 560, 17),
        _f("F6-11", 1, "Relative name in English in block letters", "text", 17, 468, 560, 17),
        _f("F6-12", 1, "Mobile number", "text", 301, 489, 195, 28,
           notes=["Type the full number once; the export adapter distributes digits across both printed rows."],
           input_mode="character-grid", max_length=20,
           grid_rows=[{"bbox": BBox(301, 489, 195, 14).as_dict(), "cell_count": 10},
                      {"bbox": BBox(301, 503, 195, 14).as_dict(), "cell_count": 10}]),
        _f("F6-13", 1, "Email ID", "text", 250, 515, 250, 18),
        _f("F6-14", 1, "Aadhaar choice and number", "composite", 45, 559, 430, 38,
           strategy="acroform-choice-and-text", options=_choice_options(
               [("aadhaar_checkbox", 50, 560, 22, 18), ("no_aadhaar", 50, 582, 22, 18),
                ("aadhaar_digits", 205, 560, 233, 14)])),
        _f("F6-15", 1, "Gender", "choice", 1, 605, 410, 24, "acroform-radio",
           options=_choice_options([("male", 130, 605, 22, 20), ("female", 225, 605, 22, 20),
                                    ("third_gender", 320, 605, 22, 20)])),
        _f("F6-16", 1, "Date of birth", "date", 165, 625, 190, 24,
           notes=["Expected display format DD/MM/YYYY."]),
        _f("F6-17", 1, "Date-of-birth proof choice", "choice", 30, 647, 420, 105, "acroform-radio",
           options=_choice_options([("birth_certificate", 50, 674, 20, 18), ("aadhaar_card", 230, 690, 20, 18),
                                    ("pan_card", 230, 714, 20, 18), ("driving_license", 382, 714, 20, 18),
                                    ("class_x_or_xii", 50, 738, 20, 18), ("indian_passport", 382, 738, 20, 18)])),
        _f("F6-18", 1, "Other date-of-birth document", "text", 340, 757, 220, 16,
           conditional_on="F6-17=other"),
        _f("F6-19", 1, "Present ordinary-residence address", "composite", 85, 770, 505, 60,
           strategy="acroform-multiline", options=[
               {"value": "house", "label": "House/building/apartment", "bbox": BBox(88, 770, 250, 15).as_dict()},
               {"value": "street", "label": "Street/area/locality", "bbox": BBox(337, 770, 250, 15).as_dict()},
               {"value": "town", "label": "Town/village", "bbox": BBox(88, 785, 250, 15).as_dict()},
               {"value": "post_office", "label": "Post office", "bbox": BBox(337, 785, 250, 15).as_dict()},
               {"value": "pin_code", "label": "PIN code", "bbox": BBox(88, 800, 250, 15).as_dict()},
               {"value": "tehsil", "label": "Tehsil/taluqa/mandal", "bbox": BBox(337, 800, 250, 15).as_dict()},
               {"value": "district", "label": "District", "bbox": BBox(88, 815, 250, 14).as_dict()},
               {"value": "state_ut", "label": "State/UT", "bbox": BBox(337, 815, 250, 14).as_dict()},
           ], notes=["Eight logical table cells: house, street, town, post office, PIN, tehsil, district, state/UT."]),
        _f("F6-20", 2, "Residence proof choice", "choice", 49, 92, 510, 70, "acroform-radio",
           options=_choice_options([("utility_bill", 50, 93, 20, 17), ("aadhaar_card", 457, 93, 20, 17),
                                    ("bank_or_post_office_passbook", 50, 110, 20, 17), ("indian_passport", 457, 110, 20, 17),
                                    ("land_records", 50, 127, 20, 17), ("registered_rent_lease", 50, 143, 20, 17),
                                    ("registered_sale_deed", 391, 143, 20, 17)])),
        _f("F6-21", 2, "Other residence document", "text", 236, 190, 340, 17,
           conditional_on="F6-20=other"),
        _f("F6-22", 2, "Disability category", "choice", 260, 214, 220, 22, "acroform-checkbox-group",
           options=_choice_options([("locomotive", 262, 215, 20, 19), ("visual", 391, 215, 20, 19),
                                    ("deaf_and_dumb", 456, 215, 20, 19)])),
        _f("F6-23", 2, "Other disability description", "text", 183, 232, 275, 17),
        _f("F6-24", 2, "Disability percentage and certificate attached", "composite", 125, 250, 330, 25,
           strategy="acroform-choice-and-text", options=_choice_options([("percentage", 125, 250, 18, 18),
                                                                            ("certificate_yes", 360, 250, 20, 20),
                                                                            ("certificate_no", 417, 250, 20, 20)])),
        _f("F6-25", 2, "Existing family member name, relationship, and EPIC number", "composite", 134, 296, 458, 36,
           strategy="acroform-multiline", options=[
               {"value": "name", "label": "Family member name", "bbox": BBox(134, 296, 186, 15).as_dict()},
               {"value": "relationship", "label": "Relationship", "bbox": BBox(454, 296, 137, 15).as_dict()},
               {"value": "epic", "label": "EPIC number", "bbox": BBox(134, 316, 186, 15).as_dict()},
           ]),
        _f("F6-26", 2, "Declaration place of birth", "composite", 50, 377, 440, 34, options=[
            {"value": "village_or_town", "label": "Village/town", "bbox": BBox(310, 377, 160, 17).as_dict()},
            {"value": "district", "label": "District", "bbox": BBox(50, 393, 210, 17).as_dict()},
            {"value": "state_ut", "label": "State/UT", "bbox": BBox(348, 393, 138, 17).as_dict()},
        ]),
        _f("F6-27", 2, "Residence since month and year", "text", 378, 410, 115, 17,
           notes=["Month/year only."]),
        _f("F6-28", 2, "Enclosed age-proof document", "text", 17, 483, 190, 17,
           conditional_on="F6-17=none"),
        _f("F6-29", 2, "Declaration date and place", "composite", 17, 540, 110, 30, options=[
            {"value": "date", "label": "Date", "bbox": BBox(45, 540, 80, 16).as_dict()},
            {"value": "place", "label": "Place", "bbox": BBox(45, 554, 76, 16).as_dict()},
        ]),
        _f("F6-30", 2, "Applicant signature or left-hand thumb impression", "signature", 285, 538, 290, 14,
           strategy="signature-placement", notes=["Review-required ink/image placement; do not treat as digital signature."]),
        _f("F6-31", 2, "Acknowledgement number and date", "composite", 135, 724, 440, 18,
           strategy="acroform-office-only", options=[
               {"value": "acknowledgement_number", "label": "Acknowledgement number", "bbox": BBox(135, 724, 260, 17).as_dict()},
               {"value": "date", "label": "Acknowledgement date", "bbox": BBox(425, 724, 150, 17).as_dict()},
           ]),
        _f("F6-32", 2, "Received applicant name", "text", 252, 738, 339, 17,
           strategy="acroform-office-only"),
        _f("F6-33", 2, "ERO/AERO/BLO signature", "signature", 285, 792, 290, 35,
           strategy="signature-placement", notes=["Office-only region."]),
    ]


def matches_form6(path: Path) -> bool:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest() == FORM6_SHA256
