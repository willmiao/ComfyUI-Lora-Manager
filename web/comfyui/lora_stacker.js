import { app } from "../../scripts/app.js";
import {
  getActiveLorasFromNode,
  collectActiveLorasFromChain,
  updateConnectedTriggerWords,
  chainCallback,
  mergeLoras,
  setupInputWidgetWithAutocomplete,
  getLinkFromGraph,
  getNodeKey,
} from "./utils.js";
import { addLorasWidget } from "./loras_widget.js";
import { applyLoraValuesToText, debounce } from "./lora_syntax_utils.js";

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

        const result = addLorasWidget(this, "loras", {}, (value) => {
          // Prevent recursive calls
          if (isUpdating) return;
          isUpdating = true;

          try {
            // Update this stacker's direct trigger toggles with its own active loras
            const activeLoraNames = new Set();
            value.forEach((lora) => {
              if (lora.active) {
                activeLoraNames.add(lora.name);
              }
            });
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
            const activeLoraNames = getActiveLorasFromNode(this);
            updateConnectedTriggerWords(this, activeLoraNames);

            // Find all Lora Loader nodes in the chain that might need updates
            updateDownstreamLoaders(this);
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
    if (node.comfyClass == "Lora Stacker (LoraManager)") {
      requestAnimationFrame(async () => {
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
      });
    }
  },
});

// Helper function to find and update downstream Lora Loader nodes
function updateDownstreamLoaders(startNode, visited = new Set()) {
  const nodeKey = getNodeKey(startNode);
  if (!nodeKey || visited.has(nodeKey)) return;
  visited.add(nodeKey);

  // Check each output link
  if (startNode.outputs) {
    for (const output of startNode.outputs) {
      if (output.links) {
        for (const linkId of output.links) {
          const link = getLinkFromGraph(startNode.graph, linkId);
          if (link) {
            const targetNode = startNode.graph?.getNodeById?.(link.target_id);

            // If target is a Lora Loader, collect all active loras in the chain and update
            if (
              targetNode &&
              targetNode.comfyClass === "Lora Loader (LoraManager)"
            ) {
              const allActiveLoraNames =
                collectActiveLorasFromChain(targetNode);
              updateConnectedTriggerWords(targetNode, allActiveLoraNames);
            }
            // If target is another Lora Stacker, recursively check its outputs
            else if (
              targetNode &&
              targetNode.comfyClass === "Lora Stacker (LoraManager)"
            ) {
              updateDownstreamLoaders(targetNode, visited);
            }
          }
        }
      }
    }
  }
}
