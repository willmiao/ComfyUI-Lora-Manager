import { getModelApiClient, resetAndReload } from '../api/modelApiFactory.js';
import { state } from '../state/index.js';
import { showToast } from '../utils/uiHelpers.js';

let currentResource = null;

function resourceForPath(filePath) {
    return state.virtualScroller?.items?.find((item) => item.file_path === filePath);
}

function renderKeys(filter = '') {
    const list = document.getElementById('wildcardKeyList');
    if (!list || !currentResource) return;
    const normalized = filter.toLowerCase();
    const entries = (currentResource.entries || []).filter((entry) =>
        `${entry.effective_key || entry.key} ${entry.source_path}`.toLowerCase().includes(normalized)
    ).slice(0, 300);
    list.replaceChildren(...entries.map((entry) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'wildcard-key-row';
        button.textContent = `${entry.effective_key || entry.key} · ${entry.values_count}`;
        button.title = entry.source_path;
        button.addEventListener('click', async () => {
            const preview = document.getElementById('wildcardContentPreview');
            preview.textContent = 'Loading...';
            try {
                const data = await getModelApiClient().fetchEntryValues(currentResource.file_path, entry.key);
                preview.textContent = data.values.join('\n');
            } catch (error) {
                preview.textContent = error.message;
            }
        });
        return button;
    }));
}

export async function openWildcardDetails(filePath, forActivation = false) {
    currentResource = resourceForPath(filePath);
    if (!currentResource) throw new Error('Wildcard resource is not loaded');
    document.getElementById('wildcardActivationTitle').textContent = currentResource.model_name;
    document.getElementById('wildcardActivationSubtitle').textContent = `${currentResource.file_name} · ${currentResource.entry_count || 0} keys`;
    document.getElementById('wildcardActivationFields').hidden = !forActivation;
    document.getElementById('wildcardActivateBtn').hidden = !forActivation;
    document.getElementById('wildcardActivationErrors').hidden = true;
    document.getElementById('wildcardNamespaceInput').value = currentResource.activation_namespace || '';
    const single = (currentResource.entries || []).length === 1;
    document.getElementById('wildcardAliasGroup').hidden = !single;
    document.getElementById('wildcardAliasInput').value = single ? currentResource.entries[0].key : '';
    document.getElementById('wildcardKeyFilter').value = '';
    renderKeys();
    document.getElementById('wildcardContentPreview').textContent = '';
    window.modalManager.showModal('wildcardActivationModal');
    if (currentResource.files?.length) {
        try {
            const data = await getModelApiClient().fetchSource(filePath, currentResource.files[0]);
            document.getElementById('wildcardContentPreview').textContent = data.content;
        } catch (error) {
            document.getElementById('wildcardContentPreview').textContent = error.message;
        }
    }
}

export async function activateWildcard(filePath) {
    const resource = resourceForPath(filePath);
    const aliases = {};
    if ((resource.entries || []).length === 1) {
        aliases[resource.entries[0].key] = document.getElementById('wildcardAliasInput').value;
    }
    try {
        await getModelApiClient().activate(
            filePath,
            document.getElementById('wildcardNamespaceInput').value,
            aliases,
        );
        window.modalManager.closeModal('wildcardActivationModal');
        showToast('wildcards.messages.activated', {}, 'success');
        await resetAndReload(false);
    } catch (error) {
        const target = document.getElementById('wildcardActivationErrors');
        const conflicts = error.payload?.conflicts || [];
        target.hidden = false;
        target.textContent = conflicts.length
            ? conflicts.map((item) => `${item.key}: ${item.owners.map((owner) => owner.resource_id).join(', ')}`).join('\n')
            : error.message;
    }
}

export async function deactivateWildcard(filePath) {
    await getModelApiClient().deactivate(filePath);
    showToast('wildcards.messages.deactivated', {}, 'success');
    await resetAndReload(false);
}

export function initializeWildcardDetails() {
    const modal = document.getElementById('wildcardActivationModal');
    if (!modal) return;
    modal.querySelectorAll('.close-modal').forEach((button) => {
        button.addEventListener('click', () => window.modalManager.closeModal('wildcardActivationModal'));
    });
    document.getElementById('wildcardKeyFilter').addEventListener('input', (event) => renderKeys(event.target.value));
    document.getElementById('wildcardActivateBtn').addEventListener('click', () => activateWildcard(currentResource.file_path));
}
