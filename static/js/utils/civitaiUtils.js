/**
 * CivitAI URL utilities
 * Functions for working with CivitAI media URLs
 */

/**
 * Optimization strategies for CivitAI URLs
 */
export const OptimizationMode = {
    /** Full quality for showcase/display - uses /optimized=true only */
    SHOWCASE: 'showcase',
    /** Thumbnail size for cards - uses /width=450,optimized=true */
    THUMBNAIL: 'thumbnail',
};

export const DEFAULT_CIVITAI_PAGE_HOST = 'civitai.com';

const SUPPORTED_CIVITAI_PAGE_HOSTS = new Set([
    'civitai.com',
    'civitai.red',
]);

export function normalizeCivitaiPageHost(hostname) {
    if (!hostname || typeof hostname !== 'string') {
        return DEFAULT_CIVITAI_PAGE_HOST;
    }

    const normalized = hostname.trim().toLowerCase();
    if (SUPPORTED_CIVITAI_PAGE_HOSTS.has(normalized)) {
        return normalized;
    }

    return DEFAULT_CIVITAI_PAGE_HOST;
}

export function buildCivitaiModelUrl(modelId, versionId = null, host = DEFAULT_CIVITAI_PAGE_HOST) {
    const normalizedHost = normalizeCivitaiPageHost(host);
    const normalizedModelId = modelId == null ? '' : String(modelId).trim();
    const normalizedVersionId = versionId == null ? '' : String(versionId).trim();

    if (normalizedModelId) {
        const encodedModelId = encodeURIComponent(normalizedModelId);
        let url = `https://${normalizedHost}/models/${encodedModelId}`;
        if (normalizedVersionId) {
            url += `?modelVersionId=${encodeURIComponent(normalizedVersionId)}`;
        }
        return url;
    }

    if (normalizedVersionId) {
        return `https://${normalizedHost}/model-versions/${encodeURIComponent(normalizedVersionId)}`;
    }

    return null;
}

export function buildCivitaiSearchUrl(query, host = DEFAULT_CIVITAI_PAGE_HOST) {
    const normalizedQuery = query == null ? '' : String(query).trim();
    if (!normalizedQuery) {
        return null;
    }

    const normalizedHost = normalizeCivitaiPageHost(host);
    return `https://${normalizedHost}/models?query=${encodeURIComponent(normalizedQuery)}`;
}

export function buildCivitaiUrl({ modelId = null, versionId = null, modelName = null, host = DEFAULT_CIVITAI_PAGE_HOST } = {}) {
    return (
        buildCivitaiModelUrl(modelId, versionId, host)
        || buildCivitaiSearchUrl(modelName, host)
    );
}

/**
 * Rewrite Civitai preview URLs to use optimized renditions.
 * Mirrors the backend's rewrite_preview_url() function from py/utils/civitai_utils.py
 *
 * @param {string|null} sourceUrl - Original preview URL from the Civitai API
 * @param {string|null} mediaType - Optional media type hint ("image" or "video")
 * @param {string} mode - Optimization mode ('showcase' or 'thumbnail')
 * @returns {[string|null, boolean]} - Tuple of [rewritten URL or original, wasRewritten flag]
 */
export function rewriteCivitaiUrl(sourceUrl, mediaType = null, mode = OptimizationMode.THUMBNAIL) {
    if (!sourceUrl) {
        return [sourceUrl, false];
    }

    try {
        const url = new URL(sourceUrl);
        
        // Check if it's a CivitAI CDN domain (supports all subdomains like image-b2.civitai.com)
        const hostname = url.hostname.toLowerCase();
        if (hostname === 'civitai.com' || !hostname.endsWith('.civitai.com')) {
            return [sourceUrl, false];
        }

        // Determine replacement based on mode and media type
        let replacement;
        if (mode === OptimizationMode.SHOWCASE) {
            // Full quality for showcase - no width restriction
            replacement = '/optimized=true';
        } else {
            // Thumbnail mode with width restriction
            replacement = '/width=450,optimized=true';
            if (mediaType && mediaType.toLowerCase() === 'video') {
                replacement = '/transcode=true,width=450,optimized=true';
            }
        }

        // Replace /original=true with optimized version
        if (!url.pathname.includes('/original=true')) {
            return [sourceUrl, false];
        }

        const updatedPath = url.pathname.replace('/original=true', replacement, 1);
        
        if (updatedPath === url.pathname) {
            return [sourceUrl, false];
        }

        url.pathname = updatedPath;
        return [url.toString(), true];
    } catch (e) {
        // Invalid URL
        return [sourceUrl, false];
    }
}

/**
 * Get the optimized URL for a media item, falling back to original if not a CivitAI URL
 *
 * @param {string} url - Original URL
 * @param {string} type - Media type ("image" or "video")
 * @param {string} mode - Optimization mode ('showcase' or 'thumbnail')
 * @returns {string} - Optimized URL or original URL
 */
export function getOptimizedUrl(url, type = 'image', mode = OptimizationMode.THUMBNAIL) {
    const [optimizedUrl] = rewriteCivitaiUrl(url, type, mode);
    return optimizedUrl || url;
}

/**
 * Get showcase-optimized URL (full quality)
 * 
 * @param {string} url - Original URL
 * @param {string} type - Media type ("image" or "video")
 * @returns {string} - Optimized URL for showcase display
 */
export function getShowcaseUrl(url, type = 'image') {
    return getOptimizedUrl(url, type, OptimizationMode.SHOWCASE);
}

/**
 * Get thumbnail-optimized URL (width=450)
 * 
 * @param {string} url - Original URL
 * @param {string} type - Media type ("image" or "video")
 * @returns {string} - Optimized URL for thumbnail display
 */
export function getThumbnailUrl(url, type = 'image') {
    return getOptimizedUrl(url, type, OptimizationMode.THUMBNAIL);
}

/**
 * Check if a URL is from CivitAI
 *
 * @param {string} url - URL to check
 * @returns {boolean} - True if it's a CivitAI URL
 */
export function isCivitaiUrl(url) {
    if (!url) return false;
    try {
        const parsed = new URL(url);
        const hostname = parsed.hostname.toLowerCase();
        return hostname.endsWith('.civitai.com') && hostname !== 'civitai.com';
    } catch (e) {
        return false;
    }
}

export function isSupportedCivitaiPageHost(hostname) {
    if (!hostname) {
        return false;
    }

    return SUPPORTED_CIVITAI_PAGE_HOSTS.has(hostname.toLowerCase());
}

export function extractCivitaiModelUrlParts(url) {
    if (!url) {
        return { modelId: null, modelVersionId: null };
    }

    try {
        const parsedUrl = new URL(url);
        if (!isSupportedCivitaiPageHost(parsedUrl.hostname)) {
            return { modelId: null, modelVersionId: null };
        }

        const pathMatch = parsedUrl.pathname.match(/\/models\/(\d+)/);
        const modelId = pathMatch ? pathMatch[1] : null;
        const modelVersionId = parsedUrl.searchParams.get('modelVersionId');

        return { modelId, modelVersionId };
    } catch (e) {
        return { modelId: null, modelVersionId: null };
    }
}

export function extractCivitaiImageId(url) {
    if (!url) {
        return null;
    }

    try {
        const parsedUrl = new URL(url);
        if (!isSupportedCivitaiPageHost(parsedUrl.hostname)) {
            return null;
        }

        const pathMatch = parsedUrl.pathname.match(/\/images\/(\d+)/);
        return pathMatch ? pathMatch[1] : null;
    } catch (e) {
        return null;
    }
}
