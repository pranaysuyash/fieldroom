const FIELD_TYPES = {
  text: { label: "Text", icon: "Aa", description: "A single-line answer such as a name, address, or identification number." },
  textarea: { label: "Text area", icon: "¶", description: "A multiline answer. Type the complete response once and it will export as a wrapped field." },
  date: { label: "Date", icon: "◷", description: "A calendar value. Use the date picker so the exported value stays consistent." },
  choice: { label: "Choice", icon: "☑", description: "A checkbox or a set of options detected in the document." },
  image: { label: "Photo", icon: "▧", description: "An image area. Add a photo by upload or drag and drop." },
  signature: { label: "Signature", icon: "✎", description: "A visual signature area. Draw, type, or upload the ink/image to place." },
  composite: { label: "Group", icon: "＋", description: "A grouped or multi-part area with coordinated answers." },
};
const FILTERS = [{ key: "all", label: "All" }, ...Object.entries(FIELD_TYPES).map(([key, type]) => ({ key, label: type.label })), { key: "review", label: "Review" }, { key: "rejected", label: "Rejected" }];
const state = { session: null, target: null, page: 1, zoom: 1, values: {}, filter: "all", sortMode: "document", drawMode: false, drag: null, saveChain: Promise.resolve(), justMoved: false, manifestRevision: 0 };
const $ = (id) => document.getElementById(id);

function normalizedKind(target) { return FIELD_TYPES[target.kind] ? target.kind : "composite"; }

function isValueMissing(target, value) {
  const candidate = value === undefined ? valueFor(target) : value;
  if (candidate === undefined || candidate === null) return true;
  if (target.kind === "signature" || target.kind === "image") {
    return !(typeof candidate === "string" && candidate.startsWith("data:"));
  }
  if (target.kind === "composite" && target.options?.length) {
    return !(typeof candidate === "object" && candidate !== null && Object.values(candidate).some((entry) => String(entry).trim() !== ""));
  }
  if (target.kind === "choice") {
    return candidate === "" || candidate === null || candidate === undefined;
  }
  if (typeof candidate === "string") {
    return candidate.trim() === "";
  }
  return false;
}

function compositeGroupLabel(target) {
  if (target.group_label) return target.group_label;
  const label = String(target.label || "").toLowerCase();
  if (label.includes("constituency")) return "Constituency group";
  if (label.includes("address") || label.includes("residence")) return "Address group";
  if (label.includes("aadhaar") || label.includes("epic") || label.includes("identity")) return "Identity group";
  if (label.includes("date") && label.includes("place")) return "Date + place group";
  if (label.includes("birth")) return "Birthplace group";
  if (label.includes("disability")) return "Disability group";
  if (label.includes("family") || label.includes("relative")) return "Family member group";
  if (label.includes("acknowledg")) return "Acknowledgement group";
  return "Grouped field";
}
function fieldType(target) {
  const kind = normalizedKind(target);
  const type = FIELD_TYPES[kind];
  if (kind === "choice") {
    const singleSelect = target.selection_mode === "radio" || target.editable_strategy === "acroform-radio";
    return { ...type, label: "Choice", subtype: singleSelect ? "single-select" : "multi-select", description: singleSelect ? "Choose one option from this choice group." : "Choose one or more options from this choice group." };
  }
  if (kind === "composite") return { ...type, label: compositeGroupLabel(target), subtype: "group" };
  return type;
}
function sourceLabel(target) { return (target.evidence?.[0]?.source || "detected").replaceAll("_", " "); }
function activeTargets() { return state.session.targets.filter((target) => target.status !== "rejected"); }
function isReviewed(target) { return target.status === "accepted"; }
function currentTarget() { return state.target ? state.session?.targets.find((target) => target.id === state.target.id) || null : null; }
function valueFor(target) { return state.values[target.id] ?? ""; }

function showToast(message) { const toast = $("toast"); toast.textContent = message; toast.classList.remove("hidden"); clearTimeout(showToast.timer); showToast.timer = setTimeout(() => toast.classList.add("hidden"), 3200); }
function displayError(message) { $("upload-error").textContent = message; $("upload-error").classList.remove("hidden"); }

function persistManifest() {
  if (!state.session) return;
  const snapshot = { revision: state.manifestRevision, targets: structuredClone(state.session.targets) };
  state.saveChain = state.saveChain.then(async () => {
    const response = await fetch(`/api/sessions/${state.session.session_id}/manifest`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(snapshot) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail?.message || data.detail || "Could not save review changes");
    state.manifestRevision = data.revision; state.session.targets = data.targets; state.target = currentTarget() || state.target; renderAll();
  }).catch((error) => showToast(error.message));
  return state.saveChain;
}

