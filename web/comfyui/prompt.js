import { app } from "../../scripts/app.js";
import { chainCallback, setupInputWidgetWithAutocomplete } from "./utils.js";

app.registerExtension({
  name: "LoraManager.Prompt",

  async beforeRegisterNodeDef(nodeType) {
    if (nodeType.comfyClass === "Prompt (LoraManager)") {
      chainCallback(nodeType.prototype, "onNodeCreated", function () {
        this.serialize_widgets = true;

        const textWidget = this.widgets?.[0];
        if (!textWidget) {
          return;
        }

        const originalCallback =
          typeof textWidget.callback === "function" ? textWidget.callback : null;

        textWidget.callback = setupInputWidgetWithAutocomplete(
          this,
          textWidget,
          originalCallback,
          "embeddings"
        );
      });
    }
  },
});
