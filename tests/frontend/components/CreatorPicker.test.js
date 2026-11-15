import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: vi.fn((key, params = {}, fallback) => {
    let text = typeof fallback === 'string' ? fallback : key;
    for (const [name, value] of Object.entries(params)) {
      text = text.split(`{${name}}`).join(String(value));
    }
    return text;
  }),
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: vi.fn(),
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  getModelApiClient: vi.fn(),
}));

import {
  CREATOR_SEARCH_DEBOUNCE_MS,
  CreatorPicker,
  normalizeCreatorName,
  renderCreatorChip,
} from '../../../static/js/components/shared/CreatorPicker.js';
import { showToast } from '../../../static/js/utils/uiHelpers.js';

Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || vi.fn();

const tick = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));

function mountChip(creator = null) {
  const wrapper = document.createElement('div');
  wrapper.className = 'creator-chip-wrap';
  wrapper.innerHTML = renderCreatorChip(creator);
  document.body.appendChild(wrapper);
  return wrapper;
}

function mountPicker({
  creator = null,
  fetchCreators = vi.fn(async () => ({ creators: [], total: 0 })),
  saveCreator = vi.fn(async () => {}),
} = {}) {
  const wrapper = mountChip(creator);
  const picker = new CreatorPicker({
    filePath: 'models/test.safetensors',
    modelType: 'loras',
    creator,
    wrapper,
    fetchCreators,
    saveCreator,
  });
  return { wrapper, picker, fetchCreators, saveCreator };
}

function getTrigger(wrapper, action) {
  return wrapper.querySelector(`[data-action="${action}"]`);
}

describe('renderCreatorChip', () => {
  it('renders the dashed add chip when no creator exists', () => {
    const markup = renderCreatorChip(null);
    expect(markup).toContain('data-action="add-creator"');
    expect(markup).toContain('Add creator');
    expect(markup).toContain('creator-info--add');
  });

  it('renders the familiar chip with a pencil for a synced creator', () => {
    const markup = renderCreatorChip({ username: 'Lykon', image: null });
    expect(markup).toContain('data-action="view-creator"');
    expect(markup).toContain('data-username="Lykon"');
    expect(markup).toContain('data-action="edit-creator"');
    expect(markup).toContain('creator-username');
    expect(markup).not.toContain('creator-badge');
  });

  it('marks a manual creator and escapes unsafe names', () => {
    const markup = renderCreatorChip({
      username: '<img src=x onerror=alert(1)>',
      source: 'manual',
    });
    expect(markup).toContain('Manual');
    expect(markup).toContain('&lt;img src=x onerror=alert(1)&gt;');
    expect(markup).not.toContain('<img src=x onerror=alert(1)>');
    expect(markup).toContain('data-source="manual"');
  });
});

describe('normalizeCreatorName', () => {
  it('trims, strips a leading @, and collapses whitespace', () => {
    expect(normalizeCreatorName('  @Lykon  ')).toBe('Lykon');
    expect(normalizeCreatorName('miao\n  ai')).toBe('miao ai');
    expect(normalizeCreatorName(null)).toBe('');
  });
});

