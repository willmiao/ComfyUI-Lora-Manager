import { getStorageItem, setStorageItem } from '../utils/storageHelpers.js';
import { state } from '../state/index.js';
import { translate } from '../utils/i18nHelpers.js';
import { showToast } from '../utils/uiHelpers.js';

export class OnboardingManager {
    constructor() {
        this.isActive = false;
        this.currentStep = 0;
        this.selectedLanguage = 'en'; // Will be updated from state
        this.overlay = null;
        this.spotlight = null;
        this.popup = null;
        this.currentTarget = null; // Track current highlighted element
        
        // Available languages with SVG flags (using flag-icons)
        this.languages = [
            { code: 'en', name: 'English', flag: 'us' },
            { code: 'zh-CN', name: '简体中文', flag: 'cn' },
            { code: 'zh-TW', name: '繁體中文', flag: 'hk' },
            { code: 'ja', name: '日本語', flag: 'jp' },
            { code: 'ko', name: '한국어', flag: 'kr' },
            { code: 'es', name: 'Español', flag: 'es' },
            { code: 'fr', name: 'Français', flag: 'fr' },
            { code: 'de', name: 'Deutsch', flag: 'de' },
            { code: 'ru', name: 'Русский', flag: 'ru' }
        ];
        
        // Tutorial steps configuration
        this.steps = [
            {
                target: '.controls .action-buttons [data-action="fetch"]',
                title: () => translate('onboarding.steps.fetch.title', {}, 'Fetch Models Metadata'),
                content: () => translate('onboarding.steps.fetch.content', {}, 'Click the <strong>Fetch</strong> button to download model metadata and preview images from Civitai.'),
                position: 'bottom'
            },
            {
                target: '.controls .action-buttons [data-action="download"]',
                title: () => translate('onboarding.steps.download.title', {}, 'Download New Models'),
                content: () => translate('onboarding.steps.download.content', {}, 'Use the <strong>Download</strong> button to download models directly from Civitai URLs.'),
                position: 'bottom'
            },
            {
                target: '.controls .action-buttons [data-action="bulk"]',
                title: () => translate('onboarding.steps.bulk.title', {}, 'Bulk Operations'),
                content: () => translate('onboarding.steps.bulk.content', {}, 'Enter bulk mode by clicking this button or pressing <span class="onboarding-shortcut">B</span>. Select multiple models and perform batch operations. Use <span class="onboarding-shortcut">Ctrl+A</span> to select all visible models.'),
                position: 'bottom'
            },
            {
                target: '#searchOptionsToggle',
                title: () => translate('onboarding.steps.searchOptions.title', {}, 'Search Options'),
                content: () => translate('onboarding.steps.searchOptions.content', {}, 'Click this button to configure what fields to search in: filename, model name, tags, or creator name. Customize your search scope.'),
                position: 'bottom'
            },
            {
                target: '#filterButton',
                title: () => translate('onboarding.steps.filter.title', {}, 'Filter Models'),
                content: () => translate('onboarding.steps.filter.content', {}, 'Use filters to narrow down models by base model type (SD1.5, SDXL, Flux, etc.) or by specific tags.'),
                position: 'bottom'
            },
            {
                target: '#breadcrumbContainer',
                title: () => translate('onboarding.steps.breadcrumb.title', {}, 'Breadcrumb Navigation'),
                content: () => translate('onboarding.steps.breadcrumb.content', {}, 'The breadcrumb navigation shows your current path and allows quick navigation between folders. Click any folder name to jump directly there.'),
                position: 'bottom'
            },
            {
                target: '.card-grid',
                title: () => translate('onboarding.steps.modelCards.title', {}, 'Model Cards'),
                content: () => translate('onboarding.steps.modelCards.content', {}, '<strong>Single-click</strong> a model card to view detailed information and edit metadata. Look for the pencil icon when hovering over editable fields.'),
                position: 'top',
                customPosition: { top: '20%', left: '50%' }
            },
            {
                target: '.card-grid',
                title: () => translate('onboarding.steps.contextMenu.title', {}, 'Context Menu'),
                content: () => translate('onboarding.steps.contextMenu.content', {}, '<strong>Right-click</strong> any model card for a context menu with additional actions.'),
                position: 'top',
                customPosition: { top: '20%', left: '50%' }
            }
        ];
    }

