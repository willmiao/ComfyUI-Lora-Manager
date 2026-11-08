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
            <div id="downloadFailureSummary" class="hidden"></div>
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

describe('ExampleImagesManager failure summary', () => {
    beforeEach(() => {
        document.body.innerHTML = `
            <div id="downloadFailureSummary" class="hidden"></div>
        `;
        vi.stubGlobal('fetch', vi.fn(async () => ({
            ok: true,
            json: async () => ({ success: false }),
        })));
    });

    it('renders skipped reasons and retry count', () => {
        const manager = new ExampleImagesManager();
        const visible = manager.updateFailureSummary({
            failure_summary: {
                no_media: 2,
                unavailable: 3,
                metadata_missing: 1,
                unknown: 1,
                total: 7,
            },
            retryable_count: 2,
        });

        const element = document.getElementById('downloadFailureSummary');
        expect(visible).toBe(true);
        expect(element.classList.contains('hidden')).toBe(false);
        expect(element.textContent).toBe(
            'Not downloaded: 2 without Civitai media · 3 unavailable at source · ' +
            '1 metadata missing · 1 unclassified · 2 will retry'
        );
        expect(element.title).toContain('Unavailable at source');
        expect(manager.hasReportedIssues({ failure_summary: { total: 7, unavailable: 3 } })).toBe(true);
    });

    it('hides itself when there is nothing to report', () => {
        const manager = new ExampleImagesManager();
        const visible = manager.updateFailureSummary({
            failure_summary: { total: 0 },
            retryable_count: 0,
        });

        const element = document.getElementById('downloadFailureSummary');
        expect(visible).toBe(false);
        expect(element.classList.contains('hidden')).toBe(true);
        expect(element.textContent).toBe('');
        expect(manager.hasReportedIssues({ failure_summary: { total: 0 } })).toBe(false);
    });
});
