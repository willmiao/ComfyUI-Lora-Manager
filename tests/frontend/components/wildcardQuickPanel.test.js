import { describe, expect, it, vi } from 'vitest';

const { CANVAS_API_MODULE, setActiveMock } = vi.hoisted(() => ({
    CANVAS_API_MODULE: new URL('../../../web/comfyui/wildcard_canvas_api.js', import.meta.url).pathname,
    setActiveMock: vi.fn(),
}));

vi.mock(CANVAS_API_MODULE, () => ({
    openWildcardManager: vi.fn(),
    searchWildcardLibrary: vi.fn(),
    setWildcardActive: setActiveMock,
}));

describe('WildcardQuickPanel', () => {
    it('filters the library down to active resources by default', async () => {
        const { WildcardQuickPanel } = await import('../../../web/comfyui/wildcard_quick_panel.js');
        const panel = new WildcardQuickPanel();
        panel.items = [{ file_path: '/active', active: true }, { file_path: '/inactive', active: false }];

        expect(panel.visibleItems().map((item) => item.file_path)).toEqual(['/active']);
        panel.activeOnly = false;
        expect(panel.visibleItems()).toHaveLength(2);
    });

    it('uses the shared activation API for toggles', async () => {
        const { WildcardQuickPanel } = await import('../../../web/comfyui/wildcard_quick_panel.js');
        const panel = new WildcardQuickPanel();
        panel.load = vi.fn().mockResolvedValue(undefined);
        setActiveMock.mockResolvedValue({ success: true });

        await panel.toggle({ file_path: '/inactive', active: false });

        expect(setActiveMock).toHaveBeenCalledWith('/inactive', true);
        expect(panel.load).toHaveBeenCalledOnce();
    });
});
