import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  APP_MODULE,
  UTILS_MODULE,
  LORA_UTILS_MODULE,
  CANVAS_API_MODULE,
  STYLES_MODULE,
  QUICK_PANEL_MODULE,
} = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  UTILS_MODULE: new URL('../../../web/comfyui/utils.js', import.meta.url).pathname,
  LORA_UTILS_MODULE: new URL('../../../web/comfyui/loras_widget_utils.js', import.meta.url).pathname,
  CANVAS_API_MODULE: new URL('../../../web/comfyui/lora_canvas_api.js', import.meta.url).pathname,
  STYLES_MODULE: new URL('../../../web/comfyui/lm_styles_loader.js', import.meta.url).pathname,
  QUICK_PANEL_MODULE: new URL('../../../web/comfyui/lora_quick_panel.js', import.meta.url).pathname,
}));

const { appMock, apiMocks } = vi.hoisted(() => ({
  appMock: {
    registerExtension: vi.fn(),
    graph: { setDirtyCanvas: vi.fn() },
    canvas: { selected_nodes: {} },
  },
  apiMocks: {
    searchLoraLibrary: vi.fn(),
    fetchLoraDetails: vi.fn(),
    fetchLoraFolderIndex: vi.fn(),
    openLoraManager: vi.fn(),
    recommendedStrength: vi.fn((details) => details?.usage_tips?.strength),
  },
}));

let graphNodes = [];

vi.mock(APP_MODULE, () => ({ app: appMock }));
vi.mock(UTILS_MODULE, () => ({
  LORA_PATTERN: /<lora:([^:>]+):([^:>]+)(?::([^:>]+))?>/,
  getAllGraphNodes: () => graphNodes.map((node) => ({ graph: appMock.graph, node })),
  getWidgetByName: (node, name) => name === 'loras' ? node.lorasWidget : null,
}));
vi.mock(LORA_UTILS_MODULE, () => ({
  normalizeLoraNameKey: (name) => String(name || '').replace(/\\/g, '/').replace(/\.(safetensors|ckpt|pt|bin)$/i, ''),
}));
vi.mock(CANVAS_API_MODULE, () => apiMocks);
vi.mock(STYLES_MODULE, () => ({ ensureLmStyles: vi.fn() }));

