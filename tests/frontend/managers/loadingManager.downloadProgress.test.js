import { beforeEach, describe, expect, it, vi } from 'vitest';

const { I18N_MODULE } = vi.hoisted(() => ({
  I18N_MODULE: new URL(
    '../../../static/js/utils/i18nHelpers.js',
    import.meta.url
  ).pathname,
}));

// Interpolate the English fallback the way the real helper does when a locale
// has not been loaded, so assertions can name the visible text.
vi.mock(I18N_MODULE, () => ({
  translate: vi.fn((key, params = {}, fallback) => {
    if (typeof fallback !== 'string') return key;
    return Object.entries(params).reduce(
      (text, [name, value]) => text.replace(`{${name}}`, String(value)),
      fallback
    );
  }),
}));

const { LoadingManager } = await import(
  '../../../static/js/managers/LoadingManager.js'
);

/**
 * A download's byte counter stops when the last byte lands, but the backend
 * still hashes the file and reads the model site's API. These tests pin the
 * rendering that says so, instead of leaving the bar at 100% showing 0 B/s.
 */
describe('LoadingManager download progress phases', () => {
  let manager;
  let updateProgress;

  beforeEach(() => {
    document.body.innerHTML = '';
    LoadingManager.instance = null;
    manager = new LoadingManager();
    updateProgress = manager.showDownloadProgress(1);
  });

  const speedText = () =>
    document.querySelector('.download-transfer-speed')?.textContent;
  const itemLabel = () =>
    document.querySelector('.current-item-label')?.textContent;
  const itemPercent = () =>
    document.querySelector('.current-item-percent')?.textContent;
  const itemBar = () => document.querySelector('.current-item-bar');

  it('shows the byte rate while transferring', () => {
    updateProgress(42, 0, 'model.safetensors', {
      bytesDownloaded: 1024,
      totalBytes: 2048,
      bytesPerSecond: 512,
    });

    expect(itemLabel()).toBe('Downloading: model.safetensors');
    expect(itemPercent()).toBe('42%');
    expect(speedText()).toMatch(/^Speed: /);
    expect(itemBar().classList.contains('is-indeterminate')).toBe(false);
  });

  it('names the indexing stage instead of a stopped speed', () => {
    updateProgress(100, 0, 'model.safetensors', {}, {
      phase: 'metadata',
      stage: 'indexing',
      platform: 'modelscope',
    });

    expect(itemLabel()).toBe('Metadata: model.safetensors');
    expect(itemPercent()).toBe('100%');
    expect(speedText()).toBe('Reading model file...');
    expect(manager.statusText.textContent).toBe('Reading model file...');
    expect(itemBar().classList.contains('is-indeterminate')).toBe(true);
  });

  it('names the site the metadata is fetched from', () => {
    updateProgress(100, 0, 'model.safetensors', {}, {
      phase: 'metadata',
      stage: 'source',
      platform: 'modelscope-ai',
    });

    expect(speedText()).toBe('Fetching metadata from ModelScope (International)...');
  });

  it('falls back to a generic message for an unknown site', () => {
    updateProgress(100, 0, 'model.safetensors', {}, {
      phase: 'metadata',
      stage: 'source',
      platform: '',
    });

    expect(speedText()).toBe('Fetching metadata...');
  });

  it('returns to the transfer rendering for the next file', () => {
    updateProgress(100, 0, 'a.safetensors', {}, {
      phase: 'metadata',
      stage: 'source',
      platform: 'modelscope',
    });

    updateProgress(0, 1, 'b.safetensors');

    expect(itemLabel()).toBe('Downloading: b.safetensors');
    expect(speedText()).toMatch(/^Speed: /);
    expect(itemBar().classList.contains('is-indeterminate')).toBe(false);
  });

  it('keeps the byte counters visible during the metadata stage', () => {
    updateProgress(100, 0, 'model.safetensors', {
      bytesDownloaded: 2048,
      totalBytes: 2048,
      bytesPerSecond: 0,
    }, {
      phase: 'metadata',
      stage: 'source',
      platform: 'modelscope',
    });

    const transferred = document.querySelector('.download-transfer-bytes');
    expect(transferred.textContent).toContain('/');
    // The 0 B/s figure is what made the pause look like a stall.
    expect(speedText()).not.toContain('0 B');
  });

  it('keeps the batch position visible in the status line', () => {
    updateProgress = manager.showDownloadProgress(4);

    updateProgress(100, 2, 'c.safetensors', {}, {
      phase: 'metadata',
      stage: 'source',
      platform: 'huggingface',
    });

    expect(manager.statusText.textContent).toBe(
      '3/4: Fetching metadata from Hugging Face...'
    );
  });
});
