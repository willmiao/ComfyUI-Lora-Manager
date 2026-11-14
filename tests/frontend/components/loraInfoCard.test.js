import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  APP_MODULE,
  UTILS_MODULE,
  LORA_UTILS_MODULE,
  CANVAS_API_MODULE,
  STYLES_MODULE,
  QUICK_PANEL_MODULE,
  MEDIA_MODULE,
  INFO_CARD_MODULE,
} = vi.hoisted(() => ({
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  UTILS_MODULE: new URL('../../../web/comfyui/utils.js', import.meta.url).pathname,
  LORA_UTILS_MODULE: new URL('../../../web/comfyui/loras_widget_utils.js', import.meta.url).pathname,
  CANVAS_API_MODULE: new URL('../../../web/comfyui/lora_canvas_api.js', import.meta.url).pathname,
  STYLES_MODULE: new URL('../../../web/comfyui/lm_styles_loader.js', import.meta.url).pathname,
  QUICK_PANEL_MODULE: new URL('../../../web/comfyui/lora_quick_panel.js', import.meta.url).pathname,
  MEDIA_MODULE: new URL('../../../web/comfyui/mediaTypes.js', import.meta.url).pathname,
  INFO_CARD_MODULE: new URL('../../../web/comfyui/lora_info_card.js', import.meta.url).pathname,
}));

const { appMock, apiMocks, quickMock } = vi.hoisted(() => ({
  appMock: { registerExtension: vi.fn(), canvas: {} },
  apiMocks: {
    fetchLoraDetails: vi.fn(),
    formatUsageTips: vi.fn(() => 'Strength 0.7'),
    openLoraManager: vi.fn(),
    refreshLoraMetadata: vi.fn(),
    saveLoraFavorite: vi.fn(),
    saveLoraNotes: vi.fn(),
  },
  quickMock: { openLoraQuickPanel: vi.fn() },
}));

vi.mock(APP_MODULE, () => ({ app: appMock }));
vi.mock(UTILS_MODULE, () => ({
  LORA_PATTERN: /<lora:([^:>]+):([^:>]+)(?::([^:>]+))?>/,
}));
vi.mock(LORA_UTILS_MODULE, () => ({
  normalizeLoraNameKey: (name) => String(name || '').replace(/\.(safetensors|ckpt|pt|bin)$/i, ''),
  syncClipStrengthIfCollapsed: (entry) => {
    if (entry.expanded === false) entry.clipStrength = entry.strength;
    return entry;
  },
}));
vi.mock(CANVAS_API_MODULE, () => apiMocks);
vi.mock(STYLES_MODULE, () => ({ ensureLmStyles: vi.fn() }));
vi.mock(QUICK_PANEL_MODULE, () => quickMock);
vi.mock(MEDIA_MODULE, () => ({ isVideoPreviewUrl: vi.fn(() => false) }));

function makeWidget() {
  return {
    value: [{ name: 'astral', strength: '0.50', clipStrength: '0.50', active: true, expanded: false }],
    callback: vi.fn(),
  };
}

function makeAnchor() {
  const nodeElement = document.createElement('div');
  nodeElement.dataset.nodeId = '1';
  nodeElement.getBoundingClientRect = vi.fn(() => ({
    left: 100,
    top: 60,
    right: 500,
    bottom: 500,
    width: 400,
    height: 440,
  }));
  const container = document.createElement('div');
  container.className = 'lm-loras-container';
  const row = document.createElement('div');
  row.className = 'lm-lora-entry';
  row.dataset.loraName = 'astral';
  container.appendChild(row);
  nodeElement.appendChild(container);
  document.body.appendChild(nodeElement);
  return row;
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
}

