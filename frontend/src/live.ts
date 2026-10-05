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
    let reconnect: ReturnType<typeof setTimeout> | undefined;
    let reconnectAttempts = 0;
    let revoked = false;
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
    const retryClosed = () => {
      if (!alive || revoked || reconnect || typeof EventSource === 'undefined') return;
      const delay = Math.min(2000 * 2 ** Math.min(reconnectAttempts++, 4), 30000);
      reconnect = setTimeout(() => { reconnect = undefined; connect(); }, delay);
    };
    const connect = () => {
      if (!alive || revoked || typeof EventSource === 'undefined') return;
      sessionProbe?.abort();
      source?.close(); source = null;
      try { source = new EventSource('/api/v1/events'); }
      catch { retryClosed(); return; }
      const stream = source;
      const current = () => alive && source === stream && !revoked;
      stream.onopen = () => {
        if (!current()) return;
        clearTimeout(reconnect); reconnect = undefined; reconnectAttempts = 0;
        setConnected(true); invalidate();
      };
      stream.onerror = () => {
        if (!current()) return;
        setConnected(false); sessionProbe?.abort(); sessionProbe = new AbortController();
        // CONNECTING already has native retries. HTTP errors can leave the
        // native source CLOSED permanently; recreate only that terminal state.
        if (stream.readyState === EventSource.CLOSED) retryClosed();
        const probe = sessionProbe;
        api.request<Session>('/auth/me', 'GET', undefined, probe.signal).then(session => {
          if (current() && !probe.signal.aborted) api.setCsrfToken(session.csrf_token);
        }).catch(error => {
          if (current() && !probe.signal.aborted && error instanceof ApiError && error.status === 401) {
            revoked = true; clearTimeout(reconnect); reconnect = undefined;
            stream.close(); api.setCsrfToken(null); api.onUnauthorized?.();
          }
        });
      };
      stream.addEventListener('snapshot.required', () => { if (current()) invalidate(); });
      const signal = (event: Event) => {
        if (!current()) return;
        try {
          const payload = JSON.parse((event as MessageEvent).data);
          if (typeof payload?.project_id !== 'string') { invalidate(); return; }
          if (payload.project_id === callbacks.current.projectId) invalidate();
          else if (event.type === 'project.updated') invalidate(true);
        } catch { invalidate(); }
      };
      for (const kind of ['project.updated', 'monitor.updated', 'incident.opened', 'incident.closed']) stream.addEventListener(kind, signal);
    };
    connect();
    // Also catches silent streams and unavailable EventSource implementations.
    const fallback = setInterval(() => invalidate(), 30000);
    const visible = () => { if (document.visibilityState === 'visible') invalidate(); };
    document.addEventListener('visibilitychange', visible);
    return () => {
      alive = false; source?.close(); sessionProbe?.abort(); clearInterval(fallback); clearTimeout(debounce); clearTimeout(reconnect);
      flush.current = () => {};
      document.removeEventListener('visibilitychange', visible);
    };
  }, []);
  return connected;
}
