import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useLiveUpdates } from '../live';
import { api } from '../api';
import { json } from './fixtures';

class FakeSource extends EventTarget {
  static instances: FakeSource[] = [];
  static CONNECTING = 0; static OPEN = 1; static CLOSED = 2;
  readyState = FakeSource.OPEN;
  onopen?: () => void; onerror?: () => void; close = vi.fn();
  constructor(public url: string) { super(); FakeSource.instances.push(this); }
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); FakeSource.instances = []; api.onUnauthorized = undefined; });

it('usa cookie sem query, filtra por projeto, refaz snapshot e fecha no unmount', async () => {
  vi.useFakeTimers(); vi.stubGlobal('EventSource', FakeSource); const refresh = vi.fn(), projects = vi.fn();
  const view = renderHook(() => useLiveUpdates('p1', refresh, projects)); const source = FakeSource.instances[0]; expect(source.url).toBe('/api/v1/events');
  act(() => { source.dispatchEvent(new MessageEvent('monitor.updated', { data: JSON.stringify({ project_id: 'p2', revision: 2 }) })); });
  await act(async () => { await vi.advanceTimersByTimeAsync(250); }); expect(refresh).not.toHaveBeenCalled();
  act(() => { source.dispatchEvent(new MessageEvent('project.updated', { data: JSON.stringify({ project_id: 'p2', revision: 3 }) })); });
  await act(async () => { await vi.advanceTimersByTimeAsync(250); }); expect(projects).toHaveBeenCalledOnce();
  act(() => { source.dispatchEvent(new MessageEvent('snapshot.required', { data: '{}' })); source.dispatchEvent(new MessageEvent('monitor.updated', { data: JSON.stringify({ project_id: 'p1' }) })); });
  await act(async () => { await vi.advanceTimersByTimeAsync(250); }); expect(refresh).toHaveBeenCalledOnce();
  view.unmount(); expect(source.close).toHaveBeenCalledOnce(); await vi.advanceTimersByTimeAsync(60000); expect(refresh).toHaveBeenCalledOnce();
});
it('mantém fallback REST a cada 30 segundos quando EventSource não existe', async () => {
  vi.useFakeTimers(); vi.stubGlobal('EventSource', undefined); const refresh = vi.fn();
  const view = renderHook(() => useLiveUpdates('p1', refresh, vi.fn()));
  await act(async () => { await vi.advanceTimersByTimeAsync(30200); }); expect(refresh).toHaveBeenCalledOnce(); view.unmount();
});
it('valida sessão após erro de stream e fecha/limpa em 401', async () => {
  vi.stubGlobal('EventSource', FakeSource); vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => json({ error: { code: 'unauthenticated', message: 'Expired' } }, 401)));
  const expired = vi.fn(); api.onUnauthorized = expired; const view = renderHook(() => useLiveUpdates('p1', vi.fn(), vi.fn()));
  await act(async () => { FakeSource.instances[0].onerror?.(); });
  expect(expired).toHaveBeenCalledOnce(); expect(FakeSource.instances[0].close).toHaveBeenCalled(); view.unmount();
});
it('reconcilia reconexão, snapshots e polling mesmo após sinais recentes', async () => {
  vi.useFakeTimers(); vi.stubGlobal('EventSource', FakeSource); const refresh = vi.fn();
  const view = renderHook(() => useLiveUpdates('p1', refresh, vi.fn())); const source = FakeSource.instances[0];
  act(() => { source.onopen?.(); source.dispatchEvent(new MessageEvent('snapshot.required', { data: '{"reason":"connected"}' })); });
  await act(async () => { await vi.advanceTimersByTimeAsync(200); }); expect(refresh).toHaveBeenCalledOnce(); expect(view.result.current).toBe(true);
  await act(async () => { await vi.advanceTimersByTimeAsync(29000); });
  act(() => { source.dispatchEvent(new MessageEvent('incident.opened', { data: '{"project_id":"p1","revision":2}' })); });
  await act(async () => { await vi.advanceTimersByTimeAsync(200); }); expect(refresh).toHaveBeenCalledTimes(2);
  await act(async () => { await vi.advanceTimersByTimeAsync(800); }); expect(refresh).toHaveBeenCalledTimes(3);
  act(() => source.onopen?.()); await act(async () => { await vi.advanceTimersByTimeAsync(200); }); expect(refresh).toHaveBeenCalledTimes(4);
  view.unmount();
});
it('retém e agrupa invalidações durante edição e usa o projeto atual', async () => {
  vi.useFakeTimers(); vi.stubGlobal('EventSource', FakeSource); const refresh = vi.fn(), projects = vi.fn();
  const view = renderHook(({ id, blocked }) => useLiveUpdates(id, refresh, projects, blocked), { initialProps: { id: 'p1', blocked: true } });
  const source = FakeSource.instances[0];
  act(() => {
    source.dispatchEvent(new MessageEvent('project.updated', { data: '{"project_id":"p2"}' }));
    source.dispatchEvent(new MessageEvent('snapshot.required', { data: '{"reason":"backpressure"}' }));
    source.dispatchEvent(new MessageEvent('monitor.updated', { data: '{"project_id":"p1"}' }));
  });
  await act(async () => { await vi.advanceTimersByTimeAsync(300); }); expect(refresh).not.toHaveBeenCalled(); expect(projects).not.toHaveBeenCalled();
  view.rerender({ id: 'p2', blocked: false }); expect(refresh).toHaveBeenCalledOnce(); expect(projects).not.toHaveBeenCalled();
  act(() => source.dispatchEvent(new MessageEvent('incident.closed', { data: '{"project_id":"p1"}' })));
  await act(async () => { await vi.advanceTimersByTimeAsync(200); }); expect(refresh).toHaveBeenCalledOnce();
  act(() => source.dispatchEvent(new MessageEvent('incident.closed', { data: '{"project_id":"p2"}' })));
  await act(async () => { await vi.advanceTimersByTimeAsync(200); }); expect(refresh).toHaveBeenCalledTimes(2); expect(FakeSource.instances).toHaveLength(1);
  view.unmount();
});
it('volta de aba oculta e tolera sinais inválidos e construtor indisponível', async () => {
  vi.useFakeTimers(); vi.stubGlobal('EventSource', FakeSource); const refresh = vi.fn();
  const view = renderHook(() => useLiveUpdates('p1', refresh, vi.fn()));
  act(() => {
    document.dispatchEvent(new Event('visibilitychange'));
    FakeSource.instances[0].dispatchEvent(new MessageEvent('monitor.updated', { data: 'null' }));
    FakeSource.instances[0].dispatchEvent(new MessageEvent('incident.opened', { data: 'invalid-json' }));
  });
  await act(async () => { await vi.advanceTimersByTimeAsync(200); }); expect(refresh).toHaveBeenCalledOnce(); view.unmount();
  vi.stubGlobal('EventSource', class { constructor() { throw new Error('unavailable'); } });
  const fallback = renderHook(() => useLiveUpdates('p1', refresh, vi.fn()));
  await act(async () => { await vi.advanceTimersByTimeAsync(30200); }); expect(refresh).toHaveBeenCalledTimes(2); fallback.unmount();
});
it('cancela probes antigos e ignora 401 recebido depois do unmount', async () => {
  vi.stubGlobal('EventSource', FakeSource);
  const completions: ((response: Response) => void)[] = []; const signals: AbortSignal[] = [];
  vi.stubGlobal('fetch', vi.fn((_url: string, init: RequestInit) => { signals.push(init.signal as AbortSignal); return new Promise<Response>(resolve => completions.push(resolve)); }));
  const expired = vi.fn(); api.onUnauthorized = expired; const view = renderHook(() => useLiveUpdates('p1', vi.fn(), vi.fn()));
  act(() => { FakeSource.instances[0].onerror?.(); FakeSource.instances[0].onerror?.(); });
  expect(signals[0].aborted).toBe(true); view.unmount(); expect(signals[1].aborted).toBe(true);
  await act(async () => { completions.forEach(resolve => resolve(json({}, 401))); }); expect(expired).not.toHaveBeenCalled();
});

