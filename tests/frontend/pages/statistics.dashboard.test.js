import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';
import { renderTemplate, resetDom } from '../utils/domFixtures.js';

const { CORE_MODULE, UI_HELPERS_MODULE, STATISTICS_MODULE } = vi.hoisted(() => ({
  CORE_MODULE: new URL('../../../static/js/core.js', import.meta.url).pathname,
  UI_HELPERS_MODULE: new URL('../../../static/js/utils/uiHelpers.js', import.meta.url).pathname,
  STATISTICS_MODULE: new URL('../../../static/js/statistics.js', import.meta.url).pathname,
}));

const appCoreInitializeMock = vi.fn();
const showToastMock = vi.fn();

vi.mock(CORE_MODULE, () => ({
  appCore: {
    initialize: appCoreInitializeMock,
  },
}));

vi.mock(UI_HELPERS_MODULE, () => ({
  showToast: showToastMock,
}));

describe('Statistics dashboard rendering', () => {
  beforeEach(() => {
    resetDom();
    appCoreInitializeMock.mockResolvedValue();
    showToastMock.mockReset();
    globalThis.Chart = undefined;
  });

  afterEach(() => {
    delete window.statsManager;
  });

  it('hydrates dashboard panels with fetched data and wires tab interactions', async () => {
    renderTemplate('statistics.html');

    const dataset = {
      '/api/lm/stats/collection-overview': {
        data: {
          total_models: 4,
          total_size: 4096,
          total_generations: 200,
          lora_count: 2,
          checkpoint_count: 1,
          embedding_count: 1,
          unused_loras: 1,
          unused_checkpoints: 0,
          unused_embeddings: 0,
          lora_size: 2048,
          checkpoint_size: 1024,
          embedding_size: 1024,
        },
      },
      '/api/lm/stats/usage-analytics': {
        data: {
          top_loras: [
            { name: 'Lora A', base_model: 'SDXL', folder: 'loras', usage_count: 10 },
          ],
          top_checkpoints: [
            { name: 'Checkpoint A', base_model: 'SDXL', folder: 'checkpoints', usage_count: 5 },
          ],
          top_embeddings: [
            { name: 'Embedding A', base_model: 'SDXL', folder: 'embeddings', usage_count: 7 },
          ],
          usage_timeline: [
            { date: '2024-01-01', lora_usage: 5, checkpoint_usage: 3, embedding_usage: 2 },
          ],
        },
      },
      '/api/lm/stats/base-model-distribution': {
        data: {
          loras: { SDXL: 2 },
          checkpoints: { SDXL: 1 },
          embeddings: { SDXL: 1 },
        },
      },
      '/api/lm/stats/tag-analytics': {
        data: {
          top_tags: [
            { tag: 'anime', count: 5 },
            { tag: 'photo', count: 3 },
          ],
          total_unique_tags: 2,
        },
      },
      '/api/lm/stats/storage-analytics': {
        data: {
          loras: [
            { name: 'Lora A', base_model: 'SDXL', size: 2048, usage_count: 10 },
          ],
          checkpoints: [
            { name: 'Checkpoint A', base_model: 'SDXL', size: 1024, usage_count: 5 },
          ],
          embeddings: [],
        },
      },
      '/api/lm/stats/insights': {
        data: {
          insights: [
            {
              type: 'info',
              title: 'Balance usage',
              description: 'Redistribute usage across models.',
              suggestion: 'Try lesser-used checkpoints.',
            },
          ],
        },
      },
    };

    const { StatisticsManager } = await import(STATISTICS_MODULE);
    const manager = new StatisticsManager();
    const refreshSpy = vi.spyOn(manager, 'refreshChartsInPanel');
    vi.spyOn(manager, 'fetchData').mockImplementation((endpoint) => Promise.resolve(dataset[endpoint]));

    await manager.initialize();

    expect(manager.initialized).toBe(true);
    expect(document.querySelectorAll('.metric-card').length).toBeGreaterThan(0);
    expect(document.querySelector('#topLorasList .model-item')).not.toBeNull();
    expect(document.querySelector('#tagCloud').textContent).toContain('anime');
    expect(document.querySelector('#insightsList .insight-card')).not.toBeNull();

    const usageButton = document.querySelector('.tab-button[data-tab="usage"]');
    usageButton.click();

    expect(refreshSpy).toHaveBeenCalledWith('usage');
    expect(document.getElementById('usage-panel').classList.contains('active')).toBe(true);
    expect(document.querySelector('.tab-button.active').dataset.tab).toBe('usage');
  });

  it('surfaces an error toast when statistics data fails to load', async () => {
    const { StatisticsManager } = await import(STATISTICS_MODULE);
    const manager = new StatisticsManager();
    vi.spyOn(manager, 'fetchData').mockRejectedValue(new Error('unavailable'));

    await manager.loadAllData();

    expect(showToastMock).toHaveBeenCalledWith('toast.general.statisticsLoadFailed', {}, 'error');
  });
});
