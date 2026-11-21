import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Ensure globals are defined before importing module under test
const ORIGINAL_REQUEST_ANIMATION_FRAME = global.requestAnimationFrame;

class MockIntersectionObserver {
    static instances = [];

    constructor(callback, options) {
        this.callback = callback;
        this.options = options;
        this.observed = new Set();
        MockIntersectionObserver.instances.push(this);
    }

    observe(element) {
        this.observed.add(element);
    }

    unobserve(element) {
        this.observed.delete(element);
    }

    disconnect() {
        this.observed.clear();
    }

    trigger(entries) {
        this.callback(entries, this);
    }
}

function createVideo(src = 'preview.mp4') {
    const preview = document.createElement('div');
    preview.className = 'card-preview';

    const video = document.createElement('video');
    video.dataset.src = src;

    const source = document.createElement('source');
    source.dataset.src = src;
    video.appendChild(source);

    preview.appendChild(video);
    document.body.appendChild(preview);
    return video;
}

function setPlaying(video, isPlaying) {
    Object.defineProperty(video, 'paused', {
        configurable: true,
        get: () => !isPlaying,
    });
}

describe('ModelCard video viewport visibility', () => {
    let configureModelCardVideo;
    let loadSpy;
    let pauseSpy;
    let playSpy;

    beforeEach(async () => {
        vi.useFakeTimers();
        // The lazy observer is a module singleton; a fresh module per test
        // keeps its queue and observer out of the previous test.
        vi.resetModules();

        MockIntersectionObserver.instances = [];
        global.IntersectionObserver = MockIntersectionObserver;
        global.requestAnimationFrame = (callback) => setTimeout(callback, 0);

        ({ configureModelCardVideo } = await import('../../../static/js/components/shared/ModelCard.js'));

        loadSpy = vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {});
        pauseSpy = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
        playSpy = vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(() => Promise.resolve());
    });

    afterEach(() => {
        loadSpy.mockRestore();
        pauseSpy.mockRestore();
        playSpy.mockRestore();
        vi.useRealTimers();
        delete global.IntersectionObserver;
        document.body.innerHTML = '';
        if (ORIGINAL_REQUEST_ANIMATION_FRAME) {
            global.requestAnimationFrame = ORIGINAL_REQUEST_ANIMATION_FRAME;
        } else {
            delete global.requestAnimationFrame;
        }
    });

    async function flushVideoQueue() {
        // processVideoLoadQueue -> setTimeout, source load -> requestAnimationFrame
        // (mapped to setTimeout here), then the paced next batch.
        for (let index = 0; index < 6; index += 1) {
            await vi.advanceTimersByTimeAsync(120);
            await vi.runOnlyPendingTimersAsync();
        }
    }

    async function loadOnScreen(video, autoplayOnHover = false) {
        configureModelCardVideo(video, autoplayOnHover);
        const observer = MockIntersectionObserver.instances.at(-1);
        observer.trigger([{ target: video, isIntersecting: true }]);
        await flushVideoQueue();
        return observer;
    }

    it('pauses a playing preview when it leaves the viewport', async () => {
        const video = createVideo();
        const observer = await loadOnScreen(video);
        expect(video.dataset.loaded).toBe('true');

        setPlaying(video, true);
        pauseSpy.mockClear();

        observer.trigger([{ target: video, isIntersecting: false }]);

        expect(pauseSpy).toHaveBeenCalledTimes(1);
        expect(video.dataset.offscreen).toBe('true');
        expect(video.dataset.resumeOnEnter).toBe('true');
    });

    it('resumes an always-playing preview when it scrolls back into view', async () => {
        const video = createVideo();
        const observer = await loadOnScreen(video, false);

        setPlaying(video, true);
        observer.trigger([{ target: video, isIntersecting: false }]);
        playSpy.mockClear();

        observer.trigger([{ target: video, isIntersecting: true }]);

        expect(playSpy).toHaveBeenCalledTimes(1);
        expect(video.dataset.offscreen).toBeUndefined();
        expect(video.dataset.resumeOnEnter).toBeUndefined();
    });

    it('does not resume a preview the user paused by hand', async () => {
        const video = createVideo();
        const observer = await loadOnScreen(video, false);

        // Paused while visible: the observer must not treat that as its own pause.
        setPlaying(video, false);
        observer.trigger([{ target: video, isIntersecting: false }]);
        expect(video.dataset.resumeOnEnter).toBeUndefined();

        playSpy.mockClear();
        observer.trigger([{ target: video, isIntersecting: true }]);

        expect(playSpy).not.toHaveBeenCalled();
    });

    it('does not autoplay a hover-mode preview on re-entry', async () => {
        const video = createVideo();
        const observer = await loadOnScreen(video, true);
        expect(video.dataset.autoplay).toBeUndefined();

        video.closest('.card-preview').dispatchEvent(new MouseEvent('mouseenter'));
        expect(playSpy).toHaveBeenCalled();

        setPlaying(video, true);
        observer.trigger([{ target: video, isIntersecting: false }]);
        playSpy.mockClear();

        observer.trigger([{ target: video, isIntersecting: true }]);

        expect(playSpy).not.toHaveBeenCalled();
    });

    it('drops a queued load when the card leaves the viewport before loading', async () => {
        const video = createVideo();
        configureModelCardVideo(video, false);

        const observer = MockIntersectionObserver.instances.at(-1);
        observer.trigger([{ target: video, isIntersecting: true }]);
        observer.trigger([{ target: video, isIntersecting: false }]);

        await vi.runOnlyPendingTimersAsync();

        expect(loadSpy).not.toHaveBeenCalled();
        expect(playSpy).not.toHaveBeenCalled();
        expect(video.dataset.loaded).toBe('false');
    });

    it('keeps observing a loaded preview so it can be paused later', async () => {
        const video = createVideo();
        const observer = await loadOnScreen(video);

        expect(observer.observed.has(video)).toBe(true);
    });
});
