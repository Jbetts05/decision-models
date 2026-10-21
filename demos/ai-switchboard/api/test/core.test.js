const test = require('node:test');
const assert = require('node:assert/strict');
const {
  ApiError, MAX_BODY_BYTES, readJson, validateInput, buildModelRequest,
  getUsage, getAnswer, runModel, createLimiter, handleCatalog, createRunHandler,
} = require('../src/core');
const { getCatalog, scenarios } = require('../src/catalog');

const env = {
  FOUNDRY_ENDPOINT: 'https://example.services.ai.azure.com',
  FOUNDRY_API_KEY: 'test-only-key',
};
const body = (overrides = {}) => ({
  modelId: 'astra',
  scenarioId: 'ticket-duplicate-charge',
  text: 'Two payments cleared for one tour ticket.',
  ...overrides,
});
const request = (value = body(), headers = {}) => new Request('https://demo.example/api/run', {
  method: 'POST',
  headers: {
    'content-type': 'application/json',
    ...headers,
  },
  body: typeof value === 'string' ? value : JSON.stringify(value),
});
const input = (overrides = {}) => validateInput(body(overrides), env);
const chatPayload = (answer = 'Billing', usage = { prompt_tokens: 34, completion_tokens: 8 }) => ({
  choices: [{ finish_reason: 'stop', message: { content: JSON.stringify({ answer }) } }],
  usage,
});
const decisionPayload = () => ({
  model: 'microsoft-decision-1',
  answers: {
    classification: {
      type: 'choice',
      choice: 'Billing',
      confidence: 0.9975,
      probabilities: { Billing: 0.9, Account: 0.04, Technical: 0.06 },
    },
  },
  usage: { input_tokens: 37, output_tokens: 9 },
});
const successFetch = async () => new Response(JSON.stringify(chatPayload()), {
  headers: { 'content-type': 'application/json' },
});
const hasStatus = (status) => (error) => error instanceof ApiError && error.status === status;

test('public catalog has four allowlisted models and eight fictional scenarios', () => {
  const result = handleCatalog();
  assert.equal(result.status, 200);
  assert.deepEqual(result.jsonBody.models.map(({ id }) => id), ['decision', 'astra', 'sol', 'luna']);
  assert.equal(result.jsonBody.scenarios.length, 8);
  for (const scenario of result.jsonBody.scenarios) {
    assert.ok(scenario.text.length > 0 && scenario.text.length <= 6000);
    assert.ok(scenario.instructions);
    assert.ok(Object.keys(scenario.criteria).length >= 2);
  }
  assert.equal(result.jsonBody.scenarios[0].instructions, result.jsonBody.scenarios[1].instructions);
  assert.deepEqual(result.jsonBody.scenarios[0].criteria, result.jsonBody.scenarios[1].criteria);
  assert.equal(result.jsonBody.scenarios[3].instructions, result.jsonBody.scenarios[5].instructions);
  assert.equal(result.jsonBody.scenarios[6].instructions, result.jsonBody.scenarios[7].instructions);
  assert.equal(result.headers['Cache-Control'], 'no-store');
});

test('deployment overrides stay server-side and catalog is an isolated copy', () => {
  const catalog = getCatalog({ ASTRA_DEPLOYMENT: ' custom-astra ', FOUNDRY_API_KEY: 'hidden' });
  assert.equal(catalog.models[1].deployment, 'custom-astra');
  assert.ok(!JSON.stringify(catalog).includes('hidden'));
  catalog.scenarios[0].criteria.Billing = 'changed';
  assert.notEqual(scenarios[0].criteria.Billing, 'changed');
});

test('anonymous requests succeed with no principal, cookies, or access allowlist', async () => {
  const handler = createRunHandler({ env, fetchImpl: successFetch });
  assert.equal((await handler(request())).status, 200);
});

test('caller-provided principal and cookie headers are ignored', async () => {
  const handler = createRunHandler({ env, fetchImpl: successFetch });
  for (const header of ['', '%%%', 'e30', 'a'.repeat(8200)]) {
    assert.equal((await handler(request(body(), {
      'x-ms-client-principal': header, cookie: 'untrusted=value',
    }))).status, 200);
  }
});

