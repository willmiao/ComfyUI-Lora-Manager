// ScanScopeMenu.js - per-root entries of the Refresh dropdown (issue #1108)
import { translate } from '../../utils/i18nHelpers.js';

/**
 * Render one row per configured model root.
 *
 * Rows carry the root path in `data-root` and are wired by delegation, because
 * the list is rebuilt every time the root set changes. An offline root stays
 * clickable (the click explains why nothing can be scanned) and is only
 * de-emphasised visually.
 *
 * @param {HTMLElement|null} menu - Container element (#refreshScopeMenu)
 * @param {Array<Object>} details - `root_details` from GET /api/lm/{type}/roots
 */
export function renderScanScopeMenu(menu, details = []) {
    if (!menu) {
        return;
    }
    menu.innerHTML = '';

    details.forEach(detail => {
        if (!detail || !detail.path) {
            return;
        }
        const item = document.createElement('div');
        item.className = `dropdown-item scan-root-item${detail.reachable ? '' : ' is-offline'}`;
        item.dataset.action = 'scan-root';
        item.dataset.root = detail.path;
        item.title = detail.path;

        const icon = document.createElement('i');
        icon.className = `fas ${detail.reachable ? 'fa-folder-open' : 'fa-plug-circle-xmark'}`;
        item.appendChild(icon);

        const label = document.createElement('span');
        label.className = 'scan-root-label';
        label.textContent = detail.label || detail.path;
        item.appendChild(label);

        const meta = document.createElement('span');
        if (detail.reachable) {
            const count = Number(detail.models || 0).toLocaleString();
            meta.className = 'scan-root-count';
            meta.textContent = translate(
                'loras.controls.refresh.rootModels',
                { count },
                `${count} models`
            );
        } else {
            meta.className = 'scan-root-offline';
            meta.textContent = translate('loras.controls.refresh.rootOffline', {}, 'Offline');
        }
        item.appendChild(meta);

        menu.appendChild(item);
    });
}

/**
 * Read what a clicked row refers to.
 * @param {HTMLElement} item - Row rendered by renderScanScopeMenu
 * @returns {{rootPath: string, label: string, offline: boolean}}
 */
export function resolveScanScopeTarget(item) {
    const rootPath = item?.dataset?.root || '';
    const label = item?.querySelector?.('.scan-root-label')?.textContent || rootPath;
    return {
        rootPath,
        label,
        offline: Boolean(item?.classList?.contains('is-offline')),
    };
}
