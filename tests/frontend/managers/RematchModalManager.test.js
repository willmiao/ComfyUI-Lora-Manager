import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const showToastMock = vi.fn();
const translateMock = vi.fn((key, params, fallback) => (typeof fallback === 'string' ? fallback : key));
const modalManagerMock = {
  showModal: vi.fn(),
  closeModal: vi.fn(),
};

vi.mock('../../../static/js/managers/ModalManager.js', () => ({
  modalManager: modalManagerMock,
}));

vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: translateMock,
}));

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: showToastMock,
}));

async function getManager() {
  const { rematchModalManager } = await import(
    '../../../static/js/managers/RematchModalManager.js'
  );
  return rematchModalManager;
}

describe('RematchModalManager options dialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = `
      <p id="rematchOptionsMessage"></p>
      <input type="checkbox" id="rematchOptionsRelaxed">
    `;
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('does not invoke the callback until confirmOptions is called', async () => {
    const manager = await getManager();
    const onConfirm = vi.fn();

    manager.showOptionsModal({ recipeCount: 3, onConfirm });

    expect(modalManagerMock.showModal).toHaveBeenCalledWith('rematchOptionsModal');
    expect(onConfirm).not.toHaveBeenCalled();
    // Bulk message mentions the selection size.
    expect(document.getElementById('rematchOptionsMessage').textContent).toContain('3');
    // The checkbox always starts unchecked.
    expect(document.getElementById('rematchOptionsRelaxed').checked).toBe(false);

    manager.confirmOptions();
    expect(onConfirm).toHaveBeenCalledWith({ relaxed: false });
    expect(modalManagerMock.closeModal).toHaveBeenCalledWith('rematchOptionsModal');
  });

  it('uses the generic message when no recipe count is given', async () => {
    const manager = await getManager();

    manager.showOptionsModal({ onConfirm: vi.fn() });

    expect(translateMock).toHaveBeenCalledWith(
      'modals.rematchOptions.messageGlobal',
      {},
      'All recipes will be scanned against your local model library.'
    );
  });

  it('uses the single-recipe message for scope: single', async () => {
    const manager = await getManager();

    manager.showOptionsModal({ scope: 'single', onConfirm: vi.fn() });

    expect(translateMock).toHaveBeenCalledWith(
      'modals.rematchOptions.messageSingle',
      {},
      'This recipe will be scanned against your local model library.'
    );
  });

  it('passes relaxed: true when the checkbox is checked', async () => {
    const manager = await getManager();
    const onConfirm = vi.fn();

    manager.showOptionsModal({ onConfirm });
    document.getElementById('rematchOptionsRelaxed').checked = true;
    manager.confirmOptions();

    expect(onConfirm).toHaveBeenCalledWith({ relaxed: true });
  });

  it('resets the checkbox to unchecked each time the dialog opens', async () => {
    const manager = await getManager();
    const checkbox = document.getElementById('rematchOptionsRelaxed');
    checkbox.checked = true;

    manager.showOptionsModal({ onConfirm: vi.fn() });

    expect(checkbox.checked).toBe(false);
  });

  it('cancelOptions runs nothing and clears the callback', async () => {
    const manager = await getManager();
    const onConfirm = vi.fn();

    manager.showOptionsModal({ onConfirm });
    manager.cancelOptions();

    expect(modalManagerMock.closeModal).toHaveBeenCalledWith('rematchOptionsModal');
    // A later confirm must not fire the cancelled callback.
    manager.confirmOptions();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

