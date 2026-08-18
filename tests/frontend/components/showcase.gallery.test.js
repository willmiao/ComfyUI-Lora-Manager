import { describe, it, beforeEach, afterEach, expect } from 'vitest';

const { SHOWCASE_MODULE, MEDIA_UTILS_MODULE, MEDIA_VIEWER_MODULE } = vi.hoisted(() => ({
  SHOWCASE_MODULE: new URL('../../../static/js/components/shared/showcase/ShowcaseView.js', import.meta.url).pathname,
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
}));

const PREVIEW_URL = '/loras_static/preview/abc.png';

const IMAGES = [
  { url: 'https://image.civitai.com/abc/111.jpeg', width: 512, height: 768, nsfwLevel: 0 },
  { url: 'https://image.civitai.com/abc/222.jpeg', width: 768, height: 512, nsfwLevel: 0 },
  { url: 'https://image.civitai.com/abc/333.mp4', width: 512, height: 512, nsfwLevel: 0 },
];

describe('Showcase gallery', () => {
  let state;

  beforeEach(async () => {
    Element.prototype.scrollIntoView = vi.fn();
    const stateModule = await import('../../../static/js/state/index.js');
    state = stateModule.state;
    state.settings.show_only_sfw = false;
    state.settings.blur_mature_content = false;
    state.global.settings.example_images_path = '/tmp/examples';
    document.body.innerHTML = '';
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('starts collapsed: slim indicator bar only, no remote examples rendered', async () => {
    const { renderShowcaseContent } = await import(SHOWCASE_MODULE);

    const html = renderShowcaseContent(IMAGES, [], PREVIEW_URL);
    const host = document.createElement('div');
    host.innerHTML = html;

    expect(host.querySelector('.showcase-gallery')).toBeTruthy();
    expect(host.querySelector('.gallery-indicator-bar')).toBeTruthy();
    // Collapsed bar carries the count and the local preview thumbnail
    expect(host.querySelector('#galleryShowBtn')?.textContent).toContain('3');
    expect(host.querySelector('.gallery-preview-thumb img')?.getAttribute('src')).toBe(PREVIEW_URL);
    expect(host.querySelector('#galleryImportBtn')).toBeTruthy();
    // No thumbnails / media wrappers → no remote fetches until expanded
    expect(host.querySelectorAll('.gallery-thumb')).toHaveLength(0);
    expect(host.querySelector('.media-wrapper')).toBeNull();
    // Import zone exists but stays collapsed
    const zone = host.querySelector('.gallery-import-zone');
    expect(zone?.classList.contains('hidden')).toBe(true);
  });

  it('expanded render shows toolbar, main viewer, thumbnails and nav controls', async () => {
    const { renderShowcaseContent } = await import(SHOWCASE_MODULE);

    const html = renderShowcaseContent(IMAGES, [], PREVIEW_URL, true);
    const host = document.createElement('div');
    host.innerHTML = html;

    expect(host.querySelector('.gallery-indicator-bar')).toBeNull();
    expect(host.querySelector('#galleryPosition')?.textContent).toBe('1 / 3');
    expect(host.querySelector('.main-media-container .media-wrapper')).toBeTruthy();
    expect(host.querySelectorAll('.gallery-thumb')).toHaveLength(3);
    expect(host.querySelector('.gallery-thumb.active')?.dataset.index).toBe('0');
    expect(host.querySelector('#galleryPrevBtn')).toBeTruthy();
    expect(host.querySelector('#galleryNextBtn')).toBeTruthy();
  });

  it('show/hide button toggles between indicator bar and gallery', async () => {
    const { renderShowcaseContent, initShowcaseContent } = await import(SHOWCASE_MODULE);

    document.body.innerHTML = `<div id="showcase-tab">${renderShowcaseContent(IMAGES, [], PREVIEW_URL)}</div>`;
    initShowcaseContent(document.querySelector('.showcase-gallery'));

    // Expand
    document.querySelector('#galleryShowBtn').click();
    expect(document.querySelectorAll('.gallery-thumb')).toHaveLength(3);
    expect(document.querySelector('.gallery-indicator-bar')).toBeNull();

    // Collapse back to the indicator bar
    document.querySelector('#galleryShowBtn').click();
    expect(document.querySelectorAll('.gallery-thumb')).toHaveLength(0);
    expect(document.querySelector('.gallery-indicator-bar')).toBeTruthy();
    expect(document.querySelector('.gallery-preview-thumb img')?.getAttribute('src')).toBe(PREVIEW_URL);
  });

  it('omits the import zone when the example images path is not configured', async () => {
    const { renderShowcaseContent } = await import(SHOWCASE_MODULE);
    state.global.settings.example_images_path = '';

    const html = renderShowcaseContent(IMAGES, [], PREVIEW_URL, true);
    const host = document.createElement('div');
    host.innerHTML = html;

    expect(host.querySelector('#galleryImportBtn')).toBeTruthy();
    expect(host.querySelector('.gallery-import-zone')).toBeNull();
  });

  it('filters NSFW examples and reports the hidden count', async () => {
    const { renderShowcaseContent } = await import(SHOWCASE_MODULE);
    state.settings.show_only_sfw = true;

    const images = [
      IMAGES[0],
      { url: 'https://image.civitai.com/abc/444.jpeg', width: 10, height: 10, nsfwLevel: 32 },
    ];
    const html = renderShowcaseContent(images, [], '', true);
    const host = document.createElement('div');
    host.innerHTML = html;

    expect(host.querySelectorAll('.gallery-thumb')).toHaveLength(1);
    expect(host.querySelector('.nsfw-filter-notification')).toBeTruthy();
    // Only one example left → no prev/next controls
    expect(host.querySelector('#galleryPrevBtn')).toBeNull();
  });

  it('renders the import interface when there are no examples', async () => {
    const { renderShowcaseContent } = await import(SHOWCASE_MODULE);

    const html = renderShowcaseContent([], [], PREVIEW_URL);
    const host = document.createElement('div');
    host.innerHTML = html;

    expect(host.querySelector('.example-import-area.empty')).toBeTruthy();
    expect(host.querySelector('#selectExampleFilesBtn')).toBeTruthy();
  });

  it('renders the setup guidance when the path is missing and there are no examples', async () => {
    const { renderShowcaseContent } = await import(SHOWCASE_MODULE);
    state.global.settings.example_images_path = '';

    const html = renderShowcaseContent([], []);
    const host = document.createElement('div');
    host.innerHTML = html;

    expect(host.querySelector('.import-container--needs-setup')).toBeTruthy();
    expect(host.querySelector('#openExampleSettingsBtn')).toBeTruthy();
  });

  it('switches the main display, position and active thumbnail when expanded', async () => {
    const { renderShowcaseContent, updateMainDisplay } = await import(SHOWCASE_MODULE);

    document.body.innerHTML = `<div id="showcase-tab">${renderShowcaseContent(IMAGES, [], PREVIEW_URL, true)}</div>`;

    updateMainDisplay(2);

    const activeThumb = document.querySelector('.gallery-thumb.active');
    expect(activeThumb?.dataset.index).toBe('2');
    expect(document.querySelector('#galleryPosition')?.textContent).toBe('3 / 3');
    const mainWrapper = document.querySelector('#mainMediaContainer .media-wrapper');
    expect(mainWrapper).toBeTruthy();
    // The third example is a video
    expect(mainWrapper.querySelector('video')).toBeTruthy();

    // Wraps around past the end
    updateMainDisplay(3);
    expect(document.querySelector('.gallery-thumb.active')?.dataset.index).toBe('0');
    expect(document.querySelector('#galleryPosition')?.textContent).toBe('1 / 3');
  });

  it('fits the main viewer to the active media aspect ratio', async () => {
    const { renderShowcaseContent, updateMainDisplay } = await import(SHOWCASE_MODULE);

    document.body.innerHTML = `<div id="showcase-tab">${renderShowcaseContent(IMAGES, [], PREVIEW_URL, true)}</div>`;

    // First image is portrait 512x768 → aspect 0.667
    const container = document.getElementById('mainMediaContainer');
    expect(container.style.getPropertyValue('--media-aspect')).toBe(String(512 / 768));

    // Second image is landscape 768x512 → aspect 1.5
    updateMainDisplay(1);
    expect(container.style.getPropertyValue('--media-aspect')).toBe('1.5');
  });

  it('ignores main-display updates while collapsed', async () => {
    const { renderShowcaseContent, updateMainDisplay } = await import(SHOWCASE_MODULE);

    document.body.innerHTML = `<div id="showcase-tab">${renderShowcaseContent(IMAGES, [], PREVIEW_URL)}</div>`;

    updateMainDisplay(1);

    // Still collapsed: indicator bar untouched, no gallery rendered
    expect(document.querySelector('.gallery-indicator-bar')).toBeTruthy();
    expect(document.querySelectorAll('.gallery-thumb')).toHaveLength(0);
  });
});
