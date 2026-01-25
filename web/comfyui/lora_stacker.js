import { app } from "../../scripts/app.js";
import {
  getActiveLorasFromNode,
  updateConnectedTriggerWords,
  updateDownstreamLoaders,
  chainCallback,
  mergeLoras,
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

        // Get the text input widget (AUTOCOMPLETE_TEXT_LORAS type, created by Vue widgets)
        const inputWidget = this.widgets[0];
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

        // Set up callback for the text input widget to trigger merge logic
        inputWidget.callback = (value) => {
          if (isUpdating) return;
          isUpdating = true;

          try {
            const currentLoras = this.lorasWidget?.value || [];
            const mergedLoras = mergeLoras(value, currentLoras);
            if (this.lorasWidget) {
              this.lorasWidget.value = mergedLoras;
            }
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
      const inputWidget = node.inputWidget || node.widgets[0];
      const mergedLoras = mergeLoras(inputWidget.value, existingLoras);
      node.lorasWidget.value = mergedLoras;
    }
  },
});