test('invalid public input is rejected before acquiring budget or fetching', async () => {
  let acquired = 0;
  let fetched = 0;
  const handler = createRunHandler({
    env,
    acquire: () => { acquired += 1; return () => {}; },
    fetchImpl: async () => { fetched += 1; return successFetch(); },
  });
  for (const value of [body({ modelId: 'unknown' }), body({ scenarioId: 'unknown' }),
    body({ endpoint: 'https://example.com' }), body({ text: '' }), '{invalid']) {
    assert.equal((await handler(request(value))).status, 400);
  }
  assert.equal((await handler(request('x'.repeat(MAX_BODY_BYTES + 1)))).status, 413);
  assert.equal((await handler(request(body(), { 'content-type': 'text/plain' }))).status, 415);
  assert.equal(acquired, 0);
  assert.equal(fetched, 0);
});

test('public handler shares its start budget regardless of caller headers', async () => {
  const handler = createRunHandler({ env, wallClock: () => 0, fetchImpl: successFetch });
  for (let i = 0; i < 96; i += 1) {
    assert.equal((await handler(request(body(), {
      'x-ms-client-principal': `caller-${i}`, 'x-forwarded-for': `192.0.2.${i}`,
    }))).status, 200);
  }
  const result = await handler(request());
  assert.equal(result.status, 429);
  assert.match(result.jsonBody.error, /shared by everyone.*Try again/);
});

test('JSON parsing accepts charset and rejects non-JSON or malformed JSON', async () => {
  assert.deepEqual(await readJson(request(body(), { 'content-type': 'application/json; charset=utf-8' })), body());
  await assert.rejects(readJson(request(body(), { 'content-type': 'text/plain' })), hasStatus(415));
  await assert.rejects(readJson(request('{not valid JSON}')), hasStatus(400));
});

test('declared body size is checked before body consumption', async () => {
  for (const length of [String(MAX_BODY_BYTES + 1), '-1', 'not-a-number']) {
    let consumed = false;
    await assert.rejects(readJson({
      headers: new Headers({ 'content-type': 'application/json', 'content-length': length }),
      text: async () => { consumed = true; return '{}'; },
    }), hasStatus(413));
    assert.equal(consumed, false);
  }
});

test('streamed request size limit is enforced without Content-Length', async () => {
  let cancelled = false;
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new Uint8Array(MAX_BODY_BYTES));
      controller.enqueue(new Uint8Array(1));
    },
    cancel() { cancelled = true; },
  });
  await assert.rejects(readJson({
    headers: new Headers({ 'content-type': 'application/json' }),
    body: stream,
  }), hasStatus(413));
  assert.equal(cancelled, true);
});

test('UTF-8 byte limit and fallback request reader also reject oversized bodies', async () => {
  await assert.rejects(readJson(request(JSON.stringify({ text: '🚀'.repeat(10000) }))), hasStatus(413));
  await assert.rejects(readJson({
    headers: new Headers({ 'content-type': 'application/json' }),
    text: async () => 'x'.repeat(MAX_BODY_BYTES + 1),
  }), hasStatus(413));
});

test('only catalog ids and the exact three request fields are accepted', () => {
  for (const value of [null, [], 'text', body({ modelId: '__proto__' }),
    body({ modelId: 'other-model' }), body({ scenarioId: 'unknown' }),
    body({ criteria: { Billing: 'custom' } }), body({ endpoint: 'https://example.com' }),
    body({ deployment: 'other-model' }), body({ model: 'gpt-6-sol' })]) {
    assert.throws(() => validateInput(value, env), hasStatus(400));
  }
});

test('text must be nonblank and 1..6000 characters, and is passed through unchanged', () => {
  for (const text of [undefined, null, 123, {}, '', ' \n\t ', 'x'.repeat(6001)]) {
    assert.throws(() => input({ text }), hasStatus(400));
  }
  assert.equal(input({ text: 'x' }).text, 'x');
  assert.equal(input({ text: 'x'.repeat(6000) }).text.length, 6000);
  assert.equal(input({ text: '  keep spaces  ' }).text, '  keep spaces  ');
});

test('Decision request uses canonical server-owned scenario criteria and deployment', () => {
  const value = input({ modelId: 'decision' });
  const result = buildModelRequest(value, env);
  assert.equal(result.url, 'https://example.services.ai.azure.com/providers/microsoft/v1/systemone');
  assert.equal(result.headers['api-key'], env.FOUNDRY_API_KEY);
  assert.deepEqual(result.body, {
    model: 'Decision-1',
    state: value.text,
    questions: { classification: {
      type: 'choice', instructions: value.scenario.instructions, criteria: value.scenario.criteria,
    } },
  });
});

