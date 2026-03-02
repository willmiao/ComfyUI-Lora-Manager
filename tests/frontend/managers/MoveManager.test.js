import { beforeEach, describe, expect, it, vi } from 'vitest';
import { moveManager } from '../../../static/js/managers/MoveManager.js';
import { state } from '../../../static/js/state/index.js';
import { modalManager } from '../../../static/js/managers/ModalManager.js';
import { getModelApiClient } from '../../../static/js/api/modelApiFactory.js';
import * as storageHelpers from '../../../static/js/utils/storageHelpers.js';

// Mock dependencies
vi.mock('../../../static/js/state/index.js', () => ({
    state: {
        currentPageType: 'loras',
        selectedModels: new Set(),
        global: {
            settings: {
                download_path_templates: {
                    lora: '{base_model}/unstaged'
                }
            }
        }
    }
}));

vi.mock('../../../static/js/managers/ModalManager.js', () => ({
    modalManager: {
        showModal: vi.fn(),
        closeModal: vi.fn()
    }
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
    getModelApiClient: vi.fn()
}));

vi.mock('../../../static/js/utils/storageHelpers.js', () => ({
    getStorageItem: vi.fn(),
    setStorageItem: vi.fn()
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
    showToast: vi.fn()
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
    translate: vi.fn(key => key)
}));

describe('MoveManager', () => {
    let mockApiClient;

    beforeEach(() => {
        vi.clearAllMocks();
        
        // Setup DOM
        document.body.innerHTML = `
            <div id="moveModal">
                <h2 id="moveModalTitle"></h2>
                <label id="moveRootLabel"></label>
                <select id="moveModelRoot"></select>
                <input type="checkbox" id="moveUseDefaultPath" />
                <div id="moveManualPathSelection">
                    <input id="moveFolderPath" />
                    <div id="moveFolderTree"></div>
                </div>
                <div id="moveTargetPathDisplay"><span class="path-text"></span></div>
            </div>
        `;

        mockApiClient = {
            apiConfig: {
                config: {
                    displayName: 'LoRA',
                    supportsMove: true
                },
                endpoints: {
                    moveModel: '/api/move'
                }
            },
            modelType: 'loras',
            fetchModelRoots: vi.fn().mockResolvedValue({ roots: ['/models/loras'] }),
            fetchUnifiedFolderTree: vi.fn().mockResolvedValue({ success: true, tree: {} }),
            moveSingleModel: vi.fn().mockResolvedValue({ success: true })
        };
        getModelApiClient.mockReturnValue(mockApiClient);
    });

    it('should reset folder selection when showing move modal', async () => {
        // Manually set a selected path in folderTreeManager
        moveManager.folderTreeManager.selectedPath = 'previous/path';
        
        await moveManager.showMoveModal('some/file.safetensors');
        
        expect(moveManager.folderTreeManager.getSelectedPath()).toBe('');
    });

    it('should ignore manual folder selection when useDefaultPath is true', async () => {
        // Setup state
        moveManager.useDefaultPath = true;
        moveManager.currentFilePath = '/models/loras/flux/my-lora.safetensors';
        document.getElementById('moveModelRoot').innerHTML = '<option value="/models/loras">/models/loras</option>';
        document.getElementById('moveModelRoot').value = '/models/loras';
        
        // Manually set a selected path despite useDefaultPath being true
        moveManager.folderTreeManager.selectedPath = 'wrong/folder';
        
        await moveManager.moveModel();
        
        // Should call moveSingleModel with the root path, NOT including the 'wrong/folder'
        expect(mockApiClient.moveSingleModel).toHaveBeenCalledWith(
            '/models/loras/flux/my-lora.safetensors',
            '/models/loras',
            true
        );
    });

    it('should include manual folder selection when useDefaultPath is false', async () => {
        // Setup state
        moveManager.useDefaultPath = false;
        moveManager.currentFilePath = '/models/loras/flux/my-lora.safetensors';
        document.getElementById('moveModelRoot').innerHTML = '<option value="/models/loras">/models/loras</option>';
        document.getElementById('moveModelRoot').value = '/models/loras';
        
        // Set a selected path
        moveManager.folderTreeManager.selectedPath = 'my/organized/folder';
        
        await moveManager.moveModel();
        
        // Should call moveSingleModel with root + selected folder
        expect(mockApiClient.moveSingleModel).toHaveBeenCalledWith(
            '/models/loras/flux/my-lora.safetensors',
            '/models/loras/my/organized/folder',
            false
        );
    });

    it('should handle bulk move and ignore manual folder selection when useDefaultPath is true', async () => {
        // Setup state
        moveManager.useDefaultPath = true;
        moveManager.bulkFilePaths = [
            '/models/loras/flux/lora1.safetensors',
            '/models/loras/flux/lora2.safetensors'
        ];
        document.getElementById('moveModelRoot').innerHTML = '<option value="/models/loras">/models/loras</option>';
        document.getElementById('moveModelRoot').value = '/models/loras';
        
        // Manually set a selected path
        moveManager.folderTreeManager.selectedPath = 'wrong/folder';
        
        mockApiClient.moveBulkModels = vi.fn().mockResolvedValue({ success: true });
        
        await moveManager.moveModel();
        
        // Should call moveBulkModels with the root path, NOT including the 'wrong/folder'
        expect(mockApiClient.moveBulkModels).toHaveBeenCalledWith(
            moveManager.bulkFilePaths,
            '/models/loras',
            true
        );
    });
});
