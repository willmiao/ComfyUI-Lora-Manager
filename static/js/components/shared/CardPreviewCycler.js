/**
 * Card preview hover cycler.
 *
 * The single preview image is the memory anchor for a model and never
 * changes implicitly. While the user hovers a card whose preview is a
 * static image, this module crossfades through the model's example images
 * (CivitAI images + custom images, videos excluded) so multi-concept
 * models can be recognized at a glance. Leaving the card restores the
 * anchor preview immediately.
 *
 * Video previews are intentionally excluded: their hover slot already
 * plays the video itself (see configureModelCardVideo).
 */

import { state } from '../../state/index.js';
import { getModelApiClient } from '../../api/modelApiFactory.js';
import { NSFW_LEVELS } from '../../utils/constants.js';
import { isVideoPreviewUrl } from '../../utils/mediaTypes.js';
import { getThumbnailUrl } from '../../utils/civitaiUtils.js';

// How long the pointer must rest on a card before cycling mode activates and
// the card chrome fades out. Generous on purpose: ordinary hover interactions
// (action icons, tooltips) must stay usable, and the anchor preview has
// already been seen by then — so the first example frame swaps in the moment
// the mode activates (it was preloaded during the delay).
const CYCLE_MODE_DELAY_MS = 1500;
const DEFAULT_CYCLE_INTERVAL_SECONDS = 3;

// Per-model example image URL lists, keyed by file_path. Values are promises
// so repeated hovers share one fetch for the session.
const cycleImagesCache = new Map();

function isVideoEntry(entry) {
    if (typeof entry?.type === 'string' && entry.type.toLowerCase() === 'video') {
        return true;
    }
    return isVideoPreviewUrl(entry?.url || '');
}

function extractCycleImages(metadata) {
    // fetchModelMetadata returns the civitai section itself (see ModelModal),
    // not a wrapper with a `civitai` key.
    const source = metadata?.images || metadata?.customImages ? metadata : metadata?.civitai || {};
    const entries = [...(source.images || []), ...(source.customImages || [])];
    const showOnlySFW = state.settings.show_only_sfw;

    return entries
        .filter(entry => entry?.url && !isVideoEntry(entry))
        .filter(entry => !showOnlySFW || (entry.nsfwLevel ?? 0) < NSFW_LEVELS.R)
        // Card-sized frames: width=450 keeps hover loads fast; non-CivitAI
        // URLs (custom images) pass through unchanged.
        .map(entry => getThumbnailUrl(entry.url));
}

function getCycleImages(model) {
    const filePath = model.file_path;
    if (!cycleImagesCache.has(filePath)) {
        const request = getModelApiClient()
            .fetchModelMetadata(filePath)
            .then(metadata => extractCycleImages(metadata))
            .catch(() => {
                // Allow a later hover to retry after a transient failure.
                cycleImagesCache.delete(filePath);
                return [];
            });
        cycleImagesCache.set(filePath, request);
    }
    return cycleImagesCache.get(filePath);
}

function getCycleIntervalMs() {
    const seconds = Number(state.global?.settings?.card_preview_cycle_interval);
    const valid = Number.isFinite(seconds) && seconds > 0 ? seconds : DEFAULT_CYCLE_INTERVAL_SECONDS;
    return valid * 1000;
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
    let hoverDelayTimer = null;
    let cycleTimer = null;
    let buffers = null;
    let imageUrls = [];
    let currentIndex = -1;
    let activeBuffer = 0;
    let swapping = false;
    // Resolved preloads persist for the card's lifetime: a re-hover after a
    // drive-by gets an instant first frame, and every shown frame warms the
    // next one so interval ticks never wait on the network.
    const preloads = new Map();

    const ensurePreloaded = (url) => {
        if (!preloads.has(url)) {
            preloads.set(url, preloadImage(url));
        }
        return preloads.get(url);
    };

    const createBuffers = () => {
        buffers = [0, 1].map(() => {
            const img = document.createElement('img');
            img.className = 'card-preview-cycle-img';
            img.draggable = false;
            img.alt = '';
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
        setTimeout(() => stale.forEach(img => img.remove()), 450);
    };

    const cleanup = () => {
        if (hoverDelayTimer) {
            clearTimeout(hoverDelayTimer);
            hoverDelayTimer = null;
        }
        if (cycleTimer) {
            clearInterval(cycleTimer);
            cycleTimer = null;
        }
        currentIndex = -1;
        swapping = false;
        card.classList.remove('cycling');
        removeBuffers();
    };

    const swapToNext = async () => {
        if (!card.isConnected) {
            hovered = false;
            cleanup();
            return;
        }
        if (!hovered || swapping || document.hidden || imageUrls.length === 0) {
            return;
        }

        swapping = true;
        const nextIndex = (currentIndex + 1) % imageUrls.length;
        const url = await ensurePreloaded(imageUrls[nextIndex]);
        swapping = false;

        // Broken image URLs are skipped without stalling the cycle.
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
        ensurePreloaded(imageUrls[(currentIndex + 1) % imageUrls.length]);
    };

    const onMouseEnter = () => {
        if (!state.global?.settings?.card_preview_cycle) return;
        if (prefersReducedMotion()) return;
        // NSFW-blurred cards stay static until the user explicitly unblurs.
        if (cardPreview.classList.contains('blurred')) return;

        hovered = true;
        // Data loading starts on hover, not when the mode activates: the
        // delay only gates the visual mode switch, and the first frame is
        // preloaded during it so it can fade in instantly on activation.
        const pendingImages = getCycleImages(model).then(urls => {
            // The first CivitAI example doubles as the cover/preview, so the
            // first frame shown is index 1 (the cover rejoins the rotation
            // when the cycle wraps).
            if (urls.length > 1) {
                ensurePreloaded(urls[1]);
            }
            return urls;
        });
        hoverDelayTimer = setTimeout(async () => {
            hoverDelayTimer = null;
            imageUrls = await pendingImages;
            // A single example is the cover image itself — nothing new to show.
            if (!hovered || !card.isConnected || imageUrls.length < 2) {
                return;
            }
            // Index 0 is the anchor's double; treat it as the current frame so
            // the first swap lands on index 1.
            currentIndex = 0;
            card.classList.add('cycling');
            createBuffers();
            swapToNext();
            cycleTimer = setInterval(swapToNext, getCycleIntervalMs());
        }, CYCLE_MODE_DELAY_MS);
    };

    const onMouseLeave = () => {
        hovered = false;
        cleanup();
    };

    cardPreview.addEventListener('mouseenter', onMouseEnter);
    cardPreview.addEventListener('mouseleave', onMouseLeave);
}

/** Test hook: drop cached image lists between tests. */
export function resetCardPreviewCycleCache() {
    cycleImagesCache.clear();
}
