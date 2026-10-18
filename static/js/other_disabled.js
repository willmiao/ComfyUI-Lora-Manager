import { appCore } from './core.js';
import { showToast } from './utils/uiHelpers.js';
import { enableOtherModels, openOtherModelsSettings, openModelPathsSettings } from './utils/otherModels.js';

/**
 * Other Models is an opt-in feature. While it is disabled this page renders an
 * empty state whose button turns the feature on; the backend then rebuilds the
 * other-model roots and starts scanning, so a reload lands on the real page.
 *
 * The same module backs the "enabled but no folders found" state: ComfyUI
 * mode points to the Settings page's Library section, while standalone mode
 * points to the standalone-only Model Paths section (which edits the primary
 * folder_paths) and still offers the settings.json location as a fallback.
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

/**
 * Open Settings on the Model Paths section for the standalone "no folders
 * found" state, so the missing folders can be added directly.
 */
function handleOpenModelPathsSettingsClick(event) {
    event.preventDefault();
    openModelPathsSettings();
}

/**
 * Open the settings.json location from the standalone no-folders state,
 * offered as a fallback next to the Model Paths settings button.
 */
async function handleOpenSettingsFolderClick() {
    const button = document.getElementById('openSettingsFolderBtn');
    if (!button || button.disabled) return;

    button.disabled = true;
    try {
        const response = await fetch('/api/lm/settings/open-location', { method: 'POST' });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }
        if (data.mode === 'clipboard' && data.path) {
            try {
                await navigator.clipboard.writeText(data.path);
                showToast('settings.openSettingsFileLocation.copied', { path: data.path }, 'success');
            } catch (clipboardError) {
                console.warn('Clipboard API not available:', clipboardError);
                showToast('settings.openSettingsFileLocation.clipboardFallback', { path: data.path }, 'info');
            }
        } else {
            showToast('settings.openSettingsFileLocation.success', {}, 'success');
        }
    } catch (error) {
        console.error('Failed to open settings location:', error);
        showToast('settings.openSettingsFileLocation.failed', {}, 'error');
    } finally {
        button.disabled = false;
    }
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

    const modelPathsButton = document.getElementById('openModelPathsSettingsBtn');
    if (modelPathsButton) {
        modelPathsButton.addEventListener('click', handleOpenModelPathsSettingsClick);
    }

    const settingsFolderButton = document.getElementById('openSettingsFolderBtn');
    if (settingsFolderButton) {
        settingsFolderButton.addEventListener('click', handleOpenSettingsFolderClick);
    }
}

document.addEventListener('DOMContentLoaded', initializeOtherDisabledPage);

export { handleEnableClick as enableOtherModels, handleOpenSettingsFolderClick, initializeOtherDisabledPage };
