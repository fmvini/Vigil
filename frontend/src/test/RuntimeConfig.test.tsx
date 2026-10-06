import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api';
import { MonitorForm } from '../Forms';
import { validateMonitor } from '../domain';
import { intervalHelp, parseRuntimeConfig } from '../runtimeConfig';
import { json, monitor } from './fixtures';

const local = { minimum_interval_seconds: 60, scheduled_checks_interval_seconds: null };
const scheduled300 = { minimum_interval_seconds: 300, scheduled_checks_interval_seconds: 300 };
const cloud = { minimum_interval_seconds: 900, scheduled_checks_interval_seconds: 900 };
const props = () => ({ projectId: 'p1', onSaved: vi.fn(), onCancel: vi.fn(), onBusyChange: vi.fn() });
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); api.onUnauthorized = undefined; api.setCsrfToken(null); });

describe('contrato público de configuração do ambiente', () => {
  it('aceita somente o envelope válido e descreve a agenda sem garantir prazo', () => {
    expect(parseRuntimeConfig(local)).toEqual(local);
    expect(parseRuntimeConfig(cloud)).toEqual(cloud);
    expect(parseRuntimeConfig(scheduled300)).toEqual(scheduled300);
    expect(parseRuntimeConfig({ minimum_interval_seconds: 3600, scheduled_checks_interval_seconds: 1 })).toMatchObject({ minimum_interval_seconds: 3600 });
    expect(intervalHelp(local)).toBe('Intervalo mínimo: 60 segundos. Tempo entre ciclos.');
    expect(intervalHelp(cloud)).toContain('aproximadamente a cada 15 minutos e podem atrasar');
    expect(intervalHelp(scheduled300)).toContain('aproximadamente a cada 5 minutos e podem atrasar');
  });
  it.each([null, [], true, {}, { ...local, minimum_interval_seconds: true }, { ...local, minimum_interval_seconds: '300' }, { ...local, minimum_interval_seconds: 300.5 }, { ...local, minimum_interval_seconds: 59 }, { ...local, minimum_interval_seconds: 3601 }, { minimum_interval_seconds: 300 }, { ...cloud, scheduled_checks_interval_seconds: true }, { ...cloud, scheduled_checks_interval_seconds: 0 }, { ...cloud, scheduled_checks_interval_seconds: 1.5 }, { ...cloud, scheduled_checks_interval_seconds: '300' }, { ...cloud, secret: 'PRIVATE_SENTINEL' }])('recusa configuração inválida sem fallback local (%#)', invalid => {
    expect(() => parseRuntimeConfig(invalid)).toThrow('RUNTIME_CONFIG_INVALID');
  });
});

