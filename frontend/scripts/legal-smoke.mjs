import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { acceptLegal, legalVersions } from './legal-consent.mjs';

// Local CLI bundle + synthetic responses. No real account, API or cloud access.
const baseURL = process.env.VIGIL_LEGAL_UI_URL ?? 'http://127.0.0.1:5175';
const output = process.env.VIGIL_LEGAL_OUTPUT ?? '.impeccable/review/legal-round1';
await mkdir(output, { recursive: true });
const key = 'vigil.cookie-preference';
const report = { scope: 'Synthetic browser QA of CLI bundle, not Vite build or backend integration', baseURL, captures: [], checks: [], errors: [], sources: {} };
const browser = await chromium.launch({ channel: 'msedge', headless: true });
async function fixture(context) {
  const posts = [], reads = [];
  await context.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname.replace('/api/v1', '');
    reads.push(path);
    if (request.method() === 'POST') {
      const body = request.postDataJSON(); posts.push({ path, body });
      assert.equal(body.terms_version, legalVersions.terms_version); assert.equal(body.privacy_version, legalVersions.privacy_version);
      return route.fulfill({ status: path === '/auth/register' ? 201 : 200, json: path === '/auth/register' ? { id: 'qa', email: body.email } : { user: { id: 'qa', email: body.email }, csrf_token: 'synthetic' } });
    }
    if (path === '/auth/me') return route.fulfill({ status: 401, json: { error: { code: 'unauthenticated', message: 'QA anonymous' } } });
    if (path === '/events') return route.fulfill({ status: 204, body: '' });
    if (path === '/runtime-config') return route.fulfill({ json: { minimum_interval_seconds: 900, scheduled_checks_interval_seconds: 900 } });
    if (path === '/projects') return route.fulfill({ json: { items: [], total: 0 } });
    return route.fulfill({ status: 404, json: { error: { code: 'not_found', message: 'QA fixture unavailable' } } });
  });
  return { posts, reads };
}
async function capture(page, name, theme) {
  await page.evaluate(() => scrollTo(0, 0)); await page.evaluate(() => document.fonts.ready);
  const dimensions = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, theme: document.documentElement.dataset.theme }));
  assert.ok(dimensions.scrollWidth <= dimensions.width, `${name}: overflow`); assert.equal(dimensions.theme, theme);
  await page.screenshot({ path: `${output}/${name}.png`, fullPage: true });
  report.captures.push({ name, path: `${output}/${name}.png`, viewport: page.viewportSize(), ...dimensions });
}
try {
  for (const width of [1440, 390]) for (const theme of ['light', 'dark']) {
    const context = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 900 }, colorScheme: theme });
    await context.addInitScript(theme => localStorage.setItem('vigil.theme', theme), theme);
    const { reads, posts } = await fixture(context); const page = await context.newPage();
    page.on('pageerror', error => report.errors.push(error.message));
    const prefix = `${width}-${theme}`;
    await page.goto(baseURL); await page.getByRole('heading', { name: 'Entre no Vigil' }).waitFor();
    const popup = page.getByRole('region', { name: 'Cookies e preferências' });
    assert.equal(await page.getByRole('dialog').count(), 0);
    const box = await popup.boundingBox(); assert.ok(box && box.y < page.viewportSize().height && box.y + box.height <= page.viewportSize().height + 1, `${prefix}: popup outside viewport`);
    assert.equal(await page.getByRole('checkbox', { name: /Privacidade/ }).isChecked(), false);
    assert.equal(await page.getByRole('checkbox', { name: /Termos de Uso/ }).isChecked(), false);
    await capture(page, `${prefix}-login-popup`, theme);
    await page.getByRole('button', { name: 'Continuar sem aceitar' }).click();
    assert.equal(await popup.count(), 0);
    await capture(page, `${prefix}-login`, theme);
    await page.getByLabel('E-mail', { exact: true }).fill('synthetic@example.com');
    await page.getByLabel('Senha', { exact: true }).fill('Synthetic-QA-123');
    await page.getByRole('button', { name: 'Entrar', exact: true }).click();
    assert.equal(posts.length, 0);
    await page.getByRole('checkbox', { name: /Privacidade/ }).check();
    await page.getByRole('button', { name: 'Entrar', exact: true }).click(); assert.equal(posts.length, 0);
    // Real new-tab navigation leaves password and checkbox state untouched.
    const [policyTab] = await Promise.all([context.waitForEvent('page'), page.getByRole('link', { name: 'Política de Privacidade', exact: true }).click()]);
    await policyTab.getByRole('heading', { name: 'Política de Privacidade', exact: true }).waitFor(); await policyTab.close();
    assert.equal(await page.getByLabel('Senha', { exact: true }).inputValue(), 'Synthetic-QA-123');
    assert.equal(await page.getByRole('checkbox', { name: /Privacidade/ }).isChecked(), true);
    await page.getByRole('button', { name: 'Criar uma conta', exact: true }).click();
    assert.equal(await page.getByRole('checkbox', { name: /Privacidade/ }).isChecked(), false);
    await page.getByLabel('Senha', { exact: true }).fill('Synthetic-QA-123'); await acceptLegal(page);
    await page.getByRole('button', { name: 'Criar conta', exact: true }).click();
    await page.getByText('Conta criada. Entre com seu e-mail e senha.').waitFor();
    assert.equal(await page.getByRole('checkbox', { name: /Privacidade/ }).isChecked(), false);
    assert.equal(await page.getByRole('checkbox', { name: /Termos de Uso/ }).isChecked(), false);
    assert.equal(await page.getByLabel('Senha', { exact: true }).inputValue(), '');
    const previousReads = reads.length;
    for (const policy of ['privacy', 'terms', 'cookies']) {
      await page.goto(`${baseURL}/${policy}`); await page.locator('.policy-content').waitFor();
      assert.equal(reads.length, previousReads); assert.equal(await page.getByRole('checkbox').count(), 0);
      assert.equal(await page.getByRole('navigation', { name: 'Informações legais' }).count(), 1);
      assert.equal(await page.getByText('O canal de contato ainda não foi informado.').count(), 1);
      await capture(page, `${prefix}-${policy}`, theme);
    }
    await page.evaluate(key => localStorage.removeItem(key), key);
    await page.reload(); await popup.waitFor(); await capture(page, `${prefix}-policy-popup`, theme);
    await page.getByRole('button', { name: 'Aceitar cookies' }).click();
    for (const [path, name] of [['/pagina-inexistente', '404'], ['/demo/desconhecida', 'demo-404']]) {
      const response = await page.goto(`${baseURL}${path}`); assert.equal(response.status(), 404);
      await page.getByRole('heading', { name: '404 · Página não encontrada' }).waitFor();
      assert.equal(reads.length, previousReads); await capture(page, `${prefix}-${name}`, theme);
    }
    await page.evaluate(key => localStorage.removeItem(key), key); await page.reload(); await popup.waitFor();
    await capture(page, `${prefix}-404-popup`, theme);
    await page.getByRole('button', { name: 'Continuar sem aceitar' }).click();
    await page.getByRole('button', { name: 'Preferências de cookies' }).click();
    assert.equal(await page.getByRole('heading', { name: 'Cookies e preferências' }).evaluate(el => el === document.activeElement), true);
    await page.getByRole('button', { name: 'Aceitar cookies' }).click();
    const saved = await page.evaluate(key => JSON.parse(localStorage.getItem(key)), key);
    assert.equal(saved.choice, 'accepted'); assert.equal(saved.version, legalVersions.terms_version); assert.equal(Date.parse(saved.expires_at) - Date.parse(saved.timestamp), 180 * 86400000);
    // Actual browser storage event from another tab.
    const other = await context.newPage(); await other.goto(`${baseURL}/privacy`); await other.locator('.policy-content').waitFor();
    await other.evaluate(key => localStorage.removeItem(key), key); await popup.waitFor();
    await other.getByRole('button', { name: 'Continuar sem aceitar' }).click(); await popup.waitFor({ state: 'hidden' });
    await other.close();
    await page.goto(`${baseURL}/demo`); await page.getByRole('heading', { name: 'Loja Horizonte', exact: true }).waitFor();
    assert.equal(reads.length, previousReads); assert.equal(await page.getByRole('navigation', { name: 'Informações legais' }).count(), 1);
    await capture(page, `${prefix}-demo`, theme);
    report.checks.push({ viewport: width, theme, auth: 'required both; exact versions; reset after registration and mode switch; new tab preserves form', cookies: 'both choices; reopen/focus; 180 days; real cross-tab storage', routing: 'public policies and both 404s zero API reads; demo isolated', http: 'synthetic local SPA server only' });
    await context.close();
  }
  const blocked = await browser.newContext(); await fixture(blocked);
  await blocked.addInitScript(() => { Object.defineProperty(window, 'localStorage', { get() { throw new Error('QA storage unavailable'); } }); });
  const page = await blocked.newPage(); await page.goto(`${baseURL}/privacy`);
  await page.getByRole('button', { name: 'Continuar sem aceitar' }).click();
  await page.getByRole('status').getByText(/Não foi possível salvar/).waitFor();
  assert.equal(await page.getByRole('region', { name: 'Cookies e preferências' }).count(), 0);
  report.checks.push({ storageUnavailable: 'choice retained in session state' }); await blocked.close();
  assert.deepEqual(report.errors, []); report.result = 'passed';
} catch (error) { report.result = 'failed'; report.failure = String(error.stack ?? error); process.exitCode = 1; }
finally {
  for (const path of ['src/App.tsx', 'src/Forms.tsx', 'src/DemoApp.tsx', 'src/Legal.tsx', 'src/cookiePreference.ts', 'src/legalContent.ts', 'src/styles.css']) report.sources[path] = createHash('sha256').update(await readFile(path)).digest('hex');
  await writeFile(`${output}/report.json`, JSON.stringify(report, null, 2));
  await browser.close(); console.log(JSON.stringify({ result: report.result, captures: report.captures.length, failure: report.failure, report: `${output}/report.json` }));
}
