import type { Metrics, Monitor, Project } from '../types';
export const project: Project = { id: 'p1', name: 'Aplicação', description: 'Ambiente de produção', archived_at: null, public_slug: 'aplicacao-qa', public_status_enabled: false, revision: 0 };
export const monitor: Monitor = {
  id: 'm1', project_id: 'p1', name: 'API principal', url: 'https://example.com/health',
  interval_seconds: 60, timeout_ms: 5000, expected_status: 200, failure_threshold: 3,
  retry_count: 1, latency_threshold_ms: 1000, is_public: false, paused_at: null, archived_at: null,
  health_status: null, freshness: 'no_data', last_checked_at: null, last_http_status: null, last_latency_ms: null,
};
export function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
}
export const emptyMetrics: Metrics = {
  from: '2026-10-03T12:00:00Z', to: '2026-10-04T12:00:00Z', computed_at: '2026-10-04T12:00:00Z',
  success_count: 0, failure_count: 0, sample_count: 0, latency_sample_count: 0,
  uptime_percent: null, average_latency_ms: null, p95_latency_ms: null,
  excluded_count: 0, cancelled_count: 0, pending_count: 0, skipped_slots: 0,
  health_status: null, data_complete: false, freshness_counts: { no_data: 1, stale: 0, fresh: 0, paused: 0 },
  bucket_seconds: 3600, series: [],
};
export function observationResponse(url: unknown) {
  const path = String(url).split('?')[0];
  if (path.endsWith('/runtime-config')) return json({ minimum_interval_seconds: 60, scheduled_checks_interval_seconds: null });
  if (path.endsWith('/metrics')) return json(emptyMetrics);
  if (path.endsWith('/incidents')) return json({ items: [], total: 0 });
  return null;
}
