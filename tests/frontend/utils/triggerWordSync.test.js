import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { APP_MODULE, UTILS_MODULE } = vi.hoisted(() => ({
  APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
  UTILS_MODULE: new URL("../../../web/comfyui/utils.js", import.meta.url).pathname,
}));

vi.mock(APP_MODULE, () => ({
  app: {
    graph: null,
    registerExtension: vi.fn(),
    ui: {
      settings: {
        getSettingValue: vi.fn(),
      },
    },
  },
}));

const TWT_CLASS = "TriggerWord Toggle (LoraManager)";
const LOADER_CLASS = "Lora Loader (LoraManager)";
const CYCLER_CLASS = "Lora Cycler (LoraManager)";

function createGraph(nodes, links) {
  const graph = {
    _nodes: nodes,
    links,
    getNodeById(id) {
      return nodes.find((node) => node.id === id) ?? null;
    },
  };

  nodes.forEach((node) => {
    node.graph = graph;
  });

  return graph;
}

/**
 * Loader(56) -> TriggerWord Toggle(55) via link 123, with a LORA_STACK input
 * from Cycler(83) via link 151 - the shape of the Lora_Cycler workflow.
 */
function createCyclerGraph() {
  const twt = {
    id: 55,
    comfyClass: TWT_CLASS,
    widgets: [],
    inputs: [],
    outputs: [{ name: "filtered_trigger_words", links: [135] }],
  };

  const loader = {
    id: 56,
    comfyClass: LOADER_CLASS,
    widgets: [{ name: "loras", value: [] }],
    inputs: [{ name: "lora_stack", type: "LORA_STACK", link: 151 }],
    outputs: [{ name: "trigger_words", links: [123] }],
  };

  // Before its own configure() runs, the cycler widget still holds the
  // factory default (no current LoRA).
  const cycler = {
    id: 83,
    comfyClass: CYCLER_CLASS,
    widgets: [
      {
        name: "cycler_config",
        value: { current_lora_filename: "", current_lora_name: "" },
      },
    ],
    inputs: [],
    outputs: [{ name: "LORA_STACK", links: [151] }],
  };

  const graph = createGraph(
    [twt, loader, cycler],
    new Map([
      [123, { id: 123, origin_id: 56, origin_slot: 2, target_id: 55, target_slot: 3 }],
      [151, { id: 151, origin_id: 83, origin_slot: 0, target_id: 56, target_slot: 4 }],
    ])
  );

  return { graph, twt, loader, cycler };
}

describe("updateConnectedTriggerWords", () => {
  let collectActiveLorasFromChain;
  let updateConnectedTriggerWords;
  let fetchMock;

  beforeEach(async () => {
    vi.resetModules();
    vi.useFakeTimers();

    ({ collectActiveLorasFromChain, updateConnectedTriggerWords } = await import(
      UTILS_MODULE
    ));

    fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("sends only the final LoRA set when the upstream node configures later", async () => {
    const { loader, cycler } = createCyclerGraph();

    // Loader restores its own (empty) `loras` widget while the cycler still
    // holds the widget default: the chain looks empty.
    expect(Array.from(collectActiveLorasFromChain(loader))).toEqual([]);
    updateConnectedTriggerWords(loader, collectActiveLorasFromChain(loader));

    // Same task, moments later: the cycler restores its saved config.
    cycler.widgets[0].value = {
      current_lora_filename: "Illustrious/realistic/114558v4df2fsdf5",
      current_lora_name: "Illustrious/realistic/114558v4df2fsdf5",
    };
    updateConnectedTriggerWords(loader, collectActiveLorasFromChain(loader));

    await vi.advanceTimersByTimeAsync(60);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/lm/loras/get_trigger_words");
    expect(JSON.parse(init.body)).toEqual({
      lora_names: ["Illustrious/realistic/114558v4df2fsdf5"],
      node_ids: [{ node_id: 55, graph_id: "root" }],
    });
  });

  it("keeps the pending timer on the node so both bundle copies coalesce", async () => {
    const { loader } = createCyclerGraph();

    updateConnectedTriggerWords(loader, new Set(["A"]));
    // Both copies share the node object; the guard lives on it.
    expect(loader.__lmTriggerWordSyncTimer).toBeTruthy();

    await vi.advanceTimersByTimeAsync(60);

    expect(loader.__lmTriggerWordSyncTimer).toBeUndefined();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("still clears the toggle nodes when the LoRAs are really gone", async () => {
    const { loader } = createCyclerGraph();

    updateConnectedTriggerWords(loader, new Set());
    await vi.advanceTimersByTimeAsync(60);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).lora_names).toEqual([]);
  });

  it("does nothing when no toggle node is connected", async () => {
    const { loader, twt } = createCyclerGraph();
    twt.outputs[0].links = [];
    loader.outputs[0].links = [];

    updateConnectedTriggerWords(loader, new Set(["A"]));
    await vi.advanceTimersByTimeAsync(60);

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("syncTriggerWordsForChain", () => {
  let syncTriggerWordsForChain;
  let installTriggerWordConnectionSync;
  let fetchMock;

  beforeEach(async () => {
    vi.resetModules();
    vi.useFakeTimers();

    ({ syncTriggerWordsForChain, installTriggerWordConnectionSync } = await import(
      UTILS_MODULE
    ));

    fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("pushes the chained LoRAs to the loader's toggle", async () => {
    const { loader, cycler } = createCyclerGraph();
    cycler.widgets[0].value = {
      current_lora_filename: "Illustrious/realistic/114558v4df2fsdf5",
      current_lora_name: "Illustrious/realistic/114558v4df2fsdf5",
    };

    syncTriggerWordsForChain(loader);
    await vi.advanceTimersByTimeAsync(60);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/lm/loras/get_trigger_words");
    expect(JSON.parse(init.body)).toEqual({
      lora_names: ["Illustrious/realistic/114558v4df2fsdf5"],
      node_ids: [{ node_id: 55, graph_id: "root" }],
    });
  });

  it("resyncs when a connection changes, installing one hook per class", async () => {
    const { loader, cycler } = createCyclerGraph();
    cycler.widgets[0].value = {
      current_lora_filename: "Illustrious/realistic/114558v4df2fsdf5",
      current_lora_name: "Illustrious/realistic/114558v4df2fsdf5",
    };

    const nodeType = { prototype: {} };
    installTriggerWordConnectionSync(nodeType);
    installTriggerWordConnectionSync(nodeType);
    expect(typeof nodeType.prototype.onConnectionsChange).toBe("function");

    const node = Object.create(nodeType.prototype);
    Object.assign(node, loader);

    node.onConnectionsChange(1, 0, true, {});
    await vi.advanceTimersByTimeAsync(60);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).node_ids).toEqual([
      { node_id: 55, graph_id: "root" },
    ]);
  });

  it("leaves an existing onConnectionsChange handler in place", () => {
    const original = vi.fn();
    const nodeType = { prototype: { onConnectionsChange: original } };
    installTriggerWordConnectionSync(nodeType);

    const node = Object.create(nodeType.prototype);
    node.onConnectionsChange(2, 1, false, {});

    expect(original).toHaveBeenCalledTimes(1);
    expect(original.mock.calls[0].slice(0, 3)).toEqual([2, 1, false]);
  });
});
