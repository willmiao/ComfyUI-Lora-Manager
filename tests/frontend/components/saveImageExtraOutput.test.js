import { beforeEach, describe, expect, it, vi } from "vitest";

const { APP_MODULE, UTILS_MODULE, TARGET_MODULE } = vi.hoisted(() => ({
  APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
  UTILS_MODULE: new URL("../../../web/comfyui/utils.js", import.meta.url).pathname,
  TARGET_MODULE: new URL(
    "../../../web/comfyui/save_image_extra_output.js",
    import.meta.url
  ).pathname,
}));

vi.mock(APP_MODULE, () => ({
  app: {
    graph: {},
    registerExtension: vi.fn(),
  },
}));

vi.mock(UTILS_MODULE, () => ({
  chainCallback: (proto, name, fn) => {
    const existing = proto[name];
    proto[name] = function (...args) {
      existing?.apply(this, args);
      fn.apply(this, args);
    };
  },
  getAllGraphNodes: vi.fn(() => []),
  getWidgetByName: (node, name) => node.widgets?.find((w) => w.name === name),
}));

describe("SaveImageExtraOutput filename_prefix serialization", () => {
  let app;
  let utils;
  let extension;

  beforeEach(async () => {
    vi.resetModules();
    await import(TARGET_MODULE);
    ({ app } = await import(APP_MODULE));
    utils = await import(UTILS_MODULE);
    extension = app.registerExtension.mock.calls[0][0];
  });

  async function createSaveNode(prefixValue) {
    const nodeType = { prototype: {} };
    await extension.beforeRegisterNodeDef(nodeType, {
      name: "Save Image (LoraManager)",
    });

    const node = {
      widgets: [{ name: "filename_prefix", value: prefixValue }],
    };
    nodeType.prototype.onNodeCreated.call(node);
    return node.widgets[0];
  }

  it("passes %date:...% through unchanged so the backend resolves it at save time", async () => {
    const widget = await createSaveNode("MOSS/%date:yy-MM-dd_hh-mm-ss%");

    expect(widget.serializeValue()).toBe("MOSS/%date:yy-MM-dd_hh-mm-ss%");
  });

  it("passes date formats containing dots through without treating them as node placeholders", async () => {
    const widget = await createSaveNode("MOSS/%date:yyyy.M.d%");

    expect(widget.serializeValue()).toBe("MOSS/%date:yyyy.M.d%");
  });

  it("still resolves %NodeTitle.WidgetName% placeholders from the graph", async () => {
    utils.getAllGraphNodes.mockReturnValue([
      {
        node: {
          title: "KSampler",
          properties: {},
          widgets: [{ name: "seed", value: 12345 }],
        },
      },
    ]);

    const widget = await createSaveNode("gen_%KSampler.seed%_%date:yyyy%");

    expect(widget.serializeValue()).toBe("gen_12345_%date:yyyy%");
  });

  it("leaves backend-only patterns like %seed% untouched", async () => {
    const widget = await createSaveNode("out_%seed%");
    vi.spyOn(console, "warn").mockImplementation(() => {});

    expect(widget.serializeValue()).toBe("out_%seed%");
  });
});
