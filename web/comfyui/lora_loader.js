import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import {
  LORA_ACTIVE_FILTERS_AUTOCOMPLETE_SETTING_ID,
  getLoraActiveFiltersAutocompletePreference,
  setLoraManagerSettingValue,
} from "./settings.js";
import { showToast } from "./utils.js";
import {
  collectActiveLorasFromChain,
  updateConnectedTriggerWords,
  chainCallback,
  mergeLoras,
  getAllGraphNodes,
  getNodeFromGraph,
  getWidgetByName,
  getWidgetSerializedValue,
} from "./utils.js";
import { applyLoraValuesToText, debounce } from "./lora_syntax_utils.js";

// Node classes whose "text" widget uses the loras autocomplete. Kept in sync
// with the broadcast-compatible classes in handleLoraCodeUpdate below.
const LORA_AUTOCOMPLETE_NODE_CLASSES = [
  "Lora Loader (LoraManager)",
  "Lora Stacker (LoraManager)",
  "WanVideo Lora Select (LoraManager)",
  "Create Hook LoRA (LoraManager)",
];

// Expose the active-filters search toggle in the node's right-click menu so
// users can discover the switch where the behavior actually happens, instead
// of only via the /activefilters and /noactivefilters slash commands. Mirrors
// the tag-autocomplete menu entry on Prompt (LoraManager) nodes.
function addActiveFiltersSearchMenuOption(nodeType) {
  const getExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
  nodeType.prototype.getExtraMenuOptions = function (_, options) {
    getExtraMenuOptions?.apply?.(this, arguments);

    options.push(null);

    const filtersSearchEnabled = getLoraActiveFiltersAutocompletePreference();
    options.push({
      content: filtersSearchEnabled
        ? "Active Filters Search: ON (/noactivefilters to disable)"
        : "Active Filters Search: OFF (/activefilters to enable)",
      callback: async () => {
        const newValue = !filtersSearchEnabled;
        try {
          const success = await setLoraManagerSettingValue(
            LORA_ACTIVE_FILTERS_AUTOCOMPLETE_SETTING_ID,
            newValue
          );
          if (!success) {
            throw new Error("settings API unavailable");
          }
          showToast({
            severity: newValue ? "success" : "secondary",
            summary: newValue
              ? "Active Filters Search Enabled"
              : "Active Filters Search Disabled",
            detail: newValue
              ? "LoRA autocomplete now respects the active filters of the LoRA Manager page. Type /noactivefilters in the LoRA field to disable."
              : "LoRA autocomplete searches the full library again. Type /activefilters in the LoRA field to re-enable.",
            life: 3000,
          });
        } catch (error) {
          console.error("[Lora Manager] Failed to toggle setting:", error);
          showToast({
            severity: "error",
            summary: "Error",
            detail: "Failed to toggle active filters search setting",
            life: 3000,
          });
        }
      },
    });
  };
}

