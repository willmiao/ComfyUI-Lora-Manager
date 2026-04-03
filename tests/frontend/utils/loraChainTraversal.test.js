import { beforeEach, describe, expect, it, vi } from "vitest";

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

describe("LoRA chain traversal", () => {
  let collectActiveLorasFromChain;

  beforeEach(async () => {
    vi.resetModules();
    ({ collectActiveLorasFromChain } = await import(UTILS_MODULE));
  });

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

  it("aggregates active LoRAs through a combiner with multiple LORA_STACK inputs", () => {
    const randomizerA = {
      id: 1,
      comfyClass: "Lora Randomizer (LoraManager)",
      mode: 0,
      widgets: [
        {
          name: "loras",
          value: [
            { name: "Alpha", active: true },
            { name: "Ignored", active: false },
          ],
        },
      ],
      inputs: [],
      outputs: [],
    };
    const randomizerB = {
      id: 2,
      comfyClass: "Lora Randomizer (LoraManager)",
      mode: 0,
      widgets: [
        {
          name: "loras",
          value: [{ name: "Beta", active: true }],
        },
      ],
      inputs: [],
      outputs: [],
    };
    const combiner = {
      id: 3,
      comfyClass: "Lora Stack Combiner (LoraManager)",
      mode: 0,
      widgets: [],
      inputs: [
        { name: "lora_stack_a", type: "LORA_STACK", link: 11 },
        { name: "lora_stack_b", type: "LORA_STACK", link: 12 },
      ],
      outputs: [],
    };
    const loader = {
      id: 4,
      comfyClass: "Lora Loader (LoraManager)",
      mode: 0,
      widgets: [],
      inputs: [{ name: "lora_stack", type: "LORA_STACK", link: 13 }],
      outputs: [],
    };

    createGraph(
      [randomizerA, randomizerB, combiner, loader],
      {
        11: { origin_id: 1, target_id: 3 },
        12: { origin_id: 2, target_id: 3 },
        13: { origin_id: 3, target_id: 4 },
      }
    );

    const result = collectActiveLorasFromChain(loader);

    expect([...result]).toEqual(["Alpha", "Beta"]);
  });

  it("stops propagation when the combiner is inactive", () => {
    const randomizer = {
      id: 1,
      comfyClass: "Lora Randomizer (LoraManager)",
      mode: 0,
      widgets: [
        {
          name: "loras",
          value: [{ name: "Alpha", active: true }],
        },
      ],
      inputs: [],
      outputs: [],
    };
    const combiner = {
      id: 2,
      comfyClass: "Lora Stack Combiner (LoraManager)",
      mode: 2,
      widgets: [],
      inputs: [{ name: "lora_stack_a", type: "LORA_STACK", link: 21 }],
      outputs: [],
    };
    const loader = {
      id: 3,
      comfyClass: "Lora Loader (LoraManager)",
      mode: 0,
      widgets: [],
      inputs: [{ name: "lora_stack", type: "LORA_STACK", link: 22 }],
      outputs: [],
    };

    createGraph(
      [randomizer, combiner, loader],
      {
        21: { origin_id: 1, target_id: 2 },
        22: { origin_id: 2, target_id: 3 },
      }
    );

    const result = collectActiveLorasFromChain(loader);

    expect(result.size).toBe(0);
  });
});
