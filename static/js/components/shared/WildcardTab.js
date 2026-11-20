import { getModelApiClient } from '../../api/modelApiFactory.js';
import { showToast } from '../../utils/uiHelpers.js';
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

/**
 * Render the wildcard-specific tab shown inside the shared model modal.
 * The tab owns activation, parsed keys and the source preview so the wildcard
 * page has one modal instead of a separate activation dialog.
 */
export function renderWildcardTab(model) {
  const entries = Array.isArray(model.entries) ? model.entries : [];
  const active = model.active === true;
  const single = entries.length === 1;
  const namespace = model.activation_namespace || '';
  const aliases = model.activation_aliases || {};
  const sourceKey = single ? entries[0].key : '';
  const alias = single ? aliases[sourceKey] || sourceKey : '';
  const statusLabel = translate(
    active ? 'wildcards.library.active' : 'wildcards.library.inactive',
    {},
    active ? 'Active' : 'Inactive',
  );
  const confirmLabel = translate('wildcards.activation.confirm', {}, 'Activate resource');
  const deactivateLabel = translate('wildcards.actions.deactivate', {}, 'Deactivate');
  const keysLabel = translate('wildcards.details.keys', {}, 'Wildcard keys');
  const filterLabel = translate('wildcards.details.filterKeys', {}, 'Filter keys');
  const previewLabel = translate('wildcards.details.preview', {}, 'Content preview');
  const selectKeyLabel = translate(
    'wildcards.details.selectKey',
    {},
    'Select a key to preview its values.',
  );
  const namespaceLabel = translate(
    'wildcards.activation.namespace',
    {},
    'Namespace prefix (optional)',
  );
  const namespacePlaceholder = translate(
    'wildcards.activation.namespacePlaceholder',
    {},
    'e.g. characters/fantasy',
  );
  const namespaceHelp = translate(
    'wildcards.activation.namespaceHelp',
    {},
    'The prefix is applied to every key in this resource. Leave it empty to preserve the downloaded paths.',
  );
  const aliasLabel = translate(
    'wildcards.activation.alias',
    {},
    'Active wildcard key',
  );
  const keyCount = model.entry_count != null ? Number(model.entry_count) : entries.length;
  const disabled = active ? ' disabled' : '';

  const errorMarkup = Array.isArray(model.errors) && model.errors.length
    ? `<div class="wildcard-activation-errors">${escapeHtml(model.errors.join(' · '))}</div>`
    : '';

  const unreferenceable = entries.filter((entry) => entry.reference_problem);
  const warningMarkup = unreferenceable.length
    ? `<div class="wildcard-tab__warning">${escapeHtml(
        translate(
          'wildcards.messages.unreferenceableKeys',
          { count: unreferenceable.length },
          `Some keys (${unreferenceable.length}) cannot be referenced with __key__ syntax.`,
        ),
      )}</div>`
    : '';

  return `
    <div class="wildcard-tab" data-file-path="${escapeAttribute(model.file_path || '')}">
      <div class="wildcard-tab__status">
        <span class="wildcard-tab__badge ${active ? 'is-active' : 'is-inactive'}">${escapeHtml(statusLabel)}</span>
        <span class="wildcard-tab__namespace">Namespace: ${escapeHtml(namespace || '(none)')}</span>
        ${active
          ? '<span class="wildcard-tab__hint">Deactivate to edit namespace or alias.</span>'
          : ''}
      </div>
      ${errorMarkup}
      ${warningMarkup}
      <div class="wildcard-tab__fields">
        <label class="wildcard-tab__field">
          <span>${escapeHtml(namespaceLabel)}</span>
          <input type="text" data-wildcard-field="namespace"
            value="${escapeAttribute(namespace)}"
            placeholder="${escapeAttribute(namespacePlaceholder)}"${disabled}>
        </label>
        <label class="wildcard-tab__field" data-wildcard-alias-group ${single ? '' : 'hidden'}>
          <span>${escapeHtml(aliasLabel)}</span>
          <input type="text" data-wildcard-field="alias"
            value="${escapeAttribute(alias)}"${disabled}>
        </label>
      </div>
      <p class="wildcard-tab__help">${escapeHtml(namespaceHelp)}</p>
      <div class="wildcard-tab__actions">
        <button type="button" class="btn btn-primary wildcard-tab__toggle ${active ? 'is-deactivate' : 'is-activate'}" data-wildcard-action="toggle">
          ${active ? escapeHtml(deactivateLabel) : escapeHtml(confirmLabel)}
        </button>
      </div>
      <div class="wildcard-tab__error" data-wildcard-error hidden></div>
      <div class="wildcard-key-layout">
        <div class="wildcard-tab__keys">
          <div class="wildcard-tab__keys-head">
            <span>${escapeHtml(keysLabel)} (${keyCount})</span>
            <input type="search" data-wildcard-filter
              placeholder="${escapeAttribute(filterLabel)}"
              aria-label="${escapeAttribute(filterLabel)}">
          </div>
          <div class="wildcard-key-list" data-wildcard-key-list></div>
        </div>
        <div class="wildcard-tab__preview">
          <div class="wildcard-tab__preview-head">${escapeHtml(previewLabel)}</div>
          <pre class="wildcard-content-preview" data-wildcard-preview>${escapeHtml(selectKeyLabel)}</pre>
        </div>
      </div>
    </div>`;
}

