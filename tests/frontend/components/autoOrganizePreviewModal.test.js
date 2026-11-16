import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const {
  PREVIEW_MODULE,
  I18N_HELPERS_MODULE,
  UI_HELPERS_MODULE,
} = vi.hoisted(() => ({
  PREVIEW_MODULE: new URL('../../../static/js/components/AutoOrganizePreviewModal.js', import.meta.url).pathname,
  I18N_HELPERS_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
}));

const showToastMock = vi.hoisted(() => vi.fn());

vi.mock(I18N_HELPERS_MODULE, () => ({
  translate: vi.fn((key, params = {}, fallback) => {
    const text = fallback ?? key;
    return Object.entries(params).reduce(
      (result, [name, value]) => result.replaceAll(`{${name}}`, value),
      text
    );
  }),
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: showToastMock,
}));

function makeResult({ moves, results, skipped, failures, total } = {}) {
  const plannedMoves = moves || [
    { model: 'Model A', from: '/models/inbox/a.safetensors', to: '/models/SDXL/a.safetensors', status: 'planned_move', reason: 'path_template' },
    { model: 'Model B', from: '/models/inbox/b.safetensors', to: '/models/SDXL/b.safetensors', status: 'planned_move', reason: 'path_template' },
  ];
  const issueResults = results || [
    { model: 'Model C', success: false, status: 'skipped', message: 'Skipped - insufficient metadata', reason: 'missing_metadata' },
  ];
  const resultSkippedCount = issueResults.filter((item) => (
    item.status === 'skipped' || ['already_organized', 'missing_metadata', 'path_too_long'].includes(item.reason)
  )).length;
  const skippedCount = skipped ?? resultSkippedCount;
  const failureCount = failures ?? issueResults.length - resultSkippedCount;
  return {
    success: true,
    dry_run: true,
    summary: {
      total: total ?? plannedMoves.length + issueResults.length,
      success: plannedMoves.length,
      skipped: skippedCount,
      failures: failureCount,
      operation_type: 'bulk',
      organization_type: 'structured',
      path_template: '{base_model}/{first_tag}',
    },
    planned_moves: plannedMoves,
    results: issueResults,
  };
}

