import { chromium } from 'playwright';
import { legalVersions } from './legal-consent.mjs';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';

// Real same-origin cookies, SSE and PostgreSQL. No routing/network mocks.
const baseURL = process.env.VIGIL_UI_URL ?? 'http://127.0.0.1:5173';
const output = '.impeccable/review';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext();
const page = await context.newPage();
const requests = [];
const errors = [];
const expectedRevocationErrors = [];
let revoking = false;
page.on('request', request => { if (request.url().includes('/api/v1/')) requests.push(new URL(request.url()).pathname + new URL(request.url()).search); });
page.on('pageerror', error => errors.push(error.message));
page.on('console', message => {
  if (message.type() !== 'error') return;
  if (revoking && message.text().includes('401') && /\/api\/v1\/(auth\/me|events|projects|monitors)/.test(message.location().url)) expectedRevocationErrors.push(message.text());
  else errors.push(message.text());
});
await page.addInitScript(() => {
  window.__liveEvidence = { urls: [], events: [], closes: 0 };
  const NativeSource = window.EventSource;
  window.EventSource = class extends NativeSource {
    constructor(...args) {
      super(...args); window.__liveEvidence.urls.push(String(args[0]));
      for (const type of ['snapshot.required', 'project.updated', 'monitor.updated', 'incident.opened', 'incident.closed']) {
        this.addEventListener(type, event => window.__liveEvidence.events.push({ type, data: JSON.parse(event.data) }));
      }
    }
    close() { window.__liveEvidence.closes++; super.close(); }
  };
});
async function mutate(path, method, data, csrf) {
  const response = await context.request.fetch(`${baseURL}/api/v1${path}`, {
    method, data,
    headers: { Origin: baseURL, 'X-Vigil-Request': 'browser', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) },
  });
  assert.ok(response.ok(), `${method} ${path}: ${response.status()}`);
  return response.status() === 204 ? null : response.json();
}
try {
  const identity = { email: `frontend.live.${Date.now()}@example.com`, password: `Vigil-QA-${Date.now()}-live`, ...legalVersions };
  await mutate('/auth/register', 'POST', identity);
  const session = await mutate('/auth/login', 'POST', identity);
  const project = await mutate('/projects', 'POST', { name: 'Projeto SSE navegador' }, session.csrf_token);
  await page.goto(baseURL);
  await page.getByText('Atualizações conectadas', { exact: true }).waitFor();
  await page.getByRole('heading', { name: 'Projeto SSE navegador', exact: true }).waitFor();
  await page.waitForFunction(() => window.__liveEvidence.events.some(event => event.type === 'snapshot.required' && event.data.reason === 'connected'));
  const beforeMutation = requests.filter(path => path.startsWith('/api/v1/projects?')).length;
  await mutate(`/projects/${project.id}`, 'PATCH', { name: 'Projeto alterado fora da aba' }, session.csrf_token);
  await page.getByRole('heading', { name: 'Projeto alterado fora da aba', exact: true }).waitFor();
  assert.ok(requests.filter(path => path.startsWith('/api/v1/projects?')).length > beforeMutation);
  await page.waitForFunction(id => window.__liveEvidence.events.some(event => event.type === 'project.updated' && event.data.project_id === id), project.id);
  console.log('SSE connected e project.updated reais reconciliados por REST.');
  const beforePeriodic = requests.filter(path => path.startsWith('/api/v1/projects?')).length;
  const periodicRead = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/projects' && response.request().method() === 'GET' && response.status() === 200, { timeout: 35000 });
  await page.waitForFunction(() => window.__liveEvidence.events.some(event => event.type === 'snapshot.required' && event.data.reason === 'periodic'), undefined, { timeout: 35000 });
  await periodicRead;
  assert.ok(requests.filter(path => path.startsWith('/api/v1/projects?')).length > beforePeriodic);
  console.log('Snapshot periódico e polling REST de 30s verificados.');
  revoking = true;
  await mutate('/auth/logout', 'POST', undefined, session.csrf_token);
  await page.getByRole('heading', { name: 'Entre no Vigil', exact: true }).waitFor({ timeout: 35000 });
  const evidence = await page.evaluate(() => window.__liveEvidence);
  assert.ok(evidence.urls.every(url => url === '/api/v1/events'));
  assert.ok(evidence.closes >= 1);
  assert.ok(evidence.events.every(event => !('owner_id' in event.data) && !('source' in event.data)));
  assert.deepEqual(errors, []);
  const report = { result: 'passed', events: evidence.events, streamUrls: evidence.urls, closes: evidence.closes, restRequests: requests.filter(path => !path.includes('/auth/')), errors, expectedRevocationErrors, externalMutationReconciled: true, periodicSnapshot: true, revokedSessionReturnsToLogin: true };
  await writeFile(`${output}/live-smoke.json`, JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ result: report.result, externalMutationReconciled: true, periodicSnapshot: true, revokedSessionReturnsToLogin: true, eventCount: evidence.events.length, errors }, null, 2));
} catch (error) {
  await page.screenshot({ path: `${output}/live-smoke-failure.png`, fullPage: true }).catch(() => {});
  throw error;
} finally { await browser.close(); }
