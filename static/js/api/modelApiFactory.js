import { LoraApiClient } from './loraApi.js';
import { CheckpointApiClient } from './checkpointApi.js';
import { EmbeddingApiClient } from './embeddingApi.js';
import { MODEL_TYPES, isValidModelType } from './apiConfig.js';
import { state } from '../state/index.js';

export function createModelApiClient(modelType) {
    switch (modelType) {
        case MODEL_TYPES.LORA:
            return new LoraApiClient(MODEL_TYPES.LORA);
        case MODEL_TYPES.CHECKPOINT:
            return new CheckpointApiClient(MODEL_TYPES.CHECKPOINT);
        case MODEL_TYPES.EMBEDDING:
            return new EmbeddingApiClient(MODEL_TYPES.EMBEDDING);
        default:
            throw new Error(`Unsupported model type: ${modelType}`);
    }
}

let _singletonClients = new Map();

export function getModelApiClient(modelType = null) {
    let targetType = modelType;

    if (!isValidModelType(targetType)) {
        targetType = isValidModelType(state.currentPageType)
            ? state.currentPageType
            : MODEL_TYPES.LORA;
    }
    
    if (!_singletonClients.has(targetType)) {
        _singletonClients.set(targetType, createModelApiClient(targetType));
    }
    
    return _singletonClients.get(targetType);
}

export function resetAndReload(updateFolders = false) {
    const client = getModelApiClient();
    return client.loadMoreWithVirtualScroll(true, updateFolders);
}
