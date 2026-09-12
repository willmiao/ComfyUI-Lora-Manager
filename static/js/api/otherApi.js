import { BaseModelApiClient } from './baseModelApi.js';

/**
 * Other-models-specific API client (VAE, upscalers, text encoders, etc.)
 */
export class OtherApiClient extends BaseModelApiClient {
    /**
     * Get other-model roots, optionally narrowed to one sub_type
     * (vae/upscaler/text_encoder/clip_vision/controlnet).
     *
     * Without a sub_type this falls back to the merged roots list
     * (GET /api/lm/other/roots); with one it reads the grouped
     * roots_by_subtype map and extracts the matching list.
     */
    async fetchModelRoots(subType = null) {
        if (!subType) {
            return super.fetchModelRoots();
        }

        const data = await this.fetchRootsBySubType();
        const groupedRoots = data.roots_by_subtype || {};
        return {
            success: data.success !== false,
            roots: groupedRoots[subType] || [],
        };
    }

    /**
     * Get other-model roots grouped by sub_type.
     * GET /api/lm/other/roots_by_subtype
     *   -> { success, roots_by_subtype: {sub_type: [...]} }
     */
    async fetchRootsBySubType() {
        try {
            const response = await fetch(this.apiConfig.endpoints.specific.roots_by_subtype);
            if (!response.ok) {
                throw new Error('Failed to fetch other-model roots by sub_type');
            }
            return await response.json();
        } catch (error) {
            console.error('Error fetching other-model roots by sub_type:', error);
            throw error;
        }
    }
}
