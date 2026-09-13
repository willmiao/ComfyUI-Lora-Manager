import { appCore } from './core.js';
import { showToast } from './utils/uiHelpers.js';
import { enableOtherModels, openOtherModelsSettings } from './utils/otherModels.js';

/**
 * Other Models is an opt-in feature. While it is disabled this page renders an
 * empty state whose button turns the feature on; the backend then rebuilds the
 * other-model roots and starts scanning, so a reload lands on the real page.
 *
 * The same module backs the "enabled but no folders found" state, where the
 * only useful action is jumping to Settings instead of enabling anything.
 */
async function handleEnableClick() {
    const button = document.getElementById('enableOtherModelsBtn');
    if (!button || button.disabled) return;

    button.disabled = true;
    try {
        await enableOtherModels();
    } catch (error) {
        button.disabled = false;
        showToast('other.disabled.enableFailed', { message: error.message }, 'error');
    }
}

/**
 * Open Settings on the Library section for the "no folders found" state, so a
 * misconfigured install can be fixed without hand-editing unknown keys.
 */
function handleOpenSettingsClick(event) {
    event.preventDefault();
    openOtherModelsSettings();
}

async function initializeOtherDisabledPage() {
    // appCore.initialize() wires the shared header (theme, settings modal,
    // language) so this page is not a dead end.
    await appCore.initialize();

    const button = document.getElementById('enableOtherModelsBtn');
    if (button) {
        button.addEventListener('click', handleEnableClick);
    }

    const settingsButton = document.getElementById('openOtherModelsSettingsBtn');
    if (settingsButton) {
        settingsButton.addEventListener('click', handleOpenSettingsClick);
    }
}

document.addEventListener('DOMContentLoaded', initializeOtherDisabledPage);

export { handleEnableClick as enableOtherModels, initializeOtherDisabledPage };
