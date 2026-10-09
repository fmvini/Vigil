import { chromium } from 'playwright';
import { acceptLegal } from './legal-consent.mjs';
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';

// Persisted synthetic QA rows, served by real REST routes. No seed writes or network mocks.
const baseURL = process.env.VIGIL_UI_URL ?? 'http://127.0.0.1:5173';
const fixturePath = process.env.VIGIL_OBSERVATIONS_FIXTURE ?? '.impeccable/review/observations-fixture.json';
const output = '.impeccable/review';
const fixture = JSON.parse(await readFile(fixturePath, 'utf8'));
assert.equal(fixture.fixture_version, 1, 'Unsupported QA fixture version');
assert.equal(fixture.fixture_kind, 'synthetic_persisted_qa');
assert.equal(fixture.external_checks_executed, false, 'This smoke must never represent external checks');
assert.ok(Date.now() < Date.parse(fixture.seed_timestamp) + 45 * 60_000,
  'QA fixture is older than 45 minutes; reseed using a new private manifest path');
const monitors = Array.isArray(fixture.monitors) ? fixture.monitors : Object.values(fixture.monitors);
const target = monitors.find(m => m.role === 'target') ?? monitors.find(m => m.checks_total > 20 && m.incidents_total > 20);
assert.ok(target, 'Fixture needs a monitor with paginated checks and incidents');
const project = fixture.project;
const login = fixture.login;
assert.ok(login?.email && login?.password && project?.id && project?.public_slug);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const report = {
  result: 'running', fixture_kind: fixture.fixture_kind, external_checks_executed: false,
  generated_at: fixture.seed_timestamp, baseURL, project_id: project.id,
  viewports: [], screenshots: [], errors: [], expectedSessionProbes: [], network: [], metrics: {},
};
const healthLabels = { online: 'Online', degraded: 'Degradado', offline: 'Offline' };
const freshnessLabels = { fresh: 'Atualizados', stale: 'Desatualizados', paused: 'Pausado', no_data: 'Sem dados' };
const endReasons = { recovered: 'Recuperado', configuration_changed: 'Configuração alterada', archived: 'Arquivado' };
const metricKeys = ['sample_count', 'success_count', 'failure_count', 'latency_sample_count', 'uptime_percent', 'average_latency_ms', 'p95_latency_ms', 'excluded_count', 'cancelled_count', 'pending_count', 'skipped_slots'];
const formatMetric = (value, unit = '') => value == null ? 'Sem dados' : `${value.toLocaleString('pt-BR', { maximumFractionDigits: unit === '%' ? 2 : 1 })}${unit === '%' ? '%' : unit ? ` ${unit}` : ''}`;
const range = (offset, total) => total === 0 ? '0 registros' : `${offset + 1}–${Math.min(offset + 20, total)} de ${total}`;
function compareMetrics(actual, expected, label) {
  assert.ok(expected, `Missing independently seeded metric expectations: ${label}`);
  for (const key of metricKeys) {
    if (!(key in expected)) continue;
    if (typeof expected[key] === 'number') assert.ok(Math.abs(actual[key] - expected[key]) < 0.000001, `${label}.${key}: ${actual[key]} != ${expected[key]}`);
    else assert.equal(actual[key], expected[key], `${label}.${key}`);
  }
  assert.equal(actual.series.reduce((sum, bucket) => sum + bucket.sample_count, 0), actual.sample_count, `${label}: bucket sample count`);
  assert.equal(actual.success_count + actual.failure_count, actual.sample_count);
  assert.ok(actual.sample_count > 0, `${label}: fixture must have evaluated cycles`);
  assert.equal(actual.series.length, expected.series.length, `${label}: bucket count`);
  for (let index = 0; index < expected.series.length; index++) {
    const bucket = actual.series[index], seeded = expected.series[index];
    assert.equal(bucket.bucket_start, seeded.bucket_start, `${label}: UTC bucket boundary`);
    for (const key of metricKeys.filter(key => key in seeded)) {
      if (typeof seeded[key] === 'number') assert.ok(Math.abs(bucket[key] - seeded[key]) < 0.000001, `${label}: bucket ${index}.${key}`);
      else assert.equal(bucket[key], seeded[key], `${label}: bucket ${index}.${key}`);
    }
  }
}
function track(page, viewport, anonymous = false) {
  page.on('pageerror', error => report.errors.push({ viewport, message: error.message }));
  page.on('console', message => {
    if (message.type() !== 'error') return;
    if (!anonymous && message.location().url.endsWith('/api/v1/auth/me') && message.text().includes('401')) report.expectedSessionProbes.push(viewport);
    else report.errors.push({ viewport, message: message.text() });
  });
  page.on('response', response => {
    const url = new URL(response.url());
    if (url.pathname.startsWith('/api/v1/')) report.network.push({ viewport, anonymous, method: response.request().method(), path: url.pathname + url.search, status: response.status() });
  });
  page.on('request', request => {
    const url = new URL(request.url());
    assert.equal(url.origin, new URL(baseURL).origin, 'No browser request may target a monitored/external URL');
    if (anonymous) assert.ok(!url.pathname.includes('/auth/') && !url.pathname.endsWith('/events'), 'Public page must not authenticate or open private SSE');
  });
}
async function read(context, path) {
  const response = await context.request.get(`${baseURL}/api/v1${path}`);
  assert.equal(response.status(), 200, `Real REST ${path}`);
  return response.json();
}
async function all(context, path) {
  const items = []; let total = Infinity;
  while (items.length < total) {
    const data = await read(context, `${path}${path.includes('?') ? '&' : '?'}limit=100&offset=${items.length}`);
    items.push(...data.items); total = data.total;
    assert.ok(data.items.length > 0 || total === 0, 'Incomplete page of persisted fixture');
  }
  return { items, total };
}
async function capture(page, locator, name) {
  const path = `${output}/${name}.png`;
  if (locator) await locator.screenshot({ path });
  else { await page.evaluate(() => scrollTo(0, 0)); await page.screenshot({ path }); }
  report.screenshots.push(path);
}
async function noOverflow(page, label) {
  const dimensions = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  assert.ok(dimensions.scrollWidth <= dimensions.width, `${label}: horizontal overflow ${JSON.stringify(dimensions)}`);
  report.viewports.push({ label, ...dimensions });
}
async function metricsUI(panel, data) {
  const values = { 'Uptime por amostras': formatMetric(data.uptime_percent, '%'), 'Latência média': formatMetric(data.average_latency_ms, 'ms'), 'Latência p95': formatMetric(data.p95_latency_ms, 'ms') };
  for (const value of Object.values(values)) await panel.locator('.metric-values dd').getByText(value, { exact: true }).first().waitFor();
  assert.deepEqual(await panel.locator('.metric-values').evaluate(dl => Object.fromEntries([...dl.children].map(node => [node.querySelector('dt').textContent, node.querySelector('dd').textContent]))), values);
  await panel.getByText(`${data.sample_count} ciclos avaliados`, { exact: true }).waitFor();
  const counters = { Sucessos: data.success_count, Falhas: data.failure_count, Excluídos: data.excluded_count, Cancelados: data.cancelled_count, Pendentes: data.pending_count, 'Slots omitidos': data.skipped_slots };
  assert.deepEqual(await panel.locator('.job-counts').evaluate(dl => Object.fromEntries([...dl.children].map(node => [node.querySelector('dt').textContent, Number(node.querySelector('dd').textContent)]))), counters);
}
async function seriesUI(panel, data) {
  const summary = panel.getByText(/Ver série temporal/);
  if (!await panel.locator('details').evaluate(details => details.open)) await summary.click();
  const rows = panel.locator('tbody tr');
  assert.equal(await rows.count(), data.series.length);
  for (let index = 0; index < data.series.length; index++) {
    const bucket = data.series[index]; const row = rows.nth(index);
    await row.getByText(formatMetric(bucket.uptime_percent, '%'), { exact: true }).waitFor();
    const cells = await row.locator('td').allTextContents();
    assert.equal(cells[0], new Date(bucket.bucket_start).toLocaleString('pt-BR', {
      timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }));
    assert.equal(cells[1], `${bucket.sample_count}${bucket.success_count} sucessos · ${bucket.failure_count} falhas`);
    assert.equal(cells[2], formatMetric(bucket.uptime_percent, '%'));
    assert.equal(cells[3], formatMetric(bucket.average_latency_ms, 'ms'));
    assert.equal(cells[4], formatMetric(bucket.p95_latency_ms, 'ms'));
  }
  await panel.getByText(/Intervalos ausentes são lacunas/).waitFor();
}
async function change(page, pathname, predicate, action) {
  const response = page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.pathname === `/api/v1${pathname}` && response.status() === 200 && predicate(url.searchParams);
  });
  const [matched] = await Promise.all([response, action()]);
  return matched.json();
}
async function incidentsUI(page, section, pathname, query, reference, prefix) {
  await section.getByText(range(0, reference.total), { exact: true }).waitFor();
  assert.equal(await section.locator('tbody tr').count(), Math.min(20, reference.total));
  if (reference.total > 20) {
    const next = await change(page, pathname, q => q.get('offset') === '20' && query(q), () => section.getByRole('button', { name: 'Próxima' }).click());
    await section.getByText(range(20, next.total), { exact: true }).waitFor();
    assert.equal(await section.locator('tbody tr').count(), next.items.length);
  }
  for (const state of ['open', 'closed']) {
    const filtered = await change(page, pathname, q => q.get('state') === state && q.get('offset') === '0' && query(q), () => section.getByLabel('Situação').selectOption(state));
    const expected = reference.items.filter(item => state === 'open' ? item.ended_at === null : item.ended_at !== null);
    assert.equal(filtered.total, expected.length);
    await section.getByText(range(0, filtered.total), { exact: true }).waitFor();
    if (state === 'open' && expected.length) await section.getByText('Em aberto', { exact: true }).first().waitFor();
    if (state === 'closed') {
      for (const ending of new Set(filtered.items.map(item => item.end_reason))) {
        if (endReasons[ending]) await section.getByText(endReasons[ending], { exact: true }).first().waitFor();
      }
    }
  }
  await noOverflow(page, `${prefix}-incidents`);
  await capture(page, section, `${prefix}-incidents-closed`);
}
try {
  for (const [name, viewport] of [['desktop', { width: 1440, height: 900 }], ['mobile', { width: 390, height: 844 }]]) {
    const context = await browser.newContext({ viewport, timezoneId: 'America/Sao_Paulo' });
    const page = await context.newPage(); track(page, name);
    await page.goto(baseURL);
    await page.getByLabel('E-mail', { exact: true }).fill(login.email);
    await page.getByLabel('Senha', { exact: true }).fill(login.password);
    await acceptLegal(page);
    await page.getByRole('button', { name: 'Entrar', exact: true }).click();
    await page.getByRole('heading', { name: project.name, exact: true }).waitFor();
    const snapshots = { project: {}, target: {}, checks: {} };
    for (const period of ['24h', '7d', '30d']) {
      snapshots.project[period] = await read(context, `/projects/${project.id}/metrics?period=${period}`);
      snapshots.target[period] = await read(context, `/monitors/${target.id}/metrics?period=${period}`);
      compareMetrics(snapshots.target[period], fixture.expected.per_monitor[target.id][period], `target.${period}`);
      const seededProject = fixture.expected.project?.[period] ?? fixture.expected.project_metrics?.[period];
      if (seededProject) compareMetrics(snapshots.project[period], seededProject, `project.${period}`);
      else {
        const expectedCount = monitors.reduce((sum, monitor) => sum + fixture.expected.per_monitor[monitor.id][period].sample_count, 0);
        assert.equal(snapshots.project[period].sample_count, expectedCount);
      }
      snapshots.checks[period] = await all(context, `/monitors/${target.id}/checks?period=${period}`);
      assert.equal(snapshots.checks[period].total, fixture.expected.per_monitor[target.id][period].sample_count);
    }
    assert.ok(snapshots.checks['24h'].total > 20, '24h checks must exercise pagination');
    assert.ok(snapshots.checks['7d'].total > snapshots.checks['24h'].total, 'Older samples must distinguish periods');
    report.metrics[name] = { project: snapshots.project, target: snapshots.target };
    const projectIncidents = await all(context, `/projects/${project.id}/incidents?state=all&period=30d`);
    assert.equal(projectIncidents.total, monitors.reduce((sum, monitor) => sum + monitor.incidents_total, 0));
    const metricPanel = page.getByRole('region', { name: 'Métricas de disponibilidade' });
    await metricsUI(metricPanel, snapshots.project['24h']);
    for (const monitor of monitors) {
      const row = page.getByRole('row').filter({ has: page.getByRole('button', { name: `Ver histórico de ${monitor.name}`, exact: true }) });
      await row.locator('.badge').getByText(freshnessLabels[monitor.freshness], { exact: true }).waitFor();
      if (monitor.health_status) await row.locator('.health').getByText(healthLabels[monitor.health_status], { exact: true }).waitFor();
      if (monitor.freshness !== 'fresh' && monitor.health_status) await row.getByText('Leitura histórica', { exact: true }).waitFor();
    }
    await noOverflow(page, `${name}-dashboard`); await capture(page, null, `observations-${name}-dashboard`);
    await seriesUI(metricPanel, snapshots.project['24h']);
    await noOverflow(page, `${name}-series`); await capture(page, metricPanel, `observations-${name}-metrics-series`);
    const incidents = page.getByRole('region', { name: 'Incidentes', exact: true });
    await incidentsUI(page, incidents, `/projects/${project.id}/incidents`, q => !q.has('monitor_id'), projectIncidents, `observations-${name}-project`);
    await page.getByRole('button', { name: `Ver histórico de ${target.name}`, exact: true }).click();
    await page.getByRole('heading', { name: target.name, exact: true }).waitFor();
    const history = page.getByRole('region', { name: 'Histórico de verificações' });
    await history.getByText(range(0, snapshots.checks['24h'].total), { exact: true }).waitFor();
    const checks = history.locator('.check-entry'); assert.equal(await checks.count(), 20);
    const firstPage = snapshots.checks['24h'].items.slice(0, 20);
    for (let index = 0; index < firstPage.length; index++) {
      const check = firstPage[index]; const entry = checks.nth(index);
      await entry.locator('.check-heading').getByText(check.outcome === 'success' ? 'Sucesso' : 'Falha', { exact: true }).waitFor();
      const displayed = await entry.locator('.check-values').evaluate(dl => Object.fromEntries([...dl.children].map(node => [node.querySelector('dt').textContent, node.querySelector('dd').textContent])));
      assert.equal(displayed.Resposta, check.http_status === null ? 'Sem resposta HTTP' : `HTTP ${check.http_status}`);
      assert.equal(displayed.Latência, formatMetric(check.latency_ms, 'ms'));
      assert.equal(displayed['Saúde após ciclo'], healthLabels[check.health_after]);
      assert.equal(displayed.Tentativas, String(check.attempt_count));
    }
    const retryIndex = firstPage.findIndex(check => check.degradation_reason === 'retry_recovered' && check.attempts.length > 1);
    assert.ok(retryIndex >= 0, 'Seed must place a recovered retry on the first checks page');
    const retry = checks.nth(retryIndex); await retry.getByText('Detalhes do ciclo', { exact: true }).click();
    await retry.getByText(/Recuperado após retry/).waitFor();
    assert.equal(await retry.getByRole('listitem').count(), firstPage[retryIndex].attempts.length);
    for (const attempt of firstPage[retryIndex].attempts) await retry.getByText(new RegExp(`duração ${formatMetric(attempt.duration_ms, 'ms').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`)).first().waitFor();
    await metricsUI(page.getByRole('region', { name: 'Métricas de disponibilidade' }), snapshots.target['24h']);
    await noOverflow(page, `${name}-history`); await capture(page, retry, `observations-${name}-retry`);
    await change(page, `/monitors/${target.id}/checks`, q => q.get('offset') === '20', () => history.getByRole('button', { name: 'Próxima' }).click());
    await history.getByText(range(20, snapshots.checks['24h'].total), { exact: true }).waitFor();
    assert.equal(await checks.count(), Math.min(20, snapshots.checks['24h'].total - 20));
    await change(page, `/monitors/${target.id}/checks`, q => q.get('period') === '7d' && q.get('offset') === '0', () => history.getByLabel('Período').selectOption('7d'));
    await history.getByText(range(0, snapshots.checks['7d'].total), { exact: true }).waitFor();
    const detailMetrics = page.getByRole('region', { name: 'Métricas de disponibilidade' });
    for (const period of ['7d', '30d']) {
      await change(page, `/monitors/${target.id}/metrics`, q => q.get('period') === period, () => detailMetrics.getByLabel('Período').selectOption(period));
      await metricsUI(detailMetrics, snapshots.target[period]);
    }
    const targetIncidents = { items: projectIncidents.items.filter(item => item.monitor_id === target.id), total: target.incidents_total };
    await incidentsUI(page, page.getByRole('region', { name: 'Incidentes', exact: true }), `/projects/${project.id}/incidents`, q => q.get('monitor_id') === target.id, targetIncidents, `observations-${name}-target`);
    await context.close();
    const anonymous = await browser.newContext({ viewport, timezoneId: 'America/Sao_Paulo' });
    const publicPage = await anonymous.newPage(); track(publicPage, name, true);
    const published = await read(anonymous, `/public/status/${encodeURIComponent(project.public_slug)}`);
    const publicMonitors = monitors.filter(monitor => monitor.is_public);
    assert.deepEqual(published.monitors.map(monitor => monitor.id).sort(), publicMonitors.map(monitor => monitor.id).sort());
    for (const monitor of published.monitors) assert.deepEqual(Object.keys(monitor).sort(), ['id', 'name', 'health_status', 'freshness', 'last_checked_at'].sort());
    const publicIncidents = await all(anonymous, `/public/status/${encodeURIComponent(project.public_slug)}/incidents?state=all&period=30d`);
    assert.equal(publicIncidents.total, publicMonitors.reduce((sum, monitor) => sum + monitor.incidents_total, 0));
    await publicPage.goto(`${baseURL}/status/${encodeURIComponent(project.public_slug)}`);
    await publicPage.getByRole('heading', { name: project.name, exact: true }).waitFor();
    await publicPage.getByRole('region', { name: 'Saúde publicada' }).getByText(healthLabels[published.health_status], { exact: true }).waitFor();
    for (const monitor of publicMonitors) {
      const row = publicPage.locator('.public-monitors li').filter({ hasText: monitor.name });
      await row.getByText(freshnessLabels[monitor.freshness], { exact: true }).waitFor();
      if (monitor.health_status) await row.getByText(`${healthLabels[monitor.health_status]}${monitor.freshness === 'fresh' ? '' : ' (histórica)'}`, { exact: true }).waitFor();
    }
    const publicText = await publicPage.locator('body').innerText();
    for (const monitor of monitors.filter(monitor => !monitor.is_public)) assert.ok(!publicText.includes(monitor.name), 'Private sentinel leaked publicly');
    assert.ok(!publicText.includes('.invalid') && !publicText.includes(login.email), 'Private URLs/account leaked publicly');
    assert.deepEqual(await anonymous.cookies(baseURL), [], 'Public smoke must remain anonymous');
    await noOverflow(publicPage, `${name}-public`); await capture(publicPage, null, `observations-${name}-public`);
    await incidentsUI(publicPage, publicPage.getByRole('region', { name: 'Incidentes', exact: true }), `/public/status/${encodeURIComponent(project.public_slug)}/incidents`, () => true, publicIncidents, `observations-${name}-public`);
    await anonymous.close();
    console.log(`${name}: persisted synthetic metrics, buckets, checks/retries, pagination and private/public incidents passed.`);
  }
  assert.deepEqual(report.errors, []);
  assert.ok(report.network.every(request => request.status === 200 || (request.path === '/api/v1/auth/me' && request.status === 401)), 'Unexpected HTTP response in browser');
  report.result = 'passed';
} catch (error) {
  report.result = 'failed'; report.failure = error.message;
  for (const context of browser.contexts()) for (const page of context.pages()) await page.screenshot({ path: `${output}/observations-failure-${report.screenshots.length}.png` }).catch(() => {});
  throw error;
} finally {
  await writeFile(`${output}/observations-smoke.json`, JSON.stringify(report, null, 2));
  await browser.close();
}
console.log(JSON.stringify({ result: report.result, fixture_kind: report.fixture_kind, external_checks_executed: false, viewports: report.viewports, errors: report.errors, screenshots: report.screenshots }, null, 2));
