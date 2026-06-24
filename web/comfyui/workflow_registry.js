import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { getAllGraphNodes, getNodeReference, getNodeFromGraph } from "./utils.js";
import { ensureLmStyles } from "./lm_styles_loader.js";

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
        ensureLmStyles();

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

        // ---- Visual cue: briefly highlight the updated widget ----
        this.flashWidget(node, targetWidget);
    },

    /**
     * Add a temporary visual highlight to a widget after its value is updated.
     * - Vue Nodes mode: change value text color on all non-button elements
     * - Canvas mode: define text_color on widget instance (value text only)
     * Highlight fades after 10 seconds or on hover (Vue mode only).
     */
    flashWidget(node, widget) {
        const FLASH_DURATION = 3000;
        const flashEnd = Date.now() + FLASH_DURATION;
        const nodeId = node.id;

        // Colors consistent with canvas mode
        const VALUE_COLOR = '#66B3FF';

        // Helper: find the widget row in the DOM (by label text matching widget name)
        const findRowEl = () => {
            const container = document.querySelector(`[data-node-id="${nodeId}"]`);
            if (!container) return null;
            const all = container.querySelectorAll('[data-testid="node-widget"]');
            for (const w of all) {
                const label = w.querySelector('[data-testid="widget-layout-field-label"]');
                if (label && label.textContent.trim() === widget.name) {
                    return w;
                }
            }
            return null;
        };

        // Helper: get label and ring elements from a widget row
        const getLabelAndRing = (row) => {
            if (!row) return { labelEl: null, ringEl: null };
            const labelEl = row.querySelector('[data-testid="widget-layout-field-label"]');
            const ringEl = labelEl?.nextElementSibling
                || row.querySelector('.flex-1.relative.min-w-0')
                || row.querySelector('.rounded-lg.transition-all')
                || null;
            return { labelEl, ringEl };
        };

        const applyFlash = (row) => {
            if (!row) return;
            const { ringEl } = getLabelAndRing(row);
            if (ringEl) {
                const innerRing = ringEl.querySelector('.rounded-lg.transition-all');
                if (innerRing) {
                    // Target value-displaying elements for all widget types:
                    // NumberWidget: spinbutton input
                    // ComboWidget: combobox button
                    // Text widgets (CLIPTextEncode, Prompt, etc.): textarea / text input
                    innerRing.querySelectorAll(
                        'input, textarea, [role="combobox"]'
                    ).forEach(el => {
                        el.style.color = VALUE_COLOR;
                    });
                }
            }
        };

        const removeFlash = (row) => {
            if (!row) return;
            const { ringEl } = getLabelAndRing(row);
            if (ringEl) {
                const innerRing = ringEl.querySelector('.rounded-lg.transition-all');
                if (innerRing) {
                    // Clear color from all inputs/textarea/combobox
                    innerRing.querySelectorAll(
                        'input, textarea, [role="combobox"]'
                    ).forEach(el => {
                        el.style.color = '';
                    });
                }
            }
        };

        // --- Try Vue Nodes mode first ---
        const nodeEl = document.querySelector(`[data-node-id="${nodeId}"]`);
        if (nodeEl) {
            // Apply immediately
            const initialRow = findRowEl();
            applyFlash(initialRow);

            // rAF loop: re-apply after Vue re-renders
            let rafId = null;
            const poll = () => {
                if (Date.now() >= flashEnd) {
                    const lastRow = findRowEl();
                    removeFlash(lastRow);
                    rafId = null;
                    return;
                }
                const currentRow = findRowEl();
                applyFlash(currentRow);
                rafId = requestAnimationFrame(poll);
            };
            rafId = requestAnimationFrame(poll);

            // Cleanup timeout
            const timeoutId = setTimeout(() => {
                if (rafId) cancelAnimationFrame(rafId);
                const lastRow = findRowEl();
                removeFlash(lastRow);
            }, FLASH_DURATION);

            // Hover dismissal via event delegation on node container
            const hoverHandler = (e) => {
                const row = findRowEl();
                if (row && row.contains(e.target)) {
                    clearTimeout(timeoutId);
                    if (rafId) cancelAnimationFrame(rafId);
                    removeFlash(row);
                    nodeEl.removeEventListener('mouseover', hoverHandler);
                }
            };
            nodeEl.addEventListener('mouseover', hoverHandler);

            return; // Vue mode done
        }

        // --- Canvas mode: change widget value text color via instance property shadowing ---
        // BaseWidget reads text_color (value) from prototype getter. Defining an own
        // property on the instance shadows the getter without monkey-patching.
        // Works for ALL widget types — only value text is changed, label is left alone.
        Object.defineProperty(widget, 'text_color', {
            value: VALUE_COLOR,
            writable: true,
            configurable: true,
        });

        if (typeof node.setDirtyCanvas === "function") {
            node.setDirtyCanvas(true);
        }

        // Track this widget so it gets restored alongside others on the same node
        if (!node._lmFlashedWidgets) node._lmFlashedWidgets = [];
        if (!node._lmFlashedWidgets.includes(widget)) {
            node._lmFlashedWidgets.push(widget);
        }

        // Single per-node timer that restores ALL flashed widgets at once.
        // Subsequent calls reset the timer but don't orphan previous widgets.
        if (node._lmFlashCleanup) {
            clearTimeout(node._lmFlashCleanup);
        }
        node._lmFlashCleanup = setTimeout(() => {
            for (const w of (node._lmFlashedWidgets || [])) {
                delete w.text_color;
                delete w.secondary_text_color;
            }
            delete node._lmFlashedWidgets;
            delete node._lmFlashCleanup;
            if (typeof node.setDirtyCanvas === "function") {
                node.setDirtyCanvas(true);
            }
        }, FLASH_DURATION);
    },
});
