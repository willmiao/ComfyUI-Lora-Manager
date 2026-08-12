import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

const { APP_MODULE, API_MODULE, STYLES_MODULE, REGISTRY_MODULE, appMock, apiMock, registeredExtensions } =
  vi.hoisted(() => {
    const registeredExtensions = [];
    const appMock = {
      graph: null,
      registerExtension: (ext) => registeredExtensions.push(ext),
    };
    const apiMock = {
      clientId: "client-1",
      initialClientId: null,
      addEventListener: vi.fn(),
    };
    return {
      APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
      API_MODULE: new URL("../../../scripts/api.js", import.meta.url).pathname,
      STYLES_MODULE: new URL("../../../web/comfyui/lm_styles_loader.js", import.meta.url).pathname,
      REGISTRY_MODULE: new URL("../../../web/comfyui/workflow_registry.js", import.meta.url).pathname,
      appMock,
      apiMock,
      registeredExtensions,
    };
  });

vi.mock(APP_MODULE, () => ({ app: appMock }));
vi.mock(API_MODULE, () => ({ api: apiMock }));
vi.mock(STYLES_MODULE, () => ({ ensureLmStyles: vi.fn() }));

function createTextEncodeNode({ linked = false, id = 1 } = {}) {
  const textWidget = { name: "text", type: "customtext", value: "old prompt", callback: null };
  return {
    id,
    comfyClass: "CLIPTextEncode",
    title: "CLIP Text Encode",
    mode: 0,
    properties: {},
    widgets: [textWidget, { name: "clip", type: "combo" }],
    widgets_values: ["old prompt", "clip-1"],
    inputs: [
      { name: "text", type: "STRING", widget: textWidget, link: linked ? 101 : null },
      { name: "clip", type: "CLIP", link: null },
    ],
    setDirtyCanvas: vi.fn(),
    graph: null,
  };
}

function createSubgraph({ id = "sub-1", nodes = [] } = {}) {
  const graph = {
    id,
    _nodes: nodes,
    _subgraphs: new Map(),
    getNodeById: vi.fn((nodeId) => nodes.find((n) => n.id === nodeId) ?? null),
    events: { addEventListener: vi.fn() },
  };
  for (const node of nodes) {
    node.graph = graph;
  }
  return graph;
}

function createGraph({ nodes = [], subgraphs = [] } = {}) {
  const graph = {
    id: "root",
    _nodes: nodes,
    _subgraphs: new Map(),
    getNodeById: vi.fn((nodeId) => nodes.find((n) => n.id === nodeId) ?? null),
    events: { addEventListener: vi.fn() },
  };
  for (const subgraph of subgraphs) {
    graph._subgraphs.set(subgraph.id, subgraph);
  }
  for (const node of nodes) {
    node.graph = graph;
  }
  return graph;
}

function lastRegisterPayload(fetchMock) {
  const calls = fetchMock.mock.calls.filter(
    ([url]) => url === "/api/lm/register-nodes"
  );
  expect(calls.length).toBeGreaterThan(0);
  return JSON.parse(calls[calls.length - 1][1].body);
}

