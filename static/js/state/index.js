// Create the new hierarchical state structure
import { getStorageItem, getMapFromStorage } from '../utils/storageHelpers.js';
import { MODEL_TYPES } from '../api/apiConfig.js';
import { DEFAULT_PATH_TEMPLATES, DEFAULT_PRIORITY_TAG_CONFIG } from '../utils/constants.js';

const DEFAULT_SETTINGS_BASE = Object.freeze({
    civitai_api_key: '',
    language: 'en',
    show_only_sfw: false,
    enable_metadata_archive_db: false,
    proxy_enabled: false,
    proxy_type: 'http',
    proxy_host: '',
    proxy_port: '',
    proxy_username: '',
    proxy_password: '',
    default_lora_root: '',
    default_checkpoint_root: '',
    default_embedding_root: '',
    base_model_path_mappings: {},
    download_path_templates: {},
    example_images_path: '',
    optimize_example_images: true,
    auto_download_example_images: false,
    blur_mature_content: true,
    autoplay_on_hover: false,
    display_density: 'default',
    card_info_display: 'always',
    model_name_display: 'model_name',
    model_card_footer_action: 'example_images',
    include_trigger_words: false,
    compact_mode: false,
    priority_tags: { ...DEFAULT_PRIORITY_TAG_CONFIG },
});

export function createDefaultSettings() {
    return {
        ...DEFAULT_SETTINGS_BASE,
        base_model_path_mappings: {},
        download_path_templates: { ...DEFAULT_PATH_TEMPLATES },
        priority_tags: { ...DEFAULT_PRIORITY_TAG_CONFIG },
    };
}

// Load preview versions from localStorage for each model type
const loraPreviewVersions = getMapFromStorage('loras_preview_versions');
const checkpointPreviewVersions = getMapFromStorage('checkpoints_preview_versions');
const embeddingPreviewVersions = getMapFromStorage('embeddings_preview_versions');

