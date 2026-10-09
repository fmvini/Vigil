import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import App from '../App';
import { CheckTiming } from '../CheckTiming';
import { PublicStatus } from '../Observations';
import { api } from '../api';
import { emptyMetrics, json, monitor, project } from './fixtures';

const cloud = { minimum_interval_seconds: 900, scheduled_checks_interval_seconds: 900 };
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); api.setCsrfToken(null); });

it('mostra a agenda real, o atraso e que consultar não dispara medições', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => json(cloud)));
  render(<CheckTiming />);
  expect(await screen.findByText(/agenda configurada a cada 15 minutos/)).toBeVisible();
  expect(screen.getByText(/A execução pode atrasar por horas/)).toBeVisible();
  expect(screen.getByText(/não inicia uma verificação do endpoint/)).toBeVisible();
});

it('não presume uma agenda cloud quando runtime falha e permite nova consulta', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(json({}, 503)).mockResolvedValueOnce(json(cloud));
  vi.stubGlobal('fetch', fetch); render(<CheckTiming />);
  await screen.findByText('Não foi possível consultar a agenda de verificações.');
  expect(screen.queryByText(/15 minutos|por horas/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Consultar agenda novamente' }));
  expect(await screen.findByText(/agenda configurada a cada 15 minutos/)).toBeVisible();
});

it.each(['unavailable', 'silent'] as const)('reconcilia a primeira medição via REST com SSE %s, sem reload manual', async mode => {
  vi.useFakeTimers();
  vi.stubGlobal('EventSource', mode === 'unavailable' ? undefined : class extends EventTarget { close() {} });
  let measured = false;
  const fetch = vi.fn(async (url: string, _init?: RequestInit) => {
    const path = url.replace('/api/v1', '').split('?')[0];
    if (path === '/runtime-config') return json(cloud);
    if (path === '/auth/me') return json({ user: { id: 'u1', email: 'poll.qa@example.com' }, csrf_token: 'qa' });
    if (path === '/projects') return json({ items: [project], total: 1 });
    if (path.endsWith('/metrics')) return json(measured ? { ...emptyMetrics, sample_count: 1, uptime_percent: 100, average_latency_ms: 123 } : emptyMetrics);
    if (path.endsWith('/incidents')) return json({ items: [], total: 0 });
    if (path.endsWith('/checks')) return json({ items: [], total: 0 });
    return json({ items: [{ ...monitor, interval_seconds: 900, ...(measured ? { freshness: 'fresh', health_status: 'online', last_checked_at: new Date().toISOString(), last_http_status: 200, last_latency_ms: 123 } : {}) }], total: 1 });
  });
  vi.stubGlobal('fetch', fetch); const view = render(<App />);
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  expect(screen.getByText('Aguardando a primeira medição.')).toBeVisible();
  expect(screen.getByText('Não avaliada')).toBeVisible();
  expect(screen.queryByText('Offline')).not.toBeInTheDocument();
  measured = true;
  await act(async () => { await vi.advanceTimersByTimeAsync(30_200); });
  expect(screen.getByText('HTTP 200 · 123 ms')).toBeVisible();
  expect(screen.getByText('100%')).toBeVisible();
  expect(screen.queryByText('Aguardando a primeira medição.')).not.toBeInTheDocument();
  expect(fetch.mock.calls.every(([, init]) => !init || (init as RequestInit).method === 'GET')).toBe(true);
  view.unmount(); const calls = fetch.mock.calls.length;
  await vi.advanceTimersByTimeAsync(60_000); expect(fetch).toHaveBeenCalledTimes(calls);
});

it('distingue primeira medição de pausa no status público sem atribuir offline', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.endsWith('/runtime-config')) return json(cloud);
    if (url.includes('/incidents')) return json({ items: [], total: 0 });
    return json({ name: 'Status QA', slug: 'qa', computed_at: emptyMetrics.computed_at, health_status: null, data_complete: false, freshness_counts: { no_data: 1, paused: 1, fresh: 0, stale: 0 }, monitors: [
      { ...monitor, name: 'Pendente' }, { ...monitor, id: 'm2', name: 'Pausado', freshness: 'paused' },
    ] });
  }));
  render(<PublicStatus slug="qa" />);
  expect(await screen.findByText('Aguardando a primeira medição.')).toBeVisible();
  expect(screen.getByText('Monitor pausado, sem medição recebida.')).toBeVisible();
  expect(screen.queryByText('Offline')).not.toBeInTheDocument();
});
