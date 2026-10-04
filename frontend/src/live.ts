import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from './api';
import type { Session } from './types';

// Signals invalidate REST snapshots; they never become monitoring results.
export function useLiveUpdates(projectId: string, onRefresh: () => void, onProjectsChange: () => void, blocked = false) {
  const callbacks = useRef({ projectId, onRefresh, onProjectsChange, blocked });
  callbacks.current = { projectId, onRefresh, onProjectsChange, blocked };
  const flush = useRef<() => void>(() => {});
  const [connected, setConnected] = useState(false);
  useEffect(() => { if (!blocked) flush.current(); }, [blocked]);
  useEffect(() => {
    let alive = true;
    let refreshPending = false;
    let projectsPending = false;
    let debounce: ReturnType<typeof setTimeout> | undefined;
    let sessionProbe: AbortController | undefined;
    const drain = () => {
      if (!alive || callbacks.current.blocked) return;
      if (refreshPending) {
        refreshPending = false; projectsPending = false; callbacks.current.onRefresh();
      } else if (projectsPending) {
        projectsPending = false; callbacks.current.onProjectsChange();
      }
    };
    flush.current = drain;
    const invalidate = (projectsOnly = false) => {
      if (!alive) return;
      if (projectsOnly) projectsPending = true; else refreshPending = true;
      if (debounce) return;
      debounce = setTimeout(() => {
        debounce = undefined;
        drain();
      }, 200);
    };
    let source: EventSource | null = null;
    try { if (typeof EventSource !== 'undefined') source = new EventSource('/api/v1/events'); } catch { /* REST polling remains available. */ }
    if (source) {
      const stream = source;
      stream.onopen = () => { if (alive) { setConnected(true); invalidate(); } };
      stream.onerror = () => {
        if (!alive) return;
        setConnected(false); sessionProbe?.abort(); sessionProbe = new AbortController();
        const probe = sessionProbe;
        api.request<Session>('/auth/me', 'GET', undefined, probe.signal).then(session => {
          if (alive && !probe.signal.aborted) api.setCsrfToken(session.csrf_token);
        }).catch(error => {
          if (alive && !probe.signal.aborted && error instanceof ApiError && error.status === 401) {
            stream.close(); api.setCsrfToken(null); api.onUnauthorized?.();
          }
        });
      };
      stream.addEventListener('snapshot.required', () => invalidate());
      const signal = (event: Event) => {
        if (!alive) return;
        try {
          const payload = JSON.parse((event as MessageEvent).data);
          if (typeof payload?.project_id !== 'string') { invalidate(); return; }
          if (payload.project_id === callbacks.current.projectId) invalidate();
          else if (event.type === 'project.updated') invalidate(true);
        } catch { invalidate(); }
      };
      for (const kind of ['project.updated', 'monitor.updated', 'incident.opened', 'incident.closed']) source.addEventListener(kind, signal);
    }
    // Also catches silent streams and unavailable EventSource implementations.
    const fallback = setInterval(() => invalidate(), 30000);
    const visible = () => { if (document.visibilityState === 'visible') invalidate(); };
    document.addEventListener('visibilitychange', visible);
    return () => {
      alive = false; source?.close(); sessionProbe?.abort(); clearInterval(fallback); clearTimeout(debounce);
      flush.current = () => {};
      document.removeEventListener('visibilitychange', visible);
    };
  }, []);
  return connected;
}
