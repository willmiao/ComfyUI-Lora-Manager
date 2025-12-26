/**
 * Frontend extension for LoraCycler node
 *
 * This handles trigger word updates for connected TriggerWordToggle nodes
 * when the Cycler node executes and selects a LoRA.
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import {
  getConnectedTriggerToggleNodes,
  getNodeReference,
  chainCallback,
} from "./utils.js";

// Store the last selected LoRA name for each node instance
const nodeSelectedLoras = new Map();

// Regex to extract LoRA name from syntax like <lora:name:strength> or <lora:name:strength:clip>
const LORA_SYNTAX_PATTERN = /<lora:([^:>]+):[^>]+>/;

/**
 * Update trigger words for connected TriggerWord Toggle nodes
 * @param {Object} node - The LoraCycler node
 * @param {Set} loraNames - Set of active LoRA names
 */
function updateConnectedTriggerWords(node, loraNames) {
  const connectedNodes = getConnectedTriggerToggleNodes(node);
  if (connectedNodes.length === 0) {
    return;
  }

  const nodeIds = connectedNodes
    .map((connectedNode) => getNodeReference(connectedNode))
    .filter((reference) => reference !== null);

  if (nodeIds.length === 0) {
    return;
  }

  fetch("/api/lm/loras/get_trigger_words", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lora_names: Array.from(loraNames),
      node_ids: nodeIds,
    }),
  }).catch((err) => console.error("Error fetching trigger words:", err));
}

/**
 * Extract LoRA name from the selected_lora output format
 * @param {string} selectedLora - String like "<lora:name:1.0>" or "<lora:name:0.8:0.6>"
 * @returns {string|null} - The LoRA name or null if not found
 */
function extractLoraName(selectedLora) {
  if (!selectedLora) {
    return null;
  }
  const match = selectedLora.match(LORA_SYNTAX_PATTERN);
  return match ? match[1] : null;
}

/**
 * Handle execution result for a Cycler node
 * @param {Object} node - The LoraCycler node
 * @param {Object} output - The execution output
 */
function handleExecutionOutput(node, output) {
  // The output array indices match RETURN_TYPES order:
  // 0: LORA_STACK, 1: trigger_words, 2: selected_lora, 3: total_count, 4: current_index
  const selectedLoraOutput = output?.selected_lora;

  if (!selectedLoraOutput || !selectedLoraOutput.length) {
    return;
  }

  // Get the selected_lora string (it's an array, take first element)
  const selectedLoraStr = Array.isArray(selectedLoraOutput)
    ? selectedLoraOutput[0]
    : selectedLoraOutput;

  const loraName = extractLoraName(selectedLoraStr);

  if (!loraName) {
    return;
  }

  // Check if this is different from the last selection
  const lastSelection = nodeSelectedLoras.get(node.id);
  if (lastSelection === loraName) {
    return;
  }

  nodeSelectedLoras.set(node.id, loraName);

  // Update connected TriggerWord Toggle nodes
  const loraNames = new Set([loraName]);
  updateConnectedTriggerWords(node, loraNames);
}

/**
 * Find a node by its unique ID across all graphs
 * @param {number|string} nodeId - The node ID to find
 * @returns {Object|null} - The node or null
 */
function findNodeById(nodeId) {
  const numericId = typeof nodeId === "string" ? parseInt(nodeId, 10) : nodeId;

  // Try the main graph first
  let node = app.graph?.getNodeById?.(numericId);
  if (node) {
    return node;
  }

  // Search subgraphs if needed
  if (app.graph?._subgraphs) {
    for (const subgraph of Object.values(app.graph._subgraphs)) {
      const graph = subgraph?.graph || subgraph?._graph || subgraph;
      if (graph?.getNodeById) {
        node = graph.getNodeById(numericId);
        if (node) {
          return node;
        }
      }
    }
  }

  return null;
}

app.registerExtension({
  name: "LoraManager.LoraCycler",

  async beforeRegisterNodeDef(nodeType, nodeData, app) {
    if (nodeType.comfyClass === "Lora Cycler (LoraManager)") {
      chainCallback(nodeType.prototype, "onNodeCreated", function () {
        // Enable widget serialization
        this.serialize_widgets = true;

        // Add optional lora_stack input
        this.addInput("lora_stack", "LORA_STACK", {
          shape: 7, // Optional input shape
        });

        // Store reference for callbacks
        const self = this;

        // Monitor mode changes to update trigger words when node is bypassed/enabled
        let _mode = this.mode;
        Object.defineProperty(this, "mode", {
          get() {
            return _mode;
          },
          set(value) {
            const oldValue = _mode;
            _mode = value;

            // When node becomes active, update trigger words if we have a selection
            const isNodeActive = value === undefined || value === 0 || value === 3;
            if (isNodeActive && oldValue !== value) {
              const lastSelection = nodeSelectedLoras.get(self.id);
              if (lastSelection) {
                updateConnectedTriggerWords(self, new Set([lastSelection]));
              }
            }
            // When node becomes inactive, clear trigger words
            else if (!isNodeActive && oldValue !== value) {
              updateConnectedTriggerWords(self, new Set());
            }
          },
        });

        // Listen for widget changes to provide immediate feedback where possible
        // For "fixed" mode with a specific index, we could potentially preview
        // but for random/increment modes, we can't know until execution
      });

      // Handle connection changes
      chainCallback(nodeType.prototype, "onConnectionsChange", function (
        type,
        index,
        connected,
        linkInfo
      ) {
        // When a new connection is made to trigger_words output (index 1)
        // try to update the connected node if we have a previous selection
        if (type === 2 && index === 1 && connected) {
          // Output connection to trigger_words
          const lastSelection = nodeSelectedLoras.get(this.id);
          if (lastSelection) {
            // Small delay to let the connection stabilize
            setTimeout(() => {
              updateConnectedTriggerWords(this, new Set([lastSelection]));
            }, 100);
          }
        }
      });
    }
  },

  async setup() {
    // Listen for execution events to capture node outputs
    api.addEventListener("executed", (event) => {
      const { node: nodeId, output } = event.detail || {};

      if (!nodeId || !output) {
        return;
      }

      // Find the node
      const node = findNodeById(nodeId);
      if (!node) {
        return;
      }

      // Check if this is a LoraCycler node
      if (node.comfyClass === "Lora Cycler (LoraManager)") {
        handleExecutionOutput(node, output);
      }
    });
  },
});
