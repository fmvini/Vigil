import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { ProcessingFailures } from '../ProcessingFailures';
import { api } from '../api';
import { json } from './fixtures';

const monitors = [{ id: '11111111-1111-4111-8111-111111111111', name: 'API de QA' }];
const job = { job_id: '22222222-2222-4222-8222-222222222222', monitor_id: monitors[0].id, config_version: 2, status: 'exhausted', scheduled_at: '2026-10-05T11:00:00Z', finished_at: '2026-10-05T11:05:00Z', execution_count: 3, error_code: 'internal_error' };
const envelope = (items = [job], total = items.length) => ({ items, total, from: '2026-10-04T12:00:00Z', to: '2026-10-05T12:00:00Z', computed_at: '2026-10-05T12:00:00Z', retention_days: 30 });
const props = { projectId: 'p1', monitors, revision: 0 };
async function expand() { await userEvent.setup().click(screen.getByText('Falhas do processamento do Vigil')); }
afterEach(() => { vi.unstubAllGlobals(); api.setCsrfToken(null); api.onUnauthorized = undefined; });

it('não consulta fechada e traduz somente allowlist ao expandir sem URL/UUID/rawcodes', async () => {
  const codes = ['internal_error', 'execution_crashed', 'pool_exhausted', 'blocked_destination', 'database_error', 'insufficient_budget', 'deadline_exceeded', 'execution_limit', null, 'PRIVATE_RAW_SENTINEL'];
  const fetch = vi.fn().mockResolvedValue(json(envelope(codes.map((error_code, index) => ({ ...job, job_id: `22222222-2222-4222-8222-${String(index).padStart(12, '0')}`, error_code: error_code as string, execution_count: index % 4 })))));
  vi.stubGlobal('fetch', fetch);
  const view = render(<ProcessingFailures {...props} />);
  view.rerender(<ProcessingFailures {...props} revision={9} />);
  expect(fetch).not.toHaveBeenCalled();
  await expand();
  await screen.findByRole('table', { name: 'Falhas operacionais do processamento do Vigil' });
  for (const text of ['Falha interna do processamento', 'Execução do processamento interrompida', 'Recursos de execução indisponíveis', 'Destino bloqueado pela política de acesso', 'Falha no acesso ao banco de dados', 'Tempo disponível insuficiente para executar', 'Prazo de processamento excedido', 'Limite de execuções de processamento atingido']) expect(screen.getByText(text)).toBeVisible();
  expect(screen.getAllByText('Não informado')).toHaveLength(2);
  expect(document.body).not.toHaveTextContent(/PRIVATE_RAW_SENTINEL|internal_error|execution_limit|11111111|22222222/);
  expect(screen.queryByText('Offline')).not.toBeInTheDocument();
  expect(screen.getByText(/A lista pode mudar entre páginas/)).toBeVisible();
  const [, init] = fetch.mock.calls[0];
  expect(init.method).toBe('GET'); expect(init.credentials).toBe('same-origin');
});

it('consulta filtros e paginação GET20, reseta offset ao mudar seleção', async () => {
  const fetch = vi.fn().mockImplementation(async () => json(envelope([job], 41)));
  vi.stubGlobal('fetch', fetch); render(<ProcessingFailures {...props} />); await expand();
  await screen.findByText('1–20 de 41');
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Próxima' }));
  await screen.findByText('21–40 de 41');
  await user.selectOptions(screen.getByLabelText('Situação'), 'expired');
  await screen.findByText('1–20 de 41');
  await user.selectOptions(screen.getByLabelText('Período do agendamento'), '7d');
  await waitFor(() => expect(fetch.mock.calls.at(-1)?.[0]).toContain('period=7d'));
  await user.selectOptions(screen.getByLabelText('Monitor'), monitors[0].id);
  await waitFor(() => expect(fetch.mock.calls.at(-1)?.[0]).toContain(`monitor_id=${monitors[0].id}`));
  for (const [url, init] of fetch.mock.calls) {
    expect(String(url)).toContain('/projects/p1/jobs?'); expect(init.method).toBe('GET');
    expect(new URL(String(url), 'http://local').searchParams.get('limit')).toBe('20');
  }
  expect(String(fetch.mock.calls.at(-1)?.[0])).toContain('status=expired');
  expect(String(fetch.mock.calls.at(-1)?.[0])).toContain('offset=0');
});

it('erro mostra mensagem estática, Recarregar lista sóGET e vazio não afirma cobertura', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(json({ error: { code: 'private_code', message: 'PRIVATE_SERVER_SENTINEL', details: ['PRIVATE_DETAIL'] } }, 503)).mockResolvedValueOnce(json(envelope([], 0)));
  vi.stubGlobal('fetch', fetch); render(<ProcessingFailures {...props} />); await expand();
  expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível consultar os registros do processamento. Tente recarregar a lista.');
  expect(document.body).not.toHaveTextContent(/PRIVATE_SERVER_SENTINEL|PRIVATE_DETAIL|private_code|Offline/);
  await userEvent.setup().click(screen.getByRole('button', { name: 'Recarregar lista' }));
  expect(await screen.findByText(/Uma lista vazia não comprova cobertura/)).toBeVisible();
  expect(screen.getByText(/A retenção prevista é de 30 dias/)).toBeVisible();
  expect(fetch).toHaveBeenCalledTimes(2);
  for (const [, init] of fetch.mock.calls) expect(init.method).toBe('GET');
});

