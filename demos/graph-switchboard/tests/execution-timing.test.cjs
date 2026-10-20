"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const vm = require("node:vm");

const source = readFileSync(join(__dirname, "..", "web", "app.js"), "utf8");
function timingContext() {
  const helpers = source.slice(source.indexOf("function timedOperation("), source.indexOf("function refreshExecutionTimers("));
  return vm.createContext({
    busy: true, clockAnchors: {}, completed: {}, readyResults: {}, entrySummary: null,
    performance: { now: () => 5000 },
    ...vm.runInNewContext(`(() => { ${helpers}; return { executionTiming, timedOperation }; })()`),
    helpers,
  });
}
function timing(event, response = null, live = null) {
  const context = timingContext();
  return JSON.parse(JSON.stringify(context.executionTiming(event, response, live)));
}

test("pending operations tick both step duration and cumulative time", () => {
  const event = { event: "model_request", elapsed_ms: 1250 };
  assert.deepEqual(timing(event, null, 1750), { duration: 500, total: 1750, state: "running" });
  assert.deepEqual(timing(event, null, 2250), { duration: 1000, total: 2250, state: "running" });
});

test("completed model calls freeze exact measured duration and response timestamp", () => {
  const event = { event: "model_request", elapsed_ms: 1250 };
  const response = { latency_ms: 322.75, elapsed_ms: 1580.5 };
  assert.deepEqual(timing(event, response, 10000), { duration: 322.75, total: 1580.5, state: "complete" });
  assert.deepEqual(timing(event, response, 20000), timing(event, response, 10000));
});

test("database duration is measured rather than the gap between events", () => {
  assert.deepEqual(timing({ event: "cypher", elapsed_ms: 1000 }, { duration_ms: 8.25, elapsed_ms: 1050 }),
    { duration: 8.25, total: 1050, state: "complete" });
});

test("fixed AGE query rows and their paired request expose measured query_ms", () => {
  const request = { event: "graph_query", elapsed_ms: 1000 };
  const response = { event: "graph_rows", query_ms: 7.125, elapsed_ms: 1042 };
  assert.deepEqual(timing(request, response, 2000),
    { duration: 7.125, total: 1042, state: "complete" });
  assert.deepEqual(timing(response, null, 9000),
    { duration: 7.125, total: 1042, state: "recorded" });
  assert.equal(timing({ event: "graph_rows", query_ms: 0, elapsed_ms: 1050 }).duration, 0);
  assert.deepEqual(timing(request, response, 5000), timing(request, response, 9000));
});

test("hybrid intake uses measured phase duration, not a shared lane offset", () => {
  assert.deepEqual(timing({ event: "entry_start", elapsed_ms: 3 }, { metrics: { elapsed_ms: 115.5 }, elapsed_ms: 119 }),
    { duration: 115.5, total: 119, state: "complete" });
});

test("markers never invent a duration; interrupted operations have no measured duration", () => {
  for (const event of ["start", "decision", "traversed", "entry_selected", "complete"]) {
    assert.deepEqual(timing({ event, elapsed_ms: 800 }, null, 1500),
      { duration: null, total: 800, state: "recorded" });
  }
  assert.deepEqual(timing({ event: "model_request", elapsed_ms: 800 }),
    { duration: null, total: 800, state: "incomplete" });
  assert.equal(timing({ event: "graph_rows", duration_ms: 0, elapsed_ms: 800 }).duration, 0);
});

test("each standalone lane has its own clock and completion boundary", () => {
  const context = timingContext();
  vm.runInContext(context.helpers, context);
  context.clockAnchors = {
    decision: { elapsed_ms: 100, received_at: 4800 },
    "llm-cypher": { elapsed_ms: 250, received_at: 4900 },
  };
  assert.equal(vm.runInContext('liveElapsedFor("decision")', context), 300);
  assert.equal(vm.runInContext('liveElapsedFor("entry")', context), 300);
  assert.equal(vm.runInContext('liveElapsedFor("llm-cypher")', context), 350);
  context.entrySummary = { result: { status: "clarify" } };
  assert.equal(vm.runInContext('liveElapsedFor("entry")', context), null);
  assert.equal(vm.runInContext('liveElapsedFor("decision")', context), null);
  assert.equal(vm.runInContext('liveElapsedFor("llm-cypher")', context), 350);
  context.completed["llm-cypher"] = {};
  assert.equal(vm.runInContext('liveElapsedFor("llm-cypher")', context), null);
  context.completed = {}; context.entrySummary = null; context.clockAnchors = {};
  assert.equal(vm.runInContext('liveElapsedFor("decision")', context), null);
});

