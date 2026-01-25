import { describe, it, expect, beforeEach, vi } from "vitest";

const {
  APP_MODULE,
  API_MODULE,
  UTILS_MODULE,
  LORAS_WIDGET_MODULE,
  LORA_LOADER_MODULE,
} = vi.hoisted(() => ({
  APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
  API_MODULE: new URL("../../../scripts/api.js", import.meta.url).pathname,
  UTILS_MODULE: new URL("../../../web/comfyui/utils.js", import.meta.url).pathname,
  LORAS_WIDGET_MODULE: new URL("../../../web/comfyui/loras_widget.js", import.meta.url).pathname,
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

const collectActiveLorasFromChain = vi.fn();
const updateConnectedTriggerWords = vi.fn();
const mergeLoras = vi.fn();
const getAllGraphNodes = vi.fn();
const getNodeFromGraph = vi.fn();

vi.mock(UTILS_MODULE, () => ({
  collectActiveLorasFromChain,
  updateConnectedTriggerWords,
  mergeLoras,
  chainCallback: (proto, property, callback) => {
    proto[property] = callback;
  },
  getAllGraphNodes,
  getNodeFromGraph,
  LORA_PATTERN: /<lora:([^:]+):([-\d.]+)(?::([-\d.]+))?>/g,
}));

const addLorasWidget = vi.fn();

vi.mock(LORAS_WIDGET_MODULE, () => ({
  addLorasWidget,
}));

describe("Lora Loader trigger word updates", () => {
  beforeEach(() => {
    vi.resetModules();

    extensionState.current = null;
    registerExtensionMock.mockClear();

    collectActiveLorasFromChain.mockClear();
    collectActiveLorasFromChain.mockImplementation(() => new Set(["Alpha"]));

    updateConnectedTriggerWords.mockClear();

    mergeLoras.mockClear();
    mergeLoras.mockImplementation(() => [{ name: "Alpha", active: true }]);

    addLorasWidget.mockClear();
    addLorasWidget.mockImplementation((_node, _name, _opts, callback) => ({
      widget: { value: [], callback },
    }));
  });

  it("refreshes trigger word toggles after LoRA syntax edits in the input widget", async () => {
    await import(LORA_LOADER_MODULE);

    expect(registerExtensionMock).toHaveBeenCalled();
    const extension = extensionState.current;
    expect(extension).toBeDefined();

    const nodeType = { comfyClass: "Lora Loader (LoraManager)", prototype: {} };
    await extension.beforeRegisterNodeDef(nodeType, {}, {});

    // Create mock widget (AUTOCOMPLETE_TEXT_LORAS type created by Vue widgets)
    const inputWidget = {
      value: "",
      options: {},
      callback: null, // Will be set by onNodeCreated
    };

    const node = {
      comfyClass: "Lora Loader (LoraManager)",
      widgets: [inputWidget],
      addInput: vi.fn(),
      graph: {},
    };

    nodeType.prototype.onNodeCreated.call(node);

    // The widget is now the AUTOCOMPLETE_TEXT_LORAS type, created automatically by Vue widgets
    expect(node.inputWidget).toBe(inputWidget);
    expect(node.lorasWidget).toBeDefined();

    // The callback should have been set up by onNodeCreated
    const inputCallback = inputWidget.callback;
    expect(typeof inputCallback).toBe("function");

    // Simulate typing in the input widget
    inputCallback("<lora:Alpha:1.0>");

    expect(mergeLoras).toHaveBeenCalledWith("<lora:Alpha:1.0>", []);
    expect(node.lorasWidget.value).toEqual([{ name: "Alpha", active: true }]);
    expect(collectActiveLorasFromChain).toHaveBeenCalledWith(node);

    const activeSet = collectActiveLorasFromChain.mock.results.at(-1)?.value;
    const [[targetNode, triggerWordSet]] = updateConnectedTriggerWords.mock.calls;
    expect(targetNode).toBe(node);
    expect(triggerWordSet).toBe(activeSet);
    expect([...triggerWordSet]).toEqual(["Alpha"]);
  });
});