describe('LoRA info card', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    window.innerWidth = 1024;
    window.innerHeight = 768;
    vi.clearAllMocks();
    vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1));
    vi.stubGlobal('cancelAnimationFrame', vi.fn());
    apiMocks.fetchLoraDetails.mockResolvedValue({
      model_name: 'Astral Portrait',
      base_model: 'Flux',
      file_name: 'astral.safetensors',
      file_path: '/models/astral.safetensors',
      notes: 'Original notes',
      description: 'Version description',
      modelDescription: 'Model description',
      usage_tips: { strength: 0.7 },
      civitai: { trainedWords: ['astral', 'cinematic'] },
    });
    apiMocks.saveLoraNotes.mockResolvedValue({ success: true });
    apiMocks.saveLoraFavorite.mockResolvedValue({ success: true });
  });

  it('updates strength and the collapsed clip strength through the widget', async () => {
    const { updateLoraStrength } = await import(INFO_CARD_MODULE);
    const widget = makeWidget();

    expect(updateLoraStrength(widget, 'astral', 'strength', '0.75')).toBe(true);

    expect(widget.value[0]).toMatchObject({ strength: '0.75', clipStrength: '0.75' });
    expect(widget.callback).toHaveBeenCalledOnce();
  });

  it('positions the card beside the whole node with a comfortable gap', async () => {
    const { LoraInfoCard } = await import(INFO_CARD_MODULE);
    const card = new LoraInfoCard({
      node: { id: 1 },
      widget: makeWidget(),
      loraName: 'astral',
      anchorElement: makeAnchor(),
    }).open();

    expect(card.panel.getRect().left).toBe(510);
    expect(card.panel.getRect().left - card.anchorRect().right).toBe(10);
    card.close();
  });

  it('uses the left side when the right side does not fit', async () => {
    const { computeInfoCardPosition } = await import(INFO_CARD_MODULE);
    const position = computeInfoCardPosition(
      { left: 500, right: 900, top: 60, bottom: 500 },
      { width: 410, height: 640 },
      { width: 1024, height: 768 },
    );

    expect(position).toEqual({ left: 80, top: 60 });
  });

  it('shows trigger words read-only without a Send to prompt action', async () => {
    const { LoraInfoCard } = await import(INFO_CARD_MODULE);
    const card = new LoraInfoCard({
      node: { id: 1 },
      widget: makeWidget(),
      loraName: 'astral',
      anchorElement: makeAnchor(),
    }).open();
    await card.loadDetails();

    expect(card.tabContent.querySelectorAll('span.lm-info-card__chip')).toHaveLength(2);
    expect(card.tabContent.querySelectorAll('button.lm-info-card__chip')).toHaveLength(0);
    expect(card.panel.body.textContent).toContain('TriggerWord Toggle');
    expect(card.panel.body.textContent).not.toContain('Send to prompt');
    card.close();
  });

  it('edits and saves notes through the existing LM metadata API', async () => {
    const { LoraInfoCard } = await import(INFO_CARD_MODULE);
    const card = new LoraInfoCard({
      node: { id: 1 },
      widget: makeWidget(),
      loraName: 'astral',
      anchorElement: makeAnchor(),
    }).open();
    await card.loadDetails();
    card.tabButtons.notes.click();

    const textarea = card.tabContent.querySelector('textarea');
    textarea.value = 'Updated notes';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    const save = card.tabContent.querySelector('button');
    expect(save.disabled).toBe(false);
    save.click();
    await flush();

    expect(apiMocks.saveLoraNotes).toHaveBeenCalledWith('/models/astral.safetensors', 'Updated notes');
    expect(card.originalNotes).toBe('Updated notes');
    expect(card.notesDirty()).toBe(false);
    card.close();
  });

  it('lets the notes editor fill the tab height', async () => {
    const { LoraInfoCard } = await import(INFO_CARD_MODULE);
    const card = new LoraInfoCard({
      node: { id: 1 },
      widget: makeWidget(),
      loraName: 'astral',
      anchorElement: makeAnchor(),
    }).open();
    await card.loadDetails();
    card.tabButtons.notes.click();

    expect(card.tabContent.classList.contains('lm-info-card__tab-content--notes')).toBe(true);
    expect(card.tabContent.querySelector('textarea')).not.toBeNull();

    card.tabButtons.overview.click();
    expect(card.tabContent.classList.contains('lm-info-card__tab-content--notes')).toBe(false);
    card.close();
  });

  it('shows version and model descriptions from local metadata', async () => {
    const { LoraInfoCard } = await import(INFO_CARD_MODULE);
    const card = new LoraInfoCard({
      node: { id: 1 },
      widget: makeWidget(),
      loraName: 'astral',
      anchorElement: makeAnchor(),
    }).open();
    await card.loadDetails();
    card.tabButtons.description.click();

    expect(card.tabContent.textContent).toContain('Version description');
    expect(card.tabContent.textContent).toContain('Model description');
    card.close();
  });

  it('remembers the last tab when another LoRA is inspected', async () => {
    const { LoraInfoCard } = await import(INFO_CARD_MODULE);
    const first = new LoraInfoCard({
      node: { id: 1 },
      widget: makeWidget(),
      loraName: 'astral',
      anchorElement: makeAnchor(),
    }).open();
    await first.loadDetails();
    first.tabButtons.notes.click();
    first.close();

    const second = new LoraInfoCard({
      node: { id: 1 },
      widget: makeWidget(),
      loraName: 'another-lora',
      anchorElement: makeAnchor(),
    }).open();
    await second.loadDetails();

    expect(second.activeTab).toBe('notes');
    expect(second.tabButtons.notes.getAttribute('aria-pressed')).toBe('true');
    expect(second.tabContent.querySelector('textarea')).not.toBeNull();
    second.close();
  });

  it('renders safe description HTML like the Lora Info node', async () => {
    const { LoraInfoCard } = await import(INFO_CARD_MODULE);
    const card = new LoraInfoCard({
      node: { id: 1 },
      widget: makeWidget(),
      loraName: 'astral',
      anchorElement: makeAnchor(),
    }).open();
    await card.loadDetails();
    apiMocks.fetchLoraDetails.mockResolvedValue({
      model_name: 'Astral Portrait',
      file_path: '/models/astral.safetensors',
      modelDescription: '<p>Model <strong>description</strong><span style="color: rgb(64, 192, 87); background-image: url(https://example.com/bad.png)">Colored</span><img src="https://example.com/image.png"><a href="javascript:alert(1)" onclick="alert(2)">Link</a><script>alert(3)</script></p>',
    });
    await card.loadDetails();
    card.tabButtons.description.click();

    const description = card.tabContent.querySelector('.lm-info-card__description');
    expect(description.querySelector('strong').textContent).toBe('description');
    expect(description.querySelector('span').style.color).toBe('rgb(64, 192, 87)');
    expect(description.querySelector('span').style.backgroundImage).toBe('');
    expect(description.querySelector('img')).not.toBeNull();
    expect(description.querySelector('script')).toBeNull();
    expect(description.querySelector('a').hasAttribute('href')).toBe(false);
    expect(description.querySelector('a').hasAttribute('onclick')).toBe(false);
    expect(description.querySelector('a').getAttribute('target')).toBe('_blank');
    card.close();
  });

  it('shows the favorite state and toggles it through the metadata API', async () => {
    apiMocks.fetchLoraDetails.mockResolvedValue({
      model_name: 'Astral Portrait',
      file_name: 'astral.safetensors',
      file_path: '/models/astral.safetensors',
      favorite: false,
    });
    const { LoraInfoCard } = await import(INFO_CARD_MODULE);
    const card = new LoraInfoCard({
      node: { id: 1 },
      widget: makeWidget(),
      loraName: 'astral',
      anchorElement: makeAnchor(),
    }).open();
    await card.loadDetails();

    const star = card.tabContent.querySelector('button.lm-info-card__favorite');
    expect(star).not.toBeNull();
    expect(star.textContent).toBe('☆');
    expect(star.getAttribute('aria-pressed')).toBe('false');

    star.click();
    await flush();

    expect(apiMocks.saveLoraFavorite).toHaveBeenCalledWith('/models/astral.safetensors', true);
    expect(card.details.favorite).toBe(true);
    expect(star.textContent).toBe('★');
    expect(star.getAttribute('aria-pressed')).toBe('true');
    card.close();
  });

  it('shows library badges from the local entry', async () => {
    apiMocks.fetchLoraDetails.mockResolvedValue({
      model_name: 'Astral Portrait',
      file_name: 'astral.safetensors',
      file_path: '/models/astral.safetensors',
      update_available: true,
      exclude: true,
      skip_metadata_refresh: true,
    });
    const { LoraInfoCard } = await import(INFO_CARD_MODULE);
    const card = new LoraInfoCard({
      node: { id: 1 },
      widget: makeWidget(),
      loraName: 'astral',
      anchorElement: makeAnchor(),
    }).open();
    await card.loadDetails();

    const labels = [...card.tabContent.querySelectorAll('.lm-info-card__badge')]
      .map((badge) => badge.textContent);
    expect(labels).toEqual(['↑ Update available', 'Excluded', 'Metadata refresh skipped']);
    expect(card.tabContent.querySelector('.lm-info-card__badge--update')).not.toBeNull();
    card.close();
  });

  it('shows the CivitAI license icons in the overview', async () => {
    apiMocks.fetchLoraDetails.mockResolvedValue({
      model_name: 'Astral Portrait',
      file_name: 'astral.safetensors',
      file_path: '/models/astral.safetensors',
      license_flags: 0,
      use_new_license_icons: true,
      civitai: {
        trainedWords: [],
        model: {
          allowNoCredit: false,
          allowCommercialUse: [],
          allowDerivatives: false,
          allowDifferentLicense: false,
        },
      },
    });
    const { LoraInfoCard } = await import(INFO_CARD_MODULE);
    const card = new LoraInfoCard({
      node: { id: 1 },
      widget: makeWidget(),
      loraName: 'astral',
      anchorElement: makeAnchor(),
    }).open();
    await card.loadDetails();

    expect(card.tabContent.textContent).toContain('License');
    const icons = card.tabContent.querySelectorAll('.lm-info-card__license-icon-new');
    expect(icons).toHaveLength(5);
    expect([...icons].every((icon) => icon.classList.contains('denied'))).toBe(true);
    expect(icons[0].getAttribute('aria-label')).toBe('No commercial use');
    card.close();
  });

  it('honours the legacy license icon style', async () => {
    apiMocks.fetchLoraDetails.mockResolvedValue({
      model_name: 'Astral Portrait',
      file_name: 'astral.safetensors',
      file_path: '/models/astral.safetensors',
      license_flags: 0,
      use_new_license_icons: false,
      civitai: {
        trainedWords: [],
        model: {
          allowNoCredit: false,
          allowCommercialUse: [],
          allowDerivatives: false,
          allowDifferentLicense: false,
        },
      },
    });
    const { LoraInfoCard } = await import(INFO_CARD_MODULE);
    const card = new LoraInfoCard({
      node: { id: 1 },
      widget: makeWidget(),
      loraName: 'astral',
      anchorElement: makeAnchor(),
    }).open();
    await card.loadDetails();

    expect(card.tabContent.querySelectorAll('.lm-info-card__license-icon')).toHaveLength(7);
    expect(card.tabContent.querySelectorAll('.lm-info-card__license-icon-new')).toHaveLength(0);
    card.close();
  });

  it('omits the license section when only cached license defaults exist', async () => {
    apiMocks.fetchLoraDetails.mockResolvedValue({
      model_name: 'Astral Portrait',
      file_name: 'astral.safetensors',
      file_path: '/models/astral.safetensors',
      license_flags: 127,
      civitai: { trainedWords: [], model: { type: 'LORA' } },
    });
    const { LoraInfoCard } = await import(INFO_CARD_MODULE);
    const card = new LoraInfoCard({
      node: { id: 1 },
      widget: makeWidget(),
      loraName: 'astral',
      anchorElement: makeAnchor(),
    }).open();
    await card.loadDetails();

    expect(card.tabContent.querySelector('.lm-info-card__license')).toBeNull();
    expect(card.tabContent.textContent).not.toContain('License');
    card.close();
  });

  it('keeps the status line empty until an action reports progress', async () => {
    const { LoraInfoCard } = await import(INFO_CARD_MODULE);
    const card = new LoraInfoCard({
      node: { id: 1 },
      widget: makeWidget(),
      loraName: 'astral',
      anchorElement: makeAnchor(),
    }).open();
    await card.loadDetails();

    expect(card.statusElement.textContent).toBe('');
    expect(card.statusElement.getAttribute('role')).toBe('status');
    card.setStatus('Notes saved');
    expect(card.statusElement.textContent).toBe('Notes saved');
    card.close();
  });
});
