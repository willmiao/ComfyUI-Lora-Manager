/**
 * ShowcaseView.js
 * Shared showcase component for displaying examples in model modals (Lora/Checkpoint)
 *
 * The showcase starts collapsed as a slim indicator bar ("Show N examples"),
 * so opening the modal never triggers remote image fetches. Expanding reveals
 * a gallery: a single main viewer with prev/next controls, a horizontal
 * thumbnail strip for overview/random access, and an always-visible import
 * entry — no scrolling through a vertical stack of full-width examples.
 */
import { showToast } from '../../../utils/uiHelpers.js';
import { state } from '../../../state/index.js';
import { modalManager } from '../../../managers/ModalManager.js';
import { translate } from '../../../utils/i18nHelpers.js';
import { NSFW_LEVELS, getMatureBlurThreshold } from '../../../utils/constants.js';
import {
    initLazyLoading,
    initNsfwBlurHandlers,
    initMetadataPanelHandlers,
    initMediaControlHandlers,
    positionAllMediaControls
} from './MediaUtils.js';
import { generateMetadataPanel } from './MetadataPanel.js';
import { generateImageWrapper, generateVideoWrapper } from './MediaRenderers.js';
import { getShowcaseUrl, getGalleryThumbnailUrl } from '../../../utils/civitaiUtils.js';
import { openMediaViewer } from '../MediaViewer.js';
import { escapeAttribute } from '../utils.js';

/**
 * Current gallery state. The model modal is a singleton, so a single module-level
 * state object is sufficient; it is replaced on every render.
 *
 * The gallery starts collapsed: only the indicator bar renders, so remote
 * example images are never fetched until the user explicitly expands the
 * gallery — same lazy behavior as the legacy collapsed carousel.
 */
const galleryState = {
    rawImages: [],
    images: [],
    exampleFiles: [],
    activeIndex: 0,
    previewUrl: '',
    expanded: false,
};

/**
 * Load example images asynchronously
 * @param {Array} images - Array of image objects (both regular and custom)
 * @param {string} modelHash - Model hash for fetching local files
 * @param {string} previewUrl - Model preview URL shown in the collapsed state
 */
export async function loadExampleImages(images, modelHash, previewUrl = '') {
    try {
        const showcaseTab = document.getElementById('showcase-tab');
        if (!showcaseTab) return;

        // First fetch local example files
        let localFiles = [];

        try {
            const endpoint = '/api/lm/example-image-files';
            const params = `model_hash=${modelHash}`;

            const response = await fetch(`${endpoint}?${params}`);
            const result = await response.json();

            if (result.success) {
                localFiles = result.files;
            }
        } catch (error) {
            console.error("Failed to get example files:", error);
        }

        // Then render with both remote images and local files
        showcaseTab.innerHTML = renderShowcaseContent(images, localFiles, previewUrl);

        const gallery = showcaseTab.querySelector('.showcase-gallery');
        if (gallery) {
            initShowcaseContent(gallery);
        }

        // Initialize the example import functionality
        initExampleImport(modelHash, showcaseTab);
    } catch (error) {
        console.error('Error loading example images:', error);
        const showcaseTab = document.getElementById('showcase-tab');
        if (showcaseTab) {
            showcaseTab.innerHTML = `
                <div class="error-message">
                    <i class="fas fa-exclamation-circle"></i>
                    Error loading example images
                </div>
            `;
        }
    }
}

/**
 * Render a small local preview thumbnail for the collapsed indicator bar
 * (local file, no remote fetch)
 * @param {string} previewUrl - Model preview URL
 * @returns {string} HTML content, empty when no preview exists
 */
function renderPreviewThumb(previewUrl) {
    if (!previewUrl) return '';
    const isVideo = previewUrl.endsWith('.mp4') || previewUrl.endsWith('.webm');
    const media = isVideo
        ? `<video src="${escapeAttribute(previewUrl)}" muted playsinline preload="metadata"></video>`
        : `<img src="${escapeAttribute(previewUrl)}" alt="" loading="lazy">`;
    return `<span class="gallery-preview-thumb">${media}</span>`;
}

/**
 * Render showcase content: collapsed indicator bar by default, gallery
 * (main viewer + thumbnail strip + import entry) when expanded
 * @param {Array} images - Array of images/videos to show
 * @param {Array} exampleFiles - Local example files
 * @param {string} previewUrl - Model preview URL for the collapsed indicator bar
 * @param {boolean} expanded - Whether to render the full gallery (loads remote media)
 * @returns {string} HTML content
 */
