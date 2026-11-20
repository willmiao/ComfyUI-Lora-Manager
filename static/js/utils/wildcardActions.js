import { getModelApiClient, resetAndReload } from '../api/modelApiFactory.js';
import { showToast } from '../utils/uiHelpers.js';

async function fetchActiveResource(filePath) {
    const response = await fetch('/api/lm/wildcards/active');
    const data = await response.json().catch(() => ({}));
    return (data.resources || []).find((item) => item.file_path === filePath) || null;
}

/**
 * Open the shared model modal, optionally scrolling to its wildcard browser.
 */
export async function openWildcardModel(filePath, { openWildcardsSection = false } = {}) {
    try {
        const { showModelModal } = await import('../components/shared/ModelModal.js');
        let model = null;
        try {
            model = await fetchActiveResource(filePath);
        } catch (error) {
            console.warn('Failed to fetch the active wildcard resource:', error);
        }
        if (!model) {
            const metadata = await getModelApiClient('wildcards').fetchModelMetadata(filePath);
            model = {
                ...metadata,
                file_path: metadata.file_path || filePath,
                active: false,
                activation_namespace: '',
                activation_aliases: {},
                entries: Array.isArray(metadata.entries) ? metadata.entries : [],
            };
        }
        await showModelModal(model, 'wildcards', { openWildcardsSection });
    } catch (error) {
        console.warn('Failed to open wildcard model:', error);
        showToast(`Failed to open wildcard: ${error.message}`, {}, 'error');
    }
}

export async function deactivateWildcard(filePath) {
    try {
        await getModelApiClient('wildcards').deactivate(filePath);
        showToast('wildcards.messages.deactivated', {}, 'success');
        await resetAndReload(false);
    } catch (error) {
        showToast(`Failed to deactivate wildcard: ${error.message}`, {}, 'error');
    }
}
