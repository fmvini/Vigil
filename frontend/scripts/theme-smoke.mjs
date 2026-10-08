import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';

// UI fixtures only: this pass does not certify API, worker or cloud integration.
const baseURL = process.env.VIGIL_UI_URL ?? 'http://127.0.0.1:5173';
const output = process.env.VIGIL_THEME_OUTPUT ?? '.impeccable/review/theme';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'light' });
let authenticated = false;
const now = new Date().toISOString();
const project = { id: 'p1', name: 'Operações QA', description: 'Dados sintéticos para validar o tema.', public_slug: 'tema-qa', public_status_enabled: true, revision: 0, archived_at: null };
const monitors = ['online', 'degraded', 'offline', null].map((health, index) => ({
  id: `m${index}`, project_id: 'p1', name: ['API principal', 'Fila de eventos', 'Checkout', 'Novo serviço'][index], url: `https://example.com/${index}`,
  interval_seconds: 60, timeout_ms: 5000, expected_status: 200, failure_threshold: 3, retry_count: 1, latency_threshold_ms: 1000,
  is_public: true, paused_at: index === 3 ? now : null, archived_at: null, health_status: health,
  freshness: index === 3 ? 'paused' : 'fresh', last_checked_at: health ? now : null, last_http_status: health ? 200 : null, last_latency_ms: health ? 125 : null,
}));
const incident = { id: 'i1', monitor_id: 'm2', monitor_name: 'Checkout', started_at: now, detected_at: now, ended_at: null, end_reason: null };
const metrics = {
  from: now, to: now, computed_at: now, success_count: 9, failure_count: 1, sample_count: 10, latency_sample_count: 9,
  uptime_percent: 90, average_latency_ms: 125, p95_latency_ms: 240, excluded_count: 1, cancelled_count: 1, pending_count: 1, skipped_slots: 2,
  health_status: 'offline', data_complete: false, freshness_counts: { fresh: 3, paused: 1, no_data: 0, stale: 0 }, bucket_seconds: 3600,
  series: [{ bucket_start: now, sample_count: 10, success_count: 9, failure_count: 1, latency_sample_count: 9, uptime_percent: 90, average_latency_ms: 125, p95_latency_ms: 240 }],
};
await context.route('**/api/v1/**', async route => {
  const path = new URL(route.request().url()).pathname.replace('/api/v1', '');
  let body; let status = 200;
  if (path === '/auth/me') { body = authenticated ? { user: { id: 'u1', email: 'tema.qa@example.com' }, csrf_token: 'qa' } : { detail: 'Unauthorized' }; if (!authenticated) status = 401; }
  else if (path === '/events') return route.fulfill({ status: 204, body: '' });
  else if (path === '/projects') body = { items: [project], total: 1 };
  else if (path.endsWith('/monitors')) body = { items: monitors, total: monitors.length };
  else if (path.endsWith('/metrics')) body = metrics;
  else if (path.endsWith('/incidents')) body = { items: [incident], total: 1 };
  else if (path.endsWith('/jobs')) body = { items: [{ job_id: 'j1', monitor_id: 'm0', config_version: 1, status: 'exhausted', scheduled_at: now, finished_at: now, execution_count: 3, error_code: 'internal_error' }], total: 1, from: now, to: now, computed_at: now, retention_days: 30 };
  else if (path === '/public/status/tema-qa') body = { ...project, slug: 'tema-qa', computed_at: now, health_status: 'offline', data_complete: false, freshness_counts: metrics.freshness_counts, monitors };
  else if (path === '/runtime-config') body = { minimum_interval_seconds: 60, scheduled_checks_interval_seconds: null };
  else return route.fulfill({ status: 404, json: { detail: `QA fixture missing: ${path}` } });
  return route.fulfill({ status, json: body });
});
await context.addInitScript(() => {
  window.__firstContentTheme = null;
  new MutationObserver(() => {
    if (window.__firstContentTheme === null && document.querySelector('#root')?.childElementCount) {
      window.__firstContentTheme = document.documentElement.dataset.theme;
    }
  }).observe(document, { subtree: true, childList: true });
});
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const captures = [];
async function check(name, theme) {
  assert.equal(await page.locator('html').getAttribute('data-theme'), theme);
  assert.equal(await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme), theme);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name}: overflow`);
  const control = page.getByRole('combobox', { name: 'Tema', exact: true });
  assert.equal(await control.count(), 1);
  assert.ok((await control.boundingBox()).height >= 44, `${name}: theme target <44px`);
  await control.focus();
  await page.keyboard.press('Tab');
  await page.keyboard.press('Shift+Tab');
  assert.equal(await control.evaluate(el => getComputedStyle(el).outlineStyle), 'solid');
  await page.evaluate(() => document.activeElement.blur());
  await page.screenshot({ path: `${output}/${name}.png`, fullPage: true });
  captures.push({ name, theme, viewport: page.viewportSize(), overflow: false });
}
try {
  await page.goto(baseURL);
  await page.getByRole('heading', { name: 'Entre no Vigil' }).waitFor();
  assert.equal(await page.getByLabel('Tema', { exact: true }).inputValue(), 'system');
  assert.equal(await page.evaluate(() => window.__firstContentTheme), 'light');
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
  await page.getByLabel('Tema', { exact: true }).selectOption('light');
  await page.reload();
  await page.getByRole('heading', { name: 'Entre no Vigil' }).waitFor();
  assert.equal(await page.evaluate(() => window.__firstContentTheme), 'light');
  await page.getByLabel('Tema', { exact: true }).selectOption('dark');
  await page.reload();
  await page.getByRole('heading', { name: 'Entre no Vigil' }).waitFor();
  assert.equal(await page.evaluate(() => window.__firstContentTheme), 'dark');
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('Tema', { exact: true }).selectOption(theme);
      await check(`login-${width}-${theme}`, theme);
    }
  }
  authenticated = true;
  await page.goto(baseURL);
  await page.getByRole('heading', { name: 'Operações QA', exact: true }).waitFor();
  await page.locator('.metric-values').getByText('90%', { exact: true }).waitFor();
  await page.getByText(/Ver série temporal/).click();
  await page.getByText('Falhas do processamento do Vigil', { exact: true }).click();
  const jobStatus = page.locator('.processing-failures td[data-label="Situação"]');
  await jobStatus.waitFor();
  assert.equal(await jobStatus.evaluate(el => el.firstChild.textContent), 'Execuções esgotadas');
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('Tema', { exact: true }).selectOption(theme);
      await check(`dashboard-${width}-${theme}`, theme);
      await page.getByRole('button', { name: 'Novo monitor', exact: true }).click();
      await page.getByLabel('Nome do monitor', { exact: true }).waitFor();
      await check(`form-${width}-${theme}`, theme);
      await page.getByRole('button', { name: 'Cancelar', exact: true }).click();
    }
  }
  await page.goto(`${baseURL}/status/tema-qa`);
  await page.getByRole('heading', { name: 'Operações QA', exact: true }).waitFor();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('Tema', { exact: true }).selectOption(theme);
      await check(`public-${width}-${theme}`, theme);
    }
  }
  const other = await context.newPage();
  await other.goto(`${baseURL}/status/tema-qa`);
  await other.getByLabel('Tema', { exact: true }).selectOption('light');
  await page.waitForFunction(() => document.documentElement.dataset.theme === 'light');
  assert.equal(await page.getByLabel('Tema', { exact: true }).inputValue(), 'light');
  await other.close();
  await page.getByLabel('Tema', { exact: true }).selectOption('system');
  await page.emulateMedia({ colorScheme: 'light' });
  await page.waitForFunction(() => document.documentElement.dataset.theme === 'light');
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
  assert.deepEqual(errors, []);
  const report = { scope: 'synthetic API UI only', captures, firstContentTheme: 'persisted light and dark verified', systemChanges: true, crossTab: true, errors };
  await writeFile(`${output}/report.json`, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
} finally { await browser.close(); }
