import { app } from "../../scripts/app.js";
import {
  getActiveLorasFromNode,
  updateConnectedTriggerWords,
  chainCallback,
  mergeLoras,
  setupInputWidgetWithAutocomplete,
} from "./utils.js";
import { addLorasWidget } from "./loras_widget.js";
import { applyLoraValuesToText, debounce } from "./lora_syntax_utils.js";

app.registerExtension({
  name: "LoraManager.WanVideoLoraSelect",

  async beforeRegisterNodeDef(nodeType, nodeData, app) {
    if (nodeType.comfyClass === "WanVideo Lora Select (LoraManager)") {
      chainCallback(nodeType.prototype, "onNodeCreated", async function () {
        // Enable widget serialization
        this.serialize_widgets = true;

        // Add optional inputs
        this.addInput("prev_lora", "WANVIDLORA", {
          shape: 7, // 7 is the shape of the optional input
        });

        this.addInput("blocks", "SELECTEDBLOCKS", {
          shape: 7, // 7 is the shape of the optional input
        });

        // Add flags to prevent callback loops
        let isUpdating = false;
        let isSyncingInput = false;

        const inputWidget = this.widgets[2];
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

        const result = addLorasWidget(this, "loras", {}, (value) => {
          // Prevent recursive calls
          if (isUpdating) return;
          isUpdating = true;

          try {
            // Update this node's direct trigger toggles with its own active loras
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

            // Update this node's direct trigger toggles with its own active loras
            const activeLoraNames = getActiveLorasFromNode(this);
            updateConnectedTriggerWords(this, activeLoraNames);
          } finally {
            isUpdating = false;
          }
        };
        inputWidget.callback = setupInputWidgetWithAutocomplete(
          this,
          inputWidget,
          originalCallback
        );
      });
    }
  },
  async nodeCreated(node) {
    if (node.comfyClass == "WanVideo Lora Select (LoraManager)") {
      requestAnimationFrame(async () => {
        // Restore saved value if exists
        let existingLoras = [];
        if (node.widgets_values && node.widgets_values.length > 0) {
          // 0 for low_mem_load, 1 for merge_loras, 2 for text widget, 3 for loras widget
          const savedValue = node.widgets_values[3];
          existingLoras = savedValue || [];
        }
        // Merge the loras data
        const mergedLoras = mergeLoras(node.widgets[2].value, existingLoras);
        node.lorasWidget.value = mergedLoras;
      });
    }
  },
});