/**
 * Bind activation, key filtering and value previews for the wildcard tab.
 * `onRefresh` receives the updated resource so the caller can re-render the
 * standard model modal without closing it.
 */
export function setupWildcardTab({ model, modalId = 'modelModal', onRefresh } = {}) {
  const modal = document.getElementById(modalId);
  const tab = modal?.querySelector('.wildcard-tab');
  if (!tab || !model?.file_path) return;

  const api = getModelApiClient('wildcards');
  const filePath = model.file_path;
  const entries = Array.isArray(model.entries) ? model.entries : [];
  const active = model.active === true;
  const single = entries.length === 1;
  const sourceKey = single ? entries[0].key : '';
  const namespaceInput = tab.querySelector('[data-wildcard-field="namespace"]');
  const aliasInput = tab.querySelector('[data-wildcard-field="alias"]');
  const filterInput = tab.querySelector('[data-wildcard-filter]');
  const keyList = tab.querySelector('[data-wildcard-key-list]');
  const preview = tab.querySelector('[data-wildcard-preview]');
  const toggleButton = tab.querySelector('[data-wildcard-action="toggle"]');
  const errorBox = tab.querySelector('[data-wildcard-error]');

  const setError = (message = '') => {
    if (!errorBox) return;
    errorBox.hidden = !message;
    errorBox.textContent = message;
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
    visible.slice(0, MAX_RENDERED_KEYS).forEach((entry) => {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'wildcard-key-row';
      const problem = entry.reference_problem;
      row.textContent = `${problem ? '⚠ ' : ''}${displayKey(entry, active)} · ${entry.values_count ?? 0}`;
      const titleParts = [];
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
      if (titleParts.length) row.title = titleParts.join('\n');
      row.addEventListener('click', () => loadEntryValues(entry));
      keyList.appendChild(row);
    });
    if (!visible.length) {
      const empty = document.createElement('div');
      empty.className = 'wildcard-tab__empty';
      empty.textContent = normalized
        ? 'No wildcard keys match this filter.'
        : 'No parsed wildcard keys in this resource.';
      keyList.appendChild(empty);
    } else if (visible.length > MAX_RENDERED_KEYS) {
      const note = document.createElement('div');
      note.className = 'wildcard-tab__empty';
      note.textContent = `Showing ${MAX_RENDERED_KEYS} of ${visible.length} keys. Browse all keys in the resource file.`;
      keyList.appendChild(note);
    }
  };

  const loadEntryValues = async (entry) => {
    if (!preview) return;
    preview.textContent = 'Loading values...';
    try {
      const data = await api.fetchEntryValues(filePath, entry.key);
      preview.textContent = (data.values || []).join('\n') || 'This key has no values.';
    } catch (error) {
      preview.textContent = error.message || 'Failed to load values';
    }
  };

  const loadSourcePreview = async () => {
    if (!preview) return;
    if (Array.isArray(model.files) && model.files.length) {
      try {
        const data = await api.fetchSource(filePath, model.files[0]);
        preview.textContent = data.content || '';
        return;
      } catch (error) {
        preview.textContent = error.message || 'Failed to load source';
        return;
      }
    }
    if (entries.length) await loadEntryValues(entries[0]);
  };

  const refresh = async () => {
    let updated = null;
    try {
      const response = await fetch('/api/lm/wildcards/active');
      const data = await response.json().catch(() => ({}));
      updated = (data.resources || []).find((item) => item.file_path === filePath) || null;
    } catch (error) {
      console.warn('Failed to refresh wildcard resource:', error);
    }
    if (typeof onRefresh === 'function') {
      await onRefresh(updated || {
        ...model,
        active: !active,
      });
    }
    try {
      await api.loadMoreWithVirtualScroll(true, false);
    } catch (error) {
      console.warn('Failed to refresh the wildcard library:', error);
    }
  };

  const toggleActivation = async () => {
    if (!toggleButton) return;
    toggleButton.disabled = true;
    toggleButton.setAttribute('aria-busy', 'true');
    setError('');
    try {
      if (active) {
        await api.deactivate(filePath);
        showToast('wildcards.messages.deactivated', {}, 'success');
      } else {
        const namespace = namespaceInput?.value.trim() || '';
        const aliases = {};
        if (single && aliasInput) {
          aliases[sourceKey] = aliasInput.value.trim();
        }
        await api.activate(filePath, namespace, aliases);
        showToast('wildcards.messages.activated', {}, 'success');
      }
      await refresh();
    } catch (error) {
      const conflicts = error.payload?.conflicts || [];
      const message = conflicts.length
        ? conflicts
          .map((item) => `${item.key}: ${(item.owners || []).map((owner) => owner.resource_id).join(', ')}`)
          .join('\n')
        : error.message || 'Failed to update wildcard activation';
      setError(message);
    } finally {
      toggleButton.disabled = false;
      toggleButton.removeAttribute('aria-busy');
    }
  };

  filterInput?.addEventListener('input', () => renderKeys(filterInput.value));
  toggleButton?.addEventListener('click', toggleActivation);
  renderKeys('');
  loadSourcePreview();
}
