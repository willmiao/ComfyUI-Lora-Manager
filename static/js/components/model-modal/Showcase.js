/**
 * Showcase - Left panel for displaying example images
 * Features:
 * - Main image display with navigation
 * - Thumbnail rail for quick switching
 * - Params panel for image metadata
 * - Upload area for custom examples
 * - Keyboard navigation support (← →)
 */

import { escapeHtml } from '../shared/utils.js';
import { translate } from '../../utils/i18nHelpers.js';
import { showToast } from '../../utils/uiHelpers.js';
import { getModelApiClient } from '../../api/modelApiFactory.js';
import { state } from '../../state/index.js';
import { NSFW_LEVELS } from '../../utils/constants.js';
import { getNsfwLevelSelector } from '../shared/NsfwLevelSelector.js';

/**
 * Image Loading Queue - Controls concurrent image loading
 */
class ImageLoadingQueue {
  constructor(maxConcurrent = 3) {
    this.maxConcurrent = maxConcurrent;
    this.running = 0;
    this.queue = [];
  }

  async add(loadFn, priority = 0) {
    return new Promise((resolve, reject) => {
      this.queue.push({ loadFn, resolve, reject, priority });
      this.queue.sort((a, b) => b.priority - a.priority);
      this.process();
    });
  }

  async process() {
    if (this.running >= this.maxConcurrent || this.queue.length === 0) {
      return;
    }

    this.running++;
    const { loadFn, resolve, reject } = this.queue.shift();

    try {
      const result = await loadFn();
      resolve(result);
    } catch (error) {
      reject(error);
    } finally {
      this.running--;
      this.process();
    }
  }
}

/**
 * Image Cache using IndexedDB
 */
class ImageCache {
  constructor() {
    this.dbName = 'LoraManagerImageCache';
    this.storeName = 'images';
    this.db = null;
    this.maxAge = 7 * 24 * 60 * 60 * 1000; // 7 days
    this.maxSize = 500; // Max 500 cached images (~50-100 models worth)
    this.initPromise = this.init();
  }

