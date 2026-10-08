import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const bootstrap = readFileSync(new URL('../public/theme.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const css = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');

test('bootstrap resolves saved/system/invalid/blocked preferences before content', () => {
  for (const [saved, systemDark, expected] of [
    [null, false, 'light'], [null, true, 'dark'], ['light', true, 'light'],
    ['dark', false, 'dark'], ['system', true, 'dark'], ['invalid', true, 'dark'],
  ]) {
    const root = { dataset: {}, style: {} };
    runInNewContext(bootstrap, { document: { documentElement: root }, window: { matchMedia: () => ({ matches: systemDark }) }, localStorage: { getItem: () => saved } });
    assert.equal(root.dataset.theme, expected); assert.equal(root.style.colorScheme, expected);
  }
  const root = { dataset: {}, style: {} };
  runInNewContext(bootstrap, { document: { documentElement: root }, window: { matchMedia: () => ({ matches: true }) }, localStorage: { getItem: () => { throw Error('blocked'); } } });
  assert.equal(root.dataset.theme, 'dark');
  runInNewContext(bootstrap, { document: { documentElement: root }, window: {}, localStorage: { getItem: () => null } });
  assert.equal(root.dataset.theme, 'light');
});
test('bootstrap is synchronous in the head, before styles and app content', () => {
  const position = html.indexOf('<script src="/theme.js"></script>');
  assert.ok(position > 0 && position < html.indexOf('</head>') && position < html.indexOf('<body>'));
  assert.doesNotMatch(html, /(?:defer|async)[^>]*src="\/theme.js"/);
});

function luminance(hex) {
  let value = hex.slice(1); if (value.length === 3) value = [...value].map(char => char + char).join('');
  const rgb = [0, 2, 4].map(index => parseInt(value.slice(index, index + 2), 16) / 255).map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4);
  return rgb.reduce((sum, c, index) => sum + c * [.2126, .7152, .0722][index], 0);
}
const blocks = [...css.matchAll(/:root(?:\[data-theme="dark"\])?\s*\{([^}]+)\}/g)].slice(0, 2);
const pairs = [
  ['text', 'canvas'], ['text', 'surface'], ['muted', 'canvas'], ['muted', 'subtle'], ['muted', 'story-bg'],
  ['control-text', 'surface'], ['placeholder', 'surface'], ['accent', 'canvas'], ['accent', 'surface'],
  ['on-accent', 'accent'], ['on-accent', 'accent-hover'], ['on-danger', 'danger'], ['on-danger', 'danger-hover'],
  ['brand-text', 'story-bg'], ['alert-text', 'alert-bg'], ['success-text', 'success-bg'], ['archive-text', 'archive-bg'],
  ['story-text', 'story-bg'], ['selected-text', 'selected-bg'], ['account-text', 'subtle'], ['health-online', 'canvas'],
  ['health-degraded', 'canvas'], ['danger', 'canvas'], ['selection-text', 'selection-bg'],
  ...['none', 'stale', 'paused', 'fresh'].map(state => [`data-${state}-text`, `data-${state}-bg`]),
];
test('light and dark semantic text pairs meet WCAG AA 4.5:1', () => {
  assert.equal(blocks.length, 2);
  for (const [index, block] of blocks.entries()) {
    const tokens = Object.fromEntries([...block[1].matchAll(/--([\w-]+):\s*(#[\da-f]+)/g)].map(match => [match[1], match[2]]));
    for (const [foreground, background] of pairs) {
      const values = [luminance(tokens[foreground]), luminance(tokens[background])].sort((a, b) => a - b);
      const ratio = (values[1] + .05) / (values[0] + .05);
      assert.ok(ratio >= 4.5, `${index === 0 ? 'light' : 'dark'} ${foreground}/${background}: ${ratio.toFixed(2)}`);
    }
    const fields = [luminance(tokens['field-border']), luminance(tokens.surface)].sort((a, b) => a - b);
    assert.ok((fields[1] + .05) / (fields[0] + .05) >= 3, 'field boundaries meet 3:1');
  }
});
