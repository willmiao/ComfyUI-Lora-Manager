import { app } from "../../scripts/app.js";
import {
  getActiveLorasFromNode,
  updateConnectedTriggerWords,
  updateDownstreamLoaders,
  chainCallback,
  mergeLoras,
  getWidgetByName,
  getWidgetSerializedValue,
} from "./utils.js";
import { applyLoraValuesToText, debounce } from "./lora_syntax_utils.js";
import { addLoraSearchWidget, applyLoraSelection } from "./lora_stacker_search.js";
import { getNodeLoraNameDisplayPreference } from "./settings.js";

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
        const inputWidget = getWidgetByName(this, "text");
        if (!inputWidget) {
          console.warn("LoRA Manager: text widget not found for Lora Stacker");
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
          console.warn("LoRA Manager: loras widget not found for Lora Stacker");
          return;
        }
        this.lorasWidget = lorasWidget;

        lorasWidget.callback = (value) => {
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
        };

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

        // Dedicated type-to-add field above the LoRA list. It is always empty
        // until typed into, so adding a LoRA never needs a caret hunt in the
        // textarea, and it matches whatever the node rows show (title or file
        // name), read at search time so a mode change applies immediately.
        const searchWidget = addLoraSearchWidget(this, {
          getDisplayMode: getNodeLoraNameDisplayPreference,
          onSelect: (entry) => {
            if (!this.lorasWidget) {
              return;
            }
            const { loras, changed } = applyLoraSelection(
              this.lorasWidget.value || [],
              entry
            );
            if (!changed) {
              return;
            }
            this.lorasWidget.value = loras;
            // setValue only re-renders; the callback is what propagates the
            // new active set to trigger words, downstream loaders and the
            // textarea syntax.
            this.lorasWidget.callback?.(loras);
          },
        });
        this.loraSearchWidget = searchWidget;

        // Place the field directly under the prompt textarea, above the list.
        // addDOMWidget appended it last, so move it rather than adding it
        // again; it is never serialized, so this does not touch
        // widgets_values.
        if (Array.isArray(this.widgets) && this.widgets.includes(searchWidget)) {
          this.widgets.splice(this.widgets.indexOf(searchWidget), 1);
          const lorasIndex = this.widgets.indexOf(lorasWidget);
          if (lorasIndex >= 0) {
            this.widgets.splice(lorasIndex, 0, searchWidget);
          } else {
            this.widgets.push(searchWidget);
          }
        }
      });
    }
  },

  async loadedGraphNode(node) {
    if (node.comfyClass == "Lora Stacker (LoraManager)") {
      // Restore saved value if exists
      let existingLoras = [];
      if (node.widgets_values && node.widgets_values.length > 0) {
        const savedValue = getWidgetSerializedValue(node, "loras");
        existingLoras = savedValue || [];
      }
      // Merge the loras data
      const inputWidget = node.inputWidget || getWidgetByName(node, "text");
      if (!inputWidget) {
        console.warn("LoRA Manager: text widget not found while restoring Lora Stacker");
        return;
      }
      const mergedLoras = mergeLoras(inputWidget.value, existingLoras);
      node.lorasWidget.value = mergedLoras;
    }
  },
});
