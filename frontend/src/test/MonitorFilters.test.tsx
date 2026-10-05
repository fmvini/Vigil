import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import App from '../App';
import { api } from '../api';
import type { Monitor } from '../types';
import { json, monitor, project, observationResponse } from './fixtures';

const now = Date.UTC(2026, 9, 5, 12);
const session = { user: { id: 'u1', email: 'tester@example.com' }, csrf_token: 'csrf-test' };
const data: Monitor[] = [
  { ...monitor, id: 'fresh', name: 'API recente offline', freshness: 'fresh', health_status: 'offline', last_checked_at: new Date(now - 10000).toISOString() },
  { ...monitor, id: 'stale', name: 'API antiga online', freshness: 'stale', health_status: 'online', last_checked_at: new Date(now - 300000).toISOString() },
  { ...monitor, id: 'aged', name: 'API envelhecida', freshness: 'fresh', health_status: 'online', last_checked_at: new Date(now - 300000).toISOString() },
  { ...monitor, id: 'empty', name: 'Worker sem leitura', url: 'https://worker.example.com/health' },
  { ...monitor, id: 'paused', name: 'API suspensa', freshness: 'fresh', health_status: 'online', paused_at: new Date(now).toISOString(), last_checked_at: new Date(now - 10000).toISOString() },
];
function path(input: unknown) { return String(input).replace('/api/v1', '').split('?')[0]; }
function setup(monitors = data, secondProject = false) {
  vi.stubGlobal('EventSource', undefined);
  vi.spyOn(Date, 'now').mockReturnValue(now);
  const fetch = vi.fn(async (url: unknown) => {
    const observation = observationResponse(url); if (observation) return observation;
    if (path(url) === '/auth/me') return json(session);
    if (path(url) === '/projects') return json({ items: secondProject ? [project, { ...project, id: 'p2', name: 'Projeto B' }] : [project], total: secondProject ? 2 : 1 });
    if (path(url) === '/projects/p2/monitors') return json({ items: [{ ...monitor, id: 'other', project_id: 'p2', name: 'Endpoint do B' }], total: 1 });
    return json({ items: monitors, total: monitors.length });
  });
  vi.stubGlobal('fetch', fetch);
  render(<App />);
  return fetch;
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); api.setCsrfToken(null); });

it('filtra as cinco qualidades atuais sem usar última saúde nem freshness DTO envelhecido', async () => {
  setup();
  const user = userEvent.setup();
  expect(await screen.findByText('5 de 5 monitores')).toBeVisible();
  const select = screen.getByLabelText('Qualidade dos dados');
  for (const [value, names] of [
    ['fresh', ['API recente offline']], ['stale', ['API antiga online', 'API envelhecida']],
    ['no_data', ['Worker sem leitura']], ['paused', ['API suspensa']], ['all', data.map(item => item.name)],
  ] as const) {
    await user.selectOptions(select, value);
    const table = screen.getByRole('table', { name: 'Monitores do projeto Aplicação' });
    expect(within(table).getAllByRole('row')).toHaveLength(names.length + 1);
    for (const name of names) expect(within(table).getByRole('button', { name: `Ver histórico de ${name}` })).toBeVisible();
    expect(screen.getByText(`${names.length} de 5 monitores`)).toBeVisible();
  }
  expect(screen.queryByRole('button', { name: 'Limpar filtros' })).not.toBeInTheDocument();
});

