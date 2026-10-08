import { useEffect, useId, useState } from 'react';

export type ThemePreference = 'light' | 'dark' | 'system';
const storageKey = 'vigil.theme';
const systemQuery = '(prefers-color-scheme: dark)';

function preferenceFrom(value: string | null): ThemePreference {
  return value === 'light' || value === 'dark' ? value : 'system';
}
function readPreference(): ThemePreference {
  try { return preferenceFrom(localStorage.getItem(storageKey)); }
  catch { return preferenceFrom(document.documentElement.dataset.themePreference ?? null); }
}
function applyTheme(preference: ThemePreference) {
  const dark = preference === 'dark' || (preference === 'system' && window.matchMedia?.(systemQuery).matches);
  const theme = dark ? 'dark' : 'light';
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.themePreference = preference;
  document.documentElement.style.colorScheme = theme;
}

export function ThemeControl() {
  const id = useId();
  const [preference, setPreference] = useState<ThemePreference>(readPreference);
  useEffect(() => {
    applyTheme(preference);
    const media = window.matchMedia?.(systemQuery);
    const onSystemChange = () => { if (preference === 'system') applyTheme('system'); };
    const onStorage = (event: StorageEvent) => {
      if (event.key === storageKey || event.key === null) {
        const next = readPreference();
        applyTheme(next); setPreference(next);
      }
    };
    media?.addEventListener('change', onSystemChange);
    window.addEventListener('storage', onStorage);
    return () => {
      media?.removeEventListener('change', onSystemChange);
      window.removeEventListener('storage', onStorage);
    };
  }, [preference]);
  function choose(value: ThemePreference) {
    applyTheme(value); setPreference(value);
    try { localStorage.setItem(storageKey, value); }
    catch { /* The choice remains active for this page if storage is blocked. */ }
  }
  return <div className="theme-control">
    <label htmlFor={id}>Tema</label>
    <select id={id} value={preference} onChange={event => choose(event.target.value as ThemePreference)}>
      <option value="system">Sistema</option><option value="light">Claro</option><option value="dark">Escuro</option>
    </select>
  </div>;
}
