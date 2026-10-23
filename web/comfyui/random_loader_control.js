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
    // Old workflows (saved before the control_after_generate feature) carry a
    // shorter widgets_values array; the frontend's index-based restore then
    // shifts the old weight_dtype value into the hidden control widget and
    // silently resets weight_dtype to its default. Sanitization hands the
    // shifted value back to this widget.
    dtypeWidget: "weight_dtype",
  },
};

// Fallback set of valid control modes, used only when the widget's
// options.values list is unavailable. Combo targets additionally get
// 'increment-wrap' appended by ComfyUI.
const CONTROL_MODES = new Set([
  "fixed",
  "increment",
  "decrement",
  "randomize",
  "increment-wrap",
]);

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

/**
 * Migrate a widget value spelled with backslashes. Windows workflows saved
 * before the forward-slash paths fix carry "dir\model.safetensors" while the
 * combo list now offers "dir/model.safetensors"; rewrite the value to its
 * separator-normalized form when that form is a known model, so old workflows
 * keep their selection instead of resetting to the first model.
 */
function migrateWidgetValue(node, widget, names) {
  const value = widget.value;
  if (typeof value !== "string" || !value.includes("\\")) return;
  if (names.includes(value)) return;
  const normalized = value.replace(/\\/g, "/");
  if (!names.includes(normalized)) return;
  widget.value = normalized;
  // Fire the standard widget-changed hook so the frontend's error-clearing
  // chain drops the stale "value not in list" flag on the corrected widget.
  node?.onWidgetChanged?.(widget.name, normalized, value, widget);
}

/**
 * Promoted combo widgets on a subgraph boundary hold their own store-backed
 * copy of the interior widget's value, seeded from the workflow's serialized
 * widgets_values; migrating the interior loader widget never reaches them.
 * Apply the same separator migration to the boundary widgets: their value
 * setter writes through to the frontend's widget store, and firing the host
 * node's onWidgetChanged clears error entries keyed to the host (the frontend
 * flags the stale boundary value as a missing model on load).
 */
function migrateBoundaryWidgets(node, names) {
  for (const widget of node.widgets ?? []) {
    migrateWidgetValue(node, widget, names);
  }
}

function allPoolNames() {
  const names = [];
  for (const pool of poolCache.values()) {
    for (const model of pool) names.push(model.name);
  }
  return names;
}

function visitAllNodes(graph, callback) {
  // Subgraphs nest loader nodes; Subgraph extends LGraph, so the same .nodes
  // list recurses through every level.
  for (const node of graph?.nodes ?? []) {
    callback(node);
    if (node.subgraph) visitAllNodes(node.subgraph, callback);
  }
}

function migrateAllBoundaryWidgets() {
  const names = allPoolNames();
  visitAllNodes(app.graph, (node) => {
    if (node.subgraph) migrateBoundaryWidgets(node, names);
  });
}

function applyBaseModelFilter(node, config) {
  const modelWidget = node.widgets?.find(
    (widget) => widget.name === config.modelWidget
  );
  const baseModelWidget = node.widgets?.find(
    (widget) => widget.name === "base_model"
  );
  if (!modelWidget || !baseModelWidget) return;

  const pool = poolCache.get(config.subType) ?? [];

  // Migrate against the full pool: separator spelling is independent of the
  // base_model filter, and wired widgets skip the filter entirely below.
  migrateWidgetValue(node, modelWidget, pool.map((model) => model.name));

  const wired = node.inputs?.some(
    (input) =>
      input.widget?.name === config.modelWidget && input.link != null
  );
  if (wired) return;

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

function isControlWidget(widget) {
  if (!widget || widget.type !== "combo") return false;
  const values = widget.options?.values;
  return (
    Array.isArray(values) &&
    values.length > 0 &&
    values.every((value) => CONTROL_MODES.has(value))
  );
}

/**
 * Repair a control_after_generate widget that holds a value outside its option
 * list after loading an old workflow. The invalid value is a side effect of
 * the frontend's index-based widget restore: old workflows serialized fewer
 * widget values (no control slot), so the value that followed the model combo
 * (e.g. weight_dtype) shifted into the control widget while its real widget
 * was silently reset to its default. Hand the shifted value back, then reset
 * the control mode to 'fixed' (the node's declared default) so old workflows
 * keep loading deterministically and the invalid value stops persisting.
 */
export function sanitizeControlWidget(node, config) {
  const controlWidget = node.widgets?.find(
    (widget) =>
      // ComfyUI names the widget after the input option string when it is a
      // string (e.g. 'fixed'), so it cannot be located by name alone.
      widget.name === "control_after_generate" || isControlWidget(widget)
  );
  if (!controlWidget) return;

  const validModes = controlWidget.options?.values;
  if (Array.isArray(validModes)) {
    if (validModes.includes(controlWidget.value)) return;
  } else if (CONTROL_MODES.has(controlWidget.value)) {
    return;
  }

  if (config.dtypeWidget) {
    const dtypeWidget = node.widgets?.find(
      (widget) => widget.name === config.dtypeWidget
    );
    const dtypeOptions = dtypeWidget?.options?.values;
    if (
      dtypeWidget &&
      Array.isArray(dtypeOptions) &&
      // Only hand the value back when the real widget still sits at its
      // default; a non-default value means it was restored or edited
      // correctly and the control value is just stale workflow data.
      dtypeWidget.value === dtypeOptions[0] &&
      dtypeOptions.includes(controlWidget.value)
    ) {
      dtypeWidget.value = controlWidget.value;
    }
  }

  controlWidget.value = "fixed";
}

function applyToAllNodes() {
  const boundaryNames = allPoolNames();
  visitAllNodes(app.graph, (node) => {
    const config = NODE_CONFIGS[node.comfyClass];
    if (config) {
      sanitizeControlWidget(node, config);
      applyBaseModelFilter(node, config);
    }
    if (node.subgraph) migrateBoundaryWidgets(node, boundaryNames);
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

    // onConfigure fires after widget values are restored, catching pasted
    // nodes that never go through the graph-level configure hook.
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = onConfigure?.apply(this, arguments);
      sanitizeControlWidget(this, config);
      applyBaseModelFilter(this, config);
      // Pasting a whole subgraph node restores its boundary widget values
      // after the interior nodes configure; sweep once the paste settles.
      queueMicrotask(() => migrateAllBoundaryWidgets());
      return result;
    };
  },

  async refreshComboInNodes() {
    await refreshPoolCache();
    applyToAllNodes();
  },
});