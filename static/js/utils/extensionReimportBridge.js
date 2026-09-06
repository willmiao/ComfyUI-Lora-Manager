/**
 * Bridge to the companion LoRA Manager browser extension.
 *
 * The extension can re-import recipes sourced from CivitAI image pages with
 * the complete page metadata (internal trpc data scraped with the user's
 * session), fixing recipes that the native import (REST API + EXIF only)
 * saved with 0 LoRAs.
 *
 * Protocol: DOM CustomEvents on `document`; `detail` is ALWAYS a JSON
 * string on both sides.
 *
 *   LM page -> extension: `lm:reimportProbe`, detail `{}`.
 *   extension -> LM page: `lm:reimportProbeResult`,
 *     detail `{supported, licenseValid, extensionVersion?, reason?}`.
 *   LM page -> extension: `lm:reimportViaExtension`,
 *     detail `{requestId, recipes: [{recipeId, imageId, imageUrl, title}]}`.
 *   extension -> LM page: `lm:reimportProgress`,
 *     detail `{requestId, current, total, recipeId, title, status, message?}`.
 *   extension -> LM page: `lm:reimportBatchDone`,
 *     detail `{requestId, completed, failed}`.
 */

const PROBE_EVENT = 'lm:reimportProbe';
const PROBE_RESULT_EVENT = 'lm:reimportProbeResult';
const REIMPORT_EVENT = 'lm:reimportViaExtension';
const PROGRESS_EVENT = 'lm:reimportProgress';
const BATCH_DONE_EVENT = 'lm:reimportBatchDone';

const DEFAULT_PROBE_TIMEOUT_MS = 500;
// Generous batch timeout; any progress event resets it (heartbeat).
const DEFAULT_REIMPORT_TIMEOUT_MS = 3 * 60 * 1000;

// Mirrors py/utils/civitai_utils.py (_SUPPORTED_CIVITAI_PAGE_HOSTS).
const SUPPORTED_CIVITAI_PAGE_HOSTS = new Set([
    'civitai.com',
    'civitai.red',
    'civitai.green',
]);

/**
 * Parse the JSON-string `detail` of a protocol event.
 * @param {CustomEvent} event
 * @returns {object|null} Parsed detail object, or null when absent/invalid.
 */
function parseDetail(event) {
    try {
        const detail = JSON.parse(event?.detail ?? 'null');
        return detail && typeof detail === 'object' ? detail : null;
    } catch {
        return null;
    }
}

/**
 * Dispatch a protocol event with a JSON-stringified detail.
 * @param {string} type - Event name.
 * @param {object} payload - Detail payload (JSON-stringified).
 */
function dispatchProtocolEvent(type, payload) {
    document.dispatchEvent(
        new CustomEvent(type, { detail: JSON.stringify(payload ?? {}) })
    );
}

/**
 * Generate a correlation id for a re-import batch.
 * @returns {string}
 */
function generateRequestId() {
    if (globalThis.crypto?.randomUUID) {
        return globalThis.crypto.randomUUID();
    }
    return `lm-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Probe whether the companion extension is installed and usable.
 *
 * @param {{timeoutMs?: number}} [options]
 * @returns {Promise<{supported: boolean, licenseValid: boolean, extensionVersion?: string, reason?: string}|null>}
 *   Resolves with the probe result, or null when the extension is absent or
 *   too old to answer (timeout).
 */
export function probeExtension({ timeoutMs = DEFAULT_PROBE_TIMEOUT_MS } = {}) {
    return new Promise((resolve) => {
        let settled = false;
        const timer = setTimeout(() => finish(null), timeoutMs);

        const finish = (value) => {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            document.removeEventListener(PROBE_RESULT_EVENT, onResult);
            resolve(value);
        };

        const onResult = (event) => {
            const detail = parseDetail(event);
            if (!detail) return;
            finish({
                supported: Boolean(detail.supported),
                licenseValid: Boolean(detail.licenseValid),
                extensionVersion: detail.extensionVersion,
                reason: detail.reason,
            });
        };

        document.addEventListener(PROBE_RESULT_EVENT, onResult);
        dispatchProtocolEvent(PROBE_EVENT, {});
    });
}

/**
 * Delegate a batch of recipe re-imports to the companion extension.
 *
 * @param {Array<{recipeId: string, imageId: number, imageUrl: string, title: string}>} recipes
 * @param {{onProgress?: (progress: object) => void, timeoutMs?: number}} [options]
 * @returns {Promise<{completed: number, failed: number}>} Resolves on
 *   `lm:reimportBatchDone`; rejects on timeout. Listeners are cleaned up in
 *   all outcomes.
 */
export function delegateReimport(recipes, { onProgress, timeoutMs = DEFAULT_REIMPORT_TIMEOUT_MS } = {}) {
    return new Promise((resolve, reject) => {
        if (!Array.isArray(recipes) || recipes.length === 0) {
            reject(new Error('delegateReimport requires a non-empty recipe list'));
            return;
        }

        const requestId = generateRequestId();
        let settled = false;
        let timer = null;

        const cleanup = () => {
            clearTimeout(timer);
            document.removeEventListener(PROGRESS_EVENT, onProgressEvent);
            document.removeEventListener(BATCH_DONE_EVENT, onBatchDone);
        };
        const succeed = (value) => {
            if (settled) return;
            settled = true;
            cleanup();
            resolve(value);
        };
        const fail = (error) => {
            if (settled) return;
            settled = true;
            cleanup();
            reject(error);
        };
        const armTimer = () => {
            clearTimeout(timer);
            timer = setTimeout(
                () => fail(new Error('Extension re-import timed out')),
                timeoutMs
            );
        };

        const onProgressEvent = (event) => {
            const detail = parseDetail(event);
            if (!detail || detail.requestId !== requestId) return;
            // Heartbeat: any progress for this batch resets the timeout.
            armTimer();
            if (typeof onProgress === 'function') {
                try {
                    onProgress(detail);
                } catch (error) {
                    console.error('[extensionReimportBridge] onProgress callback failed:', error);
                }
            }
        };
        const onBatchDone = (event) => {
            const detail = parseDetail(event);
            if (!detail || detail.requestId !== requestId) return;
            succeed({
                completed: Number.isInteger(detail.completed) ? detail.completed : 0,
                failed: Number.isInteger(detail.failed) ? detail.failed : 0,
            });
        };

        document.addEventListener(PROGRESS_EVENT, onProgressEvent);
        document.addEventListener(BATCH_DONE_EVENT, onBatchDone);
        armTimer();
        dispatchProtocolEvent(REIMPORT_EVENT, { requestId, recipes });
    });
}

/**
 * Extract CivitAI image page info from a recipe source_path.
 * Mirrors py/utils/civitai_utils.py `extract_civitai_image_id`.
 *
 * @param {string|null} sourcePath - Recipe source_path.
 * @returns {{imageId: number, imageUrl: string}|null} Null when the path is
 *   not a `/images/<id>` URL on civitai.com/.red/.green.
 */
export function getCivitaiImageInfo(sourcePath) {
    if (!sourcePath || typeof sourcePath !== 'string') {
        return null;
    }

    let parsed;
    try {
        parsed = new URL(sourcePath);
    } catch {
        return null;
    }

    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
        return null;
    }
    if (!SUPPORTED_CIVITAI_PAGE_HOSTS.has(parsed.hostname.toLowerCase())) {
        return null;
    }

    const pathMatch = parsed.pathname.match(/\/images\/(\d+)/);
    if (!pathMatch) {
        return null;
    }

    return { imageId: Number(pathMatch[1]), imageUrl: sourcePath };
}
