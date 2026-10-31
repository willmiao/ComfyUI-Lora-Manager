import { beforeEach, describe, expect, it, vi } from "vitest";

const { APP_MODULE, EXTENSION_MODULE, SETTINGS_MODULE, UTILS_MODULE, appMock, registeredExtensions } =
  vi.hoisted(() => {
    const registeredExtensions = [];
    const appMock = {
      configuringGraph: false,
      registerExtension: (ext) => registeredExtensions.push(ext),
    };
    return {
      APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
      EXTENSION_MODULE: new URL(
        "../../../web/comfyui/prompt_dynamic_inputs.js",
        import.meta.url
      ).pathname,
      SETTINGS_MODULE: new URL(
        "../../../web/comfyui/settings.js",
        import.meta.url
      ).pathname,
      UTILS_MODULE: new URL("../../../web/comfyui/utils.js", import.meta.url)
        .pathname,
      appMock,
      registeredExtensions,
    };
  });

vi.mock(APP_MODULE, () => ({
  app: appMock,
}));

vi.mock(SETTINGS_MODULE, () => ({
  PROMPT_TAG_AUTOCOMPLETE_SETTING_ID: "loramanager.prompt_tag_autocomplete",
  getPromptTagAutocompletePreference: () => true,
  setLoraManagerSettingValue: vi.fn(),
}));

vi.mock(UTILS_MODULE, () => ({
  showToast: vi.fn(),
}));

