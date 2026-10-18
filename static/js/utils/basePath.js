/**
 * Base-path helpers for the manager pages.
 *
 * `window.LM_BASE_PATH` is set by the inline bootstrap in
 * templates/components/base_path_bootstrap.html: it is the reverse-proxy
 * subpath the manager is served under (e.g. "/comfyui"), or "" for normal
 * and standalone deployments.
 */

export function getBasePath() {
    return window.LM_BASE_PATH || '';
}

export function withBasePath(path) {
    return `${getBasePath()}${path}`;
}
