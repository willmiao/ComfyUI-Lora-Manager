import { appCore } from './core.js';
import { confirmDelete, closeDeleteModal, confirmExclude, closeExcludeModal } from './utils/modalUtils.js';
import { createPageControls } from './components/controls/index.js';
import { ModelDuplicatesManager } from './components/ModelDuplicatesManager.js';
import { MODEL_TYPES } from './api/apiConfig.js';
import { initActiveFiltersSync } from './utils/activeFiltersSync.js';

// Initialize the Other Models page
class OtherPageManager {
    constructor() {
        // Initialize page controls
        this.pageControls = createPageControls(MODEL_TYPES.OTHER);

        // Initialize the ModelDuplicatesManager
        this.duplicatesManager = new ModelDuplicatesManager(this, MODEL_TYPES.OTHER);

        // Expose only necessary functions to global scope
        this._exposeRequiredGlobalFunctions();
    }

    _exposeRequiredGlobalFunctions() {
        // Minimal set of functions that need to remain global
        window.confirmDelete = confirmDelete;
        window.closeDeleteModal = closeDeleteModal;
        window.confirmExclude = confirmExclude;
        window.closeExcludeModal = closeExcludeModal;

        // Expose duplicates manager
        window.modelDuplicatesManager = this.duplicatesManager;
    }

    async initialize() {
        // Initialize common page features (including context menus)
        appCore.initializePageFeatures();

        // Mirror active filters to the backend for the ComfyUI-side autocomplete
        initActiveFiltersSync(MODEL_TYPES.OTHER);

        console.log('Other Models Manager initialized');
    }
}

async function initializeOtherPage() {
    // Initialize core application
    await appCore.initialize();

    // Initialize other models page
    const otherPage = new OtherPageManager();
    await otherPage.initialize();

    return otherPage;
}

// Initialize everything when DOM is ready
document.addEventListener('DOMContentLoaded', initializeOtherPage);

export { OtherPageManager, initializeOtherPage };
