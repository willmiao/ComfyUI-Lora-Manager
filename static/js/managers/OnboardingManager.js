import { getStorageItem, setStorageItem } from '../utils/storageHelpers.js';
import { state } from '../state/index.js';

export class OnboardingManager {
    constructor() {
        this.isActive = false;
        this.currentStep = 0;
        this.selectedLanguage = 'en';
        this.overlay = null;
        this.spotlight = null;
        this.popup = null;
        
        // Available languages with SVG flags (using flag-icons)
        this.languages = [
            { code: 'en', name: 'English', flag: 'us' },
            { code: 'zh-cn', name: '简体中文', flag: 'cn' },
            { code: 'zh-tw', name: '繁體中文', flag: 'hk' },
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
                title: 'Fetch Models Metadata',
                content: 'Click the <strong>Fetch</strong> button to download model metadata and preview images from Civitai.',
                position: 'bottom'
            },
            {
                target: '.controls .action-buttons [data-action="download"]',
                title: 'Download New Models',
                content: 'Use the <strong>Download</strong> button to download models directly from Civitai URLs.',
                position: 'bottom'
            },
            {
                target: '.controls .action-buttons [data-action="bulk"]',
                title: 'Bulk Operations',
                content: 'Enter bulk mode by clicking this button or pressing <span class="onboarding-shortcut">B</span>. Select multiple models and perform batch operations. Use <span class="onboarding-shortcut">Ctrl+A</span> to select all visible models.',
                position: 'bottom'
            },
            {
                target: '#searchOptionsToggle',
                title: 'Search Options',
                content: 'Click this button to configure what fields to search in: filename, model name, tags, or creator name. Customize your search scope.',
                position: 'bottom'
            },
            {
                target: '#filterButton',
                title: 'Filter Models',
                content: 'Use filters to narrow down models by base model type (SD1.5, SDXL, Flux, etc.) or by specific tags.',
                position: 'bottom'
            },
            {
                target: '#breadcrumbContainer',
                title: 'Breadcrumb Navigation',
                content: 'The breadcrumb navigation shows your current path and allows quick navigation between folders. Click any folder name to jump directly there.',
                position: 'bottom'
            },
            {
                target: '.card-grid',
                title: 'Model Cards',
                content: '<strong>Single-click</strong> a model card to view detailed information and edit metadata. Look for the pencil icon when hovering over editable fields.',
                position: 'top',
                customPosition: { top: '20%', left: '50%' }
            },
            {
                target: '.card-grid',
                title: 'Context Menu',
                content: '<strong>Right-click</strong> any model card for a context menu with additional actions.',
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

        // Show language selection first
        await this.showLanguageSelection();
    }

    // Show language selection modal
    showLanguageSelection() {
        return new Promise((resolve) => {
            const modal = document.createElement('div');
            modal.className = 'language-selection-modal';
            modal.innerHTML = `
                <div class="language-selection-content">
                    <h2>Welcome to LoRA Manager</h2>
                    <p>Choose your preferred language to get started, or continue with English.</p>
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
                        <button class="onboarding-btn" id="skipLanguageBtn">Skip</button>
                        <button class="onboarding-btn primary" id="continueLanguageBtn">Continue</button>
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
                if (this.selectedLanguage !== 'en') {
                    // Save language and reload page
                    await this.changeLanguage(this.selectedLanguage);
                }
                document.body.removeChild(modal);
                this.startTutorial();
                resolve();
            });

            // Handle skip button
            document.getElementById('skipLanguageBtn').addEventListener('click', () => {
                document.body.removeChild(modal);
                this.startTutorial();
                resolve();
            });

            // Select English by default
            modal.querySelector('[data-language="en"]').classList.add('selected');
        });
    }

    // Change language using existing settings manager
    async changeLanguage(languageCode) {
        try {
            // Update state
            state.global.settings.language = languageCode;
            
            // Save to localStorage
            setStorageItem('settings', state.global.settings);
            
            // Save to backend
            const response = await fetch('/api/settings', {
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

        // Handle clicks outside popup
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) {
                this.skip();
            }
        });
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

        // Position spotlight
        if (target && step.target !== 'body') {
            const rect = target.getBoundingClientRect();
            this.spotlight.style.left = `${rect.left - 5}px`;
            this.spotlight.style.top = `${rect.top - 5}px`;
            this.spotlight.style.width = `${rect.width + 10}px`;
            this.spotlight.style.height = `${rect.height + 10}px`;
            this.spotlight.style.display = 'block';
        } else {
            this.spotlight.style.display = 'none';
        }

        // Update popup content
        this.popup.innerHTML = `
            <h3>${step.title}</h3>
            <p>${step.content}</p>
            <div class="onboarding-controls">
                <div class="onboarding-progress">
                    <span>${stepIndex + 1} / ${this.steps.length}</span>
                </div>
                <div class="onboarding-actions">
                    <button class="onboarding-btn" onclick="onboardingManager.skip()">Skip Tutorial</button>
                    ${stepIndex > 0 ? '<button class="onboarding-btn" onclick="onboardingManager.previousStep()">Back</button>' : ''}
                    <button class="onboarding-btn primary" onclick="onboardingManager.nextStep()">
                        ${stepIndex === this.steps.length - 1 ? 'Finish' : 'Next'}
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
    }
}

// Create singleton instance
export const onboardingManager = new OnboardingManager();

// Make it globally available for button handlers
window.onboardingManager = onboardingManager;
