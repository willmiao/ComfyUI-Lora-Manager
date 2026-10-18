import { describe, it, expect, vi, beforeEach } from 'vitest';

const { I18N_MODULE, MODULE } = vi.hoisted(() => ({
  I18N_MODULE: new URL('../../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  MODULE: new URL('../../../../static/js/components/controls/ScanScopeMenu.js', import.meta.url).pathname,
}));

vi.mock(I18N_MODULE, () => ({
  translate: vi.fn((key, params, fallback) => {
    if (!fallback) {
      return key;
    }
    return Object.entries(params || {}).reduce(
      (text, [name, value]) => text.replaceAll(`{${name}}`, value),
      fallback
    );
  }),
}));

const { renderScanScopeMenu, resolveScanScopeTarget } = await import(MODULE);
const { i18n } = await import(
  new URL('../../../../static/js/i18n/index.js', import.meta.url).pathname
);

describe('ScanScopeMenu', () => {
  let menu;

  beforeEach(() => {
    document.body.innerHTML = '<div id="refreshScopeMenu"></div>';
    menu = document.getElementById('refreshScopeMenu');
  });

  it('renders one row per root with label, count and offline state', () => {
    renderScanScopeMenu(menu, [
      { path: '/mnt/a/loras', label: 'a/loras', reachable: true, models: 7 },
      { path: '/mnt/b/loras', label: 'b/loras', reachable: false, models: 0 },
    ]);

    const rows = menu.querySelectorAll('.scan-root-item');
    expect(rows.length).toBe(2);

    expect(rows[0].dataset.action).toBe('scan-root');
    expect(rows[0].dataset.root).toBe('/mnt/a/loras');
    // Tooltip is always two lines: full path, then the exact count.
    expect(rows[0].title).toBe('/mnt/a/loras\n7 models');
    expect(rows[0].querySelector('.scan-root-label').textContent).toBe('a/loras');
    expect(rows[0].querySelector('.scan-root-count').textContent).toBe('7 models');
    expect(rows[0].classList.contains('is-offline')).toBe(false);

    expect(rows[1].classList.contains('is-offline')).toBe(true);
    expect(rows[1].querySelector('.scan-root-offline').textContent).toBe('Offline');
    // Offline rows stay clickable so the click can explain the state.
    expect(rows[1].dataset.action).toBe('scan-root');
  });

  it('abbreviates five digit counts and keeps the exact value in the row tooltip', async () => {
    // The abbreviation itself is locale specific (K vs 万), so pin it.
    const originalLocale = i18n.currentLocale;
    i18n.currentLocale = 'en';
    try {
      renderScanScopeMenu(menu, [
        { path: '/mnt/a/loras', label: 'a/loras', reachable: true, models: 12345 },
        { path: '/mnt/b/loras', label: 'b/loras', reachable: true, models: 42 },
      ]);

      const rows = menu.querySelectorAll('.scan-root-item');
      expect(rows[0].querySelector('.scan-root-count').textContent).toBe('12.3K models');
      // Path stays in the tooltip; the exact count is always the second line, so
      // the tooltip has the same shape at every magnitude.
      expect(rows[0].title).toBe('/mnt/a/loras\n12,345 models');

      expect(rows[1].querySelector('.scan-root-count').textContent).toBe('42 models');
      expect(rows[1].title).toBe('/mnt/b/loras\n42 models');
    } finally {
      i18n.currentLocale = originalLocale;
    }
  });

  it('resolveScanScopeTarget reads path, label and offline state', () => {
    renderScanScopeMenu(menu, [
      { path: '/mnt/b/loras', label: 'b/loras', reachable: false, models: 0 },
    ]);

    expect(resolveScanScopeTarget(menu.querySelector('.scan-root-item'))).toEqual({
      rootPath: '/mnt/b/loras',
      label: 'b/loras',
      offline: true,
    });
  });

  it('skips malformed entries and replaces the previous list', () => {
    renderScanScopeMenu(menu, [{ path: '/mnt/a' }, null, {}]);
    expect(menu.querySelectorAll('.scan-root-item').length).toBe(1);

    renderScanScopeMenu(menu, []);
    expect(menu.querySelectorAll('.scan-root-item').length).toBe(0);
  });

  it('falls back to the path when a root has no label', () => {
    renderScanScopeMenu(menu, [{ path: '/mnt/a/loras', reachable: true, models: 0 }]);

    expect(menu.querySelector('.scan-root-label').textContent).toBe('/mnt/a/loras');
  });
});
