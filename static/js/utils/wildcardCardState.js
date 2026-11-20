import { state } from '../state/index.js';
import { translate } from './i18nHelpers.js';

/**
 * Reflect a wildcard activation change on the manager grid.
 *
 * Updates the rendered card when it is still in the DOM and the virtual
 * scroller item that recreates cards when rows scroll back into view. Shared by
 * the card toggle and the wildcard modal so both surfaces stay in sync.
 */
export function syncWildcardCardState(filePath, active) {
    if (!filePath) return;

    const scrollerItem = state.virtualScroller?.items?.find(
        (item) => item.file_path === filePath,
    );
    if (scrollerItem) scrollerItem.active = active;

    const card = Array.from(document.querySelectorAll('.model-card')).find(
        (element) => element.dataset.filepath === filePath,
    );
    if (!card) return;

    card.dataset.active = String(active);
    card.classList.toggle('wildcard-active', active);
    const toggle = card.querySelector('[data-wildcard-toggle]');
    if (!toggle) return;
    toggle.classList.toggle('wildcard-toggle-active', active);
    toggle.classList.toggle('wildcard-toggle-idle', !active);
    toggle.title = translate(
        active ? 'wildcards.actions.deactivate' : 'wildcards.actions.activate',
        {},
        active ? 'Deactivate' : 'Activate',
    );
}
