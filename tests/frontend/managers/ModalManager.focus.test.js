import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const MODAL_MANAGER_MODULE = new URL('../../../static/js/managers/ModalManager.js', import.meta.url).pathname;

function setupDom() {
  document.body.innerHTML = `
    <button id="triggerBtn">Trigger</button>
    <div id="deleteModal" class="modal delete-modal">
      <div class="modal-content delete-modal-content">
        <button class="cancel-btn">Cancel</button>
        <button class="delete-btn">Delete</button>
      </div>
    </div>
    <div id="excludeModal" class="modal delete-modal">
      <div class="modal-content delete-modal-content">
        <button class="cancel-btn">Cancel</button>
        <button class="exclude-btn">Exclude</button>
      </div>
    </div>
    <div id="plainModal" class="modal">
      <div class="modal-content">
        <button class="cancel-btn">Cancel</button>
      </div>
    </div>
  `;
}

describe('ModalManager delete-modal focus handling', () => {
  let ModalManager;
  let manager;

  beforeEach(async () => {
    setupDom();
    window.scrollTo = vi.fn();
    ({ ModalManager } = await import(MODAL_MANAGER_MODULE));
    manager = new ModalManager();
    for (const id of ['deleteModal', 'excludeModal', 'plainModal']) {
      manager.registerModal(id, {
        element: document.getElementById(id),
        onClose: () => {},
      });
    }
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('focuses the cancel button when a delete-type modal opens', () => {
    const trigger = document.getElementById('triggerBtn');
    trigger.focus();

    manager.showModal('deleteModal');

    expect(document.activeElement).toBe(
      document.querySelector('#deleteModal .cancel-btn')
    );
  });

  it('restores focus to the previously focused element on close', () => {
    const trigger = document.getElementById('triggerBtn');
    trigger.focus();

    manager.showModal('deleteModal');
    manager.closeModal('deleteModal');

    expect(document.activeElement).toBe(trigger);
  });

  it('does not touch focus for a non-delete modal', () => {
    const trigger = document.getElementById('triggerBtn');
    trigger.focus();

    manager.showModal('plainModal');

    expect(document.activeElement).toBe(trigger);

    manager.closeModal('plainModal');
    expect(document.activeElement).toBe(trigger);
  });

  it('does not treat delete-modal-styled modals without a delete button as delete modals', () => {
    const trigger = document.getElementById('triggerBtn');
    trigger.focus();

    manager.showModal('excludeModal');

    expect(document.activeElement).toBe(trigger);

    manager.closeModal('excludeModal');
    expect(document.activeElement).toBe(trigger);
  });

  it('skips the focus restore when the previously focused element is gone', () => {
    const trigger = document.getElementById('triggerBtn');
    trigger.focus();

    manager.showModal('deleteModal');
    trigger.remove();

    expect(() => manager.closeModal('deleteModal')).not.toThrow();
  });
});
