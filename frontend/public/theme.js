// Blocking head script: resolve the theme before styles or React can paint.
(() => {
  let preference = 'system';
  try {
    const saved = localStorage.getItem('vigil.theme');
    if (saved === 'light' || saved === 'dark') preference = saved;
  } catch { /* Storage may be unavailable; keep the system preference. */ }
  const dark = preference === 'dark' || (preference === 'system' && window.matchMedia?.('(prefers-color-scheme: dark)').matches);
  const theme = dark ? 'dark' : 'light';
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.themePreference = preference;
  document.documentElement.style.colorScheme = theme;
})();
