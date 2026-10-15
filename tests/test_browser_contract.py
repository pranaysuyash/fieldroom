from pathlib import Path


ROOT = Path(__file__).parents[1]
APP = (ROOT / "browser" / "app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "browser" / "styles.css").read_text(encoding="utf-8")


def test_browser_represents_zero_targets_as_abstention_with_manual_recovery():
    assert 'No editable targets found' in APP
    assert 'Draw a field manually' in APP
    assert 'setDrawMode(true)' in APP
    assert 'hasTargets ? `${percent}% reviewed` : "No editable targets found"' in APP


def test_browser_choice_taxonomy_keeps_behavior_as_a_subtype():
    assert 'label: "Choice", subtype: singleSelect ? "single-select" : "multi-select"' in APP
    assert '· ${type.subtype}' in APP
    assert 'Radio' not in APP.split('function fieldType', 1)[1].split('function sourceLabel', 1)[0]


def test_browser_names_composite_groups_from_semantic_labels():
    for label in ("Constituency group", "Address group", "Identity group", "Date + place group"):
        assert label in APP
    assert ".field-list-empty.no-targets" in STYLES


def test_browser_groups_use_perimeter_highlight_without_filled_child_boxes():
    assert ".target.target-grid { border:1px solid" in STYLES
    assert ".target.target-structured { border:1px solid" in STYLES
    assert ".target.target-grid .grid-region { position:absolute; border:0; background:transparent" in STYLES
    assert ".target.target-structured .option-region { position:absolute; border:0; background:transparent" in STYLES


def test_browser_review_targets_do_not_paint_over_source_document():
    assert ".target { position:absolute; display:flex; align-items:flex-start; justify-content:flex-start; padding:0; border:1px solid" in STYLES
    assert ".target.review { border-color:rgba(203,139,22,.68); background:transparent; }" in STYLES
    assert ".target:hover,.target.selected { border-color:rgba(23,107,98,.7); background:rgba(23,107,98,.02); box-shadow:none; }" in STYLES


def test_browser_review_triage_has_keyboard_flow_and_confidence_queue():
    assert 'document.addEventListener("keydown"' in APP
    assert "nextPendingTarget" in APP
    assert 'event.key === "j"' in APP
    assert 'event.key === "a"' in APP
    assert 'event.key === "x"' in APP
    assert 'state.sortMode === "confidence" ? "Worst confidence first" : "Document order"' in APP
    assert "(a.confidence - b.confidence)" in APP
    # Editing must never be hijacked: keys are ignored inside form controls.
    assert "node.closest(\"input, textarea, select, [contenteditable='true']\")" in APP
    assert ".filter-button.sort-toggle" in STYLES


def test_browser_surface_required_and_conditional_field_governance():
    assert 'id="field-flags"' in (ROOT / "browser" / "index.html").read_text(encoding="utf-8")
    assert "Mark required" in APP
    assert "Required at export" in APP
    assert "Conditional on" in APP
    assert ".field-flag.required" in STYLES


def test_browser_offers_values_download_after_export():
    assert 'id="values-link"' in (ROOT / "browser" / "index.html").read_text(encoding="utf-8")
    assert "data.values_url" in APP
    assert ".values-link.hidden" in STYLES
