import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const showToast = vi.fn();
const trackJob = vi.fn();

vi.mock('../../../static/js/utils/uiHelpers.js', () => ({
  showToast: (...args) => showToast(...args),
}));
vi.mock('../../../static/js/utils/i18nHelpers.js', () => ({
  translate: (_key, _params, fallback) => fallback,
}));
vi.mock('../../../static/js/utils/nvmeProgress.js', () => ({
  trackJob: (...args) => trackJob(...args),
  trackSync: (_op, _name, work) => work,
}));

let pinManyNvme;

/** Requests to the nvme_cache API as [endpoint, body], in order. */
let requests;

/**
 * Fake nvme_cache server. `statuses` maps absolute path -> {rel, status} (or
 * null for paths outside the cache roots); `pinResponses` maps rel -> a list
 * of {status, data} answers to successive /pin calls.
 */
function mockServer(statuses, pinResponses = {}) {
  requests = [];
  vi.stubGlobal('fetch', vi.fn(async (url, options) => {
    const endpoint = url.replace('/nvme_cache/api', '');
    const body = JSON.parse(options.body);
    requests.push([endpoint, body]);
    let status = 200;
    let data = { ok: true };
    if (endpoint === '/resolve') {
      data = { results: Object.fromEntries(body.paths.map((p) => [p, statuses[p] ?? null])) };
    } else if (endpoint === '/pin') {
      const answer = pinResponses[body.rel]?.shift();
      if (answer) ({ status, data } = answer);
    }
    return { status, ok: status < 400, json: async () => data };
  }));
}

const pinCalls = () => requests.filter(([endpoint]) => endpoint === '/pin');

describe('pinManyNvme', () => {
  beforeEach(async () => {
    document.body.innerHTML = '';
    showToast.mockReset();
    trackJob.mockReset();
    vi.stubGlobal('requestAnimationFrame', (cb) => setTimeout(cb, 0));
    vi.stubGlobal('confirm', vi.fn(() => true));
    // Statuses are memoised at module level; a fresh copy keeps tests apart.
    vi.resetModules();
    ({ pinManyNvme } = await import('../../../static/js/utils/nvmeCache.js'));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('pins cached models first, then promotes HDD models, excluding the whole batch', async () => {
    mockServer(
      {
        '/m/hdd.safetensors': { rel: 'loras/hdd.safetensors', status: 'hdd' },
        '/m/cached.safetensors': { rel: 'loras/cached.safetensors', status: 'nvme' },
        '/m/pinned.safetensors': { rel: 'loras/pinned.safetensors', status: 'pinned' },
        '/m/elsewhere.safetensors': null,
      },
      { 'loras/hdd.safetensors': [{ status: 200, data: { job_id: 'job-1', queued: true } }] }
    );
    trackJob.mockResolvedValue(true);

    await pinManyNvme([
      '/m/hdd.safetensors',
      '/m/cached.safetensors',
      '/m/pinned.safetensors',
      '/m/elsewhere.safetensors',
    ]);

    const exclude = ['loras/cached.safetensors', 'loras/hdd.safetensors'];
    expect(pinCalls()).toEqual([
      ['/pin', { rel: 'loras/cached.safetensors', exclude }],
      ['/pin', { rel: 'loras/hdd.safetensors', exclude }],
    ]);
    expect(trackJob).toHaveBeenCalledWith('job-1', 'Pinning', 'hdd.safetensors');
    expect(showToast).toHaveBeenCalledWith(
      'Pinned 2 to NVMe, 1 already pinned, 1 not pinnable (not in the cache roots, missing, or not adopted)',
      {}, 'success'
    );
  });

  it('asks before evicting, and keeps going after a declined eviction', async () => {
    const eviction = {
      status: 409,
      data: { eviction_required: true, to_evict: ['loras/old.safetensors'], total_freed: 10, promotion_size: 5 },
    };
    mockServer(
      {
        '/m/a.safetensors': { rel: 'loras/a.safetensors', status: 'hdd' },
        '/m/b.safetensors': { rel: 'loras/b.safetensors', status: 'hdd' },
      },
      {
        'loras/a.safetensors': [eviction],
        'loras/b.safetensors': [eviction, { status: 200, data: { job_id: 'job-b' } }],
      }
    );
    window.confirm.mockReturnValueOnce(false).mockReturnValueOnce(true);
    trackJob.mockResolvedValue(true);

    await pinManyNvme(['/m/a.safetensors', '/m/b.safetensors']);

    const exclude = ['loras/a.safetensors', 'loras/b.safetensors'];
    expect(pinCalls()).toEqual([
      ['/pin', { rel: 'loras/a.safetensors', exclude }],
      ['/pin', { rel: 'loras/b.safetensors', exclude }],
      ['/pin', { rel: 'loras/b.safetensors', exclude, allow_evict: ['loras/old.safetensors'] }],
    ]);
    expect(window.confirm).toHaveBeenCalledTimes(2);
    expect(showToast).toHaveBeenCalledWith(
      'Pinned 1 to NVMe, 1 skipped (eviction declined)', {}, 'success'
    );
  });

  it('reports failed copies without stopping the batch', async () => {
    mockServer(
      {
        '/m/a.safetensors': { rel: 'loras/a.safetensors', status: 'hdd' },
        '/m/b.safetensors': { rel: 'loras/b.safetensors', status: 'hdd' },
      },
      {
        'loras/a.safetensors': [{ status: 200, data: { job_id: 'job-a' } }],
        'loras/b.safetensors': [{ status: 200, data: { job_id: 'job-b' } }],
      }
    );
    trackJob.mockResolvedValueOnce(false).mockResolvedValueOnce(true);

    await pinManyNvme(['/m/a.safetensors', '/m/b.safetensors']);

    expect(trackJob).toHaveBeenCalledTimes(2);
    expect(showToast).toHaveBeenCalledWith('Pinned 1 to NVMe, 1 failed', {}, 'warning');
  });

  it('refreshes the icons of cards on screen', async () => {
    document.body.innerHTML = `
      <div class="model-card" data-filepath="/m/cached.safetensors">
        <i class="nvme-promote"></i><i class="nvme-pin"></i>
      </div>`;
    mockServer({ '/m/cached.safetensors': { rel: 'loras/cached.safetensors', status: 'nvme' } });

    await pinManyNvme(['/m/cached.safetensors']);
    // The card re-reads its status after the pin, through a fresh lookup.
    await new Promise((resolve) => setTimeout(resolve, 10));

    expect(requests.filter(([endpoint]) => endpoint === '/resolve')).toHaveLength(2);
  });
});