describe('CreatorPicker', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    showToast.mockClear();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  it('opens an anchored popover with the library creators and focuses the input', async () => {
    const { wrapper, picker, fetchCreators } = mountPicker({
      fetchCreators: vi.fn(async () => ({
        creators: [
          { username: 'Lykon', model_count: 24 },
          { username: 'TheAlly', model_count: 15 },
        ],
        total: 2,
      })),
    });

    picker.open(getTrigger(wrapper, 'add-creator'));
    await tick(10);

    const popover = wrapper.querySelector('.creator-popover');
    expect(popover).not.toBeNull();
    expect(wrapper.contains(popover)).toBe(true);
    expect(document.activeElement).toBe(popover.querySelector('.creator-input'));
    expect(fetchCreators).toHaveBeenCalledWith('');
    expect(popover.querySelector('.creator-option-name').textContent).toBe('Lykon');

    picker.destroy();
  });

  it('creates a new creator from the create row and re-renders the chip', async () => {
    const { wrapper, picker, saveCreator } = mountPicker();

    picker.open(getTrigger(wrapper, 'add-creator'));
    await tick(10);

    const input = wrapper.querySelector('.creator-input');
    input.value = 'ly';
    input.dispatchEvent(new Event('input', { bubbles: true }));

    const createRow = wrapper.querySelector('.creator-create-row');
    expect(createRow).not.toBeNull();
    expect(createRow.textContent).toContain('ly');

    createRow.click();
    await tick(10);

    expect(saveCreator).toHaveBeenCalledWith({
      username: 'ly',
      image: null,
      source: 'manual',
    });
    expect(wrapper.querySelector('.creator-username')?.textContent).toBe('ly');
    expect(wrapper.querySelector('.creator-badge')?.textContent).toBe('Manual');
    expect(wrapper.querySelector('.creator-popover')).toBeNull();
    expect(showToast).toHaveBeenCalled();
  });

  it('reuses the canonical spelling for a case-insensitive exact match', async () => {
    const fetchCreators = vi.fn(async () => ({
      creators: [{ username: 'Lykon', model_count: 24 }],
      total: 1,
    }));
    const { wrapper, picker, saveCreator } = mountPicker({ fetchCreators });

    picker.open(getTrigger(wrapper, 'add-creator'));
    await tick(10);

    const input = wrapper.querySelector('.creator-input');
    input.value = 'LYKON';
    input.dispatchEvent(new Event('input', { bubbles: true }));

    expect(wrapper.querySelector('.creator-create-row')).toBeNull();
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    await tick(10);

    expect(saveCreator).toHaveBeenCalledWith({
      username: 'Lykon',
      image: null,
      source: 'manual',
    });
    expect(wrapper.querySelector('.creator-username')?.textContent).toBe('Lykon');
  });

  it('removes a manual creator and returns to the add chip', async () => {
    const creator = { username: 'local_artist', image: null, source: 'manual' };
    const { wrapper, picker, saveCreator } = mountPicker({ creator });

    picker.open(getTrigger(wrapper, 'edit-creator'));
    await tick(10);

    wrapper.querySelector('.creator-remove-btn').click();
    await tick(10);

    expect(saveCreator).toHaveBeenCalledWith(null);
    expect(wrapper.querySelector('[data-action="add-creator"]')).not.toBeNull();
    expect(wrapper.querySelector('.creator-username')).toBeNull();
  });

  it('closes on Escape without writing', async () => {
    const { wrapper, picker, saveCreator } = mountPicker({
      creator: { username: 'Lykon', image: null },
    });

    picker.open(getTrigger(wrapper, 'edit-creator'));
    await tick(10);

    wrapper.querySelector('.creator-input').dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
    );

    expect(wrapper.querySelector('.creator-popover')).toBeNull();
    expect(saveCreator).not.toHaveBeenCalled();
  });

  it('commits typed text when clicking outside', async () => {
    const { wrapper, picker, saveCreator } = mountPicker();

    picker.open(getTrigger(wrapper, 'add-creator'));
    await tick(10);

    const input = wrapper.querySelector('.creator-input');
    input.value = 'outside_new';
    input.dispatchEvent(new Event('input', { bubbles: true }));

    document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    await tick(10);

    expect(saveCreator).toHaveBeenCalledWith({
      username: 'outside_new',
      image: null,
      source: 'manual',
    });
  });

  it('debounces typed queries before fetching', async () => {
    const fetchCreators = vi.fn(async () => ({ creators: [], total: 0 }));
    const { wrapper, picker } = mountPicker({ fetchCreators });

    picker.open(getTrigger(wrapper, 'add-creator'));
    await tick(10);
    fetchCreators.mockClear();

    const input = wrapper.querySelector('.creator-input');
    input.value = 'ly';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await tick(50);
    expect(fetchCreators).not.toHaveBeenCalled();

    await tick(CREATOR_SEARCH_DEBOUNCE_MS);
    expect(fetchCreators).toHaveBeenCalledWith('ly');
  });

  it('shows a load error but still allows creating a typed name', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const fetchCreators = vi.fn(async () => {
      throw new Error('offline');
    });
    const { wrapper, picker } = mountPicker({ fetchCreators });

    picker.open(getTrigger(wrapper, 'add-creator'));
    await tick(10);

    expect(wrapper.querySelector('.creator-empty-state')?.textContent)
      .toContain("Couldn't load creators");

    const input = wrapper.querySelector('.creator-input');
    input.value = 'new_name';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    expect(wrapper.querySelector('.creator-create-row')).not.toBeNull();
  });
});
