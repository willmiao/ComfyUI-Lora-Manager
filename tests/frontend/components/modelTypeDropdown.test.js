import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';
import { initModelTypeDropdown } from '../../../static/js/components/controls/ModelTypeDropdown.js';
import { i18n } from '../../../static/js/i18n/index.js';
import { readTemplate } from '../utils/domFixtures.js';

function renderDropdownDom() {
  document.body.innerHTML = `
    <div class="control-group model-type-dropdown-group dropdown-group hidden" id="modelTypeDropdown">
      <button type="button" class="model-type-trigger" aria-haspopup="listbox" aria-expanded="false">
        <span class="model-type-trigger__label"></span>
        <i class="fas fa-caret-down model-type-trigger__caret" aria-hidden="true"></i>
      </button>
      <div class="dropdown-menu model-type-dropdown-menu" role="listbox"></div>
    </div>
  `;
}

function createFilterManagerStub(modelTypes = []) {
  return {
    filters: { modelTypes: [...modelTypes] },
    updateModelTypeSelections: vi.fn(),
    updateActiveFiltersCount: vi.fn(),
    applyFilters: vi.fn(async () => {}),
  };
}

function mockModelTypesResponse(modelTypes) {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ success: true, model_types: modelTypes }),
  });
}

const OTHER_TYPES = [
  { type: 'vae', count: 12 },
  { type: 'upscaler', count: 5 },
  { type: 'text_encoder', count: 30 },
];

beforeEach(() => {
  vi.clearAllMocks();
  renderDropdownDom();
  window.filterManager = createFilterManagerStub();
  mockModelTypesResponse(OTHER_TYPES);
});

afterEach(() => {
  delete window.filterManager;
  delete window.modelTypeDropdown;
  delete global.fetch;
  document.body.classList.remove('excluded-view-active');
});

