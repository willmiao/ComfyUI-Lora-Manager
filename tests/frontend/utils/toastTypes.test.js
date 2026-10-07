import { describe, it, expect, vi, beforeEach } from 'vitest';

const { UI_HELPERS_MODULE, I18N_MODULE } = vi.hoisted(() => ({
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
}));

vi.mock(I18N_MODULE, () => ({
  translate: vi.fn((key, params, fallback) => fallback || key),
}));

const { showToast } = await import(UI_HELPERS_MODULE);

describe('toast type styling', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('applies the requested type class', () => {
    showToast('plain message', {}, 'success');
    expect(document.querySelector('.toast').className).toBe('toast toast-success');
  });

  it('coerces an unknown type to info instead of rendering an unstyled toast', () => {
    // Regression guard: a call site that passed its fallback sentence as the
    // `type` produced `toast toast-drive-Z is not reachable ...`, which matched
    // no rule at all (no icon, no accent border).
    showToast('plain message', {}, 'drive-Z is not reachable right now');
    expect(document.querySelector('.toast').className).toBe('toast toast-info');
  });

  it('defaults to info when no type is given', () => {
    showToast('plain message');
    expect(document.querySelector('.toast').className).toBe('toast toast-info');
  });
});
