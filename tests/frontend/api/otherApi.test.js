import { describe, it, expect } from 'vitest';
// Import order matters: api modules are circularly dependent
// (modelApiFactory -> loraApi -> baseModelApi -> modelApiFactory/state).
// Loading the factory first lets baseModelApi fully evaluate before the
// client subclasses extend it.
import { createModelApiClient, getModelApiClient } from '../../../static/js/api/modelApiFactory.js';
import {
  MODEL_TYPES,
  MODEL_CONFIG,
  getApiEndpoints,
  getCompleteApiConfig,
  isValidModelType,
} from '../../../static/js/api/apiConfig.js';
import { OtherApiClient } from '../../../static/js/api/otherApi.js';

describe('apiConfig - other model type', () => {
  it('exposes OTHER model type', () => {
    expect(MODEL_TYPES.OTHER).toBe('other');
    expect(isValidModelType('other')).toBe(true);
  });

  it('has a complete MODEL_CONFIG entry', () => {
    const config = MODEL_CONFIG[MODEL_TYPES.OTHER];

    expect(config).toBeDefined();
    expect(config.singularName).toBe('other');
    expect(config.supportsLetterFilter).toBe(false);
    expect(config.supportsBulkOperations).toBe(true);
    expect(config.supportsMove).toBe(true);
    expect(config.templateName).toBe('other.html');
  });

  it('generates /api/lm/other/* endpoints', () => {
    const endpoints = getApiEndpoints('other');

    expect(endpoints.list).toBe('/api/lm/other/list');
    expect(endpoints.delete).toBe('/api/lm/other/delete');
    expect(endpoints.exclude).toBe('/api/lm/other/exclude');
    expect(endpoints.unexclude).toBe('/api/lm/other/unexclude');
    expect(endpoints.rename).toBe('/api/lm/other/rename');
    expect(endpoints.save).toBe('/api/lm/other/save-metadata');
    expect(endpoints.bulkDelete).toBe('/api/lm/other/bulk-delete');
    expect(endpoints.moveModel).toBe('/api/lm/other/move_model');
    expect(endpoints.moveBulk).toBe('/api/lm/other/move_models_bulk');
    expect(endpoints.fetchCivitai).toBe('/api/lm/other/fetch-civitai');
    expect(endpoints.fetchAllCivitai).toBe('/api/lm/other/fetch-all-civitai');
    expect(endpoints.scan).toBe('/api/lm/other/scan');
    expect(endpoints.topTags).toBe('/api/lm/other/top-tags');
    expect(endpoints.baseModels).toBe('/api/lm/other/base-models');
    expect(endpoints.roots).toBe('/api/lm/other/roots');
    expect(endpoints.folders).toBe('/api/lm/other/folders');
    expect(endpoints.duplicates).toBe('/api/lm/other/find-duplicates');
    expect(endpoints.replacePreview).toBe('/api/lm/other/replace-preview');
  });

  it('merges other-specific endpoints into the complete config', () => {
    const config = getCompleteApiConfig('other');

    expect(config.modelType).toBe('other');
    expect(config.config).toBe(MODEL_CONFIG.other);
    expect(config.endpoints.specific.metadata).toBe('/api/lm/other/metadata');
  });
});

describe('modelApiFactory - other model type', () => {
  it('creates an OtherApiClient for the other model type', () => {
    const client = createModelApiClient(MODEL_TYPES.OTHER);

    expect(client).toBeInstanceOf(OtherApiClient);
    expect(client.modelType).toBe('other');
    expect(client.apiConfig.endpoints.list).toBe('/api/lm/other/list');
  });

  it('returns a cached singleton from getModelApiClient', () => {
    const first = getModelApiClient(MODEL_TYPES.OTHER);
    const second = getModelApiClient(MODEL_TYPES.OTHER);

    expect(first).toBeInstanceOf(OtherApiClient);
    expect(second).toBe(first);
  });

  it('still rejects unsupported model types', () => {
    expect(() => createModelApiClient('bogus')).toThrow('Unsupported model type: bogus');
  });
});
