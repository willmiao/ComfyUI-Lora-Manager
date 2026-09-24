/**
 * Base-path helpers for code running inside the ComfyUI page.
 *
 * When ComfyUI is served under a URL subpath by a reverse proxy (e.g.
 * llama-swap serves it at "/comfyui/", SwarmUI at "/ComfyBackendDirect/"),
 * the ComfyUI SPA always sits at the root of that prefix, so the prefix is
 * the current pathname without the trailing slash — the same convention the
 * ComfyUI frontend uses for its own api_base. Proxies strip the prefix and
 * forward no headers, so the page URL is the only place to learn it.
 */

export function getComfyUIBasePath() {
    const { pathname } = window.location;
    return pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
}

export function lmUrl(path) {
    return `${getComfyUIBasePath()}${path}`;
}
