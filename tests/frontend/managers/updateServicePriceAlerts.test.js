import { describe, beforeEach, afterEach, expect, it, vi } from 'vitest';
import { UpdateService } from '../../../static/js/managers/UpdateService.js';
import { state } from '../../../static/js/state/index.js';
import { modalManager } from '../../../static/js/managers/ModalManager.js';

/**
 * The price alerts panel is rendered into the notification bell modal, so the
 * tests build the same element ids the template provides and drive the service
 * directly.
 */
function buildPanelDom() {
    document.body.innerHTML = `
        <div id="updateModal">
            <button data-notification-tab="updates"></button>
            <button data-notification-tab="priceAlerts"></button>
            <div data-notification-panel="updates"></div>
            <div data-notification-panel="priceAlerts">
                <div id="priceAlertsDisabled" class="hidden"></div>
                <button id="priceAlertsSettingsBtn"></button>
                <button data-price-alert-segment="below_threshold"></button>
                <button data-price-alert-segment="became_free"></button>
                <span id="priceAlertsThreshold"></span>
                <p id="priceAlertsStale" class="hidden"></p>
                <p id="priceAlertsEmpty"></p>
                <ul id="priceAlertsList"></ul>
            </div>
            <span id="updatesTabBadge"></span>
            <span id="bannerTabBadge"></span>
            <span id="priceAlertsTabBadge"></span>
        </div>
    `;
}

function alertPayload(alerts, overrides = {}) {
    return {
        success: true,
        enabled: true,
        thresholdBuzz: 500,
        newestCheckedAt: 1791039694.5,
        alerts,
        ...overrides,
    };
}

const BELOW_THRESHOLD_ALERT = {
    modelId: 2981320,
    modelType: 'checkpoint',
    modelName: 'Glorious Art',
    versionId: 3379626,
    versionName: 'Alpha',
    kind: 'below_threshold',
    priceBuzz: 250,
    listPriceBuzz: 500,
    acceptsBlueBuzz: true,
    priceAlertSince: 1791000000,
    isInLibrary: false,
    filePath: null,
    civitaiUrl: 'https://civitai.com/models/2981320?modelVersionId=3379626',
};

const BECAME_FREE_ALERT = {
    modelId: 1802980,
    modelType: 'lora',
    modelName: 'Eira Kishida',
    versionId: 3262917,
    versionName: 'v3',
    kind: 'became_free',
    priceBuzz: null,
    priceAlertSince: null,
    gateLapsedAt: '2026-09-28T00:00:00.000Z',
    isInLibrary: true,
    filePath: '/models/loras/eira.safetensors',
    civitaiUrl: 'https://civitai.com/models/1802980?modelVersionId=3262917',
};

function createFetchResponse(payload, ok = true) {
    return { json: vi.fn().mockResolvedValue(payload), ok, statusText: '' };
}