export function renderShowcaseContent(images, exampleFiles = [], previewUrl = '', expanded = false) {
    galleryState.rawImages = images || [];
    galleryState.exampleFiles = exampleFiles;
    galleryState.previewUrl = previewUrl;
    galleryState.expanded = expanded;

    if (!images?.length) {
        galleryState.images = [];
        galleryState.activeIndex = 0;
        // Empty state: show the import interface directly
        return `
            <div class="showcase-gallery">
                ${renderImportInterface(true)}
            </div>
        `;
    }

    // Filter images based on SFW setting
    const showOnlySFW = state.settings.show_only_sfw;
    let filteredImages = images;
    let hiddenCount = 0;

    if (showOnlySFW) {
        filteredImages = images.filter(img => {
            const nsfwLevel = img.nsfwLevel !== undefined ? img.nsfwLevel : 0;
            const isSfw = nsfwLevel < NSFW_LEVELS.R;
            if (!isSfw) hiddenCount++;
            return isSfw;
        });
    }

    // Show message if no images are available after filtering
    if (filteredImages.length === 0) {
        galleryState.images = [];
        galleryState.activeIndex = 0;
        return `
            <div class="no-examples">
                <p>${translate('modals.model.showcase.allFiltered', {}, 'All example images are filtered due to NSFW content settings')}</p>
                <p class="nsfw-filter-info">${translate('modals.model.showcase.sfwOnlyEnabled', {}, 'Your settings are currently set to show only safe-for-work content')}</p>
                <p>${translate('modals.model.showcase.changeInSettings', {}, 'You can change this in Settings')} <i class="fas fa-cog"></i></p>
            </div>
        `;
    }

    galleryState.images = filteredImages;
    if (galleryState.activeIndex >= filteredImages.length || galleryState.activeIndex < 0) {
        galleryState.activeIndex = 0;
    }

    // Show hidden content notification if applicable
    const hiddenNotification = hiddenCount > 0 ?
        `<span class="nsfw-filter-notification">
            <i class="fas fa-eye-slash"></i> ${translate('modals.model.showcase.hiddenBySfw', { count: hiddenCount }, `${hiddenCount} hidden by SFW-only setting`)}
        </span>` : '';

    const exampleImagesPath = state.global.settings.example_images_path;
    const isPathConfigured = exampleImagesPath && exampleImagesPath.trim() !== '';
    const count = filteredImages.length;

    const importZone = isPathConfigured ? `<div class="gallery-import-zone hidden" id="galleryImportZone">
                ${renderImportInterface(false)}
            </div>` : '';

    // Collapsed resting state: a slim indicator bar only — remote examples are
    // not rendered (and therefore not fetched) until the user expands.
    if (!expanded) {
        const showText = translate('modals.model.showcase.showExamples', {}, 'Show examples');
        return `
        <div class="showcase-gallery">
            <div class="gallery-indicator-bar">
                ${renderPreviewThumb(previewUrl)}
                <button class="gallery-show-btn" id="galleryShowBtn">
                    <i class="fas fa-chevron-down"></i> ${translate('modals.model.showcase.showCount', { count }, `${showText} (${count})`)}
                </button>
                ${hiddenNotification}
                <button class="gallery-import-btn" id="galleryImportBtn" title="${translate('modals.model.showcase.addExamples', {}, 'Add examples')}">
                    <i class="fas fa-plus"></i> ${translate('modals.model.showcase.addExamples', {}, 'Add examples')}
                </button>
            </div>
            ${importZone}
        </div>
        `;
    }

    const showNav = count > 1;
    const positionText = `${galleryState.activeIndex + 1} / ${count}`;
    const activeImg = filteredImages[galleryState.activeIndex];
    const mediaAspect = mediaAspectRatio(activeImg);

    return `
        <div class="showcase-gallery">
            <div class="gallery-toolbar">
                ${hiddenNotification}
                <button class="gallery-show-btn" id="galleryShowBtn">
                    <i class="fas fa-chevron-up"></i> ${translate('modals.model.showcase.hideExamples', {}, 'Hide examples')}
                </button>
                <button class="gallery-import-btn" id="galleryImportBtn" title="${translate('modals.model.showcase.addExamples', {}, 'Add examples')}">
                    <i class="fas fa-plus"></i> ${translate('modals.model.showcase.addExamples', {}, 'Add examples')}
                </button>
            </div>
            <div class="gallery-main">
                <div class="main-media-container" id="mainMediaContainer" style="--media-aspect: ${mediaAspect}">
                    ${renderMediaItem(activeImg, galleryState.activeIndex, exampleFiles)}
                    ${renderPositionBadge(positionText)}
                </div>
                ${showNav ? `<button class="gallery-nav prev" id="galleryPrevBtn" title="${translate('modals.model.showcase.previousExample', {}, 'Previous example')}">
                    <i class="fas fa-chevron-left"></i>
                </button>
                <button class="gallery-nav next" id="galleryNextBtn" title="${translate('modals.model.showcase.nextExample', {}, 'Next example')}">
                    <i class="fas fa-chevron-right"></i>
                </button>` : ''}
            </div>
            <div class="gallery-strip" id="galleryStrip">
                ${filteredImages.map((img, index) => renderThumbnail(img, index, exampleFiles)).join('')}
            </div>
            ${importZone}
        </div>
    `;
}

/**
 * Render the position badge that floats over the main media
 * @param {string} positionText - e.g. "3 / 10"
 * @returns {string} HTML for the badge
 */
