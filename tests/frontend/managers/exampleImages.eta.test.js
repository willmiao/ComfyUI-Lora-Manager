import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
    showToast: vi.fn(),
}));
vi.mock('../../../static/js/state/index.js', () => ({
    state: { global: { settings: {} } },
}));
vi.mock('../../../static/js/utils/storageHelpers.js', () => ({
    getStorageItem: vi.fn(() => false),
    setStorageItem: vi.fn(),
}));
vi.mock('../../../static/js/managers/SettingsManager.js', () => ({
    settingsManager: {},
}));

const { ExampleImagesManager } = await import(
    '../../../static/js/managers/ExampleImagesManager.js'
);

describe('ExampleImagesManager ETA rendering', () => {
    beforeEach(() => {
        document.body.innerHTML = `
            <span id="elapsedTime"></span>
            <span id="remainingTime"></span>
        `;
        vi.stubGlobal('fetch', vi.fn(async () => ({
            ok: true,
            json: async () => ({ success: false }),
        })));
    });

    it('uses active elapsed time and the throughput estimator', () => {
        const manager = new ExampleImagesManager();
        manager.etaTracker = {
            update: vi.fn(() => 123),
            reset: vi.fn(),
        };

        manager.updateTimeStats({
            status: 'running',
            completed: 5,
            total: 10,
            start_time: 1,
            elapsed_seconds: 42.5,
        });

        expect(document.getElementById('elapsedTime').textContent).toBe('00:00:42');
        expect(document.getElementById('remainingTime').textContent).toBe('00:02:03');
        expect(manager.etaTracker.update).toHaveBeenCalledWith(5, 10, { running: true });
    });

    it('does not count paused time as progress', () => {
        const manager = new ExampleImagesManager();
        manager.etaTracker = {
            update: vi.fn(() => null),
            reset: vi.fn(),
        };

        manager.updateTimeStats({
            status: 'paused',
            completed: 5,
            total: 10,
            elapsed_seconds: 42.5,
        });

        expect(document.getElementById('remainingTime').textContent).toBe('--:--:--');
        expect(manager.etaTracker.update).toHaveBeenCalledWith(5, 10, { running: false });
    });

    it('falls back to start_time when elapsed_seconds is absent', () => {
        const manager = new ExampleImagesManager();
        manager.etaTracker = {
            update: vi.fn(() => 60),
            reset: vi.fn(),
        };

        manager.updateTimeStats({
            status: 'running',
            completed: 5,
            total: 10,
            start_time: Date.now() / 1000 - 30,
        });

        const elapsed = Number(
            document.getElementById('elapsedTime').textContent.split(':').pop()
        );
        expect(elapsed).toBeGreaterThanOrEqual(29);
        expect(elapsed).toBeLessThanOrEqual(31);
        expect(document.getElementById('remainingTime').textContent).toBe('00:01:00');
    });
});
