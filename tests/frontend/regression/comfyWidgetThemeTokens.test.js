import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'fs';
import path from 'path';

// Regression guard for the ComfyUI node widget theming (issue: LM widgets only
// looked right on dark palettes).
//
// LM widgets must never hard-code colour values: every colour has to alias a
// ComfyUI theme token (`--comfy-input-bg`, `--component-node-*`, ...) or an LM
// semantic token from web/comfyui/lm_theme.css (`--lm-*`). Hard-coded values
// are how the prompt textarea ended up charcoal inside a white node under the
// Light palette.
//
// The only allowed literals are overlays painted on top of preview images:
// they intentionally stay dark in every theme, and the license badge colours.

const repoRoot = path.resolve(__dirname, '../../..');

const read = (rel) => readFileSync(path.join(repoRoot, rel), 'utf-8');

const stripComments = (text) => text.replace(/\/\*[\s\S]*?\*\//g, '');

/**
 * Remove `var(...)` groups (including the fallback values inside them) so a
 * legitimately theme-neutral fallback such as `var(--comfy-input-bg, #222)` is
 * not reported. Nested `var()` fallbacks are handled by matching balanced
 * parentheses one level at a time.
 */
const stripVarCalls = (text) => {
  let out = text;
  let previous;
  do {
    previous = out;
    out = out.replace(/var\([^()]*(?:\([^()]*\)[^()]*)*\)/g, '');
  } while (out !== previous);
  return out;
};

const COLOR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\brgba?\([^)]*\)|\bhsla?\([^)]*\)/g;

const stripJsComments = (text) =>
  text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');

const colorLiterals = (text) =>
  stripVarCalls(stripComments(text)).match(COLOR_LITERAL) ?? [];

const walk = (dir) => {
  const entries = readdirSync(dir);
  return entries.flatMap((entry) => {
    const full = path.join(dir, entry);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
};

// Dark scrims/gradients/labels drawn over model preview images, plus the two
// license-state icon colours. These are theme independent by design.
const CSS_LITERAL_ALLOWLIST = new Set([
  'rgba(10, 10, 14, 0.78)', // license badge backdrop
  'rgba(255, 255, 255, 0.12)', // license badge border
  'rgba(0, 0, 0, 0.85)', // tooltip panel
  'rgba(0, 0, 0, 0.8)', // tooltip label gradient
  'rgba(0, 0, 0, 0.45)', // tooltip drop shadow
  'rgba(0, 0, 0, 0.3)', // tooltip box shadow
  'rgba(255, 255, 255, 0.9)', // license icon mask fill
  '#40c057', // license state: allowed
  '#fa5252', // license state: denied
]);

// Files whose literals are not widget chrome:
//  - top_menu_extension.js: inline SVG brand artwork (brand colours).
//  - textarea_caret_helper.js: debug-only caret mirror highlight.
//  - workflow_registry.js: last-resort fallback when --lm-accent cannot be read.
const JS_LITERAL_ALLOWLIST = new Set([
  'top_menu_extension.js',
  'textarea_caret_helper.js',
  'workflow_registry.js',
]);

describe('ComfyUI widget theme tokens', () => {
  it('keeps lm_styles.css free of theme-dependent colour literals', () => {
    const literals = colorLiterals(read('web/comfyui/lm_styles.css'));
    const unexpected = literals.filter((value) => !CSS_LITERAL_ALLOWLIST.has(value));
    expect(unexpected).toEqual([]);
  });

  it('keeps Vue widget <style> blocks free of colour literals', () => {
    const files = walk(path.join(repoRoot, 'vue-widgets/src/components')).filter(
      (file) => file.endsWith('.vue')
    );
    expect(files.length).toBeGreaterThan(0);

    const offenders = [];
    for (const file of files) {
      const source = readFileSync(file, 'utf-8');
      const styleBlocks = source.match(/<style[\s\S]*?<\/style>/g) ?? [];
      for (const block of styleBlocks) {
        for (const literal of colorLiterals(block)) {
          offenders.push(`${path.relative(repoRoot, file)}: ${literal}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it('keeps canvas widget JS free of theme-dependent colour literals', () => {
    // The compiled Vue bundle (web/comfyui/vue-widgets) is build output and is
    // covered by the source-level <style> check above.
    const files = walk(path.join(repoRoot, 'web/comfyui')).filter(
      (file) => file.endsWith('.js') && !file.includes(`${path.sep}vue-widgets${path.sep}`)
    );

    const offenders = [];
    for (const file of files) {
      const name = path.basename(file);
      if (JS_LITERAL_ALLOWLIST.has(name)) continue;
      for (const literal of colorLiterals(stripJsComments(readFileSync(file, 'utf-8')))) {
        offenders.push(`${name}: ${literal}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('declares the LM token layer for both palettes and the Vue node renderer', () => {
    const theme = read('web/comfyui/lm_theme.css');
    // Tokens are inherited by every LM widget and by ComfyUI-owned rows we style.
    expect(theme).toMatch(/:root,\s*\n\.lm-widget-root,\s*\n\.lm-popover\s*\{/);
    // Vue node mode must switch to the --component-node-* family.
    expect(theme).toContain('.lm-widget-root.lm-vue-node {');
    // Light is the default; dark is keyed on the class ComfyUI puts on <html>.
    expect(theme).toContain('html.dark-theme .lm-widget-root,');
  });
});
