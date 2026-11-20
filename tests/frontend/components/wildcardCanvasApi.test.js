import { describe, expect, it, vi } from 'vitest';

const { API_MODULE, fetchApiMock } = vi.hoisted(() => ({
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
  fetchApiMock: vi.fn(),
}));

vi.mock(API_MODULE, () => ({ api: { fetchApi: fetchApiMock } }));

describe('Wildcard canvas API', () => {
  it('reuses the named manager tab for the wildcard modal deep link', async () => {
    const openMock = vi.spyOn(window, 'open').mockImplementation(() => null);
    try {
      const { openWildcardManager } = await import('../../../web/comfyui/wildcard_canvas_api.js');

      openWildcardManager('/models/wild.safetensors');

      expect(openMock).toHaveBeenCalledWith(
        `${window.location.origin}/wildcards#model=%2Fmodels%2Fwild.safetensors`,
        'lm-lora-manager',
      );
    } finally {
      openMock.mockRestore();
    }
  });

  it('opens the manual wildcards folder through the shared endpoint', async () => {
    fetchApiMock.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    });

    const { openWildcardsFolder } = await import('../../../web/comfyui/wildcard_canvas_api.js');
    await openWildcardsFolder();

    expect(fetchApiMock).toHaveBeenCalledWith('/lm/wildcards/open-location', {
      method: 'POST',
    });
  });
});
