/**
 * MediaUtils.js
 * Media-specific utility functions for showcase components
 * (Moved from uiHelpers.js to better organize code)
 */
import { showToast, copyToClipboard } from '../../../utils/uiHelpers.js';
import { state } from '../../../state/index.js';
import { getModelApiClient } from '../../../api/baseModelApi.js';

/**
 * Try to load local image first, fall back to remote if local fails
 * @param {HTMLImageElement} imgElement - The image element to update
 * @param {Object} urls - Object with local URLs {primary, fallback} and remote URL
 */
export function tryLocalImageOrFallbackToRemote(imgElement, urls) {
    const { primary: localUrl, fallback: fallbackUrl } = urls.local || {};
    const remoteUrl = urls.remote;
    
    // If no local options, use remote directly
    if (!localUrl) {
        imgElement.src = remoteUrl;
        return;
    }
    
    // Try primary local URL
    const testImg = new Image();
    testImg.onload = () => {
        // Primary local image loaded successfully
        imgElement.src = localUrl;
    };
    testImg.onerror = () => {
        // Try fallback URL if available
        if (fallbackUrl) {
            const fallbackImg = new Image();
            fallbackImg.onload = () => {
                imgElement.src = fallbackUrl;
            };
            fallbackImg.onerror = () => {
                // Both local options failed, use remote
                imgElement.src = remoteUrl;
            };
            fallbackImg.src = fallbackUrl;
        } else {
            // No fallback, use remote
            imgElement.src = remoteUrl;
        }
    };
    testImg.src = localUrl;
}

/**
 * Try to load local video first, fall back to remote if local fails
 * @param {HTMLVideoElement} videoElement - The video element to update
 * @param {Object} urls - Object with local URLs {primary} and remote URL
 */
export function tryLocalVideoOrFallbackToRemote(videoElement, urls) {
    const { primary: localUrl } = urls.local || {};
    const remoteUrl = urls.remote;
    
    // Only try local if we have a local path
    if (localUrl) {
        // Try to fetch local file headers to see if it exists
        fetch(localUrl, { method: 'HEAD' })
            .then(response => {
                if (response.ok) {
                    // Local video exists, use it
                    videoElement.src = localUrl;
                    const source = videoElement.querySelector('source');
                    if (source) source.src = localUrl;
                } else {
                    // Local video doesn't exist, use remote
                    videoElement.src = remoteUrl;
                    const source = videoElement.querySelector('source');
                    if (source) source.src = remoteUrl;
                }
                videoElement.load();
            })
            .catch(() => {
                // Error fetching, use remote
                videoElement.src = remoteUrl;
                const source = videoElement.querySelector('source');
                if (source) source.src = remoteUrl;
                videoElement.load();
            });
    } else {
        // No local path, use remote directly
        videoElement.src = remoteUrl;
        const source = videoElement.querySelector('source');
        if (source) source.src = remoteUrl;
        videoElement.load();
    }
}

/**
 * Initialize lazy loading for images and videos in a container
 * @param {HTMLElement} container - The container with lazy-loadable elements
 */
export function initLazyLoading(container) {
    const lazyElements = container.querySelectorAll('.lazy');
    
    const lazyLoad = (element) => {
        // Get URLs from data attributes
        const localUrls = {
            primary: element.dataset.localSrc || null,
            fallback: element.dataset.localFallbackSrc || null
        };
        const remoteUrl = element.dataset.remoteSrc;
        
        const urls = {
            local: localUrls,
            remote: remoteUrl
        };
        
        // Check if element is a video or image
        if (element.tagName.toLowerCase() === 'video') {
            tryLocalVideoOrFallbackToRemote(element, urls);
        } else {
            tryLocalImageOrFallbackToRemote(element, urls);
        }
        
        element.classList.remove('lazy');
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                lazyLoad(entry.target);
                observer.unobserve(entry.target);
            }
        });
    });

    lazyElements.forEach(element => observer.observe(element));
}

/**
 * Get the actual rendered rectangle of a media element with object-fit: contain
 * @param {HTMLElement} mediaElement - The img or video element
 * @param {number} containerWidth - Width of the container
 * @param {number} containerHeight - Height of the container
 * @returns {Object} - Rect with left, top, right, bottom coordinates
 */
