/**
 * NVMe cache actions, backed by the `nvme_cache` custom node's HTTP API.
 *
 * nvme_cache keys everything on a "rel" — a path relative to its unified
 * model root — while this UI only ever knows a model by the absolute path
 * ComfyUI reports. /nvme_cache/api/resolve maps one to the other and reports
 * the file's current cache status, so the roots stay configured in exactly
 * one place: nvme_cache's own config.json.
 *
 * The two card actions are toggles: a model already on NVMe offers Demote
 * instead of Promote, and a pinned model offers Unpin instead of Pin. That
 * needs a status for every card, and the grid is virtualised — so lookups are
 * batched per animation frame and memoised, turning a screenful of cards into
 * a single request.
 *
 * Promoting a large model can require demoting others to make room. The API
 * signals that with a 409 carrying the proposed eviction list; we surface it
 * and only retry with `allow_evict` once the user has agreed.
 */

import { showToast } from './uiHelpers.js';
import { translate } from './i18nHelpers.js';
import { trackJob, trackSync } from './nvmeProgress.js';

const NVME_API = '/nvme_cache/api';

// How many evicted files to name in the confirmation before summarising.
const EVICT_PREVIEW_LIMIT = 8;

// Statuses meaning the file currently lives on NVMe, so the promote action
// flips to demote. Mirrors the `demotable` set in nvme_cache's own UI.
const ON_NVME = new Set(['nvme', 'pinned', 'nvme-only']);

function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const value = bytes / Math.pow(1024, i);
    return `${i === 0 ? value : value.toFixed(1)} ${units[i]}`;
}

function baseName(rel) {
    return rel.split('/').pop();
}

/**
 * POST to an nvme_cache endpoint. Returns {status, ok, data} rather than
 * throwing on 409, because 409 is a normal part of the promote flow.
 */
