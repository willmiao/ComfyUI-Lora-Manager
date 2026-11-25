import { app } from "../../scripts/app.js";
import {
  collectActiveLorasFromChain,
  updateConnectedTriggerWords,
  updateDownstreamLoaders,
  installTriggerWordConnectionSync,
  chainCallback,
  mergeLoras,
  getWidgetByName,
  getWidgetSerializedValue,
} from "./utils.js";
import { applyLoraValuesToText, debounce } from "./lora_syntax_utils.js";

app.registerExtension({
  name: "LoraManager.LoraStacker",

  async beforeRegisterNodeDef(nodeType, nodeData, app) {
    if (nodeType.comfyClass === "Lora Stacker (LoraManager)") {
      installTriggerWordConnectionSync(nodeType);

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
            // The stacker's runtime `trigger_words` covers its own entries plus
            // the upstream LORA_STACK, so its direct toggles need the chain-wide
            // set. Own-only names would drop the upstream pick (a Cycler's next
            // LoRA) from the toggle on every edit.
            updateConnectedTriggerWords(this, collectActiveLorasFromChain(this));

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
            // Same chain-wide set as the loras widget: the runtime output
            // includes the upstream stack, not just this node's entries.
            updateConnectedTriggerWords(this, collectActiveLorasFromChain(this));
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
