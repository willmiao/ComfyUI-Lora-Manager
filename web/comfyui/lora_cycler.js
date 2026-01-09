/**
 * Frontend extension for LoraCycler node
 *
 * This handles trigger word updates for connected TriggerWordToggle nodes
 * by calling the backend preview API when widget values change.
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import {
  getConnectedTriggerToggleNodes,
  getNodeReference,
  chainCallback,
} from "./utils.js";

// Store the last preview data for each node instance
const nodePreviewData = new Map();

// Debounce timer map for each node
const debounceTimers = new Map();

// Cache for base models list
let cachedBaseModels = null;
let baseModelsFetchPromise = null;

/**
 * Fetch available base models from the API
 * @returns {Promise<Array>} - Array of base model names
 */
async function fetchBaseModels() {
  // Return cached data if available
  if (cachedBaseModels) {
    return cachedBaseModels;
  }

  // Reuse existing fetch promise if in progress
  if (baseModelsFetchPromise) {
    return baseModelsFetchPromise;
  }

  baseModelsFetchPromise = (async () => {
    try {
      const response = await fetch("/api/lm/loras/base-models");
      if (response.ok) {
        const data = await response.json();
        if (data.success && data.base_models) {
          // Extract model names and sort
          cachedBaseModels = ["", ...data.base_models.map((m) => m.name || m).sort()];
          return cachedBaseModels;
        }
      }
    } catch (err) {
      console.error("Error fetching base models:", err);
    }
    return [""];
  })();

  return baseModelsFetchPromise;
}

/**
 * Get connected trigger toggle node references for API call
 * @param {Object} node - The LoraCycler node
 * @returns {Array} - Array of node references
 */
function getConnectedNodeReferences(node) {
  const connectedNodes = getConnectedTriggerToggleNodes(node);
  return connectedNodes
    .map((connectedNode) => getNodeReference(connectedNode))
    .filter((reference) => reference !== null);
}

/**
 * Gather widget values from the node
 * @param {Object} node - The LoraCycler node
 * @returns {Object} - Widget values
 */
function getWidgetValues(node) {
  const values = {
    selection_mode: "fixed",
    index: 0,
    seed: 0,
    folder_filter: "",
    base_model_filter: "",
    tag_filter: "",
    name_filter: "",
    first_trigger_word_only: false,
  };

  if (!node.widgets) return values;

  for (const widget of node.widgets) {
    if (widget.name === "selection_mode") values.selection_mode = widget.value;
    else if (widget.name === "index") values.index = widget.value;
    else if (widget.name === "seed") values.seed = widget.value;
    else if (widget.name === "folder_filter") values.folder_filter = widget.value || "";
    else if (widget.name === "base_model_filter") values.base_model_filter = widget.value || "";
    else if (widget.name === "tag_filter") values.tag_filter = widget.value || "";
    else if (widget.name === "name_filter") values.name_filter = widget.value || "";
    else if (widget.name === "first_trigger_word_only") values.first_trigger_word_only = widget.value || false;
  }

  return values;
}

/**
 * Call the backend preview API to get selected LoRA and update trigger words
 * @param {Object} node - The LoraCycler node
 */
async function updatePreview(node) {
  // Check if node is active (mode 0 for Always, mode 3 for On Trigger)
  const isNodeActive = node.mode === undefined || node.mode === 0 || node.mode === 3;

  // Get connected trigger toggle nodes
  const nodeIds = getConnectedNodeReferences(node);

  if (nodeIds.length === 0 && !isNodeActive) {
    return;
  }

  const widgetValues = getWidgetValues(node);

  try {
    const response = await fetch("/api/lm/loras/cycler_preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        folder_filter: widgetValues.folder_filter,
        base_model_filter: widgetValues.base_model_filter,
        tag_filter: widgetValues.tag_filter,
        name_filter: widgetValues.name_filter,
        selection_mode: widgetValues.selection_mode,
        index: widgetValues.index,
        seed: widgetValues.seed,
        unique_id: String(node.id),
        node_ids: nodeIds,
        first_trigger_word_only: widgetValues.first_trigger_word_only,
      }),
    });

    if (response.ok) {
      const data = await response.json();
      if (data.success) {
        nodePreviewData.set(node.id, {
          selectedLora: data.selected_lora,
          triggerWords: data.trigger_words,
          totalCount: data.total_count,
          selectedIndex: data.selected_index,
        });

        // Update the display widget to show the selected LoRA
        updateDisplayWidget(node, data);
      }
    }
  } catch (err) {
    console.error("Error fetching cycler preview:", err);
  }
}

/**
 * Update the display widget to show the currently selected LoRA
 * @param {Object} node - The LoraCycler node
 * @param {Object} data - Preview data from API
 */
function updateDisplayWidget(node, data) {
  if (!node.widgets) return;

  const displayWidget = node.widgets.find((w) => w.name === "next_lora_display");
  if (displayWidget) {
    if (data.total_count === 0) {
      displayWidget.value = "(no matching LoRAs)";
    } else {
      const loraName = data.selected_lora || "(none)";
      displayWidget.value = `[${data.selected_index + 1}/${data.total_count}] ${loraName}`;
    }
    // Force redraw
    if (node.graph) {
      node.setDirtyCanvas(true, true);
    }
  }
}

/**
 * Debounced version of updatePreview
 * @param {Object} node - The LoraCycler node
 * @param {number} delay - Debounce delay in ms
 */
function debouncedUpdatePreview(node, delay = 300) {
  const existingTimer = debounceTimers.get(node.id);
  if (existingTimer) {
    clearTimeout(existingTimer);
  }

  const timer = setTimeout(() => {
    updatePreview(node);
    debounceTimers.delete(node.id);
  }, delay);

  debounceTimers.set(node.id, timer);
}

