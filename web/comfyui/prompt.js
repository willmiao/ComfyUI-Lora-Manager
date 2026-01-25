import { app } from "../../scripts/app.js";
import { chainCallback } from "./utils.js";

app.registerExtension({
  name: "LoraManager.Prompt",

  async beforeRegisterNodeDef(nodeType) {
    if (nodeType.comfyClass === "Prompt (LoraManager)") {
      chainCallback(nodeType.prototype, "onNodeCreated", function () {
        this.serialize_widgets = true;

        // Get the text input widget (AUTOCOMPLETE_TEXT_EMBEDDINGS type, created by Vue widgets)
        const inputWidget = this.widgets?.[0];
        if (inputWidget) {
          this.inputWidget = inputWidget;
        }
      });
    }
  },
});
