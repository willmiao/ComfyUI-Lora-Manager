import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { getAllGraphNodes, getNodeReference, getNodeFromGraph, chainCallback, getLinkFromGraph } from "./utils.js";
import { ensureLmStyles } from "./lm_styles_loader.js";

const DEBOUNCE_DELAY = 500;

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

/**
 * Parse a hex color (#RGB or #RRGGBB) into an [r, g, b] tuple.
 */
function hexToRgb(hex) {
    let h = hex.slice(1);
    if (h.length === 3) {
        h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    }
    const n = parseInt(h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/**
 * Linearly interpolate between two [r, g, b] tuples.
 */
function lerpColor(from, to, t) {
    return [
        Math.round(from[0] + (to[0] - from[0]) * t),
        Math.round(from[1] + (to[1] - from[1]) * t),
        Math.round(from[2] + (to[2] - from[2]) * t),
    ];
}

/**
 * Run a short rAF-driven color fade on a canvas-drawn widget's text_color.
 * Sets text_color to an interpolated rgb() string each frame. Returns a
 * cancel function.
 *
 * @param widget   the widget instance (must have a configurable text_color)
 * @param fromColor  [r, g, b] start color
 * @param toColor    [r, g, b] end color
 * @param duration  fade duration in ms
 * @returns {function} cancel function — stops the fade immediately.
 */
function fadeWidgetTextColor(widget, fromColor, toColor, duration) {
    let rafId = null;
    const start = performance.now();
    const tick = () => {
        const elapsed = performance.now() - start;
        const t = Math.min(1, elapsed / duration);
        // Ease-out cubic for a smooth deceleration.
        const eased = 1 - Math.pow(1 - t, 3);
        const [r, g, b] = lerpColor(fromColor, toColor, eased);
        Object.defineProperty(widget, 'text_color', {
            value: `rgb(${r},${g},${b})`,
            writable: true,
            configurable: true,
        });
        if (t < 1) {
            rafId = requestAnimationFrame(tick);
        }
    };
    rafId = requestAnimationFrame(tick);
    return () => { if (rafId) cancelAnimationFrame(rafId); };
}

// ---------------------------------------------------------------------------
// Primitive node helpers
// ---------------------------------------------------------------------------

/**
 * Set of node type names that represent Primitive value nodes.
 * Includes both the dynamic PrimitiveNode (created by double-clicking
 * a widget input) and the static typed primitives from the node library.
 */
const PRIMITIVE_NODE_TYPES = new Set([
    "PrimitiveNode",          // dynamic (double-click a widget input)
    "PrimitiveInt",
    "PrimitiveFloat",
    "PrimitiveString",
    "PrimitiveBoolean",
    "PrimitiveStringMultiline",
]);

/**
 * Return true when `node` is any flavour of Primitive node.
 * @param {Object} node - LiteGraph node instance
 * @returns {boolean}
 */
function isPrimitiveNodeType(node) {
    return PRIMITIVE_NODE_TYPES.has(node?.type);
}

/**
 * Find the 0-based input slot index whose widget name matches `widgetName`.
 * Returns -1 when no matching input is found.
 *
 * Matching strategy (in order):
 *  1. `input.widget?.name === widgetName` — direct widget ref (preferred)
 *  2. `input.name === widgetName`        — fallback by slot name
 *
 * @param {Object} node       - LiteGraph node instance
 * @param {string} widgetName
 * @returns {number}
 */
function findInputSlotForWidget(node, widgetName) {
    if (!node || !Array.isArray(node.inputs)) {
        return -1;
    }
    return node.inputs.findIndex(
        (inp) => inp?.widget?.name === widgetName || inp?.name === widgetName
    );
}

/**
 * If the input slot that backs `widgetName` on `node` is connected to a
 * Primitive node, return that Primitive node. Otherwise return null.
 *
 * This is the key bridge for the "send gen params → Primitive" flow:
 * when a KSampler widget (e.g. "steps") has an incoming wire from a
 * Primitive node, we want to update the Primitive's value instead of the
 * KSampler widget, because ComfyUI's execution engine reads from the
 * connected input, not the widget.
 *
 * @param {Object} node       - the target node (e.g. KSampler)
 * @param {string} widgetName - e.g. "steps", "cfg", "seed"
 * @returns {Object|null}     - the connected Primitive node, or null
 */
function tryResolvePrimitiveConnection(node, widgetName) {
    const slotIndex = findInputSlotForWidget(node, widgetName);
    if (slotIndex === -1) return null;

    const input = node.inputs[slotIndex];
    if (input?.link == null) return null;

    const link = getLinkFromGraph(node.graph, input.link);
    if (!link) return null;

    const originNode = node.graph?.getNodeById?.(link.origin_id);
    if (!originNode) return null;

    return isPrimitiveNodeType(originNode) ? originNode : null;
}

app.registerExtension({
    name: "LoraManager.WorkflowRegistry",

    setup() {
        ensureLmStyles();
        this._log("extension initialized, clientId=%s", api.clientId ?? api.initialClientId ?? "(pending)");

        api.addEventListener("lora_registry_refresh", () => {
            this.refreshRegistry(true);
        });

        api.addEventListener("lm_widget_update", (event) => {
            this.applyWidgetUpdate(event?.detail ?? {});
        });

        window.addEventListener("lm_marker_changed", () => {
            this.refreshRegistry();
        });

        this._hookGraphChanges();
    },

    async afterConfigureGraph(_missingNodeTypes, _app) {
        this._log("afterConfigureGraph: workflow loaded (%s missing types)", _missingNodeTypes?.length ?? 0);
        await this.refreshRegistry();
    },

    _hookGraphChanges() {
        const graph = app.graph;
        if (!graph) {
            this._log("app.graph not available, skipping proactive hooks");
            return;
        }

        let hooksInstalled = 0;

        const scheduleRefresh = (source) => {
            if (this._debounceTimer != null) {
                clearTimeout(this._debounceTimer);
            }
            this._debounceTimer = setTimeout(() => {
                this._debounceTimer = null;
                this.refreshRegistry();
            }, DEBOUNCE_DELAY);
        };

        try {
            chainCallback(graph, "onNodeAdded", () => scheduleRefresh("onNodeAdded"));
            chainCallback(graph, "onNodeRemoved", () => scheduleRefresh("onNodeRemoved"));
            hooksInstalled += 2;
        } catch (e) {
            this._log("failed to chain LiteGraph hooks: %s", e.message);
        }

        if (typeof api.addEventListener === "function") {
            try {
                api.addEventListener("graphChanged", () => scheduleRefresh("graphChanged"));
                hooksInstalled += 1;
            } catch (_e) {
                // graphChanged may not be available on older ComfyUI versions
            }
        }

        this._log("%s proactive hooks installed on graph", hooksInstalled);
    },

    _log(format, ...args) {
        const ts = new Date().toISOString().slice(11, 23);
        let msg = format;
        for (const arg of args) {
            msg = msg.replace(/%s/g, String(arg));
        }
        console.debug(`[LM:Registry ${ts}] ${msg}`);
    },

    async refreshRegistry(force = false) {
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

            const clientId = api.clientId ?? api.initialClientId ?? "";

            // Content-based dedup: skip POST if identical to last sent payload,
            // unless forced (e.g. responding to a lora_registry_refresh WS message
            // where the backend explicitly requests a re-registration).
            const fingerprint = JSON.stringify(
                workflowNodes.map(n => `${n.graph_id}:${n.node_id}|${n.marker_role ?? ""}|${n.mode ?? 0}`).sort()
            );
            if (!force && fingerprint === this._lastFingerprint) {
                return;
            }
            this._lastFingerprint = fingerprint;

            const response = await fetch("/api/lm/register-nodes", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    nodes: workflowNodes,
                    client_id: clientId,
                }),
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

        // ---- Redirect to connected Primitive node when present ----
        // When a widget input (e.g. "steps", "cfg", "seed" on KSampler)
        // is wired to a Primitive node, the Primitive's value overrides
        // the widget value during execution.  Update the Primitive
        // directly so the change actually takes effect.
        if (widgetName) {
            const primitiveNode = tryResolvePrimitiveConnection(node, widgetName);
            if (primitiveNode) {
                const primWidget = primitiveNode.widgets?.[0];
                if (primWidget) {
                    let primNewValue = value;
                    if (mode === "append") {
                        const sep =
                            primWidget.value && primWidget.value.length > 0
                                ? " "
                                : "";
                        primNewValue = primWidget.value + sep + value;
                    }
                    primWidget.value = primNewValue;
                    if (
                        Array.isArray(primitiveNode.widgets_values) &&
                        primitiveNode.widgets_values.length > 0
                    ) {
                        primitiveNode.widgets_values[0] = primNewValue;
                    }
                    if (typeof primWidget.callback === "function") {
                        try {
                            primWidget.callback(primNewValue);
                        } catch (callbackError) {
                            console.error(
                                "LoRA Manager: primitive widget callback failed",
                                callbackError
                            );
                        }
                    }
                    if (typeof primitiveNode.setDirtyCanvas === "function") {
                        primitiveNode.setDirtyCanvas(true);
                    }
                    if (typeof app.graph?.setDirtyCanvas === "function") {
                        app.graph.setDirtyCanvas(true, true);
                    }
                    this.flashWidget(primitiveNode, primWidget);
                    console.debug(
                        "LoRA Manager: redirected widget update to Primitive node %s (id=%d) ← %s = %o",
                        primitiveNode.type,
                        primitiveNode.id,
                        widgetName,
                        primNewValue
                    );
                    return;
                }
            }
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
     *
     * Both rendering modes shift the value text color to the LM brand accent
     * (#4299E0) with a fade-in/fade-out, then restore it after FLASH_DURATION
     * (3s) or on hover:
     *  - Vue Nodes mode: add a `.lm-flash` class to the widget row. CSS
     *    `transition: color 0.25s` handles fade-in/out. A MutationObserver
     *    re-applies the class if Vue re-renders the row during the flash.
     *  - Canvas mode: DOM widgets (customtext/autocomplete) use inline
     *    `transition` for fade; canvas-drawn widgets (combo/number/toggle) use
     *    a short rAF color interpolation for fade-in (250ms) and fade-out
     *    (400ms). A low-frequency poll checks hover dismissal via
     *    app.canvas.getWidgetAtCursor().
     */
    flashWidget(node, widget) {
        const FLASH_DURATION = 3000;
        const FADE_IN_MS = 250;
        const VALUE_COLOR = '#4299E0'; // LM brand accent — consistent with selection/border/drop-indicator
        const nodeId = node.id;

        // ---- Vue Nodes mode: CSS class for value text color ----
        const nodeEl = document.querySelector(`[data-node-id="${nodeId}"]`);
        if (nodeEl) {
            this._flashVueWidget(nodeEl, widget, node, {
                FLASH_DURATION, VALUE_COLOR,
            });
            return;
        }

        // ---- Canvas mode ----
        this._flashCanvasWidget(node, widget, {
            FLASH_DURATION, FADE_IN_MS, VALUE_COLOR,
        });
    },

    /**
     * Vue/DOM flash: add `.lm-flash` class to the widget row for the value text
     * color shift. Re-applies on re-render via MutationObserver. Removes on
     * timeout / hover.
     */
    _flashVueWidget(nodeEl, widget, graphNode, { FLASH_DURATION, VALUE_COLOR }) {
        const FLASH_CLASS = 'lm-flash';

        // Find the widget row in the DOM. Vue renders widget rows as
        // [data-testid="node-widget"] elements whose order matches node.widgets[].
        // Match strategy (in priority order):
        //  1. By label text via [data-testid="widget-layout-field-label"] (combo/number/toggle)
        //  2. By <label> text (CLIPTextEncode customtext has a bare <label>)
        //  3. By widget index — graph node.widgets[i] ↔ Nth DOM row (text widgets
        //     like Prompt LM have no label at all, so index is the only stable match)
        const widgetIndex = Array.isArray(graphNode?.widgets)
            ? graphNode.widgets.indexOf(widget)
            : -1;

        const findRowEl = () => {
            const rows = nodeEl.querySelectorAll('[data-testid="node-widget"]');
            // Strategy 1: data-testid label
            for (const r of rows) {
                const label = r.querySelector('[data-testid="widget-layout-field-label"]');
                if (label && label.textContent.trim() === widget.name) {
                    return r;
                }
            }
            // Strategy 2: bare <label> element
            for (const r of rows) {
                const label = r.querySelector('label');
                if (label && label.textContent.trim() === widget.name) {
                    return r;
                }
            }
            // Strategy 3: index match
            if (widgetIndex >= 0 && widgetIndex < rows.length) {
                return rows[widgetIndex];
            }
            return null;
        };

        let cleanedUp = false;
        const cleanupFns = [];

        const cleanup = () => {
            if (cleanedUp) return;
            cleanedUp = true;
            for (const fn of cleanupFns) {
                try { fn(); } catch (e) { /* ignore */ }
            }
            // Remove .lm-flash to trigger the CSS color fade-out. Keep
            // .lm-flash-host (which carries the transition rule) until the
            // fade-out completes, then remove it.
            const row = findRowEl();
            if (row) {
                row.classList.remove(FLASH_CLASS);
                // Remove the host class after the transition completes.
                setTimeout(() => {
                    const r = findRowEl();
                    if (r) r.classList.remove('lm-flash-host');
                }, 300);
            }
        };

        // Initial application
        const apply = () => {
            const row = findRowEl();
            if (row && !row.classList.contains(FLASH_CLASS)) {
                // Restart the animation by toggling the class off-on.
                row.classList.remove(FLASH_CLASS);
                // Force reflow so the animation restarts.
                void row.offsetWidth;
                row.classList.add('lm-flash-host');
                row.classList.add(FLASH_CLASS);
            }
        };
        apply();

        // Re-apply if Vue re-renders and drops the class.
        const observer = new MutationObserver(() => {
            if (cleanedUp) return;
            apply();
        });
        observer.observe(nodeEl, { childList: true, subtree: true });
        cleanupFns.push(() => observer.disconnect());

        // Hard timeout: remove the class after FLASH_DURATION.
        const timeoutId = setTimeout(cleanup, FLASH_DURATION + 100);
        cleanupFns.push(() => clearTimeout(timeoutId));

        // Hover dismissal: clear the flash when the user mouses over the row.
        const onHover = (e) => {
            const row = findRowEl();
            if (row && row.contains(e.target)) {
                cleanup();
            }
        };
        nodeEl.addEventListener('mouseover', onHover);
        cleanupFns.push(() => nodeEl.removeEventListener('mouseover', onHover));
    },

    /**
     * Canvas flash: set text_color (canvas-drawn widgets) and inline color
     * (DOM widgets). Canvas-drawn widgets get a rAF-driven color fade-in/out;
     * DOM widgets use CSS transition. A low-frequency poll checks hover
     * dismissal via app.canvas.getWidgetAtCursor().
     */
    _flashCanvasWidget(node, widget, { FLASH_DURATION, FADE_IN_MS, VALUE_COLOR }) {
        const FADE_OUT_MS = 400;
        const FADE_OUT_START = FLASH_DURATION - FADE_OUT_MS;
        const DEFAULT_RGB = hexToRgb('#DDD'); // LiteGraph WIDGET_TEXT_COLOR
        const FLASH_RGB = hexToRgb(VALUE_COLOR);

        /**
         * Check whether a widget is a DOM-based widget (customtext / autocomplete)
         * that renders a real <textarea>/<input> element rather than being
         * canvas-drawn. Evaluated per-widget so batch cleanup handles each
         * widget correctly regardless of when it was added to the batch.
         */
        const isDomWidget = (w) =>
            (w.inputEl && (w.inputEl.tagName === 'TEXTAREA' || w.inputEl.tagName === 'INPUT'))
            || !!w.element?.querySelector?.('textarea, input');

        /**
         * Get the DOM element for a DOM-based widget.
         */
        const getDomEl = (w) =>
            (w.inputEl && (w.inputEl.tagName === 'TEXTAREA' || w.inputEl.tagName === 'INPUT'))
                ? w.inputEl
                : w.element?.querySelector?.('textarea, input') ?? null;

        // --- Track fade-out cancellers per widget so batch cleanup can stop
        //     any in-progress fade for ALL widgets in the batch, not just the
        //     latest one. ---
        if (!node._lmFadeCancels) node._lmFadeCancels = {};

        // --- DOM widget color (customtext / autocomplete text) ---
        // CSS transition handles both fade-in and fade-out automatically.
        if (isDomWidget(widget)) {
            const domEl = getDomEl(widget);
            if (domEl) {
                domEl.style.transition = `color ${FADE_IN_MS}ms ease`;
                domEl.style.color = VALUE_COLOR;
            }
        }

        // --- Canvas-drawn widget: kick off fade-in via rAF ---
        if (!isDomWidget(widget)) {
            // Set immediately to start (rAF will refine from first frame).
            Object.defineProperty(widget, 'text_color', {
                value: VALUE_COLOR,
                writable: true,
                configurable: true,
            });
            const cancel = fadeWidgetTextColor(widget, DEFAULT_RGB, FLASH_RGB, FADE_IN_MS);
            node._lmFadeCancels[widget.name] = cancel;
        }

        // --- Track flashed widgets for batch cleanup ---
        if (!node._lmFlashedWidgets) node._lmFlashedWidgets = [];
        if (!node._lmFlashedWidgets.includes(widget)) {
            node._lmFlashedWidgets.push(widget);
        }

        // --- Track fade-out scheduling per widget ---
        if (!node._lmFadeOutTimers) node._lmFadeOutTimers = {};

        if (typeof node.setDirtyCanvas === 'function') {
            node.setDirtyCanvas(true);
        }

        // --- Poll for hover dismissal ---
        let pollId = null;
        let cleanedUp = false;

        const cleanup = () => {
            if (cleanedUp) return;
            cleanedUp = true;
            if (pollId) clearInterval(pollId);
            pollId = null;

            for (const w of (node._lmFlashedWidgets || [])) {
                // Cancel any pending fade-out timer for this widget
                if (node._lmFadeOutTimers?.[w.name]) {
                    clearTimeout(node._lmFadeOutTimers[w.name]);
                    delete node._lmFadeOutTimers[w.name];
                }
                // Cancel any in-progress fade-in/out rAF for this widget
                if (node._lmFadeCancels?.[w.name]) {
                    node._lmFadeCancels[w.name]();
                    delete node._lmFadeCancels[w.name];
                }
                delete w.text_color;
                delete w.secondary_text_color;
                // Clear DOM widget inline color first (transition plays the
                // fade-out), then remove the transition property after it
                // completes. Keeping transition until then is essential.
                if (isDomWidget(w)) {
                    const el = getDomEl(w);
                    if (el) {
                        el.style.color = '';
                        // Remove the transition property after the fade completes.
                        setTimeout(() => {
                            if (el) el.style.transition = '';
                        }, 300);
                    }
                }
            }
            delete node._lmFlashedWidgets;
            delete node._lmFadeOutTimers;
            delete node._lmFadeCancels;
            delete node._lmFlashCleanup;
            if (typeof node.setDirtyCanvas === 'function') {
                node.setDirtyCanvas(true);
            }
        };

        // Schedule fade-out for canvas-drawn widgets only (DOM widgets fade
        // automatically when we clear the inline color in cleanup).
        if (!isDomWidget(widget)) {
            // Clear any previous fade-out timer for this widget
            if (node._lmFadeOutTimers[widget.name]) {
                clearTimeout(node._lmFadeOutTimers[widget.name]);
            }
            node._lmFadeOutTimers[widget.name] = setTimeout(() => {
                if (cleanedUp) return;
                const cancel = fadeWidgetTextColor(widget, FLASH_RGB, DEFAULT_RGB, FADE_OUT_MS);
                node._lmFadeCancels[widget.name] = cancel;
                delete node._lmFadeOutTimers[widget.name];
            }, FADE_OUT_START);
        }

        // Low-frequency poll (~100ms) for hover dismissal.
        const checkHover = () => {
            if (cleanedUp) return;
            const canvas = window.app?.canvas;
            if (canvas) {
                const hovered = canvas.getWidgetAtCursor?.();
                if (hovered && node._lmFlashedWidgets?.includes(hovered)) {
                    cleanup();
                    return;
                }
            }
        };
        pollId = setInterval(checkHover, 100);

        // Hard timeout fallback.
        if (node._lmFlashCleanup) clearTimeout(node._lmFlashCleanup);
        node._lmFlashCleanup = setTimeout(cleanup, FLASH_DURATION + 50);
    },
});
