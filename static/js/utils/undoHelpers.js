import { showToast } from './uiHelpers.js';

/**
 * Undo a staged delete batch via the pending-delete endpoint.
 * @param {string} batchId - The batch id returned by a staged delete response
 * @param {Function|null} refreshFn - Called once after a successful restore (unless options.refresh is false)
 * @param {Object} [options]
 * @param {boolean} [options.showToast=true] - Suppress toasts (used by sequential multi-batch undo loops)
 * @param {boolean} [options.refresh=true] - Suppress the refresh call (used by sequential multi-batch undo loops)
 * @returns {Promise<boolean>} Whether the undo succeeded
 */
export async function handleUndoDelete(batchId, refreshFn, options = {}) {
  const { showToast: showToastEnabled = true, refresh: refreshEnabled = true } = options;

  try {
    const response = await fetch('/api/lm/undo-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ batch_id: batchId }),
    });

    if (response.ok) {
      if (refreshEnabled && typeof refreshFn === 'function') {
        refreshFn();
      }
      if (showToastEnabled) {
        showToast('toast.undo.restored', {}, 'success');
      }
      return true;
    }

    // Read the error body to distinguish an expired batch from other failures
    let errorMessage = '';
    try {
      const body = await response.json();
      errorMessage = body?.error || '';
    } catch {
      errorMessage = '';
    }

    if (showToastEnabled) {
      if (response.status === 404 && errorMessage.toLowerCase().includes('expired')) {
        showToast('toast.undo.expired', {}, 'error');
      } else {
        showToast('toast.undo.failed', { error: errorMessage || response.statusText }, 'error');
      }
    }
    return false;
  } catch (error) {
    if (showToastEnabled) {
      showToast('toast.undo.failed', { error: error.message }, 'error');
    }
    return false;
  }
}
