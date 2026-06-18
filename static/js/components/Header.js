import { updateService } from '../managers/UpdateService.js';
import { toggleTheme, setPreset, CYCLE_ORDER, PRESET_NAMES } from '../utils/uiHelpers.js';
import { SearchManager } from '../managers/SearchManager.js';
import { FilterManager } from '../managers/FilterManager.js';
import { initPageState } from '../state/index.js';
import { getStorageItem, setStorageItem } from '../utils/storageHelpers.js';
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
      this.initializeThemePopover();

      const settingsToggle = document.querySelector('.settings-toggle');
      if (settingsToggle) {
        settingsToggle.addEventListener('click', () => {
          if (window.settingsManager) {
            window.settingsManager.toggleSettings();
          }
        });
      }

      const updateToggle = document.getElementById('updateToggleBtn');
      if (updateToggle) {
        updateToggle.addEventListener('click', () => {
          updateService.toggleUpdateModal();
        });
      }

      const supportToggle = document.getElementById('supportToggleBtn');
      if (supportToggle) {
        supportToggle.addEventListener('click', async () => {
          if (window.modalManager) {
            window.modalManager.toggleModal('supportModal');
            try {
              await renderSupporters();
            } catch (error) {
              console.error('Error loading supporters:', error);
            }
          }
        });
      }

      const qrToggle = document.getElementById('toggleQRCode');
      const qrContainer = document.getElementById('qrCodeContainer');

      if (qrToggle && qrContainer) {
        qrToggle.addEventListener('click', function () {
          qrContainer.classList.toggle('show');
          qrToggle.classList.toggle('active');

          const toggleText = qrToggle.querySelector('.toggle-text');
          if (qrContainer.classList.contains('show')) {
            toggleText.textContent = 'Hide WeChat QR Code';
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

      this.updateHeaderForPage();
      this.initializeHamburgerMenu();
    }

    initializeThemePopover() {
      const themeToggle = document.querySelector('.theme-toggle');
      const themePopover = document.getElementById('themePopover');
      if (!themeToggle || !themePopover) return;

      const currentTheme = getStorageItem('theme') || 'auto';
      const currentPreset = getStorageItem('theme_preset') || 'default';
      themeToggle.classList.add(`theme-${currentTheme}`);
      this.updateThemeTooltip(themeToggle, currentTheme);
      this.updatePopoverActiveStates(currentTheme, currentPreset);

      themeToggle.addEventListener('click', (e) => {
        if (e.target.closest('.theme-popover')) return;
        e.stopPropagation();
        const isOpen = themePopover.classList.contains('active');
        this.closeAllPopovers();
        if (!isOpen) {
          themePopover.classList.add('active');
        }
      });

      themePopover.addEventListener('click', (e) => {
        e.stopPropagation();
        const modeBtn = e.target.closest('.theme-mode-btn');
        const presetBtn = e.target.closest('.theme-preset-btn');

        if (modeBtn) {
          const mode = modeBtn.dataset.mode;
          this.setThemeMode(mode);
        } else if (presetBtn) {
          const preset = presetBtn.dataset.preset;
          this.setThemePreset(preset);
        }
      });

      document.addEventListener('click', (e) => {
        if (!themeToggle.contains(e.target) && !themePopover.contains(e.target)) {
          themePopover.classList.remove('active');
        }
      });
    }

    closeAllPopovers() {
      const themePopover = document.getElementById('themePopover');
      if (themePopover) {
        themePopover.classList.remove('active');
      }
    }

    setThemeMode(mode) {
      setStorageItem('theme', mode);
      const htmlElement = document.documentElement;
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      htmlElement.removeAttribute('data-theme');
      if (mode === 'dark' || (mode === 'auto' && prefersDark)) {
        htmlElement.setAttribute('data-theme', 'dark');
        document.body.dataset.theme = 'dark';
      } else {
        htmlElement.setAttribute('data-theme', 'light');
        document.body.dataset.theme = 'light';
      }
      const themeToggle = document.querySelector('.theme-toggle');
      if (themeToggle) {
        themeToggle.classList.remove('theme-light', 'theme-dark', 'theme-auto');
        themeToggle.classList.add(`theme-${mode}`);
        this.updateThemeTooltip(themeToggle, mode);
      }
      this.updateHamburgerThemeIcon();
      this.updatePopoverActiveStates(mode, getStorageItem('theme_preset') || 'default');
    }

    setThemePreset(preset) {
      setPreset(preset);
      this.updatePopoverActiveStates(getStorageItem('theme') || 'auto', preset);
      this.updateHamburgerThemeIcon();
    }

    updatePopoverActiveStates(theme, preset) {
      const popover = document.getElementById('themePopover');
      if (!popover) return;

      popover.querySelectorAll('.theme-mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === theme);
      });

      popover.querySelectorAll('.theme-preset-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.preset === preset);
      });
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
            const themeToggle = document.querySelector('.theme-toggle');
            if (themeToggle) {
              themeToggle.classList.remove('theme-light', 'theme-dark', 'theme-auto');
              themeToggle.classList.add(`theme-${newTheme}`);
              this.updateThemeTooltip(themeToggle, newTheme);
            }
            this.updateHamburgerThemeIcon();
            this.updatePopoverActiveStates(newTheme, getStorageItem('theme_preset') || 'default');
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
