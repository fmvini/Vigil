import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { AuthForm } from '../Forms';
import { LegalShell } from '../Legal';
import { LEGAL_CONTACT, policies, POLICY_VERSION } from '../legalContent';
import { COOKIE_PREFERENCE_KEY, COOKIE_PREFERENCE_LIFETIME, createCookiePreference, parseCookiePreference } from '../cookiePreference';
import { api } from '../api';
import { json } from './fixtures';

beforeEach(() => { localStorage.clear(); window.history.replaceState({}, '', '/'); });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); api.setCsrfToken(null); window.history.replaceState({}, '', '/'); });
const privacy = () => screen.getByRole('checkbox', { name: /Política de Privacidade/ });
const terms = () => screen.getByRole('checkbox', { name: /Termos de Uso/ });

describe('aceites separados na autenticação', () => {
  it.each([false, true])('não envia login/cadastro sem ambos, mesmo se validação nativa for contornada (cadastro=%s)', async register => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    render(<AuthForm notice="" onSession={vi.fn()} />);
    const user = userEvent.setup();
    if (register) await user.click(screen.getByRole('button', { name: 'Criar uma conta' }));
    await user.type(screen.getByLabelText('E-mail'), 'legal@example.com');
    await user.type(screen.getByLabelText('Senha'), 'password12345');
    expect(privacy()).toBeRequired(); expect(terms()).toBeRequired();
    expect(privacy()).not.toBeChecked(); expect(terms()).not.toBeChecked();
    const form = screen.getByLabelText('E-mail').closest('form')!;
    fireEvent.submit(form);
    expect(fetch).not.toHaveBeenCalled();
    await user.click(privacy()); fireEvent.submit(form);
    expect(fetch).not.toHaveBeenCalled();
    await user.click(privacy()); await user.click(terms()); fireEvent.submit(form);
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('aceite separadamente');
  });
  it.each([false, true])('envia versões exatas em login/cadastro e reseta cadastro bem-sucedido (cadastro=%s)', async register => {
    const session = { user: { id: 'u1', email: 'legal@example.com' }, csrf_token: 'csrf' };
    const fetch = vi.fn().mockResolvedValue(json(register ? session.user : session, register ? 201 : 200));
    vi.stubGlobal('fetch', fetch); const onSession = vi.fn();
    render(<AuthForm notice="" onSession={onSession} />); const user = userEvent.setup();
    if (register) await user.click(screen.getByRole('button', { name: 'Criar uma conta' }));
    await user.type(screen.getByLabelText('E-mail'), session.user.email);
    await user.type(screen.getByLabelText('Senha'), 'password12345');
    await user.click(privacy()); await user.click(terms());
    await user.click(screen.getByRole('button', { name: register ? 'Criar conta' : 'Entrar' }));
    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe(`/api/v1/auth/${register ? 'register' : 'login'}`);
    expect(JSON.parse(init.body)).toEqual({ email: session.user.email, password: 'password12345', terms_version: POLICY_VERSION, privacy_version: POLICY_VERSION });
    if (register) {
      expect(await screen.findByText('Conta criada. Entre com seu e-mail e senha.')).toBeVisible();
      expect(privacy()).not.toBeChecked(); expect(terms()).not.toBeChecked(); expect(onSession).not.toHaveBeenCalled();
    } else expect(onSession).toHaveBeenCalledWith(session);
  });
  it('links de leitura preservam formulário; troca de modo limpa ambos os aceites', async () => {
    render(<AuthForm notice="" onSession={vi.fn()} />); const user = userEvent.setup();
    await user.type(screen.getByLabelText('E-mail'), 'kept@example.com');
    await user.type(screen.getByLabelText('Senha'), 'password12345');
    await user.click(privacy()); await user.click(terms());
    for (const title of ['Política de Privacidade', 'Termos de Uso']) {
      const link = screen.getByRole('link', { name: title });
      expect(link).toHaveAttribute('target', '_blank'); expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    }
    expect(screen.getByLabelText('E-mail')).toHaveValue('kept@example.com'); expect(screen.getByLabelText('Senha')).toHaveValue('password12345');
    await user.click(screen.getByRole('button', { name: 'Criar uma conta' }));
    expect(privacy()).not.toBeChecked(); expect(terms()).not.toBeChecked();
    await user.click(privacy()); await user.click(terms()); await user.click(screen.getByRole('button', { name: 'Já tenho uma conta' }));
    expect(privacy()).not.toBeChecked(); expect(terms()).not.toBeChecked();
  });
});