test("finished lane clocks stop before comparison persistence while the peer keeps ticking", () => {
  for (const first of ["decision", "llm-cypher"]) {
    const context = timingContext();
    vm.runInContext(context.helpers, context);
    context.clockAnchors = {
      decision: { elapsed_ms: 100, received_at: 4800 },
      "llm-cypher": { elapsed_ms: 250, received_at: 4900 },
    };
    context.readyResults[first] = { event: "lane_ready" };
    const other = first === "decision" ? "llm-cypher" : "decision";
    assert.equal(vm.runInContext(`liveElapsedFor("${first}")`, context), null);
    assert.ok(vm.runInContext(`liveElapsedFor("${other}")`, context) > 0);
    assert.equal(Object.keys(context.completed).length, 0);
  }
});

test("selected procedure viewport stays readable despite widely separated retrieved roots", () => {
  const helper = source.slice(source.indexOf("function procedureViewport("), source.indexOf("function inspectNode("));
  const viewport = vm.runInNewContext(`(() => { ${helper}; return procedureViewport; })()`);
  const nodes = [
    { id: "other", procedure_id: "other" },
    { id: "chosen", procedure_id: "chosen" },
    { id: "current", procedure_id: "chosen" },
  ];
  const positions = new Map([
    ["other", { x: 95, y: 40, w: 155 }],
    ["chosen", { x: 1500, y: 40, w: 155 }],
    ["current", { x: 95, y: 304, w: 155 }],
  ]);
  for (const width of [600, 320]) {
    const frame = viewport({ nodes }, positions, "chosen", "current", width, 360);
    assert.ok(frame.width <= width / .8);
    assert.ok(frame.height <= 360 / .8);
    assert.ok(frame.x < 95 && frame.x + frame.width > 95);
    assert.ok(frame.y < 304 && frame.y + frame.height > 304);
    assert.ok(155 * Math.min(width / frame.width, 360 / frame.height) >= 124);
  }
  assert.equal(nodes.length, 3);
  assert.equal(positions.size, 3);
  assert.equal(viewport({ nodes }, positions, "unreturned", "current", 600, 360), null);
});

test("actual selected procedure is placed first within every retrieved layer", () => {
  const helper = source.slice(source.indexOf("function positionGraph("), source.indexOf("function procedureViewport("));
  const layout = vm.runInNewContext(`(() => { ${helper}; return positionGraph; })()`);
  const nodes = [
    ...Array.from({ length: 8 }, (_, i) => [
      { id: `p${i}`, procedure_id: `p${i}` },
      { id: `c${i}`, procedure_id: `p${i}` },
    ]).flat(),
    { id: "vehicle" }, { id: "action", procedure_id: "p4" },
  ];
  const edges = [
    ...Array.from({ length: 8 }, (_, i) => [
      { source: `p${i}`, target: `c${i}` }, { source: `p${i}`, target: "vehicle" },
    ]).flat(),
    { source: "c4", target: "action" },
  ];
  const result = layout({ nodes, edges }, false, "p4");
  assert.equal(result.nodes.size, nodes.length);
  assert.equal(result.positions.size, nodes.length);
  assert.equal(result.positions.get("p4").x, result.positions.get("c4").x);
  assert.equal(result.positions.get("c4").x, result.positions.get("action").x);
  assert.ok(result.positions.get("p0").x > result.positions.get("p4").x);
});

test("follow latest centers the current step even when the whole branching procedure fits", () => {
  const helper = source.slice(source.indexOf("function procedureViewport("), source.indexOf("function inspectNode("));
  const viewport = vm.runInNewContext(`(() => { ${helper}; return procedureViewport; })()`);
  const nodes = ["chosen", "current", "branch-a", "branch-b"]
    .map(id => ({ id, procedure_id: "chosen" }));
  const positions = new Map([
    ["chosen", { x: 95, y: 40, w: 155 }],
    ["current", { x: 95, y: 128, w: 155 }],
    ["branch-a", { x: 285, y: 216, w: 155 }],
    ["branch-b", { x: 475, y: 216, w: 155 }],
  ]);
  for (const width of [620, 320]) {
    const frame = viewport({ nodes }, positions, "chosen", "current", width, 360);
    assert.equal(frame.x + frame.width / 2, positions.get("current").x);
    assert.equal(frame.y + frame.height / 2, positions.get("current").y);
    assert.ok(155 * Math.min(width / frame.width, 360 / frame.height) >= 124);
    assert.equal(positions.size, nodes.length);
  }
});

test("graph titles prefer authored action text over generic result-type labels", () => {
  const helper = source.slice(source.indexOf("function nodeTitle("), source.indexOf("function ruleTitle("));
  const title = vm.runInNewContext(`(() => { ${helper}; return nodeTitle; })()`);
  const node = { id: "blower-pattern", type: "Action", result_type: "observation",
    description: "Review the recorded cabin fan-speed pattern" };
  assert.equal(title(node), node.description);
  assert.equal(title({ ...node, description: "", instruction: "Check which cabin fan speeds operate" }),
    "Check which cabin fan speeds operate");
  assert.equal(title({ ...node, title: "Cabin fan-speed check" }), "Cabin fan-speed check");
  assert.equal(title({ ...node, label: "Recorded blower operation" }), "Recorded blower operation");
  assert.equal(title({ ...node, label: " ", title: "\t" }), node.description);
  assert.equal(title({ ...node, description: "" }), "Observe indicator");
});

