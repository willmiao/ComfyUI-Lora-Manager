import { appCore } from './core.js';
import { confirmDelete, closeDeleteModal, confirmExclude, closeExcludeModal } from './utils/modalUtils.js';
import { createPageControls } from './components/controls/index.js';
import { ModelDuplicatesManager } from './components/ModelDuplicatesManager.js';
import { MODEL_TYPES } from './api/apiConfig.js';
import { initActiveFiltersSync } from './utils/activeFiltersSync.js';
import { showToast } from './utils/uiHelpers.js';

class WildcardsPageManager {
    constructor() {
        this.pageControls = createPageControls(MODEL_TYPES.WILDCARD);
        this.duplicatesManager = new ModelDuplicatesManager(this, MODEL_TYPES.WILDCARD);
        window.confirmDelete = confirmDelete;
        window.closeDeleteModal = closeDeleteModal;
        window.confirmExclude = confirmExclude;
        window.closeExcludeModal = closeExcludeModal;
        window.modelDuplicatesManager = this.duplicatesManager;
    }

    async initialize() {
        appCore.initializePageFeatures();
        initActiveFiltersSync(MODEL_TYPES.WILDCARD);
    }
}

async function enableWildcards() {
    try {
        const response = await fetch('/api/lm/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enable_wildcards: true }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) throw new Error(data.error || `HTTP ${response.status}`);
        window.location.reload();
    } catch (error) {
        showToast('wildcards.disabled.enableFailed', { message: error.message }, 'error');
    }
}

function openWildcardsSettings() {
    window.modalManager?.showModal('settingsModal');
    setTimeout(() => document.getElementById('wildcardPath')?.scrollIntoView({ block: 'center' }), 100);
}

export async function openLinkedWildcardModel() {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const filePath = params.get('model');
    if (!filePath) return;
    try {
        // Open the wildcard key browser in the shared model modal.
        const { openWildcardModel } = await import('./utils/wildcardActions.js');
        await openWildcardModel(filePath, { openWildcardsSection: true });
    } catch (error) {
        console.warn('Failed to open the linked wildcard:', error);
    } finally {
        if (window.location.hash) {
            history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
        }
    }
}

async function initializeWildcardsPage() {
    await appCore.initialize();
    document.getElementById('enableWildcardsBtn')?.addEventListener('click', enableWildcards);
    document.getElementById('openWildcardsSettingsBtn')?.addEventListener('click', openWildcardsSettings);
    if (!document.getElementById('modelGrid')) return;
    const manager = new WildcardsPageManager();
    await manager.initialize();
    await openLinkedWildcardModel();
    return manager;
}

window.addEventListener('hashchange', openLinkedWildcardModel);
document.addEventListener('DOMContentLoaded', initializeWildcardsPage);

export { WildcardsPageManager, initializeWildcardsPage };
