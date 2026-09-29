import { describe, it, beforeEach, afterEach, expect, vi } from 'vitest';

const { UTILS_MODULE, APP_MODULE, API_MODULE, BASE_PATH_MODULE } = vi.hoisted(() => ({
  UTILS_MODULE: new URL('../../../web/comfyui/loras_widget_utils.js', import.meta.url).pathname,
  APP_MODULE: new URL('../../../scripts/app.js', import.meta.url).pathname,
  API_MODULE: new URL('../../../scripts/api.js', import.meta.url).pathname,
  BASE_PATH_MODULE: new URL('../../../web/comfyui/base_path.js', import.meta.url).pathname,
}));

const toastAdd = vi.fn();
const graphToPrompt = vi.fn();

vi.mock(APP_MODULE, () => ({
  app: {
    graphToPrompt,
    extensionManager: { toast: { add: toastAdd } },
  },
}));

vi.mock(API_MODULE, () => ({
  api: { fetchApi: vi.fn() },
}));

vi.mock(BASE_PATH_MODULE, () => ({
  lmUrl: (path) => `/lm${path}`,
}));

async function runSave(options, responseBody) {
  let captured = null;
  globalThis.fetch = vi.fn(async (url, init) => {
    captured = { url, init };
    return { json: async () => responseBody };
  });

  const { saveRecipeDirectly } = await import(UTILS_MODULE);
  await saveRecipeDirectly(options);
  return captured;
}

describe('saveRecipeDirectly', () => {
  beforeEach(() => {
    graphToPrompt.mockResolvedValue({
      workflow: { nodes: [{ id: 1 }], last_node_id: 1 },
      output: { 1: { class_type: 'KSampler' } },
    });
  });

  afterEach(() => {
    delete globalThis.fetch;
    vi.clearAllMocks();
  });

  it('posts no workflow by default', async () => {
    const captured = await runSave(undefined, { success: true, has_workflow: false });

    expect(captured.init.body).toBe('{}');
    expect(JSON.parse(captured.init.body)).not.toHaveProperty('workflow');
  });

  it('embeds the UI-format graph when asked', async () => {
    const captured = await runSave(
      { embedWorkflow: true },
      { success: true, has_workflow: true }
    );

    const body = JSON.parse(captured.init.body);
    expect(body.workflow).toEqual({ nodes: [{ id: 1 }], last_node_id: 1 });
    expect(captured.init.headers['Content-Type']).toBe('application/json');
  });

  it('reports a skipped oversized workflow as a warning', async () => {
    await runSave(
      { embedWorkflow: true },
      { success: true, has_workflow: false, workflow_skipped: 'too_large' }
    );

    const lastToast = toastAdd.mock.calls.at(-1)[0];
    expect(lastToast.severity).toBe('warn');
    expect(lastToast.summary).toBe('Recipe Saved without Workflow');
    expect(lastToast.detail).toContain('too large');
  });

  it('reports a successful embed distinctly from a plain save', async () => {
    await runSave(
      { embedWorkflow: true },
      { success: true, has_workflow: true }
    );

    const lastToast = toastAdd.mock.calls.at(-1)[0];
    expect(lastToast.summary).toBe('Recipe Saved with Workflow');
  });
});
