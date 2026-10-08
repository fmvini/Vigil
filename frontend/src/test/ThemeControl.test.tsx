import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { ThemeControl } from '../ThemeControl';

let dark = false;
let listeners: Set<() => void>;
// npm runs the official Vitest command from frontend/. Vite's jsdom URL is
// an HTTP module URL, so resolve fixture files from the filesystem cwd.
const bootstrap = readFileSync(resolve(process.cwd(), 'public/theme.js'), 'utf8');
const html = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8');

function resetThemeDocument() {
  delete document.documentElement.dataset.theme;
  delete document.documentElement.dataset.themePreference;
  document.documentElement.style.removeProperty('color-scheme');
}

beforeEach(() => {
  localStorage.clear(); dark = false; listeners = new Set();
  resetThemeDocument();
  vi.stubGlobal('matchMedia', vi.fn(() => ({
    get matches() { return dark; },
    addEventListener: (_type: string, callback: () => void) => listeners.add(callback),
    removeEventListener: (_type: string, callback: () => void) => listeners.delete(callback),
  })));
});
afterEach(() => {
  vi.restoreAllMocks(); vi.unstubAllGlobals(); localStorage.clear();
  resetThemeDocument();
});
function changeSystem(value: boolean) {
  act(() => { dark = value; listeners.forEach(listener => listener()); });
}

describe('preferência de tema', () => {
  it.each(['system', 'light', 'dark'])('mantém o nome acessível exato Tema com preferência %s', preference => {
    localStorage.setItem('vigil.theme', preference);
    render(<ThemeControl />);
    const control = screen.getByRole('combobox', { name: /^Tema$/ }) as HTMLSelectElement;
    expect(screen.getByLabelText('Tema', { exact: true })).toBe(control);
    expect(control).toHaveAccessibleName('Tema');
    expect(control).toHaveValue(preference);
    expect(control.labels?.[0].textContent).toBe('Tema');
    expect(screen.getAllByRole('option')).toHaveLength(3);
  });
  it('segue o sistema por padrão e responde a mudanças em tempo real', () => {
    render(<ThemeControl />);
    expect(screen.getByRole('combobox', { name: 'Tema' })).toHaveValue('system');
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(document.documentElement.dataset.themePreference).toBe('system');
    changeSystem(true);
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(document.documentElement.style.colorScheme).toBe('dark');
    expect(localStorage.getItem('vigil.theme')).toBeNull();
  });
  it('persiste a escolha explícita, ignora o sistema e permite voltar a segui-lo', async () => {
    const user = userEvent.setup();
    const view = render(<ThemeControl />);
    await user.selectOptions(screen.getByLabelText('Tema'), 'dark');
    expect(localStorage.getItem('vigil.theme')).toBe('dark');
    changeSystem(false); expect(document.documentElement.dataset.theme).toBe('dark');
    view.unmount(); render(<ThemeControl />);
    expect(screen.getByLabelText('Tema')).toHaveValue('dark');
    await user.selectOptions(screen.getByLabelText('Tema'), 'light');
    changeSystem(true); expect(document.documentElement.dataset.theme).toBe('light');
    await user.selectOptions(screen.getByLabelText('Tema'), 'system');
    expect(localStorage.getItem('vigil.theme')).toBe('system');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });
  it('reconcilia alteração ou limpeza de preferência em outra aba e remove listeners', () => {
    const view = render(<ThemeControl />);
    act(() => { localStorage.setItem('vigil.theme', 'dark'); window.dispatchEvent(new StorageEvent('storage', { key: 'vigil.theme' })); });
    expect(screen.getByLabelText('Tema')).toHaveValue('dark');
    act(() => { localStorage.clear(); window.dispatchEvent(new StorageEvent('storage', { key: null })); });
    expect(screen.getByLabelText('Tema')).toHaveValue('system');
    expect(listeners.size).toBe(1); view.unmount(); expect(listeners.size).toBe(0);
  });
  it('ignora preferência inválida e resolve pelo sistema', () => {
    localStorage.setItem('vigil.theme', 'invalid'); dark = true;
    render(<ThemeControl />);
    expect(screen.getByLabelText('Tema')).toHaveValue('system');
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(document.documentElement.dataset.themePreference).toBe('system');
  });
  it('preserva a escolha na remontagem quando o storage está indisponível', async () => {
    dark = true;
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
    const view = render(<ThemeControl />);
    expect(screen.getByLabelText('Tema')).toHaveValue('system');
    await userEvent.setup().selectOptions(screen.getByLabelText('Tema'), 'light');
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(document.documentElement.dataset.themePreference).toBe('light');
    view.unmount(); expect(listeners.size).toBe(0);
    render(<ThemeControl />);
    expect(screen.getByLabelText('Tema')).toHaveValue('light');
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(document.documentElement.style.colorScheme).toBe('light');
    changeSystem(false); changeSystem(true);
    expect(document.documentElement.dataset.theme).toBe('light');
  });
});

describe('tema antes da primeira renderização', () => {
  it.each([
    [null, true, 'dark'], [null, false, 'light'], ['light', true, 'light'],
    ['dark', false, 'dark'], ['system', true, 'dark'], ['invalid', false, 'light'],
  ])('resolve %s com sistema dark=%s antes do React', (saved, systemDark, expected) => {
    if (saved) localStorage.setItem('vigil.theme', saved);
    dark = systemDark;
    new Function('window', 'document', 'localStorage', bootstrap)(window, document, localStorage);
    expect(document.documentElement.dataset.theme).toBe(expected);
    expect(document.documentElement.dataset.themePreference).toBe(saved === 'light' || saved === 'dark' ? saved : 'system');
    expect(document.documentElement.style.colorScheme).toBe(expected);
  });
  it('carrega o bootstrap bloqueante no head antes do bundle', () => {
    expect(html.indexOf('<script src="/theme.js"></script>')).toBeLessThan(html.indexOf('</head>'));
    expect(html.indexOf('<script src="/theme.js"></script>')).toBeLessThan(html.indexOf('type="module"'));
    expect(html).not.toMatch(/(?:defer|async)[^>]*src="\/theme.js"/);
  });
  it('segue o sistema mesmo quando o storage ou matchMedia não está disponível', () => {
    dark = true;
    const blocked = { getItem() { throw new Error('blocked'); } };
    new Function('window', 'document', 'localStorage', bootstrap)(window, document, blocked);
    expect(document.documentElement.dataset.theme).toBe('dark');
    new Function('window', 'document', 'localStorage', bootstrap)({}, document, blocked);
    expect(document.documentElement.dataset.theme).toBe('light');
  });
});
