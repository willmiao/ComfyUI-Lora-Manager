import { state } from '../state/index.js';

/**
 * API Configuration
 * Centralized configuration for all model types and their endpoints
 */

// Model type definitions
export const MODEL_TYPES = {
    LORA: 'loras',
    CHECKPOINT: 'checkpoints',
    EMBEDDING: 'embeddings' // Future model type
};

// Base API configuration for each model type
export const MODEL_CONFIG = {
    [MODEL_TYPES.LORA]: {
        displayName: 'LoRA',
        singularName: 'lora',
        defaultPageSize: 100,
        supportsLetterFilter: true,
        supportsBulkOperations: true,
        supportsMove: true,
        templateName: 'loras.html'
    },
    [MODEL_TYPES.CHECKPOINT]: {
        displayName: 'Checkpoint',
        singularName: 'checkpoint',
        defaultPageSize: 100,
        supportsLetterFilter: false,
        supportsBulkOperations: true,
        supportsMove: true,
        templateName: 'checkpoints.html'
    },
    [MODEL_TYPES.EMBEDDING]: {
        displayName: 'Embedding',
        singularName: 'embedding',
        defaultPageSize: 100,
        supportsLetterFilter: true,
        supportsBulkOperations: true,
        supportsMove: true,
        templateName: 'embeddings.html'
    }
};

/**
 * Generate API endpoints for a given model type
 * @param {string} modelType - The model type (e.g., 'loras', 'checkpoints')
 * @returns {Object} Object containing all API endpoints for the model type
 */
export function getApiEndpoints(modelType) {
    if (!Object.values(MODEL_TYPES).includes(modelType)) {
        throw new Error(`Invalid model type: ${modelType}`);
    }
    
    return {
        // Base CRUD operations
        list: `/api/lm/${modelType}/list`,
        delete: `/api/lm/${modelType}/delete`,
        exclude: `/api/lm/${modelType}/exclude`,
        rename: `/api/lm/${modelType}/rename`,
        save: `/api/lm/${modelType}/save-metadata`,
        
        // Bulk operations
        bulkDelete: `/api/lm/${modelType}/bulk-delete`,
        
        // Tag operations
        addTags: `/api/lm/${modelType}/add-tags`,

        // Move operations (now common for all model types that support move)
        moveModel: `/api/lm/${modelType}/move_model`,
        moveBulk: `/api/lm/${modelType}/move_models_bulk`,
        
        // CivitAI integration
        fetchCivitai: `/api/lm/${modelType}/fetch-civitai`,
        fetchAllCivitai: `/api/lm/${modelType}/fetch-all-civitai`,
        relinkCivitai: `/api/lm/${modelType}/relink-civitai`,
        civitaiVersions: `/api/lm/${modelType}/civitai/versions`,
        refreshUpdates: `/api/lm/${modelType}/updates/refresh`,
        modelUpdateStatus: `/api/lm/${modelType}/updates/status`,
        modelUpdateVersions: `/api/lm/${modelType}/updates/versions`,
        ignoreModelUpdate: `/api/lm/${modelType}/updates/ignore`,
        ignoreVersionUpdate: `/api/lm/${modelType}/updates/ignore-version`,
        
        // Preview management
        replacePreview: `/api/lm/${modelType}/replace-preview`,
        
        // Query operations
        scan: `/api/lm/${modelType}/scan`,
        topTags: `/api/lm/${modelType}/top-tags`,
        baseModels: `/api/lm/${modelType}/base-models`,
        roots: `/api/lm/${modelType}/roots`,
        folders: `/api/lm/${modelType}/folders`,
        folderTree: `/api/lm/${modelType}/folder-tree`,
        unifiedFolderTree: `/api/lm/${modelType}/unified-folder-tree`,
        duplicates: `/api/lm/${modelType}/find-duplicates`,
        conflicts: `/api/lm/${modelType}/find-filename-conflicts`,
        verify: `/api/lm/${modelType}/verify-duplicates`,
        metadata: `/api/lm/${modelType}/metadata`,
        modelDescription: `/api/lm/${modelType}/model-description`,
        
        // Auto-organize operations
        autoOrganize: `/api/lm/${modelType}/auto-organize`,
        autoOrganizeProgress: `/api/lm/${modelType}/auto-organize-progress`,
        
        // Model-specific endpoints (will be merged with specific configs)
        specific: {}
    };
}

