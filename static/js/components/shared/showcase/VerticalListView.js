/**
 * VerticalListView.js
 * Classic vertical example list for the model modal showcase: every example
 * rendered full-width and stacked, each with its own metadata panel and media
 * controls. Revived from the pre-gallery implementation (removed in v1.2.2),
 * adapted to the current shared showcase infrastructure (MediaRenderers,
 * MediaUtils) — no legacy scroll/metrics machinery.
 */
import {
    initLazyLoading,
    initNsfwBlurHandlers,
    initMetadataPanelHandlers,
    initMediaControlHandlers,
    positionAllMediaControls
} from './MediaUtils.js';
import { renderShowcaseMediaItem, findLocalFile } from './MediaRenderers.js';
import { getShowcaseUrl } from '../../../utils/civitaiUtils.js';
import { openMediaViewer } from '../MediaViewer.js';

/**
 * Render the vertical list: all examples stacked in a column
 * @param {Array} images - Filtered images/videos to show
 * @param {Array} exampleFiles - Local example files
 * @returns {string} HTML content
 */
export function renderVerticalList(images, exampleFiles = []) {
    return `
        <div class="vertical-list-container">
            ${images.map((img, index) => renderVerticalMediaItem(img, index, exampleFiles)).join('')}
        </div>
    `;
}

/**
 * Render a single vertical-list item. The wrapper is sized by the
 * padding-bottom aspect-ratio hack so the column layout is stable before any
 * media loads (and lazy loading has a box to intersect).
 * @param {Object} img - Image/video metadata
 * @param {number} index - Index in the array
 * @param {Array} exampleFiles - Local files
 * @returns {string} HTML for the media item
 */
function renderVerticalMediaItem(img, index, exampleFiles) {
    return renderShowcaseMediaItem(img, index, exampleFiles, {
        heightPercent: computeHeightPercent(img),
        fullQuality: true,
    });
}

/**
 * Compute the wrapper height as a padding-bottom percent of the modal width,
 * clamped so very tall or very wide media still gets a reasonable box
 * (defensive 4:3 fallback for missing dimensions prevents NaN layout)
 * @param {Object} img - Image/video metadata
 * @returns {number} padding-bottom percent
 */
function computeHeightPercent(img) {
    const safeW = img.width || 4;
    const safeH = img.height || 3;
    const aspectRatio = (safeH / safeW) * 100;
    const containerWidth = 800; // modal content maximum width
    const minHeightPercent = 40;
    const maxHeightPercent = (window.innerHeight * 0.6 / containerWidth) * 100;
    return Math.max(minHeightPercent, Math.min(maxHeightPercent, aspectRatio));
}

/**
 * Build the item list for the full-size media viewer from the rendered items
 * @param {Array} images - Rendered images/videos
 * @param {Array} exampleFiles - Local example files
 * @returns {Array<{url: string, type: string}>}
 */
function buildViewerItems(images, exampleFiles) {
    return images.map((img, index) => {
        const localFile = findLocalFile(img, index, exampleFiles);
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
 * Initialize all vertical-list interactions: lazy loading, NSFW blur,
 * per-item metadata panels and media controls, click-to-view
 * @param {HTMLElement} container - The .showcase-vertical root element
 * @param {Array} images - Rendered images/videos (aligned with DOM order)
 * @param {Array} exampleFiles - Local example files
 */
export function initVerticalList(container, images, exampleFiles = []) {
    if (!container) return;

    initLazyLoading(container);
    initNsfwBlurHandlers(container);
    initMetadataPanelHandlers(container);
    initMediaControlHandlers(container);
    positionAllMediaControls(container);

    // Click-to-view: open the full-size media viewer at the clicked item
    const viewerItems = buildViewerItems(images, exampleFiles);
    container.querySelectorAll('.vertical-list-container .media-wrapper').forEach((wrapper, index) => {
        const mediaEl = wrapper.querySelector('img, video');
        if (!mediaEl) return;
        mediaEl.addEventListener('click', (e) => {
            e.stopPropagation();
            openMediaViewer(viewerItems, index);
        });
    });

    // Reposition controls once media dimensions are known
    container.querySelectorAll('.vertical-list-container img, .vertical-list-container video').forEach(media => {
        media.addEventListener('load', () => positionAllMediaControls(container));
        if (media.tagName === 'VIDEO') {
            media.addEventListener('loadedmetadata', () => positionAllMediaControls(container));
        }
    });
}
