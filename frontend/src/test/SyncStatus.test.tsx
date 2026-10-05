import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import App from '../App';
import { api } from '../api';
import { json, monitor, project, observationResponse } from './fixtures';

const session = { user: { id: 'u1', email: 'tester@example.com' }, csrf_token: 'csrf-test' };
const firstRead = Date.UTC(2026, 9, 5, 12, 0, 0);
function path(input: unknown) { return String(input).replace('/api/v1', '').split('?')[0]; }
afterEach(() => { vi.unstubAllGlobals(); api.setCsrfToken(null); });

it('anuncia apenas o modo ao perder/reabrir conexão, preservando consulta REST e sem inventar saúde', async () => {
  let source: { onopen?: () => void; onerror?: () => void };
  vi.stubGlobal('EventSource', class extends EventTarget {
    static CLOSED = 2; readyState = 0; onopen?: () => void; onerror?: () => void;
    close = vi.fn(); constructor() { super(); source = this; }
  });
  vi.spyOn(Date, 'now').mockReturnValue(firstRead);
  vi.stubGlobal('fetch', vi.fn(async (url: unknown) => {
    const observation = observationResponse(url); if (observation) return observation;
    if (path(url) === '/auth/me') return json(session);
    if (path(url) === '/projects') return json({ items: [project], total: 1 });
    return json({ items: [monitor], total: 1 });
  }));
  render(<App />);
  await screen.findByText(/Última consulta dos monitores às/);
  const timestamp = document.querySelector('.sync-status time')!;
  expect(timestamp).toHaveAttribute('datetime', new Date(firstRead).toISOString());
  expect(timestamp.closest('[role="status"], [aria-live]')).toBeNull();
  await act(async () => { source.onopen?.(); });
  expect(screen.getByText('Atualizações conectadas')).toHaveAttribute('role', 'status');
  await act(async () => { source.onerror?.(); });
  expect(screen.getByText('Sincronização a cada 30 s')).toHaveAttribute('role', 'status');
  expect(screen.getByText('Consulta automática a cada 30 s. Use Atualizar para consultar agora.')).toBeVisible();
  expect(timestamp).toHaveAttribute('datetime', new Date(firstRead).toISOString());
  expect(screen.getByText('Não avaliada')).toBeVisible();
  expect(screen.getAllByText('Sem dados').length).toBeGreaterThan(0);
  await act(async () => { source.onopen?.(); });
  expect(screen.getByText('Atualizações conectadas')).toBeVisible();
});

it('só avança horário em REST bem-sucedido e explica a espera durante edição', async () => {
  vi.stubGlobal('EventSource', undefined);
  const now = vi.spyOn(Date, 'now').mockReturnValue(firstRead);
  let failed = false;
  vi.stubGlobal('fetch', vi.fn(async (url: unknown) => {
    const observation = observationResponse(url); if (observation) return observation;
    if (path(url) === '/auth/me') return json(session);
    if (path(url) === '/projects') return json({ items: [project], total: 1 });
    return failed ? json({ error: { code: 'unavailable', message: 'Unavailable' } }, 503) : json({ items: [], total: 0 });
  }));
  render(<App />);
  await screen.findByText(/Última consulta dos monitores às/);
  const user = userEvent.setup();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Atualizar' })).toBeEnabled());
  now.mockReturnValue(firstRead + 60000); failed = true;
  await user.click(screen.getByRole('button', { name: 'Atualizar' }));
  await screen.findByRole('button', { name: 'Tentar novamente' });
  expect(document.querySelector('.sync-status time')).toHaveAttribute('datetime', new Date(firstRead).toISOString());
  failed = false;
  await user.click(screen.getByRole('button', { name: 'Tentar novamente' }));
  await waitFor(() => expect(document.querySelector('.sync-status time')).toHaveAttribute('datetime', new Date(firstRead + 60000).toISOString()));
  await user.click(screen.getByRole('button', { name: 'Editar projeto' }));
  expect(screen.getByText('A consulta automática aguarda a ação em andamento.')).toBeVisible();
  expect(screen.queryByText('Consulta automática a cada 30 s. Use Atualizar para consultar agora.')).not.toBeInTheDocument();
});

it('não mostra consulta do projeto anterior enquanto aguarda primeiro REST do selecionado', async () => {
  vi.stubGlobal('EventSource', undefined);
  vi.spyOn(Date, 'now').mockReturnValue(firstRead);
  let completeSecond: (response: Response) => void = () => {};
  vi.stubGlobal('fetch', vi.fn(async (url: unknown) => {
    const observation = observationResponse(url); if (observation) return observation;
    if (path(url) === '/auth/me') return json(session);
    if (path(url) === '/projects') return json({ items: [project, { ...project, id: 'p2', name: 'Projeto B' }], total: 2 });
    if (path(url) === '/projects/p2/monitors') return new Promise<Response>(resolve => { completeSecond = resolve; });
    return json({ items: [], total: 0 });
  }));
  render(<App />);
  await screen.findByText(/Última consulta dos monitores às/);
  await userEvent.setup().click(screen.getByRole('button', { name: 'Projeto B' }));
  expect(await screen.findByText('Nenhuma consulta dos monitores concluída.')).toBeVisible();
  expect(document.querySelector('.sync-status time')).toBeNull();
  await act(async () => { completeSecond(json({ items: [], total: 0 })); });
  await screen.findByText(/Última consulta dos monitores às/);
});