    // Check if user should see onboarding
    shouldShowOnboarding() {
        const completed = getStorageItem('onboarding_completed');
        const skipped = getStorageItem('onboarding_skipped');
        return !completed && !skipped;
    }

    // Start the onboarding process
    async start() {
        if (!this.shouldShowOnboarding()) {
            return;
        }

        // If language has already been set, skip language selection
        if (getStorageItem('onboarding_language_set')) {
            this.startTutorial();
            return;
        }

        // Show language selection first
        await this.showLanguageSelection();
    }

    // Show language selection modal
    showLanguageSelection() {
        return new Promise((resolve) => {
            // Initialize selected language from current settings
            this.selectedLanguage = state.global.settings.language || 'en';
            
            const modal = document.createElement('div');
            modal.className = 'language-selection-modal';
            modal.innerHTML = `
                <div class="language-selection-content">
                    <h2>${translate('onboarding.languageSelection.title', {}, 'Welcome to LoRA Manager')}</h2>
                    <p>Choose Your Language / 选择语言 / 言語を選択</p>
                    <div class="language-grid">
                        ${this.languages.map(lang => `
                            <div class="language-option" data-language="${lang.code}">
                                <span class="language-flag">
                                    <span class="fi fi-${lang.flag}"></span>
                                </span>
                                <span class="language-name">${lang.name}</span>
                            </div>
                        `).join('')}
                    </div>
                    <div class="language-actions">
                        <button class="onboarding-btn" id="skipLanguageBtn">${translate('onboarding.tutorial.skipTutorial', {}, 'Skip Tutorial')}</button>
                        <button class="onboarding-btn primary" id="continueLanguageBtn">${translate('onboarding.languageSelection.continue', {}, 'Continue')}</button>
                    </div>
                </div>
            `;

            document.body.appendChild(modal);

            // Handle language selection
            modal.querySelectorAll('.language-option').forEach(option => {
                option.addEventListener('click', () => {
                    modal.querySelectorAll('.language-option').forEach(opt => opt.classList.remove('selected'));
                    option.classList.add('selected');
                    this.selectedLanguage = option.dataset.language;
                });
            });

            // Handle continue button
            document.getElementById('continueLanguageBtn').addEventListener('click', async () => {
                const currentLanguage = state.global.settings.language || 'en';
                
                // Only change language if it's different from current setting
                if (this.selectedLanguage !== currentLanguage) {
                    await this.changeLanguage(this.selectedLanguage);
                } else {
                    document.body.removeChild(modal);
                    this.startTutorial();
                    resolve();
                }
            });

            // Handle skip button - skip entire tutorial
            document.getElementById('skipLanguageBtn').addEventListener('click', () => {
                document.body.removeChild(modal);
                this.skip(); // Skip entire tutorial instead of just language selection
                resolve();
            });

            // Select current language by default
            const currentLanguageOption = modal.querySelector(`[data-language="${this.selectedLanguage}"]`);
            if (currentLanguageOption) {
                currentLanguageOption.classList.add('selected');
            } else {
                // Fallback to English if current language not found
                modal.querySelector('[data-language="en"]').classList.add('selected');
            }
        });
    }