/**
 * Model-specific endpoint configurations
 */
export const MODEL_SPECIFIC_ENDPOINTS = {
    [MODEL_TYPES.LORA]: {
        letterCounts: `/api/lm/${MODEL_TYPES.LORA}/letter-counts`,
        notes: `/api/lm/${MODEL_TYPES.LORA}/get-notes`,
        triggerWords: `/api/lm/${MODEL_TYPES.LORA}/get-trigger-words`,
        previewUrl: `/api/lm/${MODEL_TYPES.LORA}/preview-url`,
        civitaiUrl: `/api/lm/${MODEL_TYPES.LORA}/civitai-url`,
        metadata: `/api/lm/${MODEL_TYPES.LORA}/metadata`,
        getTriggerWordsPost: `/api/lm/${MODEL_TYPES.LORA}/get_trigger_words`,
        civitaiModelByVersion: `/api/lm/${MODEL_TYPES.LORA}/civitai/model/version`,
        civitaiModelByHash: `/api/lm/${MODEL_TYPES.LORA}/civitai/model/hash`,
    },
    [MODEL_TYPES.CHECKPOINT]: {
        info: `/api/lm/${MODEL_TYPES.CHECKPOINT}/info`,
        checkpoints_roots: `/api/lm/${MODEL_TYPES.CHECKPOINT}/checkpoints_roots`,
        unet_roots: `/api/lm/${MODEL_TYPES.CHECKPOINT}/unet_roots`,
        metadata: `/api/lm/${MODEL_TYPES.CHECKPOINT}/metadata`,
    },
    [MODEL_TYPES.EMBEDDING]: {
        metadata: `/api/lm/${MODEL_TYPES.EMBEDDING}/metadata`,
    }
};

/**
 * Get complete API configuration for a model type
 * @param {string} modelType - The model type
 * @returns {Object} Complete API configuration
 */
export function getCompleteApiConfig(modelType) {
    const baseEndpoints = getApiEndpoints(modelType);
    const specificEndpoints = MODEL_SPECIFIC_ENDPOINTS[modelType] || {};
    const config = MODEL_CONFIG[modelType];
    
    return {
        modelType,
        config,
        endpoints: {
            ...baseEndpoints,
            specific: specificEndpoints
        }
    };
}

/**
 * Validate if a model type is supported
 * @param {string} modelType - The model type to validate
 * @returns {boolean} True if valid, false otherwise
 */
export function isValidModelType(modelType) {
    return Object.values(MODEL_TYPES).includes(modelType);
}

/**
 * Get model type from current page or explicit parameter
 * @param {string} [explicitType] - Explicitly provided model type
 * @returns {string} The model type
 */
export function getCurrentModelType(explicitType = null) {
    if (explicitType && isValidModelType(explicitType)) {
        return explicitType;
    }

    return state.currentPageType || MODEL_TYPES.LORA;
}

// Download API endpoints (shared across all model types)
export const DOWNLOAD_ENDPOINTS = {
    download: '/api/lm/download-model',
    downloadGet: '/api/lm/download-model-get',
    cancelGet: '/api/lm/cancel-download-get',
    progress: '/api/lm/download-progress',
    exampleImages: '/api/lm/force-download-example-images' // New endpoint for downloading example images
};

// WebSocket endpoints
export const WS_ENDPOINTS = {
    fetchProgress: '/ws/fetch-progress'
};
