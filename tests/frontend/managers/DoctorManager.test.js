import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mountMarkup, resetDom } from '../utils/domFixtures.js';

vi.mock('../../../static/js/managers/ModalManager.js', () => ({
  modalManager: {
    showModal: vi.fn(),
  },
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: vi.fn(),
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: vi.fn((key, _params, fallback) => fallback || key),
}));

vi.mock('../../../static/js/components/shared/utils.js', () => ({
  escapeHtml: vi.fn((value) => String(value)),
}));

import { DoctorManager } from '../../../static/js/managers/DoctorManager.js';

function renderDoctorFixture() {
  mountMarkup(`
    <button id="doctorTriggerBtn"></button>
    <span id="doctorStatusBadge" class="hidden"></span>
    <div id="doctorModal"></div>
    <div id="doctorIssuesList"></div>
    <div id="doctorSummaryText"></div>
    <div id="doctorSummaryBadge"></div>
    <div id="doctorLoadingState"></div>
    <button id="doctorRefreshBtn"></button>
    <button id="doctorExportBtn"></button>
  `);
  document.body.dataset.appVersion = '1.2.3-test';
}

describe('DoctorManager', () => {
  beforeEach(() => {
    resetDom();
    vi.clearAllMocks();
    delete window.__lmDoctorConsolePatched;
    delete window.__lmDoctorConsoleEntries;
  });

  it('does not run diagnostics during initialize', () => {
    renderDoctorFixture();
    const manager = new DoctorManager();
    const refreshSpy = vi.spyOn(manager, 'refreshDiagnostics').mockResolvedValue(undefined);

    manager.initialize();

    expect(refreshSpy).not.toHaveBeenCalled();
  });

  it('builds a cache-busted reload URL that preserves the current location', () => {
    renderDoctorFixture();
    window.history.replaceState({}, '', '/loras?filter=active#details');
    vi.spyOn(Date, 'now').mockReturnValue(1234567890);

    const manager = new DoctorManager();

    const url = manager.buildReloadUrl();

    expect(url).toBe('http://localhost:3000/loras?filter=active&_lm_reload=1234567890#details');
  });

  it('delegates reload-page actions to reloadUi', async () => {
    renderDoctorFixture();
    const manager = new DoctorManager();
    const reloadSpy = vi.spyOn(manager, 'reloadUi').mockImplementation(() => undefined);

    await manager.handleAction('reload-page');

    expect(reloadSpy).toHaveBeenCalledTimes(1);
  });
});
