import { state } from '../state/index.js';

/**
 * Internationalization (i18n) system for LoRA Manager
 * Uses user-selected language from settings with fallback to English
 * Loads JSON translation files dynamically
 */

class I18nManager {
    constructor() {
        this.locales = {};
        this.translations = {};
        this.loadedLocales = new Set();
        this.ready = false;
        this.readyPromise = null;
        
        // Available locales configuration
        this.availableLocales = {
            'en': { name: 'English', nativeName: 'English' },
            'zh-CN': { name: 'Chinese (Simplified)', nativeName: '简体中文' },
            'zh-TW': { name: 'Chinese (Traditional)', nativeName: '繁體中文' },
            'zh': { name: 'Chinese (Simplified)', nativeName: '简体中文' }, // Fallback to zh-CN
            'ru': { name: 'Russian', nativeName: 'Русский' },
            'de': { name: 'German', nativeName: 'Deutsch' },
            'ja': { name: 'Japanese', nativeName: '日本語' },
            'ko': { name: 'Korean', nativeName: '한국어' },
            'fr': { name: 'French', nativeName: 'Français' },
            'es': { name: 'Spanish', nativeName: 'Español' },
            'he': { name: 'Hebrew', nativeName: 'עברית' }
        };
        
        this.currentLocale = this.getLanguageFromSettings();
        
        // Initialize with current locale and create ready promise
        this.readyPromise = this.initializeWithLocale(this.currentLocale);
    }
    
