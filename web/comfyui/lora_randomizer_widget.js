import { app } from "../../../scripts/app.js";

app.registerExtension({
  name: "LoraManager.LoraRandomizer",

  // Hook into node creation
  async nodeCreated(node) {
    if (node.comfyClass !== "Lora Randomizer (LoraManager)") {
      return;
    }

    console.log("[LoraRandomizerWidget] Node created:", node.id);

    // Store original onExecuted
    const originalOnExecuted = node.onExecuted?.bind(node);

    // Override onExecuted to handle UI updates
    node.onExecuted = function(output) {
      console.log("[LoraRandomizerWidget] Node executed with output:", output);

      // Check if output has loras data
      if (output?.loras && Array.isArray(output.loras)) {
        console.log("[LoraRandomizerWidget] Received loras data from backend:", output.loras);

        // Find the loras widget on this node
        const lorasWidget = node.widgets.find(w => w.name === 'loras');

        if (lorasWidget) {
          // Update widget value with backend data
          lorasWidget.value = output.loras;

          console.log(`[LoraRandomizerWidget] Updated widget with ${output.loras.length} loras`);
        } else {
          console.warn("[LoraRandomizerWidget] loras widget not found on node");
        }
      }

      // Call original onExecuted if it exists
      if (originalOnExecuted) {
        return originalOnExecuted(output);
      }
    };
  }
});
