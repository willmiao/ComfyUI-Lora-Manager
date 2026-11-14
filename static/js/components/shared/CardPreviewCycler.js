/**
 * Card preview hover cycler.
 *
 * The single preview image is the memory anchor for a model and never
 * changes implicitly. While the user hovers the bare preview area of a card
 * whose preview is a static image, this module crossfades through the
 * model's example images so multi-concept models can be recognized at a
 * glance. Examples come from two sources: the CivitAI entries in the sidecar
 * (remote CDN URLs) and the example files imported from disk, which carry an
 * empty `url` and are served from `/example_images_static/...` (see
 * exampleMediaResolver). Hovering the card header or footer never starts
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
const DEFAULT_CYCLE_INTERVAL_SECONDS = 2;
// The crossfade must stay short relative to the interval: at a rapid 0.5s
// interval a full-length fade would keep the card permanently mid-transition.
// The fade is capped at 400ms and takes a quarter of the interval below that.
const MAX_FADE_MS = 400;
const FADE_INTERVAL_RATIO = 0.25;

// Per-model example data (resolved frame URLs + anchor index), keyed by
// file_path. Values are promises so repeated hovers share one fetch for the
// session.
const cycleImagesCache = new Map();

function normalizeMediaUrl(url) {
    if (typeof url !== 'string') return '';
    return url.split(/[?#]/)[0];
}

function fetchLocalExampleFiles(sha256) {
    if (!sha256) return Promise.resolve([]);
    const params = new URLSearchParams({ model_hash: sha256 });
    return fetch(`/api/lm/example-image-files?${params}`)
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
 * True when at least one entry has no remote URL, i.e. it is an example
 * imported from disk and needs the local file listing to become usable.
 */
function hasUnresolvedExampleEntries(metadata) {
    const { regularImages, customImages } = getExampleSource(metadata);
    return [...regularImages, ...customImages].some(entry => entry && !entry.url);
}

/**
 * Build the cycling frame list from CivitAI metadata plus local files.
 *
 * Entries imported from disk have no `url`; resolveExampleMedia pairs them
 * with their `custom_<id>` / `image_<index>` file, so those models cycle
 * instead of being silently dropped. Remote URLs win when present because
 * they are already card-sized (`getThumbnailUrl`) and browser-cached.
 *
 * @returns {{urls: string[], anchorIndex: number}}
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

    const urls = [];
    for (const { entry, index } of candidates) {
        if (!entry) continue;
        if (showOnlySFW && (entry.nsfwLevel ?? 0) >= NSFW_LEVELS.R) continue;

        const { url: resolvedUrl, isVideo } = resolveExampleMedia(entry, index, exampleFiles);
        if (isVideo || !resolvedUrl) continue;

        // Card-sized frames: width=450 keeps hover loads fast for CivitAI
        // URLs; local example paths pass through unchanged.
        const url = entry.url ? getThumbnailUrl(resolvedUrl) : resolvedUrl;
        if (!urls.includes(url)) {
            urls.push(url);
        }
    }

    const previewKey = normalizeMediaUrl(previewUrl);
    let anchorIndex = previewKey
        ? urls.findIndex(url => normalizeMediaUrl(url) === previewKey)
        : -1;
    // CivitAI models keep the historical assumption that the first example
    // doubles as the card preview, even when the URL forms differ slightly
    // after thumbnail rewriting.
    if (anchorIndex < 0 && regularImages.length > 0) {
        anchorIndex = 0;
    }

    return { urls, anchorIndex };
}

function getCycleImages(model) {
    const filePath = model.file_path;
    if (!cycleImagesCache.has(filePath)) {
        const request = getModelApiClient()
            .fetchModelMetadata(filePath)
            .then(async metadata => {
                // Only CivitAI-less (or disk-imported) example sets need the
                // local listing; a fully remote set never touches the disk.
                const exampleFiles = hasUnresolvedExampleEntries(metadata)
                    ? await fetchLocalExampleFiles(model.sha256)
                    : [];
                return extractCycleImages(metadata, exampleFiles, model.preview_url);
            })
            .catch(() => {
                // Allow a later hover to retry after a transient failure.
                cycleImagesCache.delete(filePath);
                return { urls: [], anchorIndex: -1 };
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
    let cycleTimer = null;
    let buffers = null;
    let imageUrls = [];
    let pendingImages = null;
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

    // Data loading starts on first hover, not when the mode activates: the
    // delay only gates the visual mode switch, and the first frame is
    // preloaded during it so it can fade in instantly on activation.
    const startPrefetch = () => {
        if (pendingImages) return;
        pendingImages = getCycleImages(model).then(({ urls, anchorIndex }) => {
            if (urls.length > 1) {
                ensurePreloaded(urls[(anchorIndex + 1) % urls.length]);
            }
            return { urls, anchorIndex };
        });
    };

    const activate = async () => {
        hoverDelayTimer = null;
        const cycleData = await pendingImages;
        const urls = cycleData?.urls || [];
        // A single example is the cover image itself — nothing new to show.
        // The cycleTimer guard catches a second activation that was re-armed
        // while this one was still awaiting its image list.
        if (!hovered || pointerInChrome || !card.isConnected || urls.length < 2 || cycleTimer) {
            return;
        }
        imageUrls = urls;
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

        if (!hovered) {
            hovered = true;
            startPrefetch();
        }
        if (cycleTimer) return;

        // The card chrome (header/footer with action icons and tooltips) is
        // a child of .card-preview; only the bare preview area arms the
        // activation timer, and moving into the chrome disarms it again.
        pointerInChrome = Boolean(event.target.closest?.('.card-header, .card-footer'));
        if (pointerInChrome) {
            if (hoverDelayTimer) {
                clearTimeout(hoverDelayTimer);
                hoverDelayTimer = null;
            }
        } else if (!hoverDelayTimer) {
            hoverDelayTimer = setTimeout(activate, CYCLE_MODE_DELAY_MS);
        }
    };

    const onMouseLeave = () => {
        hovered = false;
        cleanup();
    };

    cardPreview.addEventListener('mouseover', onMouseOver);
    cardPreview.addEventListener('mouseleave', onMouseLeave);
}

/** Test hook: drop cached image lists between tests. */
export function resetCardPreviewCycleCache() {
    cycleImagesCache.clear();
}