describe('ModelTypeDropdown', () => {
  it('template carries dropdown-group so the menu can become visible', () => {
    // Regression: the menu only displays via `.dropdown-group.active .dropdown-menu`,
    // so the group element in controls.html must carry the `dropdown-group` class.
    const template = readTemplate('components/controls.html');
    const groupLine = template.split('\n').find((line) => line.includes('id="modelTypeDropdown"'));
    expect(groupLine).toBeTruthy();
    expect(groupLine).toContain('model-type-dropdown-group');
    expect(groupLine).toContain('dropdown-group');
  });

  it('stays hidden when the page has a single model type', async () => {
    mockModelTypesResponse([{ type: 'embedding', count: 40 }]);

    await initModelTypeDropdown('embeddings');

    const group = document.getElementById('modelTypeDropdown');
    expect(group.classList.contains('hidden')).toBe(true);
    expect(group.dataset.modelTypeAvailable).toBeUndefined();
    expect(window.modelTypeDropdown).toBeUndefined();
  });

  it('flags itself available when it is surfaced', async () => {
    await initModelTypeDropdown('other');

    const group = document.getElementById('modelTypeDropdown');
    expect(group.dataset.modelTypeAvailable).toBe('1');
    expect(group.classList.contains('hidden')).toBe(false);
  });

  it('does not surface itself while the excluded view is active', async () => {
    document.body.classList.add('excluded-view-active');

    await initModelTypeDropdown('other');

    const group = document.getElementById('modelTypeDropdown');
    expect(group.dataset.modelTypeAvailable).toBe('1');
    expect(group.classList.contains('hidden')).toBe(true);
  });

  it('stays hidden when no element with the dropdown id exists', async () => {
    document.body.innerHTML = '';

    await initModelTypeDropdown('other');

    expect(window.modelTypeDropdown).toBeUndefined();
  });

  it('renders All Types plus one item per type with counts', async () => {
    await initModelTypeDropdown('other');

    const group = document.getElementById('modelTypeDropdown');
    expect(group.classList.contains('hidden')).toBe(false);

    const options = group.querySelectorAll('.model-type-option');
    expect(options).toHaveLength(4);
    expect(options[0].dataset.value).toBe('');
    expect(options[0].textContent).toBe('All Types');
    expect(options[1].textContent).toBe('VAE (12)');
    expect(options[2].textContent).toBe('Upscaler (5)');
    expect(options[3].textContent).toBe('Text Encoder (30)');
  });

  it('abbreviates large counts and keeps the exact value in the option tooltip', async () => {
    const originalLocale = i18n.currentLocale;
    i18n.currentLocale = 'en';
    try {
      mockModelTypesResponse([
        { type: 'lora', count: 19876 },
        { type: 'vae', count: 12 },
      ]);

      await initModelTypeDropdown('loras');

      const options = document.querySelectorAll('.model-type-option');
      expect(options[1].textContent).toBe('LoRA (19.9K)');
      expect(options[1].title).toBe('LoRA — 19,876 models');
      // Every option carries its own tooltip, so hovering never depends on the
      // magnitude and never falls back to the group's "Filter by model type".
      expect(options[2].textContent).toBe('VAE (12)');
      expect(options[2].title).toBe('VAE — 12 models');
      // "All Types" is not a counted entry and keeps no tooltip of its own.
      expect(options[0].title).toBe('');
    } finally {
      i18n.currentLocale = originalLocale;
    }
  });

  it('ignores types without a known display name', async () => {
    mockModelTypesResponse([
      { type: 'vae', count: 12 },
      { type: 'mystery_type', count: 3 },
      { type: 'upscaler', count: 5 },
    ]);

    await initModelTypeDropdown('other');

    const options = document.querySelectorAll('.model-type-option');
    expect(options).toHaveLength(3);
    expect([...options].map((o) => o.dataset.value)).toEqual(['', 'vae', 'upscaler']);
  });

  it('initializes the trigger label from the restored filters', async () => {
    window.filterManager = createFilterManagerStub(['text_encoder']);

    await initModelTypeDropdown('other');

    const label = document.querySelector('.model-type-trigger__label');
    expect(label.textContent).toBe('Text Encoder');
  });

  it('shows a count label when multiple types are selected in the filter panel', async () => {
    window.filterManager = createFilterManagerStub(['vae', 'upscaler']);

    await initModelTypeDropdown('other');

    const label = document.querySelector('.model-type-trigger__label');
    expect(label.textContent).toBe('2 types');
  });

  it('selecting a type sets a single-entry modelTypes filter and applies it', async () => {
    await initModelTypeDropdown('other');

    const item = document.querySelector('.model-type-option[data-value="vae"]');
    item.click();
    await vi.waitFor(() => {
      expect(window.filterManager.applyFilters).toHaveBeenCalledWith(false);
    });

    expect(window.filterManager.filters.modelTypes).toEqual(['vae']);
    expect(window.filterManager.updateModelTypeSelections).toHaveBeenCalled();
    expect(window.filterManager.updateActiveFiltersCount).toHaveBeenCalled();
    expect(document.querySelector('.model-type-trigger__label').textContent).toBe('VAE');
  });

  it('selecting All Types clears the modelTypes filter', async () => {
    window.filterManager = createFilterManagerStub(['vae']);
    await initModelTypeDropdown('other');

    document.querySelector('.model-type-option[data-value=""]').click();
    await vi.waitFor(() => {
      expect(window.filterManager.applyFilters).toHaveBeenCalled();
    });

    expect(window.filterManager.filters.modelTypes).toEqual([]);
    expect(document.querySelector('.model-type-trigger__label').textContent).toBe('All Types');
  });

  it('syncFromFilters reflects external filter changes (filter panel multi-select)', async () => {
    await initModelTypeDropdown('other');

    window.filterManager.filters.modelTypes = ['vae', 'upscaler'];
    window.modelTypeDropdown.syncFromFilters();

    expect(document.querySelector('.model-type-trigger__label').textContent).toBe('2 types');

    window.filterManager.filters.modelTypes = ['upscaler'];
    window.modelTypeDropdown.syncFromFilters();

    expect(document.querySelector('.model-type-trigger__label').textContent).toBe('Upscaler');
    const selected = document.querySelector('.model-type-option.is-selected');
    expect(selected.dataset.value).toBe('upscaler');
  });

  it('toggles the menu on trigger click and closes on outside click', async () => {
    await initModelTypeDropdown('other');

    const group = document.getElementById('modelTypeDropdown');
    const trigger = group.querySelector('.model-type-trigger');

    trigger.click();
    expect(group.classList.contains('active')).toBe(true);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');

    document.body.click();
    expect(group.classList.contains('active')).toBe(false);
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
  });

  it('selects the focused option with Enter and closes the menu', async () => {
    await initModelTypeDropdown('other');

    const group = document.getElementById('modelTypeDropdown');
    const trigger = group.querySelector('.model-type-trigger');
    const menu = group.querySelector('.model-type-dropdown-menu');

    trigger.click();
    const item = menu.querySelector('.model-type-option[data-value="upscaler"]');
    item.focus();
    menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    await vi.waitFor(() => {
      expect(window.filterManager.applyFilters).toHaveBeenCalled();
    });

    expect(window.filterManager.filters.modelTypes).toEqual(['upscaler']);
    expect(group.classList.contains('active')).toBe(false);
  });

  it('Escape closes the menu without changing the filter', async () => {
    await initModelTypeDropdown('other');

    const group = document.getElementById('modelTypeDropdown');
    const menu = group.querySelector('.model-type-dropdown-menu');

    group.querySelector('.model-type-trigger').click();
    menu.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));

    expect(group.classList.contains('active')).toBe(false);
    expect(window.filterManager.filters.modelTypes).toEqual([]);
    expect(window.filterManager.applyFilters).not.toHaveBeenCalled();
  });
});