function renderPositionBadge(positionText) {
    return `<span class="gallery-position-badge" id="galleryPosition">${positionText}</span>`;
}

/**
 * Compute the aspect ratio (w/h) for the main viewer, falling back to 4:3
 * when dimensions are missing (prevents NaN layout)
 * @param {Object} img - Image/video metadata
 * @returns {number} width / height
 */
function mediaAspectRatio(img) {
    const w = img?.width || 4;
    const h = img?.height || 3;
    return w / h;
}

/**
 * Render a thumbnail for the gallery strip
 * @param {Object} img - Image/video metadata
 * @param {number} index - Index in the array
 * @param {Array} exampleFiles - Local files
 * @returns {string} HTML for the thumbnail button
 */
function renderThumbnail(img, index, exampleFiles) {
    const localFile = findLocalFile(img, index, exampleFiles);

    const originalRemoteUrl = img.url || '';
    const isVideo = localFile ? localFile.is_video :
        originalRemoteUrl.endsWith('.mp4') || originalRemoteUrl.endsWith('.webm');
    const mediaType = isVideo ? 'video' : 'image';

    const thumbUrl = localFile ? localFile.path : getGalleryThumbnailUrl(originalRemoteUrl, mediaType);

    const nsfwLevel = img.nsfwLevel !== undefined ? img.nsfwLevel : 0;
    const matureBlurThreshold = getMatureBlurThreshold(state.settings);
    const shouldBlur = state.settings.blur_mature_content && nsfwLevel >= matureBlurThreshold;

    const activeClass = index === galleryState.activeIndex ? ' active' : '';
    const blurClass = shouldBlur ? ' blurred' : '';
    const mediaHtml = isVideo ?
        `<video class="thumb-media${blurClass}" src="${escapeAttribute(thumbUrl)}" muted playsinline preload="none" data-lazy-video></video>
         <i class="fas fa-play thumb-video-badge"></i>` :
        `<img class="thumb-media${blurClass}" src="${escapeAttribute(thumbUrl)}" loading="lazy" fetchpriority="low" alt="">`;
    const nsfwBadge = shouldBlur ? '<i class="fas fa-eye-slash thumb-nsfw-badge"></i>' : '';

    return `<button class="gallery-thumb${activeClass}" data-index="${index}">${mediaHtml}${nsfwBadge}</button>`;
}

/**
 * Render the active media item in the main viewer
 * @param {Object} img - Image/video metadata
 * @param {number} index - Index in the array
 * @param {Array} exampleFiles - Local files
 * @returns {string} HTML for the media item
 */
