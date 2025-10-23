import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { getAllGraphNodes, getNodeReference, getNodeFromGraph } from "./utils.js";

const LORA_NODE_CLASSES = new Set([
    "Lora Loader (LoraManager)",
    "Lora Stacker (LoraManager)",
    "WanVideo Lora Select (LoraManager)",
]);

const TARGET_WIDGET_NAMES = new Set(["ckpt_name", "unet_name"]);

app.registerExtension({
    name: "LoraManager.WorkflowRegistry",

    setup() {
        api.addEventListener("lora_registry_refresh", () => {
            this.refreshRegistry();
        });

        api.addEventListener("lm_widget_update", (event) => {
            this.applyWidgetUpdate(event?.detail ?? {});
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

                if (!supportsLora && !hasTargetWidget) {
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
                    capabilities: {
                        supports_lora: supportsLora,
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
        const widgetName = message?.widget_name;
        const value = message?.value;

        if (nodeId == null || !widgetName) {
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

        const widgetIndex = node.widgets.findIndex((widget) => widget?.name === widgetName);
        if (widgetIndex === -1) {
            console.warn(
                "LoRA Manager: target widget not found on node",
                widgetName,
                node
            );
            return;
        }

        const widget = node.widgets[widgetIndex];
        widget.value = value;

        if (Array.isArray(node.widgets_values) && node.widgets_values.length > widgetIndex) {
            node.widgets_values[widgetIndex] = value;
        }

        if (typeof widget.callback === "function") {
            try {
                widget.callback(value);
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
