import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const {
  EDITOR_MODULE,
  API_FACTORY_MODULE,
  I18N_MODULE,
  UI_HELPERS_MODULE,
  MENU_POSITION_MODULE,
} = vi.hoisted(() => ({
  EDITOR_MODULE: new URL('../../../static/js/components/shared/QuantizationEditor.js', import.meta.url).pathname,
  API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
  I18N_MODULE: new URL('../../../static/js/utils/i18nHelpers.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  MENU_POSITION_MODULE: new URL('../../../static/js/utils/menuPosition.js', import.meta.url).pathname,
}));

vi.mock(API_FACTORY_MODULE, () => ({
  getModelApiClient: vi.fn(),
}));

vi.mock(I18N_MODULE, () => ({
  translate: vi.fn((key, params, fallback) => fallback || key),
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: vi.fn(),
}));

vi.mock(MENU_POSITION_MODULE, () => ({
  positionFixedMenu: vi.fn(),
}));

function createCard({ quantization = 'FP8', source = 'civitai' } = {}) {
  const card = document.createElement('div');
  card.dataset.filepath = '/models/example.safetensors';
  card.dataset.quantization = quantization;
  card.dataset.quantization_source = source;

  const badge = document.createElement('button');
  badge.className = 'quant-badge';
  badge.textContent = quantization;
  card.appendChild(badge);
  document.body.appendChild(card);
  return { card, badge };
}

describe('QuantizationEditor', () => {
  let openQuantizationEditor;
  let closeQuantizationEditor;
  let saveModelMetadata;
  let showToast;

  beforeEach(async () => {
    ({ openQuantizationEditor, closeQuantizationEditor } = await import(EDITOR_MODULE));
    const { getModelApiClient } = await import(API_FACTORY_MODULE);
    ({ showToast } = await import(UI_HELPERS_MODULE));
    saveModelMetadata = vi.fn().mockResolvedValue({ success: true });
    getModelApiClient.mockReturnValue({ saveModelMetadata });
    showToast.mockClear();
  });

  afterEach(() => {
    closeQuantizationEditor();
    document.body.innerHTML = '';
  });

  it('opens an anchored editor with presets and the current value', () => {
    const { card, badge } = createCard({ quantization: 'FP8', source: 'manual' });

    openQuantizationEditor(card, badge);

    const popover = document.getElementById('quantizationEditorPopover');
    const input = popover.querySelector('.quantization-input');
    expect(input.value).toBe('FP8');
    expect(popover.querySelectorAll('datalist option')).toHaveLength(7);
    expect(popover.querySelector('.quantization-popover-hint').textContent).toContain('Manually set');
    expect(badge.getAttribute('aria-expanded')).toBe('true');
  });

  it('saves a custom value and closes after success', async () => {
    const { card, badge } = createCard();
    openQuantizationEditor(card, badge);
    const input = document.querySelector('.quantization-input');
    input.value = ' nvfp4 ';

    document.querySelector('.quantization-save-btn').click();

    await vi.waitFor(() => {
      expect(document.getElementById('quantizationEditorPopover')).toBeNull();
    });
    expect(saveModelMetadata).toHaveBeenCalledWith('/models/example.safetensors', {
      quantization: 'nvfp4',
    });
    expect(showToast).toHaveBeenCalledWith('toast.models.precisionUpdated', {}, 'success');
  });

  it('clears the override through Reset to Auto', async () => {
    const { card, badge } = createCard({ quantization: 'NVFP4', source: 'manual' });
    openQuantizationEditor(card, badge);

    document.querySelector('.quantization-auto-btn').click();

    await vi.waitFor(() => {
      expect(document.getElementById('quantizationEditorPopover')).toBeNull();
    });
    expect(saveModelMetadata).toHaveBeenCalledWith('/models/example.safetensors', {
      quantization: null,
    });
  });

  it('cancels with Escape without saving', () => {
    const { card, badge } = createCard();
    openQuantizationEditor(card, badge);
    const input = document.querySelector('.quantization-input');
    input.value = 'Q8_0';

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));

    expect(document.getElementById('quantizationEditorPopover')).toBeNull();
    expect(saveModelMetadata).not.toHaveBeenCalled();
    expect(badge.getAttribute('aria-expanded')).toBe('false');
  });

  it('keeps the edited value available when saving fails', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    saveModelMetadata.mockRejectedValue(new Error('offline'));
    const { card, badge } = createCard();
    openQuantizationEditor(card, badge);
    const input = document.querySelector('.quantization-input');
    input.value = 'Q6_K';

    document.querySelector('.quantization-save-btn').click();

    await vi.waitFor(() => {
      expect(showToast).toHaveBeenCalledWith('toast.models.precisionUpdateFailed', {}, 'error');
    });
    expect(document.getElementById('quantizationEditorPopover')).not.toBeNull();
    expect(input.value).toBe('Q6_K');
    expect(input.disabled).toBe(false);
    consoleError.mockRestore();
  });
});