function renderMediaItem(img, index, exampleFiles) {
    // Find matching file in our list of actual files
    let localFile = findLocalFile(img, index, exampleFiles);

    // Get original remote URL
    const originalRemoteUrl = img.url || '';

    // Determine media type for optimization
    const isVideo = localFile ? localFile.is_video :
                  originalRemoteUrl.endsWith('.mp4') || originalRemoteUrl.endsWith('.webm');
    const mediaType = isVideo ? 'video' : 'image';

    // Optimize CivitAI URLs for showcase display (full quality)
    const remoteUrl = getShowcaseUrl(originalRemoteUrl, mediaType);

    const localUrl = localFile ? localFile.path : '';

    // Extract CivitAI image ID from CDN URL for import status check
    const cdnImageId = (img.url || '').match(/\/(\d+)\.(?:jpeg|jpg|png|webp|gif)(?:\?|#|$)/)?.[1] || '';

    // Check if media should be blurred
    const nsfwLevel = img.nsfwLevel !== undefined ? img.nsfwLevel : 0;
    const matureBlurThreshold = getMatureBlurThreshold(state.settings);
    const shouldBlur = state.settings.blur_mature_content && nsfwLevel >= matureBlurThreshold;

    // Determine NSFW warning text based on level
    let nsfwText = translate('modals.model.showcase.nsfwMature', {}, 'Mature Content');
    if (nsfwLevel >= NSFW_LEVELS.XXX) {
        nsfwText = translate('modals.model.showcase.nsfwXxx', {}, 'XXX-rated Content');
    } else if (nsfwLevel >= NSFW_LEVELS.X) {
        nsfwText = translate('modals.model.showcase.nsfwX', {}, 'X-rated Content');
    } else if (nsfwLevel >= NSFW_LEVELS.R) {
        nsfwText = translate('modals.model.showcase.nsfwR', {}, 'R-rated Content');
    }

    // Extract metadata from the image
    const meta = img.meta || {};
    const prompt = meta.prompt || '';
    const negativePrompt = meta.negative_prompt || meta.negativePrompt || '';
    const size = meta.Size || `${img.width}x${img.height}`;
    const seed = meta.seed || '';
    const model = meta.Model || '';
    const steps = meta.steps || '';
    const sampler = meta.sampler || '';
    const cfgScale = meta.cfg_scale || meta.cfgScale || '';
    const clipSkip = meta.clip_skip || meta.clipSkip || '';

    // Check if we have any meaningful generation parameters
    const hasParams = seed || model || steps || sampler || cfgScale || clipSkip;
    const hasPrompts = prompt || negativePrompt;

    // Create metadata panel content
    const metadataPanel = generateMetadataPanel(
        hasParams, hasPrompts,
        prompt, negativePrompt,
        size, seed, model, steps, sampler, cfgScale, clipSkip
    );

    // Determine if this is a custom image (has id property)
    const isCustomImage = Boolean(typeof img.id === 'string' && img.id);

    const hasGenMeta = img.hasMeta || (img.meta && (img.meta.prompt || img.meta.seed || img.meta.resources));

    // Create the media control buttons HTML
    const mediaControlsHtml = `
        <div class="media-controls">
            <button class="media-control-btn set-preview-btn" title="Set as preview">
                <i class="fas fa-image"></i>
            </button>
            ${hasGenMeta ? `
            <button class="media-control-btn create-recipe-btn"
                    title="Create As Recipe"
                    data-image-meta="${encodeURIComponent(JSON.stringify(img.meta || {}))}"
                    data-image-url="${img.url || ''}"
                    data-image-nsfw="${img.nsfwLevel ?? ''}"
                    data-image-id="${cdnImageId}"
                    data-img-id="${img.id || ''}"
                    data-local-path="${localFile ? localFile.path : ''}">
                <i class="fas fa-book-open"></i>
            </button>
            ` : ''}
            <button class="media-control-btn set-nsfw-btn"
                    title="Set content rating"
                    data-media-index="${index}"
                    data-media-source="${isCustomImage ? 'custom' : 'civitai'}"
                    data-media-id="${img.id || ''}">
                <i class="fas fa-exclamation-triangle"></i>
            </button>
            <button class="media-control-btn example-delete-btn ${!isCustomImage ? 'disabled' : ''}"
                    title="${isCustomImage ? 'Delete this example' : 'Only custom images can be deleted'}"
                    data-short-id="${img.id || ''}"
                    ${!isCustomImage ? 'aria-disabled="true"' : ''}>
                <i class="fas fa-trash-alt"></i>
                <i class="fas fa-check confirm-icon"></i>
            </button>
        </div>
    `;

    // Generate the appropriate wrapper based on media type
    if (isVideo) {
        return generateVideoWrapper(
            img, shouldBlur, nsfwText, metadataPanel,
            localUrl, remoteUrl, mediaControlsHtml
        );
    }

    return generateImageWrapper(
        img, shouldBlur, nsfwText, metadataPanel,
        localUrl, remoteUrl, mediaControlsHtml
    );
}

/**
 * Find the matching local file for an image
 * @param {Object} img - Image metadata
 * @param {number} index - Image index
 * @param {Array} exampleFiles - Array of local files
 * @returns {Object|null} Matching local file or null
 */
function findLocalFile(img, index, exampleFiles) {
    if (!exampleFiles || exampleFiles.length === 0) return null;

    let localFile = null;

    if (typeof img.id === 'string' && img.id) {
        // This is a custom image, find by custom_<id>
        const customPrefix = `custom_${img.id}`;
        localFile = exampleFiles.find(file => file.name.startsWith(customPrefix));
    } else {
        // This is a regular image from civitai, find by index
        localFile = exampleFiles.find(file => {
            const match = file.name.match(/image_(\d+)\./);
            return match && parseInt(match[1]) === index;
        });
    }

    return localFile;
}

// URLs already warmed in the HTTP cache, so repeat navigations and re-renders
// never issue duplicate prefetch requests
const prefetchedUrls = new Set();

// Direction of the last main-viewer navigation (+1 next / -1 prev); users
// tend to keep clicking the same arrow, so prefetch reaches one further
// ahead along it. Defaults to forward (Next is the most common navigation)
let lastNavDirection = 1;

/**
 * Warm the HTTP cache for the examples most likely to be shown next: both
 * indices adjacent to the active one, plus one extra ahead along the last
 * navigation direction, so prev/next navigation feels instant. Images only:
 * video payloads are too heavy for speculative prefetch, and locally stored
 * examples need no network fetch at all.
 */
function prefetchAdjacentMedia() {
    const { images, exampleFiles, activeIndex, expanded } = galleryState;
    if (!expanded || images.length < 2) return;

    [1, -1, lastNavDirection * 2].forEach(offset => {
        const index = ((activeIndex + offset) % images.length + images.length) % images.length;
        const img = images[index];
        if (!img?.url || findLocalFile(img, index, exampleFiles)) return;

        const isVideo = img.url.endsWith('.mp4') || img.url.endsWith('.webm');
        if (isVideo) return;

        const url = getShowcaseUrl(img.url, 'image');
        if (prefetchedUrls.has(url)) return;
        prefetchedUrls.add(url);

        // Off-DOM image: fills the HTTP/memory cache without affecting layout.
        // Low priority keeps it from competing with the active media's load.
        const preloader = new Image();
        preloader.fetchPriority = 'low';
        preloader.src = url;
    });
}

/**
 * Switch the main viewer to another example (wraps around)
 * @param {number} index - Target index in galleryState.images
 */
export function updateMainDisplay(index) {
    const count = galleryState.images.length;
    if (!count || !galleryState.expanded) return;

    // Remember the navigation direction for direction-aware prefetching
    // (a raw index of -1 / count means wrap-around prev / next)
    const delta = index - galleryState.activeIndex;
    if (delta !== 0) lastNavDirection = delta > 0 ? 1 : -1;

    galleryState.activeIndex = ((index % count) + count) % count;

    const container = document.getElementById('mainMediaContainer');
    if (!container) return;

    const activeImg = galleryState.images[galleryState.activeIndex];
    container.style.setProperty('--media-aspect', mediaAspectRatio(activeImg));
    // The badge lives inside the container, so rebuild it together with the media
    container.innerHTML = renderMediaItem(
        activeImg,
        galleryState.activeIndex,
        galleryState.exampleFiles
    ) + renderPositionBadge(`${galleryState.activeIndex + 1} / ${count}`);

    // Update thumbnail active state and scroll it into view
    document.querySelectorAll('.gallery-strip .gallery-thumb').forEach(thumb => {
        const isActive = Number(thumb.dataset.index) === galleryState.activeIndex;
        thumb.classList.toggle('active', isActive);
        if (isActive) {
            thumb.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
        }
    });

    initMainMediaInteractions(container);
    prefetchAdjacentMedia();
}

/**
 * Build the item list for the full-size media viewer from current gallery state
 * @returns {Array<{url: string, type: string}>}
 */
function buildViewerItems() {
    return galleryState.images.map((img, index) => {
        const localFile = findLocalFile(img, index, galleryState.exampleFiles);
        const originalRemoteUrl = img.url || '';
        const isVideo = localFile ? localFile.is_video :
            originalRemoteUrl.endsWith('.mp4') || originalRemoteUrl.endsWith('.webm');
        return {
            url: localFile?.path || getShowcaseUrl(originalRemoteUrl, isVideo ? 'video' : 'image'),
            type: isVideo ? 'video' : 'image'
        };
    });
}

/**
 * Wire up interactions for the media currently shown in the main viewer
 * @param {HTMLElement} container - The main media container
 */
function initMainMediaInteractions(container) {
    initLazyLoading(container);
    initNsfwBlurHandlers(container);
    initMetadataPanelHandlers(container);
    initMediaControlHandlers(container);
    positionAllMediaControls(container);

    // Hoist the metadata panel to the gallery-main level so it spans the full
    // column width (legacy behavior) instead of being squeezed to the media's
    // width. Handler references stay valid — they are bound to the element.
    const panel = container.querySelector('.image-metadata-panel');
    const galleryMain = container.closest('.gallery-main');
    if (panel && galleryMain) {
        // Drop the panel of the previously displayed item, if any
        galleryMain.querySelectorAll(':scope > .image-metadata-panel').forEach(p => p.remove());
        galleryMain.appendChild(panel);
    }

    // Click-to-view: open full-size media viewer at the active index
    const mediaEl = container.querySelector('.media-wrapper img, .media-wrapper video');
    if (mediaEl) {
        mediaEl.addEventListener('click', (e) => {
            e.stopPropagation();
            openMediaViewer(buildViewerItems(), galleryState.activeIndex);
        });
    }

    // Reposition controls once media dimensions are known
    container.querySelectorAll('img, video').forEach(media => {
        media.addEventListener('load', () => positionAllMediaControls(container));
        if (media.tagName === 'VIDEO') {
            media.addEventListener('loadedmetadata', () => positionAllMediaControls(container));
        }
    });
}

/**
 * Scroll to top of modal content
 * @param {HTMLElement} button - Back to top button
 */
export function scrollToTop(button) {
    const modalContent = button.closest('.modal-content');
    if (modalContent) {
        modalContent.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    }
}

/**
 * Toggle the inline import zone; without a configured path, open settings instead
 * @param {HTMLElement} gallery - The gallery root element
 */
function toggleImportZone(gallery) {
    const exampleImagesPath = state.global.settings.example_images_path;
    const isPathConfigured = exampleImagesPath && exampleImagesPath.trim() !== '';
    if (!isPathConfigured) {
        openSettingsForExampleImages();
        return;
    }
    gallery.querySelector('.gallery-import-zone')?.classList.toggle('hidden');
}

/**
 * Remove a deleted custom example from the gallery and re-render
 * @param {string} shortId - Custom image short id
 */
function handleExampleDeleted(shortId) {
    const isDeleted = (img) => img.id === shortId;
    galleryState.rawImages = galleryState.rawImages.filter(img => !isDeleted(img));
    galleryState.images = galleryState.images.filter(img => !isDeleted(img));
    galleryState.exampleFiles = galleryState.exampleFiles.filter(
        file => !file.name.startsWith(`custom_${shortId}`)
    );
    if (galleryState.activeIndex >= galleryState.images.length) {
        galleryState.activeIndex = Math.max(0, galleryState.images.length - 1);
    }

    rerenderGallery(galleryState.expanded);
}

/**
 * Re-render the gallery in place from current state and rebind everything
 * @param {boolean} expanded - Whether the re-rendered gallery starts expanded
 */
function rerenderGallery(expanded) {
    const showcaseTab = document.getElementById('showcase-tab');
    if (!showcaseTab) return;

    showcaseTab.innerHTML = renderShowcaseContent(
        galleryState.rawImages,
        galleryState.exampleFiles,
        galleryState.previewUrl,
        expanded
    );

    const gallery = showcaseTab.querySelector('.showcase-gallery');
    if (gallery) {
        initShowcaseContent(gallery);
    }

    const modelHash = document.querySelector('.showcase-section')?.dataset.modelHash;
    if (modelHash) {
        initExampleImport(modelHash, showcaseTab);
    }
}

// Track the gallery whose controls need repositioning on window resize
let resizeBoundGallery = null;

// Scroll-to-expand: expands the collapsed gallery when the user keeps
// scrolling down near the bottom of the modal (legacy muscle memory)
let scrollExpandTarget = null;

function setupScrollToExpand(gallery) {
    const modalContent = gallery.closest('.modal-content');
    if (!modalContent) return;
    if (scrollExpandTarget === modalContent) return; // already bound
    scrollExpandTarget = modalContent;

    modalContent.addEventListener('wheel', (event) => {
        if (galleryState.expanded || !galleryState.images.length) return;
        if (event.deltaY <= 0) return;
        const nearBottom = modalContent.scrollHeight - modalContent.scrollTop - modalContent.clientHeight < 100;
        if (nearBottom) {
            rerenderGallery(true);
        }
    }, { passive: true });
}

/**
 * Defer metadata fetches for video thumbnails until they scroll into view:
 * with preload="metadata" on every strip video, expanding the gallery would
 * otherwise hit the network for all of them at once
 * @param {HTMLElement} gallery - The .showcase-gallery element
 */
function initStripVideoLazyLoading(gallery) {
    const videos = gallery.querySelectorAll('.gallery-strip video[data-lazy-video]');
    if (!videos.length) return;

    const enable = (video) => {
        video.preload = 'metadata';
        video.load();
        video.removeAttribute('data-lazy-video');
    };

    if (typeof IntersectionObserver === 'undefined') {
        videos.forEach(enable);
        return;
    }

    // No explicit root: intersection accounts for the strip's overflow
    // clipping, so off-screen thumbnails stay at preload="none"
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                enable(entry.target);
                observer.unobserve(entry.target);
            }
        });
    });
    videos.forEach(video => observer.observe(video));
}