it('combina busca nome/URL com qualidade e limpa ambos pelo teclado devolvendo foco', async () => {
  setup();
  const user = userEvent.setup();
  await screen.findByText('5 de 5 monitores');
  const select = screen.getByLabelText('Qualidade dos dados');
  const search = screen.getByLabelText('Buscar monitores');
  await user.selectOptions(select, 'no_data');
  await user.type(search, 'WORKER.EXAMPLE.COM');
  expect(screen.getByText('1 de 5 monitores')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Ver histórico de Worker sem leitura' })).toBeVisible();
  await user.selectOptions(select, 'fresh');
  expect(screen.getByText('0 de 5 monitores')).toBeVisible();
  expect(screen.getByText(/Nenhum monitor corresponde aos filtros/)).toBeVisible();
  expect(screen.queryByRole('table', { name: 'Monitores do projeto Aplicação' })).not.toBeInTheDocument();
  const clear = screen.getByRole('button', { name: 'Limpar filtros' });
  clear.focus(); await user.keyboard('{Enter}');
  expect(search).toHaveFocus(); expect(search).toHaveValue(''); expect(select).toHaveValue('all');
  expect(screen.getByText('5 de 5 monitores')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Limpar filtros' })).not.toBeInTheDocument();
  expect(screen.getByText('5 de 5 monitores').closest('[aria-live], [role="status"]')).toBeNull();
  await user.type(search, 'ANTIGA');
  expect(screen.getByText('1 de 5 monitores')).toBeVisible();
});

it('reseta busca/qualidade ao trocar projeto e não filtra o novo por critérios antigos', async () => {
  setup(data, true);
  const user = userEvent.setup();
  await screen.findByText('5 de 5 monitores');
  await user.selectOptions(screen.getByLabelText('Qualidade dos dados'), 'fresh');
  await user.type(screen.getByLabelText('Buscar monitores'), 'recente');
  await user.click(screen.getByRole('button', { name: 'Projeto B' }));
  expect(await screen.findByRole('button', { name: 'Ver histórico de Endpoint do B' })).toBeVisible();
  expect(screen.getByLabelText('Qualidade dos dados')).toHaveValue('all');
  expect(screen.getByLabelText('Buscar monitores')).toHaveValue('');
  expect(screen.getByText('1 de 1 monitor')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Limpar filtros' })).not.toBeInTheDocument();
});

it('refaz filtro pelo clock de15s sem fetch extra ao envelhecer uma leitura', async () => {
  vi.useFakeTimers(); vi.setSystemTime(now); vi.stubGlobal('EventSource', undefined);
  const aging = { ...data[0], last_checked_at: new Date(now - 110000).toISOString() };
  const fetch = vi.fn(async (url: unknown) => {
    const observation = observationResponse(url); if (observation) return observation;
    if (path(url) === '/auth/me') return json(session);
    if (path(url) === '/projects') return json({ items: [project], total: 1 });
    return json({ items: [aging], total: 1 });
  });
  vi.stubGlobal('fetch', fetch);
  await act(async () => { render(<App />); await vi.advanceTimersByTimeAsync(0); });
  fireEvent.change(screen.getByLabelText('Qualidade dos dados'), { target: { value: 'fresh' } });
  expect(screen.getByText('1 de 1 monitor')).toBeVisible();
  const requests = fetch.mock.calls.length;
  await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
  expect(screen.getByText('0 de 1 monitor')).toBeVisible();
  expect(fetch).toHaveBeenCalledTimes(requests);
  fireEvent.change(screen.getByLabelText('Qualidade dos dados'), { target: { value: 'stale' } });
  expect(screen.getByText('1 de 1 monitor')).toBeVisible();
});

it('distingue projeto vazio de zero resultados filtrados e permite limpar sem monitores', async () => {
  setup([]);
  const user = userEvent.setup();
  await screen.findByRole('button', { name: 'Novo monitor' });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Novo monitor' })).toBeEnabled());
  await user.selectOptions(screen.getByLabelText('Qualidade dos dados'), 'paused');
  expect(screen.getByText('0 de 0 monitores')).toBeVisible();
  expect(screen.getByText('Nenhum endpoint configurado')).toBeVisible();
  expect(screen.queryByText(/Nenhum monitor corresponde aos filtros/)).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Limpar filtros' }));
  expect(screen.getByLabelText('Qualidade dos dados')).toHaveValue('all');
  expect(screen.getByLabelText('Buscar monitores')).toHaveFocus();
});

it('preserva pause/resume e mantém filtro ativo quando ação remove o monitor dos resultados', async () => {
  vi.stubGlobal('EventSource', undefined); vi.spyOn(Date, 'now').mockReturnValue(now);
  let saved = data[0];
  const fetch = vi.fn(async (url: unknown, init?: RequestInit) => {
    const observation = observationResponse(url); if (observation) return observation;
    if (path(url) === '/auth/me') return json(session);
    if (path(url) === '/projects') return json({ items: [project], total: 1 });
    if (path(url) === '/monitors/fresh/pause' && init?.method === 'POST') { saved = { ...saved, paused_at: new Date(now).toISOString(), freshness: 'paused' }; return json(saved); }
    if (path(url) === '/monitors/fresh/resume' && init?.method === 'POST') { saved = { ...saved, paused_at: null, freshness: 'fresh' }; return json(saved); }
    return json({ items: [saved], total: 1 });
  });
  vi.stubGlobal('fetch', fetch); render(<App />);
  const user = userEvent.setup();
  await screen.findByText('1 de 1 monitor');
  await user.selectOptions(screen.getByLabelText('Qualidade dos dados'), 'fresh');
  await user.click(screen.getByRole('button', { name: 'Pausar API recente offline' }));
  await waitFor(() => expect(screen.getByText('0 de 1 monitor')).toBeVisible());
  expect(screen.getByLabelText('Qualidade dos dados')).toHaveValue('fresh');
  await user.selectOptions(screen.getByLabelText('Qualidade dos dados'), 'paused');
  await user.click(screen.getByRole('button', { name: 'Retomar API recente offline' }));
  await waitFor(() => expect(screen.getByText('0 de 1 monitor')).toBeVisible());
  expect(screen.getByLabelText('Qualidade dos dados')).toHaveValue('paused');
  expect(fetch.mock.calls.some(([url, init]) => path(url) === '/monitors/fresh/resume' && init?.method === 'POST')).toBe(true);
});
