"use strict";

const $ = (id) => document.getElementById(id);
const LABEL = { pass: "PASS", fail: "FAIL", cannot_assess: "REVIEW" };
const OUTCOME = {
  compliant: { icon: "\u2713", text: "Compliant" },
  not_compliant: { icon: "\u2715", text: "Not compliant" },
  cannot_assess: { icon: "?", text: "Needs review" },
};
const state = { catalog: null, scenario: null, visit: null, doc: null, run: null, results: {}, events: [], busy: false };

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
const caseNumber = (id) => scenario().visits.findIndex((v) => v.id === id) + 1;
const prettyModel = (model) => (/^gpt-6-sol/i.test(model || "") ? "GPT-6 Sol" : model || "The extraction model");

// --- Markdown: a small renderer for the policy documents. It builds DOM nodes (never HTML strings),
// and only links to images the server lists for that document.

function inline(text, images) {
  const nodes = [];
  const token = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))/g;
  let last = 0;
  for (const match of text.matchAll(token)) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const t = match[0];
    if (t.startsWith("**")) nodes.push(el("strong", {}, inline(t.slice(2, -2), images)));
    else if (t.startsWith("`")) nodes.push(el("code", { text: t.slice(1, -1) }));
    else if (t.startsWith("[")) {
      const [, label, href] = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(t);
      nodes.push(images[href] ? el("a", { href: images[href], target: "_blank", rel: "noopener" }, inline(label, images))
        : el("span", {}, inline(label, images)));
    } else nodes.push(el("em", {}, inline(t.slice(1, -1), images)));
    last = match.index + t.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