describe('políticas públicas e 404', () => {
  it.each(['privacy', 'terms', 'cookies'] as const)('renderiza /%s pública com conteúdo real, contato e rodapé, sem API', async policy => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch); window.history.replaceState({}, '', `/${policy}`);
    render(<App />);
    expect(screen.getByRole('heading', { name: policies[policy].title, level: 1 })).toBeVisible();
    for (const section of policies[policy].sections) expect(screen.getByRole('heading', { name: section.title, level: 2 })).toBeVisible();
    expect(screen.getByText(LEGAL_CONTACT.name)).toBeVisible();
    expect(LEGAL_CONTACT.email).toBe('viniciusfmarrocos@gmail.com');
    expect(screen.getByRole('link', { name: LEGAL_CONTACT.email! })).toHaveAttribute('href', 'mailto:viniciusfmarrocos@gmail.com');
    expect(screen.getByText(/A identificação completa do responsável ainda precisa ser informada/)).toBeVisible();
    expect(screen.queryByText('O canal de contato ainda não foi informado.')).not.toBeInTheDocument();
    expect(POLICY_VERSION).toBe('2026-10-09');
    expect(screen.getByRole('navigation', { name: 'Informações legais' })).toBeVisible();
    expect(screen.getByRole('region', { name: 'Cookies e preferências' })).toBeVisible();
    expect(fetch).not.toHaveBeenCalled(); expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });
  it.each(['/unknown', '/arquivo-inexistente.js', '/demo/unknown', '/demo/status/a/extra', '/privacy/extra'])('404 %s compartilhada sem autenticação/rede', async path => {
    const fetch = vi.fn(), source = vi.fn(); vi.stubGlobal('fetch', fetch); vi.stubGlobal('EventSource', source);
    window.history.replaceState({}, '', path); render(<App />);
    expect(screen.getByRole('heading', { name: '404 · Página não encontrada' })).toBeVisible();
    expect(screen.getByRole('link', { name: path.startsWith('/demo/') ? 'Voltar à demonstração' : 'Voltar ao início' })).toHaveAttribute('href', path.startsWith('/demo/') ? '/demo' : '/');
    expect(screen.getByRole('navigation', { name: 'Informações legais' })).toBeVisible();
    expect(fetch).not.toHaveBeenCalled(); expect(source).not.toHaveBeenCalled();
  });
});

