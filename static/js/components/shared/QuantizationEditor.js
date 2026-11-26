import { getModelApiClient } from '../../api/modelApiFactory.js';
import { translate } from '../../utils/i18nHelpers.js';
import { showToast } from '../../utils/uiHelpers.js';
import { positionFixedMenu } from '../../utils/menuPosition.js';
import { escapeAttribute } from './utils.js';

const QUANTIZATION_PRESETS = ['FP8', 'NVFP4', 'INT8', 'Q4_K_M', 'Q5_K_M', 'Q6_K', 'Q8_0'];

let activeEditor = null;

function closeActiveEditor(restoreFocus = true) {
    if (!activeEditor) return;

    const editor = activeEditor;
    activeEditor = null;
    document.removeEventListener('mousedown', editor.outsideHandler, true);
    window.removeEventListener('resize', editor.positionHandler);
    window.removeEventListener('scroll', editor.positionHandler, true);
    editor.popover.remove();

    if (editor.trigger?.classList.contains('quant-badge')) {
        editor.trigger.setAttribute('aria-expanded', 'false');
        if (restoreFocus && editor.trigger.isConnected) {
            editor.trigger.focus({ preventScroll: true });
        }
    }
}

export function closeQuantizationEditor() {
    closeActiveEditor(false);
}

export function openQuantizationEditor(card, anchor = null) {
    const filePath = card?.dataset?.filepath;
    if (!filePath) return;

    closeActiveEditor(false);

    const trigger = anchor || card.querySelector('.quant-badge') || card;
    const originalValue = card.dataset.quantization || '';
    const originalSource = card.dataset.quantization_source || '';
    const precisionLabel = translate('modals.model.metadata.precision', {}, 'Precision');
    const editLabel = translate('modals.model.actions.editPrecision', {}, 'Edit precision');
    const autoLabel = translate('modals.model.metadata.precisionAuto', {}, 'Auto');
    const resetLabel = translate('modelCard.footer.quantResetAuto', {}, 'Reset to Auto');
    const saveLabel = translate('common.actions.save', {}, 'Save');
    const manualHint = translate(
        'modals.model.metadata.precisionManualHint',
        {},
        'Manually set — relinks and rescans will not change it'
    );
    const presets = QUANTIZATION_PRESETS
        .map((preset) => `<option value="${preset}"></option>`)
        .join('');

    const popover = document.createElement('div');
    popover.id = 'quantizationEditorPopover';
    popover.className = 'quantization-popover';
    popover.setAttribute('role', 'dialog');
    popover.setAttribute('aria-label', editLabel);
    popover.innerHTML = `
        <label class="quantization-popover-label" for="quantizationEditorInput">${precisionLabel}</label>
        <input id="quantizationEditorInput" class="quantization-input" type="text"
            list="quantizationEditorPresets" value="${escapeAttribute(originalValue)}"
            placeholder="${escapeAttribute(autoLabel)}" maxlength="32" autocomplete="off" spellcheck="false">
        <datalist id="quantizationEditorPresets">${presets}</datalist>
        ${originalSource === 'manual' ? `<div class="quantization-popover-hint">${manualHint}</div>` : ''}
        <div class="quantization-popover-actions">
            <button type="button" class="secondary-btn quantization-auto-btn">${resetLabel}</button>
            <button type="button" class="primary-btn quantization-save-btn">${saveLabel}</button>
        </div>
    `;
    document.body.appendChild(popover);

    const input = popover.querySelector('.quantization-input');
    const saveButton = popover.querySelector('.quantization-save-btn');
    const autoButton = popover.querySelector('.quantization-auto-btn');
    let saving = false;

    const close = (restoreFocus = true) => {
        if (activeEditor?.popover === popover) {
            closeActiveEditor(restoreFocus);
        }
    };

    const position = () => {
        if (!trigger.isConnected) {
            close(false);
            return;
        }
        const rect = trigger.getBoundingClientRect();
        positionFixedMenu(popover, rect.left, rect.bottom + 6);
    };

    const editor = {
        popover,
        trigger,
        outsideHandler: (event) => {
            if (!popover.contains(event.target) && event.target !== trigger) {
                close(false);
            }
        },
        positionHandler: position,
    };
    activeEditor = editor;

    const setSaving = (isSaving) => {
        saving = isSaving;
        input.disabled = isSaving;
        saveButton.disabled = isSaving;
        autoButton.disabled = isSaving;
        popover.classList.toggle('is-saving', isSaving);
    };

    const save = async (rawValue) => {
        if (saving) return;
        setSaving(true);
        try {
            await getModelApiClient().saveModelMetadata(filePath, {
                quantization: rawValue || null,
            });
            close(false);
            showToast('toast.models.precisionUpdated', {}, 'success');
        } catch (error) {
            console.error('Error updating precision:', error);
            setSaving(false);
            input.focus();
            showToast('toast.models.precisionUpdateFailed', {}, 'error');
        }
    };

    input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            save(input.value.trim());
        } else if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            close();
        }
    });
    popover.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && event.target !== input) {
            event.preventDefault();
            event.stopPropagation();
            close();
        }
    });
    saveButton.addEventListener('click', () => save(input.value.trim()));
    autoButton.addEventListener('click', () => save(null));
    document.addEventListener('mousedown', editor.outsideHandler, true);
    window.addEventListener('resize', editor.positionHandler);
    window.addEventListener('scroll', editor.positionHandler, true);

    if (trigger.classList.contains('quant-badge')) {
        trigger.setAttribute('aria-expanded', 'true');
    }
    position();
    input.focus();
    input.select();
}
