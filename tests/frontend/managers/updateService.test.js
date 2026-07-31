import { describe, beforeEach, afterEach, expect, it, vi } from 'vitest';
import { UpdateService } from '../../../static/js/managers/UpdateService.js';
import { state } from '../../../static/js/state/index.js';

function createFetchResponse(payload) {
    return {
        json: vi.fn().mockResolvedValue(payload),
        ok: true,
    };
}

function stubSettingsUpdateChannel(channel) {
    state.global = state.global || {};
    state.global.settings = state.global.settings || {};
    state.global.settings.update_channel = channel;
}

function clearSettingsUpdateChannel() {
    if (state.global?.settings) {
        delete state.global.settings.update_channel;
    }
}

describe('UpdateService passive checks', () => {
    let service;
    let fetchMock;

    beforeEach(() => {
        fetchMock = vi.fn().mockResolvedValue(createFetchResponse({
            success: true,
            current_version: 'v1.0.0',
            latest_version: 'v1.0.0',
            git_info: { short_hash: 'abc123' },
            has_git: true,
        }));
        global.fetch = fetchMock;

        stubSettingsUpdateChannel('release');

        service = new UpdateService();
        service.updateNotificationsEnabled = false;
        service.lastCheckTime = 0;
        service.nightlyMode = false;
    });

    afterEach(() => {
        delete global.fetch;
        clearSettingsUpdateChannel();
    });

    it('skips passive update checks when notifications are disabled', async () => {
        await service.checkForUpdates();

        expect(fetchMock).not.toHaveBeenCalled();
    });

    it('allows manual checks even when notifications are disabled', async () => {
        await service.checkForUpdates({ force: true });

        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(fetchMock).toHaveBeenCalledWith('/api/lm/check-updates?nightly=false');
    });
});

describe('UpdateService nightly notification throttling', () => {
    let fetchMock;
    let updateToggle;
    let updateBadge;

    function stubUpdateBadgeDom() {
        updateToggle = document.createElement('div');
        updateToggle.className = 'update-toggle';
        updateBadge = document.createElement('span');
        updateBadge.className = 'update-badge';
        updateToggle.appendChild(updateBadge);
        document.body.appendChild(updateToggle);

        vi.spyOn(document, 'querySelector').mockImplementation((selector) => {
            if (selector === '.update-toggle') return updateToggle;
            if (selector === '.update-toggle .update-badge') return updateBadge;
            return null;
        });
    }

    function makeUpdateResponse(channel) {
        return {
            success: true,
            current_version: 'v1.0.0',
            latest_version: channel === 'nightly' ? 'main-abc1234' : 'v1.1.0',
            update_available: true,
            git_info: { short_hash: 'abc123' },
            has_git: true,
            nightly: channel === 'nightly',
            changelog: ['test: change'],
            releases: [],
            behind_by: 3,
            commit_date: '2026-07-31',
        };
    }

    beforeEach(() => {
        fetchMock = vi.fn().mockResolvedValue(createFetchResponse(makeUpdateResponse('release')));
        global.fetch = fetchMock;
        stubUpdateBadgeDom();
    });

    afterEach(() => {
        vi.restoreAllMocks();
        delete global.fetch;
    });

    it('shows the nightly badge once and keeps it visible for the session', async () => {
        stubSettingsUpdateChannel('nightly');
        fetchMock.mockResolvedValue(createFetchResponse(makeUpdateResponse('nightly')));

        const service = new UpdateService();
        service.updateNotificationsEnabled = true;

        await service.checkForUpdates({ force: true });

        expect(service.updateAvailable).toBe(true);
        expect(service.nightlyBadgeShown).toBe(true);
        expect(service.nightlyNotifyDate).toBe(service._getTodayKey());
        expect(updateBadge.classList.contains('visible')).toBe(true);

        // A repeated check within the same session keeps the badge visible.
        await service.checkForUpdates({ force: true });
        expect(updateBadge.classList.contains('visible')).toBe(true);
    });

    it('suppresses the nightly badge on a later session in the same day', async () => {
        stubSettingsUpdateChannel('nightly');
        fetchMock.mockResolvedValue(createFetchResponse(makeUpdateResponse('nightly')));

        const firstService = new UpdateService();
        firstService.updateNotificationsEnabled = true;
        await firstService.checkForUpdates({ force: true });
        expect(updateBadge.classList.contains('visible')).toBe(true);

        // Simulate a fresh page session on the same calendar day.
        const secondService = new UpdateService();
        secondService.updateNotificationsEnabled = true;
        await secondService.checkForUpdates({ force: true });

        expect(secondService.updateAvailable).toBe(true);
        expect(secondService.nightlyBadgeShown).toBe(false);
        expect(updateBadge.classList.contains('visible')).toBe(false);
    });

    it('is not affected by the daily limit on the release channel', async () => {
        stubSettingsUpdateChannel('release');
        fetchMock.mockResolvedValue(createFetchResponse(makeUpdateResponse('release')));

        const firstService = new UpdateService();
        firstService.updateNotificationsEnabled = true;
        await firstService.checkForUpdates({ force: true });
        expect(updateBadge.classList.contains('visible')).toBe(true);

        const secondService = new UpdateService();
        secondService.updateNotificationsEnabled = true;
        await secondService.checkForUpdates({ force: true });

        expect(secondService.updateAvailable).toBe(true);
        expect(updateBadge.classList.contains('visible')).toBe(true);
    });
});