    /**
     * Load translations for a specific locale from JSON file
     * @param {string} locale - The locale to load
     * @returns {Promise<Object>} Promise that resolves to the translation data
     */
    async loadLocale(locale) {
        // Handle fallback for 'zh' to 'zh-CN'
        const normalizedLocale = locale === 'zh' ? 'zh-CN' : locale;
        
        if (this.loadedLocales.has(normalizedLocale)) {
            return this.locales[normalizedLocale];
        }
        
        try {
            const response = await fetch(`/locales/${normalizedLocale}.json`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const translations = await response.json();
            this.locales[normalizedLocale] = translations;
            this.loadedLocales.add(normalizedLocale);
            
            // Also set for 'zh' alias
            if (normalizedLocale === 'zh-CN') {
                this.locales['zh'] = translations;
                this.loadedLocales.add('zh');
            }
            
            return translations;
        } catch (error) {
            console.warn(`Failed to load locale ${normalizedLocale}:`, error);
            // Fallback to English if current locale fails and it's not English
            if (normalizedLocale !== 'en') {
                return this.loadLocale('en');
            }
            // Return empty object if even English fails
            return {};
        }
    }
    
    /**
     * Initialize with a specific locale
     * @param {string} locale - The locale to initialize with
     */
    async initializeWithLocale(locale) {
        try {
            this.translations = await this.loadLocale(locale);
            this.currentLocale = locale;
            this.ready = true;
            
            // Dispatch ready event
            window.dispatchEvent(new CustomEvent('i18nReady', { 
                detail: { language: locale } 
            }));
        } catch (error) {
            console.warn(`Failed to initialize with locale ${locale}, falling back to English`, error);
            this.translations = await this.loadLocale('en');
            this.currentLocale = 'en';
            this.ready = true;
            
            window.dispatchEvent(new CustomEvent('i18nReady', { 
                detail: { language: 'en' } 
            }));
        }
    }
    
    /**
     * Wait for i18n to be ready
     * @returns {Promise} Promise that resolves when i18n is ready
     */
    async waitForReady() {
        if (this.ready) {
            return Promise.resolve();
        }
        return this.readyPromise;
    }
    
    /**
     * Check if i18n is ready
     * @returns {boolean} True if ready
     */
    isReady() {
        return this.ready && this.translations && Object.keys(this.translations).length > 0;
    }
    
    /**
     * Get language from user settings with fallback to English
     * @returns {string} Language code
     */
    getLanguageFromSettings() {
        const language = state?.global?.settings?.language;

        if (language && this.availableLocales[language]) {
            return language;
        }

        return 'en';
    }
    
    /**
     * Set the current language and save to settings
     * @param {string} languageCode - The language code to set
     * @returns {Promise<boolean>} True if language was successfully set
     */
    async setLanguage(languageCode) {
        if (!this.availableLocales[languageCode]) {
            console.warn(`Language '${languageCode}' is not supported`);
            return false;
        }
        
        try {
            // Reset ready state
            this.ready = false;
            
            // Load the new locale
            this.readyPromise = this.initializeWithLocale(languageCode);
            await this.readyPromise;
            
            if (state?.global?.settings) {
                state.global.settings.language = languageCode;
            }
            
            console.log(`Language changed to: ${languageCode}`);
            
            // Dispatch event to notify components of language change
            window.dispatchEvent(new CustomEvent('languageChanged', { 
                detail: { language: languageCode } 
            }));
            
            return true;
        } catch (e) {
            console.error('Failed to set language:', e);
            return false;
        }
    }
    
    /**
     * Get list of available languages with their native names
     * @returns {Array} Array of language objects
     */
    getAvailableLanguages() {
        return Object.entries(this.availableLocales).map(([code, info]) => ({
            code,
            name: info.name,
            nativeName: info.nativeName
        }));
    }
    
    /**
     * Get translation for a key with optional parameters
     * @param {string} key - Translation key (supports dot notation)
     * @param {Object} params - Parameters for string interpolation
     * @returns {string} Translated text
     */
    t(key, params = {}) {
        // If not ready, return key as fallback
        if (!this.isReady()) {
            console.warn(`i18n not ready, returning key: ${key}`);
            return key;
        }
        
        const keys = key.split('.');
        let value = this.translations;
        
        // Navigate through nested object
        for (const k of keys) {
            if (value && typeof value === 'object' && k in value) {
                value = value[k];
            } else {
                // Fallback to English if key not found in current locale
                if (this.currentLocale !== 'en' && this.locales['en']) {
                    let fallbackValue = this.locales['en'];
                    for (const fallbackKey of keys) {
                        if (fallbackValue && typeof fallbackValue === 'object' && fallbackKey in fallbackValue) {
                            fallbackValue = fallbackValue[fallbackKey];
                        } else {
                            console.warn(`Translation key not found: ${key}`);
                            return key; // Return key as fallback
                        }
                    }
                    value = fallbackValue;
                } else {
                    console.warn(`Translation key not found: ${key}`);
                    return key; // Return key as fallback
                }
                break;
            }
        }
        
        if (typeof value !== 'string') {
            console.warn(`Translation key is not a string: ${key}`);
            return key;
        }
        
        // Replace parameters in the string
        return this.interpolate(value, params);
    }
    
    /**
     * Interpolate parameters into a string
     * Supports both {{param}} and {param} syntax
     * @param {string} str - String with placeholders
     * @param {Object} params - Parameters to interpolate
     * @returns {string} Interpolated string
     */
    interpolate(str, params) {
        return str.replace(/\{\{?(\w+)\}?\}/g, (match, key) => {
            return params[key] !== undefined ? params[key] : match;
        });
    }
    
    /**
     * Get current locale
     * @returns {string} Current locale code
     */
    getCurrentLocale() {
        return this.currentLocale;
    }
    
    /**
     * Check if current locale is RTL (Right-to-Left)
     * @returns {boolean} True if RTL
     */
    isRTL() {
        const rtlLocales = ['ar', 'he', 'fa', 'ur'];
        return rtlLocales.includes(this.currentLocale.split('-')[0]);
    }
    
    /**
     * Format number according to current locale
     * @param {number} number - Number to format
     * @param {Object} options - Intl.NumberFormat options
     * @returns {string} Formatted number
     */
    formatNumber(number, options = {}) {
        return new Intl.NumberFormat(this.currentLocale, options).format(number);
    }
    
    /**
     * Format date according to current locale
     * @param {Date|string|number} date - Date to format
     * @param {Object} options - Intl.DateTimeFormat options
     * @returns {string} Formatted date
     */
    formatDate(date, options = {}) {
        const dateObj = date instanceof Date ? date : new Date(date);
        return new Intl.DateTimeFormat(this.currentLocale, options).format(dateObj);
    }
    
    /**
     * Format file size with locale-specific formatting
     * @param {number} bytes - Size in bytes
     * @param {number} decimals - Number of decimal places
     * @returns {string} Formatted size
     */
    formatFileSize(bytes, decimals = 2) {
        if (bytes === 0) return this.t('common.fileSize.zero');
        
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['bytes', 'kb', 'mb', 'gb', 'tb'];
        
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        const size = parseFloat((bytes / Math.pow(k, i)).toFixed(dm));
        
        return `${this.formatNumber(size)} ${this.t(`common.fileSize.${sizes[i]}`)}`;
    }
    
    /**
     * Initialize i18n from user settings
     * This prevents language flashing on page load
     * @deprecated Use waitForReady() instead
     */
    async initializeFromSettings() {
        console.warn('initializeFromSettings() is deprecated, use waitForReady() instead');
        return this.waitForReady();
    }
}

// Create singleton instance
export const i18n = new I18nManager();

// Export for global access (will be attached to window)
export default i18n;
