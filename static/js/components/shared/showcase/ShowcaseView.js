/**
 * ShowcaseView.js
 * Shared showcase component for displaying examples in model modals (Lora/Checkpoint)
 */
import { showToast } from '../../../utils/uiHelpers.js';
import { state } from '../../../state/index.js';
import { NSFW_LEVELS } from '../../../utils/constants.js';
import { 
    initLazyLoading,
    initNsfwBlurHandlers, 
    initMetadataPanelHandlers,
    initMediaControlHandlers
} from './MediaUtils.js';
import { generateMetadataPanel } from './MetadataPanel.js';
import { generateImageWrapper, generateVideoWrapper } from './MediaRenderers.js';

/**
 * Load example images asynchronously
 * @param {Array} images - Array of image objects (both regular and custom)
 * @param {string} modelHash - Model hash for fetching local files
 */
export async function loadExampleImages(images, modelHash) {
    try {
        const showcaseTab = document.getElementById('showcase-tab');
        if (!showcaseTab) return;
        
        // First fetch local example files
        let localFiles = [];

        try {
            const endpoint = '/api/example-image-files';
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
        showcaseTab.innerHTML = renderShowcaseContent(images, localFiles);
        
        // Re-initialize the showcase event listeners
        initShowcaseContent(showcaseTab);
        
        // Initialize the example import functionality
        // initExampleImport(modelHash, showcaseTab);
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
 * Render showcase content
 * @param {Array} images - Array of images/videos to show
 * @param {Array} exampleFiles - Local example files
 * @param {boolean} startExpanded - Whether to start in expanded state (unused in new design)
 * @returns {string} HTML content
 */
export function renderShowcaseContent(images, exampleFiles = [], startExpanded = false) {
    if (!images?.length) {
        // Show empty state with import interface
        return renderEmptyShowcase();
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
        return `
            <div class="no-examples">
                <p>All example images are filtered due to NSFW content settings</p>
                <p class="nsfw-filter-info">Your settings are currently set to show only safe-for-work content</p>
                <p>You can change this in Settings <i class="fas fa-cog"></i></p>
            </div>
        `;
    }
    
    // Show hidden content notification if applicable
    const hiddenNotification = hiddenCount > 0 ? 
        `<div class="nsfw-filter-notification">
            <i class="fas fa-eye-slash"></i> ${hiddenCount} ${hiddenCount === 1 ? 'image' : 'images'} hidden due to SFW-only setting
        </div>` : '';
    
    return `
        ${hiddenNotification}
        <div class="showcase-container">
            <div class="thumbnail-sidebar" id="thumbnailSidebar">
                <div class="thumbnail-grid">
                    ${filteredImages.map((img, index) => renderThumbnail(img, index, exampleFiles)).join('')}
                </div>
                ${renderImportInterface()}
            </div>
            <div class="main-display-area">
                <div class="navigation-controls">
                    <button class="nav-btn prev-btn" id="prevBtn" title="Previous (←)">
                        <i class="fas fa-chevron-left"></i>
                    </button>
                    <button class="nav-btn next-btn" id="nextBtn" title="Next (→)">
                        <i class="fas fa-chevron-right"></i>
                    </button>
                    <button class="nav-btn info-btn" id="infoBtn" title="Show/Hide Info (i)">
                        <i class="fas fa-info-circle"></i>
                    </button>
                </div>
                <div class="main-media-container" id="mainMediaContainer">
                    ${filteredImages.length > 0 ? renderMainMediaItem(filteredImages[0], 0, exampleFiles) : ''}
                </div>
            </div>
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
function findLocalFile(img, index, exampleFiles) {
    if (!exampleFiles || exampleFiles.length === 0) return null;
    
    let localFile = null;
    
    if (img.id) {
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
 * Render a thumbnail for the sidebar
 * @param {Object} img - Image/video metadata
 * @param {number} index - Index in the array
 * @param {Array} exampleFiles - Local files
 * @returns {string} HTML for the thumbnail
 */
function renderThumbnail(img, index, exampleFiles) {
    // Find matching file in our list of actual files
    let localFile = findLocalFile(img, index, exampleFiles);
    
    const remoteUrl = img.url || '';
    const localUrl = localFile ? localFile.path : '';
    const isVideo = localFile ? localFile.is_video : 
                  remoteUrl.endsWith('.mp4') || remoteUrl.endsWith('.webm');
    
    // Check if media should be blurred
    const nsfwLevel = img.nsfwLevel !== undefined ? img.nsfwLevel : 0;
    const shouldBlur = state.settings.blurMatureContent && nsfwLevel > NSFW_LEVELS.PG13;
    
    return `
        <div class="thumbnail-item ${index === 0 ? 'active' : ''}" 
             data-index="${index}" 
             data-nsfw-level="${nsfwLevel}"
             data-short-id="${img.id || ''}">
            ${isVideo ? `
                <video class="thumbnail-media lazy ${shouldBlur ? 'blurred' : ''}" 
                       data-local-src="${localUrl || ''}"
                       data-remote-src="${remoteUrl}"
                       muted>
                    <source data-local-src="${localUrl || ''}" data-remote-src="${remoteUrl}" type="video/mp4">
                </video>
                <div class="video-indicator">
                    <i class="fas fa-play"></i>
                </div>
            ` : `
                <img class="thumbnail-media lazy ${shouldBlur ? 'blurred' : ''}" 
                     data-local-src="${localUrl || ''}" 
                     data-remote-src="${remoteUrl}"
                     alt="Thumbnail"
                     width="${img.width}"
                     height="${img.height}">
            `}
            ${shouldBlur ? `
                <div class="thumbnail-nsfw-overlay">
                    <i class="fas fa-eye-slash"></i>
                </div>
            ` : ''}
        </div>
    `;
}

/**
 * Render the main media item in the display area
 * @param {Object} img - Image/video metadata
 * @param {number} index - Index in the array
 * @param {Array} exampleFiles - Local files
 * @returns {string} HTML for the main media item
 */
function renderMainMediaItem(img, index, exampleFiles) {
    // Find matching file in our list of actual files
    let localFile = findLocalFile(img, index, exampleFiles);
    
    const remoteUrl = img.url || '';
    const localUrl = localFile ? localFile.path : '';
    const isVideo = localFile ? localFile.is_video : 
                  remoteUrl.endsWith('.mp4') || remoteUrl.endsWith('.webm');
    
    // Check if media should be blurred
    const nsfwLevel = img.nsfwLevel !== undefined ? img.nsfwLevel : 0;
    const shouldBlur = state.settings.blurMatureContent && nsfwLevel > NSFW_LEVELS.PG13;
    
    // Determine NSFW warning text based on level
    let nsfwText = "Mature Content";
    if (nsfwLevel >= NSFW_LEVELS.XXX) {
        nsfwText = "XXX-rated Content";
    } else if (nsfwLevel >= NSFW_LEVELS.X) {
        nsfwText = "X-rated Content";
    } else if (nsfwLevel >= NSFW_LEVELS.R) {
        nsfwText = "R-rated Content";
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
    const cfgScale = meta.cfgScale || '';
    const clipSkip = meta.clipSkip || '';
    
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
    const isCustomImage = Boolean(img.id);
    
    // Create the media control buttons HTML
    const mediaControlsHtml = `
        <div class="media-controls">
            <button class="media-control-btn set-preview-btn" title="Set as preview">
                <i class="fas fa-image"></i>
            </button>
            <button class="media-control-btn example-delete-btn ${!isCustomImage ? 'disabled' : ''}" 
                    title="${isCustomImage ? 'Delete this example' : 'Only custom images can be deleted'}" 
                    data-short-id="${img.id || ''}" 
                    ${!isCustomImage ? 'disabled' : ''}>
                <i class="fas fa-trash-alt"></i>
                <i class="fas fa-check confirm-icon"></i>
            </button>
        </div>
    `;
    
    // Generate the appropriate wrapper based on media type
    if (isVideo) {
        return generateVideoWrapper(
            img, 100, shouldBlur, nsfwText, metadataPanel, 
            localUrl, remoteUrl, mediaControlsHtml
        );
    }
    
    return generateImageWrapper(
        img, 100, shouldBlur, nsfwText, metadataPanel, 
        localUrl, remoteUrl, mediaControlsHtml
    );
}

/**
 * Render empty showcase with import interface
 * @returns {string} HTML content for empty showcase
 */
function renderEmptyShowcase() {
    return `
        <div class="showcase-container empty">
            <div class="thumbnail-sidebar" id="thumbnailSidebar">
                <div class="thumbnail-grid">
                    <!-- Empty thumbnails grid -->
                </div>
                ${renderImportInterface()}
            </div>
            <div class="main-display-area empty">
                <div class="empty-state">
                    <i class="fas fa-images"></i>
                    <h3>No example images available</h3>
                    <p>Import images or videos using the sidebar</p>
                </div>
            </div>
        </div>
    `;
}

/**
 * Render the import interface for example images
 * @returns {string} HTML content for import interface
 */
function renderImportInterface() {
    return `
        <div class="import-section">
            <button class="select-files-btn" id="selectExampleFilesBtn">
                <i class="fas fa-plus"></i>
                <span>Add Images</span>
            </button>
            <div class="import-drop-zone" id="importDropZone">
                <div class="drop-zone-content">
                    <i class="fas fa-cloud-upload-alt"></i>
                    <span>Drop here</span>
                </div>
            </div>
            <input type="file" id="exampleFilesInput" multiple accept="image/*,video/mp4,video/webm" style="display: none;">
        </div>
    `;
}

/**
 * Initialize all showcase content interactions
 * @param {HTMLElement} showcase - The showcase element
 */
export function initShowcaseContent(showcase) {
    if (!showcase) return;
    
    const container = showcase.querySelector('.showcase-container');
    if (!container) return;
    
    initLazyLoading(container);
    initNsfwBlurHandlers(container);
    initThumbnailNavigation(container);
    initMainDisplayHandlers(container);
    initMediaControlHandlers(container);
    
    // Initialize keyboard navigation
    initKeyboardNavigation(container);
}

/**
 * Initialize thumbnail navigation
 * @param {HTMLElement} container - The showcase container
 */
function initThumbnailNavigation(container) {
    const thumbnails = container.querySelectorAll('.thumbnail-item');
    const mainContainer = container.querySelector('#mainMediaContainer');
    
    if (!mainContainer) return;
    
    thumbnails.forEach((thumbnail, index) => {
        thumbnail.addEventListener('click', () => {
            // Update active thumbnail
            thumbnails.forEach(t => t.classList.remove('active'));
            thumbnail.classList.add('active');
            
            // Get the corresponding image data and render main media
            const showcaseSection = document.querySelector('.showcase-section');
            const modelHash = showcaseSection?.dataset.modelHash;
            
            // This would need access to the filtered images array
            // For now, we'll trigger a re-render of the main display
            updateMainDisplay(index, container);
        });
    });
}

/**
 * Initialize main display handlers including navigation and info toggle
 * @param {HTMLElement} container - The showcase container
 */
function initMainDisplayHandlers(container) {
    const prevBtn = container.querySelector('#prevBtn');
    const nextBtn = container.querySelector('#nextBtn');
    const infoBtn = container.querySelector('#infoBtn');
    
    if (prevBtn) {
        prevBtn.addEventListener('click', () => navigateMedia(container, -1));
    }
    
    if (nextBtn) {
        nextBtn.addEventListener('click', () => navigateMedia(container, 1));
    }
    
    if (infoBtn) {
        infoBtn.addEventListener('click', () => toggleMetadataPanel(container));
    }
    
    // Initialize metadata panel toggle behavior
    initMetadataPanelToggle(container);
}

/**
 * Initialize keyboard navigation
 * @param {HTMLElement} container - The showcase container
 */
function initKeyboardNavigation(container) {
    document.addEventListener('keydown', (e) => {
        // Only handle if showcase is visible and focused
        if (!container.closest('.modal').classList.contains('show')) return;
        
        switch(e.key) {
            case 'ArrowLeft':
                e.preventDefault();
                navigateMedia(container, -1);
                break;
            case 'ArrowRight':
                e.preventDefault();
                navigateMedia(container, 1);
                break;
            case 'i':
            case 'I':
                e.preventDefault();
                toggleMetadataPanel(container);
                break;
        }
    });
}

/**
 * Navigate to previous/next media item
 * @param {HTMLElement} container - The showcase container
 * @param {number} direction - -1 for previous, 1 for next
 */
function navigateMedia(container, direction) {
    const thumbnails = container.querySelectorAll('.thumbnail-item');
    const activeThumbnail = container.querySelector('.thumbnail-item.active');
    
    if (!activeThumbnail || thumbnails.length === 0) return;
    
    const currentIndex = Array.from(thumbnails).indexOf(activeThumbnail);
    let newIndex = currentIndex + direction;
    
    // Wrap around
    if (newIndex < 0) newIndex = thumbnails.length - 1;
    if (newIndex >= thumbnails.length) newIndex = 0;
    
    // Click the new thumbnail to trigger the display update
    thumbnails[newIndex].click();
}

/**
 * Toggle metadata panel visibility
 * @param {HTMLElement} container - The showcase container
 */
function toggleMetadataPanel(container) {
    const metadataPanel = container.querySelector('.image-metadata-panel');
    const infoBtn = container.querySelector('#infoBtn');
    
    if (!metadataPanel || !infoBtn) return;
    
    const isVisible = metadataPanel.classList.contains('visible');
    
    if (isVisible) {
        metadataPanel.classList.remove('visible');
        infoBtn.classList.remove('active');
    } else {
        metadataPanel.classList.add('visible');
        infoBtn.classList.add('active');
    }
}

/**
 * Initialize metadata panel toggle behavior
 * @param {HTMLElement} container - The showcase container
 */
function initMetadataPanelToggle(container) {
    const metadataPanel = container.querySelector('.image-metadata-panel');
    
    if (!metadataPanel) return;
    
    // Handle copy prompt buttons
    const copyBtns = metadataPanel.querySelectorAll('.copy-prompt-btn');
    copyBtns.forEach(copyBtn => {
        const promptIndex = copyBtn.dataset.promptIndex;
        const promptElement = container.querySelector(`#prompt-${promptIndex}`);
        
        copyBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            
            if (!promptElement) return;
            
            try {
                await copyToClipboard(promptElement.textContent, 'Prompt copied to clipboard');
            } catch (err) {
                console.error('Copy failed:', err);
                showToast('Copy failed', 'error');
            }
        });
    });
    
    // Prevent panel scroll from causing modal scroll
    metadataPanel.addEventListener('wheel', (e) => {
        const isAtTop = metadataPanel.scrollTop === 0;
        const isAtBottom = metadataPanel.scrollHeight - metadataPanel.scrollTop === metadataPanel.clientHeight;
        
        if ((e.deltaY < 0 && !isAtTop) || (e.deltaY > 0 && !isAtBottom)) {
            e.stopPropagation();
        }
    }, { passive: true });
}

/**
 * Update main display with new media item
 * @param {number} index - Index of the media to display
 * @param {HTMLElement} container - The showcase container
 */
function updateMainDisplay(index, container) {
    // This function would need to re-render the main display area
    // Implementation depends on how the image data is stored and accessed
    console.log('Update main display to index:', index);
}