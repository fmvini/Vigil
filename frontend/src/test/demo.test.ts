import { describe, expect, it, vi, afterEach } from 'vitest';
import { DemoClient } from '../demo';
import { defaultConfig } from '../domain';
import type { Check, Metrics, Monitor, Page, Project, PublicStatus } from '../types';

afterEach(() => vi.unstubAllGlobals());
describe('transporte da demonstração', () => {
  it('nega autenticação, URLs e rotas desconhecidas sem acessar a rede', async () => {
    const fetch = vi.fn(() => { throw new Error('NETWORK_FORBIDDEN'); });
    vi.stubGlobal('fetch', fetch);
    const client = new DemoClient();
    for (const path of ['/auth/me', '/auth/logout', '/unknown', '//api.example.com', 'https://api.example.com']) {
      await expect(client.request(path)).rejects.toMatchObject({ status: 404 });
    }
    const controller = new AbortController(); controller.abort();
    await expect(client.request('/projects', 'GET', undefined, controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetch).not.toHaveBeenCalled();
  });
  it('mantém CRUD e respostas em memória, com reset e DTO público restrito', async () => {
    const client = new DemoClient();
    const project = await client.request<Project>('/projects', 'POST', { name: 'Projeto fictício', public_status_enabled: true });
    const monitor = await client.request<Monitor>(`/projects/${project.id}/monitors`, 'POST', { ...defaultConfig, name: 'API fictícia', url: 'https://api.exemplo.invalid/health', interval_seconds: 900, is_public: true });
    monitor.name = 'Mudança externa';
    expect((await client.request<Monitor>(`/monitors/${monitor.id}`)).name).toBe('API fictícia');
    await expect(client.request(`/monitors/${monitor.id}`, 'PATCH', { url: 'https://example.com' })).rejects.toMatchObject({ status: 422 });
    const status = await client.request<PublicStatus>(`/public/status/${project.public_slug}`);
    expect(Object.keys(status.monitors[0]).sort()).toEqual(['freshness', 'health_status', 'id', 'last_checked_at', 'name']);
    await client.request(`/projects/${project.id}`, 'DELETE');
    await expect(client.request(`/public/status/${project.public_slug}`)).rejects.toMatchObject({ status: 404 });
    client.reset();
    expect((await client.list<Project>('/projects')).map(p => p.id)).toEqual(['demo-store', 'demo-platform']);
  });
  it('interrompe sequência na pausa, mantém offline até recuperação e avança versão', async () => {
    const client = new DemoClient();
    const m = await client.request<Monitor>('/projects/demo-store/monitors', 'POST', { ...defaultConfig, name: 'Sequência', url: 'https://sequence.invalid', interval_seconds: 900 });
    const simulate = (scenario: string) => client.request<Monitor>(`/demo/monitors/${m.id}/simulate`, 'POST', { scenario });
    await simulate('failure'); await simulate('failure');
    await client.request(`/monitors/${m.id}/pause`, 'POST');
    await expect(simulate('success')).rejects.toMatchObject({ status: 409 });
    await client.request(`/monitors/${m.id}/resume`, 'POST');
    expect((await simulate('failure')).health_status).toBe('degraded');
    await simulate('failure'); expect((await simulate('failure')).health_status).toBe('offline');
    await client.request(`/monitors/${m.id}/pause`, 'POST'); await client.request(`/monitors/${m.id}/resume`, 'POST');
    expect((await simulate('failure')).health_status).toBe('offline');
    expect((await simulate('success')).health_status).toBe('online');
    const checks = await client.request<Page<Check>>(`/monitors/${m.id}/checks?limit=100`);
    expect(Math.max(...checks.items.map(c => c.config_version))).toBe(5);
  });
  it('calcula métricas pelos ciclos, exclui jobs e oferece paginação e tempos coerentes', async () => {
    const client = new DemoClient();
    const metrics = await client.request<Metrics>('/projects/demo-store/metrics?period=7d');
    expect(metrics.sample_count).toBe(metrics.success_count + metrics.failure_count);
    expect(metrics.excluded_count).toBe(24);
    expect(metrics.freshness_counts).toEqual({ fresh: 3, stale: 1, paused: 1, no_data: 1 });
    expect(metrics.data_complete).toBe(false);
    expect(Date.parse(metrics.to)).toBeLessThanOrEqual(Date.parse(metrics.computed_at));
    const checks = await client.request<Page<Check>>('/monitors/demo-checkout/checks?period=7d&limit=100');
    expect(checks.total).toBe(103); expect(checks.items).toHaveLength(100);
    const second = await client.request<Page<Check>>('/monitors/demo-checkout/checks?period=7d&limit=100&offset=100');
    expect(second.items).toHaveLength(3);
    for (const id of ['demo-payment', 'demo-mail']) {
      const { items } = await client.request<Page<Check>>(`/monitors/${id}/checks`);
      for (const c of items) {
        expect(Date.parse(c.completed_at) - Date.parse(c.started_at)).toBe(c.cycle_duration_ms);
        expect(c.cycle_duration_ms).toBeGreaterThanOrEqual(c.attempts.reduce((sum, a) => sum + (a.duration_ms ?? 0), 0));
      }
    }
  });
});
