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
