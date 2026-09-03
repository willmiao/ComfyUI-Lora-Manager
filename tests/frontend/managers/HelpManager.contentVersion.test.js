import { describe, it, beforeEach, expect, vi } from 'vitest';

const HELP_MANAGER_MODULE = new URL('../../../static/js/managers/HelpManager.js', import.meta.url).pathname;
const VIEWED_KEY = 'lora_manager_help_viewed_content_version';

function setupDom({ versionMarker = null } = {}) {
    const markerAttr = versionMarker ? ` data-help-content-version="${versionMarker}"` : '';
    document.body.innerHTML = `
        <div class="help-toggle" id="helpToggleBtn">
            <span class="update-badge"></span>
        </div>
        <div id="helpModal" class="modal"${markerAttr}>
            <div class="help-tabs">
                <button class="tab-btn" data-tab="getting-started"></button>
                <button class="tab-btn" data-tab="shortcuts"></button>
            </div>
            <div class="tab-pane active" id="getting-started">
                <button id="replayTutorialBtn" class="replay-tutorial-btn"></button>
            </div>
        </div>
    `;
}

describe('HelpManager content-version badge logic', () => {
    let HelpManager;

    beforeEach(async () => {
        ({ HelpManager } = await import(HELP_MANAGER_MODULE));
    });

    function badgeIsVisible() {
        return document.querySelector('#helpToggleBtn .update-badge').classList.contains('visible');
    }

    it('has no new content when the served markup carries no version marker', () => {
        setupDom({ versionMarker: null });
        const manager = new HelpManager();

        expect(manager.hasNewContent()).toBe(false);
        manager.updateHelpBadge();
        expect(badgeIsVisible()).toBe(false);
    });

    it('has new content when a version marker exists and nothing has been viewed yet', () => {
        setupDom({ versionMarker: '2026-09-03' });
        const manager = new HelpManager();

        expect(manager.hasNewContent()).toBe(true);
        manager.updateHelpBadge();
        expect(badgeIsVisible()).toBe(true);
    });

    it('has no new content once the stored viewed version matches the marker', () => {
        setupDom({ versionMarker: '2026-09-03' });
        localStorage.setItem(VIEWED_KEY, '2026-09-03');
        const manager = new HelpManager();

        expect(manager.hasNewContent()).toBe(false);
        manager.updateHelpBadge();
        expect(badgeIsVisible()).toBe(false);
    });

    it('has new content again when the marker moves to a newer version', () => {
        setupDom({ versionMarker: '2026-09-03' });
        localStorage.setItem(VIEWED_KEY, '2025-10-11');
        const manager = new HelpManager();

        expect(manager.hasNewContent()).toBe(true);
    });

    it('markContentAsViewed persists the DOM marker version', () => {
        setupDom({ versionMarker: '2026-09-03' });
        const manager = new HelpManager();

        manager.markContentAsViewed();

        expect(localStorage.getItem(VIEWED_KEY)).toBe('2026-09-03');
        expect(manager.hasNewContent()).toBe(false);
    });

    it('markContentAsViewed is a no-op without a version marker (stale assets)', () => {
        setupDom({ versionMarker: null });
        const manager = new HelpManager();

        manager.markContentAsViewed();

        expect(localStorage.getItem(VIEWED_KEY)).toBeNull();
    });

    it('opening the help modal without new content does not mark it as viewed', () => {
        // Regression test: on a stale (pre-upgrade) page the user may open the
        // help modal before refreshing; that must not suppress the badge for
        // the new content they have not seen yet.
        setupDom({ versionMarker: null });
        window.modalManager = { toggleModal: vi.fn() };
        const manager = new HelpManager();

        manager.openHelpModal();

        expect(localStorage.getItem(VIEWED_KEY)).toBeNull();
        expect(manager.hasNewContent()).toBe(false);
        delete window.modalManager;
    });

    it('opening the help modal with new content marks it as viewed and hides the badge', () => {
        setupDom({ versionMarker: '2026-09-03' });
        window.modalManager = { toggleModal: vi.fn() };
        const manager = new HelpManager();
        manager.updateHelpBadge();
        expect(badgeIsVisible()).toBe(true);

        manager.openHelpModal();

        expect(localStorage.getItem(VIEWED_KEY)).toBe('2026-09-03');
        expect(badgeIsVisible()).toBe(false);
        delete window.modalManager;
    });

    it('adds new-content indicators to the getting-started and shortcuts tabs', () => {
        setupDom({ versionMarker: '2026-09-03' });
        const manager = new HelpManager();

        manager.updateNewContentTabIndicators();

        expect(document.querySelector('.help-tabs .tab-btn[data-tab="getting-started"]').classList.contains('has-new-content')).toBe(true);
        expect(document.querySelector('.help-tabs .tab-btn[data-tab="shortcuts"]').classList.contains('has-new-content')).toBe(true);
    });

    it('flags the Replay Tutorial button and scrolls it into view', () => {
        setupDom({ versionMarker: '2026-09-03' });
        const replayBtn = document.getElementById('replayTutorialBtn');
        replayBtn.scrollIntoView = vi.fn();
        const manager = new HelpManager();

        manager.updateNewContentTabIndicators();

        expect(replayBtn.classList.contains('has-new-content')).toBe(true);
        expect(replayBtn.scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'nearest' });
    });

    it('does not flag the Replay Tutorial button when the content is not new', () => {
        setupDom({ versionMarker: '2026-09-03' });
        localStorage.setItem(VIEWED_KEY, '2026-09-03');
        const manager = new HelpManager();

        manager.updateNewContentTabIndicators();

        expect(document.getElementById('replayTutorialBtn').classList.contains('has-new-content')).toBe(false);
    });

    it('does not scroll the Replay Tutorial button when the getting-started tab is inactive', () => {
        setupDom({ versionMarker: '2026-09-03' });
        document.getElementById('getting-started').classList.remove('active');
        const replayBtn = document.getElementById('replayTutorialBtn');
        replayBtn.scrollIntoView = vi.fn();
        const manager = new HelpManager();

        manager.updateNewContentTabIndicators();

        expect(replayBtn.scrollIntoView).not.toHaveBeenCalled();
    });
});
