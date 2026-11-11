import { withBasePath } from './basePath.js';

export const OPEN_COMFYUI_SETTINGS_MESSAGE = 'lm:open-comfy-settings';
export const OPEN_COMFYUI_SETTINGS_QUERY = 'lm_open_settings';
export const COMFYUI_SETTINGS_CHANNEL = 'lm:comfyui-settings';
export const DISCOVER_COMFYUI_SETTINGS_MESSAGE = 'lm:discover-comfyui-settings';
export const COMFYUI_SETTINGS_AVAILABLE_MESSAGE = 'lm:comfyui-settings-available';

const EXISTING_TAB_DISCOVERY_MS = 200;

function getSameOriginOpener() {
    try {
        if (window.opener && !window.opener.closed && window.opener.location.origin === window.location.origin) {
            return window.opener;
        }
    } catch (_) {
    }
    return null;
}

function requestExistingComfyUITab() {
    return new Promise((resolve) => {
        if (typeof window.BroadcastChannel !== 'function') {
            resolve(false);
            return;
        }

        let channel;
        try {
            channel = new window.BroadcastChannel(COMFYUI_SETTINGS_CHANNEL);
        } catch (_) {
            resolve(false);
            return;
        }

        const requestId = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
        const candidates = [];
        channel.onmessage = (event) => {
            const data = event.data;
            if (data?.type === COMFYUI_SETTINGS_AVAILABLE_MESSAGE && data.requestId === requestId && typeof data.tabId === 'string') {
                candidates.push(data);
            }
        };

        channel.postMessage({ type: DISCOVER_COMFYUI_SETTINGS_MESSAGE, requestId });
        setTimeout(() => {
            const target = candidates.sort((a, b) => (b.lastActive || 0) - (a.lastActive || 0))[0];
            if (target) {
                channel.postMessage({
                    type: OPEN_COMFYUI_SETTINGS_MESSAGE,
                    targetTabId: target.tabId,
                });
            }
            channel.close();
            resolve(Boolean(target));
        }, EXISTING_TAB_DISCOVERY_MS);
    });
}

export async function openComfyUISettings() {
    let opener = getSameOriginOpener();
    if (opener) {
        try {
            opener.postMessage({ type: OPEN_COMFYUI_SETTINGS_MESSAGE }, window.location.origin);
        } catch (_) {
            opener = null;
        }
    }

    if (opener) {
        try {
            opener.focus();
        } catch (_) {
        }
        return 'opener';
    }

    if (await requestExistingComfyUITab()) {
        return 'existing';
    }

    try {
        const url = new URL(withBasePath('/'), window.location.origin);
        url.searchParams.set(OPEN_COMFYUI_SETTINGS_QUERY, '1');
        return window.open(url.toString(), '_blank') ? 'new' : null;
    } catch (_) {
        return null;
    }
}
