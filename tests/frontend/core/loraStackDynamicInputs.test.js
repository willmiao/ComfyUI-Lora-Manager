import { beforeEach, describe, expect, it, vi } from "vitest";

const { APP_MODULE, EXTENSION_MODULE, appMock, registeredExtensions } =
  vi.hoisted(() => {
    const registeredExtensions = [];
    const appMock = {
      configuringGraph: false,
      registerExtension: (ext) => registeredExtensions.push(ext),
    };
    return {
      APP_MODULE: new URL("../../../scripts/app.js", import.meta.url).pathname,
      EXTENSION_MODULE: new URL(
        "../../../web/comfyui/lora_stack_dynamic_inputs.js",
        import.meta.url
      ).pathname,
      appMock,
      registeredExtensions,
    };
  });

vi.mock(APP_MODULE, () => ({
  app: appMock,
}));

describe("Lora Stack Combiner dynamic inputs", () => {
  let extension;

  beforeEach(async () => {
    vi.resetModules();
    registeredExtensions.length = 0;
    appMock.configuringGraph = false;
    await import(EXTENSION_MODULE);
    extension = registeredExtensions.find(
      (ext) => ext.name === "Comfy.LoraManager.LoraStackCombiner"
    );
    expect(extension).toBeDefined();
  });

  function createNodeType() {
    const nodeType = { prototype: {} };
    extension.beforeRegisterNodeDef(
      nodeType,
      { name: "Lora Stack Combiner (LoraManager)" },
      appMock
    );
    return nodeType;
  }

  function createNode(inputs = []) {
    const node = {
      comfyClass: "Lora Stack Combiner (LoraManager)",
      inputs: inputs.map((name) => ({ name, type: "LORA_STACK" })),
      addInput: vi.fn(function (name, type, opts) {
        this.inputs.push({ name, type, ...opts });
      }),
      removeInput: vi.fn(function (index) {
        this.inputs.splice(index, 1);
      }),
    };
    return node;
  }

  function makeLinkInfo() {
    return { id: 999, origin_id: 1, target_id: 2 };
  }

  it("adds a third input when the last slot gets connected", () => {
    const nodeType = createNodeType();
    const node = createNode(["lora_stack1", "lora_stack2"]);
    node.onConnectionsChange = nodeType.prototype.onConnectionsChange;

    node.onConnectionsChange(1, 1, true, makeLinkInfo());

    expect(node.inputs.map((input) => input.name)).toEqual([
      "lora_stack1",
      "lora_stack2",
      "lora_stack3",
    ]);
  });

  it("does not add an input when a non-last slot gets connected", () => {
    const nodeType = createNodeType();
    const node = createNode(["lora_stack1", "lora_stack2", "lora_stack3"]);
    node.onConnectionsChange = nodeType.prototype.onConnectionsChange;

    node.onConnectionsChange(1, 0, true, makeLinkInfo());

    expect(node.inputs.map((input) => input.name)).toEqual([
      "lora_stack1",
      "lora_stack2",
      "lora_stack3",
    ]);
  });

  it("removes a disconnected middle slot and renumbers", () => {
    // Simulates a real LiteGraph disconnect event: it fires only for slots that
    // had a link, and input.link has already been cleared before the event fires.
    const nodeType = createNodeType();
    const node = createNode(["lora_stack1", "lora_stack2", "lora_stack3"]);
    node.inputs[0].link = 11;
    node.inputs[1].link = null; // slot 2 was just disconnected
    node.inputs[2].link = 13;
    node.onConnectionsChange = nodeType.prototype.onConnectionsChange;

    node.onConnectionsChange(1, 1, false, makeLinkInfo());

    expect(node.inputs.map((input) => input.name)).toEqual([
      "lora_stack1",
      "lora_stack2",
    ]);
  });

  it("keeps the last slot when it is disconnected", () => {
    const nodeType = createNodeType();
    const node = createNode(["lora_stack1", "lora_stack2", "lora_stack3"]);
    node.inputs[0].link = 11;
    node.inputs[1].link = 12;
    node.inputs[2].link = null; // last slot was just disconnected
    node.onConnectionsChange = nodeType.prototype.onConnectionsChange;

    node.onConnectionsChange(1, 2, false, makeLinkInfo());

    expect(node.inputs.map((input) => input.name)).toEqual([
      "lora_stack1",
      "lora_stack2",
      "lora_stack3",
    ]);
    expect(node.removeInput).not.toHaveBeenCalled();
  });

  it("keeps at least two inputs when disconnecting", () => {
    const nodeType = createNodeType();
    const node = createNode(["lora_stack1", "lora_stack2"]);
    node.inputs[0].link = 11;
    node.inputs[1].link = null; // slot 2 was just disconnected
    node.onConnectionsChange = nodeType.prototype.onConnectionsChange;

    node.onConnectionsChange(1, 1, false, makeLinkInfo());

    expect(node.inputs.map((input) => input.name)).toEqual([
      "lora_stack1",
      "lora_stack2",
    ]);
    expect(node.removeInput).not.toHaveBeenCalled();
  });

  it("does nothing while the graph is being configured", () => {
    appMock.configuringGraph = true;
    const nodeType = createNodeType();
    const node = createNode(["lora_stack1", "lora_stack2"]);
    node.onConnectionsChange = nodeType.prototype.onConnectionsChange;

    node.onConnectionsChange(1, 1, true, makeLinkInfo());

    expect(node.inputs.map((input) => input.name)).toEqual([
      "lora_stack1",
      "lora_stack2",
    ]);
    expect(node.addInput).not.toHaveBeenCalled();
  });

  it("leaves legacy lora_stack_a/b inputs untouched", () => {
    const nodeType = createNodeType();
    const node = createNode(["lora_stack_a", "lora_stack_b"]);
    node.onConnectionsChange = nodeType.prototype.onConnectionsChange;

    node.onConnectionsChange(1, 0, true, makeLinkInfo());

    expect(node.inputs.map((input) => input.name)).toEqual([
      "lora_stack_a",
      "lora_stack_b",
    ]);
    expect(node.addInput).not.toHaveBeenCalled();
  });

  it("ensures two numbered inputs exist on creation", () => {
    const node = createNode([]);
    extension.nodeCreated(node, {});

    expect(node.inputs.map((input) => input.name)).toEqual([
      "lora_stack1",
      "lora_stack2",
    ]);
  });

  it("does not add numbered inputs to legacy workflows", () => {
    const node = createNode(["lora_stack_a", "lora_stack_b"]);
    extension.nodeCreated(node, {});

    expect(node.inputs.map((input) => input.name)).toEqual([
      "lora_stack_a",
      "lora_stack_b",
    ]);
  });
});
