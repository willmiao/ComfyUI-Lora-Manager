/**
 * API client for Civitai base model management
 * Handles fetching and refreshing base models from Civitai API
 */

import { showToast } from '../utils/uiHelpers.js';

const BASE_MODEL_ENDPOINTS = {
    getModels: '/api/lm/base-models',
    refresh: '/api/lm/base-models/refresh',
    categories: '/api/lm/base-models/categories',
    cacheStatus: '/api/lm/base-models/cache-status',
};

/**
 * Civitai Base Model API Client
 */
export class CivitaiBaseModelApi {
    constructor() {
        this.cache = null;
        this.cacheTimestamp = null;
    }

    /**
     * Get base models (with caching)
     * @param {boolean} forceRefresh - Force refresh from API
     * @returns {Promise<Object>} Response with models, source, and counts
     */
    async getBaseModels(forceRefresh = false) {
        try {
            const url = new URL(BASE_MODEL_ENDPOINTS.getModels, window.location.origin);
            if (forceRefresh) {
                url.searchParams.append('refresh', 'true');
            }

            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`Failed to fetch base models: ${response.statusText}`);
            }

            const data = await response.json();
            
            if (data.success) {
                this.cache = data.data;
                this.cacheTimestamp = Date.now();
                return data.data;
            } else {
                throw new Error(data.error || 'Failed to fetch base models');
            }
        } catch (error) {
            console.error('Error fetching base models:', error);
            showToast('Failed to fetch base models', { message: error.message }, 'error');
            throw error;
        }
    }

    /**
     * Force refresh base models from Civitai API
     * @returns {Promise<Object>} Refreshed data
     */
    async refreshBaseModels() {
        try {
            const response = await fetch(BASE_MODEL_ENDPOINTS.refresh, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                throw new Error(`Failed to refresh base models: ${response.statusText}`);
            }

            const data = await response.json();
            
            if (data.success) {
                this.cache = data.data;
                this.cacheTimestamp = Date.now();
                showToast('Base models refreshed successfully', {}, 'success');
                return data.data;
            } else {
                throw new Error(data.error || 'Failed to refresh base models');
            }
        } catch (error) {
            console.error('Error refreshing base models:', error);
            showToast('Failed to refresh base models', { message: error.message }, 'error');
            throw error;
        }
    }

    /**
     * Get base model categories
     * @returns {Promise<Object>} Categories with model lists
     */
    async getCategories() {
        try {
            const response = await fetch(BASE_MODEL_ENDPOINTS.categories);
            if (!response.ok) {
                throw new Error(`Failed to fetch categories: ${response.statusText}`);
            }

            const data = await response.json();
            
            if (data.success) {
                return data.data;
            } else {
                throw new Error(data.error || 'Failed to fetch categories');
            }
        } catch (error) {
            console.error('Error fetching categories:', error);
            throw error;
        }
    }

    /**
     * Get cache status
     * @returns {Promise<Object>} Cache status information
     */
    async getCacheStatus() {
        try {
            const response = await fetch(BASE_MODEL_ENDPOINTS.cacheStatus);
            if (!response.ok) {
                throw new Error(`Failed to fetch cache status: ${response.statusText}`);
            }

            const data = await response.json();
            
            if (data.success) {
                return data.data;
            } else {
                throw new Error(data.error || 'Failed to fetch cache status');
            }
        } catch (error) {
            console.error('Error fetching cache status:', error);
            throw error;
        }
    }

    /**
     * Get cached models (if available)
     * @returns {Object|null} Cached data or null
     */
    getCachedModels() {
        return this.cache;
    }

    /**
     * Check if cache is available
     * @returns {boolean}
     */
    hasCache() {
        return this.cache !== null;
    }

    /**
     * Get cache age in milliseconds
     * @returns {number|null} Age in ms or null if no cache
     */
    getCacheAge() {
        if (!this.cacheTimestamp) return null;
        return Date.now() - this.cacheTimestamp;
    }
}

// Export singleton instance
export const civitaiBaseModelApi = new CivitaiBaseModelApi();
