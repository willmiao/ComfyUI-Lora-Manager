/**
 * i18n utility functions for safe translation handling
 */

/**
 * Synchronous translation function.
 * Assumes window.i18n is ready.
 * @param {string} key - Translation key
 * @param {Object} params - Parameters for interpolation
 * @param {string} fallback - Fallback text if translation fails
 * @returns {string} Translated text
 */
export function translate(key, params = {}, fallback = null) {
    if (!window.i18n) {
        console.warn('i18n not available');
        return fallback || key;
    }
    const translation = window.i18n.t(key, params);
    if (translation === key && fallback) {
        return fallback;
    }
    return translation;
}

/**
 * Update element text with translation
 * @param {HTMLElement|string} element - Element or selector
 * @param {string} key - Translation key
 * @param {Object} params - Parameters for interpolation
 * @param {string} fallback - Fallback text
 */
export function updateElementText(element, key, params = {}, fallback = null) {
    const el = typeof element === 'string' ? document.querySelector(element) : element;
    if (!el) return;
    
    const text = translate(key, params, fallback);
    el.textContent = text;
}

/**
 * Update element attribute with translation
 * @param {HTMLElement|string} element - Element or selector
 * @param {string} attribute - Attribute name (e.g., 'title', 'placeholder')
 * @param {string} key - Translation key
 * @param {Object} params - Parameters for interpolation
 * @param {string} fallback - Fallback text
 */
export function updateElementAttribute(element, attribute, key, params = {}, fallback = null) {
    const el = typeof element === 'string' ? document.querySelector(element) : element;
    if (!el) return;
    
    const text = translate(key, params, fallback);
    el.setAttribute(attribute, text);
}

/**
 * Create a reactive translation that updates when language changes
 * @param {string} key - Translation key
 * @param {Object} params - Parameters for interpolation
 * @param {Function} callback - Callback function to call with translated text
 */
export function createReactiveTranslation(key, params = {}, callback) {
    let currentLanguage = null;
    
    const updateTranslation = () => {
        if (!window.i18n) return;
        
        const newLanguage = window.i18n.getCurrentLocale();
        
        // Only update if language changed or first time
        if (newLanguage !== currentLanguage) {
            currentLanguage = newLanguage;
            const translation = window.i18n.t(key, params);
            callback(translation);
        }
    };
    
    // Initial update
    updateTranslation();
    
    // Listen for language changes
    window.addEventListener('languageChanged', updateTranslation);
    window.addEventListener('i18nReady', updateTranslation);
    
    // Return cleanup function
    return () => {
        window.removeEventListener('languageChanged', updateTranslation);
        window.removeEventListener('i18nReady', updateTranslation);
    };
}

/**
 * Batch update multiple elements with translations
 * @param {Array} updates - Array of update configurations
 * Each update should have: { element, key, type: 'text'|'attribute', attribute?, params?, fallback? }
 */
export function batchUpdateTranslations(updates) {
    if (!window.i18n) return;
    
    for (const update of updates) {
        const { element, key, type = 'text', attribute, params = {}, fallback } = update;
        
        if (type === 'text') {
            updateElementText(element, key, params, fallback);
        } else if (type === 'attribute' && attribute) {
            updateElementAttribute(element, attribute, key, params, fallback);
        }
    }
}