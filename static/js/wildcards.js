import { appCore } from './core.js';
import { confirmDelete, closeDeleteModal, confirmExclude, closeExcludeModal } from './utils/modalUtils.js';
import { createPageControls } from './components/controls/index.js';
import { ModelDuplicatesManager } from './components/ModelDuplicatesManager.js';
import { MODEL_TYPES } from './api/apiConfig.js';
import { initActiveFiltersSync } from './utils/activeFiltersSync.js';
import { initializeWildcardDetails } from './utils/wildcardActions.js';
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
        initializeWildcardDetails();
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

async function initializeWildcardsPage() {
    await appCore.initialize();
    document.getElementById('enableWildcardsBtn')?.addEventListener('click', enableWildcards);
    document.getElementById('openWildcardsSettingsBtn')?.addEventListener('click', openWildcardsSettings);
    if (!document.getElementById('modelGrid')) return;
    const manager = new WildcardsPageManager();
    await manager.initialize();
    return manager;
}

document.addEventListener('DOMContentLoaded', initializeWildcardsPage);

export { WildcardsPageManager, initializeWildcardsPage };
