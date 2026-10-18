import { translate } from '../utils/i18nHelpers.js';

/**
 * Reusable directory picker modal backed by POST /api/lm/browse-directory.
 * Self-managed (NOT registered with ModalManager): it stacks above the
 * settings modal, so ModalManager's "close current modal on open" behavior
 * would kill the modal underneath.
 */
class DirectoryPickerModal {
  constructor() {
    this.isOpen = false;
    this.currentPath = '';
    this.parentPath = null;
    this.onSelect = null;
    this.elements = {};
    this._bindings = [];
  }

  open({ initialPath = '', onSelect } = {}) {
    this._cacheElements();
    if (!this.elements.modal) {
      console.warn('DirectoryPickerModal: #directoryPickerModal not found in DOM');
      return;
    }

    this._unbindEvents();
    this.onSelect = typeof onSelect === 'function' ? onSelect : null;
    this.currentPath = '';
    this.parentPath = null;
    this._clearError();
    this.elements.folderList.innerHTML = '';
    this.elements.currentPathEl.textContent = '';
    this.elements.upBtn.disabled = true;
    this.elements.pathInput.value = initialPath || '';

    this._bindEvents();
    document.body.classList.add('modal-open');
    this.elements.modal.style.display = 'block';
    this.isOpen = true;

    // An empty path lets the server pick its default (user home).
    this.loadDirectory(initialPath || '');
  }

  close() {
    if (!this.isOpen) return;
    this.isOpen = false;
    this._unbindEvents();
    if (this.elements.modal) {
      this.elements.modal.style.display = 'none';
    }
    this.onSelect = null;
    // Keep body.modal-open: the settings modal underneath may still be open.
  }

  async loadDirectory(path) {
    try {
      const response = await fetch('/api/lm/browse-directory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path })
      });
      const data = await response.json();

      if (data.success) {
        this._clearError();
        this._renderDirectory(data);
      } else {
        this._showError(data.error || translate('settings.directoryPicker.loadError', {}, 'Failed to load directory'));
      }
    } catch (error) {
      console.error('Error loading directory:', error);
      this._showError(translate('settings.directoryPicker.loadError', {}, 'Failed to load directory'));
    }
  }

  _cacheElements() {
    const modal = document.getElementById('directoryPickerModal');
    this.elements = {
      modal,
      closeBtn: document.getElementById('directoryPickerCloseBtn'),
      pathInput: document.getElementById('directoryPickerPathInput'),
      goBtn: document.getElementById('directoryPickerGoBtn'),
      upBtn: document.getElementById('directoryPickerUpBtn'),
      currentPathEl: document.getElementById('directoryPickerCurrentPath'),
      folderList: document.getElementById('directoryPickerFolderList'),
      errorEl: document.getElementById('directoryPickerError'),
      selectBtn: document.getElementById('directoryPickerSelectBtn')
    };
  }

  _bind(target, type, handler, options) {
    target.addEventListener(type, handler, options);
    this._bindings.push([target, type, handler, options]);
  }

  _bindEvents() {
    const { modal, closeBtn, pathInput, goBtn, upBtn, selectBtn } = this.elements;

    this._bind(closeBtn, 'click', () => this.close());
    this._bind(goBtn, 'click', () => this.loadDirectory(pathInput.value.trim()));
    this._bind(pathInput, 'keydown', (event) => {
      if (event.key === 'Enter') {
        this.loadDirectory(pathInput.value.trim());
      }
    });
    this._bind(upBtn, 'click', () => {
      // Server-provided parent_path: Windows paths cannot be derived client-side.
      if (this.parentPath) {
        this.loadDirectory(this.parentPath);
      }
    });
    this._bind(selectBtn, 'click', () => this._selectCurrent());

    // Capture phase + stopPropagation so an ESC here never reaches the
    // settings modal's own ESC handler underneath.
    this._bind(document, 'keydown', (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        this.close();
      }
    }, true);

    // Backdrop click (the .modal element itself, not its content).
    this._bind(modal, 'click', (event) => {
      if (event.target === modal) {
        this.close();
      }
    });
  }

  _unbindEvents() {
    for (const [target, type, handler, options] of this._bindings) {
      target.removeEventListener(type, handler, options);
    }
    this._bindings = [];
  }

  _renderDirectory(data) {
    this.currentPath = data.current_path || '';
    this.parentPath = data.parent_path || null;

    this.elements.currentPathEl.textContent = this.currentPath;
    this.elements.pathInput.value = this.currentPath;
    this.elements.upBtn.disabled = !this.parentPath;

    const folderList = this.elements.folderList;
    folderList.innerHTML = '';

    const directories = data.directories || [];
    if (directories.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'directory-picker-empty';
      empty.textContent = translate('settings.directoryPicker.emptyFolder', {}, 'This folder is empty');
      folderList.appendChild(empty);
      return;
    }

    directories.forEach((entry) => {
      folderList.appendChild(this._createFolderItem(entry));
    });
  }

  // Each entry is { name, path, is_parent }; the server supplies the full
  // child path, so navigation never joins path segments client-side.
  _createFolderItem(entry) {
    const item = document.createElement('div');
    item.className = 'folder-item';
    item.innerHTML = `
      <i class="fas fa-folder"></i>
      <span class="item-name">${this._escapeHtml(entry.name)}</span>
    `;
    item.addEventListener('click', () => {
      this.loadDirectory(entry.path);
    });
    return item;
  }

  _selectCurrent() {
    if (!this.currentPath) return;
    if (this.onSelect) {
      this.onSelect(this.currentPath);
    }
    this.close();
  }

  _showError(message) {
    this.elements.errorEl.textContent = message;
    this.elements.errorEl.style.display = 'block';
  }

  _clearError() {
    this.elements.errorEl.textContent = '';
    this.elements.errorEl.style.display = 'none';
  }

  _escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}

export const directoryPickerModal = new DirectoryPickerModal();
export { DirectoryPickerModal };