function updateProgress() {
  if (!state.session) return;
  const targets = activeTargets(); const reviewed = targets.filter(isReviewed).length; const hasTargets = targets.length > 0; const percent = hasTargets ? Math.round(reviewed / targets.length * 100) : 0;
  $("completion-label").textContent = hasTargets ? `${percent}% reviewed` : "No editable targets found"; $("target-count").textContent = hasTargets ? `${targets.length} targets` : "0 targets"; $("progress-bar").style.width = `${hasTargets ? percent : 0}%`; $("field-index-count").textContent = targets.length; renderFieldSummary(); renderFieldList();
  renderSignatureAudit();
}
function renderSignatureAudit() {
  const root = $("signature-audit");
  if (!root || !state.session) return;
  const observations = state.session.signature_observations || [];
  root.replaceChildren();
  root.classList.toggle("hidden", !observations.length);
  if (!observations.length) return;

  const present = observations.filter((item) => item.status === "present").length;
  const missing = observations.filter((item) => item.status === "missing").length;
  const uncertain = observations.filter((item) => item.status === "uncertain").length;

  const title = document.createElement("strong");
  title.textContent = "Signature audit";
  const summary = document.createElement("span");
  summary.textContent = `${present} present · ${missing} missing${uncertain ? ` · ${uncertain} uncertain` : ""}`;

  const note = document.createElement("small");
  note.textContent = "Review-only evidence, not editable fields";
  const list = document.createElement("div");
  list.className = "signature-audit-list";

  observations.forEach((item) => {
    const row = document.createElement("button");
    row.className = `signature-audit-row signature-${item.status}`;
    row.type = "button";
    row.setAttribute("aria-label", `${item.signer}, ${item.role}, ${item.status}`);
    const marker = document.createElement("span");
    marker.className = "signature-audit-marker";
    marker.textContent = item.status === "present" ? "✓" : item.status === "missing" ? "!" : "?";
    const info = document.createElement("span");
    info.className = "signature-audit-info";
    const signer = document.createElement("strong");
    signer.textContent = `${item.signer} (${item.role})`;
    const details = document.createElement("small");
    details.textContent = `Page ${item.page} · ${item.status.toUpperCase()} · conf ${Math.round(item.confidence * 100)}%`;
    info.append(signer, details);
    row.append(marker, info);
    row.addEventListener("click", () => {
      state.page = item.page;
      renderPages();
      renderCanvas();
    });
    list.append(row);
  });

  root.append(title, summary, note, list);
}
function renderFieldSummary() { const summary = $("field-summary"); summary.replaceChildren(); const counts = new Map(); activeTargets().forEach((target) => { const kind = normalizedKind(target); counts.set(kind, (counts.get(kind) || 0) + 1); }); Object.entries(FIELD_TYPES).forEach(([kind, type]) => { const count = counts.get(kind) || 0; if (!count) return; const button = document.createElement("button"); button.className = "summary-chip"; button.title = `Show ${type.label.toLowerCase()} fields`; const icon = document.createElement("span"); icon.className = `type-icon type-${kind}`; icon.textContent = type.icon; const strong = document.createElement("strong"); strong.textContent = count; const label = document.createElement("span"); label.textContent = type.label; button.append(icon, strong, label); button.addEventListener("click", () => { state.filter = kind; renderFieldFilters(); renderFieldList(); }); summary.append(button); }); }
function renderFieldFilters() { const root = $("field-filters"); root.replaceChildren(); FILTERS.forEach((filter) => { const button = document.createElement("button"); button.className = "filter-button"; button.textContent = filter.label; button.role = "tab"; button.ariaSelected = state.filter === filter.key; button.classList.toggle("active", state.filter === filter.key); button.addEventListener("click", () => { state.filter = filter.key; renderFieldFilters(); renderFieldList(); }); root.append(button); }); const sortButton = document.createElement("button"); sortButton.className = "filter-button sort-toggle"; sortButton.type = "button"; sortButton.textContent = state.sortMode === "confidence" ? "Worst confidence first" : "Document order"; sortButton.title = "Sort the review queue by lowest confidence first"; sortButton.setAttribute("aria-pressed", state.sortMode === "confidence"); sortButton.addEventListener("click", () => { state.sortMode = state.sortMode === "confidence" ? "document" : "confidence"; renderFieldFilters(); renderFieldList(); }); root.append(sortButton); }
function filteredTargets() { const source = state.filter === "rejected" ? state.session.targets.filter((target) => target.status === "rejected") : activeTargets(); const matched = source.filter((target) => state.filter === "all" || state.filter === "rejected" || (state.filter === "review" ? !isReviewed(target) : normalizedKind(target) === state.filter)); if (state.sortMode !== "confidence") return matched; return [...matched].sort((a, b) => (a.confidence - b.confidence) || String(a.id).localeCompare(String(b.id))); }
function renderFieldList() { const root = $("field-list"); if (!root || !state.session) return; root.replaceChildren(); const targets = filteredTargets(); if (!targets.length) { if (state.filter === "all" && activeTargets().length === 0) { const empty = document.createElement("div"); empty.className = "field-list-empty no-targets"; const title = document.createElement("strong"); title.textContent = "No editable targets found"; const copy = document.createElement("span"); copy.textContent = "This document may be flat, scanned, or simply have no form affordances. Draw one manually to begin."; const action = document.createElement("button"); action.type = "button"; action.className = "secondary-button"; action.textContent = "＋ Draw a field manually"; action.addEventListener("click", () => setDrawMode(true)); empty.append(title, copy, action); root.append(empty); return; } const empty = document.createElement("p"); empty.className = "field-list-empty"; empty.textContent = state.filter === "review" ? "Everything is reviewed." : state.filter === "rejected" ? "No rejected targets." : "No fields of this type."; root.append(empty); return; } targets.forEach((target) => { const type = fieldType(target); const kind = normalizedKind(target); const button = document.createElement("button"); button.className = "field-row"; button.classList.toggle("selected", state.target?.id === target.id); button.classList.toggle("needs-review", !isReviewed(target) && target.status !== "rejected"); button.classList.toggle("rejected", target.status === "rejected"); button.setAttribute("aria-label", `${type.label}: ${target.label}, page ${target.page}`); const icon = document.createElement("span"); icon.className = `type-icon type-${kind}`; icon.textContent = type.icon; const copy = document.createElement("span"); copy.className = "field-row-copy"; const strong = document.createElement("strong"); strong.textContent = target.label; const small = document.createElement("small"); small.textContent = `Page ${target.page} · ${type.label}${type.subtype ? ` · ${type.subtype}` : ""}`; copy.append(strong, small); const status = document.createElement("span"); status.className = "field-row-status"; status.textContent = target.status === "rejected" ? "Rejected" : isReviewed(target) ? "Reviewed" : "Review"; button.append(icon, copy, status); button.addEventListener("click", () => selectTarget(target)); root.append(button); }); }
function renderPages() { const list = $("page-list"); list.replaceChildren(); state.session.pages.forEach((page) => { const button = document.createElement("button"); button.className = "page-thumb"; button.classList.toggle("active", page.number === state.page); const image = document.createElement("img"); image.src = page.image_url; image.alt = ""; const label = document.createElement("span"); label.textContent = `Page ${page.number}`; button.append(image, label); button.addEventListener("click", () => { state.page = page.number; renderPages(); renderCanvas(); }); list.append(button); }); }

