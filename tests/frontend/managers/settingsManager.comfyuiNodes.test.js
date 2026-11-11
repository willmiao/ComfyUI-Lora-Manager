import { beforeEach, describe, expect, it, vi } from 'vitest';

import { readTemplate } from '../utils/domFixtures.js';

const { requestComfyUISettingsMock, showToastMock } = vi.hoisted(() => ({
  requestComfyUISettingsMock: vi.fn(),
  showToastMock: vi.fn(),
}));

vi.mock('../../../static/js/managers/ModalManager.js', () => ({
  modalManager: {
    closeModal: vi.fn(),
    showModal: vi.fn(),
  },
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
}));

vi.mock('../../../static/js/utils/comfySettingsNavigation.js', () => ({
  openComfyUISettings: requestComfyUISettingsMock,
}));

vi.mock('../../../static/js/state/index.js', () => ({
  state: {
    global: {
      settings: {},
    },
  },
  createDefaultSettings: () => ({
    language: 'en',
    standalone_mode: false,
    folder_paths: {},
    folder_path_schema: [],
  }),
}));

vi.mock('../../../static/js/api/modelApiFactory.js', () => ({
  resetAndReload: vi.fn(),
}));

vi.mock('../../../static/js/utils/constants.js', () => ({
  DOWNLOAD_PATH_TEMPLATES: {},
  DEFAULT_PATH_TEMPLATES: {},
  MAPPABLE_BASE_MODELS: [],
  PATH_TEMPLATE_PLACEHOLDERS: {},
  FILENAME_TEMPLATE_PLACEHOLDERS: [],
  DEFAULT_FILENAME_TEMPLATES: { lora: '', checkpoint: '', embedding: '' },
  DEFAULT_PRIORITY_TAG_CONFIG: {},
  getMappableBaseModelsDynamic: () => [],
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: (_key, _params, fallback) => fallback ?? '',
}));

vi.mock('../../../static/js/i18n/index.js', () => ({
  i18n: {
    getCurrentLocale: () => 'en',
    setLanguage: vi.fn().mockResolvedValue(),
  },
}));

vi.mock('../../../static/js/components/shared/ModelCard.js', () => ({
  configureModelCardVideo: vi.fn(),
}));

import { SettingsManager } from '../../../static/js/managers/SettingsManager.js';
import { state } from '../../../static/js/state/index.js';

const createManager = () => {
  const initSettingsSpy = vi
    .spyOn(SettingsManager.prototype, 'initializeSettings')
    .mockResolvedValue();
  const initializeSpy = vi
    .spyOn(SettingsManager.prototype, 'initialize')
    .mockImplementation(() => {});

  const manager = new SettingsManager();
  initSettingsSpy.mockRestore();
  initializeSpy.mockRestore();
  return manager;
};

const buildSettingsDom = () => {
  document.body.innerHTML = `
    <nav>
      <button class="settings-nav-item active" data-section="general">General</button>
      <button class="settings-nav-item" data-section="comfyuiNodes" data-comfyui-only>ComfyUI Nodes</button>
    </nav>
    <div class="settings-form">
      <div id="section-general" class="settings-section active" data-section="general">
        <label>General</label>
      </div>
      ${readTemplate('components/modals/settings/comfyui_nodes.html')}
    </div>
    <div id="nodeLoraNameDisplayHelp" data-comfyui-only>
      <button id="nodeSettingsLink" data-open-comfyui-settings>Node labels</button>
    </div>
  `;
};

describe('SettingsManager ComfyUI node settings', () => {
  beforeEach(() => {
    buildSettingsDom();
    state.global.settings = { standalone_mode: false };
    requestComfyUISettingsMock.mockReset().mockResolvedValue('opener');
    showToastMock.mockClear();
  });

  it('navigates to the guide and binds both open-settings actions', () => {
    const manager = createManager();
    manager.initialize();

    document.querySelector('[data-section="comfyuiNodes"]').click();
    expect(document.getElementById('section-comfyuiNodes').classList.contains('active')).toBe(true);
    expect(document.getElementById('section-general').classList.contains('active')).toBe(false);

    document.getElementById('openComfyUISettingsBtn').click();
    document.getElementById('nodeSettingsLink').click();
    expect(requestComfyUISettingsMock).toHaveBeenCalledTimes(2);
  });

  it('hides every ComfyUI-only element and excludes the guide from standalone search', async () => {
    const manager = createManager();
    manager.updateComfyUISettingsVisibility();
    document.querySelectorAll('[data-comfyui-only]').forEach((element) => {
      expect(element.style.display).toBe('');
    });

    state.global.settings.standalone_mode = true;
    manager.updateComfyUISettingsVisibility();
    document.querySelectorAll('[data-comfyui-only]').forEach((element) => {
      expect(element.style.display).toBe('none');
    });

    manager.performSearch('autocomplete');
    expect(document.getElementById('section-general').classList.contains('active')).toBe(true);
    expect(document.getElementById('section-comfyuiNodes').classList.contains('active')).toBe(false);

    await manager.openComfyUISettings();
    expect(requestComfyUISettingsMock).not.toHaveBeenCalled();
  });

  it('announces when settings open in an existing tab', async () => {
    requestComfyUISettingsMock.mockResolvedValue('existing');
    const manager = createManager();

    await manager.openComfyUISettings();

    expect(showToastMock).toHaveBeenCalledWith('settings.comfyuiNodes.existingTab', {}, 'info');
  });

  it('shows the manual fallback when a new ComfyUI window is blocked', async () => {
    requestComfyUISettingsMock.mockResolvedValue(null);
    const manager = createManager();

    await manager.openComfyUISettings();

    expect(showToastMock).toHaveBeenCalledWith('settings.comfyuiNodes.openFailed', {}, 'warning');
  });
});
