import { beforeEach, describe, expect, it, vi } from 'vitest';

const { I18N_MODULE } = vi.hoisted(() => ({
  I18N_MODULE: new URL(
    '../../../static/js/utils/i18nHelpers.js',
    import.meta.url
  ).pathname,
}));

vi.mock(I18N_MODULE, () => ({
  translate: vi.fn((key, params, fallback) => fallback || key),
}));

const { LoadingManager } = await import(
  '../../../static/js/managers/LoadingManager.js'
);

describe('LoadingManager refresh progress', () => {
  let manager;

  beforeEach(() => {
    document.body.innerHTML = `
      <div id="loading-overlay" class="loading-overlay" style="display: none;">
        <div class="loading-content">
          <div class="loading-spinner"></div>
          <div class="loading-status"></div>
          <div class="loading-progress-row">
            <div class="progress-container">
              <div class="progress-bar" role="progressbar"></div>
            </div>
            <span class="loading-progress-percent" hidden></span>
          </div>
          <div class="loading-eta" hidden></div>
        </div>
      </div>
    `;
    LoadingManager.instance = null;
    manager = new LoadingManager();
    manager.show('Refreshing LoRAs...', 0);
  });

  it('switches from a spinner to a progress bar with a separate percentage and ETA', () => {
    manager.setIndeterminate(true);

    expect(manager.spinner.style.display).toBe('');
    expect(manager.progressBar.style.display).toBe('none');
    expect(manager.progressPercent.hidden).toBe(true);

    manager.setIndeterminate(false);
    manager.setProgress(42.4, { showPercent: true });
    manager.setStatus('Checking for changes... Z: loras (256 files)', 'Estimating time...');

    expect(manager.spinner.style.display).toBe('none');
    expect(manager.progressBar.style.display).toBe('block');
    expect(manager.progressBar.getAttribute('aria-valuenow')).toBe('42.4');
    expect(manager.progressPercent.hidden).toBe(false);
    expect(manager.progressPercent.textContent).toBe('42%');
    expect(manager.statusText.textContent).toBe('Checking for changes... Z: loras (256 files)');
    expect(manager.etaText.hidden).toBe(false);
    expect(manager.etaText.textContent).toBe('Estimating time...');

    manager.setStatus('Done');
    expect(manager.etaText.hidden).toBe(true);
    expect(manager.etaText.textContent).toBe('');
  });

  it('restores the default loading display and hides opt-in progress details on reset', () => {
    manager.setIndeterminate(false);
    manager.setProgress(75, { showPercent: true });
    manager.setStatus('Checking for changes...', '~2 min remaining');

    manager.hide();

    expect(manager.spinner.style.display).toBe('');
    expect(manager.progressBar.style.display).toBe('block');
    expect(manager.progressPercent.hidden).toBe(true);
    expect(manager.progressPercent.textContent).toBe('');
    expect(manager.etaText.hidden).toBe(true);

    manager.setProgress(25);
    expect(manager.spinner.style.display).toBe('');
    expect(manager.progressPercent.hidden).toBe(true);
  });
});