function makeNode() {
  return {
    id: 7,
    title: 'Character Loader',
    lorasWidget: {
      value: [],
      callback: vi.fn(),
    },
    setDirtyCanvas: vi.fn(),
  };
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

describe('LoRA Quick Panel', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    graphNodes = [];
    vi.clearAllMocks();
    apiMocks.searchLoraLibrary.mockResolvedValue([
      { relativePath: 'characters/astral.safetensors', modelName: 'Astral Portrait' },
    ]);
    apiMocks.fetchLoraFolderIndex.mockResolvedValue({
      count: 1,
      folders: {},
      items: [{ relativePath: 'characters/astral.safetensors', modelName: 'Astral Portrait' }],
    });
    apiMocks.fetchLoraDetails.mockResolvedValue({
      model_name: 'Astral Portrait',
      base_model: 'Flux',
      file_path: '/models/characters/astral.safetensors',
      usage_tips: { strength: 0.7 },
      civitai: { trainedWords: ['astral'] },
    });
  });

  it('adds a normalized LoRA with its recommended strength', async () => {
    const { applyQuickLoraSelection } = await import(QUICK_PANEL_MODULE);
    const node = makeNode();
    const result = applyQuickLoraSelection(node, { name: 'characters/astral.safetensors', strength: 0.7 });

    expect(result.changed).toBe(true);
    expect(node.lorasWidget.value).toEqual([
      expect.objectContaining({ name: 'characters/astral', strength: '0.70', active: true }),
    ]);
    expect(node.lorasWidget.callback).toHaveBeenCalledOnce();
  });

  it('enables an existing LoRA instead of duplicating it', async () => {
    const { applyQuickLoraSelection } = await import(QUICK_PANEL_MODULE);
    const node = makeNode();
    node.lorasWidget.value = [{ name: 'characters/astral', strength: '0.40', active: false }];

    const result = applyQuickLoraSelection(node, { name: 'characters/astral', strength: 0.7 });

    expect(result.changed).toBe(true);
    expect(node.lorasWidget.value).toHaveLength(1);
    expect(node.lorasWidget.value[0]).toMatchObject({ strength: '0.40', active: true });
  });

  it('replaces only the requested row', async () => {
    const { applyQuickLoraSelection } = await import(QUICK_PANEL_MODULE);
    const node = makeNode();
    node.lorasWidget.value = [
      { name: 'old', strength: '0.30', active: true },
      { name: 'keep', strength: '0.90', active: true },
    ];

    applyQuickLoraSelection(node, { name: 'new', strength: 0.7 }, 'old');

    expect(node.lorasWidget.value).toEqual([
      expect.objectContaining({ name: 'new', strength: '0.70' }),
      expect.objectContaining({ name: 'keep', strength: '0.90' }),
    ]);
  });

  it('searches, selects and applies through the real panel', async () => {
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    const node = makeNode();
    graphNodes = [node];
    const quick = new LoraQuickPanel({ node }).open();

    await quick.loadSearch();
    await flush();
    expect(quick.resultsElement.querySelectorAll('.lm-quick__row')).toHaveLength(1);
    expect(quick.detailElement.textContent).toContain('Astral Portrait');

    quick.apply(true);
    expect(node.lorasWidget.value[0]).toMatchObject({ name: 'characters/astral', strength: '0.70' });
    expect(quick.panel.isOpen()).toBe(true);
    quick.close();
  });

  it('renders a video element for video previews', async () => {
    apiMocks.fetchLoraDetails.mockResolvedValue({
      model_name: 'Motion LoRA',
      base_model: 'Wan Video',
      preview_url: '/api/lm/previews?path=%2Fmodels%2Fmotion.mp4&v=123',
    });
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    graphNodes = [makeNode()];
    const quick = new LoraQuickPanel({}).open();
    await quick.loadSearch();
    await quick.loadFolderIndex();
    await flush();

    const preview = quick.detailElement.querySelector('.lm-quick__preview');
    expect(preview.tagName).toBe('VIDEO');
    expect(preview.autoplay).toBe(true);
    expect(preview.muted).toBe(true);
    expect(preview.loop).toBe(true);
    expect(preview.playsInline).toBe(true);
    expect(preview.getAttribute('src')).toContain('motion.mp4');
    expect(quick.detailElement.querySelector('img')).toBeNull();
    quick.close();
  });

  it('refuses to write after the target leaves the workflow', async () => {
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    const node = makeNode();
    graphNodes = [node];
    const quick = new LoraQuickPanel({ node }).open();
    await quick.loadSearch();
    await flush();
    graphNodes = [];

    quick.apply(true);

    expect(node.lorasWidget.value).toEqual([]);
    expect(quick.statusElement.textContent).toContain('no longer on this workflow');
    quick.close();
  });

  it('clears a query on the first Escape and closes on the next', async () => {
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    const node = makeNode();
    graphNodes = [node];
    const quick = new LoraQuickPanel({ node }).open();
    quick.loadSearch = vi.fn();
    quick.searchInput.value = 'astral';

    const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    quick.searchInput.dispatchEvent(event);

    expect(quick.searchInput.value).toBe('');
    expect(quick.panel.isOpen()).toBe(true);
    quick.searchInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(quick.panel.isOpen()).toBe(false);
  });

  it('uses folder navigation by default and preserves recursive counts', async () => {
    apiMocks.fetchLoraFolderIndex.mockResolvedValue({
      count: 2,
      folders: {
        characters: {
          count: 2,
          folders: {
            portraits: {
              count: 1,
              folders: {},
              items: [{ relativePath: 'characters/portraits/astral.safetensors', modelName: 'Astral Portrait' }],
            },
          },
          items: [{ relativePath: 'characters/root.safetensors', modelName: 'Root LoRA' }],
        },
      },
      items: [],
    });
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    const quick = new LoraQuickPanel({ node: makeNode() }).open();
    await quick.loadFolderIndex();

    expect(quick.viewMode).toBe('folders');
    const rootFolder = quick.resultsElement.querySelector('.lm-quick__folder-row');
    expect(rootFolder.textContent).toContain('characters');
    expect(rootFolder.textContent).toContain('2');

    rootFolder.click();
    expect(quick.currentFolder).toBe('characters');
    expect(quick.resultsElement.textContent).toContain('portraits');
    expect(quick.resultsElement.textContent).toContain('Root LoRA');

    quick.resultsElement.querySelector('.lm-quick__folder-row').click();
    expect(quick.currentFolder).toBe('characters/portraits');
    expect(quick.resultsElement.querySelectorAll('.lm-quick__row')).toHaveLength(1);
    quick.resultsElement.querySelector('.lm-quick__folder-back').click();
    expect(quick.currentFolder).toBe('characters');
    quick.close();
  });

  it('switches between Folder and Flat and remembers the choice', async () => {
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    const quick = new LoraQuickPanel({ node: makeNode() }).open();
    await quick.loadFolderIndex();
    await quick.loadSearch();

    quick.viewButtons.flat.click();
    expect(quick.viewMode).toBe('flat');
    expect(localStorage.getItem('lm:quick-panel:view-mode')).toBe('flat');
    expect(quick.resultsElement.querySelectorAll('.lm-quick__row')).toHaveLength(1);

    quick.viewButtons.folders.click();
    expect(localStorage.getItem('lm:quick-panel:view-mode')).toBe('folders');
    expect(quick.resultsElement.querySelector('.lm-quick__folder-nav').textContent).toContain('All');
    quick.close();
  });

  it('shows flat search results and restores the folder after clearing search', async () => {
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    const quick = new LoraQuickPanel({ node: makeNode() }).open();
    await quick.loadFolderIndex();

    quick.searchInput.value = 'astral';
    await quick.loadSearch();
    expect(quick.resultsElement.querySelector('.lm-quick__folder-nav')).toBeNull();
    expect(quick.resultsElement.querySelectorAll('.lm-quick__row')).toHaveLength(1);

    quick.searchInput.value = '';
    quick.renderResults();
    expect(quick.resultsElement.querySelector('.lm-quick__folder-nav')).not.toBeNull();
    quick.close();
  });

  it('keeps arrow navigation active after entering a folder with the mouse', async () => {
    apiMocks.fetchLoraFolderIndex.mockResolvedValue({
      count: 2,
      folders: {
        characters: {
          count: 2,
          folders: {},
          items: [
            { relativePath: 'characters/first.safetensors', modelName: 'First' },
            { relativePath: 'characters/second.safetensors', modelName: 'Second' },
          ],
        },
      },
      items: [],
    });
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    const quick = new LoraQuickPanel({ node: makeNode() }).open();
    await quick.loadFolderIndex();

    quick.resultsElement.querySelector('.lm-quick__folder-row').click();
    expect(document.activeElement).toBe(quick.searchInput);
    const event = pressQuickKey(quick, 'ArrowDown');

    expect(event.defaultPrevented).toBe(true);
    expect(quick.selectedIndex).toBe(1);
    expect(quick.selectedItem().relativePath).toBe('characters/second.safetensors');
    expect(quick.resultsElement.querySelector('.lm-quick__row.is-selected').textContent).toContain('Second');
    quick.close();
  });

  it('navigates mixed folders and LoRAs with arrows and Enter', async () => {
    apiMocks.fetchLoraFolderIndex.mockResolvedValue({
      count: 1,
      folders: {
        characters: { count: 0, folders: {}, items: [] },
        styles: { count: 0, folders: {}, items: [] },
      },
      items: [{ relativePath: 'root.safetensors', modelName: 'Root LoRA' }],
    });
    const { LoraQuickPanel } = await import(QUICK_PANEL_MODULE);
    const node = makeNode();
    graphNodes = [node];
    const quick = new LoraQuickPanel({ node }).open();
    await quick.loadFolderIndex();

    pressQuickKey(quick, 'ArrowDown');
    expect(quick.resultsElement.querySelectorAll('.lm-quick__folder-row')[1].classList.contains('is-selected')).toBe(true);
    pressQuickKey(quick, 'ArrowRight');
    expect(quick.currentFolder).toBe('styles');
    pressQuickKey(quick, 'ArrowLeft');
    expect(quick.currentFolder).toBe('');
    expect(quick.selectedIndex).toBe(1);

    pressQuickKey(quick, 'Enter');
    expect(quick.currentFolder).toBe('styles');
    pressQuickKey(quick, 'ArrowLeft');
    pressQuickKey(quick, 'ArrowDown');
    expect(quick.selectedItem().relativePath).toBe('root.safetensors');
    pressQuickKey(quick, 'Enter');
    await flush();
    expect(node.lorasWidget.value).toEqual([
      expect.objectContaining({ name: 'root', active: true }),
    ]);
  });
});

function pressQuickKey(quick, key) {
  quick.resultsElement.querySelectorAll('button').forEach((row) => {
    row.scrollIntoView = vi.fn();
  });
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
  quick.searchInput.dispatchEvent(event);
  return event;
}
