// Real Edge, synthetic loopback fixture. Tests tooling, never product latency.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { test } from 'node:test';
import { chromium } from 'playwright';
import { correlateUpdate, observeNativeProjectSnapshots } from './live-latency-observer.mjs';

test('real native Edge SSE and completed JSON are observed by exact CDP requestId', { timeout: 30000 }, async () => {
  const project = { id: 'observer-fixture', name: 'before', revision: 0 };
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
      res.end('<h1>before</h1><script>const source = new EventSource("/api/v1/events"); source.addEventListener("project.updated", async () => { const data = await (await fetch("/api/v1/projects")).json(); document.querySelector("h1").textContent = data.items[0].name; });</script>');
    }
  });
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const origin = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const page = await browser.newPage();
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Network.enable');
    const failures = [];
    const observed = observeNativeProjectSnapshots(cdp, { origin, projectId: project.id, qaHeader: 'X-Vigil-QA-Measurement', onFailure: code => failures.push(code) });
    await page.goto(origin);
    await assertEventually(() => observed.signals.some(signal => signal.reason === 'connected'));
    Object.assign(project, { name: 'after', revision: 1 });
    stream.write(`event: project.updated\ndata: ${JSON.stringify({ project_id: project.id, revision: 1 })}\n\n`);
    await page.getByRole('heading', { name: 'after', exact: true }).waitFor({ timeout: 10000 });
    await assertEventually(() => correlateUpdate(observed.signals, observed.snapshots, 1, 'after') !== null);
    assert.ok(correlateUpdate(observed.signals, observed.snapshots, 1, 'after').sse_to_product_get_ms >= 0);
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
