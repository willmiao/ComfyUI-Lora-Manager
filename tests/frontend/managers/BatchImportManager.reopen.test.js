import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderTemplate } from '../utils/domFixtures.js';

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: vi.fn(),
  setupAutoNewlineOnPaste: vi.fn(),
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: (key, params = {}, fallback = null) => fallback ?? key,
}));

vi.mock('../../../static/js/api/apiConfig.js', () => ({
  WS_ENDPOINTS: {},
}));

vi.mock('../../../static/js/utils/storageHelpers.js', () => ({
  getStorageItem: vi.fn(() => true),
  setStorageItem: vi.fn(),
}));

// jsdom has no WebSocket; the manager only needs open/connecting/close states.
class FakeWebSocket {
  constructor(url) {
    this.url = url;
    this.readyState = 0;
  }
  close() {
    this.readyState = 3;
  }
}
FakeWebSocket.OPEN = 1;
FakeWebSocket.CONNECTING = 0;

const RUNNING_PROGRESS = {
  status: 'running',
  total: 2,
  completed: 1,
  success: 1,
  failed: 0,
  skipped: 0,
  progress_percent: 50,
  current_item: 'image-1.png',
};

const COMPLETED_PROGRESS = {
  status: 'completed',
  total: 2,
  completed: 2,
  success: 2,
  failed: 0,
  skipped: 0,
  progress_percent: 100,
  current_item: '',
};

describe('BatchImportManager reopen behavior (#1084)', () => {
  let modalManager;
  let batchImportManager;
  let fetchMock;

  beforeEach(async () => {
    vi.clearAllMocks();
    vi.resetModules();

    document.body.innerHTML = '';
    renderTemplate('components/batch_import_modal.html');

    // jsdom does not implement window.scrollTo; ModalManager calls it on close.
    window.scrollTo = vi.fn();

    vi.stubGlobal('WebSocket', FakeWebSocket);
    fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({}),
    }));
    vi.stubGlobal('fetch', fetchMock);

    const modalModule = await import('../../../static/js/managers/ModalManager.js');
    modalManager = modalModule.modalManager;
    modalManager.initialize();

    const batchModule = await import('../../../static/js/managers/BatchImportManager.js');
    batchImportManager = new batchModule.BatchImportManager();
  });

  afterEach(() => {
    if (batchImportManager) {
      batchImportManager.cleanupConnections();
    }
    vi.unstubAllGlobals();
  });

  async function startImportViaUrls(urls) {
    batchImportManager.showModal();
    document.getElementById('batchUrlInput').value = urls.join('\n');
    fetchMock.mockImplementation(async (url) => ({
      ok: true,
      status: 200,
      json: async () =>
        url.includes('/batch-import/start')
          ? { success: true, operation_id: 'op-123' }
          : { success: true, progress: RUNNING_PROGRESS },
    }));
    await batchImportManager.startImport();
  }

  it('opens a fresh input form when no operation exists', () => {
    batchImportManager.showModal();
    expect(document.getElementById('batchImportModal').style.display).toBe('block');
    expect(document.getElementById('batchInputStep').style.display).toBe('block');
    expect(document.getElementById('batchProgressStep').style.display).toBe('none');
  });

  it('reopens into the progress view while an import keeps running in the background', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    await startImportViaUrls([
      'https://civitai.com/images/1',
      'https://civitai.com/images/2',
    ]);

    expect(batchImportManager.isImporting).toBe(true);
    expect(batchImportManager.operationId).toBe('op-123');
    expect(document.getElementById('batchProgressStep').style.display).toBe('block');

    // Close the modal the same way the X button does.
    modalManager.closeModal('batchImportModal');
    expect(document.getElementById('batchImportModal').style.display).toBe('none');

    // Closing while running must be visible in the console (#1084).
    const closedWhileRunning = logSpy.mock.calls.some((call) =>
      String(call[0]).includes('Modal closed while import op-123 is still running')
    );
    expect(closedWhileRunning).toBe(true);

    // Reopen: the in-flight operation must be restored, not discarded.
    batchImportManager.showModal();
    expect(document.getElementById('batchImportModal').style.display).toBe('block');
    expect(batchImportManager.operationId).toBe('op-123');
    expect(batchImportManager.isImporting).toBe(true);
    expect(document.getElementById('batchProgressStep').style.display).toBe('block');
    expect(document.getElementById('batchInputStep').style.display).toBe('none');

    logSpy.mockRestore();
  });

  it('reopens into the results view after a background import completes', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    await startImportViaUrls([
      'https://civitai.com/images/1',
      'https://civitai.com/images/2',
    ]);

    // Operation finishes while the modal stays closed.
    modalManager.closeModal('batchImportModal');
    batchImportManager.handleProgressUpdate(RUNNING_PROGRESS);
    batchImportManager.handleProgressUpdate(COMPLETED_PROGRESS);

    expect(batchImportManager.isImporting).toBe(false);
    expect(batchImportManager.results.status).toBe('completed');

    // Reopening shows the finished results instead of a blank form.
    batchImportManager.showModal();
    expect(document.getElementById('batchImportModal').style.display).toBe('block');
    expect(document.getElementById('batchResultsStep').style.display).toBe('block');
    expect(document.getElementById('batchInputStep').style.display).toBe('none');

    logSpy.mockRestore();
  });

  it('does not close when clicking the backdrop (stateful workflow, #1084)', async () => {
    await startImportViaUrls(['https://civitai.com/images/1']);

    const modalEl = document.getElementById('batchImportModal');
    expect(modalEl.style.display).toBe('block');

    // Simulate a backdrop click: mousedown + mouseup on the modal shell.
    // Because batch import is a stateful, multi-step workflow, the modal must
    // not dismiss on stray outside clicks.
    modalEl.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    modalEl.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));

    expect(modalEl.style.display).toBe('block');
    expect(modalManager.isAnyModalOpen()).toBe('batchImportModal');
  });

  it('logs start, progress and completion to the console', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    await startImportViaUrls(['https://civitai.com/images/1']);

    batchImportManager.handleProgressUpdate(RUNNING_PROGRESS);
    // A second poll tick with identical data must not log again (#1084).
    batchImportManager.handleProgressUpdate(RUNNING_PROGRESS);
    batchImportManager.handleProgressUpdate(COMPLETED_PROGRESS);

    const messages = logSpy.mock.calls.map((call) => String(call[0]));
    expect(messages.some((m) => m.includes('[BatchImport] Import started, operation_id=op-123'))).toBe(true);
    expect(messages.filter((m) => m.includes('[BatchImport] Progress 50%')).length).toBe(1);
    expect(messages.some((m) => m.includes('[BatchImport] Import finished: status=completed'))).toBe(true);

    logSpy.mockRestore();
  });
});