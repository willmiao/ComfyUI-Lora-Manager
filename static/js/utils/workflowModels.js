/**
 * Shared helpers for the opt-in Workflow management feature.
 *
 * Used by the disabled page so that enabling the feature goes through the same
 * settings API call as the Settings modal toggle.
 */

/**
 * Turn on Workflow management and reload so the server-rendered nav and the
 * scanner state pick up the change.
 */
export async function enableWorkflows() {
    const response = await fetch('/api/lm/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enable_workflows: true }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.success === false) {
        throw new Error(data.error || `HTTP ${response.status}`);
    }
    window.location.reload();
}

/**
 * Open the settings modal on the Library section and scroll to the workflow
 * folder input (the empty state only appears when the feature is on), falling
 * back to the enable toggle while the input is hidden.
 */
export function openWorkflowsSettings() {
    const modalManager = window.modalManager;
    if (modalManager && typeof modalManager.showModal === 'function') {
        modalManager.showModal('settingsModal');
    }

    window.setTimeout(() => {
        document.querySelectorAll('.settings-section').forEach((section) => {
            section.classList.remove('active');
        });
        document.getElementById('section-library')?.classList.add('active');

        document.querySelectorAll('.settings-nav-item').forEach((item) => {
            item.classList.remove('active');
        });
        document.querySelector('.settings-nav-item[data-section="library"]')?.classList.add('active');

        const pathInput = document.getElementById('workflowPath');
        const target =
            pathInput && pathInput.offsetParent !== null
                ? pathInput
                : document.getElementById('enableWorkflows');
        target?.scrollIntoView({
            behavior: 'smooth',
            block: 'center',
        });
    }, 100);
}