function pageScale() { const image = $("page-image"); const size = state.session.input.page_sizes[state.page - 1]; return { x: (image.naturalWidth || size.width) / size.width, y: (image.naturalHeight || size.height) / size.height }; }
function renderCanvas() { const page = state.session.pages.find((item) => item.number === state.page); $("page-title").textContent = `Page ${state.page}`; const image = $("page-image"); image.src = page.image_url; image.onload = () => { $("page-stage").style.transform = `scale(${state.zoom})`; $("zoom-label").textContent = `${Math.round(state.zoom * 100)}%`; renderTargets(); }; renderTargets(); }
function applyBox(element, box, scaleX, scaleY) { element.style.left = `${box.x * scaleX}px`; element.style.top = `${box.y * scaleY}px`; element.style.width = `${Math.max(28, box.width * scaleX)}px`; element.style.height = `${Math.max(26, box.height * scaleY)}px`; }
function acceptButton(target, valueForCommit) { const button = document.createElement("button"); button.type = "button"; button.className = "inline-accept"; button.textContent = "✓"; button.title = "Accept and mark reviewed"; button.setAttribute("aria-label", `Accept ${fieldType(target).label} field`); button.addEventListener("click", (event) => { event.stopPropagation(); commitTarget(target, valueForCommit()); }); return button; }
function commitTarget(target, value) {
  const finalValue = value === undefined ? valueFor(target) : value;
  if (isValueMissing(target, finalValue)) {
    showToast(`Add ${fieldType(target).label.toLowerCase()} data before marking reviewed.`);
    if (currentTarget()?.id === target.id) $("field-confirmed").checked = false;
    return false;
  }
  state.values[target.id] = finalValue;
  target.status = "accepted";
  if (currentTarget()?.id === target.id) $("field-confirmed").checked = true;
  updateProgress();
  renderTargets();
  renderFieldList();
  persistManifest();
  showToast(`${fieldType(target).label} filled on page`);
  return true;
}
function pdfPoint(event) { const rect = $("page-stage").getBoundingClientRect(); const scale = pageScale(); return { x: (event.clientX - rect.left) / state.zoom / scale.x, y: (event.clientY - rect.top) / state.zoom / scale.y }; }
function clampBox(box) { const size = state.session.input.page_sizes[state.page - 1]; box.x = Math.max(0, Math.min(box.x, size.width - box.width)); box.y = Math.max(0, Math.min(box.y, size.height - box.height)); box.width = Math.max(4, Math.min(box.width, size.width - box.x)); box.height = Math.max(4, Math.min(box.height, size.height - box.y)); return box; }
function setDrawMode(enabled) { state.drawMode = Boolean(enabled); $("add-target").classList.toggle("active", state.drawMode); $("canvas-status").textContent = state.drawMode ? "Drag over a blank area to add a target. Press Add target again to cancel." : "Select a highlighted region to type directly on the page."; }
function addManualTarget(box) { const target = { id: `manual-${crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`}`, page: state.page, label: "New field", kind: "text", component: "text-field", bbox: clampBox(box), editable_strategy: "acroform-text", status: "pending", required: false, conditional_on: null, options: [], evidence: [{ source: "manual", score: 1, detail: "Target added during browser review", observed: true }], confidence: 1, notes: ["Added manually; confirm type, label, position, and meaning."], input_mode: "single", max_length: null }; state.session.targets.push(target); setDrawMode(false); state.target = target; renderAll(); selectTarget(target); persistManifest(); showToast("Target added. Name it and choose its type."); }
function renderTargets() {
  const layer = $("target-layer");
  layer.replaceChildren();
  $("inline-editor-layer").replaceChildren();
  if (!state.session) return;
  const { x: scaleX, y: scaleY } = pageScale();
  (state.session.signature_observations || []).filter((item) => item.page === state.page).forEach((item) => {
    const observation = document.createElement("div");
    observation.className = `signature-observation signature-${item.status}`;
    observation.title = `Signature audit: ${item.label} · ${item.status}`;
    observation.setAttribute("role", "img");
    observation.setAttribute("aria-label", `Signature audit: ${item.label}, ${item.status}`);
    applyBox(observation, item.bbox, scaleX, scaleY);
    const badge = document.createElement("span");
    badge.className = "signature-observation-badge";
    badge.textContent = item.status === "present" ? "✓" : item.status === "missing" ? "!" : "?";
    const label = document.createElement("span");
    label.className = "signature-observation-label";
    label.textContent = `${item.signer} · ${item.status}`;
    observation.append(badge, label);
    layer.append(observation);
  });
  activeTargets().filter((target) => target.page === state.page).forEach((target) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `target target-${normalizedKind(target)}`;
    button.classList.toggle("review", !isReviewed(target));
    button.classList.toggle("selected", state.target?.id === target.id);
    const type = fieldType(target);
    button.title = `${type.label}: ${target.label}`;
    button.setAttribute("aria-label", `${type.label}: ${target.label}`);
    applyBox(button, target.bbox, scaleX, scaleY);
    const marker = document.createElement("span");
    marker.className = "target-marker";
    marker.textContent = type.icon;
    marker.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.className = "target-label";
    label.textContent = `${type.label} · ${target.label}`;
    const handle = document.createElement("span");
    handle.className = "resize-handle";
    handle.title = "Resize target";
    handle.setAttribute("aria-label", "Resize target");
    const structuredRegions = target.grid_rows?.length
      ? target.grid_rows.map((row) => ({ ...row, regionClass: "grid-region" }))
      : target.options?.length
        ? target.options.map((option) => ({ ...option, regionClass: "option-region" }))
        : [];
    if (structuredRegions.length) {
      button.classList.add(target.grid_rows?.length ? "target-grid" : "target-structured");
      structuredRegions.forEach((item, index) => {
        const region = document.createElement("span");
        region.className = item.regionClass;
        const box = item.bbox;
        applyBox(region, { x: box.x - target.bbox.x, y: box.y - target.bbox.y, width: box.width, height: box.height }, scaleX, scaleY);
        if (index === 0) region.append(marker, label);
        button.append(region);
      });
      button.append(handle);
    } else {
      button.append(marker, label, handle);
    }
    button.addEventListener("pointerdown", (event) => {
      if (event.target === handle) {
        event.stopPropagation();
        startTransform(event, target, "resize");
      } else startTransform(event, target, "move");
    });
    button.addEventListener("click", () => {
      if (!state.justMoved) selectTarget(target);
      state.justMoved = false;
    });
    layer.append(button);
  });
  renderInlineEditor();
}
function startTransform(event, target, mode) { if (state.drawMode) return; event.preventDefault(); state.drag = { target, mode, start: pdfPoint(event), original: { ...target.bbox }, moved: false }; }
document.addEventListener("pointermove", (event) => { if (!state.drag || state.drag.mode === "draw") return; const drag = state.drag; const point = pdfPoint(event); const dx = point.x - drag.start.x; const dy = point.y - drag.start.y; const next = { ...drag.original }; if (drag.mode === "move") { next.x += dx; next.y += dy; } else { next.width += dx; next.height += dy; } drag.target.bbox = clampBox(next); drag.moved = Math.abs(dx) + Math.abs(dy) > 2; if (drag.moved) { state.justMoved = true; renderTargets(); renderInspectorGeometry(drag.target); } });
document.addEventListener("pointerup", () => { if (!state.drag) return; const changed = state.drag.moved; state.drag = null; if (changed) persistManifest(); });

function renderCommittedValue(target, root, scaleX, scaleY) {
  const value = valueFor(target);
  const hasValue = typeof value === "string" ? value.trim().length > 0 : value && typeof value === "object";
  if (!hasValue || target.kind === "choice" || target.kind === "image" || target.kind === "signature") return false;
  if (target.kind === "composite" && target.options?.length && typeof value === "object") {
    const group = document.createElement("div");
    group.className = "inline-committed inline-composite";
    applyBox(group, target.bbox, scaleX, scaleY);
    target.options.forEach((option) => {
      const text = String(value[option.value] || "").trim();
      if (!text) return;
      const part = document.createElement("span");
      part.className = "inline-filled-part";
      part.textContent = text;
      part.title = `${option.label || option.value}: ${text}`;
      const box = option.bbox;
      applyBox(part, { x: box.x - target.bbox.x, y: box.y - target.bbox.y, width: box.width, height: box.height }, scaleX, scaleY);
      group.append(part);
    });
    root.append(group);
    return true;
  }
  const filled = document.createElement("div");
  filled.className = `inline-committed inline-filled-${normalizedKind(target)}`;
  filled.textContent = String(value);
  filled.title = `${fieldType(target).label} filled: ${value}`;
  filled.setAttribute("role", "status");
  filled.setAttribute("aria-label", `${fieldType(target).label} filled: ${value}`);
  applyBox(filled, target.bbox, scaleX, scaleY);
  root.append(filled);
  return true;
}

function renderInlineEditor() { const target = currentTarget(); const root = $("inline-editor-layer"); if (!target || target.page !== state.page || !state.session) return; const { x: scaleX, y: scaleY } = pageScale(); const kind = normalizedKind(target); if (isReviewed(target) && renderCommittedValue(target, root, scaleX, scaleY)) return; if (target.kind === "composite" && target.options?.length) { const group = document.createElement("div"); group.className = "inline-editor inline-composite"; applyBox(group, target.bbox, scaleX, scaleY); const current = typeof valueFor(target) === "object" ? valueFor(target) : {}; target.options.forEach((option) => { const input = document.createElement("input"); input.type = "text"; input.className = "inline-part"; input.placeholder = option.label || option.value; input.value = current[option.value] || ""; input.setAttribute("aria-label", `${target.label}, ${option.label || option.value}`); const box = option.bbox; input.style.left = `${(box.x - target.bbox.x) * scaleX}px`; input.style.top = `${(box.y - target.bbox.y) * scaleY}px`; input.style.width = `${Math.max(28, box.width * scaleX)}px`; input.style.height = `${Math.max(25, box.height * scaleY)}px`; input.addEventListener("input", () => { const next = { ...(state.values[target.id] || {}) }; next[option.value] = input.value; state.values[target.id] = next; }); group.append(input); }); group.append(acceptButton(target, () => state.values[target.id] || current)); root.append(group); return; } const editor = document.createElement("div"); editor.className = `inline-editor inline-${kind}`; applyBox(editor, target.bbox, scaleX, scaleY); let value = valueFor(target); let control; if (target.kind === "choice" && target.options?.length && target.selection_mode === "radio") { const group = document.createElement("fieldset"); group.className = "inline-choice-options"; const legend = document.createElement("legend"); legend.textContent = target.label; group.append(legend); target.options.forEach((option, index) => { const label = document.createElement("label"); label.className = "inline-choice-option"; const input = document.createElement("input"); input.type = "radio"; input.name = `inline-${target.id}`; input.value = option.value; input.checked = value === option.value; input.addEventListener("change", () => { if (input.checked) state.values[target.id] = input.value; }); label.append(input, document.createTextNode(option.label || option.value)); group.append(label); }); editor.append(group); editor.append(acceptButton(target, () => valueFor(target))); root.append(editor); return; } if (target.kind === "choice") { control = target.options?.length ? document.createElement("select") : document.createElement("input"); if (target.options?.length) { control.className = "inline-select"; const placeholder = document.createElement("option"); placeholder.value = ""; placeholder.textContent = "Choose an option"; control.append(placeholder); target.options.forEach((option) => { const item = document.createElement("option"); item.value = option.value; item.textContent = option.label || option.value; control.append(item); }); control.value = typeof value === "string" ? value : ""; } else { control.type = "checkbox"; control.className = "inline-checkbox"; control.checked = Boolean(value); } control.setAttribute("aria-label", target.label); control.addEventListener("change", () => { state.values[target.id] = target.options?.length ? control.value : control.checked ? "selected" : ""; }); } else if (target.kind === "image") { const label = document.createElement("label"); label.className = "inline-asset"; label.innerHTML = `<strong>${value ? "Photo added" : "Add photo"}</strong><span>${value ? "Choose another" : "Upload or drop"}</span>`; control = document.createElement("input"); control.type = "file"; control.accept = "image/png,image/jpeg"; control.hidden = true; control.addEventListener("change", () => readAsset(control, target)); label.append(control); editor.append(label); } else if (target.kind === "signature") { const button = document.createElement("button"); button.type = "button"; button.className = "inline-signature"; button.textContent = value ? "Signature added" : "Open signature tools"; button.addEventListener("click", () => $("field-control").scrollIntoView({ behavior: "smooth", block: "center" })); editor.append(button); } else { control = document.createElement(target.kind === "composite" || target.kind === "textarea" ? "textarea" : "input"); control.className = "inline-input"; if (target.kind === "textarea") control.rows = 3; if (target.kind === "date") control.type = "date"; control.value = typeof value === "string" ? value : ""; control.placeholder = target.input_mode === "character-grid" ? "Type the full answer once" : "Type here"; control.setAttribute("aria-label", target.label); control.addEventListener("input", () => { state.values[target.id] = control.value; }); } if (control && target.kind !== "image" && target.kind !== "signature") editor.append(control); editor.append(acceptButton(target, () => target.kind === "choice" ? target.options?.length ? control.value : control.checked ? "selected" : "" : target.kind === "image" || target.kind === "signature" ? valueFor(target) : control.value)); root.append(editor); }
function readAsset(input, target) { const file = input.files?.[0]; if (!file) return; if (file.size > 8 * 1024 * 1024) { showToast("Image must be 8 MB or smaller"); return; } const reader = new FileReader(); reader.onload = () => { state.values[target.id] = reader.result; renderInlineEditor(); renderControl(target); }; reader.readAsDataURL(file); }
function typedSignature(text) { const canvas = document.createElement("canvas"); canvas.width = 720; canvas.height = 240; const ctx = canvas.getContext("2d"); ctx.fillStyle = "white"; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.fillStyle = "#172d2a"; ctx.font = "italic 76px Georgia"; ctx.fillText(text || "", 34, 140); return canvas.toDataURL("image/png"); }
function drawSignature(canvas, target) { const ctx = canvas.getContext("2d"); let drawing = false; ctx.strokeStyle = "#172d2a"; ctx.lineWidth = 5; ctx.lineCap = "round"; const point = (event) => { const rect = canvas.getBoundingClientRect(); return [(event.clientX - rect.left) * canvas.width / rect.width, (event.clientY - rect.top) * canvas.height / rect.height]; }; canvas.addEventListener("pointerdown", (event) => { drawing = true; canvas.setPointerCapture(event.pointerId); const [x, y] = point(event); ctx.beginPath(); ctx.moveTo(x, y); }); canvas.addEventListener("pointermove", (event) => { if (!drawing) return; const [x, y] = point(event); ctx.lineTo(x, y); ctx.stroke(); }); canvas.addEventListener("pointerup", () => { drawing = false; state.values[target.id] = canvas.toDataURL("image/png"); }); }
function renderControl(target) { const root = $("field-control"); root.replaceChildren(); if (target.kind === "image" || target.kind === "signature") { renderAssetControl(root, target); return; } const hint = document.createElement("div"); hint.className = "inline-hint"; hint.innerHTML = "<strong>Type directly on the page</strong><span>Use the ✓ on the highlighted field when the answer looks right.</span>"; root.append(hint); }
function renderAssetControl(root, target) { const wrap = document.createElement("div"); wrap.className = "asset-control"; const tabs = document.createElement("div"); tabs.className = "asset-tabs"; const modes = target.kind === "signature" ? ["draw", "type", "upload"] : ["upload"]; const body = document.createElement("div"); const renderMode = (mode) => { tabs.querySelectorAll("button").forEach((button) => button.classList.toggle("active", button.dataset.mode === mode)); body.replaceChildren(); const current = valueFor(target); if (current && typeof current === "string" && current.startsWith("data:")) { const preview = document.createElement("img"); preview.className = "asset-preview"; preview.src = current; body.append(preview); } if (mode === "upload") { const label = document.createElement("label"); label.className = "asset-drop"; label.innerHTML = `<strong>${target.kind === "image" ? "Add a photo" : "Add signature ink"}</strong><span>Choose a PNG or JPG</span>`; const input = document.createElement("input"); input.type = "file"; input.accept = "image/png,image/jpeg"; input.hidden = true; input.addEventListener("change", () => readAsset(input, target)); label.append(input); body.append(label); } else if (mode === "type") { const label = document.createElement("label"); label.className = "control-label"; label.textContent = "Type your name"; const input = document.createElement("input"); input.className = "control-input"; input.placeholder = "Your name"; input.value = target._typed || ""; input.addEventListener("input", () => { target._typed = input.value; state.values[target.id] = typedSignature(input.value); }); body.append(label, input); } else { const label = document.createElement("label"); label.className = "control-label"; label.textContent = "Draw inside the box"; const canvas = document.createElement("canvas"); canvas.className = "signature-canvas"; canvas.width = 720; canvas.height = 240; body.append(label, canvas); drawSignature(canvas, target); } }; modes.forEach((mode) => { const button = document.createElement("button"); button.className = "asset-tab"; button.dataset.mode = mode; button.textContent = mode[0].toUpperCase() + mode.slice(1); button.addEventListener("click", () => renderMode(mode)); tabs.append(button); }); wrap.append(tabs, body); root.append(wrap); renderMode(modes[0]); }
function renderInspectorGeometry(target) { if (!target) return; $("field-x").value = target.bbox.x; $("field-y").value = target.bbox.y; $("field-width").value = target.bbox.width; $("field-height").value = target.bbox.height; }
function renderLabelEntities(target) { const root = $("field-entities"); root.replaceChildren(); const entities = target.label_entities || []; if (!entities.length) { const empty = document.createElement("span"); empty.className = "entity-empty"; empty.textContent = "No explicit intent cue"; root.append(empty); return; } entities.forEach((entity) => { const chip = document.createElement("span"); chip.className = "entity-chip"; chip.title = entity.cue || entity.type; chip.textContent = entity.type.replaceAll("_", " "); root.append(chip); }); }
function selectTarget(target) { state.target = target; state.page = target.page; renderPages(); renderCanvas(); renderFieldList(); $("empty-inspector").classList.add("hidden"); $("field-inspector").classList.remove("hidden"); const type = fieldType(target); $("field-label").textContent = target.label; $("field-label-input").value = target.label; $("field-kind").textContent = `${type.icon} ${type.label}${type.subtype ? ` · ${type.subtype}` : ""}`.toUpperCase(); $("field-description").textContent = type.description; renderLabelEntities(target); $("field-type").textContent = type.label; $("field-confidence").textContent = `${Math.round(target.confidence * 100)}%`; $("field-source").textContent = sourceLabel(target); renderFieldFlags(target); $("field-confirmed").checked = isReviewed(target); $("field-note").textContent = target.notes?.[0] || "Review this target before export."; $("reject-target").textContent = target.status === "rejected" ? "Restore target" : "Reject target"; const select = $("field-type-select"); select.replaceChildren(); Object.entries(FIELD_TYPES).forEach(([key, field]) => { const option = document.createElement("option"); option.value = key; option.textContent = field.label; option.selected = normalizedKind(target) === key; select.append(option); }); renderInspectorGeometry(target); renderControl(target); }
function renderFieldFlags(target) { const root = $("field-flags"); if (!root) return; root.replaceChildren(); const requiredChip = document.createElement("span"); requiredChip.className = `field-flag${target.required ? " required" : ""}`; requiredChip.role = "button"; requiredChip.tabIndex = 0; requiredChip.textContent = target.required ? "Required at export" : "Mark required"; requiredChip.title = target.required ? "Export refuses empty values here. Click to clear." : "Export will refuse empty values here once marked."; requiredChip.addEventListener("click", () => { target.required = !target.required; renderFieldFlags(target); persistManifest(); }); root.append(requiredChip); if (target.conditional_on) { const chip = document.createElement("span"); chip.className = "field-flag conditional"; chip.textContent = `Conditional on ${target.conditional_on}`; chip.title = "This field is only expected when its condition holds; export validation respects that."; root.append(chip); } }
function nextPendingTarget() { const queue = filteredTargets().filter((target) => !isReviewed(target)); if (!queue.length) { showToast("Everything is reviewed."); return; } const index = queue.findIndex((target) => state.target && target.id === state.target.id); selectTarget(queue[(index + 1) % queue.length]); }
function toggleRejectCurrent() { const target = currentTarget(); if (!target) return; const restoring = target.status === "rejected"; target.status = restoring ? "pending" : "rejected"; state.filter = restoring ? "all" : "rejected"; renderAll(); selectTarget(target); persistManifest(); }
document.addEventListener("keydown", (event) => {
  if (!state.session || event.metaKey || event.ctrlKey || event.altKey) return;
  const node = event.target;
  if (node && node.closest && node.closest("input, textarea, select, [contenteditable='true']")) return;
  if (event.key === "j") { event.preventDefault(); nextPendingTarget(); }
  else if (event.key === "a") { event.preventDefault(); const target = currentTarget(); if (target && commitTarget(target, undefined)) nextPendingTarget(); }
  else if (event.key === "x") { event.preventDefault(); toggleRejectCurrent(); }
  else if (event.key === "?") { event.preventDefault(); showToast("j: next unreviewed · a: accept and continue · x: reject/restore"); }
});
function renderAll() { if (!state.session) return; updateProgress(); renderPages(); renderCanvas(); renderFieldFilters(); if (currentTarget()) selectTarget(currentTarget()); }

$("field-label-input").addEventListener("change", (event) => {
  const target = currentTarget();
  if (!target) return;
  const label = event.target.value.trim();
  if (!label) {
    event.target.value = target.label;
    return;
  }
  target.label = label;
  $("field-label").textContent = label;
  renderTargets();
  renderFieldList();
  persistManifest();
});
$("field-type-select").addEventListener("change", (event) => {
  const target = currentTarget();
  if (!target) return;
  target.kind = event.target.value;
  target.component = FIELD_TYPES[target.kind].label;
  target.editable_strategy = target.kind === "choice" ? "acroform-checkbox" : target.kind === "image" || target.kind === "signature" ? "visual-overlay-image" : "acroform-text";
  renderAll();
  persistManifest();
});
["field-x", "field-y", "field-width", "field-height"].forEach((id) =>
  $(id).addEventListener("change", () => {
    const target = currentTarget();
    if (!target) return;
    target.bbox = clampBox({
      x: Number($("field-x").value),
      y: Number($("field-y").value),
      width: Number($("field-width").value),
      height: Number($("field-height").value),
    });
    renderTargets();
    renderInspectorGeometry(target);
    persistManifest();
  })
);
$("field-confirmed").addEventListener("change", (event) => {
  const target = currentTarget();
  if (!target) return;

  if (event.target.checked) {
    const committed = commitTarget(target, valueFor(target));
    if (!committed) {
      event.target.checked = false;
      return;
    }
    return;
  }

  target.status = "pending";
  updateProgress();
  renderTargets();
  renderFieldList();
  persistManifest();
});
$("reject-target").addEventListener("click", () => {
  const target = currentTarget();
  if (!target) return;
  const restoring = target.status === "rejected";
  target.status = restoring ? "pending" : "rejected";
  state.filter = restoring ? "all" : "rejected";
  renderAll();
  selectTarget(target);
  persistManifest();
  showToast(restoring ? "Target restored for review." : "Target rejected. It remains recoverable in the review manifest.");
});
$("page-stage").addEventListener("pointerdown", (event) => { if (!state.drawMode || event.target.closest("button")) return; event.preventDefault(); state.drag = { mode: "draw", start: pdfPoint(event), current: pdfPoint(event), moved: false }; }); $("page-stage").addEventListener("pointermove", (event) => { if (!state.drag || state.drag.mode !== "draw") return; state.drag.current = pdfPoint(event); state.drag.moved = true; const start = state.drag.start; const current = state.drag.current; const box = { x: Math.min(start.x, current.x), y: Math.min(start.y, current.y), width: Math.abs(current.x - start.x), height: Math.abs(current.y - start.y) }; const preview = $("draw-preview") || document.createElement("div"); preview.id = "draw-preview"; preview.className = "draw-preview"; applyBox(preview, box, pageScale().x, pageScale().y); $("target-layer").append(preview); }); $("page-stage").addEventListener("pointerup", () => { if (!state.drag || state.drag.mode !== "draw") return; const { start, current } = state.drag; state.drag = null; $("draw-preview")?.remove(); const box = { x: Math.min(start.x, current.x), y: Math.min(start.y, current.y), width: Math.abs(current.x - start.x), height: Math.abs(current.y - start.y) }; if (box.width >= 8 && box.height >= 8) addManualTarget(box); else showToast("Drag a larger rectangle to add a target"); }); $("add-target").addEventListener("click", () => { state.drawMode = !state.drawMode; $("add-target").classList.toggle("active", state.drawMode); $("canvas-status").textContent = state.drawMode ? "Drag over a blank area to add a target. Press Add target again to cancel." : "Select a highlighted region to type directly on the page."; });
async function upload(file) { $("upload-error").classList.add("hidden"); if (!file) return; if (file.size > 25 * 1024 * 1024) { displayError("PDF exceeds the 25 MB upload limit"); return; } const body = new FormData(); body.append("file", file); $("drop-zone").classList.add("loading"); try { const response = await fetch("/api/sessions", { method: "POST", body }); const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Upload failed"); state.session = { ...data, targets: data.manifest.targets }; state.manifestRevision = data.manifest.revision; state.page = 1; state.target = null; state.values = {}; state.filter = "all"; $("welcome").classList.add("hidden"); $("workspace").classList.remove("hidden"); $("file-name").textContent = data.filename; renderAll(); showToast(data.signature_observations?.length ? "PDF analyzed. Signature audit is ready for review." : "PDF analyzed. Review the highlighted targets."); } catch (error) { displayError(error.message); } finally { $("drop-zone").classList.remove("loading"); } }
async function exportPdf() { if (!state.session) return; const pending = activeTargets().filter((target) => !isReviewed(target)).length; if (pending) { showToast(`Review ${pending} target${pending === 1 ? "" : "s"} before export`); state.filter = "review"; renderFieldFilters(); renderFieldList(); return; } const button = $("export-button"); button.disabled = true; button.textContent = "Preparing…"; try { await state.saveChain; const values = Object.fromEntries(activeTargets().filter((target) => state.values[target.id] !== undefined).map((target) => [target.id, state.values[target.id]])); const response = await fetch(`/api/sessions/${state.session.session_id}/export`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ values }) }); const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Export failed"); const downloadPath = data.download_url; if (typeof downloadPath !== "string" || !downloadPath.startsWith("/api/sessions/") || downloadPath.includes("//")) throw new Error("Export download must be a same-origin API path"); const valuesLink = $("values-link"); if (typeof data.values_url === "string" && data.values_url.startsWith("/api/sessions/")) { valuesLink.href = data.values_url; valuesLink.classList.remove("hidden"); } window.location.assign(downloadPath); } catch (error) { showToast(error.message); } finally { button.disabled = false; button.textContent = "Export PDF"; } }
$("pdf-input").addEventListener("change", (event) => upload(event.target.files?.[0])); const dropZone = $("drop-zone"); ["dragenter", "dragover"].forEach((name) => dropZone.addEventListener(name, (event) => { event.preventDefault(); dropZone.classList.add("dragging"); })); ["dragleave", "drop"].forEach((name) => dropZone.addEventListener(name, (event) => { event.preventDefault(); dropZone.classList.remove("dragging"); })); dropZone.addEventListener("drop", (event) => upload(event.dataTransfer.files?.[0])); $("new-document").addEventListener("click", () => { state.session = null; state.target = null; state.values = {}; state.filter = "all"; state.drawMode = false; $("workspace").classList.add("hidden"); $("welcome").classList.remove("hidden"); $("pdf-input").value = ""; $("values-link").classList.add("hidden"); }); $("zoom-in").addEventListener("click", () => { state.zoom = Math.min(1.5, state.zoom + .1); renderCanvas(); }); $("zoom-out").addEventListener("click", () => { state.zoom = Math.max(.6, state.zoom - .1); renderCanvas(); }); $("export-button").addEventListener("click", exportPdf); window.__fieldroom = { state, upload, selectTarget, persistManifest };
