import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { getAllGraphNodes, getNodeReference, getNodeFromGraph } from "./utils.js";

const LORA_NODE_CLASSES = new Set([
    "Lora Loader (LoraManager)",
    "Lora Stacker (LoraManager)",
    "WanVideo Lora Select (LoraManager)",
]);

const TARGET_WIDGET_NAMES = new Set(["ckpt_name", "unet_name"]);

// Node classes whose "text" widget is a prompt text input (not LoRA syntax, notes, etc.)
const TEXT_CAPABLE_CLASSES = new Set([
    "Prompt (LoraManager)",
    "Text (LoraManager)",
    "CLIPTextEncode",
]);

app.registerExtension({
    name: "LoraManager.WorkflowRegistry",

    setup() {
        api.addEventListener("lora_registry_refresh", () => {
            this.refreshRegistry();
        });

        api.addEventListener("lm_widget_update", (event) => {
            this.applyWidgetUpdate(event?.detail ?? {});
        });

        // React to marker changes from the Node Marker extension
        window.addEventListener("lm_marker_changed", () => {
            this.refreshRegistry();
        });
    },

    async refreshRegistry() {
        try {
            const workflowNodes = [];
            const nodeEntries = getAllGraphNodes(app.graph);

            for (const { graph, node } of nodeEntries) {
                if (!node) {
                    continue;
                }

                const widgetNames = Array.isArray(node.widgets)
                    ? node.widgets
                          .map((widget) => widget?.name)
                          .filter((name) => typeof name === "string" && name.length > 0)
                    : [];

                const supportsLora = LORA_NODE_CLASSES.has(node.comfyClass);
                const hasTargetWidget = widgetNames.some((name) => TARGET_WIDGET_NAMES.has(name));
                const hasTextWidget = TEXT_CAPABLE_CLASSES.has(node.comfyClass);
                const markerRole = node.properties?.lm_marker_role ?? null;

                // Skip nodes with no relevant capability UNLESS they are marked
                if (!supportsLora && !hasTargetWidget && !hasTextWidget && !markerRole) {
                    continue;
                }

                const reference = getNodeReference(node);
                if (!reference) {
                    continue;
                }

                const graphName =
                    typeof graph?.name === "string" && graph.name.trim() ? graph.name : null;

                workflowNodes.push({
                    node_id: reference.node_id,
                    graph_id: reference.graph_id,
                    graph_name: graphName,
                    bgcolor: node.bgcolor ?? node.color ?? null,
                    title: node.title || node.comfyClass,
                    type: node.comfyClass,
                    comfy_class: node.comfyClass,
                    mode: node.mode,
                    marker_role: markerRole,
                    capabilities: {
                        supports_lora: supportsLora,
                        has_text_widget: hasTextWidget,
                        widget_names: widgetNames,
                    },
                });
            }

            const response = await fetch("/api/lm/register-nodes", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ nodes: workflowNodes }),
            });

            if (!response.ok) {
                console.warn("LoRA Manager: failed to register workflow nodes", response.statusText);
            } else {
                console.debug(
                    `LoRA Manager: registered ${workflowNodes.length} workflow nodes`
                );
            }
        } catch (error) {
            console.error("LoRA Manager: error refreshing workflow registry", error);
        }
    },

    applyWidgetUpdate(message) {
        const nodeId = message?.node_id ?? message?.id;
        const graphId = message?.graph_id;
        const action = message?.action;
        const widgetName = message?.widget_name;
        const value = message?.value;
        const mode = message?.mode ?? "replace";

        if (nodeId == null || (!action && !widgetName)) {
            console.warn("LoRA Manager: invalid widget update payload", message);
            return;
        }

        const node = getNodeFromGraph(graphId, nodeId);
        if (!node) {
            console.warn(
                "LoRA Manager: target node not found for widget update",
                graphId ?? "root",
                nodeId
            );
            return;
        }

        if (!Array.isArray(node.widgets)) {
            console.warn("LoRA Manager: node does not expose widgets", node);
            return;
        }

        // ---- Resolve target widget ----
        let targetWidget = null;

        if (action === "inject_text") {
            // Find the first text-capable widget by type.
            // Normalise to lowercase for case-insensitive matching.
            const TEXT_TYPES = new Set(["string", "customtext"]);
            targetWidget = node.widgets.find((w) => {
                const t = typeof w?.type === "string" ? w.type.toLowerCase() : "";
                if (TEXT_TYPES.has(t)) return true;
                // Broad fallback for unknown composite types.
                if (t.includes("string")) {
                    return true;
                }
                return false;
            });
            if (!targetWidget) {
                // Last resort: pick the first widget that is not a hidden/internal type
                targetWidget = node.widgets.find((w) => w?.name && !w.name.startsWith("_"));
                if (!targetWidget) {
                    console.warn(
                        "LoRA Manager: no suitable widget for inject_text on node",
                        node.id
                    );
                    return;
                }
            }
        } else if (widgetName) {
            // Legacy: find widget by name
            targetWidget = node.widgets.find((w) => w?.name === widgetName);
            if (!targetWidget) {
                console.warn(
                    "LoRA Manager: target widget not found on node",
                    widgetName,
                    node
                );
                return;
            }
        } else {
            console.warn("LoRA Manager: no action or widget_name in payload", message);
            return;
        }

        // ---- Update widget value ----
        const widgetIndex = node.widgets.indexOf(targetWidget);
        let newValue = value;

        if (mode === "append") {
            const separator =
                targetWidget.value && targetWidget.value.length > 0 ? " " : "";
            newValue = targetWidget.value + separator + value;
        }

        targetWidget.value = newValue;

        if (
            Array.isArray(node.widgets_values) &&
            widgetIndex >= 0 &&
            node.widgets_values.length > widgetIndex
        ) {
            node.widgets_values[widgetIndex] = newValue;
        }

        if (typeof targetWidget.callback === "function") {
            try {
                targetWidget.callback(newValue);
            } catch (callbackError) {
                console.error("LoRA Manager: widget callback failed", callbackError);
            }
        }

        if (typeof node.setDirtyCanvas === "function") {
            node.setDirtyCanvas(true);
        }

        if (typeof app.graph?.setDirtyCanvas === "function") {
            app.graph.setDirtyCanvas(true, true);
        }
    },
});
