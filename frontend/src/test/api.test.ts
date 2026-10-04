import { describe, expect, it, vi, afterEach } from 'vitest';
import { ApiClient, ApiError, errorMessage } from '../api';
import { json } from './fixtures';
afterEach(() => vi.unstubAllGlobals());

describe('contrato HTTP e sessão', () => {
  it('envia cookie same-origin e cabeçalhos de proteção só nas mutações', async () => {
    const fetch = vi.fn().mockResolvedValue(json({ ok: true })); vi.stubGlobal('fetch', fetch);
    const api = new ApiClient(); api.setCsrfToken('csrf-real');
    await api.request('/projects', 'POST', { name: 'Projeto' });
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe('/api/v1/projects'); expect(init.credentials).toBe('same-origin');
    expect(init.headers.get('X-Vigil-Request')).toBe('browser');
    expect(init.headers.get('X-CSRF-Token')).toBe('csrf-real');
    expect(init.headers.get('Content-Type')).toBe('application/json');
    expect(JSON.parse(init.body)).toEqual({ name: 'Projeto' });
    fetch.mockResolvedValue(json({})); await api.request('/projects');
    expect(fetch.mock.calls[1][1].headers.has('X-CSRF-Token')).toBe(false);
  });
  it('aceita 204, preserva erros estruturados e invalida autenticação em 401', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(json({ error: { code: 'unauthenticated', message: 'Expired', details: null } }, 401));
    vi.stubGlobal('fetch', fetch); const api = new ApiClient(); const expired = vi.fn(); api.onUnauthorized = expired;
    expect(await api.request('/auth/logout', 'POST')).toBeUndefined();
    await expect(api.request('/projects')).rejects.toMatchObject({ status: 401, code: 'unauthenticated' });
    expect(expired).toHaveBeenCalledOnce();
  });
  it('carrega todas as páginas sem apresentar contagem parcial como total', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json({ items: ['a', 'b'], total: 3 }))
      .mockResolvedValueOnce(json({ items: ['c'], total: 3 })); vi.stubGlobal('fetch', fetch);
    expect(await new ApiClient().list('/projects')).toEqual(['a', 'b', 'c']);
    expect(fetch.mock.calls[1][0]).toBe('/api/v1/projects?limit=100&offset=2');
  });
  it('mostra campos de validação sem repetir dados sensíveis do input', () => {
    const error = new ApiError(422, 'validation_error', 'Request validation failed', [{ field: 'body.password', type: 'string_too_short' }]);
    expect(errorMessage(error)).toBe('Revise os campos: senha.');
  });
  it('não invalida sessão por 401 de leitura cancelada ou de sessão anterior', async () => {
    let resolve: (response: Response) => void = () => {};
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(done => { resolve = done; })));
    const api = new ApiClient(); const expired = vi.fn(); api.onUnauthorized = expired;
    const controller = new AbortController();
    const cancelled = api.request('/projects', 'GET', undefined, controller.signal);
    controller.abort(); resolve(json({}, 401));
    await expect(cancelled).rejects.toMatchObject({ name: 'AbortError' });
    api.setCsrfToken('old');
    const previousSession = api.request('/projects');
    api.setCsrfToken('new'); resolve(json({}, 401));
    await expect(previousSession).rejects.toMatchObject({ status: 401 });
    expect(expired).not.toHaveBeenCalled();
    const fetch = vi.fn().mockResolvedValue(json({})); vi.stubGlobal('fetch', fetch);
    await api.request('/projects', 'POST', {});
    expect(fetch.mock.calls[0][1].headers.get('X-CSRF-Token')).toBe('new');
  });
  it('ignora corpo de sucesso concluído depois do cancelamento e 401 público', async () => {
    let finishBody: (data: unknown) => void = () => {};
    const body = new Promise(resolve => { finishBody = resolve; });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => body }));
    const api = new ApiClient(); const expired = vi.fn(); api.onUnauthorized = expired;
    const controller = new AbortController(); const pending = api.request('/projects', 'GET', undefined, controller.signal);
    await Promise.resolve(); controller.abort(); finishBody({});
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({}, 401)));
    await expect(api.request('/public/status/slug')).rejects.toMatchObject({ status: 401 });
    expect(expired).not.toHaveBeenCalled();
  });
});
