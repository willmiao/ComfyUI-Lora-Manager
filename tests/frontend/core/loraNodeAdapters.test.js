import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { APP_MODULE, ADAPTERS_MODULE, UTILS_MODULE, appMock } = vi.hoisted(() => ({
  APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
  ADAPTERS_MODULE: new URL(
    "../../../web/comfyui/lora_node_adapters.js",
    import.meta.url
  ).pathname,
  UTILS_MODULE: new URL("../../../web/comfyui/utils.js", import.meta.url).pathname,
  appMock: {
    graph: null,
    registerExtension: vi.fn(),
    ui: {
      settings: {
        getSettingValue: vi.fn(),
      },
    },
  },
}));

vi.mock(APP_MODULE, () => ({ app: appMock }));

function createGraph(nodes, links) {
  const graph = {
    id: "root",
    _nodes: nodes,
    links: new Map(Object.entries(links).map(([id, link]) => [Number(id), link])),
    getNodeById(id) {
      return nodes.find((node) => node.id === id) ?? null;
    },
  };
  nodes.forEach((node) => {
    node.graph = graph;
  });
  return graph;
}

function createResolverGraph() {
  const source = {
    id: 1,
    comfyClass: "Third Party LoRA Loader",
    mode: 0,
    inputs: [],
    outputs: [{ links: [10] }],
  };
  const resolver = {
    id: 2,
    comfyClass: "LoRA Trigger Words (LoraManager)",
    inputs: [],
    outputs: [{ links: [11] }],
  };
  const toggle = {
    id: 3,
    comfyClass: "TriggerWord Toggle (LoraManager)",
    inputs: [],
    outputs: [],
  };
  createGraph([source, resolver, toggle], {
    10: { origin_id: 1, target_id: 2 },
    11: { origin_id: 2, target_id: 3 },
  });
  return { source, resolver, toggle };
}

describe("third-party LoRA node adapters", () => {
  let api;
  let fetchMock;

  beforeEach(async () => {
    vi.resetModules();
    delete globalThis.__lmLoraNodeAdapterRegistry;
    fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    api = await import(ADAPTERS_MODULE);
  });

  afterEach(() => {
    delete globalThis.__lmLoraNodeAdapterRegistry;
    vi.unstubAllGlobals();
  });

  async function waitForRequestBody() {
    let request;
    await vi.waitFor(() => {
      request = fetchMock.mock.calls.find(
        ([url]) => url === "/api/lm/loras/get_trigger_words"
      );
      expect(request).toBeDefined();
    });
    return JSON.parse(request[1].body);
  }

  it("registers exact node classes and unregisters only its own adapter", () => {
    const applyLoraCode = vi.fn();
    const unregister = api.registerLoraNodeAdapter({
      id: "example-pack",
      nodeClasses: ["Third Party LoRA Loader"],
      applyLoraCode,
    });

    const node = { comfyClass: "Third Party LoRA Loader" };
    expect(api.hasLoraNodeAdapter(node)).toBe(true);
    expect(api.getLoraNodeAdapter(node).applyLoraCode).toBe(applyLoraCode);
    expect(api.hasLoraNodeAdapter("Another Loader")).toBe(false);

    unregister();
    unregister();
    expect(api.hasLoraNodeAdapter(node)).toBe(false);
  });

  it("shares registrations across direct and bundled module copies", async () => {
    api.registerLoraNodeAdapter({
      id: "example-pack",
      nodeClasses: ["Third Party LoRA Loader"],
      applyLoraCode: vi.fn(),
    });

    vi.resetModules();
    const reloadedApi = await import(ADAPTERS_MODULE);

    expect(reloadedApi.hasLoraNodeAdapter("Third Party LoRA Loader")).toBe(true);
  });

  it("rejects duplicate classes without partially registering the adapter", () => {
    api.registerLoraNodeAdapter({
      id: "first-pack",
      nodeClasses: ["Shared Loader"],
      applyLoraCode: vi.fn(),
    });

    expect(() =>
      api.registerLoraNodeAdapter({
        id: "second-pack",
        nodeClasses: ["New Loader", "Shared Loader"],
        applyLoraCode: vi.fn(),
      })
    ).toThrow("already registered");
    expect(api.hasLoraNodeAdapter("New Loader")).toBe(false);
  });

  it("applies LoRA code and refreshes toggles through a resolver node", async () => {
    const { source, toggle } = createResolverGraph();
    const { getConnectedTriggerToggleNodes } = await import(UTILS_MODULE);
    expect(getConnectedTriggerToggleNodes(source)).toEqual([toggle]);
    const applyLoraCode = vi.fn();
    api.registerLoraNodeAdapter({
      id: "example-pack",
      nodeClasses: [source.comfyClass],
      applyLoraCode,
      getActiveLoraNames: () => ["Alpha"],
    });

    expect(api.applyLoraCodeToNode(source, "<lora:Alpha:1>", "replace")).toBe(true);
    expect(applyLoraCode).toHaveBeenCalledWith({
      node: source,
      loraCode: "<lora:Alpha:1>",
      mode: "replace",
    });

    expect(await waitForRequestBody()).toEqual({
      lora_names: ["Alpha"],
      node_ids: [{ node_id: toggle.id, graph_id: "root" }],
    });
  });

  it("clears connected toggles when the adapted node is bypassed", async () => {
    const { source } = createResolverGraph();
    source.mode = 4;
    api.registerLoraNodeAdapter({
      id: "example-pack",
      nodeClasses: [source.comfyClass],
      applyLoraCode: vi.fn(),
      getActiveLoraNames: () => ["Alpha"],
    });

    expect(api.notifyLoraNodeChanged(source)).toBe(true);
    const body = await waitForRequestBody();
    expect(body.lora_names).toEqual([]);
  });

  it("includes adapted upstream LORA_STACK providers", async () => {
    const upstream = {
      id: 10,
      comfyClass: "Third Party Stack",
      mode: 0,
      inputs: [],
      outputs: [],
    };
    const loader = {
      id: 11,
      comfyClass: "Third Party Loader With Stack",
      mode: 0,
      inputs: [{ type: "LORA_STACK", link: 20 }],
      outputs: [{ links: [21] }],
    };
    const toggle = {
      id: 12,
      comfyClass: "TriggerWord Toggle (LoraManager)",
      inputs: [],
      outputs: [],
    };
    createGraph([upstream, loader, toggle], {
      20: { origin_id: 10, target_id: 11 },
      21: { origin_id: 11, target_id: 12 },
    });

    api.registerLoraNodeAdapter({
      id: "upstream-pack",
      nodeClasses: [upstream.comfyClass],
      applyLoraCode: vi.fn(),
      getActiveLoraNames: () => ["Upstream"],
    });
    api.registerLoraNodeAdapter({
      id: "loader-pack",
      nodeClasses: [loader.comfyClass],
      applyLoraCode: vi.fn(),
      getActiveLoraNames: () => ["Own"],
    });

    api.notifyLoraNodeChanged(loader);
    const body = await waitForRequestBody();
    expect(body.lora_names).toEqual(["Own", "Upstream"]);
  });
});