export function getRenderedMediaRect(mediaElement, containerWidth, containerHeight) {
    // Get natural dimensions of the media
    const naturalWidth = mediaElement.naturalWidth || mediaElement.videoWidth || mediaElement.clientWidth;
    const naturalHeight = mediaElement.naturalHeight || mediaElement.videoHeight || mediaElement.clientHeight;
    
    if (!naturalWidth || !naturalHeight) {
        // Fallback if dimensions cannot be determined
        return { left: 0, top: 0, right: containerWidth, bottom: containerHeight };
    }
    
    // Calculate aspect ratios
    const containerRatio = containerWidth / containerHeight;
    const mediaRatio = naturalWidth / naturalHeight;
    
    let renderedWidth, renderedHeight, left = 0, top = 0;
    
    // Apply object-fit: contain logic
    if (containerRatio > mediaRatio) {
        // Container is wider than media - will have empty space on sides
        renderedHeight = containerHeight;
        renderedWidth = renderedHeight * mediaRatio;
        left = (containerWidth - renderedWidth) / 2;
    } else {
        // Container is taller than media - will have empty space top/bottom
        renderedWidth = containerWidth;
        renderedHeight = renderedWidth / mediaRatio;
        top = (containerHeight - renderedHeight) / 2;
    }
    
    return {
        left,
        top,
        right: left + renderedWidth,
        bottom: top + renderedHeight
    };
}

/**
 * Initialize metadata panel interaction handlers
 * @param {HTMLElement} container - Container element with media wrappers
 */
export function initMetadataPanelHandlers(container) {
    // Metadata panel interaction is now handled by the info button
    // Keep the existing copy functionality but remove hover-based visibility
    const metadataPanel = container.querySelector('.image-metadata-panel');
    
    if (metadataPanel) {
        // Prevent events from bubbling
        metadataPanel.addEventListener('click', (e) => {
            e.stopPropagation();
        });
        
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
}

/**
 * Initialize NSFW content blur toggle handlers
 * @param {HTMLElement} container - Container element with media wrappers
 */
export function initNsfwBlurHandlers(container) {
    // Handle toggle blur buttons
    const toggleButtons = container.querySelectorAll('.toggle-blur-btn');
    toggleButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const wrapper = btn.closest('.media-wrapper');
            const media = wrapper.querySelector('img, video');
            const isBlurred = media.classList.toggle('blurred');
            const icon = btn.querySelector('i');
            
            // Update the icon based on blur state
            if (isBlurred) {
                icon.className = 'fas fa-eye';
            } else {
                icon.className = 'fas fa-eye-slash';
            }
            
            // Toggle the overlay visibility
            const overlay = wrapper.querySelector('.nsfw-overlay');
            if (overlay) {
                overlay.style.display = isBlurred ? 'flex' : 'none';
            }
        });
    });
    
    // Handle "Show" buttons in overlays
    const showButtons = container.querySelectorAll('.show-content-btn');
    showButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const wrapper = btn.closest('.media-wrapper');
            const media = wrapper.querySelector('img, video');
            media.classList.remove('blurred');
            
            // Update the toggle button icon
            const toggleBtn = wrapper.querySelector('.toggle-blur-btn');
            if (toggleBtn) {
                toggleBtn.querySelector('i').className = 'fas fa-eye-slash';
            }
            
            // Hide the overlay
            const overlay = wrapper.querySelector('.nsfw-overlay');
            if (overlay) {
                overlay.style.display = 'none';
            }
        });
    });
}

/**
 * Initialize media control buttons event handlers
 * @param {HTMLElement} container - Container with media wrappers
 */
