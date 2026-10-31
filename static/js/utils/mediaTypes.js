/**
 * Media type detection for preview URLs.
 *
 * Local previews are served through `/api/lm/previews?path=<encoded path>` and
 * the URL carries a cache-busting `&v=<mtime>` parameter, so the media type
 * cannot be read from the end of the URL string. The path is one of the query
 * parameter values; derive the extension from the decoded path (or any other
 * query value that holds a path) instead.
 */

export const VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mov', '.mkv'];

/**
 * Extract the file extension from a single path fragment, query value or URL.
 * Anything from the first `?`/`#` onwards is dropped so
 * `/previews?path=...mp4&v=123` is treated as `/previews`.
 *
 * @param {*} value
 * @returns {string} Lower-cased extension including the dot, or ''
 */
export function extractMediaExtension(value) {
    if (value == null) {
        return '';
    }

    let candidate = String(value);
    const queryIndex = candidate.search(/[?#]/);
    if (queryIndex !== -1) {
        candidate = candidate.slice(0, queryIndex);
    }
    try {
        candidate = decodeURIComponent(candidate);
    } catch (error) {
        // Ignore malformed escape sequences and fall back to the raw value.
    }

    const lastDot = candidate.lastIndexOf('.');
    if (lastDot === -1) {
        return '';
    }
    const extension = candidate.slice(lastDot).toLowerCase();
    if (extension.includes('/') || extension.includes('\\')) {
        return '';
    }
    return extension;
}

function collectCandidates(url) {
    const candidates = new Set();
    const addCandidate = value => {
        if (value == null) {
            return;
        }
        const stringValue = String(value);
        if (stringValue) {
            candidates.add(stringValue);
        }
    };

    addCandidate(url);

    try {
        const parsed = new URL(url, window.location.origin);
        addCandidate(parsed.pathname);
        parsed.searchParams.forEach(value => addCandidate(value));
    } catch (error) {
        // Ignore parse errors and rely on the raw value.
    }

    // Relative or malformed URLs may fail to parse; splitting on query
    // separators still exposes the encoded path segment.
    String(url).split(/[?&=]/).forEach(fragment => addCandidate(fragment));

    return candidates;
}

/**
 * Best-effort extension of the media file a preview URL points at.
 *
 * @param {string} url
 * @returns {string} Lower-cased extension including the dot, or ''
 */
export function getPreviewMediaExtension(url) {
    if (!url || typeof url !== 'string') {
        return '';
    }

    for (const candidate of collectCandidates(url)) {
        const extension = extractMediaExtension(candidate);
        if (extension) {
            return extension;
        }
    }

    return '';
}

/**
 * Return true when the preview URL points at a video file.
 *
 * Handles plain paths, remote URLs with query strings and the versioned
 * `/api/lm/previews?path=...&v=<mtime>` form used for local previews.
 *
 * @param {string} url
 * @returns {boolean}
 */
export function isVideoPreviewUrl(url) {
    const extension = getPreviewMediaExtension(url);
    return Boolean(extension) && VIDEO_EXTENSIONS.includes(extension);
}
