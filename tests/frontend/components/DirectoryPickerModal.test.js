import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: (key, params = {}, fallback = null) => fallback ?? key,
}));

import { directoryPickerModal } from '../../../static/js/components/DirectoryPickerModal.js';

function buildModalDom() {
  document.body.innerHTML = `
    <div id="directoryPickerModal" class="modal directory-picker-modal" style="display: none;">
      <div class="modal-content directory-picker-content">
        <button class="close" id="directoryPickerCloseBtn">&times;</button>
        <h3>Select folder</h3>
        <div class="directory-picker-path-row">
          <input type="text" id="directoryPickerPathInput">
          <button id="directoryPickerGoBtn">Go</button>
        </div>
        <div class="directory-browser" id="directoryPickerBrowser">
          <div class="browser-header">
            <button class="back-btn" id="directoryPickerUpBtn"></button>
            <div class="current-path" id="directoryPickerCurrentPath"></div>
          </div>
          <div class="browser-content">
            <div class="folder-list" id="directoryPickerFolderList"></div>
            <div class="directory-picker-error" id="directoryPickerError" style="display: none;"></div>
          </div>
          <div class="browser-footer">
            <button class="primary-btn" id="directoryPickerSelectBtn">Select</button>
          </div>
        </div>
      </div>
    </div>`;
}

function okResponse(payload) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ success: true, ...payload }),
  };
}

