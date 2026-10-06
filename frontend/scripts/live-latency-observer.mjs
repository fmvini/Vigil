// Passive CDP observation: no replacement of the product's EventSource/fetch.
export function measurementOrigin(env) {
  if (env.VIGIL_LATENCY_ALLOW_RUN !== '1') throw new Error('LATENCY_WINDOW_NOT_RELEASED');
  let url;
  try { url = new URL(env.VIGIL_UI_URL ?? 'http://127.0.0.1:8080'); }
  catch { throw new Error('LOCAL_QA_ORIGIN_REQUIRED'); }
  if (!['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) || url.protocol !== 'http:' || url.pathname !== '/' || url.username || url.password || url.search || url.hash) throw new Error('LOCAL_QA_ORIGIN_REQUIRED');
  return url.origin;
}

export function percentile(values, p) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.ceil(p * sorted.length / 100) - 1];
}

export function summary(values, total, failures) {
  return { total, successful: values.length, failures, p50_ms: percentile(values, 50), p95_ms: percentile(values, 95), p99_ms: percentile(values, 99), min_ms: values.length ? Math.min(...values) : null, max_ms: values.length ? Math.max(...values) : null };
}

export function correlateUpdate(signals, snapshots, revision, name) {
  const signal = signals.find(entry => entry.type === 'project.updated' && entry.revision === revision && Number.isFinite(entry.timestamp) && entry.timestamp >= 0);
  if (!signal) return null;
  const snapshot = snapshots.find(entry => entry.revision === revision && entry.name === name && Number.isFinite(entry.request_timestamp) && entry.request_timestamp >= signal.timestamp && Number.isFinite(entry.completed_timestamp) && entry.completed_timestamp >= entry.request_timestamp);
  if (!snapshot) return null;
  return { signal, snapshot, sse_to_product_get_ms: (snapshot.request_timestamp - signal.timestamp) * 1000 };
}

export function observeNativeProjectSnapshots(cdp, { origin, projectId, qaHeader, onFailure }) {
  const signals = [], snapshots = [], pending = new Set();
  const requests = new Map(), streams = new Set();
  cdp.on('Network.requestWillBeSent', event => {
    const url = new URL(event.request.url);
    if (url.origin !== origin) { onFailure('BROWSER_REQUEST_OUTSIDE_LOCAL_ORIGIN'); return; }
    const tagged = Object.keys(event.request.headers).some(key => key.toLowerCase() === qaHeader.toLowerCase());
    if (event.request.method !== 'GET' || tagged) return;
    if (url.pathname === '/api/v1/events') streams.add(event.requestId);
    if (url.pathname === '/api/v1/projects') requests.set(event.requestId, { timestamp: event.timestamp, status: null });
  });
  cdp.on('Network.responseReceived', event => {
    const entry = requests.get(event.requestId);
    if (entry) entry.status = event.response.status;
  });
  cdp.on('Network.loadingFailed', event => { requests.delete(event.requestId); streams.delete(event.requestId); });
  cdp.on('Network.eventSourceMessageReceived', event => {
    if (!streams.has(event.requestId)) { onFailure('SSE_SOURCE_NOT_PRODUCT_STREAM'); return; }
    let payload;
    try { payload = JSON.parse(event.data); } catch { onFailure('SSE_INVALID_JSON'); return; }
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) { onFailure('SSE_INVALID_PAYLOAD'); return; }
    if ('owner_id' in payload || 'source' in payload) { onFailure('SSE_FORBIDDEN_FIELD'); return; }
    if (event.eventName === 'project.updated') {
      if (payload.project_id !== projectId || !Number.isSafeInteger(payload.revision) || payload.revision < 0) { onFailure('SSE_FOREIGN_OR_INVALID_PROJECT'); return; }
      signals.push({ type: event.eventName, project_id: projectId, request_id: event.requestId, revision: payload.revision, timestamp: event.timestamp });
    } else if (event.eventName === 'snapshot.required') signals.push({ type: event.eventName, reason: payload.reason, timestamp: event.timestamp });
  });
  cdp.on('Network.loadingFinished', event => {
    streams.delete(event.requestId);
    const entry = requests.get(event.requestId);
    requests.delete(event.requestId);
    if (!entry || entry.status !== 200) return;
    const observation = (async () => {
      try {
        const body = await cdp.send('Network.getResponseBody', { requestId: event.requestId });
        const data = JSON.parse(body.base64Encoded ? Buffer.from(body.body, 'base64').toString('utf8') : body.body);
        if (!Array.isArray(data.items) || data.items.length !== 1 || data.items[0].id !== projectId) { onFailure('PRODUCT_SNAPSHOT_NOT_OWN_SINGLETON'); return; }
        const project = data.items[0];
        snapshots.push({ project_id: projectId, request_id: event.requestId, revision: project.revision, name: project.name, request_timestamp: entry.timestamp, completed_timestamp: event.timestamp });
      } catch { onFailure('PRODUCT_SNAPSHOT_BODY_UNAVAILABLE_OR_INVALID'); }
    })();
    pending.add(observation);
    observation.finally(() => pending.delete(observation));
  });
  return { signals, snapshots, pending };
}
