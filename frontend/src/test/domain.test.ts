import { describe, expect, it } from 'vitest';
import { currentFreshness, summarize, validateMonitor } from '../domain';
import { monitor } from './fixtures';

describe('qualidade dos dados separada da saúde', () => {
  const now = Date.parse('2026-10-04T12:00:00Z');
  const fresh = { ...monitor, health_status: 'online' as const, freshness: 'fresh' as const, last_checked_at: '2026-10-04T11:59:30Z' };
  it('nunca produz saúde online para um projeto sem medição', () => {
    expect(summarize([monitor], now)).toEqual({ counts: { no_data: 1, stale: 0, paused: 0, fresh: 0 }, health: null, partial: true });
    expect(summarize([], now).health).toBeNull();
  });
  it('pausa prevalece sem apagar a saúde histórica', () => {
    const paused = { ...fresh, paused_at: '2026-10-04T11:59:50Z', health_status: 'offline' as const };
    expect(currentFreshness(paused, now)).toBe('paused');
    expect(summarize([paused], now).health).toBeNull();
    expect(paused.health_status).toBe('offline');
  });
  it('exclui stale e dados ausentes do agregado, e sinaliza resumo parcial', () => {
    const stale = { ...fresh, health_status: 'offline' as const, last_checked_at: '2026-10-04T11:57:59Z' };
    expect(currentFreshness(stale, now)).toBe('stale');
    expect(summarize([fresh, stale, monitor], now)).toMatchObject({ health: 'online', partial: true, counts: { stale: 1, no_data: 1 } });
    expect(currentFreshness({ ...fresh, last_checked_at: '2026-10-04T11:58:00Z' }, now)).toBe('fresh');
  });
  it('aplica prioridade offline e degraded apenas em leituras atuais', () => {
    expect(summarize([fresh, { ...fresh, health_status: 'degraded' }], now).health).toBe('degraded');
    expect(summarize([fresh, { ...fresh, health_status: 'offline' }], now).health).toBe('offline');
  });
});

describe('validação de configuração', () => {
  it('aceita defaults e latência desligada', () => {
    expect(validateMonitor(monitor)).toBeNull();
    expect(validateMonitor({ ...monitor, latency_threshold_ms: null })).toBeNull();
  });
  it('rejeita URL com credenciais, porta indevida e fragmento', () => {
    for (const url of ['https://user:pass@example.com', 'https://example.com:8000', 'https://example.com/#token', 'ftp://example.com']) expect(validateMonitor({ ...monitor, url })).not.toBeNull();
  });
  it('rejeita orçamento excessivo e limiar maior que timeout', () => {
    expect(validateMonitor({ ...monitor, timeout_ms: 15000, retry_count: 2 })).toBeNull();
    expect(validateMonitor({ ...monitor, latency_threshold_ms: 6000 })).toContain('timeout');
    expect(validateMonitor({ ...monitor, timeout_ms: 16000, retry_count: 2 })).toContain('50 segundos');
  });
});