it('agrupa revisões enquanto uma consulta está pendente e para consultas ao fechar', async () => {
  let finish: (response: Response) => void = () => {};
  const fetch = vi.fn().mockImplementationOnce(() => new Promise<Response>(resolve => { finish = resolve; })).mockImplementation(async () => json(envelope([], 0)));
  vi.stubGlobal('fetch', fetch);
  const view = render(<ProcessingFailures {...props} />); await expand();
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  for (const revision of [1, 2, 3, 10]) view.rerender(<ProcessingFailures {...props} revision={revision} />);
  expect(fetch).toHaveBeenCalledTimes(1);
  await act(async () => { finish(json(envelope())); });
  await screen.findByText(/Uma lista vazia não comprova cobertura/);
  expect(fetch).toHaveBeenCalledTimes(2);
  await expand();
  await waitFor(() => expect(screen.queryByLabelText('Período do agendamento')).not.toBeInTheDocument());
  view.rerender(<ProcessingFailures {...props} revision={11} />);
  expect(fetch).toHaveBeenCalledTimes(2);
});

it('fechar aborta consulta e ignora401 tardio sem callback de sessão', async () => {
  let finish: (response: Response) => void = () => {};
  const fetch = vi.fn((_: unknown, __?: RequestInit) => new Promise<Response>(resolve => { finish = resolve; }));
  vi.stubGlobal('fetch', fetch); const expired = vi.fn(); api.onUnauthorized = expired;
  render(<ProcessingFailures {...props} />); await expand();
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  const signal = fetch.mock.calls[0][1]?.signal;
  await expand(); await waitFor(() => expect(signal?.aborted).toBe(true));
  await act(async () => { finish(json({ error: { code: 'unauthenticated', message: 'PRIVATE_OLD_SESSION' } }, 401)); });
  expect(expired).not.toHaveBeenCalled(); expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('trocar projeto aborta consulta antiga e reinicia filtros, sem dados ou401 antigos', async () => {
  let finish: (response: Response) => void = () => {};
  const fetch = vi.fn().mockResolvedValueOnce(json(envelope())).mockImplementationOnce(() => new Promise<Response>(resolve => { finish = resolve; })).mockResolvedValue(json(envelope([], 0)));
  vi.stubGlobal('fetch', fetch); const expired = vi.fn(); api.onUnauthorized = expired;
  const view = render(<ProcessingFailures {...props} />); await expand();
  await screen.findByText('1–1 de 1');
  await userEvent.setup().selectOptions(screen.getByLabelText('Situação'), 'expired');
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  const oldSignal = fetch.mock.calls[1][1].signal;
  view.rerender(<ProcessingFailures {...props} projectId="p2" />);
  expect(await screen.findByText(/Uma lista vazia não comprova cobertura/)).toBeVisible();
  expect(screen.getByLabelText('Situação')).toHaveValue('all');
  expect(oldSignal.aborted).toBe(true);
  expect(String(fetch.mock.calls.at(-1)?.[0])).toContain('/projects/p2/jobs?');
  await act(async () => { finish(json({}, 401)); });
  expect(expired).not.toHaveBeenCalled();
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

it('monitor removido volta a Todos e aborta resposta antiga sem callback401 ou404 persistente', async () => {
  let finish: (response: Response) => void = () => {};
  const fetch = vi.fn().mockResolvedValueOnce(json(envelope())).mockImplementationOnce(() => new Promise<Response>(resolve => { finish = resolve; })).mockResolvedValue(json(envelope([], 0)));
  vi.stubGlobal('fetch', fetch); const expired = vi.fn(); api.onUnauthorized = expired;
  const view = render(<ProcessingFailures {...props} />); await expand();
  await screen.findByText('1–1 de 1');
  await userEvent.setup().selectOptions(screen.getByLabelText('Monitor'), monitors[0].id);
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  const oldSignal = fetch.mock.calls[1][1].signal;
  view.rerender(<ProcessingFailures {...props} monitors={[]} />);
  await screen.findByText(/Uma lista vazia não comprova cobertura/);
  expect(screen.getByLabelText('Monitor')).toHaveValue('');
  const query = new URL(String(fetch.mock.calls.at(-1)?.[0]), 'http://local').searchParams;
  expect(query.has('monitor_id')).toBe(false); expect(query.get('offset')).toBe('0');
  expect(oldSignal.aborted).toBe(true);
  await act(async () => { finish(json({}, 401)); });
  expect(expired).not.toHaveBeenCalled(); expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('consulta aberta aguarda edição e continua com a revisão atual ao liberar', async () => {
  const fetch = vi.fn().mockImplementation(async () => json(envelope([], 0)));
  vi.stubGlobal('fetch', fetch);
  const view = render(<ProcessingFailures {...props} blocked />); await expand();
  expect(await screen.findByText('A consulta aguarda a ação em andamento.')).toBeVisible();
  view.rerender(<ProcessingFailures {...props} blocked revision={9} />);
  expect(fetch).not.toHaveBeenCalled();
  view.rerender(<ProcessingFailures {...props} revision={9} />);
  await screen.findByText(/Uma lista vazia não comprova cobertura/);
  expect(fetch).toHaveBeenCalledTimes(1);
});
