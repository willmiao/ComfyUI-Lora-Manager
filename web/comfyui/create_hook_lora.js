import { app } from "../../scripts/app.js";
import {
  getActiveLorasFromNode,
  updateConnectedTriggerWords,
  chainCallback,
  mergeLoras,
  getWidgetByName,
  getWidgetSerializedValue,
} from "./utils.js";
import { addLorasWidget } from "./loras_widget.js";
import { applyLoraValuesToText, debounce } from "./lora_syntax_utils.js";
import { applySelectionHighlight } from "./trigger_word_highlight.js";
import { updateConnectedLoraInfoNodes } from "./lora_info.js";

app.registerExtension({
  name: "LoraManager.CreateHookLora",

  async beforeRegisterNodeDef(nodeType, nodeData, app) {
    if (nodeType.comfyClass === "Create Hook LoRA (LoraManager)") {
      chainCallback(nodeType.prototype, "onNodeCreated", function () {
        // Enable widget serialization so loras widget state is persisted
        this.serialize_widgets = true;

        this.addInput("prev_hooks", "HOOKS", {
          shape: 7,
        });

        // Flags to prevent callback loops between text widget ↔ loras widget
        let isUpdating = false;
        let isSyncingInput = false;

        // Get the text input widget (AUTOCOMPLETE_TEXT_LORAS type, created by Vue widgets)
        const inputWidget = getWidgetByName(this, "text");
        if (!inputWidget) {
          console.warn(
            "LoRA Manager: text widget not found for Create Hook LoRA"
          );
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

        // Create the LoRA list widget
        const result = addLorasWidget(
          this,
          "loras",
          {
            onSelectionChange: (selection) => {
              applySelectionHighlight(this, selection);
              updateConnectedLoraInfoNodes(this, selection);
            },
          },
          (value) => {
            // Prevent recursive calls
            if (isUpdating) return;
            isUpdating = true;

            try {
              // Update connected trigger word toggles with active LoRA names
              const activeLoraNames = new Set();
              value.forEach((lora) => {
                if (lora.active) {
                  activeLoraNames.add(lora.name);
                }
              });
              updateConnectedTriggerWords(this, activeLoraNames);
            } finally {
              isUpdating = false;
            }

            scheduleInputSync(value);
          }
        );

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

            // Update connected trigger word toggles
            const activeLoraNames = getActiveLorasFromNode(this);
            updateConnectedTriggerWords(this, activeLoraNames);
          } finally {
            isUpdating = false;
          }
        };
      });
    }
  },

  async loadedGraphNode(node) {
    if (node.comfyClass === "Create Hook LoRA (LoraManager)") {
      // Restore saved loras widget values on workflow load
      let existingLoras = [];
      if (node.widgets_values && node.widgets_values.length > 0) {
        const savedValue = getWidgetSerializedValue(node, "loras");
        existingLoras = savedValue || [];
      }
      // Merge the loras data from text widget with saved values
      const inputWidget =
        node.inputWidget || getWidgetByName(node, "text");
      if (!inputWidget) {
        console.warn(
          "LoRA Manager: text widget not found while restoring Create Hook LoRA"
        );
        return;
      }
      const mergedLoras = mergeLoras(inputWidget.value, existingLoras);
      node.lorasWidget.value = mergedLoras;
    }
  },
});