describe("LoraManager.WorkflowRegistry", () => {
  let extension;
  let fetchMock;

  beforeEach(async () => {
    vi.resetModules();
    registeredExtensions.length = 0;
    appMock.graph = null;
    apiMock.addEventListener.mockClear();
    fetchMock = vi.fn().mockResolvedValue({ ok: true });
    global.fetch = fetchMock;
    await import(REGISTRY_MODULE);
    extension = registeredExtensions.find(
      (ext) => ext.name === "LoraManager.WorkflowRegistry"
    );
    expect(extension).toBeDefined();
  });

  afterEach(() => {
    delete global.fetch;
  });

  describe("refreshRegistry", () => {
    it("registers an unconnected CLIPTextEncode as a text target", async () => {
      appMock.graph = createGraph({ nodes: [createTextEncodeNode()] });

      await extension.refreshRegistry(true);

      const body = lastRegisterPayload(fetchMock);
      expect(body.nodes).toHaveLength(1);
      expect(body.nodes[0].capabilities.has_text_widget).toBe(true);
      expect(body.nodes[0].capabilities.text_widget_connected).toBe(false);
    });

    it("excludes a CLIPTextEncode whose text input is connected", async () => {
      appMock.graph = createGraph({ nodes: [createTextEncodeNode({ linked: true })] });

      await extension.refreshRegistry(true);

      const body = lastRegisterPayload(fetchMock);
      expect(body.nodes).toHaveLength(1);
      expect(body.nodes[0].capabilities.has_text_widget).toBe(false);
      expect(body.nodes[0].capabilities.text_widget_connected).toBe(true);
    });

    it("registers connection state for nodes inside subgraphs", async () => {
      const inner = createTextEncodeNode({ linked: true, id: 7 });
      const subgraph = createSubgraph({ id: "sub-1", nodes: [inner] });
      appMock.graph = createGraph({ subgraphs: [subgraph] });

      await extension.refreshRegistry(true);

      const body = lastRegisterPayload(fetchMock);
      expect(body.nodes).toHaveLength(1);
      expect(body.nodes[0].graph_id).toBe("sub-1");
      expect(body.nodes[0].node_id).toBe(7);
      expect(body.nodes[0].capabilities.text_widget_connected).toBe(true);
    });

    it("re-registers when text_widget_connected changes (fingerprint)", async () => {
      const node = createTextEncodeNode();
      appMock.graph = createGraph({ nodes: [node] });

      await extension.refreshRegistry(true);
      await extension.refreshRegistry();
      expect(
        fetchMock.mock.calls.filter(([url]) => url === "/api/lm/register-nodes")
      ).toHaveLength(1);

      node.inputs[0].link = 101;
      await extension.refreshRegistry();
      const body = lastRegisterPayload(fetchMock);
      expect(body.nodes[0].capabilities.text_widget_connected).toBe(true);
    });
  });

  describe("applyWidgetUpdate (inject_text)", () => {
    it("updates the widget value when the text input is not connected", async () => {
      const node = createTextEncodeNode();
      const callback = vi.fn();
      node.widgets[0].callback = callback;
      appMock.graph = createGraph({ nodes: [node] });
      extension.flashWidget = vi.fn();

      await extension.applyWidgetUpdate({
        node_id: 1,
        action: "inject_text",
        value: "hello",
        mode: "replace",
      });

      expect(node.widgets[0].value).toBe("hello");
      expect(node.widgets_values[0]).toBe("hello");
      expect(callback).toHaveBeenCalledWith("hello");
    });

    it("skips inject_text when the target widget is connected and self-heals the registry", async () => {
      const node = createTextEncodeNode({ linked: true });
      appMock.graph = createGraph({ nodes: [node] });
      extension.flashWidget = vi.fn();
      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

      await extension.applyWidgetUpdate({
        node_id: 1,
        graph_id: "root",
        action: "inject_text",
        value: "new prompt",
        mode: "replace",
      });

      expect(node.widgets[0].value).toBe("old prompt");
      expect(node.widgets_values[0]).toBe("old prompt");
      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining("connected to an input"),
        expect.anything(),
        expect.anything()
      );
      await vi.waitFor(() => {
        expect(
          fetchMock.mock.calls.some(([url]) => url === "/api/lm/register-nodes")
        ).toBe(true);
      });
      warnSpy.mockRestore();
    });
  });

  describe("setup link-change hooks", () => {
    it("hooks root events, existing subgraphs, and future subgraphs", () => {
      const subgraph = createSubgraph({ id: "sub-1", nodes: [] });
      const graph = createGraph({ subgraphs: [subgraph] });
      appMock.graph = graph;

      extension.setup();

      expect(graph.events.addEventListener).toHaveBeenCalledWith(
        "node:slot-links:changed",
        expect.any(Function)
      );
      expect(graph.events.addEventListener).toHaveBeenCalledWith(
        "subgraph-created",
        expect.any(Function)
      );
      expect(subgraph.events.addEventListener).toHaveBeenCalledWith(
        "node:slot-links:changed",
        expect.any(Function)
      );

      const createdHandler = graph.events.addEventListener.mock.calls.find(
        ([name]) => name === "subgraph-created"
      )[1];
      const laterSubgraph = createSubgraph({ id: "sub-2", nodes: [] });
      createdHandler({ subgraph: laterSubgraph });
      expect(laterSubgraph.events.addEventListener).toHaveBeenCalledWith(
        "node:slot-links:changed",
        expect.any(Function)
      );
    });
  });
});
