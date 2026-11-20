import { getModelApiClient } from '../../api/modelApiFactory.js';
import { copyToClipboard, showToast } from '../../utils/uiHelpers.js';
import { translate } from '../../utils/i18nHelpers.js';

const MAX_RENDERED_KEYS = 300;

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function escapeAttribute(value) {
  return escapeHtml(value).replace(/`/g, '&#096;');
}

function displayKey(entry, active) {
  return active
    ? entry.effective_key || entry.key || ''
    : entry.key || entry.effective_key || '';
}

function normalizeKeyPreview(value) {
  return String(value || '').replace(/\\/g, '/').replace(/^\/+|\/+$/g, '').toLowerCase();
}

function activationErrorMessage(error) {
  const conflicts = error?.payload?.conflicts || [];
  if (!conflicts.length) return error?.message || translate(
    'wildcards.activation.failed',
    {},
    'Failed to update activation settings.',
  );
  return conflicts
    .map((item) => `${item.key}: ${(item.owners || []).map((owner) => owner.resource_id).join(', ')}`)
    .join('\n');
}

export function renderWildcardSection(model, { expanded = false } = {}) {
  const entries = Array.isArray(model.entries) ? model.entries : [];
  const single = entries.length === 1;
  const namespace = model.activation_namespace || '';
  const aliases = model.activation_aliases || {};
  const sourceKey = single ? entries[0].key : '';
  const alias = single ? aliases[sourceKey] || sourceKey : '';
  const keyCount = model.entry_count != null ? Number(model.entry_count) : entries.length;
  const active = model.active === true;

  const errorMarkup = Array.isArray(model.errors) && model.errors.length
    ? `<div class="wildcard-section__error" role="alert">${escapeHtml(model.errors.join(' · '))}</div>`
    : '';
  const unreferenceable = entries.filter((entry) => entry.reference_problem);
  const warningMarkup = unreferenceable.length
    ? `<div class="wildcard-section__warning">${escapeHtml(
        translate(
          'wildcards.messages.unreferenceableKeys',
          { count: unreferenceable.length },
          `Some keys (${unreferenceable.length}) cannot be referenced with __key__ syntax.`,
        ),
      )}</div>`
    : '';

  return `
    <div class="info-item full-width wildcard-section ${expanded ? 'is-expanded' : 'is-collapsed'}" data-file-path="${escapeAttribute(model.file_path || '')}">
      ${errorMarkup}
      ${warningMarkup}
      <div class="wildcard-section__header">
        <div class="wildcard-section__title">
          <button type="button" class="wildcard-section__toggle" data-wildcard-section-toggle
            aria-expanded="${expanded ? 'true' : 'false'}" aria-controls="wildcard-key-browser">
            <span class="wildcard-section__heading">
              <span class="wildcard-section__label">${escapeHtml(translate('wildcards.details.keys', {}, 'Wildcard keys'))}</span>
              <span class="wildcard-section__count" aria-label="${escapeAttribute(
                translate('wildcards.card.keys', { count: keyCount }, `${keyCount} keys`),
              )}">${keyCount}</span>
            </span>
            <span class="wildcard-section__toggle-action" data-wildcard-section-expand ${expanded ? 'hidden' : ''}>
              <span>${escapeHtml(translate('wildcards.details.expand', {}, 'Expand'))}</span>
              <i class="fas fa-chevron-down" aria-hidden="true"></i>
            </span>
          </button>
        </div>
        <input type="search" class="wildcard-section__filter" data-wildcard-filter
          placeholder="${escapeAttribute(translate('wildcards.details.filterKeys', {}, 'Filter keys'))}"
          aria-label="${escapeAttribute(translate('wildcards.details.filterKeys', {}, 'Filter keys'))}"
          ${expanded ? '' : 'hidden'}>
        <button type="button" class="wildcard-section__collapse" data-wildcard-section-toggle
          data-wildcard-section-collapse aria-expanded="${expanded ? 'true' : 'false'}"
          aria-controls="wildcard-key-browser" ${expanded ? '' : 'hidden'}>
          <span>${escapeHtml(translate('wildcards.details.collapse', {}, 'Collapse'))}</span>
          <i class="fas fa-chevron-up" aria-hidden="true"></i>
        </button>
      </div>
      <div id="wildcard-key-browser" class="wildcard-key-layout" data-wildcard-browser ${expanded ? '' : 'hidden'}>
        <div class="wildcard-key-list" data-wildcard-key-list role="listbox"
          aria-label="${escapeAttribute(translate('wildcards.details.keys', {}, 'Wildcard keys'))}"></div>
        <div class="wildcard-value-panel">
          <div class="wildcard-value-panel__header">
            <span data-wildcard-values-label>${escapeHtml(translate('wildcards.details.values', {}, 'Values'))}</span>
            <button type="button" class="wildcard-copy-key" data-wildcard-copy disabled
              title="${escapeAttribute(translate('wildcards.details.copyKey', {}, 'Copy wildcard reference'))}"
              aria-label="${escapeAttribute(translate('wildcards.details.copyKey', {}, 'Copy wildcard reference'))}">
              <i class="fas fa-copy" aria-hidden="true"></i>
            </button>
          </div>
          <code class="wildcard-reference" data-wildcard-reference></code>
          <pre class="wildcard-content-preview" data-wildcard-preview>${escapeHtml(
            translate('wildcards.details.selectKey', {}, 'Select a key to preview its values.'),
          )}</pre>
        </div>
      </div>
      <dialog class="wildcard-settings-dialog" data-wildcard-settings
        aria-labelledby="wildcard-settings-title">
        <div class="wildcard-settings__header">
          <h2 id="wildcard-settings-title">${escapeHtml(
            translate('wildcards.activation.settingsTitle', {}, 'Activation settings'),
          )}</h2>
          <button type="button" class="wildcard-settings__close" data-wildcard-settings-close
            aria-label="${escapeAttribute(translate('common.actions.close', {}, 'Close'))}">
            <i class="fas fa-times" aria-hidden="true"></i>
          </button>
        </div>
        <p class="wildcard-settings__description">${escapeHtml(
          translate(
            'wildcards.activation.settingsDescription',
            {},
            'Configure the keys used by ComfyUI. Source files are not modified.',
          ),
        )}</p>
        <label class="wildcard-settings__field">
          <span>${escapeHtml(translate('wildcards.activation.keyPrefix', {}, 'Key prefix (optional)'))}</span>
          <input type="text" data-wildcard-field="namespace"
            value="${escapeAttribute(namespace)}"
            placeholder="${escapeAttribute(
              translate('wildcards.activation.namespacePlaceholder', {}, 'e.g. characters/fantasy'),
            )}">
        </label>
        <p class="wildcard-settings__help">${escapeHtml(
          translate(
            'wildcards.activation.keyPrefixHelp',
            {},
            'Added to every wildcard key when active. Leave empty to keep the original keys.',
          ),
        )}</p>
        <label class="wildcard-settings__field" data-wildcard-alias-group ${single ? '' : 'hidden'}>
          <span>${escapeHtml(translate('wildcards.activation.keyLabel', {}, 'Wildcard key'))}</span>
          <input type="text" data-wildcard-field="alias" value="${escapeAttribute(alias)}">
        </label>
        <p class="wildcard-settings__help" data-wildcard-alias-help ${single ? '' : 'hidden'}>${escapeHtml(
          translate(
            'wildcards.activation.aliasHelp',
            {},
            'This changes the key used by ComfyUI without modifying the downloaded file.',
          ),
        )}</p>
        <div class="wildcard-settings__example">
          <span>${escapeHtml(translate('wildcards.activation.referencePreview', {}, 'Reference preview'))}</span>
          <code data-wildcard-settings-example></code>
        </div>
        <div class="wildcard-settings__error" data-wildcard-settings-error role="alert" hidden></div>
        <div class="wildcard-settings__actions">
          <button type="button" class="cancel-btn" data-wildcard-settings-close>
            ${escapeHtml(translate('common.actions.cancel', {}, 'Cancel'))}
          </button>
          <button type="button" class="confirm-btn" data-wildcard-settings-save>
            ${escapeHtml(translate(
              active ? 'wildcards.activation.save' : 'wildcards.activation.saveActivate',
              {},
              active ? 'Save settings' : 'Save & Activate',
            ))}
          </button>
        </div>
      </dialog>
    </div>`;
}

export function setupWildcardSection({ model, modalId = 'modelModal', onRefresh, viewState = {} } = {}) {
  const modal = document.getElementById(modalId);
  const section = modal?.querySelector('.wildcard-section');
  if (!section || !model?.file_path) return;

  const api = getModelApiClient('wildcards');
  const filePath = model.file_path;
  const entries = Array.isArray(model.entries) ? model.entries : [];
  const active = model.active === true;
  const single = entries.length === 1;
  const sourceKey = single ? entries[0].key : '';
  const sectionToggles = section.querySelectorAll('[data-wildcard-section-toggle]');
  const expandAction = section.querySelector('[data-wildcard-section-expand]');
  const collapseButton = section.querySelector('[data-wildcard-section-collapse]');
  const browser = section.querySelector('[data-wildcard-browser]');
  const filterInput = section.querySelector('[data-wildcard-filter]');
  const keyList = section.querySelector('[data-wildcard-key-list]');
  const preview = section.querySelector('[data-wildcard-preview]');
  const valuesLabel = section.querySelector('[data-wildcard-values-label]');
  const reference = section.querySelector('[data-wildcard-reference]');
  const copyButton = section.querySelector('[data-wildcard-copy]');
  const dialog = section.querySelector('[data-wildcard-settings]');
  const namespaceInput = section.querySelector('[data-wildcard-field="namespace"]');
  const aliasInput = section.querySelector('[data-wildcard-field="alias"]');
  const settingsExample = section.querySelector('[data-wildcard-settings-example]');
  const settingsError = section.querySelector('[data-wildcard-settings-error]');
  const saveButton = section.querySelector('[data-wildcard-settings-save]');
  let expanded = viewState.expanded ?? section.classList.contains('is-expanded');
  let renderedEntries = [];
  let selectedEntry = entries.find((entry) => entry.key === viewState.selectedKey) || null;
  let previewRequest = 0;
  let hasRenderedKeys = false;
  if (filterInput) filterInput.value = viewState.query || '';

  const setSettingsError = (message = '') => {
    if (!settingsError) return;
    settingsError.hidden = !message;
    settingsError.textContent = message;
  };

  const updateSettingsExample = () => {
    if (!settingsExample) return;
    if (!entries.length) {
      settingsExample.textContent = '—';
      return;
    }
    const namespace = normalizeKeyPreview(namespaceInput?.value.trim());
    const originalKey = single ? sourceKey : entries[0].key;
    const alias = single ? normalizeKeyPreview(aliasInput?.value.trim()) : originalKey;
    const key = single && !alias
      ? ''
      : [namespace, alias || originalKey].filter(Boolean).join('/');
    settingsExample.textContent = key ? `__${key}__` : '—';
  };

  const closeSettings = () => {
    if (!dialog) return;
    if (typeof dialog.close === 'function') dialog.close();
    else dialog.removeAttribute('open');
  };

  const openSettings = (error = null) => {
    if (!dialog) return;
    setSettingsError(error ? activationErrorMessage(error) : '');
    updateSettingsExample();
    if (!dialog.open) {
      if (typeof dialog.showModal === 'function') dialog.showModal();
      else dialog.setAttribute('open', '');
    }
    namespaceInput?.focus();
  };
  section._openWildcardSettings = openSettings;

  const updateViewState = () => {
    section._wildcardViewState = {
      expanded,
      query: filterInput?.value || '',
      selectedKey: selectedEntry?.key || null,
    };
  };

  const selectEntry = async (entry, { focus = false } = {}) => {
    selectedEntry = entry || null;
    updateViewState();
    const selectedKey = selectedEntry?.key || '';
    keyList?.querySelectorAll('.wildcard-key-row').forEach((row) => {
      const selected = row.dataset.key === selectedKey;
      row.classList.toggle('is-selected', selected);
      row.setAttribute('aria-selected', String(selected));
      row.tabIndex = selected ? 0 : -1;
      if (selected && focus) row.focus();
    });

    const key = selectedEntry ? displayKey(selectedEntry, active) : '';
    if (reference) reference.textContent = key ? `__${key}__` : '';
    if (copyButton) copyButton.disabled = !selectedEntry || Boolean(selectedEntry.reference_problem);
    if (valuesLabel) {
      const label = translate('wildcards.details.values', {}, 'Values');
      valuesLabel.textContent = selectedEntry
        ? `${label} · ${selectedEntry.values_count ?? 0}`
        : label;
    }
    if (!preview) return;

    const request = ++previewRequest;
    if (!selectedEntry) {
      preview.textContent = translate(
        'wildcards.details.selectKey',
        {},
        'Select a key to preview its values.',
      );
      return;
    }
    preview.textContent = translate('wildcards.details.loading', {}, 'Loading values...');
    try {
      const data = await api.fetchEntryValues(filePath, selectedEntry.key);
      if (request !== previewRequest) return;
      preview.textContent = (data.values || []).join('\n') || translate(
        'wildcards.details.noValues',
        {},
        'This key has no values.',
      );
    } catch (error) {
      if (request !== previewRequest) return;
      preview.textContent = error.message || translate(
        'wildcards.details.loadFailed',
        {},
        'Failed to load values.',
      );
    }
  };

  const renderKeys = (query = '') => {
    if (!keyList) return;
    keyList.replaceChildren();
    const normalized = query.trim().toLowerCase();
    const visible = entries.filter((entry) => {
      if (!normalized) return true;
      return `${displayKey(entry, active)} ${entry.source_path || ''}`
        .toLowerCase()
        .includes(normalized);
    });
    renderedEntries = visible.slice(0, MAX_RENDERED_KEYS);
    const nextSelection = renderedEntries.find((entry) => entry.key === selectedEntry?.key)
      || renderedEntries[0]
      || null;

    renderedEntries.forEach((entry) => {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'wildcard-key-row';
      row.dataset.key = entry.key;
      row.setAttribute('role', 'option');
      row.setAttribute('aria-selected', 'false');
      row.tabIndex = -1;
      const problem = entry.reference_problem;
      const key = displayKey(entry, active);
      row.innerHTML = `
        ${problem ? '<i class="fas fa-exclamation-triangle wildcard-key-row__warning" aria-hidden="true"></i>' : ''}
        <span class="wildcard-key-row__name">${escapeHtml(key)}</span>
        <span class="wildcard-key-row__count" title="${escapeAttribute(
          translate(
            'wildcards.details.valueCount',
            { count: entry.values_count ?? 0 },
            `${entry.values_count ?? 0} values`,
          ),
        )}">${entry.values_count ?? 0}</span>`;
      const titleParts = [key];
      if (entry.source_path) titleParts.push(entry.source_path);
      if (problem) {
        row.classList.add('is-unreferenceable');
        titleParts.push(
          translate(
            'wildcards.details.unreferenceableKey',
            { reason: problem },
            `Cannot be referenced: ${problem}`,
          ),
        );
      }
      row.title = titleParts.join('\n');
      row.addEventListener('click', () => selectEntry(entry));
      keyList.appendChild(row);
    });

    if (!visible.length) {
      const empty = document.createElement('div');
      empty.className = 'wildcard-section__empty';
      empty.textContent = normalized
        ? translate('wildcards.details.noMatches', {}, 'No wildcard keys match this filter.')
        : translate('wildcards.details.empty', {}, 'No parsed wildcard keys in this resource.');
      keyList.appendChild(empty);
    } else if (visible.length > MAX_RENDERED_KEYS) {
      const note = document.createElement('div');
      note.className = 'wildcard-section__limit';
      note.textContent = translate(
        'wildcards.details.renderLimit',
        { shown: MAX_RENDERED_KEYS, total: visible.length },
        `Showing ${MAX_RENDERED_KEYS} of ${visible.length} keys. Refine the filter to narrow the results.`,
      );
      keyList.appendChild(note);
    }
    selectEntry(nextSelection);
  };

  const setExpanded = (nextExpanded) => {
    expanded = nextExpanded;
    section.classList.toggle('is-expanded', expanded);
    section.classList.toggle('is-collapsed', !expanded);
    sectionToggles.forEach((toggle) => {
      toggle.setAttribute('aria-expanded', String(expanded));
    });
    if (expandAction) expandAction.hidden = expanded;
    if (collapseButton) collapseButton.hidden = !expanded;
    if (filterInput) filterInput.hidden = !expanded;
    if (browser) browser.hidden = !expanded;
    updateViewState();
    if (expanded && !hasRenderedKeys) {
      hasRenderedKeys = true;
      renderKeys(filterInput?.value || '');
    }
  };

  sectionToggles.forEach((toggle) => {
    toggle.addEventListener('click', () => setExpanded(!expanded));
  });
  keyList?.addEventListener('keydown', (event) => {
    if (!renderedEntries.length) return;
    const currentIndex = Math.max(0, renderedEntries.findIndex((entry) => entry.key === selectedEntry?.key));
    let nextIndex = currentIndex;
    if (event.key === 'ArrowDown') nextIndex = Math.min(renderedEntries.length - 1, currentIndex + 1);
    else if (event.key === 'ArrowUp') nextIndex = Math.max(0, currentIndex - 1);
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = renderedEntries.length - 1;
    else return;
    event.preventDefault();
    selectEntry(renderedEntries[nextIndex], { focus: true });
  });

  filterInput?.addEventListener('input', () => renderKeys(filterInput.value));
  filterInput?.addEventListener('keydown', (event) => {
    if (event.key !== 'ArrowDown' || !selectedEntry) return;
    event.preventDefault();
    keyList?.querySelector('.wildcard-key-row.is-selected')?.focus();
  });
  copyButton?.addEventListener('click', async () => {
    if (!selectedEntry) return;
    await copyToClipboard(
      `__${displayKey(selectedEntry, active)}__`,
      translate('wildcards.details.copied', {}, 'Wildcard reference copied'),
    );
  });

  namespaceInput?.addEventListener('input', updateSettingsExample);
  aliasInput?.addEventListener('input', updateSettingsExample);
  dialog?.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      closeSettings();
    } else if (event.key === 'Enter' && !event.isComposing && event.target.matches('input')) {
      event.preventDefault();
      event.stopPropagation();
      saveButton?.click();
    }
  });
  section.querySelectorAll('[data-wildcard-settings-close]').forEach((button) => {
    button.addEventListener('click', closeSettings);
  });
  saveButton?.addEventListener('click', async () => {
    if (saveButton.disabled) return;
    saveButton.disabled = true;
    saveButton.setAttribute('aria-busy', 'true');
    setSettingsError('');
    try {
      const aliases = {};
      if (single && aliasInput) aliases[sourceKey] = aliasInput.value.trim();
      const response = await api.activate(filePath, namespaceInput?.value.trim() || '', aliases);
      const updated = {
        ...model,
        ...(response?.resource || {}),
        active: response?.resource?.active ?? true,
      };
      closeSettings();
      if (typeof onRefresh === 'function') await onRefresh(updated);
      showToast(
        active ? 'wildcards.messages.settingsSaved' : 'wildcards.messages.activated',
        {},
        'success',
        active ? 'Activation settings saved.' : 'Resource activated.',
      );
    } catch (error) {
      setSettingsError(activationErrorMessage(error));
    } finally {
      saveButton.disabled = false;
      saveButton.removeAttribute('aria-busy');
    }
  });

  setExpanded(expanded);
  updateSettingsExample();
}

export function openWildcardActivationSettings(modalId = 'modelModal', error = null) {
  const section = document.querySelector(`#${modalId} .wildcard-section`);
  section?._openWildcardSettings?.(error);
}
