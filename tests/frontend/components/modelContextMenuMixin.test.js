import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ModelContextMenuMixin } from '../../../static/js/components/ContextMenu/ModelContextMenuMixin.js';

describe('ModelContextMenuMixin.getModelTypePrefix', () => {
  it('maps every known model type to its API route prefix', () => {
    expect(ModelContextMenuMixin.getModelTypePrefix.call({ modelType: 'lora' })).toBe('loras');
    expect(ModelContextMenuMixin.getModelTypePrefix.call({ modelType: 'checkpoint' })).toBe('checkpoints');
    expect(ModelContextMenuMixin.getModelTypePrefix.call({ modelType: 'embedding' })).toBe('embeddings');
  });

  it('falls back to the loras prefix for unknown types', () => {
    expect(ModelContextMenuMixin.getModelTypePrefix.call({ modelType: 'unknown' })).toBe('loras');
    expect(ModelContextMenuMixin.getModelTypePrefix.call({})).toBe('loras');
  });
});

describe('ModelContextMenuMixin.updateEnrichMenuItem', () => {
  function setupMenu() {
    document.body.innerHTML = '<div id="menu"><div data-action="enrich-hf-llm"></div></div>';
    return { menu: document.getElementById('menu') };
  }

  function cardWith(dataset) {
    return { dataset };
  }

  it('enables enrichment for Hugging Face links', () => {
    const context = setupMenu();
    ModelContextMenuMixin.updateEnrichMenuItem.call(
      context,
      cardWith({ hf_url: 'https://huggingface.co/user/repo' })
    );

    const item = context.menu.querySelector('[data-action="enrich-hf-llm"]');
    expect(item.classList.contains('disabled')).toBe(false);
    expect(item.title).toBe('');
  });

  it('enables enrichment for ModelScope links', () => {
    const context = setupMenu();
    ModelContextMenuMixin.updateEnrichMenuItem.call(
      context,
      cardWith({
        source_platform: 'modelscope',
        source_url: 'https://modelscope.cn/models/user/repo',
      })
    );

    const item = context.menu.querySelector('[data-action="enrich-hf-llm"]');
    expect(item.classList.contains('disabled')).toBe(false);
  });

  it('disables enrichment for TensorArt and explains why', () => {
    const context = setupMenu();
    ModelContextMenuMixin.updateEnrichMenuItem.call(
      context,
      cardWith({
        source_platform: 'tensorart',
        source_url: 'https://tensor.art/models/827823520299086029',
      })
    );

    const item = context.menu.querySelector('[data-action="enrich-hf-llm"]');
    expect(item.classList.contains('disabled')).toBe(true);
    expect(item.title).toContain('TensorArt');
  });

  it('disables enrichment when no source is linked', () => {
    const context = setupMenu();
    ModelContextMenuMixin.updateEnrichMenuItem.call(context, cardWith({}));

    const item = context.menu.querySelector('[data-action="enrich-hf-llm"]');
    expect(item.classList.contains('disabled')).toBe(true);
    expect(item.title).toContain('Link this model to a model source');
  });
});

describe('ModelContextMenuMixin._renderSupportedSources', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    document.body.innerHTML = '<div id="hfSupportedSources">static fallback</div>';
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('renders the server-provided example URLs', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        { platform: 'huggingface', example_url: 'https://huggingface.co/user/repo' },
        { platform: 'modelscope', example_url: 'https://modelscope.cn/models/user/repo' },
        { platform: 'tensorart', example_url: 'https://tensor.art/models/123' },
      ],
    });

    await ModelContextMenuMixin._renderSupportedSources.call({});

    const html = document.getElementById('hfSupportedSources').innerHTML;
    expect(html).toContain('https://huggingface.co/user/repo');
    expect(html).toContain('https://modelscope.cn/models/user/repo');
    expect(html).toContain('https://tensor.art/models/123');
  });

  it('keeps the static fallback when the request fails', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('offline'));

    await ModelContextMenuMixin._renderSupportedSources.call({});

    expect(document.getElementById('hfSupportedSources').innerHTML).toBe('static fallback');
  });

  it('escapes markup from the server payload', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ example_url: '<img src=x onerror=alert(1)>' }],
    });

    await ModelContextMenuMixin._renderSupportedSources.call({});

    const html = document.getElementById('hfSupportedSources').innerHTML;
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
  });
});