describe('preferências de cookies', () => {
  it.each(['accepted', 'refused'] as const)('salva %s por 180 dias e permite reabrir pelo rodapé', async choice => {
    const cookiesBefore = document.cookie;
    const user = userEvent.setup(); render(<LegalShell><main><h1>Leitura livre</h1><button>Ler página</button></main></LegalShell>);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Ler página' }));
    const banner = screen.getByRole('region', { name: 'Cookies e preferências' });
    expect(banner).toHaveTextContent('cookie necessário com um identificador de sessão para manter o login');
    expect(banner).toHaveTextContent('O armazenamento local deste navegador guarda o tema e sua escolha neste aviso');
    expect(banner).toHaveTextContent('Não usamos analytics nem cookies de marketing');
    expect(banner).toHaveTextContent('Continuar sem aceitar mantém o acesso público; o cookie necessário será usado se você entrar na conta');
    expect(within(banner).getByRole('link', { name: /Ler a Política de Cookies/ })).toHaveAttribute('href', '/cookies');
    expect(within(banner).getAllByRole('button')).toHaveLength(2);
    await user.click(screen.getByRole('button', { name: choice === 'accepted' ? 'Aceitar cookies' : 'Continuar sem aceitar' }));
    expect(screen.queryByRole('region', { name: 'Cookies e preferências' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Leitura livre' })).toBeVisible();
    expect(document.cookie).toBe(cookiesBefore);
    const value = JSON.parse(localStorage.getItem(COOKIE_PREFERENCE_KEY)!);
    expect(value.choice).toBe(choice); expect(value.version).toBe(POLICY_VERSION);
    expect(Date.parse(value.expires_at) - Date.parse(value.timestamp)).toBe(COOKIE_PREFERENCE_LIFETIME);
    await user.click(screen.getByRole('button', { name: 'Preferências de cookies' }));
    expect(screen.getByRole('heading', { name: 'Cookies e preferências' })).toHaveFocus();
    await user.click(screen.getByRole('button', { name: choice === 'accepted' ? 'Continuar sem aceitar' : 'Aceitar cookies' }));
    expect(JSON.parse(localStorage.getItem(COOKIE_PREFERENCE_KEY)!).choice).not.toBe(choice);
    expect(screen.getByRole('button', { name: 'Preferências de cookies' })).toHaveFocus();
  });
  it('restaura escolha válida e acompanha eventos de storage de outras abas e clear', () => {
    localStorage.setItem(COOKIE_PREFERENCE_KEY, JSON.stringify(createCookiePreference('refused')));
    render(<LegalShell>Conteúdo</LegalShell>);
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: COOKIE_PREFERENCE_KEY, newValue: null })));
    expect(screen.getByRole('region')).toBeVisible();
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: COOKIE_PREFERENCE_KEY, newValue: JSON.stringify(createCookiePreference('accepted')) })));
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: 'unrelated', newValue: null })));
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: null, newValue: null })));
    expect(screen.getByRole('region')).toBeVisible();
  });
  it('expira automaticamente na aba aberta sem timeout de 180 dias transbordar', () => {
    vi.useFakeTimers(); const now = Date.now();
    localStorage.setItem(COOKIE_PREFERENCE_KEY, JSON.stringify(createCookiePreference('accepted', now - COOKIE_PREFERENCE_LIFETIME + 1000)));
    render(<LegalShell>Conteúdo</LegalShell>); expect(screen.queryByRole('region')).not.toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1001)); expect(screen.getByRole('region')).toBeVisible();
  });
  it('storage indisponível mantém escolha em memória e permite alteração', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('unavailable'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('unavailable'); });
    const user = userEvent.setup(); render(<LegalShell>Conteúdo</LegalShell>);
    await user.click(screen.getByRole('button', { name: 'Continuar sem aceitar' }));
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('enquanto esta página estiver aberta');
    await user.click(screen.getByRole('button', { name: 'Preferências de cookies' }));
    await user.click(screen.getByRole('button', { name: 'Aceitar cookies' }));
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
  });
  it('rejeita preferência corrupta, vencida, futura ou de versão antiga', () => {
    const now = Date.now(); const valid = createCookiePreference('accepted', now);
    expect(parseCookiePreference(JSON.stringify(valid), now)).toEqual(valid);
    for (const value of ['not json', 'null', JSON.stringify({ ...valid, version: 'old' }), JSON.stringify({ ...valid, choice: true }), JSON.stringify({ ...valid, timestamp: false }), JSON.stringify({ ...valid, expires_at: 'bad' }), JSON.stringify(createCookiePreference('refused', now - COOKIE_PREFERENCE_LIFETIME)), JSON.stringify(createCookiePreference('accepted', now + 1))]) expect(parseCookiePreference(value, now)).toBeNull();
  });
});
