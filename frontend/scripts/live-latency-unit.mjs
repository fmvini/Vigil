import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { test } from 'node:test';
import { correlateUpdate, measurementOrigin, observeNativeProjectSnapshots, percentile, summary } from './live-latency-observer.mjs';

const origin = 'http://127.0.0.1:12345';
const options = { origin, projectId: 'own-project', qaHeader: 'X-Vigil-QA-Measurement' };
function fixture() {
  const cdp = new EventEmitter(), failures = [];
  const bodies = new Map();
  cdp.send = async (method, { requestId }) => { assert.equal(method, 'Network.getResponseBody'); return bodies.get(requestId); };
  const observed = observeNativeProjectSnapshots(cdp, { ...options, onFailure: code => failures.push(code) });
  function request(id, path, timestamp, headers = {}) {
    cdp.emit('Network.requestWillBeSent', { requestId: id, timestamp, request: { method: 'GET', url: `${origin}${path}`, headers } });
  }
  function signal(data, requestId = 'stream', eventName = 'project.updated', timestamp = 10) {
    cdp.emit('Network.eventSourceMessageReceived', { requestId, eventName, timestamp, data: JSON.stringify(data) });
  }
  async function snapshot(id, name, revision, encoded = false, status = 200) {
    const body = JSON.stringify({ items: [{ id: options.projectId, name, revision }] });
    bodies.set(id, { body: encoded ? Buffer.from(body).toString('base64') : body, base64Encoded: encoded });
    cdp.emit('Network.responseReceived', { requestId: id, response: { status } });
    cdp.emit('Network.loadingFinished', { requestId: id });
    await Promise.all([...observed.pending]);
  }
  return { cdp, failures, observed, request, signal, snapshot };
}

test('nearest-rank quantiles, empty data and failures stay explicit', () => {
  assert.equal(percentile([], 99), null);
  const values = Array.from({ length: 25 }, (_, index) => 25 - index);
  assert.deepEqual(summary(values, 26, 1), { total: 26, successful: 25, failures: 1, p50_ms: 13, p95_ms: 24, p99_ms: 25, min_ms: 1, max_ms: 25 });
  assert.equal(values[0], 25);
});

test('correlation requires revision/name and a GET after native SSE', () => {
  const signals = [{ type: 'project.updated', revision: 2, timestamp: 10 }];
  const before = { revision: 2, name: 'new', request_timestamp: 9 };
  assert.equal(correlateUpdate(signals, [before], 2, 'new'), null);
  assert.equal(correlateUpdate(signals, [{ ...before, request_timestamp: null }], 2, 'new'), null);
  assert.equal(correlateUpdate(signals, [{ ...before, name: 'old', request_timestamp: 11 }], 2, 'new'), null);
  assert.equal(correlateUpdate(signals, [{ ...before, revision: 1, request_timestamp: 11 }], 2, 'new'), null);
  assert.equal(correlateUpdate([], [{ ...before, request_timestamp: 11 }], 2, 'new'), null);
  assert.equal(correlateUpdate(signals, [before, { ...before, request_timestamp: 10.2 }], 2, 'new').sse_to_product_get_ms.toFixed(2), '200.00');
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
});

test('unreadable completed product snapshot is a failure rather than fabricated data', async () => {
  const f = fixture();
  f.cdp.send = async () => { throw new Error('unavailable'); };
  f.request('body', '/api/v1/projects', 11);
  await f.snapshot('body', 'new', 2);
  assert.deepEqual(f.failures, ['PRODUCT_SNAPSHOT_BODY_UNAVAILABLE_OR_INVALID']);
  assert.deepEqual(f.observed.snapshots, []);
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
});