app.registerExtension({
  name: "LoraManager.LoraLoader",

  setup() {
    // Add message handler to listen for messages from Python
    api.addEventListener("lora_code_update", (event) => {
      this.handleLoraCodeUpdate(event.detail || {});
    });
  },

  // Handle lora code updates from Python
  handleLoraCodeUpdate(message) {
    const nodeId = message?.node_id ?? message?.id;
    const graphId = message?.graph_id;
    const loraCode = message?.lora_code ?? "";
    const mode = message?.mode ?? "append";

    const numericNodeId =
      typeof nodeId === "string" ? Number(nodeId) : nodeId;

    // Handle broadcast mode (for Desktop/non-browser support)
    if (numericNodeId === -1) {
      // Find all compatible nodes in the current graph
      const compatibleClasses = new Set(LORA_AUTOCOMPLETE_NODE_CLASSES);
      const targetNodes = getAllGraphNodes(app.graph)
        .map(({ node }) => node)
        .filter((node) => compatibleClasses.has(node?.comfyClass));

      // Update each node found
      if (targetNodes.length > 0) {
        targetNodes.forEach((node) => {
          this.updateNodeLoraCode(node, loraCode, mode);
        });
        console.log(
          `Updated ${targetNodes.length} nodes in broadcast mode`
        );
      } else {
        console.warn(
          "No compatible LoRA nodes found in the workflow for broadcast update"
        );
      }

      return;
    }

    // Standard mode - update a specific node
    const node = getNodeFromGraph(graphId, numericNodeId);
    if (
      !node ||
      (node.comfyClass !== "Lora Loader (LoraManager)" &&
        node.comfyClass !== "Lora Stacker (LoraManager)" &&
        node.comfyClass !== "WanVideo Lora Select (LoraManager)" &&
        node.comfyClass !== "Create Hook LoRA (LoraManager)")
    ) {
      console.warn(
        "Node not found or not a compatible LoRA node:",
        graphId ?? "root",
        nodeId
      );
      return;
    }

    this.updateNodeLoraCode(node, loraCode, mode);
  },

  // Helper method to update a single node's lora code
  updateNodeLoraCode(node, loraCode, mode) {
    // Update the input widget with new lora code
    const inputWidget = node.inputWidget;
    if (!inputWidget) return;

    // Get the current lora code
    const currentValue = inputWidget.value || "";

    // Update based on mode (replace or append)
    if (mode === "replace") {
      inputWidget.value = loraCode;
    } else {
      // Append mode - add a space if the current value isn't empty
      inputWidget.value = currentValue.trim()
        ? `${currentValue.trim()} ${loraCode}`
        : loraCode;
    }

    // Trigger the callback to update the loras widget
    if (typeof inputWidget.callback === "function") {
      inputWidget.callback(inputWidget.value);
    }
  },

  async beforeRegisterNodeDef(nodeType, nodeData, app) {
    if (LORA_AUTOCOMPLETE_NODE_CLASSES.includes(nodeType.comfyClass)) {
      addActiveFiltersSearchMenuOption(nodeType);
    }

    if (nodeType.comfyClass == "Lora Loader (LoraManager)") {
      chainCallback(nodeType.prototype, "onNodeCreated", function () {
        // Enable widget serialization
        this.serialize_widgets = true;

        this.addInput("clip", "CLIP", {
          shape: 7,
        });

        this.addInput("lora_stack", "LORA_STACK", {
          shape: 7, // 7 is the shape of the optional input
        });

        // Add flags to prevent callback loops
        let isUpdating = false;
        let isSyncingInput = false;

        // Mechanism: Property descriptor to listen for mode changes
        const self = this;
        let _mode = this.mode;
        Object.defineProperty(this, 'mode', {
          get() {
            return _mode;
          },
          set(value) {
            const oldValue = _mode;
            _mode = value;

            // Trigger mode change handler
            if (self.onModeChange) {
              self.onModeChange(value, oldValue);
            }

            console.log(`[Lora Loader] Node mode changed from ${oldValue} to ${value}`);
          }
        });

        // Define the mode change handler
        this.onModeChange = function(newMode, oldMode) {
          console.log(`Lora Loader node mode changed: from ${oldMode} to ${newMode}`);

          // Update connected trigger word toggle nodes when mode changes
          const allActiveLoraNames = collectActiveLorasFromChain(self);
          updateConnectedTriggerWords(self, allActiveLoraNames);
        };

        // Get the text input widget (AUTOCOMPLETE_TEXT_LORAS type, created by Vue widgets)
        const inputWidget = getWidgetByName(this, "text");
        if (!inputWidget) {
          console.warn("LoRA Manager: text widget not found for Lora Loader");
          return;
        }
        this.inputWidget = inputWidget;

        const scheduleInputSync = debounce((lorasValue) => {
          if (isSyncingInput) {
            return;
          }

          isSyncingInput = true;
          isUpdating = true;

          try {
            const nextText = applyLoraValuesToText(
              inputWidget.value,
              lorasValue
            );

            if (inputWidget.value !== nextText) {
              inputWidget.value = nextText;
            }
          } finally {
            isUpdating = false;
            isSyncingInput = false;
          }
        });

        // The "loras" widget is declared in INPUT_TYPES (LORAS type) and
        // created by the LoraManager.LorasWidget extension; take it over here.
        const lorasWidget = getWidgetByName(this, "loras");
        if (!lorasWidget) {
          console.warn("LoRA Manager: loras widget not found for Lora Loader");
          return;
        }
        this.lorasWidget = lorasWidget;

        lorasWidget.callback = (value) => {
          // Prevent recursive calls
          if (isUpdating) return;
          isUpdating = true;

          try {
            // Collect all active loras from this node and its input chain
            const allActiveLoraNames = collectActiveLorasFromChain(this);

            // Update trigger words for connected toggle nodes with the aggregated lora names
            updateConnectedTriggerWords(this, allActiveLoraNames);
          } finally {
            isUpdating = false;
          }

          scheduleInputSync(value);
        };

        // Set up callback for the text input widget to trigger merge logic
        inputWidget.callback = (value) => {
          if (isUpdating) return;
          isUpdating = true;

          try {
            const currentLoras = this.lorasWidget.value || [];
            const mergedLoras = mergeLoras(value, currentLoras);

            this.lorasWidget.value = mergedLoras;

            const allActiveLoraNames = collectActiveLorasFromChain(this);
            updateConnectedTriggerWords(this, allActiveLoraNames);
          } finally {
            isUpdating = false;
          }
        };
      });
    }
  },

  async loadedGraphNode(node) {
    if (node.comfyClass == "Lora Loader (LoraManager)") {
      // Restore saved value if exists
      let existingLoras = [];
      if (node.widgets_values && node.widgets_values.length > 0) {
        const savedValue = getWidgetSerializedValue(node, "loras");
        existingLoras = savedValue || [];
      }
      // Merge the loras data
      const inputWidget = node.inputWidget || getWidgetByName(node, "text");
      if (!inputWidget) {
        console.warn("LoRA Manager: text widget not found while restoring Lora Loader");
        return;
      }
      const mergedLoras = mergeLoras(inputWidget.value, existingLoras);
      node.lorasWidget.value = mergedLoras;
    }
  },
});
