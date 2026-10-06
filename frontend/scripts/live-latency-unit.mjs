import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { test } from 'node:test';
import { correlateUpdate, measurementOrigin, observeNativeProjectSnapshots, percentile, summary } from './live-latency-observer.mjs';
import { buildUpdateEvidence, qaUpdateName, replayLatencyReport } from './live-latency-replay.mjs';

const origin = 'http://127.0.0.1:12345';
const runId = '11111111-1111-4111-8111-111111111111';
const projectId = '22222222-2222-4222-8222-222222222222';
const options = { origin, projectId, qaHeader: 'X-Vigil-QA-Measurement' };
function evidenceInput(ordinal = 1) {
  const name = qaUpdateName(runId, ordinal);
  const desktop = ordinal <= 15;
  return {
    runId, projectId, ordinal, expectedRevision: ordinal,
    signal: { request_id: 'stream.1', project_id: projectId, revision: ordinal, timestamp: 1000000 + ordinal },
    snapshot: { request_id: `get.${ordinal}`, project_id: projectId, revision: ordinal, name, request_timestamp: 1000000 + ordinal + .2, completed_timestamp: 1000000 + ordinal + .22 },
    browser: { viewport: desktop ? 'desktop' : 'mobile', viewport_width: desktop ? 1440 : 390, viewport_height: desktop ? 900 : 844, realm_time_origin_ms: 1770000000000, patch_started_ms: ordinal * 1000, dom_observed_ms: ordinal * 1000 + 250, dom_name: name },
  };
}
function reportFixture() {
  const updates = Array.from({ length: 29 }, (_, index) => {
    const evidence = buildUpdateEvidence(evidenceInput(index + 1));
    return { ordinal: index + 1, viewport: evidence.browser.viewport, warmup: index < 2 || (index >= 15 && index < 17), status: 200, revision: index + 1, success: true, native_sse_revision_match: true, product_rest_revision_match: true, product_get_started_after_sse: true, periodic_overlap: index === 10, patch_rtt_ms: 15, request_start_to_dom_ms: 250, sse_to_product_get_ms: (evidence.cdp.product_get.started_s - evidence.cdp.sse.timestamp_s) * 1000, evidence };
  });
  const rest = [];
  for (const viewport of ['desktop', 'mobile']) for (let round = 0; round < 33; round++) for (const route of ['projects', 'monitors', 'metrics', 'incidents']) rest.push({ route, viewport, warmup: round < 3, ordinal: round < 3 ? round + 1 : round - 2, status: 200, success: true, elapsed_ms: round + 1 });
  const measuredRest = rest.filter(s => !s.warmup), measuredUpdates = updates.filter(s => !s.warmup);
  const groups = {};
  for (const route of ['projects', 'monitors', 'metrics', 'incidents']) {
    groups[route] = summary(measuredRest.filter(s => s.route === route).map(s => s.elapsed_ms), 60, 0);
    groups[route].by_viewport = Object.fromEntries(['desktop', 'mobile'].map(viewport => [viewport, summary(measuredRest.filter(s => s.route === route && s.viewport === viewport).map(s => s.elapsed_ms), 30, 0)]));
  }
  const ordered = measuredUpdates.filter(s => !s.periodic_overlap);
  return {
    report_version: 3, result: 'passed', run_id: runId,
    identities: { owner_id: '33333333-3333-4333-8333-333333333333', project_id: projectId, initial_project_revision: 0 },
    errors: [], network: { unexpected_statuses: [] }, external_checks_executed: false, shared_gates_modified: false,
    cleanup: { disposition: 'confirmed_api_scope', project_archive: 'confirmed', session_logout: 'confirmed', old_token_revocation: 'verified', unknown_commit_possible: [], guards: ['current_session_owner_and_csrf', 'singleton_project_id_slug_marker_current_name_revision_private_and_zero_monitors', 'captured_project_404_and_authenticated_list_empty'].map(guard => ({ guard, status: 'passed' })) },
    rest, updates,
    summary: {
      rest_by_route: groups, rest_pooled_mixed_routes: summary(measuredRest.map(s => s.elapsed_ms), 240, 0),
      patch_rtt: summary(measuredUpdates.map(s => s.patch_rtt_ms), 25, 0),
      request_start_to_dom_upper_bound: summary(measuredUpdates.map(s => s.request_start_to_dom_ms), 25, 0),
      sse_ordered_without_observed_periodic_overlap: summary(ordered.map(s => s.request_start_to_dom_ms), ordered.length, 0),
      native_sse_to_product_get: summary(measuredUpdates.map(s => s.sse_to_product_get_ms), 25, 0),
      ui_by_viewport: Object.fromEntries(['desktop', 'mobile'].map(viewport => { const subset = measuredUpdates.filter(s => s.viewport === viewport); return [viewport, summary(subset.map(s => s.request_start_to_dom_ms), subset.length, 0)]; })),
      actual_counts: { rest_measured: 240, rest_warmup: 24, updates_measured: 25, updates_warmup: 4 },
      all_created_resources: { synthetic_owners: 1, captured_projects: 1, monitors_created_by_tooling: 0, external_checks_executed_by_tooling: 0 },
    },
  };
}
function fixture() {
  const cdp = new EventEmitter(), failures = [];
  const bodies = new Map();
  const starts = new Map();
  cdp.send = async (method, { requestId }) => { assert.equal(method, 'Network.getResponseBody'); return bodies.get(requestId); };
  const observed = observeNativeProjectSnapshots(cdp, { ...options, onFailure: code => failures.push(code) });
  function request(id, path, timestamp, headers = {}) {
    starts.set(id, timestamp);
    cdp.emit('Network.requestWillBeSent', { requestId: id, timestamp, request: { method: 'GET', url: `${origin}${path}`, headers } });
  }
  function signal(data, requestId = 'stream', eventName = 'project.updated', timestamp = 10) {
    cdp.emit('Network.eventSourceMessageReceived', { requestId, eventName, timestamp, data: JSON.stringify(data) });
  }
  async function snapshot(id, name, revision, encoded = false, status = 200, items) {
    const body = JSON.stringify({ items: items ?? [{ id: options.projectId, name, revision }] });
    bodies.set(id, { body: encoded ? Buffer.from(body).toString('base64') : body, base64Encoded: encoded });
    cdp.emit('Network.responseReceived', { requestId: id, response: { status } });
    cdp.emit('Network.loadingFinished', { requestId: id, timestamp: Math.max(starts.get(id) ?? 0, 20) });
    await Promise.all([...observed.pending]);
  }
  return { cdp, failures, observed, request, signal, snapshot };
}