describe('AutoOrganizePreviewModal', () => {
  let AutoOrganizePreviewModal;
  let modal;

  beforeEach(async () => {
    vi.clearAllMocks();
    Element.prototype.scrollIntoView = vi.fn();
    ({ AutoOrganizePreviewModal } = await import(PREVIEW_MODULE));
  });

  afterEach(() => {
    modal?.close();
    delete navigator.clipboard;
    delete document.execCommand;
  });

  function createModal(options = {}) {
    modal = new AutoOrganizePreviewModal(options);
    modal.showLoading();
    return modal;
  }

  it('shows the actual template once and keeps move rows free of repeated reasons', async () => {
    const onApply = vi.fn();
    createModal({ onApply }).showResult(makeResult());

    const root = document.getElementById('autoOrganizePreviewModal');
    expect(root.querySelector('.auto-organize-preview-loading')).toBeNull();
    expect(Array.from(root.querySelectorAll('.stat-card-value')).map((el) => el.textContent)).toEqual(['2', '1', '0']);
    expect(root.querySelectorAll('.auto-organize-preview-row')).toHaveLength(2);
    expect(root.textContent).toContain('/models/inbox/a.safetensors');
    expect(root.textContent).toContain('/models/SDXL/a.safetensors');
    expect(root.querySelector('.auto-organize-preview-reason')).toBeNull();
    expect(root.querySelector('.auto-organize-preview-reason-description')).toBeNull();
    expect(root.querySelector('.auto-organize-preview-rule').textContent).toContain('Organizing with:');
    expect(root.querySelector('.auto-organize-preview-rule code').textContent).toBe('{base_model}/{first_tag}');
    expect(root.querySelector('[data-action="apply"]').textContent).toContain('Organize (2)');
    expect(root.textContent).not.toContain('Current path template and exclusion rules');
    expect(root.querySelector('.modal-content > .auto-organize-preview-actions')).not.toBeNull();
    expect(root.querySelector('.auto-organize-preview-list .auto-organize-preview-actions')).toBeNull();

    root.querySelector('[data-tab="skipped"]').click();
    expect(root.querySelectorAll('.auto-organize-preview-row')).toHaveLength(1);
    expect(root.querySelector('.auto-organize-preview-reason').textContent).toBe('Missing metadata');
    expect(root.querySelector('.auto-organize-preview-rule')).toBeNull();

    root.querySelector('[data-action="apply"]').click();
    await vi.waitFor(() => expect(onApply).toHaveBeenCalledTimes(1));
    expect(document.getElementById('autoOrganizePreviewModal')).toBeNull();
  });

  it('keeps move, skipped, and issue counts aligned with their detailed entries', () => {
    createModal().showResult(makeResult({
      results: [
        {
          model: 'Organized model',
          success: false,
          status: 'skipped',
          reason: 'already_organized',
          message: 'Already in the correct location',
          from: '/models/SDXL/organized.safetensors',
          to: '/models/SDXL/organized.safetensors',
        },
        {
          model: 'Conflicted model',
          success: false,
          status: 'issue',
          reason: 'target_exists',
          message: 'Target file already exists: /models/SDXL/conflicted.safetensors',
        },
      ],
    }));

    const root = document.getElementById('autoOrganizePreviewModal');
    expect(root.querySelector('[data-tab="moves"]').textContent.trim()).toBe('Moves (2)');
    expect(root.querySelector('[data-tab="skipped"]').textContent.trim()).toBe('Skipped (1)');
    expect(root.querySelector('[data-tab="issues"]').textContent.trim()).toBe('Issues (1)');

    root.querySelector('[data-tab="skipped"]').click();
    expect(root.querySelector('.auto-organize-preview-reason').textContent).toBe('Already organized');
    expect(root.querySelector('.auto-organize-preview-message')).toBeNull();
    expect(root.querySelector('.auto-organize-preview-current-path code').textContent).toBe('/models/SDXL/organized.safetensors');

    root.querySelector('[data-tab="issues"]').click();
    expect(root.querySelector('.auto-organize-preview-reason').textContent).toBe('Target already exists');
    expect(root.querySelector('.auto-organize-preview-message').textContent).toContain('/models/SDXL/conflicted.safetensors');
  });

  it('shows the flat-structure rule once without adding row badges', () => {
    const flatResult = makeResult({
      moves: [{ model: 'Flat model', from: '/models/nested/a.st', to: '/models/a.st' }],
      results: [],
      total: 1,
    });
    flatResult.summary.organization_type = 'flat';
    flatResult.summary.path_template = '';
    createModal().showResult(flatResult);

    expect(document.querySelector('.auto-organize-preview-rule code').textContent).toBe('Flat structure (library root)');
    expect(document.querySelector('.auto-organize-preview-reason')).toBeNull();
  });

  it('disables execution when the preview contains no planned moves', () => {
    const onApply = vi.fn();
    createModal({ onApply }).showResult(makeResult({ moves: [], results: [], skipped: 3, total: 3 }));

    const apply = document.querySelector('[data-action="apply"]');
    expect(apply.disabled).toBe(true);
    expect(apply.textContent).toContain('No Moves to Apply');
    expect(document.querySelector('.auto-organize-preview-notice').textContent).toContain('already in the correct location');

    apply.click();
    expect(onApply).not.toHaveBeenCalled();
  });

  it('paginates large plans and filters rows without rendering the whole result set', () => {
    const moves = Array.from({ length: 51 }, (_, index) => ({
      model: `Model ${index}`,
      from: `/inbox/model-${index}.safetensors`,
      to: `/organized/model-${index}.safetensors`,
    }));
    createModal().showResult(makeResult({ moves, results: [], total: 51 }));

    const root = document.getElementById('autoOrganizePreviewModal');
    expect(root.querySelectorAll('.auto-organize-preview-row')).toHaveLength(50);
    root.querySelector('[data-action="next-page"]').click();
    expect(root.querySelectorAll('.auto-organize-preview-row')).toHaveLength(1);
    expect(root.querySelector('.auto-organize-preview-pagination').textContent).toContain('51–51 of 51');

    const search = root.querySelector('[data-role="search"]');
    search.value = 'no matching model';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    expect(root.querySelector('.auto-organize-preview-empty').textContent).toBe('No results match your search.');
  });

  it('escapes model names, paths, and issue messages', () => {
    createModal().showResult(makeResult({
      moves: [{ model: '<img src=x>', from: '<script>from</script>', to: '<script>to</script>' }],
      results: [{ model: '<img src=y>', message: '<script>issue</script>', reason: 'error' }],
      total: 2,
    }));

    const root = document.getElementById('autoOrganizePreviewModal');
    expect(root.querySelector('.auto-organize-preview-model').textContent).toBe('<img src=x>');
    expect(root.querySelector('img')).toBeNull();
    expect(root.querySelector('script')).toBeNull();

    root.querySelector('[data-tab="issues"]').click();
    expect(root.querySelector('.auto-organize-preview-message').textContent).toBe('<script>issue</script>');
    expect(root.querySelector('script')).toBeNull();
  });

  it('shows preview failures inline and retries the same callback', async () => {
    const onRefresh = vi.fn();
    createModal({ onRefresh }).showError(new Error('Auto-organize is already running'));

    expect(document.querySelector('[role="alert"]').textContent).toContain('Auto-organize is already running');
    document.querySelector('[data-action="refresh"]').click();
    await vi.waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1));
  });

  it('copies the complete plan and issue report', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    createModal().showResult(makeResult({ failures: 1 }));

    document.querySelector('[data-action="copy-report"]').click();

    await vi.waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const report = writeText.mock.calls[0][0];
    expect(report).toContain('Auto-Organize Preview Report');
    expect(report).toContain('From: /models/inbox/a.safetensors');
    expect(report).toContain('To: /models/SDXL/b.safetensors');
    expect(report).toContain('[missing_metadata]');
    await vi.waitFor(() => expect(showToastMock).toHaveBeenCalledWith('toast.api.copiedToClipboard', {}, 'success'));
  });

  it('closes with Escape and restores the caller through onClose', () => {
    const onClose = vi.fn();
    createModal({ onClose });

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));

    expect(document.getElementById('autoOrganizePreviewModal')).toBeNull();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