async function nvmePost(endpoint, body) {
    let response;
    try {
        response = await fetch(`${NVME_API}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    } catch (error) {
        throw new Error(`Could not reach the NVMe cache service: ${error.message}`);
    }

    let data = null;
    try {
        data = await response.json();
    } catch (_) {
        // Non-JSON body (e.g. ComfyUI's 404 page when nvme_cache isn't loaded)
    }

    if (response.status === 404 && !data) {
        throw new Error('NVMe cache service not available (is the nvme_cache node installed?)');
    }
    return { status: response.status, ok: response.ok, data };
}

// ---------------------------------------------------------------------------
// Batched status lookups
// ---------------------------------------------------------------------------

// filePath -> {rel, status} | null. `null` means "not under any cache root",
// which is a stable answer worth remembering.
const statusCache = new Map();

// filePath -> [resolve, ...] for lookups awaiting the next flush.
let pendingPaths = new Map();
let flushScheduled = false;

async function flushPending() {
    flushScheduled = false;
    const batch = pendingPaths;
    pendingPaths = new Map();

    const paths = [...batch.keys()];
    let results = {};
    try {
        const { ok, data } = await nvmePost('/resolve', { paths });
        // A failed batch resolves every waiter to null rather than hanging;
        // callers treat null as "no cache info", which degrades to hiding the
        // NVMe controls instead of showing wrong labels.
        if (ok) results = data?.results || {};
    } catch (error) {
        console.warn('NVMe status lookup failed:', error.message);
    }

    for (const [path, waiters] of batch) {
        const info = results[path] ?? null;
        statusCache.set(path, info);
        for (const resolve of waiters) resolve(info);
    }
}

/**
 * Look up {rel, status} for a model path, batched with every other lookup
 * requested in the same frame. Resolves to null when the path is outside the
 * cache roots or the service is unreachable.
 * @param {string} filePath Absolute path as reported by ComfyUI.
 */
export function getNvmeStatus(filePath) {
    if (!filePath) return Promise.resolve(null);
    if (statusCache.has(filePath)) {
        return Promise.resolve(statusCache.get(filePath));
    }
    return new Promise((resolve) => {
        const waiters = pendingPaths.get(filePath);
        if (waiters) {
            waiters.push(resolve);
        } else {
            pendingPaths.set(filePath, [resolve]);
        }
        if (!flushScheduled) {
            flushScheduled = true;
            requestAnimationFrame(flushPending);
        }
    });
}

/**
 * Forget a cached status after an action changed it, so the next lookup asks
 * the server again. Promotes and HDD-side pins finish on a background job, so
 * the fresh answer may still be the old one until that job lands.
 */
export function invalidateNvmeStatus(filePath) {
    statusCache.delete(filePath);
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

function confirmEviction(plan, detail) {
    const shown = plan.to_evict.slice(0, EVICT_PREVIEW_LIMIT);
    const remainder = plan.to_evict.length - shown.length;
    const preview = shown.join('\n') + (remainder > 0 ? `\n…and ${remainder} more` : '');
    return window.confirm(
        `${detail}\n\n` +
        `${plan.to_evict.length} file(s) (${formatBytes(plan.total_freed)}) ` +
        `will be demoted to make room for ${formatBytes(plan.promotion_size)}:\n\n${preview}`
    );
}

/**
 * Run `op` for a model, handling the eviction 409 by asking the user first.
 * `extra` is merged into the request body (e.g. a batch's `exclude` list).
 * Returns the final response, or null if the user declined.
 */
async function runWithEvictionPrompt(op, rel, detail, extra = {}) {
    let result = await nvmePost(op, { rel, ...extra });
    if (result.status === 409 && result.data?.eviction_required) {
        if (!confirmEviction(result.data, detail)) return null;
        result = await nvmePost(op, { rel, ...extra, allow_evict: result.data.to_evict });
    }
    if (!result.ok) {
        throw new Error(result.data?.error || `Request failed (HTTP ${result.status})`);
    }
    return result;
}

/**
 * Resolve a path and guard the statuses no action can handle.
 * Returns {rel, status} or null if the caller should stop.
 */
async function prepare(filePath) {
    const info = await getNvmeStatus(filePath);
    if (!info) {
        showToast('This model is not managed by the NVMe cache', {}, 'error');
        return null;
    }
    if (info.status === 'missing') {
        showToast(`${baseName(info.rel)} was not found on disk`, {}, 'error');
        return null;
    }
    if (info.status === 'unadopted') {
        showToast(
            `${baseName(info.rel)} is not tracked by the cache yet — adopt it in the NVMe Cache tab`,
            {}, 'warning'
        );
        return null;
    }
    return info;
}

/**
 * Copy a model onto the NVMe cache, or remove it again if it is already
 * there. The direction follows the model's current status.
 * @param {string} filePath Absolute path as reported by ComfyUI.
 */
export async function togglePromoteNvme(filePath) {
    try {
        const info = await prepare(filePath);
        if (!info) return;
        const { rel, status } = info;
        const name = baseName(rel);

        if (ON_NVME.has(status)) {
            // Demoting an nvme-only file copies it back to the HDD first,
            // which is slow and worth agreeing to.
            if (status === 'nvme-only' && !window.confirm(
                `"${rel}" has no HDD copy.\n\n` +
                'It will be backed up to the HDD first, then removed from NVMe.'
            )) {
                return;
            }
            // Demote is synchronous server-side, so there is no job to poll —
            // the row runs for as long as the request does.
            await trackSync('Demoting', name, (async () => {
                const { ok, data } = await nvmePost('/demote', { rel });
                if (!ok) throw new Error(data?.error || 'Demote failed');
            })());
            invalidateNvmeStatus(filePath);
            showToast(`Demoted ${name} from NVMe`, {}, 'success');
            return;
        }

        const result = await runWithEvictionPrompt(
            '/promote', rel, `Promoting ${name} needs more space than the cache has free.`
        );
        if (!result) return;
        invalidateNvmeStatus(filePath);
        showToast(`Promoting ${name} to NVMe`, {}, 'info');
        if (result.data?.job_id) {
            const ok = await trackJob(result.data.job_id, 'Promoting', name);
            invalidateNvmeStatus(filePath);
            showToast(
                ok ? `Promoted ${name} to NVMe` : `Promoting ${name} failed`,
                {}, ok ? 'success' : 'error'
            );
        }
    } catch (error) {
        console.error('NVMe promote/demote failed:', error);
        showToast(`NVMe action failed: ${error.message}`, {}, 'error');
    }
}

/**
 * Pin a model so it is never evicted, or unpin it if it is already pinned.
 * Pinning a model still on the HDD promotes it first, as a background job.
 * @param {string} filePath Absolute path as reported by ComfyUI.
 */
export async function togglePinNvme(filePath) {
    try {
        const info = await prepare(filePath);
        if (!info) return;
        const { rel, status } = info;
        const name = baseName(rel);

        if (status === 'pinned') {
            await trackSync('Unpinning', name, (async () => {
                const { ok, data } = await nvmePost('/unpin', { rel });
                if (!ok) throw new Error(data?.error || 'Unpin failed');
            })());
            invalidateNvmeStatus(filePath);
            showToast(`Unpinned ${name} — it can be evicted again`, {}, 'success');
            return;
        }

        const result = await runWithEvictionPrompt(
            '/pin', rel, `Pinning ${name} has to promote it first, and the cache is full.`
        );
        if (!result) return;
        invalidateNvmeStatus(filePath);

        // Already-cached files are pinned by a synchronous flag flip; files
        // still on the HDD have to be copied first, which returns a job id.
        if (result.data?.job_id) {
            showToast(`Pinning ${name} — promoting it to NVMe first`, {}, 'info');
            const ok = await trackJob(result.data.job_id, 'Pinning', name);
            invalidateNvmeStatus(filePath);
            showToast(
                ok ? `Pinned ${name} to NVMe` : `Pinning ${name} failed`,
                {}, ok ? 'success' : 'error'
            );
        } else {
            showToast(`Pinned ${name} to NVMe`, {}, 'success');
        }
    } catch (error) {
        console.error('NVMe pin/unpin failed:', error);
        showToast(`NVMe action failed: ${error.message}`, {}, 'error');
    }
}

/**
 * Pin several models at once, for bulk mode. Models already pinned, or that
 * the cache cannot act on, are skipped and counted in the closing summary.
 *
 * Models already on NVMe are pinned first: that is a synchronous flag flip,
 * and it keeps them from being evicted by the promotions that follow. Models
 * still on the HDD are then pinned one at a time, waiting for each copy to
 * finish, because the server's capacity check only sees the space free when
 * the request arrives. Every model in the batch is passed as `exclude`, so
 * pinning one never evicts another that is waiting its turn.
 * @param {string[]} filePaths Absolute paths as reported by ComfyUI.
 */
export async function pinManyNvme(filePaths) {
    const infos = await Promise.all(filePaths.map(getNvmeStatus));
    const counts = { pinned: 0, alreadyPinned: 0, unmanaged: 0, declined: 0, failed: 0 };
    const targets = [];
    filePaths.forEach((filePath, i) => {
        const info = infos[i];
        if (!info || info.status === 'missing' || info.status === 'unadopted') {
            counts.unmanaged++;
        } else if (info.status === 'pinned') {
            counts.alreadyPinned++;
        } else {
            targets.push({ filePath, ...info });
        }
    });
    targets.sort((a, b) => ON_NVME.has(b.status) - ON_NVME.has(a.status));

    const exclude = targets.map((target) => target.rel);
    for (const [index, { filePath, rel }] of targets.entries()) {
        const name = baseName(rel);
        try {
            const result = await runWithEvictionPrompt(
                '/pin', rel,
                `Pinning ${name} (${index + 1} of ${targets.length}) has to promote it first, and the cache is full.`,
                { exclude }
            );
            if (!result) {
                counts.declined++;
            } else if (result.data?.job_id) {
                const ok = await trackJob(result.data.job_id, 'Pinning', name);
                counts[ok ? 'pinned' : 'failed']++;
            } else {
                counts.pinned++;
            }
        } catch (error) {
            console.error(`NVMe pin failed for ${rel}:`, error);
            counts.failed++;
        } finally {
            invalidateNvmeStatus(filePath);
            const card = [...document.querySelectorAll('.model-card')]
                .find((el) => el.dataset.filepath === filePath);
            if (card) applyNvmeCardState(card);
        }
    }

    const parts = [`Pinned ${counts.pinned} to NVMe`];
    if (counts.alreadyPinned) parts.push(`${counts.alreadyPinned} already pinned`);
    if (counts.unmanaged) parts.push(`${counts.unmanaged} not pinnable (not in the cache roots, missing, or not adopted)`);
    if (counts.declined) parts.push(`${counts.declined} skipped (eviction declined)`);
    if (counts.failed) parts.push(`${counts.failed} failed`);
    const type = counts.failed ? (counts.pinned ? 'warning' : 'error') : 'success';
    showToast(parts.join(', '), {}, type);
}

// ---------------------------------------------------------------------------
// Labelling
// ---------------------------------------------------------------------------

/** Which way each action points for a given status, already translated. */
export function nvmeActionLabels(status) {
    const onNvme = ON_NVME.has(status);
    const pinned = status === 'pinned';
    return {
        promote: {
            action: onNvme ? 'demote' : 'promote',
            label: onNvme
                ? translate('loras.contextMenu.demoteFromNvme', {}, 'Demote from NVMe')
                : translate('loras.contextMenu.promoteToNvme', {}, 'Promote to NVMe'),
            title: onNvme
                ? translate('modelCard.actions.demoteFromNvme', {}, 'Demote from NVMe (remove from the fast cache)')
                : translate('modelCard.actions.promoteToNvme', {}, 'Promote to NVMe (copy onto the fast cache)'),
        },
        pin: {
            action: pinned ? 'unpin' : 'pin',
            label: pinned
                ? translate('loras.contextMenu.unpinFromNvme', {}, 'Unpin from NVMe')
                : translate('loras.contextMenu.pinToNvme', {}, 'Pin to NVMe'),
            title: pinned
                ? translate('modelCard.actions.unpinFromNvme', {}, 'Unpin from NVMe (allow it to be evicted again)')
                : translate('modelCard.actions.pinToNvme', {}, 'Pin to NVMe (keep on the fast cache, never evict)'),
        },
    };
}

/**
 * Run one of the toggles for a card, with its NVMe icons marked busy for the
 * duration — a promote runs for as long as the copy takes — then relabel them
 * from the now-current status.
 * @param {HTMLElement} card A `.model-card` carrying `data-filepath`.
 * @param {Function} action togglePromoteNvme or togglePinNvme.
 */
export async function runNvmeCardAction(card, action) {
    const icons = [
        card.querySelector('.nvme-promote'),
        card.querySelector('.nvme-pin'),
    ].filter(Boolean);
    icons.forEach((icon) => icon.classList.add('nvme-busy'));
    try {
        await action(card.dataset.filepath);
    } finally {
        icons.forEach((icon) => icon.classList.remove('nvme-busy'));
        applyNvmeCardState(card);
    }
}

/**
 * Point a card's two NVMe icons at the actions its model currently supports,
 * once the batched status lookup lands. Cards whose model the cache does not
 * manage keep their icons hidden.
 * @param {HTMLElement} card A `.model-card` carrying `data-filepath`.
 */
export async function applyNvmeCardState(card) {
    const filePath = card?.dataset?.filepath;
    if (!filePath) return;

    const promoteIcon = card.querySelector('.nvme-promote');
    const pinIcon = card.querySelector('.nvme-pin');
    if (!promoteIcon || !pinIcon) return;

    const info = await getNvmeStatus(filePath);
    // The card may have been recycled by the virtual scroller while we waited.
    if (card.dataset.filepath !== filePath) return;

    if (!info) {
        promoteIcon.style.display = 'none';
        pinIcon.style.display = 'none';
        return;
    }

    const labels = nvmeActionLabels(info.status);
    card.dataset.nvmeStatus = info.status;

    promoteIcon.style.display = '';
    pinIcon.style.display = '';
    promoteIcon.title = labels.promote.title;
    pinIcon.title = labels.pin.title;
    // Demote reads as "send back down"; pinned state reads as a filled pin.
    promoteIcon.classList.toggle('nvme-active', labels.promote.action === 'demote');
    pinIcon.classList.toggle('nvme-active', labels.pin.action === 'unpin');
}
