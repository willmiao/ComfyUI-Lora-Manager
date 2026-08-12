import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const {
  SUMMARY_MODULE,
  I18N_HELPERS_MODULE,
  UI_HELPERS_MODULE,
} = vi.hoisted(() => ({
  SUMMARY_MODULE: new URL('../../../static/js/components/DownloadBatchSummaryModal.js', import.meta.url).pathname,
  I18N_HELPERS_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
}));

const showToastMock = vi.hoisted(() => vi.fn());
const openHuggingFaceMock = vi.hoisted(() => vi.fn());

vi.mock(I18N_HELPERS_MODULE, () => ({
  translate: vi.fn((_key, _params, fallback) => fallback ?? ''),
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: showToastMock,
  openHuggingFace: openHuggingFaceMock,
}));

// A realistic failure payload from the backend: a JSON envelope whose `error`
// field embeds an HTTP status and a nested JSON body (Civitai Early Access).
const REAL_ERROR = '{"success": false, "error": "Failed to resolve authenticated Civitai redirect: status=403 body={\\"error\\":\\"Early Access\\",\\"deadline\\":\\"2026-08-12T08:18:36.063Z\\",\\"message\\":\\"This asset is in Early Access. You can use Buzz access it now!\\"}", "download_id": "1786065633067"}';

// The human-readable error the component should derive from REAL_ERROR.
const FORMATTED_REAL_ERROR = 'HTTP 403 — This asset is in Early Access. You can use Buzz access it now!';