export function initMediaControlHandlers(container) {
    // Find all delete buttons in the container
    const deleteButtons = container.querySelectorAll('.example-delete-btn');
    
    deleteButtons.forEach(btn => {
        // Set initial state
        btn.dataset.state = 'initial';
        
        btn.addEventListener('click', async function(e) {
            e.stopPropagation();
            
            if (this.classList.contains('disabled')) {
                return;
            }
            
            const shortId = this.dataset.shortId;
            const btnState = this.dataset.state;
            
            if (!shortId) return;
            
            if (btnState === 'initial') {
                this.dataset.state = 'confirm';
                this.classList.add('confirm');
                this.title = 'Click again to confirm deletion';
                
                setTimeout(() => {
                    if (this.dataset.state === 'confirm') {
                        this.dataset.state = 'initial';
                        this.classList.remove('confirm');
                        this.title = 'Delete this example';
                    }
                }, 3000);
                
                return;
            }
            
            if (btnState === 'confirm') {
                this.disabled = true;
                this.classList.remove('confirm');
                this.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                
                const mediaWrapper = this.closest('.media-wrapper');
                const modelHashAttr = document.querySelector('.showcase-section')?.dataset;
                const modelHash = modelHashAttr?.modelHash;
                
                try {
                    const response = await fetch('/api/delete-example-image', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            model_hash: modelHash,
                            short_id: shortId
                        })
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        // Remove the corresponding thumbnail and update main display
                        const thumbnailItem = container.querySelector(`.thumbnail-item[data-short-id="${shortId}"]`);
                        if (thumbnailItem) {
                            const wasActive = thumbnailItem.classList.contains('active');
                            thumbnailItem.remove();
                            
                            // If the deleted item was active, select next item
                            if (wasActive) {
                                const remainingThumbnails = container.querySelectorAll('.thumbnail-item');
                                if (remainingThumbnails.length > 0) {
                                    remainingThumbnails[0].click();
                                } else {
                                    // No more items, show empty state
                                    const mainContainer = container.querySelector('#mainMediaContainer');
                                    if (mainContainer) {
                                        mainContainer.innerHTML = `
                                            <div class="empty-state">
                                                <i class="fas fa-images"></i>
                                                <h3>No example images available</h3>
                                                <p>Import images or videos using the sidebar</p>
                                            </div>
                                        `;
                                    }
                                }
                            }
                        }
                        
                        showToast('Example image deleted', 'success');

                        const updateData = {
                            civitai: {
                                customImages: result.custom_images || []
                            }
                        };
                        
                        state.virtualScroller.updateSingleItem(result.model_file_path, updateData);
                    } else {
                        showToast(result.error || 'Failed to delete example image', 'error');
                        
                        this.disabled = false;
                        this.dataset.state = 'initial';
                        this.classList.remove('confirm');
                        this.innerHTML = '<i class="fas fa-trash-alt"></i>';
                        this.title = 'Delete this example';
                    }
                } catch (error) {
                    console.error('Error deleting example image:', error);
                    showToast('Failed to delete example image', 'error');
                    
                    this.disabled = false;
                    this.dataset.state = 'initial';
                    this.classList.remove('confirm');
                    this.innerHTML = '<i class="fas fa-trash-alt"></i>';
                    this.title = 'Delete this example';
                }
            }
        });
    });
    
    initSetPreviewHandlers(container);
}

/**
 * Initialize set preview button handlers
 * @param {HTMLElement} container - Container with media wrappers
 */
function initSetPreviewHandlers(container) {
    const previewButtons = container.querySelectorAll('.set-preview-btn');
    const modelType = state.currentPageType == 'loras' ? 'lora' : 'checkpoint';
    
    previewButtons.forEach(btn => {
        btn.addEventListener('click', async function(e) {
            e.stopPropagation();
            
            // Show loading state
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            this.disabled = true;
            
            try {
                // Get the model file path from showcase section data attribute
                const showcaseSection = document.querySelector('.showcase-section');
                const modelHash = showcaseSection?.dataset.modelHash;
                const modelFilePath = showcaseSection?.dataset.filepath;
                
                if (!modelFilePath) {
                    throw new Error('Could not determine model file path');
                }
                
                // Get the media wrapper and media element
                const mediaWrapper = this.closest('.media-wrapper');
                const mediaElement = mediaWrapper.querySelector('img, video');
                
                if (!mediaElement) {
                    throw new Error('Media element not found');
                }
                
                // Get NSFW level from the wrapper or media element
                const nsfwLevel = parseInt(mediaWrapper.dataset.nsfwLevel || mediaElement.dataset.nsfwLevel || '0', 10);
                
                // Get local file path if available
                const useLocalFile = mediaElement.dataset.localSrc && !mediaElement.dataset.localSrc.includes('undefined');
                const apiClient = getModelApiClient();
                
                if (useLocalFile) {
                    // We have a local file, use it directly
                    const response = await fetch(mediaElement.dataset.localSrc);
                    const blob = await response.blob();
                    const file = new File([blob], 'preview.jpg', { type: blob.type });
                    
                    // Use the existing baseModelApi uploadPreview method with nsfw level
                    await apiClient.uploadPreview(modelFilePath, file, modelType, nsfwLevel);
                } else {
                    // We need to download the remote file first
                    const response = await fetch(mediaElement.src);
                    const blob = await response.blob();
                    const file = new File([blob], 'preview.jpg', { type: blob.type });
                    
                    // Use the existing baseModelApi uploadPreview method with nsfw level
                    await apiClient.uploadPreview(modelFilePath, file, modelType, nsfwLevel);
                }
            } catch (error) {
                console.error('Error setting preview:', error);
                showToast('Failed to set preview image', 'error');
            } finally {
                // Restore button state
                this.innerHTML = '<i class="fas fa-image"></i>';
                this.disabled = false;
            }
        });
    });
}