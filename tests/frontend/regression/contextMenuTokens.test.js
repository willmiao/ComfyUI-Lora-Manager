import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'fs';
import path from 'path';

// Regression guard for the destructive context-menu entries.
//
// They were styled with `var(--danger-color)`, a token defined nowhere in the
// stylesheet tree. A var() reference to an undefined property makes the
// declaration invalid at computed-value time, so the colour silently fell back
// to the menu's inherited text colour: every "Delete …" entry in the folder
// sidebar menu and the model-card menus rendered plain. The first check below
// keeps menu.css wired only to tokens that actually resolve.
describe('Context menu design tokens', () => {
  const repoRoot = path.resolve(__dirname, '../../..');
  const cssDir = path.join(repoRoot, 'static/css');
  const menuCss = readFileSync(path.join(cssDir, 'components/menu.css'), 'utf-8');

  const collectCss = (dir, files = []) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) collectCss(full, files);
      else if (entry.name.endsWith('.css')) files.push(readFileSync(full, 'utf-8'));
    }
    return files;
  };

  const allCss = collectCss(cssDir).join('\n');
  const defined = new Set([...allCss.matchAll(/(--[\w-]+)\s*:/g)].map((match) => match[1]));

  // var(--x) with no fallback: an undefined name is a silent no-op.
  const usedWithoutFallback = [...menuCss.matchAll(/var\(\s*(--[\w-]+)\s*\)/g)].map(
    (match) => match[1]
  );

  it('resolves every custom property used by the context menu', () => {
    const unresolved = [...new Set(usedWithoutFallback)].filter((name) => !defined.has(name));
    expect(unresolved).toEqual([]);
  });

  it('paints destructive entries with the themed error colour', () => {
    const rule = menuCss.match(/\.context-menu-item\.delete-item\s*\{([^}]*)\}/);
    expect(rule).not.toBeNull();
    expect(rule[1]).toContain('var(--lora-error)');
    expect(defined.has('--lora-error')).toBe(true);
  });

  it('gives destructive entries their own hover treatment', () => {
    // The shared hover paints the accent background, which a red label does
    // not read against.
    expect(menuCss).toMatch(/\.context-menu-item\.delete-item:hover[\s\S]*?\{/);
    expect(menuCss).toMatch(/\.context-menu-item\.delete-item:hover[\s\S]*?var\(--lora-error-bg\)/);
  });

  it('never references the dead --danger-color token', () => {
    // Comments may name it; a var() argument may not.
    expect(allCss).not.toMatch(/var\(\s*--danger-color/);
  });
});