export const state = {
    // Global state
    global: {
        settings: createDefaultSettings(),
        loadingManager: null,
        observer: null,
    },
    
    // Page-specific states
    pages: {
        [MODEL_TYPES.LORA]: {
            currentPage: 1,
            isLoading: false,
            hasMore: true,
            sortBy: 'name',
            activeFolder: getStorageItem(`${MODEL_TYPES.LORA}_activeFolder`),
            activeLetterFilter: null,
            previewVersions: loraPreviewVersions,
            searchManager: null,
            searchOptions: {
                filename: true,
                modelname: true,
                tags: false,
                creator: false,
                recursive: getStorageItem(`${MODEL_TYPES.LORA}_recursiveSearch`, true),
            },
            filters: {
                baseModel: [],
                tags: []
            },
            bulkMode: false,
            selectedLoras: new Set(),
            loraMetadataCache: new Map(),
            showFavoritesOnly: false,
            showUpdateAvailableOnly: false,
            duplicatesMode: false,
        },
        
        recipes: {
            currentPage: 1,
            isLoading: false,
            hasMore: true,
            sortBy: 'date',
            searchManager: null,
            searchOptions: {
                title: true,
                tags: true,
                loraName: true,
                loraModel: true
            },
            filters: {
                baseModel: [],
                tags: [],
                search: ''
            },
            pageSize: 20,
            showFavoritesOnly: false,
            duplicatesMode: false,
            bulkMode: false,
            selectedModels: new Set(),
        },
        
        [MODEL_TYPES.CHECKPOINT]: {
            currentPage: 1,
            isLoading: false,
            hasMore: true,
            sortBy: 'name',
            activeFolder: getStorageItem(`${MODEL_TYPES.CHECKPOINT}_activeFolder`),
            previewVersions: checkpointPreviewVersions,
            searchManager: null,
            searchOptions: {
                filename: true,
                modelname: true,
                creator: false,
                recursive: getStorageItem(`${MODEL_TYPES.CHECKPOINT}_recursiveSearch`, true),
            },
            filters: {
                baseModel: [],
                tags: []
            },
            modelType: 'checkpoint', // 'checkpoint' or 'diffusion_model'
            bulkMode: false,
            selectedModels: new Set(),
            metadataCache: new Map(),
            showFavoritesOnly: false,
            showUpdateAvailableOnly: false,
            duplicatesMode: false,
        },
        
        [MODEL_TYPES.EMBEDDING]: {
            currentPage: 1,
            isLoading: false,
            hasMore: true,
            sortBy: 'name',
            activeFolder: getStorageItem(`${MODEL_TYPES.EMBEDDING}_activeFolder`),
            activeLetterFilter: null,
            previewVersions: embeddingPreviewVersions,
            searchManager: null,
            searchOptions: {
                filename: true,
                modelname: true,
                tags: false,
                creator: false,
                recursive: getStorageItem(`${MODEL_TYPES.EMBEDDING}_recursiveSearch`, true),
            },
            filters: {
                baseModel: [],
                tags: []
            },
            bulkMode: false,
            selectedModels: new Set(),
            metadataCache: new Map(),
            showFavoritesOnly: false,
            showUpdateAvailableOnly: false,
            duplicatesMode: false,
        }
    },
    
    // Current active page - use MODEL_TYPES constants
    currentPageType: MODEL_TYPES.LORA,
    
    // Backward compatibility - proxy properties
    get currentPage() { return this.pages[this.currentPageType].currentPage; },
    set currentPage(value) { this.pages[this.currentPageType].currentPage = value; },
    
    get isLoading() { return this.pages[this.currentPageType].isLoading; },
    set isLoading(value) { this.pages[this.currentPageType].isLoading = value; },
    
    get hasMore() { return this.pages[this.currentPageType].hasMore; },
    set hasMore(value) { this.pages[this.currentPageType].hasMore = value; },
    
    get sortBy() { return this.pages[this.currentPageType].sortBy; },
    set sortBy(value) { this.pages[this.currentPageType].sortBy = value; },
    
    get activeFolder() { return this.pages[this.currentPageType].activeFolder; },
    set activeFolder(value) { this.pages[this.currentPageType].activeFolder = value; },
    
    get loadingManager() { return this.global.loadingManager; },
    set loadingManager(value) { this.global.loadingManager = value; },
    
    get observer() { return this.global.observer; },
    set observer(value) { this.global.observer = value; },
    
    get previewVersions() { return this.pages.loras.previewVersions; },
    set previewVersions(value) { this.pages.loras.previewVersions = value; },
    
    get searchManager() { return this.pages[this.currentPageType].searchManager; },
    set searchManager(value) { this.pages[this.currentPageType].searchManager = value; },
    
    get searchOptions() { return this.pages[this.currentPageType].searchOptions; },
    set searchOptions(value) { this.pages[this.currentPageType].searchOptions = value; },
    
    get filters() { return this.pages[this.currentPageType].filters; },
    set filters(value) { this.pages[this.currentPageType].filters = value; },
    
    get bulkMode() { 
        const currentType = this.currentPageType;
        if (currentType === MODEL_TYPES.LORA) {
            return this.pages.loras.bulkMode;
        } else {
            return this.pages[currentType].bulkMode;
        }
    },
    set bulkMode(value) { 
        const currentType = this.currentPageType;
        if (currentType === MODEL_TYPES.LORA) {
            this.pages.loras.bulkMode = value;
        } else {
            this.pages[currentType].bulkMode = value;
        }
    },
    
    get selectedLoras() { return this.pages.loras.selectedLoras; },
    set selectedLoras(value) { this.pages.loras.selectedLoras = value; },
    
    get selectedModels() { 
        const currentType = this.currentPageType;
        if (currentType === MODEL_TYPES.LORA) {
            return this.pages.loras.selectedLoras;
        } else {
            return this.pages[currentType].selectedModels;
        }
    },
    set selectedModels(value) { 
        const currentType = this.currentPageType;
        if (currentType === MODEL_TYPES.LORA) {
            this.pages.loras.selectedLoras = value;
        } else {
            this.pages[currentType].selectedModels = value;
        }
    },
    
    get loraMetadataCache() { return this.pages.loras.loraMetadataCache; },
    set loraMetadataCache(value) { this.pages.loras.loraMetadataCache = value; },
    
    get settings() { return this.global.settings; },
    set settings(value) { this.global.settings = value; }
};

// Get the current page state
export function getCurrentPageState() {
    return state.pages[state.currentPageType];
}

// Set the current page type
export function setCurrentPageType(pageType) {
    if (state.pages[pageType]) {
        state.currentPageType = pageType;
        return true;
    }
    console.warn(`Unknown page type: ${pageType}`);
    return false;
}

// Initialize page state when a page loads
export function initPageState(pageType) {
    if (setCurrentPageType(pageType)) {
        console.log(`Initialized state for page: ${pageType}`);
        return getCurrentPageState();
    }
    return null;
}
