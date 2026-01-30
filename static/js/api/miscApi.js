import { BaseModelApiClient } from './baseModelApi.js';
import { getSessionItem } from '../utils/storageHelpers.js';

export class MiscApiClient extends BaseModelApiClient {
    _addModelSpecificParams(params, pageState) {
        const filterMiscHash = getSessionItem('recipe_to_misc_filterHash');
        const filterMiscHashes = getSessionItem('recipe_to_misc_filterHashes');

        if (filterMiscHash) {
            params.append('misc_hash', filterMiscHash);
        } else if (filterMiscHashes) {
            try {
                if (Array.isArray(filterMiscHashes) && filterMiscHashes.length > 0) {
                    params.append('misc_hashes', filterMiscHashes.join(','));
                }
            } catch (error) {
                console.error('Error parsing misc hashes from session storage:', error);
            }
        }

        if (pageState.subType) {
            params.append('sub_type', pageState.subType);
        }
    }

    async getMiscInfo(filePath) {
        try {
            const response = await fetch(this.apiConfig.endpoints.specific.info, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: filePath })
            });
            if (!response.ok) throw new Error('Failed to fetch misc info');
            return await response.json();
        } catch (error) {
            console.error('Error fetching misc info:', error);
            throw error;
        }
    }

    async getVaeRoots() {
        try {
            const response = await fetch(this.apiConfig.endpoints.specific.vae_roots, { method: 'GET' });
            if (!response.ok) throw new Error('Failed to fetch VAE roots');
            return await response.json();
        } catch (error) {
            console.error('Error fetching VAE roots:', error);
            throw error;
        }
    }

    async getUpscalerRoots() {
        try {
            const response = await fetch(this.apiConfig.endpoints.specific.upscaler_roots, { method: 'GET' });
            if (!response.ok) throw new Error('Failed to fetch upscaler roots');
            return await response.json();
        } catch (error) {
            console.error('Error fetching upscaler roots:', error);
            throw error;
        }
    }
}
