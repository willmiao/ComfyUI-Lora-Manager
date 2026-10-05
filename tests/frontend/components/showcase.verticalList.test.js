import { describe, it, beforeEach, afterEach, expect } from 'vitest';

const { SHOWCASE_MODULE, VERTICAL_MODULE, MEDIA_UTILS_MODULE, MEDIA_VIEWER_MODULE } = vi.hoisted(() => ({
  SHOWCASE_MODULE: new URL('../../../static/js/components/shared/showcase/ShowcaseView.js', import.meta.url).pathname,
  VERTICAL_MODULE: new URL('../../../static/js/components/shared/showcase/VerticalListView.js', import.meta.url).pathname,
  MEDIA_UTILS_MODULE: new URL('../../../static/js/components/shared/showcase/MediaUtils.js', import.meta.url).pathname,
  MEDIA_VIEWER_MODULE: new URL('../../../static/js/components/shared/MediaViewer.js', import.meta.url).pathname,
}));

vi.mock(MEDIA_UTILS_MODULE, () => ({
  initLazyLoading: vi.fn(),
  initNsfwBlurHandlers: vi.fn(),
  initMetadataPanelHandlers: vi.fn(),
  initMediaControlHandlers: vi.fn(),
  positionAllMediaControls: vi.fn(),
}));

vi.mock(MEDIA_VIEWER_MODULE, () => ({
  openMediaViewer: vi.fn(),
  isMediaViewerOpen: vi.fn(() => false),
}));

const PREVIEW_URL = '/loras_static/preview/abc.png';

const IMAGES = [
  { url: 'https://image.civitai.com/vl/111.jpeg', width: 512, height: 768, nsfwLevel: 0 },
  { url: 'https://image.civitai.com/vl/222.jpeg', width: 768, height: 512, nsfwLevel: 0 },
  { url: 'https://image.civitai.com/vl/333.mp4', width: 512, height: 512, nsfwLevel: 0 },
];

