import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

const {
  APP_MODULE,
  API_MODULE,
  UTILS_MODULE,
  TAGS_WIDGET_MODULE,
  SETTINGS_MODULE,
  TRIGGER_WORD_TOGGLE_MODULE,
} = vi.hoisted(() => ({
  APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
  API_MODULE: new URL("../../../scripts/api.js", import.meta.url).pathname,
  UTILS_MODULE: new URL("../../../web/comfyui/utils.js", import.meta.url).pathname,
  TAGS_WIDGET_MODULE: new URL("../../../web/comfyui/tags_widget.js", import.meta.url).pathname,
  SETTINGS_MODULE: new URL("../../../web/comfyui/settings.js", import.meta.url).pathname,
  TRIGGER_WORD_TOGGLE_MODULE: new URL("../../../web/comfyui/trigger_word_toggle.js", import.meta.url).pathname,
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

vi.mock(UTILS_MODULE, () => ({
  CONVERTED_TYPE: "converted-widget",
  getNodeFromGraph: vi.fn(),
  getWidgetSerializedValue: (node, widgetName) => {
    if (!node || !Array.isArray(node.widgets) || !Array.isArray(node.widgets_values)) {
      return undefined;
    }
    const widgetIndex = node.widgets.findIndex((widget) => widget?.name === widgetName);
    return widgetIndex >= 0 ? node.widgets_values[widgetIndex] : undefined;
  },
}));

vi.mock(TAGS_WIDGET_MODULE, () => ({
  addTagsWidget: (node, name) => {
    const widget = { name, value: [] };
    node.widgets.push(widget);
    return { widget };
  },
}));

vi.mock(SETTINGS_MODULE, () => ({
  getWheelSensitivity: () => 0.02,
}));

function createNode({ widgetsValues } = {}) {
  const node = {
    comfyClass: "TriggerWord Toggle (LoraManager)",
    widgets: [
      { name: "group_mode", value: true },
      { name: "default_active", value: true },
      { name: "allow_strength_adjustment", value: false },
    ],
    widgets_values: widgetsValues,
    addInput: vi.fn(),
    addWidget: vi.fn((type, name, value) => {
      const widget = { type, name, value };
      node.widgets.push(widget);
      return widget;
    }),
  };
  return node;
}

describe("TriggerWord Toggle serialization", () => {
  const originalRequestAnimationFrame = globalThis.requestAnimationFrame;

  beforeEach(async () => {
    vi.resetModules();

    extensionState.current = null;
    registerExtensionMock.mockClear();

    // Run nodeCreated's deferred setup synchronously.
    globalThis.requestAnimationFrame = (callback) => {
      callback();
      return 0;
    };

    await import(TRIGGER_WORD_TOGGLE_MODULE);
  });

  afterEach(() => {
    globalThis.requestAnimationFrame = originalRequestAnimationFrame;
  });

  it("restores saved widget values by widget name", async () => {
    const savedTags = [
      { text: "foo", active: true, strength: null, highlighted: true },
    ];
    const node = createNode({
      widgetsValues: [true, true, false, savedTags, "foo, bar"],
    });

    await extensionState.current.nodeCreated(node);

    expect(node.tagWidget).toBeDefined();
    expect(node.tagWidget.value).toHaveLength(1);
    expect(node.tagWidget.value[0]).toMatchObject({ text: "foo", active: true });
    expect(node.originalMessageWidget.value).toBe("foo, bar");
  });

  it("strips transient highlighted state from serialized tag values", async () => {
    const node = createNode({
      widgetsValues: [true, true, false, [], ""],
    });

    await extensionState.current.nodeCreated(node);

    node.tagWidget.value = [
      { text: "plain", active: true, highlighted: false, strength: null },
      {
        text: "group a, group b",
        active: true,
        highlighted: true,
        strength: null,
        items: [
          { text: "group a", active: true, highlighted: true, strength: null },
          { text: "group b", active: false, highlighted: false, strength: null },
        ],
      },
    ];

    const serialized = node.tagWidget.serializeValue();

    expect(serialized).toEqual([
      { text: "plain", active: true, strength: null },
      {
        text: "group a, group b",
        active: true,
        strength: null,
        items: [
          { text: "group a", active: true, strength: null },
          { text: "group b", active: false, strength: null },
        ],
      },
    ]);
  });

  it("keeps strength text formatting while stripping highlighted state", async () => {
    const node = createNode({
      widgetsValues: [true, true, false, [], ""],
    });

    await extensionState.current.nodeCreated(node);

    node.tagWidget.value = [
      { text: "styled", active: true, highlighted: true, strength: 0.5 },
    ];

    const serialized = node.tagWidget.serializeValue();

    expect(serialized).toEqual([
      { text: "(styled:0.50)", active: true, strength: 0.5 },
    ]);
  });

  it("serializes restored values identically to the loaded save data", async () => {
    // Simulates a workflow saved by the current version (no highlighted keys):
    // load -> restore -> highlight recompute must not change serialized output.
    const savedTags = [
      {
        text: "masterpiece, best quality",
        active: true,
        strength: null,
        items: [
          { text: "masterpiece", active: true, strength: null },
          { text: "best quality", active: true, strength: null },
        ],
      },
    ];
    const node = createNode({
      widgetsValues: [true, true, false, savedTags, "masterpiece, best quality"],
    });

    await extensionState.current.nodeCreated(node);

    // Highlight recompute ran during nodeCreated (empty highlight set).
    const serialized = node.tagWidget.serializeValue();
    expect(serialized).toEqual(savedTags);
  });
});
