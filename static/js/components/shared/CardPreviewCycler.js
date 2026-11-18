/**
 * Card preview hover cycler.
 *
 * The single preview image is the memory anchor for a model and never
 * changes implicitly. While the user hovers the bare preview area of a card
 * whose preview is a static image, this module crossfades through the
 * model's example images so multi-concept models can be recognized at a
 * glance. Examples come from two sources: the example files under the
 * example-images root (served from `/example_images_static/...`) and the
 * CivitAI CDN URLs in the sidecar. A downloaded local copy wins over its
 * remote URL (see exampleMediaResolver): the cycle interval can be shorter
 * than a cold CDN fetch, so the first pass would otherwise stall on every
 * frame. The remote URL stays as the per-frame fallback for entries that were
 * never downloaded, and for local files that have gone missing (deleted
 * folder, unmounted drive). Hovering the card header or footer never starts
 * cycling, so action buttons and tooltips stay undisturbed. Leaving the card
 * restores the anchor preview immediately.
 *
 * Video previews are intentionally excluded: their hover slot already
 * plays the video itself (see configureModelCardVideo).
 */

import { state } from '../../state/index.js';
import { getModelApiClient } from '../../api/modelApiFactory.js';
import { NSFW_LEVELS } from '../../utils/constants.js';
import { getThumbnailUrl } from '../../utils/civitaiUtils.js';
import { resolveExampleMedia } from './showcase/exampleMediaResolver.js';

// How long the pointer must rest on the bare preview area before cycling
// mode activates and the card chrome fades out. The card header and footer
// live inside .card-preview, but hovering them disarms the timer, so chrome
// interactions (action icons, tooltips) are protected structurally and the
// delay can stay short. The first example frame is preloaded while the
// timer runs, so it swaps in the moment the mode activates.
const CYCLE_MODE_DELAY_MS = 800;
// Short intent window before the network requests start. A pointer sweeping
// across the grid usually leaves a card well inside this window, so drive-by
// hovers cost no requests; a deliberate hover still warms the first frame
// long before the 800ms activation timer fires.
const PREFETCH_DELAY_MS = 200;
const DEFAULT_CYCLE_INTERVAL_SECONDS = 2;
// The crossfade must stay short relative to the interval: at a rapid 0.5s
// interval a full-length fade would keep the card permanently mid-transition.
// The fade is capped at 400ms and takes a quarter of the interval below that.
const MAX_FADE_MS = 400;
const FADE_INTERVAL_RATIO = 0.25;

// Per-model example data (resolved frames + anchor index), keyed by
// file_path. Values are promises so repeated hovers share one fetch pair for
// the session.
const cycleImagesCache = new Map();

