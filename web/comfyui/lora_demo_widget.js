import { app } from "../../../scripts/app.js";

app.registerExtension({
  name: "LoraManager.LoraDemo",

  // Hook into node creation
  async nodeCreated(node) {
    if (node.comfyClass !== "Lora Demo (LoraManager)") {
      return;
    }

    // Store original onExecuted
    const originalOnExecuted = node.onExecuted?.bind(node);

    // Override onExecuted to handle UI updates
    node.onExecuted = function(output) {
      // Check if output has loras data
      if (output?.loras && Array.isArray(output.loras)) {
        console.log("[LoraDemoNode] Received loras data from backend:", output.loras);

        // Find the loras widget on this node
        const lorasWidget = node.widgets.find(w => w.name === 'loras');

        if (lorasWidget) {
          // Update widget value with backend data
          lorasWidget.value = output.loras;

          console.log(`[LoraDemoNode] Updated widget with ${output.loras.length} loras`);
        } else {
          console.warn("[LoraDemoNode] loras widget not found on node");
        }
      }

      // Call original onExecuted if it exists
      if (originalOnExecuted) {
        return originalOnExecuted(output);
      }
    };
  }
});
