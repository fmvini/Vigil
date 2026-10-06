import { act, render, renderHook, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { IncidentList, MetricsPanel, MonitorDetail, PublicStatus, formatMetric, useResource } from '../Observations';
import { MonitorForm, ProjectForm } from '../Forms';
import { emptyMetrics, json, monitor, project } from './fixtures';

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); window.history.replaceState({}, '', '/'); });
const published = {
  name: 'Status QA', slug: 'status-qa', revision: 1, computed_at: emptyMetrics.computed_at,
  health_status: null, data_complete: false, freshness_counts: emptyMetrics.freshness_counts,
  monitors: [{ id: 'm1', name: 'Serviço publicado', health_status: null, freshness: 'no_data', last_checked_at: null }],
};

describe('métricas e observações', () => {
  it('conclui uma leitura lenta e reconcilia sinais acumulados sem consultas concorrentes', async () => {
    const completions: ((response: Response) => void)[] = [];
    const fetch = vi.fn(() => new Promise<Response>(resolve => completions.push(resolve))); vi.stubGlobal('fetch', fetch);
    const view = renderHook(({ revision }) => useResource<{ value: number }>('/projects/p1/metrics', revision), { initialProps: { revision: 0 } });
    view.rerender({ revision: 1 }); view.rerender({ revision: 2 }); expect(fetch).toHaveBeenCalledOnce();
    await act(async () => { completions[0](json({ value: 1 })); });
    expect(fetch).toHaveBeenCalledTimes(2); expect(view.result.current.loading).toBe(true);
    await act(async () => { completions[1](json({ value: 2 })); });
    expect(view.result.current.data).toEqual({ value: 2 }); expect(view.result.current.loading).toBe(false); view.unmount();
  });
  it('cancela snapshots ao trocar caminho ou editar e ignora resposta antiga', async () => {
    const completions: ((response: Response) => void)[] = [];
    const signals: AbortSignal[] = [];
    const fetch = vi.fn((_url: string, init: RequestInit) => { signals.push(init.signal as AbortSignal); return new Promise<Response>(resolve => completions.push(resolve)); }); vi.stubGlobal('fetch', fetch);
    const view = renderHook(({ path, paused }) => useResource<{ value: string }>(path, 0, undefined, paused), { initialProps: { path: '/projects/p1/metrics?period=24h', paused: false } });
    view.rerender({ path: '/projects/p2/metrics?period=7d', paused: false });
    expect(signals[0].aborted).toBe(true); expect(view.result.current.data).toBeNull();
    await act(async () => { completions[1](json({ value: 'p2' })); completions[0](json({ value: 'p1' })); });
    expect(view.result.current.data).toEqual({ value: 'p2' });
    view.rerender({ path: '/projects/p2/metrics?period=7d', paused: true }); expect(signals[1].aborted).toBe(true);
    view.rerender({ path: '/projects/p2/metrics?period=7d', paused: false }); expect(fetch).toHaveBeenCalledTimes(3);
    await act(async () => completions[2](json({ value: 'updated' })));
    expect(view.result.current.data).toEqual({ value: 'updated' }); view.unmount(); expect(signals[2].aborted).toBe(true);
  });
  it('preserva null como sem dados e zero como medida real', () => {
    expect(formatMetric(null, '%')).toBe('Sem dados'); expect(formatMetric(undefined, 'ms')).toBe('Sem dados'); expect(formatMetric(0, '%')).toBe('0%'); expect(formatMetric(0, 'ms')).toBe('0 ms');
  });
  it('mostra ausência de amostras e consulta o período selecionado', async () => {
    const fetch = vi.fn().mockImplementation(async () => json(emptyMetrics)); vi.stubGlobal('fetch', fetch);
    render(<MetricsPanel path="/projects/p1/metrics" />);
    expect(await screen.findByText('Ainda não há ciclos avaliados neste período.')).toBeVisible();
    expect(screen.getAllByText('Sem dados')).toHaveLength(3); expect(screen.queryByText('100%')).not.toBeInTheDocument();
    await userEvent.setup().selectOptions(screen.getByLabelText('Período'), '7d');
    await waitFor(() => expect(fetch.mock.calls.at(-1)?.[0]).toContain('period=7d'));
  });
  it('renderiza métricas e buckets fornecidos, sem calcular média de p95', async () => {
    const data = { ...emptyMetrics, sample_count: 10, success_count: 9, failure_count: 1, latency_sample_count: 9, uptime_percent: 90, average_latency_ms: 100, p95_latency_ms: 140,
      series: [{ bucket_start: emptyMetrics.from, sample_count: 2, success_count: 1, failure_count: 1, latency_sample_count: 1, uptime_percent: 50, average_latency_ms: 200, p95_latency_ms: 200 }] };
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => json(data))); render(<MetricsPanel path="/projects/p1/metrics" />);
    expect(await screen.findByText('90%')).toBeVisible(); expect(screen.getByText('140 ms')).toBeVisible();
    await userEvent.setup().click(screen.getByText(/Ver série temporal/));
    expect(screen.getByText('50%')).toBeVisible(); expect(screen.getByText(/Intervalos ausentes são lacunas/)).toBeVisible();
  });
  it('pagina e filtra incidentes, preservando encerramento administrativo', async () => {
    const item = { id: 'i1', monitor_id: 'm1', monitor_name: 'Endpoint', started_at: emptyMetrics.from, detected_at: emptyMetrics.from, ended_at: emptyMetrics.to, end_reason: 'configuration_changed' };
    const fetch = vi.fn().mockImplementation(async () => json({ items: [item], total: 21 })); vi.stubGlobal('fetch', fetch); const user = userEvent.setup();
    render(<IncidentList path="/projects/p1/incidents" monitorId="m1" />);
    expect(await screen.findByText('Configuração alterada')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Próxima' }));
    await waitFor(() => expect(fetch.mock.calls.at(-1)?.[0]).toContain('offset=20'));
    await user.selectOptions(screen.getByLabelText('Situação'), 'closed');
    await waitFor(() => { expect(fetch.mock.calls.at(-1)?.[0]).toContain('state=closed'); expect(fetch.mock.calls.at(-1)?.[0]).toContain('offset=0'); });
    expect(fetch.mock.calls.at(-1)?.[0]).toContain('monitor_id=m1');
  });
  it('retorna à última página válida quando retenção reduz o total de incidentes', async () => {
    let total = 21;
    const fetch = vi.fn(async (url: string) => json({ items: [], total: new URL(url, window.location.origin).searchParams.get('offset') === '20' ? total : 21 })); vi.stubGlobal('fetch', fetch);
    const view = render(<IncidentList path="/projects/p1/incidents" revision={0} />); const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Próxima' }));
    await screen.findByText('21–21 de 21'); total = 1; view.rerender(<IncidentList path="/projects/p1/incidents" revision={1} />);
    await waitFor(() => expect(fetch.mock.calls.at(-1)?.[0]).toContain('offset=0'));
    expect(screen.queryByText('21–1 de 1')).not.toBeInTheDocument();
  });
  it('detalha resultado e tentativas de um único ciclo', async () => {
    const check = { id: 'c1', scheduled_at: emptyMetrics.from, completed_at: emptyMetrics.to, outcome: 'success', http_status: 200, latency_ms: 123, cycle_duration_ms: 1700, queue_delay_ms: 10, config_version: 1, attempt_count: 2, health_after: 'degraded', error_code: null, degradation_reason: 'retry_recovered', attempts: [{ http_status: null, error_code: 'timeout', latency_ms: null, duration_ms: 1000 }, { http_status: 200, error_code: null, latency_ms: 123, duration_ms: 123 }] };
    vi.stubGlobal('fetch', vi.fn(async (url: string) => url.includes('/metrics') ? json(emptyMetrics) : url.includes('/checks') ? json({ items: [check], total: 1 }) : json({ items: [], total: 0 })));
    render(<MonitorDetail monitor={monitor} revision={0} onBack={vi.fn()} />);
    expect(await screen.findByText('Sucesso')).toBeVisible();
    await userEvent.setup().click(screen.getByText('Detalhes do ciclo'));
    expect(screen.getByText(/Recuperado após retry/)).toBeVisible();
    expect(within(screen.getByRole('list')).getAllByRole('listitem')).toHaveLength(2);
  });
});

