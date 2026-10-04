import type { Freshness, Health, Monitor, MonitorConfig } from './types';

export const freshnessLabels: Record<Freshness, string> = {
  no_data: 'Sem dados', fresh: 'Atualizados', stale: 'Desatualizados', paused: 'Pausado',
};
export const healthLabels = { online: 'Online', degraded: 'Degradado', offline: 'Offline' };

export function currentFreshness(monitor: Monitor, now = Date.now()): Freshness {
  if (monitor.paused_at || monitor.freshness === 'paused') return 'paused';
  if (!monitor.last_checked_at || monitor.freshness === 'no_data') return 'no_data';
  if (monitor.freshness === 'stale' || now - Date.parse(monitor.last_checked_at) > Math.max(2 * monitor.interval_seconds, 120) * 1000) return 'stale';
  return 'fresh';
}

export function summarize(monitors: Monitor[], now = Date.now()) {
  const counts: Record<Freshness, number> = { fresh: 0, no_data: 0, stale: 0, paused: 0 };
  for (const monitor of monitors) counts[currentFreshness(monitor, now)]++;
  const eligible = monitors.filter(m => currentFreshness(m, now) === 'fresh' && m.health_status !== null);
  const health: Health | null = eligible.some(m => m.health_status === 'offline') ? 'offline'
    : eligible.some(m => m.health_status === 'degraded') ? 'degraded'
    : eligible.length ? 'online' : null;
  return { counts, health, partial: counts.no_data + counts.stale > 0 };
}

export const defaultConfig: MonitorConfig = {
  name: '', url: '', interval_seconds: 60, timeout_ms: 5000, expected_status: 200,
  failure_threshold: 3, retry_count: 1, latency_threshold_ms: 1000, is_public: false,
};

export function validateMonitor(config: MonitorConfig): string | null {
  try {
    const url = new URL(config.url);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.hash || (url.port && !['80', '443'].includes(url.port))) {
      return 'Use uma URL HTTP ou HTTPS, porta 80/443, sem credenciais ou fragmentos.';
    }
  } catch { return 'Informe uma URL HTTP ou HTTPS válida.'; }
  if (config.latency_threshold_ms !== null && config.latency_threshold_ms > config.timeout_ms) return 'O limiar de latência deve ser menor ou igual ao timeout.';
  const backoff = config.retry_count === 2 ? 1800 : config.retry_count === 1 ? 600 : 0;
  const budget = (config.retry_count + 1) * config.timeout_ms + backoff + 3000;
  if (budget > 50000 || budget >= config.interval_seconds * 1000) return 'Reduza o timeout ou as tentativas: o ciclo deve caber em 50 segundos e ser menor que o intervalo.';
  return null;
}