test('nearest-rank quantiles, empty data and failures stay explicit', () => {
  assert.equal(percentile([], 99), null);
  const values = Array.from({ length: 25 }, (_, index) => 25 - index);
  assert.deepEqual(summary(values, 26, 1), { total: 26, successful: 25, failures: 1, p50_ms: 13, p95_ms: 24, p99_ms: 25, min_ms: 1, max_ms: 25 });
  assert.equal(values[0], 25);
  const report = reportFixture();
  assert.equal(replayLatencyReport(report).result, 'passed_replay');
  // Additional v2 metadata remains compatible, without entering projected evidence.
  report.methodology = { arbitrary_note: 'kept' }; report.summary.note = 'kept';
  assert.equal(replayLatencyReport(report).result, 'passed_replay');
  for (const change of [r => { r.summary.rest_by_route.metrics.p95_ms += 1; }, r => { r.summary.rest_pooled_mixed_routes.successful = 239; }, r => { r.rest.pop(); }, r => { r.rest[0].warmup = false; }, r => { r.rest[4].ordinal = 1; }, r => { r.rest[15].route = 'private'; }, r => { r.rest[20].viewport = 'other'; }, r => { r.rest[22].elapsed_ms = NaN; }]) {
    const corrupt = reportFixture(); change(corrupt);
    assert.equal(replayLatencyReport(corrupt).result, 'failed_replay');
  }
});

