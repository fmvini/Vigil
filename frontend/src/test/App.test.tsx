import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { api } from '../api';
import { json, monitor, project, observationResponse } from './fixtures';

afterEach(() => { vi.unstubAllGlobals(); api.setCsrfToken(null); });
const session = { user: { id: 'u1', email: 'tester@example.com' }, csrf_token: 'csrf-test' };
function path(input: unknown) { return String(input).replace('/api/v1', '').split('?')[0]; }

describe('fluxos reais da interface com transporte isolado no teste', () => {
  it('cadastra sem autenticar, limpa a senha e exige login explícito', async () => {
    const user = userEvent.setup();
    const fetch = vi.fn(async (url: unknown) => {
      const observation = observationResponse(url); if (observation) return observation;
      if (path(url) === '/auth/me') return json({ error: { code: 'unauthenticated', message: 'No session' } }, 401);
      if (path(url) === '/auth/register') return json(session.user, 201);
      throw new Error(`Unexpected request ${url}`);
    }); vi.stubGlobal('fetch', fetch); render(<App />);
    await user.click(await screen.findByRole('button', { name: 'Criar uma conta' }));
    await user.type(screen.getByLabelText('E-mail'), 'tester@example.com');
    await user.type(screen.getByLabelText('Senha'), 'password1234');
    await user.click(screen.getByRole('checkbox', { name: /Política de Privacidade/ }));
    await user.click(screen.getByRole('checkbox', { name: /Termos de Uso/ }));
    await user.click(screen.getByRole('button', { name: 'Criar conta' }));
    expect(await screen.findByText('Conta criada. Entre com seu e-mail e senha.')).toBeVisible();
    expect(screen.getByLabelText('Senha')).toHaveValue('');
    expect(screen.getByRole('checkbox', { name: /Política de Privacidade/ })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: /Termos de Uso/ })).not.toBeChecked();
    expect(fetch.mock.calls.filter(([url]) => path(url) === '/auth/login')).toHaveLength(0);
    expect(screen.queryByRole('heading', { name: 'Monitores' })).not.toBeInTheDocument();
  });
  it('restaura cookie, mostra sem dados, pausa/retoma e arquiva após confirmação', async () => {
    const user = userEvent.setup();
    let savedMonitor = monitor;
    let archived = false;
    const fetch = vi.fn(async (url: unknown, init?: RequestInit) => {
      const observation = observationResponse(url); if (observation) return observation;
      if (path(url) === '/auth/me') return json(session);
      if (path(url) === '/projects') return json({ items: [project], total: 1 });
      if (path(url) === '/projects/p1/monitors') return json({ items: archived ? [] : [savedMonitor], total: archived ? 0 : 1 });
      if (path(url) === '/monitors/m1/pause') { savedMonitor = { ...monitor, paused_at: new Date().toISOString(), freshness: 'paused' }; return json(savedMonitor); }
      if (path(url) === '/monitors/m1/resume') { savedMonitor = monitor; return json(savedMonitor); }
      if (path(url) === '/monitors/m1' && init?.method === 'DELETE') { archived = true; return new Response(null, { status: 204 }); }
      throw new Error(`Unexpected request ${url}`);
    }); vi.stubGlobal('fetch', fetch); render(<App />);
    expect(await screen.findByText('API principal')).toBeVisible();
    expect(screen.getByText('Ainda sem leitura')).toBeVisible();
    expect(screen.getByText('Não avaliada')).toBeVisible();
    expect(screen.queryByText('100%')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Pausar API principal' }));
    await user.click(await screen.findByRole('button', { name: 'Retomar API principal' }));
    await screen.findByRole('button', { name: 'Pausar API principal' });
    await user.click(screen.getByRole('button', { name: 'Arquivar API principal' }));
    expect(fetch.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Confirmar arquivamento' }));
    expect(await screen.findByText('Nenhum endpoint configurado')).toBeVisible();
    const [, init] = fetch.mock.calls.find(([url]) => path(url) === '/monitors/m1/pause')!;
    expect(new Headers(init?.headers).get('X-CSRF-Token')).toBe('csrf-test');
  });
  it('cria e edita projeto e monitor usando dados retornados pela API', async () => {
    const user = userEvent.setup();
    let savedProject: typeof project | null = null;
    let monitorCreated = false;
    let savedMonitor = { ...monitor, name: 'Endpoint criado' };
    const fetch = vi.fn(async (url: unknown, init?: RequestInit) => {
      const observation = observationResponse(url); if (observation) return observation;
      const route = path(url); const body = init?.body ? JSON.parse(String(init.body)) : null;
      if (route === '/auth/me') return json(session);
      if (route === '/projects' && init?.method === 'GET') return json({ items: savedProject ? [savedProject] : [], total: savedProject ? 1 : 0 });
      if (route === '/projects' && init?.method === 'POST') { savedProject = { ...project, ...body }; return json(savedProject, 201); }
      if (route === '/projects/p1') { savedProject = { ...savedProject, ...body }; return json(savedProject); }
      if (route === '/projects/p1/monitors' && init?.method === 'GET') return json({ items: monitorCreated ? [savedMonitor] : [], total: monitorCreated ? 1 : 0 });
      if (route === '/projects/p1/monitors' || route === '/monitors/m1') { monitorCreated = true; savedMonitor = { ...savedMonitor, ...body }; return json(savedMonitor, route === '/monitors/m1' ? 200 : 201); }
      throw new Error(`Unexpected request ${url}`);
    }); vi.stubGlobal('fetch', fetch); render(<App />);
    await user.click(await screen.findByRole('button', { name: 'Criar primeiro projeto' }));
    await user.type(screen.getByLabelText('Nome do projeto'), 'Novo projeto');
    await user.click(screen.getByRole('button', { name: 'Salvar projeto' }));
    await user.click(await screen.findByRole('button', { name: 'Editar projeto' }));
    await user.clear(screen.getByLabelText('Nome do projeto')); await user.type(screen.getByLabelText('Nome do projeto'), 'Projeto editado');
    await user.click(screen.getByRole('button', { name: 'Salvar projeto' }));
    expect(await screen.findByRole('heading', { name: 'Projeto editado' })).toBeVisible();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Novo monitor' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Novo monitor' }));
    await user.type(await screen.findByLabelText('Nome do monitor'), 'Endpoint criado');
    await user.type(screen.getByLabelText('URL do endpoint'), 'https://example.com/health');
    await user.click(screen.getByRole('button', { name: 'Salvar monitor' }));
    await user.click(await screen.findByRole('button', { name: 'Editar Endpoint criado' }));
    await user.clear(await screen.findByLabelText('Nome do monitor')); await user.type(screen.getByLabelText('Nome do monitor'), 'Endpoint editado');
    await user.click(screen.getByRole('button', { name: 'Salvar monitor' }));
    expect(await screen.findByText('Endpoint editado')).toBeVisible();
    const request = fetch.mock.calls.find(([url, init]) => path(url) === '/monitors/m1' && init?.method === 'PATCH');
    expect(JSON.parse(String(request?.[1]?.body))).not.toHaveProperty('health_status');
  });
  it('mostra erro de carga e permite recuperar sem exibir números fictícios', async () => {
    let retry = false;
    vi.stubGlobal('fetch', vi.fn(async (url: unknown) => {
      const observation = observationResponse(url); if (observation) return observation;
      if (path(url) === '/auth/me') return json(session);
      if (path(url) === '/projects') return json({ items: [project], total: 1 });
      if (!retry) return json({ error: { code: 'database_unavailable', message: 'Unavailable' } }, 503);
      return json({ items: [monitor], total: 1 });
    })); render(<App />); const user = userEvent.setup();
    expect(await screen.findByRole('alert')).toHaveTextContent('temporariamente indisponível');
    expect(screen.queryByText('Ainda sem leitura')).not.toBeInTheDocument();
    retry = true; await user.click(screen.getByRole('button', { name: 'Tentar novamente' }));
    expect(await screen.findByText('API principal')).toBeVisible();
  });
  it('arquiva projeto apenas após confirmar e seleciona o próximo projeto', async () => {
    let archived = false;
    const fetch = vi.fn(async (url: unknown, init?: RequestInit) => {
      const observation = observationResponse(url); if (observation) return observation;
      if (path(url) === '/auth/me') return json(session);
      if (path(url) === '/projects') return json({ items: [...(archived ? [] : [project]), { ...project, id: 'p2', name: 'Projeto restante' }], total: archived ? 1 : 2 });
      if (path(url) === '/projects/p1' && init?.method === 'DELETE') { archived = true; return new Response(null, { status: 204 }); }
      return json({ items: [], total: 0 });
    }); vi.stubGlobal('fetch', fetch); render(<App />); const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Arquivar projeto' }));
    expect(fetch.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Confirmar arquivamento' }));
    expect(await screen.findByRole('heading', { name: 'Projeto restante' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Aplicação' })).not.toBeInTheDocument();
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => path(url) === '/projects/p2/monitors')).toBe(true));
  });
  it('não permite que a consulta de um projeto antigo sobrescreva o selecionado', async () => {
    let completeFirst: (response: Response) => void = () => {};
    vi.stubGlobal('fetch', vi.fn(async (url: unknown) => {
      const observation = observationResponse(url); if (observation) return observation;
      if (path(url) === '/auth/me') return json(session);
      if (path(url) === '/projects') return json({ items: [project, { ...project, id: 'p2', name: 'Outro projeto' }], total: 2 });
      if (path(url) === '/projects/p1/monitors') return new Promise<Response>(resolve => { completeFirst = resolve; });
      return json({ items: [{ ...monitor, id: 'm2', project_id: 'p2', name: 'Outro endpoint' }], total: 1 });
    })); render(<App />); const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Outro projeto' }));
    expect(await screen.findByText('Outro endpoint')).toBeVisible();
    completeFirst(json({ items: [monitor], total: 1 }));
    await waitFor(() => expect(screen.queryByText('API principal')).not.toBeInTheDocument());
    expect(within(screen.getByRole('table')).getByText('Outro endpoint')).toBeVisible();
  });
  it('bloqueia troca de projeto e logout enquanto salva um monitor', async () => {
    let finishSave: (response: Response) => void = () => {};
    vi.stubGlobal('fetch', vi.fn(async (url: unknown, init?: RequestInit) => {
      const observation = observationResponse(url); if (observation) return observation;
      if (path(url) === '/auth/me') return json(session);
      if (path(url) === '/projects') return json({ items: [project, { ...project, id: 'p2', name: 'Projeto B' }], total: 2 });
      if (path(url) === '/projects/p1/monitors' && init?.method === 'POST') return new Promise<Response>(resolve => { finishSave = resolve; });
      return json({ items: [], total: 0 });
    })); render(<App />); const user = userEvent.setup();
    const add = await screen.findByRole('button', { name: 'Novo monitor' });
    await waitFor(() => expect(add).toBeEnabled()); await user.click(add);
    await user.type(await screen.findByLabelText('Nome do monitor'), 'Salvamento lento');
    await user.type(screen.getByLabelText('URL do endpoint'), 'https://example.com/health');
    await user.click(screen.getByRole('button', { name: 'Salvar monitor' }));
    expect(screen.getByRole('button', { name: 'Projeto B' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Sair da conta' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Projeto B' }));
    expect(screen.getByRole('heading', { name: 'Aplicação' })).toBeVisible();
    finishSave(json({ ...monitor, name: 'Salvamento lento' }, 201));
    expect(await screen.findByText('Salvamento lento')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Projeto B' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Projeto B' }));
    await screen.findByText('Nenhum endpoint configurado');
    expect(screen.queryByText('Salvamento lento')).not.toBeInTheDocument();
  });
  it('cancela leitura anterior à edição e reconcilia sinais recebidos durante o salvamento', async () => {
    let source: EventTarget;
    vi.stubGlobal('EventSource', class extends EventTarget { close = vi.fn(); constructor() { super(); source = this; } });
    let completeRead: (response: Response) => void = () => {};
    let completeSave: (response: Response) => void = () => {};
    let readSignal: AbortSignal | undefined;
    let readCount = 0;
    let saved = project;
    const fetch = vi.fn(async (url: unknown, init?: RequestInit) => {
      const observation = observationResponse(url); if (observation) return observation;
      if (path(url) === '/auth/me') return json(session);
      if (path(url) === '/projects') return json({ items: [saved], total: 1 });
      if (path(url) === '/projects/p1' && init?.method === 'PATCH') return new Promise<Response>(resolve => { completeSave = resolve; });
      if (path(url) === '/projects/p1/monitors') {
        readCount++;
        if (readCount === 2) { readSignal = init?.signal as AbortSignal; return new Promise<Response>(resolve => { completeRead = resolve; }); }
        return json({ items: [monitor], total: 1 });
      }
      throw new Error(`Unexpected request ${url}`);
    }); vi.stubGlobal('fetch', fetch); render(<App />); const user = userEvent.setup();
    await screen.findByText('API principal'); await user.click(screen.getByRole('button', { name: 'Atualizar' }));
    await waitFor(() => expect(readCount).toBe(2));
    await user.click(screen.getByRole('button', { name: 'Editar projeto' })); expect(readSignal?.aborted).toBe(true);
    await user.clear(screen.getByLabelText('Nome do projeto')); await user.type(screen.getByLabelText('Nome do projeto'), 'Nome salvo');
    await user.click(screen.getByRole('button', { name: 'Salvar projeto' }));
    await act(async () => {
      source!.dispatchEvent(new MessageEvent('monitor.updated', { data: '{"project_id":"p1","revision":2}' }));
      completeRead(json({ items: [{ ...monitor, name: 'Leitura obsoleta' }], total: 1 }));
    });
    expect(screen.queryByText('Leitura obsoleta')).not.toBeInTheDocument(); expect(readCount).toBe(2);
    saved = { ...project, name: 'Nome salvo' }; await act(async () => completeSave(json(saved)));
    await waitFor(() => expect(readCount).toBeGreaterThan(2));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Nome salvo' })).toBeVisible());
    expect(screen.queryByText('Leitura obsoleta')).not.toBeInTheDocument();
  });
});
