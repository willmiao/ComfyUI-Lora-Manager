/**
 * Internationalization (i18n) system for LoRA Manager
 * Automatically detects browser language and provides fallback to English
 */

import { en } from './locales/en.js';
import { zhCN } from './locales/zh-CN.js';

class I18nManager {
    constructor() {
        this.locales = {
            'en': en,
            'zh-CN': zhCN,
            'zh': zhCN, // Fallback for 'zh' to 'zh-CN'
        };
        
        this.currentLocale = this.detectLanguage();
        this.translations = this.locales[this.currentLocale] || this.locales['en'];
    }
    
    /**
     * Detect browser language with fallback to English
     * @returns {string} Language code
     */
    detectLanguage() {
        // Get browser language
        const browserLang = navigator.language || navigator.languages[0] || 'en';
        
        // Check if we have exact match
        if (this.locales[browserLang]) {
            return browserLang;
        }
        
        // Check for language without region (e.g., 'zh' from 'zh-CN')
        const langCode = browserLang.split('-')[0];
        if (this.locales[langCode]) {
            return langCode;
        }
        
        // Fallback to English
        return 'en';
    }
    
    /**
     * Get translation for a key with optional parameters
     * @param {string} key - Translation key (supports dot notation)
     * @param {Object} params - Parameters for string interpolation
     * @returns {string} Translated text
     */
    t(key, params = {}) {
        const keys = key.split('.');
        let value = this.translations;
        
        // Navigate through nested object
        for (const k of keys) {
            if (value && typeof value === 'object' && k in value) {
                value = value[k];
            } else {
                // Fallback to English if key not found in current locale
                value = this.locales['en'];
                for (const fallbackKey of keys) {
                    if (value && typeof value === 'object' && fallbackKey in value) {
                        value = value[fallbackKey];
                    } else {
                        console.warn(`Translation key not found: ${key}`);
                        return key; // Return key as fallback
                    }
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
}

// Create singleton instance
export const i18n = new I18nManager();

// Export for global access (will be attached to window)
export default i18n;
