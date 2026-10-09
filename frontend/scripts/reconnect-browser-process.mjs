// Private QA controller over stdin/stdout. Credentials stay in process memory.
import { chromium } from 'playwright';
import { legalVersions } from './legal-consent.mjs';
import react from '@vitejs/plugin-react';
import { createServer as createVite } from 'vite';
import { createServer, request as upstreamRequest } from 'node:http';
import { createInterface } from 'node:readline';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { mkdir, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const output = new URL('../.impeccable/review/', import.meta.url);
const token = randomUUID();
const vite = await createVite({
  root: frontend, configFile: false, plugins: [react()],
  cacheDir: fileURLToPath(new URL(`../.impeccable/review/reconnect-vite-${token}/`, import.meta.url)),
  logLevel: 'silent', server: { middlewareMode: true, hmr: false, watch: null },
});
let target, baseURL, csrf, project, owner, initialConstructors;
const sockets = new Set(), streams = new Set(), gatewayFailures = new Map(), crashedApis = new Set();
const report = { result: 'running', errors: [], expectedErrors: [], gatewaySseErrors: 0, externalChecks: false };

function ownApi(value) {
  const url = new URL(value);
  assert.equal(url.protocol, 'http:'); assert.equal(url.hostname, '127.0.0.1');
  assert.ok(Number(url.port) >= 1024); assert.equal(url.pathname, '/');
  assert.equal(url.username + url.password + url.search + url.hash, '');
  return url;
}

const server = createServer((req, res) => {
  if (!req.url.startsWith('/api/') && !req.url.startsWith('/health/')) {
    vite.middlewares(req, res, () => { res.writeHead(404).end(); }); return;
  }
  if (!target) { res.writeHead(503).end(); return; }
  const requestTarget = target;
  const upstream = upstreamRequest({ hostname: requestTarget.hostname, port: requestTarget.port, path: req.url, method: req.method, headers: req.headers });
  const recordFailure = () => {
    if (crashedApis.has(requestTarget.origin)) gatewayFailures.set(req.url, (gatewayFailures.get(req.url) ?? 0) + 1);
  };
  const entry = { upstream, res };
  const isStream = req.url === '/api/v1/events';
  if (isStream) streams.add(entry);
  res.on('close', () => { streams.delete(entry); upstream.destroy(); });
  upstream.on('response', response => {
    res.writeHead(response.statusCode, response.headers);
    response.pipe(res);
    response.on('error', () => {
      if (res.destroyed) return;
      recordFailure(); res.destroy();
    });
  });
  upstream.on('error', () => {
    if (res.destroyed) return;
    recordFailure();
    if (isStream) report.gatewaySseErrors++;
    if (res.headersSent) res.destroy();
    else res.writeHead(503, { 'Content-Type': 'application/json' }).end(JSON.stringify({ error: { code: 'qa_upstream_unavailable', message: 'QA upstream unavailable' } }));
  });
  req.pipe(upstream);
});
server.on('connection', socket => { sockets.add(socket); socket.on('close', () => sockets.delete(socket)); });
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
baseURL = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext();
const page = await context.newPage();
page.setDefaultTimeout(12000);
page.on('pageerror', error => report.errors.push(error.message));
page.on('console', message => {
  if (message.type() !== 'error') return;
  const location = message.location().url;
  const path = location.startsWith(baseURL) ? new URL(location).pathname + new URL(location).search : '';
  if (/(503|ERR_|net::)/.test(message.text()) && (gatewayFailures.get(path) ?? 0) > 0) {
    gatewayFailures.set(path, gatewayFailures.get(path) - 1); report.expectedErrors.push(message.text());
  }
  else if (/\/api\/v1\/(events|auth\/me)/.test(location) && /(401|ERR_|net::)/.test(message.text())) report.expectedErrors.push(message.text());
  else report.errors.push({ message: message.text(), path: path.split('?')[0] });
});
page.on('request', req => { assert.equal(new URL(req.url()).origin, baseURL, 'Browser request escaped owned QA origin'); });
await page.addInitScript(() => {
  const Native = window.EventSource;
  window.__reconnect = { sources: [], urls: [], events: [], errors: [], opens: 0, closes: 0 };
  window.EventSource = class extends Native {
    constructor(...args) {
      super(...args); window.__reconnect.sources.push(this); window.__reconnect.urls.push(String(args[0]));
      this.addEventListener('open', () => window.__reconnect.opens++);
      this.addEventListener('error', () => window.__reconnect.errors.push(this.readyState));
      for (const type of ['snapshot.required', 'project.updated']) this.addEventListener(type, event => window.__reconnect.events.push({ type, data: JSON.parse(event.data) }));
    }
    close() { window.__reconnect.closes++; super.close(); }
  };
});

async function mutate(api, path, method, data) {
  const response = await context.request.fetch(`${api}/api/v1${path}`, {
    method, data, headers: { Origin: baseURL, 'X-Vigil-Request': 'browser', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) },
  });
  assert.ok(response.ok(), `QA REST failed: ${method} ${path} ${response.status()}`);
  return response.status() === 204 ? null : response.json();
}
async function evidence() {
  return page.evaluate(() => ({
    urls: window.__reconnect.urls, events: window.__reconnect.events, errors: window.__reconnect.errors,
    opens: window.__reconnect.opens, closes: window.__reconnect.closes,
    states: window.__reconnect.sources.map(source => source.readyState),
  }));
}
async function save() {
  await mkdir(output, { recursive: true });
  report.evidence = await evidence();
  // No cookies, passwords, CSRF tokens or request headers are serialized.
  await writeFile(new URL('reconnect-smoke.json', output), JSON.stringify(report, null, 2) + '\n');
}
async function command(input) {
  if (input.command === 'connect') {
    target = ownApi(input.api);
    const credentials = { email: `reconnect-${randomUUID()}@example.com`, password: randomUUID() + '-QA', ...legalVersions };
    owner = (await mutate(baseURL, '/auth/register', 'POST', credentials)).id;
    csrf = (await mutate(baseURL, '/auth/login', 'POST', credentials)).csrf_token;
    project = await mutate(baseURL, '/projects', 'POST', { name: 'Projeto antes da queda' });
    await page.goto(baseURL);
    await page.getByText('Atualizações conectadas', { exact: true }).waitFor();
    await page.getByRole('heading', { name: project.name, exact: true }).waitFor();
    initialConstructors = (await evidence()).urls.length;
    return { owner, project: project.id, initialConstructors };
  }
  if (input.command === 'observe_failure') {
    await page.waitForFunction(() => window.__reconnect.errors.includes(EventSource.CLOSED));
    assert.ok(report.gatewaySseErrors > 0);
    report.closedObserved = true;
    return { closed: true, gatewaySseErrors: report.gatewaySseErrors };
  }
  if (input.command === 'arm_crash') {
    crashedApis.add(target.origin);
    return { armed: true };
  }
  if (input.command === 'gap_commit') {
    const api = ownApi(input.api);
    project = await mutate(api.origin, `/projects/${project.id}`, 'PATCH', { name: 'Projeto alterado durante queda' });
    assert.equal(project.revision, 1);
    return { revision: project.revision };
  }
  if (input.command === 'restore') {
    target = ownApi(input.api);
    await page.getByText('Atualizações conectadas', { exact: true }).waitFor();
    await page.getByRole('heading', { name: project.name, exact: true }).waitFor();
    const current = await evidence();
    assert.ok(current.urls.length > initialConstructors, 'Closed native EventSource was never replaced');
    report.restoredRevision = project.revision;
    return { revision: project.revision, constructors: current.urls.length };
  }
  if (input.command === 'cutover') {
    const before = (await evidence()).opens;
    target = ownApi(input.api);
    for (const { upstream, res } of streams) { upstream.destroy(); res.destroy(); }
    await page.waitForFunction(previous => window.__reconnect.opens > previous, before);
    await page.getByText('Atualizações conectadas', { exact: true }).waitFor();
    return { connected: true };
  }
  if (input.command === 'final_commit') {
    const api = ownApi(input.api);
    project = await mutate(api.origin, `/projects/${project.id}`, 'PATCH', { name: 'Projeto na réplica substituta' });
    assert.equal(project.revision, 2);
    await page.getByRole('heading', { name: project.name, exact: true }).waitFor();
    await page.waitForFunction(id => window.__reconnect.events.some(event => event.type === 'project.updated' && event.data.project_id === id && event.data.revision === 2), project.id);
    report.finalRevision = project.revision;
    return { revision: project.revision };
  }
  if (input.command === 'logout') {
    await page.getByRole('button', { name: 'Sair da conta', exact: true }).click();
    await page.getByRole('heading', { name: 'Entre no Vigil', exact: true }).waitFor();
    const count = (await evidence()).urls.length;
    await new Promise(resolve => setTimeout(resolve, 2500));
    assert.equal((await evidence()).urls.length, count, 'Reconnect survived logout/unmount');
    report.logoutStopsReconnect = true;
    assert.deepEqual(report.errors, []);
    const current = await evidence();
    assert.ok(current.urls.every(url => url === '/api/v1/events'));
    assert.ok(current.events.every(event => !('owner_id' in event.data) && !('source' in event.data)));
    report.result = 'passed'; await save();
    return { passed: true };
  }
  if (input.command === 'stop') return { stopped: true };
  throw new Error('Unknown private QA command');
}

console.log(JSON.stringify({ ready: true, ui: baseURL }));
const lines = createInterface({ input: process.stdin });
try {
  for await (const line of lines) {
    const input = JSON.parse(line);
    try { console.log(JSON.stringify({ ok: true, ...(await command(input)) })); }
    catch (error) {
      report.result = 'failed'; report.failureType = error.name;
      await save(); await page.screenshot({ path: fileURLToPath(new URL('reconnect-failure.png', output)) });
      console.log(JSON.stringify({ ok: false, error: error.name }));
    }
    if (input.command === 'stop') break;
  }
} finally {
  lines.close(); await context.close(); await browser.close();
  for (const socket of sockets) socket.destroy();
  await new Promise(resolve => server.close(resolve)); await vite.close();
}
