import { PageControls } from './PageControls.js';
import { getModelApiClient, resetAndReload } from '../../api/modelApiFactory.js';
import { showToast } from '../../utils/uiHelpers.js';
import { downloadManager } from '../../managers/DownloadManager.js';

export class WildcardControls extends PageControls {
    constructor() {
        super('wildcards');
        this.registerAPI({
            loadMoreModels: async (resetPage = false, updateFolders = false) =>
                getModelApiClient().loadMoreWithVirtualScroll(resetPage, updateFolders),
            resetAndReload: async (updateFolders = false) => resetAndReload(updateFolders),
            fetchFromCivitai: async () => getModelApiClient().fetchCivitaiMetadata(),
            showDownloadModal: () => downloadManager.showDownloadModal(),
            toggleBulkMode: () => window.bulkManager?.toggleBulkMode(),
            clearCustomFilter: async () => showToast('toast.filters.noCustomFilterToClear', {}, 'info'),
        });
    }
}
