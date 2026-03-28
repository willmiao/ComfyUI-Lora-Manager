// Core application functionality
import { state } from './state/index.js';
import { LoadingManager } from './managers/LoadingManager.js';
import { modalManager } from './managers/ModalManager.js';
import { updateService } from './managers/UpdateService.js';
import { HeaderManager } from './components/Header.js';
import { settingsManager } from './managers/SettingsManager.js';
import { moveManager } from './managers/MoveManager.js';
import { bulkManager } from './managers/BulkManager.js';
import { ExampleImagesManager } from './managers/ExampleImagesManager.js';
import { helpManager } from './managers/HelpManager.js';
import { bannerService } from './managers/BannerService.js';
import { initTheme, initBackToTop } from './utils/uiHelpers.js';
import { initializeInfiniteScroll } from './utils/infiniteScroll.js';
import { i18n } from './i18n/index.js';
import { onboardingManager } from './managers/OnboardingManager.js';
import { BulkContextMenu } from './components/ContextMenu/BulkContextMenu.js';
import { createPageContextMenu, createGlobalContextMenu } from './components/ContextMenu/index.js';
import { initializeEventManagement } from './utils/eventManagementInit.js';
import { civitaiBaseModelApi } from './api/civitaiBaseModelApi.js';
import { setDynamicBaseModels } from './utils/constants.js';

// Core application class
export class AppCore {
    constructor() {
        this.initialized = false;
    }
    
    // Initialize core functionality
    async initialize() {
        if (this.initialized) return;

        console.log('AppCore: Initializing...');
        
        // Initialize i18n first
        window.i18n = i18n;
        // Wait for i18n to be ready
        await window.i18n.waitForReady();
        
        console.log(`AppCore: Language set: ${i18n.getCurrentLocale()}`);
        
        // Initialize settings manager and wait for it to sync from backend
        console.log('AppCore: Initializing settings...');
        await settingsManager.waitForInitialization();
        console.log('AppCore: Settings initialized');
        
        // Initialize dynamic base models (async, non-blocking)
        console.log('AppCore: Initializing dynamic base models...');
        this.initializeDynamicBaseModels();
        
        // Initialize managers
        state.loadingManager = new LoadingManager();
        modalManager.initialize();
        updateService.initialize();
        await bannerService.initialize();
        window.modalManager = modalManager;
        window.settingsManager = settingsManager;
        const exampleImagesManager = new ExampleImagesManager();
        window.exampleImagesManager = exampleImagesManager;
        window.helpManager = helpManager;
        window.moveManager = moveManager;
        window.bulkManager = bulkManager;
        
        // Initialize UI components
        window.headerManager = new HeaderManager();
        initTheme();
        initBackToTop();
        
        // Initialize the bulk manager and context menu
        bulkManager.initialize();

        // Initialize bulk context menu
        const bulkContextMenu = new BulkContextMenu();
        bulkManager.setBulkContextMenu(bulkContextMenu);
        
        // Initialize the example images manager
        exampleImagesManager.initialize();
        // Initialize the help manager
        helpManager.initialize();

        const cardInfoDisplay = state.global.settings.card_info_display || 'always';
        document.body.classList.toggle('hover-reveal', cardInfoDisplay === 'hover');

        initializeEventManagement();
        
        // Mark as initialized
        this.initialized = true;
        
        // Start onboarding if needed (after everything is initialized)
        setTimeout(async () => {
            await onboardingManager.start();
        }, 1000); // Small delay to ensure all elements are rendered
        
        // Return the core instance for chaining
        return this;
    }
    
    // Get the current page type
    getPageType() {
        const body = document.body;
        return body.dataset.page || 'unknown';
    }
    
    // Initialize common UI features based on page type
    initializePageFeatures() {
        const pageType = this.getPageType();
        
        if (['loras', 'recipes', 'checkpoints', 'embeddings'].includes(pageType)) {
            this.initializeContextMenus(pageType);
            initializeInfiniteScroll(pageType);
        }
        
        return this;
    }
    
    // Initialize context menus for the current page
    initializeContextMenus(pageType) {
        // Create page-specific context menu
        window.pageContextMenu = createPageContextMenu(pageType);

        if (!window.globalContextMenuInstance) {
            window.globalContextMenuInstance = createGlobalContextMenu();
        }
    }
    
    // Initialize dynamic base models from Civitai API
    // This is non-blocking - runs in background
    async initializeDynamicBaseModels() {
        try {
            const result = await civitaiBaseModelApi.getBaseModels();
            if (result && result.models) {
                setDynamicBaseModels(result.models, result.last_updated);
                console.log(`AppCore: Loaded ${result.merged_count} base models (${result.hardcoded_count} hardcoded + ${result.remote_count} remote)`);
            }
        } catch (error) {
            console.warn('AppCore: Failed to load dynamic base models:', error);
            // Non-critical error - app continues with hardcoded models
        }
    }
}

// Create and export a singleton instance
export const appCore = new AppCore();
