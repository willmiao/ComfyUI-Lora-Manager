import { describe, it, expect, beforeEach } from 'vitest';
import { createDefaultSettings, getCurrentPageState, initPageState, setCurrentPageType, state } from '../../../static/js/state/index.js';
import { MODEL_TYPES } from '../../../static/js/api/apiConfig.js';
import { DEFAULT_PATH_TEMPLATES } from '../../../static/js/utils/constants.js';

describe('state module', () => {
  beforeEach(() => {
    // Reset to default page before each assertion
    state.currentPageType = MODEL_TYPES.LORA;
  });

  it('creates default settings with immutable template copies', () => {
    const defaultSettings = createDefaultSettings();

    expect(defaultSettings).toMatchObject({
      civitai_api_key: '',
      language: 'en',
      blur_mature_content: true
    });

    expect(defaultSettings.download_path_templates).toEqual(DEFAULT_PATH_TEMPLATES);

    // ensure nested objects are new references so tests can safely mutate
    expect(defaultSettings.download_path_templates).not.toBe(DEFAULT_PATH_TEMPLATES);
    expect(defaultSettings.base_model_path_mappings).toEqual({});
    expect(Object.isFrozen(defaultSettings)).toBe(false);
  });

  it('switches current page type when valid', () => {
    const didSwitch = setCurrentPageType(MODEL_TYPES.CHECKPOINT);

    expect(didSwitch).toBe(true);
    expect(state.currentPageType).toBe(MODEL_TYPES.CHECKPOINT);
    expect(getCurrentPageState()).toBe(state.pages[MODEL_TYPES.CHECKPOINT]);
  });

  it('rejects switching to an unknown page type', () => {
    state.currentPageType = MODEL_TYPES.LORA;

    const didSwitch = setCurrentPageType('invalid-page');

    expect(didSwitch).toBe(false);
    expect(state.currentPageType).toBe(MODEL_TYPES.LORA);
  });

  it('initializes and returns state for a known page', () => {
    const pageState = initPageState(MODEL_TYPES.EMBEDDING);

    expect(pageState).toBeDefined();
    expect(pageState).toBe(state.pages[MODEL_TYPES.EMBEDDING]);
    expect(state.currentPageType).toBe(MODEL_TYPES.EMBEDDING);
  });
});
