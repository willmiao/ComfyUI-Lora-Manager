import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const {
  APP_MODULE,
  DEMO_APP_MODULE,
  API_MODULE,
  STYLES_MODULE,
  DEMO_MODULE,
  REGISTRY_MODULE,
  LOADER_MODULE,
  appMock,
  apiMock,
  registeredExtensions,
} = vi.hoisted(() => {
  const registeredExtensions = [];
  const appMock = {
    graph: null,
    registerExtension: (extension) => registeredExtensions.push(extension),
  };
  const apiMock = {
    clientId: "demo-test-client",
    initialClientId: null,
    addEventListener: vi.fn(),
  };
  return {
    APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
    DEMO_APP_MODULE: new URL("../../../examples/scripts/app.js", import.meta.url).pathname,
    API_MODULE: new URL("../../../scripts/api.js", import.meta.url).pathname,
    STYLES_MODULE: new URL("../../../web/comfyui/lm_styles_loader.js", import.meta.url).pathname,
    DEMO_MODULE: new URL(
      "../../../examples/lora-node-adapter-demo/web/lora_node_adapter_demo.js",
      import.meta.url
    ).pathname,
    REGISTRY_MODULE: new URL("../../../web/comfyui/workflow_registry.js", import.meta.url).pathname,
    LOADER_MODULE: new URL("../../../web/comfyui/lora_loader.js", import.meta.url).pathname,
    appMock,
    apiMock,
    registeredExtensions,
  };
});

vi.mock(APP_MODULE, () => ({ app: appMock }));
vi.mock(DEMO_APP_MODULE, () => ({ app: appMock }));
vi.mock(API_MODULE, () => ({ api: apiMock }));
vi.mock(STYLES_MODULE, () => ({ ensureLmStyles: vi.fn() }));

function createDemoGraph() {
  const textWidget = {
    name: "text",
    type: "customtext",
    value: "",
    callback: null,
  };
  const loader = {
    id: 1,
    comfyClass: "LoRA Adapter Demo Loader",
    title: "LoRA Adapter Demo Loader",
    mode: 0,
    properties: {},
    widgets: [textWidget],
    inputs: [],
    outputs: [],
    setDirtyCanvas: vi.fn(),
  };
  const toggle = {
    id: 2,
    comfyClass: "TriggerWord Toggle (LoraManager)",
    title: "TriggerWord Toggle",
    mode: 0,
    properties: {},
    widgets: [],
    inputs: [],
    outputs: [],
  };
  const graph = {
    id: "root",
    _nodes: [loader, toggle],
    _subgraphs: new Map(),
    links: new Map([[10, { origin_id: 1, target_id: 2 }]]),
    getNodeById(id) {
      return [loader, toggle].find((node) => node.id === id) ?? null;
    },
    events: { addEventListener: vi.fn() },
  };
  loader.graph = graph;
  toggle.graph = graph;
  return { graph, loader, toggle, textWidget };
}

describe("LoRA node adapter demo integration", () => {
  let fetchMock;
  let registryExtension;
  let loaderExtension;
  let demoExtension;

  beforeEach(async () => {
    vi.resetModules();
    delete globalThis.__lmLoraNodeAdapterRegistry;
    registeredExtensions.length = 0;
    apiMock.addEventListener.mockClear();
    fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);

    await import(REGISTRY_MODULE);
    await import(LOADER_MODULE);
    await import(DEMO_MODULE);
    registryExtension = registeredExtensions.find(
      (extension) => extension.name === "LoraManager.WorkflowRegistry"
    );
    loaderExtension = registeredExtensions.find(
      (extension) => extension.name === "LoraManager.LoraLoader"
    );
    demoExtension = registeredExtensions.find(
      (extension) => extension.name === "ThirdPartyExample.LoraNodeAdapterDemo"
    );
  });

  afterEach(() => {
    delete globalThis.__lmLoraNodeAdapterRegistry;
    vi.unstubAllGlobals();
  });

  async function waitForTriggerNames(expectedCallCount) {
    await vi.waitFor(() => {
      const requests = fetchMock.mock.calls.filter(
        ([url]) => url === "/api/lm/loras/get_trigger_words"
      );
      expect(requests.length).toBeGreaterThanOrEqual(expectedCallCount);
    });
    return fetchMock.mock.calls
      .filter(([url]) => url === "/api/lm/loras/get_trigger_words")
      .map(([, options]) => JSON.parse(options.body).lora_names);
  }

  it("uses the real adapter API for discovery, updates, and trigger synchronization", async () => {
    const { graph, loader, textWidget } = createDemoGraph();
    appMock.graph = graph;
    registryExtension.setup();
    await demoExtension.setup();
    await demoExtension.nodeCreated(loader);

    await vi.waitFor(() => {
      const registration = fetchMock.mock.calls.find(
        ([url]) => url === "/api/lm/register-nodes"
      );
      expect(registration).toBeDefined();
      const body = JSON.parse(registration[1].body);
      expect(body.nodes[0].comfy_class).toBe("LoRA Adapter Demo Loader");
      expect(body.nodes[0].capabilities.supports_lora).toBe(true);
    });
    expect(loader.serialize_widgets).toBe(true);

    loader.outputs = [{ links: [10] }];
    loaderExtension.handleLoraCodeUpdate({
      node_id: 1,
      graph_id: "root",
      lora_code: "<lora:folder/alpha:0.8:0.6>",
      mode: "replace",
    });

    expect(textWidget.value).toBe("<lora:folder/alpha:0.8:0.6>");
    expect(loader.setDirtyCanvas).toHaveBeenCalledWith(true, true);
    expect((await waitForTriggerNames(1))[0]).toEqual(["folder/alpha"]);

    loaderExtension.handleLoraCodeUpdate({
      node_id: 1,
      graph_id: "root",
      lora_code: "<lora:beta:0.5>",
      mode: "append",
    });
    expect(textWidget.value).toBe(
      "<lora:folder/alpha:0.8:0.6> <lora:beta:0.5>"
    );
    expect((await waitForTriggerNames(2))[1]).toEqual(["folder/alpha", "beta"]);

    textWidget.value = "<lora:gamma:1>";
    textWidget.callback(textWidget.value);
    expect((await waitForTriggerNames(3))[2]).toEqual(["gamma"]);

    loader.mode = 4;
    expect((await waitForTriggerNames(4))[3]).toEqual([]);
  });
});
