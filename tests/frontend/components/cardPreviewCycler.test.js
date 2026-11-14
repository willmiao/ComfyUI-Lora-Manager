import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const {
  CYCLER_MODULE,
  STATE_MODULE,
  API_FACTORY_MODULE,
  CONSTANTS_MODULE,
} = vi.hoisted(() => ({
  CYCLER_MODULE: new URL('../../../static/js/components/shared/CardPreviewCycler.js', import.meta.url).pathname,
  STATE_MODULE: new URL('../../../static/js/state/index.js', import.meta.url).pathname,
  API_FACTORY_MODULE: new URL('../../../static/js/api/modelApiFactory.js', import.meta.url).pathname,
  CONSTANTS_MODULE: new URL('../../../static/js/utils/constants.js', import.meta.url).pathname,
}));

const fetchModelMetadataMock = vi.fn();
// Local example files come from /api/lm/example-image-files, not from the
// model API client, so the cycler calls global fetch directly.
const fetchLocalFilesMock = vi.fn();

const stateMock = {
  settings: {
    show_only_sfw: false,
  },
  global: {
    settings: {
      card_preview_cycle: true,
      card_preview_cycle_interval: 2,
    },
  },
};

vi.mock(STATE_MODULE, () => ({
  state: stateMock,
}));

vi.mock(API_FACTORY_MODULE, () => ({
  getModelApiClient: vi.fn(() => ({ fetchModelMetadata: fetchModelMetadataMock })),
}));

vi.mock(CONSTANTS_MODULE, () => ({
  NSFW_LEVELS: { R: 4, X: 8, XXX: 16 },
}));

class InstantImage {
  set src(value) {
    this._src = value;
    setTimeout(() => this.onload?.(), 0);
  }
  get src() {
    return this._src;
  }
}

const MODEL = { file_path: '/models/test_lora.safetensors' };

// fetchModelMetadata resolves to the civitai metadata section itself,
// matching what ModelModal wraps as `civitai: fullMetadata`.
const METADATA = {
  images: [
    { url: 'https://img/1.jpg', nsfwLevel: 1 },
    { url: 'https://img/2.jpg', nsfwLevel: 1 },
    { url: 'https://vid/clip.mp4', type: 'video', nsfwLevel: 1 },
    { url: 'https://img/nsfw.jpg', nsfwLevel: 8 },
  ],
  customImages: [
    { url: 'https://img/custom.jpg', nsfwLevel: 1 },
  ],
};

function createCard() {
  const card = document.createElement('div');
  card.className = 'model-card';
  card.innerHTML = '<div class="card-preview"><img src="/anchor.jpg"></div>';
  document.body.appendChild(card);
  return card;
}

// Mirrors the real card structure: header and footer are children of
// .card-preview (see ModelCard.js), so they share its hover region.
function createCardWithChrome() {
  const card = document.createElement('div');
  card.className = 'model-card';
  card.innerHTML = '<div class="card-preview"><img src="/anchor.jpg">' +
    '<div class="card-header"><div class="card-actions"><i class="action-icon"></i></div></div>' +
    '<div class="card-footer"><span class="model-name">name</span></div></div>';
  document.body.appendChild(card);
  return card;
}

async function advance(ms) {
  await vi.advanceTimersByTimeAsync(ms);
}