test('correlation requires revision/name and a GET after native SSE', () => {
  const signals = [{ type: 'project.updated', revision: 2, timestamp: 10 }];
  const before = { revision: 2, name: 'new', request_timestamp: 9, completed_timestamp: 12 };
  assert.equal(correlateUpdate(signals, [before], 2, 'new'), null);
  assert.equal(correlateUpdate(signals, [{ ...before, request_timestamp: null }], 2, 'new'), null);
  assert.equal(correlateUpdate(signals, [{ ...before, name: 'old', request_timestamp: 11 }], 2, 'new'), null);
  assert.equal(correlateUpdate(signals, [{ ...before, revision: 1, request_timestamp: 11 }], 2, 'new'), null);
  assert.equal(correlateUpdate([], [{ ...before, request_timestamp: 11 }], 2, 'new'), null);
  assert.equal(correlateUpdate(signals, [before, { ...before, request_timestamp: 10.2 }], 2, 'new').sse_to_product_get_ms.toFixed(2), '200.00');
  assert.equal(correlateUpdate(signals, [{ ...before, request_timestamp: 11, completed_timestamp: 10 }], 2, 'new'), null);
  assert.equal(correlateUpdate([{ ...signals[0], timestamp: NaN }], [{ ...before, request_timestamp: 11 }], 2, 'new'), null);
  const mutations = [
    r => { r.updates[1].evidence.cdp.product_get.request_id = r.updates[0].evidence.cdp.product_get.request_id; },
    r => { r.updates[0].evidence.cdp.sse.request_id = r.updates[0].evidence.cdp.product_get.request_id; },
    r => { r.updates[0].evidence.cdp.product_get.started_s = 0; },
    r => { r.updates[0].evidence.cdp.product_get.completed_s = 0; },
    r => { r.updates[0].evidence.cdp.sse.timestamp_s = Infinity; },
    r => { r.updates[1].evidence.cdp.sse.timestamp_s = 1; },
    r => { r.updates[0].evidence.expected.revision = true; },
    r => { r.updates[0].evidence.cdp.sse.revision = 2; },
    r => { r.updates[0].evidence.cdp.product_get.revision = 2; },
    r => { r.updates[0].evidence.cdp.product_get.project_id = 'foreign'; },
    r => { r.updates[0].evidence.run_id = projectId; },
    r => { r.updates[0].ordinal = 0; },
    r => { r.updates[0].evidence.browser.dom_name = 'private name'; },
    r => { r.updates[0].evidence.browser.dom_observed_ms = 0; },
    r => { r.updates[1].evidence.browser.realm_time_origin_ms += 1; },
    r => { r.updates[0].evidence.browser.viewport = 'mobile'; },
    r => { r.updates[0].sse_to_product_get_ms += .01; },
    r => { r.updates[0].request_start_to_dom_ms += .01; },
    r => { r.updates[0].native_sse_revision_match = false; },
    r => { r.updates[0].warmup = false; },
    r => { r.updates.push(structuredClone(r.updates[0])); },
  ];
  for (const change of mutations) { const r = reportFixture(); change(r); assert.equal(replayLatencyReport(r).result, 'failed_replay'); }
  // One SSE stream repeats 29 times. GET IDs alone must be unique; clocks differ by orders of magnitude.
  assert.equal(new Set(reportFixture().updates.map(s => s.evidence.cdp.sse.request_id)).size, 1);
  assert.equal(replayLatencyReport(reportFixture()).result, 'passed_replay');
});

test('CDP request IDs correlate concurrent identical GET URLs with reversed completion', async () => {
  const f = fixture();
  f.request('stream', '/api/v1/events', 1);
  f.request('before', '/api/v1/projects?limit=100', 9);
  f.signal({ project_id: options.projectId, revision: 2 });
  f.request('after', '/api/v1/projects?limit=100', 10.2);
  await f.snapshot('after', 'new', 2, true);
  await f.snapshot('before', 'new', 2);
  assert.equal(correlateUpdate(f.observed.signals, f.observed.snapshots, 2, 'new').snapshot.request_timestamp, 10.2);
  const captured = correlateUpdate(f.observed.signals, f.observed.snapshots, 2, 'new');
  assert.equal(captured.signal.request_id, 'stream');
  assert.equal(captured.snapshot.request_id, 'after');
  assert.equal(captured.snapshot.completed_timestamp, 20);
  assert.equal(captured.snapshot.project_id, projectId);
  assert.deepEqual(f.failures, []);
});

