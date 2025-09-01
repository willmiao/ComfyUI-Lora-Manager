/**
 * i18n System Test
 * Simple test to verify internationalization functionality
 */

import { i18n } from '../i18n/index.js';
import { initializePageI18n, t, formatFileSize, formatDate, formatNumber } from '../utils/i18nHelpers.js';
import { findUnusedTranslationKeys, findMissingTranslationKeys, extractLeafKeys } from '../i18n/validator.js';

// Mock DOM elements for testing
function createMockDOM() {
    // Create a test container
    const container = document.createElement('div');
    container.innerHTML = `
        <div data-i18n="header.appTitle">LoRA Manager</div>
        <input data-i18n="header.search.placeholder" data-i18n-target="placeholder" placeholder="Search..." />
        <button data-i18n="common.actions.save">Save</button>
        <span data-i18n="loras.bulkOperations.selected" data-i18n-params='{"count": 5}'>5 selected</span>
    `;
    document.body.appendChild(container);
    return container;
}

// Test basic translation functionality
function testBasicTranslation() {
    console.log('=== Testing Basic Translation ===');
    
    // Test simple translation
    const saveText = t('common.actions.save');
    console.log(`Save button text: ${saveText}`);
    
    // Test translation with parameters
    const selectedText = t('loras.bulkOperations.selected', { count: 3 });
    console.log(`Selection text: ${selectedText}`);
    
    // Test non-existent key (should return the key itself)
    const missingKey = t('non.existent.key');
    console.log(`Missing key: ${missingKey}`);
}

// Test DOM translation
function testDOMTranslation() {
    console.log('=== Testing DOM Translation ===');
    
    const container = createMockDOM();
    
    // Apply translations
    initializePageI18n();
    
    // Check if translations were applied
    const titleElement = container.querySelector('[data-i18n="header.appTitle"]');
    const inputElement = container.querySelector('input[data-i18n="header.search.placeholder"]');
    const buttonElement = container.querySelector('[data-i18n="common.actions.save"]');
    
    console.log(`Title: ${titleElement.textContent}`);
    console.log(`Input placeholder: ${inputElement.placeholder}`);
    console.log(`Button: ${buttonElement.textContent}`);
    
    // Clean up
    document.body.removeChild(container);
}

// Test formatting functions
function testFormatting() {
    console.log('=== Testing Formatting Functions ===');
    
    // Test file size formatting
    const sizes = [0, 1024, 1048576, 1073741824];
    sizes.forEach(size => {
        const formatted = formatFileSize(size);
        console.log(`${size} bytes = ${formatted}`);
    });
    
    // Test date formatting
    const date = new Date('2024-01-15T10:30:00');
    const formattedDate = formatDate(date, { 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric' 
    });
    console.log(`Date: ${formattedDate}`);
    
    // Test number formatting
    const number = 1234.567;
    const formattedNumber = formatNumber(number, { 
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
    console.log(`Number: ${formattedNumber}`);
}

// Test language detection
function testLanguageDetection() {
    console.log('=== Testing Language Detection ===');
    console.log(`Detected language: ${i18n.getCurrentLocale()}`);
    console.log(`Is RTL: ${i18n.isRTL()}`);
    console.log(`Browser language: ${navigator.language}`);
}

// Test unused translations detection
function testUnusedTranslationsDetection() {
    console.log('=== Testing Unused Translations Detection ===');
    
    // Mock used keys
    const mockUsedKeys = [
        'common.actions.save',
        'common.actions.cancel',
        'header.appTitle'
    ];
    
    // Get all translations
    const allTranslations = i18n.getTranslations();
    
    // Find unused keys (only considering leaf nodes)
    const unusedKeys = findUnusedTranslationKeys(allTranslations, mockUsedKeys);
    
    console.log(`Found ${unusedKeys.length} unused translation keys`);
    console.log('First 5 unused keys:', unusedKeys.slice(0, 5));
    
    // Find missing keys
    const missingKeys = findMissingTranslationKeys(allTranslations, [
        ...mockUsedKeys,
        'non.existent.key'
    ]);
    
    console.log(`Found ${missingKeys.length} missing translation keys:`, missingKeys);
}

// Run all tests
function runTests() {
    console.log('Starting i18n System Tests...');
    console.log('=====================================');
    
    testLanguageDetection();
    testBasicTranslation();
    testFormatting();
    
    // Only test DOM if we're in a browser environment
    if (typeof document !== 'undefined') {
        testDOMTranslation();
    }
    
    // Test unused translations detection
    testUnusedTranslationsDetection();
    
    console.log('=====================================');
    console.log('i18n System Tests Completed!');
}

// Export for manual testing
export { runTests };

// Auto-run tests if this module is loaded directly
if (typeof window !== 'undefined' && window.location.search.includes('test=i18n')) {
    document.addEventListener('DOMContentLoaded', runTests);
}
