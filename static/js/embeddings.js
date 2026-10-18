import { appCore } from './core.js';
import { confirmDelete, closeDeleteModal, confirmExclude, closeExcludeModal } from './utils/modalUtils.js';
import { createPageControls } from './components/controls/index.js';
import { ModelDuplicatesManager } from './components/ModelDuplicatesManager.js';
import { MODEL_TYPES } from './api/apiConfig.js';
import { initActiveFiltersSync } from './utils/activeFiltersSync.js';

// Initialize the Embeddings page
class EmbeddingsPageManager {
    constructor() {
        // Initialize page controls
        this.pageControls = createPageControls(MODEL_TYPES.EMBEDDING);
        
        // Initialize the ModelDuplicatesManager
        this.duplicatesManager = new ModelDuplicatesManager(this, MODEL_TYPES.EMBEDDING);
        
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
        initActiveFiltersSync(MODEL_TYPES.EMBEDDING);

        console.log('Embeddings Manager initialized');
    }
}

async function initializeEmbeddingsPage() {
    // Initialize core application
    await appCore.initialize();

    // Initialize embeddings page
    const embeddingsPage = new EmbeddingsPageManager();
    await embeddingsPage.initialize();

    return embeddingsPage;
}

// Initialize everything when DOM is ready
document.addEventListener('DOMContentLoaded', initializeEmbeddingsPage);

export { EmbeddingsPageManager, initializeEmbeddingsPage };
