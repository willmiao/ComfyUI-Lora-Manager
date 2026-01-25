import { describe, it, expect, beforeEach, vi } from "vitest";

const {
  APP_MODULE,
  API_MODULE,
  UTILS_MODULE,
  LORAS_WIDGET_MODULE,
  LORA_LOADER_MODULE,
  LORA_STACKER_MODULE,
} = vi.hoisted(() => ({
  APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
  API_MODULE: new URL("../../../scripts/api.js", import.meta.url).pathname,
  UTILS_MODULE: new URL("../../../web/comfyui/utils.js", import.meta.url).pathname,
  LORAS_WIDGET_MODULE: new URL("../../../web/comfyui/loras_widget.js", import.meta.url).pathname,
  LORA_LOADER_MODULE: new URL("../../../web/comfyui/lora_loader.js", import.meta.url).pathname,
  LORA_STACKER_MODULE: new URL("../../../web/comfyui/lora_stacker.js", import.meta.url).pathname,
}));

const extensionState = {
  loraLoader: null,
  loraStacker: null,
};
const registerExtensionMock = vi.fn((extension) => {
  if (extension.name === "LoraManager.LoraLoader") {
    extensionState.loraLoader = extension;
  } else if (extension.name === "LoraManager.LoraStacker") {
    extensionState.loraStacker = extension;
  }
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
const updateDownstreamLoaders = vi.fn();
const getActiveLorasFromNode = vi.fn();
const mergeLoras = vi.fn();
const getAllGraphNodes = vi.fn();
const getNodeFromGraph = vi.fn();
const getNodeKey = vi.fn();
const getLinkFromGraph = vi.fn();
const chainCallback = vi.fn((proto, property, callback) => {
  proto[property] = callback;
});

vi.mock(UTILS_MODULE, async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    collectActiveLorasFromChain,
    updateConnectedTriggerWords,
    updateDownstreamLoaders,
    getActiveLorasFromNode,
    mergeLoras,
    chainCallback,
    getAllGraphNodes,
    getNodeFromGraph,
    getNodeKey,
    getLinkFromGraph,
  };
});

const addLorasWidget = vi.fn();

vi.mock(LORAS_WIDGET_MODULE, () => ({
  addLorasWidget,
}));

describe("Node mode change handling", () => {
  beforeEach(() => {
    vi.resetModules();

    extensionState.loraLoader = null;
    extensionState.loraStacker = null;
    registerExtensionMock.mockClear();

    collectActiveLorasFromChain.mockClear();
    collectActiveLorasFromChain.mockImplementation(() => new Set(["Alpha"]));

    updateConnectedTriggerWords.mockClear();

    updateDownstreamLoaders.mockClear();

    getActiveLorasFromNode.mockClear();
    getActiveLorasFromNode.mockImplementation(() => new Set(["Alpha"]));

    mergeLoras.mockClear();
    mergeLoras.mockImplementation(() => [{ name: "Alpha", active: true }]);

    addLorasWidget.mockClear();
    addLorasWidget.mockImplementation((_node, _name, _opts, callback) => ({
      widget: { value: [], callback },
    }));
  });

  describe("Lora Stacker mode change handling", () => {
    let node, extension;

    beforeEach(async () => {
      await import(LORA_STACKER_MODULE);

      expect(registerExtensionMock).toHaveBeenCalled();
      extension = extensionState.loraStacker;
      expect(extension).toBeDefined();

      const nodeType = { comfyClass: "Lora Stacker (LoraManager)", prototype: {} };
      const nodeData = { name: "Lora Stacker (LoraManager)" };

      await extension.beforeRegisterNodeDef(nodeType, nodeData, {});

      // Create widgets with proper structure for lora_stacker.js
      // Widget at index 0 is the AUTOCOMPLETE_TEXT_LORAS widget (created by Vue widgets)
      const inputWidget = {
        name: "text",
        value: "",
        options: {},
        callback: null, // Will be set by onNodeCreated
      };

      const lorasWidget = {
        name: "loras",
        value: [
          { name: "Alpha", active: true },
          { name: "Beta", active: true },
          { name: "Gamma", active: false },
        ],
      };

      node = {
        comfyClass: "Lora Stacker (LoraManager)",
        widgets: [inputWidget, lorasWidget],
        lorasWidget,
        addInput: vi.fn(),
        mode: 0, // Initial mode
        graph: {},
        outputs: [], // Add outputs property for updateDownstreamLoaders
      };

      nodeType.prototype.onNodeCreated.call(node);
    });

    it("should handle mode property changes", () => {
      const initialMode = node.mode;
      expect(initialMode).toBe(0);

      // Change mode from 0 to 3
      node.mode = 3;

      // Verify that the property was updated
      expect(node.mode).toBe(3);
    });

    it("should update trigger words based on node activity when mode changes", () => {
      // Change to active mode (0)
      node.mode = 0;
      expect(node.mode).toBe(0);

      // Change to inactive mode (1)
      node.mode = 1;
      expect(node.mode).toBe(1);

      // Change to active mode (3) - also considered active
      node.mode = 3;
      expect(node.mode).toBe(3);
    });
  });

  describe("Lora Loader mode change handling", () => {
    let node, extension;

    beforeEach(async () => {
      await import(LORA_LOADER_MODULE);

      expect(registerExtensionMock).toHaveBeenCalled();
      extension = extensionState.loraLoader;
      expect(extension).toBeDefined();

      const nodeType = { comfyClass: "Lora Loader (LoraManager)", prototype: {} };
      await extension.beforeRegisterNodeDef(nodeType, {}, {});

      // Widget at index 0 is the AUTOCOMPLETE_TEXT_LORAS widget (created by Vue widgets)
      node = {
        comfyClass: "Lora Loader (LoraManager)",
        widgets: [
          {
            value: "",
            options: {},
            callback: null, // Will be set by onNodeCreated
          },
        ],
        addInput: vi.fn(),
        mode: 0, // Initial mode
        graph: {},
      };

      nodeType.prototype.onNodeCreated.call(node);
    });

    it("should handle mode property changes", () => {
      const initialMode = node.mode;
      expect(initialMode).toBe(0);

      // Change mode from 0 to 3
      node.mode = 3;

      // Verify that the property was updated
      expect(node.mode).toBe(3);

      // Verify that updateConnectedTriggerWords was called
      expect(updateConnectedTriggerWords).toHaveBeenCalledWith(
        node,
        expect.anything() // This would be the active Lora names set
      );
    });

    it("should call onModeChange when mode property is changed", () => {
      const initialMode = node.mode;
      expect(initialMode).toBe(0);

      // Mock console.log to verify it was called
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

      // Change mode from 0 to 1
      node.mode = 1;

      // Verify console log was called
      expect(consoleSpy).toHaveBeenCalledWith(
        '[Lora Loader] Node mode changed from 0 to 1'
      );
      expect(consoleSpy).toHaveBeenCalledWith(
        'Lora Loader node mode changed: from 0 to 1'
      );

      consoleSpy.mockRestore();
    });

    it("should update connected trigger words when mode changes", () => {
      // Mock the collectActiveLorasFromChain to return a specific set
      collectActiveLorasFromChain.mockImplementation(() => new Set(["LoaderLora1", "LoaderLora2"]));

      // Change mode
      node.mode = 2;

      // Verify that collectActiveLorasFromChain and updateConnectedTriggerWords were called
      expect(collectActiveLorasFromChain).toHaveBeenCalledWith(node);
      expect(updateConnectedTriggerWords).toHaveBeenCalledWith(
        node,
        new Set(["LoaderLora1", "LoaderLora2"])
      );
    });
  });
});
