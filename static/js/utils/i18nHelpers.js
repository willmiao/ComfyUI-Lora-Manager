/**
 * DOM utilities for i18n text replacement
 */
import { i18n } from '../i18n/index.js';

/**
 * Replace text content in DOM elements with translations
 * Uses data-i18n attribute to specify translation keys
 */
export function translateDOM() {
    // Find all elements with data-i18n attribute
    const elements = document.querySelectorAll('[data-i18n]');
    
    elements.forEach(element => {
        const key = element.getAttribute('data-i18n');
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
        const translatedText = i18n.t(key, parsedParams);
        
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
    });
}

/**
 * Update placeholder text based on current page
 * @param {string} currentPath - Current page path
 */
export function updateSearchPlaceholder(currentPath) {
    const searchInput = document.getElementById('searchInput');
    if (!searchInput) return;
    
    let placeholderKey = 'header.search.placeholder';
    
    if (currentPath === '/loras') {
        placeholderKey = 'header.search.placeholders.loras';
    } else if (currentPath === '/loras/recipes') {
        placeholderKey = 'header.search.placeholders.recipes';
    } else if (currentPath === '/checkpoints') {
        placeholderKey = 'header.search.placeholders.checkpoints';
    } else if (currentPath === '/embeddings') {
        placeholderKey = 'header.search.placeholders.embeddings';
    }
    
    searchInput.placeholder = i18n.t(placeholderKey);
}

/**
 * Set text content for an element using i18n
 * @param {Element|string} element - DOM element or selector
 * @param {string} key - Translation key
 * @param {Object} params - Translation parameters
 */
export function setTranslatedText(element, key, params = {}) {
    const el = typeof element === 'string' ? document.querySelector(element) : element;
    if (el) {
        el.textContent = i18n.t(key, params);
    }
}

/**
 * Set attribute value for an element using i18n
 * @param {Element|string} element - DOM element or selector
 * @param {string} attribute - Attribute name
 * @param {string} key - Translation key
 * @param {Object} params - Translation parameters
 */
export function setTranslatedAttribute(element, attribute, key, params = {}) {
    const el = typeof element === 'string' ? document.querySelector(element) : element;
    if (el) {
        el.setAttribute(attribute, i18n.t(key, params));
    }
}

/**
 * Create a translated element
 * @param {string} tagName - HTML tag name
 * @param {string} key - Translation key
 * @param {Object} params - Translation parameters
 * @param {Object} attributes - Additional attributes
 * @returns {Element} Created element
 */
export function createTranslatedElement(tagName, key, params = {}, attributes = {}) {
    const element = document.createElement(tagName);
    element.textContent = i18n.t(key, params);
    
    Object.entries(attributes).forEach(([attr, value]) => {
        element.setAttribute(attr, value);
    });
    
    return element;
}

/**
 * Update bulk selection count text
 * @param {number} count - Number of selected items
 */
export function updateBulkSelectionCount(count) {
    const selectedCountElement = document.getElementById('selectedCount');
    if (selectedCountElement) {
        const textNode = selectedCountElement.firstChild;
        if (textNode && textNode.nodeType === Node.TEXT_NODE) {
            textNode.textContent = i18n.t('loras.bulkOperations.selected', { count });
        }
    }
}

/**
 * Format file size with localized units
 * @param {number} bytes - Size in bytes
 * @param {number} decimals - Number of decimal places
 * @returns {string} Formatted size string
 */
export function formatFileSize(bytes, decimals = 2) {
    return i18n.formatFileSize(bytes, decimals);
}

/**
 * Format date with current locale
 * @param {Date|string|number} date - Date to format
 * @param {Object} options - Intl.DateTimeFormat options
 * @returns {string} Formatted date string
 */
export function formatDate(date, options = {}) {
    return i18n.formatDate(date, options);
}

/**
 * Format number with current locale
 * @param {number} number - Number to format
 * @param {Object} options - Intl.NumberFormat options
 * @returns {string} Formatted number string
 */
export function formatNumber(number, options = {}) {
    return i18n.formatNumber(number, options);
}

/**
 * Initialize i18n for the page
 * This should be called after DOM content is loaded
 */
export function initializePageI18n() {
    // Translate all elements with data-i18n attributes
    translateDOM();
    
    // Update search placeholder based on current page
    const currentPath = window.location.pathname;
    updateSearchPlaceholder(currentPath);
    
    // Set document direction for RTL languages
    if (i18n.isRTL()) {
        document.documentElement.setAttribute('dir', 'rtl');
        document.body.classList.add('rtl');
    } else {
        document.documentElement.setAttribute('dir', 'ltr');
        document.body.classList.remove('rtl');
    }
}

/**
 * Helper function to get translation directly
 * @param {string} key - Translation key
 * @param {Object} params - Parameters for interpolation
 * @returns {string} Translated text
 */
export function t(key, params = {}) {
    return i18n.t(key, params);
}