test('GPT request uses strict bounded schema and same scenario/input', () => {
  const value = input();
  const result = buildModelRequest(value, env);
  assert.equal(result.url, 'https://example.services.ai.azure.com/openai/v1/chat/completions');
  assert.equal(result.body.messages[1].content, value.text);
  assert.ok(result.body.messages[0].content.includes(value.scenario.instructions));
  assert.ok(result.body.messages[0].content.includes(JSON.stringify(value.scenario.criteria)));
  assert.deepEqual(result.body.response_format.json_schema.schema.properties.answer.enum,
    Object.keys(value.scenario.criteria));
  assert.equal(result.body.response_format.json_schema.strict, true);
  assert.equal(result.body.max_completion_tokens, 1024);
  assert.equal(result.body.reasoning_effort, 'low');
});

test('each GPT deployment uses its supported server-owned reasoning and token limits', () => {
  for (const [modelId, effort, limit] of [['astra', 'low', 1024], ['luna', 'none', 512], ['sol', 'none', 512]]) {
    const result = buildModelRequest(input({ modelId }), env);
    assert.equal(result.body.reasoning_effort, effort);
    assert.equal(result.body.max_completion_tokens, limit);
  }
});

test('missing key and unsafe configured endpoints fail before fetching', () => {
  assert.throws(() => buildModelRequest(input(), {}), hasStatus(503));
  assert.throws(() => buildModelRequest(input(), { ...env, FOUNDRY_API_KEY: undefined }), hasStatus(503));
  for (const endpoint of ['http://example.com', 'https://user:secret@example.com',
    'https://example.com?token=abc', 'https://example.com/path', 'https://example.com#secret',
    'https://example.com:1234', 'not a URL']) {
    assert.throws(() => buildModelRequest(input(), { ...env, FOUNDRY_ENDPOINT: endpoint }), hasStatus(503));
  }
});

test('missing endpoint fails before budget acquisition or any upstream call', async () => {
  for (const endpoint of [undefined, '', '   ']) {
    let acquired = false;
    let fetched = false;
    const handler = createRunHandler({
      env: { ...env, FOUNDRY_ENDPOINT: endpoint },
      acquire: () => { acquired = true; return () => {}; },
      fetchImpl: async () => { fetched = true; return successFetch(); },
    });
    const result = await handler(request());
    assert.equal(result.status, 503);
    assert.deepEqual(result.jsonBody, { error: 'Model access is not configured.' });
    assert.equal(acquired, false);
    assert.equal(fetched, false);
  }
});

test('usage maps only real nonnegative integer counters and leaves unknown counts null', () => {
  assert.deepEqual(getUsage(chatPayload()), { inputTokens: 34, outputTokens: 8 });
  assert.deepEqual(getUsage(decisionPayload()), { inputTokens: 37, outputTokens: 9 });
  assert.deepEqual(getUsage({ usage: { prompt_tokens: 0, completion_tokens: 0 } }), { inputTokens: 0, outputTokens: 0 });
  for (const payload of [{}, { usage: null }, { usage: { total_tokens: 20 } },
    { usage: { prompt_tokens: '20', completion_tokens: -1 } },
    { usage: { input_tokens: 1.5, output_tokens: Infinity } }]) {
    assert.deepEqual(getUsage(payload), { inputTokens: null, outputTokens: null });
  }
});

test('GPT accepts only a completed valid choice without explanations', () => {
  assert.equal(getAnswer(chatPayload(), input()), 'Billing');
  for (const payload of [{}, chatPayload('Unknown'), { choices: [{ finish_reason: 'length', message: { content: '{"answer":"Billing"}' } }] },
    { choices: [{ finish_reason: 'stop', message: { content: 'Billing' } }] },
    { choices: [{ finish_reason: 'stop', message: { refusal: 'No', content: '{"answer":"Billing"}' } }] },
    { choices: [{ finish_reason: 'stop', message: { content: '{"answer":"Billing","explanation":"invented"}' } }] }]) {
    assert.throws(() => getAnswer(payload, input()), hasStatus(502));
  }
});

test('Decision answer returns only the selected choice without confidence or probabilities', () => {
  const value = input({ modelId: 'decision' });
  assert.equal(getAnswer(decisionPayload(), value), 'Billing');
  for (const classification of [{}, { choice: 'Unknown', probabilities: {} },
    { choice: 'Billing', probabilities: { Billing: '0.9', Account: 0.04, Technical: 0.06 } },
    { choice: 'Billing', probabilities: { Billing: 2, Account: 0.04, Technical: 0.06 } }]) {
    assert.throws(() => getAnswer({ answers: { classification } }, value), hasStatus(502));
  }
});

