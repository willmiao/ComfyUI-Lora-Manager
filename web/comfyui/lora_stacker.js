import { app } from "../../scripts/app.js";
import {
  getActiveLorasFromNode,
  collectActiveLorasFromChain,
  updateConnectedTriggerWords,
  updateDownstreamLoaders,
  chainCallback,
  mergeLoras,
  setupInputWidgetWithAutocomplete,
  getLinkFromGraph,
  getNodeKey,
} from "./utils.js";
import { addLorasWidget } from "./loras_widget.js";
import { applyLoraValuesToText, debounce } from "./lora_syntax_utils.js";
import { applySelectionHighlight } from "./trigger_word_highlight.js";

app.registerExtension({
  name: "LoraManager.LoraStacker",

  async beforeRegisterNodeDef(nodeType, nodeData, app) {
    if (nodeType.comfyClass === "Lora Stacker (LoraManager)") {
      chainCallback(nodeType.prototype, "onNodeCreated", async function () {
        // Enable widget serialization
        this.serialize_widgets = true;

        this.addInput("lora_stack", "LORA_STACK", {
          shape: 7, // 7 is the shape of the optional input
        });

        // Add flags to prevent callback loops
        let isUpdating = false;
        let isSyncingInput = false;

        // Mechanism 3: Property descriptor to listen for mode changes
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
          }
        });

        // Define the mode change handler
        this.onModeChange = function(newMode, oldMode) {
          // Update connected trigger word toggle nodes and downstream loader trigger word toggle nodes
          // when mode changes, similar to when loras change
          const isNodeActive = newMode === 0 || newMode === 3; // Active when mode is Always (0) or On Trigger (3)
          const activeLoraNames = isNodeActive ? getActiveLorasFromNode(self) : new Set();
          updateConnectedTriggerWords(self, activeLoraNames);
          updateDownstreamLoaders(self);
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

        const result = addLorasWidget(
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
              // Update this stacker's direct trigger toggles with its own active loras
              // Only if the stacker node itself is active (mode 0 for Always, mode 3 for On Trigger)
              const isNodeActive = this.mode === undefined || this.mode === 0 || this.mode === 3;
              const activeLoraNames = new Set();
              if (isNodeActive) {
                value.forEach((lora) => {
                  if (lora.active) {
                    activeLoraNames.add(lora.name);
                  }
                });
              }
              updateConnectedTriggerWords(this, activeLoraNames);

              // Find all Lora Loader nodes in the chain that might need updates
              updateDownstreamLoaders(this);
            } finally {
              isUpdating = false;
            }

            scheduleInputSync(value);
        });

        this.lorasWidget = result.widget;

        // Wrap the callback with autocomplete setup
        const originalCallback = (value) => {
          if (isUpdating) return;
          isUpdating = true;

          try {
            const currentLoras = this.lorasWidget.value || [];
            const mergedLoras = mergeLoras(value, currentLoras);

            this.lorasWidget.value = mergedLoras;

            // Update this stacker's direct trigger toggles with its own active loras
            // Only if the stacker node itself is active (mode 0 for Always, mode 3 for On Trigger)
            const isNodeActive = this.mode === undefined || this.mode === 0 || this.mode === 3;
            const activeLoraNames = isNodeActive ? getActiveLorasFromNode(this) : new Set();
            updateConnectedTriggerWords(this, activeLoraNames);

            // Find all Lora Loader nodes in the chain that might need updates
            updateDownstreamLoaders(this);
          } finally {
            isUpdating = false;
          }
        };
      });
    }
  },
  async loadedGraphNode(node) {
    if (node.comfyClass == "Lora Stacker (LoraManager)") {
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

      const inputWidget = node.inputWidget || node.widgets[0];
      if (inputWidget && !node.autocomplete) {
        const { setupInputWidgetWithAutocomplete } = await import("./utils.js");
        const modelType = "loras";
        const autocompleteOptions = {
          maxItems: 20,
          minChars: 1,
          debounceDelay: 200,
        };
        inputWidget.callback = setupInputWidgetWithAutocomplete(node, inputWidget, inputWidget.callback, modelType, autocompleteOptions);
      }
    }
  },
});
