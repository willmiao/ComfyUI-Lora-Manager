/**
 * Mixed i18n handler - coordinates server-side and client-side translations
 * Reduces language flashing by using server-rendered content initially
 */

class MixedI18nHandler {
    constructor() {
        this.serverTranslations = window.__SERVER_TRANSLATIONS__ || {};
        this.currentLanguage = this.serverTranslations.language || 'en';
        this.initialized = false;
    }
    
    /**
     * Initialize mixed i18n system
     */
    async initialize() {
        if (this.initialized) return;
        
        // Import the main i18n module
        const { i18n } = await import('/loras_static/js/i18n/index.js');
        this.clientI18n = i18n;
        
        // Ensure client i18n uses the same language as server
        if (this.currentLanguage && this.clientI18n.getCurrentLocale() !== this.currentLanguage) {
            this.clientI18n.setLanguage(this.currentLanguage);
        }
        
        // Translate any remaining elements that need client-side translation
        this.translateRemainingElements();
        
        this.initialized = true;
        
        // Dispatch event to notify that mixed i18n is ready
        window.dispatchEvent(new CustomEvent('mixedI18nReady', { 
            detail: { language: this.currentLanguage } 
        }));
    }
    
    /**
     * Translate elements that still need client-side translation
     * (primarily dynamic content and complex components)
     */
    translateRemainingElements() {
        if (!this.clientI18n) return;
        
        // Find all elements with data-i18n attribute that haven't been server-rendered
        const elements = document.querySelectorAll('[data-i18n]');
        
        elements.forEach(element => {
            // Skip if already translated by server (check if content matches key pattern)
            const key = element.getAttribute('data-i18n');
            const currentContent = element.textContent || element.value || element.placeholder;
            
            // If the current content looks like a translation key, translate it
            if (currentContent === key || currentContent.includes('.') || currentContent === '') {
                this.translateElement(element, key);
            }
        });
    }
    
    /**
     * Translate a single element using client-side i18n
     */
    translateElement(element, key) {
        if (!this.clientI18n) return;
        
        const params = element.getAttribute('data-i18n-params');
        let parsedParams = {};
        
        if (params) {
            try {
                parsedParams = JSON.parse(params);
            } catch (e) {
                console.warn(`Invalid JSON in data-i18n-params for key ${key}:`, params);
            }
        }
        
        // Get translated text
        const translatedText = this.clientI18n.t(key, parsedParams);
        
        // Handle different translation targets
        const target = element.getAttribute('data-i18n-target') || 'textContent';
        
        switch (target) {
            case 'placeholder':
                element.placeholder = translatedText;
                break;
            case 'title':
                element.title = translatedText;
                break;
            case 'alt':
                element.alt = translatedText;
                break;
            case 'innerHTML':
                element.innerHTML = translatedText;
                break;
            case 'textContent':
            default:
                element.textContent = translatedText;
                break;
        }
    }
    
    /**
     * Get current language
     */
    getCurrentLanguage() {
        return this.currentLanguage;
    }
    
    /**
     * Get translation using client-side i18n (for dynamic content)
     */
    t(key, params = {}) {
        if (this.clientI18n) {
            return this.clientI18n.t(key, params);
        }
        
        // Fallback: check server translations
        if (this.serverTranslations.common && key.startsWith('common.')) {
            const subKey = key.substring(7); // Remove 'common.' prefix
            return this.serverTranslations.common[subKey] || key;
        }
        
        return key;
    }
    
    /**
     * Format file size using client-side i18n
     */
    formatFileSize(bytes, decimals = 2) {
        if (this.clientI18n) {
            return this.clientI18n.formatFileSize(bytes, decimals);
        }
        
        // Simple fallback
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }
    
    /**
     * Format date using client-side i18n
     */
    formatDate(date, options = {}) {
        if (this.clientI18n) {
            return this.clientI18n.formatDate(date, options);
        }
        
        // Simple fallback
        const dateObj = date instanceof Date ? date : new Date(date);
        return dateObj.toLocaleDateString();
    }
}

// Create global instance
window.mixedI18n = new MixedI18nHandler();

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.mixedI18n.initialize();
    });
} else {
    window.mixedI18n.initialize();
}

// Export for module usage
export default window.mixedI18n;