describe('DirectoryPickerModal', () => {
  let fetchMock;

  beforeEach(() => {
    vi.clearAllMocks();
    buildModalDom();
    document.body.classList.remove('modal-open');

    fetchMock = vi.fn(async () => okResponse({
      current_path: '/home/user',
      parent_path: '/home',
      directories: [
        { name: 'photos', path: '/home/user/photos', is_parent: false },
        { name: 'models', path: '/home/user/models', is_parent: false },
      ],
    }));
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    directoryPickerModal.close();
    vi.unstubAllGlobals();
  });

  function lastRequestBody() {
    return JSON.parse(fetchMock.mock.calls.at(-1)[1].body);
  }

  function modalEl() {
    return document.getElementById('directoryPickerModal');
  }

  it('open() loads the initial path via POST /api/lm/browse-directory', async () => {
    directoryPickerModal.open({ initialPath: '/home/user', onSelect: vi.fn() });

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/lm/browse-directory');
    expect(options.method).toBe('POST');
    expect(lastRequestBody().path).toBe('/home/user');
    expect(modalEl().style.display).toBe('block');
    expect(document.body.classList.contains('modal-open')).toBe(true);
  });

  it('renders the folder list and current path', async () => {
    directoryPickerModal.open({ initialPath: '/home/user', onSelect: vi.fn() });

    await vi.waitFor(() => {
      expect(document.querySelectorAll('#directoryPickerFolderList .folder-item')).toHaveLength(2);
    });
    expect(document.getElementById('directoryPickerCurrentPath').textContent).toBe('/home/user');
    const names = [...document.querySelectorAll('#directoryPickerFolderList .item-name')].map((el) => el.textContent);
    expect(names).toEqual(['photos', 'models']);
  });

  it('drills down on folder click using the server-provided entry path', async () => {
    directoryPickerModal.open({ initialPath: '/home/user', onSelect: vi.fn() });
    await vi.waitFor(() => {
      expect(document.querySelectorAll('#directoryPickerFolderList .folder-item')).toHaveLength(2);
    });
    fetchMock.mockClear();

    document.querySelectorAll('#directoryPickerFolderList .folder-item')[0].click();

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(lastRequestBody().path).toBe('/home/user/photos');
  });

  it('drills down from a Windows path using the server-provided entry path', async () => {
    fetchMock.mockImplementation(async () => okResponse({
      current_path: 'C:\\Users\\miao',
      parent_path: 'C:\\Users',
      directories: [
        { name: 'models', path: 'C:\\Users\\miao\\models', is_parent: false },
      ],
    }));
    directoryPickerModal.open({ initialPath: 'C:\\Users\\miao', onSelect: vi.fn() });
    await vi.waitFor(() => {
      expect(document.querySelectorAll('#directoryPickerFolderList .folder-item')).toHaveLength(1);
    });
    fetchMock.mockClear();

    document.querySelector('#directoryPickerFolderList .folder-item').click();

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(lastRequestBody().path).toBe('C:\\Users\\miao\\models');
  });

  it('navigates up via the server-provided parent_path', async () => {
    directoryPickerModal.open({ initialPath: '/home/user', onSelect: vi.fn() });
    await vi.waitFor(() => {
      expect(document.getElementById('directoryPickerCurrentPath').textContent).toBe('/home/user');
    });
    fetchMock.mockClear();

    document.getElementById('directoryPickerUpBtn').click();

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(lastRequestBody().path).toBe('/home');
  });

  it('disables the Up button when parent_path is null', async () => {
    fetchMock.mockImplementation(async () => okResponse({
      current_path: '/',
      parent_path: null,
      directories: [],
    }));
    directoryPickerModal.open({ initialPath: '/', onSelect: vi.fn() });

    await vi.waitFor(() => {
      expect(document.getElementById('directoryPickerCurrentPath').textContent).toBe('/');
    });
    const upBtn = document.getElementById('directoryPickerUpBtn');
    expect(upBtn.disabled).toBe(true);
    fetchMock.mockClear();

    upBtn.click();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('shows an empty-folder message for a directory without subfolders', async () => {
    fetchMock.mockImplementation(async () => okResponse({
      current_path: '/home/user/empty',
      parent_path: '/home/user',
      directories: [],
    }));
    directoryPickerModal.open({ initialPath: '/home/user/empty', onSelect: vi.fn() });

    await vi.waitFor(() => {
      expect(document.querySelector('#directoryPickerFolderList .directory-picker-empty')).not.toBeNull();
    });
  });

  it('calls onSelect with current_path and closes on Select', async () => {
    const onSelect = vi.fn();
    directoryPickerModal.open({ initialPath: '/home/user', onSelect });
    await vi.waitFor(() => {
      expect(document.getElementById('directoryPickerCurrentPath').textContent).toBe('/home/user');
    });

    document.getElementById('directoryPickerSelectBtn').click();

    expect(onSelect).toHaveBeenCalledWith('/home/user');
    expect(modalEl().style.display).toBe('none');
  });

  it('shows the backend error message and keeps the previous listing', async () => {
    directoryPickerModal.open({ initialPath: '/home/user', onSelect: vi.fn() });
    await vi.waitFor(() => {
      expect(document.querySelectorAll('#directoryPickerFolderList .folder-item')).toHaveLength(2);
    });

    fetchMock.mockImplementation(async () => ({
      ok: false,
      status: 404,
      json: async () => ({ success: false, error: 'Directory not found' }),
    }));

    await directoryPickerModal.loadDirectory('/gone');

    const errorEl = document.getElementById('directoryPickerError');
    expect(errorEl.textContent).toBe('Directory not found');
    expect(errorEl.style.display).toBe('block');
    expect(document.querySelectorAll('#directoryPickerFolderList .folder-item')).toHaveLength(2);
    expect(document.getElementById('directoryPickerCurrentPath').textContent).toBe('/home/user');
  });

  it('closes on ESC and stops propagation to modals underneath', async () => {
    const underlyingEscSpy = vi.fn();
    document.addEventListener('keydown', underlyingEscSpy);

    directoryPickerModal.open({ initialPath: '/home/user', onSelect: vi.fn() });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());

    const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    document.getElementById('directoryPickerPathInput').dispatchEvent(event);

    expect(modalEl().style.display).toBe('none');
    expect(underlyingEscSpy).not.toHaveBeenCalled();
    // The settings modal's body lock must survive the picker closing.
    expect(document.body.classList.contains('modal-open')).toBe(true);

    document.removeEventListener('keydown', underlyingEscSpy);
  });

  it('loads the typed path on Go click and on Enter', async () => {
    directoryPickerModal.open({ initialPath: '/home/user', onSelect: vi.fn() });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    fetchMock.mockClear();

    const input = document.getElementById('directoryPickerPathInput');
    input.value = '/var/models';
    document.getElementById('directoryPickerGoBtn').click();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(lastRequestBody().path).toBe('/var/models');

    fetchMock.mockClear();
    input.value = '/tmp/other';
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(lastRequestBody().path).toBe('/tmp/other');
  });

  it('closes on backdrop click but not on content click', async () => {
    directoryPickerModal.open({ initialPath: '/home/user', onSelect: vi.fn() });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());

    modalEl().querySelector('.directory-picker-content').click();
    expect(modalEl().style.display).toBe('block');

    modalEl().click();
    expect(modalEl().style.display).toBe('none');
  });
});
