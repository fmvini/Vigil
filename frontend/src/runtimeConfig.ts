import { useApi } from './transport';
import { useEffect, useState } from 'react';

export interface RuntimeConfig {
  minimum_interval_seconds: number;
  scheduled_checks_interval_seconds: number | null;
}

export function parseRuntimeConfig(value: unknown): RuntimeConfig {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error('RUNTIME_CONFIG_INVALID');
  const fields = value as Record<string, unknown>;
  const minimum = fields.minimum_interval_seconds;
  const scheduled = fields.scheduled_checks_interval_seconds;
  if (Object.keys(fields).sort().join(',') !== 'minimum_interval_seconds,scheduled_checks_interval_seconds'
    || typeof minimum !== 'number' || !Number.isSafeInteger(minimum) || minimum < 60 || minimum > 3600
    || (scheduled !== null && (typeof scheduled !== 'number' || !Number.isSafeInteger(scheduled) || scheduled < 1))) {
    throw new Error('RUNTIME_CONFIG_INVALID');
  }
  return { minimum_interval_seconds: minimum, scheduled_checks_interval_seconds: scheduled as number | null };
}

export function scheduledCadence(scheduled: number): string {
  return scheduled % 60 === 0 ? `${scheduled / 60} ${scheduled === 60 ? 'minuto' : 'minutos'}` : `${scheduled} ${scheduled === 1 ? 'segundo' : 'segundos'}`;
}

export function intervalHelp(runtime: RuntimeConfig): string {
  const minimum = `Intervalo mínimo: ${runtime.minimum_interval_seconds} segundos.`;
  const scheduled = runtime.scheduled_checks_interval_seconds;
  if (scheduled === null) return `${minimum} Tempo entre ciclos.`;
  return `${minimum} As verificações são agendadas aproximadamente a cada ${scheduledCadence(scheduled)} e podem atrasar por horas, inclusive a primeira medição. O intervalo não garante um prazo de execução. Intervalos maiores continuam sendo respeitados.`;
}

export function useRuntimeConfig() {
  const api = useApi();
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ data: RuntimeConfig | null; loading: boolean; failed: boolean }>({ data: null, loading: true, failed: false });
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = window.setTimeout(() => {
      if (!active) return;
      controller.abort();
      setState({ data: null, loading: false, failed: true });
    }, 10_000);
    void (async () => {
      try {
        // This anonymous read has no private-session 401 side effects.
        const data = parseRuntimeConfig(await api.request<unknown>('/runtime-config', 'GET', undefined, controller.signal));
        if (active && !controller.signal.aborted) setState({ data, loading: false, failed: false });
      } catch {
        if (active && !controller.signal.aborted) setState({ data: null, loading: false, failed: true });
      } finally { window.clearTimeout(timeout); }
    })();
    return () => { active = false; window.clearTimeout(timeout); controller.abort(); };
  }, [attempt, api]);
  function retry() {
    setState({ data: null, loading: true, failed: false });
    setAttempt(value => value + 1);
  }
  return { ...state, retry };
}
