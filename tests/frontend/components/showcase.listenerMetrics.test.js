import { describe, it, beforeEach, afterEach, expect } from 'vitest';

const { SHOWCASE_MODULE } = vi.hoisted(() => ({
    SHOWCASE_MODULE: new URL('../../../static/js/components/shared/showcase/ShowcaseView.js', import.meta.url).pathname,
}));

describe('Showcase listener metrics', () => {
    beforeEach(() => {
        document.body.innerHTML = `
            <div id="modelModal">
                <div class="modal-content">
                    <div class="showcase-section">
                        <div class="carousel collapsed">
                            <div class="scroll-indicator"></div>
                        </div>
                        <button class="back-to-top"></button>
                    </div>
                </div>
            </div>
        `;
    });

    afterEach(() => {
        document.body.innerHTML = '';
    });

    it('tracks wheel/mutation/back-to-top listeners and resets after cleanup', async () => {
        const {
            setupShowcaseScroll,
            resetShowcaseListenerMetrics,
            showcaseListenerMetrics,
        } = await import(SHOWCASE_MODULE);

        resetShowcaseListenerMetrics();

        expect(showcaseListenerMetrics.wheelListeners).toBe(0);
        expect(showcaseListenerMetrics.mutationObservers).toBe(0);
        expect(showcaseListenerMetrics.backToTopHandlers).toBe(0);

        const cleanup = setupShowcaseScroll('modelModal');

        expect(showcaseListenerMetrics.wheelListeners).toBe(1);
        expect(showcaseListenerMetrics.mutationObservers).toBe(1);
        expect(showcaseListenerMetrics.backToTopHandlers).toBe(1);

        cleanup();

        expect(showcaseListenerMetrics.wheelListeners).toBe(0);
        expect(showcaseListenerMetrics.mutationObservers).toBe(0);
        expect(showcaseListenerMetrics.backToTopHandlers).toBe(0);
    });

    it('remains stable after repeated setup/cleanup cycles', async () => {
        const {
            setupShowcaseScroll,
            resetShowcaseListenerMetrics,
            showcaseListenerMetrics,
        } = await import(SHOWCASE_MODULE);

        resetShowcaseListenerMetrics();

        const cleanupA = setupShowcaseScroll('modelModal');
        cleanupA();

        const cleanupB = setupShowcaseScroll('modelModal');
        cleanupB();

        expect(showcaseListenerMetrics.wheelListeners).toBe(0);
        expect(showcaseListenerMetrics.mutationObservers).toBe(0);
        expect(showcaseListenerMetrics.backToTopHandlers).toBe(0);
    });
});
