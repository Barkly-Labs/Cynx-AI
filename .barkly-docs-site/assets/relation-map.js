(() => {
  "use strict";

  const dataElement = document.getElementById("relation-map-data");
  const svg = document.getElementById("relation-map-canvas");
  const viewport = document.getElementById("relation-map-viewport");
  const details = document.getElementById("relation-map-details-body");
  const search = document.getElementById("relation-map-search");
  const searchResults = document.getElementById("relation-map-search-results");
  const nodeKind = document.getElementById("relation-map-kind");
  const edgeKind = document.getElementById("relation-map-edge-kind");
  const language = document.getElementById("relation-map-language");
  const evidence = document.getElementById("relation-map-evidence");
  const count = document.getElementById("relation-map-count");
  const scopeStatus = document.getElementById("relation-map-scope-status");
  const accessibleList = document.getElementById("relation-map-accessible-list");
  const backButton = document.getElementById("relation-map-back");
  const resetFilters = document.getElementById("relation-map-reset-filters");
  const emptyState = document.getElementById("relation-map-empty");

  if (!dataElement || !svg || !viewport || !details) return;

  let graph;
  try {
    graph = JSON.parse(dataElement.textContent || "{}");
  } catch (error) {
    details.textContent = "The relationship data could not be read.";
    return;
  }

  const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const edges = Array.isArray(graph.edges) ? graph.edges : [];
  const byId = new Map(nodes.map(node => [String(node.id), node]));
  const SVG_NS = "http://www.w3.org/2000/svg";
  const OVERVIEW_LIMIT = 90;
  const NEIGHBOR_LIMIT = 140;

  const incident = new Map();
  for (const node of nodes) incident.set(String(node.id), { incoming: [], outgoing: [] });
  for (const edge of edges) {
    const source = String(edge.source ?? "");
    const target = String(edge.target ?? "");
    if (!incident.has(source)) incident.set(source, { incoming: [], outgoing: [] });
    if (!incident.has(target)) incident.set(target, { incoming: [], outgoing: [] });
    incident.get(source).outgoing.push(edge);
    incident.get(target).incoming.push(edge);
  }

  const value = (obj, ...keys) => {
    for (const key of keys) {
      if (obj && obj[key] !== undefined && obj[key] !== null && obj[key] !== "") return obj[key];
    }
    return "";
  };
  const kindOf = node => String(value(node, "kind", "type") || "unknown");
  const labelOf = node => String(value(node, "label", "name", "qualified_name") || node.id || "Unnamed item");
  const pathOf = node => String(value(node, "path", "source_file", "file_path") || "");
  const evidenceOf = item => String(value(item, "evidence", "evidence_level") || "UNKNOWN").toUpperCase();
  const languageOf = node => String(value(node && node.metadata, "language") || value(node, "language") || "");
  const descriptionOf = node => String(value(node, "description", "docstring", "summary", "explanation") || value(node && node.metadata, "description", "docstring") || "");
  const degreeOf = node => {
    const links = incident.get(String(node.id));
    return links ? links.incoming.length + links.outgoing.length : 0;
  };
  const normalized = text => String(text || "").trim().replace(/\s+/g, " ").toLowerCase();
  const searchText = node => normalized([
    labelOf(node), kindOf(node), value(node, "qualified_name"), pathOf(node),
    languageOf(node), descriptionOf(node)
  ].join(" "));

  const state = {
    selectedId: null,
    previousSelections: [],
    search: "",
    nodeKind: "",
    edgeKind: "",
    language: "",
    evidence: "",
    scale: 1,
    panX: 0,
    panY: 0,
    dragging: false,
    dragX: 0,
    dragY: 0,
  };

  function option(select, label, val) {
    if (!select) return;
    const item = document.createElement("option");
    item.value = val;
    item.textContent = label;
    select.appendChild(item);
  }

  function populateFilters() {
    [...new Set(nodes.map(kindOf).filter(Boolean))].sort().forEach(item => option(nodeKind, item, item));
    [...new Set(edges.map(edge => String(value(edge, "kind", "label") || "unknown")))].sort().forEach(item => option(edgeKind, item, item));
    [...new Set(nodes.map(languageOf).filter(Boolean))].sort().forEach(item => option(language, item, item));
    [...new Set([...nodes.map(evidenceOf), ...edges.map(evidenceOf)].filter(Boolean))].sort().forEach(item => option(evidence, item, item));
  }

  function nodePassesFilters(node) {
    if (state.nodeKind && kindOf(node) !== state.nodeKind) return false;
    if (state.language && languageOf(node) !== state.language) return false;
    if (state.evidence && evidenceOf(node) !== state.evidence) return false;
    return true;
  }

  function edgePassesFilters(edge) {
    if (state.edgeKind && String(value(edge, "kind", "label")) !== state.edgeKind) return false;
    if (state.evidence && evidenceOf(edge) !== state.evidence) return false;
    return true;
  }

  function filteredNodes() { return nodes.filter(nodePassesFilters); }

  function rankedOverview(candidates) {
    return candidates.slice().sort((a, b) =>
      degreeOf(b) - degreeOf(a) || kindOf(a).localeCompare(kindOf(b)) || labelOf(a).localeCompare(labelOf(b))
    ).slice(0, OVERVIEW_LIMIT);
  }

  function scopedNodes(candidates) {
    if (!state.selectedId || !byId.has(state.selectedId)) return rankedOverview(candidates);
    const allowed = new Set(candidates.map(node => String(node.id)));
    const selected = byId.get(state.selectedId);
    const result = [];
    const seen = new Set();
    const add = node => {
      if (!node || !allowed.has(String(node.id)) || seen.has(String(node.id))) return;
      seen.add(String(node.id)); result.push(node);
    };
    add(selected);
    const links = incident.get(state.selectedId) || { incoming: [], outgoing: [] };
    const neighbors = [...links.incoming.map(edge => String(edge.source)), ...links.outgoing.map(edge => String(edge.target))];
    neighbors.map(id => byId.get(id)).filter(Boolean)
      .sort((a, b) => degreeOf(b) - degreeOf(a) || labelOf(a).localeCompare(labelOf(b)))
      .slice(0, NEIGHBOR_LIMIT - 1).forEach(add);
    return result;
  }

  function visibleState() {
    const candidates = filteredNodes();
    const visibleNodes = scopedNodes(candidates);
    const ids = new Set(visibleNodes.map(node => String(node.id)));
    const visibleEdges = edges.filter(edge => ids.has(String(edge.source)) && ids.has(String(edge.target)) && edgePassesFilters(edge));
    return { candidates, visibleNodes, visibleEdges, ids };
  }

  function stableHash(text) {
    let hash = 2166136261;
    for (let i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i); hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  }

  function layout(visibleNodes) {
    const positions = new Map();
    const centerX = 600, centerY = 390;
    const selectedIndex = visibleNodes.findIndex(node => String(node.id) === state.selectedId);
    if (selectedIndex >= 0) positions.set(state.selectedId, { x: centerX, y: centerY });
    const rest = visibleNodes.filter(node => String(node.id) !== state.selectedId);
    const grouped = new Map();
    rest.forEach(node => {
      const key = kindOf(node);
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(node);
    });
    const groups = [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b));
    let index = 0;
    for (const [kind, group] of groups) {
      group.sort((a, b) => stableHash(String(a.id)) - stableHash(String(b.id)) || labelOf(a).localeCompare(labelOf(b)));
      for (const node of group) {
        const ring = 1 + Math.floor(index / 24);
        const slot = index % 24;
        const angle = ((slot / 24) * Math.PI * 2) + ((stableHash(kind) % 360) * Math.PI / 180);
        const radius = 155 + ring * 125;
        positions.set(String(node.id), { x: centerX + Math.cos(angle) * radius, y: centerY + Math.sin(angle) * radius });
        index += 1;
      }
    }
    return positions;
  }

  function svgElement(name, attrs = {}) {
    const el = document.createElementNS(SVG_NS, name);
    Object.entries(attrs).forEach(([key, val]) => el.setAttribute(key, String(val)));
    return el;
  }

  function colorForKind(kind) {
    const colors = { file: "#6fb7ff", module: "#ff6b9d", class: "#7dffb2", interface: "#7dffb2", function: "#ffd76b", method: "#e3a7ff", endpoint: "#ff9f6b", dependency: "#9a9a9a" };
    return colors[kind] || "#8ea0b8";
  }

  function connectedIds(selectedId, visibleEdges) {
    const ids = new Set([selectedId]);
    visibleEdges.forEach(edge => {
      if (String(edge.source) === selectedId) ids.add(String(edge.target));
      if (String(edge.target) === selectedId) ids.add(String(edge.source));
    });
    return ids;
  }

  function renderGraph() {
    const { candidates, visibleNodes, visibleEdges } = visibleState();
    const positions = layout(visibleNodes);
    viewport.replaceChildren();
    if (emptyState) emptyState.hidden = visibleNodes.length > 0;

    const hiddenNodes = Math.max(0, candidates.length - visibleNodes.length);
    const filteredEdgeTotal = edges.filter(edge => edgePassesFilters(edge)).length;
    const hiddenEdges = Math.max(0, filteredEdgeTotal - visibleEdges.length);
    if (count) count.textContent = `${visibleNodes.length} visible nodes · ${visibleEdges.length} visible edges · ${hiddenNodes} nodes and ${hiddenEdges} edges outside this view`;
    if (scopeStatus) scopeStatus.textContent = state.selectedId
      ? "Focused on the selected node and its immediate neighborhood. The complete dataset remains searchable."
      : `Overview shows up to ${OVERVIEW_LIMIT} highly connected matching nodes. Search or select a node to focus its neighborhood.`;

    if (!visibleNodes.length) { renderAccessibleList([]); return; }

    const selectedConnections = state.selectedId ? connectedIds(state.selectedId, visibleEdges) : new Set();
    const edgeLayer = svgElement("g", { class: "relation-map-edges" });
    const nodeLayer = svgElement("g", { class: "relation-map-nodes" });

    for (const edge of visibleEdges) {
      const source = positions.get(String(edge.source));
      const target = positions.get(String(edge.target));
      if (!source || !target) continue;
      const direct = state.selectedId && (String(edge.source) === state.selectedId || String(edge.target) === state.selectedId);
      const line = svgElement("line", {
        x1: source.x, y1: source.y, x2: target.x, y2: target.y,
        class: `graph-edge${state.selectedId && !direct ? " graph-dimmed" : ""}${direct ? " graph-connected" : ""}`,
        "data-edge-id": String(edge.id || ""),
      });
      const title = svgElement("title");
      title.textContent = `${value(edge, "kind", "label") || "relationship"}: ${edge.source} → ${edge.target}; evidence ${evidenceOf(edge)}`;
      line.appendChild(title);
      line.addEventListener("click", () => renderEdgeDetails(edge));
      edgeLayer.appendChild(line);
    }

    for (const node of visibleNodes) {
      const id = String(node.id);
      const pos = positions.get(id);
      const selected = id === state.selectedId;
      const connected = state.selectedId && selectedConnections.has(id);
      const dimmed = state.selectedId && !connected;
      const group = svgElement("g", {
        class: `graph-node${selected ? " selected" : ""}${connected && !selected ? " connected" : ""}${dimmed ? " graph-dimmed" : ""}`,
        role: "button", tabindex: "0", "aria-label": `${labelOf(node)}, ${kindOf(node)}, ${degreeOf(node)} relationships`,
        "data-node-id": id,
      });
      const radius = selected ? 13 : 9;
      const circle = svgElement("circle", { cx: pos.x, cy: pos.y, r: radius, fill: colorForKind(kindOf(node)), class: "node-body" });
      const text = svgElement("text", { x: pos.x + 14, y: pos.y + 4, class: "node-label" });
      text.textContent = labelOf(node).length > 28 ? `${labelOf(node).slice(0, 26)}…` : labelOf(node);
      const title = svgElement("title"); title.textContent = `${labelOf(node)} · ${kindOf(node)} · ${pathOf(node) || "location unavailable"}`;
      group.append(circle, text, title);
      group.addEventListener("click", () => selectNode(id, true));
      group.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectNode(id, true); } });
      nodeLayer.appendChild(group);
    }
    viewport.append(edgeLayer, nodeLayer);
    applyTransform();
    renderAccessibleList(visibleNodes);
  }

  function applyTransform() {
    viewport.setAttribute("transform", `translate(${state.panX} ${state.panY}) scale(${state.scale})`);
  }

  function appendFact(container, label, text) {
    if (text === "" || text === null || text === undefined) return;
    const row = document.createElement("div"); row.className = "relation-detail-fact";
    const dt = document.createElement("strong"); dt.textContent = label;
    const dd = document.createElement("span"); dd.textContent = String(text);
    row.append(dt, dd); container.appendChild(row);
  }

  function relationshipList(titleText, list, direction) {
    const section = document.createElement("section"); section.className = "relation-detail-group";
    const heading = document.createElement("h4"); heading.textContent = `${titleText} (${list.length})`; section.appendChild(heading);
    if (!list.length) { const p = document.createElement("p"); p.className = "muted"; p.textContent = `No ${titleText.toLowerCase()} in the current graph data.`; section.appendChild(p); return section; }
    const ul = document.createElement("ul"); ul.className = "relationship-list";
    list.forEach(edge => {
      const otherId = direction === "incoming" ? String(edge.source) : String(edge.target);
      const li = document.createElement("li");
      const other = byId.get(otherId);
      const targetControl = other ? document.createElement("button") : document.createElement("span");
      if (other) { targetControl.type = "button"; targetControl.className = "relation-link"; targetControl.textContent = labelOf(other); targetControl.addEventListener("click", () => selectNode(otherId, true)); }
      else { targetControl.className = "muted"; targetControl.textContent = `Unresolved target: ${otherId}`; }
      const meta = document.createElement("span"); meta.className = "muted";
      const location = edge.source_file ? ` · ${edge.source_file}` : "";
      meta.textContent = ` ${value(edge, "kind", "label") || "related"} · ${evidenceOf(edge)}${location}`;
      li.append(targetControl, meta); ul.appendChild(li);
    });
    section.appendChild(ul); return section;
  }

  function renderNodeDetails(node) {
    details.replaceChildren();
    if (!node) { const p = document.createElement("p"); p.className = "muted"; p.textContent = "Select a node to inspect its source context and relationships."; details.appendChild(p); return; }
    const title = document.createElement("h3"); title.textContent = labelOf(node); details.appendChild(title);
    const badges = document.createElement("p");
    const kind = document.createElement("span"); kind.className = "badge"; kind.textContent = kindOf(node); badges.appendChild(kind);
    const ev = document.createElement("span"); ev.className = `badge ${evidenceOf(node).toLowerCase()}`; ev.textContent = evidenceOf(node); badges.append(" ", ev); details.appendChild(badges);
    const description = document.createElement("p"); description.textContent = descriptionOf(node) || "Description unavailable."; if (!descriptionOf(node)) description.className = "muted"; details.appendChild(description);
    const facts = document.createElement("div"); facts.className = "relation-detail-facts";
    appendFact(facts, "Qualified name", value(node, "qualified_name"));
    appendFact(facts, "Language", languageOf(node) || "Not recorded");
    appendFact(facts, "Source", pathOf(node) || "Source location unavailable");
    appendFact(facts, "Line", value(node, "line"));
    details.appendChild(facts);
    const links = incident.get(String(node.id)) || { incoming: [], outgoing: [] };
    details.append(relationshipList("Outgoing relationships", links.outgoing, "outgoing"));
    details.append(relationshipList("Incoming relationships", links.incoming, "incoming"));
    const metadata = node.metadata && typeof node.metadata === "object" ? Object.entries(node.metadata) : [];
    if (metadata.length) {
      const disclosure = document.createElement("details"); disclosure.className = "relation-metadata-disclosure";
      const summary = document.createElement("summary"); summary.textContent = "Additional metadata"; disclosure.appendChild(summary);
      const dl = document.createElement("dl");
      metadata.forEach(([key, val]) => { const dt = document.createElement("dt"); dt.textContent = key; const dd = document.createElement("dd"); dd.textContent = typeof val === "object" ? JSON.stringify(val) : String(val); dl.append(dt, dd); });
      disclosure.appendChild(dl); details.appendChild(disclosure);
    }
  }

  function renderEdgeDetails(edge) {
    details.replaceChildren();
    const title = document.createElement("h3"); title.textContent = String(value(edge, "kind", "label") || "Relationship"); details.appendChild(title);
    const p = document.createElement("p"); p.textContent = `${edge.source} → ${edge.target}`; details.appendChild(p);
    const facts = document.createElement("div"); facts.className = "relation-detail-facts";
    appendFact(facts, "Evidence", evidenceOf(edge)); appendFact(facts, "Source file", value(edge, "source_file"));
    const location = value(edge, "source_location"); appendFact(facts, "Source location", typeof location === "object" ? JSON.stringify(location) : location);
    appendFact(facts, "Why this edge exists", value(edge, "explanation") || "Source evidence recorded by the relationship analysis pipeline.");
    details.appendChild(facts);
    const nav = document.createElement("div"); nav.className = "relation-map-actions";
    [["Open source", String(edge.source)], ["Open target", String(edge.target)]].forEach(([label, id]) => {
      if (!byId.has(id)) return;
      const button = document.createElement("button"); button.type = "button"; button.textContent = label; button.addEventListener("click", () => selectNode(id, true)); nav.appendChild(button);
    });
    if (nav.childElementCount) details.appendChild(nav);
  }

  function selectNode(id, remember) {
    const node = byId.get(String(id)); if (!node) return;
    if (remember && state.selectedId && state.selectedId !== String(id)) state.previousSelections.push(state.selectedId);
    state.selectedId = String(id); state.search = ""; if (search) search.value = "";
    renderSearchResults([]); renderNodeDetails(node); renderGraph(); fitGraph();
    const svgNode = svg.querySelector(`[data-node-id="${CSS.escape(String(id))}"]`); if (svgNode) svgNode.focus({ preventScroll: true });
    if (backButton) backButton.disabled = state.previousSelections.length === 0;
  }

  function renderSearchResults(results) {
    if (!searchResults) return; searchResults.replaceChildren();
    if (!state.search) { searchResults.hidden = true; return; }
    searchResults.hidden = false;
    if (!results.length) { const li = document.createElement("li"); li.className = "muted"; li.textContent = "No matching nodes. Clear the search or try another term."; searchResults.appendChild(li); return; }
    results.slice(0, 12).forEach(node => {
      const li = document.createElement("li"); const button = document.createElement("button"); button.type = "button";
      button.textContent = `${labelOf(node)} · ${kindOf(node)}${pathOf(node) ? ` · ${pathOf(node)}` : ""}`;
      button.addEventListener("click", () => selectNode(String(node.id), true)); li.appendChild(button); searchResults.appendChild(li);
    });
  }

  function updateSearch() {
    state.search = normalized(search ? search.value : "");
    const results = state.search ? nodes.filter(node => searchText(node).includes(state.search)) : [];
    renderSearchResults(results);
  }

  function renderAccessibleList(visibleNodes) {
    if (!accessibleList) return; accessibleList.replaceChildren();
    visibleNodes.forEach(node => {
      const li = document.createElement("li"); const button = document.createElement("button"); button.type = "button"; button.className = "relation-link";
      button.textContent = `${labelOf(node)} · ${kindOf(node)} · ${degreeOf(node)} relationships`;
      button.addEventListener("click", () => selectNode(String(node.id), true)); li.appendChild(button); accessibleList.appendChild(li);
    });
  }

  function syncFilters() {
    state.nodeKind = nodeKind ? nodeKind.value : ""; state.edgeKind = edgeKind ? edgeKind.value : "";
    state.language = language ? language.value : ""; state.evidence = evidence ? evidence.value : "";
    if (state.selectedId && !nodePassesFilters(byId.get(state.selectedId))) state.selectedId = null;
    renderNodeDetails(state.selectedId ? byId.get(state.selectedId) : null); renderGraph(); fitGraph();
  }

  function fitGraph() { state.scale = 1; state.panX = 0; state.panY = 0; applyTransform(); }

  populateFilters();
  renderNodeDetails(null);
  renderGraph();

  if (search) search.addEventListener("input", updateSearch);
  [nodeKind, edgeKind, language, evidence].filter(Boolean).forEach(control => control.addEventListener("change", syncFilters));
  if (resetFilters) resetFilters.addEventListener("click", () => {
    [nodeKind, edgeKind, language, evidence].filter(Boolean).forEach(control => { control.value = ""; });
    state.nodeKind = ""; state.edgeKind = ""; state.language = ""; state.evidence = "";
    state.selectedId = null; state.previousSelections = []; if (search) search.value = ""; state.search = ""; renderSearchResults([]); renderNodeDetails(null); renderGraph(); fitGraph(); if (backButton) backButton.disabled = true;
  });
  if (backButton) backButton.addEventListener("click", () => { const previous = state.previousSelections.pop(); if (previous) selectNode(previous, false); backButton.disabled = state.previousSelections.length === 0; });

  document.querySelectorAll("[data-graph-action]").forEach(button => button.addEventListener("click", () => {
    const action = button.dataset.graphAction;
    if (action === "zoom-in") state.scale = Math.min(2.8, state.scale * 1.2);
    if (action === "zoom-out") state.scale = Math.max(0.35, state.scale / 1.2);
    if (action === "fit" || action === "reset-view") fitGraph(); else applyTransform();
  }));

  svg.addEventListener("wheel", event => { event.preventDefault(); state.scale = Math.max(0.35, Math.min(2.8, state.scale * (event.deltaY < 0 ? 1.08 : 0.92))); applyTransform(); }, { passive: false });
  svg.addEventListener("pointerdown", event => { if (event.target.closest && event.target.closest(".graph-node")) return; state.dragging = true; state.dragX = event.clientX - state.panX; state.dragY = event.clientY - state.panY; svg.setPointerCapture(event.pointerId); });
  svg.addEventListener("pointermove", event => { if (!state.dragging) return; state.panX = event.clientX - state.dragX; state.panY = event.clientY - state.dragY; applyTransform(); });
  svg.addEventListener("pointerup", event => { state.dragging = false; if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId); });

  window.BarklyRelationMap = {
    getState: () => ({ ...state, previousSelections: state.previousSelections.slice() }),
    getVisibleCounts: () => { const current = visibleState(); return { nodes: current.visibleNodes.length, edges: current.visibleEdges.length, candidates: current.candidates.length }; },
    selectNode: id => selectNode(String(id), true),
    reset: () => resetFilters && resetFilters.click(),
  };
})();