test('Decision maps the confirmed live schema and preserves its exact label casing', () => {
  const value = {
    model: input({ modelId: 'decision' }).model,
    scenario: { criteria: { billing: 'Billing requests', account: 'Account requests' } },
    text: 'A duplicate charge',
  };
  const payload = {
    model: 'microsoft-decision-1',
    answers: {
      classification: {
        choice: 'billing', confidence: 0.9975, probabilities: { billing: 0.9975, account: 0.0025 }, type: 'choice',
      },
    },
    usage: { input_tokens: 58, output_tokens: 1 },
  };
  assert.equal(getAnswer(payload, value), 'billing');
  assert.deepEqual(getUsage(payload), { inputTokens: 58, outputTokens: 1 });
});

test('latency includes reading full upstream response and fetch is bounded with no redirect', async () => {
  let time = 100;
  let calls = 0;
  let sentBody;
  const providerPayload = { ...chatPayload(), model: 'gpt-6-astra' };
  const result = await runModel(input(), env, {
    now: () => time,
    fetchImpl: async (url, options) => {
      calls += 1;
      assert.equal(options.method, 'POST');
      assert.equal(options.redirect, 'error');
      assert.ok(options.signal instanceof AbortSignal);
      sentBody = JSON.parse(options.body);
      assert.equal(sentBody.model, 'gpt-6-astra');
      time = 115;
      return { ok: true, json: async () => { time = 145.125; return providerPayload; } };
    },
  });
  assert.deepEqual(result, {
    modelId: 'astra', model: 'GPT-6 Astra', deployment: 'gpt-6-astra',
    answer: 'Billing', latencyMs: 45.13, inputTokens: 34, outputTokens: 8,
    details: {
      context: {
        messages: sentBody.messages,
        reasoning_effort: sentBody.reasoning_effort,
        max_completion_tokens: sentBody.max_completion_tokens,
      },
      schema: sentBody.response_format,
      output: { model: providerPayload.model, choices: providerPayload.choices, usage: providerPayload.usage },
    },
  });
  assert.ok(!JSON.stringify(result).includes(env.FOUNDRY_API_KEY));
  assert.equal(calls, 1);
});

test('Decision requests map usage and unknown token counts remain null', async () => {
  let sentBody;
  const result = await runModel(input({ modelId: 'decision' }), env, {
    fetchImpl: async (url, options) => {
      sentBody = JSON.parse(options.body);
      return new Response(JSON.stringify(decisionPayload()));
    },
  });
  assert.equal(result.model, 'Microsoft Decision One');
  assert.equal(result.answer, 'Billing');
  assert.equal(result.inputTokens, 37);
  assert.equal(result.outputTokens, 9);
  assert.deepEqual(result.details, {
    context: { state: sentBody.state },
    schema: { questions: sentBody.questions },
    output: {
      model: decisionPayload().model, answers: decisionPayload().answers, usage: decisionPayload().usage,
    },
  });
  assert.equal(result.confidence, undefined);
  assert.equal(result.probabilities, undefined);
  assert.ok(!JSON.stringify(result).includes(env.FOUNDRY_API_KEY));
  const missing = await runModel(input(), env, {
    fetchImpl: async () => new Response(JSON.stringify({ choices: chatPayload().choices })),
  });
  assert.equal(missing.inputTokens, null);
  assert.equal(missing.outputTokens, null);
  assert.equal(missing.details.output.model, undefined);
  assert.equal(missing.details.output.usage, undefined);
  assert.deepEqual(JSON.parse(JSON.stringify(missing.details.output)), { choices: chatPayload().choices });
});

test('upstream errors map to readable statuses without retries or body leakage', async () => {
  for (const [upstreamStatus, expectedStatus] of [[429, 429], [408, 504], [504, 504], [401, 503],
    [403, 503], [400, 502], [422, 502], [500, 502], [404, 502]]) {
    let calls = 0;
    await assert.rejects(runModel(input(), env, {
      fetchImpl: async () => {
        calls += 1;
        return new Response('SENSITIVE UPSTREAM BODY', { status: upstreamStatus });
      },
    }), (error) => hasStatus(expectedStatus)(error) && error.upstreamStatus === upstreamStatus &&
      !error.message.includes('SENSITIVE'));
    assert.equal(calls, 1);
  }
});

test('network errors, malformed upstream JSON, and truncation are typed failures', async () => {
  await assert.rejects(runModel(input(), env, {
    fetchImpl: async () => { throw new Error('SECRET NETWORK DETAIL'); },
  }), (error) => hasStatus(502)(error) && !error.message.includes('SECRET'));
  await assert.rejects(runModel(input(), env, {
    fetchImpl: async () => new Response('not JSON'),
  }), hasStatus(502));
  await assert.rejects(runModel(input(), env, {
    fetchImpl: async () => new Response(JSON.stringify({ choices: [] })),
  }), hasStatus(502));
});

