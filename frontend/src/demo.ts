import { ApiClient, ApiError } from './api';
import { currentFreshness, defaultConfig, summarize, validateMonitor } from './domain';
import type { Check, Incident, Metrics, Monitor, MonitorConfig, Project, PublicIncident } from './types';

export type DemoScenario = 'success' | 'slow' | 'retry' | 'failure';
type Job = { job_id: string; monitor_id: string; config_version: number; status: 'exhausted' | 'expired'; scheduled_at: string; finished_at: string; execution_count: number; error_code: string };
const checkFields: (keyof MonitorConfig)[] = ['url', 'interval_seconds', 'timeout_ms', 'expected_status', 'failure_threshold', 'retry_count', 'latency_threshold_ms'];
const iso = (time: number) => new Date(time).toISOString();
const fail = (status = 404, message = 'Este recurso não existe na demonstração.') => { throw new ApiError(status, status === 404 ? 'not_found' : 'demo_validation', message); };
export function isDemoUrl(value: string) {
  try { const url = new URL(value); return url.hostname.endsWith('.invalid') && ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password && !url.hash; } catch { return false; }
}

/** A closed, in-memory transport. It never delegates to ApiClient.request. */
export class DemoClient extends ApiClient {
  private projects: Project[] = [];
  private monitors: Monitor[] = [];
  private checks: Check[] = [];
  private incidents: Incident[] = [];
  private jobs: Job[] = [];
  private versions = new Map<string, number>();
  private failures = new Map<string, { count: number; first: Check }>();
  private counter = 0;
  constructor() { super(); this.reset(); }
  private id(prefix: string) { return `demo-${prefix}-${++this.counter}`; }
  reset() {
    this.projects = []; this.monitors = []; this.checks = []; this.incidents = []; this.jobs = [];
    this.versions.clear(); this.failures.clear(); this.counter = 0;
    const now = Date.now();
    this.projects.push({ id: 'demo-store', name: 'Loja Horizonte', description: 'Uma loja fictícia: API, checkout e pagamentos em cenários diferentes.', public_slug: 'vigil-demo', public_status_enabled: true, archived_at: null, revision: 0 },
      { id: 'demo-platform', name: 'Plataforma interna', description: 'Explore um segundo projeto e configure novos endpoints fictícios.', public_slug: 'plataforma-demo', public_status_enabled: false, archived_at: null, revision: 0 });
    const seed = (id: string, name: string, project = 'demo-store') => {
      const m: Monitor = { ...defaultConfig, id, name, project_id: project, url: `https://${id}.vigil.invalid/health`, interval_seconds: 900, is_public: true, paused_at: null, archived_at: null, freshness: 'no_data', health_status: null, last_checked_at: null, last_http_status: null, last_latency_ms: null };
      this.monitors.push(m); this.versions.set(id, 1); return m;
    };
    const api = seed('demo-api', 'API da loja');
    for (let i = 31; i >= 0; i--) this.evaluate(api, 'success', now - i * 1800000 - 60000);
    const checkout = seed('demo-checkout', 'Checkout');
    // Closed incidents have three failures and a matching recovery check.
    for (let i = 25; i >= 1; i--) {
      const start = now - i * 7200000;
      for (let j = 0; j < 3; j++) this.evaluate(checkout, 'failure', start + j * 900000);
      this.evaluate(checkout, 'success', start + 2700000);
    }
    for (let j = 3; j >= 1; j--) this.evaluate(checkout, 'failure', now - j * 900000);
    const payment = seed('demo-payment', 'Pagamentos'); this.evaluate(payment, 'slow', now - 45000);
    const stale = seed('demo-report', 'Relatórios'); this.evaluate(stale, 'success', now - 14400000);
    const paused = seed('demo-mail', 'Envio de e-mails'); this.evaluate(paused, 'retry', now - 900000); paused.paused_at = iso(now - 600000);
    seed('demo-new', 'Novo serviço'); seed('demo-internal', 'API interna', 'demo-platform');
    for (let i = 0; i < 24; i++) this.jobs.push({ job_id: this.id('job'), monitor_id: i % 2 ? checkout.id : api.id, config_version: 1, status: i % 2 ? 'expired' : 'exhausted', scheduled_at: iso(now - (i + 1) * 1200000), finished_at: iso(now - (i + 1) * 1200000 + (i % 2 ? 900000 : 90000)), execution_count: i % 2 ? 0 : 3, error_code: i % 2 ? 'deadline_exceeded' : 'execution_crashed' });
  }
  private project(id: string) { return this.projects.find(p => p.id === id && !p.archived_at) ?? fail(); }
  private monitor(id: string) {
    const m = this.monitors.find(m => m.id === id && !m.archived_at) ?? fail(); this.project(m.project_id); return m;
  }
  private active(projectId: string) { this.project(projectId); return this.monitors.filter(m => m.project_id === projectId && !m.archived_at); }
  private readMonitor(m: Monitor) { return { ...m, freshness: currentFreshness({ ...m, freshness: m.paused_at ? 'paused' : m.last_checked_at ? 'fresh' : 'no_data' }) }; }
  private close(m: Monitor, reason: 'recovered' | 'configuration_changed' | 'archived', time: number, closing: string | null = null) {
    for (const incident of this.incidents.filter(i => i.monitor_id === m.id && !i.ended_at)) {
      incident.ended_at = iso(time); incident.end_reason = reason; incident.closing_check_id = closing;
    }
  }
  private evaluate(m: Monitor, scenario: DemoScenario, time: number) {
    const success = scenario !== 'failure';
    const retry = scenario === 'retry' && m.retry_count > 0;
    const latency = scenario === 'slow' ? m.latency_threshold_ms ?? 1200 : 180 + this.counter % 160;
    const http = success ? m.expected_status : m.expected_status === 503 ? 500 : 503;
    const previous = this.failures.get(m.id);
    const count = success ? 0 : (previous?.count ?? 0) + 1;
    const offline = !success && (m.health_status === 'offline' || count >= m.failure_threshold);
    const degraded = retry ? 'retry_recovered' : success && m.latency_threshold_ms !== null && latency >= m.latency_threshold_ms ? 'high_latency' : !success && !offline ? 'failure_pending' : null;
    const health = offline ? 'offline' : degraded ? 'degraded' : 'online';
    const duration = (retry ? m.timeout_ms + 600 : 0) + (success ? latency : 300);
    const check: Check = { id: this.id('check'), job_id: this.id('cycle'), monitor_id: m.id, config_version: this.versions.get(m.id) ?? 1, scheduled_at: iso(time - duration - 20), started_at: iso(time - duration), completed_at: iso(time), outcome: success ? 'success' : 'failure', http_status: http, latency_ms: success ? latency : null, cycle_duration_ms: duration, queue_delay_ms: 20, attempt_count: retry ? 2 : 1, attempts: [...(retry ? [{ http_status: null, error_code: 'timeout', latency_ms: null, duration_ms: m.timeout_ms }] : []), { http_status: http, error_code: success ? null : 'unexpected_status', latency_ms: success ? latency : null, duration_ms: success ? latency : 300 }], error_code: success ? null : 'unexpected_status', health_after: health, degradation_reason: degraded };
    this.checks.push(check);
    if (success) { this.failures.delete(m.id); this.close(m, 'recovered', time, check.id); }
    else {
      const first = previous?.first ?? check; this.failures.set(m.id, { count, first });
      if (count >= m.failure_threshold && !this.incidents.some(i => i.monitor_id === m.id && !i.ended_at)) this.incidents.push({ id: this.id('incident'), monitor_id: m.id, monitor_name: m.name, started_at: first.started_at, detected_at: check.completed_at, ended_at: null, end_reason: null, cause_code: 'unexpected_status', failure_threshold_snapshot: m.failure_threshold, opening_check_id: check.id, closing_check_id: null });
    }
    Object.assign(m, { health_status: health, freshness: 'fresh', last_checked_at: check.completed_at, last_http_status: http, last_latency_ms: success ? latency : null });
    this.project(m.project_id).revision++; return this.readMonitor(m);
  }
  private window(query: URLSearchParams, incidents = false) {
    const period = query.get('period') ?? (incidents ? '30d' : '24h');
    if (!(incidents ? ['24h', '7d', '30d', '90d'] : ['24h', '7d', '30d']).includes(period)) fail(422, 'Período inválido.');
    const to = Date.now();
    return { from: to - (period === '24h' ? 1 : parseInt(period)) * 86400000, to };
  }
  private page<T>(items: T[], query: URLSearchParams) {
    const limit = Number(query.get('limit') ?? 20), offset = Number(query.get('offset') ?? 0);
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100 || !Number.isSafeInteger(offset) || offset < 0) fail(422, 'Paginação inválida.');
    return { items: items.slice(offset, offset + limit), total: items.length };
  }
  private aggregate(checks: Check[]) {
    const successes = checks.filter(c => c.outcome === 'success');
    const latencies = successes.map(c => c.latency_ms).filter((n): n is number => n !== null).sort((a, b) => a - b);
    const index = .95 * (latencies.length - 1), lo = Math.floor(index), hi = Math.ceil(index);
    return { success_count: successes.length, failure_count: checks.length - successes.length, sample_count: checks.length, uptime_percent: checks.length ? successes.length / checks.length * 100 : null, latency_sample_count: latencies.length, average_latency_ms: latencies.length ? latencies.reduce((a, b) => a + b, 0) / latencies.length : null, p95_latency_ms: latencies.length ? latencies[lo] + (latencies[hi] - latencies[lo]) * (index - lo) : null };
  }
  private metrics(monitors: Monitor[], query: URLSearchParams): Metrics {
    const window = this.window(query), ids = new Set(monitors.map(m => m.id));
    const checks = this.checks.filter(c => ids.has(c.monitor_id) && Date.parse(c.scheduled_at) >= window.from && Date.parse(c.scheduled_at) < window.to);
    const bucket_seconds = query.get('period') === '7d' || query.get('period') === '30d' ? 86400 : 3600;
    const buckets = new Map<number, Check[]>();
    for (const check of checks) { const start = Math.floor(Date.parse(check.scheduled_at) / (bucket_seconds * 1000)) * bucket_seconds * 1000; buckets.set(start, [...(buckets.get(start) ?? []), check]); }
    const summary = summarize(monitors.map(m => this.readMonitor(m)));
    return { ...this.aggregate(checks), from: iso(window.from), to: iso(window.to), computed_at: iso(Date.now()), excluded_count: this.jobs.filter(j => ids.has(j.monitor_id) && Date.parse(j.scheduled_at) >= window.from && Date.parse(j.scheduled_at) < window.to).length, cancelled_count: 0, pending_count: 0, skipped_slots: 0, health_status: summary.health, data_complete: !summary.partial, freshness_counts: summary.counts, bucket_seconds, series: [...buckets.entries()].sort(([a], [b]) => a - b).map(([start, checks]) => ({ bucket_start: iso(start), ...this.aggregate(checks) })) };
  }
  private incidentPage(monitors: Monitor[], query: URLSearchParams, publicOnly: boolean) {
    const window = this.window(query, true), ids = new Set(monitors.map(m => m.id));
    const state = query.get('state') ?? 'all'; if (!['all', 'open', 'closed'].includes(state)) fail(422, 'Situação inválida.');
    const filter = query.get('monitor_id'); if (filter && !ids.has(filter)) fail();
    const items = this.incidents.filter(i => ids.has(i.monitor_id) && (!filter || i.monitor_id === filter) && Date.parse(i.started_at) < window.to && (!i.ended_at || Date.parse(i.ended_at) > window.from) && (state === 'all' || (state === 'open' ? !i.ended_at : Boolean(i.ended_at)))).sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at)).map(i => ({ ...i, monitor_name: monitors.find(m => m.id === i.monitor_id)!.name }));
    return this.page(publicOnly ? items.map(({ id, monitor_id, monitor_name, started_at, detected_at, ended_at, end_reason }): PublicIncident => ({ id, monitor_id, monitor_name, started_at, detected_at, ended_at, end_reason })) : items, query);
  }
  private validate(config: MonitorConfig) {
    const error = validateMonitor(config, 900);
    const numeric: [keyof MonitorConfig, number, number][] = [['timeout_ms', 1000, 15000], ['expected_status', 200, 599], ['failure_threshold', 1, 10], ['retry_count', 0, 2]];
    if (error || !isDemoUrl(config.url) || !config.name?.trim() || config.name.length > 100 || config.url.length > 2048 || numeric.some(([k, min, max]) => !Number.isInteger(config[k]) || Number(config[k]) < min || Number(config[k]) > max) || (config.latency_threshold_ms !== null && (!Number.isInteger(config.latency_threshold_ms) || config.latency_threshold_ms < 100))) fail(422, error ?? 'Use uma configuração válida e uma URL fictícia .invalid.');
  }
  override async request<T>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
    signal?.throwIfAborted();
    // Reject absolute/network paths and every unimplemented route locally.
    if (!path.startsWith('/') || path.startsWith('//') || path.includes('#')) return fail();
    const [route, search = ''] = path.split('?'), query = new URLSearchParams(search);
    const input = (body ?? {}) as Record<string, unknown>;
    let result: unknown;
    if (route === '/runtime-config' && method === 'GET') result = { minimum_interval_seconds: 900, scheduled_checks_interval_seconds: 900 };
    else if (route === '/projects' && method === 'GET') result = this.page(this.projects.filter(p => !p.archived_at), query);
    else if (route === '/projects' && method === 'POST') {
      const name = typeof input.name === 'string' ? input.name.trim() : '';
      if (!name || name.length > 100 || (input.description !== null && input.description !== undefined && (typeof input.description !== 'string' || input.description.length > 500))) fail(422, 'Informe um nome e uma descrição válidos.');
      const p: Project = { id: this.id('project'), name, description: input.description as string | null ?? null, public_slug: this.id('status'), public_status_enabled: input.public_status_enabled === true, archived_at: null, revision: 0 }; this.projects.push(p); result = p;
    } else if (/^\/projects\/[^/]+$/.test(route)) {
      const p = this.project(route.split('/')[2]);
      if (method === 'GET') result = p;
      else if (method === 'PATCH') {
        if ('name' in input && (typeof input.name !== 'string' || !input.name.trim() || input.name.length > 100)) fail(422, 'Informe um nome válido.');
        if ('description' in input && input.description !== null && (typeof input.description !== 'string' || input.description.length > 500)) fail(422, 'Descrição inválida.');
        if ('public_status_enabled' in input && typeof input.public_status_enabled !== 'boolean') fail(422, 'Publicação inválida.');
        Object.assign(p, { ...('name' in input ? { name: String(input.name).trim() } : {}), ...('description' in input ? { description: input.description } : {}), ...('public_status_enabled' in input ? { public_status_enabled: input.public_status_enabled } : {}), revision: p.revision + 1 }); result = p;
      } else if (method === 'DELETE') { for (const m of this.active(p.id)) { this.close(m, 'archived', Date.now()); m.archived_at = iso(Date.now()); } p.archived_at = iso(Date.now()); }
      else return fail();
    } else if (/^\/projects\/[^/]+\/monitors$/.test(route)) {
      const p = this.project(route.split('/')[2]);
      if (method === 'GET') result = this.page(this.active(p.id).map(m => this.readMonitor(m)), query);
      else if (method === 'POST') { const config = { ...defaultConfig, ...input } as MonitorConfig; this.validate(config); const m: Monitor = { ...config, name: config.name.trim(), id: this.id('monitor'), project_id: p.id, paused_at: null, archived_at: null, health_status: null, freshness: 'no_data', last_checked_at: null, last_http_status: null, last_latency_ms: null }; this.monitors.push(m); this.versions.set(m.id, 1); p.revision++; result = m; }
      else return fail();
    } else if (/^\/monitors\/[^/]+(?:\/(?:pause|resume|checks|metrics))?$/.test(route)) {
      const [, , id, action] = route.split('/'); const m = this.monitor(id);
      if (!action && method === 'GET') result = this.readMonitor(m);
      else if (!action && method === 'PATCH') {
        const config = Object.fromEntries(Object.keys(defaultConfig).map(k => [k, k in input ? input[k] : m[k as keyof MonitorConfig]])) as unknown as MonitorConfig; this.validate(config);
        if (checkFields.some(k => config[k] !== m[k])) { this.close(m, 'configuration_changed', Date.now()); this.failures.delete(m.id); this.versions.set(m.id, (this.versions.get(m.id) ?? 1) + 1); Object.assign(m, { health_status: null, last_checked_at: null, last_http_status: null, last_latency_ms: null, freshness: 'no_data' }); }
        Object.assign(m, config); this.project(m.project_id).revision++; result = this.readMonitor(m);
      } else if (!action && method === 'DELETE') { this.close(m, 'archived', Date.now()); m.archived_at = iso(Date.now()); this.project(m.project_id).revision++; }
      else if ((action === 'pause' || action === 'resume') && method === 'POST') { if ((action === 'pause') !== Boolean(m.paused_at)) { m.paused_at = action === 'pause' ? iso(Date.now()) : null; this.failures.delete(m.id); this.versions.set(m.id, (this.versions.get(m.id) ?? 1) + 1); this.project(m.project_id).revision++; } result = this.readMonitor(m); }
      else if (action === 'checks' && method === 'GET') { const window = this.window(query); result = this.page(this.checks.filter(c => c.monitor_id === m.id && Date.parse(c.scheduled_at) >= window.from && Date.parse(c.scheduled_at) < window.to).sort((a, b) => Date.parse(b.scheduled_at) - Date.parse(a.scheduled_at)), query); }
      else if (action === 'metrics' && method === 'GET') result = this.metrics([m], query);
      else return fail();
    } else if (/^\/projects\/[^/]+\/(?:metrics|incidents|jobs)$/.test(route) && method === 'GET') {
      const [, , id, action] = route.split('/'); const monitors = this.active(id);
      if (action === 'metrics') result = this.metrics(monitors, query);
      else if (action === 'incidents') result = this.incidentPage(monitors, query, false);
      else { const window = this.window(query), ids = new Set(monitors.map(m => m.id)), status = query.get('status') ?? 'all', filter = query.get('monitor_id'); if (!['all', 'exhausted', 'expired'].includes(status)) fail(422, 'Situação inválida.'); if (filter && !ids.has(filter)) fail(); result = { ...this.page(this.jobs.filter(j => ids.has(j.monitor_id) && (!filter || j.monitor_id === filter) && (status === 'all' || j.status === status) && Date.parse(j.scheduled_at) >= window.from && Date.parse(j.scheduled_at) < window.to).sort((a, b) => Date.parse(b.scheduled_at) - Date.parse(a.scheduled_at)), query), from: iso(window.from), to: iso(window.to), computed_at: iso(Date.now()), retention_days: 30 }; }
    } else if (/^\/public\/status\/[^/]+(?:\/incidents)?$/.test(route) && method === 'GET') {
      const slug = decodeURIComponent(route.split('/')[3]); const p = this.projects.find(p => p.public_slug === slug && p.public_status_enabled && !p.archived_at) ?? fail();
      const monitors = this.active(p.id).filter(m => m.is_public).map(m => this.readMonitor(m));
      if (route.endsWith('/incidents')) result = this.incidentPage(monitors, query, true);
      else { const summary = summarize(monitors); result = { name: p.name, slug: p.public_slug, revision: p.revision, computed_at: iso(Date.now()), health_status: summary.health, data_complete: !summary.partial, freshness_counts: summary.counts, monitors: monitors.map(({ id, name, health_status, freshness, last_checked_at }) => ({ id, name, health_status, freshness, last_checked_at })) }; }
    } else if (/^\/demo\/monitors\/[^/]+\/simulate$/.test(route) && method === 'POST') {
      const m = this.monitor(route.split('/')[3]); if (m.paused_at) fail(409, 'Retome o monitor antes de simular uma verificação.');
      if (!['success', 'slow', 'retry', 'failure'].includes(String(input.scenario))) fail(422, 'Cenário inválido.');
      result = this.evaluate(m, input.scenario as DemoScenario, Date.now());
    } else return fail();
    signal?.throwIfAborted(); return structuredClone(result) as T;
  }
}
