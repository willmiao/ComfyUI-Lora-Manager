import { updateService } from '../managers/UpdateService.js';
import { toggleTheme } from '../utils/uiHelpers.js';
import { SearchManager } from '../managers/SearchManager.js';
import { FilterManager } from '../managers/FilterManager.js';
import { initPageState } from '../state/index.js';
import { getStorageItem } from '../utils/storageHelpers.js';
import { updateSearchPlaceholder } from '../utils/i18nHelpers.js';

/**
 * Header.js - Manages the application header behavior across different pages
 * Handles initialization of appropriate search and filter managers based on current page
 */
export class HeaderManager {
    constructor() {
      this.currentPage = this.detectCurrentPage();
      initPageState(this.currentPage);
      this.searchManager = null;
      this.filterManager = null;
      
      // Initialize appropriate managers based on current page
      if (this.currentPage !== 'statistics') {
        this.initializeManagers();
      }
      
      // Set up common header functionality
      this.initializeCommonElements();
    }
    
    detectCurrentPage() {
      const path = window.location.pathname;
      if (path.includes('/loras/recipes')) return 'recipes';
      if (path.includes('/checkpoints')) return 'checkpoints';
      if (path.includes('/embeddings')) return 'embeddings';
      if (path.includes('/statistics')) return 'statistics';
      if (path.includes('/loras')) return 'loras';
      return 'unknown';
    }
    
    initializeManagers() {
      // Initialize SearchManager for all page types
      this.searchManager = new SearchManager({ page: this.currentPage });
      window.searchManager = this.searchManager;
      
      this.filterManager = new FilterManager({ page: this.currentPage });
      window.filterManager = this.filterManager;
    }
    
    initializeCommonElements() {
      // Handle theme toggle
      const themeToggle = document.querySelector('.theme-toggle');
      if (themeToggle) {
        // Set initial state based on current theme
        const currentTheme = getStorageItem('theme') || 'auto';
        themeToggle.classList.add(`theme-${currentTheme}`);
        
        // Set initial tooltip text
        this.updateThemeTooltip(themeToggle, currentTheme);
        
        themeToggle.addEventListener('click', () => {
          if (typeof toggleTheme === 'function') {
            const newTheme = toggleTheme();
            // Update tooltip based on next toggle action
            this.updateThemeTooltip(themeToggle, newTheme);
          }
        });
      }
      
      // Handle settings toggle
      const settingsToggle = document.querySelector('.settings-toggle');
      if (settingsToggle) {
        settingsToggle.addEventListener('click', () => {
          if (window.settingsManager) {
            window.settingsManager.toggleSettings();
          }
        });
      }
      
      // Handle update toggle
      const updateToggle = document.getElementById('updateToggleBtn');
      if (updateToggle) {
        updateToggle.addEventListener('click', () => {
          updateService.toggleUpdateModal();
        });
      }
      
      // Handle support toggle
      const supportToggle = document.getElementById('supportToggleBtn');
      if (supportToggle) {
        supportToggle.addEventListener('click', () => {
          if (window.modalManager) {
            window.modalManager.toggleModal('supportModal');
          }
        });
      }

      // Handle QR code toggle
      const qrToggle = document.getElementById('toggleQRCode');
      const qrContainer = document.getElementById('qrCodeContainer');
      
      if (qrToggle && qrContainer) {
          qrToggle.addEventListener('click', function() {
              qrContainer.classList.toggle('show');
              qrToggle.classList.toggle('active');
              
              const toggleText = qrToggle.querySelector('.toggle-text');
              if (qrContainer.classList.contains('show')) {
                  toggleText.textContent = 'Hide WeChat QR Code';
                  // Add small delay to ensure DOM is updated before scrolling
                  setTimeout(() => {
                      const supportModal = document.querySelector('.support-modal');
                      if (supportModal) {
                          supportModal.scrollTo({
                              top: supportModal.scrollHeight,
                              behavior: 'smooth'
                          });
                      }
                  }, 250);
              } else {
                  toggleText.textContent = 'Show WeChat QR Code';
              }
          });
      }
      
      // Hide search functionality on Statistics page
      this.updateHeaderForPage();
    }
    
    updateHeaderForPage() {
      const headerSearch = document.getElementById('headerSearch');
      
      if (this.currentPage === 'statistics' && headerSearch) {
        headerSearch.classList.add('disabled');
        // Disable search functionality
        const searchInput = headerSearch.querySelector('#searchInput');
        const searchButtons = headerSearch.querySelectorAll('button');
        if (searchInput) {
          searchInput.disabled = true;
          searchInput.placeholder = window.i18n?.t('header.search.notAvailable') || 'Search not available on statistics page';
        }
        searchButtons.forEach(btn => btn.disabled = true);
      } else if (headerSearch) {
        headerSearch.classList.remove('disabled');
        // Re-enable search functionality
        const searchInput = headerSearch.querySelector('#searchInput');
        const searchButtons = headerSearch.querySelectorAll('button');
        if (searchInput) {
          searchInput.disabled = false;
          // Update placeholder based on current page
          updateSearchPlaceholder(window.location.pathname);
        }
        searchButtons.forEach(btn => btn.disabled = false);
      }
    }
    
    updateThemeTooltip(themeToggle, currentTheme) {
      if (!window.i18n) return;
      
      if (currentTheme === 'light') {
        themeToggle.title = window.i18n.t('header.theme.switchToDark');
      } else if (currentTheme === 'dark') {
        themeToggle.title = window.i18n.t('header.theme.switchToLight');
      }
    }
}