test('fetch timeout and timeout during full response reading produce 504', async () => {
  await assert.rejects(runModel(input(), env, {
    fetchImpl: async () => { throw new DOMException('internal details', 'TimeoutError'); },
  }), hasStatus(504));
  const controller = new AbortController();
  await assert.rejects(runModel(input(), env, {
    makeSignal: () => controller.signal,
    fetchImpl: async () => ({
      ok: true,
      json: async () => {
        controller.abort();
        throw new DOMException('internal details', 'AbortError');
      },
    }),
  }), hasStatus(504));
});

test('per-instance limiter shares 16 concurrent requests and releases capacity once', () => {
  const acquire = createLimiter(() => 0);
  const release = Array.from({ length: 16 }, () => acquire());
  assert.throws(() => acquire(), hasStatus(429));
  release[0]();
  release[0]();
  const replacement = acquire();
  assert.throws(() => acquire(), hasStatus(429));
  replacement();
  release.slice(1).forEach((done) => done());
});

test('rolling limiter permits 96 starts per minute and cleans expired windows', () => {
  let time = 0;
  const acquire = createLimiter(() => time);
  for (let i = 0; i < 96; i += 1) acquire()();
  assert.throws(() => acquire(), hasStatus(429));
  time = 59999;
  assert.throws(() => acquire(), hasStatus(429));
  time = 60000;
  for (let i = 0; i < 96; i += 1) acquire()();
  assert.throws(() => acquire(), hasStatus(429));
});

test('handler returns safe error envelope and never logs secret exception details', async () => {
  const logs = [];
  const handler = createRunHandler({
    env,
    fetchImpl: async () => { throw new Error(`secret ${env.FOUNDRY_API_KEY}`); },
  });
  const result = await handler(request(), { error: (value) => logs.push(value) });
  assert.equal(result.status, 502);
  assert.deepEqual(Object.keys(result.jsonBody), ['error']);
  assert.deepEqual(logs, [{ name: 'ApiError', code: 'UPSTREAM_NETWORK', status: 502 }]);
  assert.ok(!JSON.stringify({ logs, result }).includes(env.FOUNDRY_API_KEY));
});

test('handler checks method before body reading, budget acquisition, or fetching', async () => {
  let called = false;
  const handler = createRunHandler({
    env,
    acquire: () => { called = true; },
    fetchImpl: async () => { called = true; },
  });
  const result = await handler({
    method: 'GET',
    headers: new Headers(),
    text: async () => { throw new Error('Body must not be read'); },
  });
  assert.equal(result.status, 405);
  assert.equal(called, false);
});

test('handler success envelope and four-model parallel request admission', async () => {
  const handler = createRunHandler({
    env,
    fetchImpl: async (url) => new Response(JSON.stringify(
      url.includes('/systemone') ? decisionPayload() : chatPayload())),
  });
  const results = await Promise.all(['decision', 'astra', 'luna', 'sol'].map((modelId) =>
    handler(request(body({ modelId })))));
  assert.ok(results.every((result) => result.status === 200));
  assert.deepEqual(Object.keys(results[0].jsonBody),
    ['modelId', 'model', 'deployment', 'answer', 'latencyMs', 'inputTokens', 'outputTokens', 'details']);
  for (const result of results.slice(1)) {
    const modelId = result.jsonBody.modelId;
    assert.equal(result.jsonBody.details.context.reasoning_effort, modelId === 'astra' ? 'low' : 'none');
    assert.equal(result.jsonBody.details.context.max_completion_tokens, modelId === 'astra' ? 1024 : 512);
  }
});

test('handler releases concurrency after upstream failures and rejects incorrect method', async () => {
  const handler = createRunHandler({
    env,
    fetchImpl: async () => { throw new Error('network failure'); },
  });
  for (let i = 0; i < 20; i += 1) assert.equal((await handler(request())).status, 502);
  assert.equal((await handler({ method: 'GET' })).status, 405);
});

test('handler maps unexpected internal failures to a safe 500 without fallback', async () => {
  const handler = createRunHandler({
    env,
    acquire: () => { throw new Error('SENSITIVE INTERNAL'); },
    fetchImpl: successFetch,
  });
  const logs = [];
  const result = await handler(request(), { error: (value) => logs.push(value) });
  assert.equal(result.status, 500);
  assert.deepEqual(logs, [{ name: 'ApiError', code: 'INTERNAL', status: 500 }]);
  assert.ok(!JSON.stringify(result).includes('SENSITIVE'));
});