test('tagged reads, failed HTTP and aborted requests cannot prove reconciliation', async () => {
  const f = fixture();
  f.request('tagged', '/api/v1/projects', 11, { 'x-vigil-qa-measurement': 'rest' });
  await f.snapshot('tagged', 'new', 2);
  f.request('failed', '/api/v1/projects', 12);
  await f.snapshot('failed', 'new', 2, false, 500);
  f.request('aborted', '/api/v1/projects', 13);
  f.cdp.emit('Network.loadingFailed', { requestId: 'aborted' });
  await f.snapshot('aborted', 'new', 2);
  assert.deepEqual(f.observed.snapshots, []);
  f.request('foreign', '/api/v1/projects', 14);
  await f.snapshot('foreign', 'private', 2, false, 200, [{ id: 'foreign', name: 'PRIVATE_SENTINEL', revision: 2 }]);
  f.request('mixed', '/api/v1/projects', 15);
  await f.snapshot('mixed', 'private', 2, false, 200, [{ id: projectId, name: 'new', revision: 2 }, { id: 'foreign' }]);
  assert.deepEqual(f.observed.snapshots, []);
  assert.deepEqual(f.failures, ['PRODUCT_SNAPSHOT_NOT_OWN_SINGLETON', 'PRODUCT_SNAPSHOT_NOT_OWN_SINGLETON']);
});

test('foreign source/project and private or malformed SSE payloads fail closed', () => {
  const f = fixture();
  f.signal({ project_id: options.projectId, revision: 1 });
  f.request('stream', '/api/v1/events', 1);
  f.signal(null);
  f.signal({ project_id: 'foreign', revision: 1 });
  f.signal({ project_id: options.projectId, revision: -1 });
  f.signal({ project_id: options.projectId, revision: 1, owner_id: 'private' });
  f.cdp.emit('Network.eventSourceMessageReceived', { requestId: 'stream', data: '{' });
  assert.deepEqual(f.failures, ['SSE_SOURCE_NOT_PRODUCT_STREAM', 'SSE_INVALID_PAYLOAD', 'SSE_FOREIGN_OR_INVALID_PROJECT', 'SSE_FOREIGN_OR_INVALID_PROJECT', 'SSE_FORBIDDEN_FIELD', 'SSE_INVALID_JSON']);
  assert.deepEqual(f.observed.signals, []);
  const input = evidenceInput();
  input.signal.headers = { Authorization: 'PRIVATE_SENTINEL' };
  input.signal.email = 'private@example.com'; input.signal.cookie = 'PRIVATE_SENTINEL';
  input.snapshot.body = { url: 'https://private.example/PRIVATE_SENTINEL' }; input.snapshot.query = 'PRIVATE_SENTINEL';
  input.browser.credentials = 'PRIVATE_SENTINEL';
  const projected = buildUpdateEvidence(input);
  const serialized = JSON.stringify(projected);
  for (const forbidden of ['PRIVATE_SENTINEL','private@example.com','https://','Authorization','cookie','headers','credentials','query','body']) assert.ok(!serialized.includes(forbidden));
  assert.equal(projected.expected.name, qaUpdateName(runId, 1));
  assert.equal(projected.browser.dom_name, input.browser.dom_name);
  for (const change of [i => { i.snapshot.name = 'PRIVATE_SENTINEL'; }, i => { i.browser.dom_name = 'PRIVATE_SENTINEL'; }, i => { i.signal.request_id = 'private@example.com'; }, i => { i.snapshot.request_id = 'https://private.example'; }, i => { i.ordinal = 30; }, i => { i.runId = 'private'; }]) {
    const bad = evidenceInput(); change(bad);
    assert.throws(() => buildUpdateEvidence(bad), error => !error.message.includes('PRIVATE_SENTINEL') && !error.message.includes('private@example.com') && !error.message.includes('https://'));
  }
  // A UUID must be a string: RegExp.test alone coerces a singleton array or
  // boxed string. Never retain these objects in the projected JSON evidence.
  for (const coercedId of [[projectId], new String(projectId)]) {
    const bad = evidenceInput();
    bad.projectId = coercedId;
    bad.signal.project_id = coercedId;
    bad.snapshot.project_id = coercedId;
    assert.throws(() => buildUpdateEvidence(bad), /EVIDENCE_IDENTITY_MISMATCH/);
  }
  const injected = reportFixture(); injected.updates[0].evidence.headers = 'PRIVATE_SENTINEL';
  const failure = replayLatencyReport(injected);
  assert.equal(failure.result,'failed_replay'); assert.ok(!JSON.stringify(failure).includes('PRIVATE_SENTINEL'));
});

