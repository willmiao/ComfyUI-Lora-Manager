import { getStorageItem, setStorageItem } from '../utils/storageHelpers.js';
import { onboardingManager } from './OnboardingManager.js';

/**
 * Manages help modal functionality and tutorial update notifications
 */
export class HelpManager {
    constructor() {
        // Version of the help content the user has seen. Compared against the
        // data-help-content-version marker rendered into the help modal markup,
        // so badge state is always derived from the content actually served.
        this.viewedContentVersion = getStorageItem('help_viewed_content_version', null);
        this.isInitialized = false;
    }

    /**
     * Initialize the help manager
     */
    initialize() {
        if (this.isInitialized) return;
        
        console.log('HelpManager: Initializing...');
        
        // Set up event handlers
        this.setupEventListeners();
        
        // Check if we need to show the badge
        this.updateHelpBadge();
        
        this.isInitialized = true;
        return this;
    }
    
    /**
     * Set up event listeners for help modal
     */
    setupEventListeners() {
        // Help toggle button
        const helpToggleBtn = document.getElementById('helpToggleBtn');
        if (helpToggleBtn) {
            helpToggleBtn.addEventListener('click', () => this.openHelpModal());
        }
        
        // Help modal tab functionality
        const tabButtons = document.querySelectorAll('.help-tabs .tab-btn');
        tabButtons.forEach(button => {
            button.addEventListener('click', (event) => {
                this.activateHelpTab(event.currentTarget.getAttribute('data-tab'));
            });
        });

        // Replay tutorial button in the Getting Started tab
        const replayTutorialBtn = document.getElementById('replayTutorialBtn');
        if (replayTutorialBtn) {
            replayTutorialBtn.addEventListener('click', () => {
                // Close the help modal, then restart the onboarding tutorial
                if (window.modalManager) {
                    window.modalManager.closeModal('helpModal');
                }
                onboardingManager.reset();
                onboardingManager.startTutorial();
            });
        }

        // Global "?" shortcut opens the help modal on the Shortcuts tab
        document.addEventListener('keydown', (event) => {
            if (event.key !== '?') return;
            if (this.isTypingContext(event.target)) return;
            if (window.modalManager?.isAnyModalOpen()) return;

            event.preventDefault();
            this.openHelpModal('shortcuts');
        });
    }

    /**
     * Check if the event target is a text entry context where "?" is literal input
     */
    isTypingContext(target) {
        if (!(target instanceof Element)) return false;

        const tagName = target.tagName?.toLowerCase();
        return target.isContentEditable || tagName === 'input' || tagName === 'textarea' || tagName === 'select';
    }

    /**
     * Activate a specific help modal tab by its data-tab id
     * @param {string} tabId - The tab id (matches data-tab and pane element id)
     */
    activateHelpTab(tabId) {
        const tabButton = document.querySelector(`.help-tabs .tab-btn[data-tab="${tabId}"]`);
        const tabPane = document.getElementById(tabId);
        if (!tabButton || !tabPane) return;

        // Remove active class from all buttons and panes
        document.querySelectorAll('.help-tabs .tab-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelectorAll('.help-content .tab-pane').forEach(pane => {
            pane.classList.remove('active');
        });

        // Activate the requested tab
        tabButton.classList.add('active');
        tabPane.classList.add('active');
    }
    
    /**
     * Open the help modal
     * @param {string} [tabId] - Optional tab id to activate after opening
     */
    openHelpModal(tabId) {
        // Use modalManager to open the help modal
        if (!window.modalManager) return;

        const hadNewContent = this.hasNewContent();

        window.modalManager.toggleModal('helpModal');

        if (tabId) {
            this.activateHelpTab(tabId);
        }

        // Only acknowledge the content as viewed when the user opened the
        // modal while it actually contained new content. Opening a stale
        // (pre-upgrade) page must not suppress the badge after a refresh.
        if (hadNewContent) {
            this.updateNewContentTabIndicators();
            this.markContentAsViewed();
        }

        // Hide the badge
        this.hideHelpBadge();
    }

    /**
     * Add visual indicator to tabs that received new content
     */
    updateNewContentTabIndicators() {
        if (!this.hasNewContent()) return;

        // Tabs updated in the 2026-09-03 discoverability release:
        // getting-started (Replay Tutorial button) and shortcuts (new cheat-sheet tab)
        const NEW_CONTENT_TABS = ['getting-started', 'shortcuts'];
        NEW_CONTENT_TABS.forEach(tabId => {
            const tab = document.querySelector(`.help-tabs .tab-btn[data-tab="${tabId}"]`);
            if (tab) {
                tab.classList.add('has-new-content');
            }
        });

        // Point the indicator at the specific new element inside the
        // Getting Started tab, and scroll it into view so it is not lost
        // below the fold of the modal body.
        const replayBtn = document.getElementById('replayTutorialBtn');
        if (replayBtn) {
            replayBtn.classList.add('has-new-content');
            const gettingStartedActive = document.querySelector('#getting-started.tab-pane.active');
            if (gettingStartedActive && typeof replayBtn.scrollIntoView === 'function') {
                replayBtn.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }
    }
    
    /**
     * Mark content as viewed by persisting the version rendered in the DOM.
     * No-op when the served markup carries no version marker (stale assets),
     * so viewing old content never suppresses the badge for new content.
     */
    markContentAsViewed() {
        const currentVersion = this.getCurrentContentVersion();
        if (!currentVersion) return;

        this.viewedContentVersion = currentVersion;
        setStorageItem('help_viewed_content_version', this.viewedContentVersion);
    }

    /**
     * Read the help content version from the rendered modal markup
     * @returns {string|null} Version marker, or null if the served markup has none
     */
    getCurrentContentVersion() {
        const marker = document.querySelector('[data-help-content-version]');
        return marker ? marker.getAttribute('data-help-content-version') : null;
    }

    /**
     * Update help badge visibility based on viewed vs. served content version
     */
    updateHelpBadge() {
        if (this.hasNewContent()) {
            this.showHelpBadge();
        } else {
            this.hideHelpBadge();
        }
    }

    /**
     * Check if the served help content is newer than what the user has viewed
     */
    hasNewContent() {
        const currentVersion = this.getCurrentContentVersion();
        return Boolean(currentVersion) && currentVersion !== this.viewedContentVersion;
    }
    
    /**
     * Show the help badge
     */
    showHelpBadge() {
        const helpBadge = document.querySelector('#helpToggleBtn .update-badge');
        if (helpBadge) {
            helpBadge.classList.add('visible');
        }
    }
    
    /**
     * Hide the help badge
     */
    hideHelpBadge() {
        const helpBadge = document.querySelector('#helpToggleBtn .update-badge');
        if (helpBadge) {
            helpBadge.classList.remove('visible');
        }
    }
}

// Create singleton instance
export const helpManager = new HelpManager();