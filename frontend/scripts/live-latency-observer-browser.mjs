// Real Edge, synthetic loopback fixture. Tests tooling, never product latency.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { test } from 'node:test';
import { chromium } from 'playwright';
import { correlateUpdate, observeNativeProjectSnapshots } from './live-latency-observer.mjs';
import { buildUpdateEvidence, qaUpdateName } from './live-latency-replay.mjs';

test('real native Edge SSE and completed JSON are observed by exact CDP requestId', { timeout: 30000 }, async () => {
  const runId = '11111111-1111-4111-8111-111111111111';
  const project = { id: '22222222-2222-4222-8222-222222222222', name: qaUpdateName(runId, 0), revision: 0, url: 'https://private.example/PRIVATE_SENTINEL', email: 'private@example.com', headers: { Authorization: 'PRIVATE_SENTINEL' } };
  let stream, browser;
  const server = createServer((req, res) => {
    if (req.url === '/api/v1/events') {
      stream = res;
      res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' });
      res.write('event: snapshot.required\ndata: {"reason":"connected"}\n\n');
    } else if (req.url.startsWith('/api/v1/projects')) {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ items: [project] }));
    } else {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(`<h1>${project.name}</h1><script>const source = new EventSource("/api/v1/events"); source.addEventListener("project.updated", async () => { const data = await (await fetch("/api/v1/projects")).json(); document.querySelector("h1").textContent = data.items[0].name; });</script>`);
    }
  });
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const origin = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Network.enable');
    const failures = [];
    const observed = observeNativeProjectSnapshots(cdp, { origin, projectId: project.id, qaHeader: 'X-Vigil-QA-Measurement', onFailure: code => failures.push(code) });
    await page.goto(origin);
    await assertEventually(() => observed.signals.some(signal => signal.reason === 'connected'));
    const name = qaUpdateName(runId, 1);
    const start = await page.evaluate(expected => {
      const started = performance.now();
      window.fixtureDomWitness = new Promise(resolve => {
        const observer = new MutationObserver(() => {
          const actual = document.querySelector('h1').textContent;
          if (actual === expected) { observer.disconnect(); resolve({ dom_name: actual, dom_observed_ms: performance.now() }); }
        });
        observer.observe(document.querySelector('h1'), { childList: true, characterData: true, subtree: true });
      });
      return { patch_started_ms: started, realm_time_origin_ms: performance.timeOrigin, viewport_width: innerWidth, viewport_height: innerHeight };
    }, name);
    Object.assign(project, { name, revision: 1 });
    stream.write(`event: project.updated\ndata: ${JSON.stringify({ project_id: project.id, revision: 1 })}\n\n`);
    await page.getByRole('heading', { name, exact: true }).waitFor({ timeout: 10000 });
    const dom = await page.evaluate(() => window.fixtureDomWitness);
    await assertEventually(() => correlateUpdate(observed.signals, observed.snapshots, 1, name) !== null);
    const correlation = correlateUpdate(observed.signals, observed.snapshots, 1, name);
    assert.ok(correlation.sse_to_product_get_ms >= 0);
    const evidence = buildUpdateEvidence({ runId, projectId: project.id, ordinal: 1, expectedRevision: 1, signal: correlation.signal, snapshot: correlation.snapshot, browser: { ...start, ...dom, viewport: 'desktop' } });
    assert.notEqual(evidence.cdp.sse.request_id, evidence.cdp.product_get.request_id);
    assert.ok(evidence.cdp.product_get.started_s >= evidence.cdp.sse.timestamp_s);
    assert.ok(evidence.cdp.product_get.completed_s >= evidence.cdp.product_get.started_s);
    assert.equal(evidence.browser.dom_name, name);
    assert.ok(evidence.browser.dom_observed_ms >= evidence.browser.patch_started_ms);
    for (const forbidden of ['PRIVATE_SENTINEL','private@example.com','https://','Authorization','headers']) {
      assert.ok(!JSON.stringify(evidence).includes(forbidden));
      assert.ok(!JSON.stringify(observed.snapshots).includes(forbidden));
    }
    assert.deepEqual(failures, []);
    assert.equal(observed.snapshots.length, 1);
  } finally {
    if (browser) await browser.close();
    stream?.end();
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
});

async function assertEventually(predicate) {
  const deadline = performance.now() + 10000;
  while (!predicate()) {
    assert.ok(performance.now() < deadline, 'Native browser CDP evidence missing');
    await new Promise(resolve => setTimeout(resolve, 25));
  }
}
