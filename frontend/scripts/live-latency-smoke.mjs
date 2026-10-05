import { chromium, request } from 'playwright';
import { fileURLToPath } from 'node:url';
import { correlateUpdate, measurementOrigin, observeNativeProjectSnapshots, summary } from './live-latency-observer.mjs';
import { randomBytes, randomUUID } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { setTimeout as sleep } from 'node:timers/promises';

// Run only in Maestro's released window. Never changes product code or shared gates.
let origin;
try { origin = measurementOrigin(process.env); }
catch (error) { console.error(error.message); process.exit(2); }
const runId = randomUUID();
const reportDirectory = fileURLToPath(new URL(`../.impeccable/review/live-latency/${runId}/`, import.meta.url));
const reportPath = `${reportDirectory}/report.json`;
const deadlineMs = 10_000;
const qaHeader = 'X-Vigil-QA-Measurement';
const viewportPlan = [
  { name: 'desktop', width: 1440, height: 900, measuredUpdates: 13 },
  { name: 'mobile', width: 390, height: 844, measuredUpdates: 12 },
];
const report = {
  report_version: 2, result: 'prepared', run_id: runId, origin, started_at: new Date().toISOString(),
  fixture_kind: 'synthetic_private_owner_empty_project', external_checks_executed: false, shared_gates_modified: false,
  methodology: {
    quantiles: 'nearest-rank: sorted[ceil(percentile * n / 100) - 1]',
    rest_scope: 'browser performance.now immediately before fetch through complete JSON parsing; warmups excluded',
    ui_scope: 'browser performance.now immediately before PATCH fetch through MutationObserver observing exact heading text',
    ui_after_commit: 'request-start to DOM is an upper bound on the post-commit portion; exact commit-to-DOM is not measured',
    clocks: 'REST/PATCH-to-DOM use browser performance.now; SSE-to-product-GET uses only CDP monotonic timestamps, never mixed clocks',
    sse_observation: 'CDP Network.eventSourceMessageReceived; native product EventSource/fetch remain untouched',
    reconciliation: 'matching native project.updated revision, subsequent untagged GET snapshot by exact CDP requestId and matching DOM; polling remains enabled',
    dataset: 'one new private project, zero monitors; empty metrics/incidents; not a pipeline or populated-database benchmark',
    rest_samples_per_route_per_viewport: 30, rest_warmups_per_route_per_viewport: 3,
    updates_measured: 25, updates_warmup: 4, update_start_spacing_min_ms: 1000,
    rest_start_spacing_min_ms: 100, deadline_ms: deadlineMs,
    limitations: ['small samples; p99 approaches the observed maximum', 'no SLA or capacity claim', 'REST pooled quantiles mix different routes', 'periodic/polling overlap can make causal SSE attribution ambiguous', 'JSON checkpoints and setup/cleanup are outside timed intervals'],
  },
  versions: {}, identities: { owner_id: null, project_id: null }, viewports: [],
  rest: [], updates: [], errors: [], network: { totals: {}, unexpected_statuses: [] },
  cleanup: {
    scope: 'public_api_project_archive_and_current_session_revocation', physical_purge: false,
    disposition: 'not_started', project_archive: 'not_created', session_logout: 'not_created', old_token_revocation: 'not_verified',
    retained_synthetic_owner_and_archive: false, unknown_commit_possible: [], guards: [],
    retention_note: 'Owner, archived project and revoked session row are intentionally retained; no database purge or empty-database claim.',
  },
};
class Failure extends Error {
  constructor(code, status = null) { super(code); this.code = code; this.status = status; }
}
function require(condition, code) { if (!condition) throw new Failure(code); }
async function checkpoint() { await writeFile(reportPath, JSON.stringify(report, null, 2)); }
function recordFailure(code, stage, status = null) { report.errors.push({ code, stage, status }); }
function routeTemplate(path) {
  const pathname = new URL(path, origin).pathname;
  if (pathname.startsWith('/api/v1/auth/')) return pathname;
  if (pathname === '/api/v1/projects') return '/api/v1/projects';
  if (pathname === '/api/v1/events') return '/api/v1/events';
  if (pathname === '/health/ready') return pathname;
  if (pathname.startsWith('/api/v1/projects/')) return pathname.replace(/^\/api\/v1\/projects\/[^/]+/, '/api/v1/projects/:id');
  return 'other_local_resource';
}
function recordHttp(method, path, status) {
  const route = routeTemplate(path);
  const key = `${method} ${route} ${status}`;
  report.network.totals[key] = (report.network.totals[key] ?? 0) + 1;
}
let browser, context, page;
let csrf = null;
let oldCookie = null;
let currentName = null;
let currentRevision = null;
let initialRevision = null;
let projectSlug = null;
let registrationAttempted = false;
let createAttempted = false;
let loginAttempted = false;
let sessionConfirmed = false;
let nextUpdateIndex = 0;
let lastUpdateStart = -Infinity;
let lastRestStart = -Infinity;
const identity = { email: `latency.${runId}@example.com`, password: randomBytes(24).toString('base64url') };
const description = `Synthetic local QA latency run ${runId}; no external checks.`;
const nameFor = index => `QA latency ${runId} #${String(index).padStart(3, '0')}`;
let signals = [], snapshots = [], pendingObservers = new Set();
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function ownRoute(path) {
  const allowed = ['/auth/register', '/auth/login', '/auth/me', '/auth/logout', '/projects'];
  const id = report.identities.project_id;
  if (id) allowed.push(`/projects/${id}`, `/projects/${id}/monitors`, `/projects/${id}/metrics`, `/projects/${id}/incidents`);
  require(allowed.includes(path.split('?')[0]), 'REQUEST_OUTSIDE_RUN_ALLOWLIST');
}
async function api(path, method = 'GET', body, expected = 200) {
  ownRoute(path);
  const headers = { Origin: origin, [qaHeader]: 'setup-cleanup' };
  if (method !== 'GET') {
    headers['X-Vigil-Request'] = 'browser';
    if (csrf) headers['X-CSRF-Token'] = csrf;
  }
  let response;
  try { response = await context.request.fetch(`${origin}/api/v1${path}`, { method, data: body, headers, timeout: deadlineMs, maxRedirects: 0 }); }
  catch { throw new Failure('API_TRANSPORT_OR_TIMEOUT'); }
  recordHttp(method, `/api/v1${path}`, response.status());
  if (response.status() !== expected) throw new Failure('API_UNEXPECTED_STATUS', response.status());
  if (expected === 204 || expected === 401 || expected === 404) return null;
  try { return await response.json(); } catch { throw new Failure('API_INVALID_JSON'); }
}
async function validateOwner() {
  const session = await api('/auth/me');
  require(session.user.id === report.identities.owner_id && session.user.email === identity.email, 'OWNER_IDENTITY_DIVERGED');
  require(session.csrf_token === csrf, 'SESSION_CHANGED');
}
async function validateProject() {
  await validateOwner();
  const list = await api('/projects?limit=100&offset=0');
  require(list.total === 1 && list.items.length === 1 && list.items[0].id === report.identities.project_id, 'PROJECT_INVENTORY_DIVERGED');
  const project = await api(`/projects/${report.identities.project_id}`);
  require(project.id === report.identities.project_id && project.name === currentName && project.description === description && project.public_slug === projectSlug && project.revision === currentRevision && project.archived_at === null && project.public_status_enabled === false, 'PROJECT_IDENTITY_OR_REVISION_DIVERGED');
  const monitors = await api(`/projects/${report.identities.project_id}/monitors?limit=100&offset=0`);
  require(monitors.total === 0 && monitors.items.length === 0, 'UNEXPECTED_MONITOR_OR_RESOURCE');
}
async function browserSpacing(lastStart, spacing) {
  const now = await page.evaluate(() => performance.now());
  if (Number.isFinite(lastStart) && now < lastStart + spacing) await sleep(lastStart + spacing - now);
}
function observeBrowser(cdp) {
  const observation = observeNativeProjectSnapshots(cdp, { origin, projectId: report.identities.project_id, qaHeader, onFailure: code => recordFailure(code, 'observation') });
  ({ signals, snapshots, pending: pendingObservers } = observation);
  page.on('pageerror', () => recordFailure('BROWSER_JAVASCRIPT_ERROR', 'observation'));
  page.on('console', message => {
    if (message.type() === 'error') recordFailure('BROWSER_CONSOLE_ERROR', 'observation');
  });
  page.on('response', response => {
    const url = new URL(response.url());
    const method = response.request().method();
    if (url.origin !== origin || !url.pathname.startsWith('/api/v1/')) return;
    recordHttp(method, url.href, response.status());
    if (response.status() >= 400) report.network.unexpected_statuses.push({ method, route: routeTemplate(url.href), status: response.status() });

  });
}
async function waitForObservation(predicate, code) {
  const until = performance.now() + deadlineMs;
  while (!predicate()) {
    if (performance.now() >= until) throw new Failure(code);
    await sleep(25);
  }
}
async function timedRest(route, viewport, warmup, ordinal) {
  ownRoute(route.path);
  await browserSpacing(lastRestStart, 100);
  const result = await page.evaluate(async ({ path, timeout }) => {
    const start = performance.now();
    try {
      const response = await fetch(`/api/v1${path}`, { credentials: 'same-origin', redirect: 'error', headers: { Accept: 'application/json', 'X-Vigil-QA-Measurement': 'rest' }, signal: AbortSignal.timeout(timeout) });
      const data = await response.json();
      return { start_ms: start, elapsed_ms: performance.now() - start, status: response.status, json_complete: true, item_count: Array.isArray(data.items) ? data.items.length : null, total: Number.isSafeInteger(data.total) ? data.total : null, sample_count: Number.isSafeInteger(data.sample_count) ? data.sample_count : null };
    } catch (error) { return { start_ms: start, elapsed_ms: performance.now() - start, status: null, json_complete: false, code: error.name === 'TimeoutError' ? 'REST_TIMEOUT' : 'REST_TRANSPORT_OR_JSON_ERROR' }; }
  }, { path: route.path, timeout: deadlineMs });
  lastRestStart = result.start_ms;
  const validDataset = route.key === 'projects' ? result.total === 1 && result.item_count === 1 : route.key === 'metrics' ? result.sample_count === 0 : result.total === 0 && result.item_count === 0;
  report.rest.push({ route: route.key, viewport, warmup, ordinal, elapsed_ms: result.elapsed_ms, status: result.status, success: result.status === 200 && result.json_complete && validDataset });
  if (result.status !== 200 || !result.json_complete || !validDataset) throw new Failure(result.code ?? 'REST_STATUS_OR_DATASET_DIVERGED', result.status);
}
async function timedUpdate(viewport, warmup) {
  await browserSpacing(lastUpdateStart, 1000);
  const ordinal = ++nextUpdateIndex;
  const name = nameFor(ordinal);
  const expectedRevision = currentRevision + 1;
  const signalOffset = signals.length;
  const result = await page.evaluate(async ({ id, name, csrfToken, timeout }) => {
    const main = document.querySelector('#main');
    if (!main) return { code: 'DOM_TARGET_MISSING', status: null };
    let observer, timer;
    let start;
    const dom = new Promise(resolve => {
      const check = () => {
        if (document.querySelector('#main .page-heading h1')?.textContent === name) {
          observer.disconnect(); clearTimeout(timer); resolve({ elapsed_ms: performance.now() - start, timed_out: false });
        }
      };
      observer = new MutationObserver(check);
      observer.observe(main, { childList: true, characterData: true, subtree: true });
      timer = setTimeout(() => { observer.disconnect(); resolve({ elapsed_ms: performance.now() - start, timed_out: true }); }, timeout);
    });
    start = performance.now();
    try {
      const response = await fetch(`/api/v1/projects/${id}`, {
        method: 'PATCH', credentials: 'same-origin', redirect: 'error',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-Vigil-Request': 'browser', 'X-CSRF-Token': csrfToken, 'X-Vigil-QA-Measurement': 'patch' },
        body: JSON.stringify({ name }), signal: AbortSignal.timeout(timeout),
      });
      const data = await response.json();
      const patch = { status: response.status, patch_rtt_ms: performance.now() - start, payload_matches: data.id === id && data.name === name, revision: Number.isSafeInteger(data.revision) ? data.revision : null };
      if (response.status !== 200 || !patch.payload_matches) { observer.disconnect(); clearTimeout(timer); return { ...patch, start_ms: start, code: 'PATCH_STATUS_OR_IDENTITY_DIVERGED' }; }
      const observed = await dom;
      return { ...patch, start_ms: start, request_start_to_dom_ms: observed.elapsed_ms, dom_timed_out: observed.timed_out };
    } catch (error) {
      observer.disconnect(); clearTimeout(timer);
      return { start_ms: start, status: null, patch_rtt_ms: performance.now() - start, code: error.name === 'TimeoutError' ? 'PATCH_TIMEOUT' : 'PATCH_TRANSPORT_OR_JSON_ERROR' };
    }
  }, { id: report.identities.project_id, name, csrfToken: csrf, timeout: deadlineMs });
  lastUpdateStart = result.start_ms ?? lastUpdateStart;
  const sample = { ordinal, viewport, warmup, status: result.status, revision: result.revision ?? null, patch_rtt_ms: result.patch_rtt_ms ?? null, request_start_to_dom_ms: result.request_start_to_dom_ms ?? null, success: false, native_sse_revision_match: false, product_rest_revision_match: false, product_get_started_after_sse: false, periodic_overlap: false };
  report.updates.push(sample);
  if (result.status === 200 && result.payload_matches) { currentName = name; currentRevision = result.revision; }
  if (result.code) throw new Failure(result.code, result.status);
  require(result.revision === expectedRevision, 'PATCH_REVISION_NOT_INCREMENTED_BY_ONE');
  require(!result.dom_timed_out && Number.isFinite(result.request_start_to_dom_ms), 'DOM_RECONCILIATION_TIMEOUT');
  await waitForObservation(() => correlateUpdate(signals.slice(signalOffset), snapshots, result.revision, name) !== null, 'SSE_OR_SUBSEQUENT_PRODUCT_REST_CORRELATION_MISSING');
  const correlation = correlateUpdate(signals.slice(signalOffset), snapshots, result.revision, name);
  sample.native_sse_revision_match = true;
  sample.product_rest_revision_match = true;
  sample.product_get_started_after_sse = true;
  sample.sse_to_product_get_ms = correlation.sse_to_product_get_ms;
  sample.periodic_overlap = signals.slice(signalOffset).some(entry => entry.type === 'snapshot.required' && ['periodic', 'backpressure'].includes(entry.reason));
  sample.success = true;
  await checkpoint();
}
async function cleanup() {
  report.cleanup.disposition = 'pending_review';
  report.cleanup.retained_synthetic_owner_and_archive = registrationAttempted;
  // Close the page first; its native SSE and polling cannot race cleanup requests.
  if (page && !page.isClosed()) await page.close().catch(() => {});
  if (!context || !sessionConfirmed) return;
  let ownerVerified = false;
  try {
    await validateOwner(); ownerVerified = true;
    report.cleanup.guards.push({ guard: 'current_session_owner_and_csrf', status: 'passed' });
    if (report.identities.project_id) {
      await validateProject();
      report.cleanup.guards.push({ guard: 'singleton_project_id_slug_marker_current_name_revision_private_and_zero_monitors', status: 'passed' });
      await api(`/projects/${report.identities.project_id}`, 'DELETE', undefined, 204);
      await api(`/projects/${report.identities.project_id}`, 'GET', undefined, 404);
      const projects = await api('/projects?limit=100&offset=0');
      require(projects.total === 0 && projects.items.length === 0, 'ACTIVE_PROJECT_REMAINED_AFTER_ARCHIVE');
      report.cleanup.project_archive = 'confirmed';
      report.cleanup.guards.push({ guard: 'captured_project_404_and_authenticated_list_empty', status: 'passed' });
    } else if (createAttempted) report.cleanup.project_archive = 'identity_unknown';
  } catch (error) {
    report.cleanup.guards.push({ guard: 'owner_project_prevalidation_or_archive_confirmation', status: 'failed', code: error.code ?? 'CLEANUP_GUARD_OR_TRANSPORT_FAILURE' });
    if (report.identities.project_id && report.cleanup.project_archive !== 'confirmed') report.cleanup.project_archive = 'failed';
  }
  if (ownerVerified) {
    try {
      await api('/auth/logout', 'POST', undefined, 204);
      await api('/auth/me', 'GET', undefined, 401);
      report.cleanup.session_logout = 'confirmed';
      if (oldCookie) {
        const verifier = await request.newContext({ baseURL: origin, extraHTTPHeaders: { Cookie: `${oldCookie.name}=${oldCookie.value}`, [qaHeader]: 'revocation-proof' } });
        try {
          const response = await verifier.get('/api/v1/auth/me', { timeout: deadlineMs, maxRedirects: 0 });
          recordHttp('GET', '/api/v1/auth/me', response.status());
          require(response.status() === 401, 'OLD_SESSION_TOKEN_STILL_AUTHENTICATED');
          report.cleanup.old_token_revocation = 'verified';
        } finally { await verifier.dispose(); }
      }
    } catch (error) {
      report.cleanup.guards.push({ guard: 'current_session_logout_and_old_token_revocation', status: 'failed', code: error.code ?? 'SESSION_CLEANUP_TRANSPORT_FAILURE' });
    }
  }
  const projectOkay = report.cleanup.project_archive === 'confirmed' || (!createAttempted && report.cleanup.project_archive === 'not_created');
  if (projectOkay && report.cleanup.session_logout === 'confirmed' && report.cleanup.old_token_revocation === 'verified' && report.cleanup.unknown_commit_possible.length === 0) report.cleanup.disposition = 'confirmed_api_scope';
}
function summarize() {
  const rest = report.rest.filter(sample => !sample.warmup);
  const updates = report.updates.filter(sample => !sample.warmup);
  const byRoute = {};
  for (const route of ['projects', 'monitors', 'metrics', 'incidents']) {
    const entries = rest.filter(sample => sample.route === route);
    byRoute[route] = summary(entries.filter(sample => sample.success).map(sample => sample.elapsed_ms), entries.length, entries.filter(sample => !sample.success).length);
    byRoute[route].by_viewport = Object.fromEntries(viewportPlan.map(viewport => {
      const subset = entries.filter(sample => sample.viewport === viewport.name);
      return [viewport.name, summary(subset.filter(sample => sample.success).map(sample => sample.elapsed_ms), subset.length, subset.filter(sample => !sample.success).length)];
    }));
  }
  const sseOrdered = updates.filter(sample => sample.success && sample.product_get_started_after_sse && !sample.periodic_overlap);
  report.summary = {
    rest_by_route: byRoute,
    rest_pooled_mixed_routes: summary(rest.filter(sample => sample.success).map(sample => sample.elapsed_ms), rest.length, rest.filter(sample => !sample.success).length),
    patch_rtt: summary(updates.filter(sample => sample.success && Number.isFinite(sample.patch_rtt_ms)).map(sample => sample.patch_rtt_ms), updates.length, updates.filter(sample => !sample.success).length),
    request_start_to_dom_upper_bound: summary(updates.filter(sample => sample.success).map(sample => sample.request_start_to_dom_ms), updates.length, updates.filter(sample => !sample.success).length),
    sse_ordered_without_observed_periodic_overlap: summary(sseOrdered.map(sample => sample.request_start_to_dom_ms), sseOrdered.length, 0),
    native_sse_to_product_get: summary(updates.filter(sample => sample.success).map(sample => sample.sse_to_product_get_ms), updates.length, updates.filter(sample => !sample.success).length),
    ui_by_viewport: Object.fromEntries(viewportPlan.map(viewport => {
      const entries = updates.filter(sample => sample.viewport === viewport.name);
      return [viewport.name, summary(entries.filter(sample => sample.success).map(sample => sample.request_start_to_dom_ms), entries.length, entries.filter(sample => !sample.success).length)];
    })),
    actual_counts: { rest_measured: rest.length, rest_warmup: report.rest.filter(sample => sample.warmup).length, updates_measured: updates.length, updates_warmup: report.updates.filter(sample => sample.warmup).length },
    all_created_resources: { synthetic_owners: report.identities.owner_id ? 1 : 0, captured_projects: report.identities.project_id ? 1 : 0, monitors_created_by_tooling: 0, external_checks_executed_by_tooling: 0 },
  };
}
await mkdir(reportDirectory, { recursive: true });
await checkpoint();
try {
  report.result = 'running';
  const frontendPackage = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'));
  const playwrightPackage = JSON.parse(await readFile(new URL('../node_modules/playwright/package.json', import.meta.url), 'utf8'));
  report.versions = { node: process.version, playwright: playwrightPackage.version, frontend_package: frontendPackage.version, build_revision: process.env.VIGIL_BUILD_REVISION && /^[\w.-]{1,80}$/.test(process.env.VIGIL_BUILD_REVISION) ? process.env.VIGIL_BUILD_REVISION : null, browser_channel: 'msedge' };
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  report.versions.browser = browser.version();
  context = await browser.newContext({ viewport: viewportPlan[0], timezoneId: 'America/Sao_Paulo' });
  const ready = await context.request.get(`${origin}/health/ready`, { timeout: deadlineMs, maxRedirects: 0 });
  require(ready.status() === 200, 'COMPOSE_NOT_READY');
  require((await context.cookies(origin)).length === 0, 'CONTEXT_HAS_EXISTING_COOKIES');
  registrationAttempted = true;
  const user = await api('/auth/register', 'POST', identity, 201);
  require(uuidPattern.test(user.id) && user.email === identity.email, 'REGISTERED_IDENTITY_INVALID');
  report.identities.owner_id = user.id;
  report.cleanup.retained_synthetic_owner_and_archive = true;
  loginAttempted = true;
  const login = await api('/auth/login', 'POST', identity);
  require(login.user.id === user.id && login.user.email === identity.email && typeof login.csrf_token === 'string', 'LOGIN_OWNER_IDENTITY_DIVERGED');
  csrf = login.csrf_token; sessionConfirmed = true;
  await validateOwner();
  const sessionCookies = (await context.cookies(origin)).filter(cookie => cookie.httpOnly && ['vigil_session', '__Host-vigil_session'].includes(cookie.name));
  require(sessionCookies.length === 1, 'EXCLUSIVE_SESSION_COOKIE_NOT_FOUND'); oldCookie = sessionCookies[0];
  const empty = await api('/projects?limit=100&offset=0');
  require(empty.total === 0 && empty.items.length === 0, 'NEW_OWNER_ALREADY_HAS_PROJECTS');
  currentName = nameFor(0); createAttempted = true;
  const project = await api('/projects', 'POST', { name: currentName, description, public_status_enabled: false }, 201);
  require(uuidPattern.test(project.id) && Number.isSafeInteger(project.revision) && typeof project.public_slug === 'string', 'CREATED_PROJECT_IDENTITY_INVALID');
  report.identities.project_id = project.id; currentRevision = project.revision; initialRevision = project.revision; projectSlug = project.public_slug;
  await validateProject();
  page = await context.newPage();
  const cdp = await context.newCDPSession(page); await cdp.send('Network.enable'); observeBrowser(cdp);
  await page.goto(origin);
  await page.getByRole('heading', { name: currentName, exact: true }).waitFor({ timeout: deadlineMs });
  await page.getByText('Atualizações conectadas', { exact: true }).waitFor({ timeout: deadlineMs });
  await waitForObservation(() => signals.some(signal => signal.type === 'snapshot.required' && signal.reason === 'connected'), 'NATIVE_SSE_CONNECTION_NOT_OBSERVED');
  report.versions.public_script_assets = await page.locator('script[src]').evaluateAll(scripts => scripts.map(script => new URL(script.src).pathname));
  const routes = [
    { key: 'projects', path: '/projects?limit=100&offset=0' },
    { key: 'monitors', path: `/projects/${project.id}/monitors?limit=100&offset=0` },
    { key: 'metrics', path: `/projects/${project.id}/metrics?period=24h` },
    { key: 'incidents', path: `/projects/${project.id}/incidents?state=all&period=30d&limit=20&offset=0` },
  ];
  for (const viewport of viewportPlan) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    const dimensions = await page.evaluate(() => ({ width: innerWidth, height: innerHeight, scroll_width: document.documentElement.scrollWidth }));
    report.viewports.push({ name: viewport.name, ...dimensions });
    require(dimensions.scroll_width <= dimensions.width, 'UI_HORIZONTAL_OVERFLOW');
    for (let round = 0; round < 33; round++) for (const route of routes) await timedRest(route, viewport.name, round < 3, round < 3 ? round + 1 : round - 2);
    await checkpoint();
    for (let warmup = 0; warmup < 2; warmup++) await timedUpdate(viewport.name, true);
    for (let sample = 0; sample < viewport.measuredUpdates; sample++) await timedUpdate(viewport.name, false);
  }
  await Promise.allSettled([...pendingObservers]);
  require(currentRevision === initialRevision + 29, 'FINAL_REVISION_OR_MUTATION_COUNT_DIVERGED');
  await validateProject();
  require(report.errors.length === 0 && report.network.unexpected_statuses.length === 0, 'UNEXPECTED_BROWSER_OR_HTTP_ERRORS');
  require(report.rest.filter(sample => !sample.warmup).length === 240 && report.updates.filter(sample => !sample.warmup && sample.success).length === 25, 'MEASURED_SAMPLE_COUNTS_DIVERGED');
  report.result = 'passed_measurement';
} catch (error) {
  report.result = 'failed';
  recordFailure(error.code ?? 'CAMPAIGN_SETUP_OR_BROWSER_FAILURE', 'campaign', error.status ?? null);
  if (registrationAttempted && !report.identities.owner_id) report.cleanup.unknown_commit_possible.push('registration_identity_unknown');
  if (loginAttempted && !sessionConfirmed) report.cleanup.unknown_commit_possible.push('login_session_identity_unknown');
  if (createAttempted && !report.identities.project_id) report.cleanup.unknown_commit_possible.push('project_identity_unknown');
} finally {
  try { await checkpoint(); } catch { recordFailure('REPORT_CHECKPOINT_FAILED', 'report'); }
  try { await cleanup(); } catch { recordFailure('CLEANUP_UNEXPECTED_FAILURE', 'cleanup'); }
  if (context) await context.close().catch(() => recordFailure('BROWSER_CONTEXT_CLOSE_FAILED', 'cleanup'));
  if (browser) await browser.close().catch(() => recordFailure('BROWSER_CLOSE_FAILED', 'cleanup'));
  summarize();
  if (report.result === 'passed_measurement') report.result = report.cleanup.disposition === 'confirmed_api_scope' && report.errors.length === 0 ? 'passed' : 'failed';
  report.finished_at = new Date().toISOString();
  await checkpoint();
}
console.log(JSON.stringify({ result: report.result, report: reportPath, measured_rest: report.summary.actual_counts.rest_measured, measured_updates: report.summary.actual_counts.updates_measured, cleanup_scope: report.cleanup.disposition, retained_synthetic_owner_and_archive: report.cleanup.retained_synthetic_owner_and_archive }));
if (report.result !== 'passed') process.exitCode = 1;