it('recria somente fontes CLOSED com espera limitada e reinicia a espera após abrir', async () => {
  vi.useFakeTimers(); vi.stubGlobal('EventSource', FakeSource);
  vi.stubGlobal('fetch', vi.fn(async () => json({ csrf_token: 'qa' })));
  const view = renderHook(() => useLiveUpdates('p1', vi.fn(), vi.fn()));
  const first = FakeSource.instances[0];
  first.readyState = FakeSource.CONNECTING;
  await act(async () => { first.onerror?.(); await vi.advanceTimersByTimeAsync(2500); });
  expect(FakeSource.instances).toHaveLength(1);
  for (const delay of [2000, 4000, 8000, 16000, 30000, 30000]) {
    const source = FakeSource.instances.at(-1)!; source.readyState = FakeSource.CLOSED;
    const count = FakeSource.instances.length;
    await act(async () => { source.onerror?.(); source.onerror?.(); await vi.advanceTimersByTimeAsync(delay - 1); });
    expect(FakeSource.instances).toHaveLength(count);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(FakeSource.instances).toHaveLength(count + 1); expect(source.close).toHaveBeenCalledOnce();
  }
  const recovered = FakeSource.instances.at(-1)!;
  act(() => recovered.onopen?.()); expect(view.result.current).toBe(true);
  recovered.readyState = FakeSource.CLOSED;
  await act(async () => { recovered.onerror?.(); await vi.advanceTimersByTimeAsync(1999); });
  expect(FakeSource.instances).toHaveLength(7);
  await act(async () => { await vi.advanceTimersByTimeAsync(1); }); expect(FakeSource.instances).toHaveLength(8);
  const last = FakeSource.instances.at(-1)!; last.readyState = FakeSource.CLOSED;
  act(() => last.onerror?.()); view.unmount();
  await vi.advanceTimersByTimeAsync(60000); expect(FakeSource.instances).toHaveLength(8);
});