describe('DownloadBatchSummaryModal', () => {
  let showDownloadBatchSummary;

  beforeEach(async () => {
    document.body.innerHTML = '';
    showToastMock.mockClear();
    openHuggingFaceMock.mockClear();
    ({ showDownloadBatchSummary } = await import(SUMMARY_MODULE));
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete navigator.clipboard;
    delete document.execCommand;
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('renders a warning summary with stat cards and a failure table on partial success', () => {
    showDownloadBatchSummary({
      total: 3,
      completed: 2,
      failedItems: [
        { item: { displayName: 'LoraA' }, error: 'timeout' },
        { item: { name: 'LoraB' }, error: '404' },
      ],
      onRetry: vi.fn(),
    });

    const modal = document.getElementById('downloadBatchSummaryModal');
    expect(modal).not.toBeNull();
    expect(modal.querySelector('.summary-header').classList.contains('warning')).toBe(true);

    // Success / Failed / Total stat cards.
    const statValues = Array.from(modal.querySelectorAll('.stat-card-value')).map(el => el.textContent);
    expect(statValues).toEqual(['2', '2', '3']);

    const rows = modal.querySelectorAll('.failure-table tbody tr');
    expect(rows).toHaveLength(2);
    expect(rows[0].querySelector('.failure-name').textContent).toBe('LoraA');
    expect(rows[0].querySelector('.failure-error').textContent).toBe('timeout');
    expect(rows[1].querySelector('.failure-name').textContent).toBe('LoraB');
    expect(rows[1].querySelector('.failure-error').textContent).toBe('404');

    expect(modal.querySelector('[data-action="retry-failed"]').textContent).toContain('Retry Failed (2)');
    expect(modal.querySelector('[data-action="copy-report"]')).not.toBeNull();
  });

  it('renders an error header when every download failed', () => {
    showDownloadBatchSummary({
      total: 2,
      completed: 0,
      failedItems: [
        { item: { displayName: 'LoraA' }, error: 'timeout' },
        { item: { displayName: 'LoraB' }, error: '404' },
      ],
      onRetry: vi.fn(),
    });

    const modal = document.getElementById('downloadBatchSummaryModal');
    expect(modal.querySelector('.summary-header').classList.contains('error')).toBe(true);
    expect(modal.querySelector('.summary-title').textContent).toBe('Download failed');
  });

  it('renders a success summary without a failure table or retry button', () => {
    showDownloadBatchSummary({ total: 2, completed: 2, failedItems: [], onRetry: vi.fn() });

    const modal = document.getElementById('downloadBatchSummaryModal');
    expect(modal.querySelector('.summary-header').classList.contains('success')).toBe(true);
    expect(modal.querySelector('.failure-table')).toBeNull();
    expect(modal.querySelector('[data-action="retry-failed"]')).toBeNull();
    expect(modal.querySelector('.refresh-success-message')).not.toBeNull();
  });

  it('escapes HTML in failed item names and errors', () => {
    showDownloadBatchSummary({
      total: 1,
      completed: 0,
      failedItems: [
        { item: { name: '<img src=x onerror=alert(1)>', url: 'https://example.com/xss-model' }, error: '<script>bad()</script>' },
      ],
      onRetry: vi.fn(),
    });

    const nameCell = document.querySelector('.failure-name');
    const errorCell = document.querySelector('.failure-error');

    // The URL resolves, so the name renders inside the failure link; the
    // escaped entities must render back to the literal payload as text...
    expect(nameCell.querySelector('a.failure-link')).not.toBeNull();
    expect(nameCell.textContent).toContain('<img src=x onerror=alert(1)>');
    expect(errorCell.textContent).toContain('<script>bad()</script>');
    // ...and never as live DOM nodes.
    expect(document.querySelector('.failure-table img')).toBeNull();
    expect(document.querySelector('.failure-table script')).toBeNull();
    expect(nameCell.innerHTML).toContain('&lt;img');
  });

  it('removes the modal and invokes onRetry with the original failed items', () => {
    const onRetry = vi.fn();
    const failedItems = [{ item: { displayName: 'LoraA' }, error: 'timeout' }];
    showDownloadBatchSummary({ total: 3, completed: 2, failedItems, onRetry });

    document.querySelector('[data-action="retry-failed"]').click();

    expect(document.getElementById('downloadBatchSummaryModal')).toBeNull();
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(onRetry).toHaveBeenCalledWith(failedItems);
    // Same object references, not copies.
    expect(onRetry.mock.calls[0][0][0]).toBe(failedItems[0]);
  });

  it('closes the modal via the close action without retrying', () => {
    const onRetry = vi.fn();
    showDownloadBatchSummary({
      total: 2,
      completed: 1,
      failedItems: [{ item: { name: 'LoraA' }, error: 'timeout' }],
      onRetry,
    });

    document.querySelector('.cancel-btn[data-action="close-modal"]').click();

    expect(document.getElementById('downloadBatchSummaryModal')).toBeNull();
    expect(onRetry).not.toHaveBeenCalled();
  });

  it('copies a plain-text batch report to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });

    showDownloadBatchSummary({
      total: 3,
      completed: 2,
      failedItems: [
        { item: { displayName: 'LoraA', url: 'https://civitai.red/models/111/lora-a?modelVersionId=222' }, error: 'timeout' },
        { item: { name: 'LoraB', url: 'https://example.com/lora-b' }, error: '404' },
      ],
      onRetry: vi.fn(),
    });

    document.querySelector('[data-action="copy-report"]').click();

    // writeText is invoked synchronously by the click handler.
    expect(writeText).toHaveBeenCalledTimes(1);
    const text = writeText.mock.calls[0][0];
    expect(text).toContain('Batch Download Report');
    expect(text).toContain('Total: 3');
    expect(text).toContain('LoraA — timeout');
    expect(text).toContain('LoraB — 404');

    // Each failed item with a URL gets an indented URL line right after it.
    expect(text).toContain('   URL: https://civitai.red/models/111/lora-a?modelVersionId=222');
    expect(text).toContain('   URL: https://example.com/lora-b');
    // Exactly the two URLs from the failed items — nothing more, no undefined.
    expect(text.match(/^\s+URL:/gm)).toHaveLength(2);
    expect(text).not.toContain('URL: undefined');

    // The toast fires after the mocked clipboard promise settles.
    await vi.waitFor(() => expect(showToastMock).toHaveBeenCalledTimes(1));
    expect(showToastMock).toHaveBeenCalledWith('toast.api.copiedToClipboard', {}, 'success');
  });

  it('omits the URL line for failed items without a resolvable url', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });

    showDownloadBatchSummary({
      total: 2,
      completed: 0,
      failedItems: [
        { item: { name: 'WithUrl', url: 'https://example.com/with-url' }, error: 'boom' },
        { item: { name: 'NoUrl' }, error: 'boom' },
      ],
      onRetry: vi.fn(),
    });

    document.querySelector('[data-action="copy-report"]').click();

    const text = writeText.mock.calls[0][0];
    expect(text).toContain('   URL: https://example.com/with-url');
    // Only the one URL line exists — the URL-less item contributes none.
    expect(text.match(/^\s+URL:/gm)).toHaveLength(1);
    expect(text).not.toContain('   URL: undefined');
    expect(text).not.toContain('   URL: null');

    await vi.waitFor(() => expect(showToastMock).toHaveBeenCalledTimes(1));
  });

  it('falls back to execCommand when navigator.clipboard is unavailable', async () => {
    // afterEach deletes navigator.clipboard, but be explicit so this test is
    // robust even if a previous test failed before its cleanup ran.
    delete navigator.clipboard;
    // jsdom does not implement document.execCommand, so install a mock for the
    // fallback path (removed by the afterEach cleanup above).
    const execCommandMock = vi.fn(() => true);
    document.execCommand = execCommandMock;

    showDownloadBatchSummary({
      total: 3,
      completed: 2,
      failedItems: [
        { item: { displayName: 'LoraA' }, error: 'timeout' },
        { item: { name: 'LoraB' }, error: '404' },
      ],
      onRetry: vi.fn(),
    });

    document.querySelector('[data-action="copy-report"]').click();

    // Without the async Clipboard API the fallback must run synchronously.
    expect(execCommandMock).toHaveBeenCalledWith('copy');

    await Promise.resolve();
    await Promise.resolve();

    expect(showToastMock).toHaveBeenCalledWith('toast.api.copiedToClipboard', {}, 'success');
  });

  it('keeps only a single modal instance across repeated calls', () => {
    showDownloadBatchSummary({
      total: 2,
      completed: 1,
      failedItems: [{ item: { name: 'A' }, error: 'e' }],
      onRetry: vi.fn(),
    });
    showDownloadBatchSummary({ total: 3, completed: 3, failedItems: [], onRetry: vi.fn() });

    expect(document.querySelectorAll('#downloadBatchSummaryModal')).toHaveLength(1);
    const modal = document.getElementById('downloadBatchSummaryModal');
    expect(modal.querySelector('.summary-header').classList.contains('success')).toBe(true);
  });

  it('resolves failure names from entry.name, item fields, URL paths, or Unknown', () => {
    showDownloadBatchSummary({
      total: 4,
      completed: 0,
      failedItems: [
        { name: 'entryName', item: { displayName: 'ItemName' }, error: 'e1' },
        { item: { selectedVersion: { name: 'v1.0' } }, error: 'e2' },
        { item: { url: 'https://civitai.red/models/837884/midjourney-artful-nsfw?modelVersionId=3153960' }, error: 'e3' },
        { item: {}, error: 'e4' },
      ],
      onRetry: vi.fn(),
    });

    const names = Array.from(document.querySelectorAll('.failure-name')).map(el => el.textContent);
    expect(names).toEqual(['entryName', 'v1.0', 'midjourney-artful-nsfw', 'Unknown']);
  });

  it('formats the real JSON failure payload into a concise HTTP error and truncates long ones', () => {
    showDownloadBatchSummary({
      total: 2,
      completed: 0,
      failedItems: [
        { item: { name: 'EarlyAccess' }, error: REAL_ERROR },
        { item: { name: 'LongError' }, error: 'x'.repeat(300) },
      ],
      onRetry: vi.fn(),
    });

    const errorCells = document.querySelectorAll('.failure-error');
    expect(errorCells[0].textContent).toBe(FORMATTED_REAL_ERROR);
    expect(errorCells[1].textContent).toBe('x'.repeat(220) + '…');
  });

  it('keeps the raw error string in the error cell title for debugging', () => {
    showDownloadBatchSummary({
      total: 1,
      completed: 0,
      failedItems: [{ item: { name: 'EarlyAccess' }, error: REAL_ERROR }],
      onRetry: vi.fn(),
    });

    const errorCell = document.querySelector('.failure-error');
    expect(errorCell.getAttribute('title')).toBe(REAL_ERROR);
    expect(errorCell.getAttribute('title')).not.toBe(FORMATTED_REAL_ERROR);
  });

  it('opens the original item url in a new tab when a failure link is clicked', () => {
    showDownloadBatchSummary({
      total: 1,
      completed: 0,
      failedItems: [{
        item: {
          url: 'https://civitai.red/models/837884/midjourney-artful-nsfw?modelVersionId=3153960',
          modelId: '837884',
          selectedVersion: { id: '3153960' },
        },
        error: 'rate limited',
      }],
      onRetry: vi.fn(),
    });

    document.querySelector('.failure-link').click();

    expect(openHuggingFaceMock).toHaveBeenCalledTimes(1);
    expect(openHuggingFaceMock).toHaveBeenCalledWith('https://civitai.red/models/837884/midjourney-artful-nsfw?modelVersionId=3153960');
    // The modal stays open so the user can keep inspecting the failures.
    expect(document.getElementById('downloadBatchSummaryModal')).not.toBeNull();
  });

  it('opens the item url directly when selectedVersion is absent', () => {
    showDownloadBatchSummary({
      total: 1,
      completed: 0,
      failedItems: [{
        item: {
          modelId: '837884',
          modelVersionId: '3153960',
          url: 'https://civitai.red/models/837884/midjourney-artful-nsfw',
        },
        error: 'rate limited',
      }],
      onRetry: vi.fn(),
    });

    document.querySelector('.failure-link').click();

    expect(openHuggingFaceMock).toHaveBeenCalledTimes(1);
    expect(openHuggingFaceMock).toHaveBeenCalledWith('https://civitai.red/models/837884/midjourney-artful-nsfw');
    expect(document.getElementById('downloadBatchSummaryModal')).not.toBeNull();
  });

  it('opens the original huggingface url directly when a huggingface failure link is clicked', () => {
    showDownloadBatchSummary({
      total: 1,
      completed: 0,
      failedItems: [{
        item: {
          url: 'https://huggingface.co/user/repo',
          source: 'huggingface',
          repo: 'user/repo',
          filename: 'model.safetensors',
          revision: 'main',
        },
        error: 'download failed',
      }],
      onRetry: vi.fn(),
    });

    document.querySelector('.failure-link').click();

    expect(openHuggingFaceMock).toHaveBeenCalledTimes(1);
    expect(openHuggingFaceMock).toHaveBeenCalledWith('https://huggingface.co/user/repo');
    expect(document.getElementById('downloadBatchSummaryModal')).not.toBeNull();
  });

  it('opens an arbitrary URL via openHuggingFace for fallback items', () => {
    showDownloadBatchSummary({
      total: 1,
      completed: 0,
      failedItems: [{ item: { url: 'https://example.com/model' }, error: 'boom' }],
      onRetry: vi.fn(),
    });

    document.querySelector('.failure-link').click();

    expect(openHuggingFaceMock).toHaveBeenCalledTimes(1);
    expect(openHuggingFaceMock).toHaveBeenCalledWith('https://example.com/model');
  });

  it('renders the failure name as plain text when no URL can be resolved', () => {
    showDownloadBatchSummary({
      total: 1,
      completed: 0,
      failedItems: [{ item: { modelId: null }, error: 'boom' }],
      onRetry: vi.fn(),
    });

    expect(document.querySelector('a.failure-link')).toBeNull();
    expect(document.querySelector('.failure-name').textContent).toBe('Unknown');

    // Without a link there is nothing to open: clicking the cell is inert.
    document.querySelector('.failure-name').click();
    expect(openHuggingFaceMock).not.toHaveBeenCalled();
  });

  it('copies formatted errors (not raw JSON) into the report text', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });

    showDownloadBatchSummary({
      total: 1,
      completed: 0,
      failedItems: [{
        item: {
          name: 'EarlyAccess',
          url: 'https://civitai.red/models/123/early-access?modelVersionId=456',
        },
        error: REAL_ERROR,
      }],
      onRetry: vi.fn(),
    });

    document.querySelector('[data-action="copy-report"]').click();

    expect(writeText).toHaveBeenCalledTimes(1);
    const text = writeText.mock.calls[0][0];
    expect(text).toContain(FORMATTED_REAL_ERROR);
    expect(text).toContain('   URL: https://civitai.red/models/123/early-access?modelVersionId=456');
    expect(text).not.toContain('download_id');
    expect(text).not.toContain('Failed to resolve authenticated Civitai redirect');

    await vi.waitFor(() => expect(showToastMock).toHaveBeenCalledTimes(1));
  });
});
