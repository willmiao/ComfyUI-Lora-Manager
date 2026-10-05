/**
 * MediaRenderers.js
 * HTML generators for media items (images/videos) in the showcase
 */
import { state } from '../../../state/index.js';
import { translate } from '../../../utils/i18nHelpers.js';
import { NSFW_LEVELS, getMatureBlurThreshold } from '../../../utils/constants.js';
import { generateMetadataPanel } from './MetadataPanel.js';
import { getDisplayUrl, getShowcaseUrl } from '../../../utils/civitaiUtils.js';

/**
 * Generate video wrapper HTML. The wrapper fills its container (the gallery's
 * main viewer) and the media is letterboxed inside via object-fit: contain.
 * @param {Object} media - Media metadata
 * @param {boolean} shouldBlur - Whether content should be blurred
 * @param {string} nsfwText - NSFW warning text
 * @param {string} metadataPanel - Metadata panel HTML
 * @param {string} localUrl - Local file URL
 * @param {string} remoteUrl - Remote file URL
 * @param {string} mediaControlsHtml - HTML for media control buttons
 * @param {number|null} heightPercent - Vertical-list aspect ratio (padding-bottom
 *   percent) sizing the wrapper before the media loads; null in gallery mode
 * @returns {string} HTML content
 */
export function generateVideoWrapper(media, shouldBlur, nsfwText, metadataPanel, localUrl, remoteUrl, mediaControlsHtml = '', heightPercent = null) {
    const nsfwLevel = media.nsfwLevel !== undefined ? media.nsfwLevel : 0;
    const wrapperStyle = heightPercent !== null ? ` style="padding-bottom: ${heightPercent}%"` : '';

    return `
        <div class="media-wrapper ${shouldBlur ? 'nsfw-media-wrapper' : ''}"${wrapperStyle} data-short-id="${media.id || ''}" data-nsfw-level="${nsfwLevel}">
            ${shouldBlur ? `
                <button class="toggle-blur-btn showcase-toggle-btn" title="Toggle blur">
                    <i class="fas fa-eye"></i>
                </button>
            ` : ''}
            ${mediaControlsHtml}
            <video controls autoplay muted loop
                data-local-src="${localUrl || ''}"
                data-remote-src="${remoteUrl}"
                data-nsfw-level="${nsfwLevel}"
                class="lazy ${shouldBlur ? 'blurred' : ''}">
                <source data-local-src="${localUrl || ''}" data-remote-src="${remoteUrl}" type="video/mp4">
                Your browser does not support video playback
            </video>
            ${shouldBlur ? `
                <div class="nsfw-overlay">
                    <div class="nsfw-warning">
                        <p>${nsfwText}</p>
                        <button class="show-content-btn">Show</button>
                    </div>
                </div>
            ` : ''}
            ${metadataPanel}
        </div>
    `;
}

/**
 * Generate image wrapper HTML. The wrapper fills its container (the gallery's
 * main viewer) and the media is letterboxed inside via object-fit: contain.
 * @param {Object} media - Media metadata
 * @param {boolean} shouldBlur - Whether content should be blurred
 * @param {string} nsfwText - NSFW warning text
 * @param {string} metadataPanel - Metadata panel HTML
 * @param {string} localUrl - Local file URL
 * @param {string} remoteUrl - Remote file URL
 * @param {string} mediaControlsHtml - HTML for media control buttons
 * @param {number|null} heightPercent - Vertical-list aspect ratio (padding-bottom
 *   percent) sizing the wrapper before the media loads; null in gallery mode
 * @returns {string} HTML content
 */
export function generateImageWrapper(media, shouldBlur, nsfwText, metadataPanel, localUrl, remoteUrl, mediaControlsHtml = '', heightPercent = null) {
    const nsfwLevel = media.nsfwLevel !== undefined ? media.nsfwLevel : 0;
    const wrapperStyle = heightPercent !== null ? ` style="padding-bottom: ${heightPercent}%"` : '';

    return `
        <div class="media-wrapper ${shouldBlur ? 'nsfw-media-wrapper' : ''}"${wrapperStyle} data-short-id="${media.id || ''}" data-nsfw-level="${nsfwLevel}">
            ${shouldBlur ? `
                <button class="toggle-blur-btn showcase-toggle-btn" title="Toggle blur">
                    <i class="fas fa-eye"></i>
                </button>
            ` : ''}
            ${mediaControlsHtml}
            <img data-local-src="${localUrl || ''}"
                data-remote-src="${remoteUrl}"
                data-nsfw-level="${nsfwLevel}"
                alt="Preview"
                width="${media.width}"
                height="${media.height}"
                ${heightPercent === null ? 'fetchpriority="high"' : ''}
                class="lazy ${shouldBlur ? 'blurred' : ''}">
            ${shouldBlur ? `
                <div class="nsfw-overlay">
                    <div class="nsfw-warning">
                        <p>${nsfwText}</p>
                        <button class="show-content-btn">Show</button>
                    </div>
                </div>
            ` : ''}
            ${metadataPanel}
        </div>
    `;
}

/**
 * Find the matching local file for an image
 * @param {Object} img - Image metadata
 * @param {number} index - Image index
 * @param {Array} exampleFiles - Array of local files
 * @returns {Object|null} Matching local file or null
 */
export function findLocalFile(img, index, exampleFiles) {
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

/**
 * Render a single showcase media item (image or video) with its metadata
 * panel and media controls. Shared by the gallery's main viewer and the
 * vertical list layout.
 * @param {Object} img - Image/video metadata
 * @param {number} index - Index in the array
 * @param {Array} exampleFiles - Local files
 * @param {Object} options - Rendering options
 * @param {number|null} options.heightPercent - Vertical-list aspect ratio
 *   (padding-bottom percent) for the wrapper; null sizes the wrapper from its
 *   container (gallery main viewer)
 * @param {boolean} options.fullQuality - True to use the full-quality showcase
 *   URL (vertical list), false for the display-optimized URL (gallery viewer)
 * @returns {string} HTML for the media item
 */
export function renderShowcaseMediaItem(img, index, exampleFiles, { heightPercent = null, fullQuality = false } = {}) {
    // Find matching file in our list of actual files
    let localFile = findLocalFile(img, index, exampleFiles);

    // Get original remote URL
    const originalRemoteUrl = img.url || '';

    // Determine media type for optimization
    const isVideo = localFile ? localFile.is_video :
                  originalRemoteUrl.endsWith('.mp4') || originalRemoteUrl.endsWith('.webm');
    const mediaType = isVideo ? 'video' : 'image';

    // Gallery main viewer: CivitAI URLs capped at width=2400 (the full-size
    // media viewer uses getShowcaseUrl separately). Vertical list: full
    // quality, matching the legacy behavior.
    const remoteUrl = fullQuality
        ? getShowcaseUrl(originalRemoteUrl, mediaType)
        : getDisplayUrl(originalRemoteUrl, mediaType);

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
            localUrl, remoteUrl, mediaControlsHtml, heightPercent
        );
    }

    return generateImageWrapper(
        img, shouldBlur, nsfwText, metadataPanel,
        localUrl, remoteUrl, mediaControlsHtml, heightPercent
    );
}