describe("Prompt (LoraManager) dynamic trigger word inputs", () => {
  let extension;

  beforeEach(async () => {
    vi.resetModules();
    registeredExtensions.length = 0;
    appMock.configuringGraph = false;
    await import(EXTENSION_MODULE);
    extension = registeredExtensions.find(
      (ext) => ext.name === "Comfy.LoraManager.PromptLM"
    );
    expect(extension).toBeDefined();
  });

  function createNodeType() {
    const nodeType = { prototype: {} };
    extension.beforeRegisterNodeDef(
      nodeType,
      { name: "Prompt (LoraManager)" },
      appMock
    );
    return nodeType;
  }

  /**
   * Minimal LiteGraph node stand-in. ``removeInput`` mirrors the current
   * frontend: later links have their ``target_slot`` shifted down.
   */
  function createNode(inputs = [], { withLinkStore = true } = {}) {
    const node = {
      id: 64,
      comfyClass: "Prompt (LoraManager)",
      inputs: inputs.map((input) => ({ ...input })),
      graph: withLinkStore ? { links: new Map() } : undefined,
      addInput: vi.fn(function (name, type, opts) {
        this.inputs.push({ name, type, link: null, ...opts });
      }),
      removeInput: vi.fn(function (index) {
        this.inputs.splice(index, 1);
        for (const link of this.graph?.links.values() ?? []) {
          if (link.target_id === this.id && link.target_slot > index) {
            link.target_slot -= 1;
          }
        }
      }),
    };
    return node;
  }

  function makeLinkInfo() {
    return { id: 999, origin_id: 55, target_id: 64 };
  }

  function names(node) {
    return node.inputs.map((input) => input.name);
  }

  const clipInput = { name: "clip", type: "CLIP", link: 134 };
  const seedInput = { name: "seed", type: "INT", link: null };
  const textInput = {
    name: "text",
    type: "AUTOCOMPLETE_TEXT_PROMPT,STRING",
    widget: { name: "text" },
    link: null,
  };

  it("does not touch slots while the graph is being configured", () => {
    appMock.configuringGraph = true;
    const nodeType = createNodeType();
    const node = createNode([
      { name: "trigger_words1", type: "STRING", link: null },
      { name: "trigger_words", type: "STRING", link: 135 },
    ]);
    node.onConnectionsChange = nodeType.prototype.onConnectionsChange;

    node.onConnectionsChange(1, 1, true, makeLinkInfo());

    expect(names(node)).toEqual(["trigger_words1", "trigger_words"]);
    expect(node.addInput).not.toHaveBeenCalled();
    expect(node.removeInput).not.toHaveBeenCalled();
  });

  it("migrates a legacy layout on load: connected slot first, one free slot after", () => {
    const node = createNode([
      clipInput,
      seedInput,
      { name: "trigger_words1", shape: 7, localized_name: "trigger_words1", type: "STRING", link: null },
      textInput,
      { name: "trigger_words", shape: 7, localized_name: "trigger_words", type: "STRING", link: 135 },
    ]);
    node.graph.links.set(135, { id: 135, origin_id: 55, target_id: 64, target_slot: 4 });

    extension.loadedGraphNode(node);

    expect(names(node)).toEqual([
      "clip",
      "seed",
      "text",
      "trigger_words1",
      "trigger_words2",
    ]);
    // The connected slot kept its link and took the first trigger slot.
    const connected = node.inputs[3];
    expect(connected.link).toBe(135);
    expect(connected.localized_name).toBe("trigger_words1");
    expect(node.graph.links.get(135).target_slot).toBe(3);
    expect(node.inputs[4].link).toBeNull();
  });

  it("adds one free slot when every trigger slot is connected", () => {
    const node = createNode([
      clipInput,
      seedInput,
      { name: "trigger_words1", shape: 7, type: "STRING", link: 135 },
      textInput,
    ]);

    extension.loadedGraphNode(node);

    expect(names(node)).toEqual([
      "clip",
      "seed",
      "trigger_words1",
      "text",
      "trigger_words2",
    ]);
    expect(node.inputs[4].link ?? null).toBeNull();
  });

  it("leaves the canonical layout alone", () => {
    const node = createNode([
      clipInput,
      seedInput,
      { name: "trigger_words1", shape: 7, type: "STRING", link: 135 },
      textInput,
      { name: "trigger_words2", type: "STRING", link: null },
    ]);

    extension.loadedGraphNode(node);

    expect(names(node)).toEqual([
      "clip",
      "seed",
      "trigger_words1",
      "text",
      "trigger_words2",
    ]);
    expect(node.addInput).not.toHaveBeenCalled();
    expect(node.removeInput).not.toHaveBeenCalled();
  });

  it("does not rebuild inputs without the shared link store", () => {
    const node = createNode(
      [
        clipInput,
        { name: "trigger_words1", type: "STRING", link: null },
        textInput,
        { name: "trigger_words", type: "STRING", link: 135 },
      ],
      { withLinkStore: false }
    );

    extension.loadedGraphNode(node);

    expect(node.removeInput).not.toHaveBeenCalled();
    expect(names(node)).toEqual([
      "clip",
      "trigger_words1",
      "text",
      "trigger_words2",
    ]);
  });

  it("adds a slot when the last trigger slot gets connected", () => {
    const nodeType = createNodeType();
    const node = createNode([
      { name: "trigger_words1", type: "STRING", link: null },
      textInput,
    ]);
    node.onConnectionsChange = nodeType.prototype.onConnectionsChange;

    node.onConnectionsChange(1, 0, true, makeLinkInfo());

    expect(names(node)).toEqual([
      "trigger_words1",
      "text",
      "trigger_words2",
    ]);
  });

  it("does not add a slot when a middle trigger slot gets connected", () => {
    const nodeType = createNodeType();
    const node = createNode([
      { name: "trigger_words1", type: "STRING", link: 11 },
      { name: "trigger_words2", type: "STRING", link: null },
      { name: "trigger_words3", type: "STRING", link: null },
    ]);
    node.onConnectionsChange = nodeType.prototype.onConnectionsChange;

    node.onConnectionsChange(1, 1, true, makeLinkInfo());

    expect(node.addInput).not.toHaveBeenCalled();
  });

  it("removes a disconnected middle slot and renumbers", () => {
    const nodeType = createNodeType();
    const node = createNode([
      { name: "trigger_words1", type: "STRING", link: 11 },
      { name: "trigger_words2", type: "STRING", link: null },
      { name: "trigger_words3", type: "STRING", link: null },
    ]);
    node.onConnectionsChange = nodeType.prototype.onConnectionsChange;

    node.onConnectionsChange(1, 1, false, makeLinkInfo());

    expect(names(node)).toEqual(["trigger_words1", "trigger_words2"]);
    expect(node.removeInput).toHaveBeenCalledTimes(1);
  });

  it("keeps the trailing slot when it is disconnected", () => {
    const nodeType = createNodeType();
    const node = createNode([
      { name: "trigger_words1", type: "STRING", link: 11 },
      { name: "trigger_words2", type: "STRING", link: null },
    ]);
    node.onConnectionsChange = nodeType.prototype.onConnectionsChange;

    node.onConnectionsChange(1, 1, false, makeLinkInfo());

    expect(names(node)).toEqual(["trigger_words1", "trigger_words2"]);
    expect(node.removeInput).not.toHaveBeenCalled();
  });

  it("ensures a trigger slot exists on creation", () => {
    const node = createNode([clipInput, textInput]);
    extension.nodeCreated(node, {});

    expect(names(node)).toEqual(["clip", "text", "trigger_words1"]);
  });
});