    // Change language using existing settings manager
    async changeLanguage(languageCode) {
        try {
            // Update state
            state.global.settings.language = languageCode;
            
            // Save to backend
            const response = await fetch('/api/lm/settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    language: languageCode
                })
            });

            if (response.ok) {
                // Mark onboarding as started before reload
                setStorageItem('onboarding_language_set', true);
                window.location.reload();
            }
        } catch (error) {
            console.error('Failed to change language:', error);
            showToast('onboarding.languageSelection.changeFailed', { message: error.message }, 'error');
        }
    }

    // Start the tutorial steps
    startTutorial() {
        this.isActive = true;
        this.currentStep = 0;
        this.createOverlay();
        this.showStep(0);
    }

    // Create overlay elements
    createOverlay() {
        // Create overlay
        this.overlay = document.createElement('div');
        this.overlay.className = 'onboarding-overlay active';
        document.body.appendChild(this.overlay);

        // Create spotlight
        this.spotlight = document.createElement('div');
        this.spotlight.className = 'onboarding-spotlight';
        document.body.appendChild(this.spotlight);

        // Create popup
        this.popup = document.createElement('div');
        this.popup.className = 'onboarding-popup';
        document.body.appendChild(this.popup);
    }

    // Show specific step
    showStep(stepIndex) {
        if (stepIndex >= this.steps.length) {
            this.complete();
            return;
        }

        const step = this.steps[stepIndex];
        const target = document.querySelector(step.target);

        if (!target && step.target !== 'body') {
            // Skip this step if target not found
            this.showStep(stepIndex + 1);
            return;
        }

        // Clear previous target highlighting
        this.clearTargetHighlight();

        // Position spotlight and create mask
        if (target && step.target !== 'body') {
            this.highlightTarget(target);
        } else {
            this.spotlight.style.display = 'none';
            this.clearOverlayMask();
        }

        // Update popup content
        this.popup.innerHTML = `
            <h3>${typeof step.title === 'function' ? step.title() : step.title}</h3>
            <p>${typeof step.content === 'function' ? step.content() : step.content}</p>
            <div class="onboarding-controls">
                <div class="onboarding-progress">
                    <span>${stepIndex + 1} / ${this.steps.length}</span>
                </div>
                <div class="onboarding-actions">
                    <button class="onboarding-btn" onclick="onboardingManager.skip()">${translate('onboarding.tutorial.skipTutorial', {}, 'Skip Tutorial')}</button>
                    ${stepIndex > 0 ? `<button class="onboarding-btn" onclick="onboardingManager.previousStep()">${translate('onboarding.tutorial.back', {}, 'Back')}</button>` : ''}
                    <button class="onboarding-btn primary" onclick="onboardingManager.nextStep()">
                        ${stepIndex === this.steps.length - 1 ? translate('onboarding.tutorial.finish', {}, 'Finish') : translate('onboarding.tutorial.next', {}, 'Next')}
                    </button>
                </div>
            </div>
        `;

        // Position popup
        this.positionPopup(step, target);
        
        this.currentStep = stepIndex;
    }

    // Position popup relative to target
    positionPopup(step, target) {
        const popup = this.popup;
        const windowWidth = window.innerWidth;
        const windowHeight = window.innerHeight;

        if (step.customPosition) {
            popup.style.left = step.customPosition.left;
            popup.style.top = step.customPosition.top;
            popup.style.transform = 'translate(-50%, 0)';
            return;
        }

        if (!target || step.target === 'body') {
            popup.style.left = '50%';
            popup.style.top = '50%';
            popup.style.transform = 'translate(-50%, -50%)';
            return;
        }

        const rect = target.getBoundingClientRect();
        const popupRect = popup.getBoundingClientRect();

        let left, top;

        switch (step.position) {
            case 'bottom':
                left = rect.left + (rect.width / 2) - (popupRect.width / 2);
                top = rect.bottom + 20;
                break;
            case 'top':
                left = rect.left + (rect.width / 2) - (popupRect.width / 2);
                top = rect.top - popupRect.height - 20;
                break;
            case 'right':
                left = rect.right + 20;
                top = rect.top + (rect.height / 2) - (popupRect.height / 2);
                break;
            case 'left':
                left = rect.left - popupRect.width - 20;
                top = rect.top + (rect.height / 2) - (popupRect.height / 2);
                break;
            default:
                left = rect.left + (rect.width / 2) - (popupRect.width / 2);
                top = rect.bottom + 20;
        }

        // Ensure popup stays within viewport
        left = Math.max(20, Math.min(left, windowWidth - popupRect.width - 20));
        top = Math.max(20, Math.min(top, windowHeight - popupRect.height - 20));

        popup.style.left = `${left}px`;
        popup.style.top = `${top}px`;
        popup.style.transform = 'none';
    }

    // Highlight target element with mask approach
    highlightTarget(target) {
        const rect = target.getBoundingClientRect();
        const padding = 4; // Padding around the target element
        const offset = 3; // Shift spotlight up and left by 3px

        // Position spotlight
        this.spotlight.style.left = `${rect.left - padding - offset}px`;
        this.spotlight.style.top = `${rect.top - padding - offset}px`;
        this.spotlight.style.width = `${rect.width + padding * 2}px`;
        this.spotlight.style.height = `${rect.height + padding * 2}px`;
        this.spotlight.style.display = 'block';

        // Create mask for overlay to cut out the highlighted area
        this.createOverlayMask(rect, padding, offset);

        // Add highlight class to target and ensure it's interactive
        target.classList.add('onboarding-target-highlight');
        this.currentTarget = target;
        
        // Add pulsing animation
        this.spotlight.classList.add('onboarding-highlight');
    }

    // Create mask for overlay to cut out highlighted area
    createOverlayMask(rect, padding, offset = 0) {
        const x = rect.left - padding - offset;
        const y = rect.top - padding - offset;
        const width = rect.width + padding * 2;
        const height = rect.height + padding * 2;
        
        // Create SVG mask
        const maskId = 'onboarding-mask';
        let maskSvg = document.getElementById(maskId);
        
        if (!maskSvg) {
            maskSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            maskSvg.id = maskId;
            maskSvg.style.position = 'absolute';
            maskSvg.style.top = '0';
            maskSvg.style.left = '0';
            maskSvg.style.width = '100%';
            maskSvg.style.height = '100%';
            maskSvg.style.pointerEvents = 'none';
            document.body.appendChild(maskSvg);
        }
        
        // Clear existing mask content
        maskSvg.innerHTML = `
            <defs>
                <mask id="overlay-mask">
                    <rect width="100%" height="100%" fill="white"/>
                    <rect x="${x}" y="${y}" width="${width}" height="${height}" 
                          rx="8" ry="8" fill="black"/>
                </mask>
            </defs>
        `;
        
        // Apply mask to overlay
        this.overlay.style.mask = 'url(#overlay-mask)';
        this.overlay.style.webkitMask = 'url(#overlay-mask)';
    }

    // Clear overlay mask
    clearOverlayMask() {
        if (this.overlay) {
            this.overlay.style.mask = 'none';
            this.overlay.style.webkitMask = 'none';
        }
        
        const maskSvg = document.getElementById('onboarding-mask');
        if (maskSvg) {
            maskSvg.remove();
        }
    }

    // Clear target highlighting
    clearTargetHighlight() {
        if (this.currentTarget) {
            this.currentTarget.classList.remove('onboarding-target-highlight');
            this.currentTarget = null;
        }
        
        if (this.spotlight) {
            this.spotlight.classList.remove('onboarding-highlight');
        }
    }

    // Navigate to next step
    nextStep() {
        this.showStep(this.currentStep + 1);
    }

    // Navigate to previous step
    previousStep() {
        if (this.currentStep > 0) {
            this.showStep(this.currentStep - 1);
        }
    }

    // Skip the tutorial
    skip() {
        setStorageItem('onboarding_skipped', true);
        this.cleanup();
    }

    // Complete the tutorial
    complete() {
        setStorageItem('onboarding_completed', true);
        this.cleanup();
    }

    // Clean up overlay elements
    cleanup() {
        this.clearTargetHighlight();
        this.clearOverlayMask();
        
        if (this.overlay) {
            document.body.removeChild(this.overlay);
            this.overlay = null;
        }
        if (this.spotlight) {
            document.body.removeChild(this.spotlight);
            this.spotlight = null;
        }
        if (this.popup) {
            document.body.removeChild(this.popup);
            this.popup = null;
        }
        this.isActive = false;
    }

    // Reset onboarding status (for testing)
    reset() {
        localStorage.removeItem('lora_manager_onboarding_completed');
        localStorage.removeItem('lora_manager_onboarding_skipped');
        localStorage.removeItem('lora_manager_onboarding_language_set');
        localStorage.setItem('lora_manager_version_info', '0.8.30-2546581');
    }
}

// Create singleton instance
export const onboardingManager = new OnboardingManager();

// Make it globally available for button handlers
window.onboardingManager = onboardingManager;