describe('formulário condicionado à configuração real', () => {
  it('mantém criação local60 e envia somente configuração do monitor', async () => {
    const callbacks = props();
    const fetch = vi.fn(async (url: string, init?: RequestInit) => url.endsWith('/runtime-config') ? json(local) : json({ ...monitor, ...JSON.parse(String(init?.body)) }, 201));
    vi.stubGlobal('fetch', fetch); render(<MonitorForm {...callbacks} />);
    const interval = await screen.findByLabelText('Intervalo (segundos)');
    expect(interval).toHaveValue(60); expect(interval).toHaveAttribute('min', '60');
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('Nome do monitor'), 'Local QA');
    await user.type(screen.getByLabelText('URL do endpoint'), 'https://example.com/health');
    await user.click(screen.getByRole('button', { name: 'Salvar monitor' }));
    await waitFor(() => expect(callbacks.onSaved).toHaveBeenCalled());
    expect(JSON.parse(String(fetch.mock.calls[1][1]?.body))).toMatchObject({ interval_seconds: 60, is_public: false });
    expect(fetch.mock.calls[0][1]).toMatchObject({ method: 'GET', credentials: 'same-origin', cache: 'no-store' });
  });
  it('cria cloud900, bloqueia valor menor/decimal e preserva intervalo maior', async () => {
    const callbacks = props();
    const fetch = vi.fn(async (url: string, init?: RequestInit) => url.endsWith('/runtime-config') ? json(cloud) : json({ ...monitor, ...JSON.parse(String(init?.body)) }, 201));
    vi.stubGlobal('fetch', fetch); render(<MonitorForm {...callbacks} />);
    const interval = await screen.findByLabelText('Intervalo (segundos)');
    expect(interval).toHaveValue(900); expect(interval).toHaveAttribute('min', '900');
    expect(screen.getByText(/aproximadamente a cada 15 minutos e podem atrasar/)).toBeVisible();
    fireEvent.change(screen.getByLabelText('Nome do monitor'), { target: { value: 'Cloud QA' } });
    fireEvent.change(screen.getByLabelText('URL do endpoint'), { target: { value: 'https://example.com/health' } });
    for (const value of ['899', '900.5', '3601', '']) {
      fireEvent.change(interval, { target: { value } });
      expect(screen.getByRole('button', { name: 'Salvar monitor' })).toBeDisabled();
      fireEvent.submit(interval.closest('form')!);
      expect(fetch).toHaveBeenCalledTimes(1);
    }
    fireEvent.change(interval, { target: { value: '1800' } });
    await userEvent.setup().click(screen.getByRole('button', { name: 'Salvar monitor' }));
    await waitFor(() => expect(callbacks.onSaved).toHaveBeenCalled());
    expect(JSON.parse(String(fetch.mock.calls[1][1]?.body)).interval_seconds).toBe(1800);
  });
  it('preserva intervalo antigo60 em edição cloud e exige ajuste explícito', async () => {
    const callbacks = props();
    const fetch = vi.fn(async (url: string, init?: RequestInit) => url.endsWith('/runtime-config') ? json(cloud) : json({ ...monitor, ...JSON.parse(String(init?.body)) }));
    vi.stubGlobal('fetch', fetch); render(<MonitorForm {...callbacks} value={monitor} />);
    const interval = await screen.findByLabelText('Intervalo (segundos)');
    expect(interval).toHaveValue(60); expect(interval).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('button', { name: 'Salvar monitor' })).toBeDisabled();
    fireEvent.submit(interval.closest('form')!); expect(fetch).toHaveBeenCalledTimes(1);
    fireEvent.change(interval, { target: { value: '900' } });
    await userEvent.setup().click(screen.getByRole('button', { name: 'Salvar monitor' }));
    await waitFor(() => expect(callbacks.onSaved).toHaveBeenCalled());
    expect(fetch.mock.calls[1][0]).toBe('/api/v1/monitors/m1');
    expect(fetch.mock.calls[1][1]?.method).toBe('PATCH');
    expect(JSON.parse(String(fetch.mock.calls[1][1]?.body)).interval_seconds).toBe(900);
    expect(validateMonitor(monitor, 900)).toContain('900');
  });
  it('erro HTTP não permite salvar, não invalida sessão e permite retry válido', async () => {
    const unauthorized = vi.fn(); api.onUnauthorized = unauthorized;
    const fetch = vi.fn().mockResolvedValueOnce(json({ error: { message: 'PRIVATE_SENTINEL' } }, 401)).mockResolvedValueOnce(json(cloud));
    vi.stubGlobal('fetch', fetch); render(<MonitorForm {...props()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível confirmar o intervalo');
    expect(screen.queryByText(/PRIVATE_SENTINEL|mínimo: 60/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Salvar monitor' })).not.toBeInTheDocument();
    expect(unauthorized).not.toHaveBeenCalled();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Carregar configuração novamente' }));
    expect(await screen.findByLabelText('Intervalo (segundos)')).toHaveValue(900);
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('resposta inválida também bloqueia o formulário', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ minimum_interval_seconds: 300 })));
    render(<MonitorForm {...props()} />);
    await screen.findByRole('alert');
    expect(screen.queryByLabelText('Intervalo (segundos)')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeEnabled();
  });
  it('cancela leitura ao fechar e consulta novamente ao reabrir', async () => {
    let complete: (response: Response) => void = () => {};
    const fetch = vi.fn().mockImplementationOnce(() => new Promise<Response>(resolve => { complete = resolve; })).mockResolvedValueOnce(json(cloud));
    vi.stubGlobal('fetch', fetch); const first = render(<MonitorForm {...props()} />);
    expect(screen.getByRole('status')).toHaveTextContent('Consultando o intervalo');
    expect(screen.queryByRole('button', { name: 'Salvar monitor' })).not.toBeInTheDocument();
    const signal = fetch.mock.calls[0][1].signal as AbortSignal;
    first.unmount(); expect(signal.aborted).toBe(true);
    render(<MonitorForm {...props()} />);
    expect(await screen.findByLabelText('Intervalo (segundos)')).toHaveValue(900);
    await act(async () => complete(json(local)));
    expect(screen.getByLabelText('Intervalo (segundos)')).toHaveValue(900);
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('timeout permite retry e resposta atrasada não troca900 por60', async () => {
    vi.useFakeTimers(); let complete: (response: Response) => void = () => {};
    const fetch = vi.fn().mockImplementationOnce(() => new Promise<Response>(resolve => { complete = resolve; })).mockResolvedValueOnce(json(cloud));
    vi.stubGlobal('fetch', fetch); render(<MonitorForm {...props()} />);
    await act(async () => vi.advanceTimersByTime(10_000));
    expect(screen.getByRole('alert')).toHaveTextContent('Não foi possível confirmar');
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Carregar configuração novamente' })));
    expect(screen.getByLabelText('Intervalo (segundos)')).toHaveValue(900);
    await act(async () => complete(json(local)));
    expect(screen.getByLabelText('Intervalo (segundos)')).toHaveValue(900);
  });
});
