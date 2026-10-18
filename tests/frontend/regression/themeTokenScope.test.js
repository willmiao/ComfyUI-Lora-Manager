import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import path from 'path';

// Regression guard: theme palette tokens may only be declared on the root element.
//
// `applyTheme()` (static/js/utils/uiHelpers.js, and Header.setThemeMode) mirrors
// the active mode onto <body> as `data-theme="dark"`, but the theme *preset* is
// only ever written to <html> (`data-theme-preset`). While the token blocks in
// tokens/colors.css used the bare attribute selector `[data-theme="dark"]`, the
// body matched that block on its own and re-declared the DEFAULT dark palette
// (#1a1a1a / #2d2d2d), shadowing the preset palette it inherited from <html>.
// The page painted the selected preset's accent but the default preset's
// backgrounds/surfaces/text, and flipped into that state ~200ms after load when
// initTheme() first touched <body> — the accent-tinted background flash on
// reload and nav-tab switches, visible under every preset except "default".
// Root-scoping the token blocks keeps <body>'s data-theme inert.
describe('Theme token scope', () => {
  const repoRoot = path.resolve(__dirname, '../../..');
  const read = (rel) => readFileSync(path.join(repoRoot, rel), 'utf-8');
  const stripComments = (css) => css.replace(/\/\*[\s\S]*?\*\//g, '');

  const COLOR_TOKENS = read('static/css/tokens/colors.css');
  const BASE_CSS = read('static/css/base.css');

  // Selectors that declare a palette token, e.g. `--bg-base:` / `--lora-surface:`.
  const tokenDeclaringSelectors = (css) => {
    const selectors = [];
    const ruleRe = /([^{}]+)\{([^{}]*)\}/g;
    let match;
    while ((match = ruleRe.exec(stripComments(css)))) {
      const selector = match[1].trim();
      const declaresPaletteToken = /(^|[;\s])--(?:bg|surface|text|border|color|favorite|lora|badge|card)-[\w-]+\s*:/.test(
        match[2]
      );
      if (declaresPaletteToken) selectors.push(selector);
    }
    return selectors;
  };

  const isRootScoped = (selector) =>
    selector.split(',').every((part) => /^\s*(:root|html)\b/.test(part));

  it('declares every colors.css palette token on :root', () => {
    const selectors = tokenDeclaringSelectors(COLOR_TOKENS);
    expect(selectors.length).toBeGreaterThan(0);
    expect(selectors.filter((selector) => !isRootScoped(selector))).toEqual([]);
  });

  it('declares every base.css palette alias on :root', () => {
    const selectors = tokenDeclaringSelectors(BASE_CSS);
    expect(selectors.length).toBeGreaterThan(0);
    expect(selectors.filter((selector) => !isRootScoped(selector))).toEqual([]);
  });

  it('keeps dark/preset token blocks anchored to the root element', () => {
    const css = stripComments(COLOR_TOKENS);
    expect(css).toContain(':root[data-theme="dark"] {');
    for (const preset of ['nord', 'midnight', 'monokai', 'dracula', 'solarized']) {
      expect(css).toContain(`:root[data-theme-preset="${preset}"] {`);
      expect(css).toContain(`:root[data-theme="dark"][data-theme-preset="${preset}"] {`);
    }
    // No bare attribute selector may open a rule: <body> carries data-theme
    // without the preset, so such a block would re-declare the default palette.
    expect(css).not.toMatch(/(^|\n)\s*\[data-theme/);
    expect(stripComments(BASE_CSS)).not.toMatch(/(^|\n)\s*\[data-theme/);
  });
});
