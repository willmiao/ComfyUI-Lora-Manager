import { describe, it, beforeEach, expect, vi } from 'vitest';

const {
  EVENTS_MODULE,
  API_MODULE,
  APP_MODULE,
} = vi.hoisted(() => ({
  EVENTS_MODULE: new URL('../../../web/comfyui/loras_widget_events.js', import.meta.url).pathname,
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
}));

const fetchApi = vi.fn();
const toastAdd = vi.fn();

vi.mock(API_MODULE, () => ({
  api: { fetchApi: (...args) => fetchApi(...args) },
}));

vi.mock(APP_MODULE, () => ({
  app: { extensionManager: { toast: { add: (...args) => toastAdd(...args) } } },
}));

function jsonResponse(body, ok = true) {
  return {
    ok,
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

/** Route the menu's requests: the favorite lookup on open, then usage tips and the save. */
function mockServer(usageTipsResponse) {
  fetchApi.mockImplementation(async (url) => {
    if (url.startsWith('/lm/loras/favorite')) {
      return jsonResponse({ success: true, favorite: false, file_path: '/loras/mianne.safetensors' });
    }
    if (url.startsWith('/lm/loras/usage-tips')) {
      return usageTipsResponse;
    }
    return jsonResponse({ success: true });
  });
}

function recommendedItem() {
  return [...document.querySelectorAll('.lm-lora-menu-item')].find((item) =>
    /Recommended Strength/.test(item.textContent)
  );
}

function savedBody() {
  const call = fetchApi.mock.calls.find(([url]) => url === '/lm/loras/save-metadata');
  return call ? JSON.parse(call[1].body) : null;
}

async function openMenu(entry) {
  const { createContextMenu } = await import(EVENTS_MODULE);
  const widget = { value: [entry], callback: vi.fn() };
  createContextMenu(10, 10, entry.name, widget, null, vi.fn());
  await flush();
  return widget;
}

describe('LoRA widget context menu — recommended strength', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    fetchApi.mockReset();
    toastAdd.mockReset();
  });

  it('saves the entry strength into the usage tips, keeping other tips', async () => {
    mockServer(jsonResponse({
      success: true,
      usage_tips: '{"strength_min": 0.5, "strength_max": 1.2, "clip_strength": 0.4}',
      file_path: '/loras/mianne.safetensors',
    }));
    await openMenu({ name: 'characters/mianne', strength: 0.85, clipStrength: 0.85 });

    recommendedItem().click();
    await flush();

    expect(fetchApi).toHaveBeenCalledWith('/lm/loras/usage-tips?name=characters%2Fmianne');
    const body = savedBody();
    expect(body.file_path).toBe('/loras/mianne.safetensors');
    expect(JSON.parse(body.usage_tips)).toEqual({
      strength_min: 0.5,
      strength_max: 1.2,
      strength: 0.85,
    });
    expect(toastAdd).toHaveBeenCalledWith(
      expect.objectContaining({ severity: 'success', detail: 'Recommended strength set to 0.85' })
    );
  });

  it('saves a differing clip strength as clip_strength', async () => {
    mockServer(jsonResponse({ success: true, usage_tips: '', file_path: '/loras/mianne.safetensors' }));
    await openMenu({ name: 'mianne', strength: 1, clipStrength: 0.6, expanded: true });

    recommendedItem().click();
    await flush();

    expect(JSON.parse(savedBody().usage_tips)).toEqual({ strength: 1, clip_strength: 0.6 });
    expect(toastAdd).toHaveBeenCalledWith(
      expect.objectContaining({ detail: 'Recommended strength set to 1.00, clip 0.60' })
    );
  });

  it('reports a LoRA missing from the cache instead of writing metadata', async () => {
    mockServer(jsonResponse({ success: false, error: 'Lora not found in cache' }, false));
    await openMenu({ name: 'nope', strength: 1, clipStrength: 1 });

    recommendedItem().click();
    await flush();

    expect(savedBody()).toBeNull();
    expect(toastAdd).toHaveBeenCalledWith(
      expect.objectContaining({ severity: 'error', detail: 'Lora not found in cache' })
    );
  });

  it('closes the menu when the entry is clicked', async () => {
    mockServer(jsonResponse({ success: true, usage_tips: '{}', file_path: '/loras/mianne.safetensors' }));
    await openMenu({ name: 'mianne', strength: 1, clipStrength: 1 });
    expect(document.querySelector('.lm-lora-context-menu')).toBeTruthy();

    recommendedItem().click();
    await flush();

    expect(document.querySelector('.lm-lora-context-menu')).toBeNull();
  });
});
