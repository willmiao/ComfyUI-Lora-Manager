import { updateService } from '../managers/UpdateService.js';
import { toggleTheme } from '../utils/uiHelpers.js';
import { SearchManager } from '../managers/SearchManager.js';
import { FilterManager } from '../managers/FilterManager.js';
import { initPageState } from '../state/index.js';
import { getStorageItem } from '../utils/storageHelpers.js';
import { updateElementAttribute } from '../utils/i18nHelpers.js';
import { renderSupporters } from '../services/supportersService.js';

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
        const currentTheme = getStorageItem('theme') || 'auto';
        themeToggle.classList.add(`theme-${currentTheme}`);

        // Use i18nHelpers to update themeToggle's title
        this.updateThemeTooltip(themeToggle, currentTheme);

        themeToggle.addEventListener('click', async () => {
          if (typeof toggleTheme === 'function') {
            const newTheme = toggleTheme();
            // Use i18nHelpers to update themeToggle's title
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
        supportToggle.addEventListener('click', async () => {
          if (window.modalManager) {
            window.modalManager.toggleModal('supportModal');
            // Load supporters data when modal opens
            try {
              await renderSupporters();
            } catch (error) {
              console.error('Error loading supporters:', error);
            }
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

      // Initialize hamburger menu for mobile
      this.initializeHamburgerMenu();
    }

    initializeHamburgerMenu() {
      const hamburgerBtn = document.getElementById('hamburgerMenuBtn');
      const hamburgerDropdown = document.getElementById('hamburgerDropdown');

      if (!hamburgerBtn || !hamburgerDropdown) return;

      // Toggle dropdown on hamburger button click
      hamburgerBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        hamburgerDropdown.classList.toggle('active');
        const icon = hamburgerBtn.querySelector('i');
        if (hamburgerDropdown.classList.contains('active')) {
          icon.classList.remove('fa-bars');
          icon.classList.add('fa-times');
        } else {
          icon.classList.remove('fa-times');
          icon.classList.add('fa-bars');
        }
      });

      // Handle dropdown item clicks
      const dropdownItems = hamburgerDropdown.querySelectorAll('.dropdown-item');
      dropdownItems.forEach(item => {
        item.addEventListener('click', (e) => {
          const action = item.dataset.action;
          this.handleHamburgerAction(action);
          hamburgerDropdown.classList.remove('active');
          const icon = hamburgerBtn.querySelector('i');
          icon.classList.remove('fa-times');
          icon.classList.add('fa-bars');
        });
      });

      // Close dropdown when clicking outside
      document.addEventListener('click', (e) => {
        if (!hamburgerDropdown.contains(e.target) && !hamburgerBtn.contains(e.target)) {
          hamburgerDropdown.classList.remove('active');
          const icon = hamburgerBtn.querySelector('i');
          if (icon) {
            icon.classList.remove('fa-times');
            icon.classList.add('fa-bars');
          }
        }
      });

      // Update theme icon in hamburger menu based on current theme
      this.updateHamburgerThemeIcon();
    }

    handleHamburgerAction(action) {
      switch (action) {
        case 'theme':
          if (typeof toggleTheme === 'function') {
            const newTheme = toggleTheme();
            // Update theme toggle in header if it exists
            const themeToggle = document.querySelector('.theme-toggle');
            if (themeToggle) {
              themeToggle.classList.remove('theme-light', 'theme-dark', 'theme-auto');
              themeToggle.classList.add(`theme-${newTheme}`);
              this.updateThemeTooltip(themeToggle, newTheme);
            }
            this.updateHamburgerThemeIcon();
          }
          break;
        case 'settings':
          if (window.settingsManager) {
            window.settingsManager.toggleSettings();
          }
          break;
        case 'help':
          const helpToggle = document.getElementById('helpToggleBtn');
          if (helpToggle) {
            helpToggle.click();
          }
          break;
        case 'notifications':
          updateService.toggleUpdateModal();
          break;
        case 'support':
          if (window.modalManager) {
            window.modalManager.toggleModal('supportModal');
            renderSupporters().catch(error => {
              console.error('Error loading supporters:', error);
            });
          }
          break;
      }
    }

    updateHamburgerThemeIcon() {
      const themeItem = document.querySelector('.dropdown-item[data-action="theme"]');
      if (!themeItem) return;

      const currentTheme = getStorageItem('theme') || 'auto';
      const icon = themeItem.querySelector('i');
      const text = themeItem.querySelector('span');

      if (icon) {
        icon.classList.remove('fa-moon', 'fa-sun', 'fa-adjust');
        if (currentTheme === 'light') {
          icon.classList.add('fa-sun');
        } else if (currentTheme === 'dark') {
          icon.classList.add('fa-moon');
        } else {
          icon.classList.add('fa-adjust');
        }
      }

      // Update text based on current theme
      if (text) {
        const key = currentTheme === 'light' ? 'header.theme.switchToDark' :
                    currentTheme === 'dark' ? 'header.theme.switchToLight' :
                    'header.theme.toggle';
        updateElementAttribute(themeItem, 'aria-label', key, {}, '');
      }
    }

    updateHeaderForPage() {
      const headerSearch = document.getElementById('headerSearch');
      const searchInput = headerSearch?.querySelector('#searchInput');
      const searchButtons = headerSearch?.querySelectorAll('button');
      const placeholderKey = 'header.search.placeholders.' + this.currentPage;

      if (this.currentPage === 'statistics' && headerSearch) {
        headerSearch.classList.add('disabled');
        if (searchInput) {
          searchInput.disabled = true;
          // Use i18nHelpers to update placeholder
          updateElementAttribute(searchInput, 'placeholder', 'header.search.notAvailable', {}, 'Search not available on statistics page');
        }
        searchButtons?.forEach(btn => btn.disabled = true);
      } else if (headerSearch) {
        headerSearch.classList.remove('disabled');
        if (searchInput) {
          searchInput.disabled = false;
          // Use i18nHelpers to update placeholder
          updateElementAttribute(searchInput, 'placeholder', placeholderKey, {}, '');
        }
        searchButtons?.forEach(btn => btn.disabled = false);
      }
    }

    updateThemeTooltip(themeToggle, currentTheme) {
      if (!themeToggle) return;
      let key;
      if (currentTheme === 'light') {
        key = 'header.theme.switchToDark';
      } else if (currentTheme === 'dark') {
        key = 'header.theme.switchToLight';
      } else {
        key = 'header.theme.toggle';
      }
      // Use i18nHelpers to update title
      updateElementAttribute(themeToggle, 'title', key, {}, '');
    }
}
