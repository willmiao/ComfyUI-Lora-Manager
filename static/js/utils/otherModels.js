/**
 * Shared helpers for the opt-in Other Models feature.
 *
 * Used by the disabled page, the announcement banner and the download modal so
 * that enabling the feature always goes through the same settings API call and
 * lands on the same settings section.
 */

/**
 * Turn on Other Models management and reload so the server-rendered nav and
 * the scanner state pick up the change.
 */
export async function enableOtherModels() {
    const response = await fetch('/api/lm/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enable_other_models: true }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.success === false) {
        throw new Error(data.error || `HTTP ${response.status}`);
    }
    window.location.reload();
}

/**
 * Open the settings modal on the Library section and scroll the Other Models
 * toggle into view. Mirrors DoctorManager's open-settings-syntax-format flow.
 */
export function openOtherModelsSettings() {
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

        document.getElementById('enableOtherModels')?.scrollIntoView({
            behavior: 'smooth',
            block: 'center',
        });
    }, 100);
}
