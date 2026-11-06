import { translate } from '../utils/i18nHelpers.js';

// Server error codes from POST /api/lm/create-directory mapped to locale keys
// so the picker can explain a failed creation in the user's language.
const CREATE_ERROR_I18N = {
  name_required: ['settings.directoryPicker.nameRequired', 'Enter a folder name'],
  name_invalid: ['settings.directoryPicker.nameInvalid', 'Folder name contains invalid characters'],
  already_exists: ['settings.directoryPicker.alreadyExists', 'A folder with this name already exists'],
  permission_denied: ['settings.directoryPicker.permissionDenied', 'Permission denied'],
};

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
    this.isCreating = false;
    this.isNewFolderOpen = false;
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
    this._hideNewFolderRow();
    this._setCreating(false);
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
      selectBtn: document.getElementById('directoryPickerSelectBtn'),
      newFolderBtn: document.getElementById('directoryPickerNewFolderBtn'),
      newFolderRow: document.getElementById('directoryPickerNewFolderRow'),
      newFolderInput: document.getElementById('directoryPickerNewFolderInput'),
      newFolderConfirmBtn: document.getElementById('directoryPickerNewFolderConfirmBtn'),
      newFolderCancelBtn: document.getElementById('directoryPickerNewFolderCancelBtn')
    };
  }

  _bind(target, type, handler, options) {
    target.addEventListener(type, handler, options);
    this._bindings.push([target, type, handler, options]);
  }

  _bindEvents() {
    const {
      modal, closeBtn, pathInput, goBtn, upBtn, selectBtn,
      newFolderBtn, newFolderInput, newFolderConfirmBtn, newFolderCancelBtn
    } = this.elements;

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

    this._bind(newFolderBtn, 'click', () => this._showNewFolderRow());
    this._bind(newFolderConfirmBtn, 'click', () => this._createFolder());
    this._bind(newFolderCancelBtn, 'click', () => this._hideNewFolderRow());
    this._bind(newFolderInput, 'keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        this._createFolder();
      }
    });

    // Capture phase + stopPropagation so an ESC here never reaches the
    // settings modal's own ESC handler underneath.
    this._bind(document, 'keydown', (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        if (this.isNewFolderOpen) {
          // The inline row is the innermost layer: dismiss it first.
          event.preventDefault();
          this._hideNewFolderRow();
          return;
        }
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

    // The virtual Windows drive list has no current_path: there is no
    // directory to create a folder in.
    if (!this.currentPath) {
      this._hideNewFolderRow();
    }
    this.elements.newFolderBtn.disabled = !this.currentPath || this.isNewFolderOpen;

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

  _showNewFolderRow() {
    if (!this.currentPath || this.isCreating) return;
    this._clearError();
    this.isNewFolderOpen = true;
    this.elements.newFolderRow.style.display = 'flex';
    this.elements.newFolderBtn.disabled = true;
    this.elements.newFolderInput.value = '';
    this.elements.newFolderInput.focus();
  }

  _hideNewFolderRow() {
    this.isNewFolderOpen = false;
    if (this.elements.newFolderRow) {
      this.elements.newFolderRow.style.display = 'none';
    }
    if (this.elements.newFolderBtn) {
      this.elements.newFolderBtn.disabled = !this.currentPath;
    }
  }

  async _createFolder() {
    if (this.isCreating || !this.currentPath) return;

    const name = this.elements.newFolderInput.value.trim();
    if (!name) {
      this._showError(translate('settings.directoryPicker.nameRequired', {}, 'Enter a folder name'));
      return;
    }
    // Reject path separators up front; the server validates the name again.
    if (/[\\/]/.test(name)) {
      this._showError(translate('settings.directoryPicker.nameInvalid', {}, 'Folder name contains invalid characters'));
      return;
    }

    this._setCreating(true);
    try {
      const response = await fetch('/api/lm/create-directory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: this.currentPath, name })
      });
      const data = await response.json();

      if (data.success) {
        this._hideNewFolderRow();
        this._clearError();
        // Enter the new folder so it can be picked with one click.
        await this.loadDirectory(data.path || this.currentPath);
      } else {
        this._showError(this._getCreateErrorMessage(data));
      }
    } catch (error) {
      console.error('Error creating directory:', error);
      this._showError(translate('settings.directoryPicker.createError', {}, 'Failed to create folder'));
    } finally {
      this._setCreating(false);
    }
  }

  _setCreating(creating) {
    this.isCreating = creating;
    if (this.elements.newFolderConfirmBtn) {
      this.elements.newFolderConfirmBtn.disabled = creating;
    }
    if (this.elements.newFolderInput) {
      this.elements.newFolderInput.disabled = creating;
    }
  }

  _getCreateErrorMessage(data) {
    const entry = CREATE_ERROR_I18N[data?.error_code];
    if (entry) {
      return translate(entry[0], {}, entry[1]);
    }
    return data?.error || translate('settings.directoryPicker.createError', {}, 'Failed to create folder');
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
