import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const {
  UI_HELPERS_MODULE,
  UNDO_HELPERS_MODULE,
} = vi.hoisted(() => ({
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  UNDO_HELPERS_MODULE: new URL('../../../static/js/utils/undoHelpers.js', import.meta.url).pathname,
}));

const showToastMock = vi.fn();

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: showToastMock,
}));

describe('handleUndoDelete', () => {
  beforeEach(() => {
    showToastMock.mockReset();
  });

  afterEach(() => {
    delete global.fetch;
  });

  it('posts the batch id, refreshes once, and shows the restored toast on 200', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ success: true, restored: ['/models/foo.safetensors'] }),
    });

    const { handleUndoDelete } = await import(UNDO_HELPERS_MODULE);

    const refreshFn = vi.fn();
    const result = await handleUndoDelete('batch-1', refreshFn);

    expect(result).toBe(true);
    expect(global.fetch).toHaveBeenCalledWith('/api/lm/undo-delete', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ batch_id: 'batch-1' }),
    }));
    expect(refreshFn).toHaveBeenCalledTimes(1);
    expect(showToastMock).toHaveBeenCalledTimes(1);
    expect(showToastMock).toHaveBeenCalledWith('toast.undo.restored', {}, 'success');
  });

  it('shows the expired toast for a 404 whose error body mentions expired', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      json: async () => ({ success: false, error: 'Undo batch expired and was purged' }),
    });

    const { handleUndoDelete } = await import(UNDO_HELPERS_MODULE);

    const refreshFn = vi.fn();
    const result = await handleUndoDelete('batch-gone', refreshFn);

    expect(result).toBe(false);
    expect(refreshFn).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledTimes(1);
    expect(showToastMock).toHaveBeenCalledWith('toast.undo.expired', {}, 'error');
  });

  it('shows the failed toast with the server message for a 404 occupied path', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      json: async () => ({ success: false, error: 'Target path occupied' }),
    });

    const { handleUndoDelete } = await import(UNDO_HELPERS_MODULE);

    const result = await handleUndoDelete('batch-occupied', vi.fn());

    expect(result).toBe(false);
    expect(showToastMock).toHaveBeenCalledTimes(1);
    expect(showToastMock).toHaveBeenCalledWith('toast.undo.failed', { error: 'Target path occupied' }, 'error');
  });

  it('shows the failed toast when the error body is not parseable', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      json: async () => { throw new Error('invalid json'); },
    });

    const { handleUndoDelete } = await import(UNDO_HELPERS_MODULE);

    const result = await handleUndoDelete('batch-malformed', vi.fn());

    expect(result).toBe(false);
    expect(showToastMock).toHaveBeenCalledTimes(1);
    expect(showToastMock).toHaveBeenCalledWith('toast.undo.failed', { error: 'Not Found' }, 'error');
  });

  it('shows the failed toast on network errors', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('connection reset'));

    const { handleUndoDelete } = await import(UNDO_HELPERS_MODULE);

    const refreshFn = vi.fn();
    const result = await handleUndoDelete('batch-net', refreshFn);

    expect(result).toBe(false);
    expect(refreshFn).not.toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalledTimes(1);
    expect(showToastMock).toHaveBeenCalledWith('toast.undo.failed', { error: 'connection reset' }, 'error');
  });

  it('suppresses the toast and refresh when the options disable them', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ success: true }),
    });

    const { handleUndoDelete } = await import(UNDO_HELPERS_MODULE);

    const refreshFn = vi.fn();
    const result = await handleUndoDelete('batch-quiet', refreshFn, { showToast: false, refresh: false });

    expect(result).toBe(true);
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(refreshFn).not.toHaveBeenCalled();
    expect(showToastMock).not.toHaveBeenCalled();
  });
});
