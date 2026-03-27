import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: vi.fn(),
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: (_key, _params, fallback) => fallback ?? '',
}));

describe('RecipeDataManager tag input Enter behavior', () => {
  beforeEach(() => {
    vi.resetModules();
    document.body.innerHTML = `
      <input id="tagInput" type="text" />
      <div id="tagsContainer"></div>
    `;
  });

  it('adds a tag when pressing Enter in tag input', async () => {
    const { RecipeDataManager } = await import('../../../static/js/managers/import/RecipeDataManager.js');
    const importManager = {
      recipeTags: [],
      stepManager: { showStep: vi.fn() },
    };
    const manager = new RecipeDataManager(importManager);

    manager.setupTagInputEnterHandler();

    const tagInput = document.getElementById('tagInput');
    tagInput.value = 'portrait';
    tagInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

    expect(importManager.recipeTags).toEqual(['portrait']);
    expect(tagInput.value).toBe('');
    expect(document.getElementById('tagsContainer').textContent).toContain('portrait');
  });

  it('does not register duplicate Enter handlers when setup runs multiple times', async () => {
    const { RecipeDataManager } = await import('../../../static/js/managers/import/RecipeDataManager.js');
    const importManager = {
      recipeTags: [],
      stepManager: { showStep: vi.fn() },
    };
    const manager = new RecipeDataManager(importManager);

    manager.setupTagInputEnterHandler();
    manager.setupTagInputEnterHandler();

    const tagInput = document.getElementById('tagInput');
    tagInput.value = 'anime';
    tagInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

    expect(importManager.recipeTags).toEqual(['anime']);
  });

  it('ignores Enter while IME composition is active', async () => {
    const { RecipeDataManager } = await import('../../../static/js/managers/import/RecipeDataManager.js');
    const importManager = {
      recipeTags: [],
      stepManager: { showStep: vi.fn() },
    };
    const manager = new RecipeDataManager(importManager);

    manager.setupTagInputEnterHandler();

    const tagInput = document.getElementById('tagInput');
    tagInput.value = '未確定';
    const event = new KeyboardEvent('keydown', {
      key: 'Enter',
      bubbles: true,
      cancelable: true,
    });
    Object.defineProperty(event, 'isComposing', { value: true });
    tagInput.dispatchEvent(event);

    expect(importManager.recipeTags).toEqual([]);
    expect(tagInput.value).toBe('未確定');
    expect(event.defaultPrevented).toBe(false);
  });

  it('ignores keyCode 229 fallback during composition', async () => {
    const { RecipeDataManager } = await import('../../../static/js/managers/import/RecipeDataManager.js');
    const importManager = {
      recipeTags: [],
      stepManager: { showStep: vi.fn() },
    };
    const manager = new RecipeDataManager(importManager);

    manager.setupTagInputEnterHandler();

    const tagInput = document.getElementById('tagInput');
    tagInput.value = '候補';
    const event = new KeyboardEvent('keydown', {
      key: 'Enter',
      bubbles: true,
      cancelable: true,
    });
    Object.defineProperty(event, 'keyCode', { value: 229 });
    tagInput.dispatchEvent(event);

    expect(importManager.recipeTags).toEqual([]);
    expect(tagInput.value).toBe('候補');
    expect(event.defaultPrevented).toBe(false);
  });
});
