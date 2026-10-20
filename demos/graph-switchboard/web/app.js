"use strict";

const $ = (id) => document.getElementById(id);
const methods = ["decision", "llm-cypher"];
const NS = "http://www.w3.org/2000/svg";
let catalog, selected, busy = false, events = [], completed = {}, timer, entrySummary = null;
let readyResults = {};
let lastInput = null;
const vehicleFields = ["make", "model", "year", "configuration"];
let views = {}, traceViews = {}, discovered = {};
let clockAnchors = {};
const traceMethods = ["entry", ...methods];
const graphData = (method) => {
  const store = discovered[method];
  return { nodes: [...(store?.nodes.values() || [])], edges: [...(store?.edges.values() || [])] };
};
const findNode = (method, id) => discovered[method]?.nodes.get(id);
const findEdge = (method, id) => discovered[method]?.edges.get(id);
const number = (value) => new Intl.NumberFormat("en-US").format(value);
const elapsed = (ms) => `${(ms / 1000).toFixed(2)}s`;
const text = (tag, content, cls) => {
  const node = document.createElement(tag);
  node.textContent = content;
  if (cls) node.className = cls;
  return node;
};
function svg(tag, attributes = {}, content) {
  const element = document.createElementNS(NS, tag);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
  if (content !== undefined) element.textContent = content;
  return element;
}
async function getJSON(url) {
  const response = await fetch(url);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
  return body;
}
function nodeTitle(node) {
  if (!node) return "Unknown node";
  const authored = [node.label, node.title, node.description, node.instruction]
    .find(value => typeof value === "string" && value.trim());
  if (authored) return authored;
  if (node.type === "Action") return {
    boolean: "Read self-check flag", categorical: "Read channel status", numeric: "Read supply level",
    range: "Read timing window", dtc: "Check diagnostic code", observation: "Observe indicator",
  }[node.result_type] || "Diagnostic check";
  return node.description || node.id;
}
function ruleTitle(rule = {}) {
  const unit = rule.unit ? ` ${rule.unit}` : "";
  const value = Array.isArray(rule.value) ? rule.value.join(", ") : rule.value;
  return {
    lt: `< ${rule.threshold}${unit}`, gte: `≥ ${rule.threshold}${unit}`,
    between_inclusive: `${rule.minimum}–${rule.maximum}${unit}`,
    outside: `Outside ${rule.minimum}–${rule.maximum}${unit}`,
    contains: `Contains ${value}`, not_contains: `No ${value}`,
    eq: `Equals ${value}`, equals: `Equals ${value}`, in: `One of ${value}`,
  }[rule.operator] || JSON.stringify(rule);
}
function titleLines(title, width) {
  const limit = Math.floor((width - 24) / 5.3), words = title.split(/\s+/), lines = [""];
  for (const word of words) {
    let line = lines.length - 1;
    if (lines[line] && `${lines[line]} ${word}`.length > limit) {
      if (line === 1) { lines[line] = `${lines[line].slice(0, limit - 1)}…`; break; }
      lines.push(""); line += 1;
    }
    lines[line] += `${lines[line] ? " " : ""}${word}`;
  }
  return lines;
}
function procedureData(data, scope, showContext = false) {
  if (!scope || showContext) return data;
  const nodes = data.nodes.filter(node => node.id === scope || node.procedure_id === scope);
  const ids = new Set(nodes.map(node => node.id));
  return { nodes, edges: data.edges.filter(edge => ids.has(edge.source) && ids.has(edge.target)) };
}
function routeData(data, path, target) {
  const selected = new Set(path);
  const edges = data.edges.filter(edge => selected.has(edge.id));
  const ids = new Set([target, ...edges.flatMap(edge => [edge.source, edge.target])]);
  const entries = data.edges.filter(edge => edge.type === "ENTRY_POINT" && ids.has(edge.target));
  entries.forEach(edge => ids.add(edge.source));
  return { nodes: data.nodes.filter(node => ids.has(node.id)), edges: [...entries, ...edges] };
}
function resultState(result = {}, target) {
  if (result.status === "next_action") return target?.handoff ? "Workshop review" : "Recommendation ready";
  return { root_cause: "Finding supported", clarify: "Needs clarification",
    unsupported: "Out of scope", error: "Failed" }[result.status] || "Finished";
}
function positionGraph(data, compact, scope = null) {
  const nodes = new Map(data.nodes.map((n) => [n.id, n]));
  const positions = new Map();
  const edges = data.edges.filter((edge) => nodes.has(edge.source) && nodes.has(edge.target));
  const queue = data.nodes.filter((node) => !edges.some((edge) => edge.target === node.id)).map((node) => [node.id, 0]);
  const levels = new Map(), counts = new Map();
  const place = (id, depth) => {
    if (levels.has(id)) return;
    levels.set(id, depth);
    edges.filter((edge) => edge.source === id).forEach((edge) => queue.push([edge.target, depth + 1]));
  };
  while (levels.size < nodes.size) {
    if (!queue.length) queue.push([data.nodes.find((node) => !levels.has(node.id)).id, 0]);
    while (queue.length) place(...queue.shift());
  }
  const scoped = (id) => scope && (id === scope || nodes.get(id)?.procedure_id === scope);
  const scopedCounts = new Map();
  for (const [id, depth] of levels) if (scoped(id)) scopedCounts.set(depth, (scopedCounts.get(depth) || 0) + 1);
  const scopedColumns = Math.max(0, ...scopedCounts.values());
  for (const [id, depth] of [...levels].sort(([a], [b]) => Number(Boolean(scoped(b))) - Number(Boolean(scoped(a))))) {
    // Leave room for the active scope before the other retrieved procedures.
    const column = Math.max(counts.get(depth) || 0, scope && !scoped(id) ? scopedColumns + 3 : 0);
    counts.set(depth, column + 1);
    positions.set(id, { x: 95 + column * (compact ? 174 : 190), y: 40 + depth * 88, w: 155 });
  }
  return { nodes, positions };
}
function procedureViewport(data, positions, scope, focusId, width, height) {
  const scoped = data.nodes.filter(node => node.procedure_id === scope || node.id === scope)
    .map(node => positions.get(node.id)).filter(Boolean);
  if (!scoped.length) return null;
  const left = Math.min(...scoped.map(p => p.x - p.w / 2)) - 18;
  const right = Math.max(...scoped.map(p => p.x + p.w / 2)) + 18;
  const top = Math.min(...scoped.map(p => p.y - 23)) - 18;
  const bottom = Math.max(...scoped.map(p => p.y + 23)) + 18;
  const focus = positions.get(focusId) || positions.get(scope) || scoped[0];
  const boxWidth = Math.min(Math.max(310, right - left), width / .8);
  const boxHeight = Math.min(Math.max(200, 2 * Math.max(focus.y - top, bottom - focus.y)), height / .8);
  return {
    x: focus.x - boxWidth / 2,
    y: focus.y - boxHeight / 2,
    width: boxWidth, height: boxHeight,
  };
}
function inspectNode(method, node) {
  pauseTrace(method);
  $(`${method}-inspector-title`).textContent = "Node properties";
  $(`${method}-time`).textContent = "Manual inspection";
  focusTrace(method, { node: node.id });
  const panel = $(`${method}-inspector`);
  panel.replaceChildren(text("h4", nodeTitle(node)), text("p", node.instruction || node.description || "", "node-description"));
  const properties = text("dl", "", "node-properties");
  for (const key of ["id", "type", "result_type", "expected_unit", "source_reference"]) {
    if (node[key] === undefined) continue;
    properties.append(text("dt", key.replaceAll("_", " ")), text("dd", String(node[key])));
  }
  const details = document.createElement("details");
  details.append(text("summary", "All properties"), text("pre", JSON.stringify(node, null, 2)));
  panel.append(properties, details);
}
function renderGraph(method, preserve = false, resetViewport = false) {
  const host = $(`${method}-graph`);
  const previous = preserve ? views[method] : null;
  host.replaceChildren();
  const root = svg("svg", { viewBox: "0 0 620 535", role: "group", tabindex: "0", "aria-label": `${method} procedure graph. Drag to pan. Control-scroll or plus and minus to zoom. Zero to fit. Select a node to inspect properties.` });
  const defs = svg("defs");
  for (const active of [false, true]) {
    const marker = svg("marker", { id: `${method}-arrow-${active}`, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 5, markerHeight: 5, orient: "auto-start-reverse" });
    marker.append(svg("path", { d: "M0 1 L9 5 L0 9 Z", fill: active ? "var(--cp-accent)" : "var(--cp-border-strong)" }));
    defs.append(marker);
  }
  root.append(defs);
  const layer = svg("g");
  root.append(layer);
  const retrieved = graphData(method);
  const answerRoute = previous?.answerRoute;
  const showRoute = answerRoute && !previous?.showContext;
  const focused = answerRoute ? routeData(retrieved, answerRoute.path, answerRoute.target)
    : procedureData(retrieved, previous?.layoutScope);
  const data = previous?.showContext ? retrieved : focused;
  host.style.height = showRoute ? `${Math.max(350, data.nodes.length * 88 + 36)}px` : "";
  const contextButton = document.querySelector(`.graph-context[data-method="${method}"]`);
  contextButton.disabled = !previous?.layoutScope
    || (focused.nodes.length === retrieved.nodes.length && focused.edges.length === retrieved.edges.length);
  contextButton.setAttribute("aria-pressed", String(Boolean(previous?.showContext)));
  contextButton.textContent = previous?.showContext ? answerRoute ? "Answer route" : "Selected procedure" : "All retrieved";
  contextButton.title = previous?.showContext ? "Return to the selected route" : "Show all retrieved candidates and vehicle-applicability links";
  root.dataset.graphContext = showRoute ? "route" : previous?.showContext || !previous?.layoutScope ? "all" : "procedure";
  const { nodes, positions } = positionGraph(data, host.clientWidth < 500, previous?.layoutScope);
  const edgeElements = new Map(), nodeElements = new Map();
  for (const edge of data.edges) {
    const a = positions.get(edge.source), b = positions.get(edge.target);
    if (!a || !b) continue;
    const vertical = a.x === b.x;
    const start = vertical ? { x: a.x, y: a.y + 23 } : { x: a.x + a.w / 2, y: a.y };
    const end = vertical ? { x: b.x, y: b.y - 23 } : { x: b.x - b.w / 2, y: b.y };
    const d = vertical ? `M${start.x} ${start.y}L${end.x} ${end.y}`
      : `M${start.x} ${start.y}C${(start.x + end.x) / 2} ${start.y} ${(start.x + end.x) / 2} ${end.y} ${end.x} ${end.y}`;
    const path = svg("path", { d, class: "edge read", "data-edge-id": edge.id, "marker-end": `url(#${method}-arrow-false)` });
    const label = svg("text", {
      x: vertical ? a.x + 7 : (start.x + end.x) / 2,
      y: vertical ? (start.y + end.y) / 2 + 2 : start.y - 8,
      class: "edge-label", "text-anchor": vertical ? "start" : "middle",
    }, edge.rule ? ruleTitle(edge.rule) : edge.type.replaceAll("_", " ").toLowerCase());
    path.append(svg("title", {}, `${edge.type}: ${edge.description || edge.id}`));
    layer.append(path, label);
    edgeElements.set(edge.id, { path, label });
  }
  for (const [id, p] of positions) {
    const node = nodes.get(id);
    const group = svg("g", { class: "graph-node read", "data-node-id": id, transform: `translate(${p.x},${p.y})`, tabindex: "0", role: "button", "aria-label": `${node.type}: ${nodeTitle(node)}` });
    group.append(svg("title", {}, `${node.type}: ${node.description || node.title}`));
    group.append(svg("rect", { x: -p.w / 2, y: -23, width: p.w, height: 46, rx: 7, class: "halo" }));
    group.append(svg("rect", { x: -p.w / 2, y: -23, width: p.w, height: 46, rx: 7 }));
    group.append(svg("text", { x: -p.w / 2 + 12, y: -7, class: "node-type" }, node.type.toUpperCase()));
    titleLines(nodeTitle(node), p.w).forEach((line, index) => {
      group.append(svg("text", { x: -p.w / 2 + 12, y: 6 + index * 12, class: "node-title" }, line));
    });
    const icon = svg("circle", { cx: p.w / 2 - 12, cy: -9, r: 2.5, class: "node-icon" });
    group.append(icon);
    group.addEventListener("click", () => inspectNode(method, node));
    group.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); inspectNode(method, node); } });
    layer.append(group);
    nodeElements.set(id, group);
  }
  host.append(root);
  if (!nodes.size) layer.append(svg("text", { x: 155, y: 100, class: "graph-empty", "text-anchor": "middle" }, "No graph data retrieved yet"));
  const bounds = nodes.size ? layer.getBBox() : { x: 0, y: 0, width: 310, height: 200 };
  const box = { x: bounds.x - 18, y: bounds.y - 18, width: bounds.width + 36, height: bounds.height + 36 };
  root.setAttribute("viewBox", `${box.x} ${box.y} ${box.width} ${box.height}`);
  const view = { root, layer, nodeElements, edgeElements, visited: new Set(), current: null, reads: 0,
    zoom: 1, dx: 0, dy: 0, mode: previous?.mode || "auto", scope: previous?.scope,
    layoutScope: previous?.layoutScope, focusId: previous?.focusId,
    showContext: Boolean(previous?.showContext), answerRoute, box };
  const scopedBox = () => procedureViewport(data, positions, view.scope, view.focusId, host.clientWidth, host.clientHeight);
  if (previous && !resetViewport && (view.mode === "manual" || !traceViews[method]?.follow)) view.box = previous.box;
  else if (!showRoute && view.mode === "auto" && view.scope) view.box = scopedBox() || box;
  const transform = () => {
    const frame = view.box;
    root.setAttribute("viewBox", `${frame.x - view.dx} ${frame.y - view.dy} ${frame.width / view.zoom} ${frame.height / view.zoom}`);
    root.dataset.viewportMode = view.mode;
    if (view.scope) root.dataset.procedureScope = view.scope;
  };
  view.focusProcedure = (scope, focusId) => {
    if (!scope) return;
    view.scope = scope; view.focusId = focusId;
    if (view.layoutScope !== scope) {
      view.layoutScope = scope;
      renderGraph(method, true);
      return;
    }
    if (view.mode !== "auto" || !traceViews[method]?.follow) return;
    view.box = view.answerRoute && !view.showContext ? box : scopedBox() || box;
    view.dx = 0; view.dy = 0; view.zoom = 1; transform();
  };
  view.fit = () => { view.mode = "overview"; view.box = box; view.dx = 0; view.dy = 0; view.zoom = 1; transform(); };
  root.addEventListener("keydown", (event) => {
    if (!["+", "=", "-", "0"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "0") view.fit();
    else { view.mode = "manual"; view.zoom = Math.min(3, Math.max(.65, view.zoom * (event.key === "-" ? .9 : 1.1))); transform(); }
  });
  root.addEventListener("wheel", (event) => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    view.mode = "manual";
    view.zoom = Math.min(2.5, Math.max(.65, view.zoom * (event.deltaY < 0 ? 1.1 : .9)));
    transform();
  }, { passive: false });
  let drag;
  root.addEventListener("pointerdown", (event) => {
    if (event.target.closest(".graph-node")) return;
    drag = { x: event.clientX, y: event.clientY, dx: view.dx, dy: view.dy };
    view.mode = "manual";
    root.setPointerCapture(event.pointerId);
  });
  root.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const scale = Math.max(view.box.width / root.clientWidth, view.box.height / root.clientHeight) / view.zoom;
    view.dx = drag.dx + (event.clientX - drag.x) * scale;
    view.dy = drag.dy + (event.clientY - drag.y) * scale;
    transform();
  });
  root.addEventListener("pointerup", () => { drag = null; });
  root.addEventListener("pointercancel", () => { drag = null; });
  views[method] = view;
  transform();
  if (previous) {
    view.reads = previous.reads;
    if (!resetViewport) { view.zoom = previous.zoom; view.dx = previous.dx; view.dy = previous.dy; }
    transform();
    previous.nodeElements.forEach((node, id) => {
      view.nodeElements.get(id)?.setAttribute("class", node.getAttribute("class"));
    });
    previous.edgeElements.forEach((edge, id) => {
      if (edge.path.classList.contains("visited")) highlightEdge(method, id);
      else if (edge.path.classList.contains("pending")) view.edgeElements.get(id)?.path.classList.add("pending");
    });
    const trace = traceViews[method];
    if (trace?.selected !== null && trace?.steps[trace.selected]) focusTrace(method, trace.steps[trace.selected]);
  }
}
function highlightEdge(method, id) {
  const view = views[method], edge = view.edgeElements.get(id);
  if (!edge) return;
  edge.path.classList.add("visited");
  edge.path.classList.remove("pending");
  edge.path.setAttribute("marker-end", `url(#${method}-arrow-true)`);
  edge.label.classList.add("visited");
  const data = findEdge(method, id);
  if (!data) return;
  [data.source, data.target].forEach((node) => view.nodeElements.get(node)?.classList.add("visited"));
  view.visited.add(id);
}
function metricGrid(method, result) {
  const metrics = [
    ["Elapsed", result ? elapsed(result.elapsed_ms) : "--", "end to end"],
    ["Input tokens", result ? number(result.input_tokens) : "--", "provider reported"],
    ["Output tokens", result ? number(result.output_tokens) : "--", "includes reasoning"],
    ["Est. cost", result ? (result.estimated_cost_usd == null ? "—" : `$${result.estimated_cost_usd.toFixed(6)}`) : "--", "configured token rates"],
    [method === "entry" ? "Phase" : "Path hops", result ? (method === "entry" ? entrySummary?.result?.status || "resolved" : result.hops) : "--", "returned / followed edges"],
    ["Model calls", result ? result.inference_calls : "--", "actual requests"],
    ["Graph queries", result ? result.graph_queries : "--", "includes controller reads"],
    ["Expected match", result ? (result.score ? (result.score.exact ? "Exact" : "Mismatch") : "Unscored") : "--", result?.score ? "status + target + path" : "unchanged cases only"],
  ];
  const host = $(`${method}-metrics`);
  host.replaceChildren(...metrics.map(([label, value, hint]) => {
    const item = text("div", "", "metric");
    item.title = hint;
    item.append(text("span", label), text("strong", String(value)), text("small", hint));
    if (label === "Expected match" && result?.score) item.querySelector("strong").className = result.score.exact ? "match" : "mismatch";
    return item;
  }));
  if (result && method !== "entry") {
    const breakdown = text("details", "", "call-breakdown");
    breakdown.append(text("summary", "Call breakdown"));
    const deployments = Object.entries(result.model_calls_by_deployment || {});
    breakdown.append(text("p", deployments.map(([name, count]) => `${name}: ${count}`).join(" · ") || "Deployment usage unavailable"));
    const entry = result.entry_metrics, traversal = result.traversal_metrics;
    if (entry && traversal) breakdown.append(text("p",
      `MD1 entry ${entry.inference_calls} calls / ${elapsed(entry.elapsed_ms)} · traversal ${traversal.inference_calls} calls / ${elapsed(traversal.elapsed_ms)}. Both phases are included.`));
    host.append(breakdown);
  }
}
function setState(method, state, running = false) {
  const node = $(`${method}-state`);
  node.textContent = state;
  node.classList.toggle("running", running);
}
function decisionInspector(event) {
  const method = event.method || "decision";
  const host = $(`${method}-inspector`);
  host.replaceChildren();
  $(`${method}-inspector-title`).textContent = "Option probabilities";
  $(`${method}-time`).textContent = elapsed(event.elapsed_ms);
  decisionInput(host, event.request);
  for (const [id, p] of Object.entries(event.probabilities)) {
    const row = text("div", "", `choice-row${id === event.selected ? " chosen" : ""}`);
    const label = choiceTitle(id, method);
    const name = text("span", `${id === event.selected ? "\u2192 " : ""}${label}`, "choice-name");
    name.title = label;
    const bar = text("div", "", "bar"), fill = text("i", "");
    fill.style.transform = `scaleX(${p})`; bar.append(fill);
    row.append(name, bar, text("span", `${(p * 100).toFixed(1)}%`, "choice-value"));
    host.append(row);
  }
  host.append(text("p", `Option scores · gate threshold ${catalog.threshold.toFixed(2)}`, "inspector-note"));
}
function stepField(host, label, value) {
  const section = text("div", "", "step-section");
  section.append(text("span", label, "eyebrow"), text("p", value));
  host.append(section);
}
function stepJSON(host, label, value, open = false) {
  const details = document.createElement("details");
  details.open = open;
  details.append(text("summary", label), text("pre", typeof value === "string" ? value : JSON.stringify(value, null, 2)));
  host.append(details);
}
function modelOutput(event) {
  const response = event?.response || {};
  if (response.answers) return response.answers;
  const content = response.choices?.[0]?.message?.content;
  if (typeof content !== "string") return response;
  try { return JSON.parse(content); }
  catch (error) { if (!(error instanceof SyntaxError)) throw error; return content; }
}
function modelInput(host, event) {
  const request = event.request;
  stepField(host, "Actual model request", `${event.deployment} · call ${event.call_index} · ${event.api_path}`);
  if (request.messages) {
    const firstUser = request.messages.find(message => message.role === "user");
    if (firstUser) {
      let input;
      try { input = JSON.parse(firstUser.content); }
      catch (error) { if (!(error instanceof SyntaxError)) throw error; }
      if (input?.question) {
        stepField(host, "User problem received by Sol", input.question);
        stepJSON(host, "Observations received by Sol", input.evidence, true);
      }
    }
    request.messages.forEach((message, index) => stepJSON(host, `${index + 1}. ${message.role} message sent to Sol`, message.content, true));
    stepField(host, "API settings", `Reasoning effort: ${request.reasoning_effort}; output limit: ${request.max_completion_tokens} tokens.`);
  } else {
    decisionInput(host, { state: request.state, instructions: request.questions?.transition?.instructions,
      criteria: request.questions?.transition?.criteria });
  }
  stepJSON(host, "Exact API request body (no credentials)", request);
}
function modelResult(host, response) {
  if (!response) {
    host.append(text("p", "Waiting for the actual model response.", "muted"));
    return;
  }
  if (response.error) stepField(host, "Model error", response.error);
  stepJSON(host, "Actual structured model output", modelOutput(response), true);
  stepField(host, "Response received", `${elapsed(response.elapsed_ms)} from this standalone lane's start · ${elapsed(response.latency_ms)} model request latency.`);
  stepJSON(host, "Returned API fields and usage", response.response);
}
function intakeEvent(event) {
  const shared = events.filter(item => item.method === "entry");
  const calls = shared.filter(item => item.event === "model_request").length;
  const queries = shared.filter(item => item.event === "graph_query").length;
  const candidates = new Set(shared.filter(item => item.event === "entry_candidates").flatMap(item => item.candidates.map(node => node.id)));
  const reused = shared.some(item => item.policy === "reuse_own_verified_entry");
  for (const method of ["decision"]) {
    const button = document.querySelector(`.shared-intake-step[data-method="${method}"]`);
    button.disabled = calls === 0 && !reused;
    button.querySelector("span").textContent = reused
      ? "Own MD1 entry reused · no new entry model call"
      : `${calls} MD1 calls · ${queries} fixed reads · ${candidates.size} eligible entries · ${entrySummary?.result?.status || "in progress"}`;
  }
  if (event.event === "model_request") {
    const host = $("entry-requests");
    host.querySelector(".empty-note")?.remove();
    const call = text("article", "", "model-call");
    call.dataset.callIndex = event.call_index;
    call.append(text("h4", `MD1 entry call ${event.call_index}`));
    modelInput(call, event);
    call.append(text("div", "Waiting for the actual model response.", "model-output muted"));
    host.append(call);
  } else if (event.event === "model_response") {
    const call = [...$("entry-requests").children].find(node => node.dataset.callIndex === String(event.call_index));
    if (call) {
      const output = call.querySelector(".model-output");
      output.classList.remove("muted");
      output.replaceChildren();
      modelResult(output, event);
    }
  } else if (event.event === "graph_query") {
    const host = $("entry-queries");
    host.querySelector(".empty-note")?.remove();
    const query = text("article", "", "entry-query");
    query.dataset.queryId = event.query_id;
    query.append(text("h4", `Python query ${event.query_id}`),
      text("pre", event.cypher, "code-line"), text("div", "Waiting for AGE.", "query-candidates muted"));
    stepJSON(query, "Bound parameters", event.parameters);
    host.append(query);
  } else if (event.event === "graph_rows" || event.event === "entry_candidates") {
    const query = event.event === "entry_candidates"
      ? $("entry-queries").lastElementChild
      : [...$("entry-queries").children].find(node => node.dataset.queryId === String(event.query_id));
    if (!query) return;
    const host = query.querySelector(".query-candidates");
    host.classList.remove("muted");
    host.replaceChildren(text("p", event.error || `${event.rows.length} AGE rows${event.candidates ? ` · ${event.candidates.length} eligible entries` : ""}.`));
    if (!event.error && event.candidates) {
      const table = text("table", "", "candidate-table");
      const header = text("tr", "");
      ["Node / type", "Returned diagnostic state", "Selection"].forEach(label => header.append(text("th", label)));
      const head = document.createElement("thead"), body = document.createElement("tbody");
      head.append(header); table.append(head, body);
      const procedures = new Map(event.procedures.map(node => [node.id, node]));
      event.candidates.forEach(node => {
        const row = text("tr", "");
        row.dataset.candidateId = node.id;
        const identity = text("td", "");
        identity.append(text("code", node.id), text("span", node.type, "candidate-state"));
        const description = text("td", "");
        description.append(text("span", node.description || node.instruction || node.id),
          text("span", procedures.get(node.procedure_id)?.title || node.procedure_id, "candidate-state"));
        row.append(identity, description, text("td", "Returned", "candidate-status"));
        body.append(row);
      });
      host.append(table);
      if (!event.candidates.length) host.append(text("p", "No starting-node property maps were returned by this query.", "muted"));
      stepJSON(host, "All candidate and procedure properties", { candidates: event.candidates, procedures: event.procedures });
      stepJSON(host, "Exact AGE rows", event.rows);
    }
  } else if (event.event === "entry_policy") {
    $("entry-selection").replaceChildren(text("p", event.reason));
    $("entry-requests").replaceChildren(text("p", "No model call: " + event.reason, "muted"));
  } else if (event.event === "entry_selected" || event.event === "entry_ready") {
    if (reused) {
      $("entry-requests").replaceChildren(text("p", "No new entry call. Python revalidated this lane's own earlier MD1 selection."));
    }
    const identifier = event.node || event.result?.target;
    const node = findNode("entry", identifier), procedure = findNode("entry", node?.procedure_id);
    const host = $("entry-selection");
    host.replaceChildren();
    if (identifier) {
      host.append(text("p", `${node?.description || identifier}`), text("code", identifier),
        text("p", `${procedure?.title || node?.procedure_id || ""} · publication and vehicle applicability verified.`),
        text("p", "MD1 selected this returned entry; Python validates it before traversal.", "muted"));
      const links = text("nav", "", "handoff-links");
      for (const [id, label] of [["decision-lane", "MD1 traversal"], ["llm-cypher-lane", "Independent Sol-only run"]]) {
        const link = text("a", label); link.href = `#${id}`; links.append(link);
      }
      host.append(links);
      $("entry-queries").querySelectorAll("[data-candidate-id]").forEach(row => {
        const selected = row.dataset.candidateId === identifier;
        row.classList.toggle("selected", selected);
        row.querySelector(".candidate-status").textContent = selected ? "Selected by MD1; verified by Python" : "Not selected";
      });
    } else host.append(text("p", event.result?.error || event.result?.reason || `Entry ${event.result?.status}. No starting node is substituted.`));
  }
}
function choiceTitle(id, method = "decision") {
  if (id === "__clarify__") return "Clarify observation";
  if (id === "__next_action__") return "Request the next check";
  if (id === "__unsupported__") return "Outside published guidance";
  const edge = findEdge(method, id);
  return edge?.rule ? ruleTitle(edge.rule) : findNode(method, id)?.description || id;
}
function decisionInput(host, request) {
  if (!request) return;
  const state = request.state || {};
  stepField(host, "Decision question", request.instructions || "Select a supported transition.");
  if (!state.current_node) {
    stepField(host, "Original problem", state.question || "");
    stepJSON(host, "Selected vehicle", state.vehicle);
    stepJSON(host, "Supplied records", state.evidence || []);
    stepJSON(host, "Exact entry criteria", request);
    return;
  }
  stepField(host, "Current check", state.current_node.instruction || nodeTitle(state.current_node));
  const evidence = state.evidence || [];
  const relevant = evidence.filter((item) => item.action_id === state.current_node?.id
    || [state.current_node?.description, state.current_node?.instruction, nodeTitle(state.current_node)].includes(item.check));
  stepField(host, "Observation for this check", relevant.length
    ? relevant.map((item) => item.observation).join("\n") : evidence.length
      ? "No exact check-label match in the UI. The model receives all observations below and interprets which check they refer to."
      : "No observations were supplied.");
  if (!relevant.length && evidence.length) stepJSON(host, "All supplied observations", evidence, true);
  stepJSON(host, "Full model input and branch criteria", request, true);
}
function stepMeta(event) {
  const node = findNode(event.method, event.node);
  const model = catalog.baseline_deployment;
  const edge = findEdge(event.method, event.edge);
  const metadata = {
    entry_start: ["Select an entry from the original problem", "MD1 entry", true],
    entry_selected: [event.policy === "reuse_own_verified_entry" ? "Reuse this lane's MD1 entry" : "MD1 selected the start; Python verified it", "MD1 entry"],
    entry_candidates: [`AGE returned ${event.candidates?.length || 0} starting-state candidates`, "Apache AGE"],
    entry_ready: [`Entry selection: ${event.result?.status}`, "MD1 entry"],
    entry_policy: [event.reason, "Python eligibility policy"],
    entry_decision_pending: ["Choose an eligible entry", "Decision-1", true],
    entry_decision: [`Entry choice: ${choiceTitle(event.selected, "entry")}`, "Decision-1"],
    graph_data: [`Discovered ${event.nodes?.length || 0} nodes / ${event.edges?.length || 0} edges`, "Successful AGE read"],
    start: [event.method === "decision" ? "Traverse from the verified MD1 entry" : "Use this lane's original input and released evidence", "Python controller (not an LLM)"],
    scope_checked: [event.eligible ? "Publication and applicability checked" : "Procedure blocked by policy", "Controller"],
    current: [node?.type === "RootCause" ? "Root cause reached" : `At ${nodeTitle(node)}`, "Controller"],
    decision_pending: ["Ask Decision-1 to select a result", "Decision-1", true],
    decision: [`Selected: ${choiceTitle(event.selected)}`, "Decision-1"],
    traversed: [event.policy === "mandatory_published_edge"
      ? (edge?.type === "INDICATES" ? "Follow the published cause" : "Follow the mandatory next action")
      : "Advance along the selected result", "Controller"],
    cypher_pending: [event.successful_reads ? "Interpret returned rows / choose next response" : "Generate a graph query", `${model} · request ${event.turn || 1}`, true],
    cypher: ["Execute generated openCypher", "Apache AGE", true],
    graph_result: [event.error ? "Query rejected or failed" : `Returned ${event.rows?.length || 0} database rows`, "Apache AGE"],
    graph_query: [event.cypher?.includes("(n)-[r]->(m)") ? "Read neighbours with fixed Cypher" : "Read graph with fixed Cypher", "Controller → Apache AGE", true],
    graph_rows: [event.error ? "Fixed query failed" : `Returned ${event.rows?.length || 0} fixed-query rows`, "Apache AGE"],
    answer_path: [`Validated ${event.path?.length || 0}-hop answer path`, "Controller"],
    answer_rejected: ["Sol answer rejected by path validation", "Controller"],
    lane_ready: [resultState(event.result, findNode(event.method, event.result?.target)),
      "Inference finished; comparison save pending"],
    complete: [resultState(event.result, findNode(event.method, event.result?.target)), "Comparison saved"],
  };
  if (event.event === "model_request") {
    const response = event.paired_response, output = modelOutput(response);
    const isDecision = Boolean(event.request.questions);
    const choice = output?.transition?.choice;
    return { title: response?.error ? "Model call failed" : !response
      ? `${isDecision ? "MD1 selects a route" : event.method === "entry" ? "Sol finds the starting state" : "Sol queries or answers"} · awaiting response`
      : isDecision ? `MD1 selected: ${choiceTitle(choice, event.method)}` : output?.kind === "query" ? "Sol generated Cypher"
        : event.method === "entry" ? "Sol returned its entry selection" : "Sol returned its answer",
    source: `${event.deployment} · call ${event.call_index}`, pending: !response };
  }
  if (event.event === "model_response") return {
    title: event.error ? "Model request failed" : "Model response received", source: event.deployment, pending: false,
  };
  if (event.paired_response && ["cypher", "graph_query"].includes(event.event)) {
    const response = event.paired_response;
    return { title: response.error ? "Graph query failed" : event.event === "cypher"
      ? `Sol Cypher → ${response.rows?.length || 0} AGE rows`
      : `Python retrieved ${response.rows?.length || 0} possible next steps`,
    source: event.event === "cypher" ? "Sol → Apache AGE" : "Python controller → Apache AGE", pending: false };
  }
  const [title, source, pending = false] = metadata[event.event] || [event.event, "Controller"];
  return { title, source: source === "Controller" ? "Python controller (not an LLM)" : source, pending };
}
function focusTrace(method, event) {
  const view = views[method];
  if (!view) return;
  view.nodeElements.forEach((node) => node.classList.remove("trace-focus"));
  view.edgeElements.forEach(({ path }) => path.classList.remove("trace-focus"));
  const ids = new Set([event.node, event.start_node, event.source, event.target, event.result?.target, event.parameters?.id]);
  const edges = [event.edge, event.selected, ...(event.path || [])];
  for (const id of edges) {
    const edge = findEdge(method, id);
    if (!edge) continue;
    view.edgeElements.get(id)?.path.classList.add("trace-focus");
    ids.add(edge.source); ids.add(edge.target);
  }
  ids.forEach((id) => view.nodeElements.get(id)?.classList.add("trace-focus"));
}
function pauseTrace(method) {
  const trace = traceViews[method];
  if (!trace) return;
  trace.follow = false;
  trace.selected = null;
  trace.intake = false;
  document.querySelector(`.shared-intake-step[data-method="${method}"]`)?.removeAttribute("aria-current");
  document.querySelector(`.follow[data-method="${method}"]`).setAttribute("aria-pressed", "false");
  $(`${method}-steps`).querySelectorAll("button").forEach((button) => button.removeAttribute("aria-current"));
}
function showSharedIntake(method) {
  pauseTrace(method);
  traceViews[method].intake = true;
  document.querySelector(`.shared-intake-step[data-method="${method}"]`).setAttribute("aria-current", "step");
  const host = $(`${method}-inspector`);
  host.replaceChildren(text("p", "Step 1 · Python retrieves published entries; MD1 selects from the original input.", "step-source"));
  const shared = events.filter(event => event.method === "entry");
  for (const event of shared) {
    if (event.event === "model_request") {
      modelInput(host, event);
      modelResult(host, shared.find(item => item.event === "model_response" && item.call_index === event.call_index));
    } else if (event.event === "graph_query") {
      host.append(text("h4", "Python's fixed query"), text("pre", event.cypher, "code-line"));
      stepJSON(host, "Bound parameters", event.parameters);
    } else if (event.event === "entry_candidates") {
      stepJSON(host, "Actual returned starting-state candidates", event.candidates, true);
      stepJSON(host, "Exact AGE rows", event.rows);
    } else if (event.event === "graph_result" && event.error) {
      stepField(host, "Graph query error", event.error);
    }
  }
  if (entrySummary) stepJSON(host, "Starting-state selection / handoff", entrySummary.result, true);
  $(`${method}-inspector-title`).textContent = "1. MD1 entry selection";
  $(`${method}-time`).textContent = entrySummary ? elapsed(entrySummary.metrics.elapsed_ms) : "In progress";
}
function showTraceStep(method, index) {
  const trace = traceViews[method], event = { ...trace.steps[index], paired_response: trace.responses.get(index) }, meta = stepMeta(event);
  trace.selected = index;
  trace.intake = false;
  document.querySelector(`.shared-intake-step[data-method="${method}"]`)?.removeAttribute("aria-current");
  const host = $(`${method}-inspector`);
  host.replaceChildren(text("p", `${meta.source} · recorded step ${index + 1}`, "step-source"));
  const node = findNode(method, event.node || event.start_node || event.result?.target || event.target);
  if (event.event === "model_request") {
    if (event.request.questions && event.paired_response?.response?.answers?.transition?.probabilities) {
      const answer = event.paired_response.response.answers.transition, transition = event.request.questions.transition;
      decisionInspector({ ...event, request: { instructions: transition.instructions, state: event.request.state, criteria: transition.criteria },
        selected: answer.choice, probabilities: answer.probabilities });
    } else modelInput(host, event);
    modelResult(host, event.paired_response);
    if (event.request.questions) stepJSON(host, "Exact API request body (no credentials)", event.request);
  } else if (event.event === "model_response") {
    modelResult(host, event);
  } else if (event.event === "decision") {
    decisionInspector(event);
    host.prepend(text("p", `${meta.source} · recorded step ${index + 1}`, "step-source"));
  } else if (event.event === "decision_pending") {
    decisionInput(host, event.request);
    const options = text("ul", "", "step-criteria");
    (event.options || []).forEach((id) => options.append(text("li", choiceTitle(id, method))));
    host.append(options);
  } else if (event.event === "cypher_pending") {
    stepField(host, "Model task", event.successful_reads
      ? "Interpret the actual AGE results. Return an answer path or request another query."
      : "Generate a read-only query using the supplied graph schema, question and observations.");
    (event.messages || []).forEach((message, position) => {
      stepJSON(host, `${position + 1}. ${message.role} message`, message.content, true);
    });
  } else if (["cypher", "graph_result", "graph_query", "graph_rows"].includes(event.event)) {
    stepField(host, "Query author", event.event.startsWith("graph_") && event.event !== "graph_result"
      ? "Application controller: fixed Cypher, not generated by either model."
      : `${catalog.baseline_deployment}: model-generated openCypher.`);
    host.append(text("pre", event.cypher, "code-line"));
    if (event.parameters) {
      stepJSON(host, "Bound parameters", event.parameters, true);
      stepField(host, "Query with actual values", "Display only: AGE executes the parameterised template above, with these exact bindings.");
      host.append(text("pre", event.resolved_cypher, "code-line"));
    }
    const response = event.paired_response || (["graph_result", "graph_rows"].includes(event.event) ? event : null);
    if (response) {
      stepField(host, response.error ? "Database error" : "Database response",
        response.error || `${response.rows?.length || 0} rows returned from PostgreSQL / Apache AGE.`);
      if (!response.error) {
        const rows = (response.rows || []).map((row) => {
          if (typeof row !== "string") return row;
          try { return JSON.parse(row.replace(/::(?:vertex|edge|path)\b/g, "")); }
          catch (error) { if (!(error instanceof SyntaxError)) throw error; return { raw_agtype: row }; }
        });
        stepJSON(host, "Returned rows", rows, true);
      }
    }
  } else if (event.event === "traversed") {
    const edge = findEdge(method, event.edge);
    stepField(host, "Transition", `${nodeTitle(findNode(method, event.source))} → ${nodeTitle(node)}`);
    stepField(host, "Why this step ran", event.policy === "mandatory_published_edge"
      ? "The published procedure has one mandatory continuation. The controller follows it without a model call."
      : "The controller applies the RESULT edge selected by Decision-1.");
    if (edge?.rule) stepField(host, "Published result rule", ruleTitle(edge.rule));
  } else if (event.event === "start" || event.event === "entry_start") {
    stepField(host, "Diagnostic question", event.question);
    stepField(host, event.event === "entry_start" || method === "llm-cypher" ? "Vehicle" : "Verified starting node", event.event === "entry_start" || method === "llm-cypher" ? event.vehicle_id : nodeTitle(node));
    stepJSON(host, "Supplied observations", event.evidence, true);
    if (event.event === "start" && method === "decision") {
      stepField(host, "Where this ID came from", `${event.start_node} was selected by MD1 from actual AGE entries. Sol-only does not receive it.`);
      const link = text("a", "View entry selection details"); link.href = "#entry-stage"; host.append(link);
    }
    if (event.messages || event.entry_messages) stepJSON(host, "Actual model messages", event.messages || event.entry_messages, true);
  } else if (event.event === "entry_ready") {
    stepJSON(host, "Entry resolution output", event.result, true);
    stepJSON(host, "Entry phase metrics", event.metrics, true);
    stepJSON(host, "Actual entry chat history", event.messages, true);
  } else if (event.event === "graph_data") {
    stepField(host, "Provenance", `Successful AGE read · query ${event.query_id} · ${event.model_authored ? "model-authored" : "controller-authored"}`);
    stepJSON(host, "Retrieved node properties", event.nodes, true);
    stepJSON(host, "Retrieved edge properties", event.edges, true);
  } else if (event.event === "entry_candidates") {
    if (event.cypher) host.append(text("pre", event.cypher, "code-line"));
    stepJSON(host, "Returned starting-state candidates", event.candidates, true);
    stepJSON(host, "Returned procedures", event.procedures, true);
  } else if (event.event === "scope_checked") {
    stepField(host, "Procedure policy", event.eligible
      ? "This procedure is published and applies to the supplied vehicle. Traversal may proceed."
      : "Publication or vehicle applicability prevents traversal. Neither model is asked to diagnose it.");
  } else if (event.event === "answer_rejected") {
    stepField(host, "Validation error", event.error);
    stepField(host, "Next step", "Sol receives this rejection within its existing turn limit. No answer or path is repaired by the controller.");
    stepJSON(host, "Rejected model answer", event.answer, true);
  } else if (event.event === "lane_ready" || event.event === "complete") {
    stepField(host, "Outcome", event.result.error || node?.description || event.result.status);
    if (event.score) stepField(host, "Evaluation", event.score.exact
      ? "Status, target and ordered edge path exactly match the hidden expected output."
      : "The returned status, target or ordered path differs from the hidden expected output.");
  } else {
    if (node) stepField(host, node.type, node.instruction || node.description || nodeTitle(node));
    if (event.path) stepJSON(host, "Validated ordered edge path", event.path, true);
  }
  stepJSON(host, "Raw event", trace.steps[index]);
  $(`${method}-inspector-title`).textContent = meta.title;
  $(`${method}-time`).textContent = elapsed(event.elapsed_ms || 0);
  host.scrollTop = 0;
  $(`${method}-steps`).querySelectorAll("button").forEach((button, position) => {
    if (position === index) button.setAttribute("aria-current", "step");
    else button.removeAttribute("aria-current");
  });
  focusTrace(method, event);
}
function keyEvent(event) {
  return ["model_request", "cypher", "entry_selected", "answer_path", "answer_rejected", "complete"].includes(event.event)
    || (event.event === "entry_ready" && event.result?.status !== "resolved")
    || (event.event === "graph_query" && (event.method === "entry" || event.cypher.includes("(n)-[r]->(m)")))
    || event.event === "entry_policy";
}
function timedOperation(event) {
  return ["model_request", "cypher", "graph_query", "entry_start"].includes(event.event);
}
function executionTiming(event, response, liveElapsed = null) {
  const duration = response?.latency_ms ?? response?.duration_ms ?? response?.query_ms ?? response?.metrics?.elapsed_ms
    ?? event.latency_ms ?? event.duration_ms ?? event.query_ms ?? null;
  if (response) return { duration, total: response.elapsed_ms, state: "complete" };
  if (timedOperation(event)) {
    if (liveElapsed !== null) return {
      duration: Math.max(0, liveElapsed - event.elapsed_ms),
      total: Math.max(event.elapsed_ms, liveElapsed), state: "running",
    };
    return { duration: null, total: event.elapsed_ms, state: "incomplete" };
  }
  return { duration, total: event.elapsed_ms, state: "recorded" };
}
function timingFields() {
  const group = text("span", "", "step-times");
  for (const [label, name] of [["Step duration", "duration"], ["Total elapsed", "total"]]) {
    const column = text("span", "", "step-time");
    const value = text("time", "--", `step-${name}`);
    value.setAttribute("aria-label", name === "duration" ? "Step duration" : "Total elapsed");
    column.append(text("small", label), value);
    group.append(column);
  }
  return group;
}
function renderTiming(group, timing) {
  group.dataset.state = timing.state;
  for (const name of ["duration", "total"]) {
    const value = group.querySelector(`.step-${name}`), ms = timing[name];
    value.textContent = ms === null ? "--" : elapsed(ms);
    if (ms === null) {
      delete value.dataset.ms;
      value.removeAttribute("datetime");
    } else {
      value.dataset.ms = ms;
      value.setAttribute("datetime", `PT${ms / 1000}S`);
    }
    value.title = name === "duration"
      ? timing.state === "running" ? "Step duration so far (live estimate until completion)."
        : ms === null ? "No separate operation duration was recorded for this event."
          : "Measured duration of this operation; not the gap since the previous row."
      : timing.state === "running" ? "Live time since this standalone lane started."
        : timing.state === "incomplete" ? "Recorded start time; no completion was received."
          : "Time since this standalone lane started when this operation completed or event was recorded.";
  }
}
function liveElapsedFor(method) {
  const clock = clockAnchors[method === "entry" ? "decision" : method];
  if (!busy || !clock || readyResults[method] || completed[method] || (method === "entry" && entrySummary)
      || (method === "decision" && entrySummary && entrySummary.result.status !== "resolved")) return null;
  return clock.elapsed_ms + performance.now() - clock.received_at;
}
function refreshExecutionTimers() {
  for (const method of traceMethods) {
    const trace = traceViews[method];
    if (!trace) continue;
    const live = liveElapsedFor(method);
    trace.steps.forEach((event, index) => {
      if (timedOperation(event) && !trace.responses.has(index)) {
        const button = $(`${method}-steps`).children[index].firstElementChild;
        renderTiming(button.querySelector(".step-times"), executionTiming(event, null, live));
      }
    });
  }
  const start = traceViews.entry?.steps.find(event => event.event === "entry_start");
  if (start) renderTiming(
    document.querySelector('.shared-intake-step[data-method="decision"] .step-times'),
    executionTiming(start, entrySummary, liveElapsedFor("entry")));
}
function updateExecutionList(method) {
  const trace = traceViews[method];
  let count = method === "decision" ? 1 : 0;
  $(`${method}-steps`).querySelectorAll("button").forEach((button, index) => {
    const raw = trace.steps[index], event = { ...raw, paired_response: trace.responses.get(index) };
    button.hidden = !trace.all && !keyEvent(raw);
    if (!button.hidden) button.firstElementChild.textContent = String(++count).padStart(2, "0");
    const meta = stepMeta(event);
    button.querySelector("strong").textContent = meta.title;
    button.classList.toggle("in-progress", meta.pending && !trace.responses.has(index));
    renderTiming(button.querySelector(".step-times"), executionTiming(raw, trace.responses.get(index), liveElapsedFor(method)));
  });
  $(`${method}-step-count`).textContent = trace.all
    ? `${trace.steps.length} events${method === "decision" ? " + entry" : ""}`
    : `${count} key steps / ${trace.steps.length} recorded`;
}
function addExecutionStep(event) {
  const method = event.method, trace = traceViews[method], meta = stepMeta(event);
  const index = trace.steps.push(event) - 1;
  const list = $(`${method}-steps`);
  list.querySelector(".empty-note")?.remove();
  list.querySelectorAll(".in-progress").forEach((button) => button.classList.remove("in-progress"));
  const row = document.createElement("li"), button = text("button", "", "execution-step");
  button.type = "button";
  button.dataset.event = event.event;
  button.classList.toggle("in-progress", meta.pending);
  const label = text("span", "");
  label.append(text("strong", meta.title), text("small", meta.source));
  button.append(text("span", String(index + 1).padStart(2, "0")), label, timingFields());
  button.addEventListener("click", () => { pauseTrace(method); showTraceStep(method, index); });
  row.append(button); list.append(row);
  let paired;
  if (event.event === "model_response") paired = trace.steps.findLastIndex(step => step.event === "model_request" && step.call_index === event.call_index);
  else if (event.event === "graph_rows") paired = trace.steps.findLastIndex(step => step.event === "graph_query" && step.query_id === event.query_id);
  else if (event.event === "graph_result") paired = trace.steps.findLastIndex(step => step.event === "cypher");
  else if (event.event === "entry_ready") paired = trace.steps.findLastIndex(step => step.event === "entry_start");
  if (paired !== undefined && paired >= 0) trace.responses.set(paired, event);
  updateExecutionList(method);
  const operationIndex = trace.all || keyEvent(event) ? index : paired;
  if (operationIndex !== undefined && operationIndex >= 0) {
    const operation = stepMeta({ ...trace.steps[operationIndex], paired_response: trace.responses.get(operationIndex) });
    $(`${method}-operation`).textContent = operation.title;
    $(`${method}-operation-meta`).textContent = `${operation.source} · actual execution`;
    $(`${method}-operation-dot`).classList.toggle("running", operation.pending);
  }
  if (trace.follow && (trace.all || keyEvent(event))) {
    showTraceStep(method, index);
    list.scrollTop = list.scrollHeight;
  } else if (paired !== undefined && paired >= 0 && ((trace.follow && (trace.all || keyEvent(trace.steps[paired]))) || trace.selected === paired)) showTraceStep(method, paired);
}
function receive(event) {
  events.push(event);
  if (event.event === "heartbeat") return;
  if (event.event === "error") throw new Error(event.error);
  const method = event.method;
  if (!traceViews[method]) return;
  const clockMethod = method === "entry" ? "decision" : method;
  if (Number.isFinite(event.elapsed_ms) && (!clockAnchors[clockMethod] || event.elapsed_ms >= clockAnchors[clockMethod].elapsed_ms)) {
    clockAnchors[clockMethod] = { elapsed_ms: event.elapsed_ms, received_at: performance.now() };
  }
  if (event.event === "graph_data") {
    for (const lane of method === "entry" ? ["entry", "decision"] : [method]) {
      const store = discovered[lane];
      (event.nodes || []).forEach((node) => store.nodes.set(node.id, { ...store.nodes.get(node.id), ...node }));
      (event.edges || []).forEach((edge) => store.edges.set(edge.id, { ...store.edges.get(edge.id), ...edge }));
      if (lane !== "entry") renderGraph(lane, true);
    }
    if (method === "llm-cypher") {
      const scopes = new Set((event.nodes || []).map(node => node.procedure_id || (node.type === "Procedure" ? node.id : null)).filter(Boolean));
      if (scopes.size === 1) {
        const scope = [...scopes][0];
        const node = event.nodes.find(item => item.procedure_id === scope && item.type !== "Procedure");
        views[method].focusProcedure(scope, node?.id || scope);
      }
    }
  }
  addExecutionStep(event);
  if (method === "entry") {
    if (event.event === "entry_selected") views.decision.focusProcedure(event.procedure_id || findNode("entry", event.node)?.procedure_id, event.node);
    if (event.event === "entry_start") setState("entry", "Resolving", true);
    if (event.event === "entry_ready") {
      entrySummary = event;
      metricGrid("entry", event.metrics);
      setState("entry", { resolved: "Resolved", clarify: "Clarification required", unsupported: "Unsupported", error: "Failed" }[event.result.status]);
      $("entry-operation-dot").classList.remove("running");
      if (event.result.status !== "resolved") ["decision"].forEach((lane) => {
        setState(lane, "Stopped");
        $(`${lane}-operation`).textContent = `Traversal stopped: entry ${event.result.status}. No fixture fallback.`;
        $(`${lane}-outcome`).replaceChildren(text("span", "ENTRY NOT RESOLVED", "eyebrow"), text("p", event.result.status));
      });
    }
    intakeEvent(event);
    methods.filter(lane => traceViews[lane].intake).forEach(showSharedIntake);
    refreshExecutionTimers();
    return;
  }
  let view = views[method];
  if (event.event === "current") {
    view.focusProcedure(findNode(method, event.node)?.procedure_id, event.node);
    view = views[method];
    view.nodeElements.forEach((node, id) => node.classList.toggle("current", id === event.node));
    $(`${method}-progress`).textContent = `${event.hops} hops`;
  } else if (event.event === "decision_pending") {
    setState(method, "Scoring options", true);
    (event.options || []).forEach((id) => view.edgeElements.get(id)?.path.classList.add("pending"));
  } else if (event.event === "decision") {
    view.edgeElements.forEach(({ path }) => path.classList.remove("pending"));
  } else if (event.event === "traversed") highlightEdge(method, event.edge);
  else if (event.event === "cypher_pending") setState(method, "Reasoning", true);
  else if (event.event === "cypher") {
    setState(method, "Querying AGE", true);
  } else if (event.event === "graph_result") {
    view.reads += 1;
    $(`${method}-progress`).textContent = `${view.reads} read${view.reads === 1 ? "" : "s"}`;
  } else if (event.event === "answer_path") {
    view.focusProcedure(findNode(method, event.target)?.procedure_id, event.target);
    view = views[method];
    event.path.forEach((id) => highlightEdge(method, id));
    view.nodeElements.get(event.target)?.classList.add("current");
  } else if (event.event === "lane_ready" || event.event === "complete") {
    readyResults[method] = event;
    if (event.event === "complete") completed[method] = event;
    const outcome = $(`${method}-outcome`);
    const target = findNode(method, event.result.target);
    setState(method, resultState(event.result, target));
    const label = { root_cause: "Supported finding", clarify: "Information needed", next_action: "Recommendation", unsupported: "No applicable guidance", error: "Run failed" }[event.result.status];
    outcome.dataset.status = event.result.status;
    outcome.replaceChildren(text("span", (label || event.result.status).toUpperCase(), "eyebrow"),
      text("p", event.result.error || event.result.reason || target?.customer_response || target?.description || target?.instruction || (target ? nodeTitle(target)
        : event.result.status === "clarify" ? "More evidence is required before traversal can continue."
          : "Vehicle applicability or publication policy blocked traversal.")));
    if (event.result.status === "error") outcome.classList.add("error");
    else outcome.classList.remove("error");
    if (target?.source_reference) outcome.append(text("small", `Source: ${target.source_reference}`, "muted"));
    const evidence = document.createElement("details");
    evidence.append(text("summary", "Why this recommendation"));
    stepField(evidence, "Problem submitted", lastInput?.question || $("question").value);
    stepJSON(evidence, "Records supplied upfront", lastInput?.evidence || currentEvidence());
    const routeIds = (event.result.path || []).flatMap(id => {
      const edge = findEdge(method, id);
      return edge ? [edge.source, edge.target] : [];
    });
    const conditions = [...new Set(routeIds)].map(id => findNode(method, id))
      .filter(node => node?.type === "Condition");
    if (conditions.length) stepField(evidence, "Conditions selected from the published guidance",
      conditions.map(nodeTitle).join(" \u2192 "));
    if (target?.instruction) stepField(evidence, "Published instruction", target.instruction);
    if (target?.source_reference) stepField(evidence, "Source reference", target.source_reference);
    evidence.append(text("small", event.score ? (event.score.exact ? "\u2713 Exact match to expected output" : "Does not match expected output") : "Unscored run: expected-output comparison unavailable",
      event.score ? (event.score.exact ? "match" : "mismatch") : "muted"));
    outcome.append(evidence);
    metricGrid(method, event);
    if (target && event.result.path?.length) {
      view.answerRoute = { path: event.result.path, target: event.result.target };
      view.showContext = false; view.mode = "auto";
      renderGraph(method, true, true);
    }
    renderAnswer();
    if (event.expected) {
      const evaluation = text("section", "", "expected-result");
      evaluation.append(text("h3", method === "decision" ? "Decision-1" : "Sol-only"), text("pre", JSON.stringify(event.expected, null, 2)));
      $("expected").querySelector(".empty-note")?.remove();
      $("expected").append(evaluation);
    }
  }
  refreshExecutionTimers();
}
function reset() {
  events = []; completed = {}; readyResults = {}; traceViews = {}; discovered = {}; entrySummary = null; views = {}; clockAnchors = {};
  $("expected").replaceChildren(text("p", "Expected output is available only after a completed, scored run.", "empty-note"));
  $("download").disabled = true;
  $("answer-summary").hidden = true;
  $("entry-requests").replaceChildren(text("p", "Exact MD1 requests and responses appear here.", "empty-note"));
  $("entry-queries").replaceChildren(text("p", "Fixed Cypher and actual AGE entries appear here.", "empty-note"));
  $("entry-selection").replaceChildren(text("p", "Waiting for MD1 entry selection.", "muted"));
  for (const method of traceMethods) {
    traceViews[method] = { steps: [], selected: null, follow: true, all: false, responses: new Map() };
    discovered[method] = { nodes: new Map(), edges: new Map() };
    document.querySelector(`.all-events[data-method="${method}"]`).setAttribute("aria-pressed", "false");
    $(`${method}-steps`).replaceChildren(text("li", "Actual requests, controller transitions and database responses will appear here.", "empty-note"));
    $(`${method}-step-count`).textContent = "0 steps";
    document.querySelector(`.follow[data-method="${method}"]`).setAttribute("aria-pressed", "true");
    $(`${method}-operation`).textContent = method === "entry" ? "Ready to resolve entry from raw input"
      : method === "decision" ? "Ready to select an entry" : "Ready to query independently";
    $(`${method}-operation-meta`).textContent = "LIVE EXECUTION";
    $(`${method}-operation-dot`).classList.remove("running");
    metricGrid(method);
    setState(method, "Ready");
    if (method !== "entry") {
      const sharedStep = document.querySelector(`.shared-intake-step[data-method="${method}"]`);
      if (sharedStep) {
        sharedStep.disabled = true;
        sharedStep.removeAttribute("aria-current");
        sharedStep.querySelector("span").textContent = "Not started";
        sharedStep.querySelector(".step-times")?.remove();
        sharedStep.append(timingFields());
      }
      discovered[method] = { nodes: new Map(), edges: new Map() };
      renderGraph(method);
      $(`${method}-progress`).textContent = method === "decision" ? "0 hops" : "0 reads";
      $(`${method}-outcome`).replaceChildren(text("span", "RESULT", "eyebrow"), text("p", "Not run"));
      $(`${method}-outcome`).classList.remove("error");
      delete $(`${method}-outcome`).dataset.status;
    }
    $(`${method}-inspector`).replaceChildren(text("p", method === "entry" ? "The raw entry input, actual Sol requests, AGE results and entry resolution output appear here."
      : method === "decision" ? "Option probabilities and selected transitions appear as real decisions complete." : "Generated Cypher, database results and the final answer path appear here.", "empty-note"));
    $(`${method}-inspector-title`).textContent = "Step details";
    $(`${method}-time`).textContent = "Select a step";
  }
}
function currentEvidence() {
  return [...$("observations").querySelectorAll(".observation")].map((row) => ({
    check: row.querySelector(".evidence-check").value, observation: row.querySelector(".evidence-observation").value,
  }));
}
function currentVehicle() {
  return Object.fromEntries(vehicleFields.flatMap(key => {
    const value = $(`vehicle-${key}`).value.trim();
    return value ? [[key, key === "year" ? Number(value) : value]] : [];
  }));
}
function sameVehicle(left = {}, right = {}) {
  return vehicleFields.every(key => String(left[key] ?? "").toLowerCase() === String(right[key] ?? "").toLowerCase());
}
function currentVehicleId() {
  const vehicle = currentVehicle();
  const known = catalog.vehicles.find(item => sameVehicle(item, vehicle));
  return known?.id || (sameVehicle(vehicle, selected?.vehicle) ? selected?.vehicle_id || "" : "");
}
function vehicleOptions(id, values, value) {
  const choices = [...new Set([...values, ...(value ? [String(value)] : [])])]
    .sort((a, b) => String(a).localeCompare(String(b), undefined, {numeric: true}));
  const host = $(id);
  host.replaceChildren(...["", ...choices].map(item => {
    const option = text("option", item || "Unknown");
    option.value = item;
    return option;
  }));
  host.value = value ?? "";
}
function syncVehicleControls(vehicle) {
  const vehicles = catalog.vehicles;
  vehicleOptions("vehicle-make", vehicles.map(item => item.make), vehicle.make);
  $("vehicle-model").value = vehicle.model || "";
  const matchingMake = vehicles.filter(item => !vehicle.make || item.make === vehicle.make);
  $("vehicle-models").replaceChildren(...[...new Set(matchingMake.map(item => item.model))].map(model => {
    const option = document.createElement("option"); option.value = model; return option;
  }));
  const matchingModel = matchingMake.filter(item => !vehicle.model || item.model.toLowerCase() === vehicle.model.toLowerCase());
  vehicleOptions("vehicle-year", matchingModel.map(item => String(item.year)), vehicle.year);
  vehicleOptions("vehicle-configuration", matchingModel.map(item => item.configuration), vehicle.configuration);
  $("vehicle-context").textContent = vehicleFields.map(key => vehicle[key]).filter(Boolean).join(" · ") || "Vehicle unknown";
}
function unchangedInput() {
  return !selected.custom && $("question").value.trim() === selected.question
    && JSON.stringify(currentEvidence()) === JSON.stringify(selected.evidence)
    && sameVehicle(currentVehicle(), selected.vehicle)
    && currentVehicleId() === selected.vehicle_id;
}
function fitProblemText() {
  const field = $("question");
  field.style.height = "auto";
  field.style.height = `${Math.max(40, field.scrollHeight + 2)}px`;
}
function edited() {
  if (!selected) return;
  if (!busy && events.length) reset();
  $("case-note").textContent = unchangedInput() ? "Same input to both lanes · expected answers withheld."
    : "Custom input · unscored · fresh model context.";
  $("run").disabled = busy || !$("question").value.trim();
}
async function chooseCase() {
  $("run").disabled = true;
  selected = catalog.cases.find((c) => c.id === $("case-select").value);
  if (!selected) return;
  await displayCase();
}
function setInputsLocked() {
  const locked = busy;
  $("run").disabled = locked || !$("question").value.trim();
  for (const id of ["case-select", "question", "show-adversarial", "new-problem",
    ...vehicleFields.map(key => `vehicle-${key}`)]) $(id).disabled = locked;
  $("observations").querySelectorAll("textarea").forEach(node => { node.disabled = locked; });
}
function responseText(method, event) {
  const result = event.result, target = findNode(method, result.target);
  return result.error || result.reason || target?.customer_response || target?.description || target?.instruction
    || (result.status === "clarify" ? "More evidence is needed before a conclusion can be reached." : resultState(result, target));
}
function renderAnswer(failure = null) {
  const panel = $("answer-summary"), rows = methods.map(method => completed[method]);
  if (failure) {
    panel.hidden = false; panel.dataset.state = "error";
    $("answer-label").textContent = "COMPARISON STOPPED";
    $("answer-title").textContent = "The comparison could not finish";
    $("answer-body").replaceChildren(text("p", failure),
      text("small", "No additional comparison was started. The visible traces retain any results already received."));
    return;
  }
  if (rows.some(row => !row)) return;
  panel.hidden = false;
  const answers = rows.map((row, index) => responseText(methods[index], row));
  const agree = rows[0].result.status === rows[1].result.status
    && rows[0].result.target === rows[1].result.target && answers[0] === answers[1];
  const causes = rows.every(row => row.result.status === "root_cause");
  const failed = rows.some(row => row.result.status === "error");
  panel.dataset.state = failed ? "error" : causes && agree ? "resolved" : "open";
  $("answer-label").textContent = "RECOMMENDATION";
  $("answer-title").textContent = failed ? "The comparison could not finish"
    : !agree ? "The models reached different recommendations"
      : causes ? "Supported finding"
        : rows[0].result.status === "clarify" ? "More information needed"
          : rows[0].result.status === "unsupported" ? "No applicable published guidance"
            : "Recommended next step";
  const body = $("answer-body");
  body.replaceChildren();
  if (agree) body.append(text("p", answers[0], "answer-text"));
  else methods.forEach((method, index) => {
    const section = text("div", "", "answer-lane");
    section.append(text("strong", method === "decision" ? "Decision-1" : "Sol-only"), text("p", answers[index]));
    body.append(section);
  });
  if (!failed) body.append(text("small", agree
    ? causes ? "Both lanes reached this finding from the supplied records. Their actual routes are below."
      : rows[0].result.status === "next_action"
        ? "This is a recommended next check, not a confirmed fault. No missing observation has been invented."
        : rows[0].result.status === "clarify"
          ? "The missing information is requested above, not assumed or supplied automatically."
          : "No applicable published procedure was identified for this submission."
    : "Neither lane has been substituted or treated as ground truth. Inspect the routes and records below."));
  const rejections = events.filter(event => event.event === "answer_rejected").length;
  if (rejections) body.append(text("small",
    `${rejections} rejected Sol answer${rejections === 1 ? "" : "s"} recorded. Any corrections and extra calls remain in the totals and execution history.`, "mismatch"));
}
async function displayCase() {
  const vehicle = selected.vehicle || catalog.vehicles?.find(item => item.id === selected.vehicle_id);
  const vehicleLabel = vehicle && [vehicle.make, vehicle.model, vehicle.year ?? vehicle.model_year, vehicle.configuration].filter(Boolean).join(" · ");
  $("vehicle-context").textContent = vehicleLabel
    || "Vehicle not supplied · clarification required";
  syncVehicleControls(vehicle || {});
  $("question").value = selected.question;
  fitProblemText();
  $("observations").replaceChildren();
  selected.evidence.forEach((item, index) => {
    const row = text("div", "", "observation");
    const label = text("label", "Check label", "sr-only");
    const check = document.createElement("textarea");
    check.className = "evidence-check"; check.value = item.check; check.rows = 2;
    check.id = `check-${index}`; label.htmlFor = check.id; check.setAttribute("aria-label", `Evidence check ${index + 1}`);
    check.addEventListener("input", edited);
    const input = document.createElement("textarea");
    input.id = `observation-${index}`; input.className = "evidence-observation"; input.setAttribute("aria-label", `Observation ${index + 1}`);
    input.value = item.observation;
    input.rows = 2; input.addEventListener("input", edited);
    row.append(label, check, input); $("observations").append(row);
  });
  if (!selected.evidence.length) $("observations").append(text("p", "No test results supplied. Recommendations will use the problem description and published guidance.", "muted"));
  $("evidence-count").textContent = `${selected.evidence.length} observation${selected.evidence.length === 1 ? "" : "s"}`;
  reset(); edited();
  $("status").classList.remove("error");
  $("status").textContent = "Ready.";
  $("run-clock").textContent = "";
  setInputsLocked();
}
function populateCases() {
  const includeChallenges = $("show-adversarial").checked;
  const previous = $("case-select").value;
  const demoCases = catalog.cases.filter(item => item.demo !== false);
  const challengeCases = catalog.cases.filter(item => item.demo === false);
  const groups = [["Customer & technician problems", demoCases.filter(item => item.input_kind !== "with_records")],
    ["Problems with workshop records already available", demoCases.filter(item => item.input_kind === "with_records")],
    ["Diagnostic challenges", includeChallenges ? challengeCases.filter(item => item.category !== "vehicle_applicability") : []],
    ["Vehicle applicability comparisons", includeChallenges ? challengeCases.filter(item => item.category === "vehicle_applicability") : []]];
  $("case-select").replaceChildren(...groups.filter(([, items]) => items.length).map(([label, items]) => {
    const group = document.createElement("optgroup"); group.label = label;
    items.forEach(item => { const option = text("option", item.title); option.value = item.id; group.append(option); });
    return group;
  }));
  const preferred = [...$("case-select").options].some(option => option.value === previous)
    ? previous : catalog.default_case_id;
  if ([...$("case-select").options].some(option => option.value === preferred)) $("case-select").value = preferred;
  chooseCase();
}
async function run() {
  if (busy) return;
  let admitted = false, rejected = false;
  busy = true; reset();
  $("run").disabled = true; $("case-select").disabled = true; $("question").disabled = true;
  $("show-adversarial").disabled = true;
  vehicleFields.forEach(key => { $(`vehicle-${key}`).disabled = true; });
  $("new-problem").disabled = true;
  $("observations").querySelectorAll("textarea").forEach((e) => { e.disabled = true; });
  $("status").classList.remove("error");
  $("status").textContent = "Running MD1 and Sol independently.";
  const started = performance.now();
  timer = setInterval(() => {
    $("run-clock").textContent = elapsed(performance.now() - started);
    refreshExecutionTimers();
  }, 50);
  setState("decision", "Awaiting entry selection");
  setState("llm-cypher", "Starting", true);
  setState("entry", "Starting", true);
  try {
    lastInput = {case_id: selected.id, question: $("question").value, evidence: currentEvidence(),
      vehicle: currentVehicle(), vehicle_id: currentVehicleId()};
    const response = await fetch("/api/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(lastInput),
    });
    if (!response.ok) {
      rejected = true;
      const body = await response.json();
      throw new Error(body.error || `HTTP ${response.status}`);
    }
    admitted = true;
    if (!response.body) throw new Error("The response did not include an event stream.");
    const reader = response.body.getReader(), decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const lines = buffer.split("\n"); buffer = lines.pop();
        lines.filter((line) => line.trim()).forEach((line) => receive(JSON.parse(line)));
        if (done) break;
      }
      if (buffer.trim()) receive(JSON.parse(buffer));
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
    const stopped = entrySummary && entrySummary.result.status !== "resolved";
    if (Object.keys(completed).length !== 2) throw new Error("Stream ended before both methods completed. Server-side results may still be available.");
    $("status").textContent = stopped ? `MD1 entry: ${entrySummary.result.status}. Sol completed independently.`
      : Object.values(completed).some((r) => r.result.status === "error")
      ? "Comparison finished with a model error. Inspect the affected result; no fallback was substituted."
      : Object.values(completed).every(r => r.result.status === "root_cause")
        ? "Comparison saved · both lanes reached a root cause."
        : "Recommendation ready · supporting routes and evidence are below.";
    $("download").disabled = false;
  } catch (error) {
    $("status").textContent = error.message;
    $("status").classList.add("error");
    const usage = admitted ? " The accepted run may still be finishing on the server; additional usage is unavailable here."
      : rejected ? " No inference was started."
        : " Admission and usage could not be confirmed; a server-side run may still be processing.";
    renderAnswer(`${error.message}${usage}`);
    methods.filter((method) => !completed[method]).forEach((method) => setState(method, "Interrupted"));
    methods.filter((method) => !completed[method]).forEach((method) => {
      $(`${method}-operation`).textContent = "Stream interrupted · live progress unavailable";
      $(`${method}-operation-dot`).classList.remove("running");
      $(`${method}-steps`).querySelectorAll(".in-progress").forEach((button) => button.classList.remove("in-progress"));
    });
  } finally {
    clearInterval(timer); busy = false;
    refreshExecutionTimers();
    setInputsLocked();
  }
}
$("run").addEventListener("click", run);
$("case-select").addEventListener("change", chooseCase);
$("show-adversarial").addEventListener("change", populateCases);
$("question").addEventListener("input", edited);
$("question").addEventListener("input", fitProblemText);
window.addEventListener("resize", fitProblemText);
vehicleFields.forEach(key => $(`vehicle-${key}`).addEventListener("change", () => {
  if (busy) return;
  syncVehicleControls(currentVehicle());
  reset(); edited();
}));
$("vehicle-model").addEventListener("input", edited);
$("new-problem").addEventListener("click", async () => {
  if (busy) return;
  const vehicle = currentVehicle(), vehicleId = currentVehicleId();
  const base = catalog.cases.find(item => item.id === selected.id) || catalog.cases[0];
  selected = {...base, vehicle, vehicle_id: vehicleId, question: "", evidence: [], custom: true};
  await displayCase();
  $("question").focus();
});
$("sources-details").addEventListener("toggle", async () => {
  if (!$("sources-details").open || $("source-documents").dataset.loaded) return;
  try {
    const sources = await getJSON("/api/sources");
    $("source-documents").replaceChildren(...sources.map(source => {
      const section = document.createElement("details");
      section.append(text("summary", source.name), text("pre", source.text));
      return section;
    }));
    $("source-documents").dataset.loaded = "true";
  } catch (error) {
    $("source-documents").replaceChildren(text("p", error.message, "error"));
  }
});
document.querySelectorAll(".fit").forEach((button) => button.addEventListener("click", () => {
  const view = views[button.dataset.method];
  if (view) view.fit();
}));
document.querySelectorAll(".graph-context").forEach(button => button.addEventListener("click", () => {
  const method = button.dataset.method, view = views[method];
  if (!view?.scope) return;
  view.showContext = !view.showContext;
  view.mode = view.showContext ? "overview" : "auto";
  renderGraph(method, true, true);
}));
document.querySelectorAll(".follow").forEach((button) => button.addEventListener("click", () => {
  const method = button.dataset.method, trace = traceViews[method];
  if (!trace) return;
  trace.follow = !trace.follow;
  button.setAttribute("aria-pressed", String(trace.follow));
  const view = views[method];
  if (trace.follow && view?.scope) view.focusProcedure(view.scope, view.focusId);
  const latest = trace.steps.findLastIndex(event => trace.all || keyEvent(event));
  if (trace.follow && latest >= 0) {
    showTraceStep(method, latest);
    const list = $(`${method}-steps`);
    list.scrollTop = list.scrollHeight;
  }
}));
document.querySelectorAll(".all-events").forEach(button => button.addEventListener("click", () => {
  const method = button.dataset.method, trace = traceViews[method];
  trace.all = !trace.all;
  button.setAttribute("aria-pressed", String(trace.all));
  updateExecutionList(method);
  if (trace.follow) {
    const latest = trace.steps.findLastIndex(event => trace.all || keyEvent(event));
    if (latest >= 0) showTraceStep(method, latest);
  }
}));
document.querySelectorAll(".shared-intake-step").forEach(button => button.addEventListener("click", () => {
  showSharedIntake(button.dataset.method);
  $(`${button.dataset.method}-inspector`).scrollIntoView({ block: "nearest" });
}));
let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => methods.forEach((method) => { if (views[method]) renderGraph(method, true); }), 100);
});
$("download").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify({ case_id: selected.id, input: lastInput, events, results: completed,
    md1_entry: entrySummary, corpus: catalog.manifest, workflow: catalog.workflow,
    input_policy: catalog.input_policy }, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob), link = document.createElement("a");
  link.href = url; link.download = `graph-comparison-${selected.id}.json`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
(async () => {
  try {
    catalog = await getJSON("/api/catalog");
    $("connection").textContent = "Apache AGE connected";
    $("connection-dot").classList.add("ready");
    const m = catalog.manifest;
    $("dataset-counts").textContent = `${number(Object.values(m.nodes).reduce((a, b) => a + b, 0))} nodes / ${number(Object.values(m.relationships).reduce((a, b) => a + b, 0))} relationships / ${number(m.queries)} cases`;
    $("llm-name").textContent = "Sol-only";
    $("case-select").disabled = false; $("question").disabled = false;
    vehicleFields.forEach(key => { $(`vehicle-${key}`).disabled = false; });
    $("new-problem").disabled = false;
    populateCases();
  } catch (error) {
    $("connection").textContent = "Connection unavailable";
    $("status").textContent = error.message;
    $("status").classList.add("error");
  }
})();
