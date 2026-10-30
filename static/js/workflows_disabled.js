import { appCore } from './core.js';
import { showToast } from './utils/uiHelpers.js';
import { enableWorkflows, openWorkflowsSettings } from './utils/workflowModels.js';

/**
 * Workflow management is an opt-in feature. While it is disabled this page
 * renders an empty state whose button turns the feature on; the backend then
 * rebuilds the workflow root and starts scanning, so a reload lands on the
 * real page.
 *
 * The same module backs the "enabled but no folder configured" state: both
 * modes point at Settings > Library (the single workflow_path input).
 */
async function handleEnableClick() {
    const button = document.getElementById('enableWorkflowsBtn');
    if (!button || button.disabled) return;

    button.disabled = true;
    try {
        await enableWorkflows();
    } catch (error) {
        button.disabled = false;
        showToast('workflows.disabled.enableFailed', { message: error.message }, 'error');
    }
}

/**
 * Open Settings on the Library section for the "no folder configured" state.
 */
function handleOpenSettingsClick(event) {
    event.preventDefault();
    openWorkflowsSettings();
}

async function initializeWorkflowsDisabledPage() {
    // appCore.initialize() wires the shared header (theme, settings modal,
    // language) so this page is not a dead end.
    await appCore.initialize();

    const button = document.getElementById('enableWorkflowsBtn');
    if (button) {
        button.addEventListener('click', handleEnableClick);
    }

    const settingsButton = document.getElementById('openWorkflowsSettingsBtn');
    if (settingsButton) {
        settingsButton.addEventListener('click', handleOpenSettingsClick);
    }
}

document.addEventListener('DOMContentLoaded', initializeWorkflowsDisabledPage);

export { handleEnableClick as enableWorkflows, initializeWorkflowsDisabledPage };
