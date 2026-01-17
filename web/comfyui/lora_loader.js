import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import {
  collectActiveLorasFromChain,
  updateConnectedTriggerWords,
  chainCallback,
  mergeLoras,
  setupInputWidgetWithAutocomplete,
  getAllGraphNodes,
  getNodeFromGraph,
} from "./utils.js";
import { addLorasWidget } from "./loras_widget.js";
import { applyLoraValuesToText, debounce } from "./lora_syntax_utils.js";
import { applySelectionHighlight } from "./trigger_word_highlight.js";

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
      // Find all Lora Loader nodes in the current graph
      const loraLoaderNodes = getAllGraphNodes(app.graph)
        .map(({ node }) => node)
        .filter((node) => node?.comfyClass === "Lora Loader (LoraManager)");

      // Update each Lora Loader node found
      if (loraLoaderNodes.length > 0) {
        loraLoaderNodes.forEach((node) => {
          this.updateNodeLoraCode(node, loraCode, mode);
        });
        console.log(
          `Updated ${loraLoaderNodes.length} Lora Loader nodes in broadcast mode`
        );
      } else {
        console.warn(
          "No Lora Loader nodes found in the workflow for broadcast update"
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
        node.comfyClass !== "WanVideo Lora Select (LoraManager)")
    ) {
      console.warn(
        "Node not found or not a LoraLoader:",
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

        const inputWidget = this.widgets[0];
        inputWidget.options.getMaxHeight = () => 100;
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

        // Get the widget object directly from the returned object
        this.lorasWidget = addLorasWidget(
          this,
          "loras",
          {
            onSelectionChange: (selection) =>
              applySelectionHighlight(this, selection),
          },
          (value) => {
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
          }
        ).widget;

        const originalCallback = (value) => {
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

        // Setup input widget with autocomplete
        inputWidget.callback = setupInputWidgetWithAutocomplete(
          this,
          inputWidget,
          originalCallback
        );
      });
    }
  },

  async loadedGraphNode(node) {
    if (node.comfyClass == "Lora Loader (LoraManager)") {
      // Restore saved value if exists
      let existingLoras = [];
      if (node.widgets_values && node.widgets_values.length > 0) {
        // 0 for input widget, 1 for loras widget
        const savedValue = node.widgets_values[1];
        existingLoras = savedValue || [];
      }
      // Merge the loras data
      const mergedLoras = mergeLoras(node.widgets[0].value, existingLoras);
      node.lorasWidget.value = mergedLoras;

      // Initialize autocomplete after DOM is fully rendered
      const inputWidget = node.inputWidget || node.widgets[0];
      if (inputWidget && !node.autocomplete) {
        const { setupInputWidgetWithAutocomplete } = await import("./utils.js");
        const modelType = "loras";
        const autocompleteOptions = {
          maxItems: 20,
          minChars: 1,
          debounceDelay: 200,
        };
        // Fix: Assign the enhanced callback to replace the original
        inputWidget.callback = setupInputWidgetWithAutocomplete(node, inputWidget, inputWidget.callback, modelType, autocompleteOptions);

        // Eager initialization: trigger callback after short delay to ensure DOM is ready
        setTimeout(() => {
          if (!node.autocomplete && inputWidget.callback) {
            inputWidget.callback(inputWidget.value);
          }
        }, 100);
      }
    }
  },
});
