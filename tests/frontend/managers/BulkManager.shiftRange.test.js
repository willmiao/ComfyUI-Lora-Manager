import { describe, it, beforeEach, afterEach, expect } from 'vitest';
import { state } from '../../../static/js/state/index.js';
import { MODEL_TYPES } from '../../../static/js/api/apiConfig.js';
import { eventManager } from '../../../static/js/utils/EventManager.js';
import { BulkManager } from '../../../static/js/managers/BulkManager.js';

function createCard(filePath) {
  const card = document.createElement('div');
  card.className = 'model-card';
  card.dataset.filepath = filePath;
  document.body.appendChild(card);
  return card;
}

describe('BulkManager shift+click range selection', () => {
  let bulk;

  beforeEach(() => {
    eventManager.cleanup();
    state.currentPageType = MODEL_TYPES.LORA;
    state.bulkMode = true;
    state.selectedModels.clear();
    state.loraMetadataCache.clear();
    document.body.innerHTML = '';

    bulk = new BulkManager();
  });

  afterEach(() => {
    eventManager.cleanup();
    delete state.virtualScroller;
    document.body.innerHTML = '';
  });

  function attachFakeScroller(filePaths) {
    const items = filePaths.map((fp) => ({
      file_path: fp,
      file_name: fp.split('/').pop(),
      folder: '',
      usage_tips: '{}',
    }));
    state.virtualScroller = {
      items,
      findIndexByFilePath: (fp) => items.findIndex((item) => item.file_path === fp),
    };
    return items;
  }

  it('a plain click selects a single card and sets it as the shift anchor', () => {
    const cardA = createCard('/models/a.safetensors');

    bulk.toggleCardSelection(cardA);

    expect(state.selectedModels.has('/models/a.safetensors')).toBe(true);
    expect(bulk.bulkAnchorFilepath).toBe('/models/a.safetensors');
  });

  it('shift+click selects every item between anchor and target', () => {
    attachFakeScroller(['/models/a', '/models/b', '/models/c', '/models/d']);
    const cards = ['/models/a', '/models/b', '/models/c', '/models/d'].map(createCard);

    bulk.toggleCardSelection(cards[0]);
    bulk.toggleCardSelection(cards[3], true);

    expect([...state.selectedModels].sort()).toEqual(['/models/a', '/models/b', '/models/c', '/models/d']);
    cards.forEach((card) => expect(card.classList.contains('selected')).toBe(true));
    // Anchor stays on the original plain-clicked card
    expect(bulk.bulkAnchorFilepath).toBe('/models/a');
  });

  it('shift+click works when the target precedes the anchor', () => {
    attachFakeScroller(['/models/a', '/models/b', '/models/c', '/models/d']);
    const cards = ['/models/a', '/models/b', '/models/c', '/models/d'].map(createCard);

    bulk.toggleCardSelection(cards[3]);
    bulk.toggleCardSelection(cards[1], true);

    expect([...state.selectedModels].sort()).toEqual(['/models/b', '/models/c', '/models/d']);
  });

  it('consecutive shift+clicks re-derive the range from the same anchor', () => {
    attachFakeScroller(['/models/a', '/models/b', '/models/c', '/models/d', '/models/e']);
    const cards = ['/models/a', '/models/b', '/models/c', '/models/d', '/models/e'].map(createCard);

    bulk.toggleCardSelection(cards[0]);
    bulk.toggleCardSelection(cards[2], true);
    expect([...state.selectedModels].sort()).toEqual(['/models/a', '/models/b', '/models/c']);

    bulk.toggleCardSelection(cards[4], true);
    expect([...state.selectedModels].sort()).toEqual([
      '/models/a', '/models/b', '/models/c', '/models/d', '/models/e',
    ]);

    bulk.toggleCardSelection(cards[1], true);
    expect([...state.selectedModels].sort()).toEqual(['/models/a', '/models/b']);
    expect(bulk.bulkAnchorFilepath).toBe('/models/a');
  });

  it('shift+click drops selections that fall outside the new range', () => {
    attachFakeScroller(['/models/a', '/models/b', '/models/c', '/models/d', '/models/e']);
    const cards = ['/models/a', '/models/b', '/models/c', '/models/d', '/models/e'].map(createCard);

    bulk.toggleCardSelection(cards[0]);

    // Simulate an out-of-range selection (e.g. from a previous marquee)
    state.selectedModels.add('/models/e');
    cards[4].classList.add('selected');

    bulk.toggleCardSelection(cards[2], true);

    expect([...state.selectedModels].sort()).toEqual(['/models/a', '/models/b', '/models/c']);
    expect(cards[4].classList.contains('selected')).toBe(false);
    expect(bulk.bulkAnchorFilepath).toBe('/models/a');
  });

  it('shift+click without an anchor falls back to a plain toggle', () => {
    attachFakeScroller(['/models/a', '/models/b', '/models/c']);
    const cardC = createCard('/models/c');

    bulk.toggleCardSelection(cardC, true);

    expect([...state.selectedModels]).toEqual(['/models/c']);
    expect(cardC.classList.contains('selected')).toBe(true);
    // The fallback click becomes the new anchor
    expect(bulk.bulkAnchorFilepath).toBe('/models/c');
  });

  it('shift+click falls back to a plain toggle when the anchor is no longer listed', () => {
    const items = attachFakeScroller(['/models/a', '/models/b', '/models/c', '/models/d']);
    const cards = ['/models/a', '/models/b', '/models/c', '/models/d'].map(createCard);

    bulk.toggleCardSelection(cards[0]);

    // Simulate a filter change removing the anchor from the loaded items
    items.splice(0, 1);

    bulk.toggleCardSelection(cards[3], true);

    expect([...state.selectedModels].sort()).toEqual(['/models/a', '/models/d']);
    expect(bulk.bulkAnchorFilepath).toBe('/models/d');
  });

  it('range selection populates metadata cache for items without rendered cards', () => {
    attachFakeScroller(['/models/a', '/models/b', '/models/c', '/models/d']);

    // Only the endpoints exist in the DOM (b, c are virtualized away)
    const cardA = createCard('/models/a');
    const cardD = createCard('/models/d');

    bulk.toggleCardSelection(cardA);
    bulk.toggleCardSelection(cardD, true);

    expect([...state.selectedModels].sort()).toEqual(['/models/a', '/models/b', '/models/c', '/models/d']);
    const cacheB = state.loraMetadataCache.get('/models/b');
    expect(cacheB.fileName).toBe('b');
  });

  it('exiting bulk mode clears the anchor along with the selection', () => {
    const cardA = createCard('/models/a');
    bulk.toggleCardSelection(cardA);
    expect(bulk.bulkAnchorFilepath).toBe('/models/a');

    bulk.toggleBulkMode();

    expect(bulk.bulkAnchorFilepath).toBeNull();
    expect(state.selectedModels.size).toBe(0);
  });
});
