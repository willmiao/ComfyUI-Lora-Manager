import { modalManager } from '../managers/ModalManager.js';
import { getModelApiClient, resetAndReload } from '../api/modelApiFactory.js';
import { showActionToast } from './uiHelpers.js';
import { translate } from './i18nHelpers.js';
import { handleUndoDelete } from './undoHelpers.js';
import { formatFileSize } from '../components/shared/utils.js';

let pendingDeletePath = null;
let pendingDeleteName = null;
let pendingExcludePath = null;

export function showDeleteModal(filePath) {
    pendingDeletePath = filePath;

    const escapedPath = window.CSS && typeof window.CSS.escape === 'function'
        ? window.CSS.escape(filePath)
        : filePath.replace(/["\\]/g, '\\$&');
    const card = document.querySelector(`.model-card[data-filepath="${escapedPath}"]`);
    const modelName = card ? card.dataset.name : filePath.split('/').pop();
    pendingDeleteName = modelName;
    const modal = modalManager.getModal('deleteModal').element;
    const modelInfo = modal.querySelector('.delete-model-info');

    const fileSize = card?.dataset.file_size;
    const sizeLine = fileSize
        ? `<br>${translate('modals.deleteModel.freesSpace', { size: formatFileSize(parseInt(fileSize, 10)) })}`
        : '';

    modelInfo.innerHTML = `
        <strong>Model:</strong> ${modelName}
        <br>
        <strong>File:</strong> ${filePath}
        <br>
        ${translate('modals.deleteModel.recoverableWarning')}${sizeLine}
    `;

    modalManager.showModal('deleteModal');
}

export async function confirmDelete() {
    if (!pendingDeletePath) return;

    try {
        const modelName = pendingDeleteName;
        const result = await getModelApiClient().deleteModel(pendingDeletePath);

        closeDeleteModal();

        if (result?.batch_id) {
            const batchId = result.batch_id;
            showActionToast('toast.undo.deleted', { name: modelName }, 'success', {
                actionText: translate('toast.undo.action'),
                onAction: () => handleUndoDelete(batchId, () => resetAndReload(true)),
            });
        }

        if (window.modelDuplicatesManager) {
            window.modelDuplicatesManager.updateDuplicatesBadgeAfterRefresh();
        }
    } catch (error) {
        console.error('Error deleting model:', error);
        alert(`Error deleting model: ${error}`);
    }
}

export function closeDeleteModal() {
    modalManager.closeModal('deleteModal');
    pendingDeletePath = null;
    pendingDeleteName = null;
}

// Functions for the exclude modal
export function showExcludeModal(filePath) {
    pendingExcludePath = filePath;
    
    const escapedPath = window.CSS && typeof window.CSS.escape === 'function'
        ? window.CSS.escape(filePath)
        : filePath.replace(/["\\]/g, '\\$&');
    const card = document.querySelector(`.model-card[data-filepath="${escapedPath}"]`);
    const modelName = card ? card.dataset.name : filePath.split('/').pop();
    const modal = modalManager.getModal('excludeModal').element;
    const modelInfo = modal.querySelector('.exclude-model-info');
    
    modelInfo.innerHTML = `
        <strong>Model:</strong> ${modelName}
        <br>
        <strong>File:</strong> ${filePath}
    `;
    
    modalManager.showModal('excludeModal');
}

export function closeExcludeModal() {
    modalManager.closeModal('excludeModal');
    pendingExcludePath = null;
}

export async function confirmExclude() {
    if (!pendingExcludePath) return;
    
    try {
        await getModelApiClient().excludeModel(pendingExcludePath);
        
        closeExcludeModal();

        if (window.modelDuplicatesManager) {
            window.modelDuplicatesManager.updateDuplicatesBadgeAfterRefresh();
        }
    } catch (error) {
        console.error('Error excluding model:', error);
    }
}