/**
 * Initialize all gallery interactions
 * @param {HTMLElement} gallery - The .showcase-gallery element
 */
export function initShowcaseContent(gallery) {
    if (!gallery) return;

    // While expanded the thumbnail strip occupies the modal's bottom-right
    // corner; hide the back-to-top button there (Hide examples is the
    // equivalent "return to top" affordance)
    gallery.closest('.modal-content')?.classList.toggle('showcase-expanded', galleryState.expanded);

    // Toolbar: show/hide toggle (expanding renders the gallery and starts remote loads)
    gallery.querySelector('#galleryShowBtn')?.addEventListener('click', () => {
        rerenderGallery(!galleryState.expanded);
    });

    // Same expansion via mouse wheel near the bottom of the modal
    setupScrollToExpand(gallery);

    // Toolbar: import toggle; scroll the freshly opened zone into view
    gallery.querySelector('#galleryImportBtn')?.addEventListener('click', () => {
        toggleImportZone(gallery);
        const zone = gallery.querySelector('.gallery-import-zone:not(.hidden)');
        zone?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });

    // Prev/next navigation (wraps around)
    gallery.querySelector('#galleryPrevBtn')?.addEventListener('click', () => {
        updateMainDisplay(galleryState.activeIndex - 1);
    });
    gallery.querySelector('#galleryNextBtn')?.addEventListener('click', () => {
        updateMainDisplay(galleryState.activeIndex + 1);
    });

    // Thumbnail strip: click to select, wheel scrolls horizontally
    gallery.querySelectorAll('.gallery-thumb').forEach(thumb => {
        thumb.addEventListener('click', () => {
            updateMainDisplay(Number(thumb.dataset.index));
        });
    });
    const strip = gallery.querySelector('.gallery-strip');
    if (strip) {
        strip.addEventListener('wheel', (e) => {
            if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return; // let native horizontal scrolling through
            e.preventDefault();
            strip.scrollLeft += e.deltaY;
        }, { passive: false });
    }

    // Custom example deleted elsewhere (media controls) → refresh gallery
    gallery.addEventListener('example-media-deleted', (e) => {
        handleExampleDeleted(e.detail?.shortId);
    });

    // Main viewer interactions (only exists in the expanded state)
    const container = gallery.querySelector('.main-media-container');
    if (container && galleryState.expanded) {
        initMainMediaInteractions(container);
        // Gallery just (re)rendered expanded: warm the cache for the
        // examples adjacent to the active one
        prefetchAdjacentMedia();
        // Video thumbnails start at preload="none"; enable them on visibility
        initStripVideoLazyLoading(gallery);
    }

    // Reposition controls on window resize
    resizeBoundGallery = gallery;
}