describe('CardPreviewCycler', () => {
  let attachCardPreviewCycler;
  let resetCardPreviewCycleCache;

  beforeEach(async () => {
    vi.useFakeTimers();
    vi.stubGlobal('Image', InstantImage);
    vi.stubGlobal('fetch', fetchLocalFilesMock);
    fetchModelMetadataMock.mockReset();
    fetchModelMetadataMock.mockResolvedValue(METADATA);
    fetchLocalFilesMock.mockReset();
    fetchLocalFilesMock.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, files: [] }),
    });
    stateMock.settings.show_only_sfw = false;
    stateMock.global.settings.card_preview_cycle = true;
    stateMock.global.settings.card_preview_cycle_interval = 2;
    document.body.innerHTML = '';
    ({ attachCardPreviewCycler, resetCardPreviewCycleCache } = await import(CYCLER_MODULE));
    resetCardPreviewCycleCache();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  function hover(card) {
    const preview = card.querySelector('.card-preview');
    preview.dispatchEvent(new Event('mouseover', { bubbles: true }));
    return preview;
  }

  it('starts loading on hover and shows the first frame when the mode activates', async () => {
    const card = createCard();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    // Prefetch begins at hover time, ahead of the visual intent delay.
    expect(fetchModelMetadataMock).toHaveBeenCalledWith(MODEL.file_path);
    expect(card.classList.contains('cycling')).toBe(false);

    // Ordinary hover interactions (action icons, tooltips) keep working:
    // the chrome stays visible until the mode delay elapses.
    await advance(400);
    expect(card.classList.contains('cycling')).toBe(false);

    await advance(400);
    // Cycling mode hides the card chrome and fades the first frame in
    // as soon as it is loaded, without waiting for a full interval.
    expect(card.classList.contains('cycling')).toBe(true);

    await advance(1);
    const buffers = preview.querySelectorAll('.card-preview-cycle-img');
    expect(buffers).toHaveLength(2);
    const visible = preview.querySelector('.card-preview-cycle-img.visible');
    expect(visible).not.toBeNull();
    // The first example usually doubles as the preview; cycling starts from
    // the second one.
    expect(visible.src).toBe('https://img/2.jpg');

    // Anchor preview is untouched underneath.
    const anchor = preview.querySelector('img:not(.card-preview-cycle-img)');
    expect(anchor.src).toContain('/anchor.jpg');
  });

  it('keeps the cover image in the rotation, just not as the first frame', async () => {
    const card = createCard();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    // Cycle order for [1, 2, nsfw, custom] is 2 → nsfw → custom → 1 (wrap).
    await advance(800);
    await advance(1);
    expect(preview.querySelector('.card-preview-cycle-img.visible').src).toBe('https://img/2.jpg');

    await advance(9000);
    await advance(1);
    const shownUrls = [...preview.querySelectorAll('.card-preview-cycle-img')].map(img => img.src);
    expect(shownUrls).toContain('https://img/1.jpg');
  });

  it('advances to the next image on each interval and skips video entries', async () => {
    const card = createCard();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    await advance(800);
    await advance(1);
    await advance(3000);
    await advance(1);

    const shownUrls = [...preview.querySelectorAll('.card-preview-cycle-img')].map(img => img.src);
    expect(shownUrls).toContain('https://img/2.jpg');
    expect(shownUrls.some(url => url.includes('clip.mp4'))).toBe(false);
  });

  it('restores the anchor preview on mouseleave', async () => {
    const card = createCard();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    await advance(800);
    await advance(0);

    preview.dispatchEvent(new Event('mouseleave'));
    await advance(500);

    expect(preview.querySelectorAll('.card-preview-cycle-img')).toHaveLength(0);
    expect(card.classList.contains('cycling')).toBe(false);
    const anchor = preview.querySelector('img');
    expect(anchor.src).toContain('/anchor.jpg');
  });

  it('never arms the timer while the pointer is over the card chrome', async () => {
    const card = createCardWithChrome();
    attachCardPreviewCycler(card, MODEL);
    card.querySelector('.card-header').dispatchEvent(new Event('mouseover', { bubbles: true }));

    await advance(5000);
    expect(card.classList.contains('cycling')).toBe(false);
    expect(card.querySelectorAll('.card-preview-cycle-img')).toHaveLength(0);
  });

  it('disarms the timer in the chrome and re-arms it back on the preview', async () => {
    const card = createCardWithChrome();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    // Half the delay on the bare preview, then move onto the footer: the
    // pending activation is cancelled, not postponed.
    await advance(400);
    card.querySelector('.card-footer').dispatchEvent(new Event('mouseover', { bubbles: true }));
    await advance(1000);
    expect(card.classList.contains('cycling')).toBe(false);

    // Back on the bare preview the full delay applies again.
    preview.querySelector('img').dispatchEvent(new Event('mouseover', { bubbles: true }));
    await advance(799);
    expect(card.classList.contains('cycling')).toBe(false);
    await advance(2);
    expect(card.classList.contains('cycling')).toBe(true);
  });

  it('does not start when the setting is disabled', async () => {
    stateMock.global.settings.card_preview_cycle = false;
    const card = createCard();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    await advance(5000);
    expect(fetchModelMetadataMock).not.toHaveBeenCalled();
    expect(preview.querySelectorAll('.card-preview-cycle-img')).toHaveLength(0);
  });

  it('does not start while the preview is NSFW-blurred', async () => {
    const card = createCard();
    card.querySelector('.card-preview').classList.add('blurred');
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    await advance(5000);
    expect(fetchModelMetadataMock).not.toHaveBeenCalled();
    expect(preview.querySelectorAll('.card-preview-cycle-img')).toHaveLength(0);
  });

  it('respects prefers-reduced-motion', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })));
    const card = createCard();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    await advance(5000);
    expect(fetchModelMetadataMock).not.toHaveBeenCalled();
    expect(preview.querySelectorAll('.card-preview-cycle-img')).toHaveLength(0);
  });

  it('filters NSFW example images when show_only_sfw is on', async () => {
    stateMock.settings.show_only_sfw = true;
    const card = createCard();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    await advance(800);
    // Cycle through all remaining frames.
    await advance(9000);

    const buffers = preview.querySelectorAll('.card-preview-cycle-img');
    const shownUrls = [...buffers].map(img => img.src);
    expect(shownUrls.some(url => url.includes('nsfw.jpg'))).toBe(false);
  });

  it('uses the configured cycle interval', async () => {
    stateMock.global.settings.card_preview_cycle_interval = 2.5;
    const card = createCard();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    await advance(800);
    await advance(1);
    expect(preview.querySelector('.card-preview-cycle-img.visible').src).toBe('https://img/2.jpg');

    // 2.5s interval: nothing new after 2s, second frame after 2.5s.
    await advance(2000);
    await advance(1);
    expect(preview.querySelector('.card-preview-cycle-img.visible').src).toBe('https://img/2.jpg');

    await advance(500);
    await advance(1);
    expect(preview.querySelector('.card-preview-cycle-img.visible').src).toBe('https://img/nsfw.jpg');
  });

  it('clamps intervals outside the slider bounds', async () => {
    // Values from the old 8s option (or manual settings.json edits) must not
    // make cycling slower than the slider can express.
    stateMock.global.settings.card_preview_cycle_interval = 8;
    const card = createCard();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    await advance(800);
    await advance(1);
    expect(preview.querySelector('.card-preview-cycle-img.visible').src).toBe('https://img/2.jpg');

    // Clamped to 3s: still the first frame after 2.5s, next one at 3s.
    await advance(2500);
    await advance(1);
    expect(preview.querySelector('.card-preview-cycle-img.visible').src).toBe('https://img/2.jpg');

    await advance(500);
    await advance(1);
    expect(preview.querySelector('.card-preview-cycle-img.visible').src).toBe('https://img/nsfw.jpg');
  });

  it('clamps sub-half-second intervals up to the slider minimum', async () => {
    stateMock.global.settings.card_preview_cycle_interval = 0.1;
    const card = createCard();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    await advance(800);
    await advance(1);
    expect(preview.querySelector('.card-preview-cycle-img.visible').src).toBe('https://img/2.jpg');

    // Clamped to 0.5s rather than switching every 100ms. 1ms has already
    // elapsed since activation, so 498ms stays under the 500ms interval.
    await advance(498);
    expect(preview.querySelector('.card-preview-cycle-img.visible').src).toBe('https://img/2.jpg');

    await advance(2);
    await advance(1);
    expect(preview.querySelector('.card-preview-cycle-img.visible').src).toBe('https://img/nsfw.jpg');
  });

  it('rewrites CivitAI example URLs to card-sized thumbnails', async () => {
    fetchModelMetadataMock.mockResolvedValue({
      images: [
        { url: 'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/cover/original=true/11111.jpeg', nsfwLevel: 1 },
        { url: 'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/original=true/12345.jpeg', nsfwLevel: 1 },
      ],
    });
    const card = createCard();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    await advance(800);
    await advance(1);

    const visible = preview.querySelector('.card-preview-cycle-img.visible');
    expect(visible.src).toContain('/width=450,optimized=true/12345.jpeg');
  });

  it('does not cycle when the only example is the preview itself', async () => {
    fetchModelMetadataMock.mockResolvedValue({
      images: [{ url: 'https://img/cover.jpg', nsfwLevel: 1 }],
    });
    const card = createCard();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    await advance(5000);
    expect(card.classList.contains('cycling')).toBe(false);
    expect(preview.querySelectorAll('.card-preview-cycle-img')).toHaveLength(0);
  });

  it('caches metadata per model across hovers', async () => {
    const card = createCard();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    await advance(800);
    preview.dispatchEvent(new Event('mouseleave'));
    await advance(500);
    hover(card);
    await advance(800);

    expect(fetchModelMetadataMock).toHaveBeenCalledTimes(1);
  });

  it('does not cycle a model without example images', async () => {
    fetchModelMetadataMock.mockResolvedValue({ images: [] });
    const card = createCard();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    await advance(5000);
    expect(preview.querySelectorAll('.card-preview-cycle-img')).toHaveLength(0);
  });

  it('cycles example images imported from disk whose metadata urls are empty', async () => {
    const model = { ...MODEL, sha256: 'hash123', preview_url: '/anchor.jpg' };
    fetchModelMetadataMock.mockResolvedValue({
      customImages: [
        { id: 'a1', url: '', nsfwLevel: 1 },
        { id: 'b2', url: '', nsfwLevel: 1 },
        // Locally imported video: paired file is skipped like remote videos.
        { id: 'v3', url: '', type: 'video', nsfwLevel: 1 },
      ],
    });
    fetchLocalFilesMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        files: [
          { name: 'custom_a1.png', path: '/example_images_static/m/custom_a1.png', is_video: false },
          { name: 'custom_b2.png', path: '/example_images_static/m/custom_b2.png', is_video: false },
          { name: 'custom_v3.mp4', path: '/example_images_static/m/custom_v3.mp4', is_video: true },
        ],
      }),
    });

    const card = createCard();
    attachCardPreviewCycler(card, model);
    const preview = hover(card);

    // The fixed preview is not part of the local-only rotation, so the first
    // frame is shown immediately instead of being skipped as the "cover".
    await advance(800);
    await advance(1);
    expect(preview.querySelector('.card-preview-cycle-img.visible').src)
      .toContain('/example_images_static/m/custom_a1.png');

    await advance(2000);
    await advance(1);
    expect(preview.querySelector('.card-preview-cycle-img.visible').src)
      .toContain('/example_images_static/m/custom_b2.png');

    // The local video never enters the rotation.
    const shownUrls = [...preview.querySelectorAll('.card-preview-cycle-img')].map(img => img.src);
    expect(shownUrls.some(url => url.includes('custom_v3.mp4'))).toBe(false);

    // Files are looked up by the model hash.
    expect(fetchLocalFilesMock).toHaveBeenCalledWith(
      expect.stringContaining('model_hash=hash123')
    );
  });

  it('starts after the fixed preview when it is the first local example', async () => {
    const model = {
      ...MODEL,
      sha256: 'hash123',
      preview_url: '/example_images_static/m/custom_a1.png',
    };
    fetchModelMetadataMock.mockResolvedValue({
      customImages: [
        { id: 'a1', url: '', nsfwLevel: 1 },
        { id: 'b2', url: '', nsfwLevel: 1 },
      ],
    });
    fetchLocalFilesMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        files: [
          { name: 'custom_a1.png', path: '/example_images_static/m/custom_a1.png', is_video: false },
          { name: 'custom_b2.png', path: '/example_images_static/m/custom_b2.png', is_video: false },
        ],
      }),
    });

    const card = createCard();
    attachCardPreviewCycler(card, model);
    const preview = hover(card);

    await advance(800);
    await advance(1);
    expect(preview.querySelector('.card-preview-cycle-img.visible').src)
      .toContain('/example_images_static/m/custom_b2.png');
  });

  it('shortens the crossfade when the cycle interval is rapid', async () => {
    stateMock.global.settings.card_preview_cycle_interval = 0.5;
    const card = createCard();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    await advance(800);
    await advance(1);

    const buffers = preview.querySelectorAll('.card-preview-cycle-img');
    expect(buffers).toHaveLength(2);
    buffers.forEach(img => expect(img.style.transitionDuration).toBe('125ms'));
  });

  it('keeps the full crossfade for slow intervals', async () => {
    stateMock.global.settings.card_preview_cycle_interval = 3;
    const card = createCard();
    attachCardPreviewCycler(card, MODEL);
    const preview = hover(card);

    await advance(800);
    await advance(1);

    const buffers = preview.querySelectorAll('.card-preview-cycle-img');
    buffers.forEach(img => expect(img.style.transitionDuration).toBe('400ms'));
  });
});
