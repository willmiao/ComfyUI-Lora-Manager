/**
 * The Lora Stacker's `trigger_words` output covers its own entries *plus* the
 * upstream LORA_STACK, so the TriggerWord Toggle wired to it must be fed the
 * chain-wide set. Feeding only the stacker's own loras drops the upstream
 * Cycler pick from the list and, with the toggle applying its selections, the
 * upstream words fall back to pass-through on the next run.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { APP_MODULE, UTILS_MODULE, LORA_STACKER_MODULE } = vi.hoisted(() => ({
  APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
  UTILS_MODULE: new URL("../../../web/comfyui/utils.js", import.meta.url).pathname,
  LORA_STACKER_MODULE: new URL("../../../web/comfyui/lora_stacker.js", import.meta.url).pathname,
}));

const extensionState = { loraStacker: null };
const registerExtensionMock = vi.fn((extension) => {
  if (extension.name === "LoraManager.LoraStacker") {
    extensionState.loraStacker = extension;
  }
});

vi.mock(APP_MODULE, () => ({
  app: {
    registerExtension: registerExtensionMock,
    graph: {},
  },
}));

const TWT_CLASS = "TriggerWord Toggle (LoraManager)";
const LOADER_CLASS = "Lora Loader (LoraManager)";
const CYCLER_CLASS = "Lora Cycler (LoraManager)";
const STACKER_CLASS = "Lora Stacker (LoraManager)";

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
 * Cycler(83) --LORA_STACK--> Stacker(90) -> Loader(56), with the toggle wired
 * to the stacker's `trigger_words` output.
 */
function createCyclerStackerGraph() {
  const twt = {
    id: 55,
    comfyClass: TWT_CLASS,
    widgets: [],
    inputs: [{ name: "trigger_words", type: "string", link: 302 }],
    outputs: [{ name: "filtered_trigger_words", links: [] }],
  };

  const stacker = {
    id: 90,
    comfyClass: STACKER_CLASS,
    mode: 0,
    widgets: [
      { name: "text", value: "", options: {}, callback: null },
      { name: "loras", value: [], options: {}, callback: null },
    ],
    inputs: [
      { name: "text", type: "AUTOCOMPLETE_TEXT_LORAS", link: null },
      { name: "loras", type: "LORAS", link: null },
      { name: "lora_stack", type: "LORA_STACK", link: 300 },
    ],
    outputs: [
      { name: "LORA_STACK", type: "LORA_STACK", links: [301] },
      { name: "trigger_words", type: "STRING", links: [302] },
      { name: "active_loras", type: "STRING", links: [] },
    ],
    addInput: vi.fn(),
  };

  const loader = {
    id: 56,
    comfyClass: LOADER_CLASS,
    widgets: [{ name: "loras", value: [] }],
    inputs: [{ name: "lora_stack", type: "LORA_STACK", link: 301 }],
    outputs: [{ name: "trigger_words", links: [] }],
  };

  const cycler = {
    id: 83,
    comfyClass: CYCLER_CLASS,
    widgets: [
      {
        name: "cycler_config",
        value: {
          current_lora_filename: "Picked",
          current_lora_name: "Picked",
        },
      },
    ],
    inputs: [],
    outputs: [{ name: "LORA_STACK", links: [300] }],
  };

  const graph = createGraph(
    [twt, loader, stacker, cycler],
    new Map([
      [300, { id: 300, origin_id: 83, origin_slot: 0, target_id: 90, target_slot: 2 }],
      [301, { id: 301, origin_id: 90, origin_slot: 0, target_id: 56, target_slot: 4 }],
      [302, { id: 302, origin_id: 90, origin_slot: 1, target_id: 55, target_slot: 3 }],
    ])
  );

  return { graph, twt, stacker, loader, cycler };
}

describe("Lora Stacker trigger word sync", () => {
  let fetchMock;
  let extension;

  beforeEach(async () => {
    vi.resetModules();
    vi.useFakeTimers();

    extension = null;
    registerExtensionMock.mockClear();

    // Re-import so the real utils module instance is used fresh.
    await import(UTILS_MODULE);
    await import(LORA_STACKER_MODULE);

    extension = extensionState.loraStacker;
    expect(extension).toBeDefined();

    fetchMock = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  async function createStackerNode() {
    const { stacker } = createCyclerStackerGraph();
    const nodeType = { comfyClass: STACKER_CLASS, prototype: {} };
    await extension.beforeRegisterNodeDef(nodeType, { name: STACKER_CLASS }, {});
    nodeType.prototype.onNodeCreated.call(stacker);
    return { nodeType, stacker };
  }

  it("includes the upstream Cycler pick when its own loras change", async () => {
    const { stacker } = await createStackerNode();

    stacker.lorasWidget.value = [{ name: "Own", active: true }];
    stacker.lorasWidget.callback(stacker.lorasWidget.value);
    await vi.advanceTimersByTimeAsync(60);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      lora_names: ["Own", "Picked"],
      node_ids: [{ node_id: 55, graph_id: "root" }],
    });
  });

  it("uses the chain-wide set when the text input is edited", async () => {
    const { stacker } = await createStackerNode();

    stacker.inputWidget.callback("<lora:Typed:1.00>");
    await vi.advanceTimersByTimeAsync(60);

    const loraNames = JSON.parse(fetchMock.mock.calls[0][1].body).lora_names;
    expect(loraNames).toContain("Picked");
  });

  it("clears its toggles when the stacker is bypassed", async () => {
    const { stacker } = await createStackerNode();

    stacker.mode = 4;
    stacker.lorasWidget.value = [{ name: "Own", active: true }];
    stacker.lorasWidget.callback(stacker.lorasWidget.value);
    await vi.advanceTimersByTimeAsync(60);

    expect(JSON.parse(fetchMock.mock.calls[0][1].body).lora_names).toEqual([]);
  });
});
