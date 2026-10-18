import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const MODAL_MANAGER_MODULE = new URL('../../../static/js/managers/ModalManager.js', import.meta.url).pathname;
const MEDIA_VIEWER_MODULE = new URL('../../../static/js/components/shared/MediaViewer.js', import.meta.url).pathname;

function setupDom() {
  document.body.innerHTML = `
    <div id="modelModal" class="modal">
      <div class="modal-content">
        <img class="media-wrapper" src="" alt="">
      </div>
    </div>
  `;
}

describe('MediaViewer Escape handling', () => {
  let ModalManager;
  let manager;
  let openMediaViewer;
  let isMediaViewerOpen;

  beforeEach(async () => {
    vi.useFakeTimers();
    setupDom();
    window.scrollTo = vi.fn();
    ({ ModalManager } = await import(MODAL_MANAGER_MODULE));
    manager = new ModalManager();
    manager.initialize();
    ({ openMediaViewer, isMediaViewerOpen } = await import(MEDIA_VIEWER_MODULE));
  });

  afterEach(() => {
    vi.runAllTimers();
    vi.useRealTimers();
    document.body.innerHTML = '';
    vi.resetModules();
  });

  it('closes only the media viewer, not the underlying modal, on Escape', () => {
    manager.showModal('modelModal');
    expect(manager.getModal('modelModal').isOpen).toBe(true);

    openMediaViewer('https://example.com/image.png');
    expect(isMediaViewerOpen()).toBe(true);

    // Dispatch on document.body (real keydown target is the focused element,
    // never document itself) so the capture handler fires before the bubble one.
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));

    expect(isMediaViewerOpen()).toBe(false);
    expect(manager.getModal('modelModal').isOpen).toBe(true);
  });

  it('still lets Escape close the modal when no viewer is open', () => {
    manager.showModal('modelModal');

    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));

    expect(manager.getModal('modelModal').isOpen).toBe(false);
  });
});