describe('UpdateService price alerts panel', () => {
    let service;

    beforeEach(() => {
        buildPanelDom();
        localStorage.clear();
        state.global = state.global || {};
        state.global.settings = state.global.settings || {};
        service = new UpdateService();
        service.setupNotificationCenter();
    });

    afterEach(() => {
        delete global.fetch;
        document.body.innerHTML = '';
        localStorage.clear();
    });

    it('loads the global endpoint and renders a below-threshold row', async () => {
        global.fetch = vi
            .fn()
            .mockResolvedValue(createFetchResponse(alertPayload([BELOW_THRESHOLD_ALERT])));

        await service.loadPriceAlerts({ force: true });

        expect(global.fetch).toHaveBeenCalledTimes(1);
        expect(String(global.fetch.mock.calls[0][0])).toContain('/api/lm/price-alerts');

        const items = document.querySelectorAll('#priceAlertsList .price-alert-item');
        expect(items).toHaveLength(1);
        expect(items[0].textContent).toContain('Glorious Art');
        expect(items[0].textContent).toContain('250 Buzz');
        // The stored list price is shown struck through.
        expect(items[0].querySelector('.price-alert-was').textContent).toBe('500 Buzz');
        expect(items[0].textContent).toContain('Blue Buzz OK');
        expect(items[0].textContent).toContain('Not in library');
        // No local file -> no "Open" action, only CivitAI.
        expect(items[0].querySelector('[data-price-alert-action="open"]')).toBeNull();
        expect(
            items[0].querySelector('[data-price-alert-action="civitai"]')
        ).not.toBeNull();
        expect(document.getElementById('priceAlertsDisabled').classList.contains('hidden')).toBe(true);
        expect(document.getElementById('priceAlertsEmpty').classList.contains('hidden')).toBe(true);
    });

    it('separates became-free alerts into their own segment', async () => {
        global.fetch = vi
            .fn()
            .mockResolvedValue(
                createFetchResponse(alertPayload([BELOW_THRESHOLD_ALERT, BECAME_FREE_ALERT]))
            );

        await service.loadPriceAlerts({ force: true });

        // Below-threshold is the default segment.
        expect(document.querySelectorAll('#priceAlertsList .price-alert-item')).toHaveLength(1);

        service.priceAlertSegment = 'became_free';
        service.renderPriceAlerts();

        const items = document.querySelectorAll('#priceAlertsList .price-alert-item');
        expect(items).toHaveLength(1);
        expect(items[0].textContent).toContain('Free now');
        expect(items[0].textContent).toContain('In library');
        // In-library row offers both actions.
        expect(items[0].querySelector('[data-price-alert-action="open"]')).not.toBeNull();
        expect(items[0].querySelector('[data-price-alert-action="civitai"]')).not.toBeNull();
    });

    it('counts unread alerts and clears the count once viewed', async () => {
        global.fetch = vi
            .fn()
            .mockResolvedValue(
                createFetchResponse(alertPayload([BELOW_THRESHOLD_ALERT, BECAME_FREE_ALERT]))
            );

        await service.loadPriceAlerts({ force: true });

        expect(service.getUnreadPriceAlertCount()).toBe(2);
        const badge = document.getElementById('priceAlertsTabBadge');
        expect(badge.classList.contains('visible')).toBe(true);
        expect(badge.textContent).toBe('2');

        service.markPriceAlertsViewed();

        expect(service.getUnreadPriceAlertCount()).toBe(0);
        expect(badge.classList.contains('visible')).toBe(false);

        // A later alert is unread again.
        service.priceAlerts = [
            { ...BELOW_THRESHOLD_ALERT, priceAlertSince: 1791000000 + 1000 },
        ];
        expect(service.refreshUnreadPriceAlertCount()).toBe(1);
    });

    it('explains itself while price tracking is off', async () => {
        global.fetch = vi
            .fn()
            .mockResolvedValue(
                createFetchResponse(
                    alertPayload([BECAME_FREE_ALERT], { enabled: false, thresholdBuzz: 0 })
                )
            );

        await service.loadPriceAlerts({ force: true });

        expect(
            document.getElementById('priceAlertsDisabled').classList.contains('hidden')
        ).toBe(false);
        expect(document.getElementById('priceAlertsThreshold').textContent).toBe('');
    });

    it('shows the empty state when the segment has no matches', async () => {
        global.fetch = vi
            .fn()
            .mockResolvedValue(createFetchResponse(alertPayload([BELOW_THRESHOLD_ALERT])));

        await service.loadPriceAlerts({ force: true });
        service.priceAlertSegment = 'became_free';
        service.renderPriceAlerts();

        const empty = document.getElementById('priceAlertsEmpty');
        expect(empty.classList.contains('hidden')).toBe(false);
        expect(document.querySelectorAll('#priceAlertsList .price-alert-item')).toHaveLength(0);
    });

    it('reports how many gated versions have no readable price', async () => {
        global.fetch = vi.fn().mockResolvedValue(
            createFetchResponse(
                alertPayload([BELOW_THRESHOLD_ALERT], { unavailableCount: 3 })
            )
        );

        await service.loadPriceAlerts({ force: true });

        expect(service.priceAlertsUnavailableCount).toBe(3);
        const note = document.getElementById('priceAlertsStale');
        expect(note.classList.contains('hidden')).toBe(false);
        expect(note.textContent).toContain('3 paid version(s) have no readable price');
    });

    it('keeps the last known list when the request fails', async () => {
        global.fetch = vi
            .fn()
            .mockResolvedValueOnce(createFetchResponse(alertPayload([BELOW_THRESHOLD_ALERT])))
            .mockResolvedValueOnce(createFetchResponse({ success: false, error: 'boom' }, false));

        await service.loadPriceAlerts({ force: true });
        await service.loadPriceAlerts({ force: true });

        expect(document.querySelectorAll('#priceAlertsList .price-alert-item')).toHaveLength(1);
        const stale = document.getElementById('priceAlertsStale');
        expect(stale.classList.contains('hidden')).toBe(false);
    });

    it('switches to the tab without closing an already-open bell', () => {
        global.fetch = vi.fn().mockResolvedValue(createFetchResponse(alertPayload([])));
        const toggleSpy = vi.spyOn(service, 'toggleUpdateModal');
        const getModalSpy = vi
            .spyOn(modalManager, 'getModal')
            .mockReturnValue({ isOpen: true });

        service.openPriceAlertsTab();

        expect(getModalSpy).toHaveBeenCalledWith('updateModal');
        // toggleUpdateModal() would have *closed* the open bell.
        expect(toggleSpy).not.toHaveBeenCalled();
        expect(service.activeNotificationTab).toBe('priceAlerts');

        getModalSpy.mockRestore();
        toggleSpy.mockRestore();
    });

    it('opens the bell when it is closed', () => {
        global.fetch = vi.fn().mockResolvedValue(createFetchResponse(alertPayload([])));
        const toggleSpy = vi
            .spyOn(service, 'toggleUpdateModal')
            .mockImplementation(() => {});
        const getModalSpy = vi
            .spyOn(modalManager, 'getModal')
            .mockReturnValue({ isOpen: false });

        service.openPriceAlertsTab();

        expect(toggleSpy).toHaveBeenCalled();
        expect(service.activeNotificationTab).toBe('priceAlerts');

        getModalSpy.mockRestore();
        toggleSpy.mockRestore();
    });
});
