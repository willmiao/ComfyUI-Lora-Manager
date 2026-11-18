import { state } from '../state/index.js';
import { translate } from './i18nHelpers.js';

// Pages whose model type has a download filename template the scoped apply
// entry can rename with. Mirrors FILENAME_TEMPLATE_MODEL_TYPES in
// SettingsManager.js (workflows/other have no template editor).
const FILENAME_TEMPLATE_SETTING_KEYS = {
    loras: 'lora',
    checkpoints: 'checkpoint',
    embeddings: 'embedding',
};

/** Setting key shared by a page's model type, or null when it has no template. */
export function filenameTemplateSettingKey(pageType) {
    return FILENAME_TEMPLATE_SETTING_KEYS[pageType] || null;
}

/**
 * Whether applying the template for this model type would restore recorded
 * original filenames (empty template) instead of rendering a name.
 */
export function isFilenameTemplateRevert(settingKey) {
    const templates = state.global?.settings?.download_filename_templates || {};
    return !templates[settingKey];
}

/**
 * Build the confirmation modal payload for a scoped apply/revert.
 *
 * The scope is `'selected'` (bulk selection) or `'folder'` (folder context
 * menu); the counts come from the backend dry run so the user sees exactly how
 * many files a path-changing rename will touch.
 */
export function buildFilenameTemplateConfirmation(preview, scope, pageType) {
    const summary = preview?.summary || {};
    const params = {
        total: Number(summary.total) || 0,
        success: Number(summary.success) || 0,
        skipped: Number(summary.skipped) || 0,
        failures: Number(summary.failures) || 0,
    };
    const isFolder = scope === 'folder';
    const revert = isFilenameTemplateRevert(filenameTemplateSettingKey(pageType));
    const variant = isFolder ? 'Folder' : 'Selected';
    const kind = revert ? 'Revert' : 'Apply';
    const subject = isFolder ? 'files in this folder (and its subfolders)' : 'selected files';

    return {
        title: translate(
            `modals.filenameTemplateConfirm.title${kind}${variant}`,
            {},
            revert
                ? (isFolder ? 'Restore original filenames in this folder?' : 'Restore original filenames for the selection?')
                : (isFolder ? 'Rename files in this folder?' : 'Rename selected files?')
        ),
        message: translate(
            `modals.filenameTemplateConfirm.message${kind}${variant}`,
            params,
            revert
                ? `${params.success} of ${params.total} ${subject} will get their recorded original filename back; ${params.skipped} have no recorded original or already match. This changes the relative path ComfyUI sees.`
                : `${params.success} of ${params.total} ${subject} will be renamed according to the filename template. ${params.skipped} already match; ${params.failures} cannot be renamed. This changes the relative path ComfyUI sees; each model keeps its original filename in metadata.`
        ),
        confirmText: translate(
            revert
                ? 'modals.filenameTemplateConfirm.restoreCountButton'
                : 'modals.filenameTemplateConfirm.renameCountButton',
            { count: params.success },
            revert
                ? `Restore ${params.success} Filenames`
                : `Rename ${params.success} Files`
        ),
    };
}