  async init() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, 1);
      
      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        this.db = request.result;
        resolve(this.db);
      };
      
      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        if (!db.objectStoreNames.contains(this.storeName)) {
          const store = db.createObjectStore(this.storeName, { keyPath: 'url' });
          store.createIndex('timestamp', 'timestamp', { unique: false });
        }
      };
    });
  }

  async get(url) {
    await this.initPromise;
    
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction([this.storeName], 'readonly');
      const store = transaction.objectStore(this.storeName);
      const request = store.get(url);
      
      request.onsuccess = () => {
        const result = request.result;
        if (!result) {
          resolve(null);
          return;
        }
        
        // Check if cache is expired
        const age = Date.now() - result.timestamp;
        if (age > this.maxAge) {
          this.delete(url);
          resolve(null);
          return;
        }
        
        resolve(result.blob);
      };
      
      request.onerror = () => reject(request.error);
    });
  }

  async set(url, blob) {
    await this.initPromise;
    
    // Check current cache size and cleanup if needed
    await this.cleanupIfNeeded();
    
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction([this.storeName], 'readwrite');
      const store = transaction.objectStore(this.storeName);
      
      const request = store.put({
        url,
        blob,
        timestamp: Date.now(),
        size: blob.size
      });
      
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async delete(url) {
    await this.initPromise;
    
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction([this.storeName], 'readwrite');
      const store = transaction.objectStore(this.storeName);
      const request = store.delete(url);
      
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async cleanupIfNeeded() {
    const transaction = this.db.transaction([this.storeName], 'readonly');
    const store = transaction.objectStore(this.storeName);
    const countRequest = store.count();
    
    return new Promise((resolve) => {
      countRequest.onsuccess = async () => {
        if (countRequest.result >= this.maxSize) {
          // Delete oldest 20% of entries
          const index = store.index('timestamp');
          const cursorRequest = index.openCursor();
          const toDelete = [];
          
          cursorRequest.onsuccess = (event) => {
            const cursor = event.target.result;
            if (cursor && toDelete.length < Math.floor(this.maxSize * 0.2)) {
              toDelete.push(cursor.value.url);
              cursor.continue();
            } else {
              // Delete collected entries
              toDelete.forEach(url => this.delete(url));
              resolve();
            }
          };
        } else {
          resolve();
        }
      };
    });
  }

  async clear() {
    await this.initPromise;
    
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction([this.storeName], 'readwrite');
      const store = transaction.objectStore(this.storeName);
      const request = store.clear();
      
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }
}

// Global instances - Optimized for better performance
const imageQueue = new ImageLoadingQueue(6); // Increased from 3 to 6 for faster loading
const imageCache = new ImageCache();

export class Showcase {
  constructor(container) {
    this.element = container;
    this.images = [];
    this.currentIndex = 0;
    this.modelHash = '';
    this.filePath = '';
    this.paramsVisible = false;
    this.uploadAreaVisible = false;
    this.isUploading = false;
    this.localFiles = [];
    this.globalBlurEnabled = true; // Will be initialized based on user settings
    this.isLoading = false; // Track loading state
    
    // Lazy loading observer for thumbnails
    this.thumbnailObserver = null;
  }

  /**
   * Render the showcase
   */
  async render({ images, modelHash, filePath }) {
    this.images = images || [];
    this.modelHash = modelHash || '';
    this.filePath = filePath || '';
    this.currentIndex = 0;
    this.paramsVisible = false;
    this.uploadAreaVisible = false;
    
    // Initialize global blur state based on user settings
    this.globalBlurEnabled = state.settings.blur_mature_content;
    
    // Fetch local example files
    await this.fetchLocalFiles();

    this.element.innerHTML = this.getTemplate();
    this.bindEvents();
    this.initLazyLoading();
    
    if (this.images.length > 0) {
      this.loadImage(0);
    }
  }

  /**
   * Initialize lazy loading for thumbnails using Intersection Observer
   */
  initLazyLoading() {
    // Disconnect existing observer if any
    if (this.thumbnailObserver) {
      this.thumbnailObserver.disconnect();
    }

    // Create new observer
    this.thumbnailObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const img = entry.target;
          const src = img.dataset.src;
          
          if (src) {
            // Load through queue and cache
            this.loadImageWithCache(src, img);
          }
          
          // Stop observing this image
          this.thumbnailObserver.unobserve(img);
        }
      });
    }, {
      root: this.element.querySelector('.thumbnail-rail'),
      rootMargin: '100px', // Start loading 100px before visible
      threshold: 0.1
    });

    // Observe all lazy-load thumbnails
    const lazyImages = this.element.querySelectorAll('img[data-src]');
    lazyImages.forEach(img => this.thumbnailObserver.observe(img));
  }

  /**
   * Load image with caching support
   * @param {string} url - Image URL
   * @param {HTMLImageElement} imgElement - Image element to load into
   */
  async loadImageWithCache(url, imgElement) {
    try {
      // Check cache first
      const cachedBlob = await imageCache.get(url);
      
      if (cachedBlob) {
        // Use cached image
        const objectUrl = URL.createObjectURL(cachedBlob);
        imgElement.src = objectUrl;
        imgElement.classList.add('loaded');
        
        // Clean up object URL after load
        imgElement.onload = () => {
          URL.revokeObjectURL(objectUrl);
        };
        return;
      }

      // Load through queue (limited concurrency) - pass true to use queue
      await this.preloadMedia(url, false, true);
      
      // Set the image src after loading (cache miss case)
      imgElement.src = url;
      imgElement.classList.add('loaded');
    } catch (error) {
      console.error('Failed to load image:', error);
      // Set fallback or error state
      imgElement.classList.add('load-error');
    }
  }

  /**
   * Fetch local example files from the server
   */
  async fetchLocalFiles() {
    if (!this.modelHash) {
      this.localFiles = [];
      return;
    }
    
    try {
      const response = await fetch(`/api/lm/example-image-files?model_hash=${this.modelHash}`);
      const result = await response.json();
      
      if (result.success) {
        this.localFiles = result.files || [];
      } else {
        this.localFiles = [];
      }
    } catch (error) {
      console.error('Failed to fetch local example files:', error);
      this.localFiles = [];
    }
  }

  /**
   * Find the matching local file for an image
   * @param {Object} img - Image metadata
   * @param {number} index - Image index
   * @returns {Object|null} Matching local file or null
   */
  findLocalFile(img, index) {
    if (!this.localFiles || this.localFiles.length === 0) return null;
    
    let localFile = null;
    
    if (typeof img.id === 'string' && img.id) {
      // This is a custom image, find by custom_<id>
      const customPrefix = `custom_${img.id}`;
      localFile = this.localFiles.find(file => file.name.startsWith(customPrefix));
    } else {
      // This is a regular image from civitai, find by index
      localFile = this.localFiles.find(file => {
        const match = file.name.match(/image_(\d+)\./);
        return match && parseInt(match[1]) === index;
      });
    }
    
    return localFile;
  }

  /**
   * Check if media is a video
   * @param {Object} img - Image metadata
   * @param {Object} localFile - Local file object
   * @returns {boolean}
   */
  isVideo(img, localFile) {
    if (localFile) {
      return localFile.is_video;
    }
    const url = img.url || '';
    return url.endsWith('.mp4') || url.endsWith('.webm');
  }

  /**
   * Check if content should be blurred based on NSFW settings
   * @param {number} nsfwLevel - NSFW level of the content
   * @returns {boolean}
   */
  shouldBlurContent(nsfwLevel) {
    return this.globalBlurEnabled && nsfwLevel > NSFW_LEVELS.PG13;
  }

  /**
   * Check if any image in the showcase is NSFW
   * @returns {boolean}
   */
  hasNsfwContent() {
    return this.images.some(img => {
      const level = img.nsfwLevel !== undefined ? img.nsfwLevel : 0;
      return level > NSFW_LEVELS.PG13;
    });
  }

  /**
   * Get NSFW warning text based on level
   * @param {number} nsfwLevel - NSFW level
   * @returns {string}
   */
  getNsfwText(nsfwLevel) {
    if (nsfwLevel >= NSFW_LEVELS.XXX) {
      return 'XXX-rated Content';
    } else if (nsfwLevel >= NSFW_LEVELS.X) {
      return 'X-rated Content';
    } else if (nsfwLevel >= NSFW_LEVELS.R) {
      return 'R-rated Content';
    }
    return 'Mature Content';
  }

  /**
   * Transform Civitai URL to optimized version
   * @param {string} url - Original Civitai URL
   * @param {boolean} isThumbnail - Whether this is for a thumbnail (smaller size)
   * @returns {string} Optimized URL or original URL if not from Civitai
   */
  transformCivitaiUrl(url, isThumbnail = false) {
    if (!url || !url.includes('image.civitai.com')) {
      return url;
    }

    const width = isThumbnail ? '320' : '450';

    if (url.includes('.mp4') || url.includes('.webm')) {
      if (isThumbnail) {
        return url.replace(/\/original=true\/(.*)$/, `/anim=false,transcode=true,width=${width},original=false,optimized=true/$1`);
      } else {
        return url.replace(/\/original=true\/(.*)$/, `/transcode=true,width=${width},optimized=true/$1`);
      }
    } else {
      if (isThumbnail) {
        return url.replace(/\/original=true\/(.*)$/, `/anim=false,width=${width},optimized=true/$1`);
      } else {
        return url.replace(/\/original=true\/(.*)$/, `/width=${width},optimized=true/$1`);
      }
    }
  }

  /**
   * Preload media (image or video) with caching support
   * Main images load immediately without queue to avoid latency
   * @param {string} url - Media URL
   * @param {boolean} isVideo - Whether media is video
   * @param {boolean} useQueue - Whether to use loading queue (thumbnails only)
   * @returns {Promise} Resolves when media is loaded
   */
  async preloadMedia(url, isVideo = false, useQueue = false) {
    // For videos, use standard loading without cache
    if (isVideo) {
      return new Promise((resolve, reject) => {
        const video = document.createElement('video');
        video.preload = 'metadata';
        video.src = url;
        video.addEventListener('loadeddata', () => resolve(url));
        video.addEventListener('error', reject);
      });
    }

    // Check cache first
    const cachedBlob = await imageCache.get(url);
    if (cachedBlob) {
      return url; // Return original URL, will use blob URL when rendering
    }

    const loadImage = async () => {
      return new Promise(async (resolve, reject) => {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.referrerPolicy = 'no-referrer';
        
        img.onload = async () => {
          // Cache the loaded image
          try {
            const response = await fetch(url, {
              credentials: 'omit',
              referrerPolicy: 'no-referrer'
            });
            const blob = await response.blob();
            await imageCache.set(url, blob);
          } catch (cacheError) {
            // Non-fatal: continue even if caching fails
            console.warn('Failed to cache image:', cacheError);
          }
          resolve(url);
        };
        
        img.onerror = reject;
        img.src = url;
      });
    };

    // Main images load immediately without queue to avoid any latency
    // Only thumbnails use queue to prevent network congestion
    if (useQueue) {
      return imageQueue.add(loadImage, 0);
    } else {
      return loadImage();
    }
  }

  /**
   * Render loading skeleton
   * @returns {string} Skeleton HTML
   */
  renderLoadingSkeleton() {
    return `
      <div class="showcase__skeleton">
        <div class="skeleton-animation">
          <i class="fas fa-circle-notch fa-spin skeleton-spinner"></i>
        </div>
      </div>
    `;
  }

  /**
   * Get the HTML template
   */
  getTemplate() {
    const hasImages = this.images.length > 0;
    
    return `
      <div class="showcase__main">
        ${hasImages ? `
          <div class="showcase__image-wrapper">
            <div class="showcase__media-container">
              <!-- Media will be loaded here -->
            </div>
            
            <div class="showcase__counter">
              <span class="showcase__counter-current">1</span>
              <span class="showcase__counter-separator">/</span>
              <span class="showcase__counter-total">${this.images.length}</span>
            </div>
            
            <div class="showcase__controls">
              <button class="showcase__control-btn ${this.hasNsfwContent() ? '' : 'hidden'}" 
                      data-action="toggle-global-blur" 
                      title="${this.globalBlurEnabled ? 'Show content' : 'Blur content'}">
                <i class="fas ${this.globalBlurEnabled ? 'fa-eye' : 'fa-eye-slash'}"></i>
              </button>
              <button class="showcase__control-btn" data-action="toggle-params" title="${translate('modals.model.actions.viewParams', {}, 'View parameters (I)')}">
                <i class="fas fa-info-circle"></i>
              </button>
              <button class="showcase__control-btn showcase__control-btn--primary" data-action="set-preview" title="${translate('modals.model.actions.setPreview', {}, 'Set as preview')}">
                <i class="fas fa-image"></i>
              </button>
              <button class="showcase__control-btn" data-action="set-nsfw" title="${translate('modals.model.actions.setContentRating', {}, 'Set content rating')}">
                <i class="fas fa-exclamation-triangle"></i>
              </button>
              <button class="showcase__control-btn showcase__control-btn--danger" data-action="delete-example" title="${translate('modals.model.actions.delete', {}, 'Delete')}">
                <i class="fas fa-trash-alt"></i>
              </button>
            </div>
            
            <button class="showcase__nav showcase__nav--prev" data-action="prev-image" title="${translate('modals.model.navigation.previous', {}, 'Previous')} (←)">
              <i class="fas fa-chevron-left"></i>
            </button>
            <button class="showcase__nav showcase__nav--next" data-action="next-image" title="${translate('modals.model.navigation.next', {}, 'Next')} (→)">
              <i class="fas fa-chevron-right"></i>
            </button>
            
            <div class="showcase__params">
              <div class="showcase__params-header">
                <span class="showcase__params-title">${translate('modals.model.params.title', {}, 'Generation Parameters')}</span>
                <button class="showcase__params-close" data-action="close-params">
                  <i class="fas fa-times"></i>
                </button>
              </div>
              <div class="showcase__params-content">
                <!-- Params will be populated here -->
              </div>
            </div>
          </div>
        ` : `
          <div class="showcase__empty">
            <i class="fas fa-images"></i>
            <p>${translate('modals.model.examples.empty', {}, 'No example images available')}</p>
            <button class="showcase__add-btn" data-action="add-example">
              <i class="fas fa-plus"></i>
              ${translate('modals.model.examples.addFirst', {}, 'Add your first example')}
            </button>
          </div>
        `}
      </div>
      
      ${this.renderThumbnailRail()}
      ${this.renderUploadArea()}
    `;
  }

  /**
   * Render the thumbnail rail
   */
  renderThumbnailRail() {
    const thumbnails = this.images.map((img, index) => {
      const localFile = this.findLocalFile(img, index);
      const remoteUrl = img.url || img;
      const localUrl = localFile ? localFile.path : '';
      const url = localUrl || this.transformCivitaiUrl(remoteUrl, true);
      const nsfwLevel = img.nsfwLevel !== undefined ? img.nsfwLevel : 0;
      // Check if this specific image needs blur based on global state
      const needsBlur = nsfwLevel > NSFW_LEVELS.PG13;
      const shouldBlur = this.globalBlurEnabled && needsBlur;
      const isVideo = this.isVideo(img, localFile);
      const blurClass = shouldBlur ? 'blurred' : '';
      
      // Smart loading: current index and nearby thumbnails load immediately
      // Others use lazy loading via IntersectionObserver
      const currentIndex = this.currentIndex || 0;
      const preloadRange = 2; // Load current +/- 2 thumbnails immediately
      const shouldPreload = Math.abs(index - currentIndex) <= preloadRange;
      const srcAttr = shouldPreload ? `src="${url}"` : `data-src="${url}"`;
      const loadingClass = shouldPreload ? '' : 'lazy-load';
      
      return `
        <div class="thumbnail-rail__item ${index === currentIndex ? 'active' : ''} ${shouldBlur ? 'thumbnail-rail__item--nsfw-blurred' : ''}" 
             data-index="${index}"
             data-action="select-image"
             data-nsfw-level="${nsfwLevel}">
          ${isVideo ? `
            <div class="thumbnail-rail__video-indicator">
              <i class="fas fa-play-circle"></i>
            </div>
          ` : ''}
          <img ${srcAttr} alt="" class="${blurClass} ${loadingClass}" onload="this.classList.add('loaded')" data-index="${index}">
          ${shouldBlur ? '<span class="thumbnail-rail__nsfw-badge">NSFW</span>' : ''}
        </div>
      `;
    }).join('');

    return `
      <div class="thumbnail-rail">
        ${thumbnails}
        <button class="thumbnail-rail__add" data-action="toggle-upload" title="${translate('modals.model.examples.add', {}, 'Add custom example')}">
          <i class="fas fa-plus"></i>
          <span>${translate('modals.model.examples.add', {}, 'Add')}</span>
        </button>
      </div>
    `;
  }

  /**
   * Render the upload area
   */
  renderUploadArea() {
    return `
      <div class="upload-area ${this.uploadAreaVisible ? 'visible' : ''}">
        <div class="upload-area__content">
          <div class="upload-area__dropzone" data-action="dropzone">
            <input type="file" 
                   class="upload-area__input" 
                   accept="image/*,video/mp4,video/webm" 
                   multiple
                   data-action="file-select">
            <div class="upload-area__placeholder">
              <i class="fas fa-cloud-upload-alt"></i>
              <p class="upload-area__title">${translate('modals.model.examples.dropFiles', {}, 'Drop files here or click to browse')}</p>
              <p class="upload-area__hint">${translate('modals.model.examples.supportedFormats', {}, 'Supports: JPG, PNG, WEBP, MP4, WEBM')}</p>
            </div>
          </div>
          <div class="upload-area__actions">
            <button class="upload-area__cancel" data-action="cancel-upload">
              ${translate('common.actions.cancel', {}, 'Cancel')}
            </button>
          </div>
        </div>
      </div>
    `;
  }

  /**
   * Bind event listeners
   */
  bindEvents() {
    this.element.addEventListener('click', (e) => {
      const target = e.target.closest('[data-action]');
      if (!target) return;

      const action = target.dataset.action;
      
      switch (action) {
        case 'prev-image':
          this.prevImage();
          break;
        case 'next-image':
          this.nextImage();
          break;
        case 'select-image':
          const index = parseInt(target.dataset.index, 10);
          if (!isNaN(index)) {
            this.loadImage(index);
          }
          break;
        case 'toggle-params':
          this.toggleParams();
          break;
        case 'close-params':
          this.hideParams();
          break;
        case 'set-preview':
          this.setAsPreview();
          break;
        case 'set-nsfw':
          this.setContentRating();
          break;
        case 'delete-example':
          this.deleteExample();
          break;
        case 'add-example':
        case 'toggle-upload':
          this.toggleUploadArea();
          break;
        case 'cancel-upload':
          this.hideUploadArea();
          break;
        case 'copy-prompt':
          this.copyPrompt();
          break;
        case 'toggle-blur':
          this.toggleBlur();
          break;
        case 'show-content':
        case 'toggle-global-blur':
          this.toggleGlobalBlur();
          break;
      }
    });

    // File input change
    const fileInput = this.element.querySelector('.upload-area__input');
    if (fileInput) {
      fileInput.addEventListener('change', (e) => {
        this.handleFileSelect(e.target.files);
      });
    }

    // Drag and drop
    const dropzone = this.element.querySelector('.upload-area__dropzone');
    if (dropzone) {
      dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
      });

      dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('dragover');
      });

      dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        this.handleFileSelect(e.dataTransfer.files);
      });

      dropzone.addEventListener('click', () => {
        fileInput?.click();
      });
    }

    // Thumbnail rail horizontal scroll on wheel
    const thumbnailRail = this.element.querySelector('.thumbnail-rail');
    if (thumbnailRail) {
      thumbnailRail.addEventListener('wheel', (e) => {
        e.preventDefault();
        thumbnailRail.scrollLeft += e.deltaY;
      }, { passive: false });
    }

    // Main image navigation on wheel (with threshold to prevent accidental switching)
    const mainImageWrapper = this.element.querySelector('.showcase__image-wrapper');
    if (mainImageWrapper) {
      let wheelAccumulated = 0;
      const WHEEL_THRESHOLD = 150;

      mainImageWrapper.addEventListener('wheel', (e) => {
        // Don't interfere with params panel scrolling
        const paramsPanel = this.element.querySelector('.showcase__params.visible');
        if (paramsPanel && paramsPanel.contains(e.target)) {
          return;
        }

        e.preventDefault();
        wheelAccumulated += e.deltaY;

        if (wheelAccumulated > WHEEL_THRESHOLD) {
          this.nextImage();
          wheelAccumulated = 0;
        } else if (wheelAccumulated < -WHEEL_THRESHOLD) {
          this.prevImage();
          wheelAccumulated = 0;
        }
      }, { passive: false });
    }
  }

  /**
   * Toggle upload area visibility
   */
  toggleUploadArea() {
    this.uploadAreaVisible = !this.uploadAreaVisible;
    const uploadArea = this.element.querySelector('.upload-area');
    if (uploadArea) {
      uploadArea.classList.toggle('visible', this.uploadAreaVisible);
    }
  }

  /**
   * Hide upload area
   */
  hideUploadArea() {
    this.uploadAreaVisible = false;
    const uploadArea = this.element.querySelector('.upload-area');
    if (uploadArea) {
      uploadArea.classList.remove('visible');
    }
  }

  /**
   * Handle file selection
   */
  async handleFileSelect(files) {
    if (!files || files.length === 0) return;
    if (this.isUploading) return;

    this.isUploading = true;
    
    const uploadArea = this.element.querySelector('.upload-area');
    const dropzone = this.element.querySelector('.upload-area__dropzone');
    
    // Show loading state
    if (dropzone) {
      dropzone.innerHTML = `
        <div class="upload-area__uploading">
          <i class="fas fa-spinner fa-spin"></i>
          <p>${translate('modals.model.examples.uploading', {}, 'Uploading...')}</p>
        </div>
      `;
    }

    try {
      for (const file of files) {
        await this.uploadFile(file);
      }
      
      showToast('modals.model.examples.uploadSuccess', {}, 'success');
      this.hideUploadArea();
      
      // Refresh the showcase by reloading model data
      this.refreshShowcase();
    } catch (error) {
      console.error('Failed to upload file:', error);
      showToast('modals.model.examples.uploadFailed', {}, 'error');
      
      // Reset dropzone
      if (dropzone) {
        dropzone.innerHTML = `
          <input type="file" 
                 class="upload-area__input" 
                 accept="image/*,video/mp4,video/webm" 
                 multiple
                 data-action="file-select">
          <div class="upload-area__placeholder">
            <i class="fas fa-cloud-upload-alt"></i>
            <p class="upload-area__title">${translate('modals.model.examples.dropFiles', {}, 'Drop files here or click to browse')}</p>
            <p class="upload-area__hint">${translate('modals.model.examples.supportedFormats', {}, 'Supports: JPG, PNG, WEBP, MP4, WEBM')}</p>
          </div>
        `;
      }
    } finally {
      this.isUploading = false;
    }
  }

  /**
   * Upload a single file
   */
  async uploadFile(file) {
    if (!this.filePath) {
      throw new Error('No file path available');
    }

    // Check file type
    const allowedTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/jpg', 'video/mp4', 'video/webm'];
    if (!allowedTypes.includes(file.type)) {
      throw new Error(`Unsupported file type: ${file.type}`);
    }

    // Check file size (100MB limit)
    const maxSize = 100 * 1024 * 1024;
    if (file.size > maxSize) {
      throw new Error('File too large (max 100MB)');
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('model_path', this.filePath);

    const response = await fetch('/api/lm/upload-example', {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.error || 'Upload failed');
    }

    return response.json();
  }

  /**
   * Refresh showcase after upload
   */
  async refreshShowcase() {
    if (!this.filePath) return;

    try {
      const client = getModelApiClient();
      const metadata = await client.fetchModelMetadata(this.filePath);
      
      if (metadata) {
        const regularImages = metadata.images || [];
        const customImages = metadata.customImages || [];
        const allImages = [...regularImages, ...customImages];
        
        this.images = allImages;
        this.currentIndex = allImages.length - 1;
        
        // Re-fetch local files
        await this.fetchLocalFiles();
        
        // Re-render
        this.element.innerHTML = this.getTemplate();
        this.bindEvents();
        
        // Load the newly uploaded image
        if (this.currentIndex >= 0) {
          this.loadImage(this.currentIndex);
        }
      }
    } catch (error) {
      console.error('Failed to refresh showcase:', error);
    }
  }

  /**
   * Load and display an image by index
   */
  async loadImage(index) {
    if (index < 0 || index >= this.images.length) return;
    
    this.currentIndex = index;
    const image = this.images[index];
    const localFile = this.findLocalFile(image, index);
    const remoteUrl = image.url || image;
    const localUrl = localFile ? localFile.path : '';
    const url = localUrl || this.transformCivitaiUrl(remoteUrl, false);
    const nsfwLevel = image.nsfwLevel !== undefined ? image.nsfwLevel : 0;
    const shouldBlur = this.shouldBlurContent(nsfwLevel);
    const isVideo = this.isVideo(image, localFile);
    const nsfwText = this.getNsfwText(nsfwLevel);
    
    // Update main media container
    const mediaContainer = this.element.querySelector('.showcase__media-container');
    if (mediaContainer) {
      // Show skeleton while loading
      mediaContainer.innerHTML = this.renderLoadingSkeleton();
      
      try {
        // Check cache first for instant display
        let displayUrl = url;
        let objectUrl = null;
        const cachedBlob = !isVideo ? await imageCache.get(url) : null;
        
        if (cachedBlob) {
          // Use cached image immediately
          objectUrl = URL.createObjectURL(cachedBlob);
          displayUrl = objectUrl;
          
          // Render with cached image
          mediaContainer.innerHTML = this.renderMediaElement(displayUrl, isVideo, shouldBlur, nsfwText, nsfwLevel);
          
          // Trigger fade-in animation
          const media = mediaContainer.querySelector('.showcase__media');
          if (media) {
            requestAnimationFrame(() => {
              media.classList.add('loaded');
            });
          }
        } else {
          // Preload media (will cache it)
          await this.preloadMedia(url, isVideo);
          
          // Try to get from cache after loading
          const newlyCachedBlob = !isVideo ? await imageCache.get(url) : null;
          if (newlyCachedBlob) {
            objectUrl = URL.createObjectURL(newlyCachedBlob);
            displayUrl = objectUrl;
          }
          
          // Render media with fade-in effect
          mediaContainer.innerHTML = this.renderMediaElement(displayUrl, isVideo, shouldBlur, nsfwText, nsfwLevel);
          
          // Trigger fade-in animation
          const media = mediaContainer.querySelector('.showcase__media');
          if (media) {
            requestAnimationFrame(() => {
              media.classList.add('loaded');
            });
          }
        }
        
        // Clean up object URL when image loads (for next navigation)
        if (objectUrl) {
          const media = mediaContainer.querySelector('.showcase__media');
          if (media) {
            media.onload = () => {
              URL.revokeObjectURL(objectUrl);
            };
          }
        }
      } catch (error) {
        console.error('Failed to load media:', error);
        mediaContainer.innerHTML = `
          <div class="showcase__error">
            <i class="fas fa-exclamation-triangle"></i>
            <p>${translate('modals.model.examples.loadError', {}, 'Failed to load media')}</p>
          </div>
        `;
      }
    }
    
    // Update global blur toggle button visibility
    const blurToggleBtn = this.element.querySelector('[data-action="toggle-global-blur"]');
    if (blurToggleBtn) {
      const hasNsfw = this.hasNsfwContent();
      blurToggleBtn.classList.toggle('hidden', !hasNsfw);
    }

    // Update thumbnail rail active state
    this.element.querySelectorAll('.thumbnail-rail__item').forEach((item, i) => {
      item.classList.toggle('active', i === index);
    });

    // Update counter
    this.updateCounter();

    // Update params
    this.updateParams(image);
  }

  /**
   * Update image counter display
   */
  updateCounter() {
    const counterCurrent = this.element.querySelector('.showcase__counter-current');
    const counterTotal = this.element.querySelector('.showcase__counter-total');
    if (counterCurrent) {
      counterCurrent.textContent = this.currentIndex + 1;
    }
    if (counterTotal) {
      counterTotal.textContent = this.images.length;
    }
  }

  /**
   * Render media element (image or video)
   */
  renderMediaElement(url, isVideo, shouldBlur, nsfwText, nsfwLevel) {
    const blurClass = shouldBlur ? 'blurred' : '';
    
    const mediaHtml = isVideo ? `
      <video controls autoplay muted loop crossorigin="anonymous" 
             referrerpolicy="no-referrer" 
             class="showcase__media ${blurClass}">
        <source src="${url}" type="video/mp4">
        Your browser does not support video playback
      </video>
    ` : `
      <img src="${url}" 
           alt="${translate('modals.model.examples.title', {}, 'Example')}" 
           class="showcase__media ${blurClass}">
    `;
    
    const nsfwOverlay = shouldBlur ? `
      <div class="showcase__nsfw-notice">
        <div class="showcase__nsfw-notice-content">
          <p class="showcase__nsfw-notice-text">${nsfwText}</p>
          <button class="showcase__nsfw-show-btn" data-action="show-content">
            <i class="fas fa-eye"></i> ${translate('common.show', {}, 'Show')}
          </button>
        </div>
      </div>
    ` : '';
    
    return `
      <div class="showcase-media-wrapper ${shouldBlur ? 'nsfw-media-wrapper' : ''}" data-nsfw-level="${nsfwLevel}">
        <div class="showcase__media-inner">
          ${mediaHtml}
          ${nsfwOverlay}
        </div>
      </div>
    `;
  }

  /**
   * Toggle global blur state for all images in the showcase
   */
  toggleGlobalBlur() {
    this.globalBlurEnabled = !this.globalBlurEnabled;
    
    // Update the toggle button
    const toggleBtn = this.element.querySelector('[data-action="toggle-global-blur"]');
    if (toggleBtn) {
      const icon = toggleBtn.querySelector('i');
      if (icon) {
        icon.className = `fas ${this.globalBlurEnabled ? 'fa-eye' : 'fa-eye-slash'}`;
      }
      toggleBtn.title = this.globalBlurEnabled ? 'Show content' : 'Blur content';
    }
    
    // Update main image
    this.updateMainImageBlur();
    
    // Update all thumbnails
    this.updateAllThumbnailsBlur();
  }

  /**
   * Update main image blur state based on global setting
   */
  updateMainImageBlur() {
    const mediaContainer = this.element.querySelector('.showcase__media-container');
    if (!mediaContainer) return;
    
    const media = mediaContainer.querySelector('.showcase__media');
    const overlay = mediaContainer.querySelector('.showcase__nsfw-notice');
    const currentImage = this.images[this.currentIndex];
    
    if (!media || !currentImage) return;
    
    const nsfwLevel = currentImage.nsfwLevel !== undefined ? currentImage.nsfwLevel : 0;
    const shouldBlur = this.globalBlurEnabled && nsfwLevel > NSFW_LEVELS.PG13;
    
    media.classList.toggle('blurred', shouldBlur);
    if (overlay) {
      overlay.style.display = shouldBlur ? 'block' : 'none';
    }
  }

  /**
   * Update all thumbnails blur state based on global setting
   */
  updateAllThumbnailsBlur() {
    this.element.querySelectorAll('.thumbnail-rail__item').forEach((item, index) => {
      const img = item.querySelector('img');
      const badge = item.querySelector('.thumbnail-rail__nsfw-badge');
      const image = this.images[index];
      
      if (!image) return;
      
      const nsfwLevel = image.nsfwLevel !== undefined ? image.nsfwLevel : 0;
      const needsBlur = nsfwLevel > NSFW_LEVELS.PG13;
      const shouldBlur = this.globalBlurEnabled && needsBlur;
      
      // Update item class
      item.classList.toggle('thumbnail-rail__item--nsfw-blurred', shouldBlur);
      
      // Update image blur
      if (img) {
        img.classList.toggle('blurred', shouldBlur);
      }
      
      // Update badge visibility
      if (needsBlur) {
        if (shouldBlur && !badge) {
          item.insertAdjacentHTML('beforeend', '<span class="thumbnail-rail__nsfw-badge">NSFW</span>');
        } else if (!shouldBlur && badge) {
          badge.remove();
        }
      }
    });
  }

  /**
   * Navigate to previous image
   */
  prevImage() {
    if (this.images.length === 0) return;
    const newIndex = this.currentIndex > 0 ? this.currentIndex - 1 : this.images.length - 1;
    this.loadImage(newIndex);
  }

  /**
   * Navigate to next image
   */
  nextImage() {
    if (this.images.length === 0) return;
    const newIndex = this.currentIndex < this.images.length - 1 ? this.currentIndex + 1 : 0;
    this.loadImage(newIndex);
  }

  /**
   * Toggle params panel visibility
   */
  toggleParams() {
    this.paramsVisible = !this.paramsVisible;
    const panel = this.element.querySelector('.showcase__params');
    if (panel) {
      panel.classList.toggle('visible', this.paramsVisible);
    }
  }

  /**
   * Hide params panel
   */
  hideParams() {
    this.paramsVisible = false;
    const panel = this.element.querySelector('.showcase__params');
    if (panel) {
      panel.classList.remove('visible');
    }
  }

  /**
   * Update params panel content
   */
  updateParams(image) {
    const content = this.element.querySelector('.showcase__params-content');
    if (!content) return;

    const meta = image.meta || {};
    const prompt = meta.prompt || '';
    const negativePrompt = meta.negativePrompt || '';
    
    // Build params display
    let html = '';
    
    if (prompt) {
      html += this.renderPromptSection(
        translate('modals.model.params.prompt', {}, 'Prompt'),
        prompt,
        'prompt'
      );
    }
    
    if (negativePrompt) {
      html += this.renderPromptSection(
        translate('modals.model.params.negativePrompt', {}, 'Negative Prompt'),
        negativePrompt,
        'negative'
      );
    }

    // Add parameter tags
    const params = [];
    if (meta.sampler) params.push({ name: 'Sampler', value: meta.sampler });
    if (meta.steps) params.push({ name: 'Steps', value: meta.steps });
    if (meta.cfgScale) params.push({ name: 'CFG', value: meta.cfgScale });
    if (meta.seed) params.push({ name: 'Seed', value: meta.seed });
    if (meta.size) params.push({ name: 'Size', value: meta.size });

    if (params.length > 0) {
      html += '<div class="params-tags">';
      params.forEach(param => {
        html += `
          <span class="param-tag">
            <span class="param-name">${escapeHtml(param.name)}:</span>
            <span class="param-value">${escapeHtml(String(param.value))}</span>
          </span>
        `;
      });
      html += '</div>';
    }

    if (!prompt && !negativePrompt && params.length === 0) {
      html = `<div class="no-metadata-message">
        <i class="fas fa-info-circle"></i>
        ${translate('modals.model.params.noData', {}, 'No generation data available')}
      </div>`;
    }

    content.innerHTML = html;
  }

  /**
   * Render a prompt section
   */
  renderPromptSection(label, text, type) {
    return `
      <div class="showcase__prompt">
        <div class="showcase__prompt-label">${escapeHtml(label)}</div>
        <div class="showcase__prompt-text">${escapeHtml(text)}</div>
        <button class="showcase__prompt-copy" data-action="copy-prompt" data-type="${type}" title="${translate('common.copy', {}, 'Copy')}">
          <i class="fas fa-copy"></i>
        </button>
      </div>
    `;
  }

  /**
   * Copy current prompt to clipboard
   */
  async copyPrompt() {
    const image = this.images[this.currentIndex];
    if (!image) return;

    const meta = image.meta || {};
    const prompt = meta.prompt || '';
    
    if (!prompt) return;

    try {
      await navigator.clipboard.writeText(prompt);
      showToast('modals.model.params.promptCopied', {}, 'success');
    } catch (err) {
      console.error('Failed to copy prompt:', err);
    }
  }

  /**
   * Set current image as model preview
   */
  async setAsPreview() {
    const image = this.images[this.currentIndex];
    if (!image || !this.filePath) return;

    const localFile = this.findLocalFile(image, this.currentIndex);
    const remoteUrl = image.url || image;
    const localUrl = localFile ? localFile.path : '';
    const url = localUrl || remoteUrl;
    const nsfwLevel = image.nsfwLevel !== undefined ? image.nsfwLevel : 0;
    
    try {
      // Fetch the image/video as a blob
      const response = await fetch(url);
      const blob = await response.blob();
      const file = new File([blob], 'preview.jpg', { type: blob.type });
      
      const client = getModelApiClient();
      await client.uploadPreview(this.filePath, file, nsfwLevel);
      
      showToast('modals.model.actions.previewSet', {}, 'success');
    } catch (err) {
      console.error('Failed to set preview:', err);
      showToast('modals.model.actions.previewFailed', {}, 'error');
    }
  }

  /**
   * Set content rating for current example
   */
  async setContentRating() {
    const image = this.images[this.currentIndex];
    if (!image || !this.modelHash) return;

    const selector = getNsfwLevelSelector();
    if (!selector) {
      console.warn('NSFW selector not available');
      return;
    }

    const currentLevel = image.nsfwLevel !== undefined ? image.nsfwLevel : 0;
    const isCustomImage = Boolean(typeof image.id === 'string' && image.id);
    const mediaIndex = this.currentIndex;
    const mediaId = image.id || '';

    selector.show({
      currentLevel,
      onSelect: async (level) => {
        try {
          const payload = {
            model_hash: this.modelHash,
            nsfw_level: level,
            source: isCustomImage ? 'custom' : 'civitai',
          };

          if (isCustomImage) {
            payload.id = mediaId;
          } else {
            payload.index = mediaIndex;
          }

          const response = await fetch('/api/lm/example-images/set-nsfw-level', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
          });

          const result = await response.json();
          if (!result.success) {
            throw new Error(result.error || 'Failed to update NSFW level');
          }

          // Update the image in our local array
          image.nsfwLevel = level;
          
          // Re-render to apply the new blur state
          this.loadImage(this.currentIndex);
          
          // Update thumbnail rail to reflect the change
          const thumbnail = this.element.querySelector(`.thumbnail-rail__item[data-index="${this.currentIndex}"]`);
          if (thumbnail) {
            const shouldBlur = this.shouldBlurContent(level);
            thumbnail.classList.toggle('thumbnail-rail__item--nsfw-blurred', shouldBlur);
            thumbnail.dataset.nsfwLevel = level;
            const thumbImg = thumbnail.querySelector('img');
            if (thumbImg) {
              thumbImg.classList.toggle('blurred', shouldBlur);
            }
            const badge = thumbnail.querySelector('.thumbnail-rail__nsfw-badge');
            if (shouldBlur && !badge) {
              thumbnail.insertAdjacentHTML('beforeend', '<span class="thumbnail-rail__nsfw-badge">NSFW</span>');
            } else if (!shouldBlur && badge) {
              badge.remove();
            }
          }
          
          showToast('toast.contextMenu.contentRatingSet', { level }, 'success');
          return true;
        } catch (error) {
          console.error('Error updating NSFW level:', error);
          showToast('toast.contextMenu.contentRatingFailed', { message: error.message }, 'error');
          return false;
        }
      },
    });
  }

  /**
   * Delete current example
   */
  async deleteExample() {
    const image = this.images[this.currentIndex];
    if (!image || !this.filePath) return;

    const url = image.url || image;
    const isCustom = image.isCustom || false;
    
    // Confirm deletion
    const confirmed = confirm(translate('modals.model.examples.confirmDelete', {}, 'Delete this example image?'));
    if (!confirmed) return;

    try {
      const response = await fetch('/api/lm/delete-example', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model_path: this.filePath,
          image_url: url,
          is_custom: isCustom
        })
      });

      if (!response.ok) {
        throw new Error('Failed to delete example');
      }

      showToast('modals.model.examples.deleted', {}, 'success');
      
      // Remove from local array and refresh
      this.images.splice(this.currentIndex, 1);
      if (this.currentIndex >= this.images.length) {
        this.currentIndex = Math.max(0, this.images.length - 1);
      }
      
      // Re-render
      this.element.innerHTML = this.getTemplate();
      this.bindEvents();
      
      if (this.images.length > 0) {
        this.loadImage(this.currentIndex);
      }
    } catch (err) {
      console.error('Failed to delete example:', err);
      showToast('modals.model.examples.deleteFailed', {}, 'error');
    }
  }

  /**
   * Clean up resources when component is destroyed
   */
  destroy() {
    // Disconnect lazy loading observer
    if (this.thumbnailObserver) {
      this.thumbnailObserver.disconnect();
      this.thumbnailObserver = null;
    }
  }
}
