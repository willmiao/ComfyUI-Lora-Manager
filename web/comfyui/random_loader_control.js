import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_CONFIGS = {
  "Checkpoint Loader (LoraManager)": {
    modelWidget: "ckpt_name",
    subType: "checkpoint",
  },
  "Unet Loader (LoraManager)": {
    modelWidget: "unet_name",
    subType: "diffusion_model",
  },
};

const poolCache = new Map();

async function fetchPool(subType) {
  try {
    const response = await api.fetchApi(
      `/api/lm/checkpoints/loader-pool?sub_type=${encodeURIComponent(subType)}`
    );
    if (!response.ok) return [];
    const data = await response.json();
    return Array.isArray(data.items) ? data.items : [];
  } catch (error) {
    console.error("LoRA Manager: failed to fetch loader pool", error);
    return [];
  }
}

async function refreshPoolCache() {
  const subTypes = new Set(Object.values(NODE_CONFIGS).map((c) => c.subType));
  await Promise.all(
    [...subTypes].map(async (subType) => {
      poolCache.set(subType, await fetchPool(subType));
    })
  );
}

function applyBaseModelFilter(node, config) {
  const modelWidget = node.widgets?.find(
    (widget) => widget.name === config.modelWidget
  );
  const baseModelWidget = node.widgets?.find(
    (widget) => widget.name === "base_model"
  );
  if (!modelWidget || !baseModelWidget) return;

  const wired = node.inputs?.some(
    (input) =>
      input.widget?.name === config.modelWidget && input.link != null
  );
  if (wired) return;

  const pool = poolCache.get(config.subType) ?? [];
  const filter = baseModelWidget.value;
  const filtered =
    filter === "Any"
      ? pool
      : pool.filter((model) => model.base_model === filter);
  const names = filtered.map((model) => model.name);

  modelWidget.options.values = names;
  if (!names.includes(modelWidget.value)) {
    modelWidget.value = names[0];
  }
}

function applyToAllNodes() {
  app.graph?.nodes?.forEach((node) => {
    const config = NODE_CONFIGS[node.comfyClass];
    if (config) applyBaseModelFilter(node, config);
  });
}

function ensureGraphConfigureHook(graph) {
  if (!graph || graph.__loraManagerConfigureHooked) return;
  graph.__loraManagerConfigureHooked = true;

  const originalConfigure = graph.onConfigure;
  graph.onConfigure = function (data) {
    const result = originalConfigure?.call(this, data);
    // Workflow reload restores widget values after onNodeCreated fires, so the
    // per-node hook runs too early; re-apply the filter once the whole graph
    // has been configured.
    setTimeout(() => applyToAllNodes(), 0);
    return result;
  };
}

app.registerExtension({
  name: "LoraManager.RandomLoaderControl",

  async setup() {
    await refreshPoolCache();
  },

  beforeRegisterNodeDef(nodeType, nodeData) {
    const config = NODE_CONFIGS[nodeType.comfyClass];
    if (!config) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);

      const baseModelWidget = this.widgets?.find(
        (widget) => widget.name === "base_model"
      );
      if (baseModelWidget) {
        const originalCallback = baseModelWidget.callback;
        baseModelWidget.callback = (value, canvas, node, pos, event) => {
          applyBaseModelFilter(node ?? this, config);
          return originalCallback?.call(this, value, canvas, node, pos, event);
        };
      }

      applyBaseModelFilter(this, config);
      return result;
    };

    // onNodeCreated fires inside LGraph.createNode, before the node is added to
    // a graph (this.graph is null there), so the graph-level configure hook
    // must be installed from onAdded, where the graph reference is available.
    const onAdded = nodeType.prototype.onAdded;
    nodeType.prototype.onAdded = function () {
      const result = onAdded?.apply(this, arguments);
      ensureGraphConfigureHook(this.graph);
      return result;
    };
  },

  async refreshComboInNodes() {
    await refreshPoolCache();
    applyToAllNodes();
  },
});