function normalizeMediaUrl(url) {
    if (typeof url !== 'string') return '';
    return url.split(/[?#]/)[0];
}

function fetchLocalExampleFiles(sha256) {
    if (!sha256) return Promise.resolve([]);
    const params = new URLSearchParams({ model_hash: sha256 });
    return fetch(`/api/lm/example-image-files?${params}`)
        // A model without an example folder answers 200 with an empty
        // `files` list; other failures degrade to no local examples too.
        .then(response => (response.ok ? response.json() : null))
        .then(data => (data?.success ? data.files || [] : []))
        .catch(() => []);
}

// fetchModelMetadata returns the civitai section itself (see ModelModal), not
// a wrapper with a `civitai` key.
function getExampleSource(metadata) {
    const source = metadata?.images || metadata?.customImages ? metadata : metadata?.civitai || {};
    return {
        regularImages: Array.isArray(source.images) ? source.images : [],
        customImages: Array.isArray(source.customImages) ? source.customImages : [],
    };
}

/**
 * Build the cycling frame list from CivitAI metadata plus local files.
 *
 * The downloaded local copy is preferred over the entry's remote URL: the
 * cycle can run faster than a cold CDN fetch, so a remote-first list makes the
 * first pass stall frame by frame. `exampleFiles` is fetched for every model
 * (see getCycleImages), which means the pairing works the same for entries
 * imported from disk (empty `url`) and for entries whose images were
 * downloaded after the metadata was cached.
 *
 * @returns {{frames: Array<{url: string, fallback: string}>, anchorIndex: number}}
 *   `url` is the frame to show; `fallback` is the remote URL to use when a
 *   local frame fails to load, and is empty when there is no remote source.
 *   `anchorIndex` is the frame matching the fixed preview, or -1 when the
 *   preview is not part of the rotation (custom-only example sets).
 */
function extractCycleImages(metadata, exampleFiles, previewUrl) {
    const { regularImages, customImages } = getExampleSource(metadata);
    const showOnlySFW = state.settings.show_only_sfw;

    const candidates = [
        ...regularImages.map((entry, index) => ({ entry, index })),
        ...customImages.map(entry => ({ entry, index: 0 })),
    ];

    const frames = [];
    for (const { entry, index } of candidates) {
        if (!entry) continue;
        if (showOnlySFW && (entry.nsfwLevel ?? 0) >= NSFW_LEVELS.R) continue;

        const { localFile, url, isVideo } = resolveExampleMedia(entry, index, exampleFiles);
        if (isVideo || !url) continue;

        // Local files already have the size the download produced; remote
        // frames are rewritten to the card-sized variant (width=450 keeps the
        // hover fetch fast).
        const frameUrl = localFile ? url : (entry.url ? getThumbnailUrl(url) : url);
        if (frames.some(frame => frame.url === frameUrl)) continue;

        frames.push({
            url: frameUrl,
            fallback: localFile && entry.url ? getThumbnailUrl(entry.url) : '',
        });
    }

    const previewKey = normalizeMediaUrl(previewUrl);
    let anchorIndex = previewKey
        ? frames.findIndex(frame => normalizeMediaUrl(frame.url) === previewKey)
        : -1;
    // CivitAI models keep the historical assumption that the first example
    // doubles as the card preview, even when the URL forms differ slightly
    // after thumbnail rewriting.
    if (anchorIndex < 0 && regularImages.length > 0) {
        anchorIndex = 0;
    }

    return { frames, anchorIndex };
}

function getCycleImages(model) {
    const filePath = model.file_path;
    if (!cycleImagesCache.has(filePath)) {
        // The two requests are independent, so they go out together: the local
        // listing is what tells a downloaded model apart from a remote-only
        // one, and it must not extend the wait before the first frame.
        const request = Promise.all([
            getModelApiClient().fetchModelMetadata(filePath),
            fetchLocalExampleFiles(model.sha256),
        ])
            .then(([metadata, exampleFiles]) =>
                extractCycleImages(metadata, exampleFiles, model.preview_url))
            .catch(() => {
                // Allow a later hover to retry after a transient failure.
                cycleImagesCache.delete(filePath);
                return { frames: [], anchorIndex: -1 };
            });
        cycleImagesCache.set(filePath, request);
    }
    return cycleImagesCache.get(filePath);
}

// Keep in sync with the range input bounds in
// templates/components/modals/settings/interface.html: stale settings.json
// values (from the old 8s option or manual edits) are clamped so the runtime
// always matches what the slider can express.
const MIN_CYCLE_INTERVAL_SECONDS = 0.5;
const MAX_CYCLE_INTERVAL_SECONDS = 3;

function getCycleIntervalMs() {
    const seconds = Number(state.global?.settings?.card_preview_cycle_interval);
    const valid = Number.isFinite(seconds) && seconds > 0 ? seconds : DEFAULT_CYCLE_INTERVAL_SECONDS;
    const clamped = Math.min(MAX_CYCLE_INTERVAL_SECONDS, Math.max(MIN_CYCLE_INTERVAL_SECONDS, valid));
    return clamped * 1000;
}

function getFadeDurationMs() {
    return Math.min(MAX_FADE_MS, Math.round(getCycleIntervalMs() * FADE_INTERVAL_RATIO));
}

function prefersReducedMotion() {
    return Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
}

function preloadImage(url) {
    return new Promise(resolve => {
        const probe = new Image();
        probe.onload = () => resolve(url);
        probe.onerror = () => resolve(null);
        probe.src = url;
    });
}

/**
 * Attach hover cycling to a rendered card. Call only for image previews;
 * video previews keep their autoplay-on-hover behavior.
 *
 * @param {HTMLElement} card - The .model-card element
 * @param {Object} model - The model data backing the card
 */
export function attachCardPreviewCycler(card, model) {
    const cardPreview = card.querySelector('.card-preview');
    if (!cardPreview) return;

    let hovered = false;
    let pointerInChrome = false;
    let hoverDelayTimer = null;
    let prefetchTimer = null;
    let cycleTimer = null;
    let buffers = null;
    let frames = [];
    let pendingImages = null;
    let currentIndex = -1;
    let activeBuffer = 0;
    let swapping = false;
    // Resolved preloads persist for the card's lifetime: a re-hover after a
    // drive-by gets an instant first frame, and every shown frame warms the
    // next one so interval ticks never wait on the network. Keyed by the
    // frame's primary URL; the promise resolves to the URL that actually
    // loaded, i.e. the remote fallback when a local file is gone.
    const preloads = new Map();

    const ensurePreloaded = (frame) => {
        if (!preloads.has(frame.url)) {
            preloads.set(frame.url, preloadImage(frame.url).then(
                loaded => loaded || (frame.fallback ? preloadImage(frame.fallback) : null)
            ));
        }
        return preloads.get(frame.url);
    };

    const createBuffers = () => {
        const fadeMs = getFadeDurationMs();
        buffers = [0, 1].map(() => {
            const img = document.createElement('img');
            img.className = 'card-preview-cycle-img';
            img.draggable = false;
            img.alt = '';
            // Overrides the stylesheet default; keeps the crossfade short
            // enough for rapid cycle intervals.
            img.style.transitionDuration = `${fadeMs}ms`;
            cardPreview.appendChild(img);
            return img;
        });
    };

    const removeBuffers = () => {
        if (!buffers) return;
        const stale = buffers;
        buffers = null;
        // Fade back to the anchor preview before dropping the overlays.
        stale.forEach(img => img.classList.remove('visible'));
        setTimeout(() => stale.forEach(img => img.remove()), getFadeDurationMs() + 50);
    };

    const cancelPrefetch = () => {
        if (!prefetchTimer) return;
        clearTimeout(prefetchTimer);
        prefetchTimer = null;
    };

    const cleanup = () => {
        if (hoverDelayTimer) {
            clearTimeout(hoverDelayTimer);
            hoverDelayTimer = null;
        }
        cancelPrefetch();
        if (cycleTimer) {
            clearInterval(cycleTimer);
            cycleTimer = null;
        }
        currentIndex = -1;
        swapping = false;
        pointerInChrome = false;
        card.classList.remove('cycling');
        removeBuffers();
    };

    const swapToNext = async () => {
        if (!card.isConnected) {
            hovered = false;
            cleanup();
            return;
        }
        if (!hovered || swapping || document.hidden || frames.length === 0) {
            return;
        }

        swapping = true;
        const nextIndex = (currentIndex + 1) % frames.length;
        const url = await ensurePreloaded(frames[nextIndex]);
        swapping = false;

        // Frames with neither a loadable local file nor a remote fallback are
        // skipped without stalling the cycle.
        currentIndex = nextIndex;
        if (!url || !hovered || !buffers) {
            return;
        }

        const incoming = buffers[1 - activeBuffer];
        const outgoing = buffers[activeBuffer];
        incoming.src = url;
        incoming.classList.add('visible');
        outgoing.classList.remove('visible');
        activeBuffer = 1 - activeBuffer;

        // Warm the following frame while this one is on screen.
        ensurePreloaded(frames[(currentIndex + 1) % frames.length]);
    };

    // Data loading starts after a short intent window, not when the mode
    // activates: the activation delay only gates the visual mode switch, and
    // the first frame is preloaded during it so it can fade in instantly.
    // Chrome hovers never call this, so action buttons and tooltips cannot
    // trigger network work by themselves.
    const startPrefetch = () => {
        if (pendingImages) return;
        pendingImages = getCycleImages(model).then(({ frames: frameList, anchorIndex }) => {
            if (frameList.length > 1) {
                ensurePreloaded(frameList[(anchorIndex + 1) % frameList.length]);
            }
            return { frames: frameList, anchorIndex };
        });
    };

    const armPrefetch = () => {
        if (pendingImages || prefetchTimer) return;
        prefetchTimer = setTimeout(() => {
            prefetchTimer = null;
            startPrefetch();
        }, PREFETCH_DELAY_MS);
    };

    const activate = async () => {
        hoverDelayTimer = null;
        // The intent window normally started the fetch long ago; this covers
        // a pending timer that was re-armed right before activation.
        cancelPrefetch();
        startPrefetch();
        const cycleData = await pendingImages;
        const frameList = cycleData?.frames || [];
        // A single example is the cover image itself — nothing new to show.
        // The cycleTimer guard catches a second activation that was re-armed
        // while this one was still awaiting its frame list.
        if (!hovered || pointerInChrome || !card.isConnected || frameList.length < 2 || cycleTimer) {
            return;
        }
        frames = frameList;
        // Start from the fixed preview when it is part of the rotation, so the
        // first swap shows the next example. Custom-only example sets have no
        // anchor in the list: start at -1 so frame 0 shows immediately.
        currentIndex = cycleData.anchorIndex;
        card.classList.add('cycling');
        createBuffers();
        swapToNext();
        cycleTimer = setInterval(swapToNext, getCycleIntervalMs());
    };

    const onMouseOver = (event) => {
        if (!state.global?.settings?.card_preview_cycle) return;
        if (prefersReducedMotion()) return;
        // NSFW-blurred cards stay static until the user explicitly unblurs.
        if (cardPreview.classList.contains('blurred')) return;

        hovered = true;
        if (cycleTimer) return;

        // The card chrome (header/footer with action icons and tooltips) is
        // a child of .card-preview; only the bare preview area counts as
        // hover intent. Entering the chrome also disarms the activation timer
        // and cancels a pending prefetch, so drive-by interactions with the
        // action buttons never reach the network.
        pointerInChrome = Boolean(event.target.closest?.('.card-header, .card-footer'));
        if (pointerInChrome) {
            cancelPrefetch();
            if (hoverDelayTimer) {
                clearTimeout(hoverDelayTimer);
                hoverDelayTimer = null;
            }
        } else {
            armPrefetch();
            if (!hoverDelayTimer) {
                hoverDelayTimer = setTimeout(activate, CYCLE_MODE_DELAY_MS);
            }
        }
    };

    const onMouseLeave = () => {
        hovered = false;
        cleanup();
    };

    cardPreview.addEventListener('mouseover', onMouseOver);
    cardPreview.addEventListener('mouseleave', onMouseLeave);
}

/** Test hook: drop cached frame lists between tests. */
export function resetCardPreviewCycleCache() {
    cycleImagesCache.clear();
}
