import { describe, beforeEach, afterEach, expect, it, vi } from 'vitest';
import { UpdateService } from '../../../static/js/managers/UpdateService.js';

function createFetchResponse(payload) {
    return {
        json: vi.fn().mockResolvedValue(payload)
    };
}

describe('UpdateService passive checks', () => {
    let service;
    let fetchMock;

    beforeEach(() => {
        fetchMock = vi.fn().mockResolvedValue(createFetchResponse({
            success: true,
            current_version: 'v1.0.0',
            latest_version: 'v1.0.0',
            git_info: { short_hash: 'abc123' }
        }));
        global.fetch = fetchMock;

        service = new UpdateService();
        service.updateNotificationsEnabled = false;
        service.lastCheckTime = 0;
        service.nightlyMode = false;
    });

    afterEach(() => {
        delete global.fetch;
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