describe('Showcase vertical list layout', () => {
  let state;

  beforeEach(async () => {
    Element.prototype.scrollIntoView = vi.fn();
    const stateModule = await import('../../../static/js/state/index.js');
    state = stateModule.state;
    state.settings.show_only_sfw = false;
    state.settings.blur_mature_content = false;
    state.settings.showcase_layout = 'vertical';
    state.global.settings.example_images_path = '/tmp/examples';
    document.body.innerHTML = '';
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete window.settingsManager;
    state.settings.showcase_layout = 'gallery';
  });

  it('defaults the showcase_layout setting to gallery', async () => {
    const { createDefaultSettings } = await import('../../../static/js/state/index.js');
    // DEFAULT_SETTINGS_BASE feeds both the frontend state and the backend key set
    expect(createDefaultSettings().showcase_layout).toBe('gallery');
  });

  it('renders every example stacked full-width with its own panel and controls', async () => {
    const { renderShowcaseContent } = await import(SHOWCASE_MODULE);

    const html = renderShowcaseContent(IMAGES, [], PREVIEW_URL, true);
    const host = document.createElement('div');
    host.innerHTML = html;

    expect(host.querySelector('.showcase-gallery.showcase-vertical')).toBeTruthy();
    const list = host.querySelector('.vertical-list-container');
    expect(list).toBeTruthy();
    const wrappers = list.querySelectorAll('.media-wrapper');
    expect(wrappers).toHaveLength(3);
    // Every item keeps its aspect ratio via the padding-bottom hack and gets
    // its own metadata panel + media controls
    wrappers.forEach(wrapper => {
      expect(wrapper.getAttribute('style')).toContain('padding-bottom');
      expect(wrapper.querySelector('.image-metadata-panel')).toBeTruthy();
      expect(wrapper.querySelector('.media-controls')).toBeTruthy();
    });
    // Gallery-only chrome is absent
    expect(host.querySelector('.gallery-main')).toBeNull();
    expect(host.querySelector('.gallery-strip')).toBeNull();
    expect(host.querySelector('#galleryPrevBtn')).toBeNull();
  });

  it('renders media lazy: data-* sources only, no real src until observed', async () => {
    const { renderShowcaseContent } = await import(SHOWCASE_MODULE);

    const html = renderShowcaseContent(IMAGES, [], PREVIEW_URL, true);
    const host = document.createElement('div');
    host.innerHTML = html;

    const media = host.querySelectorAll('.vertical-list-container .media-wrapper img, .vertical-list-container .media-wrapper video');
    expect(media).toHaveLength(3);
    media.forEach(el => {
      expect(el.classList.contains('lazy')).toBe(true);
      expect(el.dataset.remoteSrc).toBeTruthy();
      expect(el.hasAttribute('src')).toBe(false);
    });
    // The third example is a video
    expect(host.querySelectorAll('.vertical-list-container video')).toHaveLength(1);
  });

  it('filters NSFW examples and reports the hidden count', async () => {
    const { renderShowcaseContent } = await import(SHOWCASE_MODULE);
    state.settings.show_only_sfw = true;

    const images = [
      IMAGES[0],
      { url: 'https://image.civitai.com/vl/444.jpeg', width: 10, height: 10, nsfwLevel: 32 },
    ];
    const html = renderShowcaseContent(images, [], '', true);
    const host = document.createElement('div');
    host.innerHTML = html;

    expect(host.querySelectorAll('.vertical-list-container .media-wrapper')).toHaveLength(1);
    expect(host.querySelector('.nsfw-filter-notification')).toBeTruthy();
  });

  it('toggles between the collapsed indicator bar and the expanded list', async () => {
    const { renderShowcaseContent, initShowcaseContent } = await import(SHOWCASE_MODULE);

    document.body.innerHTML = `<div id="showcase-tab">${renderShowcaseContent(IMAGES, [], PREVIEW_URL)}</div>`;

    // Collapsed: indicator bar only, no media rendered even in vertical mode
    expect(document.querySelector('.gallery-indicator-bar')).toBeTruthy();
    expect(document.querySelector('.vertical-list-container')).toBeNull();

    initShowcaseContent(document.querySelector('.showcase-gallery'));

    // Expand → vertical list
    document.querySelector('#galleryShowBtn').click();
    expect(document.querySelector('.showcase-vertical')).toBeTruthy();
    expect(document.querySelectorAll('.vertical-list-container .media-wrapper')).toHaveLength(3);

    // Collapse back to the indicator bar
    document.querySelector('#galleryShowBtn').click();
    expect(document.querySelector('.vertical-list-container')).toBeNull();
    expect(document.querySelector('.gallery-indicator-bar')).toBeTruthy();
  });

  it('keeps the back-to-top button available in vertical mode (gallery hides it)', async () => {
    const { renderShowcaseContent, initShowcaseContent } = await import(SHOWCASE_MODULE);

    // Expanded vertical list: no thumbnail strip in the corner, so the modal
    // must NOT get the showcase-expanded class that hides back-to-top
    document.body.innerHTML = `<div class="modal-content"><div id="showcase-tab">${renderShowcaseContent(IMAGES, [], PREVIEW_URL, true)}</div></div>`;
    initShowcaseContent(document.querySelector('.showcase-gallery'));
    expect(document.querySelector('.modal-content').classList.contains('showcase-expanded')).toBe(false);

    // Expanded gallery: the strip occupies the corner, button hidden as before
    state.settings.showcase_layout = 'gallery';
    document.body.innerHTML = `<div class="modal-content"><div id="showcase-tab">${renderShowcaseContent(IMAGES, [], PREVIEW_URL, true)}</div></div>`;
    initShowcaseContent(document.querySelector('.showcase-gallery'));
    expect(document.querySelector('.modal-content').classList.contains('showcase-expanded')).toBe(true);
  });

  it('switches between gallery and vertical renderers via the segmented toggle', async () => {
    const { renderShowcaseContent, initShowcaseContent } = await import(SHOWCASE_MODULE);

    // Stub the settings manager global (normally set by core.js); it persists
    // into state like the real saveSetting does
    const saveSetting = vi.fn(async (key, value) => { state.global.settings[key] = value; });
    window.settingsManager = { saveSetting };

    state.settings.showcase_layout = 'gallery';
    document.body.innerHTML = `<div id="showcase-tab">${renderShowcaseContent(IMAGES, [], PREVIEW_URL, true)}</div>`;
    initShowcaseContent(document.querySelector('.showcase-gallery'));

    // Gallery renders with the gallery segment active
    expect(document.querySelector('.gallery-strip')).toBeTruthy();
    expect(document.querySelector('[data-showcase-layout="gallery"]').classList.contains('active')).toBe(true);

    // Switch to the vertical list
    document.querySelector('[data-showcase-layout="vertical"]').click();
    await vi.waitFor(() => {
      expect(document.querySelector('.showcase-vertical')).toBeTruthy();
    });
    expect(saveSetting).toHaveBeenCalledWith('showcase_layout', 'vertical');
    expect(state.settings.showcase_layout).toBe('vertical');
    expect(document.querySelectorAll('.vertical-list-container .media-wrapper')).toHaveLength(3);
    expect(document.querySelector('[data-showcase-layout="vertical"]').classList.contains('active')).toBe(true);

    // initShowcaseContent was re-run by the re-render; bind again and switch back
    document.querySelector('[data-showcase-layout="gallery"]').click();
    await vi.waitFor(() => {
      expect(document.querySelector('.gallery-strip')).toBeTruthy();
    });
    expect(saveSetting).toHaveBeenLastCalledWith('showcase_layout', 'gallery');
    expect(document.querySelector('.vertical-list-container')).toBeNull();
  });

  it('keeps the collapsed indicator bar shared across layouts (toggle included)', async () => {
    const { renderShowcaseContent } = await import(SHOWCASE_MODULE);

    const html = renderShowcaseContent(IMAGES, [], PREVIEW_URL);
    const host = document.createElement('div');
    host.innerHTML = html;

    const bar = host.querySelector('.gallery-indicator-bar');
    expect(bar).toBeTruthy();
    expect(bar.querySelector('[data-showcase-layout="vertical"]')).toBeTruthy();
    expect(bar.querySelector('[data-showcase-layout="gallery"]')).toBeTruthy();
    // Vertical layout active in the collapsed bar too
    expect(bar.querySelector('[data-showcase-layout="vertical"]').classList.contains('active')).toBe(true);
  });

  it('initializes shared media handlers for every stacked item', async () => {
    const { initLazyLoading, initNsfwBlurHandlers, initMetadataPanelHandlers, initMediaControlHandlers } = await import(MEDIA_UTILS_MODULE);
    const { renderVerticalList, initVerticalList } = await import(VERTICAL_MODULE);

    document.body.innerHTML = `<div class="showcase-gallery showcase-vertical">${renderVerticalList(IMAGES, [])}</div>`;
    initVerticalList(document.querySelector('.showcase-vertical'), IMAGES, []);

    expect(initLazyLoading).toHaveBeenCalled();
    expect(initNsfwBlurHandlers).toHaveBeenCalled();
    expect(initMetadataPanelHandlers).toHaveBeenCalled();
    expect(initMediaControlHandlers).toHaveBeenCalled();
  });

  it('opens the full-size media viewer at the clicked item', async () => {
    const { openMediaViewer } = await import(MEDIA_VIEWER_MODULE);
    const { renderVerticalList, initVerticalList } = await import(VERTICAL_MODULE);

    document.body.innerHTML = `<div class="showcase-gallery showcase-vertical">${renderVerticalList(IMAGES, [])}</div>`;
    initVerticalList(document.querySelector('.showcase-vertical'), IMAGES, []);

    const wrappers = document.querySelectorAll('.vertical-list-container .media-wrapper');
    wrappers[1].querySelector('img').click();

    expect(openMediaViewer).toHaveBeenCalledTimes(1);
    const [items, index] = openMediaViewer.mock.calls[0];
    expect(index).toBe(1);
    expect(items).toHaveLength(3);
    expect(items[2].type).toBe('video');
  });
});