// Bind the resize handler once; it always repositions the latest gallery
window.addEventListener('resize', () => {
    if (resizeBoundGallery && resizeBoundGallery.isConnected) {
        positionAllMediaControls(resizeBoundGallery);
    }
});

/**
 * Render the import interface for example images
 * @param {boolean} isEmpty - Whether there are no existing examples
 * @returns {string} HTML content for import interface
 */
function renderImportInterface(isEmpty) {
    // Check if example images path is configured
    const exampleImagesPath = state.global.settings.example_images_path;
    const isPathConfigured = exampleImagesPath && exampleImagesPath.trim() !== '';

    // If path is not configured, show setup guidance
    if (!isPathConfigured) {
        const title = translate('uiHelpers.exampleImages.setupRequired', {}, 'Example Images Storage');
        const description = translate('uiHelpers.exampleImages.setupDescription', {}, 'To add custom example images, you need to set a download location first.');
        const usage = translate('uiHelpers.exampleImages.setupUsage', {}, 'This path is used for both downloaded and custom example images.');
        const openSettings = translate('uiHelpers.exampleImages.openSettings', {}, 'Open Settings');

        return `
            <div class="example-import-area ${isEmpty ? 'empty' : ''}">
                <div class="import-container import-container--needs-setup" id="exampleImportContainer">
                    <div class="import-setup-guidance">
                        <div class="setup-icon">
                            <i class="fas fa-folder-plus"></i>
                        </div>
                        <h3>${title}</h3>
                        <p class="setup-description">
                            ${description}
                        </p>
                        <p class="setup-usage">
                            ${usage}
                        </p>
                        <button class="select-files-btn setup-settings-btn" id="openExampleSettingsBtn">
                            <i class="fas fa-cog"></i> ${openSettings}
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    return `
        <div class="example-import-area ${isEmpty ? 'empty' : ''}">
            <div class="import-container" id="exampleImportContainer">
                <div class="import-placeholder">
                    <i class="fas fa-cloud-upload-alt"></i>
                    <h3>${isEmpty
                        ? translate('modals.model.showcase.noExamples', {}, 'No example images available')
                        : translate('modals.model.showcase.addMoreExamples', {}, 'Add more examples')}</h3>
                    <p>${translate('modals.model.showcase.dragDrop', {}, 'Drag & drop images or videos here')}</p>
                    <p class="sub-text">${translate('modals.model.showcase.or', {}, 'or')}</p>
                    <button class="select-files-btn" id="selectExampleFilesBtn">
                        <i class="fas fa-folder-open"></i> ${translate('modals.model.showcase.selectFiles', {}, 'Select Files')}
                    </button>
                    <p class="import-formats">${translate('modals.model.showcase.supportedFormats', {}, 'Supported formats: jpg, png, gif, webp, avif, jxl, mp4, webm')}</p>
                </div>
                <input type="file" id="exampleFilesInput" multiple accept="image/*,image/avif,image/jxl,video/mp4,video/webm" style="display: none;">
                <div class="import-progress-container" style="display: none;">
                    <div class="import-progress">
                        <div class="progress-bar"></div>
                    </div>
                    <span class="progress-text">${translate('modals.model.showcase.importing', {}, 'Importing files...')}</span>
                </div>
            </div>
        </div>
    `;
}

/**
 * Open settings modal and scroll to example images section
 */
function openSettingsForExampleImages() {
    modalManager.showModal('settingsModal');

    // Wait for modal to be visible, then scroll to example images section
    setTimeout(() => {
        const exampleImagesInput = document.getElementById('exampleImagesPath');
        if (exampleImagesInput) {
            // Find the parent settings-section
            const section = exampleImagesInput.closest('.settings-section');
            if (section) {
                section.scrollIntoView({ behavior: 'smooth', block: 'center' });
                // Add a brief highlight effect
                section.style.transition = 'background-color 0.3s ease';
                section.style.backgroundColor = 'rgba(66, 153, 225, 0.1)';
                setTimeout(() => {
                    section.style.backgroundColor = '';
                }, 1500);
            }
            // Focus the input
            exampleImagesInput.focus();
        }
    }, 100);
}

/**
 * Initialize the example import functionality
 * @param {string} modelHash - The SHA256 hash of the model
 * @param {Element} container - The container element for the import area
 */
export function initExampleImport(modelHash, container) {
    if (!container) return;

    const importContainer = container.querySelector('#exampleImportContainer');
    const fileInput = container.querySelector('#exampleFilesInput');
    const selectFilesBtn = container.querySelector('#selectExampleFilesBtn');
    const openSettingsBtn = container.querySelector('#openExampleSettingsBtn');

    // Set up "Open Settings" button for setup guidance state
    if (openSettingsBtn) {
        openSettingsBtn.addEventListener('click', () => {
            openSettingsForExampleImages();
        });
    }

    // Set up file selection button
    if (selectFilesBtn) {
        selectFilesBtn.addEventListener('click', () => {
            fileInput.click();
        });
    }

    // Handle file selection
    if (fileInput) {
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleImportFiles(Array.from(e.target.files), modelHash, importContainer);
            }
        });
    }

    // Set up drag and drop
    if (importContainer) {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            importContainer.addEventListener(eventName, preventDefaults, false);
        });

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        // Highlight drop area on drag over
        ['dragenter', 'dragover'].forEach(eventName => {
            importContainer.addEventListener(eventName, () => {
                importContainer.classList.add('highlight');
            }, false);
        });

        // Remove highlight on drag leave
        ['dragleave', 'drop'].forEach(eventName => {
            importContainer.addEventListener(eventName, () => {
                importContainer.classList.remove('highlight');
            }, false);
        });

        // Handle dropped files
        importContainer.addEventListener('drop', (e) => {
            const files = Array.from(e.dataTransfer.files);
            handleImportFiles(files, modelHash, importContainer);
        }, false);
    }
}

/**
 * Handle the file import process
 * @param {File[]} files - Array of files to import
 * @param {string} modelHash - The SHA256 hash of the model
 * @param {Element} importContainer - The container element for import UI
 */
async function handleImportFiles(files, modelHash, importContainer) {
    // Filter for supported file types
    const supportedImages = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif', '.jxl'];
    const supportedVideos = ['.mp4', '.webm'];
    const supportedExtensions = [...supportedImages, ...supportedVideos];

    const validFiles = files.filter(file => {
        const ext = '.' + file.name.split('.').pop().toLowerCase();
        return supportedExtensions.includes(ext);
    });

    if (validFiles.length === 0) {
        showToast('modals.model.showcase.noSupportedFiles', {}, 'warning');
        return;
    }

    try {
        // Upload files one at a time to avoid exceeding server size limits
        let lastSuccessResult = null;
        let successCount = 0;
        const errors = [];

        for (const file of validFiles) {
            try {
                const formData = new FormData();
                formData.append('model_hash', modelHash);
                formData.append('files', file);

                const response = await fetch('/api/lm/import-example-images', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                if (!result.success) {
                    errors.push(`${file.name}: ${result.error || 'Unknown error'}`);
                } else {
                    lastSuccessResult = result;
                    successCount++;
                }
            } catch (err) {
                errors.push(`${file.name}: ${err.message}`);
            }
        }

        if (successCount === 0) {
            throw new Error(errors.join('; '));
        }

        const result = lastSuccessResult;

        // Get updated local files
        const updatedFilesResponse = await fetch(`/api/lm/example-image-files?model_hash=${modelHash}`);
        const updatedFilesResult = await updatedFilesResponse.json();

        if (!updatedFilesResult.success) {
            throw new Error(updatedFilesResult.error || 'Failed to get updated file list');
        }

        // Re-render the showcase content, expanded so the user sees the result
        const showcaseTab = document.getElementById('showcase-tab');
        if (showcaseTab) {
            // Get the updated images from the result
            const regularImages = result.regular_images || [];
            const customImages = result.custom_images || [];
            // Combine both arrays for rendering
            const allImages = [...regularImages, ...customImages];
            showcaseTab.innerHTML = renderShowcaseContent(allImages, updatedFilesResult.files, galleryState.previewUrl, true);

            // Re-initialize gallery functionality
            const gallery = showcaseTab.querySelector('.showcase-gallery');
            if (gallery) {
                initShowcaseContent(gallery);
                // Select the most recently imported example
                updateMainDisplay(galleryState.images.length - 1);
                // Keep the import zone expanded so multi-file imports can continue
                gallery.querySelector('.gallery-import-zone')?.classList.remove('hidden');
            }

            // Initialize the import UI for the new content
            initExampleImport(modelHash, showcaseTab);

            if (errors.length > 0) {
                showToast('toast.import.imagesPartial', { success: successCount, failed: errors.length }, 'warning');
            } else {
                showToast('toast.import.imagesImported', {}, 'success');
            }

            // Update VirtualScroller if available
            if (state.virtualScroller && result.model_file_path) {
                // Create an update object with only the necessary properties
                const updateData = {
                    civitai: {
                        images: regularImages,
                        customImages: customImages
                    }
                };

                // Update the item in the virtual scroller
                state.virtualScroller.updateSingleItem(result.model_file_path, updateData);
            }
        }
    } catch (error) {
        console.error('Error importing examples:', error);
        showToast('toast.import.importFailed', { message: error.message }, 'error');
    }
}
