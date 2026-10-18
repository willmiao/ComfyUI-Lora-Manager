/**
 * Software-rendering detection for degrading expensive visual effects.
 *
 * With hardware acceleration disabled (or a GPU blocklisted), Chrome rasterizes
 * in software. A full-viewport `backdrop-filter: blur()` then forces a per-frame
 * CPU blur over everything painted behind the modal, freezing the entire
 * browser (issue #1092). When software rendering is detected we add the
 * `no-modal-backdrop-blur` class to <html>, and CSS drops the backdrop blur.
 */

const SOFTWARE_RENDERER_PATTERN = /swiftshader|llvmpipe|softpipe|software|basic render/i;

/**
 * Check a WebGL renderer string against known software rasterizers.
 * @param {string} renderer - UNMASKED_RENDERER_WEBGL string
 * @returns {boolean}
 */
export function isSoftwareRendererString(renderer) {
    return SOFTWARE_RENDERER_PATTERN.test(renderer || '');
}

/**
 * Read the unmasked WebGL renderer string, or null when unavailable/masked.
 * @returns {string|null}
 */
function getWebGLRendererString() {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (!gl) return null;

    const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
    const renderer = debugInfo
        ? String(gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) || '')
        : '';

    const loseContext = gl.getExtension('WEBGL_lose_context');
    if (loseContext) loseContext.loseContext();

    return renderer || null;
}

/**
 * Heuristic: is the browser rasterizing in software?
 * - No WebGL at all: no evidence of GPU acceleration, assume software.
 * - Masked renderer string or detection failure: cannot tell, keep effects on.
 * @returns {boolean}
 */
export function isSoftwareRendering() {
    try {
        const renderer = getWebGLRendererString();
        if (renderer === null) {
            return true;
        }
        return isSoftwareRendererString(renderer);
    } catch (error) {
        return true;
    }
}

/**
 * Toggle the blur-disabling class on <html>. Runs once at app startup.
 * @param {boolean} [isSoftware] - Override for tests; defaults to detection.
 */
export function applyModalBackdropBlurPolicy(isSoftware = isSoftwareRendering()) {
    document.documentElement.classList.toggle('no-modal-backdrop-blur', isSoftware);
}
