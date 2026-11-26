"use strict";

const $ = (id) => document.getElementById(id);
const LABEL = { pass: "PASS", fail: "FAIL", cannot_assess: "REVIEW" };
const OUTCOME = {
  compliant: { icon: "\u2713", text: "Compliant" },
  not_compliant: { icon: "\u2715", text: "Not compliant" },
  cannot_assess: { icon: "?", text: "Needs review" },
};
const state = { catalog: null, scenario: null, visit: null, run: null, results: {}, events: [], busy: false };

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const fmtMs = (ms) => (ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`);
const fmtUsd = (usd) => `$${usd.toFixed(usd < 0.01 ? 6 : 4)}`;
const fmtInt = (n) => n.toLocaleString("en-GB");
const scenario = () => state.catalog.scenarios.find((s) => s.id === state.scenario);
const visit = () => scenario().visits.find((v) => v.id === state.visit);
const campaignName = (id) => scenario().campaigns.find((c) => c.id === id).name;

function setStatus(text, isError = false) {
  const node = $("status");
  node.textContent = text;
  node.className = isError ? "error" : "";
}

function setBusy(busy) {
  state.busy = busy;
  for (const id of ["run", "run-all", "scenario", "visit"]) $(id).disabled = busy;
  $("run-label").textContent = busy ? "Auditing" : "Run audit";
  $("run-label").classList.toggle("running", busy);
}

async function loadCatalog() {
  try {
    const response = await fetch("/api/catalog");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.catalog = await response.json();
  } catch (error) {
    $("connection").textContent = "Catalogue unavailable";
    $("connection-dot").className = "dot error";
    setStatus("Could not load the demo catalogue. Refresh to try again.", true);
    return;
  }
  const all = state.catalog.scenarios;
  const checks = all.reduce((n, s) => n + s.campaigns.reduce((m, c) => m + c.checks.length, 0), 0);
  $("dataset-counts").textContent =
    `${all.length} scenarios / ${all.reduce((n, s) => n + s.visits.length, 0)} visits / ` +
    `${all.reduce((n, s) => n + s.campaigns.length, 0)} campaigns / ${checks} checks`;
  $("connection").textContent = `${state.catalog.model} ready`;
  $("connection-dot").className = "dot ready";
  $("scenario").replaceChildren(...all.map((s) => el("option", { value: s.id, text: s.name })));
  selectScenario(all[0].id);
}

function selectScenario(id) {
  state.scenario = id;
  state.results = {};
  state.run = null;
  $("matrix").hidden = true;
  $("visit").replaceChildren(...scenario().visits.map((v) => el("option", { value: v.id, text: `${v.id} · ${v.setup}` })));
  renderDocuments();
  selectVisit(scenario().visits[0].id);
}

function selectVisit(id) {
  state.visit = id;
  $("visit").value = id;
  const v = visit();
  $("visit-setup").textContent = v.setup;
  const photos = v.photos.map((p) => el("figure", { class: "photo" },
    el("a", { href: p.url, target: "_blank", rel: "noopener" },
      el("img", { src: p.url, alt: `${p.type} photo: ${scenario().photo_types[p.type]}`, loading: "lazy" })),
    el("figcaption", {}, el("span", { class: "eyebrow", text: p.type.toUpperCase() }),
      el("span", { text: "photo" }))));
  const references = scenario().campaigns.filter((c) => c.reference).map((c) => el("figure", { class: "photo reference" },
    el("a", { href: c.reference, target: "_blank", rel: "noopener" },
      el("img", { src: c.reference, alt: `Approved lookbook for ${c.name}`, loading: "lazy" })),
    el("figcaption", {}, el("span", { class: "eyebrow", text: `LOOKBOOK ${c.id}` }), el("span", { text: "reference" }))));
  $("photos").replaceChildren(...photos, ...references);
  renderExpected();
  const result = state.results[id];
  if (result) renderResult(result);
  else renderEmptyCampaigns();
  for (const row of document.querySelectorAll("#matrix tr.row")) row.setAttribute("aria-selected", String(row.dataset.visit === id));
}

function renderDocuments() {
  const s = scenario();
  const total = s.campaigns.reduce((n, c) => n + c.checks.length, 0);
  $("question-count").textContent = `· ${total} checks across ${s.campaigns.length} campaigns`;
  $("documents").replaceChildren(...s.campaigns.map((c) => el("div", { class: "doc-campaign" },
    el("h4", { text: `Campaign ${c.id}: ${c.name}` }),
    el("details", {}, el("summary", { text: "Campaign brief" }), el("pre", { text: c.brief })),
    c.standards ? el("details", {}, el("summary", { text: "Standards document" }), el("pre", { text: c.standards })) : null,
    el("details", {}, el("summary", { text: `${c.checks.length} checks extracted by ${c.extraction.model || "the extraction model"}, then reviewed` }),
      el("ol", { class: "check-list" }, c.checks.map((k) => el("li", {},
        `${k.requirement} `, el("span", { class: "mono", text: `${k.rule} · ${k.photos.join("/")}${k.uses_reference ? " + lookbook" : ""}` })))),
      c.review_notes.length ? el("p", { class: "muted", text: `Review edits: ${c.review_notes.join(" ")}` }) : null),
    el("details", {}, el("summary", { text: `${c.not_checkable.length} requirements not checked from photos` }),
      el("ul", { class: "check-list" }, c.not_checkable.map((n) => el("li", {},
        `${n.requirement} `, el("span", { class: "mono", text: n.reason.replaceAll("_", " ") }))))))));
}

function renderExpected() {
  const v = visit();
  $("expected").replaceChildren(
    el("p", {}, el("strong", { text: "What the photos show: " }), v.shows),
    ...scenario().campaigns.map((c) => el("p", {}, `${c.name}: `, el("span", { class: `badge ${v.expected[c.id]}`, text: LABEL[v.expected[c.id]] }))));
}

function renderEmptyCampaigns() {
  $("metrics").hidden = true;
  $("campaigns").replaceChildren(...scenario().campaigns.map((c) => el("article", { class: "lane" },
    el("div", { class: "lane-header" }, el("div", {}, el("h2", { text: c.name }), el("p", { text: `Campaign ${c.id} · ${c.checks.length} checks` })),
      el("span", { class: "badge pending", text: "NOT RUN" })))));
}

function metric(label, value) {
  return el("div", { class: "metric" }, el("span", { text: label }), el("strong", { text: value }));
}

function bar(fraction) {
  const fill = el("i");
  fill.style.transform = `scaleX(${fraction})`; // CSSOM, permitted by the CSP
  return fill;
}

function renderResult(r) {
  if (r.error) {
    $("metrics").hidden = true;
    $("campaigns").replaceChildren(el("p", { class: "mismatch", text: `This visit could not be audited: ${r.error}` }));
    return;
  }
  $("metrics").hidden = false;
  $("metrics").replaceChildren(el("div", { class: "metrics" },
    metric("Model latency", fmtMs(r.latency_ms)), metric("Input tokens", fmtInt(r.usage.input_tokens)),
    metric("Output tokens", fmtInt(r.usage.output_tokens)), metric("Est. cost", fmtUsd(r.estimated_cost_usd)),
    metric("Model calls", r.questions_asked ? "1" : "0"), metric("Questions asked", String(r.questions_asked)),
    metric("No photo, not asked", String(r.questions_skipped))));
  const order = { not_compliant: 0, cannot_assess: 1, compliant: 2 };
  $("campaigns").replaceChildren(...scenario().campaigns.map((c) => {
    const verdict = r.campaigns[c.id];
    const rows = r.checks.filter((k) => k.campaign === c.id).sort((a, b) => order[a.outcome] - order[b.outcome]);
    return el("article", { class: "lane" },
      el("div", { class: "lane-header" }, el("div", {}, el("h2", { text: c.name }), el("p", { text: `Campaign ${c.id} · ${rows.length} checks` })),
        el("span", { class: `badge ${verdict.verdict}`, text: LABEL[verdict.verdict] })),
      el("div", { class: "lane-summary" },
        el("span", { text: `${verdict.failed.length} failed · ${verdict.unassessed.length} need review` }),
        el("span", { class: verdict.match ? "match" : "mismatch", text: verdict.match ? "Matches expected" : `Expected ${LABEL[verdict.expected]}` })),
      el("ol", { class: "checks" }, rows.map((k) => {
        const p = k.probabilities ? k.probabilities[k.outcome] : null;
        const source = k.reason ? k.reason : `${k.photos.join(" + ")}${k.reference ? " + lookbook" : ""} · ${k.rule}`;
        return el("li", { class: `check ${k.outcome}`, title: k.probabilities ? Object.entries(k.probabilities).map(([o, v]) => `${o}: ${(v * 100).toFixed(1)}%`).join("\n") : "" },
          el("span", { class: "icon", "aria-hidden": "true", text: OUTCOME[k.outcome].icon }),
          el("div", {}, el("strong", { text: k.requirement }), el("small", { text: source })),
          el("div", { class: "prob" }, el("span", { class: "mono", text: p === null ? "not asked" : `${(p * 100).toFixed(1)}%` }),
            el("span", { class: "sr-only", text: OUTCOME[k.outcome].text }),
            el("div", { class: "bar" }, bar(p ?? 0))));
      })));
  }));
}

function addEvent(title, detail, tMs) {
  if (!state.events.length) $("events").replaceChildren();
  state.events.push({ title, detail, tMs });
  $("events").append(el("li", { class: "execution-step" }, el("span", { text: String(state.events.length) }),
    el("div", {}, el("strong", { text: title }), detail ? el("small", { text: detail }) : null),
    el("time", { text: tMs === undefined ? "" : fmtMs(tMs) })));
  $("events").scrollTop = $("events").scrollHeight;
  $("event-count").textContent = `${state.events.length} events`;
}

function renderMatrix(summary, wallMs) {
  const s = scenario();
  const visits = s.visits.filter((v) => state.results[v.id]);
  const header = el("tr", {}, el("th", { text: "Visit" }), ...s.campaigns.map((c) => el("th", { text: `${c.id} · ${c.name}` })), el("th", { text: "Latency" }));
  const rows = visits.map((v) => {
    const r = state.results[v.id];
    return el("tr", { class: "row", "data-visit": v.id, tabindex: "0", "aria-selected": String(v.id === state.visit),
      onclick: () => selectVisit(v.id), onkeydown: (e) => { if (e.key === "Enter") selectVisit(v.id); } },
      el("td", {}, el("strong", { text: v.id }), ` ${v.setup}`),
      ...s.campaigns.map((c) => r.error ? el("td", { class: "mismatch", text: "error" }) : el("td", {},
        el("span", { class: `badge ${r.campaigns[c.id].verdict}`, text: LABEL[r.campaigns[c.id].verdict] }), " ",
        el("span", { class: r.campaigns[c.id].match ? "match" : "mismatch", text: r.campaigns[c.id].match ? "\u2713" : `\u2715 expected ${LABEL[r.campaigns[c.id].expected]}` }))),
      el("td", { class: "mono", text: r.error ? "" : fmtMs(r.latency_ms) }));
  });
  const parts = [el("table", {}, el("thead", {}, header), el("tbody", {}, rows))];
  if (summary) {
    parts.unshift(el("p", { class: "matrix-summary" },
      el("span", {}, el("strong", { text: `${summary.matches}/${summary.campaign_verdicts}` }), " verdicts match expected"),
      el("span", {}, el("strong", { text: String(summary.visits) }), " parallel calls"),
      el("span", {}, el("strong", { text: fmtMs(wallMs) }), " wall time"),
      el("span", {}, el("strong", { text: fmtInt(summary.input_tokens) }), " input tokens"),
      el("span", {}, el("strong", { text: fmtUsd(summary.estimated_cost_usd) }), " est. cost"),
      summary.errors ? el("span", { class: "mismatch", text: `${summary.errors} errors` }) : null));
  }
  $("matrix").replaceChildren(...parts);
  $("matrix").hidden = false;
}

async function runAudit(all) {
  if (state.busy) return;
  setBusy(true);
  state.events = [];
  $("events").replaceChildren(el("li", { class: "empty-note", text: "Starting." }));
  if (all) { state.results = {}; $("matrix").hidden = true; }
  const targetScenario = state.scenario;
  const run = { scenario: targetScenario, visit: all ? "all" : state.visit, started_at: new Date().toISOString(), events: [] };
  state.run = run;
  $("download").disabled = true;
  setStatus(all ? `Auditing all ${scenario().visits.length} visits in parallel` : `Auditing visit ${state.visit}`);
  const started = performance.now();
  const timer = setInterval(() => { $("elapsed").textContent = fmtMs(performance.now() - started); }, 100);
  try {
    const response = await fetch("/api/audit", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario: targetScenario, visit: run.visit }) });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error || `HTTP ${response.status}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let line;
      while ((line = buffer.indexOf("\n")) >= 0) {
        const text = buffer.slice(0, line);
        buffer = buffer.slice(line + 1);
        if (text.trim()) handleEvent(JSON.parse(text), all, run);
      }
    }
  } catch (error) {
    setStatus(`Audit failed: ${error.message}`, true);
    addEvent("Audit failed", error.message);
  } finally {
    clearInterval(timer);
    $("elapsed").textContent = fmtMs(performance.now() - started);
    setBusy(false);
    $("download").disabled = !run.events.length;
  }
}