describe('publicação explícita e rota pública', () => {
  it('projeto e monitor novos iniciam privados e enviam o opt-in escolhido', async () => {
    const fetch = vi.fn(async (url: string, init: RequestInit) => url.endsWith('/runtime-config') ? json({ minimum_interval_seconds: 60, scheduled_checks_interval_seconds: null }) : json({ ...(url.endsWith('/projects') ? project : monitor), ...JSON.parse(String(init.body)) }, 201)); vi.stubGlobal('fetch', fetch); const user = userEvent.setup();
    const saved = vi.fn(); const props = { onCancel: vi.fn(), onSaved: saved, onBusyChange: vi.fn() };
    const first = render(<ProjectForm {...props} />);
    expect(screen.getByLabelText('Publicar página de status')).not.toBeChecked();
    await user.type(screen.getByLabelText('Nome do projeto'), 'Projeto'); await user.click(screen.getByLabelText('Publicar página de status'));
    await user.click(screen.getByRole('button', { name: 'Salvar projeto' })); await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(JSON.parse(String(fetch.mock.calls[0][1].body)).public_status_enabled).toBe(true); first.unmount();
    render(<MonitorForm {...props} projectId="p1" />); expect(await screen.findByLabelText('Exibir na página pública')).not.toBeChecked();
    await user.type(screen.getByLabelText('Nome do monitor'), 'Endpoint'); await user.type(screen.getByLabelText('URL do endpoint'), 'https://example.com/health');
    await user.click(screen.getByLabelText('Exibir na página pública')); await user.click(screen.getByRole('button', { name: 'Salvar monitor' }));
    await waitFor(() => expect(fetch.mock.calls.filter(([, init]) => init.method === 'POST')).toHaveLength(2)); expect(JSON.parse(String(fetch.mock.calls.find(([url, init]) => url.endsWith('/monitors') && init.method === 'POST')?.[1].body)).is_public).toBe(true);
  });
  it('abre /status/slug sem consultar auth e sem renderizar campos privados extras', async () => {
    const fetch = vi.fn(async (url: string) => url.includes('/incidents') ? json({ items: [], total: 0 }) : json({ ...published, url: 'https://private.invalid', email: 'private@example.com', description: 'PRIVATE_DESCRIPTION' })); vi.stubGlobal('fetch', fetch);
    window.history.replaceState({}, '', '/status/status-qa'); render(<App />);
    expect(await screen.findByRole('heading', { name: 'Status QA' })).toBeVisible();
    expect(fetch.mock.calls.some(([url]) => url.includes('/auth/'))).toBe(false);
    expect(screen.queryByText(/private.invalid|private@example.com|PRIVATE_DESCRIPTION/)).not.toBeInTheDocument();
    expect(screen.getByText('Não avaliada')).toBeVisible();
  });
  it('trata 404 pública como página não publicada', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => json({ error: { code: 'not_found', message: 'Status page not found' } }, 404)));
    render(<PublicStatus slug="desativada" />); expect(await screen.findByRole('heading', { name: 'Página não publicada' })).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'Entre no Vigil' })).not.toBeInTheDocument();
  });
  it('consulta a página pública a cada 30 segundos e encerra polling no unmount', async () => {
    vi.useFakeTimers(); const fetch = vi.fn(async (url: string) => url.includes('/incidents') ? json({ items: [], total: 0 }) : json(published)); vi.stubGlobal('fetch', fetch);
    const view = render(<PublicStatus slug="status-qa" />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    const initial = fetch.mock.calls.filter(([url]) => !url.includes('/incidents')).length;
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(fetch.mock.calls.filter(([url]) => !url.includes('/incidents'))).toHaveLength(initial + 1);
    view.unmount(); const stopped = fetch.mock.calls.length; await vi.advanceTimersByTimeAsync(60000); expect(fetch).toHaveBeenCalledTimes(stopped);
  });
  it('remove snapshot público e incidentes quando a publicação é revogada no polling', async () => {
    vi.useFakeTimers(); let enabled = true;
    vi.stubGlobal('fetch', vi.fn(async (url: string) => enabled ? url.includes('/incidents') ? json({ items: [], total: 0 }) : json(published) : json({ error: { code: 'not_found', message: 'Unavailable' } }, 404)));
    render(<PublicStatus slug="status-qa" />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); }); expect(screen.getByText('Serviço publicado')).toBeVisible();
    enabled = false; await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(screen.getByRole('heading', { name: 'Página não publicada' })).toBeVisible(); expect(screen.queryByText('Serviço publicado')).not.toBeInTheDocument(); expect(screen.queryByRole('heading', { name: 'Incidentes' })).not.toBeInTheDocument();
  });
});
