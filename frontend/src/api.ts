import type { Page } from './types';

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details: unknown = null) {
    super(message);
    this.name = 'ApiError';
  }
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'validation_error') {
      const labels: Record<string, string> = { email: 'e-mail', password: 'senha', name: 'nome', url: 'URL', interval_seconds: 'intervalo', timeout_ms: 'timeout', expected_status: 'status esperado', failure_threshold: 'limite de falhas', retry_count: 'tentativas extras', latency_threshold_ms: 'limiar de latência', description: 'descrição' };
      const fields = Array.isArray(error.details) ? error.details.map(detail => labels[String(detail?.field).split('.').at(-1) ?? '']).filter(Boolean) : [];
      return fields.length ? `Revise os campos: ${[...new Set(fields)].join(', ')}.` : 'Revise a configuração informada. A API rejeitou os valores enviados.';
    }
    if (error.code === 'unauthenticated') return 'E-mail ou senha inválidos, ou sua sessão expirou. Tente entrar novamente.';
    if (error.code === 'quota_exceeded') return 'O limite de projetos ou monitores foi atingido. Arquive um item antes de criar outro.';
    if (error.code === 'not_found') return 'Este item não está disponível. Atualize a lista e tente novamente.';
    if (error.code === 'conflict') return 'Não foi possível salvar: já existe um cadastro com estes dados.';
    if (error.code === 'database_unavailable' || error.status >= 500) return 'O serviço está temporariamente indisponível. Tente novamente em instantes.';
    if (error.status === 403) return `${error.message} Atualize a página para renovar a sessão e tente novamente.`;
    return error.message;
  }
  return 'Não foi possível conectar ao Vigil. Verifique sua conexão e tente novamente.';
}

export class ApiClient {
  private csrfToken: string | null = null;
  private sessionVersion = 0;
  onUnauthorized?: () => void;
  setCsrfToken(token: string | null) { if (token !== this.csrfToken) this.sessionVersion++; this.csrfToken = token; }

  async request<T>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
    const sessionVersion = this.sessionVersion;
    const headers = new Headers({ Accept: 'application/json' });
    if (method !== 'GET') {
      headers.set('X-Vigil-Request', 'browser');
      if (this.csrfToken) headers.set('X-CSRF-Token', this.csrfToken);
      if (body !== undefined) headers.set('Content-Type', 'application/json');
    }
    const response = await fetch(`/api/v1${path}`, {
      method, headers, credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body), signal,
    });
    signal?.throwIfAborted();
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      signal?.throwIfAborted();
      const error = payload?.error;
      if (response.status === 401 && !path.startsWith('/auth/') && !path.startsWith('/public/') && sessionVersion === this.sessionVersion) {
        this.setCsrfToken(null);
        this.onUnauthorized?.();
      }
      throw new ApiError(response.status, error?.code ?? 'http_error', error?.message ?? `A solicitação falhou (HTTP ${response.status}).`, error?.details);
    }
    if (response.status === 204) return undefined as T;
    const data = await response.json() as T;
    signal?.throwIfAborted();
    return data;
  }

  async list<T>(path: string, signal?: AbortSignal): Promise<T[]> {
    const items: T[] = [];
    let total = Infinity;
    while (items.length < total) {
      const page = await this.request<Page<T>>(`${path}?limit=100&offset=${items.length}`, 'GET', undefined, signal);
      items.push(...page.items);
      total = page.total;
      if (page.items.length === 0) break;
    }
    return items;
  }
}
export const api = new ApiClient();