test("selected procedure excludes applicability context without changing returned data", () => {
  const helper = source.slice(source.indexOf("function procedureData("), source.indexOf("function resultState("));
  const filter = vm.runInNewContext(`(() => { ${helper}; return procedureData; })()`);
  const data = {
    nodes: [{ id: "p" }, { id: "entry", procedure_id: "p" }, { id: "action", procedure_id: "p" },
      { id: "vehicle" }, { id: "other" }, { id: "other-entry", procedure_id: "other" }],
    edges: [{ id: "entry-edge", source: "p", target: "entry" },
      { id: "next", source: "entry", target: "action" },
      { id: "applicability", source: "p", target: "vehicle" },
      { id: "other-applicability", source: "other", target: "vehicle" },
      { id: "unreturned-target", source: "action", target: "not-returned" }],
  };
  const original = JSON.stringify(data);
  const selected = filter(data, "p");
  assert.deepEqual(Array.from(selected.nodes, n => n.id), ["p", "entry", "action"]);
  assert.deepEqual(Array.from(selected.edges, e => e.id), ["entry-edge", "next"]);
  assert.ok(selected.nodes.every(n => data.nodes.includes(n)));
  assert.ok(selected.edges.every(e => data.edges.includes(e)));
  assert.equal(filter(data, "p", true), data);
  assert.equal(filter(data, null), data);
  assert.equal(JSON.stringify(data), original);
});

test("finished inference distinguishes evidence requests, handoff and confirmed causes", () => {
  const helper = source.slice(source.indexOf("function resultState("), source.indexOf("function positionGraph("));
  const state = vm.runInNewContext(`(() => { ${helper}; return resultState; })()`);
  assert.equal(state({ status: "next_action" }), "Recommendation ready");
  assert.equal(state({ status: "next_action" }, { handoff: false }), "Recommendation ready");
  assert.equal(state({ status: "next_action" }, { handoff: true }), "Workshop review");
  assert.equal(state({ status: "root_cause" }), "Finding supported");
  assert.equal(state({ status: "clarify" }), "Needs clarification");
  assert.equal(state({ status: "unsupported" }), "Out of scope");
  assert.equal(state({ status: "error" }), "Failed");
});

test("a submission has one request and no release or prior-context mechanism", () => {
  const run = source.slice(source.indexOf("async function run()"), source.indexOf('$("run").addEventListener'));
  assert.equal((run.match(/fetch\("\/api\/run"/g) || []).length, 1);
  for (const removed of ["api/release", "previous_run_id", "journeyRuns", "demoRunning", "manual-mode"]) {
    assert.equal(source.includes(removed), false, removed);
  }
});

test("answer route contains only real path edges plus the retrieved entry, across procedures", () => {
  const helper = source.slice(source.indexOf("function routeData("), source.indexOf("function resultState("));
  const route = vm.runInNewContext(`(() => { ${helper}; return routeData; })()`);
  const data = { nodes: [{id:"p"}, {id:"entry"}, {id:"action"}, {id:"cause", procedure_id:"other"}, {id:"vehicle"}, {id:"branch"}],
    edges: [{id:"e", source:"p", target:"entry", type:"ENTRY_POINT"},
      {id:"a", source:"entry", target:"action"}, {id:"r", source:"action", target:"cause"},
      {id:"v", source:"p", target:"vehicle", type:"APPLIES_TO"}, {id:"b", source:"action", target:"branch"}] };
  const result = route(data, ["a", "r"], "cause");
  assert.deepEqual(Array.from(result.nodes, n => n.id), ["p", "entry", "action", "cause"]);
  assert.deepEqual(Array.from(result.edges, e => e.id), ["e", "a", "r"]);
  assert.ok(result.nodes.every(n => data.nodes.includes(n)));
  assert.ok(result.edges.every(e => data.edges.includes(e)));
  assert.equal(data.nodes.length, 6);
  const recommendation = route(data, ["a"], "action");
  assert.deepEqual(Array.from(recommendation.nodes, n => n.id), ["p", "entry", "action"]);
  assert.deepEqual(Array.from(recommendation.edges, e => e.id), ["e", "a"]);
});

test("key execution has one final result; persistence markers remain in all events", () => {
  const helper = source.slice(source.indexOf("function keyEvent("), source.indexOf("function timedOperation("));
  const key = vm.runInNewContext(`(() => { ${helper}; return keyEvent; })()`);
  assert.equal(key({ event: "lane_ready" }), false);
  assert.equal(key({ event: "complete" }), true);
  assert.equal(key({ event: "answer_rejected" }), true);
});
