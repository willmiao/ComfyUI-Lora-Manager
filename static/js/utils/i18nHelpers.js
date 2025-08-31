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
 * Safe translation function that waits for i18n to be ready
 * @param {string} key - Translation key
 * @param {Object} params - Parameters for interpolation
 * @param {string} fallback - Fallback text if translation fails
 * @returns {Promise<string>} Translated text
 */
export async function safeTranslate(key, params = {}, fallback = null) {
    if (!window.i18n) {
        console.warn('i18n not available');
        return fallback || key;
    }
    
    // Wait for i18n to be ready
    await window.i18n.waitForReady();
    
    const translation = window.i18n.t(key, params);
    
    // If translation returned the key (meaning not found), use fallback
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
export async function updateElementText(element, key, params = {}, fallback = null) {
    const el = typeof element === 'string' ? document.querySelector(element) : element;
    if (!el) return;
    
    const text = await safeTranslate(key, params, fallback);
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
export async function updateElementAttribute(element, attribute, key, params = {}, fallback = null) {
    const el = typeof element === 'string' ? document.querySelector(element) : element;
    if (!el) return;
    
    const text = await safeTranslate(key, params, fallback);
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
    
    const updateTranslation = async () => {
        if (!window.i18n) return;
        
        await window.i18n.waitForReady();
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
export async function batchUpdateTranslations(updates) {
    if (!window.i18n) return;
    
    await window.i18n.waitForReady();
    
    for (const update of updates) {
        const { element, key, type = 'text', attribute, params = {}, fallback } = update;
        
        if (type === 'text') {
            await updateElementText(element, key, params, fallback);
        } else if (type === 'attribute' && attribute) {
            await updateElementAttribute(element, attribute, key, params, fallback);
        }
    }
}