function handleEvent(event, all, run) {
  run.events.push(event);
  if (event.event === "run_started") {
    const questions = event.plans.reduce((n, p) => n + p.questions, 0);
    const skipped = event.plans.reduce((n, p) => n + p.skipped, 0);
    addEvent(`Sending ${event.calls} request${event.calls === 1 ? "" : "s"} to ${state.catalog.model}`,
      `${questions} questions${skipped ? `, ${skipped} not asked (photo missing)` : ""}; each question sees only its own photos`, event.t_ms);
  } else if (event.event === "visit_result") {
    const r = event.result;
    state.results[r.visit] = r;
    if (r.error) addEvent(`Visit ${r.visit} failed`, r.error, event.t_ms);
    else {
      const verdicts = Object.entries(r.campaigns).map(([id, c]) => `${id} ${LABEL[c.verdict]}${c.match ? "" : " (unexpected)"}`).join(" · ");
      addEvent(`Visit ${r.visit} answered in ${fmtMs(r.latency_ms)}`, `${r.questions_asked} answers · ${fmtInt(r.usage.input_tokens)} input tokens · ${verdicts}`, event.t_ms);
    }
    if (all) renderMatrix(null, 0);
    if (r.visit === state.visit) renderResult(r);
  } else if (event.event === "run_finished") {
    const s = event.summary;
    addEvent("Audit complete", `${s.matches}/${s.campaign_verdicts} campaign verdicts match the expected output`, event.t_ms);
    setStatus(`${s.matches} of ${s.campaign_verdicts} campaign verdicts match the expected output · ${fmtUsd(s.estimated_cost_usd)} estimated`);
    if (all) renderMatrix(s, event.wall_ms);
  } else if (event.event === "run_error") {
    setStatus(event.error, true);
    addEvent("Audit failed", event.error, event.t_ms);
  }
}

function downloadRun() {
  if (!state.run) return;
  const blob = new Blob([JSON.stringify(state.run, null, 2)], { type: "application/json" });
  const link = el("a", { href: URL.createObjectURL(blob), download: `shelf-check-${state.run.scenario}-${state.run.visit}.json` });
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

$("scenario").addEventListener("change", (e) => selectScenario(e.target.value));
$("visit").addEventListener("change", (e) => selectVisit(e.target.value));
$("run").addEventListener("click", () => runAudit(false));
$("run-all").addEventListener("click", () => runAudit(true));
$("download").addEventListener("click", downloadRun);
loadCatalog();