const isBlockStart = (line) => /^(#{1,4}\s|>|\s*\||\s*[-*]\s+|\s*\d+\.\s+)/.test(line);
const cells = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

function renderMarkdown(markdown, images) {
  const lines = markdown.replace(/\r/g, "").split("\n");
  const out = [];
  let i = 0;
  let figuresPlaced = false;
  const figures = () => Object.values(images).map((url) => el("figure", { class: "doc-figure" },
    el("a", { href: url, target: "_blank", rel: "noopener" }, el("img", { src: url, alt: "Approved lookbook image from the brief", loading: "lazy" })),
    el("figcaption", { text: "Lookbook attached to this brief. The model receives it alongside the store photos." })));
  while (i < lines.length) {
    const line = lines[i];
    let m;
    if (!line.trim()) { i += 1; continue; }
    if ((m = /^(#{1,4})\s+(.*)$/.exec(line))) {
      out.push(el(`h${Math.min(m[1].length + 1, 5)}`, {}, inline(m[2], images)));
      i += 1;
    } else if (line.startsWith(">")) {
      const quote = [];
      while (i < lines.length && lines[i].startsWith(">")) quote.push(lines[i++].replace(/^>\s?/, ""));
      out.push(el("blockquote", {}, inline(quote.join(" "), images)));
    } else if (/^\s*\|/.test(line)) {
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(lines[i++]);
      const body = rows.slice(1).filter((r) => !/^\s*\|?[\s:|-]+\|?\s*$/.test(r));
      out.push(el("div", { class: "doc-table" }, el("table", {},
        el("thead", {}, el("tr", {}, cells(rows[0]).map((c) => el("th", {}, inline(c, images))))),
        el("tbody", {}, body.map((r) => el("tr", {}, cells(r).map((c) => el("td", {}, inline(c, images)))))))));
    } else if ((m = /^\s*([-*]|\d+\.)\s+/.exec(line))) {
      const ordered = /\d/.test(m[1]);
      const items = [];
      while (i < lines.length && lines[i].trim()) {
        const item = /^\s*([-*]|\d+\.)\s+(.*)$/.exec(lines[i]);
        if (item) items.push(item[2]);
        else if (/^\s+/.test(lines[i]) && items.length) items[items.length - 1] += ` ${lines[i].trim()}`;
        else break;
        i += 1;
      }
      out.push(el(ordered ? "ol" : "ul", {}, items.map((t) => el("li", {}, inline(t, images)))));
    } else {
      const para = [];
      while (i < lines.length && lines[i].trim() && !(para.length && isBlockStart(lines[i]))) para.push(lines[i++]);
      if (para.every((p) => /^\*\*[^*]+:\*\*/.test(p))) {
        out.push(el("dl", { class: "doc-meta" }, para.flatMap((p) => {
          const [, key, rest] = /^\*\*([^*]+):\*\*\s*(.*)$/.exec(p);
          return [el("dt", { text: key }), el("dd", {}, inline(rest, images))];
        })));
        if (!figuresPlaced) { out.push(...figures()); figuresPlaced = true; }
      } else out.push(el("p", {}, inline(para.join(" "), images)));
    }
  }
  if (!figuresPlaced) out.push(...figures());
  return out;
}

// --- Catalogue, scenarios and documents

function setStatus(text, isError = false) {
  const node = $("status");
  node.textContent = text;
  node.className = isError ? "error" : "";
}

function setBusy(busy) {
  state.busy = busy;
  for (const id of ["run", "run-all"]) $(id).disabled = busy;
  for (const node of document.querySelectorAll(".scenario-tab, .case-card")) node.disabled = busy;
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
  const count = (f) => all.reduce((n, s) => n + f(s), 0);
  $("dataset-counts").textContent = `${all.length} scenarios / ${count((s) => s.visits.length)} visits / ` +
    `${count((s) => s.documents.length)} documents / ${count((s) => s.campaigns.reduce((m, c) => m + c.checks.length, 0))} checks`;
  $("connection").textContent = `${state.catalog.model} ready`;
  $("connection-dot").className = "dot ready";
  $("scenarios").replaceChildren(...all.map((s) => el("button", {
    class: "scenario-tab", type: "button", "data-id": s.id, onclick: () => !state.busy && selectScenario(s.id) },
  el("strong", { text: s.name }), el("span", { text: s.campaigns.map((c) => c.name).join(" + ") }))));
  selectScenario(all[0].id);
}

function selectScenario(id) {
  state.scenario = id;
  state.results = {};
  state.run = null;
  state.events = [];
  $("matrix").hidden = true;
  $("download").disabled = true;
  for (const tab of document.querySelectorAll(".scenario-tab")) tab.setAttribute("aria-pressed", String(tab.dataset.id === id));
  const s = scenario();
  $("doc-note").textContent = `${s.documents.length} documents · the rep and the model start from the same text`;
  $("case-heading").textContent = `${s.store} · ${s.audit}`;
  $("run-all").textContent = `Audit all ${s.visits.length} visits`;
  $("cases").replaceChildren(...s.visits.map((v, n) => el("button", {
    class: "case-card", type: "button", role: "radio", "data-visit": v.id, onclick: () => !state.busy && selectVisit(v.id) },
  el("img", { src: v.photos[0].url, alt: "", loading: "lazy" }),
  el("span", { class: "case-text" },
    el("span", { class: "eyebrow", text: `VISIT ${n + 1}` }),
    el("strong", { text: v.title }),
    el("span", { class: "case-summary", text: v.summary }),
    el("span", { class: "case-photos mono", text: v.photos.map((p) => p.type).join(" · ") }),
    el("span", { class: "case-verdict", "data-visit": v.id })))));
  selectDocument(s.documents[0].id);
  setStatus("Choose a visit and run the audit.");
  $("elapsed").textContent = "";
  renderTrace();
  selectVisit(s.visits[0].id);
}

function selectDocument(id) {
  state.doc = id;
  const s = scenario();
  const doc = s.documents.find((d) => d.id === id);
  const usedBy = (d) => s.campaigns.filter((c) => c.documents.includes(d.id)).map((c) => c.name);
  $("doc-list").replaceChildren(...s.documents.map((d) => el("button", {
    class: "doc-tab", type: "button", role: "tab", "aria-selected": String(d.id === id), onclick: () => selectDocument(d.id) },
  el("span", { class: "eyebrow", text: d.kind.toUpperCase() }),
  el("strong", { text: d.title.replace(/^Campaign brief:\s*/, "") }),
  el("span", { class: "mono", text: d.file }),
  d.kind === "Standards" ? el("small", { text: `Applies to ${usedBy(d).join(", ")}` }) : null)));
  $("doc-page").replaceChildren(...renderMarkdown(doc.text, doc.images));
  $("doc-page").scrollTop = 0;
}

function selectVisit(id) {
  state.visit = id;
  const v = visit();
  for (const card of document.querySelectorAll(".case-card")) card.setAttribute("aria-checked", String(card.dataset.visit === id));
  const photos = v.photos.map((p) => el("figure", { class: "photo" },
    el("a", { href: p.url, target: "_blank", rel: "noopener" },
      el("img", { src: p.url, alt: `${p.type} photo: ${scenario().photo_types[p.type]}`, loading: "lazy" })),
    el("figcaption", {}, el("span", { class: "eyebrow", text: p.type.toUpperCase() }), el("span", { text: scenario().photo_types[p.type] }))));
  const references = scenario().campaigns.filter((c) => c.reference).map((c) => el("figure", { class: "photo reference" },
    el("a", { href: c.reference, target: "_blank", rel: "noopener" },
      el("img", { src: c.reference, alt: `Approved lookbook for ${c.name}`, loading: "lazy" })),
    el("figcaption", {}, el("span", { class: "eyebrow", text: "LOOKBOOK" }), el("span", { text: "from the brief, sent as the reference" }))));
  $("photos").replaceChildren(...photos, ...references);
  renderExpected();
  const result = state.results[id];
  if (result) renderResult(result);
  else renderEmptyCampaigns();
  for (const row of document.querySelectorAll("#matrix tr.row")) row.setAttribute("aria-selected", String(row.dataset.visit === id));
}

function renderExpected() {
  const v = visit();
  $("expected").replaceChildren(
    el("p", {}, el("strong", { text: "What the photos show: " }), v.shows),
    ...scenario().campaigns.map((c) => el("p", {}, `${c.name}: `, el("span", { class: `badge ${v.expected[c.id]}`, text: LABEL[v.expected[c.id]] }))));
}

// --- Results

function renderEmptyCampaigns() {
  $("metrics").hidden = true;
  $("campaigns").replaceChildren(...scenario().campaigns.map((c) => el("article", { class: "lane" },
    el("div", { class: "lane-header" }, el("div", {}, el("h2", { text: c.name }), el("p", { text: `${c.checks.length} approved checks · run the audit to see results` })),
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
    r.questions_skipped ? metric("No photo, not asked", String(r.questions_skipped)) : null));
  const order = { not_compliant: 0, cannot_assess: 1, compliant: 2 };
  $("campaigns").replaceChildren(...scenario().campaigns.map((c) => {
    const verdict = r.campaigns[c.id];
    const rows = r.checks.filter((k) => k.campaign === c.id).sort((a, b) => order[a.outcome] - order[b.outcome]);
    return el("article", { class: "lane" },
      el("div", { class: "lane-header" }, el("div", {}, el("h2", { text: c.name }), el("p", { text: `${rows.length} checks from the documents above` })),
        el("span", { class: `badge ${verdict.verdict}`, text: LABEL[verdict.verdict] })),
      el("div", { class: "lane-summary" },
        el("span", { text: `${verdict.failed.length} failed · ${verdict.unassessed.length} need review` }),
        el("span", { class: verdict.match ? "match" : "mismatch", text: verdict.match ? "Matches expected" : `Expected ${LABEL[verdict.expected]}` })),
      el("ol", { class: "checks" }, rows.map((k) => {
        const p = k.probabilities ? k.probabilities[k.model_leaning || k.outcome] : null; // gated rows show the answer the model leaned to
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

function markCase(r) {
  const node = document.querySelector(`.case-verdict[data-visit="${r.visit}"]`);
  if (!node) return;
  node.replaceChildren(...(r.error ? [el("span", { class: "mismatch", text: "error" })]
    : Object.entries(r.campaigns).map(([id, c]) => el("span", { class: `badge ${c.verdict}`, title: scenario().campaigns.find((x) => x.id === id).name, text: LABEL[c.verdict] }))));
}

function renderMatrix(summary, wallMs) {
  const s = scenario();
  const visits = s.visits.filter((v) => state.results[v.id]);
  const header = el("tr", {}, el("th", { text: "Visit" }), ...s.campaigns.map((c) => el("th", { text: c.name })), el("th", { text: "Latency" }));
  const rows = visits.map((v) => {
    const r = state.results[v.id];
    return el("tr", { class: "row", "data-visit": v.id, tabindex: "0", "aria-selected": String(v.id === state.visit),
      onclick: () => selectVisit(v.id), onkeydown: (e) => { if (e.key === "Enter") selectVisit(v.id); } },
      el("td", {}, el("strong", { text: `${caseNumber(v.id)}` }), ` ${v.title}`),
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

// --- Trace: the one-off extraction and review, then the live audit steps

function traceStep(n, kind, title, detail, time, extra) {
  return el("li", { class: `execution-step ${kind === "AUDIT" ? "live" : "prepared"}` },
    el("span", { text: String(n) }),
    el("div", {}, el("span", { class: "trace-kind", text: kind }), el("strong", { text: title }),
      detail ? el("small", { text: detail }) : null, extra || null),
    el("time", { text: time || "" }));
}

function renderTrace() {
  const s = scenario();
  const steps = [];
  const add = (...args) => steps.push(traceStep(steps.length + 1, ...args));
  add("SOURCE", `Loaded ${s.documents.length} campaign documents`, s.documents.map((d) => d.file).join(" · "), "");
  for (const c of s.campaigns) {
    const x = c.extraction;
    const files = c.documents.map((id) => s.documents.find((d) => d.id === id).file).join(" + ");
    add("EXTRACTION · ONCE", `${prettyModel(x.model)} turned ${files} into ${c.checks.length} checks for ${c.name}`,
      `${x.model} · reasoning ${x.reasoning_effort} · ${fmtInt(x.usage.input_tokens)} in / ${fmtInt(x.usage.output_tokens)} out tokens · ${(x.extracted_at || "").slice(0, 10)}`,
      x.latency_ms ? fmtMs(x.latency_ms) : "",
      el("details", { class: "trace-details" }, el("summary", { text: `Show the ${c.checks.length} checks and ${c.not_checkable.length} requirements left to a person` }),
        el("ol", { class: "check-list" }, c.checks.map((k) => el("li", {}, `${k.requirement} `,
          el("span", { class: "mono", text: `${k.rule} · ${k.photos.join("/")}${k.uses_reference ? " + lookbook" : ""}` })))),
        el("p", { class: "muted", text: "Not checked from photos:" }),
        el("ul", { class: "check-list" }, c.not_checkable.map((k) => el("li", {}, `${k.requirement} `,
          el("span", { class: "mono", text: k.reason.replaceAll("_", " ") }))))));
  }
  if (!state.events.length) steps.push(el("li", { class: "empty-note", text: "Run an audit to add the live Decision-1.1 steps." }));
  for (const e of state.events) add("AUDIT", e.title, e.detail, e.tMs === undefined ? "" : fmtMs(e.tMs));
  $("events").replaceChildren(...steps);
  $("event-count").textContent = state.events.length ? `${state.events.length} live steps` : "";
}

function addEvent(title, detail, tMs) {
  state.events.push({ title, detail, tMs });
  renderTrace();
}

// --- Running an audit

async function runAudit(all) {
  if (state.busy) return;
  setBusy(true);
  state.events = [];
  renderTrace();
  if (all) {
    state.results = {};
    $("matrix").hidden = true;
    for (const node of document.querySelectorAll(".case-verdict")) node.replaceChildren();
  }
  const run = { scenario: state.scenario, visit: all ? "all" : state.visit, started_at: new Date().toISOString(), events: [] };
  state.run = run;
  $("download").disabled = true;
  setStatus(all ? `Auditing all ${scenario().visits.length} visits in parallel` : `Auditing visit ${caseNumber(state.visit)}: ${visit().title}`);
  const started = performance.now();
  const timer = setInterval(() => { $("elapsed").textContent = fmtMs(performance.now() - started); }, 100);
  try {
    const response = await fetch("/api/audit", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario: run.scenario, visit: run.visit }) });
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
    const campaigns = scenario().campaigns.length;
    addEvent(`Sent ${event.calls} request${event.calls === 1 ? "" : "s"} to ${state.catalog.model}`,
      `${questions} questions across ${campaigns} campaign${campaigns === 1 ? "" : "s"}${skipped ? `; ${skipped} not asked because their photo is missing` : ""}; each question sees only its own photos`, event.t_ms);
  } else if (event.event === "visit_result") {
    const r = event.result;
    state.results[r.visit] = r;
    markCase(r);
    const n = caseNumber(r.visit);
    if (r.error) addEvent(`Visit ${n} failed`, r.error, event.t_ms);
    else {
      const verdicts = Object.entries(r.campaigns).map(([id, c]) => `${scenario().campaigns.find((x) => x.id === id).name} ${LABEL[c.verdict]}`).join(" · ");
      addEvent(`Visit ${n} answered in ${fmtMs(r.latency_ms)}`, `${r.questions_asked} answers · ${r.images_sent} images · ${fmtInt(r.usage.input_tokens)} input tokens · ${verdicts}`, event.t_ms);
    }
    if (all) renderMatrix(null, 0);
    if (r.visit === state.visit) renderResult(r);
  } else if (event.event === "run_finished") {
    const s = event.summary;
    addEvent("Verdicts built from the answers", `Any failed check fails a campaign; any check without clear evidence sends it to review · ${s.matches}/${s.campaign_verdicts} match the expected output`, event.t_ms);
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

// Photos open in an in-page viewer; Esc or a click outside the photo closes it.
// Ctrl, Shift or middle click still opens the image in a new tab.
document.addEventListener("click", (event) => {
  const link = event.target.closest('a[href^="/images/"]');
  if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  const img = link.querySelector("img");
  const caption = link.closest("figure")?.querySelector("figcaption");
  $("viewer-image").src = link.getAttribute("href");
  $("viewer-image").alt = img ? img.alt : link.textContent;
  $("viewer-caption").textContent = caption && caption.children.length ? [...caption.children].map((c) => c.textContent.trim()).join(" · ") : (caption || link).textContent.trim();
  $("viewer").showModal();
});
$("viewer").addEventListener("click", (event) => { if (event.target === $("viewer")) $("viewer").close(); });
$("viewer-close").addEventListener("click", () => $("viewer").close());
$("viewer").addEventListener("close", () => { $("viewer-image").removeAttribute("src"); });
$("run").addEventListener("click", () => runAudit(false));
$("run-all").addEventListener("click", () => runAudit(true));
$("download").addEventListener("click", downloadRun);
loadCatalog();
