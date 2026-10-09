import { chromium } from 'playwright';
import { acceptLegal } from './legal-consent.mjs';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';

// Dedicated local QA account; no network mocking or endpoint checks.
const baseURL = process.env.VIGIL_UI_URL ?? 'http://127.0.0.1:5173';
const email = `frontend.browser.${Date.now()}@example.com`;
const password = `Vigil-QA-${Date.now()}-browser`;
const output = '.impeccable/review';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
const errors = [];
const expectedSessionProbes = [];
const expectedRevokedReads = [];
const publicChecks = {};
let phase = 'workflow';
page.on('request', request => {
  if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/auth/logout') phase = 'logout';
});
page.on('pageerror', error => errors.push(error.message));
page.on('console', message => {
  if (message.type() !== 'error') return;
  if (message.location().url.endsWith('/api/v1/auth/me') && message.text().includes('401')) expectedSessionProbes.push(message.text());
  else errors.push({ message: message.text(), path: message.location().url ? new URL(message.location().url).pathname : '', phase });
});
const mutations = [];
page.on('response', response => {
  if (response.url().includes('/api/v1') && response.request().method() !== 'GET') mutations.push({ path: new URL(response.url()).pathname, method: response.request().method(), status: response.status() });
  const url = new URL(response.url());
  // Revocation may reach an already pending read before React unmounts it.
  // Match a real private GET 401 after the actual logout request, never all 401s.
  if (phase === 'logout' && url.origin === new URL(baseURL).origin && response.request().method() === 'GET' && response.status() === 401 && /^\/api\/v1\/(?:events$|projects(?:\/|$)|monitors(?:\/|$))/.test(url.pathname)) expectedRevokedReads.push(url.pathname);
});
async function noOverflow(label) {
  const dimensions = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  assert.ok(dimensions.scrollWidth <= dimensions.width, `${label}: horizontal overflow ${JSON.stringify(dimensions)}`);
  return dimensions;
}
async function capture(name) {
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: `${output}/${name}.png`, fullPage: true });
}
try {
  await page.goto(baseURL);
  await page.getByRole('button', { name: 'Criar uma conta', exact: true }).click();
  await page.getByLabel('E-mail', { exact: true }).fill(email);
  await page.getByLabel('Senha', { exact: true }).fill(password);
  await acceptLegal(page);
  await page.getByRole('button', { name: 'Criar conta', exact: true }).click();
  await page.getByText('Conta criada. Entre com seu e-mail e senha.').waitFor();
  assert.equal(await page.getByLabel('Senha', { exact: true }).inputValue(), '');
  await page.getByLabel('Senha', { exact: true }).fill(password);
  await acceptLegal(page);
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await page.getByRole('button', { name: 'Criar primeiro projeto' }).click();
  assert.equal(await page.getByLabel('Publicar página de status').isChecked(), false);
  await page.getByLabel('Nome do projeto').fill('Projeto smoke navegador');
  await page.getByLabel('Descrição', { exact: false }).fill('Dados reais de cadastro. Nenhuma medição executada.');
  await page.getByRole('button', { name: 'Salvar projeto' }).click();
  await page.getByRole('button', { name: 'Editar projeto' }).click();
  await page.getByLabel('Nome do projeto').fill('Projeto QA navegador');
  await page.getByLabel('Publicar página de status').check();
  await page.getByRole('button', { name: 'Salvar projeto' }).click();
  await page.getByRole('heading', { name: 'Projeto QA navegador', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Novo monitor' }).click();
  assert.equal(await page.getByLabel('Exibir na página pública').isChecked(), false);
  await page.getByLabel('Nome do monitor').fill('API de exemplo QA');
  await page.getByLabel('URL do endpoint').fill('https://example.com/health');
  await page.getByRole('button', { name: 'Salvar monitor' }).click();
  await page.getByRole('button', { name: 'Editar API de exemplo QA', exact: true }).click();
  await page.getByLabel('Nome do monitor').fill('API de exemplo editada');
  await page.getByLabel('Intervalo (segundos)').fill('120');
  await page.getByLabel('Exibir na página pública').check();
  await page.getByRole('button', { name: 'Salvar monitor' }).click();
  await page.getByText('API de exemplo editada', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Pausar API de exemplo editada', exact: true }).click();
  await page.getByRole('button', { name: 'Retomar API de exemplo editada', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Retomar API de exemplo editada', exact: true }).click();
  await page.getByRole('button', { name: 'Pausar API de exemplo editada', exact: true }).waitFor();
  await page.reload();
  await page.getByText('API de exemplo editada', { exact: true }).waitFor();
  await page.getByText('Ainda sem leitura', { exact: true }).waitFor();
  await page.getByText('Ainda não há ciclos avaliados neste período.', { exact: true }).waitFor();
  assert.equal(await page.getByText('Não avaliada', { exact: true }).count(), 1);
  const desktop = await noOverflow('desktop'); await capture('desktop');
  await page.getByRole('button', { name: 'Ver histórico de API de exemplo editada', exact: true }).click();
  await page.getByText('Nenhuma verificação registrada neste período.', { exact: true }).waitFor();
  await page.getByLabel('Período').first().selectOption('7d');
  await page.getByText('Ainda não há ciclos avaliados neste período.', { exact: true }).waitFor();
  await capture('monitor-detail-desktop');
  await page.getByRole('button', { name: 'Voltar aos monitores', exact: true }).click();
  const publicPath = await page.getByRole('link', { name: 'Abrir página pública', exact: true }).getAttribute('href');
  assert.ok(publicPath?.startsWith('/status/'));
  const anonymous = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const statusPage = await anonymous.newPage();
  const publicRequests = [];
  statusPage.on('request', request => publicRequests.push(request.url()));
  statusPage.on('pageerror', error => errors.push(error.message));
  await statusPage.goto(new URL(publicPath, baseURL).href);
  await statusPage.getByRole('heading', { name: 'Projeto QA navegador', exact: true }).waitFor();
  await statusPage.getByText('API de exemplo editada', { exact: true }).waitFor();
  assert.ok(!(await statusPage.locator('body').innerText()).includes('https://example.com'));
  assert.ok(!publicRequests.some(url => url.includes('/auth/') || url.includes('/events')));
  await statusPage.screenshot({ path: `${output}/public-desktop.png`, fullPage: true });
  await statusPage.setViewportSize({ width: 390, height: 844 });
  assert.ok(await statusPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await statusPage.screenshot({ path: `${output}/public-mobile.png`, fullPage: true });
  publicChecks.anonymous = true; publicChecks.noPrivateURL = true;
  // Removing the opt-in must remove anonymous access on the next snapshot.
  await page.getByRole('button', { name: 'Editar projeto' }).click();
  await page.getByLabel('Publicar página de status').uncheck();
  await page.getByRole('button', { name: 'Salvar projeto' }).click();
  await statusPage.reload();
  await statusPage.getByRole('heading', { name: 'Página não publicada', exact: true }).waitFor();
  publicChecks.disabledReturns404 = true;
  await anonymous.close();
  // Leave the demo public and resume private workflow.
  await page.getByRole('button', { name: 'Editar projeto' }).click();
  await page.getByLabel('Publicar página de status').check();
  await page.getByRole('button', { name: 'Salvar projeto' }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  const mobile = await noOverflow('mobile'); await capture('mobile');
  await page.getByRole('button', { name: 'Ver histórico de API de exemplo editada', exact: true }).click();
  await page.getByText('Nenhuma verificação registrada neste período.', { exact: true }).waitFor();
  await noOverflow('mobile history'); await capture('monitor-detail-mobile');
  await page.getByRole('button', { name: 'Voltar aos monitores', exact: true }).click();
  await page.getByRole('button', { name: 'Editar API de exemplo editada', exact: true }).click();
  await page.getByLabel('Nome do monitor').waitFor();
  await noOverflow('mobile editor'); await capture('mobile-editor');
  await page.getByRole('button', { name: 'Cancelar', exact: true }).click();
  await page.getByRole('button', { name: 'Arquivar API de exemplo editada', exact: true }).click();
  await page.getByRole('button', { name: 'Confirmar arquivamento' }).click();
  await page.getByText('Nenhum endpoint configurado', { exact: true }).waitFor();
  // Keep a real no_data monitor in the dedicated QA database for review.
  await page.getByRole('button', { name: 'Novo monitor' }).click();
  await page.getByLabel('Nome do monitor').fill('Endpoint QA sem dados');
  await page.getByLabel('URL do endpoint').fill('https://example.com/health');
  await page.getByLabel('Exibir na página pública').check();
  await page.getByRole('button', { name: 'Salvar monitor' }).click();
  await page.getByRole('button', { name: 'Sair da conta', exact: true }).click();
  await page.getByRole('heading', { name: 'Entre no Vigil' }).waitFor();
  await noOverflow('mobile login'); await capture('mobile-login');
  const remainingRevocations = [...expectedRevokedReads];
  const unexpectedErrors = errors.filter(error => {
    if (typeof error !== 'object' || error.phase !== 'logout' || !error.message.includes('401')) return true;
    const index = remainingRevocations.indexOf(error.path);
    if (index < 0) return true;
    remainingRevocations.splice(index, 1);
    return false;
  });
  assert.deepEqual(unexpectedErrors, [], 'Browser console or runtime errors');
  assert.ok(mutations.every(m => m.status >= 200 && m.status < 300), JSON.stringify(mutations));
  const report = { baseURL, desktop, mobile, errors: unexpectedErrors, expectedSessionProbes, expectedRevokedReads, publicChecks, mutations, screenshots: ['desktop', 'mobile', 'mobile-editor', 'mobile-login', 'monitor-detail-desktop', 'monitor-detail-mobile', 'public-desktop', 'public-mobile'].map(name => `${output}/${name}.png`), qaFixture: { email, password, publicPath }, result: 'passed' };
  await writeFile(`${output}/browser-smoke.json`, JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ result: report.result, desktop, mobile, errors: unexpectedErrors, expectedRevokedReads, mutations, screenshots: report.screenshots }, null, 2));
} finally { await browser.close(); }
