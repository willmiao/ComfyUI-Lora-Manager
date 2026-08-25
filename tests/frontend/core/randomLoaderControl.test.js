import { describe, it, expect, beforeEach, vi } from "vitest";

const state = vi.hoisted(() => {
  const APP_MODULE = new URL("../../../scripts/app.js", import.meta.url).pathname;
  const API_MODULE = new URL("../../../scripts/api.js", import.meta.url).pathname;
  return {
    APP_MODULE,
    API_MODULE,
    graph: { onConfigure: null, nodes: [] },
    registerExtension: vi.fn(),
    fetchApi: vi.fn(),
  };
});

vi.mock(state.APP_MODULE, () => ({
  app: {
    registerExtension: state.registerExtension,
    graph: state.graph,
  },
}));

vi.mock(state.API_MODULE, () => ({
  api: {
    fetchApi: state.fetchApi,
  },
}));

const { sanitizeControlWidget } = await import(
  "../../../web/comfyui/random_loader_control.js"
);

const CONTROL_VALUES = [
  "fixed",
  "increment",
  "decrement",
  "randomize",
  "increment-wrap",
];
const DTYPE_VALUES = ["default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"];

function makeUnetNode(overrides = {}) {
  return {
    comfyClass: "Unet Loader (LoraManager)",
    widgets: [
      {
        name: "unet_name",
        type: "combo",
        value: "model.safetensors",
        options: { values: ["model.safetensors"] },
      },
      {
        // Real ComfyUI names the control widget after the string option
        // (e.g. 'fixed'), not 'control_after_generate'.
        name: "fixed",
        type: "combo",
        value: "fixed",
        options: { values: CONTROL_VALUES },
      },
      { name: "control_filter_list", type: "string", value: "", options: {} },
      {
        name: "weight_dtype",
        type: "combo",
        value: "default",
        options: { values: DTYPE_VALUES },
      },
      { name: "base_model", type: "combo", value: "Any", options: { values: ["Any"] } },
    ],
    ...overrides,
  };
}

function makeCheckpointNode(overrides = {}) {
  return {
    comfyClass: "Checkpoint Loader (LoraManager)",
    widgets: [
      {
        name: "ckpt_name",
        type: "combo",
        value: "model.safetensors",
        options: { values: ["model.safetensors"] },
      },
      {
        // Real ComfyUI names the control widget after the string option
        // (e.g. 'fixed'), not 'control_after_generate'.
        name: "fixed",
        type: "combo",
        value: "fixed",
        options: { values: CONTROL_VALUES },
      },
      { name: "control_filter_list", type: "string", value: "", options: {} },
      { name: "base_model", type: "combo", value: "Any", options: { values: ["Any"] } },
    ],
    ...overrides,
  };
}

function controlWidget(node) {
  return node.widgets.find(
    (widget) =>
      widget.name === "control_after_generate" ||
      (widget.type === "combo" &&
        Array.isArray(widget.options?.values) &&
        widget.options.values.length > 0 &&
        widget.options.values.every((v) => CONTROL_VALUES.includes(v)))
  );
}

function dtypeWidget(node) {
  return node.widgets.find((widget) => widget.name === "weight_dtype");
}

beforeEach(() => {
  state.graph.onConfigure = null;
  state.graph.nodes = [];
  state.graph.__loraManagerConfigureHooked = false;
  state.fetchApi.mockReset();
  state.fetchApi.mockResolvedValue({
    ok: true,
    json: async () => ({
      items: [{ name: "model.safetensors", base_model: "Any" }],
    }),
  });
});

describe("sanitizeControlWidget", () => {
  it("hands the shifted weight_dtype value back and resets control to fixed", () => {
    const node = makeUnetNode();
    controlWidget(node).value = "fp8_e4m3fn";
    dtypeWidget(node).value = "default";

    sanitizeControlWidget(node, {
      modelWidget: "unet_name",
      subType: "diffusion_model",
      dtypeWidget: "weight_dtype",
    });

    expect(dtypeWidget(node).value).toBe("fp8_e4m3fn");
    expect(controlWidget(node).value).toBe("fixed");
  });

  it("resets control when the shifted value is the dtype default itself", () => {
    const node = makeUnetNode();
    controlWidget(node).value = "default";
    dtypeWidget(node).value = "default";

    sanitizeControlWidget(node, {
      modelWidget: "unet_name",
      subType: "diffusion_model",
      dtypeWidget: "weight_dtype",
    });

    expect(dtypeWidget(node).value).toBe("default");
    expect(controlWidget(node).value).toBe("fixed");
  });

  it("leaves valid control modes untouched", () => {
    const node = makeUnetNode();
    controlWidget(node).value = "randomize";
    dtypeWidget(node).value = "fp8_e4m3fn";

    sanitizeControlWidget(node, {
      modelWidget: "unet_name",
      subType: "diffusion_model",
      dtypeWidget: "weight_dtype",
    });

    expect(controlWidget(node).value).toBe("randomize");
    expect(dtypeWidget(node).value).toBe("fp8_e4m3fn");
  });

  it("does not overwrite a weight_dtype that is not at its default", () => {
    const node = makeUnetNode();
    controlWidget(node).value = "fp8_e4m3fn";
    dtypeWidget(node).value = "fp8_e5m2";

    sanitizeControlWidget(node, {
      modelWidget: "unet_name",
      subType: "diffusion_model",
      dtypeWidget: "weight_dtype",
    });

    expect(dtypeWidget(node).value).toBe("fp8_e5m2");
    expect(controlWidget(node).value).toBe("fixed");
  });

  it("only resets the control mode for nodes without a dtype widget", () => {
    const node = makeCheckpointNode();
    controlWidget(node).value = "default";

    sanitizeControlWidget(node, {
      modelWidget: "ckpt_name",
      subType: "checkpoint",
    });

    expect(controlWidget(node).value).toBe("fixed");
  });

  it("is a no-op when the node has no control widget", () => {
    const node = makeUnetNode();
    node.widgets = node.widgets.filter(
      (widget) => widget.name !== "control_after_generate"
    );

    expect(() =>
      sanitizeControlWidget(node, {
        modelWidget: "unet_name",
        subType: "diffusion_model",
        dtypeWidget: "weight_dtype",
      })
    ).not.toThrow();
  });

  it("falls back to the known control modes when options.values is missing", () => {
    const node = makeUnetNode();
    const control = controlWidget(node);
    // Standard ComfyUI name, so the widget is found by name while its
    // options.values is gone (exercises the CONTROL_MODES fallback).
    control.name = "control_after_generate";
    control.value = "randomize";
    control.options = {};

    sanitizeControlWidget(node, {
      modelWidget: "unet_name",
      subType: "diffusion_model",
      dtypeWidget: "weight_dtype",
    });

    expect(controlWidget(node).value).toBe("randomize");
  });
});

describe("extension graph configure hook", () => {
  it("sanitizes loader nodes after graph configure", async () => {
    const extension = state.registerExtension.mock.calls.map(
      (call) => call[0]
    )[0];
    await extension.setup();

    const node = makeUnetNode();
    controlWidget(node).value = "fp8_e4m3fn";
    dtypeWidget(node).value = "default";
    state.graph.nodes = [node];

    const nodeType = { comfyClass: "Unet Loader (LoraManager)", prototype: {} };
    extension.beforeRegisterNodeDef(nodeType, {});
    nodeType.prototype.onAdded.call({ graph: state.graph });

    state.graph.onConfigure({});

    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(controlWidget(node).value).toBe("fixed");
    expect(dtypeWidget(node).value).toBe("fp8_e4m3fn");
  });
});