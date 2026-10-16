import { describe, it, expect, beforeEach, vi } from "vitest";

const {
  APP_MODULE,
  API_MODULE,
  UTILS_MODULE,
  LORA_LOADER_MODULE,
} = vi.hoisted(() => ({
  APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
  API_MODULE: new URL("../../../scripts/api.js", import.meta.url).pathname,
  UTILS_MODULE: new URL("../../../web/comfyui/utils.js", import.meta.url).pathname,
  LORA_LOADER_MODULE: new URL("../../../web/comfyui/lora_loader.js", import.meta.url).pathname,
}));

const extensionState = { current: null };
const registerExtensionMock = vi.fn((extension) => {
  extensionState.current = extension;
});

vi.mock(APP_MODULE, () => ({
  app: {
    registerExtension: registerExtensionMock,
    graph: {},
  },
}));

vi.mock(API_MODULE, () => ({
  api: {
    addEventListener: vi.fn(),
  },
}));

const collectActiveLorasFromChain = vi.fn(() => new Set());
const updateConnectedTriggerWords = vi.fn();
const getAllGraphNodes = vi.fn(() => []);
const getNodeFromGraph = vi.fn();
const getWidgetByName = vi.fn();
const getWidgetSerializedValue = vi.fn();

// Mirrors the real merge: LoRAs already on the node keep their saved state
const mergeLoras = vi.fn((lorasText, lorasArr) => {
  const parsed = {};
  const pattern = /<lora:([^:]+):([-\d.]+)(?::([-\d.]+))?>/g;
  let match;
  while ((match = pattern.exec(lorasText || "")) !== null) {
    parsed[match[1]] = Number(match[2]);
  }

  const result = [];
  const used = new Set();
  for (const lora of lorasArr) {
    if (parsed[lora.name] !== undefined) {
      result.push({
        ...lora,
        active: lora.active !== undefined ? lora.active : true,
      });
      used.add(lora.name);
    }
  }
  for (const name of Object.keys(parsed)) {
    if (!used.has(name)) {
      result.push({ name, strength: parsed[name], active: true });
    }
  }
  return result;
});

vi.mock(UTILS_MODULE, () => ({
  collectActiveLorasFromChain,
  updateConnectedTriggerWords,
  mergeLoras,
  chainCallback: (proto, property, callback) => {
    proto[property] = callback;
  },
  getAllGraphNodes,
  getNodeFromGraph,
  getWidgetByName,
  getWidgetSerializedValue,
  LORA_PATTERN: /<lora:([^:]+):([-\d.]+)(?::([-\d.]+))?>/g,
}));

function createNode(loras) {
  const inputWidget = {
    name: "text",
    value: loras.map((lora) => `<lora:${lora.name}:${lora.strength ?? 1}>`).join(" "),
    callback: null,
  };

  const lorasWidget = {
    value: loras,
    callback: vi.fn(),
  };

  // Same wiring onNodeCreated installs: text edits are merged into the widget
  inputWidget.callback = (value) => {
    lorasWidget.value = mergeLoras(value, lorasWidget.value || []);
  };

  return {
    comfyClass: "Lora Loader (LoraManager)",
    inputWidget,
    lorasWidget,
  };
}

describe("Lora Loader re-enables disabled LoRAs sent from the manager", () => {
  beforeEach(() => {
    vi.resetModules();

    extensionState.current = null;
    registerExtensionMock.mockClear();

    collectActiveLorasFromChain.mockClear();
    updateConnectedTriggerWords.mockClear();
    mergeLoras.mockClear();
    getNodeFromGraph.mockReset();
    getAllGraphNodes.mockReset();
    getAllGraphNodes.mockReturnValue([]);
  });

  it("activates a LoRA that is already on the node but toggled off", async () => {
    await import(LORA_LOADER_MODULE);
    const extension = extensionState.current;

    const node = createNode([
      { name: "Alpha", strength: 0.8, active: false },
      { name: "Beta", strength: 1, active: false },
    ]);
    getNodeFromGraph.mockReturnValue(node);

    extension.handleLoraCodeUpdate({
      node_id: 5,
      lora_code: "<lora:Alpha:1.00>",
      mode: "append",
    });

    const alpha = node.lorasWidget.value.find((lora) => lora.name === "Alpha");
    const beta = node.lorasWidget.value.find((lora) => lora.name === "Beta");

    expect(alpha.active).toBe(true);
    // The saved strength is kept and unrelated LoRAs are left untouched
    expect(alpha.strength).toBe(0.8);
    expect(beta.active).toBe(false);
    expect(node.lorasWidget.callback).toHaveBeenCalledWith(node.lorasWidget.value);
  });

  it("re-enables the LoRA in replace mode as well", async () => {
    await import(LORA_LOADER_MODULE);
    const extension = extensionState.current;

    const node = createNode([{ name: "Alpha", strength: 0.5, active: false }]);
    getNodeFromGraph.mockReturnValue(node);

    extension.handleLoraCodeUpdate({
      node_id: 5,
      lora_code: "<lora:Alpha:1.00>",
      mode: "replace",
    });

    expect(node.lorasWidget.value[0].active).toBe(true);
  });

  it("re-enables every LoRA of a recipe sent at once", async () => {
    await import(LORA_LOADER_MODULE);
    const extension = extensionState.current;

    const node = createNode([
      { name: "Alpha", strength: 1, active: false },
      { name: "Beta", strength: 1, active: false },
    ]);
    getNodeFromGraph.mockReturnValue(node);

    extension.handleLoraCodeUpdate({
      node_id: 5,
      lora_code: "<lora:Alpha:1.00> <lora:Beta:0.70>",
      mode: "append",
    });

    expect(node.lorasWidget.value.every((lora) => lora.active === true)).toBe(true);
  });

  it("leaves the widget alone when the sent LoRA is already active", async () => {
    await import(LORA_LOADER_MODULE);
    const extension = extensionState.current;

    const node = createNode([{ name: "Alpha", strength: 1, active: true }]);
    getNodeFromGraph.mockReturnValue(node);

    extension.handleLoraCodeUpdate({
      node_id: 5,
      lora_code: "<lora:Alpha:1.00>",
      mode: "append",
    });

    expect(node.lorasWidget.value[0].active).toBe(true);
    expect(node.lorasWidget.callback).not.toHaveBeenCalled();
  });

  it("does not touch disabled LoRAs that were not sent", async () => {
    await import(LORA_LOADER_MODULE);
    const extension = extensionState.current;

    const node = createNode([{ name: "Alpha", strength: 1, active: false }]);
    getNodeFromGraph.mockReturnValue(node);

    extension.handleLoraCodeUpdate({
      node_id: 5,
      lora_code: "<lora:Gamma:1.00>",
      mode: "append",
    });

    const names = node.lorasWidget.value.map((lora) => lora.name);
    expect(names).toContain("Gamma");
    expect(node.lorasWidget.value.find((lora) => lora.name === "Alpha").active).toBe(false);
  });

  it("activates disabled LoRAs on every node in broadcast mode", async () => {
    await import(LORA_LOADER_MODULE);
    const extension = extensionState.current;

    const first = createNode([{ name: "Alpha", strength: 1, active: false }]);
    const second = createNode([{ name: "Alpha", strength: 1, active: false }]);
    getAllGraphNodes.mockReturnValue([{ node: first }, { node: second }]);

    extension.handleLoraCodeUpdate({
      node_id: -1,
      lora_code: "<lora:Alpha:1.00>",
      mode: "append",
    });

    expect(first.lorasWidget.value[0].active).toBe(true);
    expect(second.lorasWidget.value[0].active).toBe(true);
  });
});