it('401 cancela a recriação de uma fonte CLOSED', async () => {
  vi.useFakeTimers(); vi.stubGlobal('EventSource', FakeSource);
  vi.stubGlobal('fetch', vi.fn(async () => json({}, 401)));
  const expired = vi.fn(); api.onUnauthorized = expired;
  const view = renderHook(() => useLiveUpdates('p1', vi.fn(), vi.fn()));
  const source = FakeSource.instances[0]; source.readyState = FakeSource.CLOSED;
  await act(async () => { source.onerror?.(); await vi.advanceTimersByTimeAsync(60000); });
  expect(expired).toHaveBeenCalledOnce(); expect(FakeSource.instances).toHaveLength(1);
  expect(source.close).toHaveBeenCalledOnce(); view.unmount();
});

it('descarta callbacks e 401 atrasado da fonte substituída', async () => {
  vi.useFakeTimers(); vi.stubGlobal('EventSource', FakeSource);
  let complete!: (response: Response) => void; let probe!: AbortSignal;
  vi.stubGlobal('fetch', vi.fn((_url: string, init: RequestInit) => {
    probe = init.signal as AbortSignal; return new Promise<Response>(resolve => { complete = resolve; });
  }));
  const refresh = vi.fn(), expired = vi.fn(); api.onUnauthorized = expired;
  const view = renderHook(() => useLiveUpdates('p1', refresh, vi.fn()));
  const old = FakeSource.instances[0]; old.readyState = FakeSource.CLOSED;
  await act(async () => { old.onerror?.(); await vi.advanceTimersByTimeAsync(2000); });
  expect(probe.aborted).toBe(true);
  await act(async () => {
    old.onopen?.(); old.onerror?.();
    old.dispatchEvent(new MessageEvent('snapshot.required', { data: '{}' }));
    complete(json({}, 401)); await vi.advanceTimersByTimeAsync(200);
  });
  expect(expired).not.toHaveBeenCalled(); expect(refresh).not.toHaveBeenCalled();
  expect(view.result.current).toBe(false); expect(FakeSource.instances).toHaveLength(2);
  act(() => FakeSource.instances[1].onopen?.());
  await act(async () => { await vi.advanceTimersByTimeAsync(200); });
  expect(refresh).toHaveBeenCalledOnce(); expect(view.result.current).toBe(true); view.unmount();
});