test('unreadable completed product snapshot is a failure rather than fabricated data', async () => {
  const f = fixture();
  f.cdp.send = async () => { throw new Error('unavailable'); };
  f.request('body', '/api/v1/projects', 11);
  await f.snapshot('body', 'new', 2);
  assert.deepEqual(f.failures, ['PRODUCT_SNAPSHOT_BODY_UNAVAILABLE_OR_INVALID']);
  assert.deepEqual(f.observed.snapshots, []);
  for (const change of [r => { r.result = 'failed'; r.errors = [{ code: 'PRIVATE_SENTINEL' }]; }, r => { r.cleanup.old_token_revocation = 'not_verified'; }, r => { r.cleanup.unknown_commit_possible.push('unknown'); }, r => { r.cleanup.guards[0].status = 'failed'; }, r => { r.cleanup.guards[0].guard = 'unrelated'; }, r => { r.errors.push({ code: 'failure' }); }, r => { r.network.unexpected_statuses.push({ status: 500 }); }, r => { r.updates[0].evidence = null; }]) {
    const r = reportFixture(); change(r); const outcome = replayLatencyReport(r);
    assert.equal(outcome.result, 'failed_replay'); assert.ok(!JSON.stringify(outcome).includes('PRIVATE_SENTINEL'));
  }
});

test('window guard and foreign origin refuse execution before browser/setup', () => {
  assert.throws(() => measurementOrigin({}), /LATENCY_WINDOW_NOT_RELEASED/);
  assert.throws(() => measurementOrigin({ VIGIL_LATENCY_ALLOW_RUN: '0' }), /LATENCY_WINDOW_NOT_RELEASED/);
  for (const url of ['https://example.com', 'http://127.0.0.1:8080/path', 'http://user:password@127.0.0.1:8080', 'http://127.0.0.1:8080?token=private', 'http://127.0.0.1:8080#fragment', 'invalid']) {
    assert.throws(() => measurementOrigin({ VIGIL_LATENCY_ALLOW_RUN: '1', VIGIL_UI_URL: url }), /LOCAL_QA_ORIGIN_REQUIRED/);
  }
  for (const host of ['127.0.0.1', 'localhost', '[::1]']) {
    assert.equal(measurementOrigin({ VIGIL_LATENCY_ALLOW_RUN: '1', VIGIL_UI_URL: `http://${host}:8080/` }), `http://${host}:8080`);
  }
  assert.deepEqual(replayLatencyReport({ report_version: 2, private: 'PRIVATE_SENTINEL' }), { result: 'unsupported_report_version', code: 'UNSUPPORTED_REPORT_VERSION' });
  assert.equal(replayLatencyReport(null).result, 'unsupported_report_version');
  assert.throws(() => qaUpdateName(runId, 30), /EVIDENCE_UPDATE_LIMIT/);
  assert.equal(qaUpdateName(runId, 0), `QA latency ${runId} #000`);
});