/**
 * Clear trigger words from connected nodes when node is inactive
 * @param {Object} node - The LoraCycler node
 */
function clearTriggerWords(node) {
  const nodeIds = getConnectedNodeReferences(node);
  if (nodeIds.length === 0) return;

  fetch("/api/lm/loras/get_trigger_words", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lora_names: [],
      node_ids: nodeIds,
    }),
  }).catch((err) => console.error("Error clearing trigger words:", err));
}

app.registerExtension({
  name: "LoraManager.LoraCycler",

  async beforeRegisterNodeDef(nodeType, nodeData, app) {
    if (nodeType.comfyClass === "Lora Cycler (LoraManager)") {
      chainCallback(nodeType.prototype, "onNodeCreated", async function () {
        // Enable widget serialization
        this.serialize_widgets = true;

        // Store reference for callbacks
        const self = this;

        // Add a display widget to show the currently selected/next LoRA
        const displayWidget = this.addWidget(
          "text",
          "next_lora_display",
          "(loading...)",
          () => {}, // Read-only, no callback needed
          {
            serialize: false, // Don't save this widget
          }
        );
        // Make it appear read-only by moving to the top
        if (this.widgets && this.widgets.length > 1) {
          const idx = this.widgets.indexOf(displayWidget);
          if (idx > 0) {
            this.widgets.splice(idx, 1);
            this.widgets.unshift(displayWidget);
          }
        }

        // Find the base_model_filter widget and add a combo selector above it
        const baseModelFilterWidget = this.widgets?.find(
          (w) => w.name === "base_model_filter"
        );

        if (baseModelFilterWidget) {
          // Fetch base models and create a combo widget
          const baseModels = await fetchBaseModels();

          // Find the index of base_model_filter widget
          const widgetIndex = this.widgets.indexOf(baseModelFilterWidget);

          // Create a combo widget for base model selection
          const comboWidget = this.addWidget(
            "combo",
            "base_model_select",
            "",
            (value) => {
              // When a base model is selected from dropdown, update the filter widget
              baseModelFilterWidget.value = value;
              debouncedUpdatePreview(self);
            },
            {
              values: baseModels,
              serialize: false, // Don't save this widget - the filter text is what matters
            }
          );

          // Move the combo widget to be right before the base_model_filter
          if (widgetIndex >= 0) {
            const currentIndex = this.widgets.indexOf(comboWidget);
            if (currentIndex > widgetIndex) {
              this.widgets.splice(currentIndex, 1);
              this.widgets.splice(widgetIndex, 0, comboWidget);
            }
          }

          // Sync combo with existing filter value if any
          if (baseModelFilterWidget.value && baseModels.includes(baseModelFilterWidget.value)) {
            comboWidget.value = baseModelFilterWidget.value;
          }
        }

        // Setup widget callbacks for real-time preview updates
        if (this.widgets) {
          for (const widget of this.widgets) {
            // Skip the combo widget we just added (it already has a callback)
            if (widget.name === "base_model_select") continue;

            const originalCallback = widget.callback;

            widget.callback = function (value) {
              if (originalCallback) {
                originalCallback.call(this, value);
              }
              // Trigger preview update when widget value changes
              debouncedUpdatePreview(self);
            };
          }
        }

        // Monitor mode changes to update trigger words when node is bypassed/enabled
        let _mode = this.mode;
        Object.defineProperty(this, "mode", {
          get() {
            return _mode;
          },
          set(value) {
            const oldValue = _mode;
            _mode = value;

            // When node becomes active, update preview
            const isNodeActive = value === undefined || value === 0 || value === 3;
            if (isNodeActive && oldValue !== value) {
              updatePreview(self);
            }
            // When node becomes inactive, clear trigger words
            else if (!isNodeActive && oldValue !== value) {
              clearTriggerWords(self);
            }
          },
        });

        // Initial preview update after a short delay to let the graph settle
        setTimeout(() => {
          updatePreview(this);
        }, 500);
      });

      // Handle connection changes
      chainCallback(nodeType.prototype, "onConnectionsChange", function (
        type,
        index,
        connected,
        linkInfo
      ) {
        // When a new connection is made to trigger_words output (index 1)
        // update the preview to send trigger words to the new connection
        if (type === 2 && index === 1 && connected) {
          // Output connection to trigger_words
          setTimeout(() => {
            updatePreview(this);
          }, 100);
        }
      });
    }
  },

  async setup() {
    // Listen for execution events to update the counter state for increment/decrement
    api.addEventListener("executed", (event) => {
      const { node: nodeId, output } = event.detail || {};

      if (!nodeId || !output) {
        return;
      }

      // Find the node
      const numericId = typeof nodeId === "string" ? parseInt(nodeId, 10) : nodeId;
      let node = app.graph?.getNodeById?.(numericId);

      // Search subgraphs if needed
      if (!node && app.graph?._subgraphs) {
        for (const subgraph of Object.values(app.graph._subgraphs)) {
          const graph = subgraph?.graph || subgraph?._graph || subgraph;
          if (graph?.getNodeById) {
            node = graph.getNodeById(numericId);
            if (node) break;
          }
        }
      }

      if (!node) return;

      // Check if this is a LoraCycler node
      if (node.comfyClass === "Lora Cycler (LoraManager)") {
        // After execution, refresh the preview for increment/decrement modes
        // This ensures the preview reflects the new counter state
        const widgetValues = getWidgetValues(node);
        if (
          widgetValues.selection_mode === "increment" ||
          widgetValues.selection_mode === "decrement"
        ) {
          // Small delay to let the backend counter update
          setTimeout(() => {
            updatePreview(node);
          }, 200);
        }
      }
    });
  },
});
